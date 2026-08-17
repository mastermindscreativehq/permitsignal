from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from playwright.sync_api import sync_playwright


BASE_URL = "https://www.provo.gov"

PLANNING_COMMISSION_URL = (
    "https://www.provo.gov/AgendaCenter/Planning-Commission-2"
)

ADMINISTRATIVE_HEARINGS_URL = (
    "https://www.provo.gov/AgendaCenter/"
    "Planning-Commission-Administrative-Heari-5"
)

# Sibling AgendaCenter categories verified from provo.gov/rss.aspx
# CID suffixes match the AgendaCenter page slugs exactly.
ARTS_COUNCIL_URL = (
    "https://www.provo.gov/AgendaCenter/Arts-Council-10"
)

BOARD_OF_ADJUSTMENT_URL = (
    "https://www.provo.gov/AgendaCenter/"
    "Board-of-Adjustment-4"
)

CITY_COUNCIL_MEETINGS_URL = (
    "https://www.provo.gov/AgendaCenter/"
    "City-Council-Meetings-8"
)

LANDMARKS_COMMISSION_URL = (
    "https://www.provo.gov/AgendaCenter/"
    "Landmarks-Commission-3"
)

NEIGHBORHOOD_DISTRICTS_URL = (
    "https://www.provo.gov/AgendaCenter/"
    "Neighborhood-Districts-6"
)

PARKS_AND_RECREATION_URL = (
    "https://www.provo.gov/AgendaCenter/"
    "Parks-and-Recreation-Board-9"
)

# AgendaCenter RSS feed (all categories) verified from
# provo.gov/rss.aspx -> Agenda Center -> All
AGENDACENTER_RSS_URL = (
    "https://www.provo.gov/RSSFeed.aspx"
    "?ModID=65&CID=All-0"
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

                is_minutes = (
                    "/AgendaCenter/ViewFile/Minutes/"
                    in absolute_url
                )

                is_previous_versions = (
                    "/AgendaCenter/PreviousVersions/"
                    in absolute_url
                )

                if not (
                    is_agenda_pdf
                    or is_minutes
                    or is_previous_versions
                ):
                    continue

                # Determine record type.
                if is_agenda_pdf:
                    detected_type = "agenda"

                elif is_minutes:
                    detected_type = "minutes"

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


def collect_rss_records() -> list[GovernmentRecord]:
    """
    Parse the AgendaCenter RSS feed for additional
    government record links across all categories.

    The Provo AgendaCenter RSS feed contains items whose
    <link> URLs point to /AgendaCenter/PreviousVersions/
    and /AgendaCenter/ViewFile/Agenda/ endpoints. These
    are the same authoritative government record links
    the listing pages expose, surfaced via RSS for
    incremental discovery across every board and
    commission.

    Only accepts provo.gov URLs that match the same
    whitelist filter used by collect_page().
    """

    records: list[GovernmentRecord] = []

    try:

        print(
            f"[PROVO] Fetching RSS: "
            f"{AGENDACENTER_RSS_URL}"
        )

        req = Request(
            AGENDACENTER_RSS_URL,
            headers={
                "User-Agent": "PermitSignal/1.0"
            },
        )

        with urlopen(req, timeout=30) as resp:
            xml_bytes = resp.read()

        root = ElementTree.fromstring(xml_bytes)

        items = root.findall(".//item")

        print(
            f"[PROVO] RSS items parsed: "
            f"{len(items)}"
        )

        for item in items:

            title_el = item.find("title")
            link_el = item.find("link")
            pub_date_el = item.find("pubDate")

            if (
                link_el is None
                or not link_el.text
            ):
                continue

            title = (
                title_el.text.strip()
                if title_el is not None
                and title_el.text
                else ""
            )

            url = link_el.text.strip()

            # Only accept authoritative provo.gov URLs.
            if not url.startswith(BASE_URL + "/"):
                continue

            # ------------------------------------------------
            # SAME WHITELIST FILTER AS collect_page()
            # ------------------------------------------------

            is_agenda_pdf = (
                "/AgendaCenter/ViewFile/Agenda/"
                in url
            )

            is_minutes = (
                "/AgendaCenter/ViewFile/Minutes/"
                in url
            )

            is_previous_versions = (
                "/AgendaCenter/PreviousVersions/"
                in url
            )

            if not (
                is_agenda_pdf
                or is_minutes
                or is_previous_versions
            ):
                continue

            if is_agenda_pdf:
                detected_type = "agenda"

            elif is_minutes:
                detected_type = "minutes"

            else:
                detected_type = "previous_versions"

            # Use pubDate as the record date for RSS
            # items since the URL may not contain a
            # date pattern (e.g. /PreviousVersions/415).
            date: Optional[str] = None

            if (
                pub_date_el is not None
                and pub_date_el.text
            ):

                try:
                    dt = datetime.strptime(
                        pub_date_el.text.strip(),
                        "%a, %d %b %Y %H:%M:%S %z",
                    )

                    date = dt.strftime("%Y-%m-%d")

                except ValueError:
                    pass

            records.append(
                GovernmentRecord(
                    source="Provo, Utah",
                    title=title,
                    url=url,
                    date=date,
                    record_type=detected_type,
                )
            )

        print(
            f"[PROVO] RSS records accepted: "
            f"{len(records)}"
        )

    except Exception as exc:

        print(
            f"[PROVO] RSS fetch failed: {exc}"
        )

    return records


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

    # Sibling AgendaCenter categories (verified from
    # provo.gov/rss.aspx)
    arts_records = collect_page(
        ARTS_COUNCIL_URL,
        "arts_council",
    )

    print(
        f"[PROVO] Arts Council records: "
        f"{len(arts_records)}"
    )

    records.extend(arts_records)

    boa_records = collect_page(
        BOARD_OF_ADJUSTMENT_URL,
        "board_of_adjustment",
    )

    print(
        f"[PROVO] Board of Adjustment records: "
        f"{len(boa_records)}"
    )

    records.extend(boa_records)

    council_records = collect_page(
        CITY_COUNCIL_MEETINGS_URL,
        "city_council",
    )

    print(
        f"[PROVO] City Council records: "
        f"{len(council_records)}"
    )

    records.extend(council_records)

    landmarks_records = collect_page(
        LANDMARKS_COMMISSION_URL,
        "landmarks_commission",
    )

    print(
        f"[PROVO] Landmarks Commission records: "
        f"{len(landmarks_records)}"
    )

    records.extend(landmarks_records)

    neighborhood_records = collect_page(
        NEIGHBORHOOD_DISTRICTS_URL,
        "neighborhood_districts",
    )

    print(
        f"[PROVO] Neighborhood Districts records: "
        f"{len(neighborhood_records)}"
    )

    records.extend(neighborhood_records)

    parks_records = collect_page(
        PARKS_AND_RECREATION_URL,
        "parks_and_recreation",
    )

    print(
        f"[PROVO] Parks and Recreation records: "
        f"{len(parks_records)}"
    )

    records.extend(parks_records)

    # AgendaCenter RSS feed (incremental discovery
    # across all categories).
    rss_records = collect_rss_records()

    records.extend(rss_records)

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
