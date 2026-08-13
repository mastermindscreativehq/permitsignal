from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


BASE_URL = "https://www.provo.gov"

PLANNING_COMMISSION_URL = (
    "https://www.provo.gov/AgendaCenter/Planning-Commission-2"
)

ADMINISTRATIVE_HEARINGS_URL = (
    "https://www.provo.gov/AgendaCenter/"
    "Planning-Commission-Administrative-Heari-5"
)


@dataclass
class GovernmentRecord:
    source: str
    title: str
    url: str
    date: Optional[str] = None
    record_type: Optional[str] = None


def extract_date_from_url(url: str) -> Optional[str]:
    """
    Provo agenda URLs contain dates like:

    _08122026-415

    Convert that to:

    2026-08-12
    """

    import re

    match = re.search(
        r"_([0-9]{2})([0-9]{2})([0-9]{4})-",
        url,
    )

    if not match:
        return None

    month, day, year = match.groups()

    return f"{year}-{month}-{day}"


def collect_page(
    url: str,
    record_type: str,
) -> list[GovernmentRecord]:

    records: list[GovernmentRecord] = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        try:

            print(f"[PROVO] Opening: {url}")

            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            if response is None:
                raise RuntimeError(
                    f"No response from {url}"
                )

            print(
                f"[PROVO] HTTP status: "
                f"{response.status}"
            )

            page.wait_for_timeout(1500)

            links = page.locator("a")

            count = links.count()

            print(
                f"[PROVO] Links discovered: {count}"
            )

            for index in range(count):

                link = links.nth(index)

                try:
                    title = link.inner_text().strip()
                    href = link.get_attribute("href")
                except Exception:
                    continue

                if not href:
                    continue

                absolute_url = urljoin(
                    BASE_URL,
                    href,
                )

                # ------------------------------------------------
                # ONLY KEEP ACTUAL GOVERNMENT RECORD LINKS
                # ------------------------------------------------

                is_agenda_pdf = (
                    "/AgendaCenter/ViewFile/Agenda/"
                    in absolute_url
                )

                is_previous_versions = (
                    "/AgendaCenter/PreviousVersions/"
                    in absolute_url
                )

                if not (
                    is_agenda_pdf
                    or is_previous_versions
                ):
                    continue

                # Determine record type.
                if is_agenda_pdf:
                    detected_type = "agenda"

                else:
                    detected_type = "previous_versions"

                records.append(
                    GovernmentRecord(
                        source="Provo, Utah",
                        title=title,
                        url=absolute_url,
                        date=extract_date_from_url(
                            absolute_url
                        ),
                        record_type=detected_type,
                    )
                )

        finally:

            browser.close()

    # Deduplicate URLs.
    unique: dict[str, GovernmentRecord] = {}

    for record in records:
        unique[record.url] = record

    return list(unique.values())


def collect_provo_records() -> list[GovernmentRecord]:

    print(
        "[PROVO] Starting focused government "
        "record collection..."
    )

    records: list[GovernmentRecord] = []

    # Planning Commission
    planning_records = collect_page(
        PLANNING_COMMISSION_URL,
        "planning_commission",
    )

    print(
        f"[PROVO] Planning Commission records: "
        f"{len(planning_records)}"
    )

    records.extend(planning_records)

    # Administrative Hearings
    hearing_records = collect_page(
        ADMINISTRATIVE_HEARINGS_URL,
        "administrative_hearing",
    )

    print(
        f"[PROVO] Administrative Hearing records: "
        f"{len(hearing_records)}"
    )

    records.extend(hearing_records)

    # Final dedupe.
    unique: dict[str, GovernmentRecord] = {}

    for record in records:
        unique[record.url] = record

    final_records = list(unique.values())

    print(
        f"[PROVO] Total focused records: "
        f"{len(final_records)}"
    )

    return final_records


def collect_provo_records_dict() -> list[dict]:

    records = collect_provo_records()

    return [
        asdict(record)
        for record in records
    ]


if __name__ == "__main__":

    records = collect_provo_records()

    print()
    print("=" * 70)
    print("PROVO GOVERNMENT RECORDS")
    print("=" * 70)

    for record in records:

        print(
            f"{record.record_type:20} "
            f"{record.date or 'NO DATE':12} "
            f"{record.title:20} "
            f"{record.url}"
        )

    print()
    print("=" * 70)
    print(
        f"TOTAL: {len(records)}"
    )
    print("=" * 70)