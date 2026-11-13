---
phase: 38-redacted-professional-review-packet
plan: 03
subsystem: cli
tags: [crs, review-packet, render-then-scan, dry-run, opt-in, fail-closed, unittest]

requires:
  - phase: 38-redacted-professional-review-packet
    plan: 02
    provides: "run_review_packet writer + _scan_rendered_bytes + CLI verb"
provides:
  - "vault review-packet --dry-run (preview manifest, write nothing) + --include-document (per-document vault-only staging)"
  - "render-then-scan double gate refusing rendered_leak before any write"
affects: [38-04, phase-39-conformance]

tech-stack:
  added: []
  patterns:
    - "Render-then-scan: scan rendered JSON+MD bytes for abs-path/ev_/secret BEFORE any write (zero artifacts on hit)"
    - "Per-document opt-in staged ONLY under output/review-packet/<pkt_id>/documents/ via resolve_within"

key-files:
  created: []
  modified:
    - crawler/review_packet.py
    - crawler/cli.py
    - crawler/tests/test_review_packet_cli.py

key-decisions:
  - "The render-then-scan ordering is proven end-to-end via the free-text citation quote vector (monkeypatch build_remediation to inject an absolute path into a quote), asserting rendered_leak + zero artifacts"
  - "--dry-run builds the manifest and returns a sentinel private_output_path '(dry-run — not written)' that passes the vault-relative validator; writes nothing"
  - "A foreign --include-document id is refused fail-closed (unknown_document); default lists every candidate doc as excluded"

patterns-established:
  - "Belt-and-suspenders redaction: structural allowlist + render-then-scan deny gate; opt-in documents never leave the vault"
---

# Phase 38 Plan 03 — Summary

## What shipped
- `run_review_packet` (from 38-02) already carries `dry_run` + `include_documents` + the render-then-scan
  gate + per-document vault-only staging; this plan wired the `--dry-run` / `--include-document` CLI flags
  and added the dedicated tests.
- `crawler/tests/test_review_packet_cli.py`: `test_dry_run_writes_nothing`,
  `test_render_then_scan_ordering_via_quote`, `test_include_document_stages_vault_only`,
  `test_include_unknown_document_refuses`, `test_documents_excluded_by_default`.

## Requirements satisfied
- **PKT-01**: `--dry-run` previews the redaction manifest and writes nothing.
- **PKT-03**: documents excluded by default; per-document opt-in staged vault-only + recorded in the manifest; foreign id refused.
- **PKT-04 (scan side)**: render-then-scan refuses `rendered_leak` before any write (zero artifacts).

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_review_packet_cli.py -q` → all pass (dry-run/scan/opt-in incl.).

## Deviations
The writer implementing these behaviors landed in 38-02 (to avoid rework); this plan added the CLI flags + tests.
