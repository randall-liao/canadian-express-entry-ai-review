---
phase: 46
slug: safe-conformance-release-gate
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-20
revised: 2026-07-20T12:05:12-04:00
---

# Phase 46 — Validation Strategy

| Property | Exact value |
|---|---|
| Framework | pytest with stdlib `unittest.TestCase`/`subTest` in conformance modules |
| Per-task quick checks | The exact targeted command in the task map; each is intended to finish in under 120 seconds |
| Per-wave checks | The cumulative commands under Wave Gates, run after every plan in that wave completes |
| Focused v5 phase check | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_privacy_release.py crawler/tests/test_conformance_v5_release_gate.py -q` |
| All-v5 check | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_*.py -q` |
| Full test command | `.venv/bin/python -m pytest crawler/tests scripts/tests -q` |
| Authoritative release command | `.venv/bin/python scripts/run_conformance.py -q` |
| Publish safety | `.venv/bin/python -m pytest scripts/tests/test_check_publish_safe.py -q` then `.venv/bin/python scripts/check_publish_safe.py` |

The quick commands are implementation feedback, not release evidence. Per-wave gates prove each dependency boundary. The final release/phase gate is mandatory after Plan 06 and is the only level that supports the Phase 46 release claim.

## Exact Task Map

| Task | Plan | Wave | Reqs | Task/test type | Exact files | Secure behavior owned | Exact quick automated command | Status |
|---|---:|---:|---|---|---|---|---|---|
| 46-01-01 | 01 | 1 | SAFE-11 | `auto`, `tdd=true`; real-index grounding/provenance integration | `crawler/tests/test_conformance_v5_grounding.py` | Exact 38-row/75-citation MEC, 3-row/5-citation POLICY, and 3-row/4-citation STUDY/DLI manifests ground; runtime DLI file/manifest/index/hash/date lineage agrees; release-mode missing prerequisites fail with path-free text | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py -q -x` | Planned — create |
| 46-01-02 | 01 | 1 | SAFE-11 | `auto`, `tdd=true`; adversarial grounding + static scanner | `crawler/tests/test_conformance_v5_grounding.py`, `crawler/tests/test_crs_no_inlined_rules.py` | Wrong family/quote/marker/citation and superseded-source controls fail with non-vacuous valid mirrors; exact named v5 scanner enrollment includes POLICY and DLI without weakening positive controls | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py crawler/tests/test_crs_no_inlined_rules.py -q` | Planned — extend new grounding test; modify existing scanner test |
| 46-02-01 | 02 | 1 | SAFE-12 | `auto`, `tdd=true`; independent MEC matrix integration | `crawler/tests/test_conformance_v5_release_matrix.py` | Real MEC entry points fail closed for stale/superseded/out-of-window/unconfirmed/rejected/low-quality/missing/unwired/config/index/snapshot states; funds/manual/offer inputs cannot manufacture MEETS | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_release_matrix.py -q -x -k mec` | Planned — create |
| 46-02-02 | 02 | 1 | SAFE-12 | `auto`, `tdd=true`; independent POLICY matrix integration | `crawler/tests/test_conformance_v5_release_matrix.py` | Legacy, post-repeal, physician, malformed-window, absent, and stale five-key offer paths remain manual/non-green; POLICY sidecar and frozen CRS guard award zero | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_policy_no_job_offer_green.py -q -k "policy or job_offer"` | Planned — extend |
| 46-03-01 | 03 | 2 | SAFE-12 | `auto`, `tdd=true`; STUDY snapshot/provenance integration | `crawler/tests/test_conformance_v5_release_matrix.py` | Current-only designation, PGWP Details/No, evidence/config/index/snapshot absence, future/stale/drifted provenance, and selector tampering fail closed with exact public fields and zero refusal artifacts | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_release_matrix.py -q -x -k study` | Planned — extend |
| 46-03-02 | 03 | 2 | SAFE-12 | `auto`, `tdd=true`; NOC and cross-screen drift integration | `crawler/tests/test_conformance_v5_release_matrix.py` | NOC source/pending/partial/rejected/stale/citation-drift/superseded-duty states never score; snapshot-A evidence replayed under B cannot re-green MEC/POLICY/STUDY/NOC or overwrite private reports | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_noc_no_auto_green.py -q` | Planned — extend |
| 46-04-01 | 04 | 1 | SAFE-12 | `auto`, `tdd=true`; privacy/atomic publication integration | `crawler/tests/test_conformance_v5_privacy_release.py` | PII canaries, `ev_` IDs, and absolute paths remain out of both streams/public objects/DLI bytes; private reports stay root-contained, scan before atomic commit, and preserve LKG on injected failures | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_privacy_release.py -q -x -k "privacy or containment or atomic"` | Planned — create |
| 46-04-02 | 04 | 1 | SAFE-12 | `auto`, `tdd=true`; static dependency/network/contracts/framing conformance | `crawler/tests/test_conformance_v5_privacy_release.py` | Exact dependencies/lock, no audit-time network/alternate loader, closed PublicAuditEnvelope/CRS, named source hashes, publish safety, and screening/not-legal-advice framing remain frozen and positive-controlled | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_privacy_release.py crawler/tests/test_conformance_v40_screening_framing.py scripts/tests/test_check_publish_safe.py -q` | Planned — extend |
| 46-05-01 | 05 | 3 | SAFE-12 | `auto`, `tdd=true`; confirmed-vault cross-phase E2E | `crawler/tests/test_conformance_v5_privacy_release.py` | Distinct pending-then-confirmed five-key evidence drives real MEC/POLICY/STUDY/NOC/CRS/public paths against local grounded lineage under one fingerprint; sidecars cannot alter CRS and public output remains private-data-free | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_privacy_release.py -q -x -k confirmed_vault` | Planned — extend |
| 46-05-02 | 05 | 3 | SAFE-12 | `auto`, `tdd=true`; authoritative prerequisites + drift replay E2E | `crawler/tests/test_conformance_v5_privacy_release.py` | `PR_CONFORMANCE_RUNNER=1` converts missing index/DLI/confirmed-fixture prerequisites to stable PII-free failures; successful A evidence replay under B refuses, stays offline, and preserves LKG | `PR_CONFORMANCE_RUNNER=1 .venv/bin/python -m pytest crawler/tests/test_conformance_v5_privacy_release.py -q -x` | Planned — extend |
| 46-06-01 | 06 | 4 | SAFE-11/SAFE-12 | `auto`, `tdd=true`; runner subprocess/self-test | `crawler/tests/test_conformance_v5_release_gate.py`, `scripts/run_conformance.py` | Bounded deduplicated v4[01]+v5 discovery hard-requires every release module/node/marker, rejects empty/no-v5/missing sets, prevents recursive collection, sets release guard only for real runs, and propagates exact pytest status | `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_release_gate.py crawler/tests/test_conformance_v41_release_gate.py crawler/tests/test_conformance_v5_release_gate.py -q` | Planned — create runner test; modify runner |
| 46-06-02 | 06 | 4 | SAFE-11/SAFE-12 | `auto`; non-TDD config/pin/release closure | `pyproject.toml`, `crawler/tests/test_conformance_v5_mec_no_false_meets.py` | Only marker text and reviewed runner/pyproject pins move; dependencies, lock, production, envelope, CRS, and screen hashes remain fixed. Fast changed-surface verification stays under 120 seconds; final release/full/publish/freeze gates remain mandatory at plan close | `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_release_gate.py crawler/tests/test_conformance_v41_release_gate.py crawler/tests/test_conformance_v5_release_gate.py crawler/tests/test_conformance_v5_mec_no_false_meets.py::TestFrozenMecSurfaces::test_dependency_release_gate_and_crs_sources_are_frozen -q` | Planned — modify existing config and frozen-pin test |

All six plans and all twelve task IDs have one automated owner. Tasks 46-01-01 through 46-06-01 are test-first (`tdd=true`); Task 46-06-02 is a non-TDD metadata/pin rollover whose quick check targets only the changed release surfaces. No task-level command substitutes for the final gate.

## Wave Gates

### Wave 1 — Plans 46-01, 46-02, and 46-04

- `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py crawler/tests/test_crs_no_inlined_rules.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_policy_no_job_offer_green.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_privacy_release.py crawler/tests/test_conformance_v40_screening_framing.py scripts/tests/test_check_publish_safe.py -q`
- Gate result: exact SAFE-11 manifests/scanner, independent MEC/POLICY negatives, and privacy/network/dependency/framing controls are present and non-vacuous before STUDY/NOC composition.

### Wave 2 — Plan 46-03 after 46-02

- `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_study_no_false_green.py crawler/tests/test_conformance_v5_noc_no_auto_green.py -q`
- Gate result: the single matrix now covers all four screens, exact STUDY/NOC provenance and source states, and A-to-B registry drift without a false green or replacement artifact.

### Wave 3 — Plan 46-05 after 46-01, 46-03, and 46-04

- `PR_CONFORMANCE_RUNNER=1 .venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_privacy_release.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_full_audit_integration.py -q`
- Gate result: real local index/DLI prerequisites cannot skip; distinct confirmed evidence reaches every screen under one fingerprint; drift replay remains offline, fail-closed, and LKG-preserving.

### Wave 4 quick closure — Plan 46-06

- `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_release_gate.py crawler/tests/test_conformance_v41_release_gate.py crawler/tests/test_conformance_v5_release_gate.py crawler/tests/test_conformance_v5_mec_no_false_meets.py::TestFrozenMecSurfaces::test_dependency_release_gate_and_crs_sources_are_frozen -q`
- Gate result: changed runner, marker, required-module contract, exact return behavior, and two intentional pins pass a focused under-120-second check.

## Final Release / Phase Gate

Run after Task 46-06-02's quick check and before Plan 46-06 or Phase 46 is marked complete:

1. Focused new modules: `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py crawler/tests/test_conformance_v5_release_matrix.py crawler/tests/test_conformance_v5_privacy_release.py crawler/tests/test_conformance_v5_release_gate.py -q`
2. Every bounded v5 module: `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_*.py -q`
3. Non-recursive collection proof: `.venv/bin/python scripts/run_conformance.py --collect-only -q`
4. Authoritative SAFE-01..12 release: `.venv/bin/python scripts/run_conformance.py -q`
5. Full crawler and scripts suites: `.venv/bin/python -m pytest crawler/tests scripts/tests -q`
6. Publish-safe unit gate: `.venv/bin/python -m pytest scripts/tests/test_check_publish_safe.py -q`
7. Real publish-safe scanner: `.venv/bin/python scripts/check_publish_safe.py`
8. Frozen-source gate: `git diff --exit-code -- poetry.lock crawler/models/audit.py crawler/crs_audit.py crawler/auditors/__init__.py crawler/policy_offer.py crawler/mec_screen.py crawler/study_review.py crawler/noc_review.py crawler/noc_worksheet.py`

Acceptance requires all eight steps to pass, the authoritative runner to print SAFE-01..12 PASS, zero Phase 46 prerequisite skips, exact return-code propagation, and exact passed/skipped/subtest counts plus commands recorded in `46-06-SUMMARY.md`.

## Required Security and Failure Matrix

| Boundary / attack | Required observable result | Owning tasks |
|---|---|---|
| Wrong citation family, quote, marker, coordinate, or superseded source | Agreement/grounding refuses; paired mirror proves retrieval is non-empty | 46-01-01/02 |
| Omitted POLICY/DLI or other named v5 scanner surface | Exact-set scanner assertion fails while positive controls still bite | 46-01-02 |
| MEC stale/superseded/out-of-window/unconfirmed/rejected/low-quality/missing/unwired state | Exact AT-RISK/DOES-NOT-MEET reason; never MEETS | 46-02-01 |
| POLICY legacy/post-repeal/physician/malformed-window/stale evidence | Exact manual/N/A/AT-RISK result and zero CRS award | 46-02-02 |
| STUDY missing/bad config/index/snapshot, future/stale/drifted lineage, or dynamic-selector tamper | Exact closed reason/as_of, no report/vault mutation, never green | 46-03-01 |
| NOC missing source, pending/partial/rejected/stale/drifted/superseded duty | Exact safe public result, bounded confirmations, no score/private fields | 46-03-02 |
| Registry/snapshot A evidence replayed under B | Composition refuses before sidecar reuse; no replacement report or success envelope | 46-03-02, 46-05-02 |
| Applicant canary, `ev_`, candidate ID, or absolute path crosses public boundary | Whole-stream/object/snapshot scans fail; private fixture remains demonstrably live | 46-04-01, 46-05-01 |
| Stage/replace/fsync/publication failure | No partial/public success; prior LKG bytes survive atomically beneath candidate root | 46-04-01 |
| Network, refresh, alternate loader, dependency, lock, envelope, CRS, or framing drift | AST/runtime/frozen/hash/denylist assertion fails without rebaselining production/docs | 46-04-02, 46-06-02 |
| Missing authoritative index/DLI/confirmed fixture | Normal focused run may honestly skip; `PR_CONFORMANCE_RUNNER=1` fails with stable path-free text | 46-01-01, 46-05-02, 46-06-01 |
| Empty/no-v5/missing-required release discovery or recursive collection | Runner fails before real pytest or self-test detects recursion; exact nonzero status propagates | 46-06-01 |

## Wave 0 Files and Status

- [ ] `crawler/tests/test_conformance_v5_grounding.py` — create in 46-01-01
- [ ] `crawler/tests/test_conformance_v5_release_matrix.py` — create in 46-02-01, extend in 46-02-02 and 46-03
- [ ] `crawler/tests/test_conformance_v5_privacy_release.py` — create in 46-04-01, extend in 46-04-02 and 46-05
- [ ] `crawler/tests/test_conformance_v5_release_gate.py` — create in 46-06-01
- [x] `crawler/tests/test_crs_no_inlined_rules.py` — existing; extend in 46-01-02
- [x] `crawler/tests/test_conformance_v5_mec_no_false_meets.py` — existing; roll only two reviewed pins in 46-06-02

No dependency installation, external service, or manual verification is required.

## Source Coverage Audit

| SOURCE | ID | Feature / constraint | Plan | Status | Notes |
|---|---|---|---|---|---|
| GOAL | — | Extend exact grounding/no-inline proof to every v5 family and ship one end-to-end fail-closed release command | 01-06 | COVERED | Exact manifests, four-screen matrix/E2E, bounded runner |
| REQ | SAFE-11 | MEC/POLICY/STUDY/DLI values derive from grounded citations and stay out of code | 01,06 | COVERED | Grounding/scanner module is hard-required by runner |
| REQ | SAFE-12 | One command proves all-screen never-green, provenance, privacy, dependencies, and framing | 02-06 | COVERED | Matrix, privacy/E2E, runner, full phase gate |
| RESEARCH | — | Independent non-circular fixtures with paired positives and exact counts | 01-05 | COVERED | No donor helper imports or production-derived expectations |
| RESEARCH | — | Missing release prerequisites fail rather than skip | 01,05,06 | COVERED | `PR_CONFORMANCE_RUNNER=1` contract |
| RESEARCH | — | Bounded v4[01]+v5 runner, marker parity, non-recursion, and exact return code | 06 | COVERED | Runner self-test plus authoritative command |
| RESEARCH | — | Zero dependency/network drift; privacy, atomicity, framing, frozen envelope/CRS | 04,06 | COVERED | Positive-controlled checks and frozen-source gate |
| CONTEXT | — | No Phase 46 CONTEXT.md or D-XX decisions exist | — | EXCLUDED | No deferred discussion item is planned |

**Audit result:** all GOAL, SAFE-11, SAFE-12, RESEARCH, and direct revision constraints are covered. No source item is missing and no production scope was added.
