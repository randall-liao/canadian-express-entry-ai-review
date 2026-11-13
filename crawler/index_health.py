"""Typed, read-only corpus-index preflight for the audit/report path (HARD-01/02).

The CRS auditor grounds every rule row against the corpus FTS5 index at ``--db``.
Before Phase 36 a missing / empty / corrupt / drifted index escaped deep in the
grounding gate as an uncaught ``sqlite3.OperationalError`` → a generic
``internal_error``/exit-4 envelope with a raw Python traceback and no recovery
hint. This module converts that into a *stable, PII-free, actionable* refusal on
the frozen ``contract`` vocabulary plus a specific machine reason code.

Design (mirrors ``crawler.doctor``'s PII-light dataclass shape and
``crawler.searchindex``'s read-only discipline):

* :func:`probe_index` opens the index **strictly read-only** (``file:<db>?mode=ro``)
  and NEVER writes / never creates a 0-byte DB — the same WR-03 discipline
  ``searchindex.resolve`` uses. It classifies the fault into a CLOSED reason-code
  vocabulary and returns a typed :class:`IndexHealth`.
* Every post-connect row/column read is wrapped so a truncated / "disk image
  malformed" file that only fails when actual row blobs are read refuses cleanly
  as ``index_corrupt`` instead of re-raising the very traceback this phase kills.
* The happy path is cheap: table presence + a bounded ``chunk_sha`` drift sample,
  never ``PRAGMA integrity_check`` (which is O(db) on the ~14 MB index).

The reusable CLI helper ``cli._require_readable_index`` turns a non-``ok``
:class:`IndexHealth` into the frozen ``invalid_input``/exit-2 refusal envelope —
the SAME code ``search``/``ground`` already return for a bad ``--db`` — reused by
``vault audit`` now and by ``remediate`` / ``review-packet`` in Phases 37–38.

Pure stdlib (``sqlite3``/``dataclasses``/``pathlib``) + the reused
``searchindex.chunk_sha`` fingerprint — zero new runtime dependency.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Closed reason-code vocabulary. ``status`` on IndexHealth is EXACTLY one of
# these; the CLI refusal embeds it as a stable ``reason=<code>`` token so an
# agent can branch on the machine reason without a new contract error type.
# --------------------------------------------------------------------------- #
INDEX_OK = "ok"
INDEX_MISSING = "index_missing"
INDEX_EMPTY = "index_empty"
INDEX_UNREADABLE = "index_unreadable"
INDEX_CORRUPT = "index_corrupt"
INDEX_DRIFTED = "index_drifted"

# --------------------------------------------------------------------------- #
# Closed reason-code vocabulary for a REQUIRED corpus *family* snapshot (SAFE-10).
# ``probe_snapshot`` is a strict additive MIRROR of ``probe_index`` (above): it
# reuses ``probe_index`` for the missing/empty/unreadable/corrupt/drifted base
# classes and adds two family-scoped codes — ``snapshot_missing`` (the index is
# healthy but carries NO rows under ``family/``) and ``snapshot_stale`` (the
# newest ``crawl_date`` is beyond a caller-supplied ``max_age_days``). Same
# ``reason=<code>`` stable-token discipline as INDEX_*.
# --------------------------------------------------------------------------- #
SNAPSHOT_OK = "ok"
SNAPSHOT_MISSING = "snapshot_missing"
SNAPSHOT_EMPTY = "snapshot_empty"
SNAPSHOT_UNREADABLE = "snapshot_unreadable"
SNAPSHOT_CORRUPT = "snapshot_corrupt"
SNAPSHOT_DRIFTED = "snapshot_drifted"
SNAPSHOT_STALE = "snapshot_stale"

# Translate a non-ok ``probe_index`` base status into its SNAPSHOT_* equivalent so
# the reused index classification surfaces under the snapshot vocabulary.
_INDEX_TO_SNAPSHOT = {
    INDEX_MISSING: SNAPSHOT_MISSING,
    INDEX_EMPTY: SNAPSHOT_EMPTY,
    INDEX_UNREADABLE: SNAPSHOT_UNREADABLE,
    INDEX_CORRUPT: SNAPSHOT_CORRUPT,
    INDEX_DRIFTED: SNAPSHOT_DRIFTED,
}

# The tables ``searchindex.build_index`` always creates; any absence = corrupt.
_REQUIRED_TABLES = frozenset({"chunks", "chunks_fts", "meta"})

# Bounded content-drift probe size (recompute chunk_sha for the first N chunks).
# Bounded on purpose so the happy-path preflight stays O(1)-ish on a 14 MB index;
# per-citation drift is still caught fail-closed by ``searchindex.resolve``.
_DRIFT_SAMPLE = 64


@dataclass(frozen=True)
class IndexHealth:
    """The typed result of :func:`probe_index` — a closed status + PII-free reason."""

    status: str
    reason: str

    def ok(self) -> bool:
        """True iff the index is usable (``status == "ok"``)."""
        return self.status == INDEX_OK

    def message(self, db: "str | Path") -> str:
        """A stable, PII-free refusal message with a reason code + recovery hint.

        The only path echoed is the caller-supplied ``--db`` (a corpus path, not
        applicant PII) — matching the existing ``not a file: {db}`` precedent. It
        names the existing ``index`` and ``doctor`` recovery commands (HARD-02).
        """
        return (
            f"corpus index unusable (reason={self.status}): {self.reason}. "
            f"Recover: rebuild it with "
            f"'corpus-crawler --json index corpus/ --db {db}', then verify with "
            f"'corpus-crawler --json doctor'."
        )


def probe_index(db: "str | Path") -> IndexHealth:
    """Classify the corpus index at *db* into the closed reason-code vocabulary.

    Read-only and side-effect-free: a missing path is ``index_missing`` (never a
    silently-created 0-byte DB). Fail-closed order: missing → empty (0-byte) →
    unreadable (cannot open ro) → corrupt (not sqlite / missing tables / row read
    fails) → empty (0 chunks) → drifted (sampled ``chunk_sha`` mismatch) → ok.
    """
    # Lazy import keeps a bare ``import crawler.index_health`` light and mirrors how
    # cli.py lazy-imports searchindex.
    from crawler.searchindex import chunk_sha

    p = Path(db)
    # WR-01: the pre-open filesystem checks can themselves raise (a permission-denied
    # parent directory -> PermissionError; a TOCTOU deletion race -> FileNotFoundError).
    # Fail closed to a clean IndexHealth, never an uncaught traceback.
    try:
        if not p.is_file():
            return IndexHealth(INDEX_MISSING, f"no index file at {p}")
        # A 0-byte file is a VALID empty SQLite database, so classify it as empty
        # BEFORE opening (otherwise the missing-tables branch would mislabel it corrupt).
        if p.stat().st_size == 0:
            return IndexHealth(INDEX_EMPTY, f"index file is empty (0 bytes): {p}")
    except FileNotFoundError:
        return IndexHealth(INDEX_MISSING, f"no index file at {p}")
    except OSError:
        return IndexHealth(INDEX_UNREADABLE, "cannot access index path")

    # Read-only URI connect: forbids any write, never creates the file, and raises
    # on a genuinely unreadable path/permission (WR-03 discipline).
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return IndexHealth(INDEX_UNREADABLE, "cannot open index read-only")

    try:
        # Guard the ENTIRE post-connect body: a non-sqlite file, a truncated /
        # "disk image malformed" DB, or a schema-shy table only fails when its
        # header/rows/columns are actually read — catch every such DatabaseError
        # and refuse cleanly as corrupt (never an uncaught traceback).
        try:
            names = {
                row[0]
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                )
            }
            missing = _REQUIRED_TABLES - names
            if missing:
                return IndexHealth(
                    INDEX_CORRUPT, f"missing index tables: {sorted(missing)}")

            n_chunks = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
            if not n_chunks:
                return IndexHealth(INDEX_EMPTY, "index has zero chunks")

            # Touch the FTS vtable so a malformed FTS index surfaces as corrupt.
            con.execute("SELECT count(*) FROM chunks_fts").fetchone()

            # Bounded content-drift probe: recompute the integrity fingerprint over
            # the STORED text and compare to the stored chunk_sha.
            for text, sha in con.execute(
                "SELECT text, chunk_sha FROM chunks LIMIT ?", (_DRIFT_SAMPLE,)
            ):
                # WR-02: a NULL / BLOB text cell (foreign / legacy / content-malformed
                # DB) is not a str — treat it as corrupt rather than letting chunk_sha
                # raise TypeError/AttributeError and escape as an uncaught traceback.
                if not isinstance(text, str):
                    return IndexHealth(
                        INDEX_CORRUPT, "index chunk text is not stored as text")
                if chunk_sha(text) != sha:
                    return IndexHealth(
                        INDEX_DRIFTED,
                        "indexed chunk text drifted from its integrity fingerprint",
                    )
        except (sqlite3.DatabaseError, TypeError, ValueError):
            return IndexHealth(INDEX_CORRUPT, "index tables unreadable")
    finally:
        con.close()

    return IndexHealth(INDEX_OK, "index readable and consistent")


@dataclass(frozen=True)
class SnapshotHealth:
    """The typed result of :func:`probe_snapshot` — a closed status + PII-free reason.

    Mirrors :class:`IndexHealth`: ``status`` is EXACTLY one of the ``SNAPSHOT_*``
    codes and the CLI refusal embeds it as a stable ``reason=<code>`` token.
    """

    status: str
    reason: str

    def ok(self) -> bool:
        """True iff the required snapshot family is present, consistent, and fresh."""
        return self.status == SNAPSHOT_OK

    def message(self, db: "str | Path") -> str:
        """A stable, PII-free refusal message with a reason code + recovery hint.

        The ONLY path echoed is the caller-supplied ``--db`` (a corpus path, not
        applicant PII) — matching the :meth:`IndexHealth.message` precedent. No
        vault-internal path, applicant value, or ``ev_`` evidence id ever crosses.
        """
        return (
            f"required corpus snapshot unusable (reason={self.status}): {self.reason}. "
            f"Recover: refresh the snapshot family and rebuild the corpus index at "
            f"{db}, then verify with 'corpus-crawler --json doctor'."
        )


def probe_snapshot(db, family, *, max_age_days=None, as_of=None) -> SnapshotHealth:
    """Classify a REQUIRED corpus *family* snapshot into the closed ``SNAPSHOT_*`` vocab.

    Read-only and side-effect-free — a strict additive mirror of :func:`probe_index`
    (never modifies it). Fail-closed order:

    * ``base = probe_index(db)``; any non-ok base status (missing/empty/unreadable/
      corrupt/drifted) is REUSED verbatim and surfaced under its SNAPSHOT_* equivalent.
    * no rows whose ``relpath`` is under ``family/`` → ``snapshot_missing``.
    * a row whose stored text drifted from its ``chunk_sha`` fingerprint (or is not
      stored as text) → ``snapshot_drifted`` (reuses the shipped ``chunk_sha``).
    * when a ``max_age_days`` bound is supplied by the caller: a newest ``crawl_date``
      beyond that bound — a family that cannot prove its age (no dated rows) — or a
      newest ``crawl_date`` AFTER ``as_of`` (a future / after-reference anomaly:
      clock skew, a crawler bug, or tampering) — fails closed to ``snapshot_stale``.
      The after-reference rejection mirrors the sibling ``crs_audit.within_freshness``
      (``0 <= delta <= window``), so both Phase-40 freshness surfaces agree that a
      future date is NOT fresh. The bound is ALWAYS caller-supplied; this module
      inlines no numeric max-age default (SAFE-09 no-inlined-volatile rule).
      ``as_of`` is the reference instant the age is measured against; an omitted
      ``as_of`` defaults to today (``date.today()``) — the ``None`` default is NEVER
      parsed as a literal date.
    * otherwise ``snapshot_ok``.
    """
    # Lazy imports keep a bare ``import crawler.index_health`` light (as ``probe_index`` does).
    from crawler.searchindex import chunk_sha

    base = probe_index(db)
    if not base.ok():
        return SnapshotHealth(_INDEX_TO_SNAPSHOT[base.status], base.reason)

    # A SECOND read-only URI connect (WR-03: never writes / never creates the file).
    # probe_index already proved the DB is a readable, non-corrupt sqlite index, but a
    # TOCTOU race — the file deleted, unmounted, or permission-changed between ``base =
    # probe_index(db)`` above and this open — can still make this connect raise. Guard it
    # exactly as ``probe_index`` guards its own connect (lines above) so a race refuses
    # cleanly as ``snapshot_unreadable`` instead of escaping as the raw
    # ``sqlite3.OperationalError`` / internal_error traceback this module exists to
    # eliminate (WR-02). Only enter the ``try/finally`` once the connection exists, so
    # ``finally: con.close()`` never runs against an unbound ``con``.
    try:
        con = sqlite3.connect(f"file:{Path(db)}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return SnapshotHealth(SNAPSHOT_UNREADABLE, "cannot open snapshot read-only")
    try:
        try:
            # PARAMETER-BOUND family filter — never an f-string in SQL (SQLi mitigation).
            rows = con.execute(
                "SELECT text, chunk_sha, crawl_date FROM chunks WHERE relpath LIKE ?",
                (f"{family}/%",),
            ).fetchall()
            if not rows:
                return SnapshotHealth(
                    SNAPSHOT_MISSING, f"no snapshot rows under {family}/")

            for text, sha, _cd in rows:
                # WR-02 non-str guard + reuse the shipped fingerprint (no new hash scheme).
                if not isinstance(text, str) or chunk_sha(text) != sha:
                    return SnapshotHealth(
                        SNAPSHOT_DRIFTED,
                        "snapshot chunk drifted from its integrity fingerprint")

            if max_age_days is not None:
                from datetime import date

                from crawler.crs_audit import _as_date
                # ``as_of`` defaults to "now": an omitted reference date means today —
                # matching the ``cli._require_readable_snapshot`` caller, which passes
                # ``date.today().isoformat()``. Parsing the literal ``None`` raised
                # ValueError (via ``date.fromisoformat("None")``) and mislabeled a fresh,
                # present family as ``snapshot_corrupt`` (WR-01). Only the ``None`` default
                # is substituted — an explicit (even malformed) ``as_of`` still flows
                # through ``_as_date`` and fails closed exactly as before. ``max_age_days``
                # stays caller-supplied; this materializes only the reference instant, not
                # any inlined volatile max-age bound (SAFE-09).
                as_of = as_of if as_of is not None else date.today().isoformat()
                dated = [_as_date(cd) for _t, _s, cd in rows if cd]
                if not dated:
                    # Cannot prove freshness → fail closed (never silently pass).
                    return SnapshotHealth(
                        SNAPSHOT_STALE,
                        "snapshot crawl_date missing — cannot prove freshness")
                newest = max(dated)
                delta = (_as_date(as_of) - newest).days
                # A newest crawl_date AFTER as_of (delta < 0) is a future /
                # after-reference anomaly — clock skew, a crawler bug, or tampering —
                # that cannot prove freshness, so it fails CLOSED to snapshot_stale
                # BEFORE the max-age comparison. This mirrors the sibling
                # crs_audit.within_freshness, whose `0 <= delta <= window` rejects an
                # after-reference date: without this guard the negative delta is never
                # `> max_age_days` and the family fell through to SNAPSHOT_OK — a
                # fail-OPEN asymmetry the freshness sibling does not share (WR-01
                # re-review). No new reason code: both branches surface snapshot_stale.
                if delta < 0:
                    return SnapshotHealth(
                        SNAPSHOT_STALE,
                        "snapshot crawl_date is after as_of — cannot prove freshness")
                if delta > max_age_days:
                    return SnapshotHealth(
                        SNAPSHOT_STALE, f"snapshot older than {max_age_days}d")
        except (sqlite3.DatabaseError, TypeError, ValueError):
            return SnapshotHealth(SNAPSHOT_CORRUPT, "snapshot rows unreadable")
    finally:
        con.close()

    return SnapshotHealth(SNAPSHOT_OK, "snapshot present and fresh")
