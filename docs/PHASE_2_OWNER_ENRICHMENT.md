# PermitSignal — Phase 2: Owner/Person Enrichment

## Objective

Complete the existing applicant/company enrichment capability
so PermitSignal can identify the real-world owner, principal,
responsible person, or other relevant person associated with a
discovered project/application when that information is
legitimately available.

## Existing system

Do NOT rebuild existing functionality.

The Python system already provides:

- live government discovery
- document ingestion
- PDF extraction
- application extraction
- opportunity generation
- lead queue
- Supabase persistence
- idempotent upsert
- existing applicant/company enrichment foundation

## Current gap

The system does not consistently surface the actual
owner/person behind the applicant/company.

## Phase 2 must

1. Inspect existing enrichment code.
2. Determine exactly what is already extracted.
3. Determine what owner/person information is missing.
4. Extend the existing enrichment layer.
5. Preserve existing pipeline behavior.
6. Store structured enrichment data.
7. Preserve evidence/source for discovered identity information.
8. Avoid unsupported identity matches.
9. Test against real Provo data.
10. Report exactly what was added and verified.

## Out of scope

Do NOT:

- build approval-action intelligence
- modify the frontend
- redesign the Python pipeline
- move Python intelligence into n8n
- build outreach automation
- modify the roadmap
- implement Phase 3+
- rewrite working discovery/pipeline components unnecessarily

## Completion criteria

Phase 2 is complete only when:

- applicant/company enrichment still works
- owner/person enrichment is demonstrably working
- data is persisted correctly
- identity/source evidence is retained
- existing tests remain passing
- real-world test data demonstrates the result
- no unrelated architecture changes were introduced