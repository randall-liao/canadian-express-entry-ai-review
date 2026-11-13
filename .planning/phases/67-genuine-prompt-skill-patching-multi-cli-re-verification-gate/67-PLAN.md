# Phase 67 Plan: Genuine Prompt/Skill Patching & Multi-CLI Re-verification Gate

## Goal
Implement a genuine self-improvement optimizer (`crawler/eval/genuine_optimizer.py`) that analyzes the real Judge failure reports, applies prompt enhancements to `AGENTS.md` and `skills/pdf/SKILL.md` (e.g. mandatory checks for PFL lump-sum funds, NOC duty matching, certified translation affidavits, and police cert coverage gaps), re-executes worker review, and measures real score improvements. Then re-verify the 209-node SAFE-01..12 conformance gate and publish safety check.

## Requirements
- `GENUINE_OPT-01`: Genuine self-improvement loop automatically applies Judge patch proposals to `AGENTS.md` and `skills/pdf/SKILL.md`, re-runs the real Worker and Judge, and tracks real score deltas across iterations.
- `RELEASE_GATE-01`: Re-verify that all refined prompts, skills, and tools pass the 209-node SAFE-01..12 multi-CLI conformance suite and zero PII / zero path leak publish-safety check (`scripts/check_publish_safe.py`).

## Tasks
1. Create `crawler/eval/genuine_optimizer.py` that analyzes Judge failures and applies explicit review rule patches to `AGENTS.md` and `skills/pdf/SKILL.md`.
2. Update `real_worker.py` to incorporate the enhanced system instructions for detecting PFL triggers (lump-sum deposits, NOC duty mismatch, translation affidavit, police cert gaps).
3. Re-run `real_judge.py` and verify genuine score improvement delta.
4. Execute `scripts/check_publish_safe.py` and `scripts/run_multi_cli_conformance.py` to confirm publish safety and multi-CLI release gate compliance.

## Verification
Run `.venv/bin/python crawler/eval/genuine_optimizer.py` and `scripts/check_publish_safe.py`.
