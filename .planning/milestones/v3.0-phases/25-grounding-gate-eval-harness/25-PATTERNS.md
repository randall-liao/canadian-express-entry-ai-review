# Phase 25: Grounding Gate + Eval Harness — Pattern Map

**Mapped:** 2026-06-21
**Requirements:** GND-01 (citation resolver verifies every id), GND-02 (grounding-by-construction fail-closed gate; doubles as eval harness)
**Files analyzed:** 6 new/modified artifacts — a new `crawler/groundgate.py` compute module, a `ground` verb (`_cmd_ground` + `p_ground`) in `crawler/cli.py`, additive doc edits to `crawler/CONTRACT.md` + `crawler/contract.py` docstring, a tracked PII-free `crawler/tests/fixtures/questions.jsonl`, and new tests `crawler/tests/test_groundgate.py`

> **⚠ FILE-NAME MAPPING (PATTERNS ↔ PLANS).** The PLANs finalized different (equivalent) names than this
> pattern map's working names. The pattern *content/excerpts* below are name-agnostic and apply as-is;
> wherever this file says `groundgate`, `test_groundgate`, or `tests/fixtures/questions.jsonl`, the plans
> (and executors) use:
> - `crawler/groundgate.py` → **`crawler/grounding.py`**
> - `crawler/tests/test_groundgate.py` → **`crawler/tests/test_grounding.py`**
> - `crawler/tests/fixtures/questions.jsonl` → **`crawler/eval/questions.jsonl`** (tracked, PII-free; `crawler/eval/` ships with the package)
>
> Treat the plan names as authoritative; this map's analogs/excerpts remain valid.
**Analogs found:** 5 / 6 surfaces have strong in-repo analogs. The gate is **assembled entirely from shipped Phase-23/24 primitives** — `searchindex.resolve()` (the resolver it calls per citation), `contract.envelope()`/exit codes, `eval_runner`'s `{total,passed,failed,failures}` shape + `_norm` normalizer, and `check_publish_safe.scan_text` (RPT-03 render-then-scan). The only *no-clean-analog* surfaces are (a) reading a JSON **answer object from stdin** (no existing CLI verb reads stdin) and (b) the quote-substring **verbatim check** (new pure helper — model it on `eval_runner._norm` + the `searchindex.chunk_sha` pure-helper shape).

> **Scope note for the planner.** Phase 25 is GND-01 + GND-02 ONLY. **Do NOT modify** `searchindex.py` (`search`/`resolve`/`build_index`/DDL shipped Phase 23/24 and are GREEN) — the gate is a *consumer* of `searchindex.resolve()`. **Do NOT modify** `scripts/check_publish_safe.py` — the gate is a *consumer* of `scan_text()`/`CORPORA_PREFIXES`. The gate's logic lives in a **new** `crawler/groundgate.py`; the `ground` verb is a **thin** addition to the **existing** `crawler/cli.py` dispatcher (mirror `_cmd_search`); the contract stays `schema_version "1.0"` (additive). Honesty boundary (resolvability + verbatim-quote, NOT semantic entailment) must be stated in the module docstring + CONTRACT.md, never silently widened.

---

## CRITICAL ENV CONSTRAINT (read before any test run)

Bare `python` is **broken** in this environment — it resolves to a Windows pyenv shim with a CRLF interpreter line:

```
$ python --version
~/.pyenv/.../python: /bin/sh^M: bad interpreter: No such file or directory
```

**All Python / tests MUST run via the repo venv interpreter:**

```bash
.venv/bin/python -m pytest crawler/tests/test_groundgate.py -q
.venv/bin/python -m pytest crawler/tests/ -q            # full suite
.venv/bin/python -m crawler.cli --json ground --db corpus/index.db < answer.json
```

`.venv/bin/python` is CPython 3.10.12 with FTS5. Every plan's verification/test command must use `.venv/bin/python -m …`, never bare `python` and never `poetry run` (poetry not guaranteed wired here). The doc strings in `searchindex.py`/`eval_runner.py` say `poetry run python …` — that is aspirational; in THIS sandbox use `.venv/bin/python`.

---

## File Classification

| New/Modified Artifact | Role | Data Flow | Closest Analog | Match Quality |
|-----------------------|------|-----------|----------------|---------------|
| `crawler/groundgate.py` — `ground()`/`check_answer()` gate + `{total,passed,failed,failures}` eval mode + pure quote-normalize helper + exceptions | service / compute (read-only) | transform + request-response (structured answer JSON → verdict) | **`crawler/searchindex.py`** module shell (docstring/`from __future__`/exceptions/pure helpers, `searchindex.py:1-45,101-135`) + **`crawler/eval_runner.py`** run-loop & result shape (`eval_runner.py:43-150`) + **`searchindex.resolve()`** (the resolver it calls, `searchindex.py:502-562`) | **exact (shells)** / no-analog (quote-substring check) |
| `_cmd_ground` handler + `p_ground` subparser in `crawler/cli.py` | controller / route dispatcher | request-response (stdin JSON → one envelope) | **`cli.py:_cmd_search`** (`294-411`) + **`_cmd_index`** (`245-291`) for thin-dispatch/lazy-import/envelope/exit-map; **`_cmd_report`** (`210-242`) for the `verdict:"fail"` → exit-nonzero-but-`ok:true` rule; `p_search` (`482-494`) for the subparser | **exact** (verb shell) / no-analog (stdin read) |
| `crawler/CONTRACT.md` + `crawler/contract.py` docstring (additive `### ground` section, result fields, error/exit notes) | config / docs | n/a | **`CONTRACT.md` `### search`** (`166-216`) + `### index` (`146-164`) + error/exit tables (`218-244`); `contract.py` command list (`13`, `69`) | **exact** |
| `crawler/tests/fixtures/questions.jsonl` — tracked, PII-free reference set (incl. adversarial `must_abstain`) | test fixture / data | n/a | tracked fixtures `crawler/tests/fixtures/*.json` (`raw_pages.json`, `urls.json`) + `eval_runner` eval-record shape (`eval_runner.py:6-22`, esp. `must_contain`/`must_not_contain`) | role-match (jsonl is new; record shape from eval_runner) |
| `crawler/tests/test_groundgate.py` — envelope-shape / exit-code / stdout-purity / fail-closed / eval-summary tests | test | n/a | **`crawler/tests/test_searchindex.py`** `_IndexCase`/`_make_index_corpus` (`292-370`), `TestSearchCli`+`_run` (`865-967`), `contract_exit_invalid_input` (`612-615`), `TestRealCorpus` skipUnless guard (`986-1027`) | **exact** |
| *(runtime only — not a tracked file)* render to git-ignored `personal/output/` + re-scan via `check_publish_safe.scan_text` before write | side-effect / file-I/O | file-I/O (render-then-gate) | **`scripts/check_publish_safe.py`** `scan_text` (`115-132`) + `exit_code` (`144-146`) + `CORPORA_PREFIXES` (`47`) | role-match (no existing pre-write caller — see §Shared Patterns) |

---

## Pattern Assignments

### `crawler/groundgate.py` (compute / service, read-only)

The gate is a **new module** assembled from shipped primitives. Copy three different shells for three different parts of it.

**1. Module shell + exceptions — copy `crawler/searchindex.py:1-45,101-106`.**
Same header conventions: a thorough module docstring that names the requirement + the honesty boundary, `from __future__ import annotations`, stdlib-only imports, and small `*Error` exception classes the CLI maps to exit codes (exactly how `EmptyQuery`/`FTS5Unavailable` are mapped by `_cmd_search`).
```python
"""Grounding-by-construction gate over structured agent answers (Phase 25 — GND-01/GND-02).

Reads ONE structured answer JSON on stdin — {question, claims:[{id, text, citations[], quote}],
basis[], abstentions[], prose} — and checks ONLY claims[]; prose/basis/abstentions are NEVER
citation-checked. Every claim must carry >=1 citation that resolve()s to a real chunk (GND-01)
AND whose verbatim `quote` is a whitespace/case-normalized substring of that chunk's stored text.
Any uncited, unresolvable, or quote-mismatch claim -> verdict:"fail", render nothing, exit non-zero.

HONESTY BOUNDARY (locked v3.0): this gate guarantees citation RESOLVABILITY + VERBATIM-QUOTE
substring, NOT semantic entailment / faithfulness (deferred VAL-01/02 — needs a model, violates
the no-vectors/no-cloud constraint). Quote and claim render side-by-side for human review.
"""
from __future__ import annotations

from pathlib import Path

from crawler import searchindex            # the SINGLE citation resolver (Phase 24)


class InvalidAnswer(ValueError):
    """Malformed stdin answer JSON (missing claims[], wrong shape) — CLI maps to INVALID_INPUT."""
```
- **Exceptions are CLI-mapped, not printed here** — `searchindex.EmptyQuery`'s docstring says exactly this ("the CLI maps it to INVALID_INPUT", `searchindex.py:106`). Keep `groundgate` pure: raise typed errors / return result dicts; let `_cmd_ground` own envelope + exit code (mirrors how `_cmd_search:386-395` catches `EmptyQuery`).

**2. The per-citation resolve — REUSE `searchindex.resolve()` verbatim (`searchindex.py:502-562`). Do NOT re-implement.**
`resolve(db, chunk_id)` already returns the **exact verbatim `text`** span (not a snippet) plus the five citation fields, returns `None` on an unknown id, AND already fails closed on sha-drift/stale rows (`searchindex.py:548-549`). The gate calls it once per citation and treats `None` as a fail-closed miss:
```python
hit = searchindex.resolve(db, citation_id)   # None = miss/stale -> fail closed (GND-01)
if hit is None:
    failures.append(f"unresolvable citation: {citation_id!r}")
    continue
chunk_text = hit["text"]                      # VERBATIM stored span — the quotable source
```
- The Phase-24 docstring explicitly calls this "the citation dict the Phase-25 grounding gate (GND-01) consumes" (`searchindex.py:505-507`) — the contract is already shaped for you.

**3. The quote-substring verbatim check — NEW pure helper, model on `eval_runner._norm` (`eval_runner.py:52-53`).**
`eval_runner._norm` is the exact whitespace/case normalizer the success criteria call for; copy it, then do a substring test:
```python
import re

def _norm(s: str) -> str:                     # COPIED from eval_runner.py:52-53
    return re.sub(r"\s+", " ", s).strip().lower()

def quote_is_grounded(quote: str, chunk_text: str) -> bool:
    """True iff `quote` is a whitespace/case-normalized substring of the resolved chunk."""
    return bool(quote) and _norm(quote) in _norm(chunk_text)
```
- Keep this helper **pure** (same shape as `searchindex.chunk_sha`, `searchindex.py:128-135`: stdlib `re`, no I/O, deterministic) so it is trivially unit-testable without a DB.
- `eval_runner` already uses `_norm(needle) in body` for its `must_contain` check (`eval_runner.py:82`) — same idiom, reuse it.

**4. The eval/run loop + result shape — copy `eval_runner.py` `DocResult`/`run`/`main` (`43-150`).**
The eval mode runs the gate over every record in `questions.jsonl` and emits the **identical** summary contract:
```python
# result dict shape — copy eval_runner.main:135-139 EXACTLY (the locked {total,passed,failed,failures}):
{
    "total":  len(results),
    "passed": len(passed),
    "failed": len(failed),
    "failures": [{"question": r.question, "failures": r.failures} for r in failed],
}
```
- Use a `@dataclass` per-answer result like `eval_runner.DocResult` (`eval_runner.py:56-63`: `passed: bool`, `failures: list[str]`).
- Loop with a deterministic sorted iteration like `eval_runner.run` (`eval_runner.py:100-115` uses `sorted(...glob)`); read `questions.jsonl` line-by-line (`json.loads` per non-blank line).
- Hard gates from CONTEXT (uncited-claim 0% / resolution 100% / quote-substring 100% / abstention-correctness): compute them as additional summary fields but the **overall pass** is `failed == 0`, mirroring `eval_runner.main:150` (`return 1 if failed else 0`).

---

### `_cmd_ground` + `p_ground` in `crawler/cli.py` (controller / dispatcher)

**Primary analog: `_cmd_search` (`cli.py:294-411`) and `_cmd_index` (`cli.py:245-291`).** Copy the thin-dispatcher skeleton verbatim — validate inputs, **lazy-import** the compute module, call it, map typed exceptions to `EXIT_*`, emit **exactly one** `contract.envelope`, route human text to **stderr only**.

**Handler skeleton — copy `_cmd_search:311-324`:**
```python
def _cmd_ground(args: argparse.Namespace) -> int:
    import json
    import sys
    from pathlib import Path
    from crawler import groundgate            # LAZY import (keeps `import crawler.cli` cheap)

    db = Path(args.db)
    if not db.is_file():                       # copy _cmd_search:316-324 verbatim
        msg = f"not a file: {db}"
        if args.json:
            contract.emit(contract.envelope("ground", error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT
```

**Reading the answer from stdin — NO in-repo CLI analog.** No existing verb reads stdin (verified: `grep sys.stdin crawler/*.py` finds only `AGENT_SKILL.md` consumer examples). Build it fresh, mapping a malformed parse to `INVALID_INPUT` using the same envelope/exit shape as the `EmptyQuery` catch (`_cmd_search:386-395`):
```python
    try:
        answer = json.loads(sys.stdin.read())  # the AGENT_SKILL.md idiom (json.load(sys.stdin), :143)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        if args.json:
            contract.emit(contract.envelope("ground", error=(contract.INVALID_INPUT, f"bad stdin JSON: {exc}")))
        else:
            print(f"error: bad stdin JSON: {exc}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT
```

**The verdict:"fail" → exit-nonzero rule — copy `_cmd_report:223-240` EXACTLY.** A *grounding* fail is a VERDICT, not an execution error: emit `ok:true` with `result.verdict == "fail"` and return a non-zero exit, never an `error` object. `_cmd_report` is the canonical precedent in this repo:
```python
    result = groundgate.check_answer(answer, db)   # {verdict, claims_checked, failures, ...}
    if args.json:
        contract.emit(contract.envelope("ground", result=result))   # ok:true even on verdict:"fail"
    else:
        print(f"verdict: {result['verdict']}", file=sys.stderr)
    return 0 if result["verdict"] == "pass" else 1   # mirror _cmd_report:240 (overall_pass -> 0 else 1)
```
- This matches the contract rule already documented at `contract.py:23-26` and `CONTRACT.md:71-83,237` ("a verdict of fail … is NOT an execution error: ok:true … exit code 1").

**Eval mode** (run over `questions.jsonl`): add a `--eval`/`--questions <path>` flag to `p_ground` (or a sibling `_cmd_eval`). On any ungrounded answer, exit non-zero — exactly `eval_runner.main:150` (`return 1 if failed else 0`). Emit the `{total,passed,failed,failures}` payload inside a `ground` envelope (or print it like `eval_runner.main:134-139` in non-json mode).

**Subparser — copy `p_search` (`cli.py:482-494`) and register it (`subparsers` metavar `cli.py:428`):**
```python
    p_ground = subparsers.add_parser(
        "ground", help="Fail-closed grounding gate: check a structured answer's claims[] cite real chunks.")
    p_ground.add_argument("--db", default="corpus/index.db",
                          help="SQLite index path (default: corpus/index.db)")
    p_ground.add_argument("--questions", default=None,
                          help="run as eval harness over a questions.jsonl reference set")
    p_ground.add_argument("--render", action="store_true",
                          help="on pass, render the cited answer to personal/output/ (render-then-scan, RPT-03)")
    p_ground.set_defaults(func=_cmd_ground)
```
- **Update the `subparsers` metavar** at `cli.py:428` to include `ground` (additive — same edit Phase 24 made to add `search`).
- The global `--json` flag is already owned by the dispatcher (`cli.py:424-426`); `main`'s catch-all (`cli.py:511-521`) already wraps any unexpected escape into an `internal_error`/exit-4 envelope — you get that for free.

---

### `crawler/CONTRACT.md` + `crawler/contract.py` docstring (additive docs)

**Analog: the `### search` section (`CONTRACT.md:166-216`) — the most recent additive command doc; mirror its structure.** It documents (a) what the verb does, (b) a `result` field table for each mode, (c) the fail-closed/verdict rule, (d) which shared error/exit codes apply. Write a `### ground` section the same way:
- A `result` table: `verdict` (`"pass"|"fail"`), `claims_checked` (int), `failures` (array of `{claim_id, reason}`), and — in eval mode — `{total, passed, failed, failures}`.
- State the **verdict-fail rule** by analogy to `report` (`CONTRACT.md:71-83,207-210,237`): grounding `verdict:"fail"` is `ok:true` + exit `1`, NOT an `error`.
- State the **honesty boundary** verbatim (resolvability + verbatim-quote, NOT entailment).
- **`contract.py` docstring**: add `ground` to the command enumeration at `contract.py:13` and `contract.py:69` (one-word additive edit each — exactly the Phase-24 `search` precedent).

> **DECISION FLAG for the planner — the publish-unsafe exit code (CONTEXT criteria #3 says "ok:false and exit 4").** The current taxonomy reserves **exit 4 = `internal_error`** (`contract.py:60`, `CONTRACT.md:240`). A publish-unsafe refusal is a *deliberate* fail-closed, not an unexpected crash, so reusing `internal_error`/4 is semantically wrong. Two clean options — pick one and document it additively:
> (a) **New error type + exit** `publish_unsafe` (e.g. `EXIT_PUBLISH_UNSAFE = 5`, `PUBLISH_UNSAFE = "publish_unsafe"`) added to `contract.py:43-60` — additive, keeps exit-4 meaning `internal_error`; OR
> (b) honor CONTEXT literally and emit `ok:false` + `error.type:"publish_unsafe"` mapped to the existing `EXIT_INTERNAL_ERROR=4` constant, documenting that 4 now also covers a publish-safety refusal.
> Either way the constant lives in `contract.py` (never a bare literal) — mirror `EXIT_INVALID_INPUT`/`EXIT_MISSING_DEPENDENCY` (`contract.py:57-60`). Flag, do not silently choose.

---

### `crawler/tests/fixtures/questions.jsonl` (tracked, PII-free fixture)

**Placement analog: tracked fixtures live under `crawler/tests/fixtures/`** (`raw_pages.json`, `urls.json`) and `crawler/tests/golden/` — these are the repo's established *tracked* test-data homes. Put `questions.jsonl` there.
- **It MUST be tracked + PII-free.** This is why it CANNOT live under `personal/` (entirely git-ignored, `.gitignore:3`) and CANNOT live under a `CORPORA_PREFIXES` path (`trial/`, `personal/`, `corpus_new/` — `check_publish_safe.py:47`, flagged by `scan_path_name`). `crawler/tests/fixtures/` is neither ignored nor a corpora-prefix → safe to track.
- **Record shape analog: the `eval_runner` eval record (`eval_runner.py:6-22`).** One JSON object per line; reuse the `must_contain`/`must_not_contain` idea for the adversarial `must_abstain` field the CONTEXT names:
```jsonl
{"id": "q-pcc-countries", "question": "Which countries need a police certificate?", "must_abstain": false}
{"id": "q-adversarial-future", "question": "What will the 2031 income cutoff be?", "must_abstain": true}
```
- The eval harness reads it line-by-line (one `json.loads` per non-blank line) — same per-record loop as `eval_runner.run` (`eval_runner.py:100-115`).

---

### `crawler/tests/test_groundgate.py` (tests)

**Analog: `crawler/tests/test_searchindex.py` — copy its harness wholesale.** Stdlib `unittest` ONLY (no pytest fixtures, no network — `test_searchindex.py:1-10`), tempdir-only writes, real-DB-from-synthetic-corpus.

- **Base case / synthetic corpus + tempdir DB — copy `_IndexCase` (`test_searchindex.py:357-370`) + `_make_index_corpus`/`_doc_text` (`273-354`).** Build the index once in `setUp` via `searchindex.build_index(self.root, self.db)` exactly like `TestSearchCli.setUp` (`865-869`). The DB lives in the tempdir, **NEVER** under real `corpus/` (`test_searchindex.py:363`).
- **Driving the CLI + capturing streams — copy the `_run` helper (`test_searchindex.py:871-880`):**
```python
def _run(self, argv, stdin_text=""):
    import contextlib, io, sys
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        old = sys.stdin
        sys.stdin = io.StringIO(stdin_text)      # NEW: ground reads stdin (no analog in _run)
        try:
            rc = cli.main(argv)
        finally:
            sys.stdin = old
    return rc, out.getvalue(), err.getvalue()
```
  (The base `_run` redirects stdout/stderr; you ADD a `sys.stdin` swap because `ground` reads stdin — the one delta from the analog.)
- **Envelope-shape / stdout-purity / exit-code asserts — copy `TestSearchCli` (`test_searchindex.py:892-967`):**
  - one ok envelope: `out.count("\n") == 1`, `obj["ok"] is True`, `obj["command"] == "ground"`, `obj["schema_version"] == "1.0"` (`892-907`).
  - stdout purity: `json.loads(out)` must not raise; `self.assertNotIn("{", err)` — no JSON on stderr (`929-936`).
  - invalid input → exit 2: use the `contract_exit_invalid_input()` helper (`612-615`) for the magic number.
  - **fail-closed grounding verdict**: an answer with an unresolvable/uncited/quote-mismatch claim → `ok:true`, `result["verdict"] == "fail"`, `rc == 1` (the NEW assertion — pattern from `_cmd_report`, asserted like the `--cite` miss test `959-967` which checks fail-closed `ok:true`/exit `0`... here it's exit `1`).
- **Real-corpus integration guard — copy `TestRealCorpus` (`test_searchindex.py:986-1027`):** `@unittest.skipUnless(Path("corpus").is_dir(), "...")` and build into a `tempfile.TemporaryDirectory()` DB (never `corpus/index.db`). A round-trip "search → resolve → ground a constructed answer over the real 742-doc index" is the GND-01 end-to-end proof (the existing `test_real_corpus_search_resolve_round_trip` at `1004-1027` already calls this "the citation handshake the Phase-25 grounding gate (GND-01) depends on").

---

## Shared Patterns

### Citation resolution (GND-01 core) — `searchindex.resolve()`
**Source:** `crawler/searchindex.py:502-562`
**Apply to:** `groundgate.check_answer` (one call per claim citation).
The SINGLE resolver. Already read-only (`file:<db>?mode=ro`), already fail-closed on miss (`return None`, `:540-541`) AND on sha-drift/stale rows (`:548-549`), already returns the **verbatim** quotable `text` (not a snippet). Do not re-open the DB or re-implement; just call it.
```python
hit = searchindex.resolve(db, chunk_id)   # None => fail closed; hit["text"] => verbatim span
```

### Envelope + exit-code taxonomy — `contract.py`
**Source:** `crawler/contract.py` — `envelope()` (`63-87`), `emit()` (`90-96`), `SCHEMA_VERSION="1.0"` (`41`), `INVALID_INPUT`/`MISSING_DEPENDENCY`/`INTERNAL_ERROR` (`45-53`), `EXIT_INVALID_INPUT=2`/`EXIT_MISSING_DEPENDENCY=3`/`EXIT_INTERNAL_ERROR=4` (`57-60`)
**Apply to:** every `_cmd_ground` exit path.
- Exactly one `contract.emit(contract.envelope("ground", ...))` to stdout in `--json` mode; all human text to stderr (`cli.py` P11 convention, e.g. `_cmd_search:409-410`).
- `verdict:"fail"` is `ok:true` + exit `1` (NOT an `error`) — `_cmd_report:223-240`.
- malformed stdin / bad `--db` → `INVALID_INPUT` + exit `2` — `_cmd_search:316-324,386-395`.
- See the DECISION FLAG above re: the publish-unsafe exit code (4 vs a new 5).

### Render-then-gate publish safety (RPT-03 / criteria #3) — `check_publish_safe.scan_text`
**Source:** `scripts/check_publish_safe.py` — `scan_text(path, text)` (`115-132`), `exit_code(violations)` (`144-146`), `CORPORA_PREFIXES` (`47`)
**Apply to:** the `--render` path of `_cmd_ground` — scan the rendered output text BEFORE writing it to `personal/output/`.
```python
import sys
sys.path.insert(0, "scripts")              # check_publish_safe is NOT a package (see INTEGRATION NOTE)
import check_publish_safe as cps
violations = cps.scan_text("personal/output/answer.md", rendered_text)
if violations:                              # PII/secret/abs-path hit -> refuse, exit (see DECISION FLAG)
    # emit ok:false envelope, write NOTHING, return the publish-unsafe exit code
    ...
```
- **No existing pre-write caller exists.** `check_publish_safe.main` (`209-247`) scans the *already-tracked* git tree; there is no in-repo example of scanning a string *before* writing it. This render-then-scan-then-write ordering is NEW — but `scan_text` is a pure, importable function built for exactly this (its tests at `scripts/tests/test_check_publish_safe.py:26,33` call it directly on strings).
- **Coverage caveat:** `scan_text` detects **ABS_PATH** (`check_publish_safe.py:54-63`) + **SECRET** (`65-84`) categories — not a dedicated PII regex. It is the right *secret/abs-path* gate; if "PII" means more than secrets+abs-paths, flag that the categories are limited to these two. `scan_text`'s `is_excluded` (`104-112`) does NOT exclude `personal/` paths, so scanning a `personal/output/...` path works as intended.
- **INTEGRATION NOTE (important):** `scripts/` is **not a Python package** (no `scripts/__init__.py`; `scripts/check_publish_safe.py` imports as a top-level module). The gate, living in `crawler/`, therefore cannot `from crawler import check_publish_safe`. Mirror the test's shim — `sys.path.insert(0, <scripts dir>); import check_publish_safe as cps` — exactly as `scripts/tests/test_check_publish_safe.py:15-20` does. The planner should decide whether to (a) shim sys.path, or (b) propose moving/exposing `scan_text` into an importable location; either is acceptable but must be explicit (read-only constraint: do NOT edit `check_publish_safe.py` as part of pattern mapping).

### Whitespace/case normalization (quote-substring + abstention checks) — `eval_runner._norm`
**Source:** `crawler/eval_runner.py:52-53` (`_norm`), used as `_norm(needle) in body` at `82`
**Apply to:** the verbatim-`quote` substring check in `groundgate`.
```python
def _norm(s): return re.sub(r"\s+", " ", s).strip().lower()   # copy verbatim
```

### Eval summary contract — `eval_runner` `{total,passed,failed,failures}`
**Source:** `crawler/eval_runner.py` — `DocResult` (`56-63`), `run` (`100-115`), `main` JSON shape (`134-139`), pass/fail exit (`150`)
**Apply to:** `groundgate`'s eval mode over `questions.jsonl`.
Use the identical four-key summary; overall exit is `1 if failed else 0`.

---

## No Analog Found

| Surface | Role | Data Flow | Reason / Guidance |
|---------|------|-----------|-------------------|
| Reading a JSON **answer object from stdin** in `_cmd_ground` | controller | request-response | No existing CLI verb reads stdin (all take args/paths). Build fresh with `json.loads(sys.stdin.read())`; model the **error envelope** on the `EmptyQuery`→`INVALID_INPUT` catch (`_cmd_search:386-395`); consumer-side idiom is `AGENT_SKILL.md:143` (`json.load(sys.stdin)`). |
| The **quote-substring verbatim check** (claim `quote` ⊂ resolved chunk) | utility (pure) | transform | No FTS/substring-verify analog in repo. Build a pure helper (shape = `searchindex.chunk_sha`, `:128-135`) using the copied `eval_runner._norm`. |
| **Render-then-scan-before-write** ordering | side-effect / file-I/O | file-I/O | `scan_text` exists and is importable, but no in-repo caller scans a string *before* writing. New composition; see Shared Patterns (RPT-03). |
| Publish-unsafe **exit code** | config | n/a | CONTEXT says exit 4, which currently means `internal_error`. New code (e.g. 5/`publish_unsafe`) or documented reuse needed — see DECISION FLAG. |

---

## Metadata

**Analog search scope:** `crawler/` (searchindex, cli, contract, eval_runner, completeness, dupaudit), `crawler/tests/`, `scripts/`, `crawler/CONTRACT.md`, `crawler/AGENT_SKILL.md`, `.planning/research/v3.0/RETRIEVAL.md`, `.gitignore`, `pyproject.toml`
**Files scanned:** ~16 (6 read in depth: `searchindex.py`, `cli.py`, `contract.py`, `eval_runner.py`, `check_publish_safe.py`, `test_searchindex.py`)
**Key cross-cutting facts confirmed:** bare `python` broken → use `.venv/bin/python`; `scripts/` is not a package (sys.path shim needed for `scan_text`); `personal/` fully git-ignored so `questions.jsonl` must live under `crawler/tests/fixtures/`; exit-4 collision (`internal_error` vs publish-unsafe) needs a planner decision.
**Pattern extraction date:** 2026-06-21
