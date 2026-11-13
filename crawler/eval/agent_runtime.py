from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime
import contextvars
import hashlib
import json
import math
import re
import threading
from collections.abc import Mapping
from typing import Any, Callable, Literal, Sequence


class AgentRuntimeError(Exception):
    """Base exception for agent runtime errors."""
    pass


class TransientAgentError(AgentRuntimeError):
    """Raised when a transient error occurs during agent execution."""
    pass


class AgentTimeoutError(TransientAgentError):
    """Raised when an agent request times out."""
    pass


class AgentLifecycleError(AgentRuntimeError):
    """Raised when SDK process/client lifecycle ownership cannot be proven."""


class ResponseValidationError(Exception):
    """Deterministic model-response validation failure after SDK execution."""


_LIFECYCLE_FAILURE_PROBE: contextvars.ContextVar[
    Callable[[], BaseException | None] | None
] = contextvars.ContextVar("phase74_lifecycle_failure_probe", default=None)


@contextmanager
def bind_lifecycle_failure_probe(
    probe: Callable[[], BaseException | None],
):
    """Expose a parent persistence failure to the active model runtime."""
    binding = _LIFECYCLE_FAILURE_PROBE.set(probe)
    try:
        yield
    finally:
        _LIFECYCLE_FAILURE_PROBE.reset(binding)


def current_lifecycle_failure_probe() -> Callable[[], BaseException | None] | None:
    """Return the failure probe bound by the current pipeline heartbeat scope."""
    return _LIFECYCLE_FAILURE_PROBE.get()


@dataclass(frozen=True)
class BlobAttachment:
    data: bytes
    mime_type: str
    display_name: str


@dataclass(frozen=True)
class AgentRequest:
    role: Literal["worker", "judge", "optimizer", "orchestrator"]
    model: str
    context_tier: Literal["default", "long_context"]
    prompt: str
    attachments: Sequence[BlobAttachment]
    timeout_seconds: float
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] | None = None
    response_validation_policy: "ResponseValidationPolicy | None" = None


@dataclass(frozen=True)
class ResponseValidationIssue:
    """Sanitized validation categories safe to include in a correction turn."""

    codes: tuple[str, ...]


@dataclass(frozen=True)
class ResponseValidationPolicy:
    """Typed same-session structural response correction policy."""

    correction_kind: Literal[
        "worker_structure",
        "worker_validation",
        "judge_structure",
    ]
    validate: Callable[[str], ResponseValidationIssue | None]
    build_correction_prompt: Callable[[ResponseValidationIssue], str]


@dataclass(frozen=True)
class AgentProvenance:
    engine: str
    sdk_version: str
    runtime_protocol_version: str
    role: str
    model: str
    effort: str | None
    context_tier: str
    session_id: str
    prompt_hash: str
    attachment_hashes: Sequence[str]
    output_hash: str
    started_at: str
    completed_at: str
    duration_seconds: float
    terminal_event: str
    is_live: bool
    retry_classification: str | None = None
    turn_count: int = 1
    format_correction_count: int = 0
    initial_prompt_hash: str | None = None
    correction_prompt_hashes: Sequence[str] = ()
    assistant_response_hash_chain: Sequence[str] = ()
    turn_session_ids: Sequence[str] = ()
    correction_kind: Literal[
        "syntax",
        "worker_structure",
        "worker_validation",
        "judge_structure",
    ] | None = None

    def __post_init__(self) -> None:
        """Populate canonical one-turn defaults for injected/test runtimes."""
        if self.initial_prompt_hash is None:
            object.__setattr__(self, "initial_prompt_hash", self.prompt_hash)
        if not self.assistant_response_hash_chain:
            object.__setattr__(
                self,
                "assistant_response_hash_chain",
                (self.output_hash,),
            )
        if not self.turn_session_ids:
            object.__setattr__(
                self,
                "turn_session_ids",
                (self.session_id,),
            )


# ``correction_kind`` is conditionally canonical: legacy/current one-turn
# artifacts omit it, preserving exact Worker reuse across Judge-only changes.
AGENT_PROVENANCE_FIELDS = tuple(
    field.name
    for field in fields(AgentProvenance)
    if field.name != "correction_kind"
)
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_PLACEHOLDER_IDENTITIES = {
    "",
    "default",
    "injected-runner",
    "injected-test-runner",
    "none",
    "null",
    "placeholder",
    "test",
    "test-runner",
    "unknown",
}


@dataclass(frozen=True)
class AgentResult:
    content: str
    provenance: AgentProvenance


class AgentRuntime(ABC):
    """Abstract interface for agent execution runtimes."""

    @abstractmethod
    async def run(self, request: AgentRequest) -> AgentResult:
        """Execute an agent request and return the result."""
        pass


def canonical_provenance_digest(
    provenance: Mapping[str, Any],
    *,
    extra_fields: Sequence[str] = (),
) -> str:
    """Hash the canonical runtime provenance fields plus role-specific bindings."""
    correction_fields = (
        ("correction_kind",)
        if provenance.get("format_correction_count") == 1
        else ()
    )
    bound_fields = tuple(
        dict.fromkeys(
            (*AGENT_PROVENANCE_FIELDS, *correction_fields, *extra_fields)
        )
    )
    payload = {field: provenance.get(field) for field in bound_fields}
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AgentRuntimeError(f"Agent provenance {field} is not an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgentRuntimeError(
            f"Agent provenance {field} is not an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AgentRuntimeError(
            f"Agent provenance {field} must include a UTC offset"
        )
    return parsed


def _validate_identity_field(value: Any, field: str, *, live: bool) -> None:
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise AgentRuntimeError(f"Agent provenance {field} is invalid")
    if live and value.lower() in _PLACEHOLDER_IDENTITIES:
        raise AgentRuntimeError(f"Live agent provenance {field} is a placeholder")


def _validate_session_id(value: Any, *, live: bool) -> None:
    if not isinstance(value, str) or not _SESSION_ID_RE.fullmatch(value):
        raise AgentRuntimeError("Agent provenance session_id is invalid")
    lowered = value.lower()
    if lowered in {
        "",
        "default",
        "none",
        "null",
        "placeholder",
        "test",
        "test-runner",
        "unknown",
    }:
        raise AgentRuntimeError("Agent provenance session_id is a placeholder")
    if live and (
        lowered in _PLACEHOLDER_IDENTITIES
        or lowered.startswith("injected")
        or lowered.startswith("placeholder")
    ):
        raise AgentRuntimeError("Live agent provenance session_id is a placeholder")


def _validate_complete_runtime_provenance(
    provenance: Mapping[str, Any],
    *,
    expected_engine: str,
    expected_is_live: bool,
    role: str,
    model: str,
    effort: str | None,
    context_tier: str,
    prompt_hash: str,
    attachment_hashes: Sequence[str],
    output_hash: str,
) -> None:
    if (
        not isinstance(attachment_hashes, Sequence)
        or isinstance(attachment_hashes, (str, bytes))
    ):
        raise AgentRuntimeError(
            "Expected attachment_hashes must be a sequence"
        )
    actual_attachment_hashes = provenance.get("attachment_hashes")
    if not isinstance(actual_attachment_hashes, (list, tuple)):
        raise AgentRuntimeError(
            "Agent provenance attachment_hashes must be an ordered sequence"
        )
    expected = {
        "engine": expected_engine,
        "is_live": expected_is_live,
        "role": role,
        "model": model,
        "effort": effort,
        "context_tier": context_tier,
        "prompt_hash": prompt_hash,
        "attachment_hashes": list(attachment_hashes),
        "output_hash": output_hash,
        "terminal_event": "assistant.message",
        "retry_classification": None,
    }
    for field, expected_value in expected.items():
        actual_value = provenance.get(field)
        if actual_value != expected_value:
            raise AgentRuntimeError(
                f"Agent runtime provenance {field} mismatch: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )
    for field in ("prompt_hash", "output_hash"):
        value = provenance.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise AgentRuntimeError(f"Agent provenance {field} is not SHA-256")
    initial_prompt_hash = provenance.get("initial_prompt_hash")
    if (
        not isinstance(initial_prompt_hash, str)
        or not _SHA256_RE.fullmatch(initial_prompt_hash)
        or initial_prompt_hash != prompt_hash
        or initial_prompt_hash != provenance.get("prompt_hash")
    ):
        raise AgentRuntimeError(
            "Agent provenance initial_prompt_hash does not bind the request"
        )
    if any(
        not isinstance(value, str) or not _SHA256_RE.fullmatch(value)
        for value in actual_attachment_hashes
    ):
        raise AgentRuntimeError(
            "Agent provenance attachment_hashes contains a non-SHA-256 value"
        )

    _validate_identity_field(
        provenance.get("sdk_version"),
        "sdk_version",
        live=expected_is_live,
    )
    _validate_identity_field(
        provenance.get("runtime_protocol_version"),
        "runtime_protocol_version",
        live=expected_is_live,
    )
    _validate_session_id(
        provenance.get("session_id"),
        live=expected_is_live,
    )
    turn_count = provenance.get("turn_count")
    correction_count = provenance.get("format_correction_count")
    if (
        not isinstance(turn_count, int)
        or isinstance(turn_count, bool)
        or turn_count not in (1, 2)
        or not isinstance(correction_count, int)
        or isinstance(correction_count, bool)
        or correction_count not in (0, 1)
        or turn_count != correction_count + 1
    ):
        raise AgentRuntimeError(
            "Agent provenance turn/format-correction counts are invalid"
        )
    correction_kind = provenance.get("correction_kind")
    if (
        correction_count == 0
        and correction_kind is not None
    ) or (
        correction_count == 1
        and correction_kind
        not in {
            "syntax",
            "worker_structure",
            "worker_validation",
            "judge_structure",
        }
    ):
        raise AgentRuntimeError(
            "Agent provenance correction kind/count binding is invalid"
        )
    correction_hashes = provenance.get("correction_prompt_hashes")
    if (
        not isinstance(correction_hashes, (list, tuple))
        or len(correction_hashes) != correction_count
        or any(
            not isinstance(value, str) or not _SHA256_RE.fullmatch(value)
            for value in correction_hashes
        )
    ):
        raise AgentRuntimeError(
            "Agent provenance correction_prompt_hashes are invalid"
        )
    response_hash_chain = provenance.get("assistant_response_hash_chain")
    if (
        not isinstance(response_hash_chain, (list, tuple))
        or len(response_hash_chain) != turn_count
        or any(
            not isinstance(value, str) or not _SHA256_RE.fullmatch(value)
            for value in response_hash_chain
        )
        or response_hash_chain[-1] != output_hash
        or response_hash_chain[-1] != provenance.get("output_hash")
    ):
        raise AgentRuntimeError(
            "Agent provenance assistant response hash chain is invalid"
        )
    turn_session_ids = provenance.get("turn_session_ids")
    if (
        not isinstance(turn_session_ids, (list, tuple))
        or len(turn_session_ids) != turn_count
        or any(value != provenance.get("session_id") for value in turn_session_ids)
    ):
        raise AgentRuntimeError(
            "Agent provenance does not bind every turn to the same session"
        )
    started_at = _parse_timestamp(provenance.get("started_at"), "started_at")
    completed_at = _parse_timestamp(
        provenance.get("completed_at"), "completed_at"
    )
    if completed_at < started_at:
        raise AgentRuntimeError(
            "Agent provenance completed_at precedes started_at"
        )
    duration = provenance.get("duration_seconds")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not math.isfinite(float(duration))
        or duration < 0
    ):
        raise AgentRuntimeError(
            "Agent provenance duration_seconds must be finite and nonnegative"
        )


def validate_persisted_agent_provenance(
    provenance: Any,
    *,
    expected_engine: str,
    expected_is_live: bool,
    role: str,
    model: str,
    effort: str | None,
    context_tier: str,
    prompt_hash: str,
    attachment_hashes: Sequence[str],
    output_hash: str,
    extra_digest_fields: Sequence[str] = (),
    required_hash_fields: Sequence[str] = (),
    optional_hash_fields: Sequence[str] = (),
    required_hash_list_fields: Sequence[str] = (),
    reject_unexpected_fields: bool = True,
) -> None:
    """Validate complete persisted runtime proof and its canonical digest."""
    if not isinstance(provenance, Mapping):
        raise AgentRuntimeError("Persisted agent provenance is not an object")
    missing = [
        field
        for field in (*AGENT_PROVENANCE_FIELDS, "provenance_digest")
        if field not in provenance
    ]
    missing.extend(
        field for field in extra_digest_fields if field not in provenance
    )
    if provenance.get("format_correction_count") == 1 and (
        "correction_kind" not in provenance
    ):
        missing.append("correction_kind")
    if missing:
        raise AgentRuntimeError(
            f"Persisted agent provenance is incomplete: {sorted(set(missing))}"
        )
    expected_fields = {
        *AGENT_PROVENANCE_FIELDS,
        *extra_digest_fields,
        "correction_kind",
        "provenance_digest",
    }
    unexpected_fields = set(provenance) - expected_fields
    if reject_unexpected_fields and unexpected_fields:
        raise AgentRuntimeError(
            "Persisted agent provenance contains unexpected fields: "
            f"{sorted(unexpected_fields)}"
        )
    _validate_complete_runtime_provenance(
        provenance,
        expected_engine=expected_engine,
        expected_is_live=expected_is_live,
        role=role,
        model=model,
        effort=effort,
        context_tier=context_tier,
        prompt_hash=prompt_hash,
        attachment_hashes=attachment_hashes,
        output_hash=output_hash,
    )
    for field in required_hash_fields:
        value = provenance.get(field)
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise AgentRuntimeError(
                f"Persisted agent provenance {field} is not SHA-256"
            )
    for field in optional_hash_fields:
        value = provenance.get(field)
        if value is not None and (
            not isinstance(value, str) or not _SHA256_RE.fullmatch(value)
        ):
            raise AgentRuntimeError(
                f"Persisted agent provenance {field} is not null or SHA-256"
            )
    for field in required_hash_list_fields:
        value = provenance.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not _SHA256_RE.fullmatch(item)
            for item in value
        ):
            raise AgentRuntimeError(
                f"Persisted agent provenance {field} is not a SHA-256 list"
            )
    expected_digest = canonical_provenance_digest(
        provenance,
        extra_fields=extra_digest_fields,
    )
    if provenance.get("provenance_digest") != expected_digest:
        raise AgentRuntimeError(
            "Persisted agent provenance digest does not match canonical fields"
        )


def validate_agent_result(
    result: AgentResult,
    request: AgentRequest,
    *,
    expected_engine: str = "copilot-sdk",
    expected_is_live: bool = True,
) -> AgentProvenance:
    """Fail closed unless runtime provenance exactly binds the request and response."""
    if not isinstance(result, AgentResult):
        raise AgentRuntimeError("Agent runtime returned an invalid result object")
    if not isinstance(result.content, str) or not result.content:
        raise AgentRuntimeError("Agent runtime returned invalid response content")
    provenance = result.provenance
    if not isinstance(provenance, AgentProvenance):
        raise AgentRuntimeError("Agent runtime returned invalid provenance")

    runtime_provenance = {
        field: getattr(provenance, field)
        for field in AGENT_PROVENANCE_FIELDS
    }
    if provenance.correction_kind is not None:
        runtime_provenance["correction_kind"] = provenance.correction_kind
    _validate_complete_runtime_provenance(
        runtime_provenance,
        expected_engine=expected_engine,
        expected_is_live=expected_is_live,
        role=request.role,
        model=request.model,
        effort=request.reasoning_effort,
        context_tier=request.context_tier,
        prompt_hash=hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
        attachment_hashes=[
            hashlib.sha256(attachment.data).hexdigest()
            for attachment in request.attachments
        ],
        output_hash=hashlib.sha256(result.content.encode("utf-8")).hexdigest(),
    )
    return provenance


def run_async(coro, *, async_api_name: str = "the async API"):
    """Run a coroutine only when no event loop is already active."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        close = getattr(coro, "close", None)
        if callable(close):
            close()
        raise RuntimeError(
            "Synchronous agent wrapper cannot run inside an active event loop; "
            f"await {async_api_name} instead."
        )

    completed = threading.Event()
    outcome: list[tuple[bool, Any]] = []
    caller_context = contextvars.copy_context()

    def run_owned_loop() -> None:
        event_loop = asyncio.new_event_loop()
        observed_tasks: set[asyncio.Task[Any]] = set()

        def consume(task: asyncio.Task[Any]) -> None:
            if task.cancelled():
                return
            try:
                task.exception()
            except BaseException:
                pass

        def stop_when_idle() -> None:
            pending = {
                task
                for task in asyncio.all_tasks(event_loop)
                if not task.done()
            }
            for task in pending - observed_tasks:
                observed_tasks.add(task)
                task.add_done_callback(consume)
            if not pending:
                event_loop.stop()
                return
            event_loop.call_later(0.01, stop_when_idle)

        def main_done(task: asyncio.Task[Any]) -> None:
            try:
                outcome.append((True, task.result()))
            except BaseException as error:
                outcome.append((False, error))
            finally:
                completed.set()
                event_loop.call_soon(stop_when_idle)

        try:
            asyncio.set_event_loop(event_loop)
            main_task = caller_context.run(event_loop.create_task, coro)
            main_task.add_done_callback(main_done)
            event_loop.run_forever()
        except BaseException as error:
            if not completed.is_set():
                outcome.append((False, error))
                completed.set()
        finally:
            asyncio.set_event_loop(None)
            event_loop.close()

    thread = threading.Thread(
        target=run_owned_loop,
        name="copilot-sdk-async-runner",
        daemon=True,
    )
    thread.start()
    completed.wait()
    succeeded, value = outcome[0]
    if succeeded:
        return value
    raise value
