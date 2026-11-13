---
phase: 43
slug: enhanced-noc-work-duty-review-worksheet
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
---

# Phase 43 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest 9.x |
| Quick command | `.venv/bin/python -m pytest crawler/tests/test_noc_review.py crawler/tests/test_noc_review_cli.py -q` |
| Full suite | `.venv/bin/python -m pytest crawler/tests -q` |
| Gates | `.venv/bin/python scripts/check_publish_safe.py` · `.venv/bin/python scripts/run_conformance.py` |

## Per-Task Verification Map

| Task | Plan | Wave | Reqs | Secure behavior | Command | Exists | Status |
|------|------|------|------|-----------------|---------|--------|--------|
| 43-01-01 | 01 | 1 | NOC-01 | Exact NOC chunks produce stable cited lead/duty/requirements worksheet; no semantic matching | `.venv/bin/python -m pytest crawler/tests/test_noc_review.py -q -k "worksheet or duties or citation"` | ❌ | ⬜ |
| 43-02-01 | 02 | 1 | NOC-02 | Per-duty fields are pending-first, per-duty confirmed, staleness-keyed, vault-only, contamination-free | `.venv/bin/python -m pytest crawler/tests/test_noc_review.py -q -k "confirm or field or stale"` | ❌ | ⬜ |
| 43-03-01 | 03 | 2 | NOC-01/02 | CLI writes worksheet only under vault, emits PII-light envelope, and captures one duty at a time | `.venv/bin/python -m pytest crawler/tests/test_noc_review_cli.py -q` | ❌ | ⬜ |
| 43-04-01 | 04 | 3 | NOC-03 | Sidecar never SUBSTANTIATED; partial/rejected/stale/drifted/unconfirmed remain AT-RISK/GAP; core.work frozen | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_noc_no_auto_green.py -q` | ❌ | ⬜ |

## Wave 0

- [x] `crawler/tests/test_noc_review.py`
- [x] `crawler/tests/test_noc_review_cli.py`
- [x] `crawler/tests/test_conformance_v5_noc_no_auto_green.py`
- [x] deterministic NOC fixture chunks from the committed/pinned corpus

## Sign-Off

- [x] Automated coverage for every task
- [x] No watch mode
- [x] No manual-only behavior required
- [x] `nyquist_compliant: true`

**Approval:** complete 2026-07-19
