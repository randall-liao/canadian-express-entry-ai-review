---
phase: 25-grounding-gate-eval-harness
fixed_at: 2026-06-21T10:10:50Z
review_path: .planning/phases/25-grounding-gate-eval-harness/25-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 25: Code Review Fix Report

**Fixed at:** 2026-06-21T10:10:50Z
**Source review:** `.planning/phases/25-grounding-gate-eval-harness/25-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (3 Critical + 3 Warning; 0 Info)
- Fixed: 6
- Skipped: 0

Every fix was applied to source AND paired with a regression test in
`crawler/tests/test_grounding.py` that was **verified to FAIL on the old buggy
code and PASS after the fix** (each was checked by temporarily reverting only the
relevant source hunk). All work was done in an isolated git worktree on a temp
branch, committed atomically per finding, then fast-forwarded onto `master`.

**Verification (CONTRACT preserved — `schema_version "1.0"`, five envelope keys,
exit taxonomy unchanged, no new `EXIT_*` constants):**
- Grounding suite: `46 passed` (`.venv/bin/python -m pytest crawler/tests/test_grounding.py -q`)
- Full suite: `211 passed, 1 skipped, 1 deselected, 59 subtests passed` — the only
  excluded test is the documented pre-existing `test_dupaudit::TestRealCorpus`.
- Real-corpus eval still green:
  `.venv/bin/python -m crawler.cli --json ground --db corpus/index.db --eval crawler/eval/questions.jsonl`
  → `{ok:true, result:{total:5, passed:5, failed:0, failures:[]}}`, exit 0.

## Fixed Issues

### CR-01: Whitespace-only quote is trivially "grounded" — fail-closed bypass

**Files modified:** `crawler/grounding.py`, `crawler/tests/test_grounding.py`
**Commit:** `22a9ee7`
**Applied fix:** `quote_is_grounded` now normalizes the quote FIRST and requires a
non-empty normalized form (`nq = _norm(quote); return bool(nq) and nq in _norm(chunk_text)`),
so `"   "` / `"\t\n"` (which collapse to `""`) can never substring-match. The old
`bool(quote)` guard let any non-empty whitespace string through because `"" in <anything>`
is always True.
**Tests (fail on old, pass on new):**
`TestCheckClaim.test_whitespace_only_quote_is_not_grounded`,
`TestCheckClaim.test_check_claim_whitespace_quote_is_quote_not_in_chunk`,
`TestCheckAnswer.test_whitespace_only_quote_makes_verdict_fail`.

### CR-02: Non-string quote is `str()`-coerced and can match incidental tokens — fail-closed bypass

**Files modified:** `crawler/grounding.py`, `crawler/tests/test_grounding.py`
**Commit:** `7e3cff0`
**Applied fix:** `_validate_shape` now raises `InvalidAnswer` (CLI → invalid_input /
exit 2) when a claim's `quote` value is not a string, and `check_claim` fails closed
with `quote_not_in_chunk` instead of `str()`-coercing a non-string. This closes the
`null → "none"` / `true → "true"` / `123 → "123"` incidental-match vector (proven with
the synthetic statute chunk containing `9.4`).
**Tests (fail on old, pass on new):**
`TestCheckClaim.test_non_string_quote_is_not_coerced`,
`TestCheckAnswer.test_non_string_quote_value_raises_invalid`,
`TestGroundCli.test_null_quote_is_invalid_input_exit_2_no_write`.

### CR-03: `--out-dir` containment does not pin to the repo's git-ignored `personal/` — PII boundary escape

**Files modified:** `crawler/cli.py`, `crawler/tests/test_grounding.py`
**Commit:** `74f9a92`
**Applied fix:** Added a module-level `_personal_root()` helper returning the resolved
`<repo-root>/personal`, and replaced the weak `"personal" in out_dir.resolve().parts`
check with anchored containment: the resolved `--out-dir` must EQUAL or be nested under
that boundary, else invalid_input / exit 2. This blocks `/tmp/personal/evil`,
`~/personal`, `/var/www/personal/pub`, and a foreign-CWD default. The helper is
module-level so tests pin it at a tempdir and never write under the real repo.
**Tests (fail on old, pass on new):**
`TestGroundCli.test_out_dir_with_personal_segment_outside_anchor_is_rejected`,
`TestGroundCli.test_out_dir_exactly_the_anchor_is_accepted`.

### WR-01: Publish-safety scan can be silently skipped via `scan_text`'s path exclusion

**Files modified:** `crawler/cli.py`, `crawler/tests/test_grounding.py`
**Commit:** `949c4ae`
**Applied fix:** The RPT-03 render-then-scan gate now scans under a fixed,
never-excluded label — `cps.scan_text("answer.md", rendered_md)` — instead of feeding
the destination path into `scan_text` (whose `is_excluded` short-circuits any path under
`scripts/tests/` or `.github/`). The scan now ALWAYS runs regardless of the write
destination; the real out-path is reported separately.
**Test (fail on old, pass on new):**
`TestGroundCli.test_publish_scan_runs_even_under_excluded_looking_out_dir`
(an unsafe rendered answer under an excluded-looking out-dir is still refused / exit 4,
nothing written).

### WR-02: `run_eval` does not catch `InvalidAnswer` — malformed fixture line mis-mapped, not `invalid_input`

**Files modified:** `crawler/grounding.py`, `crawler/tests/test_grounding.py`
**Commit:** `1224bee`
**Applied fix:** The per-line grade in `run_eval` is now wrapped in
`try/except InvalidAnswer`; a malformed non-abstain line is recorded as a counted
per-line `invalid_shape` failure (exit 1) instead of propagating out and surfacing as
internal_error/exit 4 (`--json`) or an uncaught traceback (human mode). Fail-closed: an
unparseable line is never a pass.
**Tests (fail on old, pass on new):**
`TestRunEval.test_malformed_line_is_counted_invalid_shape_failure`,
`TestGroundCli.test_eval_mode_malformed_line_is_counted_failure_not_internal_error`.

### WR-03: `expect` field is dead — eval harness cannot assert "ungrounded must be rejected"

**Files modified:** `crawler/grounding.py`, `crawler/tests/test_grounding.py`, `crawler/eval/questions.jsonl`
**Commit:** `01aa29b`
**Applied fix:** `run_eval` now reconciles each non-abstain line's verdict against its
`expect` marker — `grounded`/`pass` ⇒ ok iff `verdict == "pass"`; `ungrounded`/`fail` ⇒
ok iff `verdict == "fail"` (reason `expected_ungrounded_but_passed` otherwise); any other
value is a fail-closed `unknown_expect` failure (default `"grounded"`). Added one
SYNTHETIC, PII-free negative fixture line (`adversarial-fabricated-citation-01`,
`expect:"ungrounded"`, citing a fabricated unresolvable id) that the gate must reject —
which the real-corpus eval now counts as a PASS (failed==0/exit 0 preserved).
**Tests (fail on old, pass on new):**
`TestRunEval.test_expect_ungrounded_passes_when_gate_correctly_rejects`,
`TestRunEval.test_expect_ungrounded_fails_when_gate_wrongly_accepts`,
`TestRunEval.test_unknown_expect_value_is_fail_closed`,
plus the end-to-end `TestRealCorpusEval` (now also fails on the old expect-ignoring grading).

## Skipped Issues

None — all 6 in-scope findings were fixed.

---

_Fixed: 2026-06-21T10:10:50Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
