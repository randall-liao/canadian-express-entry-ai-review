---
phase: 33-full-modular-crs-auditor-pack
plan: 02
subsystem: database
tags: [crs, clb, nclc, conversion, grounding, corpus]

requires:
  - phase: 31-grounded-crs-rule-registry
    provides: crs_rules registry loader/gate, crs_audit.to_clb, conversion RuleRow schema
provides:
  - complete grounded CLB/NCLC conversion rows for all 5 accepted tests x 4 abilities
  - conversion completeness + grounding + to_clb resolution tests
affects: [33-01, 33-06, 34-safety-conformance]

tech-stack:
  added: []
  patterns:
    - "one citation per CLB-level chart row; per-ability PointsEntry references it"

key-files:
  created:
    - crawler/tests/test_crs_conversion_coverage.py
  modified:
    - crawler/data/crs_rules/core.yaml

key-decisions:
  - "TEF Canada grounds ONLY the current (post-2023-12-10) window to avoid overlapping-window to_clb ambiguity"
  - "IELTS/CELPIP single chart values become contiguous non-overlapping bands; PTE/TEF/TCF use chart ranges"

patterns-established:
  - "verbatim chart-row quotes grounded through the frozen gate; no fabricated citations"

requirements-completed: [AUDIT-01, AUDIT-03]

duration: ~40min
completed: 2026-07-06
---

# Phase 33 Plan 02: Complete Grounded Conversion Tables Summary

**Completed the grounded CLB/NCLC conversion tables for all five accepted language tests across all four abilities — verbatim-grounded from the real corpus — so `to_clb` resolves every band and language `SUBSTANTIATED` is reachable (closing the Phase-32 known item).**

## Accomplishments
- Expanded `core.language.conversion.*` into five complete rows (CELPIP-General, IELTS General Training, PTE Core, TEF Canada, TCF Canada) covering reading/writing/listening/speaking, every band grounded verbatim from `corpus/language/test-equivalency-charts.md` (chunks `#002` and `#003`).
- Encoded only the current TEF window (after 2023-12-10) so `to_clb` cannot return a wrong overlapping-window level; IELTS/CELPIP single values became contiguous bands, PTE/TEF/TCF use the chart ranges.
- Verified: 34/34 registry rows ground with 0 violations, retrieve-what-you-cite agrees for every conversion row, `to_clb` resolves every test/ability top+bottom boundary, out-of-table returns None, and no bands overlap.

## Task Commits
1. **Task 1: Ground the full conversion table (5 tests × 4 abilities)** — `c0fc743` (feat)
2. **Task 2: Conversion coverage/grounding/to_clb tests; COVERAGE.md** — `7efb9a9` (test)

## Files Created/Modified
- `crawler/data/crs_rules/core.yaml` — five complete grounded conversion rows.
- `crawler/tests/test_crs_conversion_coverage.py` — completeness + grounding + `to_clb` + SUBSTANTIATED-reachability.
- `crawler/data/crs_rules/COVERAGE.md` — regenerated (byte-identical; conversion was already labelled `present`).

## Decisions Made
- Only the current TEF window is encoded (older windows excluded) to keep `to_clb` deterministic.
- Every conversion band is grounded; no ability required a truthful `gap:true` row (the current corpus fully covers all five tests × four abilities).

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- The auto-generated query for the TCF row initially included the token "CLB", which is absent from the NCLC-only TCF chunk, so the AND-query excluded it and retrieve-what-you-cite failed. Fixed by using chunk-appropriate queries (`TCF Canada NCLC level`, `TEF Canada NCLC level`).

## Next Phase Readiness
Language `SUBSTANTIATED` is now reachable end-to-end (proven in 33-06).

---
*Phase: 33-full-modular-crs-auditor-pack*
*Completed: 2026-07-06*

## Self-Check: PASSED

All listed files exist on disk and all task commit hashes are present in git history.
