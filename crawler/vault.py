"""Candidate vault: private SQLite store + content-addressed raw files (Phase 29).

This is the PII-BEARING store the whole v4.0 milestone protects. It mirrors the
corpus-DB pattern (stable logical ids, content hashes, metadata tables, migrations
keyed on ``PRAGMA user_version``) but on the PRIVATE side of the boundary:

* The DB lives at ``<candidate-root>/vault.sqlite`` where ``candidate-root`` is
  ``crawler.paths.candidate_root(...)`` — always inside the git-ignored personal
  boundary, resolved and containment-checked (Plan 01).
* Raw documents are content-addressed on disk under ``files/raw/<sha256><ext>``;
  they are NEVER stored as SQLite BLOBs (locked constraint / ARCHITECTURE-v4.0).
* Two id namespaces are kept provably disjoint (VAULT-03): a candidate
  ``evidence_id`` (``ev_`` prefix) can never be mistaken for a corpus
  ``citation_id`` (``relpath#ordinal`` shape).

PII hygiene (mirrors ``checklist.load_profile``):
* ``yaml.safe_load`` ONLY — never the unsafe full loader (threat T-29-07).
* Error messages name the FIELD/TYPE only, never a value (threat T-29-05/07).
* Summaries + returns are PII-light (ids/counts/status); ``original_name`` and
  absolute paths stay in the DB / on disk only (threat T-29-05).
* Every filesystem write goes through ``crawler.paths.resolve_within`` — never
  string concatenation (threat T-29-04).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import ValidationError

from crawler import paths
from crawler.models.vault import (
    Candidate,
    CrsProfileFactor,
    DocumentSummary,
    ExtractedValue,
    ItaRound,
    VaultDocument,
    VaultSummary,
)

# Fallback parser version used ONLY when crawler.extraction is not importable on
# a lean install (extraction deps absent). When the engine IS present its
# ``PARSER_VERSION`` is the single source of truth (see current_parser_version).
DEFAULT_PARSER_VERSION = "1"

# --------------------------------------------------------------------------- #
# Schema / migrations — versioned via PRAGMA user_version. v1 (Phase 29) is the
# candidate/profile/document subset; v2 (Phase 30) adds the extraction /
# confirmation tables. Migrations are ADDITIVE and keyed on user_version so a
# Phase-29 DB upgrades in place without touching existing rows.
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = "3"

_SCHEMA_V1_DDL = """
CREATE TABLE IF NOT EXISTS vault_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    label        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crs_profile_factors (
    factor_id          TEXT PRIMARY KEY,
    factor_group       TEXT NOT NULL,
    claimed_points     INTEGER,
    claimed_level      TEXT,
    claimed_value_json TEXT NOT NULL,
    source             TEXT NOT NULL,      -- user_entry | profile_import | corrected
    confirmed_at       TEXT,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ita_rounds (
    round_id      TEXT PRIMARY KEY,
    candidate_id  TEXT NOT NULL REFERENCES candidates(candidate_id),
    round_label   TEXT NOT NULL,
    round_date    TEXT,
    program       TEXT,
    cutoff_score  INTEGER,
    claimed_score INTEGER,
    source        TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    document_id    TEXT PRIMARY KEY,
    candidate_id   TEXT NOT NULL REFERENCES candidates(candidate_id),
    evidence_id    TEXT NOT NULL UNIQUE,   -- private ev_ id (never a corpus citation)
    doc_type       TEXT NOT NULL,
    file_sha256    TEXT NOT NULL,
    storage_relpath TEXT NOT NULL,         -- relative to candidate root (private)
    original_name  TEXT,                   -- private; never echoed in public docs
    mime_type      TEXT,
    byte_size      INTEGER,
    page_count     INTEGER,
    added_at       TEXT NOT NULL,
    status         TEXT NOT NULL           -- added | extracted | confirmed | rejected
);
"""

# Phase 30 (schema v2) — extraction / confirmation tables. ADDITIVE: created with
# IF NOT EXISTS and only ever added to a DB via the ``version < 2`` migration
# branch, so a Phase-29 (v1) vault upgrades in place. DDL mirrors ARCHITECTURE-
# v4.0.md §"SQLite Schema Option" with the five confirmed_* binding columns added
# for SC4 staleness. ``parser_version`` (not extractor_version) is the single
# source of truth consumed by staleness.
_SCHEMA_V2_DDL = """
CREATE TABLE IF NOT EXISTS extraction_runs (
    extraction_run_id TEXT PRIMARY KEY,
    document_id       TEXT REFERENCES documents(document_id),
    started_at        TEXT,
    completed_at      TEXT,
    parser_version    TEXT NOT NULL,
    engine_json       TEXT NOT NULL,
    status            TEXT NOT NULL,       -- running | complete | failed
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS document_pages (
    page_id           TEXT PRIMARY KEY,
    document_id       TEXT NOT NULL REFERENCES documents(document_id),
    page_number       INTEGER NOT NULL,
    image_relpath     TEXT,                -- vault-relative (never absolute/stdout)
    text_relpath      TEXT,
    render_sha256     TEXT,
    ocr_sha256        TEXT,
    dpi               INTEGER,
    renderer          TEXT,
    width             INTEGER,
    height            INTEGER,
    quality_json      TEXT,
    extraction_run_id TEXT REFERENCES extraction_runs(extraction_run_id)
);

CREATE TABLE IF NOT EXISTS extracted_values (
    value_id             TEXT PRIMARY KEY,
    document_id          TEXT NOT NULL REFERENCES documents(document_id),
    page_id              TEXT REFERENCES document_pages(page_id),
    factor_id            TEXT REFERENCES crs_profile_factors(factor_id),
    field_name           TEXT NOT NULL,
    raw_text             TEXT,
    normalized_value_json TEXT NOT NULL,
    bbox_json            TEXT,
    extractor_confidence REAL,
    quality_flag         TEXT NOT NULL,    -- ok | low_quality | ambiguous
    extraction_run_id    TEXT NOT NULL REFERENCES extraction_runs(extraction_run_id),
    confirmation_status  TEXT NOT NULL,    -- pending | confirmed | corrected | rejected
    confirmed_value_json TEXT,
    confirmed_at         TEXT,
    confirmed_by         TEXT,
    -- Five SC4 staleness-binding keys, captured at confirm time:
    confirmed_file_sha256           TEXT,
    confirmed_render_sha256         TEXT,
    confirmed_parser_version        TEXT,
    confirmed_profile_claim_version TEXT,
    confirmed_rule_registry_version TEXT
);

CREATE TABLE IF NOT EXISTS factor_evidence (
    factor_id     TEXT NOT NULL REFERENCES crs_profile_factors(factor_id),
    value_id      TEXT NOT NULL REFERENCES extracted_values(value_id),
    evidence_role TEXT NOT NULL,           -- primary | supporting | issuer | date | score | hours | noc
    PRIMARY KEY (factor_id, value_id, evidence_role)
);
"""

# Phase 32 (schema v3) — audit-run + verdict trail. ADDITIVE: created with
# IF NOT EXISTS and only ever added to a DB via the ``version < 3`` migration
# branch, so a Phase-29/30 (v1/v2) vault upgrades in place without touching any
# existing candidate/profile/document/extraction row. These rows are PII-BEARING
# (they reference ``ev_`` evidence pointers + store the verdict/score delta) and
# therefore live ONLY inside the git-ignored ``vault.sqlite`` (already covered by
# the publish-safe ``VAULT_DB_SUFFIXES`` / ``VAULT_ARTIFACT`` rules).
#
# ID-NAMESPACE SEPARATION (VAULT-03): ``factor_verdicts.evidence_ids_json`` holds
# ONLY private ``ev_`` pointers and ``factor_verdicts.rule_citation_ids_json``
# holds ONLY corpus ``relpath#ordinal`` ids — the two namespaces stay in SEPARATE
# columns and never mix.
_SCHEMA_V3_DDL = """
CREATE TABLE IF NOT EXISTS audit_runs (
    audit_run_id        TEXT PRIMARY KEY,
    candidate_id        TEXT REFERENCES candidates(candidate_id),
    factor_id           TEXT,
    rule_registry_version TEXT,
    ita_round_id        TEXT REFERENCES ita_rounds(round_id),
    report_relpath      TEXT,               -- vault-relative report path (private)
    status              TEXT NOT NULL,      -- running | complete | failed
    substantiated_total INTEGER,
    cutoff_delta        INTEGER,
    started_at          TEXT NOT NULL,
    completed_at        TEXT
);

CREATE TABLE IF NOT EXISTS factor_verdicts (
    verdict_id             TEXT PRIMARY KEY,
    audit_run_id           TEXT NOT NULL REFERENCES audit_runs(audit_run_id),
    factor_id              TEXT NOT NULL,
    verdict                TEXT NOT NULL,    -- SUBSTANTIATED | GAP | AT-RISK | N/A
    reason_code            TEXT,
    substantiated_points   INTEGER,
    score_delta            INTEGER,
    evidence_ids_json      TEXT NOT NULL,    -- private ev_ pointers ONLY
    rule_citation_ids_json TEXT NOT NULL,    -- corpus relpath#ordinal ids ONLY
    created_at             TEXT NOT NULL
);
"""

# Seeded once on create; the ``evidence_id_prefix`` + ``citation_id_note`` record
# the VAULT-03 id-namespace contract inside the DB itself.
_META_SEED = {
    "schema_version": SCHEMA_VERSION,
    "vault_kind": "candidate",
    "evidence_id_prefix": "ev_",
    "citation_id_note": "corpus-only relpath#ordinal",
}

# Corpus citation-id shape: ``<relpath>#<ordinal>`` (e.g. ``a/b.md#003``). Used to
# PROVE (VAULT-03) that a minted ev_ evidence id is never a corpus citation.
_CITATION_ID_RE = re.compile(r"^.+#\d+$")


class VaultError(ValueError):
    """Raised on malformed vault input. Messages name the FIELD/TYPE only, never a value.

    A :class:`ValueError` subclass so the CLI maps it to ``invalid_input`` / exit 2.
    Mirrors ``checklist.ProfileError`` PII hygiene (threat T-29-05/07).
    """


@dataclass
class Vault:
    """Open handle to one candidate's private store.

    ``root`` is the resolved, containment-checked candidate root; every write is
    re-anchored to it via :func:`crawler.paths.resolve_within`.
    """

    candidate_id: str
    root: Path
    db_path: Path
    con: sqlite3.Connection


# --------------------------------------------------------------------------- #
# Time + id minting
# --------------------------------------------------------------------------- #
def _now() -> str:
    """UTC ISO-8601 second-precision timestamp (no microseconds, diff-friendly)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_document_id() -> str:
    """Mint an opaque logical document id: ``doc_`` + 12 hex chars."""
    return "doc_" + uuid.uuid4().hex[:12]


def new_evidence_id() -> str:
    """Mint an opaque PRIVATE evidence id: ``ev_`` + 12 hex chars (VAULT-03).

    The ``ev_`` prefix guarantees it can never match the corpus citation shape
    ``relpath#ordinal`` — proven disjoint by :func:`is_evidence_id` /
    :func:`is_citation_id`.
    """
    return "ev_" + uuid.uuid4().hex[:12]


def new_round_id() -> str:
    """Mint an opaque ITA-round id: ``ita_`` + 12 hex chars."""
    return "ita_" + uuid.uuid4().hex[:12]


def new_extraction_run_id() -> str:
    """Mint an opaque extraction-run id: ``ext_`` + 12 hex chars (Phase 30)."""
    return "ext_" + uuid.uuid4().hex[:12]


def new_page_id() -> str:
    """Mint an opaque document-page id: ``pg_`` + 12 hex chars (Phase 30)."""
    return "pg_" + uuid.uuid4().hex[:12]


def new_value_id() -> str:
    """Mint an opaque extracted-value id: ``val_`` + 12 hex chars (Phase 30)."""
    return "val_" + uuid.uuid4().hex[:12]


def new_audit_run_id() -> str:
    """Mint an opaque audit-run id: ``aud_`` + 12 hex chars (Phase 32).

    One ``aud_`` id per ``vault audit`` invocation. It is the durable ``run_id``
    the public envelope surfaces and the report filename shares.
    """
    return "aud_" + uuid.uuid4().hex[:12]


def new_verdict_id() -> str:
    """Mint an opaque factor-verdict id: ``ver_`` + 12 hex chars (Phase 32)."""
    return "ver_" + uuid.uuid4().hex[:12]


def new_remediation_id() -> str:
    """Mint an opaque remediation-run id: ``rem_`` + 12 hex chars (Phase 37).

    One ``rem_`` id per ``vault remediate`` invocation — the checklist filename +
    the public summary ``run_id`` share it. Mirrors :func:`new_audit_run_id`.
    """
    return "rem_" + uuid.uuid4().hex[:12]


def new_packet_id() -> str:
    """Mint an opaque review-packet id: ``pkt_`` + 12 hex chars (Phase 38).

    One ``pkt_`` id per ``vault review-packet`` invocation — the packet filename +
    the public summary ``run_id`` share it. Mirrors :func:`new_remediation_id`.
    """
    return "pkt_" + uuid.uuid4().hex[:12]


def is_evidence_id(s: str) -> bool:
    """True iff *s* is a candidate evidence id (``ev_`` prefix)."""
    return isinstance(s, str) and s.startswith("ev_")


def is_citation_id(s: str) -> bool:
    """True iff *s* has the corpus citation shape ``<relpath>#<ordinal>``."""
    return isinstance(s, str) and bool(_CITATION_ID_RE.match(s))


# --------------------------------------------------------------------------- #
# Open / migrate
# --------------------------------------------------------------------------- #
def _migrate(con: sqlite3.Connection) -> None:
    """Create/upgrade the schema, keyed on ``PRAGMA user_version``; idempotent.

    * A fresh DB (version 0) → create the v1 schema, seed meta, bump to 1, then
      fall through into the v2 (and v3) branches.
    * A Phase-29 DB (version 1) → run the ADDITIVE v2 DDL, seed
      ``rule_registry_version``, update the ``schema_version`` meta, bump to 2 —
      WITHOUT touching existing candidate/profile/document rows.
    * A Phase-30 DB (version 2) → run the ADDITIVE v3 DDL (audit_runs +
      factor_verdicts), update the ``schema_version`` meta, bump to 3 — WITHOUT
      touching any existing row.
    * An already-current DB (version 3) → no-op.
    """
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        con.executescript(_SCHEMA_V1_DDL)
        for key, value in _META_SEED.items():
            con.execute(
                "INSERT OR IGNORE INTO vault_meta(key, value) VALUES (?, ?)",
                (key, value),
            )
        con.execute("PRAGMA user_version = 1")
        con.commit()
        version = 1
    if version < 2:
        con.executescript(_SCHEMA_V2_DDL)
        # SC4 staleness reads this vault_meta key; default "0" until Phase 31.
        con.execute(
            "INSERT OR IGNORE INTO vault_meta(key, value) "
            "VALUES ('rule_registry_version', '0')")
        # Record the new schema version in meta (v1 DBs stored "1" here).
        con.execute(
            "INSERT INTO vault_meta(key, value) VALUES ('schema_version', '2') "
            "ON CONFLICT(key) DO UPDATE SET value = '2'")
        con.execute("PRAGMA user_version = 2")
        con.commit()
        version = 2
    if version < 3:
        # ADDITIVE Phase-32 audit trail: audit_runs + factor_verdicts. A v2 DB
        # upgrades in place (existing rows untouched); a fresh DB falls through
        # v1 → v2 → v3.
        con.executescript(_SCHEMA_V3_DDL)
        con.execute(
            "INSERT INTO vault_meta(key, value) VALUES ('schema_version', '3') "
            "ON CONFLICT(key) DO UPDATE SET value = '3'")
        con.execute("PRAGMA user_version = 3")
        con.commit()


def open_vault(candidate_id: str = "default",
               explicit: "str | Path | None" = None) -> Vault:
    """Open (creating if needed) the candidate vault under the personal boundary.

    Resolves ``candidate_root`` via :func:`crawler.paths.candidate_root` (which
    slugifies the id and containment-checks the path), ensures the directory
    exists, opens/creates ``vault.sqlite`` with ``PRAGMA foreign_keys=ON``, and
    runs migrations. Re-opening is idempotent.
    """
    root = paths.candidate_root(candidate_id, explicit)
    root.mkdir(parents=True, exist_ok=True)
    db_path = paths.resolve_within(root, "vault.sqlite")
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    _migrate(con)
    return Vault(
        candidate_id=paths.safe_candidate_id(candidate_id),
        root=root,
        db_path=db_path,
        con=con,
    )


def vault_meta(vault: Vault, key: str) -> str | None:
    """Read one ``vault_meta`` value by key (None if absent)."""
    row = vault.con.execute(
        "SELECT value FROM vault_meta WHERE key = ?", (key,)
    ).fetchone()
    return None if row is None else row["value"]


# --------------------------------------------------------------------------- #
# Candidate lifecycle
# --------------------------------------------------------------------------- #
def create_candidate(vault: Vault, candidate_id: str,
                     label: str | None = None) -> Candidate:
    """Insert a candidates row (safe-slug id, timestamps); idempotent.

    On a pre-existing id this is a no-op (label/timestamps preserved). Returns the
    current :class:`Candidate` either way.
    """
    cid = paths.safe_candidate_id(candidate_id)
    now = _now()
    vault.con.execute(
        "INSERT INTO candidates(candidate_id, label, created_at, updated_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(candidate_id) DO NOTHING",
        (cid, label, now, now),
    )
    vault.con.commit()
    candidate = select_candidate(vault, cid)
    assert candidate is not None  # just inserted-or-existing
    return candidate


def select_candidate(vault: Vault, candidate_id: str) -> Candidate | None:
    """Return the :class:`Candidate` for *candidate_id*, or None if absent."""
    cid = paths.safe_candidate_id(candidate_id)
    row = vault.con.execute(
        "SELECT candidate_id, label, created_at, updated_at "
        "FROM candidates WHERE candidate_id = ?",
        (cid,),
    ).fetchone()
    return None if row is None else Candidate(**dict(row))


def _ensure_candidate(vault: Vault, candidate_id: str) -> str:
    """Guarantee a candidates row exists (FK target) and return the safe-slug id.

    ITA rounds and documents carry a ``candidate_id`` FK; with
    ``foreign_keys=ON`` a write would fail if the parent row were missing. This
    keeps ``set_ita_round`` / ``import_document`` usable without a separate
    ``create_candidate`` call (Rule 2 — correctness).
    """
    cid = paths.safe_candidate_id(candidate_id)
    now = _now()
    vault.con.execute(
        "INSERT INTO candidates(candidate_id, label, created_at, updated_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(candidate_id) DO NOTHING",
        (cid, None, now, now),
    )
    return cid


# --------------------------------------------------------------------------- #
# CRS profile factors + ITA rounds (VAULT-01)
# --------------------------------------------------------------------------- #
def upsert_profile_factor(vault: Vault, factor: CrsProfileFactor) -> str:
    """Insert/update one CRS factor row keyed on ``factor_id``; returns the id.

    ``claimed_value`` is serialized to ``claimed_value_json`` via ``json.dumps``;
    ``updated_at`` is stamped now.
    """
    now = _now()
    claimed_value_json = json.dumps(factor.claimed_value)
    vault.con.execute(
        "INSERT INTO crs_profile_factors(factor_id, factor_group, claimed_points, "
        "claimed_level, claimed_value_json, source, confirmed_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(factor_id) DO UPDATE SET "
        "factor_group=excluded.factor_group, claimed_points=excluded.claimed_points, "
        "claimed_level=excluded.claimed_level, claimed_value_json=excluded.claimed_value_json, "
        "source=excluded.source, confirmed_at=excluded.confirmed_at, "
        "updated_at=excluded.updated_at",
        (factor.factor_id, factor.factor_group, factor.claimed_points,
         factor.claimed_level, claimed_value_json, factor.source,
         factor.confirmed_at, now),
    )
    vault.con.commit()
    return factor.factor_id


def load_profile_factors(vault: Vault,
                         candidate_id: str | None = None) -> list[CrsProfileFactor]:
    """Return all stored CRS factors as :class:`CrsProfileFactor` (id-ordered).

    ``candidate_id`` is accepted for API symmetry; factors are per-vault (the DB
    is per candidate root), so no cross-candidate filtering is applied.
    """
    rows = vault.con.execute(
        "SELECT factor_id, factor_group, claimed_points, claimed_level, "
        "claimed_value_json, source, confirmed_at, updated_at "
        "FROM crs_profile_factors ORDER BY factor_id"
    ).fetchall()
    return [
        CrsProfileFactor(
            factor_id=row["factor_id"],
            factor_group=row["factor_group"],
            claimed_points=row["claimed_points"],
            claimed_level=row["claimed_level"],
            claimed_value=json.loads(row["claimed_value_json"]),
            source=row["source"],
            confirmed_at=row["confirmed_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def _describe_validation(exc: ValidationError) -> str:
    """Summarize a pydantic error naming ONLY field path + error type — never a value.

    ``exc.errors()`` entries carry the offending ``input`` value and a ``msg`` that
    can embed it; we surface only ``loc`` + ``type`` so no profile PII leaks into
    the raised message (PII boundary — threat T-29-05/07).
    """
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "<root>"
        parts.append(f"field {loc!r} ({err.get('type', 'invalid')})")
    return "; ".join(parts)


def import_profile_yaml(vault: Vault, candidate_id: str,
                        yaml_path: "str | Path") -> list[CrsProfileFactor]:
    """Load a factors YAML (``safe_load`` only), validate each, upsert as import.

    Accepts either a mapping with a ``factors:`` list or a bare top-level list.
    Each entry is validated through :class:`CrsProfileFactor` with ``source`` forced
    to ``profile_import``. Malformed YAML/shape raises :class:`VaultError` whose
    message names only the field/type, NEVER a value (PII boundary — mirrors
    ``checklist.load_profile``).
    """
    source = Path(yaml_path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        # Name the reason only — never splice the OS exception (could echo a path).
        raise VaultError("could not read profile factors file") from exc

    try:
        data = yaml.safe_load(text)  # safe_load ONLY (threat T-29-07)
    except yaml.YAMLError as exc:
        # PyYAML's error __str__ embeds the offending source LINE (potential PII);
        # surface only PII-free line/column numbers, never the snippet.
        mark = getattr(exc, "problem_mark", None)
        where = (f" (line {mark.line + 1}, column {mark.column + 1})"
                 if mark is not None else "")
        raise VaultError(f"invalid YAML in profile factors{where}") from exc

    if isinstance(data, dict):
        entries = data.get("factors")
    elif isinstance(data, list):
        entries = data
    else:
        raise VaultError(
            f"profile factors must be a mapping or list; got {type(data).__name__}"
        )
    if not isinstance(entries, list):
        raise VaultError("profile factors 'factors' must be a list")

    imported: list[CrsProfileFactor] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise VaultError(
                f"profile factor #{i} must be a mapping; got {type(entry).__name__}"
            )
        try:
            factor = CrsProfileFactor(**{**entry, "source": "profile_import"})
        except ValidationError as exc:
            raise VaultError(
                f"invalid profile factor #{i}: {_describe_validation(exc)}"
            ) from exc
        upsert_profile_factor(vault, factor)
        imported.append(factor)
    return imported


def set_ita_round(vault: Vault, candidate_id: str, round_label: str,
                  round_date: str | None, program: str | None,
                  cutoff_score: int | None,
                  claimed_score: int | None = None) -> ItaRound:
    """Insert an ITA round row with a minted ``ita_`` round id; returns the row."""
    cid = _ensure_candidate(vault, candidate_id)
    round_id = new_round_id()
    now = _now()
    vault.con.execute(
        "INSERT INTO ita_rounds(round_id, candidate_id, round_label, round_date, "
        "program, cutoff_score, claimed_score, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (round_id, cid, round_label, round_date, program, cutoff_score,
         claimed_score, "user_entry", now),
    )
    vault.con.commit()
    return ItaRound(
        round_id=round_id, candidate_id=cid, round_label=round_label,
        round_date=round_date, program=program, cutoff_score=cutoff_score,
        claimed_score=claimed_score, source="user_entry", created_at=now,
    )


def summarize_vault(vault: Vault, candidate_id: str) -> VaultSummary:
    """Return a PII-LIGHT :class:`VaultSummary`: counts + ids/statuses only.

    Deliberately omits ``claimed_points`` values, ``original_name``, and any
    filesystem path (threat T-29-05). ``groups_present`` lists which CRS factor
    groups have at least one factor.
    """
    cid = paths.safe_candidate_id(candidate_id)
    factor_count = vault.con.execute(
        "SELECT COUNT(*) FROM crs_profile_factors"
    ).fetchone()[0]
    groups = [
        r["factor_group"] for r in vault.con.execute(
            "SELECT DISTINCT factor_group FROM crs_profile_factors "
            "ORDER BY factor_group"
        ).fetchall()
    ]
    ita_count = vault.con.execute(
        "SELECT COUNT(*) FROM ita_rounds WHERE candidate_id = ?", (cid,)
    ).fetchone()[0]
    doc_rows = vault.con.execute(
        "SELECT document_id, evidence_id, doc_type, status FROM documents "
        "WHERE candidate_id = ? ORDER BY added_at, document_id", (cid,)
    ).fetchall()
    documents = [
        DocumentSummary(
            document_id=r["document_id"], evidence_id=r["evidence_id"],
            doc_type=r["doc_type"], status=r["status"],
        )
        for r in doc_rows
    ]
    return VaultSummary(
        candidate_id=cid,
        factor_count=factor_count,
        ita_round_count=ita_count,
        document_count=len(documents),
        groups_present=groups,
        documents=documents,
    )


# --------------------------------------------------------------------------- #
# Content-addressed document ingest (VAULT-02/03)
# --------------------------------------------------------------------------- #
def import_document(vault: Vault, candidate_id: str, src_path: "str | Path",
                    doc_type: str, mime_type: str | None = None) -> DocumentSummary:
    """Import a raw document as a content-addressed file + private documents row.

    Reads *src_path* bytes, computes the sha256, and writes them to
    ``resolve_within(candidate_root, "files","raw", <sha256><ext>)`` — the DEST is
    ALWAYS re-anchored through :func:`crawler.paths.resolve_within`, so it can
    never escape the vault (threat T-29-04), regardless of *src_path*. Identical
    bytes reuse the same on-disk file (content dedup) while still recording a
    DISTINCT ``documents`` row (distinct ``document_id``/``evidence_id``).

    ``original_name`` is stored PRIVATELY in the DB column only; the RETURNED
    :class:`DocumentSummary` carries ids/type/status ONLY — never the original
    filename, never an absolute path (threat T-29-05). Never touches ``corpus/``
    (threat T-29-08).
    """
    cid = _ensure_candidate(vault, candidate_id)
    src = Path(src_path)
    try:
        data = src.read_bytes()  # user chose the file; reading it is permitted
    except OSError as exc:
        # Name the reason only — never splice the OS exception (could echo a path).
        raise VaultError("could not read source document") from exc

    sha256 = hashlib.sha256(data).hexdigest()
    ext = src.suffix.lower() or ".bin"
    filename = sha256 + ext
    # Dest ALWAYS via resolve_within — a forged/escaping dest raises PathEscapeError.
    dest = paths.resolve_within(vault.root, "files", "raw", filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)  # content-addressed: identical bytes → one file

    storage_relpath = f"files/raw/{filename}"  # RELATIVE to candidate root
    document_id = new_document_id()
    evidence_id = new_evidence_id()
    now = _now()
    vault.con.execute(
        "INSERT INTO documents(document_id, candidate_id, evidence_id, doc_type, "
        "file_sha256, storage_relpath, original_name, mime_type, byte_size, "
        "page_count, added_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (document_id, cid, evidence_id, doc_type, sha256, storage_relpath,
         src.name, mime_type, len(data), None, now, "added"),
    )
    vault.con.commit()
    # PII-LIGHT return: ids/type/status only (never original_name / abs path).
    return DocumentSummary(
        document_id=document_id, evidence_id=evidence_id,
        doc_type=doc_type, status="added",
    )


# --------------------------------------------------------------------------- #
# Extraction / confirmation store (Phase 30 — Plan 01). These are the ONLY write
# paths the extraction engine (Plan 02) and confirmation workflow (Plan 03) use.
# The quarantine invariant lives here: ``add_extracted_value`` ALWAYS persists
# ``confirmation_status='pending'`` — a value can never be born confirmed.
# --------------------------------------------------------------------------- #
def record_extraction_run(vault: Vault, *, document_id: str,
                          parser_version: str,
                          engine_json: "Any" = None,
                          status: str = "running",
                          notes: str | None = None) -> str:
    """Insert an ``extraction_runs`` row; return the minted ``ext_`` run id.

    ``parser_version`` is the single source of truth (``extraction.PARSER_VERSION``)
    that SC4 staleness compares against. ``engine_json`` (tool versions) is stored
    NOT-NULL as a JSON string.
    """
    run_id = new_extraction_run_id()
    now = _now()
    completed_at = now if status in ("complete", "failed") else None
    vault.con.execute(
        "INSERT INTO extraction_runs(extraction_run_id, document_id, started_at, "
        "completed_at, parser_version, engine_json, status, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, document_id, now, completed_at, parser_version,
         json.dumps(engine_json if engine_json is not None else {}),
         status, notes),
    )
    vault.con.commit()
    return run_id


def complete_extraction_run(vault: Vault, extraction_run_id: str, *,
                            status: str = "complete",
                            notes: str | None = None) -> None:
    """Stamp ``completed_at`` + ``status`` on an existing extraction run."""
    now = _now()
    if notes is None:
        vault.con.execute(
            "UPDATE extraction_runs SET status = ?, completed_at = ? "
            "WHERE extraction_run_id = ?",
            (status, now, extraction_run_id))
    else:
        vault.con.execute(
            "UPDATE extraction_runs SET status = ?, completed_at = ?, notes = ? "
            "WHERE extraction_run_id = ?",
            (status, now, notes, extraction_run_id))
    vault.con.commit()


def add_document_page(vault: Vault, *, document_id: str, page_number: int,
                      image_relpath: str | None = None,
                      text_relpath: str | None = None,
                      render_sha256: str | None = None,
                      ocr_sha256: str | None = None,
                      dpi: int | None = None,
                      renderer: str | None = None,
                      width: int | None = None,
                      height: int | None = None,
                      quality_json: "Any" = None,
                      extraction_run_id: str | None = None) -> str:
    """Insert a ``document_pages`` row; return the minted ``pg_`` page id.

    ``image_relpath`` / ``text_relpath`` MUST be vault-relative (the engine writes
    through ``paths.resolve_within``); they are never emitted on stdout.
    """
    page_id = new_page_id()
    vault.con.execute(
        "INSERT INTO document_pages(page_id, document_id, page_number, "
        "image_relpath, text_relpath, render_sha256, ocr_sha256, dpi, renderer, "
        "width, height, quality_json, extraction_run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (page_id, document_id, page_number, image_relpath, text_relpath,
         render_sha256, ocr_sha256, dpi, renderer, width, height,
         json.dumps(quality_json) if quality_json is not None else None,
         extraction_run_id),
    )
    vault.con.commit()
    return page_id


def add_extracted_value(vault: Vault, *, document_id: str,
                        page_id: str | None, factor_id: str | None,
                        field_name: str, raw_text: str | None,
                        normalized_value: "Any", bbox: "Any",
                        extractor_confidence: float | None,
                        quality_flag: str,
                        extraction_run_id: str) -> str:
    """Insert one proposed value as ``pending``; return the ``val_`` value id.

    QUARANTINE INVARIANT (T-30-01 / SC3): ``confirmation_status`` is FORCED to
    ``'pending'`` on every insert regardless of any status the caller might try to
    pass — extraction can never write a born-confirmed value. The caller-supplied
    ``quality_flag`` is validated through the :class:`ExtractedValue` model so an
    out-of-vocabulary field_name/quality is rejected at the boundary (PII-safe
    message names the field/type only).
    """
    value_id = new_value_id()
    # Validate field_name/quality_flag at the boundary (PII-light on error).
    try:
        ExtractedValue(
            value_id=value_id, document_id=document_id, page_id=page_id,
            factor_id=factor_id, field_name=field_name, raw_text=raw_text,
            normalized_value=normalized_value, bbox=bbox,
            extractor_confidence=extractor_confidence, quality_flag=quality_flag,
            extraction_run_id=extraction_run_id, confirmation_status="pending",
        )
    except ValidationError as exc:
        raise VaultError(
            f"invalid extracted value: {_describe_validation(exc)}") from exc
    vault.con.execute(
        "INSERT INTO extracted_values(value_id, document_id, page_id, factor_id, "
        "field_name, raw_text, normalized_value_json, bbox_json, "
        "extractor_confidence, quality_flag, extraction_run_id, "
        "confirmation_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
        (value_id, document_id, page_id, factor_id, field_name, raw_text,
         json.dumps(normalized_value),
         json.dumps(bbox) if bbox is not None else None,
         extractor_confidence, quality_flag, extraction_run_id),
    )
    vault.con.commit()
    return value_id


def link_factor_evidence(vault: Vault, factor_id: str, value_id: str,
                         evidence_role: str = "primary") -> None:
    """Link an extracted value to a CRS factor with a role (idempotent)."""
    vault.con.execute(
        "INSERT OR IGNORE INTO factor_evidence(factor_id, value_id, evidence_role) "
        "VALUES (?, ?, ?)", (factor_id, value_id, evidence_role))
    vault.con.commit()


def _row_to_extracted_value(row: sqlite3.Row) -> ExtractedValue:
    """Hydrate an ``extracted_values`` row into an :class:`ExtractedValue`."""
    return ExtractedValue(
        value_id=row["value_id"],
        document_id=row["document_id"],
        page_id=row["page_id"],
        factor_id=row["factor_id"],
        field_name=row["field_name"],
        raw_text=row["raw_text"],
        normalized_value=json.loads(row["normalized_value_json"]),
        bbox=json.loads(row["bbox_json"]) if row["bbox_json"] is not None else None,
        extractor_confidence=row["extractor_confidence"],
        quality_flag=row["quality_flag"],
        extraction_run_id=row["extraction_run_id"],
        confirmation_status=row["confirmation_status"],
        confirmed_value=(json.loads(row["confirmed_value_json"])
                         if row["confirmed_value_json"] is not None else None),
        confirmed_at=row["confirmed_at"],
        confirmed_by=row["confirmed_by"],
        confirmed_file_sha256=row["confirmed_file_sha256"],
        confirmed_render_sha256=row["confirmed_render_sha256"],
        confirmed_parser_version=row["confirmed_parser_version"],
        confirmed_profile_claim_version=row["confirmed_profile_claim_version"],
        confirmed_rule_registry_version=row["confirmed_rule_registry_version"],
    )


def list_extracted_values(vault: Vault, document_id: str | None = None,
                          status: str | None = None) -> list[ExtractedValue]:
    """Return extracted values (id-ordered), optionally filtered by doc/status."""
    clauses, params = [], []
    if document_id is not None:
        clauses.append("document_id = ?")
        params.append(document_id)
    if status is not None:
        clauses.append("confirmation_status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = vault.con.execute(
        "SELECT * FROM extracted_values" + where + " ORDER BY value_id", params
    ).fetchall()
    return [_row_to_extracted_value(r) for r in rows]


def get_extracted_value(vault: Vault, value_id: str) -> ExtractedValue | None:
    """Return one :class:`ExtractedValue` by id, or None if absent."""
    row = vault.con.execute(
        "SELECT * FROM extracted_values WHERE value_id = ?", (value_id,)
    ).fetchone()
    return None if row is None else _row_to_extracted_value(row)


def live_registry_snapshot():
    """Return one validated live registry snapshot loaded from disk now.

    The lazy import avoids a module cycle while keeping confirmation and
    eligibility on one production seam.  Mutable vault metadata is deliberately
    not consulted: it cannot attest to the content of the live rule rows.
    """
    try:
        from crawler import crs_rules

        return crs_rules.load_registry_snapshot()
    except Exception:  # noqa: BLE001 - any registry failure fails closed
        raise VaultError("rule registry unavailable") from None


def live_registry_fingerprint() -> str:
    """Return the fingerprint from one validated live-registry snapshot."""
    return live_registry_snapshot().fingerprint


def rule_registry_version(
    vault: Vault,
    *,
    registry_fingerprint: str | None = None,
) -> str:
    """Compatibility accessor backed by the canonical live registry."""
    del vault
    return (
        registry_fingerprint
        if registry_fingerprint is not None
        else live_registry_fingerprint()
    )


def set_rule_registry_version(vault: Vault, version: str) -> None:
    """Set legacy metadata; live registry content remains authoritative."""
    vault.con.execute(
        "INSERT INTO vault_meta(key, value) VALUES ('rule_registry_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(version),))
    vault.con.commit()


# --------------------------------------------------------------------------- #
# Trust predicates (Phase 30 — Plan 01). The entire milestone's fail-closed
# ethos rests on these two functions: ``is_audit_eligible`` (SC3 quarantine gate)
# and ``is_stale`` (SC4 five-key staleness). A later auditor (Phase 32) must cross
# this barrier via ``audit_eligible_values`` ONLY.
# --------------------------------------------------------------------------- #
def current_parser_version() -> str:
    """Return the extraction pipeline's parser version — single source of truth.

    Imports ``PARSER_VERSION`` LAZILY from :mod:`crawler.extraction` when the
    engine (and its deps) are present; otherwise falls back to
    :data:`DEFAULT_PARSER_VERSION` so this module still imports on a lean install
    with the extraction deps absent (SC4 remains testable without them).
    """
    try:
        from crawler.extraction import PARSER_VERSION
        return PARSER_VERSION
    except Exception:  # noqa: BLE001 - lean install / any import failure → fallback
        return DEFAULT_PARSER_VERSION


def profile_claim_version(vault: Vault, factor_id: str | None) -> str | None:
    """Stable short hash of a factor's claim (claimed_value/level/points).

    This is the profile-claim version SC4 binds a confirmation to: editing the
    linked factor's claim changes the hash and invalidates the confirmation.
    Returns None when ``factor_id`` is None (unlinked value) or the factor is
    absent — a None binding that later gains a value counts as a change.
    """
    if factor_id is None:
        return None
    row = vault.con.execute(
        "SELECT claimed_value_json, claimed_level, claimed_points "
        "FROM crs_profile_factors WHERE factor_id = ?", (factor_id,)
    ).fetchone()
    if row is None:
        return None
    basis = json.dumps(
        {"value": row["claimed_value_json"],
         "level": row["claimed_level"],
         "points": row["claimed_points"]},
        sort_keys=True,
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _value_binding_context(vault: Vault, value_id: str):
    """Return (row, current_file_sha, current_render_sha) for a value, or None.

    ``row`` is the raw ``extracted_values`` row; the two shas are the CURRENT
    values of the file/render binding keys (used by both confirm capture and
    staleness comparison).
    """
    row = vault.con.execute(
        "SELECT * FROM extracted_values WHERE value_id = ?", (value_id,)
    ).fetchone()
    if row is None:
        return None
    file_row = vault.con.execute(
        "SELECT file_sha256 FROM documents WHERE document_id = ?",
        (row["document_id"],)
    ).fetchone()
    current_file_sha = file_row["file_sha256"] if file_row is not None else None
    current_render_sha = None
    if row["page_id"] is not None:
        page_row = vault.con.execute(
            "SELECT render_sha256 FROM document_pages WHERE page_id = ?",
            (row["page_id"],)
        ).fetchone()
        current_render_sha = (page_row["render_sha256"]
                              if page_row is not None else None)
    return row, current_file_sha, current_render_sha


def confirm_value(vault: Vault, value_id: str, decision: str,
                  corrected_value: "Any" = None,
                  confirmed_by: str | None = None,
                  *,
                  registry_fingerprint: str | None = None) -> None:
    """Apply ONE field-level confirm/correct/reject decision (SC3/SC4).

    ``confirm`` / ``correct`` set the status accordingly, stamp ``confirmed_at``,
    store the corrected value (correct only), and CAPTURE the five staleness
    binding keys (file sha, render sha, parser version, profile-claim version,
    rule-registry version) as they are NOW. ``reject`` sets status ``rejected``
    and CLEARS the binding columns + confirmed value. An unknown decision or
    value id raises :class:`VaultError` (field/type only — PII-safe).
    """
    if decision not in ("confirm", "correct", "reject"):
        raise VaultError("decision must be confirm | correct | reject")
    ctx = _value_binding_context(vault, value_id)
    if ctx is None:
        raise VaultError("unknown value_id")
    row, current_file_sha, current_render_sha = ctx
    now = _now()
    if decision == "reject":
        vault.con.execute(
            "UPDATE extracted_values SET confirmation_status = 'rejected', "
            "confirmed_at = ?, confirmed_by = ?, confirmed_value_json = NULL, "
            "confirmed_file_sha256 = NULL, confirmed_render_sha256 = NULL, "
            "confirmed_parser_version = NULL, confirmed_profile_claim_version = NULL, "
            "confirmed_rule_registry_version = NULL WHERE value_id = ?",
            (now, confirmed_by, value_id),
        )
        vault.con.commit()
        return
    status = "confirmed" if decision == "confirm" else "corrected"
    run_row = vault.con.execute(
        "SELECT parser_version FROM extraction_runs WHERE extraction_run_id = ?",
        (row["extraction_run_id"],)
    ).fetchone()
    confirmed_parser_version = (run_row["parser_version"]
                                if run_row is not None else None)
    confirmed_claim_version = profile_claim_version(vault, row["factor_id"])
    confirmed_registry_version = rule_registry_version(
        vault, registry_fingerprint=registry_fingerprint)
    confirmed_value_json = (json.dumps(corrected_value)
                            if decision == "correct" else None)
    vault.con.execute(
        "UPDATE extracted_values SET confirmation_status = ?, confirmed_at = ?, "
        "confirmed_by = ?, confirmed_value_json = ?, confirmed_file_sha256 = ?, "
        "confirmed_render_sha256 = ?, confirmed_parser_version = ?, "
        "confirmed_profile_claim_version = ?, confirmed_rule_registry_version = ? "
        "WHERE value_id = ?",
        (status, now, confirmed_by, confirmed_value_json, current_file_sha,
         current_render_sha, confirmed_parser_version, confirmed_claim_version,
         confirmed_registry_version, value_id),
    )
    vault.con.commit()


def is_stale(vault: Vault, value_id: str, *,
             registry_fingerprint: str | None = None) -> bool:
    """True iff any of a confirmed value's five binding keys no longer matches.

    Meaningful only for confirmed/corrected values (pending/rejected are handled
    as not-eligible upstream, so this returns False for them). A binding that was
    captured as None but now has a value — or vice versa — counts as a change.
    """
    ctx = _value_binding_context(vault, value_id)
    if ctx is None:
        return False
    row, current_file_sha, current_render_sha = ctx
    if row["confirmation_status"] not in ("confirmed", "corrected"):
        return False
    try:
        current_registry = (
            registry_fingerprint
            if registry_fingerprint is not None
            else live_registry_fingerprint()
        )
    except VaultError:
        return True
    current = (
        current_file_sha,
        current_render_sha,
        current_parser_version(),
        profile_claim_version(vault, row["factor_id"]),
        current_registry,
    )
    confirmed = (
        row["confirmed_file_sha256"],
        row["confirmed_render_sha256"],
        row["confirmed_parser_version"],
        row["confirmed_profile_claim_version"],
        row["confirmed_rule_registry_version"],
    )
    return current != confirmed


def is_audit_eligible(vault: Vault, value_id: str, *,
                      registry_fingerprint: str | None = None) -> bool:
    """The SC3 quarantine gate: the ONLY predicate an auditor may trust.

    True iff confirmation_status ∈ (confirmed, corrected) AND quality_flag == 'ok'
    AND not stale. Pending, rejected, low_quality, ambiguous, and stale-but-
    confirmed values are ALL ineligible — a silent misread (Pitfall 1) or a stale
    confirmation (Pitfall 12) can never cross into a green verdict.
    """
    row = vault.con.execute(
        "SELECT confirmation_status, quality_flag FROM extracted_values "
        "WHERE value_id = ?", (value_id,)
    ).fetchone()
    if row is None:
        return False
    if row["confirmation_status"] not in ("confirmed", "corrected"):
        return False
    if row["quality_flag"] != "ok":
        return False
    return not is_stale(
        vault, value_id, registry_fingerprint=registry_fingerprint)


def audit_eligible_values(
    vault: Vault,
    factor_id: str,
    *,
    registry_fingerprint: str | None = None,
) -> list[ExtractedValue]:
    """Return the audit-eligible values for a factor (single safe auditor entry).

    Implements the ARCHITECTURE-v4.0 auditor query (status IN confirmed/corrected)
    FURTHER filtered by quality_flag=='ok' and not-stale, so Phase 32 auditors get
    exactly the values that may support a verdict — nothing more.
    """
    if registry_fingerprint is None:
        try:
            registry_fingerprint = live_registry_fingerprint()
        except VaultError:
            return []
    rows = vault.con.execute(
        "SELECT value_id FROM extracted_values WHERE factor_id = ? "
        "AND confirmation_status IN ('confirmed', 'corrected') ORDER BY value_id",
        (factor_id,)
    ).fetchall()
    result: list[ExtractedValue] = []
    for r in rows:
        if is_audit_eligible(
                vault, r["value_id"],
                registry_fingerprint=registry_fingerprint):
            value = get_extracted_value(vault, r["value_id"])
            if value is not None:
                result.append(value)
    return result


# --------------------------------------------------------------------------- #
# Audit-run + factor-verdict trail (Phase 32 — schema v3). PII-BEARING rows that
# persist ONLY inside vault.sqlite. ``evidence_ids`` (ev_ pointers) and
# ``rule_citation_ids`` (corpus relpath#ordinal) are json-serialized into SEPARATE
# columns and NEVER mix (VAULT-03). The report writer (Plan 04) records these only
# AFTER a successful verdict, so a grounding failure leaves no orphan row.
# --------------------------------------------------------------------------- #
_VERDICT_VOCAB = ("SUBSTANTIATED", "GAP", "AT-RISK", "N/A")


def record_audit_run(vault: Vault, *, candidate_id: str, factor_id: str,
                     rule_registry_version: str,
                     ita_round_id: str | None = None,
                     report_relpath: str | None = None,
                     status: str = "running",
                     substantiated_total: int | None = None,
                     cutoff_delta: int | None = None) -> str:
    """Insert an ``audit_runs`` row; return the minted ``aud_`` run id.

    Stamps ``started_at=_now()``. ``report_relpath`` is a vault-RELATIVE path
    (never absolute / never emitted on stdout). The two id/total columns are
    updated later by :func:`complete_audit_run` once a verdict is written.
    """
    audit_run_id = new_audit_run_id()
    _insert_audit_run(
        vault,
        audit_run_id=audit_run_id,
        candidate_id=candidate_id,
        factor_id=factor_id,
        rule_registry_version=rule_registry_version,
        ita_round_id=ita_round_id,
        report_relpath=report_relpath,
        status=status,
        substantiated_total=substantiated_total,
        cutoff_delta=cutoff_delta,
    )
    vault.con.commit()
    return audit_run_id


def _insert_audit_run(vault: Vault, *, audit_run_id: str,
                      candidate_id: str, factor_id: str,
                      rule_registry_version: str,
                      ita_round_id: str | None = None,
                      report_relpath: str | None = None,
                      status: str = "running",
                      substantiated_total: int | None = None,
                      cutoff_delta: int | None = None) -> None:
    """Insert a run without committing, for report-writer transactions."""
    now = _now()
    completed_at = now if status in ("complete", "failed") else None
    vault.con.execute(
        "INSERT INTO audit_runs(audit_run_id, candidate_id, factor_id, "
        "rule_registry_version, ita_round_id, report_relpath, status, "
        "substantiated_total, cutoff_delta, started_at, completed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (audit_run_id, candidate_id, factor_id, rule_registry_version,
         ita_round_id, report_relpath, status, substantiated_total,
         cutoff_delta, now, completed_at),
    )


def complete_audit_run(vault: Vault, audit_run_id: str, *,
                       status: str = "complete",
                       report_relpath: str | None = None,
                       substantiated_total: int | None = None,
                       cutoff_delta: int | None = None) -> None:
    """Stamp ``completed_at`` + ``status`` (and totals / report path) on a run.

    The report writer calls this AFTER a successful verdict is written (Plan 04),
    so a completed row always points at a real vault report.
    """
    _complete_audit_run(
        vault,
        audit_run_id,
        status=status,
        report_relpath=report_relpath,
        substantiated_total=substantiated_total,
        cutoff_delta=cutoff_delta,
    )
    vault.con.commit()


def _complete_audit_run(vault: Vault, audit_run_id: str, *,
                        status: str = "complete",
                        report_relpath: str | None = None,
                        substantiated_total: int | None = None,
                        cutoff_delta: int | None = None) -> None:
    """Complete a run without committing, for report-writer transactions."""
    now = _now()
    vault.con.execute(
        "UPDATE audit_runs SET status = ?, completed_at = ?, "
        "report_relpath = COALESCE(?, report_relpath), "
        "substantiated_total = COALESCE(?, substantiated_total), "
        "cutoff_delta = COALESCE(?, cutoff_delta) WHERE audit_run_id = ?",
        (status, now, report_relpath, substantiated_total, cutoff_delta,
         audit_run_id),
    )


def record_factor_verdict(vault: Vault, *, audit_run_id: str, factor_id: str,
                          verdict: str, reason_code: str | None = None,
                          substantiated_points: int | None = None,
                          score_delta: int | None = None,
                          evidence_ids, rule_citation_ids) -> str:
    """Insert one ``factor_verdicts`` row; return the minted ``ver_`` id.

    ``evidence_ids`` (private ``ev_`` pointers) and ``rule_citation_ids`` (corpus
    ``relpath#ordinal`` ids) are ``json.dumps``-ed into their SEPARATE columns —
    the two id namespaces never cross columns (VAULT-03). Raises
    :class:`VaultError` (field/type only — PII-safe) if ``verdict`` is not one of
    the four verdict strings (fail-closed at the boundary).
    """
    verdict_id = new_verdict_id()
    _insert_factor_verdict(
        vault,
        verdict_id=verdict_id,
        audit_run_id=audit_run_id,
        factor_id=factor_id,
        verdict=verdict,
        reason_code=reason_code,
        substantiated_points=substantiated_points,
        score_delta=score_delta,
        evidence_ids=evidence_ids,
        rule_citation_ids=rule_citation_ids,
    )
    vault.con.commit()
    return verdict_id


def _insert_factor_verdict(vault: Vault, *, verdict_id: str,
                           audit_run_id: str, factor_id: str,
                           verdict: str, reason_code: str | None = None,
                           substantiated_points: int | None = None,
                           score_delta: int | None = None,
                           evidence_ids, rule_citation_ids) -> None:
    """Insert a factor verdict without committing, for report transactions."""
    if verdict not in _VERDICT_VOCAB:
        raise VaultError("verdict must be one of SUBSTANTIATED | GAP | AT-RISK | N/A")
    now = _now()
    vault.con.execute(
        "INSERT INTO factor_verdicts(verdict_id, audit_run_id, factor_id, "
        "verdict, reason_code, substantiated_points, score_delta, "
        "evidence_ids_json, rule_citation_ids_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (verdict_id, audit_run_id, factor_id, verdict, reason_code,
         substantiated_points, score_delta,
         json.dumps(list(evidence_ids)), json.dumps(list(rule_citation_ids)),
         now),
    )


def load_audit_run(vault: Vault, audit_run_id: str) -> dict | None:
    """Return the ``audit_runs`` row as a dict, or None if absent."""
    row = vault.con.execute(
        "SELECT audit_run_id, candidate_id, factor_id, rule_registry_version, "
        "ita_round_id, report_relpath, status, substantiated_total, "
        "cutoff_delta, started_at, completed_at FROM audit_runs "
        "WHERE audit_run_id = ?", (audit_run_id,)
    ).fetchone()
    return None if row is None else dict(row)


def latest_completed_audit_run(vault: Vault) -> dict | None:
    """Return the most recently completed ``audit_runs`` row as a dict, or None.

    Lets ``vault remediate`` default to the latest completed audit without the user
    knowing an internal ``aud_`` id. Filters ``status = 'complete'`` so a
    running/failed run (which has no usable report) is never selected.
    """
    row = vault.con.execute(
        "SELECT audit_run_id, candidate_id, factor_id, rule_registry_version, "
        "ita_round_id, report_relpath, status, substantiated_total, "
        "cutoff_delta, started_at, completed_at FROM audit_runs "
        "WHERE status = 'complete' "
        "ORDER BY completed_at DESC, audit_run_id DESC LIMIT 1"
    ).fetchone()
    return None if row is None else dict(row)


def list_candidate_documents(vault: Vault, candidate_id: str) -> list[dict]:
    """Return a candidate's document rows (PII-light: ids / doc_type only) (Phase 38).

    Parameter-bound; used by ``review-packet`` to count documents excluded-by-default
    and to resolve a per-document opt-in. Never returns raw paths / bytes.
    """
    rows = vault.con.execute(
        "SELECT document_id, doc_type FROM documents WHERE candidate_id = ? "
        "ORDER BY document_id", (candidate_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_candidate_document(vault: Vault, candidate_id: str,
                           document_id: str) -> dict | None:
    """Return one candidate-scoped document row (id/type/storage) or None (Phase 38).

    Parameter-bound + candidate-scoped so a foreign document id can never be resolved.
    """
    row = vault.con.execute(
        "SELECT document_id, doc_type, storage_relpath FROM documents "
        "WHERE candidate_id = ? AND document_id = ?", (candidate_id, document_id)
    ).fetchone()
    return None if row is None else dict(row)


def list_factor_verdicts(vault: Vault, audit_run_id: str) -> list[dict]:
    """Return the ``factor_verdicts`` rows for a run (json-decoding the id lists)."""
    rows = vault.con.execute(
        "SELECT verdict_id, audit_run_id, factor_id, verdict, reason_code, "
        "substantiated_points, score_delta, evidence_ids_json, "
        "rule_citation_ids_json, created_at FROM factor_verdicts "
        "WHERE audit_run_id = ? ORDER BY verdict_id", (audit_run_id,)
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        d = dict(row)
        d["evidence_ids"] = json.loads(d.pop("evidence_ids_json"))
        d["rule_citation_ids"] = json.loads(d.pop("rule_citation_ids_json"))
        result.append(d)
    return result
