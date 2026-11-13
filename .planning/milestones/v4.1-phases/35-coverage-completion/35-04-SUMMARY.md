---
phase: 35-coverage-completion
plan: 04
subsystem: api
tags: [crs, auditor, grounding, registry, sibling, age-threshold, real-seam, fail-closed, unittest, pytest]

# Dependency graph
requires:
  - phase: 35-coverage-completion
    provides: "35-03 sibling evidence vocabulary (siblingfields.py, _FIELD_SPECS['sibling_proof'], sibling_proof_pdf fixture) — the confirmed sibling by_field the decider reads"
  - phase: 35-coverage-completion
    provides: "35-01 real-seam file state (test_full_audit_real_seam.py language 130 / score_delta -6) — this plan owns the next edit to that file"
  - phase: 31-crs-registry
    provides: "the grounded additional.sibling points row (15 pts, crs-criteria.md#019) + _grounded_points reader"
  - phase: 33-full-modular-crs-auditor-pack
    provides: "decide_nomination / decide_study fail-closed shape + decide_age age-on-ITA-date + grounded-threshold pattern"
provides:
  - "Reachable fail-closed decide_sibling: SUBSTANTIATED only on the confirmed brother/sister + citizen/PR + Canadian-residence + ADULT-DOB chain"
  - "ENFORCED grounded adult gate: a numeric age comparison at the ITA date against grounded sibling_min_age (18) registry data — a confirmed minor is AT-RISK sibling_minor, never SUBSTANTIATED"
  - "New grounded additional.sibling.adult threshold row (kind: threshold, field: sibling_min_age, min_value: 18) grounded verbatim to crs-criteria.md#018 '18 years or older'"
  - "New reason codes: unresolved_sibling (AT-RISK) + sibling_minor (AT-RISK)"
  - "_grounded_min_age(registry, field) local reader (mirrors crs_audit._threshold_max, reads min_value)"
  - "Real-seam proof: an ADULT sibling_proof doc substantiates 15 AND a MINOR sibling doc stays AT-RISK sibling_minor, with no cross-factor contamination either direction"
affects: [phase-36-operational-hardening, phase-verify, remediation, review-packet]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reachable-but-never-relaxed decider: replace a documented-GAP stub with a real deterministic join over confirmed claimed-scoped evidence ONLY once the evidence vocabulary exists — the verdict rules are unchanged, only the code path becomes exercisable"
    - "ENFORCED grounded threshold gate: a decider reads a machine_check threshold (min_value) via a local reader mirroring crs_audit._threshold_max, then computes a neutral numeric comparison (age_on_date >= threshold) — the age bound is grounded registry data, not a documentary citation or an inlined literal"
    - "Real-seam negative control: a confirmed-minor document driven through the ACTUAL extract->confirm->age path proves a fail-closed branch is reachable AND correct, complementing the day-before/on-birthday unit boundaries"

key-files:
  created: []
  modified:
    - crawler/auditors/additional.py
    - crawler/data/crs_rules/additional.yaml
    - crawler/tests/test_auditors_additional.py
    - crawler/tests/test_conformance_v40_no_false_green.py
    - crawler/tests/test_full_audit_real_seam.py

key-decisions:
  - "The adult (18+) requirement is ENFORCED, not merely documented: a new grounded additional.sibling.adult threshold row supplies min_value: 18 as machine_check data, decide_sibling reads it via _grounded_min_age and compares age_on_date(dob, ita) < min_age — a confirmed minor is AT-RISK sibling_minor and can NEVER be SUBSTANTIATED"
  - "No volatile literal inlined: points via _grounded_points, the adult threshold via _grounded_min_age reading the grounded row, the age via crs_audit.age_on_date — the no_inlined_volatile_rules self-scan over additional.py stays []"
  - "Strict '<' boundary: on the 18th birthday age_on_date == 18 is an adult and proceeds; the day before (age 17) is AT-RISK sibling_minor — proven by both unit boundaries and the real-seam minor control"
  - "The existing additional.sibling points row (15 / #019 / citation_index 0) is left UNCHANGED — the new adult gate is a SEPARATE grounded threshold row (#018); COVERAGE.md renders byte-identical so no regeneration"
  - "The four phase-gate failures (a stale FieldName completeness pin from 35-03 + three publish-safe/PII-tree scans over prior-plan .planning/ prose) are pre-existing and out of scope for 35-04's declared files — logged to deferred-items.md, not fixed"

patterns-established:
  - "Pattern: make an already-grounded-but-stubbed decider reachable by joining over the confirmed claimed-scoped evidence + grounded points row + grounded threshold row — fail-closed on every missing/unaccepted/unresolvable/no-date/minor case"

requirements-completed: [COV-04]

# Metrics
duration: 25min
completed: 2026-07-17
---

# Phase 35 Plan 04: Reachable Fail-Closed Sibling Decider with Enforced Grounded Adult Gate (COV-04) Summary

**`additional.sibling` now decides through a real deterministic join: it returns `SUBSTANTIATED` (15 grounded pts, `crs-criteria.md#019`) ONLY on the confirmed brother/sister + citizen/PR + Canadian-residence + ADULT-date-of-birth chain, and enforces the adult (18+) requirement as a numeric age comparison at the ITA date against a NEW grounded `additional.sibling.adult` threshold row (`min_value: 18`, `crs-criteria.md#018` "18 years or older") — a confirmed minor is AT-RISK `sibling_minor` and can never green the factor; every missing/unaccepted/unresolvable/no-ITA-date case is `GAP`/`AT-RISK`; no age/points/date literal is inlined (points via `_grounded_points`, threshold via `_grounded_min_age`, age via `crs_audit.age_on_date`).**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-17T08:22:39Z
- **Completed:** 2026-07-17T08:47:29Z
- **Tasks:** 3
- **Files modified:** 5 (0 created, 5 modified)

## Accomplishments
- Closed COV-04: the `additional.sibling` decider was a hard-coded documented-GAP stub (always `GAP missing_evidence`) because no sibling evidence vocabulary existed. Now that 35-03 supplies the confirmed, claimed-scoped sibling `by_field`, `decide_sibling` is a reachable fail-closed join that substantiates the full confirmed ADULT chain and stays fail-closed everywhere else — the decider was made reachable, never relaxed.
- ENFORCED the adult (18+) gate as machine-checked registry data, not prose: added a NEW grounded `additional.sibling.adult` threshold row (`kind: threshold`, `field: sibling_min_age`, `min_value: 18`) grounded verbatim to `guidance/crs-criteria.md#018` "18 years or older". The decider reads the threshold via a local `_grounded_min_age` helper (mirroring `crs_audit._threshold_max`), pins the sibling's age to the ITA date with `crs_audit.age_on_date`, and returns AT-RISK `sibling_minor` for any confirmed sibling below the grounded threshold — a confirmed minor can NEVER be SUBSTANTIATED.
- Proved the boundary is exact: ON the 18th birthday (`age_on_date == 18`) the sibling is an adult and substantiates; the day before (`age_on_date == 17`) is AT-RISK `sibling_minor` with `substantiated_points is None`. A strict `<` against the grounded (float) threshold makes the boundary inclusive of the grounded age.
- Kept the module literal-free: `no_inlined_volatile_rules([additional.py]) == []`; points come from `_grounded_points` (never a `15`), the adult threshold from `_grounded_min_age` reading the grounded row (never an `18`), and the age from `crs_audit.age_on_date`.
- Grounded the new row cleanly: `validate_registry` over the two `additional.sibling*` rows returns `grounded == total == 2` with zero violations; `retrieve_what_you_cite['additional.sibling.adult']` selects `guidance/crs-criteria.md#018` with `agrees_with_citation` and `grounds` both True; the full grid stays `grounded == total`; and `render_coverage_markdown` is byte-identical to `COVERAGE.md` (no regeneration).
- Proved COV-04 through the ACTUAL seam: an ADULT `sibling_proof` document imported → extracted → confirmed → audited substantiates `additional.sibling` at 15 with `ev_`-prefixed evidence, while a SEPARATE minimal seam importing a confirmed MINOR sibling document (built in-test from `mf.build_pdf`, a 2015 date-of-birth) stays AT-RISK `sibling_minor` (`substantiated_points is None`, verdict `!= SUBSTANTIATED`) — with no cross-factor contamination either direction (sibling evidence links only to `additional.sibling`; the passport DOB / nomination stream never link to it).
- Corrected the no-false-green matrix to seed a REAL sibling field: `_FIELD_FOR['additional.sibling']` changed from the `"issuer"` placeholder to `"sibling_relationship"`, so the five-state blocking matrix (pending/rejected/low_quality/ambiguous/stale) exercises genuine sibling evidence and proves none of those states can green the factor.

## Task Commits

Each task was committed atomically (with the `Co-authored-by: Copilot` trailer):

1. **Task 1: TestSibling truth table + synthetic sibling rows + conformance field fix (RED)** — `0841d17` (test)
2. **Task 2: Reachable fail-closed decide_sibling with ENFORCED grounded adult gate + grounded threshold row** — `9a80fea` (feat)
3. **Task 3: Real sibling seam — adult SUBSTANTIATED + minor control + no contamination** — `4da5151` (test)

**Plan metadata:** _(final docs commit — see below)_

_TDD gate sequence present in git log for the Task 1→2 pair: Task 1 `test` (`0841d17`) adds the TestSibling truth table that FAILS RED against the always-GAP stub (8 of 9 cases fail) → Task 2 `feat` (`9a80fea`) lands the reachable decider + grounded threshold row and turns it GREEN._

## Files Created/Modified
- `crawler/auditors/additional.py` *(modified)* — imported `siblingfields`; added `_grounded_min_age(registry, field)` (reads `min_value` off a grounded `kind: threshold` row, mirroring `crs_audit._threshold_max`); rewrote `decide_sibling` from the documented-GAP stub into a reachable fail-closed join with an ENFORCED grounded adult gate (missing field → GAP `missing_evidence`; unaccepted token / unresolvable DOB / no ITA date / missing grounded threshold → AT-RISK `unresolved_sibling`; confirmed minor → AT-RISK `sibling_minor`; else SUBSTANTIATED with grounded points). `register("additional.sibling", decide_sibling)` unchanged.
- `crawler/data/crs_rules/additional.yaml` *(modified)* — appended a NEW grounded `additional.sibling.adult` threshold row (`kind: threshold`, `field: sibling_min_age`, `min_value: 18`, citation `guidance/crs-criteria.md#018` quote "18 years or older", selector marker "18 years or older" with the standard `deny_families`). The existing `additional.sibling` points row (`points: 15` / `#019` / `citation_index: 0`) is untouched.
- `crawler/tests/test_auditors_additional.py` *(modified)* — added two synthetic rows to `_registry()` (the `additional.sibling` points row `PointsEntry(label="sibling", level="sibling", points=15)` + the `additional.sibling.adult` threshold row `MachineCheck(kind="threshold", field="sibling_min_age", min_value=18)`) and a `TestSibling` truth table (full adult chain → SUBSTANTIATED/15; missing field → GAP; bad relationship/status token, unresolvable DOB, no-ITA-date → AT-RISK `unresolved_sibling`; on-18th-birthday → adult; day-before + clear-minor → AT-RISK `sibling_minor`/`substantiated_points is None`).
- `crawler/tests/test_conformance_v40_no_false_green.py` *(modified)* — corrected `_FIELD_FOR['additional.sibling']` from the `"issuer"` placeholder to `"sibling_relationship"`.
- `crawler/tests/test_full_audit_real_seam.py` *(modified)* — `_seed_and_run` now claims `additional.sibling` and imports an ADULT `sibling_proof` doc through the real seam; added `test_real_seam_sibling_reaches_substantiated` (adult → SUBSTANTIATED/15/`grounded_substantiated`, `ev_`-prefixed), `test_real_seam_minor_sibling_stays_at_risk` (a separate minimal seam importing an in-test MINOR sibling page → AT-RISK `sibling_minor`, `substantiated_points is None`, never SUBSTANTIATED), and extended `test_real_seam_no_cross_factor_contamination` to prove sibling ↔ age/nomination disjointness both directions.

## Decisions Made
- **Adult gate is ENFORCED as grounded machine_check data, not documentary prose.** The `18` age bound lives in a grounded `additional.sibling.adult` threshold row (`min_value: 18`, `#018`) and is read via `_grounded_min_age`; `decide_sibling` computes `age_on_date(dob, ita) < min_age` — a neutral numeric comparison, not a citation lookup. This is the core false-green fix: a confirmed minor is structurally AT-RISK `sibling_minor` and unreachable-to-SUBSTANTIATED.
- **No inlined volatile literal.** Points via `_grounded_points` (never `15`), the adult threshold via `_grounded_min_age` reading the grounded row (never `18`), the age via `crs_audit.age_on_date`. The `no_inlined_volatile_rules` self-scan over `additional.py` and over the new YAML row's prose both return `[]` (the `claim_text`/`query` were written free of any 15/25/30/50/100/200/600 / CLB / 2·5·10-year / date token; the verbatim `18 years or older` lives only in the allow-listed `marker`/`quote`).
- **Separate grounded threshold row, existing points row untouched.** The new adult gate is a distinct `#018` threshold row; the shipped `additional.sibling` points row (`#019`) is unchanged, `_grounded_points` is unaffected (a threshold row carries no `points_by_level`), and `COVERAGE.md` renders byte-identical.
- **Strict `<` boundary.** On the 18th birthday `age_on_date == 18` is an adult (proceeds); the day before is a minor. Verified by the unit day-before/on-birthday boundaries and the real-seam minor control.
- **Reachable, never relaxed.** The decider only became exercisable because 35-03 landed the sibling evidence vocabulary; every verdict rule (all four required fields + accepted enum tokens + resolvable DOB + authoritative ITA date + adult gate) is fail-closed.

## Deviations from Plan

None - plan executed exactly as written. Tasks 1→2→3 ran in sequence; the RED→GREEN gate landed as designed (Task 1 RED, Task 2 GREEN); every task's acceptance criteria and the plan `<verification>` block passed. No Rule 1–4 deviation was required during implementation.

**Total deviations:** 0.
**Impact:** none — the plan's design (grounded adult threshold row + `_grounded_min_age` reader + reachable fail-closed `decide_sibling` + real-seam adult/minor controls + conformance field fix) was implementable verbatim.

## Issues Encountered

The plan-scoped verification (the seven `<verification>` test files) is **fully green** (68 passed, 233 subtests). The broader phase gate (`.venv/bin/python -m pytest crawler/tests -q`) surfaced **4 pre-existing failures, all OUT OF SCOPE for 35-04's declared files** — logged to `deferred-items.md`, not fixed (scope boundary: only auto-fix issues DIRECTLY caused by the current task's changes):

1. **Stale FieldName completeness pin (35-03 surface).** `test_extraction_store.py::TestModels::test_field_name_vocabulary_is_complete` pins `models.FieldName` to a HARD-CODED `expected` set that was not extended when 35-03 added the four sibling members to the `FieldName` Literal. The sibling fields were present in `FieldName` at `06e9308` (35-03's tip, before 35-04 began), so this predates and is independent of the COV-04 decider change. 35-04 did NOT touch `crawler/models/vault.py` or `test_extraction_store.py`.
2–4. **Publish-safe / PII-tree scans over prior-plan `.planning/` prose.** `test_conformance_v40_privacy_containment.py::...::test_publish_safe_main_zero_violations`, `test_full_audit_pii_perimeter.py::...::test_publish_safe_zero_violations`, and `test_extraction_pii_perimeter.py::...::test_tracked_tree_is_clean` all flag the same absolute-home-path prose pattern in tracked `.planning/` docs authored by the 35-01 plan (its summary + `deferred-items.md`) and the milestone-v4.1 research notes. Every flagged line lives under `.planning/`; NONE is a file 35-04 created or modified (all 35-04 changes are under `crawler/`). This SUMMARY and the `deferred-items.md` additions were written to avoid reproducing the trigger substrings, so 35-04 adds no new violation.

A direct check confirms 35-04's five changed files (`crawler/auditors/additional.py`, `crawler/data/crs_rules/additional.yaml`, and three `crawler/tests/*.py`) introduce none of these failures: `git diff 06e9308 HEAD --name-only` lists exactly those five files, none of which is a failing test or a failing test's target.

## Known Stubs

None — `decide_sibling` is now a real reachable decider (the prior documented-GAP stub is replaced). The verdict is produced from confirmed claimed-scoped evidence joined against grounded points + grounded adult-threshold rows; there is no hardcoded/placeholder data source. The real-seam adult and minor cases exercise the full path end-to-end.

## Threat Flags

None new — the change is additive on the existing decider + grounded-registry seams (no new network endpoint, auth path, file-access pattern, or schema change at a trust boundary). The plan `<threat_model>` mitigations are implemented and tested:
- **T-35-01** (fabricated point / inlined age): `15` from the grounded points row via `_grounded_points`; `18` from the grounded `#018` threshold row via `_grounded_min_age`; `no_inlined_volatile_rules([additional.py]) == []`; `#018` + `#019` ground with zero violations and retrieve-what-you-cite AGREES.
- **T-35-03** (malicious / low-quality / ambiguous / stale evidence — OR a confirmed MINOR — greens the factor): `is_audit_eligible` blocks the five blocking states upstream; the decider additionally requires four fields + accepted enum tokens + a resolvable DOB + an authoritative ITA date AND enforces `age_on_date(dob, ita) >= grounded sibling_min_age` — a confirmed minor is AT-RISK `sibling_minor` (day-before/on-birthday unit boundaries + real-seam minor control); no-false-green matrix now seeds real sibling evidence across all five states.
- **T-35-04** (sibling evidence bleeds into core.age / additional.nomination): claimed-only `_DOC_TYPE_FACTOR` linkage + `by_field` scoped to `additional.sibling`; the real-seam contamination test asserts disjoint evidence both directions.
- **T-35-05** (sibling DOB/relationship/`ev_` leaks): the decider's PII-bearing `confirmed_value` (incl. the computed `sibling_age_on_ita`) stays on the vault-only `PrivateFactorCard`; the public envelope drops values/`ev_`; real-seam PII-perimeter assertions hold.
- **T-35-06** (verdict framed as legal/eligibility advice): `SUBSTANTIATED` stays narrowly defined (confirmed + eligible + grounded rule + grounded adult gate); the adult threshold is grounded machine_check data computed as a neutral date comparison, not asserted as advice.

## Next Phase Readiness
- COV-04 is closed: `additional.sibling` returns `SUBSTANTIATED` only on the claimed-scoped, confirmed, grounded, ADULT chain; missing/stale/ambiguous/cross-factor evidence — and a confirmed minor — stays `GAP`/`AT-RISK`. The adult gate is an enforced numeric comparison against grounded registry data; the decider is reachable but never relaxed.
- Two out-of-scope, pre-existing test-surface items remain for a follow-up: the stale FieldName completeness pin (a 35-03 one-line update) and the publish-safe scanner flagging `.planning/` prose (suggested owner Phase 36 Operational Hardening). Both are logged with root cause + suggested owner in `deferred-items.md`.
- Phase 35 (coverage completion) plans 01–04 are now all complete; the phase is ready for `/gsd-verify-work 35`.

## Verification Evidence

- Plan `<verification>` test files: `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_crs_rules_conformance.py crawler/tests/test_conformance_v40_retrieve_what_you_cite.py crawler/tests/test_crs_registry_transfer_additional.py crawler/tests/test_full_audit_real_seam.py crawler/tests/test_conformance_v40_no_false_green.py -q` → **68 passed, 233 subtests passed**.
- `no_inlined_volatile_rules([additional.py])` → `[]`; `no_inlined_volatile_rules(['additional.yaml'])` → `[]`.
- `validate_registry` over the two `additional.sibling*` rows → `{'total': 2, 'grounded': 2, 'violations': []}`; the full grid stays `grounded == total`.
- `retrieve_what_you_cite['additional.sibling.adult']` → `{'selected_chunk_id': 'guidance/crs-criteria.md#018', 'agrees_with_citation': True, 'grounds': True}`.
- `render_coverage_markdown(reg) == COVERAGE.md` → `True` (byte-identical, no regeneration).
- Real seam (corpus + extraction deps present, so it RAN — not a structural-only skip): all 5 `RealExtractConfirmAuditSeam` cases PASSED, including `test_real_seam_sibling_reaches_substantiated` (adult → SUBSTANTIATED/15) and `test_real_seam_minor_sibling_stays_at_risk` (minor → AT-RISK `sibling_minor`).
- `_grounded_points(reg, 'additional.sibling', 'sibling', False) == 15` and `_grounded_min_age(reg, 'sibling_min_age') == 18.0` against the REAL loaded registry; no bare `15`/`18` in the `decide_sibling` body.
- Task 1 RED evidence: before Task 2, `pytest crawler/tests/test_auditors_additional.py::TestSibling` → 8 failed, 1 passed (the always-GAP stub fails the adult-chain and every fail-closed case except the incidental missing-field GAP).
- Full phase gate (`crawler/tests -q`) → **738 passed, 1 skipped, 4 failed** — the 4 failures are pre-existing/out-of-scope (a stale 35-03 FieldName pin + three publish-safe/PII scans over prior-plan `.planning/` prose), none in a file 35-04 changed; logged to `deferred-items.md`.

---
*Phase: 35-coverage-completion*
*Completed: 2026-07-17*

## Self-Check: PASSED

- All five modified files FOUND on disk (`crawler/auditors/additional.py`, `crawler/data/crs_rules/additional.yaml`, `crawler/tests/test_auditors_additional.py`, `crawler/tests/test_conformance_v40_no_false_green.py`, `crawler/tests/test_full_audit_real_seam.py`).
- `.planning/phases/35-coverage-completion/35-04-SUMMARY.md` FOUND on disk.
- Task commits `0841d17` (RED `test`), `9a80fea` (GREEN `feat`), `4da5151` (`test`) — all present in git log; the RED→GREEN gate sequence is intact.
- `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer present on all three task commits.
- Plan `<verification>` block green: 68 passed / 233 subtests; `no_inlined_volatile_rules` `[]` for both `additional.py` and `additional.yaml`; sibling rows `grounded == total == 2`; retrieve-what-you-cite for the adult row AGREES + grounds; `COVERAGE.md` byte-identical; real-seam adult + minor cases RAN and PASSED.
- This SUMMARY and the `deferred-items.md` additions were scanned and contain NO absolute-home-path trigger substrings — 35-04 adds no new publish-safe violation.
- The four broader-suite failures are pre-existing/out-of-scope (a stale 35-03 FieldName pin + three publish-safe/PII scans over prior-plan `.planning/` prose), none in a file 35-04 changed; logged to `deferred-items.md`.
