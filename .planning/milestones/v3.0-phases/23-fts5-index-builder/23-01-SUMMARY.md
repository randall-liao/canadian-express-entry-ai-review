---
phase: 23-fts5-index-builder
plan: 01
subsystem: api
tags: [sqlite, fts5, chunking, retrieval, citations, stdlib]

# Dependency graph
requires:
  - phase: 20-dedup-audit
    provides: "dupaudit.live_docs / body_of / _frontmatter_of / body_hash corpus primitives (reused by Plan 02)"
  - phase: 13-config-engine
    provides: "profile._HEADING_RE — the crawler's ATX heading regex, reused by the chunker"
provides:
  - "crawler/searchindex.py module scaffold (stdlib-only, OFFLINE) for Phase 23"
  - "FTS5/chunks DDL as named module constants (CHUNKS_DDL + external-content FTS_DDL)"
  - "FTS5Unavailable + _probe_fts5(con): fail-loud FTS5 feature-detection (RET-01 SC4)"
  - "chunk(body) -> [(section, text)]: deterministic, bounded, heading-aware chunker (RET-01 SC2/SC3)"
  - "chunk_sha(text): sha1[:12] staleness fingerprint convention for Plan 02 / Phase 25"
  - "MIN/MAX/TARGET chunk tunables + TOKENIZER 'porter unicode61' + DB_SCHEMA_VERSION constants"
affects: [23-02-build_index, 23-03-index-cli-verb, 24-search-verb, 25-grounding-gate]

# Tech tracking
tech-stack:
  added: []  # stdlib sqlite3/re/hashlib only — zero new runtime dependency
  patterns:
    - "FTS5 external-content schema (chunks + chunks_fts content='chunks') — NO contentless FTS"
    - "Feature-detect-before-use probe (CREATE/DROP throwaway fts5 vtable) that fails loud"
    - "Pure deterministic chunker (no randomness/time/I/O) so citation chunk_ids are byte-identical across rebuilds"
    - "Content-coordinate citation id scheme (relpath#ordinal, minted in Plan 02) — never the integer rowid"

key-files:
  created:
    - crawler/searchindex.py
    - crawler/tests/test_searchindex.py
  modified: []

key-decisions:
  - "Chunker is pure str->[(section,text)] and does NOT re-strip front-matter — Plan 02 passes dupaudit.body_of output (no primitive duplication)"
  - "Merge floor skips a merge that would push the previous chunk past MAX_CHUNK_CHARS, so the SC3 hard ceiling always holds even when folding a sub-MIN tail"
  - "Hard-split falls back to char-splitting a single boundary-less sentence > MAX, guaranteeing no unbounded chunk for the ~0.5-1 MB legislation FullText docs"
  - "DB_SCHEMA_VERSION='1' (index-DB diagnostics) is kept distinct from the contract envelope schema_version '1.0' (which must not change)"

patterns-established:
  - "FTS5 probe pattern: _probe_fts5(con) raises FTS5Unavailable with an ENABLE_FTS5 remediation, leaves no _probe residue, runs before any corpus read"
  - "Heading-breadcrumb section: running heading stack joined by U+203A ( \u203a ), plus ' \u203a s.<marker>' for bold statutory markers (**9.4**)"

requirements-completed: [RET-01]  # partial — Plan 01 delivers SC2/SC3/SC4 foundations; SC1 idempotent build lands in Plan 02

# Metrics
duration: 10min
completed: 2026-06-20
---

# Phase 23 Plan 01: FTS5 Index Builder Foundation Summary

**Dependency-free `crawler/searchindex.py` foundation: the fail-loud FTS5 availability probe and the pure deterministic heading-aware chunker, plus the FTS5/`chunks` external-content DDL constants — the two "no in-repo analog" pieces every later Phase 23 plan stands on.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-20T22:35:00-04:00 (approx, session start)
- **Completed:** 2026-06-20T22:44:29-04:00 (last task commit)
- **Tasks:** 2 of 2 completed
- **Files modified:** 2 (both created)

## Accomplishments
- Built the **fail-loud FTS5 probe** (`_probe_fts5` + `FTS5Unavailable`): feature-detects FTS5 via a throwaway `CREATE VIRTUAL TABLE _probe USING fts5(x)` / `DROP`, raises an actionable `ENABLE_FTS5` remediation message on a SQLite that lacks FTS5, and leaves no `_probe` residue (RET-01 SC4).
- Built the **deterministic heading-aware chunker** `chunk(body) -> [(section, text)]`: heading-stack breadcrumb (reusing `profile._HEADING_RE`), paragraph packing toward `TARGET` with a hard `MAX` ceiling, undersized-tail merge floor, sentence/char hard-split for overlong legislation paragraphs, and bold statutory-marker capture (`**9.4**` → ` › s.9.4`) (RET-01 SC2/SC3, determinism for SC1).
- Defined the **FTS5 schema as named module constants** (`CHUNKS_DDL` with `chunk_sha`, external-content `FTS_DDL` with `content='chunks'`, `tokenize='porter unicode61'`) plus chunker tunables — all stdlib, zero new runtime dependency.
- Landed **13 stdlib-unittest tests** (`TestFtsProbe`, `TestChunkBounds`, `TestChunkSection`) covering fail-loud, residue, sane constants, working DDL round-trip, tiny→1-chunk, no-unbounded-chunk, merge floor, heading breadcrumb, statutory marker, and determinism.

## Task Commits

Each task was committed atomically (test + implementation together; code only):

1. **Task 1: Module scaffold, constants, DDL, and the fail-loud FTS5 probe** — `4bff297` (feat)
2. **Task 2: Deterministic heading-aware chunker `chunk(body) -> [(section, text)]`** — `5789a87` (feat)

_Plan/SUMMARY/STATE/ROADMAP docs commit is handled by the orchestrator (per execution constraints)._

## Files Created/Modified
- `crawler/searchindex.py` (created, 280 lines) — module scaffold + design-constraints docstring; `MIN/MAX/TARGET_CHUNK_CHARS`, `TOKENIZER`, `DB_SCHEMA_VERSION` constants; `CHUNKS_DDL` / `FTS_DDL`; `FTS5Unavailable` + `_probe_fts5`; `chunk_sha`; `chunk` + helpers `_hard_split` / `_pack` / `_merge_floor`.
- `crawler/tests/test_searchindex.py` (created) — `TestFtsProbe` (6 cases), `TestChunkBounds` (4 cases), `TestChunkSection` (3 cases); stdlib `unittest`, synthetic inline inputs, no tempdir/network.

## Verification Results

All `<verify>` commands and the plan `<verification>` gates pass under Poetry:

- `poetry run python -m pytest crawler/tests/test_searchindex.py::TestFtsProbe -x -q` → **6 passed** (Task 1)
- `poetry run python -m pytest "...::TestChunkBounds" "...::TestChunkSection" -x -q` → **7 passed** (Task 2)
- `poetry run python -m pytest crawler/tests/test_searchindex.py -q` → **13 passed**
- `poetry run python -c "import crawler.searchindex"` → imports clean, no new dependency
- Grep gates: contentless-FTS non-comment count = **0**; `porter unicode61` count = **2** (≥1); `profile._HEADING_RE` reused (3 hits); `VIRTUAL TABLE … fts5` present
- Regression: `poetry run python -m pytest crawler/tests/test_cli.py crawler/tests/test_json_contract.py -q` → **32 passed, 1 skipped** (no contract/CLI regression)

## Decisions Made
See `key-decisions` frontmatter. In brief: the chunker is a pure function that trusts Plan 02 to pass an already front-matter-stripped body; the merge floor and hard-split are both written to never violate the `MAX_CHUNK_CHARS` ceiling; `DB_SCHEMA_VERSION` is deliberately separate from the contract envelope `schema_version`.

## Deviations from Plan

None - plan executed exactly as written. Both tasks followed RETRIEVAL.md §2/§3/§7 and the cited analog symbols (`dupaudit.body_of`/`body_hash`, `profile._HEADING_RE`, `pipeline.MIN_CONTENT_CHARS`, `contract` constants) as specified.

Minor implementation note (not a deviation): the module docstring contains the literal string `yaml.load` only inside the anti-pattern reminder "never ``yaml.load``"; Plan 01 imports no `yaml` and makes no `yaml.*` call (front-matter parsing is Plan 02's surface). `yaml.safe_load`-only remains the standing rule for Plan 02.

## Issues Encountered
None. The pyenv `python` shim is broken (CRLF) as noted in the plan; all Python/pytest ran through `poetry run python …` as required, with SQLite 3.37.2 (FTS5 compiled in) confirmed on this box.

## User Setup Required
None - no external service configuration required. Stdlib `sqlite3`/`re`/`hashlib` only; no package installs, so the RESEARCH Package Legitimacy Gate is N/A (matches threat T-23-SC disposition `accept`).

## Threat Model Coverage
- **T-23-04 (DoS via ~1 MB legislation paragraph):** mitigated — `_hard_split` (sentence then char fallback) bounds every chunk; `TestChunkBounds.test_long_paragraph_is_split_and_never_unbounded` asserts `max(len(text)) <= MAX_CHUNK_CHARS`.
- **T-23-05 (host SQLite lacking FTS5 → silent wrong behavior):** mitigated — `_probe_fts5` raises `FTS5Unavailable` with an actionable message and drops the probe table; `TestFtsProbe` covers the fail-loud + no-residue paths. CLI wiring (probe-before-corpus-read + exit code) lands in Plan 03.
- No new threat surface beyond the plan's `<threat_model>` (no network, no path deref, no eval; the probe is an in-memory throwaway vtable).

## Next Phase Readiness
- **Plan 02 (`build_index`)** can now import `searchindex.chunk`, the DDL constants, `_probe_fts5`, and `chunk_sha`, and wire them to `dupaudit.live_docs` to mint `chunk_id = relpath#ordinal` rows (SC1 idempotent rebuild + SC2 five citation fields).
- **Plan 03 (`index` CLI verb)** can call `_probe_fts5` at the top of the build (before any corpus read) and map `FTS5Unavailable` → a loud non-zero envelope.
- No blockers. The two no-analog foundations are GREEN-tested in isolation as intended.

## Self-Check: PASSED
- `crawler/searchindex.py` — FOUND
- `crawler/tests/test_searchindex.py` — FOUND
- Commit `4bff297` — FOUND
- Commit `5789a87` — FOUND
- 13/13 tests passing; no `corpus/` files staged; working tree clean

---
*Phase: 23-fts5-index-builder*
*Completed: 2026-06-20*
