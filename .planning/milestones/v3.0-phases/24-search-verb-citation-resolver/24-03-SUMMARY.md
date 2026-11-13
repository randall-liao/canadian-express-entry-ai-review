---
phase: 24-search-verb-citation-resolver
plan: 03
subsystem: api
tags: [cli, argparse, json-contract, search, citation, bm25, fts5, fail-closed]

# Dependency graph
requires:
  - phase: 24-search-verb-citation-resolver (plan 01)
    provides: "search(db, query, limit, family) read-only BM25 query + EmptyQuery / FTS5Unavailable sentinels"
  - phase: 24-search-verb-citation-resolver (plan 02)
    provides: "resolve(db, chunk_id) fail-closed citation resolver (verbatim chunk + None on unknown/sha-drift)"
  - phase: 23-fts5-index-builder
    provides: "the index verb dispatcher + contract envelope/exit-code precedent (_cmd_index, CONTRACT.md ### index)"
provides:
  - "_cmd_search CLI handler — thin dispatcher: validate --db is a file, lazy-import searchindex, dispatch to search() (ranked) or resolve() (--cite), map EmptyQuery→invalid_input (exit 2) / FTS5Unavailable→missing_dependency (exit 3), emit exactly one CONTRACT envelope"
  - "p_search subparser (optional positional query + --db/--cite/--limit/--family) registered in the search metavar"
  - "additive CONTRACT.md ### search subsection (ranked-search + --cite resolve shapes) + contract.py docstring command list — SCHEMA_VERSION 1.0 + five envelope keys UNCHANGED"
  - "TestSearchCli (6 cases) + TestRealCorpus search→resolve round-trip over the real 742-doc index"
affects: [25-grounding-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin CLI dispatcher: _cmd_search validates inputs + routes to searchindex compute, no compute in cli.py (sqlite3 never imported at cli-import time — lazy import inside the handler)"
    - "Fail-closed-through-the-contract: a --cite miss/stale id is ok:true / result.found=false / chunk:null / exit 0 (a miss is NOT an execution error — mirrors the report verdict-fail rule)"
    - "Additive-only contract change: new command value + new result shapes; SCHEMA_VERSION + five envelope keys + EXIT_* constants untouched so existing consumers are unaffected"

key-files:
  created: []
  modified:
    - "crawler/cli.py"
    - "crawler/contract.py"
    - "crawler/CONTRACT.md"
    - "crawler/tests/test_searchindex.py"

key-decisions:
  - "The --db is-file check runs FIRST for both modes (ranked + --cite); a non-file db is invalid_input/exit 2 before any compute (mirrors _cmd_index's is_dir guard)"
  - "argparse makes the positional query optional (nargs='?') so --cite can omit it; the handler explicitly requires a query OR --cite (invalid_input/exit 2 when both are absent)"
  - "The --cite path has NO FTS5Unavailable catch — resolve() never raises on a miss and needs no FTS5 (no dead catch); only the ranked-search path maps FTS5Unavailable→missing_dependency"
  - "Doc change is purely additive: a new ### search subsection + search added to the existing command/error-taxonomy rows (no NEW error rows / exit codes); SCHEMA_VERSION stays 1.0"

patterns-established:
  - "CLI verb shape over a read-only compute primitive: copy _cmd_index's --json validate-then-emit shell, swap the body to dispatch to the searchindex read functions, keep ALL compute out of cli.py"
  - "Contract-level fail-closed: surface resolve()'s None as result.found=false/chunk:null at ok:true/exit 0 so the grounding gate (GND-01) reads found/chunk to reject ungrounded or stale citations"

requirements-completed: [RET-02]

# Metrics
duration: ~7min
completed: 2026-06-21
---

# Phase 24 Plan 03: Search CLI Verb + `--cite` Resolver Summary

**Wired the Plan-01 `search()` + Plan-02 `resolve()` read-side compute into the `corpus-crawler` CLI as a thin `search` verb with a `--cite <id>` resolve mode, documented it additively (no contract break), and proved the whole stack end-to-end over the real 742-doc index — completing RET-02 (SC1 the `--json search` envelope, SC2 the `--cite` resolver, SC3 empty-query→INVALID_INPUT at the boundary, SC4 the additive-contract promise).**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-21T05:53Z
- **Completed:** 2026-06-21T06:00Z
- **Tasks:** 3 (all `type="auto"`)
- **Files modified:** 4

## Accomplishments
- `_cmd_search(args)` — a THIN dispatcher mirroring `_cmd_index`: validates `--db` is a file (else `invalid_input`/exit 2), LAZY-imports `searchindex` (so importing `crawler.cli` never drags `sqlite3` — verified), then dispatches:
  - **ranked search** (`search "<q>"`) → `searchindex.search(db, query, limit, family)`, emitting one `ok:true` envelope (`command="search"`, `schema_version "1.0"`) carrying the `{query, db, count, hits}` payload; the human `"<n> hits for <q>"` summary goes to **stderr only**.
  - **`--cite` resolve** (`search --cite <id>`) → `searchindex.resolve(db, id)`, emitting `{found, chunk_id, db, chunk}`; a hit is `found:true` with the verbatim chunk, a miss/stale id is **fail-closed** (`found:false`, `chunk:null`, exit 0 — not an execution error).
- Error taxonomy mapped at the boundary: `EmptyQuery` → `invalid_input` exit 2 (an empty / all-punct query never reaches an empty `MATCH`); `FTS5Unavailable` → `missing_dependency` exit 3 (ranked-search path only); a non-file `--db` → `invalid_input` exit 2. Unexpected exceptions still fall through to `cli.main`'s `--json` catch-all (`internal_error`/exit 4) — no re-wrap.
- `p_search` subparser registered (optional positional `query` + `--db`/`--cite`/`--limit`/`--family`), added to the subparsers `metavar` and the module-docstring subcommand map.
- **Additive** contract docs: a new `### search` subsection in `CONTRACT.md` documenting both the ranked-search (`query/db/count/hits[]` with each hit's `chunk_id` + five citation fields + `snippet` + `score`) and `--cite` resolve (`found/chunk_id/db/chunk`, fail-closed on miss/stale) shapes 1:1 with the code; `search` added to the `command` key + the existing error-taxonomy rows; `contract.py` docstrings list `search`. `SCHEMA_VERSION` stays `"1.0"`, the five envelope keys + `EXIT_*` constants are unchanged.
- Real 742-doc round-trip proven: a known-term `search` returns ≥1 ranked hit and a returned `chunk_id` resolves through `--cite`/`resolve()` back to its exact chunk (tempdir-only db — nothing staged under git-ignored `corpus/`).

## Task Commits

Each task was committed atomically:

1. **Task 1 — `_cmd_search` handler + `p_search` subparser** — `8d63240` (feat)
2. **Task 2 — additive `CONTRACT.md ### search` + `contract.py` docstrings** — `e422813` (docs)
3. **Task 3 — `TestSearchCli` + real-corpus search↔cite round-trip** — `29724a2` (test)

## Files Created/Modified
- `crawler/cli.py` — added `_cmd_search` (thin dispatcher: validate → lazy import → search/resolve dispatch → one envelope), the `p_search` subparser, the `search` metavar entry, and the module-docstring subcommand map line. No compute logic added.
- `crawler/CONTRACT.md` — added the `### search` subsection (ranked + `--cite` shapes), added `search` to the `command` key and to the `missing_dependency`/`invalid_input` taxonomy rows. Additive; no new rows / exit codes.
- `crawler/contract.py` — appended `search` to the `command` enumeration in the module docstring + `envelope()` docstring. `SCHEMA_VERSION`, the five keys, and the `EXIT_*` constants are unchanged.
- `crawler/tests/test_searchindex.py` — added `class TestSearchCli(_IndexCase)` (6 cases) + `TestRealCorpus.test_real_corpus_search_resolve_round_trip` (the real-index handshake).

## Decisions Made
- **`--db` is-file check first, for both modes** — a non-file db is `invalid_input`/exit 2 before any compute (mirrors `_cmd_index`'s `is_dir` guard).
- **Optional positional query, explicit require** — argparse uses `nargs="?"` so `--cite` can omit the query; the handler then explicitly requires a query OR `--cite`, emitting `invalid_input`/exit 2 ("a query or --cite is required") when both are absent.
- **No FTS5 catch on the `--cite` path** — `resolve()` reads only the regular `chunks` table and never raises on a miss/stale id, so adding an `FTS5Unavailable` catch there would be dead code; only the ranked-search path maps `FTS5Unavailable`→`missing_dependency`.
- **Purely additive contract change** — a new `### search` subsection + `search` woven into the existing `command`/error-taxonomy rows; `SCHEMA_VERSION` stays `"1.0"` and no new error rows / exit codes were introduced (T-24-06 backward-compat mitigation).

## Deviations from Plan

None - plan executed exactly as written. All three `type="auto"` tasks landed cleanly; no bugs, missing functionality, or blocking issues encountered. No new runtime dependency (stdlib only), so the Package Legitimacy Gate is N/A.

**Total deviations:** 0
**Impact on plan:** None — implemented exactly as specified; all grep gates, the threat-register mitigations, and the must_haves hold.

## Issues Encountered
None. (Environment note: the pyenv `python` shim is CRLF-broken in this WSL env; all CLI smoke + tests were run via `.venv/bin/python -m ...` per the project's poetry env at `./.venv`, Python 3.10.12.)

## User Setup Required
None — stdlib only (`argparse`/`contextlib`/`pathlib`, all already imported; the lazy `sqlite3` lives in `searchindex`). No external service configuration required.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_searchindex.py -q` → **59 passed** (52 from Plans 01/02 + 6 `TestSearchCli` + 1 `TestRealCorpus` round-trip; the real-corpus round-trip RAN — not skipped — since `corpus/` is present).
- Regression: `.venv/bin/python -m pytest crawler/tests/test_cli.py crawler/tests/test_json_contract.py -q` → **32 passed, 1 skipped** (pre-existing skip; the additive change broke nothing).
- Real-corpus CLI smoke (`--db corpus/index.db`):
  - `--json search "police certificate which countries" --limit 3` → one `ok:true` / `command:"search"` envelope; 3 BM25 hits, each with `chunk_id` + five citation fields + `snippet` + negative ascending `score`.
  - `--json search --cite "police-certificates/eritrea.md#005"` → `ok:true`, `result.found=true`, `chunk.text` 303-char verbatim span.
  - `--json search --cite "no-such/doc.md#999"` → `ok:true`, `found:false`, `chunk:null`, **exit 0** (fail-closed).
  - `--json search "()!:"` → `ok:false`, `invalid_input`, **exit 2** (no empty MATCH).
  - `--json search "x" --db /tmp/nope-24-03.db` → `invalid_input`, **exit 2**.
  - `--json search --db corpus/index.db` (no query, no --cite) → `invalid_input`, **exit 2** ("a query or --cite is required").
- Grep gates: `grep -c 'envelope("search"' crawler/cli.py` → ≥1; `grep -c 'SCHEMA_VERSION = "1.0"' crawler/contract.py` → **1**; `grep -q '### \`search\`' crawler/CONTRACT.md` → present.
- Thin dispatcher: `import crawler.cli` does NOT import `sqlite3` (asserted) — all compute stays in `searchindex`.

### must_haves (frontmatter truths) — all hold in code
1. ✅ `--json search "<q>"` emits exactly one CONTRACT envelope (`command=search`, `ok=true`, `schema_version "1.0"`) with BM25 hits; human summary to stderr only [RET-02 SC1/SC4].
2. ✅ `--json search --cite <id>` → hit `found:true`/exact chunk; unknown/stale → `found:false` fail-closed, exit 0 [RET-02 SC2].
3. ✅ Empty / all-punct query → `invalid_input` exit 2; no-FTS5 host → `missing_dependency` exit 3; non-file `--db` → `invalid_input` exit 2 [RET-02 SC3].
4. ✅ `CONTRACT.md` + `contract.py` document `search` additively; five envelope keys + `schema_version "1.0"` unchanged [RET-02 SC4].
5. ✅ The real 742-doc index round-trips: a known-term search returns ≥1 resolvable hit; a returned `chunk_id` resolves via `--cite` to its exact chunk (skipUnless guard, tempdir-only writes) [RET-02 SC1/SC2].

## Threat Surface

All STRIDE-register mitigations from the plan hold: stdout purity (T-24-05 — `TestSearchCli` asserts one JSON line + no `{` on stderr), additive-contract backward-compat (T-24-06 — `SCHEMA_VERSION "1.0"` grep gate), bounded results (T-24-02b — `--limit` forwarded + empty query rejected pre-MATCH), `--cite` fail-closed (T-24-04b), no-FTS5 loud-fail (T-24-08b), PII-free output (T-24-03c — index built from `corpus/` only). No new security-relevant surface beyond the plan's threat model was introduced — this plan only forwards the already-hardened (Plan 01 `_to_match` + parameter-bound MATCH) read-only path.

## Next Phase Readiness
- **Phase 25 (grounding gate, GND-01/GND-02)** can now drive the full retrieval contract from a CLI-agnostic agent: `--json search` for ranked citable hits and `--json search --cite <id>` for the fail-closed resolve the gate uses to reject ungrounded or stale citations. The `result.found`/`result.chunk` shape is the stable signal.
- No blockers.

## Known Stubs
None — `_cmd_search` is fully wired to the real `search()`/`resolve()` compute; no placeholder values, empty returns, or mock data sources introduced.

---
*Phase: 24-search-verb-citation-resolver*
*Completed: 2026-06-21*

## Self-Check: PASSED

- Files: `crawler/cli.py` (contains `def _cmd_search`), `crawler/contract.py`, `crawler/CONTRACT.md` (contains `### search`), `crawler/tests/test_searchindex.py` (contains `class TestSearchCli`), `.planning/phases/24-search-verb-citation-resolver/24-03-SUMMARY.md` — all FOUND.
- Commits: `8d63240`, `e422813`, `29724a2` — all FOUND in git history.
