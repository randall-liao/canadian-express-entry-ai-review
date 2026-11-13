---
phase: 32-auditor-vertical-slice-private-report-contract
plan: 02
subsystem: database
tags: [sqlite, vault, migration, audit-trail, pii]

requires:
  - phase: 29-candidate-vault
    provides: vault.sqlite schema v1/v2, PRAGMA user_version migration pattern, id minters
provides:
  - schema v3 (audit_runs + factor_verdicts tables) via additive migration
  - aud_/ver_ id minters
  - record_audit_run / complete_audit_run / record_factor_verdict + load helpers
affects: [32-04 report writer, 32-05 vault audit CLI]

tech-stack:
  added: []
  patterns:
    - "Additive PRAGMA user_version<N migration branch (CREATE TABLE IF NOT EXISTS)"
    - "ev_ pointers and corpus relpath#ordinal ids persist in SEPARATE json columns"

key-files:
  created:
    - crawler/tests/test_audit_store.py
  modified:
    - crawler/vault.py
    - crawler/tests/test_vault.py
    - crawler/tests/test_extraction_store.py

key-decisions:
  - "record_factor_verdict json.dumps evidence_ids and rule_citation_ids into distinct columns"
  - "complete_audit_run uses COALESCE so partial completion updates don't clobber prior values"
  - "record_factor_verdict fail-closes on out-of-vocab verdict with a PII-safe VaultError"

patterns-established:
  - "Verdict trail is vault-only (already covered by publish-safe VAULT_DB_SUFFIXES)"

requirements-completed: [AUDIT-02, AUDIT-06]

duration: 15min
completed: 2026-07-06
---

# Phase 32 Plan 02: Vault Audit Trail (schema v3) Summary

**Additive schema-v3 migration giving the auditor a durable, vault-only audit trail: an `audit_runs` table (one row per `vault audit`) and a `factor_verdicts` table (one row per verdict) that keep `ev_` evidence pointers and corpus `relpath#ordinal` citations in strictly separate columns.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2 (auto)
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Bumped `SCHEMA_VERSION` 2→3 with an additive `version < 3` migration branch (`CREATE TABLE IF NOT EXISTS`), so a v2 DB upgrades in place with zero mutation of existing rows.
- Added `aud_`/`ver_` id minters and the `record_audit_run` / `complete_audit_run` / `record_factor_verdict` write helpers + `load_audit_run` / `list_factor_verdicts` read helpers.
- Enforced VAULT-03 namespace separation: `evidence_ids_json` (ev_ only) and `rule_citation_ids_json` (corpus only) never cross columns; an invalid verdict fail-closes with `VaultError`.

## Task Commits

Tasks 1 (migration + minters) and 2 (record/load helpers) were implemented cohesively and committed together:

1. **Tasks 1+2: schema-v3 audit trail + helpers** - `833d311` (feat)

## Files Created/Modified
- `crawler/vault.py` — `_SCHEMA_V3_DDL`, v3 migration branch, `aud_`/`ver_` minters, record/complete/load helpers.
- `crawler/tests/test_audit_store.py` — migration-in-place + persistence + id-separation tests (9 tests).
- `crawler/tests/test_vault.py` — frozen schema-version assertions updated 2→3 (in-scope, schema bump).
- `crawler/tests/test_extraction_store.py` — v1→v3 migration assertions updated (in-scope, schema bump).

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_audit_store.py -q` → 9 passed.
- `.venv/bin/python -m pytest crawler/tests/test_vault.py crawler/tests/test_vault_cli.py -q` → green.
- `grep -n "user_version = 3" crawler/vault.py` → additive migration branch present.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Frozen schema-version assertions broke on the v3 bump**
- **Found during:** Task 1 (regression run of frozen vault tests)
- **Issue:** `test_vault.py` and `test_extraction_store.py` asserted `user_version == 2` / `schema_version == "2"`, which is a direct consequence of this plan's mandated `SCHEMA_VERSION` bump to `"3"`.
- **Fix:** Updated the three affected assertions to `3` while preserving each test's intent (v2 tables still present, v1/v2 rows preserved through the migration).
- **Files modified:** `crawler/tests/test_vault.py`, `crawler/tests/test_extraction_store.py`
- **Commit:** `833d311`

### Process note
Tasks 1 and 2 (tightly coupled migration + helpers) were committed together rather than as two atomic commits.

## Known Stubs
None.
