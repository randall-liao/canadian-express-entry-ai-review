---
phase: 38-redacted-professional-review-packet
plan: 01
subsystem: api
tags: [crs, review-packet, redaction, allowlist, projection, pii-firewall, screening, unittest]

# Dependency graph
requires:
  - phase: 37-grounded-remediation-checklist
    provides: "PrivateRemediationChecklist projection + RemediationCitation + SCREENING_NOTICE + _build_checklist_for_run"
provides:
  - "crawler/review_packet.py — closed-allowlist packet models (PacketFinding/PacketCitation/ReviewPacket/PublicPacketSummary), RedactionManifest, pure build_packet projection, render_packet_markdown"
  - "remediation._build_checklist_for_run shared helper (resolve+load+gate+build) reused by remediate + packet"
affects: [38-02-packet-cli, 38-03-scan-gate, 38-04-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Closed-allowlist structural PII firewall (extra=forbid + citation_id ev_ rejection + no path/raw-value field) mirroring PublicAuditEnvelope"
    - "Pure projection dropping ev_ evidence pointers; documents_excluded/included passed in by the caller (build_packet stays vault-free)"

key-files:
  created:
    - crawler/review_packet.py
    - crawler/tests/test_review_packet.py
  modified:
    - crawler/remediation.py

key-decisions:
  - "score_impact/substantiated_points are admitted CRS numbers (not identifying PII) and live only in the vault packet; the stdout summary carries counts only"
  - "The screening-notice assertion checks an affirmative-claim denylist scoped to the findings body — the SCREENING_NOTICE legitimately contains the negated 'no eligibility ruling or outcome prediction' disclaimer"
  - "remediation._build_checklist_for_run extracted so review_packet reuses the exact resolve->load->fingerprint-gate->build sequence (one trust path); run_remediation behavior unchanged"

patterns-established:
  - "Export layers are closed-allowlist projections that structurally cannot carry raw values / ev_ / absolute paths"
---

# Phase 38 Plan 01 — Summary

## What shipped
- `crawler/remediation.py`: extracted `_build_checklist_for_run` (resolve completed run → `_load_report` →
  registry-fingerprint gate → `build_remediation`); `run_remediation` now delegates to it (behavior unchanged).
- `crawler/review_packet.py`: closed-allowlist packet models + `RedactionManifest` + pure `build_packet`
  projection (drops `ev_`) + `render_packet_markdown` carrying the imported `SCREENING_NOTICE`.
- `crawler/tests/test_review_packet.py`: 9 tests (structural firewall, projection, selection, determinism,
  manifest counts, screening framing without affirmative claims).

## Requirements satisfied (partial — CLI/scan in 38-02/03)
- **PKT-02**: closed-allowlist schema structurally cannot carry raw applicant values, absolute paths, or
  `ev_` ids (verified: injected keys raise ValidationError; no `ev_`/candidate id in `model_dump_json`).
- **PKT-05**: findings + score impact + resolvable citations with the screening notice and no affirmative
  approval/eligibility/outcome-prediction claim in the body.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_review_packet.py crawler/tests/test_remediation.py crawler/tests/test_remediation_cli.py -q` → all pass (14 + 9).
- `no_inlined_volatile_rules([crawler/review_packet.py])` → `[]`; AST import walk → no searchindex/grounding.

## Deviations
None. Incorporated the plan-checker's screening-notice assertion fix and the pinned `build_packet` signature.
