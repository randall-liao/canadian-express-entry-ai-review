---
phase: 37
slug: grounded-remediation-checklist
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-17
---

# Phase 37 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x running the repository's unittest-style tests |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_remediation.py crawler/tests/test_remediation_cli.py crawler/tests/test_remediation_projection.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` (~10 min) |
| **Publish-safe gate** | `.venv/bin/python scripts/check_publish_safe.py` |
| **No-inlined gate** | `.venv/bin/python -m pytest crawler/tests/test_crs_no_inlined_rules.py -q` |
| **Estimated runtime** | ~20 s targeted; ~10 min full suite |

---

## Sampling Rate

- **After every task commit:** run the requirement-specific command in the map below.
- **After every plan wave:** run
  `.venv/bin/python -m pytest crawler/tests/test_remediation.py crawler/tests/test_remediation_cli.py crawler/tests/test_remediation_projection.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_vault_audit_cli.py -q`.
- **Before verification:** full suite green + publish-safe (0 violations) + v4.0 conformance PASS.
- **Max feedback latency:** ~90 seconds (targeted).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 37-01-01 | 01 | 1 | REM-01/02 | T-37-01 | build_remediation emits exactly one item per GAP/AT-RISK/unpriced card; each item carries factor, verdict/reason, score impact, citation+verbatim quote, deterministic action | unit | `.venv/bin/python -m pytest crawler/tests/test_remediation.py -x` | ✅ | ✅ green |
| 37-01-02 | 01 | 1 | REM-03 | T-37-02 | Same report + registry in -> identical checklist out (pure, no id/timestamp in item content) | unit | `.venv/bin/python -m pytest crawler/tests/test_remediation.py -x -k determinism` | ✅ | ✅ green |
| 37-02-01 | 02 | 2 | REM-04 | T-37-03 | vault remediate writes the full checklist vault-only; stdout is a PII-light summary; every artifact carries the screening notice | integration + CLI | `.venv/bin/python -m pytest crawler/tests/test_remediation_cli.py -x` | ✅ | ✅ green |
| 37-02-02 | 02 | 2 | REM-04 | T-37-03 | No completed audit / unreadable report -> clean invalid_input/exit-2 refusal + reason code, zero artifacts | CLI | `.venv/bin/python -m pytest crawler/tests/test_remediation_cli.py -x -k refus` | ✅ | ✅ green |
| 37-03-01 | 03 | 3 | REM-03 (SAFE-07 fwd-guard) | T-37-02 / T-37-04 | Every remediation citation+quote matches an existing registry row; remediation imports neither searchindex nor grounding; no-inlined gate covers remediation.py | unit + static | `.venv/bin/python -m pytest crawler/tests/test_remediation_projection.py crawler/tests/test_crs_no_inlined_rules.py -x` | ✅ | ✅ green |

---

## Wave 0 Requirements

Created as part of their owning task (test-first where practical):

- [ ] `crawler/tests/test_remediation.py` — projection + determinism (REM-01/02/03).
- [ ] `crawler/tests/test_remediation_cli.py` — vault-only write + PII-light stdout + refusals (REM-04).
- [ ] `crawler/tests/test_remediation_projection.py` — retrieve-what-you-cite + no-second-trust-path (REM-03/SAFE-07).

No framework installation is required.

---

## Manual-Only Verifications

All phase behaviours have automated verification (deterministic backend/CLI surface).

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing test references.
- [x] No watch-mode flags.
- [x] Feedback latency < 90 seconds (targeted).
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-07-17
