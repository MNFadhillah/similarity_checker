import ast
import os
import re
import difflib
from openpyxl import Workbook

# =========================================================
# DEFAULT BOBOT AST (DAPAT DIOVERRIDE DARI FORM DJANGO)
# =========================================================
DEFAULT_AST_WEIGHTS = {
    "structure": 0.30,
    "execution_order": 0.15,
    "hierarchy": 0.10,
    "variable_names": 0.10,
    "comments": 0.10,
    "formatting": 0.15,
    "logic_modification": 0.10
}


def normalize_weights(weights: dict):
    total = sum(weights.values())
    if total <= 0:
        return {k: 1 / len(weights) for k in weights}
    return {k: v / total for k, v in weights.items()}


# =========================================================
# UTIL SIMILARITY (ADOPSI VERSI DOSEN)
# =========================================================
def numeric_similarity(a, b):
    max_val = max(a, b)
    return 1.0 if max_val == 0 else 1 - abs(a - b) / max_val


def comment_similarity(t1, t2):
    if not t1 and not t2:
        return 1.0
    return difflib.SequenceMatcher(None, t1, t2).ratio()


# =========================================================
# EKSTRAKSI KOMENTAR (# dan docstring)
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
def get_ast_features(code):
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
# CORE ENGINE SIMILARITY (BLOK / FILE)
# =========================================================
def block_similarity(code1, code2, weights=None):
    if weights is None:
        weights = DEFAULT_AST_WEIGHTS

    weights = normalize_weights(weights)

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
def extract_code_blocks(code):
    blocks = []
    try:
        tree = ast.parse(code)
        lines = code.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.For, ast.While, ast.If)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    block = "\n".join(lines[node.lineno - 1: node.end_lineno])
                    blocks.append((type(node).__name__, block))
    except:
        pass
    return blocks


# =========================================================
# SIMILARITY ANTAR BLOK (UNTUK UI DJANGO)
# =========================================================
def find_similar_blocks(code1, code2, threshold=0.65, weights=None):
    if weights is None:
        weights = DEFAULT_AST_WEIGHTS

    blocks1 = extract_code_blocks(code1)
    blocks2 = extract_code_blocks(code2)

    results = []
    for t1, b1 in blocks1:
        for t2, b2 in blocks2:
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
# FILE I/O
# =========================================================
def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return None


# =========================================================
# ANALISIS FOLDER (PENGGANTI compare_all_files)
# =========================================================
def run_analysis(folder_path, output_path, ast_weights=None, threshold=0.65):
    if ast_weights is None:
        ast_weights = DEFAULT_AST_WEIGHTS

    files = [f for f in os.listdir(folder_path) if f.endswith(".py")]
    paths = [os.path.join(folder_path, f) for f in files]

    import pandas as pd
    df = pd.DataFrame(index=files, columns=files, data=0.0)
    similar_blocks = []

    for i in range(len(paths)):
        for j in range(i, len(paths)):
            c1 = read_file(paths[i])
            c2 = read_file(paths[j])
            if not c1 or not c2:
                continue

            sim = block_similarity(c1, c2, ast_weights)
            df.iloc[i, j] = sim
            df.iloc[j, i] = sim

            blocks = find_similar_blocks(c1, c2, threshold, ast_weights)
            if blocks:
                similar_blocks.append({
                    "file1": files[i],
                    "file2": files[j],
                    "similar_blocks": blocks
                })

    os.makedirs(output_path, exist_ok=True)

    # CSV
    csv_path = os.path.join(output_path, "hasil_similaritas.csv")
    df.to_csv(csv_path)

    # TXT
    txt_path = os.path.join(output_path, "blok_kode_mirip.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for entry in similar_blocks:
            f.write(f"{entry['file1']} vs {entry['file2']}\n")
            for b in entry["similar_blocks"]:
                f.write(f"  {b['type']} | {b['score']:.2f}\n")
            f.write("-" * 40 + "\n")

    # EXCEL
    xlsx_path = os.path.join(output_path, "blok_kode_mirip.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["File A", "File B", "Jenis", "Similarity", "Kode A", "Kode B"])
    for entry in similar_blocks:
        for b in entry["similar_blocks"]:
            ws.append([
                entry["file1"],
                entry["file2"],
                b["type"],
                b["score"],
                b["snippet_a"],
                b["snippet_b"],
            ])
    wb.save(xlsx_path)

    return df, {
        "csv": csv_path,
        "txt": txt_path,
        "xlsx": xlsx_path,
        "png": None,
    }
