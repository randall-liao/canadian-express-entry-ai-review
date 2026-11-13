---
phase: 74
slug: blind-report-generator-judge-self-improvement-loop
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-23
---

# Phase 74 - Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_phase74_judge_loop.py -x -q` |
| **Full phase command** | `.venv/bin/python -m pytest crawler/tests/test_phase74_worker_isolation.py crawler/tests/test_phase74_judge_loop.py crawler/tests/test_live_phase74_conformance_gate.py -q` |
| **Estimated runtime** | Under 120 seconds with injected temporary-root runners; live baseline/optimization/final passes are separate gates |

## Sampling Rate

- After each task commit: narrowest relevant test selector.
- After each wave: Worker/Judge/optimizer contract modules.
- Before verification: explicitly enabled live Phase 74 gate, grounding, publish safety, and final 236-case/23-Judge metrics.
- Maximum non-live feedback latency: 120 seconds.

## Per-Task Verification Map

| Task ID | Wave | Requirement | Threat Ref | Behavior | Automated Command | Status |
|---------|------|-------------|------------|----------|-------------------|--------|
| 74-W0-01 | 0 | ISOLATED_PIPELINE-01 | T-74-01 | Worker receives only staged case and public bundle | `.venv/bin/python -m pytest crawler/tests/test_phase74_worker_isolation.py -q` | pending |
| 74-W0-02 | 0 | JUDGE_IMPROVE-01 | T-74-02 | Judge batching/schema/model and holdout sealing | `.venv/bin/python -m pytest crawler/tests/test_phase74_judge_loop.py -q` | pending |
| 74-W0-03 | 0 | REAL_AGENT_EXECUTION-01 | T-74-03 | Injected outputs cannot satisfy live role gates | `.venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -k injected -q` | pending |
| 74-LIVE-01 | live | ISOLATED_PIPELINE-01 | T-74-04 | 236 independent Worker sessions have blindness attestations | `REQUIRE_LIVE_PHASE74_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -k worker -q` | pending |
| 74-LIVE-02 | live | JUDGE_IMPROVE-01 | T-74-05 | 23 Opus 4.8 xhigh long-context Judge batches cover every case | `REQUIRE_LIVE_PHASE74_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -k judge -q` | pending |
| 74-LIVE-03 | live | JUDGE_IMPROVE-01 | T-74-06 | Candidate patches improve train targets with zero holdout regression | `REQUIRE_LIVE_PHASE74_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -k optimization -q` | pending |

## Wave 0 Requirements

- [ ] `crawler/tests/test_phase74_worker_isolation.py` - attachment/staging/public-bundle/AnswerObject/grounding/provenance/adversarial blindness tests.
- [ ] `crawler/tests/test_phase74_judge_loop.py` - Opus batch schema, model flags, exact case coverage, sibling holdout sealing, optimizer isolation, candidate acceptance tests.
- [ ] `crawler/tests/test_live_phase74_conformance_gate.py` - non-seeding live gate for Worker/Judge/optimizer provenance, metrics, holdout, and patch audit trails.
- [ ] Explicit test runners are non-live and temporary-root only.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Worker cannot infer failure from side channels | ISOLATED_PIPELINE-01 | Absence of filesystem/tool access requires process-level inspection | Inspect representative Worker command/cwd/attachment/public bundle and prove no privileged file/path/label is reachable. |
| Semantic Judge quality | JUDGE_IMPROVE-01 | Rubric scoring is model-semantic | Sample Opus batch rationales against PDF, Worker report, ground truth, and research; confirm evidence supports each finding. |

## Validation Sign-Off

- [ ] All tasks have automated verification or Wave 0 dependencies.
- [ ] No three consecutive tasks lack automated verification.
- [ ] Live gates never seed or copy outputs.
- [ ] Holdout findings remain sealed from optimizer inputs.
- [x] `nyquist_compliant: true` set.

**Approval:** pending
