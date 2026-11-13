# Phase 38 — Pattern Map: Redacted Professional Review Packet

**Mapped:** 2026-07-17

## New / changed source

| New or changed | Closest analog | What to mirror |
|---|---|---|
| `crawler/review_packet.py` (models + build_packet + render-then-scan + run) | `crawler/remediation.py` + `crawler/audit_report.py` | pure projection, two-tier, resolve_within write, SCREENING_NOTICE, fail-closed refusal |
| `PacketFinding` / `ReviewPacket` (closed allowlist) | `crawler/models/audit.py::PublicAuditEnvelope` + `remediation.PublicRemediationSummary` | `extra="forbid"`, reject `ev_`, reject absolute path |
| `PacketCitation{citation_id, quote}` | `remediation.RemediationCitation` | corpus id + verbatim quote; reject `ev_` |
| `RedactionManifest` | `remediation.PrivateRemediationChecklist.counts()` + a new records struct | included/excluded/redacted counts + document opt-in list |
| `remediation._build_checklist_for_run` (extracted shared helper) | `remediation.run_remediation` (its resolve+load+gate+build prefix) | one trust path; both remediate + packet call it |
| `_scan_rendered_bytes` (render-then-scan) | `scripts/check_publish_safe.py::ABS_PATH_PATTERNS`/`SECRET_PATTERNS`/`scan_text` | self-contained deny-pattern scan (scripts is not importable) |
| `cli._cmd_vault_review_packet` + `review-packet` subparser | `cli._cmd_vault_remediate` + `_vault_fail`/`_vault_ok` | PII-light stdout, fail-closed refusal, human detail → stderr |
| `--out-dir` vault containment | `cli._cmd_ground`/`_cmd_checklist` `--out-dir` containment | resolve_within/is_within; refuse non-vault |
| per-document staging | `crawler/extraction.py` render/text vault write via `resolve_within` | copy into vault subtree only; never publish |
| `output/review-packet/` in `VAULT_SUBTREES` | `output/crs-audit/` + `output/remediation/` entries | subtree registration |

## New tests

| New test | Closest analog | Pattern |
|---|---|---|
| `crawler/tests/test_review_packet.py` | `test_remediation.py` | build_packet allowlist projection + manifest + determinism |
| `crawler/tests/test_review_packet_cli.py` | `test_remediation_cli.py` | vault-only write + PII-light stdout + dry-run + refusals + per-doc opt-in (synthetic report, unguarded) |
| `crawler/tests/test_review_packet_conformance.py` | `test_remediation_projection.py` + `test_conformance_v40_privacy_containment.py` | structural firewall + redaction-leak + render-then-scan + retrieve-what-you-cite + no-second-trust-path |

## Anti-patterns explicitly avoided
- No raw applicant value / `ev_` / absolute path representable in the packet schema.
- No document content included by default; no publish/transmit; vault-only staging.
- No re-ground/re-score; no `searchindex`/`grounding` import; no volatile literal.
- No write on a `--dry-run` or a render-then-scan/refusal; no new runtime dependency.
