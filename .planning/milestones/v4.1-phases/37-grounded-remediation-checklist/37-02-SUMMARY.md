---
phase: 37-grounded-remediation-checklist
plan: 02
subsystem: cli
tags: [crs, remediation, cli, vault, fail-closed, publish-safe, pii-boundary, unittest]

# Dependency graph
requires:
  - phase: 37-grounded-remediation-checklist
    plan: 01
    provides: "build_remediation projection + two-tier models + RemediationError + render"
  - phase: 32-crs-auditor
    provides: "audit_runs trail (report_relpath) + _vault_relative + resolve_within write pattern"
provides:
  - "vault.new_remediation_id + vault.latest_completed_audit_run selectors"
  - "remediation.run_remediation writer (load completed report -> build -> vault-only write -> PII-light summary)"
  - "vault remediate CLI verb with fail-closed refusals (no_completed_audit / audit_run_not_found / audit_report_unreadable / registry_drift)"
  - "output/remediation/ registered in the publish-safe VAULT_SUBTREES allow-list"
affects: [37-03-projection-conformance, phase-38-review-packet, phase-39-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "report_relpath resolves under vault.root.parent.parent (personal root) — the exact inverse of _vault_relative — not vault.root"
    - "build-before-write ordering: a prerequisite failure leaves zero artifacts"
    - "RemediationError reason token -> frozen invalid_input/exit-2 refusal + PII-free recovery hint"

key-files:
  created:
    - crawler/tests/test_remediation_cli.py
  modified:
    - crawler/vault.py
    - crawler/remediation.py
    - crawler/cli.py
    - scripts/check_publish_safe.py

key-decisions:
  - "vault remediate takes NO --db: remediation projects the already-grounded report + static registry and never touches the corpus index (no re-grounding)"
  - "_load_report anchors report_relpath at vault.root.parent.parent (BLOCKER fix from plan-check); a missing/unreadable/invalid report -> RemediationError(audit_report_unreadable), zero artifacts"
  - "CLI test uses a SYNTHETIC completed audit run written directly under the vault so the whole path (load + write + refusals) runs UNGUARDED — no corpus needed"

patterns-established:
  - "Every corpus-report-derived verb resolves the stored report via vault.root.parent.parent + resolve_within and fails closed on a bad report"
---

# Phase 37 Plan 02 — Summary

## What shipped
- `crawler/vault.py`: `new_remediation_id()` (`rem_` prefix) + `latest_completed_audit_run()` selector.
- `crawler/remediation.py`: `_load_report` (anchors at the personal root, fail-closed) + `run_remediation`
  (build-before-write, vault-only JSON+MD under `output/remediation/`, PII-light summary).
- `crawler/cli.py`: `_cmd_vault_remediate` + the `remediate` sub-subparser + metavar/help update; fail-closed
  refusals mapped from `RemediationError` reason tokens to `invalid_input`/exit-2 with recovery hints.
- `scripts/check_publish_safe.py`: `output/remediation/` added to `VAULT_SUBTREES`.
- `crawler/tests/test_remediation_cli.py`: unguarded happy path + specific-run-id + three refusal cases.

## Requirement satisfied
- **REM-04**: the full checklist + `ev_` pointers stay vault-only (`output/remediation/`); stdout is a
  PII-light `PublicRemediationSummary`; every rendered artifact carries the screening notice; a missing /
  unreadable prerequisite refuses cleanly (`invalid_input`/exit 2 + reason code) with zero artifacts.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_remediation_cli.py crawler/tests/test_vault_cli.py scripts/tests/test_check_publish_safe.py -q` → 51 passed, 25 subtests.
- `.venv/bin/python scripts/check_publish_safe.py` → 0 violations (333 tracked files).
- Live: `vault remediate` after a real `vault audit --all` writes 9 items vault-only, PII-light stdout,
  vault-relative path; `vault remediate` with no audit → `reason=no_completed_audit`, exit 2, zero artifacts.

## Deviations
None. Implemented the plan-checker's BLOCKER fix (`vault.root.parent.parent` anchor) and the unguarded
synthetic-report test approach.
