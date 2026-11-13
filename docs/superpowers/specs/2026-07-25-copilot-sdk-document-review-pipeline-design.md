# Copilot SDK Document Review Pipeline Design

**Date:** 2026-07-25
**Status:** Approved for autonomous implementation
**Scope:** Complete Phases 74 and 75 of milestone v12.0

## Goal

Ship a ready-to-use Canadian Express Entry document review project. A user starts a
GitHub Copilot agent at the repository root and asks to review a document or
application. The agent follows `AGENTS.md`, invokes the deterministic local
`corpus-crawler --json` tools, keeps applicant PII local, grounds every policy claim
in `corpus/index.db`, and produces actionable review and remediation reports.

Before release, the project must finish its blind document-agent self-improvement
benchmark. Five document-type pipelines run concurrently. Gemini 3.6 Flash
long-context Workers remain blind, Claude Opus 4.8 `xhigh` long-context Judges alone
see research and ground truth, and Gemini optimizers receive training findings only.
No Python fallback may impersonate model output.

## Release-Blocking Final Product Goal

The milestone is not complete merely because benchmark files exist. Independent
goal-backward audit agents must verify the user outcome: from the repository root, a
user can start a GitHub Copilot agent, state "I want to review X," keep the supplied
documents and PII local, and receive corpus-grounded Canadian Express Entry review,
remediation, and redacted report guidance. The audit must also verify that the
document-agent self-improvement loop completed with truthful SDK provenance and no
holdout or safety regression.

The final audit set includes goal verification, cross-phase integration, code review,
security review, AI evaluation coverage, documentation verification, and milestone
intent audit. Any unresolved must-have, high-severity defect, grounding failure, PII
leak, or incomplete live evidence blocks release.

## Existing Failure

The Phase 74 CLI implementation is not safely resumable:

- document-type optimization is serial even when `--concurrency 5` is selected;
- Worker and Judge calls capture all output until process exit, so no heartbeat or
  progress event is visible;
- broad retries can spend about 30 minutes on one Worker or 45 minutes on one Judge,
  including deterministic schema or grounding failures that cannot benefit from a
  retry;
- accepted checkpoints retain pre-patch source hashes and become invalid after their
  own patch is applied;
- sandbox recovery can reuse stale candidates without proving the original input
  hashes and can manufacture current live provenance;
- Judge reuse does not bind the evaluation to exact Worker, bundle, PDF, research,
  and ground-truth hashes.

The interactive `copilot --resume` process is not a stale Phase 74 child. Cleanup
must preserve that foreground process and remove only run-owned state.

## Considered Architectures

### Shared SDK Client

One `CopilotClient` would host all concurrent sessions. This minimizes runtime startup
cost, but a blocked client transport can stall every document pipeline, and privileged
Judge state shares one runtime with blind Workers.

### One SDK Client per Pipeline in One Python Process

Each asynchronous document task would own a client and isolated SDK base directory.
This improves data separation, but a transport or cleanup bug can still block the
single parent event loop and makes hard termination difficult.

### Supervised Pipeline Processes

**Selected.** A parent orchestrator runs at most five document pipeline child
processes. Each child uses the official Python `github-copilot-sdk` and owns:

- one isolated SDK `base_directory`;
- one document type;
- a durable state manifest and heartbeat;
- all Worker, Judge, optimizer, and candidate-evaluation stages for that document;
- no access to another pipeline's private artifacts.

The parent owns process deadlines and can terminate a specific unresponsive child
without affecting other pipelines. This adds modest startup overhead but provides the
required isolation, observability, cleanup, and recovery guarantees.

Only one supervisor may own live benchmark execution for the repository. It acquires
an exclusive run lease containing the run ID, PID, process start time, command digest,
and heartbeat. A second supervisor fails closed unless the existing lease is proven
stale by the same ownership checks used for cleanup.

## Runtime and Dependency Contract

- Require Python 3.11 or later because `github-copilot-sdk` requires it.
- Pin the SDK to the compatible `1.0` release line and record the resolved version.
- Use the SDK-bundled Copilot runtime through `CopilotClient`; do not execute prompt
  work through `copilot -p`.
- Preflight authentication, model availability, protocol compatibility, corpus
  availability, and runtime download before launching live work.
- Use a repository-local, git-ignored SDK runtime/state root for benchmark sessions.
- Keep injected test runners behind the same typed runtime interface for non-live
  tests, but provenance must identify them as non-live.

## Components

### SDK Session Runner

A focused adapter owns `CopilotClient` and `CopilotSession` lifecycles. It:

- starts a client in `mode="empty"` with an explicit isolated `base_directory`;
- creates sessions with exact model, reasoning effort, and context tier;
- calls `send_and_wait` with a bounded timeout;
- calls `session.abort()` when a turn times out;
- disconnects or deletes the session and stops the client in `finally`;
- records sanitized lifecycle events, usage, model, protocol, input hashes, output
  hash, session ID, timestamps, and terminal status;
- never persists prompts, reasoning, applicant PII, secrets, or absolute private
  paths in publishable artifacts.

Retries are classified. Network, quota, and recoverable SDK transport failures may
retry within a stage budget. Schema, grounding, PII, blindness, coverage, or
allowlist failures do not repeat an identical model call.

### Blind Worker Session

Each case gets a fresh ephemeral Gemini 3.6 Flash `long_context` session.

- The PDF is supplied as an `application/pdf` blob attachment with an opaque display
  name, avoiding repository filesystem access.
- The prompt contains only the public review bundle, allowed extracted text, document
  upload-slot type, and opaque case ID.
- The SDK client uses `mode="empty"`, `available_tools=[]`, no custom tools, no MCP
  servers, no skills, no custom-instruction discovery, no memory, no host Git
  operations, and no session store.
- The session receives no research, ground truth, sibling mapping, defect label,
  expected verdict, or privileged path.
- Output must be strict AnswerObject JSON and pass schema, grounding, PII, and
  blindness validation before it becomes reusable.

Native and scanned siblings always use different sessions.

### Privileged Judge Session

After all cases for one document type complete, a separate privileged session runs
Claude Opus 4.8 with `reasoning_effort="xhigh"` and
`context_tier="long_context"`.

The Judge receives only that document type's PDFs, Worker reports, research, private
ground truth, and exact authoritative evidence. It returns strict per-case scores and
findings with complete case coverage. Python validates and aggregates but never
creates semantic scores or missed-defect findings.

Judge provenance binds the output to hashes of every Worker report, PDF, public
bundle, research report, ground-truth record, prompt contract, model configuration,
and SDK version.

### Optimizer and Candidate Evaluation

One Gemini optimizer per document type receives sealed training findings and the
current target skill only. It writes a candidate in its pipeline sandbox. The
candidate:

- is scanned by the existing allowlist and publish-safety rules;
- is evaluated against training cases and the complete sealed holdout sibling groups;
- is accepted only when training metrics improve and every holdout and safety
  dimension is non-regressing;
- is applied only after evaluation, using a compare-and-swap source hash;
- records accepted, rejected, or blocked status without converting infrastructure
  failure into semantic rejection.

Document pipeline tasks never run Git concurrently. The parent applies approved,
non-conflicting document-skill patches serially after each wave. A separate shared
optimizer runs after document-specific patches and evaluates any shared PDF or agent
contract candidate across all 23 document types before serial application.

## Five-Pipeline Scheduler

The parent scheduler maintains exactly one global semaphore with capacity five. A
slot represents one document pipeline child process, not one nested thread pool.
Within a child, model sessions run sequentially, so at most five live Copilot model
sessions exist globally.

Each child emits an atomic heartbeat containing:

- run ID and document type;
- current stage and case;
- attempt and stage deadline;
- last event timestamp;
- completed and expected work counts;
- input-manifest hash;
- process ID and terminal status.

The parent reports progress as heartbeats arrive. If a heartbeat or stage deadline is
missed, it terminates only that run-owned child process, marks the stage blocked, and
continues other pipelines. A slot is released only after the child and its recorded SDK
runtime descendants have exited. No name-based process killing is allowed.

## Durable State and Restart

Every run receives a new immutable run ID. State transitions are:

`pending -> running -> completed | blocked | cancelled`

Stage outputs are written to temporary files, fsynced, and atomically renamed.
Reusing an output requires exact matches for:

- document type, case set, and sibling mapping;
- PDF and allowed extracted-text hashes;
- public bundle, skill source, and prompt-contract hashes;
- Worker report hashes for Judge outputs;
- research and ground-truth hashes for Judge outputs;
- model, reasoning effort, context tier, SDK version, and runtime mode;
- successful schema, grounding, PII, blindness, coverage, and publish-safety
  validation.

Copilot conversations are never resumed for benchmark semantics. Restart resumes from
validated stage artifacts and creates a fresh session for incomplete work. This
prevents partially completed turns or stale conversation context from contaminating a
new run.

After all accepted document and shared patches are applied, the supervisor freezes one
source revision and bundle manifest. Every final Worker and Judge output must bind to
that same revision; optimization and final execution may not overlap.

## Stalled-State Cleanup

Cleanup is manifest-driven and fail-closed:

- identify run-owned process IDs from heartbeat manifests and verify their command,
  parent, start time, and repository run ID before termination;
- never terminate the foreground interactive Copilot process;
- archive accepted patch evidence and validated baseline artifacts;
- quarantine or delete partial candidate/final outputs that lack a complete matching
  manifest;
- remove abandoned Worker staging directories and SDK state roots only when no
  verified owner process is alive;
- preserve a cleanup audit describing every retained, quarantined, or removed path.

## Root-Agent Product Flow

`AGENTS.md` remains the canonical entry point. A root Copilot agent interpreting
"review X" must:

1. identify or initialize the local candidate vault;
2. import the supplied document without printing PII;
3. run extraction and surface pending fields for human confirmation;
4. invoke the matching document skill and corpus-backed review tools;
5. validate all policy claims through the grounding gate;
6. run applicable CRS and policy screeners;
7. generate private remediation guidance and a redacted review packet;
8. state blockers and abstentions explicitly rather than guessing.

Onboarding documentation provides prerequisites, authentication/runtime preflight,
the minimal review command conversation, local-data boundaries, and recovery steps.

## Verification and Release

The implementation is complete only when:

- unit tests prove SDK configuration, blob attachments, timeout-abort-cleanup,
  retry classification, provenance hashing, heartbeat monitoring, process ownership,
  and stale-output rejection;
- adversarial tests prove Workers cannot access privileged data or another pipeline;
- an integration test proves five document pipelines make concurrent progress while
  never exceeding five live model sessions;
- concurrent-supervisor and fairness tests prove the exclusive lease prevents
  overlapping runs and the scheduler advances five distinct document pipelines rather
  than filling every slot from one document type;
- the live restart run completes all 23 pipelines, 236 final Worker reports, and 23
  final Judge evaluations;
- accepted and rejected patches have complete train/holdout audit trails;
- final holdout and safety metrics do not regress from the committed baseline;
- live Phase 74 conformance, repository conformance, and publish-safety gates pass;
- root `TEST_REPORT.md` reports measured results, model assignments, isolation,
  retries, blockers, score deltas, and validation status;
- a root-agent smoke test demonstrates the documented "I want to review X" workflow
  while preserving grounding and local PII containment.

The known duplicate-audit test timeout must be reported accurately if it remains
unresolved; it may not be presented as a passing validation.
