---
phase: 73
slug: blind-synthetic-document-generation-gemini-3-6-flash-long-co
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-23
---

# Phase 73 - Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py -x -q` |
| **Full phase command** | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py crawler/tests/test_doc_synthetic_conformance.py -q` |
| **Estimated runtime** | Under 120 seconds with injected temporary-root fixtures; live generation is a separate gate |

## Sampling Rate

- **After every task commit:** Run the narrowest selector below.
- **After every wave:** Run both Phase 73 test modules.
- **Before verification:** Run the explicitly enabled 23-agent/236-PDF live gate and publish-safety checks.
- **Max feedback latency:** 120 seconds for non-live tests.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 73-01-01 | 01 | 1 | REAL_AGENT_EXECUTION-01 | T-73-01 | Injected runners are non-live and cannot seed production | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py::test_generator_provenance_is_truthful -q` | no - W0 | pending |
| 73-01-02 | 01 | 1 | BLIND_SYNTHETIC-01 | T-73-02 | Strict generation specs cover valid control plus every research failure mode | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py::test_generation_spec_coverage -q` | no - W0 | pending |
| 73-02-01 | 02 | 2 | BLIND_SYNTHETIC-01 | T-73-03 | Vector/scanned siblings render from one agent spec and scan has no text layer | integration | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py::test_vector_scanned_pair_parity -q` | no - W0 | pending |
| 73-02-02 | 02 | 2 | ISOLATED_PIPELINE-01 | T-73-04 | Filenames, metadata, page text, ordering, and paths leak no privileged labels | integration | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py::test_blind_leakage_scan -q` | no - W0 | pending |
| 73-02-03 | 02 | 2 | ISOLATED_PIPELINE-01 | T-73-05 | Worker stage contains only one opaque PDF and allowed extracted text | unit | `.venv/bin/python -m pytest crawler/tests/test_doc_synthetic_generator.py::test_staging_isolation -q` | no - W0 | pending |
| 73-03-01 | 03 | 3 | BLIND_SYNTHETIC-01 | T-73-06 | All 23 agents produce 118 cases and 236 PDFs | live conformance | `REQUIRE_LIVE_SYNTHETIC_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_doc_synthetic_conformance.py -q` | no - W0 | pending |

## Wave 0 Requirements

- [ ] `crawler/tests/test_doc_synthetic_generator.py` - schema, real-vs-injected provenance, rendering, pairing, leakage, PII, and staging tests using temporary roots.
- [ ] `crawler/tests/test_doc_synthetic_conformance.py` - ordinary temporary-root contract tests plus an explicitly enabled live gate that never seeds production.
- [ ] Tests must reject deterministic production defect selection and false Gemini metadata.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual realism across all document types | BLIND_SYNTHETIC-01 | Automated PDF structure checks cannot fully judge visual plausibility | Render representative vector/scanned pages and inspect text, layout, seals, tables, and scan degradation without reading ground truth labels. |
| Live 23-agent generation | REAL_AGENT_EXECUTION-01 | Ordinary CI must not require Copilot credentials or model quota | Run production generation, then enable the live gate and verify 23 live provenance records and 236 leak-free PDFs. |

## Validation Sign-Off

- [ ] All tasks have automated verification or Wave 0 dependencies.
- [ ] No three consecutive tasks lack automated verification.
- [ ] Wave 0 covers every missing test reference.
- [ ] No watch-mode flags.
- [x] `nyquist_compliant: true` set.

**Approval:** pending
