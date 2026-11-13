---
phase: 45
slug: mec-program-eligibility-sidecar-fsw-fst-cec
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-20
revised: 2026-07-19T23:06:05-04:00
---

# Phase 45 — Validation Strategy

| Property | Value |
|---|---|
| Framework | pytest |
| Quick | `.venv/bin/python -m pytest crawler/tests/test_mec_rules.py crawler/tests/test_mec_screen.py -q` |
| CLI/publish | `.venv/bin/python -m pytest crawler/tests/test_mec_cli.py -q` |
| Conformance | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_mec_no_false_meets.py crawler/tests/test_crs_no_inlined_rules.py -q` |
| Full | `.venv/bin/python -m pytest crawler/tests -q` |
| Publish safety | `.venv/bin/python scripts/check_publish_safe.py` |

## Exact Task Map

| Task | Plan | Wave | Reqs | Files under test | Behavior | Automated command | Exists |
|---|---:|---:|---|---|---|---|---|
| 45-01-01 | 01 | 1 | MEC-02/03/04 | `models/vault.py`, `models/crs_rules.py`, `crs_rules.py`, `snapshot_policy.py`, `test_mec_rules.py` | Add `program_eligibility` to FactorGroup before MEC YAML parsing; typed manifest; no-default max-age resolver; every selected row gets non-None effectivity/freshness checks | `.venv/bin/python -m pytest crawler/tests/test_mec_rules.py -q -k "factor_group or payload or manifest or effect or freshness or max_age"` | ❌ |
| 45-01-02 | 01 | 1 | MEC-02/03/04 | `mec.yaml`, `COVERAGE.md`, `crs_rules.py`, `test_mec_rules.py`, `test_crs_no_inlined_rules.py` | Exact cited rows; no funds amount; AST/token-aware scanner categories and controls | `.venv/bin/python -m pytest crawler/tests/test_mec_rules.py crawler/tests/test_crs_no_inlined_rules.py -q` | ❌ / existing scanner test |
| 45-02-01 | 02 | 2 | MEC-01/02/03/04 | `models/mec.py`, `mec_screen.py`, `test_mec_screen.py` | Exact statuses; deterministic FAIL precedence; unknown/missing AT-RISK; manifest-only N/A; closed projection | `.venv/bin/python -m pytest crawler/tests/test_mec_screen.py -q -k "model or projection or rollup or precedence or applicability or unknown"` | ❌ |
| 45-02-02 | 02 | 2 | MEC-01/04 | `mec_screen.py`, `noc_review.py`, `study_review.py`, sidecar/MEC tests | One loader/snapshot/fingerprint; shared gate implementation; injected read-only sidecars; no side artifacts | `.venv/bin/python -m pytest crawler/tests/test_mec_screen.py crawler/tests/test_noc_review.py crawler/tests/test_study_review.py crawler/tests/test_study_review_audit_seam.py -q -k "snapshot or fingerprint or gate or read_only or no_report or composition"` | MEC test ❌ / seam tests ✓ |
| 45-03-00 | 03 | 3 | MEC-02/03 | `models/vault.py`, `mecfields.py`, `extraction.py`, extraction/vault tests | Consume Wave-1 FactorGroup unchanged; add only complete MEC FieldName/review.mec evidence vocabulary; pending/correction/stale; deterministic employment-period join; no contamination | `.venv/bin/python -m pytest crawler/tests/test_extraction_store.py crawler/tests/test_extraction_conformance.py crawler/tests/test_vault_cli.py -q -k "mec or employment_period or confirmation or correction or contamination"` | MEC source ❌ / tests ✓ |
| 45-03-01 | 03 | 3 | MEC-02/04 | `mec_screen.py`, `test_mec_screen.py` | Complete FSW minima/grid; row-derived boundaries; FAIL-first outcome; exact funds reason/exemption | `.venv/bin/python -m pytest crawler/tests/test_mec_screen.py -q -k "fsw"` | ❌ |
| 45-03-02 | 03 | 3 | MEC-01/03/04 | `mec_screen.py`, `test_mec_screen.py` | Complete FST/CEC; per-period filters before aggregate; sidecars; deterministic in-memory bundle, no writes | `.venv/bin/python -m pytest crawler/tests/test_mec_screen.py -q -k "fst or cec or composition or bundle or render"` | ❌ |
| 45-04-01 | 04 | 4 | MEC-01/02/03/04 | `mec_publish.py`, `mec_screen.py`, `cli.py`, `test_mec_cli.py` | Exact CLI/config order; one snapshot; render/scan/stage/backup/replace/fsync/rollback; LKG at every failure seam | `.venv/bin/python -m pytest crawler/tests/test_mec_cli.py -q` | ❌ |
| 45-04-02 | 04 | 4 | MEC-01/02/03/04 | `test_conformance_v5_mec_no_false_meets.py`, `test_crs_no_inlined_rules.py` | Exhaustive statuses/freshness/period/funds/privacy/atomic/frozen dependency/network/CRS controls | `.venv/bin/python -m pytest crawler/tests/test_mec_cli.py crawler/tests/test_conformance_v5_mec_no_false_meets.py crawler/tests/test_crs_no_inlined_rules.py -q` | MEC tests ❌ / scanner test ✓ |

## Wave Gates

### Wave 1

- `.venv/bin/python -m pytest crawler/tests/test_mec_rules.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_gate_subset.py crawler/tests/test_freshness_staleness.py -q` (includes `program_eligibility` FactorGroup and real mec.yaml load before Wave 3)
- Fresh `python -m crawler.crs_rules` output byte-matches `crawler/data/crs_rules/COVERAGE.md`.

### Wave 2

- `.venv/bin/python -m pytest crawler/tests/test_mec_screen.py crawler/tests/test_noc_review.py crawler/tests/test_study_review.py crawler/tests/test_study_review_audit_seam.py -q`
- Loader spy count is exactly one; composed NOC/STUDY report directories are byte-identical.

### Wave 3

- `.venv/bin/python -m pytest crawler/tests/test_extraction_store.py crawler/tests/test_extraction_conformance.py crawler/tests/test_vault_cli.py crawler/tests/test_mec_screen.py -q`
- Cross-job mixed facts do not pass any work criterion.
- Evaluation filesystem/DB write spies observe no publication.

### Wave 4

- `.venv/bin/python -m pytest crawler/tests/test_mec_cli.py crawler/tests/test_conformance_v5_mec_no_false_meets.py crawler/tests/test_crs_no_inlined_rules.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_policy_no_job_offer_green.py crawler/tests/test_conformance_v5_noc_no_auto_green.py crawler/tests/test_conformance_v5_study_no_false_green.py -q`
- `.venv/bin/python -m pytest crawler/tests -q`
- `.venv/bin/python scripts/check_publish_safe.py`

## Required Failure-Injection Matrix

| Failure | Required result |
|---|---|
| Missing/invalid `--rule-max-age-days` / `PR_MEC_RULE_MAX_AGE_DAYS` | Refuse before registry/index/vault/write |
| Registry/index/DLI preflight | Refuse before vault/write |
| DB/evidence read | Prior LKG unchanged; no stage/public success |
| Private render | Prior LKG unchanged; no stage/public success |
| Public scan | Prior LKG unchanged; no stage/public success |
| Private scan | Prior LKG unchanged; no stage/public success |
| Stage write/file fsync | Stages cleaned; prior LKG unchanged |
| First/second replace | Restore every prior LKG target and fsync |
| Directory fsync | Restore/fsync LKG; suppress success |
| Ambiguous rollback | Retain backup; never destroy sole known-good private copy |

## Required Outcome Matrix

- Confirmed deterministic `FAIL` + unrelated `AT-RISK` → `DOES-NOT-MEET`.
- No `FAIL` + any `AT-RISK`/missing/unknown/unwired → `AT-RISK`.
- Exact all `PASS`/manifest-valid `N/A` → `MEETS`.
- Unknown status or criterion → `AT-RISK`.
- N/A without manifest declaration/grounded inapplicability → `AT-RISK`.
- No funds snapshot + no exemption → `AT-RISK/funds_snapshot_unavailable`.
- Grounded deterministic funds exemption → amount branch `N/A`.
- Stored funds amount never changes PASS/FAIL.

## Wave 0 Files

- [x] `crawler/tests/test_mec_rules.py`
- [x] `crawler/tests/test_mec_screen.py`
- [x] `crawler/tests/test_mec_cli.py`
- [x] `crawler/tests/test_conformance_v5_mec_no_false_meets.py`

No dependency installation or manual verification is required.
