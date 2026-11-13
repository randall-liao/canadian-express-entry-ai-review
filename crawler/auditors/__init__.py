"""The factor→decider dispatch contract (Phase 33 — AUDIT-01/03).

This package is the shared *dispatch spine* that fans the proven Phase-32 verdict
contract out across the whole CRS grid. It defines the interface every auditor
module (core / spouse / transferability / additional) plugs into — WITHOUT
inventing a new trust path:

* :class:`DecisionContext` — the read-only bundle the generic spine
  (``crawler.auditor.audit_one``) hands a decider: only what the spine already
  gathered (the claimed factor, the audit-eligible confirmed values keyed by
  field, the grounded registry + the gated consumed subset, spouse mode, the
  freshness reference date, and the cards decided earlier this run so
  transferability can read substantiated core values).
* :class:`DecisionResult` — the PII-bearing verdict a decider returns (verdict +
  reason + claimed/confirmed values + substantiated points). Evidence ids and
  rule citation ids are attached by the SPINE, never the decider.
* :data:`register` / :func:`resolve` — the module-level registry; an unregistered
  factor resolves to :func:`_default_decider`, a CONSERVATIVE fail-closed
  ``AT-RISK`` (an unwired factor can NEVER be ``SUBSTANTIATED`` — T-33-04).
* :data:`FULL_GRID_FACTORS` — the canonical auditable factor id list across the
  four groups (derived from the ``crs_rules.REQUIRED_RULE_IDS`` stems; cap-only
  and conversion rows are CONSUMED by deciders, never audited as factors).

NO volatile CRS threshold (CLB level, points, cap, window, date) may appear in
this package — every number is read from a grounded registry row via
``crawler.crs_audit``. The static ``no_inlined_volatile_rules`` gate covers
``crawler/auditors/`` (a self-scan test asserts it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from crawler.models.audit import PrivateFactorCard, Verdict
from crawler.models.crs_rules import Registry
from crawler.models.vault import CrsProfileFactor, ExtractedValue, FactorGroup

# The conversion factor whose grounded rows the language-family deciders consume
# (raw score → CLB/NCLC level). Kept here so both the spine's
# ``consumed_factor_ids`` and the core/additional modules agree on ONE id.
CONVERSION_FACTOR = "core.language.conversion"


# --------------------------------------------------------------------------- #
# DecisionContext / DecisionResult — the read-only bundle + the verdict.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DecisionContext:
    """Everything a decider may read — and NOTHING it should not (read-only)."""

    factor_id: str
    factor: CrsProfileFactor | None
    by_field: dict[str, ExtractedValue]
    registry: Registry
    consumed: Registry
    spouse_mode: bool
    reference_date: str
    ita_date: str | None = None
    prior_cards: dict[str, PrivateFactorCard] = field(default_factory=dict)
    # The raw audit-eligible values (NOT collapsed by field name) so a decider
    # that needs multiple values of the SAME field across documents — e.g. work
    # aggregation over several employment letters — can group them per document.
    eligible_values: tuple[ExtractedValue, ...] = ()


@dataclass
class DecisionResult:
    """The PII-bearing verdict a decider returns.

    Evidence ids (``ev_``) and rule citation ids (corpus ``relpath#ordinal``) are
    attached by the SPINE from the gated consumed subset — never by the decider —
    so the ``citation_id`` / ``evidence_id`` separation stays a structural
    property of the spine (T-33-02).
    """

    verdict: Verdict
    reason_code: str
    claimed_value: Any = None
    confirmed_value: Any = None
    substantiated_points: int | None = None
    # Optional reason-aware citation scoping (WR-02). The specific CONSUMED
    # rule ids this verdict derives from. Empty / ``None`` (the default) →
    # the spine attaches the historical UNION of ALL consumed rows' citations
    # (byte-identical behavior for every factor that never sets it). A NON-EMPTY
    # value → the spine attaches ONLY those named rows' citations, so a verdict on
    # a SHARED factor (e.g. a non-physician job-offer card) does not over-cite the
    # sibling rows it did not derive from. The ENTIRE consumed subset is still
    # grounding-gated upstream (fail-closed) — this narrows only what a card
    # SURFACES, never what is gated. An unknown id matches no consumed row (the
    # card is safely left with no citation), never an error.
    rule_ids: tuple[str, ...] | None = None


Decider = Callable[["DecisionContext"], "DecisionResult"]


# --------------------------------------------------------------------------- #
# The registry — register / resolve + the conservative fail-closed default.
# --------------------------------------------------------------------------- #
_REGISTRY: dict[str, Decider] = {}


def register(factor_id: str, fn: Decider) -> None:
    """Register *fn* as the decider for *factor_id* (last registration wins)."""
    _REGISTRY[factor_id] = fn


def resolve(factor_id: str) -> Decider:
    """Return the decider for *factor_id*, or the conservative default (AT-RISK)."""
    return _REGISTRY.get(factor_id, _default_decider)


def _default_decider(ctx: DecisionContext) -> DecisionResult:
    """The fail-closed default: an unregistered factor is AT-RISK, never green.

    Guarantees an unwired factor can NEVER reach ``SUBSTANTIATED`` (T-33-04) — the
    conservative elevation-of-privilege mitigation.
    """
    return DecisionResult(verdict="AT-RISK", reason_code="unaudited_factor")


# --------------------------------------------------------------------------- #
# FULL_GRID_FACTORS / FACTOR_GROUP — the canonical auditable factor id grid.
#
# Derived from the crs_rules.REQUIRED_RULE_IDS stems. Cap-only rule stems
# (transfer.cap.*) and conversion rows (core.language.conversion) are NOT audited
# factors — they are CONSUMED by deciders. The job-offer legacy/current split
# (additional.job_offer.current/.legacy) is one audited factor: additional.job_offer.
# --------------------------------------------------------------------------- #
FULL_GRID_FACTORS: tuple[str, ...] = (
    # core human capital
    "core.age",
    "core.education",
    "core.language.first",
    "core.language.second",
    "core.work",
    # spouse / common-law
    "spouse.education",
    "spouse.language",
    "spouse.work",
    # skill transferability (recombine already-substantiated core values)
    "transfer.education_language",
    "transfer.education_work",
    "transfer.foreign_language",
    "transfer.foreign_work",
    "transfer.certificate_language",
    # additional points
    "additional.nomination",
    "additional.job_offer",
    "additional.study",
    "additional.french",
    "additional.sibling",
)


def _group_for(factor_id: str) -> FactorGroup:
    """Map a grid factor id to its FactorGroup by structural prefix."""
    if factor_id.startswith("spouse."):
        return "spouse_common_law"
    if factor_id.startswith("transfer."):
        return "skill_transferability"
    if factor_id.startswith("additional."):
        return "additional_points"
    return "core_human_capital"


FACTOR_GROUP: dict[str, FactorGroup] = {
    fid: _group_for(fid) for fid in FULL_GRID_FACTORS
}

# The language family: factors whose deciders consume the CLB/NCLC conversion
# rows (first + second official language, and strong-French additional points).
_LANGUAGE_FAMILY: frozenset[str] = frozenset({
    "core.language.first",
    "core.language.second",
    "additional.french",
})

# Factors that are DERIVED (recombined from already-substantiated core cards) and
# therefore run their decider even when the profile carries no explicit claim.
_DERIVED_PREFIXES: tuple[str, ...] = ("transfer.",)


def is_derived(factor_id: str) -> bool:
    """True iff *factor_id* is a derived combination (audited without a claim)."""
    return factor_id.startswith(_DERIVED_PREFIXES)


def consumed_factor_ids(factor_id: str) -> list[str]:
    """The extra rule ``factor_ids`` a factor's grounding subset must include.

    A language-family factor also consumes the conversion rows (so ``to_clb`` has
    grounded bands and the gate re-checks them); every other factor's own id
    suffices (transferability rows already tag their component core factor ids).
    """
    if factor_id in _LANGUAGE_FAMILY:
        return [factor_id, CONVERSION_FACTOR]
    return [factor_id]


# --------------------------------------------------------------------------- #
# load_all — importing the package registers every decider (idempotent).
# --------------------------------------------------------------------------- #
_LOADED = False


def load_all() -> None:
    """Import every auditor module so its deciders self-register (idempotent)."""
    global _LOADED
    if _LOADED:
        return
    # Import for side effects (each module calls register at import time).
    from crawler.auditors import (  # noqa: F401  (registration side effects)
        additional,
        core,
        spouse,
        transferability,
    )
    _LOADED = True
