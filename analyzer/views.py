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

        # ✅ 1) Ambil bobot AST dari form
        weights = {
            "structure": form.cleaned_data["structure_weight"],
            "execution_order": form.cleaned_data["execution_order_weight"],
            "hierarchy": form.cleaned_data["hierarchy_weight"],
            "variable_names": form.cleaned_data["variable_names_weight"],
            "comments": form.cleaned_data["comments_weight"],
            "formatting": form.cleaned_data["formatting_weight"],
            "logic_modification": form.cleaned_data["logic_modification_weight"],
        }

        # ✅ 2) Normalisasi agar total bobot = 1 (opsional tapi rapi)
        total = sum(weights.values()) or 1
        weights = {k: v / total for k, v in weights.items()}

        # ✅ 3) Siapkan folder kerja
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

        # ✅ 4) KIRIM bobot ke run_analysis
        df, outputs = run_analysis(work_dir, out_dir, ast_weights=weights)
        with open(outputs["txt"], encoding="utf-8") as f:
            txt_lines = f.read().splitlines()

        # batasi hanya beberapa baris pertama untuk preview txt
        txt_preview = txt_lines[:5]   # 5 baris contoh

        total_rows = len(df)
        total_cols = len(df.columns)
        total_cells = df.size  # rows * cols

        # --- buat sample pasangan dari matriks (bukan tabel lebar) ---
        pairs = []
        index_names = list(df.index)
        col_names = list(df.columns)

        for i in range(len(index_names)):
            for j in range(i + 1, len(col_names)):   # hanya segitiga atas
                pairs.append({
                    "file_a": index_names[i],
                    "file_b": col_names[j],
                    "score": float(df.iloc[i, j] or 0.0),
                })

        # urutkan dari similarity tertinggi
        pairs_sorted = sorted(pairs, key=lambda x: x["score"], reverse=True)

        # ambil hanya 3 contoh teratas
        csv_pairs_preview = pairs_sorted[:3]

        preview = {
            "txt": txt_preview,
            "csv_pairs": csv_pairs_preview,
            "xlsx": f"Matriks {total_rows} × {total_cols} (total {total_cells} nilai similaritas).",
            "png": outputs["png"].name,
        }



        # Siapkan context hasil (tambah bobot kalau mau ditampilkan di result.html)
        context = {
            "files": [
                {"label": "Blok Kode Mirip (.txt)", "filename": outputs['txt'].name, "job_id": job_id},
                {"label": "Blok Kode Mirip (.xlsx)", "filename": outputs['xlsx'].name, "job_id": job_id},
                {"label": "Matriks Similaritas (.csv)", "filename": outputs['csv'].name, "job_id": job_id},
                {"label": "Heatmap Similaritas (.png)", "filename": outputs['png'].name, "job_id": job_id},
            ],

            "matrix": df.round(2).to_html(classes="table table-bordered", border=0),
            "weights": weights,  # ✅ kalau mau dipakai di result.html
            "preview": preview
        }

        return render(request, "result.html", context)


# === View untuk download file hasil dengan MIME type sesuai ===
def download_result(request, job_id, filename):
    """Melayani download file hasil analisis dengan MIME type sesuai."""
    file_path = Path(settings.MEDIA_ROOT) / "results" / job_id / filename
    if not file_path.exists():
        raise Http404("File tidak ditemukan")

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    response = FileResponse(open(file_path, 'rb'), content_type=mime_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
