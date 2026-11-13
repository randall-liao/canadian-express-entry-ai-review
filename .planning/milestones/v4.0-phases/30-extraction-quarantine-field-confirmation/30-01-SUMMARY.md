---
phase: 30-extraction-quarantine-field-confirmation
plan: 01
subsystem: database
tags: [sqlite, pydantic, vault, migration, extraction, quarantine, staleness]

# Dependency graph
requires:
  - phase: 29-candidate-vault-pii-perimeter
    provides: "vault.sqlite (user_version=1), crawler/vault.py store + paths.resolve_within, crawler/models/vault.py two-PII-tier convention"
provides:
  - "Schema v2 migration (user_version 1→2) adding extraction_runs, document_pages, extracted_values, factor_evidence"
  - "Pydantic boundary models: ExtractionRun, DocumentPage, ExtractedValue, Confirmation + PII-light summaries + FieldName/status/quality Literals"
  - "Quarantine store: add_extracted_value FORCES confirmation_status='pending'"
  - "SC3 gate is_audit_eligible() + SC4 is_stale() bound to five keys (file/render/parser/profile-claim/registry)"
  - "confirm_value / audit_eligible_values single safe auditor entry point"
affects: [30-02-extraction-engine, 30-03-confirmation-cli, 30-04-doctor-conformance, phase-31-rule-registry, phase-32-auditor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive PRAGMA user_version migration branch (version<2) — v1 rows untouched"
    - "Quarantine-at-insert: extraction store path can only ever write 'pending'"
    - "Five-key staleness binding captured at confirm time; compared to current on read"
    - "Lazy single-source parser version (current_parser_version imports extraction.PARSER_VERSION, DEFAULT fallback on lean install)"

key-files:
  created:
    - crawler/tests/test_extraction_store.py
  modified:
    - crawler/models/vault.py
    - crawler/vault.py
    - crawler/tests/test_vault.py

key-decisions:
  - "extraction_runs stores parser_version (plan spec) rather than ARCHITECTURE's extractor_version — it is the single SC4 staleness source of truth"
  - "profile_claim_version = sha256[:16] of {claimed_value_json, claimed_level, claimed_points}; None-safe for unlinked/missing factors"
  - "is_stale returns False for non-confirmed statuses (pending/rejected handled as ineligible upstream) so it is only meaningful for confirmed/corrected"

patterns-established:
  - "Trust predicate barrier: is_audit_eligible is the ONLY function an auditor may cross"
  - "add_extracted_value validates field_name/quality via ExtractedValue model → PII-safe VaultError on bad vocabulary"

requirements-completed: [EXTRACT-02, EXTRACT-03, EXTRACT-04]

# Metrics
duration: ~55min
completed: 2026-07-06
---

# Phase 30 Plan 01: Extraction Vault Schema & Trust Logic Summary

**Schema-v2 vault migration + fail-closed trust logic (`is_audit_eligible`/`is_stale`) so automated extraction is born quarantined as `pending` and five-key staleness invalidates any confirmation on change — proven with 39 synthetic-row tests, no extraction deps required.**

## Performance

- **Duration:** ~55 min
- **Started:** 2026-07-06T07:25:04Z
- **Completed:** 2026-07-06T08:20:00Z
- **Tasks:** 3 (all TDD: RED→GREEN)
- **Files modified:** 4

## Accomplishments
- **SC3 quarantine gate** (`is_audit_eligible`): a value is audit-eligible ONLY when `confirmation_status ∈ (confirmed, corrected)` AND `quality_flag=='ok'` AND not stale — pending/rejected/low_quality/ambiguous/stale are all ineligible (parametrized status×quality matrix proves it).
- **SC4 staleness** (`is_stale`): a confirmation binds five keys (source file sha256, page render sha256, parser version, profile-claim version, rule-registry version); changing ANY one flips stale→True and eligibility→False; re-confirm clears it.
- **Schema v2 migration**: additive `user_version` 1→2 branch adds `extraction_runs`, `document_pages`, `extracted_values` (with 5 `confirmed_*` binding columns), `factor_evidence`; a seeded Phase-29 v1 DB upgrades in place with all rows intact.
- **Quarantine-at-insert**: `add_extracted_value` FORCES `confirmation_status='pending'` regardless of caller input (T-30-01).
- Boundary models + PII-light summaries that never carry raw_text/normalized_value/bbox/paths.

## Task Commits

Each task was committed atomically (TDD test→feat):

1. **Task 1: Boundary models** — `66058a9` (test) → `cf5c63f` (feat)
2. **Task 2: Schema v2 migration + store functions** — `ff2988f` (test) → `b9b3ce8` (feat)
3. **Task 3: SC3 gate + SC4 staleness + version helpers** — `114c529` (test) → `a6668e1` (feat)

## Files Created/Modified
- `crawler/models/vault.py` - Added ConfirmationStatus/QualityFlag/ConfirmationDecision/EvidenceRole/FieldName Literals; ExtractionRun/DocumentPage/ExtractedValue/Confirmation full models; ExtractedValueSummary/ExtractionRunSummary/DocumentPageSummary PII-light summaries.
- `crawler/vault.py` - SCHEMA_VERSION→"2", `_SCHEMA_V2_DDL`, `_migrate` v2 branch, id minters, store functions (record/complete_extraction_run, add_document_page, add_extracted_value, link_factor_evidence, list/get_extracted_value), version helpers (current_parser_version, profile_claim_version, rule_registry_version get/set), trust predicates (confirm_value, is_stale, is_audit_eligible, audit_eligible_values).
- `crawler/tests/test_extraction_store.py` - NEW: 39 tests + 12 subtests across TestModels/TestSchemaV2Migration/TestStoreFunctions/TestAuditGate/TestStaleness.
- `crawler/tests/test_vault.py` - Updated three Phase-29 guards (user_version/schema_version/table-absence) to expect schema v2.

## Decisions Made
- `parser_version` (not `extractor_version`) is stored per extraction_run as the single SC4 staleness source of truth (per plan spec).
- `current_parser_version()` lazily imports `crawler.extraction.PARSER_VERSION` and falls back to `DEFAULT_PARSER_VERSION="1"` so the module still imports on a lean install (extraction deps absent) — SC4 stays testable without the engine.
- `is_stale` treats a None→value (or value→None) binding transition as a change.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required (this plan adds no dependencies).

## Next Phase Readiness
- Plan 02 (extraction engine) can write `pending` values through `add_extracted_value` and define `PARSER_VERSION` consumed by `current_parser_version`.
- Plan 03 (confirmation CLI) can drive `confirm_value` + surface `is_audit_eligible`/`is_stale`.
- The trust barrier is proven deterministically with synthetic rows; no extraction dependencies were needed.

---
*Phase: 30-extraction-quarantine-field-confirmation*
*Completed: 2026-07-06*

## Self-Check: PASSED
- All created/modified files present on disk.
- All 6 task commits (3 test + 3 feat) present in git history.
- Plan verification green: 48 passed + 12 subtests; fresh vault user_version=2 with 4 tables; lean import ok.
