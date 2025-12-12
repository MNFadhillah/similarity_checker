from pathlib import Path
import importlib.util
import sys, os
import matplotlib
import logging 

logger = logging.getLogger(__name__)

# Backend non-GUI (aman untuk server)
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# === Load similarity_astfix.py ===
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

spec = importlib.util.spec_from_file_location(
    "similarity_astfix",
    CURRENT_DIR / "similarity_astfix.py"
)
similarity_astfix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(similarity_astfix)


def run_analysis(src_dir: Path, out_dir: Path, ast_weights=None, threshold: float = 0.75):
    # --- sanitasi threshold ---
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = 0.75
    threshold = max(0.0, min(1.0, threshold))

    out_dir.mkdir(parents=True, exist_ok=True)

    # fallback bobot
    if ast_weights is None:
        ast_weights = similarity_astfix.AST_WEIGHTS

    # normalisasi bobot
    def _normalize_weights(w):
        w = {k: float(v) for k, v in w.items()}
        s = sum(w.values())
        if s <= 0:
            return {k: 1 / len(w) for k in w}
        return {k: v / s for k, v in w.items()}

    ast_weights = _normalize_weights(ast_weights)

    # kumpulkan file
    files = sorted(Path(src_dir).glob("*.py"))
    if len(files) < 2:
        raise RuntimeError("Minimal dua file .py diperlukan.")

    import pandas as pd
    file_names = [f.name for f in files]

    # --- Matriks similarity (SEMUA pasangan) ---
    matrix = pd.DataFrame(index=file_names, columns=file_names, data=0.0)
    for name in file_names:
        matrix.loc[name, name] = 1.0

    similar_blocks_all = []

    # --- Loop pasangan file ---
    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            f1, f2 = files[i], files[j]

            # similarity file-level
            try:
                sim = similarity_astfix.compute_similarity(
                    str(f1), str(f2), ast_weights=ast_weights
                )
                sim = float(sim or 0.0)
            except Exception as e:
                logger.exception("compute_similarity gagal")
                sim = 0.0

            matrix.loc[f1.name, f2.name] = sim
            matrix.loc[f2.name, f1.name] = sim

            # === BLOK KODE (TANPA FILTER) ===
            try:
                code1 = similarity_astfix.read_file(f1)
                code2 = similarity_astfix.read_file(f2)

                if code1 and code2:
                    blocks = similarity_astfix.find_similar_blocks(
                        code1,
                        code2,
                        threshold=threshold,     # dipakai untuk LABEL
                        ast_weights=ast_weights
                    )

                    # ⬅️ SIMPAN SEMUA, walaupun rendah
                    if blocks:
                        similar_blocks_all.append({
                            "file1": f1.name,
                            "file2": f2.name,
                            "similar_blocks": blocks
                        })

            except Exception as e:
                logger.exception("find_similar_blocks gagal")

    # --- Simpan CSV ---
    result_csv = out_dir / "hasil_similaritas.csv"
    matrix.to_csv(result_csv)

    # --- Simpan TXT & XLSX (SEMUA BLOK) ---
    similarity_astfix.save_similar_blocks_txt(similar_blocks_all, str(out_dir))
    similarity_astfix.save_similar_blocks_excel(similar_blocks_all, str(out_dir))

    # --- Heatmap ---
    import seaborn as sns
    plt.figure(figsize=(10, 8))
    sns.heatmap(matrix.astype(float), annot=True, cmap="coolwarm", fmt=".2f")
    plt.title("Heatmap Similaritas Kode Python")
    plt.xticks(rotation=90)
    plt.tight_layout()

    heatmap_path = out_dir / "heatmap_similaritas.png"
    plt.savefig(heatmap_path)
    plt.close()

    return matrix, {
        "csv": result_csv,
        "txt": out_dir / "blok_kode_mirip.txt",
        "xlsx": out_dir / "blok_kode_mirip.xlsx",
        "png": heatmap_path
    }
