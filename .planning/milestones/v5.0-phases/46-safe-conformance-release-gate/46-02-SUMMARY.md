---
phase: 46-safe-conformance-release-gate
plan: 02
subsystem: testing
tags: [pytest, unittest, mec, policy, conformance, fail-closed]

requires:
  - phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
    provides: Production MEC gate, evaluators, vault adapter, and public screen
  - phase: 42-legacy-physician-arranged-employment-policy-resolver
    provides: POLICY decider, inert eligibility sidecar, and frozen CRS guard
provides:
  - Independent real-screen MEC matrix over all 38 criteria and 253 subtests
  - Independent POLICY matrix covering current, legacy, physician, evidence, and award paths
  - Exact non-vacuous manifests for rule, evidence, preflight, funds, manual, and window failures
affects: [46-03, 46-05, 46-06, SAFE-12]

tech-stack:
  added: []
  patterns:
    - Local raw fixtures with literal expected manifests and production public entry points
    - Paired confirmed-vault controls before one-mutation fail-closed negatives

key-files:
  created:
    - crawler/tests/test_conformance_v5_release_matrix.py
    - .planning/phases/46-safe-conformance-release-gate/deferred-items.md
  modified: []

key-decisions:
  - "Keep MEC/POLICY production and lock files frozen; encode the release oracle entirely in an independent conformance module."
  - "Keep SAFE-12 pending until the later all-screen authoritative runner plans complete."

patterns-established:
  - "Real-screen matrix: mutate raw registry rows or confirmed vault bindings, then assert exact production status and reason."
  - "Non-vacuity: compare literal expected labels to seen labels and require confirmed branch-reaching controls."

requirements-completed: []

duration: 11min
completed: 2026-07-20
---

# Phase 46 Plan 02: Independent MEC/POLICY Release Matrix Summary

**Independent production-screen matrix proving stale, unconfirmed, rejected, unwired, missing, funds, offer, manual, legacy, and physician paths cannot produce false MEC MEETS or POLICY awards**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-20T16:25:23Z
- **Completed:** 2026-07-20T16:36:39Z
- **Tasks:** 2
- **Files modified:** 1 implementation artifact

## Accomplishments

- Exercised all 38 literal MEC criteria through stale, superseded, out-of-window, missing, and unwired raw-row mutations using `prepare_mec_gate` and `screen_mec`.
- Proved confirmed controls reach real branches while pending, rejected, low-quality, and all five stale vault bindings yield exact closed reasons.
- Proved funds-without-snapshot, offer/manual, legacy/current/physician windows, malformed windows, and frozen award paths remain non-green with zero truthy points.
- Kept `.venv`, research cache, production screen files, and `poetry.lock` untouched.

## Task Commits

1. **Task 46-02-01: Build an independent MEC no-false-MEETS release matrix**
   - `3ee5b42` — RED: failing three-program manifest
   - `e94119b` — GREEN: independent real-screen MEC matrix
2. **Task 46-02-02: Add independent POLICY windows and frozen-award controls**
   - `6e99b49` — RED: failing POLICY branch manifest
   - `b58999c` — GREEN: local POLICY/vault/award matrix
   - `630071d` — exact malformed-window case-manifest hardening

## Files Created/Modified

- `crawler/tests/test_conformance_v5_release_matrix.py` — Independent MEC/POLICY release matrix with local raw fixtures, confirmed-vault controls, exact reasons, and case counts.
- `.planning/phases/46-safe-conformance-release-gate/deferred-items.md` — Records an unrelated Phase 46-01 donor-suite collection regression.

## Decisions Made

- Used only public production MEC entry points for MEC outcomes; no fabricated criterion states or donor test imports.
- Used the shipped auditor spine for POLICY evidence-state quarantine and all three production POLICY surfaces for zero-award assertions.
- Left SAFE-12 pending because this plan is only the first half of the multi-plan authoritative release gate.

## Deviations from Plan

None - plan implementation scope executed as written.

## Issues Encountered

- The complete independent matrix passes: `10 passed, 253 subtests passed`.
- The POLICY compatibility command passes: `10 passed, 6 deselected, 57 subtests passed`.
- The unchanged donor MEC suite cannot collect because Phase 46-01 removed the `_MEC_MODULES` symbol it imports. This pre-existing, out-of-scope regression is recorded in `deferred-items.md`.
- Ruff is not installed in `.venv`; no package install was attempted. Pytest and `git diff --check` verification passed.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 46-03 can extend the same independent matrix with STUDY/NOC and drift cases.
- SAFE-12 remains pending until Plans 46-03 through 46-06 complete the all-screen runner.

## Self-Check: PASSED

All created files and all five task commits were verified on disk/in git history.

---
*Phase: 46-safe-conformance-release-gate*
*Completed: 2026-07-20*
