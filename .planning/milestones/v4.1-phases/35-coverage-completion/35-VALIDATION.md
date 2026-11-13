---
phase: 35
slug: coverage-completion
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-17
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 running the repository's unittest-style tests |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_crs_no_inlined_rules.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` |
| **Estimated runtime** | ~15 seconds targeted; ~90 seconds full suite |

---

## Sampling Rate

- **After every task commit:** Run the requirement-specific command in the map below.
- **After every plan wave:** Run `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_crs_conversion_coverage.py crawler/tests/test_testtype_vocab.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_full_audit_real_seam.py -q`.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 90 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 35-01-01 | 01 | 1 | COV-01 | T-35-01 | Every conversion-emitted benchmark is grounded and priced | unit + grounding | `.venv/bin/python -m pytest crawler/tests/test_language_points_coverage.py crawler/tests/test_crs_rules_conformance.py -x` | ✅ | ✅ green |
| 35-01-02 | 01 | 1 | COV-01 | T-35-01 | Real-seam language card has non-null grounded points | integration | `.venv/bin/python -m pytest crawler/tests/test_full_audit_real_seam.py -x` | ✅ | ✅ green |
| 35-02-01 | 02 | 1 | COV-02 | T-35-02 | Substantiated-but-unpriced cards are explicitly unresolved | unit | `.venv/bin/python -m pytest crawler/tests/test_unpriced_surfacing.py -x` | ✅ | ✅ green |
| 35-03-01 | 03 | 1 | COV-03 | T-35-03 | Sibling producer/consumer field vocabularies cannot drift | unit | `.venv/bin/python -m pytest crawler/tests/test_siblingfields_vocab.py -x` | ✅ | ✅ green |
| 35-03-02 | 03 | 1 | COV-03 | T-35-03 / T-35-05 | Sibling extraction is pending-first and field-confirmed | unit + CLI | `.venv/bin/python -m pytest crawler/tests/test_extraction.py crawler/tests/test_extract_confirm_cli.py -x` | ✅ | ✅ green |
| 35-04-01 | 04 | 2 | COV-04 | T-35-01 / T-35-03 | Only a complete eligible ADULT sibling chain substantiates; a confirmed minor stays AT-RISK `sibling_minor` (day-before/on-birthday boundaries); threshold `18` grounded (no inlined literal) + retrieve-what-you-cite agrees | unit + grounding | `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_conformance_v40_retrieve_what_you_cite.py crawler/tests/test_crs_registry_transfer_additional.py -x` | ✅ | ✅ green |
| 35-04-02 | 04 | 2 | COV-04 | T-35-03 / T-35-04 / T-35-05 | Real sibling seam: an adult sibling → SUBSTANTIATED, a MINOR sibling → AT-RISK `sibling_minor`, no cross-factor contamination or public PII | integration | `.venv/bin/python -m pytest crawler/tests/test_full_audit_real_seam.py crawler/tests/test_conformance_v40_no_false_green.py -x` | ✅ | ✅ green |

---

## Wave 0 Requirements

- [x] `crawler/tests/test_language_points_coverage.py` — level-set anti-drift and grounding coverage for COV-01.
- [x] `crawler/tests/test_unpriced_surfacing.py` — unresolved/unpriced surfacing contract for COV-02.
- [x] `crawler/tests/test_siblingfields_vocab.py` — shared sibling vocabulary anti-drift pin for COV-03.
- [x] `crawler/tests/fixtures/extraction/make_fixtures.py` — born-digital sibling-proof fixture.

No framework installation is required.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency < 90 seconds.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-07-17
