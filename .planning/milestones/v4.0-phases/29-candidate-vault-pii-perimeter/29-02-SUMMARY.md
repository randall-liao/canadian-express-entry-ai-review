---
phase: 29-candidate-vault-pii-perimeter
plan: 02
subsystem: database
tags: [sqlite, pydantic, vault, content-addressing, sha256, pii-boundary, evidence-id]

# Dependency graph
requires:
  - phase: 29-candidate-vault-pii-perimeter (plan 01)
    provides: "crawler.paths resolver (candidate_root, resolve_within, PathEscapeError) + pydantic/platformdirs deps"
provides:
  - "crawler/vault.py — private vault.sqlite store (schema+migrations), candidate lifecycle, CRS factor/ITA store, content-addressed document ingest"
  - "crawler/models/vault.py — pydantic v2 models incl. PII-light DocumentSummary/VaultSummary"
  - "evidence_id (ev_) vs citation_id (relpath#ordinal) disjointness predicates (VAULT-03)"
  - "personal.example/crs-profile.example.yaml — synthetic CRS factor example"
affects: [29-03-vault-cli, 29-04-pii-perimeter, phase-30-extraction, phase-32-auditor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-candidate vault.sqlite under personal/candidates/<slug>/ with PRAGMA user_version migrations (mirrors corpus-DB pattern on the PRIVATE side)"
    - "Content-addressed raw files at files/raw/<sha256><ext> — never SQLite BLOBs; identical bytes dedupe on disk, distinct logical record per import"
    - "Two id namespaces provably disjoint: ev_ evidence ids never match relpath#ordinal citation ids"
    - "PII-light boundary models (counts/ids/status) separate from FULL private records (claimed_points/original_name/paths)"

key-files:
  created:
    - crawler/vault.py
    - crawler/models/__init__.py
    - crawler/models/vault.py
    - personal.example/crs-profile.example.yaml
    - crawler/tests/test_vault.py
  modified: []

key-decisions:
  - "One vault.sqlite per candidate root; candidate_id retained as FK on ita_rounds/documents; crs_profile_factors is per-vault (no candidate_id column, matching ARCHITECTURE-v4.0 subset)"
  - "import_profile_yaml catches pydantic ValidationError and re-raises VaultError naming only field-path + error-type (never the value) to hold the PII boundary"
  - "_ensure_candidate INSERT-OR-IGNOREs the FK parent so set_ita_round/import_document work without a prior create_candidate call (Rule 2 correctness under foreign_keys=ON)"

patterns-established:
  - "VaultError(ValueError) mirrors checklist.ProfileError PII-hygiene; CLI maps it to invalid_input/exit 2 (Plan 03)"
  - "Every filesystem write re-anchored through paths.resolve_within; forged .. dest raises PathEscapeError"

requirements-completed: [VAULT-01, VAULT-02, VAULT-03]

# Metrics
duration: 9min
completed: 2026-07-06
---

# Phase 29 Plan 02: Candidate Vault Module Summary

**Private per-candidate `vault.sqlite` (schema + user_version migrations) that stores the CRS factor breakdown and ITA round/cutoff and ingests raw documents as content-addressed `files/raw/<sha256>` files with minted `ev_` evidence ids — provably disjoint from corpus `relpath#ordinal` citation ids, with PII kept in the DB and PII-light summaries for later stdout.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-07-06T05:08:19Z
- **Completed:** 2026-07-06T05:17:44Z
- **Tasks:** 3 (all TDD)
- **Files modified:** 5 (all created)

## Accomplishments
- `crawler/vault.py`: `open_vault` + `PRAGMA user_version` migrations creating the five phase-scoped tables (`vault_meta`, `candidates`, `crs_profile_factors`, `ita_rounds`, `documents`), candidate lifecycle, id minting (`doc_`/`ev_`/`ita_`), and the `is_evidence_id`/`is_citation_id` disjointness predicates.
- CRS factor + ITA round store (`upsert_profile_factor`, `load_profile_factors`, `import_profile_yaml`, `set_ita_round`) and PII-light `summarize_vault`.
- Content-addressed `import_document` writing to `files/raw/<sha256><ext>` (never a BLOB), deduping identical bytes on disk while recording a distinct `doc_`/`ev_` record per import, and returning a PII-light `DocumentSummary`.
- `crawler/models/vault.py` pydantic v2 models incl. the PII-light `DocumentSummary`/`VaultSummary`; synthetic `personal.example/crs-profile.example.yaml` spanning all four CRS groups.
- 19 vault tests (schema/user_version/meta, id-namespace disjointness, factor/ITA round-trip, YAML import, PII-light summary, PII-free error, content-address dedup, corpus-untouched, forged-dest escape).

## Task Commits

1. **Task 1: Vault schema, models, candidate lifecycle + id namespaces** — `f2ee2b4` (feat, TDD)
2. **Task 2: Store CRS factor breakdown + ITA round/cutoff (VAULT-01)** — `24a3306` (feat, TDD)
3. **Task 3: Content-addressed document ingest + evidence-id minting (VAULT-02/03)** — `08580d4` (feat, TDD)

## Files Created/Modified
- `crawler/vault.py` - Vault store: schema/migrations, candidate lifecycle, CRS factor/ITA store, content-addressed ingest, id namespaces, `VaultError`
- `crawler/models/__init__.py` - models package docstring
- `crawler/models/vault.py` - pydantic v2 models (Candidate, CrsProfileFactor, ItaRound, VaultDocument, DocumentSummary, VaultSummary)
- `personal.example/crs-profile.example.yaml` - synthetic PII-free CRS factor example (all four groups)
- `crawler/tests/test_vault.py` - 19 offline unit tests (tmp-dir vaults via `$PR_PERSONAL_DIR`)

## Decisions Made
- One `vault.sqlite` per candidate root; `crs_profile_factors` has no `candidate_id` column (per the ARCHITECTURE-v4.0 subset), while `ita_rounds`/`documents` keep the `candidate_id` FK.
- `import_profile_yaml` re-raises pydantic `ValidationError` as a `VaultError` describing only field-path + error-type (never the value) so no profile PII can reach stdout/stderr.
- `_ensure_candidate` guarantees the FK parent row exists so `set_ita_round`/`import_document` are usable standalone under `foreign_keys=ON`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `_ensure_candidate` FK-parent guard added**
- **Found during:** Task 2/3 (ITA + document writes)
- **Issue:** `ita_rounds`/`documents` carry a `candidate_id` FK and the vault runs with `PRAGMA foreign_keys=ON`; calling `set_ita_round`/`import_document` before `create_candidate` would raise a bare `IntegrityError`.
- **Fix:** Added an internal `_ensure_candidate` that `INSERT OR IGNORE`s the parent row and returns the safe-slug id, called by both writers.
- **Files modified:** crawler/vault.py
- **Verification:** ITA/document tests pass without an explicit `create_candidate` call.
- **Committed in:** 24a3306 / 08580d4

**2. [Rule 3 - Blocking] Reworded docstring to avoid the literal `yaml.load` token**
- **Found during:** Task 1 (verification grep)
- **Issue:** Plan verification greps `crawler/vault.py` for `yaml\.load\b` expecting zero hits; a docstring said "never `yaml.load`", which would trip the check.
- **Fix:** Reworded to "never the unsafe full loader"; actual code uses `yaml.safe_load` only.
- **Files modified:** crawler/vault.py
- **Verification:** `git grep -nE "yaml\.load\b" crawler/vault.py` → none.
- **Committed in:** f2ee2b4

---

**Total deviations:** 2 auto-fixed (1 missing-critical FK guard, 1 blocking verification-grep cleanup)
**Impact on plan:** No scope creep. Both are correctness/verification-alignment fixes.

## Issues Encountered
None during planned work.

## Known Stubs
None — all stored values round-trip; no placeholder data sources. (`page_count` is intentionally `NULL` at import; it is populated in Phase 30 extraction, which is out of scope here.)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `crawler.vault` is ready for Plan 29-03 to expose via additive `vault` CLI verbs.
- PII-light `DocumentSummary`/`VaultSummary` are ready to be the stdout envelope payloads.
- The vault DB + `files/raw/` artifacts are the surface Plan 29-04 must guard in publish-safe/.gitignore.

---
*Phase: 29-candidate-vault-pii-perimeter*
*Completed: 2026-07-06*

## Self-Check: PASSED
- crawler/vault.py — FOUND
- crawler/models/vault.py — FOUND
- crawler/models/__init__.py — FOUND
- personal.example/crs-profile.example.yaml — FOUND
- crawler/tests/test_vault.py — FOUND
- commits f2ee2b4, 24a3306, 08580d4 — FOUND
