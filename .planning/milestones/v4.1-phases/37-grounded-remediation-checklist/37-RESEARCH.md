# Phase 37 — Research: Grounded Remediation Checklist

**Researched:** 2026-07-17
**Consumed by:** 37-01/02/03 plans, 37-VALIDATION.md
**Scope:** deterministic projection of a completed `PrivateAuditReport` into a private,
corpus-cited fix checklist. Zero new runtime dependencies; no second trust path.

## The projection contract (REM-01/02/03)

`vault audit`/`vault audit --all` already write a fully-grounded
`PrivateAuditReport` JSON to `candidates/<id>/output/crs-audit/<run_id>.json` and an
`audit_runs` row whose `report_relpath` points at it. Each `PrivateFactorCard` carries
(verified by probe) `factor_id`, `verdict`, `reason_code`, `substantiated_points`,
`score_delta`, `points_unresolved`, `rule_citation_ids` (corpus `relpath#ordinal`),
and `evidence_ids` (`ev_`). Everything a remediation item needs already exists — so
remediation is a PURE PROJECTION, never a re-computation:

- **Which findings become items (REM-01):** exactly the cards where
  `verdict ∈ {GAP, AT-RISK}` OR (`verdict == "SUBSTANTIATED"` AND `points_unresolved`).
  `SUBSTANTIATED` (priced) and `N/A` cards produce NO item → exactly one item per
  unresolved finding.
- **Item fields (REM-02):** factor id, verdict + reason code (from the card), score
  impact (`score_delta` / `substantiated_points` from the card — never recomputed),
  the existing grounded corpus citation ids (`rule_citation_ids`) + their verbatim
  rule quote, and a deterministic action template keyed by factor + reason.
- **The verbatim rule span:** the citation `quote` lives in the PII-free registry
  (`crawler/data/crs_rules/*.yaml` → `crs_rules.load_registry()` →
  `RuleRow.citations[].{chunk_id, quote}`). It was proven verbatim-grounded when the
  audit ran (`auditor._gate_or_raise` → `crs_rules.validate_registry`). Remediation
  builds a `{chunk_id → quote}` map from the registry rows the factor consumes
  (`auditors.consumed_factor_ids`) and pairs each of the card's `rule_citation_ids`
  with its quote. This is a STATIC LOOKUP — it never touches `searchindex` or
  `grounding` (a grep test enforces "no second trust path").

## Two-tier model (REM-04, mirrors `crawler/models/audit.py`)

- `PrivateRemediationItem` / `PrivateRemediationChecklist` — PII-BEARING, vault-only:
  carry `ev_` evidence pointers, claimed/confirmed score deltas, and the corpus
  citations + quotes. `extra="forbid"`.
- `PublicRemediationSummary` — PII-LIGHT, the `--json` stdout boundary: run id,
  source `audit_run_id`, per-verdict/per-finding-kind counts, total items, and the
  vault-RELATIVE output path. NO `ev_`, NO applicant value, NO absolute path
  (`extra="forbid"` + a `citation_id`/path validator mirroring `PublicAuditEnvelope`).

## Determinism (REM-03)

`build_remediation(report, registry) -> PrivateRemediationChecklist` is a PURE
function: no timestamp, no minted id, no I/O. Same report + registry in → byte-identical
items out (a determinism test asserts two calls are equal). The minted `rem_` id +
`created_at` live only in the `run_remediation` wrapper (the filename/run metadata),
never in the compared item content — exactly the `searchindex.build_index`
"deterministic result, timestamp in the wrapper" discipline.

## Action templates (REM-02) — deterministic, keyed by factor + reason, no volatile literals

A curated `dict` keyed by `reason_code` with a per-finding-kind fallback
(`gap`/`at_risk`/`unpriced`), each a format string parameterized by the factor id.
Reason codes the deciders actually emit (enumerated from `crawler/auditors/`): e.g.
`missing_evidence`, `missing_eca`, `not_audit_eligible`, `below_threshold`,
`below_tier`, `unmet_component`, `expired_test`/`expired_eca`/`expired_nomination`,
`unresolved_*` (age/conversion/noc/nomination_expiry/sibling/timing),
`unaccepted_test_type`, `sibling_minor`, `arranged_employment_*`, `unaudited_factor`,
`at_risk_component`. Templates are GENERIC SCREENING PROSE — "obtain/confirm/re-scan/
re-confirm the evidence for `<factor>`", "needs human/professional review" — never an
eligibility ruling, never a CLB/points/date literal, never an officer-decision
prediction. The static `no_inlined_volatile_rules` gate is extended to cover
`crawler/remediation.py` so a future template that inlines a volatile threshold trips it.

## Prerequisite refusal (REM-04, reuse Phase-36 style)

`vault remediate` fails closed with a clean `invalid_input`/exit-2 refusal + a
specific reason code (writing zero artifacts) when:
- there is no completed `audit_runs` row (`reason=no_completed_audit`, hint: run
  `vault audit --all` first);
- a specified `--audit-run-id` is not found / not `complete` (`reason=audit_run_not_found`);
- the report JSON at `report_relpath` is missing / unreadable / not valid
  `PrivateAuditReport` (`reason=audit_report_unreadable`, hint: re-run `vault audit`).

Note: remediation does NOT take a `--db` and does NOT preflight the corpus index — it
projects the ALREADY-grounded report + static registry, so the corpus index is not on
its path (honoring "no re-grounding"). The Phase-36 dependency it consumes is the
clean-refusal STYLE + the dotted-id example fixture (so the audit it projects is real).

## Publish-safe

`output/remediation/` + `.json`/`.md` are added to `scripts/check_publish_safe.py`
`VAULT_SUBTREES` so a stray tracked remediation artifact is flagged `VAULT_ARTIFACT`,
exactly like `output/crs-audit/`.

## Frozen constraints (carried forward)
- Zero new runtime deps (pure stdlib + pydantic v2 already in the stack).
- No second trust path; no re-ground/re-score/synthesized volatile requirement.
- Vault-only PII; stdout PII-light; screening-not-legal-advice framing on every artifact.
- Fail closed; every refusal writes zero artifacts.
- Tracked tree publish-safe.
