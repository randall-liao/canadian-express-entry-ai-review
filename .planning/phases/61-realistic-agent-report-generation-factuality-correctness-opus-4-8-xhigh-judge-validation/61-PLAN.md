# Phase 61 Plan: Realistic Agent Report Generation & Factuality/Correctness Opus 4.8 xhigh Judge Validation

## Goal
Run Gemini 3.6 Flash Worker agent to generate realistic document review reports for all 184 synthetic PFL test fixtures, then run parallel Claude Opus 4.8 xhigh Judge subagents across all 4 document categories to cross-check worker review reports against input data, PDF fixtures, and authoritative IRCC corpus for factuality, correctness, PFL risk detection, and PII containment.

## Requirements
- `REPORT_GEN-01`: Worker agent generates full, realistic document review reports following the canonical `AGENTS.md` AnswerObject schema for every PFL synthetic test fixture.
- `FACTUAL_JUDGE-01`: Parallel Judge subagents (Claude Opus 4.8 xhigh reasoning) evaluate generated worker review reports against input data, PDF fixtures, and authoritative IRCC corpus documents across 4 review categories (A, B, C, D).
- `FACTUAL_JUDGE-02`: Judge verifies report factuality, correctness, PFL risk detection accuracy, citation exactness, and PII containment.

## Tasks
1. Execute Worker report generation in `agent_improvement_loop.py` across all 184 test cases.
2. Run `crawler/tests/test_agent_improvement_loop.py` to confirm 100% clean evaluation.
3. Execute parallel Judge evaluation scripts (`parallel_judge.py`, `judge_group_b.py`, `judge_group_c.py`, `judge_group_d.py`) powered by Claude Opus 4.8 xhigh reasoning across Category A, B, C, and D.
4. Verify category evaluation reports in `reports/judge_group_*_report.json`.

## Verification
Run `.venv/bin/python -m pytest crawler/tests/test_agent_improvement_loop.py -q`
