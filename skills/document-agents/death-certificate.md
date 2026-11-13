# Death Certificate Agent

This skill applies the shared answer-object contract
([`_contract.md`](_contract.md)) to death certificate questions — **read that
first.** The contract defines the answer object, the search → verbatim-quote →
ground → abstain loop, the PII-tier split, the abstention rule, and the critical
environment (drive everything through `corpus-crawler --json …` plus JSON parsing;
never bare `python` — use `.venv/bin/python` or `jq`). This file adds only what is
specific to this document: its scope, the baked query, the selection rule, and the
verbatim-quote loop.

## What this agent answers

What document is required when an applicant's **marital status is widowed** — requested only in that case, to validate the death of a spouse or common-law partner. The generic requirement label (a death certificate or equivalent legal certificate) is the only thing that goes in `claims[]`.

## Field validation rules

Before issuing a claim, inspect and validate the document fields:
1. **Language & Translation**: If the document is not in English or French, verify both a certified translation and translation affidavit/stamp are present.
2. **Authenticity & Seals**: Verify Registration Number, Issuing Authority Seal, and Registrar Signature are present and valid (not blank or "N/A").
3. **Identity & Marital Status**: Cross-check Deceased Name and Relationship against the declared spouse in profile. Verify actual Marital Status Code in document/profile — do not assume "widowed" from question framing if status is MARRIED or identity is mismatched.

If any field validation fails, do not emit boilerplate policy claims; record the document defect and abstain.

## The baked query

Bake this SHORT, high-signal query (2–4 tokens; the index ANDs every token, so keep
it short — never a chunk id, which drifts and fails closed):

> `death certificate widowed status` 

```bash
corpus-crawler --json search "death certificate widowed status" --db corpus/index.db --limit 5
```

## The selection rule

Do **not** blindly take `hits[0]`. Resolve each hit in BM25 order and select the
**first** whose `result.chunk.text` contains the structural requirement phrase
**"marital status is listed as widowed"** — a non-volatile marker that uniquely lands the e-APR
document-requirements chunk for this document. If no hit contains it, abstain.

## The loop (by reference to the contract)

Follow the contract's loop exactly:

1. **Read profile slice and document fields** for applicability and field validation (verify translation, registration/seals, and identity/marital status match). Everything personal goes to `basis[]` ONLY.
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
5. **Emit one generic claim** (the requirement label only) if validation passes, put all personalization
   in `basis[]`, and **ground** the answer by piping to `corpus-crawler --json
   ground`.

## The abstention rule

Abstain (emit an `abstentions[]` entry with reason and **no claim**) if:
- The requirement cannot be grounded — chunk does not resolve or no verbatim span exists.
- Document validation fails — missing translation/affidavit for foreign language, missing seal/signature/registration number, or identity/marital status mismatch.

NEVER confabulate a requirement or a quote: a fabricated quote yields
`verdict:"fail"`, `reasons:["quote_not_in_chunk"]`, exit 1, and writes nothing.
Abstain rather than invent.

## Worked example

The `quote` and `basis` values below are **placeholder tokens** — copy the real
verbatim span from `result.chunk.text` at runtime, and never paste a real name,
date, or amount.

```bash
# 1. List candidate hits (best-first). Per the selection rule, resolve each in
#    order and keep the FIRST whose text contains the marker
#    "marital status is listed as widowed" — do not assume hits[0].
corpus-crawler --json search "death certificate widowed status" --db corpus/index.db --limit 5 \
  | jq -r '.result.hits[].chunk_id'

# 2. Resolve a candidate; keep this one only if its text contains the marker.
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Copy a verbatim substring of the matched chunk's text, then assemble ONE
#    generic claim and ground it. Read the envelope `ok` first, then branch on
#    result.verdict (per _contract.md).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"What document is required when an applicant is widowed?",
 "claims":[
   {"id":"death-cert-copy","text":"<generic PII-free requirement label>",
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

The deceased partner's name, the date and place of death, and the certificate itself are **personal data** — keep them in `basis[]` ONLY. The grounding gate inspects `claims[]` only and the renderer writes only
the grounded, scanned claims, so the rendered output under `personal/output/` is
**PII-free by construction**.

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; select by the structural marker, not `hits[0]`;
  copy a verbatim quote; keep all PII in `basis[]`; abstain rather than confabulate
  or leak.
