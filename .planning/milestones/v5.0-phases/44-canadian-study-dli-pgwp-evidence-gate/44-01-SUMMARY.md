---
phase: 44-canadian-study-dli-pgwp-evidence-gate
plan: 01
subsystem: extraction
tags: [study-proof, dli, vault, quarantine, fail-closed]

requires:
  - phase: 30-extraction-quarantine
    provides: Born-pending extraction, per-value confirmation, and five-key eligibility
  - phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
    provides: Exact DLI vocabulary context for later grounded review
provides:
  - Six-field study_proof extraction onto inert review.study
  - Exact DLI and closed credential/status normalization
  - Real-seam quarantine, staleness, and full-grid isolation coverage
affects: [44-03-study-review, 44-04-conformance, 45-mec-sidecar]

tech-stack:
  added: []
  patterns: [inert FK parent, doc-type-locked factor routing, closed alias normalization]

key-files:
  created:
    - crawler/dlifields.py
    - crawler/tests/test_study_review.py
  modified:
    - crawler/models/vault.py
    - crawler/extraction.py

key-decisions:
  - "Study proof factor overrides are ignored so applicant evidence cannot leave inert review.study."
  - "Unknown credential and status labels remain non-accepted tokens; malformed DLI values normalize to null."

patterns-established:
  - "Study evidence is born pending on a dedicated inert FK parent outside FULL_GRID_FACTORS."
  - "Producer vocabulary is import-time set-equal to the shared six-field study vocabulary."

# STUDY requirements intentionally stay pending until Phase 44 closeout.
requirements-completed: []

duration: 5min
completed: 2026-07-19
---

# Phase 44 Plan 01: Canadian-Study Evidence Intake Summary

**Six private study fields now extract as born-pending values onto inert `review.study`, with exact DLI normalization and closed credential/status tokens.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-19T16:51:46Z
- **Completed:** 2026-07-19T16:56:31Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added the six-field `study_proof` vocabulary and typed vault boundary without DDL, migration, dependency, or schema-version changes.
- Added exact NFC/uppercase DLI normalization plus fail-closed credential-tier and study-status alias maps with no scoring literals.
- Proved real import/extraction/vault behavior: pending-by-default, candidate-private linkage, per-field decisions, five-key staleness, quality quarantine, and zero CRS-factor contamination.

## Task Commits

TDD work was committed atomically:

1. **RED: Add failing study quarantine coverage** - `b181c55` (test)
2. **GREEN: Quarantine Canadian study evidence** - `bbb78c4` (feat)

Both commits carry the required `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer.

## Files Created/Modified

- `crawler/dlifields.py` - Closed study vocabulary and fail-closed DLI, credential, and status normalizers.
- `crawler/models/vault.py` - Five additive `FieldName` members; shared `credential_level` remains single.
- `crawler/extraction.py` - Six-field producer, canonicalizer dispatch, inert-parent upsert, and doc-type-locked routing.
- `crawler/tests/test_study_review.py` - Synthetic real-seam quarantine, staleness, confirmation, and isolation tests.

## Decisions Made

- The general extraction factor override cannot redirect `study_proof`; the document type remains locked to `review.study`.
- The shared vocabulary module carries accepted tokens only. It performs no freshness, points, program eligibility, or legal inference.
- STUDY-02 remains unchecked in `REQUIREMENTS.md` until Phase 44 closeout, as required.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_study_review.py -q -k "extract or field or confirm or quarantine or contamination"` — 12 passed, 49 subtests passed.
- `.venv/bin/python -m pytest crawler/tests/test_study_review.py -q` — 12 passed, 49 subtests passed.
- `.venv/bin/python -m pytest crawler/tests/test_extraction.py crawler/tests/test_siblingfields_vocab.py crawler/tests/test_vault.py crawler/tests/test_full_audit_real_seam.py -q` — 54 passed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no dependencies, services, or configuration were added.

## Known Stubs

None.

## TDD Gate Compliance

- RED commit `b181c55` produced the expected collection error because `crawler.dlifields` did not yet exist.
- GREEN commit `bbb78c4` followed and made the complete focused and regression suites pass.

## Next Phase Readiness

- The quarantined intake surface is ready for Plan 44-03's candidate-scoped grounded review.
- No audit decision, `additional.study` projection, migration, dependency, or Phase-45 wiring was introduced.
- STUDY requirements remain pending until Phase 44 closeout.

## Self-Check: PASSED

- Created files exist: `crawler/dlifields.py`, `crawler/tests/test_study_review.py`.
- Task commits exist: `b181c55`, `bbb78c4`.
- No tracked file deletion occurred.
- Modified-file scan found no goal-blocking stubs or unplanned threat surface.

---
*Phase: 44-canadian-study-dli-pgwp-evidence-gate*
*Completed: 2026-07-19*
