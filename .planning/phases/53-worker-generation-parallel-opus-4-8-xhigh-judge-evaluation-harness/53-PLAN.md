# Phase 53 Plan: Worker Generation & Parallel Opus 4.8 xhigh Judge Evaluation Harness

## Goal
Run the Gemini 3.6 Flash Worker agent to generate document review reports across all 138 multi-case synthetic test fixtures, then run parallel Claude Opus 4.8 xhigh Judge subagents to evaluate the reports against ground truth JSON schemas across 4 document categories (Identity/Language, Education/Work, Financial/Civil, Legal/Relationships/LoE), producing a comprehensive benchmark evaluation report.

## Requirements
- `EVAL-01`: Worker agent (Gemini 3.6 Flash) generates structured document review reports for every multi-case synthetic test fixture.
- `EVAL-02`: Parallel Judge harness (Opus 4.8 xhigh) evaluates worker review reports against ground truth JSON across all test cases, scoring completeness, citation exactness, defect recall, and grounding compliance.

## Tasks
1. Update `crawler/eval/agent_improvement_loop.py` and `parallel_judge.py` to process all 138 multi-case synthetic test fixtures.
2. Execute Worker report generation on all 138 test cases.
3. Spawn parallel Judge subagents using Claude Opus 4.8 with `xhigh` reasoning effort across the 4 document groups to evaluate worker reports against ground truth metadata.
4. Record structured evaluation scores in `crawler/eval/multi_case_benchmark_results.json`.

## Verification
Run `.venv/bin/python -m pytest crawler/tests/test_agent_improvement_loop.py -q`
