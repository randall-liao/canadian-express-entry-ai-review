---
phase: 25-grounding-gate-eval-harness
plan: 03
subsystem: grounding
tags: [grounding, eval-harness, eval-runner, jsonl, fixture, must-abstain, pii, publish-safety, fail-closed, stdlib]

# Dependency graph
requires:
  - phase: 25-grounding-gate-eval-harness (Wave 1, 25-01)
    provides: "crawler/grounding.py — check_answer (the per-claim fail-closed gate run_eval reuses verbatim)"
  - phase: 25-grounding-gate-eval-harness (Wave 2, 25-02)
    provides: "crawler/cli.py::_cmd_ground + p_ground subparser (the verb --eval extends; the contract envelope)"
  - phase: 24-search-cli-citation-resolver
    provides: "searchindex.resolve(db, chunk_id) — the in-process resolver the grounded fixture lines resolve against"
  - phase: 15-publish-safe-hardening
    provides: "scripts/check_publish_safe.scan_text — the SAFE-02 abs-path/secret scanner reused for the tracked-fixture PII self-scan"
provides:
  - "crawler/grounding.py::run_eval(db, questions_path) -> (summary, exit_code) — gate-over-fixtures eval aggregator (locked eval_runner {total,passed,failed,failures} shape; exit 1 if any line ungrounded)"
  - "must_abstain abstention-correctness: a line carrying any claims fails with reason should_have_abstained"
  - "crawler/cli.py: --eval flag on p_ground + an eval-mode branch in _cmd_ground checked BEFORE any stdin read (never blocks on stdin)"
  - "crawler/eval/questions.jsonl — tracked, PII-free reference set (2 grounded lines that resolve verbatim against the real index + 2 adversarial must_abstain lines)"
  - "crawler/tests/test_grounding.py — TestRunEval + eval CLI cases + @skipUnless real-corpus integration + fixture PII self-scan + structural tests"
affects: [26-checklist-pii, 27-document-agents]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Gate-over-fixtures eval: the SAME check_answer gate run per stored answer line IS the eval harness (no document agent; agents are a Phase 27 concern)"
    - "Eval result is the LOCKED eval_runner {total,passed,failed,failures} shape; overall exit = 1 if failed else 0 (mirror eval_runner.main:135-150)"
    - "Eval mode is checked BEFORE any sys.stdin.read() so it never blocks on stdin (Pitfall 7); an ungrounded fixture line is a verdict (ok:true, in failures, exit 1), not an execution error"
    - "Tracked fixture share-safety: a NON-skip-guarded PII self-scan runs check_publish_safe.scan_text + raw abs-path/pr-ai-venv string checks over the committed fixture bytes (T-25-11 mitigation)" <!-- # publish-safe: allow -->

key-files:
  created:
    - crawler/eval/questions.jsonl
  modified:
    - crawler/grounding.py
    - crawler/cli.py
    - crawler/tests/test_grounding.py

key-decisions:
  - "run_eval reuses check_answer per line (no parallel gate); must_abstain lines are graded for abstention-correctness only (empty claims[] required), non-abstain lines by the normal gate"
  - "Result shape locked to eval_runner's {total,passed,failed,failures}; per-claim violations flattened to f'{id}:{reasons}' strings in failures[].reasons"
  - "Fixture lives at crawler/eval/questions.jsonl — NEITHER git-ignored NOR a CORPORA_PREFIXES path, so it is safe to track; content is synthetic/public corpus-derived only, quotes copied VERBATIM from resolve()['text']"
  - "Grounded fixture lines use real relpath#ordinal ids: police-certificates/south-africa.md#005 and medical/who-must-submit-immigration-medical-examination.md#000; adversarial must_abstain lines are obviously fictional/out-of-corpus"
  - "REQUIREMENTS.md GND-02 left for the orchestrator's phase-close step (precedent: 25-01/25-02 left it Pending); this plan does NOT mark the overall phase complete"

patterns-established:
  - "Eval-harness loader stays generic so Phase 27 can later feed agent output through the same gate (each line is a COMPLETE stored answer object, not an agent-generated answer)"
  - "Real-corpus integration is @unittest.skipUnless(Path('corpus/index.db').is_file()) guarded; the tracked-fixture PII + structural tests are NOT skip-guarded (the fixture is always committed)"

requirements-completed: [GND-02]

# Metrics
duration: ~36min
completed: 2026-06-21
---

# Phase 25 Plan 03: Eval Harness (`--eval` + tracked PII-free questions.jsonl) Summary

**The grounding gate doubles as the regression eval harness: `grounding.run_eval` runs the SAME fail-closed `check_answer` per-claim gate over every stored answer line in a tracked, PII-free `crawler/eval/questions.jsonl` reference set and aggregates the locked `eval_runner` `{total, passed, failed, failures}` shape (exit 1 if any line is ungrounded); `corpus-crawler --json ground --db <db> --eval <file>` wires it in before any stdin read, an adversarial `must_abstain` line carrying claims is a `should_have_abstained` failure, and the fixture's 2 grounded lines resolve with verbatim quotes against the real 742-doc index while a non-skipped PII self-scan keeps the committed fixture share-safe (GND-02, SC4).**

## Performance

- **Duration:** ~36 min
- **Started:** 2026-06-21T08:22:00Z (approx)
- **Completed:** 2026-06-21T08:58:00Z (approx)
- **Tasks:** 2
- **Files modified:** 4 (1 created: `crawler/eval/questions.jsonl`; 3 modified: `grounding.py`, `cli.py`, `test_grounding.py`)

## Accomplishments

- `crawler/grounding.py::run_eval(db, questions_path) -> tuple[dict, int]` — the
  gate-over-fixtures aggregator (GND-02, SC4). Iterates non-blank JSONL lines in
  deterministic file order; a `must_abstain` line passes iff it carries NO claims
  (else `["should_have_abstained"]`), any other line is graded by the Wave-1
  `check_answer` gate (pass iff `verdict == "pass"`; per-claim violations flattened
  to `f"{v['id']}:{','.join(v['reasons'])}"`). Returns the LOCKED
  `{total, passed, failed, failures}` shape and `1 if failed else 0` (mirrors
  `eval_runner.main:135-150`). Pure check — NO render, NO write.
- `crawler/cli.py` — `--eval` flag on `p_ground`; an eval-mode branch in
  `_cmd_ground` placed AFTER `--db` validation but BEFORE any `sys.stdin.read()`
  (eval mode never blocks on stdin — Pitfall 7). Validates the questions path
  (non-file → `invalid_input`/exit 2), calls `grounding.run_eval`, emits
  `contract.envelope("ground", result=summary)` (`ok:true` — an ungrounded fixture
  line is a verdict, not an execution error), prints a human summary to stderr in
  non-json mode, and returns the eval exit code (1 if any line ungrounded, else 0).
- `crawler/eval/questions.jsonl` — NEW tracked, PII-free reference set (4 lines):
  - 2 GROUNDED lines whose `citations` + verbatim `quote` resolve against the real
    `corpus/index.db`: `police-certificates/south-africa.md#005`
    (`Certificates from Ideco Biometrics are **not** valid for immigration purposes.`
    — `**not**` markdown preserved verbatim) and
    `medical/who-must-submit-immigration-medical-examination.md#000`.
  - 2 adversarial `must_abstain` lines (fictional, obviously out-of-corpus: a
    "Lunar Gateway residency permit" fee and a "Kingdom of Eldoria diplomatic
    passport" renewal) each carrying an empty `claims[]`.
- `crawler/tests/test_grounding.py` — +11 tests over Wave-2's 21:
  - `TestRunEval` (5, synthetic index + inline tempdir JSONL): all-grounded → exit 0
    `{failed:0}`; one ungrounded line → exit 1 with its id in `failures`;
    `must_abstain` empty-claims → pass; `must_abstain` carrying claims →
    `should_have_abstained` fail; blank lines skipped.
  - `TestGroundCli` eval cases (3): `--eval` emits the summary envelope without
    reading garbage stdin (proves the branch precedes stdin), exit 1 on an
    ungrounded line, non-file `--eval` → `invalid_input`/exit 2.
  - `TestRealCorpusEval` (1, `@skipUnless(corpus/index.db)`): `run_eval` over the
    tracked fixture against the live 742-doc index → `failed == 0` / exit 0 / total ≥ 3.
  - `TestFixturePublishSafety` (1, NOT skip-guarded): `scan_text` + abs-path /
    `pr-ai-venv` raw-string self-scan over the committed fixture bytes (T-25-11). <!-- # publish-safe: allow -->
  - `TestFixtureStructure` (1, NOT skip-guarded): every line parses; non-abstain
    lines carry full claim keys; `must_abstain` lines carry empty `claims[]`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add `run_eval` to grounding.py and wire `--eval` into `_cmd_ground`** — `a57e703` (feat)
2. **Task 2: Author `crawler/eval/questions.jsonl` + real-corpus integration and PII self-scan tests** — `06d45f3` (test)

**Plan metadata:** see the final docs commit (this SUMMARY + STATE.md + ROADMAP.md).

## Files Created/Modified

- `crawler/grounding.py` (+~60 lines) — `run_eval` gate-over-fixtures aggregator;
  added `import json` at module top.
- `crawler/cli.py` (+~30 lines) — `--eval` argument on `p_ground` + the eval-mode
  branch in `_cmd_ground` (before stdin); `_cmd_ground` docstring updated.
- `crawler/eval/questions.jsonl` (4 lines, NEW) — tracked PII-free reference set
  (2 grounded + 2 adversarial must_abstain).
- `crawler/tests/test_grounding.py` (+~160 lines) — `TestRunEval`, 3 eval CLI cases,
  `TestRealCorpusEval`, `TestFixturePublishSafety`, `TestFixtureStructure`.

## Decisions Made

- **The eval IS the gate (gate-over-fixtures, not agent-over-questions).** No document
  agent exists until Phase 27, so each `questions.jsonl` line is a COMPLETE stored
  answer object (the gate's stdin schema) plus an `expect`/`must_abstain` marker;
  `run_eval` reuses `check_answer` per line and never generates answers. The loader
  stays generic so Phase 27 can later feed agent output through the same gate.
- **Result shape locked to `eval_runner`'s `{total,passed,failed,failures}`**; overall
  exit `1 if failed else 0` (mirror `eval_runner.main:135-150`). Per-claim violations
  are flattened into `failures[].reasons` as `f"{id}:{reasons}"` strings.
- **`must_abstain` correctness** is graded separately from grounding: a must-abstain
  line passes iff `claims == []`; a must-abstain line that smuggles any claim is a
  `should_have_abstained` FAILURE (eval exit 1). Non-abstain lines are graded by the
  normal gate.
- **Fixture tracked at `crawler/eval/questions.jsonl`** — this path is NEITHER
  git-ignored NOR a `CORPORA_PREFIXES` (`trial/`/`personal/`/`corpus_new/`) path, so
  it is safe to commit. All content is synthetic/public and corpus-derived; the
  grounded `quote`s were copied VERBATIM from `searchindex.resolve()['text']`
  (the `**not**` markdown preserved — `_norm` only collapses whitespace + lowercases).
- **Eval mode adds NO render/write** (it is a check); only single-answer mode (Plan 02)
  renders to `personal/output/`.
- **REQUIREMENTS.md GND-02 left to the orchestrator's phase-close step** — Plans 25-01
  and 25-02 both list GND-01/GND-02 as `requirements-completed` in their summaries yet
  left the REQUIREMENTS.md table `Pending`; this plan follows that precedent and does
  NOT mark the overall phase complete (the orchestrator owns that).

## Deviations from Plan

### Adjustments

**1. [Rule 3 - Blocking] Avoided the prohibited `/tmp` path in the Task 2 verify command.**
- **Found during:** Task 2 verification.
- **Issue:** The plan's `<automated>` verify writes the eval JSON to `/tmp/eval_out.json`;
  the executor environment forbids `/tmp`/temp-file output channels.
- **Fix:** Piped `corpus-crawler --json ground … --eval …` stdout DIRECTLY into the
  asserting Python one-liner (`json.load(sys.stdin)`), preserving the exact assertions
  (`ok is True`, `command == "ground"`, four-key shape present, `failed == 0`, exit 0)
  without any temp file. Behaviourally identical to the documented check.
- **Files modified:** none (verification-only change).
- **Verification:** `real-corpus eval OK: {'total': 4, 'passed': 4, 'failed': 0, 'failures': []}`, exit 0.

**2. [Rule 3 - Blocking] Renamed the PII test method to satisfy the plan's literal `-k` acceptance grep.**
- **Found during:** Task 2 (acceptance criteria).
- **Issue:** The plan asserts the PII self-scan is selectable via
  `pytest … -k "pii or self_scan or scan"`; a method named
  `test_fixture_has_no_abs_paths_or_secrets` matched none of those keywords (pytest
  would exit 5 "no tests ran", not green).
- **Fix:** Renamed it to `test_fixture_pii_self_scan_is_clean` so the literal command
  selects exactly it (1 passed). No behavioural change.
- **Files modified:** `crawler/tests/test_grounding.py`. **Commit:** `06d45f3`.

---

**Total deviations:** 2 (both Rule 3 — blocking, environment/acceptance alignment).
**Impact on plan:** No scope creep; both adjustments keep the documented verifications
runnable in this sandbox and faithful to the plan's intent.

## Authentication Gates

None — no external service, credential, or login was required.

## Known Stubs

None — `run_eval` is fully wired to the real `check_answer` compute; the tracked
fixture's grounded lines resolve verbatim against the real `corpus/index.db` (the
`TestRealCorpusEval` integration test RAN, not skipped).

## Issues Encountered

- **Slow real-corpus test (not a failure):** `crawler/tests/test_dupaudit.py::TestRealCorpus`
  is CPU-bound over the real 742-doc / 14 MB index and takes ~6m38s; it is unrelated to
  this plan and not run in the per-task loop (only in the final full-suite confirmation).
- **Pre-existing, out-of-scope failure (NOT caused by this plan):**
  `crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts`
  fails with `AssertionError: 0 not greater than or equal to 1` (`result.exact >= 1`)
  against the real git-ignored `corpus/`. Reproduced identically here; it was already
  failing on a clean tree before Wave 1 (logged in `deferred-items.md`). Per the SCOPE
  BOUNDARY it was NOT touched.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_grounding.py -q` → **32 passed**
  (21 Waves 1-2 + 11 new).
- `-k "eval or must_abstain"` → 8 passed; `-k "pii or self_scan or scan"` → 1 passed
  (the tracked-fixture PII self-scan); `-k "RealCorpusEval or Structure"` → 2 passed.
- Real-corpus eval RAN (not skipped):
  `.venv/bin/python -m crawler.cli --json ground --db corpus/index.db --eval crawler/eval/questions.jsonl`
  → `{"ok": true, "command": "ground", "result": {"total": 4, "passed": 4, "failed": 0, "failures": []}}`, exit 0.
- `grep -nE '/home/|/Users/|pr-ai-venv|BEGIN [A-Z ]*PRIVATE KEY' crawler/eval/questions.jsonl` <!-- # publish-safe: allow -->
  → no matches. `wc -l < crawler/eval/questions.jsonl` → 4. `git check-ignore` →
  fixture is NOT ignored (tracked).
- Full suite (run in segments to fit the tool window): **199 collected → 197 passed,
  1 skipped, 1 failed (the pre-existing `test_dupaudit::TestRealCorpus`), 59 subtests** —
  +11 grounding tests vs the 186-passed Wave-2 baseline, ZERO new regression.
- Acceptance greps: `grep -n 'def run_eval' grounding.py` (1), four-key shape present,
  `check_answer(` called inside `run_eval`, `args.eval`/`run_eval(` in cli.py (≥2),
  `--eval` registered on `p_ground`, `skipUnless` referencing `corpus/index.db` present.

## User Setup Required

None — zero new dependencies (stdlib + in-repo modules only). The eval harness runs
via `corpus-crawler --json ground --db corpus/index.db --eval crawler/eval/questions.jsonl`.

## Next Phase Readiness

- The grounding gate now doubles as a regression eval harness (GND-02, SC4): the bar
  and the test are identical machinery, and the tracked PII-free fixture is the seed
  reference set Phases 26 (checklist) and 27 (document agents) can grow as they emit
  cited answers through the same gate.
- Phase 25 is functionally complete pending the orchestrator's phase-close verification
  (all three plans executed & GREEN). No blockers introduced. The only outstanding
  suite failure is the pre-existing, unrelated `test_dupaudit::TestRealCorpus`.

---
*Phase: 25-grounding-gate-eval-harness*
*Completed: 2026-06-21*

## Self-Check: PASSED

- FOUND: `crawler/grounding.py` (`def run_eval`)
- FOUND: `crawler/cli.py` (`--eval` on `p_ground` + `args.eval` branch in `_cmd_ground`)
- FOUND: `crawler/eval/questions.jsonl` (tracked, 4 lines, PII-free)
- FOUND: `crawler/tests/test_grounding.py` (`TestRunEval` + `TestRealCorpusEval` + PII/structural)
- FOUND: `.planning/phases/25-grounding-gate-eval-harness/25-03-SUMMARY.md`
- FOUND commit: `a57e703` (Task 1 — feat: run_eval + --eval CLI mode)
- FOUND commit: `06d45f3` (Task 2 — test: tracked questions.jsonl + real-corpus/PII/structural tests)
