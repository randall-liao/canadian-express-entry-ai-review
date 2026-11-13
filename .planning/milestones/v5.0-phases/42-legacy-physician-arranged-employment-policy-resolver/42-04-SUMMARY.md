---
phase: 42-legacy-physician-arranged-employment-policy-resolver
plan: 04
subsystem: testing
tags: [conformance, negative-control, crs-rules, arranged-employment, physician-public-policy, frozen-contracts, release-gate, no-false-green]

# Dependency graph
requires:
  - phase: 42-legacy-physician-arranged-employment-policy-resolver (plan 01)
    provides: "Grounded additional.job_offer.physician RuleRow + COVERAGE the synthetic registry mirrors; the retrieve-what-you-cite grounding proof this negative control complements"
  - phase: 42-legacy-physician-arranged-employment-policy-resolver (plan 02)
    provides: "decide_job_offer physician branch (AT-RISK/physician_policy_manual/None) + job_offer extraction doc type — the reachable decider outcomes this control sweeps"
  - phase: 42-legacy-physician-arranged-employment-policy-resolver (plan 03)
    provides: "policy_offer.offer_for_program_eligibility inert sidecar (constant crs_points=0, never SUBSTANTIATED) — the sidecar surface this control sweeps"
  - phase: 40-safe-freshness-effective-date-foundation
    provides: "crs_audit.row_in_effect + arranged_employment_guard the guard sweep drives across window edges"
provides:
  - "crawler/tests/test_conformance_v5_policy_no_job_offer_green.py — the exhaustive POLICY negative control proving NO additional.job_offer input/window/signal can yield SUBSTANTIATED or a non-zero/non-None award across the decider, the frozen guard, and the inert sidecar"
  - "Frozen-guard byte-identity conformance (git diff --quiet HEAD -- crawler/crs_audit.py, skip-guarded off git) proving the sole CRS-additional-points award chokepoint drifted zero this phase"
  - "Phase-42 release-gate closure evidence: full crawler/tests suite (1018 passed / 2 skipped), publish-safe, v4.x conformance, and zero-dependency gates all green with the physician row + branch + sidecar present"
affects: [43-noc-work-duty, 45-mec-sidecar, 46-safe-conformance-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Exhaustive negative-control conformance: drive the REAL production surfaces (decider + frozen guard + inert sidecar) over a synthetic registry across every window edge/input class and assert the forbidden outcome (SUBSTANTIATED / truthy award) is unreachable on EVERY path — proof-by-sweep, not by sampling"
    - "Frozen-guard byte-identity conformance: a git diff --quiet HEAD assertion scoped to a single shipped file, skip-guarded on a git checkout, proving zero drift of an award chokepoint independently of the deciders that consume it"
    - "v5-prefixed conformance file intentionally OUTSIDE the v4.x release-gate file glob (test_conformance_v4[01]_*.py) so it runs in the full suite now but is not enrolled into the v4.x gate until Phase 46 introduces the v5 glob"

key-files:
  created:
    - crawler/tests/test_conformance_v5_policy_no_job_offer_green.py
  modified: []

key-decisions:
  - "POLICY-01/02/03 marked COMPLETE only AFTER the phase release gates passed (full suite + publish-safe + v4.x conformance + zero-dep + frozen-guard byte-identity) — per the execution directive; the phase itself is left in VERIFYING (not Complete) for the verifier to sign off"
  - "Reused the synthetic-registry + by_field builders (_registry / _physician_row / _offer_factor / _val / _ctx / _PHYS_NOCS) from test_physician_policy.py rather than re-declaring the volatile physician date/NOC fixtures — the same cross-test-helper reuse precedent as test_conformance_v41_coverage.py; importing helper functions does NOT re-collect the donor module's TestCase classes"
  - "Tagged the module pytestmark = pytest.mark.conformance (registered marker) for module-style consistency with the sibling v4.x conformance files; this is SAFE because run_conformance.py selects the release gate by the file glob test_conformance_v4[01]_*.py (not by marker), so the v5 file is not enrolled into the v4.x gate and the release-gate self-checks (positive assertIn on specific v4.x modules) stay green"
  - "Task 2 (close the phase) is a verification-only gate task with no production code change, so it produced NO separate per-task commit — nothing was staged beyond Task 1's new test file"

patterns-established:
  - "Negative-control-by-sweep: enumerate every outcome a policy surface can produce and assert the dangerous verdict/award is structurally unreachable across all of them, driving the real functions (never a re-implementation) over a synthetic fixture registry"
  - "Single-file frozen byte-identity assertion (git diff --quiet HEAD -- <path>, @skipUnless(_GIT_ROOT is not None)) as a copy-forward conformance idiom for any shipped chokepoint that must not drift within a phase"

requirements-completed: [POLICY-01, POLICY-02, POLICY-03]

# Metrics
duration: 28min
completed: 2026-07-19
---

# Phase 42 Plan 04: POLICY Negative-Control Conformance & Release-Gate Closure Summary

**Shipped `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` — the exhaustive negative control proving NO `additional.job_offer` input, window, or physician signal can ever yield `SUBSTANTIATED` or a non-zero/non-`None` CRS additional-points award across the real decider, the frozen `arranged_employment_guard`, and the inert offer-for-eligibility sidecar — plus a byte-identity assertion that `crawler/crs_audit.py` stayed frozen — then closed the phase with the full suite (1018 passed / 2 skipped), publish-safe, the v4.x conformance gate, and the zero-dependency gate all green.**

## Performance

- **Duration:** ~28 min (dominated by the ~19-min full-suite regression run)
- **Started:** 2026-07-19T04:40:38Z
- **Completed:** 2026-07-19T05:09:02Z
- **Tasks:** 2 (1 test-authoring, 1 verification-only release gate)
- **Files modified:** 1 (1 created, 0 production files touched)

## Accomplishments
- **Exhaustive decider sweep (POLICY-01/02/03, T-42-01/03).** `TestNoJobOfferPathGreens` drives the REAL `additional.decide_job_offer` over a matrix of missing / unconfirmed (no-ITA) / stale / malformed-window / non-physician / legacy-edge (2024-06-01) / post-repeal (2026-01-01) / physician / zero-claim inputs — including EVERY physician NOC in the accepted set across all three windows — and asserts for every case `verdict != "SUBSTANTIATED"`, `substantiated_points in (None, 0)`, non-truthy points, and a verdict in `{AT-RISK, N/A}`. No path greens.
- **Frozen award-chokepoint sweep (T-42-01).** `TestGuardNeverGreens` proves `crs_audit.arranged_employment_guard` returns `status != "SUBSTANTIATED"` and `points in (None, 0)` for a non-zero claim (1 … 100 000) across the legacy edge and post-repeal, and `status == "N/A"` / `points == 0` for a zero claim.
- **Inert sidecar sweep (T-42-04).** `TestSidecarNeverGreens` proves `policy_offer.offer_for_program_eligibility` returns a constant `crs_points == 0` and `eligibility_status != "SUBSTANTIATED"` (AT-RISK present / N/A absent) for `claim_points ∈ {0, 200, 999}` across both window edges, and stays constant-0 even with no current row present.
- **Frozen-guard byte-identity (T-42-06).** `TestFrozenGuardByteIdentity` asserts `git diff --quiet HEAD -- crawler/crs_audit.py` exits 0 (byte-for-byte frozen), copied from `test_dli_conformance.py::TestFrozenContractsUnchanged` and `@skipUnless(_GIT_ROOT is not None)`-guarded so it skips cleanly off a git checkout. It RAN (not skipped) and PASSED this session.
- **Phase release-gate closure.** Full `crawler/tests` suite = **1018 passed / 2 skipped / 468 subtests** (at/above the 988/2 pre-phase baseline plus every phase-42 POLICY addition); publish-safe = **412 tracked files, 0 violations**; `scripts/run_conformance.py` = **PASS (77 passed, SAFE-01..08)** with the v5 file correctly absent from the gate's module list; zero-dependency test = **2 passed** (pinned `{pyyaml, pydantic, platformdirs}` intact); `crawler/crs_audit.py` and `scripts/run_conformance.py` both show **zero git diff vs HEAD**.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author the v5 POLICY negative-control conformance (no job-offer path greens; guard byte-frozen)** - `c44e655` (test)
2. **Task 2: Close the phase — full suite, publish-safe, v4.x conformance, and zero-dep gates all green** - _(verification-only release gate; no production change, so no separate commit)_

**Plan metadata:** _(final docs commit — 42-04-SUMMARY.md + STATE.md + ROADMAP.md + REQUIREMENTS.md)_

## Files Created/Modified
- `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` **[created]** — The v5 POLICY negative-control conformance module (320 lines). Four `unittest` classes: `TestNoJobOfferPathGreens` (exhaustive decider sweep), `TestGuardNeverGreens` (frozen-guard sweep across window edges), `TestSidecarNeverGreens` (inert-sidecar constant-0 sweep), and `TestFrozenGuardByteIdentity` (git-diff byte-identity, skip-guarded). Reuses the synthetic-registry/by_field fixtures from `test_physician_policy.py`; inlines no production policy literal; marker-tagged `conformance`. Name intentionally NOT matched by the v4.x release-gate glob `test_conformance_v4[01]_*.py`.

## Decisions Made
- **POLICY-01/02/03 marked complete only after the gates passed.** Per the execution directive, the three POLICY requirements were flipped from `Pending` to `Complete` ONLY after the full suite, publish-safe, v4.x conformance, zero-dep, and frozen-guard byte-identity all went green. The phase status is left in **Verifying** (not Complete) for the verifier to sign off — the plan closes the negative-control conformance, not the phase gate itself.
- **Genuine fixture reuse over re-declaration.** The volatile physician date/NOC values live only in the grounded row and the reused `test_physician_policy.py` fixtures; the new module imports those helpers (cross-test-helper reuse, the same precedent as `test_conformance_v41_coverage.py`) rather than re-inlining any literal — keeping the no-inlined discipline intact and the negative control driving the REAL functions.
- **`conformance` marker is safe here.** `run_conformance.py` selects the v4.x release gate by file glob, not by marker, and the release-gate self-checks assert specific v4.x modules are present (positive `assertIn`), so tagging the v5 file `conformance` neither enrols it into the v4.x gate nor breaks a self-check.
- **Task 2 produced no commit.** It is a verification-only phase-close gate with zero production changes; nothing beyond Task 1's new test file was staged.

## Deviations from Plan

None — plan executed exactly as written.

Both tasks were implemented to the plan's recommended shape: Task 1's four conformance classes assert exactly the `!= SUBSTANTIATED` / `points in (None, 0)` / `crs_points == 0` invariants across the decider, guard, and sidecar plus the `git diff --quiet HEAD -- crawler/crs_audit.py` byte-identity (copied from `test_dli_conformance.py::TestFrozenContractsUnchanged` with the `@skipUnless(_GIT_ROOT is not None)` guard); Task 2 ran the full suite + publish-safe + v4.x conformance + zero-dep + guard-frozen gates and confirmed all green. `scripts/run_conformance.py` was not touched, no decider was relaxed, and no assertion was weakened. The v5 file is intentionally outside the v4.x release-gate glob (Phase-46 concern), as specified.

## Issues Encountered
- **Full-suite runtime.** The complete `crawler/tests` suite runs ~19 minutes here because the real git-ignored `corpus/index.db` (16 MB) is present, so the grounding / retrieve-what-you-cite / extraction real-seam tests execute rather than skip. Under `pytest -q` piped to `tail`, progress is buffered until completion (matching the 42-01 note), so the run was executed asynchronously and its exit code + `1018 passed / 2 skipped` summary confirmed on completion (exit 0). No hang — the process ran at ~88% CPU throughout. All fast gates (publish-safe, v4.x conformance, zero-dep, guard-frozen) were additionally re-run as a chain that emitted `PHASE_GATES_GREEN`.

## User Setup Required

None — no external service configuration required. Zero new dependencies; the new module is stdlib `unittest` only, with no network and no vault.

## Known Stubs
None. The new file is a live, executing conformance module (6 tests / 41 subtests, all passing, none skipped in a git checkout). No placeholder assertions, no `pass`-only tests, no unwired fixtures were introduced.

## Threat Flags
No new security surface introduced beyond the plan's `<threat_model>`. This plan adds only a negative-control test module (no production code, no new endpoint/auth/file-access/schema surface):
- **T-42-01** (legacy/physician auto-green): swept exhaustively — `TestNoJobOfferPathGreens` + `TestGuardNeverGreens` + `TestSidecarNeverGreens` prove every outcome is `!= SUBSTANTIATED` with `points in (None, 0)` / `crs_points == 0`.
- **T-42-03** (physician NOC spoof): every physician NOC in the set caps at `AT-RISK`/`physician_policy_manual`/`None` across all windows — no green to reach.
- **T-42-04** (sidecar wiring/PII): the sidecar sweep confirms constant-0/never-green; publish-safe (412 files, 0 violations) confirms PII-free.
- **T-42-06** (frozen-guard drift): `git diff --quiet HEAD -- crawler/crs_audit.py` exits 0 (byte-frozen), asserted both in the new module and `test_dli_conformance.py`.
- **T-42-02 / T-42-05** (ungrounded/inlined policy, cross-factor contamination): re-run green in the full suite (grounding + no-inlined gate + physician linkage).
- **T-42-SC** (supply-chain): zero new deps; the frozen-dep-set test passes.

## Next Phase Readiness
- **Ready for the phase verifier:** POLICY-01/02/03 are now `Complete` in REQUIREMENTS.md (gates green); the phase is left in **Verifying** for sign-off, not marked Complete.
- **Ready for Phase 46 (SAFE conformance gate):** the v5-prefixed negative control is in place and green in the full suite; Phase 46 introduces the `test_conformance_v5_*` release-gate glob that will enrol it into the gate runner (no change to `scripts/run_conformance.py` this phase).
- **Ready for Phase 45 (MEC sidecar):** the inert `policy_offer.offer_for_program_eligibility` contract is proven constant-0 / never-green over an exhaustive sweep, so Phase 45 can wire it as an AT-RISK program-eligibility input with the negative control guarding against regression.
- **No blockers.** `crawler/crs_audit.py` remains byte-for-byte frozen; the zero-dependency baseline is intact; `scripts/run_conformance.py` is untouched.

---
*Phase: 42-legacy-physician-arranged-employment-policy-resolver*
*Completed: 2026-07-19*

## Self-Check: PASSED

- Created file verified present on disk: `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` (320 lines), and `42-04-SUMMARY.md`.
- Task commit verified in git history: `c44e655` (test, Task 1). Task 2 is verification-only with no commit (expected).
- Artifact `contains` assertion satisfied: the new module contains the string `arranged_employment_guard`; the plan's `key_links` patterns `SUBSTANTIATED` and `crs_audit.py` are both present.
- Plan verification re-run this session: new module → 6 passed / 41 subtests (frozen-guard test RAN, not skipped); full `crawler/tests` suite → 1018 passed / 2 skipped / 468 subtests; publish-safe → 412 files / 0 violations; `run_conformance.py` → PASS (77 passed, v5 file absent from the gate module list); zero-dep → 2 passed; `git diff --quiet HEAD -- crawler/crs_audit.py` and `-- scripts/run_conformance.py` → both exit 0.
