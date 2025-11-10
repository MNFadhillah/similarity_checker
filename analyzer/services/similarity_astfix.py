import ast
import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from openpyxl import Workbook

"""pembobotan indikator AST dari 0.00 - 1.00"""
AST_WEIGHTS = {
    "structure": 0.18,  # struktur sintaksis
    "execution_order": 0.12,  # urutan eksekusi
    "hierarchy": 0.10,  # hierarki blok kode
    "variable_names": 0.20,  # perubahan nama variabel/fungsi
    "comments": 0.20,  # komentar
    "formatting": 0.10,  # indentasi/spasi
    "logic_modification": 0.10  # modifikasi logika
}


def read_file(file_path):
    """Membaca isi file Python."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print(f"File {file_path} tidak ditemukan.")
        return None


def get_ast_features(code):
    """Mengekstrak fitur AST untuk tiap indikator."""
    try:
        tree = ast.parse(code)
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        loops = [node for node in ast.walk(tree) if isinstance(node, (ast.For, ast.While))]
        conditionals = [node for node in ast.walk(tree) if isinstance(node, ast.If)]
        assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]

        return {
            "structure": len(functions) + len(loops) + len(conditionals),
            "execution_order": sum(1 for _ in ast.walk(tree)),
            "hierarchy": sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.body),
            "variable_names": len({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}),
            "comments": code.count("#"),
            "formatting": code.count(" ") + code.count("\t"),
            "logic_modification": len(assignments)
        }
    except SyntaxError as e:
        print(f"Syntax Error di {code[:50]}...: {e}")
        return None


def extract_code_blocks(code):
    """Ekstrak blok fungsi, loop, dan if dari kode Python."""
    try:
        tree = ast.parse(code)
        blocks = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.For, ast.While, ast.If)):
                start_lineno = getattr(node, "lineno", None)
                end_lineno = getattr(node, "end_lineno", None)
                if start_lineno and end_lineno:
                    lines = code.splitlines()[start_lineno - 1:end_lineno]
                    block_code = "\n".join(lines)
                    blocks.append((type(node).__name__, block_code.strip()))
        return blocks
    except Exception as e:
        print(f"Error parsing code blocks: {e}")
        return []


def find_similar_blocks(code1, code2, threshold=0.85):
    """Membandingkan blok kode dan menampilkan yang mirip."""
    blocks1 = extract_code_blocks(code1)
    blocks2 = extract_code_blocks(code2)
    similar_blocks = []

    for type1, block1 in blocks1:
        for type2, block2 in blocks2:
            if type1 != type2:
                continue
            features1 = get_ast_features(block1)
            features2 = get_ast_features(block2)
            if not features1 or not features2:
                continue
            sim = sum(
                (1 - abs(features1[k] - features2[k]) / (max(features1[k], features2[k]) or 1))
                * AST_WEIGHTS[k] for k in AST_WEIGHTS
            )
            if sim >= threshold:
                similar_blocks.append((type1, sim, block1[:50] + "...", block2[:50] + "..."))

    return similar_blocks


def compute_similarity(file1, file2):
    """Membandingkan dua file Python berdasarkan fitur AST dengan bobot."""
    code1 = read_file(file1)
    code2 = read_file(file2)

    if not code1 or not code2:
        return 0.0

    features1 = get_ast_features(code1)
    features2 = get_ast_features(code2)

    if not features1 or not features2:
        return 0.0

    similarity_scores = {}

    for key in AST_WEIGHTS.keys():
        max_value = max(features1[key], features2[key]) or 1
        similarity_scores[key] = 1 - abs(features1[key] - features2[key]) / max_value

    weighted_similarity = sum(
        similarity_scores[key] * AST_WEIGHTS[key] for key in AST_WEIGHTS.keys()
    )

    return weighted_similarity


def save_similar_blocks_txt(similar_blocks_data, folder_path):
    """Menyimpan hasil blok mirip ke file .txt."""
    txt_path = os.path.join(folder_path, "blok_kode_mirip.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for entry in similar_blocks_data:
            f.write(f"File A: {entry['file1']} | File B: {entry['file2']}\n")
            for block in entry["similar_blocks"]:
                f.write(f"  - Jenis: {block[0]}, Similarity: {block[1]:.2f}\n")
                f.write(f"    ↪ Potongan kode A: {block[2]}\n")
                f.write(f"    ↪ Potongan kode B: {block[3]}\n\n")
            f.write("-" * 50 + "\n")
    print(f"File teks similaritas blok kode disimpan di: {txt_path}")


def save_similar_blocks_excel(similar_blocks_data, folder_path):
    """Menyimpan hasil blok mirip ke file Excel."""
    excel_path = os.path.join(folder_path, "blok_kode_mirip.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Blok Mirip"
    ws.append(["File A", "File B", "Jenis Blok", "Similarity", "Potongan Kode A", "Potongan Kode B"])

    for entry in similar_blocks_data:
        for block in entry["similar_blocks"]:
            ws.append([
                entry["file1"],
                entry["file2"],
                block[0],
                f"{block[1]:.2f}",
                block[2],
                block[3]
            ])

    wb.save(excel_path)
    print(f"File Excel disimpan di: {excel_path}")


def compare_all_files(folder_path):
    """Membandingkan semua file Python dalam folder (tanpa GUI)."""
    if not folder_path or not os.path.exists(folder_path):
        print("Folder tidak ditemukan.")
        return

    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith(".py")]
    if len(files) < 2:
        print("Tidak cukup file Python untuk dibandingkan (minimal 2 file).")
        return

    file_names = [os.path.basename(f) for f in files]
    similarity_matrix = pd.DataFrame(index=file_names, columns=file_names, data=0.0)
    similar_blocks_all = []

    for i in range(len(files)):
        for j in range(i, len(files)):
            similarity = compute_similarity(files[i], files[j])
            similarity_matrix.iloc[i, j] = similarity
            similarity_matrix.iloc[j, i] = similarity

            code1 = read_file(files[i])
            code2 = read_file(files[j])
            similar_parts = find_similar_blocks(code1, code2)
            if similar_parts:
                similar_blocks_all.append({
                    "file1": os.path.basename(files[i]),
                    "file2": os.path.basename(files[j]),
                    "similar_blocks": similar_parts
                })

    result_path = os.path.join(folder_path, "hasil_similaritas.csv")
    similarity_matrix.to_csv(result_path)
    save_similar_blocks_txt(similar_blocks_all, folder_path)
    save_similar_blocks_excel(similar_blocks_all, folder_path)

    plt.figure(figsize=(10, 8))
    sns.heatmap(similarity_matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
    plt.title("Heatmap Similaritas Kode Mahasiswa")
    plt.xticks(rotation=90)
    plt.yticks(rotation=0)
    plt.tight_layout()
    heatmap_path = os.path.join(folder_path, "heatmap_similaritas.png")
    plt.savefig(heatmap_path)
    plt.close()

    print(f"Hasil disimpan di: {result_path}")


# Hindari pemanggilan otomatis GUI saat diimpor Django
if __name__ == "__main__":
    folder = input("Masukkan path folder berisi file Python: ").strip()
    compare_all_files(folder)
