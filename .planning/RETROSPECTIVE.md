# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v5.0 — Grounded Eligibility & Policy Edge-Case Screening

**Shipped:** 2026-07-21  
**Phases:** 7 | **Plans:** 29 | **Sessions:** 1 extended execution thread

### What Was Built

- Shared fail-closed freshness, effectivity, snapshot, grounding, and drift controls.
- Pinned DLI/PGWP evidence plus grounded POLICY, NOC, STUDY, and FSW/FST/CEC MEC sidecars.
- One authoritative SAFE-01..12 gate proving 209 exact release nodes and cross-phase E2E behavior.

### What Worked

- Goal-backward phase verification and exact frozen contracts caught false-green, privacy, and
  persistence regressions before release.
- One immutable registry snapshot and one grounding gate kept every sidecar on the established trust
  path with zero new runtime dependencies.
- Switching final subagents to GPT-5.6 Tera high shortened the release-review/fix loop.

### What Was Inefficient

- STUDY last-known-good persistence required several deep-review iterations because crash ordering,
  journal transition, cleanup, and concurrency were initially reasoned about separately.
- Phase and milestone state metadata lagged implementation and needed manual reconciliation after the
  release gates were already green.

### Patterns Established

- Durable report publication is a serialized state machine: prepared, installed, cleanup-pending,
  with atomic journal replacement and retryable cleanup.
- Release runners must enforce exact module/node manifests, clear inherited filters/plugins, and
  reject skips or deselections in authoritative mode.
- Public identifiers and locators use exact opaque schemas; all evidence remains vault-only.

### Key Lessons

1. Design crash recovery and concurrent readers/writers together before implementing persistence;
   single-process fault injection alone is insufficient.
2. Treat validation, review, and state artifacts as release surfaces because publish-safety and
   milestone tooling consume them directly.
3. Keep volatile immigration facts in pinned local snapshots and use operational freshness
   configuration rather than presenting local policy as an authoritative claim.

### Cost Observations

- Model mix: not measured; final blocker closure and verification used GPT-5.6 Tera high.
- Sessions: one extended milestone-completion thread.
- Notable: deep independent review found four persistence defects after the initial green suite;
  mutation-tested concurrency and crash-boundary tests provided the decisive evidence.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|---|---:|---:|---|
| v5.0 | 1 extended | 7 | Exact release manifests plus deep persistence/concurrency review |

### Cumulative Quality

| Milestone | Release tests | Requirements | Runtime dependencies added |
|---|---:|---:|---:|
| v5.0 | 209 | 18/18 | 0 |

### Top Lessons (Verified Across Milestones)

1. Fail-closed behavior needs both deterministic negative matrices and real cross-phase E2E proof.
2. Frozen public/privacy contracts prevent sidecar expansion from silently changing shipped behavior.
