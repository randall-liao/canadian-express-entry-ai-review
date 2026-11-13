import json
import multiprocessing
import signal
import shutil

import pytest

from crawler.eval.pipeline_state import (
    ActiveRunError,
    DescendantOwnershipError,
    DescendantExitTimeoutError,
    PipelineRunLease,
    PipelineStateStore,
    SupervisorProcessRegistry,
    ProcessProbe,
    RunManifest,
    atomic_write_json,
    cleanup_stalled_runs,
)


def _race_acquire(root_dir, run_id, start, release, results):
    start.wait()
    try:
        lease = PipelineRunLease.acquire(root_dir, run_id=run_id)
    except ActiveRunError:
        results.put(("rejected", run_id))
        return

    results.put(("acquired", run_id))
    release.wait(timeout=5)
    lease.release()


class RecordingProbe(ProcessProbe):
    def __init__(self, *, exit_on_sigterm=True):
        super().__init__()
        self.exit_on_sigterm = exit_on_sigterm
        self.signals = []

    def terminate_process(self, pid, sig=signal.SIGTERM):
        self.signals.append((pid, sig))
        if sig == signal.SIGKILL or self.exit_on_sigterm:
            self.remove(pid)
        return True


@pytest.fixture
def process_probe():
    return ProcessProbe()


def test_completed_stage_reuse_requires_exact_manifest_hash(tmp_path):
    store = PipelineStateStore(tmp_path, run_id="run-1", doc_type="passport")
    store.complete_stage("worker:a", input_hash="a" * 64, output_hash="b" * 64)
    assert store.can_reuse("worker:a", input_hash="a" * 64)
    assert not store.can_reuse("worker:a", input_hash="c" * 64)


def test_heartbeat_is_atomic_and_monotonic(tmp_path):
    store = PipelineStateStore(tmp_path, run_id="run-1", doc_type="passport")
    store.heartbeat(stage="worker", item="opaque", completed=1, expected=10)
    heartbeat = json.loads(store.heartbeat_path.read_text())
    assert heartbeat["sequence"] == 1
    assert not list(store.heartbeat_path.parent.glob(".tmp-*"))


def test_cleanup_never_targets_unowned_interactive_process(tmp_path, process_probe):
    process_probe.add(pid=100, command=["copilot", "--resume=session"], run_id=None)
    result = cleanup_stalled_runs(tmp_path, process_probe=process_probe)
    assert result.terminated_pids == []


def test_live_run_lease_rejects_overlapping_supervisor(tmp_path, process_probe):
    first = PipelineRunLease.acquire(tmp_path, run_id="run-1", process_probe=process_probe)
    with pytest.raises(ActiveRunError):
        PipelineRunLease.acquire(tmp_path, run_id="run-2", process_probe=process_probe)
    first.release()


def test_lease_acquisition_atomically_initializes_bound_process_registry(
    tmp_path,
    process_probe,
):
    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-initialized",
        process_probe=process_probe,
    )

    registry_path = (
        tmp_path
        / "runs"
        / "run-initialized"
        / "supervisor_process_registry.json"
    )
    assert json.loads(registry_path.read_text(encoding="utf-8")) == {
        "schema_version": "phase74-supervisor-process-registry-v1",
        "run_id": "run-initialized",
        "initialized": True,
        "processes": [],
    }
    assert lease.release()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "corrupt",
        "wrong-run",
        "uninitialized",
        "missing-initialized",
        "missing-schema",
    ],
)
def test_invalid_bound_registry_blocks_owner_release_and_stale_reclaim(
    tmp_path,
    process_probe,
    mutation,
):
    owner = process_probe.add(
        pid=205,
        command=["python", "--run-id", "run-bound"],
        run_id="run-bound",
        start_time=900.0,
    )
    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-bound",
        pid=owner.pid,
        process_probe=process_probe,
    )
    registry_path = (
        tmp_path
        / "runs"
        / "run-bound"
        / "supervisor_process_registry.json"
    )
    if mutation == "missing":
        registry_path.unlink()
    elif mutation == "corrupt":
        registry_path.write_text("{", encoding="utf-8")
    else:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        if mutation == "wrong-run":
            payload["run_id"] = "run-other"
        elif mutation == "uninitialized":
            payload["initialized"] = False
        elif mutation == "missing-initialized":
            del payload["initialized"]
        else:
            del payload["schema_version"]
        registry_path.write_text(json.dumps(payload), encoding="utf-8")

    release = lease.release_after_reconciliation()
    assert not release.released
    assert any("registry" in error.lower() for error in release.errors)

    process_probe.remove(owner.pid)
    with pytest.raises(ActiveRunError, match="orphaned-run cleanup"):
        PipelineRunLease.acquire(
            tmp_path,
            run_id="run-new",
            process_probe=process_probe,
        )
    assert (tmp_path / "active_lease.json").is_file()


def test_stale_run_lease_can_be_reclaimed(tmp_path, process_probe):
    process_probe.add(pid=200, command=["python", "-m", "crawler.eval.document_pipeline", "--run-id", "run-1"], run_id="run-1")
    first = PipelineRunLease.acquire(tmp_path, run_id="run-1", pid=200, process_probe=process_probe)

    # Mark process as terminated / gone in process probe
    process_probe.remove(200)

    # Second lease acquire should reclaim the stale lease
    second = PipelineRunLease.acquire(tmp_path, run_id="run-2", process_probe=process_probe)
    assert second.run_id == "run-2"
    second.release()


def test_dead_lease_owner_with_live_bound_descendant_requires_orphan_cleanup(
    tmp_path,
    process_probe,
):
    owner = process_probe.add(
        pid=200,
        command=["python", "--run-id", "run-old"],
        run_id="run-old",
        start_time=1000.0,
    )
    PipelineRunLease.acquire(
        tmp_path,
        run_id="run-old",
        pid=owner.pid,
        process_probe=process_probe,
    )
    descendant = process_probe.add(
        pid=201,
        command=["copilot-runtime", "--run-id", "run-old-optimization"],
        run_id="run-old-optimization",
        start_time=1001.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-old-optimization",
        doc_type="passport",
        process_probe=process_probe,
    )
    store.add_descendant_pid(descendant.pid)
    process_probe.remove(owner.pid)

    with pytest.raises(ActiveRunError, match="orphaned-run cleanup"):
        PipelineRunLease.acquire(
            tmp_path,
            run_id="run-new",
            process_probe=process_probe,
        )

    assert json.loads((tmp_path / "active_lease.json").read_text())["run_id"] == (
        "run-old"
    )


def test_dead_lease_owner_reclaims_after_bound_descendants_are_gone(
    tmp_path,
    process_probe,
):
    owner = process_probe.add(
        pid=200,
        command=["python", "--run-id", "run-old"],
        run_id="run-old",
        start_time=1000.0,
    )
    PipelineRunLease.acquire(
        tmp_path,
        run_id="run-old",
        pid=owner.pid,
        process_probe=process_probe,
    )
    descendant = process_probe.add(
        pid=201,
        command=["copilot-runtime", "--run-id", "run-old-final"],
        run_id="run-old-final",
        start_time=1001.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-old-final",
        doc_type="passport",
        process_probe=process_probe,
    )
    store.add_descendant_pid(descendant.pid)
    process_probe.remove(owner.pid)
    process_probe.remove(descendant.pid)

    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-new",
        process_probe=process_probe,
    )

    assert lease.run_id == "run-new"
    assert lease.release()


def test_dead_lease_owner_cannot_reclaim_unscannable_bound_run_root(
    tmp_path,
    process_probe,
):
    owner = process_probe.add(
        pid=200,
        command=["python", "--run-id", "run-old"],
        run_id="run-old",
        start_time=1000.0,
    )
    PipelineRunLease.acquire(
        tmp_path,
        run_id="run-old",
        pid=owner.pid,
        process_probe=process_probe,
    )
    external_root = tmp_path / "external-run-root"
    external_root.mkdir()
    runs_root = tmp_path / "runs"
    runs_root.mkdir(exist_ok=True)
    shutil.rmtree(runs_root / "run-old")
    (runs_root / "run-old").symlink_to(external_root, target_is_directory=True)
    process_probe.remove(owner.pid)

    with pytest.raises(ActiveRunError, match="orphaned-run cleanup"):
        PipelineRunLease.acquire(
            tmp_path,
            run_id="run-new",
            process_probe=process_probe,
        )


def test_owner_release_requires_post_cleanup_bound_descendant_scan(
    tmp_path,
    process_probe,
):
    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-owner",
        process_probe=process_probe,
    )
    descendant = process_probe.add(
        pid=201,
        command=["copilot-runtime", "--run-id", "run-owner"],
        run_id="run-owner",
        start_time=1001.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-owner",
        doc_type="passport",
        process_probe=process_probe,
    )
    store.add_descendant_pid(descendant.pid)

    retained = lease.release_after_reconciliation()

    assert not retained.released
    assert retained.remaining_pids == [descendant.pid]
    assert lease.lease_path.is_file()

    process_probe.remove(descendant.pid)
    released = lease.release_after_reconciliation()
    assert released.released
    assert released.remaining_pids == []
    assert not lease.lease_path.exists()


def test_parent_registry_keeps_lease_for_child_without_manifest(
    tmp_path,
    process_probe,
):
    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-owner",
        process_probe=process_probe,
    )
    child = process_probe.add(
        pid=211,
        command=[
            "python",
            "-m",
            "crawler.eval.document_pipeline",
            "--run-id",
            "run-owner-optimization",
            "--doc-type",
            "passport",
        ],
        run_id="run-owner-optimization",
        start_time=1002.0,
    )
    registry = SupervisorProcessRegistry(
        tmp_path,
        parent_run_id="run-owner",
        process_probe=process_probe,
    )

    identity = registry.register_spawn(
        child.pid,
        run_id="run-owner-optimization",
        doc_type="passport",
    )

    retained = lease.release_after_reconciliation()
    assert not retained.released
    assert retained.remaining_pids == [child.pid]
    payload = json.loads(registry.path.read_text())
    record = payload["processes"][0]
    assert {
        key: record[key]
        for key in (
            "pid",
            "process_start_time",
            "command_digest",
            "run_id",
            "doc_type",
            "status",
            "exit_code",
        )
    } == {
        "pid": child.pid,
        "process_start_time": child.start_time,
        "command_digest": child.command_digest,
        "run_id": "run-owner-optimization",
        "doc_type": "passport",
        "status": "running",
        "exit_code": None,
    }
    assert record["registered_at"]
    assert record["updated_at"]
    assert identity.pid == child.pid
    assert str(tmp_path) not in registry.path.read_text()

    registry.mark_terminal(identity, exit_code=0)
    process_probe.remove(child.pid)
    registry.mark_reaped(identity, exit_code=0)

    assert json.loads(registry.path.read_text())["processes"][0]["status"] == (
        "reaped"
    )
    assert not list(registry.path.parent.glob(".tmp-*"))
    assert lease.release_after_reconciliation().released


def test_observed_spawn_ownership_mismatch_reports_actual_identity_pid(
    tmp_path,
    process_probe,
):
    process = process_probe.add(
        pid=4242,
        command=["python", "--doc-type", "doc_a"],
        run_id="run-a",
        start_time=42.0,
    )
    registry = SupervisorProcessRegistry(
        tmp_path,
        parent_run_id="run-a",
        process_probe=process_probe,
        create=True,
    )

    with pytest.raises(
        DescendantOwnershipError,
        match="Spawned child PID 4242 does not match document type doc_b",
    ):
        registry.register_observed_spawn(
            process,
            run_id="run-a",
            doc_type="doc_b",
        )


def test_cleanup_reaps_registry_child_that_never_created_manifest(tmp_path):
    probe = RecordingProbe()
    owner = probe.add(
        pid=212,
        command=["python", "--run-id", "run-orphan"],
        run_id="run-orphan",
        start_time=900.0,
    )
    PipelineRunLease.acquire(
        tmp_path,
        run_id="run-orphan",
        pid=owner.pid,
        process_probe=probe,
    )
    child = probe.add(
        pid=213,
        command=[
            "python",
            "-m",
            "crawler.eval.document_pipeline",
            "--run-id",
            "run-orphan-final",
            "--doc-type",
            "passport",
        ],
        run_id="run-orphan-final",
        start_time=1003.0,
    )
    registry = SupervisorProcessRegistry(
        tmp_path,
        parent_run_id="run-orphan",
        process_probe=probe,
    )
    registry.register_spawn(
        child.pid,
        run_id="run-orphan-final",
        doc_type="passport",
    )
    probe.remove(owner.pid)

    result = cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=0,
        process_probe=probe,
        grace_period_seconds=0,
        sleep=lambda _: None,
    )

    assert child.pid in result.terminated_pids
    assert result.lease_released
    assert not probe.is_running(child.pid)
    assert json.loads(registry.path.read_text())["processes"][0]["status"] == (
        "reaped"
    )


def test_cleanup_registry_preserves_healthy_child_of_active_owner(tmp_path):
    probe = RecordingProbe()
    owner = probe.add(
        pid=214,
        command=["python", "--run-id", "run-healthy"],
        run_id="run-healthy",
        start_time=902.0,
    )
    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-healthy",
        pid=owner.pid,
        process_probe=probe,
    )
    child = probe.add(
        pid=215,
        command=[
            "python",
            "--run-id",
            "run-healthy-final",
            "--doc-type",
            "passport",
        ],
        run_id="run-healthy-final",
        start_time=1004.0,
    )
    registry = SupervisorProcessRegistry(
        tmp_path,
        parent_run_id="run-healthy",
        process_probe=probe,
    )
    identity = registry.register_spawn(
        child.pid,
        run_id="run-healthy-final",
        doc_type="passport",
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-healthy-final",
        doc_type="passport",
        process_probe=probe,
    )
    store.manifest.pid = child.pid
    store.manifest.process_start_time = child.start_time
    store.manifest.command_digest = child.command_digest
    store.manifest.status = "in_progress"
    store._save_manifest()

    result = cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=300,
        process_probe=probe,
        grace_period_seconds=0,
        sleep=lambda _: None,
    )

    assert child.pid not in result.terminated_pids
    assert probe.is_running(child.pid)
    assert result.lease_retained_reason == "active_owner"
    probe.remove(child.pid)
    registry.mark_terminal(identity, exit_code=0)
    registry.mark_reaped(identity, exit_code=0)
    assert lease.release()


def test_corrupt_parent_registry_blocks_release_and_reclamation(
    tmp_path,
    process_probe,
):
    owner = process_probe.add(
        pid=210,
        command=["python", "--run-id", "run-corrupt"],
        run_id="run-corrupt",
        start_time=901.0,
    )
    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-corrupt",
        pid=owner.pid,
        process_probe=process_probe,
    )
    registry = SupervisorProcessRegistry(
        tmp_path,
        parent_run_id="run-corrupt",
        process_probe=process_probe,
    )
    registry.path.write_text("{", encoding="utf-8")

    release = lease.release_after_reconciliation()

    assert not release.released
    assert any("registry" in error.lower() for error in release.errors)
    process_probe.remove(owner.pid)
    with pytest.raises(ActiveRunError, match="orphaned-run cleanup"):
        PipelineRunLease.acquire(
            tmp_path,
            run_id="run-new",
            process_probe=process_probe,
        )


def test_parent_registry_rejects_symlinked_bound_run_root(
    tmp_path,
    process_probe,
):
    external = tmp_path / "external"
    external.mkdir()
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    (runs_root / "run-unsafe").symlink_to(
        external,
        target_is_directory=True,
    )

    with pytest.raises(ValueError, match="unsafe"):
        SupervisorProcessRegistry(
            tmp_path,
            parent_run_id="run-unsafe",
            process_probe=process_probe,
        )

    assert not (external / "supervisor_process_registry.json").exists()


def test_cleanup_terminates_verified_stale_owner(tmp_path, process_probe):
    cmd = ["python", "-m", "crawler.eval.document_pipeline", "--run-id", "run-stale", "--doc-type", "passport"]
    p_info = process_probe.add(pid=300, command=cmd, run_id="run-stale", start_time=1000.0)
    
    store = PipelineStateStore(tmp_path, run_id="run-stale", doc_type="passport", process_probe=process_probe)
    store.manifest.pid = 300
    store.manifest.process_start_time = 1000.0
    store.manifest.command_digest = p_info.command_digest
    store.manifest.heartbeat_at = "2000-01-01T00:00:00+00:00"  # Very old timestamp
    store._save_manifest()

    result = cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=10.0,
        process_probe=process_probe,
        grace_period_seconds=0,
        sleep=lambda _: None,
    )
    assert 300 in result.terminated_pids
    assert not process_probe.is_running(300)


def test_non_finite_timestamps_rejected():
    with pytest.raises(ValueError):
        RunManifest(
            run_id="run-nan",
            doc_type="passport",
            pid=123,
            process_start_time=float("nan"),
            command_digest="a" * 64,
            stage="init",
            status="pending",
            created_at="2026-07-25T00:00:00Z",
            updated_at="2026-07-25T00:00:00Z",
            heartbeat_at="2026-07-25T00:00:00Z",
        )


def test_invalid_stage_transition_raises(tmp_path):
    store = PipelineStateStore(tmp_path, run_id="run-1", doc_type="passport")
    store.manifest.status = "completed"
    with pytest.raises(ValueError, match="Invalid status transition"):
        store.transition_stage("init", status="in_progress")


def test_simultaneous_acquire_has_exactly_one_winner(tmp_path):
    context = multiprocessing.get_context("fork")
    start = context.Event()
    release = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_race_acquire,
            args=(tmp_path, f"run-{index}", start, release, results),
        )
        for index in range(2)
    ]

    for process in processes:
        process.start()
    start.set()
    outcomes = [results.get(timeout=5) for _ in processes]
    release.set()
    for process in processes:
        process.join(timeout=5)

    assert [outcome[0] for outcome in outcomes].count("acquired") == 1
    assert [outcome[0] for outcome in outcomes].count("rejected") == 1
    assert all(process.exitcode == 0 for process in processes)


def test_old_owner_cannot_release_newer_lease(tmp_path, process_probe):
    old = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-old",
        process_probe=process_probe,
    )
    newer_lease = {
        "run_id": "run-new",
        "pid": old.pid,
        "process_start_time": old.process_start_time,
        "command_digest": old.command_digest,
        "created_at": "2026-07-25T00:00:00+00:00",
        "updated_at": "2026-07-25T00:00:00+00:00",
    }
    atomic_write_json(old.lease_path, newer_lease)

    assert not old.release()
    assert json.loads(old.lease_path.read_text())["run_id"] == "run-new"


def test_holder_pid_reuse_does_not_block_lease_reclamation(tmp_path, process_probe):
    command = ["python", "--run-id", "run-old"]
    process_probe.add(
        pid=200,
        command=command,
        run_id="run-old",
        start_time=1000.0,
    )
    old = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-old",
        pid=200,
        process_probe=process_probe,
    )
    process_probe.add(
        pid=200,
        command=command,
        run_id="run-old",
        start_time=2000.0,
    )

    new = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-new",
        process_probe=process_probe,
    )

    assert new.run_id == "run-new"
    assert not old.release()
    assert new.release()


def test_matching_interactive_holder_still_blocks_lease_overlap(
    tmp_path,
    process_probe,
):
    process_probe.add(
        pid=200,
        command=["copilot", "--resume=session"],
        start_time=1000.0,
    )
    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-old",
        pid=200,
        process_probe=process_probe,
    )

    with pytest.raises(ActiveRunError):
        PipelineRunLease.acquire(
            tmp_path,
            run_id="run-new",
            process_probe=process_probe,
        )

    assert lease.release()


def test_cleanup_waits_then_revalidates_before_sigkill(tmp_path):
    probe = RecordingProbe(exit_on_sigterm=False)
    command = ["python", "--run-id", "run-stale"]
    process = probe.add(
        pid=300,
        command=command,
        run_id="run-stale",
        start_time=1000.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-stale",
        doc_type="passport",
        process_probe=probe,
    )
    store.manifest.pid = process.pid
    store.manifest.process_start_time = process.start_time
    store.manifest.command_digest = process.command_digest
    store.manifest.heartbeat_at = "2000-01-01T00:00:00+00:00"
    store._save_manifest()
    waits = []

    cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=10,
        process_probe=probe,
        grace_period_seconds=0.25,
        sleep=waits.append,
    )

    assert waits == [0.25, 0.25]
    assert probe.signals == [
        (300, signal.SIGTERM),
        (300, signal.SIGKILL),
    ]


def test_cleanup_retains_dead_owner_lease_when_process_survives_sigkill(
    tmp_path,
):
    probe = RecordingProbe(exit_on_sigterm=False)

    def never_exits(pid, sig=signal.SIGTERM):
        probe.signals.append((pid, sig))
        return True

    probe.terminate_process = never_exits
    lease_owner = probe.add(
        pid=200,
        command=["python", "--run-id", "run-stale"],
        run_id="run-stale",
        start_time=900.0,
    )
    PipelineRunLease.acquire(
        tmp_path,
        run_id="run-stale",
        pid=lease_owner.pid,
        process_probe=probe,
    )
    child = probe.add(
        pid=300,
        command=["python", "--run-id", "run-stale"],
        run_id="run-stale",
        start_time=1000.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-stale",
        doc_type="passport",
        process_probe=probe,
    )
    store.manifest.pid = child.pid
    store.manifest.process_start_time = child.start_time
    store.manifest.command_digest = child.command_digest
    store.manifest.heartbeat_at = "2000-01-01T00:00:00+00:00"
    store._save_manifest()
    probe.remove(lease_owner.pid)
    waits = []

    result = cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=10,
        process_probe=probe,
        grace_period_seconds=0.25,
        sleep=waits.append,
    )

    assert waits == [0.25, 0.25]
    assert result.remaining_pids == [child.pid]
    assert not result.lease_released
    assert (tmp_path / "active_lease.json").is_file()
    assert result.quarantined_paths == []


def test_cleanup_removes_dead_owner_lease_only_after_post_kill_absence(
    tmp_path,
):
    probe = RecordingProbe(exit_on_sigterm=False)
    lease_owner = probe.add(
        pid=200,
        command=["python", "--run-id", "run-stale"],
        run_id="run-stale",
        start_time=900.0,
    )
    PipelineRunLease.acquire(
        tmp_path,
        run_id="run-stale",
        pid=lease_owner.pid,
        process_probe=probe,
    )
    child = probe.add(
        pid=300,
        command=["python", "--run-id", "run-stale"],
        run_id="run-stale",
        start_time=1000.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-stale",
        doc_type="passport",
        process_probe=probe,
    )
    store.manifest.pid = child.pid
    store.manifest.process_start_time = child.start_time
    store.manifest.command_digest = child.command_digest
    store.manifest.heartbeat_at = "2000-01-01T00:00:00+00:00"
    store._save_manifest()
    probe.remove(lease_owner.pid)
    waits = []

    result = cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=10,
        process_probe=probe,
        grace_period_seconds=0.25,
        sleep=waits.append,
    )

    assert waits == [0.25, 0.25]
    assert result.remaining_pids == []
    assert result.lease_released
    assert not (tmp_path / "active_lease.json").exists()


def test_external_cleanup_cannot_release_active_owner_lease(
    tmp_path,
    process_probe,
):
    lease = PipelineRunLease.acquire(
        tmp_path,
        run_id="run-active",
        process_probe=process_probe,
    )

    result = cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=0,
        process_probe=process_probe,
        grace_period_seconds=0,
        sleep=lambda _: None,
    )

    assert not result.lease_released
    assert result.lease_retained_reason == "active_owner"
    assert lease.lease_path.is_file()
    assert lease.release()


def test_cleanup_refuses_recycled_descendant_pid(tmp_path):
    probe = RecordingProbe()
    parent_command = ["python", "--run-id", "run-stale"]
    parent = probe.add(
        pid=300,
        command=parent_command,
        run_id="run-stale",
        start_time=1000.0,
    )
    descendant = probe.add(
        pid=301,
        command=["copilot", "--run-id", "run-stale"],
        run_id="run-stale",
        start_time=1001.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-stale",
        doc_type="passport",
        process_probe=probe,
    )
    store.manifest.pid = parent.pid
    store.manifest.process_start_time = parent.start_time
    store.manifest.command_digest = parent.command_digest
    store.manifest.heartbeat_at = "2000-01-01T00:00:00+00:00"
    store.add_descendant_pid(descendant.pid)
    probe.add(
        pid=301,
        command=["unrelated", "--run-id", "other-run"],
        run_id="other-run",
        start_time=2000.0,
    )
    store._save_manifest()

    cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=10,
        process_probe=probe,
        grace_period_seconds=0,
        sleep=lambda _: None,
    )

    assert all(pid != 301 for pid, _ in probe.signals)
    assert probe.get_process_info(301).start_time == 2000.0


def test_wait_for_verified_descendants_returns_after_exit(tmp_path):
    probe = ProcessProbe()
    descendant = probe.add(
        pid=301,
        command=["copilot", "--run-id", "run-1"],
        run_id="run-1",
        start_time=1001.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-1",
        doc_type="passport",
        process_probe=probe,
    )
    store.add_descendant_pid(descendant.pid)
    now = [0.0]

    def exit_during_wait(seconds):
        now[0] += seconds
        probe.remove(descendant.pid)

    store.wait_for_verified_descendants(
        timeout_seconds=1,
        poll_interval_seconds=0.1,
        sleep=exit_during_wait,
        monotonic=lambda: now[0],
    )

    assert store.manifest.descendant_pids == []


def test_wait_for_verified_descendants_timeout_fails_closed(tmp_path):
    probe = ProcessProbe()
    descendant = probe.add(
        pid=301,
        command=["copilot", "--run-id", "run-1"],
        run_id="run-1",
        start_time=1001.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-1",
        doc_type="passport",
        process_probe=probe,
    )
    store.add_descendant_pid(descendant.pid)

    with pytest.raises(DescendantExitTimeoutError, match="301"):
        store.wait_for_verified_descendants(
            timeout_seconds=0,
            sleep=lambda _: None,
        )

    assert store.manifest.descendant_pids


def test_descendant_can_bind_run_identity_from_verified_environment(tmp_path):
    probe = ProcessProbe()
    descendant = probe.add(
        pid=401,
        command=["copilot-runtime", "--stdio"],
        run_id="run-env",
        start_time=1001.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-env",
        doc_type="passport",
        process_probe=probe,
    )

    store.add_descendant_pid(descendant.pid)

    assert [identity.pid for identity in store.manifest.descendant_pids] == [
        descendant.pid
    ]


def test_cleanup_includes_completed_manifest_with_live_verified_descendant(tmp_path):
    probe = RecordingProbe()
    descendant = probe.add(
        pid=501,
        command=["copilot-runtime", "--run-id", "run-completed"],
        run_id="run-completed",
        start_time=1001.0,
    )
    interactive = probe.add(
        pid=502,
        command=["copilot", "--resume=session"],
        start_time=1002.0,
    )
    store = PipelineStateStore(
        tmp_path,
        run_id="run-completed",
        doc_type="passport",
        process_probe=probe,
    )
    store.add_descendant_pid(descendant.pid)
    store.manifest.status = "completed"
    store._save_manifest()

    result = cleanup_stalled_runs(
        tmp_path,
        stale_threshold_seconds=10,
        process_probe=probe,
        grace_period_seconds=0,
        sleep=lambda _: None,
    )

    assert str(store.manifest_path) in result.stale_manifests
    assert result.terminated_pids == [descendant.pid]
    assert probe.is_running(interactive.pid)
