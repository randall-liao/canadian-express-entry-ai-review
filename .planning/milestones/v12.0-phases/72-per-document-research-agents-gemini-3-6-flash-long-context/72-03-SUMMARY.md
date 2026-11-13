---
phase: 72-per-document-research-agents-gemini-3-6-flash-long-context
plan: 03
subsystem: eval
tags:
  - gemini-3.6-flash
  - long-context
  - per-document-research
  - live-conformance
  - copilot-cli
dependency_graph:
  requires:
    - 72-01
    - 72-02
  provides:
    - 23 Express Entry document pipeline research reports (research.json and research_summary.md)
  affects:
    - crawler/eval/pipelines/*/research/
tech_stack:
  added: []
  patterns:
    - Live 23-agent research execution via Copilot CLI with Gemini 3.6 Flash long context
    - Bounded parallel process execution (max_workers=4) with per-document directory isolation
    - Live-only research conformance gate validation without fallback or synthetic seeding
key_files:
  created:
    - crawler/eval/pipelines/*/research/research.json
    - crawler/eval/pipelines/*/research/research_summary.md
  modified:
    - crawler/eval/doc_researcher.py
decisions:
  - "Extracted toolName/mcpToolName from JSONL tool.execution_start events to accommodate Copilot CLI 1.0.73 tool payload structures."
  - "Used unique per-document type prefix abbreviations in _build_research_prompt to ensure non-colliding PFL failure IDs across all 23 pipelines."
metrics:
  duration_seconds: 980
  completed_date: "2026-07-22"
---

# Phase 72 Plan 03: Live 23-Agent Gemini 3.6 Flash Research Pass Summary

## Substantive Summary
Executed the live 23-agent research pass using real GitHub Copilot CLI processes powered by `gemini-3.6-flash` long context across all 23 Express Entry document types. Produced 46 publish-safe, schema-validated research artifacts (23 `research.json` manifests and 23 `research_summary.md` summaries) in isolated pipeline directories under `crawler/eval/pipelines/<doc_type>/research/`. Verified 100% pass rate on the live research conformance gate (`test_live_research_conformance_gate`) and the complete Phase 72 targeted test suite with zero fallback or generic template findings.

## Task Accomplishments

### Task 1: Execute live 23-agent Gemini 3.6 Flash long-context research pass
- Launched 23 real Copilot CLI agent sessions in bounded parallel batches (`max_workers=4`) using `--model gemini-3.6-flash`, `--context long_context`, and `--available-tools web_search,web_fetch`.
- Each agent performed online web search discovery for real-world IRCC refusal cases, PFL triggers, and common applicant mistakes for its assigned Express Entry document type.
- Generated 23 valid `research.json` manifests and 23 `research_summary.md` reports with authentic execution provenance (`engine: copilot-cli`, `is_live: true`, returncode 0, valid SHA256 provenance tokens, and online web search tool events).

### Task 2: Run 23-document pipeline conformance verification and test suite sign-off
- Executed `REQUIRE_LIVE_RESEARCH_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_doc_research_conformance.py::TestDocResearchConformance::test_live_research_conformance_gate -v` and confirmed green sign-off across all 23 pipelines.
- Executed the full Phase 72 targeted test suite (`.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py crawler/tests/test_doc_research_conformance.py -v`) with 29/29 tests passing.
- Confirmed total absence of fallback research findings, generic placeholder titles, raw JSONL/prompt leaks, or cross-pipeline directory contamination.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Extended tool call extraction for Copilot CLI 1.0.73 JSONL events**
- **Found during:** Task 1 initial live execution.
- **Issue:** Copilot CLI 1.0.73 emitted `"toolName"` and `"mcpToolName"` in `"tool.execution_start"` event data objects, causing `_parse_copilot_jsonl_output` to miss recorded `web_search` tool calls when checking only `"tool_name"`.
- **Fix:** Updated `_parse_copilot_jsonl_output` in `crawler/eval/doc_researcher.py` to extract `"toolName"`, `"tool_name"`, and `"mcpToolName"` from event data.
- **Files modified:** `crawler/eval/doc_researcher.py`
- **Commit:** `507cbda`

**2. [Rule 1 - Bug] Unique failure ID prefixing for multi-word document types**
- **Found during:** Task 2 live conformance gate execution.
- **Issue:** Truncating `doc_type.upper()[:8]` produced `"PROOF_OF"` for `proof_of_studies`, `proof_of_other_name`, and `proof_of_funds`, resulting in duplicate failure IDs (`PFL-PROOF_OF-01`) across those pipelines.
- **Fix:** Added `_get_doc_type_prefix(doc_type)` helper in `crawler/eval/doc_researcher.py` to generate unique prefix tags (e.g. `POS_STUD`, `POON_NAME`, `POF_FUND`) for prompt failure ID examples, and re-executed agents for affected document types.
- **Files modified:** `crawler/eval/doc_researcher.py`, `crawler/eval/pipelines/proof_of_studies/research/*`, `crawler/eval/pipelines/proof_of_other_name/research/*`
- **Commit:** `507cbda`

## Known Stubs
None. All 23 research manifests and summaries contain authentic, live-retrieved IRCC research data and validated local corpus citations.

## Self-Check: PASSED
- [x] All 23 `research.json` files exist in `crawler/eval/pipelines/<doc_type>/research/`.
- [x] All 23 `research_summary.md` files exist in `crawler/eval/pipelines/<doc_type>/research/`.
- [x] Commit `507cbda` contains all 46 research artifacts and `crawler/eval/doc_researcher.py`.
- [x] Live conformance gate (`test_live_research_conformance_gate`) passed 100%.
- [x] Targeted test suite (`test_doc_researcher.py` and `test_doc_research_conformance.py`) passed 29/29.
