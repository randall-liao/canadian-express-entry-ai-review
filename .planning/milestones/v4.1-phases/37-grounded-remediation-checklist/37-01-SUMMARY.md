---
phase: 37-grounded-remediation-checklist
plan: 01
subsystem: api
tags: [crs, remediation, projection, deterministic, pii-boundary, screening, unittest]

# Dependency graph
requires:
  - phase: 32-crs-auditor
    provides: "PrivateAuditReport / PrivateFactorCard two-tier models + SCREENING_NOTICE + _reject_absolute_path"
  - phase: 35-coverage-completion
    provides: "PrivateFactorCard.points_unresolved (unpriced-SUBSTANTIATED flag)"
  - phase: 31-crs-rule-registry
    provides: "load_registry + RuleRow.citations[].quote (already-grounded verbatim spans) + no_inlined_volatile_rules gate"
provides:
  - "crawler/remediation.py — two-tier remediation models + pure build_remediation projection + deterministic action templates + vault-only render carrying the SCREENING_NOTICE"
  - "RemediationError fail-closed on registry drift (a cited id with no current quote)"
affects: [37-02-remediate-cli, 37-03-projection-conformance, phase-38-review-packet]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure projection (no id/timestamp/IO) so same report+registry in -> identical checklist out; id/timestamp live only in the run wrapper"
    - "Verbatim rule span reused from the static PII-free registry (no re-ground via searchindex/grounding)"
    - "Action templates keyed by reason (+ per-finding-kind fallback), parameterized by factor, with zero volatile literal (no-inlined gate clean)"

key-files:
  created:
    - crawler/remediation.py
    - crawler/tests/test_remediation.py
  modified: []

key-decisions:
  - "One item per unresolved finding: verdict in {GAP, AT-RISK} OR (SUBSTANTIATED AND points_unresolved); priced-SUBSTANTIATED and N/A produce none (mutually-exclusive by verdict, so an AT-RISK+unpriced card is ONE at_risk item)"
  - "A chunk may be cited with different verbatim quotes by different rules; _quote_map picks a real grounded quote for the chunk from the factor's consumed rows deterministically (registry order + setdefault); the retrieve-what-you-cite test asserts the (id,quote) pair exists in SOME registry citation"
  - "build_remediation fails closed (RemediationError registry_drift) if a cited id has no current quote — never emits an ungrounded/invented line"
  - "SCREENING_NOTICE imported from audit_report (never forked); JSON is data, the MD carries the notice (matches the audit-report precedent)"

patterns-established:
  - "Export layers over the audit are pure projections of the stored PrivateAuditReport + static registry — never a second trust path"
---

# Phase 37 Plan 01 — Summary

## What shipped
- `crawler/remediation.py`: `RemediationCitation` / `PrivateRemediationItem` /
  `PrivateRemediationChecklist` (PII-bearing) + `PublicRemediationSummary` (PII-light); a PURE
  `build_remediation(report, registry)` projecting one grounded item per unresolved finding; deterministic
  `_ACTION_TEMPLATES` + per-finding-kind fallback; `to_public_summary`; and `render_remediation_markdown`
  carrying the imported `SCREENING_NOTICE`.
- `crawler/tests/test_remediation.py`: 8 tests (projection count, finding kinds, item fields,
  retrieve-what-you-cite, determinism, PII-light summary, fail-closed-on-drift, screening notice).

## Requirements satisfied (partial — CLI/vault write in 37-02)
- **REM-01/02**: one actionable, corpus-cited item per GAP/AT-RISK/unpriced finding, each with factor,
  verdict/reason, score impact, citation + verbatim quote, and a deterministic action.
- **REM-03**: pure deterministic projection; no re-score/re-ground; no `searchindex`/`grounding` import;
  no inlined volatile literal (self-scan clean).

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_remediation.py -q` → 8 passed.
- `no_inlined_volatile_rules([crawler/remediation.py])` → `[]`; AST import walk → no searchindex/grounding.

## Deviations
None. Incorporated the plan-checker's fail-closed-on-drift policy. Corrected the retrieve-what-you-cite
assertion to accept any real (chunk_id, quote) registry pair (a chunk is legitimately cited with different
verbatim spans by different rules).
