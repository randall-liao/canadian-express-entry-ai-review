---
phase: 34-safety-conformance-release-framing
verified: 2026-07-06T14:19:23Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  # No previous VERIFICATION.md — initial verification.
---

# Phase 34: Safety Conformance & Release Framing — Verification Report

**Phase Goal:** Release only when automated conformance proves fail-closed behavior, privacy containment, intended rule grounding, and substantiation-screening framing.
**Verified:** 2026-07-06T14:19:23Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

This is the v4.0 **release gate**. Verification was performed goal-backward and
adversarially: every claim was checked against the shipped code + the real
`corpus/index.db`, the release gate was executed in this verifier's own process
(not trusted from SUMMARY), and each conformance module was independently read to
confirm it is **non-vacuous** (positive controls that DO green / DO ground, so the
negative assertions are load-bearing rather than trivially true).

### Observable Truths (ROADMAP Success Criteria — the contract)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Conformance proves no `pending`/unconfirmed/low-confidence/stale value can produce `SUBSTANTIATED` — all four modules, full factor grid | ✓ VERIFIED | `test_conformance_v40_no_false_green.py` (493 lines, 12 tests / 148 subtests PASS). Drives the REAL `vault.is_audit_eligible` choke point through the REAL `auditor.audit_one`/`run_full_audit` spine over `auditors.FULL_GRID_FACTORS` (independently enumerated = **18 factors: core 5, spouse 3, transfer 5, additional 5**). 13 direct factors × 5 blocking states (pending/rejected/low_quality/ambiguous/stale) + 5 derived transfer factors + whole-grid run all yield non-SUBSTANTIATED; `exercised == set(FULL_GRID_FACTORS)` asserted so a future grid addition cannot escape. |
| 2 | Privacy proves PII cannot reach stdout/repo/corpus/public reports/tracked fixtures/non-vault paths (non-vault refused) | ✓ VERIFIED | `test_conformance_v40_privacy_containment.py` (361 lines, 13 tests PASS). End-to-end `--json vault audit --all` CLI capture: no sentinel/`ev_` id on stdout or `PublicAuditEnvelope`; claims cite corpus `relpath#ordinal`; `private_output_path` vault-relative. `resolve_within` refuses `..`+symlink escapes (`PathEscapeError`); `scan_vault_artifact` flags every artifact type + no false positives; `git add -A` stages only `.gitignore`; `check_publish_safe.main()==0`. Live scan: **288 tracked files, 0 violations**. |
| 3 | Retrieve-what-you-cite proves every registry rule grounds the intended current rule (not historical/adjacent/wrong-family) | ✓ VERIFIED | `test_conformance_v40_retrieve_what_you_cite.py` (297 lines, 11 tests / 34 subtests PASS, real corpus present → RAN not skipped). Every non-gap rule `agrees_with_citation` AND `grounds` vs real corpus; `covered == non-gap rows`; `validate_registry` 0 violations, `grounded==total>=20`; coverage complete; `COVERAGE.md` fresh; static volatile-rule gate clean. Real job-offer current-vs-legacy separation. Non-vacuous negative controls (wrong-family / deny-families-historical / adjacent-missing-marker / marker-absent-abstain), each proven load-bearing (blind `hits[0]` mis-selects the decoy). |
| 4 | Release docs + report wording frame output as CRS substantiation SCREENING, not legal advice | ✓ VERIFIED | `SCREENING_NOTICE` rendered into every vault report via `_render_factor_card_markdown` (single + full-grid, `audit_report.py:130`); `crawler/README.md` "## Substantiation screening" section; `SCREENING.md` (86 lines). All carry the narrow `SUBSTANTIATED` definition, AT-RISK scope (semantic/NOC-duty fit/officer discretion), and "not legal advice / not a substitute". `test_conformance_v40_screening_framing.py` (11 tests PASS) asserts framing PRESENCE **and** prohibited-phrasing ABSENCE via a non-vacuous denylist (positive control flags a crafted "you are eligible … guaranteed … legal advice" string), + docs scan PII-free. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/tests/test_conformance_v40_no_false_green.py` | SAFE-01 full-grid × blocking-state matrix (≥180 ln, `FULL_GRID_FACTORS`) | ✓ VERIFIED | 493 lines; contains `FULL_GRID_FACTORS`; wired to `vault.audit_eligible_values` + `auditor.run_full_audit`/`AuditGroundingError`. 12 tests / 148 subtests PASS. |
| `crawler/tests/test_conformance_v40_privacy_containment.py` | SAFE-02 end-to-end privacy gate (≥180 ln, `scan_vault_artifact`) | ✓ VERIFIED | 361 lines; contains `scan_vault_artifact`; wired to `check_publish_safe` + `paths.resolve_within`/`PathEscapeError`. 13 tests PASS. |
| `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py` | SAFE-03 whole-registry + negative controls (≥170 ln, `retrieve_what_you_cite`) | ✓ VERIFIED | 297 lines; wired to `crs_rules.retrieve_what_you_cite`/`validate_registry`/`coverage_report` + real `corpus/index.db`. 11 tests / 34 subtests PASS. |
| `crawler/tests/test_conformance_v40_screening_framing.py` | SAFE-04 framing presence + absence (≥90 ln) | ✓ VERIFIED | 185 lines; renders real report markdown, asserts `SCREENING_NOTICE` present + denylist absent (non-vacuous). 11 tests PASS. |
| `crawler/tests/test_conformance_v40_release_gate.py` | Release-gate: one command collects all four SAFE modules (≥40 ln) | ✓ VERIFIED | 81 lines; subprocess `--collect-only` guarded by `PR_CONFORMANCE_RUNNER`; asserts marker on every SAFE module. 4 tests PASS. |
| `scripts/run_conformance.py` | Single authoritative entry point (≥25 ln, `test_conformance_v40`) | ✓ VERIFIED | 89 lines; marker-independent glob `crawler/tests/test_conformance_v40_*.py`; exits with pytest rc; SAFE-01..04 banner. Real run **exit 0, 51 passed**. |
| `SCREENING.md` | Release framing doc (≥40 ln) | ✓ VERIFIED | 86 lines; narrow SUBSTANTIATED, four-verdict vocab, AT-RISK scope, privacy model, not-legal-advice, gate command. Scans PII-free. |
| `crawler/audit_report.py` | `SCREENING_NOTICE` constant rendered into report | ✓ VERIFIED | Constant defined (`:54`) + appended in `_render_factor_card_markdown` (`:130`), used by both single + full-grid reports. |
| `pyproject.toml` | `conformance` marker registered, no new runtime dep | ✓ VERIFIED | Only `[tool.pytest.ini_options].markers` table added; `dependencies` unchanged; `poetry.lock` unchanged in phase. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `test_conformance_v40_no_false_green.py` | `crawler/vault.py` | `is_audit_eligible` / `audit_eligible_values` choke point | ✓ WIRED | Choke point asserted to block every state AND admit the legitimate value (non-vacuous). |
| `test_conformance_v40_no_false_green.py` | `crawler/auditor.py` | `run_full_audit` / `AuditGroundingError` | ✓ WIRED | Verdict consequence + zero-artifact fail-closed ordering asserted. |
| `test_conformance_v40_privacy_containment.py` | `scripts/check_publish_safe.py` | `scan_vault_artifact` / `main()` | ✓ WIRED | Flags all vault artifacts; `main()==0` over real tree. |
| `test_conformance_v40_privacy_containment.py` | `crawler/paths.py` | `resolve_within` / `PathEscapeError` | ✓ WIRED | `..` + symlink escapes refused. |
| `test_conformance_v40_retrieve_what_you_cite.py` | `crawler/crs_rules.py` + `corpus/index.db` | `retrieve_what_you_cite` / `validate_registry` | ✓ WIRED | Real-corpus per-rule agree+ground; RAN (not skipped) locally. |
| `crawler/audit_report.py` | `test_conformance_v40_screening_framing.py` | `SCREENING_NOTICE` rendered + asserted | ✓ WIRED | Rendered markdown asserted to carry the notice + be PII-free. |
| `scripts/run_conformance.py` | `test_conformance_v40_release_gate.py` | glob collects all four SAFE modules | ✓ WIRED | `--collect-only` enumerates 51 tests spanning all 4 SAFE modules. |

### Behavioral Spot-Checks / Probe Execution

The release gate is the phase's probe. All commands run by this verifier from repo root:

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Release gate collects all four SAFE modules | `run_conformance.py --collect-only -q` | 51 tests collected across all 4 SAFE modules + release-gate; rc=0 | ✓ PASS |
| Release gate runs green (fail-closed exit) | `run_conformance.py` | `51 passed in 16.40s`; banner `PASS — SAFE-01..04`; **exit 0** | ✓ PASS |
| Marker selector matches glob set | `pytest -m conformance -q` | `51 passed, 661 deselected, 182 subtests passed` (same set) | ✓ PASS |
| Full suite — no regression Phases 29–33 + frozen path | `pytest crawler/tests scripts/tests --deselect …test_dupaudit.py -q` | `685 passed, 1 skipped, 26 deselected, 377 subtests passed` (skip = pre-existing `crawl4ai` optional dep, unrelated) | ✓ PASS |
| Publish-safe over tracked tree | `check_publish_safe.py` | `288 tracked files scanned, 0 violations`; exit 0 | ✓ PASS |
| SAFE-01 non-vacuity (positive controls green) | `pytest …no_false_green.py -v` | `test_each_module_has_a_green_and_grid_is_complete` + `test_legitimate_value_is_admitted_non_vacuous` PASS; 12/148 | ✓ PASS |

### Non-Vacuity Audit (adversarial — SUMMARY not trusted)

| Module | Positive control present? | Evidence |
| ------ | ------------------------- | -------- |
| SAFE-01 | ✓ | One SUBSTANTIATED per module reached (core.language.first / spouse.language / transfer.foreign_language / additional.nomination); choke point ADMITS the legitimate confirmed+ok+fresh value for every direct factor. |
| SAFE-02 | ✓ | Report DOES carry the sentinels + `ev_` ids inside the vault (proving the sentinels are real/detectable), while stdout/envelope do not; publish-safe DOES flag every vault-artifact type and does NOT flag ordinary repo files. |
| SAFE-03 | ✓ | Each negative control proven load-bearing: blind `searchindex.search(family)[0]` selects the wrong/superseded/adjacent decoy, and the correct-family+marker mirror grounds the intended chunk. |
| SAFE-04 | ✓ | Denylist helper flags a crafted "you are eligible … guaranteed … legal advice" string; the negated disclaimer is normalized out first so it never trips the gate. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| SAFE-01 | 34-01 | Conformance proves no pending/unconfirmed/low-confidence/stale → SUBSTANTIATED | ✓ SATISFIED | Truth 1 |
| SAFE-02 | 34-02 | Privacy tests prove no PII reaches stdout/repo/corpus/public reports; non-vault refused | ✓ SATISFIED | Truth 2 |
| SAFE-03 | 34-03 | Retrieve-what-you-cite proves each rule grounds the intended rule | ✓ SATISFIED | Truth 3 |
| SAFE-04 | 34-04 | Release docs frame output as substantiation screening, not legal advice | ✓ SATISFIED | Truth 4 |

No orphaned requirements — REQUIREMENTS.md maps SAFE-01..04 to Phase 34, each claimed by exactly one plan.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `test_conformance_v40_no_false_green.py` | 411 | `"synthetic placeholder quote"` | ℹ️ Info | Synthetic test quote for a `gap:true` row — a fixture value, not a stub/debt marker. |
| `crawler/README.md` | 76, 99 | "placeholder rules" | ℹ️ Info | Pre-existing README template prose, outside the SAFE-04 section; not a debt marker. |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` debt markers in any phase-modified file. No stubs, empty handlers, or unwired artifacts. The two pre-existing tests reconciled with the notice (`test_full_audit_cutoff.py`, `test_full_audit_integration.py`) were **strengthened** (normalize the negated disclaimer, then additionally assert framing IS present), not weakened.

### Release-Integrity Checks

| Check | Result |
| ----- | ------ |
| No new runtime dependencies | ✓ `pyproject.toml [project].dependencies` unchanged; `poetry.lock` unchanged in phase (only a `[tool.pytest.ini_options]` marker table added). |
| Frozen v3.x trust path unchanged | ✓ Phase diff touches only conformance tests, `SCREENING.md`, `scripts/run_conformance.py`, `README.md`, `audit_report.py` (v4.0 report writer), `pyproject.toml`, and two pre-existing test reconciliations. No `searchindex`/`crs_rules` engine/`vault` core/`auditor` spine source changed. |
| Docs generic / shareable / PII-free | ✓ `SCREENING.md` + README screening section scan publish-safe (0 violations); no dev-machine specifics. |
| Claimed commits exist | ✓ `e60d36b`, `b553502`, `cc09bc6`, `f669fe3`, `3e7df7e`, `d5fe076` all present in git history. |

### Human Verification Required

None. All four Success Criteria are objectively provable and were proven by executing the automated conformance gate in this verifier's own process; the framing docs were read directly and independently confirmed. No PLAN `<human-check>` deferrals were present.

### Gaps Summary

No gaps. All four ROADMAP Success Criteria and all four SAFE requirements are verified against the shipped code and the real corpus. The single authoritative release gate (`scripts/run_conformance.py`) collects and passes all four SAFE conformance modules (51 tests, exit 0); `-m conformance` selects the same set; the full suite is green (685 passed) with no regressions; publish-safe is clean (288 files, 0 violations); no new runtime deps; the frozen v3.x trust path is untouched.

**Observation (Info, not a gap):** SAFE-03's wrong-family / historical-superseded / adjacent negative controls run against a purpose-built **synthetic** FTS index rather than the real corpus, because the real corpus does not surface an adversarial decoy ranking above the intended chunk. This is a documented, sound, and load-bearing choice: the mechanism guards are proven non-vacuous (blind `hits[0]` would mis-ground) on the synthetic index, while the **real corpus** carries the required contract — every non-gap rule grounds the intended current rule (positive per-rule agree+ground) and the job-offer current-vs-legacy separation. SC3 ("every registry rule grounds the intended current rule rather than a historical/adjacent/wrong-family chunk") is therefore satisfied.

---

_Verified: 2026-07-06T14:19:23Z_
_Verifier: the agent (gsd-verifier)_
