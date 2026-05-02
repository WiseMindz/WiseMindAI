from pathlib import Path
from typing import Optional

from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".tif"}
TEXT_EXTENSIONS = {".txt", ".csv", ".json", ".md", ".log", ".ini"}


def sanitize_filename(filename: str) -> str:
    sanitized = "".join(c for c in filename if c.isalnum() or c in "._- ")
    sanitized = sanitized.strip().replace(" ", "_")
    if not sanitized:
        sanitized = "upload"
    return sanitized


def is_image_file(filename: str, mime_type: Optional[str] = None) -> bool:
    ext = Path(filename).suffix.lower()
    if mime_type and mime_type.startswith("image/"):
        return True
    return ext in IMAGE_EXTENSIONS


def is_text_file(filename: str, mime_type: Optional[str] = None) -> bool:
    ext = Path(filename).suffix.lower()
    if mime_type and mime_type.startswith("text/"):
        return True
    return ext in TEXT_EXTENSIONS


async def download_telegram_file(file, filename: str) -> Path:
    path = UPLOAD_DIR / sanitize_filename(filename)
    await file.download_to_drive(custom_path=str(path))
    return path


def extract_text_from_image(image_path: Path) -> str:
    if pytesseract is None:
        return ""

    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang="eng")
        return text.strip()
    except (pytesseract.TesseractNotFoundError, Exception):
        return ""


def extract_text_from_document(file_path: Path) -> str:
    if file_path.suffix.lower() in TEXT_EXTENSIONS:
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return ""
    return ""
