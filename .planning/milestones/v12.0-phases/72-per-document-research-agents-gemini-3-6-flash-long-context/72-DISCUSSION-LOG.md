# Phase 72: Per-Document Research Agents (Gemini 3.6 Flash long context) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-07-22
**Phase:** 72-per-document-research-agents-gemini-3-6-flash-long-context
**Areas discussed:** Research topology, evidence contract, isolation boundary, failure semantics

---

## Research Topology

| Option | Description | Selected |
|--------|-------------|----------|
| One Gemini long-context agent per document type | Independent ownership and output directory for each of the 23 types | yes |
| Shared agents by document category | Fewer agents, but mixes contexts and weakens isolation | |
| One monolithic researcher | Lowest orchestration overhead, highest interference risk | |

**User's choice:** Auto-selected the requested one-agent-per-document topology.
**Notes:** GPT 5.6 SOL XHIGH remains the orchestrator; per-document research defaults to Gemini 3.6 Flash long context.

---

## Evidence Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Discovery plus authoritative verification | Online examples discover patterns; official sources and local corpus ground policy claims | yes |
| Unrestricted web synthesis | Broad coverage without fail-closed policy verification | |
| Local corpus only | Reproducible but does not satisfy the requested online failure-case research | |

**User's choice:** Auto-selected discovery plus authoritative verification.
**Notes:** Third-party material remains labeled discovery evidence and cannot become an immigration requirement without authoritative support.

---

## Isolation Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Structural staged-input isolation | Workers later receive only blind PDF and allowed extracted text in a separate working directory | yes |
| Prompt-only isolation | Tell workers not to read privileged files while leaving them reachable | |
| Shared pipeline workspace | Simplest layout but leaks research and ground truth through paths and files | |

**User's choice:** Auto-selected structural staged-input isolation.
**Notes:** Research is available only to the synthetic generator and final Judge.

---

## Failure Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed per document type | Retry boundedly, then mark the pipeline blocked with diagnostics | yes |
| Generic fallback research | Produce plausible findings when live research fails | |
| Skip failed types | Finish with partial document coverage | |

**User's choice:** Auto-selected fail-closed completion.
**Notes:** All 23 validated reports are required before Phase 72 can complete.

---

## the agent's Discretion

- Query phrasing, bounded concurrency, retry timing, and exact schema field names.

## Deferred Ideas

- Synthetic generation, blind worker/Judge execution, self-improvement, and root report export remain in Phases 73-75.
