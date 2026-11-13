# Letter of Explanation Agent

This skill applies the shared answer-object contract
([`_contract.md`](_contract.md)) to letter of explanation questions — **read that
first.** The contract defines the answer object, the search → verbatim-quote →
ground → abstain loop, the PII-tier split, the abstention rule, and the critical
environment (drive everything through `corpus-crawler --json …` plus JSON parsing;
never bare `python` — use `.venv/bin/python` or `jq`). This file adds only what is
specific to this document: its scope, the baked query, the selection rule, and the
verbatim-quote loop. Also refer to [`../../skills/pdf/SKILL.md`](../../skills/pdf/SKILL.md)
for multimodal document processing guidelines.

## What this agent answers

When an applicant provides a **Letter of Explanation** to clarify application details, missing optional documentation, or special circumstances in Express Entry e-APR submissions. Evaluate both the document requirement and any critical document defects.

## The baked query

Bake this SHORT, high-signal query (2–4 tokens; the index ANDs every token, so keep
it short — never a chunk id, which drifts and fails closed):

> `explanation letter`

```bash
corpus-crawler --json search "explanation letter" --db corpus/index.db --limit 5
```

## The selection rule

Do **not** blindly take `hits[0]`. Resolve each hit in BM25 order and select the
**first** whose `result.chunk.text` contains the structural requirement phrase
**"letter of explanation"** within general e-APR document requirements (ignoring
topic-restricted chunks such as police certificate guidelines or specific birth/name-change chunks unless directly applicable to the specific question context).
If no hit contains it, abstain. Do NOT cite domain-mismatched chunks (e.g., birth certificate or name change chunks for employment or funds LOEs).

## Defect analysis

Audit the Letter of Explanation against primary evidence and IRCC rules. Defect evaluation must always be conducted and documented in `basis[]`, even if claims are abstained or grounded generically.

**Grounding & Non-Hallucination Rule**: Document ONLY defects that are explicitly present in the provided document text. Do NOT list hypothetical defects, do NOT include defect categories not observed in the document, and NEVER invent amounts, family relationships, or job titles.

Evaluate and explicitly commit observed findings in `basis[]` for:
- **Header & Content Mismatches**: Discrepancies between document headers, subject lines, listed attachments, and the body narrative (e.g., subject header referencing bank account/gift deeds while narrative body describes employment history).
- **Unsworn/Unnotarized Declarations**: Statements explicitly substituting an unsworn letter for legally required sworn statutory declarations (e.g., IMM 5409 common-law declaration, legal name change).
- **Unsubstantiated Financial Claims**: LOE claims acknowledging financial gifts or balance transfers without required donor bank trails, gift deeds, or donor source proof.
- **Contradictory Narratives**: LOE claims directly conflicting with official primary records (T4/NOA tax forms, employment reference letters, pay slips).

## The loop (by reference to the contract)

Follow the contract's loop exactly:

1. **Read the profile slice and document text** for applicability and defects. Perform a thorough defect audit; write all applicability details and observed defect findings in `basis[]` ONLY (do NOT list unobserved defect types or invent findings).
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
   and defect details in `basis[]` (never leaving `basis[]` empty if defects are present), and **ground** the answer by piping to `corpus-crawler --json
   ground`.

## The abstention rule

If the requirement cannot be grounded — the chunk does not resolve, or no verbatim
span exists — emit an `abstentions[]` entry with reason `not_in_corpus` and **no
claim**. Note: Abstaining on a grounded claim does NOT excuse omitting document defect evaluation; always record identified defects in `basis[]` when evaluating submitted LOE documents. NEVER confabulate a requirement or a quote.

## Worked example

The `quote` and `basis` values below are **placeholder tokens** — copy the real
verbatim span from `result.chunk.text` at runtime, and never paste a real name,
date, or amount.

```bash
# 1. List candidate hits (best-first). Per the selection rule, resolve each in
#    order and keep the FIRST whose text contains the marker
#    "letter of explanation" — do not assume hits[0].
corpus-crawler --json search "explanation letter" --db corpus/index.db --limit 5 \
  | jq -r '.result.hits[].chunk_id'

# 2. Resolve a candidate; keep this one only if its text contains the marker.
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Copy a verbatim substring of the matched chunk's text, then assemble ONE
#    generic claim and ground it. Read the envelope `ok` first, then branch on
#    result.verdict (per _contract.md).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"When may an applicant submit a Letter of Explanation?",
 "claims":[
   {"id":"letter-explanation-doc","text":"<generic PII-free requirement label>",
    "citations":["<relpath#NNN>"],"quote":"<verbatim span from result.chunk.text>"}],
 "basis":["<personal applicability and defect audit sentence with placeholder tokens>"],
 "abstentions":[],"prose":""}
JSON
```

Branch on the **envelope** then the **verdict**: read `ok` first; on `ok:true` read
`result.verdict`. Only `verdict:"pass"` (exit 0) means the claim grounded — then the
answer is rendered beside its verbatim quote, share-safety-scanned, and written to
the git-ignored `personal/output/` boundary. A `verdict:"fail"` (exit 1) renders and
writes nothing — drop the bad quote or abstain, never confabulate.

## PII discipline

The applicant's specific explanation and personal circumstances are **personal data** — keep them in `basis[]` ONLY. The grounding gate inspects `claims[]` only and the renderer writes only
the grounded, scanned claims, so the rendered output under `personal/output/` is
**PII-free by construction**.

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; select by the structural marker, not `hits[0]`;
  copy a verbatim quote; keep all PII and defect analysis in `basis[]`; abstain rather than confabulate or leak.
