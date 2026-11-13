"""Recoverable, scan-before-publish MEC private report transaction."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from crawler import paths
from crawler.mec_screen import MecPublicationBundle, _render_private_markdown
from crawler.models.mec import PrivateMecReport, PublicMecSummary


class MecPublicationError(RuntimeError):
    """Stable path-free failure at the MEC private publication boundary."""


_ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9.])/(?:[^/\s\"']+/)*[^/\s\"']+"),
    re.compile(r"(?i)\b[A-Z]:[\\/]"),
    re.compile(r"(?:\\\\\\\\|//)[^/\s\"']+"),
    re.compile(r"(?i)\b[A-Z][A-Z0-9+.-]*://"),
    re.compile(r"(?i)\bfile:"),
    re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|$)"),
)
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"github_" r"pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(
        r"(?i)(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?key|token|password)"
        r"\s*[:=]\s*[\"']?[^\"'\s]{12,}"
    ),
)
_PUBLIC_PRIVATE_PATTERNS = (
    re.compile(r"\bev_[0-9a-f]{6,}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"(?i)\b(?:employer|applicant|candidate_id|evidence_ids|applicant_values)\b"),
    re.compile(r"(?<![0-9a-f])\b\d{5}\b(?![0-9a-f])", re.IGNORECASE),
    re.compile(r"(?i)(?:[$£€]\s*\d|\"funds_amount\")"),
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _validate_and_render(
    bundle: MecPublicationBundle,
) -> tuple[PrivateMecReport, PublicMecSummary, bytes, bytes, bytes]:
    """Validate both closed models and reproduce every byte before filesystem work."""
    if not isinstance(bundle, MecPublicationBundle):
        raise MecPublicationError("MEC report publication failed")
    try:
        report = PrivateMecReport.model_validate(
            bundle.private_report.model_dump(mode="json")
        )
        summary = PublicMecSummary.model_validate(
            bundle.public_summary.model_dump(mode="json")
        )
    except (AttributeError, TypeError, ValidationError):
        raise MecPublicationError("MEC report publication failed") from None

    expected_path = f"output/mec/{report.program}/latest.json"
    if (
        report.private_report_path != expected_path
        or summary.private_output_path != expected_path
        or summary.run_id != report.run_id
        or summary.program != report.program
        or summary.status != report.status
        or summary.counts != report.counts
        or summary.registry_fingerprint != report.registry_fingerprint
        or len(summary.criteria) != len(report.criteria)
    ):
        raise MecPublicationError("MEC report publication failed")

    for private, public in zip(report.criteria, summary.criteria):
        if (
            public.criterion_id != private.criterion_id
            or public.status != private.status
            or public.reason_code != private.reason_code
            or public.corpus_citation_ids
        ):
            raise MecPublicationError("MEC report publication failed")

    private_json = _canonical_json(report.model_dump(mode="json"))
    private_markdown = _render_private_markdown(report)
    public_json = _canonical_json(summary.model_dump(mode="json"))
    if (
        bundle.private_json != private_json
        or bundle.private_markdown != private_markdown
        or bundle.public_json != public_json
    ):
        raise MecPublicationError("MEC report publication failed")
    return report, summary, private_json, private_markdown, public_json


def _scan_private_bytes(payload: bytes) -> None:
    """Enforce typed JSON locations plus path/secret defense in depth."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise MecPublicationError("MEC report publication failed") from None
    if text.lstrip().startswith("{"):
        try:
            decoded = json.loads(text)
            report = PrivateMecReport.model_validate(decoded)
        except (json.JSONDecodeError, ValidationError, TypeError):
            raise MecPublicationError("MEC report publication failed") from None
        if _canonical_json(report.model_dump(mode="json")) != payload:
            raise MecPublicationError("MEC report publication failed")
    if any(pattern.search(text) for pattern in (*_ABSOLUTE_PATH_PATTERNS, *_SECRET_PATTERNS)):
        raise MecPublicationError("MEC report publication failed")


def _scan_public_bytes(payload: bytes) -> None:
    """Enforce the closed citation-free, PII-light public summary."""
    try:
        decoded = json.loads(payload)
        summary = PublicMecSummary.model_validate(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError):
        raise MecPublicationError("MEC report publication failed") from None
    if _canonical_json(summary.model_dump(mode="json")) != payload:
        raise MecPublicationError("MEC report publication failed")
    if any(item.corpus_citation_ids for item in summary.criteria):
        raise MecPublicationError("MEC report publication failed")
    text = payload.decode("utf-8")
    if any(
        pattern.search(text)
        for pattern in (
            *_ABSOLUTE_PATH_PATTERNS,
            *_SECRET_PATTERNS,
            *_PUBLIC_PRIVATE_PATTERNS,
        )
    ):
        raise MecPublicationError("MEC report publication failed")


def _stage_bytes(final_path: Path, payload: bytes) -> Path:
    """Write and file-fsync one unique sibling stage."""
    descriptor, name = tempfile.mkstemp(
        dir=final_path.parent,
        prefix=f".{final_path.name}.",
        suffix=".tmp",
    )
    stage = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except BaseException:
            pass
        try:
            stage.unlink(missing_ok=True)
        except BaseException:
            pass
        raise
    return stage


def _replace(source: Path, destination: Path) -> None:
    """Narrow rename seam used by failure-injection tests."""
    os.replace(source, destination)


def _fsync_dir(directory: Path) -> None:
    """Narrow durable-directory seam used by failure-injection tests."""
    paths.fsync_dir(directory)


def _backup_path(final_path: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=final_path.parent,
        prefix=f".{final_path.name}.",
        suffix=".bak",
    )
    os.close(descriptor)
    backup = Path(name)
    backup.unlink()
    return backup


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except BaseException:
        pass


def _remove_backup(path: Path) -> None:
    """Checked backup deletion seam; publication cannot silently skip cleanup."""
    path.unlink(missing_ok=True)


def _cleanup_backups(directory: Path, backups: tuple[Path, ...]) -> None:
    """Retry checked backup removal, then durably commit the directory entries."""
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            for backup in backups:
                _remove_backup(backup)
            _fsync_dir(directory)
            return
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _restore_lkg(
    directory: Path,
    mutated: list[Path],
    installed: set[Path],
    backups: dict[Path, Path],
) -> bool:
    """Restore only journaled mutations from pre-existing backup files."""
    restored = True
    for final in reversed(mutated):
        backup = backups.get(final)
        try:
            if final in installed:
                final.unlink(missing_ok=True)
            if backup is not None and backup.exists():
                # Rollback deliberately bypasses the forward replace seam: a
                # persistent injected/OS failure there must not prevent an
                # already-created backup from restoring the LKG.
                os.replace(backup, final)
            else:
                final.unlink(missing_ok=True)
        except BaseException:
            restored = False
    try:
        _fsync_dir(directory)
    except BaseException:
        restored = False
    if restored:
        for backup in backups.values():
            _remove(backup)
    return restored


def _remove_new_directories(missing: tuple[Path, ...]) -> None:
    for directory in missing:
        try:
            directory.rmdir()
        except OSError:
            pass


def publish_mec_bundle(
    vault_: Any,
    bundle: MecPublicationBundle,
) -> PublicMecSummary:
    """Scan, stage, atomically replace, and durably commit one private MEC LKG."""
    try:
        report, summary, private_json, private_markdown, public_json = (
            _validate_and_render(bundle)
        )
        _scan_private_bytes(private_json)
        _scan_private_bytes(private_markdown)
        _scan_public_bytes(public_json)
        directory = paths.resolve_within(
            vault_.root, "output", "mec", report.program
        )
    except MecPublicationError:
        raise
    except Exception:
        raise MecPublicationError("MEC report publication failed") from None

    missing: list[Path] = []
    cursor = directory
    while not cursor.exists() and cursor != Path(vault_.root):
        missing.append(cursor)
        cursor = cursor.parent

    stages: list[Path] = []
    backups: dict[Path, Path] = {}
    mutated: list[Path] = []
    installed: set[Path] = set()
    committed = False
    json_path = paths.resolve_within(directory, "latest.json")
    markdown_path = paths.resolve_within(directory, "latest.md")
    finals = (json_path, markdown_path)
    try:
        paths.mkdir_durable(directory)
        # Stage and fsync every new payload before the first final-name mutation.
        stages.append(_stage_bytes(json_path, private_json))
        stages.append(_stage_bytes(markdown_path, private_markdown))
        for final in finals:
            if final.exists():
                backup = _backup_path(final)
                backups[final] = backup
                _replace(final, backup)
                mutated.append(final)
        for stage, final in zip(stages, finals):
            _replace(stage, final)
            installed.add(final)
            if final not in mutated:
                mutated.append(final)
        _fsync_dir(directory)
        # The installed names are now durable. Cleanup failures must never
        # roll them back; retry checked backup deletion and fsync that deletion.
        committed = True
        _cleanup_backups(directory, tuple(backups.values()))
    except BaseException as exc:
        for stage in stages:
            _remove(stage)
        if not committed:
            try:
                restored = _restore_lkg(directory, mutated, installed, backups)
            except BaseException:
                restored = False
            if restored:
                _remove_new_directories(tuple(missing))
        if isinstance(exc, Exception):
            raise MecPublicationError("MEC report publication failed") from None
        raise
    else:
        for stage in stages:
            _remove(stage)
        return summary
