# Phase 32: Auditor Vertical Slice & Private Report Contract - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Applicant can run one complete CRS auditor slice from confirmed evidence plus grounded rules and
receive fail-closed, vault-only evidence-bearing output. Requirements: AUDIT-02, AUDIT-06.

Success criteria (what must be TRUE):
1. A pilot factor slice emits `SUBSTANTIATED`, `GAP`, `AT-RISK`, or `N/A` only after every rule
   claim passes the existing grounding gate.
2. `SUBSTANTIATED` is impossible unless required proof exists, evidence is confirmed/corrected,
   values meet the claimed threshold, and the admissibility/threshold rule is grounded and cited.
3. Pending, low-confidence, stale, missing, or semantically unresolved evidence produces `GAP` or
   `AT-RISK`, never a green verdict.
4. Public JSON/stdout stays PII-light (generic claims, counts, private output path, run ID); full
   evidence-bearing reports are written only under the candidate vault.
5. A grounding failure writes no partial report, while grounded `GAP`/`AT-RISK` findings are valid
   audit results rather than execution errors.

</domain>

<decisions>
## Implementation Decisions

### The agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use ROADMAP phase goal, success criteria, project constraints, and codebase conventions.

### This is the VERTICAL SLICE that proves the whole audit contract before fan-out (Phase 33)
Pick ONE crisp-threshold pilot factor (research recommends language/first-official-language or
education, because they have crisp CLB/credential thresholds and high user value). Build the full
end-to-end loop for that one factor: confirmed evidence (Phase 30) + grounded rule rows (Phase 31)
+ deterministic comparator (Phase 31 `crs_audit`) → grounding gate → verdict → PII-light public
envelope + vault-only private report. Phase 33 then fans this proven contract out to all four
modules.

### Builds on shipped Phases 29–31
- Phase 29 vault: `crawler/vault.py`, `crawler/models/vault.py`, `crawler/paths.py`, `vault` CLI,
  content-addressed files, `ev_` evidence IDs, publish-safe `VAULT_ARTIFACT`.
- Phase 30 extraction/confirmation: `crawler/extraction.py`, `crawler/confirm.py`,
  `is_audit_eligible` (confirmed/corrected + quality-ok + not-stale), five-key staleness, `doctor`.
- Phase 31 CRS registry + deterministic logic: `crawler/crs_rules.py`,
  `crawler/data/crs_rules/*.yaml` (grounded, cited rows), `crawler/crs_audit.py` (CLB/NCLC
  conversion, thresholds, spouse mode, caps, cutoff comparison).
- Frozen v3.x trust path: `search` → `--cite` resolver → `--json ground` grounding gate →
  `crawler/CONTRACT.md` 5-key JSON envelope (SCHEMA_VERSION "1.0").

### Locked constraints (from PROJECT.md / research SUMMARY-v4.0 / PITFALLS-v4.0)
- **Fail-closed grounding-by-construction:** every rule claim in the verdict must pass the existing
  grounding gate (resolve + verbatim quote). ANY ungrounded/unresolvable claim refuses the whole
  output — a grounding failure writes NO partial report. Reuse the shipped gate; no new trust path.
- **`SUBSTANTIATED` only when:** required proof exists AND evidence is confirmed/corrected (Phase 30
  `is_audit_eligible`) AND values meet the claimed threshold (Phase 31 deterministic math) AND the
  admissibility/threshold rule is grounded + cited. Pending/low-confidence/stale/missing/
  semantically-unresolved → `GAP` or `AT-RISK`, NEVER green.
- **PII containment:** public JSON/stdout is PII-light (generic corpus-cited `claims[]`, counts,
  private output path, run ID). Full evidence-bearing reports (with applicant values + `ev_`
  pointers) are written ONLY under the candidate vault. `claims[]` never carry PII; `evidence_id`
  (vault) stays separate from `citation_id` (corpus).
- Grounded `GAP`/`AT-RISK` are valid results (exit 0-style), NOT execution errors; only a true
  grounding/system failure is an error (and writes no report).
- Poetry-managed Python; pydantic models; reuse frozen primitives; additive CLI verb (e.g.
  `vault audit`/`crs-audit`). SQLite FTS5 keyword-only; no vectors/cloud.

</decisions>

<code_context>
## Existing Code Insights

Confirmed during plan-phase research. Reuse the shipped grounding gate + resolver + JSON envelope,
the Phase 30 `is_audit_eligible`/staleness gates, and the Phase 31 `crs_rules`/`crs_audit`
deterministic logic. Reference research: `.planning/research/ARCHITECTURE-v4.0.md` (auditor verdicts
reuse search/`--cite`/grounding gate + JSON envelope; PII-rich detail only under private output;
verdict semantics table SUBSTANTIATED/GAP/AT-RISK/N/A) and `.planning/research/PITFALLS-v4.0.md`
(over-claiming green, PII in `claims[]`, partial report on gate failure → tests).

</code_context>

<specifics>
## Specific Ideas

Refer to ROADMAP Phase 32 description, the five success criteria above, and the v4.0 research
verdict-semantics table. Deliver one pilot factor slice end-to-end with fail-closed verdicts,
vault-only evidence-bearing report, PII-light public envelope, evidence pointers, rule citations,
score delta, and negative tests for pending/low-confidence/stale/gate-failure cases.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
