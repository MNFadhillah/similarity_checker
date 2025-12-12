from django.shortcuts import render, redirect
import uuid
from pathlib import Path
from django.conf import settings
from django.urls import reverse
from .forms import UploadZipForm
from .utils.zip_utils import safe_extract
from .services.similarity_engine import run_analysis
from django.http import FileResponse, Http404
import mimetypes
import logging
import shutil

logger = logging.getLogger(__name__)


# === Halaman utama: landing + upload zip ===
def index(request):
    if request.method == "GET":
        form = UploadZipForm()
        return render(request, "index.html", {"form": form})

    if request.method == "POST":
        form = UploadZipForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request,
                "index.html",
                {"form": form, "error": "Pastikan file .zip dan bobot valid."}
            )

        # 1) Ambil bobot AST dari form
        weights = {
            "structure": form.cleaned_data.get("structure_weight", 0.0),
            "execution_order": form.cleaned_data.get("execution_order_weight", 0.0),
            "hierarchy": form.cleaned_data.get("hierarchy_weight", 0.0),
            "variable_names": form.cleaned_data.get("variable_names_weight", 0.0),
            "comments": form.cleaned_data.get("comments_weight", 0.0),
            "formatting": form.cleaned_data.get("formatting_weight", 0.0),
            "logic_modification": form.cleaned_data.get("logic_modification_weight", 0.0),
        }

        # 2) Normalisasi agar total bobot = 1 (jaga dari pembagian nol)
        total = sum(weights.values())
        if total <= 0:
            # fallback: beri bobot rata-rata jika semua input 0
            n = len(weights)
            weights = {k: 1.0 / n for k in weights}
        else:
            weights = {k: v / total for k, v in weights.items()}

        # Ambil threshold (pastikan berada di 0..1)
        threshold = form.cleaned_data.get("threshold", 0.75)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            threshold = 0.75
        threshold = max(0.0, min(1.0, threshold))

        # 3) Siapkan folder kerja
        job_id = uuid.uuid4().hex[:12]
        upload_dir = Path(settings.MEDIA_ROOT) / "uploads" / job_id
        work_dir = Path(settings.MEDIA_ROOT) / "workspaces" / job_id
        out_dir = Path(settings.MEDIA_ROOT) / "results" / job_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Simpan file upload
        zip_file = form.cleaned_data['zip_file']
        zip_path = upload_dir / zip_file.name
        with zip_path.open("wb") as f:
            for chunk in zip_file.chunks():
                f.write(chunk)

        # Ekstrak dan jalankan analisis
        safe_extract(zip_path, work_dir)
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("Gagal menghapus ZIP: %s", zip_path)

        # 4) Kirim bobot + threshold ke run_analysis
        try:
            df, outputs = run_analysis(work_dir, out_dir, ast_weights=weights, threshold=threshold)
        except Exception as e:
            logger.exception("run_analysis gagal")
            return render(
                request,
                "index.html",
                {"form": form, "error": f"Terjadi kesalahan saat menganalisis berkas: {e}"}
            )
        try:
            shutil.rmtree(work_dir)
        except Exception:
            logger.warning("Gagal menghapus workspace: %s", work_dir)
        # outputs expected: dict with Path or string values for keys 'txt','xlsx','csv','png'
        # buka txt hasil (jika tersedia)
        txt_preview = []
        txt_path = outputs.get("txt")
        if txt_path and Path(txt_path).exists():
            with open(txt_path, encoding="utf-8") as f:
                txt_lines = f.read().splitlines()
            txt_preview = txt_lines[:5]

        total_rows = len(df)
        total_cols = len(df.columns)
        total_cells = df.size  # rows * cols

        # --- buat sample pasangan dari matriks (robust terhadap index/column mismatch) ---
        index_names = list(df.index)
        col_names = list(df.columns)

        # jika index dan column berbeda format (mis. path penuh vs basename), gunakan union
        if index_names != col_names:
            names = sorted(set(index_names) | set(col_names))
        else:
            names = index_names

        pairs = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a = names[i]
                b = names[j]
                score = 0.0
                try:
                    # coba ambil nilai dari df dengan beberapa guard
                    if a in df.index and b in df.columns:
                        score = float(df.loc[a, b] or 0.0)
                    elif b in df.index and a in df.columns:
                        score = float(df.loc[b, a] or 0.0)
                except Exception:
                    score = 0.0
                pairs.append({
                    "file_a": a,
                    "file_b": b,
                    "score": score,
                })

        # urutkan dari similarity tertinggi
        pairs_sorted = sorted(pairs, key=lambda x: x["score"], reverse=True)

        # ====== buat statistik skor dan tentukan tier (fixed atau percentile) ======
        def _percentile(sorted_list, p):
            """Simple percentile (p in 0..100) on a sorted list (returns value)."""
            if not sorted_list:
                return None
            k = (len(sorted_list) - 1) * (p / 100.0)
            f = int(k)
            return sorted_list[f]

        scores = [p["score"] for p in pairs_sorted]
        percentiles = None
        tier_mode = "fixed"
        if len(scores) >= 5:
            sorted_scores = sorted(scores)
            p50 = float(_percentile(sorted_scores, 50))
            p90 = float(_percentile(sorted_scores, 90))
            percentiles = {"p50": p50, "p90": p90}
            tier_mode = "percentile"

        def map_score_to_tier_by_threshold(score, threshold):
            """
            Menentukan tingkat kemiripan berdasarkan threshold pengguna.
            """
            s = float(score)
            t = float(threshold)

            # batas atas kategori sedang
            mid_high = t + (1.0 - t) / 2.0

            if s < t:
                return "Rendah", "Kemiripan di bawah threshold.", "badge-low"
            elif s < mid_high:
                return "Sedang", "Kemiripan melewati threshold, perlu ditinjau.", "badge-mid"
            else:
                return "Tinggi", "Kemiripan sangat tinggi, indikasi kuat.", "badge-high"


        # buat list display_pairs yang berisi tier & pesan
        display_pairs = []
        for p in pairs_sorted:
            label, msg, cls = map_score_to_tier_by_threshold(p["score"], threshold)
            display_pairs.append({
                "file_a": p["file_a"],
                "file_b": p["file_b"],
                "score": p["score"],
                "tier_label": label,
                "tier_message": msg,
                "tier_class": cls,
            })


        # ambil hanya 3 contoh teratas (pakai display_pairs agar sudah berisi tier)
        csv_pairs_preview = display_pairs[:3]

        preview = {
            "txt": txt_preview,
            "csv_pairs": csv_pairs_preview,
            "xlsx": f"Matriks {total_rows} × {total_cols} (total {total_cells} nilai similaritas).",
            "png": Path(outputs.get("png")).name if outputs.get("png") else None,
        }


        df_info = {
            "rows": int(total_rows),
            "cols": int(total_cols),
            "min_val": float(df.min().min()) if df.size else None,
            "max_val": float(df.max().max()) if df.size else None,
            "pairs_count": len(pairs_sorted),
        }

        context = {
            "files": [
                {"label": "Blok Kode Mirip (.txt)", "filename": Path(outputs.get('txt')).name if outputs.get('txt') else None, "job_id": job_id},
                {"label": "Blok Kode Mirip (.xlsx)", "filename": Path(outputs.get('xlsx')).name if outputs.get('xlsx') else None, "job_id": job_id},
                {"label": "Matriks Similaritas (.csv)", "filename": Path(outputs.get('csv')).name if outputs.get('csv') else None, "job_id": job_id},
                {"label": "Heatmap Similaritas (.png)", "filename": Path(outputs.get('png')).name if outputs.get('png') else None, "job_id": job_id},
            ],
            "matrix": df.round(2).to_html(classes="table table-bordered", border=0),
            "weights": weights,
            "threshold": threshold,
            "preview": preview,
            "display_pairs": display_pairs,
        }


        return render(request, "result.html", context)


# === View untuk download file hasil dengan MIME type sesuai ===
def download_result(request, job_id, filename):
    """Melayani download file hasil analisis dengan MIME type sesuai."""
    file_path = Path(settings.MEDIA_ROOT) / "results" / job_id / filename
    if not file_path.exists():
        raise Http404("File tidak ditemukan")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = 'application/octet-stream'

    # gunakan Path.open untuk konsistensi
    response = FileResponse(file_path.open('rb'), content_type=mime_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
