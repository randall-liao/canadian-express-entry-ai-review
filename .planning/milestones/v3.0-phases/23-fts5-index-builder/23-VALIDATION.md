# Phase 23 — FTS5 Index Builder · Validation Strategy (Nyquist)

**Requirement:** RET-01 (the only requirement in this phase)
**Goal under test:** A re-runnable SQLite FTS5 keyword index exists over the clean 742-doc corpus,
with every chunk carrying resolvable citation metadata — the citable ground every later answer
stands on.

This file is the **sampling plan**: it names, for each ROADMAP success criterion, the smallest set
of automated checks that would catch a regression (the Nyquist rate — sample often enough that no
failure mode hides between probes). Every check is an `automated` command runnable today; none
requires the real `corpus/` except the explicitly-guarded smoke. All Python runs through Poetry
because the pyenv `python` shim is broken (CRLF / `/bin/sh^M`).

---

## Success-criterion → validation map

| SC (RET-01) | What must be TRUE | Validating test(s) | Plan |
|-------------|-------------------|--------------------|------|
| **SC1** Idempotent, diffable rebuild over the live-doc set | Build over exactly `dupaudit.live_docs`; re-run → byte-identical `chunk_id`s | `TestIdempotent` (synthetic), `TestCitationFields` (covers-live-set count), `TestRealCorpus` (real-corpus re-build equality) | 02, 03 |
| **SC2** Five citation fields per chunk, never invented; `chunk_id = relpath#ordinal` (not rowid) | Each row has relpath/source_url/title/section/crawl_date matching front-matter + headings; `source_url` verbatim; `chunk_id` is content coordinates | `TestCitationFields`, `TestChunkSection` (section breadcrumb + `**9.4**` marker) | 01, 02 |
| **SC3** Bounded chunks (tiny → 1 chunk; legislation split, none unbounded) | tiny doc → exactly 1 chunk; `max(length(text)) <= MAX_CHUNK_CHARS` | `TestChunkBounds` (synthetic), `TestRealCorpus` (`max_text_len <= MAX_CHUNK_CHARS` over real IRPA/IRPR) | 01, 03 |
| **SC4** No PII / no vectors / stdlib only; fail loud if FTS5 absent | DB has only chunks/chunks_fts*/meta; `FTS5Unavailable` raised + non-zero exit on missing FTS5; no new dep | `TestFtsProbe` (fail-loud), `TestIndexCli` (missing-FTS5 → exit 3 path is wired), no-vectors assertion in `TestCitationFields` | 01, 02, 03 |

---

## The five validation strands (and how each is sampled)

### 1. Idempotent rebuild — byte-identical `chunk_id`s (SC1)
- **Synthetic (default suite):** `TestIdempotent` builds the same synthetic corpus into the same db
  twice and asserts `SELECT chunk_id FROM chunks ORDER BY chunk_id` is identical across runs (equal
  lists **and** equal sha1 of the joined ids). Determinism is structurally guaranteed by (a)
  `dupaudit.live_docs`' sorted `rglob` traversal and (b) the pure `chunk()` function (no randomness,
  no time, no I/O — enforced by the `chunk(body) == chunk(body)` test in Plan 01).
- **Real corpus (guarded):** `TestRealCorpus` optionally builds the 742-doc corpus into two tempdir
  DBs and asserts the ordered `chunk_id` lists match.
- **Manual diff probe:** `sqlite3 <db> "SELECT chunk_id, chunk_sha FROM chunks ORDER BY chunk_id"`
  before/after a rebuild → identical (RETRIEVAL.md §6 "diffability").

### 2. Citation-metadata completeness per chunk (SC2)
- `TestCitationFields` plants a doc with known front-matter (`url`, `title`, `crawl_date`) + headings
  and asserts each `chunks` row carries all five fields exactly, that `source_url` equals the
  front-matter `url` **verbatim** (no re-normalization), and that `chunk_id` matches
  `^<relpath>#\d{3}$` and is UNIQUE and is **not** the integer `id`.
- `TestChunkSection` asserts the heading breadcrumb (`Act › DIVISION 1 › …`) and the legislation
  statutory marker capture (`… › s.9.4`) — the only "invented-from-derivation" field, proven to come
  deterministically from the markdown, never fabricated.

### 3. Bounded chunk sizes (SC3)
- `TestChunkBounds`: tiny no-heading body → exactly 1 whole-doc chunk; a ~5,000-char single paragraph
  → multiple chunks each `<= MAX_CHUNK_CHARS` (hard sentence-split). Pure-function level — fast, no DB.
- `TestRealCorpus`: `result["max_text_len"] <= searchindex.MAX_CHUNK_CHARS` over the real ~0.5–1 MB
  IRPA/IRPR FullText docs — the production worst case.
- **Manual probe:** `sqlite3 <db> "SELECT min(length(text)), max(length(text)) FROM chunks"` within
  `[MIN_CHUNK_CHARS (allowing the sole-chunk floor), MAX_CHUNK_CHARS]`.

### 4. FTS5-probe fail-loud (SC4)
- `TestFtsProbe`: (a) `_probe_fts5(real_memory_con)` does not raise and leaves no `_probe` residue;
  (b) `_probe_fts5(stub)` whose `.execute` raises `sqlite3.OperationalError("no such module: fts5")`
  raises `searchindex.FTS5Unavailable` with an actionable, FTS5-naming message.
- `TestIndexCli`: the handler path that converts `FTS5Unavailable` → `missing_dependency` envelope +
  exit 3 is exercised through `cli.main` (the negative path is unit-tested via the probe stub since
  FTS5 is compiled in on this box; the wiring/exit-code mapping is asserted at the CLI boundary).
- **Boundary reality:** FTS5 is present here (SQLite 3.37.2, `ENABLE_FTS5`); the probe is the guard
  for an exotic user Python that omits it (RETRIEVAL.md §7 P1 / environment caveat).

### 5. No-PII / no-vectors / stdlib-only + the real-corpus 742 smoke (SC4 + SC1)
- **No vectors:** `TestCitationFields` asserts the DB tables are exactly `chunks` + `chunks_fts*`
  (FTS shadow tables) + `meta` — no embeddings/vector table exists.
- **No-PII by construction:** the builder reads only `corpus/` via `dupaudit.live_docs` (never
  `personal/`), and stores only corpus text + the five PII-free citation fields + source_type/chunk_sha.
- **Stdlib only:** `poetry run python -c "import crawler.searchindex"` imports with no new dependency;
  grep gate confirms no `yaml.load`, no `content=''`.
- **742 smoke:** `TestRealCorpus` (`@skipUnless(Path("corpus").is_dir())`) builds the real corpus into
  a **tempdir** DB (never `corpus/index.db`, so the suite stages nothing under git-ignored `corpus/`)
  and asserts `docs == 742`, `chunks > docs`, `max_text_len <= MAX_CHUNK_CHARS`.

---

## Test inventory (class → concern → plan)

| Test class | Concern | Default suite? | Plan |
|------------|---------|----------------|------|
| `TestFtsProbe` | FTS5 fail-loud + probe residue (SC4) | yes | 01 |
| `TestChunkBounds` | tiny→1 chunk, no unbounded chunk (SC3) | yes | 01 |
| `TestChunkSection` | heading breadcrumb + `**9.4**` marker (SC2) | yes | 01 |
| `TestCitationFields` | five fields, url verbatim, chunk_id=relpath#NNN, no-vectors (SC2/SC4) | yes | 02 |
| `TestIdempotent` | byte-identical chunk_ids on rebuild (SC1) | yes | 02 |
| `TestIndexCli` | one-line `index` envelope, invalid_input/exit-2, stdout purity (SC1/SC4) | yes | 03 |
| `TestRealCorpus` | real 742-doc build, bounds, idempotency | **skipped unless `corpus/`** | 03 |

---

## Commands (copy-paste)

```bash
# Full phase suite (synthetic; corpus smoke auto-skips if corpus/ absent)
poetry run python -m pytest crawler/tests/test_searchindex.py -q

# Per-strand
poetry run python -m pytest crawler/tests/test_searchindex.py::TestIdempotent -x -q       # SC1
poetry run python -m pytest crawler/tests/test_searchindex.py::TestCitationFields -x -q   # SC2
poetry run python -m pytest crawler/tests/test_searchindex.py::TestChunkBounds -x -q      # SC3
poetry run python -m pytest crawler/tests/test_searchindex.py::TestFtsProbe -x -q         # SC4
poetry run python -m pytest crawler/tests/test_searchindex.py::TestRealCorpus -x -q       # 742 smoke

# Regression: additive contract broke nothing
poetry run python -m pytest crawler/tests/test_cli.py crawler/tests/test_json_contract.py -q

# Real-corpus manual end-to-end (writes the live git-ignored index)
poetry run python -m crawler.cli --json index corpus/ --db corpus/index.db | poetry run python -m json.tool
sqlite3 corpus/index.db "SELECT count(*) FROM chunks; SELECT min(length(text)),max(length(text)) FROM chunks;"
sqlite3 corpus/index.db "INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check');"   # FTS↔content
```

---

## Out of scope for this validation (deferred, by design)
- **MATCH / query escaping / injection** (`R30(3)`, bare `OR`, empty query → `INVALID_INPUT`) —
  Phase 24 (`search` verb, RET-02). No user query enters the index builder.
- **BM25 ranking / `snippet()` / `--cite` resolver round-trip** — Phase 24 (RET-02) / Phase 25 gate
  (GND-01). The `chunk_sha` staleness fingerprint is stored now so the Phase-25 resolver can detect
  content drift, but it is not exercised as a resolver here.
- **Semantic faithfulness / entailment** — explicitly deferred (VAL-01/02); the index guarantees
  resolvable citation coordinates + bounded quotable spans, not meaning.
