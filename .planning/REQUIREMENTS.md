# Requirements - Milestone v12.0 Per-Document Autonomous Research, Synthetic Generation & Blind Self-Improvement Pipeline

## Active Requirements

### DOC_RESEARCH (Per-Document Failure Research)

- [x] **DOC_RESEARCH-01**: Run one dedicated Gemini 3.6 Flash long-context research agent for each of the 23 Express Entry document types and produce validated, source-rich failure-mode reports in isolated per-document pipeline directories.

### BLIND_SYNTHETIC (Research-Driven Blind Fixtures)

- [x] **BLIND_SYNTHETIC-01**: Use Gemini 3.6 Flash long-context generator agents to turn validated research into realistic defective vector and 300 DPI scanned PDFs with opaque identifiers and separately stored ground truth.

### ISOLATED_PIPELINE (Blind Information Boundaries)

- [x] **ISOLATED_PIPELINE-01**: Run each document type in `crawler/eval/pipelines/<doc_type>/` and stage report-generator inputs so workers can access only the blind PDF and allowed extracted text, never research, ground truth, defect labels, revealing filenames, or privileged paths.

### JUDGE_IMPROVE (Privileged Evaluation and Self-Improvement)

- [x] **JUDGE_IMPROVE-01**: Allow only a GitHub Copilot CLI Judge using Claude Opus 4.8 with `xhigh` reasoning and `long_context` to compare blind worker reports with research and ground truth, score defect recall, grounding, citation exactness, and PII containment, then drive measured prompt/skill improvements.

### ORCHESTRATOR_REPORT (Autonomous Execution and Report)

- [x] **ORCHESTRATOR_REPORT-01**: Run the complete per-document pipeline under a GPT 5.6 SOL XHIGH orchestrator and export a comprehensive `TEST_REPORT.md` at the repository root.

### READY_USE (Release-Blocking Final Product Goal)

- [x] **READY_USE-01**: A user can start a GitHub Copilot agent at the repository root, state "I want to review X," and be guided through local candidate-vault ingestion, field confirmation, corpus-grounded document review, applicable CRS/policy screening, remediation, and redacted report export without leaking PII or inventing immigration requirements.
- [x] **READY_USE-02**: Independent goal-backward verifier, integration, security, code-review, and milestone-audit agents confirm the final product goal is achieved; any unresolved must-have, high-severity issue, grounding failure, PII leak, or incomplete self-improvement evidence blocks milestone completion.

### REAL_AGENT_EXECUTION (Truthful GitHub Copilot Agent Runtime)

- [x] **REAL_AGENT_EXECUTION-01**: Execute every claimed researcher, synthetic generator, report worker, Judge, optimizer, and orchestrator role through a real GitHub Copilot CLI agent session with the assigned model/context/effort; production failures must be explicit and no deterministic or hardcoded substitute may be reported as model output.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DOC_RESEARCH-01 | Phase 72 | Complete |
| BLIND_SYNTHETIC-01 | Phase 73 | Complete |
| ISOLATED_PIPELINE-01 | Phases 73-74 | Complete |
| JUDGE_IMPROVE-01 | Phase 74 | Complete |
| ORCHESTRATOR_REPORT-01 | Phase 75 | Complete |
| READY_USE-01 | Phase 75 | Complete |
| READY_USE-02 | Phase 75 / Milestone Audit | Complete |
| REAL_AGENT_EXECUTION-01 | Phases 72-75 | Complete |

## Out of Scope

- Model fine-tuning or cloud database hosting.
- Modifying IRCC authoritative laws or external guidance.
- Giving blind report-generating agents access to failure labels or research artifacts.
- Reporting deterministic Python output, ground-truth-derived output, or a hardcoded fallback as a successful GitHub Copilot agent result.
