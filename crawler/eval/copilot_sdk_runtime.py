import asyncio
import base64
import datetime
import hashlib
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import copilot
from copilot import CopilotClient
from copilot.session_events import AssistantMessageData

from crawler.eval.agent_runtime import (
    AgentLifecycleError,
    AgentProvenance,
    AgentRequest,
    AgentResult,
    AgentRuntime,
    AgentRuntimeError,
    AgentTimeoutError,
    ResponseValidationError,
    TransientAgentError,
    current_lifecycle_failure_probe,
    validate_agent_result,
)

_DEFAULT_STARTUP_TIMEOUT_SECONDS = 30.0
_DEFAULT_CLEANUP_TIMEOUT_SECONDS = 30.0
_PROCESS_INSPECTION_INTERVAL_SECONDS = 0.01

DEFAULT_ROLE_SYSTEM_MESSAGES = {
    "worker": "You are a blind PR review document verification worker. Output strict JSON matching the required schema.",
    "judge": "You are a privileged PR review judge evaluating document verification accuracy and completeness.",
    "optimizer": "You are a PR review prompt and skill optimizer proposing targeted improvements.",
    "orchestrator": "You are a PR review pipeline orchestrator.",
}

_FORMAT_CORRECTION_PROMPT = (
    "Return the same assessment again as exactly one raw JSON object. "
    "Do not add new evidence or change the assessment. The first character { "
    "and the last character } are mandatory. Do not use a Markdown fence, preface, "
    "explanation, or trailing prose."
)


def copilot_client_auth_kwargs() -> dict[str, Any]:
    """Forward an explicit host token without persisting it in SDK state."""
    token = os.environ.get("COPILOT_GITHUB_TOKEN")  # publish-safe: allow
    if not token:
        return {}
    return {
        "github_token": token,
        "use_logged_in_user": False,
    }

_NON_TRANSIENT_ERROR = re.compile(
    r"\b(?:401|403|authentication|unauthori[sz]ed|forbidden|permission(?: denied)?|"
    r"invalid (?:timeout|model|config(?:uration)?|request|schema|auth(?:entication|orization)?|permission)|"
    r"(?:timeout|model|config(?:uration)?|request|schema|auth(?:entication|orization)?|permission)(?: is)? invalid|"
    r"bad request|"
    r"validation error|unprocessable)\b",
    re.IGNORECASE,
)
_TRANSIENT_ERROR = re.compile(
    r"\b(?:429|rate limit(?:ed)?|5\d\d|provider unavailable|service unavailable|"
    r"temporarily unavailable|connection (?:reset|closed|refused|aborted|failed)|"
    r"connection (?:\w+\s+){1,3}failed|"
    r"(?:request |operation |connection |read |write )?(?:timed out|timeout)|"
    r"broken pipe|transport (?:error|failure)|network (?:error|failure)|"
    r"dns(?: (?:network )?(?:error|failure))?|socket (?:error|closed))\b",
    re.IGNORECASE,
)
_TRANSIENT_EXCEPTION_NAMES = {
    "connecterror",
    "connectionclosed",
    "connecttimeout",
    "gaierror",
    "networkerror",
    "pooltimeout",
    "proxyerror",
    "readerror",
    "readtimeout",
    "remoteprotocolerror",
    "transporterror",
    "writeerror",
    "writetimeout",
}


def _raise_classified_sdk_error(stage: str, exc: Exception) -> None:
    """Translate SDK failures without treating unknown or deterministic errors as retryable."""
    if isinstance(exc, AgentRuntimeError):
        raise exc
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        raise AgentTimeoutError(f"{stage} timed out: {exc}") from exc

    message = str(exc)
    status = getattr(exc, "status_code", getattr(exc, "status", None))
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    if status in (401, 403):
        raise AgentRuntimeError(f"{stage} failed: {exc}") from exc
    if status in (408, 429) or (
        isinstance(status, int) and 500 <= status <= 599
    ):
        raise TransientAgentError(f"{stage} failed: {exc}") from exc
    if isinstance(status, int) and 400 <= status <= 499:
        raise AgentRuntimeError(f"{stage} failed: {exc}") from exc

    if _NON_TRANSIENT_ERROR.search(message) or isinstance(exc, PermissionError):
        raise AgentRuntimeError(f"{stage} failed: {exc}") from exc
    recognized_transport_class = any(
        base.__name__.lower() in _TRANSIENT_EXCEPTION_NAMES
        for base in type(exc).__mro__
    )
    if isinstance(
        exc,
        (
            ConnectionError,
            ConnectionResetError,
            ConnectionAbortedError,
            ConnectionRefusedError,
            BrokenPipeError,
        ),
    ) or recognized_transport_class or _TRANSIENT_ERROR.search(message):
        raise TransientAgentError(f"{stage} failed: {exc}") from exc
    raise AgentRuntimeError(f"{stage} failed: {exc}") from exc


def _event_content(event: Any) -> tuple[str, str]:
    """Extract final assistant content without persisting raw SDK events."""
    raw_content: Any = None
    terminal_event = "none"
    if event is not None:
        data = getattr(event, "data", event)
        if isinstance(data, AssistantMessageData):
            raw_content = data.content
            terminal_event = "assistant.message"
        elif hasattr(data, "content"):
            raw_content = getattr(data, "content")
            terminal_event = getattr(event, "raw_type", "assistant.message")
        elif isinstance(data, dict):
            raw_content = data.get("content")
            terminal_event = event.get("type", "assistant.message")
        else:
            terminal_event = getattr(event, "raw_type", "unknown")
    if raw_content is None:
        return "", terminal_event
    if isinstance(raw_content, str):
        return raw_content, terminal_event
    try:
        return (
            json.dumps(
                raw_content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            terminal_event,
        )
    except (TypeError, ValueError):
        return str(raw_content), terminal_event


def _is_syntactically_json(content: str) -> bool:
    """Return true for any syntactically valid JSON value.

    Schema and semantic validation deliberately remain the caller's job.
    """
    try:
        json.loads(content.strip())
    except (json.JSONDecodeError, ValueError):
        return False
    return True


def _sdk_process_pid(client: Any) -> int | None:
    """Return the spawned SDK runtime PID from the pinned client contract."""
    for attribute in ("_process", "_cli_process"):
        process = getattr(client, attribute, None)
        pid = getattr(process, "pid", None)
        if isinstance(pid, int) and pid > 0:
            return pid
    return None


def _consume_task_exception(task: asyncio.Future[Any]) -> None:
    """Retrieve an abandoned task's eventual exception without awaiting it."""
    if task.cancelled():
        return
    try:
        task.exception()
    except BaseException:
        pass


def _cancel_without_waiting(task: asyncio.Future[Any]) -> None:
    if task.done():
        _consume_task_exception(task)
        return
    task.add_done_callback(_consume_task_exception)
    task.cancel()


async def _await_with_hard_deadline(
    awaitable: Any,
    *,
    timeout_seconds: float,
    operation: str,
) -> Any:
    """Await until a monotonic deadline without joining cancellation-resistant work."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("SDK lifecycle timeout must be finite and positive")
    task = asyncio.ensure_future(awaitable)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    try:
        done, _ = await asyncio.wait(
            {task},
            timeout=max(0.0, deadline - loop.time()),
        )
    except BaseException:
        _cancel_without_waiting(task)
        raise
    if task not in done:
        _cancel_without_waiting(task)
        raise asyncio.TimeoutError(
            f"{operation} timed out after {timeout_seconds}s"
        )
    return await task


async def start_client_bounded(
    client: Any,
    *,
    register_descendant: Callable[[int], None] | None,
    timeout_seconds: float,
    process_getter: Callable[[Any], int | None] = _sdk_process_pid,
) -> None:
    """Start a client while registering its process as soon as it is exposed."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("SDK startup timeout must be finite and positive")
    start_task = asyncio.create_task(client.start())
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    registered_pid: int | None = None

    def inspect_process() -> None:
        nonlocal registered_pid
        try:
            pid = process_getter(client)
        except Exception as exc:
            raise AgentLifecycleError(
                "SDK runtime process identity is unavailable during startup"
            ) from exc
        if pid is not None and (
            isinstance(pid, bool)
            or not isinstance(pid, int)
            or pid <= 0
        ):
            raise AgentLifecycleError(
                "SDK runtime process identity is invalid during startup"
            )
        if pid is None or pid == registered_pid:
            return
        if registered_pid is not None:
            raise AgentLifecycleError(
                "SDK runtime process identity changed during startup"
            )
        if register_descendant is not None:
            try:
                register_descendant(pid)
            except Exception as exc:
                raise AgentLifecycleError(
                    "SDK runtime process ownership registration failed"
                ) from exc
        registered_pid = pid

    try:
        while not start_task.done():
            inspect_process()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                _cancel_without_waiting(start_task)
                inspect_process()
                raise AgentTimeoutError(
                    f"SDK client start timed out after {timeout_seconds}s"
                )
            await asyncio.wait(
                {start_task},
                timeout=min(
                    _PROCESS_INSPECTION_INTERVAL_SECONDS,
                    remaining,
                ),
            )
        inspect_process()
        await start_task
        inspect_process()
        if register_descendant is not None and registered_pid is None:
            raise AgentLifecycleError(
                "SDK runtime process handle is unavailable after startup"
            )
    except BaseException:
        if not start_task.done():
            _cancel_without_waiting(start_task)
        inspect_process()
        raise


async def stop_client_bounded(
    client: Any,
    *,
    timeout_seconds: float,
) -> None:
    """Stop a client without permitting an unbounded cleanup await."""
    try:
        await _await_with_hard_deadline(
            client.stop(),
            timeout_seconds=timeout_seconds,
            operation="SDK client stop",
        )
    except (TimeoutError, asyncio.TimeoutError) as exc:
        raise AgentTimeoutError(
            f"SDK client stop timed out after {timeout_seconds}s"
        ) from exc
    except AgentRuntimeError:
        raise
    except Exception as exc:
        raise AgentLifecycleError("SDK client stop failed") from exc


class CopilotSdkRuntime(AgentRuntime):
    """Official GitHub Copilot SDK adapter implementing AgentRuntime interface."""

    def __init__(
        self,
        base_directory: str | Path,
        client_factory: Callable[..., Any] | None = None,
        role_system_messages: dict[str, str] | None = None,
        descendant_registrar: Callable[[int], None] | None = None,
        client_env: dict[str, str] | None = None,
        startup_timeout_seconds: float = _DEFAULT_STARTUP_TIMEOUT_SECONDS,
        cleanup_timeout_seconds: float = _DEFAULT_CLEANUP_TIMEOUT_SECONDS,
        process_getter: Callable[[Any], int | None] = _sdk_process_pid,
    ):
        self.base_directory = Path(base_directory)
        self.client_factory = client_factory or (
            lambda mode, base_directory: CopilotClient(
                mode=mode,
                base_directory=str(base_directory),
                env=client_env,
                **copilot_client_auth_kwargs(),
            )
        )
        self.role_system_messages = {
            **DEFAULT_ROLE_SYSTEM_MESSAGES,
            **(role_system_messages or {}),
        }
        self.descendant_registrar = descendant_registrar
        if (
            not math.isfinite(startup_timeout_seconds)
            or startup_timeout_seconds <= 0
            or not math.isfinite(cleanup_timeout_seconds)
            or cleanup_timeout_seconds <= 0
        ):
            raise ValueError("SDK lifecycle timeouts must be finite and positive")
        self.startup_timeout_seconds = float(startup_timeout_seconds)
        self.cleanup_timeout_seconds = float(cleanup_timeout_seconds)
        self.process_getter = process_getter

    async def run(self, request: AgentRequest) -> AgentResult:
        role_system_message = self.role_system_messages.get(
            request.role, f"You are a PR review {request.role} agent."
        )

        client = None
        session = None
        cleanup_errors: list[str] = []
        cleanup_failures: list[Exception] = []
        lifecycle_failure_probe = current_lifecycle_failure_probe()
        started_at_dt = datetime.datetime.now(datetime.timezone.utc)
        start_time = time.perf_counter()

        try:
            try:
                client = self.client_factory(mode="empty", base_directory=str(self.base_directory))
                await start_client_bounded(
                    client,
                    register_descendant=self.descendant_registrar,
                    timeout_seconds=self.startup_timeout_seconds,
                    process_getter=self.process_getter,
                )
            except AgentRuntimeError:
                raise
            except Exception as exc:
                _raise_classified_sdk_error("SDK client failed to start", exc)

            create_kwargs = {
                "model": request.model,
                "context_tier": request.context_tier,
                "available_tools": [],
                "working_directory": str(self.base_directory),
                "skip_custom_instructions": True,
                "enable_config_discovery": False,
                "enable_on_demand_instruction_discovery": False,
                "enable_file_hooks": False,
                "enable_host_git_operations": False,
                "enable_session_store": False,
                "enable_skills": False,
                "mcp_servers": {},
                "memory": {"enabled": False},
                "enable_session_telemetry": False,
                "system_message": {"mode": "replace", "content": role_system_message},
            }
            if request.reasoning_effort is not None:
                create_kwargs["reasoning_effort"] = request.reasoning_effort

            try:
                session = await client.create_session(**create_kwargs)
            except AgentRuntimeError:
                raise
            except Exception as exc:
                _raise_classified_sdk_error("SDK session creation failed", exc)

            converted_attachments = [
                {
                    "type": "blob",
                    "data": base64.b64encode(att.data).decode("utf-8"),
                    "mimeType": att.mime_type,
                    "displayName": att.display_name,
                }
                for att in request.attachments
            ]

            async def send_turn(
                prompt: str,
                *,
                attachments: list[dict[str, str]],
                stage: str,
            ) -> tuple[str, str]:
                try:
                    send_task = asyncio.create_task(
                        session.send_and_wait(
                            prompt,
                            attachments=attachments,
                            timeout=request.timeout_seconds,
                        )
                    )
                    while not send_task.done():
                        lifecycle_failure = (
                            lifecycle_failure_probe()
                            if lifecycle_failure_probe is not None
                            else None
                        )
                        if lifecycle_failure is not None:
                            _cancel_without_waiting(send_task)
                            try:
                                await _await_with_hard_deadline(
                                    session.abort(),
                                    timeout_seconds=self.cleanup_timeout_seconds,
                                    operation="SDK session abort",
                                )
                            except Exception as cleanup_error:
                                cleanup_errors.append(
                                    f"session.abort: {cleanup_error}"
                                )
                                cleanup_failures.append(cleanup_error)
                            raise AgentLifecycleError(
                                "Periodic heartbeat persistence failed during "
                                "the active model turn"
                            ) from lifecycle_failure
                        await asyncio.wait(
                            {send_task},
                            timeout=_PROCESS_INSPECTION_INTERVAL_SECONDS,
                        )
                    event = await send_task
                except asyncio.CancelledError:
                    try:
                        await _await_with_hard_deadline(
                            session.abort(),
                            timeout_seconds=self.cleanup_timeout_seconds,
                            operation="SDK session abort",
                        )
                    except Exception as cleanup_error:
                        cleanup_errors.append(
                            f"session.abort: {cleanup_error}"
                        )
                        cleanup_failures.append(cleanup_error)
                    raise
                except (TimeoutError, asyncio.TimeoutError) as exc:
                    try:
                        await _await_with_hard_deadline(
                            session.abort(),
                            timeout_seconds=self.cleanup_timeout_seconds,
                            operation="SDK session abort",
                        )
                    except Exception as cleanup_error:
                        cleanup_errors.append(
                            f"session.abort: {cleanup_error}"
                        )
                        cleanup_failures.append(cleanup_error)
                    raise AgentTimeoutError(
                        f"Agent request timed out after {request.timeout_seconds}s"
                    ) from exc
                except Exception as exc:
                    _raise_classified_sdk_error(stage, exc)
                return _event_content(event)

            content, terminal_event = await send_turn(
                request.prompt,
                attachments=converted_attachments,
                stage="SDK session error during initial send_and_wait",
            )

            if not content:
                raise TransientAgentError(
                    "Empty or missing response content returned from SDK session"
                )

            correction_prompt_hashes: list[str] = []
            assistant_response_hash_chain = [
                hashlib.sha256(content.encode("utf-8")).hexdigest()
            ]
            format_correction_count = 0
            correction_kind: str | None = None
            if not _is_syntactically_json(content):
                correction_prompt_hashes.append(
                    hashlib.sha256(
                        _FORMAT_CORRECTION_PROMPT.encode("utf-8")
                    ).hexdigest()
                )
                content, terminal_event = await send_turn(
                    _FORMAT_CORRECTION_PROMPT,
                    attachments=[],
                    stage="SDK session error during format correction",
                )
                format_correction_count = 1
                correction_kind = "syntax"
                assistant_response_hash_chain.append(
                    hashlib.sha256(content.encode("utf-8")).hexdigest()
                )
                if not content or not _is_syntactically_json(content):
                    raise ResponseValidationError(
                        "SDK same-session format correction failed: final "
                        "assistant content is not syntactically valid JSON"
                    )

            policy = request.response_validation_policy
            if policy is not None:
                issue = policy.validate(content)
                if issue is not None:
                    if format_correction_count:
                        raise ResponseValidationError(
                            "SDK response validation correction budget was "
                            "already consumed by syntax correction"
                        )
                    correction_prompt = policy.build_correction_prompt(issue)
                    if (
                        not isinstance(correction_prompt, str)
                        or not correction_prompt.strip()
                        or correction_prompt == request.prompt
                    ):
                        raise ResponseValidationError(
                            "SDK response validation policy returned an invalid "
                            "correction prompt"
                        )
                    correction_prompt_hashes.append(
                        hashlib.sha256(
                            correction_prompt.encode("utf-8")
                        ).hexdigest()
                    )
                    correction_label = policy.correction_kind.replace(
                        "_",
                        " ",
                    )
                    correction_label = (
                        correction_label[:1].upper()
                        + correction_label[1:]
                    )
                    content, terminal_event = await send_turn(
                        correction_prompt,
                        attachments=[],
                        stage=(
                            "SDK session error during "
                            f"{correction_label} correction"
                        ),
                    )
                    format_correction_count = 1
                    correction_kind = policy.correction_kind
                    assistant_response_hash_chain.append(
                        hashlib.sha256(content.encode("utf-8")).hexdigest()
                    )
                    if not content or not _is_syntactically_json(content):
                        raise ResponseValidationError(
                            f"{correction_label} correction failed: corrected "
                            "assistant content is not syntactically valid JSON"
                        )
                    if policy.validate(content) is not None:
                        raise ResponseValidationError(
                            f"{correction_label} correction failed strict "
                            "response validation"
                        )

            completed_at_dt = datetime.datetime.now(datetime.timezone.utc)
            duration = time.perf_counter() - start_time

            prompt_hash = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()
            attachment_hashes = [
                hashlib.sha256(att.data).hexdigest() for att in request.attachments
            ]
            output_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            sdk_ver = getattr(copilot, "__version__", None)
            protocol_identity = getattr(copilot, "_sdk_protocol_version", None)
            protocol_getter = getattr(
                protocol_identity,
                "get_sdk_protocol_version",
                None,
            )
            if callable(protocol_getter):
                protocol_identity = protocol_getter()
            elif hasattr(protocol_identity, "SDK_PROTOCOL_VERSION"):
                protocol_identity = protocol_identity.SDK_PROTOCOL_VERSION
            protocol_ver = (
                str(protocol_identity)
                if protocol_identity is not None
                else None
            )
            session_id = getattr(session, "session_id", None)

            provenance = AgentProvenance(
                engine="copilot-sdk",
                sdk_version=sdk_ver,
                runtime_protocol_version=protocol_ver,
                role=request.role,
                model=request.model,
                effort=request.reasoning_effort,
                context_tier=request.context_tier,
                session_id=session_id,
                prompt_hash=prompt_hash,
                attachment_hashes=attachment_hashes,
                output_hash=output_hash,
                started_at=started_at_dt.isoformat(),
                completed_at=completed_at_dt.isoformat(),
                duration_seconds=duration,
                terminal_event=terminal_event,
                is_live=True,
                retry_classification=None,
                turn_count=1 + format_correction_count,
                format_correction_count=format_correction_count,
                initial_prompt_hash=prompt_hash,
                correction_prompt_hashes=correction_prompt_hashes,
                assistant_response_hash_chain=assistant_response_hash_chain,
                turn_session_ids=[
                    session_id
                    for _ in range(1 + format_correction_count)
                ],
                correction_kind=correction_kind,
            )

            result = AgentResult(content=content, provenance=provenance)
            validate_agent_result(result, request)
            return result

        finally:
            primary_error = sys.exception()
            if session is not None:
                try:
                    await _await_with_hard_deadline(
                        session.disconnect(),
                        timeout_seconds=self.cleanup_timeout_seconds,
                        operation="SDK session disconnect",
                    )
                except Exception as cleanup_error:
                    cleanup_errors.append(
                        f"session.disconnect: {cleanup_error}"
                    )
                    cleanup_failures.append(cleanup_error)
            if client is not None:
                try:
                    await stop_client_bounded(
                        client,
                        timeout_seconds=self.cleanup_timeout_seconds,
                    )
                except Exception as cleanup_error:
                    cleanup_errors.append(f"client.stop: {cleanup_error}")
                    cleanup_failures.append(cleanup_error)
            if cleanup_errors:
                detail = "SDK cleanup failed: " + "; ".join(cleanup_errors)
                timeout_failure = next(
                    (
                        error
                        for error in cleanup_failures
                        if isinstance(
                            error,
                            (
                                AgentTimeoutError,
                                TimeoutError,
                                asyncio.TimeoutError,
                            ),
                        )
                    ),
                    None,
                )
                if timeout_failure is not None:
                    superseding_error: AgentRuntimeError = AgentTimeoutError(
                        detail
                    )
                else:
                    superseding_error = AgentLifecycleError(detail)
                if primary_error is not None:
                    superseding_error.add_note(
                        "The primary model/runtime error was superseded by "
                        "lifecycle cleanup failure."
                    )
                    raise superseding_error from primary_error
                raise superseding_error from cleanup_failures[0]
