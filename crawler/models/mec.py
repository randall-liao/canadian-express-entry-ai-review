"""Strict public/private contracts for minimum-entry-criteria screening.

The public models are a deliberately small PII-light projection.  Applicant
values, evidence identifiers, employment traces, and rendering details exist
only on the private criterion/report models and are copied field-by-field at
the single projection seam below.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from crawler.models.public_locator import MecRunId, require_exact_output_locator


Program = Literal["fsw", "fst", "cec"]
CriterionStatus = Literal["PASS", "FAIL", "AT-RISK", "N/A"]
ProgramStatus = Literal["MEETS", "DOES-NOT-MEET", "AT-RISK"]
OfferLmiaExemptionBasis = Literal[
    "international_agreement",
    "significant_benefit",
    "federal_provincial_agreement",
    "other_exempt",
    "not_exempt",
]

MecCriterionId = Literal[
    "fsw.work.primary_noc",
    "fsw.work.teer",
    "fsw.work.paid",
    "fsw.work.recency",
    "fsw.work.continuity_duration_hours",
    "fsw.work.noc_duties",
    "fsw.language.first",
    "fsw.education.minimum",
    "fsw.grid.language",
    "fsw.grid.education",
    "fsw.grid.experience",
    "fsw.grid.age",
    "fsw.grid.arranged_employment",
    "fsw.grid.adaptability",
    "fsw.grid.pass_mark",
    "fsw.funds.requirement",
    "fsw.destination.outside_quebec",
    "fst.work.trade_noc",
    "fst.work.same_noc",
    "fst.work.paid",
    "fst.work.qualified_to_practise",
    "fst.work.student_exclusion",
    "fst.work.recency_duration_hours",
    "fst.work.noc_duties_requirements",
    "fst.language.minimum",
    "fst.offer_or_certificate",
    "fst.funds.requirement",
    "fst.destination.outside_quebec",
    "cec.work.teer",
    "cec.work.in_canada",
    "cec.work.authorized_tr_status",
    "cec.work.paid",
    "cec.work.recency_duration_hours",
    "cec.work.student_exclusion",
    "cec.work.self_employment_exclusion",
    "cec.work.noc_duties",
    "cec.language.minimum",
    "cec.destination.outside_quebec",
]

# Public reasons are stable machine codes, never free-form applicant detail.
MecReasonCode = Literal[
    "criterion_satisfied",
    "confirmed_deterministic_failure",
    "evidence_missing",
    "evidence_unconfirmed",
    "scope_incomplete",
    "rule_unavailable",
    "rule_stale",
    "rule_out_of_window",
    "manual_noc_review",
    "manual_offer_review",
    "manual_study_review",
    "manual_physician_review",
    "funds_snapshot_unavailable",
    "unknown_criterion",
    "unknown_status",
    "criterion_unwired",
    "invalid_applicability",
    "composition_refused",
    "publication_refused",
    "not_applicable",
]

SCREENING_NOTICE = (
    "Minimum-entry-criteria screening is grounded in cited rules and is not "
    "legal advice or a final eligibility decision. Semantic fit, NOC-duty fit, "
    "and officer discretion remain manual and AT-RISK."
)

_CITATION_ID_PATTERN = r"^[^#\s]+#\d+$"
_PERIOD_ID_PATTERN = r"^mep_[0-9a-f]{32}$"


def _reject_unsafe_string(value: str) -> str:
    """Reject path/URI-shaped private values at the typed report boundary."""
    normalized = value.replace("\\", "/")
    if (
        value.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:[/\\]", value)
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value)
        or any(part == ".." for part in normalized.split("/"))
    ):
        raise ValueError("private report values must not contain paths or URIs")
    return value


def _walk_safe_strings(value: object) -> None:
    if isinstance(value, str):
        _reject_unsafe_string(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_unsafe_string(str(key))
            _walk_safe_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk_safe_strings(item)


class MecCounts(BaseModel):
    """Closed, PII-free status tallies exposed publicly."""

    model_config = ConfigDict(extra="forbid")

    criteria: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    at_risk: int = Field(default=0, ge=0)
    not_applicable: int = Field(default=0, ge=0)


class PublicMecCriterion(BaseModel):
    """One PII-light public criterion result."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: MecCriterionId
    status: CriterionStatus
    reason_code: MecReasonCode
    corpus_citation_ids: list[str] = Field(default_factory=list)

    @field_validator("corpus_citation_ids")
    @classmethod
    def _citations_are_public_corpus_ids(cls, values: list[str]) -> list[str]:
        import re

        for value in values:
            if value.startswith("ev_") or re.fullmatch(_CITATION_ID_PATTERN, value) is None:
                raise ValueError(
                    "corpus_citation_ids must contain corpus coordinates, not evidence ids"
                )
        return values


class PrivateApplicantValues(BaseModel):
    """Closed evaluator-owned applicant values retained only in the vault."""

    model_config = ConfigDict(extra="forbid")

    points: int | float | None = None


class PrivateEmploymentTrace(BaseModel):
    """Closed period trace; employer names and arbitrary nested values are impossible."""

    model_config = ConfigDict(extra="forbid")

    employment_period_id: str = Field(pattern=_PERIOD_ID_PATTERN)
    included: bool
    reason: Literal[
        "predicate_satisfied",
        "predicate_excluded",
        "noc_sidecar_manual",
        "same_noc_threshold_not_met",
        "physician_exception_manual",
    ]

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)

    def get(self, key: str, default: object = None) -> object:
        return getattr(self, key, default)


class PrivateNocSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noc_code: str | None = Field(default=None, pattern=r"^\d{5}$")
    duty_count: int | None = Field(default=None, ge=0)
    confirmed_count: int | None = Field(default=None, ge=0)
    status: Literal["AT-RISK", "GAP", "N/A"] | None = None
    reason: str | None = None
    citations: list[str] = Field(default_factory=list)


class PrivateOfferSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_present: bool | None = None
    eligibility_status: Literal["AT-RISK", "N/A"] | None = None
    crs_points: Literal[0] | None = None
    for_program_eligibility_only: bool | None = None
    reason: str | None = None
    citation: str | None = None


class PrivateStudySidecar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AT-RISK", "GAP", "N/A"] | None = None
    reason: str | None = None
    required_count: int | None = Field(default=None, ge=0)
    confirmed_count: int | None = Field(default=None, ge=0)
    eligible_count: int | None = Field(default=None, ge=0)
    as_of: str | None = None


class PrivateSidecarInputs(BaseModel):
    """Explicit locations for every sidecar value permitted in a criterion."""

    model_config = ConfigDict(extra="forbid")

    noc: dict[str, PrivateNocSidecar] | None = None
    offer: PrivateOfferSidecar | None = None
    study: PrivateStudySidecar | None = None
    physician_exception_claimed: bool | None = None
    offer_branch: Literal["N/A"] | None = None
    certificate_branch: Literal["PASS"] | None = None

    @field_validator("noc")
    @classmethod
    def _noc_keys_are_codes(
        cls, value: dict[str, PrivateNocSidecar] | None
    ) -> dict[str, PrivateNocSidecar] | None:
        if value is not None and any(re.fullmatch(r"\d{5}", key) is None for key in value):
            raise ValueError("NOC sidecar keys must be exact NOC codes")
        return value


class PrivateGridBounds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lower: int | float | None = None
    upper: int | float | None = None
    maximum: int | float | None = None

    def get(self, key: str, default: object = None) -> object:
        value = getattr(self, key, default)
        return default if value is None else value

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)


class PrivateCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work: bool | None = None
    offer_certificate: bool | None = None


class PrivateRenderDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_usability: Literal["usable", "rule_stale", "rule_out_of_window", "rule_unavailable"] | None = None
    registry_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class PrivateMecCriterion(BaseModel):
    """Vault-only criterion result, including evidence-bearing evaluation detail."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: MecCriterionId
    status: CriterionStatus
    reason_code: MecReasonCode
    corpus_citation_ids: list[str] = Field(default_factory=list)
    wired: bool
    grounded: bool
    applicability_grounded: bool
    applicable: bool | None
    rule_ids: list[str]
    applicant_values: PrivateApplicantValues
    evidence_ids: list[str]
    employment_traces: list[PrivateEmploymentTrace]
    sidecar_inputs: PrivateSidecarInputs
    grid_bounds: PrivateGridBounds
    completeness_attestations: PrivateCompleteness
    render_details: PrivateRenderDetails

    @model_validator(mode="after")
    def _status_proof_is_consistent(self) -> "PrivateMecCriterion":
        """Reject outcome objects that contradict their proof metadata."""
        if self.status == "PASS" and (
            self.reason_code != "criterion_satisfied"
            or not self.wired
            or not self.grounded
            or not self.applicability_grounded
            or self.applicable is not True
            or self.rule_ids != [self.criterion_id]
        ):
            raise ValueError(
                "PASS requires exact wired, grounded, applicable criterion proof"
            )
        if self.status == "FAIL" and (
            self.reason_code != "confirmed_deterministic_failure"
            or not self.wired
            or not self.applicability_grounded
            or self.applicable is not True
        ):
            raise ValueError(
                "FAIL requires a wired, grounded, applicable deterministic failure"
            )
        if self.status == "N/A" and (
            self.reason_code != "not_applicable"
            or not self.wired
            or not self.applicability_grounded
            or self.applicable is not False
        ):
            raise ValueError(
                "N/A requires wired, grounded deterministic inapplicability"
            )
        _walk_safe_strings(self.model_dump(mode="json"))
        return self


class PrivateMecReport(BaseModel):
    """Complete vault-only MEC report."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    run_id: str
    candidate_id: str
    program: Program
    status: ProgramStatus
    criteria: list[PrivateMecCriterion]
    counts: MecCounts
    registry_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str
    private_report_path: str

    @model_validator(mode="after")
    def _private_values_are_path_free(self) -> "PrivateMecReport":
        _walk_safe_strings(self.model_dump(mode="json"))
        return self


class PublicMecSummary(BaseModel):
    """The only MEC payload permitted at the public command boundary.

    Its legacy ``private_output_path`` field is an opaque locator interpreted
    relative to the selected candidate vault root, never a candidate-bearing path.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    run_id: MecRunId
    program: Program
    status: ProgramStatus
    criteria: list[PublicMecCriterion]
    counts: MecCounts
    registry_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_output_path: str
    screening_notice: Literal[
        "Minimum-entry-criteria screening is grounded in cited rules and is not legal advice or a final eligibility decision. Semantic fit, NOC-duty fit, and officer discretion remain manual and AT-RISK."
    ] = SCREENING_NOTICE

    @model_validator(mode="after")
    def _exact_private_output_path(self) -> "PublicMecSummary":
        require_exact_output_locator(
            self.private_output_path, "mec", self.program, "latest.json"
        )
        return self


def to_public_mec_summary(
    report: PrivateMecReport,
    private_output_path: str,
) -> PublicMecSummary:
    """Project a private report through an explicit PII-light field allowlist."""
    return PublicMecSummary(
        schema_version=report.schema_version,
        run_id=report.run_id,
        program=report.program,
        status=report.status,
        criteria=[
            PublicMecCriterion(
                criterion_id=criterion.criterion_id,
                status=criterion.status,
                reason_code=criterion.reason_code,
                corpus_citation_ids=list(criterion.corpus_citation_ids),
            )
            for criterion in report.criteria
        ],
        counts=report.counts.model_copy(deep=True),
        registry_fingerprint=report.registry_fingerprint,
        private_output_path=private_output_path,
        screening_notice=SCREENING_NOTICE,
    )
