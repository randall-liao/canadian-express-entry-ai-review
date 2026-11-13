---
phase: 44-canadian-study-dli-pgwp-evidence-gate
plan: 03
subsystem: audit
tags: [study-review, dli, pgwp, grounding, transient-rules, fail-closed]

requires:
  - phase: 44-01
    provides: Candidate-scoped quarantined review.study evidence
  - phase: 44-02
    provides: Explicit no-default snapshot max-age boundary
  - phase: 41
    provides: Pinned DLI/PGWP corpus family and real index
provides:
  - Candidate-scoped Canadian-study sidecar with one transient RuleRow per consumed DLI chunk
  - Shared validate-and-retrieve gate enforcement for every consumed non-gap row
  - Grounded inert R73 definition and credential-only never-green CRS decider
affects: [44-04-study-cli-conformance, 45-mec-sidecar]

tech-stack:
  added: []
  patterns: [transient in-memory registry, exact chunk discovery, private evidence report, common provenance]

key-files:
  created:
    - crawler/study_review.py
    - crawler/tests/test_study_review_audit_seam.py
  modified:
    - crawler/auditor.py
    - crawler/auditors/additional.py
    - crawler/data/crs_rules/study_dli.yaml
    - crawler/tests/test_gate_subset.py
    - crawler/tests/test_study_review.py
    - crawler/tests/test_auditors_additional.py

key-decisions:
  - "Exact DLI resolution discovers candidate chunks, but only the shared validate/retrieve gate accepts their transient rows."
  - "The static UofT designation row remains fixture-only; runtime review uses candidate-specific transient rows."
  - "The db-free additional.study decider remains credential-only and always returns GAP or AT-RISK with no points."

patterns-established:
  - "Every consumed #000/#001+ chunk has one strict transient row and one private dynamic-citation entry."
  - "Public study output is a closed six-field projection; applicant evidence and citations remain vault-only."

# STUDY requirements intentionally remain pending until Phase 44 closeout.
requirements-completed: []

duration: 14min
completed: 2026-07-19
---

# Phase 44 Plan 03: Grounded Canadian-Study Review Summary

**Candidate-specific DLI/PGWP chunks now cross one strict transient-row validate/retrieve gate, while common provenance and current-only limits keep every study path fail-closed and private evidence vault-only.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-19T17:03:18Z
- **Completed:** 2026-07-19T17:17:11Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Added `review_study(..., max_age_days=int)` with positive-int preflight, candidate/factor/field-scoped five-key eligibility, exact multi-chunk discovery, strict transient rows, common `crawl_date`, and a closed public result.
- Strengthened `auditor.gate_subset` to require both `validate_registry` and `retrieve_what_you_cite`, including selection, citation agreement, and grounding for every non-gap row.
- Added the inert grounded `study.r73_definition` row without changing the current-only static designation fixture.
- Closed `decide_study` so a grounded credential tier remains `AT-RISK credential_only_no_designation` with no points.
- Proved UofT Yes, Centre de formation professionnelle de l’Envolée Details, and Eston College No use candidate-specific rows and private citations.

## Task Commits

1. **Task 44-03-01 RED: grounded sidecar and selector controls** — `bf4a923` (test)
2. **Task 44-03-01 GREEN: transient-row study sidecar** — `cdccfd1` (feat)
3. **Task 44-03-02 RED: real audit-seam no-green safeguards** — `53093d5` (test)
4. **Task 44-03-02 GREEN: credential-only fail-closed decider** — `e26d514` (fix)
5. **Shared-gate regression fixture alignment** — `e616ba3` (test)
6. **Governing-row and retrieval refusal hardening** — `65346c7` (fix)

Every commit carries the required `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer.

## Files Created/Modified

- `crawler/study_review.py` — Exact candidate DLI discovery, transient Registry, common provenance, private report, and closed public projection.
- `crawler/data/crs_rules/study_dli.yaml` — Stable R73(1) definition row on a dedicated inert factor.
- `crawler/auditor.py` — One authoritative validate-and-retrieve gate.
- `crawler/auditors/additional.py` — Credential-only study decider with no green/points branch.
- `crawler/tests/test_gate_subset.py` — Real-index quote/marker/family/title tamper controls.
- `crawler/tests/test_study_review.py` — Yes/Details/No, transient-row, private/public, and preflight coverage.
- `crawler/tests/test_auditors_additional.py` — Credential-only no-green matrix, including forced DLI input.
- `crawler/tests/test_study_review_audit_seam.py` — Real `audit_one` and full-grid isolation proof.
- `crawler/tests/test_auditor.py`, `test_auditor_dispatch.py`, `test_auditors_spouse.py` — Synthetic selectors made non-vacuous for the strengthened shared gate.

## Decisions Made

- Candidate-specific DLI and PGWP observations are never serialized as registry YAML or persisted as rules; they exist only as strict in-memory rows.
- `as_of` is exactly the common nonempty `crawl_date` across every dynamic row, never wall-clock, manifest, or static-row time.
- Current designation and PGWP table observations cannot prove historical designation or program eligibility; even the complete Yes path terminates at `designation_historical_unproven`.
- `review.study` remains isolated from `additional.study`; no Phase-45 projection or `DecisionContext` expansion was added.
- STUDY-03/04 remain pending until Phase 44 closeout, as requested.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Made legacy synthetic auditor selectors non-vacuous**
- **Found during:** Task 44-03-02 regression verification
- **Issue:** Legacy synthetic rows cited the intended tiny chunk but their marker-free query selected an adjacent heading first under the newly authoritative retrieve-what-you-cite gate.
- **Fix:** Added the existing verbatim fixture quote as the selector marker; production behavior and non-study verdicts remain unchanged.
- **Files modified:** `crawler/tests/test_auditor.py`, `crawler/tests/test_auditor_dispatch.py`, `crawler/tests/test_auditors_spouse.py`
- **Verification:** All auditor/full-grid regressions passed: 83 tests and 8 subtests.
- **Commits:** `e26d514`, `e616ba3`

**2. [Rule 1 - Bug] Tightened dedicated R73 and incomplete retrieval refusal**
- **Found during:** Final Task 44-03-01 contract review
- **Issue:** The first implementation placed R73 on the general review factor and only inspected retrieval entries returned by the report, which could miss an omitted non-gap row.
- **Fix:** Moved R73 to `study.r73_definition`, validated both governing-row shapes, and enumerated every non-gap Registry row against the retrieval report.
- **Files modified:** `crawler/data/crs_rules/study_dli.yaml`, `crawler/study_review.py`, `crawler/auditor.py`, `crawler/tests/test_study_review.py`
- **Verification:** Both plan gates and all non-study auditor regressions passed.
- **Commit:** `65346c7`

---

**Total deviations:** 2 auto-fixed (1 blocking fixture alignment, 1 correctness hardening).
**Impact on plan:** Both fixes enforce the revised authoritative-gate contract without widening production scope.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_gate_subset.py crawler/tests/test_study_review.py crawler/tests/test_auditors_additional.py crawler/tests/test_study_review_audit_seam.py -q` — 46 passed, 67 subtests passed.
- `.venv/bin/python -m pytest crawler/tests/test_gate_subset.py crawler/tests/test_dli_grounding.py crawler/tests/test_conformance_v40_retrieve_what_you_cite.py -q` — 35 passed, 1 skipped, 42 subtests passed.
- `.venv/bin/python -m pytest crawler/tests/test_auditor*.py crawler/tests/test_full_audit*.py -q` — 83 passed, 8 subtests passed.
- `.venv/bin/python scripts/check_publish_safe.py` — 444 tracked files scanned, 0 violations.
- DLI corpus and index sizes/mtimes remained unchanged; `.planning/research/.cache/` remained untouched.

## Known Stubs

None.

## Issues Encountered

None remaining.

## TDD Gate Compliance

- Task 44-03-01 RED commit `bf4a923` failed because `crawler.study_review` did not exist; GREEN followed in `cdccfd1`.
- Task 44-03-02 RED commit `53093d5` exposed the credential-only false green; GREEN followed in `e26d514`.

## User Setup Required

None - no dependency, schema, network, or configuration surface was added.

## Next Phase Readiness

- Plan 44-04 can wire the explicit max-age CLI boundary to `review_study` and exercise exhaustive conformance.
- The static UofT fixture remains registry coverage only, dynamic evidence remains private, and no Phase-45 wiring exists.

## Self-Check: PASSED

- Created files exist: `crawler/study_review.py`, `crawler/tests/test_study_review_audit_seam.py`, and this summary.
- Task and auto-fix commits `bf4a923`, `cdccfd1`, `53093d5`, `e26d514`, `e616ba3`, and `65346c7` exist.
- No tracked file deletion occurred; modified-file scan found no goal-blocking stub or unplanned threat surface.

---
*Phase: 44-canadian-study-dli-pgwp-evidence-gate*
*Completed: 2026-07-19*
