---
phase: 36-operational-hardening
plan: 02
subsystem: data
tags: [crs, audit, example, profile, grid, anti-drift, pii-boundary, unittest]

# Dependency graph
requires:
  - phase: 33-full-modular-crs-auditor-pack
    provides: "auditors.FULL_GRID_FACTORS / FACTOR_GROUP canonical dotted grid + full-grid audit path"
provides:
  - "Re-keyed personal.example/crs-profile.example.yaml using canonical dotted factor ids (core.age, core.education, core.language.first, spouse.education, transfer.education_language, additional.nomination) + matching groups"
  - "Anti-drift pin test: every example factor_id in FULL_GRID_FACTORS + group agreement + a skip-guarded real-audit non-N/A proof"
affects: [phase-37-remediation, phase-38-review-packet]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Set-membership anti-drift pin (example ids subset of FULL_GRID_FACTORS) mirroring test_siblingfields_vocab"
    - "Skip-guarded real-audit proof mirroring test_full_audit_real_seam (structural-only on a fresh clone)"

key-files:
  created:
    - crawler/tests/test_example_profile_pinned.py
  modified:
    - personal.example/crs-profile.example.yaml

key-decisions:
  - "Pin asserts >= 1 non-N/A for a CLAIMED core factor (not every claimed factor): a single-applicant profile legitimately audits spouse.education as N/A not_applicable"
  - "Example values stay synthetic/PII-free; publish-safe scan stays clean (0 violations across 319 tracked files)"
  - "Comments updated to explain that a claimed factor with no confirmed evidence audits as GAP/AT-RISK (applicable), while an off-grid id would be N/A not_claimed"

patterns-established:
  - "Any shipped example CRS profile must be grid-pinned so it can never silently regress to all-N/A"
---

# Phase 36 Plan 02 — Summary

## What shipped
- Re-keyed `personal.example/crs-profile.example.yaml` from non-canonical ids (`core_age`,
  `core_first_language`, …) to the canonical dotted grid ids + matching groups; refreshed the header
  comments to explain the grid pin and the GAP/AT-RISK-vs-N/A semantics.
- `crawler/tests/test_example_profile_pinned.py`: grid-membership + group-agreement pin (unguarded) and a
  skip-guarded real-audit proof that a claimed core factor reaches a non-`N/A` verdict.

## Requirement satisfied
- **HARD-03**: the shipped synthetic example uses canonical dotted factor ids, is pinned to the live grid,
  and produces applicable non-`N/A` verdicts through the real CLI path (verified live: `core.age`,
  `core.education`, `core.language.first` → GAP; `spouse.education` → N/A not_applicable, as expected).

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_example_profile_pinned.py crawler/tests/test_profile_loader.py -q` → all pass (incl. the real-audit non-N/A proof).
- `.venv/bin/python scripts/check_publish_safe.py` → 0 violations (319 tracked files).

## Deviations
None. Added `vault.create_candidate` before `import_profile_yaml` in the real-audit test (the direct
seam requires the candidate row; the CLI `profile set` path creates it implicitly).
