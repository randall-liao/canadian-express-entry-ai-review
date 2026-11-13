# Document Agents — Skill Pack

A **portable, CLI-agnostic** pack of document-requirement agents for Canadian
immigration applications. It is plain Markdown with no proprietary front-matter
and no per-CLI tooling: every trust-path step is an ordinary `corpus-crawler
--json …` shell command plus JSON parsing, so any agent — Antigravity, OpenAI
Codex, Claude, GitHub Copilot, Gemini, or a plain shell script — can drive it.
The entire trust path is the shipped Python grounding gate plus shell `search`;
the agents are thin authors over the frozen Phase 24/25/26 primitives.

## Shared contract

All agents emit the same structured answer object and follow the same
search → verbatim-quote → ground → abstain loop. That single source of truth
lives in **[`_contract.md`](_contract.md)** — read it first; each agent links
back to it rather than restating the schema, the abstention rule, or the
PII-tier split.

## Agents

These agents cover the Express Entry e-APR document set. The first six target
dedicated IRCC guidance pages; the rest each target a section of the canonical
[completeness-check Program Delivery Instruction][cc] (IRCC's authoritative e-APR
document checklist).

[cc]: https://www.canada.ca/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals/permanent-residence/express-entry/completeness-check.html

- **[`police-certificate.md`](police-certificate.md)** — police / criminal
  record certificate requirements (uses `--family guidance` + a per-country
  relpath backstop so a citation never leaks residence history).
- **[`language-test.md`](language-test.md)** — approved language test and
  minimum-result requirements.
- **[`eca.md`](eca.md)** — Educational Credential Assessment requirements for
  foreign education.
- **[`proof-of-funds.md`](proof-of-funds.md)** — settlement-funds / proof-of-funds
  requirements (funds figures are quoted from the corpus, never inlined).
- **[`medical.md`](medical.md)** — immigration medical exam requirements.
- **[`employment-reference-letter.md`](employment-reference-letter.md)** —
  proof-of-work-experience reference letter content for each declared work experience.

**Mandatory for all applicants:**

- **[`passport.md`](passport.md)** — biographical data page of a passport / travel
  document (identity).
- **[`digital-photos.md`](digital-photos.md)** — digital photos meeting IRCC's
  PR-card photo specifications.
- **[`translation.md`](translation.md)** — certified translation requirements for
  any supporting document not in English or French (cross-cutting).

**Mandatory if applicable:**

- **[`job-offer.md`](job-offer.md)** — arranged-employment job-offer letter (distinct
  from the proof-of-work-experience reference letter).
- **[`proof-of-studies.md`](proof-of-studies.md)** — proof of completed education
  (transcripts / diplomas) for education points (distinct from the ECA).
- **[`certificate-of-qualification.md`](certificate-of-qualification.md)** —
  provincial / territorial certificate of qualification in a trade.
- **[`birth-certificate.md`](birth-certificate.md)** — birth document for dependent
  children.
- **[`marriage-certificate.md`](marriage-certificate.md)** — marriage certificate
  (married).
- **[`common-law-union.md`](common-law-union.md)** — statutory declaration of
  common-law union + cohabitation evidence (common-law).
- **[`divorce-certificate.md`](divorce-certificate.md)** — divorce certificate /
  legal separation agreement (divorced).
- **[`death-certificate.md`](death-certificate.md)** — death certificate (widowed).
- **[`adoption-certificate.md`](adoption-certificate.md)** — adoption certificate
  (adopted dependent child).
- **[`use-of-representative.md`](use-of-representative.md)** — Use of a Representative
  form requirements.

**Other documents:**

- **[`relative-in-canada.md`](relative-in-canada.md)** — proof of a relative in
  Canada for adaptability / additional CRS points.
- **[`other-name.md`](other-name.md)** — documentation of another name / alias.
- **[`authority-to-release.md`](authority-to-release.md)** — Authority to Release
  Personal Information form signatories.

## Scope and boundaries

- **PII-free by construction.** Generic requirement labels live in `claims[]`;
  all personalization stays in `basis[]`, which the gate never grounds and the
  renderer never writes. Rendered output goes only to the git-ignored
  `personal/output/` boundary.
- **No inlined volatile values.** Dollar amounts, validity windows, and
  requirement text are quoted verbatim from the corpus with a citation — never
  hand-typed into an agent body.
- **Additive only.** This pack does **not** modify the GSD-installer-managed
  blocks in root `AGENTS.md` or `.github/copilot-instructions.md`. Any per-CLI
  pointer is a separate, optional, additive redirect — never an edit to those
  managed config blocks.

## Conformance and the local-only grounding gate

The conformance harness (`crawler/tests/test_document_agents.py`) is the per-CLI
grounding proof. It feeds the tracked, PII-free fixture
`crawler/eval/document_agents.jsonl` through the shipped grounding gate and — for
each agent — re-runs the skill's own baked query plus its documented
selection rule against the index, proving the agent retrieves a chunk that
verbatim-grounds the quote it cites (not merely that a hand-coded citation
resolves).

That end-to-end proof against the **real IRCC content** is **local-only and not
shipped**. It is `@skipUnless(corpus/index.db)`, and `corpus/index.db` is
**git-ignored** — the corpus is never committed. On CI or a fresh clone the real
index is absent, so the real-corpus conformance is **knowingly skipped**.

**However, a corpus-less CI run is no longer just a structural pass.** An
always-run class, `TestDocumentAgentsConformanceSynthetic`, proves the document-agent
grounding **loop** end-to-end against a *synthetic* index built into a temporary
directory: it runs the same `searchindex.resolve` + grounding gate + `run_eval` over
agent-style answer objects (a grounded line, a confabulated `expect:"ungrounded"`
line that must fail closed, and a `must_abstain` line), so the loop **mechanism** is
verified in CI. Only the real-corpus *citation content* (e.g. the employment letter's
`#019` quotes) is verified locally.

The harness also makes the real-corpus skip impossible to overlook: when the corpus
is absent it (1) skips with a loud `LOCAL-ONLY GROUNDING GATE` reason, (2) raises a
`RuntimeWarning` that surfaces in pytest's default warnings summary, and (3) runs an
always-run guard (`TestGroundingGateLocalOnly`) that asserts the skip wiring matches
corpus presence in both directions. To exercise the real-content gate, build the
corpus locally and run:

```bash
.venv/bin/python -m pytest crawler/tests/test_document_agents.py -q
corpus-crawler --json ground --eval crawler/eval/document_agents.jsonl --db corpus/index.db
```

## Running examples

Bare `python` is broken in this repo (a pyenv-win CRLF shim). Use the
`corpus-crawler` console script for verbs and `.venv/bin/python` (or `jq`) for
JSON parsing; run conformance tests with `.venv/bin/python -m pytest`. Run
everything from `<repo-root>`.
