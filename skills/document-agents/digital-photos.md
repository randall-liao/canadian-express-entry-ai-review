# Digital Photos Agent

This skill applies the shared answer-object contract
([`_contract.md`](_contract.md)) to digital photos questions — **read that
first.** The contract defines the answer object, the search → verbatim-quote →
ground → abstain loop, the PII-tier split, the abstention rule, and the critical
environment (drive everything through `corpus-crawler --json …` plus JSON parsing;
never bare `python` — use `.venv/bin/python` or `jq`). This file adds only what is
specific to this document: its scope, the baked query, the selection rule, and the
verbatim-quote loop.

## What this agent answers

What **digital photos** an Express Entry e-APR requires, and whether submitted photo inspection documents meet IRCC permanent resident card specifications. It evaluates requirements and surfaces any non-compliance or specification defects.

## The baked query

Bake this SHORT, high-signal query (2–4 tokens; the index ANDs every token, so keep
it short — never a chunk id, which drifts and fails closed):

> `digital photos permanent resident card`

```bash
corpus-crawler --json search "digital photos permanent resident card" --db corpus/index.db --limit 5
```

## The selection rule

Do **not** blindly take `hits[0]`. Resolve each hit in BM25 order and select the
**first** whose `result.chunk.text` contains the structural requirement phrase
**"permanent resident card photo specifications"** — a non-volatile marker that uniquely lands the e-APR
document-requirements chunk for this document. If no hit contains it, abstain.

## Document validation and defect inspection

When evaluating an attached photo or inspection report, inspect every supplied
page for legibility and directly observable photo characteristics. Resolve the
applicable specifications from the public corpus before comparing any reported
measurement, date, framing, expression, background, or lighting characteristic.
Do not treat a document's own compliance statement as authoritative. Put observed
document facts in `basis[]`; emit only generic requirement claims supported by an
exact corpus quote. If the evidence or public rule is insufficient, abstain.

## The loop (by reference to the contract)

Follow the contract's loop exactly:

1. **Read the profile slice and document attachment** for applicability and defects. Everything personal goes to `basis[]` ONLY.
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
5. **Emit generic requirement claims**, put all personalization and observed
   document facts in `basis[]`, and **ground** the answer by piping to `corpus-crawler --json
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
#    "permanent resident card photo specifications" — do not assume hits[0].
corpus-crawler --json search "digital photos permanent resident card" --db corpus/index.db --limit 5 \
  | jq -r '.result.hits[].chunk_id'

# 2. Resolve a candidate; keep this one only if its text contains the marker.
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Copy a verbatim substring of the matched chunk's text, then assemble ONE
#    generic requirement claim and ground it. Read the envelope `ok`
#    first, then branch on result.verdict (per _contract.md).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"What digital photos must an Express Entry applicant provide?",
 "claims":[
   {"id":"digital-photos-spec","text":"<generic PII-free requirement label>",
   "citations":["<relpath#NNN>"],"quote":"<verbatim span from result.chunk.text>"}],
 "basis":["<personal applicability sentence and observed document facts>"],
 "abstentions":[],"prose":""}
JSON
```

Branch on the **envelope** then the **verdict**: read `ok` first; on `ok:true` read
`result.verdict`. Only `verdict:"pass"` (exit 0) means the claim grounded — then the
answer is rendered beside its verbatim quote, share-safety-scanned, and written to
the git-ignored `personal/output/` boundary. A `verdict:"fail"` (exit 1) renders and
writes nothing — drop the bad quote or abstain, never confabulate.

## PII discipline

The photo images themselves are **personal data** — keep any reference to them in `basis[]` ONLY. The grounding gate inspects `claims[]` only and the renderer writes only
the grounded, scanned claims, so the rendered output under `personal/output/` is
**PII-free by construction**.

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; select by the structural marker, not `hits[0]`;
  copy a verbatim quote; keep all PII in `basis[]`; abstain rather than confabulate
  or leak.
