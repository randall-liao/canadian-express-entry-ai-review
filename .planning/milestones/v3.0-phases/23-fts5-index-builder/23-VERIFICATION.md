---
phase: 23-fts5-index-builder
verified: 2026-06-21T03:26:38Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification — no prior VERIFICATION.md existed."
requirements:
  - id: RET-01
    status: satisfied
---

# Phase 23: FTS5 Index Builder — Verification Report

**Phase Goal:** A re-runnable SQLite FTS5 keyword index exists over the clean 742-doc
corpus, with every chunk carrying resolvable citation metadata — the citable ground every
later answer stands on.
**Requirement:** RET-01 (sole requirement)
**Verified:** 2026-06-21T03:26:38Z
**Status:** passed
**Re-verification:** No — initial verification

Verification was goal-backward and evidence-first: every ROADMAP success criterion was
re-derived against the *shipped code* and confirmed by (a) reading the module, (b) running
the phase test suite, and (c) an **independent real-corpus build** by the verifier — not by
trusting SUMMARY.md. The verifier's own build reproduced the SUMMARY's headline numbers
exactly (`docs=742`, `chunks=7935`, `max_text_len=1800`), so the SUMMARY is corroborated,
not merely accepted.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — the RET-01 contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | **Idempotent, diffable rebuild over the live-doc set (742-filter); re-run → byte-identical `chunk_id`s** | ✓ VERIFIED | `build_index` iterates **exactly** `dupaudit.live_docs` (searchindex.py:332) + full `DROP`+rebuild (searchindex.py:322-328) + pure `chunk()`. Verifier built the real corpus twice into separate DBs → both `7935` ordered `chunk_id`s **byte-identical**, same sha1 `4c424e8c0f120f4e0bec875899b7958066f1fb08`. `result["docs"]==742`. Tests `TestIdempotent::test_rebuild_yields_byte_identical_chunk_ids`, `test_chunk_sha_pairs_are_stable_across_rebuilds`, and `TestRealCorpus` (real 742-doc rebuild equality) **PASSED**. |
| 2 | **Five citation fields per chunk (relpath, source_url verbatim, title, section breadcrumb+statutory marker, crawl_date); `chunk_id = relpath#ordinal` (NOT rowid); section computed from headings** | ✓ VERIFIED | `CHUNKS_DDL` defines all five fields (searchindex.py:63-78). Over the real DB: **0** chunks missing `relpath`/`source_url`/`title`/`crawl_date`; **7934/7935** carry a non-empty heading breadcrumb, 7159 use the `›` separator. `chunk_id = f"{relpath}#{ordinal:03d}"` (searchindex.py:346), e.g. `mi-rounds/invitations-12.md#000` — distinct from the integer `id` rowid. `source_url` read VERBATIM via `meta.get("url")` (searchindex.py:338), no `normalize_url`. `section` derived from `profile._HEADING_RE` + `_STATUTE_RE` (`s.9.4`), never invented. Tests `TestCitationFields` ×6 (incl. `test_source_url_is_read_verbatim_not_renormalized`, `test_chunk_id_is_content_coordinates_not_rowid`) + `TestChunkSection` ×3 **PASSED**. |
| 3 | **Bounded deterministic chunking (tiny→1 chunk; large FullText split; no unbounded chunk; max ≤ MAX_CHUNK_CHARS)** | ✓ VERIFIED | `MAX_CHUNK_CHARS=1800`. Real-corpus build: `max_text_len=1800`, and a direct DB scan found **0** chunks `> 1800`. `chunks=7935 > docs=742` → the ~0.5–1 MB IRPA/IRPR `FullText` docs genuinely split. `_hard_split` guarantees boundedness (sentence-split then last-resort char-split, searchindex.py:143-173); `_merge_floor` never breaches the ceiling (searchindex.py:215-216). Tests `TestChunkBounds` ×4 (tiny→1 chunk; overlong→split & bounded) + `TestRealCorpus` **PASSED**. |
| 4 | **Index DB under git-ignored `corpus/`; corpus text + citation metadata only (no PII, no vectors); stdlib `sqlite3` only; FTS5-probe fails loud** | ✓ VERIFIED | `git check-ignore` confirms `corpus/` and `corpus/index.db` ignored (.gitignore:8); `git log --all` shows **no `.db` ever committed**; `git status` shows nothing under `corpus/` staged. Real-DB table set is exactly `chunks` + `chunks_fts*` (FTS shadow) + `meta` — **no vector/embedding table**. Imports are stdlib (`hashlib`/`re`/`sqlite3`/`pathlib`) + existing `yaml` dep; `import crawler.searchindex` OK, **no new dependency**. No `personal/`/PII access (reads only `corpus/` via `live_docs`). `_probe_fts5` raises `FTS5Unavailable` with an `ENABLE_FTS5` remediation (searchindex.py:105-121) **before any corpus read** (searchindex.py:319); CLI maps it to `missing_dependency` + **exit 3** (cli.py:271-280). Tests `TestFtsProbe` ×6 (incl. `test_probe_fails_loud_when_fts5_absent`, `test_probe_leaves_no_residue`) + `TestCitationFields::test_db_has_no_vectors_table` **PASSED**. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `crawler/searchindex.py` | FTS5 probe + deterministic chunker + `build_index` | ✓ VERIFIED | 385 lines, substantive. `_probe_fts5`, `chunk()` (pure), `build_index()` all present & wired; imports reused corpus primitives (`dupaudit.live_docs`/`body_of`/`_frontmatter_of`, `profile._HEADING_RE`). |
| `crawler/cli.py` (`index` verb) | thin dispatcher + FTS5 fail-loud → exit 3 | ✓ VERIFIED | `_cmd_index` (cli.py:244-290) lazy-imports searchindex, validates dir (→`invalid_input`/exit 2), maps `FTS5Unavailable`→`missing_dependency`/exit 3, emits one envelope. `index` subparser registered (cli.py:352-358). |
| `crawler/contract.py` | additive 5-key envelope, schema 1.0 | ✓ VERIFIED | `SCHEMA_VERSION="1.0"` unchanged (contract.py:41); envelope still exactly 5 keys (`schema_version/ok/command/result/error`); `index` added to command list. |
| `crawler/CONTRACT.md` | documents `index` result 1:1 | ✓ VERIFIED | "five-key envelope", `schema_version "1.0"`, `index` result table (db/corpus/docs/chunks/min_text_len/max_text_len/tokenizer) matches code 1:1 (CONTRACT.md:146-164); error paths (exit 2/3) documented. |
| `crawler/tests/test_searchindex.py` | offline unittest suite | ✓ VERIFIED | 655 lines, 28 tests across 6 classes; stdlib `unittest`, synthetic + real-corpus smoke. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `cli._cmd_index` | `searchindex.build_index` | lazy import + call | ✓ WIRED | cli.py:256,270 — result forwarded into `contract.envelope("index", result=...)`. |
| `build_index` | `dupaudit.live_docs` | iterate the 742-filter | ✓ WIRED | searchindex.py:332 — real build yields `docs=742`; noise files excluded (`test_noise_files_are_not_indexed` PASSED). |
| `build_index` | `chunks` + `chunks_fts` | INSERT + `'rebuild'` resync | ✓ WIRED | searchindex.py:348-358; FTS `integrity-check` PASSES on the real DB; `MATCH 'biometrics'` returns real hits. |
| `build_index` | front-matter | `yaml.safe_load` (verbatim url) | ✓ WIRED | searchindex.py:335-338; 5 fields populated, url query+fragment preserved. |
| `_probe_fts5` failure | CLI exit 3 envelope | `except FTS5Unavailable` | ✓ WIRED | cli.py:271-280 → `missing_dependency` + `EXIT_MISSING_DEPENDENCY` (=3). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `chunks` table | per-chunk citation row | `dupaudit.live_docs` → front-matter + `chunk()` | Yes — 7935 rows over 742 real docs, all 5 fields non-empty | ✓ FLOWING |
| `chunks_fts` index | searchable `text` | external-content `'rebuild'` from `chunks` | Yes — `integrity-check` passes, `MATCH` returns hits | ✓ FLOWING |
| `index` envelope `result` | build stats | `build_index` return dict | Yes — `{docs:742, chunks:7935, max_text_len:1800, ...}` on stdout | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Real-corpus build over 742-filter | `corpus-crawler --json index corpus/ --db corpus/index.db` | `ok:true`, `docs=742`, `chunks=7935`, `max_text_len=1800`, `schema_version=1.0` | ✓ PASS |
| Idempotent byte-identical rebuild | second build → compare ordered `chunk_id`s | identical (7935==7935), same sha1 `4c424e8c…` | ✓ PASS |
| No unbounded chunk | `SELECT count(*) FROM chunks WHERE length(text)>1800` | `0` | ✓ PASS |
| No vectors / table set | `SELECT name FROM sqlite_master WHERE type='table'` | `chunks, chunks_fts(+shadow), meta` only | ✓ PASS |
| FTS index functional | `chunks_fts MATCH 'biometrics'` + `integrity-check` | 3 real hits; integrity-check PASS | ✓ PASS |
| Module imports w/o new dep | `python -c "import crawler.searchindex"` | import OK | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` declared for this phase; verification is the
`unittest`/pytest suite named in 23-VALIDATION.md, run below.

| Suite | Command | Result | Status |
|-------|---------|--------|--------|
| Phase suite | `poetry run python -m pytest crawler/tests/test_searchindex.py -q` | **28 passed in 2.08s** (incl. `TestRealCorpus` — ran, not skipped, corpus/ present) | ✓ PASS |
| Additive-contract regression | `poetry run python -m pytest crawler/tests/test_cli.py crawler/tests/test_json_contract.py -q` | **32 passed, 1 skipped** | ✓ PASS |

> Per scope guidance, the `dupaudit` real-corpus O(n²) slow path (untouched module) was
> not run — out of scope for Phase 23.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RET-01 | 23-01/02/03 | Re-runnable SQLite FTS5 keyword index over the clean corpus; chunk + store 5 citation fields per chunk; no vectors/embeddings | ✓ SATISFIED | All 4 success criteria VERIFIED above; 28+32 tests green; independent real-corpus build reproduces 742/7935/1800. |

No orphaned requirements: RET-01 is the sole Phase-23 requirement and is fully claimed by the plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER scan over all 5 shipped files | — | **None found** — clean |
| — | — | `yaml.load` (unsafe) | — | **None** — only `yaml.safe_load` used (searchindex.py:335) |
| — | — | Phase-24 scope leak (`search` verb / `--cite` / `MATCH` / bm25 / snippet) | ℹ️ Info | **No leak** — only forward-looking docstring mentions of `snippet()`; no `search`/`cite` subparser, no SQL `MATCH`, no ranking code in shipped Phase-23 surface |

The `min_text_len=3` / 2375 sub-`MIN_CHUNK_CHARS` chunks are **not** a stub or violation:
`MIN_CHUNK_CHARS` is a *merge floor*, and a section's sole chunk is the documented
exception (VALIDATION.md "allowing the sole-chunk floor"). The binding bound for SC3 is the
MAX ceiling, which holds (0 chunks > 1800). This is correct citation granularity for the
many short guidance/definition docs.

### Human Verification Required

**None.** This phase is an offline, deterministic build with no UI, no real-time behavior,
and no external service. Every success criterion is programmatically verifiable and was
verified by the verifier's own commands (build + idempotency diff + DB introspection +
test run). The only environment-bound path — the CLI `missing_dependency`/exit-3 branch on a
host whose SQLite lacks FTS5 — cannot be exercised at runtime here because this box's SQLite
ships FTS5 (3.37.2, `ENABLE_FTS5`); however the fail-loud unit (`_probe_fts5`) IS tested via a
stub and the CLI mapping is code-verified (cli.py:271-280), so no human action is required.

### Gaps Summary

No gaps. All four RET-01 success criteria are genuinely delivered by the shipped code and
proven by green tests plus an independent verifier build:

1. **Idempotent diffable rebuild over the 742-filter** — two real builds produced
   byte-identical 7935-id lists (same sha1).
2. **Five resolvable citation fields, `chunk_id = relpath#ordinal`, section from headings** —
   0 missing fields, verbatim `source_url`, content-coordinate id ≠ rowid.
3. **Bounded deterministic chunking** — `max_text_len=1800`, 0 unbounded chunks, legislation
   FullText split (chunks ≫ docs), tiny docs → 1 chunk.
4. **Git-ignored DB, no PII/vectors, stdlib-only, fail-loud FTS5 probe** — corpus/ ignored &
   no `.db` ever committed, table set is chunks/chunks_fts*/meta only, no new dep, probe
   raises actionable `FTS5Unavailable`.

The additive contract is intact (`schema_version "1.0"`, five envelope keys unchanged,
`index` documented 1:1) and the regression suite stays green. No Phase-24 scope leaked.

---

_Verified: 2026-06-21T03:26:38Z_
_Verifier: the agent (gsd-verifier)_
