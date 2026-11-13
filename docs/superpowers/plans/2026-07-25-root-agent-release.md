# Root-Agent Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase 75 so a GitHub Copilot agent started at the repository root can safely guide a Canadian Express Entry document review and the milestone ships with a measured root `TEST_REPORT.md`.

**Architecture:** A GPT-5.6 Sol `xhigh` SDK orchestrator consumes only validated, PII-free aggregate Phase 72–74 evidence and emits a strict release assessment. Deterministic code validates the assessment and renders `TEST_REPORT.md`; root instructions and onboarding map natural-language review intent to the existing four-stage local vault workflow.

**Tech Stack:** Python 3.11+, GitHub Copilot Python SDK, Pydantic 2, existing `corpus-crawler --json` CLI, pytest, Markdown.

## Global Constraints

- The release orchestrator uses `gpt-5.6-sol` with `reasoning_effort="xhigh"` and `context_tier="long_context"`.
- The orchestrator must run through the official GitHub Copilot SDK and must not fabricate benchmark results.
- Applicant PII remains in `candidates/<id>/` and `basis[]`; it never enters public claims, aggregate evidence, or `TEST_REPORT.md`.
- Every immigration policy claim remains grounded in `corpus/index.db` with exact quotes.
- Root-agent guidance uses the canonical `corpus-crawler --json <subcommand>` envelope contract and fails closed.
- `TEST_REPORT.md` reports blockers and the duplicate-audit timeout accurately.
- Release is blocked until independent goal-backward agents verify the root-agent
  "I want to review X" outcome and the completed, non-regressing self-improvement
  evidence.

---

## File Structure

| File | Responsibility |
|---|---|
| `crawler/eval/release_orchestrator.py` | PII-free aggregate evidence and GPT-5.6 Sol SDK assessment |
| `crawler/eval/test_report.py` | Deterministic report validation and rendering |
| `crawler/tests/test_phase75_release.py` | Assessment, rendering, and no-PII contracts |
| `crawler/tests/test_root_agent_workflow.py` | Natural-language review intent and four-stage workflow smoke test |
| `AGENTS.md` | Canonical root-agent intent routing and user interaction |
| `README.md` | Ready-to-use setup and minimal root-agent workflow |
| `TEST_REPORT.md` | Final measured milestone report |
| `.planning/phases/75-*/75-CONTEXT.md` | Locked release decisions |
| `.planning/phases/75-*/75-01-PLAN.md` | Release execution contract |
| `.planning/phases/75-*/75-01-SUMMARY.md` | Truthful completion evidence |

### Task 1: Build the GPT-5.6 Sol Release Orchestrator

**Files:**
- Create: `crawler/eval/release_orchestrator.py`
- Create: `crawler/eval/test_report.py`
- Create: `crawler/tests/test_phase75_release.py`

**Interfaces:**
- Consumes: validated Phase 72 research counts, Phase 73 fixture manifests, Phase 74 SDK run summaries and patch audits.
- Produces: `ReleaseEvidence`, `ReleaseAssessment`, `run_release_assessment()`, `render_test_report()`.

- [ ] **Step 1: Write failing release tests**

```python
def test_release_evidence_rejects_private_fields():
    with pytest.raises(ValueError, match="private"):
        build_release_evidence({"applicant_name": "Example"})

@pytest.mark.asyncio
async def test_release_orchestrator_uses_required_model(fake_runtime, release_evidence):
    await run_release_assessment(release_evidence, runtime=fake_runtime)
    request = fake_runtime.requests[0]
    assert request.model == "gpt-5.6-sol"
    assert request.reasoning_effort == "xhigh"
    assert request.context_tier == "long_context"
    assert request.role == "orchestrator"
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase75_release.py -q
```

- [ ] **Step 3: Implement Pydantic release schemas**

`ReleaseEvidence` contains per-document status, counts, model assignments, input and
output hashes, baseline/final metrics, score deltas, patch decisions, isolation
checks, retries, blockers, and validation commands. Reject keys matching applicant,
name, birth, passport number, document number, candidate vault, or absolute path.

- [ ] **Step 4: Implement the live SDK orchestrator**

Build a PII-free JSON prompt and call:

```python
AgentRequest(
    role="orchestrator",
    model="gpt-5.6-sol",
    reasoning_effort="xhigh",
    context_tier="long_context",
    prompt=prompt,
    attachments=[],
    timeout_seconds=900,
)
```

Validate `ReleaseAssessment.model_validate_json`. The model may interpret measured
evidence and identify blockers but may not change counts, hashes, commands, or scores.

- [ ] **Step 5: Implement deterministic report rendering**

Render measured tables directly from `ReleaseEvidence`. Use model prose only in a
clearly labeled assessment section. Include run ID, SDK version, 23 pipeline rows,
236/23 counts, exact models, baseline/final metrics, patch decisions, isolation,
cleanup, tests, blockers, and duplicate-audit status.

- [ ] **Step 6: Run release tests**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase75_release.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add crawler/eval/release_orchestrator.py crawler/eval/test_report.py crawler/tests/test_phase75_release.py
git commit -m "feat(release): add SDK release orchestrator and report renderer"
```

### Task 2: Make Root Natural-Language Review Intent Operational

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Create: `crawler/tests/test_root_agent_workflow.py`

**Interfaces:**
- Consumes: existing vault, checklist, extraction, grounding, audit, remediation, and review-packet commands.
- Produces: deterministic root-agent intent routing contract and onboarding.

- [ ] **Step 1: Write failing instruction-contract tests**

Assert `AGENTS.md` contains a review-intent entrypoint, local PII rule, all four stages,
the global-before-subcommand `--json` syntax, field confirmation, grounding, and
remediation/export. Assert `README.md` documents SDK/Python preflight and the phrase
`I want to review`.

- [ ] **Step 2: Run tests and confirm failure**

```bash
.venv/bin/python -m pytest crawler/tests/test_root_agent_workflow.py -q
```

- [ ] **Step 3: Add root intent routing to `AGENTS.md`**

Specify that requests such as "review my passport", "review this document", or
"review my Express Entry application" trigger the Lead Review Coordinator. The agent
must determine the local path and document type, initialize or reuse a candidate
vault, import locally, extract, request confirmation of uncertain fields, run the
matching grounded review and applicable screeners, and export remediation/report
artifacts. It must never print vault PII or invent missing policy.

- [ ] **Step 4: Add ready-to-use onboarding**

Document:

```bash
uv python install 3.11
poetry env use "$(uv python find 3.11)"
poetry install -E doc-extract -E ocr
poetry run python -m copilot download-runtime
poetry run corpus-crawler --json doctor
copilot
```

Then show the user message:

```text
I want to review my passport for my Express Entry application.
```

Explain that source documents and extracted fields remain local and that the agent
will ask only for information required to complete the review.

- [ ] **Step 5: Run root workflow tests**

```bash
.venv/bin/python -m pytest crawler/tests/test_root_agent_workflow.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md README.md crawler/tests/test_root_agent_workflow.py
git commit -m "docs: make root document review workflow ready to use"
```

### Task 3: Execute Release Assessment and Export `TEST_REPORT.md`

**Files:**
- Create: `TEST_REPORT.md`
- Create: `.planning/phases/75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex/75-CONTEXT.md`
- Create: `.planning/phases/75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex/75-01-PLAN.md`
- Create: `.planning/phases/75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex/75-01-SUMMARY.md`

**Interfaces:**
- Consumes: complete Phase 74 SDK run and release code.
- Produces: validated root report and GSD phase artifacts.

- [ ] **Step 1: Write Phase 75 context and execution plan**

Lock the GPT-5.6 Sol model settings, PII-free aggregate input, deterministic measured
tables, model-prose boundary, root workflow smoke test, and truthful blocker reporting.

- [ ] **Step 2: Run the live release orchestrator**

```bash
.venv/bin/python -m crawler.eval.release_orchestrator --phase74-run latest --output TEST_REPORT.md
```

Expected: one live `gpt-5.6-sol` `xhigh` `long_context` SDK assessment and a validated
root report.

- [ ] **Step 3: Run targeted release gates**

```bash
.venv/bin/python -m pytest crawler/tests/test_phase75_release.py crawler/tests/test_root_agent_workflow.py -q
REQUIRE_LIVE_PHASE74_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -q
.venv/bin/python scripts/check_publish_safe.py
```

Expected: all targeted gates pass with zero publish-safety violations.

- [ ] **Step 4: Run the existing repository suite with a bounded duplicate-audit invocation**

Run the smallest established full-suite command. Record the duplicate-audit test as
passed, failed, or timed out with its exact duration. Do not convert timeout into pass.

- [ ] **Step 5: Validate report contents**

```bash
.venv/bin/python -c "from pathlib import Path; p=Path('TEST_REPORT.md').read_text(); assert p.count('|') > 50; assert 'gpt-5.6-sol' in p; assert 'claude-opus-4.8' in p; assert 'gemini-3.6-flash' in p; assert '23' in p and '236' in p"
```

- [ ] **Step 6: Write the truthful Phase 75 summary**

Include live orchestrator provenance, report hash, root workflow test, conformance,
publish safety, full-suite outcome, and remaining blockers.

- [ ] **Step 7: Commit**

```bash
git add TEST_REPORT.md .planning/phases/75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex/75-CONTEXT.md .planning/phases/75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex/75-01-PLAN.md .planning/phases/75-gpt-5-6-sol-xhigh-orchestrator-execution-root-test-report-ex/75-01-SUMMARY.md
git commit -m "feat(75): export final document review test report"
```

### Task 4: Close the Milestone

**Files:**
- Modify: `.planning/STATE.md`
- Modify: `.planning/ROADMAP.md`
- Modify: `.planning/REQUIREMENTS.md`

**Interfaces:**
- Consumes: Phase 74 and 75 verification evidence.
- Produces: truthful completed milestone state.

- [ ] **Step 1: Run Phase 74 and Phase 75 verification**

Dispatch independent audit agents with explicit goal-backward assignments:

| Auditor | Blocking question |
|---|---|
| `gsd-verifier` | Does the implementation deliver the READY_USE-01 user outcome, rather than merely completing tasks? |
| `gsd-integration-checker` | Do root intent, vault ingestion, confirmation, grounded review, screening, remediation, and redacted export connect end to end? |
| `gsd-code-reviewer` | Are there high-confidence correctness or lifecycle defects in the shipped implementation? |
| `gsd-security-auditor` | Are Worker blindness, PII containment, process ownership, and threat mitigations present in live code? |
| `gsd-eval-auditor` | Does the completed AI phase have evidence for every evaluation dimension and non-regression gate? |
| `gsd-doc-verifier` | Do `AGENTS.md`, onboarding, and `TEST_REPORT.md` match live behavior and measured artifacts? |
| milestone audit | Does v12.0 satisfy its original intent and locked final product goal? |

Any unresolved must-have, high-severity finding, grounding failure, PII leak,
integration break, or incomplete live evidence blocks completion.

- [ ] **Step 2: Update requirement traceability**

Mark `ISOLATED_PIPELINE-01`, `JUDGE_IMPROVE-01`,
`ORCHESTRATOR_REPORT-01`, `READY_USE-01`, `READY_USE-02`, and
`REAL_AGENT_EXECUTION-01` complete only when their live evidence and all blocking
audit verdicts exist.

- [ ] **Step 3: Complete and clean the milestone**

Run the GSD complete-milestone and cleanup workflows without deleting release
evidence or root onboarding.

- [ ] **Step 4: Commit**

```bash
git add .planning/STATE.md .planning/ROADMAP.md .planning/REQUIREMENTS.md
git commit -m "docs: complete v12 document review milestone"
```
