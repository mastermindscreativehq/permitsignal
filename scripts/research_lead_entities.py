"""
Live entity-intelligence research for a single lead.

Runs the bounded public-web research engine against one application in the
leads repository, prints the enriched case intelligence, and persists the
normalized graph to Supabase (requires migration 0008 to be applied).

Usage:
    python -m scripts.research_lead_entities PLRZ20260264
    python -m scripts.research_lead_entities PLRZ20260264 --seed-only
"""
import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application_number")
    parser.add_argument("--seed-only", action="store_true",
                        help="Skip web research; emit government-record seed graph only")
    parser.add_argument("--max-queries", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--no-save", action="store_true",
                        help="Do not write the JSON output file")
    args = parser.parse_args()

    from backend.app.services.lead_repository import fetch_leads
    from backend.app.services.case_research_engine import CaseResearchEngine
    from backend.app.services.entity_repository import (
        is_configured,
        persist_case_intelligence,
    )

    leads = fetch_leads()
    lead = next(
        (l for l in leads
         if str(l.get("application_number")) == args.application_number),
        None,
    )
    if not lead:
        print(f"Lead {args.application_number} not found in database "
              f"({len(leads)} leads available)")
        return 1

    if args.seed_only:
        engine = CaseResearchEngine(
            lead, serpapi_key=None, max_queries=0,
            max_pages=0, max_depth=0,
        )
        record = engine.run()
    else:
        engine = CaseResearchEngine(lead, request_delay=1.0,
                                    max_queries=args.max_queries,
                                    max_pages=args.max_pages)
        record = engine.run()

    rr = record.get("research_run", {})
    stats = record.get("stats", {})
    print()
    print("=" * 78)
    print(f"ENTITY RESEARCH: {args.application_number}")
    print("=" * 78)
    print(f"Product:            {record.get('product')}")
    print(f"Schema:             v{record.get('schema_version')}"
          f" | research_status={rr.get('status')}")
    print(f"Entities:           {len(record.get('entities', []))} "
          f"({stats.get('entity_types')})")
    print(f"Relationships:      {stats.get('relationships_total')}")
    print(f"Evidence records:   {stats.get('evidence_total')} "
          f"(verified={stats.get('verified_claims')}, "
          f"unverified={stats.get('unverified_claims')})")
    print(f"Sources:            {stats.get('sources_total')}")
    print(f"Unresolved:         {len(stats.get('unresolved_entity_keys', []))}")
    print(f"Search queries:     {rr.get('queries_executed')}"
          f"/{rr.get('params', {}).get('max_queries', 0)}"
          f" | pages fetched: {rr.get('pages_fetched')}")
    if rr.get("errors"):
        print(f"Errors:             {len(rr['errors'])}")
        for err in rr["errors"][:5]:
            print(f"  - [{err.get('where')}] {err.get('error')}")

    print()
    print("-" * 78)
    print("ENTITIES")
    print("-" * 78)
    for e in record["entities"]:
        li = e.get("best_linkedin_url") or "-"
        top = e["matches"][0] if e.get("matches") else None
        top_desc = ""
        if top:
            top_desc = (f"{top['match_status']}/{top['match_confidence']}"
                        f" -> {top['candidate_name']}")
        print(f"[{e['entity_type']:<16}] {e['canonical_name']} "
              f"| roles={e.get('case_roles')} "
              f"| status={e.get('research_status')}")
        if e.get("attributes", {}).get("role"):
            print(f"                    role: {e['attributes']['role']}")
        if e.get("attributes", {}).get("email"):
            print(f"                    email: {e['attributes']['email']}")
        if e.get("attributes", {}).get("website"):
            print(f"                    website: {e['attributes']['website']}")
        if li != "-":
            print(f"                    linkedin: {li}")
        if top_desc:
            print(f"                    best match: {top_desc}")

    print()
    print("-" * 78)
    print("RELATIONSHIPS")
    print("-" * 78)
    names = {e["entity_key"]: e["canonical_name"] for e in record["entities"]}
    for r in record["relationships"]:
        s = names.get(r["subject_entity_key"], r["subject_entity_key"])
        o = names.get(r["object_entity_key"], r["object_entity_key"])
        print(f"{s} --{r['predicate']}--> {o} (confidence={r.get('confidence')})")

    if not args.no_save:
        os.makedirs("data/output", exist_ok=True)
        out_path = f"data/output/entity_intelligence_{args.application_number}.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False, default=str)
        print()
        print(f"Saved: {out_path}")

    if is_configured():
        try:
            result = persist_case_intelligence(record)
            print(f"Supabase sync: {result}")
        except RuntimeError as exc:
            print(f"Supabase sync SKIPPED: {exc}")
            print("Apply supabase/migrations/0008_add_entity_intelligence.sql"
                  " via the Supabase SQL editor, then re-run.")
    else:
        print("Supabase not configured; persistence skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
