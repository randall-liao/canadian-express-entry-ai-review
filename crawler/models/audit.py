"""Pydantic v2 boundary models for the Phase 32 CRS auditor (AUDIT-02 / AUDIT-06).

This is the typed CORE contract the whole Phase-32 vertical slice — and the Phase
33 fan-out — reuses: the four-value verdict vocabulary and the two-tier report
models that make the PII boundary a *structural* guarantee rather than a runtime
hope. It mirrors the two-tier discipline of ``crawler.models.vault``:

* **PII-LIGHT public tier** — :class:`PublicClaim`, :class:`FactorVerdict`,
  :class:`PublicAuditEnvelope`. These cross the ``--json`` stdout boundary. They
  carry corpus ``citation_id``s (``relpath#ordinal``), verdicts, counts, the run
  id, and an opaque candidate-root-relative private-output locator — NEVER an
  applicant value, candidate id, or ``ev_``
  vault evidence pointer. ``ConfigDict(extra="forbid")`` makes an injected
  applicant/evidence key a load-time failure, and a ``citation_id``
  ``field_validator`` rejects any ``ev_``-shaped id, so the corpus
  ``citation_id`` namespace stays strictly separate from the vault
  ``evidence_id`` namespace. **This tier is the AUDIT-06 public boundary and
  carries NO PII.**

* **PII-BEARING private tier** — :class:`PrivateFactorCard`,
  :class:`PrivateAuditReport`. These are the full evidence-bearing report written
  ONLY under the candidate vault (Plan 04). They carry claimed-vs-confirmed
  applicant values, ``ev_`` evidence pointers, the substantiated-points score
  delta, and the corpus rule citations behind each verdict. They may carry
  applicant values because they never leave the vault.

Design constraints (mirroring ``crawler.models.vault`` / ``crawler.models.crs_rules``):

* ``from __future__ import annotations`` + ``BaseModel`` + ``Literal`` enums so an
  out-of-vocabulary verdict/group is rejected AT THE BOUNDARY (pydantic
  ``ValidationError``) rather than silently persisted (fail-closed).
* ``ConfigDict(extra="forbid")`` on every model.
* :data:`FactorGroup` is IMPORTED from ``crawler.models.vault`` so the CRS
  grouping stays a single source of truth across the vault, the registry, and
  the auditor.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crawler.models.public_locator import AuditRunId, require_exact_output_locator
# Single source of truth for the four CRS factor groups (imported, never re-declared).
from crawler.models.vault import FactorGroup

# The corpus content coordinate shape ``relpath#ordinal`` (e.g.
# ``guidance/language-test.md#001``) — the SAME shape
# ``crawler.models.crs_rules._CHUNK_ID_PATTERN`` constrains a rule Citation to,
# and exactly what ``searchindex.resolve`` consumes. A public claim id that is
# not a resolvable corpus coordinate is rejected at construction.
_CITATION_ID_PATTERN = r"^[^#\s]+#\d+$"

# The four-value verdict vocabulary (SUMMARY-v4.0 §Verdict Semantics). A closed
# ``Literal`` so an out-of-vocabulary verdict is rejected at the boundary (SC1):
#   * SUBSTANTIATED — proof exists, is audit-eligible, meets the threshold, and
#     the rule is grounded + cited (the ONLY green verdict);
#   * GAP           — required proof is missing / below the claimed threshold;
#   * AT-RISK       — evidence is stale / expired / semantically unresolved;
#   * N/A           — the factor is not claimed / not applicable.
Verdict = Literal["SUBSTANTIATED", "GAP", "AT-RISK", "N/A"]


# --------------------------------------------------------------------------- #
# PII-LIGHT public tier — the AUDIT-06 ``--json`` boundary. Carries NO PII.
# --------------------------------------------------------------------------- #
class PublicClaim(BaseModel):
    """A PII-LIGHT grounded claim: a corpus ``citation_id`` + verdict, never PII.

    ``citation_id`` is shape-constrained to the corpus ``relpath#ordinal``
    coordinate and additionally rejected if it is ``ev_``-prefixed — the
    structural firewall making it impossible for a vault evidence id to reach a
    public claim (locked citation_id/evidence_id separation). ``extra="forbid"``
    means an injected ``raw_value`` / ``normalized_value`` / ``evidence_id`` key
    fails at load (SC4 by construction).
    """

    model_config = ConfigDict(extra="forbid")

    claim_text: str
    citation_id: str = Field(pattern=_CITATION_ID_PATTERN)
    verdict: Verdict

    @field_validator("citation_id")
    @classmethod
    def _reject_evidence_id(cls, v: str) -> str:
        """A ``citation_id`` is a corpus coordinate — NEVER an ``ev_`` evidence id."""
        if v.startswith("ev_"):
            raise ValueError(
                "citation_id must be a corpus relpath#ordinal, never an ev_ evidence id"
            )
        return v


class FactorVerdict(BaseModel):
    """A PII-LIGHT per-factor result: id/group/verdict/reason + a claim count.

    Carries NO applicant value and NO points — only a PII-free machine
    ``reason_code`` (e.g. ``"not_audit_eligible"``, ``"below_threshold"``,
    ``"grounded_substantiated"``) and how many corpus claims backed it.
    """

    model_config = ConfigDict(extra="forbid")

    factor_id: str
    factor_group: FactorGroup
    verdict: Verdict
    reason_code: str
    claim_count: int = 0


class PublicAuditEnvelope(BaseModel):
    """The PII-LIGHT payload emitted on the ``--json`` envelope ``result`` (AUDIT-06).

    Every field type here is a PII-light scalar / model, so ``extra="forbid"``
    makes an injected ``applicant_value`` / ``evidence_id`` / ``raw_text`` key a
    load-time failure. Despite its legacy name, ``private_output_path`` is an
    opaque locator interpreted relative to the selected candidate vault root,
    such as ``output/crs-audit/aud_deadbeef0001.json``. It never contains a
    candidate id or absolute path.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: AuditRunId
    factor_id: str
    verdicts: list[FactorVerdict] = Field(default_factory=list)
    claims: list[PublicClaim] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    private_output_path: str

    @model_validator(mode="after")
    def _exact_private_output_path(self) -> "PublicAuditEnvelope":
        require_exact_output_locator(
            self.private_output_path, "crs-audit", f"{self.run_id}.json"
        )
        return self


# --------------------------------------------------------------------------- #
# PII-BEARING private tier — the vault-ONLY evidence-bearing report. May carry
# applicant values + ev_ evidence pointers because it never leaves the vault.
# --------------------------------------------------------------------------- #
class PrivateFactorCard(BaseModel):
    """The AUDIT-04-shaped factor card the applicant sees — vault-ONLY (PII-bearing).

    Carries claimed-vs-confirmed applicant values, the substantiated points +
    ``score_delta`` (claimed − substantiated), the ``ev_`` vault evidence
    pointers (this is the ONE tier permitted to hold them), and the corpus
    ``rule_citation_ids`` (``relpath#ordinal``) behind the verdict. It may carry
    applicant values because it never leaves the vault. ``extra="forbid"`` still
    fails a malformed/typo'd key loudly at load.
    """

    model_config = ConfigDict(extra="forbid")

    factor_id: str
    factor_group: FactorGroup | None = None
    verdict: Verdict
    claimed_value: Any = None
    confirmed_value: Any = None
    substantiated_points: int | None = None
    score_delta: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    rule_citation_ids: list[str] = Field(default_factory=list)
    reason_code: str | None = None
    # True iff the verdict is SUBSTANTIATED but no grounded point value could be
    # computed (``substantiated_points is None``) — an explicit unresolved item
    # (COV-02), never a silent 0. Additive optional (default False so a bare card
    # loads cleanly); the auditor sets it at card assembly, the report renders it,
    # and ``to_public_envelope`` tallies it PII-light. The verdict stays narrowly
    # SUBSTANTIATED and ``substantiated_total`` is never inflated to hide the gap.
    points_unresolved: bool = False


class PrivateAuditReport(BaseModel):
    """The full evidence-bearing audit report — vault-ONLY (PII-bearing).

    One :class:`PrivateFactorCard` per audited factor (the Phase-32 slice has
    exactly one — ``core.language.first``; the Phase-33 fan-out adds more) plus
    the substantiated total and the arithmetic cutoff delta. Written ONLY under
    ``candidates/<id>/output/crs-audit/<run_id>.json`` (Plan 04) — never on
    stdout, never in a tracked/public path.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    candidate_id: str
    created_at: str = ""
    factor_cards: list[PrivateFactorCard] = Field(default_factory=list)
    substantiated_total: int | None = None
    cutoff_delta: int | None = None
    meets_cutoff: bool | None = None
    # Deterministic content fingerprint of the rule registry this audit grounded
    # against (crs_rules.registry_fingerprint). Additive optional (default "" so a
    # legacy report loads cleanly). A projection layer (remediation / review packet)
    # that re-derives verbatim rule spans from the CURRENT registry fails closed when
    # this no longer matches — so it can never present a span the audit never grounded.
    registry_fingerprint: str = ""


# --------------------------------------------------------------------------- #
# to_public_envelope — the SINGLE tested down-projection seam (SC4).
# --------------------------------------------------------------------------- #
def to_public_envelope(report: PrivateAuditReport,
                       private_output_path: str) -> PublicAuditEnvelope:
    """Down-project a PII-bearing report to a PII-LIGHT public envelope (SC4).

    This is the ONE tested seam that guarantees the public envelope is a strict
    PII-light SUBSET of the private report. It maps each :class:`PrivateFactorCard`
    to a :class:`FactorVerdict` (DROPPING claimed/confirmed values, points, and
    ``evidence_ids``) and to :class:`PublicClaim`\\ s built from ONLY the
    ``rule_citation_ids`` (corpus) — NEVER the ``evidence_ids`` (vault). Because
    the public models are ``extra="forbid"`` and cannot hold an applicant value
    or an ``ev_`` id, the resulting ``model_dump()`` carries no PII by
    construction.

    ``private_output_path`` is an opaque locator relative to the selected candidate
    vault root; the guard rejects candidate ids, traversal, URIs, and absolute paths.
    """
    verdicts: list[FactorVerdict] = []
    claims: list[PublicClaim] = []
    counts = {
        "factors": len(report.factor_cards),
        "substantiated": 0,
        "gap": 0,
        "at_risk": 0,
        "na": 0,
    }
    _bucket = {
        "SUBSTANTIATED": "substantiated",
        "GAP": "gap",
        "AT-RISK": "at_risk",
        "N/A": "na",
    }
    for card in report.factor_cards:
        verdicts.append(FactorVerdict(
            factor_id=card.factor_id,
            factor_group=card.factor_group or "core_human_capital",
            verdict=card.verdict,
            reason_code=card.reason_code or _bucket[card.verdict],
            claim_count=len(card.rule_citation_ids),
        ))
        counts[_bucket[card.verdict]] += 1
        # Claims are built from CORPUS citations ONLY — never evidence_ids.
        for citation_id in card.rule_citation_ids:
            claims.append(PublicClaim(
                claim_text=f"{card.factor_id}: grounded corpus rule",
                citation_id=citation_id,
                verdict=card.verdict,
            ))
    counts["grounded_claims"] = len(claims)
    # COV-02 additive tally: SUBSTANTIATED cards that could NOT be priced from a
    # grounded row (``substantiated_points is None``). Derived from the intrinsic
    # verdict/points ground truth (equivalently ``card.points_unresolved`` once the
    # auditor has set it) so the public surfacing cannot be fooled into hiding an
    # unpriced factor. ``counts`` is ``dict[str, int]`` — this is a pure key
    # addition (a plain int), so ``PublicAuditEnvelope`` keeps its ``extra="forbid"``
    # schema and carries no PII.
    counts["unpriced"] = sum(
        1 for card in report.factor_cards
        if card.verdict == "SUBSTANTIATED" and card.substantiated_points is None)
    factor_id = report.factor_cards[0].factor_id if report.factor_cards else ""
    return PublicAuditEnvelope(
        run_id=report.run_id,
        factor_id=factor_id,
        verdicts=verdicts,
        claims=claims,
        counts=counts,
        private_output_path=private_output_path,
    )


if __name__ == "__main__":  # pragma: no cover
    # Import smoke check on a lean install (no new deps).
    PublicAuditEnvelope(
        run_id="aud_deadbeef0001", factor_id="core.language.first",
        private_output_path="output/crs-audit/aud_deadbeef0001.json",
    )
