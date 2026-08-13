from pathlib import Path

import pymupdf

from backend.app.services.application_extractor import (
    extract_applications,
)
from backend.app.analyzers.friction_analyzer import (
    analyze_applications,
    get_high_priority_applications,
)


PDF_PATH = Path(
    "data/documents/_08122026-415.pdf"
)


def read_pdf(path: Path) -> str:

    if not path.exists():
        raise FileNotFoundError(
            f"PDF not found: {path}"
        )

    document = pymupdf.open(path)

    try:
        return "\n".join(
            page.get_text("text")
            for page in document
        )
    finally:
        document.close()


def main():

    print("=" * 90)
    print("PERMITSIGNAL FRICTION ANALYZER")
    print("=" * 90)

    print()
    print("[1/4] Reading government packet...")

    text = read_pdf(PDF_PATH)

    print(
        f"PDF: {PDF_PATH}"
    )

    print(
        f"Characters: {len(text):,}"
    )

    print()
    print(
        "[2/4] Extracting current applications..."
    )

    applications = extract_applications(
        text
    )

    print(
        f"Current applications: "
        f"{len(applications)}"
    )

    print()
    print(
        "[3/4] ANALYZING HISTORICAL EVIDENCE..."
    )

    analyzed = analyze_applications(
        text,
        applications,
    )

    for application in analyzed:

        print()
        print("=" * 90)

        print(
            f"ITEM:              "
            f"{application.get('item')}"
        )

        print(
            f"APPLICANT:         "
            f"{application.get('applicant_name')}"
        )

        print(
            f"APPLICATION #:     "
            f"{application.get('application_number')}"
        )

        print(
            f"TYPE:              "
            f"{application.get('application_type')}"
        )

        print(
            f"ADDRESS:           "
            f"{application.get('project_address')}"
        )

        print(
            f"FRICTION SCORE:    "
            f"{application.get('friction_score')}"
        )

        signals = application.get(
            "friction_signals",
            [],
        )

        print(
            f"SIGNALS:           "
            f"{', '.join(signals) if signals else 'NONE'}"
        )

        events = application.get(
            "friction_events",
            [],
        )

        if not events:

            print()
            print(
                "EVIDENCE:"
            )
            print(
                "No relevant friction evidence detected."
            )

            continue

        print()
        print(
            f"EVIDENCE EVENTS:   {len(events)}"
        )

        for index, event in enumerate(
            events,
            start=1,
        ):

            print()
            print(
                f"[EVENT {index}]"
            )

            print(
                f"TYPE:       "
                f"{event.get('event_type')}"
            )

            print(
                f"DATE:       "
                f"{event.get('event_date') or 'Unknown'}"
            )

            print(
                f"SEVERITY:   "
                f"{event.get('severity')}"
            )

            print(
                f"CONFIDENCE: "
                f"{event.get('confidence')}"
            )

            print(
                f"RELEVANCE:  "
                f"{event.get('relevance')}"
            )

            print(
                f"PAGE:       "
                f"{event.get('source_page') or 'Unknown'}"
            )

            print(
                "EVIDENCE:"
            )

            print(
                event.get(
                    "evidence",
                    "",
                )
            )

    print()
    print(
        "[4/4] PRIORITY SUMMARY"
    )

    high_priority = (
        get_high_priority_applications(
            analyzed,
            minimum_score=40,
        )
    )

    print()
    print(
        f"High-priority applications: "
        f"{len(high_priority)}"
    )

    for application in high_priority:

        print()
        print(
            f"{application.get('application_number')} | "
            f"{application.get('applicant_name')} | "
            f"SCORE: "
            f"{application.get('friction_score')}"
        )

        print(
            f"Address: "
            f"{application.get('project_address')}"
        )

        print(
            "Signals: "
            + ", ".join(
                application.get(
                    "friction_signals",
                    [],
                )
            )
        )

    print()
    print("=" * 90)
    print(
        "FRICTION ANALYSIS COMPLETE"
    )
    print("=" * 90)


if __name__ == "__main__":
    main()