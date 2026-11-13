---
phase: 30-extraction-quarantine-field-confirmation
plan: 04
subsystem: testing
tags: [doctor, preflight, publish-safe, conformance, pii-perimeter, contract, extraction]

# Dependency graph
requires:
  - phase: 30-01
    provides: "is_audit_eligible / is_stale gate for the conformance matrix"
  - phase: 30-02
    provides: "extraction engine + classify_page_quality + MissingExtractionDependency + artifact paths"
  - phase: 30-03
    provides: "vault extract/fields/confirm CLI verbs + confirm.build_field_view"
  - phase: 29-candidate-vault-pii-perimeter
    provides: "scripts/check_publish_safe.py scanner + PII-perimeter test pattern + CONTRACT.md"
provides:
  - "crawler/doctor.py + top-level `doctor` CLI verb (dependency + scan-quality preflight, EXTRACT-05)"
  - "Publish-safe coverage of extraction artifacts (files/rendered, files/text) — unstageable"
  - "Phase-30 SC1-SC5 conformance suite with adversarial fixtures + no-PII-to-stdout gate"
  - "CONTRACT.md documentation for the additive doctor/extract/fields/confirm verbs"
affects: [phase-31-rule-registry, phase-32-auditor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Doctor preflight reuses the engine's lazy dependency probes + persisted quality_json (no re-render)"
    - "Required-dep absence -> missing_dependency/exit 3; optional OCR absence -> reported warning"
    - "Milestone conformance gate: adversarial matrix proves fail-closed audit-eligibility"

key-files:
  created:
    - crawler/doctor.py
    - crawler/tests/test_doctor.py
    - crawler/tests/test_extraction_pii_perimeter.py
    - crawler/tests/test_extraction_conformance.py
  modified:
    - crawler/cli.py
    - scripts/check_publish_safe.py
    - crawler/CONTRACT.md

key-decisions:
  - "doctor is a TOP-LEVEL command (peer of vault); scan-quality problems are surfaced but never fail the exit code"
  - "VAULT_SUBTREES lists files/rendered/ + files/text/ explicitly (self-documenting vs engine paths; already matched by bare rendered/ text/) — no scanner behaviour weakened"
  - "Adversarial SC3 matrix uses directly-inserted synthetic rows + Plan-02 fixtures; all state under $PR_PERSONAL_DIR tmp"

patterns-established:
  - "run_doctor(candidate, document_id) combines dep preflight + per-document scan-quality report"
  - "Conformance no-PII gate concatenates every --json stdout envelope and asserts no fake value/path leaks"

requirements-completed: [EXTRACT-05, EXTRACT-01, EXTRACT-02, EXTRACT-03, EXTRACT-04]

# Metrics
duration: ~55min
completed: 2026-07-06
---

# Phase 30 Plan 04: Doctor, Publish-Safe Perimeter & Conformance Summary

**A top-level `doctor` preflight that reports the required/optional extraction dependencies + per-document scan-quality flags (missing required dep → `missing_dependency`/exit 3, never a silent crash), publish-safe coverage of the new rendered-image/OCR-text artifacts, and a milestone SC1–SC5 conformance gate with adversarial fixtures proving no pending/low-quality/ambiguous/stale value is ever audit-eligible and no extraction PII reaches stdout.**

## Performance

- **Duration:** ~55 min
- **Started:** 2026-07-06T10:10:00Z
- **Completed:** 2026-07-06T11:05:00Z
- **Tasks:** 3 (all TDD)
- **Files modified:** 7

## Accomplishments
- **EXTRACT-05 (doctor)**: `corpus-crawler doctor` reports `pypdfium2`/`Pillow`/`pdfminer.six` as required (with install hints) and `pytesseract` + the `tesseract` binary as optional; a missing REQUIRED dep is `missing_dependency`/exit 3 (never `internal_error`); an absent optional OCR stack is a reported warning. `doctor --candidate --document-id` surfaces per-page scan-quality (scanned/rotated/password-protected/low-text) counts from the persisted `quality_json` without re-rendering.
- **PII perimeter**: rendered page images (`files/rendered/`), OCR/extracted text (`files/text/`), and value/confirmation exports are `VAULT_ARTIFACT`-flagged and unstageable (`git add -A` can't stage them under the project `.gitignore`); the tracked tree scans publish-safe with 0 violations.
- **Milestone conformance gate**: SC1–SC5 proven end-to-end with adversarial synthetic fixtures (CLB 8/9 boundary, IELTS listening/reading swap, ambiguous date, NOC-from-footer, low-text scan, all four staleness triggers) — no pending/rejected/low_quality/ambiguous/stale value is ever audit-eligible; a cross-verb no-PII assertion proves no fake raw value/path appears on any `--json` envelope.
- **CONTRACT.md**: documents the additive `vault extract`/`fields`/`confirm` verbs + a top-level `doctor` section; the 5-key envelope and `schema_version "1.0"` are explicitly unchanged.

## Task Commits

1. **Task 1: doctor/preflight** — `46e46cc` (test) → `57e7502` (feat)
2. **Task 2: publish-safe perimeter + explicit coverage** — `f700644` (test + scanner)
3. **Task 3: SC1-SC5 conformance suite + CONTRACT docs** — `0bc2af8` (test + docs)

## Files Created/Modified
- `crawler/doctor.py` - NEW: probe_dependencies, scan_quality_report, run_doctor, DepStatus/DoctorReport.
- `crawler/cli.py` - Added top-level `doctor` subparser + `_cmd_doctor`; metavar → includes `doctor`.
- `scripts/check_publish_safe.py` - `VAULT_SUBTREES` lists `files/rendered/` + `files/text/` explicitly (self-documenting; no behaviour weakened).
- `crawler/CONTRACT.md` - vault extract/fields/confirm rows + doctor section; envelope/schema_version unchanged.
- `crawler/tests/test_doctor.py` - NEW: 7 doctor tests.
- `crawler/tests/test_extraction_pii_perimeter.py` - NEW: 5 perimeter tests (flagged/unstageable/engine-stays-in-vault/tree-clean).
- `crawler/tests/test_extraction_conformance.py` - NEW: SC1-SC5 + adversarial matrix + no-PII gate.

## Decisions Made
- `doctor` is a top-level command; scan-quality problems are surfaced but never change the exit code (surfacing them is the point).
- The publish-safe scanner already covered the engine paths via the bare `rendered/`/`text/` subtrees + `candidates` segment; the explicit `files/rendered/`/`files/text/` entries are additive and self-documenting.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- One conformance assertion initially expected the whole label line as the raw value for a numeric field; corrected to expect the numeric token (`"8.5"`), which is what the extractor stores as `raw_text`. Test-only fix; no implementation change.

## User Setup Required
None required. Optional local OCR (`tesseract-ocr` OS package) remains opt-in; its absence is now explicitly reported by `doctor` (confirmed: `tesseract` binary absent in this environment, reported as a non-failing optional warning).

## Next Phase Readiness
- Phase 30 ships fail-closed and PII-contained: full suite green (475 passed, 1 skipped, 122 subtests), publish-safe 0 violations, doctor ok.
- Phase 31 (grounded CRS rule registry) can bump `rule_registry_version` to drive SC4 re-confirmation; Phase 32 auditors consume `vault.audit_eligible_values` only.

---
*Phase: 30-extraction-quarantine-field-confirmation*
*Completed: 2026-07-06*

## Self-Check: PASSED
- All created/modified files present on disk.
- All 4 task commits present in git history.
- Final verification green: full suite 475 passed / 1 skipped / 122 subtests; publish-safe 0 violations; doctor overall=ok (exit 0).
