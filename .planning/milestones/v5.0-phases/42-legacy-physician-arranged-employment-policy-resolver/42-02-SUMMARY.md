---
phase: 42-legacy-physician-arranged-employment-policy-resolver
plan: 02
subsystem: crs-auditors
tags: [crs-rules, arranged-employment, physician-public-policy, decider-branch, extraction, factor-linkage, grounding, frozen-contracts, fail-closed]

# Dependency graph
requires:
  - phase: 42-legacy-physician-arranged-employment-policy-resolver (plan 01)
    provides: "Grounded additional.job_offer.physician RuleRow (accepted_enum NOC set 31100/31101/31102 + effective_from 2023-04-25) the branch reads via machine_check.accepted_values + row_in_effect"
  - phase: 40-safe-freshness-effective-date-foundation
    provides: "crs_audit.row_in_effect effective-window predicate the physician branch CONSUMES (no re-added window math)"
  - phase: 30-extraction-quarantine-field-confirmation
    provides: "_DOC_TYPE_FACTOR per-document claimed-only factor linkage (_resolve_factor) the job_offer doc type extends"
provides:
  - "decide_job_offer physician branch: a confirmed noc_code in the grounded accepted-NOC set AND row_in_effect(phys, ita_date) → AT-RISK / physician_policy_manual / substantiated_points=None (distinct citation, fires BEFORE the frozen guard, never an award)"
  - "job_offer extraction doc type routing noc_code (+ inert issuer/employment_start) to additional.job_offer (reused FieldName, no vault migration, claimed-only, contamination-free)"
  - "test_physician_policy.py: physician/branch-order/legacy-repeal + per-document NOC non-leak + no-inlined self-scan (POLICY-02 decider + evidence path)"
  - "job_offer_pdf() born-digital physician-NOC fixture"
affects: [42-03-inert-sidecar, 42-04-negative-control-conformance, 43-noc-work-duty, 45-mec-sidecar]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Distinct grounded decider branch inserted BEFORE a frozen guard delegation: reads the NOC set + effective window from the grounded row, CONSUMES row_in_effect, caps at AT-RISK/manual (never an award), and delegates every other path to the frozen guard unchanged"
    - "Per-document claimed-only factor linkage extended to a NEW doc type by data alone (_FIELD_SPECS + _DOC_TYPE_FACTOR), reusing a FieldName already in the closed vocabulary → zero vault migration, zero cross-factor contamination"
    - "Fail-closed on a malformed grounded date via try/except (TypeError, ValueError), mirroring decide_sibling's age_on_date guard — a malformed window is treated as not-in-effect, never swallowed into a True"

key-files:
  created:
    - crawler/tests/test_physician_policy.py
  modified:
    - crawler/auditors/additional.py
    - crawler/extraction.py
    - crawler/tests/fixtures/extraction/make_fixtures.py

key-decisions:
  - "POLICY-02 kept PENDING (requirements-completed: []) — the physician decider + evidence path ship here, but the phase-wide negative-control conformance that proves NO additional.job_offer path can auto-green lands in 42-04; mirrors 42-01's decision to keep POLICY requirements pending until the resolver is complete end-to-end"
  - "substantiated_points=None (not 0) for the physician verdict — matches the legacy 'manual resolution' shape (A1 in 42-RESEARCH judged 0 equally safe); the physician case is a legal edge requiring human review, distinct from the current-policy AT-RISK/0"
  - "Physician branch inserted AFTER the ita_date-is-None guard and BEFORE the frozen arranged_employment_guard — branch order is load-bearing because the open physician window [2023-04-25, ∞) overlaps the legacy window (-∞, 2025-03-25); wrong order would surface arranged_employment_legacy_manual instead of the distinct physician citation (Pitfall 4 / POLICY-02)"
  - "job_offer doc type reuses the SHARED noc_code spec (already in the closed FieldName vocabulary) rather than adding a physician_noc FieldName — no vault schema migration, no PARSER_VERSION bump, no confirm-CLI change (42-PATTERNS §8)"

patterns-established:
  - "Grounded-branch-before-frozen-guard: a new distinct verdict reads all volatile values (NOC set + date) from the grounded row and consumes the shipped effective-window predicate, then falls through to the byte-frozen guard for every non-matching path — additive, no guard edit, no inlined literal"
  - "Contamination-free doc-type extension: a value's factor is a property of the DOCUMENT resolved once by claimed-only _resolve_factor, so a job_offer NOC → additional.job_offer and an employment_reference NOC → core.work never mix, and an unclaimed target leaves the value unlinked (fail-closed)"

# Metrics
duration: 8min
completed: 2026-07-19
---

# Phase 42 Plan 02: Physician Decider Branch & job_offer Evidence Path Summary

**Made the physician public-policy verdict reachable through real confirmed evidence and capped fail-closed: a distinct `decide_job_offer` branch resolves a confirmed physician `noc_code` in the grounded, in-effect window to `AT-RISK`/`physician_policy_manual`/`substantiated_points=None` (fired BEFORE the byte-frozen `arranged_employment_guard`), and a new `job_offer` extraction doc type routes that NOC to `additional.job_offer` per-document with no cross-factor contamination and no vault migration.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-19T03:56:44Z
- **Completed:** 2026-07-19T04:04:53Z
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Added a DISTINCT physician public-policy branch to `decide_job_offer` (inserted after the `ita_date is None` guard, before the frozen `arranged_employment_guard`): it looks up the grounded `additional.job_offer.physician` row, matches the confirmed `noc_code` against `machine_check.accepted_values` (READ from the row — no inlined literal), gates on `crs_audit.row_in_effect(phys, ita_date)` inside a fail-closed `try/except`, and returns `AT-RISK`/`physician_policy_manual`/`substantiated_points=None` — never `SUBSTANTIATED`, never an award. Every other path (non-physician / missing-NOC / None-ITA / post-repeal / malformed-window) delegates to the frozen guard byte-behavior-identically.
- Proved branch-order (Pitfall 4 / POLICY-02): a physician NOC inside the OVERLAPPING legacy window still yields the distinct `physician_policy_manual` reason, not `arranged_employment_legacy_manual`.
- Added the `job_offer` extraction doc type — `_FIELD_SPECS["job_offer"]` reuses the shared `noc_code` spec (name already in the closed `FieldName` vocabulary → no vault migration) plus inert `issuer`/`employment_start` fields, and `_DOC_TYPE_FACTOR["job_offer"] = "additional.job_offer"` — so a confirmed physician NOC on a `job_offer` document actually reaches `decide_job_offer`'s `by_field`.
- Proved the evidence path over the REAL `import→extract` seam: a `job_offer` NOC links to `additional.job_offer`, an `employment_reference` NOC links to `core.work`, with a proven non-leak in both directions, and an UNCLAIMED `additional.job_offer` leaves the NOC unlinked (fail-closed).
- Kept the frozen stack frozen: `crawler/crs_audit.py` shows zero git diff (consumed, not edited); the no-inlined static gate over `crawler/auditors/` stays `[]`; the `2023-04-25` date and `31100/31101/31102` NOC set appear in NO Python literal (only in the grounded row and — as test fixtures — the test file, which the gate does not scan).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the distinct physician public-policy branch to decide_job_offer** - `e3ef707` (feat)
2. **Task 2: Add the job_offer extraction doc type + fixture and prove per-document NOC linkage** - `45e5399` (feat)

**Plan metadata:** _(final docs commit — 42-02-SUMMARY.md + STATE.md + ROADMAP.md)_

## Files Created/Modified
- `crawler/auditors/additional.py` — Inserted the physician branch into `decide_job_offer` (grounded NOC-set + `row_in_effect` match → `AT-RISK`/`physician_policy_manual`/`None`; fail-closed `try/except`; delegates all other paths to the frozen guard unchanged). Rest of the function preserved verbatim; docstring extended to describe the branch.
- `crawler/extraction.py` — Added `_FIELD_SPECS["job_offer"]` (reused `noc_code` spec + inert `issuer`/`employment_start`) and `_DOC_TYPE_FACTOR["job_offer"] = "additional.job_offer"`. No `FieldName` change, no other doc-type mapping touched.
- `crawler/tests/fixtures/extraction/make_fixtures.py` — Added `FAKE_PHYSICIAN_NOC` (synthetic, distinct from `FAKE_NOC`) and `job_offer_pdf()` (born-digital physician offer carrying a physician `NOC Code:` line + employer + start date). `employment_reference_pdf`/`eca_pdf` unchanged.
- `crawler/tests/test_physician_policy.py` **[created]** — `TestPhysicianBranch` (in-window / branch-order / legacy / current / missing-NOC / None-ITA / malformed-window / zero-claim), `TestNoInlinedRules` (scans `ad.__file__`), and `TestJobOfferExtractionLinkage` (real seam: per-document NOC linkage + non-leak both ways + unclaimed-unlinked).

## Decisions Made
- **POLICY-02 kept PENDING.** Per the execution directive (and mirroring 42-01), POLICY-02 stays `Pending` in REQUIREMENTS.md — this plan delivers the physician decider branch + evidence path, but the phase's negative-control conformance proving NO `additional.job_offer` path can auto-green lands in 42-04. Marking it complete now would be premature.
- **`substantiated_points=None` for the physician verdict.** Matches the legacy manual-resolution shape (42-RESEARCH A1 judged `0` equally safe); the physician case is a legal edge requiring human review, kept distinct from the current-policy `AT-RISK`/0.
- **Branch order is load-bearing.** The physician check fires before the frozen guard because the open physician window overlaps the legacy window; wrong order would lose the distinct physician citation (Pitfall 4).
- **Reused the shared `noc_code` FieldName.** The `job_offer` doc type routes the existing `noc_code` (already in the closed vocabulary) — no vault schema migration, no PARSER_VERSION bump, no confirm-CLI change.

## Deviations from Plan

None - plan executed exactly as written.

Both tasks — the physician branch (exact recommended shape from 42-RESEARCH §Code Examples / 42-PATTERNS §2, delegating unchanged), the `job_offer` doc type + `_DOC_TYPE_FACTOR` entry (42-PATTERNS §8), the `job_offer_pdf()` fixture, and `test_physician_policy.py`'s three classes — were implemented as specified. The `decide_job_offer` docstring was extended to describe the new branch (an in-scope clarification of behavior, contains no volatile literal, and the no-inlined gate stays clean); this is documentation of the required change, not a deviation.

## Issues Encountered
None. All targeted and regression suites passed on the first full run; the frozen guard stayed byte-for-byte unchanged; the no-inlined static gate stayed clean throughout.

## Verification Evidence
- `.venv/bin/python -m pytest crawler/tests/test_physician_policy.py crawler/tests/test_auditors_additional.py crawler/tests/test_extraction_factor_linkage.py crawler/tests/test_extraction.py crawler/tests/test_crs_no_inlined_rules.py -q` → **66 passed, ~15s** (< 120 s).
- Task-1 gate: `test_physician_policy.py test_auditors_additional.py test_crs_no_inlined_rules.py` → **33 passed, 0.38s**.
- Task-2 gate: `test_physician_policy.py -k "extract or vault or signal or linkage"` → **3 passed, 9 deselected**; `test_extraction_factor_linkage.py test_extraction.py` → **30 passed**.
- 42-VALIDATION 42-02-02 selector `test_physician_policy.py -k "extract or vault or signal"` → collects EXACTLY the 3 `TestJobOfferExtractionLinkage` tests (3/12, 9 deselected).
- `git diff --quiet HEAD -- crawler/crs_audit.py` → exit **0** (frozen guard consumed, not edited).
- `grep -nE '\b(31100|31101|31102|2023-04-25)\b' crawler/auditors/additional.py crawler/extraction.py` → **no matches** (no inlined volatile literal; values come only from the grounded row).

## Known Stubs
None. The physician branch and the `job_offer` doc type are fully implemented and exercised end-to-end over the real extraction seam. No hardcoded empty values, placeholders, or unwired data paths were introduced. The inert offer-for-eligibility sidecar (a separate surface) is intentionally out of scope here and lands in 42-03.

## Threat Flags
No new security surface introduced beyond the plan's `<threat_model>`.
- **T-42-01** (auto-green): the physician branch returns `AT-RISK`/`physician_policy_manual`/`substantiated_points=None` ONLY and delegates every award to the frozen guard — no `SUBSTANTIATED`, no non-zero (asserted by `TestPhysicianBranch`).
- **T-42-03** (physician NOC spoof / unconfirmed): match is exact `noc ∈ grounded accepted_enum` AND `row_in_effect`; the value arrives only via the confirmed audit-eligible vault gate; even a spoofed physician NOC caps at `AT-RISK`/manual (there is no green to reach).
- **T-42-05** (cross-factor contamination): `_resolve_factor` is per-document, claimed-only, parameterized; `job_offer` NOC → `additional.job_offer`, `employment_reference` NOC → `core.work`, proven non-leak both ways; unclaimed target → unlinked.
- **T-42-06** (frozen-guard drift): the branch CONSUMES `row_in_effect`/`arranged_employment_guard`; `crawler/crs_audit.py` is never edited (zero git diff).
- **T-42-02** (inlined volatile rule): NOC set + date READ from `phys.machine_check`; no Python literal (`no_inlined_volatile_rules` over `crawler/auditors/` stays `[]`).
- **T-42-SC** (supply-chain): zero new deps; no install.
The `job_offer` document is read through the existing extraction pipeline (same path as `employment_reference`) — no new network endpoint, auth path, or file-access pattern.

## Next Phase Readiness
- **Ready for 42-03 (inert sidecar):** `test_physician_policy.py`'s `TestNoInlinedRules` scans `[ad.__file__]` and is ready to add the sidecar file to the scan; the `-k sidecar` selector slot is reserved.
- **Ready for 42-04 (negative-control conformance):** the physician verdict is reachable end-to-end (confirmed NOC → `job_offer` doc → `by_field` → `physician_policy_manual`), so the negative control can assert NO `additional.job_offer` path returns `SUBSTANTIATED`/non-zero/non-`None`.
- **No blockers.** `crawler/crs_audit.py` remains frozen; POLICY-01/02/03 stay `Pending` until 42-03/42-04 close them.

---
*Phase: 42-legacy-physician-arranged-employment-policy-resolver*
*Completed: 2026-07-19*

## Self-Check: PASSED

- Files verified present on disk: `test_physician_policy.py` (created), `additional.py`, `extraction.py`, `make_fixtures.py` (modified), `42-02-SUMMARY.md`.
- Task commits verified in git history: `e3ef707` (feat, Task 1), `45e5399` (feat, Task 2).
- `physician_policy_manual` confirmed in `crawler/auditors/additional.py`; `"job_offer": "additional.job_offer"` confirmed in `crawler/extraction.py`.
- Plan-level verification re-run: **66 passed** across `test_physician_policy.py` + `test_auditors_additional.py` + `test_extraction_factor_linkage.py` + `test_extraction.py` + `test_crs_no_inlined_rules.py` (< 120 s); `crs_audit.py` zero diff vs HEAD; no inlined `31100/31101/31102/2023-04-25` literal in `additional.py`/`extraction.py`.
