"""Repository-wide supervisor for isolated Copilot SDK document pipelines."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time
from typing import Any, Literal
import uuid

from crawler.eval.patch_evaluator import (
    apply_patch_atomically,
    evaluate_candidate_patch,
    validate_patch_allowlist,
    validate_target_allowlist,
)
from crawler.eval.agent_runtime import run_async
from crawler.eval.genuine_optimizer import run_candidate_optimization_pass
from crawler.eval.holdout_splitter import (
    seal_holdout_findings,
    split_doc_type_cases,
)
from crawler.eval.document_pipeline import (
    DocumentPipelineConfig,
    inspect_document_pipeline_inputs,
)
from crawler.eval.copilot_sdk_runtime import (
    CopilotSdkRuntime,
    _await_with_hard_deadline,
    copilot_client_auth_kwargs,
    start_client_bounded,
    stop_client_bounded,
)
from crawler.eval.pipeline_state import (
    ActiveRunError,
    CleanupResult,
    DescendantExitTimeoutError,
    DescendantOwnershipError,
    LeaseReleaseResult,
    PipelineRunLease,
    PipelineStateStore,
    ProcessInfo,
    ProcessIdentity,
    ProcessProbe,
    RunManifest,
    SupervisorProcessRegistry,
    _manifest_owner,
    _verified_process,
    atomic_write_json,
    cleanup_stalled_runs,
    compute_command_digest,
)
from crawler.eval.public_bundle import build_public_review_bundle
from crawler.synthetic.schemas import ExpressEntryDocType


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_ROOT = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_STATE_ROOT = _REPO_ROOT / "reports" / "phase74_sdk_runs"
_PROPOSAL_ROOT = _REPO_ROOT / "reports" / "proposal_sandboxes"
_RUNTIME_ROOT = _REPO_ROOT / "reports" / "phase74_sdk_runtime"
_CORPUS_DB = _REPO_ROOT / "corpus" / "index.db"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CANDIDATE_ID = re.compile(r"^candidate_[a-f0-9]{12}$")
_SDK_VERSION = re.compile(r"^1\.0\.\d+(?:[A-Za-z0-9._+-]*)?$")
_HASH = re.compile(r"^[a-f0-9]{64}$")
_PIPELINE_SLOTS = 5
_EXPECTED_PIPELINES = 23
_EXPECTED_PDFS = 236
_TRAILER = "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
_SCORE_FIELDS = (
    "grounding_accuracy",
    "citation_exactness",
    "defect_recall",
    "pii_containment",
    "blind_input_compliance",
)

REQUIRED_MODELS = frozenset({"gemini-3.6-flash", "claude-opus-4.8"})
_MODEL_STAGE_TIMEOUTS = {
    "worker": 600.0,
    "judge": 900.0,
    "optimizer": 600.0,
}


class RunCleanupError(RuntimeError):
    """Raised when a verified child or descendant survives reconciliation."""


@dataclass(frozen=True)
class RuntimePreflight:
    """PII-free runtime facts returned by the SDK preflight adapter."""

    sdk_version: str
    runtime_version: str
    sdk_protocol_version: int
    runtime_protocol_version: int
    authenticated: bool
    models: list[str]
    runtime_ready: bool


@dataclass(frozen=True)
class PreflightReport:
    """Validated immutable inputs for one supervisor run."""

    python_version: str
    sdk_version: str
    runtime_version: str
    protocol_version: int
    models: list[str]
    doc_types: list[str]
    pdf_count: int
    corpus_hash: str
    input_hashes: dict[str, str]
    bundle_hashes: dict[str, str]
    ignored_roots: list[str]


@dataclass
class SupervisorDocumentResult:
    """Child execution plus its independently validated parent decision."""

    doc_type: str
    status: Literal["completed", "blocked", "cancelled"]
    exit_code: int | None
    child_result: dict[str, Any] | None
    parent_patch_status: Literal[
        "pending", "applied", "rejected", "blocked"
    ] = "pending"
    blocker: str | None = None
    progress_sequences: list[int] = field(default_factory=list)
    requires_cleanup: bool = False


@dataclass(frozen=True)
class SupervisorRunResult:
    """Terminal supervisor result with explicit coverage for every document type."""

    run_id: str
    status: Literal["completed", "blocked", "cancelled"]
    preflight: PreflightReport
    document_results: dict[str, SupervisorDocumentResult]
    peak_concurrency: int
    applied_patches: list[dict[str, Any]]
    shared_decision: dict[str, Any]
    final_manifest_path: str
    final_manifest_hash: str


RuntimePreflightFn = Callable[
    [Path, str, Callable[[int], None]],
    RuntimePreflight | Awaitable[RuntimePreflight],
]
SubprocessFactory = Callable[..., Awaitable[Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _discover_worker_artifact_import_roots(
    state_root: Path,
) -> tuple[Path, ...]:
    """Disable discovery from mutable ignored run directories.

    Model output reuse remains fail-closed until a caller supplies a committed
    trust anchor that binds a completed supervisor run, registry/lease cleanup,
    source revision, SDK provenance, and every imported artifact hash.
    """
    del state_root
    return ()


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"sdk-{stamp}-{uuid.uuid4().hex[:12]}"


def _sync_await(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return run_async(
            value,
            async_api_name="the asynchronous supervisor interface",
        )
    raise RuntimeError("Use the asynchronous supervisor interface inside an event loop")


async def _default_runtime_preflight(
    runtime_root: Path,
    run_id: str,
    register_descendant: Callable[[int], None],
    *,
    client_factory: Callable[..., Any] | None = None,
    startup_timeout_seconds: float = 30.0,
    cleanup_timeout_seconds: float = 5.0,
) -> RuntimePreflight:
    import copilot
    from copilot import CopilotClient
    from copilot._sdk_protocol_version import get_sdk_protocol_version

    runtime_root.mkdir(parents=True, exist_ok=True)
    create_client = client_factory or CopilotClient
    client = create_client(
        mode="empty",
        base_directory=str(runtime_root),
        env={"PHASE74_RUN_ID": run_id},
        **copilot_client_auth_kwargs(),
    )
    try:
        await start_client_bounded(
            client,
            register_descendant=register_descendant,
            timeout_seconds=startup_timeout_seconds,
        )
        ping = await client.ping("phase74-preflight")
        status = await client.get_status()
        auth = await client.get_auth_status()
        models = await client.list_models()
    finally:
        await stop_client_bounded(
            client,
            timeout_seconds=cleanup_timeout_seconds,
        )

    runtime_protocol = int(status.protocol_version)
    if int(ping.protocol_version) != runtime_protocol:
        raise RuntimeError("Copilot runtime ping/status protocol mismatch")
    return RuntimePreflight(
        sdk_version=str(getattr(copilot, "__version__", "")),
        runtime_version=str(status.version),
        sdk_protocol_version=int(get_sdk_protocol_version()),
        runtime_protocol_version=runtime_protocol,
        authenticated=bool(auth.isAuthenticated),
        models=sorted(model.id for model in models),
        runtime_ready=True,
    )


def _default_ignored_path_checker(path: Path) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(path)],
        cwd=_REPO_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _default_dirty_input_finder(paths: Iterable[Path]) -> list[str]:
    relative = [
        str(path.resolve().relative_to(_REPO_ROOT.resolve()))
        for path in paths
        if path.resolve().is_relative_to(_REPO_ROOT.resolve())
    ]
    if not relative:
        return []
    completed = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *relative,
        ],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


class SdkPipelineOrchestrator:
    """Own the sole live lease and supervise five isolated document children."""

    def __init__(
        self,
        *,
        source_root: Path = _REPO_ROOT,
        pipeline_root: Path = _PIPELINES_ROOT,
        state_root: Path = _STATE_ROOT,
        corpus_db_path: Path = _CORPUS_DB,
        proposal_root: Path = _PROPOSAL_ROOT,
        runtime_root: Path = _RUNTIME_ROOT,
        doc_types: Iterable[str] | None = None,
        run_id: str | None = None,
        require_complete_dataset: bool = True,
        separate_final_phase: bool | None = None,
        runtime_preflight: RuntimePreflightFn = _default_runtime_preflight,
        ignored_path_checker: Callable[[Path], bool] = _default_ignored_path_checker,
        dirty_input_finder: Callable[[Iterable[Path]], list[str]] = (
            _default_dirty_input_finder
        ),
        input_inspector: Callable[[DocumentPipelineConfig], Any] = (
            inspect_document_pipeline_inputs
        ),
        subprocess_factory: SubprocessFactory = asyncio.create_subprocess_exec,
        process_probe: ProcessProbe | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        heartbeat_timeout_seconds: float = 300.0,
        stage_timeout_seconds: float = 7_200.0,
        descendant_timeout_seconds: float = 30.0,
        monitor_interval_seconds: float = 0.25,
        termination_grace_seconds: float = 5.0,
        spawn_identity_timeout_seconds: float = 0.1,
        spawn_identity_poll_seconds: float = 0.01,
        spawn_identity_sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        artifact_import_roots: Iterable[Path] | None = None,
        bundle_builder: Callable[[str], dict[str, Any]] | None = None,
        shared_optimizer: Callable[
            [dict[str, SupervisorDocumentResult]], dict[str, Any]
        ]
        | None = None,
        revision_resolver: Callable[[], str] | None = None,
        source_clean_checker: Callable[[], bool] | None = None,
        git_runner: Callable[[list[str]], Any] | None = None,
    ) -> None:
        self.source_root = Path(source_root).resolve()
        self.pipeline_root = Path(pipeline_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.corpus_db_path = Path(corpus_db_path).resolve()
        self.proposal_root = Path(proposal_root).resolve()
        self.runtime_root = Path(runtime_root).resolve()
        self.doc_types = sorted(
            list(doc_types)
            if doc_types is not None
            else [doc_type.value for doc_type in ExpressEntryDocType]
        )
        self.run_id = run_id or _new_run_id()
        self.require_complete_dataset = require_complete_dataset
        self.separate_final_phase = (
            require_complete_dataset
            if separate_final_phase is None
            else separate_final_phase
        )
        self.runtime_preflight = runtime_preflight
        self.ignored_path_checker = ignored_path_checker
        self.dirty_input_finder = dirty_input_finder
        self.input_inspector = input_inspector
        self.subprocess_factory = subprocess_factory
        self.process_probe = process_probe or ProcessProbe()
        self.progress_callback = progress_callback
        self.heartbeat_timeout_seconds = self._duration(
            "heartbeat_timeout_seconds", heartbeat_timeout_seconds, positive=True
        )
        self.stage_timeout_seconds = self._duration(
            "stage_timeout_seconds", stage_timeout_seconds, positive=True
        )
        self.descendant_timeout_seconds = self._duration(
            "descendant_timeout_seconds", descendant_timeout_seconds
        )
        self.monitor_interval_seconds = self._duration(
            "monitor_interval_seconds", monitor_interval_seconds, positive=True
        )
        self.termination_grace_seconds = self._duration(
            "termination_grace_seconds", termination_grace_seconds
        )
        self.spawn_identity_timeout_seconds = self._duration(
            "spawn_identity_timeout_seconds",
            spawn_identity_timeout_seconds,
            positive=True,
        )
        self.spawn_identity_poll_seconds = self._duration(
            "spawn_identity_poll_seconds",
            spawn_identity_poll_seconds,
            positive=True,
        )
        self.spawn_identity_sleep = spawn_identity_sleep
        self.artifact_import_roots = tuple(
            Path(path).resolve()
            for path in (
                artifact_import_roots
                if artifact_import_roots is not None
                else _discover_worker_artifact_import_roots(self.state_root)
            )
        )
        self.bundle_builder = bundle_builder or self._build_bundle
        self.shared_optimizer = shared_optimizer
        self.revision_resolver = revision_resolver or self._git_revision
        self.source_clean_checker = (
            source_clean_checker or self._source_is_clean
        )
        self.git_runner = git_runner or self._run_git
        self._active_children = 0
        self._peak_children = 0
        self._optimization_active = False
        self._lease_release_safe = True
        self._lease: PipelineRunLease | None = None
        self._process_registry: SupervisorProcessRegistry | None = None
        self._current_stage = "initialization"
        self._document_results: dict[str, SupervisorDocumentResult] = {}

        if not _SAFE_NAME.fullmatch(self.run_id):
            raise ValueError("run_id must be a path-safe identifier")
        if not self.doc_types or any(
            not _SAFE_NAME.fullmatch(doc_type) for doc_type in self.doc_types
        ):
            raise ValueError("document types must be non-empty path-safe identifiers")
        if len(set(self.doc_types)) != len(self.doc_types):
            raise ValueError("document types must be distinct")

    def _initialize_process_registry(self) -> None:
        if self._lease is None:
            raise RuntimeError("Process registry requires the owning lease")
        self._process_registry = SupervisorProcessRegistry(
            self.state_root,
            parent_run_id=self.run_id,
            process_probe=self.process_probe,
        )

    def _release_owning_lease(
        self,
        *,
        explicit_recovery: bool = False,
    ) -> LeaseReleaseResult:
        if self._lease is None:
            return LeaseReleaseResult(
                run_id=self.run_id,
                errors=["No owning lease is available"],
            )
        if not self._lease_release_safe and not explicit_recovery:
            return LeaseReleaseResult(
                run_id=self.run_id,
                errors=[
                    "Lease release is unsafe until verified process cleanup "
                    "is reconciled"
                ],
            )
        result = self._lease.release_after_reconciliation()
        if result.released:
            self._lease = None
            self._lease_release_safe = True
        return result

    @staticmethod
    def _duration(name: str, value: float, *, positive: bool = False) -> float:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or value < 0
            or (positive and value <= 0)
        ):
            qualifier = "positive" if positive else "non-negative"
            raise ValueError(f"{name} must be finite and {qualifier}")
        return float(value)

    def _stage_watchdog_timeout(self, stage: str | None) -> float:
        minimum = 0.0
        if stage:
            if stage.endswith("workers"):
                minimum = _MODEL_STAGE_TIMEOUTS["worker"]
            elif stage.endswith("judge"):
                minimum = _MODEL_STAGE_TIMEOUTS["judge"]
            elif stage == "optimizer":
                minimum = _MODEL_STAGE_TIMEOUTS["optimizer"]
        return max(
            self.stage_timeout_seconds,
            minimum
            + self.descendant_timeout_seconds
            + self.termination_grace_seconds,
        )

    def _validate_runtime(self, status: RuntimePreflight) -> None:
        if not isinstance(status, RuntimePreflight):
            raise RuntimeError("SDK preflight returned an invalid result")
        if not _SDK_VERSION.fullmatch(status.sdk_version):
            raise RuntimeError(
                "github-copilot-sdk must resolve to the compatible 1.0 release line"
            )
        if not status.runtime_ready or not status.runtime_version:
            raise RuntimeError("Copilot runtime download/startup preflight failed")
        if (
            status.sdk_protocol_version <= 0
            or status.sdk_protocol_version != status.runtime_protocol_version
        ):
            raise RuntimeError("Copilot SDK/runtime protocol mismatch")
        if not status.authenticated:
            raise RuntimeError("Copilot authentication preflight failed")
        missing_models = sorted(REQUIRED_MODELS - set(status.models))
        if missing_models:
            raise RuntimeError(
                "Required Copilot models are unavailable: "
                + ", ".join(missing_models)
            )

    def _validate_pipeline_inputs(
        self,
    ) -> tuple[int, dict[str, str], dict[str, str], list[Path]]:
        input_hashes: dict[str, str] = {}
        bundle_hashes: dict[str, str] = {}
        input_paths: list[Path] = []
        pdf_count = 0
        global_case_ids: set[str] = set()

        for index, doc_type in enumerate(self.doc_types):
            snapshot = self.input_inspector(
                DocumentPipelineConfig(
                    run_id=f"{self.run_id}-preflight-{index}",
                    doc_type=doc_type,
                    pipeline_root=self.pipeline_root,
                    state_root=self.state_root,
                    corpus_db_path=self.corpus_db_path,
                    proposal_sandbox_root=self.proposal_root,
                    source_root=self.source_root,
                )
            )
            overlap = global_case_ids.intersection(snapshot.case_ids)
            if overlap:
                raise RuntimeError(
                    f"Cross-document duplicate case IDs: {sorted(overlap)}"
                )
            global_case_ids.update(snapshot.case_ids)
            pdf_count += len(snapshot.case_ids)
            bundle_hashes[doc_type] = snapshot.bundle_hash
            for raw_path, digest in snapshot.input_hashes.items():
                path = Path(raw_path)
                input_paths.append(path)
                key = (
                    str(path.relative_to(self.source_root))
                    if path.is_relative_to(self.source_root)
                    else str(path)
                )
                input_hashes[key] = digest

        return (
            pdf_count,
            dict(sorted(input_hashes.items())),
            dict(sorted(bundle_hashes.items())),
            input_paths,
        )

    def _run_preflight_checks(
        self,
        preflight_store: PipelineStateStore,
        registered_identities: list[ProcessIdentity],
    ) -> PreflightReport:
        if sys.version_info < (3, 11):
            raise RuntimeError("Python 3.11 or later is required")

        def register_preflight_runtime(pid: int) -> None:
            if self._process_registry is None:
                raise RuntimeError("Initialized parent process registry is unavailable")
            identity = self._process_registry.register_spawn(
                pid,
                run_id=self.run_id,
                doc_type="__preflight__",
            )
            try:
                preflight_store.add_descendant_pid(pid)
            except BaseException:
                self._process_registry.mark_requires_cleanup(
                    identity,
                    exit_code=None,
                )
                self._lease_release_safe = False
                raise
            registered_identities.append(identity)

        status = _sync_await(
            self.runtime_preflight(
                self.runtime_root,
                self.run_id,
                register_preflight_runtime,
            )
        )
        self._validate_runtime(status)

        expected_doc_types = {doc_type.value for doc_type in ExpressEntryDocType}
        if self.require_complete_dataset and (
            len(self.doc_types) != _EXPECTED_PIPELINES
            or set(self.doc_types) != expected_doc_types
        ):
            raise RuntimeError("Live preflight requires exactly 23 document pipelines")
        if (
            not self.corpus_db_path.is_file()
            or self.corpus_db_path.is_symlink()
        ):
            raise RuntimeError("Corpus index database is unavailable or unsafe")

        ignored_roots = [
            self.state_root,
            self.proposal_root,
            self.runtime_root,
            self.source_root / "reports" / "worker_staging",
            self.source_root / "reports" / "judge_staging",
        ]
        not_ignored = [
            str(path)
            for path in ignored_roots
            if not self.ignored_path_checker(path)
        ]
        if not_ignored:
            raise RuntimeError(
                "Runtime roots must be git-ignored: " + ", ".join(not_ignored)
            )

        (
            pdf_count,
            input_hashes,
            bundle_hashes,
            input_paths,
        ) = self._validate_pipeline_inputs()
        if self.require_complete_dataset and pdf_count != _EXPECTED_PDFS:
            raise RuntimeError(
                f"Live preflight requires exactly 236 PDFs, found {pdf_count}"
            )
        corpus_hash = _file_hash(self.corpus_db_path)
        input_hashes[
            str(self.corpus_db_path.relative_to(self.source_root))
            if self.corpus_db_path.is_relative_to(self.source_root)
            else str(self.corpus_db_path)
        ] = corpus_hash
        dirty = self.dirty_input_finder(
            [self.pipeline_root, self.corpus_db_path, *input_paths]
        )
        if dirty:
            raise RuntimeError(
                "Pipeline inputs are dirty; clean hashes cannot be frozen: "
                + "; ".join(dirty)
            )
        return PreflightReport(
            python_version=".".join(str(value) for value in sys.version_info[:3]),
            sdk_version=status.sdk_version,
            runtime_version=status.runtime_version,
            protocol_version=status.sdk_protocol_version,
            models=sorted(status.models),
            doc_types=list(self.doc_types),
            pdf_count=pdf_count,
            corpus_hash=corpus_hash,
            input_hashes=dict(sorted(input_hashes.items())),
            bundle_hashes=bundle_hashes,
            ignored_roots=[str(path) for path in ignored_roots],
        )

    def _reconcile_preflight_registry(
        self,
        identities: list[ProcessIdentity],
    ) -> None:
        if self._process_registry is None:
            self._lease_release_safe = False
            raise RunCleanupError("Initialized parent process registry is unavailable")
        failures: list[str] = []
        for identity in identities:
            try:
                if _verified_process(identity, self.process_probe) is not None:
                    self._process_registry.mark_requires_cleanup(
                        identity,
                        exit_code=None,
                    )
                    failures.append(
                        f"Preflight runtime PID {identity.pid} remains alive"
                    )
                else:
                    self._process_registry.mark_terminal(
                        identity,
                        exit_code=None,
                    )
                    self._process_registry.mark_reaped(
                        identity,
                        exit_code=None,
                    )
            except (
                OSError,
                ValueError,
                DescendantExitTimeoutError,
                DescendantOwnershipError,
            ) as error:
                failures.append(
                    "Preflight registry reconciliation failed: "
                    f"{type(error).__name__}"
                )
        if failures:
            self._lease_release_safe = False
            raise RunCleanupError("; ".join(failures))

    def _run_owned_preflight(self) -> PreflightReport:
        preflight_store = PipelineStateStore(
            self.state_root,
            run_id=self.run_id,
            doc_type="__preflight__",
            process_probe=self.process_probe,
        )
        preflight_store.transition_stage("preflight", status="in_progress")
        primary_error: BaseException | None = None
        report: PreflightReport | None = None
        registered_identities: list[ProcessIdentity] = []
        try:
            report = self._run_preflight_checks(
                preflight_store,
                registered_identities,
            )
        except BaseException as error:
            primary_error = error

        forced_cleanup = False
        cleanup_error: RunCleanupError | None = None
        try:
            preflight_store.wait_for_verified_descendants(
                self.descendant_timeout_seconds,
                min(self.monitor_interval_seconds, 0.1),
            )
        except DescendantExitTimeoutError:
            forced_cleanup = True
            cleanup_result = preflight_store.terminate_verified_processes(
                include_owner=False,
                grace_period_seconds=self.termination_grace_seconds,
            )
            try:
                preflight_store.wait_for_verified_descendants(
                    self.descendant_timeout_seconds,
                    min(self.monitor_interval_seconds, 0.1),
                )
            except DescendantExitTimeoutError as error:
                self._lease_release_safe = False
                preflight_store.manifest.status = "stalled"
                preflight_store.manifest.error_classification = (
                    "preflight_runtime_unreaped"
                )
                preflight_store._save_manifest()
                cleanup_error = RunCleanupError(
                    "preflight runtime survived verified termination and "
                    "bounded wait"
                )
                if primary_error is not None:
                    cleanup_error.add_note(
                        f"Primary preflight error: {type(primary_error).__name__}"
                    )
                if cleanup_result.errors:
                    cleanup_error.add_note("; ".join(cleanup_result.errors))
                cleanup_error.__cause__ = error

        try:
            self._reconcile_preflight_registry(registered_identities)
        except RunCleanupError as registry_error:
            if cleanup_error is not None:
                registry_error.add_note(str(cleanup_error))
            if primary_error is not None:
                registry_error.add_note(
                    f"Primary preflight error: {type(primary_error).__name__}"
                )
            raise
        if cleanup_error is not None:
            raise cleanup_error

        if primary_error is not None:
            preflight_store.manifest.status = (
                "cancelled"
                if isinstance(primary_error, asyncio.CancelledError)
                else "failed"
            )
            preflight_store.manifest.error_classification = type(
                primary_error
            ).__name__
            preflight_store._save_manifest()
            raise primary_error
        if forced_cleanup:
            preflight_store.manifest.status = "failed"
            preflight_store.manifest.error_classification = (
                "preflight_runtime_forced_cleanup"
            )
            preflight_store._save_manifest()
            raise RuntimeError(
                "preflight runtime required verified forced cleanup"
            )

        preflight_store.transition_stage("preflight", status="completed")
        if report is None:
            raise RuntimeError("Preflight did not produce a report")
        return report

    def preflight(self) -> PreflightReport:
        """Validate the live environment under the repository-wide lease."""
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._current_stage = "preflight"
        try:
            self._lease = PipelineRunLease.acquire(
                self.state_root,
                run_id=self.run_id,
                process_probe=self.process_probe,
            )
            self._initialize_process_registry()
            report = self._run_owned_preflight()
            released = self._release_owning_lease()
            if not released.released:
                raise RunCleanupError(
                    "Preflight lease reconciliation failed: "
                    + "; ".join(released.errors)
                )
            self._lease = None
            return report
        except BaseException as error:
            if self._lease is not None:
                try:
                    release = self._release_owning_lease()
                except BaseException as release_error:
                    error.add_note(
                        "Lease reconciliation raised "
                        f"{type(release_error).__name__}"
                    )
                else:
                    if release.released:
                        self._lease = None
                    elif release.errors:
                        error.add_note(
                            "Lease retained: " + "; ".join(release.errors)
                        )
            self._persist_exceptional_result(
                error,
                stage=self._current_stage,
            )
            raise

    async def _drain_stream(self, stream: Any, log_path: Path) -> None:
        if stream is None:
            log_path.touch(exist_ok=True)
            return
        with log_path.open("ab", buffering=0) as log:
            while True:
                line = await stream.readline()
                if not line:
                    return
                log.write(line if isinstance(line, bytes) else str(line).encode())

    def _load_heartbeat(
        self,
        heartbeat_path: Path,
        *,
        child_run_id: str,
        doc_type: str,
        child_pid: int,
    ) -> dict[str, Any] | None:
        try:
            heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return None
        if (
            not isinstance(heartbeat, dict)
            or heartbeat.get("run_id") != child_run_id
            or heartbeat.get("doc_type") != doc_type
            or heartbeat.get("pid") != child_pid
            or not isinstance(heartbeat.get("sequence"), int)
            or heartbeat["sequence"] < 0
            or not isinstance(heartbeat.get("stage"), str)
        ):
            return None
        return heartbeat

    async def _terminate_verified_run(
        self,
        child_run_id: str,
        doc_type: str,
        spawn_identity: ProcessIdentity | None = None,
    ) -> CleanupResult:
        result = CleanupResult()
        manifest_path = (
            self.state_root
            / "runs"
            / child_run_id
            / doc_type
            / "run_manifest.json"
        )
        if manifest_path.is_file():
            store = PipelineStateStore(
                self.state_root,
                run_id=child_run_id,
                doc_type=doc_type,
                process_probe=self.process_probe,
            )
            manifest_result = await asyncio.to_thread(
                store.terminate_verified_processes,
                include_owner=True,
                grace_period_seconds=self.termination_grace_seconds,
            )
            result = manifest_result

        if (
            spawn_identity is not None
            and _verified_process(spawn_identity, self.process_probe) is not None
            and spawn_identity.pid not in result.terminated_pids
        ):
            if self.process_probe.terminate_process(
                spawn_identity.pid,
                signal.SIGTERM,
            ):
                result.terminated_pids.append(spawn_identity.pid)
                await asyncio.sleep(self.termination_grace_seconds)
            if _verified_process(spawn_identity, self.process_probe) is not None:
                if self.process_probe.terminate_process(
                    spawn_identity.pid,
                    signal.SIGKILL,
                ):
                    result.killed_pids.append(spawn_identity.pid)
                    await asyncio.sleep(self.termination_grace_seconds)
            if _verified_process(spawn_identity, self.process_probe) is not None:
                result.remaining_pids.append(spawn_identity.pid)
                result.errors.append(
                    f"Verified registered child {spawn_identity.pid} "
                    "survived cleanup"
                )
        return result

    @staticmethod
    def _terminal_child_is_valid(
        *,
        manifest: RunManifest,
        spawn_identity: ProcessIdentity | None,
        expected_pid: int,
        expected_command_digest: str,
        child_run_id: str,
        doc_type: str,
        run_dir: Path,
    ) -> bool:
        if (
            manifest.run_id != child_run_id
            or manifest.doc_type != doc_type
            or manifest.pid != expected_pid
            or (
                spawn_identity is not None
                and (
                    manifest.pid != spawn_identity.pid
                    or manifest.process_start_time
                    != spawn_identity.process_start_time
                )
            )
            or manifest.command_digest
            != (
                spawn_identity.command_digest
                if spawn_identity is not None
                else expected_command_digest
            )
            or manifest.status
            not in {"completed", "failed", "stalled", "cancelled"}
        ):
            return False
        try:
            result = json.loads(
                (run_dir / "pipeline_result.json").read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError, ValueError):
            return False
        return (
            isinstance(result, dict)
            and result.get("run_id") == child_run_id
            and result.get("doc_type") == doc_type
            and result.get("status") in {"completed", "blocked", "cancelled"}
            and (
                (manifest.status == "completed" and result["status"] == "completed")
                or (
                    manifest.status in {"failed", "stalled"}
                    and result["status"] == "blocked"
                )
                or (
                    manifest.status == "cancelled"
                    and result["status"] == "cancelled"
                )
            )
            and isinstance(result.get("patch"), dict)
        )

    async def _monitor_child(
        self,
        process: Any,
        *,
        child_run_id: str,
        doc_type: str,
        run_dir: Path,
        spawn_identity: ProcessIdentity | None,
        expected_command_digest: str,
    ) -> tuple[int, list[int], str | None]:
        wait_task = asyncio.create_task(process.wait())
        heartbeat_path = run_dir / "heartbeat.json"
        last_sequence = -1
        sequences: list[int] = []
        last_progress = time.monotonic()
        stage_started = last_progress
        last_stage: str | None = None
        blocker: str | None = None
        ownership_verified = False

        while True:
            heartbeat = self._load_heartbeat(
                heartbeat_path,
                child_run_id=child_run_id,
                doc_type=doc_type,
                child_pid=process.pid,
            )
            now = time.monotonic()
            if heartbeat is not None and heartbeat["sequence"] > last_sequence:
                last_sequence = heartbeat["sequence"]
                sequences.append(last_sequence)
                last_progress = now
                if heartbeat["stage"] != last_stage:
                    last_stage = heartbeat["stage"]
                    stage_started = now
                if self.progress_callback is not None:
                    self.progress_callback(dict(heartbeat))

            manifest_deadline_expired = False
            try:
                manifest = RunManifest.model_validate_json(
                    (run_dir / "run_manifest.json").read_text(encoding="utf-8")
                )
                manifest_deadline_expired = (
                    manifest.deadline is not None
                    and time.time() > manifest.deadline
                )
                if manifest.pid != process.pid:
                    blocker = "child manifest PID does not match spawned process"
                elif _verified_process(
                    _manifest_owner(manifest),
                    self.process_probe,
                ) is not None:
                    ownership_verified = True
                elif wait_task.done() and self._terminal_child_is_valid(
                    manifest=manifest,
                    spawn_identity=spawn_identity,
                    expected_pid=process.pid,
                    expected_command_digest=expected_command_digest,
                    child_run_id=child_run_id,
                    doc_type=doc_type,
                    run_dir=run_dir,
                ):
                    ownership_verified = True
            except (FileNotFoundError, OSError, ValueError):
                manifest = None

            if wait_task.done():
                break
            if now - last_progress > self.heartbeat_timeout_seconds:
                blocker = "heartbeat deadline exceeded"
            elif now - stage_started > self._stage_watchdog_timeout(last_stage):
                blocker = f"stage deadline exceeded: {last_stage or 'startup'}"
            elif manifest_deadline_expired:
                blocker = f"manifest deadline exceeded: {manifest.stage}"

            if blocker is not None:
                cleanup_result = await self._terminate_verified_run(
                    child_run_id,
                    doc_type,
                    spawn_identity,
                )
                if process.pid not in cleanup_result.terminated_pids:
                    blocker += "; child ownership could not be verified"
                break
            await asyncio.sleep(self.monitor_interval_seconds)

        if not ownership_verified and blocker is None:
            blocker = "child process ownership was never verified"
        try:
            exit_code = await asyncio.wait_for(
                wait_task,
                timeout=(
                    self.descendant_timeout_seconds
                    + self.termination_grace_seconds
                    + 1.0
                ),
            )
        except asyncio.TimeoutError as error:
            self._lease_release_safe = False
            raise RunCleanupError(
                f"Verified child {doc_type} did not exit after watchdog cleanup"
            ) from error
        return int(exit_code), sequences, blocker

    async def _wait_for_descendants(
        self,
        child_run_id: str,
        doc_type: str,
    ) -> bool:
        manifest_path = (
            self.state_root
            / "runs"
            / child_run_id
            / doc_type
            / "run_manifest.json"
        )
        if not manifest_path.is_file():
            return False
        store = PipelineStateStore(
            self.state_root,
            run_id=child_run_id,
            doc_type=doc_type,
            process_probe=self.process_probe,
        )
        try:
            await asyncio.to_thread(
                store.wait_for_verified_descendants,
                self.descendant_timeout_seconds,
                min(self.monitor_interval_seconds, 0.1),
            )
            return False
        except DescendantExitTimeoutError:
            await asyncio.to_thread(
                store.terminate_verified_processes,
                include_owner=False,
                grace_period_seconds=self.termination_grace_seconds,
            )
            try:
                await asyncio.to_thread(
                    store.wait_for_verified_descendants,
                    self.descendant_timeout_seconds,
                    min(self.monitor_interval_seconds, 0.1),
                )
            except DescendantExitTimeoutError as error:
                self._lease_release_safe = False
                raise RunCleanupError(
                    f"Verified descendant cleanup failed for {doc_type}: {error}"
                ) from error
            return True

    def _load_child_result(
        self,
        *,
        child_run_id: str,
        doc_type: str,
        run_dir: Path,
        exit_code: int,
        blocker: str | None,
        sequences: list[int],
    ) -> SupervisorDocumentResult:
        child_result: dict[str, Any] | None = None
        result_path = run_dir / "pipeline_result.json"
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            if (
                not isinstance(loaded, dict)
                or loaded.get("run_id") != child_run_id
                or loaded.get("doc_type") != doc_type
                or loaded.get("status")
                not in {"completed", "blocked", "cancelled"}
                or not isinstance(loaded.get("patch"), dict)
            ):
                raise ValueError("result identity/schema mismatch")
            child_result = loaded
        except (FileNotFoundError, OSError, ValueError) as error:
            blocker = blocker or f"child result unavailable: {error}"

        if child_result is not None and child_result["status"] == "cancelled":
            status: Literal["completed", "blocked", "cancelled"] = "cancelled"
            blocker = blocker or child_result.get("error") or "child cancelled"
        elif (
            blocker is not None
            or exit_code != 0
            or child_result is None
            or child_result["status"] != "completed"
        ):
            status: Literal["completed", "blocked"] = "blocked"
            blocker = blocker or (
                child_result.get("error")
                if child_result is not None
                else f"child exited with status {exit_code}"
            )
        else:
            status = "completed"
        return SupervisorDocumentResult(
            doc_type=doc_type,
            status=status,
            exit_code=exit_code,
            child_result=child_result,
            blocker=blocker,
            progress_sequences=sequences,
        )

    def _persist_cancelled_child(
        self,
        *,
        child_run_id: str,
        doc_type: str,
        run_dir: Path,
    ) -> None:
        result_path = run_dir / "pipeline_result.json"
        try:
            existing = json.loads(result_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            existing = None
        if (
            isinstance(existing, dict)
            and existing.get("run_id") == child_run_id
            and existing.get("doc_type") == doc_type
            and existing.get("status") == "completed"
        ):
            return
        cancelled = {
            "run_id": child_run_id,
            "doc_type": doc_type,
            "status": "cancelled",
            "stages": [],
            "max_live_sessions": 0,
            "patch": {
                "status": "blocked",
                "target_file": None,
                "candidate_id": None,
                "candidate_path": None,
                "candidate_content": "",
                "candidate_content_hash": None,
                "source_hash": None,
                "metrics": {},
                "evidence": [
                    {
                        "kind": "supervisor_cancellation",
                        "passed": False,
                    }
                ],
            },
            "baseline_bundle_hash": None,
            "candidate_bundle_hash": None,
            "final_bundle_hash": None,
            "error": "supervisor cancelled document execution",
        }
        atomic_write_json(result_path, cancelled)
        manifest_path = run_dir / "run_manifest.json"
        try:
            manifest = RunManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError, ValueError):
            return
        if manifest.status != "completed":
            manifest.status = "cancelled"
            manifest.error_classification = "supervisor_cancelled"
            atomic_write_json(manifest_path, manifest)
        atomic_write_json(
            run_dir / "pipeline_state.json",
            {
                "schema_version": "document-pipeline-state-v1",
                "run_id": child_run_id,
                "doc_type": doc_type,
                "status": "cancelled",
                "stage": manifest.stage,
                "completed_stages": [],
                "heartbeat_sequence": manifest.sequence,
                "error": "supervisor cancelled document execution",
            },
        )

    def _persist_blocked_child(
        self,
        *,
        child_run_id: str,
        doc_type: str,
        run_dir: Path,
        error: BaseException,
    ) -> None:
        diagnostic = self._safe_diagnostic(str(error))
        atomic_write_json(
            run_dir / "pipeline_result.json",
            {
                "run_id": child_run_id,
                "doc_type": doc_type,
                "status": "blocked",
                "stages": [],
                "max_live_sessions": 0,
                "patch": {
                    "status": "blocked",
                    "target_file": None,
                    "candidate_id": None,
                    "candidate_path": None,
                    "candidate_content": "",
                    "candidate_content_hash": None,
                    "source_hash": None,
                    "metrics": {},
                    "evidence": [
                        {
                            "kind": "supervisor_exception",
                            "passed": False,
                        }
                    ],
                },
                "baseline_bundle_hash": None,
                "candidate_bundle_hash": None,
                "final_bundle_hash": None,
                "error": diagnostic,
            },
        )
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.is_file():
            return
        try:
            manifest = RunManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return
        if manifest.status != "completed":
            manifest.status = "failed"
            manifest.error_classification = type(error).__name__
            atomic_write_json(manifest_path, manifest)

    def _mark_registered_reaped(
        self,
        identity: ProcessIdentity,
        *,
        exit_code: int | None,
    ) -> None:
        if self._process_registry is None:
            raise RunCleanupError("Parent process registry is unavailable")
        self._process_registry.mark_terminal(
            identity,
            exit_code=exit_code,
        )
        self._process_registry.mark_reaped(
            identity,
            exit_code=exit_code,
        )

    async def _wait_owned_process_handle(
        self,
        process: Any,
        *,
        timeout_seconds: float,
        operation: str,
    ) -> tuple[bool, int | None, str | None]:
        try:
            exit_code = int(
                await _await_with_hard_deadline(
                    process.wait(),
                    timeout_seconds=max(timeout_seconds, 0.001),
                    operation=operation,
                )
            )
            return True, exit_code, None
        except asyncio.TimeoutError as error:
            return False, getattr(process, "returncode", None), str(error)
        except BaseException as error:
            if getattr(process, "returncode", None) is not None:
                return True, int(process.returncode), None
            return (
                False,
                None,
                f"{operation} failed: {type(error).__name__}",
            )

    async def _reap_unverified_spawn_handle(
        self,
        process: Any,
    ) -> tuple[bool, int | None, list[str]]:
        """Reap only through the exact handle returned by create_subprocess_exec."""
        errors: list[str] = []
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        except BaseException as error:
            errors.append(f"owned handle terminate failed: {type(error).__name__}")
        exited, exit_code, wait_error = await self._wait_owned_process_handle(
            process,
            timeout_seconds=self.termination_grace_seconds,
            operation="owned spawned child TERM wait",
        )
        if wait_error is not None:
            errors.append(wait_error)
        if exited:
            return True, exit_code, errors

        try:
            process.kill()
        except ProcessLookupError:
            pass
        except BaseException as error:
            errors.append(f"owned handle kill failed: {type(error).__name__}")
        exited, exit_code, wait_error = await self._wait_owned_process_handle(
            process,
            timeout_seconds=self.descendant_timeout_seconds,
            operation="owned spawned child KILL wait",
        )
        if wait_error is not None:
            errors.append(wait_error)
        return exited, exit_code, errors

    async def _probe_spawn_identity(
        self,
        process: Any,
        *,
        expected_command_digest: str,
    ) -> tuple[ProcessInfo | None, int | None]:
        """Wait briefly for the spawned PID to expose its post-exec identity."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.spawn_identity_timeout_seconds
        while True:
            process_info = self.process_probe.get_process_info(process.pid)
            if (
                process_info is not None
                and process_info.command_digest == expected_command_digest
            ):
                return process_info, None
            returncode = getattr(process, "returncode", None)
            if returncode is not None:
                return None, int(returncode)
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None, None
            await self.spawn_identity_sleep(
                min(self.spawn_identity_poll_seconds, remaining)
            )

    async def _reconcile_failed_child(
        self,
        *,
        process: Any,
        spawn_identity: ProcessIdentity,
        child_run_id: str,
        doc_type: str,
        run_dir: Path,
        error: BaseException,
    ) -> None:
        failures: list[str] = []
        try:
            cleanup_result = await self._terminate_verified_run(
                child_run_id,
                doc_type,
                spawn_identity,
            )
            failures.extend(cleanup_result.errors)
        except Exception as cleanup_error:
            failures.append(f"termination failed: {cleanup_error}")
        exit_code: int | None = getattr(process, "returncode", None)
        try:
            exit_code = int(
                await asyncio.wait_for(
                    process.wait(),
                    timeout=(
                        self.descendant_timeout_seconds
                        + self.termination_grace_seconds
                        + 1.0
                    ),
                )
            )
        except Exception as wait_error:
            failures.append(f"child exit failed: {wait_error}")
        try:
            await self._wait_for_descendants(child_run_id, doc_type)
        except Exception as descendant_error:
            failures.append(str(descendant_error))
        try:
            self._mark_registered_reaped(
                spawn_identity,
                exit_code=exit_code,
            )
        except Exception as registry_error:
            failures.append(f"registry reconciliation failed: {registry_error}")
            if self._process_registry is not None:
                try:
                    self._process_registry.mark_requires_cleanup(
                        spawn_identity,
                        exit_code=exit_code,
                    )
                except Exception:
                    pass
        self._persist_blocked_child(
            child_run_id=child_run_id,
            doc_type=doc_type,
            run_dir=run_dir,
            error=error,
        )
        if failures:
            self._lease_release_safe = False
            raise RunCleanupError("; ".join(failures))

    async def _reconcile_cancelled_child(
        self,
        *,
        process: Any,
        spawn_identity: ProcessIdentity,
        child_run_id: str,
        doc_type: str,
        run_dir: Path,
    ) -> None:
        failures: list[str] = []
        try:
            cleanup_result = await self._terminate_verified_run(
                child_run_id,
                doc_type,
                spawn_identity,
            )
            failures.extend(cleanup_result.errors)
        except Exception as error:
            failures.append(f"termination failed: {error}")
        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=(
                    self.descendant_timeout_seconds
                    + self.termination_grace_seconds
                    + 1.0
                ),
            )
        except Exception as error:
            failures.append(f"child exit failed: {error}")
        try:
            await self._wait_for_descendants(child_run_id, doc_type)
        except Exception as error:
            failures.append(str(error))
        try:
            self._mark_registered_reaped(
                spawn_identity,
                exit_code=getattr(process, "returncode", None),
            )
        except Exception as error:
            failures.append(f"registry reconciliation failed: {error}")
        self._persist_cancelled_child(
            child_run_id=child_run_id,
            doc_type=doc_type,
            run_dir=run_dir,
        )
        if failures:
            self._lease_release_safe = False
            raise RunCleanupError("; ".join(failures))

    async def _run_child(
        self,
        doc_type: str,
        *,
        child_run_id: str,
        phase: Literal[
            "full",
            "optimization",
            "shared_baseline",
            "shared_candidate",
            "final",
        ],
        final_manifest_path: Path | None,
        final_manifest_hash: str | None,
        source_revision: str,
        optimization_results: Mapping[str, SupervisorDocumentResult] | None,
        shared_candidate_path: Path | None,
    ) -> SupervisorDocumentResult:
        run_dir = self.state_root / "runs" / child_run_id / doc_type
        run_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "crawler.eval.document_pipeline",
            "--run-id",
            child_run_id,
            "--doc-type",
            doc_type,
            "--run-root",
            str(self.state_root),
            "--source-revision",
            source_revision,
        ]
        if final_manifest_path is not None:
            command.extend(["--final-manifest", str(final_manifest_path)])
        if final_manifest_hash is not None:
            command.extend(["--final-manifest-hash", final_manifest_hash])
        child_env = dict(os.environ)
        child_env["PHASE74_PIPELINE_PHASE"] = phase
        child_env["PHASE74_RUN_ID"] = child_run_id
        child_env["PHASE74_PIPELINE_ROOT"] = str(self.pipeline_root)
        child_env["PHASE74_CORPUS_DB"] = str(self.corpus_db_path)
        child_env["PHASE74_PROPOSAL_ROOT"] = str(self.proposal_root)
        child_env["PHASE74_SOURCE_ROOT"] = str(self.source_root)
        child_env["PHASE74_ARTIFACT_IMPORT_ROOTS"] = json.dumps(
            [str(path) for path in self.artifact_import_roots],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        if shared_candidate_path is not None:
            child_env["PHASE74_SHARED_CANDIDATE"] = str(
                shared_candidate_path
            )
        if optimization_results is not None:
            optimization = optimization_results[doc_type]
            optimization_result_path = (
                self.state_root
                / "runs"
                / (
                    optimization.child_result.get("run_id")
                    if isinstance(optimization.child_result, dict)
                    else ""
                )
                / doc_type
                / "pipeline_result.json"
            )
            child_env["PHASE74_OPTIMIZATION_RESULT"] = str(
                optimization_result_path
            )
        process = await self.subprocess_factory(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.source_root),
            env=child_env,
        )
        expected_command_digest = compute_command_digest(command)
        process_info, exited_before_identity = await self._probe_spawn_identity(
            process,
            expected_command_digest=expected_command_digest,
        )
        if process_info is None:
            error = RunCleanupError(
                f"unverified_spawn identity is unavailable for {doc_type}"
            )
            registered = False
            try:
                if self._process_registry is None:
                    raise RuntimeError(
                        "Initialized parent process registry is unavailable"
                    )
                self._process_registry.register_unverified_spawn(
                    process.pid,
                    run_id=child_run_id,
                    doc_type=doc_type,
                )
                registered = True
            except BaseException as registry_error:
                error.add_note(
                    "Unverified spawn registry failed: "
                    f"{type(registry_error).__name__}"
                )
            if exited_before_identity is not None:
                reaped = True
                exit_code = exited_before_identity
                cleanup_errors: list[str] = []
            else:
                reaped, exit_code, cleanup_errors = (
                    await self._reap_unverified_spawn_handle(process)
                )
            if self._process_registry is not None and registered:
                try:
                    if reaped:
                        self._process_registry.mark_unverified_reaped(
                            process.pid,
                            run_id=child_run_id,
                            doc_type=doc_type,
                            exit_code=exit_code,
                        )
                    else:
                        self._process_registry.mark_unverified_requires_cleanup(
                            process.pid,
                            run_id=child_run_id,
                            doc_type=doc_type,
                            exit_code=exit_code,
                        )
                except BaseException as registry_error:
                    registered = False
                    error.add_note(
                        "Unverified spawn reconciliation failed: "
                        f"{type(registry_error).__name__}"
                    )
            if cleanup_errors:
                error.add_note("; ".join(cleanup_errors))
            if not reaped or not registered:
                self._persist_blocked_child(
                    child_run_id=child_run_id,
                    doc_type=doc_type,
                    run_dir=run_dir,
                    error=error,
                )
                self._lease_release_safe = False
                raise error
            if exited_before_identity is not None:
                reconciled = self._load_child_result(
                    child_run_id=child_run_id,
                    doc_type=doc_type,
                    run_dir=run_dir,
                    exit_code=exit_code or 0,
                    blocker=None,
                    sequences=[],
                )
                if reconciled.child_result is not None:
                    return reconciled
            self._persist_blocked_child(
                child_run_id=child_run_id,
                doc_type=doc_type,
                run_dir=run_dir,
                error=error,
            )
            return SupervisorDocumentResult(
                doc_type=doc_type,
                status="blocked",
                exit_code=exit_code,
                child_result=None,
                blocker=str(error),
            )
        spawn_identity = ProcessIdentity(
            pid=process_info.pid,
            process_start_time=process_info.start_time,
            command_digest=process_info.command_digest,
            run_id=child_run_id,
        )
        try:
            if self._process_registry is None:
                raise RuntimeError("Parent process registry is unavailable")
            registered_identity = self._process_registry.register_observed_spawn(
                process_info,
                run_id=child_run_id,
                doc_type=doc_type,
            )
            if registered_identity != spawn_identity:
                raise RuntimeError("Parent process registry identity mismatch")
        except BaseException as registration_error:
            cleanup_result = await self._terminate_verified_run(
                child_run_id,
                doc_type,
                spawn_identity,
            )
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=(
                        self.descendant_timeout_seconds
                        + self.termination_grace_seconds
                        + 1.0
                    ),
                )
            except BaseException as wait_error:
                registration_error.add_note(
                    f"Unregistered child exit failed: {type(wait_error).__name__}"
                )
            self._lease_release_safe = False
            error = RunCleanupError(
                f"Parent registry failed for spawned child {doc_type}"
            )
            if cleanup_result.errors:
                error.add_note("; ".join(cleanup_result.errors))
            self._persist_blocked_child(
                child_run_id=child_run_id,
                doc_type=doc_type,
                run_dir=run_dir,
                error=error,
            )
            raise error from registration_error
        self._active_children += 1
        self._peak_children = max(self._peak_children, self._active_children)
        stdout_task = asyncio.create_task(
            self._drain_stream(process.stdout, run_dir / "stdout.log")
        )
        stderr_task = asyncio.create_task(
            self._drain_stream(process.stderr, run_dir / "stderr.log")
        )
        try:
            if process_info.command_digest != expected_command_digest:
                raise RuntimeError(
                    f"Spawned child argv identity mismatch for {doc_type}"
                )
            exit_code, sequences, blocker = await self._monitor_child(
                process,
                child_run_id=child_run_id,
                doc_type=doc_type,
                run_dir=run_dir,
                spawn_identity=spawn_identity,
                expected_command_digest=expected_command_digest,
            )
            self._mark_registered_reaped(
                spawn_identity,
                exit_code=exit_code,
            )
            await asyncio.gather(stdout_task, stderr_task)
            descendant_was_terminated = await self._wait_for_descendants(
                child_run_id,
                doc_type,
            )
            if descendant_was_terminated:
                blocker = blocker or (
                    "verified descendant exceeded exit timeout and was terminated"
                )
            return self._load_child_result(
                child_run_id=child_run_id,
                doc_type=doc_type,
                run_dir=run_dir,
                exit_code=exit_code,
                blocker=blocker,
                sequences=sequences,
            )
        except asyncio.CancelledError as cancellation:
            try:
                await self._reconcile_cancelled_child(
                    process=process,
                    spawn_identity=spawn_identity,
                    child_run_id=child_run_id,
                    doc_type=doc_type,
                    run_dir=run_dir,
                )
            except Exception as cleanup_error:
                cancellation.add_note(
                    f"Cancelled child cleanup failed: {cleanup_error}"
                )
            for task in (stdout_task, stderr_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                stdout_task,
                stderr_task,
                return_exceptions=True,
            )
            raise
        except Exception as error:
            cleanup_error: BaseException | None = None
            try:
                await self._reconcile_failed_child(
                    process=process,
                    spawn_identity=spawn_identity,
                    child_run_id=child_run_id,
                    doc_type=doc_type,
                    run_dir=run_dir,
                    error=error,
                )
            except BaseException as reconciliation_error:
                cleanup_error = reconciliation_error
            for task in (stdout_task, stderr_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            if cleanup_error is not None:
                raise cleanup_error from error
            return SupervisorDocumentResult(
                doc_type=doc_type,
                status="blocked",
                exit_code=getattr(process, "returncode", None),
                child_result=None,
                blocker=self._safe_diagnostic(str(error)),
            )
        finally:
            self._active_children -= 1

    async def _run_children(
        self,
        *,
        child_run_id: str | None = None,
        phase: Literal[
            "full",
            "optimization",
            "shared_baseline",
            "shared_candidate",
            "final",
        ] = "full",
        final_manifest_path: Path | None = None,
        final_manifest_hash: str | None = None,
        source_revision: str | None = None,
        optimization_results: Mapping[str, SupervisorDocumentResult] | None = None,
        shared_candidate_path: Path | None = None,
    ) -> dict[str, SupervisorDocumentResult]:
        if self._process_registry is None:
            raise RuntimeError("Initialized parent process registry is unavailable")
        effective_run_id = child_run_id or self.run_id
        effective_revision = source_revision or self.revision_resolver()
        if not re.fullmatch(r"[a-f0-9]{40,64}", effective_revision):
            raise RuntimeError("Parent source revision is unavailable")
        queue: asyncio.Queue[str] = asyncio.Queue()
        slots = asyncio.Semaphore(_PIPELINE_SLOTS)
        for doc_type in self.doc_types:
            queue.put_nowait(doc_type)
        results: dict[str, SupervisorDocumentResult] = {}
        cleanup_failures: list[RunCleanupError] = []
        stop_launching = asyncio.Event()

        async def consume() -> None:
            while True:
                try:
                    doc_type = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    async with slots:
                        if stop_launching.is_set():
                            results[doc_type] = SupervisorDocumentResult(
                                doc_type=doc_type,
                                status="cancelled",
                                exit_code=None,
                                child_result=None,
                                blocker=(
                                    "not launched after verified descendant "
                                    "cleanup failure"
                                ),
                            )
                            continue
                        try:
                            results[doc_type] = await self._run_child(
                                doc_type,
                                child_run_id=effective_run_id,
                                phase=phase,
                                final_manifest_path=final_manifest_path,
                                final_manifest_hash=final_manifest_hash,
                                source_revision=effective_revision,
                                optimization_results=optimization_results,
                                shared_candidate_path=shared_candidate_path,
                            )
                            self._document_results[doc_type] = results[doc_type]
                        except RunCleanupError as error:
                            self._lease_release_safe = False
                            stop_launching.set()
                            cleanup_failures.append(error)
                            results[doc_type] = SupervisorDocumentResult(
                                doc_type=doc_type,
                                status="blocked",
                                exit_code=None,
                                child_result=None,
                                blocker=str(error),
                            )
                            self._document_results[doc_type] = results[doc_type]
                        except Exception as error:
                            results[doc_type] = SupervisorDocumentResult(
                                doc_type=doc_type,
                                status="blocked",
                                exit_code=None,
                                child_result=None,
                                blocker=(
                                    "child spawn/supervision failed: "
                                    f"{error}"
                                ),
                            )
                            self._document_results[doc_type] = results[doc_type]
                finally:
                    queue.task_done()

        consumers = [
            asyncio.create_task(consume()) for _ in range(_PIPELINE_SLOTS)
        ]
        try:
            await queue.join()
            await asyncio.gather(*consumers)
        except asyncio.CancelledError:
            for consumer in consumers:
                consumer.cancel()
            await asyncio.gather(*consumers, return_exceptions=True)
            self._persist_exceptional_result(
                asyncio.CancelledError("supervisor children cancelled"),
                stage="children",
                status="cancelled",
            )
            raise
        if cleanup_failures:
            raise cleanup_failures[0]
        return {doc_type: results[doc_type] for doc_type in self.doc_types}

    @staticmethod
    def _metrics_accept(metrics: Any) -> tuple[bool, float]:
        if not isinstance(metrics, dict) or set(metrics) != {
            "baseline_train",
            "baseline_holdout",
            "candidate_train",
            "candidate_holdout",
        }:
            return False, 0.0
        accepted = evaluate_candidate_patch(
            metrics["baseline_train"],
            metrics["baseline_holdout"],
            metrics["candidate_train"],
            metrics["candidate_holdout"],
        )
        try:
            delta = (
                float(metrics["candidate_train"]["overall_score"])
                - float(metrics["baseline_train"]["overall_score"])
            )
        except (KeyError, TypeError, ValueError):
            return False, 0.0
        return accepted and math.isfinite(delta), delta

    def _validate_candidate(
        self,
        patch: Mapping[str, Any],
        *,
        doc_type: str | None,
        evaluated_doc_types: set[str] | None = None,
    ) -> tuple[Path, str, float]:
        target = patch.get("target_file")
        candidate_id = patch.get("candidate_id")
        candidate_content = patch.get("candidate_content")
        candidate_hash = patch.get("candidate_content_hash")
        candidate_path_value = patch.get("candidate_path")
        source_hash = patch.get("source_hash")
        evidence = patch.get("evidence")
        if (
            not isinstance(target, str)
            or not isinstance(candidate_id, str)
            or not _CANDIDATE_ID.fullmatch(candidate_id)
            or not isinstance(candidate_content, str)
            or not isinstance(candidate_hash, str)
            or candidate_hash
            != hashlib.sha256(candidate_content.encode("utf-8")).hexdigest()
            or not isinstance(candidate_path_value, str)
            or not isinstance(source_hash, str)
            or not _HASH.fullmatch(source_hash)
            or not isinstance(evidence, list)
        ):
            raise ValueError("candidate identity/content/hash evidence is incomplete")
        target_allowed, reasons, normalized = validate_target_allowlist(
            target, doc_type
        )
        if not target_allowed:
            raise ValueError("; ".join(reasons))
        target_path = (self.source_root / normalized).resolve()
        if (
            not target_path.is_relative_to(self.source_root)
            or not target_path.is_file()
            or target_path.is_symlink()
            or _file_hash(target_path) != source_hash
        ):
            raise ValueError("source compare-and-swap hash no longer matches")
        candidate_path = Path(candidate_path_value).resolve()
        expected_candidate_path = (
            self.proposal_root / candidate_id / normalized
        ).resolve()
        if (
            candidate_path != expected_candidate_path
            or not candidate_path.is_file()
            or candidate_path.is_symlink()
            or _file_hash(candidate_path) != candidate_hash
            or candidate_path.read_text(encoding="utf-8") != candidate_content
        ):
            raise ValueError("candidate artifact identity/content/hash mismatch")
        allowed, patch_reasons = validate_patch_allowlist(
            candidate_content,
            normalized,
            doc_type=doc_type,
            current_content=target_path.read_text(encoding="utf-8"),
        )
        if not allowed:
            raise ValueError("; ".join(patch_reasons))
        metrics_ok, delta = self._metrics_accept(patch.get("metrics"))
        evidence_ok = any(
            item.get("kind") == "candidate_validation"
            and item.get("passed") is True
            for item in evidence
            if isinstance(item, dict)
        ) and any(
            item.get("kind") == "metric_gate"
            and item.get("passed") is True
            for item in evidence
            if isinstance(item, dict)
        )
        if not metrics_ok or not evidence_ok:
            raise ValueError("candidate decision metrics/evidence do not recompute")
        if evaluated_doc_types is not None and set(
            patch.get("evaluated_doc_types", [])
        ) != evaluated_doc_types:
            raise ValueError("shared candidate was not evaluated across all documents")
        return target_path, normalized, delta

    def _validate_optimizer_artifact(
        self,
        *,
        child_result: Mapping[str, Any],
        patch: Mapping[str, Any],
        doc_type: str,
    ) -> dict[str, Any]:
        from crawler.eval.loop_orchestrator import (
            _publishable_optimizer_provenance,
        )

        child_run_id = child_result.get("run_id")
        if (
            not isinstance(child_run_id, str)
            or not _SAFE_NAME.fullmatch(child_run_id)
        ):
            raise ValueError("optimizer provenance has no valid child run identity")
        artifact_path = (
            self.state_root
            / "runs"
            / child_run_id
            / doc_type
            / "artifacts"
            / "optimizer.json"
        )
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError) as error:
            raise ValueError(
                f"optimizer provenance artifact is unavailable: {error}"
            ) from error
        if (
            not isinstance(artifact, dict)
            or artifact.get("schema_version") != "document-pipeline-artifact-v1"
            or artifact.get("stage") != "optimizer"
            or artifact.get("doc_type") != doc_type
            or not isinstance(artifact.get("output"), dict)
            or artifact.get("output_hash")
            != _canonical_hash(artifact["output"])
        ):
            raise ValueError("optimizer provenance artifact schema/hash is invalid")
        optimizer = artifact["output"]
        for field_name in (
            "target_file",
            "candidate_id",
            "candidate_content",
        ):
            if optimizer.get(field_name) != patch.get(field_name):
                raise ValueError(
                    f"optimizer provenance does not bind {field_name}"
                )
        if (
            hashlib.sha256(
                optimizer["candidate_content"].encode("utf-8")
            ).hexdigest()
            != patch.get("candidate_content_hash")
        ):
            raise ValueError("optimizer provenance candidate hash mismatch")
        _publishable_optimizer_provenance(optimizer)
        return optimizer

    def _validate_document_decision_artifacts(
        self,
        *,
        child_result: Mapping[str, Any],
        patch: Mapping[str, Any],
        doc_type: str,
        optimizer: Mapping[str, Any],
    ) -> None:
        child_run_id = child_result["run_id"]
        artifact_path = (
            self.state_root
            / "runs"
            / child_run_id
            / doc_type
            / "artifacts"
            / "patch_decision.json"
        )
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if (
            not isinstance(artifact, dict)
            or artifact.get("schema_version") != "document-pipeline-artifact-v1"
            or artifact.get("stage") != "patch_decision"
            or artifact.get("doc_type") != doc_type
            or artifact.get("output") != dict(patch)
            or artifact.get("output_hash") != _canonical_hash(dict(patch))
            or not isinstance(artifact.get("input_manifest"), dict)
        ):
            raise ValueError("patch decision artifact schema/hash is invalid")
        decision_input = artifact["input_manifest"]
        baseline = self._load_judge_output(
            child_run_id=child_run_id,
            doc_type=doc_type,
            stage="baseline_judge",
        )
        candidate = self._load_judge_output(
            child_run_id=child_run_id,
            doc_type=doc_type,
            stage="candidate_judge",
        )
        training_ids, holdout_ids = self._case_partitions(doc_type)
        baseline_evaluations = baseline.get("case_evaluations")
        candidate_evaluations = candidate.get("case_evaluations")
        if (
            not isinstance(baseline_evaluations, dict)
            or not isinstance(candidate_evaluations, dict)
            or set(baseline_evaluations) != training_ids | holdout_ids
            or set(candidate_evaluations) != training_ids | holdout_ids
        ):
            raise ValueError("decision Judge artifacts have incomplete coverage")
        recomputed_metrics = {
            "baseline_train": self._mean_evaluations(
                [
                    baseline_evaluations[case_id]
                    for case_id in sorted(training_ids)
                ]
            ),
            "baseline_holdout": self._mean_evaluations(
                [
                    baseline_evaluations[case_id]
                    for case_id in sorted(holdout_ids)
                ]
            ),
            "candidate_train": self._mean_evaluations(
                [
                    candidate_evaluations[case_id]
                    for case_id in sorted(training_ids)
                ]
            ),
            "candidate_holdout": self._mean_evaluations(
                [
                    candidate_evaluations[case_id]
                    for case_id in sorted(holdout_ids)
                ]
            ),
        }
        sealed = seal_holdout_findings(
            baseline,
            holdout_case_ids=holdout_ids,
            doc_type=doc_type,
        )
        if (
            patch.get("metrics") != recomputed_metrics
            or decision_input.get("optimizer_output_hash")
            != _canonical_hash(dict(optimizer))
            or decision_input.get("baseline_judge_hash")
            != _canonical_hash(baseline)
            or decision_input.get("candidate_judge_hash")
            != _canonical_hash(candidate)
            or decision_input.get("training_case_ids")
            != sorted(training_ids)
            or decision_input.get("holdout_commitment")
            != sealed["holdout_commitment"]
            or decision_input.get("evaluator") != "evaluate_candidate_patch"
        ):
            raise ValueError(
                "patch decision metrics/provenance do not recompute exactly"
            )

    def _run_git(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.source_root,
            check=True,
            capture_output=True,
            text=True,
        )

    def _git_revision(self) -> str:
        completed = self._run_git(["git", "rev-parse", "HEAD"])
        revision = completed.stdout.strip()
        if not re.fullmatch(r"[a-f0-9]{40,64}", revision):
            raise RuntimeError("Git revision is unavailable")
        return revision

    def _source_is_clean(self) -> bool:
        completed = self._run_git(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--",
                "AGENTS.md",
                "skills/document-agents",
                "skills/pdf/SKILL.md",
            ]
        )
        return not completed.stdout.strip()

    def _index_entries(self) -> list[str]:
        completed = self.git_runner(
            [
                "git",
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=ACDMRTUXB",
                "-z",
            ]
        )
        stdout = getattr(completed, "stdout", "")
        if not isinstance(stdout, str):
            raise RuntimeError("Git index inspection returned invalid output")
        return sorted(entry for entry in stdout.split("\0") if entry)

    def _assert_clean_index(self) -> None:
        staged = self._index_entries()
        if staged:
            raise RuntimeError(
                "Unrelated staged entries prevent parent application: "
                + ", ".join(staged)
            )

    def _commit_patch(
        self,
        *,
        doc_type: str,
        normalized_target: str,
        delta: float,
    ) -> str:
        self.git_runner(["git", "add", "--", normalized_target])
        staged = self._index_entries()
        if staged != [normalized_target]:
            raise RuntimeError(
                "Git index does not contain exactly the intended target: "
                + ", ".join(staged)
            )
        subject = (
            f"feat(74): apply {doc_type} SDK patch "
            f"(train delta {delta:+.6f})"
        )
        self.git_runner(
            [
                "git",
                "commit",
                "--only",
                "-m",
                subject,
                "-m",
                _TRAILER,
                "--",
                normalized_target,
            ]
        )
        revision = self.revision_resolver()
        committed = self.git_runner(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "-z",
                revision,
            ]
        )
        stdout = getattr(committed, "stdout", "")
        committed_paths = sorted(
            path for path in stdout.split("\0") if path
        ) if isinstance(stdout, str) else []
        if committed_paths != [normalized_target]:
            raise RuntimeError(
                "Commit contains paths outside the intended target: "
                + ", ".join(committed_paths)
            )
        return revision

    def _restore_uncommitted_patch(
        self,
        *,
        target_path: Path | None,
        original_content: str | None,
        normalized_target: str,
    ) -> None:
        if target_path is None or original_content is None:
            return
        try:
            commit_completed = self.source_clean_checker()
        except Exception:
            commit_completed = False
        if commit_completed:
            return
        apply_patch_atomically(target_path, original_content)
        if normalized_target:
            try:
                self.git_runner(
                    ["git", "reset", "HEAD", "--", normalized_target]
                )
            except Exception:
                pass

    def _apply_document_patches(
        self,
        results: dict[str, SupervisorDocumentResult],
    ) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        claimed_targets: set[str] = set()
        for doc_type in self.doc_types:
            result = results[doc_type]
            child = result.child_result
            patch = child.get("patch") if isinstance(child, dict) else None
            if result.status != "completed" or not isinstance(patch, dict):
                result.parent_patch_status = "blocked"
                result.blocker = result.blocker or "child did not produce a decision"
                continue
            status = patch.get("status")
            if status == "rejected":
                result.parent_patch_status = "rejected"
                continue
            if status != "accepted":
                result.parent_patch_status = "blocked"
                result.blocker = "child patch decision is missing or blocked"
                continue
            original_content: str | None = None
            target_path: Path | None = None
            normalized = ""
            try:
                optimizer = self._validate_optimizer_artifact(
                    child_result=child,
                    patch=patch,
                    doc_type=doc_type,
                )
                self._validate_document_decision_artifacts(
                    child_result=child,
                    patch=patch,
                    doc_type=doc_type,
                    optimizer=optimizer,
                )
                target_path, normalized, delta = self._validate_candidate(
                    patch,
                    doc_type=doc_type,
                )
                if normalized in claimed_targets:
                    raise ValueError(
                        f"conflicting accepted target in the same wave: {normalized}"
                    )
                claimed_targets.add(normalized)
                self._assert_clean_index()
                original_content = target_path.read_text(encoding="utf-8")
                apply_patch_atomically(target_path, patch["candidate_content"])
                commit_revision = self._commit_patch(
                    doc_type=doc_type,
                    normalized_target=normalized,
                    delta=delta,
                )
            except Exception as error:
                self._restore_uncommitted_patch(
                    target_path=target_path,
                    original_content=original_content,
                    normalized_target=normalized,
                )
                result.parent_patch_status = "blocked"
                result.blocker = f"parent patch validation/application failed: {error}"
                continue
            result.parent_patch_status = "applied"
            applied.append(
                {
                    "doc_type": doc_type,
                    "target_file": normalized,
                    "candidate_id": patch["candidate_id"],
                    "train_delta": delta,
                    "commit": commit_revision,
                }
            )
        return applied

    def _load_judge_output(
        self,
        *,
        child_run_id: str,
        doc_type: str,
        stage: str,
    ) -> dict[str, Any]:
        artifact_path = (
            self.state_root
            / "runs"
            / child_run_id
            / doc_type
            / "artifacts"
            / f"{stage}.json"
        )
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if (
            not isinstance(artifact, dict)
            or artifact.get("schema_version") != "document-pipeline-artifact-v1"
            or artifact.get("stage") != stage
            or artifact.get("doc_type") != doc_type
            or not isinstance(artifact.get("output"), dict)
            or artifact.get("output_hash")
            != _canonical_hash(artifact["output"])
        ):
            raise RuntimeError(
                f"Shared evaluation artifact is invalid: {doc_type}/{stage}"
            )
        return artifact["output"]

    def _case_partitions(self, doc_type: str) -> tuple[set[str], set[str]]:
        cases_path = (
            self.pipeline_root
            / doc_type
            / "ground_truth"
            / "ground_truth.json"
        )
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        training, holdout = split_doc_type_cases(cases, doc_type=doc_type)
        return (
            {case["opaque_case_id"] for case in training},
            {case["opaque_case_id"] for case in holdout},
        )

    @staticmethod
    def _mean_evaluations(
        evaluations: list[dict[str, Any]],
    ) -> dict[str, float]:
        if not evaluations:
            raise RuntimeError("Shared metric aggregation has no evaluations")
        metrics: dict[str, float] = {}
        for field_name in _SCORE_FIELDS:
            values = [evaluation.get(field_name) for evaluation in evaluations]
            if any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
                for value in values
            ):
                raise RuntimeError(
                    f"Shared metric {field_name} is missing or invalid"
                )
            metrics[field_name] = sum(float(value) for value in values) / len(
                values
            )
        metrics["overall_score"] = sum(metrics.values()) / len(metrics)
        return metrics

    def _shared_metrics(
        self,
        *,
        baseline_run_id: str,
        candidate_run_id: str,
    ) -> dict[str, dict[str, float]]:
        baseline_train: list[dict[str, Any]] = []
        baseline_holdout: list[dict[str, Any]] = []
        candidate_train: list[dict[str, Any]] = []
        candidate_holdout: list[dict[str, Any]] = []
        for doc_type in self.doc_types:
            training_ids, holdout_ids = self._case_partitions(doc_type)
            baseline = self._load_judge_output(
                child_run_id=baseline_run_id,
                doc_type=doc_type,
                stage="shared_baseline_judge",
            ).get("case_evaluations")
            candidate = self._load_judge_output(
                child_run_id=candidate_run_id,
                doc_type=doc_type,
                stage="shared_candidate_judge",
            ).get("case_evaluations")
            if (
                not isinstance(baseline, dict)
                or not isinstance(candidate, dict)
                or set(baseline) != training_ids | holdout_ids
                or set(candidate) != training_ids | holdout_ids
            ):
                raise RuntimeError(
                    f"Shared Judge coverage mismatch for {doc_type}"
                )
            baseline_train.extend(baseline[case_id] for case_id in training_ids)
            baseline_holdout.extend(
                baseline[case_id] for case_id in holdout_ids
            )
            candidate_train.extend(
                candidate[case_id] for case_id in training_ids
            )
            candidate_holdout.extend(
                candidate[case_id] for case_id in holdout_ids
            )
        return {
            "baseline_train": self._mean_evaluations(baseline_train),
            "baseline_holdout": self._mean_evaluations(baseline_holdout),
            "candidate_train": self._mean_evaluations(candidate_train),
            "candidate_holdout": self._mean_evaluations(candidate_holdout),
        }

    def _shared_candidate_evaluation_failures(
        self,
        results: Mapping[str, SupervisorDocumentResult],
    ) -> dict[str, dict[str, str]]:
        failures: dict[str, dict[str, str]] = {}
        semantic_error_types = {
            "CandidateBundleValidationError",
            "CopilotExecutionError",
            "JudgeExecutionError",
            "ResponseValidationError",
            "ValueError",
        }
        for doc_type, result in results.items():
            child = result.child_result
            patch = child.get("patch") if isinstance(child, dict) else None
            evidence = patch.get("evidence") if isinstance(patch, dict) else None
            if not isinstance(evidence, list):
                continue
            matching = [
                item
                for item in evidence
                if (
                    isinstance(item, dict)
                    and item.get("kind") == "shared_candidate_evaluation"
                    and item.get("passed") is False
                    and item.get("error_type") in semantic_error_types
                    and isinstance(item.get("stage"), str)
                    and isinstance(item.get("message"), str)
                )
            ]
            if len(matching) != 1:
                continue
            item = matching[0]
            failures[doc_type] = {
                "stage": item["stage"],
                "error_type": item["error_type"],
                "message": self._safe_diagnostic(item["message"]),
            }
        return dict(sorted(failures.items()))

    def _shared_training_findings(
        self,
        *,
        baseline_run_id: str,
    ) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        evaluations: dict[str, dict[str, Any]] = {}
        commitments: list[dict[str, Any]] = []
        for doc_type in self.doc_types:
            _, holdout_ids = self._case_partitions(doc_type)
            judge = self._load_judge_output(
                child_run_id=baseline_run_id,
                doc_type=doc_type,
                stage="shared_baseline_judge",
            )
            sealed = seal_holdout_findings(
                judge,
                holdout_case_ids=holdout_ids,
                doc_type=doc_type,
            )
            findings.extend(sealed.get("findings", []))
            evaluations.update(sealed.get("case_evaluations", {}))
            commitment = sealed.get("holdout_commitment")
            if not isinstance(commitment, dict):
                raise RuntimeError(
                    f"Shared holdout commitment is missing for {doc_type}"
                )
            commitments.append({"doc_type": doc_type, **commitment})
        commitment = {
            "count": sum(int(item["count"]) for item in commitments),
            "hash": _canonical_hash(commitments),
        }
        return {
            "doc_type": "shared",
            "case_evaluations": evaluations,
            "findings": findings,
            "holdout_commitment": commitment,
        }

    def _default_shared_optimizer(
        self,
        optimization_results: dict[str, SupervisorDocumentResult],
    ) -> dict[str, Any]:
        baseline_run_id = f"{self.run_id}-shared-baseline"
        baseline_results = asyncio.run(
            self._run_children(
                child_run_id=baseline_run_id,
                phase="shared_baseline",
                optimization_results=optimization_results,
            )
        )
        blocked_baselines = {
            doc_type: result.blocker
            for doc_type, result in baseline_results.items()
            if result.status == "blocked"
        }
        if blocked_baselines:
            return {
                "status": "blocked",
                "evaluated_doc_types": list(self.doc_types),
                "stage": "shared_baseline",
                "blockers": blocked_baselines,
            }
        training_findings = self._shared_training_findings(
            baseline_run_id=baseline_run_id
        )
        if not training_findings["findings"]:
            return {
                "status": "rejected",
                "target_file": "skills/pdf/SKILL.md",
                "evaluated_doc_types": list(self.doc_types),
                "baseline_run_id": baseline_run_id,
                "reason": "shared baseline produced no training findings",
            }

        target_file = "skills/pdf/SKILL.md"
        source_path = self.source_root / target_file
        source_content = source_path.read_text(encoding="utf-8")
        shared_run_id = f"{self.run_id}-shared-optimizer"
        shared_store = PipelineStateStore(
            self.state_root,
            run_id=shared_run_id,
            doc_type="shared",
        )
        shared_store.transition_stage("optimizer", status="in_progress")
        shared_store.manifest.deadline = (
            time.time()
            + _MODEL_STAGE_TIMEOUTS["optimizer"]
            + self.descendant_timeout_seconds
            + self.termination_grace_seconds
        )
        shared_store._save_manifest()
        shared_store.heartbeat(
            stage="optimizer",
            item=target_file,
            completed=0,
            expected=1,
        )
        shared_runtime_root = self.runtime_root / shared_run_id
        shared_runtime_root.mkdir(parents=True, exist_ok=True)
        shared_runtime = CopilotSdkRuntime(
            base_directory=shared_runtime_root,
            descendant_registrar=shared_store.add_descendant_pid,
            client_env={**os.environ, "PHASE74_RUN_ID": shared_run_id},
        )
        try:
            with shared_store.periodic_heartbeat(
                stage="optimizer",
                item=target_file,
                completed=0,
                expected=1,
                attempt=1,
                interval_seconds=min(30.0, self.heartbeat_timeout_seconds / 2),
            ):
                optimizer = run_candidate_optimization_pass(
                    doc_type=None,
                    training_findings=training_findings,
                    current_skills={target_file: source_content},
                    proposal_sandbox_root=self.proposal_root,
                    target_file=target_file,
                    runtime=shared_runtime,
                )
            shared_store.heartbeat(
                stage="optimizer",
                item=target_file,
                completed=1,
                expected=1,
            )
            shared_store.transition_stage("optimizer", status="completed")
        except Exception:
            shared_store.transition_stage("optimizer", status="failed")
            raise
        finally:
            try:
                shared_store.wait_for_verified_descendants(
                    self.descendant_timeout_seconds
                )
            except DescendantExitTimeoutError:
                shared_store.terminate_verified_processes(
                    include_owner=False,
                    grace_period_seconds=self.termination_grace_seconds,
                )
                try:
                    shared_store.wait_for_verified_descendants(
                        self.descendant_timeout_seconds
                    )
                except DescendantExitTimeoutError as error:
                    self._lease_release_safe = False
                    raise RunCleanupError(
                        "Shared optimizer verified descendant survived cleanup"
                    ) from error
        from crawler.eval.loop_orchestrator import (
            _publishable_optimizer_provenance,
        )

        _publishable_optimizer_provenance(optimizer)
        candidate_id = optimizer["candidate_id"]
        candidate_content = optimizer["candidate_content"]
        candidate_path = (
            self.proposal_root / candidate_id / target_file
        ).resolve()
        base_decision = {
            "target_file": target_file,
            "candidate_id": candidate_id,
            "candidate_path": str(candidate_path),
            "candidate_content": candidate_content,
            "candidate_content_hash": hashlib.sha256(
                candidate_content.encode("utf-8")
            ).hexdigest(),
            "source_hash": hashlib.sha256(
                source_content.encode("utf-8")
            ).hexdigest(),
            "evaluated_doc_types": list(self.doc_types),
            "baseline_run_id": baseline_run_id,
            "optimizer_result": optimizer,
        }
        if not optimizer["is_valid"]:
            return {
                **base_decision,
                "status": "rejected",
                "metrics": {},
                "evidence": [
                    {
                        "kind": "candidate_validation",
                        "passed": False,
                        "reasons": optimizer["rejection_reasons"],
                    }
                ],
            }

        candidate_run_id = f"{self.run_id}-shared-candidate"
        candidate_results = asyncio.run(
            self._run_children(
                child_run_id=candidate_run_id,
                phase="shared_candidate",
                optimization_results=optimization_results,
                shared_candidate_path=candidate_path,
            )
        )
        blocked_candidates = {
            doc_type: result.blocker
            for doc_type, result in candidate_results.items()
            if result.status == "blocked"
        }
        if blocked_candidates:
            return {
                **base_decision,
                "status": "blocked",
                "candidate_run_id": candidate_run_id,
                "blockers": blocked_candidates,
            }
        candidate_evaluation_failures = (
            self._shared_candidate_evaluation_failures(candidate_results)
        )
        if candidate_evaluation_failures:
            return {
                **base_decision,
                "status": "rejected",
                "candidate_run_id": candidate_run_id,
                "metrics": {},
                "reason": "shared_candidate_evaluation_invalid",
                "evidence": [
                    {
                        "kind": "candidate_validation",
                        "passed": False,
                        "reasons": [
                            "shared_candidate_evaluation_invalid"
                        ],
                        "failures": candidate_evaluation_failures,
                    }
                ],
            }
        metrics = self._shared_metrics(
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
        )
        accepted, _ = self._metrics_accept(metrics)
        return {
            **base_decision,
            "status": "accepted" if accepted else "rejected",
            "candidate_run_id": candidate_run_id,
            "metrics": metrics,
            "evidence": [
                {
                    "kind": "candidate_validation",
                    "passed": True,
                    "reasons": [],
                },
                {
                    "kind": "metric_gate",
                    "evaluator": "evaluate_candidate_patch",
                    "passed": accepted,
                },
            ],
        }

    @staticmethod
    def _validate_shared_optimizer_provenance(
        decision: Mapping[str, Any],
    ) -> None:
        from crawler.eval.loop_orchestrator import (
            _publishable_optimizer_provenance,
        )

        optimizer = decision.get("optimizer_result")
        if not isinstance(optimizer, dict):
            raise ValueError("shared optimizer provenance is unavailable")
        _publishable_optimizer_provenance(optimizer)
        for field_name in ("target_file", "candidate_id", "candidate_content"):
            if optimizer.get(field_name) != decision.get(field_name):
                raise ValueError(
                    f"shared optimizer provenance does not bind {field_name}"
                )

    def _run_shared_optimizer(
        self,
        results: dict[str, SupervisorDocumentResult],
    ) -> dict[str, Any]:
        decision = (
            self.shared_optimizer(results)
            if self.shared_optimizer is not None
            else self._default_shared_optimizer(results)
        )
        if not isinstance(decision, dict):
            raise RuntimeError("Shared optimizer returned an invalid decision")
        if decision.get("status") != "accepted":
            return dict(decision)
        target_path: Path | None = None
        original_content: str | None = None
        normalized = ""
        try:
            self._validate_shared_optimizer_provenance(decision)
            target_path, normalized, delta = self._validate_candidate(
                decision,
                doc_type=None,
                evaluated_doc_types=set(self.doc_types),
            )
            self._assert_clean_index()
            original_content = target_path.read_text(encoding="utf-8")
            apply_patch_atomically(target_path, decision["candidate_content"])
            commit = self._commit_patch(
                doc_type="shared",
                normalized_target=normalized,
                delta=delta,
            )
        except Exception:
            self._restore_uncommitted_patch(
                target_path=target_path,
                original_content=original_content,
                normalized_target=normalized,
            )
            raise
        return {**decision, "commit": commit, "train_delta": delta}

    def _build_bundle(self, doc_type: str) -> dict[str, Any]:
        return build_public_review_bundle(
            doc_type,
            corpus_db_path=self.corpus_db_path,
            skills_dir=self.source_root / "skills" / "document-agents",
            shared_skill_path=self.source_root / "skills" / "pdf" / "SKILL.md",
        )

    def _freeze_final_manifest(
        self,
    ) -> tuple[Path, str]:
        if self._optimization_active:
            raise RuntimeError("Optimization and final manifest freeze may not overlap")
        if not self.source_clean_checker():
            raise RuntimeError("Source drift detected before final manifest freeze")
        revision = self.revision_resolver()
        bundles: dict[str, str] = {}
        source_hashes: dict[str, str] = {}
        for doc_type in self.doc_types:
            bundle = self.bundle_builder(doc_type)
            if (
                not isinstance(bundle, dict)
                or bundle.get("doc_type") != doc_type
                or not isinstance(bundle.get("content"), str)
                or not isinstance(bundle.get("bundle_hash"), str)
                or bundle["bundle_hash"]
                != hashlib.sha256(bundle["content"].encode("utf-8")).hexdigest()
            ):
                raise RuntimeError(
                    f"Final public bundle validation failed for {doc_type}"
                )
            bundles[doc_type] = bundle["bundle_hash"]
            target_allowed, _, normalized = validate_target_allowlist(
                f"skills/document-agents/{doc_type.replace('_', '-')}.md",
                doc_type,
            )
            if not target_allowed:
                from crawler.eval.public_bundle import DOC_TYPE_TO_SKILL

                stem = DOC_TYPE_TO_SKILL.get(
                    doc_type,
                    doc_type.replace("_", "-"),
                )
                normalized = f"skills/document-agents/{stem}.md"
            source_path = self.source_root / normalized
            if source_path.is_file():
                source_hashes[normalized] = _file_hash(source_path)
        shared_path = self.source_root / "skills" / "pdf" / "SKILL.md"
        if shared_path.is_file():
            source_hashes["skills/pdf/SKILL.md"] = _file_hash(shared_path)
        if self.revision_resolver() != revision or not self.source_clean_checker():
            raise RuntimeError("Source drift detected while freezing final manifest")

        manifest = {
            "schema_version": "phase74-final-manifest-v1",
            "run_id": self.run_id,
            "git_revision": revision,
            "bundle_hashes": dict(sorted(bundles.items())),
            "source_hashes": dict(sorted(source_hashes.items())),
            "optimization_complete": True,
            "created_at": _utc_now(),
        }
        manifest_hash = _canonical_hash(manifest)
        persisted = {**manifest, "manifest_hash": manifest_hash}
        manifest_path = (
            self.state_root / "runs" / self.run_id / "final_manifest.json"
        )
        atomic_write_json(manifest_path, persisted)
        if json.loads(manifest_path.read_text(encoding="utf-8")) != persisted:
            raise RuntimeError("Final manifest atomic verification failed")
        return manifest_path, manifest_hash

    def _validate_final_bindings(
        self,
        results: dict[str, SupervisorDocumentResult],
        *,
        manifest_path: Path,
        manifest_hash: str,
    ) -> None:
        persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundles = persisted["bundle_hashes"]
        for doc_type, result in results.items():
            child_hash = (
                result.child_result.get("final_bundle_hash")
                if isinstance(result.child_result, dict)
                else None
            )
            if child_hash is None and not self.require_complete_dataset:
                continue
            if child_hash != bundles[doc_type]:
                result.status = "blocked"
                result.parent_patch_status = "blocked"
                result.blocker = (
                    "final Worker/Judge bundle does not bind to frozen manifest"
                )
                continue
            if self.separate_final_phase and isinstance(
                result.child_result, dict
            ):
                final_run_id = result.child_result["run_id"]
                artifacts_root = (
                    self.state_root
                    / "runs"
                    / final_run_id
                    / doc_type
                    / "artifacts"
                )
                for stage in ("final_workers", "final_judge"):
                    try:
                        artifact = json.loads(
                            (artifacts_root / f"{stage}.json").read_text(
                                encoding="utf-8"
                            )
                        )
                    except (FileNotFoundError, OSError, ValueError):
                        if self.require_complete_dataset:
                            result.status = "blocked"
                            result.parent_patch_status = "blocked"
                            result.blocker = (
                                f"{stage} artifact is unavailable for final binding"
                            )
                        continue
                    if (
                        not isinstance(artifact, dict)
                        or artifact.get("input_manifest", {}).get(
                            "final_manifest_hash"
                        )
                        != manifest_hash
                    ):
                        result.status = "blocked"
                        result.parent_patch_status = "blocked"
                        result.blocker = (
                            f"{stage} does not bind the immutable final manifest"
                        )

    def _verified_supervisor_processes_remain(self) -> bool:
        if self._process_registry is not None:
            try:
                if any(
                    _verified_process(record, self.process_probe) is not None
                    for record in self._process_registry.records()
                ):
                    return True
            except (OSError, ValueError):
                return True
        runs_root = self.state_root / "runs"
        if not runs_root.is_dir():
            return False
        for manifest_path in runs_root.glob("**/run_manifest.json"):
            try:
                manifest = RunManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            if not (
                manifest.run_id == self.run_id
                or manifest.run_id.startswith(f"{self.run_id}-")
            ):
                continue
            if any(
                _verified_process(identity, self.process_probe) is not None
                for identity in manifest.descendant_pids
            ):
                return True
            if manifest.status in {"pending", "in_progress"} and (
                _verified_process(
                    _manifest_owner(manifest),
                    self.process_probe,
                )
                is not None
            ):
                return True
        return False

    def _safe_diagnostic(self, value: str) -> str:
        sanitized = value
        replacements = {
            self.source_root: "<source_root>",
            self.pipeline_root: "<pipeline_root>",
            self.state_root: "<state_root>",
            self.corpus_db_path: "<corpus_db>",
            self.proposal_root: "<proposal_root>",
            self.runtime_root: "<runtime_root>",
        }
        for path, label in sorted(
            replacements.items(),
            key=lambda item: len(str(item[0])),
            reverse=True,
        ):
            sanitized = sanitized.replace(str(path), label)
        return sanitized

    def _live_bound_process_identities(self) -> list[dict[str, Any]]:
        runs_root = self.state_root / "runs"
        if not runs_root.is_dir():
            return []
        lease_key = (
            (
                self._lease.pid,
                self._lease.process_start_time,
                self._lease.command_digest,
            )
            if self._lease is not None
            else None
        )
        identities: dict[tuple[int, float, str, str], dict[str, Any]] = {}
        if self._process_registry is not None:
            try:
                registry_records = self._process_registry.records()
            except (OSError, ValueError):
                registry_records = []
            for record in registry_records:
                process = self.process_probe.get_process_info(record.pid)
                verified = (
                    process is not None
                    and _verified_process(record, self.process_probe) is not None
                )
                if not verified and not (
                    process is None and self.process_probe.is_running(record.pid)
                ):
                    continue
                identity_key = (
                    record.pid,
                    record.process_start_time,
                    record.command_digest,
                )
                key = (*identity_key, record.run_id)
                identities[key] = {
                    "role": "child",
                    "run_id": record.run_id,
                    "doc_type": record.doc_type,
                    "pid": record.pid,
                    "process_start_time": record.process_start_time,
                    "command_digest": record.command_digest,
                    "verified": verified,
                    "status": record.status,
                }
        for manifest_path in runs_root.glob("**/run_manifest.json"):
            try:
                manifest = RunManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            if not (
                manifest.run_id == self.run_id
                or manifest.run_id.startswith(f"{self.run_id}-")
            ):
                continue
            candidates = [
                ("owner", _manifest_owner(manifest)),
                *[
                    ("descendant", identity)
                    for identity in manifest.descendant_pids
                ],
            ]
            for role, identity in candidates:
                identity_key = (
                    identity.pid,
                    identity.process_start_time,
                    identity.command_digest,
                )
                if lease_key is not None and identity_key == lease_key:
                    continue
                process = self.process_probe.get_process_info(identity.pid)
                verified = (
                    process is not None
                    and _verified_process(identity, self.process_probe) is not None
                )
                if not verified and not (
                    process is None
                    and self.process_probe.is_running(identity.pid)
                ):
                    continue
                key = (*identity_key, identity.run_id)
                identities[key] = {
                    "role": role,
                    "run_id": identity.run_id,
                    "doc_type": manifest.doc_type,
                    "pid": identity.pid,
                    "process_start_time": identity.process_start_time,
                    "command_digest": identity.command_digest,
                    "verified": verified,
                }
        return sorted(
            identities.values(),
            key=lambda item: (
                item["run_id"],
                item["doc_type"],
                item["pid"],
            ),
        )

    def _persist_exceptional_result(
        self,
        error: BaseException,
        *,
        stage: str,
        status: Literal["blocked", "cancelled"] | None = None,
    ) -> None:
        identities = self._live_bound_process_identities()
        affected_doc_types = {
            identity["doc_type"]
            for identity in identities
            if identity["doc_type"] in self.doc_types
        }
        if any(
            identity["doc_type"] == "__preflight__"
            for identity in identities
        ):
            affected_doc_types.update(self.doc_types)
        owning_lease_retained = (
            self._lease is not None
            and self.state_root.joinpath("active_lease.json").is_file()
        )
        if owning_lease_retained and not identities:
            affected_doc_types.update(self.doc_types)
        terminal_status: Literal["blocked", "cancelled"] = status or (
            "cancelled"
            if isinstance(error, asyncio.CancelledError)
            else "blocked"
        )
        documents: dict[str, dict[str, Any]] = {}
        for doc_type in self.doc_types:
            existing = self._document_results.get(doc_type)
            requires_cleanup = doc_type in affected_doc_types
            document_status = (
                "blocked"
                if requires_cleanup
                else (
                    existing.status
                    if existing is not None
                    else terminal_status
                )
            )
            blocker = (
                "parent reconciliation requires verified process cleanup"
                if requires_cleanup
                else (
                    existing.blocker
                    if existing is not None
                    else f"supervisor stopped during {stage}"
                )
            )
            documents[doc_type] = {
                "doc_type": doc_type,
                "status": document_status,
                "exit_code": existing.exit_code if existing is not None else None,
                "parent_patch_status": (
                    "blocked"
                    if requires_cleanup
                    else (
                        existing.parent_patch_status
                        if existing is not None
                        else "blocked"
                    )
                ),
                "blocker": self._safe_diagnostic(blocker or ""),
                "progress_sequences": (
                    list(existing.progress_sequences)
                    if existing is not None
                    else []
                ),
                "requires_cleanup": requires_cleanup,
            }

        requires_cleanup = bool(identities) or owning_lease_retained
        atomic_write_json(
            self.state_root
            / "runs"
            / self.run_id
            / "supervisor_result.json",
            {
                "schema_version": "phase74-supervisor-result-v2",
                "run_id": self.run_id,
                "status": terminal_status,
                "stage": stage,
                "requires_cleanup": requires_cleanup,
                "lease_status": (
                    "retained"
                    if self.state_root.joinpath("active_lease.json").is_file()
                    else "released_or_unacquired"
                ),
                "error": {
                    "type": type(error).__name__,
                    "message": self._safe_diagnostic(str(error)),
                },
                "process_identities": identities,
                "document_results": documents,
                "peak_concurrency": self._peak_children,
            },
        )

    def release_retained_lease(self) -> LeaseReleaseResult:
        """Release a retained lease only after a fresh registry/manifest scan."""
        if self._lease is None:
            return LeaseReleaseResult(
                run_id=self.run_id,
                errors=["No retained owning lease is available"],
            )
        return self._release_owning_lease(explicit_recovery=True)

    def run(self) -> SupervisorRunResult:
        """Run all configured pipelines under one repository-wide live lease."""
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._document_results = {}
        self._current_stage = "lease_acquisition"
        try:
            self._lease = PipelineRunLease.acquire(
                self.state_root,
                run_id=self.run_id,
                process_probe=self.process_probe,
            )
            self._initialize_process_registry()
            self._current_stage = "preflight"
            preflight = self._run_owned_preflight()
            self._optimization_active = True
            optimization_revision = self.revision_resolver()
            self._current_stage = "optimization_children"
            optimization_results = asyncio.run(
                self._run_children(
                    child_run_id=(
                        f"{self.run_id}-optimization"
                        if self.separate_final_phase
                        else self.run_id
                    ),
                    phase=(
                        "optimization"
                        if self.separate_final_phase
                        else "full"
                    ),
                    source_revision=optimization_revision,
                )
            )
            self._current_stage = "apply_document_patches"
            applied_patches = self._apply_document_patches(
                optimization_results
            )
            self._current_stage = "shared_optimizer"
            try:
                shared_decision = self._run_shared_optimizer(
                    optimization_results
                )
            except RunCleanupError:
                raise
            except Exception as error:
                shared_decision = {
                    "status": "blocked",
                    "evaluated_doc_types": list(self.doc_types),
                    "error": str(error),
                }
            self._optimization_active = False
            self._current_stage = "freeze_final_manifest"
            manifest_path, manifest_hash = self._freeze_final_manifest()
            if self.separate_final_phase:
                final_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                self._current_stage = "final_children"
                document_results = asyncio.run(
                    self._run_children(
                        child_run_id=f"{self.run_id}-final",
                        phase="final",
                        final_manifest_path=manifest_path,
                        final_manifest_hash=manifest_hash,
                        source_revision=final_manifest["git_revision"],
                        optimization_results=optimization_results,
                    )
                )
                for doc_type in self.doc_types:
                    optimization = optimization_results[doc_type]
                    final = document_results[doc_type]
                    final.parent_patch_status = (
                        optimization.parent_patch_status
                    )
                    if (
                        optimization.status == "blocked"
                        or optimization.parent_patch_status == "blocked"
                    ):
                        final.status = "blocked"
                        final.blocker = "; ".join(
                            part
                            for part in (
                                optimization.blocker,
                                final.blocker,
                            )
                            if part
                        )
            else:
                document_results = optimization_results
            self._document_results = dict(document_results)
            self._current_stage = "final_validation"
            self._validate_final_bindings(
                document_results,
                manifest_path=manifest_path,
                manifest_hash=manifest_hash,
            )
            status: Literal["completed", "blocked"] = (
                "completed"
                if all(
                    result.status == "completed"
                    and result.parent_patch_status != "blocked"
                    for result in document_results.values()
                )
                and shared_decision.get("status") != "blocked"
                else "blocked"
            )
            run_result = SupervisorRunResult(
                run_id=self.run_id,
                status=status,
                preflight=preflight,
                document_results=document_results,
                peak_concurrency=self._peak_children,
                applied_patches=applied_patches,
                shared_decision=shared_decision,
                final_manifest_path=str(manifest_path),
                final_manifest_hash=manifest_hash,
            )
            self._current_stage = "lease_reconciliation"
            release = self._release_owning_lease()
            if not release.released:
                raise RunCleanupError(
                    "Supervisor lease reconciliation failed"
                    + (
                        ": " + "; ".join(release.errors)
                        if release.errors
                        else ""
                    )
                )
            self._lease = None
            atomic_write_json(
                self.state_root
                / "runs"
                / self.run_id
                / "supervisor_result.json",
                _jsonable(run_result),
            )
            return run_result
        except BaseException as error:
            if self._lease is not None:
                try:
                    release = self._release_owning_lease()
                except BaseException as release_error:
                    error.add_note(
                        "Lease reconciliation raised "
                        f"{type(release_error).__name__}"
                    )
                else:
                    if release.released:
                        self._lease = None
                    elif release.errors:
                        error.add_note(
                            "Lease retained: " + "; ".join(release.errors)
                        )
            self._persist_exceptional_result(
                error,
                stage=self._current_stage,
            )
            raise
        finally:
            self._optimization_active = False


def cleanup(
    state_root: Path | None = None,
    *,
    target_root: Path | None = None,
    apply: bool = False,
    stale_threshold_seconds: float = 300.0,
    process_probe: ProcessProbe | None = None,
    grace_period_seconds: float = 5.0,
) -> CleanupResult:
    """Audit or apply manifest-owned stalled-state cleanup."""
    if state_root is not None and target_root is not None:
        raise ValueError("state_root and target_root are mutually exclusive")
    target_root = (
        _validate_cleanup_target_root(target_root)
        if target_root is not None
        else None
    )
    state_root = (
        target_root / "reports" / "phase74_sdk_runs"
        if target_root is not None
        else Path(state_root or _STATE_ROOT)
    )
    audit_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + f"-{uuid.uuid4().hex[:8]}"
    )
    audit_dir = state_root / audit_id
    result = cleanup_stalled_runs(
        state_root,
        stale_threshold_seconds=stale_threshold_seconds,
        process_probe=process_probe,
        dry_run=not apply,
        grace_period_seconds=grace_period_seconds,
    )
    _quarantine_manifest_run_dirs(
        state_root,
        audit_dir=audit_dir,
        result=result,
        apply=apply,
        label_root=target_root or _REPO_ROOT,
    )
    if target_root is not None:
        _cleanup_legacy_checkout_artifacts(
            target_root,
            audit_dir=audit_dir,
            result=result,
            apply=apply,
            stale_threshold_seconds=stale_threshold_seconds,
        )
    audit_path = audit_dir / "cleanup_audit.json"
    result.audit_path = _cleanup_path_label(
        audit_path,
        target_root or _REPO_ROOT,
    )
    atomic_write_json(
        audit_path,
        {
            "schema_version": "phase74-cleanup-audit-v1",
            "mode": "apply" if apply else "dry-run",
            "created_at": _utc_now(),
            "target_root": "." if target_root is not None else None,
            "retained": [
                action
                for action in result.actions
                if action.get("action") == "retained"
            ],
            "quarantined": [
                action
                for action in result.actions
                if action.get("action") == "quarantined"
            ],
            "removed": [
                action
                for action in result.actions
                if action.get("action") == "removed"
            ],
            "result": result.model_dump(mode="json"),
        },
    )
    return result


def _quarantine_manifest_run_dirs(
    state_root: Path,
    *,
    audit_dir: Path,
    result: CleanupResult,
    apply: bool,
    label_root: Path,
) -> None:
    """Move reconciled run directories out of the authoritative runs namespace."""
    runs_root = state_root / "runs"
    planned_paths = (
        [Path(path) for path in result.quarantined_paths]
        if apply
        else [Path(path).parent for path in result.stale_manifests]
    )
    result.quarantined_paths = []
    for source in sorted(set(planned_paths), key=str):
        try:
            relative = source.resolve(strict=True).relative_to(
                runs_root.resolve(strict=True)
            )
        except (OSError, ValueError):
            result.errors.append(
                "Manifest quarantine skipped for path outside runs namespace"
            )
            continue
        if (
            len(relative.parts) != 2
            or source.is_symlink()
            or not (source / "run_manifest.json").is_file()
        ):
            result.errors.append(
                "Manifest quarantine skipped for invalid run directory shape"
            )
            continue
        destination = audit_dir / "quarantine" / "runs" / relative
        if apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
        _record_cleanup_action(
            result,
            action="quarantined",
            path=source,
            target_root=label_root,
            reason=(
                "reconciled_manifest_run"
                if apply
                else "dry_run:reconciled_manifest_run"
            ),
            destination=destination,
        )


def _validate_cleanup_target_root(target_root: Path) -> Path:
    """Fail closed unless an explicit cleanup target is a project checkout."""
    root = Path(target_root).expanduser().resolve(strict=True)
    required = (
        root / ".git",
        root / "crawler" / "eval",
        root / "reports",
    )
    if not all(path.exists() for path in required):
        raise ValueError(
            "cleanup --target-root must name a project checkout containing "
            ".git, crawler/eval, and reports"
        )
    return root


def _cleanup_path_label(path: Path, target_root: Path) -> str:
    """Return a publish-safe relative audit label when possible."""
    try:
        return path.resolve(strict=False).relative_to(
            target_root.resolve(strict=True)
        ).as_posix()
    except (OSError, ValueError):
        return path.name


def _path_owner_pids(path: Path) -> list[int]:
    """Find processes with a cwd or open descriptor inside one candidate tree."""
    resolved = path.resolve(strict=True)
    owners: set[int] = set()
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    for process_dir in proc_root.iterdir():
        if not process_dir.name.isdigit():
            continue
        links = [process_dir / "cwd"]
        fd_root = process_dir / "fd"
        try:
            if fd_root.is_dir():
                links.extend(fd_root.iterdir())
        except OSError:
            continue
        for link in links:
            try:
                linked = link.resolve(strict=True)
                linked.relative_to(resolved)
            except (OSError, ValueError):
                continue
            owners.add(int(process_dir.name))
            break
    return sorted(owners)


def _interactive_copilot_pids() -> list[int]:
    """Identify unbound interactive Copilot processes for explicit retention."""
    retained: list[int] = []
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return retained
    for process_dir in proc_root.iterdir():
        if not process_dir.name.isdigit():
            continue
        try:
            command = (process_dir / "cmdline").read_bytes().split(b"\0")
            executable = Path(command[0].decode(errors="replace")).name
            arguments = [
                part.decode(errors="replace") for part in command[1:] if part
            ]
        except (OSError, IndexError):
            continue
        if executable == "copilot" and not any(
            argument == "--run-id" or argument.startswith("--run-id=")
            for argument in arguments
        ):
            retained.append(int(process_dir.name))
    return sorted(retained)


def _tree_is_stale(path: Path, stale_threshold_seconds: float) -> bool:
    if (
        not math.isfinite(stale_threshold_seconds)
        or stale_threshold_seconds < 0
    ):
        raise ValueError("stale_threshold_seconds must be finite and non-negative")
    newest_mtime = path.stat().st_mtime
    for child in path.rglob("*"):
        if child.is_symlink():
            return False
        newest_mtime = max(newest_mtime, child.stat().st_mtime)
    return time.time() - newest_mtime > stale_threshold_seconds


def _legacy_staging_tree_is_owned(path: Path) -> bool:
    """Recognize only legacy TemporaryDirectory PDF staging trees."""
    if not path.is_dir() or path.is_symlink():
        return False
    if re.fullmatch(r"tmp[A-Za-z0-9_]+", path.name) is None:
        return False
    for child in path.iterdir():
        if (
            not child.is_file()
            or child.is_symlink()
            or re.fullmatch(r"[a-f0-9]{32}\.pdf", child.name) is None
        ):
            return False
    return True


def _record_cleanup_action(
    result: CleanupResult,
    *,
    action: Literal["retained", "quarantined", "removed"],
    path: Path,
    target_root: Path,
    reason: str,
    destination: Path | None = None,
    owner_pids: list[int] | None = None,
) -> None:
    label = _cleanup_path_label(path, target_root)
    record: dict[str, Any] = {
        "action": action,
        "path": label,
        "reason": reason,
    }
    if destination is not None:
        record["destination"] = _cleanup_path_label(destination, target_root)
    if owner_pids:
        record["owner_pids"] = owner_pids
    result.actions.append(record)
    collection = {
        "retained": result.retained_paths,
        "quarantined": result.quarantined_paths,
        "removed": result.removed_paths,
    }[action]
    collection.append(label)


def _cleanup_legacy_checkout_artifacts(
    target_root: Path,
    *,
    audit_dir: Path,
    result: CleanupResult,
    apply: bool,
    stale_threshold_seconds: float,
) -> None:
    """Quarantine only narrow, structurally owned legacy Phase 74 partials."""
    reports_root = target_root / "reports"
    candidates: list[tuple[Path, str]] = []
    for staging_name in ("worker_staging", "judge_staging"):
        staging_root = reports_root / staging_name
        if not staging_root.is_dir():
            continue
        for child in sorted(staging_root.iterdir()):
            if _legacy_staging_tree_is_owned(child):
                candidates.append((child, f"abandoned_{staging_name}"))
            else:
                _record_cleanup_action(
                    result,
                    action="retained",
                    path=child,
                    target_root=target_root,
                    reason="unrecognized_staging_shape",
                )

    iterations_root = reports_root / "phase74_iterations"
    for partial_name in ("iter_final", "final_pass"):
        partial = iterations_root / partial_name
        if partial.is_dir() and not any(partial.iterdir()):
            candidates.append((partial, "empty_partial_final_namespace"))

    proposals_root = iterations_root / "iter_1" / "proposals"
    if proposals_root.is_dir():
        for candidate in sorted(proposals_root.iterdir()):
            if (
                candidate.is_dir()
                and not candidate.is_symlink()
                and _CANDIDATE_ID.fullmatch(candidate.name)
                and not any(candidate.iterdir())
            ):
                candidates.append((candidate, "empty_partial_candidate"))
            elif candidate.is_dir():
                _record_cleanup_action(
                    result,
                    action="retained",
                    path=candidate,
                    target_root=target_root,
                    reason="historical_candidate_evidence",
                )

    for historical in (
        iterations_root / "iter_1" / "checkpoints",
        iterations_root / "iter_00_baseline",
        iterations_root / "loop_summary.json",
    ):
        if historical.exists():
            _record_cleanup_action(
                result,
                action="retained",
                path=historical,
                target_root=target_root,
                reason="historical_diagnostic_evidence",
            )

    result.retained_processes.extend(_interactive_copilot_pids())
    for pid in result.retained_processes:
        result.actions.append(
            {
                "action": "retained",
                "kind": "process",
                "pid": pid,
                "reason": "unbound_interactive_copilot",
            }
        )

    for candidate, reason in candidates:
        if not _tree_is_stale(candidate, stale_threshold_seconds):
            _record_cleanup_action(
                result,
                action="retained",
                path=candidate,
                target_root=target_root,
                reason="not_stale",
            )
            continue
        owner_pids = _path_owner_pids(candidate)
        if owner_pids:
            _record_cleanup_action(
                result,
                action="retained",
                path=candidate,
                target_root=target_root,
                reason="live_process_owns_path",
                owner_pids=owner_pids,
            )
            continue
        destination = (
            audit_dir
            / "quarantine"
            / candidate.relative_to(target_root)
        )
        if apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            candidate.replace(destination)
        _record_cleanup_action(
            result,
            action="quarantined",
            path=candidate,
            target_root=target_root,
            reason=reason if apply else f"dry_run:{reason}",
            destination=destination,
        )


def preflight(**kwargs: Any) -> PreflightReport:
    """Run preflight under the same exclusive lease used by live execution."""
    return SdkPipelineOrchestrator(**kwargs).preflight()


def _load_completed_stage_output(
    state_root: Path,
    *,
    child_run_id: str,
    doc_type: str,
    stage: str,
) -> dict[str, Any]:
    artifact_path = (
        state_root
        / "runs"
        / child_run_id
        / doc_type
        / "artifacts"
        / f"{stage}.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if (
        not isinstance(artifact, dict)
        or artifact.get("schema_version")
        != "document-pipeline-artifact-v1"
        or artifact.get("stage") != stage
        or artifact.get("doc_type") != doc_type
        or not isinstance(artifact.get("output"), dict)
        or artifact.get("output_hash")
        != _canonical_hash(artifact["output"])
    ):
        raise RuntimeError(
            f"Completed artifact is invalid: {doc_type}/{stage}"
        )
    return artifact["output"]


def publish_completed_run(
    run_id: str,
    *,
    source_root: Path = _REPO_ROOT,
    state_root: Path = _STATE_ROOT,
    pipeline_root: Path = _PIPELINES_ROOT,
) -> dict[str, Any]:
    """Publish one completed SDK run into canonical Phase 74 gate artifacts."""
    if not _SAFE_NAME.fullmatch(run_id):
        raise ValueError("run_id must be a path-safe identifier")
    supervisor_path = (
        state_root / "runs" / run_id / "supervisor_result.json"
    )
    supervisor = json.loads(supervisor_path.read_text(encoding="utf-8"))
    if (
        not isinstance(supervisor, dict)
        or supervisor.get("run_id") != run_id
        or supervisor.get("status") != "completed"
        or set(supervisor.get("document_results", {}))
        != {doc_type.value for doc_type in ExpressEntryDocType}
    ):
        raise RuntimeError("Only a complete 23-document SDK run may publish")
    final_manifest_path = (
        state_root / "runs" / run_id / "final_manifest.json"
    )
    final_manifest = json.loads(
        final_manifest_path.read_text(encoding="utf-8")
    )
    unsigned_manifest = {
        key: value
        for key, value in final_manifest.items()
        if key != "manifest_hash"
    }
    if (
        final_manifest.get("schema_version")
        != "phase74-final-manifest-v1"
        or final_manifest.get("manifest_hash")
        != _canonical_hash(unsigned_manifest)
        or final_manifest.get("manifest_hash")
        != supervisor.get("final_manifest_hash")
    ):
        raise RuntimeError("Completed final manifest is invalid")

    baseline_doc_types: dict[str, Any] = {}
    final_doc_types: dict[str, Any] = {}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    total_final_workers = 0

    for doc_type in sorted(final_manifest["bundle_hashes"]):
        optimization_run = f"{run_id}-optimization"
        final_run = f"{run_id}-final"
        baseline_workers = _load_completed_stage_output(
            state_root,
            child_run_id=optimization_run,
            doc_type=doc_type,
            stage="baseline_workers",
        )
        baseline_judge = _load_completed_stage_output(
            state_root,
            child_run_id=optimization_run,
            doc_type=doc_type,
            stage="baseline_judge",
        )
        optimizer = _load_completed_stage_output(
            state_root,
            child_run_id=optimization_run,
            doc_type=doc_type,
            stage="optimizer",
        )
        decision = _load_completed_stage_output(
            state_root,
            child_run_id=optimization_run,
            doc_type=doc_type,
            stage="patch_decision",
        )
        final_workers = _load_completed_stage_output(
            state_root,
            child_run_id=final_run,
            doc_type=doc_type,
            stage="final_workers",
        )
        final_judge = _load_completed_stage_output(
            state_root,
            child_run_id=final_run,
            doc_type=doc_type,
            stage="final_judge",
        )
        if (
            set(final_workers) != set(baseline_workers)
            or len(final_workers) not in (10, 12)
            or set(final_judge.get("case_evaluations", {}))
            != set(final_workers)
        ):
            raise RuntimeError(
                f"Published final coverage is incomplete for {doc_type}"
            )
        total_final_workers += len(final_workers)

        cases = json.loads(
            (
                pipeline_root
                / doc_type
                / "ground_truth"
                / "ground_truth.json"
            ).read_text(encoding="utf-8")
        )
        _, holdout = split_doc_type_cases(cases, doc_type=doc_type)
        holdout_ids = {
            case["opaque_case_id"] for case in holdout
        }
        sealed = seal_holdout_findings(
            baseline_judge,
            holdout_case_ids=holdout_ids,
            doc_type=doc_type,
        )

        final_dir = (
            pipeline_root / doc_type / "iterations" / "iter_sdk_final"
        )
        final_dir.mkdir(parents=True, exist_ok=True)
        for raw_dir_name in ("worker_reports", "judge_eval"):
            raw_dir = final_dir / raw_dir_name
            if raw_dir.is_dir():
                shutil.rmtree(raw_dir)
        worker_evidence = {
            "schema_version": "phase74-final-worker-evidence-v1",
            "run_id": run_id,
            "doc_type": doc_type,
            "worker_count": len(final_workers),
            "case_ids": sorted(final_workers),
            "report_hashes": {
                case_id: _canonical_hash(report)
                for case_id, report in sorted(final_workers.items())
            },
            "provenance_digests": {
                case_id: report["_provenance"]["provenance_digest"]
                for case_id, report in sorted(final_workers.items())
            },
            "basis_redacted_from_publishable_evidence": True,
            "raw_artifacts_location": "gitignored_sdk_run_state",
            "final_manifest_hash": final_manifest["manifest_hash"],
            "git_revision": final_manifest["git_revision"],
        }
        judge_evidence = {
            "schema_version": "phase74-final-judge-evidence-v1",
            "run_id": run_id,
            "doc_type": doc_type,
            "case_ids": sorted(final_judge["case_evaluations"]),
            "case_evaluations": final_judge["case_evaluations"],
            "finding_count": len(final_judge.get("findings", [])),
            "patch_recommendation_count": len(
                final_judge.get("patch_recommendations", [])
            ),
            "raw_output_hash": _canonical_hash(final_judge),
            "provenance": final_judge["_provenance"],
            "narrative_redacted_from_publishable_evidence": True,
            "raw_artifacts_location": "gitignored_sdk_run_state",
            "final_manifest_hash": final_manifest["manifest_hash"],
            "git_revision": final_manifest["git_revision"],
        }
        atomic_write_json(
            final_dir / "worker_evidence.json",
            worker_evidence,
        )
        atomic_write_json(
            final_dir / "judge_evidence.json",
            judge_evidence,
        )
        atomic_write_json(
            final_dir / "doc_type_eval.json",
            judge_evidence,
        )

        record = {
            "iteration": 1,
            "decision": decision["status"],
            "proposal_completed": True,
            "doc_type": doc_type,
            "target_file": optimizer["target_file"],
            "candidate_id": optimizer["candidate_id"],
            "optimizer_provenance": optimizer["_provenance"],
        }
        collection = accepted if decision["status"] == "accepted" else rejected
        collection.append(record)
        proposals_dir = final_dir / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            proposals_dir / "accepted_patches.json",
            [record] if decision["status"] == "accepted" else [],
        )
        atomic_write_json(
            proposals_dir / "rejected_patches.json",
            [record] if decision["status"] == "rejected" else [],
        )
        baseline_doc_types[doc_type] = {
            "doc_type": doc_type,
            "total_cases": len(baseline_workers),
            "judge_batch": baseline_judge,
            "sealed_findings": sealed,
        }
        final_doc_types[doc_type] = {
            "doc_type": doc_type,
            "total_cases": len(final_workers),
            "judge_batch": final_judge,
            "final_manifest_hash": final_manifest["manifest_hash"],
            "git_revision": final_manifest["git_revision"],
        }

    if total_final_workers != _EXPECTED_PDFS:
        raise RuntimeError(
            f"Published final Worker count is {total_final_workers}, "
            f"expected {_EXPECTED_PDFS}"
        )
    reports_iterations = source_root / "reports" / "phase74_iterations"
    reports_iterations.mkdir(parents=True, exist_ok=True)
    optimization_summary = {
        "accepted_patches": accepted,
        "rejected_patches": rejected,
        "blocked_patches": [],
        "shared_decision": supervisor["shared_decision"],
    }
    loop_summary = {
        "schema_version": "phase74-sdk-loop-summary-v1",
        "run_id": run_id,
        "engine": "copilot-sdk",
        "baseline": {"doc_types": baseline_doc_types},
        "optimization": optimization_summary,
        "final_pass": {
            "total_doc_types": len(final_doc_types),
            "total_cases": total_final_workers,
            "doc_types": final_doc_types,
            "final_manifest_hash": final_manifest["manifest_hash"],
            "git_revision": final_manifest["git_revision"],
        },
    }
    atomic_write_json(
        reports_iterations / "loop_summary.json",
        loop_summary,
    )
    final_reports_dir = reports_iterations / "iter_sdk_final"
    final_reports_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        final_reports_dir / "accepted_patches.json",
        accepted,
    )
    atomic_write_json(
        final_reports_dir / "rejected_patches.json",
        rejected,
    )
    atomic_write_json(
        final_reports_dir / "final_summary.json",
        loop_summary["final_pass"],
    )
    from crawler.eval.phase74_evidence import (
        publish_committed_phase74_evidence,
    )

    evidence_root = source_root / "crawler" / "eval" / "phase74_evidence"
    committed_manifest = publish_committed_phase74_evidence(
        run_id,
        source_root=source_root,
        state_root=state_root,
        pipeline_root=pipeline_root,
        output_root=evidence_root,
    )
    for doc_type in final_doc_types:
        final_dir = (
            pipeline_root / doc_type / "iterations" / "iter_sdk_final"
        )
        if final_dir.exists():
            shutil.rmtree(final_dir)
        final_dir.mkdir(parents=True)
        document_prefix = f"documents/{doc_type}/"
        document_files = {
            path: digest
            for path, digest in committed_manifest["files"].items()
            if path.startswith(document_prefix)
        }
        atomic_write_json(
            final_dir / "committed_evidence.json",
            {
                "schema_version": "phase74-committed-evidence-link-v1",
                "doc_type": doc_type,
                "evidence_root": "crawler/eval/phase74_evidence",
                "evidence_manifest_hash": committed_manifest["manifest_hash"],
                "document_files": document_files,
                "final_revision": committed_manifest["final_revision"],
                "final_manifest_hash": committed_manifest[
                    "final_manifest_hash"
                ],
            },
        )
    return {
        "run_id": run_id,
        "status": "published",
        "document_types": len(final_doc_types),
        "final_workers": total_final_workers,
        "final_judges": len(final_doc_types),
        "accepted_patches": len(accepted),
        "rejected_patches": len(rejected),
        "final_manifest_hash": final_manifest["manifest_hash"],
        "evidence_manifest_hash": committed_manifest["manifest_hash"],
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: _jsonable(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Five-pipeline Copilot SDK supervisor"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--concurrency", type=int, default=_PIPELINE_SLOTS)
    run_parser.add_argument("--fresh", action="store_true")
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_mode = cleanup_parser.add_mutually_exclusive_group(required=True)
    cleanup_mode.add_argument("--dry-run", action="store_true")
    cleanup_mode.add_argument("--apply", action="store_true")
    cleanup_parser.add_argument(
        "--target-root",
        type=Path,
        help=(
            "explicit project checkout whose manifest state and narrow legacy "
            "Phase 74 partial namespaces may be audited"
        ),
    )
    subparsers.add_parser("preflight")
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "run":
            if args.concurrency != _PIPELINE_SLOTS:
                parser.error("live SDK supervision requires exactly five slots")
            result = SdkPipelineOrchestrator().run()
        elif args.command == "cleanup":
            result = cleanup(
                apply=args.apply,
                target_root=args.target_root,
            )
        elif args.command == "preflight":
            result = preflight()
        else:
            result = publish_completed_run(args.run_id)
    except (ActiveRunError, RuntimeError, ValueError, OSError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "command": args.command,
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                },
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {"ok": True, "command": args.command, "result": _jsonable(result)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
