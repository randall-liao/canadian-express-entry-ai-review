---
phase: 31-grounded-crs-rule-registry-deterministic-logic
verified: 2026-07-06T10:12:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
requirements_covered: [RULE-01, RULE-02, RULE-03, RULE-04, RULE-05]
---

# Phase 31: Grounded CRS Rule Registry & Deterministic Logic — Verification Report

**Phase Goal:** Auditors have a PII-free, corpus-grounded CRS rule registry and deterministic CRS logic before any factor verdicts are implemented.
**Verified:** 2026-07-06T10:12:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

Verification was performed goal-backward against the **actual shipped code and the real corpus** (`corpus/index.db`), not against SUMMARY.md claims. Every success criterion was independently re-derived by running the engine/logic directly, resolving cited chunks against the corpus, and confirming each verbatim quote is a true substring of its cited chunk. Grounding is **real, not fabricated** — confirmed across all 31 rows / 38 citations.

### Observable Truths

| # | Truth (ROADMAP Success Criterion) | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Every CRS factor group has registry rows capturing accepted proof types, validity windows, issuers, thresholds, caps, admissibility predicates — each with a resolving corpus citation + verbatim quote. | ✓ VERIFIED | 31 rows across all 4 groups (core 14, spouse 3, transfer 8, additional 6). check_types: admissibility×5, threshold×3, cap×3, points×16, conversion×2, policy×2. Grounded validity windows (ECA 1825d=5y, language 730d=2y), grounded caps (spouse-lang 20, edu 50, foreign-work 50, total 100), accepted-test/TEER enums, ECA-designated-org issuer admissibility. **All 38 citations resolve; every quote is a true substring of its cited chunk (independently verified).** |
| 2 | Every registry rule validates through the shipped `search`/`--cite`/grounding gate; static checks reject volatile CRS thresholds hard-coded in auditor prose. | ✓ VERIFIED | `validate_registry(load_registry(), corpus/index.db)` → **31/31 grounded, 0 violations** (run independently). grep confirms `grounding.check_answer` + `searchindex.search`/`resolve` are CALLED, never forked (no `check_answer`/`resolve`/`normalize` re-impl in crs_rules/crs_audit). `no_inlined_volatile_rules`: crs_audit.py=[], registry YAML=[]; **positive controls** (planted markdown `200 points`/`CLB 9` and Python `600` literal) are FLAGGED → gate is non-vacuous. |
| 3 | A coverage report shows the full CRS grid (4 groups) with no missing required rule rows. | ✓ VERIFIED | `coverage_report` → `complete=True`; every group present==required, 0 missing, 0 gaps. Committed `COVERAGE.md` is **byte-identical** to fresh `python -m crawler.crs_rules` output, PII-free, 23 required labels all `present`, Status: COMPLETE. |
| 4 | Deterministic Python computes CLB/NCLC conversion, date math, duration aggregation, spouse mode, transferability caps, cutoff comparison from grounded rule rows. | ✓ VERIFIED | `crs_audit.py` reads every value from `machine_check`/volatility payloads (no literals). Direct real-registry runs: `to_clb('IELTS General Training','reading',7.0)`→9, 6.5→None, `CELPIP-General` reading 9→9, unknown→None; `apply_transferability_caps({80,90})`→50/50/total 100 from grounded cap rows; `age_on_date`/`within_validity`/`aggregate_work` implemented from grounded windows. 20 golden fixtures pass (CLB 8/9 edge, spouse vs no-spouse, 50/50/100, validity expiry, 30h no-overcount, overlap no-double-count). |
| 5 | Non-zero arranged-employment additional-CRS claim → AT-RISK/0 unless ITA-era corpus rules ground a legacy/exception case (then AT-RISK/manual, never auto-green); unclaimed → N/A. | ✓ VERIFIED | Direct real-registry `arranged_employment_guard`: post-repeal 200-claim → `AT-RISK/0` citing `guidance/job-offer.md#001`; pre-repeal 50-claim → `AT-RISK/points=None` (manual) citing `ministerial-instructions/amendment-2017-2.md#006`; unclaimed(0) → `N/A`; boundary on 2025-03-25 → `AT-RISK/0` (effective_to exclusive). Current & legacy ground **different source families** (guidance vs ministerial-instructions) → no cross-grounding. Never auto-green. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `crawler/models/crs_rules.py` | Pydantic v2 PII-free rule-row models | ✓ VERIFIED | Strict `extra=forbid`, Literal enums, `relpath#ordinal` citation shape, citation_index range check, dup rule_id guard, `gap`/`gap_reason` fields. Imports `FactorGroup` from vault (single source). No applicant/PII field. |
| `crawler/crs_rules.py` | Loader + gate reuse + retrieve-what-you-cite + coverage + static check | ✓ VERIFIED | Exports load_registry, validate_registry, retrieve_what_you_cite, coverage_report, no_inlined_volatile_rules, row_to_answer, REQUIRED_RULE_IDS. Reuses frozen gate/resolver verbatim (grep-confirmed). |
| `crawler/crs_audit.py` | Deterministic CRS math reading grounded rows | ✓ VERIFIED | to_clb, age_on_date, within_validity, aggregate_work, score_factor, apply_transferability_caps, compare_to_cutoff, arranged_employment_guard — all read registry payloads; self-scan clean. |
| `crawler/data/crs_rules/{core,spouse,transferability,additional}.yaml` | Grounded rule rows, 4 groups | ✓ VERIFIED | 31 rows, 0 gaps, all ground against real corpus; span 8 distinct corpus files / multiple source families. |
| `crawler/data/crs_rules/COVERAGE.md` | Committed PII-free full-grid coverage | ✓ VERIFIED | Byte-identical to fresh gen, 23 labels present, COMPLETE, publish-safe. |
| `crawler/tests/test_crs_*.py` (6 files) | Corpus-gated conformance + always-runs synthetic mirrors | ✓ VERIFIED | 169 tests + 62 subtests pass; corpus-gated classes run (not skipped) on this host. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `crs_rules.py` | `grounding.py:check_answer` | `row_to_answer → check_answer` | ✓ WIRED | Called at lines 171, 253; no forked substring/normalize. |
| `crs_rules.py` | `searchindex.py:search/resolve` | retrieve_what_you_cite selection | ✓ WIRED | Called at lines 200, 205. |
| `core.yaml` | `language/test-equivalency-charts.md` | CLB/NCLC conversion rows cite equivalency chart | ✓ WIRED | conversion.ielts/celpip cite `language/test-equivalency-charts.md#002` (quote verified). |
| `additional.yaml` | `guidance/job-offer.md` | repeal row cites 2025-03-25 removal quote | ✓ WIRED | `additional.job_offer.current` cites `guidance/job-offer.md#001` "We no longer give points for job offers" (verified substring). |
| `crs_audit.py` | `crs_rules.py:load_registry` | reads grounded rows, never literals | ✓ WIRED | `default_registry()` + all functions take Registry. |
| `crs_audit.py` | `crs_rules.py:no_inlined_volatile_rules` | self-scan (RULE-02) | ✓ WIRED | Self-scan returns []. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| registry (31 rows) | citations[].quote | `corpus/index.db` chunks via searchindex.resolve | Yes — 38/38 quotes are true substrings of resolved chunks | ✓ FLOWING |
| crs_audit outputs | machine_check payloads | grounded RuleRow rows | Yes — to_clb/caps/guard driven by real grounded values | ✓ FLOWING |
| COVERAGE.md | coverage_report(registry) | live registry | Yes — byte-identical to fresh gen | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Whole registry grounds | `validate_registry(load_registry(),'corpus/index.db')` | total 31, grounded 31, violations 0 | ✓ PASS |
| retrieve-what-you-cite agrees + grounds | `retrieve_what_you_cite(...)` | 31/31 agree, 31/31 ground; 0 wrong-chunk | ✓ PASS |
| Every quote is a true substring | independent resolve + normalized substring over all 38 citations | 0 fabricated / 0 mismatch | ✓ PASS |
| Coverage complete | `coverage_report(...)['complete']` | True (0 missing, 0 gaps) | ✓ PASS |
| Static gate non-vacuous | positive-control markdown + python | flagged points_literal/clb_benchmark | ✓ PASS |
| crs_audit no-inline self-scan | `no_inlined_volatile_rules(['crawler/crs_audit.py'])` | [] | ✓ PASS |
| Arranged-employment guard (SC5) | direct real-registry calls | post-repeal→AT-RISK/0; pre-repeal→AT-RISK/None; unclaimed→N/A | ✓ PASS |
| to_clb from grounded bands | direct real-registry calls | 7.0→9, 6.5→None, unknown→None | ✓ PASS |
| Transferability caps | `apply_transferability_caps({80,90})` | 50/50/total 100 | ✓ PASS |
| publish-safe | `scripts/check_publish_safe.py` | 235 files, 0 violations | ✓ PASS |
| Phase-31 tests + frozen regressions | `pytest test_crs_* test_grounding test_searchindex` | 169 passed, 62 subtests | ✓ PASS |
| Full suite (excl. slow test_dupaudit) | `pytest crawler/tests scripts/tests` | 513 passed, 1 skipped (unrelated crawl4ai), 184 subtests | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared for this phase; verification uses the pytest suites + direct engine invocation above. (SKIPPED — no probe scripts.)

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| RULE-01 | 31-01/02/03 | PII-free per-factor admissibility rules with citation + verbatim quote | ✓ SATISFIED | 31 grounded rows across 4 groups; proof types/validity/issuers/thresholds/caps/admissibility all present; every quote verified as true corpus substring. |
| RULE-02 | 31-01/04/05 | Rules validate through shipped gate; static check rejects inlined volatile thresholds | ✓ SATISFIED | 31/31 grounded via `grounding.check_answer`; static gate clean on registry+crs_audit, non-vacuous positive controls. |
| RULE-03 | 31-01/02/03/05 | Full CRS grid coverage across 4 groups | ✓ SATISFIED | coverage complete=True; COVERAGE.md 23 labels present, 0 missing/gaps, drift-guarded. |
| RULE-04 | 31-04 | Deterministic CLB conversion/date/duration/spouse/caps/cutoff from grounded rows | ✓ SATISFIED | crs_audit.py reads grounded payloads; 20 golden fixtures pass; direct real-registry runs correct; module has no inlined literal. |
| RULE-05 | 31-03/04 | Non-zero job-offer claim → AT-RISK/0 unless grounded ITA-era legacy (then manual, never green) | ✓ SATISFIED | Guard fail-closed verified against real registry; current/legacy ground different source families; boundary correct. |

No ORPHANED requirements: REQUIREMENTS.md maps exactly RULE-01..05 to Phase 31, all claimed by plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `crawler/models/crs_rules.py` | 203 | word "placeholder" in docstring | ℹ️ Info | Prose describing the gap-row mechanism; not a stub. |
| `crawler/tests/test_crs_rules.py` | 180 | "placeholder ungroundable text zzz" | ℹ️ Info | Deliberate NEGATIVE test fixture proving fail-closed; not a stub. |

No `TBD`/`FIXME`/`XXX` debt markers, no `TODO`/`HACK`, no stub returns, no `NotImplementedError` in any phase file. Frozen v3.x trust path (`grounding.py` @ Phase 25, `searchindex.py` @ Phase 24, `CONTRACT.md` @ Phase 30) is unchanged — no Phase-31 commit touches it; the registry reuses it (no new trust path).

### Human Verification Required

None. This phase is entirely deterministic Python + PII-free data with corpus grounding — no UI, real-time behavior, external service, or visual/UX surface. All five success criteria are objectively machine-verifiable and were independently verified against the real corpus.

### Gaps Summary

No gaps. Every ROADMAP success criterion (SC1–SC5) and every requirement (RULE-01–05) is objectively true in the shipped code and real corpus data. Grounding was independently confirmed real (not fabricated): all 38 citations resolve to real corpus chunks and every verbatim quote is a true substring of its cited chunk. The full CRS grid is complete with zero coverage gaps, the deterministic math reads exclusively from grounded rows, the arranged-employment guard is fail-closed (never auto-green), the static no-inline gate is non-vacuous, the registry is PII-free/publish-safe and separate from the vault, and the frozen v3.x trust path is reused unchanged. Full test suite green with no regressions.

---

_Verified: 2026-07-06T10:12:00Z_
_Verifier: the agent (gsd-verifier)_
