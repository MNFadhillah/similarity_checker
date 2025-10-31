import ast
import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
# import tkinter as tk
import re
# from tkinter import filedialog
from openpyxl import Workbook

"""pembobotan indikator AST dari 0.00 - 1.00 (bobot aspek yang dideteksi, jika bobot adalah 0.00 = diabaikan/tidak mempengaruhi nilai kemiripan)"""
AST_WEIGHTS = {
    "structure": 0.18,          # struktur Sintaksis
    "execution_order": 0.12,    # urutan Eksekusi
    "hierarchy": 0.10,          # hierarki Blok Kode
    "variable_names": 0.20,     # perubahan Nama Variabel/Fungsi 0.2
    "comments": 0.20,           # komentar
    "formatting": 0.10,         # indentasi, Spasi
    "logic_modification": 0.10  # modifikasi Logika
}

METRIC_KEYS = tuple(AST_WEIGHTS.keys())


def _empty_metrics(err_msg=None):
    m = {k: 0 for k in METRIC_KEYS}
    if err_msg:
        m["_error"] = err_msg
    return m


def read_file(file_path):
    """membaca isi file python."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print(f"File {file_path} tidak ditemukan.")
        return None


def lint_indentation(code: str, max_tabs_per_indent: int = 1):
    """
    Kembalikan daftar isu indentasi:
    - line_multi_tabs: baris dengan indent berisi >= max_tabs_per_indent+1 tab
    - line_mixed: baris yang mencampur tab dan spasi pada indentasi
    - line_bad_width: (opsional) indent width tidak multiple-of-4 setelah expandtabs(8)
    """
    line_multi_tabs = []
    line_mixed = []
    line_bad_width = []

    for lineno, raw in enumerate(code.splitlines(), 1):
        if not raw.strip():
            continue
        m = re.match(r'^([ \t]+)', raw)  # leading whitespace
        if not m:
            continue
        indent = m.group(1)

        # >= 2 tab pada indentasi
        if indent.count('\t') > max_tabs_per_indent:
            line_multi_tabs.append(lineno)

        # campur tab dan spasi
        if '\t' in indent and ' ' in indent:
            line_mixed.append(lineno)

        # opsional: cek lebar indent (PEP8 rekom 4 spasi)
        width = len(indent.expandtabs(8))  # Python menganggap tab = ke kolom kelipatan 8
        if width % 4 != 0:
            line_bad_width.append(lineno)

    return {
        "multi_tabs": line_multi_tabs,
        "mixed": line_mixed,
        "bad_width": line_bad_width,
    }


def normalize_indentation_to_spaces(code: str, spaces_per_tab: int = 4):
    """
    Normalisasi indentasi: UBAH hanya whitespace di awal baris.
    Mengonversi tab pada AWAL baris menjadi spasi (4 default).
    """
    out_lines = []
    for raw in code.splitlines():
        m = re.match(r'^([ \t]+)', raw)
        if not m:
            out_lines.append(raw)
            continue
        indent = m.group(1)
        rest = raw[len(indent):]
        # ganti setiap TAB di indent menjadi sejumlah spasi
        fixed_indent = indent.replace('\t', ' ' * spaces_per_tab)
        out_lines.append(fixed_indent + rest)
    return '\n'.join(out_lines)


def get_ast_features(code):
    """mengekstrak fitur AST untuk tiap indikator."""
    issues = lint_indentation(code, max_tabs_per_indent=1)
    if issues["multi_tabs"] or issues["mixed"]:
        code = normalize_indentation_to_spaces(code, spaces_per_tab=4)
    try:
        tree = ast.parse(code)
    except (SyntaxError, IndentationError, TabError) as e:
        return _empty_metrics(f"{type(e).__name__}: {e}")

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


def extract_code_blocks(code):
    """ekstrak blok fungsi, loop, dan if dari kode python."""
    try:
        tree = ast.parse(code)
        blocks = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.For, ast.While, ast.If)):
                start_lineno = getattr(node, 'lineno', None)
                end_lineno = getattr(node, 'end_lineno', None)  # rekomen python 3.8+
                if start_lineno and end_lineno:
                    lines = code.splitlines()[start_lineno - 1:end_lineno]
                    block_code = "\n".join(lines)
                    blocks.append((type(node).__name__, block_code.strip()))
        return blocks
    except Exception as e:
        print(f"Error parsing code blocks: {e}")
        return []


def find_similar_blocks(code1, code2, threshold=0.70):  # menetapkan treshold kemiripan
    """membandingkan blok kode dan menampilkan yang mirip"""
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
                (1 - abs(features1[k] - features2[k]) / (max(features1[k], features2[k]) or 1)) * AST_WEIGHTS[k]
                for k in AST_WEIGHTS
            )
            if sim >= threshold:
                similar_blocks.append((type1, sim, block1[:50] + "...", block2[:50] + "..."))

    return similar_blocks


def compute_similarity(file1, file2):
    """membandingkan dua file python berdasarkan fitur AST dengan bobot."""
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
        max_value = max(features1[key], features2[key]) or 1  # hindari pembagian dengan nol
        similarity_scores[key] = 1 - abs(features1[key] - features2[key]) / max_value

    weighted_similarity = sum(similarity_scores[key] * AST_WEIGHTS[key] for key in AST_WEIGHTS.keys())

    similar_parts = find_similar_blocks(code1, code2)
    if similar_parts:
        print(f"\nSimilaritas Blok kode antara {os.path.basename(file1)} dan {os.path.basename(file2)}:")
        for block_type, sim, blk1, blk2 in similar_parts:
            print(f" - Jenis: {block_type}, Similarity: {sim:.2f}")
            print(f"   ↪ Potongan kode A : {blk1}")
            print(f"   ↪ Potongan kode B: {blk2}\n")

    return weighted_similarity


# def save_similar_blocks_txt(similar_blocks_data, folder_path):
#     txt_path = os.path.join(folder_path, "blok_kode_mirip.txt")  # menyimpan hasil deteksi blok-blok kode yang mirip dalam format .txt
#     with open(txt_path, "w", encoding="utf-8") as f:
#         for entry in similar_blocks_data:
#             f.write(f"File A: {entry['file1']} | File B: {entry['file2']}\n")
#             for block in entry['similar_blocks']:
#                 f.write(f"  - Jenis: {block[0]}, Similarity: {block[1]:.2f}\n")
#                 f.write(f"    ↪ Potongan kode A: {block[2]}\n")
#                 f.write(f"    ↪ Potongan kode B: {block[3]}\n\n")
#             f.write("-" * 50 + "\n")
#     print(f"\nFile teks similaritas blok kode disimpan di: {txt_path}")

# def save_similar_blocks_excel(similar_blocks_data, folder_path):
#     excel_path = os.path.join(folder_path, "blok_kode_mirip.xlsx")  # menyimpan hasil deteksi blok-blok kode yang mirip dalam format .xlsx
#     wb = Workbook()
#     ws = wb.active
#     ws.title = "Blok Mirip"
#     ws.append(["File A", "File B", "Jenis Blok", "Similarity", "Potongan Kode A", "Potongan Kode B"])
#     for entry in similar_blocks_data:
#         for block in entry['similar_blocks']:
#             ws.append([
#                 entry['file1'],
#                 entry['file2'],
#                 block[0],
#                 f"{block[1]:.2f}",
#                 block[2],
#                 block[3]
#             ])
#     wb.save(excel_path)
#     print(f"File Excel similaritas blok kode disimpan di: {excel_path}")


# def compare_all_files():
#     """menampilkan dialog pemilihan folder dan membandingkan semua file python di dalamnya."""
#     root = tk.Tk()
#     root.withdraw()

#     folder_path = filedialog.askdirectory(title="Pilih Folder Berisi Kode Mahasiswa (Kode Uji)")
#     if not folder_path:
#         print("Pemilihan folder dibatalkan.")
#         return

#     print(f"\nFolder yang dipilih: {folder_path}")

#     files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.py')]

#     if len(files) < 2:
#         print("Tidak cukup file Python untuk dibandingkan (minimal 2 file).")
#         return

#     file_names = [os.path.basename(f) for f in files]
#     similarity_matrix = pd.DataFrame(index=file_names, columns=file_names, data=0.0)

#     similar_blocks_all = []

#     for i in range(len(files)):
#         for j in range(i, len(files)):
#             similarity = compute_similarity(files[i], files[j])
#             similarity_matrix.iloc[i, j] = similarity
#             similarity_matrix.iloc[j, i] = similarity

#             # menyimpan blok mirip jika ada
#             code1 = read_file(files[i])
#             code2 = read_file(files[j])
#             similar_parts = find_similar_blocks(code1, code2)
#             if similar_parts:
#                 similar_blocks_all.append({
#                     "file1": os.path.basename(files[i]),
#                     "file2": os.path.basename(files[j]),
#                     "similar_blocks": similar_parts
#                 })

#     # result_path = os.path.join(folder_path, "hasil_similaritas.csv")
#     # similarity_matrix.to_csv(result_path)

#     # menyimpan blok kode yg mirip ke file .txt dan .xlsx
#     # save_similar_blocks_txt(similar_blocks_all, folder_path)
#     # save_similar_blocks_excel(similar_blocks_all, folder_path)

#     # visualisasi heatmap
#     plt.figure(figsize=(10, 8))
#     sns.heatmap(similarity_matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
#     plt.title("Heatmap Similaritas Kode Mahasiswa")
#     plt.xticks(rotation=90)
#     plt.yticks(rotation=0)
#     plt.tight_layout()
#     heatmap_path = os.path.join(folder_path, "heatmap_similaritas.png")
#     plt.savefig(heatmap_path)
#     plt.show()

#     print(similarity_matrix)
#     # print(f"\nHasil disimpan di: {result_path}")


# # menjalankan program
# compare_all_files()

def run_similarity_analysis(folder_path):
    """
    Versi non-GUI dari compare_all_files().
    Dipanggil dari Django untuk menjalankan analisis folder.
    """
    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.py')]
    if len(files) < 2:
        raise ValueError("Minimal harus ada 2 file Python untuk dibandingkan.")

    file_names = [os.path.basename(f) for f in files]
    similarity_matrix = pd.DataFrame(index=file_names, columns=file_names, data=0.0)

    for i in range(len(files)):
        for j in range(i, len(files)):
            similarity = compute_similarity(files[i], files[j])
            similarity_matrix.iloc[i, j] = similarity
            similarity_matrix.iloc[j, i] = similarity

    # Simpan heatmap
    plt.figure(figsize=(10, 8))
    sns.heatmap(similarity_matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
    plt.title("Heatmap Similaritas Kode Mahasiswa")
    plt.xticks(rotation=90)
    plt.yticks(rotation=0)
    plt.tight_layout()
    heatmap_path = os.path.join(folder_path, "heatmap_similaritas.png")
    plt.savefig(heatmap_path)
    plt.close()

    return heatmap_path, similarity_matrix

