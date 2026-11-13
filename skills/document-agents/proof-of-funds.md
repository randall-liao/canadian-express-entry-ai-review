# Proof-of-Funds Agent

This skill teaches you how to use the shared answer-object contract
([`_contract.md`](_contract.md)) for proof-of-funds (settlement-funds) questions
— **read that first.** The contract defines the answer object, the search →
verbatim-quote → ground → abstain loop, the PII-tier split, the abstention rule,
the "no inlined volatile values" rule, and the critical environment (drive
everything through `corpus-crawler --json …` plus JSON parsing; never bare
`python` — use `.venv/bin/python` or `jq`). This file adds only the
proof-of-funds specifics: the baked query, the generic claim, and where program
applicability and the required figure must live.

## What this agent answers

That an applicant must show settlement funds they can **legally access** — money
they cannot borrow and cannot derive from real-property equity — as stated by the
corpus. The **generic requirement label** is the only thing that goes in
`claims[]`.

Two things stay OUT of `claims[]` and live in `basis[]` ONLY:

- **Program applicability.** Whether the funds requirement even applies — federal
  skilled-worker / skilled-trades applicants must meet it, while in-Canada
  experience-class and provincial-nominee applicants may be exempt — is a
  per-profile decision, not a corpus claim value. It is `basis[]`, never
  `claims[].text`.
- **The applicant's program and amount.** The applicant's own program, family
  size, and the figure they hold are personal data; they belong in `basis[]`.

Do **NOT** inline any dollar amount or family-size minimum into this file or into
`prose`. The required figure is volatile (IRCC revises it); if a claim asserts it,
the figure MUST arrive as a span quoted verbatim from the corpus, never a
hand-typed value. Otherwise let the corpus quote carry the requirement and keep
the figure in the applicant's `basis[]`.

## The baked query

Bake this SHORT, high-signal query (the index ANDs every token, so keep it 2–4
tokens — never a chunk id, which drifts and fails closed):

> `proof settlement funds`

```bash
corpus-crawler --json search "proof settlement funds" \
  --db corpus/index.db --limit 5
```

The `guidance/proof-funds.md` rule page (the "must legally access / can't
borrow / no real-property equity" requirement) is among these hits, but it is
**not** `hits[0]` — the top hit is a settlement-funds *scoring* page that does
**not** state the equity rule. Do **not** take `hits[0]`. Instead, **scan the
top hits in order, resolve each** (`--json search --cite <chunk_id>`), and
**select the FIRST whose `result.chunk.text` actually contains the equity rule
you must quote** — money you cannot derive from real-property equity. If none of
the top hits carries that span, abstain with reason `not_in_corpus`.

For the program-applicability nuance — who must meet the requirement *unless*
they are exempt — treat that applicability as `basis[]`, not a claim.

## The loop (by reference to the contract)

1. **Read the profile slice** for applicability — the applicant's program, family
   size, and the funds they hold. Everything personal goes to `basis[]` only.
2. **Search** with the baked query. Read `result.hits`, best-first, then **scan
   the top hits and resolve each until one's `result.chunk.text` contains the
   equity rule** — settlement funds cannot be real-property equity. Select that
   hit; if no top hit carries the span, abstain.
3. **Resolve** the chosen hit to its exact stored chunk:
   ```bash
   corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db
   ```
   Read `result.found` and `result.chunk.text` (the verbatim span — never the
   display-only `snippet`). A miss is `found:false` → abstain.
4. **Copy a VERBATIM substring** of `result.chunk.text` into the claim's `quote`.
   Copy it at runtime; never paraphrase, and never inline a corpus span — or a
   dollar amount — into this file. Any required figure must arrive as a quoted
   span, not a hand-typed number.
5. **Assemble and ground.** Emit one generic claim (settlement funds must be
   legally accessible — not borrowed, not real-property equity), put the
   applicant's program / family size / amount and the program-exemption logic in
   `basis[]`, and pipe to the gate. If nothing resolves, abstain with reason
   `not_in_corpus`.

## Worked example

```bash
# 1. Search, then scan the top hits and select the FIRST whose resolved chunk
#    text actually contains the equity rule you must quote. Abstain if none of
#    the top hits carries it (never quote the rule from a chunk that omits it).
corpus-crawler --json search "proof settlement funds" \
  --db corpus/index.db --limit 5 \
  | .venv/bin/python -c "import json,subprocess,sys
d=json.load(sys.stdin)
hits=d['result']['hits']
marker='equity on real property'  # the structural equity-rule phrase
def chunk_text(cid):
    out=subprocess.run(['corpus-crawler','--json','search','--cite',cid,
                        '--db','corpus/index.db'],capture_output=True,text=True).stdout
    r=json.loads(out)['result']
    return r['chunk']['text'] if r.get('found') else ''
sel=next((h['chunk_id'] for h in hits if marker in chunk_text(h['chunk_id'])),None)
print(sel or 'ABSTAIN: not_in_corpus')"

# 2. Resolve the chosen chunk_id, then copy a substring of result.chunk.text
#    into the claim quote (do this at runtime, verbatim).
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Ground ONE generic, PII-free claim. The program/exemption logic and the
#    applicant's amount stay in basis[]; no dollar figure is inlined.
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"What must the applicant's settlement funds satisfy?",
 "claims":[{"id":"proof-of-funds",
            "text":"<generic requirement label: settlement funds must be legally accessible, not borrowed, not real-property equity>",
            "citations":["<relpath#NNN>"],
            "quote":"<verbatim span copied from result.chunk.text>"}],
 "basis":["<applicant program, family size and the funds held; whether the program is exempt — PII/applicability, never a claim>"],
 "abstentions":[],"prose":""}
JSON
```

If nothing resolves, emit an abstention instead of a claim:

```json
{"question":"What must the applicant's settlement funds satisfy?",
 "claims":[],
 "basis":["<applicant program, family size and the funds held>"],
 "abstentions":[{"text":"<note: the settlement-funds rule did not resolve>","reason":"not_in_corpus"}],"prose":""}
```

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; quote every requirement value verbatim from the
  corpus; abstain rather than confabulate.
- NEVER inline a dollar amount or family-size minimum — the figure is volatile and
  is only ever a quoted span. Keep program applicability and the applicant's
  amount in `basis[]`, never in `claims[]`.
