---
phase: 39
slug: safe-conformance-release-consolidation
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-17
---

# Phase 39 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x running the repository's unittest-style tests |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_conformance_v41_coverage.py crawler/tests/test_conformance_v41_privacy.py crawler/tests/test_conformance_v41_grounding.py crawler/tests/test_conformance_v41_release_gate.py -q` |
| **Release gate** | `.venv/bin/python scripts/run_conformance.py` (SAFE-01..08) |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` (~14 min) |
| **Publish-safe gate** | `.venv/bin/python scripts/check_publish_safe.py` |
| **Estimated runtime** | ~40 s targeted; ~14 min full suite |

---

## Sampling Rate

- **After every task commit:** run the requirement-specific command in the map below.
- **After every plan wave:** run `.venv/bin/python scripts/run_conformance.py`.
- **Before verification:** full suite green + publish-safe (0 violations) + release gate PASS (SAFE-01..08).
- **Max feedback latency:** ~90 seconds (targeted).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 39-01-01 | 01 | 1 | SAFE-05 | T-39-01 | Every supported language benchmark priced-or-unresolved; no sibling/adversarial state greens a factor (real seam skip-guarded) | conformance | `.venv/bin/python -m pytest crawler/tests/test_conformance_v41_coverage.py -x` | ✅ | ✅ green |
| 39-02-01 | 02 | 1 | SAFE-06 | T-39-02 | Remediation/packet defaults PII-light; artifacts vault-only; both subtrees unstageable; non-vault writes fail closed | conformance | `.venv/bin/python -m pytest crawler/tests/test_conformance_v41_privacy.py -x` | ✅ | ✅ green |
| 39-03-01 | 03 | 3 | SAFE-07 | T-39-03 | Retrieve-what-you-cite + determinism + static volatile + no-second-trust-path + screening framing over remediation/packet | conformance | `.venv/bin/python -m pytest crawler/tests/test_conformance_v41_grounding.py -x` | ✅ | ✅ green |
| 39-03-02 | 03 | 3 | SAFE-08 | T-39-04 | ONE release-gate command exercises coverage/refusal/remediation/packet/privacy/grounding/screening for the complete v4.1 flow | conformance + CLI | `.venv/bin/python -m pytest crawler/tests/test_conformance_v41_release_gate.py -x && .venv/bin/python scripts/run_conformance.py --collect-only >/dev/null` | ✅ | ✅ green |

---

## Wave 0 Requirements

Created as part of their owning task:

- [ ] `crawler/tests/test_conformance_v41_coverage.py` — SAFE-05.
- [ ] `crawler/tests/test_conformance_v41_privacy.py` — SAFE-06.
- [ ] `crawler/tests/test_conformance_v41_grounding.py` — SAFE-07.
- [ ] `crawler/tests/test_conformance_v41_release_gate.py` — SAFE-08.

No framework installation is required.

---

## Manual-Only Verifications

All phase behaviours have automated verification (a conformance test layer + a CLI gate).

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing test references.
- [x] No watch-mode flags.
- [x] Feedback latency < 90 seconds (targeted).
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-07-17
