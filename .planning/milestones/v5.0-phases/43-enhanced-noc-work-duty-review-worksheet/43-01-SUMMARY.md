---
phase: 43-enhanced-noc-work-duty-review-worksheet
plan: 01
subsystem: api

tags: [noc-2021, worksheet, grounding, vault, quarantine, review.noc, idempotency, sqlite, pydantic]

# Dependency graph
requires:
  - phase: 25-retrieval
    provides: searchindex.resolve exact chunk_id lookup + chunk_sha fingerprint
  - phase: 25-grounding
    provides: grounding.quote_is_grounded retrieve-what-you-cite gate
  - phase: 30-extraction-confirmation-store
    provides: vault add_extracted_value (born-pending) / import_document / record_extraction_run / upsert_profile_factor / audit_eligible_values + FieldName closed enum
  - phase: 32-audit
    provides: audit_report.SCREENING_NOTICE (SAFE-04 framing)
provides:
  - "crawler/noc_worksheet.py: exact-NOC retrieval (resolve_noc_spans), deterministic per-duty split (split_duties), vault-only cited worksheet renderer, inert review.noc FK-parent seed, born-pending per-item capture on review.noc, idempotent regeneration via (duty_id, duty_sha) dedup"
  - "noc_duty / noc_lead_statement FieldName members (code-only closed-enum, no DB migration)"
  - "The {duty_id, duty_sha, citation} noc_duty value contract + factor_id='review.noc' isolation contract consumed by Plan 02 (sidecar) and Plan 03 (CLI)"
affects: [43-02-inert-sidecar, 43-03-cli, 43-04-core-work-byte-identity]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies — composes only frozen primitives
  patterns:
    - "Exact chunk_id retrieval ONLY (never search()/BM25) — a ranked lookup can return a neighbour occupation"
    - "Fail-closed retrieval: any miss/hash-drift/quote-drift -> None refusal, never fabricated duty text"
    - "Inert review-only factor (review.noc) as an FK parent seeded by data upsert, kept out of FULL_GRID_FACTORS to isolate from the frozen core.work grid"
    - "Idempotent capture keyed by (duty_id, duty_sha): exact match reuses value_id (no re-status), drift inserts one new pending row and leaves the old untouched"

key-files:
  created:
    - crawler/noc_worksheet.py
  modified:
    - crawler/models/vault.py
    - crawler/tests/test_noc_review.py
    - crawler/tests/test_extraction_store.py

key-decisions:
  - "Lead statement captured with duty_id=<code>:1:00 (chunk-ordinal 1) so it never collides with a duty's <code>:2:NN id space"
  - "generate_worksheet renders + writes the vault-only artifact on every call (deterministic bytes) but imports a new document + extraction_run ONLY when >=1 new value is inserted; an exact rerun reuses the newest existing noc_worksheet document"
  - "worksheet_doc_id on an exact rerun resolves via _newest_worksheet_document (added_at DESC) so the returned identity stays stable without a duplicate import"
  - "PII-light summary carries only {noc_code, worksheet_doc_id, value_ids, duty_count, citations}; raw duty text + worksheet body stay vault-only"

patterns-established:
  - "Pattern: retrieve-what-you-cite for every split span (grounding.quote_is_grounded gate at generation time)"
  - "Pattern: narrow read-only dedup helper (_existing_duty_values) JOINing documents on candidate_id — no bulk status mutation, no schema migration"

requirements-completed: [NOC-01, NOC-02]

# Metrics
duration: 25min
completed: 2026-07-19
---

# Phase 43 Plan 01: Enhanced NOC Work-Duty Review Worksheet Summary

**Grounded NOC-2021 duty worksheet generator: exact-chunk_id retrieval, deterministic per-duty split with stable (duty_id, duty_sha) fingerprints, a vault-only cited worksheet, and idempotent born-pending capture on a dedicated inert `review.noc` factor (never `core.work`).**

## Performance

- **Duration:** ~25 min (whole plan, across the truncated + resumed executor)
- **Started:** 2026-07-19T05:18:00-04:00
- **Completed:** 2026-07-19T05:43:00-04:00
- **Tasks:** 3 (all complete)
- **Files modified:** 4

## Accomplishments
- `resolve_noc_spans` / `split_duties` (Task 2, prior commit): `\d{5}`-validated exact `chunk_id` retrieval of #001/#002/#003 via the frozen `searchindex.resolve` (never `search()`/BM25), a deterministic idempotent duty split preserving grouped sub-occupation headers verbatim (no classification / no "essential" invention), with stable `duty_id`/`duty_sha` fingerprints and a `grounding.quote_is_grounded` check on every span. Any miss/drift fails closed to `None`.
- `generate_worksheet` (Task 3, this session): renders the `SCREENING_NOTICE`-prefixed cited worksheet, writes it strictly under the vault via `paths.resolve_within` (never `corpus/`), imports it as a `noc_worksheet` document, seeds the inert `review.noc` FK parent as a one-time data upsert, and mints 1 lead + N duty born-pending values on `factor_id="review.noc"` (never `core.work`).
- Idempotent regeneration via the narrow read-only `_existing_duty_values` dedup: an exact `(duty_id, duty_sha)` match reuses the existing `value_id` (no new row, status preserved), a brand-new `duty_id` inserts exactly one born-pending row, and a same-`duty_id`/new-`duty_sha` drift inserts at most one new row while leaving the old value untouched.
- `noc_duty` / `noc_lead_statement` closed-enum FieldName members (Task 1, prior commit) with no DB migration.

## Task Commits

Each task was committed atomically:

1. **Task 1: FieldName vocabulary + RED worksheet test scaffold** — `9a21bfa` (feat) — *committed in a prior executor session*
2. **Task 2: exact-NOC retrieval + deterministic per-duty split** — `89c62c3` (feat) — *committed in a prior executor session*
3. **Task 3: vault-only cited worksheet + born-pending per-item capture** — `e3ca2c5` (feat) — *this session*

**Deviation (Rule 1):** `4aa749d` (fix) — sync FieldName completeness sentinel

**Plan metadata:** _(final docs commit — see completion)_

_Note: this plan was resumed after a truncated executor response; Tasks 1–2 were already committed and verified, so they were NOT re-executed or rewritten._

## Files Created/Modified
- `crawler/noc_worksheet.py` (331 lines) — exact-NOC retrieval, deterministic per-duty split, vault-only cited worksheet renderer, inert `review.noc` FK-parent seed, born-pending capture, and idempotent `(duty_id, duty_sha)` regeneration.
- `crawler/models/vault.py` — `noc_duty` + `noc_lead_statement` closed-enum FieldName members (code-only, no migration).
- `crawler/tests/test_noc_review.py` (301 lines) — worksheet retrieval / split / citation / fail-closed / vault-only / born-pending / idempotent-rerun / changed-sha unit coverage.
- `crawler/tests/test_extraction_store.py` — completeness-sentinel expected set updated for the NOC-02 vocabulary extension (deviation, see below).

## Decisions Made
- Lead statement id-space (`<code>:1:00`) is kept distinct from duty id-space (`<code>:2:NN`) so the lead and duty 0 never collide in the dedup map.
- The vault artifact is (re)written deterministically on every call, but a new document + `extraction_run` are created only when ≥1 new value is inserted; an exact rerun reuses the newest existing `noc_worksheet` document so `{worksheet_doc_id, value_ids, duty_count}` stays byte-stable.
- The FK-parent factor is `review.noc` in `FactorGroup=additional_points` with `claimed_points=None` — an inert data upsert, deliberately absent from `FULL_GRID_FACTORS`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Sync FieldName completeness sentinel with the NOC-02 vocabulary extension**
- **Found during:** Task 3 verification (running the regression suite the plan's `<verification>` requires)
- **Issue:** `test_extraction_store.py::test_field_name_vocabulary_is_complete` pins the exact `FieldName` Literal as a closed-enum sentinel. Task 1 (already committed) legitimately added `noc_lead_statement`/`noc_duty` per NOC-02 but did not update this sentinel's `expected` set, so it failed. This is a regression directly caused by this plan's Task 1 change to `crawler/models/vault.py` (in scope).
- **Fix:** Added the two Phase-43 members to the sentinel's `expected` set under a Phase 43 comment so the completeness check tracks the legitimate extension.
- **Files modified:** `crawler/tests/test_extraction_store.py`
- **Verification:** `test_extraction_store.py` now passes (71 passed, 12 subtests) with no source change to the vocabulary itself.
- **Committed in:** `4aa749d` (separate atomic `fix` commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix keeps the closed-enum sentinel honest without weakening it (the vocabulary boundary is still enforced verbatim). No scope creep; no schema/dependency change.

## Issues Encountered
- The plan's `<verification>` names `crawler/tests/test_vault_schema.py`, which does not exist in this repo. The equivalent quarantine-store / schema coverage lives in `crawler/tests/test_vault.py` + `crawler/tests/test_extraction_store.py`; those were run instead and pass (no migration/regression). The confirm-flow suite `crawler/tests/test_extract_confirm_cli.py` also passes.
- The full `crawler/tests/` sweep includes real-network integration/seam suites (e.g. full-audit real-seam / DLI snapshot) that hang offline; they are unrelated to this plan's changes. The 149 offline FieldName/vault/extraction-touching suites all pass, fully exercising the vocabulary extension.

## Verification Results
- `.venv/bin/python -m pytest crawler/tests/test_noc_review.py -q` → **12 passed** (full worksheet slice green).
- `.venv/bin/python -m pytest crawler/tests/test_vault.py test_extraction_store.py test_extract_confirm_cli.py -q` → **71 passed, 12 subtests** (quarantine store + confirm flow, no migration/regression).
- 149 offline FieldName/vault/extraction/auditor/conformance suites → **all passed** (no wider regression).
- No-new-dependency gate: `git diff pyproject.toml` → **empty** (zero dependency change).
- No-scoring / no-fuzzy scan of `crawler/noc_worksheet.py` → clean (the only `search`/`BM25` tokens are NEGATED docstring references; the code uses `searchindex.resolve` only).

## Known Stubs
None — every rendered/captured span comes from the resolved pinned corpus; there are no hardcoded empty values, placeholder text, or unwired data sources.

## Next Phase Readiness
- The `{duty_id, duty_sha, citation}` `noc_duty` value contract and the `factor_id="review.noc"` isolation contract are ready for Plan 02 (inert sidecar via `audit_eligible_values(v, "review.noc")` + current-key filtering) and Plan 03 (CLI).
- The AST-aware no-scoring / no-fuzzy source scan over both NOC modules is intentionally deferred to Plan 02 Task 2 (so it can exclude docstrings/comments rather than a fragile raw grep).
- Plan 04 will assert `core.work` audit byte-identity before/after worksheet generation + regeneration; the `review.noc` isolation implemented here is the enabling invariant.

---
*Phase: 43-enhanced-noc-work-duty-review-worksheet*
*Completed: 2026-07-19*

## Self-Check: PASSED
- Files verified on disk: `crawler/noc_worksheet.py`, `crawler/models/vault.py`, `crawler/tests/test_noc_review.py`, `crawler/tests/test_extraction_store.py`, `43-01-SUMMARY.md` — all FOUND.
- Commits verified in git history: `9a21bfa` (Task 1), `89c62c3` (Task 2), `e3ca2c5` (Task 3), `4aa749d` (Rule 1 fix) — all FOUND.
