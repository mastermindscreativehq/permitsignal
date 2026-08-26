from __future__ import annotations

"""
Source adapter registry — maps adapter names to implementation classes.

To add a new adapter:
1. Create a module in this package that implements BaseAdapter
2. Register it in ADAPTER_REGISTRY below
3. Set the ``adapter`` field on the government_sources row
"""

from backend.app.services.source_adapters.base import BaseAdapter
from backend.app.services.source_adapters.pdf_adapter import PdfAdapter
from backend.app.services.source_adapters.html_adapter import HtmlPlaywrightAdapter

ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "pdf": PdfAdapter,
    "html_playwright": HtmlPlaywrightAdapter,
}


def get_adapter(adapter_name: str) -> BaseAdapter:
    """
    Instantiate and return an adapter by name.

    Raises ValueError if the adapter is not registered.
    """
    cls = ADAPTER_REGISTRY.get(adapter_name)
    if cls is None:
        raise ValueError(
            f"Unknown adapter {adapter_name!r}. "
            f"Available: {sorted(ADAPTER_REGISTRY)}"
        )
    return cls()


__all__ = ["get_adapter", "ADAPTER_REGISTRY", "BaseAdapter"]
