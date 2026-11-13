"""Committed, PII-safe Phase 74 final evidence publication and validation."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    field_validator,
)

from crawler import searchindex
from crawler.eval.agent_runtime import (
    AgentRuntimeError,
    validate_persisted_agent_provenance,
)
from crawler.eval.holdout_splitter import split_doc_type_cases
from crawler.eval.genuine_optimizer import (
    _OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
    derive_optimizer_candidate_id,
)
from crawler.eval.patch_evaluator import validate_target_allowlist
from crawler.eval.pipeline_judge import (
    _JUDGE_PROMPT_CONTRACT,
    _JUDGE_PROVENANCE_EXTRA_FIELDS,
    build_judge_input_manifest,
)
from crawler.eval.pipeline_worker import (
    _WORKER_PROVENANCE_EXTRA_FIELDS,
    build_worker_input_manifest,
)
from crawler.eval.public_bundle import DOC_TYPE_TO_SKILL, build_public_review_bundle
from crawler.synthetic.schemas import ExpressEntryDocType


_HASH = re.compile(r"^[a-f0-9]{64}$")
_REVISION = re.compile(r"^[a-f0-9]{40,64}$")
_CASE_ID = re.compile(r"^[a-f0-9]{32}$")
_SCORE_FIELDS = (
    "grounding_accuracy",
    "citation_exactness",
    "defect_recall",
    "pii_containment",
    "blind_input_compliance",
)
_TRAILER = "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
PHASE74_SDK_VERSION = "1.0.8"
PHASE74_RUNTIME_VERSION = "1.0.73"
PHASE74_PROTOCOL_VERSION = "3"
PHASE74_WORKER_MODEL = "gemini-3.6-flash"
PHASE74_JUDGE_MODEL = "claude-opus-4.8"
PHASE74_JUDGE_EFFORT = "xhigh"
PHASE74_CONTEXT_TIER = "long_context"
EXPECTED_WORKER_SOURCE_PATHS = frozenset(
    {
        f"skills/document-agents/{DOC_TYPE_TO_SKILL[doc_type.value]}.md"
        for doc_type in ExpressEntryDocType
    }
    | {"skills/pdf/SKILL.md"}
)
PHASE74_CITATION_SET_HASH = (
    "c6a01948386711fd259ec112c20e5a90a78567de67bf0fc1b41c1695810e2105"
)
PHASE74_JUDGE_BINDING_SET_HASH = (
    "324ff53e4556a49da6fdf9c44bfe52ff8b1e6fb0e53da2bd2d22112b3fa9e5b1"
)
PHASE74_SANITIZER_SCHEMA_VERSION = "phase74-sanitized-judge-payload-v1"
Sha256 = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]
CommitId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{40,64}$"),
]
CandidateId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^candidate_[0-9a-f]{12}$"),
]
CaseId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{32}$"),
]
RunId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^sdk-[0-9TZ-]+-[0-9a-f]{12}(?:-[a-z-]+)?$"),
]
DocType = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]+$"),
]
RelativeTarget = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=r"^(?:AGENTS\.md|skills/(?:pdf/SKILL\.md|document-agents/[a-z0-9-]+\.md))$",
    ),
]
PublicCitationId = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=r"^[a-z0-9][a-z0-9_./-]*\.md#[0-9]{3}$",
    ),
]
_EXPECTED_ACCEPTED_BINDINGS = (
    ("b2dfc21cd33557911363bb61ded323b3d1c7a4fb", "sdk-20260725T182627Z-60d5e7a01d43", "digital_photo", "candidate_16413b799fc9", "skills/document-agents/digital-photos.md"),
    ("9b5b8b55583a1f6ed97af492100d564fa3a29ac8", "sdk-20260725T182627Z-60d5e7a01d43", "letter_of_explanation", "candidate_930d1f058c90", "skills/document-agents/letter-of-explanation.md"),
    ("2c4000ecd1e666e71b1999e9d37f1a1cfb7fdf2d", "sdk-20260725T182627Z-60d5e7a01d43", "marriage_certificate", "candidate_766439d920e3", "skills/document-agents/marriage-certificate.md"),
    ("90d6aab27bfd44dacef5f659f77804f604be82f3", "sdk-20260725T182627Z-60d5e7a01d43", "medical_examination", "candidate_26dba5dfa663", "skills/document-agents/medical.md"),
    ("64e2e0a49bf3d1214bcf2f2c237f2d8adb284c8e", "sdk-20260725T182627Z-60d5e7a01d43", "proof_of_other_name", "candidate_1d50b9b836ba", "skills/document-agents/other-name.md"),
    ("1fe4e35421e751803356e99e2da1ef61ac3d025b", "sdk-20260725T182627Z-60d5e7a01d43", "proof_of_studies", "candidate_c0fbd7f92e17", "skills/document-agents/proof-of-studies.md"),
    ("7975782565b94dba78f94dc3d5ca3ba38b8acd09", "sdk-20260725T213116Z-96cac59dabcb", "medical_examination", "candidate_5641f8ff188e", "skills/document-agents/medical.md"),
    ("06071757e8f64fe86b15df3000ae2790b64006bc", "sdk-20260726T005337Z-14e36ab1aa5f", "employment_reference_letter", "candidate_d394bfe38bfd", "skills/document-agents/employment-reference-letter.md"),
    ("bbe1e46fd9a6339d33761557cea2e2589d0affa9", "sdk-20260726T005337Z-14e36ab1aa5f", "letter_of_explanation", "candidate_f7fc1ecffaff", "skills/document-agents/letter-of-explanation.md"),
    ("a2c6497df92c19bcf86237cccc81bb0207486828", "sdk-20260726T230431Z-ea657d2706b3", "letter_of_explanation", "candidate_e5436c87d7f6", "skills/document-agents/letter-of-explanation.md"),
    ("b00e9cf65225aee44b2dcc8eece7de8540755367", "sdk-20260727T030015Z-02472e3e132e", "proof_of_other_name", "candidate_8c80d8c13e40", "skills/document-agents/other-name.md"),
)
_LEGACY_PROVENANCE_FIELDS = (
    "engine",
    "sdk_version",
    "runtime_protocol_version",
    "role",
    "model",
    "effort",
    "context_tier",
    "session_id",
    "prompt_hash",
    "attachment_hashes",
    "output_hash",
    "started_at",
    "completed_at",
    "duration_seconds",
    "terminal_event",
    "is_live",
    "retry_classification",
)
_PII_OR_PATH = re.compile(
    r"Jane Synthetic|John Synthetic|Jane Doe|John Doe|X99999999|Y88888888|"
    r"\b\d{3}[- ]?\d{3}[- ]?\d{3}\b|/(?:home|Users)/|[A-Za-z]:\\Users\\",
    re.IGNORECASE,
)
_FORBIDDEN_EVIDENCE_KEYS = {
    "basis",
    "question",
    "claims",
    "abstentions",
    "prose",
    "findings",
    "rationale",
    "patch_recommendations",
    "raw_prompt",
    "reasoning",
    "content",
    "path",
    "pid",
}


class EvidenceValidationError(RuntimeError):
    """Committed evidence is incomplete, inconsistent, or tampered."""


class _StrictEvidenceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        strict=True,
    )


class ScoreMetrics(_StrictEvidenceModel):
    grounding_accuracy: float = Field(ge=0.0, le=1.0)
    citation_exactness: float = Field(ge=0.0, le=1.0)
    defect_recall: float = Field(ge=0.0, le=1.0)
    pii_containment: float = Field(ge=0.0, le=1.0)
    blind_input_compliance: float = Field(ge=0.0, le=1.0)
    overall_score: float = Field(ge=0.0, le=1.0)

    @field_validator("*")
    @classmethod
    def finite(cls, value: float) -> float:
        if not isinstance(value, (int, float)) or not float("-inf") < value < float("inf"):
            raise ValueError("metric must be finite")
        return float(value)

    @field_validator("*", mode="before")
    @classmethod
    def numeric_not_bool(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("metric must be numeric and not boolean")
        return value


class MetricDeltas(_StrictEvidenceModel):
    grounding_accuracy: float = Field(ge=-1.0, le=1.0)
    citation_exactness: float = Field(ge=-1.0, le=1.0)
    defect_recall: float = Field(ge=-1.0, le=1.0)
    pii_containment: float = Field(ge=-1.0, le=1.0)
    blind_input_compliance: float = Field(ge=-1.0, le=1.0)
    overall_score: float = Field(ge=-1.0, le=1.0)

    @field_validator("*")
    @classmethod
    def finite(cls, value: float) -> float:
        if not isinstance(value, (int, float)) or not float("-inf") < value < float("inf"):
            raise ValueError("delta must be finite")
        return float(value)

    @field_validator("*", mode="before")
    @classmethod
    def numeric_not_bool(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("delta must be numeric and not boolean")
        return value


class CaseScores(_StrictEvidenceModel):
    grounding_accuracy: float = Field(ge=0.0, le=1.0)
    citation_exactness: float = Field(ge=0.0, le=1.0)
    defect_recall: float = Field(ge=0.0, le=1.0)
    pii_containment: float = Field(ge=0.0, le=1.0)
    blind_input_compliance: float = Field(ge=0.0, le=1.0)

    @field_validator("*", mode="before")
    @classmethod
    def finite_numeric(cls, value: Any) -> Any:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not float("-inf") < value < float("inf")
        ):
            raise ValueError("case score must be finite numeric")
        return value


class RoleModelConfig(_StrictEvidenceModel):
    role: Literal["judge"]
    model: Literal["claude-opus-4.8"]
    effort: Literal["xhigh"]
    context_tier: Literal["long_context"]
    timeout_seconds: Literal[900]


class CanonicalProvenance(_StrictEvidenceModel):
    engine: Literal["copilot-sdk"]
    is_live: Literal[True]
    sdk_version: Literal["1.0.8"]
    runtime_protocol_version: Literal["3"]
    role: Literal["worker", "judge", "optimizer"]
    model: Literal["gemini-3.6-flash", "claude-opus-4.8"]
    effort: Literal["xhigh"] | None
    context_tier: Literal["long_context"]
    session_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]
    prompt_hash: Sha256
    attachment_hashes: list[Sha256]
    output_hash: Sha256
    started_at: Annotated[str, StringConstraints(strict=True)]
    completed_at: Annotated[str, StringConstraints(strict=True)]
    duration_seconds: FiniteFloat = Field(ge=0.0)
    terminal_event: Literal["assistant.message"]
    retry_classification: None
    turn_count: int | None = None
    format_correction_count: int | None = None
    initial_prompt_hash: Sha256 | None = None
    correction_prompt_hashes: list[Sha256] | None = None
    assistant_response_hash_chain: list[Sha256] | None = None
    turn_session_ids: list[str] | None = None
    correction_kind: str | None = None
    provenance_digest: Sha256
    input_pdf_sha256: Sha256 | None = None
    allowed_text_sha256: Sha256 | None = None
    bundle_hash: Sha256 | None = None
    answer_hash: Sha256 | None = None
    pii_manifest_hash: Sha256 | None = None
    pii_manifest_count: int | None = None
    pii_manifest_categories: dict[str, int] | None = None
    prompt_contract_hash: Sha256 | None = None
    input_manifest_hash: Sha256 | None = None
    case_ids: list[CaseId] | None = None
    pdf_hashes: list[Sha256] | None = None
    worker_report_hashes: list[Sha256] | None = None
    worker_input_manifest_hashes: list[Sha256] | None = None
    public_bundle_hashes: list[Sha256] | None = None
    worker_prompt_hashes: list[Sha256] | None = None
    research_hash: Sha256 | None = None
    ground_truth_hash: Sha256 | None = None
    model_configuration: RoleModelConfig | None = Field(
        default=None,
        alias="model_config",
    )
    artifact_output_hash: Sha256 | None = None
    input_findings_sha256: Sha256 | None = None
    candidate_content_hash: Sha256 | None = None
    candidate_id: CandidateId | None = None
    target_file: RelativeTarget | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def aware_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() is None
            or parsed.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamp must be UTC")
        return value


class WorkerRecord(_StrictEvidenceModel):
    schema_version: Literal["phase74-final-worker-record-v1"]
    case_id: CaseId
    doc_type: DocType
    report_hash: Sha256
    output_hash: Sha256
    answer_hash: Sha256
    runtime_version: Literal["1.0.73"]
    provenance: CanonicalProvenance
    final_revision: CommitId
    final_manifest_hash: Sha256
    bundle_hash: Sha256
    citation_ids: list[PublicCitationId]
    citation_id_hashes: list[Sha256]
    evidence_hash: Sha256

    @field_validator("citation_ids")
    @classmethod
    def safe_citations(cls, values: list[str]) -> list[str]:
        if any(".." in value for value in values):
            raise ValueError("citation ID traversal is forbidden")
        return values


class JudgeInputManifest(_StrictEvidenceModel):
    schema_version: Literal["judge-input-manifest-v2"]
    doc_type: DocType
    case_ids: list[CaseId]
    pdf_hashes: list[Sha256]
    worker_report_hashes: list[Sha256]
    worker_input_manifest_hashes: list[Sha256]
    public_bundle_hashes: list[Sha256]
    worker_prompt_hashes: list[Sha256]
    research_hash: Sha256
    ground_truth_hash: Sha256
    prompt_contract_hash: Sha256
    model_configuration: RoleModelConfig = Field(alias="model_config")


class SanitizedJudgeEvaluationPayload(_StrictEvidenceModel):
    schema_version: Literal["phase74-sanitized-judge-payload-v1"]
    doc_type: DocType
    case_ids: list[CaseId]
    case_count: int
    case_evaluations: dict[CaseId, CaseScores]
    aggregate_metrics: ScoreMetrics
    finding_count: int
    patch_recommendation_count: int


class JudgeRecord(_StrictEvidenceModel):
    schema_version: Literal["phase74-final-judge-record-v1"]
    doc_type: DocType
    case_ids: list[CaseId]
    case_count: int
    input_manifest: JudgeInputManifest
    sanitized_evaluation_payload: SanitizedJudgeEvaluationPayload
    raw_output_hash: Sha256
    artifact_output_hash: Sha256
    sanitization_binding_hash: Sha256
    sanitizer_schema_version: Literal["phase74-sanitized-judge-payload-v1"]
    runtime_version: Literal["1.0.73"]
    provenance: CanonicalProvenance
    final_revision: CommitId
    final_manifest_hash: Sha256
    evidence_hash: Sha256


class TurnEvidence(_StrictEvidenceModel):
    schema_name: Literal[
        "legacy-one-turn-v1",
        "canonical-turn-v1",
    ] = Field(alias="schema")
    turn_count: int
    format_correction_count: int
    correction_kind: str | None
    initial_prompt_hash: Sha256
    correction_prompt_hashes: list[Sha256]
    assistant_response_hash_chain: list[Sha256]
    turn_session_ids: list[str]
    raw_provenance_hash: Sha256


class AcceptedPatchRecord(_StrictEvidenceModel):
    schema_version: Literal["phase74-accepted-patch-evidence-v1"]
    sequence: int
    doc_type: DocType
    target_file: RelativeTarget
    commit: CommitId
    candidate_id: CandidateId
    candidate_content_hash: Sha256
    source_before_hash: Sha256
    source_after_hash: Sha256
    source_revision: CommitId
    optimizer_output_hash: Sha256
    optimizer_response_hash: Sha256
    optimizer_provenance: CanonicalProvenance
    optimizer_turn_evidence: TurnEvidence
    runtime_version: Literal["1.0.73"]
    baseline_train: ScoreMetrics
    candidate_train: ScoreMetrics
    training_deltas: MetricDeltas
    baseline_holdout: ScoreMetrics
    candidate_holdout: ScoreMetrics
    holdout_deltas: MetricDeltas
    allowlist_passed: bool
    cas_source_hash: Sha256
    non_regression_accepted: bool
    decision_reason: Literal["metric_gate_accepted"]
    decision_output_hash: Sha256
    decision_binding_hash: Sha256
    run_id: RunId
    parent_run_id: RunId
    run_manifest_hash: Sha256
    run_binding_hash: Sha256
    completed_run_id: RunId
    completed_supervisor_result_hash: Sha256
    final_manifest_hash: Sha256
    evidence_hash: Sha256


class RejectedPatchRecord(_StrictEvidenceModel):
    schema_version: Literal["phase74-rejected-patch-evidence-v1"]
    doc_type: DocType
    target_file: RelativeTarget
    candidate_id: CandidateId
    candidate_content_hash: Sha256
    source_hash: Sha256
    source_revision: CommitId
    optimizer_output_hash: Sha256
    optimizer_response_hash: Sha256
    optimizer_provenance: CanonicalProvenance
    optimizer_turn_evidence: TurnEvidence
    runtime_version: Literal["1.0.73"]
    decision_output_hash: Sha256
    decision_binding_hash: Sha256
    reason_code: Literal["metric_gate_rejected", "candidate_evaluation_failed"]
    baseline_train: ScoreMetrics | None
    candidate_train: ScoreMetrics | None
    training_deltas: MetricDeltas | None
    baseline_holdout: ScoreMetrics | None
    candidate_holdout: ScoreMetrics | None
    holdout_deltas: MetricDeltas | None
    run_id: RunId
    parent_run_id: RunId
    run_manifest_hash: Sha256
    run_binding_hash: Sha256
    completed_supervisor_result_hash: Sha256
    final_manifest_hash: Sha256
    evidence_hash: Sha256


class AcceptedPatchCollection(_StrictEvidenceModel):
    schema_version: Literal["phase74-cumulative-accepted-patches-v1"]
    records: list[AcceptedPatchRecord]
    evidence_hash: Sha256


class RejectedPatchCollection(_StrictEvidenceModel):
    schema_version: Literal["phase74-final-run-rejected-patches-v1"]
    records: list[RejectedPatchRecord]
    evidence_hash: Sha256


class SharedEvaluationRecord(_StrictEvidenceModel):
    schema_version: Literal["phase74-shared-evaluation-record-v1"]
    doc_type: DocType
    status: Literal["completed"]
    decision: Literal["rejected"]
    decision_reason: Literal["metric_gate_non_acceptance"]
    baseline_worker_output_hash: Sha256
    baseline_judge_output_hash: Sha256
    candidate_worker_output_hash: Sha256
    candidate_judge_output_hash: Sha256
    training_count: int = Field(gt=0)
    holdout_count: Literal[4]
    baseline_train: ScoreMetrics
    candidate_train: ScoreMetrics
    training_deltas: MetricDeltas
    baseline_holdout: ScoreMetrics
    candidate_holdout: ScoreMetrics
    holdout_deltas: MetricDeltas
    shared_candidate_id: CandidateId
    shared_candidate_hash: Sha256
    shared_decision_hash: Sha256
    shared_run_id: RunId
    shared_target_file: Literal["skills/pdf/SKILL.md"]
    shared_source_revision: CommitId
    shared_input_findings_hash: Sha256
    shared_prompt_hash: Sha256
    shared_optimizer_output_hash: Sha256
    runtime_version: Literal["1.0.73"]
    shared_optimizer_provenance: CanonicalProvenance
    final_revision: CommitId
    final_manifest_hash: Sha256
    evidence_hash: Sha256


class SharedDecisionEvidence(_StrictEvidenceModel):
    schema_version: Literal["phase74-shared-decision-evidence-v1"]
    run_id: RunId
    decision: Literal["rejected"]
    applied_commit: None
    shared_decision_hash: Sha256
    target_file: RelativeTarget
    source_hash: Sha256
    source_revision: CommitId
    candidate_id: CandidateId
    candidate_content_hash: Sha256
    input_findings_hash: Sha256
    prompt_hash: Sha256
    optimizer_output_hash: Sha256
    optimizer_provenance: CanonicalProvenance
    runtime_version: Literal["1.0.73"]
    baseline_train: ScoreMetrics
    candidate_train: ScoreMetrics
    training_deltas: MetricDeltas
    baseline_holdout: ScoreMetrics
    candidate_holdout: ScoreMetrics
    holdout_deltas: MetricDeltas
    final_manifest_hash: Sha256
    evidence_hash: Sha256


class ConcurrencyEvent(_StrictEvidenceModel):
    sequence: int = Field(gt=0)
    timestamp: Annotated[str, StringConstraints(strict=True)]
    event: Literal["start", "end"]
    doc_type: Annotated[str, StringConstraints(strict=True, pattern=r"^(?:__[a-z]+__|[a-z][a-z0-9_]+)$")]
    phase: Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z-]+$")]
    role: Literal["preflight", "document_pipeline"]
    process_kind: Literal["sdk_preflight", "document_child"]
    run_id: RunId
    process_instance_hash: Sha256
    active_before: int
    active_after: int

    @field_validator("timestamp")
    @classmethod
    def aware_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() is None
            or parsed.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamp must be UTC")
        return value


class ConcurrencyEvidence(_StrictEvidenceModel):
    schema_version: Literal["phase74-concurrency-evidence-v1"]
    declared_peak: Literal[5]
    slot_limit: Literal[5]
    events: list[ConcurrencyEvent]
    distinct_documents: list[DocType]
    process_instance_count: Literal[93]
    stage_instance_counts: dict[str, int]
    evidence_hash: Sha256


class CleanupEvidence(_StrictEvidenceModel):
    schema_version: Literal["phase74-cleanup-evidence-v1"]
    run_id: RunId
    supervisor_status: Literal["completed"]
    lease_status: Literal["released"]
    registry_record_count: Literal[93]
    registry_reaped_count: Literal[93]
    survivor_count: Literal[0]
    error_count: Literal[0]
    cleanup_audit_count: Literal[0]
    cleanup_audit_hashes: list[Sha256]
    supervisor_result_hash: Sha256
    registry_hash: Sha256
    process_instance_hashes: list[Sha256]
    reconciled_at: Annotated[str, StringConstraints(strict=True)]
    evidence_hash: Sha256

    @field_validator("reconciled_at")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() is None
            or parsed.utcoffset() != timedelta(0)
        ):
            raise ValueError("reconciliation timestamp must be UTC")
        return value


class CitationCommitment(_StrictEvidenceModel):
    citation_id: PublicCitationId
    citation_id_hash: Sha256
    chunk_text_hash: Sha256

    @field_validator("citation_id")
    @classmethod
    def safe_citation(cls, value: str) -> str:
        if ".." in value:
            raise ValueError("citation ID traversal is forbidden")
        return value


class TrackedInputCommitment(_StrictEvidenceModel):
    relative_file: Annotated[
        str,
        StringConstraints(
            strict=True,
            pattern=r"^crawler/eval/pipelines/[a-z0-9_]+/(?:research/research|ground_truth/ground_truth)\.json$",
        ),
    ]
    file_hash: Sha256
    canonical_json_hash: Sha256


class CorpusCommitmentEvidence(_StrictEvidenceModel):
    schema_version: Literal["phase74-corpus-commitment-v1"]
    db_hash: Sha256
    citations: list[CitationCommitment]
    citation_set_hash: Sha256
    bundle_citation_ids: dict[DocType, list[PublicCitationId]]
    bundle_hashes: dict[DocType, Sha256]
    tracked_inputs: list[TrackedInputCommitment]
    source_hashes: dict[str, Sha256]
    final_revision: CommitId
    final_manifest_hash: Sha256
    evidence_hash: Sha256


class FinalManifestData(_StrictEvidenceModel):
    schema_version: Literal["phase74-final-manifest-v1"]
    run_id: RunId
    git_revision: CommitId
    bundle_hashes: dict[DocType, Sha256]
    source_hashes: dict[str, Sha256]
    optimization_complete: Literal[True]
    created_at: Annotated[str, StringConstraints(strict=True)]
    manifest_hash: Sha256

    @field_validator("created_at")
    @classmethod
    def aware_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() is None
            or parsed.utcoffset() != timedelta(0)
        ):
            raise ValueError("timestamp must be UTC")
        return value


class FrozenManifestEvidence(_StrictEvidenceModel):
    schema_version: Literal["phase74-frozen-manifest-evidence-v1"]
    final_manifest: FinalManifestData
    evidence_hash: Sha256


class EvidenceManifest(_StrictEvidenceModel):
    schema_version: Literal["phase74-committed-evidence-v1"]
    run_id: RunId
    engine: Literal["copilot-sdk"]
    sdk_version: Literal["1.0.8"]
    runtime_version: Literal["1.0.73"]
    protocol_version: Literal["3"]
    worker_model: Literal["gemini-3.6-flash"]
    judge_model: Literal["claude-opus-4.8"]
    judge_effort: Literal["xhigh"]
    context_tier: Literal["long_context"]
    document_types: list[DocType]
    worker_count: Literal[236]
    judge_count: Literal[23]
    optimizer_count: Literal[23]
    shared_evaluation_count: Literal[23]
    imported_model_artifact_count: Literal[0]
    final_revision: CommitId
    final_manifest_hash: Sha256
    bundle_hashes: dict[DocType, Sha256]
    source_hashes: dict[str, Sha256]
    accepted_patch_count: Literal[11]
    final_run_accepted_patch_count: Literal[0]
    final_run_rejected_patch_count: Literal[23]
    concurrency_hash: Sha256
    cleanup_hash: Sha256
    shared_decision_hash: Sha256
    frozen_manifest_evidence_hash: Sha256
    corpus_commitment_hash: Sha256
    judge_binding_set_hash: Sha256
    document_case_ids: dict[DocType, list[CaseId]]
    files: dict[str, Sha256]
    manifest_hash: Sha256


class DocumentEvidenceLink(_StrictEvidenceModel):
    schema_version: Literal["phase74-committed-evidence-link-v1"]
    doc_type: DocType
    evidence_root: Literal["crawler/eval/phase74_evidence"]
    evidence_manifest_hash: Sha256
    document_files: dict[str, Sha256]
    final_revision: CommitId
    final_manifest_hash: Sha256


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def canonical_evidence_hash(value: dict[str, Any]) -> str:
    """Hash an evidence object excluding its own self-hash fields."""
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"evidence_hash", "manifest_hash"}
    }
    return _canonical_hash(payload)


def _assert_sanitized_schema(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = _FORBIDDEN_EVIDENCE_KEYS.intersection(value)
        if forbidden:
            raise EvidenceValidationError(
                f"Evidence contains forbidden fields: {sorted(forbidden)}"
            )
        for item in value.values():
            _assert_sanitized_schema(item)
    elif isinstance(value, list):
        for item in value:
            _assert_sanitized_schema(item)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(_canonical_json(value) + "\n", encoding="utf-8")
    partial.replace(path)


def _write_evidence(path: Path, value: dict[str, Any]) -> None:
    value = dict(value)
    value["evidence_hash"] = canonical_evidence_hash(value)
    _write_json(path, value)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_tracked_confined_file(
    source_root: Path,
    expected_root: Path,
    path: Path,
) -> Path:
    if path.is_symlink() or any(
        parent.is_symlink()
        for parent in [path.parent, *path.parents]
        if parent != parent.parent
        and (
            parent == source_root
            or parent.is_relative_to(source_root)
        )
    ):
        raise EvidenceValidationError("Tracked evidence input contains a symlink")
    resolved_root = expected_root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(resolved_root):
        raise EvidenceValidationError("Tracked evidence input escaped confinement")
    relative = resolved.relative_to(source_root.resolve(strict=True)).as_posix()
    try:
        _run_git(source_root, "ls-files", "--error-unmatch", relative)
    except subprocess.CalledProcessError as error:
        raise EvidenceValidationError("Evidence input is not git-tracked") from error
    return resolved


def _run_git(source_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=source_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _git_blob_hash(source_root: Path, revision: str, target: str) -> str:
    content = subprocess.run(
        ["git", "show", f"{revision}:{target}"],
        cwd=source_root,
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(content).hexdigest()


def _validate_frozen_worker_source(
    source_root: Path,
    revision: str,
    source_hashes: Any,
) -> None:
    """Bind the frozen Git blobs and current release bytes to one exact set."""
    if (
        not isinstance(source_hashes, dict)
        or set(source_hashes) != EXPECTED_WORKER_SOURCE_PATHS
    ):
        raise EvidenceValidationError("Frozen Worker source inventory mismatch")
    resolved_root = source_root.resolve(strict=True)
    for target in sorted(EXPECTED_WORKER_SOURCE_PATHS):
        expected_hash = source_hashes[target]
        current = source_root / target
        if (
            not isinstance(expected_hash, str)
            or not _HASH.fullmatch(expected_hash)
            or current.is_symlink()
            or any(
                parent.is_symlink()
                for parent in current.parents
                if parent == source_root or parent.is_relative_to(source_root)
            )
        ):
            raise EvidenceValidationError("Frozen source hash mismatch")
        try:
            resolved = current.resolve(strict=True)
            git_hash = _git_blob_hash(source_root, revision, target)
        except (FileNotFoundError, OSError, subprocess.CalledProcessError) as error:
            raise EvidenceValidationError("Frozen source hash mismatch") from error
        if (
            not resolved.is_file()
            or not resolved.is_relative_to(resolved_root)
            or git_hash != expected_hash
            or _file_hash(resolved) != expected_hash
        ):
            raise EvidenceValidationError("Frozen source hash mismatch")


def _find_patch_commit(
    source_root: Path,
    *,
    target: str,
    source_before_hash: str,
    source_after_hash: str,
) -> str | None:
    commits = _run_git(
        source_root,
        "log",
        "--format=%H",
        "--all",
        "--",
        target,
    ).splitlines()
    for commit in commits:
        try:
            after = _git_blob_hash(source_root, commit, target)
            parent = _run_git(source_root, "rev-parse", f"{commit}^").strip()
            before = _git_blob_hash(source_root, parent, target)
            changed = [
                value
                for value in _run_git(
                    source_root,
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    commit,
                ).splitlines()
                if value
            ]
        except (subprocess.CalledProcessError, IndexError):
            continue
        if (
            before == source_before_hash
            and after == source_after_hash
            and changed == [target]
        ):
            return commit
    return None


def _load_artifact(doc_root: Path, stage: str) -> tuple[dict[str, Any], str]:
    path = doc_root / "artifacts" / f"{stage}.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if (
        artifact.get("schema_version") != "document-pipeline-artifact-v1"
        or artifact.get("stage") != stage
        or not isinstance(artifact.get("output"), dict)
        or artifact.get("output_hash") != _canonical_hash(artifact["output"])
    ):
        raise EvidenceValidationError(f"Raw artifact is invalid: {path.name}")
    return artifact["output"], artifact["output_hash"]


def _mean_metrics(evaluations: dict[str, Any], case_ids: set[str]) -> dict[str, float]:
    if not case_ids or not case_ids.issubset(evaluations):
        raise EvidenceValidationError("Metric evidence has incomplete coverage")
    ordered_case_ids = sorted(case_ids)
    result = {
        field: sum(
            float(evaluations[case_id][field]) for case_id in ordered_case_ids
        )
        / len(ordered_case_ids)
        for field in _SCORE_FIELDS
    }
    result["overall_score"] = sum(result.values()) / len(result)
    return result


def _metric_delta(
    candidate: dict[str, float],
    baseline: dict[str, float],
) -> dict[str, float]:
    return {
        field: candidate[field] - baseline[field]
        for field in (*_SCORE_FIELDS, "overall_score")
    }


def _citation_commitment_set_hash(
    records: list[dict[str, Any]],
) -> str:
    return _canonical_hash(
        [
            (
                record["citation_id"],
                record["citation_id_hash"],
                record["chunk_text_hash"],
            )
            for record in records
        ]
    )


def _judge_binding_set_hash(
    records: list[dict[str, str]],
) -> str:
    return _canonical_hash(
        [
            (
                record["doc_type"],
                record["raw_output_hash"],
                record["artifact_output_hash"],
                record["input_manifest_hash"],
                record["sanitizer_schema_version"],
                record["sanitization_binding_hash"],
            )
            for record in sorted(records, key=lambda item: item["doc_type"])
        ]
    )


def _validate_metric_delta(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    stored: dict[str, Any],
    *,
    label: str,
) -> None:
    ScoreMetrics.model_validate(baseline)
    ScoreMetrics.model_validate(candidate)
    MetricDeltas.model_validate(stored)
    computed = _metric_delta(candidate, baseline)
    if set(stored) != set(computed) or any(
        abs(float(stored[field]) - computed[field]) > 1e-9
        for field in computed
    ):
        raise EvidenceValidationError(f"{label} metric delta mismatch")


def _patch_would_be_accepted(record: dict[str, Any]) -> bool:
    training = record["training_deltas"]
    holdout = record["holdout_deltas"]
    training_safety_fields = (
        "grounding_accuracy",
        "citation_exactness",
        "pii_containment",
        "blind_input_compliance",
    )
    return (
        training["overall_score"] > 1e-6
        and all(
            training[field] >= -1e-6
            for field in training_safety_fields
        )
        and all(
            holdout[field] >= -1e-6
            for field in (*_SCORE_FIELDS, "overall_score")
        )
    )


def _turn_evidence(provenance: dict[str, Any]) -> dict[str, Any]:
    legacy = "turn_count" not in provenance
    return {
        "schema": (
            "legacy-one-turn-v1" if legacy else "canonical-turn-v1"
        ),
        "turn_count": provenance.get("turn_count", 1),
        "format_correction_count": provenance.get(
            "format_correction_count",
            0,
        ),
        "correction_kind": provenance.get("correction_kind"),
        "initial_prompt_hash": provenance.get(
            "initial_prompt_hash",
            provenance["prompt_hash"],
        ),
        "correction_prompt_hashes": provenance.get(
            "correction_prompt_hashes",
            [],
        ),
        "assistant_response_hash_chain": provenance.get(
            "assistant_response_hash_chain",
            [provenance["output_hash"]],
        ),
        "turn_session_ids": provenance.get(
            "turn_session_ids",
            [provenance["session_id"]],
        ),
        "raw_provenance_hash": _canonical_hash(provenance),
    }


def _validate_optimizer_provenance_evidence(
    provenance: dict[str, Any],
    turn_evidence: dict[str, Any] | None,
) -> None:
    try:
        validate_persisted_agent_provenance(
            provenance,
            expected_engine="copilot-sdk",
            expected_is_live=True,
            role="optimizer",
            model="gemini-3.6-flash",
            effort=None,
            context_tier="long_context",
            prompt_hash=provenance["prompt_hash"],
            attachment_hashes=[],
            output_hash=provenance["output_hash"],
            extra_digest_fields=_OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
            required_hash_fields=(
                "input_findings_sha256",
                "candidate_content_hash",
            ),
        )
        expected_turn = _turn_evidence(provenance)
    except AgentRuntimeError:
        if not isinstance(turn_evidence, dict) or turn_evidence.get(
            "schema"
        ) != "legacy-one-turn-v1":
            raise
        fields = (
            *_LEGACY_PROVENANCE_FIELDS,
            *_OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
        )
        digest = _canonical_hash(
            {field: provenance.get(field) for field in fields}
        )
        if (
            provenance.get("engine") != "copilot-sdk"
            or provenance.get("is_live") is not True
            or provenance.get("role") != "optimizer"
            or provenance.get("model") != "gemini-3.6-flash"
            or provenance.get("effort") is not None
            or provenance.get("context_tier") != "long_context"
            or provenance.get("attachment_hashes") != []
            or provenance.get("terminal_event") != "assistant.message"
            or provenance.get("retry_classification") is not None
            or provenance.get("provenance_digest") != digest
        ):
            raise AgentRuntimeError("Legacy optimizer provenance is invalid")
        expected_turn = _turn_evidence(provenance)
    if turn_evidence != expected_turn:
        raise AgentRuntimeError("Optimizer turn evidence is invalid")
    if (
        provenance.get("sdk_version") != PHASE74_SDK_VERSION
        or provenance.get("runtime_protocol_version")
        != PHASE74_PROTOCOL_VERSION
        or provenance.get("model") != PHASE74_WORKER_MODEL
        or provenance.get("context_tier") != PHASE74_CONTEXT_TIER
    ):
        raise AgentRuntimeError("Optimizer runtime identity does not match Phase 74")


def _validate_runtime_constants(
    provenance: dict[str, Any],
    *,
    role: Literal["worker", "judge"],
) -> None:
    expected_model = (
        PHASE74_WORKER_MODEL if role == "worker" else PHASE74_JUDGE_MODEL
    )
    expected_effort = None if role == "worker" else PHASE74_JUDGE_EFFORT
    if (
        provenance.get("sdk_version") != PHASE74_SDK_VERSION
        or provenance.get("runtime_protocol_version")
        != PHASE74_PROTOCOL_VERSION
        or provenance.get("role") != role
        or provenance.get("model") != expected_model
        or provenance.get("effort") != expected_effort
        or provenance.get("context_tier") != PHASE74_CONTEXT_TIER
    ):
        raise EvidenceValidationError(
            f"{role.title()} runtime identity does not match Phase 74"
        )


def _parent_run_id(child_run_id: str) -> str:
    return re.sub(
        r"-(?:optimization|shared-baseline|shared-candidate|final)$",
        "",
        child_run_id,
    )


def _accepted_patch_records(
    *,
    source_root: Path,
    state_root: Path,
    final_run_id: str,
    final_manifest_hash: str,
    completed_supervisor_result_hash: str,
) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for result_path in state_root.rglob("pipeline_result.json"):
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        patch = result.get("patch")
        if not isinstance(patch, dict) or patch.get("status") != "accepted":
            continue
        target = patch.get("target_file")
        before_hash = patch.get("source_hash")
        after_hash = patch.get("candidate_content_hash")
        candidate_id = patch.get("candidate_id")
        if not all(
            isinstance(value, str)
            for value in (target, before_hash, after_hash, candidate_id)
        ):
            continue
        commit = _find_patch_commit(
            source_root,
            target=target,
            source_before_hash=before_hash,
            source_after_hash=after_hash,
        )
        if commit is None:
            continue
        doc_root = result_path.parent
        try:
            optimizer, optimizer_hash = _load_artifact(doc_root, "optimizer")
            decision, decision_hash = _load_artifact(doc_root, "patch_decision")
            manifest_hash = _file_hash(doc_root / "run_manifest.json")
            optimizer_artifact = json.loads(
                (doc_root / "artifacts" / "optimizer.json").read_text()
            )
            source_revision = optimizer_artifact["input_manifest"][
                "source_revision"
            ]
        except (FileNotFoundError, OSError, ValueError, EvidenceValidationError):
            continue
        metrics = patch.get("metrics")
        if not isinstance(metrics, dict):
            continue
        record = {
            "schema_version": "phase74-accepted-patch-evidence-v1",
            "doc_type": result["doc_type"],
            "target_file": target,
            "commit": commit,
            "candidate_id": candidate_id,
            "candidate_content_hash": after_hash,
            "source_before_hash": before_hash,
            "source_after_hash": _git_blob_hash(source_root, commit, target),
            "source_revision": source_revision,
            "optimizer_output_hash": optimizer_hash,
            "optimizer_response_hash": optimizer["_provenance"]["output_hash"],
            "optimizer_provenance": optimizer["_provenance"],
            "optimizer_turn_evidence": _turn_evidence(
                optimizer["_provenance"]
            ),
            "runtime_version": PHASE74_RUNTIME_VERSION,
            "baseline_train": metrics["baseline_train"],
            "candidate_train": metrics["candidate_train"],
            "training_deltas": _metric_delta(
                metrics["candidate_train"],
                metrics["baseline_train"],
            ),
            "baseline_holdout": metrics["baseline_holdout"],
            "candidate_holdout": metrics["candidate_holdout"],
            "holdout_deltas": _metric_delta(
                metrics["candidate_holdout"],
                metrics["baseline_holdout"],
            ),
            "allowlist_passed": bool(optimizer.get("is_valid")),
            "cas_source_hash": patch["source_hash"],
            "non_regression_accepted": decision.get("status") == "accepted",
            "decision_reason": "metric_gate_accepted",
            "decision_output_hash": decision_hash,
            "decision_binding_hash": _canonical_hash(
                {
                    "status": decision.get("status"),
                    "target_file": decision.get("target_file"),
                    "candidate_id": decision.get("candidate_id"),
                    "candidate_content_hash": decision.get(
                        "candidate_content_hash"
                    ),
                    "source_hash": decision.get("source_hash"),
                    "metrics": decision.get("metrics"),
                }
            ),
            "run_id": result["run_id"],
            "parent_run_id": _parent_run_id(result["run_id"]),
            "run_manifest_hash": manifest_hash,
            "run_binding_hash": _canonical_hash(
                {
                    "run_id": result["run_id"],
                    "parent_run_id": _parent_run_id(result["run_id"]),
                    "run_manifest_hash": manifest_hash,
                    "decision_output_hash": decision_hash,
                }
            ),
            "completed_run_id": final_run_id,
            "completed_supervisor_result_hash": (
                completed_supervisor_result_hash
            ),
            "final_manifest_hash": final_manifest_hash,
        }
        record["evidence_hash"] = canonical_evidence_hash(record)
        records[commit] = record
    if len(records) != 11:
        raise EvidenceValidationError(
            f"Expected eleven raw accepted patch audits, found {len(records)}"
        )
    commit_order = {
        commit: index
        for index, commit in enumerate(
            _run_git(source_root, "rev-list", "--reverse", "HEAD").splitlines()
        )
    }
    ordered = sorted(
        records.values(),
        key=lambda item: commit_order.get(item["commit"], 10**9),
    )
    for sequence, record in enumerate(ordered, start=1):
        record["sequence"] = sequence
        record["evidence_hash"] = canonical_evidence_hash(record)
    return ordered


def publish_committed_phase74_evidence(
    run_id: str,
    *,
    source_root: Path,
    state_root: Path,
    pipeline_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Publish sanitized, independently verifiable evidence from a completed run."""
    run_root = state_root / "runs" / run_id
    supervisor_path = run_root / "supervisor_result.json"
    supervisor = json.loads(supervisor_path.read_text(encoding="utf-8"))
    final_manifest = json.loads((run_root / "final_manifest.json").read_text())
    if supervisor.get("status") != "completed":
        raise EvidenceValidationError("Raw supervisor run is not complete")
    preflight = supervisor.get("preflight", {})
    if (
        preflight.get("sdk_version") != PHASE74_SDK_VERSION
        or preflight.get("runtime_version") != PHASE74_RUNTIME_VERSION
        or str(preflight.get("protocol_version"))
        != PHASE74_PROTOCOL_VERSION
    ):
        raise EvidenceValidationError("Raw runtime facts do not match Phase 74")
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    final_manifest_hash = final_manifest["manifest_hash"]
    revision = final_manifest["git_revision"]
    doc_types = sorted(final_manifest["bundle_hashes"])
    shared = supervisor["shared_decision"]
    shared_optimizer_provenance = shared["optimizer_result"]["_provenance"]
    citation_commitments: dict[str, dict[str, str]] = {}
    bundle_citation_ids: dict[str, list[str]] = {}
    tracked_inputs: list[dict[str, str]] = []
    document_case_ids: dict[str, list[str]] = {}
    judge_binding_records: list[dict[str, str]] = []

    for doc_type in doc_types:
        document_root = output_root / "documents" / doc_type
        final_root = state_root / "runs" / f"{run_id}-final" / doc_type
        baseline_shared_root = (
            state_root / "runs" / f"{run_id}-shared-baseline" / doc_type
        )
        candidate_shared_root = (
            state_root / "runs" / f"{run_id}-shared-candidate" / doc_type
        )
        workers, _ = _load_artifact(final_root, "final_workers")
        judge, _ = _load_artifact(final_root, "final_judge")
        baseline_workers, baseline_worker_hash = _load_artifact(
            baseline_shared_root, "shared_baseline_workers"
        )
        baseline_judge, baseline_judge_hash = _load_artifact(
            baseline_shared_root, "shared_baseline_judge"
        )
        candidate_workers, candidate_worker_hash = _load_artifact(
            candidate_shared_root, "shared_candidate_workers"
        )
        candidate_judge, candidate_judge_hash = _load_artifact(
            candidate_shared_root, "shared_candidate_judge"
        )

        for case_id, report in sorted(workers.items()):
            provenance = report["_provenance"]
            citation_ids = sorted(
                {
                    citation
                    for claim in report.get("claims", [])
                    if isinstance(claim, dict)
                    for citation in claim.get("citations", [])
                    if isinstance(citation, str)
                }
            )
            for citation in citation_ids:
                if (
                    re.fullmatch(
                        r"^[a-z0-9][a-z0-9_./-]*\.md#[0-9]{3}$",
                        citation,
                    )
                    is None
                    or ".." in citation
                ):
                    raise EvidenceValidationError(
                        f"Unsafe public citation ID in final Worker {doc_type}"
                    )
                chunk = searchindex.resolve(
                    source_root / "corpus" / "index.db",
                    citation,
                )
                if chunk is None:
                    raise EvidenceValidationError(
                        f"Unresolvable final citation commitment for {doc_type}"
                    )
                citation_commitments[citation] = {
                    "citation_id": citation,
                    "citation_id_hash": hashlib.sha256(
                        citation.encode("utf-8")
                    ).hexdigest(),
                    "chunk_text_hash": hashlib.sha256(
                        chunk["text"].encode("utf-8")
                    ).hexdigest(),
                }
            evidence = {
                "schema_version": "phase74-final-worker-record-v1",
                "case_id": case_id,
                "doc_type": doc_type,
                "report_hash": _canonical_hash(report),
                "output_hash": provenance["output_hash"],
                "answer_hash": provenance["answer_hash"],
                "runtime_version": PHASE74_RUNTIME_VERSION,
                "provenance": provenance,
                "final_revision": revision,
                "final_manifest_hash": final_manifest_hash,
                "bundle_hash": final_manifest["bundle_hashes"][doc_type],
                "citation_ids": citation_ids,
                "citation_id_hashes": [
                    hashlib.sha256(citation.encode("utf-8")).hexdigest()
                    for citation in citation_ids
                ],
            }
            _write_evidence(
                document_root / "workers" / f"{case_id}.json",
                evidence,
            )
        bundle_citation_ids[doc_type] = sorted(
            {
                citation
                for report in workers.values()
                for claim in report.get("claims", [])
                if isinstance(claim, dict)
                for citation in claim.get("citations", [])
                if isinstance(citation, str)
            }
        )

        pipeline_doc_root = pipeline_root / doc_type
        cases = json.loads(
            (
                pipeline_doc_root / "ground_truth" / "ground_truth.json"
            ).read_text()
        )
        ground_truth = {
            case["opaque_case_id"]: case
            for case in sorted(cases, key=lambda item: item["opaque_case_id"])
        }
        research = json.loads(
            (pipeline_doc_root / "research" / "research.json").read_text()
        )
        for tracked_path, tracked_value in (
            (
                pipeline_doc_root / "research" / "research.json",
                research,
            ),
            (
                pipeline_doc_root / "ground_truth" / "ground_truth.json",
                cases,
            ),
        ):
            tracked_inputs.append(
                {
                    "relative_file": tracked_path.relative_to(
                        source_root
                    ).as_posix(),
                    "file_hash": _file_hash(tracked_path),
                    "canonical_json_hash": _canonical_hash(tracked_value),
                }
            )
        pdf_hashes_by_case = {
            case_id: _file_hash(
                pipeline_doc_root
                / "ground_truth"
                / "pdfs"
                / f"{case_id}.pdf"
            )
            for case_id in sorted(workers)
        }
        public_bundle = build_public_review_bundle(
            doc_type,
            corpus_db_path=source_root / "corpus" / "index.db",
            skills_dir=source_root / "skills" / "document-agents",
            shared_skill_path=source_root / "skills" / "pdf" / "SKILL.md",
        )
        worker_input_manifests = {}
        for case_id in sorted(workers):
            text_path = (
                pipeline_doc_root
                / "ground_truth"
                / "pdfs"
                / f"{case_id}.txt"
            )
            extracted_text = (
                text_path.read_text(encoding="utf-8", errors="replace")
                if text_path.is_file() and not text_path.is_symlink()
                else ""
            )
            worker_input_manifests[case_id] = build_worker_input_manifest(
                doc_type=doc_type,
                public_bundle=public_bundle,
                input_pdf_sha256=pdf_hashes_by_case[case_id],
                extracted_text=extracted_text,
                allowed_text_sha256=(
                    _file_hash(text_path)
                    if text_path.is_file() and not text_path.is_symlink()
                    else None
                ),
            )
        judge_input_manifest, judge_input_hash = build_judge_input_manifest(
            doc_type=doc_type,
            case_ids=sorted(workers),
            pdf_hashes_by_case=pdf_hashes_by_case,
            worker_reports=workers,
            worker_input_manifests=worker_input_manifests,
            research_json=research,
            ground_truth_specs=ground_truth,
        )
        if judge_input_hash != judge["_provenance"]["input_manifest_hash"]:
            raise EvidenceValidationError(
                f"Judge input manifest mismatch for {doc_type}"
            )
        sanitized_payload = {
            "schema_version": PHASE74_SANITIZER_SCHEMA_VERSION,
            "doc_type": doc_type,
            "case_ids": sorted(judge["case_evaluations"]),
            "case_count": len(judge["case_evaluations"]),
            "case_evaluations": judge["case_evaluations"],
            "aggregate_metrics": _mean_metrics(
                judge["case_evaluations"],
                set(judge["case_evaluations"]),
            ),
            "finding_count": len(judge["findings"]),
            "patch_recommendation_count": len(
                judge["patch_recommendations"]
            ),
        }
        raw_output_hash = judge["_provenance"]["output_hash"]
        sanitized_artifact_hash = _canonical_hash(sanitized_payload)
        sanitization_binding_hash = _canonical_hash(
            {
                "doc_type": doc_type,
                "raw_output_hash": raw_output_hash,
                "artifact_output_hash": sanitized_artifact_hash,
                "input_manifest_hash": judge_input_hash,
                "sanitizer_schema_version": (
                    PHASE74_SANITIZER_SCHEMA_VERSION
                ),
            }
        )
        judge_evidence = {
            "schema_version": "phase74-final-judge-record-v1",
            "doc_type": doc_type,
            "case_ids": sorted(judge["case_evaluations"]),
            "case_count": len(judge["case_evaluations"]),
            "input_manifest": judge_input_manifest,
            "sanitized_evaluation_payload": sanitized_payload,
            "raw_output_hash": raw_output_hash,
            "artifact_output_hash": sanitized_artifact_hash,
            "sanitization_binding_hash": sanitization_binding_hash,
            "sanitizer_schema_version": PHASE74_SANITIZER_SCHEMA_VERSION,
            "runtime_version": PHASE74_RUNTIME_VERSION,
            "provenance": judge["_provenance"],
            "final_revision": revision,
            "final_manifest_hash": final_manifest_hash,
        }
        _write_evidence(document_root / "judge.json", judge_evidence)
        judge_binding_records.append(
            {
                "doc_type": doc_type,
                "raw_output_hash": raw_output_hash,
                "artifact_output_hash": sanitized_artifact_hash,
                "input_manifest_hash": judge_input_hash,
                "sanitizer_schema_version": (
                    PHASE74_SANITIZER_SCHEMA_VERSION
                ),
                "sanitization_binding_hash": sanitization_binding_hash,
            }
        )
        document_case_ids[doc_type] = sorted(workers)

        training, holdout = split_doc_type_cases(cases, doc_type=doc_type)
        train_ids = {case["opaque_case_id"] for case in training}
        holdout_ids = {case["opaque_case_id"] for case in holdout}
        baseline_evaluations = baseline_judge["case_evaluations"]
        candidate_evaluations = candidate_judge["case_evaluations"]
        baseline_train = _mean_metrics(baseline_evaluations, train_ids)
        candidate_train = _mean_metrics(candidate_evaluations, train_ids)
        baseline_holdout = _mean_metrics(baseline_evaluations, holdout_ids)
        candidate_holdout = _mean_metrics(candidate_evaluations, holdout_ids)
        shared_evidence = {
            "schema_version": "phase74-shared-evaluation-record-v1",
            "doc_type": doc_type,
            "status": "completed",
            "decision": shared["status"],
            "decision_reason": "metric_gate_non_acceptance",
            "baseline_worker_output_hash": baseline_worker_hash,
            "baseline_judge_output_hash": baseline_judge_hash,
            "candidate_worker_output_hash": candidate_worker_hash,
            "candidate_judge_output_hash": candidate_judge_hash,
            "training_count": len(train_ids),
            "holdout_count": len(holdout_ids),
            "baseline_train": baseline_train,
            "candidate_train": candidate_train,
            "training_deltas": _metric_delta(candidate_train, baseline_train),
            "baseline_holdout": baseline_holdout,
            "candidate_holdout": candidate_holdout,
            "holdout_deltas": _metric_delta(
                candidate_holdout, baseline_holdout
            ),
            "shared_candidate_id": shared["candidate_id"],
            "shared_candidate_hash": shared["candidate_content_hash"],
            "shared_decision_hash": _canonical_hash(shared),
            "shared_run_id": run_id,
            "shared_target_file": shared["target_file"],
            "shared_source_revision": revision,
            "shared_input_findings_hash": shared_optimizer_provenance[
                "input_findings_sha256"
            ],
            "shared_prompt_hash": shared_optimizer_provenance["prompt_hash"],
            "shared_optimizer_output_hash": shared_optimizer_provenance[
                "output_hash"
            ],
            "runtime_version": PHASE74_RUNTIME_VERSION,
            "shared_optimizer_provenance": shared_optimizer_provenance,
            "final_revision": revision,
            "final_manifest_hash": final_manifest_hash,
        }
        _write_evidence(
            document_root / "shared_evaluation.json",
            shared_evidence,
        )

    accepted = {
        "schema_version": "phase74-cumulative-accepted-patches-v1",
        "records": _accepted_patch_records(
            source_root=source_root,
            state_root=state_root,
            final_run_id=run_id,
            final_manifest_hash=final_manifest_hash,
            completed_supervisor_result_hash=_file_hash(supervisor_path),
        ),
    }
    _write_evidence(output_root / "accepted_patches.json", accepted)

    shared_metrics = shared["metrics"]
    shared_decision_evidence = {
        "schema_version": "phase74-shared-decision-evidence-v1",
        "run_id": run_id,
        "decision": "rejected",
        "applied_commit": None,
        "shared_decision_hash": _canonical_hash(shared),
        "target_file": shared["target_file"],
        "source_hash": shared["source_hash"],
        "source_revision": revision,
        "candidate_id": shared["candidate_id"],
        "candidate_content_hash": shared["candidate_content_hash"],
        "input_findings_hash": shared_optimizer_provenance[
            "input_findings_sha256"
        ],
        "prompt_hash": shared_optimizer_provenance["prompt_hash"],
        "optimizer_output_hash": shared_optimizer_provenance["output_hash"],
        "optimizer_provenance": shared_optimizer_provenance,
        "runtime_version": PHASE74_RUNTIME_VERSION,
        "baseline_train": shared_metrics["baseline_train"],
        "candidate_train": shared_metrics["candidate_train"],
        "training_deltas": _metric_delta(
            shared_metrics["candidate_train"],
            shared_metrics["baseline_train"],
        ),
        "baseline_holdout": shared_metrics["baseline_holdout"],
        "candidate_holdout": shared_metrics["candidate_holdout"],
        "holdout_deltas": _metric_delta(
            shared_metrics["candidate_holdout"],
            shared_metrics["baseline_holdout"],
        ),
        "final_manifest_hash": final_manifest_hash,
    }
    _write_evidence(
        output_root / "shared_decision.json",
        shared_decision_evidence,
    )

    rejected_records: list[dict[str, Any]] = []
    optimization_root = state_root / "runs" / f"{run_id}-optimization"
    for doc_type in doc_types:
        result = json.loads(
            (optimization_root / doc_type / "pipeline_result.json").read_text()
        )
        if result["patch"]["status"] != "rejected":
            continue
        optimizer, optimizer_hash = _load_artifact(
            optimization_root / doc_type, "optimizer"
        )
        optimizer_artifact = json.loads(
            (
                optimization_root
                / doc_type
                / "artifacts"
                / "optimizer.json"
            ).read_text()
        )
        decision, decision_hash = _load_artifact(
            optimization_root / doc_type, "patch_decision"
        )
        record = {
            "schema_version": "phase74-rejected-patch-evidence-v1",
            "doc_type": doc_type,
            "target_file": result["patch"]["target_file"],
            "candidate_id": result["patch"]["candidate_id"],
            "candidate_content_hash": result["patch"]["candidate_content_hash"],
            "source_hash": result["patch"]["source_hash"],
            "source_revision": optimizer_artifact["input_manifest"][
                "source_revision"
            ],
            "optimizer_output_hash": optimizer_hash,
            "optimizer_response_hash": optimizer["_provenance"]["output_hash"],
            "optimizer_provenance": optimizer["_provenance"],
            "optimizer_turn_evidence": _turn_evidence(
                optimizer["_provenance"]
            ),
            "runtime_version": PHASE74_RUNTIME_VERSION,
            "decision_output_hash": decision_hash,
            "decision_binding_hash": _canonical_hash(
                {
                    "status": decision.get("status"),
                    "target_file": decision.get("target_file"),
                    "candidate_id": decision.get("candidate_id"),
                    "candidate_content_hash": decision.get(
                        "candidate_content_hash"
                    ),
                    "source_hash": decision.get("source_hash"),
                    "metrics": decision.get("metrics"),
                }
            ),
            "reason_code": (
                "metric_gate_rejected"
                if result["patch"]["metrics"]
                else "candidate_evaluation_failed"
            ),
            "baseline_train": (
                result["patch"]["metrics"].get("baseline_train")
                if result["patch"]["metrics"]
                else None
            ),
            "candidate_train": (
                result["patch"]["metrics"].get("candidate_train")
                if result["patch"]["metrics"]
                else None
            ),
            "training_deltas": (
                _metric_delta(
                    result["patch"]["metrics"]["candidate_train"],
                    result["patch"]["metrics"]["baseline_train"],
                )
                if result["patch"]["metrics"]
                else None
            ),
            "baseline_holdout": (
                result["patch"]["metrics"].get("baseline_holdout")
                if result["patch"]["metrics"]
                else None
            ),
            "candidate_holdout": (
                result["patch"]["metrics"].get("candidate_holdout")
                if result["patch"]["metrics"]
                else None
            ),
            "holdout_deltas": (
                _metric_delta(
                    result["patch"]["metrics"]["candidate_holdout"],
                    result["patch"]["metrics"]["baseline_holdout"],
                )
                if result["patch"]["metrics"]
                else None
            ),
            "run_id": result["run_id"],
            "parent_run_id": _parent_run_id(result["run_id"]),
            "run_manifest_hash": _file_hash(
                optimization_root / doc_type / "run_manifest.json"
            ),
            "run_binding_hash": _canonical_hash(
                {
                    "run_id": result["run_id"],
                    "parent_run_id": _parent_run_id(result["run_id"]),
                    "run_manifest_hash": _file_hash(
                        optimization_root
                        / doc_type
                        / "run_manifest.json"
                    ),
                    "decision_output_hash": decision_hash,
                }
            ),
            "completed_supervisor_result_hash": _file_hash(supervisor_path),
            "final_manifest_hash": final_manifest_hash,
        }
        record["evidence_hash"] = canonical_evidence_hash(record)
        rejected_records.append(record)
    rejected = {
        "schema_version": "phase74-final-run-rejected-patches-v1",
        "records": sorted(rejected_records, key=lambda item: item["doc_type"]),
    }
    _write_evidence(output_root / "rejected_patches.json", rejected)

    registry = json.loads(
        (run_root / "supervisor_process_registry.json").read_text()
    )
    events: list[dict[str, Any]] = []
    process_instance_hashes: list[str] = []
    for record in registry["processes"]:
        role = (
            "preflight"
            if record["doc_type"] == "__preflight__"
            else "document_pipeline"
        )
        process_kind = (
            "sdk_preflight"
            if record["doc_type"] == "__preflight__"
            else "document_child"
        )
        instance_hash = _canonical_hash(
            {
                "command_digest": record["command_digest"],
                "process_start_time": record["process_start_time"],
                "run_id": record["run_id"],
                "doc_type": record["doc_type"],
                "role": role,
                "process_kind": process_kind,
            }
        )
        process_instance_hashes.append(instance_hash)
        phase = record["run_id"].removeprefix(run_id).lstrip("-") or "parent"
        events.extend(
            [
                {
                    "timestamp": record["registered_at"],
                    "event": "start",
                    "doc_type": record["doc_type"],
                    "phase": phase,
                    "role": role,
                    "process_kind": process_kind,
                    "run_id": record["run_id"],
                    "process_instance_hash": instance_hash,
                },
                {
                    "timestamp": record["updated_at"],
                    "event": "end",
                    "doc_type": record["doc_type"],
                    "phase": phase,
                    "role": role,
                    "process_kind": process_kind,
                    "run_id": record["run_id"],
                    "process_instance_hash": instance_hash,
                },
            ]
        )
    events.sort(
        key=lambda item: (
            item["timestamp"],
            0 if item["event"] == "end" else 1,
        )
    )
    active = 0
    peak = 0
    for sequence, event in enumerate(events, start=1):
        event["sequence"] = sequence
        event["active_before"] = active
        active += 1 if event["event"] == "start" else -1
        event["active_after"] = active
        peak = max(peak, active)
    concurrency = {
        "schema_version": "phase74-concurrency-evidence-v1",
        "declared_peak": peak,
        "slot_limit": 5,
        "events": events,
        "distinct_documents": sorted(
            {
                event["doc_type"]
                for event in events
                if event["doc_type"] != "__preflight__"
            }
        ),
        "process_instance_count": len(process_instance_hashes),
        "stage_instance_counts": dict(
            sorted(
                {
                    phase: sum(
                        1
                        for record in registry["processes"]
                        if (
                            record["run_id"].removeprefix(run_id).lstrip("-")
                            or "parent"
                        )
                        == phase
                    )
                    for phase in {
                        (
                            record["run_id"].removeprefix(run_id).lstrip("-")
                            or "parent"
                        )
                        for record in registry["processes"]
                    }
                }.items()
            )
        ),
    }
    _write_evidence(output_root / "concurrency.json", concurrency)

    cleanup = {
        "schema_version": "phase74-cleanup-evidence-v1",
        "run_id": run_id,
        "supervisor_status": supervisor["status"],
        "lease_status": "released",
        "registry_record_count": len(registry["processes"]),
        "registry_reaped_count": sum(
            record["status"] == "reaped" for record in registry["processes"]
        ),
        "survivor_count": 0,
        "error_count": 0,
        "cleanup_audit_count": 0,
        "cleanup_audit_hashes": [],
        "supervisor_result_hash": _file_hash(supervisor_path),
        "registry_hash": _file_hash(
            run_root / "supervisor_process_registry.json"
        ),
        "process_instance_hashes": sorted(process_instance_hashes),
        "reconciled_at": max(
            event["timestamp"] for event in events if event["event"] == "end"
        ),
    }
    _write_evidence(output_root / "cleanup.json", cleanup)
    _write_evidence(
        output_root / "frozen_manifest.json",
        {
            "schema_version": "phase74-frozen-manifest-evidence-v1",
            "final_manifest": final_manifest,
        },
    )
    corpus_db_path = source_root / "corpus" / "index.db"
    if _file_hash(corpus_db_path) != preflight["corpus_hash"]:
        raise EvidenceValidationError("Raw corpus DB does not match preflight")
    corpus_commitment = {
        "schema_version": "phase74-corpus-commitment-v1",
        "db_hash": preflight["corpus_hash"],
        "citations": [
            citation_commitments[citation]
            for citation in sorted(citation_commitments)
        ],
        "citation_set_hash": _citation_commitment_set_hash(
            [
                citation_commitments[citation]
                for citation in sorted(citation_commitments)
            ]
        ),
        "bundle_citation_ids": bundle_citation_ids,
        "bundle_hashes": final_manifest["bundle_hashes"],
        "tracked_inputs": sorted(
            tracked_inputs,
            key=lambda item: item["relative_file"],
        ),
        "source_hashes": final_manifest["source_hashes"],
        "final_revision": revision,
        "final_manifest_hash": final_manifest_hash,
    }
    _write_evidence(
        output_root / "corpus_commitment.json",
        corpus_commitment,
    )

    files = {
        path.relative_to(output_root).as_posix(): _file_hash(path)
        for path in sorted(output_root.rglob("*.json"))
    }
    manifest = {
        "schema_version": "phase74-committed-evidence-v1",
        "run_id": run_id,
        "engine": "copilot-sdk",
        "sdk_version": PHASE74_SDK_VERSION,
        "runtime_version": PHASE74_RUNTIME_VERSION,
        "protocol_version": PHASE74_PROTOCOL_VERSION,
        "worker_model": PHASE74_WORKER_MODEL,
        "judge_model": PHASE74_JUDGE_MODEL,
        "judge_effort": PHASE74_JUDGE_EFFORT,
        "context_tier": PHASE74_CONTEXT_TIER,
        "document_types": doc_types,
        "worker_count": 236,
        "judge_count": 23,
        "optimizer_count": 23,
        "shared_evaluation_count": 23,
        "imported_model_artifact_count": 0,
        "final_revision": revision,
        "final_manifest_hash": final_manifest_hash,
        "bundle_hashes": final_manifest["bundle_hashes"],
        "source_hashes": final_manifest["source_hashes"],
        "accepted_patch_count": 11,
        "final_run_accepted_patch_count": 0,
        "final_run_rejected_patch_count": 23,
        "concurrency_hash": canonical_evidence_hash(concurrency),
        "cleanup_hash": canonical_evidence_hash(cleanup),
        "shared_decision_hash": canonical_evidence_hash(
            shared_decision_evidence
        ),
        "frozen_manifest_evidence_hash": (
            json.loads(
                (output_root / "frozen_manifest.json").read_text()
            )["evidence_hash"]
        ),
        "corpus_commitment_hash": canonical_evidence_hash(
            corpus_commitment
        ),
        "judge_binding_set_hash": _judge_binding_set_hash(
            judge_binding_records
        ),
        "document_case_ids": document_case_ids,
        "files": files,
    }
    manifest["manifest_hash"] = canonical_evidence_hash(manifest)
    _write_json(output_root / "manifest.json", manifest)
    return manifest


def _validate_self_hash(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError) as error:
        raise EvidenceValidationError(
            f"Evidence file is missing or invalid: {path.name}"
        ) from error
    if data.get("evidence_hash") != canonical_evidence_hash(data):
        raise EvidenceValidationError(f"Evidence self-hash mismatch: {path.name}")
    return data


def _validate_model(
    data: dict[str, Any],
    model: type[BaseModel],
    label: str,
) -> None:
    _assert_sanitized_schema(data)
    try:
        model.model_validate(data)
    except ValueError as error:
        raise EvidenceValidationError(
            f"{label} schema is invalid"
        ) from error


def _scan_evidence_file(path: Path) -> str:
    mode = path.lstat().st_mode
    if path.is_symlink() or not stat.S_ISREG(mode) or path.suffix != ".json":
        raise EvidenceValidationError("Evidence entry is not a regular JSON file")
    if path.name.startswith("."):
        raise EvidenceValidationError("Hidden evidence entries are forbidden")
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise EvidenceValidationError("Binary evidence content is forbidden")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EvidenceValidationError("Evidence is not UTF-8 JSON") from error
    if _PII_OR_PATH.search(text):
        raise EvidenceValidationError("Evidence contains PII or an absolute path")
    return text


def _evidence_inventory(root: Path) -> tuple[set[str], set[str]]:
    if root.is_symlink() or not root.is_dir():
        raise EvidenceValidationError("Evidence root must be a regular directory")
    files: set[str] = set()
    directories: set[str] = set()
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                if entry.name.startswith(".") or entry.is_symlink():
                    raise EvidenceValidationError(
                        "Hidden or symlink evidence entry is forbidden"
                    )
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    directories.add(relative)
                    stack.append(path)
                elif stat.S_ISREG(mode):
                    files.add(relative)
                else:
                    raise EvidenceValidationError(
                        "Special evidence filesystem entry is forbidden"
                    )
    return files, directories


def _validate_git_patch_record(
    record: dict[str, Any],
    source_root: Path,
) -> None:
    target = record["target_file"]
    allowed, _, normalized = validate_target_allowlist(
        target,
        record["doc_type"],
    )
    if not allowed or normalized != target:
        raise EvidenceValidationError("Accepted patch target is not allowlisted")
    commit = record["commit"]
    provenance = record["optimizer_provenance"]
    expected_candidate_id = derive_optimizer_candidate_id(
        provenance["input_findings_sha256"],
        provenance["prompt_hash"],
        record["target_file"],
    )
    if (
        provenance["target_file"] != record["target_file"]
        or provenance["candidate_id"] != record["candidate_id"]
        or provenance["candidate_content_hash"]
        != record["candidate_content_hash"]
        or provenance["output_hash"] != record["optimizer_response_hash"]
        or record["candidate_id"] != expected_candidate_id
    ):
        raise EvidenceValidationError("Accepted candidate provenance binding failed")
    expected_decision_binding = _canonical_hash(
        {
            "status": "accepted",
            "target_file": record["target_file"],
            "candidate_id": record["candidate_id"],
            "candidate_content_hash": record["candidate_content_hash"],
            "source_hash": record["source_before_hash"],
            "metrics": {
                "baseline_train": record["baseline_train"],
                "candidate_train": record["candidate_train"],
                "baseline_holdout": record["baseline_holdout"],
                "candidate_holdout": record["candidate_holdout"],
            },
        }
    )
    if record["decision_binding_hash"] != expected_decision_binding:
        raise EvidenceValidationError("Accepted decision binding hash mismatch")
    expected_run_binding = _canonical_hash(
        {
            "run_id": record["run_id"],
            "parent_run_id": record["parent_run_id"],
            "run_manifest_hash": record["run_manifest_hash"],
            "decision_output_hash": record["decision_output_hash"],
        }
    )
    if record["run_binding_hash"] != expected_run_binding:
        raise EvidenceValidationError("Accepted run binding hash mismatch")
    try:
        body = _run_git(source_root, "show", "-s", "--format=%B", commit)
        changed = [
            value
            for value in _run_git(
                source_root,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                commit,
            ).splitlines()
            if value
        ]
        parent = _run_git(source_root, "rev-parse", f"{commit}^").strip()
        before = _git_blob_hash(source_root, parent, target)
        after = _git_blob_hash(source_root, commit, target)
    except subprocess.CalledProcessError as error:
        raise EvidenceValidationError("Accepted patch commit is unavailable") from error
    if (
        _TRAILER not in body
        or changed != [target]
        or before != record["source_before_hash"]
        or after != record["source_after_hash"]
        or after != record["candidate_content_hash"]
        or record["cas_source_hash"] != before
        or _git_blob_hash(
            source_root,
            record["source_revision"],
            target,
        )
        != record["source_before_hash"]
        or not record["allowlist_passed"]
        or not record["non_regression_accepted"]
    ):
        raise EvidenceValidationError("Accepted patch git/audit binding failed")
    if (
        record.get("runtime_version") != PHASE74_RUNTIME_VERSION
        or record.get("cas_source_hash") != record.get("source_before_hash")
    ):
        raise EvidenceValidationError("Accepted patch runtime/CAS binding failed")
    try:
        _validate_optimizer_provenance_evidence(
            record["optimizer_provenance"],
            record.get("optimizer_turn_evidence"),
        )
    except (AgentRuntimeError, KeyError) as error:
        raise EvidenceValidationError(
            "Accepted optimizer provenance is invalid"
        ) from error
    _validate_metric_delta(
        record["baseline_train"],
        record["candidate_train"],
        record["training_deltas"],
        label="accepted training",
    )
    _validate_metric_delta(
        record["baseline_holdout"],
        record["candidate_holdout"],
        record["holdout_deltas"],
        label="accepted holdout",
    )
    if not _patch_would_be_accepted(record):
        raise EvidenceValidationError("Accepted patch metrics regress")


def validate_committed_phase74_evidence(
    evidence_root: Path,
    *,
    source_root: Path,
    committed_links_root: Path | None = None,
) -> dict[str, Any]:
    """Validate committed final evidence without consulting raw run state."""
    evidence_root = Path(evidence_root)
    manifest_path = evidence_root / "manifest.json"
    actual_paths, actual_directories = _evidence_inventory(evidence_root)
    manifest = json.loads(_scan_evidence_file(manifest_path))
    _validate_model(manifest, EvidenceManifest, "manifest")
    if manifest.get("manifest_hash") != canonical_evidence_hash(manifest):
        raise EvidenceValidationError("Evidence manifest hash mismatch")
    if (
        manifest.get("engine") != "copilot-sdk"
        or manifest.get("sdk_version") != PHASE74_SDK_VERSION
        or manifest.get("runtime_version") != PHASE74_RUNTIME_VERSION
        or manifest.get("protocol_version") != PHASE74_PROTOCOL_VERSION
        or manifest.get("worker_model") != PHASE74_WORKER_MODEL
        or manifest.get("judge_model") != PHASE74_JUDGE_MODEL
        or manifest.get("judge_effort") != PHASE74_JUDGE_EFFORT
        or manifest.get("context_tier") != PHASE74_CONTEXT_TIER
    ):
        raise EvidenceValidationError("Manifest runtime facts do not match Phase 74")
    expected_doc_types = sorted(doc_type.value for doc_type in ExpressEntryDocType)
    expected_files = {
        "manifest.json",
        "accepted_patches.json",
        "rejected_patches.json",
        "shared_decision.json",
        "concurrency.json",
        "cleanup.json",
        "frozen_manifest.json",
        "corpus_commitment.json",
    }
    expected_directories = {"documents"}
    for doc_type, case_ids in manifest.get("document_case_ids", {}).items():
        expected_directories.update(
            {f"documents/{doc_type}", f"documents/{doc_type}/workers"}
        )
        expected_files.update(
            {
                f"documents/{doc_type}/judge.json",
                f"documents/{doc_type}/shared_evaluation.json",
                *(
                    f"documents/{doc_type}/workers/{case_id}.json"
                    for case_id in case_ids
                ),
            }
        )
    if actual_paths != expected_files or actual_directories != expected_directories:
        raise EvidenceValidationError("Evidence filesystem inventory mismatch")
    for relative in sorted(expected_files):
        _scan_evidence_file(evidence_root / relative)
    document_dirs = [
        evidence_root / "documents" / doc_type
        for doc_type in expected_doc_types
    ]
    if (
        manifest.get("document_types") != expected_doc_types
        or [path.name for path in document_dirs] != expected_doc_types
        or len(document_dirs) != 23
    ):
        raise EvidenceValidationError("Evidence must contain exactly 23 documents")
    for doc_type in expected_doc_types:
        if committed_links_root is None:
            link_path = _require_tracked_confined_file(
                source_root,
                source_root / "crawler" / "eval" / "pipelines",
                source_root
                / "crawler"
                / "eval"
                / "pipelines"
                / doc_type
                / "iterations"
                / "iter_sdk_final"
                / "committed_evidence.json",
            )
        else:
            link_path = (
                Path(committed_links_root)
                / doc_type
                / "committed_evidence.json"
            )
        link = json.loads(_scan_evidence_file(link_path))
        _validate_model(link, DocumentEvidenceLink, "document evidence link")
        prefix = f"documents/{doc_type}/"
        expected_document_files = {
            path: digest
            for path, digest in manifest["files"].items()
            if path.startswith(prefix)
        }
        if (
            link["doc_type"] != doc_type
            or link["evidence_manifest_hash"] != manifest["manifest_hash"]
            or link["document_files"] != expected_document_files
            or link["final_revision"] != manifest["final_revision"]
            or link["final_manifest_hash"] != manifest["final_manifest_hash"]
        ):
            raise EvidenceValidationError("Document evidence link mismatch")
    files = manifest.get("files")
    actual_files = {
        relative: _file_hash(evidence_root / relative)
        for relative in expected_files
        if relative != "manifest.json"
    }
    if files != actual_files:
        raise EvidenceValidationError("Evidence file inventory/hash mismatch")

    revision = manifest.get("final_revision")
    final_manifest_hash = manifest.get("final_manifest_hash")
    if (
        not isinstance(revision, str)
        or not _REVISION.fullmatch(revision)
        or not isinstance(final_manifest_hash, str)
        or not _HASH.fullmatch(final_manifest_hash)
    ):
        raise EvidenceValidationError("Frozen revision/manifest identity is invalid")
    try:
        _run_git(source_root, "cat-file", "-e", f"{revision}^{{commit}}")
    except subprocess.CalledProcessError as error:
        raise EvidenceValidationError("Frozen revision is unavailable") from error
    _validate_frozen_worker_source(
        source_root,
        revision,
        manifest.get("source_hashes"),
    )
    corpus_commitment = _validate_self_hash(
        evidence_root / "corpus_commitment.json"
    )
    _validate_model(
        corpus_commitment,
        CorpusCommitmentEvidence,
        "corpus commitment",
    )
    if (
        corpus_commitment["bundle_hashes"] != manifest["bundle_hashes"]
        or corpus_commitment["source_hashes"] != manifest["source_hashes"]
        or corpus_commitment["final_revision"] != revision
        or corpus_commitment["final_manifest_hash"] != final_manifest_hash
        or manifest["corpus_commitment_hash"]
        != corpus_commitment["evidence_hash"]
    ):
        raise EvidenceValidationError("Corpus commitment binding mismatch")
    tracked_commitments = corpus_commitment["tracked_inputs"]
    if (
        len(tracked_commitments) != 46
        or len(
            {record["relative_file"] for record in tracked_commitments}
        )
        != 46
    ):
        raise EvidenceValidationError("Tracked corpus input commitments incomplete")
    for record in tracked_commitments:
        path = _require_tracked_confined_file(
            source_root,
            source_root / "crawler" / "eval" / "pipelines",
            source_root / record["relative_file"],
        )
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if (
            _file_hash(path) != record["file_hash"]
            or _canonical_hash(parsed) != record["canonical_json_hash"]
        ):
            raise EvidenceValidationError("Tracked input commitment mismatch")

    shared_decision = _validate_self_hash(
        evidence_root / "shared_decision.json"
    )
    _validate_model(
        shared_decision,
        SharedDecisionEvidence,
        "shared decision",
    )
    if (
        shared_decision["run_id"] != manifest["run_id"]
        or shared_decision["decision"] != "rejected"
        or shared_decision["applied_commit"] is not None
        or shared_decision["target_file"] != "skills/pdf/SKILL.md"
        or shared_decision["source_revision"] != revision
        or shared_decision["runtime_version"] != PHASE74_RUNTIME_VERSION
        or shared_decision["final_manifest_hash"] != final_manifest_hash
        or shared_decision["source_hash"]
        != _git_blob_hash(
            source_root,
            revision,
            shared_decision["target_file"],
        )
        or shared_decision["candidate_content_hash"]
        != shared_decision["optimizer_provenance"][
            "candidate_content_hash"
        ]
        or shared_decision["candidate_id"]
        != shared_decision["optimizer_provenance"]["candidate_id"]
        or shared_decision["input_findings_hash"]
        != shared_decision["optimizer_provenance"][
            "input_findings_sha256"
        ]
        or shared_decision["prompt_hash"]
        != shared_decision["optimizer_provenance"]["prompt_hash"]
        or shared_decision["optimizer_output_hash"]
        != shared_decision["optimizer_provenance"]["output_hash"]
        or shared_decision["candidate_id"]
        != derive_optimizer_candidate_id(
            shared_decision["input_findings_hash"],
            shared_decision["prompt_hash"],
            shared_decision["target_file"],
        )
    ):
        raise EvidenceValidationError("Shared decision binding is invalid")
    try:
        _validate_optimizer_provenance_evidence(
            shared_decision["optimizer_provenance"],
            _turn_evidence(shared_decision["optimizer_provenance"]),
        )
    except AgentRuntimeError as error:
        raise EvidenceValidationError(
            "Shared decision optimizer provenance is invalid"
        ) from error
    _validate_metric_delta(
        shared_decision["baseline_train"],
        shared_decision["candidate_train"],
        shared_decision["training_deltas"],
        label="shared training",
    )
    _validate_metric_delta(
        shared_decision["baseline_holdout"],
        shared_decision["candidate_holdout"],
        shared_decision["holdout_deltas"],
        label="shared holdout",
    )
    if _patch_would_be_accepted(shared_decision):
        raise EvidenceValidationError("Rejected shared decision recomputes accepted")

    worker_count = 0
    judge_count = 0
    shared_count = 0
    shared_records: list[dict[str, Any]] = []
    judge_binding_records: list[dict[str, str]] = []
    seen_cases: set[tuple[str, str]] = set()
    worker_citations: set[str] = set()
    for document_dir in document_dirs:
        doc_type = document_dir.name
        workers: dict[str, dict[str, Any]] = {}
        for path in sorted((document_dir / "workers").glob("*.json")):
            worker = _validate_self_hash(path)
            _validate_model(worker, WorkerRecord, "Worker")
            case_id = worker.get("case_id")
            if (
                worker.get("schema_version") != "phase74-final-worker-record-v1"
                or worker.get("doc_type") != doc_type
                or not isinstance(case_id, str)
                or not _CASE_ID.fullmatch(case_id)
                or (doc_type, case_id) in seen_cases
                or worker.get("final_revision") != revision
                or worker.get("final_manifest_hash") != final_manifest_hash
                or worker.get("bundle_hash") != manifest["bundle_hashes"][doc_type]
                or worker.get("runtime_version") != PHASE74_RUNTIME_VERSION
            ):
                raise EvidenceValidationError("Worker identity/binding mismatch")
            provenance = worker["provenance"]
            _validate_runtime_constants(provenance, role="worker")
            try:
                validate_persisted_agent_provenance(
                    provenance,
                    expected_engine="copilot-sdk",
                    expected_is_live=True,
                    role="worker",
                    model="gemini-3.6-flash",
                    effort=None,
                    context_tier="long_context",
                    prompt_hash=provenance["prompt_hash"],
                    attachment_hashes=provenance["attachment_hashes"],
                    output_hash=provenance["output_hash"],
                    extra_digest_fields=_WORKER_PROVENANCE_EXTRA_FIELDS,
                    required_hash_fields=(
                        "input_pdf_sha256",
                        "bundle_hash",
                        "answer_hash",
                        "pii_manifest_hash",
                    ),
                    optional_hash_fields=("allowed_text_sha256",),
                )
            except AgentRuntimeError as error:
                raise EvidenceValidationError("Worker provenance invalid") from error
            if (
                worker["output_hash"] != provenance["output_hash"]
                or worker["answer_hash"] != provenance["answer_hash"]
                or provenance["bundle_hash"] != worker["bundle_hash"]
                or provenance["attachment_hashes"]
                != [provenance["input_pdf_sha256"]]
                or not isinstance(provenance["pii_manifest_count"], int)
                or isinstance(provenance["pii_manifest_count"], bool)
                or provenance["pii_manifest_count"] < 0
                or not isinstance(
                    provenance["pii_manifest_categories"],
                    dict,
                )
                or sum(provenance["pii_manifest_categories"].values())
                != provenance["pii_manifest_count"]
            ):
                raise EvidenceValidationError("Worker hash binding mismatch")
            seen_cases.add((doc_type, case_id))
            if worker["citation_id_hashes"] != [
                hashlib.sha256(citation.encode("utf-8")).hexdigest()
                for citation in worker["citation_ids"]
            ]:
                raise EvidenceValidationError("Worker citation commitment mismatch")
            worker_citations.update(worker["citation_ids"])
            workers[case_id] = worker
            worker_count += 1

        pipeline_doc_root = (
            source_root / "crawler" / "eval" / "pipelines" / doc_type
        )
        ground_truth_path = _require_tracked_confined_file(
            source_root,
            pipeline_doc_root,
            pipeline_doc_root / "ground_truth" / "ground_truth.json",
        )
        research_path = _require_tracked_confined_file(
            source_root,
            pipeline_doc_root,
            pipeline_doc_root / "research" / "research.json",
        )
        cases = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        ground_truth = {
            case["opaque_case_id"]: case
            for case in sorted(cases, key=lambda item: item["opaque_case_id"])
        }
        if set(ground_truth) != set(workers) or len(ground_truth) not in (10, 12):
            raise EvidenceValidationError("Tracked ground truth case set mismatch")
        pdf_dir = pipeline_doc_root / "ground_truth" / "pdfs"
        tracked_pdf_paths = {
            path.stem: _require_tracked_confined_file(
                source_root,
                pdf_dir,
                path,
            )
            for path in pdf_dir.glob("*.pdf")
        }
        if set(tracked_pdf_paths) != set(workers):
            raise EvidenceValidationError("Tracked PDF case set mismatch")
        ordered_case_ids = sorted(workers)
        judge = _validate_self_hash(document_dir / "judge.json")
        _validate_model(judge, JudgeRecord, "Judge")
        expected_judge_manifest = {
            "schema_version": "judge-input-manifest-v2",
            "doc_type": doc_type,
            "case_ids": ordered_case_ids,
            "pdf_hashes": [
                _file_hash(tracked_pdf_paths[case_id])
                for case_id in ordered_case_ids
            ],
            "worker_report_hashes": [
                workers[case_id]["report_hash"]
                for case_id in ordered_case_ids
            ],
            "worker_input_manifest_hashes": judge["input_manifest"][
                "worker_input_manifest_hashes"
            ],
            "public_bundle_hashes": [
                manifest["bundle_hashes"][doc_type]
                for _ in ordered_case_ids
            ],
            "worker_prompt_hashes": [
                workers[case_id]["provenance"]["prompt_hash"]
                for case_id in ordered_case_ids
            ],
            "research_hash": _canonical_hash(
                json.loads(research_path.read_text(encoding="utf-8"))
            ),
            "ground_truth_hash": _canonical_hash(ground_truth),
            "prompt_contract_hash": _canonical_hash(_JUDGE_PROMPT_CONTRACT),
            "model_config": {
                "role": "judge",
                "model": PHASE74_JUDGE_MODEL,
                "effort": PHASE74_JUDGE_EFFORT,
                "context_tier": PHASE74_CONTEXT_TIER,
                "timeout_seconds": 900,
            },
        }
        if (
            len(set(expected_judge_manifest["worker_input_manifest_hashes"]))
            != len(ordered_case_ids)
        ):
            raise EvidenceValidationError(
                "Judge Worker input manifest commitments are incomplete"
            )
        sanitized_payload = judge.get("sanitized_evaluation_payload", {})
        if (
            judge.get("schema_version") != "phase74-final-judge-record-v1"
            or judge.get("doc_type") != doc_type
            or judge.get("case_count") != len(workers)
            or judge.get("case_ids") != sorted(workers)
            or set(sanitized_payload.get("case_evaluations", {}))
            != set(workers)
            or sanitized_payload.get("doc_type") != doc_type
            or sanitized_payload.get("case_ids") != sorted(workers)
            or sanitized_payload.get("case_count") != len(workers)
            or sanitized_payload.get("aggregate_metrics")
            != _mean_metrics(
                sanitized_payload.get("case_evaluations", {}),
                set(workers),
            )
            or judge.get("final_revision") != revision
            or judge.get("final_manifest_hash") != final_manifest_hash
            or judge.get("runtime_version") != PHASE74_RUNTIME_VERSION
            or judge.get("input_manifest") != expected_judge_manifest
            or judge.get("raw_output_hash")
            != judge["provenance"]["output_hash"]
            or judge.get("artifact_output_hash")
            != _canonical_hash(sanitized_payload)
            or judge.get("sanitizer_schema_version")
            != PHASE74_SANITIZER_SCHEMA_VERSION
            or judge.get("sanitization_binding_hash")
            != _canonical_hash(
                {
                    "doc_type": doc_type,
                    "raw_output_hash": judge["raw_output_hash"],
                    "artifact_output_hash": judge["artifact_output_hash"],
                    "input_manifest_hash": judge["provenance"][
                        "input_manifest_hash"
                    ],
                    "sanitizer_schema_version": (
                        PHASE74_SANITIZER_SCHEMA_VERSION
                    ),
                }
            )
        ):
            raise EvidenceValidationError("Judge coverage/binding mismatch")
        provenance = judge["provenance"]
        _validate_runtime_constants(provenance, role="judge")
        try:
            validate_persisted_agent_provenance(
                provenance,
                expected_engine="copilot-sdk",
                expected_is_live=True,
                role="judge",
                model="claude-opus-4.8",
                effort="xhigh",
                context_tier="long_context",
                prompt_hash=provenance["prompt_hash"],
                attachment_hashes=provenance["attachment_hashes"],
                output_hash=provenance["output_hash"],
                extra_digest_fields=_JUDGE_PROVENANCE_EXTRA_FIELDS,
                required_hash_fields=(
                    "prompt_contract_hash",
                    "input_manifest_hash",
                    "research_hash",
                    "ground_truth_hash",
                    "artifact_output_hash",
                ),
                required_hash_list_fields=(
                    "pdf_hashes",
                    "worker_report_hashes",
                    "worker_input_manifest_hashes",
                    "public_bundle_hashes",
                    "worker_prompt_hashes",
                ),
            )
        except AgentRuntimeError as error:
            raise EvidenceValidationError("Judge provenance invalid") from error
        if (
            provenance["case_ids"] != sorted(workers)
            or provenance["input_manifest_hash"]
            != _canonical_hash(expected_judge_manifest)
            or provenance["pdf_hashes"]
            != expected_judge_manifest["pdf_hashes"]
            or provenance["research_hash"]
            != expected_judge_manifest["research_hash"]
            or provenance["ground_truth_hash"]
            != expected_judge_manifest["ground_truth_hash"]
            or provenance["prompt_contract_hash"]
            != expected_judge_manifest["prompt_contract_hash"]
            or provenance["model_config"]
            != expected_judge_manifest["model_config"]
            or provenance["worker_report_hashes"]
            != [workers[case_id]["report_hash"] for case_id in sorted(workers)]
            or provenance["worker_input_manifest_hashes"]
            != expected_judge_manifest["worker_input_manifest_hashes"]
            or provenance["public_bundle_hashes"]
            != expected_judge_manifest["public_bundle_hashes"]
            or provenance["worker_prompt_hashes"]
            != expected_judge_manifest["worker_prompt_hashes"]
            or provenance["attachment_hashes"] != provenance["pdf_hashes"]
        ):
            raise EvidenceValidationError("Judge input hash binding mismatch")
        judge_count += 1
        judge_binding_records.append(
            {
                "doc_type": doc_type,
                "raw_output_hash": judge["raw_output_hash"],
                "artifact_output_hash": judge["artifact_output_hash"],
                "input_manifest_hash": provenance["input_manifest_hash"],
                "sanitizer_schema_version": judge[
                    "sanitizer_schema_version"
                ],
                "sanitization_binding_hash": judge[
                    "sanitization_binding_hash"
                ],
            }
        )

        shared = _validate_self_hash(document_dir / "shared_evaluation.json")
        _validate_model(shared, SharedEvaluationRecord, "shared evaluation")
        if (
            shared.get("schema_version")
            != "phase74-shared-evaluation-record-v1"
            or shared.get("doc_type") != doc_type
            or shared.get("status") != "completed"
            or shared.get("final_revision") != revision
            or shared.get("final_manifest_hash") != final_manifest_hash
            or shared.get("runtime_version") != PHASE74_RUNTIME_VERSION
            or shared.get("decision") != "rejected"
            or shared.get("shared_candidate_id")
            != shared_decision["candidate_id"]
            or shared.get("shared_candidate_hash")
            != shared_decision["candidate_content_hash"]
            or shared.get("shared_decision_hash")
            != shared_decision["shared_decision_hash"]
            or shared.get("shared_run_id") != manifest["run_id"]
            or shared.get("shared_target_file") != "skills/pdf/SKILL.md"
            or shared.get("shared_source_revision") != revision
            or shared.get("shared_input_findings_hash")
            != shared_decision["input_findings_hash"]
            or shared.get("shared_prompt_hash")
            != shared_decision["prompt_hash"]
            or shared.get("shared_optimizer_output_hash")
            != shared_decision["optimizer_output_hash"]
        ):
            raise EvidenceValidationError("Shared evaluation binding mismatch")
        try:
            provenance = shared["shared_optimizer_provenance"]
            validate_persisted_agent_provenance(
                provenance,
                expected_engine="copilot-sdk",
                expected_is_live=True,
                role="optimizer",
                model="gemini-3.6-flash",
                effort=None,
                context_tier="long_context",
                prompt_hash=provenance["prompt_hash"],
                attachment_hashes=[],
                output_hash=provenance["output_hash"],
                extra_digest_fields=_OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
                required_hash_fields=(
                    "input_findings_sha256",
                    "candidate_content_hash",
                ),
            )
        except (AgentRuntimeError, KeyError) as error:
            raise EvidenceValidationError(
                "Shared optimizer provenance is invalid"
            ) from error
        for delta_name, baseline_name, candidate_name in (
            ("training_deltas", "baseline_train", "candidate_train"),
            ("holdout_deltas", "baseline_holdout", "candidate_holdout"),
        ):
            for field, delta in shared[delta_name].items():
                expected = shared[candidate_name][field] - shared[baseline_name][field]
                if abs(delta - expected) > 1e-9:
                    raise EvidenceValidationError("Shared metric delta mismatch")
        if (
            shared["shared_optimizer_provenance"]
            != shared_decision["optimizer_provenance"]
        ):
            raise EvidenceValidationError(
                "Shared optimizer provenance differs across documents"
            )
        shared_count += 1
        shared_records.append(shared)

    if (
        worker_count != 236
        or judge_count != 23
        or shared_count != 23
        or manifest.get("worker_count") != 236
        or manifest.get("judge_count") != 23
        or manifest.get("shared_evaluation_count") != 23
    ):
        raise EvidenceValidationError("Final evidence counts are incomplete")
    if (
        len(judge_binding_records) != 23
        or _judge_binding_set_hash(judge_binding_records)
        != PHASE74_JUDGE_BINDING_SET_HASH
        or manifest["judge_binding_set_hash"]
        != PHASE74_JUDGE_BINDING_SET_HASH
    ):
        raise EvidenceValidationError("Judge sanitization binding set mismatch")
    citation_records = corpus_commitment["citations"]
    if (
        len(citation_records) != 25
        or len({record["citation_id"] for record in citation_records}) != 25
        or [record["citation_id"] for record in citation_records]
        != sorted(worker_citations)
        or corpus_commitment["citation_set_hash"]
        != PHASE74_CITATION_SET_HASH
        or _citation_commitment_set_hash(citation_records)
        != PHASE74_CITATION_SET_HASH
        or any(
            record["citation_id_hash"]
            != hashlib.sha256(record["citation_id"].encode("utf-8")).hexdigest()
            for record in citation_records
        )
    ):
        raise EvidenceValidationError("Corpus citation commitments are incomplete")
    for document_dir in document_dirs:
        doc_type = document_dir.name
        per_document = {
            citation
            for path in (document_dir / "workers").glob("*.json")
            for citation in json.loads(path.read_text())["citation_ids"]
        }
        if corpus_commitment["bundle_citation_ids"].get(doc_type) != sorted(
            per_document
        ):
            raise EvidenceValidationError(
                "Per-bundle citation commitment mismatch"
            )

    def aggregate_shared(metric_name: str, count_name: str) -> dict[str, float]:
        total = sum(record[count_name] for record in shared_records)
        return {
            field: sum(
                record[metric_name][field] * record[count_name]
                for record in shared_records
            )
            / total
            for field in (*_SCORE_FIELDS, "overall_score")
        }

    for metric_name, count_name in (
        ("baseline_train", "training_count"),
        ("candidate_train", "training_count"),
        ("baseline_holdout", "holdout_count"),
        ("candidate_holdout", "holdout_count"),
    ):
        aggregate = aggregate_shared(metric_name, count_name)
        if any(
            abs(aggregate[field] - shared_decision[metric_name][field]) > 1e-9
            for field in aggregate
        ):
            raise EvidenceValidationError(
                "Shared aggregate metrics do not match 23 document records"
            )

    concurrency = _validate_self_hash(evidence_root / "concurrency.json")
    _validate_model(concurrency, ConcurrencyEvidence, "concurrency")
    active = 0
    peak = 0
    documents: set[str] = set()
    process_events: dict[str, list[dict[str, Any]]] = {}
    parsed_event_order = [
        (
            datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")),
            event["sequence"],
        )
        for event in concurrency["events"]
    ]
    if (
        [event["sequence"] for event in concurrency["events"]]
        != list(range(1, len(concurrency["events"]) + 1))
        or parsed_event_order != sorted(parsed_event_order)
    ):
        raise EvidenceValidationError("Concurrency events are not globally ordered")
    for event in concurrency["events"]:
        if event["active_before"] != active:
            raise EvidenceValidationError("Concurrency active-before mismatch")
        active += 1 if event["event"] == "start" else -1
        if active != event["active_after"] or active < 0 or active > 5:
            raise EvidenceValidationError("Concurrency trace is inconsistent")
        peak = max(peak, active)
        documents.add(event["doc_type"])
        process_events.setdefault(event["process_instance_hash"], []).append(
            event
        )
    process_pair_invalid = False
    for instance_events in process_events.values():
        if len(instance_events) != 2:
            process_pair_invalid = True
            continue
        start_events = [
            event for event in instance_events if event["event"] == "start"
        ]
        end_events = [
            event for event in instance_events if event["event"] == "end"
        ]
        if len(start_events) != 1 or len(end_events) != 1:
            process_pair_invalid = True
            continue
        start_event, end_event = start_events[0], end_events[0]
        immutable_fields = (
            "doc_type",
            "phase",
            "role",
            "process_kind",
            "run_id",
            "process_instance_hash",
        )
        if (
            any(
                start_event[field] != end_event[field]
                for field in immutable_fields
            )
            or datetime.fromisoformat(
                start_event["timestamp"].replace("Z", "+00:00")
            )
            >= datetime.fromisoformat(
                end_event["timestamp"].replace("Z", "+00:00")
            )
            or (
                start_event["phase"] == "parent"
                and (
                    start_event["doc_type"] != "__preflight__"
                    or start_event["role"] != "preflight"
                    or start_event["process_kind"] != "sdk_preflight"
                    or start_event["run_id"] != manifest["run_id"]
                )
            )
            or (
                start_event["phase"] != "parent"
                and (
                    start_event["doc_type"] not in expected_doc_types
                    or start_event["role"] != "document_pipeline"
                    or start_event["process_kind"] != "document_child"
                    or start_event["run_id"]
                    != f"{manifest['run_id']}-{start_event['phase']}"
                )
            )
        ):
            process_pair_invalid = True
    if (
        active != 0
        or peak != 5
        or concurrency.get("declared_peak") != 5
        or concurrency.get("slot_limit") != 5
        or {
            doc_type for doc_type in documents if doc_type != "__preflight__"
        }
        != set(expected_doc_types)
        or process_pair_invalid
        or concurrency.get("process_instance_count") != 93
        or concurrency.get("stage_instance_counts")
        != {
            "parent": 1,
            "optimization": 23,
            "shared-baseline": 23,
            "shared-candidate": 23,
            "final": 23,
        }
        or dict(
            Counter(
                event["phase"]
                for event in concurrency["events"]
                if event["event"] == "start"
            )
        )
        != concurrency["stage_instance_counts"]
    ):
        raise EvidenceValidationError("Concurrency evidence does not prove five slots")

    cleanup = _validate_self_hash(evidence_root / "cleanup.json")
    _validate_model(cleanup, CleanupEvidence, "cleanup")
    if (
        cleanup.get("supervisor_status") != "completed"
        or cleanup.get("lease_status") != "released"
        or cleanup.get("survivor_count") != 0
        or cleanup.get("error_count") != 0
        or cleanup.get("registry_record_count")
        != cleanup.get("registry_reaped_count")
        or cleanup.get("registry_record_count") != 93
        or cleanup.get("registry_record_count") != len(process_events)
        or cleanup.get("process_instance_hashes") != sorted(process_events)
        or datetime.fromisoformat(
            cleanup["reconciled_at"].replace("Z", "+00:00")
        )
        < max(
            datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            for event in concurrency["events"]
            if event["event"] == "end"
        )
    ):
        raise EvidenceValidationError("Cleanup/reconciliation evidence is incomplete")

    frozen = _validate_self_hash(evidence_root / "frozen_manifest.json")
    _validate_model(frozen, FrozenManifestEvidence, "frozen manifest")
    raw_manifest = frozen.get("final_manifest")
    if (
        not isinstance(raw_manifest, dict)
        or raw_manifest.get("manifest_hash") != final_manifest_hash
        or _canonical_hash(
            {
                key: value
                for key, value in raw_manifest.items()
                if key != "manifest_hash"
            }
        )
        != final_manifest_hash
        or raw_manifest.get("git_revision") != revision
        or raw_manifest.get("bundle_hashes") != manifest.get("bundle_hashes")
        or raw_manifest.get("source_hashes") != manifest.get("source_hashes")
    ):
        raise EvidenceValidationError("Frozen final manifest evidence is invalid")
    if (
        manifest["concurrency_hash"] != concurrency["evidence_hash"]
        or manifest["cleanup_hash"] != cleanup["evidence_hash"]
        or manifest["shared_decision_hash"]
        != shared_decision["evidence_hash"]
        or manifest["frozen_manifest_evidence_hash"]
        != frozen["evidence_hash"]
    ):
        raise EvidenceValidationError(
            "Final evidence manifest cross-link hash mismatch"
        )

    accepted = _validate_self_hash(evidence_root / "accepted_patches.json")
    _validate_model(accepted, AcceptedPatchCollection, "accepted patches")
    if len(accepted.get("records", [])) != 11:
        raise EvidenceValidationError("Cumulative accepted patch evidence is incomplete")
    accepted_records = accepted["records"]
    if [record["sequence"] for record in accepted_records] != list(range(1, 12)):
        raise EvidenceValidationError("Accepted patch sequence is not canonical")
    actual_bindings = tuple(
        (
            record["commit"],
            record["parent_run_id"],
            record["doc_type"],
            record["candidate_id"],
            record["target_file"],
        )
        for record in accepted_records
    )
    if actual_bindings != _EXPECTED_ACCEPTED_BINDINGS:
        raise EvidenceValidationError(
            "Cumulative accepted patch identities do not match audited sequence"
        )
    if (
        len({record["commit"] for record in accepted_records}) != 11
        or len({record["candidate_id"] for record in accepted_records}) != 11
        or len(
            {
                (record["parent_run_id"], record["doc_type"])
                for record in accepted_records
            }
        )
        != 11
    ):
        raise EvidenceValidationError("Accepted patch identities are not unique")
    for earlier, later in zip(accepted_records, accepted_records[1:]):
        if subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                earlier["commit"],
                later["commit"],
            ],
            cwd=source_root,
        ).returncode != 0:
            raise EvidenceValidationError("Accepted patch sequence is not ordered")
    for record in accepted_records:
        if record.get("evidence_hash") != canonical_evidence_hash(record):
            raise EvidenceValidationError("Accepted patch record hash mismatch")
        if (
            record["completed_run_id"] != manifest["run_id"]
            or record["final_manifest_hash"] != final_manifest_hash
            or record["parent_run_id"] != _parent_run_id(record["run_id"])
            or record["completed_supervisor_result_hash"]
            != cleanup["supervisor_result_hash"]
        ):
            raise EvidenceValidationError("Accepted patch run binding is invalid")
        _validate_git_patch_record(record, source_root)

    rejected = _validate_self_hash(evidence_root / "rejected_patches.json")
    _validate_model(rejected, RejectedPatchCollection, "rejected patches")
    if len(rejected.get("records", [])) != 23:
        raise EvidenceValidationError("Final-run rejected patch evidence is incomplete")
    rejected_records = rejected["records"]
    if len({record["doc_type"] for record in rejected_records}) != 23:
        raise EvidenceValidationError("Rejected patch documents are duplicated")
    final_accepted = {
        record["doc_type"]
        for record in accepted_records
        if record["parent_run_id"] == manifest["run_id"]
    }
    rejected_docs = {record["doc_type"] for record in rejected_records}
    if (
        len(final_accepted) != 0
        or final_accepted & rejected_docs
        or final_accepted | rejected_docs != set(expected_doc_types)
        or manifest.get("final_run_accepted_patch_count") != 0
        or manifest.get("final_run_rejected_patch_count") != 23
    ):
        raise EvidenceValidationError(
            "Final-run accepted/rejected decisions do not partition 23 documents"
        )
    for record in rejected_records:
        if record.get("evidence_hash") != canonical_evidence_hash(record):
            raise EvidenceValidationError("Rejected patch record hash mismatch")
        if (
            record["parent_run_id"] != manifest["run_id"]
            or record["parent_run_id"] != _parent_run_id(record["run_id"])
            or record["final_manifest_hash"] != final_manifest_hash
            or record["runtime_version"] != PHASE74_RUNTIME_VERSION
            or record["completed_supervisor_result_hash"]
            != cleanup["supervisor_result_hash"]
        ):
            raise EvidenceValidationError("Rejected patch run binding is invalid")
        expected_stem = DOC_TYPE_TO_SKILL.get(
            record["doc_type"],
            record["doc_type"].replace("_", "-"),
        )
        expected_target = f"skills/document-agents/{expected_stem}.md"
        if (
            record["target_file"] != expected_target
            or _git_blob_hash(
                source_root,
                record["source_revision"],
                record["target_file"],
            )
            != record["source_hash"]
        ):
            raise EvidenceValidationError(
                "Rejected patch target/source binding is invalid"
            )
        provenance = record["optimizer_provenance"]
        if (
            provenance["target_file"] != record["target_file"]
            or provenance["candidate_id"] != record["candidate_id"]
            or provenance["candidate_content_hash"]
            != record["candidate_content_hash"]
            or provenance["output_hash"] != record["optimizer_response_hash"]
            or record["candidate_id"]
            != derive_optimizer_candidate_id(
                provenance["input_findings_sha256"],
                provenance["prompt_hash"],
                record["target_file"],
            )
        ):
            raise EvidenceValidationError(
                "Rejected candidate provenance binding failed"
            )
        try:
            _validate_optimizer_provenance_evidence(
                record["optimizer_provenance"],
                record.get("optimizer_turn_evidence"),
            )
        except (AgentRuntimeError, KeyError) as error:
            raise EvidenceValidationError(
                "Rejected optimizer provenance is invalid"
            ) from error
        metric_fields = (
            "baseline_train",
            "candidate_train",
            "training_deltas",
            "baseline_holdout",
            "candidate_holdout",
            "holdout_deltas",
        )
        if record["reason_code"] == "metric_gate_rejected":
            if any(record[field] is None for field in metric_fields):
                raise EvidenceValidationError("Rejected metric evidence is incomplete")
            _validate_metric_delta(
                record["baseline_train"],
                record["candidate_train"],
                record["training_deltas"],
                label="rejected training",
            )
            _validate_metric_delta(
                record["baseline_holdout"],
                record["candidate_holdout"],
                record["holdout_deltas"],
                label="rejected holdout",
            )
            if _patch_would_be_accepted(record):
                raise EvidenceValidationError(
                    "Rejected patch recomputes as accepted"
                )
            raw_metrics = {
                "baseline_train": record["baseline_train"],
                "candidate_train": record["candidate_train"],
                "baseline_holdout": record["baseline_holdout"],
                "candidate_holdout": record["candidate_holdout"],
            }
        elif any(record[field] is not None for field in metric_fields):
            raise EvidenceValidationError(
                "Candidate-evaluation rejection must not claim metrics"
            )
        else:
            raw_metrics = {}
        if record["decision_binding_hash"] != _canonical_hash(
            {
                "status": "rejected",
                "target_file": record["target_file"],
                "candidate_id": record["candidate_id"],
                "candidate_content_hash": record["candidate_content_hash"],
                "source_hash": record["source_hash"],
                "metrics": raw_metrics,
            }
        ):
            raise EvidenceValidationError("Rejected decision binding hash mismatch")
        if record["run_binding_hash"] != _canonical_hash(
            {
                "run_id": record["run_id"],
                "parent_run_id": record["parent_run_id"],
                "run_manifest_hash": record["run_manifest_hash"],
                "decision_output_hash": record["decision_output_hash"],
            }
        ):
            raise EvidenceValidationError("Rejected run binding hash mismatch")
    return {
        "status": "CONFORMANT",
        "document_types": 23,
        "workers": worker_count,
        "judges": judge_count,
        "shared_evaluations": shared_count,
        "accepted_patches": 11,
        "rejected_patches": 23,
        "peak_concurrency": peak,
        "final_revision": revision,
        "final_manifest_hash": final_manifest_hash,
    }
