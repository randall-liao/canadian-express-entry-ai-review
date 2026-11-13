---
phase: 24-search-verb-citation-resolver
fixed_at: 2026-06-21T06:18:16Z
review_path: .planning/phases/24-search-verb-citation-resolver/24-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 24: Code Review Fix Report

**Fixed at:** 2026-06-21T06:18:16Z
**Source review:** `.planning/phases/24-search-verb-citation-resolver/24-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (4 warning, 2 info — `fix_scope: all`)
- Fixed: 6
- Skipped: 0

**Contract preservation (verified):** `schema_version` stays `"1.0"`, the five
envelope keys are unchanged, and the exit-code taxonomy is intact — both new CLI
guards reuse the existing `invalid_input` / exit-2 path. The fail-closed grounding
guarantees in `resolve()` (sha-drift / unknown id → `None`) are untouched.

**Tests:** full `crawler/tests/` suite green (167 collected, `pytest` exit 0).
Phase-24 + regression files (`test_searchindex.py`, `test_cli.py`,
`test_json_contract.py`): **91 passed, 1 skipped**. Run via
`.venv/bin/python -m pytest` (bare `python` is broken in this environment).

## Fixed Issues

### WR-01: `search()` wrote to the index on its read-only path (mutation + misclassified FTS5Unavailable)

**Files modified:** `crawler/searchindex.py`
**Commit:** `f12945b`
**Applied fix:** Opened the read path read-only via `sqlite3.connect(f"file:{db}?mode=ro", uri=True)` and removed the `_probe_fts5(con)` call from `search()` (the probe ran `CREATE/DROP VIRTUAL TABLE` — write DDL). A genuinely FTS5-less host now fails loud on the `chunks_fts MATCH ?` query itself, mirroring `resolve()`. Updated the docstring to drop the false "fails loud via `_probe_fts5`" claim. Empirically confirmed: a read no longer mutates the index file bytes, and a read-only/locked DB no longer misreports as missing FTS5.

### WR-02: `--family` LIKE pattern had no `ESCAPE` (wildcard leak)

**Files modified:** `crawler/searchindex.py`
**Commit:** `adc57ce`
**Applied fix:** Escaped `\`, `%`, `_` in the bound `family` value and added `ESCAPE '\'` to the `LIKE ? || '/%'` clause so the family is a literal path prefix. Verified against the synthetic corpus: `--family '%'` → 0 hits (no longer disables the filter), `--family 'pr_pdi'` → 0 hits (no longer matches `pr-pdi`), `--family 'pr-pdi'` → 2 hits (real prefix intact).

### WR-03: `resolve()` opened read-write and auto-created a 0-byte DB on a missing path

**Files modified:** `crawler/searchindex.py`
**Commit:** `3ea0df1`
**Applied fix:** Opened `resolve()` read-only via `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`. A missing/typo'd path now raises an explicit `OperationalError: unable to open database file` with no side-effecting file-create, instead of silently materialising a 0-byte SQLite file then `no such table: chunks`. A genuine miss (unknown id in a real index) still returns `None`, never raises. (`search()`'s half of WR-03 was already satisfied by the `mode=ro` connect in `f12945b`/WR-01.)

### WR-04: mutation test asserted on a row count, not file bytes (masked WR-01)

**Files modified:** `crawler/tests/test_searchindex.py`
**Commit:** `bd73615`
**Applied fix:** `test_search_does_not_mutate_the_index` now sha256-hashes the raw DB bytes before/after a `search()` instead of comparing `count(*) FROM chunks` (which the separate `_probe` table never touched). Empirically confirmed the new assertion FAILS on the old write-DDL probe path and PASSES with the WR-01 read-only fix.

### IN-01: `--limit` accepted a negative value that disabled the cap

**Files modified:** `crawler/cli.py`
**Commit:** `7cea28b`
**Applied fix:** `_cmd_search` rejects `--limit < 1` as `invalid_input` (exit 2) before calling `search()` — SQLite treats a negative `LIMIT` as "no limit", so `-1` previously returned every hit. Verified `--limit -1` and `--limit 0` now exit 2; `--limit 1` still returns ≤1 hit.

### IN-02: `--cite` silently ignored a positional `query`

**Files modified:** `crawler/cli.py`
**Commit:** `4e8d17b`
**Applied fix:** `_cmd_search` rejects a positional `query` supplied together with `--cite` as `invalid_input` (exit 2) instead of silently discarding the query. Verified the both-supplied case exits 2; cite-only and query-only invocations are unchanged.

## Skipped Issues

None — all 6 in-scope findings were fixed.

---

_Fixed: 2026-06-21T06:18:16Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
