"""Core human-capital deciders (Phase 33 — 33-01/33-02, AUDIT-01/03).

The reference module on the dispatch spine: it ports the shipped Phase-32
first-official-language verdict logic VERBATIM (every reason code + branch order
preserved so ``test_auditor.py`` stays green — the parity gate) and extends the
same fail-closed pattern to the four other core factors: second official
language, age, education, and Canadian work.

Every band / window / points / accepted-value figure is READ from a grounded
registry row via ``crawler.crs_audit`` (``to_clb`` / ``within_validity`` /
``score_factor`` / ``age_on_date`` / ``aggregate_work``); this module carries NO
inlined volatile CRS threshold (a self-scan ``no_inlined_volatile_rules`` test
asserts it).

Task-boundary note (33-01 vs 33-02): the language deciders (``decide_first_language``
/ ``decide_second_language``) land in Wave-1 Task 1 so the ``audit_factor`` →
``audit_one`` → dispatch shim keeps the 16 ``test_auditor.py`` cases green; the
age / education / work deciders + the dispatch test land in Task 2.
"""

from __future__ import annotations

from typing import Any

from crawler import crs_audit
from crawler.auditors import DecisionContext, DecisionResult, register
from crawler.models.crs_rules import Registry

# The four abilities a language verdict requires, mapped from the EXTRACT-01
# raw-score field name to the conversion-row ability token.
_ABILITY_FIELDS: dict[str, str] = {
    "raw_score_listening": "listening",
    "raw_score_reading": "reading",
    "raw_score_writing": "writing",
    "raw_score_speaking": "speaking",
}

# The non-ability fields a language verdict also requires.
_REQUIRED_META_FIELDS = ("test_type", "test_date")


# --------------------------------------------------------------------------- #
# Shared confirmed-value helpers (PII-bearing snapshots stay vault-only).
# --------------------------------------------------------------------------- #
def _effective_value(value) -> Any:
    """The confirmed applicant value: the correction if corrected, else the read."""
    if value.confirmation_status == "corrected" and value.confirmed_value is not None:
        return value.confirmed_value
    return value.normalized_value


def _confirmed_snapshot(by_field: dict) -> dict:
    """A PII-BEARING snapshot of the confirmed applicant values (vault-only)."""
    return {field: _effective_value(value) for field, value in by_field.items()}


def _claimed_threshold(factor) -> int | None:
    """Parse the claimed benchmark level from the profile factor (level or value)."""
    if factor is None:
        return None
    for candidate in (factor.claimed_level, factor.claimed_value):
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _accepted_test_types(registry: Registry, field: str = "test_type") -> set[str] | None:
    """Return the grounded accepted language test-type set (or None)."""
    for row in registry.rows:
        mc = row.machine_check
        if mc.kind == "accepted_enum" and mc.field == field and mc.accepted_values:
            return {av.value for av in mc.accepted_values}
    return None


def _sum_points(factor_id: str, benchmarks: dict[str, int], spouse_mode: bool,
                registry: Registry) -> int | None:
    """Sum the grounded per-ability points across benchmarks (None if any absent).

    Every point figure is read from a grounded points row via
    ``crs_audit.score_factor`` — never a literal.
    """
    total = 0
    for level in benchmarks.values():
        points = crs_audit.score_factor(factor_id, level, spouse_mode, registry)
        if points is None:
            return None
        total += points
    return total


# --------------------------------------------------------------------------- #
# Language deciders (first + second official language) — Phase-32 parity.
# --------------------------------------------------------------------------- #
def _decide_language(ctx: DecisionContext, points_factor_id: str) -> DecisionResult:
    """The fail-closed language decision table (shared by first + second language).

    Reason codes + branch order are BYTE-FOR-BYTE identical to the shipped
    Phase-32 ``auditor._decide`` (proven by ``test_auditor.py``). ``points_factor_id``
    selects the grounded points row (``core.language.first`` vs
    ``core.language.second``) so the second language scores under its lower
    combined maximum while reusing the same conversion + validity path.
    """
    by_field = ctx.by_field
    registry = ctx.registry
    spouse_mode = ctx.spouse_mode
    reference_date = ctx.reference_date
    claimed_threshold = _claimed_threshold(ctx.factor)
    confirmed = _confirmed_snapshot(by_field)

    # 1. Missing required proof -> GAP (never green).
    required = list(_ABILITY_FIELDS) + list(_REQUIRED_META_FIELDS)
    missing = [f for f in required if f not in by_field]
    if missing:
        return DecisionResult("GAP", "missing_evidence",
                              claimed_value=claimed_threshold, confirmed_value=confirmed)

    test_type = str(_effective_value(by_field["test_type"]))
    test_date = str(_effective_value(by_field["test_date"]))[:10]

    # 2. Unaccepted test type -> GAP.
    accepted = _accepted_test_types(registry)
    if accepted is not None and test_type not in accepted:
        return DecisionResult("GAP", "unaccepted_test_type",
                              claimed_value=claimed_threshold, confirmed_value=confirmed)

    # 3. Convert each ability; a None mapping is semantically unresolved -> AT-RISK.
    benchmarks: dict[str, int] = {}
    for field, ability in _ABILITY_FIELDS.items():
        raw = _effective_value(by_field[field])
        try:
            level = crs_audit.to_clb(test_type, ability, float(raw), registry)
        except (TypeError, ValueError):
            level = None
        if level is None:
            confirmed["benchmarks"] = benchmarks
            return DecisionResult("AT-RISK", "unresolved_conversion",
                                  claimed_value=claimed_threshold, confirmed_value=confirmed)
        benchmarks[ability] = level
    confirmed["benchmarks"] = benchmarks
    lowest = min(benchmarks.values())
    confirmed["lowest_benchmark"] = lowest
    substantiated_points = _sum_points(points_factor_id, benchmarks, spouse_mode, registry)

    # 4. Expired test date -> AT-RISK (stale-by-time).
    if not crs_audit.within_validity("language", test_date, reference_date, registry):
        return DecisionResult("AT-RISK", "expired_test",
                              claimed_value=claimed_threshold, confirmed_value=confirmed,
                              substantiated_points=substantiated_points)

    # 5. Below the claimed benchmark -> GAP (recalculated downward).
    if claimed_threshold is not None and lowest < claimed_threshold:
        return DecisionResult("GAP", "below_threshold",
                              claimed_value=claimed_threshold, confirmed_value=confirmed,
                              substantiated_points=substantiated_points)

    # 6. Proof + eligibility + threshold + grounded -> SUBSTANTIATED.
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          claimed_value=claimed_threshold, confirmed_value=confirmed,
                          substantiated_points=substantiated_points)


def decide_first_language(ctx: DecisionContext) -> DecisionResult:
    """First-official-language verdict (Phase-32 parity; scores under first table)."""
    return _decide_language(ctx, "core.language.first")


def decide_second_language(ctx: DecisionContext) -> DecisionResult:
    """Second-official-language verdict (same path; lower combined maximum table)."""
    return _decide_language(ctx, "core.language.second")


# --------------------------------------------------------------------------- #
# Grounded points lookup (mode-aware) — principal core factors encode both the
# with-spouse and without-spouse columns as labelled PointsEntry rows inside ONE
# core_human_capital row, so column selection is by LABEL, not factor_group.
# --------------------------------------------------------------------------- #
def _grounded_points(registry: Registry, factor_id: str, value,
                     spouse_mode: bool) -> int | None:
    """Return grounded points for *factor_id* at *value*, preferring the mode column.

    Reads only grounded ``points_by_level`` entries; prefers the entry whose label
    matches the spouse / no-spouse column, else the last matching entry. Returns
    ``None`` when no grounded row covers the value (never a guessed award).
    """
    matches = []
    for row in registry.rows:
        if not row.factor_ids or row.factor_ids[0] != factor_id:
            continue
        for entry in row.machine_check.points_by_level or []:
            if str(entry.level) == str(value):
                matches.append(entry)
    if not matches:
        return None
    for entry in matches:
        label = entry.label or ""
        if spouse_mode and "with_spouse" in label and "without_spouse" not in label:
            return entry.points
        if not spouse_mode and "without_spouse" in label:
            return entry.points
    return matches[-1].points


def _parse_band(level) -> tuple[int | None, int | None]:
    """Parse a grounded age-band level string (``"20-29"`` / ``"30"``) to (lo, hi)."""
    text = str(level).strip()
    try:
        if "-" in text:
            lo_s, hi_s = text.split("-", 1)
            return int(lo_s), int(hi_s)
        n = int(text)
        return n, n
    except (TypeError, ValueError):
        return None, None


def _age_points(registry: Registry, age: int, spouse_mode: bool) -> int | None:
    """Return grounded age-table points for *age* in the mode column, or None."""
    fallback = None
    for row in registry.rows:
        if "core.age" not in row.factor_ids:
            continue
        for entry in row.machine_check.points_by_level or []:
            lo, hi = _parse_band(entry.level)
            if lo is None or not (lo <= age <= hi):
                continue
            label = entry.label or ""
            if spouse_mode and "with_spouse" in label and "without_spouse" not in label:
                return entry.points
            if not spouse_mode and "without_spouse" in label:
                return entry.points
            fallback = entry.points if fallback is None else fallback
    return fallback


def _claimed_years(factor) -> float | None:
    """Parse the claimed number of years of work from the profile factor."""
    if factor is None:
        return None
    for candidate in (factor.claimed_value, factor.claimed_level):
        try:
            return float(candidate)
        except (TypeError, ValueError):
            continue
    return None


# --------------------------------------------------------------------------- #
# decide_age — confirmed DOB + ITA date → grounded age-table points.
# --------------------------------------------------------------------------- #
def decide_age(ctx: DecisionContext) -> DecisionResult:
    """Age on the ITA date maps to grounded age-table points (fail-closed).

    Missing / unconfirmed DOB → GAP; no authoritative ITA date to pin the age
    against → AT-RISK (timing unresolved); an age outside the grounded table → GAP;
    otherwise SUBSTANTIATED with the grounded age-table points.
    """
    confirmed = _confirmed_snapshot(ctx.by_field)
    claimed = _claimed_threshold(ctx.factor)
    dob_value = ctx.by_field.get("date_of_birth")
    if dob_value is None:
        return DecisionResult("GAP", "missing_evidence",
                              claimed_value=claimed, confirmed_value=confirmed)
    dob = _effective_value(dob_value)

    # No authoritative ITA date → the age cannot be pinned to the invitation
    # (a birthday between profile and ITA could change the points): AT-RISK.
    if ctx.ita_date is None:
        return DecisionResult("AT-RISK", "timing_unresolved",
                              claimed_value=claimed, confirmed_value=confirmed)
    try:
        age = crs_audit.age_on_date(dob, ctx.ita_date)
    except (TypeError, ValueError):
        return DecisionResult("AT-RISK", "unresolved_age",
                              claimed_value=claimed, confirmed_value=confirmed)
    confirmed["age_on_ita"] = age
    points = _age_points(ctx.registry, age, ctx.spouse_mode)
    if points is None:
        return DecisionResult("GAP", "below_threshold",
                              claimed_value=claimed, confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          claimed_value=claimed, confirmed_value=confirmed,
                          substantiated_points=points)


# --------------------------------------------------------------------------- #
# decide_education — confirmed credential (+ in-window ECA for foreign) → points.
# --------------------------------------------------------------------------- #
def decide_education(ctx: DecisionContext) -> DecisionResult:
    """Education level maps to grounded education-table points (fail-closed).

    Missing credential level → GAP; a foreign credential with a missing / expired
    ECA → AT-RISK; a level outside the grounded table → GAP; otherwise
    SUBSTANTIATED with the grounded education-table points (mode column).
    """
    confirmed = _confirmed_snapshot(ctx.by_field)
    claimed = ctx.factor.claimed_level if ctx.factor is not None else None
    level_value = ctx.by_field.get("credential_level")
    if level_value is None:
        return DecisionResult("GAP", "missing_evidence",
                              claimed_value=claimed, confirmed_value=confirmed)
    level = _effective_value(level_value)

    # Foreign credential: an ECA date must exist AND be in the grounded window.
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

    points = _grounded_points(ctx.registry, "core.education", level, ctx.spouse_mode)
    if points is None:
        return DecisionResult("GAP", "below_threshold",
                              claimed_value=claimed, confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          claimed_value=claimed, confirmed_value=confirmed,
                          substantiated_points=points)


# --------------------------------------------------------------------------- #
# decide_work — multi-document eligible-work aggregation (no overlap double-count).
# --------------------------------------------------------------------------- #
_WORK_FIELDS = ("employment_start", "employment_end", "hours_per_week", "teer")


def decide_work(ctx: DecisionContext) -> DecisionResult:
    """Aggregate ALL audit-eligible work periods across documents (SC5).

    Groups the eligible ``employment_*`` / ``hours_per_week`` / ``teer`` values per
    backing document, calls ``crs_audit.aggregate_work`` (no over-count, no
    overlap double-count, TEER / hours from grounded rows), and compares the
    aggregated years to the claim. A set of individually-valid letters that
    aggregate below the claim → GAP; missing evidence → GAP; a period with no
    TEER (unresolvable skill level) → AT-RISK; otherwise SUBSTANTIATED.
    """
    confirmed = _confirmed_snapshot(ctx.by_field)
    claimed_years = _claimed_years(ctx.factor)

    per_doc: dict[str, dict] = {}
    for value in ctx.eligible_values:
        if value.field_name in _WORK_FIELDS:
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

    # A tiny tolerance so a whole-year claim is not tripped by day-rounding.
    if claimed_years is not None and years + 0.01 < claimed_years:
        return DecisionResult("GAP", "below_threshold",
                              claimed_value=claimed_years, confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          claimed_value=claimed_years, confirmed_value=confirmed)


register("core.age", decide_age)
register("core.education", decide_education)
register("core.work", decide_work)
register("core.language.first", decide_first_language)
register("core.language.second", decide_second_language)
