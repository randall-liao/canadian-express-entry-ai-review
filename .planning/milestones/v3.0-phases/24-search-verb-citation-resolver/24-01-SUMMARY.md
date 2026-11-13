---
phase: 24-search-verb-citation-resolver
plan: 01
subsystem: api
tags: [sqlite, fts5, bm25, search, query-escaping, citation, retrieval]

# Dependency graph
requires:
  - phase: 23-fts5-index-builder
    provides: "chunks + chunks_fts external-content FTS5 index, _probe_fts5 fail-loud guard, chunk_id=relpath#ordinal content coordinates, build_index connect/try-finally shell"
provides:
  - "_to_match() adversarial-query FTS5 escaper (re.findall(\\w+) + per-term double-quote, implicit-AND literals)"
  - "search(db, query, limit, family) — read-only BM25 query returning the citable {query, db, count, hits} envelope"
  - "EmptyQuery(ValueError) sentinel for empty / all-punctuation queries (CLI maps to INVALID_INPUT)"
  - "TestToMatch + TestSearch covering adversarial escaping, BM25 order, snippet highlight, chunk_id round-trip, family filter, read-only"
affects: [24-02-citation-resolver, 24-03-search-cli-verb, 25-grounding-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Untrusted query → _to_match() → parameter-bound `chunks_fts MATCH ?` (raw query never reaches SQLite)"
    - "bm25() ascending = best-first; raw negative score passed through verbatim (never negated/re-sorted)"
    - "snippet(chunks_fts, 0, ...) for the human preview; exact span is quoted from chunks.text (never offsets())"
    - "search() reuses build_index's connect/try-finally + _probe_fts5 fail-loud shell; SELECT only"

key-files:
  created: []
  modified:
    - "crawler/searchindex.py"
    - "crawler/tests/test_searchindex.py"

key-decisions:
  - "_to_match() returns None for empty/all-punct (stays pure & unit-testable); search() raises EmptyQuery — separation keeps the escaper side-effect-free"
  - "--family is a parameter-bound `c.relpath LIKE ? || '/%'` post-filter (not a Python split), keeping it injection-safe and in the single SQL pass"
  - "Reused the existing _probe_fts5 guard rather than writing a second probe (single fail-loud surface shared with build_index)"

patterns-established:
  - "Adversarial-query safety: tokenize on \\w+ and re-quote each term so parens/colons/apostrophes/bare OR-AND-NEAR are LITERAL terms — no fts5 syntax error, no operator/column-filter injection"
  - "Read-only verb shape: copy build_index's connect/try-finally/close + _probe_fts5, swap the body to a SELECT-only query, add NO write statement"

requirements-completed: [RET-02]

# Metrics
duration: ~10min
completed: 2026-06-21
---

# Phase 24 Plan 01: Search Verb Read-Side (escaper + BM25 query) Summary

**Adversarial-query-safe `_to_match()` FTS5 escaper plus a read-only `search()` BM25 query that returns BM25-ranked, citable `{query, db, count, hits}` hits (stable `relpath#NNN` chunk_id + five citation fields + ⟦⟧ snippet highlight) over the already-built Phase-23 index.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-21T05:32:02Z
- **Completed:** 2026-06-21T05:41:40Z
- **Tasks:** 2 (both TDD: RED → GREEN)
- **Files modified:** 2

## Accomplishments
- `_to_match(q)` — the security core of RET-02 SC3: tokenizes via `re.findall(r"\w+")` and double-quotes every term, so `R30(3)`, `body:funds`, `women's`, and bare `OR/AND/NEAR` become LITERAL terms; empty / all-punctuation input returns `None`. No new import (stdlib `re`, already present).
- `search(db, query, limit=10, family=None)` — read-only BM25 query returning the citable envelope; each hit carries the stable `chunk_id = relpath#NNN`, the five citation fields (`source_url`, `relpath`, `title`, `section`, `crawl_date`), a non-empty `snippet()` highlight, and the raw negative `bm25` score, sorted best-first (score ascending).
- `EmptyQuery(ValueError)` sentinel added next to `FTS5Unavailable`; `search()` raises it for empty / all-punct queries instead of running an empty `MATCH`.
- Adversarial safety proven: `R30(3)`, `police OR certificates`, `body:funds`, and an apostrophe query all run **without** an fts5 syntax error or operator/column-filter injection.
- `--family` restricts hits to a `relpath` prefix via a parameter-bound `LIKE ? || '/%'`; `search()` performs SELECT only (chunk count unchanged before/after).

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 (RED): TestToMatch** — `5c17403` (test)
2. **Task 1 (GREEN): `_to_match()` + `EmptyQuery`** — `bf9f98c` (feat)
3. **Task 2 (RED): TestSearch** — `903c4c6` (test)
4. **Task 2 (GREEN): read-only BM25 `search()`** — `f89f4e4` (feat)

_Note: the `offsets(`-in-comment gate fix (see Deviations) was folded into the Task 2 GREEN commit `f89f4e4` before commit._

## Files Created/Modified
- `crawler/searchindex.py` — added `EmptyQuery`, the pure `_to_match()` escaper, and the read-only `search()` BM25 query (+91 lines). No write statement added; `build_index` remains the sole writer.
- `crawler/tests/test_searchindex.py` — added `TestToMatch` (6 pure-function adversarial cases) and `TestSearch` (10 cases: citable envelope, BM25-ascending negative scores, eight hit fields, snippet highlight, chunk_id round-trip, adversarial no-raise, EmptyQuery, family filter, limit, read-only) (+140 lines).

## Decisions Made
- Kept `_to_match()` pure (returns `None`) and moved the raise into `search()` (`EmptyQuery`) so the escaper stays a deterministic, side-effect-free unit (mirrors the existing `chunk_sha` helper shape).
- Implemented `--family` as a parameter-bound `c.relpath LIKE ? || '/%'` clause in the single SQL pass rather than a Python post-filter — keeps it injection-safe and avoids a second traversal.
- Reused the existing `_probe_fts5(con)` guard (the same fail-loud surface `build_index` uses) instead of a second probe; Plan 03's CLI maps `FTS5Unavailable` → missing_dependency / exit 3.
- Snippet markers use the `\u27e6` / `\u27e7` / `\u2026` unicode escapes in the SQL (matching the existing `\u203a` source style); SQLite returns the literal ⟦ / ⟧ / … characters the tests assert on.

## Verification

- `poetry run python -m pytest crawler/tests/test_searchindex.py -q` → **44 passed** (Phase-23 classes unaffected; `.venv/bin/python` used because the pyenv `python` shim is CRLF-broken in this env).
- `crawler/tests/test_cli.py` → 6 passed (no cross-module regression).
- Anti-pattern grep gates:
  - `grep -c "offsets(" crawler/searchindex.py` → **0** (no FTS3/4 offsets — P5).
  - `grep -c "MATCH ?" crawler/searchindex.py` → **2** (≥1, parameter-bound MATCH).
  - `grep -cE "INSERT|DROP|UPDATE|DELETE|commit" crawler/searchindex.py` → **9** (unchanged from Phase 23 — `search` adds NO write statement).
  - `grep -cE "^import|^from" crawler/searchindex.py` → **7** (unchanged — no new import).
- Empirical adversarial smoke (in-process, auto-cleaned tempdir): `_to_match("R30(3)") == '"R30" "3"'`, `OR` quoted as a literal, colon/apostrophe dropped, empty/all-punct → `None`; `search()` envelope has `count==len(hits)`, top hit `legislation-irpr/longpara.md#000` with a `⟦police⟧ ⟦certificates⟧` snippet, scores ascending and all negative; adversarial queries return without raising; `EmptyQuery` raised on `""`/`"()!:"`; chunk count unchanged (read-only); `family="pr-pdi"` hits all `pr-pdi/`-prefixed.

### must_haves (frontmatter truths) — all hold in code
1. ✅ Adversarial-safe `_to_match()` (per-term quoted `\w+` literals; empty/all-punct → None).
2. ✅ `search()` parameter-bound `chunks_fts MATCH ?` ordered by `bm25()` ascending with parameter-bound `LIMIT ?`; adversarial queries never raise / never inject a column filter.
3. ✅ Each hit = stable `chunk_id` + five citation fields + non-empty `snippet()` highlight + raw negative `bm25` score, best-first.
4. ✅ `search()` is read-only (SELECT only); empty/all-punct raises `EmptyQuery`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Anti-pattern grep gate tripped by a literal `offsets(` in a code comment**
- **Found during:** Task 2 (search() GREEN)
- **Issue:** A clarifying comment read "use snippet() (never offsets(), which FTS5 lacks — P5)". The literal `offsets(` substring made `grep -c "offsets(" crawler/searchindex.py` return `1`, violating the plan's required `== 0` read-only/anti-pattern gate (even though the code uses `snippet()`, not `offsets()`).
- **Fix:** Reworded the comment to "never the FTS3/4 offsets span function, which FTS5 lacks — P5" (drops the `offsets(` token) while preserving the intent.
- **Files modified:** `crawler/searchindex.py`
- **Verification:** `grep -c "offsets(" crawler/searchindex.py` → `0`; full suite still 44 passed.
- **Committed in:** `f89f4e4` (folded into the Task 2 GREEN commit before committing).

---

**Total deviations:** 1 auto-fixed (Rule 1 — gate-tripping comment).
**Impact on plan:** Cosmetic comment-only change to satisfy the explicit anti-pattern grep gate; no behavior change, no scope creep.

## Issues Encountered
None — both TDD tasks went RED → GREEN cleanly. (Environment note: `read_bash`/`stop_bash` were unavailable, and the full `crawler/tests` run is slow; verification used the module-scoped `test_searchindex.py` + `test_cli.py` suites, which fully exercise the changed surface.)

## User Setup Required
None — stdlib only (`re` + `sqlite3`, both already imported). No external service configuration required.

## Next Phase Readiness
- **Plan 24-02 (citation resolver)** can build on `search()`'s hit shape and the stable `chunk_id = relpath#NNN` round-trip (verified to resolve in `chunks`). `EmptyQuery` + `FTS5Unavailable` are the two sentinels Plan 03's CLI will map to `INVALID_INPUT` / `missing_dependency`.
- **Plan 24-03 (search CLI verb)** forwards directly to `search(db, query, limit, family)` and emits `{query, db, count, hits}` through the existing `contract.envelope`. Real-corpus adversarial/smoke coverage is deferred to Plan 03 per the plan (synthetic 4-doc corpus only here).
- No blockers.

## Known Stubs
None — `_to_match()` and `search()` are fully wired; no placeholder values, empty returns, or mock data sources introduced.

---
*Phase: 24-search-verb-citation-resolver*
*Completed: 2026-06-21*

## Self-Check: PASSED

- Files: `crawler/searchindex.py`, `crawler/tests/test_searchindex.py`, `.planning/phases/24-search-verb-citation-resolver/24-01-SUMMARY.md` — all FOUND.
- Commits: `5c17403`, `bf9f98c`, `903c4c6`, `f89f4e4` — all FOUND in git history.
