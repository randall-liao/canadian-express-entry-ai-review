---
phase: 47-canonical-agents-md-multi-cli-adapter-layer
plan: 01
subsystem: testing
tags: [agents, system-prompt, tool-contracts, grounding, pii-containment, workflow]

requires:
  - phase: 41-conformance-hardening
    provides: Grounded citation verification, PII containment invariants, and corpus-crawler CLI contracts
provides:
  - Canonical AGENTS.md system specification at repository root
  - Multi-agent role specifications and 4-stage operational review workflow
  - Standardized 5-key JSON envelope tool contracts and 5-field AnswerObject schema
  - crawler/tests/test_instruction_eval.py test suite verifying AGENTS.md structure and contracts
affects: [47-02-PLAN, 47-03-PLAN, multi-cli-adapters, skills]

tech-stack:
  added: []
  patterns: [canonical-agents-md, 5-key-json-envelope, 5-field-answer-object, fail-closed-grounding, pii-containment-partition]

key-files:
  created:
    - AGENTS.md
    - crawler/tests/test_instruction_eval.py
  modified: []

key-decisions:
  - "AGENTS.md at repository root is the canonical system specification authority for all AI agent runtimes."
  - "Tool orchestration contracts require corpus-crawler --json <subcommand> with explicit 5-key JSON envelope parsing."
  - "Grounding directives mandate verbatim quotes from corpus/index.db and strict structural PII partition (claims generic vs basis personal/vault)."

patterns-established:
  - "Canonical AGENTS.md System Prompt: Unified system prompt, roles, and workflows across all AI CLIs."
  - "5-Field Answer Object Schema: Structured JSON output (question, claims, basis, abstentions, prose) for document review and CRS auditing."

requirements-completed: [AGENT-01, AGENT-02, AGENT-03]

duration: 12min
completed: 2026-07-21
---

# Phase 47 Plan 01: Canonical AGENTS.md & Multi-CLI Tool Contracts Summary

**Authored canonical AGENTS.md system specification at repository root defining multi-agent roles, corpus-crawler tool contracts, fail-closed grounding, PII containment, and 4-stage review workflow.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-21T23:21:58Z
- **Completed:** 2026-07-21T23:33:58Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Authored `AGENTS.md` at repository root as single source of truth for all AI CLIs (Copilot, Claude, Codex, Cursor, Windsurf).
- Inscribed System Role (PR Review Agent), core invariant principles (100% Grounded Citations, Zero Ungrounded Assertions, Strict PII Containment), and standard 5-key stdout JSON envelope parsing contracts.
- Inscribed fail-closed grounding directives, 5-field `AnswerObject` schema (`question`, `claims`, `basis`, `abstentions`, `prose`), verbatim quote matching, and self-correction pipe loop (`corpus-crawler --json ground`).
- Inscribed 4 multi-agent roles (Lead Review Coordinator, Document Review Agent, CRS Auditor Agent, Remediation Exporter) and 4-stage operational review workflow (Setup -> Extract/Confirm -> Audit/Screen -> Remediate/Export).
- Scaffolded `crawler/tests/test_instruction_eval.py` test suite verifying `AGENTS.md` syntax, grounding rules, and review workflow contracts.

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold evaluation test suite & author AGENTS.md core roles and tool contracts** - `02647ce` (feat)
2. **Task 2: Inscribe fail-closed grounding, PII containment invariants, and answer-object schema in AGENTS.md** - `eb02809` (feat)
3. **Task 3: Author multi-agent roles and 4-stage operational review workflow in AGENTS.md** - `a86a70a` (feat)

## Files Created/Modified

- `AGENTS.md` - Canonical system prompt, tool contracts, multi-agent roles, grounding rules, and 4-stage document review workflow.
- `crawler/tests/test_instruction_eval.py` - Instruction evaluation test suite verifying AGENTS.md structure and contracts.

## Decisions Made

- Established `AGENTS.md` as the authoritative system specification for all supported AI CLI runtimes.
- Mandated 5-key stdout JSON envelope (`schema_version`, `ok`, `command`, `result`, `error`) and stdout=JSON / stderr=diagnostics invariant across all CLI tool calls.
- Confined all applicant PII to private candidate vault and `basis[]`, ensuring public `claims[]` contain generic requirement labels and verbatim corpus quotes only.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - no stubs or empty placeholders remain.

## Threat Flags

None - no new unvetted network endpoints or trust boundary violations introduced.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Phase 47 Plan 02 (`47-02-PLAN.md`): Authoring thin adapter pointer files (`CLAUDE.md`, `.github/copilot-instructions.md`, `.codex/AGENTS.md`, `.cursor/rules/agents.mdc`, `.windsurfrules`).

---
*Phase: 47-canonical-agents-md-multi-cli-adapter-layer*
*Completed: 2026-07-21*

## Self-Check: PASSED
- FOUND: AGENTS.md
- FOUND: crawler/tests/test_instruction_eval.py
- FOUND: 02647ce
- FOUND: eb02809
- FOUND: a86a70a
