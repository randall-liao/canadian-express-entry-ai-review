---
phase: 39-safe-conformance-release-consolidation
plan: 01
subsystem: testing
tags: [crs, conformance, safe-05, coverage, no-false-green, sibling, adversarial, unittest]

requires:
  - phase: 35-coverage-completion
    provides: "score_factor pricing pin + points_unresolved/counts[unpriced] + decide_sibling fail-closed matrix"
  - phase: 36-operational-hardening
    provides: "adversarial extraction quarantine real-seam"
provides:
  - "test_conformance_v41_coverage.py (SAFE-05) — priced-or-unresolved + sibling/adversarial no-false-green, conformance-marked"
affects: [39-03-release-gate]

tech-stack:
  added: []
  patterns:
    - "Conformance module reuses proven Phase-35/36 helpers (imports _conversion_emitted_levels, _ctx/_sibling_fields, make_fixtures) — authoritative, not duplicative"

key-files:
  created:
    - crawler/tests/test_conformance_v41_coverage.py
  modified: []

key-decisions:
  - "Real-seam adversarial check is skip-guarded on corpus/index.db + deps (structural-only on a fresh clone), like the shipped real-seam tests"
  - "Priced-or-unresolved proven unguarded via score_factor over emitted CLB levels + counts['unpriced'] on a synthetic unpriced card"

patterns-established:
  - "v4.1 SAFE conformance modules carry pytest.mark.conformance and mix unguarded structural + skip-guarded real-seam checks"
---

# Phase 39 Plan 01 — Summary

## What shipped
- `crawler/tests/test_conformance_v41_coverage.py` (SAFE-05): PricedOrExplicitlyUnresolved (every emitted CLB
  benchmark priced both modes + unpriced surfaced), SiblingNoFalseGreen (blocking states never SUBSTANTIATED;
  adult chain does), AdversarialNoFalseGreenRealSeam (rotated language scan never greens, skip-guarded).

## Requirement satisfied
- **SAFE-05**: every supported language benchmark priced-or-unresolved; no sibling/adversarial state greens a factor.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_conformance_v41_coverage.py -q` → 6 passed (real-seam ran here).

## Deviations
None. Incorporated the plan-checker's 4-arg score_factor signature + explicit points_unresolved / counts['unpriced'] guidance.
