---
phase: 26-personalized-layer-1-checklist-pii-separation
plan: 02
subsystem: checklist
tags: [grounding, retrieval, fts5, pii-separation, express-entry, layer-1, unittest, defense-in-depth]

# Dependency graph
requires:
  - phase: 25-grounding-gate
    provides: "grounding.check_answer (fail-closed answer gate) + the {question, claims[], basis[], abstentions[], prose} answer shape this plan assembles and gates THROUGH"
  - phase: 24-search-verb
    provides: "searchindex.search(query, family=) BM25 retrieval + searchindex.resolve() verbatim citation resolver (consumed here)"
  - phase: 26-personalized-layer-1-checklist-pii-separation
    provides: "Plan 01 checklist.applicable_items() — the deterministic PII-tiered item list this plan turns into grounded claims"
provides:
  - "crawler/checklist.py: grounded_claim(db, item) — retrieve -> relpath backstop -> resolve -> verbatim quote -> PII-free claim; fail-closed None"
  - "crawler/checklist.py: build_answer(profile, db) — assemble the 5-key Phase-25 answer object, gate it through grounding.check_answer, abstain explicitly"
  - "crawler/checklist.py: RESEARCH-verified generic queries baked into applicable_items (no country-page leak) + per-country relpath backstop (threat T-26-08)"
  - "crawler/tests/test_checklist.py: synthetic-corpus assembler suite + PII-separation + generic-citation + abstention + @skipUnless real-corpus integration (39 tests total)"
affects: [26-03, checklist-cli, render-answer, publish-safety]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Grounding-by-construction: grounded_claim only emits resolving+verbatim claims; build_answer re-runs grounding.check_answer and demotes any rejected claim to an abstention so the returned answer always verifies pass"
    - "Defense-in-depth no-leak: (1) verified generic queries baked into applicable_items + (2) a CODE-LEVEL relpath backstop in grounded_claim that refuses any police-certificates/<country> page + (3) optional per-item family= retrieval constraint"
    - "Fail-closed abstention: EmptyQuery / zero-hit / all-country-specific / unresolvable-drift / empty-quote each yield None -> explicit abstention, never an ungrounded or residence-leaking claim"
    - "PII tiering by construction: claims[].text = generic label, claims[].quote = verbatim corpus span; ALL profile PII confined to basis[] (never gated, never rendered)"

key-files:
  created: []
  modified:
    - crawler/checklist.py
    - crawler/tests/test_checklist.py

key-decisions:
  - "grounded_claim ITERATES hits (limit=5) and skips any country-specific relpath rather than blindly taking hits[0] — the relpath backstop is the hard no-leak guarantee, independent of query tuning (plan-checker WARNING folded in)"
  - "build_answer runs the assembled answer THROUGH grounding.check_answer and demotes any rejected claim to an abstention (grounding-by-construction); satisfies the build_answer -> grounding.check_answer key-link and guarantees a pass verdict on return"
  - "Relpath re-checked AFTER resolve() (not only on the search snippet row) — resolve() is the source of truth for the stored relpath"
  - "Synthetic corpus bodies carry every token of the VERIFIED applicable_items queries so the REAL baked queries ground end-to-end offline; a planted police-certificates/<country> page exercises the backstop without the real index"

patterns-established:
  - "Pattern: verify-then-bake — each generic query was author-time checked against corpus/index.db (top hit is a GENERIC page), then baked into applicable_items; a @skipUnless real-corpus test re-asserts it"
  - "Pattern: fail-closed assembler — every retrieval/resolution failure mode becomes an explicit abstention; the answer is never empty-and-silent (SC1 honesty boundary)"

requirements-completed: [CHK-01, CHK-02]

# Metrics
duration: 25min
completed: 2026-06-21
---

# Phase 26 Plan 02: Checklist Assembler (grounded PII-free claims + gated answer) Summary

**`grounded_claim` retrieves a GENERIC corpus chunk for each applicable item (short verified query → relpath backstop that refuses per-country police pages → resolve → verbatim quote), and `build_answer` assembles the Phase-25 answer object — PII confined to `basis[]`, every claim cited + verbatim-grounded — then runs it THROUGH `grounding.check_answer`, demoting anything ungroundable to an explicit abstention.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-21T07:17:00-04:00
- **Completed:** 2026-06-21T07:42:00-04:00
- **Tasks:** 2 (both TDD)
- **Files modified:** 2 (both extended from Plan 01)

## Accomplishments

- **`grounded_claim(db, item)`** — runs the item's SHORT generic query (`searchindex.search`, `limit=5`, optional `family=`), iterates the best hits, **SKIPS any country-specific relpath** (`police-certificates/<country>` — threat T-26-08), resolves the first generic hit via `searchindex.resolve` (fail-closed `None` on miss/sha-drift), and slices a **VERBATIM** quote span from the live chunk text. Returns a gate-ready `{id, text, citations, quote}` whose `text` is the GENERIC PII-free label from Plan 01 — or `None` (a fail-closed abstention) on EmptyQuery / zero-hit / all-country-specific / unresolvable / empty-quote.
- **`build_answer(profile, db)`** — selects applicable items, grounds each, assembles `{question, claims[], basis[], abstentions[], prose}` with **all profile PII confined to `basis[]`**, runs the answer THROUGH the shipped Phase-25 gate (`grounding.check_answer`) and **demotes any rejected claim to an explicit abstention** so the returned answer always verifies `pass` (grounding-by-construction). Zero-applicable / zero-grounded → explicit abstention, never an empty claimless answer (SC1).
- **Defense-in-depth no-residence-leak (plan-checker WARNING folded in):** (1) baked the RESEARCH-verified generic queries into `applicable_items` (each author-time verified to return a GENERIC top hit against the live 742-doc index), **and** (2) added the CODE-LEVEL relpath backstop in `grounded_claim` so the guarantee does not rest on query tuning alone, **and** (3) plumbed the optional `family=` retrieval constraint through. The corpus holds **229** `police-certificates/<country>.md` pages and a naive query (e.g. `police certificate national authority`) surfaces `police-certificates/peru.md` — exactly the leak the backstop refuses.
- **Tests:** extended `crawler/tests/test_checklist.py` from 20 → **39** tests: a synthetic generic-corpus harness, `grounded_claim` unit tests (verbatim-grounds / zero-hit / EmptyQuery / unresolvable / **backstop-skips-country** / only-country→None / family-constraint), `build_answer` grounds + 5-key assembly + FSW proof-of-funds, abstention, **PII-separation** (sentinels never in `claims[].text`/`quote`, retained in `basis[]`), **generic-citation**, and a `@skipUnless corpus/index.db` real-corpus integration test (the baked queries ground + cite no country page).

## Task Commits

Each task executed TDD, committed atomically:

1. **Task 1 (RED): failing grounded_claim + build_answer assembler tests** — `57d2ed4` (test)
2. **Task 1 (GREEN): grounded_claim + build_answer (gate by construction)** — `7a5a312` (feat)
3. **Task 2: PII-separation + generic-citation guarantee tests** — `5ae8660` (test)

**Plan metadata:** committed separately with this SUMMARY (docs).

_Task 2 needed no production change: the PII-separation + generic-citation guarantees are by-construction from the Task-1 relpath backstop and PII tiering. Per the plan ("If build_answer/grounded_claim need a tiny adjustment to keep PII out of claims (it must not), fix it"), the Task-2 commit is the explicit regression assertion the plan requires. The backstop is proven load-bearing by Task-1's `test_only_country_page_grounds_to_none` / `test_backstop_skips_country_page_grounds_generic`._

## Files Created/Modified

- `crawler/checklist.py` — EXTENDED (+194 lines): `grounded_claim`, `build_answer`, `_assemble_answer`, `_is_country_specific`, `_verbatim_quote`, constants (`_ANSWER_QUESTION`, `_QUOTE_MAX_CHARS`, `_COUNTRY_SPECIFIC_FAMILIES`); imports `re` + `from crawler import grounding, searchindex`; baked the RESEARCH-verified generic queries into `applicable_items`.
- `crawler/tests/test_checklist.py` — EXTENDED (+328 lines): `_make_corpus` + `_GENERIC_DOCS` + `_example_profile` harness; `TestGroundedClaim`, `TestBuildAnswerGrounds`, `TestAbstention`, `TestPiiSeparation`, `TestGenericCitation`, `@skipUnless` `TestRealCorpus`.

## Decisions Made

- **Iterate-and-skip over `hits[0]`:** `grounded_claim` walks up to 5 hits and skips any country-specific relpath, then resolves the first generic hit. This makes the no-leak guarantee a property of the code, not of the query string — fail-closed if every hit is country-specific.
- **`build_answer` gates by construction:** it re-runs `grounding.check_answer` and demotes any rejected claim to an abstention. Because `grounded_claim` already only emits resolving+verbatim claims this is belt-and-braces, but it makes the returned answer's `pass` verdict a guarantee and satisfies the planned `build_answer → grounding.check_answer` key-link.
- **Verified queries baked in:** each generic query was author-time checked against `corpus/index.db`; e.g. `police certificate 10 years country → guidance/police-certificates.md#002` (generic), `give biometrics permanent residence → biometrics/when-to-give.md#000`, `settlement funds requirement unless → pr-pdi/...#036`. The `job-offer` query was tuned to `arranged employment job offer letter` (grounds to a generic `pr-pdi` page).
- **Reused the shipped gate + resolver verbatim:** `crawler/grounding.py` and `crawler/searchindex.py` are UNMODIFIED (`git diff --stat` for this plan shows only `checklist.py` + `test_checklist.py`).

## Deviations from Plan

**None — plan executed exactly as written, with the plan-checker WARNING folded into the implementation as instructed** (verified generic queries baked into `applicable_items` + a code-level relpath backstop in `grounded_claim` + the optional `family=` constraint). No architectural changes, no new dependencies (stdlib + the in-repo `grounding`/`searchindex` only).

## Issues Encountered

- The full suite is slow because `crawler/tests/test_dupaudit.py::TestRealCorpus` walks the real `corpus/index.db`. Verification was split accordingly (see below). That single `TestRealCorpus` failure is **pre-existing and unrelated** to this phase (documented in STATE.md / the 26-01 summary) — **no new regression introduced**.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_checklist.py -q` → **39 passed** (real-corpus integration tests RAN, not skipped — `corpus/index.db` present).
- `.venv/bin/python -m pytest crawler/tests/test_checklist.py -k "grounds or assemble or abstain" -q` → all assembler/abstention tests pass.
- `.venv/bin/python -m pytest crawler/tests/test_checklist.py -k pii -q` → **4 passed** (PII-separation guarantees).
- `.venv/bin/python -m pytest crawler/tests -q --ignore=crawler/tests/test_dupaudit.py` → **225 passed, 1 skipped, 59 subtests passed**.
- `.venv/bin/python -m pytest crawler/tests/test_dupaudit.py -q -k "not RealCorpus"` → **25 passed** (only the pre-existing `TestRealCorpus` remains failing — out of scope).
- End-to-end real-corpus `build_answer(personal.example, corpus/index.db)` → verdict **pass**; all 6 claims cite GENERIC pages (police → `guidance/police-certificates.md#002`, never a country page); sentinel PII (Wakanda/Latveria) present ONLY in the police `basis`, absent from every `claims[].text`/`quote`/`prose`.
- `grep -c 'searchindex.resolve' crawler/checklist.py` (non-comment) → **2** (≥1; citations resolved via the shipped resolver).
- `git diff --stat ac58157..HEAD -- crawler/` → only `crawler/checklist.py` + `crawler/tests/test_checklist.py` (grounding.py / searchindex.py UNMODIFIED).

## Known Stubs

None. The Plan-01 placeholder queries are now replaced with RESEARCH-verified generic queries (the Plan-01 "Known Stubs" item is resolved). No data-source stub flows to any rendered output — rendering is Plan 03.

## Next Phase Readiness

- `build_answer` returns a gated, PII-free-by-construction answer object ready for **Plan 03** to `grounding.render_answer` (claims+quote+citation only, never `basis[]`) → `check_publish_safe.scan_text` → anchored write under `personal/output/`, exposed via the new `checklist` CLI verb.
- The synthetic `_make_corpus`/`_GENERIC_DOCS` harness + the `@skipUnless` real-corpus pattern are ready to drive the Plan-03 CLI + publish-safety self-scan tests.
- No blockers. PII boundary verified end-to-end; the no-residence-leak guarantee rests on three independent layers (verified queries + relpath backstop + optional family constraint).

---
*Phase: 26-personalized-layer-1-checklist-pii-separation*
*Completed: 2026-06-21*

## Self-Check: PASSED

- FOUND: crawler/checklist.py
- FOUND: crawler/tests/test_checklist.py
- FOUND: .planning/phases/26-personalized-layer-1-checklist-pii-separation/26-02-SUMMARY.md
- FOUND commit 57d2ed4 (test: Task 1 RED)
- FOUND commit 7a5a312 (feat: Task 1 GREEN)
- FOUND commit 5ae8660 (test: Task 2 guarantee tests)
