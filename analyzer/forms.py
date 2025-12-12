from django import forms

class UploadZipForm(forms.Form):
    # Input utama: file ZIP
    zip_file = forms.FileField(
        label="Berkas .zip berisi file .py"
    )

    # Bobot indikator AST (0–1)
    structure_weight = forms.FloatField(
        label="Struktur sintaksis",
        min_value=0, max_value=1, initial=0.18
    )
    execution_order_weight = forms.FloatField(
        label="Urutan eksekusi",
        min_value=0, max_value=1, initial=0.12
    )
    hierarchy_weight = forms.FloatField(
        label="Hierarki blok kode",
        min_value=0, max_value=1, initial=0.10
    )
    variable_names_weight = forms.FloatField(
        label="Nama variabel/fungsi",
        min_value=0, max_value=1, initial=0.20
    )
    comments_weight = forms.FloatField(
        label="Komentar",
        min_value=0, max_value=1, initial=0.20
    )
    formatting_weight = forms.FloatField(
        label="Format (indentasi/spasi)",
        min_value=0, max_value=1, initial=0.10
    )
    logic_modification_weight = forms.FloatField(
        label="Modifikasi logika",
        min_value=0, max_value=1, initial=0.10
    )
    threshold = forms.FloatField(
        min_value=0.0,
        max_value=1.0,
        initial=0.75,
        label="Threshold Kemiripan (0,0 - 1,0)"
    )

