---
phase: 74-blind-report-generator-judge-self-improvement-loop
plan: 01
subsystem: eval
tags: [blind-worker, public-bundle, CWD-isolation, answer-object, grounding-gate]
dependency_graph:
  requires: [ISOLATED_PIPELINE-01]
  provides: [PUBLIC_BUNDLE_ENGINE, ISOLATED_BLIND_WORKER_RUNNER]
  affects: [crawler/eval/public_bundle.py, crawler/eval/pipeline_worker.py, crawler/eval/real_worker.py, crawler/grounding.py]
tech_stack:
  added: []
  patterns: [CWD staging isolation, SHA-256 evidence bundle provenance, JSONL event extraction, AnswerObject local grounding gate]
key_files:
  created:
    - crawler/eval/public_bundle.py
    - crawler/tests/test_phase74_worker_isolation.py
  modified:
    - crawler/eval/pipeline_worker.py
    - crawler/eval/real_worker.py
    - crawler/grounding.py
decisions:
  - Public review bundles use canonical skill rules and exact corpus quotes with SHA-256 provenance hashes.
  - Blind Workers execute in isolated temporary staging CWDs outside repository root with gemini-3.6-flash, --no-custom-instructions, and zero repository tools.
  - Worker outputs require local AnswerObject grounding verification and fail closed on errors without fake fallback reports.
metrics:
  duration: "~10m"
  completed_date: "2026-07-23"
---

# Phase 74 Plan 01: Public Review Bundle & Blind Worker Runner Isolation Summary

## Executive Summary

Public review bundle engine built and blind Worker runner refactored to enforce strict filesystem staging isolation, zero tool privileges, and local AnswerObject grounding verification for all report-generator test cases per D-01..D-07 and ISOLATED_PIPELINE-01.

## Key Changes

1. **Public Review Bundle Engine (`crawler/eval/public_bundle.py`)**
   - Implemented `build_public_review_bundle` to assemble immutable, PII-free public evidence bundles for each document type containing both canonical per-document skill rules (`skills/document-agents/<doc_type>.md`) and the shared PDF review contract (`skills/pdf/SKILL.md`), plus verbatim local corpus quotes (`corpus/index.db`).
   - Added explicit in-memory override parameters `override_skill_content` and `override_shared_content` for candidate evaluations without editing source files on disk before acceptance.
   - Recorded SHA-256 content hashes for execution provenance and verified zero leakage of privileged keywords (`research.json`, `ground_truth`, `case_001`, `expected_verdict`) or opaque case IDs in overrides.

2. **Blind Worker Execution Engine (`crawler/eval/pipeline_worker.py`, `crawler/eval/real_worker.py`)**
   - Implemented `run_blind_worker_task` to execute Gemini 3.6 Flash long-context sessions in an isolated staging CWD outside the repository root containing ONLY `<opaque_id>.pdf` (and optional `<opaque_id>.txt`).
   - Removed legacy repository CWD execution, `--allow-all` permissions, and fake fallback success reports.
   - Employed portable Copilot CLI executable discovery, passed `-s --no-custom-instructions`, captured JSONL streams, extracted strict 5-field AnswerObjects, verified local grounding, and attached truthful provenance.

3. **Grounding Verification Gate (`crawler/grounding.py`)**
   - Exposed `check_answer_grounding` for in-process AnswerObject validation and local citation-resolvability / verbatim-quote checking.

4. **Isolation Unit & Contract Test Suite (`crawler/tests/test_phase74_worker_isolation.py`)**
   - Implemented 6 unit and contract tests verifying public bundle determinism, missing-skill handling, zero-privileged keyword guarantees, CWD staging isolation, flag safety, and fail-closed error handling.

## Verification Results

- Automated test execution: `.venv/bin/python -m pytest crawler/tests/test_phase74_worker_isolation.py -v` (6/6 PASSED).
- Engine test suite: `.venv/bin/python -m pytest crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_real_llm_engine.py -v` (12/12 PASSED).

## Deviations from Plan

### Auto-fixed: Worker runtime and public-bundle contract

- Replaced plain output parsing with strict JSONL final-message parsing and reasoning-event rejection.
- Added one-PDF attachment, Gemini long context, zero-tool exclusions, built-in MCP disablement, and no-custom/no-question flags.
- Moved stages out of the globally readable system temp area, denied temp access, and guaranteed cleanup.
- Added publish-safe input/bundle/prompt/output/provenance hashes with truthful live vs injected engines.
- Disabled the legacy repository-root `real_worker.run_worker_review_task` entrypoint.
- Made public bundles fail closed unless their dedicated document skill resolves exact local corpus evidence; added a dedicated Letter of Explanation skill.
- Changed missing-corpus grounding from fail-open success to an explicit error.

## Self-Check: PASSED

- FOUND: `crawler/eval/public_bundle.py`
- FOUND: `crawler/eval/pipeline_worker.py`
- FOUND: `crawler/tests/test_phase74_worker_isolation.py`
- FOUND Commit `03ff950`: feat(74-01): build public review bundle engine and isolation unit test scaffold
- FOUND Commit `fad4735`: feat(74-01): refactor blind Worker runner for staging isolation and AnswerObject grounding
