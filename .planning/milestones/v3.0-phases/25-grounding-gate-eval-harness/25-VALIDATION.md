# Phase 25 — Grounding Gate + Eval Harness · Validation Strategy (Nyquist)

**Requirements:** GND-01 (citation resolves to a real chunk), GND-02 (structured answer, fail-closed gate, eval harness)
**Goal under test:** A fail-closed grounding-by-construction gate turns structured agent answers into
trustworthy cited output, and the same gate run over a tracked PII-free question set IS the automated
eval harness — the contract every later producer (Phase 26 checklist, Phase 27 document agents) emits into.

This file is the **sampling plan**: for each ROADMAP success criterion it names the smallest set of
automated checks that would catch a regression (the Nyquist rate — sample often enough that no failure
mode hides between probes). Every check is an `automated` command runnable today; none requires the real
`corpus/` except the explicitly `@skipUnless`-guarded real-corpus eval/integration smoke. **The bare
`python` shim is broken (Windows pyenv-win CRLF / `/bin/sh^M`); every command runs through
`.venv/bin/python -m …`.** Tests are stdlib `unittest` driven by pytest — no pytest fixtures, no network.

---

## Success-criterion → validation map

| SC (GND) | What must be TRUE | Validating test(s) | Plan |
|----------|-------------------|--------------------|------|
| **SC1** Structured answer; gate checks ONLY `claims[]` | `{question, claims:[{id,text,citations[],quote}], basis[], abstentions[], prose}` parses; `prose`/`basis`/`abstentions` are never citation-checked, so non-factual filler never trips a false failure | `test_grounding.py -k "filler"` (filler prose does not fail), `TestGroundCli` (CLI envelope) | 01, 02 |
| **SC2** Grounding-by-construction, fail-closed, exit 1 | every claim needs ≥1 citation that `resolve()` returns AND a `quote` that is a `_norm` substring of that chunk; ANY uncited / unresolvable / quote-mismatch claim → `verdict:"fail"`, render nothing, `ok:true` exit **1** | `test_grounding.py -k "uncited or unresolvable or quote"` (three fail-closed reasons each asserted), `TestGroundCli` (verdict-fail → exit 1, writes nothing) | 01, 02 |
| **SC3** Render to `personal/output/` + RPT-03 scan → exit 4 | a passing answer renders ONLY under git-ignored `personal/output/`; the rendered text is re-scanned with `check_publish_safe.scan_text` before write; a PII/secret/abs-path hit refuses output `ok:false`/`internal_error`/exit **4** | `TestGroundCli` (pass writes one file under `personal/output/`; injected unsafe content → exit 4), manual round-trip in 25-02 | 02 |
| **SC4** `--eval` over tracked PII-free set; `eval_runner` shape; `must_abstain`; non-zero on any ungrounded | `--eval crawler/eval/questions.jsonl` emits `{total,passed,failed,failures}`; an ungrounded line → exit 1 with its id in `failures`; a `must_abstain` line carrying claims → `should_have_abstained`; real-corpus run has `failed==0` | `test_grounding.py -k "eval or must_abstain"` (synthetic index + inline jsonl), real-corpus `--eval` smoke (skipUnless `corpus/index.db`) | 03 |
| **SC5** Honesty boundary documented; quote+claim side-by-side; VAL-01/02 deferred | the gate guarantees resolvability + verbatim-quote, NOT semantic entailment; rendered output places `quote` beside its `claim` for human review; VAL-01/02 absent from all plans | `test_grounding.py -k "render"` (quote rendered beside claim), `grep` gates on `grounding.py` docstring + `CONTRACT.md` honesty-boundary note | 01, 02 |

---

## The validation strands (and how each is sampled)

### 1. Fail-closed verdict — the headline (SC2, GND-01+GND-02)
- **Pure-function (default suite):** `quote_is_grounded()` smoke — `.venv/bin/python -c "from crawler import grounding as g; assert g.quote_is_grounded('A  B','x a   b y'); assert not g.quote_is_grounded('zzz','abc'); assert not g.quote_is_grounded('','abc')"` proves the `_norm` whitespace/case substring check (and that an empty quote is NOT trivially grounded).
- **Claim-level (default suite):** unit tests drive the three fail-closed reasons through `check_answer()`: an **uncited** claim, an **unresolvable** citation (`resolve()` → None on unknown/sha-drift), and a **quote-mismatch** claim each force `verdict:"fail"`. `-k "uncited or unresolvable or quote"` isolates them.
- **Boundary (default suite):** `TestGroundCli` proves a verdict-fail answer piped to `cli.main` returns `ok:true` / `verdict:"fail"` / **exit 1** and writes nothing user-facing.

### 2. Claims-only scoping (SC1, GND-02)
- `-k "filler"` asserts that `prose` / `basis` / `abstentions` content — including text that would never resolve — does NOT trigger a failure: only `claims[]` is citation-checked. This is the guard against false failures on non-factual filler.

### 3. Publish-safety render-then-gate (SC3, GND-02)
- `TestGroundCli`: a **passing** answer writes exactly one file under `personal/output/` (git-ignored; `CORPORA_PREFIXES` includes `personal/`, and `is_excluded()` does NOT exclude `personal/`, so the scan actually runs). An answer whose rendered text contains an injected abs-path / secret is refused `ok:false` / `error.type:"internal_error"` / **exit 4** — mirroring `dupaudit.py:614-629` / `dupclean.py:575-589`. No new exit code; `SCHEMA_VERSION` stays `"1.0"`.

### 4. Contract stability (SC1/SC5, GND-02)
- **Grep + import gate:** `grep -q '### ground' crawler/CONTRACT.md && grep -q 'ground' crawler/contract.py && .venv/bin/python -c "import crawler.contract as ct; assert ct.SCHEMA_VERSION=='1.0'; assert not hasattr(ct,'EXIT_PUBLISH_UNSAFE')"` — proves `ground` is documented 1:1, the five envelope keys + schema version are unchanged, and NO new exit/error constant was added (additive-only).

### 5. Eval harness = the same gate over a tracked PII-free set (SC4, GND-02)
- **Synthetic (default suite):** `run_eval` over a tiny inline `questions.jsonl` in a TemporaryDirectory against a synthetic index asserts (a) all-grounded → `{total,passed,failed:0,failures:[]}` exit 0, (b) one ungrounded line → exit 1 with that id in `failures`, (c) a `must_abstain` line that carries claims → `should_have_abstained`.
- **Real-corpus (guarded smoke):** `.venv/bin/python -m crawler.cli --json ground --db corpus/index.db --eval crawler/eval/questions.jsonl` runs (not skipped when `corpus/index.db` exists) and asserts `ok:true`, `command=="ground"`, the four keys present, and `result.failed == 0`.
- **PII self-scan (default suite):** the tracked `crawler/eval/questions.jsonl` is itself scanned — `-k "pii or self_scan or scan"` plus `grep -nE '/home/|/Users/|pr-ai-venv|BEGIN [A-Z ]*PRIVATE KEY' crawler/eval/questions.jsonl` returns nothing. The fixture is the #1 PII-leak temptation and is gated. <!-- # publish-safe: allow -->

---

## Nyquist rate justification

- **Continuous sampling, 2 automated probes per plan** (one fast `-c`/`-k` smoke + one full-file run), so no failure mode hides between probes: the escaper/substring logic (strand 1) is sampled at the pure-function, claim, and CLI-boundary levels; the contract (strand 4) at grep + import; the PII boundary (strand 5) at both unit and `grep` levels.
- **No watch-mode, no E2E browser suite, no network** — every check is a deterministic `unittest`/CLI invocation finishing in seconds; the only environment-gated probe is the real-corpus eval, which `@skipUnless(Path("corpus/index.db").is_file())` keeps CI-safe while still RUNNING locally (where the 742-doc index is present).
- **Regression floor:** every plan re-asserts `.venv/bin/python -m pytest crawler/tests/ -q` stays GREEN against the 167-test baseline, so the gate cannot silently regress search/resolve/contract.

## Honesty boundary (explicit)

The gate validates **resolvability + verbatim-quote substring** only. It does NOT check semantic
entailment / faithfulness (does the quote actually *support* the claim) — that needs a model/NLI and is
deferred as **VAL-01 / VAL-02**, intentionally absent from all Phase-25 plans to honor the
no-vectors / no-cloud constraint. Rendered output shows each `quote` beside its `claim` so a human can
make the entailment judgement the gate deliberately does not.
