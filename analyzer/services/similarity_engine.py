from pathlib import Path
import importlib.util
import sys, os
import matplotlib
matplotlib.use("Agg")   # <— Tambahkan ini paling atas file sebelum import pyplot
import matplotlib.pyplot as plt

# import modul similarity_astfix.py
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

spec = importlib.util.spec_from_file_location("similarity_astfix", CURRENT_DIR / "similarity_astfix.py")
similarity_astfix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(similarity_astfix)


def run_analysis(src_dir: Path, out_dir: Path):
    """
    Menjalankan analisis AST similarity menggunakan engine milik pengguna
    (similarity_astfix.py), dan mengambil file hasil yang dihasilkan di folder out_dir.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # === Jalankan engine utama ===
    # Kita adaptasikan agar fungsi compare_all_files() bisa dipanggil secara langsung.
    # Caranya: ubah sedikit fungsi itu agar menerima path input dan output.
    # Untuk sementara, kita tiru perilakunya dengan cara di bawah ini.
    files = [str(p) for p in Path(src_dir).glob("*.py")]
    if len(files) < 2:
        raise RuntimeError("Minimal dua file .py diperlukan untuk analisis.")

    # Panggil fungsi2 dari engine aslimu
    file_names = [os.path.basename(f) for f in files]
    import pandas as pd

    matrix = pd.DataFrame(index=file_names, columns=file_names, data=0.0)
    similar_blocks_all = []

    for i in range(len(files)):
        for j in range(i, len(files)):
            sim = similarity_astfix.compute_similarity(files[i], files[j])
            matrix.iloc[i, j] = sim
            matrix.iloc[j, i] = sim

            code1 = similarity_astfix.read_file(files[i])
            code2 = similarity_astfix.read_file(files[j])
            similar_parts = similarity_astfix.find_similar_blocks(code1, code2)
            if similar_parts:
                similar_blocks_all.append({
                    "file1": os.path.basename(files[i]),
                    "file2": os.path.basename(files[j]),
                    "similar_blocks": similar_parts
                })

    # simpan hasil ke folder hasil engine utama (versi kamu)
    result_csv = out_dir / "hasil_similaritas.csv"
    matrix.to_csv(result_csv)

    similarity_astfix.save_similar_blocks_txt(similar_blocks_all, str(out_dir))
    similarity_astfix.save_similar_blocks_excel(similar_blocks_all, str(out_dir))

    # heatmap otomatis dibuat sesuai fungsi di engine kamu (gunakan seaborn / plt)
    import seaborn as sns
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 8))
    sns.heatmap(matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
    plt.title("Heatmap Similaritas Kode Python")
    plt.xticks(rotation=90)
    plt.yticks(rotation=0)
    plt.tight_layout()
    heatmap_path = out_dir / "heatmap_similaritas.png"
    plt.savefig(heatmap_path)
    plt.close()

    # === Kembalikan file hasil untuk web ===
    return matrix, {
        "csv": result_csv,
        "txt": out_dir / "blok_kode_mirip.txt",
        "xlsx": out_dir / "blok_kode_mirip.xlsx",
        "png": heatmap_path
    }
