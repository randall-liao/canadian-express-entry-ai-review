---
phase: 31-grounded-crs-rule-registry-deterministic-logic
plan: 02
subsystem: crs-rule-registry
tags: [crs, registry, grounding, yaml, corpus, core, spouse]

# Dependency graph
requires:
  - phase: 31-01
    provides: RuleRow schema + registry engine (load/validate/retrieve/coverage)
provides:
  - Grounded core-human-capital rule rows (crawler/data/crs_rules/core.yaml)
  - Grounded spouse/common-law rule rows (crawler/data/crs_rules/spouse.yaml)
  - CLB/NCLC conversion rows citing the equivalency chart (feeds 31-04 to_clb)
  - Corpus-gated conformance + always-runs synthetic mirror
affects: [31-04, 31-05, 32-auditor-vertical-slice]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Grounded rule rows: baked short query + family allow + non-volatile marker + deny_families"
    - "deny_families drops near-duplicate CRS grid families (guidance/grid + year-end reports)"

key-files:
  created:
    - crawler/data/crs_rules/core.yaml
    - crawler/data/crs_rules/spouse.yaml
    - crawler/tests/test_crs_registry_core_spouse.py
  modified: []

key-decisions:
  - "FTS5 uses implicit-AND term matching — queries are kept SHORT (2-4 high-signal terms present in the target chunk) so the cited chunk is actually retrieved"
  - "crs-criteria.md and grid.md are near-duplicates; every CRS-grid row denies guidance/grid + year-end/midyear/summary/fact-sheet families so retrieve-what-you-cite lands the intended chunk"
  - "CLB/NCLC conversion grounded from language/test-equivalency-charts.md with kind=conversion payloads (IELTS + CELPIP), the source 31-04 reads"

patterns-established:
  - "Pattern: author row -> verify via validate_registry + retrieve_what_you_cite against the REAL corpus -> tune query/marker until agree+ground"

requirements-completed: [RULE-01, RULE-03]

# Metrics
duration: 55min
completed: 2026-07-06
---

# Phase 31 Plan 02: Grounded Core + Spouse CRS Rule Rows Summary

**17 corpus-grounded CRS rule rows for factor groups A (core human capital) and B (spouse/common-law) — every row resolves + verbatim-grounds through the shipped gate and passes retrieve-what-you-cite against the REAL corpus, with CLB/NCLC conversion sourced from the equivalency chart.**

## Performance
- **Duration:** ~55 min
- **Tasks:** 3 completed
- **Files modified:** 3 created
- **Rows grounded:** 14 core + 3 spouse = 17 (0 gaps)

## Accomplishments
- Authored `core.yaml`: age + education tables, ECA <5y validity + designated-org admissibility, first-language approved/accepted-tests/<2y validity/per-ability points, CLB/NCLC conversion (IELTS + CELPIP), second-language points, and the Canadian work definition (TEER 0-3, 30h full-time equivalence, self-employment/full-time-study exclusions).
- Authored `spouse.yaml`: spouse education (owner-must-be-spouse), spouse language (section cap 20), spouse Canadian work (owner separation) — each grounded.
- Every non-gap row grounds through the SHIPPED gate AND retrieve-what-you-cite re-selects the cited chunk (guards historical/adjacent chunk grounding via deny_families).
- Corpus-gated conformance + always-runs synthetic mirror; rendered rows self-scanned publish-safe.

## Task Commits
1. **Task 1: Ground core-human-capital rows into core.yaml** - `bf884af` (feat)
2. **Task 2: Ground spouse/common-law rows into spouse.yaml** - `d6c2b4d` (feat)
3. **Task 3: Corpus-gated conformance for core + spouse rows** - `6e5b7e5` (test)

## Files Created/Modified
- `crawler/data/crs_rules/core.yaml` - 14 grounded core-human-capital rule rows.
- `crawler/data/crs_rules/spouse.yaml` - 3 grounded spouse/common-law rule rows.
- `crawler/tests/test_crs_registry_core_spouse.py` - corpus-gated + synthetic conformance.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_crs_registry_core_spouse.py -q` → 8 passed, 17 subtests.
- validate_registry over corpus/index.db → 17/17 grounded, 0 violations.
- retrieve_what_you_cite → all 17 agree + ground.
- `.venv/bin/python scripts/check_publish_safe.py` → 227 files, 0 violations.
- coverage_report: core 6/6 present, spouse 3/3 present, 0 gaps.
- No regression: `test_crs_rules.py` → 16 passed.

## Deviations from Plan
None — plan executed as written. All required core and spouse rows grounded from the current corpus; no fabricated citations and no coverage gaps needed for groups A/B.

## Known Stubs
None.

## Self-Check: PASSED
- FOUND: crawler/data/crs_rules/core.yaml, crawler/data/crs_rules/spouse.yaml, crawler/tests/test_crs_registry_core_spouse.py
- FOUND commits: bf884af, d6c2b4d, 6e5b7e5
