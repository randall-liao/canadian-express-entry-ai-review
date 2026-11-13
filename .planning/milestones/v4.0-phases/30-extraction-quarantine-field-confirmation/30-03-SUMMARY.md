---
phase: 30-extraction-quarantine-field-confirmation
plan: 03
subsystem: cli
tags: [cli, argparse, confirmation, pii, json-envelope, extraction, vault]

# Dependency graph
requires:
  - phase: 30-01
    provides: "confirm_value / is_stale / is_audit_eligible / list_extracted_values store + gate"
  - phase: 30-02
    provides: "extraction.extract_document + MissingExtractionDependency"
  - phase: 29-candidate-vault-pii-perimeter
    provides: "vault CLI verbs + PII-light _vault_ok/_vault_fail envelope helpers + contract"
provides:
  - "crawler/confirm.py: field-level confirm/correct/reject orchestration + PII split (build_field_view / build_field_view_summary / apply_decision / format_field_view_human)"
  - "Additive `vault extract`, `vault fields`, `vault confirm` CLI verbs on the frozen 5-key envelope"
  - "End-to-end SC1-SC4 conformance through crawler.cli.main"
affects: [30-04-doctor-conformance, phase-32-auditor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PII split: human-visible confirmation detail to STDERR only; --json carries PII-light summaries"
    - "Rubber-stamp defense is structural: one --value-id per confirm call, no bulk confirm-all"
    - "Lazy extraction import in the CLI verb; MissingExtractionDependency -> missing_dependency/exit 3"

key-files:
  created:
    - crawler/confirm.py
    - crawler/tests/test_extract_confirm_cli.py
  modified:
    - crawler/cli.py

key-decisions:
  - "vault fields prints the full PII-rich view to stderr (local terminal) and emits only PII-light ExtractedValueSummary-shaped rows on --json stdout"
  - "apply_decision validates decision + requires corrected_value for correct; delegates to vault.confirm_value for exactly one value"
  - "--note is recorded via confirmed_by (no separate confirmation-notes column added this phase)"

patterns-established:
  - "confirm.py imports only crawler.vault (never crawler.extraction) so it loads lean"
  - "vault extract aggregates PII-light quality_counts across documents"

requirements-completed: [EXTRACT-02, EXTRACT-03, EXTRACT-04]

# Metrics
duration: ~45min
completed: 2026-07-06
---

# Phase 30 Plan 03: Confirm-What-I-Read CLI Summary

**Field-level `vault extract`/`fields`/`confirm` CLI verbs that let the applicant review each extracted field's raw value, normalized value, source page/crop, affected CRS factor, and profile claim on the local terminal — while the `--json` machine envelope stays PII-light — and that surface the Plan-01 audit-eligibility gate + staleness so nothing pending/rejected/low-quality/ambiguous/stale can look green. 16 e2e tests prove SC1-SC4.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-06T09:20:00Z
- **Completed:** 2026-07-06T10:05:00Z
- **Tasks:** 3 (Task 1 TDD, Task 2 auto, Task 3 TDD e2e)
- **Files modified:** 3

## Accomplishments
- **EXTRACT-03**: `vault fields` (human/stderr) shows all five facets per field — raw value, normalized value, source page/crop (image relpath + bbox), affected CRS factor, and the profile claim it substantiates; `vault confirm` acts per-field (confirm|correct|reject).
- **PII split (locked constraint)**: the PII-rich detail goes to STDERR only; the `--json` envelope carries only `ExtractedValueSummary`-shaped rows (value_id, field_name, status, quality, factor_id, stale, audit_eligible). Cross-verb no-PII test proves no fake raw value / path reaches any stdout envelope.
- **Rubber-stamp defense (Pitfall 10)**: `vault confirm` requires a single `--value-id` — there is no bulk "confirm all"; `apply_decision` mutates exactly one value.
- **Staleness surfacing (Pitfall 12)**: `stale`/`audit_eligible` reported from the Plan-01 gate; a rule-registry bump or file replacement flips a confirmation stale until CLI re-confirm.
- **Fail-closed dep handling**: `vault extract` maps `MissingExtractionDependency` to `missing_dependency`/exit 3 with the install hint (not an opaque crash).

## Task Commits

1. **Task 1: confirm.py orchestration + view builder** — `6a4ae2a` (test) → `a379400` (feat)
2. **Task 2: vault extract/fields/confirm CLI verbs** — `1a6dfdb` (feat)
3. **Task 3: end-to-end SC1-SC4 conformance** — `0664277` (test)

## Files Created/Modified
- `crawler/confirm.py` - NEW: build_field_view (full PII view), build_field_view_summary + list_field_views (PII-light), apply_decision (single value), format_field_view_human (stderr).
- `crawler/cli.py` - Added `_cmd_vault_extract`/`_cmd_vault_fields`/`_cmd_vault_confirm` + subparsers; metavar → `{init,profile,ita,import,list,extract,fields,confirm}`; frozen envelope untouched.
- `crawler/tests/test_extract_confirm_cli.py` - NEW: 7 unit (view/decision) + 9 e2e CLI (SC1-SC4, ambiguous, missing-dep, no-PII, structural single-value).

## Decisions Made
- Human confirmation detail (PII) is printed to stderr; the machine envelope never carries raw/normalized values (locked constraint / Pitfall 5 & 11).
- `apply_decision` structurally confirms exactly one value — the rubber-stamp defense is by design, not by policy.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required (optional Tesseract already noted in Plan 02).

## Next Phase Readiness
- Plan 04 (doctor + conformance) can drive the full extract→fields→confirm loop and reuse the PII-light envelope for the milestone conformance gate.

---
*Phase: 30-extraction-quarantine-field-confirmation*
*Completed: 2026-07-06*

## Self-Check: PASSED
- All created/modified files present on disk.
- All 4 task commits (2 test + 2 feat) present in git history.
- Plan verification green: 26 passed (test_extract_confirm_cli + test_vault_cli); each --json verb emits one five-key envelope.
