---
phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
verified: 2026-07-20T15:03:27Z
status: passed
score: 13/13 must-haves verified
overrides_applied: 0
gates:
  focused_mec:
    status: passed
    result: "134 passed, 568 subtests passed"
  prior_sidecar_conformance:
    status: passed
    result: "42 passed, 135 subtests passed"
  full_crawler:
    status: passed
    result: "1372 passed, 2 skipped, 1768 subtests passed"
  publish_safe:
    status: passed
    result: "468 tracked files scanned, 0 violations"
  compile:
    status: passed
    result: "crawler compileall exited 0"
  final_review:
    status: clean
    result: "No source changes after fe2d3a9; git diff --check clean"
gaps: []
human_verification: []
---

# Phase 45: MEC Program-Eligibility Sidecar Verification Report

**Phase Goal:** Deliver a separate, grounded, fail-closed FSW/FST/CEC MEC screen without changing CRS totals or `PublicAuditEnvelope`.
**Verified:** 2026-07-20T15:03:27Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | MEC-01: exact per-program sidecar CLI emits the closed screening summary | ✓ VERIFIED | `cli.py:1629-1793,2043-2074`; parser and real CLI tests passed. |
| 2 | MEC-02: FSW evaluates grounded work, language, education, and all six grid factors | ✓ VERIFIED | `mec_screen.py:984-1613`; exact 17-row FSW manifest and focused/conformance tests passed. |
| 3 | MEC-03: FST and CEC evaluate distinct complete criteria fail-closed | ✓ VERIFIED | `mec_screen.py:2017-2694`; 11 FST and 10 CEC rows; boundary and exclusion tests passed. |
| 4 | MEC-04: policy values come from cited rows; stale/unresolved state cannot green | ✓ VERIFIED | 38 cited, non-gap `mec.yaml` rows; shared scanner clean; grounding tamper tests passed. |
| 5 | One immutable snapshot, fingerprint, shared gate, effectivity, and freshness bind a run | ✓ VERIFIED | `RegistrySnapshot` deep isolation at `crs_rules.py:169-194`; CLI loads once; `prepare_mec_gate` calls `auditor.gate_subset`, `row_in_effect`, and freshness for every row. |
| 6 | Evidence is pending/confirm-first, five-key stale-aware, candidate-scoped, and period-isolated | ✓ VERIFIED | `mecfields.py:460-650`; six locked `review.mec` routes; malformed and cross-period joins demote to `AT-RISK`. |
| 7 | FSW criteria use confirmed evidence and registry-derived bounds | ✓ VERIFIED | No CRS totals are consumed; unresolved grid factors retain row-derived lower/upper bounds. |
| 8 | FST/CEC criteria apply period predicates before aggregation | ✓ VERIFIED | Same-NOC, overlap, lookback, authorization, student, self-employment, and language-TEER tests passed. |
| 9 | Rollup is deterministic FAIL-first and admits no false `MEETS` | ✓ VERIFIED | `mec_screen.py:612-697`; malformed/missing/unwired/invalid-N/A demote; valid FAIL wins over unrelated uncertainty. |
| 10 | Offers remain manual/fail-closed; complete FST certificate evidence has a real PASS path | ✓ VERIFIED | Offer rows have no machine-pass branches; certificate requires complete conflict-free scope, validity, jurisdiction, and matching qualifying trade (`mec_screen.py:2222-2293`). |
| 11 | Funds amounts are deferred and cannot decide a criterion | ✓ VERIFIED | No amount/LICO values in registry; amount variants remain `AT-RISK/funds_snapshot_unavailable`; manual offers cannot activate exemption. |
| 12 | CLI publication is PII-light, scan-first, atomic, recoverable, and durable before success | ✓ VERIFIED | `mec_publish.py:58-335`; render/scan/stage/replace/fsync failure matrix preserves LKG; no public file is written. |
| 13 | Public audit/CRS, dependencies, release gate, no-inline, loader, and network surfaces remain frozen | ✓ VERIFIED | Protected-file diff empty; pinned hashes pass; no MEC network import or alternate loader; `PublicAuditEnvelope` and `FULL_GRID_FACTORS` unchanged. |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `crawler/data/crs_rules/mec.yaml` | Complete grounded registry | ✓ VERIFIED | 38 rows: FSW 17, FST 11, CEC 10; zero gaps/uncited rows/funds amounts. |
| `crawler/crs_rules.py` | Exact manifest and shared no-inline gate | ✓ VERIFIED | Manifest exactness, scanner enrollment, and positive controls pass. |
| `crawler/snapshot_policy.py` | No-default freshness policy | ✓ VERIFIED | Explicit-over-env, positive-only resolver and fail-closed row predicate. |
| `crawler/models/mec.py` | Closed public/private contracts | ✓ VERIFIED | Strict status/reason schemas and explicit allowlist projection. |
| `crawler/mecfields.py` | Complete private adapter and period joins | ✓ VERIFIED | Candidate-scoped SQL, five-key eligibility, deterministic period IDs. |
| `crawler/mec_screen.py` | All evaluators and rollup | ✓ VERIFIED | Substantive, CLI-wired, snapshot-bound, and tested end-to-end. |
| `crawler/mec_publish.py` | Atomic durable private publisher | ✓ VERIFIED | Two-file LKG transaction with scan, backups, rollback, and fsync. |
| `crawler/cli.py` | Exact `vault screen-mec` command | ✓ VERIFIED | One command spelling; durable publish precedes `_vault_ok`. |
| Phase 45 test modules | Focused and conformance proof | ✓ VERIFIED | Collected and passed in focused and full runs. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| CLI | freshness resolver | one pre-read resolution | ✓ WIRED | Invalid/missing value refuses before registry/index/vault/write. |
| CLI | registry snapshot | one command-boundary load | ✓ WIRED | Loader called once; same snapshot/fingerprint reaches composition. |
| Gate context | corpus | `auditor.gate_subset` | ✓ WIRED | Exact selected subset grounds before evaluation. |
| Evidence adapter | vault | candidate SQL + `is_audit_eligible` | ✓ WIRED | Confirmed/current/quality-ok values only. |
| Evaluators | registry rows | typed `machine_check` values | ✓ WIRED | Thresholds, windows, hierarchy, and grid values are row-derived. |
| CLI | publisher | `publish_mec_bundle` before `_vault_ok` | ✓ WIRED | Failure emits no success envelope. |
| Publisher | filesystem durability | `resolve_within`, stage, replace, `fsync_dir` | ✓ WIRED | Contained two-file transaction and rollback. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `mecfields.py` | `MecEvidence` | Candidate-bound vault SQL + five-key gate | Yes | ✓ FLOWING |
| `mec_screen.py` | criteria/report | Confirmed cards, keyed evidence, cited registry rows | Yes | ✓ FLOWING |
| `mec_publish.py` | private/public bytes | Validated `MecPublicationBundle` | Yes | ✓ FLOWING |
| CLI envelope | `PublicMecSummary` | Successful durable private publication | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Phase 45 focused behavior | `pytest test_mec_rules.py test_mec_screen.py test_mec_cli.py test_conformance_v5_mec_no_false_meets.py test_crs_no_inlined_rules.py -q` | 134 passed, 568 subtests | ✓ PASS |
| Prior sidecars remain conformant | Three v5 policy/NOC/study conformance files | 42 passed, 135 subtests | ✓ PASS |
| Full crawler regression | `pytest crawler/tests -q` | 1372 passed, 2 skipped, 1768 subtests | ✓ PASS |
| Publish safety | `python scripts/check_publish_safe.py` | 468 files, 0 violations | ✓ PASS |
| Exact CLI exists | `python -m crawler.cli vault screen-mec --help` | Required `--program {fsw,fst,cec}` shown | ✓ PASS |

### Probe Execution

No Phase 45 probe scripts were declared or discovered.

### Requirements Coverage

| Requirement | Source Plans | Status | Evidence |
|---|---|---|---|
| MEC-01 | 45-02/03/04 | ✓ SATISFIED | Exact CLI, closed summary, screening notice, frozen CRS/envelope. |
| MEC-02 | 45-01/02/03/04 | ✓ SATISFIED | Complete grounded FSW manifest and evaluator. |
| MEC-03 | 45-01/02/03/04 | ✓ SATISFIED | Complete distinct FST/CEC evaluators and evidence controls. |
| MEC-04 | 45-01/02/03/04 | ✓ SATISFIED | Cited rows, shared grounding, freshness/effectivity, no-inline gate. |

No Phase 45 requirements are orphaned. SAFE-11/12 remain explicitly owned by Phase 46.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|---|---|---|---|
| Phase 45 production surface | No TBD/FIXME/XXX or placeholder implementations | ℹ️ Info | No blocker. |
| `test_conformance_v5_mec_no_false_meets.py` | Funds-exemption test name is broader than its current manual-offer expectation | ℹ️ Info | Test still correctly proves funds defer; no product gap. |
| `mec_publish.py` | MEC tests do not directly inject partial `mkdir_durable` failure | ℹ️ Info | Shared durable-mkdir code is covered elsewhere; all required report mutation seams are covered. |

### Human Verification Required

None. The phase behavior is deterministic CLI/data/persistence logic and was exercised automatically.

### Gaps Summary

No blocking or warning-level gaps. The final source matches the corrected manual-offer and complete-certificate contract, and no source changed after the clean final review.

---

_Verified: 2026-07-20T15:03:27Z_
_Verifier: the agent (gsd-verifier)_
