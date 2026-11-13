"""Sequential, isolated evaluation pipeline for one document type."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Literal

from crawler.eval.agent_runtime import (
    AgentLifecycleError,
    AgentRuntime,
    AgentRuntimeError,
    AgentTimeoutError,
    ResponseValidationError,
    validate_persisted_agent_provenance,
)
from crawler.eval.genuine_optimizer import (
    OptimizerProposal,
    _OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
    _build_optimizer_model_input,
    _build_optimizer_training_input,
    derive_optimizer_candidate_id,
    run_candidate_optimization_pass,
)
from crawler.eval.holdout_splitter import (
    seal_holdout_findings,
    split_doc_type_cases,
)
from crawler.eval.patch_evaluator import (
    evaluate_candidate_patch,
    validate_patch_allowlist,
    validate_target_allowlist,
)
from crawler.eval.pipeline_judge import (
    JudgeExecutionError,
    JudgeEvaluationBatch,
    _JUDGE_PROVENANCE_EXTRA_FIELDS,
    _build_judge_prompt,
    _judge_provenance_digest,
    build_judge_input_manifest,
    run_batched_document_judge,
)
from crawler.eval.pipeline_state import (
    DescendantExitTimeoutError,
    PipelineStateStore,
    StageManifest,
    atomic_write_json,
)
from crawler.eval.pipeline_worker import (
    CopilotExecutionError,
    _WORKER_PROVENANCE_EXTRA_FIELDS,
    _assert_answer_blindness_and_pii,
    _build_parent_pii_manifest,
    _build_worker_prompt,
    _worker_provenance_digest,
    build_worker_input_manifest,
    run_blind_worker_task,
)
from crawler.eval.public_bundle import (
    DOC_TYPE_TO_SKILL,
    PublicBundleValidationError,
    build_public_review_bundle,
)
from crawler.eval.real_worker import _validate_answer_object
from crawler.grounding import check_answer_grounding


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_STATE_ROOT = _REPO_ROOT / "reports" / "sdk_pipeline_state"
_PROPOSAL_ROOT = _REPO_ROOT / "reports" / "proposal_sandboxes"
_CORPUS_DB = _REPO_ROOT / "corpus" / "index.db"
_STAGES = [
    "baseline_workers",
    "baseline_judge",
    "optimizer",
    "candidate_workers",
    "candidate_judge",
    "patch_decision",
    "final_workers",
    "final_judge",
]
_SCORE_FIELDS = (
    "grounding_accuracy",
    "citation_exactness",
    "defect_recall",
    "pii_containment",
    "blind_input_compliance",
)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CASE_ID = re.compile(r"^[a-f0-9]{32}$")
_CANDIDATE_ID = re.compile(r"^candidate_[a-f0-9]{12}$")
_REVISION = re.compile(r"^[a-f0-9]{40,64}$")
_WORKER_STAGE_TIMEOUT_SECONDS = 600
_JUDGE_STAGE_TIMEOUT_SECONDS = 900
_OPTIMIZER_STAGE_TIMEOUT_SECONDS = 600
_DEFAULT_STAGE_CLEANUP_GRACE_SECONDS = 30


class CandidateBundleValidationError(ValueError):
    """A deterministic candidate bundle defect that warrants rejection."""


_CANDIDATE_SEMANTIC_ERRORS = (
    ValueError,
    CopilotExecutionError,
    JudgeExecutionError,
    ResponseValidationError,
)


@dataclass(frozen=True)
class DocumentPipelineConfig:
    """Immutable inputs for one document-type child pipeline."""

    run_id: str
    doc_type: str
    pipeline_root: Path = _PIPELINES_DIR
    state_root: Path = _STATE_ROOT
    corpus_db_path: Path = _CORPUS_DB
    proposal_sandbox_root: Path = _PROPOSAL_ROOT
    source_root: Path = _REPO_ROOT
    runtime: AgentRuntime | None = None
    execution_phase: Literal[
        "full",
        "optimization",
        "shared_baseline",
        "shared_candidate",
        "final",
    ] = "full"
    final_manifest_path: Path | None = None
    final_manifest_hash: str | None = None
    optimization_result_path: Path | None = None
    shared_candidate_path: Path | None = None
    source_revision: str | None = None
    artifact_import_roots: tuple[Path, ...] = ()
    heartbeat_interval_seconds: float = 30.0
    stage_cleanup_grace_seconds: float = _DEFAULT_STAGE_CLEANUP_GRACE_SECONDS


@dataclass(frozen=True)
class PatchDecision:
    """Candidate evidence returned to the source-owning parent."""

    status: Literal["accepted", "rejected", "blocked"]
    target_file: str | None
    candidate_id: str | None
    candidate_path: str | None
    candidate_content: str
    candidate_content_hash: str | None
    source_hash: str | None
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    @property
    def source_compare_and_swap_hash(self) -> str | None:
        return self.source_hash

    @property
    def decision_evidence(self) -> list[dict[str, Any]]:
        return self.evidence


@dataclass(frozen=True)
class DocumentPipelineResult:
    """Terminal result for one isolated document pipeline."""

    run_id: str
    doc_type: str
    status: Literal["completed", "blocked", "cancelled"]
    stages: list[str]
    max_live_sessions: int
    patch: PatchDecision
    baseline_bundle_hash: str | None = None
    candidate_bundle_hash: str | None = None
    final_bundle_hash: str | None = None
    error: str | None = None

    @property
    def candidate_content(self) -> str:
        return self.patch.candidate_content

    @property
    def candidate_id(self) -> str | None:
        return self.patch.candidate_id

    @property
    def candidate_content_hash(self) -> str | None:
        return self.patch.candidate_content_hash

    @property
    def candidate_path(self) -> str | None:
        return self.patch.candidate_path

    @property
    def source_compare_and_swap_hash(self) -> str | None:
        return self.patch.source_compare_and_swap_hash

    @property
    def metrics(self) -> dict[str, dict[str, float]]:
        return self.patch.metrics

    @property
    def decision_evidence(self) -> list[dict[str, Any]]:
        return self.patch.decision_evidence


@dataclass(frozen=True)
class DocumentPipelineInputSnapshot:
    """Safety-validated, hash-bound preflight inputs for one document type."""

    doc_type: str
    case_ids: tuple[str, ...]
    input_hashes: dict[str, str]
    source_hash: str
    bundle_hash: str


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


def _bytes_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _DocumentPipeline:
    def __init__(
        self,
        config: DocumentPipelineConfig,
        *,
        initialize_state: bool = True,
    ) -> None:
        self.config = config
        self._validate_names()
        self.pipeline_root_input = Path(config.pipeline_root)
        self.pipeline_root = self.pipeline_root_input.resolve()
        self.doc_dir = (self.pipeline_root / config.doc_type).resolve()
        self.source_root_input = Path(config.source_root)
        self.source_root = self.source_root_input.resolve()
        self.corpus_db_input = Path(config.corpus_db_path)
        self.corpus_db_path = self.corpus_db_input.resolve()
        self.proposal_root_input = Path(config.proposal_sandbox_root)
        self.proposal_root = self.proposal_root_input.resolve()
        self.store: PipelineStateStore | None = None
        if initialize_state:
            self.store = PipelineStateStore(
                Path(config.state_root),
                run_id=config.run_id,
                doc_type=config.doc_type,
            )
            self.artifacts_dir = self.store.run_dir / "artifacts"
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
            self.pipeline_state_path = self.store.run_dir / "pipeline_state.json"
            self.result_path = self.store.run_dir / "pipeline_result.json"
        else:
            self.artifacts_dir = Path()
            self.pipeline_state_path = Path()
            self.result_path = Path()
        self.completed_stages: list[str] = []
        self.current_stage = "init"
        self.current_input_hash = "0" * 64
        self.live_sessions = 0
        self.max_live_sessions = 0
        self.metrics: dict[str, dict[str, float]] = {}
        self.candidate_result: dict[str, Any] | None = None
        self.baseline_bundle: dict[str, Any] | None = None
        self.candidate_bundle: dict[str, Any] | None = None
        self.final_bundle: dict[str, Any] | None = None
        self.target_file: str | None = None
        self.source_hash: str | None = None
        self.source_content = ""
        self.ground_truth_dir = self.doc_dir / "ground_truth"
        self.pdf_dir = self.ground_truth_dir / "pdfs"
        self.research_dir = self.doc_dir / "research"
        self.document_skills_dir = self.source_root / "skills" / "document-agents"
        self.shared_skill_path = self.source_root / "skills" / "pdf" / "SKILL.md"

    def _validate_names(self) -> None:
        if not _SAFE_NAME.fullmatch(self.config.run_id):
            raise ValueError("run_id must be a path-safe identifier")
        if not _SAFE_NAME.fullmatch(self.config.doc_type):
            raise ValueError("doc_type must be a path-safe identifier")
        if self.config.execution_phase not in {
            "full",
            "optimization",
            "shared_baseline",
            "shared_candidate",
            "final",
        }:
            raise ValueError(
                "execution_phase must be full, optimization, "
                "shared_baseline, shared_candidate, or final"
            )
        if self.config.source_revision is not None and not _REVISION.fullmatch(
            self.config.source_revision
        ):
            raise ValueError("source_revision must be a full hexadecimal revision")
        for name, value in (
            ("heartbeat_interval_seconds", self.config.heartbeat_interval_seconds),
            (
                "stage_cleanup_grace_seconds",
                self.config.stage_cleanup_grace_seconds,
            ),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or value <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")

    @staticmethod
    def _assert_no_symlink_components(path: Path, label: str) -> None:
        absolute = path.absolute()
        components = [absolute, *absolute.parents]
        for component in components:
            if component.is_symlink():
                raise ValueError(f"{label} contains a symlink component: {component}")

    def _require_directory(
        self,
        path: Path,
        *,
        expected_parent: Path | None,
        label: str,
    ) -> Path:
        self._assert_no_symlink_components(path, label)
        if not path.is_dir():
            raise FileNotFoundError(f"{label} is not an available directory: {path}")
        resolved = path.resolve(strict=True)
        if expected_parent is not None and resolved.parent != expected_parent:
            raise ValueError(
                f"{label} escaped its exact expected parent {expected_parent}: {resolved}"
            )
        return resolved

    def _require_file(
        self,
        path: Path,
        *,
        expected_parent: Path,
        label: str,
    ) -> Path:
        self._assert_no_symlink_components(path, label)
        if not path.is_file():
            raise FileNotFoundError(f"{label} is not an available regular file: {path}")
        resolved = path.resolve(strict=True)
        if resolved.parent != expected_parent:
            raise ValueError(
                f"{label} escaped its exact expected directory {expected_parent}: "
                f"{resolved}"
            )
        return resolved

    def _optional_text_path(self, case_id: str) -> Path | None:
        path = self.pdf_dir / f"{case_id}.txt"
        self._assert_no_symlink_components(path, f"Extracted text for case {case_id}")
        if not path.exists():
            return None
        return self._require_file(
            path,
            expected_parent=self.pdf_dir,
            label=f"Extracted text for case {case_id}",
        )

    def _pdf_path(self, case_id: str) -> Path:
        return self._require_file(
            self.pdf_dir / f"{case_id}.pdf",
            expected_parent=self.pdf_dir,
            label=f"PDF for case {case_id}",
        )

    def _validate_research_identity(
        self,
        research: dict[str, Any],
        research_path: Path,
    ) -> None:
        identity = research.get("doc_type")
        if isinstance(identity, str):
            if identity != self.config.doc_type:
                raise ValueError(
                    "Research doc_type mismatch: "
                    f"expected {self.config.doc_type!r}, got {identity!r}"
                )
            return
        if identity is not None:
            raise ValueError("Research doc_type identity must be a string")

        manifest_path = self.doc_dir / "pipeline_manifest.json"
        manifest_file = self._require_file(
            manifest_path,
            expected_parent=self.doc_dir,
            label="Canonical pipeline manifest for identity-less research",
        )
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("doc_type") != self.config.doc_type:
            raise ValueError(
                "Identity-less research lacks a matching canonical pipeline manifest"
            )
        expected_hash = None
        for key in ("research_sha256", "research_hash"):
            if isinstance(manifest.get(key), str):
                expected_hash = manifest[key]
                break
        for container_key in ("input_hashes", "inputs", "artifacts"):
            container = manifest.get(container_key)
            if not isinstance(container, dict):
                continue
            binding = container.get("research/research.json")
            if isinstance(binding, str):
                expected_hash = binding
                break
            if isinstance(binding, dict) and isinstance(binding.get("sha256"), str):
                expected_hash = binding["sha256"]
                break
        actual_hash = _bytes_hash(research_path)
        if (
            not isinstance(expected_hash, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_hash)
            or expected_hash != actual_hash
        ):
            raise ValueError(
                "Identity-less research is not hash-bound by its canonical "
                "pipeline manifest"
            )

    def _write_pipeline_state(
        self,
        status: Literal["running", "completed", "blocked", "cancelled"],
        *,
        error: str | None = None,
    ) -> None:
        atomic_write_json(
            self.pipeline_state_path,
            {
                "schema_version": "document-pipeline-state-v1",
                "run_id": self.config.run_id,
                "doc_type": self.config.doc_type,
                "status": status,
                "stage": self.current_stage,
                "completed_stages": list(self.completed_stages),
                "heartbeat_sequence": self.store.sequence,
                "error": error,
            },
        )

    def _stage_path(self, stage: str) -> Path:
        return self.artifacts_dir / f"{stage}.json"

    def _state_stage_path(self, stage: str) -> Path:
        return self.store.stages_dir / f"{stage.replace(':', '_')}.json"

    def _begin_stage(
        self,
        stage: str,
        input_hash: str,
        expected: int,
    ) -> None:
        self.current_stage = stage
        self.current_input_hash = input_hash
        self.store.transition_stage(stage, status="in_progress")
        timeout_seconds = self._model_stage_timeout(stage)
        self.store.manifest.deadline = (
            time.time()
            + timeout_seconds
            + self.config.stage_cleanup_grace_seconds
            if timeout_seconds is not None
            else None
        )
        self.store._save_manifest()
        atomic_write_json(
            self._state_stage_path(stage),
            StageManifest(
                stage=stage,
                status="in_progress",
                input_hash=input_hash,
                started_at=_utc_now(),
            ),
        )
        self.store.heartbeat(
            stage=stage,
            item="stage:start",
            completed=0,
            expected=expected,
        )
        self._write_pipeline_state("running")

    def _heartbeat(
        self,
        stage: str,
        item: str,
        completed: int,
        expected: int,
        attempt: int | None = None,
    ) -> None:
        self.store.heartbeat(
            stage=stage,
            item=item,
            completed=completed,
            expected=expected,
            attempt=attempt,
        )
        self._write_pipeline_state("running")

    @staticmethod
    def _model_stage_timeout(stage: str) -> float | None:
        if stage.endswith("workers"):
            return _WORKER_STAGE_TIMEOUT_SECONDS
        if stage.endswith("judge"):
            return _JUDGE_STAGE_TIMEOUT_SECONDS
        if stage == "optimizer":
            return _OPTIMIZER_STAGE_TIMEOUT_SECONDS
        return None

    def _model_call(
        self,
        call: Callable[[], dict[str, Any]],
        *,
        stage: str,
        item: str,
        completed: int,
        expected: int,
        attempt: int = 1,
    ) -> dict[str, Any]:
        self.live_sessions += 1
        self.max_live_sessions = max(self.max_live_sessions, self.live_sessions)
        if self.live_sessions > 1:
            raise RuntimeError("Document pipeline attempted overlapping model sessions")
        result: dict[str, Any] | None = None
        primary_error: BaseException | None = None
        try:
            try:
                with self.store.periodic_heartbeat(
                    stage=stage,
                    item=item,
                    completed=completed,
                    expected=expected,
                    attempt=attempt,
                    interval_seconds=self.config.heartbeat_interval_seconds,
                ):
                    self._write_pipeline_state("running")
                    result = call()
            except BaseException as error:
                primary_error = error

            reconciliation_error: AgentRuntimeError | None = None
            reconciliation_cause: BaseException | None = None
            try:
                self.store.wait_for_verified_descendants(
                    self.config.stage_cleanup_grace_seconds,
                    min(self.config.heartbeat_interval_seconds, 0.1),
                )
            except DescendantExitTimeoutError:
                cleanup = None
                try:
                    cleanup = self.store.terminate_verified_processes(
                        include_owner=False,
                        grace_period_seconds=(
                            self.config.stage_cleanup_grace_seconds
                        ),
                    )
                    self.store.wait_for_verified_descendants(
                        self.config.stage_cleanup_grace_seconds,
                        0.1,
                    )
                except DescendantExitTimeoutError as error:
                    reconciliation_error = AgentLifecycleError(
                        "Registered SDK descendants survived forced reconciliation"
                    )
                    reconciliation_cause = error
                except BaseException as error:
                    reconciliation_error = AgentLifecycleError(
                        "Registered SDK descendant termination failed"
                    )
                    reconciliation_cause = error
                else:
                    reconciliation_error = AgentTimeoutError(
                        "Registered SDK descendants exceeded the stage cleanup "
                        "deadline"
                    )
                if cleanup is not None and cleanup.remaining_pids:
                    reconciliation_error = AgentLifecycleError(
                        "Registered SDK descendants remain unreconciled"
                    )
                    reconciliation_cause = None
            except BaseException as error:
                reconciliation_error = AgentLifecycleError(
                    "Registered SDK descendant reconciliation failed"
                )
                reconciliation_cause = error

            if reconciliation_error is not None:
                if primary_error is not None:
                    raise reconciliation_error from primary_error
                if reconciliation_cause is not None:
                    raise reconciliation_error from reconciliation_cause
                raise reconciliation_error
            if primary_error is not None:
                raise primary_error
            if result is None:
                raise AgentLifecycleError("Model turn returned no result")
            return result
        finally:
            self.live_sessions -= 1

    def _load_reusable(
        self,
        stage: str,
        input_manifest: dict[str, Any],
        validator: Callable[[Any], None],
    ) -> Any | None:
        input_hash = _canonical_hash(input_manifest)
        if not self.store.can_reuse(stage, input_hash):
            return None
        try:
            stage_manifest = StageManifest.model_validate_json(
                self._state_stage_path(stage).read_text(encoding="utf-8")
            )
            artifact = json.loads(self._stage_path(stage).read_text(encoding="utf-8"))
            if not isinstance(artifact, dict) or set(artifact) != {
                "schema_version",
                "stage",
                "doc_type",
                "input_manifest",
                "input_hash",
                "output",
                "output_hash",
            }:
                return None
            if (
                artifact["schema_version"] != "document-pipeline-artifact-v1"
                or artifact["stage"] != stage
                or artifact["doc_type"] != self.config.doc_type
                or artifact["input_manifest"] != input_manifest
                or artifact["input_hash"] != input_hash
            ):
                return None
            output = artifact["output"]
            output_hash = _canonical_hash(output)
            if (
                artifact["output_hash"] != output_hash
                or stage_manifest.output_hash != output_hash
                or self.store.manifest.output_hashes.get(stage) != output_hash
                or self.store.manifest.input_hashes.get(stage) != input_hash
            ):
                return None
            validator(output)
        except (OSError, ValueError, TypeError, KeyError, AgentRuntimeError):
            return None
        self.current_stage = stage
        self.current_input_hash = input_hash
        self.completed_stages.append(stage)
        self.store.heartbeat(
            stage=stage,
            item="stage:reused",
            completed=1,
            expected=1,
        )
        return output

    def _import_reusable_model_output(
        self,
        stage: str,
        input_manifest: dict[str, Any],
        validator: Callable[[Any], None],
        *,
        expected: int,
    ) -> Any | None:
        """Refuse mutable model artifacts that have no committed trust anchor."""
        del stage, input_manifest, validator, expected
        return None

    def _run_stage(
        self,
        stage: str,
        input_manifest: dict[str, Any],
        *,
        expected: int,
        produce: Callable[[], Any],
        validate: Callable[[Any], None],
    ) -> Any:
        reused = self._load_reusable(stage, input_manifest, validate)
        if reused is not None:
            return reused
        imported = self._import_reusable_model_output(
            stage,
            input_manifest,
            validate,
            expected=expected,
        )
        if imported is not None:
            return imported

        input_hash = _canonical_hash(input_manifest)
        self._begin_stage(stage, input_hash, expected)
        output = produce()
        validate(output)
        output_hash = _canonical_hash(output)
        artifact = {
            "schema_version": "document-pipeline-artifact-v1",
            "stage": stage,
            "doc_type": self.config.doc_type,
            "input_manifest": input_manifest,
            "input_hash": input_hash,
            "output": output,
            "output_hash": output_hash,
        }
        atomic_write_json(self._stage_path(stage), artifact)
        persisted = json.loads(self._stage_path(stage).read_text(encoding="utf-8"))
        if persisted != artifact:
            raise RuntimeError(f"Atomic artifact verification failed for {stage}")
        validate(persisted["output"])
        self.store.complete_stage(stage, input_hash, output_hash)
        self.completed_stages.append(stage)
        self._heartbeat(stage, "stage:completed", expected, expected)
        return output

    def _load_inputs(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any],
    ]:
        self.pipeline_root = self._require_directory(
            self.pipeline_root_input,
            expected_parent=None,
            label="Pipeline root",
        )
        self.doc_dir = self._require_directory(
            self.pipeline_root / self.config.doc_type,
            expected_parent=self.pipeline_root,
            label=f"Selected {self.config.doc_type} document pipeline",
        )
        self.ground_truth_dir = self._require_directory(
            self.doc_dir / "ground_truth",
            expected_parent=self.doc_dir,
            label="Ground-truth directory",
        )
        self.pdf_dir = self._require_directory(
            self.ground_truth_dir / "pdfs",
            expected_parent=self.ground_truth_dir,
            label="Ground-truth PDF directory",
        )
        self.research_dir = self._require_directory(
            self.doc_dir / "research",
            expected_parent=self.doc_dir,
            label="Research directory",
        )
        ground_truth_path = self._require_file(
            self.ground_truth_dir / "ground_truth.json",
            expected_parent=self.ground_truth_dir,
            label="Ground-truth input",
        )
        research_path = self._require_file(
            self.research_dir / "research.json",
            expected_parent=self.research_dir,
            label="Research input",
        )
        cases = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        research = json.loads(research_path.read_text(encoding="utf-8"))
        if not isinstance(cases, list) or not cases:
            raise ValueError("ground_truth.json must contain a non-empty case list")
        if not isinstance(research, dict):
            raise ValueError("research.json must contain an object")
        self._validate_research_identity(research, research_path)

        case_map: dict[str, dict[str, Any]] = {}
        for case in cases:
            if not isinstance(case, dict):
                raise ValueError("Every ground-truth case must be an object")
            case_id = case.get("opaque_case_id")
            sibling_id = case.get("sibling_case_id")
            if (
                not isinstance(case_id, str)
                or not _CASE_ID.fullmatch(case_id)
                or not isinstance(sibling_id, str)
                or not _CASE_ID.fullmatch(sibling_id)
            ):
                raise ValueError("Case and sibling IDs must be opaque 32-hex values")
            if case_id in case_map:
                raise ValueError(f"Duplicate case ID: {case_id}")
            if case.get("doc_type") != self.config.doc_type:
                raise ValueError(f"Cross-document case found in {self.config.doc_type}")
            pdf_path = self._pdf_path(case_id)
            actual_pdf_hash = _bytes_hash(pdf_path)
            expected_pdf_hash = case.get("pdf_sha256")
            if expected_pdf_hash is not None and expected_pdf_hash != actual_pdf_hash:
                raise ValueError(f"PDF hash mismatch for case {case_id}")
            case = dict(case)
            case["pdf_sha256"] = actual_pdf_hash
            case_map[case_id] = case

        for case_id, case in case_map.items():
            sibling = case_map.get(case["sibling_case_id"])
            if sibling is None or sibling.get("sibling_case_id") != case_id:
                raise ValueError(f"Broken sibling link for case {case_id}")

        ordered_cases = [case_map[case_id] for case_id in sorted(case_map)]
        training, holdout = split_doc_type_cases(
            ordered_cases,
            doc_type=self.config.doc_type,
        )
        return ordered_cases, training, holdout, research

    def _resolve_source(self) -> tuple[str, Path]:
        self.source_root = self._require_directory(
            self.source_root_input,
            expected_parent=None,
            label="Source root",
        )
        skills_root = self._require_directory(
            self.source_root / "skills",
            expected_parent=self.source_root,
            label="Skills directory",
        )
        self.document_skills_dir = self._require_directory(
            skills_root / "document-agents",
            expected_parent=skills_root,
            label="Document skills directory",
        )
        pdf_skills_dir = self._require_directory(
            skills_root / "pdf",
            expected_parent=skills_root,
            label="Shared PDF skill directory",
        )
        self.shared_skill_path = self._require_file(
            pdf_skills_dir / "SKILL.md",
            expected_parent=pdf_skills_dir,
            label="Shared PDF review contract",
        )
        stem = DOC_TYPE_TO_SKILL.get(
            self.config.doc_type,
            self.config.doc_type.replace("_", "-"),
        )
        target_file = f"skills/document-agents/{stem}.md"
        allowed, reasons, normalized = validate_target_allowlist(
            target_file,
            self.config.doc_type,
        )
        if not allowed:
            raise ValueError("; ".join(reasons))
        source_path = self._require_file(
            self.document_skills_dir / f"{stem}.md",
            expected_parent=self.document_skills_dir,
            label="Canonical source target",
        )
        if source_path != (self.source_root / normalized).resolve():
            raise ValueError("Canonical source target does not match its allowlisted path")
        return normalized, source_path

    def _build_bundle(self, candidate_content: str | None = None) -> dict[str, Any]:
        try:
            bundle = build_public_review_bundle(
                self.config.doc_type,
                corpus_db_path=self.corpus_db_path,
                skills_dir=self.document_skills_dir,
                override_skill_content=candidate_content,
                shared_skill_path=self.shared_skill_path,
            )
        except PublicBundleValidationError as error:
            if candidate_content is None:
                raise
            raise CandidateBundleValidationError(str(error)) from error
        if (
            not isinstance(bundle, dict)
            or set(bundle) != {"doc_type", "content", "bundle_hash"}
            or bundle.get("doc_type") != self.config.doc_type
            or not isinstance(bundle.get("content"), str)
            or not isinstance(bundle.get("bundle_hash"), str)
            or bundle["bundle_hash"]
            != hashlib.sha256(bundle["content"].encode("utf-8")).hexdigest()
        ):
            error = CandidateBundleValidationError(
                "Public review bundle schema/hash validation failed"
            )
            if candidate_content is not None:
                raise error
            raise PublicBundleValidationError(str(error))
        return bundle

    def _build_shared_bundle(self, shared_content: str) -> dict[str, Any]:
        try:
            bundle = build_public_review_bundle(
                self.config.doc_type,
                corpus_db_path=self.corpus_db_path,
                skills_dir=self.document_skills_dir,
                shared_skill_path=self.shared_skill_path,
                override_shared_content=shared_content,
            )
        except PublicBundleValidationError as error:
            raise CandidateBundleValidationError(str(error)) from error
        if (
            not isinstance(bundle, dict)
            or set(bundle) != {"doc_type", "content", "bundle_hash"}
            or bundle.get("doc_type") != self.config.doc_type
            or not isinstance(bundle.get("content"), str)
            or bundle.get("bundle_hash")
            != hashlib.sha256(bundle["content"].encode("utf-8")).hexdigest()
        ):
            raise CandidateBundleValidationError(
                "Shared candidate public bundle schema/hash validation failed"
            )
        return bundle

    def _case_inputs(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        inputs: list[dict[str, Any]] = []
        for case in sorted(cases, key=lambda item: item["opaque_case_id"]):
            case_id = case["opaque_case_id"]
            pdf_path = self._pdf_path(case_id)
            text_path = self._optional_text_path(case_id)
            inputs.append(
                {
                    "case_id": case_id,
                    "pdf_sha256": _bytes_hash(pdf_path),
                    "allowed_text_sha256": (
                        _bytes_hash(text_path) if text_path is not None else None
                    ),
                }
            )
        return inputs

    def _worker_manifest(
        self,
        stage: str,
        cases: list[dict[str, Any]],
        bundle: dict[str, Any],
        *,
        selection: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": "document-worker-stage-v1",
            "stage": stage,
            "doc_type": self.config.doc_type,
            "source_revision": self.config.source_revision,
            "selection": selection,
            "cases": self._case_inputs(cases),
            "bundle_hash": bundle["bundle_hash"],
            "bundle_content_hash": hashlib.sha256(
                bundle["content"].encode("utf-8")
            ).hexdigest(),
            "corpus_db_sha256": _bytes_hash(self.corpus_db_path),
            "runtime_mode": (
                "injected-test-runner"
                if self.config.runtime is not None
                else "copilot-sdk"
            ),
            "model_config": {
                "role": "worker",
                "model": "gemini-3.6-flash",
                "effort": None,
                "context_tier": "long_context",
                "timeout_seconds": 600,
            },
        }

    def _validate_runtime_provenance(
        self,
        provenance: Any,
        *,
        role: str,
        model: str,
        effort: str | None,
        attachment_hashes: list[str],
        extra_fields: tuple[str, ...],
        required_hash_fields: tuple[str, ...],
        optional_hash_fields: tuple[str, ...] = (),
        required_hash_list_fields: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if not isinstance(provenance, dict):
            raise ValueError(f"{role} artifact lacks provenance")
        expected_engine = (
            "injected-test-runner"
            if self.config.runtime is not None
            else "copilot-sdk"
        )
        validate_persisted_agent_provenance(
            provenance,
            expected_engine=expected_engine,
            expected_is_live=self.config.runtime is None,
            role=role,
            model=model,
            effort=effort,
            context_tier="long_context",
            prompt_hash=provenance.get("prompt_hash"),
            attachment_hashes=attachment_hashes,
            output_hash=provenance.get("output_hash"),
            extra_digest_fields=extra_fields,
            required_hash_fields=required_hash_fields,
            optional_hash_fields=optional_hash_fields,
            required_hash_list_fields=required_hash_list_fields,
        )
        return provenance

    def _validate_worker_reports(
        self,
        reports: Any,
        cases: list[dict[str, Any]],
        bundle: dict[str, Any],
    ) -> None:
        if not isinstance(reports, dict):
            raise ValueError("Worker stage output must be an object")
        case_map = {case["opaque_case_id"]: case for case in cases}
        if set(reports) != set(case_map):
            raise ValueError("Worker stage output does not exactly cover its cases")
        for case_id, case in case_map.items():
            report = reports[case_id]
            if (
                not isinstance(report, dict)
                or report.get("case_id") != case_id
                or report.get("doc_type") != self.config.doc_type
            ):
                raise ValueError(f"Invalid Worker report identity for {case_id}")
            _validate_answer_object(report)
            check_answer_grounding(report, db_path=self.corpus_db_path)
            pdf_path = self._pdf_path(case_id)
            text_path = self._optional_text_path(case_id)
            extracted_text = (
                text_path.read_text(encoding="utf-8", errors="replace")
                if text_path is not None
                else ""
            )
            expected_text_hash = (
                _bytes_hash(text_path) if text_path is not None else None
            )
            pii_manifest = _build_parent_pii_manifest(
                pdf_path=pdf_path,
                extracted_text=extracted_text,
                pipeline_root=self.pdf_dir,
                case_id=case_id,
            )
            _assert_answer_blindness_and_pii(
                report,
                pii_manifest=pii_manifest,
            )
            expected_prompt_hash = hashlib.sha256(
                _build_worker_prompt(
                    doc_type=self.config.doc_type,
                    public_bundle=bundle,
                    extracted_text=extracted_text,
                ).encode("utf-8")
            ).hexdigest()
            provenance = self._validate_runtime_provenance(
                report.get("_provenance"),
                role="worker",
                model="gemini-3.6-flash",
                effort=None,
                attachment_hashes=[case["pdf_sha256"]],
                extra_fields=_WORKER_PROVENANCE_EXTRA_FIELDS,
                required_hash_fields=(
                    "input_pdf_sha256",
                    "bundle_hash",
                    "answer_hash",
                    "pii_manifest_hash",
                ),
                optional_hash_fields=("allowed_text_sha256",),
            )
            answer = {
                field: report[field]
                for field in ("question", "claims", "basis", "abstentions", "prose")
            }
            if (
                provenance["input_pdf_sha256"] != case["pdf_sha256"]
                or provenance["bundle_hash"] != bundle["bundle_hash"]
                or provenance["allowed_text_sha256"] != expected_text_hash
                or provenance["prompt_hash"] != expected_prompt_hash
                or provenance["answer_hash"] != _canonical_hash(answer)
                or provenance["pii_manifest_hash"]
                != pii_manifest.manifest_hash
                or provenance["pii_manifest_count"] != pii_manifest.count
                or provenance["pii_manifest_categories"]
                != pii_manifest.category_summary
                or provenance["provenance_digest"]
                != _worker_provenance_digest(provenance)
            ):
                raise ValueError(f"Worker provenance binding mismatch for {case_id}")

    def _produce_workers(
        self,
        stage: str,
        cases: list[dict[str, Any]],
        bundle: dict[str, Any],
    ) -> dict[str, Any]:
        reports: dict[str, Any] = {}
        expected = len(cases)
        for index, case in enumerate(
            sorted(cases, key=lambda item: item["opaque_case_id"])
        ):
            case_id = case["opaque_case_id"]
            self._pdf_path(case_id)
            self._optional_text_path(case_id)
            self._heartbeat(stage, case_id, index, expected)
            reports[case_id] = self._model_call(
                lambda case_id=case_id: run_blind_worker_task(
                    opaque_case_id=case_id,
                    doc_type=self.config.doc_type,
                    public_bundle=bundle,
                    pipeline_root=self.pdf_dir,
                    corpus_db_path=self.corpus_db_path,
                    runtime=self.config.runtime,
                    descendant_registrar=(
                        self.store.add_descendant_pid
                        if self.store is not None
                        else None
                    ),
                ),
                stage=stage,
                item=case_id,
                completed=index,
                expected=expected,
            )
            self._heartbeat(stage, case_id, index + 1, expected)
        return reports

    def _judge_inputs(
        self,
        reports: dict[str, dict[str, Any]],
        cases: list[dict[str, Any]],
        research: dict[str, Any],
        bundle: dict[str, Any],
    ) -> tuple[
        list[Path],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, Any],
        str,
    ]:
        ordered_ids = sorted(case["opaque_case_id"] for case in cases)
        pdf_paths = [self._pdf_path(case_id) for case_id in ordered_ids]
        ground_truth = {
            case["opaque_case_id"]: case
            for case in sorted(cases, key=lambda item: item["opaque_case_id"])
        }
        worker_inputs: dict[str, dict[str, Any]] = {}
        for case_id, pdf_path in zip(ordered_ids, pdf_paths):
            text_path = self._optional_text_path(case_id)
            extracted_text = (
                text_path.read_text(encoding="utf-8", errors="replace")
                if text_path is not None
                else ""
            )
            worker_inputs[case_id] = build_worker_input_manifest(
                doc_type=self.config.doc_type,
                public_bundle=bundle,
                input_pdf_sha256=_bytes_hash(pdf_path),
                extracted_text=extracted_text,
                allowed_text_sha256=(
                    _bytes_hash(text_path) if text_path is not None else None
                ),
            )
        judge_manifest, judge_hash = build_judge_input_manifest(
            doc_type=self.config.doc_type,
            case_ids=ordered_ids,
            pdf_hashes_by_case={
                path.stem: _bytes_hash(path) for path in pdf_paths
            },
            worker_reports=reports,
            worker_input_manifests=worker_inputs,
            research_json=research,
            ground_truth_specs=ground_truth,
        )
        return pdf_paths, ground_truth, worker_inputs, judge_manifest, judge_hash

    def _judge_manifest(
        self,
        stage: str,
        reports: dict[str, dict[str, Any]],
        cases: list[dict[str, Any]],
        research: dict[str, Any],
        bundle: dict[str, Any],
        *,
        selection: str,
    ) -> dict[str, Any]:
        _, _, _, judge_manifest, judge_hash = self._judge_inputs(
            reports,
            cases,
            research,
            bundle,
        )
        return {
            "schema_version": "document-judge-stage-v1",
            "stage": stage,
            "doc_type": self.config.doc_type,
            "source_revision": self.config.source_revision,
            "selection": selection,
            "judge_input_manifest": judge_manifest,
            "judge_input_manifest_hash": judge_hash,
            "runtime_mode": (
                "injected-test-runner"
                if self.config.runtime is not None
                else "copilot-sdk"
            ),
        }

    def _validate_judge(
        self,
        output: Any,
        reports: dict[str, dict[str, Any]],
        cases: list[dict[str, Any]],
        research: dict[str, Any],
        bundle: dict[str, Any],
    ) -> None:
        if not isinstance(output, dict):
            raise ValueError("Judge output must be an object")
        artifact = {key: value for key, value in output.items() if key != "_provenance"}
        batch = JudgeEvaluationBatch.model_validate(artifact)
        expected_ids = sorted(case["opaque_case_id"] for case in cases)
        if batch.doc_type != self.config.doc_type or set(
            batch.case_evaluations
        ) != set(expected_ids):
            raise ValueError("Judge output identity or coverage mismatch")
        for finding in batch.findings:
            if finding.case_id not in expected_ids:
                raise ValueError("Judge finding references an out-of-scope case")

        (
            pdf_paths,
            ground_truth,
            worker_inputs,
            manifest,
            manifest_hash,
        ) = self._judge_inputs(
            reports,
            cases,
            research,
            bundle,
        )
        expected_prompt_hash = hashlib.sha256(
            _build_judge_prompt(
                doc_type=self.config.doc_type,
                case_ids=expected_ids,
                worker_reports=reports,
                worker_input_manifests=worker_inputs,
                research_json=research,
                ground_truth_specs=ground_truth,
                input_manifest_hash=manifest_hash,
                prompt_contract_hash=manifest["prompt_contract_hash"],
            ).encode("utf-8")
        ).hexdigest()
        provenance = self._validate_runtime_provenance(
            output.get("_provenance"),
            role="judge",
            model="claude-opus-4.8",
            effort="xhigh",
            attachment_hashes=[_bytes_hash(path) for path in pdf_paths],
            extra_fields=_JUDGE_PROVENANCE_EXTRA_FIELDS,
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
        for key in (
            "prompt_contract_hash",
            "case_ids",
            "pdf_hashes",
            "worker_report_hashes",
            "worker_input_manifest_hashes",
            "public_bundle_hashes",
            "worker_prompt_hashes",
            "research_hash",
            "ground_truth_hash",
            "model_config",
        ):
            if provenance.get(key) != manifest.get(key):
                raise ValueError(f"Judge provenance {key} mismatch")
        if (
            provenance["input_manifest_hash"] != manifest_hash
            or provenance["prompt_hash"] != expected_prompt_hash
            or provenance["artifact_output_hash"] != _canonical_hash(artifact)
            or provenance["provenance_digest"]
            != _judge_provenance_digest(provenance)
        ):
            raise ValueError("Judge provenance binding mismatch")

    def _produce_judge(
        self,
        stage: str,
        reports: dict[str, dict[str, Any]],
        cases: list[dict[str, Any]],
        research: dict[str, Any],
        bundle: dict[str, Any],
    ) -> dict[str, Any]:
        pdf_paths, ground_truth, _, _, _ = self._judge_inputs(
            reports,
            cases,
            research,
            bundle,
        )
        self._heartbeat(stage, self.config.doc_type, 0, 1)
        output = self._model_call(
            lambda: run_batched_document_judge(
                doc_type=self.config.doc_type,
                worker_reports=reports,
                pdf_paths=pdf_paths,
                research_json=research,
                ground_truth_specs=ground_truth,
                public_bundle=bundle,
                runtime=self.config.runtime,
                descendant_registrar=(
                    self.store.add_descendant_pid
                    if self.store is not None
                    else None
                ),
            ),
            stage=stage,
            item=self.config.doc_type,
            completed=0,
            expected=1,
        )
        self._heartbeat(stage, self.config.doc_type, 1, 1)
        return output

    def _optimizer_manifest(
        self,
        sealed_findings: dict[str, Any],
    ) -> dict[str, Any]:
        committed_input = _build_optimizer_training_input(sealed_findings)
        optimizer_input = _build_optimizer_model_input(committed_input)
        return {
            "schema_version": "document-optimizer-stage-v1",
            "stage": "optimizer",
            "doc_type": self.config.doc_type,
            "source_revision": self.config.source_revision,
            "target_file": self.target_file,
            "source_hash": self.source_hash,
            "training_input": optimizer_input,
            "training_input_hash": _canonical_hash(optimizer_input),
            "holdout_commitment": committed_input["holdout_commitment"],
            "runtime_mode": (
                "injected-test-runner"
                if self.config.runtime is not None
                else "copilot-sdk"
            ),
            "model_config": {
                "role": "optimizer",
                "model": "gemini-3.6-flash",
                "effort": None,
                "context_tier": "long_context",
                "timeout_seconds": 300,
            },
        }

    def _candidate_path(self, candidate: dict[str, Any]) -> Path:
        candidate_id = candidate.get("candidate_id")
        target_file = candidate.get("target_file")
        if (
            not isinstance(candidate_id, str)
            or not _CANDIDATE_ID.fullmatch(candidate_id)
            or target_file != self.target_file
        ):
            raise CandidateBundleValidationError(
                "Candidate identity or target path is invalid"
            )
        candidate_dir = self.proposal_root / candidate_id
        self._assert_no_symlink_components(candidate_dir, "Candidate proposal directory")
        candidate_path = candidate_dir / target_file
        self._assert_no_symlink_components(candidate_path, "Candidate proposal artifact")
        resolved = candidate_path.resolve()
        expected_root = candidate_dir.resolve()
        if not resolved.is_relative_to(expected_root):
            raise CandidateBundleValidationError(
                "Candidate proposal artifact escaped its exact candidate directory"
            )
        return resolved

    def _validate_optimizer(
        self,
        output: Any,
        sealed_findings: dict[str, Any],
    ) -> None:
        if not isinstance(output, dict):
            raise ValueError("Optimizer output must be an object")
        if (
            output.get("target_file") != self.target_file
            or not isinstance(output.get("candidate_content"), str)
            or type(output.get("is_valid")) is not bool
            or not isinstance(output.get("rejection_reasons"), list)
        ):
            raise ValueError("Optimizer output has invalid candidate fields")
        raw_output = output.get("_optimizer_output")
        if not isinstance(raw_output, str):
            raise ValueError("Optimizer raw output is missing")
        proposal = OptimizerProposal.model_validate_json(raw_output)
        if (
            proposal.target_file != output["target_file"]
            or proposal.candidate_content != output["candidate_content"]
            or proposal.rationale != output.get("rationale")
        ):
            raise ValueError("Optimizer proposal and candidate differ")
        candidate_hash = hashlib.sha256(
            output["candidate_content"].encode("utf-8")
        ).hexdigest()
        provenance = self._validate_runtime_provenance(
            output.get("_provenance"),
            role="optimizer",
            model="gemini-3.6-flash",
            effort=None,
            attachment_hashes=[],
            extra_fields=_OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
            required_hash_fields=(
                "input_findings_sha256",
                "candidate_content_hash",
            ),
        )
        committed_input = _build_optimizer_training_input(sealed_findings)
        optimizer_input = _build_optimizer_model_input(committed_input)
        expected_findings_hash = _canonical_hash(optimizer_input)
        expected_candidate_id = derive_optimizer_candidate_id(
            expected_findings_hash,
            provenance["prompt_hash"],
            self.target_file or "",
        )
        if (
            provenance["input_findings_sha256"] != expected_findings_hash
            or provenance["candidate_content_hash"] != candidate_hash
            or provenance["candidate_id"] != output.get("candidate_id")
            or output.get("candidate_id") != expected_candidate_id
            or provenance["target_file"] != self.target_file
            or provenance["output_hash"]
            != hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
            or output.get("_holdout_commitment")
            != committed_input["holdout_commitment"]
        ):
            raise ValueError("Optimizer provenance binding mismatch")
        patch_valid, reasons = validate_patch_allowlist(
            output["candidate_content"],
            self.target_file or "",
            doc_type=self.config.doc_type,
            current_content=self.source_content,
            forbidden_private_texts=(
                finding["description"]
                for finding in optimizer_input["findings"]
                if "description" in finding
            ),
        )
        if patch_valid != output["is_valid"] or reasons != output["rejection_reasons"]:
            raise ValueError("Optimizer allowlist result is not reproducible")
        if output["is_valid"]:
            candidate_path = self._candidate_path(output)
            if (
                not candidate_path.is_relative_to(self.proposal_root)
                or not candidate_path.is_file()
                or _bytes_hash(candidate_path) != candidate_hash
            ):
                raise ValueError("Optimizer candidate artifact is missing or changed")

    def _produce_optimizer(
        self,
        sealed_findings: dict[str, Any],
    ) -> dict[str, Any]:
        self._heartbeat("optimizer", self.target_file or "candidate", 0, 1)
        output = self._model_call(
            lambda: run_candidate_optimization_pass(
                doc_type=None,
                training_findings=sealed_findings,
                current_skills={self.target_file or "": self.source_content},
                proposal_sandbox_root=self.proposal_root,
                target_file=self.target_file,
                runtime=self.config.runtime,
                descendant_registrar=(
                    self.store.add_descendant_pid
                    if self.store is not None
                    else None
                ),
            ),
            stage="optimizer",
            item=self.target_file or "candidate",
            completed=0,
            expected=1,
        )
        self._heartbeat("optimizer", self.target_file or "candidate", 1, 1)
        return output

    def _mean_metrics(
        self,
        batch: dict[str, Any],
        case_ids: set[str],
    ) -> dict[str, float]:
        evaluations = batch.get("case_evaluations")
        if not isinstance(evaluations, dict) or not case_ids:
            raise ValueError("Metric aggregation requires non-empty exact evaluations")
        if not case_ids.issubset(evaluations):
            raise ValueError("Metric aggregation is missing case evaluations")
        result: dict[str, float] = {}
        for field_name in _SCORE_FIELDS:
            values: list[float] = []
            for case_id in sorted(case_ids):
                score = evaluations[case_id]
                value = score.get(field_name) if isinstance(score, dict) else None
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                ):
                    raise ValueError(
                        f"Judge metric {field_name} for {case_id} is invalid"
                    )
                values.append(float(value))
            result[field_name] = sum(values) / len(values)
        result["overall_score"] = sum(result.values()) / len(result)
        return result

    def _decision_output(
        self,
        optimizer: dict[str, Any],
        baseline_judge: dict[str, Any],
        candidate_judge: dict[str, Any] | None,
        training_ids: set[str],
        holdout_ids: set[str],
        candidate_bundle_error: str | None = None,
        candidate_evaluation_error: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        candidate_content = optimizer["candidate_content"]
        candidate_hash = hashlib.sha256(candidate_content.encode("utf-8")).hexdigest()
        candidate_path = (
            str(self._candidate_path(optimizer)) if optimizer["is_valid"] else None
        )
        if not optimizer["is_valid"]:
            return {
                "status": "rejected",
                "target_file": self.target_file,
                "candidate_id": optimizer["candidate_id"],
                "candidate_path": candidate_path,
                "candidate_content": candidate_content,
                "candidate_content_hash": candidate_hash,
                "source_hash": self.source_hash,
                "metrics": {},
                "evidence": [
                    {
                        "kind": "candidate_validation",
                        "passed": False,
                        "reasons": optimizer["rejection_reasons"],
                    }
                ],
            }
        if candidate_bundle_error is not None:
            return {
                "status": "rejected",
                "target_file": self.target_file,
                "candidate_id": optimizer["candidate_id"],
                "candidate_path": candidate_path,
                "candidate_content": candidate_content,
                "candidate_content_hash": candidate_hash,
                "source_hash": self.source_hash,
                "metrics": {},
                "evidence": [
                    {
                        "kind": "candidate_validation",
                        "passed": True,
                        "reasons": [],
                    },
                    {
                        "kind": "candidate_bundle_validation",
                        "passed": False,
                        "reasons": [candidate_bundle_error],
                    },
                ],
            }
        if candidate_evaluation_error is not None:
            return {
                "status": "rejected",
                "target_file": self.target_file,
                "candidate_id": optimizer["candidate_id"],
                "candidate_path": candidate_path,
                "candidate_content": candidate_content,
                "candidate_content_hash": candidate_hash,
                "source_hash": self.source_hash,
                "metrics": {},
                "evidence": [
                    {
                        "kind": "candidate_validation",
                        "passed": True,
                        "reasons": [],
                    },
                    {
                        "kind": "candidate_evaluation",
                        "passed": False,
                        **candidate_evaluation_error,
                    },
                ],
            }
        if candidate_judge is None:
            raise RuntimeError("Valid candidate was not evaluated")

        if not training_ids:
            metrics = {
                "baseline_holdout": self._mean_metrics(
                    baseline_judge,
                    holdout_ids,
                ),
                "candidate_holdout": self._mean_metrics(
                    candidate_judge,
                    holdout_ids,
                ),
            }
            self.metrics = metrics
            return {
                "status": "rejected",
                "target_file": self.target_file,
                "candidate_id": optimizer["candidate_id"],
                "candidate_path": candidate_path,
                "candidate_content": candidate_content,
                "candidate_content_hash": candidate_hash,
                "source_hash": self.source_hash,
                "metrics": metrics,
                "evidence": [
                    {
                        "kind": "candidate_validation",
                        "passed": True,
                        "reasons": [],
                    },
                    {
                        "kind": "insufficient_training_data",
                        "passed": False,
                        "training_case_count": 0,
                    },
                ],
            }

        metrics = {
            "baseline_train": self._mean_metrics(baseline_judge, training_ids),
            "baseline_holdout": self._mean_metrics(baseline_judge, holdout_ids),
            "candidate_train": self._mean_metrics(candidate_judge, training_ids),
            "candidate_holdout": self._mean_metrics(candidate_judge, holdout_ids),
        }
        accepted = evaluate_candidate_patch(
            metrics["baseline_train"],
            metrics["baseline_holdout"],
            metrics["candidate_train"],
            metrics["candidate_holdout"],
        )
        evidence = [
            {
                "kind": "candidate_validation",
                "passed": True,
                "reasons": [],
            },
            {
                "kind": "metric_gate",
                "evaluator": "evaluate_candidate_patch",
                "passed": accepted,
                "training_overall_improved": (
                    metrics["candidate_train"]["overall_score"]
                    > metrics["baseline_train"]["overall_score"] + 1e-6
                ),
                "training_safety_non_regression": all(
                    metrics["candidate_train"][name]
                    >= metrics["baseline_train"][name] - 1e-6
                    for name in (
                        "grounding_accuracy",
                        "citation_exactness",
                        "pii_containment",
                        "blind_input_compliance",
                    )
                ),
                "holdout_non_regression": all(
                    metrics["candidate_holdout"][name]
                    >= metrics["baseline_holdout"][name] - 1e-6
                    for name in _SCORE_FIELDS
                ),
            },
        ]
        self.metrics = metrics
        return {
            "status": "accepted" if accepted else "rejected",
            "target_file": self.target_file,
            "candidate_id": optimizer["candidate_id"],
            "candidate_path": candidate_path,
            "candidate_content": candidate_content,
            "candidate_content_hash": candidate_hash,
            "source_hash": self.source_hash,
            "metrics": metrics,
            "evidence": evidence,
        }

    def _validate_decision(self, output: Any) -> None:
        if not isinstance(output, dict) or output.get("status") not in {
            "accepted",
            "rejected",
        }:
            raise ValueError("Patch decision must be accepted or rejected")
        if (
            output.get("target_file") != self.target_file
            or not isinstance(output.get("candidate_id"), str)
            or not _CANDIDATE_ID.fullmatch(output["candidate_id"])
            or self.candidate_result is None
            or output["candidate_id"] != self.candidate_result.get("candidate_id")
            or output["candidate_id"]
            != (self.candidate_result.get("_provenance") or {}).get("candidate_id")
            or output.get("source_hash") != self.source_hash
            or not isinstance(output.get("candidate_content"), str)
            or output.get("candidate_content_hash")
            != hashlib.sha256(
                output["candidate_content"].encode("utf-8")
            ).hexdigest()
            or not isinstance(output.get("metrics"), dict)
            or not isinstance(output.get("evidence"), list)
        ):
            raise ValueError("Patch decision evidence is incomplete")
        if output["status"] == "accepted":
            path = Path(output.get("candidate_path", ""))
            if not path.is_file() or _bytes_hash(path) != output["candidate_content_hash"]:
                raise ValueError("Accepted decision lacks an exact candidate artifact")

    def _validate_exact_decision(
        self,
        output: Any,
        *,
        optimizer: dict[str, Any],
        baseline_judge: dict[str, Any],
        candidate_judge: dict[str, Any] | None,
        training_ids: set[str],
        holdout_ids: set[str],
        candidate_bundle_error: str | None,
        candidate_evaluation_error: dict[str, str] | None,
    ) -> None:
        self._validate_decision(output)
        expected = self._decision_output(
            optimizer,
            baseline_judge,
            candidate_judge,
            training_ids,
            holdout_ids,
            candidate_bundle_error,
            candidate_evaluation_error,
        )
        if output != expected:
            raise ValueError("Persisted patch decision does not recompute exactly")

    def _execute_shared_evaluation(
        self,
        cases: list[dict[str, Any]],
        research: dict[str, Any],
    ) -> DocumentPipelineResult:
        phase = self.config.execution_phase
        if phase == "shared_candidate":
            candidate_path = self.config.shared_candidate_path
            if candidate_path is None:
                raise ValueError(
                    "Shared candidate evaluation requires a candidate path"
                )
            candidate_path = Path(candidate_path)
            self._assert_no_symlink_components(
                candidate_path,
                "Shared candidate artifact",
            )
            resolved_candidate = candidate_path.resolve()
            if (
                not resolved_candidate.is_relative_to(self.proposal_root)
                or not resolved_candidate.is_file()
                or resolved_candidate.name != "SKILL.md"
                or tuple(resolved_candidate.parts[-3:-1]) != ("skills", "pdf")
            ):
                raise ValueError(
                    "Shared candidate artifact is outside its proposal sandbox"
                )
            candidate_content = resolved_candidate.read_text(encoding="utf-8")
            evaluation_bundle = self._build_shared_bundle(candidate_content)
            prefix = "shared_candidate"
            selection = "shared-candidate"
            candidate_hash = hashlib.sha256(
                candidate_content.encode("utf-8")
            ).hexdigest()
        else:
            evaluation_bundle = self.baseline_bundle or {}
            prefix = "shared_baseline"
            selection = "post-document-source"
            candidate_hash = None

        worker_stage = f"{prefix}_workers"
        worker_manifest = self._worker_manifest(
            worker_stage,
            cases,
            evaluation_bundle,
            selection=selection,
        )
        worker_manifest["shared_candidate_content_hash"] = candidate_hash
        try:
            workers = self._run_stage(
                worker_stage,
                worker_manifest,
                expected=len(cases),
                produce=lambda: self._produce_workers(
                    worker_stage,
                    cases,
                    evaluation_bundle,
                ),
                validate=lambda output: self._validate_worker_reports(
                    output,
                    cases,
                    evaluation_bundle,
                ),
            )
        except _CANDIDATE_SEMANTIC_ERRORS as error:
            if phase != "shared_candidate":
                raise
            return self._complete_invalid_shared_candidate(
                stage=worker_stage,
                error=error,
                selection=selection,
                evaluation_bundle=evaluation_bundle,
                candidate_hash=candidate_hash,
            )
        judge_stage = f"{prefix}_judge"
        judge_manifest = self._judge_manifest(
            judge_stage,
            workers,
            cases,
            research,
            evaluation_bundle,
            selection=selection,
        )
        judge_manifest["shared_candidate_content_hash"] = candidate_hash
        try:
            self._run_stage(
                judge_stage,
                judge_manifest,
                expected=1,
                produce=lambda: self._produce_judge(
                    judge_stage,
                    workers,
                    cases,
                    research,
                    evaluation_bundle,
                ),
                validate=lambda output: self._validate_judge(
                    output,
                    workers,
                    cases,
                    research,
                    evaluation_bundle,
                ),
            )
        except _CANDIDATE_SEMANTIC_ERRORS as error:
            if phase != "shared_candidate":
                raise
            return self._complete_invalid_shared_candidate(
                stage=judge_stage,
                error=error,
                selection=selection,
                evaluation_bundle=evaluation_bundle,
                candidate_hash=candidate_hash,
                worker_output_hash=_canonical_hash(workers),
            )
        patch = PatchDecision(
            status="rejected",
            target_file=None,
            candidate_id=None,
            candidate_path=None,
            candidate_content="",
            candidate_content_hash=None,
            source_hash=None,
            evidence=[
                {
                    "kind": "shared_candidate_evaluation",
                    "passed": True,
                    "selection": selection,
                }
            ],
        )
        result = DocumentPipelineResult(
            run_id=self.config.run_id,
            doc_type=self.config.doc_type,
            status="completed",
            stages=list(self.completed_stages),
            max_live_sessions=self.max_live_sessions,
            patch=patch,
            baseline_bundle_hash=(self.baseline_bundle or {})["bundle_hash"],
            candidate_bundle_hash=(
                evaluation_bundle["bundle_hash"]
                if phase == "shared_candidate"
                else None
            ),
            final_bundle_hash=evaluation_bundle["bundle_hash"],
        )
        atomic_write_json(self.result_path, asdict(result))
        self.store.transition_stage(judge_stage, status="completed")
        self._write_pipeline_state("completed")
        return result

    def _complete_invalid_shared_candidate(
        self,
        *,
        stage: str,
        error: BaseException,
        selection: str,
        evaluation_bundle: dict[str, Any],
        candidate_hash: str | None,
        worker_output_hash: str | None = None,
    ) -> DocumentPipelineResult:
        failure = {
            "stage": stage,
            "error_type": type(error).__name__,
            "message": str(error),
        }
        skipped = {
            "skipped": True,
            "reason": "shared_candidate_evaluation_invalid",
        }
        manifest: dict[str, Any] = {
            "schema_version": (
                "document-judge-stage-v1"
                if stage.endswith("_judge")
                else "document-worker-stage-v1"
            ),
            "stage": stage,
            "doc_type": self.config.doc_type,
            "selection": "invalid-shared-candidate-evaluation",
            "shared_candidate_content_hash": candidate_hash,
            "failure": failure,
        }
        if worker_output_hash is not None:
            manifest["worker_output_hash"] = worker_output_hash
        self._run_stage(
            stage,
            manifest,
            expected=0,
            produce=lambda: skipped,
            validate=lambda output: (
                None
                if output == skipped
                else (_ for _ in ()).throw(
                    ValueError(
                        "Invalid shared candidate failure artifact"
                    )
                )
            ),
        )
        patch = PatchDecision(
            status="rejected",
            target_file=None,
            candidate_id=None,
            candidate_path=None,
            candidate_content="",
            candidate_content_hash=None,
            source_hash=None,
            evidence=[
                {
                    "kind": "shared_candidate_evaluation",
                    "passed": False,
                    "selection": selection,
                    **failure,
                }
            ],
        )
        result = DocumentPipelineResult(
            run_id=self.config.run_id,
            doc_type=self.config.doc_type,
            status="completed",
            stages=list(self.completed_stages),
            max_live_sessions=self.max_live_sessions,
            patch=patch,
            baseline_bundle_hash=(self.baseline_bundle or {})["bundle_hash"],
            candidate_bundle_hash=evaluation_bundle["bundle_hash"],
            final_bundle_hash=evaluation_bundle["bundle_hash"],
        )
        atomic_write_json(self.result_path, asdict(result))
        self._write_pipeline_state("completed")
        return result

    def _load_final_contract(
        self,
    ) -> tuple[dict[str, Any], PatchDecision, str]:
        manifest_path = self.config.final_manifest_path
        optimization_path = self.config.optimization_result_path
        if (
            manifest_path is None
            or optimization_path is None
            or self.config.source_revision is None
            or self.config.final_manifest_hash is None
        ):
            raise ValueError(
                "Final execution requires frozen manifest identity, source revision, "
                "and optimization result"
            )
        for path, label in (
            (Path(manifest_path), "Final manifest"),
            (Path(optimization_path), "Optimization result"),
        ):
            self._assert_no_symlink_components(path, label)
            if not path.is_file():
                raise FileNotFoundError(f"{label} is unavailable: {path}")
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        expected_keys = {
            "schema_version",
            "run_id",
            "git_revision",
            "bundle_hashes",
            "source_hashes",
            "optimization_complete",
            "created_at",
            "manifest_hash",
        }
        if (
            not isinstance(manifest, dict)
            or set(manifest) != expected_keys
            or manifest.get("schema_version") != "phase74-final-manifest-v1"
            or manifest.get("optimization_complete") is not True
            or not isinstance(manifest.get("run_id"), str)
            or not _SAFE_NAME.fullmatch(manifest["run_id"])
            or not isinstance(manifest.get("git_revision"), str)
            or not re.fullmatch(r"[a-f0-9]{40,64}", manifest["git_revision"])
            or not isinstance(manifest.get("bundle_hashes"), dict)
            or not isinstance(manifest.get("source_hashes"), dict)
        ):
            raise ValueError("Final manifest schema is invalid")
        unsigned_manifest = {
            key: value for key, value in manifest.items() if key != "manifest_hash"
        }
        manifest_hash = _canonical_hash(unsigned_manifest)
        if (
            manifest.get("manifest_hash") != manifest_hash
            or manifest_hash != self.config.final_manifest_hash
        ):
            raise ValueError("Final manifest hash is invalid")
        if manifest["git_revision"] != self.config.source_revision:
            raise ValueError("Provided source revision does not match final manifest")
        expected_bundle_hash = manifest["bundle_hashes"].get(self.config.doc_type)
        if (
            not isinstance(expected_bundle_hash, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_bundle_hash)
            or self.baseline_bundle is None
            or self.baseline_bundle["bundle_hash"] != expected_bundle_hash
        ):
            raise ValueError("Current public bundle does not match final manifest")
        for relative_path in (
            self.target_file,
            "skills/pdf/SKILL.md",
        ):
            expected_hash = manifest["source_hashes"].get(relative_path)
            source_path = self.source_root / (relative_path or "")
            if (
                not isinstance(expected_hash, str)
                or not re.fullmatch(r"[a-f0-9]{64}", expected_hash)
                or not source_path.is_file()
                or source_path.is_symlink()
                or _bytes_hash(source_path) != expected_hash
            ):
                raise ValueError(
                    f"Frozen source hash mismatch for {relative_path}"
                )
        optimization = json.loads(
            Path(optimization_path).read_text(encoding="utf-8")
        )
        if (
            not isinstance(optimization, dict)
            or optimization.get("doc_type") != self.config.doc_type
            or optimization.get("status") != "completed"
            or not isinstance(optimization.get("patch"), dict)
        ):
            raise ValueError("Optimization result identity/schema is invalid")
        patch = PatchDecision(**optimization["patch"])
        return manifest, patch, manifest_hash

    def _execute_final(
        self,
        cases: list[dict[str, Any]],
        research: dict[str, Any],
    ) -> DocumentPipelineResult:
        manifest, patch, manifest_hash = self._load_final_contract()
        self.final_bundle = self.baseline_bundle
        final_worker_manifest = self._worker_manifest(
            "final_workers",
            cases,
            self.final_bundle or {},
            selection="frozen-source",
        )
        final_worker_manifest.update(
            {
                "final_manifest_hash": manifest_hash,
                "git_revision": manifest["git_revision"],
            }
        )
        final_workers = self._run_stage(
            "final_workers",
            final_worker_manifest,
            expected=len(cases),
            produce=lambda: self._produce_workers(
                "final_workers",
                cases,
                self.final_bundle or {},
            ),
            validate=lambda output: self._validate_worker_reports(
                output,
                cases,
                self.final_bundle or {},
            ),
        )
        final_judge_manifest = self._judge_manifest(
            "final_judge",
            final_workers,
            cases,
            research,
            self.final_bundle or {},
            selection="frozen-source",
        )
        final_judge_manifest.update(
            {
                "final_manifest_hash": manifest_hash,
                "git_revision": manifest["git_revision"],
            }
        )
        self._run_stage(
            "final_judge",
            final_judge_manifest,
            expected=1,
            produce=lambda: self._produce_judge(
                "final_judge",
                final_workers,
                cases,
                research,
                self.final_bundle or {},
            ),
            validate=lambda output: self._validate_judge(
                output,
                final_workers,
                cases,
                research,
                self.final_bundle or {},
            ),
        )
        optimization = json.loads(
            Path(self.config.optimization_result_path or "").read_text(
                encoding="utf-8"
            )
        )
        result = DocumentPipelineResult(
            run_id=self.config.run_id,
            doc_type=self.config.doc_type,
            status="completed",
            stages=list(self.completed_stages),
            max_live_sessions=self.max_live_sessions,
            patch=patch,
            baseline_bundle_hash=(self.baseline_bundle or {})["bundle_hash"],
            candidate_bundle_hash=optimization.get("candidate_bundle_hash"),
            final_bundle_hash=(self.final_bundle or {})["bundle_hash"],
        )
        atomic_write_json(self.result_path, asdict(result))
        self.store.transition_stage("final_judge", status="completed")
        self._write_pipeline_state("completed")
        return result

    def execute(self) -> DocumentPipelineResult:
        cases, training, holdout, research = self._load_inputs()
        training_ids = {case["opaque_case_id"] for case in training}
        holdout_ids = {case["opaque_case_id"] for case in holdout}
        if self.corpus_db_input.is_symlink():
            raise ValueError("Corpus index database must not itself be a symlink")
        if not self.corpus_db_input.is_file():
            raise FileNotFoundError(
                f"Corpus index database is not available: {self.corpus_db_input}"
            )
        self.corpus_db_path = self.corpus_db_input.resolve(strict=True)
        self._assert_no_symlink_components(
            self.proposal_root_input,
            "Proposal sandbox root",
        )
        if self.proposal_root_input.exists() and not self.proposal_root_input.is_dir():
            raise ValueError("Proposal sandbox root is not a directory")
        self.proposal_root = self.proposal_root_input.resolve()
        self.target_file, source_path = self._resolve_source()
        source_bytes = source_path.read_bytes()
        self.source_content = source_bytes.decode("utf-8")
        self.source_hash = hashlib.sha256(source_bytes).hexdigest()
        self.baseline_bundle = self._build_bundle()
        if self.config.execution_phase in {
            "shared_baseline",
            "shared_candidate",
        }:
            return self._execute_shared_evaluation(cases, research)
        if self.config.execution_phase == "final":
            return self._execute_final(cases, research)

        baseline_worker_manifest = self._worker_manifest(
            "baseline_workers",
            cases,
            self.baseline_bundle,
            selection="source",
        )
        baseline_workers = self._run_stage(
            "baseline_workers",
            baseline_worker_manifest,
            expected=len(cases),
            produce=lambda: self._produce_workers(
                "baseline_workers",
                cases,
                self.baseline_bundle or {},
            ),
            validate=lambda output: self._validate_worker_reports(
                output,
                cases,
                self.baseline_bundle or {},
            ),
        )

        baseline_judge_manifest = self._judge_manifest(
            "baseline_judge",
            baseline_workers,
            cases,
            research,
            self.baseline_bundle or {},
            selection="source",
        )
        baseline_judge = self._run_stage(
            "baseline_judge",
            baseline_judge_manifest,
            expected=1,
            produce=lambda: self._produce_judge(
                "baseline_judge",
                baseline_workers,
                cases,
                research,
                self.baseline_bundle or {},
            ),
            validate=lambda output: self._validate_judge(
                output,
                baseline_workers,
                cases,
                research,
                self.baseline_bundle or {},
            ),
        )

        sealed_findings = seal_holdout_findings(
            baseline_judge,
            holdout_case_ids=holdout_ids,
            doc_type=self.config.doc_type,
        )
        serialized_sealed = _canonical_json(sealed_findings)
        if any(case_id in serialized_sealed for case_id in holdout_ids):
            raise RuntimeError("Holdout findings crossed the optimizer seal")
        optimizer_manifest = self._optimizer_manifest(sealed_findings)
        optimizer = self._run_stage(
            "optimizer",
            optimizer_manifest,
            expected=1,
            produce=lambda: self._produce_optimizer(sealed_findings),
            validate=lambda output: self._validate_optimizer(output, sealed_findings),
        )
        self.candidate_result = optimizer

        candidate_valid = bool(optimizer["is_valid"])
        candidate_bundle_error: str | None = None
        candidate_evaluation_error: dict[str, str] | None = None
        if candidate_valid:
            try:
                self.candidate_bundle = self._build_bundle(
                    optimizer["candidate_content"]
                )
            except CandidateBundleValidationError as error:
                candidate_valid = False
                candidate_bundle_error = str(error)
        if candidate_valid:
            candidate_worker_manifest = self._worker_manifest(
                "candidate_workers",
                cases,
                self.candidate_bundle,
                selection="candidate",
            )
            try:
                candidate_workers = self._run_stage(
                    "candidate_workers",
                    candidate_worker_manifest,
                    expected=len(cases),
                    produce=lambda: self._produce_workers(
                        "candidate_workers",
                        cases,
                        self.candidate_bundle or {},
                    ),
                    validate=lambda output: self._validate_worker_reports(
                        output,
                        cases,
                        self.candidate_bundle or {},
                    ),
                )
            except _CANDIDATE_SEMANTIC_ERRORS as error:
                candidate_evaluation_error = {
                    "stage": "candidate_workers",
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
                skipped_workers = {
                    "skipped": True,
                    "reason": "candidate_evaluation_invalid",
                }
                candidate_workers = self._run_stage(
                    "candidate_workers",
                    {
                        "schema_version": "document-worker-stage-v1",
                        "stage": "candidate_workers",
                        "doc_type": self.config.doc_type,
                        "selection": "invalid-candidate-evaluation",
                        "optimizer_output_hash": _canonical_hash(optimizer),
                        "failure": candidate_evaluation_error,
                    },
                    expected=0,
                    produce=lambda: skipped_workers,
                    validate=lambda output: (
                        None
                        if output == skipped_workers
                        else (_ for _ in ()).throw(
                            ValueError("Invalid candidate Worker failure artifact")
                        )
                    ),
                )

            if candidate_evaluation_error is None:
                candidate_judge_manifest = self._judge_manifest(
                    "candidate_judge",
                    candidate_workers,
                    cases,
                    research,
                    self.candidate_bundle or {},
                    selection="candidate",
                )
                try:
                    candidate_judge = self._run_stage(
                        "candidate_judge",
                        candidate_judge_manifest,
                        expected=1,
                        produce=lambda: self._produce_judge(
                            "candidate_judge",
                            candidate_workers,
                            cases,
                            research,
                            self.candidate_bundle or {},
                        ),
                        validate=lambda output: self._validate_judge(
                            output,
                            candidate_workers,
                            cases,
                            research,
                            self.candidate_bundle or {},
                        ),
                    )
                except _CANDIDATE_SEMANTIC_ERRORS as error:
                    candidate_evaluation_error = {
                        "stage": "candidate_judge",
                        "error_type": type(error).__name__,
                        "message": str(error),
                    }
                    skipped_judge = {
                        "skipped": True,
                        "reason": "candidate_evaluation_invalid",
                    }
                    self._run_stage(
                        "candidate_judge",
                        {
                            "schema_version": "document-judge-stage-v1",
                            "stage": "candidate_judge",
                            "doc_type": self.config.doc_type,
                            "selection": "invalid-candidate-evaluation",
                            "worker_output_hash": _canonical_hash(candidate_workers),
                            "failure": candidate_evaluation_error,
                        },
                        expected=0,
                        produce=lambda: skipped_judge,
                        validate=lambda output: (
                            None
                            if output == skipped_judge
                            else (_ for _ in ()).throw(
                                ValueError("Invalid candidate Judge failure artifact")
                            )
                        ),
                    )
                    candidate_judge = None
            else:
                skipped_judge = {
                    "skipped": True,
                    "reason": "candidate_evaluation_invalid",
                }
                self._run_stage(
                    "candidate_judge",
                    {
                        "schema_version": "document-judge-stage-v1",
                        "stage": "candidate_judge",
                        "doc_type": self.config.doc_type,
                        "selection": "invalid-candidate-evaluation",
                        "worker_skip_hash": _canonical_hash(candidate_workers),
                        "failure": candidate_evaluation_error,
                    },
                    expected=0,
                    produce=lambda: skipped_judge,
                    validate=lambda output: (
                        None
                        if output == skipped_judge
                        else (_ for _ in ()).throw(
                            ValueError("Invalid candidate Judge skip artifact")
                        )
                    ),
                )
                candidate_judge = None
        else:
            skipped_workers = {
                "skipped": True,
                "reason": (
                    "candidate_bundle_invalid"
                    if candidate_bundle_error is not None
                    else "optimizer_candidate_invalid"
                ),
            }
            candidate_workers = self._run_stage(
                "candidate_workers",
                {
                    "schema_version": "document-worker-stage-v1",
                    "stage": "candidate_workers",
                    "doc_type": self.config.doc_type,
                    "selection": "invalid-candidate",
                    "optimizer_output_hash": _canonical_hash(optimizer),
                },
                expected=0,
                produce=lambda: skipped_workers,
                validate=lambda output: (
                    None
                    if output == skipped_workers
                    else (_ for _ in ()).throw(
                        ValueError("Invalid candidate Worker skip artifact")
                    )
                ),
            )
            skipped_judge = {
                "skipped": True,
                "reason": (
                    "candidate_bundle_invalid"
                    if candidate_bundle_error is not None
                    else "optimizer_candidate_invalid"
                ),
            }
            candidate_judge = self._run_stage(
                "candidate_judge",
                {
                    "schema_version": "document-judge-stage-v1",
                    "stage": "candidate_judge",
                    "doc_type": self.config.doc_type,
                    "selection": "invalid-candidate",
                    "worker_skip_hash": _canonical_hash(candidate_workers),
                },
                expected=0,
                produce=lambda: skipped_judge,
                validate=lambda output: (
                    None
                    if output == skipped_judge
                    else (_ for _ in ()).throw(
                        ValueError("Invalid candidate Judge skip artifact")
                    )
                ),
            )
            candidate_judge = None

        decision_manifest = {
            "schema_version": "document-patch-decision-v1",
            "stage": "patch_decision",
            "doc_type": self.config.doc_type,
            "source_revision": self.config.source_revision,
            "source_hash": self.source_hash,
            "optimizer_output_hash": _canonical_hash(optimizer),
            "baseline_judge_hash": _canonical_hash(baseline_judge),
            "candidate_judge_hash": (
                _canonical_hash(candidate_judge)
                if candidate_judge is not None
                else None
            ),
            "candidate_bundle_error": candidate_bundle_error,
            "candidate_evaluation_error": candidate_evaluation_error,
            "training_case_ids": sorted(training_ids),
            "holdout_commitment": sealed_findings["holdout_commitment"],
            "evaluator": "evaluate_candidate_patch",
        }
        decision = self._run_stage(
            "patch_decision",
            decision_manifest,
            expected=1,
            produce=lambda: self._decision_output(
                optimizer,
                baseline_judge,
                candidate_judge,
                training_ids,
                holdout_ids,
                candidate_bundle_error,
                candidate_evaluation_error,
            ),
            validate=lambda output: self._validate_exact_decision(
                output,
                optimizer=optimizer,
                baseline_judge=baseline_judge,
                candidate_judge=candidate_judge,
                training_ids=training_ids,
                holdout_ids=holdout_ids,
                candidate_bundle_error=candidate_bundle_error,
                candidate_evaluation_error=candidate_evaluation_error,
            ),
        )
        self.metrics = decision["metrics"]

        if self.config.execution_phase == "optimization":
            patch = PatchDecision(**decision)
            result = DocumentPipelineResult(
                run_id=self.config.run_id,
                doc_type=self.config.doc_type,
                status="completed",
                stages=list(self.completed_stages),
                max_live_sessions=self.max_live_sessions,
                patch=patch,
                baseline_bundle_hash=self.baseline_bundle["bundle_hash"],
                candidate_bundle_hash=(
                    self.candidate_bundle["bundle_hash"]
                    if self.candidate_bundle is not None
                    else None
                ),
                final_bundle_hash=None,
            )
            atomic_write_json(self.result_path, asdict(result))
            self.store.transition_stage("patch_decision", status="completed")
            self._write_pipeline_state("completed")
            return result

        self.final_bundle = (
            self.candidate_bundle
            if decision["status"] == "accepted"
            else self.baseline_bundle
        )
        final_selection = (
            "accepted-candidate"
            if decision["status"] == "accepted"
            else "source"
        )
        final_worker_manifest = self._worker_manifest(
            "final_workers",
            cases,
            self.final_bundle or {},
            selection=final_selection,
        )
        final_worker_manifest["decision_hash"] = _canonical_hash(decision)
        final_workers = self._run_stage(
            "final_workers",
            final_worker_manifest,
            expected=len(cases),
            produce=lambda: self._produce_workers(
                "final_workers",
                cases,
                self.final_bundle or {},
            ),
            validate=lambda output: self._validate_worker_reports(
                output,
                cases,
                self.final_bundle or {},
            ),
        )

        final_judge_manifest = self._judge_manifest(
            "final_judge",
            final_workers,
            cases,
            research,
            self.final_bundle or {},
            selection=final_selection,
        )
        final_judge_manifest["decision_hash"] = _canonical_hash(decision)
        self._run_stage(
            "final_judge",
            final_judge_manifest,
            expected=1,
            produce=lambda: self._produce_judge(
                "final_judge",
                final_workers,
                cases,
                research,
                self.final_bundle or {},
            ),
            validate=lambda output: self._validate_judge(
                output,
                final_workers,
                cases,
                research,
                self.final_bundle or {},
            ),
        )

        patch = PatchDecision(**decision)
        result = DocumentPipelineResult(
            run_id=self.config.run_id,
            doc_type=self.config.doc_type,
            status="completed",
            stages=list(self.completed_stages),
            max_live_sessions=self.max_live_sessions,
            patch=patch,
            baseline_bundle_hash=self.baseline_bundle["bundle_hash"],
            candidate_bundle_hash=(
                self.candidate_bundle["bundle_hash"]
                if self.candidate_bundle is not None
                else None
            ),
            final_bundle_hash=(self.final_bundle or {})["bundle_hash"],
        )
        atomic_write_json(self.result_path, asdict(result))
        self.store.transition_stage("final_judge", status="completed")
        self._write_pipeline_state("completed")
        return result

    def blocked(self, error: Exception) -> DocumentPipelineResult:
        candidate = self.candidate_result or {}
        candidate_id = candidate.get("candidate_id")
        candidate_provenance = candidate.get("_provenance")
        if (
            not isinstance(candidate_id, str)
            or not _CANDIDATE_ID.fullmatch(candidate_id)
            or not isinstance(candidate_provenance, dict)
            or candidate_provenance.get("candidate_id") != candidate_id
        ):
            candidate_id = None
        candidate_content = candidate.get("candidate_content", "")
        candidate_hash = (
            hashlib.sha256(candidate_content.encode("utf-8")).hexdigest()
            if candidate_content
            else None
        )
        candidate_path: str | None = None
        if candidate.get("is_valid"):
            try:
                path = self._candidate_path(candidate)
                if path.is_file() and _bytes_hash(path) == candidate_hash:
                    candidate_path = str(path)
            except (KeyError, OSError, TypeError):
                candidate_path = None
        patch = PatchDecision(
            status="blocked",
            target_file=self.target_file,
            candidate_id=candidate_id,
            candidate_path=candidate_path,
            candidate_content=candidate_content,
            candidate_content_hash=candidate_hash,
            source_hash=self.source_hash,
            metrics=dict(self.metrics),
            evidence=[
                {
                    "kind": "infrastructure_failure",
                    "stage": self.current_stage,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            ],
        )
        result = DocumentPipelineResult(
            run_id=self.config.run_id,
            doc_type=self.config.doc_type,
            status="blocked",
            stages=list(self.completed_stages),
            max_live_sessions=self.max_live_sessions,
            patch=patch,
            baseline_bundle_hash=(
                self.baseline_bundle.get("bundle_hash")
                if self.baseline_bundle
                else None
            ),
            candidate_bundle_hash=(
                self.candidate_bundle.get("bundle_hash")
                if self.candidate_bundle
                else None
            ),
            final_bundle_hash=(
                self.final_bundle.get("bundle_hash") if self.final_bundle else None
            ),
            error=str(error),
        )
        atomic_write_json(
            self._state_stage_path(self.current_stage),
            StageManifest(
                stage=self.current_stage,
                status="failed",
                input_hash=self.current_input_hash,
                completed_at=_utc_now(),
                error=str(error),
            ),
        )
        atomic_write_json(self.result_path, asdict(result))
        self._write_pipeline_state("blocked", error=str(error))
        self.store.manifest.error_classification = "infrastructure_blocked"
        self.store.manifest.stage = self.current_stage
        self.store.manifest.status = "failed"
        self.store._save_manifest()
        return result


def inspect_document_pipeline_inputs(
    config: DocumentPipelineConfig,
) -> DocumentPipelineInputSnapshot:
    """Reuse child containment, identity, and hash checks without creating run state."""
    pipeline = _DocumentPipeline(config, initialize_state=False)
    cases, _, _, _ = pipeline._load_inputs()
    if pipeline.corpus_db_input.is_symlink():
        raise ValueError("Corpus index database must not itself be a symlink")
    if not pipeline.corpus_db_input.is_file():
        raise FileNotFoundError(
            f"Corpus index database is not available: {pipeline.corpus_db_input}"
        )
    pipeline.corpus_db_path = pipeline.corpus_db_input.resolve(strict=True)
    pipeline.target_file, source_path = pipeline._resolve_source()
    source_bytes = source_path.read_bytes()
    pipeline.source_content = source_bytes.decode("utf-8")
    pipeline.source_hash = hashlib.sha256(source_bytes).hexdigest()
    bundle = pipeline._build_bundle()

    input_paths = [
        pipeline.doc_dir / "ground_truth" / "ground_truth.json",
        pipeline.doc_dir / "research" / "research.json",
        source_path,
        pipeline.shared_skill_path,
    ]
    manifest_path = pipeline.doc_dir / "pipeline_manifest.json"
    if manifest_path.is_file():
        input_paths.append(manifest_path)
    for case in cases:
        case_id = case["opaque_case_id"]
        input_paths.append(pipeline._pdf_path(case_id))
        text_path = pipeline._optional_text_path(case_id)
        if text_path is not None:
            input_paths.append(text_path)
    return DocumentPipelineInputSnapshot(
        doc_type=config.doc_type,
        case_ids=tuple(sorted(case["opaque_case_id"] for case in cases)),
        input_hashes={
            str(path): _bytes_hash(path)
            for path in sorted(set(input_paths), key=str)
        },
        source_hash=pipeline.source_hash,
        bundle_hash=bundle["bundle_hash"],
    )


def run_document_pipeline(config: DocumentPipelineConfig) -> DocumentPipelineResult:
    """Run one document type through all model stages with no session overlap."""
    pipeline: _DocumentPipeline | None = None
    try:
        pipeline = _DocumentPipeline(config)
        return pipeline.execute()
    except Exception as error:
        if pipeline is None:
            raise
        return pipeline.blocked(error)


def main(argv: list[str] | None = None) -> int:
    """Execute one supervisor-owned document pipeline child."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--doc-type", required=True)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--final-manifest", type=Path)
    parser.add_argument("--final-manifest-hash")
    args = parser.parse_args(argv)
    result = run_document_pipeline(
        DocumentPipelineConfig(
            run_id=args.run_id,
            doc_type=args.doc_type,
            pipeline_root=Path(
                os.environ.get("PHASE74_PIPELINE_ROOT", _PIPELINES_DIR)
            ),
            state_root=args.run_root,
            corpus_db_path=Path(
                os.environ.get("PHASE74_CORPUS_DB", _CORPUS_DB)
            ),
            proposal_sandbox_root=Path(
                os.environ.get("PHASE74_PROPOSAL_ROOT", _PROPOSAL_ROOT)
            ),
            source_root=Path(
                os.environ.get("PHASE74_SOURCE_ROOT", _REPO_ROOT)
            ),
            execution_phase=os.environ.get(
                "PHASE74_PIPELINE_PHASE",
                "full",
            ),
            final_manifest_path=(
                args.final_manifest
                if args.final_manifest is not None
                else (
                    Path(os.environ["PHASE74_FINAL_MANIFEST"])
                    if os.environ.get("PHASE74_FINAL_MANIFEST")
                    else None
                )
            ),
            final_manifest_hash=args.final_manifest_hash,
            optimization_result_path=(
                Path(os.environ["PHASE74_OPTIMIZATION_RESULT"])
                if os.environ.get("PHASE74_OPTIMIZATION_RESULT")
                else None
            ),
            shared_candidate_path=(
                Path(os.environ["PHASE74_SHARED_CANDIDATE"])
                if os.environ.get("PHASE74_SHARED_CANDIDATE")
                else None
            ),
            source_revision=args.source_revision,
            artifact_import_roots=tuple(
                Path(value)
                for value in json.loads(
                    os.environ.get(
                        "PHASE74_ARTIFACT_IMPORT_ROOTS",
                        "[]",
                    )
                )
            ),
        )
    )
    print(_canonical_json(asdict(result)))
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
