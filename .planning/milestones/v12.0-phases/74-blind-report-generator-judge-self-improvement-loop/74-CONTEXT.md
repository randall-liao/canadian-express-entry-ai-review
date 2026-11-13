# Phase 74: Blind Report Generator & Judge Self-Improvement Loop - Context

**Gathered:** 2026-07-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 74 runs blind report-generating workers over the 236 Phase 73 PDFs, evaluates them with the only privileged role, and performs measured self-improvement. Each worker is a real GitHub Copilot CLI Gemini 3.6 Flash long-context session with one staged case. The final Judge is a real GitHub Copilot CLI Claude Opus 4.8 session using `xhigh` reasoning and `long_context`, batched once per document type. Optimizer roles are also real Copilot agents. This phase may apply only measured, non-regressing prompt/skill patches; end-to-end orchestration and root `TEST_REPORT.md` export remain Phase 75.

</domain>

<decisions>
## Implementation Decisions

### Blind Worker Execution
- **D-01:** Execute exactly one independent Gemini 3.6 Flash long-context GitHub Copilot CLI Worker session for each of the 236 opaque PDF fixtures.
- **D-02:** A Worker receives only: one Phase 73 staged opaque PDF attachment, allowed extracted text, the normal document upload-slot type, and a public review evidence bundle assembled from canonical document skills plus authoritative local corpus chunks. It receives no research report, GenerationSpec, ground truth, sibling mapping, failure ID, expected verdict, variant label, or privileged path.
- **D-03:** Workers run from the fresh Phase 73 staging directory with `--no-custom-instructions`, no unrestricted path permission, no repository cwd, and no shell/write/GitHub/web capability. All review evidence is inline or attached.
- **D-04:** Worker output is a strict five-field AnswerObject plus truthful execution provenance. It is captured from canonical JSONL final-message events only, passed through the local grounding gate, and fails closed on process, schema, citation, quote, PII, or blindness errors.
- **D-05:** Native and scanned siblings run in separate sessions and cannot share session history, cached outputs, filenames, or case mappings.

### Public Evidence Bundle
- **D-06:** Build one immutable public review bundle per document type from `skills/document-agents/` and exact corpus citations/quotes. Bundles may describe normal requirements but contain no Phase 72 failure research, Phase 73 defect selection, case labels, or Judge-only information.
- **D-07:** Bundle hashes are recorded in Worker provenance so each report can be reproduced and compared across iterations without revealing privileged inputs.

### Privileged Judge
- **D-08:** Run exactly one privileged Judge session per document type per evaluation pass, batching that type's Worker reports and 10 or 12 PDF attachments. The Judge alone receives Phase 72 research, Phase 73 private ground truth/sibling mapping, Worker reports, and authoritative evidence.
- **D-09:** Every Judge session uses GitHub Copilot CLI model `claude-opus-4.8`, `--effort xhigh`, and `--context long_context`. No GPT or deterministic evaluator may be reported as the Judge.
- **D-10:** Judge outputs strict per-case scores for grounding accuracy, citation exactness, defect recall, PII containment, and blind-input compliance, plus evidence-based findings and training-only patch recommendations. Process or schema failure is blocked; deterministic score fallback is prohibited.
- **D-11:** Python may validate Judge structure, recompute deterministic counts/hashes, and aggregate metrics, but may not generate semantic scores or missed-defect findings from ground truth.

### Holdout and Contamination Control
- **D-12:** Split by logical sibling group, never individual PDF, before optimization. For each document type, hold out the valid-control sibling pair plus one deterministic hashed defective sibling pair; all remaining pairs are training.
- **D-13:** Optimizer agents receive only training Judge findings. Holdout ground truth, Judge rationales, scores, and failure labels remain sealed until candidate evaluation completes.
- **D-14:** Baseline and final evaluation cover all 236 cases. Each optimization iteration reruns failed training cases plus all holdout cases; a final full pass confirms global metrics.

### Genuine Self-Improvement
- **D-15:** Run one Gemini 3.6 Flash long-context optimizer agent per document type to propose changes only to that document type's skill. A separate Gemini optimizer may propose shared `AGENTS.md` / `skills/pdf/SKILL.md` changes from aggregated training findings.
- **D-16:** Optimizers write candidate files/diffs only inside isolated proposal directories. They never edit shared source directly and never read another document type's ground truth.
- **D-17:** Candidate review bundles are evaluated without modifying source. Apply a candidate only when targeted training metrics improve and no holdout dimension regresses. Rejected candidates leave source unchanged and retain evidence.
- **D-18:** Accepted patches are allowlisted, bounded, publish-safe, grounding-safe, and committed atomically. No patch may add literal fixture labels, case IDs, ground-truth paths, synthetic applicant values, ungrounded immigration rules, or weaken PII/abstention contracts.
- **D-19:** Run at most three iterations and stop on perfect scores, no actionable training failures, no accepted non-regressing patch, provider quota blocker, or convergence. A perfect baseline requires no artificial patch.

### Pipeline Isolation and Artifacts
- **D-20:** Store Worker/Judge/optimizer artifacts beneath each document pipeline and iteration, but never stage those directories to Workers. Shared aggregate reports contain no synthetic applicant facts.
- **D-21:** Ordinary tests use injected non-live runners and temporary roots. Explicit live gates never seed outputs and reject injected, cached-without-hash, deterministic, missing, partial, or stale artifacts.
- **D-22:** Phase completion requires truthful live provenance for all executed roles, complete baseline/final metrics, sealed-holdout evidence, accepted/rejected patch audit trails, no grounding/PII/blindness regression, and no unresolved high-severity Judge finding.

### the agent's Discretion
- Bounded concurrency, exact JSON schema names, and iteration targeting are implementation details, provided all privilege, holdout, real-agent, and acceptance gates remain enforceable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone and Model Contracts
- `.planning/PROJECT.md` - Truthful Copilot roles and Opus Judge decision.
- `.planning/REQUIREMENTS.md` - `ISOLATED_PIPELINE-01`, `JUDGE_IMPROVE-01`, `REAL_AGENT_EXECUTION-01`.
- `.planning/ROADMAP.md` - Phase 74 goal and success criteria.
- `AGENTS.md` - Grounding, PII partition, AnswerObject, and tool contracts.
- `skills/document-agents/_contract.md` - Canonical Worker review contract.
- `skills/document-agents/` - Per-document public review rules.
- `skills/pdf/SKILL.md` - Shared PDF review behavior and allowed shared patch target.

### Privileged Inputs and Staging
- `.planning/phases/73-blind-synthetic-document-generation-gemini-3-6-flash-long-co/73-CONTEXT.md` - Blindness and side-channel contract.
- `.planning/phases/73-blind-synthetic-document-generation-gemini-3-6-flash-long-co/73-SECURITY.md` - Staging and leakage threat mitigations.
- `crawler/synthetic/staging.py` - Only allowed Worker input seam.
- `crawler/eval/pipelines/*/research/research.json` - Judge-only research input.
- `crawler/eval/pipelines/*/ground_truth/` - Judge-only case mapping and PDF store.

### Existing Fake/Partial Paths to Replace
- `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-REVIEW.md` - Original truthful-execution audit and deferred Worker/Judge/optimizer findings.
- `crawler/eval/pipeline_worker.py` - Prompt-only blindness, repository cwd, unrestricted permissions, and success-shaped fallback to remove.
- `crawler/eval/pipeline_judge.py` - Per-case Judge with deterministic score fallback and hardcoded executable path to replace.
- `crawler/eval/real_worker.py` - Live call pattern but repository access and plain-text parsing are insufficient for this phase.
- `crawler/eval/real_judge.py` - Partial live Judge schema/validation pattern; lacks required Phase 74 batching/isolation/long-context contract.
- `crawler/eval/genuine_optimizer.py` - Hardcoded canned patcher that must become real agent-driven candidate optimization.
- `crawler/eval/agent_improvement_loop.py`, `crawler/eval/benchmark_runner.py`, `crawler/eval/self_optimizer.py` - Ground-truth-derived fake Worker/optimization paths that cannot satisfy live gates.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 72/73 Copilot runners provide portable executable discovery, JSONL filtering, truthful live/injected provenance, prompt/output hashes, temporary-root tests, and fail-closed stale cleanup.
- `stage_case_for_worker` provides the validated Worker filesystem boundary.
- Phase 73 private manifests provide logical sibling groups, expected verdicts, failure IDs, and artifact hashes for Judge-only use.
- Existing AnswerObject and Judge schema validators can be hardened rather than replaced wholesale.

### Established Patterns
- Live success requires model/process/tool provenance and an explicitly enabled conformance gate.
- Raw prompts, reasoning, JSONL, absolute paths, and secrets are never persisted.
- Deterministic Python validates and aggregates; it does not impersonate LLM semantic work.

### Integration Points
- Replace `pipeline_worker.py`, `pipeline_judge.py`, and `genuine_optimizer.py`.
- Build public review bundles before case staging.
- Keep per-document candidate skill patches isolated until train/holdout acceptance.
- Phase 75 consumes Phase 74 baseline/final metrics and patch audit trails for root reporting.

</code_context>

<specifics>
## Specific Ideas

- 236 Worker sessions per full pass; 23 batched Judge sessions per full pass.
- Claude Opus 4.8 with xhigh reasoning and long context is mandatory for every Judge session.
- Holdout selection keeps sibling variants together and seals the only valid-control pair plus one defective pair per document type from optimizer feedback.
- Report agents may know the normal upload-slot document type and public review rules, but no failure-specific source or side channel.

</specifics>

<deferred>
## Deferred Ideas

- GPT 5.6 SOL XHIGH cross-phase orchestration, final release gate handling, and root `TEST_REPORT.md` export - Phase 75.

</deferred>

---

*Phase: 74-blind-report-generator-judge-self-improvement-loop*
*Context gathered: 2026-07-23*
