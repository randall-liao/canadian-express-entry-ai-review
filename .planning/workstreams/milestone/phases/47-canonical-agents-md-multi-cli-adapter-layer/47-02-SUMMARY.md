---
phase: 47-canonical-agents-md-multi-cli-adapter-layer
plan: 02
subsystem: adapters
tags: [multi-cli, pointer-adapters, agents-md, portable-skills, claude, copilot, codex, cursor, windsurf]

requires:
  - phase: 47-01
    provides: Canonical AGENTS.md system specification at repository root
provides:
  - Thin multi-CLI pointer adapters for Claude, Copilot, Codex, Cursor, and Windsurf
  - Documented portable skills interface in skills/README.md
  - Automated tests verifying adapter pointers and skills interface in test_instruction_eval.py
affects: [47-03-PLAN, multi-cli-conformance, onboarding-docs]

tech-stack:
  added: []
  patterns: [thin-pointer-adapters, open-standard-agents-md, portable-markdown-skills]

key-files:
  created:
    - CLAUDE.md
    - .codex/AGENTS.md
    - .cursor/rules/agents.mdc
    - .windsurfrules
    - skills/README.md
  modified:
    - .github/copilot-instructions.md
    - crawler/tests/test_instruction_eval.py

key-decisions:
  - "Thin pointer adapter files (< 35 lines each) delegate 100% of agent instructions, contracts, and workflows to /AGENTS.md."
  - "All CLI adapters follow the open AGENTS.md standard without vendor-specific instruction forks or proprietary API locks."
  - "Skills/ interface documented as vendor-neutral Markdown skills usable across all supported AI agent CLIs."

requirements-completed: [ADAPT-01, ADAPT-02]

completed: 2026-07-21
---

# Phase 47 Plan 02: Multi-CLI Thin Pointer Adapters & Portable Skills Interface Summary

**Created thin multi-CLI pointer adapter files delegating 100% of instructions to AGENTS.md across Claude, Copilot, Codex, Cursor, and Windsurf, and documented the portable skills interface.**

## Accomplishments

- Created thin adapter files (< 35 lines each) directing agents to follow `/AGENTS.md`:
  - `CLAUDE.md` (Claude CLI)
  - `.github/copilot-instructions.md` (GitHub Copilot Workspace)
  - `.codex/AGENTS.md` (OpenAI Codex CLI)
  - `.cursor/rules/agents.mdc` (Cursor IDE with `alwaysApply: true` frontmatter)
  - `.windsurfrules` (Windsurf Cascade)
- Created `skills/README.md` documenting the portable, vendor-neutral skills interface (`skills/document-agents/` and `skills/crs-auditors/`).
- Updated `crawler/tests/test_instruction_eval.py` to verify adapter pointers and skills interface structure.
- Verified test suite execution with 5/5 tests passing green.

---
*Phase: 47-canonical-agents-md-multi-cli-adapter-layer*
*Completed: 2026-07-21*
