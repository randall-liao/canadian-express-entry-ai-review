---
phase: 27-cli-agnostic-document-agents
plan: 01
subsystem: testing
tags: [document-agents, grounding, cli-agnostic, markdown-skill, pii-separation, citations]

# Dependency graph
requires:
  - phase: 24-search-verb
    provides: "corpus-crawler --json search / search --cite resolver (RET-02) the contract names as the resolve step"
  - phase: 25-grounding-gate
    provides: "crawler/grounding.py answer-object schema + fail-closed gate (GND-01/GND-02) the contract documents"
  - phase: 26-checklist
    provides: "crawler/checklist.py grounded_claim producer loop + PII-tier split the contract describes in prose"
provides:
  - "skills/document-agents/_contract.md — shared answer-object schema + search->quote->ground->abstain loop + abstention/PII rules"
  - "skills/document-agents/README.md — additive, self-contained skill-pack index for the six agents"
affects: [27-02, 27-03, 27-04, 27-05, document-agents]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Portable CLI-agnostic skill authoring: plain Markdown, no front-matter, trust path = corpus-crawler --json shell + JSON parsing (mirrors crawler/AGENT_SKILL.md)"
    - "Single shared _contract.md as source of truth so per-agent skills stay thin and behave identically across CLIs"

key-files:
  created:
    - skills/document-agents/_contract.md
    - skills/document-agents/README.md
  modified: []

key-decisions:
  - "Authored the contract as plain Markdown with zero new trust-path code — every guarantee defers to the frozen Phase 24/25/26 primitives"
  - "All worked examples use the corpus-crawler console script + .venv/bin/python (bare python is broken by the repo's pyenv-win CRLF shim)"
  - "Worked-example quote fields are placeholder tokens, never pasted corpus spans — no requirement text or volatile value is inlined anywhere"
  - "README is additive only and leaves GSD-managed AGENTS.md / .github/copilot-instructions.md blocks untouched"

patterns-established:
  - "Pattern 1: Grounding-by-construction loop documented in prose (search -> resolve --cite -> verbatim quote -> ground -> abstain) mirroring checklist.grounded_claim"
  - "Pattern 2: PII-tier split — generic labels in claims[], all personalization in basis[] (gate never grounds basis, renderer never writes it)"
  - "Pattern 3: Abstain-never-confabulate — zero hits / leaky relpath / unresolvable chunk => abstentions[] reason not_in_corpus, zero claims"

requirements-completed: [CHK-03]

# Metrics
duration: 4min
completed: 2026-06-21
---

# Phase 27 Plan 01: Shared Document-Agents Contract Summary

**A single CLI-agnostic `_contract.md` defining the 5-key answer object, the search→verbatim-quote→ground→abstain loop, the three fail-closed reasons, the PII-tier split, and the no-inlined-values rule — plus an additive skill-pack README pointing at all six agents — with zero new trust-path code.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-21T13:52:28Z
- **Completed:** 2026-06-21T13:55:44Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments

- Shipped `skills/document-agents/_contract.md` (226 lines): the shared answer-object schema `{question, claims:[{id,text,citations[],quote}], basis[], abstentions[], prose}` exactly as `crawler/grounding.py` defines it, spelling out that the gate inspects `claims[]` ONLY (what makes PII-in-`basis` safe).
- Documented the grounding-by-construction producer loop: read profile slice → `corpus-crawler --json search "<2-4 token query>"` → resolve with `search --cite <chunk_id>` → copy a VERBATIM substring of `result.chunk.text` (never the `snippet`) → assemble → pipe to `corpus-crawler --json ground`.
- Named both trust-path verbs (`--json search` + `--json ground`), the pass rule, the three fail reasons (`uncited` / `unresolvable` / `quote_not_in_chunk`), and the malformed-input path (missing key or non-string `quote` → `invalid_input` / exit 2).
- Documented the PII-tier split, the `not_in_corpus` abstention rule (zero claims, never confabulate), the no-inlined-volatile-values rule, the five-key envelope, read-`ok`-first, and the exit-code table 0/1/2/3/4.
- Shipped `skills/document-agents/README.md`: a thin, additive index listing all six agents with one-line purposes and pointing at `_contract.md`, with an explicit note that it does NOT modify GSD-managed `AGENTS.md` / `.github/copilot-instructions.md` blocks.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author the shared _contract.md** - `8b7c550` (feat)
2. **Task 2: Author the skill-pack README pointer** - `986efb2` (docs)

**Plan metadata:** see final docs commit (this SUMMARY + STATE.md + ROADMAP.md)

## Files Created/Modified

- `skills/document-agents/_contract.md` - Shared answer-object schema + producer loop + abstention/PII/no-inlined-values rules + exit-code table for all six agents (plain Markdown, no front-matter)
- `skills/document-agents/README.md` - Additive, self-contained skill-pack index/pointer; lists all six agents and points at `_contract.md`; leaves GSD config blocks untouched

## Decisions Made

- Mirrored `crawler/AGENT_SKILL.md` tone/structure verbatim in spirit for the portability opener so the pack reads as one coherent skill family.
- Used relative cross-links (`../../crawler/CONTRACT.md`, `_contract.md`) so the skill pack is self-locating from `skills/document-agents/`.
- Kept every number in the contract structural (exit codes, `2-4` token guidance, `limit 5`) — no years, dollar amounts, dates, or `N days/months` — so the static no-inlined-volatile-values grep gate (Plan 05) stays green across the pack.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' acceptance criteria and `<automated>` verify gates passed on the first authoring pass, and the plan-level `<verification>` block (both files exist, no bare-`python` anywhere in the pack, no front-matter, GSD blocks untouched) passed.

## Issues Encountered

None. One care item handled during authoring: fenced code blocks were kept to `bash` / `json` (never a ` ```python ` language fence) and the word `python` appears only inside backticks or as the `.venv/bin/python` path, so the `grep -nE '(^|[^./[:alnum:]])python( |$)'` no-bare-python gate returns zero matches.

## Known Stubs

None. The `<verbatim span copied from result.chunk.text>` and `<2-4 token query>` tokens in worked examples are intentional placeholder tokens mandated by the plan (agents copy the real verbatim quote at runtime); they are not data stubs and no future plan needs to "wire" them.

## User Setup Required

None - no external service configuration required. This plan ships plain Markdown only; no packages installed (RESEARCH Package Legitimacy Audit: N/A).

## Next Phase Readiness

- The shared contract is in place; Wave 2 plans (27-02 police-certificate/language-test/eca, 27-03 proof-of-funds/medical, 27-04 employment-reference-letter) can now author the six per-agent skills that link `_contract.md`.
- Wave 3 (27-05) conformance harness + static grep gate can assert the pack-wide invariants (no bare-`python`, no front-matter, no inlined volatile values) the contract establishes.
- No blockers. GSD-managed `AGENTS.md` / `.github/copilot-instructions.md` remain untouched and the phase is NOT marked complete (orchestrator owns that).

## Self-Check: PASSED

- FOUND: skills/document-agents/_contract.md
- FOUND: skills/document-agents/README.md
- FOUND: .planning/phases/27-cli-agnostic-document-agents/27-01-SUMMARY.md
- FOUND commit: 8b7c550 (Task 1 — feat _contract.md)
- FOUND commit: 986efb2 (Task 2 — docs README.md)

---
*Phase: 27-cli-agnostic-document-agents*
*Completed: 2026-06-21*
