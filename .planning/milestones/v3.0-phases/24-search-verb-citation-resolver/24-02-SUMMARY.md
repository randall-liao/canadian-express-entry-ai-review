---
phase: 24-search-verb-citation-resolver
plan: 02
subsystem: api
tags: [sqlite, citation, resolver, retrieval, grounding, fail-closed, chunk_sha, integrity]

# Dependency graph
requires:
  - phase: 23-fts5-index-builder
    provides: "chunks table with UNIQUE chunk_id (relpath#ordinal) + chunk_sha staleness fingerprint, chunk_sha() helper, build_index connect/try-finally/fetchone() read mechanics"
  - phase: 24-search-verb-citation-resolver (plan 01)
    provides: "search() BM25 hit shape with the stable chunk_id round-trip that resolve() consumes"
provides:
  - "resolve(db, chunk_id) — CRUD read-by-key citation resolver: returns the EXACT verbatim chunks.text + five citation fields (+ chunk_id), fail-closed None on unknown id, fail-closed None on chunk_sha drift"
  - "TestResolve (hit returns verbatim text + fields, unknown id → None, empty id → None, search→resolve round-trip, intact-row resolves, sha-drift → None)"
affects: [24-03-search-cli-verb, 25-grounding-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read-by-key resolver: connect → ONE parameter-bound `WHERE chunk_id = ?` SELECT → fetchone() → close in finally; reads ONLY the regular chunks table (no FTS5, no _probe_fts5)"
    - "Fail-closed integrity guard: recompute chunk_sha(stored_text) and compare to stored chunk_sha; mismatch is treated exactly like a miss (return None, never raise)"
    - "Stable PII-free citation contract: exactly {chunk_id, relpath, source_url, title, section, crawl_date, text}; the internal chunk_sha is dropped from the payload"

key-files:
  created: []
  modified:
    - "crawler/searchindex.py"
    - "crawler/tests/test_searchindex.py"

key-decisions:
  - "resolve() deliberately does NOT call _probe_fts5 — it reads only the regular chunks table, so the GND-01 gate stays cheap (no FTS5 module load per call); a DB lacking FTS5 could never have been built, so that concern lives on the search() path only"
  - "A chunk_sha drift mismatch is treated IDENTICALLY to a miss (return None) rather than raised — an unknown OR stale id are both normal fail-closed 'not found' signals, not execution errors (RET-02 SC2)"
  - "The SELECT pulls chunk_sha but the returned dict drops it — chunk_sha is an internal integrity field, not part of the citation contract the grounding gate consumes (information-disclosure mitigation T-24-03b)"

patterns-established:
  - "Fail-closed read-by-key: unknown key → None and tamper/drift (recomputed fingerprint != stored) → None; never raise on either — a clean None is the gate's reject signal"
  - "Verbatim quotable span: resolve() returns stored chunks.text byte-for-byte (the grounding-grade span), NEVER a snippet()/highlight (snippet is search-display only — P5)"

requirements-completed: [RET-02]

# Metrics
duration: ~8min
completed: 2026-06-21
---

# Phase 24 Plan 02: Citation Resolver (resolve()) Summary

**Read-only `resolve(db, chunk_id)` that resolves a stable citation id back to its EXACT verbatim `chunks.text` (the quotable span the grounding gate grounds on) plus the five PII-free citation fields — failing closed to `None` (never raising) for an unknown id AND for a content-drifted row whose stored text no longer hashes to its `chunk_sha`.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-21T05:44Z
- **Completed:** 2026-06-21T05:52Z
- **Tasks:** 2 (both TDD: RED → GREEN, no REFACTOR needed)
- **Files modified:** 2

## Accomplishments
- `resolve(db, chunk_id) -> dict | None` — one parameter-bound `WHERE chunk_id = ?` lookup on the UNIQUE `chunk_id` index (O(log n)); returns the stable, PII-free citation dict (`chunk_id, relpath, source_url, title, section, crawl_date, text`) with `text` returned VERBATIM (the grounding-grade quotable span — never a `snippet()`). Reads ONLY the regular `chunks` table; never touches FTS5.
- Fail-closed MISS: an unknown id (`no-such/doc.md#999`) and an empty id (`""`) both return `None` — never an exception (RET-02 SC2).
- Fail-closed DRIFT: `resolve()` recomputes `chunk_sha(stored_text)` and compares it to the row's stored `chunk_sha`; on mismatch (tampered / corrupted / re-crawled-then-edited row) it returns `None` — the exact staleness/tamper guard the Phase-25 grounding gate (GND-01) relies on. The drift case returns `None`, NOT the tampered text and NOT an exception.
- `search()` → `resolve()` round-trip proven: a `chunk_id` returned by `search()` resolves back to a citation dict (the handshake Plan-03's real-corpus test exercises end-to-end).
- Read-only: `resolve()` adds NO write statement (`build_index` remains the sole writer); the chunk count is stable across `resolve()` calls.

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 (RED): TestResolve hit + fail-closed miss** — `b696d91` (test)
2. **Task 1 (GREEN): `resolve()` exact-chunk citation lookup** — `ea788bf` (feat)
3. **Task 2 (RED): TestResolve sha-drift fail-closed case** — `ee7f690` (test)
4. **Task 2 (GREEN): `chunk_sha` staleness fail-closed guard** — `38ef76f` (feat)

## Files Created/Modified
- `crawler/searchindex.py` — added `resolve(db, chunk_id)`: connect → parameter-bound `WHERE chunk_id = ?` SELECT → `fetchone()` → close in `finally`; fail-closed on miss + `chunk_sha` drift; returns the verbatim citation dict (+65 lines). No write statement added.
- `crawler/tests/test_searchindex.py` — added `class TestResolve(_IndexCase)` (8 cases: exact citation dict, verbatim non-snippet text, citation fields match the planted row, unknown id → None, empty id → None, search→resolve round-trip, intact-row resolves, sha-drift → None) (+95 lines).

## Decisions Made
- **No `_probe_fts5` in `resolve()`** — it reads only the regular `chunks` table, so the GND-01 resolver stays cheap (the Phase-25 gate hammers it). The missing-FTS5 concern lives entirely on the `search()` path (a DB lacking FTS5 could never have been built).
- **Drift mismatch == miss** — a stale id and an unknown id both yield `None` (fail-closed "not found"), never a raise. A miss/stale id is a normal fail-closed signal, not an execution error (anti-pattern: treating a `--cite` miss / sha-drift as an exception).
- **`chunk_sha` selected but not returned** — the SELECT pulls `chunk_sha` for the integrity comparison, but the returned dict drops it (internal integrity field, not part of the PII-free citation contract the gate consumes — T-24-03b).

## Deviations from Plan

None - plan executed exactly as written. Both TDD tasks went RED → GREEN cleanly; no REFACTOR needed; no bugs, missing functionality, or blocking issues encountered.

**Total deviations:** 0
**Impact on plan:** None — implemented exactly as specified, all grep/anti-pattern gates and must_haves hold.

## Issues Encountered
None — both TDD cycles produced the expected RED (Task 1: `AttributeError: module 'crawler.searchindex' has no attribute 'resolve'`; Task 2: drift test returned the tampered dict instead of None) and went GREEN on first implementation.

(Environment note: the pyenv `python` shim is CRLF-broken in this WSL env; all tests were run via `.venv/bin/python -m pytest ...` per the project's poetry env at `./.venv`, Python 3.10.12.)

## User Setup Required
None — stdlib only (`sqlite3` + the existing `chunk_sha`/`hashlib`). No new runtime dependency, no Package Legitimacy Gate, no external service configuration required.

## Next Phase Readiness
- **Plan 24-03 (search CLI verb)** can wire a `--cite <chunk_id>` path directly to `resolve(db, chunk_id)` and map a `None` return to a fail-closed not-found / `INVALID_INPUT` outcome through the `contract` envelope (per the phase's error taxonomy). The return shape (`{chunk_id, relpath, source_url, title, section, crawl_date, text}`) is stable.
- **Phase 25 (grounding gate, GND-01)** consumes `resolve()` as its citation-verification primitive: an ungrounded/stale citation id fails closed to `None`, which is exactly the reject signal the gate needs (RET-02 SC2 → GND-01).
- No blockers.

## Known Stubs
None — `resolve()` is fully wired against the real `chunks` table; no placeholder values, empty returns, or mock data sources introduced. The single `UPDATE` in the suite is test-only tampering to exercise the drift guard; `resolve()`/`search()` themselves never write.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_searchindex.py::TestResolve -q` → **8 passed** (hit/verbatim/fields, unknown→None, empty→None, round-trip, intact-row, sha-drift→None).
- Full module suite: `.venv/bin/python -m pytest crawler/tests/test_searchindex.py -q` → **52 passed** (Phase-23 + Plan-01 + Plan-02 classes, none broken; baseline was 50 after Task 1, 44 before this plan).
- Cross-module: `crawler/tests/test_cli.py` → **6 passed** (no regression).
- Anti-pattern / read-only grep gates (on `crawler/searchindex.py`):
  - `grep -c "snippet(" ` → **5** (unchanged vs Plan 01 — resolve returns verbatim text, never a snippet; P5).
  - `grep -cE "INSERT|DROP|UPDATE|DELETE|commit" ` → **9** (unchanged vs Plan 01 — resolve adds no write statement; the test's UPDATE lives in the test file, not the module).
  - `grep -c "WHERE chunk_id = ?" ` → **2** (>= 1 — the parameter-bound indexed lookup + its docstring reference).
  - `grep -c "chunk_sha(" ` → **3** (>= 3 — the helper def + the build_index call + the resolve() drift recompute).
- Empirical in-process smoke (auto-cleaned tempdir, synthetic 4-doc corpus): keys == the exact contract; `text` byte-for-byte equals stored text with no `…`/`⟦`/`⟧`; `source_url` verbatim (`https://www.canada.ca/en/tiny.html?wbdisable=true#frag`); `chunk_sha` not in the dict; unknown id → None; empty id → None; search→resolve round-trips; tampered row → None; chunk count stable across resolve() calls (read-only).

### must_haves (frontmatter truths) — all hold in code
1. ✅ `resolve(db, chunk_id)` returns the EXACT verbatim `chunks.text` + the five citation fields + chunk_id for a known id [RET-02 SC2].
2. ✅ An unknown `chunk_id` returns None (fail-closed) — never raises [RET-02 SC2].
3. ✅ A content-drifted row (stored `text` no longer hashes to its stored `chunk_sha`) resolves to None — the fail-closed staleness/tamper guard GND-01 relies on [RET-02 SC2].
4. ✅ `resolve()` is read-only and reads only the regular `chunks` table (no FTS5), an O(log n) lookup on the UNIQUE `chunk_id` index [RET-02 SC2].

---
*Phase: 24-search-verb-citation-resolver*
*Completed: 2026-06-21*

## Self-Check: PASSED

- Files: `crawler/searchindex.py` (contains `def resolve`), `crawler/tests/test_searchindex.py` (contains `class TestResolve`), `.planning/phases/24-search-verb-citation-resolver/24-02-SUMMARY.md` — all FOUND.
- Commits: `b696d91`, `ea788bf`, `ee7f690`, `38ef76f` — all FOUND in git history.
