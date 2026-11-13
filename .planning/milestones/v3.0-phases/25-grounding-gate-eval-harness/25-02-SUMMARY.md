---
phase: 25-grounding-gate-eval-harness
plan: 02
subsystem: grounding
tags: [grounding, cli, contract, json-envelope, stdin, fail-closed, publish-safety, rpt-03, stdlib]

# Dependency graph
requires:
  - phase: 25-grounding-gate-eval-harness (Wave 1, 25-01)
    provides: "crawler/grounding.py — check_answer / render_answer / InvalidAnswer (the pure fail-closed compute this verb wraps)"
  - phase: 24-search-cli-citation-resolver
    provides: "the contract envelope + thin _cmd_* dispatcher house style (cli.py / contract.py) the ground verb mirrors"
  - phase: 15-publish-safe-hardening
    provides: "scripts/check_publish_safe.scan_text — the RPT-03 render-then-gate share-safety scan"
provides:
  - "crawler/cli.py::_cmd_ground — producer-facing `ground` CLI verb (stdin answer → one five-key envelope)"
  - "p_ground subparser (--db, --out-dir) + `ground` in the subparsers metavar"
  - "verdict-fail → ok:true/exit 1/render-nothing; pass → render→RPT-03 scan→write personal/output/ exit 0; publish-unsafe → ok:false/internal_error/exit 4; bad input → invalid_input/exit 2"
  - "additive `### ground` CONTRACT.md docs + `ground` in contract.py docstrings (schema_version 1.0, exit taxonomy UNCHANGED)"
  - "crawler/tests/test_grounding.py::TestGroundCli — 6 end-to-end CLI cases (stdin stubbing)"
affects: [25-03-eval-harness, 26-checklist-pii, 27-document-agents]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin stdin-reading CLI dispatcher: json.loads(sys.stdin.read()) → grounding.check_answer → contract envelope; all compute stays in grounding.py"
    - "RPT-03 render-then-scan-then-write: scan the EXACT rendered bytes with check_publish_safe.scan_text BEFORE any write; refuse on any hit"
    - "scripts/ sys.path shim (not a package) to import check_publish_safe — mirrors dupclean.py:478-482"
    - "Output confined to a git-ignored personal/ segment; --out-dir not under personal/ is refused as invalid_input"

key-files:
  created: []
  modified:
    - crawler/cli.py
    - crawler/contract.py
    - crawler/CONTRACT.md
    - crawler/tests/test_grounding.py

key-decisions:
  - "A grounding verdict:'fail' is an EXPECTED verdict (ok:true / exit 1 / render+write nothing), NOT an execution error — mirrors _cmd_report and dupclean 'return 1 if fail else 0'"
  - "A publish-safety hit REUSES the existing internal_error / EXIT_INTERNAL_ERROR=4 (NO new error type or exit code), distinguished by the grep-able message 'refusing to write answer: N publish-safety violation(s)'"
  - "Contract change is additive-only: SCHEMA_VERSION stays '1.0', five envelope keys + exit codes 0/1/2/3/4 unchanged; only the new `command` value `ground` + additive docs"
  - "Output is confined to a git-ignored personal/ segment (the structural PII control); the RPT-03 scan is the backstop, not the primary control"

patterns-established:
  - "stdin-driven verb: lazy-import json/sys/Path/grounding, validate --db, json.loads(stdin), map JSONDecodeError/UnicodeDecodeError + InvalidAnswer → invalid_input/exit 2"
  - "TestGroundCli._run mirrors TestSearchCli._run + a sys.stdin swap (restored in finally) — the one delta for a stdin-reading verb"

requirements-completed: [GND-01, GND-02]

# Metrics
duration: ~40min
completed: 2026-06-21
---

# Phase 25 Plan 02: Ground CLI Verb + Additive Contract Docs Summary

**The producer-facing `corpus-crawler --json ground` verb: a thin `_cmd_ground` dispatcher that reads one structured answer JSON from stdin, runs the Wave-1 `grounding.check_answer` compute, and maps the outcome to the frozen five-key contract — a grounding `verdict:"fail"` is an expected `ok:true`/exit-1 (render nothing), a fully-grounded answer is rendered → RPT-03 publish-safety-scanned → written ONLY to git-ignored `personal/output/` (exit 0), a scan hit refuses with `ok:false`/`internal_error`/exit 4, and bad input is `invalid_input`/exit 2 — documented additively in CONTRACT.md/contract.py without bumping `schema_version` or touching the exit-code taxonomy.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-06-21T07:57:00Z (approx)
- **Completed:** 2026-06-21T08:25:00Z (approx)
- **Tasks:** 2
- **Files modified:** 4 (cli.py, contract.py, CONTRACT.md, test_grounding.py)

## Accomplishments

- `crawler/cli.py::_cmd_ground` — a THIN dispatcher (mirrors `_cmd_search`/`_cmd_report`)
  that lazy-imports `grounding`, validates `--db`, reads ONE answer JSON from `sys.stdin`,
  dispatches to `grounding.check_answer`, and maps every outcome to exactly one
  `contract.envelope("ground", …)` (human text → stderr only):
  - `verdict:"fail"` → `ok:true` + `result.verdict:"fail"` + **exit 1**, render/write NOTHING
    (mirrors `_cmd_report`; a grounding fail is a verdict, never an `error`).
  - `verdict:"pass"` → `grounding.render_answer` → **RPT-03 render-then-gate**: scan the exact
    rendered bytes with `check_publish_safe.scan_text` BEFORE any write; a clean scan writes one
    deterministic `<question-slug>.md` under git-ignored `personal/output/` → `ok:true` + `result.out` + **exit 0**.
  - a publish-safety hit → `ok:false` / `error.type:"internal_error"` / **exit 4** (REUSED code,
    message `refusing to write answer: N publish-safety violation(s)`), writing NOTHING.
  - malformed stdin JSON / a missing-key answer (`InvalidAnswer`) / a non-file `--db` / an
    `--out-dir` not under a `personal/` segment → `invalid_input` / **exit 2**.
- `p_ground` subparser (`--db` default `corpus/index.db`, `--out-dir` default `personal/output`)
  registered + `ground` added to the `subparsers` metavar (additive — the Phase-24 `search` precedent).
- `crawler/CONTRACT.md` — additive `### ground` section (stdin answer shape, `result` field table,
  the verdict-fail rule, the exit-4 publish-unsafe refusal, and the verbatim honesty boundary) plus
  `ground` in the `command` enumeration. `crawler/contract.py` — `ground` added to both docstrings.
  **No new constants, no schema bump, no new exit-code row.**
- `crawler/tests/test_grounding.py::TestGroundCli` — 6 end-to-end cases driven through
  `cli.main(["--json","ground",…])` with `sys.stdin` stubbing: grounded→pass/exit-0/one-file,
  fail-closed→ok:true/verdict-fail/exit-1/no-write, malformed-stdin→invalid_input/exit-2,
  non-file-db→invalid_input/exit-2, publish-unsafe (stubbed render)→internal_error/exit-4/no-write,
  and stdout-purity (one JSON line, no `{` on stderr).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add `_cmd_ground` + `p_ground` to cli.py and `TestGroundCli` to the suite** — `83d4d03` (feat)
2. **Task 2: Document the `ground` command additively in CONTRACT.md and contract.py** — `acfe968` (docs)

**Plan metadata:** see the final docs commit (this SUMMARY + STATE.md + ROADMAP.md).

## Files Created/Modified

- `crawler/cli.py` (+~125 lines) — `_cmd_ground` thin dispatcher + `p_ground` subparser + `ground`
  in the subparsers metavar. Stdin → compute → contract; render-then-scan-then-write to `personal/output/`.
- `crawler/contract.py` (+2 docstring tokens) — `ground` added to the module docstring command
  enumeration (line 13) and the `envelope()` docstring (line 69). Zero new constants, schema_version unchanged.
- `crawler/CONTRACT.md` (+~65 lines) — additive `### ground` section + `ground` in the `command` list row.
- `crawler/tests/test_grounding.py` (+~135 lines) — `TestGroundCli` (6 cases) + the `_run` stdin-stubbing
  helper; docstring behaviour-map updated.

## Decisions Made

- **Verdict-fail is exit 1, not an error.** A grounding failure (any uncited / unresolvable /
  quote-mismatch claim) is an EXPECTED verdict: `ok:true`, `result.verdict:"fail"`, exit 1, render
  NOTHING — exactly mirroring `_cmd_report:223-240` and `dupclean.py:597` (`return 1 if verdict=="fail" else 0`).
  `error` is reserved for genuine execution failures.
- **Publish-unsafe reuses exit 4 (`internal_error`).** Per the plan's locked decision (RESOLVING the
  pattern-mapper's exit-code flag via shipped prior art), a publish-safety refusal reuses the existing
  `contract.INTERNAL_ERROR` / `contract.EXIT_INTERNAL_ERROR=4` — distinguished by the grep-able message
  `refusing to write answer: …`. No new error type or exit code was added (additive-only constraint held).
- **Output is structurally confined to `personal/`.** The default `--out-dir` is `personal/output`
  (git-ignored); an override whose resolved path is not under a `personal/` segment is refused as
  `invalid_input`. The RPT-03 `scan_text` is the abs-path/secret backstop, not the primary PII control.
- **`scripts/` is not a package** → imported `check_publish_safe` via the `sys.path.insert(0, <repo>/scripts)`
  shim (mirrors `dupclean.py:478-482`); `scripts/check_publish_safe.py` was NOT edited.

## Deviations from Plan

### Auto-fixed / adjustments

**1. CONTRACT.md `### ground` heading written without backticks (to satisfy the plan's documented verify).**
- **Found during:** Task 2.
- **Issue:** The plan's verify + acceptance commands check the heading with `grep -q '### ground'`
  (a literal substring). The established sibling sections use a backtick code-style heading
  (`### \`search\``), which does NOT contain the substring `### ground` — so a backtick form would fail
  the documented `grep`.
- **Fix:** Wrote the heading as plain `### ground` so the plan's literal `grep -q '### ground'` (and the
  acceptance `grep -n '### ground'`) pass. This is the plan's literal instruction; the only cost is a
  cosmetic divergence from sibling sections' backtick style. Not a behavioural change.
- **Files modified:** `crawler/CONTRACT.md`. **Commit:** `acfe968`.

No other deviations — both tasks executed as written.

## Authentication Gates

None — no external service, credential, or login was required.

## Known Stubs

None — `_cmd_ground` is fully wired to the real `grounding` compute and the real
`check_publish_safe.scan_text`; the smoke test below drove the real `corpus/index.db`.

## Issues Encountered

- **Pre-existing, out-of-scope failure (NOT caused by this plan):**
  `crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts`
  fails (`AssertionError: 0 not greater than or equal to 1` — an exact-dup signal against the real
  git-ignored `corpus/`). It was already failing on a clean tree before Wave 1 (logged in
  `deferred-items.md`); per the SCOPE BOUNDARY it was NOT touched.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_grounding.py -q` → **21 passed** (15 Wave-1 + 6 new
  `TestGroundCli`).
- `.venv/bin/python -m pytest "crawler/tests/test_grounding.py::TestGroundCli" -q` → **6 passed**.
- `.venv/bin/python -m pytest crawler/tests/ -q` → **186 passed / 1 failed (pre-existing
  `test_dupaudit::TestRealCorpus`) / 1 skipped / 59 subtests** — +6 vs the 180 baseline, ZERO new regression.
- Contract additive-only: `SCHEMA_VERSION == "1.0"`, no `EXIT_PUBLISH_UNSAFE`,
  `grep -nE 'EXIT_|_ERROR =|_INPUT =|UNSAFE' crawler/contract.py` shows ONLY the pre-existing constants.
- **Manual round-trip against the real `corpus/index.db`:**
  - grounded answer → `ok:true` / `verdict:"pass"` / exit 0, wrote `personal/output/smoke-test-grounded-question.md`.
  - ungrounded (uncited) answer → `ok:true` / `verdict:"fail"` / exit 1, NO file written.
  - malformed stdin → `ok:false` / `invalid_input` / exit 2.
  - non-file `--db` → `ok:false` / `invalid_input` / exit 2.
  - stdout was exactly one JSON object in every case; `personal/output/` is git-ignored (`git check-ignore` confirmed) — no PII leak into the tree.

## User Setup Required

None — zero new dependencies (stdlib + in-repo modules only). The verb defaults to `--db corpus/index.db`
and `--out-dir personal/output`.

## Next Phase Readiness

- The `ground` verb is the stable producer-facing CLI API (GND-02) that Plan 25-03 (the eval harness)
  and Phases 26/27 emit into. Plan 25-03 can add an `--eval`/`--questions` mode (a tracked PII-free
  `questions.jsonl`) running the SAME gate per stored answer and aggregating the `eval_runner`
  `{total,passed,failed,failures}` shape.
- No blockers introduced. The phase is NOT complete — 25-03 (eval harness) remains.

---
*Phase: 25-grounding-gate-eval-harness*
*Completed: 2026-06-21*

## Self-Check: PASSED

- FOUND: `crawler/cli.py` (`_cmd_ground` + `p_ground`)
- FOUND: `crawler/contract.py` (`ground` in both docstrings)
- FOUND: `crawler/CONTRACT.md` (`### ground` section)
- FOUND: `crawler/tests/test_grounding.py` (`TestGroundCli`)
- FOUND: `.planning/phases/25-grounding-gate-eval-harness/25-02-SUMMARY.md`
- FOUND commit: `83d4d03` (Task 1 — feat: ground CLI verb + TestGroundCli)
- FOUND commit: `acfe968` (Task 2 — docs: additive ground contract docs)

