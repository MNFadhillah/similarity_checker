from django.shortcuts import render
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse
from pathlib import Path
import os, zipfile, shutil, time
from checker.similarity_ast6 import run_similarity_analysis  # fungsi kamu

def upload_view(request):
    if request.method == "POST":
        uploaded_zip = request.FILES.get("zipfile")
        if not uploaded_zip:
            return render(request, "checker/upload.html", {"error": "Tidak ada file ZIP yang diunggah."})

        # Folder dasar
        base_upload_dir = Path("media/uploads/")
        base_result_dir = Path("media/results/")
        base_upload_dir.mkdir(parents=True, exist_ok=True)
        base_result_dir.mkdir(parents=True, exist_ok=True)

        # Simpan file zip
        fs = FileSystemStorage(location=base_upload_dir)
        zip_filename = fs.save(uploaded_zip.name, uploaded_zip)
        zip_path = base_upload_dir / zip_filename

        # Ekstrak ZIP
        extract_dir = base_upload_dir / uploaded_zip.name.replace(".zip", "")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # Jalankan analisis
        try:
            heatmap_path, matrix = run_similarity_analysis(extract_dir)
        except ValueError as e:
            return render(request, "checker/upload.html", {"error": str(e)})

        # Simpan hasil ke folder terpisah
        result_folder = base_result_dir / f"hasil_{int(time.time())}"
        result_folder.mkdir(parents=True, exist_ok=True)

        # Simpan tabel similarity
        csv_path = result_folder / "matrix_similarity.csv"
        matrix.to_csv(csv_path, float_format="%.2f")

        # Pindahkan heatmap
        heatmap_dest = result_folder / "heatmap_similaritas.png"
        shutil.copy(heatmap_path, heatmap_dest)

        # Buat file ZIP hasil
        output_zip = base_result_dir / f"{result_folder.name}.zip"
        shutil.make_archive(str(output_zip).replace(".zip", ""), "zip", result_folder)

        # Path untuk tampilan
        context = {
            "heatmap_url": f"/media/results/{result_folder.name}/heatmap_similaritas.png",
            "table_html": matrix.to_html(classes="table table-striped", float_format="%.2f"),
            "download_url": f"/download/{result_folder.name}.zip",  # arahkan ke view download
        }
        return render(request, "checker/result.html", context)

    return render(request, "checker/upload.html")


def download_result_view(request, filename):
    """Fungsi untuk handle tombol download ZIP hasil."""
    file_path = Path("media/results") / filename
    print("Mencari file:", file_path)  # untuk debug
    if not file_path.exists():
        raise Http404("File hasil tidak ditemukan di server.")
    return FileResponse(open(file_path, "rb"), as_attachment=True, filename=file_path.name)
