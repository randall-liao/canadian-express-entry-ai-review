# Pitfalls Research

**Domain:** v4.0 CRS Profile ↔ Document Substantiation Auditor for a grounded, PII-separated Canadian Express Entry e-APR guidance system  
**Researched:** 2026-07-05  
**Confidence:** HIGH for project-specific trust-boundary, PII, grounding, and cited CRS/admissibility examples from the local authoritative corpus; MEDIUM for OCR/rendering dependency behavior because exact failure modes vary by user OS and document quality.

> **Roadmap note:** v4.0 introduces the first deliberately non-grounded step: automated extraction from the applicant's own documents. The milestone must keep the existing two invariants intact: (1) every immigration-rule/admissibility claim is still corpus-grounded and fail-closed, and (2) all PII stays in the local vault only. The central design rule is: **unconfirmed extracted values are never allowed to produce `SUBSTANTIATED`.**

## Critical Pitfalls

### Pitfall 1: Silent extraction misreads become grounded-looking false confidence

**What goes wrong:**
The extractor reads a document incorrectly, then the auditor treats the misread value as fact. Examples: IELTS/TEF ability scores normalize to the wrong CLB; "CLB 8" becomes "CLB 9"; a result date, issue date, expiry date, birth date, or employment date is swapped; an NOC/TEER code is read from a footer or old job title; a spouse value is attached to the principal applicant; an OCR table column shift changes listening vs reading. Downstream rules can still be perfectly cited, so the final report looks authoritative while substantiating the wrong evidence.

**Why it happens:**
Grounding validates the rule quote, not the user's document value. Rendering/OCR/extraction is probabilistic and layout-sensitive, while the existing gate only knows whether an official corpus quote resolves. If the pipeline has no explicit "unconfirmed input" state, a bad extraction silently crosses the trust boundary.

**How to avoid:**
- Treat extraction as an **evidence proposal**, never as accepted fact. Every extracted field starts as `unconfirmed`.
- Store per-field provenance in the vault: `document_id`, file hash, page number, crop/coordinate or text span, extractor/parser version, raw extracted text, normalized value, confidence/quality flags, and confirmation status.
- Make the confirm-what-I-read checkpoint **field-level**, not document-level. Show the user the raw value, normalized value, affected CRS factor, source page/crop, and the claimed profile value side by side.
- Downstream audit must fail closed: `unconfirmed`, `missing`, `ambiguous`, `conflicting`, `low_quality`, or `stale_confirmation` evidence can only produce `GAP` or `AT-RISK`, never `SUBSTANTIATED`.
- Require the auditor contract to include `evidence_status:"confirmed"` for every value-bearing substantiation. Make this a deterministic precondition before rule grounding even runs.
- Add adversarial fixtures: CLB 8 vs CLB 9 boundary, IELTS listening/reading column swap, date format ambiguity, stale language-test date, old NOC 2016 code vs NOC 2021 TEER, and a multi-page work letter with totals split across pages.
- Preserve user corrections. Re-running extraction may propose new values, but must not silently overwrite confirmed corrections.

**Warning signs:**
Audit tests pass with unconfirmed extractor output; the audit JSON has values but no confirmation state; there is a "confirm all" button with no per-field review; extracted values lack page/source coordinates; the extractor stores only normalized values and discards raw text; the auditor can emit `SUBSTANTIATED` when the confirmation table is empty; user corrections disappear after re-extraction.

**Phase to address:**
**Phase 2 — Document extraction + confirm-what-I-read.** Phase 4 auditors must not start until Phase 2 exposes a confirmed-evidence contract and fail-closed fixtures.

---

### Pitfall 2: PII leaks through the new vault/image/OCR surface instead of the old `personal/` path

**What goes wrong:**
v4.0 adds raw PDFs, rendered page images, OCR text, extracted values, cropped thumbnails, vault DB files, WAL/SHM sidecars, import manifests, error logs, screenshots, and private audit reports. Any one of these can leak passport pages, language scores, employers, dates, names, UCI/application numbers, addresses, or document numbers into the repo, corpus, test fixtures, `.planning/`, `reports/`, CI artifacts, shell history, exception messages, or git history.

**Why it happens:**
The existing PII boundary was designed for profile/checklist data and PII-free rendered outputs. Document extraction creates many more artifact types, including binary images and temporary files that developers often forget to route through the same guardrails.

**How to avoid:**
- Define one vault root, e.g. `personal/vault/` or `$PR_CANDIDATE_VAULT`, and make it the **only** allowed write target for raw documents, images, OCR text, extracted values, private reports, logs, temp files, and caches.
- Extend `.gitignore` and publish-safety checks before extraction lands: reject tracked vault paths, raw document extensions, rendered image extensions, OCR/extraction JSON, vault DB sidecars, temp dirs, and private report names.
- Add a path guard used by all v4.0 writers: refuse to write if the target is inside `corpus/`, `.planning/`, `reports/`, `skills/`, `crawler/eval/`, or any git-tracked path.
- Put temporary render/OCR directories under the vault, not the system temp directory; clean them after use; set restrictive file permissions where practical.
- Keep JSON envelope errors PII-free. Do not interpolate OCR source lines, file contents, extracted values, or OS exception snippets into `stdout`/`stderr`.
- Keep all tracked tests synthetic. Use fake PDFs/images with obviously fake values; never crop real applicant documents into fixtures.
- Run the existing publish-safe gate and gitleaks/PII scans after adding v4.0 patterns. Also test `git add -A` cannot stage vault artifacts.

**Warning signs:**
`git status` shows `.pdf`, `.png`, `.jpg`, `.tif`, `.sqlite`, `.db-wal`, OCR JSON, or private audit reports; an exception message includes a passport name or language score; `TemporaryDirectory()` creates render artifacts outside the vault; tests include realistic personal dates or document numbers; a private report lands in `reports/`; the corpus DB contains user-document text.

**Phase to address:**
**Phase 1 — Candidate vault + guardrails.** The vault path guard and expanded publish-safe/gitleaks patterns must exist before any real document is rendered once.

---

### Pitfall 3: The candidate vault boundary is blurred with the authoritative corpus boundary

**What goes wrong:**
User document text is indexed into `corpus/index.db`, stored under `corpus/`, or represented as a normal corpus citation. The auditor then mixes authoritative-rule citations with private evidence pointers. This breaks both invariants: PII enters the shareable retrieval surface, and evidence from the applicant's documents can be mistaken for official authority.

**Why it happens:**
Both sides are "local SQLite-like stores" and both need search/retrieval. Reusing the corpus indexer for candidate documents is tempting but unsafe: the corpus is PII-free authority; the vault is private evidence.

**How to avoid:**
- Enforce a two-store invariant:
  - `corpus/index.db` is read-only, authoritative, PII-free, and citeable.
  - `personal/vault/candidate.db` is private, evidence-bearing, git-ignored, and never citeable as authority.
- Use distinct identifiers: `citation_id` only for corpus chunks; `evidence_id` only for vault documents/fields.
- If candidate-document search/FTS is added, keep it inside the vault DB and label it "private evidence search"; never expose it through `corpus-crawler --json search` as an authoritative source.
- The audit output should carry both: a corpus-grounded rule citation and a private evidence pointer. `SUBSTANTIATED` requires both, but they are not interchangeable.
- Add tests that fail if any candidate document text, extracted value, image path, or vault DB file appears under `corpus/` or in tracked fixtures.

**Warning signs:**
User docs get `chunk_id` values; a private document path appears in `claims[].citations`; `corpus/index.db` changes after importing candidate files; a rule citation points to a vault record; an evidence pointer looks like `relpath#NNN`; an auditor searches user docs with the same command used for official rules.

**Phase to address:**
**Phase 1 — Vault schema and path contracts**, then re-verified in **Phase 3 — CRS-rule registry** and **Phase 4 — auditor contract**.

---

### Pitfall 4: Volatile CRS/admissibility rules are baked into agents instead of grounded at run time

**What goes wrong:**
Agents hardcode values that change or depend on date/context: language-test validity windows, ECA validity, NOC 2021/TEER eligibility, point tables, spouse vs no-spouse tables, skill-transferability caps, job-offer/arranged-employment policy changes, and accepted proof requirements. The output remains confidently wrong after IRCC changes guidance or the corpus contains both current and historical pages.

**Why it happens:**
CRS tables feel like stable constants, and agent prompts are easier to write with examples. But this project deliberately avoids hand-typed rule values: the local corpus is the source of truth, and even that corpus needs freshness metadata and source selection.

**How to avoid:**
- Build a **grounded CRS-rule registry** whose entries contain source family, query, marker/selection rule, volatility level, and expected rule type; do not store final volatile numbers as hand-maintained constants.
- At audit time, resolve the registry entry through the local corpus, copy the verbatim rule span, and pass it through the existing grounding gate.
- Add static checks for v4.0 agents/registry prose: no hand-typed validity windows, CRS point amounts, calendar-effective dates, NOC/TEER lists, or chunk IDs except inside test names or source summaries explicitly marked as research.
- Give volatile fields strict staleness budgets and surface `crawl_date` / source URL in the private report.
- Separate "job offer may matter for program eligibility" from "job offer gives CRS points"; the corpus currently includes a current job-offer page stating job-offer CRS points were removed, while historical/year-end pages still describe old point regimes.
- Require current-rule source priority. For current CRS/admissibility, prefer current guidance/Ministerial Instructions/PDIs over year-end reports and historical summaries.

**Warning signs:**
A grep finds values like validity windows, old arranged-employment points, NOC/TEER categories, or effective dates in agent files; the registry cites a year-end report for a current rule; a test passes without `corpus/index.db`; source `crawl_date` is hidden; a rule entry has a value but no source query/marker; an old source and current source conflict with no warning.

**Phase to address:**
**Phase 3 — Grounded CRS-rule registry.** Phase 4 auditors should be thin consumers of this registry, not independent rule authors.

---

### Pitfall 5: Over-claiming `SUBSTANTIATED` beyond what the corpus and gate can prove

**What goes wrong:**
The auditor says a factor is `SUBSTANTIATED` when it has only proven that an official rule exists. For example, a cited rule can ground that work experience must match NOC lead statement/main duties, but the keyword corpus and substring gate cannot semantically prove the applicant's duties actually match the NOC. Similar gaps exist for ECA equivalency nuance, employment-letter semantic duties, genuine relationship facts, and whether a particular document is authentic. The tool starts sounding like legal/eligibility advice.

**Why it happens:**
The existing grounding gate verifies citation resolvability and verbatim quote presence, not semantic entailment. v4.0 adds private evidence, making it easy to conflate "the rule is grounded" with "the user's document conclusively satisfies the rule."

**How to avoid:**
- Define `SUBSTANTIATED` narrowly: confirmed extracted evidence + required document presence + a corpus-grounded admissibility/threshold rule all align for a factor that can be checked deterministically.
- Use `AT-RISK` whenever semantic judgment is required. Example: "reference letter contains duties text and claimed NOC/TEER was confirmed, but semantic NOC-duty fit requires human review."
- Keep "not legal advice" and "misrepresentation-risk screening, not eligibility guarantee" framing in every private report.
- Make each verdict carry a machine-readable reason category: `deterministic_match`, `missing_evidence`, `unconfirmed_evidence`, `rule_not_found`, `semantic_review_required`, `conflicting_evidence`, `stale_rule`.
- Keep PII evidence out of `claims[]`; corpus claims remain generic and cited, while private evidence lives in vault-only fields.
- Add negative tests where the corpus grounds the rule but the evidence is insufficient; expected verdict is `AT-RISK` or `GAP`, never `SUBSTANTIATED`.

**Warning signs:**
Report prose says "you are eligible," "safe," "approved," or "no misrepresentation risk"; `SUBSTANTIATED` appears without a confirmed evidence pointer; a cited rule quote is treated as proof of the applicant's facts; no verdict category indicates semantic-review limits; work-experience NOC fit is treated as automatic from job title alone.

**Phase to address:**
**Phase 3 — Verdict semantics and registry contract**, enforced in **Phase 4 — modular auditor agents**.

---

### Pitfall 6: CRS scoring logic is naively summed and misses caps, combinations, and spouse/per-ability distinctions

**What goes wrong:**
The auditor recomputes or reconciles CRS factors incorrectly: it uses the no-spouse table for an accompanying-spouse case, averages language abilities instead of checking each ability, treats one CLB 9 as "CLB 9 or more on all four abilities," double-counts skill-transferability combinations, ignores the 50-point subcaps and 100-point transferability cap, applies obsolete job-offer points, mixes principal-applicant and spouse evidence, or conflates claimed total CRS with factor substantiation.

**Why it happens:**
CRS is table-driven but not flat. Some factors are per ability, some are paired combinations, some cap across multiple subfactors, and some depend on accompanying-spouse status or current policy. LLM-authored agent prose is a poor place to implement arithmetic.

**How to avoid:**
- Build deterministic CRS logic outside agent prompts: factor IDs, applicant role, spouse/accompanying status, per-ability language records, date-aware validity, combination rules, subcaps, total caps, and "claimed vs substantiated" ledgers.
- Source tables and thresholds from the CRS-rule registry at run time; agents should not independently calculate from hand-written tables.
- Represent language as four separate abilities plus test type/date. Any "all abilities" rule must compute minimum/across-all, not average.
- Represent skill-transferability combinations explicitly: education×language, education×Canadian-experience, foreign-experience×language, foreign-experience×Canadian-experience, certificate×language, then apply documented caps.
- Treat job-offer/arranged-employment as a volatile factor with current-rule selection and a separate eligibility-vs-CRS-points distinction.
- Add golden fixtures around boundary cases: CLB 8/9, one ability below threshold, spouse vs no spouse, overlapping transferability combinations, capped totals, and stale/removed job-offer points.

**Warning signs:**
The report has only one total score and no per-factor ledger; there is a single `clb` field instead of four abilities; spouse status is ignored; skill transferability subtotals exceed caps; an arranged-employment factor still adds obsolete points; the auditor's math lives in markdown agent instructions; changing one ability does not alter transferability verdicts.

**Phase to address:**
**Phase 3 — CRS-rule registry + deterministic CRS logic**, then **Phase 4 — auditor pack** consumes the tested logic.

---

### Pitfall 7: Current-rule retrieval selects historical or adjacent-but-wrong chunks

**What goes wrong:**
FTS returns a relevant-looking but wrong source: a year-end report describing historical arranged-employment points, a PDI for a different program, an old NOC transition page, a job-offer letter chunk instead of work-experience reference-letter requirements, or a generic CRS calculator page when the Ministerial Instructions are needed. The quote is real, so the grounding gate passes, but the selected authority is not the right authority for the current factor.

**Why it happens:**
FTS5 keyword retrieval proves lexical match, not applicability. The existing v3.1 agents solved this with short queries plus non-volatile marker selection; v4.0 needs the same discipline for CRS factors, especially where the corpus intentionally contains historical and current documents.

**How to avoid:**
- Each registry entry must define allowed source families, disallowed historical families where appropriate, a selection marker, and applicability filters.
- Never use `hits[0]` blindly for CRS rules. Resolve candidate hits in BM25 order, inspect text/metadata, and select only a chunk containing the expected non-volatile marker.
- Store and test `(query, marker, expected relpath family, quote)` triples for every CRS factor, mirroring the v3.1 retrieve-what-you-cite proof.
- Add conflict detection: if current guidance says a factor changed but older corpus pages still mention old values, emit `AT-RISK`/maintenance warning until the registry source priority is explicit.
- Use source type deliberately: guidance for applicant-facing requirements, PDIs for officer assessment/completeness, Ministerial Instructions for CRS point mechanics, IRPR/IRPA for legal authority.

**Warning signs:**
Registry entries have only query strings; tests only prove citations resolve, not that the agent's own query retrieves them; current job-offer rules cite a year-end report; a work-experience auditor cites the arranged-employment job-offer chunk; chunk IDs are baked in; there is no source-family allowlist.

**Phase to address:**
**Phase 3 — Grounded CRS-rule registry.** This is the bridge between keyword retrieval and safe factor-specific auditing.

---

### Pitfall 8: Multi-document aggregation is treated as a single-document check

**What goes wrong:**
The auditor checks each uploaded document independently but misses the factor-level aggregate: multiple work letters need combined duration/hours and non-overlap handling; education points may require multiple credentials and ECAs; first/second language designation must match the claimed profile; spouse documents must attach to the spouse factor; proof for sibling, Canadian study, nomination, or arranged employment may span several documents. The report says every document looks okay, but the claimed factor is still not substantiated.

**Why it happens:**
The existing document-agent pack is per document type. CRS factors are cross-document claims. v4.0 must pivot from "does this document have requirements?" to "does the evidence set substantiate this claimed factor?"

**How to avoid:**
- Model factor ledgers separately from document records. A factor verdict consumes one or more evidence records and produces one factor-level conclusion.
- Add aggregation primitives: date intervals, hours/week, full-time equivalent, role/applicant owner, credential grouping, test attempt grouping, issuer, and document type.
- Detect overlap and conflicts instead of "latest wins." Examples: two jobs overlapping full time, two language tests with different first-language designation, a profile claims two credentials but only one valid ECA is confirmed.
- Require per-factor auditors to cite both the rule and the exact evidence records used for the aggregate.
- Make "document-level pass" insufficient for `SUBSTANTIATED`; factor-level aggregate must pass too.

**Warning signs:**
Each document gets a verdict but there is no factor ledger; work experience months are summed without interval overlap checks; education points are inferred from the highest credential only; multiple language tests are merged ability-by-ability; profile changes do not invalidate factor verdicts; one document can satisfy multiple people/factors without ownership.

**Phase to address:**
**Phase 1 — Vault schema** for factor/evidence relationships, **Phase 2 — extraction** for structured intervals/owners, and **Phase 4 — auditor pack** for aggregation verdicts.

---

### Pitfall 9: Extraction dependency friction blocks non-technical users or creates invisible quality failures

**What goes wrong:**
The extractor works on the developer machine but fails for users: Poppler is missing, PyMuPDF wheels differ by platform, OCR binaries are absent, fonts or encrypted PDFs fail rendering, scanned PDFs produce no text, rotated pages are misread, tables lose columns, multi-page documents process only page one, or multiple documents bundled in one PDF are treated as one evidence item. Users either cannot run the tool or get low-quality values that look normal.

**Why it happens:**
PDF extraction spans native binaries, optional Python packages, OCR engines, image rendering, and messy real-world documents. Digital PDFs and scans need different paths, and non-technical users rarely know which dependency is missing.

**How to avoid:**
- Add a `doctor`/preflight command that checks render backend, OCR backend, supported image formats, write access to the vault, and sample PDF rendering before import.
- Prefer the lowest-friction local dependency path, but fail loudly with install guidance when optional extras are missing. Missing extraction dependencies should be `missing_dependency`, not `internal_error`.
- Render all pages and record page count; never silently process only the first page.
- Detect scanned-vs-digital PDFs, empty OCR, low text density, low OCR confidence, rotated pages, password-protected files, and huge images; mark affected fields `low_quality` and require confirmation.
- Support an import manifest that lets the user split a multi-document PDF into document records and assign document types/person/factor roles.
- Keep all rendered images and OCR artifacts in the vault and show them in confirmation; do not copy them to tracked fixtures.

**Warning signs:**
Install docs say "install poppler somehow"; a missing binary produces a traceback with a file path; extractor has no page-count assertion; scanned PDF tests are absent; OCR-empty output still produces `SUBSTANTIATED`; multi-document uploads get one `document_id`; users cannot see the page/crop that produced a value.

**Phase to address:**
**Phase 2 — Document extraction.** Dependency preflight and quality-state plumbing are acceptance criteria, not polish.

---

### Pitfall 10: Confirmation becomes a rubber stamp rather than a trust-boundary checkpoint

**What goes wrong:**
The UI/CLI asks "Does this look correct?" once for an entire document or report. The user clicks through, missing that one ability, date, issuer, NOC, or spouse/principal owner is wrong. The system then treats all values as confirmed and produces false confidence.

**Why it happens:**
Confirmation is often implemented as a workflow checkbox after extraction instead of as the formal boundary between non-grounded perception and grounded rule evaluation.

**How to avoid:**
- Confirm at the field/factor level. For each value show: raw extraction, normalized value, source page/crop, factor affected, profile value it is substantiating, and rule consequence.
- Provide explicit choices: `confirm`, `correct`, `not readable`, `not applicable`, `split document`, `wrong person`, `wrong factor`.
- Force unresolved values to remain non-substantiating. There must be a safe path to say "unknown" without inventing a value.
- Require re-confirmation when the source file hash, extracted field, parser version, profile claim, or rule registry version changes.
- Log confirmations in the vault event log with timestamps and hashes, but keep the log private.

**Warning signs:**
There is a single "confirm all" switch; confirmation state is per document, not per field; the user cannot correct a normalized value; old confirmations survive file replacement; the report does not show which confirmed field caused a verdict; ambiguous dates are auto-normalized without review.

**Phase to address:**
**Phase 2 — Confirm-what-I-read**, with invalidation hooks in **Phase 1 — vault schema**.

---

### Pitfall 11: Private audit reports reintroduce PII into rendered outputs

**What goes wrong:**
The final CRS substantiation report naturally contains private values: scores, dates, employers, NOC codes, document names, issuers, and factor deltas. If it reuses the v3.0/v3.1 PII-free renderer assumptions, it may write to a tracked report path, place PII in `claims[]` or `prose`, or produce fixtures that normalize leaking real values.

**Why it happens:**
Earlier document-agent outputs were designed so rendered claims were generic and PII-free. v4.0's useful output is inherently private. The system needs a vault-only private renderer, not just the old public-safe rendered answer path.

**How to avoid:**
- Split output types:
  - **Grounded rule claims:** generic, corpus-cited, PII-free, pass through the existing gate.
  - **Private evidence/value report:** vault-only, may contain PII, never tracked, never published, never used as a fixture.
- Write all full audit reports only under the vault output directory. Refuse `--out` paths outside the vault unless the report is explicitly redacted and publish-safe-scanned.
- Keep PII out of `claims[].text`, `quote`, and `citations`. Put private values in vault-only evidence sections.
- Add a redacted summary mode if shareable output is needed; prove it with the existing publish-safe scanner.
- Test that private report rendering fails closed for non-vault paths and that redacted reports contain no extracted values.

**Warning signs:**
Audit JSON appears under `reports/`; `claims[].text` contains an employer, school, test score, NOC code from the applicant, or date of birth; private values appear in markdown fixtures; `--out` accepts arbitrary paths; publish-safe scanning is used as the only privacy control for private reports instead of path containment.

**Phase to address:**
**Phase 4 — Auditor report renderer**, relying on **Phase 1 — vault path guard**.

---

### Pitfall 12: Stale confirmations and stale extractions survive document/profile changes

**What goes wrong:**
The applicant replaces a PDF, corrects a profile factor, changes accompanying-spouse status, reclassifies first vs second official language, or adds a new ECA. The vault keeps old extracted/confirmed values active, so the next audit substantiates a claim using evidence from a previous file or profile state.

**Why it happens:**
Extraction feels like a one-time import, but the applicant's document set evolves during e-APR preparation. Without hashes and dependency invalidation, "confirmed" becomes detached from the source that was confirmed.

**How to avoid:**
- Tie every extracted and confirmed field to file hash, page hash/crop hash where practical, extractor version, parser version, profile version, and rule-registry version.
- On source/profile/rule changes, mark affected confirmations `stale` and require re-confirmation before `SUBSTANTIATED`.
- Maintain active/inactive document versions instead of overwriting rows.
- Show the audit run ID and evidence snapshot in the report so users know what was checked.
- Add tests: replace a file with same filename but different hash; change spouse status; update language test values; refresh rule registry; expected verdict becomes `AT-RISK` until re-confirmed.

**Warning signs:**
Confirmation rows have timestamps but no source hash; replacing a PDF does not alter verdicts; profile edits do not invalidate factor ledgers; extraction overwrites prior values in place; reports do not identify the evidence snapshot/run ID.

**Phase to address:**
**Phase 1 — Vault schema/versioning** and **Phase 2 — extraction invalidation**, verified again in **Phase 4 — audit re-run behavior**.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Let unconfirmed extraction feed the auditor | Faster demo | False `SUBSTANTIATED` verdicts; undermines the whole fail-closed guarantee | **Never** |
| Store vault artifacts beside repo outputs for convenience | Easy debugging | PII leaks through git status, screenshots, CI, or history | **Never** for real data; synthetic only in tracked tests |
| Reuse `corpus/index.db` for candidate documents | Avoids new DB code | PII contaminates authoritative corpus; evidence confused with source authority | **Never** |
| Hardcode CRS tables/validity windows in agent markdown | Quick rule implementation | Stale, ungrounded, and hard to update across agents | **Never** for current rules |
| Use `hits[0]` as the rule source | Less registry work | Historical/adjacent chunks pass the gate but ground the wrong rule | Only for a proven registry entry with a retrieve-what-you-cite test; otherwise never |
| Produce only a total CRS score | Simple UI | Masks factor-level mismatches, caps, spouse-table errors, and evidence gaps | Only as a derived summary after factor ledger is complete |
| "Confirm all" for an entire document | Less UX work | Rubber-stamps one wrong value into many verdicts | Only for synthetic demos; never for real audit mode |
| Add OCR/render dependencies without preflight | Faster implementation | Non-technical users fail at install or get silent low-quality extraction | Never; preflight is part of extraction acceptance |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Vault ↔ Git | Rely on `.gitignore` only | Path guard all writes to vault; expand publish-safe/gitleaks patterns; test `git add -A` cannot stage private artifacts |
| Vault DB ↔ Corpus DB | Treat both as searchable stores with shared IDs | Separate `evidence_id` from `citation_id`; never index PII into the authoritative corpus |
| Extractor ↔ Auditor | Pass normalized values directly | Pass only confirmed evidence records; unconfirmed/low-quality/stale evidence fails closed |
| OCR/render backend | Surface native-tool traceback | `doctor` command + `missing_dependency` envelope + vault-local temp artifacts |
| CRS registry ↔ FTS5 | Blind BM25 top hit | Source-family filters + marker selection + retrieve-what-you-cite tests |
| Rule citation ↔ Evidence pointer | Put user values in grounded claims | Corpus claims stay generic/cited; private evidence pointers stay vault-only |
| Job-offer rules | Assume valid job offer still gives CRS points | Ground current job-offer policy at run time and separate eligibility effects from CRS points |
| Work-experience/NOC | Infer NOC fit from job title | Check deterministic fields and mark semantic NOC-duty fit as `AT-RISK` unless manually reviewed |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Rendering every page at high DPI on every audit run | Slow imports; huge vault; repeated temp files | Cache by file hash + render settings inside vault; clean stale cache | Multi-page PDFs and image-heavy scans |
| OCRing digital PDFs unnecessarily | Slow and less accurate than embedded text | Extract embedded text first, render/OCR for visual confirmation and scanned pages | Any batch of documents |
| Processing only first page for speed | Missing back-page scores, signatures, dates, or duties | Record page count and require page coverage in extraction manifests | Immediately on language/ECA/work letters |
| Re-running rule retrieval per factor without registry cache | Slow audit; inconsistent source choice | Cache resolved registry rules by corpus hash + registry version | Full CRS grid |
| Keeping all rendered images forever | Vault grows quickly; harder cleanup | Content-addressed cache with cleanup policy; never tracked | Repeated imports/re-renders |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Rendered page images outside vault | Passport/score/employer images leak into repo, temp, or backups | Vault-only temp/render dirs; path guard; cleanup |
| OCR text in logs/errors | Full document text leaks through stdout/stderr or CI | Generic error messages; no offending snippets; vault-only debug logs |
| Private report written to tracked path | Complete CRS/evidence profile can be committed | Refuse non-vault output for private reports; redacted mode only outside vault |
| Real documents used as fixtures | Permanent PII in git history | Synthetic PDFs/images only; fixture scan and reviewer checklist |
| Candidate evidence in `claims[]` | PII appears in grounded output path | Keep claims generic; private evidence in vault-only fields |
| Storing vault DB/WAL in repo | Full extracted values leak | Ignore/guard all DB sidecars; publish-safe path patterns |
| Unencrypted/loose local file permissions | Other local users/processes can read documents | Use restrictive vault permissions where practical; warn users vault is local-sensitive data |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| "Green check" without evidence status | User trusts unconfirmed OCR | Show confirmed/unconfirmed/stale per field and block `SUBSTANTIATED` until confirmed |
| Single report-level confirmation | User misses one wrong value | Field-level confirmation with page/crop and profile comparison |
| Hiding uncertainty behind `AT-RISK` | User does not know what to fix | Explain the exact blocker: missing doc, unconfirmed value, stale rule, semantic review required |
| Legal-sounding verdicts | User mistakes tool for immigration advice | Use substantiation/risk framing, official citations, and "not legal advice" |
| No source freshness visible | User cannot tell if a volatile rule changed | Show crawl date, source URL, and stale-rule warnings |
| No import/split workflow for multi-doc PDFs | Evidence attached to wrong person/factor | Import manifest with document type, owner, factor, and page range |

## "Looks Done But Isn't" Checklist

- [ ] **Vault:** Often missing sidecar/temp coverage — verify raw docs, rendered images, OCR text, DB/WAL/SHM, logs, private reports, and temp dirs are all vault-only and unstaged.
- [ ] **Extraction:** Often missing fail-closed state — verify every value has `unconfirmed/confirmed/corrected/stale/low_quality` status and only confirmed values can substantiate.
- [ ] **Confirmation:** Often too coarse — verify confirmation is per field with source page/crop, normalized value, and affected CRS factor.
- [ ] **Rule registry:** Often just hardcoded constants — verify each CRS rule resolves from corpus at run time with source-family filters and marker tests.
- [ ] **Current-rule retrieval:** Often picks historical pages — verify arranged-employment/job-offer, CRS tables, and NOC/TEER rules cite current intended sources, not year-end summaries.
- [ ] **CRS math:** Often misses caps — verify spouse/no-spouse tables, per-ability language, transferability caps, and additional-point rules with boundary fixtures.
- [ ] **Over-claiming:** Often treats "rule grounded" as "fact proven" — verify semantic-review cases produce `AT-RISK`, not `SUBSTANTIATED`.
- [ ] **Private reporting:** Often reuses PII-free renderer assumptions — verify full audit reports can only be written under the vault.
- [ ] **Dependency UX:** Often works only locally — verify `doctor` catches missing render/OCR dependencies and scanned/multi-page fixtures are covered.
- [ ] **Re-runs:** Often reuse stale confirmations — verify file/profile/rule changes invalidate affected confirmations.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Real document artifact committed | HIGH | Treat as compromised; stop publishing; scrub git history; rotate exposed secrets/credentials if any; add the artifact pattern to gates; re-clone/fork warning as needed |
| False `SUBSTANTIATED` from extraction misread | HIGH | Change affected factor to fail-closed; add adversarial fixture; require field confirmation; invalidate prior audit runs using same extractor/version |
| Candidate text entered corpus/index | HIGH | Delete contaminated corpus/index locally; rebuild from authoritative corpus only; add path/type guard tests; scan repo/history for copied text |
| Stale CRS rule used | MEDIUM | Re-crawl authoritative sources; update registry source priority/marker; add stale-field warning and regression for changed rule |
| Historical chunk selected | MEDIUM | Add source-family allowlist/disallowlist and marker selection; add retrieve-what-you-cite test for the factor |
| CRS cap/math error | MEDIUM | Move arithmetic into deterministic tested module; add boundary fixtures; re-run all factor ledgers |
| OCR dependency install failure | LOW-MEDIUM | Add preflight detection and clearer install docs; make optional extras explicit; return `missing_dependency` |
| Private report written outside vault | HIGH | Delete/scrub report; add output path refusal; add test for arbitrary `--out` rejection |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| PII leaks through vault/images/OCR/logs | **Phase 1 — Candidate vault + guardrails** | `git add -A` cannot stage vault artifacts; publish-safe/gitleaks patterns cover docs/images/OCR/DB/temp/private reports |
| Vault/corpus boundary blurred | **Phase 1**, reinforced in **Phase 3/4** | Candidate imports never mutate `corpus/` or `corpus/index.db`; citations and evidence IDs are distinct |
| Stale confirmations after file/profile changes | **Phase 1 schema + Phase 2 invalidation** | Hash/version change flips evidence to `stale` and blocks `SUBSTANTIATED` |
| Extraction misreads false confidence | **Phase 2 — Extraction + confirmation** | Unconfirmed/low-quality/ambiguous fixture yields `AT-RISK`/`GAP`; CLB/date/NOC adversarial tests pass |
| Confirmation rubber-stamp | **Phase 2** | Field-level confirmation required; no document-level `confirm_all` can substantiate |
| Dependency/scanned/multi-page failures | **Phase 2** | `doctor` covers dependencies; scanned, rotated, multi-page, multi-doc fixtures covered |
| Volatile rules hardcoded | **Phase 3 — CRS-rule registry** | Static gate finds no inlined volatile values; every rule resolves to corpus with crawl date |
| Historical/adjacent source selected | **Phase 3** | Retrieve-what-you-cite tests lock query+marker+expected source family per factor |
| CRS logic caps/combinations wrong | **Phase 3**, consumed in **Phase 4** | Boundary fixtures for spouse/no-spouse, per-ability CLB, caps, job-offer changes, and transferability combinations |
| Over-claiming `SUBSTANTIATED` / legal advice | **Phase 3 verdict semantics + Phase 4 agents** | Semantic-review fixtures produce `AT-RISK`; report includes scope/not-legal-advice framing |
| Multi-document aggregation missing | **Phase 4 — Modular auditor pack** | Factor ledger uses multiple evidence records, detects conflicts/overlaps, and cites rule + evidence pointers |
| Private report leaks PII | **Phase 4 — Renderer** | Full report refuses non-vault paths; redacted mode publish-safe-scans clean |

## Sources

- `.planning/PROJECT.md` — v4.0 target features, constraints, PII/vault invariant, no vectors/cloud APIs, current milestone context. (HIGH)
- `.planning/notes/crs-claim-substantiation-auditor.md` — extraction trust-gap caveat and the need for confirm-what-I-read despite automated extraction. (HIGH)
- `.planning/seeds/crs-claim-substantiation-auditor.md` — candidate phase shape: vault → extraction → grounded registry → auditor pack. (HIGH)
- `.planning/research/PITFALLS.md` — existing project pitfalls: PII side doors, grounding limits, volatile values, stale corpus, CLI portability, and PDF extraction/corpus-integrity patterns. (HIGH)
- `crawler/grounding.py` and `skills/document-agents/_contract.md` — existing gate guarantees resolvability + verbatim quote only, not semantic entailment; PII-tier split for claims vs basis. (HIGH)
- `scripts/check_publish_safe.py` and `.gitignore` — current publish-safety guard surface that v4.0 must extend for vault/images/OCR/private reports. (HIGH)
- Local authoritative corpus, `pr-pdi/express-entry-intake-applications-received-on-after-january-1-2015.md#001` — e-APR supporting documents must substantiate profile/e-APR information; inability to substantiate can lead to A11.2 refusal and misrepresentation consideration. (HIGH; crawled 2026-06-11)
- Local authoritative corpus, `guidance/language-test.md#009` and `guidance/language-test.md#013` — language validity and per-ability CLB conversion examples showing date/per-ability boundary risk. (HIGH; crawled 2026-06-11)
- Local authoritative corpus, `guidance/check-score.md#006` and `guidance/education-assessment.md#009` — ECA validity and multi-credential examples. (HIGH; crawled 2026-06-11)
- Local authoritative corpus, `guidance/job-offer.md#001` and `guidance/job-offer.md#002` — recent job-offer/arranged-employment policy change and eligibility-vs-CRS distinction. (HIGH; crawled 2026-06-11)
- Local authoritative corpus, `guidance/crs-criteria.md#006`, `#013`, `#014`, `#016`, and `ministerial-instructions/current.md#087` — spouse/no-spouse language tables, skill-transferability rules, and caps. (HIGH; crawled 2026-06-11)
- Local authoritative corpus, `guidance/federal-skilled-workers.md#002` and `definitions/terms-definitions-related-permanent-residence.md` search results — NOC/TEER and skilled-work-experience examples. (HIGH; crawled 2026-06-11)
- Known local-document extraction implementation risks (PDF rendering/OCR/native dependencies/scanned vs digital PDFs/multi-page files). (MEDIUM; engineering experience, must be validated with v4.0 fixtures)

---
*Pitfalls research for: v4.0 CRS Profile ↔ Document Substantiation Auditor*
*Researched: 2026-07-05*
