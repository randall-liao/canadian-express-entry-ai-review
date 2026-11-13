# Phase 26 — Personalized Layer-1 Checklist + PII Separation · Validation Strategy (Nyquist)

**Requirements:** CHK-01 (personalized cited Layer-1 checklist from a local profile), CHK-02 (PII strictly out of repo + corpus DB)
**Goal under test:** Generate a personalized, fully-cited Layer-1 "which documents you need" checklist for a
post-ITA Express Entry applicant from a LOCAL profile, with all PII kept strictly out of the repo and the
corpus DB — every requirement line is a gated, cited `claims[]` entry that passes the Phase-25 gate, and the
PII tier split (`basis[]` = applicability, `claims[]` = generic gated text) keeps rendered output PII-free.

This file is the **sampling plan**: for each ROADMAP success criterion it names the smallest set of automated
checks that would catch a regression. Every check is an `automated` command runnable today; only the
real-corpus integration check requires `corpus/index.db` (`@skipUnless`-guarded). **Bare `python` is broken
(Windows pyenv-win CRLF / `/bin/sh^M`); every command runs through `.venv/bin/python -m …`.** Tests are
stdlib `unittest` driven by pytest — synthetic tiny index + synthetic `personal.example/profile.yaml`, no
real PII, tempdir-only writes.

---

## Success-criterion → validation map

| SC (CHK) | What must be TRUE | Validating test(s) | Plan |
|----------|-------------------|--------------------|------|
| **SC1** Generator produces a Layer-1 checklist where every requirement line is a gated, cited `claims[]` entry that passes the Phase-25 gate | profile → applicable items → short corpus queries → `resolve()` verbatim quote → `claims[]` → `grounding.check_answer` returns `verdict:"pass"` | `-k "profile or personal_dir"`, `-k applicability`, `-k "grounds or assemble or abstain"`, CLI `-k cli` end-to-end pass | 01, 02, 03 |
| **SC2** Separation of concerns: applicability in `basis[]` (never gated), requirement text+citation from corpus (gated) | profile-derived countries/dates/names go to `basis[]`; `claims[].text` carries only generic requirement text + a corpus citation; no claim cites a country-specific `police-certificates/<country>` relpath | `-k applicability` (basis vs claims), `-k pii` (sentinel PII tokens present in basis, ABSENT from claims), `-k "generic"` (no country-specific citation) | 01, 02 |
| **SC3** Rendered checklist written only under git-ignored `personal/output/`; `CORPORA_PREFIXES` fails closed on any `git add` of profile/output; `personal.example/` stays tracked | `_personal_root()` anchored containment refuses out-of-`personal/` dirs; rendered file lands under `personal/output/`; `personal.example/profile.yaml` is tracked, `personal/` ignored | `-k "cli or containment"`, `-k tracked` (personal.example tracked + personal/ ignored) | 03 |
| **SC4** No PII (countries, dates, names) in `claims[].text`, the corpus DB, or any tracked file — confirmed by the RPT-03 scan over the rendered checklist bytes | `check_publish_safe.scan_text(rendered_bytes) == []`; sentinel PII tokens never appear in rendered output; rendered bytes carry only `claims[]`+quote+citation (never `basis[]`) | `-k pii`, `-k "real_corpus or publish_safe or pii or tracked"` (scan over rendered bytes == clean) | 02, 03 |

---

## The validation strands (and how each is sampled)

### 1. PII-free-by-construction — the headline (SC2/SC4, CHK-02)
- **Sentinel test (default suite):** the synthetic `personal.example/profile.yaml` carries recognizable
  sentinel PII tokens (a country, a date, a name). `-k pii` asserts those tokens DO appear in `basis[]`
  but NEVER in any `claims[].text` or `quote`, and that `check_publish_safe.scan_text` over the rendered
  checklist bytes returns `[]` (no violation). This is the fail-closed secondary guard on top of the
  by-construction guarantee that `render_answer` renders only `claims[]`.
- **Generic-citation test (default suite):** `-k "generic"` asserts no claim cites a
  `police-certificates/<country>` (or other country-specific) relpath — the relpath itself would leak
  residence history even though the text is generic.

### 2. Grounding-by-construction of every requirement line (SC1, CHK-01)
- `-k "grounds or assemble or abstain"` drives `grounded_claim` (retrieve → `resolve()` → verbatim quote)
  and `build_answer` (assemble the Phase-25 answer object) through `grounding.check_answer`, asserting
  `verdict:"pass"` for a populated profile and an explicit `abstention` (never an empty/ungrounded
  checklist) when an item has no applicable corpus hit.

### 3. Personalized applicability = selection, not mutation (SC1/SC2, CHK-01)
- `-k applicability` asserts the applicable-item set changes with the profile (CEC stream omits
  proof-of-funds; foreign education includes ECA) while the gated requirement TEXT is never mutated —
  personalization lives in WHICH claims are selected, sourced from `basis[]`.

### 4. PII boundary + containment (SC3, CHK-02)
- `-k "cli or containment"` asserts the `checklist` verb renders only under `personal/output/` via the
  `_personal_root()` anchored-containment guard (reused from the Phase-25 CR-03 fix) and refuses an
  out-of-`personal/` `--out-dir` with `invalid_input`/exit 2.
- `-k tracked` asserts `personal.example/profile.yaml` is git-tracked while `personal/` is git-ignored
  (the synthetic schema ships; real profiles never do).

### 5. Contract stability (SC1, CHK-01)
- Import gate: `.venv/bin/python -c "from crawler import contract; e=contract.envelope('checklist', result={'verdict':'pass'}); assert e['command']=='checklist' and e['schema_version']=='1.0' and set(e)=={'schema_version','ok','command','result','error'}"` — proves the new `checklist` command is additive, the five envelope keys + schema version unchanged, no new exit/error constant.

### 6. Real-corpus integration (SC1/SC4, guarded)
- `-k "real_corpus or publish_safe or pii or tracked"` runs the `checklist` verb against the real
  `corpus/index.db` (skips cleanly when absent), asserting a passing gated checklist renders under
  `personal/output/` and its bytes scan clean.

---

## Nyquist rate justification

- **Continuous sampling, 2–3 automated probes per plan** (a fast `-k` slice + the full-file run), so no
  failure mode hides between probes: the PII boundary (strand 1) is sampled at the sentinel-token, generic-
  citation, and rendered-bytes-scan levels; grounding (strand 2) at the claim and answer levels;
  containment (strand 4) at the CLI boundary.
- **No watch-mode, no browser/E2E, no network** — every check is a deterministic `unittest`/CLI invocation
  in seconds; the only environment-gated probe is the real-corpus integration, `@skipUnless`-guarded.
- **Regression floor:** every plan re-asserts `.venv/bin/python -m pytest crawler/tests -q` stays green
  (only the documented pre-existing `test_dupaudit::TestRealCorpus` may fail), so the producer cannot
  regress the Phase-24/25 search/resolve/gate primitives it consumes.

## Scope note (do NOT over-gate)

A whole-tree `check_publish_safe` run currently reports ~22 pre-existing `ABS_PATH` hits OUTSIDE this phase
(Phase-25 planning docs + `crawler/tests/test_grounding.py` marker strings; the scanner does not exclude
`crawler/tests/`). Phase-26's PII gate is therefore scoped to the **rendered checklist bytes** (SC4's exact
wording), NOT a whole-tree exit-0 gate. The pre-existing tree debt is logged for the milestone audit.

## Honesty boundary (inherited)

The checklist reuses the Phase-25 gate unchanged: it guarantees resolvability + verbatim-quote of every
requirement line, NOT semantic entailment (VAL-01/02 deferred). Layer-2 per-document rule matching
(recency/amounts/format/translation) is out of scope for Phase 26 (Layer-1 completeness only).
