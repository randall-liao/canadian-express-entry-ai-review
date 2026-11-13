# Phase 25: Grounding Gate + Eval Harness - Research

**Researched:** 2026-06-21
**Domain:** Deterministic, fail-closed grounding gate (CLI verb) over structured agent answers + eval harness — pure-stdlib Python, additive to a frozen JSON-envelope contract
**Confidence:** HIGH (entirely codebase-grounded; reuses shipped `searchindex.resolve`, `contract`, `check_publish_safe.scan_text`, `eval_runner`, and the `dupaudit`/`dupclean` RPT-03 prior art)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

All implementation choices are at the agent's discretion — discuss phase was skipped per user setting. Use the ROADMAP phase goal, success criteria, codebase conventions, and the existing `crawler/` primitives to guide decisions.

Locked anchors from PROJECT/STATE decisions to honor:
- **Reuse existing `crawler/` primitives, NO new deps:** `searchindex.resolve()` (Phase 24, fail-closed sha-drift guard) is the single citation resolver the gate (GND-01) calls; `contract.envelope`/exit codes; `check_publish_safe.scan_text` (RPT-03) + `CORPORA_PREFIXES` (already includes `personal/`); `eval_runner` `{total,passed,failed,failures}` shape.
- **Acceptance bar (locked, v3.0):** grounding-by-construction, fail-closed. The gate guarantees resolvability + verbatim-quote, NOT semantic entailment (deferred VAL-01/02 — needs model/NLI, violates no-vectors/no-cloud constraint).
- **SQLite FTS5 (stdlib) only;** PII confined to git-ignored `personal/`, never the repo or corpus DB.
- **The gate is the contract Phases 26 (checklist) and 27 (document agents) emit into** — design its stdin JSON schema + JSON-envelope output to be the stable producer-facing API.

### the agent's Discretion

All implementation choices (module layout, exact stdin-schema validation rules, eval-record field names, output filename scheme, render format) are at the agent's discretion, guided by codebase conventions and the success criteria.

### Deferred Ideas (OUT OF SCOPE)

- **Semantic entailment / NLI faithfulness checking (VAL-01/VAL-02)** — needs a model; out of scope for v3.0 per the locked acceptance bar. The gate stops at resolvability + verbatim-quote.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GND-01 | A citation resolver verifies every citation ID emitted in an answer resolves to a real corpus chunk; unresolvable or missing citations fail closed. | The resolver already exists and is shipped: `crawler/searchindex.resolve(db, chunk_id) -> dict | None` (Phase 24). It returns the verbatim chunk dict on a hit, `None` on a miss **or** a sha-drift/stale row (fail-closed). The gate calls it **in-process** per citation — it does NOT re-implement resolution and does NOT shell out to `search --cite`. (`crawler/searchindex.py:502-562`, verified.) |
| GND-02 | Grounding-by-construction gate — every factual claim must carry ≥1 resolving citation; any uncited factual claim fails the entire output (fail-closed). Doubles as the automated eval harness. | New `ground` CLI verb (`crawler/cli.py` thin `_cmd_*` dispatcher → new `crawler/grounding.py` compute module). Iterates `claims[]` only; ANY uncited / unresolvable / quote-mismatch claim ⇒ `verdict:"fail"`, render nothing, exit 1. Same gate over a tracked `questions.jsonl` reference set emits `eval_runner`-style `{total,passed,failed,failures}`. Render-on-pass goes through `check_publish_safe.scan_text` (RPT-03) before write to `personal/output/`. |
</phase_requirements>

## Summary

Phase 25 adds a **new `ground` CLI verb** backed by a **new pure-stdlib compute module** (recommended `crawler/grounding.py`) and a **tracked, PII-free eval reference set** (recommended `crawler/eval/questions.jsonl`). Every primitive the gate needs already ships and is GREEN-tested: the **citation resolver** is `searchindex.resolve()` (Phase 24, fail-closed with a sha-drift guard), the **envelope + exit codes** are `crawler/contract.py`, the **render-then-gate share-safety scan** is `check_publish_safe.scan_text` (already wired exactly this way in `dupaudit.py`/`dupclean.py` for RPT-03), the **whitespace/case normalizer** for the quote-substring check is `eval_runner._norm`, and the **result shape** for the eval mode is `eval_runner`'s `{total,passed,failed,failures}`. This phase is therefore **assembly of shipped parts under a fail-closed contract**, not new infrastructure — and it adds **zero new dependencies** (the locked constraint).

Two distinct fail-closed outcomes map to two distinct exit codes, both verified against shipped prior art: a **grounding failure** (an uncited / unresolvable / quote-mismatch claim) is an *expected verdict* — `ok:true`, `result.verdict:"fail"`, **exit 1**, render nothing — exactly mirroring how `report`/`dupclean` treat a failing verdict (`crawler/dupclean.py:597-599`). A **publish-safety hit** in the rendered answer is a *should-never-happen* refusal — `ok:false`, `error.type:"internal_error"`, **exit 4** — identical to `dupaudit.py:614-629` / `dupclean.py:575-589`. The contract stays **schema_version `1.0`, five keys, exit-codes unchanged** — the only changes are additive: one new `command` value (`ground`) and additive CONTRACT.md docs.

The honesty boundary must be documented explicitly: the gate proves **resolvability + verbatim-quote**, NOT that the cited chunk *semantically entails* the paraphrased claim. True entailment needs NLI/a model (VAL-01/02), which violates the no-vectors/no-cloud constraint, so it is deferred. The quote-substring check is the cheap deterministic faithfulness floor; the claim and its quote should render side-by-side for human review.

**Primary recommendation:** Build `crawler/grounding.py` (compute) + a thin `_cmd_ground` dispatcher in `cli.py` that reads one answer JSON from stdin, iterates `claims[]` only (never `prose`/`basis`/`abstentions`), calls `searchindex.resolve()` per citation, runs `eval_runner._norm(quote) in _norm(chunk["text"])`, fails closed to `verdict:"fail"`/exit 1 on any miss, and on a full pass renders to `personal/output/` only after `check_publish_safe.scan_text` clears it (else `ok:false`/exit 4). The eval mode (`--eval <questions.jsonl>`) runs the same per-claim gate over each stored answer line and aggregates the `eval_runner` shape, exiting 1 if any answer is ungrounded.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Read + validate structured answer JSON (stdin) | CLI dispatcher (`cli._cmd_ground`) | — | Mirrors `_cmd_search`/`_cmd_index`: validate inputs, map errors to envelope, no compute in the handler. |
| Per-claim grounding (cited? resolves? quote-substring?) | Compute module (`crawler/grounding.py`) | `searchindex.resolve` (resolution), `eval_runner._norm` (normalization) | The fail-closed determinism lives in one pure module, unit-testable without the CLI; resolution + normalization are reused, not re-implemented. |
| Citation resolution to a real chunk (GND-01) | `crawler/searchindex.resolve` (Phase 24, shipped) | SQLite `chunks` table (read-only) | Single source of truth for "is this citation real"; already carries the sha-drift/stale fail-closed guard. |
| Render answer markdown (claim + quote side-by-side) | Compute module (`grounding.py`) | — | Render is a pure string op; the share-safety scan must run over the exact rendered bytes. |
| Share-safety scan of rendered output (RPT-03) | `check_publish_safe.scan_text` (shipped) | — | Reused verbatim — abs-path/secret detection over the rendered string before any write. |
| Write rendered answer | Filesystem → git-ignored `personal/output/` only | — | PII boundary; `personal/` is already in `.gitignore` and in `CORPORA_PREFIXES`. |
| Eval aggregation `{total,passed,failed,failures}` | Compute module (`grounding.py`) | `eval_runner` shape (reused) | The eval harness IS the gate over a fixture set — no separate machinery; mirror the existing result shape + exit-1-on-any-fail. |
| Envelope build + emit + exit codes | `crawler/contract.py` (shipped) | — | One five-key envelope per invocation; reuse `INVALID_INPUT`, `INTERNAL_ERROR`, `EXIT_INVALID_INPUT`, `EXIT_INTERNAL_ERROR`. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `json` | 3.10+ | Parse the stdin answer JSON; build/emit the envelope | Pure stdlib; the whole contract is "one `json.dumps` object on stdout" (`contract.emit`). [VERIFIED: crawler/contract.py] |
| Python stdlib `sys` | 3.10+ | Read `sys.stdin` (the answer), route human text to stderr | The stdout=JSON / stderr=human invariant is contract law. [VERIFIED: crawler/CONTRACT.md] |
| Python stdlib `re` | 3.10+ | Whitespace-collapse normalization for the quote-substring check | `eval_runner._norm = re.sub(r"\s+"," ",s).strip().lower()`. [VERIFIED: crawler/eval_runner.py:52-53] |
| Python stdlib `argparse` | 3.10+ | New `ground` subparser in `build_parser()` | Mirrors the six existing subparsers. [VERIFIED: crawler/cli.py:414-496] |
| Python stdlib `pathlib`, `sqlite3` | 3.10+ | `--db` path handling; resolution (via `searchindex`) | `sqlite3` is reached only through `searchindex.resolve` (lazy import in the handler). [VERIFIED: crawler/cli.py:311-313] |

### Supporting (in-repo modules — reuse, do not re-implement)

| Module / function | Purpose | When to Use |
|---------|---------|-------------|
| `crawler.searchindex.resolve(db, chunk_id)` | GND-01 citation resolver → `{chunk_id, relpath, source_url, title, section, crawl_date, text}` or `None` | Call once per citation id; a `None` is a fail-closed miss (unknown id OR stale sha-drift row). [VERIFIED: crawler/searchindex.py:502-562] |
| `crawler.contract.envelope/emit` + `SCHEMA_VERSION`, `INVALID_INPUT`, `INTERNAL_ERROR`, `EXIT_INVALID_INPUT (2)`, `EXIT_INTERNAL_ERROR (4)` | The five-key envelope + error types + exit codes | Build exactly one envelope; reuse the existing error types — do NOT invent new ones. [VERIFIED: crawler/contract.py] |
| `scripts/check_publish_safe.py` `scan_text(path, text)` | RPT-03 share-safety scan over the rendered answer bytes | After render, before write; non-empty result ⇒ refuse (`internal_error`, exit 4). [VERIFIED: scripts/check_publish_safe.py:115-132] |
| `crawler.eval_runner._norm(s)` and the `{total,passed,failed,failures}` JSON shape | Normalizer for the quote check; result shape for `--eval` mode | Reuse `_norm` for substring matching; mirror the result shape + exit-1-on-fail. [VERIFIED: crawler/eval_runner.py:52-53, 134-150] |
| `crawler/dupaudit.py:604-632` and `crawler/dupclean.py:472-599` | Canonical RPT-03 render-then-gate prior art (import-and-call pattern + exit-code mapping) | Copy the ordering and the `INTERNAL_ERROR`/exit-4 mapping line-for-line. [VERIFIED: read in full] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-process `searchindex.resolve()` | Shell out to `corpus-crawler --json search --cite <id>` per citation | Subprocess-per-citation is slow and fragile; both live in the same package — direct call is the CONTEXT-locked choice ("`searchindex.resolve()` is the single citation resolver the gate calls"). [VERIFIED: 25-CONTEXT.md] |
| Structured `claims[]` declared by the producer | Free-text answer + NLP claim extraction at gate time | NLP extraction makes fail-closed *probabilistic* (missed claims ship ungrounded; filler flagged); needs a model → breaks pure-stdlib + no-vectors. The structured contract makes fail-closed absolute. [CITED: .planning/research/v3.0/GROUNDING.md §1] |
| Reuse exit 4 (`internal_error`) for the publish-safety refusal | Add a new error type / new exit code | The shipped RPT-03 prior art already maps a publish-safety refusal to `INTERNAL_ERROR` + exit 4; reusing it keeps the exit-code taxonomy **unchanged** (additive-only constraint satisfied). [VERIFIED: dupaudit.py:622-629] |

**Installation:** None. This phase adds **zero** runtime dependencies. The only declared runtime dep stays `pyyaml` (`pyproject.toml`), and the gate does not even need YAML. Run/test via `poetry run` or `.venv/bin/python` (see Environment Availability — bare `python` is broken).

## Package Legitimacy Audit

**Not applicable — this phase installs no external packages (stdlib-only, locked "NO new deps" constraint).** All building blocks are either Python standard library (`json`, `sys`, `re`, `argparse`, `pathlib`, `sqlite3`) or already-shipped in-repo modules. No `pip`/registry interaction occurs. The Package Legitimacy Gate is satisfied vacuously.

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
 producer (Phase 26/27 agent, OR a tracked fixture line)
        │  one structured answer JSON on stdin:
        │  {question, claims:[{id,text,citations[],quote}], basis[], abstentions[], prose}
        ▼
  corpus-crawler --json ground            (cli._cmd_ground — thin dispatcher)
        │
   ┌────┴───────────────────────────────────────────────────────┐
   │ 1. PARSE + VALIDATE shape (json.load(sys.stdin))            │
   │    malformed JSON / missing `question`|`claims` / claims    │
   │    not a list / claim missing id|text|citations|quote       │
   │      → ok:false, invalid_input, EXIT 2                      │
   └────┬───────────────────────────────────────────────────────┘
        │ iterate claims[] ONLY  (prose / basis / abstentions are NEVER citation-checked)
        ▼
   ┌────────────────────────────────────────────────────────────┐
   │ 2. PER-CLAIM GROUNDING (fail-closed, deterministic)         │
   │    for each claim c:                                        │        read-only
   │      a. len(c.citations) >= 1?      else  "uncited"         │        ┌───────────────┐
   │      b. resolve(db, id) per cite ───────────────────────────┼───────▶│ corpus/index.db│
   │         no citation resolves?       then  "unresolvable"    │        │  chunks table  │
   │      c. _norm(c.quote) in _norm(resolved.text)?             │        │  (GND-01)      │
   │         for the SAME resolving cite, else "quote_not_in_chunk"       └───────────────┘
   └────┬───────────────────────────────────────────┬───────────┘
   any violation                              all claims grounded
        ▼                                            ▼
 ┌───────────────────────────────┐      ┌────────────────────────────────────┐
 │ verdict:"fail" — render NOTHING│      │ 3. RENDER answer markdown          │
 │ ok:true, result.violations[]   │      │    (claim + quote side-by-side +    │
 │ EXIT 1                          │      │     citation + crawl_date)         │
 └───────────────────────────────┘      └───────────────┬────────────────────┘
                                                          ▼
                                         ┌────────────────────────────────────┐
                                         │ 4. RPT-03 render-then-gate          │
                                         │    check_publish_safe.scan_text(...) │
                                         │    abs-path / secret hit?            │
                                         │      → ok:false, internal_error,     │
                                         │        EXIT 4 (write nothing)        │
                                         └───────────────┬────────────────────┘
                                                   clean │
                                                         ▼
                                         ┌────────────────────────────────────┐
                                         │ 5. WRITE → personal/output/<name>.md │
                                         │    (git-ignored) — ok:true,          │
                                         │    verdict:"pass", EXIT 0            │
                                         └────────────────────────────────────┘

 EVAL MODE:  corpus-crawler --json ground --eval crawler/eval/questions.jsonl
   run steps 1–2 over EVERY stored answer line → aggregate
   {total, passed, failed, failures}; EXIT 1 if any line ungrounded.
   (no per-line render/write; an `must_abstain` line must carry empty claims[].)
```

### Recommended Project Structure

```
crawler/
├── grounding.py          # NEW — pure-stdlib gate compute (parse, per-claim grounding, render, eval aggregate)
├── cli.py                # EDIT (additive) — add `ground` subparser + thin `_cmd_ground` handler
├── searchindex.py        # UNCHANGED — resolve() is the GND-01 resolver (read-only)
├── contract.py           # UNCHANGED — reuse envelope/emit + INVALID_INPUT/INTERNAL_ERROR + exit codes
├── eval_runner.py        # UNCHANGED — reuse _norm + {total,passed,failed,failures} shape (import or mirror)
├── CONTRACT.md           # EDIT (additive) — document the `ground` command + its result/exit mapping
├── eval/
│   └── questions.jsonl   # NEW — tracked, PII-free reference answers (incl. must_abstain lines)
└── tests/
    └── test_grounding.py # NEW — unittest-style (NO pytest fixtures), synthetic tiny index + stdin stubbing

scripts/check_publish_safe.py   # UNCHANGED — scan_text reused; `personal/` ALREADY in CORPORA_PREFIXES
personal/output/                # runtime-only, git-ignored (created on demand by the gate)
```

### Pattern 1: Thin CLI dispatcher → compute module (the house style)

**What:** `_cmd_ground(args)` validates `--db`, lazy-imports the compute module, dispatches, maps known errors to the envelope, and keeps stdout pure JSON. ALL grounding logic lives in `grounding.py`.
**When to use:** Always — every existing verb (`_cmd_index`, `_cmd_search`) follows this; the plan-checker verifies tier correctness against it.
**Example:**
```python
# Source: crawler/cli.py:294-411 (mirror this exactly for `ground`)
def _cmd_ground(args: argparse.Namespace) -> int:
    from pathlib import Path
    from crawler import grounding          # LAZY import (keeps `import crawler.cli` cheap)

    db = Path(args.db)
    if not db.is_file():
        msg = f"not a file: {db}"
        if args.json:
            contract.emit(contract.envelope("ground", error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT
    # ... eval-mode branch (args.eval) vs single-answer branch (read sys.stdin) ...
```

### Pattern 2: Per-claim grounding (the fail-closed core)

**What:** A claim passes iff **at least one** of its citations BOTH resolves AND its resolved chunk contains the normalized quote. Any claim that fails ⇒ whole-answer `verdict:"fail"`.
**When to use:** The heart of GND-02.
**Example:**
```python
# Source: synthesized from searchindex.resolve (verified) + eval_runner._norm (verified)
from crawler import searchindex
from crawler.eval_runner import _norm    # whitespace-collapse + casefold normalizer (reuse)

def check_claim(db, claim) -> list[str]:
    """Return a list of violation reasons for one claim (empty == grounded)."""
    cites = claim.get("citations") or []
    if not isinstance(cites, list) or len(cites) < 1:
        return ["uncited"]
    quote_norm = _norm(str(claim.get("quote", "")))
    resolved_any = False
    quote_ok = False
    for cid in cites:
        chunk = searchindex.resolve(db, str(cid))   # None == miss OR sha-drift (fail-closed)
        if chunk is None:
            continue
        resolved_any = True
        if quote_norm and quote_norm in _norm(chunk["text"]):
            quote_ok = True
            break
    if not resolved_any:
        return ["unresolvable"]
    if not quote_ok:
        return ["quote_not_in_chunk"]
    return []
```

### Pattern 3: RPT-03 render-then-gate (copy the order precisely)

**What:** Render the exact bytes the user would see, scan them with `scan_text`, refuse on any violation, and only then write. Scan-then-write, never write-then-scan.
**When to use:** Step 4 — before writing the passing answer to `personal/output/`.
**Example:**
```python
# Source: crawler/dupaudit.py:614-632 and crawler/dupclean.py:472-595 (verified prior art)
import sys as _sys
from pathlib import Path
_scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
if _scripts_dir not in _sys.path:
    _sys.path.insert(0, _scripts_dir)
import check_publish_safe as cps           # RPT-03 share-safety gate

violations = cps.scan_text(out_relpath, rendered_md)   # scan the rendered string
if violations:
    msg = f"refusing to write answer: {len(violations)} publish-safety violation(s)"
    contract.emit(contract.envelope("ground", error=(contract.INTERNAL_ERROR, msg)))
    return contract.EXIT_INTERNAL_ERROR    # exit 4 — identical to dupaudit/dupclean
# clean → mkdir personal/output/ ; out_path.write_text(rendered_md, encoding="utf-8")
```

### Anti-Patterns to Avoid

- **Free-text + NLP claim extraction:** makes fail-closed probabilistic and needs a model — forbidden. The producer declares `claims[]`; the gate never guesses claim boundaries. [CITED: GROUNDING.md §1]
- **Answer-level "Sources:" footer instead of per-claim citations:** a footer looks grounded but binds to nothing — partial-citation hole. Citations bind **per claim**; any empty `citations[]` fails the whole output. [CITED: GROUNDING.md §7 P2]
- **Citation-checking `prose`/`basis`/`abstentions`:** only `claims[]` is checked. Checking filler causes false failures and breaks the contract. [VERIFIED: ROADMAP SC1]
- **Re-implementing a resolver / re-opening the DB by hand:** call `searchindex.resolve()`; it already opens read-only and carries the sha-drift guard.
- **Writing the rendered answer anywhere tracked (reports/, repo root, corpus/):** output goes ONLY to git-ignored `personal/output/`. Resolve the output path and confirm it is under `personal/`.
- **Stripping markdown / "fixing" quotes before the substring check:** normalize whitespace + case ONLY (`_norm`). Stripping `**`/punctuation would silently widen the gate and let mis-quotes pass.
- **Bumping `schema_version` or renaming envelope keys:** the change is additive (one new `command` value). The 5-key envelope and exit codes 0/1/2/3/4 stay as-is.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Resolve a citation id → real chunk | A new SQLite reader / id parser | `searchindex.resolve(db, id)` | Already read-only, parameter-bound, UNIQUE-indexed, with a sha-drift/stale fail-closed guard. Re-rolling loses the tamper guard. [VERIFIED: searchindex.py:502-562] |
| Whitespace/case normalization for substring match | A bespoke regex each call | `eval_runner._norm` | One canonical normalizer already used for the same purpose in QC evals; consistency matters across the codebase. [VERIFIED: eval_runner.py:52-53] |
| JSON envelope + error types + exit codes | A new result schema | `contract.envelope/emit` + `INVALID_INPUT`/`INTERNAL_ERROR` + `EXIT_*` | The frozen producer-facing contract; agents already parse it. [VERIFIED: contract.py] |
| Render-then-scan share-safety | A new PII/secret scanner | `check_publish_safe.scan_text` (+ the `dupaudit` import pattern) | Detects abs-paths + secrets, has the `# publish-safe: allow` escape hatch, and is the project's sanctioned gate. [VERIFIED: check_publish_safe.py] |
| Eval result aggregation | A new report shape | `eval_runner`'s `{total,passed,failed,failures}` + exit-1-on-fail | Locked reuse; keeps "the bar" and "the test" identical. [VERIFIED: eval_runner.py:134-150] |
| Reading the structured answer | A custom parser/format | `json.load(sys.stdin)` (one object) | The whole interface is "one JSON object in, one envelope out" — mirrors `AGENT_SKILL.md`. [VERIFIED: AGENT_SKILL.md] |

**Key insight:** Phase 25 is *composition of shipped, tested primitives under a fail-closed contract*. The only genuinely new code is (a) the per-claim iteration/gate logic, (b) the answer render, and (c) the eval-line driver — all pure functions over already-built parts. Every "hard" part (resolution integrity, PII scanning, the envelope) is already solved.

## Runtime State Inventory

**SKIPPED — this is a greenfield, additive phase (new module + new verb + new tracked fixture), not a rename/refactor/migration.** No stored data, live-service config, OS-registered state, secret/env-var renames, or build artifacts are touched. Verified: the change adds files (`grounding.py`, `eval/questions.jsonl`, `test_grounding.py`) and additively edits `cli.py`/`CONTRACT.md`; it renames nothing and migrates no data. (`corpus/index.db` is read-only consumed via `resolve()`.)

## Common Pitfalls

### Pitfall 1: Quote-substring fails on typographic/markdown characters in the chunk
**What goes wrong:** A producer (or fixture author) retypes a quote with a straight apostrophe `'` or straight quotes `"`, but the corpus chunk stores **curly** punctuation (`'` U+2019, `"`/`"` U+201C/U+201D) and **markdown bold** (`**after**`). `_norm` collapses whitespace + lowercases but does NOT convert curly→straight, strip `**`, or NFC-normalize — so the substring check fails on a "correct" quote.
**Why it happens:** Real IRCC chunks contain curly quotes, `**bold**`, em-dashes, and non-ASCII (e.g. Korean Hangul). Verified live example from `police-certificates/when.md#003`: `"…it was issued **after** the last time you stayed there…"` and `"You **don't** need to give us…"` (curly apostrophe).
**How to avoid:** Producers MUST copy the `quote` **verbatim** from the resolved chunk's `text` (obtain it via `corpus-crawler --json search --cite <id>` → `result.chunk.text`, or from a prior `search` hit). Document this in the producer contract. The gate's strictness is intentional (verbatim-by-construction) — do NOT loosen `_norm` to paper over retyped quotes; that would weaken the grounding guarantee.
**Warning signs:** `quote_not_in_chunk` violations on claims whose quote "looks right" by eye — almost always a punctuation/markdown mismatch.

### Pitfall 2: Reusing exit 4 without a distinguishable message
**What goes wrong:** Exit 4 is `EXIT_INTERNAL_ERROR` and is ALSO the established RPT-03 publish-safety refusal code. An agent can't tell "corrupt input crashed" from "render tripped the PII scan" by exit code alone.
**Why it happens:** The contract intentionally maps both to exit 4 (the prior art does the same — `dupaudit`/`dupclean` use `INTERNAL_ERROR` for the refusal).
**How to avoid:** Make `error.message` explicit and grep-able (e.g. `"refusing to write answer: N publish-safety violation(s)"`), matching the dupaudit/dupclean wording. The contract already tells agents to **branch on `error.type` + message, not the bare exit code**. Keep `internal_error` as the type (do NOT invent a new type/code — that would break the additive-only exit-code constraint).
**Warning signs:** A test that asserts exit-4 semantics purely on the code without checking the message.

### Pitfall 3: Eval reference set is coupled to the live corpus index (and the producers don't exist yet)
**What goes wrong:** (a) `questions.jsonl` answers carry real `relpath#ordinal` citation ids + verbatim quotes that only resolve against the locally-built `corpus/index.db`; a corpus refresh that shifts chunk ordinals can break fixture citations. (b) In Phase 25 there is **no document agent** (Phase 27) to *generate* answers, so the eval can't run "question → agent → gate."
**Why it happens:** `corpus/` is git-ignored, so CI has no index; and the gate needs answers to check.
**How to avoid:** For Phase 25, make each `questions.jsonl` line a **complete stored answer object** (the gate's stdin schema) plus an `expect`/`must_abstain` marker, and run the gate over the stored answers (gate-over-fixtures, NOT agent-over-questions — that's a Phase 27 concern). Unit-test the gate **logic** against a **synthetic tiny index** built in `setUp` (mirror `TestResolve`/`_IndexCase` in `test_searchindex.py`), so tests are deterministic and need no real corpus. Make the real-corpus eval an integration check guarded by `@unittest.skipUnless(Path("corpus/index.db").is_file(), …)` (mirror `TestRealCorpus`).
**Warning signs:** Eval tests that import `corpus/index.db` directly and would fail in CI; fixture citations that break after `corpus-crawler index` re-runs.

### Pitfall 4: PII slipped into the tracked eval fixture
**What goes wrong:** `questions.jsonl` is **tracked** (so it can be the regression bar) — it is the single most tempting place to drop in the author's real Q&A, names, or case data.
**Why it happens:** Fixtures feel like "test data," but tracked == public on GitHub.
**How to avoid:** Use only synthetic/generic questions about IRCC requirements; `claims[].text` is corpus-derived (the corpus has no PII); never put names/dates/countries in the fixture. The publish-safety scanner's `CORPORA_PREFIXES` does NOT cover `crawler/eval/`, so the fixture is NOT auto-guarded by path — rely on review + the fact that `scan_text` over tracked files runs in the repo-wide check. Consider adding a test that runs `scan_text` over `questions.jsonl` content.
**Warning signs:** A fixture quote containing a person's name, a real address, an abs path, or a token-shaped string.

### Pitfall 5: Output written outside the PII boundary
**What goes wrong:** A passing answer is rendered to `reports/` or repo root (like `dupaudit` does for its shareable report), leaking the user's `basis[]`/PII into a tracked location.
**Why it happens:** The closest prior art (`dupaudit`) writes to `reports/` (a SHAREABLE location) — but Phase 25's output is PII-bearing and must go to `personal/output/` (git-ignored).
**How to avoid:** Default and confine the output to `personal/output/` (git-ignored; `personal/` is already in `.gitignore` and `CORPORA_PREFIXES`). `mkdir(parents=True, exist_ok=True)` it on demand (like `dupaudit` does for its out dir). Validate any `--out` override resolves under `personal/`. The RPT-03 `scan_text` is the backstop for abs-paths/secrets, but it does NOT detect names — the structural git-ignore is the primary PII control.
**Warning signs:** A write path that isn't under `personal/`; a `--out` flag with no containment check.

### Pitfall 6: Grounding fail emitted as `ok:false` (execution error) instead of `ok:true`/`verdict:"fail"`
**What goes wrong:** Treating an ungrounded claim as an execution error (`ok:false`, exit 2/4) conflates "the gate did its job and refused" with "the gate crashed."
**Why it happens:** Both are non-zero exits; easy to conflate.
**How to avoid:** A grounding failure is an **expected verdict** — `ok:true`, `result.verdict:"fail"`, `result.violations[...]`, **exit 1** — exactly like `report`/`dupclean` (`return 1 if verdict == "fail" else 0`). Reserve `ok:false` for malformed input (exit 2) and the publish-safety refusal (exit 4). [VERIFIED: dupclean.py:597-599, CONTRACT.md "Success vs verdict-fail vs execution error"]
**Warning signs:** `error` populated on a grounding fail; a test asserting `ok is False` for an uncited claim.

### Pitfall 7: stdin not stubbed in tests / CLI handler reads stdin in eval mode
**What goes wrong:** Tests that drive `cli.main(["--json","ground",…])` hang or read the test runner's stdin; or the handler tries to read stdin even in `--eval` mode.
**Why it happens:** The single-answer path reads `sys.stdin`; unittest must replace it.
**How to avoid:** In tests, set `sys.stdin = io.StringIO(answer_json)` (alongside the existing `redirect_stdout/redirect_stderr` `_run` helper in `test_searchindex.py:558-567`). In the handler, branch on `args.eval` BEFORE touching stdin — eval mode reads the file, never stdin.
**Warning signs:** A test that blocks; an eval-mode invocation that waits for stdin.

## Code Examples

### Adding the `ground` subparser (additive to `build_parser`)
```python
# Source: mirror crawler/cli.py:482-494 (the `search` subparser)
p_ground = subparsers.add_parser(
    "ground",
    help="Fail-closed grounding gate over a structured answer (stdin), "
         "or run the eval harness over a reference set with --eval.")
p_ground.add_argument("--db", default="corpus/index.db",
                      help="SQLite index path (default: corpus/index.db)")
p_ground.add_argument("--eval", default=None,
                      help="run the gate over a questions.jsonl reference set instead of stdin")
p_ground.add_argument("--out-dir", default="personal/output",
                      help="git-ignored output dir for a passing answer (default: personal/output)")
p_ground.set_defaults(func=_cmd_ground)
# Also: add "ground" to the subparsers metavar string (cli.py:428) and to CONTRACT.md's command enum.
```

### Whole-answer gate + verdict envelope (single-answer mode)
```python
# Source: synthesized from contract.py (verified) + dupclean.py verdict mapping (verified)
import json, sys
from crawler import contract

def run_gate(db, payload) -> dict:
    """Return {'verdict','total_claims','grounded','ungrounded','violations':[...]}"""
    claims = payload["claims"]                      # validated to be a list of dicts upstream
    violations = []
    for c in claims:
        reasons = check_claim(db, c)                # Pattern 2
        if reasons:
            violations.append({"id": c.get("id"), "reasons": reasons,
                               "citations": c.get("citations", [])})
    grounded = len(claims) - len(violations)
    return {"verdict": "fail" if violations else "pass",
            "total_claims": len(claims), "grounded": grounded,
            "ungrounded": len(violations), "violations": violations}

# on verdict == "fail": emit ok:true envelope, render NOTHING, return 1
# on verdict == "pass": render → scan_text → (clean) write to personal/output → ok:true/exit 0
#                                          → (violations) ok:false/internal_error/exit 4
```

### Eval mode — gate over a stored reference set (`eval_runner` shape)
```python
# Source: mirror crawler/eval_runner.py:134-150 result shape + exit-1-on-fail
def run_eval(db, questions_path) -> tuple[dict, int]:
    results = []
    with open(questions_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)                 # one stored answer + expect/must_abstain marker
            must_abstain = bool(rec.get("must_abstain"))
            claims = rec.get("claims") or []
            if must_abstain:
                # abstention-correctness: a must-abstain answer must carry NO claims
                ok = (len(claims) == 0)
                reasons = [] if ok else ["should_have_abstained"]
            else:
                summary = run_gate(db, rec)
                ok = (summary["verdict"] == "pass")
                reasons = [f"{v['id']}:{','.join(v['reasons'])}" for v in summary["violations"]]
            results.append((rec.get("id"), ok, reasons))
    failed = [(i, r) for (i, ok, r) in results if not ok]
    out = {"total": len(results),
           "passed": len(results) - len(failed),
           "failed": len(failed),
           "failures": [{"id": i, "reasons": r} for (i, r) in failed]}
    return out, (1 if failed else 0)               # exit 1 if any answer ungrounded
```

### Recommended `questions.jsonl` record shape (tracked, PII-free)
```jsonl
{"id":"police-01","expect":"grounded","question":"How recent must a police certificate be?","claims":[{"id":"c1","text":"For any other country, the police certificate must be issued after the last 6-month-consecutive stay since age 18.","citations":["police-certificates/when.md#003"],"quote":"the police certificate must be issued after the last time you resided there for 6 consecutive months or longer since the age of 18"}],"basis":[],"abstentions":[],"prose":""}
{"id":"adversarial-01","must_abstain":true,"question":"What is the fee for a Mars residency permit?","claims":[],"basis":[],"abstentions":[{"text":"Mars residency is not an IRCC program","reason":"not_in_corpus"}],"prose":""}
```
*(Field names `expect`/`must_abstain` are the agent's discretion — no locked schema. The grounded line's citation id + quote MUST be a real `relpath#ordinal` + verbatim span from the live index.)*

## State of the Art

| Old Approach (pre-ship guess in milestone GROUNDING.md) | Current Approach (shipped Phase 23/24 reality) | When Changed | Impact |
|--------------------------------------------------------|-----------------------------------------------|--------------|--------|
| Resolver invoked as `search --cite <id>` (subprocess) | In-process `searchindex.resolve(db, id)` | Phase 24 shipped | Gate calls the function directly — faster, no subprocess; CONTEXT-locked. |
| Citation ids look like `ircc-police-certs__who__a1b2c3` | Ids are `relpath#ordinal` (e.g. `police-certificates/when.md#003`) | Phase 23 shipped | Fixtures + producer examples must use `relpath#ordinal`. [VERIFIED: CONTRACT.md `search`] |
| `search` returns `result.results[]` / `--top-k` | Returns `result.hits[]` / `--limit` (+ `--family`) | Phase 24 shipped | Phase 27 agent skeletons in GROUNDING.md need this correction (not Phase 25's gate). |
| "add `personal/` to `CORPORA_PREFIXES`" | `personal/` is ALREADY in `CORPORA_PREFIXES` | Phase 15+ | No scanner change needed for the PII guard. [VERIFIED: check_publish_safe.py:47] |
| Normalizer described as "casefold" | `eval_runner._norm` uses `.lower()` (not `.casefold()`) | Shipped | Reuse `_norm` as-is for consistency; `.casefold()` is an optional hardening (see Open Questions). |

**Deprecated/outdated:** The forward-looking ID format, `results[]`/`--top-k`, and "add personal/" notes in `.planning/research/v3.0/GROUNDING.md` predate the Phase 23/24 ships — treat the shipped code (`searchindex.py`, `CONTRACT.md`, `check_publish_safe.py`) as authoritative where they disagree.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Phase 25's eval set stores **complete answer objects** (gate-over-fixtures), since no document agent exists until Phase 27. | Pitfall 3 / Code Examples | If the intent was agent-over-questions, the eval can't run in Phase 25 at all — but agents are a Phase 27 deliverable, so stored answers are the only self-contained option. Confirm scope with planner. |
| A2 | `questions.jsonl` record fields (`expect`, `must_abstain`) and the output filename scheme are the agent's discretion (no locked schema). | Code Examples | Low — CONTEXT marks all impl choices discretionary; only the `{total,passed,failed,failures}` result shape is locked. |
| A3 | A grounding failure maps to `ok:true`/`verdict:"fail"`/**exit 1**; publish-safety refusal to `ok:false`/`internal_error`/**exit 4**. | Pitfall 6 / Summary | Low — verified against `dupclean.py`/`dupaudit.py` prior art + CONTRACT.md + ROADMAP SC3 ("exit 4"). |
| A4 | The output filename is derived from the answer (e.g. a slug of `question` or an explicit `--name`), written under `personal/output/`. | Architecture | Low — naming is cosmetic; containment under `personal/` is the real constraint. |
| A5 | `eval_runner._norm` (`.lower()`, no Unicode NFC, no markdown strip) is the exact normalization for the quote check. | Pitfall 1 | Medium — accented/curly-punctuation quotes that differ only in Unicode form would fail; mitigation is "copy verbatim," but NFC-normalizing both sides is a low-risk hardening to consider. |
| A6 | The gate validates `claims[]` shape (list of dicts each with `id`,`text`,`citations`,`quote`) and maps shape errors to `invalid_input`/exit 2. | Architecture / Pitfall 7 | Low — mirrors `_cmd_search` input-validation discipline; exact required-key set is a design choice for the planner. |

## Open Questions (RESOLVED)

> All four were resolved by the orchestrator (autonomous, no-further-questions mode) and the decisions
> are baked verbatim into the Phase-25 plans' "Locked decisions". Recorded here for traceability.

1. **Eval driver scope: stored answers vs. agent-generated answers**
   - What we know: The gate doubles as the eval harness over `questions.jsonl`; the eval result shape is locked to `eval_runner`'s `{total,passed,failed,failures}`.
   - What's unclear: Whether Phase 25 should store full answer objects (gate-over-fixtures) or defer answer generation to Phase 27 agents.
   - Recommendation: Store full answer objects now (A1). Keep the loader generic enough that Phase 27 can later feed agent output through the same gate.
   - **— RESOLVED: store full answer objects now (gate-over-fixtures); loader stays generic so Phase 27 agent output flows through the same gate.**

2. **Output filename / `--out` containment policy**
   - What we know: Output must land in git-ignored `personal/output/`.
   - What's unclear: filename scheme and whether to expose `--out-dir` at all.
   - Recommendation: Derive a slug from `question` (or accept `--name`); if `--out-dir` is exposed, validate the resolved path is under `personal/` and refuse otherwise.
   - **— RESOLVED: default `--out-dir` to `personal/output/` with a deterministic question-derived filename; the resolved path must stay under `personal/` (refuse otherwise).**

3. **Quote-normalization hardening (Unicode NFC / curly→straight)**
   - What we know: `_norm` collapses whitespace + lowercases only; real chunks carry curly punctuation + markdown.
   - What's unclear: Whether to add `unicodedata.normalize("NFC", …)` (and/or quote folding) to reduce false `quote_not_in_chunk` failures.
   - Recommendation: Ship with `_norm` as-is (strict, verbatim-by-construction) + a clear "copy the quote verbatim" producer rule; treat NFC folding as a future hardening so the grounding guarantee isn't accidentally widened.
   - **— RESOLVED: ship strict `_norm` as-is (whitespace-collapse + lowercase only) + a hard "copy the quote verbatim from `resolve()['text']`" producer rule; NFC folding deferred as future hardening.**

4. **`questions.jsonl` location under the package vs. repo root**
   - What we know: It must be tracked + PII-free; `corpus/`, `personal/`, `trial/`, `corpus_new/` are all git-ignored and unusable.
   - Recommendation: `crawler/eval/questions.jsonl` (ships with the package, tracked). Confirm whether to exclude `crawler/eval/` from the wheel like `crawler/tests`.
   - **— RESOLVED: `crawler/eval/questions.jsonl` (tracked, PII-free, synthetic).**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python interpreter via `.venv/bin/python` / `poetry run` | All gate code + tests | ✓ | 3.10.12 | — |
| **bare `python`** | (must NOT be used) | ✗ | — | Use `.venv/bin/python` or `poetry run` — bare `python` hits a Windows pyenv-win CRLF shim (`/bin/sh^M: bad interpreter`). |
| Poetry | Run/test orchestration | ✓ | 2.2.1 | `.venv/bin/python -m pytest` |
| SQLite FTS5 (stdlib `sqlite3`) | `searchindex.resolve` (gate); FTS only for search, not the gate | ✓ | sqlite 3.37.2, FTS5 present | — (the gate's `resolve()` needs only the `chunks` table, no FTS5) |
| `corpus/index.db` (Phase 24 build) | Real-corpus eval / integration smoke | ✓ (present, 14 MB, git-ignored) | 742-doc index | Build with `corpus-crawler --json index corpus/ --db corpus/index.db`; in CI (no corpus) skip via `@unittest.skipUnless(Path("corpus/index.db").is_file(), …)` |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** bare `python` is broken — every command/test must use `.venv/bin/python` or `poetry run` (locked env constraint). Do NOT use `gsd-tools state advance-plan` (corrupts this repo's STATE.md).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `unittest` (stdlib) — driven by pytest. **NO pytest fixtures, NO crawl4ai, NO network** (house rule, `test_searchindex.py:3`). |
| Config file | none (no `[tool.pytest]` in `pyproject.toml`); test discovery is default. |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_grounding.py -q` |
| Full suite command | `.venv/bin/python -m pytest -q` (196 tests currently collected, ~3s for searchindex alone) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GND-01 | unknown / stale citation id → claim `unresolvable` (fail-closed) | unit (synthetic index) | `.venv/bin/python -m pytest crawler/tests/test_grounding.py -k unresolvable -x` | ❌ Wave 0 |
| GND-02 | uncited claim → whole-answer `verdict:"fail"`, exit 1, nothing rendered | unit | `… -k uncited_fails_closed -x` | ❌ Wave 0 |
| GND-02 | quote not a normalized substring of resolved chunk → `quote_not_in_chunk` | unit | `… -k quote_mismatch -x` | ❌ Wave 0 |
| GND-02 | all claims grounded → render to `personal/output/`, ok:true/verdict:pass/exit 0 | unit (tmp out dir) | `… -k pass_renders_to_personal -x` | ❌ Wave 0 |
| GND-02 | `prose`/`basis`/`abstentions` never citation-checked | unit | `… -k filler_not_checked -x` | ❌ Wave 0 |
| GND-02 | rendered output with abs-path/secret → ok:false/internal_error/exit 4, no write | unit | `… -k publish_unsafe_exit4 -x` | ❌ Wave 0 |
| GND-02 | `--json ground` emits exactly one 5-key envelope; human text → stderr | unit (CLI, `_run` helper) | `… -k one_envelope -x` | ❌ Wave 0 |
| GND-02 | malformed stdin / missing keys → invalid_input/exit 2 | unit | `… -k invalid_input_exit2 -x` | ❌ Wave 0 |
| GND-02 | `--eval` over a fixture set → `{total,passed,failed,failures}`, exit 1 if any fail | unit (synthetic index + tiny jsonl) | `… -k eval_runner_shape -x` | ❌ Wave 0 |
| GND-02 | adversarial `must_abstain` line with claims → eval failure (abstention-correctness) | unit | `… -k must_abstain -x` | ❌ Wave 0 |
| GND-01/02 | real-corpus end-to-end gate over `questions.jsonl` (skip if no `corpus/index.db`) | integration | `… -k real_corpus_eval` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_grounding.py -q`
- **Per wave merge:** `.venv/bin/python -m pytest -q` (full suite green; ~196+new)
- **Phase gate:** full suite green before `/gsd-verify-work`; run the real-corpus eval once with `corpus/index.db` present (RAN, not skipped).

### Wave 0 Gaps
- [ ] `crawler/tests/test_grounding.py` — covers GND-01 + GND-02 (use a synthetic tiny index built in `setUp` via `searchindex.build_index`, mirroring `_IndexCase`/`TestResolve`; stub `sys.stdin` with `io.StringIO`; mirror the `_run` capture helper from `test_searchindex.py:558-567`).
- [ ] `crawler/eval/questions.jsonl` — a tracked, PII-free reference set (a couple grounded lines + ≥1 `must_abstain` line) whose grounded citations resolve against the real index for the integration test.
- [ ] CONTRACT.md additive section for the `ground` command (result fields + exit-code mapping) — covered by an existing-style doc/contract assertion if the suite has one.
- [ ] No framework install needed (unittest is stdlib; pytest already present).

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: "high"`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface (local CLI). |
| V3 Session Management | no | No sessions. |
| V4 Access Control | no | Local single-user CLI; no multi-tenant boundary. |
| V5 Input Validation | **yes** | The stdin answer JSON and `questions.jsonl` are semi-trusted local input. Parse with `json.load` only; validate shape (claims is a list; each claim has `id`/`text`/`citations`/`quote`); fail closed to `invalid_input`/exit 2 on any deviation. Citation ids are passed to `searchindex.resolve`, which binds them **positionally** (never f-string, no `MATCH`) — no SQL/FTS injection surface. [VERIFIED: searchindex.py:502-536] |
| V6 Cryptography | no (consumed, not implemented) | The integrity fingerprint is the shipped `chunk_sha` (sha1 staleness guard) inside `resolve()`; the gate adds no crypto. |
| V7 Errors & Logging | **yes** | `--json` mode must keep stdout = exactly one envelope; tracebacks/human text → stderr only (the `cli.main` catch-all already enforces this). Never leak abs paths/secrets into the rendered answer — RPT-03 `scan_text` is the backstop (exit 4). |
| V12 Files & Resources | **yes** | Output is confined to git-ignored `personal/output/`; never write to corpus/, reports/, or repo root. `resolve()` opens the DB strictly read-only (`mode=ro`) — the gate cannot mutate the index. [VERIFIED: searchindex.py:529] |
| V14 Config | **yes (privacy)** | PII boundary: tracked `questions.jsonl` must be synthetic/PII-free; rendered PII-bearing answers stay under `personal/` (git-ignored, in `CORPORA_PREFIXES`). |

### Known Threat Patterns for {pure-stdlib local CLI over an SQLite index}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Hallucinated/fabricated citation id presented as real | Spoofing | `searchindex.resolve` checks every id against the real index; unknown ⇒ `None` ⇒ `unresolvable` ⇒ fail-closed (GND-01). |
| Decorative citation that resolves but doesn't contain the claim's quote | Tampering / Repudiation | Hard verbatim-quote substring check (`_norm(quote) in _norm(chunk.text)`) — the deterministic faithfulness floor. |
| Stale/tampered chunk row reused as a citation | Tampering | `resolve()` recomputes `chunk_sha` over stored text and returns `None` on drift (treated as a miss). [VERIFIED: searchindex.py:548-549] |
| Malicious citation id crafted to break the query | Tampering (injection) | Positional-bound `WHERE chunk_id = ?` (no f-string, no `MATCH`) — no injection surface. [VERIFIED] |
| PII / secret / abs-path leaked into a shareable rendered answer | Information disclosure | RPT-03 render-then-gate: `scan_text` over rendered bytes BEFORE write; any hit ⇒ `ok:false`/exit 4, write nothing. |
| PII committed via the tracked eval fixture | Information disclosure | Synthetic-only `questions.jsonl`; corpus-derived `claims[].text`; `personal/` git-ignored + in `CORPORA_PREFIXES`; review + optional `scan_text` self-check. |
| stdout polluted by non-JSON (breaks agent parsing) | Tampering | `--json` invariant: one envelope on stdout, human/diagnostics on stderr; `cli.main` catch-all converts stray exceptions to a parseable `ok:false` envelope. |

**Security block-on:** No `high`-severity issues introduced (no network, no auth, no crypto, no new deps, read-only DB access, output confined to git-ignored area). The dominant risk is a *privacy* leak via the tracked fixture or a mis-targeted write — both covered above.

## Sources

### Primary (HIGH confidence — read in full this session)
- `crawler/searchindex.py:400-562` — `_to_match`, `search`, **`resolve`** (the GND-01 resolver + sha-drift guard + read-only connect).
- `crawler/contract.py` (full) — envelope/emit, `SCHEMA_VERSION="1.0"`, `INVALID_INPUT`, `INTERNAL_ERROR`, `EXIT_INVALID_INPUT=2`, `EXIT_INTERNAL_ERROR=4`.
- `crawler/CONTRACT.md` (full) — five-key envelope, success/verdict-fail/execution-error taxonomy, `search`/`--cite` result fields, exit-code table.
- `crawler/cli.py:1-50, 210-525` — `_cmd_report` (verdict mapping), `_cmd_index`, `_cmd_search`, `build_parser`, `main` catch-all.
- `crawler/eval_runner.py` (full) — `_norm`, `{total,passed,failed,failures}` shape, exit-1-on-fail.
- `scripts/check_publish_safe.py:1-160` — `scan_text`, `CORPORA_PREFIXES` (already includes `personal/`), `is_excluded`, abs-path/secret patterns.
- `crawler/dupaudit.py:604-632` and `crawler/dupclean.py:472-599` — the canonical RPT-03 render-then-gate (`scan_text` → `INTERNAL_ERROR`/exit 4) prior art.
- `crawler/tests/test_searchindex.py:557-1032` — unittest conventions (`_run` capture helper, synthetic `_IndexCase`, `TestResolve`, `@skipUnless` real-corpus pattern).
- Live verification: `.venv/bin/python` resolve/normalize round-trip over `corpus/index.db` (confirmed curly-quote/markdown chunk text + `_norm` behavior); FTS5 present (sqlite 3.37.2); 196 tests collected.

### Secondary (HIGH/MEDIUM — internal research, cross-checked against shipped code)
- `.planning/research/v3.0/GROUNDING.md` — milestone-level grounding research (algorithm, honesty boundary, eval metrics, pitfalls, reuse map). Codebase-grounded claims re-verified; forward-looking pre-ship guesses (ID format, `results[]`, "add personal/") corrected against shipped code (see State of the Art).
- `.planning/ROADMAP.md:100-111` — Phase 25 success criteria (authoritative SC1–SC5).
- `.planning/REQUIREMENTS.md` — GND-01/GND-02 definitions; VAL-01/02 deferred; CHK-* downstream.
- `.planning/STATE.md` — locked v3.0 decisions (reuse primitives, no new deps; RPT-03 render-then-gate; acceptance bar).

### Tertiary (LOW confidence)
- None. No external web lookup was performed: the phase is stdlib-only and fully codebase-grounded, so external documentation adds nothing (and all web-provider config flags are `false`).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every primitive is shipped, read in full, and re-verified live.
- Architecture (gate algorithm, exit-code mapping, render-then-gate): HIGH — exact prior art in `dupaudit`/`dupclean` + verdict mapping in `dupclean`/`report`.
- Pitfalls: HIGH — quote-normalization pitfall demonstrated against real corpus chunks; eval-coupling/PII pitfalls grounded in `.gitignore` + `CORPORA_PREFIXES` reality.
- Eval-record schema specifics: MEDIUM — no locked schema; field names are recommendations (see Assumptions A1/A2).

**Research date:** 2026-06-21
**Valid until:** ~2026-07-21 (stable internal domain; re-verify only if `searchindex.resolve`, `contract` exit codes, or `check_publish_safe.scan_text` signatures change).
