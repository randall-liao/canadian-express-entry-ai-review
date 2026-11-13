---
phase: 32-auditor-vertical-slice-private-report-contract
plan: 03
subsystem: api
tags: [auditor, crs, grounding, fail-closed, verdict, tdd]

requires:
  - phase: 30-extraction-confirmation
    provides: is_audit_eligible / audit_eligible_values quarantine + staleness
  - phase: 31-grounded-crs-rule-registry
    provides: validate_registry (frozen gate), crs_audit to_clb/within_validity/score_factor
  - phase: 32-01
    provides: PrivateAuditReport / PrivateFactorCard models
provides:
  - crawler/auditor.py audit_factor() fail-closed first-language verdict engine
  - AuditGroundingError (sole error surface; GAP/AT-RISK/N/A are returned verdicts)
affects: [32-04 report writer, 32-05 vault audit CLI, 33 fan-out]

tech-stack:
  added: []
  patterns:
    - "Grounding-by-construction: gate consumed rows before any evidence read or verdict"
    - "Deterministic threshold math read entirely from grounded rows (no inlined literals)"

key-files:
  created:
    - crawler/auditor.py
    - crawler/tests/test_auditor.py
  modified: []

key-decisions:
  - "Verdict order: N/A -> gate -> missing -> unaccepted -> unresolved -> expired -> below -> SUBSTANTIATED"
  - "substantiated_points = sum of per-ability grounded score_factor across the four abilities"
  - "reference_date = ITA round date if present else the run date (date.today())"
  - "confirmed_value snapshot (raw scores + benchmarks) is PII-bearing, stays in the vault report"

patterns-established:
  - "Engine returns an in-memory report only; persistence/write is Plan 04"

requirements-completed: [AUDIT-02]

duration: 22min
completed: 2026-07-06
---

# Phase 32 Plan 03: Fail-Closed First-Language Verdict Engine Summary

**The heart of the vertical slice: `audit_factor` runs the complete first-official-language substantiation loop — grounding gate → eligibility quarantine → deterministic benchmark math → verdict — and returns a `PrivateAuditReport`, where `SUBSTANTIATED` is impossible without proof + eligibility + threshold + a grounded/cited rule, and any ungrounded rule refuses the whole output.**

## Performance

- **Duration:** ~22 min
- **Tasks:** 1 feature (TDD: RED → GREEN)
- **Files modified:** 2 (created)

## Accomplishments
- Built `audit_factor` reusing the frozen `crs_rules.validate_registry` gate, the Phase-30 `audit_eligible_values` quarantine, and the Phase-31 `crs_audit` deterministic helpers — no new trust path, no inlined volatile threshold.
- Implemented the SC2/SC3 "never green" decision table: pending/low-quality/stale/missing → GAP; below-threshold/wrong-test → GAP; expired/unresolved → AT-RISK; not-claimed → N/A; happy path → SUBSTANTIATED.
- `AuditGroundingError` raised on any ungrounded or `gap:true` consumed rule (SC1/SC5), returning NO report; a grounded GAP/AT-RISK is a valid returned result.

## Task Commits

1. **RED: verdict-matrix tests** - `72e9783` (test)
2. **GREEN: fail-closed engine + N/A fixture fix** - `0157eba` (feat)

_No REFACTOR commit — the GREEN implementation was already minimal and clean._

## TDD Gate Compliance
- RED gate: `72e9783` (`test(32-03)`) — full matrix failed (module absent).
- GREEN gate: `0157eba` (`feat(32-03)`) — 16/16 tests pass.

## Files Created/Modified
- `crawler/auditor.py` — `audit_factor`, `AuditGroundingError`, gate/quarantine/decision helpers.
- `crawler/tests/test_auditor.py` — 16 tests over a synthetic index + registry + vault.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_auditor.py -q` → 16 passed.
- `.venv/bin/python -c "from crawler.auditor import audit_factor, AuditGroundingError"` → OK.
- `.venv/bin/python -m pytest crawler/tests/test_crs_audit.py crawler/tests/test_crs_rules.py -q` → green (frozen primitives untouched).
- `crs_rules.no_inlined_volatile_rules([auditor.__file__])` → `[]` (static self-scan clean).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] N/A test fixture violated a foreign-key constraint**
- **Found during:** GREEN run
- **Issue:** the not-claimed fixture added extracted values with `factor_id="core.language.first"` while omitting that factor row, tripping the `extracted_values → crs_profile_factors` FK.
- **Fix:** when `with_factor=False`, seed the evidence unlinked (`factor_id=None`); the N/A path short-circuits before reading evidence anyway.
- **Files modified:** `crawler/tests/test_auditor.py`
- **Commit:** `0157eba`

## Known Stubs
None.
