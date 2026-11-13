"""Pydantic v2 boundary models for the PII-free CRS rule registry (Phase 31 — RULE-01).

These models are the typed contract every *public* CRS rule row crosses at load
time. Unlike ``crawler.models.vault`` (which carries applicant PII behind the
git-ignored vault), this registry is **PII-FREE and PUBLIC by construction**: a
rule row models ONLY corpus authority — a baked query, a source selector, a
verbatim quote copied from a resolved corpus chunk, and machine-readable checks.
There is deliberately no applicant field, no vault reference, and no free-form
value store, so a row can never smuggle personal data into the shareable tree.

Design constraints (mirroring ``crawler.models.vault``):

* ``from __future__ import annotations`` + ``BaseModel`` + ``Literal`` enums so an
  out-of-vocabulary value is rejected AT THE BOUNDARY (pydantic ``ValidationError``)
  rather than silently persisted.
* ``extra="forbid"`` on every model so a malformed / typo'd / oversized YAML row
  fails LOUD at load (fail-closed — threat T-31-02), never persists as a partial.
* :data:`FactorGroup` is IMPORTED from ``crawler.models.vault`` so the public rule
  domains stay a single source of truth across the vault and registry boundaries.
* A :class:`Citation` ``chunk_id`` is shape-constrained to the corpus
  ``relpath#ordinal`` coordinate (the exact id :func:`crawler.searchindex.resolve`
  consumes), so a citation that is not a resolvable corpus coordinate is rejected
  before it can reach the grounding gate.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Single source of truth for the four CRS factor groups (imported, never re-declared).
from crawler.models.vault import FactorGroup

# The corpus content coordinate shape ``relpath#ordinal`` (e.g.
# ``guidance/job-offer.md#001``) — exactly what ``searchindex.build_index`` bakes
# (``f"{relpath}#{ordinal:03d}"``) and ``searchindex.resolve`` looks up. A citation
# whose id does not match this shape can never resolve, so it is rejected at load.
_CHUNK_ID_PATTERN = r"^[^#\s]+#\d+$"

# The machine-check kinds a rule row may carry. ``conversion`` is included (beyond
# the six kinds named in the 31-01 plan sketch) so CLB/NCLC raw-score→level
# conversion rows — which Plan 31-04's deterministic ``to_clb`` reads — have a
# first-class kind instead of overloading ``points_table``.
MachineCheckKind = Literal[
    "accepted_enum",     # a closed set of accepted values (tests, issuers, doc types)
    "threshold",         # a numeric min/max gate (e.g. CLB 7+ all abilities)
    "validity_window",   # a document freshness window (language <2y, ECA <5y)
    "cap",               # a points ceiling (transferability 50/50/100)
    "points_table",      # a level/tier → points mapping (age, spouse tables)
    "conversion",        # a raw test score → CLB/NCLC level mapping
    "policy_flag",       # a boolean policy fact (job-offer additional CRS = 0)
    "duration_hours",    # cited duration / hours / lookback requirements
    "hierarchy",         # cited NOC/TEER inclusions and exclusions
    "applicability",     # cited applicability / conditional-N/A predicates
]

# The verdict a rule row asserts about a factor. ``check_type`` is the row's role;
# ``machine_check.kind`` is HOW it is checked. Kept distinct so e.g. a ``conversion``
# check_type can carry a ``conversion`` machine_check while a ``cap`` check_type
# carries a ``cap`` machine_check.
CheckType = Literal[
    "admissibility",  # accepted proof / issuer / owner predicates
    "threshold",      # a numeric bar
    "conversion",     # CLB/NCLC conversion
    "points",         # a points table
    "cap",            # a points ceiling
    "policy",         # a dated policy fact (arranged-employment repeal)
]

Volatility = Literal["stable", "volatile"]


class Selector(BaseModel):
    """How the registry re-finds the RIGHT corpus chunk for a rule (retrieve-what-you-cite).

    Mirrors the v3.1 document-agent selection discipline: a source-family allow
    (``family``), an optional non-volatile ``marker`` substring used to pick the
    intended chunk out of the BM25 hits, an optional ``require_title_contains``
    title filter, and an optional ``deny_families`` list of source families that
    must NOT ground this row (e.g. year-end reports / superseded amendments) so a
    historical or adjacent chunk cannot masquerade as the cited rule (T-31-01).
    """

    model_config = ConfigDict(extra="forbid")

    family: str
    require_title_contains: str | None = None
    marker: str | None = None
    deny_families: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    """One corpus citation: a resolvable ``relpath#ordinal`` id + a verbatim quote.

    ``quote`` is copied VERBATIM from the resolved chunk text at build time; the
    shipped grounding gate proves it is a whitespace/case-normalized substring of
    the chunk the id resolves to. A ``chunk_id`` that does not match the corpus
    ``relpath#ordinal`` shape is rejected at load (it could never resolve).
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(pattern=_CHUNK_ID_PATTERN)
    quote: str = Field(min_length=1)


class AcceptedValue(BaseModel):
    """One member of an ``accepted_enum`` machine check, paired with a citation."""

    model_config = ConfigDict(extra="forbid")

    value: str
    citation_index: int = 0


class PolicyValue(BaseModel):
    """One typed MEC policy value paired with the citation that authorizes it."""

    model_config = ConfigDict(extra="forbid")

    value: str | int | float | bool
    citation_index: int = 0


class PointsEntry(BaseModel):
    """One row of a points / conversion table, each paired with a citation.

    Deliberately flexible so a single shape can carry either a CLB/NCLC conversion
    row (raw-score band ``min_score``..``max_score`` → ``level`` for a given
    ``ability``/``test_type``) or a points row (a ``level`` or years band
    ``years_min``..``years_max`` → ``points``). Every payload number a deterministic
    computation reads lives HERE, paired with ``citation_index`` — never as a bare
    literal in Python (RULE-02).
    """

    model_config = ConfigDict(extra="forbid")

    label: str | None = None            # free label (ability name, tier name)
    test_type: str | None = None        # for conversion rows: the language test
    ability: str | None = None          # for conversion rows: listening/reading/...
    level: str | int | None = None      # CLB/NCLC level or education level
    min_score: float | None = None      # inclusive lower bound of a raw-score band
    max_score: float | None = None      # inclusive upper bound of a raw-score band
    years_min: float | None = None      # inclusive lower bound of a years band
    years_max: float | None = None      # inclusive upper bound of a years band
    points: int | None = None           # awarded points for this row
    citation_index: int = 0


class FactRequirement(BaseModel):
    """One grounded fact predicate in a closed machine-check branch."""

    model_config = ConfigDict(extra="forbid")

    field: str
    operator: Literal[
        "present",
        "equals",
        "minimum",
        "maximum",
        "in",
        "matches_selected_noc",
        "on_or_before_reference",
        "on_or_after_reference",
    ]
    value: str | int | bool | list[str] | list[int] | None = None
    citation_index: int = 0


class RuleBranch(BaseModel):
    """A named all-facts-required policy branch."""

    model_config = ConfigDict(extra="forbid")

    label: str
    requirements: list[FactRequirement]
    citation_index: int = 0


class MachineCheck(BaseModel):
    """The machine-readable payload of a rule row — the ONLY place volatile numbers live.

    Every numeric threshold / cap / window / points value the deterministic logic
    (Plan 31-04) reads is carried here, each paired (directly or via a
    :class:`PointsEntry`/:class:`AcceptedValue` ``citation_index``) with a resolving
    :class:`Citation`. The static ``no_inlined_volatile_rules`` gate allow-lists
    exactly these values; the same number hard-coded in prose or a Python literal
    is a violation (RULE-02).
    """

    model_config = ConfigDict(extra="forbid")

    kind: MachineCheckKind
    field: str
    # accepted_enum
    accepted_values: list[AcceptedValue] | None = None
    # threshold
    min_value: float | None = None
    max_value: float | None = None
    # validity_window (+ policy effective window on dated rules)
    window_days: int | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    # cap
    cap_value: int | None = None
    # points_table / conversion
    points_by_level: list[PointsEntry] | None = None
    # policy_flag
    flag_value: bool | None = None
    # MEC duration, hours, hierarchy, and applicability payloads. Each entry owns
    # its citation index; no policy scalar is accepted through an untyped mapping.
    minimum_duration_months: PolicyValue | None = None
    minimum_hours: PolicyValue | None = None
    minimum_hours_per_week: PolicyValue | None = None
    maximum_hours_per_week: PolicyValue | None = None
    lookback_years: PolicyValue | None = None
    included_hierarchy: list[PolicyValue] | None = None
    excluded_hierarchy: list[PolicyValue] | None = None
    applicability: list[PolicyValue] | None = None
    conditional_na: list[PolicyValue] | None = None
    branches: list[RuleBranch] | None = None
    # default citation index for a scalar payload (min/max/window/cap/flag)
    citation_index: int = 0


class VolatilityMeta(BaseModel):
    """Staleness / freshness metadata for a rule (Pitfall 4 — surface crawl_date).

    ``volatility`` marks whether the rule value is expected to drift (a points
    table, a policy date) or is stable (a definition). ``effective_from`` /
    ``effective_to`` carry ISO policy dates for dated rules such as the
    2025-03-25 arranged-employment repeal, so Plan 31-04's guard decides legacy
    applicability from grounded metadata, never a prose date.
    """

    model_config = ConfigDict(extra="forbid")

    volatility: Volatility
    source_family: str
    crawl_date: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None


class RuleRow(BaseModel):
    """One PII-free, corpus-grounded CRS rule row (ARCHITECTURE-v4.0 Pattern 3).

    Composes the query + selector + verbatim citations + machine check + volatility
    metadata into the single typed unit the whole Phase-31 machinery operates on. A
    row is only *usable* once its ``citations`` resolve and their quotes pass the
    shipped grounding gate — the registry engine (``crawler.crs_rules``) enforces
    that; this model enforces the SHAPE (fail-closed at load).

    ``gap`` marks a required grid slot whose exact rule text could NOT be grounded
    from the current corpus — a documented COVERAGE GAP, never a fabricated
    citation. A ``gap`` row still validates structurally (it carries a placeholder
    citation + note) but is excluded from grounding assertions and surfaced by
    ``coverage_report``.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    factor_group: FactorGroup
    factor_ids: list[str] = Field(min_length=1)
    check_type: CheckType
    query: str = Field(min_length=1)
    selector: Selector
    claim_text: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)
    machine_check: MachineCheck
    volatility: VolatilityMeta
    # Coverage-gap marker + human note (documented GAP, never a fabricated citation).
    gap: bool = False
    gap_reason: str | None = None

    @field_validator("rule_id")
    @classmethod
    def _rule_id_is_dotted(cls, v: str) -> str:
        """A rule_id is a dotted structural label (e.g. ``core.language.first``).

        Rejects whitespace so a stray space in a YAML key cannot silently create a
        near-duplicate id. Does NOT constrain the dotted depth (labels vary).
        """
        if v != v.strip() or any(c.isspace() for c in v):
            raise ValueError(f"rule_id must not contain whitespace: {v!r}")
        return v

    @model_validator(mode="after")
    def _citation_indices_in_range(self) -> RuleRow:
        """Every ``citation_index`` in the machine check must point at a real citation.

        A payload value paired with an out-of-range ``citation_index`` would claim
        grounding from a citation that does not exist — fail-closed at load.
        """
        n = len(self.citations)
        mc = self.machine_check

        def _check(idx: int, where: str) -> None:
            if idx < 0 or idx >= n:
                raise ValueError(
                    f"citation_index {idx} in {where} is out of range "
                    f"(row {self.rule_id!r} has {n} citation(s))"
                )

        _check(mc.citation_index, "machine_check")
        for av in mc.accepted_values or []:
            _check(av.citation_index, "accepted_values")
        for pe in mc.points_by_level or []:
            _check(pe.citation_index, "points_by_level")
        for field_name in (
            "minimum_duration_months",
            "minimum_hours",
            "minimum_hours_per_week",
            "maximum_hours_per_week",
            "lookback_years",
        ):
            item = getattr(mc, field_name)
            if item is not None:
                _check(item.citation_index, field_name)
        for field_name in (
            "included_hierarchy",
            "excluded_hierarchy",
            "applicability",
            "conditional_na",
        ):
            for item in getattr(mc, field_name) or []:
                _check(item.citation_index, field_name)
        for branch in mc.branches or []:
            _check(branch.citation_index, "branches")
            for requirement in branch.requirements:
                _check(requirement.citation_index, "branches.requirements")
        return self


class Registry(BaseModel):
    """A container of rule rows with a duplicate-rule_id guard (fail-closed at load)."""

    model_config = ConfigDict(extra="forbid")

    rows: list[RuleRow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_duplicate_rule_ids(self) -> Registry:
        seen: set[str] = set()
        dupes: list[str] = []
        for row in self.rows:
            if row.rule_id in seen:
                dupes.append(row.rule_id)
            seen.add(row.rule_id)
        if dupes:
            raise ValueError(f"duplicate rule_id(s) in registry: {sorted(set(dupes))}")
        return self
