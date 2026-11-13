"""Additional-points auditor module (Phase 33 — 33-05, AUDIT-01/03).

The fourth and final context-light module: provincial/territorial nomination,
arranged employment (job offer), Canadian post-secondary study, strong French,
and sibling in Canada — with extra policy attention on the arranged-employment
trap.

The job-offer factor NEVER auto-greens: ``decide_job_offer`` delegates to the
shipped ``crs_audit.arranged_employment_guard`` (RULE-05) and only ever returns
N/A (no claim) or AT-RISK (current-policy 0, or a grounded in-window legacy that
stays manual with ``points is None``). This separates "a valid offer for program
eligibility" from "CRS additional points" (T-33-12).

Every level / point / threshold is READ from a grounded row (the shared core
helpers + ``crs_audit``); this module carries NO inlined volatile threshold (a
self-scan ``no_inlined_volatile_rules`` test asserts it).
"""

from __future__ import annotations

from datetime import date

from crawler import crs_audit, siblingfields
from crawler.auditors import DecisionContext, DecisionResult, register
from crawler.auditors.core import (
    _confirmed_snapshot,
    _decide_language,
    _effective_value,
    _grounded_points,
)

# The three distinct rows on the SHARED ``additional.job_offer`` factor. Naming
# them lets ``decide_job_offer`` scope each verdict's citations to the row(s) it
# actually derives from (WR-02) — these are rule IDS (stable identifiers), NOT
# volatile thresholds, so they are not inlined-rule literals.
_JOB_OFFER_CURRENT = "additional.job_offer.current"
_JOB_OFFER_LEGACY = "additional.job_offer.legacy"
_JOB_OFFER_PHYSICIAN = "additional.job_offer.physician"


# --------------------------------------------------------------------------- #
# decide_job_offer — RULE-05 guard; never SUBSTANTIATED, never auto-award.
# --------------------------------------------------------------------------- #
def decide_job_offer(ctx: DecisionContext) -> DecisionResult:
    """Arranged-employment additional CRS is AT-RISK unless grounded legacy proven.

    Delegates to ``crs_audit.arranged_employment_guard``: a zero/unclaimed offer →
    N/A; any non-zero claim → AT-RISK with the current-policy 0 (repeal) OR, only
    for a grounded in-window legacy row, AT-RISK with ``points is None`` (manual
    legacy resolution). It NEVER returns SUBSTANTIATED and NEVER auto-awards a
    non-zero value.

    A distinct physician public-policy branch fires BEFORE the frozen guard: a
    confirmed physician ``noc_code`` matched against the grounded
    ``additional.job_offer.physician`` accepted-NOC set AND that row's grounded
    effective window (``crs_audit.row_in_effect``) resolves to a DISTINCT
    ``AT-RISK "physician_policy_manual"`` verdict with ``substantiated_points is
    None`` — still manual, never an award, never green. Every physician NOC + date
    is READ from the grounded row (no inlined literal); the branch order matters
    because the open physician window overlaps the legacy window, so the physician
    check must precede the guard to keep POLICY-02's distinct citation.

    Reason-aware citations (WR-02): each verdict scopes ``rule_ids`` to the single
    ``additional.job_offer`` row it derives from (current-repeal / legacy /
    physician), so the spine surfaces ONLY that row's citations. A non-physician
    verdict therefore never over-cites the physician-NOC citations, and vice versa.
    The whole consumed subset is still grounding-gated by the spine (fail-closed);
    this only narrows what each card surfaces.
    """
    claim_points = getattr(ctx.factor, "claimed_points", None) or 0
    confirmed = _confirmed_snapshot(ctx.by_field)
    if not claim_points:
        # No claim → N/A. The grounded basis for "a job offer yields no additional
        # CRS points" is the current-repeal row, so scope the citation to it (not
        # the irrelevant legacy / physician rows).
        return DecisionResult("N/A", "no_job_offer_points",
                              claimed_value=claim_points, confirmed_value=confirmed,
                              rule_ids=(_JOB_OFFER_CURRENT,))
    # Without an authoritative ITA date the legacy window cannot be evaluated —
    # fall back to the fail-closed current policy (AT-RISK / 0).
    if ctx.ita_date is None:
        return DecisionResult("AT-RISK", "arranged_employment_current",
                              claimed_value=claim_points, confirmed_value=confirmed,
                              substantiated_points=0,
                              rule_ids=(_JOB_OFFER_CURRENT,))

    # [NEW] Distinct physician public-policy branch — grounded, AT-RISK/manual only.
    # Fires BEFORE the frozen guard because the open physician window overlaps the
    # legacy window; wrong order would surface arranged_employment_legacy_manual
    # instead of the distinct physician citation (POLICY-02). The NOC set + the
    # effective window come ONLY from the grounded row (no inlined literal); the
    # window predicate is CONSUMED from crs_audit (never re-added here). A malformed
    # grounded date fails closed (not-in-effect). Still AT-RISK/manual — never an
    # award, never SUBSTANTIATED.
    phys = next((r for r in ctx.registry.rows
                 if r.rule_id == _JOB_OFFER_PHYSICIAN), None)
    noc_val = ctx.by_field.get("noc_code")
    if phys is not None and not phys.gap and noc_val is not None:
        noc = str(_effective_value(noc_val))
        phys_nocs = {av.value for av in (phys.machine_check.accepted_values or [])}
        try:
            in_effect = crs_audit.row_in_effect(phys, ctx.ita_date)
        except (TypeError, ValueError):
            in_effect = False
        if noc in phys_nocs and in_effect:
            return DecisionResult("AT-RISK", "physician_policy_manual",
                                  claimed_value=claim_points,
                                  confirmed_value=confirmed,
                                  substantiated_points=None,  # manual; never an award
                                  rule_ids=(_JOB_OFFER_PHYSICIAN,))

    guard = crs_audit.arranged_employment_guard(
        claim_points, ctx.ita_date, ctx.registry)
    if guard["status"] == "N/A":
        return DecisionResult("N/A", "no_job_offer_points",
                              claimed_value=claim_points, confirmed_value=confirmed,
                              rule_ids=(_JOB_OFFER_CURRENT,))
    # Scope the citation to the row the guard's verdict derives from: the legacy
    # row for a manual legacy resolution, else the current-repeal row.
    if guard["points"] is None:
        reason = "arranged_employment_legacy_manual"
        rule_ids = (_JOB_OFFER_LEGACY,)
    else:
        reason = "arranged_employment_current"
        rule_ids = (_JOB_OFFER_CURRENT,)
    return DecisionResult("AT-RISK", reason, claimed_value=claim_points,
                          confirmed_value=confirmed,
                          substantiated_points=guard["points"],
                          rule_ids=rule_ids)


# --------------------------------------------------------------------------- #
# decide_nomination — 600 only on a verified, non-revoked, non-expired nomination.
# --------------------------------------------------------------------------- #
def decide_nomination(ctx: DecisionContext) -> DecisionResult:
    """Provincial/territorial nomination: grounded points only when verified.

    Requires a confirmed nomination stream; an expired nomination → AT-RISK; a
    missing one → GAP. The award value is read from the grounded nomination row.
    """
    confirmed = _confirmed_snapshot(ctx.by_field)
    stream = ctx.by_field.get("nomination_stream")
    if stream is None:
        return DecisionResult("GAP", "missing_evidence", confirmed_value=confirmed)

    expiry = ctx.by_field.get("expiry_date")
    if expiry is not None:
        try:
            expiry_date = date.fromisoformat(str(_effective_value(expiry))[:10])
            ref = date.fromisoformat(str(ctx.reference_date)[:10])
            if expiry_date < ref:
                return DecisionResult("AT-RISK", "expired_nomination",
                                      confirmed_value=confirmed)
        except (TypeError, ValueError):
            return DecisionResult("AT-RISK", "unresolved_nomination_expiry",
                                  confirmed_value=confirmed)

    points = _grounded_points(ctx.registry, "additional.nomination", "nomination",
                              spouse_mode=False)
    if points is None:
        return DecisionResult("GAP", "below_threshold", confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          confirmed_value=confirmed, substantiated_points=points)


# --------------------------------------------------------------------------- #
# decide_study — credential-only seam; designation belongs to study_review.
# --------------------------------------------------------------------------- #
def decide_study(ctx: DecisionContext) -> DecisionResult:
    """Fail closed because this db-free context has credential evidence only.

    Exact DLI, R73, snapshot, provenance, and temporal validation belongs
    exclusively to :mod:`crawler.study_review`; normal evidence is intentionally
    isolated on ``review.study`` and never reaches this CRS-grid decider.  A
    credential matching the gated ``additional.study`` tier therefore remains
    manual/AT-RISK with no points.  Missing or unknown tiers remain GAP.
    """
    confirmed = _confirmed_snapshot(ctx.by_field)
    level_value = ctx.by_field.get("credential_level")
    if level_value is None:
        return DecisionResult("GAP", "missing_evidence", confirmed_value=confirmed)
    level = str(_effective_value(level_value))
    row = next(
        (item for item in ctx.registry.rows
         if item.rule_id == "additional.study" and not item.gap),
        None,
    )
    grounded_tiers = {
        str(entry.level)
        for entry in (
            row.machine_check.points_by_level
            if row is not None else []
        ) or []
        if entry.level is not None
    }
    if level not in grounded_tiers:
        return DecisionResult("GAP", "below_threshold", confirmed_value=confirmed)
    return DecisionResult(
        "AT-RISK",
        "credential_only_no_designation",
        confirmed_value=confirmed,
        substantiated_points=None,
    )


# --------------------------------------------------------------------------- #
# decide_french — strong French via grounded NCLC conversion + French points.
# --------------------------------------------------------------------------- #
def decide_french(ctx: DecisionContext) -> DecisionResult:
    """Strong French: all four French abilities convert (NCLC) and meet the claim.

    Reuses the frozen conversion + validity + per-ability decision path; a below-
    claim result is GAP and an unresolved conversion is AT-RISK. On a satisfying
    French result the grounded strong-French points are awarded.
    """
    result = _decide_language(ctx, "additional.french")
    if result.verdict != "SUBSTANTIATED":
        return result
    points = _grounded_points(ctx.registry, "additional.french", "french_only",
                              spouse_mode=False)
    result.substantiated_points = points
    return result


# --------------------------------------------------------------------------- #
# decide_sibling — grounded relationship + status + residence + ADULT-age chain.
# --------------------------------------------------------------------------- #
def _grounded_min_age(registry, field: str) -> float | None:
    """Return the grounded minimum-age threshold (``min_value``) for *field*, or None.

    Mirrors ``crs_audit._threshold_max`` but reads ``min_value`` off the grounded
    ``kind: threshold`` row — an allow-listed machine_check payload the registry
    carries, never an inlined Python literal.
    """
    for row in registry.rows:
        mc = row.machine_check
        if mc.kind == "threshold" and mc.field == field and mc.min_value is not None:
            return mc.min_value
    return None


def decide_sibling(ctx: DecisionContext) -> DecisionResult:
    """Sibling in Canada: grounded points only on a confirmed ADULT chain.

    Requires confirmed sibling evidence — an accepted relationship
    (brother/sister) + an accepted status (citizen/permanent_resident) + a
    current Canadian residence + a resolvable date-of-birth proving the sibling
    is an ADULT at the ITA date. Fail-closed:

      * any of the four required fields absent → GAP ``missing_evidence``;
      * a non-accepted relationship / status token, an unresolvable DOB, no
        authoritative ITA date to pin the age, or a missing grounded adult
        threshold → AT-RISK ``unresolved_sibling`` (never coerced to accepted);
      * a confirmed MINOR (age at the ITA date below the grounded threshold) →
        AT-RISK ``sibling_minor`` — NEVER SUBSTANTIATED;
      * otherwise SUBSTANTIATED with the grounded points.

    The points come from the grounded ``additional.sibling`` row via
    ``_grounded_points`` and the adult threshold from the grounded
    ``additional.sibling.adult`` row via ``_grounded_min_age``; the age is pinned
    with ``crs_audit.age_on_date`` — no threshold / points / date literal here.
    """
    confirmed = _confirmed_snapshot(ctx.by_field)
    required = ("sibling_relationship", "sibling_status", "sibling_residence",
                "sibling_date_of_birth")
    if any(name not in ctx.by_field for name in required):
        return DecisionResult("GAP", "missing_evidence", confirmed_value=confirmed)

    relationship = str(_effective_value(ctx.by_field["sibling_relationship"]))
    status = str(_effective_value(ctx.by_field["sibling_status"]))
    if (relationship not in siblingfields.SIBLING_RELATIONSHIP_ACCEPTED
            or status not in siblingfields.SIBLING_STATUS_ACCEPTED):
        return DecisionResult("AT-RISK", "unresolved_sibling",
                              confirmed_value=confirmed)

    # ENFORCED grounded adult gate (mirror decide_age): read the minimum age from
    # the grounded threshold row, and pin the sibling's age to the authoritative
    # ITA date. Without the grounded threshold OR an ITA date, fail closed.
    min_age = _grounded_min_age(ctx.registry, "sibling_min_age")
    if min_age is None or ctx.ita_date is None:
        return DecisionResult("AT-RISK", "unresolved_sibling",
                              confirmed_value=confirmed)
    try:
        age = crs_audit.age_on_date(
            _effective_value(ctx.by_field["sibling_date_of_birth"]), ctx.ita_date)
    except (TypeError, ValueError):
        return DecisionResult("AT-RISK", "unresolved_sibling",
                              confirmed_value=confirmed)
    confirmed["sibling_age_on_ita"] = age
    if age < min_age:
        # A confirmed minor can NEVER green the factor (the core false-green fix).
        return DecisionResult("AT-RISK", "sibling_minor", confirmed_value=confirmed)

    points = _grounded_points(ctx.registry, "additional.sibling", "sibling",
                              spouse_mode=False)
    if points is None:
        return DecisionResult("GAP", "below_threshold", confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          confirmed_value=confirmed, substantiated_points=points)


register("additional.nomination", decide_nomination)
register("additional.job_offer", decide_job_offer)
register("additional.study", decide_study)
register("additional.french", decide_french)
register("additional.sibling", decide_sibling)
