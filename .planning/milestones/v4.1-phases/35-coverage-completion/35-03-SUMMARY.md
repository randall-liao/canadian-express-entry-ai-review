---
phase: 35-coverage-completion
plan: 03
subsystem: testing
tags: [extraction, vault, pydantic, field-vocabulary, sibling, pii-boundary, anti-drift, unittest]

# Dependency graph
requires:
  - phase: 30-vault-extraction-confirm
    provides: "the EXTRACT-01 store (add_extracted_value forces pending), the FieldName Literal boundary, _FIELD_SPECS / _DOC_TYPE_FACTOR extraction wiring, the claimed-only _resolve_factor linkage, the shared is_audit_eligible choke point, and the testtypes.py + test_testtype_vocab.py shared-vocabulary anti-drift template"
  - phase: 31-crs-registry
    provides: "the grounded additional.sibling rule row (15 pts, crs-criteria.md#019) that this plan makes reachable and that 35-04's decider will read"
provides:
  - "crawler/siblingfields.py — the ONE shared sibling evidence vocabulary (SIBLING_FIELDS + fail-closed SIBLING_STATUS_ACCEPTED / SIBLING_RELATIONSHIP_ACCEPTED), names/enums only (no CRS points)"
  - "FieldName Literal extended with the four sibling members (free TEXT column — no DDL / migration / PARSER_VERSION bump)"
  - "extraction._FIELD_SPECS['sibling_proof'] (3 text + 1 ISO-date) + _DOC_TYPE_FACTOR['sibling_proof']='additional.sibling' with a producer anti-drift guard"
  - "make_fixtures.sibling_proof_pdf() + FAKE sibling tokens (born-digital, synthetic-only)"
  - "test_siblingfields_vocab.py producer<->consumer set-equality pin + pending-first / claimed-only / per-field-confirm / PII-perimeter regression coverage"
affects: [35-04-sibling-decider-real-seam, phase-37-remediation, review-packet]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared-vocabulary gap closure: a names-only module pinned set-equal to the pydantic Literal boundary AND the extraction spec by an anti-drift test — closes an extraction-side reachability gap for an already-grounded factor without touching the decider"
    - "Producer anti-drift guard: an import-time assertion that the extraction spec's field names equal the shared vocabulary frozenset, complementing the test-time three-way set-equality pin (fail-fast on producer drift)"
    - "Claimed-only, per-document factor linkage reused unchanged for a new doc_type — evidence links to its SPECIFIC grid factor only when that factor is CLAIMED, else UNLINKED (fail-closed, no cross-factor contamination)"

key-files:
  created:
    - crawler/siblingfields.py
    - crawler/tests/test_siblingfields_vocab.py
  modified:
    - crawler/models/vault.py
    - crawler/extraction.py
    - crawler/tests/fixtures/extraction/make_fixtures.py
    - crawler/tests/test_extraction.py
    - crawler/tests/test_extract_confirm_cli.py

key-decisions:
  - "siblingfields.py carries field NAMES + fail-closed accepted-token ENUMS only (no points/levels/caps) so it stays OUTSIDE the no_inlined_volatile_rules scan surface; 35-04's decider reads the sibling points from the grounded registry row, never from here"
  - "Landed the FieldName Literal extension, the _FIELD_SPECS['sibling_proof'] spec, the _DOC_TYPE_FACTOR entry, and the fixture in ONE atomic commit (Pitfall 3): splitting the Literal edit from the spec edit would make add_extracted_value raise ValidationError at the pydantic boundary and the extractor would persist zero values"
  - "No PARSER_VERSION bump: adding a NEW doc_type spec does not change parse logic for existing doc_types, so prior confirmations for other documents stay valid (a bump would needlessly mark them stale via SC4)"
  - "Added an import-time producer guard (spec names == SIBLING_FIELDS) in extraction.py on top of the test-time pin — the plan invited 'reference its members so the producer cannot drift'; this fails fast rather than only at test time"
  - "Reused the shipped add_extracted_value (forces pending) / confirm_value / is_audit_eligible choke point unchanged — no bespoke sibling quarantine or validator"

patterns-established:
  - "Pattern: make an already-grounded-but-unreachable factor capturable by extending the shared field vocabulary + extraction spec + fixture (never the decider), pinned producer<->consumer to prevent silent drift"

requirements-completed: [COV-03]

# Metrics
duration: 9min
completed: 2026-07-17
---

# Phase 35 Plan 03: Sibling Evidence Field Vocabulary (COV-03) Summary

**The already-grounded `additional.sibling` factor is now reachable on the evidence side: a `sibling_proof` document imports and extracts relationship / status / Canadian-residence / date-of-birth as four born-`pending` fields through one shared vocabulary (`crawler/siblingfields.py`, pinned set-equal to the `FieldName` Literal and `_FIELD_SPECS['sibling_proof']` by an anti-drift test), each individually confirm/correct/reject-able and linked claimed-only to `additional.sibling` — no decider change, no migration, no `PARSER_VERSION` bump.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-07-17T08:09:57Z
- **Completed:** 2026-07-17T08:18:48Z
- **Tasks:** 3
- **Files modified:** 7 (2 created, 5 modified)

## Accomplishments
- Closed COV-03: the sibling factor was structurally unreachable because the EXTRACT-01 field vocabulary carried no sibling fields; an applicant can now import sibling relationship/status/age/Canadian-residence proof, extract it as `pending`, and confirm/correct/reject each field before audit use.
- Added `crawler/siblingfields.py` — the single shared sibling vocabulary (`SIBLING_FIELDS` + fail-closed `SIBLING_STATUS_ACCEPTED` = `{citizen, permanent_resident}` and `SIBLING_RELATIONSHIP_ACCEPTED` = `{brother, sister}`), names/enums only. It carries no CRS points, so it stays off the `no_inlined_volatile_rules` surface (verified green).
- Extended the `FieldName` Literal with the four sibling members (free `TEXT` column — no DDL/migration), added `_FIELD_SPECS['sibling_proof']` (3 `text` + 1 `date` routed through the shipped `_normalize_date` ISO path) and `_DOC_TYPE_FACTOR['sibling_proof'] = 'additional.sibling'`, plus an import-time producer anti-drift guard. `PARSER_VERSION` unchanged.
- Pinned producer↔consumer agreement with `test_siblingfields_vocab.py`: `SIBLING_FIELDS` == the `sibling_`-prefixed `FieldName` members (read via `typing.get_args`) == the `_FIELD_SPECS['sibling_proof']` names (read via tuple-unpacking) — drift in ANY direction fails loudly.
- Proved the full COV-03 evidence chain end-to-end: real extraction yields four born-`pending` fields (DOB → ISO `1988-03-12`); linkage is claimed-only (`additional.sibling` when claimed, `factor_id` `None` when unclaimed, never `core.age`/`additional.nomination`); each field is individually confirm/correct/reject-able through the shipped `is_audit_eligible` choke point; and no FAKE sibling PII token appears on any `--json` stdout envelope. `vault import --doc-type sibling_proof` works with no CLI code change (free-form `--doc-type`).

## Task Commits

Each task was committed atomically (with the `Co-authored-by: Copilot` trailer):

1. **Task 1: Wave 0 — sibling shared-vocab anti-drift pin (RED before vocab)** — `fd22665` (test)
2. **Task 2: Land the sibling vocabulary + extraction spec + fixture (one atomic change)** — `5fadae7` (feat)
3. **Task 3: Prove pending-first extraction + per-field confirm/correct/reject + claimed-only linkage** — `03791c3` (test)

**Plan metadata:** _(final docs commit — see below)_

_RED→GREEN gate sequence present in git log: Task 1 `test` pin (`fd22665`) fails RED (ImportError: `crawler.siblingfields` absent) → Task 2 `feat` (`5fadae7`) lands the vocab and turns it GREEN._

## Files Created/Modified
- `crawler/siblingfields.py` *(created)* — the shared sibling vocabulary: `SIBLING_FIELDS` frozenset + fail-closed `SIBLING_STATUS_ACCEPTED` / `SIBLING_RELATIONSHIP_ACCEPTED` enums. Pure stdlib; names/enums only (no CRS points → off the no-inlined-rules surface). Mirrors the Phase-30 `testtypes.py` template.
- `crawler/tests/test_siblingfields_vocab.py` *(created)* — stdlib `unittest` producer↔consumer set-equality pin: three-way equality (vocab == `FieldName` sibling members == spec names, each read the way its owner reads it), the exact four-member guard, fail-closed accepted-enum equality for status/relationship, and the `additional.sibling` linkage-target guard.
- `crawler/models/vault.py` *(modified)* — extended the `FieldName` Literal with `sibling_relationship`, `sibling_status`, `sibling_residence`, `sibling_date_of_birth` under a `# sibling in Canada` comment near the nomination members. Out-of-vocab names still rejected at the boundary.
- `crawler/extraction.py` *(modified)* — imported `siblingfields`; added `_FIELD_SPECS['sibling_proof']` (relationship/status/residence `text` + DOB `date`), `_DOC_TYPE_FACTOR['sibling_proof'] = 'additional.sibling'`, and an import-time producer guard asserting the spec names equal `siblingfields.SIBLING_FIELDS`. `PARSER_VERSION` unchanged.
- `crawler/tests/fixtures/extraction/make_fixtures.py` *(modified)* — added distinctive FAKE sibling constants and `sibling_proof_pdf()` (born-digital, synthetic-only; the four `label: value` lines match the spec regexes; the title avoids the field-label keywords so each line is the sole match).
- `crawler/tests/test_extraction.py` *(modified)* — added `TestSiblingExtraction` (real-extraction, skip-guarded on deps): pending-first, claimed-only linkage (linked when claimed, UNLINKED when not, never cross-factor), and the FAKE-tokens-stay-in-vault PII perimeter.
- `crawler/tests/test_extract_confirm_cli.py` *(modified)* — added `TestSiblingConfirm` (seed-based confirm/correct/reject + per-field + PII-light summary) and two `TestExtractConfirmCli` cases driving `crawler.cli.main` end-to-end over `--doc-type sibling_proof` (4 pending values, confirm/correct/reject → `audit_eligible`, no sibling PII on any `--json` envelope).

## Decisions Made
- **Names-only vocabulary, off the volatile surface.** `siblingfields.py` carries field names + fail-closed accepted-token enums but zero CRS points/levels/caps, so it does not appear on the `no_inlined_volatile_rules` scan and cannot inline a volatile threshold. The 15-pt sibling value and the adult/minor age threshold remain the grounded registry's job (35-04 reads them).
- **One atomic vocabulary landing (Pitfall 3).** The `FieldName` Literal extension, the `_FIELD_SPECS['sibling_proof']` spec, the `_DOC_TYPE_FACTOR` entry, and the fixture shipped in a single commit. Splitting the Literal edit from the spec edit would trip the pydantic boundary (`add_extracted_value` raises `ValidationError`) and persist zero values.
- **No `PARSER_VERSION` bump.** Adding a new doc_type spec does not change parse logic for existing doc_types, so prior confirmations for other documents stay valid; a bump would needlessly mark them stale via SC4.
- **Belt-and-suspenders producer guard.** Beyond the test-time three-way pin, an import-time assertion in `extraction.py` fails fast if the spec's field names ever drift from `siblingfields.SIBLING_FIELDS`.
- **Reused the shipped choke points.** No bespoke sibling quarantine/validator: `add_extracted_value` forces `pending`, and `confirm_value` / `is_audit_eligible` own the pending-first + 5-key-staleness invariant unchanged.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0.
**Impact on plan:** The plan's Task 1 → Task 2 → Task 3 sequence executed as specified; the RED→GREEN gate landed as designed and every task's acceptance criteria passed on the first verification loop.

## Issues Encountered
- **Pre-existing publish-safe failures (OUT OF SCOPE, already deferred).** The repo-wide publish-safe scanner is RED at baseline because a handful of tracked `.planning/` prose lines contain the absolute home-directory path patterns the scanner itself hunts (documented in `deferred-items.md`, committed for milestone-v4.1 research and the 35-01 plan — all before this plan). This plan changed only files under `crawler/`; scanning my seven created/modified files individually reports **0** absolute-path-leak lines, so this plan adds no new violation. Not fixed here (scope boundary: only auto-fix issues directly caused by the current task's changes); it stays logged in `deferred-items.md` with suggested owner Phase 36 (Operational Hardening). This SUMMARY was written to avoid reproducing the trigger patterns so it adds none.

## Known Stubs

None — the evidence chain is wired end to end: the shared vocab feeds both the `FieldName` boundary and the extraction spec, `sibling_proof_pdf()` exercises the real extractor, values are born `pending`, linkage is claimed-only, and each field flows through the shipped confirm/eligibility choke point. No placeholder/empty data source.

## Threat Flags

None new. The change is additive on the existing Phase-30 extraction seams — no new network endpoint, auth path, or file-access pattern. The plan's `<threat_model>` mitigations are implemented and tested: **T-35-03** (malicious/low-quality sibling document) — `add_extracted_value` forces `pending`, `is_audit_eligible` blocks pending/rejected/low_quality/ambiguous/stale, extraction is structural-only; **T-35-04** (evidence bleeds into age/nomination or an unclaimed-factor injection) — `_DOC_TYPE_FACTOR['sibling_proof']='additional.sibling'` + claimed-only `_resolve_factor` (parameterized SQL), asserted UNLINKED when unclaimed and never `core.age`/`additional.nomination`; **T-35-05** (sibling PII leaks to stdout/tracked files) — new values are vault-only, the `FieldName` Literal rejects out-of-vocab keys, and the PII-perimeter tests assert FAKE tokens never reach `--json` stdout; **T-35-06** (vocabulary drift silently GAPs a qualified applicant) — one shared `siblingfields.py` pinned set-equal to `FieldName` + `_FIELD_SPECS` by `test_siblingfields_vocab.py` plus the import-time producer guard.

## User Setup Required

None - no external service configuration required. Zero new runtime dependencies; no DB migration; no CLI code change (free-form `--doc-type`).

## Next Phase Readiness
- COV-03 is closed: the sibling evidence is now capturable, born-quarantined, claimed-scoped, and per-field confirmable through the shipped choke points. 35-04 (COV-04) can now make `decide_sibling` reachable and prove the real import→extract→confirm→audit sibling seam (adult → SUBSTANTIATED, minor → AT-RISK `sibling_minor`) — this plan deliberately did NOT touch the decider.
- The shared-vocab producer↔consumer pin (`test_siblingfields_vocab.py`) guards against silent re-divergence; a future rename on any of the three sides fails the pin.
- One pre-existing publish-safe violation set in tracked `.planning/` docs remains deferred to Phase 36 per `deferred-items.md`.

## Verification Evidence

- Plan verification: `pytest crawler/tests/test_siblingfields_vocab.py crawler/tests/test_extraction.py crawler/tests/test_extract_confirm_cli.py crawler/tests/test_crs_no_inlined_rules.py -q` → **47 passed**.
- Sibling-specific tests (verbose, to confirm PASS not SKIP): `TestSiblingExtraction` (4) + `TestSiblingConfirm` (5) + two `TestExtractConfirmCli` sibling CLI cases → **11 passed**.
- Task 1 RED evidence: before Task 2, `pytest crawler/tests/test_siblingfields_vocab.py` → collection error `ImportError: cannot import name 'siblingfields' from 'crawler'` (the intended RED).
- Wave regression (VALIDATION.md): `pytest crawler/tests/test_auditors_additional.py crawler/tests/test_crs_conversion_coverage.py crawler/tests/test_testtype_vocab.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_full_audit_real_seam.py -q` → **38 passed, 5 subtests passed**.
- Broader touched-surface sweep: `pytest crawler/tests/test_vault.py crawler/tests/test_extraction_factor_linkage.py crawler/tests/test_audit_models.py crawler/tests/test_conformance_v40_no_false_green.py crawler/tests/test_full_audit_integration.py -q` → **69 passed, 148 subtests passed** (the `FieldName` extension broke nothing).
- Plan verification snippets: the three-set equality one-liner prints `True`; `_DOC_TYPE_FACTOR['sibling_proof']` prints `additional.sibling`; `PARSER_VERSION` still `1`.
- Pydantic boundary: constructing an `ExtractedValue` with each of the four sibling field names succeeds; an out-of-vocab `sibling_bogus` still raises `ValidationError` (fail-closed).
- Publish-safe: each of the seven created/modified `crawler/` files scanned individually → **0** absolute-path-leak lines (this plan adds no new violation).

---
*Phase: 35-coverage-completion*
*Completed: 2026-07-17*

## Self-Check: PASSED

- `crawler/siblingfields.py` — FOUND on disk.
- `crawler/tests/test_siblingfields_vocab.py` — FOUND on disk.
- `.planning/phases/35-coverage-completion/35-03-SUMMARY.md` — FOUND on disk.
- Modified files (`crawler/models/vault.py`, `crawler/extraction.py`, `crawler/tests/fixtures/extraction/make_fixtures.py`, `crawler/tests/test_extraction.py`, `crawler/tests/test_extract_confirm_cli.py`) — all FOUND on disk.
- Commits `fd22665` (RED `test`), `5fadae7` (GREEN `feat`), `03791c3` (`test`) — all present in git log; RED→GREEN gate sequence intact.
- `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer present on all three task commits.
- Plan verification green (47 passed) and every task's acceptance criteria verified; the three-set equality prints `True` and `_DOC_TYPE_FACTOR['sibling_proof']` is `additional.sibling`.
- Publish-safe scan of the seven changed `crawler/` files individually → 0 new violations (the only repo-scan failures are the pre-existing tracked-`.planning/` docs set, out of scope, logged in `deferred-items.md`; this SUMMARY avoids reproducing the trigger patterns).
