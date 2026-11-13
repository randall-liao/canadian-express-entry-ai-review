---
phase: 72-per-document-research-agents-gemini-3-6-flash-long-context
plan: "01"
subsystem: testing
tags: [pydantic, copilot-cli, gemini-3.6-flash, corpus-crawler, grounding-gate]

requires:
  - phase: 71-multi-cli-conformance-re-verification-publish-safety-release-gate
    provides: Conformance verification gate and publish safety baseline
provides:
  - Refactored doc_researcher with Pydantic schema validation, local corpus grounding, and fail-closed blocked behavior
  - Unit contract test suite in crawler/tests/test_doc_researcher.py
affects:
  - 72-per-document-research-agents-gemini-3-6-flash-long-context
  - 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co

tech-stack:
  added: []
  patterns:
    - Pydantic BaseModel validation for ResearchReport and FailureMode schemas
    - Local corpus grounding gate cross-checking via corpus-crawler --json search
    - Subprocess execution isolation in per-document staging directories
    - Portable executable discovery via COPILOT_PATH env var and PATH lookup with explicit missing-dependency failure

key-files:
  created:
    - crawler/tests/test_doc_researcher.py
  modified:
    - crawler/eval/doc_researcher.py

key-decisions:
  - "Fail closed on Copilot execution errors: unlink stale research.json and write research.error.json without generating fake fallback success data"
  - "Downgrade unverified policy assertions from authoritative to discovery status when local corpus search yields zero hits"
  - "Stage Copilot execution inside per-document pipeline working directory (crawler/eval/pipelines/<doc_type>/research/) rather than repo root"

patterns-established:
  - "Pattern 1: Fail-closed agent execution recording status: failed in research.error.json"
  - "Pattern 2: Test double dependency injection via copilot_runner parameter"

requirements-completed:
  - DOC_RESEARCH-01
  - REAL_AGENT_EXECUTION-01

duration: 10m
completed: 2026-07-22
---

# Phase 72 Plan 01: Refactored Document Research Runner & Unit Contract Suite Summary

**Truthful Gemini 3.6 Flash research agent runner with Pydantic schema enforcement, fail-closed error recording, portable Copilot CLI discovery, per-document staging isolation, and local corpus grounding gate.**

## Performance

- **Duration:** 10m
- **Started:** 2026-07-22T22:52:41Z
- **Completed:** 2026-07-22T23:02:41Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Refactored `crawler/eval/doc_researcher.py` to eliminate all success-shaped generic fallbacks and enforce strict Pydantic `ResearchReport` / `FailureMode` schema validation covering all D-05/D-06 failure mode fields.
- Integrated portable executable discovery (`_discover_copilot_executable()`) supporting `COPILOT_PATH` env var and PATH lookup with explicit `CopilotExecutionError` on missing executable, eliminating machine-specific absolute fallbacks (WR-01).
- Isolated Copilot execution inside per-document staging working directories (`_PIPELINES_DIR / doc_type / "research"`) and enforced capability isolation using `--model gemini-3.6-flash`, `--context long_context`, `--available-tools web_search,web_fetch`, `--allow-all-tools`, `--allow-all-urls`, `--disallow-temp-dir`, `--no-ask-user`, `--no-custom-instructions`, and eliminating `--allow-all`, `--yolo`, `--allow-all-paths`, `--allow-tool`, and invalid tool names (WR-02, D-01, D-03, D-09).
- Integrated local corpus grounding gate (`verify_policy_assertion_locally`) invoking `corpus-crawler --json search`, populating `local_corpus_verified` and `local_corpus_citations`, and automatically downgrading ungrounded policy claims to `discovery` status (D-04, D-06).
- Supported explicit test double dependency injection via `copilot_runner` parameter (D-14).
- Created comprehensive unit contract test suite in `crawler/tests/test_doc_researcher.py` (7 unit tests, all passing).

## Task Commits

Each task was committed atomically:

1. **Task 1: Create unit contract test suite in crawler/tests/test_doc_researcher.py** - `acd85e5` (test)
2. **Task 2 & 3: Refactor crawler/eval/doc_researcher.py and integrate grounding gate** - `d7da49c` (feat)
3. **Fix: Enforce portable executable discovery and capability isolation** - `78777d7` (fix)

## Files Created/Modified

- `crawler/tests/test_doc_researcher.py` - Unit contract test suite verifying schema validation, fail-closed blocked behavior, executable discovery, capability isolation flags, staging isolation, and grounding gate.
- `crawler/eval/doc_researcher.py` - Refactored per-document research agent runner module with Pydantic schema enforcement, capability isolation, local corpus search integration, and fail-closed error recording.

## Decisions Made

- Fail closed on Copilot execution errors: when Copilot CLI fails or returns invalid output, unlink any existing `research.json` and write `research.error.json` with `status: "failed"` rather than returning hardcoded success fallback JSON.
- Automatically reclassify unverified policy assertions from `authoritative` to `discovery` status when `corpus-crawler --json search` returns zero hits.
- Execute Copilot CLI in the pipeline's per-document staging directory to maintain strict boundary isolation.
- Enforce capability isolation structurally by restricting `--available-tools` to online research tools (`web_search,web_fetch`), passing `--allow-all-tools`, `--allow-all-urls`, `--disallow-temp-dir`, using `--context long_context`, `--no-ask-user`, `--no-custom-instructions`, and omitting `--allow-all`, `--yolo`, `--allow-all-paths`, `--allow-tool`, and `fetch_web_page`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected Copilot executable discovery and capability isolation**
- **Found during:** Post-Wave 1 audit review
- **Issue:** `_discover_copilot_executable()` reintroduced a machine-specific absolute fallback path, and Copilot execution lacked `--context long_context` and structural tool restriction (`--available-tools`), relying on `--allow-all`.
- **Fix:** Removed the machine-specific fallback; raised explicit `CopilotExecutionError` when neither `COPILOT_PATH` nor `shutil.which("copilot")` resolves. Replaced `--allow-all` with `--context long_context`, `--available-tools web_search,web_fetch`, `--allow-all-tools` within that filtered tool set, `--allow-all-urls`, `--disallow-temp-dir`, `--no-ask-user`, and `--no-custom-instructions`. Added unit test `test_copilot_command_and_capability_isolation`.
- **Files modified:** `crawler/eval/doc_researcher.py`, `crawler/tests/test_doc_researcher.py`, `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-01-SUMMARY.md`

**2. [Rule 1 - Bug] Corrected Copilot CLI tool names and capability flags based on live probe**
- **Found during:** Live GitHub Copilot CLI capability probe
- **Issue:** `doc_researcher.py` used invalid tool name `fetch_web_page` and invalid argument `--allow-tool web_search,fetch_web_page`.
- **Fix:** Updated Copilot CLI command flags to use `--available-tools web_search,web_fetch`, `--allow-all-tools`, `--allow-all-urls`, `--disallow-temp-dir`, `--no-ask-user`, `--no-custom-instructions`, `-s`, removing `--allow-tool` and correcting `fetch_web_page` to `web_fetch`. Updated unit test assertions in `crawler/tests/test_doc_researcher.py`.
- **Files modified:** `crawler/eval/doc_researcher.py`, `crawler/tests/test_doc_researcher.py`, `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-01-SUMMARY.md`

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- FOUND: `crawler/tests/test_doc_researcher.py`
- FOUND: `crawler/eval/doc_researcher.py`
- FOUND commit `acd85e5`: `test(72-01): create unit contract test suite for doc_researcher`
- FOUND commit `d7da49c`: `feat(72-01): refactor doc_researcher for schema enforcement, isolation, and grounding gate`

## Next Phase Readiness

- `doc_researcher.py` and its unit contract test suite are fully updated and passing.
- Ready for plan 72-02 execution.

---
*Phase: 72-per-document-research-agents-gemini-3-6-flash-long-context*
*Completed: 2026-07-22*
