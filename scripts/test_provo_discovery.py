"""
PermitSignal live Provo discovery tests.

These hit the real Provo government site over the network (the same
target already used by backend.app.collectors.provo and
scripts/test_playwright.py) -- there is no mock Provo site to test
against, and discovery logic that only works against a fake page proves
nothing about the real one.

Run from project root:

    python -m scripts.test_provo_discovery
"""

from pathlib import Path

from backend.app.collectors.provo import collect_provo_records, extract_date_from_url
from backend.app.services import discovery_orchestrator, document_registry


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True
    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 80)
    print("PERMITSIGNAL LIVE PROVO DISCOVERY")
    print("=" * 80)

    results = []

    test_registry_path = Path("data/state/_test_provo_discovery_registry.json")
    if test_registry_path.exists():
        test_registry_path.unlink()

    try:
        print("\n[1/3] Raw collector against the real Provo site")

        records = collect_provo_records()

        results.append(
            check(
                len(records) > 0,
                f"Discovers at least one government record ({len(records)} found)",
            )
        )

        agenda_records = [r for r in records if r.record_type == "agenda"]

        results.append(
            check(
                len(agenda_records) > 0,
                f"Discovers at least one agenda packet ({len(agenda_records)} found)",
            )
        )

        dated = [
            r
            for r in agenda_records
            if r.date and extract_date_from_url(r.url) == r.date
        ]

        results.append(
            check(
                len(dated) > 0,
                "At least one agenda record has a normalized YYYY-MM-DD date",
            )
        )

        print("\n[2/3] First discovery pass registers every record")

        first_pass = discovery_orchestrator.discover_and_ingest_provo(
            dry_run=True,
            registry_path=test_registry_path,
        )

        results.append(
            check(
                first_pass["discovered_total"] == len(records),
                "Reports the same total the raw collector found",
            )
        )
        results.append(
            check(
                first_pass["new_total"] > 0,
                "First run against an empty registry finds new records",
            )
        )
        results.append(
            check(first_pass["dry_run"] is True, "Reports dry_run status")
        )
        results.append(
            check(
                first_pass["ingested"] == [],
                "Dry run does not download or run the pipeline",
            )
        )

        registry_after_first = document_registry.load_registry(test_registry_path)
        results.append(
            check(
                len(registry_after_first) == len(records),
                "Registry persists one entry per discovered record",
            )
        )

        print("\n[3/3] Second discovery pass is idempotent")

        second_pass = discovery_orchestrator.discover_and_ingest_provo(
            dry_run=True,
            registry_path=test_registry_path,
        )

        # The live site's exact link count can fluctuate slightly between
        # requests (dynamic page content), so this does not assert an
        # exact discovered_total match -- only the actual idempotency
        # invariant: nothing already registered is ever re-registered as
        # new, and no previously known entry is lost.
        results.append(
            check(
                second_pass["new_total"] == 0,
                "Re-running discovery finds no new records",
            )
        )

        registry_after_second = document_registry.load_registry(test_registry_path)
        results.append(
            check(
                set(registry_after_first) <= set(registry_after_second),
                "Every previously registered document is still registered",
            )
        )

        passed = sum(results)
        failed = len(results) - passed

        print("\n" + "=" * 80)
        print(f"TESTS: {passed} passed, {failed} failed")
        print("=" * 80)

        if failed:
            raise SystemExit(1)

    finally:
        if test_registry_path.exists():
            test_registry_path.unlink()


if __name__ == "__main__":
    main()
