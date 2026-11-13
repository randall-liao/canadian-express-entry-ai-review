# Phase 24: `search` Verb + Citation Resolver — Pattern Map

**Mapped:** 2026-06-20
**Requirement:** RET-02
**Files analyzed:** 5 new/modified artifacts — `search()` + `resolve()` (+ a `_to_match()` escaper) in `crawler/searchindex.py`, the `search` verb + `--cite` mode in `crawler/cli.py`, additive doc edits to `crawler/CONTRACT.md` + `crawler/contract.py` docstring, new test classes in `crawler/tests/test_searchindex.py`
**Analogs found:** 4 / 5 strong in-repo analogs — the **Phase-23 `index` verb + `build_index()` are the primary templates** for every new artifact. The only no-analog surface is the FTS5 `MATCH`/`bm25()`/`snippet()` query mechanics + the `_to_match()` escaper (use RETRIEVAL.md §5 + P2 verbatim).

> **Scope note for the planner.** Phase 24 is RET-02 only: the read-side **`search`** verb + the **`--cite`** resolver over the *already-built* Phase-23 index. Do **not** touch `build_index()` / `chunk()` / the DDL / the `index` verb — they shipped in Phase 23 and are GREEN. Phase 23's `23-PATTERNS.md` already flagged `search()`/`resolve()`/`to_match()` as `(P24)`; this is where they get built. Every new function lives in the **existing** `crawler/searchindex.py`; every new verb is a **thin** addition to the **existing** `crawler/cli.py` dispatcher. The contract stays `schema_version "1.0"` (additive).

---

## File Classification

| New/Modified Artifact | Role | Data Flow | Closest Analog | Match Quality |
|-----------------------|------|-----------|----------------|---------------|
| `search(db, query, limit, family) -> dict` in `crawler/searchindex.py` | service / compute (read-only) | request-response (query → BM25-ranked hits) | `searchindex.build_index` (`searchindex.py:296-385`) — sqlite3 connect/try-finally/return-dict shell | exact (shell) / no-analog (FTS query body) |
| `resolve(db, chunk_id) -> dict\|None` in `crawler/searchindex.py` | service / compute (read-only) | CRUD read-by-key (`WHERE chunk_id=?`) | `build_index` post-build `SELECT … fetchone()` (`searchindex.py:369-373`) | exact (mechanics) |
| `_to_match(query) -> str\|None` escaper in `crawler/searchindex.py` | utility (pure) | transform (raw query → FTS5 literal) | `searchindex.chunk_sha` (`searchindex.py:124-131`) — pure stdlib `re`/`hashlib` helper shape | role-match (no FTS-escape analog in repo) |
| `_cmd_search` + `p_search` subparser (incl. `--cite`) in `crawler/cli.py` | controller / route dispatcher | request-response | `cli.py:_cmd_index` (`244-290`) + `p_index` (`352-358`) | **exact** |
| `crawler/CONTRACT.md` + `crawler/contract.py` docstring (additive `search` row) | config / docs | n/a | `CONTRACT.md` `### index` (`146-164`) + `contract.py` docstring command list (`13`, `69`) | **exact** |
| new test classes in `crawler/tests/test_searchindex.py` (`TestSearch*`, `TestCite*`, `TestSearchCli`) | test | n/a | `TestIndexCli` (`test_searchindex.py:557-610`) + `_IndexCase`/`_make_index_corpus` (`292-370`) + `TestRealCorpus` (`634-650`) | **exact** |

---

## Pattern Assignments

### `search()` in `crawler/searchindex.py` (compute, request-response)

**Primary analog:** `searchindex.build_index` (`crawler/searchindex.py:296-385`). Copy its **connection lifecycle shell verbatim** — only the body (a read query instead of a rebuild) changes.

**Connect / try-finally / close shell** — copy `build_index` (`searchindex.py:314-384`):
```python
def search(db: Path, query: str, limit: int = 10, family: str | None = None) -> dict:
    con = sqlite3.connect(str(db))
    try:
        _probe_fts5(con)                     # SAME fail-loud guard as build_index:319
        match = _to_match(query)             # P2 escaper — see below
        ...
        return {                             # deterministic result dict (no timestamp)
            "query": query, "db": str(db), "count": len(hits), "hits": hits,
        }
    finally:
        con.close()
```
- **Reuse `_probe_fts5(con)`** (`searchindex.py:105-121`) at the top — do NOT add a second FTS5 probe. A SQLite without FTS5 must fail loud here exactly as it does in `index` (`FTS5Unavailable` → `_cmd_search` maps to `missing_dependency` / exit 3, mirroring `_cmd_index:271-280`).
- **DB-not-a-file is `INVALID_INPUT`** — but validate it in the CLI handler (`_cmd_search`), not here, mirroring how `_cmd_index:258-267` validates `corpus_dir` before calling `build_index`. (RETRIEVAL.md §5 error handling.)

**Query SQL — copy RETRIEVAL.md §5 (`RETRIEVAL.md:210-218`) verbatim** (this is the no-analog part; there is no existing `MATCH`/`bm25` call in the repo):
```sql
SELECT c.chunk_id, c.source_url, c.relpath, c.title, c.section, c.crawl_date,
       snippet(chunks_fts, 0, '⟦', '⟧', '…', 12) AS snippet,
       bm25(chunks_fts) AS score
FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
WHERE chunks_fts MATCH ?
ORDER BY bm25(chunks_fts)          -- ascending: most relevant first
LIMIT ?;
```
- **Parameter-bind `MATCH ?` and `LIMIT ?`** — never f-string them, mirroring `build_index`'s parameter-bound INSERT (`searchindex.py:348-354`, the inline comment `# parameter-bound, never f-string`). The `MATCH` value is the **escaped** `_to_match()` output, never the raw query (anti-pattern P2 below).
- **`snippet(chunks_fts, 0, …)`** — column index `0` = `text` (the only FTS column; the DDL at `searchindex.py:82-89` indexes only `text`). This is the highlighted cited-span preview (RET-02 SC1).
- **`bm25()` ascending** — scores are negative; more-negative = better; `ORDER BY bm25(...)` (default ascending) puts best hits first (RETRIEVAL.md P9 / `:299`). Do not negate or re-sort.
- **`--family` post-filter** (optional): `AND c.relpath LIKE ? || '/%'`, binding `family`, OR filter in Python on `relpath.split('/',1)[0]` — the same family-derivation convention used in `dupaudit.parse_doc` (`dupaudit.py:186`).

**Hit-dict shape — match the envelope `result.hits[]` in RETRIEVAL.md §5 (`:182-200`)** exactly: `chunk_id, source_url, relpath, title, section, crawl_date, snippet, score`. Build each hit as a plain `dict` from the row (use `con.row_factory = sqlite3.Row` or index positionally as `build_index` does at `:369-373`).

---

### `resolve()` in `crawler/searchindex.py` (compute, CRUD read-by-key)

**Analog:** the post-build `SELECT … fetchone()` reads in `build_index` (`searchindex.py:369-373`). Same mechanics: connect → one parameter-bound `SELECT` → `fetchone()` → close.

**Resolution SQL — copy RETRIEVAL.md §4 (`RETRIEVAL.md:154-159`)**:
```python
def resolve(db: Path, chunk_id: str) -> dict | None:
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT relpath, source_url, title, section, crawl_date, "
            "chunk_sha, text FROM chunks WHERE chunk_id = ?",   # UNIQUE(chunk_id) → 1 row or none
            (chunk_id,),                                         # parameter-bound, never f-string
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None                       # MISS → fail-closed (RET-02 SC2)
    ...
```
- **`WHERE chunk_id = ?`** is an O(log n) indexed lookup — `chunk_id` is `UNIQUE` in the DDL (`searchindex.py:66`). This is **the resolver the Phase-25 grounding gate (GND-01) calls** — keep the return shape stable and PII-free.
- **Fail-closed on miss** (`row is None`) and **on `chunk_sha` drift**: the DDL stores `chunk_sha` (`searchindex.py:73`); `resolve()` may recompute `chunk_sha(text)` (`searchindex.py:124-131`) and signal a mismatch as a stale/fail-closed result (RETRIEVAL.md §4 `:159` + P8 `:297`). An unknown OR stale ID → "not found" (RET-02 SC2).
- **No snippet/bm25 here** — `resolve()` returns the *exact* stored `chunks.text` (the quotable span the gate grounds on); `snippet()` is search-display only (RETRIEVAL.md P5 `:291`).

---

### `_to_match()` escaper in `crawler/searchindex.py` (pure utility, transform)

**No in-repo analog** — closest shape is the pure stdlib helper `chunk_sha` (`searchindex.py:124-131`: a tiny module-level function using `re`/`hashlib`, no I/O). **Copy RETRIEVAL.md P2 (`RETRIEVAL.md:277-285`) verbatim** — this is the ADVERSARIAL-QUERY-SAFE core of the whole phase:
```python
def _to_match(q: str) -> str | None:
    terms = re.findall(r"\w+", q, flags=re.UNICODE)      # drop ()/:/quotes/operators
    if not terms:
        return None                                      # empty/all-punct → caller returns INVALID_INPUT
    return " ".join('"' + t.replace('"', '""') + '"' for t in terms)  # implicit AND
```
- `re` is already imported at `searchindex.py:39` — no new import.
- **Verified behaviour (RETRIEVAL.md `:285`):** `R30(3)` → `"R30" "3"` (parens stripped, no `fts5: syntax error`); `police OR certificates` → `"police" "OR" "certificates"` (bare `OR` becomes a literal term, no operator injection, no column filter); apostrophes/colons are dropped by `\w+`. This satisfies RET-02 SC3.
- **Empty / all-punctuation query → `None`** → `_cmd_search` emits `INVALID_INPUT` (exit 2) and **never runs an empty `MATCH`** (RET-02 SC3). Map `None` exactly like `_cmd_index` maps a bad corpus dir (`cli.py:258-267`).

---

### `_cmd_search` + `p_search` subparser in `crawler/cli.py` (controller — incl. `--cite`)

**Exact analog:** `_cmd_index` (`cli.py:244-290`) for the handler, `p_index` (`cli.py:352-358`) for the subparser. Mirror them 1:1 — the `search`/`--cite` verb is the same thin-dispatcher shape.

**Handler skeleton — copy `_cmd_index` (`cli.py:244-290`):**
```python
def _cmd_search(args: argparse.Namespace) -> int:
    from pathlib import Path
    from crawler import searchindex                       # LAZY import (cli.py:256)

    db = Path(args.db)
    if not db.is_file():                                  # mirror _cmd_index:259-267 (is_dir → is_file)
        msg = f"not a file: {db}"
        if args.json:
            contract.emit(contract.envelope(
                "search", error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT

    # --cite mode: resolve one chunk_id → exact chunk (fail-closed on miss).
    if args.cite is not None:
        try:
            hit = searchindex.resolve(db, args.cite)
        except searchindex.FTS5Unavailable as exc:       # SAME catch as _cmd_index:271-280
            ...                                           # → MISSING_DEPENDENCY, exit 3
        if hit is None:                                   # miss/stale → fail-closed, NOT an exec error
            ...                                           # emit ok:true result:{found:false} OR INVALID_INPUT — pick per SC2
        ...

    # default: ranked search
    try:
        result = searchindex.search(db, args.query, args.limit, args.family)
    except searchindex.FTS5Unavailable as exc:           # copy cli.py:271-280 verbatim
        if args.json:
            contract.emit(contract.envelope(
                "search", error=(contract.MISSING_DEPENDENCY, str(exc))))
        else:
            print(str(exc), file=sys.stderr)
        return contract.EXIT_MISSING_DEPENDENCY
    # INVALID_INPUT for empty/all-punct query (search() / _to_match returned a signal)

    if args.json:
        contract.emit(contract.envelope("search", result=result))
    else:
        print(f"{result['count']} hits for {result['query']!r}", file=sys.stderr)  # human → STDERR ONLY
    return 0
```
**Conventions to copy (all from `_cmd_index`):**
- **Lazy `from crawler import searchindex`** inside the handler (`cli.py:256`) — importing `crawler.cli` must never drag `sqlite3`/index setup (PKG-02 discipline, `cli.py:25`).
- **`contract.emit(contract.envelope("search", result=…))`** is the **only** stdout write; human/summary text goes to **stderr only** (`cli.py:283-289` + RETRIEVAL.md P11 `:303`). One `json.dumps` line, nothing else.
- **Error taxonomy reuse** (`contract.INVALID_INPUT` / `EXIT_INVALID_INPUT=2`, `contract.MISSING_DEPENDENCY` / `EXIT_MISSING_DEPENDENCY=3` from `contract.py:45-60`) — do NOT invent new error types or exit codes.
- **`internal_error` is free** — the `main()` `--json` catch-all (`cli.py:375-385`) already converts any unexpected exception into `ok:false`/`internal_error`/exit 4 with the traceback on stderr. Don't re-implement it; just don't swallow exceptions.

**Subparser — copy `p_index` (`cli.py:352-358`):**
```python
p_search = subparsers.add_parser(
    "search", help="BM25-search the FTS5 index, or resolve a citation id with --cite.")
p_search.add_argument("query", nargs="?", default=None, help="search query (omit when using --cite)")
p_search.add_argument("--db", default="corpus/index.db",
                      help="SQLite index path (default: corpus/index.db)")  # same default as p_index:356
p_search.add_argument("--cite", default=None, help="resolve a single chunk_id to its exact chunk")
p_search.add_argument("--limit", type=int, default=10, help="max ranked hits (default: 10)")
p_search.add_argument("--family", default=None, help="restrict to a corpus family (e.g. pr-pdi)")
p_search.set_defaults(func=_cmd_search)
```
- **Update the subparsers `metavar`** at `cli.py:306-307` to add `search` (it already lists `index`). The global `--json` flag (`cli.py:303-305`) is parsed before the subcommand and is reused as-is.

---

### `crawler/CONTRACT.md` + `crawler/contract.py` docstring (additive — stays `schema_version "1.0"`)

**Analog:** the **`### index`** section added in Phase 23 (`CONTRACT.md:146-164`). Add a sibling **`### search`** section in the same 1:1 style. This is purely additive (RET-02 SC4): the five envelope keys are unchanged; only a new `command` *value* and a new `result` shape are introduced.

**`CONTRACT.md` edits (mirror the `index` precedent):**
- Add `search` to the `command` key description (`CONTRACT.md:54`) and any command enumerations.
- Add a `### search` result-fields table documenting `query, db, count, hits[]` and each hit field (`chunk_id, source_url, relpath, title, section, crawl_date, snippet, score`) — copy the column layout of the `### index` table (`CONTRACT.md:152-160`).
- Document the **`--cite`** resolution result shape (exact chunk; not-found/stale = fail-closed) as a sub-case of `search`.
- Reuse the existing error-taxonomy + exit-code rows as-is (`CONTRACT.md:174-178`, `:182-192`): empty/all-punct query → `invalid_input` exit 2; missing FTS5 → `missing_dependency` exit 3. No new rows needed.

**`contract.py` docstring edits (mirror line 13 + 69):** add `"search"` to the `command` enumerations in the module docstring (`contract.py:13`) and in `envelope()`'s docstring (`contract.py:69`). **No code change to `envelope()`/`emit()`** — they are command-agnostic. `SCHEMA_VERSION` stays `"1.0"` (`contract.py:41`).

---

### New tests in `crawler/tests/test_searchindex.py` (mirror `TestIndexCli` + `_IndexCase` + `TestRealCorpus`)

**Exact analogs (all in `test_searchindex.py`):** `TestIndexCli` (`557-610`), `_IndexCase`/`_make_index_corpus`/`_doc_text` (`273-370`), `TestRealCorpus` (`634-650`). Stdlib `unittest` ONLY — NO pytest fixtures, NO crawl4ai, NO network (header `:1-25` + AGENTS.md convention).

- **Build once, then search/resolve against the real DB** — extend `_IndexCase` (`:357-370`): it already plants a synthetic 4-doc corpus (`_make_index_corpus:292-354`, incl. the `**9.4**` statute doc and an `R30`-style token target) + a tempdir `index.db`. A new `TestSearch(_IndexCase)` calls `searchindex.build_index(self.root, self.db)` in setUp/test, then asserts `searchindex.search(...)` returns ranked hits with a `snippet` and a `chunk_id`.
- **CLI round-trip — copy `TestIndexCli._run` (`:558-567`)** verbatim (the `io.StringIO` + `contextlib.redirect_stdout/stderr` capture). Assert (mirroring `test_index_verb_emits_one_ok_envelope:569-581`): exactly ONE `\n` on stdout (`out.count("\n") == 1`), `obj["ok"] is True`, `obj["command"] == "search"`, `obj["schema_version"] == "1.0"`, and `{` never leaks to stderr (`test_json_stdout_is_pure_one_object:595-602`).
- **Adversarial-query tests (RET-02 SC3 — the headline acceptance):** drive `R30(3)`, `police OR certificates`, an apostrophe query, and `body:funds` through `search()` / the verb and assert **no exception** + literal-term matching; assert an **empty / all-punctuation** query → `invalid_input` exit 2 (mirror `test_missing_corpus_dir_is_invalid_input_exit_2:583-593` and reuse `contract_exit_invalid_input():612-615`).
- **`--cite` hit + miss (RET-02 SC2):** resolve a known `chunk_id` from the built DB (round-trip), and a bogus/stale id → fail-closed "not found". Assert `resolve()` returns the exact `chunks.text` (not a snippet).
- **Optional real-corpus smoke — copy `TestRealCorpus` (`:634-650`)**: `@unittest.skipUnless(Path("corpus").is_dir(), …)`, build into a `tempfile.TemporaryDirectory()` db (NEVER `corpus/index.db`), then run a known query (e.g. `"police certificate which countries"`, RETRIEVAL.md `:338`) and assert ≥1 hit + a resolvable `chunk_id`.

---

## Shared Patterns

### JSON envelope + emit (stdout=JSON / stderr=human)
**Source:** `crawler/contract.py` — `envelope()` (`:63-87`), `emit()` (`:90-96`), constants (`:41-60`).
**Apply to:** `_cmd_search` (both `search` and `--cite` paths).
```python
contract.emit(contract.envelope("search", result=result))            # success
contract.emit(contract.envelope("search", error=(contract.INVALID_INPUT, msg)))  # failure
```
One `json.dumps` line to stdout via `emit`; **all** human/progress text to stderr (`cli.py:285-289`, RETRIEVAL.md P11 `:303`).

### sqlite3 connect → try/finally → close
**Source:** `searchindex.build_index` (`searchindex.py:315-384`).
**Apply to:** `search()` and `resolve()`. Always `con.close()` in a `finally`; read-only (no `commit` needed for SELECT-only paths).

### Parameter-bound SQL (never f-string user input)
**Source:** `build_index` INSERT (`searchindex.py:348-354`, comment `# parameter-bound, never f-string`) + the post-build `SELECT` reads (`:369-373`).
**Apply to:** `MATCH ?`, `LIMIT ?`, `WHERE chunk_id = ?`, the `--family LIKE ? || '/%'` filter.

### Error taxonomy + exit codes (reuse, don't extend)
**Source:** `contract.py:45-60` + `CONTRACT.md:174-192`.
**Apply to:** empty/all-punct query → `INVALID_INPUT`/exit 2; DB not a file → `INVALID_INPUT`/exit 2; host without FTS5 (`FTS5Unavailable`) → `MISSING_DEPENDENCY`/exit 3; unexpected → `internal_error`/exit 4 (free via `cli.py:375-385`).

### FTS5 fail-loud probe (reuse the Phase-23 function)
**Source:** `searchindex._probe_fts5` (`searchindex.py:105-121`) + `FTS5Unavailable` (`:101-102`).
**Apply to:** the top of `search()` (and `resolve()` if it opens its own connection). Do NOT write a second probe.

### Lazy import in the CLI handler
**Source:** `_cmd_index` (`cli.py:256`).
**Apply to:** `_cmd_search` — `from crawler import searchindex` inside the function, never at `cli.py` module top.

---

## Anti-Patterns to Avoid

| Anti-pattern | Why it's wrong | Mitigation (source) |
|---|---|---|
| **Raw query → `MATCH` (P2 injection/syntax)** | `MATCH 'R30(3)'` raises `fts5: syntax error near "R30"`; `body:funds` becomes a silent column filter; bare `OR`/`AND`/`NEAR` become operators; an apostrophe breaks the literal. | **Always** route through `_to_match()` (RETRIEVAL.md `:277-285`); bind the escaped string to `MATCH ?`. RET-02 SC3. |
| **Empty / all-punct query → empty `MATCH`** | Runs a meaningless/erroring query instead of a clean rejection. | `_to_match()` returns `None` → emit `INVALID_INPUT` exit 2 (mirror `cli.py:258-267`). RET-02 SC3. |
| **`offsets()` for span info (P5)** | `offsets()` does **not** exist in FTS5 (`unable to use function offsets in the requested context`) — it was FTS3/4. | Use `snippet(chunks_fts, 0, '⟦','⟧','…',12)` for preview; quote `chunks.text` for the exact span (RETRIEVAL.md `:291`). |
| **`rowid`/`chunks.id` as the citation id (P8)** | A rebuild renumbers `id`; prior citations resolve to the wrong chunk → breaks the grounding gate's trust. | Resolve on the stable `chunk_id = relpath#ordinal` (`UNIQUE`, `searchindex.py:66`); never expose/resolve `c.id` (RETRIEVAL.md `:297`, test precedent `test_searchindex.py:445-460`). |
| **Negating / re-sorting `bm25()` (P9)** | Scores are negative (more-negative = better); flipping the sign or re-sorting inverts relevance. | `ORDER BY bm25(chunks_fts)` ascending; pass the raw score through to `result.hits[].score` (RETRIEVAL.md `:299`). |
| **Resolver returns a snippet instead of exact text** | The grounding gate must quote the verbatim chunk; a highlighted/truncated snippet is not quotable. | `resolve()` returns `chunks.text` verbatim; `snippet()` is search-display only (RETRIEVAL.md `:291`). |
| **Treating a `--cite` miss / sha-drift as an exception** | A miss is a normal fail-closed signal, not an execution error. | Return `None`/`found:false` (or `INVALID_INPUT` per SC2) — don't raise/crash (RETRIEVAL.md §4 `:159`). |
| **Any stray stdout print (P11)** | Corrupts the single-JSON-object contract. | Emit only via `contract.emit`; all human text to stderr (`cli.py:285-289`). |
| **Re-building / mutating the index in `search`/`--cite`** | RET-02 is read-only over the Phase-23 DB; a write would break idempotency + concurrency. | SELECT-only; no `INSERT`/`DROP`/`commit`. The index is built solely by the Phase-23 `index` verb. |
| **A new third-party dependency** | RET-01/RET-02 are stdlib-only (`sqlite3` is stdlib; SC4). | `re` + `sqlite3` only — both already imported in `searchindex.py:39-40`. |

---

## No Analog Found

| Surface | Role | Data Flow | Reason | Planner action |
|---|---|---|---|---|
| FTS5 `MATCH` / `bm25()` / `snippet()` query body in `search()` | compute | request-response | No existing `MATCH`/`bm25`/`snippet` call anywhere in `crawler/` — Phase 23 only *built* the index, never queried it. | Copy the Query SQL from **RETRIEVAL.md §5 (`:210-218`)** + P5/P9 verbatim; the surrounding connect/try-finally shell **does** have an analog (`build_index`). |
| `_to_match()` FTS5 escaper | utility | transform | No query-string escaper exists in the repo. | Copy **RETRIEVAL.md P2 (`:277-285`)** verbatim; shape it like the pure helper `chunk_sha` (`searchindex.py:124-131`). |

---

## Metadata

**Analog search scope:** `crawler/` (`searchindex.py`, `cli.py`, `contract.py`, `CONTRACT.md`, `dupaudit.py`), `crawler/tests/` (`test_searchindex.py`, `test_json_contract.py`), `.planning/research/v3.0/RETRIEVAL.md`, `.planning/ROADMAP.md`.
**Files scanned:** 8.
**Primary template:** the Phase-23 `index` verb (`_cmd_index`, `p_index`) + `build_index()` — every Phase-24 artifact mirrors its Phase-23 sibling.
**Pattern extraction date:** 2026-06-20.
