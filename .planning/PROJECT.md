# PR Review Agents — Canadian PR Application Guide

## What This Is

A CLI-agnostic, multi-agent system that guides a Canadian permanent-residence applicant through the post-Invitation-to-Apply (ITA) process, starting with personalized document checklist & guidance. Every claim the system makes is grounded in and cited from authoritative sources (IRCC guidance on canada.ca, the IRPA Act and IRPR regulations, and IRCC Program Delivery Instructions). It is built so the agent harness can be shared publicly on GitHub while the user's personal data (PII) stays strictly separate and local. Built first for the author (a Chinese citizen with an Express Entry ITA), then shared for other applicants.

## Current State

**Shipped: v12.0 (2026-07-27)** - Per-document research, blind synthetic generation, official-SDK self-improvement, root-agent onboarding, and measured release report.

## Latest Milestone: v12.0 Per-Document Autonomous Research, Synthetic Generation & Blind Self-Improvement Pipeline (Shipped)

**Goal:** Ship a ready-to-use Canadian Express Entry document review system: finish the isolated per-document research, blind synthetic generation, blind report review, privileged Judge evaluation, and measured self-improvement pipeline; then prove that a user can start a GitHub Copilot agent at the repository root, say "I want to review X," and receive grounded, PII-safe document review, remediation, and report guidance.

**Target features:**
- One Gemini 3.6 Flash long-context GitHub Copilot research and synthetic-generation agent per document type.
- Structurally blind worker staging with no research, ground truth, revealing paths, or filenames.
- A privileged GitHub Copilot Judge using Claude Opus 4.8, `xhigh` reasoning, and `long_context`.
- A GPT 5.6 SOL XHIGH GSD orchestrator that runs measured self-improvement and exports root `TEST_REPORT.md`.
- Goal-backward audit agents that block release unless the root-agent "review X" workflow works end to end and the final document-agent improvements are measured and non-regressing.

## Core Value

Every answer about which documents are required and whether the user has them right is **grounded in and cited from an authoritative source** — the system never guesses on immigration requirements.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ CRS auditor hardening + grounded remediation checklist + explicitly-redacted lawyer/RCIC review packet, consolidated behind a single SAFE-01..08 release gate — v4.1
- ✓ Deterministic, corpus-grounded MEC/POLICY/STUDY/NOC screening with pinned volatile-data snapshots and a complete SAFE-01..12 release gate — v5.0 (Phases 40–46)
- ✓ Local, PII-safe CRS claim substantiation against confirmed document evidence, with full-grid fail-closed verdicts and corpus-grounded rules — v4.0
- ✓ Grounded answer layer, personalized checklist, and 22 portable document agents over the authoritative corpus — v3.0–v3.1

### Active

<!-- Current scope. Building toward these. -->

- **Per-Document Research**: Phase 72 complete with 23 live, isolated Gemini research agents and 46 grounded artifacts.
- **Blind Synthetic Generation**: Phase 73 turns research into opaque vector/scanned cases using real GitHub Copilot agents.
- **Blind Review & Privileged Judge**: Phase 74 enforces worker blindness and runs the Opus 4.8 xhigh long-context Judge.
- **Autonomous Orchestration & Report**: Phase 75 runs measured self-improvement and exports root `TEST_REPORT.md`.
- **Ready-to-Use Root Agent**: Phase 75 must prove that a root GitHub Copilot agent routes natural-language review intent through the local vault, grounded document skills, audit, remediation, and redacted report workflow.

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Actual document content inspection (reading the user's uploaded PDFs/scans to verify contents) — **in scope as of v4.0** (Validation Layer 2/3): the CRS substantiation auditor extracts values from real documents to check them against grounded rules; the extracted inputs carry a confirm-what-I-read checkpoint since extraction is the one non-grounded step
- Vector/embedding semantic index — deferred; corpus is small enough (estimated single-digit to low-tens of MB) that markdown + metadata + a keyword index is sufficient to start; revisit only if recall proves insufficient
- Programs other than post-ITA Express Entry PR (PNP, family sponsorship, study/work permits) — out of initial scope; structure should not preclude later generalization
- Pre-ITA eligibility/CRS scoring and profile optimization — the system begins after an ITA is received
- Submitting forms to IRCC or any automated interaction with IRCC accounts — the system guides; the user acts
- Legal advice — the system surfaces and cites official sources; it is not a substitute for a licensed immigration consultant/lawyer
- Legacy arranged-employment resolution, DLI/PGWP study-points evidence, NOC-duty review, and MEC sidecar checks — **in scope as of v5.0** (Grounded Eligibility & Policy Edge-Case Screening): each is delivered as a deterministic, corpus-grounded, fail-closed screen with semantic judgments left human-confirmed / `AT-RISK`; none introduces a model/NLI/vector/cloud path or legal advice

## Context

- **Author's situation:** Chinese citizen who has received an Invitation to Apply for Canadian PR (Express Entry). Building the tool to navigate their own e-APR document gathering first.
- **Sharing intent:** The harness will be published on a public GitHub repo. PII leaking into the repo is the single biggest risk to avoid — architecture must separate personal data from the agent harness from day one.
- **Harness model:** The intended design is CLI-agnostic agent definitions (prompt/skill files) plus shared Python tools (crawler, indexer, validators) that any agent CLI can invoke — analogous to portable skills that work across Antigravity, Codex, Claude, and Copilot.
- **Build sequencing:** The crawler/corpus must exist before the check agents — the corpus is the "ground" the document agents reason against.
- **Domain note:** Document requirements vary by program and personal situation; initial focus is the author's Express Entry case, kept structured enough to generalize later.

## Constraints

- **Tech stack**: Shared tools (crawler, corpus indexer, validators) in Python — best crawling/parsing/text ecosystem (httpx, BeautifulSoup, pdfminer) and easy for others to run.
- **Dependency management**: Use Poetry (`pyproject.toml` + `poetry.lock`, `poetry run`) for all Python dependencies — user directive (overrides the research-suggested `uv`).
- **Security/Privacy**: No PII may ever enter the public repo — personal data and documents stay in a local, git-ignored area, structurally separated from the shareable harness.
- **Compatibility**: Harness must be CLI-agnostic — works across Antigravity, OpenAI Codex, Claude, and GitHub Copilot without proprietary CLI dependencies.
- **Grounding**: All requirement claims must be backed by a citation to the curated authoritative corpus (IRCC / IRPA / IRPR / PDIs) — no ungrounded assertions.
- **Source authority**: Corpus is limited to authoritative sources (IRCC canada.ca, Justice Laws IRPA/IRPR, IRCC PDIs); third-party/blog content is not authoritative.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Build the crawler/corpus first, check agents second | The corpus is the grounding all document agents depend on | — Pending |
| Curated local corpus (RAG) over live retrieval | Stable, citable, reproducible grounding the user controls | — Pending |
| Sources: IRCC canada.ca + IRPA/IRPR + IRCC PDIs | Authoritative coverage of requirements, law, and operational guidance | — Pending |
| Markdown + metadata + lightweight keyword index; no vector index yet | Corpus is small; keeps system dependency-light and CLI-agnostic | — Pending |
| Per-document check agents (one per important document type) | Encapsulates each document's distinct rules; composable and clear | ✓ Realized — 22 grounded agents cover the full Express Entry e-APR document set (v3.0 + v3.1) |
| Layered validation: checklist → rule-matching → (later) document inspection | Deliver value incrementally; defer the hardest layer | — Pending |
| PII separated from harness via local git-ignored personal-data area | Enables public sharing with zero PII leakage | — Pending |
| CLI-agnostic agent harness + shared Python tools | Usable from Antigravity, Codex, Claude, Copilot | — Pending |
| Python for shared tooling | Strongest crawling/parsing/text ecosystem; easy for others to run | — Pending |
| Poetry for Python dependency management | User directive; reproducible `pyproject.toml` + `poetry.lock`, overrides research-suggested `uv` | ✓ Good — shipped v2.0 as `corpus-crawler` package |
| [v4.0] CRS substantiation = presence + value + admissibility per factor, grounded & fail-closed | Officer substantiates claimed CRS against documents at e-APR; a mismatch removes points → refusal risk. Only admissibility/threshold verdicts are grounded — extraction is a separate confirm-first step | — Pending |
| [v4.0] All PII in a local git-ignored candidate vault (profile + documents + extracted values) | Extends the established PII-separation constraint to the new document/extraction surface; never the repo or corpus DB | — Pending |
| [v4.0] Modular auditor split along IRCC's CRS factor grid | Keeps each agent context-light; reuses the proven v3.1 per-document-agent pattern and frozen search→gate→contract primitives | — Pending |
| [v4.1] Close shipped fail-closed gaps before adding new policy domains | Higher-CLB, sibling evidence, clean refusals, and fixture drift directly affect completeness and operator trust; legacy policy/domain expansions can remain deferred | ✓ Shipped v4.1 |
| [v4.1] Remediation and professional-review exports derive only from existing grounded verdicts | Keeps action guidance auditable and prevents a second ungrounded advice path | ✓ Shipped v4.1 |
| [v4.1] GSD planning and execution proceed autonomously without clarification questions | The operator has delegated routine scope and implementation decisions; written artifacts must preserve enough rationale for later review | ✓ Shipped v4.1 |
| [v5.0] Eligibility/policy edge-case screens are deterministic, corpus-grounded, and fail-closed; semantic judgments stay human-confirmed / `AT-RISK` | Extends the auditor into program eligibility (MEC) and the policy edge cases v4.x left AT-RISK without adding a model/NLI/vector/cloud trust path or presenting legal advice | ✓ Shipped v5.0 |
| [v5.0] DLI/PGWP and other volatile external facts are grounded in refreshable authoritative *local snapshots*, never an ungrounded live remote lookup during audit | Keeps grounding reproducible, offline, PII-safe, and citable; a live lookup would break the frozen local-corpus trust path and could green a result from unpinned data | ✓ Shipped v5.0 |
| [v5.0] Cross-cutting policy effective-date / freshness / drift handling so stale or superseded rules can never green a result | Program eligibility and arranged-employment rules change on effective dates; a stale/superseded rule silently substantiating a factor is the milestone's dominant risk | ✓ Verified across every v5.0 screen by SAFE-09..12 |
| [v5.0] Prefer zero new dependencies; any addition requires strong justification and a supply-chain gate | The shipped stack (crawler/corpus/index/grounding/vault/auditor/remediation/packet) already covers these screens; new deps threaten the dependency-light, PII-safe, CLI-agnostic constraints | ✓ Shipped v5.0 with zero new runtime dependencies |
| [v12.0] Full repository PII & privacy audit (1,074 files) | Executed parallel Gemini 3.6 Flash long-context review across all tracked repo files; 0 PII found | ✓ Confirmed 100% clean & safe to push to public repo (2026-07-23) |
| [v12.0] Every claimed AI role must be a real GitHub Copilot CLI/SDK agent | Prevents hardcoded, deterministic, or ground-truth-derived substitutes from being reported as model work | ✓ Verified across researchers, generators, Workers, Judges, optimizers, and release orchestrator |
| [v12.0] Final Judge uses Claude Opus 4.8 with xhigh reasoning and long context | Keeps ground-truth evaluation privileged and maximizes cross-document reasoning quality | ✓ Verified across 23 batched Judges |
| [v12.0] Final product goal is release-blocking and independently audited | Completion means a user can start a root Copilot agent, request review of X, and receive grounded, PII-safe Canadian Express Entry review guidance after measured self-improvement; artifact completion alone is insufficient | ✓ Verified by goal, integration, code, security, eval, docs, and milestone audits |
| [v6.0] Canonical AGENTS.md + thin per-CLI adapters as universal harness | Single source of truth for agent behavior and tool usage; per-CLI configs simply redirect to AGENTS.md | — Active |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-27 after v12.0 milestone*
