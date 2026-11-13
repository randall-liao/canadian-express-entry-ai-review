---
phase: 48
slug: synthetic-data-generation-agent-self-improvement-loop
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-21
---

# Phase 48 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via .venv/bin/python -m pytest) |
| **Config file** | pyproject.toml |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` |
| **Estimated runtime** | ~15 seconds (quick) / ~60 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest crawler/tests -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 48-01-01 | 01 | 1 | SELF-01 | T-48-01 | Generate synthetic PDF documents for 22 Express Entry document types + LoE | unit | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py -k test_generate_pdf_suite -q` | ❌ W0 | ⬜ pending |
| 48-01-02 | 01 | 1 | SELF-01 | T-48-02 | Generate scanned/image-based PDFs with PIL/pypdfium2 rasterization & image downloads | unit | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py -k test_generate_scanned_pdfs -q` | ❌ W0 | ⬜ pending |
| 48-02-01 | 02 | 2 | SELF-02 | T-48-03 | Evaluate agent review outputs against ground-truth JSON specifications | integration | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py -k test_benchmark_runner -q` | ❌ W0 | ⬜ pending |
| 48-03-01 | 03 | 3 | SELF-03 | T-48-04 | Iteratively optimize system prompts and review skills based on eval reports | e2e | `.venv/bin/python -m pytest crawler/tests/test_synthetic_eval.py -k test_self_optimizer_loop -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `crawler/tests/test_synthetic_eval.py` — unit & integration tests for synthetic PDF generation, benchmark runner, and self-optimizer
- [ ] `crawler/synthetic/` — synthetic PDF generator modules for all 22 document types + Letters of Explanation
- [ ] `crawler/eval/benchmark_runner.py` — automated evaluation runner scoring agent reviews against ground truth
- [ ] `crawler/eval/self_optimizer.py` — feedback-driven prompt & skill patch generator

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual quality of rendered scanned PDF images | SELF-01 | Visual layout check for OCR/vision readiness | Inspect generated PNG/PDF pages in `crawler/eval/synthetic_fixtures/rendered/` to ensure realistic contrast, rotation, and text alignment. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** Approved 2026-07-21
