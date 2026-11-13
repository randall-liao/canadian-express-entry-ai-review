---
phase: 74-blind-report-generator-judge-self-improvement-loop
plan: "02"
subsystem: eval
tags: [holdout-splitter, sibling-sealing, batched-judge, claude-opus-4.8, xhigh-effort, long-context, pydantic-schema, strict-jsonl]
dependency_graph:
  requires: [74-01]
  provides: [HOLDOUT_SPLITTER_ENGINE, BATCHED_OPUS_JUDGE_HARNESS]
  affects: [crawler/eval/holdout_splitter.py, crawler/eval/pipeline_judge.py, crawler/eval/real_judge.py, crawler/tests/test_phase74_judge_loop.py]
tech_stack:
  added: []
  patterns: [logical sibling group holdout partitioning, sha256-deterministic pair selection, batched Copilot CLI attachment staging, Pydantic JudgeEvaluationBatch schema validation, strict JSONL parsing, sanitized provenance]
key_files:
  created:
    - crawler/eval/holdout_splitter.py
    - crawler/tests/test_phase74_judge_loop.py
  modified:
    - crawler/eval/pipeline_judge.py
    - crawler/eval/real_judge.py
decisions:
  - Logical cases are partitioned by sibling pair (vector + scanned) so no sibling crosses train and holdout boundaries, with exactly 4 cases in holdout per doc type.
  - Holdout set contains 1 valid control pair and 1 sha256-deterministic defective pair per document type; holdout data is sealed from optimizer agents with commitment count and hash.
  - Privileged Judge executes as one batched Copilot CLI session per document type using claude-opus-4.8, --effort xhigh, --context long_context, --attachment, --disallow-temp-dir, and --excluded-tools=* in an isolated privileged staging CWD outside repo/system temp.
  - Judge output requires strict JSONL assistant.message parsing, Pydantic model_validate parsing with extra="forbid", and 100% case coverage assertion, failing closed without Python score fabrication.
  - Worker reports passed to Judge must have live Gemini 3.6 Flash long-context provenance and matching input PDF sha256 hashes.
  - Legacy single-case deterministic Judge entrypoints are disabled.
metrics:
  duration: "~15m"
  completed_date: "2026-07-23"
---

# Phase 74 Plan 02: Logical Sibling Holdout Splitter & Privileged Batched Opus 4.8 Judge Engine Summary

## Executive Summary

Logical sibling group train/holdout splitter built and privileged batched Claude Opus 4.8 Judge engine refactored to enforce strict holdout sealing, 100% case coverage assertions, Pydantic schema validation, attachment validation, and strict JSONL stream parsing for all 23 document types per D-08..D-13 and JUDGE_IMPROVE-01.

## Key Changes

1. **Holdout Splitter & Sealer Engine (`crawler/eval/holdout_splitter.py`)**
   - Implemented `split_doc_type_cases` to partition cases by logical sibling pairs (vector and scanned), ensuring no sibling pair crosses train/holdout boundaries and asserting exactly 4 cases in holdout.
   - Allocated the 1 valid control pair and 1 defective pair selected deterministically via `int(hashlib.sha256(doc_type.encode()).hexdigest(), 16) % len(defective_pairs)` into the sealed holdout set.
   - Implemented `seal_holdout_findings` to purge holdout case evaluations, findings, recommendations, and labels from optimizer-facing data structures, adding a structural holdout commitment count and SHA-256 hash. Fails closed if holdout IDs cannot be resolved.

2. **Privileged Batched Opus 4.8 Judge Harness (`crawler/eval/pipeline_judge.py`, `crawler/eval/real_judge.py`)**
   - Implemented `run_batched_document_judge` to execute exactly one privileged Copilot CLI session per document type per evaluation pass, batching all 10 or 12 Worker reports and PDF attachments (`--attachment <pdf_name>`).
   - Executes in a fresh privileged staging CWD outside repo and system temp (`reports/judge_staging/<tmp>`) with automatic cleanup in `finally`.
   - Configured mandatory Copilot flags: `--model claude-opus-4.8`, `--effort xhigh`, `--context long_context`, `--output-format json`, `--stream off`, `--disallow-temp-dir`, `--excluded-tools=*`, `--disable-builtin-mcps`, `--no-custom-instructions`, `--no-ask-user`.
   - Defined strict Pydantic models with `extra="forbid"`, bounded finite score validators, allowed finding categories/severities, allowlisted patch targets, and required case IDs.
   - Enforced pre-invocation Worker report provenance verification (model `gemini-3.6-flash`, context `long_context`, matching `input_pdf_sha256`).
   - Implemented strict JSONL stream parsing (`_parse_judge_jsonl_output`), rejecting malformed lines, reasoning events, raw markdown fences, and brace-scanning fallbacks.
   - Implemented 100% case coverage assertion, failing closed if response has missing or extra case IDs or doc_type mismatch.
   - Prohibited deterministic Python score fabrication or fake fallback evaluations; process errors write `judge_error.json` and block the pipeline.
   - Attached sanitized provenance with prompt/research/ground-truth digests and relative attachments without exposing raw privileged text or absolute paths.
   - Disabled legacy single-case deterministic entrypoints (`judge_pipeline_case` and `judge_real_worker_output`).

3. **Judge Engine & Holdout Unit Test Suite (`crawler/tests/test_phase74_judge_loop.py`)**
   - Implemented 13 unit and contract tests verifying exact split rules, sibling group sealing determinism, optimizer redaction, holdout commitment, Opus command flags and attachments, attachment/case mismatch detection, repository/temp denial and stage cleanup, strict JSONL parsing, reasoning event rejection, fail-closed worker report provenance and hash verification, Pydantic schema validation (`extra="forbid"`, finite score bounds, allowed categories/patch targets), raw privileged leakage redaction, holdout loading failure fail-closed behavior, and legacy entrypoint disablement.

## Verification Results

- Phase 74 test suite: `.venv/bin/python -m pytest crawler/tests/test_phase74_judge_loop.py crawler/tests/test_phase74_worker_isolation.py -q` (21/21 PASSED).

## Deviations from Plan

Rule 1 & Rule 2: Hardened attachment flags to `--attachment`, added privileged staging CWD isolation, strict JSONL parsing, Worker report provenance hash verification, and holdout commitment structure to close all strict Judge/holdout gaps.

## Known Stubs

None - all code paths are fully wired and functional.

## Self-Check: PASSED

- FOUND: `crawler/eval/holdout_splitter.py`
- FOUND: `crawler/eval/pipeline_judge.py`
- FOUND: `crawler/eval/real_judge.py`
- FOUND: `crawler/tests/test_phase74_judge_loop.py`

