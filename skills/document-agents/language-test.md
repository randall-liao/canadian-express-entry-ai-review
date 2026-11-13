# Language-Test Agent

This skill teaches you how to use the shared answer-object contract
([`_contract.md`](_contract.md)) for language-test questions — **read that
first.** The contract defines the answer object, the search → verbatim-quote →
ground → abstain loop, the PII-tier split, the abstention rule, and the critical
environment (drive everything through `corpus-crawler --json …` plus JSON
parsing; never bare `python` — use `.venv/bin/python` or `jq`). This file adds
only the language-test specifics: the baked query and the generic claim.

## What this agent answers

That an applicant must prove their language ability with an **approved** language
test, as stated by the corpus. The **generic requirement label** is the only
thing that goes in `claims[]`. The applicant's own test choice, result numbers,
or proficiency level are personal data and belong in `basis[]` ONLY — never in a
claim, a quote, or a citation. Any test-score figure or proficiency level that
appears in the answer must be a span quoted verbatim from the corpus, never a
hand-typed value.

## The baked query

Bake this SHORT, high-signal query (the index ANDs every token, so keep it 2–4
tokens — never a chunk id, which drifts and fails closed):

> `language test approved results`

```bash
corpus-crawler --json search "language test approved results" \
  --db corpus/index.db --limit 5
```

This ranks the generic `guidance/language-test.md` rule page first.

## The loop (by reference to the contract)

1. **Read the profile slice** for applicability. Anything personal it yields
   (chosen test, dates, scores) goes to `basis[]` only.
2. **Search** with the baked query. Read `result.hits`, best-first.
3. **Resolve** the top generic guidance hit to its exact stored chunk:
   ```bash
   corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db
   ```
   Read `result.found` and `result.chunk.text` (the verbatim span — never the
   display-only `snippet`). A miss is `found:false` → abstain.
4. **Copy a VERBATIM substring** of `result.chunk.text` into the claim's
   `quote`. Copy it at runtime; never paraphrase and never inline a corpus span
   into this file.
5. **Assemble and ground.** Emit one generic claim (language ability must be
   proven via an approved test), keep personal data in `basis[]`, and pipe to
   the gate. If nothing resolves, abstain with reason `not_in_corpus`.

## Worked example

```bash
# 1. Search for the generic language-test rule, take the top hit's chunk_id.
corpus-crawler --json search "language test approved results" \
  --db corpus/index.db --limit 5 \
  | .venv/bin/python -c "import json,sys
d=json.load(sys.stdin)
hits=d['result']['hits']
print(hits[0]['chunk_id'] if hits else 'ABSTAIN: not_in_corpus')"

# 2. Resolve the chosen chunk_id, then copy a substring of result.chunk.text
#    into the claim quote (do this at runtime, verbatim).
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Ground ONE generic, PII-free claim (test choice/scores stay in basis[]).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"How must an applicant prove their language ability?",
 "claims":[{"id":"language-test",
            "text":"<generic requirement label: language ability proven via an approved test>",
            "citations":["<relpath#NNN>"],
            "quote":"<verbatim span copied from result.chunk.text>"}],
 "basis":["<applicant chosen test, dates, results — PII, never a claim>"],
 "abstentions":[],"prose":""}
JSON
```

If nothing resolves, emit an abstention instead of a claim:

```json
{"question":"How must an applicant prove their language ability?",
 "claims":[],
 "basis":["<applicant chosen test, dates, results>"],
 "abstentions":[{"text":"<note: the language-test requirement did not resolve>","reason":"not_in_corpus"}],"prose":""}
```

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; quote every requirement value verbatim from
  the corpus; abstain rather than confabulate.
