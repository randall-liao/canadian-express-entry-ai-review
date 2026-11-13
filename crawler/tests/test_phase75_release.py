from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from crawler.eval import release_orchestrator
from crawler.eval.agent_runtime import (
    AgentProvenance,
    AgentRequest,
    AgentResult,
)
from crawler.eval.release_orchestrator import (
    ReleaseAssessment,
    ReleaseEvidence,
    _validated_patch_records,
    _weighted_baseline,
    build_release_evidence,
    execute_release,
    load_release_evidence,
    main,
    release_evidence_hash,
    run_release_assessment,
    validate_release_artifacts,
)
from crawler.eval.test_report import render_test_report
from crawler.synthetic.schemas import ExpressEntryDocType


SCORE = {
    "grounding_accuracy": 0.9,
    "citation_exactness": 1.0,
    "defect_recall": 0.5,
    "pii_containment": 1.0,
    "blind_input_compliance": 1.0,
    "overall_score": 0.88,
}
DELTA = {
    "grounding_accuracy": 0.1,
    "citation_exactness": 0.0,
    "defect_recall": 0.2,
    "pii_containment": 0.0,
    "blind_input_compliance": 0.0,
    "overall_score": 0.06,
}


def _evidence_payload() -> dict[str, Any]:
    documents = []
    doc_types = sorted(doc_type.value for doc_type in ExpressEntryDocType)
    for index, doc_type in enumerate(doc_types):
        case_count = 12 if index < 3 else 10
        documents.append(
            {
                "doc_type": doc_type,
                "status": "completed",
                "case_count": case_count,
                "worker_count": case_count,
                "judge_count": 1,
                "shared_evaluation_count": 1,
                "baseline_metrics": SCORE,
                "final_metrics": {
                    **SCORE,
                    "grounding_accuracy": 1.0,
                    "defect_recall": 0.7,
                    "overall_score": 0.94,
                },
                "metric_deltas": DELTA,
                "accepted_patch_count": 1 if index == 0 else 0,
                "rejected_patch_count": 0 if index == 0 else 1,
                "blockers": [],
            }
        )
    return {
        "schema_version": "phase75-release-evidence-v1",
        "phase72_research_documents": 23,
        "phase73_logical_cases": 118,
        "phase73_pdf_count": 236,
        "phase74_run_id": "sdk-20260727T030015Z-02472e3e132e",
        "phase74_final_revision": "a" * 40,
        "phase74_final_manifest_hash": "b" * 64,
        "phase74_evidence_manifest_hash": "c" * 64,
        "sdk_version": "1.0.8",
        "runtime_version": "1.0.73",
        "protocol_version": "3",
        "worker_model": "gemini-3.6-flash",
        "optimizer_model": "gemini-3.6-flash",
        "judge_model": "claude-opus-4.8",
        "judge_effort": "xhigh",
        "orchestrator_model": "gpt-5.6-sol",
        "context_tier": "long_context",
        "worker_count": 236,
        "judge_count": 23,
        "optimizer_count": 23,
        "shared_evaluation_count": 23,
        "accepted_patch_count": 1,
        "rejected_patch_count": 22,
        "accepted_patches": [
            {
                "sequence": 1,
                "doc_type": documents[0]["doc_type"],
                "commit": "d" * 40,
                "target_file": "skills/document-agents/adoption-certificate.md",
                "training_overall_delta": 0.05,
                "holdout_overall_delta": 0.01,
            }
        ],
        "peak_concurrency": 5,
        "imported_model_artifact_count": 0,
        "cleanup_survivor_count": 0,
        "cleanup_error_count": 0,
        "documents": documents,
        "validation_results": [
            {
                "name": "phase74-live-gate",
                "command": (
                    "REQUIRE_LIVE_PHASE74_CONFORMANCE=1 "
                    ".venv/bin/python -m pytest "
                    "crawler/tests/test_live_phase74_conformance_gate.py -q"
                ),
                "status": "passed",
                "duration_seconds": 2.1,
                "detail": "83 passed",
            }
        ],
        "blockers": [],
    }


def _assessment_payload(evidence: ReleaseEvidence) -> dict[str, Any]:
    return {
        "schema_version": "phase75-release-assessment-v1",
        "verdict": "ready",
        "phase74_run_id": evidence.phase74_run_id,
        "evidence_manifest_hash": evidence.phase74_evidence_manifest_hash,
        "release_evidence_hash": release_evidence_hash(evidence),
        "summary": "Measured evidence satisfies the release contract.",
        "strengths": ["All document pipelines completed."],
        "blockers": [],
        "recommendations": ["Preserve the committed evidence manifest."],
    }


class FakeRuntime:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[AgentRequest] = []

    async def run(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        content = json.dumps(self.response, sort_keys=True)
        return AgentResult(
            content=content,
            provenance=AgentProvenance(
                engine="injected-test-runner",
                sdk_version="1.0.8",
                runtime_protocol_version="3",
                role=request.role,
                model=request.model,
                effort=request.reasoning_effort,
                context_tier=request.context_tier,
                session_id="phase75-test-session",
                prompt_hash=hashlib.sha256(
                    request.prompt.encode("utf-8")
                ).hexdigest(),
                attachment_hashes=[],
                output_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                started_at="2026-07-27T00:00:00Z",
                completed_at="2026-07-27T00:00:01Z",
                duration_seconds=1.0,
                terminal_event="assistant.message",
                is_live=False,
            ),
        )


@pytest.mark.parametrize(
    "private_fragment",
    [
        {"applicant_name": "Example Person"},
        {"nested": {"birth_date": "1990-01-01"}},
        {"nested": [{"passport_number": "X1234567"}]},
        {"candidate_vault": "private"},
        {"source": "/home/example/candidates/private"},
    ],
)
def test_release_evidence_rejects_private_fields(
    private_fragment: dict[str, Any],
) -> None:
    payload = _evidence_payload()
    payload.update(private_fragment)

    with pytest.raises(ValueError, match="private"):
        build_release_evidence(payload)


@pytest.mark.parametrize(
    "private_value",
    [
        "path=/home/example/candidates/private",
        "root:/Users/example/private",
        "file:///home/example/private",
        "path=C:/Users/example/private",
        "Jane Synthetic",
        "John Doe",
    ],
)
def test_release_evidence_rejects_private_value_variants(
    private_value: str,
) -> None:
    payload = _evidence_payload()
    payload["validation_results"][0]["detail"] = private_value

    with pytest.raises(ValueError, match="private"):
        build_release_evidence(payload)


def test_release_evidence_requires_exact_23_document_coverage() -> None:
    payload = _evidence_payload()
    payload["documents"].pop()

    with pytest.raises(ValueError, match="23"):
        build_release_evidence(payload)


def test_release_evidence_requires_canonical_document_inventory() -> None:
    payload = _evidence_payload()
    payload["documents"][-1]["doc_type"] = "zz_fake_document"

    with pytest.raises(ValueError, match="canonical"):
        build_release_evidence(payload)


def test_release_evidence_hash_accepts_equivalent_module_identity() -> None:
    evidence = build_release_evidence(_evidence_payload())

    class EquivalentEvidence:
        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return evidence.model_dump(mode="json")

    assert release_evidence_hash(EquivalentEvidence()) == (
        release_evidence_hash(evidence)
    )


@pytest.mark.asyncio
async def test_release_assessment_accepts_equivalent_module_identity() -> None:
    evidence = build_release_evidence(_evidence_payload())

    class EquivalentEvidence:
        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return evidence.model_dump(mode="json")

    assessment, _ = await run_release_assessment(
        EquivalentEvidence(),
        runtime=FakeRuntime(_assessment_payload(evidence)),
    )

    assert assessment.verdict == "ready"


def test_weighted_baseline_rejects_zero_case_count() -> None:
    with pytest.raises(ValueError, match="positive"):
        _weighted_baseline(
            {
                "training_count": 0,
                "holdout_count": 0,
                "baseline_train": SCORE,
                "baseline_holdout": SCORE,
            },
            case_count=0,
        )


def test_patch_records_reject_non_mapping_items() -> None:
    with pytest.raises(ValueError, match="patch records"):
        _validated_patch_records(
            {"records": [1]},
            {"records": []},
        )


def test_load_release_evidence_uses_validated_committed_phase74(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "phase74_evidence"
    documents_root = evidence_root / "documents"
    documents_root.mkdir(parents=True)
    payload = _evidence_payload()
    manifest = {
        "schema_version": "phase74-committed-evidence-v1",
        "run_id": payload["phase74_run_id"],
        "final_revision": payload["phase74_final_revision"],
        "final_manifest_hash": payload["phase74_final_manifest_hash"],
        "manifest_hash": payload["phase74_evidence_manifest_hash"],
        "sdk_version": payload["sdk_version"],
        "runtime_version": payload["runtime_version"],
        "protocol_version": payload["protocol_version"],
        "worker_model": payload["worker_model"],
        "judge_model": payload["judge_model"],
        "judge_effort": payload["judge_effort"],
        "context_tier": payload["context_tier"],
        "worker_count": 236,
        "judge_count": 23,
        "shared_evaluation_count": 23,
        "accepted_patch_count": 1,
        "optimizer_count": 23,
        "imported_model_artifact_count": 0,
    }
    (evidence_root / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    for document in payload["documents"]:
        doc_root = documents_root / document["doc_type"]
        doc_root.mkdir()
        (doc_root / "judge.json").write_text(
            json.dumps(
                {
                    "doc_type": document["doc_type"],
                    "case_count": document["case_count"],
                    "sanitized_evaluation_payload": {
                        "aggregate_metrics": document["final_metrics"]
                    },
                }
            ),
            encoding="utf-8",
        )
        (doc_root / "shared_evaluation.json").write_text(
            json.dumps(
                {
                    "doc_type": document["doc_type"],
                    "training_count": document["case_count"] - 4,
                    "holdout_count": 4,
                    "baseline_train": document["baseline_metrics"],
                    "baseline_holdout": document["baseline_metrics"],
                    "decision": (
                        "accepted"
                        if document["accepted_patch_count"]
                        else "rejected"
                    ),
                    "status": "completed",
                }
            ),
            encoding="utf-8",
        )
    (evidence_root / "accepted_patches.json").write_text(
        json.dumps(
            {
                "schema_version": "accepted-v1",
                "records": [
                    {
                        "sequence": 1,
                        "doc_type": payload["documents"][0]["doc_type"],
                        "commit": "d" * 40,
                        "target_file": (
                            "skills/document-agents/"
                            "adoption-certificate.md"
                        ),
                        "training_deltas": {"overall_score": 0.05},
                        "holdout_deltas": {"overall_score": 0.01},
                    }
                ],
                "evidence_hash": "d" * 64,
            }
        ),
        encoding="utf-8",
    )
    (evidence_root / "rejected_patches.json").write_text(
        json.dumps(
            {
                "schema_version": "rejected-v1",
                "records": [
                    {"doc_type": document["doc_type"]}
                    for document in payload["documents"][1:]
                ],
                "evidence_hash": "e" * 64,
            }
        ),
        encoding="utf-8",
    )
    (evidence_root / "concurrency.json").write_text(
        json.dumps({"declared_peak": 5, "slot_limit": 5}),
        encoding="utf-8",
    )
    (evidence_root / "cleanup.json").write_text(
        json.dumps(
            {
                "supervisor_status": "completed",
                "lease_status": "released",
                "survivor_count": 0,
                "error_count": 0,
            }
        ),
        encoding="utf-8",
    )
    validation_results = payload["validation_results"]
    calls: list[Any] = []

    def validator(root: Any, **_: Any) -> dict[str, Any]:
        calls.append(root)
        return {
            "status": "CONFORMANT",
            "document_types": 23,
            "workers": 236,
            "judges": 23,
            "shared_evaluations": 23,
            "accepted_patches": 1,
            "rejected_patches": 22,
            "peak_concurrency": 5,
            "final_revision": payload["phase74_final_revision"],
            "final_manifest_hash": payload[
                "phase74_final_manifest_hash"
            ],
        }

    evidence = load_release_evidence(
        evidence_root,
        validation_results=validation_results,
        phase74_validator=validator,
    )

    assert calls == [evidence_root]
    assert evidence.worker_count == 236
    assert evidence.documents[0].final_metrics.overall_score == 0.94
    assert evidence.documents[0].accepted_patch_count == 1
    assert evidence.documents[1].rejected_patch_count == 1


@pytest.mark.asyncio
async def test_release_orchestrator_uses_required_model() -> None:
    evidence = build_release_evidence(_evidence_payload())
    runtime = FakeRuntime(_assessment_payload(evidence))

    assessment, provenance = await run_release_assessment(
        evidence,
        runtime=runtime,
    )

    request = runtime.requests[0]
    assert request.role == "orchestrator"
    assert request.model == "gpt-5.6-sol"
    assert request.reasoning_effort == "xhigh"
    assert request.context_tier == "long_context"
    assert request.attachments == []
    assert request.timeout_seconds == 900
    assert assessment.verdict == "ready"
    assert provenance.model == "gpt-5.6-sol"


@pytest.mark.asyncio
async def test_release_assessment_cannot_change_evidence_binding() -> None:
    evidence = build_release_evidence(_evidence_payload())
    response = _assessment_payload(evidence)
    response["evidence_manifest_hash"] = "d" * 64

    with pytest.raises(ValueError, match="evidence binding"):
        await run_release_assessment(
            evidence,
            runtime=FakeRuntime(response),
        )


@pytest.mark.asyncio
async def test_release_assessment_binds_complete_release_evidence() -> None:
    evidence = build_release_evidence(_evidence_payload())
    response = _assessment_payload(evidence)
    response["release_evidence_hash"] = "f" * 64

    with pytest.raises(ValueError, match="evidence binding"):
        await run_release_assessment(
            evidence,
            runtime=FakeRuntime(response),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "private_value",
    [
        "file:///home/example/private",
        "Jane Synthetic",
    ],
)
async def test_release_assessment_rejects_private_prose(
    private_value: str,
) -> None:
    evidence = build_release_evidence(_evidence_payload())
    response = _assessment_payload(evidence)
    response["summary"] = private_value

    with pytest.raises(ValueError, match="private"):
        await run_release_assessment(
            evidence,
            runtime=FakeRuntime(response),
        )


def test_render_test_report_uses_measured_evidence() -> None:
    evidence = build_release_evidence(_evidence_payload())
    assessment = ReleaseAssessment.model_validate(
        _assessment_payload(evidence)
    )

    report = render_test_report(evidence, assessment)

    assert sum(
        f"\n| {document.doc_type} |" in report
        for document in evidence.documents
    ) == 23
    assert "236" in report
    assert "23" in report
    assert "`gemini-3.6-flash`" in report
    assert "`claude-opus-4.8`" in report
    assert "`gpt-5.6-sol`" in report
    assert evidence.phase74_evidence_manifest_hash in report
    assert "## GPT-5.6 Sol Assessment" in report
    assert "## Accepted Self-Improvement Patches" in report
    assert "`dddddddddddddddddddddddddddddddddddddddd`" in report
    assert "independent post-patch evaluations" in report
    assert assessment.summary in report


def test_render_test_report_preserves_assessment_paragraphs() -> None:
    evidence = build_release_evidence(_evidence_payload())
    response = _assessment_payload(evidence)
    response["summary"] = "First measured conclusion.\n\nSecond conclusion."
    assessment = ReleaseAssessment.model_validate(response)

    report = render_test_report(evidence, assessment)

    assert "First measured conclusion.\n\nSecond conclusion." in report


def test_release_assessment_forbids_extra_measured_fields() -> None:
    evidence = build_release_evidence(_evidence_payload())
    response = _assessment_payload(evidence)
    response["worker_count"] = 999

    with pytest.raises(ValueError):
        ReleaseAssessment.model_validate(response)


@pytest.mark.asyncio
async def test_execute_release_writes_bound_report_and_evidence(
    tmp_path: Path,
) -> None:
    evidence = build_release_evidence(_evidence_payload())
    runtime = FakeRuntime(_assessment_payload(evidence))
    report_path = tmp_path / "TEST_REPORT.md"
    evidence_root = tmp_path / "phase75_evidence"

    result = await execute_release(
        evidence,
        report_path=report_path,
        evidence_root=evidence_root,
        runtime=runtime,
    )

    report = report_path.read_text(encoding="utf-8")
    manifest = json.loads(
        (evidence_root / "manifest.json").read_text(encoding="utf-8")
    )
    assessment = json.loads(
        (evidence_root / "assessment.json").read_text(encoding="utf-8")
    )
    release_record = json.loads(
        (evidence_root / "release_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["status"] == "ready"
    assert result["release_evidence_hash"] == release_evidence_hash(evidence)
    assert manifest["report_hash"] == hashlib.sha256(
        report.encode("utf-8")
    ).hexdigest()
    assert manifest["assessment_hash"] == assessment["evidence_hash"]
    assert manifest["release_evidence_hash"] == release_evidence_hash(evidence)
    assert manifest["release_evidence_record_hash"] == release_record[
        "evidence_hash"
    ]
    assert release_record["release_evidence_hash"] == release_evidence_hash(
        evidence
    )
    assert assessment["assessment"]["verdict"] == "ready"
    assert assessment["provenance"]["model"] == "gpt-5.6-sol"
    assert json.loads(assessment["raw_response"]) == assessment["assessment"]
    assert assessment["provenance"]["output_hash"] == hashlib.sha256(
        assessment["raw_response"].encode("utf-8")
    ).hexdigest()


def test_release_orchestrator_main_writes_outputs_with_injected_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = build_release_evidence(_evidence_payload())
    runtime = FakeRuntime(_assessment_payload(evidence))
    validation_path = tmp_path / "validation.json"
    validation_path.write_text(
        json.dumps(_evidence_payload()["validation_results"]),
        encoding="utf-8",
    )
    report_path = tmp_path / "TEST_REPORT.md"
    evidence_root = tmp_path / "phase75_evidence"
    observed: list[Any] = []

    def fake_loader(
        evidence_path: Any,
        *,
        validation_results: Any,
        source_root: Any,
        phase74_validator: Any,
    ) -> ReleaseEvidence:
        observed.append(
            (
                evidence_path,
                validation_results,
                source_root,
                phase74_validator,
            )
        )
        return evidence

    monkeypatch.setattr(
        release_orchestrator,
        "load_release_evidence",
        fake_loader,
    )

    exit_code = main(
        [
            "--phase74-evidence",
            str(tmp_path / "phase74_evidence"),
            "--source-root",
            str(tmp_path),
            "--validation-results",
            str(validation_path),
            "--output",
            str(report_path),
            "--evidence-output",
            str(evidence_root),
        ],
        runtime=runtime,
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "ready"
    assert output["documents"] == 23
    assert report_path.is_file()
    assert (evidence_root / "manifest.json").is_file()
    assert len(observed) == 1
    assert observed[0][2] == tmp_path


@pytest.mark.asyncio
async def test_validate_release_artifacts_detects_report_tampering(
    tmp_path: Path,
) -> None:
    evidence = build_release_evidence(_evidence_payload())
    report_path = tmp_path / "TEST_REPORT.md"
    evidence_root = tmp_path / "phase75_evidence"
    await execute_release(
        evidence,
        report_path=report_path,
        evidence_root=evidence_root,
        runtime=FakeRuntime(_assessment_payload(evidence)),
    )

    summary = validate_release_artifacts(
        evidence_root,
        report_path=report_path,
        expected_live=False,
    )

    assert summary["status"] == "ready"
    assert summary["documents"] == 23
    report_path.write_text(
        report_path.read_text(encoding="utf-8") + "tampered\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="report"):
        validate_release_artifacts(
            evidence_root,
            report_path=report_path,
            expected_live=False,
        )
