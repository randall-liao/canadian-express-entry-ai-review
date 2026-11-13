---
phase: 33-full-modular-crs-auditor-pack
plan: 03
subsystem: api
tags: [crs, spouse, ownership-separation, auditor]

requires:
  - phase: 33-full-modular-crs-auditor-pack
    provides: dispatch spine, DecisionContext, core leaf helpers, spouse.* N/A short-circuit
provides:
  - spouse/common-law deciders (education, language, work) + determine_spouse_mode
  - structural ownership separation (principal value can never green a spouse factor)
  - portable skills/crs-auditors/spouse-common-law.md
affects: [33-06, 34-safety-conformance]

tech-stack:
  added: []
  patterns:
    - "spouse mode driven by an explicit spouse.accompanying profile signal, not stray evidence"

key-files:
  created:
    - skills/crs-auditors/spouse-common-law.md
    - crawler/tests/test_auditors_spouse.py
  modified:
    - crawler/auditors/spouse.py

key-decisions:
  - "spouse language section total is clamped to the grounded section cap after summing per-ability points"
  - "ownership separation is structural: spine restricts by_field to the spouse factor's audit-eligible values"

patterns-established:
  - "reuse core leaf helpers (_decide_language, _grounded_points) across modules"

requirements-completed: [AUDIT-01, AUDIT-03]

duration: ~35min
completed: 2026-07-06
---

# Phase 33 Plan 03: Spouse / Common-Law Module Summary

**Replaced the Wave-1 spouse stub with the real spouse/common-law module — spouse-mode gating on an explicit profile signal, spouse-table scoring with the grounded section cap, and structural ownership separation so a principal-owned value can never substantiate a spouse factor (SC5).**

## Accomplishments
- `determine_spouse_mode` reads the explicit `spouse.accompanying` profile signal (not stray evidence), so no-spouse mode marks every `spouse.*` factor `N/A`.
- Three deciders (`decide_spouse_education`, `decide_spouse_language` with section-cap clamp, `decide_spouse_work`) score under spouse mode and read only spine-restricted spouse-owned values — ownership separation is structural.
- Added the portable `spouse-common-law.md` spec (no inlined thresholds) and tests proving no-spouse N/A, spouse SUBSTANTIATED (capped at 20), below-threshold GAP, and the ownership-separation GAP.

## Task Commits
1. **Task 1 (TDD) + Task 2: Spouse deciders + spec + tests** — `8d00c09` (feat)

## Files Created/Modified
- `crawler/auditors/spouse.py` — real deciders + `determine_spouse_mode` + section-cap helper.
- `skills/crs-auditors/spouse-common-law.md` — portable context-light spec.
- `crawler/tests/test_auditors_spouse.py` — gating, N/A, SUBSTANTIATED, ownership separation.

## Decisions Made
- Spouse language points are summed per ability then clamped to the grounded section cap (the cap spans the section, not each ability).

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- The ownership-separation test needed `core.language.first` claimed as a profile factor for the FK on principal-owned evidence; added the principal claim in the seeding.

## Next Phase Readiness
Spouse module is wired into the full grid; 33-06 asserts the ownership GAP end-to-end.

---
*Phase: 33-full-modular-crs-auditor-pack*
*Completed: 2026-07-06*

## Self-Check: PASSED

All listed files exist on disk and all task commit hashes are present in git history.
