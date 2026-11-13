# Phase 23: FTS5 Index Builder — Pattern Map

**Mapped:** 2026-06-20
**Requirement:** RET-01
**Files analyzed:** 4 new/modified artifacts (`crawler/searchindex.py`, `index` verb in `crawler/cli.py`, `crawler/tests/test_searchindex.py`, additive doc edits to `crawler/CONTRACT.md` + `crawler/contract.py` docstring)
**Analogs found:** 3 / 4 strong in-repo analogs (the FTS5/SQLite mechanics + the chunker have **no** in-repo analog — see "No Analog Found")

> **Scope note for the planner.** Phase 23 is RET-01 only: **build** the index + the citation metadata + the `index` verb. The research (RETRIEVAL.md) is written for RET-01 *and* RET-02 (`search`/`--cite`). The `search()` / `resolve()` functions, the `search` subparser, query-escaping (`to_match`), `snippet()`/`bm25()`, and the `search` result shape are **Phase 24** surface. They are listed here only where they share the same analog as a Phase-23 artifact, flagged `(P24)`, so the planner does not pull them into this phase's plans. Build them as stubs/raise-`NotImplementedError` if the contract module pattern (RED-first) is followed.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `crawler/searchindex.py` | service / compute module | file-I/O read → transform (chunk) → CRUD into SQLite `.db` | `crawler/dupaudit.py` (corpus-reader half) + `crawler/dupclean.py` (mutating-output half) | role-match (reader = exact; SQLite write = no analog) |
| `index` verb in `crawler/cli.py` (`_cmd_index`, `p_index` subparser) | controller / route dispatcher | request-response | `crawler/cli.py:_cmd_report` (208–240) + `_cmd_apply_verdicts` (134–159) | exact |
| `crawler/tests/test_searchindex.py` | test | n/a | `crawler/tests/test_dupaudit.py` (synthetic corpus) + `test_cli.py` (CLI dispatch) | exact |
| `crawler/CONTRACT.md` + `crawler/contract.py` docstring (additive `index` command row) | config / docs | n/a | `crawler/CONTRACT.md` "Per-command `result` fields" + `contract.py:1-32` docstring | exact |

---

## Pattern Assignments

### `crawler/searchindex.py` (service / compute module, file-I/O → transform → SQLite CRUD)

**Primary analog:** `crawler/dupaudit.py` — the canonical **read-only corpus-reading tool** in this repo. It already enumerates the live-doc set, strips front-matter, parses YAML, and computes relpath/family. Phase 23 reuses those primitives **by import**, never reimplements them.
**Secondary analog:** `crawler/dupclean.py` — the canonical **tool that writes a durable artifact + a `--json` contract envelope + fails closed**. Mirror its module-docstring "Design constraints" block and its main()/validation/error shape.

**Module docstring + design-constraints block** — mirror `dupaudit.py:1-41` and `dupclean.py:34-48`. State explicitly: OFFLINE (no `crawl4ai`, no network), **stdlib only — no new runtime dependency** (`sqlite3` is stdlib; RET-01 SC4), `yaml.safe_load` ONLY, and the reuse map. Open with:
```python
from __future__ import annotations
```
(every module in `crawler/` starts with this — `dupaudit.py:43`, `dupclean.py:50`, `cli.py:27`, `contract.py:34`, `profile.py:19`.)

**Reuse map — import these, do NOT rebuild** (verified line anchors):

| Need | Call exactly | Anchor |
|------|--------------|--------|
| Enumerate the 742 live docs (skips `_dropped/`, `completeness/`, `REPORT.md`, `*.live.md`, frontmatterless) | `dupaudit.live_docs(corpus) -> Iterator[(Path, str)]` | `crawler/dupaudit.py:146` |
| Strip front-matter → cleaned body (the chunker's input) | `dupaudit.body_of(text)` | `crawler/dupaudit.py:65` |
| Raw YAML front-matter block to parse | `dupaudit._frontmatter_of(text)` then `yaml.safe_load(...)` (NEVER `yaml.load`) | `crawler/dupaudit.py:90` |
| corpus-relative path (POSIX) + family | `path.resolve().relative_to(Path(corpus_root).resolve()).as_posix()` / `relpath.split("/",1)[0]` | `crawler/dupaudit.py:186` (in `parse_doc`) |
| Content fingerprint convention for `chunk_sha` | follow `dupaudit.body_hash` → `hashlib.sha1(...).hexdigest()` (`[:12]` slice for chunk_sha) | `crawler/dupaudit.py:80` |
| Heading regex (the crawler's own notion of an ATX heading) | `profile._HEADING_RE` = `re.compile(r"^(#{1,6})\s")` | `crawler/profile.py:32` |
| Min-content precedent for the chunker merge floor | `pipeline.MIN_CONTENT_CHARS = 200` (chunker's `MIN_CHUNK_CHARS ~250` echoes this) | `crawler/pipeline.py:43` |
| `url` is already normalized at crawl time — read front-matter `url` **verbatim** as `source_url` | written via `profile.normalize_url` in the crawler; do NOT re-normalize | `crawler/profile.py` / `pipeline.py:105` |

**Front-matter parse pattern** — copy `dupaudit.parse_doc` (`crawler/dupaudit.py:177-187`) verbatim for the metadata read:
```python
# Frontmatter — safe_load ONLY (never yaml.load): semi-trusted local input.
meta = yaml.safe_load(_frontmatter_of(text)) or {}
if not isinstance(meta, dict):
    meta = {}
raw_url = str(meta.get("url", "") or "")
title   = str(meta.get("title", "") or "")
# RET-01: source_url is read VERBATIM (already normalized) — unlike parse_doc which
# re-normalizes only as belt-and-suspenders for cross-family URL-dup detection.
```

**Module-constants pattern** — chunker tunables go in named module constants next to the chunker, mirroring `pipeline.MIN_CONTENT_CHARS = 200` (`pipeline.py:43`) and `contract.SCHEMA_VERSION = "1.0"` (`contract.py:41`):
```python
MIN_CHUNK_CHARS = 250      # merge floor — echoes pipeline.MIN_CONTENT_CHARS = 200
MAX_CHUNK_CHARS = 1800     # hard ceiling (heading/sentence split above this)
```

**Function surface to add** (stdlib only): `build_index(corpus, db)`, `chunk(body) -> [(section, text)]`, `_probe_fts5(con)`, `resolve(db, chunk_id) -> row|None` (P24), `search(db, query, limit, family)` + `to_match(q)` (P24).

**Idempotent full-rebuild loop** — RETRIEVAL.md §6; the determinism guarantee rides on `dupaudit.live_docs`' sorted `rglob` traversal + a deterministic chunker:
```python
for path, text in dupaudit.live_docs(corpus_root):     # the 742-filter, reused
    meta = yaml.safe_load(dupaudit._frontmatter_of(text)) or {}
    body = dupaudit.body_of(text)
    relpath = path.resolve().relative_to(corpus_root).as_posix()
    for ordinal, (section, chunk_text) in enumerate(chunk(body)):
        chunk_id = f"{relpath}#{ordinal:03d}"          # content-coordinate id, NOT rowid
        # INSERT INTO chunks(...)
# INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')  # resync FTS from content
```

**Anti-patterns to avoid** (each verified in RETRIEVAL.md §7):
- **Do NOT use the integer `rowid`/DB autoincrement as the citation ID** (P8) — a rebuild renumbers it. Use `chunk_id = f"{relpath}#{ordinal:03d}"` content coordinates.
- **Do NOT re-normalize `url`** — front-matter `url` is already normalized at crawl time; read it verbatim (avoids a `profile` coupling the builder doesn't need).
- **Do NOT re-parse front-matter / re-implement body-strip / re-walk the corpus** — call `dupaudit.live_docs` / `body_of` / `_frontmatter_of`. Reimplementing risks diverging from the 742-filter the QC pipeline uses.
- **Never `yaml.load`** — `yaml.safe_load` only (threat T-20-02; front-matter is semi-trusted local input).
- **Do NOT use `content=''` (contentless FTS5)** (P6) — it breaks `snippet()`/text retrieval. Use external-content `content='chunks'`.
- **Do NOT keep FTS in sync with triggers / the `'delete'` command** (§6) — always resync via the single `INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')`.
- **Do NOT emit progress to stdout** in `--json` mode (P11) — route human text to stderr; the only stdout write is `contract.emit`.

---

### `index` verb in `crawler/cli.py` (`_cmd_index` + `p_index` subparser)

**Analog:** `_cmd_report` (`crawler/cli.py:208-240`) for the validate→compute→emit shape; `_cmd_apply_verdicts` (`134-159`) for the directory-validation guard; `build_parser` (`243-302`) for subparser registration; `main()` (`305-327`) for the inherited catch-all.

`cli.py` is a **THIN dispatcher** (its module docstring, `cli.py:4-7`: "No module logic is re-implemented here"). `_cmd_index` validates inputs and forwards to `searchindex.build_index`; **all compute lives in `searchindex.py`**.

**Handler pattern** — copy the `--json` validate-then-emit branch from `_cmd_report` / `_cmd_apply_verdicts`:
```python
def _cmd_index(args: argparse.Namespace) -> int:
    from pathlib import Path
    from crawler import searchindex        # LAZY import (keeps CLI import light)

    corpus = Path(args.corpus_dir)
    if not corpus.is_dir():
        if args.json:
            contract.emit(contract.envelope(
                "index", error=(contract.INVALID_INPUT, f"not a directory: {corpus}")))
        return contract.EXIT_INVALID_INPUT      # 2
    # FTS5 probe BEFORE touching the corpus (RET-01 SC4 / RETRIEVAL.md P1) →
    # fail loud with an actionable error + non-zero exit if SQLite lacks FTS5.
    result = searchindex.build_index(corpus, Path(args.db))
    if args.json:
        contract.emit(contract.envelope("index", result=result))
    return 0
```

**Subparser registration** — mirror `p_report` / `p_apply` (`cli.py:280-300`), and add `index` to the `metavar` list (`cli.py:257`) and the docstring command map (`cli.py:9-14`):
```python
p_index = subparsers.add_parser(
    "index", help="Build/rebuild the FTS5 keyword index over the clean corpus.")
p_index.add_argument("corpus_dir", help="corpus directory to index")
p_index.add_argument("--db", default="corpus/index.db",
                     help="output SQLite index path (default: corpus/index.db)")
p_index.set_defaults(func=_cmd_index)
```

**Error taxonomy — reuse `contract` constants** (`contract.py:43-60`): bad corpus dir → `INVALID_INPUT` / exit `2`; FTS5 missing → fail loud (a `MISSING_DEPENDENCY`-style envelope / exit `3`, or `INVALID_INPUT` with a clear message — planner's call, but it MUST be loud + non-zero per SC4). Any unexpected exception is converted to `internal_error` / exit `4` **for free** by the `main()` catch-all (`cli.py:317-327`) — inherit it, don't re-wrap.

**Anti-patterns to avoid:**
- **Do NOT put compute logic in `cli.py`** — it is a thin dispatcher (docstring `cli.py:4-7`). Keep `_cmd_index` to validation + `contract.emit`.
- **Do NOT import `searchindex` at module top** — lazy-import inside the handler (mirrors `_cmd_report`'s `from crawler import completeness` at `cli.py:211`), so `import crawler.cli` stays cheap and never drags `sqlite3` setup work.
- **Do NOT print to stdout in `--json` mode** — only `contract.emit`; human text → stderr.
- **Do NOT bump `schema_version`** — adding the `index` command value + its `result` shape is **additive** (RETRIEVAL.md §5, ROADMAP SC; stays `"1.0"`).

---

### `crawler/tests/test_searchindex.py` (test)

**Analogs:** `crawler/tests/test_dupaudit.py` (synthetic-corpus fixtures + real-corpus skip), `crawler/tests/test_cli.py` (CLI dispatch capture), `crawler/tests/test_dupclean.py` (mint artifacts from the real producer).

**Hard conventions (from AGENTS.md / `test_dupaudit.py:1-28`):** stdlib **`unittest` ONLY** — NO pytest, NO crawl4ai, NO network, NO browser. Run via `python -m unittest crawler.tests.test_searchindex -v`. Every test builds a tiny synthetic corpus in a tempdir and runs in-process.

**Synthetic-corpus + frontmatter builder** — copy `_doc_text` (`test_dupaudit.py:97-106`) and the `_make_dup_corpus` tempdir pattern (`133-247`):
```python
def _doc_text(url, crawl_date, title, body):
    return ("---\n" f'url: "{url}"\n' f'title: "{title}"\n'
            f'crawl_date: "{crawl_date}"\n' "---\n\n" f"{body}")
```
Plant at least: a tiny doc (→ one whole-doc chunk, SC3), a multi-heading doc (→ breadcrumb `section`), and a legislation-style doc with an inline `**9.4**` bold statutory marker (→ statutory anchor capture, SC2/SC3).

**tempdir `setUp`/`tearDown` base case** — copy `_CorpusCase` (`test_dupaudit.py:276-283`):
```python
class _IndexCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
    def tearDown(self):
        self._tmp.cleanup()
```

**Class-per-concern split** — mirror `test_dupaudit.py`'s `TestEnumerate`/`TestExact`/…/`TestJson` layout. For RET-01 map the SCs to classes: `TestFtsProbe` (P1 fail-loud), `TestChunkBounds` (SC3 min/max, tiny→1 chunk, no unbounded chunk), `TestCitationFields` (SC2 five fields + `chunk_id == relpath#ordinal`, never invented), `TestIdempotent` (SC1 — build twice, `chunk_id`s byte-identical), `TestJson` (the `index` envelope), `TestRealCorpus` (skipped if `corpus/` absent).

**CLI-dispatch capture helper** — copy `test_dupaudit.py:522-535` `_run` / `test_cli.py:30-37`:
```python
def _run(self, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(argv)            # exercise the real `index` verb end-to-end
    return rc, out.getvalue(), err.getvalue()
# assert exactly one JSON line, then json.loads + obj["command"] == "index"
```

**Optional real-corpus smoke test** — copy the `skipUnless` guard verbatim (`test_dupaudit.py:542-548`):
```python
@unittest.skipUnless(Path("corpus").is_dir(),
                     "real corpus/ not present — skipping integration smoke test")
class TestRealCorpus(unittest.TestCase):
    def test_index_covers_the_live_doc_set(self):
        ...   # assert chunk count > live-doc count; SELECT max(length(text)) within bounds
```

**Idempotency assertion (SC1)** — the FTS5-native way (RETRIEVAL.md §6/§8): build twice into two DBs (or rebuild in place), then `SELECT chunk_id FROM chunks ORDER BY chunk_id` and assert the two ID lists are byte-identical; optionally `INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')` to assert FTS↔content consistency.

**Anti-patterns to avoid:**
- **No pytest / no fixtures plugins** — `unittest.TestCase` classes only.
- **No network / no `crawl4ai`** — index tests run purely offline on synthetic tempdir corpora.
- **Do NOT assert against the real `corpus/`** in the default suite — gate it behind `skipUnless(Path("corpus").is_dir())` so CI without the git-ignored corpus stays green.
- **Do NOT hand-author the expected DB/contract** — drive the real `searchindex.build_index` / `cli.main(["--json","index",...])` and assert on its output (mirrors `test_dupclean._mint_report` minting from the real producer, `test_dupclean.py:16-19`).

---

### `crawler/CONTRACT.md` + `crawler/contract.py` docstring (additive doc edit)

**Analog:** `CONTRACT.md` "Per-command `result` fields" section (`### crawl` / `### report` rows at `CONTRACT.md:85-140`) and the `contract.py` module docstring command list (`contract.py:13`, `54`).

The contract doc must mirror the code **1:1** (RETRIEVAL.md §5; `CONTRACT.md` stability promise). Add an `### index` result-fields subsection in `CONTRACT.md` and append `index` to the `command` enumeration string in `contract.py:13` and `:54`. This is an **additive** change — `schema_version` stays `"1.0"` (the five envelope keys are unchanged; only a new `command` value + `result` shape are introduced).

**Anti-pattern:** Do NOT change the five envelope keys, the `EXIT_*` codes, or `SCHEMA_VERSION` (`contract.py:41`). Additive-only.

---

## Shared Patterns

### JSON envelope + emit (stdout = JSON / stderr = human)
**Source:** `crawler/contract.py` — `envelope(command, result=, error=)` (`63-87`), `emit(obj)` (`90-96`), constants `INVALID_INPUT`/`MISSING_DEPENDENCY`/`INTERNAL_ERROR` (`45-53`), `EXIT_INVALID_INPUT=2`/`EXIT_MISSING_DEPENDENCY=3`/`EXIT_INTERNAL_ERROR=4` (`57-60`).
**Apply to:** `_cmd_index` in `cli.py` (and any `--json` path in `searchindex.main` if a standalone entry is added).
```python
from crawler import contract
contract.emit(contract.envelope("index", result={...}))            # success
contract.emit(contract.envelope("index", error=(contract.INVALID_INPUT, msg)))  # error
```
A *verdict* of fail is **ok:true** with exit 1; `error` is reserved for execution failures (`contract.py:22-28`). Exactly one `json.dumps` line on stdout; everything else stderr.

### YAML safe-load (security — threat T-20-02)
**Source:** `dupaudit.parse_doc` (`crawler/dupaudit.py:178`), `profile.py:15-16`.
**Apply to:** every front-matter read in `searchindex.py`.
```python
meta = yaml.safe_load(_frontmatter_of(text)) or {}   # NEVER yaml.load
```

### sha1 body/content fingerprint convention
**Source:** `dupaudit.body_hash` (`crawler/dupaudit.py:80-87`), itself mirroring `pipeline.py:115`.
**Apply to:** the optional `chunk_sha` staleness fingerprint (RET-01 SC2 / RETRIEVAL.md §4).
```python
chunk_sha = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
```

### Corpus confinement / read-only enumeration (threat T-20-01)
**Source:** `dupaudit.live_docs` (`crawler/dupaudit.py:152-166`) — walks only `rglob` within the resolved root; never dereferences a path taken from file content.
**Apply to:** `searchindex.build_index` reads only via `dupaudit.live_docs`; the only write is `corpus/index.db` (a git-ignored, PII-free artifact). Never index anything under the user's PII area.

### Inherited `--json` catch-all (no per-command try/except needed)
**Source:** `cli.main` (`crawler/cli.py:317-327`) — wraps dispatch, converts any unhandled exception into an `internal_error` envelope (exit 4) with the traceback on stderr.
**Apply to:** `_cmd_index` — let unexpected errors propagate; the dispatcher guarantees a parseable `ok:false` envelope.

### `from __future__ import annotations` header
**Source:** every `crawler/` module (`dupaudit.py:43`, `cli.py:27`, `contract.py:34`, `profile.py:19`).
**Apply to:** `searchindex.py` and `test_searchindex.py`.

---

## No Analog Found

These have **no existing implementation pattern in the repo** (confirmed: `grep -rln "import sqlite3|fts5|FTS5" crawler/` → zero hits). The planner must take them from **RETRIEVAL.md** (the authoritative, environment-verified research), not from an in-repo file.

| Concern | Role | Data Flow | Why no analog | Use instead |
|---------|------|-----------|---------------|-------------|
| FTS5 schema (`chunks` + external-content `chunks_fts`) + DDL + `sqlite3` connection/cursor lifecycle | persistence / migration | CRUD | No SQLite anywhere in `crawler/` | RETRIEVAL.md §2 (DDL), §6 (rebuild) |
| The deterministic chunker (`chunk(body) -> [(section, text)]`): heading-stack breadcrumb, paragraph-packing, min/max bounds, legislation `**9.4**` anchor capture | transform | batch / transform | No chunking exists in the corpus pipeline | RETRIEVAL.md §3 (algorithm) + §4 (`chunk_id`) |
| FTS5 probe / fail-loud guard (`CREATE VIRTUAL TABLE _probe USING fts5(x)`) | utility / guard | — | No FTS5 feature-detection precedent | RETRIEVAL.md §7 P1 |
| `bm25()` / `snippet()` ranked query + `to_match()` query escaping `(P24)` | service | request-response | Phase 24 surface; no FTS query code exists | RETRIEVAL.md §5 (query SQL) + §7 P2/P3 |

The **shape** for these still follows the repo's house style (module docstring + design-constraints block + `from __future__ import annotations` + sectioned comment banners + `contract` envelope) — only the SQLite/FTS5/chunking *bodies* come from research.

---

## Metadata

**Analog search scope:** `crawler/` (modules + `tests/`), `crawler/CONTRACT.md`, `.planning/research/v3.0/RETRIEVAL.md`, `.planning/ROADMAP.md`.
**Files scanned:** `dupaudit.py`, `dupclean.py`, `cli.py`, `contract.py`, `profile.py`, `pipeline.py`, `tests/test_dupaudit.py`, `tests/test_dupclean.py`, `tests/test_cli.py`, `CONTRACT.md`.
**SQLite/FTS5 precedent in repo:** none (`grep -rln "import sqlite3|fts5|FTS5" crawler/` → 0).
**Pattern extraction date:** 2026-06-20
