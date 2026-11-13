---
phase: 42
slug: legacy-physician-arranged-employment-policy-resolver
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
---

# Phase 42 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x / unittest-style tests |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_physician_policy.py crawler/tests/test_conformance_v5_policy_no_job_offer_green.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` (1029 passed / 2 skipped / 1 known pre-existing real-corpus dedup test deselected at sign-off) |
| **Publish-safe gate** | `.venv/bin/python scripts/check_publish_safe.py` |
| **Conformance gate** | `.venv/bin/python scripts/run_conformance.py` |

## Sampling Rate

- After each task: run its focused command.
- After each wave: run the quick command plus registry/no-inline tests.
- Before verification: full suite, publish-safe, and conformance green.
- Max targeted feedback latency: 120 seconds.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-------------------|-------------|--------|
| 42-01-01 | 01 | 1 | POLICY-01 / POLICY-02 | T-42-01 / T-42-02 | Effective-dated physician row loads, grounds, and stays distinct from legacy/repeal rows; coverage remains complete | `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_retrieve_what_you_cite.py crawler/tests/test_crs_no_inlined_rules.py -q` | ✅ | ✅ green |
| 42-02-01 | 02 | 1 | POLICY-02 | T-42-01 / T-42-03 | Confirmed exact physician NOC reaches a distinct AT-RISK/manual branch; stale/missing/non-physician signals fall through; never awards points | `.venv/bin/python -m pytest crawler/tests/test_physician_policy.py crawler/tests/test_auditors_additional.py -q` | ✅ | ✅ green |
| 42-02-02 | 02 | 1 | POLICY-02 | T-42-03 / T-42-05 | Real extraction/vault routing can supply the physician NOC only as confirmed evidence; unconfirmed/malformed values fail closed | `.venv/bin/python -m pytest crawler/tests/test_physician_policy.py -q -k "extract or vault or signal"` | ✅ | ✅ green |
| 42-03-01 | 03 | 2 | POLICY-03 | T-42-01 / T-42-04 | Offer-for-eligibility sidecar is inert, unregistered, PII-light, and always reports CRS points 0 with AT-RISK/N/A only | `.venv/bin/python -m pytest crawler/tests/test_physician_policy.py -q -k sidecar` | ✅ | ✅ green |
| 42-04-01 | 04 | 3 | POLICY-01 / POLICY-02 / POLICY-03 | T-42-01..T-42-06 | No job-offer path can be SUBSTANTIATED/non-zero; frozen guard unchanged; full registry and release gates pass | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_policy_no_job_offer_green.py -q` | ✅ | ✅ green |

## Wave 0 Requirements

- [x] `crawler/tests/test_physician_policy.py`
- [x] `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py`
- [x] Extend registry grounding/coverage tests and regenerate `crawler/data/crs_rules/COVERAGE.md`
- [x] Update Phase-41 frozen-path expectations only for intentional Phase-42 data files

No framework installation is required.

## Manual-Only Verifications

All phase behavior is deterministic and automated. No manual verification is required.

## Validation Sign-Off

- [x] Every task has automated verification or a Wave 0 dependency.
- [x] Sampling continuity is preserved.
- [x] No watch-mode commands.
- [x] `nyquist_compliant: true`.

**Approval:** complete 2026-07-19
