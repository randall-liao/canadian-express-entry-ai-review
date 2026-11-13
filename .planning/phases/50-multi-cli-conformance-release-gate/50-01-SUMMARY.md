---
phase: 50-multi-cli-conformance-release-gate
plan: 01
subsystem: conformance
tags: [conformance, release-gate, multi-cli, privacy, grounding, safe-01-12, verify-01, verify-02]

requires:
  - phase: 49-agent-evaluation-iterative-self-improvement-loop
    provides: Benchmark runner and self-optimizer engine for document review evaluation
provides:
  - Multi-CLI release gate runner (scripts/run_multi_cli_conformance.py)
  - Multi-CLI conformance pytest suite (crawler/tests/test_multi_cli_conformance.py)
  - Structured release gate JSON report (reports/multi_cli_conformance_report.json)
affects: [51-user-guidance-production-release, release-packaging]

tech-stack:
  added: []
  patterns: [multi-cli-conformance-runner, 5-stage-release-gate, structured-json-release-report, adapter-pointer-verification, portable-skills-validation]

key-files:
  created:
    - scripts/run_multi_cli_conformance.py
    - crawler/tests/test_multi_cli_conformance.py
    - .planning/phases/50-multi-cli-conformance-release-gate/50-01-SUMMARY.md
  modified: []

key-decisions:
  - "Automated multi-CLI release gate runner executes 5 validation stages: AGENTS.md contracts, thin adapter pointers across 5 CLIs, portable skills interface, synthetic benchmark suite, and SAFE-01..12 privacy/grounding gate."
  - "Thin adapter pointers for Claude Code, GitHub Copilot, OpenAI Codex, Cursor, and Windsurf are verified to be under 35 lines, point to AGENTS.md, and enforce alwaysApply for Cursor."
  - "Portable skills interface integrity is verified across all skills markdown files to ensure zero vendor-specific tags (<anthropic:, <openai:)."
  - "Release gate emits a structured JSON report (reports/multi_cli_conformance_report.json) and exits 0 on PASS / 1 on FAIL."

patterns-established:
  - "5-Stage Multi-CLI Release Gate: Automated end-to-end verification covering instruction compliance, adapter pointers, portable skills, synthetic benchmarks, and SAFE-01..12 conformance."
  - "Structured Release Gate Reporting: Machine-readable JSON report with timestamp, overall status, stage summaries, and detailed check results."

requirements-completed: [VERIFY-01, VERIFY-02]

duration: 15min
completed: 2026-07-22
---

# Phase 50 Plan 01: Multi-CLI Conformance & Release Gate Summary

**Implemented the Multi-CLI Release Gate Runner (`scripts/run_multi_cli_conformance.py`) and Pytest Verification Suite (`crawler/tests/test_multi_cli_conformance.py`) fulfilling VERIFY-01 and VERIFY-02 requirements.**

## Accomplishments

1. **Multi-CLI Release Gate Runner (`scripts/run_multi_cli_conformance.py`)**:
   - Executes 5-stage release gate verification across all supported agent runtimes:
     a. `agents_md_contracts`: Verifies `AGENTS.md` syntax, roles, and tool contracts (`crawler/tests/test_instruction_eval.py`).
     b. `adapter_pointers`: Verifies thin adapter pointers across all 5 supported CLIs (`CLAUDE.md`, `.github/copilot-instructions.md`, `.codex/AGENTS.md`, `.cursor/rules/agents.mdc`, `.windsurfrules`).
     c. `portable_skills`: Verifies portable skills interface (`skills/README.md`, contract headers, `skills/pdf/SKILL.md`) and enforces zero vendor-specific tags.
     d. `synthetic_benchmark`: Verifies synthetic benchmark suite & ground truth evaluation (`test_benchmark_loop.py` & `test_pdf_synthetic.py`).
     e. `safe_conformance`: Executes complete SAFE-01..12 privacy containment and citation grounding gate (`scripts/run_conformance.py`).
   - Emits structured JSON release-gate report to `reports/multi_cli_conformance_report.json`.
   - Exits 0 on PASS and 1 on FAIL.

2. **Multi-CLI Conformance Pytest Suite (`crawler/tests/test_multi_cli_conformance.py`)**:
   - Pytest suite with 9 unit and integration tests covering:
     - End-to-end execution of `run_multi_cli_conformance`.
     - Direct verification of adapter pointers for all 5 CLIs.
     - Portable skills interface integrity and vendor tag checks.
     - AGENTS.md syntax and contract checks.
     - Synthetic benchmark suite checks.
     - SAFE-01..12 conformance gate checks.
     - Executable CLI entrypoint invocation via subprocess.
     - Failure handling for missing adapters or vendor-specific skill tags.
   - All 9 tests passed cleanly in 6.66s.

3. **Phase 50 Completion Summary (`50-01-SUMMARY.md`)**:
   - Documented completion of Phase 50 and fulfillment of VERIFY-01 and VERIFY-02 requirements.

## Files Created

- `scripts/run_multi_cli_conformance.py` - Multi-CLI release gate runner executable.
- `crawler/tests/test_multi_cli_conformance.py` - Pytest verification suite for multi-CLI conformance.
- `.planning/phases/50-multi-cli-conformance-release-gate/50-01-SUMMARY.md` - Phase completion summary document.

## Requirements Completed

- **VERIFY-01**: Automated conformance test suite verifies `AGENTS.md` system prompt and tool invocations across supported CLI agent runtimes.
- **VERIFY-02**: Multi-CLI release gate proves zero PII leakage, zero ungrounded advice, and SAFE-01..12 release gate compliance before final release.

## Verification

- Command executed: `.venv/bin/python -m pytest crawler/tests/test_multi_cli_conformance.py -v`
- Result: 9 passed in 6.66s.
