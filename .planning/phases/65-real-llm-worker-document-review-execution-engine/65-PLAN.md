# Phase 65 Plan: Real LLM Worker Document Review Execution Engine

## Goal
Implement a real LLM Worker execution engine (`crawler/eval/real_worker.py`) that reads raw document text (extracted from PDF via `pdfminer`) and executes document review tasks to produce AnswerObject review reports without access to ground truth or defect labels.

## Requirements
- `REAL_WORKER-01`: Real LLM Worker execution engine (Gemini 3.6 Flash) reads raw document text and executes document review tasks to produce AnswerObject review reports without access to ground truth or defect labels.

## Tasks
1. Create `crawler/eval/real_worker.py` supporting direct document review execution over raw text using `AGENTS.md` instructions and corpus search tools.
2. Persist real worker review outputs in `reports/worker_outputs/case_XXX.json`.
3. Add tests in `crawler/tests/test_agent_improvement_loop.py` to verify worker review output format and PII containment.

## Verification
Run `.venv/bin/python -m pytest crawler/tests/test_agent_improvement_loop.py -q`
