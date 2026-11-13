---
phase: 75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex
plan: 01
subsystem: release-evaluation
tags: [copilot-sdk, gpt-5.6-sol, pii-safe-evidence, deterministic-report]
dependency_graph:
  requires: [PHASE74_COMMITTED_EVIDENCE]
  provides: [RELEASE_EVIDENCE_SCHEMA, LIVE_RELEASE_ASSESSMENT, TEST_REPORT_RENDERER]
  affects: [phase-75, TEST_REPORT.md, final-audits]
tech_stack:
  added: []
  patterns:
    - strict extra-forbid Pydantic aggregate schemas
    - complete release-evidence hash binding
    - official SDK no-tools orchestrator session
    - independently validated atomic public evidence
key_files:
  created:
    - crawler/eval/release_orchestrator.py
    - crawler/eval/test_report.py
    - crawler/tests/test_phase75_release.py
  modified: []
decisions:
  - GPT-5.6 Sol receives only validated PII-free aggregates and cannot author measured facts.
  - TEST_REPORT tables render deterministically from evidence; model prose remains labeled and subordinate.
  - Phase 75 persists the exact validated release evidence, raw sanitized assessment JSON, SDK provenance, report hash, and cross-linked manifest.
metrics:
  duration: "implemented during Phase 74 live execution"
  completed_date: "2026-07-27"
---

# Phase 75 Plan 01: SDK Release Orchestrator Summary

## Executive Summary

Implemented the official-SDK GPT-5.6 Sol release assessment and deterministic
root report renderer. The release model is bound to a canonical hash of strict,
PII-free Phase 72-74 aggregates and cannot modify counts, hashes, scores,
commands, model assignments, or statuses.

## Key Changes

1. **Release evidence and loader**
   - Requires the exact 23 `ExpressEntryDocType` values, 236 Workers, 23 Judges,
     23 optimizers, 23 shared evaluations, peak concurrency five, zero imports,
     and clean terminal lifecycle evidence.
   - Calls `validate_committed_phase74_evidence` before reading aggregate files.
   - Recomputes baseline/final metrics, deltas, patch counts, and blockers.

2. **Live SDK assessment**
   - Uses role `orchestrator`, model `gpt-5.6-sol`, `xhigh`,
     `long_context`, no attachments/tools, and a 900-second bound.
   - Strictly validates the assessment and exact Phase 74/run/release-evidence
     bindings.
   - Rejects private fields, absolute paths, identifiers, emails, and known
     synthetic identities recursively.

3. **Deterministic report and evidence**
   - Renders all measured tables without model-authored values.
   - Atomically persists `release_evidence.json`, `assessment.json`,
     `manifest.json`, and root report bytes.
   - Independently revalidates self-hashes, raw SDK response/output hash,
     prompt hash, provenance, deterministic rendering, and file inventory.

## Verification Results

- `crawler/tests/test_phase75_release.py`: **24 passed**.
- Phase 75 release plus SDK lifecycle tests: **94 passed**.
- Fresh Phase 74 evidence loader:
  - 23 documents
  - 236 Workers
  - 23 Judges
  - 23 optimizers
  - 11 cumulative accepted patches
  - 23 final rejected patches
  - 0 imported model artifacts
- Two read-only adversarial design reviews found no remaining high-confidence
  blocker after scanner and evidence-binding fixes.

## Commit

- `5662163` - `feat(75): add SDK release orchestrator`

## Self-Check: PASSED

- FOUND: `crawler/eval/release_orchestrator.py`
- FOUND: `crawler/eval/test_report.py`
- FOUND: `crawler/tests/test_phase75_release.py`
- FOUND: exact GPT model/effort/context assertions
- FOUND: independently validated release artifact persistence
