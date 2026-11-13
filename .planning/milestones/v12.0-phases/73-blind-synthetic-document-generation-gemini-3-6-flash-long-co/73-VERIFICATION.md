---
phase: 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co
verified: 2026-07-23T03:23:02Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
requirements_checked:
  - BLIND_SYNTHETIC-01
  - ISOLATED_PIPELINE-01
  - REAL_AGENT_EXECUTION-01
verification_debt: 1
---

# Phase 73: Blind Synthetic Document Generation (Gemini 3.6 Flash long context) Verification Report

**Phase Goal:** Generate realistic defective vector and 300 DPI scanned PDF cases from validated research while preventing filenames, paths, document contents, and worker-visible metadata from revealing injected failures.
**Verified:** 2026-07-23T03:23:02Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Pydantic schemas enforce 1 valid_control case plus 1 defective case for every research failure mode with source failure ID tracing (per D-02, D-04, D-06). | ✓ VERIFIED | `crawler/synthetic/schemas.py` defines `GenerationSpec`, `TestCaseSpec`, `DefectSpec`, and `PrivateCaseRecord`. Pydantic v2 validators enforce exactly 1 valid control per pipeline and source failure ID mapping. |
| 2 | Side-channel leakage scanner inspects filenames, PDF metadata dictionaries, and text streams for forbidden document types, variants, or verdict labels (per D-07, D-08, D-10). | ✓ VERIFIED | `crawler/synthetic/leakage_scanner.py` implements `scan_blind_artifact_leakage` and `scan_blind_text_leakage`. All 236 production PDFs passed automated leakage scans. |
| 3 | Worker staging API generates 32-hex opaque IDs and stages exactly one opaque PDF in an isolated temporary directory outside the pipeline tree (per D-07, D-09, D-10). | ✓ VERIFIED | `crawler/synthetic/staging.py` implements `stage_case_for_worker` using 16 cryptographically random bytes per ID. Staging unit tests confirm isolation, symlink rejection, path traversal prevention, duplicate source rejection, and cleanup. |
| 4 | Doc synthetic generator executes live GitHub Copilot CLI with gemini-3.6-flash long_context, records truthful provenance, supports injected test runners, and fails closed without fallback output (per D-01, D-02, D-03, D-12, D-13, D-15). | ✓ VERIFIED | `crawler/eval/doc_synthetic_generator.py` executes live Copilot CLI. Provenance files verify live `gemini-3.6-flash` execution with `long_context` flags and SHA-256 prompt/output digests across all 23 pipelines. |
| 5 | ReportLab vector compiler strips all PDF metadata attributes (/Title, /Author, /Subject, /Keywords, /Creator, /Producer) via custom Canvas callbacks (per D-07, D-08). | ✓ VERIFIED | `crawler/synthetic/generator.py` uses `SanitizedMetadataCanvas` overriding ReportLab metadata setters to write empty strings / generic values. Raw PDF inspection confirms zero metadata leakage across all 118 vector PDFs. |
| 6 | Document templates render agent-authored TestCaseSpec fields and narrative_blocks dynamically without embedded defect labels or synthetic annotations (per D-02, D-08, D-14). | ✓ VERIFIED | `crawler/synthetic/templates.py` renders Platypus document flowables across all 23 Express Entry document types dynamically without embedding defect labels or explanatory annotations. |
| 7 | PyPDFium2 + Pillow 300 DPI rasterizer converts clean vector PDF bytes into scanned sibling PDFs with rotation tilt, noise simulation, and zero text layer (per D-05, D-07). | ✓ VERIFIED | `crawler/synthetic/rasterizer.py` converts vector PDFs into scanned sibling PDFs at 300 DPI. PyPDFium text extraction verifies zero text layer across all 118 scanned sibling PDFs. |
| 8 | Pipeline coordinator generates 118 logical cases (23 valid controls + 95 research failure mode cases) and 236 PDF fixtures across 23 document types (per D-04, D-05). | ✓ VERIFIED | Multi-pipeline generator in `crawler/eval/doc_synthetic_generator.py` produced exactly 118 logical cases and 236 PDFs across 23 pipelines. |
| 9 | Privileged ground truth storage writes generation_spec.json, generation_provenance.json, ground_truth.json, and opaque pdfs/<opaque_32hex>.pdf without worker exposure (per D-06, D-09, D-11, D-13). | ✓ VERIFIED | Production pipeline directories (`crawler/eval/pipelines/*/ground_truth/`) contain all required ground-truth manifests and opaque PDFs. Staging API isolates worker access. |
| 10 | Pipeline generation fails closed on malformed output, missing failure mode coverage, or leakage detection, unlinking stale artifacts before exit (per D-15). | ✓ VERIFIED | `_parse_copilot_jsonl_output` and `run_document_generator_agent` fail closed via `CopilotExecutionError`, unlinking stale directories and writing `generator.error.json`. Unit tests pass. |
| 11 | Conformance test suite verifies complete 23-pipeline synthetic dataset generation in temporary test roots using injected test runners (per D-12, D-16). | ✓ VERIFIED | `crawler/tests/test_doc_synthetic_conformance.py` executes 23-pipeline generation in temporary roots. Targeted suite passed 44 tests with one expected ordinary live-gate skip. |
| 12 | Live GitHub Copilot CLI Gemini 3.6 Flash long-context agents run for all 23 Express Entry document types and produce 118 logical case specs and 236 PDF fixtures (per D-01, D-04, D-16). | ✓ VERIFIED | Live conformance release gate (`REQUIRE_LIVE_SYNTHETIC_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_doc_synthetic_conformance.py -k test_live_doc_synthetic_conformance_gate`) passed against all 23 production pipelines. |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `crawler/synthetic/schemas.py` | Pydantic v2 schemas for synthetic dataset generation | ✓ VERIFIED | 474 lines; defines `DefectSpec`, `TestCaseSpec`, `GenerationSpec`, `PrivateCaseRecord`. |
| `crawler/synthetic/leakage_scanner.py` | Side-channel and metadata leakage scanner | ✓ VERIFIED | 176 lines; implements `scan_blind_artifact_leakage` and `scan_blind_text_leakage`. |
| `crawler/synthetic/staging.py` | Worker staging API with 32-hex opaque IDs | ✓ VERIFIED | 209 lines; implements `stage_case_for_worker` and `generate_opaque_32hex_id`. |
| `crawler/eval/doc_synthetic_generator.py` | Live Gemini 3.6 Flash generator agent runner & pipeline coordinator | ✓ VERIFIED | 689 lines; implements Copilot CLI execution, JSONL parser, prompt builder, and ground-truth writer. |
| `crawler/tests/test_doc_synthetic_generator.py` | Unit test suite for schemas, scanner, staging, generator | ✓ VERIFIED | 800 lines. |
| `crawler/synthetic/generator.py` | Metadata-sanitized ReportLab vector compilation engine | ✓ VERIFIED | 255 lines; implements `SanitizedMetadataCanvas` and `render_vector_pdf_bytes`. |
| `crawler/synthetic/templates.py` | Flowable document templates for 23 document types | ✓ VERIFIED | 490 lines; supports all 22 Express Entry document types plus Letter of Explanation. |
| `crawler/synthetic/rasterizer.py` | PyPDFium2 + Pillow 300 DPI scanned sibling PDF rasterizer | ✓ VERIFIED | 224 lines; implements `rasterize_pdf_to_scanned_pdf` with DoS resource bounds. |
| `crawler/tests/test_pdf_synthetic.py` | Unit test suite for vector rendering and scanned rasterization | ✓ VERIFIED | 251 lines. |
| `crawler/tests/test_doc_synthetic_conformance.py` | Pipeline conformance test suite and live release gate | ✓ VERIFIED | 514 lines. |

### Verification Debt

- `crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts` retains the previously disclosed repository-wide performance timeout. Phase 73's targeted, live, security, schema, and publish-safety gates are green; the duplicate-audit performance concern remains deferred to the Phase 75 release gate.

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `crawler/eval/doc_synthetic_generator.py` | `crawler/synthetic/schemas.py` | `GenerationSpec.model_validate` | ✓ WIRED | Validates agent output JSON against Pydantic schema. |
| `crawler/synthetic/generator.py` | `crawler/synthetic/templates.py` | `build_document_story` | ✓ WIRED | Compiles TestCaseSpec into ReportLab Platypus story. |
| `crawler/synthetic/rasterizer.py` | `pypdfium2` | `PdfDocument` | ✓ WIRED | Loads vector PDF bytes for 300 DPI page rendering. |
| `crawler/eval/doc_synthetic_generator.py` | `crawler/synthetic/staging.py` | `generate_opaque_32hex_id` | ✓ WIRED | Generates 32-hex opaque IDs for vector and scanned cases. |
| `crawler/eval/doc_synthetic_generator.py` | `crawler/synthetic/generator.py` | `render_vector_pdf_bytes` | ✓ WIRED | Compiles TestCaseSpec into sanitized vector PDF bytes. |
| `crawler/eval/doc_synthetic_generator.py` | `crawler/synthetic/rasterizer.py` | `rasterize_pdf_to_scanned_pdf` | ✓ WIRED | Rasterizes vector PDF bytes into scanned sibling PDF. |
| `crawler/eval/pipelines/*/ground_truth/generation_provenance.json` | `GitHub Copilot CLI` | `copilot-cli` | ✓ WIRED | Records live execution provenance (`engine: copilot-cli`, `is_live: true`). |
| `crawler/eval/pipelines/*/ground_truth/ground_truth.json` | `crawler/synthetic/staging.py` | `blind_filename` | ✓ WIRED | Maps opaque 32-hex IDs to ground truth fields and staging API. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `crawler/eval/doc_synthetic_generator.py` | `GenerationSpec` | Live Copilot CLI `gemini-3.6-flash` output | Yes | ✓ FLOWING |
| `crawler/synthetic/generator.py` | `vector_pdf_bytes` | ReportLab Platypus compilation from `TestCaseSpec` | Yes | ✓ FLOWING |
| `crawler/synthetic/rasterizer.py` | `scanned_pdf_bytes` | PyPDFium2 + Pillow 300 DPI rendering from `vector_pdf_bytes` | Yes | ✓ FLOWING |
| `crawler/synthetic/staging.py` | `staged_pdf` | Privileged pipeline PDF read & byte copy | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Unit test suite | `poetry run pytest crawler/tests/test_doc_synthetic_generator.py crawler/tests/test_pdf_synthetic.py` | 40 passed in 10s | ✓ PASS |
| Conformance test suite | `poetry run pytest crawler/tests/test_doc_synthetic_conformance.py` | 4 passed, 1 skipped (live gate) in 127s | ✓ PASS |
| Live release gate | `RUN_LIVE_GENERATOR_GATE=1 poetry run pytest crawler/tests/test_doc_synthetic_conformance.py -k test_live_doc_synthetic_conformance_gate` | 1 passed in 128s | ✓ PASS |
| Total logical cases & PDFs count | Python inspection script across all 23 pipelines | 118 logical cases, 236 PDFs (118 vector, 118 scanned), 236 unique 32-hex IDs | ✓ PASS |
| Research failure mode match | Python inspection script | 95/95 research failure IDs 100% matched to defect specs | ✓ PASS |
| Side-channel & text layer check | Python inspection script across all 236 PDFs | 0 leakage violations; 118/118 scanned PDFs have empty text layer | ✓ PASS |

### Probe Execution

No external shell probe script was required; synthetic generator uses pytest release gate (`test_live_doc_synthetic_conformance_gate`).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| `BLIND_SYNTHETIC-01` | 73-01, 73-02, 73-03, 73-04 | Use Gemini 3.6 Flash long-context generator agents to turn validated research into realistic defective vector and 300 DPI scanned PDFs with opaque identifiers and separately stored ground truth. | ✓ SATISFIED | 23 live Gemini 3.6 Flash agents ran, 118 logical cases and 236 PDFs (118 vector, 118 scanned) generated with 32-hex opaque IDs and isolated ground truth manifests. |
| `ISOLATED_PIPELINE-01` | 73-01, 73-03 | Run each document type in `crawler/eval/pipelines/<doc_type>/` and stage report-generator inputs so workers can access only the blind PDF and allowed extracted text. | ✓ SATISFIED | Worker Staging API implemented in `crawler/synthetic/staging.py` enforces isolated staging outside pipeline tree, leakage scanning, symlink/path traversal rejection. |
| `REAL_AGENT_EXECUTION-01` | 73-01, 73-04 | Execute every claimed synthetic generator role through a real GitHub Copilot CLI agent session with assigned model/context/effort. | ✓ SATISFIED | Provenance records across all 23 pipelines confirm live `copilot-cli` execution with `gemini-3.6-flash`, `long_context`, `is_live: true`, SHA-256 prompt digests, and zero deterministic fallbacks. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | N/A | None | None | No debt markers, TODOs, or stubs found in Phase 73 code. |

### Human Verification Required

None. All Phase 73 success criteria and requirements are programmatically verified via unit tests, conformance tests, release gates, and structural inspection scripts.

### Gaps Summary

None. All 12 must-have truths are verified. All 23 document pipelines generated complete, valid synthetic datasets with live Gemini 3.6 Flash long-context provenance.

---

_Verified: 2026-07-23T03:23:02Z_
_Verifier: the agent (gsd-verifier)_
