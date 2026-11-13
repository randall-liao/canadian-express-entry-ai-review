# Phase 24 — `search` Verb + Citation Resolver · Validation Strategy (Nyquist)

**Requirement:** RET-02 (the only requirement in this phase)
**Goal under test:** Any CLI-agnostic agent can search the corpus for ranked, citable chunks and resolve a
citation back to its exact chunk — all through the existing `crawler/CONTRACT.md` JSON-envelope contract,
read-only over the Phase-23 index.

This file is the **sampling plan**: for each ROADMAP success criterion it names the smallest set of automated
checks that would catch a regression (the Nyquist rate — sample often enough that no failure mode hides
between probes). Every check is an `automated` command runnable today; none requires the real `corpus/`
except the explicitly-guarded round-trip smoke. All Python runs through Poetry because the pyenv `python`
shim is broken (CRLF / `/bin/sh^M`).

---

## Success-criterion → validation map

| SC (RET-02) | What must be TRUE | Validating test(s) | Plan |
|-------------|-------------------|--------------------|------|
| **SC1** Ranked, citable hits + snippet, one envelope | `search` returns BM25-ascending hits (stable `relpath#NNN` id, five citation fields, `snippet`), emitted as exactly one `command:"search"` envelope; human text on stderr | `TestSearch` (ranking/snippet/fields), `TestSearchCli` (one-line envelope, stdout purity), `TestRealCorpus` (real-corpus known-term search) | 01, 03 |
| **SC2** `--cite` resolves to the exact chunk; unknown/stale → fail-closed | `resolve()` returns verbatim `chunks.text` + fields for a hit, None for an unknown OR sha-drifted id; the `--cite` verb maps that to `found:true/false` (exit 0) | `TestResolve` (hit/miss/sha-drift), `TestSearchCli` (`--cite` hit + miss), `TestRealCorpus` (search→cite round-trip) | 02, 03 |
| **SC3** Adversarial-query safety; empty → INVALID_INPUT | R30(3)/apostrophe/`OR`/`body:funds` are literal terms (no fts5 error/injection); empty/all-punct → `EmptyQuery` → `invalid_input` exit 2 (no empty MATCH) | `TestToMatch` (escaper), `TestSearch` (adversarial + `EmptyQuery`), `TestSearchCli` (empty→invalid_input/exit2) | 01, 03 |
| **SC4** Additive contract; schema_version unchanged | five envelope keys + `schema_version "1.0"` unchanged; `CONTRACT.md` + `contract.py` document `search` (+ `--cite`) 1:1; existing consumers unaffected | `TestSearchCli` (schema_version "1.0" on a `search` envelope), grep gates, `test_cli.py` / `test_json_contract.py` regression | 03 |

---

## The six validation strands (and how each is sampled)

### 1. Adversarial-query safety — the headline (SC3)
- **Pure-function (default suite):** `TestToMatch` asserts `_to_match()` double-quotes every `\w+` token so
  `R30(3)` → distinct `"R30"`/`"3"` literals (parens dropped, no `fts5: syntax error`), `police OR certificates`
  keeps `OR` as a LITERAL term (no operator injection), `body:funds` drops the colon (no silent column filter),
  and an apostrophe query keeps the literal intact — and that an empty / all-punctuation query returns `None`.
- **Query-level (default suite):** `TestSearch` drives `R30(3)`, `police OR certificates`, `body:funds`, and an
  apostrophe query through `search()` and asserts **no exception**; it asserts `search(db, "")` /
  `search(db, "()!:")` raise `searchindex.EmptyQuery`.
- **Boundary (default suite):** `TestSearchCli` asserts an all-punct query → `ok:false` / `invalid_input` / exit 2
  via `cli.main` — the empty query is rejected at the boundary, never run as an empty MATCH.

### 2. BM25 ranking + snippet + citable id (SC1)
- `TestSearch` asserts the hit `score` list is non-decreasing (ascending bm25) and every score is negative
  (P9 — never negate/re-sort), each hit has the eight fields, `chunk_id` matches `^<relpath>#\d{3}$` (content
  coordinate, not the integer rowid — P8), and `snippet` is a non-empty str (the top hit's snippet contains a
  `⟦` highlight). `offsets()` is never used (P5) — asserted by the `grep -c "offsets(" == 0` gate.
- `TestRealCorpus` runs a known IRCC term (`"police certificate which countries"`) over the real 742-doc index
  and asserts ≥1 hit.

### 3. Citation resolution — exact chunk, fail-closed (SC2)
- `TestResolve`: (a) a known `chunk_id` resolves to the EXACT stored `chunks.text` (byte-for-byte, no `…`/`⟦`)
  plus the five citation fields; (b) an unknown id returns `None` (no exception); (c) a content-drifted row
  (test-only `UPDATE chunks SET text=...` leaving `chunk_sha` stale) resolves to `None` — the fail-closed
  staleness guard the Phase-25 gate relies on.
- `TestSearchCli` proves the `--cite` verb maps these to the contract: hit → `result.found=true` with the
  verbatim `chunk.text`; miss → `result.found=false`, `chunk:null`, exit 0 (a miss is NOT an execution error).

### 4. Additive contract / schema stability (SC4)
- `TestSearchCli` asserts a `search` envelope carries `command == "search"` and `schema_version == "1.0"`
  (unchanged), and that stdout is exactly one JSON object (`{` never leaks to stderr — P11).
- **Grep gates:** `grep -q '### `search`' crawler/CONTRACT.md` (doc mirrors code) and
  `grep -q 'SCHEMA_VERSION = "1.0"' crawler/contract.py` (version unchanged).
- **Regression:** `test_cli.py` + `test_json_contract.py` still pass — the additive `search` command broke no
  existing consumer.

### 5. Read-only invariant (RET-02 constraint)
- `TestSearch` snapshots `SELECT count(*) FROM chunks` before/after a `search()` and asserts equality (no
  mutation). `resolve()` likewise issues SELECT only.
- **Grep gate:** `grep -cE "INSERT|DROP|UPDATE|DELETE|commit" crawler/searchindex.py` is unchanged from Phase 23
  — `search()`/`resolve()` add NO write statement; the index is built solely by the Phase-23 `index` verb.

### 6. Real-corpus search↔cite round-trip (SC1 + SC2)
- `TestRealCorpus` (`@skipUnless(Path("corpus").is_dir())`) builds the real 742-doc corpus into a **tempdir** DB
  (never `corpus/index.db`, so the suite stages nothing under git-ignored `corpus/`), runs a known-term search,
  takes `hits[0]["chunk_id"]`, and asserts `resolve(tmpdb, that_id)` returns a dict with non-empty verbatim text
  whose `chunk_id` matches — the end-to-end citation handshake the grounding gate (GND-01) will call.

---

## Test inventory (class → concern → plan)

| Test class | Concern | Default suite? | Plan |
|------------|---------|----------------|------|
| `TestToMatch` | adversarial-query escaping (R30(3)/OR/colon/apostrophe/empty→None) (SC3) | yes | 01 |
| `TestSearch` | BM25-ascending negative scores, snippet, chunk_id, `--family`, EmptyQuery, read-only (SC1/SC3) | yes | 01 |
| `TestResolve` | verbatim text + fields hit, unknown→None, sha-drift→None (SC2) | yes | 02 |
| `TestSearchCli` | one-line `search` envelope, empty→invalid_input/exit2, non-file-db→exit2, stdout purity, `--cite` hit/miss (SC1/SC2/SC3/SC4) | yes | 03 |
| `TestRealCorpus` (extended) | real 742-doc search → resolvable chunk_id → `--cite` round-trip | **skipped unless `corpus/`** | 03 |

---

## Commands (copy-paste)

```bash
# Full phase suite (synthetic; the real-corpus round-trip auto-skips if corpus/ absent)
poetry run python -m pytest crawler/tests/test_searchindex.py -q

# Per-strand
poetry run python -m pytest crawler/tests/test_searchindex.py::TestToMatch -x -q     # SC3 escaper
poetry run python -m pytest crawler/tests/test_searchindex.py::TestSearch -x -q      # SC1/SC3 search
poetry run python -m pytest crawler/tests/test_searchindex.py::TestResolve -x -q     # SC2 resolve
poetry run python -m pytest crawler/tests/test_searchindex.py::TestSearchCli -x -q   # SC1/SC2/SC3/SC4 verb
poetry run python -m pytest crawler/tests/test_searchindex.py::TestRealCorpus -x -q  # round-trip smoke

# Regression: the additive `search` command broke nothing
poetry run python -m pytest crawler/tests/test_cli.py crawler/tests/test_json_contract.py -q

# Anti-pattern / read-only grep gates
grep -c "offsets(" crawler/searchindex.py                                  # == 0 (P5 — no FTS3/4 offsets)
grep -c "MATCH ?" crawler/searchindex.py                                   # >= 1 (parameter-bound MATCH)
grep -c "WHERE chunk_id = ?" crawler/searchindex.py                        # >= 1 (indexed resolve)
grep -cE "INSERT|DROP|UPDATE|DELETE|commit" crawler/searchindex.py         # unchanged vs Phase 23 (read-only)
grep -q '### `search`' crawler/CONTRACT.md && echo CONTRACT_OK             # doc mirrors code (SC4)
grep -q 'SCHEMA_VERSION = "1.0"' crawler/contract.py && echo SCHEMA_OK     # version unchanged (SC4)

# Real-corpus manual end-to-end (read-only against the live git-ignored index)
poetry run python -m crawler.cli --json search "police certificate which countries" --db corpus/index.db --limit 5 | poetry run python -m json.tool
# round-trip a returned hits[].chunk_id:
poetry run python -m crawler.cli --json search --cite "<paste-a-chunk_id>" --db corpus/index.db | poetry run python -m json.tool
# empty-query rejection:
poetry run python -m crawler.cli --json search "()!:" --db corpus/index.db; echo "exit=$?"   # ok:false / invalid_input / exit 2
```

---

## Out of scope for this validation (deferred, by design)
- **Grounding-by-construction gate / structured-answer contract / quote-substring verification** — Phase 25
  (GND-01/GND-02). This phase delivers ONLY the read primitives; `resolve()` returning `None` on miss/stale is
  the fail-closed signal the gate will build on, but the gate itself (claim-checking, verdict, eval harness) is
  not exercised here.
- **Semantic relevance / entailment quality of BM25 ranking** — out of scope (the corpus is keyword-FTS5 by
  decision; vectors/embeddings are explicitly excluded). The tests assert ranking *ordering* (score ascending,
  negative) and citability, not semantic faithfulness (deferred VAL-01/02).
- **Index construction / chunking / idempotency** — Phase 23 (RET-01), already verified. This phase is read-only
  over that index and never rebuilds or mutates it.
