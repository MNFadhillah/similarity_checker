import zipfile
from pathlib import Path

def safe_extract(zip_path: Path, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            extracted_path = dest_dir / member.filename
            if not str(extracted_path.resolve()).startswith(str(dest_dir.resolve())):
                raise RuntimeError("Zip mengandung path tidak aman.")
            zf.extract(member, dest_dir)
