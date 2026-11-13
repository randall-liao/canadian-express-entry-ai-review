# Phase 47: Canonical AGENTS.md & Multi-CLI Adapter Layer - Research

**Researched:** 2026-07-21
**Domain:** Canonical Agent Specifications, Prompt Engineering, & Multi-CLI Adapter Layer
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Canonical AGENTS.md**: Define system prompt, tool contracts (`corpus-crawler`, `vault`), multi-agent roles, and step-by-step review workflows in a single portable `AGENTS.md`.
- **Fail-Closed Grounding**: The agent MUST refuse to answer or make claims that cannot be verbatim-grounded in the curated corpus/repo content.
- **Prompt Engineering Best Practices**: Structure agent prompts with role definition, explicit inputs/outputs, negative constraints, and verification loops to minimize hallucinations and mistake rates.
- **Thin Pointer Files**: `.github/copilot-instructions.md`, `CLAUDE.md`, `.codex/AGENTS.md`, `.cursor/rules/agents.mdc`, etc., delegate directly to `AGENTS.md`.
- **Portable Skills**: `skills/` directory formatted in CLI-agnostic Markdown accessible without proprietary API locks.
- **Synthetic Sample Documents**: Create sample applicant document fixtures to benchmark and evaluate agent instructions and error rates.

### the agent's Discretion
- Implementation details for adapter pointer file schemas, prompt section organization, and synthetic benchmark evaluation fixture design are left to planner discretion based on research findings.

### Deferred Ideas (OUT OF SCOPE)
- Model fine-tuning or proprietary LLM runtime dependencies.
- Web-hosted cloud service or multi-tenant user backend (stays 100% local and offline).
- Direct automated interaction with IRCC web portal or account submission.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AGENT-01 | `AGENTS.md` defines canonical multi-agent roles, tool orchestration contracts, and execution workflows for post-ITA document review and CRS audit. | Researched single-source system prompt layout, tool contracts (`corpus-crawler --json`), 4-role agent topology, and 4-stage applicant review workflow. [VERIFIED: repo contracts] |
| AGENT-02 | `AGENTS.md` enforces the grounded citation requirement, PII containment rules, and zero-ungrounded-assertion constraint across all document review interactions. | Researched negative prompt constraints, `claims[]` vs `basis[]` structural split, fail-closed `abstentions[]`, and `ground` gate self-correction piping. [VERIFIED: repo contracts] |
| AGENT-03 | `AGENTS.md` specifies step-by-step applicant document review workflows, guiding AI agents through candidate setup, extraction confirmation, audit execution, and remediation export. | Researched 4-stage operational pipeline (`init`/`profile`/`ita` -> `extract`/`confirm` -> `audit`/`screen` -> `remediate`/`review-packet`). [VERIFIED: repo contracts] |
| ADAPT-01 | Thin pointer adapters provided for GitHub Copilot (`.github/copilot-instructions.md`), Claude (`CLAUDE.md`), Codex (`.codex/AGENTS.md`), Cursor (`.cursor/rules/`), and Antigravity delegating to `AGENTS.md`. | Researched per-CLI pointer file conventions (`CLAUDE.md`, `.github/copilot-instructions.md`, `.codex/AGENTS.md`, `.cursor/rules/agents.mdc`, `.windsurfrules`). [CITED: CLI vendor specifications] |
| ADAPT-02 | Portable `skills/` interface exposed in CLI-agnostic markdown format, compatible with all supported agent runtimes without proprietary API locks. | Verified `skills/document-agents/` and `skills/crs-auditors/` contracts, confirming CLI-agnostic markdown format without proprietary lock-in. [VERIFIED: repo contracts] |
</phase_requirements>

## Summary

Phase 47 establishes the single source of truth for all AI agent interactions across supported agent CLI runtimes (Copilot, Claude, Codex, Cursor, Antigravity, Windsurf). Rather than writing custom, divergent system prompts for each agent environment, Phase 47 creates a canonical `AGENTS.md` at the repository root that defines agent roles, CLI tool contracts, step-by-step review workflows, fail-closed grounding rules, and PII containment. Per-CLI instruction files remain thin pointer adapters that redirect the respective agent runtime directly to `AGENTS.md`.

The technical foundation built in Milestones v1.0 through v5.0 provides deterministic CLI tools (`corpus-crawler` with verbs like `search`, `ground`, `checklist`, and `vault` subcommands for `init`, `extract`, `confirm`, `audit`, `remediate`, `review-packet`, `screen-mec`, `noc-review`, `study-review`). `AGENTS.md` serves as the authoritative orchestrator that instructs AI agents how to invoke these CLI tools, parse JSON stdout, enforce the structural PII split (`claims[]`generic vs `basis[]` personal), pipe generated answer objects through `corpus-crawler ground` for self-correction, and emit fail-closed abstentions whenever authoritative proof is absent.

To verify prompt compliance and measure instruction adherence, Phase 47 also establishes a synthetic evaluation fixture strategy (`crawler/eval/synthetic_fixtures/`) containing 100% fake-PII applicant profiles and document extractions. An automated test suite (`crawler/tests/test_instruction_eval.py`) verifies that agents following `AGENTS.md` correctly execute tool calls, enforce grounding citations, respect PII boundaries, and handle out-of-corpus queries with explicit abstentions.

**Primary recommendation:** Author a single, authoritative `AGENTS.md` at repo root with explicit tool contracts and multi-agent roles. Implement thin adapter files (`CLAUDE.md`, `.github/copilot-instructions.md`, `.codex/AGENTS.md`, `.cursor/rules/agents.mdc`, `.windsurfrules`) containing 15-25 lines that direct CLIs to delegate 100% of instructions to `AGENTS.md` and `skills/`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Canonical System Specification & Roles | `AGENTS.md` System Prompt | — | Single source of truth for agent system prompts, roles, contracts, and workflows across all CLIs. [VERIFIED: repo contracts] |
| Multi-CLI Adapter Delegation | Thin Pointer Files (`CLAUDE.md`, etc.) | — | Lightweight adapter files forwarding agent context to `AGENTS.md` without duplicating logic. [CITED: CLI vendor specs] |
| Domain Skill Knowledge | Portable Markdown (`skills/`) | — | CLI-agnostic skill files defining per-document and per-auditor execution steps. [VERIFIED: repo contracts] |
| Tool Invocations & Execution | Shared Python CLI (`corpus-crawler`) | Python Runtime | Executes deterministic searches, extraction, audits, grounding gate, and PII containment. [VERIFIED: repo contracts] |
| Private Applicant State | Candidate Vault (`candidates/<id>/`) | Local Filesystem | Git-ignored storage keeping applicant PII completely isolated from public harness. [VERIFIED: repo contracts] |
| Benchmark Evaluation | Synthetic Fixtures (`crawler/eval/`) | Automated Test Runner (`pytest`) | Synthetic profiles & documents benchmarking instruction compliance and fail-closed grounding. [VERIFIED: repo contracts] |

## Standard Stack

### Core
| Library / Tool | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| Python | >=3.10, <4.0 | Runtime environment for shared tools | Project standard for CLI tools and data processing. [VERIFIED: pyproject.toml] |
| Poetry | ^2.0.0 | Python dependency management | Standard project dependency lock and environment manager. [VERIFIED: pyproject.toml] |
| `corpus-crawler` CLI | 2.0.0 | Shared CLI interface for search, grounding, vault, audit | Core tool suite providing deterministic JSON contracts. [VERIFIED: pyproject.toml] |
| `pytest` | >=9.0 | Automated conformance and evaluation test framework | Standard testing runner used for release gates. [VERIFIED: pyproject.toml] |

### Supporting
| Library / Tool | Version | Purpose | When to Use |
|----------------|---------|---------|-------------|
| `pydantic` | >=2.13, <3.0 | Data modeling and schema validation | Validating JSON contract envelopes and evaluation fixtures. [VERIFIED: pyproject.toml] |
| `pyyaml` | >=6.0, <7.0 | YAML parsing for Cursor rules and crawler profiles | Reading `.cursor/rules/agents.mdc` frontmatter and site profiles. [VERIFIED: pyproject.toml] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-CLI Custom Prompts | Single `AGENTS.md` + Thin Adapters | Per-CLI custom prompts cause instruction drift, duplicate maintenance, and inconsistent grounding behavior across runtimes. Single `AGENTS.md` guarantees uniform execution. [VERIFIED: repo architecture] |
| Proprietary LLM API Locks / MCP Servers | Plain Shell Commands + `--json` | MCP / vendor APIs create vendor lock-in and break offline CLI runtimes. Plain shell commands + JSON parsing work in any CLI. [VERIFIED: AGENT_SKILL.md] |

## Package Legitimacy Audit

> **Required** whenever this phase installs external packages.

Phase 47 installs **zero new external runtime dependencies**. It relies entirely on the established Python tool ecosystem (`corpus-crawler`), standard markdown instructions, and existing test frameworks (`pytest`).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *None* | N/A | N/A | N/A | N/A | [OK] | No external packages installed in Phase 47 |

**Packages removed due to [SLOP] verdict:** None  
**Packages flagged as suspicious [SUS]:** None

## Architecture Patterns

### System Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                            Multi-CLI Entry Surface                                |
|  [GitHub Copilot]   [Claude Code]   [OpenAI Codex]   [Cursor IDE]   [Windsurf]    |
|   .github/copilot-  CLAUDE.md       .codex/AGENTS.md .cursor/rules/ .windsurfrules|
|   instructions.md                                     agents.mdc                  |
+------------------------------------------+----------------------------------------+
                                           |
                                           | (Delegates 100% to)
                                           v
+-----------------------------------------------------------------------------------+
|                       Canonical AGENTS.md System Prompt                           |
|  - System Role & Core Mission (Post-ITA Document Review & CRS Audit)              |
|  - Multi-Agent Roles (Coordinator, Document Agents, CRS Auditors, Remediation)   |
|  - Tool Orchestration Contracts (corpus-crawler --json <subcommand>)               |
|  - 4-Stage Workflow (Setup -> Extract/Confirm -> Audit/Screen -> Remediate/Export) |
|  - Fail-Closed Grounding & PII Containment Invariants                             |
+------------------------------------------+----------------------------------------+
                                           |
                                           | (References domain skills)
                                           v
+-----------------------------------------------------------------------------------+
|                        Portable Skills Surface (skills/)                         |
|  - Document Agents: skills/document-agents/ (22 agents + _contract.md)            |
|  - CRS Auditors: skills/crs-auditors/ (4 modules + _contract.md)                 |
+------------------------------------------+----------------------------------------+
                                           |
                                           | (Executes shell commands)
                                           v
+-----------------------------------------------------------------------------------+
|                       Shared Python Tooling (corpus-crawler)                      |
|  - Search & Grounding: search, ground, checklist                                 |
|  - Vault & Extraction: vault init, extract, fields, confirm                       |
|  - Audit & Screening: vault audit, screen-mec, noc-review, study-review           |
|  - Remediation & Export: vault remediate, vault review-packet                     |
+------------------------------------------+----------------------------------------+
                                           |
                       +-------------------+-------------------+
                       |                                       |
                       v                                       v
+---------------------------------------------+ +----------------------------------+
|           Private Candidate Vault           | |      Authoritative Local Corpus    |
|  candidates/<id>/ (Profile, Docs, Extractions| |  corpus/ (742 docs, FTS5 index)  |
|  Git-ignored, 100% Local PII Containment)   | |  Grounding rules & citations   |
+---------------------------------------------+ +----------------------------------+
```

### Recommended Project Structure

```
.
├── AGENTS.md                          # Canonical system specification & multi-agent prompt
├── CLAUDE.md                          # Thin pointer adapter for Claude CLI
├── .github/
│   └── copilot-instructions.md        # Thin pointer adapter for GitHub Copilot Workspace
├── .codex/
│   └── AGENTS.md                      # Thin pointer adapter for OpenAI Codex CLI
├── .cursor/
│   └── rules/
│       └── agents.mdc                 # Thin pointer adapter for Cursor IDE
├── .windsurfrules                     # Thin pointer adapter for Windsurf Cascade
├── skills/                            # CLI-agnostic portable Markdown skills
│   ├── document-agents/               # 22 document agent skills + _contract.md
│   └── crs-auditors/                  # 4 auditor skills + _contract.md
└── crawler/
    ├── eval/                          # Evaluation benchmarks & synthetic fixtures
    │   └── synthetic_fixtures/        # PII-free synthetic profiles & document extractions
    └── tests/
        └── test_instruction_eval.py  # Automated prompt instruction compliance suite
```

### Pattern 1: Multi-CLI Adapter Delegation Pattern
**What:** Per-CLI instruction files (`CLAUDE.md`, `.github/copilot-instructions.md`, `.codex/AGENTS.md`, `.cursor/rules/agents.mdc`, `.windsurfrules`) contain minimal wrapper instructions directing the agent to read and follow `/AGENTS.md` for all system prompts, tool usage, and execution steps.
**When to use:** In any multi-CLI project to eliminate instruction duplication, prevent behavioral drift across runtimes, and maintain a single maintenance boundary.
**Example:**
```markdown
# Claude Adapter (`CLAUDE.md`)
# PR Review Agents — Claude Adapter

This repository uses `AGENTS.md` at the repository root as its canonical system prompt, agent specification, and tool orchestration guide.

## System Specification Delegation
- **Canonical Instructions**: Read and follow `/AGENTS.md` for all agent roles, tool orchestration contracts, workflow steps, fail-closed grounding rules, and PII containment requirements.
- **Domain Skills**: Refer to `skills/document-agents/` and `skills/crs-auditors/` for specific document-check and CRS-audit skill procedures.
- **Execution Mode**: Invoke tools via `corpus-crawler --json <subcommand>` shell calls and parse the 5-key JSON stdout envelope (`schema_version`, `ok`, `command`, `result`, `error`).

Do not alter or override the rules in `AGENTS.md`.
```

### Pattern 2: Multi-Agent Role & 4-Stage Workflow Pattern
**What:** `AGENTS.md` structures agent responsibilities into four distinct roles and a linear four-stage operational workflow.
**Roles:**
1. **Lead Review Coordinator**: Welcomes applicant, manages candidate setup, delegates tasks to specialized agents, executes vault commands, and formats output.
2. **Document Review Agent**: Uses `skills/document-agents/` to verify mandatory e-APR supporting documents (passports, language tests, reference letters, etc.) against grounded corpus rules.
3. **CRS Auditor Agent**: Uses `skills/crs-auditors/` and `corpus-crawler vault audit` to substantiate claimed CRS factors against confirmed document extractions.
4. **Remediation & Export Agent**: Runs `corpus-crawler vault remediate` and `vault review-packet` to generate actionable private checklists and redacted lawyer packets.

**4-Stage Operational Workflow:**
1. **Stage 1 — Candidate Setup & Ingestion:** Initialize vault (`vault init`), load profile/ITA (`vault profile`, `vault ita`), import documents (`vault import`), generate personalized checklist (`checklist`).
2. **Stage 2 — Document Extraction & Confirmation:** Extract fields (`vault extract`), check scan quality (`doctor`), review pending fields (`vault fields`), confirm/correct extracted values (`vault confirm`).
3. **Stage 3 — Grounded Audit & Screening:** Run CRS substantiation audit (`vault audit --all`), execute edge-case policy screens (`vault screen-mec`, `vault noc-review`, `vault study-review`).
4. **Stage 4 — Remediation & Export:** Generate private remediation checklist (`vault remediate`), export redacted professional review packet (`vault review-packet`).

### Pattern 3: Fail-Closed Grounding Pipe Loop & PII Tier Split Pattern
**What:** Agents must construct structured answer objects containing `question`, `claims[]`, `basis[]`, `abstentions[]`, and `prose`. Every claim is grounded via a verbatim quote and corpus citation. Personal data is isolated in `basis[]` or candidate vault files. Agents pipe generated answer objects into `corpus-crawler ground --db corpus/index.db` for automated verification and self-correction.
**When to use:** Whenever an agent generates guidance or requirement claims.
**Example:**
```bash
# Agent self-correction loop: Pipe generated JSON answer object to grounding gate
corpus-crawler --json ground --db corpus/index.db <<'JSON'
{
  "question": "Who must undergo an immigration medical examination?",
  "claims": [
    {
      "id": "c1",
      "text": "Foreign nationals applying for permanent residence must undergo an immigration medical examination.",
      "citations": ["medical/who-must-submit-immigration-medical-examination.md#000"],
      "quote": "Foreign nationals who are applying for a permanent resident visa (PRV) or applying to remain in Canada as a permanent resident"
    }
  ],
  "basis": ["Applicant is submitting an Express Entry e-APR."],
  "abstentions": [],
  "prose": ""
}
JSON
```
If the output envelope returns `result.verdict == "fail"`, the agent inspects `result.reasons` (`uncited`, `unresolvable`, `quote_not_in_chunk`) and either adjusts the verbatim quote or moves the item to `abstentions[]`.

### Pattern 4: Synthetic Evaluation Fixtures & Instruction Benchmarking Pattern
**What:** Create synthetic candidate profiles and document extraction JSON fixtures (`crawler/eval/synthetic_fixtures/`) with 100% synthetic/fake PII (e.g., Jane Doe, synthetic passport numbers, fictional dates). Write automated `pytest` suites (`crawler/tests/test_instruction_eval.py`) that evaluate agent prompt rules: verifying JSON output schemas, quote exactness, PII non-leakage, and out-of-corpus abstention behavior.
**When to use:** To prove agent instructions enforce grounding and privacy invariants without requiring an active LLM API key during CI test execution.

### Anti-Patterns to Avoid
- **Per-CLI Instruction Duplication:** Writing distinct, detailed rules in `CLAUDE.md`, `copilot-instructions.md`, etc. This leads to out-of-sync behavior where one CLI enforces grounding and another hallucinates.
- **Soft Grounding / Summary Quotation:** Allowing agents to summarize corpus text in `claims[].quote`. Quotes MUST be exact, verbatim substrings of resolving corpus chunks.
- **Inlined Volatile Rules:** Writing specific dollar amounts, validity windows, or score thresholds directly into agent prompts or adapter instructions. All volatile figures must be cited dynamically from the corpus or rule registry.
- **PII Pollution in Claims:** Putting applicant names, birthdates, or document numbers into `claims[].text` or `claims[].quote`. All applicant values must remain in `basis[]` or in private candidate vault files.
- **Presuming Execution Green on Pending Extractions:** Treating unconfirmed extracted fields as `SUBSTANTIATED`. Unconfirmed fields MUST remain `AT-RISK` / pending human confirmation via `vault confirm`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Grounding Verification | Custom string matching or regex in agent prompts | `corpus-crawler ground` CLI verb | The shipped grounding gate normalizes case/whitespace, validates SHA hashes, and enforces fail-closed quote verification. [VERIFIED: repo contracts] |
| Per-CLI Workflow Logic | Proprietary JSON/YAML agent configs per CLI | `AGENTS.md` + Thin Pointer Adapters | Proprietary CLI configs lock the project to a single vendor and require redundant maintenance. Markdown pointer adapters work across all CLIs. [VERIFIED: repo architecture] |
| PII Redaction & Containment | Custom regex search/replace in agent prompts | Candidate Vault Isolation + `basis[]` Partitioning | Vault files stay in git-ignored `candidates/<id>/`. Public stdout envelopes project PII-light fields only. [VERIFIED: repo contracts] |
| CRS Rule Calculation | Custom math or threshold checks in LLM logic | `corpus-crawler vault audit` verb | LLMs frequently make arithmetic errors and hallucinate score caps. `vault audit` uses a grounded rule registry + deterministic Python math. [VERIFIED: repo contracts] |

**Key insight:** AI agents in this project act as *orchestrators and authors*, driving deterministic Python CLI tools (`corpus-crawler`). Agents should never re-implement calculation, extraction, search, or grounding logic inside prompt text.

## Common Pitfalls

### Pitfall 1: Adapter Instruction Drift
**What goes wrong:** Developers update instructions in `CLAUDE.md` but forget `.github/copilot-instructions.md` or `.cursor/rules/agents.mdc`, causing different AI CLIs to behave inconsistently.  
**Why it happens:** Duplicating instructions across multiple files.  
**How to avoid:** Keep per-CLI files strictly as thin pointer adapters (15-25 lines) delegating 100% of instruction content to `AGENTS.md`.  
**Warning signs:** A feature or constraint mentioned in `CLAUDE.md` is missing from `copilot-instructions.md`.

### Pitfall 2: Paraphrase Grounding Failures
**What goes wrong:** The agent rephrases a corpus sentence when populating `claims[].quote`, causing `corpus-crawler ground` to fail with `quote_not_in_chunk`.  
**Why it happens:** LLMs naturally attempt to summarize or rephrase source text.  
**How to avoid:** Emphasize in `AGENTS.md` that `quote` MUST be copied verbatim from `result.chunk.text` returned by `corpus-crawler search --cite <id>`. Instruct the agent to run the self-correction pipe loop.  
**Warning signs:** Grounding gate returning `verdict: "fail"` with `reasons: ["quote_not_in_chunk"]`.

### Pitfall 3: PII Leakage into Public Output Envelopes
**What goes wrong:** An agent includes applicant details (e.g., "John Doe's IELTS score is CLB 9") in `claims[].text`.  
**Why it happens:** Blending requirement claims with applicant profile data.  
**How to avoid:** Enforce strict structural separation in `AGENTS.md`: `claims[]` contain generic requirement statements only; all applicant facts go into `basis[]` or remain inside `candidates/<id>/`.  
**Warning signs:** Applicant names or document numbers appearing in `claims[].text` or public report markdown.

### Pitfall 4: Flaky Synthetic Evaluation Benchmarks
**What goes wrong:** Benchmark test fixtures fail because cited chunk IDs drift or synthetic test quotes become stale after a corpus refresh.  
**Why it happens:** Hardcoding fragile chunk IDs or old text in synthetic fixtures without checking index health.  
**How to avoid:** Use `corpus-crawler index_health` preflight checks and base synthetic benchmarks on stable questions in `crawler/eval/questions.jsonl`.  
**Warning signs:** Test suite failures on `test_instruction_eval.py` after corpus updates.

## Code Examples

### Example 1: Canonical `AGENTS.md` Structural Layout

```markdown
# AGENTS.md — Canonical System Specification & Multi-CLI Agent Instructions

This file is the single source of truth for all AI agent runtimes (Copilot, Claude, Codex, Cursor, Antigravity, Windsurf) working in this repository.

## 1. System Role & Core Mission
You are the **PR Review Agent**, an expert, citable guidance system for Canadian permanent residence applicants submitting an Express Entry e-APR post-ITA application.

### Invariant Principles
1. **100% Grounded Citations**: Every claim about immigration requirements, documents, or CRS points MUST be verbatim-grounded in the curated corpus via `corpus-crawler`.
2. **Zero Ungrounded Assertions**: If a topic is not in the corpus or search returns no hits, you MUST emit an explicit `abstentions[]` entry and ZERO claims. Never guess or extrapolate.
3. **Strict PII Containment**: Applicant personal data (PII) MUST stay strictly local in git-ignored `candidates/<id>/` vault files or in `basis[]`. Never include PII in `claims[]` or stdout.

## 2. Tool Orchestration Contracts
All tools are invoked via the `corpus-crawler` Python CLI.

### Execution Syntax & Invariants
- Command format: `corpus-crawler --json <subcommand> [args...]`
- **stdout**: Exactly ONE JSON object matching the 5-key envelope:
  `{"schema_version": "1.0", "ok": true, "command": "<cmd>", "result": {...}, "error": null}`
- **stderr**: Diagnostic text — surface to user, never parse as JSON.
- **Read `ok` first**: If `ok: false`, read `error.type` and `error.message`.

### Available Commands
- `checklist`: Generate personalized Layer-1 document checklist from profile.
- `search`: Keyword search FTS5 index (`--db corpus/index.db`) or resolve citation (`--cite <id>`).
- `ground`: Fail-closed grounding gate — validates answer JSON piped on stdin.
- `vault`: Subcommands (`init`, `profile`, `ita`, `import`, `list`, `extract`, `fields`, `confirm`, `audit`, `remediates`, `review-packet`, `screen-mec`, `noc-review`, `study-review`).

## 3. Multi-Agent Roles
1. **Lead Review Coordinator**: Manages onboarding, candidate setup, dispatches sub-tasks, and formats output.
2. **Document Review Agent**: Uses `skills/document-agents/` to verify mandatory e-APR supporting documents.
3. **CRS Auditor Agent**: Uses `skills/crs-auditors/` and `vault audit` to substantiate claimed CRS points.
4. **Remediation Exporter**: Uses `vault remediate` and `vault review-packet` to export private checklists and lawyer review packets.

## 4. Step-by-Step 4-Stage Workflow
- **Stage 1 (Setup)**: `vault init` -> `vault profile` -> `vault ita` -> `vault import` -> `checklist`.
- **Stage 2 (Extraction & Confirmation)**: `vault extract` -> `doctor` -> `vault fields` -> `vault confirm`.
- **Stage 3 (Audit & Screening)**: `vault audit --all` -> `vault screen-mec` -> `vault noc-review` -> `vault study-review`.
- **Stage 4 (Remediation & Export)**: `vault remediate` -> `vault review-packet`.
```

### Example 2: Multi-CLI Pointer Adapters

#### GitHub Copilot (`.github/copilot-instructions.md`)
```markdown
# PR Review Agents — GitHub Copilot Adapter

This repository uses `AGENTS.md` at the repository root as its canonical system prompt, agent specification, and tool orchestration guide.

- **System Specification**: Read and follow `/AGENTS.md` for all agent roles, tool orchestration contracts, 4-stage review workflows, grounding rules, and PII containment.
- **Domain Skills**: Refer to `skills/document-agents/` and `skills/crs-auditors/` for specific domain skills.
- **Execution Contract**: Execute tools via `corpus-crawler --json <subcommand>` shell calls and parse the 5-key stdout envelope.

Do not alter or override instructions in `AGENTS.md`.
```

#### OpenAI Codex (`.codex/AGENTS.md`)
```markdown
# PR Review Agents — OpenAI Codex Adapter

Delegates 100% of instructions to `/AGENTS.md`.

- Read `/AGENTS.md` for canonical system prompts, multi-agent roles, tool contracts, and workflows.
- Refer to `skills/` for CLI-agnostic domain skills.
- Drive tools using `corpus-crawler --json <subcommand>`.
```

#### Cursor IDE (`.cursor/rules/agents.mdc`)
```markdown
---
description: PR Review Agents Canonical Specification Pointer
globs: "*"
alwaysApply: true
---
# PR Review Agents — Cursor Rules Adapter

This repository uses `AGENTS.md` at the repository root as its canonical system specification.

- Read and follow `/AGENTS.md` for all agent instructions, roles, tool contracts, and workflows.
- Use `skills/` for domain-specific agent skill procedures.
- Tool invocations use `corpus-crawler --json <subcommand>` shell commands.
```

#### Windsurf Cascade (`.windsurfrules`)
```markdown
# PR Review Agents — Windsurf Cascade Rules Adapter

Delegates instructions to `/AGENTS.md`.

- Read `/AGENTS.md` for canonical system prompts, multi-agent roles, tool contracts, and workflows.
- Refer to `skills/` for CLI-agnostic domain skills.
- Invoke tools via `corpus-crawler --json <subcommand>`.
```

### Example 3: Synthetic Evaluation Fixture Schema & Benchmark Runner

#### Synthetic Candidate Profile Fixture (`crawler/eval/synthetic_fixtures/candidate_fsw_pass.json`)
```json
{
  "candidate_id": "syn_fsw_01",
  "name": "Synthetic Candidate Jane Doe",
  "program": "FSW",
  "profile": {
    "age": 29,
    "education": "Master's degree",
    "language": {"reading": 8.0, "writing": 7.5, "listening": 8.5, "speaking": 7.5},
    "work_experience_years": 3,
    "has_job_offer": false
  },
  "documents": [
    {"doc_type": "passport", "status": "confirmed", "extracted_values": {"nationality": "Synthetic Land"}},
    {"doc_type": "language_test", "status": "confirmed", "extracted_values": {"test_type": "IELTS", "clb_level": 9}}
  ]
}
```

#### Benchmark Instruction Test (`crawler/tests/test_instruction_eval.py`)
```python
"""Automated benchmark test verifying agent instruction compliance against synthetic fixtures."""

import json
import unittest
from pathlib import Path
from crawler.grounding import check_answer
from crawler.models.public_locator import AnswerObject

_REPO_ROOT = Path(__file__).resolve().parents[2]

class TestInstructionCompliance(unittest.TestCase):
    def test_canonical_agents_md_exists(self):
        """Verify canonical AGENTS.md exists at repo root."""
        agents_md = _REPO_ROOT / "AGENTS.md"
        self.assertTrue(agents_md.is_file())
        content = agents_md.read_text(encoding="utf-8")
        self.assertIn("PR Review Agent", content)
        self.assertIn("corpus-crawler", content)

    def test_thin_adapters_exist_and_delegate(self):
        """Verify all thin pointer adapters exist and reference AGENTS.md."""
        adapters = [
            _REPO_ROOT / "CLAUDE.md",
            _REPO_ROOT / ".github" / "copilot-instructions.md",
            _REPO_ROOT / ".codex" / "AGENTS.md",
            _REPO_ROOT / ".cursor" / "rules" / "agents.mdc",
            _REPO_ROOT / ".windsurfrules",
        ]
        for adapter in adapters:
            self.assertTrue(adapter.is_file(), f"Adapter missing: {adapter}")
            content = adapter.read_text(encoding="utf-8")
            self.assertIn("AGENTS.md", content, f"Adapter {adapter.name} does not reference AGENTS.md")

    def test_synthetic_eval_grounding_compliance(self):
        """Verify synthetic evaluation questions produce valid grounded answer objects."""
        eval_path = _REPO_ROOT / "crawler" / "eval" / "questions.jsonl"
        self.assertTrue(eval_path.is_file())
        with open(eval_path, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                if data.get("expect") == "grounded":
                    ans = AnswerObject(
                        question=data["question"],
                        claims=data["claims"],
                        basis=data["basis"],
                        abstentions=data["abstentions"],
                        prose=data["prose"]
                    )
                    res = check_answer(ans, db_path=_REPO_ROOT / "corpus" / "index.db")
                    self.assertEqual(res["verdict"], "pass", f"Synthetic query failed grounding: {data['id']}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Multi-file duplicate system prompts in `.github/`, `.claude/`, `.cursor/` | Single canonical `AGENTS.md` at root + thin pointer adapters | Phase 47 (v6.0) | Eliminates prompt drift, unifies behavior across 6 CLIs, simplifies maintenance. [VERIFIED: repo decisions] |
| Free-form ungrounded LLM advice for immigration guidance | Fail-closed grounding gate (`corpus-crawler ground`) + mandatory verbatim quotes | Phase 24 (v3.0) | Zero ungrounded assertions; answers must quote authoritative source spans. [VERIFIED: repo history] |
| Storing applicant data in repo files or prompt text | Private candidate vault (`candidates/<id>/`) + structural `basis[]` split | Phase 29 (v4.0) | 100% local PII containment; public output envelopes carry zero applicant values. [VERIFIED: repo history] |

**Deprecated/outdated:**
- Writing detailed system instructions inside `CLAUDE.md` or `.github/copilot-instructions.md`: Deprecated in favor of thin pointers delegating to `AGENTS.md`.

## Assumptions Log

> List of claims tagged `[ASSUMED]` in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Windsurf supports `.windsurfrules` at repository root for workspace instructions. | Multi-CLI Adapter Layer | Low. If Windsurf uses a slightly different file path in future releases, a thin pointer file can easily be added to the expected directory. |

*All other claims in this research were verified against repository source code and official vendor documentation — no user confirmation required.*

## Open Questions (RESOLVED)

1. **How should Cursor handles rule matching for `.cursor/rules/agents.mdc`? (RESOLVED)**
   - *What we know:* Cursor MDC format uses frontmatter parameters `description`, `globs`, and `alwaysApply`.
   - *What's unclear:* Whether `alwaysApply: true` or `globs: "*"` is preferred by all versions of Cursor.
   - *Recommendation:* Set both `alwaysApply: true` and `globs: "*"` in `.cursor/rules/agents.mdc` to guarantee the pointer rule is evaluated regardless of active file context.

2. **How to run automated prompt instruction compliance in CI without LLM API costs? (RESOLVED)**
   - *What we know:* Running live LLM queries in CI requires external API keys and introduces non-determinism.
   - *What's unclear:* How to verify agent instruction compliance statically and deterministically.
   - *Recommendation:* Use a two-tiered test strategy: (1) Static file structure and AST checks verifying adapter pointers and `AGENTS.md` key sections, and (2) Piping pre-generated synthetic answer objects from `crawler/eval/questions.jsonl` through `corpus-crawler ground` to prove quote validity and fail-closed grounding.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Tool execution & pytest | ✓ | 3.10.12 | — |
| Poetry | Package environment | ✓ | 2.0.0 | `.venv/bin/python` |
| `corpus-crawler` CLI | Search, grounding, vault tools | ✓ | 2.0.0 | — |
| `pytest` | Test execution | ✓ | 9.0.3 | `.venv/bin/python -m pytest` |
| `git` | Repository management | ✓ | 2.34.1 | — |

**Missing dependencies with no fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -v` |
| Full suite command | `.venv/bin/python scripts/run_conformance.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGENT-01 | `AGENTS.md` defines system roles, contracts, and workflows | unit / integration | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py::TestInstructionCompliance::test_canonical_agents_md_exists -v` | ❌ Wave 0 |
| AGENT-02 | Grounded citations, PII containment, zero-ungrounded assertion | integration | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py::TestInstructionCompliance::test_synthetic_eval_grounding_compliance -v` | ❌ Wave 0 |
| AGENT-03 | Step-by-step review workflows from setup to remediation | integration | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py::TestInstructionCompliance::test_stage_workflow_contracts -v` | ❌ Wave 0 |
| ADAPT-01 | Thin pointer adapters delegate to `AGENTS.md` | unit / integration | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py::TestInstructionCompliance::test_thin_adapters_exist_and_delegate -v` | ❌ Wave 0 |
| ADAPT-02 | Portable `skills/` interface exposed in Markdown | unit / integration | `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py::TestInstructionCompliance::test_portable_skills_contracts -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_instruction_eval.py -v`
- **Per wave merge:** `.venv/bin/python scripts/run_conformance.py`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `crawler/tests/test_instruction_eval.py` — test module verifying `AGENTS.md`, adapters, and synthetic benchmark fixtures.
- [ ] `crawler/eval/synthetic_fixtures/` — directory containing 100% fake-PII applicant profile and extraction fixtures for evaluation.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local offline CLI tool; no authentication server needed. |
| V3 Session Management | no | Local offline execution; no web session state. |
| V4 Access Control | yes | Candidate vault isolated in local filesystem (`candidates/<id>/`). |
| V5 Input Validation | yes | Standard JSON envelope parsing and Pydantic schema validation. |
| V6 Cryptography / Privacy | yes | Strict PII containment; personal facts kept in local vault / `basis[]`. |

### Known Threat Patterns for AI Agent Runtimes

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PII Exfiltration via Agent Output | Information Disclosure | Structural partition (`claims[]` generic vs `basis[]` personal) + local candidate vault storage. [VERIFIED: repo contracts] |
| Hallucinated / Ungrounded Policy Claims | Spoofing / Tampering | Fail-closed grounding gate (`corpus-crawler ground`) + mandatory verbatim quote matching. [VERIFIED: repo contracts] |
| Adapter Instruction Drift / Disactivation | Denial of Service / Bypass | Automated test suite (`test_instruction_eval.py`) verifying adapter file existence and `AGENTS.md` delegation. [VERIFIED: repo strategy] |

## Sources

### Primary (HIGH confidence)
- `crawler/CONTRACT.md` — Canonical JSON envelope contract and command specifications.
- `skills/document-agents/_contract.md` — Shared answer-object contract and grounding loop for document agents.
- `skills/crs-auditors/_contract.md` — Shared substantiation contract for CRS auditor modules.
- `scripts/run_conformance.py` — Release gate runner enforcing SAFE-01..12 conformance suite.

### Secondary (MEDIUM confidence)
- Cursor MDC Rules Specification (`.cursor/rules/`) — Format for Cursor rules frontmatter.
- GitHub Copilot Workspace Custom Instructions Specification — Format for `.github/copilot-instructions.md`.
- Claude Code Instructions Specification — Format for `CLAUDE.md`.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Uses shipped Python tools, Poetry, and pytest.
- Architecture: HIGH — Leverages frozen `corpus-crawler` JSON contracts and single-source instruction patterns.
- Pitfalls: HIGH — Identifies real failure modes from multi-CLI deployment and prompt engineering.

**Research date:** 2026-07-21  
**Valid until:** 2026-08-20 (30 days)
