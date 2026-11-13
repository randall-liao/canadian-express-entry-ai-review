# Phase 27: CLI-Agnostic Document Agents - Research

**Researched:** 2026-06-21
**Domain:** Portable plain-Markdown agent skills + corpus-grounded answer assembly (CHK-03)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
*(CONTEXT.md `## Decisions` — discuss skipped; all implementation choices are at the
agent's discretion, but these anchors are LOCKED.)*

- Each agent is PLAIN MARKDOWN with NO proprietary front-matter and NO dependency on any single
  CLI's tool/MCP API — everything is an ordinary shell command (`corpus-crawler --json search` /
  `corpus-crawler --json ground`) plus JSON parsing. Mirror the existing `crawler/AGENT_SKILL.md`
  style (CLI-agnostic, shell + JSON only).
- The six agents SHARE one `_contract.md` describing the structured answer object
  `{question, claims:[{id,text,citations[],quote}], basis[], abstentions[], prose}`, the
  search→copy-verbatim-quote→ground loop, and the abstention rule.
- GROUNDING-BY-CONSTRUCTION: an agent copies the `quote` VERBATIM from a retrieved chunk and pipes
  the answer through `corpus-crawler --json ground`; it emits ONLY cited claims; when the corpus has
  no answer it abstains ("not in corpus"), never confabulates. The Python gate (Phase 25) is the
  trust boundary — no CLI-native tooling in the trust path.
- No volatile/hardcoded requirement values in agent prompts (no inlined dollar amounts, validity
  windows, or requirement text) — every requirement statement resolves from the corpus via `search`
  with a citation (the v1.0 "grep finds no inlined volatile values" rule).
- PII boundary holds (CHK-02 inheritance): no PII (employer name, dates, salary, names) in
  `claims[].text`; personalization/applicability stays in `basis[]` / local files; rendered output
  stays under git-ignored `personal/output/`.
- Per-CLI conformance is proven by a portable conformance check (one grounded question → verified
  citation set passes identically across CLIs because all logic is the shared Python gate + shell
  `search`).

### the agent's Discretion
- All implementation choices (file placement, agent-spec structure, conformance-harness shape,
  exact baked queries, number of plans/waves). Use the ROADMAP goal, success criteria, codebase
  conventions, and `crawler/AGENT_SKILL.md` to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
- Layer-2 per-document rule matching (recency/amounts/format/translation verification) — VAL-01.
  Phase 27 agents answer document questions (which requirements + cited), **not** full Layer-2
  validation.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHK-03 | Portable, CLI-agnostic document agents (markdown skills) consume the `search` contract to answer document questions, emitting only cited claims (subject to GND-02). | All six doc types verified citable against the live 742-doc index (see *Corpus Citability Map*). The shipped `search`→`ground` pipeline grounds a crafted employment-reference-letter answer to `verdict:"pass"` and fails-closed on a confabulated quote (both run end-to-end this session). Shared-contract shape + abstention/PII rules taken verbatim from `crawler/grounding.py`, `crawler/checklist.py`, `crawler/CONTRACT.md`. |
</phase_requirements>

## Summary

Phase 27 ships **no new trust-path code**. The three primitives the agents stand on are already
GREEN and frozen: `corpus-crawler --json search` (Phase 24, BM25 + `--cite` resolve),
`corpus-crawler --json ground` (Phase 25, fail-closed grounding gate that reads an answer JSON on
stdin and renders to `personal/output/`), and `corpus-crawler --json checklist` (Phase 26, the
producer pattern to mirror). The deliverable is six **plain-Markdown agent specs** + one shared
`_contract.md` + a **conformance harness**. Each spec teaches any CLI agent to run the same loop the
shipped `checklist.py` already runs in Python: read the local profile slice for applicability
(→ `basis[]`), run a SHORT 2-4-token query via `search`, copy a **verbatim** quote span from the
retrieved chunk, assemble the Phase-25 answer object with **generic PII-free** `claims[].text`, and
pipe it through `ground` — which renders only on a clean grounding + publish-safety pass and
**abstains rather than confabulates**. [VERIFIED: crawler/checklist.py, crawler/grounding.py]

The centrepiece — the new 6th **employment reference letter** agent — is fully citable. **Every
required element** (company letterhead, applicant name, company contact info, signatory
name/title/signature, all positions held, job title, duties & responsibilities, job status, dates
worked, hours/week, annual salary + benefits) is present **verbatim in a single generic, PII-free
corpus chunk**: `pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#019`.
All six candidate element quotes pass `grounding.quote_is_grounded()` against that chunk, and a
4-claim answer grounds to `verdict:"pass"` end-to-end this session. **No element is un-citable** —
there is nothing the employment-reference agent must abstain on for the canonical Express Entry
proof-of-work-experience reference letter. [VERIFIED: corpus/index.db via `search --cite` + `ground`]

The single most important design distinction: **two different IRCC letters both get called
"reference/employment letter."** Chunk `#019` is the **proof-of-work-experience reference letter**
(supports the *skilled work-experience* claim — this is Phase 27's employment-reference agent).
Chunks `#034` / `economic-classes-federal-skilled-workers-arranged-employment-…#000` are the
**arranged-employment job-offer letter** (a *different* doc type, the existing `job-offer` item in
`checklist.py`, only required when claiming arranged-employment points). The agent must cite the
work-experience letter requirements, not the job-offer ones. [VERIFIED: corpus/index.db]

**Primary recommendation:** Build six thin Markdown specs + one `_contract.md` under
`skills/document-agents/` (or `crawler/agents/` — see decision note), each baking a SHORT 2-4-token
`search` query (NEVER a hardcoded chunk_id or requirement value), reusing the `checklist.py`
search→verbatim-quote→ground→abstain loop, and add a `@skipUnless(corpus/index.db)` real-corpus
conformance test (`crawler/tests/test_document_agents.py`) that grounds each baked question to
`pass`, fails-closed on a confabulated quote, and asserts the resolved citation set is deterministic.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Answer assembly (search → quote → answer JSON) | Agent skill (Markdown instructions, executed by the CLI agent) | — | The "agent" is a prompt: it shells out and parses JSON. No new runtime code in the trust path. |
| Retrieval | Python `searchindex.search` via `corpus-crawler --json search` (shell) | — | Shipped Phase-24 primitive; BM25 over the FTS5 index. The agent never re-implements search. |
| Grounding / verdict / render / write | Python `grounding` + `cli._cmd_ground` via `corpus-crawler --json ground` (shell) | — | Shipped Phase-25 gate is the TRUST BOUNDARY (fail-closed, publish-safe, `personal/`-confined). All CLIs share it. |
| Applicability (which requirements apply) | Local profile slice (`personal/profile.yaml`) read by the agent | `basis[]` of the answer | PII drives selection only; mirrors `checklist.applicable_items`. Never enters `claims[].text`. |
| PII containment | Python write-gate (`personal/output/` boundary + publish-safe scan) | Agent discipline (no PII in claims) | Defense-in-depth: even a misbehaving agent can't leak — the gate scans rendered bytes and refuses. |
| Conformance proof | pytest real-corpus integration test | shell subprocess of `ground` | Proves the trust path is CLI-independent (identical verdict for any CLI emitting the same JSON). |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `corpus-crawler` CLI (`crawler.cli:main`) | 2.0.0 (in-repo) | The `search` / `ground` verbs the agents shell out to | Already the shipped, frozen contract (`crawler/CONTRACT.md`, schema_version "1.0"). [VERIFIED: pyproject.toml, `.venv/bin/corpus-crawler --help`] |
| Python stdlib `json` | 3.10.12 | Parse the `--json` envelope / build the answer object | Zero deps; the agent specs only require "a shell command + JSON parsing" per AGENT_SKILL.md. [VERIFIED] |
| `crawler.grounding` | in-repo (Phase 25) | The fail-closed gate (`check_answer`, `quote_is_grounded`, `render_answer`) | The trust boundary; reused UNMODIFIED. [VERIFIED: crawler/grounding.py] |
| `crawler.searchindex` | in-repo (Phase 24) | `search` / `resolve` over `corpus/index.db` | Reused UNMODIFIED; `_to_match` ANDs every token. [VERIFIED: crawler/searchindex.py] |
| `crawler.checklist` | in-repo (Phase 26) | Producer pattern to mirror (search→verbatim-quote→ground→abstain; relpath backstop) | The exact pattern Phase 27 generalizes per doc type. [VERIFIED: crawler/checklist.py] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 | Run the unittest-style conformance suite | Test command: `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -q`. [VERIFIED: pytest --version] |
| `scripts/check_publish_safe` | in-repo | Publish-safety scanner the `ground` write-gate calls internally (SAFE-02) | Already invoked by `_cmd_ground`; the conformance test reuses it on rendered bytes (NEVER a whole-tree scan — see Pitfall 6). [VERIFIED: crawler/cli.py, scripts/] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `corpus-crawler --json search/ground` (console script) | `.venv/bin/python -m crawler.cli --json …` | Module form is the **mandatory** invocation in this env because bare `python` is broken (CRLF shim). The console script `.venv/bin/corpus-crawler` works too (verified). Agent specs should show the generic `corpus-crawler …` form (as AGENT_SKILL.md does) and the conformance test should call `.venv/bin/python -m crawler.cli` or `grounding.*` directly. |
| Baking SHORT `search` queries per item | Hardcoding chunk_ids in the spec | Chunk_ids are `relpath#ordinal` content coordinates that **drift** (resolve returns `None` → fail-closed) on any content change; queries are stable and self-healing. `checklist.py` bakes queries, never ids. Mirror it. |
| One Markdown `_contract.md` shared by six specs | Six self-contained specs | Shared contract keeps the answer-object schema / abstention rule single-sourced (DRY) and matches the locked decision. |

**Installation:**
```bash
# No new packages. Everything is in-repo + stdlib. Confirm the toolchain only:
.venv/bin/corpus-crawler --help          # console script present
.venv/bin/python -m crawler.cli --json search "passport" --db corpus/index.db --limit 1
```

**Version verification:** No external package is added by this phase, so the npm/PyPI legitimacy
gate is **N/A**. The one runtime dep already declared (`pyyaml>=6.0,<7.0`) is unchanged. [VERIFIED:
pyproject.toml — `dependencies = ["pyyaml>=6.0,<7.0"]`, no additions needed]

## Package Legitimacy Audit

> **N/A — this phase installs no external packages.** The deliverable is plain-Markdown agent specs
> + a pytest conformance test. It reuses only in-repo modules (`crawler.*`, `scripts/`) and the
> Python stdlib (`json`, `subprocess`, `unittest`). No `pip install` step exists, so there is no
> registry surface to slopsquat. Confirmed by reading `pyproject.toml` (no dependency change) and by
> the locked decision "everything is an ordinary shell command plus JSON parsing."

**Packages removed due to [SLOP] verdict:** none (no packages introduced).
**Packages flagged as suspicious [SUS]:** none.

## Corpus Citability Map (the heart of this research)

> Verified this session against the live, git-ignored `corpus/index.db` (742 docs) via
> `corpus-crawler --json search`, `search --cite <id>`, and `grounding.quote_is_grounded()`.
> Chunk_ids are stable while the corpus is byte-identical but agents bake the **query**, not the id.

### Employment reference letter (the new 6th agent) — **fully citable, zero gaps**

**Canonical chunk:** `pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#019`
(generic IRCC operational manual page, NO PII, NOT under the `police-certificates/` leaky family).
Source: `https://www.canada.ca/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals/permanent-residence/express-entry/applications-received-on-after-january-1-2016-completeness-check.html`
Section: *Mandatory documents for all applicants › Proof of work experience › Document requirements*.

| Required element | Verbatim quote (a real substring of #019; passes `quote_is_grounded`) | Citable? |
|------------------|----------------------------------------------------------------------|----------|
| Company letterhead | `should be an official document printed on company letterhead` | ✅ PASS |
| Applicant's name | `must include the applicant's name` | ⚠ PASS only with CURLY apostrophe |
| Company contact info (address, phone, email) | `the company's contact information [address, telephone number and email address]` | ⚠ PASS only with CURLY apostrophe |
| Signatory name + title + signature | `the name, title and signature of the immediate supervisor or personnel officer at the company` | ✅ PASS |
| All positions held | `should indicate all positions held while employed at the company` | ✅ PASS |
| Job title / duties & responsibilities / job status / dates worked / hours per week / annual salary + benefits | `must include the following details: job title, duties and responsibilities, job status (if current job), dates worked for the company, number of work hours per week and annual salary plus benefits` | ✅ PASS |

> **⚠ CURLY-APOSTROPHE HAZARD (plan-check W1).** Chunk #019 uses a curly apostrophe `U+2019` in
> "applicant's" / "company's", and `grounding._norm` collapses whitespace + lowercases ONLY (it does NOT
> normalize apostrophes). A straight-apostrophe RETYPE of those two rows FAILS `quote_is_grounded`. The same
> hazard affects ECA (`organization's`/`applicant's`). **Rule for the fixture/skill authors: copy every
> `quote` VERBATIM from live `corpus-crawler --json search --cite #019` output — never retype from this
> table.** The consolidated multi-element span grounds 4/4 only when copied with curly apostrophes.


All six element quotes returned **PASS** from `crawler.grounding.quote_is_grounded(quote, chunk_text)`,
and a 4-claim answer over #019 grounded to `verdict:"pass", grounded:4, ungrounded:0` via
`corpus-crawler --json ground` this session. **Nothing for this agent needs to abstain.** [VERIFIED:
corpus/index.db]

**Queries that surface #019 (2-4 tokens, AND'd):** `reference letter letterhead` (1 hit, #019),
`letter employer positions held` (1 hit, #019), `reference letter company letterhead` (1 hit, #019),
`letter work experience mandatory` (1 hit, #019), `duties responsibilities job title` (#019 ranks
first). Prefer a query that uniquely returns #019 so the agent reliably lands the work-experience
letter, not the job-offer letter. [VERIFIED]

**DO NOT confuse with the arranged-employment job-offer letter** (different doc type):
`pr-pdi/express-entry-…completeness-check.md#034` (*Letter of offer from the employer*) and
`pr-pdi/economic-classes-federal-skilled-workers-arranged-employment-awarding-points-…#000`. These
add elements like *expected start date* and *continuous, paid, full-time… at least one year*. They
belong to the existing `job-offer` checklist item, not the employment-reference agent. [VERIFIED]

### The other five document types — all have generic, PII-free, citable chunks

| Agent | Verified generic citation(s) | Baked query (2-4 tokens) | Notes |
|-------|------------------------------|--------------------------|-------|
| Police certificate | `guidance/police-certificates.md#002` (who needs them: 18+, every country 6 mo in last 10 yrs) | `police certificate 10 years country` | **MUST** constrain with `--family guidance` and/or skip `police-certificates/<country>.md` relpaths (mirror `checklist._is_country_specific`). A naive `police certificate` returns ONLY per-country PII-leaking pages. [VERIFIED] |
| Language test | `guidance/language-test.md#001` (take an approved test) / `#002` (tests we accept) | `language test approved results` | Generic guidance family. [VERIFIED] |
| ECA | `eca/educational-credential-assessment.md#005` (equivalency to a *completed* Canadian credential) / `guidance/education-assessment.md#004` | `foreign educational credential assessment` | Generic. [VERIFIED] |
| Proof of funds | `guidance/proof-funds.md#007` (must legally access; can't borrow / no real-property equity) + `pr-pdi/express-entry-assessing-electronic-application-on-section-a11-2.md#036` (FSW/FST must meet; CEC/PNP exempt) | `proof settlement funds` / `settlement funds requirement unless` | Generic; matches `checklist.py` proof-of-funds applicability. [VERIFIED] |
| Medical (IME) | `medical/requirements-permanent-residents.md#000` (must have an IME) / `medical/immigration-medical-assessment.md#001` | `immigration medical examination permanent residence` | Chunk #000 contains a VOLATILE date (`until October 5, 2029`) — quote it from corpus, never inline it (see Pitfall 2). [VERIFIED] |

## Architecture Patterns

### System Architecture Diagram

```
  Local profile slice                 The six Markdown agent specs (CLI-agnostic prompts)
  personal/profile.yaml  ──────────►  read applicability  ──►  basis[]  (PII stays here, never rendered)
  (git-ignored, PII)                         │
                                             ▼
                              for each required element:
                                             │
                    ┌────────────────────────┴───────────────────────────┐
                    ▼                                                      ▼
        corpus-crawler --json search                          (zero hits OR only leaky
        "<2-4 token query>" [--family guidance]                per-country relpath?)
                    │                                                      │
            best generic hit                                              ▼
       (skip police-certificates/<country>)                   ABSTAIN: emit abstention
                    │                                          "not in corpus" — NO claim
                    ▼
        copy VERBATIM quote span from the hit's chunk text
        (substring; never paraphrase)
                    │
                    ▼
        assemble answer JSON:
        { question, claims:[{id, text(GENERIC), citations:[chunk_id], quote}],
          basis:[PII applicability], abstentions:[…], prose }
                    │
                    ▼
        corpus-crawler --json ground   < answer.json   --db corpus/index.db
        ┌──────────────────────────── TRUST BOUNDARY (Phase 25, Python) ───────────────────────────┐
        │ resolve every citation → verify quote is a normalized substring → whole-answer verdict   │
        │  fail (any uncited/unresolvable/quote_not_in_chunk) → exit 1, render/write NOTHING        │
        │  pass → render (claim + quote + citation) → publish-safe scan → write personal/output/    │
        │         publish-unsafe hit → exit 4, refuse to write                                      │
        └──────────────────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
        personal/output/<slug>.md   (git-ignored; PII-free by construction — claims only)
```

### Recommended Project Structure
```
skills/document-agents/            # repo-root portable skill pack (see decision note)
├── _contract.md                   # SHARED: answer-object schema + search→quote→ground loop + abstention rule
├── employment-reference-letter.md # the new 6th agent (cites #019 work-experience letter elements)
├── police-certificate.md          # uses --family guidance + per-country relpath backstop
├── language-test.md
├── eca.md
├── proof-of-funds.md
└── medical.md
crawler/tests/
└── test_document_agents.py        # @skipUnless(corpus/index.db) conformance harness
```
(Per-CLI pointer files — `AGENTS.md`, `.github/copilot-instructions.md`, optionally `CLAUDE.md` —
each add a one-line redirect to `skills/document-agents/`. They are thin adapters, not logic.)

### Pattern 1: The shared search→verbatim-quote→ground→abstain loop (mirror `checklist.grounded_claim`)
**What:** For each requirement element, search → take the best **generic** hit → slice a verbatim
quote → emit a claim; on any miss, abstain (never a bare claim).
**When to use:** Every claim in every one of the six agents.
**Example:**
```python
# Source: crawler/checklist.py:339-388 (grounded_claim) — the pattern the Markdown specs describe in prose
res = searchindex.search(db, query, limit=5, family=family)      # family optional; tokens AND'd
for hit in res["hits"]:
    relpath = hit["relpath"]
    if _is_country_specific(relpath):        # skip police-certificates/<country> (PII leak)
        continue
    chunk = searchindex.resolve(db, hit["chunk_id"])  # None == miss/drift → fail-closed
    if chunk is None:
        continue
    quote = _verbatim_quote(chunk["text"])   # a REAL substring; "" → abstain
    if not quote:
        continue
    return {"id": item["doc_type"], "text": item["text"],   # GENERIC PII-free label
            "citations": [hit["chunk_id"]], "quote": quote}
return None                                   # → caller emits an explicit abstention
```

### Pattern 2: PII-tier split (claims generic, basis personal)
**What:** `claims[].text` / `quote` / `citations` are GENERIC corpus content; profile-derived PII
(countries, dates, family counts, employer name) lives ONLY in `basis[]`, which the gate never
checks and `render_answer` never renders.
**When to use:** Every agent; it is what makes the rendered output PII-free *by construction*.
**Example:** `crawler/checklist.py:391-399` (`_assemble_answer`) — `claims` ← generic claim, `basis`
← PII sentence; verified PII-free render this session.

### Pattern 3: Abstain, never confabulate (the honesty boundary)
**What:** If `search` returns zero hits (or only leaky relpaths, or an unresolvable/degenerate
chunk), the agent emits an `abstentions[]` entry ("not in corpus") and **no claim** for that element.
**When to use:** Whenever retrieval cannot ground an element. Verified: a confabulated quote yields
`verdict:"fail", reasons:["quote_not_in_chunk"], exit 1`, render/write nothing. [VERIFIED]

### Anti-Patterns to Avoid
- **Hardcoding requirement text / dollar amounts / validity windows in the Markdown spec** — violates
  the locked "no inlined volatile values" rule. Every requirement statement must resolve from the
  corpus via `search` with a citation.
- **Baking chunk_ids** instead of queries — ids drift and fail-close; bake the 2-4-token query.
- **Long AND'd queries** — `_to_match` ANDs every token, so a 6-word query often returns 0 hits.
  Keep queries to 2-4 high-signal tokens.
- **Paraphrasing the quote** — the gate requires a normalized substring; a paraphrase fails closed.
- **Putting any PII in `claims[].text` / `quote` / `citations`** — breaks CHK-02; rendered output
  must stay PII-free.
- **Relying on a CLI-native tool/MCP** for any trust-path step — breaks CLI-agnosticism.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Citation resolution / staleness | A custom id→chunk lookup | `searchindex.resolve` (via `search --cite` or in-process in the test) | Fail-closed on drift is already correct + tested (GND-01). |
| Grounding verdict | A regex/"does the quote look cited" check | `grounding.check_answer` / `corpus-crawler --json ground` | The locked trust boundary; any re-implementation forks the guarantee. |
| Quote normalization | Your own whitespace/case folding | `grounding._norm` (used by `quote_is_grounded`) | Loosening normalization silently widens the grounding guarantee — forbidden. |
| Render + publish-safe write | Markdown templating + manual PII scrub | `grounding.render_answer` + `_cmd_ground` write-gate | Render-then-scan-then-write to `personal/` is shipped (RPT-03); refuses on a publish-safety hit. |
| Per-country PII backstop | New logic | `checklist._is_country_specific` pattern (`--family guidance` + relpath skip) | Defense-in-depth already designed for threat T-26-08. |
| Search escaping / FTS5 safety | Building MATCH strings | `searchindex._to_match` (parameter-bound) | Crafted queries can't inject operators; empty queries fail-closed. |

**Key insight:** Phase 27 is an **integration/authoring** phase, not an implementation phase. Every
hard problem (resolution, grounding, normalization, render, PII containment, search safety) is
already solved and frozen. The risk is *re-implementing* one of them in a CLI-native way and forking
the guarantee — don't.

## Common Pitfalls

### Pitfall 1: Confabulating requirement text instead of citing it
**What goes wrong:** The agent writes a plausible-sounding requirement ("must be notarized within 30
days") with a real chunk_id but a quote that isn't in the chunk.
**Why it happens:** LLM priors fill gaps; the citation "looks" attached.
**How to avoid:** The quote MUST be copied verbatim from the retrieved chunk text. The gate enforces
this (`quote_not_in_chunk` → fail-closed, exit 1, writes nothing). Verified this session.
**Warning signs:** `ground` returns `verdict:"fail"` with `reasons:["quote_not_in_chunk"]`.

### Pitfall 2: Inlining volatile values (the medical IME date trap)
**What goes wrong:** Hardcoding "exempt until October 5, 2029" or a settlement-funds dollar amount in
the Markdown spec. IRCC changes these; the spec rots and lies.
**Why it happens:** It's convenient to state the value directly.
**How to avoid:** Quote the volatile value verbatim **from the corpus** with a citation (chunk
`medical/requirements-permanent-residents.md#000` contains the date verbatim — VERIFIED). The v1.0
rule: "grep finds no inlined volatile values in agent prompts."
**Warning signs:** A number/date/window appears in the `.md` spec body rather than in a quoted span.

### Pitfall 3: Long AND'd queries returning zero hits
**What goes wrong:** A 6-8 word query returns 0 hits because `_to_match` ANDs every token.
**Why it happens:** Natural-language phrasing of the requirement.
**How to avoid:** Bake 2-4 high-signal tokens (e.g. `reference letter letterhead`, not "what should
an employment reference letter printed on company letterhead include"). Verified: short queries land
#019; long ones miss.
**Warning signs:** `search` `count: 0` → forced abstention on an element that IS in the corpus.

### Pitfall 4: Citing a country/PII-bearing relpath (police certificates)
**What goes wrong:** A police-certificate claim cites `police-certificates/cameroon.md` — the relpath
itself leaks residence history.
**Why it happens:** A naive `police certificate` query returns ONLY per-country pages (VERIFIED:
Cameroon, Russia, Pakistan, Puerto Rico, Benin ranked above any generic page).
**How to avoid:** Constrain with `--family guidance` (VERIFIED: returns only `guidance/police-certificates.md`)
AND/OR apply the `_is_country_specific` relpath backstop (skip `police-certificates/<country>`).
Prefer the generic `guidance/police-certificates.md` rule page.
**Warning signs:** A citation relpath starts with `police-certificates/`.

### Pitfall 5: Proprietary front-matter / CLI-native tooling creeping into a spec
**What goes wrong:** A spec gains a YAML front-matter block (`tools:`, `mcp:`) or tells the agent to
use a CLI's native file/search tool.
**Why it happens:** Per-CLI ergonomics tempt shortcuts.
**How to avoid:** Plain Markdown only; everything is `corpus-crawler --json …` + JSON parsing
(mirror `crawler/AGENT_SKILL.md`, which has none). The conformance test proves identical behavior
through the shell path.
**Warning signs:** `---` front-matter at the top of a spec, or any reference to a CLI-specific tool.

### Pitfall 6: A whole-tree publish-safe scan in the conformance test reds on pre-existing violations
**What goes wrong:** Calling `check_publish_safe` with no path scans all tracked files and reports
~28 pre-existing `ABS_PATH` violations in test fixtures (VERIFIED this session) — a false red.
**Why it happens:** The scanner defaults to scanning the tracked tree.
**How to avoid:** Scan only the **rendered bytes** (use `scan_text(label, bytes)` as `_cmd_ground`
and `test_checklist.py` do), never the whole tree. Phase 26 already documented this.
**Warning signs:** Test fails on `/home/...` strings inside `crawler/tests/*.py`. <!-- # publish-safe: allow -->

## Code Examples

### End-to-end: ground an employment-reference-letter answer (VERIFIED `pass` this session)
```bash
# Source: run this session against corpus/index.db
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{"question":"What must an Express Entry employment/reference letter contain?",
 "claims":[
   {"id":"letterhead","text":"The reference letter must be on company letterhead.",
    "citations":["pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#019"],
    "quote":"should be an official document printed on company letterhead"}],
 "basis":["Applicant declares skilled work experience for the Express Entry claim."],
 "abstentions":[],"prose":""}
JSON
# → {"ok":true,"command":"ground","result":{"verdict":"pass","total_claims":1,"grounded":1,
#    "ungrounded":0,"violations":[],"out":"personal/output/...md"}}  exit 0
```

### Negative: a confabulated quote fails closed (VERIFIED this session)
```bash
# quote not present in chunk #019 → verdict:"fail", exit 1, writes nothing
# violations:[{"id":"confab","reasons":["quote_not_in_chunk"], ...}]
```

### Discover the generic police-certificate page without leaking a country (VERIFIED)
```bash
corpus-crawler --json search "police certificate" --db corpus/index.db --family guidance --limit 3
# → guidance/police-certificates.md#005, #007, #002  (no per-country relpath)
```

### Conformance harness skeleton (mirror `test_checklist.TestRealCorpus`)
```python
# Source: crawler/tests/test_checklist.py:688-705 pattern
import unittest
from pathlib import Path
from crawler import searchindex, grounding, checklist  # reuse the producer helpers

_DB = Path("corpus/index.db")

@unittest.skipUnless(_DB.is_file(), "real corpus/index.db is local-only — skip when absent")
class TestDocumentAgents(unittest.TestCase):
    def test_employment_reference_letter_grounds_pass(self):
        # baked SHORT query → generic hit → verbatim quote → assemble → gate
        item = {"doc_type": "employment-reference-letter",
                "query": "reference letter company letterhead",
                "text": "The employment/reference letter must meet IRCC content requirements.",
                "basis": "Applicant declares skilled work experience."}
        claim = checklist.grounded_claim(_DB, item)      # reuse shipped loop (or shell `search`)
        self.assertIsNotNone(claim)                       # citable → not an abstention
        answer = {"question": "...", "claims": [claim], "basis": [item["basis"]],
                  "abstentions": [], "prose": ""}
        self.assertEqual(grounding.check_answer(answer, _DB)["verdict"], "pass")

    def test_confabulation_fails_closed(self):
        bad = {"question": "...", "claims": [{"id": "x", "text": "...",
               "citations": ["pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#019"],
               "quote": "the letter must be notarized by a lawyer within 30 days"}],
               "basis": [], "abstentions": [], "prose": ""}
        self.assertEqual(grounding.check_answer(bad, _DB)["verdict"], "fail")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v1.0 doc agents lived in untracked `tools/`+`trial/` (5 agents, never shipped publicly) | v3.0 rebuilds them cleanly into the public tree as plain-Markdown specs over the frozen `--json` contract | v3.0 milestone | Phase 27 is the public rebuild; reuse the shipped gate, add the 6th (employment reference) agent. |
| Per-CLI proprietary skill formats | Canonical `AGENTS.md` + portable `skills/` Markdown + thin per-CLI pointer adapters; tools as shell commands | 2025 cross-CLI convention (STACK.md) | Lowest-common-denominator design robust to per-CLI churn. [CITED: .github/copilot-instructions.md] |

**Deprecated/outdated:**
- The STACK.md's early `uv run pr-tools <verb>` / `typer` naming is **aspirational** — the SHIPPED
  CLI is `corpus-crawler` (argparse, `crawler.cli:main`). Agent specs must use `corpus-crawler
  --json search/ground`, not `pr-tools`. [VERIFIED: pyproject.toml `[project.scripts]`]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Skills should live at repo-root `skills/document-agents/` (vs `crawler/agents/`). | Project Structure / Open Q1 | Low — pure placement choice; both work. Planner/user should confirm. STACK.md favours root `skills/`; AGENT_SKILL.md precedent favours `crawler/`. |
| A2 | The conformance harness is a `@skipUnless` pytest test (+ optional shell-subprocess of `ground`), not a literal 4-CLI run. | Validation Architecture | Low — a literal multi-CLI run is impractical in CI; the trust path is CLI-independent by construction, so a single gate test is the honest proof. If the user wants a literal per-CLI demo, add a shell-subprocess variant. |
| A3 | The employment-reference agent should cite the *proof-of-work-experience* letter (#019), not the *arranged-employment job-offer* letter (#034/#000). | Corpus Citability Map | Medium — citing the wrong letter would verify the wrong elements. Strongly supported by CONTEXT ("supports the Express Entry skilled work-experience claim") + the IRCC section headings, but worth a human glance. |

**If this table is empty:** (it is not) — these three are placement/shape choices, not factual gaps;
all six agents' *citability* is VERIFIED, not assumed.

## Open Questions (RESOLVED)

> Resolved by the orchestrator and implemented in the plans:
> **Q1 (spec placement)** — RESOLVED: skills live in a new top-level `skills/document-agents/`; per-CLI pointers are additive only and never clobber the GSD-managed `AGENTS.md`/`.github/copilot-instructions.md` blocks.
> **Q2 (one query per agent vs per element)** — RESOLVED: one baked `search` query per agent that lands the verified generic chunk, then per-element verbatim quotes against that resolved chunk (employment letter → chunk `#019`).


1. **Where do the six specs + `_contract.md` live?**
   - What we know: STACK.md/copilot-instructions recommends canonical `AGENTS.md` + portable
     `skills/` + thin per-CLI pointers; the existing `crawler/AGENT_SKILL.md` precedent puts the
     portable skill inside `crawler/` (which is also the pip-packaged dir). Root `AGENTS.md` is
     currently GSD-managed.
   - What's unclear: root `skills/document-agents/` vs `crawler/agents/`.
   - Recommendation: **`skills/document-agents/`** (matches the documented harness intent; the
     corpus is git-ignored/local so pip-packaging the specs isn't required). Add a one-line redirect
     from `AGENTS.md` and `.github/copilot-instructions.md`. If the team prefers pip-shipped specs
     next to `AGENT_SKILL.md`, use `crawler/agents/` instead. Planner should pick one and be
     consistent.

2. **One baked query per agent, or one per element?**
   - What we know: the employment-reference letter needs several elements but they all live in ONE
     chunk (#019), so a single query that lands #019 can ground all six element-claims (each claim
     quotes a different verbatim span of the same chunk). Other agents are single-requirement.
   - Recommendation: bake one query per *claimable span* you intend to emit; for the
     employment-reference agent, one query that reliably returns #019 plus six per-element verbatim
     quotes against that one resolved chunk. Keep all queries 2-4 tokens.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/python` | All tooling (bare `python` is BROKEN — CRLF shim) | ✓ | 3.10.12 | none — MUST use `.venv/bin/python` / `corpus-crawler` |
| `corpus-crawler` console script | `search` / `ground` shell calls | ✓ | 2.0.0 (`.venv/bin/corpus-crawler`) | `.venv/bin/python -m crawler.cli` |
| `corpus/index.db` (FTS5, 742 docs) | Retrieval + grounding | ✓ | 14 MB, built 2026-06-21 | none — git-ignored/local-only; conformance test must `@skipUnless` it |
| pytest | Conformance suite | ✓ | 9.0.3 | none |
| `scripts/check_publish_safe` | Publish-safe scan (already inside `ground`) | ✓ | in-repo | none |
| SQLite FTS5 | `search` ranked path | ✓ | host SQLite has FTS5 (index built + queried successfully) | fail-loud `missing_dependency`/exit 3 if absent |

**Missing dependencies with no fallback:** none — every primitive this phase needs is present and
exercised end-to-end this session.
**Missing dependencies with fallback:** `corpus-crawler` → `python -m crawler.cli` (both verified).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 running unittest-style `TestCase` classes |
| Config file | none (no pytest.ini/pyproject `[tool.pytest]`); tests discovered under `crawler/tests/` |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -q` |
| Full suite command | `.venv/bin/python -m pytest crawler/tests -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CHK-03 | Each of 6 baked questions grounds to `verdict:"pass"` with a deterministic citation set over the live index | integration (real-corpus) | `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -k grounds_pass -q` | ❌ Wave 0 |
| CHK-03 | A confabulated quote fails closed (`quote_not_in_chunk`, no write) | unit/integration | `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -k confabulation -q` | ❌ Wave 0 |
| CHK-03 | An element with no corpus support yields an explicit abstention (zero claims), not a bare claim | integration | `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -k abstain -q` | ❌ Wave 0 |
| CHK-03 | Police-cert citations are GENERIC (no `police-certificates/<country>` relpath) | integration | `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -k police_generic -q` | ❌ Wave 0 |
| CHK-03 | Rendered bytes are publish-safe (scan rendered output only, NOT whole tree) + PII-free | integration | `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -k publish_safe -q` | ❌ Wave 0 |
| CHK-03 | No spec inlines a volatile value / proprietary front-matter (grep guard over `skills/document-agents/*.md`) | static guard | `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -k no_inlined -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_document_agents.py -q`
- **Per wave merge:** `.venv/bin/python -m pytest crawler/tests -q` (note pre-existing
  `dupaudit::TestRealCorpus` failure is unrelated/out-of-scope per STATE.md)
- **Phase gate:** Full suite green (minus the known unrelated dupaudit real-corpus case) before
  `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `crawler/tests/test_document_agents.py` — covers CHK-03 (grounds-pass per agent, confabulation
  fail-closed, abstention, police-generic, publish-safe rendered bytes, no-inlined-values guard)
- [ ] No new conftest/fixtures required — reuse `corpus/index.db` `@skipUnless` pattern + the
  in-repo `scripts/check_publish_safe.scan_text` import shim from `test_checklist.py`
- [ ] Framework install: none (pytest 9.0.3 already present)

## Security Domain

> `security_enforcement: true`, ASVS level 1, block_on `high`. The dominant security property here is
> **PII non-leakage** (CHK-02 inheritance), not classic web auth.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface (local CLI, no network). |
| V3 Session Management | no | Stateless shell invocations. |
| V4 Access Control | no | Single local user; PII access is filesystem-scoped to git-ignored `personal/`. |
| V5 Input Validation | **yes** | `searchindex._to_match` (FTS5 injection-safe, param-bound); `grounding._validate_shape` (answer-shape validation → `InvalidAnswer`/exit 2); empty/degenerate quote fail-closed. All shipped + reused. |
| V6 Cryptography | no | No crypto; no secrets handled by this phase. |
| V7 Error Handling & Logging | **yes** | Error messages must carry NO PII (the `checklist.load_profile` CR-01 rule: YAML errors surface line/col, never the offending source line). Specs/tests must not echo profile bytes. |
| V8 Data Protection (PII) | **yes (primary)** | Generic `claims[].text`/`quote`/`citations`; PII confined to `basis[]`; render-then-scan-then-write to `personal/output/` only; per-country relpath backstop. All shipped (Phase 25/26) and reused UNMODIFIED. |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Confabulated requirement passing as cited | Spoofing (of authority) | Fail-closed grounding gate (`quote_not_in_chunk`); verified. |
| Residence-history leak via per-country relpath citation | Information Disclosure | `--family guidance` + `_is_country_specific` relpath backstop (threat T-26-08). |
| Employer name / dates / salary leaking into rendered output | Information Disclosure | PII-tier split (claims generic, basis personal) + publish-safe rendered-bytes scan + `personal/` containment. |
| FTS5 query injection via crafted requirement text | Tampering | `_to_match` tokenizes on `\w+` and param-binds MATCH; verified injection-safe. |
| Volatile value rot (stale hardcoded date/amount) | Tampering (integrity) | "No inlined volatile values" rule; quote from corpus with citation; static grep guard test. |
| PII echoed in an error/log line | Information Disclosure | PII-free error messages (CR-01); never `str(exc)` from a personal-profile YAML error. |

## Project Constraints (from copilot-instructions.md)

- **No PII in the public repo** — personal data/documents stay in a local, git-ignored area
  (`personal/`), structurally separate from the shareable harness. (Hard constraint.)
- **CLI-agnostic harness** — must work across Antigravity, OpenAI Codex, Claude, GitHub Copilot
  **without** proprietary CLI dependencies. Canonical `AGENTS.md` + portable `skills/` Markdown +
  thin per-CLI pointer adapters; tools invoked as ordinary shell commands.
- **Grounding** — all requirement claims must carry a citation to the curated authoritative corpus
  (IRCC / IRPA / IRPR / PDIs); no ungrounded assertions.
- **Source authority** — corpus limited to authoritative sources; third-party/blog content is not
  authoritative (already enforced upstream by the corpus; agents only cite the index).
- **No vectors/embeddings, no cloud APIs** — local SQLite FTS5 keyword retrieval only.
- **What NOT to use:** proprietary per-CLI tool/skill formats as the source of truth; storing
  personal docs/answers in the repo or corpus DB; LangChain/LlamaIndex/CrewAI as the harness runtime.
- **Test convention:** pytest over saved fixtures / real-corpus `@skipUnless` integration.
- **Note (tension to flag to planner):** STACK.md names the canonical pointer as root `AGENTS.md`,
  but `AGENTS.md` and `.github/copilot-instructions.md` are currently GSD-installer-managed. The
  per-CLI redirect to `skills/document-agents/` must be added without clobbering GSD config blocks.

## Sources

### Primary (HIGH confidence)
- `crawler/grounding.py` — answer-object schema, `check_answer`/`quote_is_grounded`/`render_answer`,
  honesty boundary, fail-closed reasons. (read in full)
- `crawler/checklist.py` — Phase-26 producer pattern: `grounded_claim`, `_verbatim_quote`,
  `_is_country_specific`, PII-tier split, abstention. (read in full)
- `crawler/searchindex.py` — `search`/`resolve`/`_to_match` (tokens AND'd), `--family` filter.
- `crawler/cli.py` — `_cmd_search`/`_cmd_ground`/`_cmd_checklist` dispatch, `personal/` containment.
- `crawler/CONTRACT.md` + `crawler/AGENT_SKILL.md` — the frozen `--json` envelope + portable-skill
  convention to mirror.
- `corpus/index.db` (live, 742 docs) — verified citability of all six doc types via
  `corpus-crawler --json search`, `search --cite <id>`, `ground` (end-to-end pass + fail-closed),
  and `grounding.quote_is_grounded` element checks. (this session)
- `.planning/CONTEXT.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `PROJECT.md`, `STATE.md`, `config.json`.

### Secondary (MEDIUM confidence)
- `.github/copilot-instructions.md` (STACK.md) — canonical harness pattern, what-not-to-use,
  packaging intent. (project doc; some `pr-tools`/`uv` naming is aspirational vs the shipped
  `corpus-crawler`.)

### Tertiary (LOW confidence)
- none — all technical claims verified against in-repo code or the live corpus this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all in-repo/stdlib, verified by execution; no external packages.
- Architecture / patterns: HIGH — mirrors shipped `checklist.py`/`grounding.py`; pipeline run
  end-to-end this session.
- Corpus citability (all six agents, incl. employment reference letter): HIGH — every element
  resolved + quote-checked + ground-passed against the live index this session.
- Pitfalls: HIGH — each reproduced this session (confabulation fail, country-page leak, family
  filter, whole-tree scan red).
- Placement / conformance-harness shape: MEDIUM — sound recommendation, but a discretion choice
  (see Assumptions A1/A2).

**Research date:** 2026-06-21
**Valid until:** ~2026-07-21 for code/contract facts (stable, frozen schema_version "1.0"). Corpus
chunk_ids valid while `corpus/index.db` is byte-identical; agents bake QUERIES not ids, so query-level
findings outlive a rebuild. Re-verify citations if the corpus is re-crawled/re-indexed.
