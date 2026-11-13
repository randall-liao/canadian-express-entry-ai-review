"""Live Phase 74 Conformance Gate Test Scaffold (D-21, D-22, REAL_AGENT_EXECUTION-01).

Verifies Worker/Judge/optimizer provenance, baseline/final coverage across all 236 cases,
sealed holdout commitments, patch audit trails, exact Opus model flags, and zero deterministic scores.

Skipped unless REQUIRE_LIVE_PHASE74_CONFORMANCE=1 environment variable is set.
Includes non-live contract tests verifying gate validation logic against mock artifact structures.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytest

from crawler.eval.agent_runtime import (
    AgentRuntimeError,
    validate_persisted_agent_provenance,
)
from crawler.eval.genuine_optimizer import (
    _OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
    derive_optimizer_candidate_id,
    optimizer_provenance_digest,
)
from crawler.eval.pipeline_judge import _JUDGE_PROVENANCE_EXTRA_FIELDS
from crawler.eval.pipeline_judge import _judge_provenance_digest
from crawler.eval.pipeline_worker import (
    _WORKER_PROVENANCE_EXTRA_FIELDS,
    _worker_provenance_digest,
)
from crawler.eval.phase74_evidence import (
    EvidenceValidationError,
    validate_committed_phase74_evidence,
)
from crawler.grounding import check_answer_grounding
from crawler.tests.phase74_provenance import build_provenance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORTS_DIR = _REPO_ROOT / "reports"
_ITERATIONS_DIR = _REPORTS_DIR / "phase74_iterations"
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_CANDIDATE_ID_RE = re.compile(r"^candidate_[a-f0-9]{12}$")
_OPTIMIZER_PROVENANCE_FIELDS = {
    "engine",
    "is_live",
    "sdk_version",
    "runtime_protocol_version",
    "role",
    "model",
    "effort",
    "context_tier",
    "session_id",
    "attachment_hashes",
    "input_findings_sha256",
    "prompt_hash",
    "output_hash",
    "candidate_content_hash",
    "terminal_event",
    "candidate_id",
    "target_file",
    "started_at",
    "completed_at",
    "duration_seconds",
    "retry_classification",
    "turn_count",
    "format_correction_count",
    "initial_prompt_hash",
    "correction_prompt_hashes",
    "assistant_response_hash_chain",
    "turn_session_ids",
    "provenance_digest",
}


def _valid_sdk_provenance(role: str) -> Dict[str, Any]:
    is_judge = role == "judge"
    extras = (
        {
            "prompt_contract_hash": "c" * 64,
            "input_manifest_hash": "d" * 64,
            "case_ids": ["case-1"],
            "pdf_hashes": ["e" * 64],
            "worker_report_hashes": ["f" * 64],
            "worker_input_manifest_hashes": ["6" * 64],
            "public_bundle_hashes": ["d" * 64],
            "worker_prompt_hashes": ["a" * 64],
            "research_hash": "1" * 64,
            "ground_truth_hash": "2" * 64,
            "model_config": {
                "model": "claude-opus-4.8",
                "effort": "xhigh",
                "context_tier": "long_context",
            },
            "artifact_output_hash": "3" * 64,
        }
        if is_judge
        else {
            "input_pdf_sha256": "e" * 64,
            "allowed_text_sha256": None,
            "bundle_hash": "d" * 64,
            "answer_hash": "c" * 64,
            "pii_manifest_hash": "6" * 64,
            "pii_manifest_count": 0,
            "pii_manifest_categories": {},
        }
    )
    return build_provenance(
        role,
        live=True,
        prompt_hash="a" * 64,
        attachment_hashes=["e" * 64],
        output_hash="b" * 64,
        extras=extras,
    )


def _valid_optimizer_provenance() -> Dict[str, Any]:
    findings_hash = "a" * 64
    prompt_hash = "b" * 64
    target_file = "skills/document-agents/passport.md"
    candidate_id = derive_optimizer_candidate_id(
        findings_hash,
        prompt_hash,
        target_file,
    )
    return build_provenance(
        "optimizer",
        live=True,
        prompt_hash=prompt_hash,
        attachment_hashes=[],
        output_hash="c" * 64,
        extras={
            "input_findings_sha256": findings_hash,
            "candidate_content_hash": "d" * 64,
            "candidate_id": candidate_id,
            "target_file": target_file,
        },
    )


def _valid_corrected_worker_provenance() -> Dict[str, Any]:
    provenance = _valid_sdk_provenance("worker")
    provenance.update(
        {
            "turn_count": 2,
            "format_correction_count": 1,
            "correction_kind": "syntax",
            "correction_prompt_hashes": ["4" * 64],
            "assistant_response_hash_chain": ["5" * 64, "b" * 64],
            "turn_session_ids": [
                provenance["session_id"],
                provenance["session_id"],
            ],
        }
    )
    provenance["provenance_digest"] = _worker_provenance_digest(provenance)
    return provenance


def _valid_corrected_judge_provenance() -> Dict[str, Any]:
    provenance = _valid_sdk_provenance("judge")
    provenance.update(
        {
            "turn_count": 2,
            "format_correction_count": 1,
            "correction_kind": "judge_structure",
            "correction_prompt_hashes": ["4" * 64],
            "assistant_response_hash_chain": ["5" * 64, "b" * 64],
            "turn_session_ids": [
                provenance["session_id"],
                provenance["session_id"],
            ],
        }
    )
    provenance["provenance_digest"] = _judge_provenance_digest(provenance)
    return provenance


def _optimizer_patch_record(
    decision: str = "accepted",
    *,
    provenance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    optimizer_provenance = provenance or _valid_optimizer_provenance()
    return {
        "iteration": 1,
        "decision": decision,
        "proposal_completed": True,
        "doc_type": "passport",
        "target_file": optimizer_provenance.get("target_file"),
        "candidate_id": optimizer_provenance.get("candidate_id"),
        "optimizer_provenance": optimizer_provenance,
    }


def _write_single_doc_gate_fixture(
    root: Path,
    *,
    worker_provenance: Dict[str, Any] | None = None,
    judge_provenance: Dict[str, Any] | None = None,
) -> Path:
    pipe_root = root / "pipelines"
    dt_iter = pipe_root / "passport" / "iterations" / "iter_00_baseline"
    worker_dir = dt_iter / "worker_reports"
    judge_dir = dt_iter / "judge_eval"
    worker_dir.mkdir(parents=True)
    judge_dir.mkdir(parents=True)

    for index in range(10):
        worker_report = {
            "question": "Review the supplied passport.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "No claims made.",
            "_provenance": worker_provenance or _valid_sdk_provenance("worker"),
        }
        (worker_dir / f"case_{index}.json").write_text(
            json.dumps(worker_report),
            encoding="utf-8",
        )

    judge_batch = {
        "doc_type": "passport",
        "case_evaluations": {},
        "findings": [],
        "patch_recommendations": [],
        "rationale": "Pass.",
        "_provenance": judge_provenance or _valid_sdk_provenance("judge"),
    }
    (judge_dir / "judge_batch.json").write_text(
        json.dumps(judge_batch),
        encoding="utf-8",
    )
    summary = {
        "baseline": {
            "doc_types": {
                "passport": {
                    "doc_type": "passport",
                    "total_cases": 10,
                    "judge_batch": judge_batch,
                    "sealed_findings": {
                        "holdout_commitment": {"count": 4, "hash": "a" * 64}
                    },
                }
            }
        }
    }
    (root / "loop_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return pipe_root


class Phase74ConformanceError(Exception):
    """Raised when live Phase 74 artifacts fail strict conformance validation."""


def test_live_gate_accepts_truthful_same_session_format_correction() -> None:
    _assert_live_sdk_provenance(
        _valid_corrected_worker_provenance(),
        artifact_label="corrected Worker",
        role="worker",
        model="gemini-3.6-flash",
        effort=None,
    )


def test_live_gate_rejects_relabelled_format_correction_as_one_turn() -> None:
    provenance = _valid_corrected_worker_provenance()
    provenance["turn_count"] = 1
    provenance["format_correction_count"] = 0
    provenance["correction_prompt_hashes"] = []
    provenance["provenance_digest"] = _worker_provenance_digest(provenance)

    with pytest.raises(Phase74ConformanceError):
        _assert_live_sdk_provenance(
            provenance,
            artifact_label="relabelled Worker",
            role="worker",
            model="gemini-3.6-flash",
            effort=None,
        )


def test_live_gate_accepts_truthful_worker_structure_correction() -> None:
    provenance = _valid_corrected_worker_provenance()
    provenance["correction_kind"] = "worker_structure"
    provenance["provenance_digest"] = _worker_provenance_digest(provenance)

    _assert_live_sdk_provenance(
        provenance,
        artifact_label="structure-corrected Worker",
        role="worker",
        model="gemini-3.6-flash",
        effort=None,
    )


def test_live_gate_accepts_truthful_worker_validation_correction() -> None:
    provenance = _valid_corrected_worker_provenance()
    provenance["correction_kind"] = "worker_validation"
    provenance["provenance_digest"] = _worker_provenance_digest(provenance)

    _assert_live_sdk_provenance(
        provenance,
        artifact_label="validation-corrected Worker",
        role="worker",
        model="gemini-3.6-flash",
        effort=None,
    )


def test_live_gate_rejects_tampered_worker_correction_kind() -> None:
    provenance = _valid_corrected_worker_provenance()
    provenance["correction_kind"] = "worker_structure"
    provenance["provenance_digest"] = _worker_provenance_digest(provenance)
    provenance["correction_kind"] = "judge_structure"

    with pytest.raises(Phase74ConformanceError):
        _assert_live_sdk_provenance(
            provenance,
            artifact_label="tampered Worker",
            role="worker",
            model="gemini-3.6-flash",
            effort=None,
        )


def test_live_gate_accepts_truthful_judge_structure_correction() -> None:
    _assert_live_sdk_provenance(
        _valid_corrected_judge_provenance(),
        artifact_label="corrected Judge",
        role="judge",
        model="claude-opus-4.8",
        effort="xhigh",
    )


def test_live_gate_rejects_tampered_judge_correction_kind() -> None:
    provenance = _valid_corrected_judge_provenance()
    provenance["correction_kind"] = "syntax"

    with pytest.raises(Phase74ConformanceError):
        _assert_live_sdk_provenance(
            provenance,
            artifact_label="tampered Judge",
            role="judge",
            model="claude-opus-4.8",
            effort="xhigh",
        )


def test_live_gate_rejects_pre_correction_provenance_schema() -> None:
    provenance = _valid_sdk_provenance("worker")
    provenance.pop("initial_prompt_hash")
    provenance["provenance_digest"] = _worker_provenance_digest(provenance)

    with pytest.raises(Phase74ConformanceError):
        _assert_live_sdk_provenance(
            provenance,
            artifact_label="old Worker",
            role="worker",
            model="gemini-3.6-flash",
            effort=None,
        )


def _assert_live_sdk_provenance(
    provenance: Any,
    *,
    artifact_label: str,
    role: str,
    model: str,
    effort: str | None,
) -> None:
    if not isinstance(provenance, dict):
        raise Phase74ConformanceError(
            f"invalid {artifact_label} SDK provenance: {provenance!r}"
        )
    extra_fields = (
        _JUDGE_PROVENANCE_EXTRA_FIELDS
        if role == "judge"
        else _WORKER_PROVENANCE_EXTRA_FIELDS
    )
    if role == "judge":
        required_hash_fields = (
            "prompt_contract_hash",
            "input_manifest_hash",
            "research_hash",
            "ground_truth_hash",
            "artifact_output_hash",
        )
        optional_hash_fields = ()
        required_hash_list_fields = (
            "pdf_hashes",
            "worker_report_hashes",
            "worker_input_manifest_hashes",
            "public_bundle_hashes",
            "worker_prompt_hashes",
        )
    else:
        required_hash_fields = (
            "input_pdf_sha256",
            "bundle_hash",
            "answer_hash",
            "pii_manifest_hash",
        )
        optional_hash_fields = ("allowed_text_sha256",)
        required_hash_list_fields = ()
    try:
        validate_persisted_agent_provenance(
            provenance,
            expected_engine="copilot-sdk",
            expected_is_live=True,
            role=role,
            model=model,
            effort=effort,
            context_tier="long_context",
            prompt_hash=provenance.get("prompt_hash"),
            attachment_hashes=provenance.get("attachment_hashes"),
            output_hash=provenance.get("output_hash"),
            extra_digest_fields=extra_fields,
            required_hash_fields=required_hash_fields,
            optional_hash_fields=optional_hash_fields,
            required_hash_list_fields=required_hash_list_fields,
        )
        if role == "worker" and provenance["attachment_hashes"] != [
            provenance["input_pdf_sha256"]
        ]:
            raise AgentRuntimeError(
                "Worker input PDF hash does not match attachment hash"
            )
        if role == "judge" and provenance["attachment_hashes"] != provenance[
            "pdf_hashes"
        ]:
            raise AgentRuntimeError(
                "Judge PDF hashes do not match attachment hashes"
            )
    except AgentRuntimeError as exc:
        raise Phase74ConformanceError(
            f"invalid {artifact_label} SDK provenance: {exc}"
        ) from exc


def _assert_live_optimizer_patch_record(
    record: Any,
    *,
    collection_name: str,
    record_index: int,
) -> None:
    label = f"{collection_name}[{record_index}]"
    if not isinstance(record, dict):
        raise Phase74ConformanceError(
            f"invalid {collection_name} optimizer SDK provenance: "
            f"{label} is not an object"
        )

    expected_decision = {
        "accepted_patches": "accepted",
        "rejected_patches": "rejected",
        "blocked_patches": "blocked",
    }.get(collection_name)
    if record.get("decision") != expected_decision:
        raise Phase74ConformanceError(
            f"invalid {collection_name} patch decision at {label}: "
            f"expected {expected_decision!r}, got {record.get('decision')!r}"
        )

    proposal_completed = record.get("proposal_completed")
    if not isinstance(proposal_completed, bool):
        raise Phase74ConformanceError(
            f"invalid {collection_name} optimizer SDK provenance: "
            f"{label} lacks an explicit proposal_completed boolean"
        )
    if expected_decision != "blocked" and not proposal_completed:
        raise Phase74ConformanceError(
            f"invalid {collection_name} optimizer SDK provenance: "
            f"{label} cannot record {expected_decision} without a proposal"
        )
    if not proposal_completed:
        masquerading_fields = {
            "candidate_id",
            "target_file",
            "optimizer_provenance",
            "provenance_hash",
        }.intersection(record)
        if masquerading_fields:
            raise Phase74ConformanceError(
                "blocked patch without a completed proposal contains optimizer "
                f"success evidence: {sorted(masquerading_fields)}"
            )
        return

    provenance = record.get("optimizer_provenance")
    if not isinstance(provenance, dict):
        raise Phase74ConformanceError(
            f"invalid {collection_name} optimizer SDK provenance: "
            f"{label} has missing or hash-only optimizer evidence"
        )

    try:
        validate_persisted_agent_provenance(
            provenance,
            expected_engine="copilot-sdk",
            expected_is_live=True,
            role="optimizer",
            model="gemini-3.6-flash",
            effort=None,
            context_tier="long_context",
            prompt_hash=provenance.get("prompt_hash"),
            attachment_hashes=[],
            output_hash=provenance.get("output_hash"),
            extra_digest_fields=_OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
            required_hash_fields=(
                "input_findings_sha256",
                "candidate_content_hash",
            ),
        )
    except AgentRuntimeError as exc:
        runtime_error = str(exc)
    else:
        runtime_error = None

    expected = {
        "engine": "copilot-sdk",
        "is_live": True,
        "role": "optimizer",
        "model": "gemini-3.6-flash",
        "effort": None,
        "context_tier": "long_context",
        "attachment_hashes": [],
        "terminal_event": "assistant.message",
        "retry_classification": None,
    }
    mismatches = {
        field: {"expected": expected_value, "actual": provenance.get(field)}
        for field, expected_value in expected.items()
        if provenance.get(field) != expected_value
    }
    if runtime_error is not None:
        mismatches["runtime_provenance"] = runtime_error
    actual_fields = set(provenance)
    expected_fields = set(_OPTIMIZER_PROVENANCE_FIELDS)
    if provenance.get("format_correction_count") == 1:
        expected_fields.add("correction_kind")
    if actual_fields != expected_fields:
        mismatches["publishable_fields"] = {
            "expected": sorted(expected_fields),
            "actual": sorted(actual_fields),
        }
    for field in ("sdk_version", "runtime_protocol_version"):
        value = provenance.get(field)
        if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
            mismatches[field] = {
                "expected": "non-empty version",
                "actual": value,
            }
    session_id = provenance.get("session_id")
    if (
        not isinstance(session_id, str)
        or not _SESSION_ID_RE.fullmatch(session_id)
        or session_id == "unknown"
    ):
        mismatches["session_id"] = {
            "expected": "non-empty live SDK session ID",
            "actual": session_id,
        }
    for field in (
        "input_findings_sha256",
        "prompt_hash",
        "output_hash",
        "candidate_content_hash",
        "provenance_digest",
    ):
        value = provenance.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            mismatches[field] = {
                "expected": "SHA-256 digest",
                "actual": value,
            }

    candidate_id = provenance.get("candidate_id")
    target_file = provenance.get("target_file")
    expected_candidate_id = (
        derive_optimizer_candidate_id(
            provenance.get("input_findings_sha256"),
            provenance.get("prompt_hash"),
            target_file,
        )
        if (
            isinstance(provenance.get("input_findings_sha256"), str)
            and isinstance(provenance.get("prompt_hash"), str)
            and isinstance(target_file, str)
        )
        else None
    )
    if (
        not isinstance(candidate_id, str)
        or not _CANDIDATE_ID_RE.fullmatch(candidate_id)
        or record.get("candidate_id") != candidate_id
        or record.get("target_file") != target_file
        or candidate_id != expected_candidate_id
    ):
        mismatches["candidate_id"] = {
            "expected": "matching candidate_<12 lowercase hex> identity",
            "actual": {
                "record": record.get("candidate_id"),
                "provenance": candidate_id,
                "recomputed": expected_candidate_id,
            },
        }

    parsed_times: Dict[str, datetime] = {}
    for field in ("started_at", "completed_at"):
        value = provenance.get(field)
        try:
            if not isinstance(value, str):
                raise ValueError
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
            parsed_times[field] = parsed
        except ValueError:
            mismatches[field] = {
                "expected": "ISO-8601 timestamp with UTC offset",
                "actual": value,
            }
    if (
        len(parsed_times) == 2
        and parsed_times["completed_at"] < parsed_times["started_at"]
    ):
        mismatches["completed_at"] = {
            "expected": "timestamp not before started_at",
            "actual": provenance.get("completed_at"),
        }

    duration = provenance.get("duration_seconds")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not math.isfinite(float(duration))
        or duration < 0
    ):
        mismatches["duration_seconds"] = {
            "expected": "finite nonnegative number",
            "actual": duration,
        }

    expected_digest = optimizer_provenance_digest(provenance)
    if provenance.get("provenance_digest") != expected_digest:
        mismatches["provenance_digest"] = {
            "expected": expected_digest,
            "actual": provenance.get("provenance_digest"),
        }

    serialized_record = json.dumps(record, sort_keys=True)
    if any(
        private_path_prefix in serialized_record
        for private_path_prefix in ("/home/", "/Users/", "\\Users\\")
    ):
        mismatches["private_path"] = {
            "expected": "no absolute private paths",
            "actual": "present",
        }

    if mismatches:
        raise Phase74ConformanceError(
            f"invalid {collection_name} optimizer SDK provenance: {mismatches}"
        )


@pytest.mark.parametrize("decision", ["accepted", "rejected", "blocked"])
def test_live_sdk_optimizer_proposal_record_is_accepted(decision: str) -> None:
    _assert_live_optimizer_patch_record(
        _optimizer_patch_record(decision),
        collection_name=f"{decision}_patches",
        record_index=0,
    )


@pytest.mark.parametrize(
    "optimizer_provenance",
    [
        None,
        {"provenance_hash": "a" * 64},
        {
            **_valid_optimizer_provenance(),
            "engine": "copilot-cli",
        },
        {
            **_valid_optimizer_provenance(),
            "engine": "injected-test-runner",
            "is_live": False,
        },
    ],
    ids=["missing", "hash-only", "legacy-cli", "injected"],
)
def test_optimizer_proposal_record_rejects_non_live_sdk_evidence(
    optimizer_provenance: Dict[str, Any] | None,
) -> None:
    record = _optimizer_patch_record()
    if optimizer_provenance is None:
        record.pop("optimizer_provenance")
    else:
        record["optimizer_provenance"] = optimizer_provenance

    with pytest.raises(
        Phase74ConformanceError,
        match="invalid accepted_patches optimizer SDK provenance",
    ):
        _assert_live_optimizer_patch_record(
            record,
            collection_name="accepted_patches",
            record_index=0,
        )


def _redigest_optimizer_provenance(provenance: Dict[str, Any]) -> None:
    provenance["provenance_digest"] = optimizer_provenance_digest(provenance)


@pytest.mark.parametrize(
    "missing_field",
    sorted(_OPTIMIZER_PROVENANCE_FIELDS),
)
def test_optimizer_proposal_record_rejects_each_missing_required_field(
    missing_field: str,
) -> None:
    provenance = _valid_optimizer_provenance()
    provenance.pop(missing_field)
    if missing_field != "provenance_digest":
        _redigest_optimizer_provenance(provenance)
    record = _optimizer_patch_record(provenance=provenance)

    with pytest.raises(
        Phase74ConformanceError,
        match="invalid accepted_patches optimizer SDK provenance",
    ):
        _assert_live_optimizer_patch_record(
            record,
            collection_name="accepted_patches",
            record_index=0,
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("sdk_version", None),
        ("runtime_protocol_version", ""),
        ("session_id", "unknown"),
        ("input_findings_sha256", "not-a-hash"),
        ("prompt_hash", "B" * 64),
        ("output_hash", "c" * 63),
        ("candidate_content_hash", None),
        ("started_at", "not-a-timestamp"),
        ("completed_at", "2026-07-25T11:59:59+00:00"),
        ("duration_seconds", -0.1),
        ("duration_seconds", float("inf")),
        ("duration_seconds", True),
        ("retry_classification", "transient"),
        ("candidate_id", "candidate_not-a-digest"),
    ],
)
def test_optimizer_proposal_record_rejects_malformed_provenance(
    field: str,
    invalid_value: Any,
) -> None:
    provenance = _valid_optimizer_provenance()
    provenance[field] = invalid_value
    _redigest_optimizer_provenance(provenance)
    record = _optimizer_patch_record(provenance=provenance)

    with pytest.raises(
        Phase74ConformanceError,
        match="invalid accepted_patches optimizer SDK provenance",
    ):
        _assert_live_optimizer_patch_record(
            record,
            collection_name="accepted_patches",
            record_index=0,
        )


def test_optimizer_proposal_record_rejects_candidate_identity_mismatch() -> None:
    record = _optimizer_patch_record()
    record["candidate_id"] = "candidate_fedcba987654"

    with pytest.raises(
        Phase74ConformanceError,
        match="invalid accepted_patches optimizer SDK provenance",
    ):
        _assert_live_optimizer_patch_record(
            record,
            collection_name="accepted_patches",
            record_index=0,
        )


def test_optimizer_proposal_record_rejects_coordinated_forged_identity() -> None:
    record = _optimizer_patch_record()
    forged_id = "candidate_fedcba987654"
    record["candidate_id"] = forged_id
    record["optimizer_provenance"]["candidate_id"] = forged_id
    _redigest_optimizer_provenance(record["optimizer_provenance"])

    with pytest.raises(
        Phase74ConformanceError,
        match="invalid accepted_patches optimizer SDK provenance",
    ):
        _assert_live_optimizer_patch_record(
            record,
            collection_name="accepted_patches",
            record_index=0,
        )


def test_optimizer_proposal_record_rejects_relabelled_injected_runtime() -> None:
    provenance = _valid_optimizer_provenance()
    provenance.update(
        {
            "engine": "injected-test-runner",
            "is_live": False,
            "sdk_version": "injected-test-runner",
            "runtime_protocol_version": "injected-test-protocol",
            "session_id": "injected-optimizer-session-123",
        }
    )
    _redigest_optimizer_provenance(provenance)
    provenance.update({"engine": "copilot-sdk", "is_live": True})
    _redigest_optimizer_provenance(provenance)

    with pytest.raises(
        Phase74ConformanceError,
        match="invalid accepted_patches optimizer SDK provenance",
    ):
        _assert_live_optimizer_patch_record(
            _optimizer_patch_record(provenance=provenance),
            collection_name="accepted_patches",
            record_index=0,
        )


def test_blocked_without_completed_proposal_has_no_optimizer_success() -> None:
    _assert_live_optimizer_patch_record(
        {
            "iteration": 1,
            "decision": "blocked",
            "proposal_completed": False,
            "doc_type": "passport",
            "reasons": ["Optimizer infrastructure unavailable"],
        },
        collection_name="blocked_patches",
        record_index=0,
    )

    masquerading_record = {
        "iteration": 1,
        "decision": "blocked",
        "proposal_completed": False,
        "doc_type": "passport",
        "optimizer_provenance": _valid_optimizer_provenance(),
        "reasons": ["Optimizer infrastructure unavailable"],
    }
    with pytest.raises(
        Phase74ConformanceError,
        match="blocked patch without a completed proposal",
    ):
        _assert_live_optimizer_patch_record(
            masquerading_record,
            collection_name="blocked_patches",
            record_index=0,
        )


def assert_phase74_conformance(
    iterations_dir: Path | str,
    pipelines_dir: Path | str | None = None,
    require_live_provenance: bool = True,
    require_final_pass: bool = False,
) -> Dict[str, Any]:
    """Validate Phase 74 execution artifacts for strict conformance (D-21, D-22).

    Checks:
    - Live Copilot SDK provenance with exact role/model/effort/context and terminal success.
    - 236 Worker reports exist, pass local AnswerObject grounding, and have unique provenance hashes.
    - 23 batched Opus 4.8 xhigh long-context Judge sessions cover 100% of cases.
    - Sealed holdout evidence commitment and patch audit trails (accepted_patches.json, rejected_patches.json).
    - Rejects injected, cached-without-hash, or deterministic fallback artifacts.
    """
    # Final completion is proved exclusively by committed PII-safe evidence.
    # Legacy arguments remain only for call compatibility and are deliberately
    # ignored; no baseline/raw/ignored artifact can satisfy this gate.
    del iterations_dir, pipelines_dir, require_live_provenance, require_final_pass
    try:
        return validate_committed_phase74_evidence(
            _REPO_ROOT / "crawler" / "eval" / "phase74_evidence",
            source_root=_REPO_ROOT,
        )
    except (EvidenceValidationError, FileNotFoundError, OSError, ValueError) as exc:
        raise Phase74ConformanceError(
            f"Committed Phase 74 evidence is invalid: {exc}"
        ) from exc

    # Disabled legacy baseline/raw gate retained temporarily for historical
    # unit fixture readability. It is unreachable by construction.
    iter_root = Path(iterations_dir)
    pipe_root = Path(pipelines_dir or _PIPELINES_DIR)

    if not iter_root.exists():
        raise Phase74ConformanceError(f"Iterations directory does not exist: {iter_root}")

    summary_file = iter_root / "loop_summary.json"
    if not summary_file.is_file():
        raise Phase74ConformanceError(f"Loop summary missing: {summary_file}")

    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise Phase74ConformanceError("Failed to parse loop_summary.json") from exc

    # 1. Verify Baseline Pass Coverage (236 Worker cases, 23 document types)
    baseline = summary.get("baseline", {})
    doc_types = baseline.get("doc_types", {})

    total_worker_cases = 0

    for dt, dt_data in doc_types.items():
        # Inspect per-pipeline iteration directory artifacts per D-20
        p_iter_dir = pipe_root / dt / "iterations" / "iter_00_baseline"
        w_out_dir = p_iter_dir / "worker_reports"
        j_out_dir = p_iter_dir / "judge_eval"

        if not w_out_dir.is_dir():
            raise Phase74ConformanceError(f"Missing per-pipeline worker reports directory for {dt} at {w_out_dir}")
        if not j_out_dir.is_dir() or not (j_out_dir / "judge_batch.json").is_file():
            raise Phase74ConformanceError(f"Missing per-pipeline judge evaluation report for {dt} at {j_out_dir}")

        w_files = list(w_out_dir.glob("*.json"))
        expected_cases = dt_data.get("total_cases", 0)
        if len(w_files) < expected_cases or expected_cases not in (10, 12):
            raise Phase74ConformanceError(
                f"Per-pipeline worker reports count for {dt} ({len(w_files)}) does not match expected {expected_cases}"
            )

        judge_batch = dt_data.get("judge_batch", {})
        if require_live_provenance:
            _assert_live_sdk_provenance(
                judge_batch.get("_provenance"),
                artifact_label="Judge",
                role="judge",
                model="claude-opus-4.8",
                effort="xhigh",
            )
            judge_file = j_out_dir / "judge_batch.json"
            try:
                persisted_judge_batch = json.loads(
                    judge_file.read_text(encoding="utf-8")
                )
            except Exception as exc:
                raise Phase74ConformanceError(
                    f"Failed to parse persisted Judge artifact for {dt}"
                ) from exc
            _assert_live_sdk_provenance(
                persisted_judge_batch.get("_provenance"),
                artifact_label="Judge",
                role="judge",
                model="claude-opus-4.8",
                effort="xhigh",
            )
            if persisted_judge_batch != judge_batch:
                raise Phase74ConformanceError(
                    f"Persisted Judge artifact for {dt} does not match loop summary"
                )

            for worker_file in w_files:
                try:
                    worker_report = json.loads(worker_file.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise Phase74ConformanceError(
                        f"Failed to parse Worker artifact for {dt}: {worker_file.name}"
                    ) from exc
                _assert_live_sdk_provenance(
                    worker_report.get("_provenance"),
                    artifact_label="Worker",
                    role="worker",
                    model="gemini-3.6-flash",
                    effort=None,
                )

        # Sealed Holdout Assertion
        sealed = dt_data.get("sealed_findings", {})
        if "holdout_commitment" not in sealed:
            raise Phase74ConformanceError(f"Doc type {dt} baseline lacks holdout_commitment structure")

        commitment = sealed["holdout_commitment"]
        if commitment.get("count") != 4:
            raise Phase74ConformanceError(f"Doc type {dt} holdout count is {commitment.get('count')}, expected 4")

        # Worker Cases Count
        total_worker_cases += dt_data.get("total_cases", 0)

    if len(doc_types) < 23:
        raise Phase74ConformanceError(f"Baseline doc_types count ({len(doc_types)}) is less than required 23")

    if total_worker_cases < 236:
        raise Phase74ConformanceError(f"Total baseline worker cases ({total_worker_cases}) is less than required 236")

    # 2. Verify Final Pass & Patch Audit Trails (if required)
    opt = summary.get("optimization", {})
    accepted_patches = opt.get("accepted_patches", [])
    rejected_patches = opt.get("rejected_patches", [])
    blocked_patches = opt.get("blocked_patches", [])
    patch_collections = {
        "accepted_patches": accepted_patches,
        "rejected_patches": rejected_patches,
        "blocked_patches": blocked_patches,
    }
    for collection_name, records in patch_collections.items():
        if not isinstance(records, list):
            raise Phase74ConformanceError(
                f"{collection_name} must be a list"
            )
        if require_live_provenance:
            for record_index, record in enumerate(records):
                _assert_live_optimizer_patch_record(
                    record,
                    collection_name=collection_name,
                    record_index=record_index,
                )

    if require_final_pass:
        final_pass = summary.get("final_pass", {})
        if not final_pass or final_pass.get("total_cases", 0) < 236:
            raise Phase74ConformanceError("Final pass missing or incomplete (<236 cases)")

    return {
        "status": "CONFORMANT",
        "total_doc_types": len(doc_types),
        "total_worker_cases": total_worker_cases,
        "accepted_patches_count": len(accepted_patches),
        "rejected_patches_count": len(rejected_patches),
        "blocked_patches_count": len(blocked_patches),
    }


# --- Non-Live Unit / Contract Tests for Gate Logic ---


def test_conformance_gate_ignores_missing_legacy_iterations_dir() -> None:
    """Fresh committed evidence is authoritative over legacy raw paths."""
    report = assert_phase74_conformance(
        _REPO_ROOT / ".nonexistent_phase74_path_12345"
    )

    assert report["status"] == "CONFORMANT"


@pytest.mark.parametrize(
    ("role", "field", "invalid_value"),
    [
        ("judge", "engine", "copilot-cli"),
        ("judge", "engine", "injected-test-runner"),
        ("judge", "is_live", False),
        ("judge", "sdk_version", ""),
        ("judge", "role", "worker"),
        ("judge", "model", "gemini-3.6-flash"),
        ("judge", "effort", None),
        ("judge", "context_tier", "default"),
        ("judge", "terminal_event", "session.error"),
        ("worker", "engine", "copilot-cli"),
        ("worker", "engine", "injected-test-runner"),
        ("worker", "is_live", False),
        ("worker", "sdk_version", ""),
        ("worker", "role", "judge"),
        ("worker", "model", "claude-opus-4.8"),
        ("worker", "effort", "xhigh"),
        ("worker", "session_id", "injected-runner"),
        ("worker", "terminal_event", "session.error"),
    ],
)
def test_conformance_gate_requires_exact_live_sdk_role_provenance(
    role: str,
    field: str,
    invalid_value: Any,
) -> None:
    target = _valid_sdk_provenance(role)
    target[field] = invalid_value

    with pytest.raises(
        Phase74ConformanceError,
        match=rf"invalid {role.title()} SDK provenance",
    ):
        _assert_live_sdk_provenance(
            target,
            artifact_label=role.title(),
            role=role,
            model=(
                "claude-opus-4.8"
                if role == "judge"
                else "gemini-3.6-flash"
            ),
            effort="xhigh" if role == "judge" else None,
        )


def test_conformance_gate_rejects_non_live_or_wrong_model() -> None:
    provenance = _valid_sdk_provenance("judge")
    provenance["is_live"] = False
    provenance["model"] = "wrong-model"
    with pytest.raises(Phase74ConformanceError):
        _assert_live_sdk_provenance(
            provenance,
            artifact_label="Judge",
            role="judge",
            model="claude-opus-4.8",
            effort="xhigh",
        )


def test_conformance_gate_ignores_seeded_raw_loop_summary(
    tmp_path: Path,
) -> None:
    """A seeded raw loop summary cannot satisfy or alter the committed gate."""
    (tmp_path / "loop_summary.json").write_text(
        json.dumps({"baseline": {"doc_types": {}}}),
        encoding="utf-8",
    )
    report = assert_phase74_conformance(
        tmp_path,
        pipelines_dir=tmp_path / "missing-pipelines",
    )

    assert report["status"] == "CONFORMANT"


# --- Live Conformance Gate (Enforced via REQUIRE_LIVE_PHASE74_CONFORMANCE=1) ---


def test_live_phase74_conformance() -> None:
    """Live conformance gate verifying end-to-end execution evidence across all 236 cases.

    Skipped unless REQUIRE_LIVE_PHASE74_CONFORMANCE=1.
    """
    if os.getenv("REQUIRE_LIVE_PHASE74_CONFORMANCE") != "1":
        pytest.skip("REQUIRE_LIVE_PHASE74_CONFORMANCE=1 is not set")

    report = assert_phase74_conformance(
        iterations_dir=_ITERATIONS_DIR,
        pipelines_dir=_PIPELINES_DIR,
        require_live_provenance=True,
        require_final_pass=os.getenv("REQUIRE_FINAL_PASS") == "1",
    )

    assert report["status"] == "CONFORMANT"
    assert report["workers"] == 236
    assert report["document_types"] == 23
    assert report["judges"] == 23
    assert report["shared_evaluations"] == 23
