---
phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
plan: 01
subsystem: rule-registry
tags: [mec, fsw, fst, cec, grounding, freshness, ast]

requires:
  - phase: 40-safe-freshness-effective-date-foundation
    provides: shared gate_subset and effective-window predicate
  - phase: 31-grounded-crs-rule-registry
    provides: typed registry, retrieve-what-you-cite, coverage, and no-inline gate
provides:
  - Exact grounded FSW, FST, and CEC criterion registry
  - Inert program_eligibility FactorGroup and typed cited MEC payloads
  - Explicit no-default operational freshness resolver and row predicate
  - AST-aware MEC no-inline scanner categories
affects: [45-02, 45-03, 45-04, mec-screening, conformance-v5]

tech-stack:
  added: []
  patterns: [exact structural manifest, cited policy values, explicit operational freshness, AST constant scanning]

key-files:
  created:
    - crawler/data/crs_rules/mec.yaml
    - crawler/tests/test_mec_rules.py
  modified:
    - crawler/models/vault.py
    - crawler/models/crs_rules.py
    - crawler/crs_rules.py
    - crawler/snapshot_policy.py
    - crawler/data/crs_rules/COVERAGE.md
    - crawler/tests/test_crs_no_inlined_rules.py

key-decisions:
  - "program_eligibility is an inert additive registry domain; CRS scoring and FieldName remain unchanged."
  - "MEC rule age is operator configuration resolved from explicit input before PR_MEC_RULE_MAX_AGE_DAYS, with no default."
  - "Funds rows ground applicability, exemption, accessibility, borrowing, and equity only; no amount table is encoded."

patterns-established:
  - "Every MEC criterion has one exact structural rule ID and typed citation-indexed payload."
  - "Every selected MEC row must pass both row_in_effect and the shared operational freshness predicate."

requirements-completed: []

duration: 19min
completed: 2026-07-20
---

# Phase 45 Plan 01: Grounded MEC Registry Summary

**Complete official-source FSW/FST/CEC registry with exact coverage, cited typed policy payloads, explicit no-default freshness, and AST-aware no-inline enforcement**

## Performance

- **Duration:** 19 min
- **Started:** 2026-07-20T03:13:34Z
- **Completed:** 2026-07-20T03:32:08Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added all 38 exact FSW, FST, and CEC criteria as typed rows grounded in pinned IRCC, PDI, and IRPR corpus chunks.
- Added exact duplicate/missing/unknown/malformed/gap coverage enforcement and generated coverage with zero gaps.
- Added explicit operational MEC max-age resolution and fail-closed row freshness without a default.
- Extended the shared scanner for MEC durations, language levels, occupational hierarchy, grid values, dates, and funds values while ignoring Python comments/docstrings.
- Excluded all settlement-funds amount and low-income-threshold values while grounding applicability and accessibility policy.

## Task Commits

Each task was committed atomically:

1. **Task 45-01-01 RED: MEC registry contracts** - `905481a` (test)
2. **Task 45-01-01 GREEN: typed manifest and freshness contracts** - `0ae3d3a` (feat)
3. **Task 45-01-02 RED: grounding and scanner controls** - `e23efdd` (test)
4. **Task 45-01-02 GREEN: grounded registry and scanner** - `0d5dc88` (feat)
5. **Task 45-01-02 correction: exact payload citation binding** - `a2dfe7f` (fix)

## Files Created/Modified

- `crawler/data/crs_rules/mec.yaml` - Complete official-source MEC rows without funds amounts.
- `crawler/data/crs_rules/COVERAGE.md` - Generated exact five-domain coverage.
- `crawler/models/vault.py` - Inert additive `program_eligibility` factor group.
- `crawler/models/crs_rules.py` - Typed cited duration, hierarchy, and applicability payloads.
- `crawler/crs_rules.py` - Exact MEC manifest, coverage validation, and AST-aware scanner.
- `crawler/snapshot_policy.py` - Explicit no-default MEC max-age resolver and row freshness predicate.
- `crawler/tests/test_mec_rules.py` - Manifest, grounding, retrieve, effectivity, freshness, and funds-exclusion proofs.
- `crawler/tests/test_crs_no_inlined_rules.py` - MEC scanner enrollment and category controls.

## Decisions Made

- Kept `program_eligibility` inert: no CRS dispatch, totals, cards, public envelope, or evidence vocabulary changed.
- Used the existing loader, fingerprint, `auditor.gate_subset`, and `crs_audit.row_in_effect`; no alternate trust path was added.
- Treated the max-age value solely as required operational configuration, not an authoritative update-cadence claim.
- Left MEC-02, MEC-03, and MEC-04 pending until the later evaluator/CLI plans complete the end-to-end requirements.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected weekly-hours semantics and tightened citation binding**
- **Found during:** Task 45-01-02 verification
- **Issue:** The first payload draft reused a maximum-hours field for a minimum full-time offer condition and several composite values referenced overly narrow quote spans.
- **Fix:** Added a distinct cited minimum-hours-per-week field, cited maximum-counted-hours separately, and bound funds accessibility and grid caps to exact official spans.
- **Files modified:** `crawler/models/crs_rules.py`, `crawler/crs_rules.py`, `crawler/data/crs_rules/mec.yaml`
- **Verification:** All real rows pass `auditor.gate_subset`; all targeted suites pass.
- **Committed in:** `a2dfe7f`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Correctness and grounding were strengthened without expanding scope or dependencies.

## Issues Encountered

- Initial selector queries were too broad for the fixed retrieval budget; concise non-volatile queries and markers were tuned until all 38 real rows independently agreed and grounded.

## User Setup Required

None - runtime configuration is consumed by later CLI work; no dependency or external service was added.

## Next Phase Readiness

- Plans 45-02 through 45-04 can consume the exact manifest and one immutable registry snapshot.
- MEC-02, MEC-03, and MEC-04 remain pending until evaluator composition and command-boundary enforcement land.

## Self-Check: PASSED

All created artifacts and five task commits were verified on disk.

---
*Phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec*
*Completed: 2026-07-20*
