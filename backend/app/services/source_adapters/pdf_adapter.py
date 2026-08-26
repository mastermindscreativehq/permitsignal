from __future__ import annotations

"""
PDF direct adapter — for government sources that publish standalone PDF URLs.

Discovery: the source_url itself points to a PDF (or an index page
with direct PDF links).  This adapter handles single-PDF sources and
RSS/CSV index pages that list PDFs.

Download: uses the existing document_downloader.download_document().
"""

import re
from typing import Any
from urllib.parse import urljoin

from backend.app.services.source_adapters.base import BaseAdapter, DocumentRecord
from backend.app.services import document_downloader


class PdfAdapter(BaseAdapter):
    """Adapter for direct PDF sources."""

    def discover(
        self,
        source_config: dict[str, Any],
    ) -> list[DocumentRecord]:
        source_url = source_config.get("source_url", "")
        source_key = source_config.get("source_key", "")
        config = source_config.get("config", {})

        records: list[DocumentRecord] = []

        if _is_pdf_url(source_url):
            records.append(
                DocumentRecord(
                    source_key=source_key,
                    url=source_url,
                    title=source_config.get("agency", source_key),
                    record_type="pdf_direct",
                )
            )

        pdf_links = config.get("pdf_links", [])
        for link in pdf_links:
            url = link.get("url", "") if isinstance(link, dict) else str(link)
            title = link.get("title", "") if isinstance(link, dict) else ""
            date = link.get("date") if isinstance(link, dict) else None
            if url:
                records.append(
                    DocumentRecord(
                        source_key=source_key,
                        url=urljoin(source_url, url),
                        title=title,
                        document_date=date,
                        record_type="pdf_direct",
                    )
                )

        return records

    def download(
        self,
        record: DocumentRecord,
        source_config: dict[str, Any],
    ) -> str:
        path = document_downloader.download_document(record.url)
        return str(path)

    def is_ingestible(self, record: DocumentRecord) -> bool:
        return record.record_type in ("pdf_direct", "agenda")


def _is_pdf_url(url: str) -> bool:
    return url.lower().endswith(".pdf")
