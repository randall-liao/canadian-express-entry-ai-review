# Agent Crawler and Self-Improvement Portfolio Design

**Date:** 2026-07-27
**Status:** Approved
**Output:** Revised `TECHNICAL_HIGHLIGHTS.md`

## Goal

Revise the existing portfolio case study so its primary technical highlight is the
measured self-improving agent loop, with the agent-enabled web crawler presented as
the evidence foundation that makes grounded improvement possible.

The document must remain useful to both recruiters and technical interviewers. It
should explain the product impact quickly, then demonstrate how deterministic Python
systems and real GitHub Copilot agents cooperate under strict privacy, grounding,
evaluation, and release controls.

## Selected Approach

Use a two-pillar rewrite within the current two-diagram budget:

1. **Self-Improving Agent Loop** — the hero architecture and primary engineering story.
2. **Agent-Enabled Web Crawler** — the source-agnostic corpus acquisition, quality,
   completeness, and reporting foundation.

The existing end-user review workflow remains in concise prose. A third diagram is
not added because it would make the case study longer and weaken the emphasis on the
two differentiating engineering systems.

## Narrative Structure

The revised case study will use this order:

1. Project pitch centered on a self-improving, evidence-grounded agent system.
2. Project snapshot with measured release scale.
3. Engineering challenge and safety constraints.
4. Self-Improving Agent Loop.
5. Agent-Enabled Web Crawler.
6. How the production review product consumes the corpus and improved skills.
7. Engineering highlights.
8. Reliability and security.
9. Measured outcomes.
10. Engineering competencies demonstrated.
11. Technical references.

## Self-Improving Agent Loop

The first Mermaid flowchart will show:

`authoritative corpus + per-document failure research -> synthetic vector/scanned
documents -> blind Worker -> privileged Judge -> sealed training findings ->
sandboxed optimizer -> allowlist and train/holdout non-regression gate -> atomic
patch -> fresh final evaluation -> cryptographically bound release report`

The section will make these boundaries explicit:

- Workers cannot access research, failure labels, revealing filenames, internal case
  identifiers, sibling mappings, ground truth, or Judge findings.
- Judges may access the privileged evidence required for complete evaluation.
- Optimizers receive training findings only; holdout findings and scores are sealed.
- Optimizer writes stay inside proposal sandboxes until deterministic validation passes.
- Python validates and orchestrates model work but never fabricates semantic results.

The measured result will be presented as **11 accepted / 23 rejected** proposals.
Acceptance requires:

- a positive training overall-score delta;
- no regression in training grounding, citation exactness, PII containment, or
  blind-input compliance;
- no regression in any sealed holdout dimension.

Shared-baseline and final-rerun scores are independent post-patch evaluations of the
same source. Their deltas move in both directions and are monitoring evidence, not
self-improvement credit.

## Agent-Enabled Web Crawler

The second Mermaid flowchart will show:

`site profile + seed URL -> crawl4ai BFS/headless browser -> deterministic scope,
chrome-removal, and dedup classifier -> partitioned QC agents -> verbatim/eval
enforcement -> drop quarantine -> independent full-fidelity re-fetch ->
completeness agent -> citable local corpus + build report`

The crawler is described as agent-enabled rather than fully agentic:

- deterministic code controls browser crawling, domain boundaries, URL filters,
  lossless `<main>` capture, classification, deduplication, manifests, JSON contracts,
  verdict application, and final status;
- parallel QC agents perform semantic scope review, but may only delete complete
  lines or sections and must write per-document eval contracts;
- a byte-preservation gate detects rewritten retained text;
- deterministic eval enforcement rejects invalid `must_contain`, `must_not_contain`,
  relevance, or verdict contracts;
- dropped pages are quarantined with an audit log rather than silently deleted;
- an independent full-fidelity re-fetch samples the live source so a completeness
  agent can detect silent truncation;
- the final report distinguishes `pass`, `fail`, and `incomplete`.

The crawler remains source-agnostic through YAML site profiles and exposes a portable
five-key JSON envelope so any supported agent CLI can drive it through ordinary shell
commands.

## Product Integration

The case study will explain in prose that the root review workflow consumes:

- the locally built authoritative corpus for exact citation and verbatim grounding;
- per-document skills improved by the measured agent loop;
- private candidate vault inputs that never enter public claims or release evidence.

The product remains a substantiation-screening and guidance system, not legal advice
and not a guarantee of an immigration outcome.

## Error Handling and Safety

### Crawler

- Missing optional crawl dependencies produce a typed `missing_dependency` JSON error.
- Crawl scope remains bounded by the active profile, allowed domains, and include glob.
- Agent QC cannot rewrite retained authoritative text.
- Missing or invalid eval contracts stop the pipeline.
- Failed completeness checks prevent a passing report.

### Self-Improvement

- Model execution failures never produce hardcoded fallback research, reports, scores,
  or patches.
- Holdout contamination fails closed.
- Candidate targets and content must pass path, PII, privileged-data, safety, and diff
  allowlists.
- Source-hash compare-and-swap and atomic writes prevent stale or concurrent patches.
- Semantic non-improvement rejects a proposal; infrastructure uncertainty blocks the
  pipeline and release.
- Process ownership, bounded correction, deadlines, and exact cleanup remain visible
  as supporting reliability work.

## Test and Evidence Contract

Update `crawler/tests/test_technical_highlights.py` to:

- use anchored regular expressions for the required heading hierarchy;
- normalize whitespace before testing evidence phrases;
- require the new `Self-Improving Agent Loop` and `Agent-Enabled Web Crawler` sections;
- require exactly two Mermaid flowcharts;
- require crawler terms including `crawl4ai`, delete-only QC, full-fidelity re-fetch,
  deterministic eval enforcement, and `pass`, `fail`, `incomplete`;
- require loop terms including sealed holdouts, sandboxed optimizer proposals,
  `11 accepted / 23 rejected`, non-regression, and atomic patches;
- retain checks for measured release facts, outcome disclaimer, and resolving local
  links.

All quantitative claims must remain traceable to `TEST_REPORT.md` or committed v12.0
evidence. No runtime source, dependency, README, or unrelated file will be modified.

## Technical References

The revised case study will link directly to:

- `crawler/deepcrawl.py`
- `crawler/QC_RUNBOOK.md`
- `crawler/eval_runner.py`
- `crawler/apply_verdicts.py`
- `crawler/completeness.py`
- `crawler/AGENT_SKILL.md`
- `crawler/eval/genuine_optimizer.py`
- `crawler/eval/holdout_splitter.py`
- `crawler/eval/patch_evaluator.py`
- `crawler/eval/sdk_pipeline_orchestrator.py`
- `crawler/eval/copilot_sdk_runtime.py`
- `TEST_REPORT.md`

## Validation

Before completion:

1. Run the focused technical-highlights pytest contract.
2. Run the tracked-file publish-safety scanner.
3. Run `git diff --check` on the two modified files.
4. Verify all local Markdown links resolve.
5. Inspect the final diff for factual accuracy and unintended scope.

