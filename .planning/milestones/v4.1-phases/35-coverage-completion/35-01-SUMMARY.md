---
phase: 35-coverage-completion
plan: 01
subsystem: testing
tags: [crs, grounding, registry, yaml, pydantic, language-points, clb, unittest, pytest]

# Dependency graph
requires:
  - phase: 31-grounded-crs-rule-registry
    provides: "core.language.first.points grounded row + score_factor/_grounded_points level-generalized readers + no_inlined_volatile_rules gate"
  - phase: 33-full-modular-crs-auditor-pack
    provides: "label-based spouse/no-spouse column selection in score_factor/_grounded_points (with_spouse/without_spouse discriminators)"
  - phase: 30-extraction-quarantine
    provides: "real import->extract->confirm->audit seam test (test_full_audit_real_seam.py)"
provides:
  - "Grounded first-official-language points for EVERY conversion-emitted CLB benchmark {3,4,5,6,7,8,9,10} in both spouse and no-spouse modes"
  - "Anti-drift completeness pin: priced first-language level set == live conversion-emitted level set"
  - "Grounding pin: the core.language.first.points row grounds against the real corpus with zero violations"
  - "Corrected real-seam expectation: language card fully priced at no-spouse 130 / score_delta -6"
affects: [35-02-coverage-second-language, 35-04-sibling-seam, remediation, review-packet]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CLB band -> points mapping lives ONLY in grounded PointsEntry rows paired with verbatim #006 quotes (never a Python literal)"
    - "Completeness pin derives the expected level set LIVE from non-gap conversion rows (no hard-coded interval)"

key-files:
  created:
    - crawler/tests/test_language_points_coverage.py
  modified:
    - crawler/data/crs_rules/core.yaml
    - crawler/tests/test_full_audit_real_seam.py
    - crawler/tests/test_crs_audit.py

key-decisions:
  - "COV-01 closed data-only: six new #006 citations + CLB 3,4,5,6,7,8,10 PointsEntry pairs extend the ONE core.language.first.points row; no reader/decider code changed"
  - "Column semantics preserved verbatim: first #006 numeric column = with_spouse, second = without_spouse (CLB 9 = 29/31)"
  - "Fail-closed unmatched-level pin retargeted to CLB 11 (above the grounded ceiling) since COV-01 legitimately grounds CLB 3"

patterns-established:
  - "Pattern: every volatile CRS point value is a grounded YAML row with a verbatim corpus quote — the no_inlined_volatile_rules + conformance gates stay green"
  - "Pattern: anti-drift completeness test reads the emitted level set from the registry so a future conversion band without a matching point row fails loudly"

requirements-completed: [COV-01]

# Metrics
duration: 17min
completed: 2026-07-17
---

# Phase 35 Plan 01: Coverage Completion (COV-01) Summary

**Grounded first-official-language points for every conversion-emitted CLB benchmark {3–8,10} in both spouse/no-spouse modes via six verbatim #006 citations — closing the silent under-pricing gap with zero fabricated values, zero reader-code changes, and a live-derived anti-drift pin.**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-07-17T06:54:07Z
- **Completed:** 2026-07-17T07:11:01Z
- **Tasks:** 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Closed COV-01: `score_factor("core.language.first", lvl, mode)` now returns grounded points for every conversion-emitted benchmark `{3,4,5,6,7,8,9,10}` in both modes — no `None` (was `None` for every level except CLB 9), so a candidate whose lowest ability is not exactly CLB 9 is no longer silently under-priced to 0.
- Extended the single `core.language.first.points` registry row with six new `citations` (indexes 1–6, all `guidance/crs-criteria.md#006`) and `with_spouse`/`without_spouse` `PointsEntry` pairs for CLB 3,4,5,6,7,8,10 — every value paired with a corpus-verbatim quote; the row grounds with zero violations against the real `corpus/index.db`.
- Added an anti-drift + grounding pin (`test_language_points_coverage.py`) that derives the expected level set LIVE from the non-gap conversion rows and asserts the priced set is set-equal to it — a future conversion band without a matching point row now fails loudly instead of silently pricing 0.
- Corrected the stale real-seam expectation: the IELTS fixture (CLB 10/9/9/10) now proves the language card is fully priced at no-spouse **130** (`34+31+31+34`) with `score_delta == -6` (claimed 124 − 130), and the "MUST NOT be patched by touching the frozen registry" note is gone.
- No reader/decider code touched; `no_inlined_volatile_rules`, registry-conformance, and conversion-coverage gates all stay green.

## Task Commits

Each task was committed atomically (with `Co-authored-by: Copilot` trailer):

1. **Task 1: Wave 0 — COV-01 anti-drift + grounding pin (RED before data)** — `9182927` (test)
2. **Task 2: Ground CLB 3–8,10 first-language point rows (data-only, turns Task 1 GREEN)** — `0c58cb7` (feat)
3. **Task 3: Correct the stale CLB-10 real-seam note + strengthen the language assertion** — `4860547` (test)

**Plan metadata:** _(final docs commit — see below)_

_TDD gate sequence: RED `test` (9182927) → GREEN `feat` (0c58cb7) present in git log._

## Files Created/Modified
- `crawler/tests/test_language_points_coverage.py` *(created)* — stdlib `unittest` pin: `TestFirstLanguagePricingCompleteness` (live level-set derivation + both-mode pricing + priced==emitted anti-drift) and `TestFirstLanguagePricingGrounding` (skip-guarded on `corpus/index.db`, asserts the points row grounds with zero violations).
- `crawler/data/crs_rules/core.yaml` *(modified)* — extended the `core.language.first.points` row: six new `#006` citations + `PointsEntry` pairs for CLB 3,4,5,6,7,8,10 (points from the verified #006 columns).
- `crawler/tests/test_full_audit_real_seam.py` *(modified)* — replaced the stale CLB-10 comment; strengthened the language-card assertion to `substantiated_points == 130` and `score_delta == -6`; skip-guard and BLOCKER-A/B / cross-factor assertions unchanged.
- `crawler/tests/test_crs_audit.py` *(modified — deviation)* — retargeted the fail-closed unmatched-level pin from CLB 3 (now grounded by COV-01) to CLB 11.

## Decisions Made
- **Data-only closure.** COV-01 was closed entirely in grounded registry data; the level-generalized readers (`score_factor`, `_grounded_points`) and every decider were left byte-for-byte unchanged, honoring the locked "close coverage with corpus-grounded data; never fabricate a point value or relax a decider" decision.
- **Column semantics not transposed.** Verified against the shipped CLB-9 entry (`clb9_with_spouse=29`, `clb9_without_spouse=31`, quote `"CLB 9  | 29  | 31"`): the first #006 numeric column is `with_spouse`, the second is `without_spouse`.
- **All seven quotes pre-verified as verbatim substrings of chunk `guidance/crs-criteria.md#006`** before landing the data (checked directly against `corpus/index.db`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale fail-closed pin assumed CLB 3 is unpriced**
- **Found during:** Task 2 (regression sweep after the registry data change)
- **Issue:** `test_crs_audit.py::TestScoreFactorRealRegistry::test_unmatched_level_returns_none_over_real_registry` asserted `score_factor("core.language.first", 3, False, reg) is None`. COV-01 deliberately grounds CLB 3 (band "Less than CLB 4" → 0/0), so CLB 3 now prices at 0 and the assertion broke. The test's INTENT (prove `score_factor` returns `None` — never a guessed award — for a level no grounded row prices) is preserved by choosing a genuinely-unmatched level.
- **Fix:** Retargeted the pin to CLB 11 (above the grounded ceiling of 10) and updated the comment to reference the COV-01 closure.
- **Files modified:** `crawler/tests/test_crs_audit.py`
- **Verification:** `pytest crawler/tests/test_crs_audit.py` → 28 passed; `TestScoreFactorRealRegistry` → 4 passed.
- **Committed in:** `0c58cb7` (Task 2 commit — coupled to the data change that caused it)

---

**Total deviations:** 1 auto-fixed (1 bug — a stale test expectation directly invalidated by the in-scope registry change).
**Impact on plan:** The deviation is a required consequence of COV-01 (grounding CLB 3). No scope creep — the fix preserves the fail-closed intent while reflecting the new grounded coverage.

## Issues Encountered

- **Publish-safe planning-prose failure (resolved at the Phase 35 gate).** The Task 2 regression sweep surfaced two failing whole-tree scans caused by a research document quoting the scanner's absolute-home-prefix trigger examples. The implementation files introduced no violation. The phase closeout reworded the planning prose so the tracked-tree gate is green without weakening or allowlisting the scanner.

## User Setup Required

None — no external service configuration required. Zero new runtime dependencies (ships on the existing `pyyaml`/`pydantic`/`platformdirs` + stdlib stack); no DB migration.

## Next Phase Readiness
- COV-01 is closed and pinned: first-official-language points are complete for every emitted benchmark, grounded, and anti-drift-guarded.
- The real-seam language card is fully priced (130 / delta −6) and remains STRUCTURAL-ONLY skip-guarded on a fresh clone.
- Plan 35-02 (COV-02, unpriced-surfacing net for any residual `SUBSTANTIATED`-but-`None` card, e.g. second language at CLB≠9) and Plan 35-04 (sibling seam) build on this foundation. This plan intentionally leaves the sibling document addition in `test_full_audit_real_seam.py` to plan 35-04 (Wave 2).
- One pre-existing publish-safe violation in `.planning/research/PITFALLS.md` is deferred to operational hardening (Phase 36).

## Verification Evidence

- `pytest crawler/tests/test_language_points_coverage.py test_crs_rules_conformance.py test_crs_no_inlined_rules.py test_full_audit_real_seam.py -q` → **19 passed, 34 subtests passed**.
- `score_factor` over `core.language.first` for levels `(3..10)` × `(False,True)` prints `[0,0,6,6,6,6,9,8,17,16,23,22,31,29,34,32]` — **no `None`**.
- `grep -n 'MUST NOT be patched' crawler/tests/test_full_audit_real_seam.py` → no output (stale note removed).
- Regression: auditor / auditor-dispatch / auditors-additional / auditors-spouse / auditors-transferability / crs-registry / crs-audit / conversion-coverage suites → all green.

---
*Phase: 35-coverage-completion*
*Completed: 2026-07-17*

## Self-Check: PASSED

- `crawler/tests/test_language_points_coverage.py` — FOUND on disk.
- `.planning/phases/35-coverage-completion/35-01-SUMMARY.md` — FOUND on disk.
- Commits `9182927`, `0c58cb7`, `4860547` — all present in git log.
- `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer present on all three task commits.
- Plan verification (four suites) green; `score_factor` prints no `None`; stale note removed.
