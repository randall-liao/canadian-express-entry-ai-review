---
phase: 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co
plan: 01
subsystem: crawler/synthetic
tags:
  - pydantic
  - gemini-3.6-flash
  - blind-staging
  - leakage-scanner
  - copilot-cli
dependency_graph:
  requires:
    - Phase 72 research reports (crawler/eval/pipelines/*/research/research.json)
  provides:
    - GenerationSpec
    - DefectSpec
    - TestCaseSpec
    - PrivateCaseRecord
    - scan_blind_artifact_leakage
    - stage_case_for_worker
    - run_document_generator_agent
  affects:
    - crawler/synthetic/schemas.py
    - crawler/synthetic/leakage_scanner.py
    - crawler/synthetic/staging.py
    - crawler/eval/doc_synthetic_generator.py
    - crawler/tests/test_doc_synthetic_generator.py
tech_stack:
  added: []
  patterns:
    - Pydantic v2 schema validation
    - 32-hex opaque random case IDs
    - Automated side-channel leakage scanning
    - Worker staging API in temporary roots
    - Copilot CLI JSONL runner with test double support
key_files:
  created:
    - crawler/synthetic/leakage_scanner.py
    - crawler/synthetic/staging.py
    - crawler/eval/doc_synthetic_generator.py
    - crawler/tests/test_doc_synthetic_generator.py
  modified:
    - crawler/synthetic/schemas.py
decisions:
  - "Enforce 1 valid control + N defective cases for every research failure mode via Pydantic v2 model_validator on GenerationSpec."
  - "Scans filenames, PDF metadata dictionaries, and text streams for side-channel leakage before staging artifacts for worker evaluation."
  - "Worker staging API creates isolated temporary directories and copies only one opaque PDF file without exposing ground truth manifests or sibling pointers."
  - "Refactor doc_synthetic_generator.py to invoke Copilot CLI with gemini-3.6-flash long_context, record truthful provenance, support injected test runners, and fail closed on error."
metrics:
  duration: "~10m"
  completed_date: "2026-07-23"
---

# Phase 73 Plan 01: Core Schemas, Side-Channel Leakage Scanner, Worker Staging API & Gemini Agent Runner Summary

**Substantive Summary:** Delivered Pydantic v2 schemas (`GenerationSpec`, `DefectSpec`, `TestCaseSpec`, `PrivateCaseRecord`), automated side-channel leakage scanner (`scan_blind_artifact_leakage`), worker staging API (`stage_case_for_worker`), and refactored live Copilot CLI Gemini 3.6 Flash generator runner (`run_document_generator_agent`) with test double support.

## Executed Tasks

| Task | Name | Commit | Files Created/Modified |
| --- | --- | --- | --- |
| 1 | Define GenerationSpec, DefectSpec, TestCaseSpec, and PrivateCaseRecord Schemas | `6ee4f1b` | `crawler/synthetic/schemas.py` |
| 2 | Build Automated Side-Channel Leakage Scanner and Blind Worker Staging API | `a09c178` | `crawler/synthetic/leakage_scanner.py`, `crawler/synthetic/staging.py` |
| 3 | Refactor doc_synthetic_generator.py into Gemini Flash Agent Runner with Test Double Support | `d6646e6` | `crawler/eval/doc_synthetic_generator.py`, `crawler/tests/test_doc_synthetic_generator.py`, `crawler/synthetic/schemas.py` |

## Accomplishments

1. **Pydantic v2 Schemas:** Defined `DefectSpec`, `TestCaseSpec`, `GenerationSpec`, and `PrivateCaseRecord` enforcing 1 valid control + N defective cases per Phase 72 research failure mode, 32-hex opaque ID validation, and private ground truth recording.
2. **Side-Channel Leakage Scanner:** Built `scan_blind_artifact_leakage` to inspect filenames (`<opaque_32hex>.pdf`), PDF metadata dictionaries (stripping document type, variant, case class, and PFL labels), and page text streams.
3. **Worker Staging API:** Built `generate_opaque_32hex_id` (`secrets.token_hex(16)`) and `stage_case_for_worker` to stage single opaque PDFs into fresh temporary directories outside the pipeline tree.
4. **Gemini 3.6 Flash Agent Runner:** Refactored `crawler/eval/doc_synthetic_generator.py` into a genuine agent runner invoking GitHub Copilot CLI with `--model gemini-3.6-flash` and `--context long_context`. Supported fake `copilot_runner` test doubles with truthful `is_live=False` provenance tracking and fail-closed error recording (`generator.error.json`).
5. **Unit Test Suite:** Created `crawler/tests/test_doc_synthetic_generator.py` with 9 passing unit tests covering schema validation, leakage scanning, staging API, and agent execution in temporary roots.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed blocking structural-isolation gaps in worker staging API**
- **Found during:** Post-plan Wave 1 structural isolation audit
- **Issue:** `stage_case_for_worker` previously allowed target directories inside pipeline root, did not reject pre-populated target directories, did not reject symlinked source PDF/text files, did not enforce source file uniqueness or single-match validation, used hint-bearing directory prefixes (`blind_worker_staging_`), preserved source filesystem mtimes/metadata, did not scan text file leakage before copying, and lacked strict destination artifact assertions.
- **Fix:** Refactored `staging.py` and `leakage_scanner.py` to resolve and enforce `pipeline_root` containment, reject symlinked source files, reject duplicate source matches, enforce caller-supplied `target_dir` emptiness outside `pipeline_root`, use neutral `tempfile.mkdtemp()` directories, write raw bytes with normalized `chmod(0o644)` and `os.utime((0, 0))` timestamps, scan extracted text before/after staging, clean up destination directory on any exception/violation, and assert destination contains strictly allowed opaque artifacts. Added 7 comprehensive adversarial unit tests in `test_doc_synthetic_generator.py`.
- **Files modified:** `crawler/synthetic/staging.py`, `crawler/synthetic/leakage_scanner.py`, `crawler/tests/test_doc_synthetic_generator.py`
- **Commit:** `ce8e0ac`

**2. [Rule 2 - Security] Closed T-73-01 Prompt Injection threat mitigation**
- **Found during:** Phase 73 security sign-off remediation
- **Issue:** Generator prompt previously embedded full un-sanitized research reports/excerpts without strict data isolation or input provenance verification.
- **Fix:** Validated production research input against Phase 72 ResearchReport contract and required truthful live provenance (`is_live=True`, `status="success"`, `provenance_token`). Whitelisted generator prompt failure mode fields (`failure_id`, `category`, `severity`, `title`, `affected_fields`) and serialized as JSON inside `<UNTRUSTED_RESEARCH_FAILURE_MODES>` tag with escaped delimiters (`\u003c` / `\u003e`). Added explicit untrusted data directive to system prompt. Added adversarial research string tests in `test_doc_synthetic_generator.py`.
- **Files modified:** `crawler/eval/doc_synthetic_generator.py`, `crawler/tests/test_doc_synthetic_generator.py`
- **Commit:** `a7225b7`

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- All 5 key files exist and are verified:
  - `crawler/synthetic/schemas.py`
  - `crawler/synthetic/leakage_scanner.py`
  - `crawler/synthetic/staging.py`
  - `crawler/eval/doc_synthetic_generator.py`
  - `crawler/tests/test_doc_synthetic_generator.py`
- All task commits exist in git log: `6ee4f1b`, `a09c178`, `d6646e6`, `ce8e0ac`.
- Unit test suite (`crawler/tests/test_doc_synthetic_generator.py`) passes 16/16 green.
