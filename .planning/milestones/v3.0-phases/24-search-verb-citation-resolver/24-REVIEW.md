---
phase: 24-search-verb-citation-resolver
reviewed: 2026-06-21T06:10:05Z
depth: deep
files_reviewed: 5
files_reviewed_list:
  - crawler/searchindex.py
  - crawler/cli.py
  - crawler/contract.py
  - crawler/CONTRACT.md
  - crawler/tests/test_searchindex.py
findings:
  critical: 0
  warning: 4
  info: 2
  total: 6
status: resolved
resolved_at: 2026-06-21T06:18:16Z
resolved_iteration: 1
fixes:
  WR-01: f12945b
  WR-02: adc57ce
  WR-03: 3ea0df1
  WR-04: bd73615
  IN-01: 7cea28b
  IN-02: 4e8d17b
---

# Phase 24: Code Review Report

**Reviewed:** 2026-06-21T06:10:05Z
**Depth:** deep (read-side cross-file trace + empirical reproduction in `.venv`)
**Files Reviewed:** 5 (production scope: `searchindex.py`, `cli.py`, `contract.py`, `CONTRACT.md`, `test_searchindex.py`)
**Status:** resolved (all 6 findings fixed 2026-06-21 — see Resolution below)

## Resolution

All 6 findings (4 warning, 2 info) were fixed and committed atomically; the full
`crawler/tests/` suite is green (167 tests, exit 0; phase-24 + CLI + json-contract
files: 91 passed, 1 skipped). The frozen CONTRACT is preserved: `schema_version`
stays `"1.0"`, the five-key envelope is unchanged, and the exit-code taxonomy is
intact (the new guards reuse the existing `invalid_input`/exit-2 path). The
fail-closed grounding guarantees in `resolve()` (sha-drift / unknown id → `None`)
are untouched.

| Finding | Resolution | Commit |
|---------|-----------|--------|
| WR-01 | `search()` opens the DB read-only (`file:<db>?mode=ro`) and the write-DDL `_probe_fts5()` call is removed from the read path | `f12945b` |
| WR-02 | `--family` LIKE metacharacters (`\` `%` `_`) are escaped with an `ESCAPE '\'` clause — literal prefix match, no wildcard leak | `adc57ce` |
| WR-03 | `resolve()` opens the DB read-only (`file:<db>?mode=ro`) — explicit error on a missing path, never a 0-byte file-create | `3ea0df1` |
| WR-04 | `test_search_does_not_mutate_the_index` now hashes the raw DB bytes (verified to FAIL on the old probe, PASS on the fix) | `bd73615` |
| IN-01 | `_cmd_search` rejects non-positive `--limit` as `invalid_input` (exit 2) so `-1`/`0` cannot disable the cap | `7cea28b` |
| IN-02 | `_cmd_search` rejects a positional `query` together with `--cite` as `invalid_input` (exit 2) instead of silently ignoring the query | `4e8d17b` |

## Summary

Phase 24 adds the read side of the retrieval layer: `_to_match()` (FTS5 query
escaper), `search()` (BM25 query), `resolve()` (citation resolver with a
fail-closed staleness guard), `EmptyQuery`, the `_cmd_search` CLI handler +
`p_search` subparser, and the additive `search` contract docs.

**The three highest-risk surfaces this phase owns are SOUND — verified empirically:**

- **FTS5 / SQL injection (the whole untrusted attack surface):** `_to_match()`
  (`searchindex.py:400`) tokenizes on `\w+` and re-quotes every token as an FTS5
  string literal joined by spaces. Adversarial inputs (`R30(3)`, `body:funds`,
  `women's`, `police OR certificates`, `NEAR(a b)`, `"; DROP`) all reduce to
  inert quoted literals — no operator/column-filter injection, no `fts5: syntax
  error`. The escaped string is the only value bound to `MATCH ?`; `family` and
  `limit` are parameter-bound; no user value is ever f-stringed into SQL. **No
  injection path found.**
- **Ungrounded/uncited leak:** `resolve()` (`searchindex.py:487`) is correctly
  fail-closed — unknown id → `None`, and a content-drift guard recomputes
  `chunk_sha(text)` over the **stored** text and returns `None` on mismatch
  (verified consistent with `build_index`'s stored `chunk_sha`, `searchindex.py:351`).
  `text` is returned verbatim, never a snippet. **No ungrounded-result path found.**
- **Contract envelope:** `command="search"` is added consistently to
  `contract.py` and `CONTRACT.md`; `schema_version` stays `"1.0"`; every exit path
  goes through `contract.envelope(...)`, so the frozen 5-key envelope is preserved.
  Exit-code mapping is correct (EmptyQuery → invalid_input/2, FTS5Unavailable →
  missing_dependency/3, `--cite` miss → ok:true/exit 0). **No contract break found.**

The defects below are **robustness/correctness**, not grounding or injection.
The lead finding (WR-01) is a genuine read-path bug confirmed to manifest on the
**default** writable path (every `search()` mutates the index file) and to break
`search()` outright on a read-only or locked DB with a *misleading* error.

All 59 tests in `crawler/tests/test_searchindex.py` pass (`.venv/bin/python -m
pytest`, 3.42s).

## Critical Issues

None. The injection, fail-closed-grounding, and contract-envelope surfaces are sound.

## Warnings

### WR-01: `search()` writes to the index on its documented read-only path — mutates the "frozen/diffable" DB on every call and misreports read-only/locked DBs as `FTS5Unavailable`

> **✅ RESOLVED** (`f12945b`): `search()` now connects via `file:<db>?mode=ro` and the read-path `_probe_fts5()` call is removed.

**File:** `crawler/searchindex.py:451` (the `_probe_fts5(con)` call inside `search()`); root mechanism at `crawler/searchindex.py:109-125`; false docstring claim at `crawler/searchindex.py:441` ("Read-only: SELECT only, no mutation of the index.")

**Issue:** `search()` calls `_probe_fts5(con)`, which executes `CREATE VIRTUAL
TABLE _probe USING fts5(x)` followed by `DROP TABLE _probe` — **write DDL** — on
what is documented as a read-only query path. Two confirmed consequences:

1. **Default (writable) path: the index file is mutated on every search.**
   `build_index` is deliberately engineered to be byte-identical / diffable across
   rebuilds (SC1), but a single `search()` changes the file's bytes. Reproduced:
   ```
   before: ('d7e414f3c37b13d5', 14266368)
   after : ('4642d6a62518cac0', 14266368)   # same size, different sha256
   FILE MUTATED BY READ-PATH search(): True
   ```
   A "read" silently breaks the frozen/diffable-artifact guarantee the phase
   designed for.

2. **Read-only or locked DB: `search()` fails with a misleading error.** On a
   read-only `index.db` (a shipped/published artifact, a read-only container
   mount, or a concurrently locked DB) the probe's `CREATE VIRTUAL TABLE` raises
   `sqlite3.OperationalError: attempt to write a readonly database`, which
   `_probe_fts5` catches and re-raises as `FTS5Unavailable`. The CLI then emits
   `missing_dependency` (exit 3) telling the operator to "install a Python whose
   bundled SQLite is built with ENABLE_FTS5" — the wrong diagnosis. Reproduced
   against a `chmod 444` copy of the real `corpus/index.db`:
   ```
   MISCLASSIFIED as FTS5Unavailable: This Python's bundled SQLite lacks the FTS5
   extension (attempt to write a readonly databas...
   ```
   `resolve()` on the same read-only DB works fine (it deliberately skips the
   probe), proving the probe is the sole cause.

The probe is also **redundant on the read path**: if FTS5 were genuinely absent,
the `chunks_fts MATCH ?` query itself would fail loud — and `resolve()` already
omits the probe by exactly this reasoning ("a DB lacking FTS5 could never have
been built", `searchindex.py:487` docstring). `_probe_fts5` was designed for the
**build** path (fail loud *before* a corpus read); reusing it on the read path
conflates "FTS5 missing" with "cannot write this DB".

**Fix:** Remove the probe from `search()` (let the `MATCH` query be the fail-loud
signal, mirroring `resolve()`), and open the DB read-only so reads can never
mutate or create the file:
```python
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
try:
    # no _probe_fts5 here — a non-FTS5 DB could never have been built, and a
    # genuinely FTS5-less host makes `chunks_fts MATCH ?` fail loud on its own.
    hits = [dict(r) for r in con.execute(sql, params).fetchall()]
    ...
```
If a pre-query FTS5 feature check is still wanted, do it *without writing* (e.g.
`SELECT 1 FROM chunks_fts LIMIT 0` or `pragma_table_list`).

### WR-02: `--family` value is interpolated into a `LIKE` pattern with no `ESCAPE` — `%` / `_` act as wildcards (filter over-matches)

> **✅ RESOLVED** (`adc57ce`): the bound `family` value escapes `\` `%` `_` and the SQL adds `ESCAPE '\'`; verified `%`/`pr_pdi` no longer leak while `pr-pdi` still matches.

**File:** `crawler/searchindex.py:467` — `sql += " AND c.relpath LIKE ? || '/%'"` with `params.append(family)`

**Issue:** `family` is parameter-bound (so this is **not** SQL injection), but it
is used as the literal prefix of a `LIKE` pattern with no `ESCAPE` clause, so
`%` and `_` in `--family` are interpreted as LIKE wildcards. The family filter
therefore over-matches instead of doing a strict prefix match. Reproduced
against the real corpus:
```
family='%'      -> hits leak across 7 distinct families (definitions, guidance,
                   legislation-irpa, legislation-irpr, medical, police-certificates, pr-pdi)
family='pr_pdi' -> 50 hits, all from 'pr-pdi'  (the '_' matched the '-')
```
A user typing `pr_pdi` silently gets `pr-pdi` results; `--family '%'` disables
the filter entirely. This is a scoping/correctness defect (not a grounding leak —
returned chunks are still real, indexed rows), latent today only because current
family directory names happen to contain no `%`/`_`.

**Fix:** Escape LIKE metacharacters and declare an escape char, or compare an
exact leading path segment:
```python
if family is not None:
    esc = family.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    sql += " AND c.relpath LIKE ? || '/%' ESCAPE '\\'"
    params.append(esc)
```

### WR-03: `search()` / `resolve()` open the DB read-write and auto-create it — library callers get a 0-byte file + a generic `OperationalError` instead of the documented behavior

> **✅ RESOLVED** (`search()` in `f12945b`, `resolve()` in `3ea0df1`): both open via `file:<db>?mode=ro` — a missing path raises an explicit `unable to open database file`, no 0-byte file is created.

**File:** `crawler/searchindex.py:447` (`search`) and `crawler/searchindex.py:507` (`resolve`) — both `sqlite3.connect(str(db))`

**Issue:** `sqlite3.connect(str(db))` opens read-write and **creates the file if
it does not exist**. The `_cmd_search` CLI handler guards this with
`db.is_file()` (`cli.py:316`), so the CLI surface is protected — but `search()`
and `resolve()` are public library functions, and the Phase-25 grounding gate is
documented to call `resolve()` directly ("the GND-01 gate hammers it",
`searchindex.py:483`). Called with a missing/typo'd path, these functions
silently create a 0-byte SQLite file and then raise `OperationalError: no such
table: chunks` — which contradicts both docstrings ("Read-only…no mutation" for
`search`; "never an exception … a miss is a normal fail-closed signal" for
`resolve`). A missing DB should be an explicit, non-mutating failure, not a
side-effecting file-create + generic error.

**Fix:** Open read-only via URI mode for both functions (also fixes WR-01's
mutation problem):
```python
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
```
`mode=ro` raises `sqlite3.OperationalError: unable to open database file` for a
missing path (explicit, no file created) and forbids any write on the read path.

### WR-04: `test_search_does_not_mutate_the_index` does not actually verify read-only behavior — it passes while `search()` writes to the DB

> **✅ RESOLVED** (`bd73615`): the test now sha256-hashes the raw DB bytes before/after `search()`; empirically confirmed to FAIL on the old write-DDL probe and PASS on the WR-01 fix.

**File:** `crawler/tests/test_searchindex.py` — `TestSearch.test_search_does_not_mutate_the_index` (the `before/after` block asserting `count(*) FROM chunks`)

**Issue:** The test asserts `count(*) FROM chunks` is unchanged across a
`search()`. The probe in WR-01 creates and drops a *separate* `_probe` table and
never touches `chunks`, so the row count is trivially unchanged — yet the file
bytes do change (WR-01, reproduced). The test's name and intent ("performs NO
mutation … read-only over the Phase-23 DB", per the class docstring) assert a
property the test does not actually check, giving false confidence and masking
WR-01. This is a test-reliability defect (in scope: tests that assert something
they don't verify).

**Fix:** Assert on the actual file, not a row count — e.g. hash the DB bytes
before/after, or run `search()` against a `chmod 0o444` copy of the DB and assert
it returns hits without raising:
```python
import hashlib
before = hashlib.sha256(self.db.read_bytes()).digest()
searchindex.search(self.db, "police certificate")
self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).digest())
```
(With the current code this assertion FAILS — which is the point: it would have
caught WR-01.)

## Info

### IN-01: `--limit` is unvalidated; a negative value disables the cap and returns all hits

> **✅ RESOLVED** (`7cea28b`): `_cmd_search` rejects `--limit < 1` as `invalid_input` (exit 2); positive limits are unchanged.

**File:** `crawler/cli.py:464` (`--limit`, `type=int`, no bound) → `crawler/searchindex.py:470` (`LIMIT ?`)

**Issue:** `--limit` is bound straight into SQLite `LIMIT ?`. SQLite treats a
negative LIMIT as "no limit", so `--limit -1` returns the entire result set,
contradicting the contract's "`--limit` caps the result count" / "max ranked
hits". Not a security or grounding issue, but a surprising, undocumented
behavior.

**Fix:** Reject (or clamp) negative limits at the CLI boundary, e.g.
`if args.limit < 0: <invalid_input, exit 2>`, or `limit = max(0, args.limit)`.

### IN-02: `_cmd_search` silently ignores a positional `query` when `--cite` is also supplied

> **✅ RESOLVED** (`4e8d17b`): supplying both `query` and `--cite` now returns `invalid_input` (exit 2) instead of silently discarding the query.

**File:** `crawler/cli.py:330` (`if args.cite is not None:` short-circuits before the query path)

**Issue:** Invoking `search "some query" --cite id` silently runs cite-resolve
mode and discards the query with no warning. Harmless to correctness, but a
mutually-exclusive-arguments situation that resolves silently rather than
erroring can mask operator mistakes.

**Fix:** Either make `query` and `--cite` a mutually exclusive argparse group, or
emit `invalid_input` when both are provided.

---

_Reviewed: 2026-06-21T06:10:05Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
