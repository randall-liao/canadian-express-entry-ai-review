"""Offline test suite for the FTS5 keyword-index builder (Phase 23 — RET-01).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO crawl4ai, NO network, NO
browser (per the AGENTS.md / ``crawler/tests/test_dupaudit.py`` convention).
Every test drives synthetic, in-process inputs; the pure pieces built in Plan
01 (the FTS5 probe + the deterministic chunker) need no tempdir corpus. Run
from the repo root::

    poetry run python -m pytest crawler/tests/test_searchindex.py -q
    poetry run python -m unittest crawler.tests.test_searchindex -v

Classes (Plan 01 surface):

    TestFtsProbe    — RET-01 SC4: fail-loud FTS5 feature-detection + no residue
    TestChunkBounds — RET-01 SC3: tiny -> 1 chunk, no unbounded legislation chunk
    TestChunkSection— RET-01 SC2: heading breadcrumb + ``**9.4**`` statutory marker

Classes (Plan 02 surface — driven against a synthetic tempdir corpus + real DB):

    TestCitationFields — RET-01 SC1/SC2/SC4: builds over ``dupaudit.live_docs``;
                         five citation fields per chunk (``source_url`` verbatim);
                         ``chunk_id = relpath#NNN`` content coordinates; no vectors
    TestIdempotent     — RET-01 SC1/SC3: byte-identical ``chunk_id``/``chunk_sha`` on
                         rebuild; FTS ``integrity-check`` passes; ``max_text_len`` bound
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from crawler import cli, searchindex


# --------------------------------------------------------------------------- #
# A connection stub whose ``execute`` mimics a SQLite build WITHOUT FTS5 — the
# exotic-user-Python case the probe must fail loud on (RETRIEVAL.md §7 P1).
# --------------------------------------------------------------------------- #
class _NoFtsConnection:
    def execute(self, sql: str):  # noqa: D401 - test stub
        raise sqlite3.OperationalError("no such module: fts5")


# --------------------------------------------------------------------------- #
# TestFtsProbe — RET-01 SC4 (fail loud if the host SQLite lacks FTS5)
# --------------------------------------------------------------------------- #
class TestFtsProbe(unittest.TestCase):
    def test_probe_passes_on_real_connection(self) -> None:
        """A real in-memory SQLite (FTS5 compiled in here) probes without error."""
        con = sqlite3.connect(":memory:")
        try:
            self.assertIsNone(searchindex._probe_fts5(con))
        finally:
            con.close()

    def test_probe_fails_loud_when_fts5_absent(self) -> None:
        """Missing FTS5 -> FTS5Unavailable with an actionable, FTS5-naming message."""
        with self.assertRaises(searchindex.FTS5Unavailable) as ctx:
            searchindex._probe_fts5(_NoFtsConnection())
        msg = str(ctx.exception)
        self.assertIn("FTS5", msg)
        # Names the concrete remediation, not just "it broke".
        self.assertIn("ENABLE_FTS5", msg)

    def test_probe_leaves_no_residue(self) -> None:
        """After a happy-path probe, no ``_probe`` table remains in sqlite_master."""
        con = sqlite3.connect(":memory:")
        try:
            searchindex._probe_fts5(con)
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE name = '_probe'"
            ).fetchall()
            self.assertEqual(rows, [])
        finally:
            con.close()

    def test_chunk_constants_are_sane(self) -> None:
        """Tunables are positive ints with MIN < MAX; MIN echoes MIN_CONTENT_CHARS."""
        self.assertIsInstance(searchindex.MIN_CHUNK_CHARS, int)
        self.assertIsInstance(searchindex.MAX_CHUNK_CHARS, int)
        self.assertGreater(searchindex.MIN_CHUNK_CHARS, 0)
        self.assertLess(searchindex.MIN_CHUNK_CHARS, searchindex.MAX_CHUNK_CHARS)
        # Merge floor echoes the crawler's MIN_CONTENT_CHARS = 200 precedent.
        self.assertGreaterEqual(searchindex.MIN_CHUNK_CHARS, 200)
        self.assertEqual(searchindex.TOKENIZER, "porter unicode61")

    def test_ddl_constants_use_external_content_fts5(self) -> None:
        """The FTS DDL is an external-content vtable (never contentless)."""
        self.assertIn("VIRTUAL TABLE", searchindex.FTS_DDL)
        self.assertIn("fts5", searchindex.FTS_DDL)
        self.assertIn("content='chunks'", searchindex.FTS_DDL)
        self.assertIn("porter unicode61", searchindex.FTS_DDL)
        self.assertIn("chunk_id", searchindex.CHUNKS_DDL)
        self.assertIn("chunk_sha", searchindex.CHUNKS_DDL)

    def test_ddl_constants_build_a_working_schema(self) -> None:
        """CHUNKS_DDL + FTS_DDL execute cleanly and yield an FTS index over text."""
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(searchindex.CHUNKS_DDL)
            con.executescript(searchindex.FTS_DDL)
            con.execute(
                "INSERT INTO chunks(chunk_id, relpath, source_url, title, "
                "section, crawl_date, source_type, chunk_sha, ordinal, text) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("a.md#000", "a.md", "https://x", "T", "", "", "", "abc", 0,
                 "police certificate required"),
            )
            con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
            hit = con.execute(
                "SELECT chunk_id FROM chunks WHERE id IN "
                "(SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'police')"
            ).fetchone()
            self.assertEqual(hit[0], "a.md#000")
        finally:
            con.close()


SEP = searchindex._SEP  # heading-breadcrumb separator (U+203A)


def _filler(n: int) -> str:
    """A deterministic, space-bearing filler paragraph of exactly *n* chars."""
    base = (
        "Police certificates and medical examinations are part of the "
        "permanent residence requirements that applicants must satisfy. "
    )
    return (base * ((n // len(base)) + 1))[:n]


# A small whole doc (no headings) — the `definitions/`-style citation granularity.
TINY_BODY = "\n\n".join(
    [
        "Permanent residence applicants must provide police certificates for "
        "every country where they have lived for six months or more since the "
        "age of eighteen, without exception.",
        "Each certificate must be issued by the relevant national authority and "
        "must accompany the application at the time it is submitted to the "
        "department for processing.",
        "Applicants should request certificates early, because some countries "
        "take several weeks to process and return them by mail to the applicant.",
    ]
)

# One ~5,000-char paragraph (no blank lines) — the legislation FullText worst case.
LONG_PARA = (
    ". ".join(
        f"Section requirements about police certificates and biometrics apply "
        f"to applicants in case number {i:03d}"
        for i in range(60)
    )
    + "."
)

# A heading-stacked doc — each paragraph carries its running breadcrumb.
HEADING_BODY = (
    "# Act\n\n"
    "This Act governs the requirements for permanent residence and the "
    "examination of applicants by officers of the department.\n\n"
    "## DIVISION 1\n\n"
    "Division 1 sets out the documentary requirements an applicant must meet "
    "before an application is placed into processing.\n\n"
    "### Heading\n\n"
    "This heading describes the police certificate obligations that apply to "
    "each applicant aged eighteen years or older.\n"
)

# A statutory marker at the chunk head (not a markdown heading).
STATUTE_BODY = (
    "# Immigration and Refugee Protection Act\n\n"
    "## DIVISION 9 \u2014 Examination\n\n"
    "**9.4** Despite any other provision of this Act, an officer may examine an "
    "applicant to determine whether the documentary requirements have been met "
    "at the time of the application.\n"
)


# --------------------------------------------------------------------------- #
# TestChunkBounds — RET-01 SC3 (tiny -> 1 chunk; no unbounded legislation chunk)
# --------------------------------------------------------------------------- #
class TestChunkBounds(unittest.TestCase):
    def test_tiny_doc_is_one_whole_doc_chunk(self) -> None:
        chunks = searchindex.chunk(TINY_BODY)
        self.assertEqual(len(chunks), 1)
        section, text = chunks[0]
        self.assertEqual(section, "")          # no headings -> empty breadcrumb
        self.assertEqual(text, TINY_BODY)      # the whole body, verbatim

    def test_long_paragraph_is_split_and_never_unbounded(self) -> None:
        self.assertGreater(len(LONG_PARA), 4000)  # the input really is overlong
        chunks = searchindex.chunk(LONG_PARA)
        self.assertGreater(len(chunks), 1)         # hard-split into several chunks
        self.assertLessEqual(
            max(len(t) for _, t in chunks), searchindex.MAX_CHUNK_CHARS
        )

    def test_merge_floor_absorbs_trailing_fragment(self) -> None:
        # Two packed chunks + a tiny trailing fragment (< MIN) that must merge
        # into the previous chunk of the same section (not ship as its own chunk).
        body = "\n\n".join([_filler(1100), _filler(1100), _filler(100)])
        chunks = searchindex.chunk(body)
        self.assertEqual(len(chunks), 2)  # 3rd fragment merged, not emitted alone
        for _, text in chunks:
            self.assertGreaterEqual(len(text), searchindex.MIN_CHUNK_CHARS)
            self.assertLessEqual(len(text), searchindex.MAX_CHUNK_CHARS)

    def test_chunk_is_deterministic(self) -> None:
        for body in (TINY_BODY, LONG_PARA, HEADING_BODY, STATUTE_BODY):
            self.assertEqual(searchindex.chunk(body), searchindex.chunk(body))


# --------------------------------------------------------------------------- #
# TestChunkSection — RET-01 SC2 (heading breadcrumb + statutory marker capture)
# --------------------------------------------------------------------------- #
class TestChunkSection(unittest.TestCase):
    def test_heading_breadcrumb_is_the_running_stack(self) -> None:
        sections = [s for s, _ in searchindex.chunk(HEADING_BODY)]
        self.assertEqual(
            sections,
            [
                "Act",
                f"Act{SEP}DIVISION 1",
                f"Act{SEP}DIVISION 1{SEP}Heading",
            ],
        )

    def test_statutory_marker_is_appended_to_section(self) -> None:
        chunks = searchindex.chunk(STATUTE_BODY)
        self.assertEqual(len(chunks), 1)
        section, text = chunks[0]
        self.assertTrue(text.startswith("**9.4**"))
        self.assertTrue(
            section.endswith(f"{SEP}s.9.4"),
            msg=f"section did not capture the statutory marker: {section!r}",
        )

    def test_chunk_is_deterministic_for_sections(self) -> None:
        self.assertEqual(
            searchindex.chunk(HEADING_BODY), searchindex.chunk(HEADING_BODY)
        )


# --------------------------------------------------------------------------- #
# Synthetic tempdir-corpus fixtures for the build_index integration tests
# (Plan 02). Mirrors test_dupaudit.py's `_doc_text` (97-106) + `_CorpusCase`
# (276-283): every test builds a fresh corpus under a TemporaryDirectory and
# writes the DB INSIDE that same tempdir — never under the real `corpus/`.
# --------------------------------------------------------------------------- #

# A planted doc with citation fields whose `url` carries a query + fragment, so a
# byte-for-byte assert proves build_index reads `source_url` VERBATIM (no
# normalize_url re-normalization — RETRIEVAL.md §1 / §7 anti-pattern).
TINY_URL = "https://www.canada.ca/en/tiny.html?wbdisable=true#frag"
TINY_TITLE = "Tiny PR doc"
TINY_CRAWL_DATE = "2026-01-01T00:00:00Z"

# The four relpaths the 742-filter MUST yield for the synthetic corpus below.
_LIVE_INDEX_RELPATHS = {
    "pr-pdi/tiny.md",
    "pr-pdi/headings.md",
    "legislation-irpa/statute.md",
    "legislation-irpr/longpara.md",
}


def _doc_text(
    url: str, crawl_date: str, title: str, body: str, source_type: str = "guidance"
) -> str:
    """Compose a corpus .md file: YAML frontmatter block + body.

    Copied from ``test_dupaudit.py:97-106`` with an extra ``source_type`` key (the
    fifth facet build_index stores); ``safe_load`` parses it back unchanged.
    """
    return (
        "---\n"
        f'url: "{url}"\n'
        f'title: "{title}"\n'
        f'source_type: "{source_type}"\n'
        f'crawl_date: "{crawl_date}"\n'
        "---\n\n"
        f"{body}"
    )


def _make_index_corpus(tmp: Path) -> Path:
    """Build a synthetic live corpus under *tmp* and return its root.

    Plants exactly four LIVE docs the chunker exercises end-to-end:
      (1) a tiny no-heading doc      -> a single whole-doc chunk (known citation
                                        fields; url with query+fragment)
      (2) a multi-heading doc        -> breadcrumb sections
      (3) a legislation-style doc    -> inline ``**9.4**`` statutory anchor
      (4) an overlong single-paragraph doc (~6 KB) -> hard-split path / max bound
    plus NOISE the ``dupaudit.live_docs`` 742-filter must EXCLUDE (``REPORT.md``,
    ``completeness/*.live.md``, ``_dropped/*``, a frontmatterless ``.md``) — proving
    build_index never re-walks the corpus itself.
    """
    root = tmp / "corpus"
    for fam in ("pr-pdi", "legislation-irpa", "legislation-irpr"):
        (root / fam).mkdir(parents=True, exist_ok=True)

    # (1) tiny no-heading doc -> 1 whole-doc chunk; verbatim-url citation fields.
    (root / "pr-pdi" / "tiny.md").write_text(
        _doc_text(TINY_URL, TINY_CRAWL_DATE, TINY_TITLE, TINY_BODY,
                  source_type="guidance"),
        encoding="utf-8")

    # (2) multi-heading doc -> running heading-stack breadcrumb sections.
    (root / "pr-pdi" / "headings.md").write_text(
        _doc_text("https://www.canada.ca/en/headings.html", "2026-02-02T00:00:00Z",
                  "Headings doc", HEADING_BODY, source_type="guidance"),
        encoding="utf-8")

    # (3) legislation-style doc with an inline **9.4** statutory marker.
    (root / "legislation-irpa" / "statute.md").write_text(
        _doc_text("https://laws-lois.justice.gc.ca/eng/acts/i-2.5/FullText.html",
                  "2026-03-03T00:00:00Z",
                  "Immigration and Refugee Protection Act",
                  STATUTE_BODY, source_type="legislation"),
        encoding="utf-8")

    # (4) overlong single-paragraph doc -> exercises the hard-split + max bound.
    (root / "legislation-irpr" / "longpara.md").write_text(
        _doc_text(
            "https://laws-lois.justice.gc.ca/eng/regulations/sor-2002-227/FullText.html",
            "2026-04-04T00:00:00Z",
            "Immigration and Refugee Protection Regulations",
            LONG_PARA, source_type="legislation"),
        encoding="utf-8")

    # NOISE the live-doc filter MUST drop (none of these may appear in `chunks`).
    (root / "pr-pdi" / "REPORT.md").write_text(
        "# Family report\nGenerated aggregate — not a corpus doc.\n", encoding="utf-8")
    (root / "pr-pdi" / "completeness").mkdir(exist_ok=True)
    (root / "pr-pdi" / "completeness" / "sample.live.md").write_text(
        _doc_text("https://www.canada.ca/en/live.html", "2026-05-05T00:00:00Z",
                  "Live capture", "Ground-truth re-fetch capture.\n"),
        encoding="utf-8")
    (root / "legislation-irpa" / "_dropped").mkdir(exist_ok=True)
    (root / "legislation-irpa" / "_dropped" / "old.md").write_text(
        _doc_text("https://www.canada.ca/en/dropped.html", "2026-05-06T00:00:00Z",
                  "Dropped", "Quarantined dropped document.\n"), encoding="utf-8")
    (root / "legislation-irpr" / "plain.md").write_text(
        "Just a plain markdown artifact with no YAML frontmatter at all.\n",
        encoding="utf-8")

    return root


class _IndexCase(unittest.TestCase):
    """Base case: a fresh synthetic corpus + a db path INSIDE the same tempdir."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
        # The DB lives in the tempdir — NEVER under the real git-ignored corpus/.
        self.db = Path(self._tmp.name) / "index.db"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db))


# --------------------------------------------------------------------------- #
# TestCitationFields — RET-01 SC1/SC2/SC4 (live-doc set, five fields, chunk_id,
# no vectors). Drives the REAL `searchindex.build_index` and asserts on the DB.
# --------------------------------------------------------------------------- #
class TestCitationFields(_IndexCase):
    def test_indexes_exactly_the_live_doc_set(self) -> None:
        """Builds over `dupaudit.live_docs` (N=4); chunks >= docs; result mirrors DB."""
        result = searchindex.build_index(self.root, self.db)
        con = self._connect()
        try:
            distinct = con.execute(
                "SELECT count(DISTINCT relpath) FROM chunks").fetchone()[0]
            total = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(distinct, len(_LIVE_INDEX_RELPATHS))
        self.assertGreaterEqual(total, distinct)   # tiny docs -> 1 chunk each
        # The returned dict is the source of truth for the Plan 03 envelope.
        self.assertEqual(result["docs"], distinct)
        self.assertEqual(result["chunks"], total)
        self.assertEqual(result["tokenizer"], searchindex.TOKENIZER)
        self.assertEqual(result["corpus"], str(self.root.resolve()))
        self.assertEqual(result["db"], str(self.db))

    def test_noise_files_are_not_indexed(self) -> None:
        """`live_docs` filters _dropped/, completeness/, REPORT.md, frontmatterless."""
        searchindex.build_index(self.root, self.db)
        con = self._connect()
        try:
            relpaths = {r[0] for r in con.execute(
                "SELECT DISTINCT relpath FROM chunks")}
        finally:
            con.close()
        self.assertEqual(relpaths, _LIVE_INDEX_RELPATHS)
        for noise in ("REPORT", "completeness", "_dropped", "plain", ".live."):
            self.assertFalse(
                any(noise in rp for rp in relpaths),
                msg=f"noise marker {noise!r} leaked into the index: {relpaths}")

    def test_five_citation_fields_match_frontmatter(self) -> None:
        """The planted tiny doc's row carries all five fields exactly as planted."""
        searchindex.build_index(self.root, self.db)
        con = self._connect()
        try:
            row = con.execute(
                "SELECT relpath, source_url, title, section, crawl_date, source_type "
                "FROM chunks WHERE relpath = 'pr-pdi/tiny.md'"
            ).fetchone()
        finally:
            con.close()
        relpath, source_url, title, section, crawl_date, source_type = row
        self.assertEqual(relpath, "pr-pdi/tiny.md")
        self.assertEqual(source_url, TINY_URL)        # exact, never invented
        self.assertEqual(title, TINY_TITLE)
        self.assertEqual(crawl_date, TINY_CRAWL_DATE)
        self.assertEqual(source_type, "guidance")
        self.assertEqual(section, "")                 # no-heading doc -> empty breadcrumb

    def test_source_url_is_read_verbatim_not_renormalized(self) -> None:
        """`source_url` keeps the query + fragment — no normalize_url was called."""
        searchindex.build_index(self.root, self.db)
        con = self._connect()
        try:
            url = con.execute(
                "SELECT source_url FROM chunks WHERE relpath='pr-pdi/tiny.md' LIMIT 1"
            ).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(url, TINY_URL)
        self.assertIn("?wbdisable=true", url)   # query NOT stripped
        self.assertIn("#frag", url)             # fragment NOT stripped

    def test_chunk_id_is_content_coordinates_not_rowid(self) -> None:
        """Every chunk_id == relpath#NNN (>=3 digits), UNIQUE, and NOT the rowid."""
        searchindex.build_index(self.root, self.db)
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT id, chunk_id, relpath, ordinal FROM chunks").fetchall()
        finally:
            con.close()
        chunk_ids = [r[1] for r in rows]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)))   # UNIQUE
        for rowid, chunk_id, relpath, ordinal in rows:
            # `:03d` is a min-width FLOOR, not a cap -> match 3-OR-MORE digits.
            self.assertRegex(chunk_id, rf"^{re.escape(relpath)}#\d{{3,}}$")
            self.assertEqual(chunk_id, f"{relpath}#{ordinal:03d}")
            self.assertNotEqual(chunk_id, str(rowid))           # not the integer rowid

    def test_db_has_no_vectors_table(self) -> None:
        """The DB holds ONLY chunks + chunks_fts* (FTS shadow) + meta — no vectors."""
        searchindex.build_index(self.root, self.db)
        con = self._connect()
        try:
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
        self.assertIn("chunks", tables)
        self.assertIn("meta", tables)
        self.assertTrue(any(t.startswith("chunks_fts") for t in tables))
        for t in tables:
            self.assertTrue(
                t == "chunks" or t == "meta" or t.startswith("chunks_fts"),
                msg=f"unexpected table in the index DB: {t!r}")
            self.assertNotIn("vec", t.lower())
            self.assertNotIn("embed", t.lower())


# --------------------------------------------------------------------------- #
# TestIdempotent — RET-01 SC1/SC3 (byte-identical rebuild + FTS integrity +
# size bounds). Adds NO production code: idempotency is structurally guaranteed
# by build_index's full DROP+rebuild over the sorted `dupaudit.live_docs`
# traversal and the pure `chunk()`; these are the executable proof.
# --------------------------------------------------------------------------- #
class TestIdempotent(_IndexCase):
    def _chunk_ids(self) -> list[str]:
        con = self._connect()
        try:
            return [r[0] for r in con.execute(
                "SELECT chunk_id FROM chunks ORDER BY chunk_id")]
        finally:
            con.close()

    def _id_sha_pairs(self) -> list[tuple[str, str]]:
        con = self._connect()
        try:
            return con.execute(
                "SELECT chunk_id, chunk_sha FROM chunks ORDER BY chunk_id"
            ).fetchall()
        finally:
            con.close()

    def test_rebuild_yields_byte_identical_chunk_ids(self) -> None:
        """Two builds into the same db -> identical ordered chunk_id lists."""
        r1 = searchindex.build_index(self.root, self.db)
        ids1 = self._chunk_ids()
        r2 = searchindex.build_index(self.root, self.db)   # rebuild into the SAME db
        ids2 = self._chunk_ids()
        self.assertEqual(ids1, ids2)                       # byte-identical list
        self.assertEqual(
            hashlib.sha1("\n".join(ids1).encode("utf-8")).hexdigest(),
            hashlib.sha1("\n".join(ids2).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(r1["chunks"], r2["chunks"])       # row count unchanged
        self.assertEqual(len(ids1), r1["chunks"])

    def test_chunk_sha_pairs_are_stable_across_rebuilds(self) -> None:
        """The ordered (chunk_id, chunk_sha) pairs are reproducible across builds."""
        searchindex.build_index(self.root, self.db)
        pairs1 = self._id_sha_pairs()
        searchindex.build_index(self.root, self.db)
        pairs2 = self._id_sha_pairs()
        self.assertEqual(pairs1, pairs2)

    def test_fts_integrity_check_passes(self) -> None:
        """The external-content FTS index matches `chunks` content (no exception)."""
        searchindex.build_index(self.root, self.db)
        con = self._connect()
        try:
            # 'integrity-check' raises sqlite3.DatabaseError if the FTS index and
            # the content table disagree; reaching the next line == it matched.
            con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")
        finally:
            con.close()

    def test_result_bounds_are_within_max_chunk_chars(self) -> None:
        """max_text_len <= MAX_CHUNK_CHARS and chunks >= docs >= 1 (overlong split)."""
        result = searchindex.build_index(self.root, self.db)
        self.assertLessEqual(result["max_text_len"], searchindex.MAX_CHUNK_CHARS)
        self.assertGreaterEqual(result["chunks"], result["docs"])
        self.assertGreaterEqual(result["docs"], 1)
        # The planted ~6 KB single-paragraph doc must have forced a multi-chunk
        # hard-split, so the corpus really exercises the bound (not all 1-chunk docs).
        self.assertGreater(result["chunks"], result["docs"])


# --------------------------------------------------------------------------- #
# TestIndexCli — RET-01 SC1/SC4: drive the REAL `index` verb end-to-end through
# `cli.main` and assert the one-line CONTRACT envelope (ok/command/schema_version),
# the invalid_input / exit-2 path, and stdout purity (RETRIEVAL.md §7 P11). The DB
# always lives INSIDE the tempdir (via `_IndexCase`), never under the real corpus/.
# --------------------------------------------------------------------------- #

class TestIndexCli(_IndexCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        """Run cli.main(argv) capturing (exit_code, stdout, stderr).

        Mirrors test_dupaudit.py:523-527 — redirect both streams to StringIO so a
        test can assert stdout is exactly one JSON object and human text is on stderr.
        """
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_index_verb_emits_one_ok_envelope(self) -> None:
        """`--json index <corpus> --db <tempdir>` → one ok:true index envelope, exit 0."""
        rc, out, _ = self._run(
            ["--json", "index", str(self.root), "--db", str(self.db)])
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("\n"), 1)            # exactly ONE JSON line
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertEqual(obj["command"], "index")
        self.assertEqual(obj["schema_version"], "1.0")  # additive change: unchanged
        self.assertGreaterEqual(obj["result"]["chunks"], obj["result"]["docs"])
        self.assertGreaterEqual(obj["result"]["docs"], 1)
        self.assertTrue(self.db.exists())               # wrote the db in the tempdir

    def test_missing_corpus_dir_is_invalid_input_exit_2(self) -> None:
        """A non-directory corpus → ok:false / invalid_input envelope + exit 2 (SC4)."""
        rc, out, _ = self._run(
            ["--json", "index", "/no/such/dir-xyz-23-03",
             "--db", str(Path(self._tmp.name) / "unused.db")])
        self.assertEqual(rc, contract_exit_invalid_input())
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")
        self.assertIsNone(obj["result"])

    def test_json_stdout_is_pure_one_object(self) -> None:
        """stdout carries EXACTLY one parseable JSON object (RETRIEVAL.md §7 P11)."""
        rc, out, err = self._run(
            ["--json", "index", str(self.root), "--db", str(self.db)])
        self.assertEqual(rc, 0)
        json.loads(out)                                  # must not raise
        self.assertEqual(out.count("\n"), 1)
        self.assertNotIn("{", err)                       # no JSON leaked to stderr

    def test_non_json_summary_goes_to_stderr_not_stdout(self) -> None:
        """Non-json human summary is written to STDERR; stdout stays clean (P11)."""
        rc, out, err = self._run(["index", str(self.root), "--db", str(self.db)])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")                        # nothing on stdout
        self.assertIn("chunks", err)                     # docs/chunks summary on stderr


def contract_exit_invalid_input() -> int:
    """The documented invalid_input exit code (2), sourced from the contract module."""
    from crawler import contract
    return contract.EXIT_INVALID_INPUT


# --------------------------------------------------------------------------- #
# TestToMatch — RET-02 SC3: the adversarial-query FTS5 escaper (pure, no DB).
# A crafted query must never reach SQLite as raw text: every `\w+` token is
# re-quoted as a literal, parens/colons/apostrophes are dropped, bare OR/AND/NEAR
# are literal terms (no operator/column-filter injection), and an empty /
# all-punctuation query yields None (the caller raises EmptyQuery).
# --------------------------------------------------------------------------- #
class TestToMatch(unittest.TestCase):
    def test_section_code_tokens_are_separate_quoted_literals(self) -> None:
        """R30(3) -> R30 and 3 become separate quoted literals; parens dropped."""
        out = searchindex._to_match("R30(3)")
        self.assertIn('"R30"', out)
        self.assertIn('"3"', out)
        self.assertNotIn("(", out)
        self.assertNotIn(")", out)

    def test_bare_boolean_words_are_literal_terms(self) -> None:
        """`police OR certificates` -> all three quoted; OR is a LITERAL, not an op."""
        out = searchindex._to_match("police OR certificates")
        self.assertIn('"police"', out)
        self.assertIn('"OR"', out)
        self.assertIn('"certificates"', out)

    def test_colon_is_dropped_no_column_filter(self) -> None:
        """`body:funds` -> tokens body, funds; the column-filter colon is gone."""
        out = searchindex._to_match("body:funds")
        self.assertIn('"body"', out)
        self.assertIn('"funds"', out)
        self.assertNotIn(":", out)

    def test_apostrophe_is_dropped(self) -> None:
        """`women's certificate` -> women, s, certificate; the apostrophe never lands."""
        out = searchindex._to_match("women's certificate")
        self.assertIn('"women"', out)
        self.assertIn('"s"', out)
        self.assertIn('"certificate"', out)
        self.assertNotIn("'", out)

    def test_every_term_is_a_double_quoted_literal_no_bare_punct(self) -> None:
        """The whole output is a space-joined run of double-quoted `\\w+` literals."""
        out = searchindex._to_match("R30(3) body:funds women's police OR certificates")
        self.assertRegex(out, r'^"\w+"(?: "\w+")*$')
        for ch in "()[]:'!":
            self.assertNotIn(ch, out)

    def test_empty_and_all_punctuation_return_none(self) -> None:
        """Empty / whitespace / all-punct queries yield None (no empty MATCH)."""
        self.assertIsNone(searchindex._to_match(""))
        self.assertIsNone(searchindex._to_match("   "))
        self.assertIsNone(searchindex._to_match("()[]:!"))


# --------------------------------------------------------------------------- #
# TestSearch — RET-02 SC1/SC3: the read-only BM25 query over the built synthetic
# 4-doc index. Builds once via build_index in setUp, then drives search() and
# asserts the citable envelope, BM25-ascending negative scores, the eight hit
# fields incl. a highlighted snippet + relpath#NNN chunk_id, adversarial-query
# safety, EmptyQuery on empty/all-punct, the --family relpath filter, and that
# search performs NO mutation (read-only over the Phase-23 DB).
# --------------------------------------------------------------------------- #
class TestSearch(_IndexCase):
    _HIT_FIELDS = {
        "chunk_id", "source_url", "relpath", "title", "section",
        "crawl_date", "snippet", "score",
    }

    def setUp(self) -> None:
        super().setUp()
        # Build the index once against the synthetic 4-doc corpus (NOT real corpus/).
        searchindex.build_index(self.root, self.db)

    def test_returns_citable_envelope_with_hits(self) -> None:
        res = searchindex.search(self.db, "police certificate")
        self.assertEqual(set(res), {"query", "db", "count", "hits"})
        self.assertEqual(res["query"], "police certificate")
        self.assertEqual(res["db"], str(self.db))
        self.assertEqual(res["count"], len(res["hits"]))
        self.assertGreaterEqual(res["count"], 1)

    def test_hits_are_bm25_ascending_and_negative(self) -> None:
        scores = [h["score"] for h in searchindex.search(self.db, "police certificate")["hits"]]
        self.assertEqual(scores, sorted(scores))      # best-first = score ascending
        self.assertTrue(all(s < 0 for s in scores))   # bm25 sign (P9): never negated

    def test_each_hit_has_eight_fields_and_content_chunk_id(self) -> None:
        for h in searchindex.search(self.db, "police certificate")["hits"]:
            self.assertEqual(set(h), self._HIT_FIELDS)
            # content coordinate relpath#NNN — NOT the integer rowid (P8).
            self.assertRegex(h["chunk_id"], rf"^{re.escape(h['relpath'])}#\d{{3}}$")
            self.assertIsInstance(h["snippet"], str)
            self.assertTrue(h["snippet"])             # non-empty preview

    def test_top_hit_snippet_carries_a_highlight_marker(self) -> None:
        res = searchindex.search(self.db, "police certificate")
        self.assertIn("\u27e6", res["hits"][0]["snippet"])   # ⟦ open marker

    def test_returned_chunk_id_resolves_in_chunks(self) -> None:
        """Round-trip readiness: every returned chunk_id exists in `chunks`."""
        res = searchindex.search(self.db, "police certificate")
        con = self._connect()
        try:
            for h in res["hits"]:
                row = con.execute(
                    "SELECT 1 FROM chunks WHERE chunk_id = ?", (h["chunk_id"],)
                ).fetchone()
                self.assertIsNotNone(row, msg=f"unresolvable chunk_id: {h['chunk_id']}")
        finally:
            con.close()

    def test_adversarial_queries_never_raise(self) -> None:
        for q in ("R30(3)", "police OR certificates", "body:funds", "women's certificate"):
            res = searchindex.search(self.db, q)      # must NOT raise an fts5 error
            self.assertEqual(set(res), {"query", "db", "count", "hits"})

    def test_empty_and_all_punct_raise_emptyquery(self) -> None:
        for q in ("", "   ", "()!:"):
            with self.assertRaises(searchindex.EmptyQuery):
                searchindex.search(self.db, q)

    def test_family_filter_restricts_to_relpath_prefix(self) -> None:
        res = searchindex.search(self.db, "police certificate", family="pr-pdi")
        self.assertGreaterEqual(res["count"], 1)
        for h in res["hits"]:
            self.assertTrue(h["relpath"].startswith("pr-pdi/"),
                            msg=f"family filter leaked: {h['relpath']}")

    def test_limit_caps_returned_hits(self) -> None:
        self.assertLessEqual(searchindex.search(self.db, "police certificate", limit=1)["count"], 1)

    def test_search_does_not_mutate_the_index(self) -> None:
        """search() is byte-read-only: the DB file is identical before/after (WR-04).

        Hash the RAW DB bytes (not ``count(*) FROM chunks``). The old read-path FTS5
        probe created+dropped a *separate* ``_probe`` table, so the row count was
        trivially unchanged while the file's bytes still changed — masking the WR-01
        write. A sha256 over the file would have caught it; with the read-only
        ``mode=ro`` connect (WR-01) the bytes are provably unchanged.
        """
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        searchindex.search(self.db, "police certificate")
        after = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(before, after, msg="search() mutated the index file bytes")


# --------------------------------------------------------------------------- #
# TestResolve — RET-02 SC2: the citation resolver. A known chunk_id resolves to
# its EXACT stored chunk text (verbatim, never a snippet) + the five citation
# fields (+ chunk_id); an unknown / empty id returns None (fail-closed, no raise);
# and a content-drifted row (stored text no longer hashes to its chunk_sha) returns
# None — the fail-closed staleness guard the Phase-25 grounding gate (GND-01) relies
# on. Builds the synthetic 4-doc index once in setUp, then drives resolve().
# --------------------------------------------------------------------------- #
class TestResolve(_IndexCase):
    # The stable, PII-free citation contract the grounding gate consumes — exactly
    # these keys, no internal chunk_sha.
    _CITATION_FIELDS = {
        "chunk_id", "relpath", "source_url", "title", "section",
        "crawl_date", "text",
    }

    def setUp(self) -> None:
        super().setUp()
        # Build the index once against the synthetic 4-doc corpus (NOT real corpus/).
        searchindex.build_index(self.root, self.db)

    def _known_row(self) -> tuple[str, str]:
        """Return a real ``(chunk_id, text)`` straight from the built `chunks` table."""
        con = self._connect()
        try:
            return con.execute(
                "SELECT chunk_id, text FROM chunks "
                "WHERE relpath = 'pr-pdi/tiny.md' LIMIT 1"
            ).fetchone()
        finally:
            con.close()

    def test_known_id_resolves_to_exact_citation_dict(self) -> None:
        chunk_id, _ = self._known_row()
        got = searchindex.resolve(self.db, chunk_id)
        self.assertIsInstance(got, dict)
        self.assertEqual(set(got), self._CITATION_FIELDS)   # exact contract, no chunk_sha
        self.assertEqual(got["chunk_id"], chunk_id)

    def test_returned_text_is_verbatim_not_a_snippet(self) -> None:
        chunk_id, stored_text = self._known_row()
        got = searchindex.resolve(self.db, chunk_id)
        self.assertEqual(got["text"], stored_text)          # byte-for-byte stored text
        for marker in ("\u2026", "\u27e6", "\u27e7"):       # no … ⟦ ⟧ snippet markers
            self.assertNotIn(marker, got["text"])

    def test_citation_fields_match_the_stored_row(self) -> None:
        """The tiny doc's planted citation fields come back verbatim (e.g. the url)."""
        chunk_id, _ = self._known_row()
        got = searchindex.resolve(self.db, chunk_id)
        self.assertEqual(got["relpath"], "pr-pdi/tiny.md")
        self.assertEqual(got["source_url"], TINY_URL)       # verbatim url w/ query+frag
        self.assertEqual(got["title"], TINY_TITLE)
        self.assertEqual(got["crawl_date"], TINY_CRAWL_DATE)

    def test_unknown_id_returns_none_fail_closed(self) -> None:
        self.assertIsNone(searchindex.resolve(self.db, "no-such/doc.md#999"))

    def test_empty_id_returns_none_no_raise(self) -> None:
        self.assertIsNone(searchindex.resolve(self.db, ""))

    def test_search_then_resolve_round_trip(self) -> None:
        """A chunk_id returned by search() resolves back to a citation dict."""
        hits = searchindex.search(self.db, "police certificate")["hits"]
        self.assertGreaterEqual(len(hits), 1)
        got = searchindex.resolve(self.db, hits[0]["chunk_id"])
        self.assertIsInstance(got, dict)
        self.assertEqual(got["chunk_id"], hits[0]["chunk_id"])

    def test_intact_row_still_resolves(self) -> None:
        """The integrity check is silent on a healthy row (text hashes to chunk_sha)."""
        chunk_id, _ = self._known_row()
        self.assertIsInstance(searchindex.resolve(self.db, chunk_id), dict)

    def test_sha_drift_row_resolves_to_none_fail_closed(self) -> None:
        """Tampering text in place (leaving chunk_sha stale) → resolve returns None.

        Test-only tampering to exercise the staleness/tamper guard the Phase-25
        grounding gate (GND-01) relies on — resolve()/search() themselves never write.
        """
        chunk_id, _ = self._known_row()
        con = self._connect()
        try:
            con.execute(
                "UPDATE chunks SET text = 'TAMPERED CONTENT' WHERE chunk_id = ?",
                (chunk_id,),                          # leaves the stored chunk_sha stale
            )
            con.commit()
        finally:
            con.close()
        # Stored text no longer hashes to its chunk_sha → fail-closed, NOT the
        # tampered text and NOT an exception.
        self.assertIsNone(searchindex.resolve(self.db, chunk_id))


# --------------------------------------------------------------------------- #
# TestSearchCli — RET-02 SC1/SC2/SC3: the `search` CLI verb through the JSON
# contract. Drives cli.main(["--json","search",...]) against the synthetic 4-doc
# index (built in setUp): the one-line ranked-search envelope (ok/command/
# schema_version + hits), the empty-query → invalid_input/exit-2 and non-file-db →
# exit-2 boundaries, stdout purity, and the --cite hit (found:true, verbatim text)
# + miss (found:false, fail-closed exit 0).
# --------------------------------------------------------------------------- #
class TestSearchCli(_IndexCase):
    def setUp(self) -> None:
        super().setUp()
        # Build the index once against the synthetic 4-doc corpus (NOT real corpus/).
        searchindex.build_index(self.root, self.db)

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        """Run cli.main(argv) capturing (exit_code, stdout, stderr).

        Mirrors TestIndexCli._run (:558-567) — redirect both streams to StringIO so a
        test can assert stdout is exactly one JSON object and human text is on stderr.
        """
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _a_chunk_id(self) -> str:
        """A real chunk_id straight from the built `chunks` table (the tiny doc)."""
        con = self._connect()
        try:
            return con.execute(
                "SELECT chunk_id FROM chunks WHERE relpath = 'pr-pdi/tiny.md' LIMIT 1"
            ).fetchone()[0]
        finally:
            con.close()

    def test_search_verb_emits_one_ok_envelope(self) -> None:
        """`--json search "<q>"` → one ok:true search envelope w/ ranked hits, exit 0."""
        rc, out, _ = self._run(
            ["--json", "search", "police certificate", "--db", str(self.db)])
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("\n"), 1)            # exactly ONE JSON line
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertEqual(obj["command"], "search")
        self.assertEqual(obj["schema_version"], "1.0")  # additive change: unchanged
        self.assertEqual(obj["result"]["count"], len(obj["result"]["hits"]))
        self.assertGreaterEqual(obj["result"]["count"], 1)
        for h in obj["result"]["hits"]:                 # each hit carries the citation
            self.assertIn("chunk_id", h)                # + display + score fields
            self.assertIn("snippet", h)
            self.assertIn("score", h)

    def test_empty_query_is_invalid_input_exit_2(self) -> None:
        """An all-punctuation query → ok:false / invalid_input + exit 2 (no empty MATCH)."""
        rc, out, _ = self._run(
            ["--json", "search", "()!:", "--db", str(self.db)])
        self.assertEqual(rc, contract_exit_invalid_input())
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")
        self.assertIsNone(obj["result"])

    def test_non_file_db_is_invalid_input_exit_2(self) -> None:
        """A --db that is not a file → ok:false / invalid_input + exit 2."""
        rc, out, _ = self._run(
            ["--json", "search", "x", "--db", "/no/such/db-24-03.db"])
        self.assertEqual(rc, contract_exit_invalid_input())
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")

    def test_json_stdout_is_pure_one_object(self) -> None:
        """stdout carries EXACTLY one parseable JSON object; no JSON on stderr (P11)."""
        rc, out, err = self._run(
            ["--json", "search", "police certificate", "--db", str(self.db)])
        self.assertEqual(rc, 0)
        json.loads(out)                                 # must not raise
        self.assertEqual(out.count("\n"), 1)
        self.assertNotIn("{", err)                      # no JSON leaked to stderr

    def test_cite_hit_returns_verbatim_chunk(self) -> None:
        """`--json search --cite <id>` → found:true with the exact stored chunk text."""
        chunk_id = self._a_chunk_id()
        con = self._connect()
        try:
            stored_text = con.execute(
                "SELECT text FROM chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()[0]
        finally:
            con.close()
        rc, out, _ = self._run(
            ["--json", "search", "--cite", chunk_id, "--db", str(self.db)])
        self.assertEqual(rc, 0)
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertIs(obj["result"]["found"], True)
        # The resolved chunk's text is the VERBATIM stored span (not a snippet).
        self.assertEqual(obj["result"]["chunk"]["text"], stored_text)
        for marker in ("\u2026", "\u27e6"):             # no … / ⟦ snippet markers
            self.assertNotIn(marker, obj["result"]["chunk"]["text"])

    def test_cite_miss_is_fail_closed_exit_0(self) -> None:
        """An unknown id → ok:true / found:false / chunk:null / exit 0 (NOT an error)."""
        rc, out, _ = self._run(
            ["--json", "search", "--cite", "no-such/doc.md#999", "--db", str(self.db)])
        self.assertEqual(rc, 0)
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertIs(obj["result"]["found"], False)
        self.assertIsNone(obj["result"]["chunk"])


# --------------------------------------------------------------------------- #
# TestRealCorpus — optional smoke over the real on-disk corpus/. Builds into a
# TemporaryDirectory db (NEVER corpus/index.db, so nothing is staged under the
# git-ignored corpus/): docs == 742 canonical committed docs (PLUS the
# git-ignored Phase-41 dli family when a local `refresh-dli` has populated
# corpus/dli/), chunks > docs, max chunk bounded (SC3), and a second build into a
# fresh db yields a byte-identical chunk_id list (SC1).
# --------------------------------------------------------------------------- #


def _expected_live_docs() -> int:
    """The canonical 742 committed live docs, plus the git-ignored Phase-41 dli
    family when a local ``refresh-dli`` has populated ``corpus/dli/``.

    ``corpus/dli/`` is git-ignored, so a fresh clone / CI sees exactly 742; a
    locally-refreshed tree sees ``742 + <dli .md count>`` (the flat family the
    generator writes). Both are the correct live-doc filter set for the on-disk
    corpus the index is built over.
    """
    dli_dir = Path("corpus/dli")
    dli_docs = len(list(dli_dir.glob("*.md"))) if dli_dir.is_dir() else 0
    return 742 + dli_docs


def _ordered_chunk_ids(db: Path) -> list[str]:
    con = sqlite3.connect(str(db))
    try:
        return [r[0] for r in con.execute(
            "SELECT chunk_id FROM chunks ORDER BY chunk_id")]
    finally:
        con.close()


@unittest.skipUnless(Path("corpus").is_dir(),
                     "real corpus/ not present — skipping integration smoke test")
class TestRealCorpus(unittest.TestCase):
    def test_real_corpus_builds_742_docs_bounded_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db1 = Path(tmp) / "index.db"
            result = searchindex.build_index(Path("corpus"), db1)
            # SC1: the live-doc filter set is the canonical 742 committed docs,
            # plus the git-ignored Phase-41 dli family when locally refreshed
            # (742 in CI / a fresh clone; 742 + <dli count> after refresh-dli).
            self.assertEqual(result["docs"], _expected_live_docs())
            # The two legislation FullText docs split into many chunks → chunks > docs.
            self.assertGreater(result["chunks"], result["docs"])
            # SC3: no unbounded chunk over the real corpus.
            self.assertLessEqual(result["max_text_len"], searchindex.MAX_CHUNK_CHARS)
            # SC1 over the REAL corpus: a fresh rebuild is byte-identical.
            db2 = Path(tmp) / "index2.db"
            searchindex.build_index(Path("corpus"), db2)
            self.assertEqual(_ordered_chunk_ids(db1), _ordered_chunk_ids(db2))

    def test_real_corpus_search_resolve_round_trip(self) -> None:
        """search → resolvable chunk_id → resolve over the real 742-doc index (SC1/SC2).

        Builds the real corpus into a TemporaryDirectory db (NEVER corpus/index.db —
        nothing is staged under the git-ignored corpus/), runs a known-term search,
        and resolves a returned chunk_id back to its EXACT chunk — the end-to-end
        citation handshake the Phase-25 grounding gate (GND-01) depends on.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmpdb = Path(tmp) / "index.db"
            searchindex.build_index(Path("corpus"), tmpdb)
            result = searchindex.search(
                tmpdb, "police certificate which countries", limit=5)
            # A known term returns at least one ranked hit.
            self.assertGreaterEqual(result["count"], 1)
            # best-first = score ascending (more negative = more relevant, P9).
            scores = [h["score"] for h in result["hits"]]
            self.assertEqual(scores, sorted(scores))
            # The top hit's chunk_id round-trips back to its exact chunk via resolve().
            cid = result["hits"][0]["chunk_id"]
            got = searchindex.resolve(tmpdb, cid)
            self.assertIsInstance(got, dict)
            self.assertEqual(got["chunk_id"], cid)       # same id, resolvable
            self.assertTrue(got["text"])                 # non-empty verbatim span


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
