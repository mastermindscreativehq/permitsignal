"""
PermitSignal document discovery registry tests.

Run from project root:

    python -m scripts.test_document_registry
"""

from pathlib import Path

from backend.app.services import document_registry


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True
    print(f"[FAIL] {label}")
    return False


def main():
    print("=" * 80)
    print("PERMITSIGNAL DOCUMENT REGISTRY")
    print("=" * 80)

    results = []

    test_path = Path("data/state/_test_document_registry.json")
    if test_path.exists():
        test_path.unlink()

    try:
        print("\n[1/4] Empty registry")

        registry = document_registry.load_registry(test_path)
        results.append(
            check(registry == {}, "Missing file loads as empty registry")
        )

        print("\n[2/4] Discovery registration")

        record = {
            "source": "Provo, Utah",
            "title": "Planning Commission Agenda",
            "url": "https://www.provo.gov/AgendaCenter/ViewFile/Agenda/_08122026-415",
            "date": "2026-08-12",
            "record_type": "agenda",
        }

        entry = document_registry.record_discovered(registry, record)
        results.append(
            check(entry["status"] == "discovered", "New record registers as discovered")
        )
        results.append(
            check(
                document_registry.is_known(record["url"], registry),
                "Registered URL is known",
            )
        )

        print("\n[3/4] Filtering and persistence")

        new_records = document_registry.filter_new_records([record], registry)
        results.append(
            check(new_records == [], "Already-known record is filtered out")
        )

        second_record = {**record, "url": record["url"] + "-2"}
        new_records = document_registry.filter_new_records(
            [record, second_record], registry
        )
        results.append(
            check(new_records == [second_record], "Only the unseen record is returned")
        )

        document_registry.save_registry(registry, test_path)
        reloaded = document_registry.load_registry(test_path)
        results.append(
            check(record["url"] in reloaded, "Registry persists across save/load")
        )

        print("\n[4/4] Processing outcomes")

        document_registry.record_processed(
            registry,
            record["url"],
            status="ingested",
            applications=8,
        )
        results.append(
            check(
                registry[record["url"]]["status"] == "ingested",
                "Marks a document ingested",
            )
        )
        results.append(
            check(
                registry[record["url"]]["applications"] == 8,
                "Carries ingestion metadata",
            )
        )
        results.append(
            check(
                registry[record["url"]]["processed_at"] is not None,
                "Records a processed_at timestamp",
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
        if test_path.exists():
            test_path.unlink()


if __name__ == "__main__":
    main()
