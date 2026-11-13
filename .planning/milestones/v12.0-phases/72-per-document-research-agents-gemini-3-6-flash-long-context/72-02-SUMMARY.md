---
phase: 72-per-document-research-agents-gemini-3-6-flash-long-context
plan: "02"
subsystem: evaluation
tags: [pydantic, copilot-cli, gemini-3.6-flash, concurrent, threadpoolexecutor, conformance]

requires:
  - phase: 72-per-document-research-agents-gemini-3-6-flash-long-context
    plan: "01"
    provides: Refactored doc_researcher with Pydantic schema validation, local corpus grounding, and fail-closed blocked behavior
provides:
  - Bounded concurrent 23-document agent orchestrator in crawler/eval/doc_researcher.py
  - Dual artifact generation (research.json and research_summary.md) with full execution provenance
  - 23-document pipeline conformance test suite in crawler/tests/test_doc_research_conformance.py
affects:
  - 72-per-document-research-agents-gemini-3-6-flash-long-context
  - 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co

tech-stack:
  added: []
  patterns:
    - ThreadPoolExecutor(max_workers=4) bounded concurrency across 23 ExpressEntryDocType pipelines
    - Path security containment assertions for per-document pipeline staging directories
    - Human-readable research_summary.md generation alongside machine-readable research.json
    - Full execution provenance recording with SHA256 provenance_token
    - 23-document pipeline conformance test suite

key-files:
  created:
    - crawler/tests/test_doc_research_conformance.py
  modified:
    - crawler/eval/doc_researcher.py
    - crawler/tests/test_doc_researcher.py

key-decisions:
  - "Bound concurrent research execution to ThreadPoolExecutor(max_workers=4) across all 23 ExpressEntryDocType values"
  - "Enforce strict per-document pipeline directory path containment before writing research artifacts"
  - "Produce dual artifacts (research.json and research_summary.md) for every successful research pipeline"
  - "Record full execution provenance (engine, model, timestamp, duration_seconds, command, returncode, provenance_token) without fake identity claims"

patterns-established:
  - "Pattern 1: Bounded concurrent multi-doc orchestration via ThreadPoolExecutor"
  - "Pattern 2: Dual artifact output (machine-readable JSON + human-readable Markdown)"
  - "Pattern 3: Complete execution provenance recording with SHA256 token"

requirements-completed:
  - DOC_RESEARCH-01
  - REAL_AGENT_EXECUTION-01

duration: 10m
completed: 2026-07-22
---

# Phase 72 Plan 02: Bounded Concurrent 23-Agent Research Orchestrator & Conformance Suite Summary

**Bounded concurrent 23-agent research orchestrator with ThreadPoolExecutor, dual artifact generation (`research.json` & `research_summary.md`), truthful SHA256 execution provenance recording, and 23-pipeline conformance test suite.**

## Performance

- **Duration:** 10m
- **Started:** 2026-07-22T23:05:00Z
- **Completed:** 2026-07-22T23:15:00Z
- **Tasks:** 3
- **Files created/modified:** 3

## Accomplishments

- Updated `research_all_document_types` in `crawler/eval/doc_researcher.py` with bounded concurrent execution using `ThreadPoolExecutor(max_workers=4)` across all 23 `ExpressEntryDocType` values (D-01, D-03).
- Implemented per-document directory path security assertion (`_assert_in_pipeline_dir`) verifying that every worker process writes exclusively within `crawler/eval/pipelines/<doc_type>/research/` (D-01, D-03, D-09, T-72-04 mitigation).
- Implemented human-readable summary generator `generate_research_summary_md` rendering `research_summary.md` with executive summary and structured failure modes table alongside `research.json` (D-08).
- Recorded complete execution provenance metadata in `research.json`: `status: "success"`, `engine: "copilot-cli"`, `model: "gemini-3.6-flash"`, ISO UTC `timestamp`, float `duration_seconds`, serialized `command`, subprocess exit status `returncode`, and 64-character SHA256 `provenance_token` (D-12, D-14).
- Added unit tests `test_concurrent_execution_isolation` and `test_summary_markdown_and_provenance` in `crawler/tests/test_doc_researcher.py`.
- Created 23-document pipeline conformance test suite in `crawler/tests/test_doc_research_conformance.py` enforcing pipeline isolation, Pydantic schema validity, refusal/PFL failure mode count (>= 3), absence of generic fallback content, dual artifact presence, cross-pipeline failure ID uniqueness, and zero cross-pipeline leakage across all 23 Express Entry document types (D-11).

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement bounded concurrent 23-document agent orchestrator in crawler/eval/doc_researcher.py** - `6911112` (feat)
2. **Task 2: Implement human summary generator and complete execution provenance metadata recording** - `bdc6786` (feat)
3. **Task 3: Create 23-document pipeline conformance test suite in crawler/tests/test_doc_research_conformance.py** - `11a34dc` (test)

## Files Created/Modified

- `crawler/eval/doc_researcher.py` - Updated with `ThreadPoolExecutor(max_workers=4)` concurrent runner across all 23 doc types, per-document path containment check `_assert_in_pipeline_dir`, summary generator `generate_research_summary_md`, and complete execution provenance recording.
- `crawler/tests/test_doc_researcher.py` - Updated with unit tests verifying concurrent execution across 23 document types, isolation, markdown summary rendering, and execution provenance attributes.
- `crawler/tests/test_doc_research_conformance.py` - Created 23-document pipeline conformance test suite enforcing schema, citation, uniqueness, isolation, and dual artifact rules across all pipelines.

## Decisions Made

- Bound concurrent multi-doc research execution to `ThreadPoolExecutor(max_workers=4)` across all 23 `ExpressEntryDocType` values.
- Enforce strict per-document pipeline directory path containment assertions (`_assert_in_pipeline_dir`) before writing any artifact.
- Render human-readable Markdown summary (`research_summary.md`) alongside `research.json` for every successful pipeline run.
- Record truthful execution provenance (`engine`, `is_live`, `model`, `timestamp`, `duration_seconds`, `command`, `returncode`, `provenance_token`) without false identity claims. Injected mock runners set `engine: injected-test-runner` and `is_live: False`, while real subprocess calls set `engine: copilot-cli` and `is_live: True`.

## Deviations from Plan

**1. [Rule 1 - Bug / Truthful Execution] Corrected non-live test runner provenance and isolated test pipeline outputs**
- **Found during:** Pre-live verification audit of Phase 72 Wave 2 setup.
- **Issue:** `test_doc_research_conformance.py::setUpModule` invoked mock runners against the real `crawler/eval/pipelines/` tree and recorded `engine: copilot-cli` on injected mock outputs.
- **Fix:**
  1. Updated `doc_researcher.py` to record `engine: injected-test-runner` and `is_live: False` when `copilot_runner` test double is injected, reserving `engine: copilot-cli` and `is_live: True` for genuine subprocess calls.
  2. Isolated unit and conformance tests to temporary pipeline roots (`tempfile.TemporaryDirectory()`), guaranteeing ordinary test runs leave `crawler/eval/pipelines/` untouched.
  3. Added a distinct live-only conformance gate (`test_live_research_conformance_gate`) enabled via `REQUIRE_LIVE_RESEARCH_CONFORMANCE=1` that reads `crawler/eval/pipelines/` without seeding or skipping, validating all 23 live reports, model `gemini-3.6-flash`, `long_context`, `web_search,web_fetch` capability restrictions, and live provenance.
  4. Added test cases (`test_injected_outputs_cannot_satisfy_live_gate` and `test_mocked_conformance_leaves_pipeline_tree_unchanged`) proving injected test outputs fail live gate validation and mock tests leave the repository tree untouched.
  5. Positively identified and removed 46 synthetic mock research artifacts (23 `research.json` + 23 `research_summary.md`) seeded in `crawler/eval/pipelines/` by the previous test setup.
- **Files modified:** `crawler/eval/doc_researcher.py`, `crawler/tests/test_doc_researcher.py`, `crawler/tests/test_doc_research_conformance.py`, `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-02-SUMMARY.md`.

**2. [Rule 1 / Rule 2 - Bug / Truthful Execution Proof] Implemented fail-closed JSONL event parsing and online tool call provenance**
- **Found during:** Final truthful-execution proof gap audit prior to Phase 72 Wave 3 live execution.
- **Issue:** Copilot CLI in silent text mode emitted unstructured stdout that could not prove online research (`web_search`) actually occurred.
- **Fix:**
  1. Updated Copilot CLI invocation in `doc_researcher.py` to pass `--output-format json` and `--stream off`.
  2. Implemented `_parse_copilot_jsonl_output` to parse stdout as JSONL line events, require a successful `tool.execution_start` event with `web_search`, extract ordered tool-call provenance (`tool_calls`, `tool_call_count`), and extract the final JSON report payload from the last assistant message event.
  3. Updated `_build_research_prompt` to mandate active `web_search` and `web_fetch`, require source URLs/excerpts, prohibit answering solely from model memory, and treat retrieved web content as untrusted external data.
  4. Recorded `online_research_performed: true`, tool call list/count, `output_format: "json"`, and `stream: "off"` in execution metadata without raw reasoning traces.
  5. Updated unit tests (`test_doc_researcher.py`) and live conformance suite (`test_doc_research_conformance.py`) to enforce JSONL parsing, mandatory `web_search` tool execution events, fail-closed error handling on malformed JSONL or missing tool events, and live gate conformance assertions.
- **Files modified:** `crawler/eval/doc_researcher.py`, `crawler/tests/test_doc_researcher.py`, `crawler/tests/test_doc_research_conformance.py`, `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-02-SUMMARY.md`.
- **Commit:** `21db259`

**3. [Rule 1 - Bug / Data Minimization] Excluded reasoning events from payload selection**
- **Found during:** Live JSONL provenance spot-check before the 23-agent run.
- **Issue:** The parser accepted every `assistant.*` event as a candidate final payload, so a later `assistant.reasoning` event containing JSON could supersede the actual `assistant.message`.
- **Fix:** Restrict payload candidates to `assistant.message` and canonical `result` events; add a regression fixture with a poisoned reasoning payload after the valid final message.
- **Files modified:** `crawler/eval/doc_researcher.py`, `crawler/tests/test_doc_researcher.py`.

**4. [Rule 1 / Rule 2 - Bug / Publish Safety & Corpus Verification] Sanitized persisted command and implemented exact quote citation resolution**
- **Found during:** Phase 72 pre-run hardening audit.
- **Issue:** `execution.command` persisted absolute Copilot executable paths and full `-p` prompt text in `research.json`, risking publish-safety violations and prompt leakage. In addition, policy grounding recorded hit IDs without verifying exact local corpus quotes.
- **Fix:**
  1. Sanitized `execution.command` to persist executable basename `copilot` without absolute paths or raw `-p` prompt text.
  2. Recorded `prompt_sha256` and `raw_output_sha256` in execution metadata.
  3. Replaced hit-only corpus verification with canonical `corpus-crawler --json search` and `corpus-crawler --json search --cite <chunk_id>` two-step flow.
  4. Extended `FailureMode` schema with `local_corpus_evidence: [{citation, quote}]` capturing exact verbatim quote substrings from `result.chunk.text`.
  5. Required `authority_classification: authoritative` failure modes to resolve citations and contain exact quotes, automatically downgrading unverified claims to `discovery` and clearing local evidence.
  6. Updated human summary markdown rendering to clearly label discovery vs authoritative and present local evidence only when verified.
  7. Updated unit test suite (`test_doc_researcher.py`) and live conformance suite (`test_doc_research_conformance.py`) to enforce exact quote resolution, citation downgrades, publish-safe metadata, and malformed envelope handling.
- **Files modified:** `crawler/eval/doc_researcher.py`, `crawler/tests/test_doc_researcher.py`, `crawler/tests/test_doc_research_conformance.py`, `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-02-SUMMARY.md`.
- **Commit:** `528c26c`

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- FOUND: `crawler/eval/doc_researcher.py`
- FOUND: `crawler/tests/test_doc_researcher.py`
- FOUND: `crawler/tests/test_doc_research_conformance.py`
- FOUND commit `6911112`: `feat(72-02): implement bounded concurrent 23-document agent orchestrator`
- FOUND commit `bdc6786`: `feat(72-02): implement human summary generator and complete execution provenance metadata recording`
- FOUND commit `11a34dc`: `test(72-02): create 23-document pipeline conformance test suite`
- FOUND commit `528c26c`: `fix(72-02): sanitize persisted command and enforce exact quote citation resolution`

## Next Phase Readiness

- All unit contract tests (9/9) in `test_doc_researcher.py` and conformance tests (6/6) in `test_doc_research_conformance.py` pass cleanly.
- Ready for live Gemini Flash research execution or phase completion.

---
*Phase: 72-per-document-research-agents-gemini-3-6-flash-long-context*
*Completed: 2026-07-22*
