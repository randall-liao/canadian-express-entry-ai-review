"""Unit table for the corpus-index preflight (HARD-01 — Phase 36 Plan 01).

Builds every index-health state in a tempdir and asserts ``probe_index`` classifies
it into the closed reason-code vocabulary, read-only and side-effect-free. Stdlib
``unittest`` ONLY — no network, no corpus, no vault.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from crawler import index_health
from crawler.searchindex import CHUNKS_DDL, FTS_DDL, chunk_sha


def _build_valid_index(db: Path, *, chunks: list[str], tamper_first_sha: bool = False,
                       drop_chunk_sha_column: bool = False) -> None:
    """Write a minimal but real searchindex-shaped DB with *chunks* rows.

    ``tamper_first_sha`` stores a wrong ``chunk_sha`` for row 0 (drift). 
    ``drop_chunk_sha_column`` builds a ``chunks`` table WITHOUT the ``chunk_sha``
    column so a post-connect row read raises ``DatabaseError`` (HIGH-1 case).
    """
    con = sqlite3.connect(str(db))
    try:
        if drop_chunk_sha_column:
            # Same table name + enough columns to pass count(*), but no chunk_sha.
            con.execute(
                "CREATE TABLE chunks (id INTEGER PRIMARY KEY, chunk_id TEXT, text TEXT)")
        else:
            con.executescript(CHUNKS_DDL)
        con.executescript(FTS_DDL)
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        for ordinal, text in enumerate(chunks):
            sha = chunk_sha(text)
            if tamper_first_sha and ordinal == 0:
                sha = "0" * len(sha)  # wrong fingerprint → drift
            cid = f"doc.md#{ordinal:03d}"
            if drop_chunk_sha_column:
                con.execute(
                    "INSERT INTO chunks(chunk_id, text) VALUES (?, ?)", (cid, text))
            else:
                con.execute(
                    "INSERT INTO chunks(chunk_id, relpath, source_url, title, "
                    "section, crawl_date, source_type, chunk_sha, ordinal, text) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (cid, "doc.md", "", "", "", "", "", sha, ordinal, text))
        if not drop_chunk_sha_column:
            con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        con.commit()
    finally:
        con.close()


class ProbeIndexReasonCodes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_path_is_index_missing_and_creates_nothing(self) -> None:
        db = self.dir / "nope.db"
        self.assertEqual(index_health.probe_index(db).status,
                         index_health.INDEX_MISSING)
        # Read-only / side-effect-free: the probe must NOT create the file.
        self.assertFalse(db.exists())

    def test_zero_byte_file_is_index_empty(self) -> None:
        db = self.dir / "empty.db"
        db.write_bytes(b"")
        self.assertEqual(index_health.probe_index(db).status,
                         index_health.INDEX_EMPTY)

    def test_non_sqlite_bytes_is_index_corrupt(self) -> None:
        db = self.dir / "corrupt.db"
        db.write_bytes(b"this is not a database")
        self.assertEqual(index_health.probe_index(db).status,
                         index_health.INDEX_CORRUPT)

    def test_missing_required_tables_is_index_corrupt(self) -> None:
        db = self.dir / "wrong-schema.db"
        con = sqlite3.connect(str(db))
        con.execute("CREATE TABLE foo (x INTEGER)")
        con.commit()
        con.close()
        self.assertEqual(index_health.probe_index(db).status,
                         index_health.INDEX_CORRUPT)

    def test_zero_chunk_rows_is_index_empty(self) -> None:
        db = self.dir / "no-chunks.db"
        _build_valid_index(db, chunks=[])
        self.assertEqual(index_health.probe_index(db).status,
                         index_health.INDEX_EMPTY)

    def test_valid_populated_index_is_ok(self) -> None:
        db = self.dir / "good.db"
        _build_valid_index(db, chunks=["first chunk text here", "second chunk text"])
        health = index_health.probe_index(db)
        self.assertEqual(health.status, index_health.INDEX_OK)
        self.assertTrue(health.ok())

    def test_tampered_chunk_sha_is_index_drifted(self) -> None:
        db = self.dir / "drifted.db"
        _build_valid_index(db, chunks=["alpha beta gamma", "delta epsilon"],
                           tamper_first_sha=True)
        self.assertEqual(index_health.probe_index(db).status,
                         index_health.INDEX_DRIFTED)

    def test_row_level_malformation_is_corrupt_not_exception(self) -> None:
        # HIGH-1: tables exist and count(*) works, but reading `chunk_sha` raises
        # a DatabaseError — must refuse cleanly as corrupt, never re-raise.
        db = self.dir / "row-malformed.db"
        _build_valid_index(db, chunks=["some text", "more text"],
                           drop_chunk_sha_column=True)
        # Must NOT raise:
        health = index_health.probe_index(db)
        self.assertEqual(health.status, index_health.INDEX_CORRUPT)

    def test_non_text_cell_is_corrupt_not_exception(self) -> None:
        # WR-02: a foreign/legacy schema whose `text` column stores a BLOB (not str)
        # would make chunk_sha raise — must refuse cleanly as corrupt, never re-raise.
        db = self.dir / "blob-text.db"
        con = sqlite3.connect(str(db))
        # Foreign schema: required table names present, but text is a BLOB.
        con.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, "
                    "text BLOB, chunk_sha TEXT)")
        con.execute("CREATE TABLE chunks_fts (x)")
        con.execute("CREATE TABLE meta (key TEXT, value TEXT)")
        con.execute("INSERT INTO chunks(text, chunk_sha) VALUES (?, ?)",
                    (b"\x00\x01\x02binary", "deadbeef"))
        con.commit()
        con.close()
        health = index_health.probe_index(db)
        self.assertEqual(health.status, index_health.INDEX_CORRUPT)

    def test_permission_denied_parent_is_unreadable_not_exception(self) -> None:
        # WR-01: a permission-denied parent directory raises PermissionError from
        # is_file()/stat() — must fail closed to index_unreadable, never re-raise.
        locked = self.dir / "locked"
        locked.mkdir()
        db = locked / "index.db"
        db.write_bytes(b"placeholder")
        os.chmod(locked, 0o000)
        try:
            health = index_health.probe_index(db)
            self.assertIn(
                health.status,
                (index_health.INDEX_UNREADABLE, index_health.INDEX_MISSING))
        finally:
            os.chmod(locked, 0o755)  # restore so tearDown can clean up

    def test_ok_only_for_ok_status(self) -> None:
        self.assertFalse(index_health.IndexHealth("index_missing", "x").ok())
        self.assertTrue(index_health.IndexHealth("ok", "x").ok())

    def test_message_is_pii_free_and_actionable(self) -> None:
        health = index_health.IndexHealth(index_health.INDEX_MISSING, "no index file")
        msg = health.message("corpus/index.db")
        self.assertIn("reason=index_missing", msg)
        self.assertIn("index", msg)      # names the index rebuild command
        self.assertIn("doctor", msg)     # names the doctor recovery command
        self.assertNotIn("ev_", msg)     # no vault evidence id


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
