---
phase: 75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex
plan: 02
subsystem: root-agent-onboarding
tags: [agents-md, copilot, natural-language-routing, pii-containment, onboarding]
dependency_graph:
  requires: [CANONICAL_AGENTS_MD, FOUR_STAGE_REVIEW_WORKFLOW]
  provides: [ROOT_REVIEW_INTENT, READY_TO_USE_ONBOARDING]
  affects: [READY_USE-01, README.md, final-integration-audit]
tech_stack:
  added: []
  patterns:
    - natural-language intent routes to existing deterministic commands
    - extraction remains confirm-first and non-grounded
    - public conversation remains PII-light
key_files:
  created:
    - crawler/tests/test_root_agent_workflow.py
  modified:
    - AGENTS.md
    - README.md
decisions:
  - Root review requests activate the Lead Review Coordinator rather than a second public command.
  - The agent asks only for missing local path/document type facts and never prints vault PII.
  - Poetry/Python 3.11 and the pinned Copilot SDK runtime are the primary setup path.
metrics:
  duration: "~15m"
  completed_date: "2026-07-27"
---

# Phase 75 Plan 02: Root Natural-Language Review Workflow Summary

## Executive Summary

Made the repository-root product workflow explicit: a user can start Copilot,
say "I want to review X," and be routed through local vault ingestion,
confirm-first extraction, corpus-grounded review/screening, remediation, and
redacted export.

## Key Changes

1. **Canonical root routing**
   - Added review intent examples to `AGENTS.md`.
   - Requires local path and canonical document type resolution.
   - Preserves global-before-subcommand `corpus-crawler --json` syntax and
     standard envelope handling.
   - Keeps vault PII, raw content, personal values, and private paths out of
     public claims/stdout.
   - Requires `not_in_corpus` abstention rather than guessed policy.

2. **Ready-to-use onboarding**
   - Corrected the supported runtime to Python 3.11.
   - Documented Poetry extras for extraction/OCR and the Tesseract OS package.
   - Documented pinned Copilot runtime download, `doctor`, root `copilot`
     startup, and a literal passport-review request.

3. **Contract tests**
   - Assert natural-language routing, all four stages, field confirmation,
     grounding/abstention, PII containment, remediation/export, and onboarding.

## Verification Results

- Root workflow contract: **4 passed**.
- Phase 75 release plus root workflow: **28 passed**.
- `corpus-crawler --json doctor`: `ok: true`, `overall: ok`; all required
  document extraction dependencies present. The environment lacks only the
  optional Tesseract binary, now documented explicitly.
- Publish safety: **1,583 tracked files, 0 violations**.

## Commit

- `7264ff2` - `docs(75): make root review workflow operational`

## Self-Check: PASSED

- FOUND: root `AGENTS.md` intent entrypoint
- FOUND: literal "I want to review" README example
- FOUND: all four local workflow stages
- FOUND: confirm-first extraction and fail-closed abstention rules
- FOUND: ready-to-use Poetry/Copilot/doctor setup
