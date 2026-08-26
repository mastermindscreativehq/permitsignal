from __future__ import annotations

"""
HTML Playwright adapter — for government sources that publish agenda
pages as HTML with links to PDF documents.

This generalizes the existing Provo AgendaCenter scraping logic into a
configuration-driven adapter.  The ``config`` dict on the source record
specifies:
- ``categories``: list of agenda page URLs to scrape
- ``rss_url``: optional RSS feed URL for incremental discovery
- ``link_patterns``: URL substrings that identify valid document links
- ``base_url``: the site root for resolving relative links
- ``link_type_map``: mapping from URL patterns to record_type labels
"""

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx

from backend.app.services.source_adapters.base import BaseAdapter, DocumentRecord


class HtmlPlaywrightAdapter(BaseAdapter):
    """Adapter for HTML agenda pages with linked PDFs."""

    def discover(
        self,
        source_config: dict[str, Any],
    ) -> list[DocumentRecord]:
        config = source_config.get("config", {})
        source_key = source_config.get("source_key", "")
        base_url = config.get("base_url", _infer_base_url(source_config.get("source_url", "")))
        categories = config.get("categories", [])
        link_patterns = config.get("link_patterns", ["/Agenda/", "/ViewFile/", "/Minutes/"])
        link_type_map = config.get("link_type_map", {})
        rss_url = config.get("rss_url")

        records: dict[str, DocumentRecord] = {}

        for category_url in categories:
            page_records = self._scrape_category(
                category_url, source_key, base_url, link_patterns, link_type_map
            )
            for r in page_records:
                records[r.url] = r

        if rss_url:
            rss_records = self._parse_rss(
                rss_url, source_key, base_url, link_patterns, link_type_map
            )
            for r in rss_records:
                if r.url not in records:
                    records[r.url] = r

        return list(records.values())

    def download(
        self,
        record: DocumentRecord,
        source_config: dict[str, Any],
    ) -> str:
        from backend.app.services import document_downloader
        path = document_downloader.download_document(record.url)
        return str(path)

    def _scrape_category(
        self,
        url: str,
        source_key: str,
        base_url: str,
        link_patterns: list[str],
        link_type_map: dict[str, str],
    ) -> list[DocumentRecord]:
        records: list[DocumentRecord] = []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print(f"[ADAPTER] Playwright not installed — skipping {url}")
            return records

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                if response is None:
                    print(f"[ADAPTER] No response from {url}")
                    return records

                page.wait_for_timeout(1500)
                links = page.locator("a")
                count = links.count()

                for index in range(count):
                    link = links.nth(index)
                    try:
                        title = link.inner_text().strip()
                        href = link.get_attribute("href")
                    except Exception:
                        continue

                    if not href:
                        continue

                    absolute_url = urljoin(base_url, href)

                    if not any(pattern in absolute_url for pattern in link_patterns):
                        continue

                    record_type = self._classify_link(absolute_url, link_type_map)

                    date = _extract_date_from_url(absolute_url)

                    records.append(
                        DocumentRecord(
                            source_key=source_key,
                            url=absolute_url,
                            title=title,
                            document_date=date,
                            record_type=record_type,
                            metadata={"category_url": url},
                        )
                    )
            finally:
                browser.close()

        return records

    def _parse_rss(
        self,
        rss_url: str,
        source_key: str,
        base_url: str,
        link_patterns: list[str],
        link_type_map: dict[str, str],
    ) -> list[DocumentRecord]:
        records: list[DocumentRecord] = []

        try:
            req = httpx.get(
                rss_url,
                headers={"User-Agent": "PermitSignal/2.0"},
                timeout=30,
                follow_redirects=True,
            )
            req.raise_for_status()
        except Exception as exc:
            print(f"[ADAPTER] RSS fetch failed for {rss_url}: {exc}")
            return records

        try:
            root = ElementTree.fromstring(req.text)
        except ElementTree.ParseError as exc:
            print(f"[ADAPTER] RSS parse failed: {exc}")
            return records

        for item in root.findall(".//item"):
            link_el = item.find("link")
            title_el = item.find("title")

            if link_el is None or not link_el.text:
                continue

            url = urljoin(base_url, link_el.text.strip())

            if not any(pattern in url for pattern in link_patterns):
                continue

            record_type = self._classify_link(url, link_type_map)
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            date = _extract_date_from_url(url)

            records.append(
                DocumentRecord(
                    source_key=source_key,
                    url=url,
                    title=title,
                    document_date=date,
                    record_type=record_type,
                    metadata={"source": "rss"},
                )
            )

        return records

    def _classify_link(
        self,
        url: str,
        link_type_map: dict[str, str],
    ) -> str:
        for pattern, record_type in link_type_map.items():
            if pattern in url:
                return record_type

        if "/ViewFile/Agenda/" in url:
            return "agenda"
        if "/ViewFile/Minutes/" in url:
            return "minutes"
        if "/PreviousVersions/" in url:
            return "previous_versions"

        return "unknown"


def _infer_base_url(url: str) -> str:
    """Extract scheme + authority from a URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _extract_date_from_url(url: str) -> str | None:
    """
    Extract MMDDYYYY from common government URL patterns.
    E.g. ``_08122026-415`` → ``2026-08-12``.
    """
    match = re.search(r"_([0-9]{2})([0-9]{2})([0-9]{4})-", url)
    if not match:
        return None
    month, day, year = match.groups()
    return f"{year}-{month}-{day}"
