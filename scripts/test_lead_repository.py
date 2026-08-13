"""
PermitSignal Lead Repository Tests

These tests are entirely deterministic and network-free: is_configured()
is checked with the real environment (SUPABASE_URL/SUPABASE_KEY are not
expected to be set in a test environment), and upsert_leads() is exercised
against a FAKE Supabase client, never a real one.

Run from the project root:

    python -m scripts.test_lead_repository
"""

import os

from backend.app.services.lead_repository import (
    DEFAULT_TABLE,
    get_table_name,
    is_configured,
    lead_to_row,
    upsert_leads,
)


def check(condition, label):
    if condition:
        print(f"[PASS] {label}")
        return True

    print(f"[FAIL] {label}")
    return False


class FakeQuery:
    def __init__(self, calls, table, rows):
        self.calls = calls
        self.table = table
        self.rows = rows

    def upsert(self, rows, on_conflict=None):
        self.calls.append(
            {
                "table": self.table,
                "rows": rows,
                "on_conflict": on_conflict,
            }
        )
        return self

    def execute(self):
        return {"data": self.rows}


class FakeSupabaseClient:
    def __init__(self):
        self.calls = []

    def table(self, name):
        return FakeQuery(self.calls, name, [])


def main():
    print("=" * 80)
    print("PERMITSIGNAL LEAD REPOSITORY")
    print("=" * 80)

    results = []

    # ------------------------------------------------------------------
    print("\n[1/6] Configuration detection")

    original_url = os.environ.pop("SUPABASE_URL", None)
    original_key = os.environ.pop("SUPABASE_KEY", None)

    try:
        results.append(
            check(
                is_configured() is False,
                "Reports not configured when SUPABASE_URL/KEY are absent",
            )
        )

        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_KEY"] = "test-key"

        results.append(
            check(
                is_configured() is True,
                "Reports configured once SUPABASE_URL and SUPABASE_KEY are set",
            )
        )

        results.append(
            check(
                get_table_name() == DEFAULT_TABLE,
                "Defaults to the 'leads' table",
            )
        )

        os.environ["SUPABASE_LEADS_TABLE"] = "custom_leads"

        results.append(
            check(
                get_table_name() == "custom_leads",
                "Honors SUPABASE_LEADS_TABLE override",
            )
        )
    finally:
        os.environ.pop("SUPABASE_LEADS_TABLE", None)
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_KEY", None)

        if original_url is not None:
            os.environ["SUPABASE_URL"] = original_url

        if original_key is not None:
            os.environ["SUPABASE_KEY"] = original_key

    # ------------------------------------------------------------------
    print("\n[2/6] Lead-to-row mapping")

    lead = {
        "application_number": "PLRZ20260264",
        "applicant_name": "Jared Morgan",
        "normalized_applicant_name": "Jared Morgan",
        "company_name": None,
        "applicant_email": None,
        "applicant_phone": None,
        "contact_email": None,
        "friction_score": 100,
        "friction_signals": ["denied", "recommended_denial"],
        "priority": "HIGH",
        "priority_score": 180,
        "lead_status": "NO_CONTACT",
        "is_contactable": False,
        "next_project_date": "2026-08-12",
        "next_project_event": "public_hearing",
        "next_project_time": "6:00 PM",
        "has_future_opportunity": True,
        "staff_contact_name": "Megan Van De Graaff",
        "staff_contact_email": "mvandegraaff@provo.gov",
    }

    row = lead_to_row(lead)

    results.append(
        check(
            row["application_number"] == "PLRZ20260264",
            "Row carries the business key",
        )
    )
    results.append(
        check(
            row["applicant_email"] is None,
            "Row never fabricates a missing applicant email",
        )
    )
    results.append(
        check(
            row["friction_signals"] == ["denied", "recommended_denial"],
            "Row preserves friction signals",
        )
    )
    results.append(
        check(
            row["lead_status"] == "NO_CONTACT" and row["is_contactable"] is False,
            "Row preserves lead qualification fields",
        )
    )
    results.append(
        check(
            row["staff_contact_email"] == "mvandegraaff@provo.gov"
            and row["staff_contact_email"] != row["applicant_email"],
            "Row keeps staff contact separate from applicant contact",
        )
    )
    results.append(
        check(
            row["record"] == lead,
            "Row preserves the full lead record verbatim in the JSONB column",
        )
    )
    results.append(
        check(
            "updated_at" in row and row["updated_at"],
            "Row stamps updated_at",
        )
    )

    # A field NOT in the promoted column list must still survive via record.
    lead_with_extra = dict(lead)
    lead_with_extra["some_future_field"] = "not yet a column"

    row_with_extra = lead_to_row(lead_with_extra)

    results.append(
        check(
            row_with_extra["record"]["some_future_field"] == "not yet a column",
            "Fields not promoted to a column are still preserved in record",
        )
    )

    # ------------------------------------------------------------------
    print("\n[3/6] Friction signals persistence edge case")

    # An application with genuinely no friction evidence: Opportunity's
    # own friction_signals field(default_factory=list) already treats
    # this as [], matching the "leads" table's
    # "jsonb not null default '[]'::jsonb" column -- this must map
    # cleanly, not be confused with a database integrity risk.
    lead_empty_signals = dict(lead)
    lead_empty_signals["friction_signals"] = []

    row_empty_signals = lead_to_row(lead_empty_signals)

    results.append(
        check(
            row_empty_signals["friction_signals"] == [],
            "A lead with friction_signals=[] maps to [] in the row",
        )
    )
    results.append(
        check(
            row_empty_signals["record"]["friction_signals"] == [],
            "The [] representation is preserved in the full record JSONB",
        )
    )

    # The actual bug: a lead dict where friction_signals is explicitly
    # None (or the key is absent, which .get() also returns as None).
    # Sending an explicit SQL null violates the NOT NULL constraint on
    # the leads table's friction_signals column -- a Postgres column
    # default only applies when the column is omitted from the payload,
    # not when it is explicitly null.
    lead_none_signals = dict(lead)
    lead_none_signals["friction_signals"] = None

    row_none_signals = lead_to_row(lead_none_signals)

    results.append(
        check(
            row_none_signals["friction_signals"] == [],
            "A lead with friction_signals=None maps to [] in the row "
            "column, avoiding a NOT NULL constraint violation",
        )
    )
    results.append(
        check(
            row_none_signals["friction_signals"] is not None,
            "The friction_signals column is never sent as an explicit SQL null",
        )
    )

    lead_missing_signals = {
        key: value for key, value in lead.items() if key != "friction_signals"
    }

    row_missing_signals = lead_to_row(lead_missing_signals)

    results.append(
        check(
            row_missing_signals["friction_signals"] == [],
            "A lead with no friction_signals key at all still maps to []",
        )
    )

    # The coercion must be scoped to the promoted column only -- the raw
    # value (even None) is preserved untouched in the full record JSONB,
    # so no evidence is silently rewritten.
    results.append(
        check(
            row_none_signals["record"]["friction_signals"] is None,
            "The true original value (None) is preserved unaltered in "
            "the full record JSONB, even though the column is coerced",
        )
    )

    # Real friction signals must remain completely unaffected by this fix.
    results.append(
        check(
            lead_to_row(lead)["friction_signals"]
            == ["denied", "recommended_denial"],
            "Real friction signals are still preserved exactly",
        )
    )

    # ------------------------------------------------------------------
    print("\n[4/6] Upsert against a fake Supabase client (no network)")

    fake_client = FakeSupabaseClient()

    result = upsert_leads(
        [lead],
        client=fake_client,
        table="leads",
    )

    results.append(
        check(result["status"] == "synced" and result["rows"] == 1, "Reports a successful sync")
    )
    results.append(
        check(len(fake_client.calls) == 1, "Calls the client exactly once")
    )
    results.append(
        check(
            fake_client.calls[0]["table"] == "leads",
            "Targets the configured table",
        )
    )
    results.append(
        check(
            fake_client.calls[0]["on_conflict"] == "application_number",
            "Upserts on the application_number business key",
        )
    )

    # ------------------------------------------------------------------
    print("\n[5/6] No fabrication: leads without application_number are skipped")

    fake_client_2 = FakeSupabaseClient()

    incomplete_lead = {"applicant_name": "No Application Number"}

    result_2 = upsert_leads(
        [lead, incomplete_lead],
        client=fake_client_2,
        table="leads",
    )

    results.append(
        check(
            result_2["rows"] == 1 and result_2.get("skipped") == 1,
            "Skips a lead with no application_number instead of inventing one",
        )
    )

    result_3 = upsert_leads([incomplete_lead], client=FakeSupabaseClient())

    results.append(
        check(
            result_3["status"] == "skipped" and result_3["rows"] == 0,
            "Reports skipped when nothing has an application_number",
        )
    )

    result_4 = upsert_leads([], client=FakeSupabaseClient())

    results.append(
        check(
            result_4["status"] == "skipped" and result_4["reason"] == "no_leads",
            "Reports skipped for an empty lead list",
        )
    )

    # ------------------------------------------------------------------
    print("\n[6/6] get_client() fails loudly without configuration")

    from backend.app.services.lead_repository import get_client

    original_url = os.environ.pop("SUPABASE_URL", None)
    original_key = os.environ.pop("SUPABASE_KEY", None)

    raised = False

    try:
        get_client()
    except RuntimeError:
        raised = True
    finally:
        if original_url is not None:
            os.environ["SUPABASE_URL"] = original_url

        if original_key is not None:
            os.environ["SUPABASE_KEY"] = original_key

    results.append(
        check(raised, "get_client() raises a clear RuntimeError when not configured")
    )

    print("\n" + "=" * 80)

    passed = sum(results)
    failed = len(results) - passed

    print(f"TESTS: {passed} passed, {failed} failed")
    print("=" * 80)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
