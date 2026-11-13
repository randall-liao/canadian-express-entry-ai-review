# Requirements — Milestone v6.0 AGENTS.md & Multi-CLI Agent Guidance

## Active Requirements

### AGENTS (Canonical System Specification & Roles)

- [x] **AGENT-01**: `AGENTS.md` defines canonical multi-agent roles, tool orchestration contracts, and execution workflows for post-ITA document review and CRS audit.
- [x] **AGENT-02**: `AGENTS.md` enforces the grounded citation requirement, PII containment rules, and zero-ungrounded-assertion constraint across all document review interactions.
- [x] **AGENT-03**: `AGENTS.md` specifies step-by-step applicant document review workflows, guiding AI agents through candidate setup, extraction confirmation, audit execution, and remediation export.

### ADAPT (Multi-CLI Pointer Adapters & Integration)

- [x] **ADAPT-01**: Thin pointer adapters provided for GitHub Copilot (`.github/copilot-instructions.md`), Claude (`CLAUDE.md`), Codex (`.codex/AGENTS.md`), Cursor (`.cursor/rules/`), and Antigravity delegating to `AGENTS.md`.
- [x] **ADAPT-02**: Portable `skills/` interface exposed in CLI-agnostic markdown format, compatible with all supported agent runtimes without proprietary API locks.

### PDF (PDF Skill & Synthetic Document Testing Engine)

- [ ] **PDF-01**: Portable PDF processing & generation skill (`skills/pdf/`) supporting text/table/image extraction, rendering, OCR, and PDF creation (`reportlab`, `pypdfium2`, `pdfplumber`).
- [ ] **PDF-02**: Synthetic PDF generator creates realistic text-based and scanned/image-based PDF test fixtures for all 22 Express Entry document types plus Letters of Explanation (LoE).
- [ ] **PDF-03**: All synthetic test PDF files and generated datasets are isolated in a dedicated, git-ignored directory (`crawler/eval/test_data/`) for easy removal before public repo release.

### SELF (Agent Evaluation & Self-Improvement Loop)

- [ ] **SELF-01**: Automated evaluation harness benchmark-scores agent document reviews against synthetic PDF ground truth (grounding accuracy, citation exactness, defect recall, PII containment).
- [ ] **SELF-02**: Iterative self-improvement loop refines system prompts (`AGENTS.md`), review skills (`skills/`), and tool error handling based on evaluation findings to minimize error rates.

### VERIFY (Multi-CLI Conformance & Automated Testing)

- [ ] **VERIFY-01**: Automated conformance test suite verifies `AGENTS.md` system prompt and tool invocations across supported CLI agent runtimes.
- [ ] **VERIFY-02**: Multi-CLI release gate proves zero PII leakage, zero ungrounded advice, and SAFE-01..12 release gate compliance before final release.

### SHIP (Production Documentation & Release Packaging)

- [ ] **SHIP-01**: User onboarding quickstart and end-to-end guide (`README.md`, `GUIDE.md`) explaining multi-agent document review setup and usage across different AI CLIs.
- [ ] **SHIP-02**: Final production release package, template profiles, publish-safety verification, and public GitHub repository readiness.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AGENT-01 | Phase 47 | Complete |
| AGENT-02 | Phase 47 | Complete |
| AGENT-03 | Phase 47 | Complete |
| ADAPT-01 | Phase 47 | Complete |
| ADAPT-02 | Phase 47 | Complete |
| PDF-01 | Phase 48 | Pending |
| PDF-02 | Phase 48 | Pending |
| PDF-03 | Phase 48 | Pending |
| SELF-01 | Phase 49 | Pending |
| SELF-02 | Phase 49 | Pending |
| VERIFY-01 | Phase 50 | Pending |
| VERIFY-02 | Phase 50 | Pending |
| SHIP-01 | Phase 51 | Pending |
| SHIP-02 | Phase 51 | Pending |

## Out of Scope

- Model fine-tuning or proprietary LLM runtime dependencies
- Web-hosted cloud service or multi-tenant user backend (stays 100% local and offline)
- Direct automated interaction with IRCC web portal or account submission
