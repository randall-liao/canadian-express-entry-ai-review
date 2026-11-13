---
phase: 48-synthetic-data-generation-agent-self-improvement-loop
plan: 01
subsystem: synthetic-data
tags: [synthetic, reportlab, Pillow, pdfplumber, pypdfium2, pytesseract, pypdf, express-entry, ground-truth, defect-injection]

requires:
  - phase: 47-canonical-agents-md-multi-cli-adapter-layer
    provides: Canonical agents system prompts and multi-CLI adapter layer

provides:
  - crawler/synthetic/ package with schemas for all 22 Express Entry document types + LoE
  - Defect injection taxonomy (DefectCategory) and parametric mutators (inject_defect)
  - GroundTruthSpec model for evaluation benchmark harness

affects:
  - 48-02-PLAN.md
  - crawler/eval/benchmark_runner.py
  - crawler/eval/self_optimizer.py

tech-stack:
  added:
    - reportlab>=5.0.0
    - Pillow>=12.3.0
    - pdfplumber>=0.11.10
    - pypdfium2>=5.11.0
    - pytesseract>=0.3.13
    - pypdf>=6.14.2
  patterns:
    - Strongly typed dataclasses for applicant profiles and Express Entry document types
    - Parametric defect injection returning (mutated_doc, GroundTruthSpec)

key-files:
  created:
    - crawler/synthetic/__init__.py
    - crawler/synthetic/schemas.py
    - crawler/synthetic/defects.py
  modified:
    - pyproject.toml

key-decisions:
  - "Added synthetic optional-dependency group to pyproject.toml covering ReportLab, Pillow, pdfplumber, pypdfium2, pytesseract, and pypdf."
  - "Defined ExpressEntryDocType enum covering all 22 Express Entry e-APR supporting document types plus Letters of Explanation (LoE)."
  - "Defined DefectCategory taxonomy covering 6 core post-ITA document defect types: missing_mandatory_field, unencumbered_funds_violation, expired_credential, date_mismatch, police_cert_gap, loe_unsubstantiated_claim."

patterns-established:
  - "Defect injection mutator inject_defect returns a copy of SyntheticDocument paired with a GroundTruthSpec evaluation object."

requirements-completed:
  - SELF-01

duration: 10min
completed: 2026-07-21
---

# Phase 48 Plan 01 Summary

**Established the `crawler/synthetic/` package with strongly typed dataclasses for all 22 Express Entry document types plus Letters of Explanation, GroundTruthSpec evaluation models, and parametric defect injection taxonomy.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-21T23:44:00-04:00
- **Completed:** 2026-07-21T23:54:00-04:00
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Configured optional dependency group `synthetic` in `pyproject.toml` including `reportlab`, `Pillow`, `pdfplumber`, `pypdfium2`, `pytesseract`, and `pypdf`.
- Created `crawler/synthetic/__init__.py`, `crawler/synthetic/schemas.py`, and `crawler/synthetic/defects.py`.
- Defined `ExpressEntryDocType` enum covering all 22 Express Entry e-APR supporting document types plus Letters of Explanation (LoE).
- Defined `GroundTruthSpec`, `SyntheticProfile`, `SyntheticDocument`, and `InjectedDefect` models along with `DefectCategory` enum.
- Implemented `inject_defect(doc, defect_category)` mutator for parametric defect injection.
- Verified python importability via `.venv/bin/python -c "from crawler.synthetic.schemas import GroundTruthSpec; from crawler.synthetic.defects import DefectCategory, inject_defect; print('Plan 01 Verification Passed')"`.

## Files Created/Modified
- `pyproject.toml` — Added `synthetic` optional dependencies group.
- `crawler/synthetic/__init__.py` — Package initialization for synthetic data generation.
- `crawler/synthetic/schemas.py` — Dataclasses for 22 Express Entry doc types, LoE, applicant profiles, and ground-truth specs.
- `crawler/synthetic/defects.py` — `DefectCategory` enum, `InjectedDefect` model, and `inject_defect` parametric mutators.

## Decisions Made
- Organized all 22 Express Entry document types plus LoE into `ExpressEntryDocType` enum and dedicated typed dataclasses to ensure strict schema validation and full coverage.
- Placed `InjectedDefect` in `schemas.py` and re-exported in `defects.py` to prevent circular imports between modules.

## Deviations from Plan
None - plan executed exactly as specified.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `crawler/synthetic/` foundational schemas and defect taxonomy are ready for Plan 02 (generator, rasterizer, benchmark runner, and self-optimizer).

---
*Phase: 48-synthetic-data-generation-agent-self-improvement-loop*
*Completed: 2026-07-21*
