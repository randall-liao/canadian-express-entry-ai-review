---
phase: 26-personalized-layer-1-checklist-pii-separation
reviewed: 2026-06-21T12:23:00Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - crawler/checklist.py
  - crawler/cli.py
  - crawler/contract.py
  - crawler/CONTRACT.md
  - personal.example/profile.yaml
  - crawler/tests/test_checklist.py
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: resolved
resolution:
  resolved_at: 2026-06-21T12:35:00Z
  fix_report: 26-REVIEW-FIX.md
  fixed: 5
  skipped: 0
  commits:
    CR-01: 0ce82c5
    WR-01: d764f1c
    WR-02: fee2bf6
    WR-03: c37f10f
    IN-01: 7de6203
---

# Phase 26: Code Review Report

**Reviewed:** 2026-06-21T12:23:00Z
**Depth:** deep (cross-file: checklist.py → cli.py → grounding.py → searchindex.py → scripts/check_publish_safe.py)
**Files Reviewed:** 6 (Phase-26 production changes only)
**Status:** resolved — all 5 findings fixed (see `26-REVIEW-FIX.md`); each fix is
covered by a unit/CLI test that fails on the old code and passes after the fix.

## Summary

Phase 26 adds a personalized, fully-cited Layer-1 document checklist with a hard
PII boundary. The core architecture is sound and well-defended in the **happy
path**:

- PII is genuinely confined to `basis[]` — `applicable_items` never interpolates a
  profile value into `text`/`query`/`doc_type` (verified by tracing every item;
  confirmed against the real corpus: the example profile grounds `pass` with six
  generic citations and zero `police-certificates/<country>` pages).
- The country-relpath backstop (`_is_country_specific`) correctly double-checks both
  the search-hit relpath and the *resolved* relpath, and abstains rather than cite a
  per-country page.
- `--out-dir` anchored containment is correct (resolved-path equality / `parents`
  check defeats `..`, symlinks, and `/tmp/personal/evil`-style prefix tricks).
- Render → scan → write ordering is correct: the publish-safe scan runs on the
  in-memory rendered bytes *before* any `mkdir`/`write`, so no temp/partial file
  leaks. The scan uses a neutral never-excluded label (WR-01 fix preserved).
- CONTRACT.md / contract.py are genuinely additive: `schema_version` stays `"1.0"`,
  five envelope keys, no new `EXIT_*`, only the `checklist` command value + a new doc
  section.
- `personal.example/profile.yaml` is genuinely synthetic (Wakanda/Latveria), and
  `git ls-files` confirms `personal/` has zero tracked files while
  `personal.example/profile.yaml` is tracked and `personal/output/*` stays ignored.

However, the adversarial probe found **one PII-boundary breach that is automatic and
unscanned** (CR-01), plus robustness/defense-in-depth gaps. The unifying theme: every
*designed* output channel (rendered markdown) is meticulously scanned and PII-free by
construction, but the **error path and the `--emit-answer` escape hatch route
profile-derived bytes to stdout/stderr with no scan and no containment**.

---

## Critical Issues

### CR-01: Malformed-profile YAML error echoes raw profile contents (PII) to stdout/stderr

> **RESOLVED** (commit `0ce82c5`): `load_profile` no longer interpolates
> `str(YAMLError)` (whose snippet echoes the offending source line). It raises a
> generic `ProfileError` carrying only PII-free line/column numbers; the sibling
> `OSError` branch is hardened the same way. Tests
> `test_invalid_yaml_error_message_carries_no_profile_pii` (loader) and
> `TestChecklistCli::test_malformed_profile_pii_never_reaches_{json_stdout,human_stderr}`
> assert a PII-bearing syntax error reaches NO stdout/stderr and exits invalid_input/2.

**File:** `crawler/checklist.py:80-81` → `crawler/cli.py:638-639` → `crawler/cli.py:618-623`

**Issue:** `load_profile` wraps a `yaml.YAMLError` by interpolating the exception into
the message: `raise ProfileError(f"Invalid YAML in profile {source}: {exc}")`. PyYAML's
`MarkedYAMLError.__str__` **includes the offending source line verbatim** (its
`get_snippet()` caret context). `_cmd_checklist` maps `ProfileError` to
`_fail(contract.INVALID_INPUT, str(exc), …)`, which in `--json` mode emits the message
inside the contract envelope **on stdout** (and to stderr in human mode). The personal
profile is exactly where real names / countries / dates live, so a single syntax error
in the user's real `personal/profile.yaml` ships those bytes out of the `personal/`
boundary — bypassing both the render-then-scan publish-safe gate and the
`personal/`-containment that the rest of the phase so carefully enforces.

This is the threat the design names ("an error message echoing profile contents"). The
loader copied this pattern verbatim from `crawler/profile.py:158-159`, which is safe
there (a non-PII crawl-*site* profile) but unsafe here (a PII personal profile).

**Reproduced** (PII on the offending line is echoed to stdout in `--json` mode, exit 2):
```
$ corpus-crawler --json checklist --profile personal/x --db corpus/index.db
{"schema_version":"1.0","ok":false,"command":"checklist","result":null,
 "error":{"type":"invalid_input",
  "message":"Invalid YAML in profile personal/x/profile.yaml: mapping values are not
   allowed here\n  in \"<unicode string>\", line 4, column 46:\n
   ... \"Maria Silva lived in Portugal\" : oops_unbalanced\n   ^"}}
```

**Fix:** Never interpolate the YAML exception body (or the parsed text) into a
user-facing message for the *personal* profile. Surface only a PII-free reason plus the
*path*; if a location is useful, expose `problem_mark.line/column` numbers, never the
snippet:
```python
except yaml.YAMLError as exc:
    mark = getattr(exc, "problem_mark", None)
    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
    # Do NOT include str(exc) / the source snippet — it echoes profile PII.
    raise ProfileError(f"Invalid YAML in personal profile{where}.") from exc
```
(The sibling `OSError` branch at `checklist.py:74-75` similarly interpolates `{exc}`/the
path; it leaks the path, not file contents, but the same PII-free-message hardening
should apply.)

---

## Warnings

### WR-01: Mis-typed profile sub-field crashes (AttributeError) → `internal_error`/exit 4 + raw traceback, instead of `invalid_input`/exit 2

> **RESOLVED** (commit `d764f1c`): `load_profile` now validates the known typed
> sub-sections (`program`/`education`/`applicant` must be mappings, `residence_since_18`
> a list) and raises `ProfileError` — which the CLI already routes to invalid_input/exit
> 2 — instead of letting `"FSW".get(...)` crash as an AttributeError into the catch-all.
> Messages name only the field + type name, never the offending value. Tests:
> `TestLoadProfile::test_mistyped_subsection_raises_profile_error_not_attributeerror`,
> `test_mistyped_residence_raises_profile_error`, and
> `TestChecklistCli::test_mistyped_subsection_is_invalid_input_exit_2_no_traceback`.

**File:** `crawler/checklist.py:110-112` (and the `.get()` calls at `:115-117`, `:119`)

**Issue:** The defensive idiom `profile.get("program") or {}` guards only *missing/falsy*
keys, not keys present with the **wrong type**. A structurally-valid YAML mapping such as
`program: FSW` (scalar instead of a sub-mapping) makes `program` the string `"FSW"`, and
`program.get("stream")` at `:115` raises `AttributeError: 'str' object has no attribute
'get'`. Same for `education` and `applicant`. `build_answer` calls `applicable_items`
with no guard (`checklist.py:361`), and `_cmd_checklist` calls `build_answer` with no
try/except (`cli.py:643`), so the exception escapes to `main()`'s catch-all
(`cli.py:855-861`).

This contradicts the module docstring's promise ("Sparse profiles are read defensively
… never KeyError", `checklist.py:26-27, 107-108`) and CONTRACT.md's stated mapping
("a missing / non-mapping `profile.yaml` … is `invalid_input` (exit `2`)"). User-supplied
malformed input is being treated as an internal crash.

**Reproduced:**
```
$ corpus-crawler --json checklist --profile personal/badshape ...
{... "error":{"type":"internal_error","message":"AttributeError: 'str' object ..."}}  # exit 4
$ corpus-crawler checklist --profile personal/badshape ...                            # human mode:
AttributeError: 'str' object has no attribute 'get'                                    # uncaught traceback, exit 1
```

**Fix:** Coerce each sub-section to a mapping defensively in `applicable_items`, or
validate types in `load_profile` and raise `ProfileError` (which the CLI already maps to
`invalid_input`/exit 2). Minimal defensive coercion:
```python
def _as_map(v): return v if isinstance(v, dict) else {}
program   = _as_map(profile.get("program"))
education = _as_map(profile.get("education"))
applicant = _as_map(profile.get("applicant"))
```
(`residence_since_18` and `family_members_18_plus` are already type-defended at
`:113`/`:118-121`, so only these three need it.)

### WR-02: `--emit-answer` writes `basis[]` PII to stdout — unscanned, uncontained, and not the contract envelope

> **RESOLVED** (commit `fee2bf6`): `--emit-answer` now redacts `basis[]` to an empty
> list before printing — only the PII-free `question`/`claims[]` (generic labels +
> verbatim corpus quotes) and `abstentions`/`prose` are emitted. The `ground` gate
> inspects `claims[]` only, so the redacted answer still gates identically. CONTRACT.md
> + the verb docstring now state that `--emit-answer` emits the raw answer (not the
> envelope) with `basis[]` redacted. Test
> `TestChecklistCli::test_emit_answer_stdout_carries_no_basis_pii_still_grounds` asserts
> no residence sentinel reaches stdout and the emitted answer still grounds `pass`.

**File:** `crawler/cli.py:647-649` (basis assembled at `checklist.py:339`; PII populated at
`applicable_items` `:201-213`)

**Issue:** `--emit-answer` prints the **whole** assembled answer —
`print(json.dumps(answer, ensure_ascii=False))` — and the answer's `basis[]` is exactly
the PII tier (e.g. *"…residence since age 18 in Wakanda, Latveria; 1 accompanying family
member(s)…"*). Two problems:
1. **PII to unscanned stdout.** Unlike the render path, this output never passes through
   `check_publish_safe` and is not confined to `personal/`. A user redirecting
   `checklist --emit-answer > somewhere` (the doc literally invites composability) moves
   real residence countries / counts wherever they point — potentially a tracked path.
2. **Contract deviation.** In `--json` mode every other command emits the five-key
   envelope; `--emit-answer` emits a *raw* answer object instead (keys
   `abstentions/basis/claims/prose/question`). An agent doing `json.loads(stdout)`
   expecting `schema_version/ok/command/error` gets a different shape.

**Reproduced:** `--json checklist --emit-answer` stdout top-level keys are
`['abstentions','basis','claims','prose','question']` and `basis[]` carries the sentinel
PII.

**Fix:** Either (a) document `--emit-answer` as a PII-bearing, *unsafe-to-persist* stream
and have it emit `claims`-only (drop `basis`/`abstentions`) since the downstream `ground`
gate ignores them anyway; or (b) run the same publish-safe `scan_text` over the serialized
answer before printing and refuse on a hit. At minimum, the CONTRACT.md `checklist`
section should state explicitly that `--emit-answer` output is the raw answer (not the
envelope) **and carries `basis[]` PII that must never be redirected outside
`personal/`**.

### WR-03: The `_is_country_specific` "hard guarantee" is case-/separator-literal, and the write-path scan is not PII-aware

> **RESOLVED** (commit `c37f10f`): `_is_country_specific` now normalizes the relpath
> (folds `\` → `/`, strips leading separators, case-folds) before the prefix test, so
> `Police-Certificates\<country>` is caught regardless of case/separator; it stays
> fail-closed. Tests `TestCountrySpecificBackstop::test_case_and_separator_variants_are_all_flagged`
> and `test_backstop_skips_uppercase_country_page_grounds_generic` cover the variants
> end-to-end. (Gap #2 — adding a name-aware PII assertion to the write-path scan — was
> out of scope for this fix pass; the by-construction PII split plus the now-robust
> relpath backstop remain the controls.)

**File:** `crawler/checklist.py:250-262`; cross-ref `scripts/check_publish_safe.py:54-90`
used at `crawler/cli.py:691`

**Issue (two related defense-in-depth gaps):**
1. The backstop matches `rp.startswith("police-certificates/")` **case-sensitively** with
   a hard-coded `/` separator (`checklist.py:261-262`). Its own docstring calls it "the
   hard guarantee" that "does not rest on the query strings alone" — yet a corpus built on
   a case-insensitive/case-preserving filesystem (macOS/Windows) or with a `Police-
   Certificates/` directory would slip past and could surface a per-country relpath
   (residence-history leak) into a citation/render. The live corpus is all-lowercase, so
   this is latent rather than active.
2. The only **runtime** guard on the rendered output before write is
   `cps.scan_text`, which matches **ABS_PATH / SECRET patterns only** — it does **not**
   detect PII (country/name/date). Verified:
   `scan_text("checklist.md", "...resided in France and Brazil; Maria Silva...")` returns
   `[]`. So if the by-construction guarantee ever regressed (e.g. via gap #1, or a future
   edit that rendered `basis[]`), nothing at write-time would catch a real-profile leak;
   the test that checks "no sentinel PII in rendered bytes" only looks for the fictional
   `Wakanda`/`Latveria` sentinels, which never appear in a real corpus or real profile.

**Fix:** Normalize before the prefix test, and fail safe across separators/case:
```python
rp = (relpath or "").lstrip("/").replace("\\", "/").lower()
return any(rp.startswith(p.lower()) for p in _COUNTRY_SPECIFIC_FAMILIES)
```
Separately, consider a lightweight PII assertion on the rendered bytes before write
(e.g. fail-closed if any `basis[]` substring appears in `rendered_md`) so the runtime
write-gate is a true PII backstop, not only an abs-path/secret scan.

---

## Info

### IN-01: `_verbatim_quote` can emit a degenerate single-punctuation quote that still "grounds"

> **RESOLVED** (commit `7de6203`): `_verbatim_quote` now requires a minimal word-character
> floor (`_QUOTE_MIN_WORD_CHARS = 3`) on the sliced span and returns `""` below it, so
> the caller abstains rather than emit a vacuous quote like `"."`. Tests:
> `TestVerbatimQuote` (degenerate / too-few-word-char / empty spans) and
> `TestGroundedClaim::test_degenerate_chunk_quote_grounds_to_none` (end-to-end abstention).

**File:** `crawler/checklist.py:265-279`

**Issue:** For a pathological chunk whose first non-empty content is a lone terminator
(e.g. text `"   .  x"`), `_verbatim_quote` returns `"."`. `quote_is_grounded` normalizes
to `"."` and `"." in _norm(chunk_text)` is True, so the gate accepts a meaningless quote
— a minor erosion of the grounding-by-construction guarantee. Not reachable on the
controlled IRCC corpus (chunks are substantial prose), hence informational.

**Fix:** Require a minimum signal in the sliced span, e.g. reject quotes whose normalized
form has fewer than N alphanumerics (`if len(re.findall(r"\w", span)) < 3: return ""`),
so the caller abstains rather than emit a vacuous quote.

---

_Reviewed: 2026-06-21T12:23:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
