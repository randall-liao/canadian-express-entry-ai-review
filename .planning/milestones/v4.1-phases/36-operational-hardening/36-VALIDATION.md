---
phase: 36
slug: operational-hardening
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-17
---

# Phase 36 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x running the repository's unittest-style tests |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_index_health.py crawler/tests/test_vault_audit_cli.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` (~10 min; 752/1-skip baseline) |
| **Publish-safe gate** | `.venv/bin/python scripts/check_publish_safe.py` |
| **v4.0 conformance gate** | `.venv/bin/python scripts/run_conformance.py` |
| **Estimated runtime** | ~20 s targeted; ~10 min full suite |

---

## Sampling Rate

- **After every task commit:** run the requirement-specific command in the map below.
- **After every plan wave:** run
  `.venv/bin/python -m pytest crawler/tests/test_index_health.py crawler/tests/test_audit_index_refusal.py crawler/tests/test_example_profile_pinned.py crawler/tests/test_adversarial_extraction_seam.py crawler/tests/test_vault_audit_cli.py crawler/tests/test_full_audit_real_seam.py -q`.
- **Before verification:** full suite green + publish-safe (0 violations) + v4.0 gate PASS.
- **Max feedback latency:** ~90 seconds (targeted).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 36-01-01 | 01 | 1 | HARD-01 | T-36-01 | `probe_index` classifies missing/empty/unreadable/corrupt/drifted into a closed reason-code vocabulary; read-only, never creates a DB | unit | `.venv/bin/python -m pytest crawler/tests/test_index_health.py -x` | ✅ | ✅ green |
| 36-01-02 | 01 | 1 | HARD-01 / HARD-02 | T-36-01 / T-36-02 | `vault audit` on a bad `--db` refuses with `invalid_input`/exit 2 + `reason=<code>` + recovery hint, writing zero `audit_runs`/report artifacts | integration + CLI | `.venv/bin/python -m pytest crawler/tests/test_audit_index_refusal.py -x` | ✅ | ✅ green |
| 36-02-01 | 02 | 1 | HARD-03 | T-36-03 | Every example `factor_id` ∈ `FULL_GRID_FACTORS`; example produces ≥1 non-`N/A` verdict via the real audit path | unit + integration | `.venv/bin/python -m pytest crawler/tests/test_example_profile_pinned.py -x` | ✅ | ✅ green |
| 36-03-01 | 03 | 1 | HARD-04 | T-36-04 | Rotated / low-text / password-protected / ambiguous-date fixtures stay quarantined through the REAL seam; no cross-factor contamination | integration | `.venv/bin/python -m pytest crawler/tests/test_adversarial_extraction_seam.py -x` | ✅ | ✅ green |
| 36-03-02 | 03 | 1 | HARD-04 | T-36-04 | No regression: full auditor + real-seam suite stays green | integration | `.venv/bin/python -m pytest crawler/tests/test_full_audit_real_seam.py crawler/tests/test_auditors_additional.py -x` | ✅ | ✅ green |

---

## Wave 0 Requirements

The four new test files below are created as part of their owning task (test-first
where practical) and gate that task's commit:

- [ ] `crawler/tests/test_index_health.py` — reason-code unit table (HARD-01).
- [ ] `crawler/tests/test_audit_index_refusal.py` — CLI refusal + no-artifact (HARD-01/02).
- [ ] `crawler/tests/test_example_profile_pinned.py` — grid-pin + non-N/A proof (HARD-03).
- [ ] `crawler/tests/test_adversarial_extraction_seam.py` — real-seam quarantine (HARD-04).

No framework installation is required (all deps already present).

---

## Manual-Only Verifications

All phase behaviours have automated verification. The auditor/extraction surfaces
are deterministic CLI/backend behaviour with no visual/real-time/external-service
component, so no human-only verification is invented.

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing test references.
- [x] No watch-mode flags.
- [x] Feedback latency < 90 seconds (targeted).
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-07-17
