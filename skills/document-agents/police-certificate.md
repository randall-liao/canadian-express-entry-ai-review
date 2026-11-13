# Police-Certificate Agent

This skill teaches you how to use the shared answer-object contract
([`_contract.md`](_contract.md)) for police-certificate questions — **read that
first.** The contract defines the answer object, the search → verbatim-quote →
ground → abstain loop, the PII-tier split, the abstention rule, and the critical
environment (drive everything through `corpus-crawler --json …` plus JSON
parsing; never bare `python` — use `.venv/bin/python` or `jq`). This file adds
only what is specific to police certificates: the residence-history no-leak
backstop and the baked query.

## What this agent answers

Who must provide a police (criminal-record) certificate for a Canadian
permanent-residence application, as stated by the corpus. The **generic
requirement label** — *who must provide a police certificate* — is the only
thing that goes in `claims[]`. The applicant's actual countries of residence and
the dates they lived there are **personal data**: they decide applicability and
belong in `basis[]` ONLY. They never appear in a claim, a quote, or a citation.

## The residence-history no-leak backstop (read this before you cite)

The corpus holds hundreds of per-country pages whose **relpath itself** leaks
where the applicant lived (for example, any path that starts with
`police-certificates/` followed by a country name). Citing one of those would
disclose residence history through the citation string alone. Defend with both
layers, together:

1. **Constrain retrieval to the generic guidance family.** ALWAYS run the baked
   search with `--family guidance`. The generic rule page lives at
   `guidance/police-certificates.md`; the leaky per-country pages live under the
   `police-certificates/` family and are excluded by the filter.

2. **Apply the relpath backstop anyway (defense in depth).** Independent of the
   query, NEVER cite a chunk whose relpath starts with `police-certificates/`.
   Walk the hits best-first and **skip** any hit whose relpath begins with
   `police-certificates/`; take the first GENERIC hit instead. If every hit is
   country-specific — or nothing resolves — **abstain** with reason
   `not_in_corpus` rather than cite a leaky page. This mirrors
   `crawler/checklist.py:_is_country_specific` (which normalizes the relpath —
   folds `\` to `/`, strips leading separators, lowercases — before the prefix
   test) and `grounded_claim` (skip the country relpath, resolve, re-check the
   resolved relpath, slice a verbatim quote, and fail closed on any miss).

## The baked query

Bake this SHORT, high-signal query (the index ANDs every token, so keep it 2–4
tokens — never a chunk id, which drifts and fails closed):

> `police certificate every country`

Always run it with `--family guidance`:

```bash
corpus-crawler --json search "police certificate every country" \
  --db corpus/index.db --family guidance --limit 5
```

This lands the generic `guidance/police-certificates.md` rule page — no
per-country relpath.

## The loop (by reference to the contract)

Follow the contract's loop exactly; the police-specific parts are the family
filter and the backstop above.

1. **Read the profile slice** for applicability — which countries and dates make
   a police certificate required. Everything personal goes to `basis[]` only.
2. **Search** with the baked query and `--family guidance`. Read `result.hits`,
   then skip any hit whose relpath starts with `police-certificates/`.
3. **Resolve** the chosen generic hit to its exact stored chunk:
   ```bash
   corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db
   ```
   Read `result.found` and `result.chunk.text` (the verbatim span — never the
   display-only `snippet`). A miss is `found:false` → abstain.
4. **Copy a VERBATIM substring** of `result.chunk.text` into the claim's
   `quote`. Copy it at runtime; never paraphrase, and never inline a corpus
   span into this file. Any requirement value — the age threshold or the
   residence-history window — must arrive as a quoted span, not a hand-typed
   number.
5. **Assemble and ground.** Emit one generic claim (the requirement label), put
   the applicant's countries and dates in `basis[]`, and pipe to the gate.

## Worked example

```bash
# 1. Search the generic guidance family, then apply the relpath backstop.
corpus-crawler --json search "police certificate every country" \
  --db corpus/index.db --family guidance --limit 5 \
  | .venv/bin/python -c "import json,sys
d=json.load(sys.stdin)
hits=d['result']['hits']
generic=[h for h in hits if not h['chunk_id'].startswith('police-certificates/')]
print(generic[0]['chunk_id'] if generic else 'ABSTAIN: not_in_corpus')"

# 2. Resolve the chosen generic chunk_id, then copy a substring of
#    result.chunk.text into the claim quote (do this at runtime, verbatim).
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Ground ONE generic, PII-free claim (countries stay in basis[]).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"Who needs a police certificate for this application?",
 "claims":[{"id":"police-certificate",
            "text":"<generic requirement label: who must provide a police certificate>",
            "citations":["<relpath#NNN>"],
            "quote":"<verbatim span copied from result.chunk.text>"}],
 "basis":["<applicant countries of residence and dates — PII, never a claim>"],
 "abstentions":[],"prose":""}
JSON
```

When no generic hit resolves, emit an abstention instead of a claim — never cite
a leaky page:

```json
{"question":"Who needs a police certificate for this application?",
 "claims":[],
 "basis":["<applicant countries of residence and dates>"],
 "abstentions":[{"text":"<note: no generic police-certificate rule resolved>","reason":"not_in_corpus"}],"prose":""}
```

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- ALWAYS `--family guidance`; NEVER cite a `police-certificates/<country>`
  relpath — skip to the next generic hit or abstain.
- Bake the query, not a chunk id; quote every requirement value verbatim from
  the corpus; abstain rather than confabulate or leak.
