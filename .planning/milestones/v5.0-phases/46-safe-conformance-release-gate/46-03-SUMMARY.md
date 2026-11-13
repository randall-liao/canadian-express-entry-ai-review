---
phase: 46-safe-conformance-release-gate
plan: 03
subsystem: testing
tags: [pytest, study, noc, registry-fingerprint, provenance, fail-closed]

requires:
  - phase: 46-safe-conformance-release-gate
    provides: Independent MEC/POLICY release matrix from Plan 02
  - phase: 44-canadian-study-dli-pgwp-evidence-gate
    provides: Production STUDY screen and pinned DLI provenance gate
  - phase: 43-enhanced-noc-work-duty-review-worksheet
    provides: Production NOC worksheet and inert duty-review sidecar
provides:
  - Independent STUDY current-only, PGWP Details/No, evidence, preflight, and provenance matrix
  - Independent NOC missing, source, partial, rejected, stale, drifted, and superseded-duty matrix
  - Cross-screen registry snapshot A-to-B replay for MEC, POLICY, STUDY, and NOC
affects: [46-05, 46-06, SAFE-12, release-conformance]

tech-stack:
  added: []
  patterns:
    - Fresh local vaults plus copied read-only SQLite and source fixtures
    - Production registry fingerprint as the sole replay trust input

key-files:
  created: []
  modified:
    - crawler/tests/test_conformance_v5_release_matrix.py

key-decisions:
  - "Keep all STUDY/NOC release oracles local to the single matrix and call production public screens without donor test helpers."
  - "Model registry drift by adding one grounded row to immutable snapshot B, then replay snapshot-A evidence at each screen boundary."

patterns-established:
  - "Dynamic provenance negatives mutate one source, manifest, index, selector, citation, or date property and assert exact closed output."
  - "Cross-screen replay verifies the fingerprint mismatch before inert sidecars can consume stale state."

requirements-completed: [SAFE-12]

duration: 15min
completed: 2026-07-20
---

# Phase 46 Plan 03: STUDY/NOC Adversarial Release Matrix Summary

**Independent production-screen matrix proving STUDY snapshot/provenance and NOC duty states cannot green, including four-screen registry fingerprint replay from snapshot A to B**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-20T17:06:51Z
- **Completed:** 2026-07-20T17:21:17Z
- **Tasks:** 2
- **Files modified:** 1 implementation artifact

## Accomplishments

- Exercised PGWP Yes/current-only, Details, and No controls with independently enumerated SQLite citations and exact six-field STUDY results.
- Covered STUDY evidence, config, index, snapshot, future-date, hash, manifest, citation, selector, and unmanifested-chunk failures with no green result.
- Covered NOC missing/source-unavailable, pending, partial, rejected, Layer-1 stale, Layer-2 drift, superseded-duty, and fully confirmed manual states with no scoring fields.
- Replayed completed MEC, POLICY, STUDY, and NOC state from registry snapshot A against changed snapshot B; fingerprint drift could not reuse evidence or invoke the POLICY sidecar.

## Task Commits

1. **Task 46-03-01: Add independent STUDY snapshot and dynamic-provenance cases**
   - `51b473c` — RED: failing exact STUDY case manifest
   - `7d49cde` — GREEN: independent STUDY production matrix
2. **Task 46-03-02: Add NOC partial/drift/source cases and registry re-green prevention**
   - `550665d` — RED: failing NOC and registry replay manifests
   - `6f7a625` — GREEN: NOC matrix and four-screen A-to-B replay

## Files Created/Modified

- `crawler/tests/test_conformance_v5_release_matrix.py` — Single MEC/POLICY/STUDY/NOC release matrix with independent fixtures, exact case counts, and registry replay.

## Decisions Made

- Retained the production `RegistrySnapshot.fingerprint` as the only registry-drift oracle; no test canonicalizer was added.
- Used copied source directories named `dli` so canonical document coordinates remain production-identical while every mutation stays temporary.
- Kept production modules, dependencies, lock files, and the existing research cache untouched.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The first copied STUDY source root used a label-specific directory name, which correctly failed canonical provenance. The fixture was corrected to preserve the required `dli/` coordinate before task commit.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 46-05 and 46-06 can enroll this complete all-screen matrix in the authoritative release runner.
- Verification is green: release matrix `18 passed, 307 subtests`; STUDY/NOC compatibility `36 passed, 94 subtests`.

## Self-Check: PASSED

The modified matrix, summary, and all four task commits were verified on disk/in git history.

---
*Phase: 46-safe-conformance-release-gate*
*Completed: 2026-07-20*
