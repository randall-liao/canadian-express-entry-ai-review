---
phase: 23-fts5-index-builder
plan: 03
subsystem: api
tags: [cli, contract, fts5, sqlite, retrieval, json-envelope, stdlib]

# Dependency graph
requires:
  - phase: 23-02-fts5-index-builder
    provides: "searchindex.build_index(corpus, db) -> result dict + FTS5Unavailable (the compute layer the index verb forwards to)"
  - phase: 23-01-fts5-index-builder
    provides: "searchindex._probe_fts5 / FTS5Unavailable / MAX_CHUNK_CHARS (fail-loud + bound constants)"
  - phase: 14-cli-packaging
    provides: "crawler.cli thin dispatcher + crawler.contract five-key envelope/emit + EXIT_* taxonomy (mirrored by _cmd_index)"
provides:
  - "`corpus-crawler --json index <corpus> --db <db>` verb: one CONTRACT envelope (command='index'), exit 0/2/3"
  - "_cmd_index thin dispatcher (lazy searchindex import, dir guard, FTS5 fail-loud → missing_dependency/exit 3)"
  - "Additive contract docs: CONTRACT.md ### index result-fields + contract.py command enumeration (schema_version still '1.0')"
  - "TestIndexCli (envelope/invalid_input/stdout-purity) + TestRealCorpus (skipUnless 742-doc smoke, tempdir DB)"
affects: [24-search-verb, 25-grounding-gate]

# Tech tracking
tech-stack:
  added: []  # stdlib only — zero new runtime dependency; reuses existing argparse/contract/searchindex
  patterns:
    - "Thin-dispatcher verb: validate inputs + lazy-import compute module + emit exactly one contract envelope; no compute in cli.py"
    - "Additive contract evolution: new `command` value + new `result` shape only; five envelope keys + EXIT_* + SCHEMA_VERSION '1.0' frozen"
    - "Build-command exit mapping: bad dir → invalid_input/2, host without FTS5 → missing_dependency/3, success → 0"
    - "stdout-purity guard: --json emits one JSON object to stdout; the human docs/chunks summary goes to stderr only"

key-files:
  created: []
  modified:
    - crawler/cli.py
    - crawler/contract.py
    - crawler/CONTRACT.md
    - crawler/tests/test_searchindex.py

key-decisions:
  - "_cmd_index forwards to searchindex.build_index in BOTH modes (searchindex IS the compute layer — there is no module main() to forward to, unlike crawl/completeness/report)"
  - "Only FTS5Unavailable is caught in the handler; every other exception propagates to cli.main's --json catch-all (internal_error/exit 4) — no re-wrapping"
  - "All command enumerations (CONTRACT.md envelope table, contract.py module + envelope() docstrings) were extended to include `index` to keep the docs 1:1 with the code, beyond the single ### index subsection the task named"
  - "Manual real-corpus smoke wrote the git-ignored default corpus/index.db then removed it; all tests write the DB inside a tempdir, never under corpus/"

patterns-established:
  - "Index verb: `_cmd_index` is the template for future read/build verbs (search, Phase 24) — lazy import + envelope('<verb>', result=...) + EXIT_* mapping"
  - "Real-corpus skipUnless smoke driven through build_index into a TemporaryDirectory db proves the full stack (742 docs / chunks>docs / bounded) without polluting corpus/"

requirements-completed: [RET-01]  # Plan 03 lands SC1 (documented `index` build command) + SC4 (FTS5 fail-loud at the boundary, non-zero exit) + the additive-contract promise

# Metrics
duration: 12min
completed: 2026-06-20
---

# Phase 23 Plan 03: `index` CLI Verb + Additive FTS5 Contract Summary

**Wires the FTS5 index builder into `corpus-crawler` as a thin `index` verb — `corpus-crawler --json index corpus/ --db corpus/index.db` emits exactly one `ok:true command:"index"` envelope (742 docs / 7935 chunks) — and documents it additively (new `command` + `result` shape, schema_version still `1.0`), proven end-to-end over the real 742-doc corpus behind a `skipUnless` guard. This completes RET-01 (the retrieval index is now a first-class, contracted CLI command).**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-20T22:56:00-04:00 (session start)
- **Completed:** 2026-06-20T23:08:00-04:00 (last task commit)
- **Tasks:** 3 of 3 completed
- **Files modified:** 4 (all extended; none created)

## Accomplishments
- Added **`_cmd_index`** to `crawler/cli.py` — a THIN dispatcher (no compute) that validates `corpus_dir` is a directory, **lazy-imports** `searchindex` (so `import crawler.cli` never drags `sqlite3`/index setup), forwards to `searchindex.build_index`, and emits exactly one CONTRACT envelope. It maps a host SQLite without FTS5 (`FTS5Unavailable`) to a loud **`missing_dependency`/exit 3** and a bad corpus dir to **`invalid_input`/exit 2**; the human docs/chunks summary goes to **stderr only** (stdout stays pure JSON). Registered the `p_index` subparser (`--db` default `corpus/index.db`), and added `index` to the subparsers metavar + the module docstring map.
- Made the **additive (non-breaking) contract change**: a new `### index` result-fields subsection in `CONTRACT.md` (db/corpus/docs/chunks/min_text_len/max_text_len/tokenizer), the build-command exit codes + FTS5-absent → `missing_dependency` note, and `index` appended to every command enumeration (envelope table, `contract.py` module + `envelope()` docstrings). The **five envelope keys, all `EXIT_*` constants, and `SCHEMA_VERSION "1.0"` are unchanged**.
- Landed **5 new tests** in `test_searchindex.py`: `TestIndexCli` (×4) drives the real verb through `cli.main` and asserts the one-line `ok/command/schema_version` envelope, the `invalid_input`/exit-2 path, stdout purity, and the non-json summary on stderr; `TestRealCorpus` (`skipUnless corpus/`) builds the real corpus into a **tempdir** DB and asserts `docs==742`, `chunks>docs`, `max_text_len<=MAX_CHUNK_CHARS`, and a byte-identical `chunk_id` list across a fresh rebuild (SC1).
- Verified the whole stack over the **real 742-doc corpus**: the manual `--json index corpus/` smoke emits one parseable `ok:true` envelope (`docs:742, chunks:7935, max_text_len:1800, tokenizer:"porter unicode61"`).

## Task Commits

Each task was committed atomically (code only; docs handled by the orchestrator):

1. **Task 1: `index` verb — _cmd_index handler + p_index subparser + FTS5 fail-loud** — `b915605` (feat)
2. **Task 2: Additive contract docs — CONTRACT.md ### index + contract.py docstring** — `03c08ad` (docs)
3. **Task 3: CLI-envelope tests + real-corpus 742 smoke (skipUnless)** — `3a31b0a` (test)

All three commits carry the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer.

_Plan/SUMMARY/STATE/ROADMAP docs commit is handled by the orchestrator (per execution constraints)._

## Files Created/Modified
- `crawler/cli.py` (modified, +59 lines) — `_cmd_index` handler (lazy import, dir guard, FTS5→missing_dependency, stdout-pure JSON); `p_index` subparser (`--db` default `corpus/index.db`); `index` added to subparsers metavar + module docstring subcommand map.
- `crawler/contract.py` (modified, +2/-2) — docstring-only: `index` appended to the module-docstring command enum (line 13) and the `envelope()` arg docstring. `SCHEMA_VERSION`, the five keys, and `EXIT_*` untouched.
- `crawler/CONTRACT.md` (modified, +22 lines) — new `### index` result-fields subsection; `index` added to the envelope-key command list; the `missing_dependency` taxonomy row notes the FTS5-absent index case.
- `crawler/tests/test_searchindex.py` (modified, +107 lines) — added `io`/`json`/`contextlib`/`cli` imports, `TestIndexCli` (capture helper mirroring `test_dupaudit.py:523-527`), `_ordered_chunk_ids` helper, and `TestRealCorpus` (`skipUnless` verbatim from `test_dupaudit.py:542-543`). The DB is always written inside a tempdir.

## Verification Results

All `<verify>` commands and the plan `<verification>` gates pass under Poetry (`poetry run python ...`, per the broken-pyenv-shim note):

- **Task 1** `poetry run python -m crawler.cli --json index /tmp/does-not-exist-xyz --db /tmp/x.db` → emits `ok:false`/`invalid_input` envelope, **exit 2** (`INVALID_INPUT_OK`); `index --help` works; `index` appears in the subparsers metavar.
- **Task 2** `grep -q '### \`index\`' CONTRACT.md && grep -q 'SCHEMA_VERSION = "1.0"' contract.py` → `DOCS_OK`.
- **Task 3** `poetry run python -m pytest crawler/tests/test_searchindex.py -q` → **28 passed** (Plan 01+02+03 classes). Verbose confirms `TestRealCorpus` and all four `TestIndexCli` cases **ran** (not skipped — `corpus/` present).
- **Manual real-corpus smoke** `poetry run python -m crawler.cli --json index corpus/ --db corpus/index.db | python -m json.tool` → one `ok:true`/`command:"index"`/`schema_version:"1.0"` envelope, `docs:742, chunks:7935, min_text_len:3, max_text_len:1800, tokenizer:"porter unicode61"`. (The git-ignored `corpus/index.db` was removed afterward; `git status corpus/` clean.)
- **Regression** `poetry run python -m pytest crawler/tests/test_cli.py crawler/tests/test_json_contract.py -q` → **32 passed, 1 skipped** (additive change broke no existing CLI/contract consumer; the 5-key `set(e)` guard still holds).
- **Grep gates** `grep -c 'envelope("index"' crawler/cli.py` = **1** (≥1 ✓); `grep -c 'SCHEMA_VERSION = "1.0"' crawler/contract.py` = **1** (==1 ✓).
- **Broad regression** (other modules, individually): `test_dupclean` 18✓, `test_engine_refactor` 6+26 subtests✓, `test_profile_loader` 15+3 subtests✓, `test_template_profile` 4✓, `test_parity_ircc` 6+30 subtests✓. (`test_dupaudit`'s real-corpus near-duplicate O(n²) overlap detection is a pre-existing slow path in a module this plan did not touch — `dupaudit.py` is unchanged, and `searchindex` imports `dupaudit`, never the reverse — so it is out of scope for 23-03's regression surface.)

## Decisions Made
See `key-decisions` frontmatter. In brief: `_cmd_index` runs the build in both `--json` and human modes because `searchindex.build_index` *is* the compute layer (no module `main()` to forward to, unlike the other verbs); only `FTS5Unavailable` is caught (everything else flows to `cli.main`'s `internal_error` catch-all); and the command enumerations everywhere were extended to `index` so the docs stay 1:1 with the code.

## Deviations from Plan

None — plan executed exactly as written. The handler, subparser, additive docs, and both test classes match the Task 1–3 actions and the cited analogs (`_cmd_report`/`_cmd_apply_verdicts` shapes, `test_dupaudit.py` capture helper + `skipUnless` guard, the Plan-02 `build_index` result dict).

Minor implementation notes (not deviations):
- Beyond the named `### index` subsection, the `index` command value was also added to the CONTRACT.md envelope-key table, the `contract.py` module docstring, and the `envelope()` arg docstring — required to keep the contract docs 1:1 with the now-five-command code (the additivity promise). No envelope key, `EXIT_*`, or `SCHEMA_VERSION` changed.
- `TestIndexCli` adds a fourth case (non-json summary → stderr) beyond the plan's named (a)/(b)/(c) to lock the stdout-purity invariant (threat T-23-06 / RETRIEVAL.md §7 P11) for the human path too.

## Issues Encountered
None affecting the plan. The pyenv `python` shim is broken (CRLF) as noted — all Python/pytest ran through `poetry run python …`; SQLite 3.37.2 ships FTS5, so the probe passes and the real-corpus build succeeds. A full `pytest crawler/tests/` run is slow only because of the pre-existing `test_dupaudit` real-corpus near-duplicate detection (untouched by this plan); every individual module passes.

## User Setup Required
None — no external service configuration. Stdlib `argparse`/`sqlite3` only; no package installs (Package Legitimacy Gate N/A, matching threat T-23-SC disposition `accept`). The `index` verb's default `--db corpus/index.db` is git-ignored.

## Threat Model Coverage
- **T-23-05 (host SQLite lacking FTS5):** mitigated — `_cmd_index` catches `searchindex.FTS5Unavailable` (raised by `build_index`'s probe before any corpus read) and emits a `missing_dependency` envelope + **exit 3**; loud, actionable, non-zero (RET-01 SC4).
- **T-23-06 (`--json` stdout purity):** mitigated — only `contract.emit` writes stdout in `--json` mode; the human docs/chunks summary is printed to stderr only. `TestIndexCli.test_json_stdout_is_pure_one_object` asserts exactly one JSON object on stdout (no `{` leaks to stderr); `test_non_json_summary_goes_to_stderr_not_stdout` proves the human path keeps stdout empty.
- **T-23-07 (additive contract / backward-compat):** mitigated — only a new `command` value + `result` shape were added; the five envelope keys, `EXIT_*`, and `SCHEMA_VERSION "1.0"` are unchanged (grep gate asserts `SCHEMA_VERSION = "1.0"`); the existing `set(e) == {5 keys}` contract test still passes.
- **T-23-03 (`--db` write target / path traversal):** mitigated — the default `--db` is the git-ignored `corpus/index.db`; the builder writes only that path; every test writes the DB inside a `TemporaryDirectory`, never under `corpus/` (`git status corpus/` stayed clean).
- No new threat surface beyond the plan's `<threat_model>` (no shell, no eval, no query input — the `index` verb takes only a corpus dir + db path; MATCH/query escaping is Phase 24's `search` verb).

## Known Stubs
None. No hardcoded empty values, placeholders, or unwired data paths were introduced — `_cmd_index` forwards live `build_index` results and is exercised end-to-end over the real 742-doc corpus.

## Next Phase Readiness
- **Phase 24 (`search` verb / RET-02)** now has a contracted, buildable index: the `index` verb materializes the queryable `chunks_fts` table + resolvable `chunk_id`, and `_cmd_index` is the dispatcher template for the `search` verb (lazy import + `envelope('search', ...)` + EXIT_* mapping, plus the MATCH/query escaping that Phase 24 owns).
- **Phase 25 (grounding gate)** has the `chunk_sha` staleness fingerprint and the documented, additive envelope contract to read against.
- No blockers. Phase 23 (FTS5 Index Builder) is complete end-to-end: probe + chunker (01), citable idempotent `build_index` (02), and the documented `index` CLI verb (03).

## Self-Check: PASSED
- `crawler/cli.py::_cmd_index` — FOUND (`grep -n "def _cmd_index"` → present)
- `crawler/CONTRACT.md ### index` — FOUND
- `crawler/tests/test_searchindex.py::TestIndexCli` / `TestRealCorpus` — FOUND
- Commit `b915605` — FOUND
- Commit `03c08ad` — FOUND
- Commit `3a31b0a` — FOUND
- 28/28 searchindex tests passing; 32 regression tests passing; no `corpus/` files staged; working tree (code) clean

---
*Phase: 23-fts5-index-builder*
*Completed: 2026-06-20*
