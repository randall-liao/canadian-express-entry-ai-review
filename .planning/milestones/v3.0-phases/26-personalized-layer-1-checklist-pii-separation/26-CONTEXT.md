# Phase 26: Personalized Layer-1 Checklist + PII Separation - Context

**Gathered:** 2026-06-21
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Generate a personalized, fully-cited Layer-1 "which documents you need" checklist for a post-ITA
Express Entry applicant from a LOCAL profile, with all PII kept strictly out of the repo and the
corpus DB.

Requirements: CHK-01, CHK-02. Depends on Phase 25 (every checklist requirement line passes through
the `ground` gate).

Success criteria (from ROADMAP):
1. Running the checklist generator against `$PR_PERSONAL_DIR/profile.yaml` (default `./personal/`)
   produces a Layer-1 document checklist where every requirement line is a gated, cited `claims[]`
   entry that passes the Phase-25 gate. [CHK-01]
2. Separation of concerns: profile-derived **applicability** (which items apply — e.g. countries
   lived in since 18) lives in `basis[]` / local files and is NEVER citation-checked, while the
   **requirement text + citation** comes from the corpus and is gated. [CHK-01, CHK-02]
3. The rendered checklist is written only under git-ignored `personal/output/`, and the
   publish-safety scanner's `CORPORA_PREFIXES` guard (already includes `personal/`) fails closed if
   any profile/output file is ever `git add`-ed; `personal.example/` (synthetic schema) stays
   tracked. [CHK-02]
4. No PII (countries, dates, names) ever appears in `claims[].text`, the corpus DB, or any tracked
   file — confirmed by the RPT-03 publish-safe scan over the rendered checklist bytes. [CHK-02]

</domain>

<decisions>
## Implementation Decisions

### Agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use the ROADMAP goal, success criteria, codebase conventions, and existing `crawler/`
primitives to guide decisions.

Locked anchors to honor:
- The checklist is a PRODUCER that emits the Phase-25 structured answer object
  `{question, claims:[{id,text,citations[],quote}], basis[], abstentions[], prose}` and passes it
  THROUGH the Phase-25 gate (`grounding.check_answer` / the `ground` verb). Requirement text +
  citation come from the corpus (via `searchindex.search`/`resolve`) and are gated; profile-derived
  applicability goes in `basis[]` and is NEVER citation-checked.
- HARD PII boundary: profile (`$PR_PERSONAL_DIR/profile.yaml`, default `./personal/`) and rendered
  output (`personal/output/`) are git-ignored. The synthetic `personal.example/` is the ONLY tracked
  profile artifact. `.gitignore` already has `personal/` ignored + `!personal.example/` un-ignored.
- `claims[].text` (the gated requirement statements) must contain NO PII — PII (countries, dates,
  names) lives only in `basis[]` / local files, never in gated claim text or the corpus DB.
- Reuse: `grounding` (Phase 25 gate + render-then-scan), `searchindex.search`/`resolve` (Phase 24),
  `check_publish_safe.scan_text`/`CORPORA_PREFIXES` (RPT-03), `contract.envelope`/exit codes,
  `cli.py` `_cmd_*` dispatch. stdlib + PyYAML only (PyYAML already a dependency); NO new deps.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research (gsd-phase-researcher +
gsd-pattern-mapper). Facts established by the orchestrator:
- `personal.example/` does NOT yet exist — Phase 26 CREATES the synthetic `personal.example/profile.yaml`
  schema (tracked). `.gitignore` already has `personal/` (ignored) and `!personal.example/` (tracked).
- No `$PR_PERSONAL_DIR` / `profile.yaml` resolution exists yet — Phase 26 adds it (env var, default `./personal/`).
- Phase-25 gate symbols available: `crawler/grounding.py` (`check_answer`, `render_answer`, `run_eval`,
  `_norm`, `quote_is_grounded`, `InvalidAnswer`) + the `ground` CLI verb (render-then-scan to personal/output/).
- Phase-24 retrieval: `crawler/searchindex.py` (`search`, `resolve`, `EmptyQuery`).

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond the ROADMAP success criteria — discuss phase skipped. Likely shape: a
new generator module (e.g. `crawler/checklist.py`) + a `checklist` CLI verb that reads
`$PR_PERSONAL_DIR/profile.yaml`, derives applicability into `basis[]`, retrieves+cites Layer-1
document requirements from the corpus into gated `claims[]`, assembles the Phase-25 answer object,
runs it through the gate, and renders the cited checklist to `personal/output/`. A synthetic
`personal.example/profile.yaml` drives the test/demo end-to-end with zero real data.

</specifics>

<deferred>
## Deferred Ideas

- Layer-2 rule matching (recency/amounts/format/translation verification per document) — VAL-01;
  Phase 26 is Layer-1 completeness ("which documents you need") only.

</deferred>
