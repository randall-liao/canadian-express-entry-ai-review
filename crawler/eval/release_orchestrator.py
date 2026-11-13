"""PII-free Phase 75 release assessment through the official Copilot SDK."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from crawler.eval.agent_runtime import (
    AgentProvenance,
    AgentRequest,
    AgentRuntime,
    run_async,
    validate_agent_result,
)
from crawler.eval.copilot_sdk_runtime import CopilotSdkRuntime
from crawler.eval.phase74_evidence import (
    validate_committed_phase74_evidence,
)
from crawler.eval.pipeline_state import atomic_write_json
from crawler.synthetic.schemas import ExpressEntryDocType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_DOCUMENT_TYPES = tuple(
    sorted(doc_type.value for doc_type in ExpressEntryDocType)
)

_HASH = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$"),
]
_REVISION = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-f0-9]{40,64}$"),
]
_TARGET_FILE = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=(
            r"^(?:AGENTS\.md|skills/(?:pdf/SKILL\.md|"
            r"document-agents/[a-z0-9-]+\.md))$"
        ),
    ),
]
_RUN_ID = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=r"^sdk-[0-9TZ-]+-[a-f0-9]{12}$",
    ),
]
_DOC_TYPE = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]+$"),
]
_PRIVATE_KEY = re.compile(
    r"(?:^|_)(?:applicant|candidate|vault|birth_date|date_of_birth|dob|"
    r"passport_number|document_number|full_name|person_name|given_name|"
    r"family_name|first_name|last_name|surname)(?:_|$)",
    re.IGNORECASE,
)
_PRIVATE_VALUE = re.compile(
    r"Jane Synthetic|John Synthetic|Jane Doe|John Doe|"
    r"/(?:home|Users)/|[A-Za-z]:[/\\]Users[/\\]|"
    r"\b[A-Z]\d{7,8}\b|\b\d{3}[- ]?\d{3}[- ]?\d{3}\b|"
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
_SCORE_FIELDS = (
    "grounding_accuracy",
    "citation_exactness",
    "defect_recall",
    "pii_containment",
    "blind_input_compliance",
    "overall_score",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReleaseScoreMetrics(_StrictModel):
    grounding_accuracy: float = Field(ge=0.0, le=1.0)
    citation_exactness: float = Field(ge=0.0, le=1.0)
    defect_recall: float = Field(ge=0.0, le=1.0)
    pii_containment: float = Field(ge=0.0, le=1.0)
    blind_input_compliance: float = Field(ge=0.0, le=1.0)
    overall_score: float = Field(ge=0.0, le=1.0)

    @field_validator("*", mode="before")
    @classmethod
    def finite_numeric(cls, value: Any) -> Any:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not float("-inf") < float(value) < float("inf")
        ):
            raise ValueError("release score must be finite numeric")
        return float(value)


class ReleaseMetricDeltas(_StrictModel):
    grounding_accuracy: float = Field(ge=-1.0, le=1.0)
    citation_exactness: float = Field(ge=-1.0, le=1.0)
    defect_recall: float = Field(ge=-1.0, le=1.0)
    pii_containment: float = Field(ge=-1.0, le=1.0)
    blind_input_compliance: float = Field(ge=-1.0, le=1.0)
    overall_score: float = Field(ge=-1.0, le=1.0)

    @field_validator("*", mode="before")
    @classmethod
    def finite_numeric(cls, value: Any) -> Any:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not float("-inf") < float(value) < float("inf")
        ):
            raise ValueError("release delta must be finite numeric")
        return float(value)


class ReleaseDocumentEvidence(_StrictModel):
    doc_type: _DOC_TYPE
    status: Literal["completed", "blocked"]
    case_count: int = Field(ge=1)
    worker_count: int = Field(ge=0)
    judge_count: int = Field(ge=0, le=1)
    shared_evaluation_count: int = Field(ge=0, le=1)
    baseline_metrics: ReleaseScoreMetrics
    final_metrics: ReleaseScoreMetrics
    metric_deltas: ReleaseMetricDeltas
    accepted_patch_count: int = Field(ge=0)
    rejected_patch_count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_coverage(self) -> "ReleaseDocumentEvidence":
        if self.status == "completed":
            if (
                self.worker_count != self.case_count
                or self.judge_count != 1
                or self.shared_evaluation_count != 1
            ):
                raise ValueError(
                    f"Completed document {self.doc_type} has incomplete coverage"
                )
            if self.blockers:
                raise ValueError(
                    f"Completed document {self.doc_type} cannot claim blockers"
                )
        elif not self.blockers:
            raise ValueError(
                f"Blocked document {self.doc_type} requires a blocker"
            )
        for field in _SCORE_FIELDS:
            expected = getattr(self.final_metrics, field) - getattr(
                self.baseline_metrics,
                field,
            )
            if abs(getattr(self.metric_deltas, field) - expected) > 1e-9:
                raise ValueError(
                    f"Document {self.doc_type} metric delta mismatch"
                )
        return self


class ValidationResult(_StrictModel):
    name: Annotated[
        str,
        StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9-]+$"),
    ]
    command: str = Field(min_length=1, max_length=2000)
    status: Literal["passed", "failed", "timed_out", "blocked"]
    duration_seconds: float = Field(ge=0.0)
    detail: str = Field(min_length=1, max_length=2000)

    @field_validator("duration_seconds", mode="before")
    @classmethod
    def finite_duration(cls, value: Any) -> Any:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not float("-inf") < float(value) < float("inf")
        ):
            raise ValueError("validation duration must be finite numeric")
        return float(value)


class ReleasePatchEvidence(_StrictModel):
    sequence: int = Field(ge=1)
    doc_type: _DOC_TYPE
    commit: _REVISION
    target_file: _TARGET_FILE
    training_overall_delta: float = Field(gt=0.0, le=1.0)
    holdout_overall_delta: float = Field(ge=-1e-6, le=1.0)

    @field_validator(
        "training_overall_delta",
        "holdout_overall_delta",
        mode="before",
    )
    @classmethod
    def finite_delta(cls, value: Any) -> Any:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not float("-inf") < float(value) < float("inf")
        ):
            raise ValueError("patch delta must be finite numeric")
        return float(value)


class ReleaseEvidence(_StrictModel):
    schema_version: Literal["phase75-release-evidence-v1"]
    phase72_research_documents: Literal[23]
    phase73_logical_cases: Literal[118]
    phase73_pdf_count: Literal[236]
    phase74_run_id: _RUN_ID
    phase74_final_revision: _REVISION
    phase74_final_manifest_hash: _HASH
    phase74_evidence_manifest_hash: _HASH
    sdk_version: Literal["1.0.8"]
    runtime_version: str = Field(min_length=1, max_length=64)
    protocol_version: Literal["3"]
    worker_model: Literal["gemini-3.6-flash"]
    optimizer_model: Literal["gemini-3.6-flash"]
    judge_model: Literal["claude-opus-4.8"]
    judge_effort: Literal["xhigh"]
    orchestrator_model: Literal["gpt-5.6-sol"]
    context_tier: Literal["long_context"]
    worker_count: Literal[236]
    judge_count: Literal[23]
    optimizer_count: Literal[23]
    shared_evaluation_count: Literal[23]
    accepted_patch_count: int = Field(ge=0)
    rejected_patch_count: int = Field(ge=0)
    accepted_patches: list[ReleasePatchEvidence]
    peak_concurrency: Literal[5]
    imported_model_artifact_count: Literal[0]
    cleanup_survivor_count: Literal[0]
    cleanup_error_count: Literal[0]
    documents: list[ReleaseDocumentEvidence]
    validation_results: list[ValidationResult]
    blockers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_totals(self) -> "ReleaseEvidence":
        if len(self.documents) != 23:
            raise ValueError("Release evidence requires exactly 23 documents")
        doc_types = [document.doc_type for document in self.documents]
        if tuple(doc_types) != _EXPECTED_DOCUMENT_TYPES:
            raise ValueError(
                "Release evidence must cover the canonical document inventory"
            )
        if sum(document.case_count for document in self.documents) != 236:
            raise ValueError("Release evidence case coverage must equal 236")
        if sum(document.worker_count for document in self.documents) != 236:
            raise ValueError("Release evidence Worker coverage must equal 236")
        if sum(document.judge_count for document in self.documents) != 23:
            raise ValueError("Release evidence Judge coverage must equal 23")
        if (
            sum(
                document.shared_evaluation_count
                for document in self.documents
            )
            != 23
        ):
            raise ValueError(
                "Release evidence shared evaluation coverage must equal 23"
            )
        if (
            sum(
                document.accepted_patch_count
                for document in self.documents
            )
            != self.accepted_patch_count
            or sum(
                document.rejected_patch_count
                for document in self.documents
            )
            != self.rejected_patch_count
        ):
            raise ValueError("Release evidence patch totals are inconsistent")
        if (
            len(self.accepted_patches) != self.accepted_patch_count
            or [patch.sequence for patch in self.accepted_patches]
            != list(range(1, self.accepted_patch_count + 1))
            or any(
                patch.doc_type not in _EXPECTED_DOCUMENT_TYPES
                for patch in self.accepted_patches
            )
        ):
            raise ValueError(
                "Release evidence accepted patch sequence is inconsistent"
            )
        if not self.validation_results:
            raise ValueError("Release evidence requires validation results")
        if any(document.status == "blocked" for document in self.documents):
            if not self.blockers:
                raise ValueError(
                    "Blocked document coverage requires release blockers"
                )
        return self


class ReleaseAssessment(_StrictModel):
    schema_version: Literal["phase75-release-assessment-v1"]
    verdict: Literal["ready", "blocked"]
    phase74_run_id: _RUN_ID
    evidence_manifest_hash: _HASH
    release_evidence_hash: _HASH
    summary: str = Field(min_length=1, max_length=4000)
    strengths: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_verdict(self) -> "ReleaseAssessment":
        if self.verdict == "ready" and self.blockers:
            raise ValueError("Ready release assessment cannot contain blockers")
        if self.verdict == "blocked" and not self.blockers:
            raise ValueError("Blocked release assessment requires blockers")
        return self


def _assert_public_aggregate(value: Any, *, location: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("Release evidence contains a private key")
            if _PRIVATE_KEY.search(key):
                raise ValueError(
                    f"Release evidence contains private field at {location}"
                )
            _assert_public_aggregate(child, location=f"{location}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for index, child in enumerate(value):
            _assert_public_aggregate(
                child,
                location=f"{location}[{index}]",
            )
        return
    if isinstance(value, str) and _PRIVATE_VALUE.search(value):
        raise ValueError(
            f"Release evidence contains private content at {location}"
        )


def build_release_evidence(payload: Mapping[str, Any]) -> ReleaseEvidence:
    """Validate one already-measured PII-free release evidence payload."""
    if not isinstance(payload, Mapping):
        raise ValueError("Release evidence must be a mapping")
    _assert_public_aggregate(payload)
    return ReleaseEvidence.model_validate(dict(payload))


def release_evidence_hash(evidence: Any) -> str:
    """Return the canonical digest bound into the model assessment."""
    model_dump = getattr(evidence, "model_dump", None)
    if not callable(model_dump):
        raise ValueError("Release evidence hash requires validated evidence")
    try:
        validated = ReleaseEvidence.model_validate(model_dump(mode="json"))
    except ValueError as error:
        raise ValueError(
            "Release evidence hash requires validated evidence"
        ) from error
    canonical = json.dumps(
        validated.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Committed release evidence file is invalid: {path.name}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(
            f"Committed release evidence file is not an object: {path.name}"
        )
    return payload


def _weighted_baseline(
    shared: Mapping[str, Any],
    *,
    case_count: int,
) -> dict[str, float]:
    if isinstance(case_count, bool) or not isinstance(case_count, int) or case_count <= 0:
        raise ValueError(
            "Committed baseline metric case count must be positive"
        )
    training_count = shared.get("training_count")
    holdout_count = shared.get("holdout_count")
    train = shared.get("baseline_train")
    holdout = shared.get("baseline_holdout")
    if (
        isinstance(training_count, bool)
        or not isinstance(training_count, int)
        or isinstance(holdout_count, bool)
        or not isinstance(holdout_count, int)
        or training_count < 0
        or holdout_count < 0
        or training_count + holdout_count != case_count
        or not isinstance(train, Mapping)
        or not isinstance(holdout, Mapping)
    ):
        raise ValueError("Committed baseline metric coverage is invalid")
    weighted: dict[str, float] = {}
    for field in _SCORE_FIELDS:
        train_value = train.get(field)
        holdout_value = holdout.get(field)
        if (
            isinstance(train_value, bool)
            or not isinstance(train_value, (int, float))
            or isinstance(holdout_value, bool)
            or not isinstance(holdout_value, (int, float))
        ):
            raise ValueError("Committed baseline metrics are invalid")
        weighted[field] = (
            float(train_value) * training_count
            + float(holdout_value) * holdout_count
        ) / case_count
    return weighted


def _validated_patch_records(
    accepted_root: Mapping[str, Any],
    rejected_root: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    accepted_records = accepted_root.get("records")
    rejected_records = rejected_root.get("records")
    if (
        not isinstance(accepted_records, list)
        or not isinstance(rejected_records, list)
        or any(
            not isinstance(record, Mapping)
            for record in accepted_records
        )
        or any(
            not isinstance(record, Mapping)
            for record in rejected_records
        )
    ):
        raise ValueError("Committed patch records are invalid")
    return accepted_records, rejected_records


def load_release_evidence(
    evidence_root: Path,
    *,
    validation_results: Sequence[Mapping[str, Any]],
    source_root: Path = _REPO_ROOT,
    phase74_validator: Callable[..., Mapping[str, Any]] = (
        validate_committed_phase74_evidence
    ),
) -> ReleaseEvidence:
    """Build release evidence only from validated committed Phase 74 files."""
    evidence_root = Path(evidence_root).resolve()
    source_root = Path(source_root).resolve()
    summary = phase74_validator(
        evidence_root,
        source_root=source_root,
    )
    if not isinstance(summary, Mapping) or summary.get("status") != "CONFORMANT":
        raise ValueError("Committed Phase 74 evidence is not conformant")

    manifest = _read_json_object(evidence_root / "manifest.json")
    required_summary = {
        "document_types": 23,
        "workers": 236,
        "judges": 23,
        "shared_evaluations": 23,
        "peak_concurrency": 5,
    }
    for key, expected in required_summary.items():
        if summary.get(key) != expected:
            raise ValueError(
                f"Committed Phase 74 summary has invalid {key}"
            )
    if (
        summary.get("final_revision") != manifest.get("final_revision")
        or summary.get("final_manifest_hash")
        != manifest.get("final_manifest_hash")
    ):
        raise ValueError("Committed Phase 74 summary binding is invalid")

    accepted_root = _read_json_object(
        evidence_root / "accepted_patches.json"
    )
    rejected_root = _read_json_object(
        evidence_root / "rejected_patches.json"
    )
    accepted_records, rejected_records = _validated_patch_records(
        accepted_root,
        rejected_root,
    )
    if (
        summary.get("accepted_patches") != len(accepted_records)
        or summary.get("rejected_patches") != len(rejected_records)
        or manifest.get("accepted_patch_count") != len(accepted_records)
    ):
        raise ValueError("Committed patch counts are inconsistent")
    accepted_by_doc = Counter(
        record.get("doc_type")
        for record in accepted_records
        if isinstance(record, Mapping)
    )
    rejected_by_doc = Counter(
        record.get("doc_type")
        for record in rejected_records
        if isinstance(record, Mapping)
    )
    if None in accepted_by_doc or None in rejected_by_doc:
        raise ValueError("Committed patch document binding is invalid")

    concurrency = _read_json_object(evidence_root / "concurrency.json")
    cleanup = _read_json_object(evidence_root / "cleanup.json")
    if (
        concurrency.get("declared_peak") != 5
        or concurrency.get("slot_limit") != 5
        or cleanup.get("supervisor_status") != "completed"
        or cleanup.get("lease_status") != "released"
        or cleanup.get("survivor_count") != 0
        or cleanup.get("error_count") != 0
    ):
        raise ValueError("Committed concurrency or cleanup evidence is invalid")
    if (
        manifest.get("optimizer_count") != 23
        or manifest.get("imported_model_artifact_count") != 0
    ):
        raise ValueError(
            "Committed optimizer/import coverage is incomplete"
        )

    documents_root = evidence_root / "documents"
    document_types = sorted(
        path.name
        for path in documents_root.iterdir()
        if path.is_dir()
    )
    documents: list[dict[str, Any]] = []
    for doc_type in document_types:
        doc_root = documents_root / doc_type
        judge = _read_json_object(doc_root / "judge.json")
        shared = _read_json_object(doc_root / "shared_evaluation.json")
        if (
            judge.get("doc_type") != doc_type
            or shared.get("doc_type") != doc_type
            or shared.get("status") != "completed"
        ):
            raise ValueError("Committed document evidence binding is invalid")
        case_count = judge.get("case_count")
        sanitized = judge.get("sanitized_evaluation_payload")
        if (
            isinstance(case_count, bool)
            or not isinstance(case_count, int)
            or not isinstance(sanitized, Mapping)
            or not isinstance(sanitized.get("aggregate_metrics"), Mapping)
        ):
            raise ValueError("Committed final Judge evidence is invalid")
        baseline = _weighted_baseline(shared, case_count=case_count)
        final = dict(sanitized["aggregate_metrics"])
        deltas = {
            field: float(final[field]) - baseline[field]
            for field in _SCORE_FIELDS
        }
        documents.append(
            {
                "doc_type": doc_type,
                "status": "completed",
                "case_count": case_count,
                "worker_count": case_count,
                "judge_count": 1,
                "shared_evaluation_count": 1,
                "baseline_metrics": baseline,
                "final_metrics": final,
                "metric_deltas": deltas,
                "accepted_patch_count": accepted_by_doc[doc_type],
                "rejected_patch_count": rejected_by_doc[doc_type],
                "blockers": [],
            }
        )

    validated_results = [
        ValidationResult.model_validate(dict(result)).model_dump(mode="json")
        for result in validation_results
    ]
    blockers = [
        f"{result['name']}: {result['status']} - {result['detail']}"
        for result in validated_results
        if result["status"] != "passed"
    ]
    return build_release_evidence(
        {
            "schema_version": "phase75-release-evidence-v1",
            "phase72_research_documents": 23,
            "phase73_logical_cases": 118,
            "phase73_pdf_count": 236,
            "phase74_run_id": manifest.get("run_id"),
            "phase74_final_revision": manifest.get("final_revision"),
            "phase74_final_manifest_hash": manifest.get(
                "final_manifest_hash"
            ),
            "phase74_evidence_manifest_hash": manifest.get("manifest_hash"),
            "sdk_version": manifest.get("sdk_version"),
            "runtime_version": manifest.get("runtime_version"),
            "protocol_version": manifest.get("protocol_version"),
            "worker_model": manifest.get("worker_model"),
            "optimizer_model": "gemini-3.6-flash",
            "judge_model": manifest.get("judge_model"),
            "judge_effort": manifest.get("judge_effort"),
            "orchestrator_model": "gpt-5.6-sol",
            "context_tier": manifest.get("context_tier"),
            "worker_count": summary.get("workers"),
            "judge_count": summary.get("judges"),
            "optimizer_count": manifest.get("optimizer_count"),
            "shared_evaluation_count": summary.get("shared_evaluations"),
            "accepted_patch_count": len(accepted_records),
            "rejected_patch_count": len(rejected_records),
            "accepted_patches": [
                {
                    "sequence": record.get("sequence"),
                    "doc_type": record.get("doc_type"),
                    "commit": record.get("commit"),
                    "target_file": record.get("target_file"),
                    "training_overall_delta": (
                        record.get("training_deltas") or {}
                    ).get("overall_score"),
                    "holdout_overall_delta": (
                        record.get("holdout_deltas") or {}
                    ).get("overall_score"),
                }
                for record in accepted_records
            ],
            "peak_concurrency": summary.get("peak_concurrency"),
            "imported_model_artifact_count": manifest.get(
                "imported_model_artifact_count"
            ),
            "cleanup_survivor_count": cleanup.get("survivor_count"),
            "cleanup_error_count": cleanup.get("error_count"),
            "documents": documents,
            "validation_results": validated_results,
            "blockers": blockers,
        }
    )


def _build_release_prompt(evidence: ReleaseEvidence) -> str:
    evidence_json = json.dumps(
        evidence.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "Assess whether the measured Canadian Express Entry document-review "
        "pipeline is ready to release. Use only the PII-free evidence JSON "
        "below. Do not change, infer, or restate counts, hashes, scores, model "
        "assignments, commands, or statuses as new facts. Identify blockers "
        "only from this evidence. Return exactly one raw JSON object with keys "
        "schema_version, verdict, phase74_run_id, evidence_manifest_hash, "
        "release_evidence_hash, summary, strengths, blockers, "
        "recommendations. schema_version must "
        "be phase75-release-assessment-v1; verdict must be ready or blocked. "
        "Copy phase74_run_id, evidence_manifest_hash, and this exact release "
        f"evidence hash: {release_evidence_hash(evidence)}.\n\n"
        f"EVIDENCE_JSON={evidence_json}"
    )


async def _run_release_assessment_with_raw(
    evidence: ReleaseEvidence,
    *,
    runtime: AgentRuntime | None = None,
) -> tuple[ReleaseAssessment, AgentProvenance, str]:
    """Run and validate one official-SDK release assessment."""
    model_dump = getattr(evidence, "model_dump", None)
    if not callable(model_dump):
        raise ValueError("Release assessment requires validated evidence")
    try:
        evidence = ReleaseEvidence.model_validate(model_dump(mode="json"))
    except ValueError as error:
        raise ValueError(
            "Release assessment requires validated evidence"
        ) from error
    prompt = _build_release_prompt(evidence)
    request = AgentRequest(
        role="orchestrator",
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        context_tier="long_context",
        prompt=prompt,
        attachments=[],
        timeout_seconds=900,
    )

    if runtime is not None:
        result = await runtime.run(request)
        provenance = validate_agent_result(
            result,
            request,
            expected_engine="injected-test-runner",
            expected_is_live=False,
        )
    else:
        with tempfile.TemporaryDirectory(
            prefix="phase75-release-",
        ) as temporary_directory:
            active_runtime = CopilotSdkRuntime(
                base_directory=Path(temporary_directory)
            )
            result = await active_runtime.run(request)
        provenance = validate_agent_result(result, request)

    try:
        assessment = ReleaseAssessment.model_validate_json(result.content)
    except ValueError as error:
        raise ValueError("Release assessment output is invalid") from error
    _assert_public_aggregate(assessment.model_dump(mode="json"))
    if (
        assessment.phase74_run_id != evidence.phase74_run_id
        or assessment.evidence_manifest_hash
        != evidence.phase74_evidence_manifest_hash
        or assessment.release_evidence_hash
        != release_evidence_hash(evidence)
    ):
        raise ValueError("Release assessment evidence binding mismatch")
    if evidence.blockers and assessment.verdict != "blocked":
        raise ValueError(
            "Release assessment cannot override measured blockers"
        )
    return assessment, provenance, result.content


async def run_release_assessment(
    evidence: ReleaseEvidence,
    *,
    runtime: AgentRuntime | None = None,
) -> tuple[ReleaseAssessment, AgentProvenance]:
    """Run one assessment without exposing raw SDK output to callers."""
    assessment, provenance, _ = await _run_release_assessment_with_raw(
        evidence,
        runtime=runtime,
    )
    return assessment, provenance


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


async def execute_release(
    evidence: ReleaseEvidence,
    *,
    report_path: Path,
    evidence_root: Path,
    runtime: AgentRuntime | None = None,
) -> dict[str, Any]:
    """Execute one assessment and atomically persist its public evidence."""
    from crawler.eval.test_report import render_test_report

    assessment, provenance, raw_response = (
        await _run_release_assessment_with_raw(
            evidence,
            runtime=runtime,
        )
    )
    report = render_test_report(evidence, assessment)
    report_path = Path(report_path)
    evidence_root = Path(evidence_root)
    assessment_record: dict[str, Any] = {
        "schema_version": "phase75-assessment-evidence-v1",
        "release_evidence_hash": release_evidence_hash(evidence),
        "assessment": assessment.model_dump(mode="json"),
        "provenance": asdict(provenance),
        "raw_response": raw_response,
    }
    _assert_public_aggregate(assessment_record)
    assessment_record["evidence_hash"] = _canonical_hash(assessment_record)
    release_record: dict[str, Any] = {
        "schema_version": "phase75-release-evidence-record-v1",
        "release_evidence_hash": release_evidence_hash(evidence),
        "evidence": evidence.model_dump(mode="json"),
    }
    _assert_public_aggregate(release_record)
    release_record["evidence_hash"] = _canonical_hash(release_record)
    report_hash = hashlib.sha256(report.encode("utf-8")).hexdigest()
    manifest: dict[str, Any] = {
        "schema_version": "phase75-release-manifest-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": assessment.verdict,
        "phase74_run_id": evidence.phase74_run_id,
        "phase74_evidence_manifest_hash": (
            evidence.phase74_evidence_manifest_hash
        ),
        "release_evidence_hash": release_evidence_hash(evidence),
        "release_evidence_record_hash": release_record["evidence_hash"],
        "assessment_hash": assessment_record["evidence_hash"],
        "report_file": report_path.name,
        "report_hash": report_hash,
        "model": "gpt-5.6-sol",
        "effort": "xhigh",
        "context_tier": "long_context",
    }
    manifest["manifest_hash"] = _canonical_hash(manifest)
    _assert_public_aggregate(manifest)

    _atomic_write_text(report_path, report)
    atomic_write_json(
        evidence_root / "release_evidence.json",
        release_record,
    )
    atomic_write_json(evidence_root / "assessment.json", assessment_record)
    atomic_write_json(evidence_root / "manifest.json", manifest)
    return {
        "status": assessment.verdict,
        "report_hash": report_hash,
        "release_evidence_hash": release_evidence_hash(evidence),
        "assessment_hash": assessment_record["evidence_hash"],
        "manifest_hash": manifest["manifest_hash"],
    }


def _validate_self_hash(
    payload: Mapping[str, Any],
    *,
    hash_field: str,
    label: str,
) -> None:
    claimed = payload.get(hash_field)
    body = {
        key: value
        for key, value in payload.items()
        if key != hash_field
    }
    if not isinstance(claimed, str) or claimed != _canonical_hash(body):
        raise ValueError(f"Phase 75 {label} hash is invalid")


def validate_release_artifacts(
    evidence_root: Path,
    *,
    report_path: Path,
    expected_live: bool = True,
) -> dict[str, Any]:
    """Independently validate persisted Phase 75 evidence and report bytes."""
    evidence_root = Path(evidence_root)
    report_path = Path(report_path)
    if evidence_root.is_symlink() or not evidence_root.is_dir():
        raise ValueError("Phase 75 evidence root is invalid")
    actual_files = {
        path.name
        for path in evidence_root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if actual_files != {
        "assessment.json",
        "manifest.json",
        "release_evidence.json",
    }:
        raise ValueError("Phase 75 evidence inventory is invalid")

    release_record = _read_json_object(
        evidence_root / "release_evidence.json"
    )
    assessment_record = _read_json_object(
        evidence_root / "assessment.json"
    )
    manifest = _read_json_object(evidence_root / "manifest.json")
    _assert_public_aggregate(release_record)
    _assert_public_aggregate(assessment_record)
    _assert_public_aggregate(manifest)
    _validate_self_hash(
        release_record,
        hash_field="evidence_hash",
        label="release evidence",
    )
    _validate_self_hash(
        assessment_record,
        hash_field="evidence_hash",
        label="assessment",
    )
    _validate_self_hash(
        manifest,
        hash_field="manifest_hash",
        label="manifest",
    )

    evidence = ReleaseEvidence.model_validate(release_record.get("evidence"))
    assessment = ReleaseAssessment.model_validate(
        assessment_record.get("assessment")
    )
    evidence_digest = release_evidence_hash(evidence)
    if (
        release_record.get("schema_version")
        != "phase75-release-evidence-record-v1"
        or release_record.get("release_evidence_hash") != evidence_digest
        or assessment_record.get("schema_version")
        != "phase75-assessment-evidence-v1"
        or assessment_record.get("release_evidence_hash") != evidence_digest
    ):
        raise ValueError("Phase 75 release evidence binding is invalid")
    if (
        assessment.release_evidence_hash != evidence_digest
        or assessment.phase74_run_id != evidence.phase74_run_id
        or assessment.evidence_manifest_hash
        != evidence.phase74_evidence_manifest_hash
    ):
        raise ValueError("Phase 75 assessment binding is invalid")

    provenance = assessment_record.get("provenance")
    raw_response = assessment_record.get("raw_response")
    expected_engine = "copilot-sdk" if expected_live else "injected-test-runner"
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("engine") != expected_engine
        or provenance.get("is_live") is not expected_live
        or provenance.get("role") != "orchestrator"
        or provenance.get("model") != "gpt-5.6-sol"
        or provenance.get("effort") != "xhigh"
        or provenance.get("context_tier") != "long_context"
        or provenance.get("attachment_hashes") != []
        or provenance.get("prompt_hash")
        != hashlib.sha256(
            _build_release_prompt(evidence).encode("utf-8")
        ).hexdigest()
        or not isinstance(raw_response, str)
        or hashlib.sha256(raw_response.encode("utf-8")).hexdigest()
        != provenance.get("output_hash")
    ):
        raise ValueError("Phase 75 assessment provenance is invalid")
    try:
        raw_assessment = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise ValueError("Phase 75 raw assessment is invalid") from error
    if raw_assessment != assessment.model_dump(mode="json"):
        raise ValueError("Phase 75 raw assessment does not match parsed output")

    try:
        report = report_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError("Phase 75 report is unavailable") from error
    report_hash = hashlib.sha256(report.encode("utf-8")).hexdigest()
    if (
        manifest.get("schema_version") != "phase75-release-manifest-v1"
        or manifest.get("status") != assessment.verdict
        or manifest.get("phase74_run_id") != evidence.phase74_run_id
        or manifest.get("phase74_evidence_manifest_hash")
        != evidence.phase74_evidence_manifest_hash
        or manifest.get("release_evidence_hash") != evidence_digest
        or manifest.get("release_evidence_record_hash")
        != release_record["evidence_hash"]
        or manifest.get("assessment_hash")
        != assessment_record["evidence_hash"]
        or manifest.get("report_file") != report_path.name
        or manifest.get("report_hash") != report_hash
        or manifest.get("model") != "gpt-5.6-sol"
        or manifest.get("effort") != "xhigh"
        or manifest.get("context_tier") != "long_context"
    ):
        raise ValueError("Phase 75 manifest or report hash is invalid")
    from crawler.eval.test_report import render_test_report

    if report != render_test_report(evidence, assessment):
        raise ValueError("Phase 75 report does not match measured evidence")
    return {
        "status": assessment.verdict,
        "documents": len(evidence.documents),
        "workers": evidence.worker_count,
        "judges": evidence.judge_count,
        "release_evidence_hash": evidence_digest,
        "report_hash": report_hash,
        "manifest_hash": manifest["manifest_hash"],
    }


def main(
    argv: list[str] | None = None,
    *,
    runtime: AgentRuntime | None = None,
    phase74_validator: Callable[..., Mapping[str, Any]] = (
        validate_committed_phase74_evidence
    ),
) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Phase 75 Copilot SDK release assessment"
    )
    parser.add_argument(
        "--phase74-evidence",
        type=Path,
        default=_REPO_ROOT / "crawler" / "eval" / "phase74_evidence",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=_REPO_ROOT,
    )
    parser.add_argument(
        "--validation-results",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPO_ROOT / "TEST_REPORT.md",
    )
    parser.add_argument(
        "--evidence-output",
        type=Path,
        default=_REPO_ROOT / "crawler" / "eval" / "phase75_evidence",
    )
    args = parser.parse_args(argv)

    try:
        validation_payload = json.loads(
            args.validation_results.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Validation results file is invalid") from error
    if not isinstance(validation_payload, list) or any(
        not isinstance(item, Mapping) for item in validation_payload
    ):
        raise ValueError("Validation results must be a JSON array of objects")

    evidence = load_release_evidence(
        args.phase74_evidence,
        validation_results=validation_payload,
        source_root=args.source_root,
        phase74_validator=phase74_validator,
    )
    run_async(
        execute_release(
            evidence,
            report_path=args.output,
            evidence_root=args.evidence_output,
            runtime=runtime,
        ),
        async_api_name="execute_release",
    )
    result = validate_release_artifacts(
        args.evidence_output,
        report_path=args.output,
        expected_live=runtime is None,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
