---
phase: 46-safe-conformance-release-gate
plan: 06
subsystem: testing
tags: [pytest, conformance, release-gate, safe-11, safe-12, publish-safety]

requires:
  - phase: 46-safe-conformance-release-gate
    provides: SAFE-11 grounding, all-screen release matrices, privacy proof, and confirmed-vault E2E
provides:
  - One bounded authoritative SAFE-01..12 runner over v4[01] and v5 modules
  - Non-vacuous runner self-tests for exact discovery, required nodes, markers, recursion, and return codes
  - Complete focused, release, full-suite, publish-safe, dependency, lock, and frozen-source evidence
affects: [v5.0-release, phase-verification, safe-conformance]

tech-stack:
  added: []
  patterns:
    - Sorted deduplicated bounded glob union with literal hard-required release modules
    - Pre-pytest non-empty, v5-present, and required-module validation
    - Collection mode preserves inherited environment while only real execution sets the release guard

key-files:
  created:
    - crawler/tests/test_conformance_v5_release_gate.py
  modified:
    - scripts/run_conformance.py
    - pyproject.toml
    - crawler/tests/test_conformance_v5_mec_no_false_meets.py
    - crawler/tests/test_conformance_v5_study_no_false_green.py

key-decisions:
  - "Use only the bounded v4[01] and v5 glob union, then enforce a literal eight-module v5 release prerequisite set before pytest."
  - "Treat an inherited PR_CONFORMANCE_RUNNER value as copied outer release state; collect/list never creates or mutates it, while real execution sets it to 1."
  - "Keep Phase 46 in Verifying after all release gates pass so verifier sign-off remains the final lifecycle transition."

patterns-established:
  - "Release discovery must be both non-empty and complete: structural marker parity alone cannot authorize a release."
  - "Exact required node IDs make every focused v5 proof load-bearing during collect-only verification."

requirements-completed: [SAFE-11, SAFE-12]

duration: 59min
completed: 2026-07-20
---

# Phase 46 Plan 06: Authoritative SAFE-01..12 Release Gate Summary

**A single bounded Python command now hard-requires and executes every v4[01]/v5 conformance proof, with exact discovery, marker, recursion, prerequisite, return-code, publication, and frozen-surface closure.**

## Performance

- **Duration:** 59 min
- **Started:** 2026-07-20T17:41:22Z
- **Completed:** 2026-07-20T18:40:31Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Extended `scripts/run_conformance.py` from SAFE-01..08 to SAFE-01..12 using only the sorted deduplicated union of `test_conformance_v4[01]_*.py` and `test_conformance_v5_*.py`.
- Added a marked self-test that proves non-empty discovery, v5 presence, all eight hard-required v5 modules and exact nodes, marker parity, non-recursive collection, stable omission failures, passthrough, guard behavior, repository cwd, and exact pytest status propagation.
- Preserved all v4 modules while the authoritative command completed with 202 passed, 2227 subtests, zero skips, and the SAFE-01..12 PASS banner.
- Completed the full crawler/scripts, publish-safe, dependency/lock, and frozen production-source closure without modifying production, dependencies, lock, docs, or cache.

## Task Commits

1. **Task 46-06-01 RED: failing bounded runner contract** - `9bb0704` (test)
2. **Task 46-06-01 GREEN: authoritative SAFE-01..12 runner** - `2ab5596` (feat)
3. **Task 46-06-02: marker and reviewed frozen pins** - `56322ed` (test)
4. **Rule 3 fix: align the second pyproject hash oracle** - `13c963c` (fix)
5. **Rule 1 fix: inherited release-guard collection semantics** - `c327777` (fix)

Every commit carries the project-standard `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer.

## Files Created/Modified

- `crawler/tests/test_conformance_v5_release_gate.py` - Bounded discovery, exact required-node, marker, omission, recursion, passthrough, guard, cwd, and status self-test.
- `scripts/run_conformance.py` - Single authoritative SAFE-01..12 release command with hard-required v5 validation.
- `pyproject.toml` - Marker description updated to the v5 SAFE-01..12 suite only.
- `crawler/tests/test_conformance_v5_mec_no_false_meets.py` - Reviewed runner and pyproject SHA-256 pin rollover.
- `crawler/tests/test_conformance_v5_study_no_false_green.py` - Matching intentional pyproject marker SHA oracle rollover; dependency, lock, source, and network assertions unchanged.

## Decisions Made

- Required v5 modules are a literal exact set independent from glob discovery, so omission cannot silently reduce the release proof.
- Required node IDs are literal collect-only assertions, making every focused MEC/POLICY/STUDY/NOC, grounding, matrix, privacy/E2E, and runner proof non-vacuous.
- Collection copies the environment exactly and does not create the release guard; only a real run writes `PR_CONFORMANCE_RUNNER=1`.
- SAFE-11 and SAFE-12 are complete only after all eight final gates passed; Phase 46 remains Verifying for verifier sign-off.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Rolled the second intentional pyproject hash oracle**
- **Found during:** Final all-v5 conformance gate
- **Issue:** The planned marker-only `pyproject.toml` edit also invalidated the existing `_PYPROJECT_SHA` oracle in the STUDY frozen dependency test.
- **Fix:** Updated only that pyproject SHA constant; dependency sets, lock hash, source hashes, and network checks stayed unchanged.
- **Files modified:** `crawler/tests/test_conformance_v5_study_no_false_green.py`
- **Verification:** Focused frozen-pin tests passed, then all v5 passed with 120 tests and 2003 subtests.
- **Committed in:** `13c963c`

**2. [Rule 1 - Bug] Corrected collection behavior under an inherited release guard**
- **Found during:** Authoritative runner gate
- **Issue:** The self-test incorrectly required the copied environment to omit `PR_CONFORMANCE_RUNNER`, although the outer authoritative run correctly supplies it.
- **Fix:** Asserted collect/list preserve the inherited value without creating or mutating it; real runs still explicitly set it to `1`.
- **Files modified:** `crawler/tests/test_conformance_v5_release_gate.py`
- **Verification:** Self-test passed both with and without an inherited guard; authoritative runner then passed with zero skips.
- **Committed in:** `c327777`

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 3 blocker)
**Impact on plan:** Both fixes were required for exact release semantics and frozen-pin consistency; no production, dependency, lock, documentation, or cache scope was added.

## Issues Encountered

- The first all-v5 run exposed the second pyproject pin and stopped at `119 passed, 1 failed, 2003 subtests`; the corrected run completed `120 passed, 2003 subtests`.
- The first authoritative run exposed inherited-guard test semantics and stopped at `202 passed, 2 failed subtests`; the corrected authoritative run completed with zero skips.

## Verification

1. `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_privacy_release.py crawler/tests/test_conformance_v5_release_gate.py -q`
   - `54 passed, 1509 subtests passed`
2. `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_*.py -q`
   - `120 passed, 2003 subtests passed`
3. `.venv/bin/python scripts/run_conformance.py --collect-only -q`
   - `202 tests collected`; exact 17-module bounded union; pytest rc 0
4. `.venv/bin/python scripts/run_conformance.py -q`
   - `202 passed, 2227 subtests passed`; zero skips; SAFE-01..12 PASS
5. `.venv/bin/python -m pytest crawler/tests scripts/tests -q`
   - `1463 passed, 2 skipped, 3302 subtests passed`
6. `.venv/bin/python -m pytest scripts/tests/test_check_publish_safe.py -q`
   - `36 passed, 25 subtests passed`
7. `.venv/bin/python scripts/check_publish_safe.py`
   - `485 tracked files scanned, 0 violations`
8. `git diff --exit-code -- poetry.lock crawler/models/audit.py crawler/crs_audit.py crawler/auditors/__init__.py crawler/policy_offer.py crawler/mec_screen.py crawler/study_review.py crawler/noc_review.py crawler/noc_worksheet.py`
   - Exit 0; lock and frozen production surfaces unchanged

The two full-suite skips are unrelated local-only tests; the authoritative Phase 46 release command recorded zero prerequisite skips.

## TDD Gate Compliance

- RED commit: `9bb0704`
- GREEN commit: `2ab5596`
- The RED test failed against the v4-only runner before implementation, then the complete quick gate passed after GREEN.

## Known Stubs

None. Empty collections and `None` values found by the scan are deliberate adversarial test fixtures and fail-closed states, not unwired release behavior.

## Authentication Gates

None.

## User Setup Required

None - no package install, network service, credential, or manual action was required.

## Next Phase Readiness

- SAFE-11 and SAFE-12 have complete green release evidence.
- Phase 46 is ready for verifier sign-off and remains in Verifying rather than Complete.
- `.planning/research/.cache/` remained untouched.

## Self-Check: PASSED

All five implementation artifacts, the summary, and all five atomic task/fix commits were verified on disk and in git history.

---
*Phase: 46-safe-conformance-release-gate*
*Completed: 2026-07-20*
