"""Stdlib-only IRCC DLI/PGWP pinned-snapshot generator (STUDY-01).

Fetches the FIXED authoritative IRCC "designated learning institutions" JSON,
strictly validates it against a closed nine-field schema, normalizes the
one-campus-per-row data into one canonical per-DLI-number markdown doc, and
atomically writes the whole ``corpus/dli/`` family with per-doc provenance
(``crawl_date`` = upstream ``Last-Modified``; body-only ``content_sha256``) plus
a non-indexed ``manifest.json``.

Design (mirrors ``crawler.pipeline`` — a pure core behind a thin network seam):

* :func:`fetch` is a ≤5-line network seam bound to the FIXED :data:`_DLI_URL`
  (the ONLY host ever contacted — SSRF guard T-41-02); it rejects off-host
  redirects and enforces a byte ceiling before ``json.loads`` (DoS guard).
* :func:`as_of_from` derives the deterministic upstream data-age from the
  ``Last-Modified`` header — NEVER the wall clock (fail-closed D2).
* :func:`normalize` is a pure function of ``(payload, as_of)`` that performs the
  strict closed-schema validation (fail-closed on any drift) and per-DLI
  canonicalization, so the whole pipeline is testable OFFLINE against a fixture.
* :func:`write` performs an atomic full-family replace HONORING the requested
  ``out_dir`` (the CLI fixes it to ``corpus/dli``; tests pass temp/golden roots).

Zero new runtime dependency — stdlib only (RESEARCH §Standard Stack). The
front-matter emit idiom is reused verbatim from ``crawler.deepcrawl`` with ONE
critical divergence: ``crawl_date`` is the upstream ``Last-Modified``, never a
wall-clock timestamp — so identical upstream payload yields byte-identical
bodies and hashes across runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from crawler import paths
from crawler.dli_contract import (
    _DLI_URL,
    _PAGE_URL,
    _body_sha256,
    _family_sha256,
)

# --------------------------------------------------------------------------- #
# Fixed authoritative source + closed-schema constants
# --------------------------------------------------------------------------- #
# The ONLY host ever fetched (SSRF guard T-41-02). There is NO caller-overridable
# host anywhere: :func:`fetch` takes no ``url`` parameter and ALWAYS constructs its
# request from this constant, and the CLI (41-02) exposes no ``--url``. Unit tests
# exercise the seam by monkeypatching the module-level :data:`_OPENER`.
# Stable DLI identity: an ``O`` followed by 6+ digits (after ``.strip()``).
_DLI_RE = re.compile(r"^O\d{6,}$")

# The exact nine keys of every upstream row — a CLOSED schema (extra/missing key
# is a fail-closed refusal, never a partial family).
_FIELDS = (
    "Province",
    "Institution",
    "DLI #",
    "City",
    "Campus",
    "Grad Program",
    "PGWP",
    "HTML",
    "Public/Private",
)
_FIELD_SET = frozenset(_FIELDS)

# PGWP is a verified TRI-STATE; anything else is a fail-closed refusal.
_PGWP = frozenset({"Yes", "No", "Details"})

# Response byte ceiling enforced BEFORE json.loads (DoS guard T-41-01). ~25 MiB
# is generous headroom over the ~0.4 MiB live payload.
_MAX_BYTES = 25 * 1024 * 1024

# Reproduced-for-personal-use current-status-only source label (RESEARCH Pattern 2).
_LABEL = (
    "Source: IRCC (canada.ca) Designated learning institutions list, reproduced "
    "for personal non-commercial use; current status only — verify against the "
    "live list."
)

# The explicit current-status-only limitation carried in every doc body.
_CAVEAT = (
    "Status scope: current status only — this snapshot does NOT establish DLI "
    "designation during any prior study period, nor program-level PGWP eligibility."
)


class SchemaError(Exception):
    """Fail-closed structural refusal of a malformed / drifted DLI payload.

    Raised on: empty / truncated / oversized payload, a missing or extra
    top-level key, a missing / extra / non-string row field, an out-of-domain
    PGWP value, a malformed DLI number, or an absent / unparseable
    ``Last-Modified``. ANY single row-level violation aborts the WHOLE refresh
    (never a partial family). The 41-02 CLI maps it to ``contract.INVALID_INPUT``
    / exit 2, mirroring ``searchindex.FTS5Unavailable`` and
    ``paths.PathEscapeError``.
    """


def _nfc(text: str) -> str:
    """Return the Unicode NFC normalization of *text* (byte-stable hashing)."""
    return unicodedata.normalize("NFC", text)


def _has_control_char(text: str) -> bool:
    """True iff *text* contains any ASCII/Latin-1 control character (WR-02).

    Deterministic EXPLICIT-codepoint predicate — never a locale- or Unicode-
    version-dependent category table lookup — so it is byte-stable across Python
    builds. It rejects exactly the C-category control block that is meaningful in
    JSON text:

    * the ASCII **C0** range ``0x00``–``0x1F`` (this includes ``\\n``/``\\r`` — the
      line breakers that can forge a ``DLI number:`` marker or a markdown heading
      into the grounded chunk #000 — plus ``\\t`` and ``NUL``),
    * ``DEL`` (``0x7F``), and
    * the **C1** range ``0x80``–``0x9F`` (Unicode category ``Cc``; notably ``NEL``
      ``U+0085``, which several line-oriented processors also treat as a break).

    It deliberately does NOT reject ordinary Unicode letters or punctuation:
    accented letters such as ``è`` (``U+00E8``) and the curly apostrophe ``’``
    (``U+2019``) are all above ``0x9F`` and pass unharmed, so legitimate
    institution/campus names survive verbatim.
    """
    return any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in text)


# --------------------------------------------------------------------------- #
# Normalized per-DLI document (data container)
# --------------------------------------------------------------------------- #
@dataclass
class DliDoc:
    """One canonical doc per DISTINCT normalized DLI number.

    ``front`` / ``body`` / ``content_sha256`` are populated by ``_build_doc``
    (Plan 41-01 Task 2); Task 1 lands the validated grouping only.
    """

    dli_number: str
    campuses: list
    front: dict = field(default_factory=dict)
    body: str = ""
    content_sha256: str = ""

    @property
    def path(self) -> str:
        return f"{self.dli_number}.md"

    @property
    def rows(self) -> int:
        return len(self.campuses)


# --------------------------------------------------------------------------- #
# Network seam (SSRF guard: fixed host, no off-host redirect, byte ceiling)
# --------------------------------------------------------------------------- #
class _NoCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    """Reject any redirect that leaves the original host (SSRF/exfil guard)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old_host = urllib.parse.urlparse(req.full_url).hostname
        new_host = urllib.parse.urlparse(newurl).hostname
        if new_host != old_host:
            raise urllib.error.HTTPError(
                newurl, code, f"cross-host redirect blocked: {new_host!r}",
                headers, fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Module-level opener so tests can monkeypatch ``dli_snapshot._OPENER``.
_OPENER = urllib.request.build_opener(_NoCrossHostRedirect())


def fetch(*, timeout: int = 60) -> tuple[dict, str | None]:
    """Fetch and parse the FIXED authoritative DLI JSON.

    Returns ``(payload, last_modified)``. There is NO ``url`` parameter: the
    request is ALWAYS constructed from the fixed :data:`_DLI_URL`, so the
    fixed-source boundary is structurally enforced and there is no initial-request
    SSRF surface (off-host redirects remain rejected by
    :class:`_NoCrossHostRedirect`). Unit tests drive the seam by monkeypatching
    the module-level :data:`_OPENER`.

    No custom / browser-spoofed User-Agent is sent: stdlib ``urllib`` supplies its
    own honest client identity, which is what the authoritative endpoint accepts
    (a custom identifier is empirically blackholed by the upstream CDN in some
    egress environments — this is compatibility, NOT identity evasion). Only
    ``Accept: application/json`` is advertised. Enforces an explicit ``timeout``
    and a :data:`_MAX_BYTES` response ceiling before ``json.loads`` (never
    ``eval``).

    Every refusal that originates in this seam — the :data:`_MAX_BYTES` ceiling,
    a non-UTF-8 body, or a non-JSON/truncated payload (e.g. a canada.ca HTML
    maintenance page served with HTTP 200) — is normalized to a fail-closed
    :class:`SchemaError` with a STABLE, PII-free message (raw payload bytes are
    NEVER echoed). This keeps the whole fetch/validate boundary mappable to the
    41-02 CLI's single ``invalid_input`` / exit 2 contract (CR-01): a DoS-guard or
    decode refusal is never mislabeled ``internal_error`` and never escapes as a
    raw traceback in human mode.
    """
    req = urllib.request.Request(_DLI_URL, headers={"Accept": "application/json"})
    with _OPENER.open(req, timeout=timeout) as resp:  # nosec B310 - fixed authoritative host constant
        last_modified = resp.headers.get("Last-Modified")
        raw = resp.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise SchemaError(f"DLI dataset exceeds {_MAX_BYTES}-byte ceiling")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Stable + PII-free: never echo the offending bytes into the message.
        raise SchemaError("DLI dataset is not valid UTF-8") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        # ``exc.msg`` is the parser's short reason ("Expecting value", …) — stable
        # and content-free; the full ``str(exc)`` position suffix is omitted.
        raise SchemaError(f"DLI dataset is not valid JSON: {exc.msg}") from exc
    return payload, last_modified


def as_of_from(last_modified: str | None) -> str:
    """Parse an RFC-1123 ``Last-Modified`` into ISO ``YYYY-MM-DDTHH:MM:SSZ``.

    This is the deterministic upstream data-age (D2). Raises :class:`SchemaError`
    when the header is absent or unparseable — NEVER substitutes the wall clock.
    """
    if not last_modified:
        raise SchemaError("missing Last-Modified header")
    try:
        dt = parsedate_to_datetime(last_modified)
    except (ValueError, TypeError) as exc:
        raise SchemaError(f"unparseable Last-Modified: {last_modified!r}") from exc
    if dt is None:
        raise SchemaError(f"unparseable Last-Modified: {last_modified!r}")
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize(payload: dict, *, as_of: str) -> list[DliDoc]:
    """Strictly validate *payload* and canonicalize it into per-DLI docs.

    Fail-closed on ANY structural drift (SchemaError): non-object payload, a
    missing / extra top-level key, a non-list / empty ``data``, a row that is not
    an object, a row whose key set is not EXACTLY the nine fields, a non-string
    value, a string value carrying a control character (C0 / DEL / C1 — WR-02),
    an out-of-domain PGWP, or a ``DLI #`` that fails ``^O\\d{6,}$`` after
    NFC + ``.strip()``. A SINGLE malformed row aborts the WHOLE refresh — the
    caller writes nothing, so a prior healthy family is preserved byte-for-byte;
    a partial or garbage subset is never produced.

    Returns one :class:`DliDoc` per DISTINCT normalized DLI number, ordered by
    DLI# ascending. (Per-DLI body/front construction lands in Task 2.)
    """
    if not isinstance(payload, dict):
        raise SchemaError("payload is not a JSON object")
    if set(payload) != {"data"}:
        raise SchemaError(f"unexpected top-level keys: {sorted(payload)!r}")
    data = payload["data"]
    if not isinstance(data, list):
        raise SchemaError("'data' is not a list")
    if not data:
        raise SchemaError("empty DLI dataset")

    by_dli: dict[str, list[dict]] = {}
    for raw in data:
        if not isinstance(raw, dict):
            raise SchemaError("row is not a JSON object")
        if set(raw) != _FIELD_SET:
            raise SchemaError(f"row has unexpected field set: {sorted(raw)!r}")
        for key, value in raw.items():
            if not isinstance(value, str):
                raise SchemaError(f"row field {key!r} is not a string")
            # Fail-closed on control-character content (WR-02). A raw newline /
            # carriage-return / NEL in ANY free-text field survives _nfc().strip()
            # (which only trims LEADING/TRAILING whitespace) verbatim into the
            # generated body, letting a drifted upstream row forge a `DLI number:`
            # marker or a markdown heading into the grounding selector's chunk
            # #000. Reject the WHOLE refresh instead of emitting a
            # marker-injectable doc. The message names only the (fixed, public)
            # schema field key — it NEVER echoes the raw offending content, so it
            # stays stable and PII-free.
            if _has_control_char(value):
                raise SchemaError(f"row field {key!r} contains a control character")
        if raw["PGWP"] not in _PGWP:
            raise SchemaError(f"invalid PGWP value: {raw['PGWP']!r}")
        dli = _nfc(str(raw["DLI #"])).strip()
        if not _DLI_RE.fullmatch(dli):
            # Fail-closed: ANY malformed row aborts the WHOLE refresh — never a
            # partial family, never a garbage doc, never a dropped-identity subset.
            raise SchemaError(f"invalid DLI number: {dli!r}")
        by_dli.setdefault(dli, []).append(raw)

    return [
        _build_doc(dli, sorted(by_dli[dli], key=_campus_key), as_of=as_of)
        for dli in sorted(by_dli)
    ]


# --------------------------------------------------------------------------- #
# Per-DLI canonical doc build (front-matter + verbatim-citable body)
# --------------------------------------------------------------------------- #
def _campus_key(row: dict) -> tuple[str, str]:
    """Deterministic per-campus ordering key: (City, Campus), NFC + stripped."""
    return (_nfc(row["City"]).strip(), _nfc(row["Campus"]).strip())


def _distinct(values) -> list[str]:
    """Return the sorted list of distinct NFC-normalized, whitespace-stripped values."""
    return sorted({_nfc(v).strip() for v in values})


def _build_doc(dli: str, campuses: list[dict], *, as_of: str) -> DliDoc:
    """Build ONE canonical :class:`DliDoc` for *dli* from its sorted *campuses*.

    The body is a deterministic transform of the authoritative payload: an H1, a
    pre-heading block carrying the exact ASCII ``DLI number: <dli>`` line, the
    current-status-only caveat, the whitespace-stripped UNION of institution-name
    variants, and a province/sector/graduate summary, followed by a per-campus
    PGWP table that preserves each campus's ``Yes``/``No``/``Details`` VERBATIM
    (never collapsed, never a ``Details`` sub-page followed). ``crawl_date`` is
    the derived *as_of*, never the wall clock; ``content_sha256`` hashes the BODY
    only, so identical upstream payload yields byte-identical bodies and hashes.
    """
    names = _distinct(c["Institution"] for c in campuses)
    primary = _nfc(campuses[0]["Institution"]).strip()
    province = ", ".join(_distinct(c["Province"] for c in campuses))
    sector = ", ".join(_distinct(c["Public/Private"] for c in campuses))
    grad = ", ".join(_distinct(c["Grad Program"] for c in campuses))

    lines = [
        f"# DLI {dli} — {primary}",
        "",
        f"DLI number: {dli}",
        "Designation status: Designated — currently present in the IRCC designated "
        "learning institutions list (snapshot date recorded in front-matter crawl_date).",
        _CAVEAT,
        f"Institution names: {'; '.join(names)}",
        f"Province: {province} · Sector: {sector} · Graduate program: {grad}",
        "",
        "## Post-Graduation Work Permit (PGWP) eligibility by campus",
        "",
        "| City | Campus | PGWP |",
        "| ---- | ------ | ---- |",
    ]
    for c in campuses:
        city = _nfc(c["City"]).strip()
        campus = _nfc(c["Campus"]).strip()
        lines.append(f"| {city} | {campus} | {c['PGWP']} |")
    body = "\n".join(lines) + "\n"

    content_sha256 = _body_sha256(body)
    front = {
        "url": _PAGE_URL,
        "title": f"DLI {dli} — {primary}",
        "source_type": "dli",
        "dli_number": dli,
        "crawl_date": as_of,
        "content_sha256": content_sha256,
        "status_scope": "current-only",
        "label": _LABEL,
        "generator": "ircc-dli-json",
    }
    return DliDoc(
        dli_number=dli,
        campuses=campuses,
        front=front,
        body=body,
        content_sha256=content_sha256,
    )


def _render(doc: DliDoc) -> str:
    """Front-matter (deepcrawl idiom) + body — crawl_date carried, NOT hashed."""
    fm = "---\n" + "\n".join(
        f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in doc.front.items()
    ) + "\n---\n\n"
    return fm + doc.body


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Crash-safe staging container (OUTSIDE the indexed family tree — WR-01)
# --------------------------------------------------------------------------- #
# The stage/backup dirs live in a collision-resistant container that is a sibling
# of the family's PARENT (``root.parent.parent``), NOT a sibling of the family
# root (``root.parent``). ``dupaudit.live_docs`` / ``searchindex.build_index``
# enumerate ``root.parent.rglob("*.md")`` and DESCEND dot-prefixed directories, so
# a hard-kill (SIGKILL / power loss) that left a full family copy in a sibling of
# the root — the old ``corpus/.dli.bak-<pid>`` scheme — was enumerated as a
# DUPLICATE live DLI doc. Placing the transient copies one directory HIGHER keeps
# any crash-window orphan OUTSIDE that indexed tree, so it can never be indexed
# (the frozen ``dupaudit`` / ``searchindex`` are NOT touched). The container stays
# on the SAME filesystem as ``root`` (one level up), so ``os.replace`` remains an
# atomic rename. A stable hash of the ABSOLUTE root scopes the on-entry sweep to
# THIS family; a pid+random suffix guarantees per-run uniqueness so concurrent
# refreshes never collide.
_TEMP_PREFIX = ".dli-refresh-"


def _root_container_prefix(root: Path) -> str:
    """Sweep/name prefix scoping transient containers to THIS resolved *root*."""
    root_hash = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    return f"{_TEMP_PREFIX}{root_hash}-"


def _container_pid(name: str, prefix: str) -> int | None:
    """Parse the owning PID out of a ``<prefix><pid>-<rand>`` container name."""
    if not name.startswith(prefix):
        return None
    head = name[len(prefix):].split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness probe (POSIX ``kill -0``); assume alive on any doubt.

    Used ONLY to spare a concurrent run's active container during the stale sweep
    — NEVER for correctness. A false "alive" merely defers cleanup of a harmless
    orphan (already OUTSIDE the indexed tree) to a later sweep; on any error other
    than ``ProcessLookupError`` we conservatively report alive so live concurrent
    work is never destroyed. No locks, no platform-specific API beyond ``kill``.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _sweep_stale_containers(container_parent: Path, prefix: str) -> None:
    """Remove this family's dead crash-orphan containers, sparing live ones.

    Only containers whose owning PID is PROVABLY dead are removed, so an active
    concurrent refresh of the same family is never disturbed. Orphans that survive
    (live-PID, unparseable name, or a recycled PID) stay OUTSIDE the indexed tree,
    so correctness never depends on the sweep succeeding.
    """
    for leftover in container_parent.glob(f"{prefix}*"):
        pid = _container_pid(leftover.name, prefix)
        if pid is not None and _pid_alive(pid):
            continue
        _rmtree(leftover)


# --------------------------------------------------------------------------- #
# Atomic full-family replace (honors out_dir; stage -> validate -> swap/rollback)
# --------------------------------------------------------------------------- #
def write(docs: list[DliDoc], out_dir) -> dict:
    """Atomically (re)generate the WHOLE DLI family under the resolved *out_dir*.

    Containment is anchored on ``root = Path(out_dir).resolve()`` via the GENERIC
    ``paths.resolve_within`` helper (never the vault helpers). The whole family
    plus ``manifest.json`` is staged into a collision-resistant transient
    container that lives OUTSIDE the indexed tree (a sibling of ``root.parent`` —
    see WR-01), every staged doc is validated (front-matter present, filename ==
    validated DLI#, non-empty body), then swapped in with ``os.replace`` after
    renaming any prior family aside — so an upstream-removed institution leaves no
    stale ``.md``. On ANY staging / validation / swap error the prior healthy
    family is restored byte-for-byte (never a partial subset). The CLI (41-02) is
    the only production caller and passes fixed ``Path("corpus/dli")``; tests pass
    temp/golden roots.

    Returns ``{"out", "docs", "rows", "family_sha256"}`` (PII-free provenance).
    """
    root = Path(out_dir).resolve()
    root.parent.mkdir(parents=True, exist_ok=True)
    as_of = docs[0].front.get("crawl_date") if docs else None

    # Transient stage/backup live OUTSIDE the indexed family tree (WR-01): a
    # collision-resistant container under root.parent.parent, on the SAME
    # filesystem so os.replace stays an atomic rename. Sweep THIS family's dead
    # crash-orphans on entry (sparing any live concurrent run), then mint a unique
    # per-run container. A hard-kill in the swap window can therefore only ever
    # leave a copy here — never a sibling of root that dupaudit/searchindex would
    # enumerate as a duplicate live doc.
    container_parent = root.parent.parent
    prefix = _root_container_prefix(root)
    _sweep_stale_containers(container_parent, prefix)
    container = container_parent / f"{prefix}{os.getpid()}-{os.urandom(6).hex()}"
    container.mkdir(parents=True)
    stage = container / "stage"
    backup = container / "bak"

    file_hashes: list[dict] = []
    total_rows = 0
    swapped = False
    try:
        stage.mkdir(parents=True)
        for doc in docs:
            # Filename is the validated ^O\d{6,}$ DLI# only; resolve_within is a
            # belt-and-suspenders traversal guard (T-41-03).
            target = paths.resolve_within(stage, doc.path)
            target.write_text(_render(doc), encoding="utf-8")
            staged = target.read_text(encoding="utf-8")
            if not staged.startswith("---"):
                raise SchemaError(f"staged doc {doc.path} missing front-matter")
            if target.name != f"{doc.dli_number}.md":
                raise SchemaError(f"staged filename mismatch for {doc.dli_number}")
            if not doc.body.strip():
                raise SchemaError(f"staged doc {doc.path} has empty body")
            file_hashes.append(
                {"file": doc.path, "content_sha256": doc.content_sha256}
            )
            total_rows += doc.rows

        file_hashes.sort(key=lambda e: e["file"])
        family_sha256 = _family_sha256(file_hashes)
        _write_manifest(stage, docs, as_of=as_of, family_sha256=family_sha256)

        # Atomic swap: prior family aside (into the out-of-tree container), stage
        # -> root, then drop the whole container (which now holds only the old
        # family). Both renames stay on one filesystem.
        if root.exists():
            os.replace(root, backup)
        os.replace(stage, root)
        swapped = True
        _rmtree(container)
    except BaseException:
        # Roll back: discard the stage, restore any prior family untouched. If the
        # restore itself raises, _rmtree(container) is skipped and the backup is
        # PRESERVED in the out-of-tree container (recoverable, never indexed)
        # rather than deleted.
        _rmtree(stage)
        if not swapped and backup.exists() and not root.exists():
            os.replace(backup, root)
        _rmtree(container)
        raise

    return {
        "out": str(out_dir),
        "docs": len(docs),
        "rows": total_rows,
        "family_sha256": family_sha256,
    }


def _write_manifest(stage_dir, docs: list[DliDoc], *, as_of, family_sha256: str) -> None:
    """Write the non-indexed ``manifest.json`` provenance into *stage_dir*.

    It carries the source URL, the as-of / ``Last-Modified``, the generator id, a
    current-status-only note, the sorted per-file content hashes, and the
    family-level hash. The ``.json`` extension keeps it out of the index
    (``dupaudit.live_docs`` enumerates only front-matter ``.md`` docs) and it is
    NEVER cited by a grounded rule row.
    """
    manifest = {
        "source_url": _DLI_URL,
        "as_of": as_of,
        "last_modified": as_of,
        "generator": "ircc-dli-json",
        "status_scope": "current-only",
        "note": _CAVEAT,
        "family_sha256": family_sha256,
        "files": sorted(
            [{"file": d.path, "content_sha256": d.content_sha256} for d in docs],
            key=lambda e: e["file"],
        ),
    }
    (Path(stage_dir) / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
