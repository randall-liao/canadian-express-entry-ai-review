"""Private, candidate-scoped Canadian-study evidence review.

The sidecar consumes only audit-eligible ``review.study`` values and exact chunks
from the pinned local DLI family.  Exact resolution is discovery only: every
consumed DLI chunk becomes a strict transient :class:`RuleRow` and the complete
temporary Registry crosses :func:`crawler.auditor.gate_subset` before any
snapshot observation informs a result.  Current designation and PGWP table cells
are evidence about the current snapshot only; they never establish historical
designation or program-level eligibility.

Applicant values, evidence ids, quotes, and citation coordinates are written only
to the candidate vault.  The returned mapping is the closed ``PUBLIC_FIELDS``
projection and contains no report path or DLI identifier.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import hashlib
import os
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import yaml

try:  # Keep the module importable on both supported OS lock implementations.
    if os.name == "nt":
        import msvcrt as _msvcrt
        _fcntl = None
    else:
        import fcntl as _fcntl
        _msvcrt = None
except ImportError:  # pragma: no cover - unsupported platforms fail closed below.
    _fcntl = None
    _msvcrt = None

from crawler import (
    auditor,
    crs_rules,
    dli_contract,
    dlifields,
    dupaudit,
    index_health,
    paths,
    searchindex,
    vault,
)
from crawler.models.crs_rules import (
    AcceptedValue,
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)

PUBLIC_FIELDS: tuple[str, ...] = (
    "status",
    "reason",
    "required_count",
    "confirmed_count",
    "eligible_count",
    "as_of",
)

_REVIEW_FACTOR = "review.study"
_STUDY_FIELDS = (
    "institution_name",
    "dli_number",
    "credential_level",
    "program_start",
    "program_end",
    "study_status",
)
_REQUIRED_FIELDS = (
    "dli_number",
    "credential_level",
    "study_status",
    "program_start",
    "program_end",
)
_STATIC_RULE_IDS = ("additional.study", "study.r73_definition")
_PGWP_VALUES = ("Yes", "No", "Details")
_NOTICE = (
    "This is Canadian-study evidence screening, not legal advice or an "
    "eligibility determination. Current snapshot observations do not establish "
    "historical DLI designation or program-level PGWP eligibility."
)
_DLI_SNAPSHOT_ROOT = (
    Path(__file__).resolve().parents[1] / "corpus" / "dli"
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_RECOVERY_MARKER_NAME = ".latest-recovery-required.json"
_BACKUP_NAME_RE = re.compile(r"\.latest-[A-Za-z0-9_-]+\.bak")
_REPORT_LOCK_NAME = ".latest-recovery.lock"


def _today() -> date:
    """Clock seam for deterministic freshness tests."""
    return date.today()


class _ReviewResult(dict):
    """Closed public mapping with one non-serializing lifecycle signal."""

    __slots__ = ("report_created", "registry_fingerprint")

    def __init__(
        self,
        *args,
        report_created: bool = False,
        registry_fingerprint: str | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.report_created = report_created
        self.registry_fingerprint = registry_fingerprint


class StudyReportPersistenceError(RuntimeError):
    """Stable, path-free failure while publishing a new study report."""


class StudyReportRecoveryError(RuntimeError):
    """Fatal, path-free failure to restore the prior study report."""


def _pack(status: str, reason: str, *, confirmed_count: int = 0,
          eligible_count: int = 0, as_of: str | None = None,
          report_created: bool = False,
          registry_fingerprint: str | None = None) -> dict:
    """Return the exact closed public projection in stable field order."""
    return _ReviewResult({
        "status": status,
        "reason": reason,
        "required_count": len(_REQUIRED_FIELDS),
        "confirmed_count": confirmed_count,
        "eligible_count": eligible_count,
        "as_of": as_of,
    }, report_created=report_created,
       registry_fingerprint=registry_fingerprint)


def _latest_report_path(candidate_root: Path) -> Path:
    """Resolve the sole report target beneath the private candidate root."""
    return paths.resolve_within(
        candidate_root, "output", "study-review", "latest.json")


def _effective_value(value) -> Any:
    """Use a correction when present; otherwise use the extracted normalization."""
    if value.confirmation_status == "corrected":
        return value.confirmed_value
    return value.normalized_value


def _candidate_values(
    vault_: vault.Vault,
    candidate_id: str,
    registry_fingerprint: str,
):
    """Load only candidate-scoped study fields and apply the shipped trust predicate."""
    placeholders = ",".join("?" for _ in _STUDY_FIELDS)
    rows = vault_.con.execute(
        "SELECT ev.value_id, d.evidence_id FROM extracted_values ev "
        "JOIN documents d ON d.document_id = ev.document_id "
        "WHERE d.candidate_id = ? AND ev.factor_id = ? "
        f"AND ev.field_name IN ({placeholders}) "
        "ORDER BY ev.value_id",
        (candidate_id, _REVIEW_FACTOR, *_STUDY_FIELDS),
    ).fetchall()

    all_values: list[tuple[Any, str | None]] = []
    eligible: list[tuple[Any, str | None]] = []
    for row in rows:
        value = vault.get_extracted_value(vault_, row["value_id"])
        if value is None:
            continue
        pair = (value, row["evidence_id"])
        all_values.append(pair)
        if vault.is_audit_eligible(
                vault_, value.value_id,
                registry_fingerprint=registry_fingerprint):
            eligible.append(pair)
    return all_values, eligible


def _collapse_eligible(eligible):
    """Collapse identical eligible duplicates; reject conflicting current values."""
    grouped: dict[str, list[tuple[Any, str | None]]] = {}
    for value, evidence_id in eligible:
        grouped.setdefault(value.field_name, []).append((value, evidence_id))

    collapsed: dict[str, dict] = {}
    for field_name, pairs in grouped.items():
        by_value: dict[str, tuple[Any, list[Any], list[str]]] = {}
        for value, evidence_id in pairs:
            effective = _effective_value(value)
            key = json.dumps(
                effective, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), default=str)
            if key not in by_value:
                by_value[key] = (effective, [], [])
            by_value[key][1].append(value)
            if evidence_id and evidence_id not in by_value[key][2]:
                by_value[key][2].append(evidence_id)
        if len(by_value) != 1:
            return None
        effective, values, evidence_ids = next(iter(by_value.values()))
        collapsed[field_name] = {
            "value": effective,
            "value_ids": [value.value_id for value in values],
            "evidence_ids": evidence_ids,
        }
    return collapsed


def _static_rows(registry: Registry) -> list[RuleRow]:
    """Return exactly one non-gap row for each required governing rule."""
    selected: list[RuleRow] = []
    for rule_id in _STATIC_RULE_IDS:
        matches = [row for row in registry.rows if row.rule_id == rule_id]
        if len(matches) != 1 or matches[0].gap:
            raise auditor.AuditGroundingError(
                f"required governing rule unavailable: {rule_id}")
        selected.append(matches[0])
    credential, completion = selected
    if (credential.machine_check.kind != "points_table"
            or credential.machine_check.field != "canadian_study"
            or not credential.machine_check.points_by_level):
        raise auditor.AuditGroundingError(
            "required governing rule has invalid shape: additional.study")
    if (completion.machine_check.kind != "accepted_enum"
            or completion.machine_check.field != "study_status"
            or not completion.machine_check.accepted_values):
        raise auditor.AuditGroundingError(
            "required governing rule has invalid shape: study.r73_definition")
    return selected


def _resolve_candidate_chunks(db, dli: str):
    """Read all rows for the candidate relpath without positional gap guessing."""
    relpath = f"dli/{dli}.md"
    rows = searchindex.canonical_rows_for_relpath(Path(db), relpath)
    if not rows:
        return None
    return rows[0], rows[1:]


def _candidate_snapshot_provenance(
    dli: str,
    designation: dict,
    pgwp_chunks: list[dict],
    common_crawl_date: str,
    *,
    max_age_days: int,
) -> bool:
    """Bind candidate index metadata to the fixed local DLI family manifest.

    ``manifest.json`` is lineage metadata, not a grounding source.  The shared
    gate remains authoritative for citations; this check independently ensures
    that the candidate coordinate, title, body hash, and date came from the
    pinned local family that produced the index.
    """
    try:
        manifest_path = paths.resolve_within(
            _DLI_SNAPSHOT_ROOT, "manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return False

        source_url = manifest.get("source_url")
        as_of = manifest.get("as_of")
        files = manifest.get("files")
        family_sha256 = manifest.get("family_sha256")
        if (
            source_url != dli_contract._DLI_URL
            or not isinstance(as_of, str)
            or not as_of
            or as_of != common_crawl_date
            or manifest.get("last_modified") != as_of
            or manifest.get("generator") != "ircc-dli-json"
            or manifest.get("status_scope") != "current-only"
            or not isinstance(files, list)
            or not files
            or not isinstance(family_sha256, str)
            or not _SHA256_RE.fullmatch(family_sha256)
        ):
            return False

        normalized_files: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in files:
            if not isinstance(entry, dict) or set(entry) != {
                    "file", "content_sha256"}:
                return False
            filename = entry.get("file")
            content_sha256 = entry.get("content_sha256")
            if (
                not isinstance(filename, str)
                or Path(filename).name != filename
                or not filename.endswith(".md")
                or filename in seen
                or not isinstance(content_sha256, str)
                or not _SHA256_RE.fullmatch(content_sha256)
            ):
                return False
            seen.add(filename)
            normalized_files.append({
                "file": filename,
                "content_sha256": content_sha256,
            })
        if normalized_files != sorted(
                normalized_files, key=lambda item: item["file"]):
            return False
        if dli_contract._family_sha256(normalized_files) != family_sha256:
            return False

        filename = f"{dli}.md"
        matches = [
            entry for entry in normalized_files if entry["file"] == filename
        ]
        if len(matches) != 1:
            return False
        expected_hash = matches[0]["content_sha256"]

        document_path = paths.resolve_within(_DLI_SNAPSHOT_ROOT, filename)
        raw = document_path.read_text(encoding="utf-8")
        metadata = yaml.safe_load(dupaudit._frontmatter_of(raw)) or {}
        if not isinstance(metadata, dict):
            return False
        body_hash = dli_contract._body_sha256(
            dupaudit.body_of(raw).removeprefix("\n"))
        relpath = f"dli/{filename}"
        actual_rows = [designation, *pgwp_chunks]
        expected_rows = searchindex.canonical_document_rows(
            document_path, _DLI_SNAPSHOT_ROOT.parent, raw)
        if (
            body_hash != expected_hash
            or metadata.get("content_sha256") != expected_hash
            or metadata.get("url") != dli_contract._PAGE_URL
            or metadata.get("crawl_date") != as_of
            or metadata.get("source_type") != "dli"
            or metadata.get("dli_number") != dli
            or metadata.get("status_scope") != "current-only"
            or metadata.get("generator") != "ircc-dli-json"
            or not isinstance(metadata.get("title"), str)
            or f"DLI {dli}" not in metadata["title"]
            or expected_rows != actual_rows
        ):
            return False

        from crawler.crs_audit import _as_date

        delta = (_as_date(_today()) - _as_date(common_crawl_date)).days
        return 0 <= delta <= max_age_days
    except (
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ):
        return False


def _designation_quote(text: Any, dli: str) -> str | None:
    """Select the three exact current-status lines used by the transient citation."""
    if not isinstance(text, str):
        return None
    prefixes = (
        f"DLI number: {dli}",
        "Designation status:",
        "Status scope:",
    )
    lines = text.splitlines()
    selected: list[str] = []
    for prefix in prefixes:
        matches = [line for line in lines if line.startswith(prefix)]
        if len(matches) != 1:
            return None
        selected.append(matches[0])
    return "\n".join(selected)


def _pgwp_observations(text: Any) -> list[str]:
    """Read a complete PGWP markdown table into its closed observed-value payload."""
    if not isinstance(text, str) or not text.strip():
        return []
    table = [line for line in text.splitlines() if line.strip()]
    if len(table) < 3 or not all(line.startswith("|") and line.endswith("|")
                                 for line in table):
        return []
    header = [cell.strip() for cell in table[0].strip("|").split("|")]
    if "PGWP" not in header:
        return []
    pgwp_index = header.index("PGWP")
    observations: list[str] = []
    for line in table[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(header):
            return []
        observed = cells[pgwp_index]
        if observed not in _PGWP_VALUES:
            return []
        if observed not in observations:
            observations.append(observed)
    return observations


def _dynamic_rows(dli: str, designation: dict,
                  pgwp_chunks: list[dict]) -> tuple[list[RuleRow], list[dict]] | None:
    """Build one strict transient row and private citation per consumed chunk."""
    title_token = f"DLI {dli}"
    designation_quote = _designation_quote(designation.get("text"), dli)
    if designation_quote is None:
        return None

    rows: list[RuleRow] = []
    private: list[dict] = []
    designation_rule_id = f"study.dynamic.{dli}.designation"
    designation_values = [dli]
    rows.append(RuleRow(
        rule_id=designation_rule_id,
        factor_group="additional_points",
        factor_ids=[_REVIEW_FACTOR],
        check_type="admissibility",
        query=dli,
        selector=Selector(
            family="dli",
            marker=f"DLI number: {dli}",
            require_title_contains=title_token,
        ),
        claim_text=(
            "The pinned DLI snapshot records this identifier as currently "
            "designated, with current-only scope."),
        citations=[Citation(
            chunk_id=designation["chunk_id"],
            quote=designation_quote,
        )],
        machine_check=MachineCheck(
            kind="accepted_enum",
            field="dli_number",
            accepted_values=[
                AcceptedValue(value=dli, citation_index=0),
            ],
        ),
        volatility=VolatilityMeta(
            volatility="volatile",
            source_family="dli",
            crawl_date=designation.get("crawl_date"),
        ),
    ))
    private.append({
        "rule_id": designation_rule_id,
        "kind": "designation_current",
        "chunk_id": designation["chunk_id"],
        "quote": designation_quote,
        "crawl_date": designation.get("crawl_date"),
        "observed_values": designation_values,
    })

    for chunk in pgwp_chunks:
        ordinal = int(chunk["chunk_id"].rsplit("#", 1)[1])
        table_text = chunk.get("text")
        if not isinstance(table_text, str) or not table_text:
            return None
        observations = _pgwp_observations(table_text)
        rule_id = f"study.dynamic.{dli}.pgwp.{ordinal:03d}"
        rows.append(RuleRow(
            rule_id=rule_id,
            factor_group="additional_points",
            factor_ids=[_REVIEW_FACTOR],
            check_type="admissibility",
            query=table_text,
            selector=Selector(
                family="dli",
                marker=table_text,
                require_title_contains=title_token,
            ),
            claim_text=(
                "The pinned DLI snapshot records these current PGWP table "
                "observations without implying program eligibility."),
            citations=[Citation(
                chunk_id=chunk["chunk_id"],
                quote=table_text,
            )],
            machine_check=MachineCheck(
                kind="accepted_enum",
                field="pgwp_current_status",
                accepted_values=[
                    AcceptedValue(value=value, citation_index=0)
                    for value in observations
                ],
            ),
            volatility=VolatilityMeta(
                volatility="volatile",
                source_family="dli",
                crawl_date=chunk.get("crawl_date"),
            ),
        ))
        private.append({
            "rule_id": rule_id,
            "kind": "pgwp_current",
            "chunk_id": chunk["chunk_id"],
            "quote": table_text,
            "crawl_date": chunk.get("crawl_date"),
            "observed_values": observations,
        })
    return rows, private


def _grounded_tiers(row: RuleRow) -> set[str]:
    """Read credential labels only from the gated points-table row."""
    return {
        str(entry.level)
        for entry in (row.machine_check.points_by_level or [])
        if entry.level is not None
    }


def _grounded_statuses(row: RuleRow) -> set[str]:
    """Read completion tokens only from the gated R73 definition row."""
    return {
        item.value
        for item in (row.machine_check.accepted_values or [])
    }


def _pgwp_reason(dynamic_rows: list[RuleRow]) -> str:
    """Derive the fail-closed PGWP outcome from already-gated row payloads."""
    observed: list[str] = []
    for row in dynamic_rows:
        if row.machine_check.field != "pgwp_current_status":
            continue
        values = [
            item.value for item in (row.machine_check.accepted_values or [])
        ]
        if not values:
            return "pgwp_ambiguous"
        observed.extend(values)
    if not observed or any(value not in _PGWP_VALUES for value in observed):
        return "pgwp_ambiguous"
    distinct = set(observed)
    if "Details" in distinct:
        return "pgwp_details_manual"
    if distinct == {"No"}:
        return "pgwp_no"
    if distinct == {"Yes"}:
        return "designation_historical_unproven"
    return "pgwp_ambiguous"


def _write_private_report(vault_: vault.Vault, *, candidate_id: str,
                          fields: dict, static_rows: list[RuleRow],
                          dynamic_citations: list[dict], result: dict) -> None:
    """Write one deterministic evidence-bearing report inside the candidate vault."""
    _ensure_study_report_recovered(
        _latest_report_path(vault_.root).parent
    )
    applicant_fields = {
        name: item["value"] for name, item in sorted(fields.items())
    }
    evidence_ids = {
        name: item["evidence_ids"] for name, item in sorted(fields.items())
    }
    static_citations = [
        {
            "rule_id": row.rule_id,
            "citations": [
                {"chunk_id": citation.chunk_id, "quote": citation.quote}
                for citation in row.citations
            ],
        }
        for row in static_rows
    ]
    report = {
        "candidate_id": candidate_id,
        "applicant_fields": applicant_fields,
        "evidence_ids": evidence_ids,
        "static_citations": static_citations,
        "dynamic_citations": dynamic_citations,
        "verdict": {
            "status": result["status"],
            "reason": result["reason"],
        },
        "as_of": result["as_of"],
        "registry_fingerprint": result.registry_fingerprint,
        "notice": _NOTICE,
    }
    payload = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    _publish_private_report(_latest_report_path(vault_.root), payload)


@contextmanager
def _report_lock(report_dir: Path):
    """Hold the per-report advisory lock without exposing vault details on failure."""
    descriptor = -1
    locked = False
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            report_dir / _REPORT_LOCK_NAME,
            os.O_RDWR | os.O_CREAT,
            0o600,
        )
        os.chmod(report_dir / _REPORT_LOCK_NAME, 0o600)
        if os.name == "nt":
            if _msvcrt is None:
                raise OSError("study report lock is unavailable")
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            _msvcrt.locking(descriptor, _msvcrt.LK_LOCK, 1)
        else:
            if _fcntl is None:
                raise OSError("study report lock is unavailable")
            _fcntl.flock(descriptor, _fcntl.LOCK_EX)
        locked = True
    except Exception:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except Exception:
                pass
        raise StudyReportRecoveryError(
            "study report recovery failed") from None

    try:
        yield
    finally:
        release_failed = False
        try:
            if locked:
                if os.name == "nt":
                    if _msvcrt is None:
                        raise OSError("study report lock is unavailable")
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    _msvcrt.locking(descriptor, _msvcrt.LK_UNLCK, 1)
                else:
                    if _fcntl is None:
                        raise OSError("study report lock is unavailable")
                    _fcntl.flock(descriptor, _fcntl.LOCK_UN)
        except Exception:
            release_failed = True
        try:
            os.close(descriptor)
        except Exception:
            release_failed = True
        if release_failed:
            raise StudyReportRecoveryError(
                "study report recovery failed") from None


def _publish_private_report(out: Path, payload: str) -> None:
    """Serialize durable publication and recovery for one private report."""
    with _report_lock(out.parent):
        _publish_private_report_unlocked(out, payload)


def _publish_private_report_unlocked(out: Path, payload: str) -> None:
    """Publish while the caller holds this report's exclusive recovery lock."""
    fd = -1
    temporary: Path | None = None
    backup: Path | None = None
    installed = False
    report_dir = out.parent
    _ensure_study_report_recovered_unlocked(report_dir)
    try:
        paths.mkdir_durable(report_dir)
        fd, raw_path = tempfile.mkstemp(
            prefix=".latest-", suffix=".tmp", dir=report_dir)
        temporary = Path(raw_path)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            _write_report_payload(handle, payload)
            handle.flush()
            os.fsync(handle.fileno())
        if out.exists():
            backup = _create_report_backup(out)
            # The old canonical name remains in place.  First make both its
            # recovery copy and the prepared journal durable; an interrupted
            # publication can then never leave only an unlabelled LKG behind.
            paths.fsync_dir(report_dir)
            _begin_recovery_journal(report_dir, backup)
        os.replace(temporary, out)
        installed = True
        temporary = None
        paths.fsync_dir(report_dir)
        if backup is not None:
            _mark_recovery_journal_installed(
                report_dir, backup, hashlib.sha256(payload.encode()).hexdigest()
            )
            _finalize_recovery_journal(report_dir, backup)
            backup = None
    except BaseException as exc:
        # A wrapper may raise after performing os.replace. Infer the completed swap
        # from consumption of the staged name so rollback never mistakes new bytes
        # for an untouched old canonical report.
        if not installed and temporary is not None and not temporary.exists():
            installed = True
            temporary = None
        if fd >= 0:
            try:
                os.close(fd)
            except BaseException:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except BaseException:
                pass

        # Process-level crash signals preserve the atomic rename's state: before
        # replace the old canonical remains; after replace the new canonical remains.
        if not isinstance(exc, Exception):
            raise

        if installed:
            if backup is not None:
                _ensure_study_report_recovered_unlocked(report_dir)
                backup = None
            else:
                _recover_absent_report(out)
        if backup is not None:
            # A journal creation failure occurs before the canonical swap.  A
            # markerless copy may be removed only after proving it duplicates the
            # still-canonical LKG; otherwise preserve it for quarantine.
            marker = report_dir / _RECOVERY_MARKER_NAME
            if marker.exists():
                _ensure_study_report_recovered_unlocked(report_dir)
            else:
                _remove_matching_report_backups(report_dir)
        if not installed:
            try:
                if report_dir.is_dir():
                    paths.fsync_dir(report_dir)
            except BaseException:
                pass
        raise StudyReportPersistenceError(
            "study review report persistence failed") from None


def _recover_absent_report(out: Path) -> None:
    """Restore the pre-publication state when no prior report existed."""
    try:
        out.unlink(missing_ok=True)
        paths.fsync_dir(out.parent)
        if out.exists():
            raise OSError("failed report still exists")
    except Exception:
        raise StudyReportRecoveryError(
            "study report recovery failed") from None


def _journal_payload(
    state: str,
    backup: Path,
    expected_sha256: str,
    installed_sha256: str | None = None,
) -> bytes:
    """Return the narrowly validated, path-free recovery journal payload."""
    payload: dict[str, object] = {
        "version": 2,
        "state": state,
        "backup_filename": backup.name,
        "expected_sha256": expected_sha256,
    }
    if installed_sha256 is not None:
        payload["installed_sha256"] = installed_sha256
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("ascii")


def _write_recovery_journal_payload(handle, payload: bytes) -> None:
    """Write every journal byte; kept narrow for durability fault injection."""
    remaining = memoryview(payload)
    while remaining:
        written = handle.write(remaining)
        if written is None or written <= 0:
            raise OSError("short recovery journal write")
        remaining = remaining[written:]


def _fsync_recovery_journal_file(handle) -> None:
    """Flush a journal file through the same narrow fault-injection seam."""
    os.fsync(handle.fileno())


def _begin_recovery_journal(
    report_dir: Path,
    backup: Path,
) -> None:
    """Durably record the prepared state before replacing the canonical name."""
    marker = report_dir / _RECOVERY_MARKER_NAME
    try:
        expected_sha256 = hashlib.sha256(backup.read_bytes()).hexdigest()
        descriptor = os.open(
            marker,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            _write_recovery_journal_payload(
                handle, _journal_payload("prepared", backup, expected_sha256)
            )
            handle.flush()
            _fsync_recovery_journal_file(handle)
        paths.fsync_dir(report_dir)
    except Exception:
        raise StudyReportRecoveryError(
            "study report recovery failed") from None


def _mark_recovery_journal_installed(
    report_dir: Path,
    backup: Path,
    installed_sha256: str,
) -> None:
    """Atomically record that the new canonical bytes were installed and synced."""
    marker = report_dir / _RECOVERY_MARKER_NAME
    try:
        expected_sha256 = hashlib.sha256(backup.read_bytes()).hexdigest()
        state, recorded_backup, prior, _recorded_installed = (
            _validated_recovery_journal(report_dir, marker)
        )
        if (
            state != "prepared"
            or recorded_backup != backup
            or prior != backup.read_bytes()
            or not isinstance(installed_sha256, str)
            or _SHA256_RE.fullmatch(installed_sha256) is None
            or hashlib.sha256(
                (report_dir / "latest.json").read_bytes()
            ).hexdigest() != installed_sha256
        ):
            raise OSError("invalid prepared recovery transition")
        _replace_recovery_journal(
            report_dir,
            marker,
            _journal_payload(
                "installed", backup, expected_sha256, installed_sha256
            ),
        )
    except Exception:
        raise StudyReportRecoveryError(
            "study report recovery failed") from None


def _replace_recovery_journal(
    report_dir: Path,
    marker: Path,
    payload: bytes,
) -> None:
    """Durably replace a valid marker without ever truncating its authority."""
    temporary: Path | None = None
    descriptor = -1
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=".latest-recovery-journal-",
            suffix=".tmp",
            dir=report_dir,
        )
        temporary = Path(raw_temporary)
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            _write_recovery_journal_payload(handle, payload)
            handle.flush()
            _fsync_recovery_journal_file(handle)
        # A wrapper can raise after replacing.  In that case the complete new
        # record is still authoritative; callers recover from the marker rather
        # than treating this as an in-place write failure.
        os.replace(temporary, marker)
        temporary = None
        paths.fsync_dir(report_dir)
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _validated_recovery_journal(
    report_dir: Path,
    marker: Path,
) -> tuple[str, Path, bytes | None, str | None]:
    """Load a journal only with its exact named backup and recognized state."""
    try:
        state = json.loads(marker.read_text(encoding="ascii"))
        if not isinstance(state, dict):
            raise ValueError("invalid recovery state")
        journal_state = state.get("state")
        legacy = (
            set(state) == {
                "version", "state", "backup_filename", "expected_sha256"
            }
            and state.get("version") == 1
            and journal_state == "restore_required"
        )
        prepared = (
            set(state) == {
                "version", "state", "backup_filename", "expected_sha256"
            }
            and state.get("version") == 2
            and journal_state == "prepared"
        )
        installed = (
            set(state) == {
                "version", "state", "backup_filename", "expected_sha256",
                "installed_sha256",
            }
            and state.get("version") == 2
            and journal_state == "installed"
            and isinstance(state.get("installed_sha256"), str)
            and _SHA256_RE.fullmatch(state["installed_sha256"]) is not None
        )
        cleanup_pending = (
            set(state) == {
                "version", "state", "backup_filename", "expected_sha256",
                "installed_sha256",
            }
            and state.get("version") == 2
            and journal_state == "cleanup_pending"
            and isinstance(state.get("installed_sha256"), str)
            and _SHA256_RE.fullmatch(state["installed_sha256"]) is not None
        )
        if not (legacy or prepared or installed or cleanup_pending):
            raise ValueError("invalid recovery state")
        if (
            not isinstance(state["backup_filename"], str)
            or _BACKUP_NAME_RE.fullmatch(state["backup_filename"]) is None
            or not isinstance(state["expected_sha256"], str)
            or _SHA256_RE.fullmatch(state["expected_sha256"]) is None
        ):
            raise ValueError("invalid recovery state")
        backup = report_dir / state["backup_filename"]
        try:
            prior = backup.read_bytes()
        except FileNotFoundError:
            # Only cleanup_pending may have durably removed its validated old
            # bytes before its marker.  Its installed hash still proves the
            # canonical report that remains acceptable.
            if not cleanup_pending:
                raise ValueError("invalid recovery backup")
            prior = None
        if (
            prior is not None
            and hashlib.sha256(prior).hexdigest() != state["expected_sha256"]
        ):
            raise ValueError("invalid recovery backup")
        installed_sha256 = (
            state["installed_sha256"] if installed or cleanup_pending else None
        )
        return journal_state, backup, prior, installed_sha256
    except Exception:
        raise StudyReportRecoveryError(
            "study report recovery failed") from None


def _stage_recovery_backup(backup: Path) -> Path:
    """Create a durable atomic-restore source while retaining the named backup."""
    descriptor, raw_staged = tempfile.mkstemp(
        prefix=".latest-recovery-",
        suffix=".tmp",
        dir=backup.parent,
    )
    os.close(descriptor)
    staged = Path(raw_staged)
    staged.unlink()
    try:
        try:
            os.link(backup, staged)
        except OSError:
            shutil.copyfile(backup, staged)
            with staged.open("rb") as handle:
                os.fsync(handle.fileno())
        paths.fsync_dir(backup.parent)
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _remove_matching_report_backups(report_dir: Path) -> None:
    """Remove markerless backups only when each exactly duplicates canonical."""
    backups = list(report_dir.glob(".latest-*.bak"))
    if not backups:
        return
    try:
        out = report_dir / "latest.json"
        if not out.is_file():
            raise OSError("canonical report is unavailable")
        canonical = out.read_bytes()
        if any(backup.read_bytes() != canonical for backup in backups):
            raise OSError("markerless recovery backup differs from canonical")
        for backup in backups:
            backup.unlink()
        paths.fsync_dir(report_dir)
    except Exception:
        raise StudyReportRecoveryError(
            "study report recovery failed") from None


def _clean_recovery_journal(
    report_dir: Path,
    marker: Path,
    backup: Path,
) -> None:
    """Remove only a journal whose backup exactly duplicates the canonical."""
    if not _report_matches(report_dir / "latest.json", backup.read_bytes()):
        raise OSError("recovery cleanup requires matching bytes")
    marker.unlink()
    paths.fsync_dir(report_dir)
    backup.unlink()
    paths.fsync_dir(report_dir)


def _restore_recovery_backup(
    report_dir: Path,
    marker: Path,
    backup: Path,
    prior: bytes,
) -> None:
    """Atomically restore exact LKG bytes, then durably remove its journal."""
    staged: Path | None = None
    out = report_dir / "latest.json"
    try:
        staged = _stage_recovery_backup(backup)
        os.replace(staged, out)
        staged = None
        paths.fsync_dir(report_dir)
        if not _report_matches(out, prior):
            raise OSError("restored report verification failed")
        _clean_recovery_journal(report_dir, marker, backup)
    except Exception:
        if staged is not None:
            try:
                staged.unlink(missing_ok=True)
            except Exception:
                pass
        raise


def _complete_cleanup_pending(
    report_dir: Path,
    marker: Path,
    backup: Path,
    prior: bytes | None,
    installed_sha256: str,
) -> None:
    """Finish a verified cleanup without ever exposing a differing old LKG."""
    out = report_dir / "latest.json"
    try:
        if hashlib.sha256(out.read_bytes()).hexdigest() != installed_sha256:
            raise OSError("installed report verification failed")
        if prior is not None:
            # ``_validated_recovery_journal`` has already proved the old
            # generation's exact hash before making it unavailable.
            backup.unlink()
            paths.fsync_dir(report_dir)
        elif backup.exists():
            # A named artifact that reappeared after a missing-backup cleanup
            # boundary is not an authorized recovery source.
            raise OSError("invalid recovery backup")
        # If unlink raised after succeeding, retrying this operation sees the
        # known cleanup_pending marker plus the verified installed canonical and
        # safely completes marker removal.
        marker.unlink()
        paths.fsync_dir(report_dir)
    except Exception:
        raise


def _finalize_recovery_journal(report_dir: Path, backup: Path) -> None:
    """Finish a successful publication without exposing a markerless LKG."""
    marker = report_dir / _RECOVERY_MARKER_NAME
    state, recorded_backup, prior, installed_sha256 = (
        _validated_recovery_journal(report_dir, marker)
    )
    if (
        state != "installed"
        or recorded_backup != backup
        or prior is None
        or installed_sha256 is None
        or hashlib.sha256(
            (report_dir / "latest.json").read_bytes()
        ).hexdigest() != installed_sha256
    ):
        raise StudyReportRecoveryError("study report recovery failed")
    try:
        _replace_recovery_journal(
            report_dir,
            marker,
            _journal_payload(
                "cleanup_pending",
                backup,
                hashlib.sha256(prior).hexdigest(),
                installed_sha256,
            ),
        )
        _complete_cleanup_pending(
            report_dir, marker, backup, prior, installed_sha256
        )
    except Exception:
        raise StudyReportRecoveryError(
            "study report recovery failed") from None


def _ensure_study_report_recovered(report_dir: Path) -> None:
    """Recover a quarantined report before any study lifecycle can proceed.

    The marker and durable backup are authoritative while present.  Canonical
    ``latest.json`` is never read until an atomic replacement has installed the
    validated backup bytes.
    """
    if not report_dir.exists():
        return
    with _report_lock(report_dir):
        _ensure_study_report_recovered_unlocked(report_dir)


def _ensure_study_report_recovered_unlocked(report_dir: Path) -> None:
    """Recover while the caller holds this report's exclusive recovery lock."""
    marker = report_dir / _RECOVERY_MARKER_NAME
    if not marker.exists():
        _remove_matching_report_backups(report_dir)
        return

    state, backup, prior, installed_sha256 = _validated_recovery_journal(
        report_dir, marker
    )
    try:
        # A prepared journal whose canonical bytes are still the LKG has not
        # crossed the swap boundary.  It is safe to discard only because both
        # names have been proven byte-identical.  All other journal states,
        # including legacy markers, conservatively restore the LKG.
        if state == "cleanup_pending":
            if installed_sha256 is None:
                raise OSError("invalid cleanup recovery state")
            _complete_cleanup_pending(
                report_dir, marker, backup, prior, installed_sha256
            )
        elif state == "prepared" and prior is not None and _report_matches(
                report_dir / "latest.json", prior):
            _clean_recovery_journal(report_dir, marker, backup)
        else:
            if prior is None:
                raise OSError("missing recovery backup")
            _restore_recovery_backup(report_dir, marker, backup, prior)
    except Exception:
        raise StudyReportRecoveryError(
            "study report recovery failed") from None


def _report_matches(out: Path, expected: bytes) -> bool:
    """Return whether the canonical report is readable and byte-exact."""
    try:
        return out.read_bytes() == expected
    except OSError:
        return False


def _create_report_backup(out: Path) -> Path:
    """Create a durable sibling recovery copy without moving the canonical LKG."""
    backup_fd, raw_backup = tempfile.mkstemp(
        prefix=".latest-", suffix=".bak", dir=out.parent
    )
    os.close(backup_fd)
    backup = Path(raw_backup)
    backup.unlink()
    try:
        try:
            os.link(out, backup)
        except OSError:
            shutil.copyfile(out, backup)
            with backup.open("rb") as handle:
                os.fsync(handle.fileno())
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
    return backup


def _write_report_payload(handle, payload: str) -> None:
    """Narrow staged-write seam used by atomicity failure tests."""
    handle.write(payload)


def review_study(
    vault_: vault.Vault,
    db,
    *,
    candidate_id: str,
    max_age_days: int,
    registry_snapshot: crs_rules.RegistrySnapshot | None = None,
    read_only: bool = False,
    no_report: bool = False,
) -> dict:
    """Review confirmed Canadian-study evidence against the pinned local snapshot."""
    _ensure_study_report_recovered(
        _latest_report_path(vault_.root).parent
    )
    result_fingerprint = (
        registry_snapshot.fingerprint if registry_snapshot is not None else None
    )

    def pack(*args, **kwargs):
        kwargs["registry_fingerprint"] = result_fingerprint
        return _pack(*args, **kwargs)

    suppress_report = read_only or no_report

    def finish_without_report(result: dict) -> dict:
        """Return the current refusal while preserving the latest successful report."""
        return result

    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int):
        return finish_without_report(pack("AT-RISK", "snapshot_config_invalid"))
    if max_age_days <= 0:
        return finish_without_report(pack("AT-RISK", "snapshot_config_invalid"))

    health = index_health.probe_snapshot(
        db, "dli", max_age_days=max_age_days)
    if not health.ok():
        return finish_without_report(pack("AT-RISK", "snapshot_unusable"))

    try:
        candidate_id = paths.safe_candidate_id(candidate_id)
        snapshot = (
            registry_snapshot
            if registry_snapshot is not None
            else crs_rules.load_registry_snapshot()
        )
        result_fingerprint = snapshot.fingerprint
        static_rows = _static_rows(snapshot.registry)
        all_values, eligible = _candidate_values(
            vault_, candidate_id, snapshot.fingerprint)
    except (
        ValueError,
        TypeError,
        auditor.AuditGroundingError,
        crs_rules.RegistryUnavailable,
    ):
        return finish_without_report(pack("AT-RISK", "grounding_refused"))

    confirmed_count = len({
        value.field_name for value, _ in all_values
        if value.confirmation_status in ("confirmed", "corrected")
    })
    eligible_count = len({value.field_name for value, _ in eligible})
    if not eligible:
        return finish_without_report(pack(
            "N/A", "no_study_evidence",
            confirmed_count=confirmed_count, eligible_count=eligible_count))

    fields = _collapse_eligible(eligible)
    if fields is None:
        return finish_without_report(pack(
            "AT-RISK", "ambiguous_study_evidence",
            confirmed_count=confirmed_count, eligible_count=eligible_count))
    missing = [field for field in _REQUIRED_FIELDS if field not in fields]
    if missing:
        return finish_without_report(pack(
            "GAP", "missing_study_fields",
            confirmed_count=confirmed_count, eligible_count=eligible_count))

    try:
        start = date.fromisoformat(str(fields["program_start"]["value"]))
        end = date.fromisoformat(str(fields["program_end"]["value"]))
    except (TypeError, ValueError):
        return finish_without_report(pack(
            "AT-RISK", "ambiguous_study_evidence",
            confirmed_count=confirmed_count, eligible_count=eligible_count))
    if start > end:
        return finish_without_report(pack(
            "AT-RISK", "ambiguous_study_evidence",
            confirmed_count=confirmed_count, eligible_count=eligible_count))

    dli = dlifields.normalize_dli(fields["dli_number"]["value"])
    if dli is None:
        return finish_without_report(pack(
            "AT-RISK", "exact_dli_mismatch",
            confirmed_count=confirmed_count, eligible_count=eligible_count))
    try:
        resolved = _resolve_candidate_chunks(db, dli)
    except (OSError, TypeError, ValueError):
        resolved = None
    if resolved is None:
        return finish_without_report(pack(
            "AT-RISK", "exact_dli_mismatch",
            confirmed_count=confirmed_count, eligible_count=eligible_count))
    designation, pgwp_chunks = resolved
    crawl_dates = [
        chunk.get("crawl_date") for chunk in (designation, *pgwp_chunks)
    ]
    if (not crawl_dates
            or any(not isinstance(value, str) or not value for value in crawl_dates)
            or len(set(crawl_dates)) != 1):
        return finish_without_report(pack(
            "AT-RISK", "snapshot_provenance_mismatch",
            confirmed_count=confirmed_count, eligible_count=eligible_count))
    as_of = crawl_dates[0]
    if not _candidate_snapshot_provenance(
            dli, designation, pgwp_chunks, as_of,
            max_age_days=max_age_days):
        return finish_without_report(pack(
            "AT-RISK", "snapshot_provenance_mismatch",
            confirmed_count=confirmed_count, eligible_count=eligible_count))

    built = _dynamic_rows(dli, designation, pgwp_chunks)
    if built is None:
        return finish_without_report(pack(
            "AT-RISK", "exact_dli_mismatch",
            confirmed_count=confirmed_count, eligible_count=eligible_count))
    dynamic_rows, dynamic_citations = built
    temporary = Registry(rows=[*static_rows, *dynamic_rows])

    try:
        auditor.gate_subset(temporary, db)
    except (auditor.AuditGroundingError, OSError, TypeError, ValueError):
        return finish_without_report(pack(
            "AT-RISK", "grounding_refused",
            confirmed_count=confirmed_count, eligible_count=eligible_count))

    credential = str(fields["credential_level"]["value"])
    status = str(fields["study_status"]["value"])
    if credential not in _grounded_tiers(static_rows[0]):
        reason = "below_grounded_credential_tier"
        public_status = "GAP"
    elif status not in _grounded_statuses(static_rows[1]):
        reason = "study_not_completed"
        public_status = "GAP"
    else:
        reason = _pgwp_reason(dynamic_rows)
        public_status = "AT-RISK"

    result = pack(
        public_status, reason,
        confirmed_count=confirmed_count,
        eligible_count=eligible_count,
        as_of=as_of,
    )
    if suppress_report:
        return result
    try:
        _write_private_report(
            vault_,
            candidate_id=candidate_id,
            fields=fields,
            static_rows=static_rows,
            dynamic_citations=dynamic_citations,
            result=result,
        )
    except StudyReportPersistenceError:
        return pack(
            "AT-RISK", "report_write_failed",
            confirmed_count=confirmed_count, eligible_count=eligible_count)
    return pack(
        public_status, reason,
        confirmed_count=confirmed_count,
        eligible_count=eligible_count,
        as_of=as_of,
        report_created=True,
    )
