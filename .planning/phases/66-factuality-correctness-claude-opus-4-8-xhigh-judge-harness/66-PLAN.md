# Phase 66 Plan: Factuality & Correctness Claude Opus 4.8 xhigh Judge Harness

## Goal
Implement a real LLM Judge runner (`crawler/eval/real_judge.py`) using Claude Opus 4.8 with `xhigh` reasoning effort that cross-checks worker AnswerObject review reports against raw document evidence, ground truth specs, and authoritative IRCC corpus.

## Requirements
- `REAL_JUDGE-01`: Real LLM Judge runner (Claude Opus 4.8 xhigh reasoning) evaluates worker AnswerObject review reports against raw document evidence, authoritative IRCC corpus, and ground truth specs across 4 review categories (A, B, C, D).
- `REAL_JUDGE-02`: Judge cross-checks verdict correctness, defect recall, citation exactness, grounding quote validity, and PII containment.

## Tasks
1. Create `crawler/eval/real_judge.py` implementing Claude Opus 4.8 xhigh Judge evaluation logic over real worker review outputs.
2. Evaluate worker review reports against blind PDF text and ground truth specs stored in `crawler/eval/ground_truth/`.
3. Output category-level evaluation reports in `reports/judge_group_<category>_report.json`.
4. Run `real_judge.py` on all 184 blind test fixtures.

## Verification
Run `.venv/bin/python crawler/eval/real_judge.py`
