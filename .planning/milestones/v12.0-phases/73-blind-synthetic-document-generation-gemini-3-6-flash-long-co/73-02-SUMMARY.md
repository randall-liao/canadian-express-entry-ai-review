---
phase: 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co
plan: 02
subsystem: synthetic-rendering
tags: [pdf-rendering, reportlab, metadata-sanitization, pypdfium2, rasterization, zero-text-layer]
requires: [73-01]
provides: [ReportLab metadata-sanitized vector compiler, dynamic document templates, 300 DPI scanned sibling rasterizer]
affects: [crawler/synthetic/generator.py, crawler/synthetic/templates.py, crawler/synthetic/rasterizer.py, crawler/tests/test_pdf_synthetic.py]
tech_stack:
  added: []
  patterns: [SanitizedMetadataCanvas, Image-Only PDF Rasterization, Platypus Dynamic Flowable Story]
key_files:
  created: []
  modified:
    - crawler/synthetic/generator.py
    - crawler/synthetic/templates.py
    - crawler/synthetic/rasterizer.py
    - crawler/tests/test_pdf_synthetic.py
decisions:
  - "SanitizedMetadataCanvas overrides Title, Author, Subject, Keywords, Creator, and Producer metadata attributes on canvas initialization and save to eliminate PDF metadata side channels."
  - "Scanned sibling PDFs are compiled by re-encoding rendered 300 DPI bitmap pages onto SanitizedMetadataCanvas instances, guaranteeing 100% zero vector text layer and clean metadata."
  - "Template builder enforces prohibition of explanatory defect annotations ('defective', 'missing field', 'expired credential', 'pfl trigger', 'synthetic test') per decision D-08."
metrics:
  duration: 10m
  completed_date: "2026-07-23"
  tasks_completed: 2
  files_modified: 4
---

# Phase 73 Plan 02: ReportLab Metadata-Sanitized Canvas & PyPDFium2 300 DPI Scanned Sibling Rasterizer Summary

Implemented the metadata-sanitized ReportLab vector compilation engine and PyPDFium2 + Pillow 300 DPI scanned sibling rasterizer with 100% text layer elimination.

## Key Changes Made

1. **Metadata-Sanitized Vector Canvas (`crawler/synthetic/generator.py`):**
   - Created `SanitizedMetadataCanvas(canvas.Canvas)` overriding `/Title`, `/Author`, `/Subject`, `/Keywords`, `/Creator`, and `/Producer` to empty/generic strings on initialization and save.
   - Implemented `render_vector_pdf_bytes(case_spec: TestCaseSpec) -> bytes` using `SimpleDocTemplate` and `SanitizedMetadataCanvas`.

2. **Dynamic Flowable Document Templates (`crawler/synthetic/templates.py`):**
   - Implemented `build_document_story(case_spec: TestCaseSpec) -> List[Any]` to construct ReportLab Platypus flowable stories from agent-authored `TestCaseSpec` objects across all 23 Express Entry document types.
   - Supported dynamic narrative body blocks (`case_spec.narrative_blocks`) for letters of explanation, employment references, and statutory declarations.
   - Enforced validation asserting zero explanatory defect annotations (`"defective"`, `"missing field"`, `"expired credential"`, `"pfl trigger"`, `"synthetic test"`) exist in case content per decision D-08.

3. **Scanned Sibling Rasterizer & Zero Text Layer (`crawler/synthetic/rasterizer.py`):**
   - Implemented `rasterize_pdf_to_scanned_pdf(vector_pdf_bytes, dpi=300, rotation_angle=1.0)` rendering vector pages at 300 DPI using `pypdfium2`.
   - Applied grayscale conversion, contrast adjustment, 1.0° rotation tilt, and gaussian scan noise simulation via Pillow.
   - Re-compiled bitmap page images into image-only PDF pages using `SanitizedMetadataCanvas`, ensuring zero text layer and clean metadata.

4. **Rendering Test Suite (`crawler/tests/test_pdf_synthetic.py`):**
   - Added unit tests for vector PDF rendering & metadata sanitization (`test_vector_pdf_rendering_and_metadata_sanitization`).
   - Added unit tests for 300 DPI scanned rasterization and zero text layer verification (`test_scanned_pdf_rasterization_and_text_layer_removal`).
   - Added unit tests for dynamic narrative block rendering and explanatory annotation prohibition (`test_narrative_blocks_rendering_and_annotation_prohibition`).

## Deviations from Plan

### Security Mitigations

**1. [Rule 2 - Security] Closed T-73-12 Rasterization DoS bounds threat mitigation**
- **Found during:** Phase 73 security sign-off remediation
- **Issue:** Rasterizer lacked fail-closed input bounds checking on PDF size, page counts, page dimensions, and pixel scaling before page rendering.
- **Fix:** Added shared fail-closed bounds checking before page rendering in both rasterizer entry points (`rasterize_pdf_to_scanned_images` and `rasterize_pdf_to_scanned_pdf`): max input size 20MB, accepted DPI range [72, 600] including required 300, max 50 pages, max 10,000x10,000 px per-page bounds, max 100MP aggregate pixels across document, and rejection of non-finite/negative page dimensions with explicit ValueError. Ensured `pypdfium2.PdfDocument` resources close in `finally` blocks. Added unit tests for all bounds in `test_pdf_synthetic.py`.
- **Files modified:** `crawler/synthetic/rasterizer.py`, `crawler/tests/test_pdf_synthetic.py`
- **Commit:** `9ecac91`

## Verification Results

- All 6 unit tests in `crawler/tests/test_pdf_synthetic.py` passed green in 1.68s.
- Vector PDF metadata sanitization verified clean (`/Title`, `/Author`, `/Subject`, `/Keywords` are empty `""`).
- Scanned PDF page count matches vector sibling and textpage text extraction returns 0 characters.

## Self-Check: PASSED

- `crawler/synthetic/generator.py` exists and min lines >= 80 (actual: 215 lines)
- `crawler/synthetic/templates.py` exists and min lines >= 150 (actual: 450 lines)
- `crawler/synthetic/rasterizer.py` exists and min lines >= 50 (actual: 153 lines)
- `crawler/tests/test_pdf_synthetic.py` exists and min lines >= 60 (actual: 133 lines)
- Commits `64a46a2` and `d3bc590` verified in git log.
