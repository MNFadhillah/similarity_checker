# 🔍 AST-Based Python Code Similarity Detector

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Aplikasi ini merupakan sistem **pendeteksi kemiripan kode program Python berbasis Abstract Syntax Tree (AST)** yang dirancang untuk membantu proses **evaluasi pembelajaran pemrograman**, khususnya dalam mendeteksi plagiarisme atau kemiripan struktur kode.

---

## Tujuan Pengembangan
- Membantu dosen/guru dalam **mendeteksi kemiripan kode program mahasiswa/siswa**  
- Mengurangi kecurangan dalam pengumpulan tugas pemrograman  
- Memberikan **visualisasi hasil kemiripan** dalam bentuk skor dan heatmap  
- Mendukung **penelitian pada bidang pendidikan dan analisis kode program**

---

## Fitur Utama
- Upload banyak file Python sekaligus
- Analisis kemiripan berbasis **struktur AST**
- Perbandingan antar file secara otomatis
- Skor similaritas dalam bentuk persentase
- Visualisasi *heatmap* kemiripan
- Ekspor hasil dalam bentuk **gambar & CSV**
- Tampilan berbasis web (Django)

---

## Metode yang Digunakan
- **Abstract Syntax Tree (AST) Analysis**
- Pembobotan struktur sintaks:
  - Fungsi
  - Percabangan
  - Perulangan
  - Operasi aritmatika
- Perhitungan tingkat kemiripan berbasis **struktur dan alur program**, bukan hanya teks

---

## Teknologi yang Digunakan
- **Python**
- **Django (Web Framework)**
- **Matplotlib** – visualisasi heatmap
- **Pandas** – pengolahan data hasil perbandingan
- **HTML, CSS, JavaScript** – antarmuka pengguna

---

## Cara Instalasi

### 1. Clone Repository

git clone https://github.com/username/nama-repo.git
cd nama-repo

pip install -r requirements.txt

python manage.py runserver
