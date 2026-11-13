"""Corpus-structure + index-grounding regression for the NOC duty split (Phase 43 — WR-01/WR-02).

The Plan-01/02 worksheet slice (``test_noc_review.py``) exercises the happy-path
NOCs (``21232`` 7 duties, ``53124`` grouped headers) plus the fail-closed
``99999`` sentinel. This module pins the two re-review defects the flattened
index-chunk parser could not survive, and the source-driven redesign that closes
them:

  * **WR-01** — a grouped sub-occupation header that StatCan flattens onto ONE
    physical line (e.g. 72410's "Mechanical repairers - motor vehicle
    manufacturing") was OVER-SPLIT at its internal ``" - "``. The redesign parses
    the AUTHORITATIVE markdown SOURCE (one item per physical ``- `` line), so an
    internal hyphen stays inside its item — never over-split.
  * **WR-02** — a single Main-duties bullet the deterministic chunker split across
    a chunk boundary had its tail (a continuation chunk with NO leading ``- ``)
    silently DROPPED, leaving a cited-but-empty chunk (e.g. 11202 / 31100). The
    redesign maps each full source item, in order, across the Main-duties chunk
    STREAM and emits ONE grounded citation fragment per chunk it spans — the
    continuation is recovered, and every cited chunk contributes rendered content.

Two ways:

  * :class:`TestNocOverflowHermetic` — a fully SELF-CONTAINED slice that builds a
    tiny synthetic corpus (BOTH the ``chunks`` index AND the matching NOC markdown
    SOURCE files, since the redesign grounds the source against the index)
    reproducing the four real formats: an OVERFLOW NOC (Main-duties across ``#002``
    + inline-flattened ``#003``, requirements at ``#004``); a GROUPED NOC whose
    sub-occupation header carries an internal ``" - "``; a NORMAL newline NOC; and a
    CROSS-CHUNK NOC whose ONE bullet is split across ``#002``/``#003`` (the ``#003``
    tail has NO leading ``- ``). It runs ALWAYS (no corpus dependency) with EXACT
    expected counts.
  * :class:`TestNocOverflowRealCorpus` — skip-guarded on the pinned, git-ignored
    ``corpus/index.db``: 72410's grouped header is exactly one item (WR-01); 11202's
    last duty carries all three agent sentences and spans ``#002``/``#003`` with both
    citations grounded (WR-02); 31100's Preventive-medicine duty includes its
    continuation (WR-02); the real overflow ``72400`` is not mislabelled; and a
    full-corpus scan over ALL 376 NOC-2021 unit groups compares the emitted duty
    items BYTE-FOR-BYTE to the source bullets (after boilerplate) and proves EVERY
    citation fragment grounds against its sha-validated chunk.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_noc_overflow_regression.py -q
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import grounding, noc_review, noc_worksheet, searchindex, vault

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"
_CORPUS_MISSING = (
    "LOCAL-ONLY: corpus/index.db is git-ignored — the NOC overflow real-corpus "
    "regression did NOT run; a green suite here is STRUCTURAL ONLY"
)

_SEP = " \u203a "  # heading-breadcrumb separator (mirrors searchindex._SEP)


def _sec(code: str, title: str, label: "str | None") -> str:
    """A chunker-shaped section breadcrumb: ``NOC 2021 <code> — <title> › <label>``."""
    head = f"NOC 2021 {code} — {title}"
    return head if label is None else f"{head}{_SEP}{label}"


def _norm(s: str) -> str:
    """Whitespace-collapse + lowercase (mirror ``grounding._norm`` for coverage checks)."""
    return re.sub(r"\s+", " ", s).strip().lower()


def _source_bullets(md_path: Path) -> list[str]:
    """INDEPENDENTLY parse the Main-duties ``- `` bullets from a NOC markdown file.

    Reads the raw file (NOT via ``noc_worksheet``) so the full-corpus scan is a
    genuine cross-check: the emitted duty items must equal these source bullets
    byte-for-byte. Drops ONLY the exact boilerplate lead line; keeps grouped headers
    and internal hyphens verbatim.
    """
    text = md_path.read_text(encoding="utf-8")
    # Strip the leading frontmatter block (same split the indexer used).
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            text = text[nl + 1:] if nl != -1 else ""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "## Main duties":
            start = i + 1
            break
    assert start is not None, f"{md_path} has no '## Main duties' heading"
    bullets: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if not line.startswith("- "):
            continue
        body = line[2:].strip()
        if not body or body.lower().startswith("this group performs"):
            continue
        bullets.append(body)
    return bullets


# --------------------------------------------------------------------------- #
# Synthetic corpus fixtures. Each fixture writes BOTH a chunks-index row set AND
# the matching NOC markdown SOURCE file, because the redesign parses the source
# (authoritative item list) and grounds each item against the index chunk stream.
# The TEXT is representative StatCan-shaped content (NOT the verbatim corpus — the
# real bytes are covered by the skip-guarded real-corpus scan below); its job is to
# reproduce the exact bullet ENCODINGS the parser must survive. Each source item is
# verbatim-present, in order, across its Main-duties chunk(s).
# --------------------------------------------------------------------------- #
_LEAD_TEXT = "Representative lead statement for the fixture occupation."

_OVERFLOW = "72400"
_OVERFLOW_TITLE = "Construction millwrights and industrial mechanics"
# Source bullets (item bodies, boilerplate dropped) — the AUTHORITATIVE list.
_OVERFLOW_BULLETS = [
    "Alpha specialists",
    "Perform alpha duty one",
    "Perform alpha duty two",
    "Beta specialists",
    "Perform beta duty one",
    "Perform continuation duty one",
    "Perform continuation duty two",
]
# #002 is a SINGLE physical line, inline " - "-separated (the flattened overflow
# format); #003 is the inline-flattened CONTINUATION of the SAME list.
_OVERFLOW_MAIN_CHUNKS = [
    ("- This group performs some or all of the following duties: "
     "- Alpha specialists - Perform alpha duty one - Perform alpha duty two "
     "- Beta specialists - Perform beta duty one"),
    "- Perform continuation duty one - Perform continuation duty two",
]
# #004: the REAL Employment requirements (newline bullets, as StatCan emits them).
_OVERFLOW_REQS = [
    "A relevant trade credential is usually required.",
    "Several years of related experience is usually required.",
]

_GROUPED = "53124"
_GROUPED_TITLE = "Artisans and craftspersons"
_GROUPED_BULLETS = [
    "Carvers",
    "Carve items from wood and stone.",
    "Support workers - senior care",   # internal " - " — must stay ONE item
    "Assist senior clients with daily activities.",
    "Potters",
    "Design and create earthenware pieces.",
]
# A single multiline chunk (newline bullets), one header carrying an internal " - ".
_GROUPED_MAIN_CHUNKS = [
    "- This group performs some or all of the following duties:\n"
    "- Carvers\n"
    "- Carve items from wood and stone.\n"
    "- Support workers - senior care\n"
    "- Assist senior clients with daily activities.\n"
    "- Potters\n"
    "- Design and create earthenware pieces.",
]
_GROUPED_REQS = ["A portfolio of work is usually required."]

_NORMAL = "21232"
_NORMAL_TITLE = "Software developers and programmers"
_NORMAL_BULLETS = [
    "Design, write and test code for new software.",
    "Analyze information to plan new systems.",
    "Write documentation for updated software.",
]
_NORMAL_MAIN_CHUNKS = [
    "- This group performs some or all of the following duties:\n"
    "- Design, write and test code for new software.\n"
    "- Analyze information to plan new systems.\n"
    "- Write documentation for updated software.",
]
_NORMAL_REQS = ["A bachelor's degree is usually required."]

# CROSS-CHUNK: one bullet split across #002/#003; the #003 tail has NO leading
# "- " and no inline " - " (exactly the 11202 / 31100 continuation the flattened
# parser dropped).
_CROSS = "90001"
_CROSS_TITLE = "Fixture cross-chunk occupation"
_CROSS_BULLETS = [
    "Perform the first duty entirely inside chunk two.",
    ("Represent clients and prepare contracts. "
     "Literary agents specialize in representing authors. "
     "Performance agents specialize in representing performers. "
     "Sports agents specialize in representing athletes."),
]
_CROSS_MAIN_CHUNKS = [
    ("- This group performs some or all of the following duties: "
     "- Perform the first duty entirely inside chunk two. "
     "- Represent clients and prepare contracts. "
     "Literary agents specialize in representing authors."),
    ("Performance agents specialize in representing performers. "
     "Sports agents specialize in representing athletes."),
]
_CROSS_REQS = ["A relevant credential is usually required."]


def _write_source_md(corpus_root: Path, code: str, title: str,
                     bullets: list[str], reqs: list[str]) -> None:
    """Write the NOC markdown SOURCE the redesign parses (frontmatter + sections)."""
    rel = corpus_root / "noc-2021" / f"noc-{code}.md"
    rel.parent.mkdir(parents=True, exist_ok=True)
    main_lines = ["- This group performs some or all of the following duties:"]
    main_lines += [f"- {b}" for b in bullets]
    reqs_lines = [f"- {r}" for r in reqs]
    md = (
        "---\n"
        f'url: "https://example.test/noc-2021/noc-{code}.md"\n'
        f'title: "NOC 2021 {code} - {title}"\n'
        'source_type: "noc"\n'
        f'noc_code: "{code}"\n'
        'crawl_date: "2026-01-01T00:00:00Z"\n'
        "---\n\n"
        f"# NOC 2021 {code} — {title}\n\n"
        "## Lead statement\n"
        f"{_LEAD_TEXT}\n\n"
        "## Main duties\n"
        + "\n".join(main_lines) + "\n\n"
        "## Employment requirements\n"
        + "\n".join(reqs_lines) + "\n\n"
        "## Illustrative example(s)\n"
        "- Example role one\n- Example role two\n"
    )
    rel.write_text(md, encoding="utf-8")


def _build_fixture_corpus(corpus_root: Path) -> Path:
    """Build a tiny synthetic corpus (index + source md) reproducing the real formats.

    Uses the frozen ``searchindex.CHUNKS_DDL`` schema and ``searchindex.chunk_sha``
    fingerprints so ``searchindex.resolve`` / ``relpath_sections`` behave EXACTLY as
    over the real index, and writes the matching markdown SOURCE so the source-driven
    split can parse + ground each fixture. Returns the index db path.
    """
    db_path = corpus_root / "fixture-index.db"
    con = sqlite3.connect(str(db_path))
    con.executescript(searchindex.CHUNKS_DDL)

    def add(relpath: str, ordinal: int, section: str, text: str) -> None:
        con.execute(
            "INSERT INTO chunks(chunk_id, relpath, source_url, title, section, "
            "crawl_date, source_type, chunk_sha, ordinal, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"{relpath}#{ordinal:03d}", relpath,
             f"https://example.test/{relpath}", "Fixture NOC", section,
             "2026-01-01", "noc", searchindex.chunk_sha(text), ordinal, text),
        )

    def doc(code: str, title: str, bullets: list[str],
            main_chunks: list[str], reqs: list[str]) -> None:
        rel = f"noc-2021/noc-{code}.md"
        add(rel, 0, _sec(code, title, None), f"NOC 2021 {code}")
        add(rel, 1, _sec(code, title, "Lead statement"), _LEAD_TEXT)
        ordinal = 2
        for m in main_chunks:
            add(rel, ordinal, _sec(code, title, "Main duties"), m)
            ordinal += 1
        # ONE Employment-requirements chunk (newline bullets), as StatCan emits it.
        add(rel, ordinal, _sec(code, title, "Employment requirements"),
            "\n".join(f"- {r}" for r in reqs))
        ordinal += 1
        # A trailing non-target section to prove the classifier ignores it.
        add(rel, ordinal, _sec(code, title, "Illustrative example(s)"),
            "- Example role one\n- Example role two")
        _write_source_md(corpus_root, code, title, bullets, reqs)

    doc(_OVERFLOW, _OVERFLOW_TITLE, _OVERFLOW_BULLETS,
        _OVERFLOW_MAIN_CHUNKS, _OVERFLOW_REQS)
    doc(_GROUPED, _GROUPED_TITLE, _GROUPED_BULLETS,
        _GROUPED_MAIN_CHUNKS, _GROUPED_REQS)
    doc(_NORMAL, _NORMAL_TITLE, _NORMAL_BULLETS, _NORMAL_MAIN_CHUNKS, _NORMAL_REQS)
    doc(_CROSS, _CROSS_TITLE, _CROSS_BULLETS, _CROSS_MAIN_CHUNKS, _CROSS_REQS)
    con.commit()
    con.close()
    return db_path


def _build_healthy_index_corpus(corpus_root: Path) -> Path:
    """Build a HEALTHY fixture index (``chunks`` + populated ``chunks_fts`` + ``meta``).

    ``_build_fixture_corpus`` above creates ONLY the ``chunks`` table — enough for
    ``resolve_noc_spans`` / ``split_duties`` (which read ``chunks`` directly) but
    NOT enough for ``cli._require_readable_index`` (``index_health.probe_index``
    requires the ``meta`` + external-content ``chunks_fts`` tables and a clean
    ``chunk_sha`` drift sample). The WR-01 CLI slice must pass that index preflight
    FIRST and only THEN hit the source-availability fault, so this builder writes a
    fully healthy index (a single NORMAL NOC) plus the matching markdown SOURCE.
    Returns the index db path.
    """
    db_path = corpus_root / "healthy-index.db"
    con = sqlite3.connect(str(db_path))
    con.executescript(searchindex.CHUNKS_DDL)
    con.executescript(searchindex.FTS_DDL)
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta(key, value) VALUES ('schema_version', 'test')")

    def add(relpath: str, ordinal: int, section: str, text: str) -> None:
        con.execute(
            "INSERT INTO chunks(chunk_id, relpath, source_url, title, section, "
            "crawl_date, source_type, chunk_sha, ordinal, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"{relpath}#{ordinal:03d}", relpath,
             f"https://example.test/{relpath}", "Fixture NOC", section,
             "2026-01-01", "noc", searchindex.chunk_sha(text), ordinal, text),
        )

    code, title = _NORMAL, _NORMAL_TITLE
    rel = f"noc-2021/noc-{code}.md"
    add(rel, 0, _sec(code, title, None), f"NOC 2021 {code}")
    add(rel, 1, _sec(code, title, "Lead statement"), _LEAD_TEXT)
    ordinal = 2
    for m in _NORMAL_MAIN_CHUNKS:
        add(rel, ordinal, _sec(code, title, "Main duties"), m)
        ordinal += 1
    add(rel, ordinal, _sec(code, title, "Employment requirements"),
        "\n".join(f"- {r}" for r in _NORMAL_REQS))
    # Populate the external-content FTS index so probe_index's `count(*)` + drift
    # sample succeed (an unpopulated external-content vtable reads as corrupt).
    con.execute("INSERT INTO chunks_fts(rowid, text) SELECT id, text FROM chunks")
    con.commit()
    con.close()
    _write_source_md(corpus_root, code, title, _NORMAL_BULLETS, _NORMAL_REQS)
    return db_path


class TestNocOverflowHermetic(unittest.TestCase):
    """Self-contained overflow/grouped/normal/cross-chunk parser regression (no corpus)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self._tmp.name)
        self.db = str(_build_fixture_corpus(self.corpus))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- section-aware resolution: overflow spans two Main-duties chunks ----- #
    def test_overflow_resolves_two_main_chunks_and_reqs_at_004(self) -> None:
        spans = noc_worksheet.resolve_noc_spans(self.db, _OVERFLOW)
        self.assertIsNotNone(spans)
        self.assertEqual(spans["lead"]["chunk_id"],
                         f"noc-2021/noc-{_OVERFLOW}.md#001")
        # BOTH Main-duties chunks are collected (never truncated to one), and #003
        # is classified as Main duties (NOT positionally assumed to be requirements).
        self.assertEqual(
            [m["chunk_id"] for m in spans["main"]],
            [f"noc-2021/noc-{_OVERFLOW}.md#002",
             f"noc-2021/noc-{_OVERFLOW}.md#003"])
        # The REAL Employment requirements live at #004 — NOT the #003 continuation.
        self.assertEqual([r["chunk_id"] for r in spans["reqs"]],
                         [f"noc-2021/noc-{_OVERFLOW}.md#004"])
        for r in spans["reqs"]:
            self.assertTrue(r["section"].endswith("Employment requirements"))

    # -- duties captured across BOTH chunks; source-item ordinals (CR-02) ---- #
    def test_overflow_duties_span_both_chunks_stable_source_ids(self) -> None:
        spans = noc_worksheet.resolve_noc_spans(self.db, _OVERFLOW)
        duties = noc_worksheet.split_duties(self.db, _OVERFLOW, spans["main"])
        self.assertIsNotNone(duties)
        ids = [d["duty_id"] for d in duties]
        texts = [d["text"] for d in duties]
        # 7 items, keyed by SOURCE-section item ordinal (not a chunk ordinal).
        self.assertEqual(ids, [f"{_OVERFLOW}:{i:02d}" for i in range(7)])
        # Emitted items equal the source bullets byte-for-byte (boilerplate dropped).
        self.assertEqual(texts, _OVERFLOW_BULLETS)
        self.assertNotIn(
            "This group performs some or all of the following duties:", texts)
        # Sub-occupation headers preserved verbatim (never classified away).
        self.assertIn("Alpha specialists", texts)
        self.assertIn("Beta specialists", texts)
        # The #003 continuation duties are present (they were dropped pre-fix).
        self.assertIn("Perform continuation duty one", texts)
        self.assertIn("Perform continuation duty two", texts)
        # Each duty cites its OWN source chunk (#002 for 00-04, #003 for 05-06).
        cite = {d["duty_id"]: [c["chunk_id"] for c in d["citations"]]
                for d in duties}
        self.assertEqual(cite[f"{_OVERFLOW}:00"],
                         [f"noc-2021/noc-{_OVERFLOW}.md#002"])
        self.assertEqual(cite[f"{_OVERFLOW}:05"],
                         [f"noc-2021/noc-{_OVERFLOW}.md#003"])

    # -- render never mislabels duty text as Employment requirements (CR-01) - #
    def test_overflow_render_never_mislabels_duties_as_requirements(self) -> None:
        spans = noc_worksheet.resolve_noc_spans(self.db, _OVERFLOW)
        duties = noc_worksheet.split_duties(self.db, _OVERFLOW, spans["main"])
        body = noc_worksheet._render_worksheet(spans, duties, _OVERFLOW)
        self.assertIn("## Main duties", body)
        self.assertIn("## Employment requirements (read-only)", body)
        main_part, _, reqs_part = body.partition(
            "## Employment requirements (read-only)")
        # Duty text lives ONLY under Main duties; the #003 continuation duty must
        # NOT appear in the Employment-requirements section (the CR-01 bug).
        self.assertIn("Perform continuation duty one", main_part)
        self.assertNotIn("Perform continuation duty one", reqs_part)
        # The REAL requirements ARE shown (not silently dropped) + correctly cited.
        self.assertIn("A relevant trade credential is usually required.", reqs_part)
        self.assertIn(f"noc-2021/noc-{_OVERFLOW}.md#004", reqs_part)

    # -- end-to-end capture: duty_count is the sum across both chunks -------- #
    def test_overflow_generate_worksheet_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as personal:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": personal}):
                v = vault.open_vault("default")
                vault.create_candidate(v, "default")
                res = noc_worksheet.generate_worksheet(
                    v, self.db, "default", _OVERFLOW)
                self.assertEqual(res["duty_count"], 7)   # 5 (#002) + 2 (#003)
                self.assertEqual(len(res["value_ids"]), 8)  # + lead statement
                # Citations reflect the ACTUAL section-classified chunks (no
                # positional #003-is-requirements guess): lead, #002, #003, #004.
                self.assertEqual(res["citations"], [
                    f"noc-2021/noc-{_OVERFLOW}.md#001",
                    f"noc-2021/noc-{_OVERFLOW}.md#002",
                    f"noc-2021/noc-{_OVERFLOW}.md#003",
                    f"noc-2021/noc-{_OVERFLOW}.md#004"])
                # The inert never-green sidecar sees all 7 current duties.
                review = noc_review.review_noc_duties(
                    v, self.db, _OVERFLOW, "default")
                self.assertEqual(review["duty_count"], 7)
                self.assertNotEqual(review["status"], "SUBSTANTIATED")

    # -- WR-01: grouped headers with an internal " - " are NEVER over-split -- #
    def test_grouped_headers_preserved_and_not_oversplit(self) -> None:
        spans = noc_worksheet.resolve_noc_spans(self.db, _GROUPED)
        self.assertEqual(len(spans["main"]), 1)  # single (multiline) chunk
        duties = noc_worksheet.split_duties(self.db, _GROUPED, spans["main"])
        self.assertIsNotNone(duties)
        texts = [d["text"] for d in duties]
        # Emitted items equal the source bullets byte-for-byte.
        self.assertEqual(texts, _GROUPED_BULLETS)
        self.assertIn("Carvers", texts)
        self.assertIn("Potters", texts)
        # A header with an internal " - " stays ONE verbatim item (the WR-01 guard).
        self.assertIn("Support workers - senior care", texts)
        # Over-split would have produced "Support workers" and "senior care" as
        # separate items; assert neither fragment ever stands alone.
        self.assertNotIn("Support workers", texts)
        self.assertNotIn("senior care", texts)
        # 6 items: 3 headers + 3 duties (the boilerplate lead line is dropped).
        self.assertEqual(len(duties), 6)
        # The internal hyphen never fabricates a second citation.
        hdr = next(d for d in duties if d["text"] == "Support workers - senior care")
        self.assertEqual(len(hdr["citations"]), 1)

    # -- normal newline NOC: source-item ids/count -------------------------- #
    def test_normal_newline_bullets_source_item_ids(self) -> None:
        spans = noc_worksheet.resolve_noc_spans(self.db, _NORMAL)
        self.assertEqual(len(spans["main"]), 1)
        duties = noc_worksheet.split_duties(self.db, _NORMAL, spans["main"])
        self.assertIsNotNone(duties)
        self.assertEqual([d["duty_id"] for d in duties],
                         [f"{_NORMAL}:{i:02d}" for i in range(3)])
        self.assertEqual([d["text"] for d in duties], _NORMAL_BULLETS)

    # -- WR-02: a bullet split across the boundary keeps its continuation ---- #
    def test_crosschunk_bullet_spans_two_chunks_both_grounded(self) -> None:
        spans = noc_worksheet.resolve_noc_spans(self.db, _CROSS)
        self.assertEqual(
            [m["chunk_id"] for m in spans["main"]],
            [f"noc-2021/noc-{_CROSS}.md#002", f"noc-2021/noc-{_CROSS}.md#003"])
        duties = noc_worksheet.split_duties(self.db, _CROSS, spans["main"])
        self.assertIsNotNone(duties)
        # Exactly TWO source items (the #003 tail is NOT a third phantom duty).
        self.assertEqual(len(duties), 2)
        self.assertEqual([d["text"] for d in duties], _CROSS_BULLETS)
        last = duties[-1]
        # The full bullet (all three "agents" sentences) is one item (WR-02).
        for sentence in ("Represent clients and prepare contracts.",
                         "Literary agents specialize in representing authors.",
                         "Performance agents specialize in representing performers.",
                         "Sports agents specialize in representing athletes."):
            self.assertIn(sentence, last["text"])
        # It carries ONE ordered citation fragment per chunk it spans (#002, #003).
        self.assertEqual([c["chunk_id"] for c in last["citations"]],
                         [f"noc-2021/noc-{_CROSS}.md#002",
                          f"noc-2021/noc-{_CROSS}.md#003"])
        # BOTH fragments ground against their OWN sha-validated chunk.
        for frag in last["citations"]:
            chunk = searchindex.resolve(self.db, frag["chunk_id"])
            self.assertIsNotNone(chunk)
            self.assertTrue(grounding.quote_is_grounded(frag["quote"], chunk["text"]))
        # The two fragments concatenate (normalized) back to the full item — full
        # in-order coverage, nothing dropped or duplicated.
        joined = _norm(" ".join(c["quote"] for c in last["citations"]))
        self.assertEqual(joined, _norm(last["text"]))

    # -- WR-02: every cited Main-duties chunk contributes rendered content --- #
    def test_crosschunk_no_cited_chunk_is_empty(self) -> None:
        spans = noc_worksheet.resolve_noc_spans(self.db, _CROSS)
        duties = noc_worksheet.split_duties(self.db, _CROSS, spans["main"])
        body = noc_worksheet._render_worksheet(spans, duties, _CROSS)
        main_part, _, _ = body.partition("## Employment requirements (read-only)")
        # Each Main-duties chunk cited in the heading contributes >=1 fragment, so
        # its content actually renders (the #003 continuation is NOT a dangling
        # citation — the WR-02 defect).
        cited_chunks = {c["chunk_id"] for d in duties for c in d["citations"]}
        for m in spans["main"]:
            self.assertIn(m["chunk_id"], cited_chunks,
                          f"{m['chunk_id']} cited but yields no duty fragment")
        # The #003 continuation text is rendered under Main duties (not dropped).
        self.assertIn("Performance agents specialize in representing performers.",
                      main_part)


@unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
class TestNocOverflowRealCorpus(unittest.TestCase):
    """End-to-end overflow/WR-01/WR-02 regression + a full-corpus byte-for-byte scan."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.db = str(_REAL_DB)
        self.corpus_root = Path(self.db).resolve().parent

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _duties(self, code: str) -> list[dict]:
        spans = noc_worksheet.resolve_noc_spans(self.db, code)
        self.assertIsNotNone(spans, f"{code} failed to resolve")
        duties = noc_worksheet.split_duties(self.db, code, spans["main"])
        self.assertIsNotNone(duties, f"{code} failed to split")
        return duties

    def _src_bullets(self, code: str) -> list[str]:
        return _source_bullets(self.corpus_root / "noc-2021" / f"noc-{code}.md")

    @staticmethod
    def _all_noc_relpaths() -> list[str]:
        con = sqlite3.connect(f"file:{_REAL_DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT DISTINCT relpath FROM chunks "
                "WHERE relpath LIKE 'noc-2021/noc-%' ORDER BY relpath").fetchall()
        finally:
            con.close()
        return [r["relpath"] for r in rows]

    # -- WR-01: 72410's flattened grouped header is EXACTLY one item --------- #
    def test_real_72410_grouped_header_is_exactly_one_item(self) -> None:
        duties = self._duties("72410")
        texts = [d["text"] for d in duties]
        # The header lives inside a SINGLE flattened chunk (#002) with an internal
        # " - "; the source-driven split keeps it ONE verbatim item.
        self.assertIn("Mechanical repairers - motor vehicle manufacturing", texts)
        # Pre-fix it was over-split into these two nonsensical standalone "duties".
        self.assertNotIn("Mechanical repairers", texts)
        self.assertNotIn("motor vehicle manufacturing", texts)
        # 17 source bullets -> 17 duties (pre-fix: 18, the over-split header).
        self.assertEqual(texts, self._src_bullets("72410"))
        self.assertEqual(len(duties), 17)

    # -- WR-02: 11202's last bullet spans #002/#003, both citations grounded - #
    def test_real_11202_last_duty_spans_two_chunks_grounded(self) -> None:
        duties = self._duties("11202")
        last = duties[-1]
        for agent in ("Literary agents", "Performance agents", "Sports agents"):
            self.assertIn(agent, last["text"])
        self.assertEqual([c["chunk_id"] for c in last["citations"]],
                         ["noc-2021/noc-11202.md#002", "noc-2021/noc-11202.md#003"])
        for frag in last["citations"]:
            chunk = searchindex.resolve(self.db, frag["chunk_id"])
            self.assertIsNotNone(chunk)
            self.assertTrue(
                grounding.quote_is_grounded(frag["quote"], chunk["text"]))
        # The two continuation sentences (only in #003) are NOT dropped.
        self.assertIn(
            "Performance agents specialize in representing singers", last["text"])
        self.assertIn(
            "Sports agents specialize in representing specific athletes",
            last["text"])

    # -- WR-02: 31100's Preventive-medicine duty includes its continuation --- #
    def test_real_31100_preventive_duty_includes_continuation(self) -> None:
        duties = self._duties("31100")
        preventive = next(
            d for d in duties
            if d["text"].startswith("Apply knowledge of general preventive"))
        # The continuation (only in #003) is stitched into the SAME item.
        self.assertIn(
            "May diagnose and treat patients in the context of clinical health "
            "promotion and disease prevention.", preventive["text"])
        self.assertEqual([c["chunk_id"] for c in preventive["citations"]],
                         ["noc-2021/noc-31100.md#002", "noc-2021/noc-31100.md#003"])
        for frag in preventive["citations"]:
            chunk = searchindex.resolve(self.db, frag["chunk_id"])
            self.assertIsNotNone(chunk)
            self.assertTrue(
                grounding.quote_is_grounded(frag["quote"], chunk["text"]))

    # -- the real 72400 overflow, end-to-end through the shipped path -------- #
    def test_real_72400_overflow_no_mislabel_no_dropped_duties(self) -> None:
        spans = noc_worksheet.resolve_noc_spans(self.db, "72400")
        self.assertIsNotNone(spans)
        # 72400's Main-duties list overflows onto a SECOND chunk (#002 + #003).
        self.assertGreaterEqual(len(spans["main"]), 2)
        for m in spans["main"]:
            self.assertTrue(m["section"].endswith("Main duties"))
        # The real Employment requirements resolve to their OWN section (#004+),
        # never the #003 duty continuation.
        self.assertGreaterEqual(len(spans["reqs"]), 1)
        for r in spans["reqs"]:
            self.assertIn("Employment requirements", r["section"])
        duties = noc_worksheet.split_duties(self.db, "72400", spans["main"])
        # duties are drawn from BOTH #002 and #003.
        cited = {c["chunk_id"] for d in duties for c in d["citations"]}
        self.assertIn("noc-2021/noc-72400.md#002", cited)
        self.assertIn("noc-2021/noc-72400.md#003", cited)
        # Emitted items equal the source bullets byte-for-byte (18 duties).
        self.assertEqual([d["text"] for d in duties], self._src_bullets("72400"))
        self.assertEqual(len(duties), 18)
        # Render: no duty text under the Employment-requirements heading.
        body = noc_worksheet._render_worksheet(spans, duties, "72400")
        _, _, reqs_part = body.partition("## Employment requirements (read-only)")
        for d in duties:
            self.assertNotIn(d["text"], reqs_part)

    # -- every one of the 376 NOC groups: byte-for-byte + every fragment grounds #
    def test_all_376_noc_groups_emit_source_bullets_and_ground(self) -> None:
        relpaths = self._all_noc_relpaths()
        self.assertGreaterEqual(len(relpaths), 376)
        total_multi = 0
        for rel in relpaths:
            code = rel.split("noc-")[-1].replace(".md", "")
            with self.subTest(noc=code):
                spans = noc_worksheet.resolve_noc_spans(self.db, code)
                self.assertIsNotNone(spans, f"{code} failed to resolve")
                self.assertTrue(spans["lead"]["section"].endswith("Lead statement"))
                self.assertGreaterEqual(len(spans["main"]), 1)
                for m in spans["main"]:
                    self.assertTrue(m["section"].endswith("Main duties"))
                for r in spans["reqs"]:
                    self.assertTrue(
                        r["section"].endswith("Employment requirements"))
                duties = noc_worksheet.split_duties(self.db, code, spans["main"])
                self.assertIsNotNone(duties, f"{code} failed to split")
                self.assertGreater(len(duties), 0, f"{code} produced zero duties")
                # (1) Emitted items equal the raw source bullets byte-for-byte.
                self.assertEqual([d["text"] for d in duties],
                                 self._src_bullets(code),
                                 f"{code} emitted items differ from source bullets")
                # (2) Every citation fragment grounds against its sha-validated chunk,
                #     and the fragments cover the full item in order.
                for d in duties:
                    self.assertGreaterEqual(len(d["citations"]), 1)
                    if len(d["citations"]) > 1:
                        total_multi += 1
                    for frag in d["citations"]:
                        chunk = searchindex.resolve(self.db, frag["chunk_id"])
                        self.assertIsNotNone(
                            chunk, f"{code} fragment cites unresolved "
                                   f"{frag['chunk_id']}")
                        self.assertTrue(
                            grounding.quote_is_grounded(frag["quote"],
                                                        chunk["text"]),
                            f"{code} fragment not grounded in {frag['chunk_id']}")
                    joined = _norm(" ".join(c["quote"] for c in d["citations"]))
                    self.assertEqual(joined, _norm(d["text"]),
                                     f"{code} fragments do not cover {d['duty_id']}")
        # The corpus contains the known boundary-split duties (11202 + 31100), so the
        # multi-chunk path is genuinely exercised by the scan.
        self.assertGreaterEqual(total_multi, 2)


# --------------------------------------------------------------------------- #
# WR-01 (final re-review): a MISSING / unreadable / path-escaped /
# frontmatter-mismatched authoritative NOC SOURCE — with the INDEX still present —
# must be a DISTINCT, fail-closed ``noc_source_unavailable`` corpus-integrity fault
# (a typed ``NocSourceUnavailable``), never masked as a bad ``--noc-code``
# (``unresolved_noc``) at the worksheet nor as a clean ``N/A`` / ``no_worksheet``
# success at the sidecar. These are fully hermetic (build a synthetic index, then
# remove/break ONLY the source) and run ALWAYS — no corpus dependency.
# --------------------------------------------------------------------------- #
class TestNocSourceUnavailableHermetic(unittest.TestCase):
    """Index-present / source-broken is a typed, fail-closed corpus-integrity fault."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self._tmp.name)
        self.db = str(_build_fixture_corpus(self.corpus))
        self.code = _NORMAL  # a normal newline NOC present in the fixture index
        self.src = self.corpus / "noc-2021" / f"noc-{self.code}.md"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _abs_leak_free(self, text: str) -> None:
        """A refusal/exception string must carry NO absolute source/vault path."""
        self.assertNotIn(str(self.corpus), text)
        self.assertNotIn(self._tmp.name, text)
        self.assertNotIn(str(self.src), text)

    # -- the index STILL resolves after the source is removed --------------- #
    def test_index_resolves_but_source_missing_raises_typed_error(self) -> None:
        # Precondition: with the source present the NOC splits cleanly.
        spans = noc_worksheet.resolve_noc_spans(self.db, self.code)
        self.assertIsNotNone(spans)
        self.assertIsNotNone(
            noc_worksheet.split_duties(self.db, self.code, spans["main"]))
        # Remove ONLY the markdown source; the pinned index is untouched.
        self.src.unlink()
        spans = noc_worksheet.resolve_noc_spans(self.db, self.code)
        self.assertIsNotNone(spans, "index must still resolve the NOC")
        # The split now raises the DISTINCT typed fault (never returns None here).
        with self.assertRaises(noc_worksheet.NocSourceUnavailable) as ctx:
            noc_worksheet.split_duties(self.db, self.code, spans["main"])
        self.assertEqual(ctx.exception.reason, "noc_source_unavailable")
        self._abs_leak_free(str(ctx.exception))
        # _source_main_duty_items raises for a missing source too...
        with self.assertRaises(noc_worksheet.NocSourceUnavailable):
            noc_worksheet._source_main_duty_items(self.db, self.code)

    # -- code SYNTAX stays separate from source AVAILABILITY ---------------- #
    def test_malformed_code_returns_none_not_source_unavailable(self) -> None:
        # A malformed code is an INPUT-validation miss (existing None semantics),
        # NOT a source-availability fault — it must never raise NocSourceUnavailable.
        for bad in ("abc", "123", "1234", "123456", ""):
            with self.subTest(bad=bad):
                self.assertIsNone(
                    noc_worksheet._source_main_duty_items(self.db, bad))

    # -- unreadable source (permission) ------------------------------------- #
    def test_unreadable_source_raises_typed_error(self) -> None:
        self.src.chmod(0)
        if os.access(self.src, os.R_OK):  # running as root — chmod is a no-op
            self.skipTest("cannot make the source unreadable as this uid (root)")
        try:
            with self.assertRaises(noc_worksheet.NocSourceUnavailable):
                noc_worksheet._source_main_duty_items(self.db, self.code)
        finally:
            self.src.chmod(stat.S_IRUSR | stat.S_IWUSR)

    # -- path-escaped source (symlink out of the corpus root) --------------- #
    def test_path_escaped_source_raises_typed_error(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "elsewhere.md"
            target.write_text("---\nsource_type: \"noc\"\n---\n## Main duties\n- x\n",
                              encoding="utf-8")
            self.src.unlink()
            self.src.symlink_to(target)  # resolves OUTSIDE the corpus root
            with self.assertRaises(noc_worksheet.NocSourceUnavailable):
                noc_worksheet._source_main_duty_items(self.db, self.code)

    # -- frontmatter-mismatched source (wrong noc_code / source_type) ------- #
    def test_frontmatter_mismatch_source_raises_typed_error(self) -> None:
        wrong_code = (
            "---\n"
            'source_type: "noc"\n'
            'noc_code: "99999"\n'          # not self.code -> mismatch
            "---\n\n## Main duties\n- Some duty.\n")
        self.src.write_text(wrong_code, encoding="utf-8")
        with self.assertRaises(noc_worksheet.NocSourceUnavailable):
            noc_worksheet._source_main_duty_items(self.db, self.code)
        wrong_type = (
            "---\n"
            'source_type: "policy"\n'      # not "noc" -> mismatch
            f'noc_code: "{self.code}"\n'
            "---\n\n## Main duties\n- Some duty.\n")
        self.src.write_text(wrong_type, encoding="utf-8")
        with self.assertRaises(noc_worksheet.NocSourceUnavailable):
            noc_worksheet._source_main_duty_items(self.db, self.code)

    # -- generator: distinct reason, ZERO artifacts, no green --------------- #
    def test_generate_worksheet_source_missing_zero_artifacts(self) -> None:
        self.src.unlink()
        with tempfile.TemporaryDirectory() as personal:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": personal}):
                v = vault.open_vault("default")
                vault.create_candidate(v, "default")
                res = noc_worksheet.generate_worksheet(
                    v, self.db, "default", self.code)
                # DISTINCT reason (not unresolved_noc), fail-closed refusal.
                self.assertEqual(res["reason"], "noc_source_unavailable")
                self.assertIsNone(res["worksheet_doc_id"])
                self.assertEqual(res["value_ids"], [])
                self.assertEqual(res["duty_count"], 0)
                # ZERO worksheet artifacts + ZERO review.noc values + ZERO documents.
                self.assertEqual(list(Path(personal).rglob("noc-*.md")), [])
                docs = v.con.execute(
                    "SELECT COUNT(*) c FROM documents "
                    "WHERE doc_type='noc_worksheet'").fetchone()["c"]
                self.assertEqual(docs, 0)
                vals = v.con.execute(
                    "SELECT COUNT(*) c FROM extracted_values "
                    "WHERE factor_id='review.noc'").fetchone()["c"]
                self.assertEqual(vals, 0)

    # -- sidecar: AT-RISK / noc_source_unavailable, closed, never green ----- #
    def test_review_source_missing_at_risk_not_no_worksheet(self) -> None:
        self.src.unlink()
        with tempfile.TemporaryDirectory() as personal:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": personal}):
                v = vault.open_vault("default")
                vault.create_candidate(v, "default")
                res = noc_review.review_noc_duties(v, self.db, self.code, "default")
                # NOT the clean N/A/no_worksheet a duty-less NOC returns.
                self.assertEqual(res["status"], "AT-RISK")
                self.assertEqual(res["reason"], "noc_source_unavailable")
                self.assertNotEqual(res["status"], "N/A")
                self.assertNotEqual(res["reason"], "no_worksheet")
                # Structurally never green + closed PII-light PUBLIC_FIELDS only.
                self.assertNotEqual(res["status"], "SUBSTANTIATED")
                self.assertIn(res["status"], ("AT-RISK", "GAP", "N/A"))
                self.assertEqual(set(res.keys()), set(noc_review.PUBLIC_FIELDS))
                self.assertEqual(res["duty_count"], 0)
                self.assertEqual(res["confirmed_count"], 0)
                self.assertLessEqual(res["confirmed_count"], res["duty_count"])
                self._abs_leak_free(json.dumps(res))

    # -- PRESERVE: a genuinely absent NOC code stays the OLD behavior ------- #
    def test_absent_code_still_unresolved_noc_and_no_worksheet(self) -> None:
        with tempfile.TemporaryDirectory() as personal:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": personal}):
                v = vault.open_vault("default")
                vault.create_candidate(v, "default")
                # "99999" is absent from the fixture index -> resolve returns None.
                res = noc_worksheet.generate_worksheet(v, self.db, "default", "99999")
                self.assertEqual(res["reason"], "unresolved_noc")
                self.assertIsNone(res["worksheet_doc_id"])
                review = noc_review.review_noc_duties(v, self.db, "99999", "default")
                self.assertEqual((review["status"], review["reason"]),
                                 ("N/A", "no_worksheet"))


@unittest.skipUnless(hasattr(os, "geteuid"), "POSIX-only chmod semantics")
class TestNocSourceUnavailableCli(unittest.TestCase):
    """WR-01 through ``cli.main``: a healthy index + a missing SOURCE (hermetic)."""

    def setUp(self) -> None:
        self._corpus_tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self._corpus_tmp.name)
        self.db = str(_build_healthy_index_corpus(self.corpus))
        self.code = _NORMAL
        self.src = self.corpus / "noc-2021" / f"noc-{self.code}.md"
        self._personal_tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._personal_tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._personal_tmp.cleanup()
        self._corpus_tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        from crawler import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _artifacts(self) -> list[Path]:
        return list(Path(self._personal_tmp.name).rglob("noc-*.md"))

    def _no_abs_path(self, blob: str) -> None:
        self.assertNotIn(self.corpus.as_posix(), blob)
        self.assertNotIn(self._corpus_tmp.name, blob)
        self.assertNotIn(self._personal_tmp.name, blob)

    def test_healthy_index_source_present_worksheet_succeeds(self) -> None:
        # Control: with the source present the healthy index yields a worksheet
        # (proves the index passes the preflight and the fault is the SOURCE only).
        rc, out, _ = self._run(
            ["--json", "vault", "noc-worksheet", "--noc-code", self.code,
             "--db", self.db])
        self.assertEqual(rc, 0, out)
        self.assertTrue(json.loads(out)["ok"])
        self.assertEqual(len(self._artifacts()), 1)

    def test_worksheet_source_missing_invalid_input_exit2_zero_artifacts(self) -> None:
        self.src.unlink()
        rc, out, _ = self._run(
            ["--json", "vault", "noc-worksheet", "--noc-code", self.code,
             "--db", self.db])
        self.assertEqual(rc, 2, out)
        env = json.loads(out)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], "invalid_input")
        # STABLE reason token + refresh/rebuild-the-corpus hint (NOT "check code").
        self.assertIn("reason=noc_source_unavailable", env["error"]["message"])
        self.assertIn("refresh", env["error"]["message"].lower())
        self.assertNotIn("unresolved_noc", env["error"]["message"])
        # No absolute path leaks; the index preflight passed, so this is NOT the
        # generic index refusal — the fault is the missing SOURCE.
        self._no_abs_path(out)
        # Zero worksheet artifacts written on the refusal path.
        self.assertEqual(self._artifacts(), [])

    def test_review_source_missing_reports_accurate_at_risk(self) -> None:
        self.src.unlink()
        rc, out, err = self._run(
            ["--json", "vault", "noc-review", "--noc-code", self.code,
             "--db", self.db])
        # The sidecar verb may remain ok:true, but status/reason MUST be accurate.
        self.assertEqual(rc, 0, out)
        env = json.loads(out)
        self.assertTrue(env["ok"])
        result = env["result"]
        self.assertEqual(result["status"], "AT-RISK")
        self.assertEqual(result["reason"], "noc_source_unavailable")
        self.assertNotEqual(result["reason"], "no_worksheet")
        self.assertNotEqual(result["status"], "SUBSTANTIATED")
        self.assertNotIn("SUBSTANTIATED", out)
        self.assertEqual(set(result.keys()), set(noc_review.PUBLIC_FIELDS))
        self._no_abs_path(out)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
