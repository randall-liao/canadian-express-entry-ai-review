from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import time

import pytest

from crawler import searchindex
from crawler.eval.agent_runtime import (
    AgentLifecycleError,
    AgentProvenance,
    AgentRequest,
    AgentResult,
    AgentRuntime,
    AgentRuntimeError,
    AgentTimeoutError,
    ResponseValidationError,
)
from crawler.eval.document_pipeline import (
    DocumentPipelineConfig,
    _CANDIDATE_SEMANTIC_ERRORS,
    _DocumentPipeline,
    run_document_pipeline,
)
from crawler.eval.holdout_splitter import split_doc_type_cases
from crawler.eval.public_bundle import build_public_review_bundle
from crawler.eval.pipeline_state import (
    CleanupResult,
    DescendantExitTimeoutError,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PDF = next(
    (_REPO_ROOT / "crawler" / "eval" / "pipelines").rglob("*.pdf")
).read_bytes()


def _case(case_id: str, sibling_id: str, verdict: str) -> dict[str, object]:
    return {
        "opaque_case_id": case_id,
        "sibling_case_id": sibling_id,
        "doc_type": "passport",
        "variant": "vector" if case_id < sibling_id else "scanned",
        "expected_verdict": verdict,
        "source_failure_id": None if verdict == "meets_requirements" else "PFL-1",
        "pdf_sha256": hashlib.sha256(_SAMPLE_PDF).hexdigest(),
    }


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, list[dict[str, object]]]:
    pipeline_root = tmp_path / "pipelines"
    doc_dir = pipeline_root / "passport"
    pdf_dir = doc_dir / "ground_truth" / "pdfs"
    pdf_dir.mkdir(parents=True)
    (doc_dir / "research").mkdir()

    groups = [
        ("1" * 32, "2" * 32, "meets_requirements"),
        ("3" * 32, "4" * 32, "defective"),
        ("5" * 32, "6" * 32, "defective"),
    ]
    cases: list[dict[str, object]] = []
    for left, right, verdict in groups:
        cases.extend((_case(left, right, verdict), _case(right, left, verdict)))
        (pdf_dir / f"{left}.pdf").write_bytes(_SAMPLE_PDF)
        (pdf_dir / f"{right}.pdf").write_bytes(_SAMPLE_PDF)
    (doc_dir / "ground_truth" / "ground_truth.json").write_text(
        json.dumps(cases),
        encoding="utf-8",
    )
    (doc_dir / "research" / "research.json").write_text(
        json.dumps({"doc_type": "passport", "requirements": []}),
        encoding="utf-8",
    )

    source_root = tmp_path / "source"
    source_path = source_root / "skills" / "document-agents" / "passport.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "\n".join(
            [
                "# Passport",
                "",
                "> `biographical data page passport`",
                "",
                "- Verify the biographical page.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    shared_path = source_root / "skills" / "pdf" / "SKILL.md"
    shared_path.parent.mkdir(parents=True)
    shared_path.write_text("# PDF review\n\n- Inspect the supplied PDF.\n", encoding="utf-8")
    return pipeline_root, source_root, source_path, cases


class PipelineRuntime(AgentRuntime):
    def __init__(
        self,
        *,
        source_content: str,
        holdout_ids: set[str],
        candidate_content: str | None = None,
        candidate_improves: bool = True,
        holdout_score: float = 0.5,
        holdout_rationale: str = "SEALED-HOLDOUT-RATIONALE",
    ) -> None:
        self.source_content = source_content
        self.holdout_ids = holdout_ids
        self.candidate_content = candidate_content
        self.candidate_improves = candidate_improves
        self.holdout_score = holdout_score
        self.holdout_rationale = holdout_rationale
        self.requests: list[AgentRequest] = []
        self.judge_calls = 0
        self.active = 0
        self.max_active = 0

    async def run(self, request: AgentRequest) -> AgentResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            self.requests.append(request)
            if request.role == "worker":
                content = json.dumps(
                    {
                        "question": "Review the supplied passport.",
                        "claims": [],
                        "basis": [],
                        "abstentions": [],
                        "prose": "No generic claims were made.",
                    }
                )
            elif request.role == "judge":
                self.judge_calls += 1
                case_ids = [
                    attachment.display_name.removesuffix(".pdf")
                    for attachment in request.attachments
                ]
                candidate_pass = self.judge_calls >= 2 and self.candidate_improves
                evaluations = {}
                for case_id in case_ids:
                    defect_recall = (
                        self.holdout_score
                        if case_id in self.holdout_ids
                        else 0.5
                        if not candidate_pass
                        else 0.8
                    )
                    evaluations[case_id] = {
                        "grounding_accuracy": 1.0,
                        "citation_exactness": 1.0,
                        "defect_recall": defect_recall,
                        "pii_containment": 1.0,
                        "blind_input_compliance": 1.0,
                    }
                content = json.dumps(
                    {
                        "doc_type": "passport",
                        "case_evaluations": evaluations,
                        "findings": [
                            {
                                "case_id": case_id,
                                "category": "defect_recall",
                                "severity": "major",
                                "description": self.holdout_rationale,
                            }
                            for case_id in case_ids
                            if case_id in self.holdout_ids
                        ],
                        "patch_recommendations": [],
                        "rationale": "Evaluation complete.",
                    }
                )
            else:
                content = json.dumps(
                    {
                        "target_file": "skills/document-agents/passport.md",
                        "candidate_content": (
                            self.candidate_content
                            if self.candidate_content is not None
                            else self.source_content
                            + "- Check the document signature when one is present.\n"
                        ),
                        "rationale": "Improve training defect recall.",
                    }
                )
            return AgentResult(
                content=content,
                provenance=_provenance(request, content, len(self.requests)),
            )
        finally:
            self.active -= 1


class FailingCandidateRuntime(PipelineRuntime):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.optimizer_completed = False

    async def run(self, request: AgentRequest) -> AgentResult:
        if request.role == "optimizer":
            result = await super().run(request)
            self.optimizer_completed = True
            return result
        if self.optimizer_completed and request.role == "worker":
            raise RuntimeError("SDK transport unavailable")
        return await super().run(request)


class InvalidResponseCandidateRuntime(PipelineRuntime):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.optimizer_completed = False

    async def run(self, request: AgentRequest) -> AgentResult:
        if request.role == "optimizer":
            result = await super().run(request)
            self.optimizer_completed = True
            return result
        if self.optimizer_completed and request.role == "worker":
            raise ResponseValidationError(
                "same-session response validation failed"
            )
        return await super().run(request)


class CandidateWorkerLifecycleRuntime(PipelineRuntime):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.optimizer_completed = False

    async def run(self, request: AgentRequest) -> AgentResult:
        if request.role == "optimizer":
            result = await super().run(request)
            self.optimizer_completed = True
            return result
        if self.optimizer_completed and request.role == "worker":
            raise AgentLifecycleError("SDK process identity unavailable")
        return await super().run(request)


class CandidateJudgeInfrastructureRuntime(PipelineRuntime):
    def __init__(self, error: AgentRuntimeError, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.error = error

    async def run(self, request: AgentRequest) -> AgentResult:
        if request.role == "judge" and self.judge_calls >= 1:
            raise self.error
        return await super().run(request)


class OptimizerLifecycleRuntime(PipelineRuntime):
    async def run(self, request: AgentRequest) -> AgentResult:
        if request.role == "optimizer":
            raise AgentLifecycleError("optimizer SDK process ownership lost")
        return await super().run(request)


class InvalidCandidateJudgeRuntime(PipelineRuntime):
    def __init__(self, failure: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.failure = failure

    async def run(self, request: AgentRequest) -> AgentResult:
        result = await super().run(request)
        if request.role != "judge" or self.judge_calls < 2:
            return result
        if self.failure == "json":
            content = "not one Judge JSON object"
        else:
            payload = json.loads(result.content)
            payload["case_evaluations"].pop(next(iter(payload["case_evaluations"])))
            content = json.dumps(payload)
        return AgentResult(
            content=content,
            provenance=_provenance(request, content, len(self.requests)),
        )


class InvalidSharedCandidateJudgeRuntime(PipelineRuntime):
    async def run(self, request: AgentRequest) -> AgentResult:
        result = await super().run(request)
        if request.role != "judge":
            return result
        content = "not one Judge JSON object"
        return AgentResult(
            content=content,
            provenance=_provenance(request, content, len(self.requests)),
        )


class InvalidCandidateOutputRuntime(PipelineRuntime):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.optimizer_completed = False
        self.candidate_failure_emitted = False

    async def run(self, request: AgentRequest) -> AgentResult:
        if request.role == "optimizer":
            result = await super().run(request)
            self.optimizer_completed = True
            return result
        if (
            self.optimizer_completed
            and request.role == "worker"
            and not self.candidate_failure_emitted
        ):
            self.candidate_failure_emitted = True
            content = json.dumps(
                {
                    "question": "Review the supplied passport.",
                    "claims": [],
                    "basis": [],
                    "abstentions": ["invalid"],
                    "prose": "Invalid candidate output.",
                }
            )
            self.requests.append(request)
            return AgentResult(
                content=content,
                provenance=_provenance(request, content, len(self.requests)),
            )
        return await super().run(request)


class ObservingRuntime(PipelineRuntime):
    def __init__(self, *, run_dir: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.run_dir = run_dir
        self.observed_stages: set[str] = set()

    async def run(self, request: AgentRequest) -> AgentResult:
        pipeline_state = json.loads(
            (self.run_dir / "pipeline_state.json").read_text(encoding="utf-8")
        )
        heartbeat = json.loads(
            (self.run_dir / "heartbeat.json").read_text(encoding="utf-8")
        )
        stage_manifest = json.loads(
            (
                self.run_dir
                / "stages"
                / f"{pipeline_state['stage']}.json"
            ).read_text(encoding="utf-8")
        )
        assert pipeline_state["status"] == "running"
        assert heartbeat["stage"] == pipeline_state["stage"]
        assert heartbeat["sequence"] == pipeline_state["heartbeat_sequence"]
        assert stage_manifest["status"] == "in_progress"
        self.observed_stages.add(pipeline_state["stage"])
        return await super().run(request)


class SlowHeartbeatRuntime(PipelineRuntime):
    def __init__(self, *, run_dir: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.run_dir = run_dir
        self.observed_periodic_heartbeat = False

    async def run(self, request: AgentRequest) -> AgentResult:
        initial = json.loads(
            (self.run_dir / "heartbeat.json").read_text(encoding="utf-8")
        )
        await asyncio.sleep(0.05)
        current = json.loads(
            (self.run_dir / "heartbeat.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (self.run_dir / "run_manifest.json").read_text(encoding="utf-8")
        )
        self.observed_periodic_heartbeat = self.observed_periodic_heartbeat or (
            current["sequence"] > initial["sequence"]
            and current["stage"] == "baseline_workers"
            and len(current["item"]) == 32
            and current["item"] not in request.prompt
            and request.attachments[0].display_name == "document.pdf"
            and current["attempt"] == 1
            and manifest["deadline"] >= time.time() + 600
        )
        return await super().run(request)


def _provenance(
    request: AgentRequest,
    content: str,
    sequence: int,
) -> AgentProvenance:
    return AgentProvenance(
        engine="injected-test-runner",
        sdk_version="1.0.8",
        runtime_protocol_version="1.0",
        role=request.role,
        model=request.model,
        effort=request.reasoning_effort,
        context_tier=request.context_tier,
        session_id=f"pipeline-session-{sequence}",
        prompt_hash=hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
        attachment_hashes=[
            hashlib.sha256(attachment.data).hexdigest()
            for attachment in request.attachments
        ],
        output_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        started_at="2026-07-25T00:00:00Z",
        completed_at="2026-07-25T00:00:01Z",
        duration_seconds=1.0,
        terminal_event="assistant.message",
        is_live=False,
    )


def test_document_pipeline_runs_stages_sequentially_and_returns_cas_evidence(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    original = source_path.read_bytes()
    runtime = PipelineRuntime(
        source_content=original.decode("utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-4",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.stages == [
        "baseline_workers",
        "baseline_judge",
        "optimizer",
        "candidate_workers",
        "candidate_judge",
        "patch_decision",
        "final_workers",
        "final_judge",
    ]
    assert result.status == "completed"
    assert result.max_live_sessions == 1
    assert runtime.max_active == 1
    assert result.patch.status == "accepted"
    assert result.patch.candidate_id is not None
    assert result.candidate_id == result.patch.candidate_id
    assert result.patch.candidate_id == result.patch.candidate_path.split("/")[-4]
    assert result.patch.source_hash == hashlib.sha256(original).hexdigest()
    assert result.source_compare_and_swap_hash == result.patch.source_hash
    assert result.candidate_content == result.patch.candidate_content
    assert result.candidate_path == result.patch.candidate_path
    assert result.candidate_content_hash == result.patch.candidate_content_hash
    assert result.metrics == result.patch.metrics
    assert result.decision_evidence == result.patch.evidence
    assert result.patch.candidate_content_hash == hashlib.sha256(
        result.patch.candidate_content.encode("utf-8")
    ).hexdigest()
    assert Path(result.patch.candidate_path).read_text(encoding="utf-8") == (
        result.patch.candidate_content
    )
    assert result.patch.metrics["candidate_train"]["overall_score"] > (
        result.patch.metrics["baseline_train"]["overall_score"]
    )
    assert result.final_bundle_hash == result.candidate_bundle_hash
    assert source_path.read_bytes() == original
    assert all(request.role != "orchestrator" for request in runtime.requests)

    run_dir = tmp_path / "state" / "runs" / "run-4" / "passport"
    run_manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert run_manifest["status"] == "completed"
    assert json.loads((run_dir / "pipeline_state.json").read_text())["status"] == "completed"
    assert not list(run_dir.rglob(".tmp-*"))


def test_optimization_phase_stops_before_final_worker_and_judge(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-optimization",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
            execution_phase="optimization",
        )
    )

    assert result.status == "completed"
    assert result.stages[-1] == "patch_decision"
    assert "final_workers" not in result.stages
    assert "final_judge" not in result.stages
    assert result.final_bundle_hash is None
    assert runtime.judge_calls == 2


def test_unanchored_exact_artifacts_are_never_imported(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {str(case["opaque_case_id"]) for case in holdout}
    first_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    first = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-import-source",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=first_runtime,
            execution_phase="optimization",
            source_revision="a" * 40,
        )
    )
    assert first.status == "completed"
    source_artifact_root = (
        tmp_path / "state" / "runs" / "run-import-source" / "passport"
    )
    second_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    second = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-import-target",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals-2",
            source_root=source_root,
            runtime=second_runtime,
            execution_phase="optimization",
            source_revision="b" * 40,
            artifact_import_roots=(source_artifact_root,),
        )
    )

    assert second.status == "completed"
    worker_requests = [
        request for request in second_runtime.requests if request.role == "worker"
    ]
    assert len(worker_requests) == 12
    judge_requests = [
        request for request in second_runtime.requests if request.role == "judge"
    ]
    assert len(judge_requests) == 2
    assert not (
        tmp_path
        / "state"
        / "runs"
        / "run-import-target"
        / "passport"
        / "imports"
    ).exists()


def test_fully_redigested_unanchored_worker_forgery_is_not_imported(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {str(case["opaque_case_id"]) for case in holdout}
    first_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-forgery-source",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=first_runtime,
            execution_phase="optimization",
            source_revision="a" * 40,
        )
    )
    source_artifact_root = (
        tmp_path / "state" / "runs" / "run-forgery-source" / "passport"
    )
    artifact_path = source_artifact_root / "artifacts" / "baseline_workers.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    first_case = sorted(artifact["output"])[0]
    report = artifact["output"][first_case]
    report["prose"] = "Coordinated forged model output."
    answer = {
        key: report[key]
        for key in ("question", "claims", "basis", "abstentions", "prose")
    }
    report["_provenance"]["answer_hash"] = hashlib.sha256(
        json.dumps(
            answer,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    from crawler.eval.pipeline_worker import _worker_provenance_digest

    report["_provenance"]["provenance_digest"] = _worker_provenance_digest(
        report["_provenance"]
    )
    artifact["output_hash"] = hashlib.sha256(
        json.dumps(
            artifact["output"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    stage_path = source_artifact_root / "stages" / "baseline_workers.json"
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    stage["output_hash"] = artifact["output_hash"]
    stage_path.write_text(json.dumps(stage), encoding="utf-8")
    manifest_path = source_artifact_root / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["output_hashes"]["baseline_workers"] = artifact["output_hash"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    second_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-forgery-target",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals-2",
            source_root=source_root,
            runtime=second_runtime,
            execution_phase="optimization",
            source_revision="b" * 40,
            artifact_import_roots=(source_artifact_root,),
        )
    )

    assert result.status == "completed"
    assert len(
        [request for request in second_runtime.requests if request.role == "worker"]
    ) == 12
    assert all(
        request.prompt != "Coordinated forged model output."
        for request in second_runtime.requests
    )


def test_rejects_worker_import_when_any_model_binding_changes(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {str(case["opaque_case_id"]) for case in holdout}
    first_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-import-mismatch-source",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=first_runtime,
            execution_phase="optimization",
            source_revision="a" * 40,
        )
    )
    source_artifact_root = (
        tmp_path
        / "state"
        / "runs"
        / "run-import-mismatch-source"
        / "passport"
    )
    source_path.write_text(
        source_path.read_text() + "\n- Changed public Worker evidence.\n",
        encoding="utf-8",
    )
    second_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-import-mismatch-target",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals-2",
            source_root=source_root,
            runtime=second_runtime,
            execution_phase="optimization",
            source_revision="b" * 40,
            artifact_import_roots=(source_artifact_root,),
        )
    )

    worker_requests = [
        request for request in second_runtime.requests if request.role == "worker"
    ]
    assert len(worker_requests) == len(cases) * 2


def test_final_phase_uses_only_frozen_manifest_workers_and_judge(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {str(case["opaque_case_id"]) for case in holdout}
    optimization_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    optimization = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-before-freeze",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=optimization_runtime,
            execution_phase="optimization",
        )
    )
    source_path.write_text(
        optimization.patch.candidate_content,
        encoding="utf-8",
    )
    bundle = build_public_review_bundle(
        "passport",
        corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
        skills_dir=source_root / "skills" / "document-agents",
        shared_skill_path=source_root / "skills" / "pdf" / "SKILL.md",
    )
    manifest = {
        "schema_version": "phase74-final-manifest-v1",
        "run_id": "parent-run",
        "git_revision": "a" * 40,
        "bundle_hashes": {"passport": bundle["bundle_hash"]},
        "source_hashes": {
            "skills/document-agents/passport.md": hashlib.sha256(
                source_path.read_bytes()
            ).hexdigest(),
            "skills/pdf/SKILL.md": hashlib.sha256(
                (source_root / "skills" / "pdf" / "SKILL.md").read_bytes()
            ).hexdigest(),
        },
        "optimization_complete": True,
        "created_at": "2026-07-25T00:00:00+00:00",
    }
    manifest["manifest_hash"] = hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    final_manifest_path = tmp_path / "final_manifest.json"
    final_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    final_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )

    final = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-final",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=final_runtime,
            execution_phase="final",
            final_manifest_path=final_manifest_path,
            final_manifest_hash=manifest["manifest_hash"],
            source_revision=manifest["git_revision"],
            optimization_result_path=(
                tmp_path
                / "state"
                / "runs"
                / "run-before-freeze"
                / "passport"
                / "pipeline_result.json"
            ),
        )
    )

    assert final.status == "completed"
    assert final.stages == ["final_workers", "final_judge"]
    assert final.patch == optimization.patch
    assert final.final_bundle_hash == bundle["bundle_hash"]
    assert {request.role for request in final_runtime.requests} == {
        "worker",
        "judge",
    }
    run_dir = tmp_path / "state" / "runs" / "run-final" / "passport"
    for stage in ("final_workers", "final_judge"):
        artifact = json.loads(
            (run_dir / "artifacts" / f"{stage}.json").read_text()
        )
        assert (
            artifact["input_manifest"]["final_manifest_hash"]
            == manifest["manifest_hash"]
        )


def test_shared_baseline_phase_evaluates_current_bundle_without_optimizer(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-shared-baseline",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
            execution_phase="shared_baseline",
        )
    )

    assert result.status == "completed"
    assert result.stages == [
        "shared_baseline_workers",
        "shared_baseline_judge",
    ]
    assert {request.role for request in runtime.requests} == {
        "worker",
        "judge",
    }


def test_shared_candidate_phase_uses_sandboxed_shared_content(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    proposal_root = tmp_path / "proposals"
    candidate_path = (
        proposal_root
        / ("candidate_" + "b" * 12)
        / "skills"
        / "pdf"
        / "SKILL.md"
    )
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        "# PDF review\n\n- Inspect the supplied PDF.\n- Verify visible seals.\n",
        encoding="utf-8",
    )
    runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-shared-candidate",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=proposal_root,
            source_root=source_root,
            runtime=runtime,
            execution_phase="shared_candidate",
            shared_candidate_path=candidate_path,
        )
    )

    assert result.status == "completed"
    assert result.stages == [
        "shared_candidate_workers",
        "shared_candidate_judge",
    ]
    assert result.candidate_bundle_hash == result.final_bundle_hash
    assert result.candidate_bundle_hash != result.baseline_bundle_hash


def test_shared_candidate_semantic_judge_failure_rejects_candidate(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    proposal_root = tmp_path / "proposals"
    candidate_path = (
        proposal_root
        / ("candidate_" + "b" * 12)
        / "skills"
        / "pdf"
        / "SKILL.md"
    )
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        "# PDF review\n\n- Inspect the supplied PDF.\n",
        encoding="utf-8",
    )
    runtime = InvalidSharedCandidateJudgeRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-shared-candidate-invalid",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=proposal_root,
            source_root=source_root,
            runtime=runtime,
            execution_phase="shared_candidate",
            shared_candidate_path=candidate_path,
        )
    )

    assert result.status == "completed"
    assert result.patch.status == "rejected"
    assert len(result.patch.evidence) == 1
    evidence = result.patch.evidence[0]
    assert evidence["kind"] == "shared_candidate_evaluation"
    assert evidence["passed"] is False
    assert evidence["selection"] == "shared-candidate"
    assert evidence["stage"] == "shared_candidate_judge"
    assert evidence["error_type"] == "JudgeExecutionError"
    assert "raw JSON object" in evidence["message"]


def test_two_sibling_group_pipeline_finishes_with_insufficient_training_rejection(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    cases = cases[:4]
    doc_dir = pipeline_root / "passport"
    (doc_dir / "ground_truth" / "ground_truth.json").write_text(
        json.dumps(cases),
        encoding="utf-8",
    )
    for case_id in ("5" * 32, "6" * 32):
        (doc_dir / "ground_truth" / "pdfs" / f"{case_id}.pdf").unlink()
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    source_content = source_path.read_text(encoding="utf-8")
    runtime = PipelineRuntime(
        source_content=source_content,
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-two-groups",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "completed"
    assert result.stages == [
        "baseline_workers",
        "baseline_judge",
        "optimizer",
        "candidate_workers",
        "candidate_judge",
        "patch_decision",
        "final_workers",
        "final_judge",
    ]
    assert result.patch.status == "rejected"
    assert result.patch.evidence[-1]["kind"] == "insufficient_training_data"
    assert result.final_bundle_hash == result.baseline_bundle_hash


def test_infrastructure_failure_blocks_instead_of_rejecting_candidate(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    original = source_path.read_bytes()
    runtime = FailingCandidateRuntime(
        source_content=original.decode("utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-blocked",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "blocked"
    assert result.patch.status == "blocked"
    assert result.patch.evidence == [
        {
            "kind": "infrastructure_failure",
            "stage": "candidate_workers",
            "error_type": "RuntimeError",
            "message": "SDK transport unavailable",
        }
    ]
    assert source_path.read_bytes() == original
    run_dir = tmp_path / "state" / "runs" / "run-blocked" / "passport"
    assert json.loads((run_dir / "pipeline_state.json").read_text())["status"] == "blocked"
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["error_classification"] == "infrastructure_blocked"


def test_candidate_response_validation_failure_rejects_instead_of_blocking(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = InvalidResponseCandidateRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-candidate-response-invalid",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
            execution_phase="optimization",
        )
    )

    assert result.status == "completed"
    assert result.patch.status == "rejected"
    assert result.patch.evidence[-1]["kind"] == "candidate_evaluation"
    assert result.patch.evidence[-1]["error_type"] == "ResponseValidationError"


def test_candidate_semantic_errors_exclude_runtime_infrastructure() -> None:
    assert not any(
        issubclass(error_type, AgentRuntimeError)
        for error_type in _CANDIDATE_SEMANTIC_ERRORS
    )


def test_descendant_reconciliation_failure_supersedes_semantic_error(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, _, _ = _write_fixture(tmp_path)
    pipeline = _DocumentPipeline(
        DocumentPipelineConfig(
            run_id="run-descendant-priority",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=PipelineRuntime(source_content="", holdout_ids=set()),
            stage_cleanup_grace_seconds=0.01,
        )
    )
    wait_calls = 0

    def never_reconciled(*args: object, **kwargs: object) -> None:
        nonlocal wait_calls
        wait_calls += 1
        raise DescendantExitTimeoutError("descendant still running")

    pipeline.store.wait_for_verified_descendants = (  # type: ignore[method-assign]
        never_reconciled
    )
    pipeline.store.terminate_verified_processes = (  # type: ignore[method-assign]
        lambda **kwargs: CleanupResult(remaining_pids=[9876])
    )

    def semantic_failure() -> dict[str, Any]:
        raise ResponseValidationError("invalid candidate response")

    with pytest.raises(AgentLifecycleError) as exc_info:
        pipeline._model_call(
            semantic_failure,
            stage="candidate_workers",
            item="case",
            completed=0,
            expected=1,
        )

    assert isinstance(exc_info.value.__cause__, ResponseValidationError)
    assert wait_calls == 2


def test_candidate_worker_lifecycle_failure_blocks_without_rejection(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = CandidateWorkerLifecycleRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-candidate-worker-lifecycle",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "blocked"
    assert result.patch.status == "blocked"
    assert result.patch.evidence[-1]["stage"] == "candidate_workers"
    assert result.patch.evidence[-1]["error_type"] == "AgentLifecycleError"
    manifest = json.loads(
        (
            tmp_path
            / "state"
            / "runs"
            / "run-candidate-worker-lifecycle"
            / "passport"
            / "run_manifest.json"
        ).read_text()
    )
    assert manifest["error_classification"] == "infrastructure_blocked"


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (
            AgentLifecycleError("Judge SDK process ownership lost"),
            "AgentLifecycleError",
        ),
        (AgentTimeoutError("Judge SDK request timed out"), "AgentTimeoutError"),
    ],
)
def test_candidate_judge_infrastructure_failure_survives_and_blocks(
    tmp_path: Path,
    error: AgentRuntimeError,
    error_type: str,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = CandidateJudgeInfrastructureRuntime(
        error,
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id=f"run-candidate-judge-{error_type.lower()}",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "blocked"
    assert result.patch.status == "blocked"
    assert result.patch.evidence[-1]["stage"] == "candidate_judge"
    assert result.patch.evidence[-1]["error_type"] == error_type


@pytest.mark.parametrize("failure", ["json", "coverage"])
def test_deterministic_candidate_judge_failure_remains_semantic_rejection(
    tmp_path: Path,
    failure: str,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = InvalidCandidateJudgeRuntime(
        failure,
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id=f"run-invalid-candidate-judge-{failure}",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
            execution_phase="optimization",
        )
    )

    assert result.status == "completed"
    assert result.patch.status == "rejected"
    assert result.patch.evidence[-1]["stage"] == "candidate_judge"
    assert result.patch.evidence[-1]["error_type"] == "JudgeExecutionError"


def test_optimizer_lifecycle_failure_blocks_without_rejection(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = OptimizerLifecycleRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-optimizer-lifecycle",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "blocked"
    assert result.patch.status == "blocked"
    assert result.patch.evidence[-1]["stage"] == "optimizer"
    assert result.patch.evidence[-1]["error_type"] == "AgentLifecycleError"


def test_candidate_semantic_failure_rejects_patch_and_keeps_baseline(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    original = source_path.read_bytes()
    runtime = InvalidCandidateOutputRuntime(
        source_content=original.decode("utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-invalid-candidate-output",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "completed"
    assert result.patch.status == "rejected"
    assert result.patch.evidence[-1] == {
        "kind": "candidate_evaluation",
        "passed": False,
        "stage": "candidate_workers",
        "error_type": "ValueError",
        "message": "Every AnswerObject abstention must be an object",
    }
    assert result.final_bundle_hash == result.baseline_bundle_hash
    assert source_path.read_bytes() == original


def test_optimizer_prompt_excludes_holdout_commitment_and_derived_values(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {str(case["opaque_case_id"]) for case in holdout}
    runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
        holdout_score=0.123456,
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-prompt-isolation",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "completed"
    optimizer_request = next(
        request for request in runtime.requests if request.role == "optimizer"
    )
    prompt = optimizer_request.prompt
    commitment = {
        "count": len(holdout_ids),
        "hash": hashlib.sha256(
            json.dumps(sorted(holdout_ids), separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    assert "holdout" not in prompt.lower()
    assert json.dumps(commitment, sort_keys=True) not in prompt
    assert commitment["hash"] not in prompt
    assert "0.123456" not in prompt
    assert "SEALED-HOLDOUT-RATIONALE" not in prompt
    assert holdout_ids.isdisjoint(prompt.split())

    artifact = json.loads(
        (
            tmp_path
            / "state"
            / "runs"
            / "run-prompt-isolation"
            / "passport"
            / "artifacts"
            / "optimizer.json"
        ).read_text(encoding="utf-8")
    )
    assert artifact["input_manifest"]["holdout_commitment"] == commitment


def test_exact_completed_artifacts_are_reused_without_model_sessions(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {str(case["opaque_case_id"]) for case in holdout}
    config_kwargs = {
        "run_id": "run-reuse",
        "doc_type": "passport",
        "pipeline_root": pipeline_root,
        "state_root": tmp_path / "state",
        "corpus_db_path": _REPO_ROOT / "corpus" / "index.db",
        "proposal_sandbox_root": tmp_path / "proposals",
        "source_root": source_root,
    }
    first_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    first = run_document_pipeline(
        DocumentPipelineConfig(runtime=first_runtime, **config_kwargs)
    )
    assert first.status == "completed"

    second_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    second = run_document_pipeline(
        DocumentPipelineConfig(runtime=second_runtime, **config_kwargs)
    )

    assert second.status == "completed"
    assert second.stages == first.stages
    assert second.patch == first.patch
    assert second_runtime.requests == []
    assert second.max_live_sessions == 0


def test_failed_resume_does_not_leave_durable_state_completed(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {str(case["opaque_case_id"]) for case in holdout}
    config_kwargs = {
        "run_id": "run-failed-resume",
        "doc_type": "passport",
        "pipeline_root": pipeline_root,
        "state_root": tmp_path / "state",
        "corpus_db_path": _REPO_ROOT / "corpus" / "index.db",
        "proposal_sandbox_root": tmp_path / "proposals",
        "source_root": source_root,
    }
    first = run_document_pipeline(
        DocumentPipelineConfig(
            runtime=PipelineRuntime(
                source_content=source_path.read_text(encoding="utf-8"),
                holdout_ids=holdout_ids,
            ),
            **config_kwargs,
        )
    )
    assert first.status == "completed"
    run_dir = tmp_path / "state" / "runs" / "run-failed-resume" / "passport"
    (run_dir / "artifacts" / "baseline_judge.json").unlink()

    resumed = run_document_pipeline(
        DocumentPipelineConfig(
            runtime=PipelineRuntime(
                source_content=source_path.read_text(encoding="utf-8"),
                holdout_ids=holdout_ids,
            ),
            **config_kwargs,
        )
    )

    assert resumed.status == "blocked"
    assert "baseline_workers" in resumed.stages
    assert json.loads((run_dir / "pipeline_state.json").read_text())["status"] == "blocked"
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["error_classification"] == "infrastructure_blocked"
    failed_stage = json.loads((run_dir / "stages" / "baseline_judge.json").read_text())
    assert failed_stage["status"] == "failed"


def test_candidate_bundle_validation_failure_is_semantic_rejection(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    source_content = source_path.read_text(encoding="utf-8")
    runtime = PipelineRuntime(
        source_content=source_content,
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
        candidate_content=source_content.replace(
            "> `biographical data page passport`\n",
            "",
        ),
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-invalid-bundle",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "completed"
    assert result.patch.status == "rejected"
    assert result.patch.candidate_id is not None
    assert result.patch.evidence[-1]["kind"] == "candidate_bundle_validation"
    assert result.final_bundle_hash == result.baseline_bundle_hash


def test_metric_gate_rejection_runs_final_pass_against_source_bundle(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
        candidate_improves=False,
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-rejected",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "completed"
    assert result.patch.status == "rejected"
    assert result.patch.evidence[-1]["kind"] == "metric_gate"
    assert not result.patch.evidence[-1]["passed"]
    assert result.final_bundle_hash == result.baseline_bundle_hash
    assert result.final_bundle_hash != result.candidate_bundle_hash


@pytest.mark.parametrize(
    "mutation",
    ["pipeline_root", "ground_truth", "pdf", "research", "extracted_text"],
)
def test_pipeline_rejects_symlinked_cross_document_inputs(
    tmp_path: Path,
    mutation: str,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    selected_root = pipeline_root
    doc_dir = pipeline_root / "passport"
    first_case_id = str(cases[0]["opaque_case_id"])
    external = tmp_path / "other-document"
    external.mkdir()

    if mutation == "pipeline_root":
        selected_root = tmp_path / "pipeline-link"
        selected_root.symlink_to(pipeline_root, target_is_directory=True)
    elif mutation == "ground_truth":
        path = doc_dir / "ground_truth" / "ground_truth.json"
        replacement = external / "ground_truth.json"
        replacement.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(replacement)
    elif mutation == "pdf":
        path = doc_dir / "ground_truth" / "pdfs" / f"{first_case_id}.pdf"
        replacement = external / path.name
        replacement.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(replacement)
    elif mutation == "research":
        path = doc_dir / "research" / "research.json"
        replacement = external / "research.json"
        replacement.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(replacement)
    else:
        path = doc_dir / "ground_truth" / "pdfs" / f"{first_case_id}.txt"
        replacement = external / path.name
        replacement.write_text("cross-document text", encoding="utf-8")
        path.symlink_to(replacement)

    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )
    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id=f"run-symlink-{mutation}",
            doc_type="passport",
            pipeline_root=selected_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "blocked"
    assert result.patch.status == "blocked"
    assert runtime.requests == []
    assert "symlink" in (result.error or "").lower()


def test_pipeline_rejects_mismatched_research_document_identity(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    research_path = pipeline_root / "passport" / "research" / "research.json"
    research_path.write_text(
        json.dumps({"doc_type": "police_certificate", "requirements": []}),
        encoding="utf-8",
    )
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-mismatched-research",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "blocked"
    assert runtime.requests == []
    assert "research" in (result.error or "").lower()
    assert "doc_type" in (result.error or "")


@pytest.mark.parametrize("failure_mode", ["zero_hits", "unresolved", "invalid_schema", "empty_query"])
def test_candidate_corpus_evidence_failure_is_semantic_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    source_content = source_path.read_text(encoding="utf-8")
    candidate_query = f"candidate-{failure_mode}-evidence-query"
    candidate_content = source_content.replace(
        "biographical data page passport",
        candidate_query,
    )
    runtime = PipelineRuntime(
        source_content=source_content,
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
        candidate_content=candidate_content,
    )
    real_search = searchindex.search
    real_resolve = searchindex.resolve

    def controlled_search(db_path: Path, query: str, limit: int = 20) -> object:
        if query == candidate_query:
            if failure_mode == "zero_hits":
                return {"hits": []}
            if failure_mode == "invalid_schema":
                return []
            if failure_mode == "empty_query":
                raise searchindex.EmptyQuery(f"no searchable terms in query: {query!r}")
            return {"hits": [{"chunk_id": "candidate/missing.md#000"}]}
        return real_search(db_path, query, limit=limit)

    def controlled_resolve(db_path: Path, chunk_id: str) -> dict | None:
        if chunk_id == "candidate/missing.md#000":
            return None
        return real_resolve(db_path, chunk_id)

    monkeypatch.setattr(searchindex, "search", controlled_search)
    monkeypatch.setattr(searchindex, "resolve", controlled_resolve)

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id=f"run-candidate-{failure_mode}",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "completed"
    assert result.patch.status == "rejected"
    assert result.patch.candidate_id is not None
    assert result.patch.evidence[-1]["kind"] == "candidate_bundle_validation"
    assert result.patch.evidence[-1]["passed"] is False


def test_candidate_punctuation_only_query_is_semantic_rejection(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    source_content = source_path.read_text(encoding="utf-8")
    candidate_content = source_content.replace(
        "biographical data page passport",
        "???",
    )
    runtime = PipelineRuntime(
        source_content=source_content,
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
        candidate_content=candidate_content,
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-candidate-punctuation-only",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "completed"
    assert result.patch.status == "rejected"
    assert result.patch.candidate_id is not None
    assert result.patch.evidence[-1]["kind"] == "candidate_bundle_validation"
    assert result.patch.evidence[-1]["passed"] is False
    assert "no searchable terms" in result.patch.evidence[-1]["reasons"][0]


def test_missing_corpus_database_remains_infrastructure_blocked(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-missing-corpus",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=tmp_path / "missing-corpus.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "blocked"
    assert result.patch.status == "blocked"
    assert result.patch.candidate_id is None
    assert result.patch.evidence[-1]["kind"] == "infrastructure_failure"
    assert result.patch.evidence[-1]["error_type"] == "FileNotFoundError"
    assert runtime.requests == []


def test_tampered_stage_artifact_is_not_reused(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {str(case["opaque_case_id"]) for case in holdout}
    config_kwargs = {
        "run_id": "run-tamper",
        "doc_type": "passport",
        "pipeline_root": pipeline_root,
        "state_root": tmp_path / "state",
        "corpus_db_path": _REPO_ROOT / "corpus" / "index.db",
        "proposal_sandbox_root": tmp_path / "proposals",
        "source_root": source_root,
    }
    first_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )
    assert run_document_pipeline(
        DocumentPipelineConfig(runtime=first_runtime, **config_kwargs)
    ).status == "completed"

    artifact_path = (
        tmp_path
        / "state"
        / "runs"
        / "run-tamper"
        / "passport"
        / "artifacts"
        / "baseline_workers.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    first_case = sorted(artifact["output"])[0]
    artifact["output"][first_case]["prose"] = "tampered"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    second_runtime = PipelineRuntime(
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids=holdout_ids,
    )

    second = run_document_pipeline(
        DocumentPipelineConfig(runtime=second_runtime, **config_kwargs)
    )

    assert second.status == "blocked"
    assert second.patch.status == "blocked"
    assert second.patch.evidence[0]["stage"] == "baseline_workers"
    assert second_runtime.requests == []


def test_running_state_and_heartbeat_cover_every_model_stage(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    run_dir = tmp_path / "state" / "runs" / "run-observed" / "passport"
    runtime = ObservingRuntime(
        run_dir=run_dir,
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-observed",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
        )
    )

    assert result.status == "completed"
    assert runtime.observed_stages == {
        "baseline_workers",
        "baseline_judge",
        "optimizer",
        "candidate_workers",
        "candidate_judge",
        "final_workers",
        "final_judge",
    }


def test_model_inference_maintains_periodic_atomic_heartbeat_and_stage_deadline(
    tmp_path: Path,
) -> None:
    pipeline_root, source_root, source_path, cases = _write_fixture(tmp_path)
    _, holdout = split_doc_type_cases(cases, doc_type="passport")
    run_dir = tmp_path / "state" / "runs" / "run-heartbeat" / "passport"
    runtime = SlowHeartbeatRuntime(
        run_dir=run_dir,
        source_content=source_path.read_text(encoding="utf-8"),
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )

    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id="run-heartbeat",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=_REPO_ROOT / "corpus" / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
            heartbeat_interval_seconds=0.01,
        )
    )

    assert result.status == "completed"
    assert runtime.observed_periodic_heartbeat
