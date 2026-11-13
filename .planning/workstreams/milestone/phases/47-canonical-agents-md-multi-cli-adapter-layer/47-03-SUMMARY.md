---
phase: 47-canonical-agents-md-multi-cli-adapter-layer
plan: 03
subsystem: testing
tags: [synthetic-fixtures, benchmark, instruction-eval, fail-closed-grounding, pii-containment]

requires:
  - phase: 47-01
    provides: Canonical AGENTS.md system specification at repository root
  - phase: 47-02
    provides: Thin multi-CLI pointer adapters and portable skills interface
provides:
  - Synthetic PII-free candidate profile and extraction benchmark fixtures
  - Complete 8-test instruction compliance, adapter pointer, and grounding evaluation suite
affects: [phase-48, multi-cli-conformance]

tech-stack:
  added: []
  patterns: [synthetic-benchmark-fixtures, instruction-eval-suite, fail-closed-grounding-verification]

key-files:
  created:
    - crawler/eval/synthetic_fixtures/candidate_fsw_pass.json
    - crawler/eval/synthetic_fixtures/candidate_cec_fail.json
    - crawler/eval/synthetic_fixtures/extractions_sample.json
  modified:
    - crawler/tests/test_instruction_eval.py

key-decisions:
  - "Synthetic evaluation benchmark fixtures use 100% fake PII data matching candidate profile and extraction schemas."
  - "Instruction evaluation test suite verifies AGENTS.md, adapter pointers, skills interface, synthetic fixture structures, and grounding gate fail-closed behavior."

requirements-completed: [AGENT-01, AGENT-02, AGENT-03, ADAPT-01, ADAPT-02]

completed: 2026-07-21
---

# Phase 47 Plan 03: Synthetic Benchmark Fixtures & Instruction Evaluation Suite Summary

**Established synthetic PII-free evaluation benchmark fixtures and completed the automated instruction evaluation test suite (`test_instruction_eval.py`).**

## Accomplishments

- Created directory `crawler/eval/synthetic_fixtures/` with 3 synthetic JSON fixtures (100% fake PII):
  - `candidate_fsw_pass.json`: Passing FSW candidate profile benchmark
  - `candidate_cec_fail.json`: Incomplete CEC candidate profile benchmark
  - `extractions_sample.json`: Synthetic document extractions sample benchmark
- Expanded `crawler/tests/test_instruction_eval.py` to 8 comprehensive test methods:
  - `test_agents_md_syntax`: Validates AGENTS.md core roles & tool contracts syntax
  - `test_grounding_rules`: Validates fail-closed grounding, AnswerObject schema, and quote rules
  - `test_review_workflows`: Validates 4-stage operational review subcommands
  - `test_adapter_pointers`: Validates thin pointer adapters (< 35 lines) for all 5 CLIs
  - `test_skills_interface`: Validates portable skills structure and contracts
  - `test_synthetic_fixtures_structure`: Validates synthetic benchmark JSON structures
  - `test_synthetic_fixtures_grounding`: Validates grounding gate over AnswerObject schema
  - `test_out_of_corpus_abstention`: Validates unresolvable claims yield fail-closed violations
- Verified full test suite execution: 8/8 tests PASSED green in 0.12s.

---
*Phase: 47-canonical-agents-md-multi-cli-adapter-layer*
*Completed: 2026-07-21*
