---
phase: 33-full-modular-crs-auditor-pack
verified: 2026-07-06T13:18:37Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "SC3 / AUDIT-04 — spouse-mode core.language.first/.second cards now carry non-blank substantiated_points and score_delta (116 / delta 8 for the CLB-9 fixture)."
    - "SC4 / AUDIT-05 — the substantiated CRS total now INCLUDES the with-spouse language points (no ~116-point undercount); total-vs-cutoff arithmetic is correct in spouse mode."
  gaps_remaining: []
  regressions: []
deferred: []
---

# Phase 33: Full Modular CRS Auditor Pack — Verification Report (RE-VERIFICATION)

**Phase Goal:** Applicant can audit every claimed CRS factor through four context-light modules and see substantiated points plus ITA cutoff risk.
**Verified:** 2026-07-06T13:18:37Z
**Status:** passed
**Re-verification:** Yes — after gap closure (plan 33-07). Prior report (2026-07-06T12:47:11Z) found SC3/SC4 spouse-mode gaps; this run confirms both are closed and nothing regressed.

## Goal Achievement

I re-verified the two previously-failing criteria and regression-checked the three previously-passing ones by driving an INDEPENDENT synthetic spouse-mode full-profile candidate through `run_full_audit_report` / `vault audit --all` against the REAL `corpus/index.db`, and re-deriving every number from the emitted `PrivateFactorCard`s (not from SUMMARY claims or the committed test assertions). The single scoped `crawler/crs_audit.py::score_factor` defect that blocked SC3 and SC4 for spouse-mode candidates is fixed at the root: the mode column is now selected by grounded LABEL (`with_spouse` / `without_spouse`) instead of the `(factor_group == "spouse_common_law") != spouse_mode` row filter that dropped the owning `core_human_capital` language row in spouse mode.

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | SC1 — every claimed/applicable factor → exactly one `SUBSTANTIATED`/`GAP`/`AT-RISK`/`N/A` verdict with grounded rule citation + private evidence pointer | ✓ VERIFIED (no regression) | Independent E2E spouse-mode `vault audit --all`: 18/18 grid cards, 18 unique ids, 0 dupes, every verdict in the closed vocab, every applicable (non-N/A) card carries ≥1 `rule_citation_ids` entry; document-backed SUBSTANTIATED language card carries `evidence_ids=['ev_df1b9c839e69']`. `test_every_conversion_row_grounds` + `TestFullGridIntegration::test_sc1_one_verdict_per_factor` pass. |
| 2 | SC2 — four separate context-light modules through frozen v3.x primitives, no new trust path | ✓ VERIFIED (no regression) | `crawler/auditors/{core,spouse,transferability,additional}.py` all present and registered; the spine reuses the SHIPPED `crs_rules.validate_registry` (→ `grounding.check_answer`) frozen gate (`crawler/auditor.py:82`). `crawler/grounding.py` last touched `01aa29b` (Phase 25, 2026-06-21) — UNCHANGED by any Phase-33 commit. 33-07 touched only `crawler/crs_audit.py` + two test files (no trust-boundary code). |
| 3 | SC3 / AUDIT-04 — factor cards show all six fields (claimed, confirmed, substantiated points, score delta, evidence pointer, rule citation) INCLUDING spouse mode | ✓ VERIFIED (was FAILED) | Independent spouse-mode E2E: `core.language.first` = SUBSTANTIATED, `substantiated_points=116`, `score_delta=8`, `claimed_value=9`, `confirmed_value`={IELTS benchmarks CLB 9}, `evidence_ids=['ev_df1b9c839e69']`, `rule_citation_ids` populated — **zero blank/None fields**. Unit over real registry: `score_factor('core.language.second',9,spouse=True)=6` (second-language spouse column also resolves). Previously blank → now populated. |
| 4 | SC4 / AUDIT-05 — substantiated total vs ITA cutoff surfaces risk without legal advice; correct arithmetic in spouse mode | ✓ VERIFIED (was FAILED) | Independent spouse-mode E2E: `substantiated_total=944`, independent re-sum of SUBSTANTIATED points = 944 (self-consistent). Breakdown: age 100 + education 28 + **language 116** + nomination 600 + transfer (50+50+0) = 944. Cutoff 500 → `cutoff_delta=444` (944−500), `meets_cutoff=True`. Language points ARE in the total (previously undercounted to 0). No-legal-advice wording intact (`test_markdown_has_cutoff_line_no_legal_advice`, `test_sc4_cutoff_and_no_legal_advice` pass). |
| 5 | SC5 — multi-document aggregation, spouse/principal ownership, work-interval conflicts, transferability dependencies → factor-level GAP/AT-RISK, not hidden document-level passes | ✓ VERIFIED (no regression) | Independent spouse-mode E2E: `core.work` = GAP `below_threshold` (two OVERLAPPING full-time letters aggregated by union, no double-count, ~2y < claimed 3y); `transfer.education_work`/`transfer.foreign_work` = GAP (unmet `core.work` component dependency); `spouse.language` = N/A — principal IELTS evidence did NOT leak into the spouse-owned factor (ownership separation → no hidden pass). Committed `test_spouse_factor_with_only_principal_evidence_is_gap` + `test_sc5_*` pass. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `crawler/crs_audit.py::score_factor` | mode-aware grounded-points selection by label; core rows applied in both modes; `spouse_common_law` gated to spouse mode; `factor_ids[0]` ownership + cap clamp preserved; no inlined literal | ✓ VERIFIED (fixed) | Real-registry: `first@9` → 29 (spouse) / 31 (no-spouse); `second@9` → 6 both modes; `first@3` → None (fail-closed). Diff `d173ffa` preserves the ownership guard verbatim, swaps the mode filter for `spouse_common_law and not spouse_mode`, adds label-based column pick, keeps cap clamp + `None` fallback. |
| `crawler/auditors/{core,spouse,transferability,additional}.py` | four registered context-light modules | ✓ VERIFIED | All four present; module test suites green; frozen gate reused, no new trust path. |
| `crawler/tests/test_crs_audit.py` | unit regression: spouse-column selection, spouse_common_law gating, no transferability leak, unmatched-level None | ✓ VERIFIED | `TestScoreFactorRealRegistry` + new `TestSpouseMode` cases pass; existing `test_spouse_vs_no_spouse_diverge` (31 vs 5) and `test_unknown_value_returns_none` untouched and green. |
| `crawler/tests/test_full_audit_integration.py` | E2E spouse-mode assertion: cards carry with-spouse points and total includes them; no-spouse unchanged | ✓ VERIFIED | `TestSpouseModeLanguagePoints` (3 tests) green over real corpus; independently reproduced. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `crawler/auditors/core.py` | `crawler/crs_audit.py` | `_sum_points` → `score_factor` per ability | ✓ WIRED | Spouse-mode language cards now resolve grounded with-spouse points end-to-end. |
| `crawler/crs_audit.py` | grounded `points_by_level` (`with_spouse`/`without_spouse`) | label selection inside owning core row | ✓ WIRED | `score_factor` picks `clb9_with_spouse=29` in spouse mode, `clb9_without_spouse=31` in no-spouse. |
| `crawler/auditor.py` | `crawler/crs_rules.py` (frozen gate) | `validate_registry` (reused, not forked) | ✓ WIRED | `grounding.py` unchanged; no new trust path. |
| `crawler/auditor.py` | `crawler/crs_audit.py` | `compare_to_cutoff` on substantiated total | ✓ WIRED | `cutoff_delta=444`, `meets_cutoff=True` from a total that now includes language. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| spouse-mode language card | `substantiated_points` | `score_factor` over grounded core row (label-selected `clb9_with_spouse=29`) | Yes — 4×29=116 (was None) | ✓ FLOWING |
| spouse-mode report | `substantiated_total` | sum of SUBSTANTIATED card points | Yes — 944 includes language 116 (was undercounted) | ✓ FLOWING |
| no-spouse language card | `substantiated_points` | `score_factor` label-selected `clb9_without_spouse=31` | Yes — 4×31=124, delta 0 | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite (Phase 33 + 29–32 regressions + frozen path, excl. test_dupaudit) | `pytest crawler/tests scripts/tests --deselect crawler/tests/test_dupaudit.py -q` | 634 passed, 1 skipped, 26 deselected, 195 subtests | ✓ PASS |
| `score_factor` spouse column (real registry) | `score_factor('core.language.first',9,True/False,reg)` | 29 / 31 | ✓ PASS |
| `score_factor` second language + fail-closed | `second@9`=6 both modes; `first@3`=None | 6 / 6 / None | ✓ PASS |
| Spouse-mode E2E language card (real corpus) | independent `run_full_audit_report` | SUBSTANTIATED, points=116, delta=8, six fields populated | ✓ PASS |
| Spouse-mode substantiated total | independent re-sum vs report | total=944, self-consistent, cutoff_delta=444 | ✓ PASS |
| No-spouse language (regression) | clean-vault `run_full_audit_report` | SUBSTANTIATED, points=124, delta=0 | ✓ PASS |
| Arranged-employment never auto-green | seed `additional.job_offer` | AT-RISK, points=0, delta=50 | ✓ PASS |
| Sibling truthful fail-closed GAP | seed `additional.sibling` no doc | GAP `missing_evidence` | ✓ PASS |
| `no_inlined_volatile_rules(['crawler/crs_audit.py'])` | ASVS L1 integrity self-scan | `[]` (clean) | ✓ PASS |
| publish-safe scan | `scripts/check_publish_safe.py` | 277 files, 0 violations | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes are declared for this phase. Verification was performed via the full pytest suite + an INDEPENDENT end-to-end audit driver (seeded synthetic spouse-mode full profile vs real corpus, re-derived from emitted cards). Step 7c: N/A.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| AUDIT-01 | 33-01…06 | Verdict per claimed factor with grounded citation + private evidence pointer | ✓ SATISFIED | 18 factors, one verdict each, closed vocab, grounded citations + `ev_` pointers. |
| AUDIT-03 | 33-01…05 | Four context-light modules reusing frozen primitives, no new trust-path code | ✓ SATISFIED | Four registered modules; frozen gate reused; `grounding.py` unchanged. |
| AUDIT-04 | 33-01, 33-06, 33-07 | Factor cards show six fields | ✓ SATISFIED | All six fields populated INCLUDING spouse mode (116 / delta 8). Gap closed by 33-07. |
| AUDIT-05 | 33-01, 33-06, 33-07 | Substantiated total vs ITA cutoff, no legal advice | ✓ SATISFIED | Total (944) includes spouse-mode language points; `cutoff_delta=444`; no legal-advice wording. Gap closed by 33-07. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No `TBD`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` markers in any 33-07 file | ℹ️ Info | Clean; the prior 🛑 Blocker (`score_factor` spouse-mode column filter) is RESOLVED — spouse and core rows are now both visited and selected by label. |
| `crawler/crs_audit.py` | `score_factor` | scanned by `no_inlined_volatile_rules` | ℹ️ Info | Self-scan returns `[]`; the fix carries no inlined numeric literal (docstring uses generic `*_with_spouse`/`*_without_spouse` forms, avoiding the `\b(?:CLB|NCLC)\s*\d+` trip). |

### Human Verification Required

None — every criterion was re-derived deterministically from emitted factor cards over the real corpus (no visual, real-time, or external-service behavior). The prior gap was reproduced and is now closed programmatically.

### Gaps Summary

**No gaps.** The single scoped BLOCKER from the prior report — `crawler/crs_audit.py::score_factor` dropping the owning `core_human_capital` language row in spouse mode via the `(factor_group == "spouse_common_law") != spouse_mode` filter — is fixed at the root by label-based mode-column selection (mirroring `core._grounded_points`). Independent re-verification confirms:

- **SC3 / AUDIT-04 (was FAILED → VERIFIED):** spouse-mode `core.language.first` reaches SUBSTANTIATED with `substantiated_points=116` (4 × grounded `clb9_with_spouse` 29) and `score_delta=8` (claimed 124 − 116); all six card fields are populated. Second-language spouse column resolves to the grounded value (6) at the unit level.
- **SC4 / AUDIT-05 (was FAILED → VERIFIED):** the spouse-mode substantiated total (944) INCLUDES the with-spouse language points (no ~116-point undercount); the total-vs-cutoff arithmetic (`cutoff_delta=444`, `meets_cutoff=True`) is self-consistent and free of legal-advice wording.

**No regressions:** SC1 (18 one-verdict cards, closed vocab, grounded citations), SC2 (four modules + reused frozen gate, `grounding.py` untouched, no new trust path), and SC5 (work aggregation GAP with overlap de-dup, transferability dependency GAP, spouse/principal ownership separation with no leak) all still hold. No-spouse language = 124 / delta 0 (a transient 116 seen mid-verification was a driver harness artifact — a shared candidate dir carried the spouse claim into the second seed; a clean-vault re-run and the committed `test_no_spouse_mode_language_points_unchanged` both confirm 124/0). Arranged-employment = AT-RISK/0 (never auto-green), sibling = truthful fail-closed GAP, conversion rows verbatim-grounded, transferability caps (50/50/100) hold. Full suite 634 passed / 1 skipped / 26 deselected (baseline 623 + 11 new tests); `no_inlined_volatile_rules(['crawler/crs_audit.py'])==[]`; publish-safe 0 violations; frozen v3.x trust path unchanged.

---

_Verified: 2026-07-06T13:18:37Z_
_Verifier: the agent (gsd-verifier) — re-verification after 33-07 gap closure_
