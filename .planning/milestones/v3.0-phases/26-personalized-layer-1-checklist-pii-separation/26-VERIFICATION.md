---
phase: 26-personalized-layer-1-checklist-pii-separation
verified: 2026-06-21T12:21:07Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification — no prior VERIFICATION.md"
---

# Phase 26: Personalized Layer-1 Checklist + PII Separation — Verification Report

**Phase Goal:** Generate a personalized, fully-cited Layer-1 "which documents you need" checklist for a post-ITA Express Entry applicant from a LOCAL profile, with all PII kept strictly out of the repo and the corpus DB.
**Verified:** 2026-06-21T12:21:07Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

Goal-backward verification was run against the ACTUAL codebase and live behavior, not SUMMARY claims. The corpus index (`corpus/index.db`, 14 MB) is present, so all `@skipUnless` real-corpus tests executed (not skipped). Every observable truth is backed by code inspection + an executed command.

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | Generator reads `$PR_PERSONAL_DIR/profile.yaml` (default `./personal/`) and produces a Layer-1 checklist where every requirement line is a gated, cited `claims[]` entry passing the Phase-25 gate (`verdict:"pass"`). [CHK-01] | ✓ VERIFIED | `personal_dir()` = `Path(os.environ.get("PR_PERSONAL_DIR","personal"))` (checklist.py:51-59). Live CLI smoke `PR_PERSONAL_DIR=personal.example … checklist --db corpus/index.db --out-dir personal/output` → `{ok:true, verdict:"pass", total_claims:6, grounded:6, ungrounded:0, out:"personal/output/checklist.md"}`, exit 0. `build_answer` runs the assembled answer THROUGH `grounding.check_answer` (checklist.py:381) and the CLI re-gates (cli.py:654). |
| 2   | PII tier split: applicability lives ONLY in `basis[]`, never gated/rendered; requirement text+citation come from corpus and are gated. Sentinel tokens appear in `basis[]` but NEVER in `claims[].text/quote` or rendered output. [CHK-01, CHK-02] | ✓ VERIFIED | `applicable_items` routes country/date/count into `basis` only; `text`/`query` never interpolate a profile value (checklist.py:91-228). Rendered `personal/output/checklist.md` contains **0** occurrences of `Wakanda`/`Latveria` (the only `citizenship` substring match is the IRCC department URL `immigration-refugees-citizenship`, not the profile value). `grounding.render_answer` never references `basis` (confirmed in grounding.py). Tests `test_pii_never_in_claims_text_or_quote`, `test_pii_retained_in_basis` pass. |
| 3   | No claim cites a country-specific relpath (`police-certificates/<country>`) — code-level backstop in `grounded_claim` AND a test. [CHK-02] | ✓ VERIFIED | `_COUNTRY_SPECIFIC_FAMILIES=("police-certificates/",)` + `_is_country_specific()` backstop skips per-country hits on BOTH the search row and the resolved relpath (checklist.py:250-262, 313, 320). Tests: `test_backstop_skips_country_page_grounds_generic`, `test_only_country_page_grounds_to_none`, `test_no_claim_cites_country_specific_page`, real-corpus `test_…_cites_no_country_specific_page` — all pass. Live rendered output cites generic `guidance/police-certificates.md`, not a country page. |
| 4   | Rendered checklist written ONLY under git-ignored `personal/output/` (anchored containment); `personal.example/` tracked while `personal/` ignored; render-then-scan via `check_publish_safe.scan_text` over rendered bytes returns `[]` (fail-closed → exit 4 otherwise). [CHK-02] | ✓ VERIFIED | `_personal_root()` anchored resolve()-containment (cli.py:669-674) rejects out-of-anchor `--out-dir` as invalid_input/exit 2. `git check-ignore personal/output/checklist.md` → IGNORED; `git ls-files personal/` → empty; `personal.example/profile.yaml` tracked. `scan_text("checklist.md", rendered)` → `[]` (executed live). `test_publish_unsafe_render_is_internal_error_exit_4_no_write` proves a scan hit → exit 4, NOTHING written. |
| 5   | Contract additive-only: new `checklist` command, `SCHEMA_VERSION "1.0"`, 5 envelope keys + `EXIT_*` unchanged; exit mapping mirrors `ground` (verdict-fail=1, publish-unsafe=4, invalid_input=2). | ✓ VERIFIED | `envelope('checklist', …)` returns the 5 stable keys, schema_version "1.0" (executed). Exactly 3 `EXIT_*` constants (2,3,4) — unchanged. `git diff` of contract.py is doc-only (command-union string in two docstrings). `### checklist` section in CONTRACT.md documents result shape + exit mapping + "schema_version stays 1.0". Exit mapping in cli.py:628/639 (=2), :662 (=1), :702 (=4). Gate primitives `grounding.py`/`searchindex.py`/`check_publish_safe.py` UNMODIFIED by the phase. |
| 6   | Checklist suite + full suite + real-corpus CLI smoke green except the known pre-existing `test_dupaudit::TestRealCorpus`; real-corpus checklist renders a passing gated PII-free output. | ✓ VERIFIED | `pytest crawler/tests/test_checklist.py` → **55 passed**. Full suite minus dupaudit → **241 passed, 1 skipped, 59 subtests passed**. `test_dupaudit.py` → 25 passed, **1 failed = the documented `TestRealCorpus` (`result.exact==0`)**, out of scope per the prompt. CLI smoke → verdict pass, 6 claims, PII-free output written. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/checklist.py` | `personal_dir`, `load_profile`, `applicable_items`, `grounded_claim`, `build_answer` + country backstop | ✓ VERIFIED | 399 lines, all symbols present + substantive; `yaml.safe_load` only (never `yaml.load`); imported & used by cli.py and tests. |
| `personal.example/profile.yaml` | Tracked synthetic sentinel profile (CEC + foreign-edu) | ✓ VERIFIED | Tracked (git ls-files), loads as mapping, drives every test + the live real-corpus smoke. Sentinel countries Wakanda/Latveria only. |
| `crawler/tests/test_checklist.py` | profile/applicability/grounds/PII/CLI/real-corpus/tracked-tree tests | ✓ VERIFIED | 927 lines, 55 tests, all pass. Assertions are non-vacuous (guards on `answer["claims"]`). |
| `crawler/cli.py` (`_cmd_checklist` + subparser) | `checklist` verb reusing `_personal_root` + render→scan→write | ✓ VERIFIED | `--help` lists --db/--out-dir/--profile/--emit-answer; metavar includes `checklist`; exit mapping mirrors `ground`. |
| `crawler/contract.py` | Additive `checklist` command value | ✓ VERIFIED | Doc-only additive diff; schema_version "1.0", 5 keys, EXIT_* unchanged. |
| `crawler/CONTRACT.md` | `### checklist` section | ✓ VERIFIED | Documents result shape, exit mapping, RPT-03 refusal, honesty boundary, schema-stability line. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `checklist.build_answer` | `grounding.check_answer` | answer passes THROUGH the Phase-25 gate | ✓ WIRED | checklist.py:381 + re-gated in cli.py:654; live verdict pass. |
| `checklist.grounded_claim` | `searchindex.search` / `resolve` | retrieve generic chunk then resolve verbatim | ✓ WIRED | checklist.py:303 (search), :315 (resolve); fail-closed on None. |
| `claims[].text` | `item['text']` (generic only) | PII never enters gated claim text | ✓ WIRED | checklist.py:327 — claim text = generic label; verified PII-free in rendered output. |
| `_cmd_checklist` | `render_answer` + `scan_text` + `_personal_root` | gate→render→RPT-03 scan→anchored write | ✓ WIRED | cli.py:669,676,691. |
| rendered checklist bytes | `check_publish_safe.scan_text` | fail-closed publish-safety scan (neutral label) before any write | ✓ WIRED | cli.py:691 `scan_text("checklist.md", rendered_md)`; live result `[]`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `personal/output/checklist.md` | `answer["claims"]` (6 claims) | `build_answer` → `grounded_claim` → `searchindex.resolve(corpus/index.db)` | Yes — 6 real IRCC claims with verbatim quotes + resolvable citations (legislation-irpr, language-test, medical, biometrics, eca, police-certificates) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Real-corpus checklist renders a passing PII-free output | `PR_PERSONAL_DIR=personal.example .venv/bin/python -m crawler.cli --json checklist --db corpus/index.db --out-dir personal/output` | `ok:true, verdict:pass, 6/6 grounded, out=personal/output/checklist.md`, exit 0 | ✓ PASS |
| Rendered bytes scan clean | `cps.scan_text("checklist.md", rendered)` | `[]` | ✓ PASS |
| No sentinel PII in rendered output | `grep -c "Wakanda\|Latveria" personal/output/checklist.md` | `0` | ✓ PASS |
| No PII in corpus DB (CHK-02) | `sqlite3 corpus/index.db` LIKE %Wakanda%/%Latveria% | `0` hits each | ✓ PASS |
| Contract additive envelope | `contract.envelope('checklist', …)` | 5 keys, command checklist, schema 1.0 | ✓ PASS |
| Output is git-ignored | `git check-ignore personal/output/checklist.md` | IGNORED; `git ls-files personal/` empty | ✓ PASS |
| Abstention honesty boundary | `build_answer` with mocked-empty / all-ungrounded items | claims `[]` + non-empty `abstentions[]` (tests) | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| (none) | — | No `scripts/*/tests/probe-*.sh` exist or are declared by the phase | N/A — verification driven by pytest (executed directly) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| CHK-01 | 26-01, 26-02, 26-03 | Personalized, grounded+cited Layer-1 checklist from local profile | ✓ SATISFIED | Live CLI smoke verdict pass, 6 grounded+cited claims; every claim through Phase-25 gate; truths 1,2,3,5,6. |
| CHK-02 | 26-01, 26-02, 26-03 | All user PII stays in git-ignored area — never repo or corpus DB | ✓ SATISFIED | `personal/` ignored & empty; rendered output + corpus DB carry 0 sentinel PII; scan_text `[]`; anchored containment + exit-4 refusal; truths 2,3,4. |

No orphaned requirements: both CHK-01 and CHK-02 are mapped to Phase 26 in REQUIREMENTS.md and declared in every plan's `requirements:` frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` in any phase file | — | The two `return None` in `checklist.py` (305, 331) are intentional, documented, tested fail-closed abstention paths — not stubs. |

### Human Verification Required

None for the phase goal. The gate's semantic-entailment limitation (a human judging whether each quoted span *supports* the requirement) is an explicitly documented honesty boundary inherited from Phase 25 (VAL-01/02), declared **out of scope** for Phase 26 in 26-VALIDATION.md and CONTRACT.md. The Phase-26 deliverables — citation resolvability, verbatim quoting, PII separation, and anchored containment — are all deterministically testable and were verified in code + live behavior. No `<verify><human-check>` blocks were deferred in any PLAN.

### Gaps Summary

No gaps. All six must-have truths are VERIFIED against the actual codebase and live execution. The contract change is additive-only and the Phase-24/25 gate primitives are unmodified. The single failing test in the wider suite (`test_dupaudit.py::TestRealCorpus`, `result.exact==0`) is the documented pre-existing, unrelated condition explicitly excluded from this phase's scope — it reproduces on a clean tree and is logged in deferred-items. The phase goal is achieved: a personalized, fully-cited, PII-free Layer-1 checklist is generated from a local profile, written only under the git-ignored `personal/output/`, with all PII kept out of the repo and the corpus DB.

---

_Verified: 2026-06-21T12:21:07Z_
_Verifier: the agent (gsd-verifier)_
