# src/pdf_utils.py
from pypdf import PdfReader


def extract_text_from_pdf(file_path: str) -> str:
    """Return all the text in a PDF. Scanned (image-only) PDFs give back an empty string."""
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
