---
phase: 36-operational-hardening
plan: 01
subsystem: cli
tags: [crs, audit, index, preflight, fail-closed, refusal, sqlite, hardening, unittest]

# Dependency graph
requires:
  - phase: 23-fts5-index-builder
    provides: "searchindex.chunk_sha integrity fingerprint + chunks/chunks_fts/meta schema + mode=ro read discipline"
  - phase: 32-crs-auditor
    provides: "_cmd_vault_audit CLI path + run_audit/run_full_audit_report fail-closed verdict-then-persist ordering"
provides:
  - "crawler/index_health.py — typed read-only corpus-index preflight (probe_index -> IndexHealth) with a closed reason-code vocabulary {ok, index_missing, index_empty, index_unreadable, index_corrupt, index_drifted}"
  - "cli._require_readable_index — reusable invalid_input/exit-2 refusal helper (audit now; remediate/review-packet in Phases 37-38) that refuses BEFORE any vault write"
  - "vault audit refuses a bad --db cleanly (PII-free, reason=<code>, index/doctor recovery hint) writing zero artifacts"
affects: [phase-37-remediation, phase-38-review-packet, phase-39-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Typed read-only preflight mirroring doctor.py's dataclass/PII-light shape; open mode=ro, never create/write a DB"
    - "Guard the ENTIRE post-connect body with one try/except sqlite3.DatabaseError so a row/column-level malformation refuses cleanly (index_corrupt) instead of re-raising a traceback"
    - "Bounded chunk_sha drift sample (64 rows) keeps the happy-path preflight O(1)-ish on a 14 MB index; per-citation drift still caught fail-closed by searchindex.resolve"

key-files:
  created:
    - crawler/index_health.py
    - crawler/tests/test_index_health.py
    - crawler/tests/test_audit_index_refusal.py
  modified:
    - crawler/cli.py

key-decisions:
  - "Keep the frozen contract error.type = invalid_input (exit 2 — the same code search/ground return for a bad --db); the specific reason code lives in the message as a stable reason=<code> token (no new contract error type / exit constant)"
  - "0-byte file classified index_empty BEFORE opening (a 0-byte file is a valid empty SQLite DB; opening it would mislabel as missing-tables/corrupt)"
  - "Preflight runs before open_vault so a refusal touches no vault and writes zero audit_runs/report artifacts (reinforces the existing verdict-then-persist ordering)"
  - "Refusal message echoes only the caller-supplied --db path (a corpus path, not PII) + reason code + recovery hint — matching the existing 'not a file: {db}' precedent"

patterns-established:
  - "Every corpus-index-grounded verb should call _require_readable_index first (Phases 37-38 reuse it)"
---

# Phase 36 Plan 01 — Summary

## What shipped
- `crawler/index_health.py`: `IndexHealth(status, reason)` frozen dataclass + `probe_index(db)`
  read-only classifier over the closed reason-code vocabulary, plus a PII-free `message(db)` naming the
  `index`/`doctor` recovery commands.
- `cli._require_readable_index(args, db)`: reusable refusal helper returning `invalid_input`/exit 2 (or
  `None` when healthy); called at the top of `_cmd_vault_audit` **before** `vault.open_vault`.
- Tests: `test_index_health.py` (10 reason-code states incl. the HIGH-1 row-level-malformation case) and
  `test_audit_index_refusal.py` (CLI refusal + exit code + reason token + recovery hint + zero-artifact +
  a skip-guarded real-index positive control).

## Requirements satisfied
- **HARD-01**: missing/empty/unreadable/corrupt/content-drifted index → stable, PII-free refusal on the
  frozen `invalid_input` vocabulary + a specific `reason=<code>`.
- **HARD-02**: refusal exits non-zero (2), recommends the `index`/`doctor` recovery commands, and writes
  no audit/remediation/packet/database artifact (verified: 0 `audit_runs` rows, no report file).

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_index_health.py crawler/tests/test_audit_index_refusal.py crawler/tests/test_vault_audit_cli.py crawler/tests/test_cli.py -q` → all pass.
- Live: `vault audit --all --db corpus/NOPE.db` → `ok:false`, `invalid_input`, exit 2,
  `reason=index_missing`, names `index`/`doctor`; `--db corpus/index.db` still runs (`ok:true`).

## Deviations
None. Incorporated the plan-checker's HIGH-1 (guard the whole post-connect body) and LOW-6 (pass the raw
`args.db` string; `Path` is not imported at cli.py module top) during implementation.

## Notes for later phases
Phases 37 (remediation) and 38 (review-packet) MUST call `_require_readable_index` first on any
corpus-index-grounded verb so they refuse identically and write zero artifacts on a bad index.
