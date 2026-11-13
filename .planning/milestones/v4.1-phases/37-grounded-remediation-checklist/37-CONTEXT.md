# Phase 37: Grounded Remediation Checklist - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via `workflow.skip_discuss`)

<domain>
## Phase Boundary

Turn a **completed** CRS audit run into a private, corpus-cited **fix checklist** —
exactly one actionable item per unresolved finding (`GAP`, `AT-RISK`, or an
unpriced/unresolved `SUBSTANTIATED`) — as a **pure deterministic projection** of the
already-grounded `PrivateAuditReport`. No re-scoring, no re-grounding, no synthesized
volatile requirements, no second advice/trust path.

Three seams:

1. **Two-tier remediation model + `crawler/remediation.py` (REM-01/02/03).** A pure
   `build_remediation(report, registry)` that walks the stored `PrivateAuditReport`
   factor cards and emits one PII-bearing `PrivateRemediationItem` per unresolved
   finding, each carrying: factor id, verdict + reason code, score impact
   (score_delta / substantiated points from the report), the existing grounded
   corpus citation ids + their verbatim rule quote (read from the PII-free registry,
   NOT re-grounded), the `ev_` evidence pointers (vault-only), and a deterministic
   action template keyed by factor + reason. Plus a PII-light `PublicRemediationSummary`
   down-projection (counts + run id + vault-relative path only).

2. **`vault remediate` verb + `output/remediation/` subtree (REM-04).** A CLI verb
   that loads a selected completed audit run (default: the latest completed run),
   reads its stored report JSON, builds the checklist, writes the full PII-bearing
   JSON + Markdown ONLY under `candidates/<id>/output/remediation/<rem_id>.{json,md}`
   (every path re-anchored via `paths.resolve_within`), emits the PII-light summary
   on stdout, and refuses cleanly (fail-closed, zero artifacts) when there is no
   completed audit run or the report is missing/unreadable. Register the new subtree
   in the publish-safe allow-list.

3. **Projection / determinism / volatile-rule conformance (REM-03).** Static +
   behavioral proofs that remediation is a faithful projection: exactly one item per
   unresolved finding; every requirement-bearing line derives from an existing
   grounded rule (its citation id + quote match a real registry row) rather than
   synthesized advice; the no-inlined-volatile-rules gate covers
   `crawler/remediation.py`; same report in → identical checklist out; and
   remediation never imports/calls the grounding gate or `searchindex` (no second
   trust path).

Do NOT re-run the grounding gate, re-score, synthesize volatile requirements
(CLB/points/cap/window/date literals), predict officer decisions, or add a runtime
dependency.

</domain>

<decisions>
## Implementation Decisions

### Locked Decisions

- Remediation is a PURE PROJECTION of the stored `PrivateAuditReport` (loaded from
  the `audit_runs.report_relpath` JSON) + the static PII-free registry quotes; it
  NEVER calls `grounding.check_answer` / `searchindex` (a grep test enforces this).
- One remediation item per unresolved finding: `verdict ∈ {GAP, AT-RISK}` OR
  (`verdict == SUBSTANTIATED` AND `points_unresolved`). `SUBSTANTIATED` (priced) and
  `N/A` factors produce NO item.
- Score impact is read from the report card (`score_delta` / `substantiated_points`),
  never recomputed; no volatile literal is inlined (the no-inlined gate covers the
  module).
- The verbatim rule span is the registry citation `quote` (already grounded at audit
  time), looked up by the card's `rule_citation_ids` — not re-fetched from the corpus.
- Action templates are a deterministic, curated map keyed by reason code (with a
  per-finding-kind fallback), parameterized by the factor id; generic screening
  prose only — no eligibility ruling, no volatile number, no officer-decision
  prediction.
- Full checklist + `ev_` pointers stay vault-only (`output/remediation/`); stdout is
  a PII-light `PublicRemediationSummary`; every rendered artifact carries the
  `SCREENING_NOTICE`.
- Prerequisite refusal reuses the Phase-36 clean-refusal STYLE (`_vault_fail`,
  `invalid_input`/exit 2 + a specific reason code) and writes zero artifacts.

### Agent Discretion

All remaining implementation choices are at the agent's discretion. Prefer the
existing audit model / report-writer / vault-path / render patterns. Add no runtime
dependency.

</decisions>

<code_context>
## Existing Code Insights

- The stored `PrivateAuditReport` JSON (`candidates/<id>/output/crs-audit/<run_id>.json`)
  carries per-card `factor_id`, `verdict`, `reason_code`, `substantiated_points`,
  `score_delta`, `points_unresolved`, `rule_citation_ids`, `evidence_ids` — exactly
  the projection inputs (verified by probe).
- `crawler/audit_report.py` is the writer to mirror (fail-closed ordering,
  `_vault_relative`, `resolve_within` write path, `SCREENING_NOTICE`, PII-light
  down-projection via `to_public_envelope`).
- `crawler/models/audit.py` is the two-tier model pattern (private PII-bearing +
  public PII-light, `extra="forbid"`, `citation_id` rejects `ev_`).
- `crawler/crs_rules.py::load_registry` + `crawler/models/crs_rules.py::Citation`
  give the `{chunk_id → quote}` map for the verbatim rule span (already grounded).
- `crawler/auditors/__init__.py::consumed_factor_ids` scopes which registry rows a
  factor consumes (to collect its citations/quotes).
- `crawler/vault.py::load_audit_run` returns the run row (incl. `report_relpath`);
  a `latest_completed_audit_run` selector must be added.
- `crawler/cli.py::_vault_fail` / `_require_readable_index` (Phase 36) are the clean
  refusal precedents.
- `scripts/check_publish_safe.py::VAULT_SUBTREES` must gain `output/remediation/`.
- `crawler/crs_rules.py::no_inlined_volatile_rules` + `test_crs_no_inlined_rules.py`
  is the static gate to extend to `crawler/remediation.py`.

</code_context>

<specifics>
## Specific Ideas

- Determinism is a property of the pure `build_remediation`; the minted `rem_id` +
  timestamp live only in the run wrapper, not in the compared item content.
- Exactly-one-item-per-finding is asserted against a synthetic multi-verdict report.

</specifics>

<deferred>
## Deferred Ideas

Recipient-specific export presets (LATER-06), encrypted bundles (LATER-07), and any
free-form generated legal advice remain out of scope. The redacted professional-review
packet is Phase 38 (built on this remediation layer).

</deferred>
