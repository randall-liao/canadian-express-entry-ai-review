---
phase: 33-full-modular-crs-auditor-pack
plan: 05
subsystem: api
tags: [crs, additional-points, job-offer, nomination, french, auditor]

requires:
  - phase: 33-full-modular-crs-auditor-pack
    provides: dispatch spine, core leaf helpers, crs_audit.arranged_employment_guard
provides:
  - additional-points deciders (nomination, job-offer guard, study, french, sibling)
  - portable skills/crs-auditors/additional-points.md
affects: [33-06, 34-safety-conformance]

tech-stack:
  added: []
  patterns:
    - "job-offer additional CRS is never SUBSTANTIATED (arranged_employment_guard delegation)"

key-files:
  created:
    - skills/crs-auditors/additional-points.md
    - crawler/tests/test_auditors_additional.py
  modified:
    - crawler/auditors/additional.py

key-decisions:
  - "decide_job_offer delegates to the shipped RULE-05 guard: AT-RISK/0 current, AT-RISK/None in-window legacy, N/A zero"
  - "strong French reuses the frozen conversion + validity path (NCLC), awards grounded French points"

patterns-established:
  - "fail-closed default (missing evidence -> GAP) for factors without a captured evidence field (sibling)"

requirements-completed: [AUDIT-01, AUDIT-03]

duration: ~35min
completed: 2026-07-06
---

# Phase 33 Plan 05: Additional-Points Module Summary

**Replaced the Wave-1 additional-points stub with the real module — the arranged-employment job-offer factor never auto-greens (delegates to the shipped RULE-05 guard), nomination awards its grounded maximum only when verified and non-expired, and strong French reuses the grounded NCLC conversion path.**

## Accomplishments
- `decide_job_offer` delegates to `crs_audit.arranged_employment_guard`: a non-zero claim is AT-RISK/0 under current policy, AT-RISK/None (manual) only for a grounded in-window legacy, and N/A when zero — never SUBSTANTIATED.
- `decide_nomination` (verified, non-expired → grounded points; missing → GAP; expired → AT-RISK), `decide_study` (eligible credential length → grounded tier), `decide_french` (grounded NCLC conversion + strong-French points), `decide_sibling` (fail-closed GAP).
- Added the portable `additional-points.md` spec (framed as screening, not legal advice) and tests proving the job-offer trap, nomination verification, and French thresholds.

## Task Commits
1. **Task 1 (TDD) + Task 2: Additional deciders + spec + tests** — `5801b92` (feat)

## Files Created/Modified
- `crawler/auditors/additional.py` — five deciders (job-offer guard delegation).
- `skills/crs-auditors/additional-points.md` — portable context-light spec.
- `crawler/tests/test_auditors_additional.py` — job-offer trap, nomination, French, study.

## Decisions Made
- Strong French awards the grounded `french_only` tier by default; the higher French+English tier remains available in the grounded row.

## Deviations from Plan

### Known limitation (documented)

**decide_sibling is fail-closed GAP** — the EXTRACT-01 field vocabulary carries no sibling-relationship / status / residence field yet, so a sibling claim currently surfaces as a documented GAP (never a hidden pass) until that evidence is captured in a future phase. This is truthful fail-closed behaviour, not a stub that greens.

---

**Total deviations:** 0 auto-fixed (1 documented known limitation).
**Impact on plan:** None on the required verdicts; sibling remains a safe GAP.

## Issues Encountered
None.

## Next Phase Readiness
All four modules are now real; 33-06 exercises the whole grid end-to-end.

## Known Stubs
- `additional.sibling` → always GAP (`missing_evidence`) because no sibling-relationship evidence field exists in the vocabulary yet. Documented above; does not block any required verdict.

---
*Phase: 33-full-modular-crs-auditor-pack*
*Completed: 2026-07-06*

## Self-Check: PASSED

All listed files exist on disk and all task commit hashes are present in git history.
