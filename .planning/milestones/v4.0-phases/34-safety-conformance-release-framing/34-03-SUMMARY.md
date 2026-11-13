---
phase: 34-safety-conformance-release-framing
plan: 03
subsystem: testing
tags: [conformance, grounding, retrieve-what-you-cite, fts5, crs-registry, safety]

# Dependency graph
requires:
  - phase: 31-grounded-crs-registry
    provides: retrieve_what_you_cite / validate_registry / coverage_report / no_inlined_volatile_rules + COVERAGE.md
provides:
  - Authoritative SAFE-03 retrieve-what-you-cite conformance module (positive + negative controls)
  - Whole-registry per-rule agree+ground proof against the real corpus
  - Wrong-family / historical-superseded / adjacent-marker negative controls (non-vacuous)
affects: [milestone-audit, release-gate, safety-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Real-corpus per-rule agree+ground subTest sweep + covered-set equality guard"
    - "Synthetic-index negative controls proven load-bearing vs blind hits[0]"

key-files:
  created:
    - crawler/tests/test_conformance_v40_retrieve_what_you_cite.py
  modified: []

key-decisions:
  - "Split proof: real-corpus asserts the actual registry selects the intended authority; synthetic index proves the family/marker guards are load-bearing"
  - "Real job-offer control asserts current-vs-legacy separation structurally (disjoint citations, distinct families) since the historical decoy does not rank on the real corpus"

patterns-established:
  - "Negative-control non-vacuity via blind searchindex.search(family)[0] == the wrong chunk"

requirements-completed: [SAFE-03]

# Metrics
duration: 22min
completed: 2026-07-06
---

# Phase 34 Plan 03: SAFE-03 Retrieve-What-You-Cite Conformance Summary

**Authoritative proof that every registry rule grounds the intended current rule against the real corpus, plus non-vacuous wrong-family / historical-superseded / adjacent-marker negative controls proving the source-family allow/deny + marker selection discipline actually bites.**

## Performance

- **Duration:** ~22 min (whole phase, parallel wave)
- **Tasks:** 2
- **Files created:** 1
- **Tests added:** 11 tests, 34 subtests

## Accomplishments
- Positive (real corpus): every non-gap rule across all four YAML groups `agrees_with_citation` AND `grounds` (34 subtests), `validate_registry` returns 0 violations with `grounded == total` and total ≥ 20, coverage is complete with no silent missing ids, the committed `COVERAGE.md` matches fresh output (drift guard), and the static `no_inlined_volatile_rules` gate is clean over the registry + auditor surface.
- Real job-offer control: the current-policy row grounds from current guidance (never a denied year-end/midyear historical chunk); the legacy row stays a separate `ministerial-instructions` row citing a disjoint chunk — the legacy points chunk never bleeds into the current verdict.
- Negative controls (synthetic index, always-run, non-vacuous): a wrong-family selection does not agree/ground; `deny_families` drops the superseded top hit to select the current authority; an adjacent chunk missing the marker is dropped and a marker-absent-everywhere row abstains; the correct-family+marker mirror grounds the intended chunk — each proven load-bearing because a blind `hits[0]` selection would have mis-grounded.

## Task Commits

1. **Task 1: Positive per-rule grounding + coverage + static gate** - `cc09bc6` (test)
2. **Task 2: Wrong-family / historical / adjacent negative controls** - `cc09bc6` (test)

## Files Created/Modified
- `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py` - SAFE-03 authoritative retrieve-what-you-cite conformance module (297 lines).

## Decisions Made
- Prove the actual registry against the real corpus (structural) and prove the guard mechanisms against a synthetic index (always-run, non-vacuous) — the split gives both real-authority selection and demonstrable load-bearing guards.
- Assert the covered rule_id set equals the non-gap rows so a future added rule cannot silently escape the proof.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- On the real corpus the current job-offer query does not surface a historical decoy in the top hits, so deny_families non-vacuity is proven on the synthetic index instead; the real control asserts the structural current-vs-legacy separation.

## Next Phase Readiness
SAFE-03 module is collected by the release gate and runs against the real corpus locally.

---
*Phase: 34-safety-conformance-release-framing*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created files exist on disk; all task commit hashes are present in git history.
