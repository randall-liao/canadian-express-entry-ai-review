---
phase: 24-search-verb-citation-resolver
verified: 2026-06-21T06:03:35Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification — no prior VERIFICATION.md existed."
---

# Phase 24: `search` Verb + Citation Resolver — Verification Report

**Phase Goal:** Any CLI-agnostic agent can search the corpus for ranked, citable chunks and resolve a citation back to its exact chunk — all through the existing `crawler/CONTRACT.md` JSON-envelope contract.
**Verified:** 2026-06-21T06:03:35Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

Goal-backward verification was run against the ACTUAL codebase and a live execution of the
CLI over the real `corpus/index.db`, not against SUMMARY.md claims. Every must-have truth
was confirmed by reading the implementation AND by behavioral spot-checks (live CLI smoke +
named tests). All 8 truths hold.

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | `--json search "<q>"` emits exactly one CONTRACT envelope (command=search, ok=true, schema_version 1.0) with BM25-ranked hits; human summary to stderr only | ✓ VERIFIED | Live smoke on `corpus/index.db`: stdout = exactly 1 line, `ok=True`, `command=search`, `schema_version=1.0`, `count==len(hits)==3`, each hit has the 8 fields (`chunk_id, source_url, relpath, title, section, crawl_date, snippet, score`), snippet carries `⟦`, score negative; `--json` stderr is empty and `{` never appears on stderr. Non-json mode: stdout = 0 bytes, summary `"2 hits for 'police certificate'"` on stderr. `cli.py:380-384`, `searchindex.py:457-473`. TestSearchCli (6 tests) green. |
| 2 | `--json search --cite <id>` resolves: hit → found=true exact chunk; unknown/stale id → found=false (fail-closed, exit 0) | ✓ VERIFIED | Live smoke: real id → `ok=True, found=True`, chunk has 7 keys (chunk_id + 5 citation fields + verbatim text, 1647 chars, no `⟦`/`…`), exit 0; `no-such/doc.md#999` → `ok=True, found=False, chunk=None`, exit 0. `cli.py:330-344`. TestResolve + TestSearchCli `test_cite_hit`/`test_cite_miss` green. |
| 3 | Adversarial/empty queries: empty/all-punct → invalid_input exit 2 (never empty MATCH); no-FTS5 host → missing_dependency exit 3; non-file --db → invalid_input exit 2 | ✓ VERIFIED | Live smoke: `"()!:"` → `ok=False, invalid_input, result=None`, **exit 2**; `--db /no/such/db` → `ok=False, invalid_input`, **exit 2**. EmptyQuery raised before any MATCH (`searchindex.py:443-445`). FTS5Unavailable→missing_dependency/exit 3 path is wired (`cli.py:370-378`) and `_probe_fts5` is called before the query (`searchindex.py:451`) — same guard the tested `index` verb uses; not behaviorally triggerable on this FTS5-enabled host (see Notes). |
| 4 | `_to_match()` makes section codes / OR / colons / apostrophes literal (no FTS5 injection or syntax error) | ✓ VERIFIED | In-process: `R30(3)`→`"R30" "3"`, `police OR certificates`→`"police" "OR" "certificates"` (OR is a literal term), `body:funds`→`"body" "funds"` (colon dropped, no column filter), `women's certificate`→`"women" "s" "certificate"` (apostrophe dropped), empty/`   `/`()[]:!`→`None`. All four adversarial queries run on the real index with exit 0 / ok=true (no `fts5: syntax error`). `searchindex.py:400-417`. TestToMatch (6 tests) green. |
| 5 | `resolve()` returns verbatim `chunks.text` + 5 citation fields; sha-drift → None (the fail-closed guard Phase-25 GND-01 relies on) | ✓ VERIFIED | `resolve()` returns exactly `{chunk_id, relpath, source_url, title, section, crawl_date, text}` with `text` verbatim (live cite-hit: no snippet markers); recomputes `chunk_sha(row["text"]) != row["chunk_sha"] → return None` (`searchindex.py:526-527`); internal `chunk_sha` is NOT exposed. TestResolve `test_sha_drift_row_resolves_to_none_fail_closed`, `test_returned_text_is_verbatim_not_a_snippet`, `test_unknown_id_returns_none_fail_closed`, `test_empty_id_returns_none` all green. |
| 6 | CONTRACT.md + contract.py document `search` additively; SCHEMA_VERSION + 5 envelope keys unchanged | ✓ VERIFIED | `CONTRACT.md:166-216` adds `### search` documenting both ranked-search and `--cite` shapes 1:1 with the code; `search` added to the command list (`CONTRACT.md:54`). `contract.py` lists `search` in both docstrings (`:13`, `:69`). `SCHEMA_VERSION="1.0"`, envelope keys = exactly `[schema_version, ok, command, result, error]`, EXIT_* unchanged (2/3/4). Regression: `test_cli.py`+`test_json_contract.py` → 32 passed, 1 skipped (additive change broke nothing). |
| 7 | Real 742-doc index round-trips (search → resolvable hit → --cite back to exact chunk) | ✓ VERIFIED | `corpus/index.db` holds exactly **742 distinct docs** / 7935 chunks. `TestRealCorpus::test_real_corpus_search_resolve_round_trip` **PASSED (not skipped)**. Live smoke: `search "police certificate which countries"` returned a hit whose `chunk_id` resolved via `--cite` back to a 1647-char verbatim chunk. |
| 8 | Test suite is green | ✓ VERIFIED | `test_searchindex.py` → **59 passed in 2.95s** (TestToMatch, TestSearch, TestResolve, TestSearchCli, TestRealCorpus + Phase-23 classes). Regression suites → 32 passed, 1 skipped. |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/searchindex.py` | `_to_match()` escaper, read-only `search()` BM25 query, `resolve()` resolver, `EmptyQuery` | ✓ VERIFIED | `_to_match` (`:400`), `search` (`:420`), `resolve` (`:487`), `EmptyQuery(ValueError)` (`:105`) all present, substantive (540 lines), wired into `cli.py`, and exercised by live data. No write statements in lines 420–540 (SELECT-only). |
| `crawler/cli.py` | `_cmd_search` thin dispatcher + `p_search` subparser | ✓ VERIFIED | `_cmd_search` (`:294`) lazy-imports `searchindex`, validates `--db`, dispatches search/resolve, maps EmptyQuery→invalid_input(2) / FTS5Unavailable→missing_dependency(3); `p_search` registered (`:456-468`) with `query?`/`--db`/`--cite`/`--limit`/`--family`; `search` in metavar (`:402`). |
| `crawler/contract.py` | docstrings enumerate `search`; SCHEMA_VERSION unchanged | ✓ VERIFIED | `search` in module + `envelope()` docstrings (`:13`, `:69`); `SCHEMA_VERSION="1.0"` (`:41`); five-key envelope + EXIT_* unchanged. |
| `crawler/CONTRACT.md` | additive `### search` result-fields subsection | ✓ VERIFIED | `### search` (`:166-216`) documents ranked-search + `--cite` resolve shapes, fail-closed semantics, and reuses existing error taxonomy/exit codes 1:1 with the code. |
| `crawler/tests/test_searchindex.py` | TestToMatch, TestSearch, TestResolve, TestSearchCli, TestRealCorpus round-trip | ✓ VERIFIED | All five classes present (1027 lines); 30 phase-24 tests collected and passing. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `searchindex.search` | `searchindex._to_match` | escape raw query before MATCH | ✓ WIRED | `match = _to_match(query)` (`:443`); only the escaped string binds to `MATCH ?`. |
| `searchindex.search` | `chunks_fts MATCH ?` | parameter-bound FTS5 MATCH | ✓ WIRED | `WHERE chunks_fts MATCH ?` (`:463`), bound positionally; `grep -c "MATCH ?" = 2`. |
| `searchindex.resolve` | `chunks WHERE chunk_id = ?` | parameter-bound indexed lookup | ✓ WIRED | `WHERE chunk_id = ?` (`:512`), bound positionally. |
| `searchindex.resolve` | `searchindex.chunk_sha` | recompute fingerprint to detect drift | ✓ WIRED | `chunk_sha(row["text"]) != row["chunk_sha"]` (`:526`); `grep -c "chunk_sha(" = 3`. |
| `cli._cmd_search` | `searchindex.search` | lazy import + forward (ranked path) | ✓ WIRED | `searchindex.search(db, args.query, args.limit, args.family)` (`cli.py:359`). |
| `cli._cmd_search` | `searchindex.resolve` | `--cite` dispatch | ✓ WIRED | `searchindex.resolve(db, args.cite)` (`cli.py:331`). |
| `cli._cmd_search` | `contract.emit(envelope("search"))` | one envelope per call | ✓ WIRED | `envelope("search"...)` 2 occurrences (`cli.py:339,381` + error paths). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `search()` result hits | `hits` | `con.execute(sql, params).fetchall()` over `chunks_fts JOIN chunks` | Yes — live query on real 742-doc index returned 3 ranked, citable hits | ✓ FLOWING |
| `resolve()` chunk | `row` | `SELECT ... FROM chunks WHERE chunk_id = ?` | Yes — live `--cite` returned a 1647-char verbatim chunk | ✓ FLOWING |
| `_cmd_search` envelope | `result` | `searchindex.search`/`resolve` return value | Yes — real payload reaches stdout as one CONTRACT envelope | ✓ FLOWING |

No hollow props, no static/empty fallbacks: the CLI forwards real compute output; the only `[]`/`None`
defaults are legitimate (empty hits on no-match, `chunk:null` on a fail-closed miss).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Ranked search envelope | `cli --json search "police certificate which countries" --db corpus/index.db --limit 3` | 1 stdout line, ok=true, command=search, schema 1.0, 3 hits w/ 8 fields, ⟦ snippet, neg score | ✓ PASS |
| `--cite` hit | `cli --json search --cite <real-id> --db corpus/index.db` | ok=true, found=true, verbatim 1647-char chunk, 7 keys, exit 0 | ✓ PASS |
| `--cite` miss | `cli --json search --cite "no-such/doc.md#999" --db corpus/index.db` | ok=true, found=false, chunk=null, exit 0 | ✓ PASS |
| Empty/all-punct query | `cli --json search "()!:" --db corpus/index.db` | ok=false, invalid_input, exit 2 | ✓ PASS |
| Non-file `--db` | `cli --json search "x" --db /no/such/db.db` | ok=false, invalid_input, exit 2 | ✓ PASS |
| Adversarial queries (R30(3), OR, colon, apostrophe) | `cli --json search "<q>" --db corpus/index.db` | all exit 0 / ok=true, no fts5 syntax error | ✓ PASS |
| Non-json stdout purity | `cli search "police certificate" --db corpus/index.db` | stdout 0 bytes, summary on stderr | ✓ PASS |
| Real-corpus round-trip (named test) | `pytest ...TestRealCorpus::test_real_corpus_search_resolve_round_trip -v` | 1 passed (RAN, not skipped) | ✓ PASS |
| Full module suite | `pytest crawler/tests/test_searchindex.py -q` | 59 passed | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes are declared for this phase (verb-test phase).
Verification used the project's pytest suites + live CLI smoke per the environment note.

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| _(none declared)_ | — | — | N/A |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| RET-02 | 24-01, 24-02, 24-03 (all declare `requirements: [RET-02]`) | Expose a `search` CLI verb returning ranked chunks + a stable resolvable citation ID per hit, emitting the existing JSON-envelope contract, so any CLI-agnostic agent can shell out | ✓ SATISFIED | All 4 ROADMAP Success Criteria (SC1–SC4) verified above. REQUIREMENTS.md `:20` defines RET-02; traceability matrix `:60` maps RET-02 → Phase 24. No orphaned requirement IDs for this phase. |

_Note: REQUIREMENTS.md still lists RET-02 as "Pending" (`:60`) and the checkbox unchecked (`:20`) — this is the
expected pre-completion state; this verification is the gate that authorizes marking it Complete. Not a gap._

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER in any modified file | — | None |

Anti-pattern grep gates all pass: `offsets(`=0, `MATCH ?`=2 (≥1), `WHERE chunk_id = ?`=2 (≥1),
`chunk_sha(`=3 (≥3), `envelope("search"`=2 (≥1), `SCHEMA_VERSION = "1.0"`=1. Write statements
(`INSERT`/`DROP`/`commit`) are confined to `build_index` and the `_probe_fts5` temp-table probe;
`search()`/`resolve()` bodies are SELECT-only (read-only confirmed).

### Human Verification Required

None. The phase delivers a machine-readable JSON CLI contract with no visual/UX/real-time/external-service
surface; every observable behavior was exercised directly against the real 742-doc index and via named tests.

### Notes (informational, non-blocking)

- **no-FTS5-host → missing_dependency exit 3** is the one error path that cannot be *triggered* on this
  host (its SQLite has FTS5). It is nonetheless verified by code inspection: `_cmd_search` catches
  `searchindex.FTS5Unavailable` and returns `MISSING_DEPENDENCY`/exit 3 (`cli.py:370-378`), `search()`
  calls the shared `_probe_fts5` guard before any query (`searchindex.py:451`), and this is byte-for-byte
  the same guard/mapping the `index` verb uses (whose FTS5 path is covered by the green suite). This is a
  structurally-proven, correctly-wired path — not a gap and not a human-verification item.

### Gaps Summary

No gaps. All 8 must-have truths are VERIFIED against the actual codebase and a live run over the real
742-doc index. The 3 plans deliver exactly what the phase goal requires: a CLI-agnostic agent can
`--json search` for BM25-ranked, citable chunks and `--json search --cite <id>` to resolve a citation
back to its exact (fail-closed, sha-drift-guarded) chunk, entirely through the unchanged five-key
CONTRACT.md envelope (schema_version 1.0, additive). RET-02 SC1–SC4 are all satisfied.

---

_Verified: 2026-06-21T06:03:35Z_
_Verifier: the agent (gsd-verifier)_
