# Phase 25: Grounding Gate + Eval Harness - Context

**Gathered:** 2026-06-21
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

A fail-closed grounding-by-construction gate turns structured agent answers into trustworthy
cited output, and the same gate run over a tracked PII-free question set IS the automated eval
harness. This is the contract every later producer (checklist, agents) emits into.

Requirements: GND-01, GND-02. Depends on Phase 24 (the `--cite` citation resolver).

Success criteria (from ROADMAP):
1. Answers are one structured JSON object — `{question, claims:[{id, text, citations[], quote}],
   basis[], abstentions[], prose}` — and the gate (`corpus-crawler --json ground`, reading stdin)
   checks **only** `claims[]`; `prose`/`basis`/`abstentions` are never citation-checked.
2. Grounding-by-construction, fail-closed: every claim must carry ≥1 citation that resolves to a
   real chunk (GND-01) AND whose verbatim `quote` is a whitespace/case-normalized substring of that
   chunk; ANY uncited, unresolvable, or quote-mismatch claim → `verdict:"fail"`, render nothing,
   exit non-zero.
3. A passing answer renders only to git-ignored `personal/output/` and is re-scanned with
   `check_publish_safe.scan_text` (RPT-03 render-then-gate) before write — a PII/secret/abs-path hit
   refuses output with `ok:false` and exit 4.
4. The same gate over a tracked PII-free `questions.jsonl` reference set (incl. adversarial
   `must_abstain`) emits `eval_runner`-style `{total, passed, failed, failures}` and exits non-zero
   if any answer is ungrounded — gate doubles as eval harness; uncited-claim count /
   citation-resolution rate / quote-substring rate / abstention-correctness are hard 0%/100% gates.
5. The gate's honesty boundary is explicit + documented: it guarantees resolvability +
   verbatim-quote, NOT semantic entailment/faithfulness (deferred with VAL-01/02); quote and claim
   render side-by-side for human review.

</domain>

<decisions>
## Implementation Decisions

### Agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use the ROADMAP phase goal, success criteria, codebase conventions, and the existing
`crawler/` primitives to guide decisions.

Locked anchors from PROJECT/STATE decisions to honor:
- Reuse existing `crawler/` primitives, NO new deps: `searchindex.resolve()` (Phase 24,
  fail-closed sha-drift guard) is the single citation resolver the gate (GND-01) calls;
  `contract.envelope`/exit codes; `check_publish_safe.scan_text` (RPT-03) + `CORPORA_PREFIXES`
  (already includes `personal/`); `eval_runner` `{total,passed,failed,failures}` shape.
- Acceptance bar (locked, v3.0): grounding-by-construction, fail-closed. The gate guarantees
  resolvability + verbatim-quote, NOT semantic entailment (deferred VAL-01/02 — needs model/NLI,
  violates no-vectors/no-cloud constraint).
- SQLite FTS5 (stdlib) only; PII confined to git-ignored `personal/`, never the repo or corpus DB.
- The gate is the contract Phases 26 (checklist) and 27 (document agents) emit into — design its
  stdin JSON schema + JSON-envelope output to be the stable producer-facing API.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research (gsd-phase-researcher +
gsd-pattern-mapper). Key existing modules to build on: `crawler/searchindex.py`
(`search`/`resolve`/`EmptyQuery`, read-only), `crawler/contract.py` + `crawler/CONTRACT.md`
(frozen JSON-envelope, schema_version 1.0, exit-code taxonomy), `crawler/eval_runner.py`,
`scripts/check_publish_safe.py` (`scan_text`, RPT-03), `crawler/cli.py` (`_cmd_*` dispatch).

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond the ROADMAP success criteria — discuss phase skipped. The
`ground` verb reads a structured answer JSON on stdin, checks only `claims[]`, calls
`searchindex.resolve()` per citation, verifies the verbatim quote is a normalized substring of
the resolved chunk, fails closed on any miss, and (on pass) render-then-scans output to
`personal/output/`. The eval mode runs the same gate over `questions.jsonl`.

</specifics>

<deferred>
## Deferred Ideas

- Semantic entailment / NLI faithfulness checking (VAL-01/VAL-02) — needs a model; out of scope
  for v3.0 per the locked acceptance bar.

</deferred>
