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

## Phases

- [x] **Phase 47: Canonical AGENTS.md & Multi-CLI Adapter Layer** - Users receive the same grounded, PII-safe review workflow through every supported agent CLI.
- [ ] **Phase 48: PDF Skill & Synthetic PDF Testing Engine** - Dedicated PDF processing skill (`skills/pdf/`) and synthetic text & image PDF test generator covering all 22 Express Entry document types + LoE, isolated in git-ignored `crawler/eval/test_data/`.
- [ ] **Phase 49: Agent Evaluation & Iterative Self-Improvement Loop** - Benchmark evaluation harness scores agent reviews against synthetic PDF ground truth and iteratively refines prompts (`AGENTS.md`), skills, and tools.
- [ ] **Phase 50: Multi-CLI Conformance & Release Gate** - Maintainers can prove all supported runtimes obey the canonical contracts and safety invariants.
- [ ] **Phase 51: User Guidance & Production Release Packaging** - New users can adopt the verified system from a publish-safe, production-ready repository.

## Phase Details

### Phase 47: Canonical AGENTS.md & Multi-CLI Adapter Layer

**Goal**: Users can invoke any supported agent CLI and receive one canonical, grounded, PII-safe document-review and CRS-audit workflow.
**Depends on**: Phase 46
**Requirements**: AGENT-01, AGENT-02, AGENT-03, ADAPT-01, ADAPT-02
**Success Criteria** (what must be TRUE):

  1. A user entering through any supported CLI adapter gets the roles, tool contracts, and execution behavior defined by the canonical `AGENTS.md`, without a competing CLI-specific workflow.
  2. An applicant is guided step by step from candidate setup through extraction confirmation, audit execution, and remediation export.
  3. Review interactions cite authoritative sources, keep applicant PII in the local private boundary, and abstain or fail closed instead of emitting an ungrounded assertion.
  4. A user can invoke the portable `skills/` interface from supported runtimes using CLI-agnostic Markdown, without a proprietary API dependency.

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 47-01-PLAN.md — Author canonical AGENTS.md system specification, roles, contracts, fail-closed grounding rules, and 4-stage workflow

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 47-02-PLAN.md — Create thin multi-CLI pointer adapters (Claude, Copilot, Codex, Cursor, Windsurf) and document portable skills interface

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 47-03-PLAN.md — Establish synthetic PII-free evaluation benchmarks and complete automated instruction evaluation test suite

**UI hint**: yes

### Phase 48: PDF Skill & Synthetic PDF Testing Engine

**Goal**: Implement a dedicated PDF processing & generation skill (`skills/pdf/`) and generate synthetic text and image-based scanned PDF test fixtures for all 22 Express Entry document types plus Letters of Explanation (LoE), stored in an isolated git-ignored directory (`crawler/eval/test_data/`) for easy cleanup before public release.
**Depends on**: Phase 47
**Requirements**: PDF-01, PDF-02, PDF-03
**Success Criteria** (what must be TRUE):

  1. Portable `skills/pdf/` skill is implemented providing text, table, and image extraction, OCR handling, and PDF creation workflows (`reportlab`, `pypdfium2`, `pdfplumber`).
  2. Synthetic generator creates realistic text-based and scanned/image-based PDF test files for all 22 Express Entry document types and Letters of Explanation (LoE) with known defects.
  3. All generated test PDFs and raw sample datasets are isolated in git-ignored `crawler/eval/test_data/` for easy removal prior to public repository release.

**Plans**: TBD

### Phase 49: Agent Evaluation & Iterative Self-Improvement Loop

**Goal**: Benchmark agent review outputs against synthetic PDF ground truth and iteratively refine system prompts (`AGENTS.md`), review skills (`skills/`), and tool error handling to minimize mistake rates.
**Depends on**: Phase 48
**Requirements**: SELF-01, SELF-02
**Success Criteria** (what must be TRUE):

  1. Automated evaluation harness evaluates agent reviews against synthetic PDF ground truth, scoring grounding accuracy, citation exactness, defect recall, and PII containment.
  2. Evaluation findings drive an iterative self-improvement loop that refines `AGENTS.md`, document review skills (`skills/`), and tool error handling to measurably reduce mistake rates.

**Plans**: TBD

### Phase 50: Multi-CLI Conformance & Release Gate

**Goal**: Maintainers can prove that every supported agent runtime executes the canonical workflow without weakening grounding, privacy, or release safety.
**Depends on**: Phase 49
**Requirements**: VERIFY-01, VERIFY-02
**Success Criteria** (what must be TRUE):

  1. A maintainer can run one automated conformance suite and see whether each supported CLI runtime follows the canonical system prompt and tool-invocation contracts.
  2. Adversarial runs that attempt to expose PII or produce uncited advice fail the gate across every supported runtime.
  3. A release is blocked unless multi-CLI conformance and the complete SAFE-01..12 checks pass, with clear failure evidence identifying the violated runtime or invariant.

**Plans**: TBD

### Phase 51: User Guidance & Production Release Packaging

**Goal**: New users can set up, run, and understand the verified multi-agent review system from a publish-safe production release.
**Depends on**: Phase 50
**Requirements**: SHIP-01, SHIP-02
**Success Criteria** (what must be TRUE):

  1. A new user can follow the `README.md` quickstart to configure a supported AI CLI and complete an initial document-review run.
  2. A user can follow `GUIDE.md` from candidate setup and extraction confirmation through grounded audit and remediation output across supported CLIs.
  3. A maintainer can assemble the final release with safe template profiles and receive a passing publish-safety and repository-readiness result.
  4. A public repository visitor can clone the release and find the guidance, adapters, skills, and templates needed to start without encountering private applicant data.

**Plans**: TBD

## Progress

**Execution Order:** Phase 47 → Phase 48 → Phase 49 → Phase 50 → Phase 51

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 47. Canonical AGENTS.md & Multi-CLI Adapter Layer | 3/3 | Complete | 2026-07-21 |
| 48. PDF Skill & Synthetic PDF Testing Engine | 0/TBD | Not started | - |
| 49. Agent Evaluation & Iterative Self-Improvement Loop | 0/TBD | Not started | - |
| 50. Multi-CLI Conformance & Release Gate | 0/TBD | Not started | - |
| 51. User Guidance & Production Release Packaging | 0/TBD | Not started | - |
