# Technical Highlights Portfolio Case Study Design

**Date:** 2026-07-27
**Status:** Approved
**Output:** `TECHNICAL_HIGHLIGHTS.md`

## Goal

Create a root-level portfolio case study that presents this project as evidence of
software-engineering capability. The document must work for both recruiters and
technical interviewers: it should communicate impact quickly, then provide enough
architecture, reliability, security, and evaluation detail to support deeper review.

The case study uses first-person voice to make ownership explicit. Every quantitative
claim must be traceable to committed repository evidence, primarily `TEST_REPORT.md`,
`AGENTS.md`, the Phase 74 and Phase 75 evidence, and representative implementation
and test files.

## Selected Approach

Use a portfolio case-study structure rather than a resume-style one-pager or a
low-level engineering dossier.

- Lead with the problem, impact, and measured scale.
- Explain the architecture and data flow with GitHub-rendered Mermaid diagrams.
- Highlight the hardest engineering decisions and their trade-offs.
- Describe safety, failure handling, validation, and release discipline.
- Close with the engineering competencies demonstrated and links to source evidence.

This structure lets non-technical readers understand the project without removing
the details senior engineers need to evaluate the implementation.

## Document Structure

1. **Title and project pitch** — a concise statement of the user problem and solution.
2. **Project snapshot** — a compact table of measured scale and release results.
3. **Engineering challenge** — high-stakes grounding, privacy, real-agent execution,
   blind evaluation, concurrency, and fail-closed behavior.
4. **Production architecture** — a Mermaid flowchart from root natural-language intent
   through private ingestion, grounded review, CRS auditing, screening, remediation,
   and redacted export.
5. **Blind self-improvement pipeline** — a Mermaid flowchart showing isolated Gemini
   research and generation, blind Workers, privileged Opus Judges, measured patch
   gates, and the GPT release assessment.
6. **Technical highlights** — focused subsections on SDK orchestration, process
   isolation, evidence integrity, deterministic contracts, and multi-CLI portability.
7. **Reliability and security** — bounded retries and correction, exact process
   ownership, cleanup guarantees, local PII containment, no-tools model sessions,
   publish-safety, and tamper-resistant evidence.
8. **Measured outcomes** — evidence-backed results and accepted improvement deltas,
   with stochastic rerun variance explicitly distinguished from patch improvement.
9. **What I demonstrated** — a concise mapping from implementation work to software
   engineering competencies.
10. **Technical references** — direct links to representative source, tests, system
    contracts, and the measured release report.

## Mermaid Visualizations

Use standard fenced `mermaid` blocks supported by GitHub Markdown.

### Operational Architecture

The first diagram will show these boundaries:

`User intent -> Lead Coordinator -> Local candidate vault -> Extraction confirmation
-> Document/CRS agents -> Corpus grounding gate -> Policy screening -> Private
remediation/redacted packet`

The diagram must make the public and private data boundary visually explicit.

### Blind Evaluation and Self-Improvement

The second diagram will show:

`Per-document research -> Synthetic vector/scanned cases -> Blind Worker -> Privileged
Judge -> Optimizer candidate -> Training/holdout safety gate -> Accepted patch ->
Fresh final evaluation -> GPT release assessment`

It must show that Workers cannot access research, failure labels, revealing filenames,
ground truth, or Judge findings, while the privileged Judge can access the evidence
required to evaluate them.

## Evidence and Accuracy Rules

- Use only measurements present in tracked release evidence.
- Link major figures to `TEST_REPORT.md`.
- Do not present shared-baseline versus final-rerun variance as self-improvement.
- Present the 11 accepted patches as measured, non-regressing improvements.
- Avoid claims of legal correctness or guaranteed immigration outcomes.
- Do not include applicant PII, private paths, credentials, raw prompts, or unpublished
  run artifacts.
- Describe the system as substantiation screening and guidance, not legal advice.

## Error Handling and Safety Coverage

The case study will explain the engineering response to failure without reproducing
internal sensitive data:

- typed transport, lifecycle, schema, grounding, PII, and blindness failures;
- one bounded same-session structural correction rather than unbounded retry loops;
- exact PID, process-start-time, command-digest, and lease ownership;
- targeted cleanup with no name-based process termination;
- candidate rejection for semantic non-improvement and release blocking for
  infrastructure uncertainty;
- atomic, hash-bound evidence persistence and allowlisted patch application.

## Validation

Before completion:

- confirm all referenced files exist;
- check every numeric claim against `TEST_REPORT.md` or committed evidence;
- verify both Mermaid blocks use valid GitHub-compatible syntax;
- run the repository's documentation/publish-safety checks that cover the new file;
- inspect the final diff to ensure no unrelated or untracked files are included.

