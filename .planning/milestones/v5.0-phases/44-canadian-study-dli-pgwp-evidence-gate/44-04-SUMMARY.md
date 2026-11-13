---
phase: 44-canadian-study-dli-pgwp-evidence-gate
plan: 04
subsystem: audit
tags: [study-review, cli, dli, pgwp, conformance, privacy, fail-closed]

requires:
  - phase: 44-01
    provides: Quarantined six-field review.study intake and confirmation
  - phase: 44-02
    provides: Explicit positive-only DLI snapshot max-age resolver
  - phase: 44-03
    provides: Candidate-specific grounded study sidecar and private report
provides:
  - Resolver-first vault study-review CLI with index/snapshot preflights before vault access
  - Exact five-key public envelope with the closed six-field study result
  - Exhaustive study no-false-green, privacy, provenance, isolation, and freeze conformance
affects: [45-mec-sidecar, 46-safe-v5-conformance]

tech-stack:
  added: []
  patterns: [boundary-resolved configuration, zero-artifact refusal, runtime ignored-artifact fingerprinting, closed public projection]

key-files:
  created:
    - crawler/tests/test_study_review_cli.py
    - crawler/tests/test_conformance_v5_study_no_false_green.py
  modified:
    - crawler/cli.py
    - crawler/tests/test_conformance_v5_noc_no_auto_green.py
    - crawler/tests/test_extraction_store.py

key-decisions:
  - "Resolve the operational DLI max age once at the CLI boundary, then pass the same integer through snapshot preflight and review_study."
  - "CLI boundary refusals use the normal five-key error envelope with result null; only successful sidecar projections carry as_of."
  - "Ignored DLI/index integrity is proven with deterministic runtime pre/post fingerprints, never git diff."

patterns-established:
  - "No config, index, or snapshot refusal may probe a later boundary, open a vault, or create an artifact."
  - "Study stdout is limited to the common envelope and study_review.PUBLIC_FIELDS; evidence, citations, values, and paths remain private."

requirements-completed: [STUDY-02, STUDY-03, STUDY-04]

duration: 48min
completed: 2026-07-19
---

# Phase 44 Plan 04: Study Review CLI and Conformance Summary

**An offline resolver-first study-review command now exposes only a closed safe envelope, while exhaustive real-index conformance proves every refusal is artifact-free and every study path remains unscored and never green.**

## Performance

- **Duration:** 48 min
- **Started:** 2026-07-19T17:20:33Z
- **Completed:** 2026-07-19T18:08:08Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `vault study-review` with positive-only max-age resolution before index/snapshot probes, vault open, or writes, preserving the exact resolved override through `review_study`.
- Locked JSON stdout to the exact common five-key envelope and exact `study_review.PUBLIC_FIELDS`, with the validated common DLI chunk timestamp as the only public `as_of`.
- Added evidence, config, index/snapshot, grounding, provenance, credential-only, unwired, and all-factor isolation matrices with universal no-`SUBSTANTIATED`/nonzero assertions.
- Pinned ignored DLI/index runtime fingerprints, tracked golden bytes, vault schema/user-version, dependency set, lock hash, frozen source, and network-free imports.
- Completed the full crawler suite, complete conformance suite, focused study gates, and publish-safety scan without modifying dependencies or cached research.

## Task Commits

1. **Task 44-04-01 RED: CLI boundary and privacy contract** — `dd07131` (test)
2. **Task 44-04-01 GREEN: resolver-first study-review command** — `d6136e5` (feat)
3. **Task 44-04-02 RED: conformance gate requirement** — `c80d71d` (test)
4. **Task 44-04-02 GREEN: exhaustive no-false-green and freeze matrix** — `555cd46` (feat)
5. **Blocking conformance fixture alignment** — `4f3e39f` (fix)
6. **Full-suite field-vocabulary alignment** — `f20614d` (fix)

Every commit carries the required `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer.

## Files Created/Modified

- `crawler/cli.py` — Resolver-first/preflight-first `vault study-review` handler and parser.
- `crawler/tests/test_study_review_cli.py` — Override/order/refusal/envelope/privacy/private-report/idempotence CLI coverage.
- `crawler/tests/test_conformance_v5_study_no_false_green.py` — Complete study negative matrix and deterministic runtime/frozen-surface pins.
- `crawler/tests/test_conformance_v5_noc_no_auto_green.py` — Non-vacuous exact marker/title selector for the shared retrieval gate.
- `crawler/tests/test_extraction_store.py` — Complete Phase 44 `FieldName` vocabulary expectation.

## Decisions Made

- Raw `--snapshot-max-age-days` text is resolved by the one policy resolver so explicit and environment failures share one machine-readable refusal.
- Human mode writes only safe status/reason/counts and the vault-relative private-report location to stderr; stdout remains empty.
- Current designation and PGWP observations remain historical/program eligibility limits, so even corrected complete evidence ends `AT-RISK designation_historical_unproven`.
- `pyproject.toml`, `poetry.lock`, vault schema, CRS/public-envelope code, and ignored corpus/index bytes remain unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Aligned the NOC synthetic selector with the strengthened shared gate**
- **Found during:** Overall conformance verification
- **Issue:** The legacy NOC synthetic query selected an adjacent heading before its cited tiny chunk, so strict retrieval correctly refused four isolation tests.
- **Fix:** Added the fixture's exact quote marker and title requirement to select the cited chunk non-vacuously.
- **Files modified:** `crawler/tests/test_conformance_v5_noc_no_auto_green.py`
- **Verification:** Focused repair passed 5 tests; complete conformance passed 116 tests and 314 subtests.
- **Commit:** `4f3e39f`

**2. [Rule 3 - Blocking] Completed the model vocabulary expectation**
- **Found during:** Full crawler suite verification
- **Issue:** The older exhaustive `FieldName` test omitted five Phase 44 study members already present in the typed model.
- **Fix:** Added institution, DLI, program start/end, and study status to the expected vocabulary.
- **Files modified:** `crawler/tests/test_extraction_store.py`
- **Verification:** Focused model test passed; full suite passed 1148 tests, 2 skipped, and 1046 subtests.
- **Commit:** `f20614d`

---

**Total deviations:** 2 auto-fixed (2 blocking test-fixture alignments).
**Impact on plan:** Both repairs restored existing contract gates after Phase 44 additions; neither changed production behavior, dependencies, schema, or scope.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_study_review_cli.py crawler/tests/test_conformance_v5_study_no_false_green.py -q` — 22 passed, 93 subtests passed.
- `.venv/bin/python -m pytest crawler/tests/test_study_review.py crawler/tests/test_study_review_audit_seam.py crawler/tests/test_auditors_additional.py -q` — 40 passed, 63 subtests passed.
- `.venv/bin/python -m pytest crawler/tests -m conformance -q` — 116 passed, 1034 deselected, 314 subtests passed.
- `.venv/bin/python -m pytest crawler/tests -q` — 1148 passed, 2 skipped, 1046 subtests passed.
- `.venv/bin/python scripts/check_publish_safe.py` — 445 tracked files scanned, 0 violations.
- `pyproject.toml` and `poetry.lock` have no diff; `.planning/research/.cache/` remained untouched.

## Known Stubs

None.

## Issues Encountered

None remaining.

## TDD Gate Compliance

- Task 44-04-01 RED commit `dd07131` failed because `study-review` was not registered; GREEN followed in `d6136e5`.
- Task 44-04-02 RED commit `c80d71d` required the missing conformance matrix; GREEN followed in `555cd46`.

## User Setup Required

None - no package, schema, network, or external-service setup was added. Runtime callers must provide a positive max age explicitly or through `PR_DLI_SNAPSHOT_MAX_AGE_DAYS`.

## Next Phase Readiness

- STUDY-02, STUDY-03, and STUDY-04 are fully gated and ready for Phase 44 verification.
- Phase 45 may consume the inert study sidecar without changing CRS totals, public audit envelopes, or the pinned local-snapshot trust path.

## Self-Check: PASSED

- Created files and summary exist.
- Task/deviation commits `dd07131`, `d6136e5`, `c80d71d`, `555cd46`, `4f3e39f`, and `f20614d` exist.
- No tracked file deletion occurred; stub and threat-surface scans found no goal-blocking residue or unplanned boundary.

---
*Phase: 44-canadian-study-dli-pgwp-evidence-gate*
*Completed: 2026-07-19*
