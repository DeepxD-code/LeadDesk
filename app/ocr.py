"""Text extraction with Tesseract OCR for scans and image-only PDFs."""
import io
import os
import shutil

import pytesseract
from PIL import Image, ImageOps

_win = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if not shutil.which("tesseract") and os.path.exists(_win):
    pytesseract.pytesseract.tesseract_cmd = _win

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def ocr_image(img: Image.Image) -> str:
    img = ImageOps.exif_transpose(img).convert("L")
    if max(img.size) < 1400:  # upscale small photos, Tesseract likes ~300 dpi
        scale = 1400 / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return pytesseract.image_to_string(img, config="--psm 3")


def ocr_pdf(path_or_bytes) -> list[str]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path_or_bytes)
    pages = []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=300 / 72).to_pil()
        pages.append(ocr_image(img))
    return pages


def extract_text(data: bytes, filename: str) -> tuple[str, bool]:
    """Returns (text, ocr_used)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXT:
        return ocr_image(Image.open(io.BytesIO(data))), True
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
        if sum(len(p.strip()) for p in pages) >= 30 * max(1, len(pages)):
            return "\n".join(pages), False
        return "\n".join(ocr_pdf(data)), True
    if ext == ".docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts), False
    if ext in (".txt", ".md", ".csv"):
        return data.decode("utf-8", errors="replace"), False
    return "", False
