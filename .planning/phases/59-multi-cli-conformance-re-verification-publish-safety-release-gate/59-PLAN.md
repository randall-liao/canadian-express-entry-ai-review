# Phase 59 Plan: Multi-CLI Conformance Re-verification & Publish Safety Release Gate

## Goal
Re-verify that all system prompts (`AGENTS.md`), thin multi-CLI pointer adapters (`CLAUDE.md`, `.github/copilot-instructions.md`, `.codex/AGENTS.md`, `.cursor/rules/agents.mdc`, `.windsurfrules`), document review skills, and Python tools pass the complete 209-node SAFE-01..12 multi-CLI conformance suite and the zero PII / zero path leak publish-safety check before final release assembly.

## Requirements
- `RELEASE_GATE-01`: Re-verify that all refined prompts, skills, and tools pass the 209-node SAFE-01..12 multi-CLI conformance suite and zero PII / zero path leak publish-safety check.

## Tasks
1. Execute `scripts/check_publish_safe.py` to verify 0 absolute path or secret shape violations across all tracked repository files.
2. Execute `scripts/run_multi_cli_conformance.py` to re-verify multi-CLI release gate conformance across all supported agent runtimes.
3. Run complete unit test suite across the entire codebase (`.venv/bin/python -m pytest crawler/tests -q`).

## Verification
Run `scripts/check_publish_safe.py`, `scripts/run_multi_cli_conformance.py`, and `.venv/bin/python -m pytest crawler/tests -q`.
