# Medical (IME) Agent

This skill teaches you how to use the shared answer-object contract
([`_contract.md`](_contract.md)) for medical / immigration-medical-examination
(IME) questions — **read that first.** The contract defines the answer object, the
search → verbatim-quote → ground → abstain loop, the PII-tier split, the
abstention rule, the "no inlined volatile values" rule, and the critical
environment (drive everything through `corpus-crawler --json …` plus JSON parsing;
never bare `python` — use `.venv/bin/python` or `jq`). This file adds only the
medical specifics: the baked query, the generic claim, and the **volatile-date
callout** below — the reason this agent is the canonical test of the
no-inlined-values rule.

## What this agent answers

That an applicant must undergo an immigration medical examination, subject to a
corpus-stated, **time-limited public-policy exemption window**, and whether the
medical submission satisfies standard validity requirements or exhibits defects. The agent evaluates:
- **Upfront proof requirement**: presence of required IMM1017B form or eMedical receipt.
- **Panel physician designation**: whether the exam was performed by a designated panel physician.
- **Furtherance status**: whether medical clearance is complete versus blocked by unresolved furtherance/pending specialist reports.

Generic requirement and defect criteria labels go in `claims[]`. The applicant's own exam status, physician details, identifiers, or eligibility belong in `basis[]` ONLY — never in a claim, a quote, or a citation.

## ⚠ The volatile-date callout (read this before you write anything)

The corpus describes the IME exemption as a **dated public-policy window** and a
re-use window for a prior exam. **Those values are VOLATILE** — IRCC extends and
revises them, and any value hand-typed into this file rots and lies the moment the
policy changes.

Therefore:

- **NEVER write the exemption date, the policy window, or any duration into this
  file or into `prose`.** No month, no year, no "valid for N …". The spec body
  states the requirement *structurally* and lets the corpus carry every value.
- **The date is reproduced ONLY as a quoted span at runtime.** If the requirement
  you are grounding involves the time-limited exemption, the claim's `quote` MUST
  be a verbatim substring of the resolving chunk's `result.chunk.text` that
  *includes the dated span exactly as it appears there* — copied at runtime,
  never retyped.
- This is enforced downstream by the Plan 05 grep gate, which asserts no
  date / number / window appears in any agent body. The honest place for the date
  is the grounded, cited `quote` — nowhere else.

## The baked query

Bake these SHORT, high-signal queries:

- Standard IME requirement / exemption: `immigration medical examination permanent residence`
- Panel physician requirement check: `panel physician designation medical examination`
- Upfront proof / receipt check: `upfront medical examination receipt IMM1017B`
- Unresolved furtherance check: `medical examination furtherance pending report`

```bash
corpus-crawler --json search "immigration medical examination permanent residence" \
  --db corpus/index.db --limit 5
```

This surfaces the permanent-residence IME pages. Do **not** blindly take
`hits[0]` — scan the top hits in order, resolve each (`--json search --cite <chunk_id>`),
and select the hit whose `result.chunk.text` actually carries the relevant rule, exemption, or defect standard. If evaluating profile defects (non-panel physician, missing receipt, unresolved furtherance), search the matching targeted query to ground the rule. If no top hits match, abstain with reason `not_in_corpus`.

## The loop (by reference to the contract)

1. **Read the profile slice** to evaluate document validity and detect defects:
   - **Missing upfront proof**: Verify whether IMM1017B form or eMedical receipt is attached.
   - **Non-designated physician**: Check if the examining doctor/clinic is unregistered or non-designated.
   - **Unresolved furtherance**: Check for pending specialist reports, sputum cultures, abnormal X-rays, or incomplete assessments.
   *Crucial*: Never assert in `basis[]` that proof was provided, the physician was designated, or clearance is complete if the profile indicates otherwise. Record all observed profile facts and specific defect findings accurately in `basis[]` ONLY.
2. **Search** with the appropriate baked query for the core requirement or defect standard. Read `result.hits`, best-first, then **scan the top hits and resolve each until one's `result.chunk.text` contains the rule span**. Select that hit; if no hit carries it, abstain.
3. **Resolve** the chosen hit to its exact stored chunk:
   ```bash
   corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db
   ```
   Read `result.found` and `result.chunk.text` (the verbatim span — never the
   display-only `snippet`). A miss is `found:false` → abstain.
4. **Copy a VERBATIM substring** of `result.chunk.text` into the claim's `quote`.
   Copy it at runtime; never paraphrase, and never inline a corpus span into this
   file. If the requirement involves the time-limited exemption, the copied span
   MUST include the dated window exactly as it appears in `result.chunk.text` —
   the date lives in the quote, never in the body.
5. **Assemble and ground.** Emit generic, non-PII claims (requirement, panel physician rule, upfront receipt rule, or furtherance status requirement), keep applicant details in `basis[]`, and pipe to the gate. If nothing resolves, abstain with reason `not_in_corpus`.

## Worked example

```bash
# 1. Search, then scan the top hits and select the FIRST whose resolved chunk
#    text actually contains the exemption or defect rule span you must quote.
#    Abstain if none of the top hits carries it.
corpus-crawler --json search "immigration medical examination permanent residence" \
  --db corpus/index.db --limit 5 \
  | .venv/bin/python -c "import json,subprocess,sys
d=json.load(sys.stdin)
hits=d['result']['hits']
marker='temporary public policy'  # structural exemption phrase — never a date
def chunk_text(cid):
    out=subprocess.run(['corpus-crawler','--json','search','--cite',cid,
                        '--db','corpus/index.db'],capture_output=True,text=True).stdout
    r=json.loads(out)['result']
    return r['chunk']['text'] if r.get('found') else ''
sel=next((h['chunk_id'] for h in hits if marker in chunk_text(h['chunk_id'])),None)
print(sel or 'ABSTAIN: not_in_corpus')"

# 2. Resolve the chosen chunk_id, then copy a substring of result.chunk.text
#    into the claim quote (do this at runtime, verbatim). If the requirement is
#    the time-limited exemption, the copied span MUST include the dated window
#    exactly as it appears here — never retype it into this file.
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Ground ONE generic, PII-free claim. The dated window rides inside the
#    verbatim quote; the applicant's exam status stays in basis[].
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"Does the applicant need an immigration medical examination?",
 "claims":[{"id":"medical-exam",
            "text":"<generic requirement label: an IME is required, subject to the corpus-stated exemption window>",
            "citations":["<relpath#NNN>"],
            "quote":"<verbatim span copied from result.chunk.text, including the dated exemption window exactly as stored>"}],
 "basis":["<applicant exam status / prior-IME identifier / exemption eligibility — PII, never a claim>"],
 "abstentions":[],"prose":""}
JSON
```

If nothing resolves, emit an abstention instead of a claim:

```json
{"question":"Does the applicant need an immigration medical examination?",
 "claims":[],
 "basis":["<applicant exam status / prior-IME identifier>"],
 "abstentions":[{"text":"<note: the IME requirement did not resolve in the corpus>","reason":"not_in_corpus"}],"prose":""}
```

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- Bake the query, not a chunk id; quote every requirement value verbatim from the
  corpus; abstain rather than confabulate.
- Evaluate profile conditions against medical defect rules (missing upfront receipt, non-designated doctor, unresolved furtherance).
- **NEVER inline the exemption date, the policy window, or any duration** — it is
  VOLATILE and lives ONLY inside a grounded, cited `quote`. The body states the
  requirement structurally; the corpus carries the value.
