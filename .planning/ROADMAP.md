# Roadmap: PR Review Agents — Canadian PR Application Guide

## Overview

Milestone v6.0 turns the shipped local, grounded auditor into a consistently guided multi-CLI product. A canonical `AGENTS.md` first defines the complete review behavior and portable adapter surface; synthetic document generation and evaluation then establish a feedback loop for self-improving prompt/skill/tool accuracy; conformance proves every supported runtime preserves grounding, privacy, and SAFE-01..12; onboarding and publish-safe packaging finally make that verified system ready for public use.

## Shipped Milestones

- ✅ **v1.0** (2026-06-09) — Grounded e-APR guidance and five document agents. Phases 1–8.
- ✅ **v1.1** (2026-06-09) — Corpus coverage and completeness enforcement. Phases 9–12.
- ✅ **v2.0** (2026-06-10) — Generic, shareable crawler and portable CLI contract. Phases 13–17.
- ✅ **v2.1** (2026-06-11) — Authoritative corpus ingestion and QC. Phases 18–19.
- ✅ **v2.2** (2026-06-11) — Duplicate audit, cleanup, and tooling hardening. Phases 20–22.
- ✅ **v3.0** (2026-06-21) — Grounded answer layer and portable document agents. Phases 23–27.
- ✅ **v3.1** (2026-06-24) — Complete 22-agent document pack. Phase 28.
- ✅ **v4.0** (2026-07-06) — PII-safe CRS substantiation auditor. Phases 29–34.
- ✅ **v4.1** (2026-07-17) — Auditor hardening, remediation, and redacted review packets. Phases 35–39.
- ✅ **v5.0** (2026-07-21) — Grounded eligibility and policy edge-case screening. Phases 40–46.
- ✅ **v6.0** (2026-07-22) — AGENTS.md & Multi-CLI Agent Guidance. Phases 47–51.
- ✅ **v7.0** (2026-07-22) — Multi-Case Agent Self-Improvement Loop. Phases 52–55.
- ✅ **v8.0** (2026-07-22) — Agent-Driven Realistic Defective Data Generation. Phases 56–59.
- ✅ **v9.0** (2026-07-22) — Real-World Express Entry PFL Case Benchmarking. Phases 60–63.
- ✅ **v10.0** (2026-07-22) — Real-LLM Blind Evaluation Harness & Genuine Self-Improvement Engine. Phases 64–67.
- ✅ **v11.0** (2026-07-22) — Full Live LLM Execution & Autonomous Audit Loop. Phases 68–71.
- ✅ **v12.0** (shipped 2026-07-27) — Per-Document Autonomous Research, Synthetic Generation & Blind Self-Improvement Pipeline. Phases 72–75.

## Phases

- [x] **Phase 72: Per-Document Research Agents (Gemini 3.6 Flash long context)** - Dedicated research agents for each of the 23 Express Entry document types searching online failure cases, IRCC rejections, and PFL triggers. (completed 2026-07-23)
- [x] **Phase 73: Blind Synthetic Document Generation (Gemini 3.6 Flash long context)** - Generate defective vector/scanned PDF test cases per document type based on online research with opaque filenames and isolated ground truth. (completed 2026-07-23)
- [x] **Phase 74: Blind Report Generator & Judge Self-Improvement Loop** - Run report generating worker agents with no access to research/ground truth, judge outputs using Opus 4.8 xhigh, and patch AGENTS.md/skills. (completed 2026-07-26)
- [x] **Phase 75: GPT 5.6 SOL XHIGH Orchestrator Execution & Root Test Report Export** - Orchestrate independent per-document pipelines, run self-improvement iterations, and export TEST_REPORT.md to root. (completed 2026-07-27)

## Phase Details

### Phase 68: Live Gemini 3.6 Flash LLM Worker Review Execution Engine

**Goal**: Execute live Copilot CLI LLM calls (`copilot -p ... --model gemini-3.6-flash`) for all 184 blind test fixtures, extracting document text and writing real AnswerObject JSON review reports to `reports/worker_outputs/`.
**Depends on**: Phase 67
**Requirements**: LIVE_WORKER-01
**Success Criteria** (what must be TRUE):

  1. Real Gemini 3.6 Flash LLM calls run across all 184 blind test fixtures via Copilot CLI.
  2. AnswerObject JSON review reports are saved in `reports/worker_outputs/case_XXX.json`.

### Phase 69: Live Claude Opus 4.8 xhigh Reasoning LLM Judge Evaluation Harness

**Goal**: Execute live Copilot CLI LLM judge calls (`copilot -p ... --model claude-opus-4.8 --effort xhigh`) cross-checking worker review reports against blind document text, IRCC corpus, and ground truth specs.
**Depends on**: Phase 68
**Requirements**: LIVE_JUDGE-01
**Success Criteria** (what must be TRUE):

  1. Real Claude Opus 4.8 xhigh LLM judge calls evaluate worker review reports.
  2. Category-level evaluation reports are produced in `reports/judge_group_<category>_report.json`.

### Phase 70: Autonomous Prompt & Skill Patching Optimization Loop

**Goal**: Automatically patch `AGENTS.md` system prompts and `skills/pdf/SKILL.md` based on live LLM Judge feedback and measure score improvements.
**Depends on**: Phase 69
**Requirements**: AUTO_IMPROVE-01
**Success Criteria** (what must be TRUE):

  1. Genuine prompt/skill file patches applied to `AGENTS.md` and `skills/pdf/SKILL.md`.
  2. Re-evaluation tracks real score deltas before and after prompt/skill optimization passes.

### Phase 71: Multi-CLI Conformance Re-verification & Publish Safety Release Gate

**Goal**: Re-verify that all refined prompts, skills, and tools pass the 209-node SAFE-01..12 conformance gate and zero PII / absolute path publish-safety checks.
**Depends on**: Phase 70
**Requirements**: RELEASE_GATE-01
**Success Criteria** (what must be TRUE):

  1. Complete 209-node SAFE-01..12 multi-CLI conformance suite passes 100% green.
  2. `scripts/check_publish_safe.py` confirms 0 PII or absolute path violations across tracked repository files.

## Progress

**Execution Order:** Phase 68 → Phase 69 → Phase 70 → Phase 71

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 68. Live Gemini 3.6 Flash LLM Worker Review Execution Engine | 1/1 | Complete | 2026-07-22 |
| 69. Live Claude Opus 4.8 xhigh Reasoning LLM Judge Evaluation Harness | 1/1 | Complete | 2026-07-22 |
| 70. Autonomous Prompt & Skill Patching Optimization Loop | 1/1 | Complete | 2026-07-22 |
| 71. Multi-CLI Conformance Re-verification & Publish Safety Release Gate | 1/1 | Complete | 2026-07-22 |

### Phase 72: Per-Document Research Agents (Gemini 3.6 Flash long context)

**Goal:** Run one dedicated Gemini 3.6 Flash long-context research agent for each of the 23 Express Entry document types and produce validated, source-rich failure-mode reports in isolated per-document pipeline directories.
**Requirements**: DOC_RESEARCH-01, REAL_AGENT_EXECUTION-01
**Depends on:** Phase 71
**Plans:** 3/3 plans complete

**Success Criteria**:

  1. All 23 `ExpressEntryDocType` values have exactly one isolated research report produced by a dedicated Gemini 3.6 Flash long-context agent.
  2. Every policy assertion is backed by authoritative IRCC/Justice Laws evidence and local-corpus verification; third-party discovery evidence remains explicitly labeled.
  3. Schema, citation, uniqueness, and cross-pipeline isolation validation passes for all research artifacts.
  4. Failed live research is reported as blocked after bounded retries; no generic fallback is counted as successful research.
  5. Every successful research artifact includes provenance for an actual GitHub Copilot CLI Gemini agent invocation.

Plans:
**Wave 1**

- [x] 72-01-PLAN.md — Refactor core doc researcher engine with Pydantic schema validation, fail-closed blocked recording, local corpus grounding gate, portable executable discovery, and unit contract test suite.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 72-02-PLAN.md — Implement bounded concurrent 23-document agent orchestration, human summary generation, complete execution provenance recording, and 23-document pipeline conformance test suite.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 72-03-PLAN.md — Execute live 23-agent Gemini 3.6 Flash research pass across all Express Entry document types and verify complete pipeline conformance.

### Phase 73: Blind Synthetic Document Generation (Gemini 3.6 Flash long context)

**Goal:** Generate realistic defective vector and 300 DPI scanned PDF cases from validated research while preventing filenames, paths, document contents, and worker-visible metadata from revealing the injected failures.
**Requirements**: BLIND_SYNTHETIC-01, ISOLATED_PIPELINE-01, REAL_AGENT_EXECUTION-01
**Depends on:** Phase 72
**Plans:** 4/4 plans complete

**Success Criteria**:

  1. Each of the 23 document pipelines contains research-driven vector and 300 DPI scanned cases with opaque case identifiers.
  2. Ground-truth manifests are stored outside worker-visible staged inputs and map each opaque case to its injected defects.
  3. Automated leakage tests prove filenames, PDF metadata/text, extracted text, and staged paths contain no failure labels or research hints.

Plans:
**Wave 1**

- [x] 73-01-PLAN.md — Build core generator agent schemas, side-channel leakage scanner, worker staging API, and live Copilot CLI Gemini 3.6 Flash runner.
- [x] 73-02-PLAN.md — Build metadata-sanitized ReportLab vector compilation engine and PyPDFium2 + Pillow 300 DPI scanned sibling rasterizer.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 73-03-PLAN.md — Build multi-pipeline generation coordinator, privileged ground truth writer, and synthetic conformance test suite.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 73-04-PLAN.md — Execute live 23-agent Gemini 3.6 Flash synthetic generation pass and run live 236-PDF release gate.

### Phase 74: Blind Report Generator & Judge Self-Improvement Loop

**Goal:** Execute blind Gemini report generators in structurally isolated workspaces, let only the final privileged GitHub Copilot CLI Judge using Claude Opus 4.8 (`xhigh`, `long_context`) compare their reports with research and ground truth, and apply measured prompt/skill improvements.
**Requirements**: ISOLATED_PIPELINE-01, JUDGE_IMPROVE-01, REAL_AGENT_EXECUTION-01
**Depends on:** Phase 73
**Plans:** 5/5 plans complete

**Success Criteria**:

  1. Worker process capabilities restrict readable inputs to the staged blind PDF, allowed extracted text, and public review contracts.
  2. The final Judge alone can read research and ground truth and runs through GitHub Copilot CLI with `claude-opus-4.8`, `--effort xhigh`, and `--context long_context`.
  3. Self-improvement patches are derived from Judge findings, applied only to approved prompt/skill targets, and accepted only when re-evaluation improves or preserves all safety metrics.

Plans:
**Wave 1**

- [x] 74-01-PLAN.md — Build public review bundle engine and refactor blind Worker runner for staging isolation

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 74-02-PLAN.md — Build logical sibling group train/holdout splitter and refactor batched Opus 4.8 Judge engine

**Wave 3** *(blocked on Wave 1 and Wave 2 completion)*

- [x] 74-03-PLAN.md — Build sandboxed Gemini candidate optimizer, patch evaluator, loop orchestrator, and live gate scaffold

**Wave 4** *(blocked on Wave 1, Wave 2, and Wave 3 completion)*

- [x] 74-04-PLAN.md — Execute live baseline report generation (236 Workers) and privileged evaluation (23 batched Opus Judges)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 74-05-PLAN.md — Execute targeted Gemini self-improvement iterations, atomic patch commits, final full pass, and live conformance gate

### Phase 75: GPT 5.6 SOL XHIGH Orchestrator Execution & Root Test Report Export

**Goal:** Run all 23 independent research-to-generation-to-blind-review-to-Judge pipelines automatically under one GPT 5.6 SOL XHIGH orchestrator and export the measured final results to root `TEST_REPORT.md`.
**Requirements**: ORCHESTRATOR_REPORT-01, READY_USE-01, READY_USE-02, REAL_AGENT_EXECUTION-01
**Depends on:** Phase 74
**Plans:** 4/4 plans complete

**Success Criteria**:

  1. The orchestrator runs every document pipeline independently and records explicit completion or blocker status without cross-document artifact access.
  2. The self-improvement loop records baseline, iteration, and final metrics plus every accepted or rejected patch.
  3. Root `TEST_REPORT.md` reports all 23 document pipelines, model assignments, isolation checks, failures, score deltas, and final verification results.
  4. Goal-backward audit agents prove a user can start a GitHub Copilot agent at the repository root, request review of a document or application, and complete the grounded, PII-safe review/remediation/report workflow; audit failure blocks release.

Plans:

- [x] 75-01-PLAN.md — Build the PII-free GPT-5.6 Sol release orchestrator and deterministic report renderer.
- [x] 75-02-PLAN.md — Make root natural-language review intent operational and document ready-to-use onboarding.
- [x] 75-03-PLAN.md — Execute the live release assessment, export `TEST_REPORT.md`, and run release gates.
- [x] 75-04-PLAN.md — Run blocking independent audits and close milestone v12.0.
