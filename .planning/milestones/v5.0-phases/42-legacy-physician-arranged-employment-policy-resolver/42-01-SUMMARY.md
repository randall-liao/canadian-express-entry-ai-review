---
phase: 42-legacy-physician-arranged-employment-policy-resolver
plan: 01
subsystem: crs-registry
tags: [crs-rules, grounding, physician-public-policy, arranged-employment, yaml-registry, conformance, frozen-contracts]

# Dependency graph
requires:
  - phase: 40-safe-freshness-effective-date-foundation
    provides: "row_in_effect effective-dated predicate + MachineCheck.effective_from/to window fields the physician row is dated against"
  - phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
    provides: "_FROZEN_CONTRACT_PATHS frozen-contract test harness whose intent this plan realigns"
provides:
  - "Grounded, effective-dated additional.job_offer.physician RuleRow (accepted_enum NOC set 31100/31101/31102, effective_from 2023-04-25, effective_to null) in additional.yaml"
  - "REQUIRED_RULE_IDS[additional_points] physician label + regenerated COVERAGE.md (grid manifest documents the physician slot; coverage stays COMPLETE)"
  - "retrieve-what-you-cite conformance proof that the physician row grounds + cites chunks disjoint from current/legacy (POLICY-02 distinct citation)"
  - "Realigned Phase-41 frozen-path intent: additional.yaml + COVERAGE.md dropped as mutation targets; crawler/crs_audit.py stays byte-for-byte frozen"
affects: [42-02-physician-decider-branch, 42-03-inert-sidecar, 42-04-negative-control-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Grounded-by-construction rule row: all volatile literals (date + NOCs) live ONLY in allow-listed grounded YAML keys (effective_from, value, quote); zero Python/prose inlining"
    - "Distinct-citation-on-shared-factor: current/legacy/physician are 3 distinct rows on factor_ids [additional.job_offer] citing DISJOINT chunks; prefix-exact _covers keeps labels non-overlapping"
    - "Generated-artifact discipline: COVERAGE.md is a pure registry render (never hand-edited), pinned fresh by test_committed_coverage_md_not_stale"

key-files:
  created: []
  modified:
    - crawler/data/crs_rules/additional.yaml
    - crawler/crs_rules.py
    - crawler/data/crs_rules/COVERAGE.md
    - crawler/tests/test_dli_conformance.py
    - crawler/tests/test_conformance_v40_retrieve_what_you_cite.py

key-decisions:
  - "Kept POLICY-01/02/03 requirements PENDING (not marked complete) — this plan ships only the grounded data foundation; the physician decider branch (42-02), inert sidecar (42-03), and negative-control conformance (42-04) must land before the POLICY requirements are satisfied end-to-end"
  - "Used check_type: policy with machine_check.kind: accepted_enum (both valid Literal members) — an accepted-value SET carries NO points_table, so the row can never inject a CRS award; the award stays the frozen guard's job"
  - "Marker uses the YAML \\u2019 double-quoted escape → U+2019 curly apostrophe (grounding is whitespace/case-normalized only, NOT Unicode-folded); verified verbatim in corpus/guidance/job-offer.md:56"
  - "Date grounded from guidance/job-offer.md#002 text (citation_index 0); NOC set grounded from FSW arranged-employment PDI #020 (citation_index 1) — never the PDI section header, never mi-rounds category-based content"

patterns-established:
  - "Effective-dated open-ended policy row: effective_from set, effective_to intentionally OMITTED (null) for a policy that 'remains in effect until revoked by the Minister'"
  - "Frozen-intent realignment: when a formerly-frozen artifact becomes a legitimate mutation target, drop it from _FROZEN_CONTRACT_PATHS AND update the surrounding comment/docstring so a green suite is not misleading — while keeping the true guard (crs_audit.py) frozen"

requirements-completed: []

# Metrics
duration: 17min
completed: 2026-07-19
---

# Phase 42 Plan 01: Legacy & Physician Arranged-Employment Policy Resolver — Grounded Data Foundation Summary

**Shipped the grounded, effective-dated `additional.job_offer.physician` public-policy rule row (NOC 31100/31101/31102, effective_from 2023-04-25, open-ended) that grounds live against the pinned corpus citing chunks disjoint from the current/legacy rows, registered its grid label with a fresh COVERAGE.md, proved it in the retrieve-what-you-cite sweep, and realigned the Phase-41 frozen-path intent without unfreezing `crs_audit.py`.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-19T03:31:24Z
- **Completed:** 2026-07-19T03:48:49Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added the grounded, effective-dated `additional.job_offer.physician` `RuleRow` to `additional.yaml` on the SAME `additional.job_offer` factor as current/legacy but citing DISJOINT chunks (`guidance/job-offer.md#002` + FSW-PDI `#020`) and a distinct U+2019 physician marker; `validate_registry` = **0 violations / 37 grounded of 37**, and `retrieve_what_you_cite` re-selects `guidance/job-offer.md#002` (`agrees_with_citation` + `grounds` both True).
- Registered `additional.job_offer.physician` in `REQUIRED_RULE_IDS["additional_points"]` (prefix-exact `_covers` → the label covers ONLY the new row) and regenerated the committed `COVERAGE.md` (pure registry render): the physician slot shows `present`, overall `Status: COMPLETE`, and the artifact is byte-identical to a fresh render.
- Extended `test_conformance_v40_retrieve_what_you_cite.py` with `TestJobOfferPhysicianRealCorpus` (skip-guarded on `corpus/index.db`) asserting the physician row grounds from a `guidance/` chunk and that its citation ids are DISJOINT from BOTH current and legacy — the POLICY-02 distinct-citation invariant — with all three rows sharing `factor_ids == ["additional.job_offer"]`.
- Realigned the Phase-41 frozen-path INTENT: dropped `additional.yaml` + `COVERAGE.md` from `_FROZEN_CONTRACT_PATHS` (legitimate Phase-42 mutation targets) and updated the tuple comment + `TestFrozenContractsUnchanged` docstring, while KEEPING `crawler/crs_audit.py` frozen and asserted byte-for-byte (`git diff --quiet HEAD` = exit 0, zero diff).
- Kept the no-inlined-volatile static gate clean: the `2023-04-25` date and the `31100/31101/31102` NOC set live ONLY in allow-listed grounded keys (`effective_from`, `value`, `quote`) — `no_inlined_volatile_rules` returns `[]`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the grounded physician row, register the label, regenerate COVERAGE.md, and realign the frozen-path intent** - `980ecf3` (feat)
2. **Task 2: Extend the retrieve-what-you-cite conformance to prove the physician row grounds and cites disjoint chunks** - `506f76e` (test)

**Plan metadata:** _(final docs commit — SUMMARY.md + STATE.md + ROADMAP.md)_

## Files Created/Modified
- `crawler/data/crs_rules/additional.yaml` - Added the grounded, effective-dated `additional.job_offer.physician` row (accepted_enum NOC set, `effective_from: 2023-04-25`, `effective_to` omitted/null; DISJOINT citations + distinct U+2019 marker; SAME `factor_ids: [additional.job_offer]`).
- `crawler/crs_rules.py` - Appended `"additional.job_offer.physician"` to `REQUIRED_RULE_IDS["additional_points"]` with a physician-edge-case comment.
- `crawler/data/crs_rules/COVERAGE.md` - Regenerated pure-render coverage artifact; physician slot `present`, `Status: COMPLETE`.
- `crawler/tests/test_dli_conformance.py` - Dropped `additional.yaml` + `COVERAGE.md` from `_FROZEN_CONTRACT_PATHS`; kept `crawler/crs_audit.py`; realigned the tuple comment + `TestFrozenContractsUnchanged` docstring.
- `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py` - Added `TestJobOfferPhysicianRealCorpus` (grounding + POLICY-02 disjoint-citation assertions, skip-guarded on the real DB).

## Decisions Made
- **POLICY requirements kept PENDING.** Per the execution directive, POLICY-01/02/03 remain `Pending` in REQUIREMENTS.md — this plan delivers only the grounded data foundation the later plans (decider branch 42-02, inert sidecar 42-03, negative-control conformance 42-04) build on. Marking them complete now would be premature.
- **`accepted_enum` over `points_table`.** The physician `machine_check` is a match SET carrying NO points — structurally incapable of injecting a CRS award. The award decision stays the frozen `arranged_employment_guard`'s sole job (T-42-01 mitigation).
- **Curly apostrophe via YAML escape.** The selector marker uses `"If you\u2019re a physician with a job offer in Canada"`; PyYAML resolves `\u2019` to U+2019, matching the corpus verbatim (grounding is not Unicode-folded).
- **Grounding sources fixed per research.** Date from `guidance/job-offer.md#002` text; NOC set from FSW arranged-employment PDI `#020` text — both verified verbatim substrings against `corpus/index.db` this session (Pitfall 2/6 avoided; no mi-rounds category content).

## Deviations from Plan

None - plan executed exactly as written.

All five files, the row shape, the exact chunk ids/quotes/marker, the `REQUIRED_RULE_IDS` entry, the COVERAGE regen command, the frozen-path realignment, and the conformance assertions were implemented exactly as specified. The `TestFrozenContractsUnchanged` class docstring was updated alongside the tuple comment (both explicitly required by the Task 1 action: "Update the tuple's surrounding comment so it no longer claims the CRS-grid YAML is frozen this phase"); this is in-scope, not a deviation.

## Authentication Gates
None - no authenticated services or credentials involved (zero-network, zero-dependency phase).

## Issues Encountered
- The full `crawler/tests/` sweep buffers output under `pytest -q` and did not surface results within ~12 minutes, so it was stopped and replaced with targeted regression runs on the surfaces the physician row actually touches. All targeted suites pass:
  - `test_conformance_v40_retrieve_what_you_cite.py` + `test_crs_no_inlined_rules.py` + `test_dli_conformance.py`: **32 passed, 61 subtests**.
  - `test_auditors_additional.py` + `test_crs_rules.py` + `test_crs_registry_transfer_additional.py` + `test_auditor.py` + `test_auditor_dispatch.py`: **68 passed, 17 subtests**.
  - `test_crs_rules_conformance.py`: **8 passed, 37 subtests**.

## Verification Evidence
- `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_retrieve_what_you_cite.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_dli_conformance.py -q` → **32 passed, 61 subtests, ~2.8s** (< 120 s).
- `coverage_report(load_registry())['complete']` → `True`.
- `git diff --quiet HEAD -- crawler/crs_audit.py` → exit **0** (guard byte-for-byte frozen).
- `diff <(.venv/bin/python -m crawler.crs_rules) crawler/data/crs_rules/COVERAGE.md` → **empty** (committed coverage not stale).
- `validate_registry` → `violations: []`, `grounded/total: 37/37`; physician `agrees_with_citation` + `grounds` True, `selected_chunk_id = guidance/job-offer.md#002`.
- `no_inlined_volatile_rules(static_gate_surface)` → `[]`.

## Known Stubs
None - the physician row is a fully grounded, live-verified rule row (not a placeholder or gap row); no empty/placeholder data ships in this plan. The physician *decider branch* that consumes this row is intentionally out of scope here and lands in Plan 42-02.

## Threat Flags
No new security surface introduced beyond the plan's `<threat_model>`. The physician row's citations/marker (T-42-02) are proven verbatim substrings; the volatile date/NOC literals (T-42-02) live only in allow-listed grounded keys; the `accepted_enum` machine_check carries no award (T-42-01); and the frozen guard `crawler/crs_audit.py` (T-42-06) stays byte-for-byte unchanged. No packages introduced (T-42-SC accept). All threat-register mitigations owned by shipped tests are green.

## Next Phase Readiness
- **Ready for 42-02 (physician decider branch):** the grounded `additional.job_offer.physician` row, its `machine_check.accepted_values` NOC set, and `effective_from` window are loadable and grounding — the decider can read the NOC set + `row_in_effect(phys, ita_date)` without inlining any literal.
- **Ready for 42-03 (inert sidecar) / 42-04 (negative control):** grid manifest + COVERAGE stay COMPLETE, so the later plans extend a green baseline.
- **No blockers.** `crawler/crs_audit.py` remains frozen; POLICY-01/02/03 stay `Pending` until the deciders/tests in 42-02..42-04 close them.

---
*Phase: 42-legacy-physician-arranged-employment-policy-resolver*
*Completed: 2026-07-19*

## Self-Check: PASSED

- Modified files verified present on disk: `additional.yaml`, `crs_rules.py`, `COVERAGE.md`, `test_dli_conformance.py`, `test_conformance_v40_retrieve_what_you_cite.py`, `42-01-SUMMARY.md`.
- Task commits verified in git history: `980ecf3` (feat), `506f76e` (test).
- `additional.job_offer.physician` label confirmed present in `additional.yaml`, `crs_rules.py`, `COVERAGE.md`, and the conformance test.
- Plan-level verification re-run: 32 passed / 61 subtests; coverage `complete`; `crs_audit.py` zero diff vs HEAD; COVERAGE.md not stale.
