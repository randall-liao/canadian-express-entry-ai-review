---
phase: 32-auditor-vertical-slice-private-report-contract
verified: 2026-07-06T11:15:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 32: Auditor Vertical Slice & Private Report Contract — Verification Report

**Phase Goal:** Applicant can run one complete CRS auditor slice from confirmed evidence plus grounded rules and receive fail-closed, vault-only evidence-bearing output.
**Verified:** 2026-07-06T11:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

Verified **goal-backward** against the shipped code AND by running the real
`vault audit` CLI end-to-end on a **synthetic** candidate against the **real**
corpus index (`corpus/index.db`). Every success criterion was proven by
executing the code path, not by trusting SUMMARY claims. All data used was
synthetic — no real PII was printed or inspected.

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | A pilot factor slice emits `SUBSTANTIATED`/`GAP`/`AT-RISK`/`N/A` only after every rule claim passes the existing grounding gate. | ✓ VERIFIED | `auditor.audit_factor` calls `_gate_or_raise` → `crs_rules.validate_registry` → frozen `grounding.check_answer` (crs_rules.py:171) BEFORE any evidence read or verdict; `Verdict` is a closed `Literal[...]` (audit.py:60). End-to-end: real registry subset grounds clean (0 violations) → verdict emitted; mismatched index → `AuditGroundingError`, no verdict. |
| 2 | `SUBSTANTIATED` impossible unless proof exists, evidence confirmed/corrected, threshold met, and rule grounded+cited. | ✓ VERIFIED | `_decide` (auditor.py:184-229) requires all 4 abilities present + accepted test type + every ability resolves to a CLB + in-window + `lowest ≥ claimed_threshold`; evidence is read ONLY via `vault.audit_eligible_values` (confirmed/corrected + quality ok + not stale, vault.py:1060-1078). Green reachable through the FULL `run_audit` write pipeline — `test_audit_report.py::test_writes_two_files_and_returns_pair` + `test_auditor.py::test_happy_path_is_substantiated` both PASS with a complete grounded synthetic registry. |
| 3 | Pending/low-confidence/stale/missing/semantically-unresolved evidence → `GAP`/`AT-RISK`, never green. | ✓ VERIFIED | End-to-end CLI matrix over the real corpus: pending→GAP, low_quality→GAP, stale→GAP, missing→GAP, threshold_miss→AT-RISK, wrong_test→GAP — **none SUBSTANTIATED**. Backed by 16 `test_auditor.py` matrix tests (all pass). |
| 4 | Public JSON/stdout PII-light (generic claims, counts, private path, run id); full evidence-bearing reports only under the vault. | ✓ VERIFIED | Real `vault audit --json` stdout envelope carried only `run_id`, `factor_id`, `verdicts[]`, corpus-cited `claims[]` (`relpath#ordinal`, none `ev_`), `counts{}`, vault-relative `private_output_path` — **NO** `ev_c94504d76ad4`, **NO** raw scores (7.5/8.0), **NO** absolute path. The on-disk vault report JSON DOES carry the `ev_` id + raw scores. Human detail routes to stderr only. Structural pydantic firewall: `extra="forbid"` + `citation_id` `field_validator` rejecting `ev_`. `check_publish_safe.py` → 0 violations; `git status` tracks no vault artifact. |
| 5 | A grounding failure writes NO partial report; grounded `GAP`/`AT-RISK` are valid results, not execution errors. | ✓ VERIFIED | End-to-end via CLI against a mismatched index: `ok:false`, **exit 2**, PII-free error (rule ids + `unresolvable`), crs-audit dir does NOT exist, `audit_runs=0` `factor_verdicts=0` (zero orphan rows). Grounded GAP/AT-RISK/N/A runs → `ok:true`, exit 0, complete report written. Confirmed by `test_audit_report.py::test_grounding_failure_writes_nothing` + `test_grounded_gap_writes_report_without_raising`. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `crawler/models/audit.py` | Verdict enum + PII-light public + PII-bearing private models + `to_public_envelope` | ✓ VERIFIED | 267 lines. Closed 4-value `Verdict`; `PublicClaim`/`FactorVerdict`/`PublicAuditEnvelope` (`extra="forbid"`, ev_ firewall, relative-path guard); `PrivateFactorCard`/`PrivateAuditReport`; single down-projection seam. `FactorGroup` imported from `crawler.models.vault` (single source of truth). |
| `crawler/vault.py` (schema v3) | `audit_runs`+`factor_verdicts` tables, `aud_`/`ver_` minters, record/load helpers | ✓ VERIFIED | Additive `version < 3` migration (`PRAGMA user_version = 3`, `CREATE TABLE IF NOT EXISTS`); `ev_` and corpus ids in SEPARATE json columns; `record_factor_verdict` fail-closes on out-of-vocab verdict via `VaultError`. Migrates v2 in place (test suite green). |
| `crawler/auditor.py` | Fail-closed `audit_factor()` + `AuditGroundingError` | ✓ VERIFIED | 303 lines. Reuses frozen gate + Phase-30 quarantine + Phase-31 `crs_audit` math; no inlined volatile threshold; `AuditGroundingError` is the sole error surface. |
| `crawler/audit_report.py` | Vault-only `run_audit()`, fail-closed ordering | ✓ VERIFIED | 146 lines. Verdict computed BEFORE any write/persist; JSON+MD written under `output/crs-audit/` via `paths.resolve_within`; down-projects to PII-light envelope with vault-relative path. |
| `crawler/cli.py` (`vault audit`) | `_cmd_vault_audit` + subparser, PII-light envelope | ✓ VERIFIED | Reuses `command:"vault"` (pre-existing since 29-03); grounded verdict → `_vault_ok`, `AuditGroundingError` → `_vault_fail(INVALID_INPUT, exit 2)`; human detail → stderr. |
| `scripts/check_publish_safe.py` | crs-audit artifact coverage | ✓ VERIFIED | `output/crs-audit/` in `VAULT_SUBTREES`, `.json`/`.md` in `VAULT_ARTIFACT_EXTS`; `*.sqlite` in `VAULT_DB_SUFFIXES`. Checker exits 0 with 0 violations across 250 tracked files. |
| `crawler/CONTRACT.md` | `vault audit` result-shape docs | ✓ VERIFIED | Documents PII-light result keys + explicit "NO applicant values / NO ev_" + vault-only artifact note; 5-key envelope + `schema_version "1.0"` unchanged. |
| Tests (5 files) | Full matrix + boundary + perimeter | ✓ VERIFIED | `test_audit_models.py` (281), `test_audit_store.py` (247), `test_auditor.py` (351), `test_audit_report.py` (164), `test_vault_audit_cli.py` (127), `test_audit_pii_perimeter.py` (106) — all substantive, all green. |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `auditor.py` | `crs_rules.validate_registry` / `grounding.check_answer` | gate every consumed row before verdict | ✓ WIRED (auditor.py:94) |
| `auditor.py` | `vault.audit_eligible_values` | sole trusted evidence entry point | ✓ WIRED (auditor.py:270) |
| `auditor.py` | `crs_audit.to_clb/within_validity/score_factor` | deterministic threshold math over grounded rows | ✓ WIRED (auditor.py:208/221/172) |
| `audit_report.py` | `paths.resolve_within(candidate_root/output/crs-audit)` | containment-checked vault-only write | ✓ WIRED (audit_report.py:116-119) |
| `audit_report.py` | `vault.record_audit_run/record_factor_verdict/complete_audit_run` | persist trail only after a verdict | ✓ WIRED (audit_report.py:107/129/138) |
| `cli._cmd_vault_audit` | `audit_report.run_audit` + `contract.envelope("vault", ...)` | compute+write then emit PII-light result / error | ✓ WIRED (cli.py:1107/754) |
| `check_publish_safe.py` | `output/crs-audit/` | `VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS` coverage | ✓ WIRED (check_publish_safe.py:71,76) |
| `models/audit.py` | `crawler.models.vault.FactorGroup` | single source of truth import | ✓ WIRED (audit.py:44) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `PublicAuditEnvelope` (stdout) | `verdicts`/`claims`/`counts` | `to_public_envelope(PrivateAuditReport)` down-projection | Yes — real verdicts/claims flowed end-to-end (AT-RISK w/ 8 corpus claims, run id) | ✓ FLOWING |
| Vault report JSON/MD | `confirmed_value`, `evidence_ids`, `rule_citation_ids` | `audit_factor` reading `audit_eligible_values` + grounded rows | Yes — real `ev_` id + raw scores + benchmarks {listening:9, reading:9} written to vault only | ✓ FLOWING |
| `factor_verdicts` rows | `evidence_ids_json`, `rule_citation_ids_json` | `record_factor_verdict` after verdict | Yes — separate columns, round-trips via `list_factor_verdicts` (tests green) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Real registry subset grounds against real corpus | `validate_registry(_consumed_rows(reg,'core.language.first'), 'corpus/index.db')` | 0 violations, 0 gap rows | ✓ PASS |
| Green case (fully-satisfying) over real corpus | `vault audit --json ... --db corpus/index.db` | `ok:true`, verdict AT-RISK (reason `unresolved_conversion` — see Notes) | ✓ PASS |
| Never-green matrix (pending/low/stale/missing/below/wrong-test) | seed each mode → `vault audit --json` | GAP/GAP/GAP/GAP/AT-RISK/GAP — none SUBSTANTIATED | ✓ PASS |
| SUBSTANTIATED reachable in full write pipeline | `pytest test_audit_report.py -v` | 7 passed incl. SUBSTANTIATED write + fail-closed | ✓ PASS |
| SC4 PII perimeter (stdout vs vault) | e2e stdout scan vs on-disk report | no ev_/raw score/abs path on stdout; both in vault report | ✓ PASS |
| SC5 grounding failure (mismatched index) | `vault audit --json --db <mismatch>` | `ok:false`, exit 2, no report dir, 0 orphan rows | ✓ PASS |
| Publish-safe checker | `scripts/check_publish_safe.py` | 250 files, 0 violations, exit 0 | ✓ PASS |
| Phase-32 + frozen-path suites | `pytest` (audit* + vault* + json_contract + grounding + crs_audit) | 184 passed, 1 skipped | ✓ PASS |
| Whole suite (excl. slow test_dupaudit) | `pytest crawler/tests scripts/tests --deselect test_dupaudit` | 568 passed, 1 skipped, 184 subtests | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
|-------|---------|--------|--------|
| — | — | No `scripts/*/tests/probe-*.sh` convention exists in this project; phase docs declare none. | N/A (Step 7c SKIPPED) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| AUDIT-02 | 32-01/02/03/04/05 | `SUBSTANTIATED` only when proof+confirmed+threshold+grounded/cited (fail-closed; pending/low/stale never green) | ✓ SATISFIED | SC1/SC2/SC3/SC5 verified end-to-end + unit matrix |
| AUDIT-06 | 32-01/02/04/05 | Public output PII-light; full evidence-bearing reports vault-only | ✓ SATISFIED | SC4 verified end-to-end; publish-safe coverage; clean git tree |

No orphaned requirements — REQUIREMENTS.md maps only AUDIT-02 + AUDIT-06 to Phase 32, both declared across the plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No `TBD`/`FIXME`/`XXX`, no `TODO`/`HACK`, no stub returns in the new audit modules | — | — |

Note: two `placeholder` hits in `scripts/check_publish_safe.py` (lines 22/40) are pre-existing comments about a vendored third-party framework, not Phase-32 stubs.

### Frozen Trust-Path Integrity

- `contract.SCHEMA_VERSION == "1.0"` unchanged; 5-key envelope (`schema_version`, `ok`, `command`, `result`, `error`) intact on real output.
- `command:"vault"` REUSED (pre-existing since commit `4553aa1`, Phase 29-03) — no new command added to the allowlist.
- Auditor reuses `crs_rules.validate_registry` → frozen `grounding.check_answer`; no forked/re-implemented grounding or search primitive.

### Human Verification Required

None. This is a CLI / JSON-contract / persistence phase with no visual, real-time, or external-service surface. Every success criterion was verifiable — and was verified — programmatically by executing the shipped code path.

### Notes (Informational — not a gap)

**Real-corpus green verdict currently resolves to AT-RISK, by correct fail-closed design.** A fully-satisfying synthetic IELTS candidate audited against the REAL corpus returns `AT-RISK` with `reason_code = "unresolved_conversion"`, because the shipped Phase-31 IELTS conversion rule (`language/test-equivalency-charts.md#002`) only grounds **reading** and **listening** bands — `to_clb` returns `None` for **writing**/**speaking**, so the engine correctly refuses to fabricate an ungrounded CLB and declines to go green. This is the intended SC2/SC3 behavior (never green without a fully-resolved, grounded threshold), NOT a Phase-32 code defect: `SUBSTANTIATED` is proven reachable through both the pure engine and the full `run_audit` write pipeline with a complete grounded registry (passing tests). The conversion-table completeness is Phase-31 rule-data / Phase-33 fan-out scope, not a Phase-32 slice-code gap. The Phase-32 goal — run one complete slice from confirmed evidence + grounded rules and receive fail-closed, vault-only evidence-bearing output — is fully achieved.

### Gaps Summary

None. All five success criteria are objectively TRUE in the shipped code and verified by direct end-to-end execution against the real corpus. Both requirements (AUDIT-02, AUDIT-06) are satisfied. The full test suite (excluding the intentionally-scoped-out slow `test_dupaudit`) is green with no regressions to the frozen v3.x trust path, and the publish-safe checker reports zero violations.

---

_Verified: 2026-07-06T11:15:00Z_
_Verifier: the agent (gsd-verifier)_
