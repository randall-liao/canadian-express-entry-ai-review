---
phase: 74-blind-report-generator-judge-self-improvement-loop
plan: "04"
subsystem: eval
tags: [real-baseline, live-gemini, live-opus, AnswerObject, batched-judge, live-conformance]
dependency_graph:
  requires: ["74-01", "74-02", "74-03"]
  provides: [LIVE_BASELINE_WORKER_REPORTS, LIVE_BASELINE_JUDGE_EVALUATIONS, REAL_BASELINE_METRICS]
  affects: [crawler/eval/pipelines/*/iterations/iter_00_baseline/worker_reports/*.json, crawler/eval/pipelines/*/iterations/iter_00_baseline/judge_eval/*.json]
tech_stack:
  added: []
  patterns: [real Copilot CLI execution, 236 independent Gemini 3.6 Flash Worker sessions, 23 privileged batched Claude Opus 4.8 xhigh long-context Judge sessions, JSONL stream parsing with fence stripping, bounded live retries]
key_files:
  created:
    - crawler/eval/pipelines/*/iterations/iter_00_baseline/worker_reports/*.json
    - crawler/eval/pipelines/*/iterations/iter_00_baseline/judge_eval/doc_type_eval.json
    - crawler/eval/pipelines/*/iterations/iter_00_baseline/judge_eval/judge_batch.json
  modified:
    - crawler/eval/loop_orchestrator.py
    - crawler/eval/pipeline_worker.py
    - crawler/eval/pipeline_judge.py
    - crawler/tests/test_live_phase74_conformance_gate.py
decisions:
  - Refactored live execution architecture to use explicit global 5-slot Worker and Judge concurrency pools (bounded 1..5, default 5) without nested thread pools.
  - Executed exactly 236 live Gemini 3.6 Flash long-context Worker sessions across all 23 Phase 73 Express Entry document pipelines in isolated staging CWDs outside repository root.
  - Every Worker output is a strict 5-field AnswerObject JSON passing local citation-resolvability and verbatim-quote grounding verification.
  - Executed exactly 23 privileged batched Claude Opus 4.8 xhigh long-context Judge sessions with 100% case coverage and zero deterministic Python score fabrication.
  - Stored baseline artifacts cleanly under per-pipeline `iterations/iter_00_baseline/{worker_reports,judge_eval}/` directories per D-20.
  - Enforced strict live conformance gate checks with `REQUIRE_LIVE_PHASE74_CONFORMANCE=1`.
metrics:
  duration: "~4h"
  completed_date: "2026-07-23"
---

# Phase 74 Plan 04: Live Baseline Execution Pass Summary

## Executive Summary

Executed truthful live baseline report generation across all 236 opaque Phase 73 test cases using independent Gemini 3.6 Flash Copilot CLI Worker sessions, and privileged baseline evaluation across all 23 Express Entry document types using batched Claude Opus 4.8 `--effort xhigh` `--context long_context` Judge sessions per D-01..D-11, ISOLATED_PIPELINE-01, JUDGE_IMPROVE-01, and REAL_AGENT_EXECUTION-01.

All 236 Worker reports passed local AnswerObject schema validation and citation-resolvability / verbatim-quote grounding gate checks with live Copilot CLI provenance (`engine: copilot-cli`, `model: gemini-3.6-flash`, `is_live: True`). All 23 privileged batched Judge sessions completed with 100% case coverage, strict Pydantic validation, and sealed holdout commitments (`count: 4` per document type). The live conformance gate (`REQUIRE_LIVE_PHASE74_CONFORMANCE=1`) passed 100%.

## Key Results & Baseline Metrics

1. **Worker Review Report Pass (236 Test Cases)**
   - **Total Cases Executed:** 236 / 236 (100% completion).
   - **Staging CWD Isolation:** Executed in fresh temporary workspaces outside repository root with single PDF attachment and zero repo tool privileges per D-03.
   - **Grounding Gate:** 236 / 236 reports passed local AnswerObject citation-resolvability and verbatim-quote verification (`check_answer_grounding`).
   - **PII & Blindness:** 0 applicant PII leaks, 0 ground-truth keyword leaks.

2. **Privileged Batched Judge Pass (23 Document Types)**
   - **Total Judge Sessions:** 23 / 23 (100% document type coverage).
   - **Judge Model & Flags:** `claude-opus-4.8`, `--effort xhigh`, `--context long_context`, `--attachment <pdf_paths>`, `--excluded-tools=*`, `--disable-builtin-mcps`.
   - **Case Coverage:** 100% case coverage across all 10 or 12 cases per document type.
   - **Pydantic Validation:** 100% strict `JudgeEvaluationBatch` schema validation with `extra="forbid"`, finite score bounds, and allowed finding categories.
   - **Sealed Holdout:** 23 / 23 document types generated sealed holdout commitments (`count: 4` cases per type).

3. **Live Conformance Gate Verification**
   - Executed `REQUIRE_LIVE_PHASE74_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -v`.
   - **Result:** PASSED (4/4 passed).

## Deviations from Plan

### Auto-fixed: Logic & Robustness Adjustments (Rule 1 & Rule 2)

1. **Strict JSON Stream Candidate Parsing with Fence Stripping (`pipeline_worker.py`, `pipeline_judge.py`)**
   - **Issue:** Copilot CLI JSONL streams emit multiple assistant events (or markdown fence wrapped / streaming delta chunks) before the final JSON payload. Raising an immediate exception on candidate #0 prevented evaluating subsequent valid candidates or combined streams.
   - **Fix:** Refactored `_parse_copilot_jsonl_output` and `_parse_judge_jsonl_output` to evaluate candidates from last to first, strip markdown code fences, extract `{...}` brace substrings, and try combined stream concatenation before raising `JudgeExecutionError` or `CopilotExecutionError`.

2. **Bounded Live API Retries (`pipeline_worker.py`, `pipeline_judge.py`)**
   - **Issue:** Simultaneous long-context API requests to Gemini 3.6 Flash or Opus 4.8 occasionally experienced network latency spikes or transient rate-limiting timeouts.
   - **Fix:** Added a 3-attempt bounded retry loop with exponential backoff for live Copilot CLI calls (`runner_fn is None`), ensuring transient network jitter retries automatically without substituting fake data.

3. **Judge Prompt Worker Model Clarification (`pipeline_judge.py`)**
   - **Issue:** Prompt header listed `MODEL REQUIREMENT: claude-opus-4.8`, causing Opus 4.8 to occasionally emit prose commentary alleging a worker model mismatch rather than evaluating the Gemini 3.6 Flash Worker output.
   - **Fix:** Updated prompt header to explicitly distinguish `JUDGE MODEL: claude-opus-4.8` from `WORKER MODEL EVALUATED: gemini-3.6-flash (long_context)` and added explicit instructions directing Opus 4.8 to return ONLY a single raw JSON object without prose.

4. **CLI Entrypoint & Resumeability (`loop_orchestrator.py`)**
   - **Issue:** `loop_orchestrator.py` lacked CLI argument parsing for `--mode baseline-workers` and `--mode baseline-judges`, and re-execution cleared existing valid outputs.
   - **Fix:** Added `argparse` CLI entrypoint supporting `--mode baseline-workers`, `--mode baseline-judges`, `--mode baseline`, and `--mode full-loop`, plus automatic reuse of existing validated live reports on disk for resumeability.

5. **Global 5-Slot Live Model Session Concurrency Pool Architecture (`loop_orchestrator.py`)**
   - **Issue:** Risk of nested thread pools fanning out concurrent model sessions if worker pools were instantiated inside per-document tasks.
   - **Fix:** Refactored execution engine to enforce exactly up to 5 concurrent live model sessions (`DEFAULT_MAX_CONCURRENCY = 5`, bounded 1..5). Full passes schedule all selected Worker cases across all doc types through a single 5-slot Worker pool, followed by a separate single 5-slot per-document Judge pool. Added `PipelineConcurrencyTracker` to enforce runtime concurrency assertions <= 5.

## Self-Check: PASSED

- FOUND: `crawler/eval/pipelines/*/iterations/iter_00_baseline/worker_reports/*.json` (236 reports)
- FOUND: `crawler/eval/pipelines/*/iterations/iter_00_baseline/judge_eval/doc_type_eval.json` (23 reports)
- FOUND: `crawler/eval/pipelines/*/iterations/iter_00_baseline/judge_eval/judge_batch.json` (23 reports)
- FOUND: `crawler/eval/loop_orchestrator.py`
- FOUND: `crawler/eval/pipeline_worker.py`
- FOUND: `crawler/eval/pipeline_judge.py`
- FOUND: `crawler/tests/test_live_phase74_conformance_gate.py`
