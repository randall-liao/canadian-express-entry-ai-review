---
phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
plan: 03
subsystem: eligibility-screening
tags: [mec, fsw, fst, cec, evidence, pydantic, privacy]

requires:
  - phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
    plan: 02
    provides: Strict MEC contracts, exact manifests, immutable gate context, and read-only sidecar seams
provides:
  - Six canonical private review.mec intake forms with closed normalization
  - Deterministic employment-period keys and candidate-scoped five-key evidence adapter
  - Grounded FSW, FST, and CEC evaluators with period-before-aggregation filtering
  - Deterministic side-effect-free private/public MEC publication bundle
affects: [45-04, mec-cli, mec-publication, conformance-v5]

tech-stack:
  added: []
  patterns: [deterministic period envelopes, confirmed-only evidence adapter, registry-derived grid bounds, inert in-memory publication]

key-files:
  created:
    - crawler/mecfields.py
  modified:
    - crawler/models/vault.py
    - crawler/extraction.py
    - crawler/mec_screen.py
    - crawler/tests/test_extraction_store.py
    - crawler/tests/test_extraction_conformance.py
    - crawler/tests/test_vault_cli.py
    - crawler/tests/test_mec_rules.py
    - crawler/tests/test_mec_screen.py

key-decisions:
  - "Each mec-employment-period document owns one content-derived mep_ key; corrections retain the document stamp and cannot create a fallback join."
  - "Unknown or incomplete period facts never aggregate, while deterministic failures require confirmed complete scope."
  - "Stored funds household and amount values are never compared; only a grounded authorization-plus-valid-offer exemption can make the declared branch N/A."
  - "screen_mec returns validated deterministic bytes and models only; durable publication remains exclusively Plan 45-04."

patterns-established:
  - "MEC evidence is queried by candidate, canonical document type, review.mec factor, confirmation status, and the existing five-key audit-eligibility predicate."
  - "Program work predicates filter each keyed period before same-NOC or capped-hours aggregation."

requirements-completed: []

duration: 30min
completed: 2026-07-20
---

# Phase 45 Plan 03: Complete MEC Evidence and Program Evaluators Summary

**Private confirm-first MEC evidence with deterministic employment-period joins and grounded FSW/FST/CEC screening that returns only inert in-memory report material**

## Performance

- **Duration:** 30 min
- **Started:** 2026-07-20T03:54:11Z
- **Completed:** 2026-07-20T04:23:40Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Added all six canonical `review.mec` document routes and exact private evidence fields for anchors, period predicates, trade certificates, offers, funds, destinations, authorization, and status.
- Added deterministic content-derived employment-period IDs, strict internal key agreement, conflict detection, candidate isolation, and confirmed/current/quality-ok evidence gating.
- Implemented complete exact-manifest FSW, FST, and CEC evaluators from usable grounded rows and period-safe evidence, including registry-derived FSW grid bounds and FAIL-first rollup.
- Preserved manual NOC/offer/study/physician boundaries and canonical `funds_snapshot_unavailable` behavior without comparing stored amounts.
- Added deterministic validated private JSON/Markdown and explicit PII-light public JSON in memory with no filesystem or database mutation.

## Task Commits

Each TDD task was committed atomically with the required trailer:

1. **Task 45-03-00 RED: MEC evidence lifecycle tests** - `18ec65c` (test)
2. **Task 45-03-00 GREEN: period-safe private MEC evidence** - `b1ef1f0` (feat)
3. **Task 45-03-01 RED: grounded FSW evaluator tests** - `671d33d` (test)
4. **Task 45-03-01 GREEN: complete FSW evaluator** - `1007b53` (feat)
5. **Task 45-03-02 RED: FST/CEC and bundle tests** - `a04c90e` (test)
6. **Task 45-03-02 GREEN: FST/CEC evaluators and inert bundle** - `d432260` (feat)
7. **Correction lifecycle fix** - `2bb59a0` (fix)
8. **Wave-aware vocabulary contract update** - `1f632ca` (test)

## Files Created/Modified

- `crawler/mecfields.py` - Closed MEC vocabularies, normalizers, deterministic period IDs, candidate-scoped adapter, and conflict-safe period grouping.
- `crawler/models/vault.py` - Additive MEC `FieldName` members only; `FactorGroup` remains unchanged.
- `crawler/extraction.py` - Six factor-locked private forms, inert `review.mec` parent, period stamping, and producer/consumer equality guards.
- `crawler/mec_screen.py` - FSW/FST/CEC evaluators, sidecar composition, report construction, and deterministic in-memory rendering.
- `crawler/tests/test_extraction_store.py` - Vocabulary, correction, confirmation, and period-key coverage.
- `crawler/tests/test_extraction_conformance.py` - Closed normalization, deterministic IDs, and CRS/public-envelope isolation.
- `crawler/tests/test_vault_cli.py` - PII-light canonical MEC import reachability.
- `crawler/tests/test_mec_rules.py` - Phase-aware proof that Wave 3 extends FieldName while preserving FactorGroup.
- `crawler/tests/test_mec_screen.py` - Program distinctions, exclusions, bounds, funds, anti-mixing, sidecar propagation, privacy, and determinism.

## Decisions Made

- Corrections may supply the existing CLI's scalar JSON value; the adapter validates the original period stamp first and then applies the correction inside that immutable document envelope.
- FST hierarchy matching parses major, sub-major, minor, and unit groups structurally and applies exclusions before inclusions.
- CEC evaluates student and self-employment exclusions independently, then intersects accepted periods before recency/hour aggregation.
- Requirements remain pending as requested; Plan 45-04 still owns durable publication and the command boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved period identity through scalar corrections**
- **Found during:** Overall correction-lifecycle review
- **Issue:** The shipped CLI accepts a scalar `--corrected-value`; requiring the correction itself to repeat the internal period envelope would make corrected period facts unusable.
- **Fix:** Validate the original deterministic document stamp, then normalize the scalar correction within that same immutable period.
- **Files modified:** `crawler/mecfields.py`, `crawler/tests/test_extraction_store.py`
- **Verification:** Corrected paid status remains usable in its original keyed period through the real five-key adapter.
- **Committed in:** `2bb59a0`

**2. [Rule 3 - Blocking] Advanced a time-limited Wave-1 vocabulary assertion**
- **Found during:** Overall MEC registry regression verification
- **Issue:** The prior Wave-1 test intentionally asserted that MEC FieldName additions did not exist yet, which became false at the planned Wave-3 boundary.
- **Fix:** Replaced it with the current contract: all additive MEC fields exist and the exact Plan-01 FactorGroup tuple remains unchanged.
- **Files modified:** `crawler/tests/test_mec_rules.py`
- **Verification:** MEC registry and no-inline suites pass.
- **Committed in:** `1f632ca`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking issue)
**Impact on plan:** Both changes enforce the planned lifecycle and wave boundary; no schema, parser, dependency, CRS, or publication scope was added.

## Issues Encountered

- The required three-sidecar conformance command has one pre-existing stale SHA pin for the intentional Plan-45-02 `crawler/study_review.py` change. All other tests in that command pass; the deferred item is recorded in `deferred-items.md` for the Phase 45 conformance plan.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_extraction_store.py crawler/tests/test_extraction_conformance.py crawler/tests/test_vault_cli.py crawler/tests/test_mec_screen.py -q` - 80 passed, 59 subtests passed.
- `.venv/bin/python -m pytest crawler/tests/test_mec_rules.py crawler/tests/test_crs_no_inlined_rules.py -q` - 27 passed, 68 subtests passed.
- Sidecar conformance excluding the one stale prior-plan source pin - 41 passed, 1 deselected, 135 subtests passed.
- `pyproject.toml`, `poetry.lock`, parser version, SQLite DDL/user version, `PublicAuditEnvelope`, `FULL_GRID_FACTORS`, CRS auditor modules, `.venv`, and `.planning/research/.cache/` were untouched.

## Known Stubs

None.

## User Setup Required

None - no dependencies, external services, or configuration were added.

## Next Phase Readiness

- Plan 45-04 can load one snapshot, obtain confirmed evidence through `load_mec_evidence`, call `screen_mec`, scan the returned bytes, and publish private LKG files atomically.
- Durable publication and CLI wiring remain intentionally absent.
- MEC-01 through MEC-04 remain pending until the Plan 45-04 command/publication boundary is complete.

## Self-Check: PASSED

All nine implementation/test files, the summary, and all eight Plan 45-03 task/fix commits were verified on disk.

---
*Phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec*
*Completed: 2026-07-20*
