# Common-Law Union Evidence Agent

This skill applies the shared answer-object contract
([`_contract.md`](_contract.md)) to common law union questions — **read that
first.** The contract defines the answer object, the search → verbatim-quote →
ground → abstain loop, the PII-tier split, the abstention rule, and the critical
environment (drive everything through `corpus-crawler --json …` plus JSON parsing;
never bare `python` — use `.venv/bin/python` or `jq`). This file adds only what is
specific to this document: its scope, the baked query, the selection rule, and the
verbatim-quote loop.

## What this agent answers

What an applicant must provide to **evidence a common-law union** — requested only when marital status is common-law. The generic requirement labels (the statutory declaration form plus evidence of cohabitation for the minimum continuous period the source states) are the only things that go in `claims[]`.

## The baked query

Bake this SHORT, high-signal query (2–4 tokens; the index ANDs every token, so keep
it short — never a chunk id, which drifts and fails closed):

> `common-law union cohabitation evidence`

```bash
corpus-crawler --json search "common-law union cohabitation evidence" --db corpus/index.db --limit 5
```

## The selection rule

Do **not** blindly take `hits[0]`. Resolve each hit in BM25 order and select the
**first** whose `result.chunk.text` contains the structural requirement phrase
**"Statutory Declaration of Common-Law Union"** — a non-volatile marker that uniquely lands the e-APR
document-requirements chunk for this document. If no hit contains it, abstain.

## The loop (by reference to the contract)

Follow the contract's loop exactly:

1. **Read the profile slice** for applicability (does this document apply to this
   applicant?). Everything personal goes to `basis[]` ONLY.
2. **Search** with the baked query; read `result.hits`.
3. **Resolve** the selected hit to its exact stored chunk:
   ```bash
   corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
     | jq -r '.result.chunk.text'
   ```
   Read `result.found` and `result.chunk.text` (the verbatim span — never the
   display-only `snippet`). A miss is `found:false` → abstain.
4. **Copy a verbatim substring** of `result.chunk.text` into the claim's `quote`.
   Copy it at runtime; never paraphrase, and never inline a corpus span into this
   file.
5. **Emit one generic claim** (the requirement label only), put all personalization
   in `basis[]`, and **ground** the answer by piping to `corpus-crawler --json
   ground`.

## The abstention rule

If the requirement cannot be grounded — the chunk does not resolve, or no verbatim
span exists — emit an `abstentions[]` entry with reason `not_in_corpus` and **no
claim**. NEVER confabulate a requirement or a quote: a fabricated quote yields
`verdict:"fail"`, `reasons:["quote_not_in_chunk"]`, exit 1, and writes nothing.
Abstain rather than invent.

## Worked example

The `quote` and `basis` values below are **placeholder tokens** — copy the real
verbatim span from `result.chunk.text` at runtime, and never paste a real name,
date, or amount.

```bash
# 1. List candidate hits (best-first). Per the selection rule, resolve each in
#    order and keep the FIRST whose text contains the marker
#    "Statutory Declaration of Common-Law Union" — do not assume hits[0].
corpus-crawler --json search "common-law union cohabitation evidence" --db corpus/index.db --limit 5 \
  | jq -r '.result.hits[].chunk_id'

# 2. Resolve a candidate; keep this one only if its text contains the marker.
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Copy a verbatim substring of the matched chunk's text, then assemble ONE
#    generic claim and ground it. Read the envelope `ok` first, then branch on
#    result.verdict (per _contract.md).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"What must an applicant provide to evidence a common-law union?",
 "claims":[
   {"id":"common-law-declaration","text":"<generic PII-free requirement label>",
    "citations":["<relpath#NNN>"],"quote":"<verbatim span from result.chunk.text>"}],
 "basis":["<personal applicability sentence with placeholder tokens>"],
 "abstentions":[],"prose":""}
JSON
```

Branch on the **envelope** then the **verdict**: read `ok` first; on `ok:true` read
`result.verdict`. Only `verdict:"pass"` (exit 0) means the claim grounded — then the
answer is rendered beside its verbatim quote, share-safety-scanned, and written to
the git-ignored `personal/output/` boundary. A `verdict:"fail"` (exit 1) renders and
writes nothing — drop the bad quote or abstain, never confabulate.

## PII discipline

The partner's name, the cohabitation dates and address, and the supporting joint documents are **personal data** — keep them in `basis[]` ONLY. Do not inline the minimum cohabitation window; quote it from the corpus at runtime. The grounding gate inspects `claims[]` only and the renderer writes only
the grounded, scanned claims, so the rendered output under `personal/output/` is
**PII-free by construction**.

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; select by the structural marker, not `hits[0]`;
  copy a verbatim quote; keep all PII in `basis[]`; abstain rather than confabulate
  or leak.
