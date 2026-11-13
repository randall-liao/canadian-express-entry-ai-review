# Copilot SDK Evaluation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stalled Phase 74 prompt subprocess loop with five supervised, isolated document pipelines whose model work runs through the official GitHub Copilot Python SDK.

**Architecture:** A typed SDK adapter executes one bounded model turn at a time. A document-pipeline child process owns one SDK runtime directory and sequential Worker, Judge, optimizer, and candidate-evaluation stages; a parent supervisor runs at most five children, monitors atomic heartbeats, and terminates only verified run-owned processes. Exact input hashes, model configuration, validation results, and SDK provenance gate every reusable artifact.

**Tech Stack:** Python 3.11+, `github-copilot-sdk` 1.0.x, `asyncio`, Pydantic 2, pytest, existing corpus/grounding and Phase 73 fixture APIs.

## Global Constraints

- Require Python 3.11 or later because `github-copilot-sdk` requires it.
- Use `gemini-3.6-flash` with `context_tier="long_context"` for Workers and optimizers.
- Use `claude-opus-4.8` with `reasoning_effort="xhigh"` and `context_tier="long_context"` for Judges.
- Run at most five document pipeline child processes and at most five live model sessions globally.
- Hold one repository-wide exclusive live-run lease; overlapping supervisors fail closed.
- Release a pipeline slot only after its child and recorded SDK runtime descendants exit.
- Worker sessions use SDK `mode="empty"`, `available_tools=[]`, blob PDF attachments, no skills, no MCP, no memory, no host Git, no custom instructions, and no session store.
- Only Judges may receive research, ground truth, sibling mappings, or failure labels.
- No deterministic or hardcoded output may be reported as model output.
- Reuse requires exact input, configuration, provenance, and validation hashes.
- Do not terminate the foreground interactive Copilot process; cleanup is run-ID and PID-ownership based.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Python floor and SDK dependency |
| `crawler/eval/agent_runtime.py` | Runtime-neutral request/result types and protocol |
| `crawler/eval/copilot_sdk_runtime.py` | Official SDK lifecycle, timeout, abort, event, and provenance adapter |
| `crawler/eval/pipeline_state.py` | Atomic run manifests, heartbeats, hashes, and state transitions |
| `crawler/eval/pipeline_worker.py` | Blind SDK Worker prompt, blob attachment, validation, and report persistence |
| `crawler/eval/pipeline_judge.py` | Privileged SDK Judge request, strict coverage, and bound provenance |
| `crawler/eval/genuine_optimizer.py` | Training-only SDK optimizer proposal |
| `crawler/eval/document_pipeline.py` | One document type's sequential evaluation and optimization state machine |
| `crawler/eval/sdk_pipeline_orchestrator.py` | Five-child supervisor, preflight, cleanup, progress, and restart |
| `crawler/eval/loop_orchestrator.py` | Compatibility entrypoint delegating live work to the SDK supervisor |
| `crawler/tests/test_copilot_sdk_runtime.py` | SDK configuration and lifecycle contracts |
| `crawler/tests/test_phase74_pipeline_state.py` | Atomic state, heartbeat, reuse, and cleanup contracts |
| `crawler/tests/test_phase74_sdk_pipeline.py` | Blindness, five-pipeline scheduling, optimization, and restart integration |
| `crawler/tests/test_live_phase74_conformance_gate.py` | Live SDK provenance and complete final-run gate |

### Task 1: Adopt the Official SDK Runtime

**Files:**
- Modify: `pyproject.toml:6-16`
- Create: `crawler/eval/agent_runtime.py`
- Create: `crawler/eval/copilot_sdk_runtime.py`
- Create: `crawler/tests/test_copilot_sdk_runtime.py`

**Interfaces:**
- Produces: `AgentRequest`, `AgentResult`, `AgentRuntime`, `CopilotSdkRuntime.run(request) -> AgentResult`.
- Consumes: official `copilot.CopilotClient`, `copilot.session_events.AssistantMessageData`, and SDK attachment dictionaries.

- [ ] **Step 1: Write failing runtime-contract tests**

```python
@pytest.mark.asyncio
async def test_worker_request_uses_empty_mode_and_no_tools(fake_sdk):
    runtime = CopilotSdkRuntime(
        base_directory=fake_sdk.base_directory,
        client_factory=fake_sdk.client_factory,
    )
    result = await runtime.run(
        AgentRequest(
            role="worker",
            model="gemini-3.6-flash",
            context_tier="long_context",
            prompt="return JSON",
            attachments=[
                BlobAttachment(
                    data=b"%PDF-1.4\n%%EOF",
                    mime_type="application/pdf",
                    display_name="document.pdf",
                )
            ],
            timeout_seconds=10,
        )
    )
    assert fake_sdk.client_mode == "empty"
    assert fake_sdk.create_kwargs["available_tools"] == []
    assert fake_sdk.create_kwargs["enable_skills"] is False
    assert fake_sdk.create_kwargs["enable_session_store"] is False
    assert result.provenance.engine == "copilot-sdk"
```

```python
@pytest.mark.asyncio
async def test_timeout_aborts_disconnects_and_stops(fake_sdk):
    fake_sdk.block_until_aborted = True
    runtime = CopilotSdkRuntime(
        base_directory=fake_sdk.base_directory,
        client_factory=fake_sdk.client_factory,
    )
    with pytest.raises(AgentTimeoutError):
        await runtime.run(
            AgentRequest(
                role="worker",
                model="gemini-3.6-flash",
                context_tier="long_context",
                prompt="block",
                attachments=[],
                timeout_seconds=0.01,
            )
        )
    assert fake_sdk.abort_calls == 1
    assert fake_sdk.disconnect_calls == 1
    assert fake_sdk.stop_calls == 1
```

- [ ] **Step 2: Run tests and confirm the new modules are missing**

Run:

```bash
.venv/bin/python -m pytest crawler/tests/test_copilot_sdk_runtime.py -q
```

Expected: collection fails because `crawler.eval.agent_runtime` and `crawler.eval.copilot_sdk_runtime` do not exist.

- [ ] **Step 3: Update the Python and dependency contract**

Set:

```toml
requires-python = ">=3.11,<4.0"
dependencies = [
    "pyyaml>=6.0,<7.0",
    "pydantic (>=2.13,<3.0)",
    "platformdirs (>=4.10,<5.0)",
    "github-copilot-sdk>=1.0.8,<1.1.0",
]

[project.optional-dependencies]
doc-extract = [
    "pypdfium2>=5.11,<6.0",
    "Pillow>=12.3,<13.0",
    "pdfminer.six>=20260107,<20270000",
    "reportlab>=4.4,<6.0",
]
```

Provision Python 3.11 if it is not already installed, then let Poetry manage the
environment and dependencies:

```bash
uv python install 3.11
poetry env use "$(uv python find 3.11)"
poetry lock
poetry install -E doc-extract -E ocr
poetry run python -m copilot download-runtime
```

- [ ] **Step 4: Implement runtime-neutral types**

Define frozen dataclasses for:

```python
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

@dataclass(frozen=True)
class AgentResult:
    content: str
    provenance: AgentProvenance
```

`AgentProvenance` must include engine, SDK version, runtime protocol version, role,
model, effort, context tier, session ID, prompt hash, attachment hashes, output hash,
started/completed timestamps, duration, terminal event, and retry classification.

- [ ] **Step 5: Implement `CopilotSdkRuntime`**

Use:

```python
client = CopilotClient(mode="empty", base_directory=str(self.base_directory))
await client.start()
session = await client.create_session(
    model=request.model,
    reasoning_effort=request.reasoning_effort,
    context_tier=request.context_tier,
    available_tools=[],
    working_directory=str(self.base_directory),
    skip_custom_instructions=True,
    enable_config_discovery=False,
    enable_on_demand_instruction_discovery=False,
    enable_file_hooks=False,
    enable_host_git_operations=False,
    enable_session_store=False,
    enable_skills=False,
    mcp_servers={},
    memory={"enabled": False},
    enable_session_telemetry=False,
    system_message={"mode": "replace", "content": role_system_message},
)
```

Pass attachments as base64 blob dictionaries. On `TimeoutError`, call
`await session.abort()` under a cleanup timeout. Always disconnect and stop under
separate cleanup timeouts. Accept only a final `AssistantMessageData` event.

- [ ] **Step 6: Run runtime tests**

Run:

```bash
.venv/bin/python -m pytest crawler/tests/test_copilot_sdk_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml crawler/eval/agent_runtime.py crawler/eval/copilot_sdk_runtime.py crawler/tests/test_copilot_sdk_runtime.py
git commit -m "feat(eval): add isolated Copilot SDK runtime"
```

### Task 2: Add Durable Pipeline State and Ownership-Safe Cleanup

**Files:**
- Create: `crawler/eval/pipeline_state.py`
- Create: `crawler/tests/test_phase74_pipeline_state.py`

**Interfaces:**
- Consumes: `AgentProvenance`.
- Produces: `RunManifest`, `StageManifest`, `PipelineStateStore`, `cleanup_stalled_runs()`.

- [ ] **Step 1: Write failing state tests**

Cover:

```python
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
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase74_pipeline_state.py -q
```

Expected: import failure for `crawler.eval.pipeline_state`.

- [ ] **Step 3: Implement strict Pydantic manifests**

Use enums for stage and status. Store `run_id`, `doc_type`, PID, process start time,
command digest, stage, item, sequence, deadline, hashes, timestamps, status, and error
classification. Reject invalid transitions and non-finite timestamps.

- [ ] **Step 4: Implement atomic JSON writes**

Write in the destination directory with `NamedTemporaryFile(delete=False)`, flush,
`os.fsync`, `os.replace`, and directory fsync. Invalid JSON must never be interpreted
as a successful checkpoint.

- [ ] **Step 5: Implement cleanup ownership checks**

Before signaling a PID, verify all of:

```python
manifest.pid == process.pid
manifest.process_start_time == process.start_time
manifest.command_digest == sha256(process.argv)
manifest.run_id in process.argv
heartbeat_is_stale(manifest)
```

Use `os.kill(pid, signal.SIGTERM)`, wait a bounded grace period, and use
`signal.SIGKILL` only for the same revalidated PID. Never use `pkill` or `killall`.
Track SDK runtime descendant PIDs in the manifest and do not release a supervisor slot
until all verified descendants exit.

- [ ] **Step 6: Run state tests**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase74_pipeline_state.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add crawler/eval/pipeline_state.py crawler/tests/test_phase74_pipeline_state.py
git commit -m "feat(eval): add durable pipeline state and cleanup"
```

### Task 3: Migrate Worker, Judge, and Optimizer Roles

**Files:**
- Modify: `crawler/eval/pipeline_worker.py`
- Modify: `crawler/eval/pipeline_judge.py`
- Modify: `crawler/eval/genuine_optimizer.py`
- Modify: `crawler/tests/test_phase74_worker_isolation.py`
- Modify: `crawler/tests/test_phase74_judge_loop.py`
- Create: `crawler/tests/test_phase74_sdk_roles.py`

**Interfaces:**
- Consumes: `AgentRuntime.run(AgentRequest)`.
- Produces: `run_blind_worker_task_async`, `run_batched_document_judge_async`, `run_candidate_optimization_pass_async`.

- [ ] **Step 1: Write failing SDK role tests**

Assert Worker requests contain no privileged values and one PDF blob; Judge requests
use exact Opus model/effort/context and bind all input hashes; optimizer requests
contain sealed training findings but no holdout evaluations or case rationales.

- [ ] **Step 2: Run role tests and confirm failure**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase74_sdk_roles.py crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_phase74_judge_loop.py -q
```

- [ ] **Step 3: Refactor Worker execution**

Keep prompt construction and validators, but replace command construction and JSONL
parsing with:

```python
result = await runtime.run(
    AgentRequest(
        role="worker",
        model="gemini-3.6-flash",
        context_tier="long_context",
        prompt=prompt,
        attachments=[
            BlobAttachment(
                data=pdf_bytes,
                mime_type="application/pdf",
                display_name="document.pdf",
            )
        ],
        timeout_seconds=600,
    )
)
answer = json.loads(result.content)
```

Retry only `TransientAgentError`; schema, grounding, PII, and blindness errors fail
immediately and remove partial reports.

- [ ] **Step 4: Refactor Judge execution**

Build blob attachments from the exact ordered PDF set and execute:

```python
AgentRequest(
    role="judge",
    model="claude-opus-4.8",
    reasoning_effort="xhigh",
    context_tier="long_context",
    prompt=prompt,
    attachments=pdf_attachments,
    timeout_seconds=900,
)
```

Validate strict JSON with `JudgeEvaluationBatch.model_validate_json`, exact document
type, exact case coverage, valid finding case IDs, and bound input-manifest hash.

- [ ] **Step 5: Refactor optimizer execution**

Execute Gemini through the runtime with no attachments and validate
`OptimizerProposal.model_validate_json`. Write the candidate only after validation.
Remove sandbox recovery that fabricates live provenance.

- [ ] **Step 6: Run role tests**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase74_sdk_roles.py crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_phase74_judge_loop.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add crawler/eval/pipeline_worker.py crawler/eval/pipeline_judge.py crawler/eval/genuine_optimizer.py crawler/tests/test_phase74_sdk_roles.py crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_phase74_judge_loop.py
git commit -m "refactor(eval): run Phase 74 roles through Copilot SDK"
```

### Task 4: Build One Isolated Document Pipeline

**Files:**
- Create: `crawler/eval/document_pipeline.py`
- Create: `crawler/tests/test_phase74_document_pipeline.py`

**Interfaces:**
- Consumes: SDK role functions, holdout splitter, patch evaluator, state store.
- Produces: `DocumentPipelineConfig`, `DocumentPipelineResult`, `run_document_pipeline(config)`.

- [ ] **Step 1: Write a failing state-machine test**

Use fake runtime results for two sibling groups and assert transitions:

```python
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
assert result.max_live_sessions == 1
assert result.patch.status in {"accepted", "rejected"}
```

- [ ] **Step 2: Run the test and confirm failure**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase74_document_pipeline.py -q
```

- [ ] **Step 3: Implement the sequential state machine**

Each stage computes a canonical input manifest before execution, writes a running
checkpoint and heartbeat, persists validated outputs atomically, and marks completion.
Reuse only through `PipelineStateStore.can_reuse`.

- [ ] **Step 4: Implement compare-and-swap patch decisions**

Return candidate content and decision evidence to the parent. Do not edit source or
invoke Git inside the document child. The result includes the source hash used for the
candidate so the parent can reject drift.

- [ ] **Step 5: Run document-pipeline tests**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase74_document_pipeline.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add crawler/eval/document_pipeline.py crawler/tests/test_phase74_document_pipeline.py
git commit -m "feat(eval): add isolated document pipeline state machine"
```

### Task 5: Build the Five-Pipeline Supervisor and Stalled-State Cleanup

**Files:**
- Create: `crawler/eval/sdk_pipeline_orchestrator.py`
- Modify: `crawler/eval/loop_orchestrator.py`
- Create: `crawler/tests/test_phase74_sdk_pipeline.py`
- Modify: `crawler/tests/test_phase74_data_seam_integration.py`

**Interfaces:**
- Consumes: `run_document_pipeline` child entrypoint and run manifests.
- Produces: `SdkPipelineOrchestrator.run()`, `cleanup`, `preflight`, and compatibility CLI.

- [ ] **Step 1: Write failing concurrency and watchdog tests**

Launch six fake document child commands. Assert five distinct document types overlap,
the sixth starts after a slot and its descendants exit, heartbeat progress is
observed, a second supervisor is rejected by the exclusive lease, and a stale child is
terminated by its verified PID without affecting healthy children.

- [ ] **Step 2: Run tests and confirm failure**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase74_sdk_pipeline.py crawler/tests/test_phase74_data_seam_integration.py -q
```

- [ ] **Step 3: Implement preflight**

Verify Python >=3.11, SDK import/version, runtime download, Copilot auth, exact model
availability, protocol status, corpus DB, 23 pipeline roots, 236 PDFs, ignored runtime
roots, and clean input hashes before spawning children.

- [ ] **Step 4: Implement five-child scheduling**

Use `asyncio.create_subprocess_exec` with:

```python
await asyncio.create_subprocess_exec(
    sys.executable,
    "-m",
    "crawler.eval.document_pipeline",
    "--run-id",
    run_id,
    "--doc-type",
    doc_type,
    "--run-root",
    str(run_root),
)
```

Guard launch with `asyncio.Semaphore(5)` and a repository-wide
`PipelineRunLease`. Use a fair document queue, read stdout/stderr incrementally into
run-local logs, monitor heartbeats and recorded SDK descendants, and preserve a result
for every document type.

- [ ] **Step 5: Apply approved patches serially**

After each wave, validate source hash, allowlist, candidate hash, and decision
evidence. Apply with `apply_patch_atomically`; serialize Git commits and include the
document type and measured delta.

After all document and shared decisions, freeze the Git revision and the 23 public
bundle hashes. Final Workers and Judges must all bind to this immutable final manifest;
the supervisor must reject any source drift or overlapping optimization.

- [ ] **Step 6: Delegate the legacy CLI entrypoint**

`loop_orchestrator.py --mode optimize|final-pass|full-loop` must invoke
`SdkPipelineOrchestrator` for live execution. Keep injected unit-runner paths only
where existing tests require them, and mark them non-live.

- [ ] **Step 7: Run supervisor tests**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase74_sdk_pipeline.py crawler/tests/test_phase74_data_seam_integration.py -q
```

Expected: all tests pass, observed peak pipeline concurrency equals five, five
distinct document types make progress fairly, overlapping supervisors are rejected,
and no child or SDK runtime descendant remains.

- [ ] **Step 8: Commit**

```bash
git add crawler/eval/sdk_pipeline_orchestrator.py crawler/eval/loop_orchestrator.py crawler/tests/test_phase74_sdk_pipeline.py crawler/tests/test_phase74_data_seam_integration.py
git commit -m "feat(eval): supervise five isolated SDK pipelines"
```

### Task 6: Clean Stalled State and Run a Fresh Live Improvement Pass

**Files:**
- Create: `reports/phase74_sdk_runs/<run_id>/cleanup_audit.json` (git-ignored)
- Create: `crawler/eval/pipelines/*/iterations/iter_sdk_final/`
- Modify: `crawler/tests/test_live_phase74_conformance_gate.py`
- Create: `.planning/phases/74-blind-report-generator-judge-self-improvement-loop/74-05-SUMMARY.md`

**Interfaces:**
- Consumes: completed SDK supervisor and existing committed baseline.
- Produces: complete live final artifacts, patch audit, conformance evidence, summary.

- [ ] **Step 1: Run ownership-safe cleanup in dry-run mode**

```bash
.venv/bin/python -m crawler.eval.sdk_pipeline_orchestrator cleanup --dry-run
```

Expected: foreground interactive Copilot PID is explicitly retained; stale partial
candidate/final artifacts are listed for quarantine.

- [ ] **Step 2: Execute cleanup**

```bash
.venv/bin/python -m crawler.eval.sdk_pipeline_orchestrator cleanup --apply
```

Expected: only manifest-owned stale state is terminated or quarantined and an atomic
cleanup audit is written.

- [ ] **Step 3: Run the fresh live pipeline**

```bash
.venv/bin/python -m crawler.eval.sdk_pipeline_orchestrator run --concurrency 5 --fresh
```

Expected: 23 document results, 236 final live Worker reports, 23 final live Judge
reports, peak pipeline concurrency 5, and no active run-owned child remains.

- [ ] **Step 4: Strengthen and run the live gate**

The gate must require `engine == "copilot-sdk"`, SDK version, exact role model config,
input manifest hashes, complete terminal lifecycle, 236/23 counts, zero unresolved
stale state, holdout non-regression, and patch audits.

```bash
REQUIRE_LIVE_PHASE74_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -v
```

Expected: pass.

- [ ] **Step 5: Run targeted Phase 74 tests**

```bash
.venv/bin/python -m pytest crawler/tests/test_copilot_sdk_runtime.py crawler/tests/test_phase74_pipeline_state.py crawler/tests/test_phase74_sdk_roles.py crawler/tests/test_phase74_document_pipeline.py crawler/tests/test_phase74_sdk_pipeline.py crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_phase74_judge_loop.py crawler/tests/test_phase74_data_seam_integration.py -q
```

Expected: pass.

- [ ] **Step 6: Write the truthful Plan 74-05 summary**

Include the diagnosed stall mechanism, SDK architecture, cleanup audit, exact live
counts, accepted/rejected patches, baseline/final metrics, concurrency evidence,
holdout results, and any blocker. Do not mark Phase 74 complete if the live gate fails.

- [ ] **Step 7: Commit**

```bash
git add crawler/eval/pipelines/*/iterations/iter_sdk_final .planning/phases/74-blind-report-generator-judge-self-improvement-loop/74-05-SUMMARY.md crawler/tests/test_live_phase74_conformance_gate.py
git commit -m "feat(74-05): complete SDK self-improvement pass"
```
