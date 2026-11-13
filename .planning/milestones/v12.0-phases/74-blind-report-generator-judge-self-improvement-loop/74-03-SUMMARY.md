---
phase: 74-blind-report-generator-judge-self-improvement-loop
plan: "03"
subsystem: eval
tags: [sandboxed-optimizer, patch-evaluator, allowlist-scanner, loop-orchestrator, live-conformance-gate]
dependency_graph:
  requires: ["74-01", "74-02"]
  provides: [CANDIDATE_OPTIMIZER_ENGINE, PATCH_REGRESSION_EVALUATOR, LOOP_ORCHESTRATOR, LIVE_CONFORMANCE_GATE]
  affects: [crawler/eval/genuine_optimizer.py, crawler/eval/patch_evaluator.py, crawler/eval/loop_orchestrator.py, crawler/tests/test_live_phase74_conformance_gate.py]
tech_stack:
  added: []
  patterns: [proposal sandbox isolation, allowlist regex scanning, holdout zero-regression gate, atomic patch applier, multi-iteration pipeline orchestrator]
key_files:
  created:
    - crawler/eval/patch_evaluator.py
    - crawler/eval/loop_orchestrator.py
    - crawler/tests/test_live_phase74_conformance_gate.py
  modified:
    - crawler/eval/genuine_optimizer.py
    - crawler/eval/agent_improvement_loop.py
    - crawler/eval/benchmark_runner.py
    - crawler/eval/self_optimizer.py
    - crawler/tests/test_phase74_judge_loop.py
decisions:
  - Gemini candidate optimizers run in isolated proposal sandboxes with sealed training findings and write candidate skill patches without editing shared source directly.
  - Per-document target paths resolve through canonical DOC_TYPE_TO_SKILL mapping; hyphenated and special doc_type names (ECA, medical, LoE) map to canonical skill paths without duplicate underscore skills.
  - Optimizer returns strict JSONL final-message object parsed via Pydantic model (OptimizerProposal) with target_file, candidate_content, and rationale; malformed/reasoning/plain/fenced/raw fallbacks are rejected.
  - Optimizer prompt XML-escapes prompt inputs as untrusted data, requires valid holdout commitment structure, and structurally rejects holdout IDs, evaluations, or labels in training findings.
  - Candidate sandbox clearing removes stale sandboxes on error; stored provenance contains candidate ID and hashes only, omitting absolute sandbox/candidate paths, raw prompts, JSONL, or secrets.
  - Patch evaluator scans allowlisted target files and validates diff line counts (<= 120 lines) and change ratios (<= 40%), control/binary chars, Markdown fence parity, case IDs, PII, and safety weakenings.
  - Regression gate requires all 5 finite metrics plus overall score for baseline/candidate train and holdout, rejecting missing/NaN/Inf metrics, training safety regressions, or holdout regressions.
  - Loop orchestrator manages baseline pass (236 Workers, 23 batched Opus Judges), up to 3 optimization iterations including 23 per-doc proposals and 1 shared Gemini optimizer proposal evaluated across all 23 document types explicitly, and final full pass.
  - Live conformance gate scaffold enforces REQUIRE_LIVE_PHASE74_CONFORMANCE=1 and validates live Copilot CLI provenance, 236 case coverage, 23 Opus 4.8 xhigh Judges, sealed holdout evidence, and patch audit trails.
metrics:
  duration: "~20m"
  completed_date: "2026-07-23"
---

# Phase 74 Plan 03: Sandboxed Gemini Optimizer, Allowlist Patch Evaluator, Loop Orchestrator & Live Conformance Gate Summary

## Executive Summary

Hardened sandboxed Gemini candidate optimizer engine, allowlist patch evaluator, loop orchestrator, and live conformance gate scaffold implemented per D-14..D-22 and REAL_AGENT_EXECUTION-01 before live baseline.

## Key Changes

1. **Sandboxed Gemini Candidate Optimizer (`crawler/eval/genuine_optimizer.py`)**
   - Implemented `run_candidate_optimization_pass` to run Gemini 3.6 Flash long-context Copilot sessions using sealed training Judge findings.
   - Resolved per-document target paths through canonical `DOC_TYPE_TO_SKILL` mapping (`educational_credential_assessment` -> `eca.md`, `language_test` -> `language-test.md`, `letter_of_explanation` -> `letter-of-explanation.md`, etc.).
   - Parsed strict `OptimizerProposal` JSON objects (`target_file`, `candidate_content`, `rationale`) via Pydantic; rejected malformed JSON, reasoning events, plain string, Markdown fenced string, or raw fallback strings.
   - XML-escaped prompt inputs as untrusted data; verified holdout commitment objects; structurally rejected holdout contamination in training findings.
   - Cleared candidate proposal sandboxes before use and cleaned up stale sandboxes on error; ensured stored provenance contains candidate ID and hashes only, omitting absolute sandbox/candidate paths, raw prompts, JSONL, or secrets.

2. **Allowlist Patch Evaluator & Regression Gate (`crawler/eval/patch_evaluator.py`)**
   - Implemented `validate_patch_allowlist` to scan candidate patches against canonical target paths (`skills/document-agents/<stem>.md`, `AGENTS.md`, `skills/pdf/SKILL.md`).
   - Validated diff bounds (<= 120 changed lines, <= 40% line change ratio), control/binary characters, Markdown fence balance, forbidden case IDs, ground-truth paths, applicant PII, and safety/grounding rule weakenings.
   - Implemented `evaluate_candidate_patch` enforcing present and finite float values across all 5 evaluation dimensions (`grounding_accuracy`, `citation_exactness`, `defect_recall`, `pii_containment`, `blind_input_compliance`) plus `overall_score`.
   - Accepted patches IF AND ONLY IF overall training score improved, zero training safety dimension regressed, and ZERO holdout dimension regressed across all 5 dimensions.
   - Implemented `apply_patch_atomically` for serialized atomic file updates.

3. **Loop Orchestrator (`crawler/eval/loop_orchestrator.py`)**
   - Implemented `LoopOrchestrator` to drive baseline execution across all 236 Worker sessions and 23 batched Opus Judges, up to 3 optimization iterations, and final full pass.
   - Discovers all 23 canonical `ExpressEntryDocType` pipelines requiring Phase 73 data layout (`ground_truth/ground_truth.json`, `ground_truth/pdfs/`, `research/research.json`), failing closed on missing/extra/legacy directories.
   - Loads and validates canonical list-valued `ground_truth.json` records, verifying reciprocal sibling links, 32-hex IDs, doc_type match, 10/12 cases per type, 236 total cases, and PDF SHA256 hashes before Worker invocation. Removed legacy `test_data` fallbacks.
   - Executes Workers with bounded concurrency (`max_workers=4` default), storing Worker reports and Judge evaluations under each document pipeline's `iterations/<iteration_name>/` directory per D-20.
   - Clears target iteration output directories before pass execution and writes explicit error metadata (`worker_error.json`, `judge_error.json`) on partial failure, preventing incomplete passes from satisfying live gates.
   - Hardened `_mean_metrics` to fail closed on empty evaluation lists or missing/non-finite metric dimensions.
   - Driven 23 per-doc optimizer proposals passing `override_skill_content` to `build_public_review_bundle` and 1 shared Gemini optimizer proposal (`skills/pdf/SKILL.md` / `AGENTS.md`) building candidate bundles with `override_shared_content` evaluated explicitly across all 23 document types before applying patches.
   - Managed structured iteration artifact storage (`iterations/iter_<N>/`) and complete patch audit trails (`accepted_patches.json`, `rejected_patches.json`).

4. **Legacy Module Deprecation (`crawler/eval/agent_improvement_loop.py`, `crawler/eval/benchmark_runner.py`, `crawler/eval/self_optimizer.py`)**
   - Replaced synthetic ground-truth report generators and fake score fallbacks with deprecation stubs that raise `NotImplementedError`, preventing fake substitute data generation.

5. **Live Conformance Gate Scaffold (`crawler/tests/test_live_phase74_conformance_gate.py`)**
   - Implemented `assert_phase74_conformance` and `test_live_phase74_conformance` enforcing `REQUIRE_LIVE_PHASE74_CONFORMANCE=1`.
   - Added contract unit tests verifying gate checks for live Copilot CLI provenance, 236 Worker case coverage, 23 batched Opus 4.8 `xhigh` `long_context` Judge sessions, sealed holdout commitments, and patch audit trails.

6. **Adversarial Test Suite (`crawler/tests/test_phase74_judge_loop.py`)**
   - Added comprehensive adversarial unit tests covering all 23 canonical target mappings, strict JSON proposal parsing, prompt injection XML escaping, holdout contamination rejection, stale sandbox cleanup, provenance path sanitization, diff bounds/control char/Markdown/safety checks, missing/NaN metric rejection, training safety regression, holdout dimension regression, fail-closed mean metrics, and pre-acceptance source byte identity.

## Verification Results

- Phase 74 contract & unit test suite: `poetry run pytest crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_phase74_judge_loop.py crawler/tests/test_live_phase74_conformance_gate.py -v` (43 passed, 1 skipped).
- Publish safety scan: `poetry run python scripts/check_publish_safe.py` (966 tracked files scanned, 0 violations).

## Deviations from Plan

Rule 1 & Rule 2:
- Hardened optimizer proposal validation, canonical skill path mapping, diff bounds scanning, finite metric checks, and shared optimizer evaluation across all 23 document types to ensure total safety before live baseline execution.
- Fixed candidate bundle wiring in `build_public_review_bundle` and `LoopOrchestrator`: included shared PDF review contract in public evidence bundles, added in-memory candidate overrides (`override_skill_content`, `override_shared_content`), and evaluated per-document and shared candidate proposals against candidate bundles while keeping disk source untouched prior to acceptance.

## Known Stubs

None - all code paths are fully wired and functional.

## Self-Check: PASSED

- FOUND: `crawler/eval/genuine_optimizer.py`
- FOUND: `crawler/eval/patch_evaluator.py`
- FOUND: `crawler/eval/loop_orchestrator.py`
- FOUND: `crawler/tests/test_live_phase74_conformance_gate.py`

