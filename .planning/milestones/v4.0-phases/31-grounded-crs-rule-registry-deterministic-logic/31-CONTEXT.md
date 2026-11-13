# Phase 31: Grounded CRS Rule Registry & Deterministic Logic - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Auditors have a PII-free, corpus-grounded CRS rule registry and deterministic CRS logic before
any factor verdicts are implemented. Requirements: RULE-01, RULE-02, RULE-03, RULE-04, RULE-05.

Success criteria (what must be TRUE):
1. For every CRS factor group, registry rows capture accepted proof types, validity windows,
   issuers, thresholds, caps, and admissibility predicates with resolving corpus citations and
   verbatim quotes.
2. Every registry rule validates through the existing `search`/`--cite`/grounding gate, and static
   checks reject volatile CRS thresholds hard-coded in auditor prose.
3. A coverage report shows the full CRS grid across core human capital, spouse/common-law, skill
   transferability, and additional points with no missing required rule rows.
4. Deterministic Python logic computes CLB/NCLC conversion, date math, duration aggregation,
   spouse mode, transferability caps, and cutoff comparison from grounded rule rows.
5. A non-zero arranged-employment additional-CRS claim is treated as `AT-RISK`/0 unless ITA-era
   corpus rules ground a legacy or exception case.

</domain>

<decisions>
## Implementation Decisions

### The agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use ROADMAP phase goal, success criteria, project constraints, and codebase conventions.

### This phase is PII-FREE and PUBLIC (unlike 29/30)
The CRS rule registry is a precomputed, PII-free, cited table generated/validated FROM the local
authoritative corpus. It lives in the public tree (e.g. `crawler/data/crs_rules/*.yaml` +
`crawler/crs_rules.py`), NOT in the vault. It must never contain applicant PII. Deterministic CRS
math (`crawler/crs_audit.py` or similar) is also public/tested Python.

### Grounding is mandatory (reuse frozen v3.x primitives)
- Every registry rule row carries: query/selector/source-family, a machine check, a `citation_id`,
  a verbatim quote, and volatility/staleness metadata — and must RESOLVE + verbatim-ground through
  the existing `search` → `--cite` → grounding gate (`corpus-crawler --json ground`). Reuse the
  shipped resolver/gate; do NOT build a new trust path.
- A static check must REJECT volatile CRS thresholds hard-coded in auditor prose (rules live in the
  registry, cited — not inlined in agent markdown).
- Source-family allow/deny lists + marker selection + retrieve-what-you-cite tests prevent
  historical/adjacent chunks from grounding the wrong rule.

### Full CRS grid coverage (per research FEATURES-v4.0 / SUMMARY-v4.0 per-factor map)
Four factor groups: (A) core human capital — age, education, first & second official language,
Canadian work experience; (B) spouse/common-law — education, language, Canadian work; (C) skill
transferability — education×language, education×Canadian-work, foreign-work×language,
foreign-work×Canadian-work, certificate-of-qualification×language (with caps: education combos ≤50,
foreign-work combos ≤50, total ≤100); (D) additional points — provincial nomination, arranged
employment (current CRS points = 0 unless ITA-era legacy proven — RULE-05), Canadian study,
strong French, sibling in Canada. Include CLB/NCLC conversion tables, language-test & ECA validity
windows, accepted test/issuer lists, work definitions (NOC TEER 0-3, ≥30h/wk, within 10y), and
spouse-vs-no-spouse point tables — each grounded.

### Locked constraints
- Retrieval remains SQLite FTS5 keyword-only; no vectors/embeddings/cloud. Poetry-managed Python;
  pydantic models. Do NOT modify the frozen v3.x trust path or the Phase 29/30 vault.

</decisions>

<code_context>
## Existing Code Insights

Confirmed during plan-phase research. Build on the shipped v3.x grounding stack: `crawler`'s
`search`/`--cite` resolver, the `--json ground` grounding gate, `crawler/CONTRACT.md` envelope,
the corpus SQLite/FTS5 index, and the 22 existing document-agent markdown specs (pattern for
short-query + non-volatile marker selection + grounded quotes). Reference research:
`.planning/research/ARCHITECTURE-v4.0.md` (`crawler/data/crs_rules/*.yaml`, `crawler/crs_rules.py`,
`crawler/crs_audit.py`), `.planning/research/FEATURES-v4.0.md` (per-factor document→threshold→
admissibility map), `.planning/research/PITFALLS-v4.0.md` (hard-coded volatile rules, wrong-chunk
grounding, CRS math/cap errors, arranged-employment repeal → tests).

</code_context>

<specifics>
## Specific Ideas

Refer to ROADMAP Phase 31 description, the five success criteria above, and the v4.0 research
files for the registry schema (per-factor rows with citation + verbatim quote + volatility
metadata), the grounding-validation harness (reuse the gate), the static "no inlined volatile
rule" check, the CRS-grid coverage report, deterministic CRS math, and the arranged-employment
guard.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
