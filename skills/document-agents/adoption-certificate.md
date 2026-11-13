# Adoption Certificate Agent

This skill applies the shared answer-object contract
([`_contract.md`](_contract.md)) to adoption certificate questions — **read that
first.** The contract defines the answer object, the search → verbatim-quote →
ground → abstain loop, the PII-tier split, the abstention rule, and the critical
environment (drive everything through `corpus-crawler --json …` plus JSON parsing;
never bare `python` — use `.venv/bin/python` or `jq`). This file adds only what is
specific to this document: its scope, the baked query, the selection rule, and the
verbatim-quote loop.

## What this agent answers

What document is required when a **dependent child's status is adopted** — requested only in that case. The generic requirement label (the adoption certificate or legal adoption papers) and explicit document verification verdict (`meets_requirements` or `defective` with specific defect reasons) go in `claims[]`.

## Document verification checklist

When reviewing submitted adoption documents and attached narrative notes, verify the following four criteria:
1. **Full Court Adoption Order**: Confirm a final judicial court adoption order/decree is present. Flag as defective if only a Civil Status Registry extract or birth-registration extract is provided with no court order.
2. **Severance of Biological Ties**: Confirm legal status is full legal adoption severing biological parental ties. Flag as defective if status is temporary legal guardianship/custody retaining biological rights.
3. **Provincial Letter of No Objection**: For foreign or non-accredited jurisdictions, require a Provincial Letter of No Objection (LNO). Flag as defective if LNO is missing or listed as N/A.
4. **Consent and Home Study**: Confirm verified biological parent consent and a completed Home Study Report. Flag as defective if consent is unverified or home study is missing/N/A.

## The baked query

Bake this SHORT, high-signal query (2–4 tokens; the index ANDs every token, so keep
it short — never a chunk id, which drifts and fails closed):

> `adoption certificate adopted child`

```bash
corpus-crawler --json search "adoption certificate adopted child" --db corpus/index.db --limit 5
```

## The selection rule

Do **not** blindly take `hits[0]`. Resolve each hit in BM25 order and select the
**first** whose `result.chunk.text` contains the structural requirement phrase
**"dependent child status is listed as adopted"** — a non-volatile marker that uniquely lands the e-APR
document-requirements chunk for this document. If no hit contains it, abstain.

## The loop (by reference to the contract)

Follow the contract's loop exactly:

1. **Read the profile slice and document content** (including narrative notes/detailed sections) for applicability and defect verification against the checklist. Everything personal goes to `basis[]` ONLY.
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
5. **Emit one generic claim** (the requirement label and explicit verification verdict), put all personalization
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
#    "dependent child status is listed as adopted" — do not assume hits[0].
corpus-crawler --json search "adoption certificate adopted child" --db corpus/index.db --limit 5 \
  | jq -r '.result.hits[].chunk_id'

# 2. Resolve a candidate; keep this one only if its text contains the marker.
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Copy a verbatim substring of the matched chunk's text, then assemble ONE
#    generic claim and ground it. Read the envelope `ok` first, then branch on
#    result.verdict (per _contract.md).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"What document is required when a dependent child is adopted?",
 "claims":[
   {"id":"adoption-cert-copy","text":"<generic PII-free requirement label>",
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

The child's name, the adoption date and jurisdiction, and the papers themselves are **personal data** — keep them in `basis[]` ONLY. The grounding gate inspects `claims[]` only and the renderer writes only
the grounded, scanned claims, so the rendered output under `personal/output/` is
**PII-free by construction**.

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; select by the structural marker, not `hits[0]`;
  copy a verbatim quote; keep all PII in `basis[]`; abstain rather than confabulate
  or leak.
