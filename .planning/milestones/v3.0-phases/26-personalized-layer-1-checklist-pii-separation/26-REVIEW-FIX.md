---
phase: 26-personalized-layer-1-checklist-pii-separation
fixed_at: 2026-06-21T12:35:00Z
review_path: .planning/phases/26-personalized-layer-1-checklist-pii-separation/26-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 26: Code Review Fix Report

**Fixed at:** 2026-06-21T12:35:00Z
**Source review:** `.planning/phases/26-personalized-layer-1-checklist-pii-separation/26-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (1 critical, 3 warning, 1 info — `fix_scope = all`)
- Fixed: 5
- Skipped: 0

Overriding principle honored throughout: the **HARD PII BOUNDARY** — no
profile-derived bytes (countries, dates, names, raw profile source lines) may reach
stdout/stderr, a tracked file, the corpus DB, or any un-git-ignored location. Every
fix fails **closed** with a GENERIC, PII-free message when in doubt.

Each fix adds/strengthens a unit/CLI test in `crawler/tests/test_checklist.py` that
**fails on the old code and passes after the fix** (verified by `git stash`-ing the
production change and re-running the new test) — closing the "only happy-path inputs
were tested" gap that let these leaks through.

**Contract preserved:** `schema_version` stays `"1.0"`, five envelope keys, no new
`EXIT_*` constants, exit-code taxonomy unchanged. `grounding` / `searchindex` /
`scripts/check_publish_safe` are UNMODIFIED; `crawler/contract.py` is untouched (no
new constants were needed). Only `crawler/checklist.py`, `crawler/cli.py`,
`crawler/CONTRACT.md`, and `crawler/tests/test_checklist.py` were changed.

## Verification

- **Checklist suite:** `.venv/bin/python -m pytest crawler/tests/test_checklist.py -q`
  → **72 passed** (was 55 before; +17 new test methods).
- **Full suite:** `.venv/bin/python -m pytest crawler/tests -q`
  → **283 passed, 1 skipped, 59 subtests passed, 1 failed**. The single failure is
  the documented acceptable pre-existing one:
  `test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts`
  (`result.exact == 0`, an unrelated real-corpus de-dup assertion). No new failures
  were introduced.
- **Real-corpus checklist smoke (constraint):**
  `PR_PERSONAL_DIR=personal.example .venv/bin/python -m crawler.cli --json checklist
  --db corpus/index.db --out-dir personal/output`
  → `ok:true`, `verdict:"pass"`, `6/6` grounded, exit 0. The rendered
  `personal/output/checklist.md` contains NO profile-derived PII (no
  `Wakanda`/`Latveria`/residence-count/basis strings) and `check_publish_safe.scan_text`
  over the rendered bytes returns `[]`. (`personal/` stays git-ignored;
  `personal.example/profile.yaml` stays tracked + synthetic.)

## Fixed Issues

### CR-01: Malformed-profile YAML error echoes raw profile contents (PII) to stdout/stderr

**Files modified:** `crawler/checklist.py`, `crawler/tests/test_checklist.py`
**Commit:** `0ce82c5`
**Applied fix:** `load_profile` previously raised
`ProfileError(f"Invalid YAML in profile {source}: {exc}")`. PyYAML's
`MarkedYAMLError.__str__` embeds the offending **source line verbatim** (its
`get_snippet` caret context), so a single syntax error in the user's real
`personal/profile.yaml` shipped real names/countries/dates into the `--json` envelope
on stdout (and human stderr), bypassing the render-then-scan publish-safe gate and the
`personal/` boundary. The `except yaml.YAMLError` branch now derives a PII-free message
from `problem_mark` line/column numbers ONLY — never `str(exc)`/the snippet:
`raise ProfileError(f"Invalid YAML in personal profile{where}.")`. The sibling
`OSError` branch was hardened the same way (path only, no raw `{exc}` body).
**Tests:** `TestLoadProfile::test_invalid_yaml_error_message_carries_no_profile_pii`,
`test_unreadable_profile_error_message_carries_no_exc_body`, and
`TestChecklistCli::test_malformed_profile_pii_never_reaches_json_stdout` /
`...never_reaches_human_stderr` — a syntax error whose offending line carries the PII
sentinel `Maria Silva lived in Portugal: 1990-05-03` must leave NO sentinel token in
captured stdout OR stderr, and exit `invalid_input`/2. (Reproduced the original leak on
the pre-fix code: stderr contained `... Maria Silva lived in Portugal ...`.)

### WR-01: Mis-typed profile sub-field crashes (AttributeError) → internal_error/exit 4

**Files modified:** `crawler/checklist.py`, `crawler/tests/test_checklist.py`
**Commit:** `d764f1c`
**Applied fix:** A structurally-valid mapping whose sub-section had the wrong type
(e.g. `program: FSW`, a scalar) made `applicable_items` execute `"FSW".get("stream")`
→ `AttributeError`, which escaped to `main()`'s catch-all as `internal_error`/exit 4
(contract says `invalid_input`/exit 2) plus a raw traceback that can echo profile
bytes. Rather than coerce-and-ignore (which would silently drop malformed input), the
fix validates the known typed sub-sections in `load_profile` — `program`/`education`/
`applicant` must be mappings and `residence_since_18` a list — and raises `ProfileError`
(the CLI already maps it to `invalid_input`/exit 2). This is the correct place because
the CLI only wraps `load_profile` in the `ProfileError → exit 2` mapping; raising inside
`applicable_items` would instead hit the catch-all (exit 4). Error messages name only
the field name + type name (e.g. `'str'`), never the offending value.
**Tests:** `TestLoadProfile::test_mistyped_subsection_raises_profile_error_not_attributeerror`
(loops program/education/applicant, asserts no `Maria`/`Silva` leak into the message),
`test_mistyped_residence_raises_profile_error`, and
`TestChecklistCli::test_mistyped_subsection_is_invalid_input_exit_2_no_traceback`
(asserts exit 2, no `AttributeError`/`Traceback`, no PII in stdout/stderr).

### WR-02: `--emit-answer` writes basis[] PII to stdout — unscanned, uncontained

**Files modified:** `crawler/cli.py`, `crawler/CONTRACT.md`, `crawler/tests/test_checklist.py`
**Commit:** `fee2bf6`
**Applied fix:** `--emit-answer` printed the WHOLE assembled answer to UNSCANNED,
UNCONTAINED stdout, and `basis[]` is the PII tier (residence countries/counts). Because
the downstream `ground` gate inspects `claims[]` ONLY (`basis`/`abstentions`/`prose` are
free-form and never citation-checked — confirmed in `grounding._validate_shape`), the
fix emits a PII-FREE answer: it keeps `question` + `claims[]` (generic labels + verbatim
corpus quotes) and the PII-free `abstentions`/`prose`, but REDACTS `basis[]` to an empty
list before `json.dumps`. The redacted answer still validates against grounding's shape
and pipes straight into `ground`. CONTRACT.md and the verb docstring now document that
`--emit-answer` emits the raw answer (not the five-key envelope) with `basis[]` redacted.
**Test:** `TestChecklistCli::test_emit_answer_stdout_carries_no_basis_pii_still_grounds`
— asserts `basis == []`, no `Wakanda`/`Latveria` token anywhere on stdout, and that
`grounding.check_answer(parsed, db)` still returns `verdict:"pass"` (composability
preserved).

### WR-03: `_is_country_specific` backstop is case-/separator-literal

**Files modified:** `crawler/checklist.py`, `crawler/tests/test_checklist.py`
**Commit:** `c37f10f`
**Applied fix:** The country-relpath backstop matched `"police-certificates/"`
case-sensitively with a hard-coded `/` separator, so a `Police-Certificates/` directory
or a backslash path on a case-insensitive/Windows corpus could slip past and surface a
per-country (residence-leaking) relpath into a citation. The relpath is now normalized
before the prefix test — `rp = (relpath or "").replace("\\", "/").lstrip("/").lower()` —
with separators folded **before** stripping leading slashes (so a leading backslash is
handled too), and the prefix is matched case-folded. It stays fail-closed.
**Tests:** `TestCountrySpecificBackstop::test_case_and_separator_variants_are_all_flagged`
(capitalized/upper-case dirs, backslash separators, leading separators — six variants)
and `test_backstop_skips_uppercase_country_page_grounds_generic` (an UPPER-CASE-only
per-country corpus must still abstain end-to-end).

> Note: the review's secondary "consider" item under WR-03 — adding a name-aware PII
> assertion to the write-path scan — was deliberately left out of scope for this fix
> pass (the task asked specifically for the normalization). The by-construction PII split
> plus the now case/separator-robust relpath backstop remain the controls.

### IN-01: `_verbatim_quote` can emit a degenerate single-punctuation quote that still grounds

**Files modified:** `crawler/checklist.py`, `crawler/tests/test_checklist.py`
**Commit:** `7de6203`
**Applied fix:** For a pathological chunk whose first span is a lone terminator,
`_verbatim_quote` returned `"."`, which `quote_is_grounded` normalize-accepts — grounding
a vacuous claim. The fix adds a `_QUOTE_MIN_WORD_CHARS = 3` floor: after slicing the
span, if it carries fewer than three word characters the function returns `""`, so the
caller (`grounded_claim`) fails closed and abstains rather than emit a trivial quote.
**Tests:** `TestVerbatimQuote` (degenerate `"   .  x"` → `""`, too-few-word-char `"a. bcd
efgh"` → `""`, empty/whitespace → `""`, and a substantial-prose case still returning a
verbatim substring) and `TestGroundedClaim::test_degenerate_chunk_quote_grounds_to_none`
(end-to-end: a resolved chunk with a degenerate span → `grounded_claim` returns `None`).

> This is a small behavioral/defensive change to the quote-slicing logic. It is fully
> exercised by the tests above and does not affect the real corpus (substantial prose
> chunks comfortably clear the floor; the real-corpus smoke still grounds `6/6`), but a
> human may wish to confirm the chosen floor (`>= 3` word chars) matches intent.

## Skipped Issues

None — all 5 in-scope findings were fixed.

---

_Fixed: 2026-06-21T12:35:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
