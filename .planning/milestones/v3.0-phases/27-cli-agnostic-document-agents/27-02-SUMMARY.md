---
phase: 27-cli-agnostic-document-agents
plan: 02
subsystem: document-agents
tags: [markdown-skills, cli-agnostic, corpus-crawler, grounding, pii-containment, police-certificate, language-test, eca]

# Dependency graph
requires:
  - phase: 27-01
    provides: "skills/document-agents/_contract.md (shared 5-key answer object + search→quote→ground→abstain loop + abstention/PII/no-inlined-values rules + exit-code table) and README.md skill-pack index"
provides:
  - "skills/document-agents/police-certificate.md — police/criminal-record certificate agent with --family guidance + police-certificates/<country> relpath no-leak backstop"
  - "skills/document-agents/language-test.md — approved-language-test agent"
  - "skills/document-agents/eca.md — foreign Educational Credential Assessment agent (curly-apostrophe verbatim-copy hazard flagged)"
affects: [27-03, 27-04, 27-05, document-agents conformance harness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin plain-Markdown agent: link _contract.md, bake a SHORT 2-4-token search query (never a chunk_id), describe the loop by reference, one worked example via corpus-crawler + .venv/bin/python/jq"
    - "Residence-history no-leak backstop: --family guidance + skip any police-certificates/<country> relpath + abstain rather than cite a leaky page (mirrors checklist._is_country_specific / grounded_claim)"

key-files:
  created:
    - skills/document-agents/police-certificate.md
    - skills/document-agents/language-test.md
    - skills/document-agents/eca.md
  modified: []

key-decisions:
  - "Baked the police query as `police certificate every country` (digit-free) instead of the plan's suggested `police certificate 10 years country`, because the literal `10 years` trips Task 1's own no-inlined-values acceptance gate; the substitute lands the identical generic chunk guidance/police-certificates.md#002 under --family guidance (verified live)."
  - "No corpus span is inlined into any agent body; worked examples use placeholder tokens (<chunk_id>, <relpath#NNN>, <verbatim span ...>) so the agent copies the real quote at runtime."
  - "Flagged the curly-apostrophe (U+2019) verbatim-copy hazard in eca.md, since the grounding gate normalizes whitespace+case only and a straight-apostrophe retype fails quote_not_in_chunk."

patterns-established:
  - "Pattern: generic-claim / PII-basis split per agent — the requirement label is the only thing in claims[]; countries, dates, institutions, scores stay in basis[]"
  - "Pattern: defense-in-depth relpath backstop applied in the worked example itself (filter hits whose chunk_id startswith police-certificates/)"

requirements-completed: []  # CHK-03 spans plans 27-02..27-05; this plan advances CHK-03 SC1 (3 of 6 agents) + SC2 (police no-leak). Not marking CHK-03 fully complete — orchestrator owns phase/requirement closure.

# Metrics
duration: 7min
completed: 2026-06-21
---

# Phase 27 Plan 02: Police-Certificate, Language-Test & ECA Document Agents Summary

**Three thin, plain-Markdown CLI-agnostic document agents that bake a short corpus-crawler search query, copy a verbatim generic quote, and ground it — with the police agent enforcing the residence-history no-leak backstop (--family guidance + per-country relpath skip + abstention).**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-21T13:59:24Z
- **Completed:** 2026-06-21T14:06:38Z
- **Tasks:** 3
- **Files modified:** 3 (all created)

## Accomplishments
- **police-certificate.md** (132 lines): links `_contract.md`, bakes `police certificate every country`, mandates `--family guidance`, and spells out the two-layer no-leak backstop (skip any `police-certificates/<country>` relpath; abstain with `not_in_corpus` rather than cite a leaky page) mirroring `checklist._is_country_specific` / `grounded_claim`. The worked example applies the relpath filter in-line.
- **language-test.md** (96 lines): links `_contract.md`, bakes `language test approved results`, describes the search→quote→ground→abstain loop by reference, emits one generic "approved test" claim with test choice/scores confined to `basis[]`.
- **eca.md** (102 lines): links `_contract.md`, bakes `foreign educational credential assessment`, flags the curly-apostrophe verbatim-copy hazard, emits one generic "assessed by a designated organization" claim.
- All baked queries verified live against `corpus/index.db`: police→`guidance/police-certificates.md#002` (generic, non-leaky), language→`guidance/language-test.md#001`, eca→`eca/educational-credential-assessment.md#014`.

## Task Commits

Each task was committed atomically (hooks ran, no `--no-verify`):

1. **Task 1: Author police-certificate.md (with the country no-leak backstop)** - `2f9a870` (feat)
2. **Task 2: Author language-test.md** - `e7c2910` (feat)
3. **Task 3: Author eca.md** - `215b934` (feat)

**Plan metadata:** see final docs commit (this SUMMARY + STATE + ROADMAP).

## Files Created/Modified
- `skills/document-agents/police-certificate.md` - Police/criminal-record certificate agent; `--family guidance` + `police-certificates/<country>` relpath backstop + abstention.
- `skills/document-agents/language-test.md` - Approved-language-test agent.
- `skills/document-agents/eca.md` - Foreign Educational Credential Assessment agent (curly-apostrophe hazard flagged).

## Decisions Made
- **Police baked query substitution** (see Deviations): used `police certificate every country` instead of `police certificate 10 years country` to satisfy the no-inlined-values gate while landing the identical generic chunk.
- **No inlined corpus spans / values:** every quote is a runtime placeholder; no requirement number (age threshold, residence window, score, dollar amount) is hand-typed into any agent body.
- **Curly-apostrophe note in eca.md:** instructs copying exact bytes from `result.chunk.text` because `grounding._norm` does not normalize apostrophes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Police baked query reworded to clear the plan's own no-inlined-values gate**
- **Found during:** Task 1 (police-certificate.md)
- **Issue:** The plan's suggested baked query `police certificate 10 years country` literally contains `10 years`, which matches Task 1's acceptance criterion 6 (`grep -nE '[0-9]+ (months|years|days)|\$[0-9]'` must return no matches) and the phase-wide no-inlined-values rule (threat T-27-06). Baking it verbatim would fail the file's own gate — an internal inconsistency in the plan.
- **Fix:** Baked the digit-free equivalent `police certificate every country`, verified live to land the identical generic chunk `guidance/police-certificates.md#002` under `--family guidance` (and even without the family filter). The grader's hardcoded live-check (acceptance criterion 7, which runs the fixed `police certificate 10 years country` command independent of file content) still returns the same non-leaky generic relpath.
- **Files modified:** skills/document-agents/police-certificate.md
- **Verification:** `grep -nE '[0-9]+ (months|years|days)|\$[0-9]'` returns nothing; both `police certificate every country` and the grader's `police certificate 10 years country` resolve to `guidance/police-certificates.md#002` with `--family guidance`.
- **Committed in:** 2f9a870 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — internal plan inconsistency)
**Impact on plan:** Minimal. The fix preserves the verified citation target and the no-leak guarantee while satisfying the plan's own acceptance gate. No scope creep; the conceptual `key_link` (police → `guidance/police-certificates.md` via `--family guidance`) and the `pattern: "family guidance"` check are both honored.

## Issues Encountered
None — all per-task acceptance gates, the `<automated>` verify gates, and the plan-level `<verification>` block passed on the first pass after the query substitution.

## Known Stubs
None. The agents are author specs that drive shipped primitives by reference; they introduce no placeholder data sources, no empty returns, and no "coming soon" text. Worked-example placeholders (`<chunk_id>`, `<relpath#NNN>`, `<verbatim span ...>`) are intentional runtime-fill tokens, per the contract's "never inline a pasted corpus span" rule — not stubs.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 3 of the 6 document agents shipped; `_contract.md` proven to drive police/language/ECA. Plans 27-03/27-04 add the remaining agents (proof-of-funds, medical, employment-reference-letter); Plan 27-05 adds the conformance harness + the phase-wide grep gates.
- The police-certificate no-leak backstop is documented in prose AND demonstrated in its worked example, ready for the `police_generic` conformance test in Plan 27-05.
- Phase NOT marked complete — orchestrator owns phase/requirement closure (CHK-03 spans plans 02–05).

## Self-Check: PASSED

- FOUND: skills/document-agents/police-certificate.md
- FOUND: skills/document-agents/language-test.md
- FOUND: skills/document-agents/eca.md
- FOUND: .planning/phases/27-cli-agnostic-document-agents/27-02-SUMMARY.md
- FOUND commit: 2f9a870 (Task 1, police-certificate.md)
- FOUND commit: e7c2910 (Task 2, language-test.md)
- FOUND commit: 215b934 (Task 3, eca.md)

---
*Phase: 27-cli-agnostic-document-agents*
*Completed: 2026-06-21*
