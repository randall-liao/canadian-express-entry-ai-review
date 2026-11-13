# Phase 68 Plan: Live Gemini 3.6 Flash LLM Worker Review Execution Engine

## Goal
Execute live Copilot CLI LLM calls (`copilot -p ... --model gemini-3.6-flash`) across all 184 blind test fixtures in `crawler/eval/test_data/` to read document text and produce real AnswerObject review reports without ground truth or defect label access.

## Requirements
- `LIVE_WORKER-01`: Execute real Copilot CLI calls (`copilot -p ... --model gemini-3.6-flash`) for all 184 blind synthetic test fixtures, extracting document text and writing real AnswerObject JSON review reports to `reports/worker_outputs/`.

## Tasks
1. Update `crawler/eval/real_worker.py` to make direct subprocess calls to `copilot -p ... --model gemini-3.6-flash -s` resolved through `PATH`.
2. Run `real_worker.py` across all 184 blind PDF test fixtures in `crawler/eval/test_data/`.
3. Verify that real AnswerObject review reports are generated and persisted in `reports/worker_outputs/case_001_vec.json`.

## Verification
Run `.venv/bin/python crawler/eval/real_worker.py` and inspect `reports/worker_outputs/case_001_vec.json`.
