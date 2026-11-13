---
phase: 44-canadian-study-dli-pgwp-evidence-gate
plan: 02
subsystem: freshness
tags: [snapshot-policy, configuration, fail-closed, pii-free, stdlib]

requires:
  - phase: 40-safe-freshness-effective-date-foundation
    provides: Caller-supplied snapshot freshness probing and no-inline static gate
  - phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
    provides: Pinned DLI snapshot family without a self-grounded max-age row
provides:
  - One explicit-then-environment DLI snapshot max-age resolver
  - Positive-integer-only parsing with no operational default
  - Pre-registered no-inline scan coverage for snapshot policy and study review
affects: [44-03-study-review, 44-04-cli-conformance]

tech-stack:
  added: []
  patterns: [single boundary resolver, explicit-over-environment precedence, fail-closed configuration]

key-files:
  created:
    - crawler/snapshot_policy.py
  modified:
    - crawler/tests/test_freshness_staleness.py
    - crawler/tests/test_crs_no_inlined_rules.py

key-decisions:
  - "Invalid explicit input refuses directly and never falls back to a valid environment value."
  - "A missing or invalid bound remains None at the resolver boundary and must be refused by Plan 44-04 before probe_snapshot."

patterns-established:
  - "Operational snapshot policy is separate from IRCC-grounded rules and carries no numeric default."
  - "The CLI resolves once; downstream study review receives only the explicit positive integer."

# STUDY requirements intentionally remain pending until Phase 44 closeout.
requirements-completed: []

duration: 1min
completed: 2026-07-19
---

# Phase 44 Plan 02: Authoritative Snapshot Max-Age Summary

**A zero-dependency operational resolver now enforces explicit-over-environment precedence and yields only a positive DLI snapshot max age or a mandatory pre-probe refusal signal.**

## Performance

- **Duration:** 1 min
- **Started:** 2026-07-19T16:59:20Z
- **Completed:** 2026-07-19T17:00:33Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Added the single `dli_snapshot_max_age_days` boundary resolver with exact explicit-then-`PR_DLI_SNAPSHOT_MAX_AGE_DAYS` precedence.
- Rejected absent, blank, non-integer, non-positive, boolean, and unsupported inputs without a default or environment fallback after an explicit value.
- Extended freshness and no-inline coverage while pre-registering the future study sidecar without creating or wiring it.

## Task Commits

TDD work was committed atomically:

1. **RED: Add failing snapshot policy coverage** - `b54b396` (test)
2. **GREEN: Resolve operational snapshot max age** - `1a86be9` (feat)

Both commits carry the required `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer.

## Files Created/Modified

- `crawler/snapshot_policy.py` - PII-free, stdlib-only operational max-age resolver and mandatory pre-probe refusal contract.
- `crawler/tests/test_freshness_staleness.py` - Explicit precedence, environment fallback, no-default, and invalid-value matrix.
- `crawler/tests/test_crs_no_inlined_rules.py` - Static scan ownership for snapshot policy and the future study review module.

## Decisions Made

- Explicit input owns the decision whenever it is not `None`; malformed explicit input cannot silently fall through to the environment.
- `None` is a boundary refusal signal only. Plan 44-04 must reject it before index probing, vault access, or writes because `probe_snapshot(..., max_age_days=None)` skips staleness.
- Max age remains operational configuration rather than an IRCC-grounded fact; no registry row or numeric default was added.
- STUDY-03 and STUDY-04 remain pending until Phase 44 closeout.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_freshness_staleness.py crawler/tests/test_crs_no_inlined_rules.py -q` — 19 passed, 10 subtests passed.
- `.venv/bin/python -c "from crawler import snapshot_policy as s; print(s.dli_snapshot_max_age_days(30), s.dli_snapshot_max_age_days(0), s.dli_snapshot_max_age_days('x'))"` — `30 None None`.
- `no_inlined_volatile_rules(['crawler/snapshot_policy.py'])` — empty violation list.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no dependency, service, CLI, or sidecar changes were introduced.

## Known Stubs

None.

## TDD Gate Compliance

- RED commit `b54b396` failed collection as expected because `crawler.snapshot_policy` did not exist.
- GREEN commit `1a86be9` followed and made the focused and complete plan suites pass.

## Next Phase Readiness

- Plan 44-04 can resolve the bound once at the CLI boundary, refuse `None`, and pass the positive integer explicitly.
- Sidecar, CLI, extraction, registry, dependency, and cache surfaces remain untouched.
- STUDY requirements remain pending until Phase 44 closeout.

## Self-Check: PASSED

- Created file exists: `crawler/snapshot_policy.py`.
- Task commits exist: `b54b396`, `1a86be9`.
- No tracked file deletion occurred.
- Modified-file scan found no goal-blocking stubs or unplanned threat surface.

---
*Phase: 44-canadian-study-dli-pgwp-evidence-gate*
*Completed: 2026-07-19*
