"""Skill-transferability auditor module (Phase 33 — 33-04, AUDIT-01/03, SC5).

The third context-light module. Unlike the others it RECOMBINES already-
substantiated core evidence, so each of the five combination deciders reads its
two component core cards from ``ctx.prior_cards`` (populated because the spine
orders ``transfer.*`` factors LAST) and awards the grounded tier points ONLY when
every component is SUBSTANTIATED — never on an unproven component (T-33-10 / SC5).

Cap enforcement is fail-closed and grounded: each combination's contribution is
clamped through ``crs_audit.apply_transferability_caps`` against the grounded
education-combination, foreign-work-combination, and total caps (the running
per-section + total sums come from the prior transfer cards this run). NO cap or
tier literal appears here — every number is read from a grounded row (a self-scan
``no_inlined_volatile_rules`` test asserts it).
"""

from __future__ import annotations

from collections import defaultdict

from crawler import crs_audit
from crawler.auditors import DecisionContext, DecisionResult, register

# Which grounded cap section each combination contributes to.
_SECTION_OF: dict[str, str] = {
    "transfer.education_language": "education_combination",
    "transfer.education_work": "education_combination",
    "transfer.foreign_language": "foreign_work_combination",
    "transfer.foreign_work": "foreign_work_combination",
    "transfer.certificate_language": "foreign_work_combination",
}

_LANGUAGE_COMPONENT = "core.language.first"
_WORK_COMPONENT = "core.work"


def _component_ids(ctx: DecisionContext) -> list[str]:
    """The component core factor ids tagged on this combination's grounded row(s)."""
    ids: list[str] = []
    for row in ctx.consumed.rows:
        for fid in row.factor_ids:
            if fid.startswith("core.") and fid not in ids:
                ids.append(fid)
    return ids


def _tier_threshold(level) -> float | None:
    """Parse a grounded tier level (``7`` / ``"2+"`` / ``"1"``) to a numeric floor."""
    text = str(level).strip().rstrip("+")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _driver_level(components: list[str], prior_cards) -> float | None:
    """The confirmed component level that keys the tier (language CLB or work years)."""
    if _LANGUAGE_COMPONENT in components:
        card = prior_cards.get(_LANGUAGE_COMPONENT)
        key = "lowest_benchmark"
    elif _WORK_COMPONENT in components:
        card = prior_cards.get(_WORK_COMPONENT)
        key = "aggregated_years"
    else:
        return None
    if card is None or not isinstance(card.confirmed_value, dict):
        return None
    value = card.confirmed_value.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tier_points(ctx: DecisionContext, level: float | None) -> int | None:
    """Highest grounded tier points whose floor is <= *level* (None if below all)."""
    if level is None:
        return None
    best: tuple[float, int] | None = None
    for row in ctx.consumed.rows:
        for entry in row.machine_check.points_by_level or []:
            if entry.points is None:
                continue
            floor = _tier_threshold(entry.level)
            if floor is None or level < floor:
                continue
            if best is None or floor > best[0]:
                best = (floor, entry.points)
    return best[1] if best else None


def _award_capped(ctx: DecisionContext, section_field: str, raw_points: int) -> int:
    """Incremental clamped contribution of this combination (grounded caps).

    Rebuilds the per-section running totals from the prior transfer cards decided
    this run, then uses ``crs_audit.apply_transferability_caps`` to clamp the
    section AND the grand total; the awarded amount is the increase in the clamped
    total this combination produces (so the grounded 50/50/100 caps hold across
    combinations, in decision order).
    """
    prior_sec: dict[str, int] = defaultdict(int)
    for fid, card in ctx.prior_cards.items():
        if (fid.startswith("transfer.") and card.verdict == "SUBSTANTIATED"
                and card.substantiated_points):
            prior_sec[_SECTION_OF.get(fid, section_field)] += card.substantiated_points

    prior_total = crs_audit.apply_transferability_caps(
        dict(prior_sec), ctx.registry)["total"]
    new_sec = dict(prior_sec)
    new_sec[section_field] = new_sec.get(section_field, 0) + raw_points
    new_total = crs_audit.apply_transferability_caps(new_sec, ctx.registry)["total"]
    return max(0, new_total - prior_total)


def _decide_combination(ctx: DecisionContext) -> DecisionResult:
    """The shared combination decision: every component SUBSTANTIATED → capped tier."""
    components = _component_ids(ctx)
    confirmed = {"components": components}

    if not components:
        return DecisionResult("GAP", "unmet_component", confirmed_value=confirmed)

    cards = [(cid, ctx.prior_cards.get(cid)) for cid in components]
    # A component decided AT-RISK propagates AT-RISK (unresolved dependency).
    if any(card is not None and card.verdict == "AT-RISK" for _, card in cards):
        return DecisionResult("AT-RISK", "at_risk_component", confirmed_value=confirmed)
    # A missing / GAP / N/A component blocks the combination (never points).
    if any(card is None or card.verdict != "SUBSTANTIATED" for _, card in cards):
        return DecisionResult("GAP", "unmet_component", confirmed_value=confirmed)

    level = _driver_level(components, ctx.prior_cards)
    confirmed["driver_level"] = level
    raw = _tier_points(ctx, level)
    if raw is None:
        return DecisionResult("GAP", "below_tier", confirmed_value=confirmed)

    awarded = _award_capped(ctx, _SECTION_OF.get(ctx.factor_id, ""), raw)
    confirmed["raw_tier_points"] = raw
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          confirmed_value=confirmed, substantiated_points=awarded)


def decide_education_language(ctx: DecisionContext) -> DecisionResult:
    """Education × first official language (tier keyed by the language benchmark)."""
    return _decide_combination(ctx)


def decide_education_work(ctx: DecisionContext) -> DecisionResult:
    """Education × Canadian work (tier keyed by years of Canadian work)."""
    return _decide_combination(ctx)


def decide_foreign_language(ctx: DecisionContext) -> DecisionResult:
    """Foreign work × first official language (tier keyed by the language benchmark)."""
    return _decide_combination(ctx)


def decide_foreign_work(ctx: DecisionContext) -> DecisionResult:
    """Foreign work × Canadian work (tier keyed by years of Canadian work)."""
    return _decide_combination(ctx)


def decide_certificate_language(ctx: DecisionContext) -> DecisionResult:
    """Certificate of qualification × language (tier keyed by the language benchmark)."""
    return _decide_combination(ctx)


register("transfer.education_language", decide_education_language)
register("transfer.education_work", decide_education_work)
register("transfer.foreign_language", decide_foreign_language)
register("transfer.foreign_work", decide_foreign_work)
register("transfer.certificate_language", decide_certificate_language)
