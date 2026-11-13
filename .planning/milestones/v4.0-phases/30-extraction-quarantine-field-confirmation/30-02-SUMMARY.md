---
phase: 30-extraction-quarantine-field-confirmation
plan: 02
subsystem: extraction
tags: [pypdfium2, pillow, pdfminer, pytesseract, ocr, pdf, extraction, poetry]

# Dependency graph
requires:
  - phase: 30-01
    provides: "vault schema v2 store (add_extracted_value forced-pending, record_extraction_run, add_document_page), current_parser_version consumer"
  - phase: 29-candidate-vault-pii-perimeter
    provides: "content-addressed documents + paths.resolve_within vault anchor"
provides:
  - "crawler/extraction.py: render (pypdfium2) + text-first (pdfminer.six) + normalize (Pillow) + optional OCR (pytesseract) pipeline"
  - "PARSER_VERSION single source of truth consumed by SC4 staleness"
  - "Deterministic EXTRACT-01 field extractors writing pending values with structural normalization"
  - "classify_page_quality (scanned/low_text/rotated/password_protected) + MissingExtractionDependency typed error"
  - "doc-extract + ocr Poetry extras; synthetic reportlab-free PDF/image fixture generator"
affects: [30-03-confirmation-cli, 30-04-doctor-conformance, phase-31-rule-registry]

# Tech tracking
tech-stack:
  added:
    - "pypdfium2 5.11.0 (doc-extract extra) — PDF page renderer, prebuilt wheels, no Poppler"
    - "Pillow 12.3.0 (doc-extract extra) — image normalization / OCR handoff"
    - "pdfminer.six 20260107 (doc-extract extra) — first-tier born-digital text"
    - "pytesseract 0.3.13 (ocr extra, opt-in) — local Tesseract wrapper"
  patterns:
    - "Lazy heavy-lib importers (_import_pdfium/_import_pil/_import_pdfminer/_import_pytesseract) raising typed MissingExtractionDependency"
    - "Render-every-page (never page-one-only) with content-hash render cache"
    - "Structural-only normalization (ISO dates/numbers/NOC) — no CLB/points at extraction"
    - "Vault-anchored artifact writes via resolve_within(files/rendered, files/text)"

key-files:
  created:
    - crawler/extraction.py
    - crawler/tests/test_extraction.py
    - crawler/tests/fixtures/extraction/make_fixtures.py
    - crawler/tests/fixtures/__init__.py
    - crawler/tests/fixtures/extraction/__init__.py
  modified:
    - pyproject.toml
    - poetry.lock

key-decisions:
  - "Extraction libs are Poetry extras (doc-extract/ocr), never core dependencies — the lean CLI still imports/runs without them"
  - "Reportlab-free hand-rolled PDF writer generates synthetic fixtures at test time (no committed binaries, no real PII)"
  - "Values linked to the first existing factor of a field's CRS group (extraction never creates factors) so Plan 03 can show affected factor + claim"
  - "OCR invoked ONLY for text-empty pages when pytesseract + tesseract binary present; otherwise page flagged low_quality (never silently skipped)"

patterns-established:
  - "MissingExtractionDependency carries module + extra + install hint (mirrors cli._crawl_extra_hint)"
  - "Ambiguous numeric date (both components <= 12) flagged 'ambiguous', never silently normalized"

requirements-completed: [EXTRACT-01, EXTRACT-02, EXTRACT-05]

# Metrics
duration: ~50min
completed: 2026-07-06
---

# Phase 30 Plan 02: Local Extraction Engine Summary

**Local-only render+read extraction engine (pypdfium2 + pdfminer.six + Pillow, optional pytesseract) that turns vault documents into `pending`-only EXTRACT-01 fields, flags scanned/rotated/low-text/ambiguous quality instead of failing silently, and writes all rendered images/OCR text into the vault only — proven with 11 synthetic-fixture tests.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-07-06T08:25:00Z
- **Completed:** 2026-07-06T09:15:00Z
- **Tasks:** 3 (Task 1 checkpoint auto-approved; Task 2 chore; Task 3 TDD)
- **Files modified:** 7

## Accomplishments
- **EXTRACT-01**: `extract_document` renders EVERY page (pypdfium2 → PIL → normalized PNG), reads embedded text first (pdfminer.six), and proposes structured fields (test type/date/scores, credential/ECA, NOC/TEER/hours/duration/issuer, nomination stream/expiry) — all as `pending` values (EXTRACT-02, 100%).
- **EXTRACT-05 (quality half)**: `classify_page_quality` detects scanned (no embedded text), low_text (sparse), rotated (page `/Rotate` metadata), and password_protected (caught decryption error) — each flags `low_quality`; a genuinely ambiguous date flags `ambiguous`; nothing is silently `ok`.
- **Local stack only**: no cloud OCR/document-AI, no vector/embedding, no heavy-ML, no default PyMuPDF/pdf2image/Poppler. `pypdfium2` needs no system Poppler.
- **PII-in-vault**: rendered PNGs (`files/rendered/<doc>/`) + combined text (`files/text/<doc>.txt`) written via `resolve_within` only; the no-PII test proves fake values never hit stdout and `corpus/` is untouched.
- Content-hash render cache: re-running extraction reuses cached PNGs (rendered_pages=0 on re-run).
- Typed `MissingExtractionDependency` (not opaque ImportError) with install hint.

## Task Commits

1. **Task 1: Supply-chain legitimacy gate** — checkpoint (auto-approved, see Deviations); no code.
2. **Task 2: doc-extract deps + optional ocr extra** — `aa139bb` (chore)
3. **Task 3: Extraction engine** — `4d32f08` (test) → `db9a672` (feat)

## Files Created/Modified
- `crawler/extraction.py` - NEW: full render/text/OCR orchestration + deterministic field extractors + scan-quality classifier + MissingExtractionDependency.
- `crawler/tests/test_extraction.py` - NEW: 11 tests (pipeline, quality flags, cache, missing-dep, PII perimeter).
- `crawler/tests/fixtures/extraction/make_fixtures.py` - NEW: reportlab-free synthetic PDF builder + Pillow image fixtures (FAKE values, generated at test time).
- `crawler/tests/fixtures/__init__.py`, `crawler/tests/fixtures/extraction/__init__.py` - NEW: make the fixture generator importable.
- `pyproject.toml` - Added `doc-extract` + `ocr` optional-dependency extras (extras-only; core deps unchanged).
- `poetry.lock` - Locked pypdfium2 5.11.0, Pillow 12.3.0, pdfminer.six 20260107, pytesseract 0.3.13.

## Decisions Made
- Extraction dependencies are Poetry **extras**, never core `dependencies` (the lean CLI must import/run without them).
- Synthetic fixtures are generated at test time via a hand-rolled PDF writer — no committed binaries, no real PII (PITFALLS-v4.0 Anti-Pattern 4).
- Proposed values auto-link to the first existing factor of the field's CRS group (extraction never creates factors).

## Deviations from Plan

### Auto-approved supply-chain checkpoint (standing authorization)

**1. [Blocking-human checkpoint auto-approved] Extraction-stack supply-chain legitimacy gate (Task 1)**
- **Found during:** Task 1 (blocking-human gate, `gate="blocking-human"`)
- **Context:** Task 1 is a package-legitimacy checkpoint that normally halts for human confirmation. The orchestrator provided explicit STANDING USER AUTHORIZATION to auto-approve this specific supply-chain checkpoint and proceed without questions.
- **Basis:** All four packages are pre-vetted in `.planning/research/STACK-v4.0.md` (§Installation/§Sources), local-only, no cloud/heavy-ML: **pypdfium2 5.11.0** (BSD/Apache, PDFium renderer, prebuilt wheels, no Poppler), **Pillow 12.3.0** (MIT-CMU), **pdfminer.six 20260107** (MIT, pure-Python), and the OPTIONAL **pytesseract 0.3.13** (Apache, behind the `ocr` extra). Names verified exact (not `pypdfium`; PyPI name is `pdfminer.six`). `poetry lock` resolved these exact versions.
- **Verification:** Locked versions in `poetry.lock` match STACK-v4.0 exactly; `import pypdfium2, PIL, pdfminer` succeeds; extraction libs are extras-only (core deps unchanged).
- **Committed in:** `aa139bb` (Task 2 dependency commit)

---

**Total deviations:** 1 (auto-approved supply-chain checkpoint under standing authorization).
**Impact on plan:** No scope change — the checkpoint's pre-vetted packages were installed exactly as specified.

## Issues Encountered
None. The hand-rolled PDF fixture builder was smoke-tested against pdfminer + pypdfium2 before the tests were written to validate the API assumptions.

## User Setup Required
**Optional local OCR only.** The `ocr` extra (`pytesseract`) is opt-in and additionally requires a locally-installed **Tesseract binary** (e.g. `apt-get install tesseract-ocr`). It is NOT required — born-digital PDFs extract without it, and its absence is reported by the Plan-04 `doctor` verb rather than failing. Tesseract is currently absent in this environment (by design; doctor will report it).

## Next Phase Readiness
- Plan 03 (confirmation CLI) can call `extraction.extract_document` and surface pending values through `vault fields`/`vault confirm`.
- Plan 04 (doctor) can reuse `_import_*` probes + `classify_page_quality`/persisted `quality_json`.

---
*Phase: 30-extraction-quarantine-field-confirmation*
*Completed: 2026-07-06*

## Self-Check: PASSED
- All created/modified files present on disk.
- Task 2 (chore) + Task 3 (test+feat) commits present in git history.
- Plan verification green: 11 extraction tests pass; cli imports lean; extraction libs are extras-only.
