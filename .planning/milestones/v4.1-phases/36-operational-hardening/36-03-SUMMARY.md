---
phase: 36-operational-hardening
plan: 03
subsystem: extraction
tags: [crs, extraction, quarantine, adversarial, real-seam, regression, fail-closed, unittest]

# Dependency graph
requires:
  - phase: 30-extraction-quarantine
    provides: "classify_page_quality (scanned/low_text/rotated/password_protected), _normalize_date ambiguous flag, is_audit_eligible quality gate, _DOC_TYPE_FACTOR claimed-only linkage, real import->extract->confirm seam"
provides:
  - "crawler/tests/test_adversarial_extraction_seam.py — real-seam regression proving rotated/low-text/password-protected/ambiguous inputs stay quarantined, no cross-factor contamination, and confirm/correct cannot green an adversarial value"
affects: [phase-39-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Real-seam adversarial regression skip-guarded on corpus/index.db + extraction deps (structural-only on a fresh clone)"
    - "Non-vacuous rotation assertion keys on the PAGE quality flag (rotated==True) since a rotated page extracts no field values"

key-files:
  created:
    - crawler/tests/test_adversarial_extraction_seam.py
  modified: []

key-decisions:
  - "No production code change needed: the shipped quality gate already quarantines all four adversarial states (confirmed by probe). confirm_value never mutates quality_flag and is_audit_eligible requires quality_flag=='ok', so confirm/correct cannot green a low_quality/ambiguous value"
  - "Rotated fixture uses REAL language content rotated 90deg; the assertion keys on the page rotated flag (a rotated page extracts 0 field values, so 'every value low_quality' would be vacuous) + audit_eligible empty + card not SUBSTANTIATED"
  - "Password-protected fixture = a truncated/unparseable .pdf (raises pdfium.PdfiumError -> password_protected page); an /Encrypt dict does NOT trigger it (pdfium opens it). Quarantine proven by absence (no text -> no values -> nothing eligible)"
  - "make_fixtures.py left untouched; adversarial fixtures built inline via mf.build_pdf"

patterns-established:
  - "Every adversarial extraction state must be locked by a real-seam regression, not just a unit test of classify_page_quality"
---

# Phase 36 Plan 03 — Summary

## What shipped
- `crawler/tests/test_adversarial_extraction_seam.py`: six real-seam regressions (rotated, low-text,
  password-protected/unparseable, ambiguous DOB, no-cross-factor-contamination, confirm/correct-can't-green)
  driving the ACTUAL `import_document → extract_document → confirm_value → run_full_audit_report` path.

## Requirement satisfied
- **HARD-04**: rotated / low-text / password-protected / ambiguous-date fixtures remain quarantined
  (`low_quality`/`ambiguous` → never audit-eligible) and cannot green or contaminate another factor
  through the real seam.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_adversarial_extraction_seam.py -q` → 6 passed.
- Regression cluster (`test_full_audit_real_seam`, `test_extraction`, `test_extract_confirm_cli`,
  `test_auditors_additional`) → 73 passed, no regression.

## Deviations
None. No production code change was required — probes confirmed the shipped quality gate already
quarantines every adversarial state and that confirm/correct cannot bypass it (this plan is a durable
regression net, exactly as scoped). Applied the plan-checker's MED-1/2/3 (real rotated content +
page-flag assertion; truncated-PDF password fixture; eligibility-keyed confirm assertion).
