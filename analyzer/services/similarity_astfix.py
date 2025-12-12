import ast
import os
from openpyxl import Workbook

# ===============================
# Bobot indikator AST (default)
# ===============================
AST_WEIGHTS = {
    "structure": 0.18,
    "execution_order": 0.12,
    "hierarchy": 0.10,
    "variable_names": 0.20,
    "comments": 0.20,
    "formatting": 0.10,
    "logic_modification": 0.10
}


def get_default_ast_weights():
    return AST_WEIGHTS.copy()


# ===============================
# Util dasar
# ===============================
def read_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def get_ast_features(code):
    try:
        tree = ast.parse(code)

        return {
            "structure": sum(isinstance(n, (ast.FunctionDef, ast.For, ast.While, ast.If)) for n in ast.walk(tree)),
            "execution_order": sum(1 for _ in ast.walk(tree)),
            "hierarchy": sum(isinstance(n, ast.FunctionDef) and bool(n.body) for n in ast.walk(tree)),
            "variable_names": len({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}),
            "comments": code.count("#"),
            "formatting": code.count(" ") + code.count("\t"),
            "logic_modification": sum(isinstance(n, ast.Assign) for n in ast.walk(tree)),
        }
    except Exception:
        return None


def extract_code_blocks(code):
    try:
        tree = ast.parse(code)
        blocks = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.For, ast.While, ast.If)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    lines = code.splitlines()[node.lineno - 1: node.end_lineno]
                    blocks.append((type(node).__name__, "\n".join(lines)))

        return blocks
    except Exception:
        return []


# ===============================
# Similarity antar BLOK (TIDAK FILTER)
# ===============================
def find_similar_blocks(code1, code2, threshold=0.7, ast_weights=None):
    if ast_weights is None:
        ast_weights = AST_WEIGHTS.copy()

    # normalisasi bobot
    total = sum(ast_weights.values())
    if total <= 0:
        ast_weights = {k: 1 / len(ast_weights) for k in ast_weights}
    else:
        ast_weights = {k: v / total for k, v in ast_weights.items()}

    threshold = max(0.0, min(1.0, float(threshold)))

    blocks1 = extract_code_blocks(code1)
    blocks2 = extract_code_blocks(code2)

    results = []
    eps = 1e-9

    for type1, block1 in blocks1:
        for type2, block2 in blocks2:
            if type1 != type2:
                continue

            f1 = get_ast_features(block1)
            f2 = get_ast_features(block2)
            if not f1 or not f2:
                continue

            weighted_sum = 0.0
            for k in ast_weights:
                a = float(f1.get(k, 0.0))
                b = float(f2.get(k, 0.0))
                denom = max(abs(a), abs(b), eps)
                weighted_sum += (1 - abs(a - b) / denom) * ast_weights[k]

            sim = float(weighted_sum)

            # threshold HANYA UNTUK LEVEL
            if sim >= threshold:
                level = "Tinggi"
            elif sim >= threshold * 0.5:
                level = "Sedang"
            else:
                level = "Rendah"

            results.append({
                "type": type1,
                "score": sim,
                "level": level,
                "snippet_a": block1[:120],
                "snippet_b": block2[:120],
            })

    return results


# ===============================
# Similarity antar FILE (CSV / matrix)
# ===============================
def compute_similarity(file1, file2, ast_weights=None):
    if ast_weights is None:
        ast_weights = AST_WEIGHTS

    code1 = read_file(file1)
    code2 = read_file(file2)
    if not code1 or not code2:
        return 0.0

    f1 = get_ast_features(code1)
    f2 = get_ast_features(code2)
    if not f1 or not f2:
        return 0.0

    total = sum(ast_weights.values())
    if total <= 0:
        ast_weights = {k: 1 / len(ast_weights) for k in ast_weights}
    else:
        ast_weights = {k: v / total for k, v in ast_weights.items()}

    sim = 0.0
    for k in ast_weights:
        a = f1.get(k, 0.0)
        b = f2.get(k, 0.0)
        denom = max(a, b, 1)
        sim += (1 - abs(a - b) / denom) * ast_weights[k]

    return float(sim)


# ===============================
# SAVE TXT
# ===============================
def save_similar_blocks_txt(similar_blocks_data, folder_path):
    path = os.path.join(folder_path, "blok_kode_mirip.txt")

    with open(path, "w", encoding="utf-8") as f:
        for entry in similar_blocks_data:
            f.write(f"File A: {entry['file1']} | File B: {entry['file2']}\n")

            for block in entry["similar_blocks"]:
                f.write(
                    f"  - {block['type']} | "
                    f"Score: {block['score']:.2f} | "
                    f"Tingkat: {block['level']}\n"
                )
                f.write(f"    A: {block['snippet_a']}\n")
                f.write(f"    B: {block['snippet_b']}\n\n")

            f.write("-" * 60 + "\n")


# ===============================
# SAVE EXCEL
# ===============================
def save_similar_blocks_excel(similar_blocks_data, folder_path):
    path = os.path.join(folder_path, "blok_kode_mirip.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Blok Mirip"

    ws.append([
        "File A", "File B",
        "Jenis Blok", "Score", "Tingkat",
        "Potongan A", "Potongan B"
    ])

    for entry in similar_blocks_data:
        for block in entry["similar_blocks"]:
            ws.append([
                entry["file1"],
                entry["file2"],
                block["type"],
                round(block["score"], 3),
                block["level"],
                block["snippet_a"],
                block["snippet_b"],
            ])

    wb.save(path)
