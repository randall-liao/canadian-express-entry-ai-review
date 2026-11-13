# Phase 34: Safety Conformance & Release Framing - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Release only when automated conformance proves fail-closed behavior, privacy containment, intended
rule grounding, and substantiation-screening framing. Requirements: SAFE-01, SAFE-02, SAFE-03,
SAFE-04.

Success criteria (what must be TRUE):
1. Conformance tests prove no `pending`, unconfirmed, low-confidence, or stale value can produce a
   `SUBSTANTIATED` verdict.
2. Privacy tests prove PII cannot reach stdout, the repo, the corpus, public reports, tracked
   fixtures, or non-vault output paths.
3. Retrieve-what-you-cite tests prove every registry rule grounds the intended current rule rather
   than a historical, adjacent, or wrong-family chunk.
4. Release docs and report wording frame the output as CRS substantiation screening and not legal
   advice.

</domain>

<decisions>
## Implementation Decisions

### The agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use ROADMAP phase goal, success criteria, project constraints, and codebase conventions.

### This is the RELEASE-GATE / hardening phase — the product promise is trust
Consolidate and harden the safety guarantees established across Phases 29–33 into an authoritative
conformance suite plus release documentation. Prefer strengthening/formalizing existing tests into
a clearly-labeled conformance layer over inventing new behavior. Reuse the synthetic/adversarial
fixture patterns already introduced in earlier phases; never introduce real PII into tracked
fixtures.

### Builds on shipped Phases 29–33
- Phase 29 vault + PII perimeter (publish-safe `VAULT_ARTIFACT`, `.gitignore`, path-guard).
- Phase 30 extraction quarantine (`is_audit_eligible`, five-key staleness) + `doctor`.
- Phase 31 grounded CRS registry (grounding-gate validation, retrieve-what-you-cite, no-inlined-
  volatile-rule static check, COVERAGE.md).
- Phase 32 audit slice fail-closed contract (no partial report on gate failure; PII-light public
  envelope; vault-only evidence-bearing report).
- Phase 33 full four-module auditor pack + factor cards + cutoff comparison.

### Locked constraints (from PROJECT.md / research SUMMARY-v4.0 / PITFALLS-v4.0)
- **SAFE-01 (no false green):** conformance proves NO `pending`/unconfirmed/low-confidence/stale
  value can ever yield `SUBSTANTIATED` — across all four modules and the full factor grid.
- **SAFE-02 (privacy containment):** prove PII cannot reach stdout, the repo, the corpus, public
  reports, tracked fixtures, or any non-vault output path; non-vault output paths are refused.
- **SAFE-03 (retrieve-what-you-cite):** prove every registry rule grounds the INTENDED current rule,
  not a historical / adjacent / wrong-family chunk (source-family allow/deny + marker selection).
- **SAFE-04 (framing):** release docs + report wording frame output as CRS substantiation SCREENING,
  not legal advice; `SUBSTANTIATED` is defined narrowly; semantic/NOC-duty fit + officer discretion
  stay `AT-RISK`.
- Reuse frozen v3.x primitives + Phases 29–33; no new trust path. Poetry-managed Python; SQLite
  FTS5 keyword-only; no vectors/cloud. All PII stays in the git-ignored vault.
- Documentation changes framed generically (no dev-machine specifics/PII); keep the public repo
  clean and shareable.

</decisions>

<code_context>
## Existing Code Insights

Confirmed during plan-phase research. Consolidate the safety tests from Phases 29–33 into an
authoritative conformance suite and write release docs. Reference research:
`.planning/research/PITFALLS-v4.0.md` (the full pitfall→prevention table maps directly to
conformance tests) and `.planning/research/SUMMARY-v4.0.md` "Phase 6: Conformance, Safety
Hardening, and Release Docs" (synthetic fixture corpus, adversarial extraction cases,
retrieve-what-you-cite tests, no-PII stdout tests, non-vault output refusal tests,
stale-invalidation tests, screening-not-legal-advice framing).

</code_context>

<specifics>
## Specific Ideas

Refer to ROADMAP Phase 34 description, the four success criteria above, and the v4.0 research
release-hardening plan. Deliver: a labeled conformance suite (no-false-green, privacy-containment,
retrieve-what-you-cite, stale-invalidation, non-vault-output-refusal) and release docs framing the
tool as substantiation screening, not legal advice.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
