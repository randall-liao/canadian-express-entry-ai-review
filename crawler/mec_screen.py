"""MEC structural manifest, gate preparation, and conservative status rollup."""

from __future__ import annotations

import re
import json
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Literal

from pydantic import ValidationError

from crawler import auditor, crs_audit, crs_rules, snapshot_policy
from crawler.models.crs_rules import Registry, RuleRow
from crawler.models.mec import (
    MecCounts,
    MecCriterionId,
    PrivateMecCriterion,
    PrivateMecReport,
    Program,
    ProgramStatus,
    PublicMecSummary,
    SCREENING_NOTICE,
    to_public_mec_summary,
)
from crawler.mecfields import (
    MEC_TRADE_JURISDICTIONS,
    EmploymentPeriod,
    MecEvidence,
    employment_periods,
)


@dataclass(frozen=True)
class MecCriterionSpec:
    """Policy-value-free structural wiring for one program criterion."""

    criterion_id: MecCriterionId
    rule_ids: tuple[str, ...]
    applicability_predicate: str | None = None


class MecGatePreparationError(RuntimeError):
    """Stable failure for invalid configuration or non-exact MEC row wiring."""


@dataclass(frozen=True)
class MecRowUsability:
    """Effectivity/freshness state for one already-grounded selected row."""

    row: RuleRow
    usable: bool
    reason: str


@dataclass(frozen=True)
class MecGateContext:
    """One exact program subset bound to its caller-owned registry snapshot."""

    registry_snapshot: crs_rules.RegistrySnapshot
    registry_fingerprint: str
    selected_rows: tuple[RuleRow, ...]
    reference_date: Any
    max_age_days: int
    row_usability: tuple[MecRowUsability, ...]
    operational_as_of: Any = None


@dataclass(frozen=True)
class MecOfferValidation:
    """Private typed program-offer decision; never part of the public projection."""

    status: Literal["PASS", "FAIL", "AT-RISK"]
    program: Program
    selected_noc: str | None
    reason: Literal[
        "grounded_offer_satisfied",
        "grounded_offer_failed",
        "offer_evidence_missing",
        "offer_rule_unavailable",
        "officer_determination_unavailable",
    ]
    rule_ids: tuple[str, ...]
    selected_branch: str | None = None
    evidence_fields: tuple[str, ...] = ()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    """Copy frozen input containers into JSON-safe private report values."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set | frozenset):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ConfirmedMecInputs:
    """Already-confirmed non-MEC card inputs, never CRS conclusions or totals."""

    language: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    education: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    age_years: int | None = None
    adaptability_labels: tuple[str, ...] = ()
    sidecars: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "language", _freeze(self.language))
        object.__setattr__(self, "education", _freeze(self.education))
        object.__setattr__(
            self, "adaptability_labels", tuple(self.adaptability_labels)
        )
        object.__setattr__(self, "sidecars", _freeze(self.sidecars))

    def with_updates(self, **updates: Any) -> "ConfirmedMecInputs":
        return replace(self, **updates)


def _substantiated_card_values(card: Any) -> Mapping[str, Any] | None:
    """Return only the private values behind a grounded green audit card."""
    if card.verdict != "SUBSTANTIATED" or not isinstance(
        card.confirmed_value, Mapping
    ):
        return None
    return card.confirmed_value


def _card_language(card: Any) -> dict[str, Any] | None:
    values = _substantiated_card_values(card)
    if values is None or not isinstance(values.get("benchmarks"), Mapping):
        return None
    benchmarks = values["benchmarks"]
    abilities = ("listening", "reading", "writing", "speaking")
    if any(
        isinstance(benchmarks.get(ability), bool)
        or not isinstance(benchmarks.get(ability), int)
        for ability in abilities
    ):
        return None
    test_date = values.get("test_date")
    if _reference_date(test_date) is None:
        return None
    return {
        "test_date": str(test_date)[:10],
        **{
            f"clb_{ability}": benchmarks[ability]
            for ability in abilities
        },
    }


def _entry_number(row: RuleRow, label: str) -> float | None:
    """Read the first numeric prerequisite from a grounded labelled entry."""
    entry = next(
        (
            item
            for item in row.machine_check.points_by_level or []
            if item.label == label
        ),
        None,
    )
    if entry is None:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(entry.level))
    return float(match.group()) if match else None


def _validate_mec_offer(
    program: Program,
    row: RuleRow,
    evidence: MecEvidence,
    reference: date | None,
    *,
    selected_nocs: Iterable[str] = (),
) -> MecOfferValidation:
    """Evaluate a grounded offer branch without consulting the CRS sidecar."""
    branches = tuple(row.machine_check.branches or ())
    if not branches and row.rule_id in {
        "fsw.grid.arranged_employment",
        "fst.offer_or_certificate",
    }:
        return MecOfferValidation(
            status="AT-RISK",
            program=program,
            selected_noc=None,
            reason="officer_determination_unavailable",
            rule_ids=(row.rule_id,),
            evidence_fields=tuple(
                sorted(
                    name
                    for name in evidence.scalars
                    if name.startswith("offer_")
                    and name != "offer_certificate_scope_complete"
                )
            ),
        )
    selected = frozenset(str(value) for value in selected_nocs)
    branch_results: list[bool | None] = []
    for branch in branches:
        facts: list[bool | None] = []
        branch_noc: str | None = None
        for requirement in branch.requirements:
            value = evidence.value(requirement.field)
            if (
                value is None
                or requirement.field in evidence.conflicts
                or (
                    requirement.operator
                    in {"on_or_before_reference", "on_or_after_reference"}
                    and reference is None
                )
            ):
                facts.append(None)
                continue
            if requirement.operator == "present":
                facts.append(True)
            elif requirement.operator == "equals":
                facts.append(value == requirement.value)
            elif requirement.operator == "minimum":
                facts.append(
                    isinstance(value, int | float)
                    and not isinstance(value, bool)
                    and isinstance(requirement.value, int)
                    and value >= requirement.value
                )
            elif requirement.operator == "maximum":
                facts.append(
                    isinstance(value, int | float)
                    and not isinstance(value, bool)
                    and isinstance(requirement.value, int)
                    and value <= requirement.value
                )
            elif requirement.operator == "in":
                facts.append(
                    isinstance(requirement.value, list)
                    and value in requirement.value
                )
            elif requirement.operator == "matches_selected_noc":
                match = str(value) in selected if selected else None
                facts.append(match)
                if match:
                    branch_noc = str(value)
            else:
                fact_date = _reference_date(value)
                if fact_date is None or reference is None:
                    facts.append(None)
                elif requirement.operator == "on_or_before_reference":
                    facts.append(fact_date <= reference)
                else:
                    facts.append(fact_date >= reference)
        if facts and all(fact is True for fact in facts):
            if branch_noc is None:
                offered_noc = evidence.value("offer_noc_code")
                branch_noc = str(offered_noc) if offered_noc is not None else None
            return MecOfferValidation(
                status="PASS",
                program=program,
                selected_noc=branch_noc,
                reason="grounded_offer_satisfied",
                rule_ids=(row.rule_id,),
                selected_branch=branch.label,
                evidence_fields=tuple(
                    dict.fromkeys(
                        requirement.field for requirement in branch.requirements
                    )
                ),
            )
        elif any(fact is False for fact in facts):
            branch_results.append(False)
        else:
            branch_results.append(None)

    if branch_results and all(result is False for result in branch_results):
        return MecOfferValidation(
            status="FAIL",
            program=program,
            selected_noc=None,
            reason="grounded_offer_failed",
            rule_ids=(row.rule_id,),
        )
    return MecOfferValidation(
        status="AT-RISK",
        program=program,
        selected_noc=None,
        reason=(
            "offer_evidence_missing" if branches else "offer_rule_unavailable"
        ),
        rule_ids=(row.rule_id,) if branches else (),
    )


def build_confirmed_mec_inputs(
    program: Program,
    context: MecGateContext,
    evidence: MecEvidence,
    vault_: Any,
    db: Any,
) -> ConfirmedMecInputs:
    """Adapt five-key-eligible grounded cards and MEC evidence for real screening.

    No extraction value is read here directly.  Standard applicant values cross
    the existing audit-card gate, while offer/exemption inputs come only from the
    already candidate-scoped MEC envelope bound to this snapshot fingerprint.
    """
    from crawler import auditors
    from crawler import vault as vault_module

    if evidence.registry_fingerprint != context.registry_fingerprint:
        raise MecGatePreparationError("MEC evidence fingerprint mismatch")
    auditors.load_all()
    profile_factors = {
        item.factor_id: item for item in vault_module.load_profile_factors(vault_)
    }
    spouse_mode = auditors.spouse.determine_spouse_mode(
        vault_, list(profile_factors.values())
    )
    reference = _reference_date(context.reference_date)
    if reference is None:
        raise MecGatePreparationError("MEC reference date unavailable")
    factor_ids = (
        "core.language.first",
        "core.language.second",
        "core.age",
        "core.education",
        "core.work",
        "spouse.language",
        "spouse.work",
        "additional.sibling",
    )
    cards = {
        factor_id: auditor.audit_one(
            vault_,
            factor_id,
            db,
            context.registry_snapshot.registry,
            spouse_mode=spouse_mode,
            reference_date=reference.isoformat(),
            ita_date=reference.isoformat(),
            prior_cards={},
            registry_fingerprint=context.registry_fingerprint,
            profile_factors=profile_factors,
        )
        for factor_id in factor_ids
    }

    language = {}
    for branch, factor_id in (
        ("first", "core.language.first"),
        ("second", "core.language.second"),
    ):
        adapted = _card_language(cards[factor_id])
        if adapted is not None:
            language[branch] = adapted

    education = {}
    education_values = _substantiated_card_values(cards["core.education"])
    if education_values is not None:
        level = education_values.get("credential_level")
        education_row = next(
            (
                item.row
                for item in context.row_usability
                if item.row.rule_id == "fsw.education.minimum" and item.usable
            ),
            None,
        )
        if level is not None:
            education["level"] = level
        branch = evidence.value("fsw_education_branch")
        accepted = {
            item.value
            for item in (
                education_row.machine_check.applicability
                if education_row is not None
                else []
            ) or []
        }
        if branch in accepted:
            education["branch"] = branch

    age_values = _substantiated_card_values(cards["core.age"])
    age_years = age_values.get("age_on_ita") if age_values is not None else None
    if isinstance(age_years, bool) or not isinstance(age_years, int):
        age_years = None

    adaptability: set[str] = set()
    adaptability_row = next(
        (
            item.row
            for item in context.row_usability
            if item.row.rule_id == "fsw.grid.adaptability" and item.usable
        ),
        None,
    )
    if adaptability_row is not None:
        spouse_language = _substantiated_card_values(cards["spouse.language"])
        spouse_minimum = _entry_number(adaptability_row, "spouse_language")
        spouse_benchmarks = (
            spouse_language.get("benchmarks")
            if spouse_language is not None
            else None
        )
        if (
            spouse_minimum is not None
            and isinstance(spouse_benchmarks, Mapping)
            and spouse_benchmarks
            and all(
                isinstance(value, int)
                and not isinstance(value, bool)
                and value >= spouse_minimum
                for value in spouse_benchmarks.values()
            )
        ):
            adaptability.add("spouse_language")
        for factor_id, label in (
            ("core.work", "applicant_work"),
            ("spouse.work", "spouse_work"),
        ):
            work = _substantiated_card_values(cards[factor_id])
            minimum = _entry_number(adaptability_row, label)
            years = work.get("aggregated_years") if work is not None else None
            if (
                minimum is not None
                and isinstance(years, int | float)
                and not isinstance(years, bool)
                and years >= minimum
            ):
                adaptability.add(label)
        if _substantiated_card_values(cards["additional.sibling"]) is not None:
            adaptability.add("relative")
    return ConfirmedMecInputs(
        language=language,
        education=education,
        age_years=age_years,
        adaptability_labels=tuple(sorted(adaptability)),
    )


def _spec(
    criterion_id: MecCriterionId,
    *,
    applicability_predicate: str | None = None,
) -> MecCriterionSpec:
    return MecCriterionSpec(
        criterion_id=criterion_id,
        rule_ids=(criterion_id,),
        applicability_predicate=applicability_predicate,
    )


# Structural IDs and applicability branch names only.  All policy values remain
# in grounded registry rows.  The tuple order is the canonical report order.
MEC_PROGRAM_CRITERIA: Mapping[Program, tuple[MecCriterionSpec, ...]] = (
    MappingProxyType(
        {
            "fsw": tuple(
                _spec(
                    criterion_id,
                    applicability_predicate=(
                        "funds_exemption"
                        if criterion_id == "fsw.funds.requirement"
                        else None
                    ),
                )
                for criterion_id in crs_rules.REQUIRED_MEC_RULE_IDS["fsw"]
            ),
            "fst": tuple(
                _spec(
                    criterion_id,
                    applicability_predicate=(
                        "funds_exemption"
                        if criterion_id == "fst.funds.requirement"
                        else "offer_or_certificate_alternative"
                        if criterion_id == "fst.offer_or_certificate"
                        else None
                    ),
                )
                for criterion_id in crs_rules.REQUIRED_MEC_RULE_IDS["fst"]
            ),
            "cec": tuple(
                _spec(criterion_id)
                for criterion_id in crs_rules.REQUIRED_MEC_RULE_IDS["cec"]
            ),
        }
    )
)


def prepare_mec_gate(
    program: str,
    registry_snapshot: crs_rules.RegistrySnapshot,
    db: Any,
    reference_date: Any,
    max_age_days: int,
    *,
    as_of: Any = None,
) -> MecGateContext:
    """Select and ground one exact program subset without loading registry state.

    ``registry_snapshot`` and its fingerprint are retained verbatim.  This
    function never reads YAML and never recomputes a fingerprint.  Every selected
    row crosses the one shared :func:`crawler.auditor.gate_subset`
    implementation, then receives both an effectivity and operational freshness
    observation.
    """
    specs = MEC_PROGRAM_CRITERIA.get(program)  # type: ignore[arg-type]
    if (
        specs is None
        or not isinstance(registry_snapshot, crs_rules.RegistrySnapshot)
        or reference_date is None
        or isinstance(max_age_days, bool)
        or not isinstance(max_age_days, int)
        or max_age_days <= 0
    ):
        raise MecGatePreparationError("MEC gate configuration unavailable")
    operational_as_of = as_of if as_of is not None else date.today()
    if _reference_date(operational_as_of) is None:
        raise MecGatePreparationError("MEC operational as-of date unavailable")

    expected = tuple(
        rule_id for spec in specs for rule_id in spec.rule_ids
    )
    expected_set = set(expected)
    selected: list[RuleRow] = []
    for rule_id in expected:
        matches = [
            row for row in registry_snapshot.registry.rows
            if row.rule_id == rule_id
        ]
        if (
            len(matches) != 1
            or matches[0].gap
            or matches[0].factor_group != "program_eligibility"
            or rule_id not in matches[0].factor_ids
        ):
            raise MecGatePreparationError("MEC criterion manifest is not exactly wired")
        selected.append(matches[0])

    # A program-eligibility row in this program namespace that is absent from the
    # structural manifest is unknown wiring, not an ignorable extension.
    unknown = [
        row.rule_id
        for row in registry_snapshot.registry.rows
        if row.factor_group == "program_eligibility"
        and row.rule_id.startswith(f"{program}.")
        and row.rule_id not in expected_set
    ]
    if unknown or len(selected) != len(set(expected)):
        raise MecGatePreparationError("MEC criterion manifest is not exactly wired")

    subset = Registry(rows=selected)
    auditor.gate_subset(subset, db)

    usability: list[MecRowUsability] = []
    for row in selected:
        try:
            in_effect = crs_audit.row_in_effect(row, reference_date)
        except (TypeError, ValueError):
            in_effect = False
        fresh = snapshot_policy.mec_rule_row_is_fresh(
            row, operational_as_of, max_age_days
        )
        if not in_effect:
            reason = "rule_out_of_window"
        elif not fresh:
            reason = "rule_stale"
        else:
            reason = "usable"
        usability.append(
            MecRowUsability(row=row, usable=in_effect and fresh, reason=reason)
        )

    return MecGateContext(
        registry_snapshot=registry_snapshot,
        registry_fingerprint=registry_snapshot.fingerprint,
        selected_rows=tuple(selected),
        reference_date=reference_date,
        max_age_days=max_age_days,
        row_usability=tuple(usability),
        operational_as_of=operational_as_of,
    )


def _as_private_criterion(value: Any) -> PrivateMecCriterion | None:
    if isinstance(value, PrivateMecCriterion):
        try:
            return PrivateMecCriterion.model_validate(
                value.model_dump(mode="json")
            )
        except ValidationError:
            return None
    if isinstance(value, Mapping):
        try:
            return PrivateMecCriterion.model_validate(dict(value))
        except ValidationError:
            return None
    return None


def rollup_program_status(
    program: str,
    criteria: Iterable[PrivateMecCriterion | Mapping[str, Any]],
) -> ProgramStatus:
    """Return the canonical FAIL-first outcome, failing unknown states closed.

    Manifest defects are recorded as unresolved rather than raised.  A valid
    deterministic ``FAIL`` still controls over unrelated unresolved input;
    otherwise any malformed, unknown, missing, duplicate, unwired, or invalid
    N/A input produces ``AT-RISK``.
    """
    specs = MEC_PROGRAM_CRITERIA.get(program)  # type: ignore[arg-type]
    if specs is None:
        return "AT-RISK"

    by_id = {spec.criterion_id: spec for spec in specs}
    seen: set[str] = set()
    has_confirmed_fail = False
    has_unresolved = False

    for raw in criteria:
        criterion = _as_private_criterion(raw)
        if criterion is None:
            has_unresolved = True
            continue

        criterion_id = criterion.criterion_id
        spec = by_id.get(criterion_id)
        if spec is None:
            has_unresolved = True
            continue
        if criterion_id in seen:
            has_unresolved = True
        seen.add(criterion_id)

        if not criterion.wired or tuple(criterion.rule_ids) != spec.rule_ids:
            has_unresolved = True
            continue

        if criterion.status == "FAIL":
            valid_fail = (
                criterion.reason_code == "confirmed_deterministic_failure"
                and criterion.wired
                and criterion.applicability_grounded
                and criterion.applicable is True
            )
            if valid_fail:
                has_confirmed_fail = True
            else:
                has_unresolved = True
        elif criterion.status == "AT-RISK":
            has_unresolved = True
        elif criterion.status == "N/A":
            valid_na = (
                spec.applicability_predicate is not None
                and criterion.applicability_grounded
                and criterion.applicable is False
            )
            if not valid_na:
                has_unresolved = True
        elif criterion.status == "PASS":
            valid_pass = (
                criterion.reason_code == "criterion_satisfied"
                and criterion.wired
                and criterion.grounded
                and criterion.applicability_grounded
                and criterion.applicable is True
                and tuple(criterion.rule_ids) == spec.rule_ids
            )
            if not valid_pass:
                has_unresolved = True
        else:
            has_unresolved = True

    if seen != set(by_id):
        has_unresolved = True

    if has_confirmed_fail:
        return "DOES-NOT-MEET"
    # This milestone cannot resolve the officer-only FSW arranged-employment
    # determination, so even a forged all-PASS criterion collection is not MEETS.
    if program == "fsw":
        return "AT-RISK"
    if has_unresolved:
        return "AT-RISK"
    return "MEETS"


def _context_rows(context: MecGateContext) -> dict[str, MecRowUsability]:
    return {item.row.rule_id: item for item in context.row_usability}


def _citation_ids(row: RuleRow) -> list[str]:
    return [citation.chunk_id for citation in row.citations]


def _private_result(
    spec: MecCriterionSpec,
    row_state: MecRowUsability,
    status: str,
    reason_code: str,
    *,
    applicant_values: Mapping[str, Any] | None = None,
    evidence_ids: Iterable[str] = (),
    employment_traces: Iterable[Mapping[str, Any]] = (),
    sidecar_inputs: Mapping[str, Any] | None = None,
    grid_bounds: Mapping[str, Any] | None = None,
    completeness: Mapping[str, bool] | None = None,
    applicability_grounded: bool = False,
    applicable: bool | None = None,
) -> PrivateMecCriterion:
    if status in {"PASS", "FAIL"}:
        applicability_grounded = True
        applicable = True
    return PrivateMecCriterion(
        criterion_id=spec.criterion_id,
        status=status,
        reason_code=reason_code,
        corpus_citation_ids=_citation_ids(row_state.row),
        wired=True,
        grounded=row_state.usable,
        applicability_grounded=applicability_grounded,
        applicable=applicable,
        rule_ids=list(spec.rule_ids),
        applicant_values=_plain(applicant_values or {}),
        evidence_ids=sorted(set(evidence_ids)),
        employment_traces=[_plain(trace) for trace in employment_traces],
        sidecar_inputs=_plain(sidecar_inputs or {}),
        grid_bounds=_plain(grid_bounds or {}),
        completeness_attestations=_plain(completeness or {}),
        render_details={
            "rule_usability": row_state.reason,
            "registry_fingerprint": None,
        },
    )


def _unusable_result(
    spec: MecCriterionSpec, row_state: MecRowUsability
) -> PrivateMecCriterion:
    reason = (
        row_state.reason
        if row_state.reason in {"rule_stale", "rule_out_of_window"}
        else "rule_unavailable"
    )
    return _private_result(spec, row_state, "AT-RISK", reason)


def _apply_prerequisite_usability(
    specs: tuple[MecCriterionSpec, ...],
    states: Mapping[str, MecRowUsability],
    results: dict[str, PrivateMecCriterion],
    dependencies: Mapping[str, tuple[str, ...]],
) -> None:
    """Demote criteria whose rule or fact-selection prerequisites are unresolved."""
    by_id = {spec.criterion_id: spec for spec in specs}
    for criterion_id, required_ids in dependencies.items():
        unresolved_state = None
        unresolved_result = None
        for rule_id in required_ids:
            candidate = states.get(rule_id)
            if candidate is None or not candidate.usable:
                unresolved_state = candidate
                break
            candidate_result = results.get(rule_id)
            if candidate_result is None or candidate_result.status == "AT-RISK":
                unresolved_result = candidate_result
                break
        if unresolved_state is None and unresolved_result is None:
            continue
        if unresolved_result is not None:
            reason = unresolved_result.reason_code
        else:
            reason = (
                unresolved_state.reason
                if unresolved_state is not None
                and unresolved_state.reason in {"rule_stale", "rule_out_of_window"}
                else "rule_unavailable"
            )
        own_state = states.get(criterion_id)
        spec = by_id.get(criterion_id)
        if own_state is None or spec is None:
            continue
        if (
            unresolved_state is None
            and results.get(criterion_id) is not None
            and results[criterion_id].status == "AT-RISK"
        ):
            continue
        results[criterion_id] = _private_result(
            spec,
            own_state,
            "AT-RISK",
            reason,
        )


def _period_trace(period: EmploymentPeriod, included: bool, reason: str) -> dict[str, Any]:
    return {
        "employment_period_id": period.employment_period_id,
        "included": included,
        "reason": reason,
    }


def _period_has(period: EmploymentPeriod, *fields: str) -> bool:
    return period.usable and all(name in period.values for name in fields)


def _policy_value(value: Any) -> Any:
    return value.value if value is not None else None


def _reference_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _years_before(reference: date, years: int) -> date:
    try:
        return reference.replace(year=reference.year - years)
    except ValueError:
        return reference.replace(month=2, day=28, year=reference.year - years)


def _in_lookback(end_value: Any, reference: date | None, years: Any) -> bool | None:
    if reference is None or isinstance(years, bool) or not isinstance(years, int):
        return None
    try:
        ended = date.fromisoformat(str(end_value))
    except ValueError:
        return None
    return _years_before(reference, years) <= ended <= reference


def _interval_in_lookback(
    start_value: Any,
    end_value: Any,
    reference: date | None,
    years: Any,
) -> bool | None:
    """Return whether a valid employment interval overlaps the exact lookback."""
    if reference is None or isinstance(years, bool) or not isinstance(years, int):
        return None
    try:
        start = date.fromisoformat(str(start_value))
        end = date.fromisoformat(str(end_value))
    except ValueError:
        return None
    if end < start:
        return None
    return max(start, _years_before(reference, years)) <= min(end, reference)


def _hierarchy_numbers(row: RuleRow) -> set[int]:
    values = row.machine_check.included_hierarchy or []
    numbers: set[int] = set()
    for item in values:
        match = re.search(r"\d+", str(item.value))
        if match:
            numbers.add(int(match.group()))
    return numbers


def _all_card_levels(language: Mapping[str, Any], branch: str) -> list[int] | None:
    raw = language.get(branch)
    if not isinstance(raw, Mapping):
        return None
    names = ("clb_listening", "clb_reading", "clb_writing", "clb_speaking")
    values = [raw.get(name) for name in names]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return None
    return values  # type: ignore[return-value]


def _language_current(
    language: Mapping[str, Any], branch: str, row: RuleRow, reference: date | None
) -> bool | None:
    raw = language.get(branch)
    if not isinstance(raw, Mapping):
        return None
    years = _policy_value(row.machine_check.lookback_years)
    return _in_lookback(raw.get("test_date"), reference, years)


def _points_for_level(row: RuleRow, level: Any) -> int | None:
    for entry in row.machine_check.points_by_level or []:
        if entry.level == level and entry.points is not None:
            return entry.points
    return None


def _points_for_years(row: RuleRow, years: int) -> int | None:
    """Price only completed calendar-equivalent years from validated periods."""
    if isinstance(years, bool) or not isinstance(years, int) or years < 0:
        return None
    matches = []
    for entry in row.machine_check.points_by_level or []:
        if entry.points is None or entry.years_min is None:
            continue
        if years < entry.years_min:
            continue
        if entry.years_max is not None and years > entry.years_max:
            continue
        matches.append(entry.points)
    return max(matches) if matches else None


def _grid_result(
    spec: MecCriterionSpec,
    row_state: MecRowUsability,
    points: int | None,
    *,
    reason: str = "evidence_missing",
    evidence_ids: Iterable[str] = (),
    sidecar_inputs: Mapping[str, Any] | None = None,
) -> PrivateMecCriterion:
    cap = row_state.row.machine_check.cap_value
    if cap is None:
        table_points = [
            entry.points
            for entry in row_state.row.machine_check.points_by_level or []
            if entry.points is not None
        ]
        cap = max(table_points) if table_points else 0
    if points is None:
        return _private_result(
            spec,
            row_state,
            "AT-RISK",
            reason,
            evidence_ids=evidence_ids,
            sidecar_inputs=sidecar_inputs,
            grid_bounds={"lower": 0, "upper": cap},
        )
    return _private_result(
        spec,
        row_state,
        "PASS",
        "criterion_satisfied",
        applicant_values={"points": points},
        evidence_ids=evidence_ids,
        sidecar_inputs=sidecar_inputs,
        grid_bounds={"lower": points, "upper": points},
    )


def _scope_complete(evidence: MecEvidence, field_name: str) -> bool:
    declared_complete = (
        evidence.value(field_name) is True and field_name not in evidence.conflicts
    )
    if field_name == "work_history_scope_complete":
        return declared_complete and not evidence.has_period_scope_issue
    return declared_complete


def _evidence_ids(evidence: MecEvidence, *fields: str) -> tuple[str, ...]:
    return tuple(
        value_id
        for name in fields
        for value_id in evidence.scalar_evidence_ids.get(name, ())
    )


def evaluate_fsw(
    context: MecGateContext,
    evidence: MecEvidence,
    confirmed_inputs: ConfirmedMecInputs,
) -> tuple[PrivateMecCriterion, ...]:
    """Evaluate the exact FSW manifest from usable rows and period-safe evidence."""
    if evidence.registry_fingerprint != context.registry_fingerprint:
        raise MecGatePreparationError("MEC evidence fingerprint mismatch")
    specs = MEC_PROGRAM_CRITERIA["fsw"]
    states = _context_rows(context)
    reference = _reference_date(context.reference_date)
    periods = evidence.periods
    complete_work = _scope_complete(evidence, "work_history_scope_complete")
    primary_noc = evidence.value("primary_noc_code")
    results: dict[str, PrivateMecCriterion] = {}

    def state_for(spec: MecCriterionSpec) -> MecRowUsability:
        state = states.get(spec.criterion_id)
        if state is None:
            raise MecGatePreparationError("MEC criterion manifest is not exactly wired")
        return state

    def add(
        criterion_id: str,
        status: str,
        reason: str,
        *,
        matching_periods: Iterable[EmploymentPeriod] = (),
        completeness: Mapping[str, bool] | None = None,
    ) -> None:
        spec = next(item for item in specs if item.criterion_id == criterion_id)
        state = state_for(spec)
        if not state.usable:
            results[criterion_id] = _unusable_result(spec, state)
            return
        chosen = tuple(matching_periods)
        results[criterion_id] = _private_result(
            spec,
            state,
            status,
            reason,
            evidence_ids=(
                *(_evidence_ids(evidence, "primary_noc_code")),
                *(value_id for period in chosen for value_id in period.evidence_ids),
            ),
            employment_traces=(
                _period_trace(
                    period,
                    period in chosen,
                    "predicate_satisfied" if period in chosen else "predicate_excluded",
                )
                for period in periods
            ),
            completeness=completeness,
        )

    primary_known = [
        period for period in periods if _period_has(period, "noc_code")
    ]
    primary_matches = [
        period for period in primary_known
        if primary_noc is not None and period.values["noc_code"] == primary_noc
    ]
    if primary_noc is None or not primary_known:
        add("fsw.work.primary_noc", "AT-RISK", "evidence_missing")
    elif primary_matches:
        add(
            "fsw.work.primary_noc", "PASS", "criterion_satisfied",
            matching_periods=primary_matches,
        )
    elif complete_work and len(primary_known) == len(periods):
        add(
            "fsw.work.primary_noc", "FAIL", "confirmed_deterministic_failure",
            completeness={"work": True},
        )
    else:
        add(
            "fsw.work.primary_noc", "AT-RISK", "scope_incomplete",
            completeness={"work": False},
        )

    teer_spec = next(item for item in specs if item.criterion_id == "fsw.work.teer")
    teer_state = state_for(teer_spec)
    allowed_teers = _hierarchy_numbers(teer_state.row)
    teer_known = [
        period for period in primary_matches if _period_has(period, "teer")
    ]
    skilled = [
        period for period in teer_known if period.values["teer"] in allowed_teers
    ]
    if not teer_state.usable:
        results[teer_spec.criterion_id] = _unusable_result(teer_spec, teer_state)
    elif skilled:
        add("fsw.work.teer", "PASS", "criterion_satisfied", matching_periods=skilled)
    elif complete_work and primary_matches and len(teer_known) == len(primary_matches):
        add("fsw.work.teer", "FAIL", "confirmed_deterministic_failure")
    else:
        add("fsw.work.teer", "AT-RISK", "evidence_missing")

    paid_known = [
        period for period in skilled if _period_has(period, "paid_status")
    ]
    paid = [period for period in paid_known if period.values["paid_status"] is True]
    if paid:
        add("fsw.work.paid", "PASS", "criterion_satisfied", matching_periods=paid)
    elif complete_work and skilled and len(paid_known) == len(skilled):
        add("fsw.work.paid", "FAIL", "confirmed_deterministic_failure")
    else:
        add("fsw.work.paid", "AT-RISK", "evidence_missing")

    recency_spec = next(
        item for item in specs if item.criterion_id == "fsw.work.recency"
    )
    recency_state = state_for(recency_spec)
    lookback = _policy_value(recency_state.row.machine_check.lookback_years)
    recent_known = [
        (
            period,
            _interval_in_lookback(
                period.values.get("employment_start"),
                period.values.get("employment_end"),
                reference,
                lookback,
            ),
        )
        for period in paid
    ]
    recent = [period for period, state in recent_known if state is True]
    if not recency_state.usable:
        results[recency_spec.criterion_id] = _unusable_result(
            recency_spec, recency_state
        )
    elif recent:
        add("fsw.work.recency", "PASS", "criterion_satisfied", matching_periods=recent)
    elif complete_work and paid and all(state is False for _, state in recent_known):
        add("fsw.work.recency", "FAIL", "confirmed_deterministic_failure")
    else:
        add("fsw.work.recency", "AT-RISK", "evidence_missing")

    duration_spec = next(
        item for item in specs
        if item.criterion_id == "fsw.work.continuity_duration_hours"
    )
    duration_state = state_for(duration_spec)
    check = duration_state.row.machine_check
    min_months = _policy_value(check.minimum_duration_months)
    min_hours = _policy_value(check.minimum_hours)
    duration_known = [
        period
        for period in recent
        if _period_has(
            period,
            "employment_continuous",
            "employment_start",
            "employment_end",
            "duration_months",
            "total_hours",
            "hours_per_week",
        )
    ]
    duration_matches = []
    duration_resolved = len(duration_known) == len(recent)
    for period in duration_known:
        aggregates, resolved = _aggregate_periods(
            (period,),
            duration_state.row,
            separate_noc=False,
            reference=reference,
            lookback_years=lookback,
        )
        duration_resolved = duration_resolved and resolved
        aggregate = aggregates.get("*")
        if (
            aggregate is not None
            and period.values["employment_continuous"] is True
            and aggregate[0] >= min_months
            and aggregate[1] >= min_hours
        ):
            duration_matches.append(period)
    if not duration_state.usable:
        results[duration_spec.criterion_id] = _unusable_result(
            duration_spec, duration_state
        )
    elif duration_matches:
        add(
            duration_spec.criterion_id,
            "PASS",
            "criterion_satisfied",
            matching_periods=duration_matches,
        )
    elif complete_work and recent and duration_resolved:
        add(
            duration_spec.criterion_id,
            "FAIL",
            "confirmed_deterministic_failure",
        )
    else:
        add(duration_spec.criterion_id, "AT-RISK", "evidence_missing")

    noc_spec = next(
        item for item in specs if item.criterion_id == "fsw.work.noc_duties"
    )
    noc_state = state_for(noc_spec)
    results[noc_spec.criterion_id] = (
        _unusable_result(noc_spec, noc_state)
        if not noc_state.usable
        else _private_result(
            noc_spec,
            noc_state,
            "AT-RISK",
            "manual_noc_review" if primary_matches else "evidence_missing",
            employment_traces=(
                _period_trace(period, period in primary_matches, "noc_sidecar_manual")
                for period in periods
            ),
            sidecar_inputs={"noc": confirmed_inputs.sidecars.get("noc", {})},
        )
    )

    language_spec = next(
        item for item in specs if item.criterion_id == "fsw.language.first"
    )
    language_state = state_for(language_spec)
    levels = _all_card_levels(confirmed_inputs.language, "first")
    language_minima = _hierarchy_numbers(language_state.row)
    minimum_level = min(language_minima) if language_minima else None
    current = _language_current(
        confirmed_inputs.language, "first", language_state.row, reference
    )
    if not language_state.usable:
        results[language_spec.criterion_id] = _unusable_result(
            language_spec, language_state
        )
    elif levels is None or current is None or minimum_level is None:
        results[language_spec.criterion_id] = _private_result(
            language_spec, language_state, "AT-RISK", "evidence_missing"
        )
    elif current is False or any(level < minimum_level for level in levels):
        results[language_spec.criterion_id] = _private_result(
            language_spec,
            language_state,
            "FAIL",
            "confirmed_deterministic_failure",
        )
    else:
        results[language_spec.criterion_id] = _private_result(
            language_spec, language_state, "PASS", "criterion_satisfied"
        )

    education_spec = next(
        item for item in specs if item.criterion_id == "fsw.education.minimum"
    )
    education_state = state_for(education_spec)
    branch = confirmed_inputs.education.get("branch")
    accepted_branches = {
        item.value for item in education_state.row.machine_check.applicability or []
    }
    if not education_state.usable:
        results[education_spec.criterion_id] = _unusable_result(
            education_spec, education_state
        )
    elif branch is None:
        results[education_spec.criterion_id] = _private_result(
            education_spec, education_state, "AT-RISK", "evidence_missing"
        )
    elif branch in accepted_branches:
        results[education_spec.criterion_id] = _private_result(
            education_spec, education_state, "PASS", "criterion_satisfied"
        )
    else:
        results[education_spec.criterion_id] = _private_result(
            education_spec,
            education_state,
            "FAIL",
            "confirmed_deterministic_failure",
        )

    # Six selection factors.  Unknown factors retain registry-derived bounds.
    language_grid_spec = next(
        item for item in specs if item.criterion_id == "fsw.grid.language"
    )
    language_grid_state = state_for(language_grid_spec)
    language_points: int | None = None
    if levels is not None and current is True:
        first_entries = [
            entry for entry in language_grid_state.row.machine_check.points_by_level or []
            if entry.label == "first_per_ability"
            and isinstance(entry.level, int)
            and entry.points is not None
        ]
        points = []
        for level in levels:
            eligible = [entry.points for entry in first_entries if level >= entry.level]
            if not eligible:
                break
            points.append(max(eligible))
        if len(points) == len(levels):
            language_points = sum(points)
            second = _all_card_levels(confirmed_inputs.language, "second")
            second_entries = [
                entry for entry in language_grid_state.row.machine_check.points_by_level or []
                if entry.label == "second_all_abilities"
                and isinstance(entry.level, int)
                and entry.points is not None
            ]
            if second and second_entries:
                eligible = [
                    entry.points for entry in second_entries
                    if all(level >= entry.level for level in second)
                ]
                if eligible:
                    language_points += max(eligible)
            cap = language_grid_state.row.machine_check.cap_value
            if cap is not None:
                language_points = min(language_points, cap)
    results[language_grid_spec.criterion_id] = (
        _unusable_result(language_grid_spec, language_grid_state)
        if not language_grid_state.usable
        else _grid_result(language_grid_spec, language_grid_state, language_points)
    )

    education_grid_spec = next(
        item for item in specs if item.criterion_id == "fsw.grid.education"
    )
    education_grid_state = state_for(education_grid_spec)
    education_points = _points_for_level(
        education_grid_state.row, confirmed_inputs.education.get("level")
    )
    results[education_grid_spec.criterion_id] = (
        _unusable_result(education_grid_spec, education_grid_state)
        if not education_grid_state.usable
        else _grid_result(
            education_grid_spec, education_grid_state, education_points
        )
    )

    experience_spec = next(
        item for item in specs if item.criterion_id == "fsw.grid.experience"
    )
    experience_state = state_for(experience_spec)
    experience_periods = [
        period
        for period in recent
        if _period_has(
            period,
            "teer",
            "paid_status",
            "employment_start",
            "employment_end",
            "duration_months",
            "total_hours",
            "hours_per_week",
        )
        and period.values["teer"] in allowed_teers
        and period.values["paid_status"] is True
    ]
    experience_points = None
    experience_aggregates, experience_resolved = _aggregate_periods(
        experience_periods,
        duration_state.row,
        separate_noc=False,
        reference=reference,
        lookback_years=lookback,
    )
    if complete_work and experience_resolved and len(experience_periods) == len(recent):
        total_months = experience_aggregates["*"][0]
        experience_points = _points_for_years(
            experience_state.row, int(total_months // 12)
        )
    results[experience_spec.criterion_id] = (
        _unusable_result(experience_spec, experience_state)
        if not experience_state.usable
        else _grid_result(
            experience_spec,
            experience_state,
            experience_points,
            evidence_ids=(
                value_id
                for period in experience_periods
                for value_id in period.evidence_ids
            ),
            reason="scope_incomplete" if not complete_work else "evidence_missing",
        )
    )

    age_spec = next(item for item in specs if item.criterion_id == "fsw.grid.age")
    age_state = state_for(age_spec)
    age_points = None
    age = confirmed_inputs.age_years
    if isinstance(age, int) and not isinstance(age, bool):
        for entry in age_state.row.machine_check.points_by_level or []:
            if entry.points is None:
                continue
            if isinstance(entry.level, int) and age == entry.level:
                age_points = entry.points
            elif entry.label == "age_18_35":
                numbers = [int(item) for item in re.findall(r"\d+", str(entry.level))]
                if len(numbers) == 2 and numbers[0] <= age <= numbers[1]:
                    age_points = entry.points
            elif entry.label == "under_18":
                boundary = min(
                    int(item) for item in re.findall(r"\d+", str(entry.level))
                )
                if age < boundary:
                    age_points = entry.points
            elif entry.label == "age_47_plus":
                boundary = min(
                    int(item) for item in re.findall(r"\d+", str(entry.level))
                )
                if age >= boundary:
                    age_points = entry.points
    results[age_spec.criterion_id] = (
        _unusable_result(age_spec, age_state)
        if not age_state.usable
        else _grid_result(age_spec, age_state, age_points)
    )

    offer_spec = next(
        item for item in specs if item.criterion_id == "fsw.grid.arranged_employment"
    )
    offer_state = state_for(offer_spec)
    offer_validation = (
        _validate_mec_offer(
            "fsw",
            offer_state.row,
            evidence,
            reference,
        )
        if offer_state.usable
        else MecOfferValidation(
            status="AT-RISK",
            program="fsw",
            selected_noc=None,
            reason="offer_rule_unavailable",
            rule_ids=(),
        )
    )
    offer_present = any(
        name.startswith("offer_") and name != "offer_certificate_scope_complete"
        for name in evidence.scalars
    )
    if not offer_state.usable:
        results[offer_spec.criterion_id] = _unusable_result(offer_spec, offer_state)
    else:
        results[offer_spec.criterion_id] = _grid_result(
            offer_spec,
            offer_state,
            None,
            reason="manual_offer_review",
            evidence_ids=_evidence_ids(evidence, *offer_validation.evidence_fields),
            sidecar_inputs={"offer": confirmed_inputs.sidecars.get("offer", {})},
        )

    adaptability_spec = next(
        item for item in specs if item.criterion_id == "fsw.grid.adaptability"
    )
    adaptability_state = state_for(adaptability_spec)
    adaptability_scope = _scope_complete(evidence, "adaptability_scope_complete")
    entries = {
        entry.label: entry.points
        for entry in adaptability_state.row.machine_check.points_by_level or []
        if entry.label and entry.points is not None
    }
    labels = set(confirmed_inputs.adaptability_labels)
    labels.discard("arranged_employment")
    if offer_validation.status == "PASS":
        labels.add("arranged_employment")
    manual_study = bool(labels & {"applicant_study", "spouse_study"})
    adaptability_points = None
    adaptability_reason = (
        "manual_offer_review"
        if offer_present
        else "manual_study_review"
        if manual_study
        else "scope_incomplete"
    )
    if (
        adaptability_scope
        and labels <= set(entries)
        and not manual_study
        and not offer_present
    ):
        adaptability_points = sum(entries[label] for label in labels)
        cap = adaptability_state.row.machine_check.cap_value
        if cap is not None:
            adaptability_points = min(adaptability_points, cap)
    results[adaptability_spec.criterion_id] = (
        _unusable_result(adaptability_spec, adaptability_state)
        if not adaptability_state.usable
        else _grid_result(
            adaptability_spec,
            adaptability_state,
            adaptability_points,
            reason=adaptability_reason,
            sidecar_inputs={"study": confirmed_inputs.sidecars.get("study", {})},
        )
    )

    pass_spec = next(
        item for item in specs if item.criterion_id == "fsw.grid.pass_mark"
    )
    pass_state = state_for(pass_spec)
    factor_ids = (
        "fsw.grid.language",
        "fsw.grid.education",
        "fsw.grid.experience",
        "fsw.grid.age",
        "fsw.grid.arranged_employment",
        "fsw.grid.adaptability",
    )
    lower = sum(results[item].grid_bounds.get("lower", 0) for item in factor_ids)
    upper = sum(results[item].grid_bounds.get("upper", 0) for item in factor_ids)
    minimum = pass_state.row.machine_check.min_value
    maximum = pass_state.row.machine_check.max_value
    if not pass_state.usable or minimum is None:
        results[pass_spec.criterion_id] = (
            _unusable_result(pass_spec, pass_state)
            if not pass_state.usable
            else _private_result(
                pass_spec, pass_state, "AT-RISK", "rule_unavailable"
            )
        )
    elif lower >= minimum:
        results[pass_spec.criterion_id] = _private_result(
            pass_spec,
            pass_state,
            "PASS",
            "criterion_satisfied",
            grid_bounds={"lower": lower, "upper": upper, "maximum": maximum},
        )
    elif upper < minimum and all(
        results[item].status == "PASS" for item in factor_ids
    ):
        results[pass_spec.criterion_id] = _private_result(
            pass_spec,
            pass_state,
            "FAIL",
            "confirmed_deterministic_failure",
            grid_bounds={"lower": lower, "upper": upper, "maximum": maximum},
        )
    else:
        results[pass_spec.criterion_id] = _private_result(
            pass_spec,
            pass_state,
            "AT-RISK",
            "evidence_missing",
            grid_bounds={"lower": lower, "upper": upper, "maximum": maximum},
        )

    funds_spec = next(
        item for item in specs if item.criterion_id == "fsw.funds.requirement"
    )
    funds_state = state_for(funds_spec)
    results[funds_spec.criterion_id] = _funds_result(
        funds_spec,
        funds_state,
        evidence,
        offer_validation,
        reference,
    )

    destination_spec = next(
        item for item in specs
        if item.criterion_id == "fsw.destination.outside_quebec"
    )
    destination_state = state_for(destination_spec)
    province = evidence.value("intended_destination_province")
    if not destination_state.usable:
        results[destination_spec.criterion_id] = _unusable_result(
            destination_spec, destination_state
        )
    elif province is None:
        results[destination_spec.criterion_id] = _private_result(
            destination_spec, destination_state, "AT-RISK", "evidence_missing"
        )
    elif province == "QC":
        results[destination_spec.criterion_id] = _private_result(
            destination_spec,
            destination_state,
            "FAIL",
            "confirmed_deterministic_failure",
            evidence_ids=_evidence_ids(evidence, "intended_destination_province"),
        )
    else:
        results[destination_spec.criterion_id] = _private_result(
            destination_spec,
            destination_state,
            "PASS",
            "criterion_satisfied",
            evidence_ids=_evidence_ids(evidence, "intended_destination_province"),
        )

    _apply_prerequisite_usability(
        specs,
        states,
        results,
        {
            "fsw.work.teer": ("fsw.work.primary_noc",),
            "fsw.work.paid": ("fsw.work.primary_noc", "fsw.work.teer"),
            "fsw.work.recency": (
                "fsw.work.primary_noc",
                "fsw.work.teer",
                "fsw.work.paid",
            ),
            "fsw.work.continuity_duration_hours": (
                "fsw.work.primary_noc",
                "fsw.work.teer",
                "fsw.work.paid",
                "fsw.work.recency",
            ),
            "fsw.work.noc_duties": ("fsw.work.primary_noc",),
            "fsw.grid.experience": (
                "fsw.work.teer",
                "fsw.work.paid",
                "fsw.work.recency",
                "fsw.work.continuity_duration_hours",
            ),
            "fsw.grid.pass_mark": (
                "fsw.grid.language",
                "fsw.grid.education",
                "fsw.grid.experience",
                "fsw.grid.age",
                "fsw.grid.arranged_employment",
                "fsw.grid.adaptability",
            ),
        },
    )
    if set(results) != {spec.criterion_id for spec in specs}:
        raise MecGatePreparationError("FSW criterion set is not exact")
    return tuple(results[spec.criterion_id] for spec in specs)


def _noc_hierarchy_match(row: RuleRow, noc_code: Any) -> bool | None:
    code = str(noc_code)
    if re.fullmatch(r"\d{5}", code) is None:
        return None

    def matches(label: str) -> bool:
        number_match = re.search(r"\d+", label)
        if not number_match:
            return False
        number = number_match.group()
        if label.startswith("Major Group"):
            return code[:2] == number
        if label.startswith("Sub-Major Group"):
            return code[:3] == number
        if label.startswith("Minor Group"):
            return code[:4] == number
        if label.startswith("Unit Group"):
            return code == number
        return False

    excluded = [
        str(item.value) for item in row.machine_check.excluded_hierarchy or []
    ]
    if any(matches(label) for label in excluded):
        return False
    included = [
        str(item.value) for item in row.machine_check.included_hierarchy or []
    ]
    return any(matches(label) for label in included)


def _add_calendar_months(value: date, months: int) -> date:
    """Return the clamped calendar anniversary ``months`` after ``value``."""
    month_index = value.month - 1 + months
    year, month_offset = divmod(month_index, 12)
    target_year = value.year + year
    target_month = month_offset + 1
    if target_month == 12:
        next_month = date(target_year + 1, 1, 1)
    else:
        next_month = date(target_year, target_month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(target_year, target_month, min(value.day, last_day))


def _completed_calendar_months(start: date, end_inclusive: date) -> int:
    """Count completed month anniversaries in one inclusive policy interval."""
    if end_inclusive < start:
        raise ValueError("employment interval ends before it starts")
    exclusive_end = end_inclusive + timedelta(days=1)
    months = (
        (exclusive_end.year - start.year) * 12
        + exclusive_end.month
        - start.month
    )
    if _add_calendar_months(start, months) > exclusive_end:
        months -= 1
    return max(months, 0)


def _completed_fragmented_calendar_months(
    ranges: Iterable[tuple[date, date]],
) -> int:
    """Count one exact calendar duration after unioning disconnected ranges.

    The ranges use exclusive ends.  Disconnected employment has no natural
    anniversary, so its exact covered days are laid consecutively from the first
    actual start date.  This canonical calendar preserves leap/month boundaries
    without average-year arithmetic and, critically, carries every partial-range
    remainder into the next range instead of flooring each range separately.
    """
    merged: list[tuple[date, date]] = []
    for range_start, range_end in sorted(ranges):
        if range_end <= range_start:
            raise ValueError("covered range must have positive duration")
        if merged and range_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], range_end))
        else:
            merged.append((range_start, range_end))
    if not merged:
        return 0
    covered_days = sum(
        (range_end - range_start).days for range_start, range_end in merged
    )
    canonical_start = merged[0][0]
    canonical_end = canonical_start + timedelta(days=covered_days)
    return _completed_calendar_months(
        canonical_start,
        canonical_end - timedelta(days=1),
    )


def _aggregate_periods(
    periods: Iterable[EmploymentPeriod],
    row: RuleRow,
    *,
    separate_noc: bool = True,
    reference: date | None = None,
    lookback_years: int | None = None,
) -> tuple[
    dict[str, tuple[int, float, tuple[EmploymentPeriod, ...]]],
    bool,
]:
    """Derive calendar duration and globally capped concurrent hours by NOC.

    Claimed duration is never summed.  Each period must carry a valid interval,
    grounded weekly/total hours, and internally consistent claims.  Concurrent
    periods share one weekly cap; when different NOCs exceed that cap, exact
    same-NOC allocation is unknowable and the aggregate fails closed. When a
    lookback is supplied, original claims are validated first and only the
    inclusive intersection with that grounded window contributes.
    """
    cap = _policy_value(row.machine_check.maximum_hours_per_week)
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap <= 0:
        return {}, False

    validated: list[tuple[EmploymentPeriod, date, date, float, str]] = []
    for period in tuple(periods):
        if not _period_has(
            period,
            "noc_code",
            "employment_start",
            "employment_end",
            "duration_months",
            "total_hours",
            "hours_per_week",
        ):
            return {}, False
        try:
            start = date.fromisoformat(str(period.values["employment_start"]))
            end = date.fromisoformat(str(period.values["employment_end"]))
            weekly = float(period.values["hours_per_week"])
            claimed_hours = float(period.values["total_hours"])
            claimed_months = period.values["duration_months"]
        except (TypeError, ValueError):
            return {}, False
        if (
            end < start
            or weekly <= 0
            or claimed_hours < 0
            or isinstance(claimed_months, bool)
            or not isinstance(claimed_months, int)
            or claimed_months < 0
        ):
            return {}, False
        days = (end - start).days + 1
        derived_hours = weekly * days / 7
        derived_months = _completed_calendar_months(start, end)
        if (
            abs(claimed_hours - derived_hours) > max(weekly, derived_hours * 0.05)
            or abs(claimed_months - derived_months) > 1
        ):
            return {}, False
        clipped_start = start
        clipped_end = end
        if reference is not None or lookback_years is not None:
            if (
                reference is None
                or isinstance(lookback_years, bool)
                or not isinstance(lookback_years, int)
            ):
                return {}, False
            clipped_start = max(start, _years_before(reference, lookback_years))
            clipped_end = min(end, reference)
            if clipped_start > clipped_end:
                continue
        validated.append(
            (
                period,
                clipped_start,
                clipped_end,
                weekly,
                str(period.values["noc_code"]) if separate_noc else "*",
            )
        )

    if not validated:
        return {}, False
    boundaries = sorted(
        {
            point
            for _, start, end, _, _ in validated
            for point in (start, end + timedelta(days=1))
        }
    )
    covered_ranges: dict[str, list[tuple[date, date]]] = {}
    counted_hours: dict[str, float] = {}
    grouped_periods: dict[str, dict[str, EmploymentPeriod]] = {}
    for segment_start, segment_end in zip(boundaries, boundaries[1:]):
        active = [
            item
            for item in validated
            if item[1] <= segment_start and item[2] >= segment_start
        ]
        if not active:
            continue
        segment_days = (segment_end - segment_start).days
        by_noc: dict[str, list[tuple[EmploymentPeriod, date, date, float, str]]] = {}
        for item in active:
            by_noc.setdefault(item[4], []).append(item)
        if separate_noc and len(by_noc) > 1 and sum(item[3] for item in active) > cap:
            return {}, False
        for noc, items in by_noc.items():
            weekly = min(sum(item[3] for item in items), cap)
            covered_ranges.setdefault(noc, []).append((segment_start, segment_end))
            counted_hours[noc] = (
                counted_hours.get(noc, 0.0) + weekly * segment_days / 7
            )
            grouped_periods.setdefault(noc, {}).update(
                {item[0].employment_period_id: item[0] for item in items}
            )
    completed_months = {
        noc: _completed_fragmented_calendar_months(ranges)
        for noc, ranges in covered_ranges.items()
    }
    return (
        {
            noc: (
                completed_months[noc],
                counted_hours[noc],
                tuple(
                    sorted(
                        grouped_periods[noc].values(),
                        key=lambda period: period.employment_period_id,
                    )
                ),
            )
            for noc in covered_ranges
        },
        True,
    )


def _simple_period_criterion(
    spec: MecCriterionSpec,
    state: MecRowUsability,
    all_periods: tuple[EmploymentPeriod, ...],
    population: Iterable[EmploymentPeriod],
    matches: Iterable[EmploymentPeriod],
    field_valid: Iterable[EmploymentPeriod],
    *,
    complete: bool,
    fail_when_complete: bool = True,
    at_risk_reason: str = "evidence_missing",
) -> PrivateMecCriterion:
    if not state.usable:
        return _unusable_result(spec, state)
    relevant = tuple(population)
    matched = tuple(matches)
    valid_values = tuple(field_valid)
    if matched:
        status, reason = "PASS", "criterion_satisfied"
    elif (
        complete
        and relevant
        and len(valid_values) == len(relevant)
        and fail_when_complete
    ):
        status, reason = "FAIL", "confirmed_deterministic_failure"
    else:
        status = "AT-RISK"
        reason = "scope_incomplete" if not complete else at_risk_reason
    return _private_result(
        spec,
        state,
        status,
        reason,
        evidence_ids=(
            value_id for period in matched for value_id in period.evidence_ids
        ),
        employment_traces=(
            _period_trace(
                period,
                period in matched,
                "predicate_satisfied" if period in matched else "predicate_excluded",
            )
            for period in all_periods
        ),
        completeness={"work": complete},
    )


def _funds_result(
    spec: MecCriterionSpec,
    state: MecRowUsability,
    evidence: MecEvidence,
    offer_validation: MecOfferValidation | None,
    reference: date | None,
) -> PrivateMecCriterion:
    if not state.usable:
        return _unusable_result(spec, state)
    program: Program = "fsw" if spec.criterion_id.startswith("fsw.") else "fst"
    conditions = _validate_mec_offer(
        program,
        state.row,
        evidence,
        reference,
    )
    expected_offer_rule = (
        "fsw.grid.arranged_employment"
        if program == "fsw"
        else "fst.offer_or_certificate"
    )
    exempt = (
        offer_validation is not None
        and offer_validation.status == "PASS"
        and offer_validation.program == program
        and offer_validation.rule_ids == (expected_offer_rule,)
        and conditions.status == "PASS"
    )
    if exempt:
        return _private_result(
            spec,
            state,
            "N/A",
            "not_applicable",
            evidence_ids=_evidence_ids(
                evidence,
                "legally_authorized_to_work_canada",
                *offer_validation.evidence_fields,
            ),
            applicability_grounded=True,
            applicable=False,
        )
    return _private_result(
        spec,
        state,
        "AT-RISK",
        "funds_snapshot_unavailable",
        evidence_ids=_evidence_ids(
            evidence,
            "funds_accessible",
            "funds_borrowed",
            "funds_real_property_equity",
        ),
        applicability_grounded=True,
        applicable=True,
    )


def _destination_result(
    spec: MecCriterionSpec,
    state: MecRowUsability,
    evidence: MecEvidence,
) -> PrivateMecCriterion:
    if not state.usable:
        return _unusable_result(spec, state)
    province = evidence.value("intended_destination_province")
    if province is None:
        status, reason = "AT-RISK", "evidence_missing"
    elif province == "QC":
        status, reason = "FAIL", "confirmed_deterministic_failure"
    else:
        status, reason = "PASS", "criterion_satisfied"
    return _private_result(
        spec,
        state,
        status,
        reason,
        evidence_ids=_evidence_ids(evidence, "intended_destination_province"),
    )


def _fst_language_result(
    spec: MecCriterionSpec,
    state: MecRowUsability,
    context: MecGateContext,
    inputs: ConfirmedMecInputs,
) -> PrivateMecCriterion:
    if not state.usable:
        return _unusable_result(spec, state)
    levels = _all_card_levels(inputs.language, "first")
    current = _language_current(
        inputs.language, "first", state.row, _reference_date(context.reference_date)
    )
    thresholds: dict[str, int] = {}
    for item in state.row.machine_check.included_hierarchy or []:
        text = str(item.value).casefold()
        numbers = [int(value) for value in re.findall(r"\d+", text)]
        if not numbers:
            continue
        if "speaking" in text and "listening" in text:
            thresholds["speaking"] = numbers[-1]
            thresholds["listening"] = numbers[-1]
        if "reading" in text and "writing" in text:
            thresholds["reading"] = numbers[-1]
            thresholds["writing"] = numbers[-1]
    if levels is None or current is None or len(thresholds) != 4:
        return _private_result(spec, state, "AT-RISK", "evidence_missing")
    ordered = dict(
        zip(("listening", "reading", "writing", "speaking"), levels, strict=True)
    )
    if current is False or any(
        ordered[ability] < minimum for ability, minimum in thresholds.items()
    ):
        return _private_result(
            spec, state, "FAIL", "confirmed_deterministic_failure"
        )
    return _private_result(spec, state, "PASS", "criterion_satisfied")


def evaluate_fst(
    context: MecGateContext,
    evidence: MecEvidence,
    confirmed_inputs: ConfirmedMecInputs,
) -> tuple[PrivateMecCriterion, ...]:
    """Evaluate FST with structural hierarchy and same-NOC aggregation."""
    if evidence.registry_fingerprint != context.registry_fingerprint:
        raise MecGatePreparationError("MEC evidence fingerprint mismatch")
    specs = MEC_PROGRAM_CRITERIA["fst"]
    states = _context_rows(context)
    periods = evidence.periods
    complete = _scope_complete(evidence, "work_history_scope_complete")
    results: dict[str, PrivateMecCriterion] = {}

    def pair(criterion_id: str) -> tuple[MecCriterionSpec, MecRowUsability]:
        spec = next(item for item in specs if item.criterion_id == criterion_id)
        state = states.get(criterion_id)
        if state is None:
            raise MecGatePreparationError("MEC criterion manifest is not exactly wired")
        return spec, state

    trade_spec, trade_state = pair("fst.work.trade_noc")
    trade_known = [
        period for period in periods if _period_has(period, "noc_code")
    ]
    trade = [
        period for period in trade_known
        if _noc_hierarchy_match(trade_state.row, period.values["noc_code"]) is True
    ]
    results[trade_spec.criterion_id] = _simple_period_criterion(
        trade_spec,
        trade_state,
        periods,
        periods,
        trade,
        trade_known,
        complete=complete,
    )

    paid_spec, paid_state = pair("fst.work.paid")
    paid_known = [
        period for period in trade if _period_has(period, "paid_status")
    ]
    paid = [period for period in paid_known if period.values["paid_status"] is True]
    results[paid_spec.criterion_id] = _simple_period_criterion(
        paid_spec, paid_state, periods, trade, paid, paid_known, complete=complete
    )

    qualify_spec, qualify_state = pair("fst.work.qualified_to_practise")
    qualify_known = [
        period for period in paid if _period_has(period, "qualified_to_practise")
    ]
    qualified = [
        period for period in qualify_known
        if period.values["qualified_to_practise"] is True
    ]
    results[qualify_spec.criterion_id] = _simple_period_criterion(
        qualify_spec,
        qualify_state,
        periods,
        paid,
        qualified,
        qualify_known,
        complete=complete,
    )

    student_spec, student_state = pair("fst.work.student_exclusion")
    student_known = [
        period for period in qualified if _period_has(period, "student_status")
    ]
    non_student = [
        period for period in student_known if period.values["student_status"] is False
    ]
    results[student_spec.criterion_id] = _simple_period_criterion(
        student_spec,
        student_state,
        periods,
        qualified,
        non_student,
        student_known,
        complete=complete,
    )

    duration_spec, duration_state = pair("fst.work.recency_duration_hours")
    lookback = _policy_value(duration_state.row.machine_check.lookback_years)
    reference = _reference_date(context.reference_date)
    recency_known = [
        (
            period,
            _interval_in_lookback(
                period.values.get("employment_start"),
                period.values.get("employment_end"),
                reference,
                lookback,
            ),
        )
        for period in non_student
    ]
    recent = [period for period, current in recency_known if current is True]
    grouped, aggregate_resolved = _aggregate_periods(
        recent,
        duration_state.row,
        reference=reference,
        lookback_years=lookback,
    )
    minimum_months = _policy_value(
        duration_state.row.machine_check.minimum_duration_months
    )
    minimum_hours = _policy_value(duration_state.row.machine_check.minimum_hours)
    qualifying_groups = {
        noc: values
        for noc, values in grouped.items()
        if values[0] >= minimum_months and values[1] >= minimum_hours
    }
    if not duration_state.usable:
        results[duration_spec.criterion_id] = _unusable_result(
            duration_spec, duration_state
        )
    elif qualifying_groups:
        selected = next(iter(sorted(qualifying_groups.items())))[1][2]
        results[duration_spec.criterion_id] = _simple_period_criterion(
            duration_spec,
            duration_state,
            periods,
            recent,
            selected,
            recent,
            complete=complete,
        )
    elif (
        complete
        and recent
        and aggregate_resolved
        and all(current is not None for _, current in recency_known)
    ):
        results[duration_spec.criterion_id] = _private_result(
            duration_spec,
            duration_state,
            "FAIL",
            "confirmed_deterministic_failure",
            employment_traces=(
                _period_trace(period, False, "same_noc_threshold_not_met")
                for period in periods
            ),
            completeness={"work": True},
        )
    else:
        results[duration_spec.criterion_id] = _private_result(
            duration_spec,
            duration_state,
            "AT-RISK",
            "evidence_missing" if recent else "scope_incomplete",
            completeness={"work": complete},
        )

    same_spec, same_state = pair("fst.work.same_noc")
    if not same_state.usable:
        results[same_spec.criterion_id] = _unusable_result(same_spec, same_state)
    elif qualifying_groups or len({p.values["noc_code"] for p in recent}) == 1:
        selected_nocs = set(qualifying_groups) or {
            period.values["noc_code"] for period in recent
        }
        selected = [
            period for period in recent if period.values["noc_code"] in selected_nocs
        ]
        results[same_spec.criterion_id] = _simple_period_criterion(
            same_spec,
            same_state,
            periods,
            recent,
            selected,
            recent,
            complete=complete,
        )
    elif complete and recent:
        results[same_spec.criterion_id] = _private_result(
            same_spec,
            same_state,
            "FAIL",
            "confirmed_deterministic_failure",
            completeness={"work": True},
        )
    else:
        results[same_spec.criterion_id] = _private_result(
            same_spec, same_state, "AT-RISK", "evidence_missing"
        )

    noc_spec, noc_state = pair("fst.work.noc_duties_requirements")
    results[noc_spec.criterion_id] = (
        _unusable_result(noc_spec, noc_state)
        if not noc_state.usable
        else _private_result(
            noc_spec,
            noc_state,
            "AT-RISK",
            "manual_noc_review" if trade else "evidence_missing",
            sidecar_inputs={"noc": confirmed_inputs.sidecars.get("noc", {})},
        )
    )

    language_spec, language_state = pair("fst.language.minimum")
    results[language_spec.criterion_id] = _fst_language_result(
        language_spec, language_state, context, confirmed_inputs
    )

    offer_spec, offer_state = pair("fst.offer_or_certificate")
    certificate_fields = (
        "trade_certificate_authority",
        "trade_certificate_jurisdiction",
        "trade_certificate_noc_code",
        "trade_certificate_status",
        "trade_certificate_issue_date",
        "trade_certificate_expiry_date",
    )
    issue_date = _reference_date(evidence.value("trade_certificate_issue_date"))
    expiry_date = _reference_date(evidence.value("trade_certificate_expiry_date"))
    selected_trade_nocs = {
        str(noc_code)
        for noc_code in qualifying_groups
    }
    certificate_scope_complete = _scope_complete(
        evidence, "offer_certificate_scope_complete"
    )
    certificate_complete = (
        certificate_scope_complete
        and not evidence.conflicts.intersection(certificate_fields)
        and all(evidence.value(name) is not None for name in certificate_fields)
    )
    certificate_valid = (
        certificate_complete
        and reference is not None
        and issue_date is not None
        and expiry_date is not None
        and issue_date <= reference <= expiry_date
        and evidence.value("trade_certificate_status") == "valid"
        and evidence.value("trade_certificate_jurisdiction")
        in MEC_TRADE_JURISDICTIONS
        and evidence.value("trade_certificate_noc_code") in selected_trade_nocs
    )
    offer_sidecar = confirmed_inputs.sidecars.get("offer")
    offer_validation = _validate_mec_offer(
        "fst",
        offer_state.row,
        evidence,
        reference,
        selected_nocs=selected_trade_nocs,
    )
    offer_branch_valid = offer_validation.status == "PASS"
    if not offer_state.usable:
        results[offer_spec.criterion_id] = _unusable_result(offer_spec, offer_state)
    elif certificate_valid:
        results[offer_spec.criterion_id] = _private_result(
            offer_spec,
            offer_state,
            "PASS",
            "criterion_satisfied",
            evidence_ids=_evidence_ids(
                evidence, "offer_certificate_scope_complete", *certificate_fields
            ),
            sidecar_inputs={"offer_branch": "N/A", "certificate_branch": "PASS"},
            completeness={"offer_certificate": certificate_scope_complete},
        )
    else:
        results[offer_spec.criterion_id] = _private_result(
            offer_spec,
            offer_state,
            "AT-RISK",
            "manual_offer_review",
            evidence_ids=_evidence_ids(
                evidence,
                "offer_certificate_scope_complete",
                *certificate_fields,
                *offer_validation.evidence_fields,
            ),
            sidecar_inputs={"offer": offer_sidecar or {}},
            completeness={"offer_certificate": certificate_scope_complete},
        )

    funds_spec, funds_state = pair("fst.funds.requirement")
    results[funds_spec.criterion_id] = _funds_result(
        funds_spec,
        funds_state,
        evidence,
        offer_validation,
        reference,
    )
    destination_spec, destination_state = pair("fst.destination.outside_quebec")
    results[destination_spec.criterion_id] = _destination_result(
        destination_spec, destination_state, evidence
    )

    _apply_prerequisite_usability(
        specs,
        states,
        results,
        {
            "fst.work.paid": ("fst.work.trade_noc",),
            "fst.work.qualified_to_practise": (
                "fst.work.trade_noc",
                "fst.work.paid",
            ),
            "fst.work.student_exclusion": (
                "fst.work.trade_noc",
                "fst.work.paid",
                "fst.work.qualified_to_practise",
            ),
            "fst.work.recency_duration_hours": (
                "fst.work.trade_noc",
                "fst.work.paid",
                "fst.work.qualified_to_practise",
                "fst.work.student_exclusion",
            ),
            "fst.work.same_noc": (
                "fst.work.trade_noc",
                "fst.work.recency_duration_hours",
            ),
            "fst.work.noc_duties_requirements": ("fst.work.trade_noc",),
            "fst.offer_or_certificate": (
                () if offer_branch_valid else ("fst.work.trade_noc",)
            ),
        },
    )
    if set(results) != {spec.criterion_id for spec in specs}:
        raise MecGatePreparationError("FST criterion set is not exact")
    return tuple(results[spec.criterion_id] for spec in specs)


def _cec_language_result(
    spec: MecCriterionSpec,
    state: MecRowUsability,
    context: MecGateContext,
    inputs: ConfirmedMecInputs,
    teers: set[int],
) -> PrivateMecCriterion:
    if not state.usable:
        return _unusable_result(spec, state)
    levels = _all_card_levels(inputs.language, "first")
    current = _language_current(
        inputs.language, "first", state.row, _reference_date(context.reference_date)
    )
    required: list[int] = []
    for item in state.row.machine_check.included_hierarchy or []:
        text = str(item.value)
        numbers = [int(value) for value in re.findall(r"\d+", text)]
        if len(numbers) < 2:
            continue
        threshold = numbers[-1]
        row_teers = set(numbers[:-1])
        if teers & row_teers:
            required.append(threshold)
    if levels is None or current is None or not teers or not required:
        return _private_result(spec, state, "AT-RISK", "evidence_missing")
    minimum = max(required)
    if current is False or any(level < minimum for level in levels):
        return _private_result(
            spec, state, "FAIL", "confirmed_deterministic_failure"
        )
    return _private_result(spec, state, "PASS", "criterion_satisfied")


def evaluate_cec(
    context: MecGateContext,
    evidence: MecEvidence,
    confirmed_inputs: ConfirmedMecInputs,
) -> tuple[PrivateMecCriterion, ...]:
    """Evaluate CEC after applying every exclusion to each keyed period."""
    if evidence.registry_fingerprint != context.registry_fingerprint:
        raise MecGatePreparationError("MEC evidence fingerprint mismatch")
    specs = MEC_PROGRAM_CRITERIA["cec"]
    states = _context_rows(context)
    periods = evidence.periods
    complete = _scope_complete(evidence, "work_history_scope_complete")
    results: dict[str, PrivateMecCriterion] = {}

    def pair(criterion_id: str) -> tuple[MecCriterionSpec, MecRowUsability]:
        spec = next(item for item in specs if item.criterion_id == criterion_id)
        state = states.get(criterion_id)
        if state is None:
            raise MecGatePreparationError("MEC criterion manifest is not exactly wired")
        return spec, state

    teer_spec, teer_state = pair("cec.work.teer")
    allowed = _hierarchy_numbers(teer_state.row)
    teer_known = [period for period in periods if _period_has(period, "teer")]
    skilled = [
        period for period in teer_known if period.values["teer"] in allowed
    ]
    results[teer_spec.criterion_id] = _simple_period_criterion(
        teer_spec,
        teer_state,
        periods,
        periods,
        skilled,
        teer_known,
        complete=complete,
    )

    canada_spec, canada_state = pair("cec.work.in_canada")
    canada_known = [
        period
        for period in skilled
        if _period_has(
            period,
            "work_country",
            "work_province",
            "physically_in_canada",
            "is_remote",
        )
        and (
            period.values["is_remote"] is False
            or _period_has(period, "canadian_employer_if_remote")
        )
    ]
    in_canada = [
        period
        for period in canada_known
        if period.values["work_country"] == "CA"
        and period.values["physically_in_canada"] is True
        and (
            period.values["is_remote"] is False
            or period.values["canadian_employer_if_remote"] is True
        )
    ]
    results[canada_spec.criterion_id] = _simple_period_criterion(
        canada_spec,
        canada_state,
        periods,
        skilled,
        in_canada,
        canada_known,
        complete=complete,
    )

    auth_spec, auth_state = pair("cec.work.authorized_tr_status")
    auth_known = [
        period
        for period in in_canada
        if _period_has(period, "work_authorized", "temporary_resident_status")
    ]
    authorized = [
        period
        for period in auth_known
        if period.values["work_authorized"] is True
        and period.values["temporary_resident_status"] in {"valid", "maintained"}
    ]
    results[auth_spec.criterion_id] = _simple_period_criterion(
        auth_spec,
        auth_state,
        periods,
        in_canada,
        authorized,
        auth_known,
        complete=complete,
    )

    paid_spec, paid_state = pair("cec.work.paid")
    paid_known = [
        period for period in authorized if _period_has(period, "paid_status")
    ]
    paid = [period for period in paid_known if period.values["paid_status"] is True]
    results[paid_spec.criterion_id] = _simple_period_criterion(
        paid_spec,
        paid_state,
        periods,
        authorized,
        paid,
        paid_known,
        complete=complete,
    )

    student_spec, student_state = pair("cec.work.student_exclusion")
    student_known = [
        period for period in paid if _period_has(period, "student_status")
    ]
    non_student = [
        period for period in student_known if period.values["student_status"] is False
    ]
    results[student_spec.criterion_id] = _simple_period_criterion(
        student_spec,
        student_state,
        periods,
        paid,
        non_student,
        student_known,
        complete=complete,
    )

    self_spec, self_state = pair("cec.work.self_employment_exclusion")
    self_known = [
        period for period in paid if _period_has(period, "self_employed")
    ]
    employed = [
        period for period in self_known if period.values["self_employed"] is False
    ]
    physician_claimed = bool(
        confirmed_inputs.sidecars.get("physician_exception_claimed")
    )
    if physician_claimed and any(
        period.values["self_employed"] is True for period in self_known
    ):
        results[self_spec.criterion_id] = _private_result(
            self_spec,
            self_state,
            "AT-RISK",
            "manual_physician_review",
            employment_traces=(
                _period_trace(period, period in employed, "physician_exception_manual")
                for period in periods
            ),
            sidecar_inputs={"physician_exception_claimed": True},
        )
    else:
        results[self_spec.criterion_id] = _simple_period_criterion(
            self_spec,
            self_state,
            periods,
            paid,
            employed,
            self_known,
            complete=complete,
        )

    duration_spec, duration_state = pair("cec.work.recency_duration_hours")
    lookback = _policy_value(duration_state.row.machine_check.lookback_years)
    reference = _reference_date(context.reference_date)
    fully_included = [period for period in non_student if period in employed]
    recent = [
        period
        for period in fully_included
        if _interval_in_lookback(
            period.values.get("employment_start"),
            period.values.get("employment_end"),
            reference,
            lookback,
        ) is True
    ]
    duration_known = [
        period
        for period in recent
        if _period_has(
            period,
            "employment_start",
            "employment_end",
            "duration_months",
            "total_hours",
            "hours_per_week",
        )
    ]
    aggregates, aggregate_resolved = _aggregate_periods(
        duration_known,
        duration_state.row,
        separate_noc=False,
        reference=reference,
        lookback_years=lookback,
    )
    aggregate = aggregates.get("*")
    total_months = aggregate[0] if aggregate is not None else 0.0
    total_hours = aggregate[1] if aggregate is not None else 0.0
    minimum_months = _policy_value(
        duration_state.row.machine_check.minimum_duration_months
    )
    minimum_hours = _policy_value(duration_state.row.machine_check.minimum_hours)
    meets_duration = (
        total_months >= minimum_months and total_hours >= minimum_hours
    )
    if not duration_state.usable:
        results[duration_spec.criterion_id] = _unusable_result(
            duration_spec, duration_state
        )
    elif meets_duration:
        results[duration_spec.criterion_id] = _simple_period_criterion(
            duration_spec,
            duration_state,
            periods,
            recent,
            duration_known,
            duration_known,
            complete=complete,
        )
    elif (
        complete
        and recent
        and aggregate_resolved
        and len(duration_known) == len(recent)
    ):
        results[duration_spec.criterion_id] = _private_result(
            duration_spec,
            duration_state,
            "FAIL",
            "confirmed_deterministic_failure",
            completeness={"work": True},
        )
    else:
        results[duration_spec.criterion_id] = _private_result(
            duration_spec,
            duration_state,
            "AT-RISK",
            "scope_incomplete" if not complete else "evidence_missing",
            completeness={"work": complete},
        )

    noc_spec, noc_state = pair("cec.work.noc_duties")
    results[noc_spec.criterion_id] = (
        _unusable_result(noc_spec, noc_state)
        if not noc_state.usable
        else _private_result(
            noc_spec,
            noc_state,
            "AT-RISK",
            "manual_noc_review" if skilled else "evidence_missing",
            sidecar_inputs={"noc": confirmed_inputs.sidecars.get("noc", {})},
        )
    )

    language_spec, language_state = pair("cec.language.minimum")
    results[language_spec.criterion_id] = _cec_language_result(
        language_spec,
        language_state,
        context,
        confirmed_inputs,
        {period.values["teer"] for period in duration_known},
    )

    destination_spec, destination_state = pair("cec.destination.outside_quebec")
    results[destination_spec.criterion_id] = _destination_result(
        destination_spec, destination_state, evidence
    )

    _apply_prerequisite_usability(
        specs,
        states,
        results,
        {
            "cec.work.in_canada": ("cec.work.teer",),
            "cec.work.authorized_tr_status": (
                "cec.work.teer",
                "cec.work.in_canada",
            ),
            "cec.work.paid": (
                "cec.work.teer",
                "cec.work.in_canada",
                "cec.work.authorized_tr_status",
            ),
            "cec.work.student_exclusion": (
                "cec.work.teer",
                "cec.work.in_canada",
                "cec.work.authorized_tr_status",
                "cec.work.paid",
            ),
            "cec.work.self_employment_exclusion": (
                "cec.work.teer",
                "cec.work.in_canada",
                "cec.work.authorized_tr_status",
                "cec.work.paid",
            ),
            "cec.work.recency_duration_hours": (
                "cec.work.teer",
                "cec.work.in_canada",
                "cec.work.authorized_tr_status",
                "cec.work.paid",
                "cec.work.student_exclusion",
                "cec.work.self_employment_exclusion",
            ),
            "cec.work.noc_duties": ("cec.work.teer",),
            "cec.language.minimum": (
                "cec.work.teer",
                "cec.work.in_canada",
                "cec.work.authorized_tr_status",
                "cec.work.paid",
                "cec.work.student_exclusion",
                "cec.work.self_employment_exclusion",
                "cec.work.recency_duration_hours",
            ),
        },
    )
    if set(results) != {spec.criterion_id for spec in specs}:
        raise MecGatePreparationError("CEC criterion set is not exact")
    return tuple(results[spec.criterion_id] for spec in specs)


@dataclass(frozen=True)
class MecPublicationBundle:
    """Validated in-memory material; publication belongs to the next plan."""

    private_report: PrivateMecReport
    public_summary: PublicMecSummary
    private_json: bytes
    private_markdown: bytes
    public_json: bytes


def _compose_sidecars(
    program: Program,
    context: MecGateContext,
    evidence: MecEvidence,
    inputs: ConfirmedMecInputs,
    *,
    vault_: Any = None,
    db: Any = None,
    study_max_age_days: int | None = None,
) -> ConfirmedMecInputs:
    """Compose shipped sidecars read-only without promoting their statuses."""
    sidecars = dict(inputs.sidecars)
    try:
        from crawler import noc_review, policy_offer, study_review

        offer_present = any(name.startswith("offer_") for name in evidence.scalars)
        sidecars["offer"] = policy_offer.offer_for_program_eligibility(
            offer_present,
            evidence.value("ita_date"),
            context.registry_snapshot.registry,
        )
        if vault_ is not None and db is not None:
            noc_results = {}
            for noc_code in sorted(
                {
                    period.values["noc_code"]
                    for period in employment_periods(evidence)
                    if "noc_code" in period.values
                }
            ):
                noc_results[noc_code] = noc_review.review_noc_duties(
                    vault_,
                    db,
                    noc_code,
                    candidate_id=evidence.candidate_id,
                    registry_snapshot=context.registry_snapshot,
                    registry_fingerprint=context.registry_fingerprint,
                )
            sidecars["noc"] = noc_results
        if (
            program == "fsw"
            and vault_ is not None
            and db is not None
            and study_max_age_days is not None
        ):
            sidecars["study"] = study_review.review_study(
                vault_,
                db,
                candidate_id=evidence.candidate_id,
                max_age_days=study_max_age_days,
                registry_snapshot=context.registry_snapshot,
                read_only=True,
                no_report=True,
            )
    except study_review.StudyReportRecoveryError:
        raise
    except (OSError, TypeError, ValueError, RuntimeError):
        sidecars["composition"] = {"status": "AT-RISK", "reason": "composition_refused"}
    return inputs.with_updates(sidecars=sidecars)


def _render_private_markdown(report: PrivateMecReport) -> bytes:
    lines = [
        f"# MEC {report.program.upper()} private screening",
        "",
        SCREENING_NOTICE,
        "",
        f"- Run: `{report.run_id}`",
        f"- Status: `{report.status}`",
        f"- Registry: `{report.registry_fingerprint}`",
        "",
        "## Criteria",
        "",
    ]
    for criterion in report.criteria:
        lines.append(
            f"- `{criterion.criterion_id}`: **{criterion.status}** "
            f"(`{criterion.reason_code}`)"
        )
    lines.extend(
        [
            "",
            "## Private evidence detail",
            "",
            "```json",
            json.dumps(
                [item.model_dump(mode="json") for item in report.criteria],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines).encode()


def screen_mec(
    program: Program,
    context: MecGateContext,
    evidence: MecEvidence,
    confirmed_inputs: ConfirmedMecInputs,
    *,
    vault_: Any = None,
    db: Any = None,
    study_max_age_days: int | None = None,
    run_id: str | None = None,
    created_at: str | None = None,
    private_output_path: str | None = None,
) -> MecPublicationBundle:
    """Return deterministic validated private/public MEC material in memory."""
    if program not in MEC_PROGRAM_CRITERIA:
        raise MecGatePreparationError("unknown MEC program")
    if private_output_path is None:
        private_output_path = f"output/mec/{program}/latest.json"
    composed = _compose_sidecars(
        program,
        context,
        evidence,
        confirmed_inputs,
        vault_=vault_,
        db=db,
        study_max_age_days=study_max_age_days,
    )
    evaluators = {
        "fsw": evaluate_fsw,
        "fst": evaluate_fst,
        "cec": evaluate_cec,
    }
    criteria = evaluators[program](context, evidence, composed)
    expected = tuple(
        spec.criterion_id for spec in MEC_PROGRAM_CRITERIA[program]
    )
    if tuple(item.criterion_id for item in criteria) != expected:
        raise MecGatePreparationError("MEC criterion set is not exact")
    status = rollup_program_status(program, criteria)
    counts = MecCounts(
        criteria=len(criteria),
        passed=sum(item.status == "PASS" for item in criteria),
        failed=sum(item.status == "FAIL" for item in criteria),
        at_risk=sum(item.status == "AT-RISK" for item in criteria),
        not_applicable=sum(item.status == "N/A" for item in criteria),
    )
    if run_id is None:
        run_id = f"mec_{uuid.uuid4().hex}"
    if created_at is None:
        operational = _reference_date(context.operational_as_of)
        if operational is None:
            raise MecGatePreparationError("MEC operational as-of date unavailable")
        created_at = f"{operational.isoformat()}T00:00:00Z"
    report = PrivateMecReport(
        schema_version="1.0",
        run_id=run_id,
        candidate_id=evidence.candidate_id,
        program=program,
        status=status,
        criteria=list(criteria),
        counts=counts,
        registry_fingerprint=context.registry_fingerprint,
        created_at=created_at,
        private_report_path=private_output_path,
    )
    projected = to_public_mec_summary(report, private_output_path)
    # The command boundary is citation-free as well as applicant-value-free.
    # Corpus coordinates remain available in the vault-private report only.
    public = projected.model_copy(
        update={
            "criteria": [
                criterion.model_copy(update={"corpus_citation_ids": []})
                for criterion in projected.criteria
            ]
        },
        deep=True,
    )
    private_json = json.dumps(
        report.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    public_json = json.dumps(
        public.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return MecPublicationBundle(
        private_report=report,
        public_summary=public,
        private_json=private_json,
        private_markdown=_render_private_markdown(report),
        public_json=public_json,
    )
