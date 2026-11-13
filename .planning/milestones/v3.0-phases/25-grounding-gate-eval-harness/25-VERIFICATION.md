---
phase: 25-grounding-gate-eval-harness
verified: 2026-06-21T05:02:50Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification — no prior VERIFICATION.md existed."
---

# Phase 25: Grounding Gate + Eval Harness — Verification Report

**Phase Goal:** A fail-closed grounding-by-construction gate turns structured agent answers into trustworthy cited output, and the same gate run over a tracked PII-free question set IS the automated eval harness. This is the contract every later producer (checklist, agents) emits into.
**Verified:** 2026-06-21T05:02:50Z
**Status:** passed
**Re-verification:** No — initial verification
**Requirements:** GND-01, GND-02 (both accounted for; VAL-01/02 intentionally deferred and absent from plan requirements)

## Goal Achievement

### Observable Truths

Truths are the union of the 5 ROADMAP success criteria (the non-negotiable contract), the merged PLAN frontmatter must-haves across plans 01–03, and the 6 prompt-supplied verification truths. All were verified against the ACTUAL code + live behavior, not SUMMARY claims.

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 1  | Answer is one structured JSON object `{question, claims:[{id,text,citations[],quote}], basis[], abstentions[], prose}`; the gate checks ONLY `claims[]` — prose/basis/abstentions never citation-checked (SC1, GND-02) | ✓ VERIFIED | `grounding._validate_shape` validates only `question`+`claims[]`; `check_answer` (grounding.py:162-180) iterates `claims` exclusively. CLI live: a grounded answer with bogus `prose`/`basis` filler still returned `verdict:"pass"`, `ungrounded:0`, exit 0. Unit `test_filler_is_never_inspected` passes. |
| 2  | Fail-closed: any uncited / unresolvable / quote-mismatch claim → `verdict:"fail"`, render nothing, `ok:true`, exit 1 (SC2, GND-01/02) | ✓ VERIFIED | Live CLI (real corpus): uncited → `{verdict:fail, reasons:["uncited"]}` ok:true exit 1; bad id → `["unresolvable"]` exit 1; real id + wrong quote → `["quote_not_in_chunk"]` exit 1. All `result:`-bearing (ok:true), nothing written. cli.py:499-506 returns 1 on non-pass without render. |
| 3  | Quote check uses `_norm` whitespace/case substring; per-citation resolver is `searchindex.resolve()` called in-process (GND-01) | ✓ VERIFIED | `quote_is_grounded` = `bool(quote) and _norm(quote) in _norm(chunk_text)` (grounding.py:79-86); `_norm` = `re.sub(r"\s+"," ",s).strip().lower()`. `check_claim` calls `searchindex.resolve(db, str(cid))` in-process (grounding.py:110), never shells out. `import crawler.searchindex` at module top. |
| 4  | Passing answer renders ONLY to git-ignored `personal/output/`, re-scanned with `check_publish_safe.scan_text` BEFORE write; PII/secret/abs-path hit → `ok:false`/`internal_error`/exit 4, nothing written (SC3, RPT-03) | ✓ VERIFIED | Live: grounded answer wrote `personal/output/are-ideco-...md` (verified git-ignored via `git check-ignore`). cli.py:511-515 refuses any `--out-dir` not under `personal/`. cli.py:525-541 imports `check_publish_safe`, scans rendered bytes, and on a hit emits `internal_error` exit 4 writing nothing. Live injection of `~/secrets/...` into a grounded claim → `ok:false`/`internal_error`/exit 4, no file written. |
| 5  | Exit codes reuse existing constants (no new `EXIT_*`); `SCHEMA_VERSION "1.0"` + 5 envelope keys unchanged; only additive `ground` command (SC3 stability) | ✓ VERIFIED | `git show acfe968 -- crawler/contract.py`: only additive `ground` token added to command enum docstrings; `SCHEMA_VERSION="1.0"` and 5 keys (schema_version, ok, command, result, error) unchanged. Exit constants remain `EXIT_INVALID_INPUT=2`/`EXIT_MISSING_DEPENDENCY=3`/`EXIT_INTERNAL_ERROR=4`; exit 4 path reuses `EXIT_INTERNAL_ERROR`. cli.py metavar additively lists `ground`. |
| 6  | The SAME gate over `crawler/eval/questions.jsonl` via `--eval` emits `{total,passed,failed,failures}`, exits non-zero on any ungrounded, includes adversarial `must_abstain` → `should_have_abstained` (SC4, GND-02) | ✓ VERIFIED | `run_eval` reuses `check_answer` per line (grounding.py:223); must_abstain line passes iff `len(claims)==0` else `["should_have_abstained"]` (grounding.py:218-221). Live real-corpus `--eval`: `{total:4,passed:4,failed:0,failures:[]}` exit 0. Unit tests cover ungrounded→exit 1 (id in failures) and must_abstain-carrying-claims→should_have_abstained. |
| 7  | `crawler/eval/questions.jsonl` is TRACKED, PII-FREE, synthetic; grounded lines resolve against real `corpus/index.db` with verbatim quotes (SC4) | ✓ VERIFIED | `git ls-files` confirms tracked. Content is synthetic (Ideco SA cert, IME, + adversarial fictional "Lunar Gateway"/"Kingdom of Eldoria"). 4 lines (≥2 grounded + 2 must_abstain). `TestFixturePublishSafety` self-scans the tracked bytes (NOT skip-guarded) and asserts no `/home/`,`/Users/`,`pr-ai-venv` markers. Real-corpus eval `failed==0` proves verbatim resolution. | <!-- # publish-safe: allow -->
| 8  | Honesty boundary documented: resolvability + verbatim-quote, NOT semantic entailment; VAL-01/02 deferred and ABSENT from plan requirements (SC5) | ✓ VERIFIED | Documented in `grounding.py` module docstring (lines 23-30), `CONTRACT.md` honesty-boundary note (lines 271-276), and the render footer. VAL-01/02 appear in plans ONLY as deferral prose — NOT in any `requirements:` frontmatter (plans declare GND-01/GND-02 only). REQUIREMENTS.md lists VAL-01/02 in the deferred section (no phase mapping). |
| 9  | Quote + claim render side-by-side for human review (SC5) | ✓ VERIFIED | `render_answer` (grounding.py:241-292) emits per claim: claim text, the verbatim `quote` as a blockquote, then resolved citation fields, ending with the honesty footer. Live render of the Ideco answer shows claim → `> Certificates from Ideco Biometrics are **not** valid…` → `police-certificates/south-africa.md` citation. `test_render_*` (incl. no-absolute-paths) pass. |
| 10 | Malformed stdin / missing-key answer / non-file `--db` → `invalid_input` exit 2 (plan-02 must-have) | ✓ VERIFIED | Live: `not json{` → `ok:false`/`invalid_input`/exit 2; `--db corpus/nope.db` → `ok:false`/`invalid_input`/exit 2. `InvalidAnswer` mapped to exit 2 (cli.py:494-495). Unit `test_malformed_stdin_*`, `test_non_file_db_*`, `test_claim_missing_quote_raises_invalid` pass. |
| 11 | GND-01 + GND-02 both implemented and accounted for; no orphaned requirements | ✓ VERIFIED | GND-01 (citation resolver fail-closed) satisfied by in-process `searchindex.resolve` consumption. GND-02 (grounding-by-construction gate doubling as eval harness) satisfied by `check_answer` + `run_eval`. Traceability maps both to Phase 25; both covered by declared plan requirements. No orphaned IDs. |
| 12 | Grounding suite green; full suite green EXCEPT the known pre-existing `test_dupaudit::TestRealCorpus` | ✓ VERIFIED | `pytest test_grounding.py` → 32 passed. Per-file: cli 6, engine_refactor 6, parity_ircc 6, profile_loader 15, template_profile 4, json_contract 26(+1 skip), searchindex 59, dupclean 18, dupaudit excl-TestRealCorpus 25. ONLY failure: `TestRealCorpus::test_audit_runs_clean_with_expected_counts` → `AssertionError: 0 not >= 1` (line 548) — reproduced live, documented pre-existing in deferred-items.md. |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/grounding.py` | Pure-stdlib compute: InvalidAnswer, _norm, quote_is_grounded, check_claim, check_answer, render_answer, run_eval | ✓ VERIFIED | 293 lines; all symbols present and substantive; stdlib-only (`re`, `json`, `pathlib`, `crawler.searchindex`); no stubs/debt markers. |
| `crawler/cli.py` (`_cmd_ground` + `p_ground`) | ground handler + subparser + `--eval`/`--db`/`--out-dir`; `ground` in metavar | ✓ VERIFIED | `_cmd_ground` (lines 414-551) fully wired: eval branch, stdin parse, verdict map, render→scan→write; `p_ground` subparser registered; metavar additively lists `ground`. |
| `crawler/CONTRACT.md` | additive `### ground` section + honesty boundary + exit notes | ✓ VERIFIED | `### ground` section (line 218+) documents stdin shape, result fields, verdict-fail rule, publish-unsafe refusal, honesty boundary; `schema_version` stability promise intact. |
| `crawler/contract.py` | `ground` added to command enumeration | ✓ VERIFIED | Additive-only diff (commit acfe968); SCHEMA_VERSION "1.0" + 5-key envelope unchanged; no new constants. |
| `crawler/eval/questions.jsonl` | tracked PII-free set: ≥2 grounded + ≥1 must_abstain | ✓ VERIFIED | Tracked, synthetic, PII-free; 4 lines (2 grounded + 2 adversarial must_abstain); resolves clean against real corpus. |
| `crawler/tests/test_grounding.py` | compute + CLI + eval + real-corpus + PII self-scan suite | ✓ VERIFIED | 625 lines, 32 tests across TestCheckClaim/TestCheckAnswer/TestRenderAnswer/TestRunEval/TestGroundCli/TestRealCorpusEval/TestFixturePublishSafety/TestFixtureStructure. All pass. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `grounding.check_claim` | `searchindex.resolve` | in-process per-citation resolve | ✓ WIRED | grounding.py:110 calls `searchindex.resolve(db, str(cid))`; live eval proves real chunks (with `text`) returned. |
| `grounding.quote_is_grounded` | `_norm` substring | `_norm(quote) in _norm(chunk text)` | ✓ WIRED | grounding.py:86; whitespace/case-tolerant, empty-quote fail-closed. |
| `cli._cmd_ground` | `grounding.check_answer`/`render_answer`/`run_eval` | lazy import + dispatch | ✓ WIRED | cli.py:447 lazy `from crawler import grounding`; all three dispatched. |
| `cli._cmd_ground` | `check_publish_safe.scan_text` | render-then-scan before write (RPT-03) | ✓ WIRED | cli.py:528-530 sys.path shim import + `cps.scan_text(...)` before any write; live exit-4 refusal confirms. |
| passing answer | `personal/output/` | write only after clean scan + personal/ guard | ✓ WIRED | cli.py:511-515 guard + 543-544 write; `git check-ignore` confirms dir ignored. |
| `run_eval` | `check_answer` | per-line gate reuse | ✓ WIRED | grounding.py:223 — the bar IS the eval machinery. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `run_eval` summary | `results` per line | `check_answer(rec, db)` → `searchindex.resolve` over real `corpus/index.db` | Yes — live `{total:4,passed:4}` against 742-doc index | ✓ FLOWING |
| `render_answer` output | resolved `chunk` fields | `searchindex.resolve(db, cid)` | Yes — live render shows real relpath/section/source_url/crawl_date | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Eval over tracked set, real corpus | `ground --eval questions.jsonl --db corpus/index.db` | `{total:4,passed:4,failed:0,failures:[]}` exit 0 | ✓ PASS |
| Fail-closed uncited | stdin uncited claim → `ground` | `verdict:fail` `["uncited"]` ok:true exit 1 | ✓ PASS |
| Fail-closed unresolvable | stdin bad id → `ground` | `["unresolvable"]` ok:true exit 1 | ✓ PASS |
| Fail-closed quote-mismatch | real id + wrong quote → `ground` | `["quote_not_in_chunk"]` ok:true exit 1 | ✓ PASS |
| Pass renders to personal/output | grounded answer → `ground --out-dir personal/output` | `verdict:pass` exit 0, one file under git-ignored dir | ✓ PASS |
| Publish-unsafe refusal | abs-path injected in grounded claim text | `ok:false`/`internal_error`/exit 4, nothing written | ✓ PASS |
| Filler not citation-checked | grounded answer + bogus prose/basis | `verdict:pass` exit 0 (SC1) | ✓ PASS |
| Malformed stdin / non-file db | `not json{` / `--db corpus/nope.db` | `invalid_input` exit 2 | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared for this phase; verification is via the pytest `unittest` suite and CLI smoke (the phase's documented Nyquist sampling plan). N/A.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| GND-01 | 25-01, 25-02 | Citation resolver verifies every emitted citation ID resolves to a real chunk; unresolvable/missing fail closed | ✓ SATISFIED | `check_claim` calls `searchindex.resolve` in-process; unknown/sha-drift → `unresolvable` fail-closed (live + unit). |
| GND-02 | 25-01, 25-02, 25-03 | Grounding-by-construction gate; any uncited factual claim fails the whole output; doubles as the eval harness | ✓ SATISFIED | `check_answer` whole-answer fail on any violation; `run_eval` is the same gate over the tracked set (live exit 0; unit exit-1-on-ungrounded). |

No orphaned requirements: REQUIREMENTS.md traceability maps GND-01/GND-02 → Phase 25; both are claimed by plan frontmatter and verified. VAL-01/02 are explicitly deferred (no phase mapping) and correctly absent from plan requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | None | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/`return null|{}|[]` stubs in `grounding.py`, the `ground` section of `cli.py`, `questions.jsonl`, or `contract.py`. `return ["uncited"]`/`[]` in `check_claim` are real fail-closed/grounded verdicts, not stubs. |

### Human Verification Required

None. The phase produces deterministic, fully CLI-/unit-testable code with no visual, real-time, or external-service surface. Every observable truth was exercised programmatically (live CLI against the real 742-doc corpus + 32 unit tests). The honesty boundary's deferral of semantic entailment (VAL-01/02) is an intentional, documented product property — the render places quote beside claim so the eventual human/Phase-27 entailment judgement is possible — not an open verification item for this phase.

### Gaps Summary

No gaps. All 5 ROADMAP success criteria, all merged PLAN must-haves (truths, artifacts, key links), and all 6 prompt-supplied verification truths are VERIFIED against the actual codebase and live behavior:

- The gate is one structured JSON object checking ONLY `claims[]` (filler proven inert).
- Fail-closed across all three reasons (uncited / unresolvable / quote-mismatch) with `ok:true`/exit 1 and nothing rendered; quote uses `_norm`; GND-01 resolution is in-process `searchindex.resolve`.
- Passing answers render ONLY to git-ignored `personal/output/`, re-scanned with `check_publish_safe.scan_text` first; a publish-unsafe hit refuses with `ok:false`/`internal_error`/exit 4. Exit codes reuse existing constants, schema stays `"1.0"` with 5 keys, `ground` is purely additive.
- The SAME gate is the eval harness over the tracked, PII-free, synthetic `questions.jsonl`: live real-corpus run `{total:4,passed:4,failed:0}` exit 0; adversarial `must_abstain` correctness enforced.
- The honesty boundary (resolvability + verbatim-quote, NOT entailment) is documented in code, CONTRACT.md, and the render footer; VAL-01/02 are deferred and absent from plan requirements.

The only failing test in the full suite is `crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts` (`AssertionError: 0 not >= 1`), a pre-existing real-corpus dedup-signal data issue unrelated to grounding, reproduced on a clean tree and logged in `deferred-items.md`. It is explicitly out of scope for Phase 25 and does not block the goal.

---

_Verified: 2026-06-21T05:02:50Z_
_Verifier: the agent (gsd-verifier)_
