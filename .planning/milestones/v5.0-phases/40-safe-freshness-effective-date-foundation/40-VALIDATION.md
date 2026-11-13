---
phase: 40
slug: safe-freshness-effective-date-foundation
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-17
---

# Phase 40 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x running the repository's unittest-style tests |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_crs_audit.py crawler/tests/test_freshness_staleness.py crawler/tests/test_snapshot_health.py crawler/tests/test_snapshot_refusal.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` (~15 min; 888 passed / 1 skipped at sign-off) |
| **Publish-safe gate** | `.venv/bin/python scripts/check_publish_safe.py` |
| **v4.x conformance gate** | `.venv/bin/python scripts/run_conformance.py` |
| **Estimated runtime** | <90 s targeted; ~10 min full suite |

---

## Sampling Rate

- **After every task commit:** run the requirement-specific command in the map below.
- **After every plan wave:** run the quick command plus
  `.venv/bin/python -m pytest crawler/tests/test_crs_rules.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_auditor.py crawler/tests/test_auditor_dispatch.py -q`.
- **Before verification:** full suite green + publish-safe (0 violations) + v4.x conformance PASS.
- **Max feedback latency:** <90 seconds for targeted checks.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 40-01-01 | 01 | 1 | SAFE-09 | T-40-01 | Missing grounded windows, stale snapshots, and out-of-window rows return false; in-window rows pass | unit | `.venv/bin/python -m pytest crawler/tests/test_freshness_staleness.py -x` | ✅ | ✅ green |
| 40-01-02 | 01 | 1 | SAFE-09 | T-40-02 | The freshness bound is loaded from a grounded registry row, changes the registry fingerprint when tampered, and is absent from Python literals | unit + static gate | `.venv/bin/python -m pytest crawler/tests/test_crs_rules.py crawler/tests/test_crs_no_inlined_rules.py -k "fingerprint or no_inlined or freshness" -x` | ✅ | ✅ green |
| 40-02-01 | 02 | 1 | SAFE-09 | T-40-03 | Public `gate_subset` uses the shipped grounding path with behavior identical to `_gate_or_raise`; the frozen auditor grid remains green | regression | `.venv/bin/python -m pytest crawler/tests/test_gate_subset.py crawler/tests/test_auditor.py crawler/tests/test_auditor_dispatch.py -q` | ✅ | ✅ green |
| 40-03-01 | 03 | 2 | SAFE-10 | T-40-04 / T-40-05 | Read-only snapshot probing classifies missing, empty, unreadable, corrupt, drifted, stale, and healthy states into a closed reason vocabulary | unit table | `.venv/bin/python -m pytest crawler/tests/test_snapshot_health.py -q` | ✅ | ✅ green |
| 40-03-02 | 03 | 2 | SAFE-10 | T-40-06 / T-40-07 | Bad snapshot preflight returns `invalid_input`/exit 2 with a PII-free `reason=<code>` and writes zero artifacts; a healthy snapshot permits continuation | integration + CLI | `.venv/bin/python -m pytest crawler/tests/test_snapshot_refusal.py -q` | ✅ | ✅ green |

---

## Wave 0 Requirements

The new test files are created by their owning implementation tasks and gate those
tasks before completion:

- [x] `crawler/tests/test_freshness_staleness.py` — SAFE-09 freshness/effective-window negative controls.
- [x] `crawler/tests/test_gate_subset.py` — SAFE-09 one-trust-path promotion and alias parity.
- [x] `crawler/tests/test_snapshot_health.py` — SAFE-10 snapshot health classification table.
- [x] `crawler/tests/test_snapshot_refusal.py` — SAFE-10 CLI refusal, zero-artifact, privacy, and healthy positive controls.
- [x] Extend `crawler/tests/test_crs_rules.py` — grounded-bound fingerprint coverage.
- [x] No static-gate scan extension needed — helper logic landed in already-scanned `crawler/crs_audit.py`.

No framework or dependency installation is required.

---

## Manual-Only Verifications

All phase behaviors have automated verification. Phase 40 is deterministic,
fixture-driven backend/CLI behavior with no visual, real-time, or external-service
component.

---

## Validation Sign-Off

- [x] Every planned task has an automated command or a Wave 0 dependency.
- [x] Sampling continuity has no three consecutive tasks without automated verification.
- [x] Wave 0 covers every missing test reference.
- [x] Commands contain no watch-mode flags.
- [x] Targeted feedback latency is under 90 seconds.
- [x] `nyquist_compliant: true` is set in frontmatter.

**Approval:** complete 2026-07-18
