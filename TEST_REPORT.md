# Canadian Express Entry Document Review Test Report

## Release Evidence

- **Phase 74 run:** `sdk-20260727T082623Z-539def5d2bd9`
- **Final revision:** `7a83a0100c2b064defe2a441f3a3db38aec4877f`
- **Final manifest:** `9af44262a2a2cf09411fd14792bf437dfac99e06960ea51eb8247cf9eb292f59`
- **Committed evidence manifest:** `3c59e9b94802556e80de1685f4f3118a8f842548e3ba2f9c9e668e5ecfe3b811`
- **Release evidence hash:** `298de720e1f1857751556d188f4f258bb5c9ffe3f89ffbb832eb806a8ecab54d`
- **SDK/runtime/protocol:** `1.0.8` / `1.0.73` / `3`
- **Workers:** `gemini-3.6-flash`
- **Judges:** `claude-opus-4.8` (`xhigh`, `long_context`)
- **Optimizers:** `gemini-3.6-flash`
- **Release orchestrator:** `gpt-5.6-sol` (`xhigh`, `long_context`)

## Coverage

| Measure | Result |
|---|---:|
| Phase 72 research documents | 23 |
| Phase 73 logical cases | 118 |
| Phase 73 PDFs | 236 |
| Final Workers | 236 |
| Final Judges | 23 |
| Optimizers | 23 |
| Shared evaluations | 23 |
| Peak concurrency | 5 |
| Imported model artifacts | 0 |
| Cleanup survivors / errors | 0 / 0 |
| Accepted / rejected patches | 11 / 23 |

## Per-Document Results

The shared baseline and final rerun are independent post-patch evaluations of the same frozen source. Their delta measures repeatability variance, not patch acceptance.

| Document | Status | Cases | Workers | Judge | Shared baseline | Final rerun | Rerun delta | Patches A/R | Blockers |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| adoption_certificate | completed | 10 | 10 | 1 | 0.7830 | 0.7768 | -0.0062 | 0/1 | None |
| authority_to_release_info | completed | 10 | 10 | 1 | 0.8400 | 0.8360 | -0.0040 | 0/1 | None |
| birth_certificate | completed | 10 | 10 | 1 | 0.8180 | 0.8400 | +0.0220 | 0/1 | None |
| certificate_of_qualification | completed | 10 | 10 | 1 | 0.8200 | 0.8400 | +0.0200 | 0/1 | None |
| certified_translation | completed | 10 | 10 | 1 | 0.8126 | 0.7630 | -0.0496 | 0/1 | None |
| death_certificate | completed | 10 | 10 | 1 | 0.7020 | 0.7260 | +0.0240 | 0/1 | None |
| digital_photo | completed | 10 | 10 | 1 | 0.8400 | 0.8360 | -0.0040 | 1/1 | None |
| divorce_certificate | completed | 10 | 10 | 1 | 0.8400 | 0.8400 | +0.0000 | 0/1 | None |
| educational_credential_assessment | completed | 10 | 10 | 1 | 0.8200 | 0.8280 | +0.0080 | 0/1 | None |
| employment_reference_letter | completed | 12 | 12 | 1 | 0.7967 | 0.8008 | +0.0042 | 1/1 | None |
| language_test | completed | 10 | 10 | 1 | 0.8400 | 0.8400 | +0.0000 | 0/1 | None |
| letter_of_explanation | completed | 10 | 10 | 1 | 0.7320 | 0.8160 | +0.0840 | 3/1 | None |
| marriage_certificate | completed | 10 | 10 | 1 | 0.7920 | 0.7910 | -0.0010 | 1/1 | None |
| medical_examination | completed | 10 | 10 | 1 | 0.7400 | 0.7370 | -0.0030 | 2/1 | None |
| passport | completed | 12 | 12 | 1 | 0.8308 | 0.8283 | -0.0025 | 0/1 | None |
| police_certificate | completed | 12 | 12 | 1 | 0.8333 | 0.8158 | -0.0175 | 0/1 | None |
| proof_of_funds | completed | 10 | 10 | 1 | 0.8400 | 0.8400 | +0.0000 | 0/1 | None |
| proof_of_other_name | completed | 10 | 10 | 1 | 0.7220 | 0.7480 | +0.0260 | 2/1 | None |
| proof_of_studies | completed | 10 | 10 | 1 | 0.7480 | 0.7800 | +0.0320 | 1/1 | None |
| relative_in_canada | completed | 10 | 10 | 1 | 0.8310 | 0.8330 | +0.0020 | 0/1 | None |
| statutory_declaration_common_law | completed | 10 | 10 | 1 | 0.8240 | 0.8050 | -0.0190 | 0/1 | None |
| use_of_representative | completed | 10 | 10 | 1 | 0.8000 | 0.8240 | +0.0240 | 0/1 | None |
| written_job_offer_lmia | completed | 10 | 10 | 1 | 0.8400 | 0.8050 | -0.0350 | 0/1 | None |

## Accepted Self-Improvement Patches

These are the measured acceptance deltas used by the self-improvement gate.

| Sequence | Document | Commit | Target | Training delta | Holdout delta |
|---:|---|---|---|---:|---:|
| 1 | digital_photo | `b2dfc21cd33557911363bb61ded323b3d1c7a4fb` | `skills/document-agents/digital-photos.md` | +0.0100 | +0.0100 |
| 2 | letter_of_explanation | `9b5b8b55583a1f6ed97af492100d564fa3a29ac8` | `skills/document-agents/letter-of-explanation.md` | +0.1333 | +0.1100 |
| 3 | marriage_certificate | `2c4000ecd1e666e71b1999e9d37f1a1cfb7fdf2d` | `skills/document-agents/marriage-certificate.md` | +0.0233 | +0.0225 |
| 4 | medical_examination | `90d6aab27bfd44dacef5f659f77804f604be82f3` | `skills/document-agents/medical.md` | +0.0600 | +0.0575 |
| 5 | proof_of_other_name | `64e2e0a49bf3d1214bcf2f2c237f2d8adb284c8e` | `skills/document-agents/other-name.md` | +0.0750 | +0.0675 |
| 6 | proof_of_studies | `1fe4e35421e751803356e99e2da1ef61ac3d025b` | `skills/document-agents/proof-of-studies.md` | +0.0067 | +0.0000 |
| 7 | medical_examination | `7975782565b94dba78f94dc3d5ca3ba38b8acd09` | `skills/document-agents/medical.md` | +0.0233 | +0.0075 |
| 8 | employment_reference_letter | `06071757e8f64fe86b15df3000ae2790b64006bc` | `skills/document-agents/employment-reference-letter.md` | +0.0100 | +0.0100 |
| 9 | letter_of_explanation | `bbe1e46fd9a6339d33761557cea2e2589d0affa9` | `skills/document-agents/letter-of-explanation.md` | +0.0517 | +0.0975 |
| 10 | letter_of_explanation | `a2c6497df92c19bcf86237cccc81bb0207486828` | `skills/document-agents/letter-of-explanation.md` | +0.0017 | +0.0775 |
| 11 | proof_of_other_name | `b00e9cf65225aee44b2dcc8eece7de8540755367` | `skills/document-agents/other-name.md` | +0.0917 | +0.0400 |

## Validation Results

| Gate | Status | Duration | Detail | Command |
|---|---|---:|---|---|
| phase74-full-suite | passed | 1217.30s | 742 passed, 200371 subtests passed | `.venv/bin/python -m pytest crawler/tests/test_copilot_sdk_runtime.py crawler/tests/test_phase74_*.py -q` |
| phase74-live-gate | passed | 9.68s | 83 passed | `REQUIRE_LIVE_PHASE74_CONFORMANCE=1 .venv/bin/python -m pytest crawler/tests/test_live_phase74_conformance_gate.py -q` |
| phase74-tamper-suite | passed | 108.38s | 140 passed | `.venv/bin/python -m pytest crawler/tests/test_phase74_committed_evidence.py -q` |
| phase75-targeted | passed | 1.12s | 29 passed | `.venv/bin/python -m pytest crawler/tests/test_phase75_release.py crawler/tests/test_root_agent_workflow.py -q` |
| publish-safety | passed | 7.04s | 1584 tracked files scanned, 0 violations | `.venv/bin/python scripts/check_publish_safe.py` |
| doctor-preflight | passed | 0.63s | ok true, overall ok, all required extraction dependencies present | `.venv/bin/corpus-crawler --json doctor` |
| duplicate-audit | passed | 679.79s | 1 passed; pytest duration 611.77 seconds | `timeout --signal=TERM --kill-after=30s 1200s .venv/bin/python -m pytest crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts -q` |
| repository-suite | passed | 2333.98s | 2409 passed, 8 skipped, 1 deselected, 203795 subtests passed | `timeout --signal=TERM --kill-after=30s 2400s .venv/bin/python -m pytest crawler/tests -q --deselect crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts` |

## Release Blockers

- None in measured evidence.

## GPT-5.6 Sol Assessment

**Verdict:** `ready`  (interpretive; measured tables above are authoritative)

The evidence identifies no release blockers and supports release readiness.

### Strengths

- All listed validation results passed.
- All document reviews completed.
- Cleanup reported no errors or survivors.
- Publish-safety and tamper checks passed.

### Assessment Blockers

- None stated.

### Recommendations

- Proceed with release.
- Monitor document types showing negative final metric deltas.
