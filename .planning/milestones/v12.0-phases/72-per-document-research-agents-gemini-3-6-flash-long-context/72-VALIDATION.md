---
phase: 72
slug: per-document-research-agents-gemini-3-6-flash-long-context
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-22
---

# Phase 72 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py crawler/tests/test_doc_research_conformance.py -x -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` |
| **Estimated runtime** | ~60 seconds targeted; ~10 minutes full |

---

## Sampling Rate

- **After every task commit:** Run the narrowest relevant selector from the map below.
- **After every plan wave:** Run `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py crawler/tests/test_doc_research_conformance.py -q`.
- **Before `/gsd-verify-work`:** Full suite and a live 23-agent research run must be green.
- **Max feedback latency:** 120 seconds for mocked contract tests; live model execution is a separate phase gate.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 72-01-01 | 01 | 1 | DOC_RESEARCH-01 | T-72-01 | Reject malformed or incomplete research output | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_research_schema_validation -q` | no - W0 | pending |
| 72-01-02 | 01 | 1 | REAL_AGENT_EXECUTION-01 | T-72-02 | Failed Copilot calls become blocked results, never fabricated success | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_blocked_pipeline_no_fallback -q` | no - W0 | pending |
| 72-01-03 | 01 | 1 | DOC_RESEARCH-01 | T-72-03 | Only verified official/local evidence is classified authoritative | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_corpus_verification_gate -q` | no - W0 | pending |
| 72-02-01 | 02 | 2 | DOC_RESEARCH-01 | T-72-04 | Agent writes remain inside the assigned document pipeline | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_pipeline_isolation -q` | no - W0 | pending |
| 72-02-02 | 02 | 2 | REAL_AGENT_EXECUTION-01 | T-72-05 | Provenance identifies a real GitHub Copilot CLI Gemini invocation | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_researcher.py::test_success_requires_copilot_provenance -q` | no - W0 | pending |
| 72-03-01 | 03 | 3 | DOC_RESEARCH-01 | T-72-06 | Exactly 23 isolated reports pass schema, citation, uniqueness, and source checks | conformance | `.venv/bin/python -m pytest crawler/tests/test_doc_research_conformance.py -q` | no - W0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `crawler/tests/test_doc_researcher.py` - injected Copilot runner contract, schema, blocked-state, grounding, provenance, and path-isolation tests.
- [ ] `crawler/tests/test_doc_research_conformance.py` - 23-report conformance and uniqueness checks.
- [ ] Shared fixtures must supply explicit test doubles; production code cannot auto-select a fake runner.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live GitHub Copilot execution for all 23 types | REAL_AGENT_EXECUTION-01 | Ordinary CI must not spend model quota or require interactive Copilot credentials | Run the Phase 72 live command, verify 23 successful Gemini provenance records, then inspect that no report has fallback/deterministic status. |
| Online source quality | DOC_RESEARCH-01 | Source relevance and excerpts require privileged final review beyond schema validation | Sample every document report, resolve each official citation, and confirm discovery evidence is labeled separately. |

---

## Validation Sign-Off

- [ ] All tasks have automated verification or Wave 0 dependencies.
- [ ] Sampling continuity: no three consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing test references.
- [ ] No watch-mode flags.
- [x] Feedback latency under 120 seconds for targeted tests.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
