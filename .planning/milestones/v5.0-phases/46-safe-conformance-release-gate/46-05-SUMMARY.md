---
phase: 46-safe-conformance-release-gate
plan: 05
subsystem: testing
tags: [e2e, confirmed-vault, mec, study, noc, policy, privacy, drift]
requires:
  - phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
    provides: pinned DLI family, manifest, and indexed lineage
  - phase: 43-enhanced-noc-work-duty-review-worksheet
    provides: grounded NOC worksheet and manual review
  - phase: 44-canadian-study-dli-pgwp-evidence-gate
    provides: confirmed-vault STUDY review
  - phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
    provides: MEC composition and atomic publication
  - phase: 46-safe-conformance-release-gate
    provides: grounded release matrix and privacy contracts from Plans 01, 03, and 04
provides:
  - Real pending-to-confirmed cross-phase vault E2E under one immutable registry fingerprint
  - Authoritative no-skip checks for index, DLI lineage, canonical files/chunks, and confirmed fixture
  - Registry/index drift replay that refuses stale evidence and preserves private LKG bytes
affects: [46-06, SAFE-12, release-conformance]
tech-stack:
  added: []
  patterns:
    - authoritative prerequisite helper with stable path-free logical labels
    - read-only drift replay across production composition boundaries
key-files:
  created:
    - .planning/phases/46-safe-conformance-release-gate/46-05-SUMMARY.md
  modified:
    - crawler/tests/test_conformance_v5_privacy_release.py
key-decisions:
  - "Load one RegistrySnapshot before fixture construction and bind every confirmation and screen to that exact fingerprint."
  - "Validate every DLI manifest file plus indexed DLI relpath in authoritative mode; missing resources fail with logical path-free labels."
  - "Replay drift through no-report production paths so refusal cannot overwrite snapshot-A MEC, STUDY, or CRS artifacts."
patterns-established:
  - "Cross-phase fixtures use one imported document, extraction run, page render, and evidence ID per manually confirmed field."
  - "Snapshot-B tests prove both registry fingerprint drift and copied-index provenance drift are non-vacuous before asserting refusal."
requirements-completed: [SAFE-12]
duration: 13min
completed: 2026-07-20
---

# Phase 46 Plan 05: Confirmed-Vault Release E2E Summary

**A real distinct-evidence vault now drives MEC, POLICY, STUDY, NOC, frozen CRS, and public projection offline, while authoritative prerequisites and post-success registry/index drift fail closed without replacing private outputs.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-20T17:24:06Z
- **Completed:** 2026-07-20T17:37:05Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Created 16 distinct imported documents whose values are observed pending and explicitly confirmed with unique evidence, file, render, and extraction identities under one production registry fingerprint.
- Drove real FSW MEC composition/publication, POLICY zero-point handling, pinned STUDY review, grounded NOC generation/review, full CRS audit, and PublicAuditEnvelope projection against the local index and DLI lineage.
- Proved literal public field/status/reason/count contracts, grounded citations, non-zero MEC/CRS/NOC reachability, byte-identical CRS results after sidecars, and complete PII/evidence/path containment.
- Made index, DLI family/manifest/files/chunks, and confirmed-fixture prerequisites fail rather than skip under `PR_CONFORMANCE_RUNNER=1`.
- Replayed the same confirmed evidence against an independently changed registry snapshot and copied DLI index, proving closed outcomes, no replacement publication, and byte-identical snapshot-A LKG files.

## Task Commits

1. **Task 46-05-01 RED: failing confirmed-vault E2E manifest** - `90402c2` (test)
2. **Task 46-05-01 GREEN: real confirmed-vault cross-phase flow** - `aacd853` (feat)
3. **Task 46-05-02 RED: failing prerequisite/drift manifest** - `35d9742` (test)
4. **Task 46-05-02 GREEN: authoritative prerequisites and drift refusal** - `8402e31` (feat)

## Files Created/Modified

- `crawler/tests/test_conformance_v5_privacy_release.py` - Real confirmed-vault E2E, authoritative prerequisite enforcement, copied-index/registry drift replay, and LKG/privacy assertions.

## Decisions Made

- Used FSW as the MEC composition path because it exercises POLICY and STUDY sidecars while retaining independent real NOC review and frozen CRS boundaries.
- Kept all expected statuses, reasons, key sets, dates, criteria counts, duty counts, and citations as literals rather than deriving expectations from production builders.
- Exercised snapshot-B refusals through read-only/no-report entry points; a refusal is not allowed to invalidate or replace the already successful snapshot-A artifacts.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the literal MEC public schema oracle**
- **Found during:** Task 46-05-01
- **Issue:** The initial independent key-set oracle omitted the existing `screening_notice` field.
- **Fix:** Added the field literally and reran the real E2E.
- **Files modified:** `crawler/tests/test_conformance_v5_privacy_release.py`
- **Verification:** Confirmed-vault target passed.
- **Committed in:** `aacd853`

**2. [Rule 2 - Missing Critical] Routed existing local-only checks through authoritative prerequisites**
- **Found during:** Task 46-05-02
- **Issue:** Two pre-existing real-index checks still used `skipUnless`, which could record prerequisite skips in release mode.
- **Fix:** Routed those checks through the same release-aware helper used by the E2E.
- **Files modified:** `crawler/tests/test_conformance_v5_privacy_release.py`
- **Verification:** Authoritative module completed with 17 passed, 1192 subtests, and zero skips.
- **Committed in:** `8402e31`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both changes enforce exact contract and no-skip correctness without production, dependency, environment, or cache changes.

## Issues Encountered

- Snapshot-B POLICY and core-age production paths use their existing closed reasons (`arranged_employment_current` and `missing_evidence`) after stale evidence is filtered; literal assertions also require empty evidence IDs to prove prior evidence was not consumed.

## Known Stubs

None. Empty collections found by the scan are deliberate refusal or test-initialization states, not unwired release behavior.

## Authentication Gates

None.

## User Setup Required

None - execution used the existing `.venv` and local corpus only; no network, dependency install, or external service was required.

## Verification

- `PR_CONFORMANCE_RUNNER=1 .venv/bin/python -m pytest crawler/tests/test_conformance_v5_privacy_release.py -q -x` — 17 passed, 1192 subtests.
- `PR_CONFORMANCE_RUNNER=1 .venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_privacy_release.py -q` — 45 passed, 1499 subtests.
- `.venv/bin/python -m pytest crawler/tests/test_full_audit_integration.py -q` — 10 passed.

## Next Phase Readiness

- Plan 46-06 can enroll the complete bounded v5 suite in the one-command authoritative runner.
- `.venv` and `.planning/research/.cache/` were not modified.

## Self-Check: PASSED

The modified test file, summary, and all four task commits were verified on disk/in git history.

---
*Phase: 46-safe-conformance-release-gate*
*Completed: 2026-07-20*
