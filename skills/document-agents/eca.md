# ECA Agent (Educational Credential Assessment)

This skill teaches you how to use the shared answer-object contract
([`_contract.md`](_contract.md)) for ECA (Educational Credential Assessment)
questions — **read that first.** The contract defines the answer object, the
search → verbatim-quote → ground → abstain loop, the PII-tier split, the
abstention rule, and the critical environment (drive everything through
`corpus-crawler --json …` plus JSON parsing; never bare `python` — use
`.venv/bin/python` or `jq`). This file adds only the ECA specifics: the baked
query and the generic claim.

## What this agent answers

That a **foreign** educational credential must be assessed by a designated
organization (an ECA) so its Canadian equivalency and authenticity can be
established, as stated by the corpus. The **generic requirement label** is the
only thing that goes in `claims[]`. The applicant's own institutions, dates,
country of study, or assessing body are personal data and belong in `basis[]`
ONLY — never in a claim, a quote, or a citation.

## The baked query

Bake this SHORT, high-signal query (the index ANDs every token, so keep it 2–4
tokens — never a chunk id, which drifts and fails closed):

> `foreign educational credential assessment`

```bash
corpus-crawler --json search "foreign educational credential assessment" \
  --db corpus/index.db --limit 5
```

This ranks the generic `eca/educational-credential-assessment.md` page first.

> Copy the quote VERBATIM at runtime. The ECA chunks use a **curly apostrophe**
> (`’`, U+2019) in phrases like `organization’s` / `applicant’s`, and the gate
> normalizes whitespace + case ONLY — it does not normalize apostrophes. A
> straight-apostrophe retype fails `quote_not_in_chunk`; copy the exact bytes
> from `result.chunk.text`.

## The loop (by reference to the contract)

1. **Read the profile slice** for applicability. Anything personal (institution,
   country of study, dates) goes to `basis[]` only.
2. **Search** with the baked query. Read `result.hits`, best-first.
3. **Resolve** the top generic `eca/` hit to its exact stored chunk:
   ```bash
   corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db
   ```
   Read `result.found` and `result.chunk.text` (the verbatim span — never the
   display-only `snippet`). A miss is `found:false` → abstain.
4. **Copy a VERBATIM substring** of `result.chunk.text` into the claim's
   `quote`. Copy it at runtime; never paraphrase and never inline a corpus span
   into this file.
5. **Assemble and ground.** Emit one generic claim (a foreign credential must be
   assessed by a designated organization), keep personal data in `basis[]`, and
   pipe to the gate. If nothing resolves, abstain with reason `not_in_corpus`.

## Worked example

```bash
# 1. Search for the generic ECA rule, take the top hit's chunk_id.
corpus-crawler --json search "foreign educational credential assessment" \
  --db corpus/index.db --limit 5 \
  | .venv/bin/python -c "import json,sys
d=json.load(sys.stdin)
hits=d['result']['hits']
print(hits[0]['chunk_id'] if hits else 'ABSTAIN: not_in_corpus')"

# 2. Resolve the chosen chunk_id, then copy a substring of result.chunk.text
#    into the claim quote (do this at runtime, verbatim — keep curly apostrophes).
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Ground ONE generic, PII-free claim (institutions/dates stay in basis[]).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"How must a foreign educational credential be assessed?",
 "claims":[{"id":"eca",
            "text":"<generic requirement label: foreign credential assessed by a designated organization>",
            "citations":["<relpath#NNN>"],
            "quote":"<verbatim span copied from result.chunk.text>"}],
 "basis":["<applicant institution, country of study, dates — PII, never a claim>"],
 "abstentions":[],"prose":""}
JSON
```

If nothing resolves, emit an abstention instead of a claim:

```json
{"question":"How must a foreign educational credential be assessed?",
 "claims":[],
 "basis":["<applicant institution, country of study, dates>"],
 "abstentions":[{"text":"<note: the ECA requirement did not resolve in the corpus>","reason":"not_in_corpus"}],"prose":""}
```

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; quote every requirement value verbatim from
  the corpus (curly apostrophes included); abstain rather than confabulate.
