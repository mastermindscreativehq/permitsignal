from __future__ import annotations

from pathlib import Path
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