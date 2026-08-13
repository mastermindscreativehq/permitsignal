from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx


DOCUMENT_DIR = Path("data/documents")

DOCUMENT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def filename_from_url(url: str) -> str:
    """
    Convert a government document URL into a safe filename.
    """

    parsed = urlparse(url)

    filename = Path(
        parsed.path
    ).name

    if not filename:
        filename = "government_document.pdf"

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    return filename


def download_document(url: str) -> Path:
    """
    Download a public government document.
    """

    filename = filename_from_url(url)

    destination = DOCUMENT_DIR / filename

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0 Safari/537.36"
        )
    }

    with httpx.Client(
        follow_redirects=True,
        timeout=60.0,
        headers=headers,
    ) as client:

        response = client.get(url)

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "content-type",
                "",
            ).lower()
        )

        if (
            "pdf" not in content_type
            and not response.content.startswith(b"%PDF")
        ):
            raise RuntimeError(
                "Downloaded content does not appear "
                "to be a PDF."
            )

        destination.write_bytes(
            response.content
        )

    return destination


def save_uploaded_document(filename: Optional[str], content: bytes) -> Path:
    """
    Persist an uploaded government document (raw PDF bytes, e.g. from an
    n8n multipart file upload) to DOCUMENT_DIR -- the same location
    download_document() uses for URL-fetched packets -- so the rest of the
    pipeline treats both ingestion paths identically.
    """

    safe_name = Path(filename).name if filename else ""

    if not safe_name:
        safe_name = "government_document.pdf"

    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"

    if not content.startswith(b"%PDF"):
        raise RuntimeError(
            "Uploaded content does not appear "
            "to be a PDF."
        )

    destination = DOCUMENT_DIR / safe_name

    destination.write_bytes(content)

    return destination