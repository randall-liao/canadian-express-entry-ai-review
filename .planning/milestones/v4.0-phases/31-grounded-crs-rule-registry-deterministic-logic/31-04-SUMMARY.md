---
phase: 31-grounded-crs-rule-registry-deterministic-logic
plan: 04
subsystem: crs-audit-logic
tags: [crs, deterministic, clb, spouse-mode, caps, arranged-employment, rule-04, rule-05]

# Dependency graph
requires:
  - phase: 31-01
    provides: RuleRow schema + registry engine + no_inlined_volatile_rules
  - phase: 31-02
    provides: grounded core/spouse rows (CLB conversion, validity, work, point tables)
  - phase: 31-03
    provides: grounded transferability caps + arranged-employment current/legacy rows
provides:
  - Deterministic CRS math reading grounded rows (crawler/crs_audit.py)
  - to_clb / age_on_date / within_validity / aggregate_work
  - score_factor (spouse mode) / apply_transferability_caps / compare_to_cutoff
  - arranged_employment_guard (RULE-05 fail-closed)
affects: [32-auditor-vertical-slice, 33-full-modular-crs-auditor-pack]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deterministic CRS math reads EVERY volatile value from grounded machine_check payloads"
    - "Golden boundary fixtures use synthetic in-test registries (no corpus dependency)"
    - "Module held to the same no-inlined-volatile-rule bar as auditor prose (self-scan)"

key-files:
  created:
    - crawler/crs_audit.py
    - crawler/tests/test_crs_audit.py
  modified: []

key-decisions:
  - "Every function takes an explicit Registry (testable with synthetic rows); default_registry() loads the real grounded registry for callers"
  - "arranged_employment_guard NEVER auto-awards: even a grounded in-window legacy row yields AT-RISK with points=None (manual), and any missing/gap legacy or post-repeal ITA is AT-RISK/0"
  - "Calendar constants (365.2425 days/year, 12 months) are not CRS thresholds; all CRS values (CLB bands, windows, hours, caps, points, policy dates) are read from grounded rows"

patterns-established:
  - "Pattern: registry-driven deterministic math with a self no-inline scan gate"

requirements-completed: [RULE-02, RULE-04, RULE-05]

# Metrics
duration: 45min
completed: 2026-07-06
---

# Phase 31 Plan 04: Deterministic CRS Logic Summary

**Pure, tested CRS math (`crawler/crs_audit.py`) — CLB/NCLC conversion, date math, work-duration aggregation, spouse-mode scoring, 50/50/100 transferability cap clamping, cutoff comparison, and the fail-closed arranged-employment guard — every threshold read from a grounded rule row, with the module itself passing the no-inlined-volatile-rule gate.**

## Performance
- **Duration:** ~45 min
- **Tasks:** 3 completed (each TDD: test → feat)
- **Files modified:** 2 created
- **Tests:** 20 golden/guard fixtures

## Accomplishments
- `to_clb` reads grounded conversion bands (CLB 8/9 boundary → 9, one below → 8, off-table → None); `age_on_date` (post-ITA birthday does not lower age); `within_validity` (language/ECA windows, fail-closed if absent).
- `aggregate_work`: TEER-eligible, 30h full-time clamp (hours above 30 do not over-count), union merge (no overlap double-count), grounded reference-period window.
- `score_factor` (spouse vs no-spouse diverge for the same inputs), `apply_transferability_caps` (clamps to grounded 50/50/100), `compare_to_cutoff` (arithmetic delta only, no legal advice).
- `arranged_employment_guard` (RULE-05): non-zero job-offer claim → AT-RISK/0 citing the grounded repeal; grounded in-window legacy → AT-RISK/manual (never auto-green); missing/gap legacy or post-repeal ITA → AT-RISK/0; unclaimed → N/A.
- `crawler/crs_audit.py` passes `no_inlined_volatile_rules(["crawler/crs_audit.py"]) == []`.

## Task Commits
1. **Task 1: CLB conversion + date math + work aggregation** - `eaf1de2` (test) → `58121b0` (feat)
2. **Task 2: Spouse mode + caps + cutoff + self no-inline scan** - `4b48765` (test) → `6ad492b` (feat)
3. **Task 3: Arranged-employment guard (RULE-05)** - `2880c45` (test) → `b0cac26` (feat)

## Files Created/Modified
- `crawler/crs_audit.py` - deterministic CRS logic (all values read from grounded rows).
- `crawler/tests/test_crs_audit.py` - 20 golden boundary + guard + self-scan fixtures.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_crs_audit.py -q` → 20 passed.
- `-k inline` self-scan → crs_audit.py has 0 inlined volatile thresholds.
- End-to-end against the REAL registry: post-repeal claim → AT-RISK/0 (job-offer.md#001); pre-repeal → AT-RISK/manual (amendment-2017-2.md#006); caps clamp to 50/50/100.
- No regression: test_crs_rules.py + test_grounding.py → 62 passed.

## Deviations from Plan
None — plan executed as written. Added `default_registry()` convenience (loads the grounded registry for downstream callers) which also satisfies the plan's crs_audit→load_registry key link.

## Known Stubs
None. (compare_to_cutoff intentionally takes the round cutoff as caller-provided grounded round data — round-level rows are outside the four-group registry grid, per SAFE-04 deferral.)

## Self-Check: PASSED
- FOUND: crawler/crs_audit.py, crawler/tests/test_crs_audit.py
- FOUND commits: 58121b0, 6ad492b, b0cac26
