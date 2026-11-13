from __future__ import annotations

import asyncio
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any

import pytest

from crawler.eval import document_pipeline, sdk_pipeline_orchestrator
from crawler.eval.agent_runtime import AgentTimeoutError
from crawler.eval.document_pipeline import DocumentPipelineInputSnapshot
from crawler.eval.pipeline_state import (
    ActiveRunError,
    PipelineRunLease,
    ProcessInfo,
    ProcessIdentity,
    ProcessProbe,
    RunManifest,
    atomic_write_json,
    compute_command_digest,
)
from crawler.eval.sdk_pipeline_orchestrator import (
    REQUIRED_MODELS,
    RuntimePreflight,
    SdkPipelineOrchestrator,
    SupervisorDocumentResult,
    _default_runtime_preflight,
    cleanup,
)


class RecordingProbe(ProcessProbe):
    def __init__(self) -> None:
        super().__init__()
        self.signals: list[tuple[int, int]] = []
        self.fake_pids: set[int] = set()

    def add(self, *args: Any, **kwargs: Any) -> Any:
        process = super().add(*args, **kwargs)
        self.fake_pids.add(process.pid)
        return process

    def is_running(self, pid: int) -> bool:
        if pid in self.fake_pids:
            return pid in self._mock_processes
        return super().is_running(pid)

    def terminate_process(self, pid: int, sig: int = signal.SIGTERM) -> bool:
        self.signals.append((pid, sig))
        self.remove(pid)
        return True


class StubbornProbe(RecordingProbe):
    def terminate_process(self, pid: int, sig: int = signal.SIGTERM) -> bool:
        self.signals.append((pid, sig))
        return True


class DelayedVisibilityProbe(RecordingProbe):
    def __init__(self, misses: int) -> None:
        super().__init__()
        self.misses = misses
        self.lookups: dict[int, int] = {}

    def get_process_info(self, pid: int) -> Any:
        if pid in self.fake_pids:
            seen = self.lookups.get(pid, 0)
            self.lookups[pid] = seen + 1
            if seen < self.misses:
                return None
        return super().get_process_info(pid)


class ExecTransitionProbe(RecordingProbe):
    def __init__(self) -> None:
        super().__init__()
        self.lookups: dict[int, int] = {}

    def get_process_info(self, pid: int) -> Any:
        process = super().get_process_info(pid)
        if (
            process is not None
            and pid in self.fake_pids
            and "crawler.eval.document_pipeline" in process.command
        ):
            seen = self.lookups.get(pid, 0)
            self.lookups[pid] = seen + 1
            if seen == 0:
                return ProcessInfo(
                    pid=process.pid,
                    command=[
                        sys.executable,
                        "-m",
                        "crawler.eval.sdk_pipeline_orchestrator",
                    ],
                    start_time=process.start_time,
                )
        return process


def _runtime_preflight(
    _: Path,
    _run_id: str | None = None,
    _register_descendant: Any = None,
) -> RuntimePreflight:
    return RuntimePreflight(
        sdk_version="1.0.8",
        runtime_version="1.0.8",
        sdk_protocol_version=3,
        runtime_protocol_version=3,
        authenticated=True,
        models=sorted(REQUIRED_MODELS),
        runtime_ready=True,
    )


def _input_inspector(
    config: document_pipeline.DocumentPipelineConfig,
) -> DocumentPipelineInputSnapshot:
    doc_root = Path(config.pipeline_root) / config.doc_type
    ground_truth = doc_root / "ground_truth" / "ground_truth.json"
    research = doc_root / "research" / "research.json"
    cases = json.loads(ground_truth.read_text(encoding="utf-8"))
    paths = [ground_truth, research]
    paths.extend(
        doc_root / "ground_truth" / "pdfs" / f"{case['opaque_case_id']}.pdf"
        for case in cases
    )
    return DocumentPipelineInputSnapshot(
        doc_type=config.doc_type,
        case_ids=tuple(sorted(case["opaque_case_id"] for case in cases)),
        input_hashes={
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
        source_hash="0" * 64,
        bundle_hash="1" * 64,
    )


def _write_pipeline_inputs(root: Path, doc_types: list[str]) -> None:
    for index, doc_type in enumerate(doc_types):
        doc_root = root / doc_type
        pdf_root = doc_root / "ground_truth" / "pdfs"
        research_root = doc_root / "research"
        pdf_root.mkdir(parents=True)
        research_root.mkdir()
        left = f"{index * 2 + 1:032x}"
        right = f"{index * 2 + 2:032x}"
        pdf = b"%PDF-1.4\n%%EOF"
        digest = hashlib.sha256(pdf).hexdigest()
        cases = [
            {
                "opaque_case_id": left,
                "sibling_case_id": right,
                "doc_type": doc_type,
                "pdf_sha256": digest,
            },
            {
                "opaque_case_id": right,
                "sibling_case_id": left,
                "doc_type": doc_type,
                "pdf_sha256": digest,
            },
        ]
        (pdf_root / f"{left}.pdf").write_bytes(pdf)
        (pdf_root / f"{right}.pdf").write_bytes(pdf)
        (doc_root / "ground_truth" / "ground_truth.json").write_text(
            json.dumps(cases),
            encoding="utf-8",
        )
        (research_root / "research.json").write_text(
            json.dumps({"doc_type": doc_type}),
            encoding="utf-8",
        )


def _result(
    run_id: str,
    doc_type: str,
    *,
    final_bundle_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "doc_type": doc_type,
        "status": "completed",
        "stages": ["final_judge"],
        "max_live_sessions": 1,
        "patch": {
            "status": "rejected",
            "target_file": None,
            "candidate_id": None,
            "candidate_path": None,
            "candidate_content": "",
            "candidate_content_hash": None,
            "source_hash": None,
            "metrics": {},
            "evidence": [{"kind": "candidate_validation", "passed": False}],
        },
        "baseline_bundle_hash": None,
        "candidate_bundle_hash": None,
        "final_bundle_hash": final_bundle_hash,
        "error": None,
    }


class FakeProcess:
    def __init__(
        self,
        *,
        pid: int,
        command: list[str],
        state_root: Path,
        probe: RecordingProbe,
        start_gate: asyncio.Event,
        starts: list[str],
        active: set[str],
        descendant_exit: dict[str, float],
        stale: bool,
        phase: str,
        final_bundle_hash: str | None,
    ) -> None:
        self.pid = pid
        self.command = command
        self.state_root = state_root
        self.probe = probe
        self.start_gate = start_gate
        self.starts = starts
        self.active = active
        self.descendant_exit = descendant_exit
        self.stale = stale
        self.phase = phase
        self.final_bundle_hash = final_bundle_hash
        self.returncode: int | None = None
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.run_id = command[command.index("--run-id") + 1]
        self.doc_type = command[command.index("--doc-type") + 1]
        self.run_dir = state_root / "runs" / self.run_id / self.doc_type
        self.run_dir.mkdir(parents=True, exist_ok=True)

        child = probe.add(
            pid=pid,
            command=command,
            run_id=self.run_id,
            start_time=float(pid),
        )
        descendant_command = [
            "copilot-runtime",
            "--run-id",
            self.run_id,
            "--doc-type",
            self.doc_type,
        ]
        descendant = probe.add(
            pid=pid + 10_000,
            command=descendant_command,
            run_id=self.run_id,
            start_time=float(pid + 10_000),
        )
        manifest = RunManifest(
            run_id=self.run_id,
            doc_type=self.doc_type,
            pid=pid,
            process_start_time=child.start_time,
            command_digest=child.command_digest,
            stage="baseline_workers",
            status="in_progress",
            descendant_pids=[
                ProcessIdentity(
                    pid=descendant.pid,
                    process_start_time=descendant.start_time,
                    command_digest=descendant.command_digest,
                    run_id=self.run_id,
                )
            ],
        )
        atomic_write_json(self.run_dir / "run_manifest.json", manifest)
        atomic_write_json(
            self.run_dir / "heartbeat.json",
            {
                "run_id": self.run_id,
                "doc_type": self.doc_type,
                "stage": "baseline_workers",
                "item": "case",
                "completed": 1,
                "expected": 2,
                "sequence": 1,
                "timestamp": manifest.heartbeat_at,
                "pid": pid,
                "process_start_time": child.start_time,
            },
        )
        self.stdout.feed_data(f"started {self.doc_type}\n".encode())
        self.stderr.feed_data(f"diagnostic {self.doc_type}\n".encode())
        self.task = asyncio.create_task(self._complete())

    async def _complete(self) -> int:
        if self.stale:
            while self.probe.is_running(self.pid):
                await asyncio.sleep(0.002)
            self.returncode = -signal.SIGTERM
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            return self.returncode

        while not self.start_gate.is_set():
            if not self.probe.is_running(self.pid):
                self.returncode = -signal.SIGTERM
                self.stdout.feed_eof()
                self.stderr.feed_eof()
                return self.returncode
            await asyncio.sleep(0.002)
        await asyncio.sleep(0.02)
        atomic_write_json(
            self.run_dir / "pipeline_result.json",
            _result(
                self.run_id,
                self.doc_type,
                final_bundle_hash=self.final_bundle_hash,
            ),
        )
        manifest = RunManifest.model_validate_json(
            (self.run_dir / "run_manifest.json").read_text(encoding="utf-8")
        )
        manifest.status = "completed"
        atomic_write_json(self.run_dir / "run_manifest.json", manifest)
        self.probe.remove(self.pid)
        self.active.remove(self.doc_type)

        async def exit_descendant() -> None:
            await asyncio.sleep(self.descendant_exit.get(self.doc_type, 0.0))
            self.probe.remove(self.pid + 10_000)

        asyncio.create_task(exit_descendant())
        self.returncode = 0
        self.stdout.feed_data(f"completed {self.doc_type}\n".encode())
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        return 0

    async def wait(self) -> int:
        return await self.task


class FakeProcessFactory:
    def __init__(
        self,
        state_root: Path,
        probe: RecordingProbe,
        *,
        stale_doc_type: str | None = None,
        descendant_exit: dict[str, float] | None = None,
    ) -> None:
        self.state_root = state_root
        self.probe = probe
        self.stale_doc_type = stale_doc_type
        self.descendant_exit = descendant_exit or {}
        self.starts: list[str] = []
        self.pids: dict[str, int] = {}
        self.phases: list[str] = []
        self.active: set[str] = set()
        self.peak = 0
        self.start_gate = asyncio.Event()

    async def __call__(self, *command: str, **kwargs: Any) -> FakeProcess:
        assert command[:3] == (
            sys.executable,
            "-m",
            "crawler.eval.document_pipeline",
        )
        assert kwargs["stdout"] == asyncio.subprocess.PIPE
        assert kwargs["stderr"] == asyncio.subprocess.PIPE
        assert command[command.index("--source-revision") + 1] == "a" * 40
        doc_type = command[command.index("--doc-type") + 1]
        env = kwargs.get("env") or {}
        phase = env.get("PHASE74_PIPELINE_PHASE", "full")
        final_bundle_hash = None
        final_manifest = (
            command[command.index("--final-manifest") + 1]
            if "--final-manifest" in command
            else None
        )
        if phase == "final" and final_manifest:
            manifest = json.loads(Path(final_manifest).read_text(encoding="utf-8"))
            final_bundle_hash = manifest["bundle_hashes"][doc_type]
        self.starts.append(doc_type)
        self.phases.append(phase)
        self.pids[doc_type] = 1_000 + len(self.starts)
        self.active.add(doc_type)
        self.peak = max(self.peak, len(self.active))
        if len(self.starts) >= 5 or self.stale_doc_type is not None:
            self.start_gate.set()
        return FakeProcess(
            pid=1_000 + len(self.starts),
            command=list(command),
            state_root=self.state_root,
            probe=self.probe,
            start_gate=self.start_gate,
            starts=self.starts,
            active=self.active,
            descendant_exit=self.descendant_exit,
            stale=doc_type == self.stale_doc_type,
            phase=phase,
            final_bundle_hash=final_bundle_hash,
        )


class ManifestlessProcess:
    def __init__(
        self,
        *,
        pid: int,
        command: list[str],
        probe: RecordingProbe,
        exit_immediately: bool = False,
    ) -> None:
        self.pid = pid
        self.command = command
        self.probe = probe
        self.returncode: int | None = None
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        run_id = command[command.index("--run-id") + 1]
        probe.add(
            pid=pid,
            command=command,
            run_id=run_id,
            start_time=float(pid),
        )
        self.exit_immediately = exit_immediately

    async def wait(self) -> int:
        if self.exit_immediately:
            self.probe.remove(self.pid)
            self.returncode = 1
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            return 1
        while self.probe.is_running(self.pid):
            await asyncio.sleep(0.001)
        self.returncode = -signal.SIGTERM
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        return self.returncode


class UnverifiedSpawnProcess:
    def __init__(self, *, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.terminate_calls = 0
        self.kill_calls = 0
        self._exited = asyncio.Event()

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = -signal.SIGTERM
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._exited.set()

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -signal.SIGKILL
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._exited.set()

    async def wait(self) -> int:
        await self._exited.wait()
        assert self.returncode is not None
        return self.returncode


class UnreapableSpawnProcess(UnverifiedSpawnProcess):
    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


class FastExitBeforeIdentityProcess:
    def __init__(
        self,
        *,
        command: list[str],
        state_root: Path,
    ) -> None:
        self.pid = 8_097
        self.returncode = 0
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self.terminate_calls = 0
        self.kill_calls = 0
        run_id = command[command.index("--run-id") + 1]
        doc_type = command[command.index("--doc-type") + 1]
        run_dir = state_root / "runs" / run_id / doc_type
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            run_dir / "pipeline_result.json",
            _result(run_id, doc_type),
        )
        atomic_write_json(
            run_dir / "run_manifest.json",
            RunManifest(
                run_id=run_id,
                doc_type=doc_type,
                pid=self.pid,
                process_start_time=0.0,
                command_digest=compute_command_digest(command),
                stage="patch_decision",
                status="completed",
            ),
        )

    async def wait(self) -> int:
        return 0

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1


def _orchestrator(
    tmp_path: Path,
    doc_types: list[str],
    factory: FakeProcessFactory,
    probe: RecordingProbe,
    **kwargs: Any,
) -> SdkPipelineOrchestrator:
    pipeline_root = tmp_path / "pipelines"
    _write_pipeline_inputs(pipeline_root, doc_types)
    corpus = tmp_path / "corpus.db"
    corpus.write_bytes(b"corpus")
    runtime_preflight = kwargs.pop("runtime_preflight", _runtime_preflight)
    shared_optimizer = kwargs.pop(
        "shared_optimizer",
        lambda _: {
            "status": "rejected",
            "evaluated_doc_types": list(doc_types),
            "reason": "injected non-live test decision",
        },
    )
    return SdkPipelineOrchestrator(
        source_root=tmp_path,
        pipeline_root=pipeline_root,
        state_root=factory.state_root,
        corpus_db_path=corpus,
        proposal_root=tmp_path / "proposals",
        runtime_root=tmp_path / "runtime",
        doc_types=doc_types,
        require_complete_dataset=False,
        runtime_preflight=runtime_preflight,
        ignored_path_checker=lambda _: True,
        dirty_input_finder=lambda _: [],
        input_inspector=_input_inspector,
        subprocess_factory=kwargs.pop("subprocess_factory", factory),
        process_probe=probe,
        heartbeat_timeout_seconds=kwargs.pop("heartbeat_timeout_seconds", 0.2),
        stage_timeout_seconds=kwargs.pop("stage_timeout_seconds", 1.0),
        descendant_timeout_seconds=kwargs.pop("descendant_timeout_seconds", 1.0),
        monitor_interval_seconds=0.005,
        termination_grace_seconds=kwargs.pop("termination_grace_seconds", 0),
        bundle_builder=lambda doc_type: {
            "doc_type": doc_type,
            "content": doc_type,
            "bundle_hash": hashlib.sha256(doc_type.encode()).hexdigest(),
        },
        revision_resolver=lambda: "a" * 40,
        source_clean_checker=lambda: True,
        shared_optimizer=shared_optimizer,
        **kwargs,
    )


def test_five_pipeline_slots_are_fair_and_wait_for_descendants(tmp_path: Path) -> None:
    doc_types = [f"doc_{index}" for index in range(6)]
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(
        state_root,
        probe,
        descendant_exit={"doc_0": 0.08},
    )
    progress: list[tuple[str, int]] = []
    orchestrator = _orchestrator(
        tmp_path,
        doc_types,
        factory,
        probe,
        progress_callback=lambda heartbeat: progress.append(
            (heartbeat["doc_type"], heartbeat["sequence"])
        ),
    )

    result = orchestrator.run()

    assert factory.peak == 5
    assert factory.starts[:5] == doc_types[:5]
    assert factory.starts[5] == "doc_5"
    assert set(result.document_results) == set(doc_types)
    assert result.peak_concurrency == 5
    assert {doc_type for doc_type, _ in progress} >= set(doc_types[:5])
    assert not probe._mock_processes
    for doc_type in doc_types:
        run_dir = state_root / "runs" / result.run_id / doc_type
        assert f"started {doc_type}" in (run_dir / "stdout.log").read_text()
        assert f"diagnostic {doc_type}" in (run_dir / "stderr.log").read_text()


def test_repository_wide_lease_rejects_second_supervisor(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    orchestrator = _orchestrator(tmp_path, ["doc_0"], factory, probe)
    lease = PipelineRunLease.acquire(
        state_root,
        run_id="already-running",
        process_probe=probe,
    )
    try:
        with pytest.raises(ActiveRunError):
            orchestrator.run()
    finally:
        lease.release()

    assert factory.starts == []


def test_optimization_finishes_before_frozen_manifest_final_phase(
    tmp_path: Path,
) -> None:
    doc_types = [f"doc_{index}" for index in range(6)]
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    orchestrator = _orchestrator(
        tmp_path,
        doc_types,
        factory,
        probe,
        separate_final_phase=True,
        heartbeat_timeout_seconds=2.0,
        stage_timeout_seconds=2.0,
    )

    result = orchestrator.run()

    assert factory.phases == ["optimization"] * 6 + ["final"] * 6
    assert result.status == "completed"
    assert all(
        item.child_result["run_id"].endswith("-final")
        for item in result.document_results.values()
    )
    final_manifest = json.loads(Path(result.final_manifest_path).read_text())
    assert final_manifest["manifest_hash"] == result.final_manifest_hash
    assert set(final_manifest["bundle_hashes"]) == set(doc_types)


def test_shared_candidate_semantic_failures_are_candidate_rejections(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
    )
    results = {
        "doc_0": SupervisorDocumentResult(
            doc_type="doc_0",
            status="completed",
            exit_code=0,
            child_result={
                "patch": {
                    "evidence": [
                        {
                            "kind": "shared_candidate_evaluation",
                            "passed": False,
                            "stage": "shared_candidate_judge",
                            "error_type": "JudgeExecutionError",
                            "message": "corrected response is not JSON",
                        }
                    ]
                }
            },
        )
    }

    failures = orchestrator._shared_candidate_evaluation_failures(results)

    assert failures == {
        "doc_0": {
            "stage": "shared_candidate_judge",
            "error_type": "JudgeExecutionError",
            "message": "corrected response is not JSON",
        }
    }


def test_watchdog_terminates_only_verified_stale_child(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(
        state_root,
        probe,
        stale_doc_type="doc_stale",
    )
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_stale", "doc_healthy"],
        factory,
        probe,
        heartbeat_timeout_seconds=0.2,
        stage_timeout_seconds=0.2,
    )

    result = orchestrator.run()

    stale_pid = factory.pids["doc_stale"]
    healthy_pid = factory.pids["doc_healthy"]
    assert any(pid == stale_pid for pid, _ in probe.signals)
    assert all(pid != healthy_pid for pid, _ in probe.signals)
    assert result.document_results["doc_stale"].status == "blocked"
    assert result.document_results["doc_healthy"].status == "completed"


def test_descendant_timeout_terminates_verified_descendant_before_reusing_slot(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(
        state_root,
        probe,
        descendant_exit={"doc_0": 10.0},
    )
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0", "doc_1"],
        factory,
        probe,
        descendant_timeout_seconds=0.01,
    )

    result = orchestrator.run()

    assert result.document_results["doc_0"].status == "blocked"
    assert any(pid == factory.pids["doc_0"] + 10_000 for pid, _ in probe.signals)
    assert factory.starts == ["doc_0", "doc_1"]
    assert not probe._mock_processes


def test_unreaped_verified_descendant_keeps_supervisor_lease(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = StubbornProbe()
    factory = FakeProcessFactory(
        state_root,
        probe,
        descendant_exit={"doc_0": 10.0},
    )
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        descendant_timeout_seconds=0.01,
    )
    factory.start_gate.set()

    with pytest.raises(RuntimeError, match="descendant"):
        orchestrator.run()

    assert (state_root / "active_lease.json").is_file()
    descendant_pid = factory.pids["doc_0"] + 10_000
    assert probe.is_running(descendant_pid)
    durable = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_result.json"
        ).read_text(encoding="utf-8")
    )
    assert durable["status"] == "blocked"
    assert durable["stage"] == "optimization_children"
    assert durable["requires_cleanup"] is True
    assert durable["document_results"]["doc_0"]["status"] == "blocked"
    assert durable["document_results"]["doc_0"]["requires_cleanup"] is True
    assert {
        identity["pid"] for identity in durable["process_identities"]
    } == {descendant_pid}
    assert all("path" not in identity for identity in durable["process_identities"])

    probe.terminate_process = RecordingProbe.terminate_process.__get__(
        probe,
        StubbornProbe,
    )
    recovery = cleanup(
        state_root,
        apply=True,
        stale_threshold_seconds=0,
        process_probe=probe,
        grace_period_seconds=0,
    )
    assert recovery.lease_retained_reason == "active_owner"
    assert not probe.is_running(descendant_pid)
    released = orchestrator.release_retained_lease()
    assert released.released
    assert not (state_root / "active_lease.json").exists()


def test_run_owned_preflight_registers_exact_fake_runtime_identity(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    observed: list[dict[str, Any]] = []

    def tracked_preflight(
        _: Path,
        run_id: str,
        register_descendant: Any,
    ) -> RuntimePreflight:
        runtime = probe.add(
            pid=901,
            command=["copilot-runtime", "--stdio"],
            run_id=run_id,
            start_time=901.5,
        )
        register_descendant(runtime.pid)
        manifest = json.loads(
            (
                state_root
                / "runs"
                / run_id
                / "__preflight__"
                / "run_manifest.json"
            ).read_text(encoding="utf-8")
        )
        observed.extend(manifest["descendant_pids"])
        probe.remove(runtime.pid)
        return _runtime_preflight(tmp_path)

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        runtime_preflight=tracked_preflight,
    )

    result = orchestrator.preflight()

    assert result.doc_types == ["doc_0"]
    assert observed == [
        {
            "pid": 901,
            "process_start_time": 901.5,
            "command_digest": hashlib.sha256(
                b'["copilot-runtime","--stdio"]'
            ).hexdigest(),
            "run_id": orchestrator.run_id,
        }
    ]
    preflight_manifest = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "__preflight__"
            / "run_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert preflight_manifest["status"] == "completed"
    registry = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_process_registry.json"
        ).read_text(encoding="utf-8")
    )
    assert registry["initialized"] is True
    assert registry["run_id"] == orchestrator.run_id
    assert registry["processes"][0]["doc_type"] == "__preflight__"
    assert registry["processes"][0]["status"] == "reaped"


@pytest.mark.asyncio
async def test_default_preflight_start_timeout_registers_spawned_runtime(
    tmp_path: Path,
) -> None:
    registered: list[int] = []

    class HangingStartClient:
        def __init__(self) -> None:
            self._process = SimpleNamespace(pid=903)
            self.stop_calls = 0

        async def start(self) -> None:
            await asyncio.Event().wait()

        async def stop(self) -> None:
            self.stop_calls += 1

    client = HangingStartClient()

    with pytest.raises(AgentTimeoutError, match="start"):
        await asyncio.wait_for(
            _default_runtime_preflight(
                tmp_path,
                "run-preflight-start",
                registered.append,
                client_factory=lambda **_: client,
                startup_timeout_seconds=0.01,
                cleanup_timeout_seconds=0.01,
            ),
            timeout=0.2,
        )

    assert registered == [903]
    assert client.stop_calls == 1


@pytest.mark.asyncio
async def test_default_preflight_stop_is_bounded_after_registered_start(
    tmp_path: Path,
) -> None:
    registered: list[int] = []

    class HangingStopClient:
        def __init__(self) -> None:
            self._process = SimpleNamespace(pid=904)

        async def start(self) -> None:
            return None

        async def ping(self, _: str) -> Any:
            return SimpleNamespace(protocol_version=3)

        async def get_status(self) -> Any:
            return SimpleNamespace(protocol_version=3, version="1.0.8")

        async def get_auth_status(self) -> Any:
            return SimpleNamespace(isAuthenticated=True)

        async def list_models(self) -> list[Any]:
            return [
                SimpleNamespace(id="gemini-3.6-flash"),
                SimpleNamespace(id="claude-opus-4.8"),
            ]

        async def stop(self) -> None:
            await asyncio.Event().wait()

    client = HangingStopClient()

    with pytest.raises(AgentTimeoutError):
        await asyncio.wait_for(
            _default_runtime_preflight(
                tmp_path,
                "run-preflight-stop",
                registered.append,
                client_factory=lambda **_: client,
                startup_timeout_seconds=0.01,
                cleanup_timeout_seconds=0.01,
            ),
            timeout=0.2,
        )

    assert registered == [904]


def test_preflight_cancellation_resistant_start_has_hard_deadline_and_cleanup(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    runtime_pid = 905
    runtime = probe.add(
        pid=runtime_pid,
        command=["copilot-runtime", "--stdio"],
        run_id="run-placeholder",
        start_time=905.5,
    )

    class CancellationResistantStartClient:
        def __init__(self) -> None:
            self._process = SimpleNamespace(pid=runtime_pid)

        async def start(self) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 0.40
                while loop.time() < deadline:
                    try:
                        await asyncio.sleep(deadline - loop.time())
                    except asyncio.CancelledError:
                        continue

        async def stop(self) -> None:
            return None

    client = CancellationResistantStartClient()
    orchestrator: SdkPipelineOrchestrator

    async def bounded_preflight(
        runtime_root: Path,
        run_id: str,
        register_descendant: Any,
    ) -> RuntimePreflight:
        runtime.run_id = run_id
        return await _default_runtime_preflight(
            runtime_root,
            run_id,
            register_descendant,
            client_factory=lambda **_: client,
            startup_timeout_seconds=0.01,
            cleanup_timeout_seconds=0.01,
        )

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        runtime_preflight=bounded_preflight,
        descendant_timeout_seconds=0.01,
        termination_grace_seconds=0.01,
    )

    started = time.perf_counter()
    with pytest.raises(AgentTimeoutError, match="start"):
        orchestrator.preflight()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.25
    assert not probe.is_running(runtime_pid)
    assert not (state_root / "active_lease.json").exists()
    registry = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_process_registry.json"
        ).read_text(encoding="utf-8")
    )
    assert registry["processes"][0]["status"] == "reaped"


def test_unreaped_preflight_runtime_persists_blocker_and_retains_lease(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = StubbornProbe()
    factory = FakeProcessFactory(state_root, probe)

    def leaking_preflight(
        _: Path,
        run_id: str,
        register_descendant: Any,
    ) -> RuntimePreflight:
        runtime = probe.add(
            pid=902,
            command=["copilot-runtime", "--stdio"],
            run_id=run_id,
            start_time=902.5,
        )
        register_descendant(runtime.pid)
        return _runtime_preflight(tmp_path)

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        runtime_preflight=leaking_preflight,
        descendant_timeout_seconds=0.01,
    )

    with pytest.raises(RuntimeError, match="preflight.*runtime"):
        orchestrator.run()

    assert (902, signal.SIGTERM) in probe.signals
    assert (902, signal.SIGKILL) in probe.signals
    assert (state_root / "active_lease.json").is_file()
    durable = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_result.json"
        ).read_text(encoding="utf-8")
    )
    assert durable["stage"] == "preflight"
    assert durable["requires_cleanup"] is True
    assert durable["document_results"]["doc_0"]["status"] == "blocked"
    assert durable["document_results"]["doc_0"]["requires_cleanup"] is True
    assert [item["pid"] for item in durable["process_identities"]] == [902]


def test_unverifiable_bound_manifest_persists_cleanup_requirement(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    orchestrator: SdkPipelineOrchestrator

    def corrupt_bound_manifest(
        _: dict[str, SupervisorDocumentResult],
    ) -> dict[str, Any]:
        corrupt = (
            state_root
            / "runs"
            / f"{orchestrator.run_id}-corrupt"
            / "doc_0"
            / "run_manifest.json"
        )
        atomic_write_json(corrupt, {"invalid": True})
        return {
            "status": "rejected",
            "evaluated_doc_types": ["doc_0"],
            "reason": "injected non-live test decision",
        }

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        shared_optimizer=corrupt_bound_manifest,
    )

    with pytest.raises(RuntimeError, match="lease reconciliation"):
        orchestrator.run()

    durable = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_result.json"
        ).read_text(encoding="utf-8")
    )
    assert durable["stage"] == "lease_reconciliation"
    assert durable["requires_cleanup"] is True
    assert durable["document_results"]["doc_0"]["requires_cleanup"] is True
    assert durable["lease_status"] == "retained"


@pytest.mark.asyncio
async def test_supervisor_cancellation_reconciles_every_launched_document(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0", "doc_1"],
        factory,
        probe,
    )
    orchestrator._lease = PipelineRunLease.acquire(
        state_root,
        run_id=orchestrator.run_id,
        process_probe=probe,
    )
    orchestrator._initialize_process_registry()
    task = asyncio.create_task(orchestrator._run_children())
    while len(factory.starts) < 2:
        await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    for doc_type in ("doc_0", "doc_1"):
        run_dir = state_root / "runs" / orchestrator.run_id / doc_type
        assert json.loads(
            (run_dir / "pipeline_result.json").read_text(encoding="utf-8")
        )["status"] == "cancelled"
        assert json.loads(
            (run_dir / "run_manifest.json").read_text(encoding="utf-8")
        )["status"] == "cancelled"
    assert not probe._mock_processes
    durable = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_result.json"
        ).read_text(encoding="utf-8")
    )
    assert durable["status"] == "cancelled"
    assert durable["stage"] == "children"
    assert set(durable["document_results"]) == {"doc_0", "doc_1"}
    assert orchestrator.release_retained_lease().released


def test_watchdog_stage_deadlines_cover_long_model_timeouts(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        heartbeat_timeout_seconds=300,
        stage_timeout_seconds=300,
        descendant_timeout_seconds=30,
        termination_grace_seconds=5,
    )

    assert orchestrator._stage_watchdog_timeout("baseline_workers") >= 635
    assert orchestrator._stage_watchdog_timeout("baseline_judge") >= 935
    assert orchestrator._stage_watchdog_timeout("optimizer") >= 635


def test_spawn_failure_preserves_blocker_and_continues_other_documents(
    tmp_path: Path,
) -> None:
    doc_types = [f"doc_{index}" for index in range(6)]
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    orchestrator = _orchestrator(
        tmp_path,
        doc_types,
        factory,
        probe,
    )
    real_factory = orchestrator.subprocess_factory

    async def fail_one(*command: str, **kwargs: Any) -> FakeProcess:
        doc_type = command[command.index("--doc-type") + 1]
        if doc_type == "doc_0":
            raise OSError("simulated spawn failure")
        return await real_factory(*command, **kwargs)

    orchestrator.subprocess_factory = fail_one

    result = orchestrator.run()

    assert set(result.document_results) == set(doc_types)
    assert result.document_results["doc_0"].status == "blocked"
    assert "spawn failure" in (
        result.document_results["doc_0"].blocker or ""
    )
    assert all(
        result.document_results[doc_type].status == "completed"
        for doc_type in doc_types[1:]
    )


def test_spawn_identity_probe_waits_for_delayed_proc_visibility(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = DelayedVisibilityProbe(misses=2)
    factory = FakeProcessFactory(state_root, probe)
    factory.start_gate.set()
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        spawn_identity_timeout_seconds=0.05,
        spawn_identity_poll_seconds=0.001,
    )

    result = orchestrator.run()

    assert result.document_results["doc_0"].status == "completed"
    assert probe.lookups[factory.pids["doc_0"]] >= 3
    registry = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_process_registry.json"
        ).read_text()
    )
    assert registry["processes"][0]["identity_verified"] is True
    assert registry["processes"][0]["status"] == "reaped"


def test_spawn_identity_probe_waits_for_child_exec_command(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    probe = ExecTransitionProbe()
    factory = FakeProcessFactory(state_root, probe)
    factory.start_gate.set()
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        spawn_identity_timeout_seconds=0.05,
        spawn_identity_poll_seconds=0.001,
    )

    result = orchestrator.run()

    assert result.document_results["doc_0"].status == "completed"
    assert probe.lookups[factory.pids["doc_0"]] >= 2
    registry = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_process_registry.json"
        ).read_text()
    )
    assert registry["processes"][0]["identity_verified"] is True
    assert registry["processes"][0]["status"] == "reaped"


def test_fast_exit_before_identity_reconciles_terminal_result(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    spawned: list[FastExitBeforeIdentityProcess] = []

    async def factory(*command: str, **_: Any) -> FastExitBeforeIdentityProcess:
        process = FastExitBeforeIdentityProcess(
            command=list(command),
            state_root=state_root,
        )
        spawned.append(process)
        return process

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        FakeProcessFactory(state_root, probe),
        probe,
        subprocess_factory=factory,
        spawn_identity_timeout_seconds=0.05,
        spawn_identity_poll_seconds=0.001,
    )

    result = orchestrator.run()

    assert result.document_results["doc_0"].status == "completed"
    assert spawned[0].terminate_calls == 0
    assert spawned[0].kill_calls == 0
    registry = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_process_registry.json"
        ).read_text()
    )
    assert registry["processes"][0]["identity_verified"] is False
    assert registry["processes"][0]["status"] == "reaped"


def test_unverified_just_spawned_child_is_reaped_only_through_owned_handle(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    spawned: list[UnverifiedSpawnProcess] = []

    async def factory(*_: str, **__: Any) -> UnverifiedSpawnProcess:
        process = UnverifiedSpawnProcess(pid=8_099)
        spawned.append(process)
        return process

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        FakeProcessFactory(state_root, probe),
        probe,
        subprocess_factory=factory,
        spawn_identity_timeout_seconds=0.01,
        spawn_identity_poll_seconds=0.001,
        termination_grace_seconds=0.01,
        descendant_timeout_seconds=0.01,
    )

    result = orchestrator.run()

    assert result.status == "blocked"
    assert result.document_results["doc_0"].status == "blocked"
    assert "unverified_spawn" in (
        result.document_results["doc_0"].blocker or ""
    )
    assert spawned[0].terminate_calls == 1
    assert spawned[0].kill_calls == 0
    assert probe.signals == []
    assert not (state_root / "active_lease.json").exists()
    registry = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_process_registry.json"
        ).read_text(encoding="utf-8")
    )
    assert registry["processes"][0]["identity_verified"] is False
    assert registry["processes"][0]["status"] == "reaped"


def test_unreaped_unverified_spawn_retains_lease_and_cleanup_record(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    spawned: list[UnreapableSpawnProcess] = []

    async def factory(*_: str, **__: Any) -> UnreapableSpawnProcess:
        process = UnreapableSpawnProcess(pid=8_098)
        spawned.append(process)
        return process

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        FakeProcessFactory(state_root, probe),
        probe,
        subprocess_factory=factory,
        spawn_identity_timeout_seconds=0.01,
        spawn_identity_poll_seconds=0.001,
        termination_grace_seconds=0.01,
        descendant_timeout_seconds=0.01,
    )

    started = time.perf_counter()
    with pytest.raises(RuntimeError, match="identity is unavailable"):
        orchestrator.run()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.20
    assert spawned[0].terminate_calls == 1
    assert spawned[0].kill_calls == 1
    assert probe.signals == []
    assert (state_root / "active_lease.json").is_file()
    registry = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_process_registry.json"
        ).read_text(encoding="utf-8")
    )
    assert registry["processes"][0]["identity_verified"] is False
    assert registry["processes"][0]["status"] == "requires_cleanup"
    durable = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_result.json"
        ).read_text(encoding="utf-8")
    )
    assert durable["requires_cleanup"] is True
    assert durable["document_results"]["doc_0"]["requires_cleanup"] is True


@pytest.mark.parametrize("exit_immediately", [False, True])
def test_parent_registry_reaps_child_without_manifest(
    tmp_path: Path,
    exit_immediately: bool,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()

    async def factory(*command: str, **_: Any) -> ManifestlessProcess:
        return ManifestlessProcess(
            pid=8_100,
            command=list(command),
            probe=probe,
            exit_immediately=exit_immediately,
        )

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        FakeProcessFactory(state_root, probe),
        probe,
        subprocess_factory=factory,
        heartbeat_timeout_seconds=0.01,
        stage_timeout_seconds=0.01,
    )

    result = orchestrator.run()

    assert result.document_results["doc_0"].status == "blocked"
    assert not probe.is_running(8_100)
    assert not (state_root / "active_lease.json").exists()
    registry = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_process_registry.json"
        ).read_text(encoding="utf-8")
    )
    assert registry["processes"][0]["status"] == "reaped"
    assert registry["processes"][0]["doc_type"] == "doc_0"


def test_generic_monitor_exception_reaps_live_child_before_releasing_slot(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()

    async def factory(*command: str, **_: Any) -> ManifestlessProcess:
        return ManifestlessProcess(
            pid=8_101,
            command=list(command),
            probe=probe,
        )

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        FakeProcessFactory(state_root, probe),
        probe,
        subprocess_factory=factory,
    )

    def broken_monitor_input(*_: Any, **__: Any) -> None:
        raise ValueError("simulated manifest parse failure")

    orchestrator._load_heartbeat = broken_monitor_input  # type: ignore[method-assign]

    result = orchestrator.run()

    document = result.document_results["doc_0"]
    assert document.status == "blocked"
    assert "manifest parse failure" in (document.blocker or "")
    assert any(pid == 8_101 for pid, _ in probe.signals)
    assert not probe.is_running(8_101)
    assert not (state_root / "active_lease.json").exists()
    blocked = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "doc_0"
            / "pipeline_result.json"
        ).read_text(encoding="utf-8")
    )
    assert blocked["status"] == "blocked"


def test_lease_release_safe_flag_retains_lease_even_after_empty_scan(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)
    orchestrator: SdkPipelineOrchestrator

    def mark_unsafe(
        _: dict[str, SupervisorDocumentResult],
    ) -> dict[str, Any]:
        orchestrator._lease_release_safe = False
        return {
            "status": "rejected",
            "evaluated_doc_types": ["doc_0"],
            "reason": "injected unsafe cleanup state",
        }

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        shared_optimizer=mark_unsafe,
    )

    with pytest.raises(RuntimeError, match="lease.*unsafe|unsafe.*lease"):
        orchestrator.run()

    assert (state_root / "active_lease.json").is_file()
    durable = json.loads(
        (
            state_root
            / "runs"
            / orchestrator.run_id
            / "supervisor_result.json"
        ).read_text(encoding="utf-8")
    )
    assert durable["requires_cleanup"] is True
    assert durable["lease_status"] == "retained"


def test_preflight_rejects_missing_exact_model_before_spawn(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    factory = FakeProcessFactory(state_root, probe)

    def missing_model(
        _: Path,
        _run_id: str,
        _register_descendant: Any,
    ) -> RuntimePreflight:
        status = asdict(_runtime_preflight(tmp_path))
        status["models"] = ["gemini-3.6-flash"]
        return RuntimePreflight(**status)

    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        factory,
        probe,
        runtime_preflight=missing_model,
    )

    with pytest.raises(RuntimeError, match="claude-opus-4.8"):
        orchestrator.run()

    assert factory.starts == []


def test_document_pipeline_cli_binds_run_identity_and_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: list[document_pipeline.DocumentPipelineConfig] = []

    def fake_run(
        config: document_pipeline.DocumentPipelineConfig,
    ) -> document_pipeline.DocumentPipelineResult:
        captured.append(config)
        return document_pipeline.DocumentPipelineResult(
            run_id=config.run_id,
            doc_type=config.doc_type,
            status="blocked",
            stages=[],
            max_live_sessions=0,
            patch=document_pipeline.PatchDecision(
                status="blocked",
                target_file=None,
                candidate_id=None,
                candidate_path=None,
                candidate_content="",
                candidate_content_hash=None,
                source_hash=None,
                evidence=[],
            ),
            error="fake",
        )

    monkeypatch.setattr(document_pipeline, "run_document_pipeline", fake_run)
    monkeypatch.setenv("PHASE74_PIPELINE_PHASE", "optimization")

    exit_code = document_pipeline.main(
        [
            "--run-id",
            "run-1",
            "--doc-type",
            "passport",
            "--run-root",
            str(tmp_path),
            "--source-revision",
            "a" * 40,
        ]
    )

    assert exit_code == 1
    assert captured == [
        document_pipeline.DocumentPipelineConfig(
            run_id="run-1",
            doc_type="passport",
            state_root=tmp_path,
            execution_phase="optimization",
            source_revision="a" * 40,
        )
    ]
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def test_document_pipeline_child_has_no_git_subprocess_dependency() -> None:
    assert not hasattr(document_pipeline, "subprocess")


def _score(value: float) -> dict[str, float]:
    return {
        "grounding_accuracy": 1.0,
        "citation_exactness": 1.0,
        "defect_recall": value,
        "pii_containment": 1.0,
        "blind_input_compliance": 1.0,
        "overall_score": (4.0 + value) / 5.0,
    }


def test_parent_rejects_accepted_patch_without_optimizer_provenance(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    target = source_root / "skills" / "document-agents" / "passport.md"
    target.parent.mkdir(parents=True)
    original = "\n".join(f"- Existing rule {index}" for index in range(10)) + "\n"
    candidate = original + "- Added verification rule\n"
    target.write_text(original, encoding="utf-8")
    candidate_id = "candidate_" + "a" * 12
    proposal_root = tmp_path / "proposals"
    candidate_path = (
        proposal_root
        / candidate_id
        / "skills"
        / "document-agents"
        / "passport.md"
    )
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(candidate, encoding="utf-8")
    patch = {
        "status": "accepted",
        "target_file": "skills/document-agents/passport.md",
        "candidate_id": candidate_id,
        "candidate_path": str(candidate_path),
        "candidate_content": candidate,
        "candidate_content_hash": hashlib.sha256(candidate.encode()).hexdigest(),
        "source_hash": hashlib.sha256(original.encode()).hexdigest(),
        "metrics": {
            "baseline_train": _score(0.4),
            "baseline_holdout": _score(0.5),
            "candidate_train": _score(0.8),
            "candidate_holdout": _score(0.5),
        },
        "evidence": [
            {"kind": "candidate_validation", "passed": True},
            {"kind": "metric_gate", "passed": True},
        ],
    }
    result = SupervisorDocumentResult(
        doc_type="passport",
        status="completed",
        exit_code=0,
        child_result={
            **_result("run-1", "passport"),
            "patch": patch,
        },
    )
    orchestrator = SdkPipelineOrchestrator(
        source_root=source_root,
        pipeline_root=tmp_path / "pipelines",
        state_root=tmp_path / "state",
        corpus_db_path=tmp_path / "corpus.db",
        proposal_root=proposal_root,
        runtime_root=tmp_path / "runtime",
        doc_types=["passport"],
        require_complete_dataset=False,
    )

    applied = orchestrator._apply_document_patches({"passport": result})

    assert applied == []
    assert result.parent_patch_status == "blocked"
    assert "optimizer provenance" in (result.blocker or "")
    assert target.read_text(encoding="utf-8") == original


def test_parent_revalidates_and_commits_accepted_document_patch(
    tmp_path: Path,
) -> None:
    from crawler.tests.test_phase74_document_pipeline import (
        PipelineRuntime,
        _write_fixture,
    )

    fixture_root = tmp_path / "fixture"
    pipeline_root, source_root, source_path, cases = _write_fixture(
        fixture_root
    )
    _, holdout = document_pipeline.split_doc_type_cases(
        cases,
        doc_type="passport",
    )
    original = source_path.read_text(encoding="utf-8")
    runtime = PipelineRuntime(
        source_content=original,
        holdout_ids={str(case["opaque_case_id"]) for case in holdout},
    )
    pipeline_result = document_pipeline.run_document_pipeline(
        document_pipeline.DocumentPipelineConfig(
            run_id="run-parent-apply",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=Path(__file__).resolve().parents[2]
            / "corpus"
            / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=runtime,
            execution_phase="optimization",
        )
    )
    subprocess.run(["git", "init", "-q"], cwd=source_root, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Task 5 Test"],
        cwd=source_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "task5@example.invalid"],
        cwd=source_root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=source_root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"],
        cwd=source_root,
        check=True,
    )
    parent_result = SupervisorDocumentResult(
        doc_type="passport",
        status="completed",
        exit_code=0,
        child_result=asdict(pipeline_result),
    )
    orchestrator = SdkPipelineOrchestrator(
        source_root=source_root,
        pipeline_root=pipeline_root,
        state_root=tmp_path / "state",
        corpus_db_path=Path(__file__).resolve().parents[2]
        / "corpus"
        / "index.db",
        proposal_root=tmp_path / "proposals",
        runtime_root=tmp_path / "runtime",
        doc_types=["passport"],
        require_complete_dataset=False,
    )

    applied = orchestrator._apply_document_patches(
        {"passport": parent_result}
    )

    assert parent_result.parent_patch_status == "applied"
    assert source_path.read_text(encoding="utf-8") == (
        pipeline_result.patch.candidate_content
    )
    assert applied[0]["doc_type"] == "passport"
    log = subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        cwd=source_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "passport SDK patch" in log
    assert (
        "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
        in log
    )


def test_parent_refuses_to_absorb_unrelated_staged_file(tmp_path: Path) -> None:
    from crawler.tests.test_phase74_document_pipeline import (
        PipelineRuntime,
        _write_fixture,
    )

    fixture_root = tmp_path / "fixture"
    pipeline_root, source_root, source_path, cases = _write_fixture(fixture_root)
    _, holdout = document_pipeline.split_doc_type_cases(
        cases,
        doc_type="passport",
    )
    original = source_path.read_text(encoding="utf-8")
    pipeline_result = document_pipeline.run_document_pipeline(
        document_pipeline.DocumentPipelineConfig(
            run_id="run-parent-staged",
            doc_type="passport",
            pipeline_root=pipeline_root,
            state_root=tmp_path / "state",
            corpus_db_path=Path(__file__).resolve().parents[2]
            / "corpus"
            / "index.db",
            proposal_sandbox_root=tmp_path / "proposals",
            source_root=source_root,
            runtime=PipelineRuntime(
                source_content=original,
                holdout_ids={
                    str(case["opaque_case_id"]) for case in holdout
                },
            ),
            execution_phase="optimization",
        )
    )
    unrelated = source_root / "unrelated.txt"
    unrelated.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=source_root, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Task 5 Test"],
        cwd=source_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "task5@example.invalid"],
        cwd=source_root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=source_root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"],
        cwd=source_root,
        check=True,
    )
    unrelated.write_text("staged unrelated change\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], cwd=source_root, check=True)
    parent_result = SupervisorDocumentResult(
        doc_type="passport",
        status="completed",
        exit_code=0,
        child_result=asdict(pipeline_result),
    )
    orchestrator = SdkPipelineOrchestrator(
        source_root=source_root,
        pipeline_root=pipeline_root,
        state_root=tmp_path / "state",
        corpus_db_path=Path(__file__).resolve().parents[2]
        / "corpus"
        / "index.db",
        proposal_root=tmp_path / "proposals",
        runtime_root=tmp_path / "runtime",
        doc_types=["passport"],
        require_complete_dataset=False,
    )

    applied = orchestrator._apply_document_patches(
        {"passport": parent_result}
    )

    assert applied == []
    assert parent_result.parent_patch_status == "blocked"
    assert "staged" in (parent_result.blocker or "")
    assert source_path.read_text(encoding="utf-8") == original
    assert subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=source_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines() == ["unrelated.txt"]
    assert subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=source_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "1"


class ImmediateProcess:
    def __init__(
        self,
        *,
        command: list[str],
        state_root: Path,
        probe: RecordingProbe,
        succeeded: bool,
    ) -> None:
        self.command = command
        self.probe = probe
        self.run_id = command[command.index("--run-id") + 1]
        self.doc_type = command[command.index("--doc-type") + 1]
        self.pid = 9_000 if succeeded else 9_001
        self.returncode = 0 if succeeded else 1
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        child = probe.add(
            pid=self.pid,
            command=command,
            run_id=self.run_id,
            start_time=float(self.pid),
        )
        run_dir = state_root / "runs" / self.run_id / self.doc_type
        manifest = RunManifest(
            run_id=self.run_id,
            doc_type=self.doc_type,
            pid=self.pid,
            process_start_time=child.start_time,
            command_digest=child.command_digest,
            status="completed" if succeeded else "failed",
        )
        atomic_write_json(run_dir / "run_manifest.json", manifest)
        result = _result(self.run_id, self.doc_type)
        if not succeeded:
            result["status"] = "blocked"
            result["patch"]["status"] = "blocked"
            result["error"] = "fast failure"
        atomic_write_json(run_dir / "pipeline_result.json", result)
        self.stdout.feed_eof()
        self.stderr.feed_eof()

    async def wait(self) -> int:
        self.probe.remove(self.pid)
        return self.returncode


@pytest.mark.parametrize(
    ("succeeded", "expected_status"),
    [(True, "completed"), (False, "blocked")],
)
def test_fast_exit_validates_terminal_manifest_before_ownership_blocker(
    tmp_path: Path,
    succeeded: bool,
    expected_status: str,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()

    async def factory(*command: str, **_: Any) -> ImmediateProcess:
        return ImmediateProcess(
            command=list(command),
            state_root=state_root,
            probe=probe,
            succeeded=succeeded,
        )

    placeholder = FakeProcessFactory(state_root, probe)
    orchestrator = _orchestrator(
        tmp_path,
        ["doc_0"],
        placeholder,
        probe,
        subprocess_factory=factory,
    )

    result = orchestrator.run()

    document = result.document_results["doc_0"]
    assert document.status == expected_status
    assert "ownership was never verified" not in (document.blocker or "")


def test_cleanup_dry_run_and_apply_only_manifest_owned_processes(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    probe = RecordingProbe()
    interactive = probe.add(
        pid=700,
        command=["copilot", "--resume=session"],
        start_time=700.0,
    )
    unowned = probe.add(
        pid=701,
        command=["copilot-runtime"],
        start_time=701.0,
    )
    command = [
        sys.executable,
        "-m",
        "crawler.eval.document_pipeline",
        "--run-id",
        "stalled-run",
        "--doc-type",
        "passport",
        "--run-root",
        str(state_root),
    ]
    owned = probe.add(
        pid=702,
        command=command,
        run_id="stalled-run",
        start_time=702.0,
    )
    manifest = RunManifest(
        run_id="stalled-run",
        doc_type="passport",
        pid=owned.pid,
        process_start_time=owned.start_time,
        command_digest=owned.command_digest,
        heartbeat_at="2000-01-01T00:00:00+00:00",
        status="in_progress",
    )
    manifest_path = (
        state_root
        / "runs"
        / "stalled-run"
        / "passport"
        / "run_manifest.json"
    )
    atomic_write_json(manifest_path, manifest)
    completed_process = probe.add(
        pid=703,
        command=[
            sys.executable,
            "--run-id",
            "completed-run",
        ],
        run_id="completed-run",
        start_time=703.0,
    )
    completed_manifest = RunManifest(
        run_id="completed-run",
        doc_type="passport",
        pid=completed_process.pid,
        process_start_time=completed_process.start_time,
        command_digest=completed_process.command_digest,
        heartbeat_at="2000-01-01T00:00:00+00:00",
        status="completed",
    )
    completed_manifest_path = (
        state_root
        / "runs"
        / "completed-run"
        / "passport"
        / "run_manifest.json"
    )
    atomic_write_json(completed_manifest_path, completed_manifest)
    probe.remove(completed_process.pid)

    dry_run = cleanup(
        state_root,
        apply=False,
        stale_threshold_seconds=1,
        process_probe=probe,
        grace_period_seconds=0,
    )

    assert dry_run.terminated_pids == []
    assert dry_run.stale_manifests == [str(manifest_path)]
    assert probe.get_process_info(owned.pid) is not None

    applied = cleanup(
        state_root,
        apply=True,
        stale_threshold_seconds=1,
        process_probe=probe,
        grace_period_seconds=0,
    )

    assert applied.terminated_pids == [owned.pid]
    assert not manifest_path.exists()
    assert str(completed_manifest_path) not in applied.stale_manifests
    assert (
        json.loads(completed_manifest_path.read_text())["status"]
        == "completed"
    )
    assert probe.get_process_info(interactive.pid) is not None
    assert probe.get_process_info(unowned.pid) is not None
    audits = list(state_root.glob("*/cleanup_audit.json"))
    assert len(audits) == 2
    assert {json.loads(path.read_text())["mode"] for path in audits} == {
        "dry-run",
        "apply",
    }
    assert len(applied.quarantined_paths) == 1
    apply_audit = next(
        path
        for path in audits
        if json.loads(path.read_text())["mode"] == "apply"
    )
    apply_payload = json.loads(apply_audit.read_text())
    assert apply_payload["quarantined"][0]["reason"] == "reconciled_manifest_run"
    assert len(
        list(state_root.glob("*/quarantine/runs/stalled-run/passport"))
    ) == 1


def test_cleanup_explicit_target_root_quarantines_only_owned_legacy_partials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_root = tmp_path / "checkout"
    (target_root / ".git").mkdir(parents=True)
    (target_root / "crawler" / "eval").mkdir(parents=True)
    reports = target_root / "reports"
    worker = reports / "worker_staging" / "tmpworker"
    judge = reports / "judge_staging" / "tmpjudge"
    worker.mkdir(parents=True)
    judge.mkdir(parents=True)
    (worker / f"{'a' * 32}.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    (judge / f"{'b' * 32}.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

    iterations = reports / "phase74_iterations"
    partial_final = iterations / "iter_final"
    partial_final.mkdir(parents=True)
    partial_candidate = (
        iterations / "iter_1" / "proposals" / "candidate_aaaaaaaaaaaa"
    )
    partial_candidate.mkdir(parents=True)
    retained_candidate = (
        iterations / "iter_1" / "proposals" / "candidate_bbbbbbbbbbbb"
    )
    retained_candidate.mkdir(parents=True)
    (retained_candidate / "candidate.md").write_text(
        "historical evidence",
        encoding="utf-8",
    )
    checkpoints = iterations / "iter_1" / "checkpoints"
    checkpoints.mkdir(parents=True)
    (checkpoints / "checkpoint.json").write_text("{}", encoding="utf-8")

    old_timestamp = time.time() - 600
    for path in (
        worker / f"{'a' * 32}.pdf",
        judge / f"{'b' * 32}.pdf",
        worker,
        judge,
        partial_final,
        partial_candidate,
    ):
        os.utime(path, (old_timestamp, old_timestamp))

    monkeypatch.setattr(
        sdk_pipeline_orchestrator,
        "_path_owner_pids",
        lambda _path: [],
    )
    monkeypatch.setattr(
        sdk_pipeline_orchestrator,
        "_interactive_copilot_pids",
        lambda: [4242],
    )

    dry_run = cleanup(
        target_root=target_root,
        apply=False,
        stale_threshold_seconds=10,
    )

    assert worker.is_dir()
    assert judge.is_dir()
    assert partial_final.is_dir()
    assert partial_candidate.is_dir()
    assert dry_run.retained_processes == [4242]
    assert {
        "reports/worker_staging/tmpworker",
        "reports/judge_staging/tmpjudge",
        "reports/phase74_iterations/iter_final",
        (
            "reports/phase74_iterations/iter_1/proposals/"
            "candidate_aaaaaaaaaaaa"
        ),
    }.issubset(set(dry_run.quarantined_paths))
    dry_audit = target_root / str(dry_run.audit_path)
    dry_payload = json.loads(dry_audit.read_text(encoding="utf-8"))
    assert dry_payload["mode"] == "dry-run"
    assert dry_payload["removed"] == []
    assert len(dry_payload["quarantined"]) == 4

    applied = cleanup(
        target_root=target_root,
        apply=True,
        stale_threshold_seconds=10,
    )

    assert not worker.exists()
    assert not judge.exists()
    assert not partial_final.exists()
    assert not partial_candidate.exists()
    assert retained_candidate.is_dir()
    assert checkpoints.is_dir()
    apply_audit = target_root / str(applied.audit_path)
    apply_payload = json.loads(apply_audit.read_text(encoding="utf-8"))
    destinations = {
        target_root / action["destination"]
        for action in apply_payload["quarantined"]
    }
    assert len(destinations) == 4
    assert all(destination.exists() for destination in destinations)
    assert apply_payload["removed"] == []


def test_cleanup_target_root_rejects_non_checkout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must name a project checkout"):
        cleanup(target_root=tmp_path, apply=False)
