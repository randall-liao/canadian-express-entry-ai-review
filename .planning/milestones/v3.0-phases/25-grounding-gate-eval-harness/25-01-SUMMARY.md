---
phase: 25-grounding-gate-eval-harness
plan: 01
subsystem: grounding
tags: [grounding, citations, fts5, sqlite, unittest, fail-closed, stdlib]

# Dependency graph
requires:
  - phase: 24-search-cli-citation-resolver
    provides: "searchindex.resolve(db, chunk_id) — verbatim chunk dict or None on miss/sha-drift (GND-01 resolver)"
  - phase: 23-fts5-index-builder
    provides: "build_index + chunks table (chunk_id/relpath/source_url/section/crawl_date/text) the gate grounds on"
provides:
  - "crawler/grounding.py — pure-stdlib fail-closed grounding compute (GND-01/GND-02)"
  - "InvalidAnswer / _norm / quote_is_grounded / check_claim / check_answer / render_answer"
  - "whole-answer verdict shape {verdict,total_claims,grounded,ungrounded,violations}"
  - "crawler/tests/test_grounding.py — 15-test compute-layer unittest suite"
affects: [25-02-ground-cli-verb, 25-03-eval-harness, 26-checklist-pii, 27-document-agents]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-claim fail-closed grounding: resolve() in-process + verbatim-quote substring via _norm"
    - "Pure compute module (no I/O) so CLI/eval layers are thin consumers"
    - "Shape-validation (InvalidAnswer) distinct from grounding violation (verdict:fail)"

key-files:
  created:
    - crawler/grounding.py
    - crawler/tests/test_grounding.py
  modified: []

key-decisions:
  - "Quote normalization reuses eval_runner._norm semantics EXACTLY (whitespace-collapse + lowercase only) — no Unicode/curly/markdown folding"
  - "Gate checks ONLY claims[]; prose/basis/abstentions are never citation-checked (SC1)"
  - "Honesty boundary documented in module docstring: resolvability + verbatim-quote, NOT semantic entailment (VAL-01/02 deferred)"
  - "InvalidAnswer (malformed shape) is distinct from a fail-closed grounding violation"

patterns-established:
  - "check_claim returns list[str] of violation reasons (uncited/unresolvable/quote_not_in_chunk); empty == grounded"
  - "Synthetic tempdir index in setUp via searchindex.build_index — NEVER the real corpus/"

requirements-completed: [GND-01, GND-02]

# Metrics
duration: ~28min
completed: 2026-06-21
---

# Phase 25 Plan 01: Grounding Compute Module Summary

**Pure-stdlib fail-closed grounding core (`crawler/grounding.py`) that resolves every claim citation in-process via `searchindex.resolve` and verifies the verbatim quote is a whitespace/case-normalized substring of a resolving chunk — any uncited/unresolvable/quote-mismatch claim fails the whole answer (GND-01/GND-02).**

## Performance

- **Duration:** ~28 min
- **Started:** 2026-06-21T07:25:00Z (approx)
- **Completed:** 2026-06-21T07:54:01Z
- **Tasks:** 2
- **Files modified:** 2 created (1 module + 1 test suite)

## Accomplishments

- `crawler/grounding.py`: pure-stdlib compute module exporting the six locked symbols
  (`InvalidAnswer`, `_norm`, `quote_is_grounded`, `check_claim`, `check_answer`,
  `render_answer`) — imports limited to `re`, `pathlib.Path`, `crawler.searchindex`.
- Per-claim fail-closed grounding (GND-01/GND-02): empty/absent citations → `uncited`;
  every citation failing `resolve()` (unknown OR sha-drift) → `unresolvable`; resolving
  citation whose chunk lacks the normalized quote → `quote_not_in_chunk`; a claim passes
  iff ≥1 citation BOTH resolves AND contains the normalized quote.
- Whole-answer verdict (SC2): any single failing claim makes the verdict `fail`; returns
  `{verdict, total_claims, grounded, ungrounded, violations}`.
- Claims-only inspection (SC1): `prose`/`basis`/`abstentions` are never citation-checked.
- `render_answer` (SC5): renders each claim + its verbatim quote (blockquote) beside the
  resolved citation, ending with the honesty-boundary footer; no file I/O, no abs paths.
- `crawler/tests/test_grounding.py`: 15-test stdlib `unittest` suite over a synthetic
  tempdir index (NEVER the real `corpus/`), proving each fail-closed reason, grounded-pass,
  case/whitespace tolerance, SC1 filler-not-checked, invalid-shape raises, and SC5 render.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create crawler/grounding.py pure compute module** — `7ee9f76` (feat)
2. **Task 2: Create crawler/tests/test_grounding.py compute-layer suite** — `4235ca6` (test)

**Plan metadata:** see final docs commit (this SUMMARY + STATE.md + deferred-items.md).

## Files Created/Modified

- `crawler/grounding.py` (233 lines) — pure-stdlib fail-closed grounding compute: shape
  validation, per-claim resolve()+verbatim-quote check, whole-answer verdict, render.
- `crawler/tests/test_grounding.py` (227 lines) — 15-test compute-layer unittest suite.
- `.planning/phases/25-grounding-gate-eval-harness/deferred-items.md` — logged one
  pre-existing, out-of-scope failing test (see Issues Encountered).

## Decisions Made

- Reused `eval_runner._norm` semantics verbatim (`re.sub(r"\s+"," ",s).strip().lower()`) —
  whitespace-collapse + lowercase ONLY. Loosening this would silently widen the grounding
  guarantee, so no Unicode folding / curly-quote conversion / markdown stripping was added.
- The gate is a strict CONSUMER of `searchindex.resolve` (called in-process per citation);
  `crawler/searchindex.py` was not modified. A `None` from `resolve` (unknown id OR
  sha-drift) is treated as a fail-closed miss.
- `InvalidAnswer(ValueError)` distinguishes malformed input (CLI → `invalid_input`/exit 2
  in Plan 02) from a well-formed-but-ungrounded answer (`verdict:"fail"`).
- Honesty boundary stated verbatim in the module docstring: the gate guarantees citation
  resolvability + verbatim-quote presence, NOT semantic entailment (VAL-01/02 deferred —
  would need a model, violating the no-vectors/no-cloud constraint).

## Deviations from Plan

None - plan executed exactly as written. (The test's anti-leak assertion was authored to
check the real tempdir/db absolute paths rather than a hardcoded `/home/` literal, so the <!-- # publish-safe: allow -->
plan's acceptance grep for `corpus/index.db|/home/|/Users/` returns clean — this is a <!-- # publish-safe: allow -->
faithful implementation of the stated criterion, not a deviation.)

## Issues Encountered

- **Pre-existing, out-of-scope test failure (NOT caused by this plan):**
  `crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts`
  fails with `AssertionError: 0 not greater than or equal to 1` (`result.exact >= 1`). This
  was reproduced on a CLEAN tree BEFORE any 25-01 change — it asserts an exact-duplicate
  signal against the real git-ignored `corpus/`, wholly unrelated to grounding. Per the
  SCOPE BOUNDARY it was NOT fixed; logged to
  `.planning/phases/25-grounding-gate-eval-harness/deferred-items.md`.
- Full-suite result after this plan: **180 passed, 1 failed (the pre-existing dupaudit
  real-corpus test), 1 skipped, 59 subtests passed** — baseline was 165 passed / 1 failed /
  1 skipped, so the 15 new grounding tests are additive with ZERO regression.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_grounding.py -q` → **15 passed** (≥8 required).
- `-k "uncited or unresolvable or quote"` → 7 passed (the three fail-closed reasons asserted).
- `-k "filler or render"` → 4 passed (SC1 + SC5 honesty boundary asserted).
- `.venv/bin/python -m pytest crawler/tests/ -q` → 180 passed / 1 pre-existing fail / 1 skipped
  (no regression vs the 165-passed baseline).
- `grounding.py` exports the six symbols and calls `searchindex.resolve(` in-process; no
  abs-paths/secrets; no real `corpus/` path referenced in the test.

## User Setup Required

None - no external service configuration required (zero new dependencies; stdlib only).

## Next Phase Readiness

- The compute contract is ready for Plan 25-02 (the `ground` CLI verb — a thin consumer that
  maps `InvalidAnswer` → `invalid_input`/exit 2, emits the verdict envelope, and wires the
  RPT-03 render-then-scan-then-write step) and Plan 25-03 (the eval harness pointing the same
  gate at a tracked PII-free `questions.jsonl` fixture set).
- No blockers introduced. The pre-existing dupaudit real-corpus failure is deferred and
  unrelated to the grounding chain.

---
*Phase: 25-grounding-gate-eval-harness*
*Completed: 2026-06-21*

## Self-Check: PASSED

- FOUND: `crawler/grounding.py`
- FOUND: `crawler/tests/test_grounding.py`
- FOUND: `.planning/phases/25-grounding-gate-eval-harness/25-01-SUMMARY.md`
- FOUND: `.planning/phases/25-grounding-gate-eval-harness/deferred-items.md`
- FOUND commit: `7ee9f76` (Task 1 — feat: grounding compute module)
- FOUND commit: `4235ca6` (Task 2 — test: grounding compute-layer suite)
