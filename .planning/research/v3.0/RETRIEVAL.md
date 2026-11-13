# v3.0 Retrieval — FTS5 Keyword Index + `search` Verb + Resolvable Citations

**Scope:** Implementation-ready details for RET-01 (re-runnable FTS5 index over the clean corpus) and RET-02 (`search` CLI verb returning ranked, citable chunks via the `crawler/CONTRACT.md` JSON envelope). The stack is **locked** (STACK.md): stdlib `sqlite3` FTS5, BM25 ranking, no vectors, single local `.db`, citation metadata stored per chunk. This document is the *how*, not a re-pick.

**Verification basis:** All FTS5 behaviors below were probed live in this repo's environment — **Python 3.14.4 / SQLite 3.53.0, FTS5 compiled in (`ENABLE_FTS5` present)** — matching the STACK.md note. Confidence **HIGH** on FTS5 mechanics (verified against the running engine + authoritative SQLite FTS5 docs), **HIGH** on corpus metadata reality (read the real files + `crawler/dupaudit.py`).

---

## 1. Corpus metadata reality — where each citation field lives

I inspected the real `corpus/` and `crawler/` code. **The citation fields are not all in one place — three of five come from YAML front-matter, one is derived from the file path, and `section` does not exist as metadata at all (it must be derived from the markdown headings).**

### Per-doc YAML front-matter (the source of truth for source_url / title / crawl_date)

Every live corpus doc is a markdown file beginning with a `---` … `---` YAML block. Verified keys present on **all 742 live docs**:

| Front-matter key | Example | Citation field it feeds |
|---|---|---|
| `url` | `https://laws-lois.justice.gc.ca/eng/acts/i-2.5/FullText.html` | **source_url** (already normalized at crawl time — see below) |
| `title` | `Immigration and Refugee Protection Act` | **title** |
| `crawl_date` | `2026-06-10T23:27:24Z` (ISO-8601 UTC) | **crawl_date** |
| `source_type` | `legislation` / `guidance` | useful facet (store it too) |
| `label` | `Source: IRCC (canada.ca), reproduced for personal non-commercial use; …` | provenance string (store it) |
| `generator` | `crawl4ai-deep` | provenance only |
| `teer`, `noc_code` | (376 NOC docs only) | optional NOC facet |

Real example (`corpus/legislation-irpa/FullText.md`):
```yaml
---
url: "https://laws-lois.justice.gc.ca/eng/acts/i-2.5/FullText.html"
title: "Immigration and Refugee Protection Act"
source_type: "legislation"
crawl_date: "2026-06-10T23:27:24Z"
label: "Source: IRCC (canada.ca), reproduced for personal non-commercial use; verify against the live page."
generator: "crawl4ai-deep"
---
```

**`url` is already normalized.** The crawler records pages through `pipeline.PageClassifier.classify` → `profile.normalize_url` (drops fragment, strips configured query params, trims trailing slash), and writes that normalized URL into front-matter. So the index can read `url` **verbatim** as `source_url` — no need to re-normalize, no profile coupling required for the index builder. (`dupaudit.parse_doc` re-normalizes only as belt-and-suspenders for cross-family URL-dup detection.)

### corpus-relative path — derived from the filesystem, not stored

`relpath` = the doc path relative to the corpus root, POSIX form, e.g. `legislation-irpa/FullText.md`. This is exactly what `dupaudit.parse_doc` computes:
```python
relpath = path.resolve().relative_to(Path(corpus_root).resolve()).as_posix()
family  = relpath.split("/", 1)[0]   # e.g. "legislation-irpa"
```
Reuse this. `relpath` is the human-facing, PII-free citation locator and the basis of the stable citation ID (§4).

### `section` — **does NOT exist as metadata; derive it from markdown headings**

There is **no `section` front-matter key** anywhere in the corpus (confirmed: only `url/title/source_type/label/generator/crawl_date` + `teer/noc_code`). The "section" required by RET-01 must be **computed during chunking** as the nearest enclosing ATX heading path. Heading reality across the corpus:

- Heading-level histogram (sampled): `#` (doc title) → `##` → `###` are dominant, with some `####`/`#####`.
- **Legislation is the hard case.** In `legislation-irpa/FullText.md` and `legislation-irpr/FullText.md` (the two ~0.5–1.0 MB docs) the *statutory* unit (e.g. `30(3)`, `9.4`) is an **inline bold marker** `**9.4** Despite other provisions…`, **not** a markdown heading. Markdown headings in those files are things like `## SOR/2019-174, s. 1` and `####  DIVISION 1.1`.

So `section` = the chunk's heading breadcrumb (e.g. `Immigration and Refugee Protection Act › DIVISION 1 — Requirements and Selection`). For legislation, additionally capture the leading bold statutory marker of the chunk (e.g. `9.4`) into the section/anchor so a cite can name the subsection. See §3.

### Sidecars present (do not need them for citation metadata)

Each doc has a sibling `<name>.md.eval.json` (QC verdict — `verdict`, `relevance_score`, `must_contain`…) and each family has a `manifest.json` keyed by URL mirroring the front-matter. **The front-matter is the authoritative per-doc metadata; the manifest is a convenience mirror.** Index off the front-matter (via `dupaudit.live_docs`), not the manifest, so the index and the QC pipeline agree on exactly the same live-doc set (the 742-filter).

---

## 2. FTS5 schema

**Decision: a regular `chunks` table (citable source of truth) + an external-content FTS5 index over only the `text` column.** Rationale, then the DDL.

Why this shape (not the alternatives):
- **Contentless (`content=''`) is rejected** — it cannot run `snippet()`/`highlight()` and cannot return the stored text, which breaks the "show the cited span" requirement. (Verified: snippet needs retrievable column content.)
- **Single standalone FTS5 table with `UNINDEXED` metadata columns** works and is the simplest (one table, `snippet()`/`bm25()` fine, `DELETE … WHERE source_url=?` fine) — but resolving a citation ID (`WHERE chunk_id=?`) and per-source deletes become **O(n) scans** because you cannot put a B-tree index on an FTS5 column. The grounding gate (GND-01) and eval harness (GND-02) hammer the resolver, so an indexed lookup matters.
- **External-content FTS5 + regular `chunks` table** gives: indexed O(log n) citation resolution (`UNIQUE(chunk_id)`), `snippet()`/`highlight()`/`bm25()` all work (verified), and the text is stored once (FTS reads it from `chunks`). This is the recommended design.

```sql
-- The citable source of truth. One row per chunk. PII-free.
CREATE TABLE chunks (
    id          INTEGER PRIMARY KEY,         -- internal rowid; NOT the citation id
    chunk_id    TEXT NOT NULL UNIQUE,        -- stable, resolvable citation id (see §4)
    relpath     TEXT NOT NULL,               -- 'legislation-irpa/FullText.md'
    source_url  TEXT NOT NULL,               -- front-matter `url` (already normalized)
    title       TEXT NOT NULL,               -- front-matter `title`
    section     TEXT NOT NULL DEFAULT '',    -- heading breadcrumb (+ statutory marker)
    crawl_date  TEXT NOT NULL DEFAULT '',    -- front-matter `crawl_date`
    source_type TEXT NOT NULL DEFAULT '',    -- front-matter `source_type` (facet)
    ordinal     INTEGER NOT NULL,            -- 0-based chunk index within the doc
    text        TEXT NOT NULL                -- the chunk body (the cited span source)
);
CREATE INDEX idx_chunks_source_url ON chunks(source_url);  -- fast per-source rebuild
-- chunk_id already indexed by the UNIQUE constraint (fast citation resolve).

-- External-content FTS5 index over ONLY the searchable text.
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    content='chunks',          -- read column content from `chunks`
    content_rowid='id',        -- map fts rowid -> chunks.id
    tokenize='porter unicode61'
);

-- Build/refresh the FTS index from current `chunks` content (see §6):
INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');
```

Notes verified live in this repo:
- `bm25(chunks_fts[, w_text])` returns a score where **more relevant = more negative**; `ORDER BY bm25(chunks_fts)` (ascending, the default) puts best hits first. With a single indexed column, column weighting is moot here (title/section are not indexed, by design — keep the index lean and rank on body relevance).
- `snippet(chunks_fts, 0, '⟦', '⟧', '…', N)` returns a windowed, highlighted excerpt of the matched span — this is the cited-span display. (Column index `0` = `text`, the only FTS column.)
- `highlight(chunks_fts, 0, '<', '>')` returns the **whole** column with matches wrapped — use `snippet()` for display, `highlight()` only if you want the full chunk marked up.
- **There is no `offsets()` in FTS5** (it was an FTS3/4 function; verified: `unable to use function offsets in the requested context`). Do **not** plan on `offsets()` — use `snippet()`/`highlight()` (or an `fts5vocab` table) for span info.

Optionally store a tiny `meta` table (`schema_version`, `built_at`, `tokenizer`, `corpus_root`) for diagnostics and to let the `search` verb fail loud if the DB predates a schema change.

---

## 3. Chunking strategy

Goal: chunks small enough that a citation points at a *specific passage* (not a 1 MB Act), large enough that BM25 has lexical context. Corpus size profile (live docs, body bytes): **min 597, median 3,765, p75 5,564, p95 11,392, max 1,081,734.** So most docs are a few KB (1–4 chunks), but the two legislation FullText docs are ~0.5–1.0 MB and **must** be split.

**Algorithm — heading-aware, paragraph-packed, with min/max bounds:**

1. **Strip front-matter** with `dupaudit.body_of(text)` (it mirrors `eval_runner._strip_frontmatter`: file minus the leading `---`…`---` block = the cleaned body). Reuse it — do not re-parse.
2. **Split into sections at ATX headings** (`^#{1,6}\s`). Maintain a running **heading stack** so each section carries its breadcrumb path (e.g. `Act › DIVISION 1 — Requirements`). `crawler/profile.py` already has `_HEADING_RE = re.compile(r"^(#{1,6})\s")` — reuse that exact regex so heading detection matches the crawler's own notion of a heading.
3. **Pack paragraphs into chunks** within each section. Walk the section's blank-line-delimited paragraphs and accumulate until the next paragraph would exceed **`MAX_CHUNK_CHARS` (~1,800)**; emit, then continue. Target window ≈ **800–1,200 chars** (~150–200 words) — good BM25 context and citation granularity.
4. **Merge undersized fragments.** If a chunk would be `< MIN_CHUNK_CHARS` (~250, echoing the crawler's `MIN_CONTENT_CHARS = 200`), merge it into the previous chunk of the same section. Tiny docs (e.g. `definitions/`) thus become a single chunk = the whole doc, which is the correct citation granularity for them.
5. **Hard-split overlong paragraphs.** A single paragraph longer than `MAX_CHUNK_CHARS` (common in legislation) is split on sentence boundaries (`. ` / newline) as a fallback so no chunk is unbounded.
6. **Legislation anchor capture.** When a chunk's first non-heading line begins with a bold statutory marker `**\d`, capture that marker (e.g. `9.4`, `30`) into the chunk's `section` (append ` › s.9.4`). Regex: `^\*\*([0-9]+(?:\.[0-9]+)?)\*\*`. This lets a cite name the subsection even though it is not a markdown heading.

**`section` value** stored per chunk = the heading breadcrumb at emit time, plus the statutory marker when present. Deterministic given the doc text.

**Chunk ↔ citation granularity:** cite the **chunk**, not the whole doc. A chunk is small enough to quote verbatim (the grounding gate quotes a real span) and carries `source_url + relpath + section` so the human can verify against the live page. The whole-doc identity is still recoverable via `relpath`/`source_url`.

> Tunables (`MIN_CHUNK_CHARS`, `MAX_CHUNK_CHARS`, target window) belong in module constants next to the chunker, mirroring how `pipeline.MIN_CONTENT_CHARS` is a single named constant. Keep them deterministic — no randomness, no model calls.

---

## 4. Citation-ID scheme

**Requirement:** a `chunk_id` that (a) deterministically maps back to exactly one chunk row, (b) survives a re-index, (c) is safe to print (PII-free, ASCII, copy-pasteable).

**Do NOT use the integer `rowid` as the citation ID.** A full rebuild can renumber rows if the doc set or ordering changes, breaking previously emitted citations. The ID must be derived from stable *content coordinates*, not DB internals.

**Scheme — `relpath#ordinal` plus a short content digest:**

```
chunk_id = f"{relpath}#{ordinal:03d}"            # e.g. "legislation-irpr/FullText.md#017"
```
- `relpath` is stable (corpus path) and PII-free; `ordinal` is the 0-based chunk index within that doc from the deterministic chunker (§3). Same corpus text → same IDs on every rebuild → **survives re-index** and is **diffable**.
- It is human-meaningful: a reader sees the source file and the position.

**Add a content fingerprint for tamper/staleness detection** (used by the grounding gate, GND-01):
```
chunk_sha = sha1(text).hexdigest()[:12]          # store in a column (optional but recommended)
```
The resolver can then verify both that `chunk_id` exists **and** that the cited text still hashes to `chunk_sha` — catching the case where the corpus was re-crawled and the chunk content drifted. (`dupaudit.body_hash` already establishes the sha1-of-body convention; reuse `hashlib.sha1` the same way.)

**Resolution (the GND-01 resolver, O(log n)):**
```sql
SELECT relpath, source_url, title, section, crawl_date, text
FROM chunks WHERE chunk_id = ?;     -- UNIQUE(chunk_id) → one row or none
```
A miss (no row) or a `chunk_sha` mismatch is a **fail-closed** signal. Verified live: `WHERE chunk_id=?` returns exactly the one row.

> Edge case: if two docs ever collide on `relpath` (they cannot — relpath is unique per file) the `UNIQUE(chunk_id)` constraint fails the build loudly, which is the desired fail-closed behavior. Re-crawls that delete a doc make its old IDs resolve to *nothing* → the gate fails closed on stale citations, exactly as intended.

---

## 5. `search` verb + JSON envelope

Add a `search` subcommand to the **existing** `corpus-crawler` CLI (`crawler/cli.py`), wired through the **existing** envelope in `crawler/contract.py`. Implement the compute in a new lean module (e.g. `crawler/searchindex.py`) so `cli.py` stays a thin dispatcher (its established pattern).

**CLI shape** (mirrors the other subparsers in `build_parser`):
```
corpus-crawler --json search "<query>" --db corpus/index.db [--limit 10] [--family pr-pdi]
corpus-crawler --json index  corpus/ --db corpus/index.db        # build/rebuild (RET-01)
```
The global `--json` flag is parsed **before** the subcommand (already implemented). Honor the stdout=JSON / stderr=human invariant: in `--json` mode write **exactly one** `json.dumps` object to stdout via `contract.emit`, everything else to stderr.

**Envelope** (reuse `contract.envelope("search", result=…)` / `contract.emit`):
```json
{
  "schema_version": "1.0",
  "ok": true,
  "command": "search",
  "result": {
    "query": "police certificate which countries",
    "db": "corpus/index.db",
    "count": 3,
    "hits": [
      {
        "chunk_id": "police-certificates/police-certificate-requirements.md#004",
        "source_url": "https://www.canada.ca/.../police-certificates.html",
        "relpath": "police-certificates/police-certificate-requirements.md",
        "title": "Police certificates – Canada.ca",
        "section": "Who needs a police certificate › Where you lived",
        "crawl_date": "2026-06-11T01:09:06Z",
        "snippet": "…you need a police certificate from every country where you ⟦lived⟧ 6 months or more…",
        "score": -1.83
      }
    ]
  },
  "error": null
}
```

**Adding `search`/`index` is a non-breaking (additive) contract change.** The five envelope keys are unchanged; only new `command` *values* and new per-command `result` shapes are introduced (existing shapes untouched). Per `CONTRACT.md`'s stability promise this stays `schema_version "1.0"`. Update `CONTRACT.md` + `contract.py`'s docstring command list to include `index`/`search` (the doc must mirror the code 1:1).

**Error handling — reuse the existing taxonomy:**
- DB file missing / not a file, or corpus dir missing on `index` → `INVALID_INPUT` (exit `2`).
- **FTS5 not compiled into the user's SQLite** → emit a `missing_dependency`-style failure (a new sentinel or reuse `INVALID_INPUT` with a clear message); fail loud. Probe at startup (see Pitfall 1).
- Unexpected exception in `--json` mode → the `cli.main` catch-all already converts it to `internal_error` (exit `4`) with the traceback on stderr. Inherit that for free.

**Query SQL** (the safe, escaped form — see Pitfall 2):
```sql
SELECT c.chunk_id, c.source_url, c.relpath, c.title, c.section, c.crawl_date,
       snippet(chunks_fts, 0, '⟦', '⟧', '…', 12) AS snippet,
       bm25(chunks_fts) AS score
FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
WHERE chunks_fts MATCH ?
ORDER BY bm25(chunks_fts)          -- ascending: most relevant first
LIMIT ?;
```
Optional `--family` post-filter: `AND c.relpath LIKE ? || '/%'` (or filter in Python on `relpath.split('/',1)[0]`).

---

## 6. Rebuild / idempotency

**Two re-runnable modes, both deterministic and diffable:**

**(a) Full rebuild (default for `index`, simplest, bulletproof):**
```python
DROP TABLE IF EXISTS chunks_fts;
DROP TABLE IF EXISTS chunks;
# CREATE both (DDL in §2)
for path, text in dupaudit.live_docs(corpus_root):     # the 742-filter, reused
    meta = yaml.safe_load(dupaudit._frontmatter_of(text)) or {}
    body = dupaudit.body_of(text)
    relpath = path.resolve().relative_to(corpus_root).as_posix()
    for ordinal, (section, chunk_text) in enumerate(chunk(body)):
        INSERT INTO chunks(chunk_id, relpath, source_url, title, section,
                           crawl_date, source_type, ordinal, text) VALUES (...)
INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');   # resync FTS from content
```
Because `live_docs` walks `rglob("*.md")` (a stable, sorted-by-Path traversal) and the chunker is deterministic, two runs over the same corpus produce **identical `chunk_id → text` rows**. Verified: re-running an identical build leaves the row count and IDs unchanged.

**(b) Per-source incremental refresh (idempotent by `source_url`):**
```sql
DELETE FROM chunks WHERE source_url = ?;          -- drop the doc's old chunks
-- re-INSERT this doc's freshly-chunked rows
INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');  -- resync FTS
```
`idx_chunks_source_url` makes the delete O(log n). Use this when refreshing a single re-crawled doc.

**Avoid the external-content sync footgun by NOT using triggers.** External-content FTS5 can be kept in sync with incremental triggers, but the `'delete'` command requires the *old* text and is a classic source of corruption bugs. For a corpus this small (≈742 docs → low-tens-of-thousands of chunks), always resync with the single **`INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')`** command after mutating `chunks`. It is sub-second here, fully deterministic, and has no stale-text footgun. (`'integrity-check'` is available to assert the index matches content in tests.)

**Diffability:** to compare two builds, dump a deterministic manifest and diff it:
```sql
SELECT chunk_id, length(text) AS n, substr(text,1,0) FROM chunks ORDER BY chunk_id;
-- or store chunk_sha (§4) and: SELECT chunk_id, chunk_sha FROM chunks ORDER BY chunk_id;
```
Identical corpus → identical manifest. This is the practical meaning of "diffable" for a binary `.db`.

**Where the `.db` lives:** write to `corpus/index.db` (the corpus dir is already git-ignored, so the index — which contains corpus text but **no PII** — stays out of the public repo, consistent with the corpus itself). Never index anything from the user's PII area.

---

## 7. Pitfalls (ranked, each with mitigation)

**P1 — FTS5 not compiled into the user's SQLite (fail loud).** *Critical.* Verified present here (SQLite 3.53.0, `ENABLE_FTS5`), but a user's exotic Python may lack it. **Mitigation:** at the start of `index`/`search`, run a probe and fail with an actionable message + the contract's error envelope:
```python
try:
    con.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)"); con.execute("DROP TABLE _probe")
except sqlite3.OperationalError:
    # emit ok:false error envelope: "Your SQLite lacks FTS5; install a Python whose
    # bundled SQLite is built with ENABLE_FTS5." -> non-zero exit.
```
Do this **before** touching the corpus so the failure is unambiguous.

**P2 — Unescaped user query → MATCH syntax error / silent mis-parse.** *Critical & citation-relevant.* Verified: `… MATCH 'R30(3)'` raises `fts5: syntax error near "R30"` (parens are FTS5 grouping operators); a bare apostrophe breaks the SQL string; a colon like `body:funds` is silently reinterpreted as an FTS5 **column filter**; bare `OR`/`AND`/`NOT`/`NEAR` become operators. **Mitigation:** never pass the raw query to `MATCH`. Tokenize and re-quote each term as an FTS5 string literal:
```python
import re
def to_match(q: str) -> str | None:
    terms = re.findall(r"\w+", q, flags=re.UNICODE)     # drop ()/:/quotes/operators
    if not terms: return None
    return " ".join('"' + t.replace('"', '""') + '"' for t in terms)  # implicit AND
```
Verified: `R30(3)` → `"R30" "3"` matches the R30(3) chunk; `police OR certificates` → `"police" "OR" "certificates"` treats `OR` as a literal term (no injection). An empty/all-punctuation query → return `INVALID_INPUT`, don't run an empty MATCH.

**P3 — Tokenizer choice (`unicode61` vs `porter` vs `trigram`) for IRCC English + section codes.** *High.* Verified: with plain `unicode61`, `"certificate"` and `"certificates"` match **different** chunks (split recall). With **`porter unicode61`**, both forms match both chunks (stemmed singular/plural collapse) **and** alphanumeric section tokens like `R30` are preserved intact. `trigram` is for substring/`LIKE`-style matching and bloats the index — wrong tool for ranked English retrieval. **Mitigation:** use **`tokenize='porter unicode61'`** (porter stemmer wrapping the unicode61 word-splitter). It maximizes recall on IRCC prose while keeping `R30`/`9.4`-style tokens.

**P4 — Numeric/section tokens are low-IDF noise.** *High, legislation-specific.* Verified tokenization: `R30(3)` → `[r30, 3]`, `30(3)` → `[30, 3]`. The bare `3` (or `30`) appears in thousands of chunks, so AND-ing it dilutes precision when a user searches `R30(3)`. **Mitigation:** the distinctive token (`r30`) carries the signal; consider dropping pure 1–2 digit tokens from the generated MATCH (treat as stopwords) so the query reduces to the rare `"r30"`, or offer phrase search (`"30 3"` via the consecutive-token phrase) for exact-subsection intent. Capturing the statutory marker into `section` (§3) also lets agents filter/verify by subsection without relying on the noisy digit token.

**P5 — Showing the cited span: use `snippet()`, not `offsets()`.** *Medium.* Verified: `offsets()` does **not** exist in FTS5 (`unable to use function offsets in the requested context`); `highlight()` returns the *entire* column (too long for a citation preview); `snippet()` returns a bounded, highlighted window. **Mitigation:** display with `snippet(chunks_fts, 0, open, close, '…', N)` (N≈10–15 tokens). For a guaranteed-quotable span the grounding gate should quote from the stored `chunks.text` (the exact chunk), using `snippet` only for the human-facing preview.

**P6 — Contentless FTS can't snippet / can't return text.** *Medium.* If someone "optimizes" to `content=''` to save space, `snippet()`/`highlight()`/text retrieval break, killing the citation display. **Mitigation:** the §2 schema uses **external content** (`content='chunks'`), which keeps text retrievable and `snippet()` working while storing text once. Don't switch to contentless.

**P7 — Very short and very long docs.** *Medium.* Tiny docs (min 597 bytes, e.g. `definitions/`) shouldn't fragment; the two ~0.5–1.0 MB legislation FullText docs must not become one giant chunk. **Mitigation:** the chunker's `MIN_CHUNK_CHARS` merge makes a tiny doc one chunk (= whole-doc citation, correct), and the heading-split + `MAX_CHUNK_CHARS` hard-split bounds the legislation chunks (§3). Verify post-build: `SELECT max(length(text)), min(length(text)) FROM chunks` are within the configured bounds (allowing the merge floor).

**P8 — Citation ID tied to `rowid` breaks on re-index.** *Medium but corrosive to trust.* A rebuild can renumber `rowid`, so prior citations would resolve to the wrong/again chunk. **Mitigation:** content-coordinate `chunk_id = relpath#ordinal` + optional `chunk_sha` (§4), never the integer rowid. Stable across rebuilds; mismatched sha = fail-closed.

**P9 — BM25 column weighting misuse / sign confusion.** *Low.* `bm25()` returns **negative** scores (more negative = better); ordering ascending is correct. With a single indexed `text` column, extra weights are inert. **Mitigation:** `ORDER BY bm25(chunks_fts)` ascending; don't index `title`/`section` just to weight them (keeps the index lean and citations rank on body relevance). If title-boosting is ever wanted, add `title` as a second FTS column and use `bm25(chunks_fts, 5.0, 1.0)` — but that is a deliberate, later change.

**P10 — Prefix/phrase queries and the `*` operator.** *Low.* Prefix search needs the quoted-term-then-star form: `"biometr"*` (verified to match `biometrics`); a bare `*` or a malformed prefix can error. **Mitigation:** only enable prefix as an explicit `--prefix` mode that appends `*` to the last quoted term; keep the default exact-token AND search. Phrase intent (`--phrase`) wraps all terms in one `"…"`.

**P11 — `--json` stdout purity.** *Low (already solved upstream).* Any stray print to stdout corrupts the single-JSON-object contract. **Mitigation:** route all human/progress text to stderr; emit only via `contract.emit`; the `cli.main` `--json` catch-all already guarantees a parseable `ok:false` envelope on unexpected errors. Mirror the `contextlib.redirect_stdout(sys.stderr)` discipline used by the crawl path if any chatty library is ever called.

---

## 8. Reuse map — call these, don't reinvent

| Need | Reuse (do **not** rebuild) | Where |
|---|---|---|
| Enumerate the 742 live docs (skip `_dropped/`, `completeness/`, `REPORT.md`, `*.live.md`, frontmatterless files) | `dupaudit.live_docs(corpus) -> Iterator[(Path, text)]` | `crawler/dupaudit.py:146` |
| Strip front-matter → cleaned body (the on-disk body = the cleaned markdown) | `dupaudit.body_of(text)` | `crawler/dupaudit.py:65` |
| Get the raw YAML front-matter block to parse | `dupaudit._frontmatter_of(text)` + `yaml.safe_load` (**never** `yaml.load`) | `crawler/dupaudit.py:90` |
| Compute corpus-relative path + family | `path.resolve().relative_to(corpus_root).as_posix()` / `relpath.split('/',1)[0]` (as in `parse_doc`) | `crawler/dupaudit.py:186` |
| Content fingerprint convention (sha1 of body) | follow `dupaudit.body_hash` (`hashlib.sha1`) for `chunk_sha` | `crawler/dupaudit.py:80` |
| Heading detection regex (match the crawler's notion of a heading) | `profile._HEADING_RE = re.compile(r"^(#{1,6})\s")` | `crawler/profile.py:32` |
| Min-content threshold precedent for the merge floor | `pipeline.MIN_CONTENT_CHARS = 200` | `crawler/pipeline.py:43` |
| JSON envelope + emit (stdout=JSON / stderr=human) | `contract.envelope("search"|"index", result=…)`, `contract.emit(...)`, `contract.INVALID_INPUT`, `EXIT_*` | `crawler/contract.py` |
| CLI dispatch pattern (thin subparser → compute module) | add `p_search`/`p_index` subparsers in `build_parser`, dispatch like `_cmd_report` | `crawler/cli.py:243` |
| URL is already normalized (read front-matter `url` verbatim) | written via `profile.normalize_url` at crawl time | `crawler/profile.py:286`, `crawler/pipeline.py:105` |

**New code to add (stdlib only — no new deps):**
- `crawler/searchindex.py` — `build_index(corpus, db)`, `chunk(body) -> [(section, text)]`, `search(db, query, limit, family) -> result`, `resolve(db, chunk_id) -> row|None`, `_probe_fts5(con)`.
- `crawler/cli.py` — `index` + `search` subparsers and `_cmd_index` / `_cmd_search`.
- `crawler/CONTRACT.md` + `contract.py` docstring — document the two new command result shapes (additive; stays `schema_version "1.0"`).
- Tests under `crawler/tests/` (the repo already tests the contract + CLI): FTS5 probe, query escaping (`R30(3)`, quotes, `OR`), idempotent rebuild (counts/IDs stable), citation resolve hit/miss, snippet present, chunk-size bounds.

**Verify commands (post-build):**
```bash
# Build + sanity
corpus-crawler --json index corpus/ --db corpus/index.db | python -m json.tool
sqlite3 corpus/index.db "SELECT count(*) FROM chunks; SELECT min(length(text)),max(length(text)) FROM chunks;"
# Idempotency: build twice, IDs identical
sqlite3 corpus/index.db "SELECT chunk_id FROM chunks ORDER BY chunk_id" | sha1sum   # rebuild → same hash
# FTS integrity
sqlite3 corpus/index.db "INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check');"
# Search + resolve round-trip
corpus-crawler --json search "police certificate which countries" --db corpus/index.db --limit 5
sqlite3 corpus/index.db "SELECT source_url FROM chunks WHERE chunk_id='police-certificates/...#004';"
```

---

### Environment caveat (flagged per quality gate)
FTS5 mechanics were verified on this box: **Python 3.14.4 / SQLite 3.53.0, FTS5 compiled in**, matching STACK.md. The project targets `requires-python >=3.10`; CPython's bundled SQLite ships FTS5 on mainstream builds, and `bm25()` exists since SQLite 3.20. The one genuinely environment-dependent risk is a user-built Python whose SQLite omits `ENABLE_FTS5` — **P1's startup probe is the required guard**, not an optional nicety.
