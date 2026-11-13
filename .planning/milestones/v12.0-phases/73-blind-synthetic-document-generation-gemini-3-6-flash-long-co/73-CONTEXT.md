# Phase 73: Blind Synthetic Document Generation (Gemini 3.6 Flash long context) - Context

**Gathered:** 2026-07-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 73 converts the 23 validated Phase 72 research reports into realistic blind synthetic documents. One real GitHub Copilot CLI Gemini 3.6 Flash long-context generator agent owns each document type and produces a strict generation specification. Deterministic Python may validate and render that agent-authored specification into vector and 300 DPI scanned PDFs, but it may not select defects, invent document content, or report local templates as Gemini work. Blind worker execution, privileged Judge evaluation, self-improvement, and final orchestration remain in Phases 74-75.

</domain>

<decisions>
## Implementation Decisions

### Genuine Generator Agent Topology
- **D-01:** Launch exactly one real GitHub Copilot CLI generator agent per `ExpressEntryDocType`; each invocation uses `gemini-3.6-flash` with `long_context` and receives only its assigned validated research report plus a strict output schema.
- **D-02:** The Gemini agent generates the document fields, narrative content, layout intent, valid control, and one failed case for every researched failure mode. Python only validates, renders, rasterizes, hashes, and stores those agent-authored specifications.
- **D-03:** The current deterministic `doc_synthetic_generator.py` defect-selection/template path cannot be labeled or counted as agent generation. Production agent failure is blocked; no local fallback may replace it.

### Fixture Coverage and Pairing
- **D-04:** Generate one valid control plus one defective case per Phase 72 failure mode for each document type. The current 95 failure modes produce 118 logical cases and 236 PDF fixtures across 23 pipelines.
- **D-05:** Every logical case produces a native vector PDF and a 300 DPI scanned sibling rasterized from the exact vector bytes. The private manifest links siblings; worker-visible names do not reveal the relationship.
- **D-06:** Each generation specification records its source research failure ID privately so the final Judge can trace coverage, but the blind document and staged worker input contain no failure ID, defect label, expected verdict, or research note.

### Blindness and Side-Channel Elimination
- **D-07:** Use cryptographically opaque, non-sequential case IDs and uniform `<opaque>.pdf` filenames. Filenames, directory names, PDF metadata, titles, bookmarks, attachments, extracted text, and visible content must not contain document type, variant, case class, defect category, PFL labels, research IDs, or expected verdict.
- **D-08:** The defective condition itself remains observable in the document evidence; explanatory annotations such as "defective", "missing field", "expired", or "synthetic test" are prohibited.
- **D-09:** Ground truth, research, generator prompts, JSONL events, generation specifications, provenance, and case mappings are privileged. A staging API must copy only one opaque PDF and its allowed extracted text into a fresh worker directory outside the privileged pipeline tree.
- **D-10:** Blindness is enforced by filesystem/tool capability boundaries and automated leakage scans, not prompt instructions alone.

### Ground Truth and Provenance
- **D-11:** Private ground truth stores the opaque case ID, document type, variant, sibling linkage, expected verdict, injected research failure ID, affected fields, and hashes of the agent specification/vector/scanned bytes.
- **D-12:** Successful generation provenance proves a live Copilot CLI invocation, Gemini model/context, return status, prompt/output hashes, and sanitized command flags. Injected test doubles are explicitly non-live and can write only to temporary test roots.
- **D-13:** Raw prompts, full research reports, absolute executable paths, raw JSONL, assistant reasoning, and secrets are never persisted in public fixtures or provenance.

### Realism, Privacy, and Failure Semantics
- **D-14:** Documents use clearly fictional fixture identities internally while remaining visually realistic; no real applicant PII or candidate-vault data may enter generated artifacts.
- **D-15:** Malformed agent output, missing failure-mode coverage, render failure, metadata leakage, duplicate opaque IDs, or mismatch between vector/scanned siblings blocks the document pipeline and removes stale success artifacts.
- **D-16:** Phase completion requires all 23 live generator invocations, all 118 logical cases, all 236 PDFs, private ground truth, provenance, scan parity, PII checks, and blind leakage conformance to pass.

### the agent's Discretion
- Exact Pydantic field names, renderer layout primitives, bounded concurrency, and opaque-ID derivation are implementation details, provided IDs cannot be inferred and every locked coverage/isolation invariant is testable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone and Prior Phase Contracts
- `.planning/PROJECT.md` - v12 goal, truthful agent rule, grounding, privacy, and model assignments.
- `.planning/REQUIREMENTS.md` - `BLIND_SYNTHETIC-01`, `ISOLATED_PIPELINE-01`, and `REAL_AGENT_EXECUTION-01`.
- `.planning/ROADMAP.md` - Phase 73 goal and success criteria.
- `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-CONTEXT.md` - Privileged research boundary and real-agent decisions.
- `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-REVIEW.md` - Truthful-execution audit and deferred generator finding CR-03.
- `.planning/phases/72-per-document-research-agents-gemini-3-6-flash-long-context/72-SECURITY.md` - Proven Copilot, provenance, path, and prompt-injection mitigations to reuse.

### Validated Inputs
- `crawler/eval/pipelines/*/research/research.json` - The 23 privileged, validated source manifests containing 95 researched failure modes.
- `crawler/eval/doc_researcher.py` - Closest live Copilot JSONL, provenance, fail-closed, and injected-runner pattern.
- `crawler/synthetic/schemas.py` - Canonical 23 document types and existing synthetic dataclasses.

### Existing Rendering Assets
- `crawler/eval/doc_synthetic_generator.py` - Deterministic baseline to replace; currently selects defects and falsely presents local rendering as Gemini generation.
- `crawler/synthetic/generator.py` - Existing PDF rendering primitives and document templates.
- `crawler/synthetic/rasterizer.py` - Required vector-to-300-DPI scanned sibling renderer.
- `crawler/synthetic/defects.py` - Existing defect vocabulary; may validate mappings but cannot choose agent cases in production.
- `crawler/synthetic/generate_test_dataset.py` - Existing vector/scanned pairing pattern and legacy sequential naming to replace.
- `crawler/tests/test_pdf_synthetic.py` - Existing PDF text-layer and scan-quality assertions.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 72 Copilot runner patterns provide portable executable discovery, JSONL parsing, model/tool provenance, explicit test injection, and fail-closed stale-artifact cleanup.
- `generate_synthetic_document` and the template/rasterizer stack can render validated agent specifications without becoming the source of case reasoning.
- `rasterize_pdf_to_scanned_pdf` already produces 300 DPI OCR-required scanned siblings from vector bytes.

### Established Patterns
- Existing fixtures separate PDF files from ground-truth JSON, but current sequential names and `research_notes` leak case meaning.
- Existing deterministic defect maps and ground-truth-derived reviews are prohibited as production agent substitutes.
- Phase 72 tests demonstrate temporary-root injection so ordinary tests cannot seed production artifacts.

### Integration Points
- Replace `crawler/eval/doc_synthetic_generator.py` with the live per-document specification generator, validator, renderer coordinator, privileged manifest writer, and blind staging API.
- Extend rendering primitives only where an agent-authored specification cannot currently be represented.
- Phase 74 consumes only the Phase 73 staging API, while its privileged Judge reads private ground truth and Phase 72 research.

</code_context>

<specifics>
## Specific Ideas

- The 20 document types with four failure modes produce five logical cases each; three types with five failure modes produce six each, totaling 118 logical cases and 236 vector/scanned PDFs.
- A report-generating worker must not infer failure cause from names, paths, ordering, PDF metadata, annotations, or paired-variant suffixes.
- Claude Opus 4.8 with `xhigh` reasoning and `long_context` is reserved for the final Judge in Phase 74.

</specifics>

<deferred>
## Deferred Ideas

- Blind Gemini report generation, Opus 4.8 Judge evaluation, and measured prompt/skill patching - Phase 74.
- GPT 5.6 SOL XHIGH end-to-end orchestration and root `TEST_REPORT.md` export - Phase 75.

</deferred>

---

*Phase: 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co*
*Context gathered: 2026-07-23*
