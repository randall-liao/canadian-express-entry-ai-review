---
phase: 38
slug: redacted-professional-review-packet
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-17
---

# Phase 38 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x running the repository's unittest-style tests |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_review_packet.py crawler/tests/test_review_packet_cli.py crawler/tests/test_review_packet_conformance.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` (~11 min) |
| **Publish-safe gate** | `.venv/bin/python scripts/check_publish_safe.py` |
| **No-inlined gate** | `.venv/bin/python -m pytest crawler/tests/test_crs_no_inlined_rules.py -q` |
| **Estimated runtime** | ~25 s targeted; ~11 min full suite |

---

## Sampling Rate

- **After every task commit:** run the requirement-specific command in the map below.
- **After every plan wave:** run
  `.venv/bin/python -m pytest crawler/tests/test_review_packet.py crawler/tests/test_review_packet_cli.py crawler/tests/test_review_packet_conformance.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_remediation_cli.py -q`.
- **Before verification:** full suite green + publish-safe (0 violations) + v4.0 conformance PASS.
- **Max feedback latency:** ~90 seconds (targeted).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 38-01-01 | 01 | 1 | PKT-02/05 | T-38-01 | PacketFinding/ReviewPacket structurally reject raw value / ev_ / absolute path; build_packet projects only allowlisted fields + screening framing | unit | `.venv/bin/python -m pytest crawler/tests/test_review_packet.py -x` | ✅ | ✅ green |
| 38-02-01 | 02 | 2 | PKT-04 | T-38-02 | vault review-packet writes only under output/review-packet via resolve_within (writes are unconditionally vault-anchored; a crafted escaping component raises PathEscapeError); a missing prerequisite refuses invalid_input/exit 2 | integration + CLI | `.venv/bin/python -m pytest crawler/tests/test_review_packet_cli.py -x -k "write or refus"` | ✅ | ✅ green |
| 38-03-01 | 03 | 3 | PKT-01/04 | T-38-03 | --dry-run previews the manifest and writes NOTHING; render-then-scan refuses fail-closed on a rendered leak (zero artifacts) | integration | `.venv/bin/python -m pytest crawler/tests/test_review_packet_cli.py -x -k "dry or scan"` | ✅ | ✅ green |
| 38-03-02 | 03 | 3 | PKT-03 | T-38-04 | documents excluded by default; a per-document opt-in stages content vault-only + records it in the manifest; a foreign doc id refuses | integration | `.venv/bin/python -m pytest crawler/tests/test_review_packet_cli.py -x -k document` | ✅ | ✅ green |
| 38-04-01 | 04 | 4 | PKT-02/03 | T-38-01 / T-38-05 | structural-firewall + redaction-leak + retrieve-what-you-cite + no-second-trust-path + no-inlined coverage | unit + static | `.venv/bin/python -m pytest crawler/tests/test_review_packet_conformance.py crawler/tests/test_crs_no_inlined_rules.py -x` | ✅ | ✅ green |

---

## Wave 0 Requirements

Created as part of their owning task (test-first where practical):

- [ ] `crawler/tests/test_review_packet.py` — allowlist projection + manifest (PKT-02/05).
- [ ] `crawler/tests/test_review_packet_cli.py` — write + dry-run + refusals + per-doc opt-in (PKT-01/03/04).
- [ ] `crawler/tests/test_review_packet_conformance.py` — firewall + leak + rwyc + no-trust-path (PKT-02/03).

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
