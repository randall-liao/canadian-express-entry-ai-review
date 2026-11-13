# Phase 37 — Pattern Map: Grounded Remediation Checklist

**Mapped:** 2026-07-17

## New / changed source

| New or changed | Closest analog | What to mirror |
|---|---|---|
| `crawler/remediation.py` (build/render/run + two-tier models) | `crawler/audit_report.py` + `crawler/models/audit.py` | fail-closed ordering, `_vault_relative`, `resolve_within` write path, `SCREENING_NOTICE`, PII-light down-projection |
| `PrivateRemediationItem/Checklist` + `PublicRemediationSummary` | `PrivateFactorCard`/`PrivateAuditReport` + `PublicAuditEnvelope` | `extra="forbid"`, `citation_id` rejects `ev_`, vault-relative path validator |
| `RemediationCitation{citation_id, quote}` | `crawler/models/crs_rules.py::Citation` | corpus `relpath#ordinal` + verbatim quote shape |
| deterministic `build_remediation(report, registry)` (pure, no id/timestamp) | `searchindex.build_index` deterministic result (timestamp in wrapper) | pure function; id/timestamp only in the `run_remediation` wrapper |
| `_ACTION_TEMPLATES` keyed by reason + finding-kind fallback | `audit_report._render_factor_card_markdown` reason handling | deterministic prose, `{factor}` param, no volatile literal |
| `vault.latest_completed_audit_run` selector | `vault.load_audit_run` / `_latest_ita_round_id` | one small parameter-bound SELECT ORDER BY DESC LIMIT 1 |
| `cli._cmd_vault_remediate` + `remediate` subparser | `cli._cmd_vault_audit` + `_vault_fail`/`_require_readable_index` | clean `invalid_input`/exit-2 refusal, PII-light stdout, human detail → stderr |
| `output/remediation/` in `VAULT_SUBTREES` | `output/crs-audit/` entry in `scripts/check_publish_safe.py` | subtree + artifact-ext registration |
| no-inlined gate over `crawler/remediation.py` | `test_crs_no_inlined_rules.py` surface list | add the module to the scanned surface |

## New tests

| New test | Closest analog | Pattern |
|---|---|---|
| `crawler/tests/test_remediation.py` | `test_audit_report.py` / `test_audit_models.py` | synthetic multi-verdict report → one item per unresolved finding; item fields; determinism |
| `crawler/tests/test_remediation_cli.py` | `test_vault_audit_cli.py` | real `vault remediate` via CLI; vault-only write; PII-light stdout; refusals + no-artifact |
| `crawler/tests/test_remediation_projection.py` | `test_conformance_v40_retrieve_what_you_cite.py` + `test_crs_no_inlined_rules.py` | every item citation+quote matches a registry row; no `searchindex`/`grounding` import; no-inlined gate covers remediation.py |

## Anti-patterns explicitly avoided
- No call to `grounding.check_answer` / `searchindex.*` from remediation (no second trust path).
- No recomputation of points/verdicts; no synthesized volatile requirement.
- No PII / `ev_` / absolute path on the public summary; no committed artifact.
- No new runtime dependency; no new `contract` error type / exit code.
