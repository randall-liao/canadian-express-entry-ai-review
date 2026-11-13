# Phase 74: Blind Report Generator & Judge Self-Improvement Loop - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md.

**Date:** 2026-07-23
**Areas discussed:** Worker isolation, Judge batching/model, holdout control, optimizer patch acceptance

## Worker Isolation

| Option | Description | Selected |
|--------|-------------|----------|
| One staged case per Gemini session | 236 sessions; no cross-case history or privileged filesystem | yes |
| One batch per document type | Fewer calls but cross-case inference risk | |
| Repository-root Worker | Exposes research and ground truth | |

**Choice:** Auto-selected one isolated Worker per PDF.

## Privileged Judge

| Option | Description | Selected |
|--------|-------------|----------|
| One Opus batch per document type | 23 xhigh long-context Judge sessions per pass | yes |
| One Judge per PDF | 236 costly privileged calls | |
| Deterministic Python Judge | Not an LLM Judge and can fake scores | |

**Choice:** Auto-selected Claude Opus 4.8 xhigh long-context document-type batches.

## Holdout Control

| Option | Description | Selected |
|--------|-------------|----------|
| Sealed sibling-group holdout | Valid pair + one defect pair per type hidden from optimizer | yes |
| Random PDFs | Sibling leakage across train/holdout | |
| No holdout | Encourages fixture memorization | |

**Choice:** Auto-selected sealed logical-pair holdouts.

## Patch Acceptance

| Option | Description | Selected |
|--------|-------------|----------|
| Candidate sandbox then metric gate | Apply only train improvement with zero holdout regression | yes |
| Optimizer edits source directly | Cross-pipeline conflicts and no rollback evidence | |
| Hardcoded canned patches | Not genuine optimization | |

**Choice:** Auto-selected candidate-only evaluation and bounded atomic acceptance.

## the agent's Discretion

- Concurrency, JSON field names, and targeted rerun scheduling.

## Deferred Ideas

- Root report and final cross-phase orchestration remain Phase 75.
