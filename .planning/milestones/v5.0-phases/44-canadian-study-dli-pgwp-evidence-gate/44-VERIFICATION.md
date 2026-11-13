---
phase: 44-canadian-study-dli-pgwp-evidence-gate
verified: 2026-07-20T02:00:07Z
status: passed
score: 25/25 must-haves verified
requirements_verified: [STUDY-02, STUDY-03, STUDY-04]
overrides_applied: 0
gaps: []
human_verification: []
gate_results:
  focused_phase_and_review_fix: "PASS — 170 passed, 150 subtests"
  full_crawler: "PASS — 1233 passed, 2 skipped, 1115 subtests"
  marked_conformance: "PASS — 124 passed, 1111 deselected, 321 subtests"
  safe_conformance_command: "PASS — 82 passed; SAFE-01 through SAFE-08"
  publish_safe: "PASS — 448 tracked files scanned, 0 violations"
  compile_and_ast: "PASS — 139 Python files parsed; crawler/scripts compile clean"
  final_review: "PASS — current 44-REVIEW.md is clean; independent gates found no blocker or warning"
skips:
  - "Full suite: live IRCC endpoint contract is intentionally offline unless PR_LIVE_DLI=1."
  - "Full suite: crawl4ai-only deepcrawl constants test skipped because optional crawl4ai is absent."
---

# Phase 44: Canadian-Study DLI/PGWP Evidence Gate Verification Report

**Phase Goal:** Close the credential-only study false-green by gating Canadian-study evidence on candidate-specific transient DLI/PGWP rows, grounded credential/R73 rules, and snapshot freshness/provenance while keeping intake and decisions fail-closed.

**Verified:** 2026-07-20T02:00:07Z  
**Status:** passed  
**Re-verification:** No — initial verification

## Goal Achievement

The three ROADMAP success criteria are covered by the 25 deduplicated PLAN truths below. Evidence comes from current code and fresh verifier-run tests, not SUMMARY claims.

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Six study fields are captured as pending values linked only to `review.study`. | ✓ VERIFIED | `dlifields.py:13-20`; `extraction.py` route; real extraction tests at `test_study_review.py:202-266`. |
| 2 | Each field is independently confirmable, correctable, or rejectable. | ✓ VERIFIED | One-value API in `confirm.py:135-155`; independent state test at `test_study_review.py:268-296`. |
| 3 | Only candidate-scoped, confirmed/corrected, quality-ok, five-key-current values cross eligibility. | ✓ VERIFIED | Candidate/factor/field SQL and `is_audit_eligible` call at `study_review.py:160-188`; predicate at `vault.py:1119-1139`. |
| 4 | Unknown DLI, credential, status, and non-string DLI values fail closed. | ✓ VERIFIED | Closed normalizers at `dlifields.py:77-101`; normalization/type matrices at `test_study_review.py:109-179` and conformance lines 631-656. |
| 5 | Study extraction cannot contaminate any CRS factor. | ✓ VERIFIED | `review.study` is outside `FULL_GRID_FACTORS`; full-factor sweep includes `core.age`, `core.education`, and `additional.study` (`test_study_review.py:232-265`). |
| 6 | One resolver applies explicit override before environment and returns positive int or `None`. | ✓ VERIFIED | `snapshot_policy.py:13-31`; fresh spot-check returned `30 None None None`. |
| 7 | Missing, blank, non-int, bool, zero, and negative max-age have no default. | ✓ VERIFIED | Resolver implementation and config matrix (`test_freshness_staleness.py`, `test_conformance_v5...py:966-1000`). |
| 8 | Resolution is CLI-only; `review_study` receives and preserves the caller value. | ✓ VERIFIED | Sidecar has no `snapshot_policy` import/call; exact value reaches `probe_snapshot` at `study_review.py:654-655`; CLI passes `max_age_days=max_age` at `cli.py:1609-1614`. |
| 9 | Max age is operational configuration, not an IRCC claim or inlined study rule. | ✓ VERIFIED | Module contract at `snapshot_policy.py:1-6`; no freshness registry row; no-inline tests passed. |
| 10 | Invalid/stale snapshot state is refused before evidence reads or report publication. | ✓ VERIFIED | Report invalidation first, then type and health guards before registry/evidence at `study_review.py:640-675`; ordering/failure-injection tests passed. |
| 11 | Every candidate DLI/PGWP chunk becomes one transient in-memory `RuleRow` gated with static rows. | ✓ VERIFIED | Dynamic construction at `study_review.py:414-513`; temporary registry and single gate call at lines 741-751; no YAML/persistence path. |
| 12 | `gate_subset` applies both registry validation and retrieve-what-you-cite. | ✓ VERIFIED | `auditor.py:75-108`; quote/marker/family/title/citation tamper matrix at conformance lines 780-811. |
| 13 | DLI, credential tier, completion status, start date, and end date are conjunctively required. | ✓ VERIFIED | `_REQUIRED_FIELDS` at `study_review.py:67-73`; missing/invalid/reversed matrix at conformance lines 501-534. |
| 14 | Canonical exact resolution is discovery only; every #000/#001+ chunk supplies a gated citation. | ✓ VERIFIED | Canonical DB rows loaded at `study_review.py:244-250`; exact source projection comparison at lines 338-353; always-run three-chunk membership/tamper matrix passed. |
| 15 | Current-only designation, PGWP Details, and PGWP No never green or imply program eligibility. | ✓ VERIFIED | Fail-closed result derivation at `study_review.py:533-554`; Yes/Details/No real candidates pass with only AT-RISK reasons. |
| 16 | Public `as_of` is the common nonempty crawl date of every consumed chunk. | ✓ VERIFIED | Equality at `study_review.py:724-739`; real index shows both chunks for all three candidates at `2026-07-16T18:08:26Z`; missing/mismatch returns null. |
| 17 | Public output is exactly the six safe fields; evidence and citations remain private. | ✓ VERIFIED | `PUBLIC_FIELDS` at `study_review.py:49-56`; private report at lines 557-593; whole-envelope PII tests passed. |
| 18 | The real `additional.study` seam is credential-only and never substantiates or scores. | ✓ VERIFIED | `decide_study` has only GAP/AT-RISK branches and `substantiated_points=None` (`additional.py:169-203`); real audit-seam tests passed. |
| 19 | CLI resolves once, preflights index/snapshot, opens the vault last, and preserves the override. | ✓ VERIFIED | `cli.py:1584-1614`; ordering spies and focused CLI suite passed. Stale report invalidation intentionally precedes config to prevent stale evidence reuse. |
| 20 | Config/index/snapshot refusal exits nonzero and creates no candidate/database/report artifact. | ✓ VERIFIED | Complete preflight matrix at conformance lines 962-1140; fresh tests passed. |
| 21 | CLI emits the five-key envelope with result keys exactly `PUBLIC_FIELDS` and no private markers. | ✓ VERIFIED | CLI/privacy E2E and conformance lines 1144-1177 passed. |
| 22 | Complete negative evidence matrix never returns `SUBSTANTIATED` or nonzero points. | ✓ VERIFIED | Pending/rejected/corrected, five stale keys, quality, malformed types, dates, current-only, grounding and unwired cases passed. |
| 23 | Multi-candidate and multi-chunk fixtures prove candidate-specific transient rows and shared-gate tamper refusal. | ✓ VERIFIED | UofT Yes, Envolée Details, Eston No plus synthetic #000/#001/#002 canonical fixture all passed. |
| 24 | DLI family/index/goldens are read-only and deterministically fingerprinted. | ✓ VERIFIED | Runtime family and DB pre/post fingerprints, read-only SQLite URI, regenerated golden bytes, and approved source hashes passed. |
| 25 | Vault schema, dependencies, lock, frozen source, and no-network/no-Phase-45 boundaries remain fixed. | ✓ VERIFIED | Schema v3/hash pin, exact three dependencies, pyproject/lock hashes, AST network scan, and source pins passed; no MEC/Phase-45 implementation found. |

**Score:** 25/25 truths verified

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `crawler/dlifields.py` | Closed study vocabulary/normalizers | ✓ VERIFIED | Substantive, imported by extraction and sidecar, fail-closed tests pass. |
| `crawler/models/vault.py` | Six typed field names | ✓ VERIFIED | Vocabulary parity test passes; no DDL change. |
| `crawler/extraction.py` | `study_proof` → inert `review.study` | ✓ VERIFIED | Producer parity and full-grid isolation pass. |
| `crawler/snapshot_policy.py` | No-default positive-int resolver | ✓ VERIFIED | CLI-wired once; static no-inline gate passes. |
| `crawler/study_review.py` | Grounded sidecar/private report | ✓ VERIFIED | 793 substantive lines; candidate data flows through eligibility, canonical snapshot binding, shared gate, and private publication. |
| `crawler/auditor.py` | Authoritative validate/retrieve gate | ✓ VERIFIED | Both trust primitives invoked for every non-gap row. |
| `crawler/data/crs_rules/study_dli.yaml` | Static current-only DLI fixture and grounded R73 row | ✓ VERIFIED | R73 cites exact IRPR chunk; static UofT row excluded from runtime candidate registries. |
| `crawler/auditors/additional.py` | Credential-only no-green decider | ✓ VERIFIED | No study `SUBSTANTIATED` branch. |
| `crawler/cli.py` | Offline `vault study-review` boundary | ✓ VERIFIED | Registered and help-visible; config/index/snapshot/vault order tested. |
| Phase 44 focused/conformance tests | Negative, privacy, provenance, durability and freeze proof | ✓ VERIFIED | Fresh focused, full, and conformance runs all green. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `extraction._FIELD_SPECS["study_proof"]` | `dlifields.STUDY_FIELDS` | Import-time set equality | ✓ WIRED | Tests prove exact six-field parity. |
| `study_proof` | `review.study` | Locked doc-type factor route | ✓ WIRED | Overrides cannot redirect to a CRS factor. |
| CLI | `snapshot_policy.dli_snapshot_max_age_days` | One boundary call | ✓ WIRED | Invalid config stops before probes/open. |
| CLI | `study_review.review_study` | Exact `max_age_days` keyword | ✓ WIRED | Same integer reaches sidecar snapshot probe. |
| `review_study` | canonical DLI source/index | Manifest, document projection and ordered DB-row comparison | ✓ WIRED | Extra/missing/reordered/rehashed/metadata-tampered chunk cases refuse. |
| `review_study` | `auditor.gate_subset` | One temporary static+dynamic Registry | ✓ WIRED | Every consumed chunk has one row/citation. |
| `gate_subset` | grounding/search trust path | `validate_registry` + `retrieve_what_you_cite` | ✓ WIRED | Tampering refuses through the shared gate. |
| confirmation/audit | one registry snapshot/fingerprint | Validated loader → confirmation → eligibility → report metadata | ✓ WIRED | CLI loads once; direct APIs recompute/verify supplied Registry; mismatch refuses before evidence/write. |

## Data-Flow Trace

| Artifact | Data | Source | Status |
|---|---|---|---|
| Study extraction | Six pending values | Private imported `study_proof` document | ✓ FLOWING |
| Study sidecar | Eligible candidate values | Candidate/document/factor-scoped vault query + five-key predicate | ✓ FLOWING |
| Dynamic rules | Current DLI/PGWP observations | Canonical source document and read-only indexed rows | ✓ FLOWING |
| Public result | Status/reason/counts/as-of | Gated rows and common chunk provenance | ✓ FLOWING |
| Private report | Applicant values/evidence/citations | Same gated run, atomically published under candidate vault | ✓ FLOWING |

## Review-Fix Closure

- **Registry snapshot/fingerprint:** `load_registry_snapshot` strictly parses every registry YAML, requires complete grid plus usable auxiliary rows, and fingerprints the same in-memory Registry. Confirm, fields, CLI audit, direct audit, eligibility, and persisted metadata are bound to that fingerprint.
- **Round provenance:** candidate-scoped explicit rounds fail before evaluation/write; full persisted audits resolve the latest round once and carry the same ID through cutoff, private JSON/Markdown, and `audit_runs`.
- **Persistence/durability:** study reports durably invalidate stale `latest.json`, fsync staged content, atomically replace, fsync the directory, and remove an unadvertised target after post-replace failure. CRS reports stage/fsync both files, replace both, fsync the directory, then commit SQLite; failure-injection tests cover rollback, collision restoration, post-commit confirmation, and control-flow exceptions.
- **Final review:** `44-REVIEW.md` is clean. Independent AST/debt scans, compile, focused tests, full suite, conformance, publish-safe, and `git diff --check` found no current blocker or warning.

## Behavioral Spot-Checks and Gates

| Check | Result | Status |
|---|---|---|
| Focused Phase 44 + review-fix tests | 170 passed, 150 subtests | ✓ PASS |
| Fresh full crawler suite | 1233 passed, 2 intentionally skipped, 1115 subtests | ✓ PASS |
| Marked conformance | 124 passed, 321 subtests | ✓ PASS |
| Canonical SAFE conformance command | 82 passed; SAFE-01..08 PASS | ✓ PASS |
| Publish-safe | 448 tracked files, 0 violations | ✓ PASS |
| Compile/AST/debt scan | 139 Python files parsed; 0 TBD/FIXME/XXX; compile clean | ✓ PASS |
| CLI registration/resolver | `vault study-review --help`; resolver `30/None/None/None` | ✓ PASS |

### Honest Skips

The full suite's two skips are intentional and unrelated to Phase 44 deterministic behavior:

1. Live IRCC DLI schema contract requires opt-in `PR_LIVE_DLI=1`; verification remained offline.
2. One optional `crawl4ai`-only deepcrawl test skipped because that optional dependency is absent.

No Phase 44 focused or conformance test skipped. Probe execution was skipped because no Phase 44 probe script is declared or present.

## Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| STUDY-02 | ✓ SATISFIED | Inert six-field pending intake, per-field decisions, five-key eligibility, factor isolation. |
| STUDY-03 | ✓ SATISFIED | Exact candidate DLI/PGWP transient rows plus grounded credential/R73 shared gate; credential-only seam never green. |
| STUDY-04 | ✓ SATISFIED | No-default freshness bound, index/family/candidate provenance, stale/refusal behavior, unconditional historical-designation AT-RISK cap. |

No Phase 44 requirement is orphaned. SAFE-11/12 remain explicitly assigned to Phase 46 and MEC-01..04 to Phase 45; no later-phase work was introduced.

## Anti-Patterns

No blocker debt markers, stubs, placeholder handlers, second validation engine, persisted dynamic rules, live audit-time network path, new dependency, Phase-45 wiring, or public PII leak was found. Parser helpers returning empty lists are deliberate fail-closed signals and are covered by negative tests.

## Human Verification Required

None. The requested behavior is deterministic and covered by current code inspection, failure injection, real local corpus/index tests, fresh full-suite execution, and conformance. No visual, real-time, or external-service UAT is needed.

## Gaps Summary

None. All 25 deduplicated must-haves and STUDY-02 through STUDY-04 are verified. The phase goal is achieved without marking the phase complete.

---

_Verified: 2026-07-20T02:00:07Z_  
_Verifier: the agent (gsd-verifier)_
