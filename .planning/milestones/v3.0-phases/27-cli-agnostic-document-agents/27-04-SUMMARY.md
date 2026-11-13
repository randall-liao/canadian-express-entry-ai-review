---
phase: 27-cli-agnostic-document-agents
plan: 04
subsystem: document-agents
tags: [markdown-skills, cli-agnostic, corpus-crawler, grounding, pii-containment, employment-reference-letter, work-experience, per-element-quotes, curly-apostrophe]

# Dependency graph
requires:
  - phase: 27-01
    provides: "skills/document-agents/_contract.md (shared 5-key answer object + search→resolve→verbatim-quote→ground→abstain loop + abstention/PII/no-inlined-values rules + exit-code table)"
provides:
  - "skills/document-agents/employment-reference-letter.md — the new sixth (headline) document agent; verifies the Express Entry proof-of-work-experience reference letter's required elements via one generic PII-free claim per element, each grounded to a separate verbatim quote from the resolved corpus chunk"
affects: [27-05, document-agents conformance harness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-resolve / many-element-claims: when all required elements live in one corpus chunk, resolve once via search --cite, then copy a SEPARATE verbatim substring per element and emit ONE generic claim per element (vs. one query per element)"
    - "Doc-type disambiguation guard: explicit do-not-confuse note + a baked query verified to uniquely return the work-experience-letter chunk and never an arranged-employment relpath; the worked example asserts no arranged-employment id appears in hits before resolving"
    - "Curly-apostrophe hazard callout: the chunk uses U+2019 in possessives and the gate normalizes whitespace+case ONLY, so the agent must copy exact bytes from result.chunk.text — a straight-apostrophe retype fails quote_not_in_chunk"

key-files:
  created:
    - skills/document-agents/employment-reference-letter.md
  modified: []

key-decisions:
  - "Baked the SHORT query `reference letter company letterhead` — verified live to return EXACTLY ONE hit (the proof-of-work-experience completeness-check chunk) and never an arranged-employment relpath."
  - "Referenced the canonical chunk descriptively (no chunk_id, no literal relpath) because the relpath contains a year and chunk ids drift — both would trip the no-inlined-volatile-values / no-chunk_id gates and rot."
  - "Worked-example quote fields are placeholder tokens and basis values are placeholder tokens (<employer>/<start-date>/<salary>); the real verbatim spans (with curly apostrophes) are copied at runtime, so the spec body holds no pasted corpus spans, no PII, and no inlined requirement values."
  - "Did NOT mark CHK-03 complete — it spans plans 27-02..27-05; this plan ships the final (sixth) agent and advances CHK-03 SC4, but phase/requirement closure is the orchestrator's job."

patterns-established:
  - "Pattern: multi-element verbatim-quote loop — one resolved chunk grounds N element-claims, each PII-free, with abstention per element when a span is missing"
  - "Pattern: wrong-doc-type defense — bake a uniquely-landing query + a do-not-confuse guard + a runtime assertion that the resolved id is not the sibling doc type"

requirements-completed: []  # CHK-03 spans plans 27-02..27-05; this plan advances CHK-03 SC2/SC4 (6 of 6 agents now shipped). NOT marking CHK-03 fully complete — orchestrator owns phase/requirement closure (Plan 05 locks the conformance test).

# Metrics
duration: 7min
completed: 2026-06-21
---

# Phase 27 Plan 04: Employment / Reference Letter Document Agent Summary

**The headline sixth CLI-agnostic document agent: a thin plain-Markdown skill that bakes the short query `reference letter company letterhead` to land the Express Entry proof-of-work-experience reference-letter chunk, then copies a SEPARATE verbatim quote for each required element (letterhead, applicant name, company contact, signatory/signature, positions held, and the job-title/duties/status/dates/hours/salary details) into one generic PII-free claim per element — grounding the assembled 4-claim answer to verdict:"pass" (4/4) live, with a do-not-confuse guard against the arranged-employment job-offer letter and a per-element abstention rule.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-21T10:18:21Z
- **Completed:** 2026-06-21T10:25:00Z
- **Tasks:** 2
- **Files modified:** 1 (created)

## Accomplishments

- Authored `skills/document-agents/employment-reference-letter.md` (184 lines) — the new sixth document agent, the milestone's headline deliverable — as plain Markdown with no front-matter, linking the shared `_contract.md`.
- Scoped the agent precisely to the **proof-of-work-experience** reference / experience letter and added an explicit **do-not-confuse** guard against the **arranged-employment job-offer** letter (a different doc type / the existing `job-offer` checklist item), instructing the agent never to cite the arranged-employment chunks and to assert no arranged-employment id appears in hits before resolving.
- Baked the SHORT query `reference letter company letterhead` (no chunk_id), verified live to return exactly one hit — the work-experience-letter requirements chunk — and never an arranged-employment relpath.
- Documented the **single-resolve / per-element verbatim-quote loop**: resolve once via `search --cite`, then copy a separate verbatim substring per element and emit one generic PII-free claim per element, keeping employer/applicant/dates/hours/salary in `basis[]` only.
- Added a worked example piping the assembled multi-element answer to `corpus-crawler --json ground`, branching on the envelope (`ok` then `result.verdict`), a PII-discipline guard, and a per-element abstention rule (`not_in_corpus`, no claim, never confabulate).
- Proved live that the 4 per-element claims over the resolved chunk ground to `verdict:"pass"`, grounded 4/4, ungrounded 0 — copying quote spans verbatim with the curly apostrophes (U+2019) preserved.

## Task Commits

Each task was committed atomically (hooks passed, no `--no-verify`):

1. **Task 1: Author the employment-reference-letter agent core (per-element verbatim quotes)** — `3cfb6a8` (feat)
2. **Task 2: Add the worked grounding example + PII/no-leak guards** — `2a869bf` (feat)

**Plan metadata:** see final `docs(27-04)` commit.

## Files Created/Modified

- `skills/document-agents/employment-reference-letter.md` — NEW. The sixth document agent: verifies the Express Entry work-experience reference-letter elements via per-element verbatim quotes from the resolved corpus chunk, one generic PII-free claim per element, with the do-not-confuse-with-job-offer guard, the baked query (no chunk_id), the curly-apostrophe hazard callout, the worked grounding example, the PII-discipline guard, and the abstention rule.

## Decisions Made

- **Baked `reference letter company letterhead`** — verified live to return exactly one hit (the proof-of-work-experience chunk) and no arranged-employment relpath; preferred a uniquely-landing query so the agent reliably hits the work-experience letter, not the job-offer letter.
- **No literal relpath / no chunk_id in the body.** The canonical chunk's relpath contains a year and chunk ids drift; writing either would trip the no-inlined-volatile-values / no-chunk_id gates and rot. The chunk is referenced descriptively and via placeholder tokens (`<chunk_id>`, `<relpath#NNN>`).
- **Avoided the literal codepoint string "U+2019"** in the hazard callout because it contains a 4-digit year-like substring that the no-inlined-values gate flags; described the curly apostrophe with the character itself plus "right single quote" instead.
- **Worked-example quote and basis fields are placeholder tokens** — the real verbatim spans (curly apostrophes included) are copied at runtime, keeping the spec body free of pasted corpus spans, PII, and inlined requirement values.

## Deviations from Plan

None - plan executed exactly as written. All per-task acceptance criteria, both `<automated>` verify gates, and the plan-level `<verification>` block passed; no Rule 1–4 deviations were required.

## Issues Encountered

- `corpus-crawler` is not on `PATH` by default; it lives at `.venv/bin/corpus-crawler`. Resolved by prefixing `PATH="$PWD/.venv/bin:$PATH"` (and/or invoking the full path) for the live verification commands. This is an execution-environment detail only — the skill text correctly instructs running from `<repo-root>` per `_contract.md`, and no skill content changed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All six document agents are now shipped (`police-certificate`, `language-test`, `eca`, `proof-of-funds`, `medical`, `employment-reference-letter`), each thin, plain-Markdown, linking `_contract.md`, baking a short query, no chunk_id / inlined values / bare-python.
- Plan 27-05 (the conformance harness) can now lock the employment-reference-letter pass/fail behavior permanently: the live proof in this plan (4-claim answer → `verdict:"pass"`, 4/4) and the negative case (confabulated quote → `verdict:"fail"`, `quote_not_in_chunk`, writes nothing) are both ready to be asserted against `corpus/index.db`.
- CHK-03 is NOT marked complete here — it spans plans 27-02..27-05 and the orchestrator owns phase/requirement closure.

---
*Phase: 27-cli-agnostic-document-agents*
*Completed: 2026-06-21*

## Self-Check: PASSED

- FOUND: `skills/document-agents/employment-reference-letter.md`
- FOUND: `.planning/phases/27-cli-agnostic-document-agents/27-04-SUMMARY.md`
- FOUND commit: `3cfb6a8` (Task 1)
- FOUND commit: `2a869bf` (Task 2)
