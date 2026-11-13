"""Grounded remediation checklist — a deterministic projection of a completed audit
(Phase 37 — REM-01/02/03).

A completed ``vault audit`` writes a fully-grounded
:class:`crawler.models.audit.PrivateAuditReport` to the vault. This module turns that
already-grounded report into a private, corpus-cited **fix checklist** — exactly one
actionable item per unresolved finding (``GAP`` / ``AT-RISK`` / an unpriced
``SUBSTANTIATED``). It is a **pure projection**, NOT a second trust path:

* it reuses the verdicts, reason codes, score deltas, and corpus citation ids the
  audit already computed and gated — it never re-scores or re-grounds;
* the verbatim rule span is copied from the PII-free registry
  (:class:`crawler.models.crs_rules.RuleRow` ``citations[].quote`` — already proven
  verbatim-grounded when the audit ran), looked up by the card's ``rule_citation_ids``;
* it NEVER imports or calls ``crawler.searchindex`` / ``crawler.grounding`` (the
  retrieval/grounding trust path) — an AST import check + a call-level guard enforce
  this (``test_remediation_projection.py``);
* it inlines NO volatile CRS threshold (the ``no_inlined_volatile_rules`` gate covers
  this module) — action templates are generic screening prose.

Two tiers mirror :mod:`crawler.models.audit`: a PII-BEARING private checklist written
ONLY under the vault, and a PII-LIGHT public summary for ``--json`` stdout. Every
rendered artifact carries the same substantiation-screening notice as the audit report.

Pure stdlib + pydantic v2 (already in the stack) — zero new runtime dependency.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crawler import auditor, auditors, crs_rules, paths
from crawler import vault as vault_module
from crawler.audit_report import SCREENING_NOTICE, _candidate_relative
from crawler.models.audit import (
    PrivateAuditReport,
    Verdict,
)
from crawler.models.crs_rules import Registry
from crawler.models.public_locator import (
    AuditRunId,
    RemediationRunId,
    require_exact_output_locator,
)
from crawler.models.vault import FactorGroup

# The corpus content coordinate shape ``relpath#ordinal`` (same as the audit models).
_CITATION_ID_PATTERN = r"^[^#\s]+#\d+$"

# The three unresolved-finding buckets a card can project into (or None = not a finding).
FindingKind = Literal["gap", "at_risk", "unpriced"]


class RemediationError(ValueError):
    """Raised on a fail-closed remediation prerequisite failure (PII-safe reason only).

    The message is a stable machine reason token (``no_completed_audit`` /
    ``audit_run_not_found`` / ``audit_report_unreadable`` / ``registry_drift``) — never
    an applicant value — so the CLI maps it to the frozen ``invalid_input`` refusal.
    """


# --------------------------------------------------------------------------- #
# Deterministic action templates — keyed by reason code, with a per-finding-kind
# fallback. Generic screening prose ONLY: parameterized by the factor id, carrying
# NO volatile CRS threshold (no CLB level, points value, cap, window, or date) so the
# no-inlined-volatile-rules gate stays clean and no requirement is synthesized here.
# --------------------------------------------------------------------------- #
_ACTION_TEMPLATES: dict[str, str] = {
    "missing_evidence": (
        "Obtain and import the required proof document for {factor}, then confirm "
        "each extracted field before re-running the audit."),
    "missing_eca": (
        "Obtain and import the required assessment document for {factor}, then "
        "confirm each extracted field before re-running the audit."),
    "not_audit_eligible": (
        "Confirm (or correct) the pending or low-quality evidence for {factor}; "
        "re-scan any rotated, low-text, or password-protected page so it passes the "
        "quality gate, then confirm each field."),
    "below_threshold": (
        "The confirmed evidence for {factor} does not meet the claimed level; obtain "
        "updated proof, or correct the claim to match the confirmed value."),
    "below_tier": (
        "The confirmed evidence for {factor} falls below the claimed tier; obtain "
        "updated proof, or correct the claim to match the confirmed value."),
    "unmet_component": (
        "One or more required components of {factor} are not substantiated; resolve "
        "the underlying core factors first, then re-run the audit."),
    "expired_test": (
        "The evidence for {factor} is outside its validity window; obtain a current "
        "document and confirm it before re-running the audit."),
    "expired_eca": (
        "The assessment for {factor} is outside its validity window; obtain a current "
        "assessment and confirm it before re-running the audit."),
    "expired_nomination": (
        "The nomination evidence for {factor} is outside its validity window; obtain "
        "a current document and confirm it before re-running the audit."),
    "unresolved_age": (
        "The date of birth for {factor} could not be resolved; import and confirm a "
        "clear identity document with an unambiguous date of birth."),
    "unresolved_conversion": (
        "The language scores for {factor} could not be converted to a benchmark; "
        "confirm the test type and each ability score, then re-run the audit."),
    "unresolved_noc": (
        "The occupation details for {factor} need review; this requires human or "
        "professional assessment of the job-duty fit and cannot be auto-substantiated."),
    "unresolved_nomination_expiry": (
        "The nomination validity for {factor} could not be resolved; confirm the "
        "expiry date on the nomination document."),
    "unresolved_sibling": (
        "Provide complete, in-scope sibling evidence for {factor} (relationship, "
        "status, residence, and age) and confirm each field."),
    "timing_unresolved": (
        "The relevant date for {factor} could not be resolved against the ITA round; "
        "confirm the round date and the supporting document date."),
    "unaccepted_test_type": (
        "The test type recorded for {factor} is not an accepted designated test; "
        "confirm the correct test type on the report, or obtain an accepted test."),
    "sibling_minor": (
        "The sibling evidence for {factor} indicates a minor; this factor cannot be "
        "substantiated on a minor sibling."),
    "arranged_employment_current": (
        "The claimed arranged-employment points for {factor} need review against the "
        "current policy; this requires human or professional assessment."),
    "arranged_employment_legacy_manual": (
        "The claimed legacy arranged-employment points for {factor} require manual, "
        "professional review of the transition-period policy."),
    "physician_policy_manual": (
        "The claimed physician public-policy arranged-employment case for {factor} "
        "requires manual, professional review; it is not an automatic points award."),
    "offer_for_eligibility_manual": (
        "The job offer for {factor} may support program eligibility but awards no CRS "
        "additional points; confirm program-eligibility use with a professional."),
    "unaudited_factor": (
        "{factor} is not yet supported by an automated decider; it requires human or "
        "professional review."),
    "at_risk_component": (
        "A component that {factor} depends on is at risk; resolve the underlying "
        "factor first, then re-run the audit."),
}

_DEFAULT_ACTION_BY_KIND: dict[str, str] = {
    "gap": (
        "Provide and confirm the required evidence for {factor}, then re-run the "
        "audit."),
    "at_risk": (
        "The evidence for {factor} needs human or professional review; resolve the "
        "underlying issue and re-confirm, then re-run the audit."),
    "unpriced": (
        "{factor} is substantiated, but its point value could not be grounded from the "
        "current rule registry; review the grounded rule and its corpus citation."),
}

# Reason-code aliases — a downstream reason token that REUSES an existing shipped
# action template rather than adding a duplicate entry to ``_ACTION_TEMPLATES``. The
# Phase-43 NOC duty-review sidecar (``crawler.noc_review``) emits the terminal
# ``duty_review_manual`` reason for its fully-confirmed-but-still-AT-RISK state, and
# the ``noc_source_unavailable`` reason when the index resolved the NOC but its
# authoritative corpus SOURCE is missing/drifted (WR-01); BOTH are exactly the
# "occupation details need review" remediation the shipped ``unresolved_noc``
# template (:data:`_ACTION_TEMPLATES`) already carries, so they alias to it — NO
# duplicate template, NO new volatile literal (the aliased prose stays the existing
# ``{factor}``-parameterized string, so the no-inlined-volatile-rules gate over this
# module stays clean).
_REASON_ALIASES: dict[str, str] = {
    "duty_review_manual": "unresolved_noc",
    "noc_source_unavailable": "unresolved_noc",
}


def _action_for(factor_id: str, reason_code: str | None, kind: str) -> str:
    """The deterministic action for a finding — keyed by reason, then finding kind."""
    # Resolve a reason alias FIRST (reuse a shipped template; never a duplicate).
    reason_code = _REASON_ALIASES.get(reason_code or "", reason_code)
    template = _ACTION_TEMPLATES.get(reason_code or "")
    if template is None:
        template = _DEFAULT_ACTION_BY_KIND[kind]
    return template.format(factor=factor_id)


# --------------------------------------------------------------------------- #
# Two-tier models — PII-BEARING private tier (vault-only) + PII-LIGHT public tier.
# --------------------------------------------------------------------------- #
class RemediationCitation(BaseModel):
    """A corpus citation id + its verbatim registry quote (already grounded)."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(pattern=_CITATION_ID_PATTERN)
    quote: str = Field(min_length=1)

    @field_validator("citation_id")
    @classmethod
    def _reject_evidence_id(cls, v: str) -> str:
        if v.startswith("ev_"):
            raise ValueError(
                "citation_id must be a corpus relpath#ordinal, never an ev_ id")
        return v


class PrivateRemediationItem(BaseModel):
    """One PII-BEARING remediation item (vault-only) — one per unresolved finding."""

    model_config = ConfigDict(extra="forbid")

    factor_id: str
    factor_group: FactorGroup | None = None
    verdict: Verdict
    reason_code: str | None = None
    finding_kind: FindingKind
    substantiated_points: int | None = None
    score_delta: int | None = None
    points_unresolved: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    citations: list[RemediationCitation] = Field(default_factory=list)
    action: str


class PrivateRemediationChecklist(BaseModel):
    """The full PII-BEARING remediation checklist — written ONLY under the vault."""

    model_config = ConfigDict(extra="forbid")

    source_audit_run_id: str
    candidate_id: str
    items: list[PrivateRemediationItem] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """Per-finding-kind + per-verdict counts (PII-light — plain ints)."""
        c = {"items": len(self.items), "gap": 0, "at_risk": 0, "unpriced": 0}
        for item in self.items:
            c[item.finding_kind] += 1
        return c


class PublicRemediationSummary(BaseModel):
    """PII-light stdout summary with a candidate-root-relative opaque locator.

    Despite its legacy name, ``private_output_path`` is interpreted relative to
    the already-selected candidate vault root and never contains a candidate id.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: RemediationRunId
    source_audit_run_id: AuditRunId
    item_count: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    private_output_path: str

    @model_validator(mode="after")
    def _exact_private_output_path(self) -> "PublicRemediationSummary":
        require_exact_output_locator(
            self.private_output_path, "remediation", f"{self.run_id}.json"
        )
        return self


# --------------------------------------------------------------------------- #
# Pure projection — build_remediation. NO id, NO timestamp, NO I/O (deterministic).
# --------------------------------------------------------------------------- #
def _finding_kind(card) -> "FindingKind | None":
    """The unresolved-finding bucket for a card, or None when it is not a finding."""
    if card.verdict == "GAP":
        return "gap"
    if card.verdict == "AT-RISK":
        return "at_risk"
    if card.verdict == "SUBSTANTIATED" and card.points_unresolved:
        return "unpriced"
    return None


def _quote_map(registry: Registry, factor_id: str) -> dict[str, str]:
    """Build ``{citation_id: verbatim quote}`` over the rows this factor consumes.

    Scopes to ``auditors.consumed_factor_ids(factor_id)`` — the SAME set the auditor's
    spine used to attach the card's ``rule_citation_ids`` — so every cited id has a
    quote (orphan-free on a same-registry run). A STATIC registry read; never a
    re-ground via searchindex/grounding.
    """
    wanted = set(auditors.consumed_factor_ids(factor_id))
    quotes: dict[str, str] = {}
    for row in registry.rows:
        if wanted.intersection(row.factor_ids):
            for citation in row.citations:
                quotes.setdefault(citation.chunk_id, citation.quote)
    return quotes


def build_remediation(report: PrivateAuditReport,
                      registry: Registry) -> PrivateRemediationChecklist:
    """Project a completed audit report into a remediation checklist (PURE).

    One :class:`PrivateRemediationItem` per unresolved finding (``GAP`` / ``AT-RISK`` /
    unpriced ``SUBSTANTIATED``), in card order. FAIL-CLOSED: if a card's
    ``rule_citation_id`` has no verbatim quote in the current registry (registry
    drift), raise :class:`RemediationError` rather than emit a line with a
    missing/invented quote. No minted id, no timestamp, no I/O — same inputs → same
    output.
    """
    items: list[PrivateRemediationItem] = []
    for card in report.factor_cards:
        kind = _finding_kind(card)
        if kind is None:
            continue
        quotes = _quote_map(registry, card.factor_id)
        citations: list[RemediationCitation] = []
        for citation_id in card.rule_citation_ids:
            quote = quotes.get(citation_id)
            if quote is None:
                # Registry drift: the audit cited a rule that the current registry no
                # longer grounds. Fail closed — never emit an ungrounded remediation line.
                raise RemediationError("registry_drift")
            citations.append(RemediationCitation(citation_id=citation_id, quote=quote))
        items.append(PrivateRemediationItem(
            factor_id=card.factor_id,
            factor_group=card.factor_group,
            verdict=card.verdict,
            reason_code=card.reason_code,
            finding_kind=kind,
            substantiated_points=card.substantiated_points,
            score_delta=card.score_delta,
            points_unresolved=card.points_unresolved,
            evidence_ids=list(card.evidence_ids),
            citations=citations,
            action=_action_for(card.factor_id, card.reason_code, kind),
        ))
    return PrivateRemediationChecklist(
        source_audit_run_id=report.run_id,
        candidate_id=report.candidate_id,
        items=items,
    )


def to_public_summary(checklist: PrivateRemediationChecklist,
                      private_output_path: str, *,
                      run_id: RemediationRunId) -> PublicRemediationSummary:
    """Down-project the checklist to the PII-LIGHT public summary (counts/ids only)."""
    return PublicRemediationSummary(
        run_id=run_id,
        source_audit_run_id=checklist.source_audit_run_id,
        item_count=len(checklist.items),
        counts=checklist.counts(),
        private_output_path=private_output_path,
    )


# --------------------------------------------------------------------------- #
# Vault-only render — PII-BEARING markdown carrying the substantiation-screening
# notice (the SAME framing as the audit report; never forked).
# --------------------------------------------------------------------------- #
def render_remediation_markdown(checklist: PrivateRemediationChecklist) -> str:
    """Render a human-readable, PII-BEARING remediation checklist (vault-only)."""
    lines: list[str] = [
        f"# CRS Remediation Checklist — from audit `{checklist.source_audit_run_id}`",
        "",
        f"- Candidate: `{checklist.candidate_id}`",
        f"- Unresolved findings: {len(checklist.items)}",
        "",
    ]
    for item in checklist.items:
        lines.extend([
            f"## `{item.factor_id}` — **{item.verdict}** ({item.finding_kind})",
            "",
            f"- Reason: `{item.reason_code}`",
            f"- Score impact (claimed − substantiated): {item.score_delta}",
            f"- Substantiated points: {item.substantiated_points}",
            f"- Evidence: {', '.join(item.evidence_ids) or '(none)'}",
            f"- **Action:** {item.action}",
        ])
        for citation in item.citations:
            lines.append(f"  - Grounded rule `{citation.citation_id}`: “{citation.quote}”")
        lines.append("")
    lines.append(SCREENING_NOTICE)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Vault writer — load a completed audit report, build, write vault-only, summarize.
# Fail-closed ordering: BUILD first; the vault writes happen only after a valid
# checklist exists (a prerequisite failure leaves zero artifacts).
# --------------------------------------------------------------------------- #
_REMEDIATION_SUBTREE = ("output", "remediation")


def _load_report(vault, audit_run_row: dict) -> PrivateAuditReport:
    """Load the stored PrivateAuditReport for a completed audit run (fail-closed).

    ``audit_runs.report_relpath`` is stored RELATIVE TO THE PERSONAL ROOT by
    ``audit_report._vault_relative`` (``candidates/<id>/output/crs-audit/<run_id>.json``),
    so it resolves under ``vault.root.parent.parent`` — the exact inverse of
    ``_vault_relative``; NOT under ``vault.root`` (which would double-count
    ``candidates/<id>``). A missing / unreadable / invalid report raises
    :class:`RemediationError` (PII-free reason token) — never a partial checklist.
    """
    relpath = audit_run_row.get("report_relpath")
    if not relpath:
        raise RemediationError("audit_report_unreadable")
    personal_root = vault.root.parent.parent
    try:
        report_path = paths.resolve_within(personal_root, *str(relpath).split("/"))
        text = report_path.read_text(encoding="utf-8")
        payload = json.loads(text)
        if "ita_round_id" in payload:
            return auditor.ProvenancedPrivateAuditReport.model_validate(payload)
        return PrivateAuditReport.model_validate(payload)
    except (OSError, ValueError) as exc:  # OSError=missing; ValueError=bad JSON/schema/PathEscape
        raise RemediationError("audit_report_unreadable") from exc


def _build_checklist_for_run(vault, audit_run_id: "str | None" = None, *,
                             registry: "Registry | None" = None
                             ) -> "tuple[PrivateRemediationChecklist, dict]":
    """Resolve a completed audit run, load its report, gate on drift, build the checklist.

    Shared by :func:`run_remediation` (which then writes) and
    ``review_packet.run_review_packet`` (which redacts + writes a packet) — ONE trust
    path, no duplication. Returns ``(checklist, run_row)``. Raises
    :class:`RemediationError` on any prerequisite failure (no completed audit / run not
    found / report unreadable / registry drift), leaving ZERO artifacts.
    """
    if audit_run_id is not None:
        run_row = vault_module.load_audit_run(vault, audit_run_id)
        if run_row is None or run_row.get("status") != "complete":
            raise RemediationError("audit_run_not_found")
    else:
        run_row = vault_module.latest_completed_audit_run(vault)
        if run_row is None:
            raise RemediationError("no_completed_audit")

    report = _load_report(vault, run_row)
    if registry is None:
        registry = crs_rules.load_registry()

    # Fail closed on registry drift: if the audit stamped a registry fingerprint and it
    # no longer matches the current registry, the re-derived verbatim quotes could be
    # spans the audit never grounded — refuse rather than present an unvetted span. A
    # legacy report (empty fingerprint) skips this gate and relies on the per-citation
    # drift check in build_remediation.
    if (report.registry_fingerprint
            and report.registry_fingerprint != crs_rules.registry_fingerprint(registry)):
        raise RemediationError("registry_drift")

    # BUILD (may raise RemediationError registry_drift for an orphan citation).
    checklist = build_remediation(report, registry)
    return checklist, run_row


def run_remediation(vault, audit_run_id: "str | None" = None, *,
                    registry: "Registry | None" = None
                    ) -> "tuple[PrivateRemediationChecklist, PublicRemediationSummary]":
    """Build a remediation checklist from a completed audit run + write it vault-only.

    Resolves the target run (``audit_run_id`` if given and ``complete``, else the
    latest completed run), loads its stored report, projects it via
    :func:`build_remediation`, writes the PII-bearing JSON + Markdown ONLY under
    ``candidates/<id>/output/remediation/<rem_id>.{json,md}`` (paths re-anchored via
    ``resolve_within``), and returns the checklist + a PII-light summary. Raises
    :class:`RemediationError` — leaving ZERO artifacts — on any prerequisite failure.
    """
    # Resolve + load + gate + build (shared helper) — before any write.
    checklist, _run_row = _build_checklist_for_run(
        vault, audit_run_id, registry=registry)

    rem_id = vault_module.new_remediation_id()
    out_dir = paths.resolve_within(vault.root, *_REMEDIATION_SUBTREE)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = paths.resolve_within(out_dir, f"{rem_id}.json")
    md_path = paths.resolve_within(out_dir, f"{rem_id}.md")
    json_path.write_text(
        json.dumps(checklist.model_dump(), ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_remediation_markdown(checklist), encoding="utf-8")

    report_relpath = _candidate_relative(
        vault, *_REMEDIATION_SUBTREE, f"{rem_id}.json"
    )
    summary = to_public_summary(checklist, report_relpath, run_id=rem_id)
    return checklist, summary
