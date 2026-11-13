# Phase 72: Per-Document Research Agents (Gemini 3.6 Flash long context) - Context

**Gathered:** 2026-07-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 72 produces evidence-rich research artifacts for all 23 Express Entry document types. Each document type is owned by one dedicated Gemini 3.6 Flash long-context research agent and written to its own isolated pipeline directory. This phase stops at research: synthetic document generation, blind worker execution, judge evaluation, self-improvement, and root report export belong to Phases 73-75.

</domain>

<decisions>
## Implementation Decisions

### Per-Document Research Topology
- **D-01:** Launch exactly one dedicated research agent for each `ExpressEntryDocType`; agents must not combine document types or read another document type's pipeline.
- **D-02:** Every research agent uses `gemini-3.6-flash` with `long_context`. GPT 5.6 SOL XHIGH remains the top-level orchestrator, not a replacement for the per-document researchers.
- **D-03:** Agents may execute concurrently, but each writes only beneath `crawler/eval/pipelines/<doc_type>/research/`.

### Evidence and Source Contract
- **D-04:** Online sources may discover recurring failure patterns, refusal examples, and PFL triggers, but policy requirements must be verified against authoritative IRCC/Justice Laws sources and the local corpus before being represented as requirements.
- **D-05:** Each failure mode records a stable ID, category, severity, affected fields/evidence, source URL, retrieval date, exact supporting excerpt, authority classification, and remediation hypothesis.
- **D-06:** Anecdotal or third-party observations must be labeled as discovery evidence and kept distinct from authoritative policy evidence. Unsupported policy claims fail closed rather than being inferred.

### Isolation and Downstream Artifact Boundary
- **D-07:** Research artifacts are privileged inputs for the synthetic generator and final Judge only. They must never be copied into blind PDFs, opaque filenames, worker prompts, extracted text, worker working directories, or worker-visible metadata.
- **D-08:** Research output uses a machine-readable schema plus a human-readable summary per document type so Phase 73 can generate fixtures deterministically without leaking defect labels to report-generating agents.
- **D-09:** Pipeline isolation is structural, not prompt-only: later worker processes receive a staged blind input directory that contains only the PDF and allowed extracted text.

### Failure and Completion Semantics
- **D-10:** Live research failure, malformed output, missing citations, or insufficient coverage is an explicit failed/blocked document pipeline. Generic fallback findings must not masquerade as successful online research.
- **D-11:** Phase completion requires all 23 research reports to pass schema, source, citation, uniqueness, and cross-pipeline isolation validation.

### Real GitHub Copilot Agent Execution
- **D-12:** Every role described as an agent must execute through a real GitHub Copilot CLI agent session. Python code may schedule agents, stage inputs, validate outputs, and aggregate metrics, but it must not synthesize the researcher, generator, worker, Judge, optimizer, or orchestrator's reasoning/report output.
- **D-13:** Production paths must never inspect ground truth to fabricate worker reports, emit deterministic Judge scores under an LLM model label, append canned optimizer patches, or convert a failed Copilot call into success-shaped output.
- **D-14:** Test doubles are permitted only through explicit dependency injection in tests. Production execution metadata must record the actual Copilot command, model, effort/context settings, exit status, and artifact provenance.

### the agent's Discretion
- Query wording, bounded concurrency, retry timing, and the exact JSON field names are implementation details, provided they preserve the locked model, evidence, fail-closed, and isolation contracts above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone Scope and Safety
- `.planning/milestones/v12.0-REQUIREMENTS.md` - Locks the 23-agent research coverage, model assignments, blind isolation, Judge, orchestrator, and root-report requirements.
- `.planning/milestones/v12.0-ROADMAP.md` - Defines the Phase 72-75 delivery sequence.
- `.planning/ROADMAP.md` - Canonical phase registry and dependency order.
- `.planning/PROJECT.md` - Core grounding, PII containment, CLI portability, and autonomous GSD decisions.
- `AGENTS.md` - Canonical fail-closed grounding, PII partition, and deterministic tool contracts.

### Existing Research and Document Contracts
- `crawler/synthetic/schemas.py` - Canonical 23-value `ExpressEntryDocType` inventory.
- `skills/document-agents/_contract.md` - Search, citation resolution, AnswerObject, and fail-closed grounding contract.
- `skills/document-agents/README.md` - Document-agent inventory and authoritative corpus references.
- `skills/document-agents/` - Per-document rules and established corpus queries that research agents must map to their assigned type.

### Existing Evaluation Assets
- `crawler/eval/doc_researcher.py` - Partial research runner to replace or harden; currently serializes all types and contains success-shaped generic fallback research.
- `crawler/eval/doc_synthetic_generator.py` - Downstream consumer that establishes the current research-to-generation seam.
- `crawler/eval/pipeline_worker.py` - Blind worker seam whose future staged input must exclude Phase 72 artifacts.
- `crawler/eval/pipeline_judge.py` - Privileged downstream consumer allowed to read research and ground truth.
- `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-REVIEW.md` - Deep truthful-execution audit identifying hardcoded fallbacks, answer-key leaks, false model metadata, and prompt-only worker isolation.
- `.planning/phases/48-synthetic-data-generation-agent-self-improvement-loop/48-CONTEXT.md` - Prior decision covering all 22 e-APR document types plus Letter of Explanation and vector/scanned fixture parity.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ExpressEntryDocType`: provides the exact 23-document work queue and stable pipeline keys.
- `skills/document-agents/`: provides one grounded rule contract per document type for authoritative-source cross-checking.
- `crawler/eval/pipelines/<doc_type>/`: existing directory convention can become the enforced per-document artifact boundary.

### Established Patterns
- Existing synthetic fixtures pair vector PDFs with 300 DPI scanned siblings and keep JSON ground truth separate.
- Existing review agents use the five-field AnswerObject and local-corpus citation resolution.
- Existing evaluation code invokes live Copilot models and records execution metadata, but success-shaped deterministic fallbacks must be removed for this phase.
- Existing tests often validate simulated reports derived from ground truth; replacement tests must verify the Copilot runner contract and fail-closed production behavior instead.

### Integration Points
- Harden or replace `crawler/eval/doc_researcher.py` with a per-document agent runner and validated research schema.
- Feed only validated research manifests into `crawler/eval/doc_synthetic_generator.py` in Phase 73.
- Preserve research access for `crawler/eval/pipeline_judge.py` while ensuring `crawler/eval/pipeline_worker.py` cannot resolve the research path in Phase 74.

</code_context>

<specifics>
## Specific Ideas

- One independent pipeline per document type so agents cannot interfere with each other.
- Gemini 3.6 Flash long context is the default subagent model unless a later phase explicitly assigns the GPT 5.6 SOL XHIGH orchestrator or final Judge role.
- The future report-generating worker must not infer defects from research reports, ground truth, paths, filenames, case labels, or other side channels.
- All model-backed roles run through GitHub Copilot CLI; a local deterministic implementation cannot be reported as Gemini, GPT, Claude, or an agent.

</specifics>

<deferred>
## Deferred Ideas

- Research-driven vector and scanned defective PDF generation - Phase 73.
- Blind report generation, privileged Judge evaluation, and prompt/skill self-improvement - Phase 74.
- End-to-end GPT 5.6 SOL XHIGH orchestration and root `TEST_REPORT.md` export - Phase 75.

</deferred>

---

*Phase: 72-per-document-research-agents-gemini-3-6-flash-long-context*
*Context gathered: 2026-07-22*
