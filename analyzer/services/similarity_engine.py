from pathlib import Path
import importlib.util
import sys, os
import matplotlib

# Gunakan backend non-GUI untuk generate gambar di server
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# === Load modul similarity_astfix.py secara dinamis ===
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

spec = importlib.util.spec_from_file_location(
    "similarity_astfix",
    CURRENT_DIR / "similarity_astfix.py"
)
similarity_astfix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(similarity_astfix)


def run_analysis(src_dir: Path, out_dir: Path, ast_weights=None, threshold: float = 0.85):
    """
    Menjalankan analisis AST similarity menggunakan engine di similarity_astfix.py

    Parameters
    ----------
    src_dir : Path
        Folder berisi file .py hasil ekstrak dari ZIP.
    out_dir : Path
        Folder output untuk menyimpan CSV, TXT, XLSX, dan PNG.
    ast_weights : dict | None
        Bobot indikator AST. Jika None, akan memakai similarity_astfix.AST_WEIGHTS.
        Contoh:
        {
            "structure": 0.18,
            "execution_order": 0.12,
            ...
        }
    threshold : float
        Batas minimal similarity blok untuk dianggap "mirip".
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # Jika tidak ada bobot custom, pakai default dari modul engine
    if ast_weights is None:
        ast_weights = similarity_astfix.AST_WEIGHTS

    # Kumpulkan file .py
    files = [str(p) for p in Path(src_dir).glob("*.py")]
    if len(files) < 2:
        raise RuntimeError("Minimal dua file .py diperlukan untuk analisis.")

    # Siapkan struktur matriks similaritas
    import pandas as pd
    file_names = [os.path.basename(f) for f in files]
    matrix = pd.DataFrame(index=file_names, columns=file_names, data=0.0)

    similar_blocks_all = []

    # === Hitung similaritas antar file ===
    for i in range(len(files)):
        for j in range(i, len(files)):
            # Similaritas file vs file dengan bobot AST
            sim = similarity_astfix.compute_similarity(
                files[i],
                files[j],
                ast_weights=ast_weights
            )
            matrix.iloc[i, j] = sim
            matrix.iloc[j, i] = sim

            # Cari blok-blok kode mirip (fungsi/loop/if, dll)
            code1 = similarity_astfix.read_file(files[i])
            code2 = similarity_astfix.read_file(files[j])
            similar_parts = similarity_astfix.find_similar_blocks(
                code1,
                code2,
                threshold=threshold,
                ast_weights=ast_weights
            )
            if similar_parts:
                similar_blocks_all.append({
                    "file1": os.path.basename(files[i]),
                    "file2": os.path.basename(files[j]),
                    "similar_blocks": similar_parts
                })

    # === Simpan hasil utama ===
    result_csv = out_dir / "hasil_similaritas.csv"
    matrix.to_csv(result_csv)

    # Simpan blok-blok mirip dalam TXT & Excel melalui fungsi di engine
    similarity_astfix.save_similar_blocks_txt(similar_blocks_all, str(out_dir))
    similarity_astfix.save_similar_blocks_excel(similar_blocks_all, str(out_dir))

    # === Generate heatmap ===
    import seaborn as sns

    plt.figure(figsize=(10, 8))
    sns.heatmap(matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
    plt.title("Heatmap Similaritas Kode Python")
    plt.xticks(rotation=90)
    plt.yticks(rotation=0)
    plt.tight_layout()
    heatmap_path = out_dir / "heatmap_similaritas.png"
    plt.savefig(heatmap_path)
    plt.close()

    # === Kembalikan objek hasil ke views.py ===
    return matrix, {
        "csv": result_csv,
        "txt": out_dir / "blok_kode_mirip.txt",
        "xlsx": out_dir / "blok_kode_mirip.xlsx",
        "png": heatmap_path
    }
