import fcntl
import hashlib
import json
import math
import os
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from crawler.eval.agent_runtime import (
    AgentLifecycleError,
    AgentProvenance,
    bind_lifecycle_failure_probe,
)


class ActiveRunError(Exception):
    """Raised when an active or unverifiable owner holds a run lease."""


class DescendantOwnershipError(Exception):
    """Raised when a descendant cannot be registered as owned by a run."""


class DescendantExitTimeoutError(TimeoutError):
    """Raised while verified run descendants remain alive at the deadline."""


def compute_command_digest(command: list[str]) -> str:
    """Compute a stable SHA256 digest of command-line arguments."""
    payload = json.dumps(command, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _command_has_run_id(command: list[str], run_id: str) -> bool:
    for index, argument in enumerate(command):
        if argument == run_id:
            return True
        if argument == f"--run-id={run_id}":
            return True
        if argument == "--run-id" and index + 1 < len(command):
            if command[index + 1] == run_id:
                return True
    return False


def _extract_run_id(command: list[str]) -> str | None:
    for index, argument in enumerate(command):
        if argument.startswith("--run-id="):
            return argument.split("=", 1)[1]
        if argument == "--run-id" and index + 1 < len(command):
            return command[index + 1]
    return None


def _command_has_doc_type(command: list[str], doc_type: str) -> bool:
    for index, argument in enumerate(command):
        if argument == f"--doc-type={doc_type}":
            return True
        if argument == "--doc-type" and index + 1 < len(command):
            return command[index + 1] == doc_type
    return False


def _is_interactive_copilot(command: list[str]) -> bool:
    joined = " ".join(command).lower()
    return "copilot" in joined and "--resume" in joined


class ProcessInfo:
    """Observed process identity."""

    def __init__(
        self,
        pid: int,
        command: list[str],
        start_time: float,
        run_id: str | None = None,
    ):
        self.pid = pid
        self.command = command
        self.start_time = start_time
        self.run_id = run_id
        self.command_digest = compute_command_digest(command)


class ProcessProbe:
    """Injectable probe for querying and signaling processes."""

    def __init__(self) -> None:
        self._mock_processes: dict[int, ProcessInfo] = {}

    def add(
        self,
        pid: int,
        command: list[str],
        run_id: str | None = None,
        start_time: float = 1000.0,
    ) -> ProcessInfo:
        """Register deterministic process state for tests and simulations."""
        info = ProcessInfo(
            pid=pid,
            command=command,
            start_time=start_time,
            run_id=run_id,
        )
        self._mock_processes[pid] = info
        return info

    def remove(self, pid: int) -> None:
        """Remove deterministic process state."""
        self._mock_processes.pop(pid, None)

    def is_running(self, pid: int) -> bool:
        """Check whether a PID currently exists."""
        if pid in self._mock_processes:
            return True
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False

    def get_process_info(self, pid: int) -> ProcessInfo | None:
        """Read PID, argv, and kernel process start time."""
        if pid in self._mock_processes:
            return self._mock_processes[pid]
        if not self.is_running(pid):
            return None

        proc_cmdline = Path(f"/proc/{pid}/cmdline")
        try:
            raw = proc_cmdline.read_bytes()
            command = [
                part.decode("utf-8", errors="replace")
                for part in raw.split(b"\x00")
                if part
            ]
            if not command and pid == os.getpid():
                command = list(sys.argv)
            return ProcessInfo(
                pid=pid,
                command=command,
                start_time=self._get_pid_start_time(pid),
                run_id=(
                    _extract_run_id(command)
                    or self._get_environment_run_id(pid)
                ),
            )
        except (OSError, ValueError):
            return None

    @staticmethod
    def _get_environment_run_id(pid: int) -> str | None:
        try:
            environment = Path(f"/proc/{pid}/environ").read_bytes()
        except OSError:
            return None
        prefix = b"PHASE74_RUN_ID="
        for entry in environment.split(b"\x00"):
            if entry.startswith(prefix):
                value = entry[len(prefix) :].decode(
                    "utf-8",
                    errors="strict",
                )
                return value or None
        return None

    def _get_pid_start_time(self, pid: int) -> float:
        """Read Linux /proc start ticks, which are stable for a PID lifetime."""
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        closing_paren = stat_text.rfind(")")
        if closing_paren == -1:
            raise ValueError(f"Malformed /proc stat for PID {pid}")
        fields_after_command = stat_text[closing_paren + 2 :].split()
        return float(fields_after_command[19])

    def terminate_process(
        self,
        pid: int,
        sig: int = signal.SIGTERM,
    ) -> bool:
        """Send a specific signal to a PID."""
        if pid in self._mock_processes:
            self.remove(pid)
            return True
        try:
            os.kill(pid, sig)
            return True
        except (OSError, ProcessLookupError):
            return False


class ProcessIdentity(BaseModel):
    """Persisted ownership identity for a process."""

    pid: int = Field(gt=0)
    process_start_time: float
    command_digest: str = Field(min_length=64, max_length=64)
    run_id: str = Field(min_length=1)

    @field_validator("process_start_time")
    @classmethod
    def validate_finite_start_time(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Timestamp value must be finite")
        return value


class SupervisorProcessRecord(BaseModel):
    """PII-free parent-owned lifecycle record for one spawned child."""

    pid: int = Field(gt=0)
    process_start_time: float | None = None
    command_digest: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
    )
    run_id: str = Field(min_length=1)
    doc_type: str = Field(min_length=1, max_length=128)
    identity_verified: bool = True
    status: Literal[
        "running",
        "unverified_spawn",
        "terminal",
        "reaped",
        "requires_cleanup",
    ]
    exit_code: int | None = None
    registered_at: str
    updated_at: str

    @field_validator("run_id", "doc_type")
    @classmethod
    def validate_safe_label(cls, value: str) -> str:
        if (
            value in {".", ".."}
            or not value
            or any(
                character
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
                for character in value
            )
        ):
            raise ValueError("Process registry labels must be path-safe")
        return value

    @field_validator("process_start_time")
    @classmethod
    def validate_optional_start_time(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Timestamp value must be finite")
        return value

    @model_validator(mode="after")
    def validate_identity_shape(self) -> "SupervisorProcessRecord":
        has_identity = (
            self.process_start_time is not None
            and self.command_digest is not None
        )
        if self.identity_verified != has_identity:
            raise ValueError("Process registry identity verification is inconsistent")
        if not self.identity_verified and self.status in {"running", "terminal"}:
            raise ValueError("Unverified process registry status is invalid")
        return self


class _SupervisorProcessRegistryData(BaseModel):
    schema_version: Literal["phase74-supervisor-process-registry-v1"]
    run_id: str
    initialized: Literal[True]
    processes: list[SupervisorProcessRecord] = Field(default_factory=list)

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return SupervisorProcessRecord.validate_safe_label(value)


def _matches_process_identity(
    identity: ProcessIdentity,
    process: ProcessInfo,
) -> bool:
    run_id_matches = (
        _command_has_run_id(process.command, identity.run_id)
        or process.run_id == identity.run_id
    )
    return (
        process.pid == identity.pid
        and process.start_time == identity.process_start_time
        and compute_command_digest(process.command) == identity.command_digest
        and run_id_matches
        and not _is_interactive_copilot(process.command)
    )


class StageManifest(BaseModel):
    """Manifest for an individual pipeline stage execution."""

    stage: str
    status: Literal[
        "pending",
        "in_progress",
        "completed",
        "failed",
        "stalled",
        "cancelled",
    ]
    input_hash: str
    output_hash: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    provenance: AgentProvenance | dict[str, Any] | None = None
    error: str | None = None


class RunManifest(BaseModel):
    """Durable manifest for a document pipeline run."""

    run_id: str
    doc_type: str
    pid: int
    process_start_time: float
    command_digest: str
    stage: str = "init"
    status: Literal[
        "pending",
        "in_progress",
        "completed",
        "failed",
        "stalled",
        "cancelled",
    ] = "pending"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    heartbeat_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    sequence: int = 0
    deadline: float | None = None
    descendant_pids: list[ProcessIdentity] = Field(default_factory=list)
    error_classification: str | None = None
    input_hashes: dict[str, str] = Field(default_factory=dict)
    output_hashes: dict[str, str] = Field(default_factory=dict)

    @field_validator("process_start_time", "deadline")
    @classmethod
    def validate_finite_timestamps(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Timestamp value must be finite")
        return value


class CleanupResult(BaseModel):
    """Result summary of a stalled run cleanup pass."""

    scanned_manifests: list[str] = Field(default_factory=list)
    scanned_registries: list[str] = Field(default_factory=list)
    stale_manifests: list[str] = Field(default_factory=list)
    terminated_pids: list[int] = Field(default_factory=list)
    killed_pids: list[int] = Field(default_factory=list)
    remaining_pids: list[int] = Field(default_factory=list)
    retained_paths: list[str] = Field(default_factory=list)
    quarantined_paths: list[str] = Field(default_factory=list)
    removed_paths: list[str] = Field(default_factory=list)
    retained_processes: list[int] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    audit_path: str | None = None
    errors: list[str] = Field(default_factory=list)
    lease_released: bool = False
    lease_retained_reason: str | None = None


class LeaseReleaseResult(BaseModel):
    """Fail-closed result of an owning supervisor's reconciliation release."""

    released: bool = False
    run_id: str
    scanned_manifest_count: int = 0
    remaining_pids: list[int] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class _LeaseRecord(BaseModel):
    run_id: str
    manifest_root_identity: str = Field(min_length=64, max_length=64)
    pid: int = Field(gt=0)
    process_start_time: float
    command_digest: str = Field(min_length=64, max_length=64)
    created_at: str
    updated_at: str

    @field_validator("process_start_time")
    @classmethod
    def validate_finite_start_time(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Timestamp value must be finite")
        return value


def _json_text(data: Any, indent: int = 2) -> str:
    if isinstance(data, BaseModel):
        return data.model_dump_json(indent=indent)
    return json.dumps(data, indent=indent, default=str)


def _fsync_directory(path: Path) -> None:
    try:
        directory_fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        pass


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON atomically, flush it, and sync its containing directory."""
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=".tmp-",
        dir=str(parent),
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(temporary_fd, "w", encoding="utf-8") as file:
            file.write(_json_text(data, indent=indent))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(parent)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _exclusive_write_json(path: Path, data: Any) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    file_descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
            file.write(_json_text(data))
            file.flush()
            os.fsync(file.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    _fsync_directory(path.parent)


@contextmanager
def _lease_guard(lease_path: Path) -> Iterator[None]:
    lock_path = lease_path.with_suffix(".lock")
    lock_descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)


def _read_lease(lease_path: Path) -> _LeaseRecord:
    return _LeaseRecord.model_validate_json(
        lease_path.read_text(encoding="utf-8")
    )


def _manifest_root_identity(root_dir: Path, run_id: str) -> str:
    payload = f"{Path(root_dir).resolve()}\0{run_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bound_manifest_paths(
    root_dir: Path,
    run_id: str,
) -> tuple[list[Path], list[str]]:
    runs_root = Path(root_dir) / "runs"
    if not runs_root.is_dir():
        return [], []
    bound_roots = sorted(
        path
        for path in runs_root.iterdir()
        if path.name == run_id or path.name.startswith(f"{run_id}-")
    )
    manifests: list[Path] = []
    errors: list[str] = []
    for bound_root in bound_roots:
        if bound_root.is_symlink() or not bound_root.is_dir():
            errors.append("Bound run root is unavailable or unsafe")
            continue
        for current_root, directory_names, file_names in os.walk(
            bound_root,
            followlinks=False,
        ):
            current = Path(current_root)
            unsafe_directories = [
                name
                for name in directory_names
                if (current / name).is_symlink()
            ]
            if unsafe_directories:
                errors.append("Bound run root contains an unsafe directory")
                directory_names[:] = [
                    name
                    for name in directory_names
                    if name not in unsafe_directories
                ]
            if "run_manifest.json" in file_names:
                manifest_path = current / "run_manifest.json"
                if manifest_path.is_symlink():
                    errors.append("Bound run manifest is unsafe")
                else:
                    manifests.append(manifest_path)
    manifests.sort()
    return manifests, errors


def _registry_path(root_dir: Path, parent_run_id: str) -> Path:
    return (
        Path(root_dir)
        / "runs"
        / parent_run_id
        / "supervisor_process_registry.json"
    )


def _registry_label(root_dir: Path, path: Path) -> str:
    try:
        relative = path.relative_to(Path(root_dir))
    except ValueError:
        return "runs/<unsafe>/supervisor_process_registry.json"
    return relative.as_posix()


def _read_process_registry(
    path: Path,
    *,
    expected_parent_run_id: str,
) -> _SupervisorProcessRegistryData:
    if path.is_symlink():
        raise ValueError("Parent process registry is unsafe")
    registry = _SupervisorProcessRegistryData.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if registry.run_id != expected_parent_run_id:
        raise ValueError("Parent process registry run identity mismatch")
    return registry


class SupervisorProcessRegistry:
    """Atomic parent-owned registry that exists independently of child manifests."""

    def __init__(
        self,
        root_dir: Path,
        *,
        parent_run_id: str,
        process_probe: ProcessProbe | None = None,
        create: bool = False,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.parent_run_id = SupervisorProcessRecord.validate_safe_label(
            parent_run_id
        )
        self.process_probe = process_probe or ProcessProbe()
        self.path = _registry_path(self.root_dir, self.parent_run_id)
        runs_root = self.root_dir / "runs"
        if runs_root.is_symlink():
            raise ValueError("Parent process registry root is unsafe")
        runs_root.mkdir(parents=True, exist_ok=True)
        if self.path.parent.is_symlink():
            raise ValueError("Parent process registry run root is unsafe")
        self.path.parent.mkdir(exist_ok=True)
        with _lease_guard(self.path):
            if self.path.exists():
                _read_process_registry(
                    self.path,
                    expected_parent_run_id=self.parent_run_id,
                )
            elif create:
                atomic_write_json(
                    self.path,
                    _SupervisorProcessRegistryData(
                        schema_version="phase74-supervisor-process-registry-v1",
                        run_id=self.parent_run_id,
                        initialized=True,
                    ),
                )
            else:
                raise FileNotFoundError(
                    "Initialized parent process registry is unavailable"
                )

    @staticmethod
    def _key(
        identity: ProcessIdentity,
    ) -> tuple[int, float, str, str]:
        return (
            identity.pid,
            identity.process_start_time,
            identity.command_digest,
            identity.run_id,
        )

    def _update(
        self,
        update: Callable[[_SupervisorProcessRegistryData], Any],
    ) -> Any:
        with _lease_guard(self.path):
            registry = _read_process_registry(
                self.path,
                expected_parent_run_id=self.parent_run_id,
            )
            result = update(registry)
            atomic_write_json(self.path, registry)
            return result

    def register_spawn(
        self,
        pid: int,
        *,
        run_id: str,
        doc_type: str,
    ) -> ProcessIdentity:
        """Verify and durably register an exact child identity after spawn."""
        SupervisorProcessRecord.validate_safe_label(run_id)
        SupervisorProcessRecord.validate_safe_label(doc_type)
        if not (
            run_id == self.parent_run_id
            or run_id.startswith(f"{self.parent_run_id}-")
        ):
            raise DescendantOwnershipError(
                "Spawned child run is not bound to the parent registry"
            )
        process = self.process_probe.get_process_info(pid)
        if process is None or not self.process_probe.is_running(pid):
            raise DescendantOwnershipError(
                f"Cannot register missing spawned child PID {pid}"
            )
        return self.register_observed_spawn(
            process,
            run_id=run_id,
            doc_type=doc_type,
        )

    def register_observed_spawn(
        self,
        process: ProcessInfo,
        *,
        run_id: str,
        doc_type: str,
    ) -> ProcessIdentity:
        """Atomically register one already-observed exact child identity.

        The caller owns the process handle and obtains this immutable snapshot
        inside a bounded post-spawn probe window. Avoiding a second /proc read
        closes the short visibility race between observation and registration.
        """
        SupervisorProcessRecord.validate_safe_label(run_id)
        SupervisorProcessRecord.validate_safe_label(doc_type)
        if not (
            run_id == self.parent_run_id
            or run_id.startswith(f"{self.parent_run_id}-")
        ):
            raise DescendantOwnershipError(
                "Spawned child run is not bound to the parent registry"
            )
        identity = ProcessIdentity(
            pid=process.pid,
            process_start_time=process.start_time,
            command_digest=process.command_digest,
            run_id=run_id,
        )
        if not _matches_process_identity(identity, process):
            raise DescendantOwnershipError(
                f"Spawned child PID {identity.pid} is not owned by run {run_id}"
            )
        if (
            doc_type != "__preflight__"
            and not _command_has_doc_type(process.command, doc_type)
        ):
            raise DescendantOwnershipError(
                f"Spawned child PID {identity.pid} does not match document "
                f"type {doc_type}"
            )

        def register(registry: _SupervisorProcessRegistryData) -> None:
            key = self._key(identity)
            registry.processes = [
                record
                for record in registry.processes
                if self._key(record) != key
            ]
            registry.processes.append(
                SupervisorProcessRecord(
                    **identity.model_dump(),
                    doc_type=doc_type,
                    identity_verified=True,
                    status="running",
                    registered_at=datetime.now(timezone.utc).isoformat(),
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
            )

        self._update(register)
        return identity

    def register_unverified_spawn(
        self,
        pid: int,
        *,
        run_id: str,
        doc_type: str,
    ) -> None:
        """Record an exact returned handle before cleanup when PID identity is unavailable."""
        if pid <= 0:
            raise ValueError("Spawned process PID must be positive")
        SupervisorProcessRecord.validate_safe_label(run_id)
        SupervisorProcessRecord.validate_safe_label(doc_type)
        if not (
            run_id == self.parent_run_id
            or run_id.startswith(f"{self.parent_run_id}-")
        ):
            raise DescendantOwnershipError(
                "Spawned child run is not bound to the parent registry"
            )

        def register(registry: _SupervisorProcessRegistryData) -> None:
            registry.processes = [
                record
                for record in registry.processes
                if not (
                    not record.identity_verified
                    and record.pid == pid
                    and record.run_id == run_id
                    and record.doc_type == doc_type
                )
            ]
            now = datetime.now(timezone.utc).isoformat()
            registry.processes.append(
                SupervisorProcessRecord(
                    pid=pid,
                    run_id=run_id,
                    doc_type=doc_type,
                    identity_verified=False,
                    status="unverified_spawn",
                    registered_at=now,
                    updated_at=now,
                )
            )

        self._update(register)

    def _set_unverified_status(
        self,
        pid: int,
        *,
        run_id: str,
        doc_type: str,
        status: Literal["reaped", "requires_cleanup"],
        exit_code: int | None,
    ) -> None:
        def set_status(registry: _SupervisorProcessRegistryData) -> None:
            matches = [
                record
                for record in registry.processes
                if (
                    not record.identity_verified
                    and record.pid == pid
                    and record.run_id == run_id
                    and record.doc_type == doc_type
                )
            ]
            if len(matches) != 1:
                raise DescendantOwnershipError(
                    "Unverified spawned child is absent from parent registry"
                )
            matches[0].status = status
            matches[0].exit_code = exit_code
            matches[0].updated_at = datetime.now(timezone.utc).isoformat()

        self._update(set_status)

    def mark_unverified_reaped(
        self,
        pid: int,
        *,
        run_id: str,
        doc_type: str,
        exit_code: int | None,
    ) -> None:
        self._set_unverified_status(
            pid,
            run_id=run_id,
            doc_type=doc_type,
            status="reaped",
            exit_code=exit_code,
        )

    def mark_unverified_requires_cleanup(
        self,
        pid: int,
        *,
        run_id: str,
        doc_type: str,
        exit_code: int | None,
    ) -> None:
        self._set_unverified_status(
            pid,
            run_id=run_id,
            doc_type=doc_type,
            status="requires_cleanup",
            exit_code=exit_code,
        )

    def _set_status(
        self,
        identity: ProcessIdentity,
        *,
        status: Literal["terminal", "reaped", "requires_cleanup"],
        exit_code: int | None,
    ) -> None:
        def set_status(registry: _SupervisorProcessRegistryData) -> None:
            key = self._key(identity)
            matches = [
                record
                for record in registry.processes
                if self._key(record) == key
            ]
            if len(matches) != 1:
                raise DescendantOwnershipError(
                    "Spawned child identity is absent from parent registry"
                )
            matches[0].status = status
            matches[0].exit_code = exit_code
            matches[0].updated_at = datetime.now(timezone.utc).isoformat()

        self._update(set_status)

    def mark_terminal(
        self,
        identity: ProcessIdentity,
        *,
        exit_code: int | None,
    ) -> None:
        self._set_status(
            identity,
            status="terminal",
            exit_code=exit_code,
        )

    def mark_reaped(
        self,
        identity: ProcessIdentity,
        *,
        exit_code: int | None,
    ) -> None:
        if _verified_process(identity, self.process_probe) is not None:
            raise DescendantExitTimeoutError(
                f"Registered child PID {identity.pid} is still alive"
            )
        self._set_status(
            identity,
            status="reaped",
            exit_code=exit_code,
        )

    def mark_requires_cleanup(
        self,
        identity: ProcessIdentity,
        *,
        exit_code: int | None,
    ) -> None:
        self._set_status(
            identity,
            status="requires_cleanup",
            exit_code=exit_code,
        )

    def records(self) -> list[SupervisorProcessRecord]:
        with _lease_guard(self.path):
            return list(
                _read_process_registry(
                    self.path,
                    expected_parent_run_id=self.parent_run_id,
                ).processes
            )


def _scan_bound_processes(
    root_dir: Path,
    record: _LeaseRecord,
    probe: ProcessProbe,
) -> tuple[list[Path], list[ProcessIdentity], list[str]]:
    expected_identity = _manifest_root_identity(root_dir, record.run_id)
    if record.manifest_root_identity != expected_identity:
        return [], [], ["Lease manifest-root identity does not match its state root"]

    paths, errors = _bound_manifest_paths(root_dir, record.run_id)
    remaining: list[ProcessIdentity] = []
    lease_owner_key = (
        record.pid,
        record.process_start_time,
        record.command_digest,
    )
    for manifest_path in paths:
        try:
            manifest = RunManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            relative = manifest_path.relative_to(Path(root_dir) / "runs")
            directory_run_id = relative.parts[0]
            if (
                manifest.run_id != directory_run_id
                or not (
                    manifest.run_id == record.run_id
                    or manifest.run_id.startswith(f"{record.run_id}-")
                )
            ):
                raise ValueError("manifest run identity does not match bound root")
        except (OSError, ValueError) as error:
            errors.append(
                f"Bound run manifest is unavailable or invalid: {type(error).__name__}"
            )
            continue

        for identity in [_manifest_owner(manifest), *manifest.descendant_pids]:
            identity_key = (
                identity.pid,
                identity.process_start_time,
                identity.command_digest,
            )
            if identity_key == lease_owner_key:
                continue
            process = probe.get_process_info(identity.pid)
            if process is None:
                if probe.is_running(identity.pid):
                    errors.append(
                        f"Bound PID {identity.pid} is alive but unverifiable"
                    )
                continue
            if _matches_process_identity(identity, process):
                remaining.append(identity)

    registry_path = _registry_path(root_dir, record.run_id)
    paths.append(registry_path)
    try:
        registry = _read_process_registry(
            registry_path,
            expected_parent_run_id=record.run_id,
        )
    except (OSError, ValueError) as error:
        errors.append(
            "Bound parent process registry is unavailable or invalid: "
            f"{type(error).__name__}"
        )
    else:
        for registry_record in registry.processes:
            if not registry_record.identity_verified:
                if registry_record.status != "reaped":
                    errors.append(
                        "Bound parent process registry contains an unreaped "
                        f"unverified spawn PID {registry_record.pid}"
                    )
                continue
            identity = ProcessIdentity(
                pid=registry_record.pid,
                process_start_time=registry_record.process_start_time,
                command_digest=registry_record.command_digest,
                run_id=registry_record.run_id,
            )
            identity_key = (
                identity.pid,
                identity.process_start_time,
                identity.command_digest,
            )
            if identity_key == lease_owner_key:
                continue
            process = probe.get_process_info(identity.pid)
            if process is None:
                if probe.is_running(identity.pid):
                    errors.append(
                        f"Bound registry PID {identity.pid} is alive but "
                        "unverifiable"
                    )
                continue
            if _matches_process_identity(identity, process):
                remaining.append(identity)

    deduplicated = {
        (
            identity.pid,
            identity.process_start_time,
            identity.command_digest,
            identity.run_id,
        ): identity
        for identity in remaining
    }
    return paths, list(deduplicated.values()), errors


def _lease_holder_is_active(
    record: _LeaseRecord,
    probe: ProcessProbe,
) -> bool:
    process = probe.get_process_info(record.pid)
    if process is None:
        if probe.is_running(record.pid):
            raise ActiveRunError(
                f"Run lease holder PID {record.pid} is alive but unverifiable"
            )
        return False
    return (
        process.pid == record.pid
        and process.start_time == record.process_start_time
        and compute_command_digest(process.command) == record.command_digest
    )


class PipelineRunLease:
    """Exclusive process lease protected by an inter-process file lock."""

    def __init__(
        self,
        root_dir: Path,
        lease_path: Path,
        run_id: str,
        manifest_root_identity: str,
        pid: int,
        process_start_time: float,
        command_digest: str,
        process_probe: ProcessProbe,
    ):
        self.root_dir = Path(root_dir)
        self.lease_path = lease_path
        self.run_id = run_id
        self.manifest_root_identity = manifest_root_identity
        self.pid = pid
        self.process_start_time = process_start_time
        self.command_digest = command_digest
        self.process_probe = process_probe

    @classmethod
    def acquire(
        cls,
        root_dir: Path,
        run_id: str,
        pid: int | None = None,
        process_probe: ProcessProbe | None = None,
        heartbeat_timeout_seconds: float = 300.0,
    ) -> "PipelineRunLease":
        del heartbeat_timeout_seconds
        root_dir = Path(root_dir)
        root_dir.mkdir(parents=True, exist_ok=True)
        lease_path = root_dir / "active_lease.json"
        probe = process_probe or ProcessProbe()
        current_pid = pid if pid is not None else os.getpid()
        current_process = probe.get_process_info(current_pid)
        if current_process is None:
            raise ActiveRunError(
                f"Cannot acquire lease: PID {current_pid} identity is unavailable"
            )

        now = datetime.now(timezone.utc).isoformat()
        record = _LeaseRecord(
            run_id=run_id,
            manifest_root_identity=_manifest_root_identity(root_dir, run_id),
            pid=current_pid,
            process_start_time=current_process.start_time,
            command_digest=compute_command_digest(current_process.command),
            created_at=now,
            updated_at=now,
        )
        with _lease_guard(lease_path):
            if lease_path.exists():
                try:
                    holder = _read_lease(lease_path)
                except (OSError, ValueError) as error:
                    raise ActiveRunError(
                        f"Existing run lease is unverifiable: {error}"
                    ) from error
                if _lease_holder_is_active(holder, probe):
                    raise ActiveRunError(
                        "Active run lease held by "
                        f"run_id={holder.run_id}, pid={holder.pid}"
                    )
                _, remaining, errors = _scan_bound_processes(
                    root_dir,
                    holder,
                    probe,
                )
                if errors or remaining:
                    detail = (
                        f"; verified PIDs: "
                        f"{sorted(identity.pid for identity in remaining)}"
                        if remaining
                        else ""
                    )
                    raise ActiveRunError(
                        "Cannot reclaim dead owner lease: orphaned-run cleanup "
                        f"is required{detail}"
                    )
                lease_path.unlink()
                _fsync_directory(lease_path.parent)
            try:
                registry = SupervisorProcessRegistry(
                    root_dir,
                    parent_run_id=run_id,
                    process_probe=probe,
                    create=True,
                )
                if registry.records():
                    raise ActiveRunError(
                        "Cannot acquire lease: initialized parent process "
                        "registry is not empty"
                    )
            except ActiveRunError:
                raise
            except (OSError, ValueError) as error:
                raise ActiveRunError(
                    "Cannot acquire lease: parent process registry "
                    f"initialization failed: {type(error).__name__}"
                ) from error
            _exclusive_write_json(lease_path, record)

        return cls(
            root_dir=root_dir,
            lease_path=lease_path,
            run_id=record.run_id,
            manifest_root_identity=record.manifest_root_identity,
            pid=record.pid,
            process_start_time=record.process_start_time,
            command_digest=record.command_digest,
            process_probe=probe,
        )

    def release_after_reconciliation(self) -> LeaseReleaseResult:
        """Release this owner's lease only after its bound process scan is empty."""
        outcome = LeaseReleaseResult(run_id=self.run_id)
        with _lease_guard(self.lease_path):
            if not self.lease_path.exists():
                outcome.errors.append("Active lease file is unavailable")
                return outcome
            try:
                active = _read_lease(self.lease_path)
            except (OSError, ValueError) as error:
                outcome.errors.append(f"Active lease is invalid: {type(error).__name__}")
                return outcome
            owns_active_lease = (
                active.run_id == self.run_id
                and active.manifest_root_identity == self.manifest_root_identity
                and active.pid == self.pid
                and active.process_start_time == self.process_start_time
                and active.command_digest == self.command_digest
            )
            if not owns_active_lease:
                outcome.errors.append("Active lease identity changed")
                return outcome
            try:
                owner_is_active = _lease_holder_is_active(
                    active,
                    self.process_probe,
                )
            except ActiveRunError as error:
                outcome.errors.append(str(error))
                return outcome
            if not owner_is_active:
                outcome.errors.append("Lease owner is no longer active")
                return outcome
            paths, remaining, errors = _scan_bound_processes(
                self.root_dir,
                active,
                self.process_probe,
            )
            outcome.scanned_manifest_count = len(paths)
            outcome.remaining_pids = sorted(
                identity.pid for identity in remaining
            )
            outcome.errors.extend(errors)
            if remaining or errors:
                return outcome
            self.lease_path.unlink()
            _fsync_directory(self.lease_path.parent)
            outcome.released = True
            return outcome

    def release(self) -> bool:
        """Compatibility boolean for fail-closed owner reconciliation release."""
        return self.release_after_reconciliation().released


class PipelineStateStore:
    """Durable run state, stage completion, heartbeat, and descendants."""

    def __init__(
        self,
        root_dir: Path,
        run_id: str,
        doc_type: str,
        process_probe: ProcessProbe | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.run_id = run_id
        self.doc_type = doc_type
        self.process_probe = process_probe or ProcessProbe()
        self._lock = threading.RLock()
        self.run_dir = self.root_dir / "runs" / self.run_id / self.doc_type
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.run_dir / "run_manifest.json"
        self.heartbeat_path = self.run_dir / "heartbeat.json"
        self.stages_dir = self.run_dir / "stages"
        self.stages_dir.mkdir(parents=True, exist_ok=True)
        self.sequence = 0
        self._init_or_load_manifest()

    def _init_or_load_manifest(self) -> None:
        pid = os.getpid()
        process = self.process_probe.get_process_info(pid)
        start_time = process.start_time if process else 0.0
        command_digest = (
            compute_command_digest(process.command)
            if process
            else compute_command_digest(sys.argv)
        )
        if self.manifest_path.exists():
            try:
                self.manifest = RunManifest.model_validate_json(
                    self.manifest_path.read_text(encoding="utf-8")
                )
                self.sequence = self.manifest.sequence
                return
            except (OSError, ValueError):
                pass
        self.manifest = RunManifest(
            run_id=self.run_id,
            doc_type=self.doc_type,
            pid=pid,
            process_start_time=start_time,
            command_digest=command_digest,
        )
        self._save_manifest()

    def _save_manifest(self) -> None:
        with self._lock:
            self.manifest.updated_at = datetime.now(timezone.utc).isoformat()
            atomic_write_json(self.manifest_path, self.manifest)

    def heartbeat(
        self,
        stage: str,
        item: str,
        completed: int,
        expected: int,
        attempt: int | None = None,
    ) -> None:
        """Record an atomic, monotonic heartbeat."""
        with self._lock:
            self.sequence += 1
            self.manifest.sequence = self.sequence
            self.manifest.stage = stage
            now = datetime.now(timezone.utc).isoformat()
            self.manifest.heartbeat_at = now
            heartbeat = {
                "run_id": self.run_id,
                "doc_type": self.doc_type,
                "stage": stage,
                "item": item,
                "completed": completed,
                "expected": expected,
                "sequence": self.sequence,
                "timestamp": now,
                "pid": self.manifest.pid,
                "process_start_time": self.manifest.process_start_time,
            }
            if attempt is not None:
                heartbeat["attempt"] = attempt
            atomic_write_json(self.heartbeat_path, heartbeat)
            self._save_manifest()

    @contextmanager
    def periodic_heartbeat(
        self,
        *,
        stage: str,
        item: str,
        completed: int,
        expected: int,
        attempt: int,
        interval_seconds: float,
    ) -> Iterator[None]:
        """Keep an atomic heartbeat advancing while a blocking model call runs."""
        if (
            not math.isfinite(interval_seconds)
            or interval_seconds <= 0
            or attempt <= 0
        ):
            raise ValueError(
                "Heartbeat interval and attempt must be finite and positive"
            )
        stopped = threading.Event()
        failures: list[BaseException] = []

        def pump() -> None:
            while not stopped.wait(interval_seconds):
                try:
                    self.heartbeat(
                        stage=stage,
                        item=item,
                        completed=completed,
                        expected=expected,
                        attempt=attempt,
                    )
                except BaseException as error:
                    failures.append(error)
                    stopped.set()

        try:
            self.heartbeat(
                stage=stage,
                item=item,
                completed=completed,
                expected=expected,
                attempt=attempt,
            )
        except BaseException as error:
            raise AgentLifecycleError(
                "Initial heartbeat persistence failed"
            ) from error
        thread = threading.Thread(
            target=pump,
            name=f"heartbeat-{self.run_id}-{self.doc_type}",
            daemon=True,
        )
        thread.start()

        def heartbeat_failure() -> BaseException | None:
            return failures[0] if failures else None

        try:
            with bind_lifecycle_failure_probe(heartbeat_failure):
                yield
        finally:
            primary_error = sys.exception()
            stopped.set()
            thread.join()
            if failures:
                lifecycle_error = AgentLifecycleError(
                    "Periodic heartbeat persistence failed"
                )
                if primary_error is not None:
                    lifecycle_error.add_note(
                        "The model/runtime failure was superseded by heartbeat "
                        "persistence failure."
                    )
                    raise lifecycle_error from primary_error
                raise lifecycle_error from failures[0]

    def transition_stage(
        self,
        stage: str,
        status: Literal[
            "pending",
            "in_progress",
            "completed",
            "failed",
            "stalled",
            "cancelled",
        ] = "in_progress",
    ) -> None:
        """Transition the pipeline stage and status."""
        current_status = self.manifest.status
        if (
            current_status in ("completed", "failed", "stalled", "cancelled")
            and status != current_status
        ):
            raise ValueError(
                f"Invalid status transition from {current_status} to {status}"
            )
        self.manifest.stage = stage
        self.manifest.status = status
        self._save_manifest()

    def complete_stage(
        self,
        stage_name: str,
        input_hash: str,
        output_hash: str,
        provenance: AgentProvenance | dict[str, Any] | None = None,
    ) -> None:
        """Record stage completion and exact input/output hashes."""
        stage_manifest = StageManifest(
            stage=stage_name,
            status="completed",
            input_hash=input_hash,
            output_hash=output_hash,
            completed_at=datetime.now(timezone.utc).isoformat(),
            provenance=provenance,
        )
        stage_file = self.stages_dir / (
            f"{stage_name.replace(':', '_')}.json"
        )
        atomic_write_json(stage_file, stage_manifest)
        self.manifest.input_hashes[stage_name] = input_hash
        self.manifest.output_hashes[stage_name] = output_hash
        self._save_manifest()

    def can_reuse(self, stage_name: str, input_hash: str) -> bool:
        """Check for a completed stage with the exact input hash."""
        stage_file = self.stages_dir / (
            f"{stage_name.replace(':', '_')}.json"
        )
        if not stage_file.exists():
            return False
        try:
            stage_manifest = StageManifest.model_validate_json(
                stage_file.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return False
        return (
            stage_manifest.status == "completed"
            and stage_manifest.input_hash == input_hash
        )

    def add_descendant_pid(self, pid: int) -> None:
        """Register a descendant's complete, currently verified identity."""
        process = self.process_probe.get_process_info(pid)
        if process is None or not self.process_probe.is_running(pid):
            raise DescendantOwnershipError(
                f"Cannot register missing descendant PID {pid}"
            )
        identity = ProcessIdentity(
            pid=process.pid,
            process_start_time=process.start_time,
            command_digest=compute_command_digest(process.command),
            run_id=self.run_id,
        )
        if not _matches_process_identity(identity, process):
            raise DescendantOwnershipError(
                f"Descendant PID {pid} is not owned by run {self.run_id}"
            )
        with self._lock:
            self.manifest.descendant_pids = [
                descendant
                for descendant in self.manifest.descendant_pids
                if descendant.pid != pid
            ]
            self.manifest.descendant_pids.append(identity)
            self._save_manifest()

    def reload_manifest(self) -> RunManifest:
        """Reload the durable manifest before making a lifecycle decision."""
        with self._lock:
            self.manifest = RunManifest.model_validate_json(
                self.manifest_path.read_text(encoding="utf-8")
            )
            self.sequence = self.manifest.sequence
            return self.manifest

    def verified_descendants(self) -> list[ProcessIdentity]:
        """Return only descendants whose complete run-owned identity still matches."""
        self.reload_manifest()
        return [
            identity
            for identity in self.manifest.descendant_pids
            if _verified_process(identity, self.process_probe) is not None
        ]

    def terminate_verified_processes(
        self,
        *,
        include_owner: bool,
        grace_period_seconds: float,
        kill_wait_seconds: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> CleanupResult:
        """Signal owned identities and prove absence after a bounded kill wait."""
        effective_kill_wait = (
            grace_period_seconds
            if kill_wait_seconds is None
            else kill_wait_seconds
        )
        if (
            not math.isfinite(grace_period_seconds)
            or grace_period_seconds < 0
            or not math.isfinite(effective_kill_wait)
            or effective_kill_wait < 0
        ):
            raise ValueError("Wait periods must be finite and non-negative")
        self.reload_manifest()
        result = CleanupResult(scanned_manifests=[str(self.manifest_path)])
        identities = list(self.manifest.descendant_pids)
        if include_owner:
            identities.insert(0, _manifest_owner(self.manifest))

        signaled: list[ProcessIdentity] = []
        for identity in identities:
            if _verified_process(identity, self.process_probe) is None:
                continue
            if self.process_probe.terminate_process(identity.pid, signal.SIGTERM):
                signaled.append(identity)
                result.terminated_pids.append(identity.pid)
        if signaled:
            sleep(grace_period_seconds)
        for identity in signaled:
            if _verified_process(identity, self.process_probe) is None:
                continue
            if self.process_probe.terminate_process(identity.pid, signal.SIGKILL):
                result.killed_pids.append(identity.pid)
        if result.killed_pids:
            sleep(effective_kill_wait)

        self.reload_manifest()
        remaining = [
            identity
            for identity in self.manifest.descendant_pids
            if _verified_process(identity, self.process_probe) is not None
        ]
        result.remaining_pids = sorted(identity.pid for identity in remaining)
        if remaining:
            result.errors.append(
                "Verified processes survived SIGKILL bounded wait: "
                + ", ".join(str(identity.pid) for identity in remaining)
            )
        if remaining != self.manifest.descendant_pids:
            self.manifest.descendant_pids = remaining
            self._save_manifest()
        return result

    def wait_for_verified_descendants(
        self,
        timeout_seconds: float,
        poll_interval_seconds: float = 0.1,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Wait for run-owned descendants, raising rather than timing out open."""
        if (
            not math.isfinite(timeout_seconds)
            or timeout_seconds < 0
            or not math.isfinite(poll_interval_seconds)
            or poll_interval_seconds <= 0
        ):
            raise ValueError("Wait durations must be finite and non-negative")
        deadline = monotonic() + timeout_seconds
        while True:
            still_owned: list[ProcessIdentity] = []
            for identity in self.manifest.descendant_pids:
                process = self.process_probe.get_process_info(identity.pid)
                if process is None:
                    if self.process_probe.is_running(identity.pid):
                        still_owned.append(identity)
                    continue
                if _matches_process_identity(identity, process):
                    still_owned.append(identity)

            if still_owned != self.manifest.descendant_pids:
                self.manifest.descendant_pids = still_owned
                self._save_manifest()
            if not still_owned:
                return

            now = monotonic()
            if now >= deadline:
                pids = ", ".join(str(identity.pid) for identity in still_owned)
                raise DescendantExitTimeoutError(
                    f"Verified descendants still running at timeout: {pids}"
                )
            sleep(min(poll_interval_seconds, deadline - now))


def heartbeat_is_stale(
    manifest: RunManifest,
    stale_threshold_seconds: float = 300.0,
    now: datetime | None = None,
) -> bool:
    """Check whether a manifest heartbeat exceeded its stale threshold."""
    current_time = now or datetime.now(timezone.utc)
    try:
        heartbeat_time = datetime.fromisoformat(manifest.heartbeat_at)
        if heartbeat_time.tzinfo is None:
            heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)
        return (
            current_time - heartbeat_time
        ).total_seconds() > stale_threshold_seconds
    except (ValueError, TypeError):
        return True


def _manifest_owner(manifest: RunManifest) -> ProcessIdentity:
    return ProcessIdentity(
        pid=manifest.pid,
        process_start_time=manifest.process_start_time,
        command_digest=manifest.command_digest,
        run_id=manifest.run_id,
    )


def _verified_process(
    identity: ProcessIdentity,
    probe: ProcessProbe,
) -> ProcessInfo | None:
    process = probe.get_process_info(identity.pid)
    if process is None or not probe.is_running(identity.pid):
        return None
    if not _matches_process_identity(identity, process):
        return None
    return process


def _cleanup_stale_lease(
    root_dir: Path,
    lease_path: Path,
    probe: ProcessProbe,
    result: CleanupResult,
    dry_run: bool,
) -> None:
    if not lease_path.exists():
        return
    with _lease_guard(lease_path):
        if not lease_path.exists():
            return
        try:
            holder = _read_lease(lease_path)
            holder_active = _lease_holder_is_active(holder, probe)
        except (OSError, ValueError, ActiveRunError) as error:
            result.errors.append(f"Lease cleanup skipped: {error}")
            result.lease_retained_reason = "unverifiable_lease"
            return
        if holder_active:
            result.lease_retained_reason = "active_owner"
            return
        if dry_run:
            result.lease_retained_reason = "dry_run"
            return
        _, remaining, errors = _scan_bound_processes(
            root_dir,
            holder,
            probe,
        )
        if errors:
            result.errors.extend(errors)
            result.lease_retained_reason = "bound_manifest_unverifiable"
            return
        if remaining:
            result.remaining_pids = sorted(
                set(result.remaining_pids).union(
                    identity.pid for identity in remaining
                )
            )
            result.lease_retained_reason = "verified_processes_remain"
            return
        lease_path.unlink()
        _fsync_directory(lease_path.parent)
        result.lease_released = True


def cleanup_stalled_runs(
    root_dir: Path,
    stale_threshold_seconds: float = 300.0,
    process_probe: ProcessProbe | None = None,
    dry_run: bool = False,
    grace_period_seconds: float = 5.0,
    kill_wait_seconds: float | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> CleanupResult:
    """Terminate only stale processes whose complete identity still matches."""
    effective_kill_wait = (
        grace_period_seconds if kill_wait_seconds is None else kill_wait_seconds
    )
    if (
        not math.isfinite(grace_period_seconds)
        or grace_period_seconds < 0
        or not math.isfinite(effective_kill_wait)
        or effective_kill_wait < 0
    ):
        raise ValueError("Wait periods must be finite and non-negative")

    root_dir = Path(root_dir)
    probe = process_probe or ProcessProbe()
    result = CleanupResult()
    if not root_dir.exists():
        return result

    for manifest_file in root_dir.glob("runs/*/*/run_manifest.json"):
        result.scanned_manifests.append(str(manifest_file))
        try:
            manifest = RunManifest.model_validate_json(
                manifest_file.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            result.errors.append(
                f"Failed to read manifest {manifest_file}: {error}"
            )
            continue
        owner = _manifest_owner(manifest)
        owner_is_verified = _verified_process(owner, probe) is not None
        completed_descendants = [
            identity
            for identity in manifest.descendant_pids
            if _verified_process(identity, probe) is not None
        ]
        if manifest.status == "completed" and not completed_descendants:
            continue
        if not (
            completed_descendants
            or
            heartbeat_is_stale(manifest, stale_threshold_seconds)
            or not owner_is_verified
        ):
            continue
        result.stale_manifests.append(str(manifest_file))

        identities = (
            completed_descendants
            if manifest.status == "completed"
            else [owner, *manifest.descendant_pids]
        )
        verified_targets: list[ProcessIdentity] = []
        for identity in identities:
            process = probe.get_process_info(identity.pid)
            if process is None:
                if probe.is_running(identity.pid):
                    result.errors.append(
                        f"PID {identity.pid} skipped cleanup: "
                        "process identity is unavailable"
                    )
                continue
            if not _matches_process_identity(identity, process):
                result.errors.append(
                    f"PID {identity.pid} skipped cleanup: "
                    "failed ownership verification"
                )
                continue
            verified_targets.append(identity)

        signaled_targets: list[ProcessIdentity] = []
        if not dry_run:
            for identity in verified_targets:
                if _verified_process(identity, probe) is None:
                    continue
                if probe.terminate_process(identity.pid, signal.SIGTERM):
                    signaled_targets.append(identity)
                    result.terminated_pids.append(identity.pid)

            if signaled_targets:
                sleep(grace_period_seconds)

            for identity in signaled_targets:
                if _verified_process(identity, probe) is None:
                    continue
                if probe.terminate_process(identity.pid, signal.SIGKILL):
                    result.killed_pids.append(identity.pid)

            if any(
                identity.pid in result.killed_pids
                for identity in signaled_targets
            ):
                sleep(effective_kill_wait)

            remaining_targets = [
                identity
                for identity in verified_targets
                if _verified_process(identity, probe) is not None
            ]
            if remaining_targets:
                result.remaining_pids = sorted(
                    set(result.remaining_pids).union(
                        identity.pid for identity in remaining_targets
                    )
                )
                result.errors.append(
                    "Verified processes survived SIGKILL bounded wait: "
                    + ", ".join(
                        str(identity.pid) for identity in remaining_targets
                    )
                )
            if manifest.status != "completed":
                manifest.status = "stalled"
            atomic_write_json(manifest_file, manifest)
            if not remaining_targets:
                result.quarantined_paths.append(str(manifest_file.parent))

    for registry_path in root_dir.glob(
        "runs/*/supervisor_process_registry.json"
    ):
        parent_run_id = registry_path.parent.name
        result.scanned_registries.append(
            _registry_label(root_dir, registry_path)
        )
        try:
            registry = SupervisorProcessRegistry(
                root_dir,
                parent_run_id=parent_run_id,
                process_probe=probe,
            )
            records = registry.records()
        except (OSError, ValueError) as error:
            result.errors.append(
                "Failed to read parent process registry "
                f"{_registry_label(root_dir, registry_path)}: "
                f"{type(error).__name__}"
            )
            continue
        active_parent_owner = False
        lease_path = root_dir / "active_lease.json"
        if lease_path.is_file():
            try:
                lease_record = _read_lease(lease_path)
                active_parent_owner = (
                    lease_record.run_id == parent_run_id
                    and _lease_holder_is_active(lease_record, probe)
                )
            except (OSError, ValueError, ActiveRunError):
                active_parent_owner = False
        for record in records:
            if not record.identity_verified:
                if record.status == "reaped":
                    continue
                if probe.is_running(record.pid):
                    result.remaining_pids = sorted(
                        set(result.remaining_pids).union({record.pid})
                    )
                    result.errors.append(
                        f"Unverified registry spawn PID {record.pid} "
                        "requires cleanup through its owning process handle"
                    )
                    if not dry_run:
                        registry.mark_unverified_requires_cleanup(
                            record.pid,
                            run_id=record.run_id,
                            doc_type=record.doc_type,
                            exit_code=record.exit_code,
                        )
                elif not dry_run:
                    registry.mark_unverified_reaped(
                        record.pid,
                        run_id=record.run_id,
                        doc_type=record.doc_type,
                        exit_code=record.exit_code,
                    )
                continue
            process = probe.get_process_info(record.pid)
            if process is None:
                if probe.is_running(record.pid):
                    result.errors.append(
                        f"Registry PID {record.pid} skipped cleanup: "
                        "process identity is unavailable"
                    )
                    try:
                        registry.mark_requires_cleanup(
                            record,
                            exit_code=record.exit_code,
                        )
                    except (OSError, ValueError, DescendantOwnershipError):
                        pass
                elif record.status != "reaped" and not dry_run:
                    registry.mark_reaped(
                        record,
                        exit_code=record.exit_code,
                    )
                continue
            if not _matches_process_identity(record, process):
                continue
            manifest_path = (
                root_dir
                / "runs"
                / record.run_id
                / record.doc_type
                / "run_manifest.json"
            )
            manifest_is_healthy = False
            if manifest_path.is_file():
                try:
                    manifest = RunManifest.model_validate_json(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    manifest_is_healthy = (
                        manifest.run_id == record.run_id
                        and manifest.doc_type == record.doc_type
                        and _manifest_owner(manifest) == ProcessIdentity(
                            pid=record.pid,
                            process_start_time=record.process_start_time,
                            command_digest=record.command_digest,
                            run_id=record.run_id,
                        )
                        and manifest.status in {"pending", "in_progress"}
                        and not heartbeat_is_stale(
                            manifest,
                            stale_threshold_seconds,
                        )
                    )
                except (OSError, ValueError):
                    manifest_is_healthy = False
            try:
                registry_updated = datetime.fromisoformat(record.updated_at)
                if registry_updated.tzinfo is None:
                    registry_updated = registry_updated.replace(
                        tzinfo=timezone.utc
                    )
                registry_is_fresh = (
                    datetime.now(timezone.utc) - registry_updated
                ).total_seconds() <= stale_threshold_seconds
            except (TypeError, ValueError):
                registry_is_fresh = False
            if (
                record.status == "running"
                and active_parent_owner
                and (manifest_is_healthy or registry_is_fresh)
            ):
                continue
            if dry_run:
                result.remaining_pids = sorted(
                    set(result.remaining_pids).union({record.pid})
                )
                continue
            if probe.terminate_process(record.pid, signal.SIGTERM):
                result.terminated_pids.append(record.pid)
            sleep(grace_period_seconds)
            if _verified_process(record, probe) is not None:
                if probe.terminate_process(record.pid, signal.SIGKILL):
                    result.killed_pids.append(record.pid)
                sleep(effective_kill_wait)
            if _verified_process(record, probe) is not None:
                result.remaining_pids = sorted(
                    set(result.remaining_pids).union({record.pid})
                )
                result.errors.append(
                    f"Verified registry process {record.pid} survived cleanup"
                )
                registry.mark_requires_cleanup(
                    record,
                    exit_code=record.exit_code,
                )
            else:
                registry.mark_reaped(
                    record,
                    exit_code=record.exit_code,
                )

    _cleanup_stale_lease(
        root_dir,
        root_dir / "active_lease.json",
        probe,
        result,
        dry_run,
    )
    return result
