# Phase 36 — Pattern Map: Operational Hardening

**Mapped:** 2026-07-17
Every NEW file/behaviour mapped to its closest existing analog so the phase adds no
novel structure or dependency.

## New / changed source

| New or changed | Closest analog | What to mirror |
|---|---|---|
| `crawler/index_health.py` (typed read-only preflight, `IndexHealth` dataclass + `probe_index`) | `crawler/doctor.py` (`DepStatus`/`DoctorReport` dataclass + `run_doctor`, PII-light `to_result`) | dataclass shape, PII-light reason strings, single `probe_*` entry point, closed status vocabulary |
| read-only `sqlite3` open + drift fingerprint | `crawler/searchindex.py::resolve` (`file:<db>?mode=ro` connect, `chunk_sha` recompute-and-compare) | never write, never create a 0-byte DB, reuse `searchindex.chunk_sha` verbatim |
| `cli._require_readable_index(args, db)` refusal helper | `cli._cmd_search` / `_cmd_ground` `if not db.is_file(): return _fail(INVALID_INPUT, ...)`; `cli._vault_fail` | `invalid_input`/exit 2 refusal envelope, reused across verbs |
| preflight call in `_cmd_vault_audit` before `open_vault` | fail-closed ordering in `audit_report.run_audit` (verdict/write ordering) | refuse before any vault touch → zero artifacts |
| re-keyed `personal.example/crs-profile.example.yaml` | itself (schema unchanged) + `auditors.FULL_GRID_FACTORS` / `FACTOR_GROUP` | canonical dotted ids + groups; values stay synthetic/PII-free |
| adversarial fixtures | `crawler/tests/fixtures/extraction/make_fixtures.py` (`build_pdf(pages, rotations)`) | generated at test time, reportlab-free, never a committed binary |

## New tests

| New test | Closest analog | Pattern |
|---|---|---|
| `crawler/tests/test_index_health.py` | `crawler/tests/test_doctor.py` (if present) / `test_searchindex_*` unit tests | unit table over each reason code; temp DBs built in-test |
| `crawler/tests/test_audit_index_refusal.py` | `crawler/tests/` CLI envelope tests (`--json` stdout parse, exit code, no-artifact assert) | run `_cmd_vault_audit` via CLI, assert envelope/exit/reason + zero `audit_runs` rows written |
| `crawler/tests/test_example_profile_pinned.py` | `crawler/tests/test_siblingfields_vocab.py` (set-equality anti-drift pin) + `test_full_audit_real_seam.py` (skip-guard) | pin example ids ⊆ `FULL_GRID_FACTORS`; real audit path yields ≥1 non-N/A (skip-guarded) |
| `crawler/tests/test_adversarial_extraction_seam.py` | `crawler/tests/test_full_audit_real_seam.py` | REAL `import→extract→confirm→audit`; skip-guarded on `corpus/index.db` + deps; never `add_extracted_value` |

## Anti-patterns explicitly avoided
- No writable index open / write-DDL FTS probe on the read path (WR-01 lesson).
- No new `contract` error type or exit code (frozen vocabulary preserved).
- No committed binary fixtures; no network; no new runtime dependency.
- No relaxation of `is_audit_eligible` or any decider (HARD-04 is a regression net).
