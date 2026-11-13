"""Redacted professional review packet — a closed-allowlist projection (Phase 38).

The applicant can produce an opt-in, explicitly redacted lawyer/RCIC review packet from
a completed audit's remediation checklist. The packet is a FURTHER-redacted PROJECTION
of already-grounded data — never a re-score, re-ground, or second trust path:

* :class:`PacketFinding` is a CLOSED ALLOWLIST (``extra="forbid"``) admitting ONLY the
  PII-free fields a professional needs: factor id, verdict + reason, score impact,
  finding kind, the resolvable authoritative corpus citations (id + verbatim quote),
  and the deterministic action. It structurally CANNOT carry a raw applicant value, an
  ``ev_`` evidence id, or an absolute path (no field for them; ``extra="forbid"``; a
  ``citation_id`` validator rejects ``ev_``).
* :func:`build_packet` projects a Phase-37 :class:`~crawler.remediation.PrivateRemediationChecklist`,
  DROPPING the ``ev_`` evidence pointers, and records the redaction in a
  :class:`RedactionManifest`. It is PURE (no id/timestamp/IO).
* :func:`run_review_packet` (Plans 38-02/03) reuses ``remediation._build_checklist_for_run``
  (one trust path), renders the packet, SCANS the rendered bytes for abs-path/``ev_``/
  secret leaks BEFORE any write (render-then-scan), and writes ONLY under the vault.

Every rendered packet carries the same substantiation-screening notice as the audit
report (no approval / eligibility ruling / outcome prediction). Pure stdlib + pydantic
v2 — zero new runtime dependency.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crawler import paths, remediation
from crawler import vault as vault_module
from crawler.audit_report import SCREENING_NOTICE
from crawler.models.audit import Verdict
from crawler.models.public_locator import (
    AuditRunId,
    PacketRunId,
    require_exact_output_locator,
)
from crawler.remediation import PrivateRemediationChecklist, RemediationError

# Corpus content coordinate shape ``relpath#ordinal`` (same as the audit/remediation).
_CITATION_ID_PATTERN = r"^[^#\s]+#\d+$"

FindingKind = Literal["gap", "at_risk", "unpriced"]

# The vault subtree the packet artifacts land in (publish-safe covered).
_PACKET_SUBTREE = ("output", "review-packet")


# --------------------------------------------------------------------------- #
# Closed-allowlist packet models — the structural PII firewall (PKT-02).
# --------------------------------------------------------------------------- #
class PacketCitation(BaseModel):
    """A resolvable authoritative corpus citation — id + verbatim quote (never ev_)."""

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


class PacketFinding(BaseModel):
    """One redacted finding — a CLOSED ALLOWLIST of PII-free fields ONLY.

    Structurally cannot carry a raw applicant value, an ``ev_`` id, or an absolute
    path: there is no field for them, ``extra="forbid"`` rejects an injected key, and
    ``citations`` reject ``ev_`` ids. ``score_impact``/``substantiated_points`` are
    derived CRS numbers (not identifying PII) and live only in the vault packet.
    """

    model_config = ConfigDict(extra="forbid")

    factor_id: str
    verdict: Verdict
    reason_code: str | None = None
    finding_kind: FindingKind
    score_impact: int | None = None
    substantiated_points: int | None = None
    citations: list[PacketCitation] = Field(default_factory=list)
    action: str


class IncludedDocument(BaseModel):
    """An explicitly opted-in document — recorded by DOCUMENT ID ONLY (no path/bytes)."""

    model_config = ConfigDict(extra="forbid")

    document_id: str


class RedactionManifest(BaseModel):
    """The auditable record of what was included, excluded, and redacted (PKT-04)."""

    model_config = ConfigDict(extra="forbid")

    findings_total: int = 0
    findings_included: int = 0
    findings_excluded: int = 0
    redacted_fields: list[str] = Field(default_factory=list)
    documents_excluded: int = 0
    documents_included: list[IncludedDocument] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "findings_total": self.findings_total,
            "findings_included": self.findings_included,
            "findings_excluded": self.findings_excluded,
            "documents_excluded": self.documents_excluded,
            "documents_included": len(self.documents_included),
        }


class ReviewPacket(BaseModel):
    """The redacted review packet — vault-only, carries NO candidate id / ev_ / bytes."""

    model_config = ConfigDict(extra="forbid")

    source_audit_run_id: str
    findings: list[PacketFinding] = Field(default_factory=list)
    manifest: RedactionManifest
    screening_notice: str = SCREENING_NOTICE


class PublicPacketSummary(BaseModel):
    """PII-light stdout summary with a candidate-root-relative opaque locator.

    ``private_output_path`` is interpreted relative to the already-selected
    candidate vault root and never contains a candidate id.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: PacketRunId | None = None
    source_audit_run_id: AuditRunId
    findings_included: int = 0
    documents_included: int = 0
    manifest_counts: dict[str, int] = Field(default_factory=dict)
    private_output_path: str | None

    @model_validator(mode="after")
    def _exact_private_output_path(self) -> "PublicPacketSummary":
        if self.run_id is None:
            if self.private_output_path is not None:
                raise ValueError("dry-run private_output_path must be None")
            return self
        if self.private_output_path is None:
            raise ValueError("written packet requires private_output_path")
        require_exact_output_locator(
            self.private_output_path, "review-packet", f"{self.run_id}.json"
        )
        return self


# --------------------------------------------------------------------------- #
# Pure projection — build_packet. NO id/timestamp/IO (deterministic).
# --------------------------------------------------------------------------- #
def build_packet(checklist: PrivateRemediationChecklist,
                 selection: "set[str] | None" = None, *,
                 documents_excluded: int = 0,
                 documents_included: "list[IncludedDocument] | None" = None
                 ) -> "tuple[ReviewPacket, RedactionManifest]":
    """Project a remediation checklist into a redacted review packet (PURE).

    ``selection`` is a set of factor ids to include (None/empty = all). Each selected
    item becomes a :class:`PacketFinding`, DROPPING ``evidence_ids`` (``ev_``). The
    ``documents_excluded`` / ``documents_included`` counts are supplied by the caller
    (``run_review_packet``, which has the vault) — ``build_packet`` performs no vault
    access. No id, no timestamp, no I/O — same inputs → same output.
    """
    docs_included = documents_included or []
    selected = [
        item for item in checklist.items
        if not selection or item.factor_id in selection]
    findings: list[PacketFinding] = []
    for item in selected:
        findings.append(PacketFinding(
            factor_id=item.factor_id,
            verdict=item.verdict,
            reason_code=item.reason_code,
            finding_kind=item.finding_kind,
            score_impact=item.score_delta,
            substantiated_points=item.substantiated_points,
            citations=[PacketCitation(citation_id=c.citation_id, quote=c.quote)
                       for c in item.citations],
            action=item.action,
        ))
    manifest = RedactionManifest(
        findings_total=len(checklist.items),
        findings_included=len(findings),
        findings_excluded=len(checklist.items) - len(findings),
        redacted_fields=["evidence_ids"],
        documents_excluded=documents_excluded,
        documents_included=list(docs_included),
    )
    packet = ReviewPacket(
        source_audit_run_id=checklist.source_audit_run_id,
        findings=findings,
        manifest=manifest,
        screening_notice=SCREENING_NOTICE,
    )
    return packet, manifest


def render_packet_markdown(packet: ReviewPacket) -> str:
    """Render a human-readable, professionally-framed review packet (vault-only).

    Presents each finding + score impact + resolvable citations, then the verbatim
    ``SCREENING_NOTICE``. The findings body carries NO approval / eligibility /
    outcome-prediction claim (the notice's negated disclaimer stays intact).
    """
    lines: list[str] = [
        "# CRS Substantiation — Professional Review Packet",
        "",
        f"- Source audit: `{packet.source_audit_run_id}`",
        f"- Findings included: {packet.manifest.findings_included} "
        f"of {packet.manifest.findings_total}",
        f"- Documents included: {len(packet.manifest.documents_included)} "
        f"(excluded by default: {packet.manifest.documents_excluded})",
        "",
    ]
    for finding in packet.findings:
        lines.extend([
            f"## `{finding.factor_id}` — **{finding.verdict}** ({finding.finding_kind})",
            "",
            f"- Reason: `{finding.reason_code}`",
            f"- Score impact (claimed − substantiated): {finding.score_impact}",
            f"- Substantiated points: {finding.substantiated_points}",
            f"- Suggested next step: {finding.action}",
        ])
        for citation in finding.citations:
            lines.append(
                f"  - Authoritative rule `{citation.citation_id}`: “{citation.quote}”")
        lines.append("")
    lines.append(SCREENING_NOTICE)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Render-then-scan double gate (PKT-04) — a self-contained deny-pattern scan over the
# RENDERED packet bytes, BEFORE any write. Mirrors scripts/check_publish_safe.py shapes
# (scripts is NOT an importable package, so the patterns are duplicated here on
# purpose). A hit refuses fail-closed; the structural allowlist is the first line, this
# is belt-and-suspenders on the free-text (quote/action) fields.
# --------------------------------------------------------------------------- #
_LEAK_PATTERNS: tuple[re.Pattern, ...] = (
    # Patterns are assembled from fragments so this source file does not itself trip
    # the publish-safe abs-path scanner (the same self-reference trick check_publish_safe
    # uses for its ALLOW_MARKER). They still match the literal paths at runtime.
    re.compile(r"(?i)/" "home" r"/[^/\s'\"]"),
    re.compile(r"(?i)/" "Users" r"/[^/\s'\"]"),
    re.compile(r"(?i)/" "root" r"/"),
    re.compile("pr-" "ai-venv"),
    re.compile(r"/usr/" "bin" r"/python3(?:\.\d+)?"),
    re.compile(r"[A-Za-z]:\\\\"),                     # Windows drive path
    re.compile(r"\bev_[0-9a-f]{6,}\b"),               # vault evidence id shape
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"github_" "pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}"),
    # Generic assigned-credential (key looks like a secret field; value >= 12 chars).
    re.compile(
        r"(?i)(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?key|token|password)"
        r"\s*[:=]\s*['\"]?[^'\"\s]{12,}"),
)


def _scan_rendered_bytes(text: str) -> list[str]:
    """Return the list of leak-pattern names found in *text* (``[]`` == clean)."""
    hits: list[str] = []
    for pattern in _LEAK_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def run_review_packet(vault, audit_run_id: "str | None" = None, *,
                      selection: "set[str] | None" = None,
                      include_documents: "list[str] | None" = None,
                      dry_run: bool = False,
                      registry=None
                      ) -> "tuple[ReviewPacket, PublicPacketSummary]":
    """Build a redacted review packet from a completed audit run (fail-closed).

    Reuses ``remediation._build_checklist_for_run`` (one trust path), projects the
    allowlisted packet, records the redaction, and — on a real (non ``dry_run``) run —
    RENDERS + SCANS the bytes for abs-path/``ev_``/secret leaks BEFORE writing anything
    ONLY under ``candidates/<id>/output/review-packet/`` via ``resolve_within``.

    ``dry_run`` builds + returns the packet/summary but writes NOTHING. Any
    prerequisite / leak / unknown-document failure raises
    :class:`~crawler.remediation.RemediationError` (the class the CLI maps to a clean
    ``invalid_input``/exit-2 refusal), leaving ZERO artifacts.
    """
    checklist, _run_row = remediation._build_checklist_for_run(
        vault, audit_run_id, registry=registry)

    # Per-document opt-in (default: none included; every candidate doc excluded).
    # De-dupe the requested ids (order-preserving) so a repeated --include-document can
    # never double-count / drive documents_excluded negative (WR-02).
    docs = vault_module.list_candidate_documents(vault, vault.candidate_id)
    requested: list[str] = []
    for doc_id in (include_documents or []):
        if doc_id not in requested:
            requested.append(doc_id)
    included: list[IncludedDocument] = []
    # Resolve AND READ every included document's bytes NOW — before any write — so a
    # missing/unreadable backing file fails closed (RemediationError) leaving ZERO
    # artifacts, never a partial packet or an abs-path leak on stdout (CR-01).
    staged_bytes: list[tuple[str, str, bytes]] = []  # (document_id, ext, data)
    for doc_id in requested:
        row = vault_module.get_candidate_document(vault, vault.candidate_id, doc_id)
        if row is None:
            raise RemediationError("unknown_document")
        try:
            src = paths.resolve_within(vault.root, *row["storage_relpath"].split("/"))
            data = src.read_bytes()
        except (OSError, paths.PathEscapeError) as exc:
            raise RemediationError("document_unreadable") from exc
        ext = "".join(src.suffixes) or ".bin"
        staged_bytes.append((doc_id, ext, data))
        included.append(IncludedDocument(document_id=doc_id))

    packet, _manifest = build_packet(
        checklist, selection,
        documents_excluded=len(docs) - len(included),
        documents_included=included)

    if dry_run:
        summary = PublicPacketSummary(
            run_id=None,
            source_audit_run_id=packet.source_audit_run_id,
            findings_included=packet.manifest.findings_included,
            documents_included=len(included),
            manifest_counts=packet.manifest.counts(),
            private_output_path=None)
        return packet, summary

    # RENDER-THEN-SCAN: scan the rendered bytes BEFORE any write (zero artifacts on hit).
    packet_json = json.dumps(packet.model_dump(), ensure_ascii=False)
    packet_md = render_packet_markdown(packet)
    if _scan_rendered_bytes(packet_json) or _scan_rendered_bytes(packet_md):
        raise RemediationError("rendered_leak")

    pkt_id = vault_module.new_packet_id()
    out_dir = paths.resolve_within(vault.root, *_PACKET_SUBTREE)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths.resolve_within(out_dir, f"{pkt_id}.json").write_text(
        packet_json, encoding="utf-8")
    paths.resolve_within(out_dir, f"{pkt_id}.md").write_text(
        packet_md, encoding="utf-8")

    # Stage the PRE-READ opted-in document bytes ONLY under the vault packet subtree
    # (never published; every path re-anchored via resolve_within).
    for document_id, ext, data in staged_bytes:
        dest = paths.resolve_within(
            out_dir, pkt_id, "documents", f"{document_id}{ext}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    report_relpath = remediation._candidate_relative(
        vault, *_PACKET_SUBTREE, f"{pkt_id}.json")
    summary = PublicPacketSummary(
        run_id=pkt_id,
        source_audit_run_id=packet.source_audit_run_id,
        findings_included=packet.manifest.findings_included,
        documents_included=len(included),
        manifest_counts=packet.manifest.counts(),
        private_output_path=report_relpath)
    return packet, summary
