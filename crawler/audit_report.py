"""Vault-only, fail-closed audit report writer (Phase 32 — AUDIT-02 / AUDIT-06).

``run_audit`` is the orchestration seam between the pure verdict engine
(``crawler.auditor.audit_factor``, Plan 03) and the CLI (Plan 05):

1. Compute the verdict FIRST. If ``audit_factor`` raises
   :class:`crawler.auditor.AuditGroundingError`, it propagates unchanged and NO
   artifact is written — no report file, no ``audit_runs`` row, no
   ``factor_verdicts`` row (SC5: "a grounding failure writes no partial report").
   Because nothing is persisted until AFTER a verdict is computed, the vault can
   never hold a half-finished report.
2. On a valid verdict (SUBSTANTIATED / GAP / AT-RISK / N/A), write the full
   evidence-bearing :class:`crawler.models.audit.PrivateAuditReport` as JSON AND a
   human-readable factor-card Markdown, ONLY under
   ``candidates/<id>/output/crs-audit/<run_id>.{json,md}`` (every path re-anchored
   through ``crawler.paths.resolve_within``, which rejects ``..`` / symlink
   escapes); persist the ``audit_runs`` + ``factor_verdicts`` rows; and
   down-project the report to a PII-light
   :class:`crawler.models.audit.PublicAuditEnvelope` carrying an opaque locator
   relative to the selected candidate vault root.

The ``output/crs-audit/`` subtree + the ``.json``/``.md`` extensions are already
inside the shipped publish-safe ``VAULT_SUBTREES`` / ``VAULT_ARTIFACT_EXTS``
allow-list, so the written artifact is publish-safe-covered the moment it lands.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from crawler import auditor, paths
from crawler import vault as vault_module
from crawler.models.audit import (
    PrivateAuditReport,
    PublicAuditEnvelope,
    to_public_envelope,
)

# The vault subtree the evidence-bearing report lands in (publish-safe covered).
_REPORT_SUBTREE = ("output", "crs-audit")

# --------------------------------------------------------------------------- #
# SCREENING_NOTICE — the SAFE-04 framing rendered into every vault report.
#
# Frames the output as CRS substantiation SCREENING, not legal advice; defines
# SUBSTANTIATED NARROWLY (a deterministic match only); and states that semantic /
# NOC-duty fit, document authenticity, and officer discretion stay AT-RISK. It is
# GENERIC and PII-FREE — it carries no applicant value and no machine path, so it
# renders into a vault report without itself becoming personal data. Every
# occurrence of the phrase "legal advice" here is the NEGATED disclaimer ("not
# legal advice") so the SAFE-04 denylist scan stays clean.
# --------------------------------------------------------------------------- #
SCREENING_NOTICE = (
    "## Substantiation screening — scope & limits\n"
    "\n"
    "This report is a **CRS substantiation screening**. It is **not legal "
    "advice** and **not a substitute** for a licensed immigration consultant or "
    "lawyer. It does not decide your case and makes no eligibility ruling or "
    "outcome prediction.\n"
    "\n"
    "A factor is marked **SUBSTANTIATED** only under a narrow, deterministic "
    "definition: the required proof is present, the backing evidence is confirmed "
    "and audit-eligible, the confirmed value meets the claimed threshold, and a "
    "corpus-grounded, cited admissibility rule applies — a deterministic match, "
    "nothing more.\n"
    "\n"
    "Everything that needs human judgement stays **AT-RISK** and requires human "
    "or professional review: semantic fit, NOC-duty (job-duty) fit, document "
    "authenticity, and officer discretion are never SUBSTANTIATED by this "
    "screening. A stale, expired, or unconfirmed input is AT-RISK, never green.\n"
)

# The audit_runs.factor_id sentinel for a full-grid run (the single-factor path
# stores the real factor id; the full-grid path audits every grid factor).
_FULL_GRID_FACTOR_ID = "*full-grid*"


class AuditPersistenceError(RuntimeError):
    """A stable, path-free audit persistence failure for public boundaries."""


def _best_effort_fsync_dir(directory: Path) -> None:
    """Attempt cleanup durability without masking the operation's real outcome."""
    try:
        paths.fsync_dir(directory)
    except BaseException:
        pass


def _vault_relative(vault, *parts: str) -> str:
    """Return a path under the candidate root, RELATIVE to the personal root.

    ``vault.root`` is ``<personal-root>/candidates/<id>`` so the personal root is
    its grandparent; the returned string is e.g.
    ``candidates/<id>/output/crs-audit/<run_id>.json`` — never absolute.
    """
    personal_root = vault.root.parent.parent
    target = vault.root.joinpath(*parts).resolve()
    return target.relative_to(personal_root.resolve()).as_posix()


def _candidate_relative(vault, *parts: str) -> str:
    """Return an opaque locator interpreted relative to this candidate vault root."""
    target = vault.root.joinpath(*parts).resolve()
    return target.relative_to(vault.root.resolve()).as_posix()


def _render_factor_card_markdown(report: PrivateAuditReport) -> str:
    """Render a human-readable, PII-BEARING factor-card summary (vault-only).

    Carries the applicant confirmed values + ``ev_`` evidence pointers + rule
    citations — which is exactly why the write is vault-only.
    """
    lines: list[str] = [
        f"# CRS Audit Report — {report.run_id}",
        "",
        f"- Candidate: `{report.candidate_id}`",
        f"- Created: {report.created_at}",
        f"- Substantiated total: {report.substantiated_total}",
    ]
    ita_round_id = getattr(report, "ita_round_id", None)
    if ita_round_id is not None:
        lines.append(f"- ITA round: `{ita_round_id}`")
    # Cutoff comparison — a pure arithmetic score gap, NOT an eligibility ruling
    # or legal advice (AUDIT-05 / SAFE-04 framing). Only rendered for a full-grid
    # run that carries a cutoff delta.
    if report.cutoff_delta is not None:
        relation = "meets" if report.meets_cutoff else "does not meet"
        lines.append(
            f"- Cutoff comparison: the substantiated total {relation} the ITA "
            f"round cutoff by {abs(report.cutoff_delta)} point(s) "
            f"(arithmetic delta {report.cutoff_delta})."
        )
    lines.append("")
    for card in report.factor_cards:
        # COV-02: an unpriced SUBSTANTIATED card renders an explicit unresolved line
        # (never a bare numeric / None), so it can never read as a plain 0. The
        # wording is a neutral data-completeness statement — not eligibility/legal
        # framing — and names no volatile CLB/points literal.
        if card.points_unresolved:
            points_line = (
                "- Substantiated points: UNRESOLVED (unpriced — no grounded "
                "point row)"
            )
        else:
            points_line = f"- Substantiated points: {card.substantiated_points}"
        lines.extend([
            f"## Factor: `{card.factor_id}` — **{card.verdict}**",
            "",
            f"- Reason: `{card.reason_code}`",
            f"- Claimed: `{card.claimed_value}`",
            f"- Confirmed: `{card.confirmed_value}`",
            points_line,
            f"- Score delta: {card.score_delta}",
            f"- Evidence: {', '.join(card.evidence_ids) or '(none)'}",
            f"- Rule citations: {', '.join(card.rule_citation_ids) or '(none)'}",
            "",
        ])
    # SAFE-04 framing: the narrow-SUBSTANTIATED + AT-RISK-scope + not-legal-advice
    # screening notice renders into EVERY vault report (single + full-grid).
    lines.append(SCREENING_NOTICE)
    return "\n".join(lines)


def _stage_text(final_path: Path, text: str) -> Path:
    """Write and fsync a unique sibling temp file, returning its path."""
    fd, temp_name = tempfile.mkstemp(
        dir=final_path.parent,
        prefix=f".{final_path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # ``os.fdopen`` can fail before taking ownership of the descriptor.
        # Closing an already-owned/already-closed descriptor is harmless here.
        try:
            os.close(fd)
        except BaseException:
            pass
        try:
            temp_path.unlink(missing_ok=True)
        except BaseException:
            pass
        raise
    return temp_path


def _remove_paths(paths_to_remove: list[Path]) -> None:
    """Best-effort cleanup that never replaces the original failure."""
    for path in paths_to_remove:
        try:
            path.unlink(missing_ok=True)
        except BaseException:
            pass


def _backup_existing(path: Path) -> Path | None:
    """Move a colliding immutable output aside until the transaction commits."""
    if not path.exists():
        return None
    fd, backup_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".bak",
    )
    os.close(fd)
    backup = Path(backup_name)
    try:
        os.replace(path, backup)
    except BaseException:
        _remove_paths([backup])
        raise
    return backup


def _restore_backups(backups: list[tuple[Path, Path]]) -> None:
    """Best-effort restoration of outputs moved aside before publication."""
    for final_path, backup_path in reversed(backups):
        try:
            final_path.unlink(missing_ok=True)
        except BaseException:
            pass
        try:
            os.replace(backup_path, final_path)
        except BaseException:
            # Keep the backup when restoration itself fails. Losing the only
            # preserved copy would be worse than leaving a private temp behind.
            pass


def _commit_transaction(vault) -> None:
    """Commit the report transaction (a narrow failure-injection seam)."""
    vault.con.commit()


def _durable_report_commit(
        vault, *, audit_run_id: str, report: PrivateAuditReport,
        report_relpath: str) -> bool | None:
    """Classify a commit after its call raised.

    ``True`` means the connection is out of transaction and the exact completed
    run, report metadata, and verdict cardinality are durably visible. Publication
    fsyncs both report directory entries before SQLite is allowed to commit, so a
    durable row also has durable report targets. ``False`` means the transaction
    is still active or the query disproves that exact commit. ``None`` is
    deliberately ambiguous: connection inspection or the parameter-bound
    confirmation query failed.
    """
    try:
        if vault.con.in_transaction:
            return False
        row = vault.con.execute(
            "SELECT status, rule_registry_version, report_relpath, "
            "completed_at IS NOT NULL, "
            "(SELECT COUNT(*) FROM factor_verdicts "
            " WHERE audit_run_id = audit_runs.audit_run_id) "
            "FROM audit_runs WHERE audit_run_id = ?",
            (audit_run_id,),
        ).fetchone()
    except BaseException:
        return None
    return bool(
        row is not None
        and row[0] == "complete"
        and row[1] == report.registry_fingerprint
        and row[2] == report_relpath
        and row[3] == 1
        and row[4] == len(report.factor_cards)
    )


def _persist_report(vault, report: PrivateAuditReport, *,
                    factor_id: str, ita_round_id: str | None) -> str:
    """Publish recoverably ordered files followed by one complete DB transaction.

    Two files plus SQLite cannot form one globally atomic filesystem transaction.
    Instead, both staged file contents and their final directory entries are fsynced
    before SQLite commits its references. Pre-commit failures roll back the rows and
    restore collisions; an ambiguous post-commit failure keeps reports and backups
    for conservative recovery.
    """
    # Never commandeer a caller-owned transaction.  In particular, do not stage
    # files and do not commit/rollback unrelated uncommitted caller work.
    if vault.con.in_transaction:
        raise AuditPersistenceError("audit report persistence failed") from None

    staged: list[Path] = []
    published: list[Path] = []
    backups: list[tuple[Path, Path]] = []
    begin_attempted = False
    transaction_owned = False
    commit_attempted = False
    out_dir: Path | None = None
    try:
        audit_run_id = vault_module.new_audit_run_id()
        report.run_id = audit_run_id
        out_dir = paths.resolve_within(vault.root, *_REPORT_SUBTREE)
        paths.mkdir_durable(out_dir)
        json_path = paths.resolve_within(out_dir, f"{audit_run_id}.json")
        md_path = paths.resolve_within(out_dir, f"{audit_run_id}.md")
        report_relpath = _vault_relative(
            vault, *_REPORT_SUBTREE, f"{audit_run_id}.json")

        staged.append(_stage_text(
            json_path,
            json.dumps(report.model_dump(), ensure_ascii=False),
        ))
        staged.append(_stage_text(
            md_path,
            _render_factor_card_markdown(report),
        ))

        begin_attempted = True
        vault.con.execute("BEGIN")
        transaction_owned = True
        vault_module._insert_audit_run(
            vault,
            audit_run_id=audit_run_id,
            candidate_id=vault.candidate_id,
            factor_id=factor_id,
            rule_registry_version=report.registry_fingerprint,
            ita_round_id=ita_round_id,
            status="running",
        )
        for card in report.factor_cards:
            vault_module._insert_factor_verdict(
                vault,
                verdict_id=vault_module.new_verdict_id(),
                audit_run_id=audit_run_id,
                factor_id=card.factor_id,
                verdict=card.verdict,
                reason_code=card.reason_code,
                substantiated_points=card.substantiated_points,
                score_delta=card.score_delta,
                evidence_ids=card.evidence_ids,
                rule_citation_ids=card.rule_citation_ids,
            )
        vault_module._complete_audit_run(
            vault,
            audit_run_id,
            status="complete",
            report_relpath=report_relpath,
            substantiated_total=report.substantiated_total,
            cutoff_delta=report.cutoff_delta,
        )

        json_backup = _backup_existing(json_path)
        if json_backup is not None:
            backups.append((json_path, json_backup))
        published.append(json_path)
        os.replace(staged[0], json_path)
        md_backup = _backup_existing(md_path)
        if md_backup is not None:
            backups.append((md_path, md_backup))
        published.append(md_path)
        os.replace(staged[1], md_path)
        # File contents were fsynced while staged. Flush both final names (and any
        # collision-backup renames) before SQLite can make their references durable.
        paths.fsync_dir(out_dir)
        commit_attempted = True
        _commit_transaction(vault)
    except BaseException as exc:
        commit_state = (
            _durable_report_commit(
                vault,
                audit_run_id=audit_run_id,
                report=report,
                report_relpath=report_relpath,
            )
            if commit_attempted
            else False
        )
        if commit_state is True:
            # The commit is authoritative. Never delete its referenced reports or
            # restore stale collision backups merely because a wrapper raised
            # after sqlite made the transaction durable.
            _remove_paths([backup for _, backup in backups])
            if backups and out_dir is not None:
                _best_effort_fsync_dir(out_dir)
            if not isinstance(exc, Exception):
                # Preserve control-flow semantics only after preserving the
                # now-consistent durable state.
                raise
        else:
            # BEGIN may have taken effect before a failure-injection wrapper
            # raised. Since the connection was transaction-free on entry, this
            # operation owns any transaction left behind.
            if begin_attempted:
                try:
                    transaction_owned = (
                        transaction_owned or vault.con.in_transaction)
                except BaseException:
                    pass
            if transaction_owned:
                try:
                    vault.con.rollback()
                except BaseException:
                    pass

            if commit_state is False:
                _remove_paths(published)
                _restore_backups(backups)
                if out_dir is not None and (published or backups):
                    _best_effort_fsync_dir(out_dir)
            # If commit confirmation itself is unavailable, fail closed but keep
            # both published reports and collision backups. Orphan private files
            # are safer than deleting files that a possibly durable row names.
            if isinstance(exc, Exception):
                raise AuditPersistenceError(
                    "audit report persistence failed") from None
            raise
    else:
        _remove_paths([backup for _, backup in backups])
        if backups and out_dir is not None:
            _best_effort_fsync_dir(out_dir)
    finally:
        _remove_paths(staged)
        if staged and out_dir is not None:
            _best_effort_fsync_dir(out_dir)
    return report_relpath


def run_audit(vault, factor_id: str, db, registry, *,
              ita_round_id: str | None = None,
              spouse_mode: bool = False,
              registry_fingerprint: str | None = None,
              explicit_root: str | None = None
              ) -> tuple[PrivateAuditReport, PublicAuditEnvelope]:
    """Compute a verdict, then write the vault-only report + persist the trail.

    Returns ``(PrivateAuditReport, PublicAuditEnvelope)``. Raises
    :class:`crawler.auditor.AuditGroundingError` — leaving ZERO artifacts — on a
    grounding / system failure (SC5).
    """
    supplied_fingerprint = auditor._verified_registry_fingerprint(
        registry, registry_fingerprint)
    effective_round_id = (
        auditor._effective_ita_round_id(vault, ita_round_id)
        if ita_round_id is not None
        else None
    )

    # 1. Compute the verdict FIRST. An AuditGroundingError propagates here with
    #    NO side effects — the writes + persistence below are simply never
    #    reached (fail-closed ordering; SC5).
    report = auditor._audit_factor_verified(
        vault, factor_id, db, registry,
        ita_round_id=effective_round_id, spouse_mode=spouse_mode,
        registry_fingerprint=supplied_fingerprint)

    report_relpath = _persist_report(
        vault, report, factor_id=factor_id, ita_round_id=effective_round_id)

    # The persisted row may keep its private personal-root-relative path. The public
    # envelope gets only a locator relative to the already-selected candidate root.
    public_locator = _candidate_relative(
        vault, *_REPORT_SUBTREE, f"{report.run_id}.json"
    )
    envelope = to_public_envelope(report, private_output_path=public_locator)
    return report, envelope


def run_full_audit_report(vault, db, registry, *,
                          ita_round_id: str | None = None,
                          spouse_mode: bool | None = None,
                          registry_fingerprint: str | None = None,
                          explicit_root: str | None = None
                          ) -> tuple[PrivateAuditReport, PublicAuditEnvelope]:
    """Audit the WHOLE CRS grid, then write the vault-only report + persist the trail.

    Mirrors :func:`run_audit`'s fail-closed ordering over the full grid:

    1. Compute every factor's verdict FIRST via ``auditor.run_full_audit`` — an
       :class:`crawler.auditor.AuditGroundingError` propagates leaving ZERO
       artifacts (SC5).
    2. Persist ONE ``audit_runs`` row, write the multi-card PII-bearing JSON +
       Markdown report ONLY under ``candidates/<id>/output/crs-audit/`` (paths
       re-anchored through ``resolve_within``), persist one ``factor_verdicts``
       row per card, and complete the run with the substantiated total + cutoff
       delta.
    3. Down-project to the PII-light :class:`PublicAuditEnvelope`.

    Returns ``(PrivateAuditReport, PublicAuditEnvelope)``. Raises
    :class:`crawler.auditor.AuditGroundingError` — leaving ZERO artifacts — on a
    grounding / system failure (SC5).
    """
    supplied_fingerprint = auditor._verified_registry_fingerprint(
        registry, registry_fingerprint)
    effective_round_id = auditor._effective_ita_round_id(vault, ita_round_id)

    # 1. Compute the full-grid verdicts FIRST. An AuditGroundingError propagates
    #    here with NO side effects (fail-closed ordering; SC5).
    report = auditor._run_full_audit_verified(
        vault, db, registry, ita_round_id=effective_round_id,
        spouse_mode=spouse_mode,
        registry_fingerprint=supplied_fingerprint)

    report_relpath = _persist_report(
        vault,
        report,
        factor_id=_FULL_GRID_FACTOR_ID,
        ita_round_id=effective_round_id,
    )

    public_locator = _candidate_relative(
        vault, *_REPORT_SUBTREE, f"{report.run_id}.json"
    )
    envelope = to_public_envelope(report, private_output_path=public_locator)
    return report, envelope
