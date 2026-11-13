# Employment / Reference Letter Agent

This skill teaches you how to use the shared answer-object contract
([`_contract.md`](_contract.md)) for employment / reference-letter questions —
**read that first.** The contract defines the answer object, the search →
verbatim-quote → ground → abstain loop, the PII-tier split, the abstention rule,
and the critical environment (drive everything through `corpus-crawler --json …`
plus JSON parsing; never bare `python` — use `.venv/bin/python` or `jq`). This
file adds only what is specific to the employment / reference letter: the scope
boundary against the job-offer letter, the baked query, and the per-element
verbatim-quote loop.

## What this agent answers

What an Express Entry **proof-of-work-experience reference / experience letter**
must contain, as stated by the corpus. This is the letter from the employer that
supports the applicant's **skilled work-experience** claim, and it is a mandatory
document for each declared work experience. The **generic requirement labels** —
letterhead, applicant name, company contact details, signatory, positions held,
and the employment details — are the only things that go in `claims[]`. The
applicant's actual employer name, employment dates, work hours, and salary are
**personal data**: they decide applicability and belong in `basis[]` ONLY. They
never appear in a claim, a quote, or a citation.

## Do not confuse this with the arranged-employment job-offer letter

The corpus holds **two different employer letters**, and they are NOT
interchangeable:

- **This agent** verifies the *proof-of-work-experience* reference / experience
  letter — the mandatory document supporting each declared work experience.
- A **separate** document type is the *arranged-employment job-offer* letter (the
  "letter of offer from the employer" item, plus the federal-skilled-workers
  arranged-employment points page). That letter adds different elements — an
  expected start date and a continuous, paid, full-time minimum — and belongs to
  the existing `job-offer` checklist item, **not** this agent. It is only required
  when the applicant claims arranged-employment points.

NEVER cite an arranged-employment job-offer chunk from this agent — that would
verify the wrong document's elements. The baked query below is chosen precisely
because it uniquely lands the work-experience-letter requirements and never
returns an arranged-employment relpath; assert that **no** arranged-employment id
appears in your hits before you resolve one.

## The baked query

Bake this SHORT, high-signal query (the index ANDs every token, so keep it 2–4
tokens — never a chunk id, which drifts and fails closed):

> `reference letter company letterhead`

```bash
corpus-crawler --json search "reference letter company letterhead" \
  --db corpus/index.db --limit 5
```

This returns exactly one hit — the Express Entry completeness-check
work-experience-letter requirements chunk — and never an arranged-employment
relpath. Every required element lives in that one chunk, so a single resolve can
ground every element-claim.

> Copy each quote VERBATIM at runtime. This chunk uses a **curly apostrophe**
> (`’`, the right single quote) in possessives like `applicant’s` / `company’s`,
> and the gate normalizes whitespace + case ONLY — it does not normalize
> apostrophes. A straight-apostrophe retype fails `quote_not_in_chunk`; copy the
> exact bytes from `result.chunk.text`.

## The per-element loop (by reference to the contract)

Follow the contract's loop exactly. What is specific here: this letter has
**several required elements that all live in the one resolved chunk**, so you
resolve once and then copy a **separate verbatim quote for each element**,
emitting **one generic, PII-free claim per element**.

1. **Read the profile slice** for applicability (which declared work experience
   this letter supports) and audit the submitted document for mandatory completeness:
   check for letterhead/contact info, weekly work hours/status, salary/benefits,
   and whether job duties are copied verbatim from NOC lead statements. Record all
   observed document defects in `basis[]` ONLY.
2. **Search** with the baked query. Read `result.hits`, confirm the hit is the
   work-experience requirements chunk and NOT an arranged-employment relpath.
3. **Resolve** the chosen hit to its exact stored chunk:
   ```bash
   corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db
   ```
   Read `result.found` and `result.chunk.text` (the verbatim span — never the
   display-only `snippet`). A miss is `found:false` → abstain.
4. **For EACH required element, copy a SEPARATE verbatim substring** of
   `result.chunk.text` into that element's `quote`. The elements to locate and
   quote are:
   - **company letterhead** — the official-document-on-letterhead element;
   - **applicant name** — the element requiring the applicant's name;
   - **company contact** information — address, telephone number and email;
   - **signatory** — the name, title and **signature** of the immediate
     supervisor or personnel officer;
   - all **positions** held while employed at the company;
   - the employment **details** — job title, **duties** and responsibilities, job
     status, dates worked, work **hours** per week, and annual **salary** plus
     benefits.

   Copy each span at runtime, verbatim (curly apostrophes included); never
   paraphrase, and never inline a corpus span or a requirement value into this
   file.
5. **Emit one generic claim per element** (the requirement label only) and put all
   personalization and document defects in `basis[]`. **Assemble** every element-claim
   into a single answer object and **ground** it by piping to `corpus-crawler --json ground`.

## Document audit & defect checklist (recorded in basis[])

When auditing the submitted employment reference letter against mandatory corpus requirements, audit all four critical defect areas and record any observed deficiencies in `basis[]`:

- **Missing Letterhead / Contact**: Check if official company letterhead or contact details (address, phone, email) are omitted from the document.
- **Missing Working Hours / Status**: Check if weekly work hours or employment status (full-time vs part-time) are missing.
- **Missing Compensation / Benefits**: Check if annual salary or monetary benefits are missing.
- **Verbatim NOC Duties**: Check if listed duties are copied verbatim from official NOC lead statements or duty descriptions rather than describing actual, personalized duties.

## The abstention rule

If any element cannot be grounded — the chunk does not resolve, or no verbatim
span exists for that element — emit an `abstentions[]` entry with reason
`not_in_corpus` and **no claim** for that element. NEVER confabulate a requirement
or a quote: a fabricated quote yields `verdict:"fail"`,
`reasons:["quote_not_in_chunk"]`, exit 1, and writes nothing. Abstain rather than
invent.

## Worked example

The `quote` fields below are **placeholder tokens** — you copy the real verbatim
span from `result.chunk.text` at runtime (curly apostrophes included). The
`basis[]` values are placeholder tokens too; never paste a real name, date, or
amount.

```bash
# 1. Land the work-experience requirements chunk; assert it is NOT arranged-employment.
corpus-crawler --json search "reference letter company letterhead" \
  --db corpus/index.db --limit 5 \
  | .venv/bin/python -c "import json,sys
d=json.load(sys.stdin)
hits=d['result']['hits']
top=hits[0]['chunk_id'] if hits else None
assert top and 'arranged-employment' not in top, hits
print(top)"

# 2. Resolve once; copy a SEPARATE verbatim substring of result.chunk.text for
#    each element at runtime (keep the curly apostrophes — do not retype them).
corpus-crawler --json search --cite "<chunk_id>" --db corpus/index.db \
  | jq -r '.result.chunk.text'

# 3. Assemble ONE generic claim per element and ground the whole answer. Read the
#    envelope `ok` first, then branch on result.verdict (per _contract.md).
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"What must an Express Entry employment / reference letter contain?",
 "claims":[
   {"id":"letterhead","text":"<generic label: the letter must be on company letterhead>",
    "citations":["<relpath#NNN>"],"quote":"<verbatim letterhead span from result.chunk.text>"},
   {"id":"identity-contact-signatory","text":"<generic label: applicant name, company contact, signatory>",
    "citations":["<relpath#NNN>"],"quote":"<verbatim span copied from result.chunk.text>"},
   {"id":"positions-held","text":"<generic label: all positions held at the company>",
    "citations":["<relpath#NNN>"],"quote":"<verbatim positions span from result.chunk.text>"},
   {"id":"employment-details","text":"<generic label: job title, duties, status, dates, hours, salary>",
    "citations":["<relpath#NNN>"],"quote":"<verbatim details span from result.chunk.text>"}],
 "basis":["Applicant declares skilled work experience at <employer> starting <start-date> earning <salary>.",
          "Document Audit: Check letterhead/contact info, weekly work hours/status, salary/benefits, and non-verbatim NOC duties."],
 "abstentions":[],"prose":""}
JSON
```

Branch on the **envelope** then the **verdict**: read `ok` first; on `ok:true`
read `result.verdict`. Only `verdict:"pass"` (exit 0) means every element-claim
grounded — then the answer is rendered beside its verbatim quotes,
share-safety-scanned, and written to the git-ignored `personal/output/` boundary.
A `verdict:"fail"` (exit 1) renders and writes nothing; on a fail you must **NOT**
present the failing element as verified — drop the bad quote or abstain for that
element, never confabulate.

## PII discipline (employer / applicant / dates / salary stay in basis[])

The employer's name, the applicant's name, employment dates, work hours, and
salary are **PII**. They must appear ONLY in `basis[]` (or the local profile) —
**never** in `claims[].text`, `quote`, or `citations`. The grounding gate inspects
`claims[]` only and the renderer writes only the grounded, scanned claims, so the
rendered output under `personal/output/` is **PII-free by construction**. Use
placeholder tokens like `<employer>`, `<start-date>`, and `<salary>` for any
personal example — never a real name, date, or amount, and never an inlined
requirement value.

## Rules recap

- Plain Markdown, no front-matter, no per-CLI tooling — everything is
  `corpus-crawler --json …` plus JSON parsing (never bare `python`; use
  `.venv/bin/python` or `jq`).
- This is the *work-experience* reference letter — NEVER cite the
  arranged-employment job-offer chunks.
- Bake the query, not a chunk id; copy a separate verbatim quote (curly
  apostrophes included) for each element; keep all PII in `basis[]`; abstain
  rather than confabulate or leak.
