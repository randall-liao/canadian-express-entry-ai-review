---
phase: 33-full-modular-crs-auditor-pack
plan: 07
subsystem: audit
tags: [crs, spouse-mode, scoring, grounded-registry, python, pytest]

# Dependency graph
requires:
  - phase: 33-01
    provides: core human-capital deciders + _grounded_points label-selection pattern (the correct mode-aware lookup this fix mirrors)
  - phase: 33-02
    provides: full-grid dispatch spine (audit_one → score_factor per ability via _sum_points)
  - phase: 33-06
    provides: full-grid integration harness (_IntegrationCase) + run_full_audit_report + vault audit --all
provides:
  - "Mode-aware score_factor: core-group factors select the grounded with_spouse/without_spouse column by label in BOTH modes; spouse_common_law rows stay gated to spouse mode"
  - "Spouse-mode core language cards now populate substantiated_points/score_delta (SC3/AUDIT-04) and contribute to the substantiated total (SC4/AUDIT-05)"
  - "Unit regression suite for spouse-column selection + transferability no-leak; end-to-end spouse-mode language points assertion"
affects: [phase-34-safety-conformance-release-framing, crs-auditor, vault-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Label-based mode-column selection (with_spouse / without_spouse) reused from core._grounded_points inside crs_audit.score_factor"

key-files:
  created: []
  modified:
    - crawler/crs_audit.py
    - crawler/tests/test_crs_audit.py
    - crawler/tests/test_full_audit_integration.py

key-decisions:
  - "score_factor selects the mode column by grounded LABEL (not by factor_group), so spouse mode no longer drops the owning core_human_capital language row"
  - "factor_ids[0] ownership guard + cap clamp + fail-closed None preserved verbatim — no CLB-9 transferability tier leak, no inlined volatile literal"

patterns-established:
  - "Core factors encode both spouse columns as labelled PointsEntry rows inside one owning row; spouse_common_law rows are the spouse's OWN factors, gated to spouse mode only"

requirements-completed: [AUDIT-04, AUDIT-05]

# Metrics
duration: 15min
completed: 2026-07-06
---

# Phase 33 Plan 07: Spouse-Mode score_factor Gap Closure Summary

**`crs_audit.score_factor` now selects the grounded `with_spouse`/`without_spouse` column by label for core factors in BOTH modes — spouse-mode core language cards populate `substantiated_points=116` / `score_delta=8` and are counted in the substantiated total, while the `factor_ids[0]` ownership guard, cap clamp, and no-inlined-literal gate are preserved.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-06T09:01:20Z
- **Completed:** 2026-07-06T09:12:00Z
- **Tasks:** 3 (Task 1 executed TDD: RED → GREEN)
- **Files modified:** 3

## Accomplishments
- Rewrote `score_factor` to mirror the proven `crawler/auditors/core._grounded_points` label selection: core-group rows are visited in both spouse and no-spouse mode and the mode column is chosen from the entry whose label carries `with_spouse` (resp. `without_spouse`); `spouse_common_law` rows remain gated to spouse mode only.
- Closed **SC3/AUDIT-04**: spouse-mode `core.language.first` now reaches SUBSTANTIATED with a non-blank `substantiated_points` (116 = 4 × grounded `clb9_with_spouse` 29) and `score_delta` (8 = claimed 124 − 116).
- Closed **SC4/AUDIT-05**: the spouse-mode substantiated CRS total now includes the with-spouse language points (verified end-to-end and via `vault audit --all` against the real corpus — no ~116-point undercount).
- Preserved the transferability `factor_ids[0]` ownership fix (decoy `transfer.foreign_language` tier of 50 never leaks into `core.language.first`), cap clamping, no-spouse language = 124 / delta 0, and the `no_inlined_volatile_rules` self-scan (clean).
- Added a unit regression suite (labelled-column selection, second-language fallback, no-leak, unmatched-level) and an end-to-end spouse-mode integration class.

## Task Commits

Each task was committed atomically (with `Co-authored-by: Copilot` trailer):

1. **Task 1 (TDD RED): failing real-registry spouse-column tests** — `41a36af` (test)
2. **Task 1 (TDD GREEN): mode-aware label-based score_factor** — `d173ffa` (feat)
3. **Task 2: unit regression (spouse column, no transferability leak)** — `dda0ee3` (test)
4. **Task 3: end-to-end spouse-mode language points assertions** — `5fbc0e6` (test)

**Plan metadata:** _(docs commit for SUMMARY/STATE/ROADMAP/REQUIREMENTS — see final commit)_

_Note: Task 1 is a TDD task, hence its two commits (test → feat). No REFACTOR commit was needed — the implementation was minimal and clear._

## Files Created/Modified
- `crawler/crs_audit.py` — Rewrote `score_factor`: replaced the `(factor_group == "spouse_common_law") != spouse_mode` row filter (which dropped core rows in spouse mode) with a `spouse_common_law and not spouse_mode` skip + label-based mode-column selection; ownership guard, cap clamp, and fail-closed None retained; docstring updated (no `clb9`/`CLB 9` literal that would trip the self-scan).
- `crawler/tests/test_crs_audit.py` — Added `TestScoreFactorRealRegistry` (real-registry Task-1 behavior) + `_labelled_core_language_registry()` helper and four named tests inside `TestSpouseMode`; existing `_spouse_mode_registry`, `test_spouse_vs_no_spouse_diverge`, `test_unknown_value_returns_none`, and cap/aggregation tests untouched and still green.
- `crawler/tests/test_full_audit_integration.py` — Added `TestSpouseModeLanguagePoints(_IntegrationCase)` with `_seed_spouse_language` + three tests (with-spouse card fields, substantiated total inclusion, no-spouse-unchanged).

## Decisions Made
- **Label over group for the mode column.** The correct signal for a core factor's spouse/no-spouse column is the `PointsEntry.label` inside its ONE owning `core_human_capital` row, not the row's `factor_group` — the old group-based filter was the root cause of the spouse-mode `None`. Mirrored `core._grounded_points` exactly so the two lookups stay consistent.
- **Kept `spouse_common_law` gating semantically distinct.** Spouse-owned rows (the partner's own factors) still contribute only when a spouse is present (`row.factor_group == "spouse_common_law" and not spouse_mode: continue`), so `test_spouse_vs_no_spouse_diverge` (31 vs 5, with the section cap) stays green.
- **No numeric literals in production code.** With-spouse points (29/116) come only from grounded rows; test files assert on computed output (allowed), keeping the `crs_audit.py` self-scan clean.

## Deviations from Plan

None — plan executed exactly as written. All three invariants (ownership, spouse-mode gating, cap clamp) were preserved as specified, the self-scan gate stayed clean, and no package installs or architectural changes were required.

## Issues Encountered
- **Self-scan trip on docstring (resolved during Task 1 GREEN, pre-commit).** My first docstring draft used the concrete labels `clb9_with_spouse` / `clb9_without_spouse` as examples; the `no_inlined_volatile_rules` `_CLB_RE` (`\b(?:CLB|NCLC)\s*\d+`) matched the `clb9` token and flagged `crawler/crs_audit.py`. Reworded the docstring to the generic `*_with_spouse` / `*_without_spouse` label forms (mirroring how `core._grounded_points` avoids concrete benchmark tokens). The self-scan then reported `[]`. Caught and fixed before the GREEN commit, so no bad commit landed. (Threat T-33-18 mitigation held.)

## Verification Results
- `.venv/bin/python -m pytest crawler/tests scripts/tests --deselect crawler/tests/test_dupaudit.py -q` → **634 passed, 1 skipped, 26 deselected, 195 subtests** (baseline was 623 passed; exactly +11 new tests: 4 real-registry + 4 unit regression + 3 integration). No regressions across Phases 29–33 or the frozen trust path.
- `.venv/bin/python -m pytest crawler/tests/test_crs_audit.py crawler/tests/test_full_audit_integration.py -q` → green (28 + 10).
- `.venv/bin/python scripts/check_publish_safe.py` → **0 violations** (276 tracked files scanned; PII perimeter untouched).
- `no_inlined_volatile_rules(["crawler/crs_audit.py"])` → `[]` (ASVS L1 integrity self-scan clean).
- **`vault audit --all` (synthetic spouse-mode full profile vs REAL corpus):** exit 0, envelope `ok:true`, stdout PII-light (no applicant values). Vault-only card detail: `core.language.first` = SUBSTANTIATED, **substantiated_points = 116** (4 × grounded with-spouse 29), **score_delta = 8**, and the language points are included in the **substantiated CRS total (344)** — no undercount with language at 0.

## Threat Flags
None — no new network endpoint, auth path, file-access pattern, or trust-boundary schema change. The change is a pure-arithmetic source edit plus tests; STRIDE register items T-33-18/19/20 are mitigated (grounded-only points, fail-closed None, ownership guard proven by the decoy test) and T-33-SC (package installs) remained `accept` (no new dependencies).

## Next Phase Readiness
- Phase 33 gap closure complete — AUDIT-04 and AUDIT-05 now hold for spouse-mode candidates end-to-end. Ready for `/gsd-execute-phase 34` (Safety Conformance & Release Framing).
- No blockers introduced. The frozen trust path, PII perimeter, and no-inlined-literal integrity gate are all intact.

---
*Phase: 33-full-modular-crs-auditor-pack*
*Completed: 2026-07-06*

## Self-Check: PASSED

- Files verified on disk: `33-07-SUMMARY.md`, `crawler/crs_audit.py`, `crawler/tests/test_crs_audit.py`, `crawler/tests/test_full_audit_integration.py` — all FOUND.
- Commits verified in git history: `41a36af` (test/RED), `d173ffa` (feat/GREEN), `dda0ee3` (test), `5fbc0e6` (test) — all FOUND.
