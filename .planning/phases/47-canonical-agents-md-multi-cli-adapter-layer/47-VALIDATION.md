---
phase: 47
slug: canonical-agents-md-multi-cli-adapter-layer
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-21
---

# Phase 47 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via .venv/bin/python -m pytest) |
| **Config file** | pyproject.toml |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` |
| **Estimated runtime** | ~10 seconds (quick) / ~60 seconds (conformance subset) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest crawler/tests -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 47-01-01 | 01 | 1 | AGENT-01 | T-47-01 | Roles and tool contracts clearly defined in AGENTS.md | unit/doc | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -k test_agents_md_syntax -q` | ❌ W0 | ⬜ pending |
| 47-01-02 | 01 | 1 | AGENT-02 | T-47-02 | Fail-closed grounding & PII containment rules enforced | unit | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -k test_grounding_rules -q` | ❌ W0 | ⬜ pending |
| 47-01-03 | 01 | 1 | AGENT-03 | T-47-03 | Step-by-step document review workflows specified | unit | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -k test_review_workflows -q` | ❌ W0 | ⬜ pending |
| 47-02-01 | 02 | 2 | ADAPT-01 | T-47-04 | Pointer files delegate 100% to AGENTS.md | integration | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -k test_adapter_pointers -q` | ❌ W0 | ⬜ pending |
| 47-02-02 | 02 | 2 | ADAPT-02 | T-47-05 | Portable skills/ interface validated across CLI formats | integration | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -k test_skills_interface -q` | ❌ W0 | ⬜ pending |
| 47-03-01 | 03 | 3 | AGENT-01, AGENT-02 | T-47-06 | Synthetic applicant fixtures benchmark agent instructions | e2e | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -k test_synthetic_fixtures_grounding -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `crawler/tests/test_instruction_eval.py` — unit & integration tests verifying AGENTS.md structure, adapter pointers, skills format, and synthetic fixture grounding
- [ ] `crawler/eval/synthetic_fixtures/` — synthetic PII-free applicant profile & extraction fixtures for benchmarking instruction compliance

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Multi-agent interactive chat experience | AGENT-01 | Interactive CLI runtime prompt rendering | Run `copilot`, `claude`, or `codex` in a interactive terminal session, ask document review questions, and confirm formatting and citation output. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** Approved 2026-07-21
