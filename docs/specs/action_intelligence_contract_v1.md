# Approval & Action Intelligence — Output Contract v1.0

Product: PROVO ADMINISTRATIVE SERVICES FINANCE
Status: FROZEN SPEC (Step 1 of execution plan) — implementation pending
Scope exclusions: NO prior-cycle linkage (v1). No API/dashboard/PDF/report/
schema/entity-layer changes. Storage: `leads.record["action_intelligence"]`
(namespaced key inside the canonical verbatim-preserved JSONB payload).

---

## 1. Top-level output contract

Attached to each lead as `record["action_intelligence"]`:

```json
{
  "schema_version": "1.0",
  "product": "PROVO ADMINISTRATIVE SERVICES FINANCE",
  "generated_at": "<ISO-8601 UTC>",
  "application_number": "PLRZ20260264",

  "requested_action": {
    "action_type": "<REQUESTED-ACTION-TYPE>",
    "from_state": "<string|null>",
    "to_state": "<string|null>",
    "scope": {
      "units": "<int|null>",
      "use_mix": ["<string>"],
      "notes": "<string|null>"
    },
    "evidence_quote": "<string|null>",
    "source_url": "<string|null>",
    "confidence": "<HIGH|MEDIUM|LOW|NONE>"
  },

  "decision_stage": {
    "stage": "<DECISION-STAGE>",
    "confidence_band": "<HIGH|MEDIUM|LOW|NONE>",
    "basis": "<one-line reason citing which inputs decided the stage>",
    "evidence_ids": ["A001", "..."]
  },

  "conditions": [
    {
      "condition_id": "C001",
      "statement": "<normalized condition text>",
      "condition_type": "<CONDITION-TYPE>",
      "evidence_quote": "<verbatim quote|null>",
      "source_url": "<string|null>",
      "event_date": "<YYYY-MM-DD|null>",
      "subject_hint": "<who/what must satisfy it|null>",
      "confidence": "<HIGH|MEDIUM|LOW>"
    }
  ],

  "blockers": [
    {
      "blocker_id": "B001",
      "statement": "<blocker text>",
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "source": "<engine_blocker|derived>",
      "rationale": "<string>",
      "related_condition_ids": ["C001"],
      "resolution_hint": "<string|null>"
    }
  ],

  "next_action": {
    "action_id": "N001",
    "action": "<imperative one-liner>",
    "action_category": "<ACTION-CATEGORY>",
    "deadline": "<YYYY-MM-DD|null>",
    "deadline_basis": "<event_date|statutory_window|null>",
    "rationale": "<string>",
    "priority_rank": 1,
    "evidence_ids": ["E0001"]
  },
  "action_alternatives": [ /* same shape as next_action, rank >= 2 */ ],

  "inputs_consumed": {
    "approval_flat_fields": true,
    "engine_package": true,
    "friction_event_count": 2,
    "project_date_count": 5,
    "entity_reference_count": 0
  },

  "unresolved": ["<explicit gap statements>"],
  "warnings": ["<degradation / ambiguity notes>"]
}
```

## 2. Vocabularies (frozen)

### DECISION-STAGE
Canonical lifecycle of the CURRENT application only (no cross-cycle joins):

| Value | Meaning |
|---|---|
| `pre_submission` | Not yet filed / pre-app phase |
| `under_staff_review` | Filed; staff analysis in progress |
| `scheduled_public_hearing` | A dated public hearing/meeting exists ahead |
| `in_hearing_process` | Continued / deferred / tabled pending items |
| `approved_pending_conditions` | Approved subject to unmet conditions |
| `approved` | Final approval, no outstanding conditions |
| `denied_appeal_window` | Denied and an appeal path may still exist |
| `denied_current_application` | Denied on this application |
| `withdrawn` | Withdrawn by applicant |
| `unknown` | Insufficient evidence (never guess) |

Precedence when multiple signals apply:
government-record event dates > friction/status signals > engine decision_path
> description inference. `unknown` + warning is correct behavior.

### CONDITION-TYPE

| Value | Meaning |
|---|---|
| `staff_recommendation_condition` | Condition recommended by staff for approval |
| `code_standard_condition` | Compliance item tied to a cited code standard |
| `neighborhood_commitment` | Commitment extracted from neighborhood feedback context |
| `procedural_condition` | Filing/notice/attendance procedure requirements |
| `prior_decision_requirement` | Requirement stated by a decision on THIS application |

### REQUESTED-ACTION-TYPE
Mirrors the application-type vocabulary already produced by the extractor:

`Zone Map Amendment`, `Concept Plan`, `Variance`, `Ordinance Text Amendment`,
`Project Plan`, `Conditional Use`, `General Plan Amendment`, `Subdivision`,
`Other`, `Unknown`

`from_state` / `to_state` carry zoning or plan designations when quoted
(e.g., CG -> MU); otherwise null.

### BLOCKER severity
Reuses the deep-engine scale: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
Blockers sourced from `approval_intelligence.approval_blockers` keep their
original severity; derived blockers declare `"source": "derived"`.

### ACTION-CATEGORY

| Value | Maps to |
|---|---|
| `hearing_preparation` | Prepare for a scheduled hearing |
| `appeal_filing` | Appeal window actions |
| `resubmission_prep` | New-cycle submission preparation |
| `condition_resolution` | Satisfy an extracted condition |
| `documentation_prep` | Assemble required materials |
| `stakeholder_engagement` | Address staff/neighborhood objections |
| `contact_enrichment` | Obtain missing public contact evidence |
| `monitoring_only` | No actionable step until next event |

## 3. Integrity rules

1. Evidence-first: every non-null claim carries evidence_quote/source or an
   evidence_id traceable to consumed inputs. No fabrication.
2. Evidence-backed absence: if no condition language exists, `conditions: []`
   plus an `unresolved[]` entry is CORRECT output.
3. Idempotent merge: re-running must reproduce byte-stable structure apart
   from `generated_at`; never duplicates condition/blocker/action ids.
4. Additive only: the key `action_intelligence` is written into the record;
   no existing key is modified or removed.
5. Deterministic IDs: C/B/N sequences assigned in stable sort order of their
   source content.
6. Confidence bands: HIGH = government-record or direct quote; MEDIUM =
   structured engine output; LOW = inference from narrative text; NONE = no
   evidence (field null).
