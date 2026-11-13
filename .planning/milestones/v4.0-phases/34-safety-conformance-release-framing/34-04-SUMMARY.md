---
phase: 34-safety-conformance-release-framing
plan: 04
subsystem: testing
tags: [conformance, release-gate, screening, framing, docs, pytest-marker, safety]

# Dependency graph
requires:
  - phase: 34-safety-conformance-release-framing
    provides: SAFE-01/02/03 conformance modules (Waves 1) the entry point collects
  - phase: 32-audit-slice
    provides: audit_report._render_factor_card_markdown report writer
provides:
  - SAFE-04 screening framing (SCREENING_NOTICE report wording + README section + SCREENING.md)
  - scripts/run_conformance.py single authoritative release-gate entry point
  - conformance pytest marker registration
  - Screening-framing + release-gate conformance tests
affects: [milestone-audit, release-gate, safety-conformance, docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Screening-not-legal-advice framing rendered into every vault report + release docs"
    - "Single marker-independent conformance entry point over test_conformance_v40_*.py glob"
    - "Non-vacuous, negated-disclaimer-normalizing legal-advice denylist scan"

key-files:
  created:
    - SCREENING.md
    - scripts/run_conformance.py
    - crawler/tests/test_conformance_v40_screening_framing.py
    - crawler/tests/test_conformance_v40_release_gate.py
  modified:
    - crawler/audit_report.py
    - crawler/README.md
    - pyproject.toml
    - crawler/tests/test_full_audit_integration.py
    - crawler/tests/test_full_audit_cutoff.py

key-decisions:
  - "Framing lives in rendered markdown + docs, NOT in the strict PublicAuditEnvelope schema (preserve the AUDIT-06 boundary)"
  - "Runner selects by the deterministic file glob (marker-independent) and exits with pytest rc; --collect-only enables non-recursive coverage checks"
  - "Only a [tool.pytest.ini_options] markers table added to pyproject — no new runtime dependency"

patterns-established:
  - "PR_CONFORMANCE_RUNNER guard env marks a real gate run so the release-gate test avoids recursion"

requirements-completed: [SAFE-04]

# Metrics
duration: 22min
completed: 2026-07-06
---

# Phase 34 Plan 04: SAFE-04 Screening Framing + Release Gate Summary

**Frames the CRS auditor output as substantiation screening (not legal advice) in the report wording and release docs with a narrow SUBSTANTIATED definition and AT-RISK scope, and locks the milestone release gate behind one authoritative command that collects and passes all four SAFE conformance modules.**

## Performance

- **Duration:** ~22 min (whole phase; Wave 2)
- **Tasks:** 3
- **Files created:** 4, **modified:** 5
- **Tests added:** 15 tests (11 framing + 4 release-gate)

## Accomplishments
- `SCREENING_NOTICE` constant added to `crawler/audit_report.py` and rendered into every vault report (single + full-grid): narrow SUBSTANTIATED definition (confirmed + audit-eligible evidence + met threshold + corpus-grounded cited rule), AT-RISK scope for semantic / NOC-duty fit / document authenticity / officer discretion, and "CRS substantiation screening, not legal advice / not a substitute" — generic and PII-free.
- `crawler/README.md` gains a "Substantiation screening — scope & limits" section; new `SCREENING.md` release doc covers what the tool does, the narrow SUBSTANTIATED definition, the four-verdict vocabulary, the AT-RISK scope, the privacy model, the not-legal-advice framing, and the single-command release gate — all shareable/PII-free.
- `scripts/run_conformance.py` is the single authoritative release gate: runs the whole `test_conformance_v40_*.py` suite via `sys.executable -m pytest`, exits with pytest's rc, prints a SAFE-01..04 pass/fail banner, supports non-recursive `--collect-only`, passes extra flags through, and exports `PR_CONFORMANCE_RUNNER=1` on real runs. Stdlib only, no new deps. The `conformance` marker is registered in `pyproject.toml` (no runtime dependency added).
- Two conformance tests: screening-framing presence + non-vacuous prohibited-phrasing absence + PII-free doc scan, and the release-gate test proving one command collects all four SAFE modules and each carries the marker.

## Task Commits

1. **Task 1: Screening-framing report wording + release docs** - `f669fe3` (feat)
2. **Task 2: Single conformance entry point + marker registration** - `3e7df7e` (feat)
3. **Task 3: Screening-framing + release-gate conformance tests** - `d5fe076` (test)

## Files Created/Modified
- `crawler/audit_report.py` - `SCREENING_NOTICE` constant + rendered into `_render_factor_card_markdown`.
- `crawler/README.md` - screening scope & limits section + release-gate command.
- `SCREENING.md` - authoritative release framing doc (86 lines).
- `scripts/run_conformance.py` - single conformance release-gate entry point.
- `pyproject.toml` - registered the `conformance` pytest marker.
- `crawler/tests/test_conformance_v40_screening_framing.py`, `..._release_gate.py` - the two new tests.
- `crawler/tests/test_full_audit_integration.py`, `test_full_audit_cutoff.py` - reconciled with the rendered notice (deviation, below).

## Decisions Made
- Keep the framing in rendered markdown + docs, not the strict `PublicAuditEnvelope` schema, to preserve the AUDIT-06 PII boundary.
- Select the suite by the file glob (marker-independent) so the gate is deterministic; the `conformance` marker is the documented alternative selector.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reconcile existing report-markdown tests with the rendered screening notice**
- **Found during:** Task 1 (screening-framing report wording)
- **Issue:** `test_full_audit_integration.test_sc4_cutoff_and_no_legal_advice` and `test_full_audit_cutoff.test_markdown_has_cutoff_line_no_legal_advice` asserted the bare substring "legal advice" was absent from the rendered report. The new `SCREENING_NOTICE` renders "not legal advice" into every report, so those bare-substring checks would fail.
- **Fix:** Both tests now normalize out the negated disclaimer ("not legal advice" / "not a substitute") before scanning for a bare legal-advice / eligibility claim, and additionally assert the screening framing IS present — preserving their original intent (no legal-advice CLAIM) while accommodating the required disclaimer.
- **Files modified:** `crawler/tests/test_full_audit_integration.py`, `crawler/tests/test_full_audit_cutoff.py`
- **Verification:** Both modules pass; the full suite is green (685 passed).
- **Committed in:** `f669fe3` (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1). 
**Impact on plan:** Necessary reconciliation of pre-existing tests with the SAFE-04 framing. No scope creep.

## Issues Encountered
None.

## Next Phase Readiness
Release gate green: `.venv/bin/python scripts/run_conformance.py` collects all five `test_conformance_v40_*.py` modules (SAFE-01..04 + release-gate) and passes (51 tests, exit 0). `check_publish_safe.py` is 0 violations over 284 tracked files. The v4.0 safety conformance layer is ready for the milestone audit.

---
*Phase: 34-safety-conformance-release-framing*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created files exist on disk; all task commit hashes are present in git history.
