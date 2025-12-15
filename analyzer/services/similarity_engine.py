from pathlib import Path
import logging
import ast
import re
import difflib
import os

import matplotlib
matplotlib.use("Agg")   # aman untuk server
import matplotlib.pyplot as plt
import seaborn as sns

import pandas as pd
from openpyxl import Workbook

logger = logging.getLogger(__name__)

# =========================================================
# DEFAULT BOBOT AST (BISA DIOVERRIDE DARI FORM)
# =========================================================
DEFAULT_AST_WEIGHTS = {
    "structure": 0.18,
    "execution_order": 0.12,
    "hierarchy": 0.10,
    "variable_names": 0.20,
    "comments": 0.20,
    "formatting": 0.10,
    "logic_modification": 0.10,
}


# =========================================================
# UTIL DASAR
# =========================================================
def normalize_weights(weights: dict) -> dict:
    weights = {k: float(v) for k, v in weights.items()}
    total = sum(weights.values())
    if total <= 0:
        return {k: 1.0 / len(weights) for k in weights}
    return {k: v / total for k, v in weights.items()}


def read_file(path: Path) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


# =========================================================
# SIMILARITY UTIL (VERSI DOSEN)
# =========================================================
def numeric_similarity(a: float, b: float) -> float:
    max_val = max(a, b)
    return 1.0 if max_val == 0 else 1 - abs(a - b) / max_val


def comment_similarity(t1: str, t2: str) -> float:
    if not t1 and not t2:
        return 1.0
    return difflib.SequenceMatcher(None, t1, t2).ratio()


# =========================================================
# EKSTRAKSI KOMENTAR
# =========================================================
def extract_comment_strings(code: str) -> str:
    comments = []

    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            comments.append(stripped[1:].strip())
        elif "#" in line:
            comments.append(line.split("#", 1)[1].strip())

    triple = r"(?:'''(.*?)'''|\"\"\"(.*?)\"\"\")"
    matches = re.findall(triple, code, re.DOTALL)
    for m in matches:
        text = m[0] or m[1]
        if text.strip():
            comments.append(text.strip())

    return "\n".join(comments)


# =========================================================
# EKSTRAKSI FITUR AST
# =========================================================
def get_ast_features(code: str) -> dict | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))]
    conditionals = [n for n in ast.walk(tree) if isinstance(n, ast.If)]
    assignments = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}

    return {
        "structure": len(functions) + len(loops) + len(conditionals),
        "execution_order": sum(1 for _ in ast.walk(tree)),
        "hierarchy": sum(1 for f in functions if f.body),
        "variable_names": len(names),
        "logic_modification": len(assignments),
        "formatting": code.count(" ") + code.count("\t"),
        "comment_text": extract_comment_strings(code),
    }


# =========================================================
# CORE SIMILARITY (FILE / BLOK)
# =========================================================
def block_similarity(code1: str, code2: str, weights: dict) -> float:
    f1 = get_ast_features(code1)
    f2 = get_ast_features(code2)
    if not f1 or not f2:
        return 0.0

    scores = {
        "structure": numeric_similarity(f1["structure"], f2["structure"]),
        "execution_order": numeric_similarity(f1["execution_order"], f2["execution_order"]),
        "hierarchy": numeric_similarity(f1["hierarchy"], f2["hierarchy"]),
        "variable_names": numeric_similarity(f1["variable_names"], f2["variable_names"]),
        "logic_modification": numeric_similarity(f1["logic_modification"], f2["logic_modification"]),
        "formatting": numeric_similarity(f1["formatting"], f2["formatting"]),
        "comments": comment_similarity(f1["comment_text"], f2["comment_text"]),
    }

    return sum(scores[k] * weights[k] for k in weights)


# =========================================================
# EKSTRAKSI BLOK KODE
# =========================================================
def extract_code_blocks(code: str):
    blocks = []
    try:
        tree = ast.parse(code)
        lines = code.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.For, ast.While, ast.If)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    block = "\n".join(lines[node.lineno - 1: node.end_lineno])
                    blocks.append((type(node).__name__, block))
    except Exception:
        pass
    return blocks


def find_similar_blocks(code1: str, code2: str, threshold: float, weights: dict):
    results = []
    for t1, b1 in extract_code_blocks(code1):
        for t2, b2 in extract_code_blocks(code2):
            if t1 != t2:
                continue
            score = block_similarity(b1, b2, weights)
            if score >= threshold:
                results.append({
                    "type": t1,
                    "score": round(score, 3),
                    "snippet_a": b1[:120],
                    "snippet_b": b2[:120],
                })
    return results


# =========================================================
# SIMPAN OUTPUT
# =========================================================
def save_similar_blocks_txt(data, out_dir: Path):
    path = out_dir / "blok_kode_mirip.txt"
    with open(path, "w", encoding="utf-8") as f:
        for e in data:
            f.write(f"{e['file1']} vs {e['file2']}\n")
            for b in e["similar_blocks"]:
                f.write(f"  {b['type']} | {b['score']:.2f}\n")
            f.write("-" * 40 + "\n")


def save_similar_blocks_excel(data, out_dir: Path):
    path = out_dir / "blok_kode_mirip.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["File A", "File B", "Jenis", "Score", "Kode A", "Kode B"])

    for e in data:
        for b in e["similar_blocks"]:
            ws.append([
                e["file1"],
                e["file2"],
                b["type"],
                b["score"],
                b["snippet_a"],
                b["snippet_b"],
            ])
    wb.save(path)


# =========================================================
# MAIN ENTRY (DIPANGGIL DARI views.py)
# =========================================================
def run_analysis(src_dir: Path, out_dir: Path, ast_weights=None, threshold: float = 0.75):
    out_dir.mkdir(parents=True, exist_ok=True)

    weights = normalize_weights(ast_weights or DEFAULT_AST_WEIGHTS)

    files = sorted(Path(src_dir).glob("*.py"))
    if len(files) < 2:
        raise RuntimeError("Minimal dua file .py diperlukan.")

    names = [f.name for f in files]
    matrix = pd.DataFrame(index=names, columns=names, data=0.0)

    similar_blocks_all = []

    for i in range(len(files)):
        for j in range(i, len(files)):
            f1, f2 = files[i], files[j]
            c1, c2 = read_file(f1), read_file(f2)
            if not c1 or not c2:
                continue

            sim = block_similarity(c1, c2, weights)
            matrix.loc[f1.name, f2.name] = sim
            matrix.loc[f2.name, f1.name] = sim

            if i != j:
                blocks = find_similar_blocks(c1, c2, threshold, weights)
                if blocks:
                    similar_blocks_all.append({
                        "file1": f1.name,
                        "file2": f2.name,
                        "similar_blocks": blocks
                    })

    # CSV
    csv_path = out_dir / "hasil_similaritas.csv"
    matrix.to_csv(csv_path)

    # TXT & XLSX
    save_similar_blocks_txt(similar_blocks_all, out_dir)
    save_similar_blocks_excel(similar_blocks_all, out_dir)

    # Heatmap
    plt.figure(figsize=(10, 8))
    sns.heatmap(matrix.astype(float), annot=True, fmt=".2f", cmap="coolwarm")
    plt.title("Heatmap Similaritas Kode Python")
    plt.tight_layout()

    png_path = out_dir / "heatmap_similaritas.png"
    plt.savefig(png_path)
    plt.close()

    return matrix, {
        "csv": csv_path,
        "txt": out_dir / "blok_kode_mirip.txt",
        "xlsx": out_dir / "blok_kode_mirip.xlsx",
        "png": png_path,
    }
