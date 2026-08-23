"""
Step 7: batch validation of Action Intelligence packages (contract v1.0)
against the real production output.

Validates every lead in data/output/permitsignal_opportunities.json:

1. PRESENCE      -- every opportunity carries an action_intelligence package.
2. VOCABULARY    -- all types/stages/categories/severities/confidences are
                    members of the frozen contract vocabularies.
3. EVIDENCE      -- every populated evidence_quote is a verbatim substring
                    of one of the lead's own text blocks (no fabrication).
4. ID SEQUENCES  -- C001.. / B001.. / A001.. assigned in order.
5. DETERMINISM   -- recomputing the package from the stored lead with the
                    recorded reference date reproduces the stored package
                    byte-for-byte.

Run: python -m scripts.test_action_batch
"""
import json
import sys
from pathlib import Path

from backend.app.services.approval_stage_intelligence import (
    ACTION_CATEGORIES,
    BLOCKER_TYPES,
    CONTRACT_VERSION,
    DECISION_STAGES,
    REQUESTED_ACTION_TYPES,
    _iter_lead_text_blocks,
    build_conditions,
    build_decision_stage,
    build_requested_action,
    map_blockers_and_actions,
)

OUTPUT_PATH = Path("data/output/permitsignal_opportunities.json")

CONFIDENCE_BANDS = {"HIGH", "MEDIUM", "LOW", "NONE"}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

failures: list[str] = []


def fail(lead_number: str, label: str, detail: str = "") -> None:
    failures.append(f"{lead_number}: {label}" + (f" | {detail}" if detail else ""))


def _check_ids(ids: list[str], prefix: str) -> bool:
    return ids == [f"{prefix}{i:03d}" for i in range(1, len(ids) + 1)]


def main() -> int:
    if not OUTPUT_PATH.exists():
        print(f"MISSING OUTPUT: {OUTPUT_PATH}")
        return 1

    data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    opportunities = data.get("opportunities") or []
    reference_date = (data.get("metadata") or {}).get("reference_date")
    if not opportunities or not reference_date:
        print("INVALID OUTPUT SHAPE: opportunities/metadata.reference_date")
        return 1

    print("=" * 78)
    print(f"BATCH VALIDATION: {len(opportunities)} opportunities | "
          f"reference_date={reference_date} | contract v{CONTRACT_VERSION}")
    print("=" * 78)

    packaged = 0
    for lead in opportunities:
        number = str(lead.get("application_number") or "<unnamed>")
        package = lead.get("action_intelligence")
        if not isinstance(package, dict):
            fail(number, "missing action_intelligence package")
            continue
        if package.get("status") == "error":
            fail(number, "package is an error stub", package.get("error", ""))
            continue
        packaged += 1

        if package.get("contract_version") != CONTRACT_VERSION:
            fail(number, "contract_version mismatch",
                 str(package.get("contract_version")))

        corpus_blocks = [b["text"] for b in _iter_lead_text_blocks(lead)]
        corpus = "\n".join(corpus_blocks)

        def quote_ok(q) -> bool:
            return q is None or (isinstance(q, str)
                                 and (q == "" or q in corpus))

        # -- vocabulary ---------------------------------------------------
        ra = package.get("requested_action") or {}
        if ra.get("action_type") not in REQUESTED_ACTION_TYPES:
            fail(number, "requested_action.action_type out of vocabulary",
                 str(ra.get("action_type")))
        if ra.get("confidence") not in CONFIDENCE_BANDS:
            fail(number, "requested_action.confidence out of bands",
                 str(ra.get("confidence")))
        if not quote_ok(ra.get("evidence_quote")):
            fail(number, "requested_action.evidence_quote not verbatim")

        ds = package.get("decision_stage") or {}
        if ds.get("decision_stage") not in DECISION_STAGES:
            fail(number, "decision_stage out of vocabulary",
                 str(ds.get("decision_stage")))
        if ds.get("confidence") not in CONFIDENCE_BANDS:
            fail(number, "decision_stage.confidence out of bands")
        if not quote_ok(ds.get("evidence_quote")):
            fail(number, "decision_stage.evidence_quote not verbatim")

        ba = package.get("blockers_and_actions") or {}
        blockers = ba.get("blockers") or []
        actions = ba.get("actions") or []

        if not _check_ids([c.get("condition_id") for c in
                           package.get("conditions") or []], "C"):
            fail(number, "condition ids not sequential C001..")
        if not _check_ids([b.get("blocker_id") for b in blockers], "B"):
            fail(number, "blocker ids not sequential B001..")
        if not _check_ids([a.get("action_id") for a in actions], "A"):
            fail(number, "action ids not sequential A001..")

        for cond in package.get("conditions") or []:
            if cond.get("confidence") not in CONFIDENCE_BANDS:
                fail(number, "condition confidence out of bands",
                     str(cond.get("condition_id")))
            if not quote_ok(cond.get("evidence_quote")):
                fail(number, "condition quote not verbatim",
                     str(cond.get("condition_id")))

        for blocker in blockers:
            if blocker.get("blocker_type") not in BLOCKER_TYPES:
                fail(number, "blocker_type out of vocabulary",
                     str(blocker.get("blocker_type")))
            if blocker.get("severity") not in SEVERITIES:
                fail(number, "blocker severity out of bands",
                     str(blocker.get("blocker_id")))
            if blocker.get("confidence") not in CONFIDENCE_BANDS:
                fail(number, "blocker confidence out of bands",
                     str(blocker.get("blocker_id")))
            if not quote_ok(blocker.get("evidence_quote")):
                fail(number, "blocker quote not verbatim",
                     str(blocker.get("blocker_id")))

        for action in actions:
            if action.get("category") not in ACTION_CATEGORIES:
                fail(number, "action category out of vocabulary",
                     str(action.get("category")))
            if action.get("confidence") not in CONFIDENCE_BANDS:
                fail(number, "action confidence out of bands",
                     str(action.get("action_id")))

        # -- determinism ----------------------------------------------------
        recomputed = {
            "contract_version": CONTRACT_VERSION,
            "requested_action": build_requested_action(lead),
            "conditions": build_conditions(lead),
            "decision_stage": build_decision_stage(
                lead, reference_date=reference_date),
            "blockers_and_actions": map_blockers_and_actions(
                lead, reference_date=reference_date),
        }
        if json.dumps(recomputed, sort_keys=True) != \
                json.dumps(package, sort_keys=True):
            fail(number, "stored package differs from recomputation")

    print()
    print(f"{'APP #':<16} {'STAGE':<26} {'REQ':<22} {'C':>3} {'B':>3} "
          f"{'A':>3}")
    print("-" * 78)
    for lead in opportunities:
        number = str(lead.get("application_number") or "<unnamed>")
        package = lead.get("action_intelligence") or {}
        stage = (package.get("decision_stage") or {}).get(
            "decision_stage", "-")
        req = (package.get("requested_action") or {}).get("action_type", "-")
        ba = package.get("blockers_and_actions") or {}
        print(f"{number:<16} {stage:<26} {str(req):<22} "
              f"{len(package.get('conditions') or []):>3} "
              f"{len(ba.get('blockers') or []):>3} "
              f"{len(ba.get('actions') or []):>3}")

    print("=" * 78)
    if failures:
        print(f"BATCH VALIDATION FAILED: {len(failures)} violation(s)")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"BATCH VALIDATION PASSED: {packaged}/{len(opportunities)} "
          f"packages conform to contract v{CONTRACT_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
