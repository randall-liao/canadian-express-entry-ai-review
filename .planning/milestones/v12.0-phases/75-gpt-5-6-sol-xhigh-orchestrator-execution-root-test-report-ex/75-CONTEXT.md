# Phase 75: GPT 5.6 SOL XHIGH Orchestrator Execution & Root Test Report Export - Context

**Gathered:** 2026-07-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 75 converts validated Phase 72-74 evidence into the final release
assessment and root `TEST_REPORT.md`, makes the repository-root "I want to
review X" workflow operational, and runs the independent goal-backward audits
that decide whether milestone v12.0 is ready to ship. It does not rerun or
weaken the per-document research, synthetic generation, blind Worker, Judge,
or patch-acceptance contracts owned by Phases 72-74.

</domain>

<decisions>
## Implementation Decisions

### Release Assessment Authority
- **D-01:** Execute exactly one release assessment through the official GitHub Copilot SDK using `gpt-5.6-sol`, `xhigh` reasoning effort, and `long_context`.
- **D-02:** The release model receives only validated, PII-free aggregate evidence. Applicant facts, candidate-vault paths, raw Worker/Judge output, prompts, reasoning, credentials, and synthetic personal facts are excluded.
- **D-03:** Deterministic code is authoritative for every count, hash, score, delta, model assignment, command, status, and report table. Model prose is isolated in a labeled assessment section and cannot overwrite measured evidence.
- **D-04:** Missing, stale, malformed, privately contaminated, or internally inconsistent evidence fails closed. No hardcoded or deterministic substitute may be reported as the GPT orchestrator.

### Root Natural-Language Review Intent
- **D-05:** Requests such as "I want to review my passport," "review this document," or "review my Express Entry application" route to the Lead Review Coordinator defined in canonical root `AGENTS.md`.
- **D-06:** The coordinator uses the existing four-stage local workflow: candidate-vault setup/import and checklist; extraction and human field confirmation; corpus-grounded review, audit, and applicable screeners; remediation and redacted review-packet export.
- **D-07:** The agent must determine the local document path and upload-slot type without printing vault PII, must surface uncertain extraction for confirmation, and must abstain when authoritative corpus support is absent.
- **D-08:** `README.md` provides the minimal Poetry/Python/Copilot runtime setup and a literal "I want to review" example. No separate bespoke public review command is required.

### Measured Root Test Report
- **D-09:** Root `TEST_REPORT.md` includes all 23 document pipelines, 236 final Workers, 23 final Judges, optimizer/orchestrator provenance, exact model tiers, baseline/final metrics, score deltas, accepted and rejected patches, isolation checks, cleanup, retries/corrections, validation commands, and blockers.
- **D-10:** Per-document rows and aggregate totals render directly from validated evidence. The report states the Phase 74 source revision and evidence manifest hash.
- **D-11:** Existing repository test outcomes are reported truthfully. The known duplicate-audit invocation must be recorded as passed, failed, or timed out with its exact bounded duration; timeout is never converted into pass.

### Release and Audit Gate
- **D-12:** Milestone completion requires independent goal verifier, integration checker, deep code reviewer, security auditor, AI evaluation auditor, documentation verifier, and milestone-intent audit verdicts.
- **D-13:** Any unresolved must-have, high-severity correctness/security finding, grounding failure, PII leak, root-workflow integration break, incomplete live evidence, or self-improvement regression blocks release.
- **D-14:** `ORCHESTRATOR_REPORT-01`, `READY_USE-01`, `READY_USE-02`, and final cross-phase requirements are marked complete only after the live report and all blocking audit verdicts exist.

### the agent's Discretion
- Exact Pydantic field names, report helper boundaries, test fixture shape, and Markdown table layout are implementation details, provided the authority, privacy, model, truthfulness, and audit gates above remain explicit and testable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Final Goal and Requirements
- `.planning/PROJECT.md` - Release-ready root-agent goal, grounding, privacy, and real-agent constraints.
- `.planning/REQUIREMENTS.md` - `ORCHESTRATOR_REPORT-01`, `READY_USE-01`, `READY_USE-02`, and cross-phase traceability.
- `.planning/ROADMAP.md` - Phase 75 goal, success criteria, and dependency on Phase 74.
- `AGENTS.md` - Canonical grounding, PII partition, tool envelope, and four-stage review workflow.

### Approved Architecture and Execution Plan
- `docs/superpowers/specs/2026-07-25-copilot-sdk-document-review-pipeline-design.md` - Official SDK architecture, restart, source-freeze, cleanup, and release requirements.
- `docs/superpowers/plans/2026-07-25-root-agent-release.md` - Approved Phase 75 file structure, TDD tasks, live command, report contents, and audit matrix.
- `.planning/phases/74-blind-report-generator-judge-self-improvement-loop/74-CONTEXT.md` - Worker/Judge/optimizer privilege and evidence boundaries consumed by this phase.
- `.planning/phases/74-blind-report-generator-judge-self-improvement-loop/74-REVIEW.md` - Final deep review expectations and source-staleness gate.

### Runtime and Evidence Interfaces
- `crawler/eval/agent_runtime.py` - Typed `AgentRequest`, provenance, and lifecycle error contracts.
- `crawler/eval/copilot_sdk_runtime.py` - Official SDK session isolation and bounded lifecycle.
- `crawler/eval/phase74_evidence.py` - Strict committed evidence validation and aggregate source.
- `crawler/eval/phase74_evidence/manifest.json` - Canonical committed Phase 74 evidence root after the fresh run is published.
- `crawler/eval/sdk_pipeline_orchestrator.py` - Five-pipeline source freeze, process ownership, patch audit, and evidence publication.
- `crawler/tests/test_live_phase74_conformance_gate.py` - Release-blocking committed evidence gate.

### Product Onboarding
- `README.md` - User-facing setup and root-agent entrypoint to update.
- `crawler/cli.py` - Existing `corpus-crawler --json` command surface used by the root agent.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AgentRequest` and `CopilotSdkRuntime`: provide the exact official-SDK execution and provenance path required for the GPT release orchestrator.
- `phase74_evidence.validate_committed_phase74_evidence`: provides the fail-closed source of measured Phase 74 data.
- Root `AGENTS.md`: already defines the Lead Review Coordinator and all four review stages; Phase 75 adds explicit natural-language routing rather than inventing a second workflow.
- Existing `corpus-crawler --json` vault, checklist, doctor, grounding, audit, screening, remediation, and review-packet commands provide the complete local execution surface.

### Established Patterns
- Model roles generate interpretation only; Python validates schemas, hashes, coverage, and measured aggregates.
- Public reports contain no PII, raw prompts, reasoning, credentials, synthetic applicant facts, or absolute private paths.
- All model failures and incomplete evidence are explicit blockers; no success-shaped fallback exists.
- GSD state and requirement transitions occur only after live evidence and independent verification.

### Integration Points
- Add `crawler/eval/release_orchestrator.py` and `crawler/eval/test_report.py`.
- Add Phase 75 release and root-agent workflow tests under `crawler/tests/`.
- Extend `AGENTS.md` and `README.md` with root review-intent routing and onboarding.
- Generate root `TEST_REPORT.md` only after the fresh Phase 74 committed evidence gate passes.

</code_context>

<specifics>
## Specific Ideas

- The release assessment model is mandatory `gpt-5.6-sol` with `xhigh` effort and `long_context`.
- The report must visibly name `gemini-3.6-flash`, `claude-opus-4.8`, and `gpt-5.6-sol`.
- The user-facing happy path begins by starting Copilot at the repository root and saying: `I want to review my passport for my Express Entry application.`
- Artifact completion alone is insufficient; audit agents must prove the user outcome works end to end.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within the Phase 75 release boundary.

</deferred>

---

*Phase: 75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-export*
*Context gathered: 2026-07-27*
