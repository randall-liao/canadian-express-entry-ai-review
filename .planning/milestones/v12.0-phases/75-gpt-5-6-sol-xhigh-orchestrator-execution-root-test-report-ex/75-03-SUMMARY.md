---
phase: 75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex
plan: 03
subsystem: release-publication
tags: [gpt-5.6-sol, test-report, committed-evidence, full-suite, publish-safety]
dependency_graph:
  requires: [RELEASE_EVIDENCE_SCHEMA, ROOT_REVIEW_INTENT, PHASE74_COMMITTED_EVIDENCE]
  provides: [TEST_REPORT, PHASE75_COMMITTED_EVIDENCE, LIVE_RELEASE_VERDICT]
  affects: [READY_USE-01, READY_USE-02, final-audits]
tech_stack:
  added: []
  patterns:
    - one live aggregate-only SDK assessment
    - deterministic measured Markdown tables
    - separately bounded duplicate audit
    - exact-head repository validation ledger
key_files:
  created:
    - TEST_REPORT.md
    - crawler/eval/phase75_evidence/release_evidence.json
    - crawler/eval/phase75_evidence/assessment.json
    - crawler/eval/phase75_evidence/manifest.json
  modified:
    - crawler/eval/release_orchestrator.py
    - crawler/eval/test_report.py
    - crawler/tests/test_phase75_release.py
    - crawler/tests/test_agent_improvement_loop.py
    - crawler/tests/test_benchmark_loop.py
decisions:
  - Per-document shared-baseline/final differences are labeled repeatability variance, not patch improvement.
  - Accepted patch training and holdout deltas are published as the authoritative self-improvement metrics.
  - Stale tests for fake legacy agent paths were replaced by fail-closed deprecation contracts.
metrics:
  completed_date: "2026-07-27"
  report_hash: "3ee148b8c5873a82931ea0b94b1ea28a69bc7b03c25509c8cc4d707d4e36ec19"
---

# Phase 75 Plan 03: Live Release Assessment and TEST_REPORT Summary

## Executive Summary

Executed the live GPT-5.6 Sol `xhigh` long-context assessment over validated,
PII-free Phase 72-74 aggregates and published a deterministic root
`TEST_REPORT.md` with independently verifiable Phase 75 evidence.

## Live Assessment

- **Engine:** `copilot-sdk`
- **Model:** `gpt-5.6-sol`
- **Effort/context:** `xhigh` / `long_context`
- **Tools/attachments:** none
- **Live provenance:** true
- **Successful session duration:** 14.84 seconds
- **Verdict:** ready
- **Release evidence hash:**
  `298de720e1f1857751556d188f4f258bb5c9ffe3f89ffbb832eb806a8ecab54d`
- **Phase 75 manifest:**
  `7fd79ca1e8d48e134f2b539e8cbd4303ffa3f58263c50f5f8121a77ec1713355`
- **Report hash:**
  `3ee148b8c5873a82931ea0b94b1ea28a69bc7b03c25509c8cc4d707d4e36ec19`

The first live response passed model/schema/evidence validation but exposed a
local `python -m` duplicate-module `isinstance` bug during rendering. Commit
`4f29ab8` added structural revalidation across equivalent module identities.
No partial report/evidence was published; the final successful call produced
the committed artifacts.

## Report Coverage

- 23 research documents
- 118 logical synthetic cases
- 236 PDFs and final Workers
- 23 final Judges
- 23 optimizers
- 23 shared evaluations
- peak concurrency 5
- zero imported model artifacts
- zero cleanup survivors/errors
- 11 cumulative accepted patch records with exact training/holdout deltas
- final-run 0 accepted / 23 rejected partition
- all 23 per-document rows

## Validation Results

- Phase 74 full suite: **742 passed, 200,371 subtests passed**.
- Strict live Phase 74 gate: **83 passed**.
- Committed evidence tamper suite: **140 passed**.
- Phase 75 targeted tests: **29 passed**.
- Duplicate audit: **1 passed** in 611.77 seconds
  (679.79 seconds wall-clock under a 1,200-second bound).
- Current-head repository suite excluding the separately run duplicate node:
  **2,409 passed, 8 skipped, 1 deselected, 203,795 subtests passed**.
- Publish safety after staging report/evidence:
  **1,588 tracked files, 0 violations**.
- Doctor preflight: `ok: true`, `overall: ok`, all required extraction
  dependencies present; optional OS Tesseract remains documented.
- Independent Phase 75 artifact validator: ready, 23 documents, 236 Workers,
  23 Judges, exact report/evidence/manifest hashes.

## Commits

- `4f29ab8` - close release execution and suite regressions
- `6fbb7a6` - report measured patch deltas
- `37ce70a` - publish measured release report

## Self-Check: PASSED

- FOUND: root `TEST_REPORT.md`
- FOUND: exact 23-document table
- FOUND: all required models and runtime facts
- FOUND: 11 accepted patch delta records
- FOUND: live GPT provenance and raw-response binding
- FOUND: independently validated Phase 75 manifest
- FOUND: zero measured release blockers
