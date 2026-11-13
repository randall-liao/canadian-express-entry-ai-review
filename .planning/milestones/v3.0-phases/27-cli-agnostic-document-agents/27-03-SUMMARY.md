---
phase: 27-cli-agnostic-document-agents
plan: 03
subsystem: document-agents
tags: [markdown-skills, cli-agnostic, corpus-crawler, grounding, pii-containment, proof-of-funds, medical, ime, volatile-values]

# Dependency graph
requires:
  - phase: 27-01
    provides: "skills/document-agents/_contract.md (shared 5-key answer object + search→quote→ground→abstain loop + abstention/PII/no-inlined-values rules + exit-code table)"
provides:
  - "skills/document-agents/proof-of-funds.md — settlement-funds agent; program applicability (FSW/FST must meet, CEC/PNP exempt) + the applicant's amount confined to basis[]; no dollar figure inlined"
  - "skills/document-agents/medical.md — IME agent; the volatile public-policy exemption date is QUOTED from the corpus chunk at runtime, never written into the body"
affects: [27-04, 27-05, document-agents conformance harness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin plain-Markdown agent: link _contract.md, bake a SHORT 2-4-token search query (never a chunk_id), describe the loop by reference, one worked example via corpus-crawler + .venv/bin/python/jq"
    - "Volatile-value containment: a date/figure that would rot is reproduced ONLY inside a grounded, cited verbatim quote span — never as prose in the agent body (proven on the IME-exemption date, the hardest case)"
    - "Generic-claim / PII-and-applicability-basis split: the requirement label is the only thing in claims[]; program applicability, family size, amount, and exam status stay in basis[]"

key-files:
  created:
    - skills/document-agents/proof-of-funds.md
    - skills/document-agents/medical.md
  modified: []

key-decisions:
  - "Baked `proof settlement funds` for proof-of-funds (top hits incl. generic guidance/proof-funds.md#007 and the program-applicability page); noted the alternate `settlement funds requirement unless` for the FSW/FST-must-meet vs CEC/PNP-exempt nuance, which is treated as basis[], never a claim value."
  - "Baked `immigration medical examination permanent residence` for medical (ranks the medical/ family first, incl. medical/requirements-permanent-residents.md#000 whose text carries the dated public-policy exemption verbatim)."
  - "Wrote NO date/month/year/duration/dollar figure into either body. The IME exemption date and the settlement-funds figure are reproduced ONLY as runtime-quoted spans; worked examples use placeholder tokens (<chunk_id>, <relpath#NNN>, <verbatim span ...>) so the agent copies the real quote at runtime."

patterns-established:
  - "Pattern: hardest-case proof of the no-inlined-volatile-values rule — medical.md adds an explicit volatile-date callout instructing the author that the dated exemption window rides inside the verbatim quote, enforced downstream by the Plan 05 grep gate"
  - "Pattern: applicability stays in basis[] — proof-of-funds keeps program-exemption logic and the held amount out of claims[] entirely"

requirements-completed: []  # CHK-03 spans plans 27-02..27-05; this plan advances CHK-03 SC1 (5 of 6 agents shipped) + SC2 (volatile-value containment). NOT marking CHK-03 fully complete — orchestrator owns phase/requirement closure.

# Metrics
duration: 5min
completed: 2026-06-21
---

# Phase 27 Plan 03: Proof-of-Funds & Medical (IME) Document Agents Summary

**Two thin, plain-Markdown CLI-agnostic document agents that bake a short corpus-crawler search query, copy a verbatim generic quote, and ground it — proving volatile-value containment: proof-of-funds inlines no dollar figure (amount/program stay in basis[]), and medical reproduces the volatile IME-exemption date ONLY as a corpus-quoted span, never as prose.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-21T14:10:17Z
- **Completed:** 2026-06-21T14:14:45Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- `skills/document-agents/proof-of-funds.md` (124 lines): bakes `proof settlement funds`, one generic claim (settlement funds must be legally accessible — not borrowed, not real-property equity); program applicability (FSW/FST must meet vs CEC/PNP exempt) and the applicant's family size + held amount confined to `basis[]`; NO dollar figure inlined (a required figure, if asserted, arrives only as a quoted span).
- `skills/document-agents/medical.md` (134 lines): bakes `immigration medical examination permanent residence`, one generic IME-required claim; adds an explicit **volatile-date callout** instructing that the dated public-policy exemption window is reproduced ONLY inside the runtime verbatim quote — the body contains NO date, month, year, or duration.
- Both link the shared `_contract.md`, describe the search→quote→ground→abstain loop by reference, and carry one worked example via `corpus-crawler` + `.venv/bin/python`/`jq`; both abstain (`not_in_corpus`) when nothing resolves.
- All baked queries verified live against `corpus/index.db`: `proof settlement funds` → top hit `pr-pdi/express-entry-assessing-electronic-application-on-section-a11-2.md#036` (generic; `guidance/proof-funds.md#007` also returned); `immigration medical examination permanent residence` → all hits under the `medical/` family (top `medical/immigration-medical-assessment.md#001`; `medical/requirements-permanent-residents.md#000` returned, whose stored text carries the dated exemption verbatim — confirmed by `search --cite`).

## Task Commits

Each task was committed atomically:

1. **Task 1: Author proof-of-funds.md** - `69b7821` (feat)
2. **Task 2: Author medical.md (volatile date quoted from corpus)** - `4e97f88` (feat)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `skills/document-agents/proof-of-funds.md` - Proof-of-funds (settlement-funds) agent; program/amount applicability in basis[], no inlined dollar figure.
- `skills/document-agents/medical.md` - Medical/IME agent; volatile exemption date quoted from corpus, never inlined.

## Decisions Made
- Baked `proof settlement funds` (top hits include the generic settlement-funds rule) and noted the alternate `settlement funds requirement unless` for the program-exemption nuance — that applicability is `basis[]`, not a claim.
- Baked `immigration medical examination permanent residence` (ranks the `medical/` family first; the resolving chunk carries the dated exemption verbatim, so the date can be quoted, never inlined).
- Wrote no date/month/year/duration/dollar figure into either body; worked examples use runtime placeholder tokens, mirroring the sibling agents authored in 27-02.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `corpus-crawler` is not on `PATH`; invoked it as `.venv/bin/corpus-crawler` for the live verification queries (the in-skill examples use the bare `corpus-crawler` console-script name per the contract convention, which is correct once the package's entry point is on the user's PATH). No code or skill change required.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 5 of the 6 document agents now exist (`police-certificate`, `language-test`, `eca`, `proof-of-funds`, `medical`); only `employment-reference-letter.md` (Plan 04) remains before the Plan 05 conformance harness + static grep gate.
- The no-inlined-volatile-values rule is now proven on its hardest case (the IME exemption date), ready for the Plan 05 grep guard to assert across all skills.
- Phase NOT marked complete — orchestrator owns phase/requirement closure. CHK-03 continues to span plans 27-02..27-05.

## Self-Check: PASSED

- FOUND: skills/document-agents/proof-of-funds.md
- FOUND: skills/document-agents/medical.md
- FOUND: .planning/phases/27-cli-agnostic-document-agents/27-03-SUMMARY.md
- FOUND commit: 69b7821 (Task 1 — proof-of-funds)
- FOUND commit: 4e97f88 (Task 2 — medical)

---
*Phase: 27-cli-agnostic-document-agents*
*Completed: 2026-06-21*
