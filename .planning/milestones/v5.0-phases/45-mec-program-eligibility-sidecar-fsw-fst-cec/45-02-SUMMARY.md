---
phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
plan: 02
subsystem: eligibility-screening
tags: [mec, pydantic, registry-snapshot, grounding, pii, sidecars]

requires:
  - phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
    plan: 01
    provides: Exact grounded FSW/FST/CEC registry, immutable snapshot, effectivity, and freshness helpers
provides:
  - Strict public/private MEC status and reason contracts
  - Canonical FAIL-first conservative program rollup
  - Exact policy-value-free criterion manifests with grounded N/A declarations
  - Snapshot-bound MEC gate context using auditor.gate_subset
  - Read-only snapshot-injected NOC and study composition
affects: [45-03, 45-04, mec-evaluators, mec-cli, conformance-v5]

tech-stack:
  added: []
  patterns: [explicit PII-light projection, FAIL-first rollup, caller-owned immutable snapshot, read-only sidecar composition]

key-files:
  created:
    - crawler/models/mec.py
    - crawler/mec_screen.py
    - crawler/tests/test_mec_screen.py
  modified:
    - crawler/noc_review.py
    - crawler/study_review.py
    - crawler/tests/test_noc_review.py
    - crawler/tests/test_study_review.py
    - crawler/tests/test_study_review_audit_seam.py

key-decisions:
  - "A typed deterministic FAIL controls the program outcome before unrelated unresolved criteria; all unknown, missing, duplicate, unwired, or invalid-N/A states otherwise become AT-RISK."
  - "MEC, NOC, and study retain the caller's RegistrySnapshot fingerprint without reload or recomputation; every grounded subset uses crawler.auditor.gate_subset."
  - "Study composition exposes fingerprint metadata only as a non-serializing result attribute and suppresses invalidation, report writes, and temporary artifacts in read-only/no-report mode."
  - "MEC-01 through MEC-04 remain pending until evaluator, publication, and CLI plans complete their end-to-end outcomes."

patterns-established:
  - "Public MEC output is constructed field-by-field from private models and rejects evidence IDs, free-form reasons, extra fields, absolute paths, and traversal paths."
  - "MecGateContext is frozen and retains the exact snapshot object, selected row identities, fingerprint, reference date, max age, and per-row usability reason."

requirements-completed: []

duration: 16min
completed: 2026-07-20
---

# Phase 45 Plan 02: MEC Contracts and Immutable Composition Summary

**Strict PII-light MEC contracts with deterministic FAIL-first rollup and read-only NOC/study composition over one caller-owned registry snapshot**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-20T03:35:11Z
- **Completed:** 2026-07-20T03:51:10Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added exact criterion and program status vocabularies, a closed PII-light reason enum, strict private/public models, and an explicit projection that drops applicant values, evidence IDs, employers, NOCs, funds data, dates, and absolute paths.
- Added complete ordered FSW/FST/CEC criterion manifests, grounded conditional-N/A metadata, and conservative rollup where deterministic FAIL wins over AT-RISK while malformed or incomplete input cannot MEETS.
- Added frozen snapshot-bound MEC gate preparation with exact wiring checks, shared grounding, effectivity, operational freshness, and per-row usability.
- Threaded one injected fingerprint through every NOC five-key eligibility read and added injected study read-only/no-report composition with no reload, invalidation, report, or temporary artifact.
- Preserved PublicAuditEnvelope, CRS totals, cards, cutoffs, and policy-offer source unchanged.

## Task Commits

Each TDD task was committed atomically with the required trailer:

1. **Task 45-02-01 RED: strict MEC contracts and rollup tests** - `188fe02` (test)
2. **Task 45-02-01 GREEN: typed contracts and canonical FAIL-first rollup** - `c432b8e` (feat)
3. **Task 45-02-02 RED: immutable snapshot composition tests** - `6924c94` (test)
4. **Task 45-02-02 GREEN: shared-gate read-only sidecar composition** - `872807c` (feat)

## Files Created/Modified

- `crawler/models/mec.py` - Closed criterion/program vocabularies, strict private/public reports, safe paths, and allowlist projection.
- `crawler/mec_screen.py` - Exact manifests, frozen gate context, row usability, and canonical rollup.
- `crawler/noc_review.py` - Optional snapshot/fingerprint injection propagated to all audit-eligibility checks.
- `crawler/study_review.py` - Injected snapshot reuse, non-serializing fingerprint propagation, and read-only/no-report mode.
- `crawler/tests/test_mec_screen.py` - Status, reason, projection, manifest, rollup, N/A, loader, identity, and gate tests.
- `crawler/tests/test_noc_review.py` - Fingerprint propagation, no-reload, and drift refusal tests.
- `crawler/tests/test_study_review.py` - Loader-count-one, shared-gate identity, read-only artifact identity, fingerprint, and PII tests.
- `crawler/tests/test_study_review_audit_seam.py` - Order-independent frozen CRS isolation setup.

## Decisions Made

- Kept manifest metadata structural: criterion IDs, exact rule IDs, and named applicability branches only; policy values remain exclusively in cited registry payloads.
- Treated `FAIL` as the typed representation of a confirmed deterministic violation. Invalid raw statuses fail model validation and become unresolved when passed to rollup.
- Allowed N/A only for a manifest-declared conditional criterion with a grounded applicability result that is deterministically false.
- Kept direct study CLI behavior unchanged by default; either `read_only=True` or `no_report=True` activates artifact suppression for composition.
- Left all four phase requirements pending because this plan establishes contracts and composition seams but does not yet deliver evaluators, publication, or the command boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Made the direct study audit seam independent of test import order**
- **Found during:** Task 45-02-02 overall verification
- **Issue:** Two existing direct `audit_one` assertions depended on another test module having already registered auditor deciders, so the required suite failed in isolation with `unaudited_factor`.
- **Fix:** Explicitly invoked the established idempotent `auditors.load_all()` test setup before exercising the low-level spine.
- **Files modified:** `crawler/tests/test_study_review_audit_seam.py`
- **Verification:** The seam passes alone and as part of the complete four-file verification suite.
- **Committed in:** `872807c`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix only removed order dependence from an in-scope test; no production CRS or envelope behavior changed.

## Issues Encountered

- The initial full verification exposed the order-dependent audit seam above; no implementation failures remained after correcting its setup.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_mec_screen.py crawler/tests/test_noc_review.py crawler/tests/test_study_review.py crawler/tests/test_study_review_audit_seam.py -q` - 85 passed, 122 subtests passed.
- `.venv/bin/python -m pytest crawler/tests/test_audit_models.py crawler/tests/test_json_contract.py -q` - 41 passed, 1 skipped.
- Protected-file diff confirmed no changes to `crawler/contract.py`, `crawler/models/audit.py`, `crawler/crs_audit.py`, or `crawler/auditors/`.
- `.venv`, `.planning/research/.cache/`, dependency files, and requirements tracking were left untouched.

## User Setup Required

None - no dependencies, external services, or configuration were added.

## Next Phase Readiness

- Plan 45-03 can build FSW/FST/CEC evaluators against the strict criterion contracts and snapshot-bound gate context.
- Plan 45-04 can publish only `PublicMecSummary` after durable private publication and wire the one-snapshot CLI boundary.
- MEC-01, MEC-02, MEC-03, and MEC-04 remain pending until those end-to-end plans complete.

## Self-Check: PASSED

All eight implementation/test files, the summary, and all four TDD task commits were verified on disk.

---
*Phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec*
*Completed: 2026-07-20*
