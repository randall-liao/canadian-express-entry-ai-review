---
phase: 31-grounded-crs-rule-registry-deterministic-logic
plan: 03
subsystem: crs-rule-registry
tags: [crs, registry, grounding, transferability, caps, arranged-employment, rule-05]

# Dependency graph
requires:
  - phase: 31-01
    provides: RuleRow schema + registry engine (load/validate/retrieve/coverage/static-gate)
provides:
  - Grounded skill-transferability rows + 50/50/100 caps (transferability.yaml)
  - Grounded additional-points rows incl. arranged-employment repeal + legacy (additional.yaml)
  - RULE-05 registry half (current repeal + distinct ITA-era legacy, effective-date metadata)
affects: [31-04, 31-05, 32-auditor-vertical-slice]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Grounded cap rows (kind=cap) so deterministic logic clamps from corpus, not literals"
    - "Current vs legacy policy rows in DIFFERENT source families so they never cross-ground"

key-files:
  created:
    - crawler/data/crs_rules/transferability.yaml
    - crawler/data/crs_rules/additional.yaml
    - crawler/tests/test_crs_registry_transfer_additional.py
  modified:
    - crawler/crs_rules.py

key-decisions:
  - "The arranged-employment CURRENT repeal grounds guidance/job-offer.md#001 (2025-03-25) and the LEGACY row grounds the ministerial-instructions amendment-2017-2.md#006 (200-point Major Group 00) — different families guarantee no cross-grounding (T-31-09)"
  - "The legacy row is GROUNDED (not gap:true) with effective_to=2025-03-25, so 31-04's guard can decide legacy applicability from grounded metadata"
  - "Skill-transferability tier markers legitimately quote grounded CLB thresholds, so 'marker' was added to the static-gate allow-keys (grounded carrier, not inlined prose)"

patterns-established:
  - "Pattern: grounded 50/50/100 cap rows as first-class RuleRows (kind=cap)"

requirements-completed: [RULE-01, RULE-03, RULE-05]

# Metrics
duration: 50min
completed: 2026-07-06
---

# Phase 31 Plan 03: Grounded Transferability + Additional CRS Rule Rows Summary

**14 corpus-grounded rule rows for factor groups C (skill transferability, incl. grounded 50/50/100 caps) and D (additional points, incl. the 2025-03-25 arranged-employment repeal and a distinct grounded ITA-era legacy row) — completing the full CRS grid with zero coverage gaps.**

## Performance
- **Duration:** ~50 min
- **Tasks:** 3 completed
- **Files modified:** 3 created, 1 modified (engine allow-key)
- **Rows grounded:** 8 transferability (incl. 3 caps) + 6 additional = 14 (0 gaps)

## Accomplishments
- Authored `transferability.yaml`: five combination rows + three GROUNDED cap rows (education 50, foreign-work 50, total 100).
- Authored `additional.yaml`: nomination (600), Canadian study (15/30), strong French (25/50), sibling (15), and the RULE-05 arranged-employment pair.
- RULE-05 registry half: current repeal grounds `guidance/job-offer.md#001` with `effective_from=2025-03-25`; a DISTINCT legacy row grounds `ministerial-instructions/amendment-2017-2.md#006` (200-point Major Group 00) with `effective_to=2025-03-25`. Different families → no cross-grounding.
- Full CRS grid now COMPLETE across all four factor groups (0 missing, 0 gaps).

## Task Commits
1. **Engine allow-key fix (marker is a grounded carrier)** - `33f84f1` (fix)
2. **Task 1: Ground skill-transferability rows + caps** - `cdfdcf9` (feat)
3. **Task 2: Ground additional-points rows incl. arranged-employment repeal** - `48a78dd` (feat)
4. **Task 3: Corpus-gated conformance** - `2d2bd7d` (test)

## Files Created/Modified
- `crawler/data/crs_rules/transferability.yaml` - 8 grounded rows (5 combos + 3 caps).
- `crawler/data/crs_rules/additional.yaml` - 6 grounded rows (nomination/study/french/sibling + job-offer current & legacy).
- `crawler/tests/test_crs_registry_transfer_additional.py` - corpus-gated + synthetic conformance (incl. dedicated RULE-05 cross-ground proof).
- `crawler/crs_rules.py` - added `marker` to the static-gate allow-keys.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_crs_registry_transfer_additional.py -q` → 8 passed, 14 subtests.
- validate_registry over corpus/index.db (all 31 rows) → 31/31 grounded, 0 violations.
- retrieve_what_you_cite → all agree; current/legacy job-offer rows select different chunks.
- coverage_report → complete=True (core 6/6, spouse 3/3, transfer 8/8, additional 6/6).
- `.venv/bin/python scripts/check_publish_safe.py` → 230 files, 0 violations.
- No regression: test_crs_rules.py + test_crs_registry_core_spouse.py → 24 passed.

## Deviations from Plan

### Auto-fixed (Rule 3 — blocking false positive)

**1. [Rule 3 - Blocking] Added `marker` to no_inlined_volatile_rules allow-keys**
- **Found during:** Task 1 — skill-transferability tier markers must quote grounded CLB thresholds (e.g. "CLB 9 or more on all four ... abilities") to pick the right chunk.
- **Issue:** A selector `marker` is a verbatim substring of the grounded chunk, but the static gate flagged it as an inlined volatile threshold — a false positive that would have blocked grounded tier rows.
- **Fix:** Added `marker` to `_ALLOW_KEYS` in `crawler/crs_rules.py`; genuine inlined thresholds in prose/Python (non-`marker:` lines) are still flagged (16 static tests + positive control still green).
- **Files modified:** crawler/crs_rules.py
- **Commit:** `33f84f1`

### Note on the legacy arranged-employment row
The plan allowed the legacy row to be `gap:true` if un-groundable. The ITA-era 200-point Major Group 00 rule WAS cleanly groundable from `ministerial-instructions/amendment-2017-2.md#006`, so the legacy row is grounded (not a gap) — with `effective_to=2025-03-25` metadata for 31-04's fail-closed guard.

## Known Stubs
None.

## Self-Check: PASSED
- FOUND: transferability.yaml, additional.yaml, test_crs_registry_transfer_additional.py
- FOUND commits: 33f84f1, cdfdcf9, 48a78dd, 2d2bd7d
