# Phase 57 Plan: Realistic Agent Report Generation & Parallel Opus 4.8 xhigh Judge Validation

## Goal
Run Gemini 3.6 Flash Worker agent to generate realistic document review reports for all 184 agent-generated test fixtures, then run parallel Claude Opus 4.8 xhigh Judge agents across all 4 document categories to cross-check worker review reports against input data, PDF fixtures, and authoritative IRCC corpus.

## Requirements
- `REPORT_GEN-01`: Worker agent generates full, realistic document review reports following the canonical `AGENTS.md` AnswerObject schema for every agent-generated synthetic test fixture.
- `JUDGE_EVAL-01`: Parallel Judge subagents (Claude Opus 4.8 xhigh reasoning) evaluate generated worker review reports against input data, PDF fixtures, and authoritative IRCC corpus documents across 4 review categories (A, B, C, D).
- `JUDGE_EVAL-02`: Judge cross-checks grounding completeness, citation exactness, defect recall (incomplete translation, no translation, missing info), and PII containment.

## Tasks
1. Execute Worker report generation in `agent_improvement_loop.py` across all 184 test cases.
2. Update `_EXPECTED_FIXTURES = 184` in `crawler/tests/test_agent_improvement_loop.py` and run tests.
3. Execute parallel Judge evaluation scripts (`parallel_judge.py`, `judge_group_b.py`, `judge_group_c.py`, `judge_group_d.py`) powered by Claude Opus 4.8 xhigh reasoning across Category A, B, C, and D.
4. Verify category evaluation reports in `reports/judge_group_*_report.json`.

## Verification
Run `.venv/bin/python -m pytest crawler/tests/test_agent_improvement_loop.py -q`
