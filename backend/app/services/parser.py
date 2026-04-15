from pathlib import Path

from pypdf import PdfReader


def extract_text_from_txt(file_bytes: bytes) -> tuple[str, list[dict]]:
    text = file_bytes.decode("utf-8", errors="ignore")
    return text, [{"page_number": None, "text": text}]


def extract_text_from_pdf(file_path: str) -> tuple[str, list[dict]]:
    reader = PdfReader(file_path)
    pages = []
    full_text_parts: list[str] = []

    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page_number": idx, "text": text})
        full_text_parts.append(text)

    return "\n\n".join(full_text_parts), pages


def parse_document(file_path: str, filename: str, file_bytes: bytes) -> tuple[str, list[dict], str]:
    suffix = Path(filename).suffix.lower()

    if suffix == ".txt":
        text, pages = extract_text_from_txt(file_bytes)
        return text, pages, "txt"

    if suffix == ".pdf":
        text, pages = extract_text_from_pdf(file_path)
        return text, pages, "pdf"

    raise ValueError("Unsupported file type. Only PDF and TXT files are supported.")