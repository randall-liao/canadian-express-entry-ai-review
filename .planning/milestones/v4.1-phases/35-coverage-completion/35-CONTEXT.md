# Phase 35: Coverage Completion - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via `workflow.skip_discuss`)

<domain>
## Phase Boundary

Complete grounded first-official-language point coverage for every supported benchmark and make the already-grounded sibling factor reachable through confirmed, claimed-scoped evidence. Do not expand into new policy domains, relax verdict rules, or create a second trust path.

</domain>

<decisions>
## Implementation Decisions

### Locked Decisions

- Preserve the frozen `search` -> `--cite` -> grounding gate -> JSON envelope path.
- Close language-point coverage with corpus-grounded registry data; never fabricate a point value or relax a decider.
- Surface any still-unpriced substantiated factor as unresolved.
- Close sibling support on the extraction/evidence side with pending-first, field-level confirmation and claimed-scoped linkage.
- Keep sibling evidence fields in one shared vocabulary and pin producer/consumer agreement to prevent drift.
- Preserve vault-only PII storage, `ev_` evidence/corpus citation namespace separation, and screening-not-legal-advice framing.

### Agent Discretion

All remaining implementation choices are at the agent's discretion. Prefer existing registry, extraction, vocabulary, migration, and real-seam test patterns. Add no runtime dependency.

</decisions>

<code_context>
## Existing Code Insights

- Higher-CLB point completion should extend the existing grounded CRS rule rows and generalized scoring readers.
- Sibling evidence should mirror the shared-vocabulary and extraction-side gap-closure patterns established by Phase 30.
- Phase verification must exercise the real import -> extract -> confirm -> audit seam and prove no cross-factor contamination.

</code_context>

<specifics>
## Specific Ideas

- Pin the set of supported first-language benchmark outputs to grounded point rows.
- Keep ambiguous, missing, stale, rejected, or low-quality sibling evidence fail-closed.

</specifics>

<deferred>
## Deferred Ideas

Legacy arranged-employment resolution, live DLI/PGWP lookup, NOC-duty semantic review, MEC sidecars, and model-based semantic relationship inference remain out of scope.

</deferred>
