---
phase: 33-full-modular-crs-auditor-pack
plan: 04
subsystem: api
tags: [crs, transferability, caps, dependency, auditor]

requires:
  - phase: 33-full-modular-crs-auditor-pack
    provides: dispatch spine, prior_cards ordering (transfer.* last), crs_audit.apply_transferability_caps
provides:
  - five transferability combination deciders consuming prior core cards + grounded caps
  - portable skills/crs-auditors/skill-transferability.md
affects: [33-06, 34-safety-conformance]

tech-stack:
  added: []
  patterns:
    - "derived combinations require every component SUBSTANTIATED before awarding tier points"
    - "cross-combination cap clamp via incremental apply_transferability_caps over prior transfer cards"

key-files:
  created:
    - skills/crs-auditors/skill-transferability.md
    - crawler/tests/test_auditors_transferability.py
  modified:
    - crawler/auditors/transferability.py

key-decisions:
  - "tier keyed by the grounded ladder (language CLB or work years) read from ctx.consumed rows"
  - "section + total caps applied incrementally in decision order (transfer.* ordered last by the spine)"

patterns-established:
  - "recombination modules read component verdicts from ctx.prior_cards, never re-read documents"

requirements-completed: [AUDIT-01, AUDIT-03]

duration: ~35min
completed: 2026-07-06
---

# Phase 33 Plan 04: Skill-Transferability Module Summary

**Replaced the Wave-1 transferability stub with the real module — five combination deciders that recombine already-substantiated core cards, block on any unproven component (GAP/AT-RISK, never points), and clamp their contribution to the grounded 50/50/100 caps across combinations (SC5).**

## Accomplishments
- Five combination deciders read component core cards from `ctx.prior_cards`; every component must be `SUBSTANTIATED` before awarding tier points (missing/GAP → `unmet_component` GAP; AT-RISK component → AT-RISK).
- Tier selection reads the grounded ladder from `ctx.consumed` (language CLB or work years); the contribution is clamped through `crs_audit.apply_transferability_caps` incrementally across combinations so the grounded section (50/50) and total (100) caps hold.
- Added the portable `skill-transferability.md` spec and tests proving dependency, tier flip (CLB 9→7 flips 50→25), and section + total cap clamping.

## Task Commits
1. **Task 1 (TDD) + Task 2: Combination deciders + spec + tests** — `f5628c4` (feat)

## Files Created/Modified
- `crawler/auditors/transferability.py` — five deciders + `_award_capped` cross-combination clamp.
- `skills/crs-auditors/skill-transferability.md` — portable context-light spec.
- `crawler/tests/test_auditors_transferability.py` — dependency, tier flip, caps.

## Decisions Made
- The total-cap clamp is applied per combination as the increase in the clamped grand total (`apply_transferability_caps` over the prior transfer cards + this combination), so the 100 cap holds across the whole group in decision order.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## Next Phase Readiness
Transferability dependency GAP is asserted end-to-end in 33-06 (`transfer.education_work` GAP when `core.work` is GAP).

---
*Phase: 33-full-modular-crs-auditor-pack*
*Completed: 2026-07-06*

## Self-Check: PASSED

All listed files exist on disk and all task commit hashes are present in git history.
