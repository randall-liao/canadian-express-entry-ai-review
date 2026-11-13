---
phase: 72-per-document-research-agents-gemini-3-6-flash-long-context
verified: 2026-07-23T01:10:00Z
status: passed
score: 16/16 must-haves verified
overrides_applied: 0
requirements_checked:
  - DOC_RESEARCH-01
  - REAL_AGENT_EXECUTION-01
verification_debt: 1
---

# Phase 72: Per-Document Research Agents (Gemini 3.6 Flash long context) Verification Report

**Phase Goal:** Run one dedicated Gemini 3.6 Flash long-context GitHub Copilot CLI research agent for each of the 23 Express Entry document types and produce validated, source-rich failure-mode reports in isolated per-document pipeline directories.
**Verified:** 2026-07-23T01:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All 23 ExpressEntryDocType values have exactly one isolated research report produced by a dedicated Gemini 3.6 Flash agent | ✓ VERIFIED | 23 pipeline directories under `crawler/eval/pipelines/<doc_type>/research/` each contain a valid `research.json` and `research_summary.md`. Tested via `verify_live_conformance`. |
| 2 | Every policy assertion is backed by authoritative IRCC/Justice Laws evidence and local-corpus verification; third-party discovery evidence remains explicitly labeled | ✓ VERIFIED | `verify_policy_assertion_locally` in `crawler/eval/doc_researcher.py` queries `corpus/index.db` via `crawler.cli --json search`, confirming exact quotes and citations for all `authoritative` failure modes. |
| 3 | Schema, citation, uniqueness, and cross-pipeline isolation validation passes for all research artifacts | ✓ VERIFIED | `test_doc_research_conformance.py` passed 9/9 assertions with zero errors across all 23 pipelines. |
| 4 | Failed live research is reported as blocked after bounded retries; no generic fallback is counted as successful research | ✓ VERIFIED | Failures unlink `research.json` and write `research.error.json` with status `"failed"`. Zero generic fallback templates exist in production outputs. Tested in `test_blocked_pipeline_no_fallback`. |
| 5 | Every successful research artifact includes provenance for an actual GitHub Copilot CLI Gemini agent invocation | ✓ VERIFIED | Every `research.json` contains `execution` metadata with `engine: "copilot-cli"`, `model: "gemini-3.6-flash"`, a sanitized command containing `--context long_context`, `online_research_performed: true`, tool calls (`web_search`), and a 64-character SHA256 `provenance_token`. |
| 6 | Doc researcher runner enforces Pydantic schema validation for all failure mode fields | ✓ VERIFIED | Pydantic models `AuthorityClassification`, `FailureMode`, and `ResearchReport` strictly enforce schema compliance in `crawler/eval/doc_researcher.py`. Tested in `test_research_schema_validation`. |
| 7 | Copilot CLI execution failure raises CopilotExecutionError without emitting fallback JSON | ✓ VERIFIED | Tested in `test_blocked_pipeline_no_fallback` in `crawler/tests/test_doc_researcher.py`. |
| 8 | Executable discovery locates copilot portably via COPILOT_PATH or PATH | ✓ VERIFIED | `_discover_copilot_executable()` handles `COPILOT_PATH`, `shutil.which("copilot")`, or raises clear error. Tested in `test_copilot_executable_discovery`. |
| 9 | Copilot CLI executes inside a per-document isolated staging working directory | ✓ VERIFIED | Execution staged in `_PIPELINES_DIR / doc_type / "research"`. Tested in `test_staging_directory_isolation`. |
| 10 | Research agents run with bounded concurrency (max_workers=4) across all 23 document types | ✓ VERIFIED | `research_all_document_types` uses `ThreadPoolExecutor(max_workers=4)`. Tested in `test_concurrent_execution_isolation`. |
| 11 | Each document pipeline produces both machine-readable JSON and human-readable Markdown summary | ✓ VERIFIED | 23 `research.json` and 23 `research_summary.md` files generated. Tested in `test_summary_markdown_and_provenance` and `test_research_summary_markdown_exists`. |
| 12 | Execution metadata records true engine, model, duration, command, and provenance token without false claims | ✓ VERIFIED | Tested in `test_live_copilot_runner_provenance` and verified across all 23 live pipeline outputs. |
| 13 | Failed pipelines cleanly unlink research.json to prevent stale success survival | ✓ VERIFIED | Unlink logic in `doc_researcher.py` verified in `test_blocked_pipeline_no_fallback`. |
| 14 | Conformance test suite enforces schema, source quality, citation presence, uniqueness, and isolation | ✓ VERIFIED | `REQUIRE_LIVE_RESEARCH_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_doc_research_conformance.py` passed 9/9 tests. |
| 15 | Live Copilot CLI research pass executed across all 23 Express Entry document types | ✓ VERIFIED | All 23 `research.json` files contain live execution metadata (`is_live: true`, returncode: 0, tool_calls: `["web_search", ...]`). |
| 16 | All 23 research reports pass 100% of conformance assertions | ✓ VERIFIED | `verify_live_conformance(_PIPELINES_DIR)` returned 0 errors across all 23 document types. |

**Score:** 16/16 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `crawler/eval/doc_researcher.py` | Refactored research agent runner with Pydantic schemas, isolated execution, local corpus grounding, and concurrent orchestrator | ✓ VERIFIED | 829 lines. Defines `ResearchReport`, `FailureMode`, `AuthorityClassification`, `verify_policy_assertion_locally`, `research_document_failure_modes`, `research_all_document_types`, `generate_research_summary_md`. |
| `crawler/tests/test_doc_researcher.py` | Unit contract test suite | ✓ VERIFIED | 753 lines, 20 test cases. |
| `crawler/tests/test_doc_research_conformance.py` | 23-document pipeline conformance test suite | ✓ VERIFIED | 524 lines, 9 test cases including the explicitly enabled live gate. |
| 23 x `crawler/eval/pipelines/<doc_type>/research/research.json` | Schema-validated machine-readable research reports for all 23 document types | ✓ VERIFIED | 23 files present, 100% schema compliant, authenticated with SHA256 provenance tokens. |
| 23 x `crawler/eval/pipelines/<doc_type>/research/research_summary.md` | Human-readable Markdown summary reports for all 23 document types | ✓ VERIFIED | 23 files present, cleanly formatted with executive summaries and failure mode tables. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `crawler/eval/doc_researcher.py` | `crawler.synthetic.schemas.ExpressEntryDocType` | `from crawler.synthetic.schemas import ExpressEntryDocType` | ✓ WIRED | Imports and iterates over all 23 `ExpressEntryDocType` enum members. |
| `crawler/eval/doc_researcher.py` | `corpus/index.db` | `crawler.cli --json search` subprocess call | ✓ WIRED | Grounding gate executes local corpus search and verifies quotes against SQLite chunk text in `corpus/index.db`. |
| `crawler/eval/doc_researcher.py` | `crawler/eval/pipelines/<doc_type>/research/research.json` | JSON artifact output | ✓ WIRED | Writes validated `ResearchReport` dict to per-document pipeline JSON file. |
| `crawler/eval/doc_researcher.py` | `crawler/eval/pipelines/<doc_type>/research/research_summary.md` | Markdown summary output | ✓ WIRED | Writes formatted Markdown summary to per-document pipeline file. |
| `crawler/tests/test_doc_research_conformance.py` | `crawler/synthetic/schemas.py` | Enum iteration | ✓ WIRED | Iterates over all 23 document types to enforce strict conformance. |
| `crawler/tests/test_doc_research_conformance.py` | `crawler/eval/pipelines/*/research/research.json` | Conformance validation pass | ✓ WIRED | Loads and verifies schema, provenance, citations, quotes, and uniqueness across all 23 JSON reports. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `doc_researcher.py` | `raw_llm_json` | Subprocess call `copilot --model gemini-3.6-flash --context long_context --available-tools web_search,web_fetch` | Yes — live Copilot agent session performs online web searches and yields JSON payload | ✓ FLOWING |
| `doc_researcher.py` | `local_corpus_verified`, `local_corpus_citations`, `local_corpus_evidence` | `_cite_local_corpus_chunk` / `corpus/index.db` | Yes — queries local corpus index and validates exact chunk text matches | ✓ FLOWING |
| `doc_researcher.py` | `execution` metadata | Execution timing, command flags, prompt/output SHA256, tool call logs | Yes — records true process metadata and computes SHA256 provenance token | ✓ FLOWING |
| `research.json` | `failure_modes` | Gemini 3.6 Flash agent output + grounding gate validation | Yes — 23 JSON reports contain >=3 source-rich failure modes with real URLs and citations | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Discover Copilot executable | `.venv/bin/python -c "from crawler.eval.doc_researcher import _discover_copilot_executable; assert _discover_copilot_executable()"` | Executable resolved through configured environment/PATH | ✓ PASS |
| Unit test suite | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py -v` | 20 passed in 0.36s | ✓ PASS |
| Live research conformance gate | `REQUIRE_LIVE_RESEARCH_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_doc_research_conformance.py -v` | 9 passed in 0.53s | ✓ PASS |
| Direct live conformance verification | `.venv/bin/python -c "from crawler.eval.doc_researcher import _PIPELINES_DIR; from crawler.tests.test_doc_research_conformance import verify_live_conformance; assert len(verify_live_conformance(_PIPELINES_DIR)) == 0"` | 0 errors returned across all 23 production pipelines | ✓ PASS |
| Publish-safe check | `.venv/bin/python scripts/check_publish_safe.py` | Tracked files scanned, 0 violations | ✓ PASS |

### Verification Debt

- `crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts` exceeded a 20-minute diagnostic timeout. All tests before it passed through 45%, and the 841 tests after `test_dupaudit.py` passed with 1 skip and 893 subtests. This pre-existing duplicate-audit performance concern is deferred to the Phase 75 release gate; it does not invalidate the Phase 72 targeted, live, security, or publish-safety gates.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| `DOC_RESEARCH-01` | 72-01, 72-02, 72-03 | Run one dedicated Gemini 3.6 Flash long-context research agent for each of the 23 Express Entry document types and produce validated, source-rich failure-mode reports in isolated per-document pipeline directories. | ✓ SATISFIED | 23 isolated per-document research pipelines created beneath `crawler/eval/pipelines/<doc_type>/research/` containing 23 `research.json` and 23 `research_summary.md` files verified by `test_doc_research_conformance.py`. |
| `REAL_AGENT_EXECUTION-01` | 72-01, 72-02, 72-03 | Execute every claimed researcher role through a real GitHub Copilot CLI agent session with the assigned model/context/effort; production failures must be explicit and no deterministic or hardcoded substitute may be reported as model output. | ✓ SATISFIED | All 23 research artifacts contain authentic execution provenance for `copilot-cli` with `gemini-3.6-flash`, `long_context`, `is_live: true`, tool call logs, and SHA256 provenance tokens. Zero fallbacks or generic templates exist. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| - | - | None | Info | Clean codebase. Zero TBD, FIXME, XXX, TODO, HACK, or PLACEHOLDER markers in Phase 72 files. `check_publish_safe.py` passed with 0 violations. |

### Human Verification Required

None. All checks are fully automated and verified via live unit and conformance test suites.

### Gaps Summary

Zero gaps identified. Phase 72 goal achieved in full codebase evidence.

---

_Verified: 2026-07-23T01:10:00Z_
_Verifier: gsd-verifier_
