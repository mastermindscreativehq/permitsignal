from __future__ import annotations

"""
Base adapter interface for government source discovery and download.

Every source adapter implements two methods:

- ``discover()`` — find new document URLs from the source
- ``download()`` — fetch a document to a local file path

The downstream pipeline (application extraction, enrichment, etc.) is
adapter-agnostic: it receives either a file path or raw text.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DocumentRecord:
    """
    Canonical representation of a discovered government document,
    regardless of which adapter found it.
    """
    source_key: str
    url: str
    title: str = ""
    document_date: Optional[str] = None
    record_type: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAdapter(ABC):
    """
    Abstract base class for source adapters.

    Subclasses must implement ``discover()`` and ``download()``.
    """

    @abstractmethod
    def discover(
        self,
        source_config: dict[str, Any],
    ) -> list[DocumentRecord]:
        """
        Discover document URLs from a government source.

        Parameters
        ----------
        source_config : dict
            The government_sources row for this source, including
            source_key, source_url, adapter, config, etc.

        Returns
        -------
        list[DocumentRecord]
            Discovered documents.  The ingestion orchestrator handles
            deduplication against the document_registry.
        """
        ...

    @abstractmethod
    def download(
        self,
        record: DocumentRecord,
        source_config: dict[str, Any],
    ) -> str:
        """
        Download a document to a local file path.

        Parameters
        ----------
        record : DocumentRecord
            The document to download.
        source_config : dict
            The government_sources row.

        Returns
        -------
        str
            Local file path to the downloaded document.
        """
        ...

    def is_ingestible(self, record: DocumentRecord) -> bool:
        """
        Whether this record should be auto-ingested through the pipeline.
        Override for source-type-specific filtering.
        """
        return record.record_type in ("agenda", "pdf_direct", "minutes")
