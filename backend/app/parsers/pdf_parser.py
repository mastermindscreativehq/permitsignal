from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass
class ParsedDocument:
    page_count: int
    text: str
    pages: list[dict]


def parse_pdf(pdf_path: str | Path) -> ParsedDocument:
    """
    Extract text from a government PDF using PyMuPDF.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    document = fitz.open(pdf_path)

    pages = []
    full_text_parts = []

    try:
        for page_number, page in enumerate(document, start=1):

            text = page.get_text("text").strip()

            pages.append(
                {
                    "page": page_number,
                    "text": text,
                }
            )

            if text:
                full_text_parts.append(
                    f"\n--- PAGE {page_number} ---\n"
                )

                full_text_parts.append(text)

        full_text = "\n".join(full_text_parts)

        return ParsedDocument(
            page_count=len(document),
            text=full_text,
            pages=pages,
        )

    finally:
        document.close()