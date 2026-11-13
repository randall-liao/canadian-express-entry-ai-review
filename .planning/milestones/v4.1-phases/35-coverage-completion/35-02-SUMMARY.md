---
phase: 35-coverage-completion
plan: 02
subsystem: api
tags: [crs, audit, pydantic, pii-boundary, envelope, unresolved, unpriced, unittest]

# Dependency graph
requires:
  - phase: 32-crs-auditor
    provides: "two-tier audit models (PrivateFactorCard / PublicAuditEnvelope), the to_public_envelope down-projection seam, and the vault-only _render_factor_card_markdown report writer"
  - phase: 33-full-modular-crs-auditor-pack
    provides: "run_full_audit full-grid roll-up (sum of (points or 0) for SUBSTANTIATED cards) + audit_one shared card-assembly seam"
provides:
  - "Additive PrivateFactorCard.points_unresolved flag (True iff verdict SUBSTANTIATED and substantiated_points is None) — an explicit unresolved item, never a silent 0"
  - "PII-light counts['unpriced'] tally on PublicAuditEnvelope, derived from intrinsic verdict/points ground truth (dict[str,int] key; no schema change)"
  - "Explicit 'Substantiated points: UNRESOLVED (unpriced ...)' render line in the vault-only markdown report, distinct from a numeric 0/None"
  - "COV-02 net-proof test (flag + count + render + no-inflation + PII-light) as a durable contract"
affects: [35-04-sibling-seam, phase-37-remediation, review-packet]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "No-false-completeness net: an additive optional card flag + an additive counts key + one render line surface a truthful-but-incomplete result without a schema break, migration, or verdict change"
    - "PII-boundary tally derives from intrinsic verdict/points state (not a mutable flag) so the public surfacing cannot be fooled into hiding an unpriced factor"

key-files:
  created:
    - crawler/tests/test_unpriced_surfacing.py
  modified:
    - crawler/models/audit.py
    - crawler/auditor.py
    - crawler/audit_report.py

key-decisions:
  - "counts['unpriced'] derives from intrinsic (verdict == SUBSTANTIATED and substantiated_points is None), not from card.points_unresolved, so the public tally is ground-truth even if the flag was not set"
  - "points_unresolved is a plain additive field defaulting False (the auditor sets it at assembly); a bare SUBSTANTIATED+None card loads with points_unresolved False, honoring the additive-optional-loads-cleanly verification"
  - "The vault render shows UNRESOLVED only for a SUBSTANTIATED-but-unpriced card; a GAP/AT-RISK/N-A card with None points legitimately still renders None (the net is narrowly scoped)"

patterns-established:
  - "Pattern: surface an unpriceable-but-substantiated factor as an explicit unresolved item across all three tiers (private flag, public count, vault render) additively — verdict and substantiated_total value stay unchanged"

requirements-completed: [COV-02]

# Metrics
duration: 47min
completed: 2026-07-17
---

# Phase 35 Plan 02: Unpriced-`SUBSTANTIATED` Surfacing Net (COV-02) Summary

**Any factor that is `SUBSTANTIATED` yet cannot be priced from grounded rows is now surfaced as an explicit unresolved item — an additive `PrivateFactorCard.points_unresolved` flag, a PII-light `counts["unpriced"]` tally, and an explicit `UNRESOLVED (unpriced)` vault-report line — with the verdict unchanged and `substantiated_total` never inflated.**

## Performance

- **Duration:** ~47 min
- **Started:** 2026-07-17T07:13Z
- **Completed:** 2026-07-17T08:01Z
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Closed COV-02: a `SUBSTANTIATED` card whose `substantiated_points is None` (e.g. a second language at CLB≠9, or any residual unpriced case after 35-01 closed first language) is now flagged `points_unresolved == True` at card assembly — never presented as complete, never silently coalesced to `0`.
- Added the PII-light public tally `PublicAuditEnvelope.counts["unpriced"]` (a pure additive `dict[str, int]` key beside the existing `counts["grounded_claims"]`), derived from the intrinsic `verdict == "SUBSTANTIATED" and substantiated_points is None` ground truth so it holds even if the flag was not pre-set. `PublicAuditEnvelope` keeps `extra="forbid"` — no declared-field / schema change.
- The vault-only markdown report renders an explicit `- Substantiated points: UNRESOLVED (unpriced — no grounded point row)` line for a flagged card, clearly distinct from a genuine numeric `0` or a bare `None`.
- Preserved the invariants: the verdict stays narrowly `SUBSTANTIATED`, no point value is fabricated, and `substantiated_total` retains its truthful `(points or 0)` roll-up value (the unpriced card contributes `0` AND is separately counted as `unpriced`, so a consumer can distinguish "0 points, priced" from "unpriced").
- The flag is set from ONE place (`audit_one`), covering BOTH the single-factor (`audit_factor`/`run_audit`) and full-grid (`run_full_audit`) paths. Zero new runtime dependencies, no migration, no CLI verb change, no touch to the frozen `search`→`--cite`→grounding gate→envelope path.

## Task Commits

Each task was committed atomically (with the `Co-authored-by: Copilot` trailer):

1. **Task 1: Wave 0 — COV-02 net-proof (RED before net)** — `0530e12` (test)
2. **Task 2: Implement the unpriced-surfacing net (flag + count + render line)** — `cec8128` (feat)

**Plan metadata:** _(final docs commit — see below)_

_TDD gate sequence present in git log: RED `test` (`0530e12`) → GREEN `feat` (`cec8128`)._

## Files Created/Modified
- `crawler/tests/test_unpriced_surfacing.py` *(created)* — stdlib `unittest` net proof: `TestUnpricedFlag` (only the SUBSTANTIATED-but-None card is flagged; bare card defaults False), `TestUnpricedCount` (`counts["unpriced"] == 1`; count derives from intrinsic state even when the flag is left False), `TestUnpricedRender` (exactly one `UNRESOLVED (unpriced` line; priced cards render `15`/`0`; the unpriced card's own section never reads a numeric/None points line), `TestNoFalseCompleteness` (`substantiated_total == 15`, not inflated; unpriced distinguishable from a priced `0`), `TestPublicSurfacingIsPiiLight` (dumped envelope carries no applicant sentinel and no `ev_` id; the counts value is a plain int).
- `crawler/models/audit.py` *(modified)* — added the additive `PrivateFactorCard.points_unresolved: bool = False` field (documented) and the `counts["unpriced"]` tally in `to_public_envelope` (intrinsic derivation, placed beside `counts["grounded_claims"]`).
- `crawler/auditor.py` *(modified)* — `audit_one` computes `points_unresolved = (result.verdict == "SUBSTANTIATED" and substantiated_points is None)` and passes it into the assembled `PrivateFactorCard`; the roll-up `(points or 0)` value is unchanged.
- `crawler/audit_report.py` *(modified)* — `_render_factor_card_markdown` renders the explicit `UNRESOLVED (unpriced ...)` line when `card.points_unresolved` is True, else the numeric points line; `SCREENING_NOTICE` and the vault-only write path are unchanged.

## Decisions Made
- **Intrinsic-derived public tally.** `counts["unpriced"]` is computed from `verdict == "SUBSTANTIATED" and substantiated_points is None` rather than from the mutable `card.points_unresolved` flag. Rationale: the PII boundary should reflect the ground truth and cannot be fooled by a mis-set/unset flag; a dedicated test (`test_count_derives_from_intrinsic_state_not_the_flag`) pins this.
- **Plain field, auditor-set (not a computed/validator field).** The plan verification requires `PrivateFactorCard(factor_id='x', verdict='SUBSTANTIATED').points_unresolved` to be `False` "by default" (additive optional loads cleanly). A model-validator/computed field would force it True for that bare card, contradicting the verification — so the flag is a plain default-False field the auditor sets at assembly.
- **Narrowly-scoped render.** Only a `SUBSTANTIATED`-but-unpriced card renders `UNRESOLVED`; a `GAP`/`AT-RISK`/`N/A` card with `None` points keeps its existing `None` render (that is not an "unpriced" case), so no unrelated report behavior changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Over-broad render assertion in the RED test**
- **Found during:** Task 2 (GREEN — running the Task 2 verification suite)
- **Issue:** The Task-1 render test asserted `assertNotIn("- Substantiated points: None", md)` against the WHOLE markdown. The synthetic report intentionally includes a `GAP` card (`additional.sibling`) with `substantiated_points=None`, which legitimately renders `- Substantiated points: None` (unchanged pre-existing behavior; a GAP is not "unpriced"). The over-broad assertion therefore failed even though the implementation was correct.
- **Fix:** Scoped the assertion to the unpriced card's own `## Factor:` section (`core.language.second`) — assert that section contains `UNRESOLVED (unpriced`, and does NOT contain `- Substantiated points: None` or `- Substantiated points: 0`. The global `UNRESOLVED (unpriced` count-of-1 and the priced `15`/`0` numeric-line assertions were kept.
- **Files modified:** `crawler/tests/test_unpriced_surfacing.py`
- **Verification:** `pytest crawler/tests/test_unpriced_surfacing.py` → 7 passed.
- **Committed in:** `cec8128` (Task 2 GREEN commit — coupled to the implementation the assertion is proving).

---

**Total deviations:** 1 auto-fixed (1 bug — a test-only over-broad assertion; no implementation change caused it).
**Impact on plan:** The fix tightened the test to the intended contract (the unpriced card's section reads UNRESOLVED) without weakening it. No scope creep; the net's behavior matches the plan exactly.

## Issues Encountered

- **Pre-existing publish-safe failures (OUT OF SCOPE, already deferred).** The Task 2 regression sweep confirms `crawler/tests/test_full_audit_pii_perimeter.py::TestRepositoryPublishSafe::test_publish_safe_zero_violations` (and its sibling `test_conformance_v40_privacy_containment.py::...::test_publish_safe_main_zero_violations`) are RED at baseline. The publish-safe scanner flags 4 tracked-`.planning/` prose lines that contain the absolute home-directory path patterns it itself hunts — in `35-01-SUMMARY.md`, `deferred-items.md`, and `research/PITFALLS.md` — all committed BEFORE this plan (35-01 / milestone-v4.1 research). This plan changed only files under `crawler/`; scanning my four created/modified files individually reports **0** violations, so this plan adds none. Not fixed here (scope boundary: only auto-fix issues DIRECTLY caused by the current task's changes); it remains logged in `deferred-items.md` with suggested owner Phase 36 (Operational Hardening). This SUMMARY was written to avoid reproducing the trigger patterns so it adds no new violation.
- **Environment slowness in an unrelated suite.** `crawler/tests/test_dupaudit.py` (the crawler's cross-family duplicate-audit module) runs very slowly in this environment. It is unrelated to the CRS auditor — it references none of the touched symbols (`points_unresolved`, `to_public_envelope`, `_render_factor_card_markdown`, `PrivateFactorCard`). Not a regression from this plan; not re-run to completion here.

## Known Stubs

None — the net is wired end to end: `audit_one` sets the flag, `to_public_envelope` tallies it PII-light, and `_render_factor_card_markdown` renders it. No placeholder/empty data source.

## Threat Flags

None new. The change is additive on the existing Phase-32/33 audit seams — no new network endpoint, auth path, file-access pattern, or schema change at a trust boundary. The plan's `<threat_model>` mitigations are implemented and tested: T-35-02 (completeness spoofing) — flag + count + render, `substantiated_total` value unchanged (`test_total_not_inflated_and_unpriced_distinguishable`); T-35-05 (info disclosure on the stdout envelope) — int-only additive key, `extra="forbid"` preserved, no applicant value / `ev_` id in the dump (`test_envelope_dump_carries_no_pii`); T-35-06 (render misframing) — a neutral data-completeness statement, `SCREENING_NOTICE` and the narrow SUBSTANTIATED verdict unchanged.

## User Setup Required

None — no external service configuration required. Zero new runtime dependencies (ships on the existing `pydantic`/`pyyaml` + stdlib stack); no DB migration; no CLI change.

## Next Phase Readiness
- COV-02 is closed and pinned: any residual unpriced-but-substantiated factor is now an explicit unresolved item across the private card, the public counts, and the vault report — the no-false-completeness net Phase 37 remediation reads as an actionable unresolved item.
- 35-03 (COV-03 sibling extraction vocabulary) and 35-04 (COV-04 reachable `decide_sibling` + real seam, depends on 35-01/35-03) are unblocked; this plan touched no sibling/extraction code and left the frozen grounding gate + envelope path intact.
- One pre-existing publish-safe violation set in tracked `.planning/` docs remains deferred to Phase 36 (Operational Hardening) per `deferred-items.md`.

## Verification Evidence

- `pytest crawler/tests/test_unpriced_surfacing.py crawler/tests/test_audit_report.py crawler/tests/test_audit_models.py crawler/tests/test_vault_audit_cli.py -q` → **34 passed**.
- `pytest crawler/tests/test_unpriced_surfacing.py -q` → **7 passed**.
- Regression: `test_auditor` (16), `test_auditor_dispatch`+`test_auditors_additional`+`test_auditors_spouse`+`test_auditors_transferability`+`test_crs_audit` (59), `test_audit_store` (9), `test_audit_pii_perimeter` (3), `test_full_audit_cutoff` (5), `test_full_audit_integration`+`test_full_audit_real_seam` (13) → all green. `test_full_audit_pii_perimeter.py` → 26 passed, 1 pre-existing publish-safe fail (out of scope, above).
- `PrivateFactorCard(factor_id='x', verdict='SUBSTANTIATED').points_unresolved` → `False` (additive optional loads cleanly).
- A report with an unpriced card → `to_public_envelope(...).counts["unpriced"] == 1` and `"ev_"` absent from the dumped envelope.
- Publish-safe scan of the four created/modified `crawler/` files individually → **0** violations.

---
*Phase: 35-coverage-completion*
*Completed: 2026-07-17*

## Self-Check: PASSED

- `crawler/tests/test_unpriced_surfacing.py` — FOUND on disk.
- `.planning/phases/35-coverage-completion/35-02-SUMMARY.md` — FOUND on disk.
- Commits `0530e12` (RED `test`), `cec8128` (GREEN `feat`) — both present in git log; TDD gate sequence intact.
- `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer present on both task commits.
- Plan verification green (34 audit-report/models/CLI + 7 net-proof); `points_unresolved` defaults False; `counts["unpriced"] == 1` with no `ev_` in the dumped envelope.
- Publish-safe scan of the four changed `crawler/` files AND this SUMMARY individually → 0 new violations (the only repo-scan failure is the pre-existing tracked-`.planning/` docs set, out of scope, logged in `deferred-items.md`).
