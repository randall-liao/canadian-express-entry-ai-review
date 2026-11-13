"""Deterministic CRS logic that consumes the grounded rule registry (Phase 31 — Plan 04).

RULE-04 (tested deterministic CRS math from grounded rows) + RULE-05 (the
arranged-employment guard). This module is PURE arithmetic over grounded
:class:`crawler.models.crs_rules.RuleRow` payloads: it NEVER grounds on its own,
never forks the gate, and — critically — carries NO inlined volatile CRS
threshold. Every CLB conversion band, validity window, hour ceiling, cap, points
value, and policy date is READ from a row's ``machine_check`` payload (or its
volatility metadata), so the SAME static ``no_inlined_volatile_rules`` gate that
guards auditor prose also passes on this module (a self-scan test asserts it).

Public surface:
  * :func:`to_clb`                    — raw test score → CLB/NCLC level (grounded bands)
  * :func:`age_on_date`               — integer age on the ITA date (pure date math)
  * :func:`within_validity`           — freshness check from a grounded window row
  * :func:`within_freshness`          — fail-closed snapshot max-age check (grounded window)
  * :func:`row_in_effect`             — effective-window predicate over both grounded windows
  * :func:`aggregate_work`            — eligible-work duration (no over-count, no overlap)
  * :func:`score_factor`              — spouse/no-spouse point-table lookup
  * :func:`apply_transferability_caps`— clamp to the grounded 50/50/100 caps
  * :func:`compare_to_cutoff`         — arithmetic delta vs a grounded round cutoff
  * :func:`arranged_employment_guard` — RULE-05 fail-closed current-policy guard
"""

from __future__ import annotations

from datetime import date, timedelta

from crawler import crs_rules
from crawler.models.crs_rules import Registry, RuleRow

# Calendar conversion constants (NOT CRS thresholds): mean days per Gregorian year.
_DAYS_PER_YEAR = 365.2425
_MONTHS_PER_YEAR = 12

# Semantic validity kinds → the grounded machine_check field carrying the window.
_VALIDITY_FIELD = {"language": "test_date", "eca": "eca_report_date"}

# Semantic freshness kinds → the grounded machine_check field carrying the max-age
# window. STRINGS only (no volatile number lives here, so the module self-scan stays
# clean): ``snapshot_max_age`` is the FROZEN field-name contract Phase 41's real
# grounded DLI snapshot row will populate. The concrete max-age value + its
# authoritative citation are a Phase 41 (STUDY-01) data responsibility — no
# authoritative span is groundable in the current corpus — so no bound row is shipped
# to the registry this phase; ``within_freshness`` reads the window from a grounded
# ``validity_window`` row via ``_window_days`` and fails closed when none exists.
_FRESHNESS_FIELD = {"dli_snapshot": "snapshot_max_age"}


def default_registry() -> Registry:
    """Load the grounded public CRS rule registry — the source every value is read from.

    Callers (e.g. the Phase 32 auditors) pass the returned :class:`Registry` into
    the functions below; nothing here is a literal. Tests pass SYNTHETIC registries
    instead so the arithmetic is exercised without the real corpus.
    """
    return crs_rules.load_registry()


def _as_date(value) -> date:
    """Coerce an ISO ``YYYY-MM-DD`` string (or a date) into a ``date``."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# --------------------------------------------------------------------------- #
# Registry payload lookups — the ONLY source of every volatile value.
# --------------------------------------------------------------------------- #
def _window_days(registry: Registry, field: str):
    for row in registry.rows:
        mc = row.machine_check
        if mc.kind == "validity_window" and mc.field == field:
            return mc.window_days
    return None


def _threshold_max(registry: Registry, field: str):
    for row in registry.rows:
        mc = row.machine_check
        if mc.field == field and mc.max_value is not None:
            return mc.max_value
    return None


def _accepted_values(registry: Registry, field: str):
    for row in registry.rows:
        mc = row.machine_check
        if mc.kind == "accepted_enum" and mc.field == field and mc.accepted_values:
            return {av.value for av in mc.accepted_values}
    return None


def _cap_value(registry: Registry, field: str):
    for row in registry.rows:
        mc = row.machine_check
        if mc.kind == "cap" and mc.field == field:
            return mc.cap_value
    return None


def _find_row(registry: Registry, rule_id: str) -> RuleRow | None:
    for row in registry.rows:
        if row.rule_id == rule_id:
            return row
    return None


# --------------------------------------------------------------------------- #
# to_clb — raw language-test score → CLB/NCLC level (grounded conversion bands).
# --------------------------------------------------------------------------- #
def to_clb(test_type: str, ability: str, raw_score, registry: Registry):
    """Return the CLB/NCLC level for a raw ability score from grounded conversion rows.

    Scans every ``conversion`` machine_check for a band entry whose ``test_type``
    and ``ability`` match and whose ``[min_score, max_score]`` contains
    *raw_score*; returns the band's level. An unknown test/ability or an
    out-of-table score returns ``None`` — NEVER a guessed level (fail-closed).
    """
    for row in registry.rows:
        mc = row.machine_check
        if mc.kind != "conversion":
            continue
        for entry in mc.points_by_level or []:
            if entry.test_type != test_type or entry.ability != ability:
                continue
            if entry.min_score is None or entry.max_score is None:
                continue
            if entry.min_score <= raw_score <= entry.max_score:
                return int(entry.level)
    return None


# --------------------------------------------------------------------------- #
# age_on_date — integer age on the ITA date (pure date math, no thresholds).
# --------------------------------------------------------------------------- #
def age_on_date(dob, ita_date) -> int:
    """Return integer completed years on the ITA date.

    A birthday falling AFTER the ITA date in the same year does not raise the
    count (the person had not yet had that birthday on the ITA date).
    """
    d = _as_date(dob)
    i = _as_date(ita_date)
    years = i.year - d.year
    if (i.month, i.day) < (d.month, d.day):
        years -= 1
    return years


# --------------------------------------------------------------------------- #
# within_validity — freshness check from a grounded validity-window row.
# --------------------------------------------------------------------------- #
def within_validity(kind: str, issued_date, reference_date, registry: Registry) -> bool:
    """Return True iff *issued_date* is within the grounded validity window of *kind*.

    Reads the window length from the grounded ``validity_window`` row (language /
    ECA). If no grounded window exists the result is ``False`` (fail-closed for a
    green verdict). A document issued after the reference date, or older than the
    grounded window, is not valid.
    """
    field = _VALIDITY_FIELD.get(kind, kind)
    window = _window_days(registry, field)
    if window is None:
        return False
    delta = (_as_date(reference_date) - _as_date(issued_date)).days
    return 0 <= delta <= window


# --------------------------------------------------------------------------- #
# within_freshness — staleness check from a grounded max-age window row.
# --------------------------------------------------------------------------- #
def within_freshness(kind: str, crawl_date, reference_date, registry: Registry) -> bool:
    """Return True iff *crawl_date* is within the grounded max-age window of *kind*.

    An additive fail-closed SIBLING of :func:`within_validity` (it is NOT wired into
    any decider). Reads the window length from the grounded ``validity_window`` row
    named by :data:`_FRESHNESS_FIELD` — the SAME shipped ``_window_days`` reader, never
    an inlined numeric default. If no grounded window exists the result is ``False``
    (fail-closed for a green verdict — the milestone's dominant false-green risk). A
    crawl_date after the reference date, or older than the grounded window, is stale
    and returns ``False``.
    """
    field = _FRESHNESS_FIELD.get(kind, kind)
    window = _window_days(registry, field)
    if window is None:
        return False
    delta = (_as_date(reference_date) - _as_date(crawl_date)).days
    return 0 <= delta <= window


# --------------------------------------------------------------------------- #
# aggregate_work — eligible-work duration (no over-count, no overlap double-count).
# --------------------------------------------------------------------------- #
def aggregate_work(periods, registry: Registry) -> dict:
    """Sum eligible work duration from grounded work-definition rows.

    Eligibility (all read from grounded rows): the period's TEER must be in the
    grounded accepted set; a full-time period (weekly hours at or above the
    grounded ceiling) contributes its whole calendar span, and hours ABOVE the
    ceiling do NOT over-count (the full-time fraction is clamped to one); a
    part-time period contributes its span pro-rated by the grounded hours ceiling.
    Overlapping full-time calendar spans are merged (union) so shared time is
    never double-counted. Only work inside the grounded reference-period window
    (anchored at the most recent period end) is counted.

    Returns ``{"months": float, "years": float}``.
    """
    hours_ceiling = _threshold_max(registry, "hours_per_week")
    window = _window_days(registry, "work_reference_period")
    teer_ok = _accepted_values(registry, "teer")

    eligible: list[tuple[date, date, float]] = []
    for p in periods:
        if teer_ok is not None and str(p.get("teer")) not in teer_ok:
            continue
        start = _as_date(p["start"])
        end = _as_date(p["end"])
        if end < start:
            continue
        hours = p.get("hours_per_week")
        if hours_ceiling and hours is not None:
            fraction = min(hours / hours_ceiling, 1.0)
        else:
            fraction = 1.0
        eligible.append((start, end, fraction))

    if not eligible:
        return {"months": 0.0, "years": 0.0}

    # Grounded reference-period window: drop/clip spans older than the window.
    if window is not None:
        anchor = max(e for _, e, _ in eligible)
        cutoff = anchor - timedelta(days=window)
        clipped: list[tuple[date, date, float]] = []
        for s, e, f in eligible:
            if e < cutoff:
                continue
            clipped.append((max(s, cutoff), e, f))
        eligible = clipped

    # Full-time spans (fraction one) merge as a union; part-time spans pro-rate.
    full = sorted((s, e) for s, e, f in eligible if f >= 1.0)
    part_days = sum(
        f * ((e - s).days + 1) for s, e, f in eligible if f < 1.0
    )

    merged: list[list[date]] = []
    for s, e in full:
        if merged and s <= merged[-1][1] + timedelta(days=1):
            if e > merged[-1][1]:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    full_days = sum((e - s).days + 1 for s, e in merged)

    total_days = full_days + part_days
    years = total_days / _DAYS_PER_YEAR
    return {"months": years * _MONTHS_PER_YEAR, "years": years}


# --------------------------------------------------------------------------- #
# score_factor — spouse/no-spouse point-table lookup (mode-correct grounded row).
# --------------------------------------------------------------------------- #
def score_factor(factor_id: str, value, spouse_mode: bool, registry: Registry):
    """Return the grounded points for *factor_id* at *value* under the given mode.

    Selects rows the factor OWNS — whose PRIMARY factor id (``factor_ids[0]``) is
    *factor_id*. Matching the OWNING factor (not any factor in the list) is what
    keeps a transferability row — which lists a core factor as a *component*
    dependency in ``factor_ids`` but owns a ``transfer.*`` primary id — from being
    mistaken for that core factor's own points table (which would otherwise let a
    CLB-9 transferability tier leak into a language score).

    Mode is chosen by LABEL, not by ``factor_group`` — mirroring the already-proven
    ``crawler.auditors.core._grounded_points`` / ``_age_points``. A principal
    core factor encodes both the with-spouse and no-spouse columns as LABELLED
    :class:`PointsEntry` rows INSIDE its one owning ``core_human_capital`` row
    (``*_with_spouse`` / ``*_without_spouse`` labels), so the owning core row is
    visited in BOTH modes and the mode column is picked from the entry whose label
    carries ``with_spouse`` (resp. ``without_spouse``); an unlabelled synthetic row
    falls back to the last matching entry (preserving prior last-match-wins
    behaviour). A ``spouse_common_law``-group row (the SPOUSE's OWN factor) is
    visited ONLY in spouse mode, so a spouse factor still contributes only when an
    accompanying partner is present. Clamps to any grounded per-section ``cap`` row
    for the surviving rows. Returns ``None`` when no grounded row covers the value
    (never a guessed award).
    """
    cap = None
    matches = []
    for row in registry.rows:
        if not row.factor_ids or row.factor_ids[0] != factor_id:
            continue
        # Spouse-owned rows contribute ONLY in spouse mode; core-group rows (which
        # carry both columns as labelled entries) are visited in BOTH modes.
        if row.factor_group == "spouse_common_law" and not spouse_mode:
            continue
        mc = row.machine_check
        if mc.kind == "cap" and mc.cap_value is not None:
            cap = mc.cap_value if cap is None else min(cap, mc.cap_value)
        for entry in mc.points_by_level or []:
            if str(entry.level) == str(value):
                matches.append(entry)
    if not matches:
        return None
    # Mode-column selection by grounded label, else the last matching entry.
    points = None
    for entry in matches:
        label = entry.label or ""
        if spouse_mode and "with_spouse" in label and "without_spouse" not in label:
            points = entry.points
            break
        if not spouse_mode and "without_spouse" in label:
            points = entry.points
            break
    if points is None:
        points = matches[-1].points
    return min(points, cap) if cap is not None else points


# --------------------------------------------------------------------------- #
# apply_transferability_caps — clamp to the grounded 50/50/100 caps.
# --------------------------------------------------------------------------- #
def apply_transferability_caps(components: dict, registry: Registry) -> dict:
    """Clamp each transferability component and the total to their grounded caps.

    *components* maps a grounded cap field (e.g. ``education_combination``,
    ``foreign_work_combination``) to a raw points value. Each is clamped to its
    grounded ``cap`` row value; the total is the sum of the clamped components,
    itself clamped to the grounded total-transferability cap. Every ceiling is
    READ from a grounded cap row — never a literal.
    """
    out: dict = {}
    subtotal = 0
    for field, value in components.items():
        cap = _cap_value(registry, field)
        clamped = min(value, cap) if cap is not None else value
        out[field] = clamped
        subtotal += clamped
    total_cap = _cap_value(registry, "skill_transferability_total")
    out["total"] = min(subtotal, total_cap) if total_cap is not None else subtotal
    return out


# --------------------------------------------------------------------------- #
# compare_to_cutoff — arithmetic delta vs a grounded round cutoff (no advice).
# --------------------------------------------------------------------------- #
def compare_to_cutoff(substantiated_total, ita_round, registry: Registry | None = None) -> dict:
    """Return ``{delta, meets_cutoff}`` for a substantiated total vs a round cutoff.

    *ita_round* is either the numeric cutoff or a mapping carrying ``cutoff`` /
    ``cutoff_score`` (sourced from grounded round data by the caller). This is a
    pure arithmetic delta — it gives NO legal advice or eligibility ruling
    (SAFE-04 framing is deferred).
    """
    if isinstance(ita_round, dict):
        cutoff = ita_round.get("cutoff", ita_round.get("cutoff_score"))
    else:
        cutoff = ita_round
    delta = int(substantiated_total) - int(cutoff)
    return {"delta": delta, "meets_cutoff": delta >= 0}


# --------------------------------------------------------------------------- #
# arranged_employment_guard — RULE-05 fail-closed current-policy guard.
# --------------------------------------------------------------------------- #
def _in_window(when, effective_from, effective_to) -> bool:
    """True iff *when* is within [effective_from, effective_to) (grounded dates)."""
    d = _as_date(when)
    if effective_from is not None and d < _as_date(effective_from):
        return False
    if effective_to is not None and d >= _as_date(effective_to):
        return False
    return True


def row_in_effect(row: RuleRow, reference_date) -> bool:
    """Return True iff *row* is applicable on *reference_date* (grounded windows).

    An additive predicate that composes :func:`_in_window` over BOTH grounded window
    sources a row carries — ``machine_check.effective_from/to`` and
    ``volatility.effective_from/to`` — consolidating the exact pair of window checks
    :func:`arranged_employment_guard` performs. Outside EITHER window the row is not in
    effect (``False``). A row whose windows are both ``None`` is stable/effective and
    returns ``True`` (``_in_window`` returns True for a ``None`` bound). A malformed
    date raises out of ``_as_date`` to the caller (a decider treats the exception as
    not-in-effect) — it is never swallowed into a ``True``.
    """
    mc, vol = row.machine_check, row.volatility
    if not _in_window(reference_date, mc.effective_from, mc.effective_to):
        return False
    if not _in_window(reference_date, vol.effective_from, vol.effective_to):
        return False
    return True


def arranged_employment_guard(claim_points, ita_date, registry: Registry) -> dict:
    """Fail-closed guard for a non-zero arranged-employment (job-offer) CRS claim.

    Returns ``{status, points, citation}``:

    * A zero / unclaimed job-offer factor is ``N/A``.
    * ANY non-zero claim defaults to ``AT-RISK`` with ``points == 0``, citing the
      grounded current-policy repeal row — the job-offer additional-CRS points
      were removed as of the grounded effective date.
    * The ONLY exception: a grounded (non-gap) legacy row whose grounded effective
      window covers *ita_date*. Even then the verdict stays ``AT-RISK`` with
      ``points is None`` (deferred to manual legacy resolution), citing the legacy
      row — it NEVER auto-returns a non-zero award or a SUBSTANTIATED verdict.

    Every policy date is READ from grounded metadata (the current row's
    ``machine_check.effective_from`` and the legacy row's volatility window),
    never a prose literal.
    """
    if not claim_points:
        return {"status": "N/A", "points": 0, "citation": None}

    current = _find_row(registry, "additional.job_offer.current")
    legacy = _find_row(registry, "additional.job_offer.legacy")

    current_citation = current.citations[0].chunk_id if current else None

    # Legacy exception: a grounded, in-window legacy row → AT-RISK (manual), never green.
    if legacy is not None and not legacy.gap:
        if _in_window(ita_date, legacy.volatility.effective_from, legacy.volatility.effective_to):
            return {
                "status": "AT-RISK",
                "points": None,  # manual legacy resolution — never an auto-award
                "citation": legacy.citations[0].chunk_id,
            }

    # Default fail-closed: non-zero claim is AT-RISK / 0 citing the current repeal.
    return {"status": "AT-RISK", "points": 0, "citation": current_citation}
