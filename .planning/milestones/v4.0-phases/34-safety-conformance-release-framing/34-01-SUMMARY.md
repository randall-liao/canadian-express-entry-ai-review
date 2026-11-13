---
phase: 34-safety-conformance-release-framing
plan: 01
subsystem: testing
tags: [conformance, fail-closed, crs-auditor, vault, pydantic, safety]

# Dependency graph
requires:
  - phase: 30-extraction-quarantine
    provides: is_audit_eligible / five-key staleness quarantine gate
  - phase: 32-audit-slice
    provides: fail-closed verdict contract + AuditGroundingError + closed verdict vocabulary
  - phase: 33-full-auditor-pack
    provides: FULL_GRID_FACTORS dispatch spine + four auditor modules + default decider
provides:
  - Authoritative SAFE-01 no-false-green conformance module (full grid x blocking-state matrix)
  - Choke-point proof that no pending/rejected/low-quality/ambiguous/stale value is audit-eligible
  - Fail-closed ordering + default-decider + closed-vocabulary + down-projection proofs
affects: [milestone-audit, release-gate, safety-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Full-grid x blocking-evidence-state parametrized matrix over all four modules"
    - "Choke-point (is_audit_eligible) + verdict-consequence dual assertion"
    - "Non-vacuity via per-factor eligible-admittance + one green per module"

key-files:
  created:
    - crawler/tests/test_conformance_v40_no_false_green.py
  modified: []

key-decisions:
  - "Prove the gate at the choke point (audit_eligible_values) AND the verdict (audit_one/run_full_audit) so the guarantee is load-bearing, not incidental"
  - "Non-vacuity shown per-factor (legitimate value admitted) plus one SUBSTANTIATED positive control per module (core/spouse/transferability/additional)"
  - "Reuse the shipped _IntegrationCase synthetic-vault seeding + real registry + real corpus; never a test double"

patterns-established:
  - "Fresh per-subtest candidate vault for clean staleness isolation"
  - "Ungrounded + gap:true consumed-rule registries assert zero-artifact fail-closed ordering"

requirements-completed: [SAFE-01]

# Metrics
duration: 22min
completed: 2026-07-06
---

# Phase 34 Plan 01: SAFE-01 No-False-Green Conformance Summary

**Authoritative full-grid x blocking-evidence-state matrix proving no pending/unconfirmed/low-confidence/stale value can ever green any of the 18 CRS grid factors across all four modules, driving the real vault.is_audit_eligible choke point through the auditor spine.**

## Performance

- **Duration:** ~22 min (whole phase, parallel wave)
- **Tasks:** 2
- **Files created:** 1
- **Tests added:** 12 tests, 148 subtests

## Accomplishments
- Full-grid x five-blocking-state matrix (pending/rejected/low_quality/ambiguous/stale) asserts non-audit-eligibility at the choke point and non-SUBSTANTIATED verdicts through `auditor.audit_one` / `run_full_audit` for every `FULL_GRID_FACTORS` factor.
- Non-vacuity proven two ways: the same gate ADMITS a legitimate confirmed+ok+fresh value for every direct factor, and one fully-satisfying case per module (core.language.first / spouse.language / transfer.foreign_language / additional.nomination) still reaches SUBSTANTIATED.
- Fail-closed proofs: ungrounded and gap:true consumed rules raise `AuditGroundingError` and write ZERO artifacts (no report file, no `audit_runs`/`factor_verdicts` rows); the unregistered-factor default decider is AT-RISK; an out-of-vocabulary verdict is rejected at the pydantic boundary; `to_public_envelope` maps verdicts 1:1 (no invented green).

## Task Commits

1. **Task 1: Full-grid x blocking-state matrix (all four modules)** - `e60d36b` (test)
2. **Task 2: Fail-closed ordering / default-decider / closed-vocabulary / down-projection** - `e60d36b` (test)

_(Both tasks landed in one atomic module commit; classes are separable within the file.)_

## Files Created/Modified
- `crawler/tests/test_conformance_v40_no_false_green.py` - SAFE-01 authoritative no-false-green conformance module (493 lines).

## Decisions Made
- Assert BOTH the choke point and the verdict consequence so the no-false-green guarantee is proven load-bearing.
- Use a fresh candidate vault per blocking subtest for clean five-key staleness isolation.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- `extracted_values.factor_id` carries a FK to `crs_profile_factors`; the choke-point seeding was updated to upsert a profile claim before inserting the value (required by the schema, not a behavior change).

## Next Phase Readiness
SAFE-01 module is discovered by the release gate (`scripts/run_conformance.py`) via the `test_conformance_v40_*.py` glob and the `conformance` marker. Ready for the milestone audit.

---
*Phase: 34-safety-conformance-release-framing*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created files exist on disk; all task commit hashes are present in git history.
