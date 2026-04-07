from pathlib import Path

import pdfplumber
from pypdf import PdfReader


def parse_document_text(file_path: str) -> str:
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        text = _parse_pdf_with_pdfplumber(path)
        if text.strip():
            return text
        return _parse_pdf_with_pypdf(path)
    return path.read_text(encoding="utf-8")


def _parse_pdf_with_pdfplumber(path: Path) -> str:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def _parse_pdf_with_pypdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

