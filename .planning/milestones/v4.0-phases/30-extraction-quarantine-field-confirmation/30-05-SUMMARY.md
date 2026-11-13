---
phase: 30-extraction-quarantine-field-confirmation
plan: 05
subsystem: extraction
tags: [extraction, crs-audit, factor-linkage, test-type-vocabulary, integration-seam, tdd]

# Dependency graph
requires:
  - phase: 30-02
    provides: extraction engine (_FIELD_SPECS, extract_document, pending-value store)
  - phase: 30-04
    provides: confirm/field-view seam consumed by the real-seam E2E test
  - phase: 31
    provides: registry test_type accepted-enum + grounded conversion tables (pinned to, never modified)
  - phase: 32-33
    provides: factor-specific auditor read (audit_eligible_values by factor_id) consumed via the real seam
provides:
  - Shared canonical test_type vocabulary (crawler/testtypes.py) pinned to the registry accepted-enum
  - Deterministic per-document factor linkage (_DOC_TYPE_FACTOR + rewritten _resolve_factor)
  - CLI `vault extract --factor` override for first/second-language disambiguation
  - date_of_birth extraction from a passport/identity doc, linked to core.age (extraction-side only)
  - Real extract->confirm->audit E2E regression proving SUBSTANTIATED reachability + an anti-drift gate
affects: [milestone-v4.0-audit, extraction, crs-audit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-source-of-truth vocabulary module pinned to the grounded registry by an anti-drift test"
    - "Factor linkage is a property of the DOCUMENT (doc_type -> specific grid factor), not the field"
    - "Fail-closed claimed-factor scoping via parameterized SQL (no cross-factor contamination)"
    - "Real-seam E2E test drives import->extract->confirm->audit (never add_extracted_value)"

key-files:
  created:
    - crawler/testtypes.py
    - crawler/tests/test_testtype_vocab.py
    - crawler/tests/test_extraction_factor_linkage.py
    - crawler/tests/test_full_audit_real_seam.py
  modified:
    - crawler/extraction.py
    - crawler/cli.py
    - crawler/tests/fixtures/extraction/make_fixtures.py
    - crawler/tests/test_extraction_conformance.py
    - crawler/tests/test_extract_confirm_cli.py

key-decisions:
  - "Close the age gap on the EXTRACTION side (passport DOB -> core.age) rather than relaxing the frozen decide_age — keeps the fail-closed auditor byte-for-byte unchanged"
  - "Fail-closed normalize_test_type: an unknown test-type token stays non-accepted (GAP'd unaccepted_test_type) rather than being coerced to an accepted value"
  - "A value's target grid factor is a property of the DOCUMENT, resolved once per document; unclaimed/injected targets leave values unlinked (never contaminated)"
  - "Pin CANONICAL_TEST_TYPES to the registry accepted-enum with a set-equality anti-drift test so the P30<->P31 seam cannot silently diverge again"

patterns-established:
  - "Anti-drift gate: a shared constant asserted set-equal to the grounded registry read exactly as the auditor reads it"
  - "Real-seam regression: exercise the actual shipped pipeline end-to-end, skip-guarded on git-ignored corpus + optional deps"

requirements-completed: [EXTRACT-01, EXTRACT-02]

# Metrics
duration: 23min
completed: 2026-07-06
---

# Phase 30 Plan 05: Extraction→Auditor Integration Gap Closure Summary

**Closed the two milestone INTEGRATION blockers so the real CLI now produces a SUBSTANTIATED `core.language.first` (with a non-zero substantiated total that flows into the ITA cutoff) for a qualified applicant — by centralizing the test_type vocabulary against the registry, making per-document factor linkage deterministic and fail-closed, adding passport→core.age DOB extraction, and locking it all with a real extract→confirm→audit E2E regression + anti-drift gate. The frozen auditor/registry/PII perimeter is byte-for-byte untouched.**

## Performance

- **Duration:** ~23 min
- **Started:** 2026-07-06T14:57:31Z
- **Completed:** 2026-07-06T15:20:32Z
- **Tasks:** 4/4 complete
- **Files created:** 4 · **Files modified:** 5

## Accomplishments
- **BLOCKER B closed:** `IELTS`→`IELTS General Training` and `CELPIP`→`CELPIP-General` (PTE Core / TEF Canada / TCF Canada preserved) via a new shared `crawler/testtypes.py`, pinned to the registry `test_type` accepted-enum by a set-equality anti-drift gate so P30↔P31 can never silently diverge again.
- **BLOCKER A closed:** rewrote `_resolve_factor` from group-alphabetical (`ORDER BY factor_id LIMIT 1`, which dumped every language value on `core.age`) to a deterministic per-document `_DOC_TYPE_FACTOR` mapping, parameterized + scoped to the applicant's CLAIMED factors — an unclaimed/injected target leaves values unlinked (no cross-group/cross-factor contamination). Added a `vault extract --factor` override for first-vs-second-language disambiguation and fixed the latent `issuer` cross-doc collision.
- **Supporting age gap closed:** a `passport`/`identity` doc_type now extracts an ISO `date_of_birth` linked to `core.age`, with a synthetic born-digital `passport_pdf()` fixture — entirely extraction-side (`decide_age`/`crs_audit`/registry untouched).
- **Blind spot closed:** new `test_full_audit_real_seam.py` drives the ACTUAL `import_document → extract_document → confirm_value → run_full_audit_report` seam (never `add_extracted_value`), proving `core.language.first` reaches SUBSTANTIATED, the substantiated total is non-zero and fed into the cutoff comparison, and language scores never land on `core.age`.
- **Verified end-to-end by hand** via the real `corpus-crawler` CLI: `init → profile set → ita set → import → extract → confirm → audit --all` yields `core.language.first` SUBSTANTIATED, **substantiated_total = 650**, cutoff_delta = 180, cards vault-only, stdout PII-light (0 FAKE tokens leaked).

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1: Centralize canonical test_type vocab + normalize at extraction (BLOCKER B)**
   - `983dfe6` (test: failing anti-drift gate) → `a10ca21` (feat: testtypes.py + extraction wiring)
2. **Task 2: Deterministic per-document factor linkage + --factor override (BLOCKER A)**
   - `706ea68` (test: failing linkage tests) → `1cd3ec5` (feat: _DOC_TYPE_FACTOR + rewritten _resolve_factor + CLI --factor)
3. **Task 3: Extract date_of_birth from an identity/passport doc, linked to core.age**
   - `35cabd3` (test: failing passport DOB tests + fixture) → `01308a2` (feat: _FIELD_SPECS[passport]/[identity])
4. **Task 4: Real extract→confirm→audit E2E regression + anti-drift proof (MANDATORY)**
   - `faf8d1f` (test: real-seam E2E regression)

**Plan metadata:** _(final docs commit)_

_TDD tasks 1–3 each carry a RED `test(...)` commit followed by a GREEN `feat(...)` commit._

## Files Created/Modified
- `crawler/testtypes.py` *(created)* — `CANONICAL_TEST_TYPES` frozenset + fail-closed `normalize_test_type`; test NAMES only (outside `no_inlined_volatile_rules`).
- `crawler/extraction.py` *(modified)* — registry-aligned test_type normalization in the `language_test` branch; `_DOC_TYPE_FACTOR` per-document linkage; rewritten parameterized fail-closed `_resolve_factor`; `factor_override` param on `extract_document`; `passport`/`identity` DOB field spec; removed dead `_FIELD_GROUP`.
- `crawler/cli.py` *(modified)* — `vault extract --factor` argument threaded into `extract_document(factor_override=…)`.
- `crawler/tests/fixtures/extraction/make_fixtures.py` *(modified)* — synthetic `passport_pdf()` + FAKE DOB/passport-number/surname sentinels.
- `crawler/tests/test_testtype_vocab.py` *(created)* — 13 tests: P30↔P31 set-equality gate + per-token normalization + fail-closed unknowns + every capturable regex token.
- `crawler/tests/test_extraction_factor_linkage.py` *(created)* — 13 tests: real-seam per-document linkage, issuer no-cross-doc-leak, `--factor` override (incl. CLI), unclaimed→unlinked, injected-id safety, passport DOB→core.age, auditor-untouched structural guard.
- `crawler/tests/test_full_audit_real_seam.py` *(created)* — 3 tests: SUBSTANTIATED reachability, non-zero total-in-cutoff, no cross-factor contamination (skip-guarded on corpus/deps).
- `crawler/tests/test_extraction_conformance.py`, `crawler/tests/test_extract_confirm_cli.py` *(modified)* — updated two SC2 tests that encoded the OLD group-alphabetical linkage (see Deviations).

## Decisions Made
- **Extraction-side age fix.** Chose passport-DOB extraction over relaxing `decide_age`, keeping the frozen fail-closed auditor untouched while making `core.age` substantiable through the real pipeline.
- **Fail-closed vocabulary.** `normalize_test_type` never coerces an unknown token to an accepted value; the untouched decider still GAPs it `unaccepted_test_type`.
- **Document-scoped linkage.** A value's factor follows the DOCUMENT (doc_type → specific grid factor), resolved once per document, and is only linked when that factor is CLAIMED.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Two SC2 conformance tests encoded the OLD (buggy) group-alphabetical linkage**
- **Found during:** Task 2 (deterministic factor linkage)
- **Issue:** `test_extraction_conformance.py::TestSC2` and `test_extract_confirm_cli.py::test_sc2_human_shows_facets_json_is_pii_light` claimed a synthetic factor id `core_lang` and asserted a `language_test` document's values linked to it — relying on the exact `ORDER BY factor_id LIMIT 1` behavior BLOCKER A fixes. Under the corrected per-document linkage a `language_test` doc links to the real grid factor `core.language.first`, so those assertions failed.
- **Fix:** Updated both tests to claim the real grid factor `core.language.first` (the doc_type's deterministic target) and assert the confirmation-view/human-view facets against it. The SC2 intent (five facets exposed; `--json` stays PII-light) is preserved; only the encoded-linkage expectation was corrected.
- **Files modified:** `crawler/tests/test_extraction_conformance.py`, `crawler/tests/test_extract_confirm_cli.py`
- **Verification:** both files green (`44 passed`); full suite green.
- **Committed in:** `1cd3ec5` (part of Task 2)

**2. [Rule 3 — Blocking] `identity` doc_type produced no fields**
- **Found during:** Task 3 (passport DOB)
- **Issue:** `_DOC_TYPE_FACTOR` mapped both `passport` and `identity` → `core.age`, but `_FIELD_SPECS` only carried a `passport` key, so an `identity` document extracted zero `date_of_birth` values (its linkage test failed).
- **Fix:** aliased `_FIELD_SPECS["identity"] = _FIELD_SPECS["passport"]` so either doc_type yields the DOB spec.
- **Files modified:** `crawler/extraction.py`
- **Verification:** `test_identity_doc_type_also_links_to_core_age` green.
- **Committed in:** `01308a2` (part of Task 3)

**3. [Rule 4-adjacent — scope clarification, NOT auto-fixed] Registry CLB-10 first-language points are ungrounded**
- **Found during:** Task 4 (real-seam E2E)
- **Issue:** the shared `language_test_pdf()` fixture's abilities (8.5/7.5/7.0/8.0) convert to CLB 10 for listening/speaking, but the corpus registry grounds only CLB 9 first-language points — so the SUBSTANTIATED `core.language.first` card carries `substantiated_points = None` (contributes 0 to the total).
- **Decision:** This is a pre-existing **registry** grounding boundary, explicitly OUT OF SCOPE (the plan freezes the registry and forbids new grounded rows). It does NOT block the milestone: the language card still reaches **SUBSTANTIATED** through the real seam (the BLOCKER A/B proof), and the substantiated **total is non-zero (650)** from `additional.nomination` (600) + `transfer.foreign_language` (50) and flows into the cutoff comparison. Task 4's assertion #2 was written to the plan's exact wording (total>0, total == sum of substantiated card points, `cutoff_delta == total - cutoff`) — no over-strict per-card language-points assertion that would contradict the frozen registry.
- **Files modified:** none (test authored to match the plan; registry untouched).

---

**Total deviations:** 2 auto-fixed (1×Rule 1, 1×Rule 3) + 1 documented scope clarification.
**Impact on plan:** All auto-fixes were necessary to align pre-existing tests with the corrected (BLOCKER-A) behavior and to make the `identity` alias functional. No scope creep; the frozen auditor/registry/PII perimeter is untouched.

## Verification Results
- **Seam-focused:** `test_testtype_vocab.py test_extraction_factor_linkage.py test_full_audit_real_seam.py` → **29 passed** (13 + 13 + 3).
- **Full regression** (`crawler/tests scripts/tests --deselect crawler/tests/test_dupaudit.py`) → **714 passed, 1 skipped, 0 failures** (baseline 685 → +29 new tests; no regressions across Phases 29–34 or the frozen path).
- **No-inlined-rules gate** (`test_crs_no_inlined_rules.py`) → 4 passed (new files carry test NAMES / linkage logic only).
- **Publish-safe** (`scripts/check_publish_safe.py`) → **0 violations** across 291 tracked files (no synthetic PII fixture tracked).
- **Conformance / SAFE release gate** (`scripts/run_conformance.py`) → **PASS** (SAFE-01..04, 51 tests, exit 0).
- **Frozen-core proof:** `git diff --name-only` since plan start shows **zero** changes under `crawler/auditor.py`, `crawler/auditors/`, `crawler/crs_audit.py`, `crawler/crs_rules.py`, `crawler/data/crs_rules/`.
- **Real E2E CLI drive:** `init → profile set → ita set → import(language_test,passport,eca,nomination) → extract → confirm → audit --all` → `core.language.first` **SUBSTANTIATED** (reason `grounded_substantiated`, real evidence `ev_…`); **substantiated_total = 650**, `cutoff_delta = 180`, `meets_cutoff = True`; SUBSTANTIATED cards = {core.language.first, additional.nomination(600), transfer.foreign_language(50), transfer.certificate_language(0)}; DOB linked to `core.age` (never a language id); stdout envelope PII-light (0 FAKE tokens).

## Known Stubs
None — no stubbed/placeholder data paths introduced. `normalize_test_type` returning the collapsed input for an unknown token is an intentional fail-closed behavior (the unknown stays non-accepted), not a stub.

## Issues Encountered
- The first real E2E `audit --all` invocation failed with a `FOREIGN KEY constraint` because `vault audit --round` expects the ITA round **id**, not the round **label** (`r-cli`). Resolved by omitting `--round` so the auditor auto-selects the latest ITA round (`_latest_ita_round_id`). This is pre-existing CLI ergonomics, unrelated to this plan's changes; noted for awareness.

## Next Phase Readiness
- Both milestone INTEGRATION blockers are closed and locked with a real-seam regression + an anti-drift gate; the v4.0 milestone audit can proceed.
- Follow-up candidate (out of scope here, registry-side / Phase 31 territory): ground CLB-10 first-language points so a top-band language card contributes its own non-zero points to the substantiated total.

---
*Phase: 30-extraction-quarantine-field-confirmation*
*Completed: 2026-07-06*

## Self-Check: PASSED
- All 4 created source/test files exist on disk (`crawler/testtypes.py`, `test_testtype_vocab.py`, `test_extraction_factor_linkage.py`, `test_full_audit_real_seam.py`) + this SUMMARY.
- All 7 task commits verified present in git history (`983dfe6`, `a10ca21`, `706ea68`, `1cd3ec5`, `35cabd3`, `01308a2`, `faf8d1f`).
