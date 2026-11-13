---
phase: 39-safe-conformance-release-consolidation
plan: 03
subsystem: testing
tags: [crs, conformance, safe-07, safe-08, release-gate, grounding, determinism, screening, unittest]

requires:
  - phase: 37-grounded-remediation-checklist
    provides: "build_remediation + no-second-trust-path patterns"
  - phase: 38-redacted-professional-review-packet
    provides: "build_packet + render + no-inlined coverage"
provides:
  - "test_conformance_v41_grounding.py (SAFE-07) — rwyc + determinism + no-inlined + no-second-trust-path + screening over remediation + packet"
  - "scripts/run_conformance.py extended to the complete v4.0 + v4.1 flow (SAFE-01..08) via glob test_conformance_v4[01]_*.py"
  - "test_conformance_v41_release_gate.py (SAFE-08) — one command collects the complete v4.1 flow"
affects: [milestone-audit, milestone-complete]

tech-stack:
  added: []
  patterns:
    - "Single release gate over v4.0 + v4.1 via a superset glob; the v4.0 self-test stays green (uses its own v40 glob)"
    - "Screening-framing check scopes to tool-synthesized text (excludes grounded quote lines, which may legitimately contain words like 'approved')"

key-files:
  created:
    - crawler/tests/test_conformance_v41_grounding.py
    - crawler/tests/test_conformance_v41_release_gate.py
  modified:
    - scripts/run_conformance.py
    - pyproject.toml

key-decisions:
  - "_GLOB -> test_conformance_v4[01]_*.py matches v40 AND v41; _SAFE_CRITERIA/banner extended to SAFE-01..08; the v4.0 release-gate self-test stays green (superset collection)"
  - "The affirmative-claim screening check excludes grounded-rule citation lines (case-insensitively) so a verbatim corpus quote ('approved language test') is not misread as a tool approval claim"

patterns-established:
  - "The milestone release gate is ONE command (scripts/run_conformance.py) exercising the complete v4.x SAFE flow"
---

# Phase 39 Plan 03 — Summary

## What shipped
- `crawler/tests/test_conformance_v41_grounding.py` (SAFE-07): retrieve-what-you-cite + determinism +
  no-inlined-volatile + no-second-trust-path (AST + call-level guard) + screening framing over BOTH
  remediation and packet.
- `scripts/run_conformance.py`: `_GLOB` → `test_conformance_v4[01]_*.py`; banner + `_SAFE_CRITERIA` →
  SAFE-01..08; docstring updated. ONE command now runs the complete v4.0 + v4.1 conformance flow.
- `crawler/tests/test_conformance_v41_release_gate.py` (SAFE-08): the one command collects every v4.1 module
  + a v4.0 sentinel; all v4.1 modules carry the conformance marker.
- `pyproject.toml`: conformance marker description widened to SAFE-01..08.

## Requirements satisfied
- **SAFE-07**: every requirement-bearing remediation/packet line derives from a grounded rule (rwyc +
  determinism + static volatile + single trust path).
- **SAFE-08**: the single release-gate command exercises coverage / refusal / remediation / packet /
  privacy / grounding / screening for the complete v4.1 flow.

## Verification
- `.venv/bin/python scripts/run_conformance.py` → PASS SAFE-01..08 (9 modules).
- v4.0 + v4.1 release-gate self-tests + grounding module → 14 passed; publish-safe → 0 violations.

## Deviations
Fixed the screening-framing check to exclude grounded-rule citation lines (a verbatim corpus quote
legitimately contains "approved") — the check now scopes to tool-synthesized framing only.
