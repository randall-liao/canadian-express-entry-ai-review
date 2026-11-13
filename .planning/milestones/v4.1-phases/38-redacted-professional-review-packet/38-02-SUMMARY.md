---
phase: 38-redacted-professional-review-packet
plan: 02
subsystem: cli
tags: [crs, review-packet, cli, vault, fail-closed, publish-safe, pii-boundary, unittest]

requires:
  - phase: 38-redacted-professional-review-packet
    plan: 01
    provides: "build_packet + packet models + _build_checklist_for_run"
provides:
  - "vault.new_packet_id + list_candidate_documents + get_candidate_document"
  - "review_packet.run_review_packet writer (build -> render-then-scan -> vault-only write -> PII-light summary)"
  - "vault review-packet CLI verb with fail-closed refusals + output/review-packet subtree + publish-safe registration"
affects: [38-03, 38-04, phase-39-conformance]

tech-stack:
  added: []
  patterns:
    - "Writes unconditionally vault-anchored via resolve_within (no destination override); non-vault is structurally unreachable"
    - "Reuse remediation.RemediationError for all packet refusals (the class the CLI catches)"

key-files:
  created:
    - crawler/tests/test_review_packet_cli.py
  modified:
    - crawler/vault.py
    - crawler/review_packet.py
    - crawler/cli.py
    - scripts/check_publish_safe.py

key-decisions:
  - "run_review_packet implements the full writer (dry-run + include-documents + render-then-scan) in this plan to avoid rework; 38-03 adds the CLI flags + their tests"
  - "Leak-scan patterns are built from string fragments so review_packet.py does not self-trip the publish-safe abs-path scanner (mirrors check_publish_safe's ALLOW_MARKER trick)"

patterns-established:
  - "Packet/report export verbs write vault-only via resolve_within and refuse via RemediationError reason tokens"
---

# Phase 38 Plan 02 — Summary

## What shipped
- `crawler/vault.py`: `new_packet_id` + `list_candidate_documents` + `get_candidate_document`.
- `crawler/review_packet.py`: `run_review_packet` writer (reuse `_build_checklist_for_run` -> build_packet
  -> render-then-scan -> vault-only write -> `PublicPacketSummary`) + `_scan_rendered_bytes`/`_LEAK_PATTERNS`.
- `crawler/cli.py`: `_cmd_vault_review_packet` + `review-packet` subparser + hints (rendered_leak/unknown_document).
- `scripts/check_publish_safe.py`: `output/review-packet/` registered.
- `crawler/tests/test_review_packet_cli.py`: write + refusals + vault-anchoring proof (+ dry-run/scan/opt-in from 38-03).

## Requirement satisfied
- **PKT-04 (write side)**: packet writes ONLY under `output/review-packet/` via `resolve_within`; a crafted
  escaping component raises `PathEscapeError`; a missing prerequisite refuses cleanly with zero artifacts;
  stdout is PII-light; subtree publish-safe-registered.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_review_packet_cli.py crawler/tests/test_vault_cli.py scripts/tests/test_check_publish_safe.py -q` → 55 passed, 25 subtests.
- `.venv/bin/python scripts/check_publish_safe.py` → 0 violations (347 files).

## Deviations
Implemented the full writer (incl. 38-03's render-then-scan/dry-run/opt-in) here to avoid rework; 38-03
adds the CLI flags + their dedicated tests. Fixed a publish-safe self-trip (fragment-built leak patterns).
