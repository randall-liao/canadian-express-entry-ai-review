---
phase: 32-auditor-vertical-slice-private-report-contract
plan: 04
subsystem: api
tags: [audit-report, vault, fail-closed, pii-boundary, persistence]

requires:
  - phase: 32-02
    provides: record_audit_run / complete_audit_run / record_factor_verdict
  - phase: 32-03
    provides: audit_factor + AuditGroundingError
  - phase: 32-01
    provides: to_public_envelope down-projection
provides:
  - crawler/audit_report.py run_audit() orchestration seam
  - vault-only JSON+MD report write under output/crs-audit/
  - fail-closed ordering (no partial report / orphan row on grounding failure)
affects: [32-05 vault audit CLI]

tech-stack:
  added: []
  patterns:
    - "Fail-closed ordering: verdict computed before any write/persist"
    - "Vault-relative report path derived from vault.root grandparent (personal root)"

key-files:
  created:
    - crawler/audit_report.py
    - crawler/tests/test_audit_report.py
  modified: []

key-decisions:
  - "Do not pre-mint the run id: record_audit_run (after a verdict) mints the durable aud_ id"
  - "report.run_id reassigned to the persisted id so filename == audit_runs.audit_run_id"
  - "Report path computed relative to the personal root (candidates/<id>/output/crs-audit/<id>.json)"

patterns-established:
  - "The report artifact lands inside the already-publish-safe output/crs-audit subtree"

requirements-completed: [AUDIT-02, AUDIT-06]

duration: 14min
completed: 2026-07-06
---

# Phase 32 Plan 04: Vault-Only Audit Report Writer Summary

**`run_audit` turns an in-memory verdict into durable, vault-only output — fail-closed: it computes the verdict first so an `AuditGroundingError` leaves zero artifacts, then writes the evidence-bearing JSON+MD report only under `candidates/<id>/output/crs-audit/`, persists the `audit_runs`+`factor_verdicts` trail, and returns a PII-light public envelope with a vault-relative path.**

## Performance

- **Duration:** ~14 min
- **Tasks:** 2 (both tdd), implemented cohesively (fail-closed by construction)
- **Files modified:** 2 (created)

## Accomplishments
- Ordered `run_audit` so `audit_factor` runs BEFORE any filesystem write or DB insert — an `AuditGroundingError` propagates with no report file and no persisted rows (SC5).
- Wrote the PII-bearing report (JSON model dump + human Markdown factor card) only under the vault `output/crs-audit/` subtree, every path re-anchored via `paths.resolve_within`.
- Persisted a complete `audit_runs` row + one `factor_verdicts` row per card, and down-projected to a PII-light `PublicAuditEnvelope` with the vault-relative report path.

## Task Commits

1. **Tasks 1+2: fail-closed run_audit + tests** - `3eaead8` (feat)

## Files Created/Modified
- `crawler/audit_report.py` — `run_audit`, the vault-relative path helper, and the Markdown renderer.
- `crawler/tests/test_audit_report.py` — 7 tests (write path, persistence, PII perimeter, fail-closed).

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_audit_report.py -q` → 7 passed.
- `.venv/bin/python scripts/check_publish_safe.py` → 0 violations (reports written to a tempdir vault).
- `.venv/bin/python -m pytest crawler/tests/test_auditor.py crawler/tests/test_audit_store.py -q` → green.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Run-id minting reconciled with the record helper**
- **Found during:** Task 1 implementation
- **Issue:** the plan suggested minting the run id up front via `vault.new_audit_run_id()`, but the shipped `record_audit_run` (Plan 02, out of this plan's file scope) mints its own id — pre-minting would desync the filename from the persisted `audit_runs.audit_run_id`.
- **Fix:** let `record_audit_run` mint the durable id (called only AFTER a verdict, preserving fail-closed ordering) and reassign `report.run_id` to it, so the filename and the persisted id share one id. This satisfies the "insert lazily / only after success" invariant without modifying `vault.py`.
- **Files modified:** `crawler/audit_report.py`
- **Commit:** `3eaead8`

## Known Stubs
None.
