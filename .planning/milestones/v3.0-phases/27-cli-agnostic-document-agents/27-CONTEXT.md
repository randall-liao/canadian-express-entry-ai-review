# Phase 27: CLI-Agnostic Document Agents - Context

**Gathered:** 2026-06-21
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Six portable markdown document-agent skills (police certificate, language test, ECA, proof of
funds, medical, **employment reference letter**) answer document questions by consuming the `search`
contract and emitting only gated, cited claims — identically across CLIs.

Requirements: CHK-03. Depends on Phase 25 (the `ground` gate) and Phase 24 (`search`); reuses the
local profile-slice pattern from Phase 26.

Success criteria (from ROADMAP):
1. Each of the six document agents is a thin plain-Markdown skill sharing one `_contract.md` (no
   proprietary front-matter) that retrieves via `corpus-crawler --json search`, copies a verbatim
   `quote` per claim from the retrieved chunk, and pipes its structured answer to
   `corpus-crawler --json ground`. [CHK-03]
2. An agent emits ONLY cited claims; when the corpus has no answer it emits zero claims with an
   explicit `abstention` ("not in corpus") rather than confabulating, and the gate refuses any
   ungrounded output. [CHK-03]
3. Per-CLI conformance: the same question run under Antigravity / Codex / Claude / Copilot passes the
   gate with the same resolved citation set — no CLI-native tooling sits in the trust path (all logic
   is in the Python gate + shell `search`). [CHK-03]
4. The employment reference letter agent verifies an Express Entry employment/reference letter's
   required elements (e.g. company letterhead/contact, signatory + title, job title(s),
   dates/period of employment, hours/full-time status, annual salary + benefits, detailed duties) —
   each requirement statement gated + cited to the corpus, never hardcoded; no PII (employer name,
   dates, salary) in `claims[].text`. [CHK-03]

</domain>

<decisions>
## Implementation Decisions

### Agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use the ROADMAP goal, success criteria, codebase conventions, and the existing
`crawler/AGENT_SKILL.md` portable-skill convention to guide decisions.

Locked anchors to honor:
- Each agent is PLAIN MARKDOWN with NO proprietary front-matter and NO dependency on any single CLI's
  tool/MCP API — everything is an ordinary shell command (`corpus-crawler --json search` /
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

</decisions>

<code_context>
## Existing Code Insights

Codebase context gathered during plan-phase research. Facts established by the orchestrator:
- `crawler/AGENT_SKILL.md` is the existing portable, CLI-agnostic markdown skill (drives the crawler
  pipeline via `corpus-crawler --json <subcommand>`) — Phase 27 follows this exact convention.
- Shipped primitives the agents consume (NO new code needed in the trust path, only the markdown
  skills + a shared contract + a conformance harness): `corpus-crawler --json search` /
  `--json search --cite <id>` (Phase 24), `corpus-crawler --json ground` (Phase 25, reads the answer
  JSON on stdin, fail-closed, renders to personal/output/), `corpus-crawler --json checklist`
  (Phase 26). The frozen envelope: schema_version "1.0", 5 keys, exit-code taxonomy.
- The employment reference letter is a NEW (6th) document type — the existing/planned 5 were police
  certificate, language test, ECA, proof of funds, medical. It supports the Express Entry skilled
  work-experience claim.
- Likely placement: a portable `agents/` (or `skills/document-agents/`) directory of plain-markdown
  specs + one shared `_contract.md`; the planner/researcher confirm the exact location + conformance
  harness shape (a small script/test that proves a grounded question passes the gate identically).

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond the ROADMAP success criteria — discuss phase skipped. Likely shape:
a portable directory of six plain-markdown document-agent skills + one shared `_contract.md`, each
teaching the agent to (1) read the local profile slice for applicability (basis[]), (2) retrieve
each requirement from the corpus via `corpus-crawler --json search`, (3) copy the verbatim quote,
(4) assemble the Phase-25 answer object with gated PII-free claims[], (5) pipe it to
`corpus-crawler --json ground`, abstaining when the corpus has no answer; plus a per-CLI conformance
check proving identical behavior.

</specifics>

<deferred>
## Deferred Ideas

- Layer-2 per-document rule matching (recency/amounts/format/translation verification) — VAL-01;
  Phase 27 agents answer document questions (which requirements + cited), not full Layer-2 validation.

</deferred>
