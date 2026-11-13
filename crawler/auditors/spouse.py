"""Spouse / common-law auditor module (Phase 33 — 33-03, AUDIT-01/03).

The second of the four context-light modules. It fans the proven verdict contract
out to the three spouse factors — spouse education, spouse language, spouse
Canadian work — WITHOUT a new trust path:

* :func:`determine_spouse_mode` reads an EXPLICIT ``spouse.accompanying`` profile
  signal (not the mere presence of spouse evidence, which stray evidence could
  flip — T-33-09). Spouse factors are scored ONLY when an accompanying
  spouse / common-law partner who is NOT a Canadian citizen / PR is declared;
  otherwise the spine short-circuits every ``spouse.*`` factor to N/A.
* The three deciders score under ``ctx.spouse_mode`` and read ONLY
  ``ctx.by_field`` — which the spine has already restricted to the spouse
  factor's audit-eligible values. Ownership separation is therefore STRUCTURAL:
  a principal-owned value (linked to a ``core.*`` factor) is never visible to a
  spouse decider, so it can never substantiate a spouse factor (T-33-08 / SC5).

Every band / level / cap is READ from a grounded row (the shared core helpers +
``crs_audit``); this module carries NO inlined volatile threshold (a self-scan
``no_inlined_volatile_rules`` test asserts it).
"""

from __future__ import annotations

from crawler import crs_audit
from crawler.auditors import DecisionContext, DecisionResult, register
from crawler.auditors.core import (
    _claimed_years,
    _confirmed_snapshot,
    _decide_language,
    _effective_value,
    _grounded_points,
)
from crawler.models.crs_rules import Registry

# The explicit profile signal that turns spouse mode ON (documented here + in the
# portable spec). Its ``claimed_value`` is truthy iff an accompanying spouse /
# common-law partner who is NOT a Canadian citizen or PR is declared.
_ACCOMPANYING_SIGNAL = "spouse.accompanying"

_SPOUSE_WORK_FIELDS = ("employment_start", "employment_end", "hours_per_week", "teer")


def determine_spouse_mode(vault, profile_factors) -> bool:
    """True iff the profile declares an accompanying non-citizen/PR spouse.

    Reads the explicit ``spouse.accompanying`` profile factor (truthy
    ``claimed_value``). Absent or falsy → False (no-spouse mode). Does NOT infer
    spouse mode from the presence of spouse evidence — that would let stray
    evidence flip the mode (T-33-09).
    """
    for factor in profile_factors:
        if factor.factor_id == _ACCOMPANYING_SIGNAL and factor.claimed_value:
            return True
    return False


def _section_cap(registry: Registry, field: str) -> int | None:
    """Read a grounded per-section cap value (e.g. the spouse-language cap)."""
    for row in registry.rows:
        mc = row.machine_check
        if mc.kind == "cap" and mc.field == field and mc.cap_value is not None:
            return mc.cap_value
    return None


# --------------------------------------------------------------------------- #
# decide_spouse_education — spouse-owned credential (+ in-window ECA) → points.
# --------------------------------------------------------------------------- #
def decide_spouse_education(ctx: DecisionContext) -> DecisionResult:
    """Spouse education points from the grounded spouse education table (spouse mode).

    Reads only spouse-owned confirmed evidence (spine-restricted to
    ``spouse.education``). Missing credential → GAP; a foreign credential with a
    missing / expired ECA → AT-RISK; a level outside the grounded spouse table →
    GAP; otherwise SUBSTANTIATED with the grounded spouse-column points.
    """
    confirmed = _confirmed_snapshot(ctx.by_field)
    claimed = ctx.factor.claimed_level if ctx.factor is not None else None
    level_value = ctx.by_field.get("credential_level")
    if level_value is None:
        return DecisionResult("GAP", "missing_evidence",
                              claimed_value=claimed, confirmed_value=confirmed)
    level = _effective_value(level_value)

    eca_date_value = ctx.by_field.get("eca_report_date")
    eca_org_value = ctx.by_field.get("eca_organization")
    if eca_org_value is not None and eca_date_value is None:
        return DecisionResult("AT-RISK", "missing_eca",
                              claimed_value=claimed, confirmed_value=confirmed)
    if eca_date_value is not None:
        eca_date = str(_effective_value(eca_date_value))[:10]
        if not crs_audit.within_validity("eca", eca_date, ctx.reference_date,
                                         ctx.registry):
            return DecisionResult("AT-RISK", "expired_eca",
                                  claimed_value=claimed, confirmed_value=confirmed)

    points = _grounded_points(ctx.registry, "spouse.education", level,
                              spouse_mode=True)
    if points is None:
        return DecisionResult("GAP", "below_threshold",
                              claimed_value=claimed, confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          claimed_value=claimed, confirmed_value=confirmed,
                          substantiated_points=points)


# --------------------------------------------------------------------------- #
# decide_spouse_language — spouse-owned language → per-ability points, cap-clamped.
# --------------------------------------------------------------------------- #
def decide_spouse_language(ctx: DecisionContext) -> DecisionResult:
    """Spouse language points via the grounded conversion + spouse points table.

    Reuses the frozen conversion + validity + per-ability decision path (byte-for-
    byte reason codes) scoring under the spouse points table, then clamps the
    section total to the grounded spouse-language section cap. Missing spouse-owned
    evidence → GAP; unresolved conversion → AT-RISK; below the claim → GAP.
    """
    result = _decide_language(ctx, "spouse.language")
    if result.substantiated_points is not None:
        cap = _section_cap(ctx.registry, "spouse_language_section")
        if cap is not None:
            result.substantiated_points = min(result.substantiated_points, cap)
    return result


# --------------------------------------------------------------------------- #
# decide_spouse_work — spouse-owned Canadian work aggregation (no double-count).
# --------------------------------------------------------------------------- #
def decide_spouse_work(ctx: DecisionContext) -> DecisionResult:
    """Aggregate spouse-owned Canadian work via ``aggregate_work``; below claim → GAP.

    Only spouse-owned values reach here (spine-restricted to ``spouse.work``), so
    a principal's work can never substantiate the spouse factor (ownership
    separation).
    """
    confirmed = _confirmed_snapshot(ctx.by_field)
    claimed_years = _claimed_years(ctx.factor)

    per_doc: dict[str, dict] = {}
    for value in ctx.eligible_values:
        if value.field_name in _SPOUSE_WORK_FIELDS:
            per_doc.setdefault(value.document_id, {})[value.field_name] = (
                _effective_value(value))

    periods: list[dict] = []
    missing_teer = False
    for fields in per_doc.values():
        if "employment_start" not in fields or "employment_end" not in fields:
            continue
        if "teer" not in fields:
            missing_teer = True
        periods.append({
            "start": fields["employment_start"],
            "end": fields["employment_end"],
            "hours_per_week": fields.get("hours_per_week"),
            "teer": fields.get("teer"),
        })

    if not periods:
        return DecisionResult("GAP", "missing_evidence",
                              claimed_value=claimed_years, confirmed_value=confirmed)
    if missing_teer:
        return DecisionResult("AT-RISK", "unresolved_noc",
                              claimed_value=claimed_years, confirmed_value=confirmed)

    aggregate = crs_audit.aggregate_work(periods, ctx.registry)
    years = aggregate["years"]
    confirmed["aggregated_years"] = round(years, 4)
    confirmed["period_count"] = len(periods)
    if claimed_years is not None and years + 0.01 < claimed_years:
        return DecisionResult("GAP", "below_threshold",
                              claimed_value=claimed_years, confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          claimed_value=claimed_years, confirmed_value=confirmed)


register("spouse.education", decide_spouse_education)
register("spouse.language", decide_spouse_language)
register("spouse.work", decide_spouse_work)
