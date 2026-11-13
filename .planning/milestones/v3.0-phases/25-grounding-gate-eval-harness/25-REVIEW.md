---
phase: 25-grounding-gate-eval-harness
reviewed: 2026-06-21T05:32:05Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - crawler/grounding.py
  - crawler/cli.py
  - crawler/contract.py
  - crawler/CONTRACT.md
  - crawler/eval/questions.jsonl
  - crawler/tests/test_grounding.py
findings:
  critical: 3
  warning: 3
  info: 0
  total: 6
status: resolved
resolved: 2026-06-21T10:10:50Z
fix_report: .planning/phases/25-grounding-gate-eval-harness/25-REVIEW-FIX.md
findings_fixed: 6
findings_skipped: 0
fix_commits:
  CR-01: 22a9ee7
  CR-02: 7e3cff0
  CR-03: 74f9a92
  WR-01: 949c4ae
  WR-02: 1224bee
  WR-03: 01aa29b
---

> **RESOLUTION (2026-06-21T10:10:50Z):** All 6 findings (3 Critical + 3 Warning)
> were fixed, each in its own atomic commit with a regression test in
> `crawler/tests/test_grounding.py` that FAILS on the old buggy code and PASSES
> after the fix. The grounding suite (46 tests) and the full suite are green (only
> the pre-existing `test_dupaudit::TestRealCorpus` is excluded), and the
> real-corpus `--eval` still returns `ok:true`/`failed==0`/exit 0. See
> `25-REVIEW-FIX.md` for the per-finding report.

# Phase 25: Code Review Report

**Reviewed:** 2026-06-21T05:32:05Z
**Depth:** deep
**Files Reviewed:** 6
**Status:** resolved (all 6 findings fixed — see RESOLUTION above / `25-REVIEW-FIX.md`)

## Summary

Phase 25 adds the fail-closed grounding gate (`crawler/grounding.py`), the `ground`
CLI verb (`crawler/cli.py`), additive contract docs, a tracked reference set, and a
test suite. The contract changes are genuinely additive-only (no new `EXIT_*` /
error-type constants, `schema_version` still `"1.0"`, five keys, `ground` is the only
new `command` value — verified against the diff). The reference set
`crawler/eval/questions.jsonl` is PII-free (0 publish-safety violations, no
email/phone/SIN patterns) and the adversarial lines are synthetic. The 32-test suite
is green.

**However, the gate is NOT fail-closed in three provable ways**, all directly in the
project's core value (grounding-by-construction + PII containment). The verbatim-quote
check can be satisfied by a quote that is *not actually a quote*, letting an ungrounded
claim earn `verdict:"pass"`; and the `personal/` write-containment control does not pin
to the repo's git-ignored boundary, so rendered answers (which embed verbatim corpus
text) can be written outside it. Each Critical below was reproduced with the shipped
code, not inferred.

The unit tests pass precisely because none of them exercise the bypass inputs
(whitespace-only quote, JSON-`null` quote, out-of-repo `--out-dir`).

## Critical Issues

### CR-01: Whitespace-only quote is trivially "grounded" — fail-closed bypass

**✅ RESOLVED in `22a9ee7`** — `quote_is_grounded` now normalizes first and requires a
non-empty normalized quote. Regression tests: `TestCheckClaim.test_whitespace_only_quote_is_not_grounded`,
`test_check_claim_whitespace_quote_is_quote_not_in_chunk`, `TestCheckAnswer.test_whitespace_only_quote_makes_verdict_fail`.

**File:** `crawler/grounding.py:86` (`quote_is_grounded`), reached via `crawler/grounding.py:106-122` (`check_claim`)
**Issue:**
`quote_is_grounded` guards only against the *exact* empty string via `bool(quote)`,
then tests `_norm(quote) in _norm(chunk_text)`. A whitespace-only quote (`" "`,
`"\t\n"`) is a non-empty string, so `bool(quote)` is `True`, but `_norm(" ")` collapses
to `""`, and `"" in <anything>` is always `True`. So **any** claim that carries one
real, resolving citation plus a blank-but-non-empty `quote` passes the gate, even
though the quote grounds nothing. This is exactly the "empty quote trivially grounded"
failure the gate exists to prevent — the docstring even claims "An empty quote can
never be grounded (fail-closed)," but that is false for whitespace.

Reproduced end-to-end (real resolving citation mocked):
```
WHITESPACE-QUOTE  verdict: pass        # claim text: "a totally unsupported claim", quote: "   "
```
**Fix:** Normalize first and require a non-empty normalized quote, so blank/whitespace
quotes can never match:
```python
def quote_is_grounded(quote: str, chunk_text: str) -> bool:
    nq = _norm(quote)
    return bool(nq) and nq in _norm(chunk_text)
```

### CR-02: Non-string quote is `str()`-coerced and can match incidental tokens — fail-closed bypass

**✅ RESOLVED in `7e3cff0`** — `_validate_shape` now raises `InvalidAnswer` (CLI →
invalid_input/exit 2) for a non-string `quote`, and `check_claim` fails closed with
`quote_not_in_chunk` rather than `str()`-coercing. Regression tests:
`TestCheckClaim.test_non_string_quote_is_not_coerced`, `TestCheckAnswer.test_non_string_quote_value_raises_invalid`,
`TestGroundCli.test_null_quote_is_invalid_input_exit_2_no_write`.

**File:** `crawler/grounding.py:106` (`quote = str(claim.get("quote", ""))`), with the match at `crawler/grounding.py:86`
**Issue:**
`_validate_shape` requires the `quote` *key* to be present but never checks its *value*
type. `check_claim` then coerces it with `str(...)`. A JSON `null` quote becomes the
literal string `"None"` → `_norm` → `"none"`; a boolean `true` → `"true"`; a number
`123` → `"123"`. Because `"none"` / `"true"` are extremely common words in real chunk
text, a claim with `"quote": null` plus a citation to any chunk containing the word
"none" passes the gate with no genuine quoted span.

Reproduced end-to-end (chunk text contains the word "none"):
```
NULL-QUOTE        verdict: pass        # quote: null  ->  "none"  matched in chunk
```
**Fix:** Treat a non-string (or absent-value) quote as ungrounded rather than coercing
it. Either validate in `_validate_shape` (require `isinstance(claim["quote"], str)`) or
guard in `check_claim`:
```python
raw = claim.get("quote", "")
if not isinstance(raw, str):
    return ["quote_not_in_chunk"]   # fail-closed; do NOT str()-coerce
quote = raw
```
(Combined with CR-01's `nq = _norm(quote)` check this closes both quote vectors.)

### CR-03: `--out-dir` containment does not pin to the repo's git-ignored `personal/` — PII boundary escape

**✅ RESOLVED in `74f9a92`** — anchored containment via a new `_personal_root()` helper:
the resolved `--out-dir` must equal or be nested under `<repo-root>/personal`, else
invalid_input/exit 2. Regression tests: `TestGroundCli.test_out_dir_with_personal_segment_outside_anchor_is_rejected`,
`test_out_dir_exactly_the_anchor_is_accepted`.

**File:** `crawler/cli.py:511-516` (`if "personal" not in out_dir.resolve().parts`)
**Issue:**
The documented control (CONTRACT.md "ground" section, and `cli.py:509-510`) is that a
passing answer is written "to the git-ignored `personal/output/` boundary ONLY." The
implemented check only asserts that *some* resolved path component is literally named
`personal`. It does **not** verify the path is under `<repo-root>/personal/`. Confirmed:
```
/tmp/personal/evil      -> containment OK? True
~/personal  -> containment OK? True
/var/www/personal/pub   -> containment OK? True
```
Rendered answers embed verbatim corpus chunk text (and, for a personal/trial corpus,
potentially sensitive content). This control therefore permits writing that content
*outside* any `.gitignore` protection — to `/tmp`, a home dir, a web root, etc. The
default `--out-dir personal/output` is also CWD-relative and resolved without anchoring
to the repo, so invoking the CLI from a foreign CWD (e.g. `/tmp`) writes to
`/tmp/personal/output/...` while still passing the check. This is a real weakening of
the project's PII-containment guarantee, not a style nit.
**Fix:** Anchor to the repository root and require true containment:
```python
repo_personal = (Path(__file__).resolve().parents[1] / "personal").resolve()
resolved = out_dir.resolve()
if repo_personal != resolved and repo_personal not in resolved.parents:
    return _fail(contract.INVALID_INPUT,
                 f"--out-dir must resolve under {repo_personal}: {out_dir}",
                 contract.EXIT_INVALID_INPUT)
```

## Warnings

### WR-01: Publish-safety scan can be silently skipped via `scan_text`'s path exclusion

**✅ RESOLVED in `949c4ae`** — the render-then-scan gate now scans under a fixed,
never-excluded label (`scan_text("answer.md", rendered_md)`) so the scan ALWAYS runs
regardless of the write destination. Regression test:
`TestGroundCli.test_publish_scan_runs_even_under_excluded_looking_out_dir`.

**File:** `crawler/cli.py:530` (`violations = cps.scan_text(str(out_path), rendered_md)`)
**Issue:**
`scan_text(path, text)` first calls `is_excluded(path)` and returns `[]` (no
violations) for any path under `scripts/tests/` or `.github/`, or for the checker's own
file. That exclusion logic is designed for the *repo-tree* publish scan, but here the
destination path is fed straight into it. Combined with the weak CR-03 containment
(only a literal `personal` segment is required), an `--out-dir` such as
`scripts/tests/personal` resolves with a `personal` part (passes containment) **and**
starts with `scripts/tests/` (triggers `is_excluded` → scan returns `[]`), so the
RPT-03 render-then-scan gate is bypassed and unscanned content is written. Confirmed:
```
scripts/tests/personal/answer.md -> violations: 0   (abs-path line present but skipped)
.github/personal/answer.md       -> violations: 0
personal/output/answer.md        -> violations: 1   (default path scans correctly)
```
The default path scans correctly, but the write-gate should never be subject to the
repo-scan exclusion list.
**Fix:** Don't route the destination path through the exclusion logic. Either scan with
a neutral, never-excluded label (e.g. `cps.scan_text("answer.md", rendered_md)`) or call
the line-level matcher directly so a clean scan is always required regardless of the
write destination. (Fixing CR-03 first also removes the `scripts/tests` reachability.)

### WR-02: `run_eval` does not catch `InvalidAnswer` — malformed fixture line mis-mapped, not `invalid_input`

**✅ RESOLVED in `1224bee`** — `run_eval` now wraps the per-line grade in
`try/except InvalidAnswer` and records a malformed line as a counted per-line
`invalid_shape` failure (exit 1) instead of letting it collapse the run into
internal_error/exit 4. Regression tests: `TestRunEval.test_malformed_line_is_counted_invalid_shape_failure`,
`TestGroundCli.test_eval_mode_malformed_line_is_counted_failure_not_internal_error`.

**File:** `crawler/grounding.py:223` (`summary = check_answer(rec, db)`), dispatched at `crawler/cli.py:471`
**Issue:**
For a non-`must_abstain` reference line, `run_eval` calls `check_answer`, which raises
`InvalidAnswer` on a malformed line (e.g. a claim missing `quote`). Neither `run_eval`
nor the `--eval` CLI branch catches it. Confirmed:
```
run_eval raised: InvalidAnswer -> claim #0 (id='c1') is missing keys: ['quote']
```
In `--json` mode this surfaces through the `cli.main` catch-all as
`internal_error`/exit `4`; in human mode it escapes as an uncaught traceback (exit `1`).
The contract says a malformed answer is `invalid_input`/exit `2`. Risk is low because
the reference set is tracked, but the eval path mishandles a bad line instead of failing
as documented `invalid_input`.
**Fix:** Wrap the per-line grade in `try/except grounding.InvalidAnswer` and surface it
as a per-line failure (e.g. reason `["invalid_shape"]`) so one bad fixture line fails
that line loudly without collapsing the whole run into `internal_error`.

### WR-03: `expect` field is dead — eval harness cannot assert "ungrounded must be rejected" and silently mis-grades it

**✅ RESOLVED in `01aa29b`** — `run_eval` now reconciles the verdict against the line's
`expect` marker (grounded/pass ⇒ ok iff pass; ungrounded/fail ⇒ ok iff fail; any other
value ⇒ fail-closed `unknown_expect`). Added a SYNTHETIC, PII-free negative fixture
line (`adversarial-fabricated-citation-01`, `expect:"ungrounded"`) the gate must reject;
real-corpus `--eval` still returns `failed==0`/exit 0. Regression tests:
`TestRunEval.test_expect_ungrounded_passes_when_gate_correctly_rejects`,
`test_expect_ungrounded_fails_when_gate_wrongly_accepts`, `test_unknown_expect_value_is_fail_closed`,
plus the end-to-end `TestRealCorpusEval`.

**File:** `crawler/grounding.py:210-229` (`run_eval` loop; `rec["expect"]` is never read)
**Issue:**
Every non-abstain line in `questions.jsonl` carries `"expect":"grounded"`, but
`run_eval` never reads `expect`. Non-abstain lines are graded purely as "PASS iff
`verdict == "pass"`." Consequently the harness can only express "expect grounded" or
"expect abstain"; a fixture author who wrote `"expect":"ungrounded"` (to assert the gate
*correctly rejects* an ungrounded answer) would have that line silently graded as a
FAILURE. As a regression harness for a fail-closed gate, the tracked set therefore has
no positive test that an ungrounded answer is *rejected* (only the unit tests cover
that), and the unused `expect` key implies a capability that does not exist.
**Fix:** Either honor `expect` (grade `ok = (verdict == "pass") == (expect == "grounded")`)
so negative grounding fixtures are possible, or drop the `expect` field from the schema
and docs so it cannot mislead fixture authors.

---

_Reviewed: 2026-06-21T05:32:05Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
