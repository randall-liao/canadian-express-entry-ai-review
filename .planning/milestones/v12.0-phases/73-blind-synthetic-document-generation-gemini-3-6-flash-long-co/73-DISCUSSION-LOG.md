# Phase 73: Blind Synthetic Document Generation - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md.

**Date:** 2026-07-23
**Phase:** 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co
**Areas discussed:** Agent/render split, coverage, opaque blindness, privileged ground truth, failure semantics

## Agent and Renderer Responsibilities

| Option | Description | Selected |
|--------|-------------|----------|
| Gemini authors specifications; Python renders | Real agent creates content and failures; deterministic code only validates/renders | yes |
| Deterministic templates labeled Gemini | Current behavior; no actual generator agent | |
| Agent writes arbitrary files directly | Weak schema, reproducibility, and path isolation | |

**Choice:** Auto-selected the real-agent specification/render split.

## Coverage and Pairing

| Option | Description | Selected |
|--------|-------------|----------|
| Valid control plus every researched failure mode | 118 logical cases and 236 vector/scanned PDFs | yes |
| Two sample failures per type | Misses researched modes | |
| Fixed 184 legacy fixtures | Forces research coverage loss | |

**Choice:** Auto-selected complete research-mode coverage.

## Blindness Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Opaque IDs plus isolated staging API | No hint-bearing names, paths, metadata, mappings, or privileged files | yes |
| Opaque filenames only | Paths/metadata/order can still leak labels | |
| Prompt-only secrecy | Worker can inspect reachable privileged files | |

**Choice:** Auto-selected structural staging and side-channel scans.

## Failure Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Fail closed per document pipeline | No live agent/spec/render/leakage failure can become success | yes |
| Deterministic fallback cases | Fabricates Gemini work | |
| Partial dataset completion | Breaks cross-document coverage | |

**Choice:** Auto-selected all-23 fail-closed completion.

## the agent's Discretion

- Schema field names, renderer primitives, concurrency cap, and opaque-ID construction.

## Deferred Ideas

- Worker/Judge/self-improvement in Phase 74 and final orchestrator/report in Phase 75.
