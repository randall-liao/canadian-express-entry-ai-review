---
phase: 72-per-document-research-agents-gemini-3-6-flash-long-context
reviewed: 2026-07-23T00:10:00Z
depth: deep
files_reviewed: 49
files_reviewed_list:
  - crawler/eval/doc_researcher.py
  - crawler/tests/test_doc_researcher.py
  - crawler/tests/test_doc_research_conformance.py
  - crawler/eval/pipelines/adoption_certificate/research/research.json
  - crawler/eval/pipelines/adoption_certificate/research/research_summary.md
  - crawler/eval/pipelines/authority_to_release_info/research/research.json
  - crawler/eval/pipelines/authority_to_release_info/research/research_summary.md
  - crawler/eval/pipelines/birth_certificate/research/research.json
  - crawler/eval/pipelines/birth_certificate/research/research_summary.md
  - crawler/eval/pipelines/certificate_of_qualification/research/research.json
  - crawler/eval/pipelines/certificate_of_qualification/research/research_summary.md
  - crawler/eval/pipelines/certified_translation/research/research.json
  - crawler/eval/pipelines/certified_translation/research/research_summary.md
  - crawler/eval/pipelines/death_certificate/research/research.json
  - crawler/eval/pipelines/death_certificate/research/research_summary.md
  - crawler/eval/pipelines/digital_photo/research/research.json
  - crawler/eval/pipelines/digital_photo/research/research_summary.md
  - crawler/eval/pipelines/divorce_certificate/research/research.json
  - crawler/eval/pipelines/divorce_certificate/research/research_summary.md
  - crawler/eval/pipelines/educational_credential_assessment/research/research.json
  - crawler/eval/pipelines/educational_credential_assessment/research/research_summary.md
  - crawler/eval/pipelines/employment_reference_letter/research/research.json
  - crawler/eval/pipelines/employment_reference_letter/research/research_summary.md
  - crawler/eval/pipelines/language_test/research/research.json
  - crawler/eval/pipelines/language_test/research/research_summary.md
  - crawler/eval/pipelines/letter_of_explanation/research/research.json
  - crawler/eval/pipelines/letter_of_explanation/research/research_summary.md
  - crawler/eval/pipelines/marriage_certificate/research/research.json
  - crawler/eval/pipelines/marriage_certificate/research/research_summary.md
  - crawler/eval/pipelines/medical_examination/research/research.json
  - crawler/eval/pipelines/medical_examination/research/research_summary.md
  - crawler/eval/pipelines/passport/research/research.json
  - crawler/eval/pipelines/passport/research/research_summary.md
  - crawler/eval/pipelines/police_certificate/research/research.json
  - crawler/eval/pipelines/police_certificate/research/research_summary.md
  - crawler/eval/pipelines/proof_of_funds/research/research.json
  - crawler/eval/pipelines/proof_of_funds/research/research_summary.md
  - crawler/eval/pipelines/proof_of_other_name/research/research.json
  - crawler/eval/pipelines/proof_of_other_name/research/research_summary.md
  - crawler/eval/pipelines/proof_of_studies/research/research.json
  - crawler/eval/pipelines/proof_of_studies/research/research_summary.md
  - crawler/eval/pipelines/relative_in_canada/research/research.json
  - crawler/eval/pipelines/relative_in_canada/research/research_summary.md
  - crawler/eval/pipelines/statutory_declaration_common_law/research/research.json
  - crawler/eval/pipelines/statutory_declaration_common_law/research/research_summary.md
  - crawler/eval/pipelines/use_of_representative/research/research.json
  - crawler/eval/pipelines/use_of_representative/research/research_summary.md
  - crawler/eval/pipelines/written_job_offer_lmia/research/research.json
  - crawler/eval/pipelines/written_job_offer_lmia/research/research_summary.md
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: clean
---

# Phase 72: Post-Execution Truthful Agent & Isolation Review Report

**Reviewed:** 2026-07-23T00:10:00Z
**Depth:** deep
**Files Reviewed:** 49
**Status:** clean

---

## Executive Summary

A deep adversarial post-execution review was conducted across the Phase 72 implementation (`crawler/eval/doc_researcher.py`), unit and contract test suites (`crawler/tests/test_doc_researcher.py`, `crawler/tests/test_doc_research_conformance.py`), and all 46 live research artifacts across 23 Express Entry document pipelines (`crawler/eval/pipelines/*/research/research.json` and `research_summary.md`).

The review verified that all 10 Phase 72 verification requirements are fully satisfied:
1. **Genuine Copilot CLI Execution:** Invokes real Copilot CLI with `--model gemini-3.6-flash`, `--context long_context`, `--output-format json`, `--stream off`, and `--available-tools web_search,web_fetch`.
2. **Online Tool Event & Reasoning Isolation:** Verifies `web_search` tool execution events in JSONL output; ignores `assistant.reasoning` events and never parses or persists raw reasoning in payloads.
3. **Truthful Execution Provenance:** Distinguishes live subprocess calls (`engine: copilot-cli`, `is_live: true`) from test doubles (`engine: injected-test-runner`, `is_live: false`).
4. **Test Isolation:** Unit and conformance tests run in isolated `tempfile.TemporaryDirectory()` paths and cannot seed or mutate `crawler/eval/pipelines/`.
5. **Fail-Closed Semantics:** Removes stale success artifacts (`research.json` and `research_summary.md`), records `research.error.json`, and raises `CopilotExecutionError` on any subprocess, JSONL, schema, or grounding failure.
6. **Publish-Safe Provenance:** Persists sanitized command metadata (basename `copilot`, no absolute executable paths, no raw prompt text), `prompt_sha256`, `raw_output_sha256`, and SHA256 `provenance_token` without secrets or raw reasoning.
7. **Canonical Grounding Gate:** Employs canonical `corpus-crawler --json search` followed by `--cite <chunk_id>` and exact quote substring verification before setting `authority_classification: authoritative`; automatically downgrades ungrounded claims to `discovery`.
8. **Pipeline Directory Isolation:** Enforces directory path containment (`_assert_in_pipeline_dir`) and schedules 23 independent document pipelines via `ThreadPoolExecutor(max_workers=4)`.
9. **Live Conformance Enforcement:** Enforces strict live gate (`test_live_research_conformance_gate`) that fails explicitly on missing, blocked, injected, non-live, ungrounded, cross-pipeline, or fake artifacts.
10. **Live Artifact Quality:** All 46 live production artifacts were produced by live `gemini-3.6-flash` runs, pass Pydantic schema validation, contain zero PII, and contain no absolute paths or privileged data leaks.

---

## Pre-Execution Audit Findings Remediation Status

This table maps the original critical findings (CR-01 through CR-04) and warnings (WR-01, WR-02) identified during the pre-execution audit to their Phase 72 remediation status versus scope intentionally deferred to downstream Phases 73–75.

| Finding ID | Original Finding Description | Phase 72 Remediation Status | Scope Fixed in Phase 72 | Scope Deferred to Phases 73–75 |
| :--- | :--- | :--- | :--- | :--- |
| **CR-01** | Silent success-shaped fallbacks in live pipeline execution chains | **PARTIALLY FIXED** (Fixed for Phase 72) | Refactored `doc_researcher.py` to fail closed. On error, deletes stale success artifacts, writes `research.error.json`, and raises `CopilotExecutionError`. Live gate rejects non-live or blocked artifacts. | Silent fallbacks in `pipeline_worker.py` and `pipeline_judge.py` are deferred to Phase 74 (Worker/Judge agents). |
| **CR-02** | Fabrication of worker reports and reviews directly from ground truth | **DEFERRED** | Phase 72 research path (`doc_researcher.py`) does NOT read ground truth answer keys or fabricate worker reports. | Remediation of `agent_improvement_loop.py`, `benchmark_runner.py`, and `self_optimizer.py` is deferred to Phase 74 (Worker/Judge) and Phase 75 (Orchestration). |
| **CR-03** | False agent identity metadata in parallel judges, synthetic generator, and orchestrator | **PARTIALLY FIXED** (Fixed for Phase 72) | `doc_researcher.py` records truthful provenance metadata: `engine: copilot-cli` and `is_live: true` on live runs; `engine: injected-test-runner` and `is_live: false` on test doubles. | False model metadata in `doc_synthetic_generator.py` (Phase 73), `parallel_judge.py` / `judge_group_*.py` (Phase 74), and `autonomous_pipeline_orchestrator.py` (Phase 75) is deferred. |
| **CR-04** | Test suite validates fabricated fallbacks and ground truth leaks | **PARTIALLY FIXED** (Fixed for Phase 72) | Phase 72 test suites (`test_doc_researcher.py`, `test_doc_research_conformance.py`) verify genuine Copilot execution contracts, fail-closed errors, `web_search` tool call events, and live gate conformance without mutating repo trees. | Legacy test suites for worker/judge/optimizer loops (`test_agent_improvement_loop.py`, `test_benchmark_loop.py`, `test_parallel_judge.py`) are deferred to Phases 74–75. |
| **WR-01** | Hardcoded absolute path to Linuxbrew Copilot executable | **PARTIALLY FIXED** (Fixed for Phase 72) | Implemented `_discover_copilot_executable()` checking `COPILOT_PATH` env var and `shutil.which("copilot")`. Stored metadata sanitizes command to executable basename `copilot`. | Absolute path cleanup in `pipeline_worker.py`, `pipeline_judge.py`, `real_worker.py`, and `real_judge.py` is deferred to Phases 74–75. |
| **WR-02** | Blind worker prompt isolation flaw via `--allow-all` in repository root | **PARTIALLY FIXED** (Fixed for Phase 72) | `doc_researcher.py` sets `cwd` to isolated staging directory (`crawler/eval/pipelines/<doc_type>/research/`), enforces `--available-tools web_search,web_fetch`, and validates path containment (`_assert_in_pipeline_dir`). | Worker sandbox directory staging and prompt isolation are deferred to Phase 74. |

---

## Phase 72 Truthful Execution & Isolation Matrix

| Pipeline Component | Module / File(s) | Model & Context Setting | Engine & Live Provenance | Tool Restriction | Grounding Gate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Per-Document Researcher** | `crawler/eval/doc_researcher.py` | `gemini-3.6-flash`<br>`long_context` | `copilot-cli`<br>`is_live: true` | `web_search`<br>`web_fetch` | Canonical search + cite + verbatim quote membership |
| **Unit Contract Suite** | `crawler/tests/test_doc_researcher.py` | Test doubles via injection | `injected-test-runner`<br>`is_live: false` | Mocked JSONL events | Isolated temporary directory (`tmp_path`) |
| **Conformance Suite** | `crawler/tests/test_doc_research_conformance.py` | Live + Test Double validation | Validates live vs injected provenance | Mandatory `web_search` event check | Verifies exact local corpus quote resolution |
| **23 Pipeline Artifacts** | `crawler/eval/pipelines/*/research/` | `gemini-3.6-flash` | `copilot-cli`<br>`is_live: true` | Verified `web_search` tool call in JSONL stream | All 23 reports pass live conformance gate |

---

## Narrative Findings (AI Reviewer)

### IN-01: Verbatim Quote Extraction Fallback Substring Matching Edge Case

**File:** `crawler/eval/doc_researcher.py:398-405`
**Severity:** Info
**Issue:**
In `_extract_verbatim_quote`, when exact candidate string match (`cand in chunk_text`) fails and fallback normalized word matching is executed:
```python
first_w = words_chunk[i]
last_w = words_chunk[i + cand_len - 1]
idx1 = chunk_text.find(first_w)
```
Calling `chunk_text.find(first_w)` locates the *first* occurrence of `first_w` in `chunk_text`, which may precede word index `i` if `first_w` is a common word (e.g. "the", "passport"). The safety guard on line 403 (`if "join(extracted.split()).lower() == norm_cand`) correctly rejects incorrect extractions and falls through safely to return `None` (preventing corrupted quote returns). However, finding an earlier occurrence of `first_w` can cause valid candidate quotes to fail fallback extraction when `first_w` appears earlier in the chunk text.

**Fix Suggestion:**
Use `chunk_text.find(first_w, search_offset)` or perform word-index-aware offset tracking when searching for `first_w` in `chunk_text`.

---

## Summary & Sign-Off

- **Critical Issues:** 0
- **Warnings:** 0
- **Info Items:** 1
- **Status:** **clean**

All 23 Express Entry document research pipelines have been successfully executed with genuine GitHub Copilot CLI sessions powered by `gemini-3.6-flash` long context. All 46 output artifacts are publish-safe, schema-compliant, PII-free, and grounded in the local corpus or official IRCC operational guidance. Phase 72 is ready to advance to Phase 73 (Blind Synthetic Document Generation).

---
_Reviewed: 2026-07-23T00:10:00Z_
_Reviewer: gsd-code-reviewer_
_Depth: deep_
