"""Offline FTS5 keyword-index builder over the clean corpus (Phase 23 — RET-01).

This module builds a re-runnable SQLite FTS5 keyword index over the live corpus
and stamps every chunk with the resolvable citation metadata the grounding gate
(Phase 25) later verifies. Plan 01 lays the two dependency-free foundations the
rest of the phase stands on — the **fail-loud FTS5 availability probe** and the
**deterministic heading-aware chunker** — built and GREEN-tested in isolation
before ``build_index`` (Plan 02) and the ``index`` CLI verb (Plan 03) wire them
together.

Run (Plan 03 adds the ``index`` subparser)::

    poetry run python -m crawler.cli --json index corpus/ --db corpus/index.db

Design constraints (mirroring ``dupaudit`` / ``dupclean``):
* OFFLINE — no ``crawl4ai`` import, no network, no browser.
* STDLIB ONLY — no new runtime dependency. ``sqlite3`` is stdlib and ships FTS5
  on mainstream CPython builds (RET-01 SC4); the probe fails loud otherwise.
* ``yaml.safe_load`` ONLY (never ``yaml.load``) for the semi-trusted local
  front-matter Plan 02 reads (threat T-20-02).
* Reuse the repo's tested primitives — do NOT re-implement them:
    - live-doc enumeration / body-strip / front-matter:
      ``dupaudit.live_docs`` / ``dupaudit.body_of`` / ``dupaudit._frontmatter_of``
    - ATX heading detection: ``profile._HEADING_RE``
    - sha1 fingerprint convention: ``dupaudit.body_hash`` (``hashlib.sha1``)

Anti-patterns this module must avoid (RETRIEVAL.md §7):
* No contentless FTS5 — it breaks ``snippet()``/text retrieval (P6); the FTS
  vtable uses external content (``content='chunks'``).
* No ``rowid`` as the citation id — a rebuild renumbers it (P8); Plan 02 mints
  ``chunk_id = relpath#ordinal`` content coordinates.
* No re-normalizing ``url`` — front-matter ``url`` is already normalized at
  crawl time; read it verbatim.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

import yaml

from crawler import dupaudit, profile  # reused corpus primitives + heading regex

# --------------------------------------------------------------------------- #
# Chunker tunables (named module constants — mirroring pipeline.MIN_CONTENT_CHARS
# = 200 and contract.SCHEMA_VERSION = "1.0"). Deterministic: no randomness, no
# time, no I/O. RETRIEVAL.md §3.
# --------------------------------------------------------------------------- #
MIN_CHUNK_CHARS = 250        # merge floor — echoes pipeline.MIN_CONTENT_CHARS = 200
MAX_CHUNK_CHARS = 1800       # hard ceiling (heading / sentence split above this)
TARGET_CHUNK_CHARS = 1000    # soft pack target (~800-1200 chars)
TOKENIZER = "porter unicode61"  # RETRIEVAL.md §7 P3 — stems plurals, keeps R30/9.4
DB_SCHEMA_VERSION = "1"      # index-DB schema version (diagnostics `meta` table);
                             # distinct from the contract envelope schema_version "1.0".

# --------------------------------------------------------------------------- #
# Schema DDL (RETRIEVAL.md §2). A regular `chunks` table = the citable source of
# truth + an external-content FTS5 index over ONLY the searchable `text` column.
# --------------------------------------------------------------------------- #
CHUNKS_DDL = """
CREATE TABLE chunks (
    id          INTEGER PRIMARY KEY,         -- internal rowid; NOT the citation id
    chunk_id    TEXT NOT NULL UNIQUE,        -- stable resolvable citation id (relpath#ordinal)
    relpath     TEXT NOT NULL,               -- 'legislation-irpa/FullText.md'
    source_url  TEXT NOT NULL,               -- front-matter `url` (already normalized)
    title       TEXT NOT NULL,               -- front-matter `title`
    section     TEXT NOT NULL DEFAULT '',    -- heading breadcrumb (+ statutory marker)
    crawl_date  TEXT NOT NULL DEFAULT '',    -- front-matter `crawl_date`
    source_type TEXT NOT NULL DEFAULT '',    -- front-matter `source_type` (facet)
    chunk_sha   TEXT NOT NULL DEFAULT '',    -- sha1(text)[:12] staleness fingerprint (§4)
    ordinal     INTEGER NOT NULL,            -- 0-based chunk index within the doc
    text        TEXT NOT NULL                -- the chunk body (the cited span source)
);
CREATE INDEX idx_chunks_source_url ON chunks(source_url);  -- fast per-source rebuild
""".strip()

# External-content FTS5 index over ONLY the searchable text. content='chunks'
# (NOT contentless) keeps text retrievable so snippet()/highlight() work (P6).
FTS_DDL = """
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id',
    tokenize='porter unicode61'
);
""".strip()

# Legislation statutory marker at a chunk head, e.g. **9.4** or **30** (§3 step 6).
_STATUTE_RE = re.compile(r"^\*\*([0-9]+(?:\.[0-9]+)?)\*\*")

# Heading-breadcrumb separator (U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION MARK).
_SEP = " \u203a "


# --------------------------------------------------------------------------- #
# FTS5 availability probe (RETRIEVAL.md §7 P1 — fail loud, before any corpus read)
# --------------------------------------------------------------------------- #
class FTS5Unavailable(RuntimeError):
    """Raised when the host SQLite build lacks the FTS5 extension."""


class EmptyQuery(ValueError):
    """Raised when a query has no searchable terms (empty / all-punctuation) — the CLI maps it to INVALID_INPUT."""


def _probe_fts5(con) -> None:
    """Feature-detect FTS5 by creating + dropping a throwaway vtable.

    Runs BEFORE any corpus read (Plan 03 calls it at the top of the build) so a
    SQLite without FTS5 fails unambiguously with an actionable message instead of
    silently mis-behaving. Leaves no ``_probe`` residue on success.
    """
    try:
        con.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        con.execute("DROP TABLE _probe")
    except sqlite3.OperationalError as exc:
        raise FTS5Unavailable(
            "This Python's bundled SQLite lacks the FTS5 extension "
            f"({exc}). The keyword index requires FTS5: install a Python whose "
            "bundled SQLite is built with ENABLE_FTS5 (mainstream CPython builds "
            "ship it), then re-run."
        ) from exc


def chunk_sha(text: str) -> str:
    """Short content fingerprint for staleness detection (RETRIEVAL.md §4).

    Mirrors ``dupaudit.body_hash`` (``hashlib.sha1``); the 12-hex slice is the
    ``chunks.chunk_sha`` value Plan 02 stores so the Phase-25 resolver can detect
    corpus drift.
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Deterministic heading-aware chunker (RETRIEVAL.md §3 — NO in-repo analog).
#
# Pure: same body in -> byte-identical (section, text) list out. No randomness,
# no time, no I/O, no model calls. This purity is what makes the citation
# `chunk_id`s (relpath#ordinal, Plan 02) byte-identical across rebuilds (SC1).
# --------------------------------------------------------------------------- #


def _hard_split(para: str) -> list[str]:
    """Split a paragraph longer than MAX_CHUNK_CHARS on sentence boundaries.

    A single oversized legislation paragraph (~0.5-1 MB FullText docs) is split
    on ``. `` / newline so NO chunk is ever unbounded (RETRIEVAL.md §3 step 5).
    A sentence with no boundary that is itself longer than the ceiling is
    char-split as a last-resort fallback, guaranteeing every piece <= the ceiling.
    """
    if len(para) <= MAX_CHUNK_CHARS:
        return [para]
    units = [u for u in re.split(r"(?<=\.)\s+|\n+", para) if u]
    pieces: list[str] = []
    buf = ""
    for unit in units:
        candidate = (buf + " " + unit) if buf else unit
        if buf and len(candidate) > MAX_CHUNK_CHARS:
            pieces.append(buf)
            buf = unit
        else:
            buf = candidate
    if buf:
        pieces.append(buf)
    # Last resort: a single unit longer than the ceiling -> char-split.
    bounded: list[str] = []
    for piece in pieces:
        if len(piece) <= MAX_CHUNK_CHARS:
            bounded.append(piece)
        else:
            for i in range(0, len(piece), MAX_CHUNK_CHARS):
                bounded.append(piece[i : i + MAX_CHUNK_CHARS])
    return bounded


def _pack(paras: list[str]) -> list[str]:
    """Pack blank-line-delimited paragraphs into chunks within one section.

    Accumulate paragraphs toward TARGET_CHUNK_CHARS, never exceeding
    MAX_CHUNK_CHARS (RETRIEVAL.md §3 step 3). Overlong paragraphs are hard-split
    first so the ceiling always holds.
    """
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for para in paras:
        for piece in _hard_split(para):
            plen = len(piece)
            sep = 2 if buf else 0  # the "\n\n" join cost
            if buf and buf_len + sep + plen > MAX_CHUNK_CHARS:
                chunks.append("\n\n".join(buf))
                buf, buf_len, sep = [], 0, 0
            buf.append(piece)
            buf_len += sep + plen
            if buf_len >= TARGET_CHUNK_CHARS:
                chunks.append("\n\n".join(buf))
                buf, buf_len = [], 0
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def _merge_floor(chunks: list[str]) -> list[str]:
    """Merge an undersized trailing chunk into the previous one of the section.

    RETRIEVAL.md §3 step 4 — so a tiny whole doc collapses to one chunk and no
    section ships a sub-MIN_CHUNK_CHARS tail (except a section's sole chunk).
    The merge is skipped when it would push the previous chunk past
    MAX_CHUNK_CHARS, so the hard ceiling (SC3) is never violated.
    """
    merged = list(chunks)
    while len(merged) >= 2 and len(merged[-1]) < MIN_CHUNK_CHARS:
        tail = merged[-1]
        prev = merged[-2]
        if len(prev) + 2 + len(tail) > MAX_CHUNK_CHARS:
            break
        merged[-2] = prev + "\n\n" + tail
        merged.pop()
    return merged


def chunk(body: str) -> list[tuple[str, str]]:
    """Split a front-matter-stripped body into ``(section, text)`` chunks.

    The caller passes an already front-matter-stripped body (Plan 02 uses
    ``dupaudit.body_of``); this function does NOT re-strip. Deterministic and
    bounded (RETRIEVAL.md §3):

    1. Detect ATX headings with ``profile._HEADING_RE`` and keep a running
       heading stack; each paragraph carries its breadcrumb (joined by ``\u203a``).
    2. Pack paragraphs into chunks per section (TARGET soft, MAX hard ceiling).
    3. Merge an undersized trailing fragment into the previous chunk.
    4. Hard-split any paragraph longer than the ceiling on sentence boundaries.
    5. Append ``\u203a s.<marker>`` when a chunk head is a bold statutory marker.
    """
    # Pass 1: walk lines -> (breadcrumb, paragraph) events in document order.
    para_events: list[tuple[str, str]] = []
    stack: dict[int, str] = {}
    breadcrumb = ""
    para_lines: list[str] = []

    def _emit_para() -> None:
        if para_lines:
            para = "\n".join(para_lines)
            if para.strip():
                para_events.append((breadcrumb, para))
            para_lines.clear()

    for line in body.split("\n"):
        m = profile._HEADING_RE.match(line)
        if m:
            _emit_para()  # flush paragraph under the *current* breadcrumb first
            level = len(m.group(1))
            stack[level] = line[m.end():].strip()
            for deeper in range(level + 1, 7):
                stack.pop(deeper, None)
            breadcrumb = _SEP.join(stack[lv] for lv in range(1, 7) if lv in stack)
            continue
        if line.strip() == "":
            _emit_para()
        else:
            para_lines.append(line)
    _emit_para()

    # Pass 2: group consecutive same-breadcrumb paragraphs into sections.
    sections: list[tuple[str, list[str]]] = []
    for bc, para in para_events:
        if sections and sections[-1][0] == bc:
            sections[-1][1].append(para)
        else:
            sections.append((bc, [para]))

    # Pass 3: pack + merge each section; capture statutory markers.
    result: list[tuple[str, str]] = []
    for bc, paras in sections:
        for text in _merge_floor(_pack(paras)):
            section = bc
            sm = _STATUTE_RE.match(text)
            if sm:
                marker = "s." + sm.group(1)
                section = (bc + _SEP + marker) if bc else marker
            result.append((section, text))
    return result


def canonical_document_rows(
    path: Path,
    corpus_root: Path,
    text: str | None = None,
) -> list[dict]:
    """Return the exact canonical rows :func:`build_index` inserts for one doc.

    This is the single read-only document-to-index projection.  Callers that need
    to attest index membership can compare these grounding-relevant fields without
    duplicating the chunker, metadata coercion, id format, or hash convention.
    ``text`` is an optional already-read document used by the builder; when omitted
    the markdown file is read once from disk.
    """
    root = Path(corpus_root).resolve()
    document = Path(path).resolve()
    raw = document.read_text(encoding="utf-8") if text is None else text
    meta = yaml.safe_load(dupaudit._frontmatter_of(raw)) or {}
    if not isinstance(meta, dict):
        meta = {}
    relpath = document.relative_to(root).as_posix()
    source_url = str(meta.get("url", "") or "")
    title = str(meta.get("title", "") or "")
    crawl_date = str(meta.get("crawl_date", "") or "")
    source_type = str(meta.get("source_type", "") or "")
    return [
        {
            "chunk_id": f"{relpath}#{ordinal:03d}",
            "relpath": relpath,
            "source_url": source_url,
            "title": title,
            "section": section,
            "crawl_date": crawl_date,
            "source_type": source_type,
            "chunk_sha": chunk_sha(chunk_text),
            "ordinal": ordinal,
            "text": chunk_text,
        }
        for ordinal, (section, chunk_text) in enumerate(
            chunk(dupaudit.body_of(raw))
        )
    ]


# --------------------------------------------------------------------------- #
# build_index — the idempotent, diffable rebuild (RETRIEVAL.md §2/§4/§6).
#
# Turns the clean live-doc corpus into the citable `chunks` table + the
# external-content `chunks_fts` index. Reuses the shipped corpus-reader
# primitives (`dupaudit.live_docs` / `body_of` / `_frontmatter_of`), assembles
# the five citation fields per chunk, mints the stable content-coordinate
# `chunk_id = relpath#ordinal`, stores a `chunk_sha` staleness fingerprint, and
# resyncs FTS with the single `'rebuild'` command. RET-01 SC1/SC2/SC4.
# --------------------------------------------------------------------------- #
def build_index(corpus: Path, db: Path) -> dict:
    """Build the FTS5 keyword index over the live corpus into *db*.

    Full DROP+rebuild for bulletproof idempotency (RETRIEVAL.md §6a): because
    ``dupaudit.live_docs`` walks a stable sorted ``rglob`` traversal and ``chunk``
    is a pure function, two runs over the same corpus yield byte-identical
    ``chunk_id``/``chunk_sha`` rows (SC1). Each chunk carries its five citation
    fields — ``relpath`` (filesystem), ``source_url`` / ``title`` / ``crawl_date``
    (front-matter, ``source_url`` read VERBATIM — never re-normalized), and
    ``section`` (heading breadcrumb derived by the chunker) — never invented (SC2).

    Fails loud via :func:`_probe_fts5` BEFORE any corpus read if the host SQLite
    lacks FTS5 (SC4). The only durable write is *db*; the DB holds corpus text +
    PII-free citation metadata only — no vectors/embeddings (SC4).

    Returns a deterministic result dict for the Plan 03 envelope (no timestamp, so
    the envelope stays diffable).
    """
    corpus_root = Path(corpus).resolve()
    con = sqlite3.connect(str(db))
    try:
        # Fail loud BEFORE any corpus read (RET-01 SC4); Plan 03's CLI maps the
        # FTS5Unavailable into a loud non-zero error envelope.
        _probe_fts5(con)

        # Full rebuild — drop the dependent FTS vtable first, then the tables.
        con.executescript(
            "DROP TABLE IF EXISTS chunks_fts;\n"
            "DROP TABLE IF EXISTS chunks;\n"
            "DROP TABLE IF EXISTS meta;"
        )
        con.executescript(CHUNKS_DDL)
        con.executescript(FTS_DDL)
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")

        # Enumerate EXACTLY the live-doc set — never re-walk the corpus ourselves.
        for path, text in dupaudit.live_docs(corpus_root):
            for row in canonical_document_rows(path, corpus_root, text):
                con.execute(
                    "INSERT INTO chunks(chunk_id, relpath, source_url, title, "
                    "section, crawl_date, source_type, chunk_sha, ordinal, text) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",                # parameter-bound, never f-string
                    tuple(row[field] for field in (
                        "chunk_id", "relpath", "source_url", "title",
                        "section", "crawl_date", "source_type", "chunk_sha",
                        "ordinal", "text",
                    )),
                )

        # Resync FTS from content — the single no-footgun command (no triggers,
        # no 'delete'); RETRIEVAL.md §6.
        con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        con.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            [
                ("schema_version", DB_SCHEMA_VERSION),
                ("tokenizer", TOKENIZER),
                ("corpus_root", str(corpus_root)),
            ],
        )
        con.commit()

        docs = con.execute("SELECT count(DISTINCT relpath) FROM chunks").fetchone()[0]
        chunks_n = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
        lo, hi = con.execute(
            "SELECT min(length(text)), max(length(text)) FROM chunks"
        ).fetchone()
        return {
            "db": str(db),
            "corpus": str(corpus_root),
            "docs": docs,
            "chunks": chunks_n,
            "min_text_len": lo if lo is not None else 0,
            "max_text_len": hi if hi is not None else 0,
            "tokenizer": TOKENIZER,
        }
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# search read side — the adversarial-query-safe escaper + the read-only BM25
# query over the *already-built* Phase-23 index (RETRIEVAL.md §5/§7). The whole
# attack surface of the phase is the untrusted `query`: it must NEVER reach
# SQLite as raw text — only the `_to_match()`-escaped string is bound to MATCH.
# search() is SELECT only; the index is built solely by build_index above.
# --------------------------------------------------------------------------- #


def _to_match(q: str) -> str | None:
    """Escape an untrusted query into a safe FTS5 ``MATCH`` string (RETRIEVAL.md §7 P2).

    Tokenize on ``\\w+`` (so parens, colons, apostrophes, quotes, and bare
    ``OR``/``AND``/``NEAR`` are dropped or demoted to literal terms) and re-quote
    every token as an FTS5 string literal joined by spaces (implicit AND). A
    crafted query (``R30(3)``, ``body:funds``, ``women's``, ``police OR certificates``)
    therefore can never raise an ``fts5: syntax error`` or inject an operator /
    column filter (RET-02 SC3). Returns ``None`` for an empty / all-punctuation
    query — the caller raises :class:`EmptyQuery` rather than run an empty MATCH.

    Pure like :func:`chunk_sha`: same query in -> same string out, no I/O. This is
    the ONLY value that ever feeds ``MATCH``; the raw query must never reach SQLite.
    """
    terms = re.findall(r"\w+", q, flags=re.UNICODE)
    if not terms:
        return None
    return " ".join('"' + t.replace('"', '""') + '"' for t in terms)


def search(db: Path, query: str, limit: int = 10, family: str | None = None) -> dict:
    """Run a read-only BM25 keyword query over the Phase-23 index at *db* (RETRIEVAL.md §5).

    Returns the citable envelope ``{query, db, count, hits}`` where each hit
    carries the stable ``chunk_id = relpath#ordinal`` content coordinate, the five
    citation fields (``source_url``, ``relpath``, ``title``, ``section``,
    ``crawl_date``), a non-empty :func:`snippet`-highlighted preview, and the raw
    negative ``bm25`` ``score``. Hits are sorted best-first (score ascending — more
    negative = better, P9): the score is passed through verbatim, never negated or
    re-sorted (RET-02 SC1).

    The untrusted *query* is escaped via :func:`_to_match` and bound to
    ``chunks_fts MATCH ?`` (parameter-bound, never f-string), so a crafted query
    (``R30(3)``, ``police OR certificates``, ``body:funds``, apostrophes) can never
    raise an ``fts5`` syntax error or inject an operator / column filter (RET-02
    SC3). An empty / all-punctuation query raises :class:`EmptyQuery` instead of
    running an empty MATCH. Optional *family* restricts hits to a ``relpath``
    prefix (``family + '/%'``); *limit* caps the result count (parameter-bound).

    Opened strictly read-only (``file:<db>?mode=ro``): SELECT only, never a write
    or a file-create, so a read can never mutate the byte-identical index (SC1) nor
    silently materialise a 0-byte DB for a missing path. NO write-DDL FTS5 probe runs
    on the read path (WR-01): the probe's ``CREATE/DROP VIRTUAL TABLE`` would mutate
    the index on the writable path and misreport a read-only/locked DB as "FTS5
    missing". A host whose SQLite lacks FTS5 — which could therefore never have built
    this index — makes the ``chunks_fts MATCH ?`` query below fail loud on its own,
    exactly the reasoning :func:`resolve` already relies on.
    """
    match = _to_match(query)
    if match is None:
        raise EmptyQuery(f"no searchable terms in query: {query!r}")

    # Read-only URI connect (WR-01/WR-03): forbids any write and never creates the
    # file, so a read can neither mutate the frozen/diffable index nor silently spawn
    # a 0-byte DB; a missing path raises an explicit OperationalError instead.
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row  # hits build as plain dicts by column name
    try:
        # No _probe_fts5 here (WR-01): a non-FTS5 DB could never have been built,
        # and a genuinely FTS5-less host makes `chunks_fts MATCH ?` fail loud on its
        # own — mirroring resolve(). The old probe ran write-DDL on this read path.

        # Query SQL from RETRIEVAL.md §5 (no in-repo analog). snippet() column
        # index 0 = the only FTS column `text`; use snippet() for the preview
        # (never the FTS3/4 offsets span function, which FTS5 lacks — P5). MATCH /
        # LIKE / LIMIT are ALL parameter-bound.
        sql = (
            "SELECT c.chunk_id, c.source_url, c.relpath, c.title, c.section, "
            "c.crawl_date, "
            "snippet(chunks_fts, 0, '\u27e6', '\u27e7', '\u2026', 12) AS snippet, "
            "bm25(chunks_fts) AS score "
            "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid "
            "WHERE chunks_fts MATCH ?"
        )
        params: list = [match]
        if family is not None:
            # Escape LIKE metacharacters so a family like 'pr_pdi' or '%' is matched
            # as a LITERAL path prefix, not a wildcard (WR-02). Without ESCAPE, '_'
            # matches any char (pr_pdi -> pr-pdi) and '%' disables the filter
            # entirely (cross-family leak). The trailing '/%' literal stays a real
            # wildcard so the rest of the relpath still matches.
            esc = family.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql += " AND c.relpath LIKE ? || '/%' ESCAPE '\\'"
            params.append(esc)
        sql += " ORDER BY bm25(chunks_fts) LIMIT ?"  # ascending: most relevant first
        params.append(limit)

        hits = [dict(row) for row in con.execute(sql, params).fetchall()]
        return {"query": query, "db": str(db), "count": len(hits), "hits": hits}
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# resolve read side — the citation resolver (RETRIEVAL.md §4). Given a stable
# `chunk_id` it returns the EXACT stored chunk text (the quotable span the
# Phase-25 grounding gate grounds on) + the five citation fields; an unknown id
# returns None (fail-closed). Reads ONLY the regular `chunks` table — no FTS5
# needed, so it stays cheap (the GND-01 gate hammers it) and SELECT-only.
# --------------------------------------------------------------------------- #


def resolve(db: Path, chunk_id: str) -> dict | None:
    """Resolve a stable ``chunk_id`` back to its exact stored chunk (RETRIEVAL.md §4).

    Returns the stable, PII-free citation dict the Phase-25 grounding gate
    (GND-01) consumes — EXACTLY ``{chunk_id, relpath, source_url, title, section,
    crawl_date, text}`` — where ``text`` is the stored ``chunks.text`` VERBATIM
    (the exact quotable span), NEVER a :func:`snippet`/highlight (snippet is
    search-display only — P5). An unknown ``chunk_id`` returns ``None``
    (fail-closed MISS — RET-02 SC2), never an exception: a miss is a normal
    fail-closed signal, not an execution error.

    Reads ONLY the regular ``chunks`` table via one parameter-bound
    ``WHERE chunk_id = ?`` lookup (``chunk_id`` is ``UNIQUE`` in the DDL, so this
    is an O(log n) indexed read → one row or none). The untrusted ``chunk_id`` is
    bound POSITIONALLY (never f-string); it is not routed through ``_to_match`` /
    ``MATCH``, so the FTS injection surface does not apply here. No FTS5 module is
    touched (no :func:`_probe_fts5`) — a DB lacking FTS5 could never have been
    built, so that concern lives entirely on the :func:`search` path. Opened
    strictly read-only (``file:<db>?mode=ro``): SELECT only, no mutation of the
    index — and, for a missing/typo'd path, an explicit ``OperationalError``
    (``unable to open database file``) rather than a side-effecting 0-byte
    file-create + generic ``no such table`` (WR-03). A genuine *miss* (unknown id
    in a real index) still returns ``None``, never raises.
    """
    # Read-only URI connect (WR-03): the Phase-25 grounding gate calls resolve()
    # directly; a missing path must fail explicitly without creating a 0-byte DB,
    # and the read path must never be able to write.
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT chunk_id, relpath, source_url, title, section, crawl_date, "
            "chunk_sha, text FROM chunks WHERE chunk_id = ?",   # UNIQUE(chunk_id) → 1 row or none
            (chunk_id,),                                         # parameter-bound, never f-string
        ).fetchone()
    finally:
        con.close()

    if row is None:
        return None                       # MISS → fail-closed (RET-02 SC2)

    # Staleness/tamper guard (RETRIEVAL.md §4): recompute the fingerprint over the
    # STORED text and compare to the stored chunk_sha. A mismatch means the row has
    # drifted from what was indexed (corrupted / tampered / re-crawled-then-edited)
    # → treat it exactly like a miss. An unknown OR a stale id both yield "not
    # found" — a normal fail-closed signal, NOT an exception (RET-02 SC2 / P-anti).
    if chunk_sha(row["text"]) != row["chunk_sha"]:
        return None                       # DRIFT → fail-closed (stale / tampered row)

    # The stable, PII-free citation contract — the internal `chunk_sha` is NOT
    # exposed (it is an integrity field, not part of the citation contract the
    # grounding gate consumes). Return `text` VERBATIM.
    return {
        "chunk_id": row["chunk_id"],
        "relpath": row["relpath"],
        "source_url": row["source_url"],
        "title": row["title"],
        "section": row["section"],
        "crawl_date": row["crawl_date"],
        "text": row["text"],
    }


def relpath_sections(db: Path, relpath: str) -> list[dict]:
    """List the ``(chunk_id, ordinal, section)`` table-of-contents for *relpath*.

    A read-only, parameter-bound *structure* read over the regular ``chunks``
    table for ONE document, returned in ``ordinal`` order. It exposes ONLY the
    citation coordinates + heading breadcrumb (deliberately NOT ``text`` and NOT
    ``chunk_sha``): it is a table-of-contents, NOT a second quotable-content /
    grounding path — every quotable span a caller cites still flows through
    :func:`resolve` (which re-validates ``chunk_sha`` and returns the verbatim
    text). Section-aware callers use this to map heading breadcrumbs (e.g. a
    ``… › Main duties`` continuation that overflowed onto a second chunk) to
    ``chunk_id``s WITHOUT positional guessing, then :func:`resolve` each id.

    Opened strictly read-only (``file:<db>?mode=ro``): SELECT only, never a write
    and never a 0-byte file-create for a missing/typo'd path (an explicit
    ``OperationalError`` is raised instead, mirroring :func:`resolve`). ``relpath``
    is bound POSITIONALLY (never an f-string) and is not routed through
    ``_to_match`` / ``MATCH``, so there is no FTS injection surface. An absent
    document yields an empty list (fail-closed signal, never an exception).
    """
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT chunk_id, ordinal, section FROM chunks "
            "WHERE relpath = ? ORDER BY ordinal",   # param-bound, never f-string
            (relpath,),
        ).fetchall()
    finally:
        con.close()
    return [
        {"chunk_id": r["chunk_id"], "ordinal": r["ordinal"],
         "section": r["section"]}
        for r in rows
    ]


def canonical_rows_for_relpath(db: Path, relpath: str) -> list[dict]:
    """Read every canonical field stored for *relpath* in insertion order.

    The internal ``id`` is used only to preserve the builder's insertion order and
    is never returned or compared.  This allows provenance checks to detect extra,
    missing, reordered, or replaced rows while ignoring SQLite implementation
    details that are not part of the grounding contract.
    """
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT chunk_id, relpath, source_url, title, section, crawl_date, "
            "source_type, chunk_sha, ordinal, text FROM chunks "
            "WHERE relpath = ? ORDER BY id",
            (relpath,),
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]
