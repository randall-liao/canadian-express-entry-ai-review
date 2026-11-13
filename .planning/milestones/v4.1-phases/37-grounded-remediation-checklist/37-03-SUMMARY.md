---
phase: 37-grounded-remediation-checklist
plan: 03
subsystem: testing
tags: [crs, remediation, conformance, no-inlined, retrieve-what-you-cite, determinism, unittest]

# Dependency graph
requires:
  - phase: 37-grounded-remediation-checklist
    plan: 01
    provides: "build_remediation + _quote_map"
  - phase: 31-crs-rule-registry
    provides: "no_inlined_volatile_rules gate + load_registry"
provides:
  - "no-inlined-volatile-rules gate now scans crawler/remediation.py (and forward-guards crawler/review_packet.py)"
  - "test_remediation_projection.py — AST no-import + call-level trust-path guard + retrieve-what-you-cite + determinism + unpriced-invariant"
affects: [phase-38-review-packet, phase-39-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "No-second-trust-path proven two ways: AST import walk (ignores docstrings) + call-level monkeypatch guard (booby-trap grounding/searchindex, assert build still succeeds)"
    - "Retrieve-what-you-cite for a projection: every emitted (citation_id, quote) pair exists in a real registry citation"

key-files:
  created:
    - crawler/tests/test_remediation_projection.py
  modified:
    - crawler/tests/test_crs_no_inlined_rules.py

key-decisions:
  - "SAFE-07 is a Phase-39 requirement; this conformance test is the forward-guard, not the SAFE-07 sign-off"
  - "AST import check (not text grep) so the module's legitimate 'grounding'/'re-grounding' docstrings do not false-fail"
  - "Call-level guard proves runtime non-use of the trust path even though importing crs_rules pulls grounding/searchindex into sys.modules (benign presence != use)"

patterns-established:
  - "Export layers are proven single-trust-path by AST-import + call-level guard, and retrieve-what-you-cite against the real registry"
---

# Phase 37 Plan 03 — Summary

## What shipped
- `crawler/tests/test_crs_no_inlined_rules.py`: `_registry_and_auditor_surface` now includes
  `crawler/remediation.py` (and forward-guards `crawler/review_packet.py`); the gate returns clean and the
  positive control still bites.
- `crawler/tests/test_remediation_projection.py`: AST no-import + call-level trust-path guard,
  retrieve-what-you-cite against the real registry, determinism, and the unpriced-invariant.

## Requirement satisfied
- **REM-03** (and forward-guards the Phase-39 **SAFE-07**): every requirement-bearing remediation line
  derives from an existing grounded registry rule; remediation is a single-trust-path, deterministic
  projection with no inlined volatile requirement.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_remediation_projection.py crawler/tests/test_crs_no_inlined_rules.py -q` → 10 passed.
- Phase-37 cluster + audit + publish-safe + v4.0 conformance all green.

## Deviations
None. Used the plan-checker's AST + call-level approach (not a naive grep / unsatisfiable sys.modules check).
