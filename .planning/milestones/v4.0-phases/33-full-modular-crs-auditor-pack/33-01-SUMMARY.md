---
phase: 33-full-modular-crs-auditor-pack
plan: 01
subsystem: api
tags: [crs, auditor, dispatch, pydantic, cutoff]

requires:
  - phase: 32-auditor-vertical-slice
    provides: audit_factor verdict engine, PrivateFactorCard/PublicAuditEnvelope models, run_audit writer, vault audit CLI
  - phase: 31-grounded-crs-rule-registry
    provides: crs_rules validate_registry + no_inlined_volatile_rules, crs_audit deterministic math
provides:
  - crawler/auditors dispatch package (register/resolve, DecisionContext/Result, FULL_GRID_FACTORS)
  - generic audit_one spine + run_full_audit + audit_factor back-compat shim
  - core human-capital deciders (age, education, first/second language, work)
  - run_full_audit_report writer + vault audit --all + substantiated-total-vs-cutoff
  - shared skills/crs-auditors/_contract.md
affects: [33-03, 33-04, 33-05, 33-06, 34-safety-conformance]

tech-stack:
  added: []
  patterns:
    - "factor -> decider registry dispatch over a frozen shared spine"
    - "conservative AT-RISK default decider (unwired factor never greens)"

key-files:
  created:
    - crawler/auditors/__init__.py
    - crawler/auditors/core.py
    - crawler/auditors/spouse.py (stub)
    - crawler/auditors/transferability.py (stub)
    - crawler/auditors/additional.py (stub)
    - skills/crs-auditors/_contract.md
    - crawler/tests/test_auditor_dispatch.py
    - crawler/tests/test_full_audit_cutoff.py
  modified:
    - crawler/auditor.py
    - crawler/audit_report.py
    - crawler/cli.py
    - crawler/tests/test_crs_no_inlined_rules.py
    - crawler/models/vault.py (date_of_birth field)
    - crawler/tests/test_extraction_store.py (vocabulary test)

key-decisions:
  - "audit_factor is a thin shim over audit_one so the whole test_auditor.py contract is preserved via dispatch"
  - "transfer.* ordered LAST in run_full_audit so prior_cards holds decided core/spouse cards"
  - "cutoff comparison is pure arithmetic (delta + meets), no legal-advice wording"

patterns-established:
  - "DecisionContext carries only spine-gathered data; deciders never touch ev_/citation ids"
  - "N/A short-circuit (spouse no-mode, unclaimed non-derived) before any gate/evidence read"

requirements-completed: [AUDIT-01, AUDIT-03, AUDIT-04, AUDIT-05]

duration: ~90min
completed: 2026-07-06
---

# Phase 33 Plan 01: Dispatch Spine + Core Human Capital Summary

**Generalized the Phase-32 single-factor audit slice into a factor→decider dispatch spine that fans one proven verdict contract across the whole CRS grid, landed the core human-capital module on top of it, and rolled SUBSTANTIATED points into a substantiated-total-vs-ITA-cutoff comparison surfaced by `vault audit --all`.**

## Accomplishments
- Built `crawler/auditors/` as the shared dispatch contract: `DecisionContext`/`DecisionResult`, `register`/`resolve` with a fail-closed AT-RISK default, `FULL_GRID_FACTORS` (18), `FACTOR_GROUP`, `consumed_factor_ids`, idempotent `load_all`.
- Refactored `crawler/auditor.py` into the generic spine: `audit_one` (N/A short-circuit → frozen grounding gate → evidence quarantine → decider dispatch → card assembly), `run_full_audit` (one card per factor + cutoff), and `audit_factor` as a thin back-compat shim.
- Landed the five core deciders (age, education, first/second language, Canadian work) in `crawler/auditors/core.py`, moving the Phase-32 language logic verbatim (parity gate).
- Added `run_full_audit_report`, `vault audit --all`, and the shared `_contract.md`; extended the `no_inlined_volatile_rules` gate to `crawler/auditors/` + `crawler/auditor.py`.

## Task Commits
1. **Task 1: Dispatch spine + package + core language deciders** — `308f562` (feat)
2. **Task 2: Core age/education/work deciders + dispatch tests** — `5ff8eb5` (feat)
3. **Task 3: Full-run report writer + cutoff + vault audit --all + _contract.md** — `015700d` (feat)

## Files Created/Modified
- `crawler/auditors/__init__.py` — dispatch contract + registry + grid manifest.
- `crawler/auditor.py` — generic `audit_one` / `run_full_audit` / `audit_factor` shim.
- `crawler/auditors/core.py` — five core human-capital deciders.
- `crawler/audit_report.py` — `run_full_audit_report` (fail-closed multi-card writer + cutoff line).
- `crawler/cli.py` — `vault audit --all`.
- `skills/crs-auditors/_contract.md` — shared portable auditor contract.

## Decisions Made
- Created `core.py` (with the moved language deciders) in Task 1 rather than Task 2 so `audit_factor`'s dispatch shim keeps `test_auditor.py` green; Task 2 added age/education/work + the dispatch test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task boundary: language deciders moved in Task 1**
- **Found during:** Task 1
- **Issue:** `audit_factor` as a thin shim over `audit_one` requires `core.language.first` to be registered for `test_auditor.py` to pass, but the plan placed `core.py` in Task 2.
- **Fix:** Created `core.py` with the moved language deciders in Task 1; Task 2 expanded it.
- **Committed in:** `308f562`

**2. [Rule 2 - Missing functionality] Added `date_of_birth` field + `eligible_values` context**
- **Found during:** Task 2
- **Issue:** The `FieldName` vocabulary had no birth-date field (age auditing needs a confirmed DOB), and `DecisionContext.by_field` (keyed by field name) collapses multiple same-field work values, breaking multi-document aggregation.
- **Fix:** Added `date_of_birth` to `FieldName` (+ updated the vocabulary-completeness test) and added `DecisionContext.eligible_values` (raw per-document values) populated by the spine.
- **Files modified:** `crawler/models/vault.py`, `crawler/tests/test_extraction_store.py`, `crawler/auditors/__init__.py`, `crawler/auditor.py`
- **Committed in:** `5ff8eb5`

---

**Total deviations:** 2 auto-fixed (1× Rule 3, 1× Rule 2)
**Impact on plan:** Both additive and required for correctness; no scope creep.

## Issues Encountered
None beyond the deviations above.

## Next Phase Readiness
The spine + stubs are in place; Waves 2-3 fill spouse/transferability/additional deciders into the stub files.

---
*Phase: 33-full-modular-crs-auditor-pack*
*Completed: 2026-07-06*

## Self-Check: PASSED

All listed files exist on disk and all task commit hashes are present in git history.
