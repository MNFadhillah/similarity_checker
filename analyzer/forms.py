from django import forms

class UploadZipForm(forms.Form):
    zip_file = forms.FileField(
        label="Upload .zip berisi file .py",
        widget=forms.ClearableFileInput(attrs={'accept': '.zip'})
    )
