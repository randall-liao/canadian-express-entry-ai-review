"""Unit table for the required-corpus-family snapshot preflight (SAFE-10 — Phase 40 Plan 03).

Builds every snapshot-health state in a tempdir and asserts ``probe_snapshot`` classifies
it into the CLOSED ``SNAPSHOT_*`` reason-code vocabulary, read-only and side-effect-free.
``probe_snapshot`` is a strict additive mirror of the frozen ``probe_index`` — it REUSES
``probe_index`` for the missing/empty/unreadable/corrupt/drifted base classes and adds the
family-scoped ``snapshot_missing`` (no rows under ``family/``) and ``snapshot_stale`` (newest
``crawl_date`` beyond a caller-supplied ``max_age_days``) codes. Stdlib ``unittest`` ONLY —
no network, no real corpus, no ``corpus/dli/`` dependency, no vault.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import index_health
from crawler.searchindex import CHUNKS_DDL, FTS_DDL, chunk_sha


def _build_snapshot_index(db: Path, *, family: str, chunks: list[str],
                          tamper_first_sha: bool = False,
                          crawl_date: str = "2026-07-10") -> None:
    """Write a minimal but real searchindex-shaped DB with *chunks* rows under ``family/``.

    Extends the ``test_index_health._build_valid_index`` shape: every row's ``relpath`` is
    ``f"{family}/doc.md"`` and its ``crawl_date`` is settable so the freshness path can be
    exercised. ``tamper_first_sha`` stores a wrong ``chunk_sha`` for row 0 (drift).
    """
    con = sqlite3.connect(str(db))
    try:
        con.executescript(CHUNKS_DDL)
        con.executescript(FTS_DDL)
        con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        relpath = f"{family}/doc.md"
        for ordinal, text in enumerate(chunks):
            sha = chunk_sha(text)
            if tamper_first_sha and ordinal == 0:
                sha = "0" * len(sha)  # wrong fingerprint → drift
            cid = f"{relpath}#{ordinal:03d}"
            con.execute(
                "INSERT INTO chunks(chunk_id, relpath, source_url, title, "
                "section, crawl_date, source_type, chunk_sha, ordinal, text) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (cid, relpath, "", "", "", crawl_date, "", sha, ordinal, text))
        con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        con.commit()
    finally:
        con.close()


class ProbeSnapshotReasonCodes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_family_is_snapshot_missing(self) -> None:
        # A valid index with rows under 'guidance/' but NONE under 'dli/'.
        db = self.dir / "no-family.db"
        _build_snapshot_index(db, family="guidance", chunks=["alpha beta", "gamma delta"])
        self.assertEqual(index_health.probe_snapshot(db, "dli").status,
                         index_health.SNAPSHOT_MISSING)

    def test_missing_db_path_is_snapshot_missing_and_creates_nothing(self) -> None:
        db = self.dir / "nope.db"
        self.assertEqual(index_health.probe_snapshot(db, "dli").status,
                         index_health.SNAPSHOT_MISSING)
        # Read-only / side-effect-free: the probe must NOT create the file.
        self.assertFalse(db.exists())

    def test_zero_byte_file_is_snapshot_empty(self) -> None:
        db = self.dir / "empty.db"
        db.write_bytes(b"")
        self.assertEqual(index_health.probe_snapshot(db, "dli").status,
                         index_health.SNAPSHOT_EMPTY)

    def test_non_sqlite_bytes_is_snapshot_corrupt(self) -> None:
        db = self.dir / "corrupt.db"
        db.write_bytes(b"this is not a database at all")
        self.assertEqual(index_health.probe_snapshot(db, "dli").status,
                         index_health.SNAPSHOT_CORRUPT)

    def test_unreadable_base_maps_to_snapshot_unreadable(self) -> None:
        # The INDEX_* → SNAPSHOT_* base map translates an unreadable index deterministically
        # (a permission-denied probe is flaky under differing UIDs; assert the mapping directly).
        self.assertEqual(
            index_health._INDEX_TO_SNAPSHOT[index_health.INDEX_UNREADABLE],
            index_health.SNAPSHOT_UNREADABLE)

    def test_toctou_second_open_failure_refuses_snapshot_unreadable(self) -> None:
        # WR-02 regression: if the DB is deleted / unmounted / permission-changed AFTER the
        # base probe_index check but BEFORE probe_snapshot's OWN read-only connect (a TOCTOU
        # window), the second open must refuse cleanly as snapshot_unreadable — never escape
        # as the raw sqlite3.OperationalError / internal_error traceback this module kills.
        # Simulated deterministically (NO timing race): force the base probe to OK, then point
        # at a path with no database so the SECOND connect raises OperationalError.
        gone = self.dir / "vanished-after-probe.db"  # never created → 2nd ro-open fails
        with mock.patch.object(
            index_health, "probe_index",
            return_value=index_health.IndexHealth(index_health.INDEX_OK, "ok"),
        ):
            health = index_health.probe_snapshot(
                gone, "dli", max_age_days=30, as_of="2026-07-17")
        self.assertEqual(health.status, index_health.SNAPSHOT_UNREADABLE)
        self.assertFalse(health.ok())

    def test_tampered_chunk_sha_is_snapshot_drifted(self) -> None:
        db = self.dir / "drifted.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta gamma", "delta epsilon"],
                              tamper_first_sha=True)
        self.assertEqual(index_health.probe_snapshot(db, "dli").status,
                         index_health.SNAPSHOT_DRIFTED)

    def test_stale_crawl_date_is_snapshot_stale(self) -> None:
        db = self.dir / "stale.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta"],
                              crawl_date="2000-01-01")
        self.assertEqual(
            index_health.probe_snapshot(db, "dli", max_age_days=30,
                                        as_of="2026-07-17").status,
            index_health.SNAPSHOT_STALE)

    def test_future_crawl_date_after_as_of_fails_closed_to_stale(self) -> None:
        # WR-01 (re-review) regression: a newest crawl_date AFTER as_of (a future /
        # after-reference date — clock skew, a crawler bug, or tampering) cannot prove
        # freshness and must fail CLOSED to snapshot_stale, matching the sibling
        # crs_audit.within_freshness (test_crawl_after_reference_is_not_fresh: a crawl
        # after the reference date returns False). Previously the (as_of - newest) delta
        # went negative, was never > max_age_days, and probe_snapshot fell through to
        # SNAPSHOT_OK — a fail-OPEN asymmetry its freshness sibling does not share.
        # Deterministic: explicit as_of + a fixed far-future crawl_date (no wall clock).
        db = self.dir / "future.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta"],
                              crawl_date="2099-01-01")
        self.assertEqual(
            index_health.probe_snapshot(db, "dli", max_age_days=30,
                                        as_of="2026-07-17").status,
            index_health.SNAPSHOT_STALE)

    def test_all_blank_crawl_dates_fail_closed_to_stale(self) -> None:
        # A family that cannot prove its age never passes the freshness check.
        db = self.dir / "blank-dates.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta"], crawl_date="")
        self.assertEqual(
            index_health.probe_snapshot(db, "dli", max_age_days=30,
                                        as_of="2026-07-17").status,
            index_health.SNAPSHOT_STALE)

    def test_present_and_fresh_is_snapshot_ok(self) -> None:
        db = self.dir / "fresh.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta", "gamma delta"],
                              crawl_date="2026-07-10")
        health = index_health.probe_snapshot(db, "dli", max_age_days=3650,
                                             as_of="2026-07-17")
        self.assertEqual(health.status, index_health.SNAPSHOT_OK)
        self.assertTrue(health.ok())

    def test_max_age_none_skips_stale_check(self) -> None:
        # Even an ancient crawl_date is OK when no bound is supplied (stale check skipped).
        db = self.dir / "no-bound.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta"],
                              crawl_date="2000-01-01")
        health = index_health.probe_snapshot(db, "dli", max_age_days=None)
        self.assertEqual(health.status, index_health.SNAPSHOT_OK)
        self.assertTrue(health.ok())

    def test_default_as_of_uses_today_not_literal_none(self) -> None:
        # WR-01 regression: supplying max_age_days but LEAVING as_of at its None default
        # must measure freshness against TODAY — not parse the literal string "None"
        # (date.fromisoformat("None") -> ValueError, previously swallowed and mislabeling a
        # fresh, present family as snapshot_corrupt). A large bound over a fixed fixture date
        # keeps the assertion deterministic regardless of the wall clock.
        db = self.dir / "fresh-default-asof.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta", "gamma delta"],
                              crawl_date="2026-07-10")
        health = index_health.probe_snapshot(db, "dli", max_age_days=3650)  # as_of defaulted
        self.assertEqual(health.status, index_health.SNAPSHOT_OK)
        self.assertTrue(health.ok())

    def test_ok_only_for_ok_status(self) -> None:
        self.assertFalse(index_health.SnapshotHealth("snapshot_missing", "x").ok())
        self.assertTrue(index_health.SnapshotHealth("ok", "x").ok())

    def test_message_is_pii_free(self) -> None:
        health = index_health.SnapshotHealth(index_health.SNAPSHOT_MISSING,
                                             "no snapshot rows under dli/")
        msg = health.message("corpus/index.db")
        self.assertIn("reason=snapshot_missing", msg)  # stable machine reason token
        self.assertNotIn("ev_", msg)                   # no vault evidence id


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
