# Phase 33: Full Modular CRS Auditor Pack - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Applicant can audit every claimed CRS factor through four context-light modules and see
substantiated points plus ITA cutoff risk. Requirements: AUDIT-01, AUDIT-03, AUDIT-04, AUDIT-05.

Success criteria (what must be TRUE):
1. Every claimed or applicable CRS factor returns exactly one `SUBSTANTIATED`, `GAP`, `AT-RISK`, or
   `N/A` verdict with a grounded rule citation and private evidence pointer.
2. Core human capital, spouse/common-law, skill transferability, and additional-points auditors run
   as separate context-light modules through the frozen v3.x primitives with no new trust path.
3. Applicant can inspect factor cards showing claimed value, confirmed extracted value,
   substantiated points, score delta, evidence pointer, and rule citation.
4. The audit compares the substantiated CRS total against the ITA round cutoff and surfaces
   score-impact risk without giving legal advice.
5. Multi-document aggregation, spouse/principal ownership, work-interval conflicts, and
   transferability dependencies surface as factor-level `GAP` or `AT-RISK` findings rather than
   hidden document-level passes.

</domain>

<decisions>
## Implementation Decisions

### The agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use ROADMAP phase goal, success criteria, project constraints, and codebase conventions.

### Fans out the Phase 32 vertical slice to the full CRS grid
Phase 32 proved the end-to-end audit contract (confirmed evidence + grounded rules + deterministic
comparator + grounding gate + fail-closed verdict + vault-only report) on one pilot factor. Phase
33 replicates that proven contract across ALL CRS factors as four context-light modules — do NOT
invent a new trust path or verdict mechanism; reuse the Phase 32 slice's audit core.

### Four modules (per research SUMMARY-v4.0 per-factor map + skills/ document-agent pattern)
- **Core human capital** — age, education, first & second official language, Canadian work.
- **Spouse/common-law** — spouse education, language, Canadian work (only when an accompanying
  spouse/CLP who is not a citizen/PR; else score no-spouse mode and mark spouse rows `N/A`).
- **Skill transferability** — education×language, education×Canadian-work, foreign-work×language,
  foreign-work×Canadian-work, certificate-of-qualification×language (consume already-substantiated
  core values; enforce caps 50/50/100).
- **Additional points** — provincial nomination, arranged employment (current CRS = 0 unless
  ITA-era legacy proven — never auto-green), Canadian study, strong French, sibling in Canada.
Keep each module context-light (mirror the portable-markdown pattern of the 22 v3.1 document
agents: short query + non-volatile marker selection + grounded quotes).

### Builds on shipped Phases 29–32
- Phase 29 vault, Phase 30 confirmed-evidence (`is_audit_eligible`/staleness), Phase 31
  `crs_rules`/`crs_audit` (grounded rows + deterministic math + caps + arranged-employment guard),
  Phase 32 audit slice core (verdict emission, PII-light public envelope, vault-only private
  report, fail-closed grounding).

### Locked constraints
- Every factor → exactly one verdict (`SUBSTANTIATED`/`GAP`/`AT-RISK`/`N/A`) with a grounded rule
  citation + private evidence pointer. `SUBSTANTIATED` stays fail-closed (Phase 32 rules).
- Factor cards show claimed value, confirmed extracted value, substantiated points, score delta,
  evidence pointer, rule citation — PII-rich cards live ONLY under the vault; public output stays
  PII-light. Compare substantiated total vs ITA cutoff; surface risk WITHOUT legal advice.
- Multi-document aggregation, spouse/principal ownership separation, work-interval overlap, and
  transferability fan-out surface as factor-level `GAP`/`AT-RISK`, never hidden document-level
  passes.
- Reuse frozen v3.x primitives + Phase 29–32 code; no new trust path. Poetry-managed Python;
  pydantic; SQLite FTS5 keyword-only; no vectors/cloud. All PII in the vault.

</decisions>

<code_context>
## Existing Code Insights

Confirmed during plan-phase research. Reuse the Phase 32 audit slice core, the Phase 31
`crs_rules`/`crs_audit`, the Phase 30 confirmed-evidence gates, and the frozen grounding gate/JSON
envelope. Reference research: `.planning/research/ARCHITECTURE-v4.0.md` (four auditor modules under
`skills/crs-auditors/`; factor dependency graph; substantiated total + cutoff comparison) and
`.planning/research/PITFALLS-v4.0.md` (spouse/principal mixups, work-interval overlap, job-offer
trap, over-claiming → tests).

</code_context>

<specifics>
## Specific Ideas

Refer to ROADMAP Phase 33 description, the five success criteria above, and the v4.0 research
per-factor map. Deliver four context-light auditor modules covering the full CRS grid, factor
cards, multi-document aggregation, the factor dependency graph (skill-transferability fan-out from
core), and the substantiated-total-vs-ITA-cutoff comparison.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
