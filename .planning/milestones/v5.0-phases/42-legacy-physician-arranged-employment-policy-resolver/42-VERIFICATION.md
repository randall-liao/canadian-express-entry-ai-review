---
phase: 42-legacy-physician-arranged-employment-policy-resolver
verified: 2026-07-19T07:10:00Z
status: passed
score: 14/14 must-haves verified
overrides_applied: 0
requirements:
  - id: POLICY-01
    status: satisfied
  - id: POLICY-02
    status: satisfied
  - id: POLICY-03
    status: satisfied
gates:
  frozen_guard_byte_identity: pass        # git diff --quiet HEAD -- crawler/crs_audit.py (exit 0), and 0a86920..HEAD empty
  no_inlined_volatile_rules: pass         # static gate clean over registry + auditor + remediation + sidecar surfaces
  coverage_complete_not_stale: pass       # COVERAGE.md == fresh render; physician slot present; Status COMPLETE
  physician_grounding_real_corpus: pass   # TestJobOfferPhysicianRealCorpus (agrees + grounds + disjoint)
  physician_grounding_hermetic: pass      # TestJobOfferPhysicianHermeticGrounding (always-run WR-01 + gate-bites control)
  publish_safe: pass                      # 415 tracked files, 0 violations
  conformance_v4x_release_gate: pass      # 82 passed, SAFE-01..08; v5 file absent from gate module list
  zero_new_dependency: pass               # pyproject.toml unchanged; frozen-dep-set test 2 passed
  full_crawler_suite: pass                # 1029 passed / 2 skipped / 1 deselected / 468 subtests (fresh verifier run)
  code_review_critical_warning: pass      # 42-REVIEW.md critical:0 warning:0; WR-01/WR-02 fixed & re-reviewed
human_verification: []
deferred: []
---

# Phase 42: Legacy & Physician Arranged-Employment Policy Resolver — Verification Report

**Phase Goal:** Resolve the arranged-employment edge cases v4.x left `AT-RISK` with effective-dated grounded verdicts (legacy pre-repeal, post-repeal, physician public-policy), keeping the shipped fail-closed guard byte-for-byte frozen and separating "valid offer for program eligibility" from "arranged-employment CRS additional points."
**Verified:** 2026-07-19T07:10:00Z
**Status:** passed
**Re-verification:** No — initial verification (no prior 42-VERIFICATION.md)

## Verification Method

Goal-backward. Every claim below was re-established by reading the actual source/YAML/tests and by
**running the tests in this verifier's own process** — SUMMARY/REVIEW PASS-marker counts were treated
as claims, not evidence. All commands use `.venv/bin/python` (Python 3.10.12, pytest 9.0.3). The real
git-ignored `corpus/index.db` (16 MB) is present, so grounding / retrieve-what-you-cite / extraction
real-seam tests executed rather than skipped.

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 1  | **(POLICY-01)** Legacy in-window claim → grounded `AT-RISK`/manual by effective-dated windows, never `SUBSTANTIATED`/auto-green; post-repeal stays `AT-RISK`/0; and the guard is byte-frozen | ✓ VERIFIED | `crs_audit.arranged_employment_guard` (crs_audit.py:397-433): grounded in-window legacy → `AT-RISK`/`points=None`; non-zero post-repeal → `AT-RISK`/`0`; zero → `N/A`. `decide_job_offer` delegates unchanged. Tests: `TestJobOfferTrap` (3 pass), v5 `TestNoJobOfferPathGreens` cases (c) legacy 2024-06-01 / (d) post-repeal 2026-01-01, `TestGuardNeverGreens` across window edges (1…100000) — all `!= SUBSTANTIATED`, `points in (None,0)`. `git diff HEAD -- crawler/crs_audit.py` empty (also empty across whole phase 0a86920..HEAD). |
| 2  | **(POLICY-02)** Grounded physician row carries official citations / window / NOCs, distinct from repeal/legacy | ✓ VERIFIED | `additional.yaml:124-159` — `additional.job_offer.physician`, `factor_ids:[additional.job_offer]`, `accepted_enum` NOC set {31100,31101,31102}, `effective_from 2023-04-25`, `effective_to` omitted (null); 2 citations (`guidance/job-offer.md#002` + FSW-PDI `#020`), U+2019 marker. `TestJobOfferPhysicianRealCorpus`: `agrees_with_citation`+`grounds` True, citations disjoint from current & legacy. `TestJobOfferPhysicianHermeticGrounding` (WR-01, always-run, no DB) proves grounding + `gate_bites_when_citation_chunk_drifts` (fail-closed). |
| 3  | **(POLICY-02)** Physician verdict is reachable through **real confirmed** `job_offer` extraction evidence, contamination-free, no vault migration | ✓ VERIFIED | `extraction.py:239-264` — `_FIELD_SPECS["job_offer"]` (reused `noc_code` spec + inert issuer/employment_start), `_DOC_TYPE_FACTOR["job_offer"]="additional.job_offer"`. `TestJobOfferExtractionLinkage` (3 pass): job_offer NOC → `additional.job_offer`, employment_reference NOC → `core.work`, non-leak both ways, unclaimed target → unlinked (fail-closed). No `FieldName` change. |
| 4  | Stale / unconfirmed / malformed / non-physician / no-ITA / missing-NOC all **fail closed** to the frozen guard | ✓ VERIFIED | `decide_job_offer` (additional.py:87-129): malformed grounded date → `try/except → in_effect=False`; missing NOC / non-physician / no-ITA fall through to the unchanged guard. Spine gate `audit_eligible_values` (auditor.py:243) admits only confirmed/audit-eligible values before the branch. Tests: `TestPhysicianBranch` malformed-window / missing-noc / none-ita / non-physician / zero-claim (8 pass). |
| 5  | **(POLICY-02)** Physician branch is `AT-RISK`/manual only, fires BEFORE the frozen guard, reads NOC set + window from the grounded row (no inlined literal) | ✓ VERIFIED | additional.py:95-110 → `DecisionResult("AT-RISK","physician_policy_manual",substantiated_points=None,rule_ids=(_JOB_OFFER_PHYSICIAN,))`; NOC set from `phys.machine_check.accepted_values`, window via `crs_audit.row_in_effect`. `test_physician_noc_in_legacy_window_branch_order_wins` proves precedence. `grep` for 31100/31101/31102/2023-04-25 in production `.py` → no matches. |
| 6  | Reason-aware citations (WR-02): each job-offer card surfaces ONLY the rows it derives from; other factors keep the historical union; whole subset still gated | ✓ VERIFIED | `DecisionResult.rule_ids` (auditors/__init__.py:92, default None). Spine gates entire subset (`_gate_or_raise`, auditor.py:240) BEFORE scoping (`if result.rule_ids:` at :268-271). `_rule_citation_ids_for` order-stable, fail-closed on unknown id. Tests: `TestJobOfferReasonAwareCitations` (7 pass) incl. non-physician-excludes-physician/legacy and unset-preserves-union. |
| 7  | **(POLICY-03)** Inert offer sidecar: constant `crs_points=0`, `AT-RISK`/`N/A` only, unregistered, PII-light, reuses grounded citation | ✓ VERIFIED | `policy_offer.py:44-80` — bare `crs_points:0` (no reassignment branch), status `AT-RISK`/`N/A`, closed `PUBLIC_FIELDS`, reused `additional.job_offer.current` citation. Not registered (grep of production imports empty; `resolve('additional.job_offer')` ≠ sidecar), not in `FULL_GRID_FACTORS`, no MEC wiring. Tests: `TestOfferSidecar` (6) + `TestSidecarNeverGreens` (2). |
| 8  | Remediation surfaces `physician_policy_manual` + `offer_for_eligibility_manual` as generic `{factor}`-only PII-light prose with no inlined threshold; unknown codes degrade safely | ✓ VERIFIED | `remediation.py:127-132` templates (no date/NOC/points/CLB/window literal); `_action_for` falls back to `_DEFAULT_ACTION_BY_KIND`. Tests: `TestRemediationReasons` (4 pass) incl. no-inlined-threshold and unknown-degrades. `review_packet.py` untouched (0 diff). |
| 9  | Coverage stays complete & not stale; no-inlined-volatile static gate clean | ✓ VERIFIED | `COVERAGE.md:54` physician slot `present`, `Status: COMPLETE`; `REQUIRED_RULE_IDS["additional_points"]` includes physician label (crs_rules.py:85). `test_committed_coverage_md_not_stale` + `test_static_no_inlined_volatile_gate_is_clean` pass; `test_crs_no_inlined_rules.py` clean. |
| 10 | Exhaustive negative-control conformance proves NO `additional.job_offer` path greens (decider + guard + sidecar) | ✓ VERIFIED | `test_conformance_v5_policy_no_job_offer_green.py` drives the REAL functions over an exhaustive matrix asserting `!= SUBSTANTIATED` + `points/substantiated_points in (None,0)` + non-truthy + `crs_points==0`; `TestFrozenGuardByteIdentity` RAN (not skipped) and passed. Full module: 6 tests / 41 subtests pass. Non-vacuous (imports and calls production surfaces). |
| 11 | Zero new deps; later-phase boundaries respected (run_conformance untouched, v5 outside v4.x glob, no MEC wiring) | ✓ VERIFIED | `pyproject.toml` unchanged 0a86920..HEAD; `test_dli_conformance.py -k dependencies` → 2 pass. `scripts/run_conformance.py` unchanged; v5 file NOT matched by `test_conformance_v4[01]_*.py`; `policy_offer` unimported by production. |
| 12 | Review fixes applied; final review critical:0 / warning:0 | ✓ VERIFIED | Commits `58372d8` (WR-01 always-run hermetic grounding) + `27c4b8d` (WR-02 reason-aware citations) present; `42-REVIEW.md` (post-fix re-review) records critical:0, warning:0, 2 Info (non-blocking). WR-01/WR-02 behaviors independently re-run green here. |
| 13 | Publish-safe + v4.x conformance release gates green | ✓ VERIFIED | `check_publish_safe.py` → 415 files, 0 violations (exit 0). `run_conformance.py` → 82 passed, gate PASS SAFE-01..08 (exit 0). |
| 14 | Fresh full `crawler/tests` suite green; the dedup real-corpus hang is pre-existing and phase-independent | ✓ VERIFIED | Verifier's own run: **1029 passed / 2 skipped / 1 deselected / 468 subtests** (131 s). 2 skips are pre-existing intentional offline skips (live DLI endpoint; optional `crawl4ai`). The 1 deselected (`test_dupaudit.py::TestRealCorpus`) is a heavy `difflib.SequenceMatcher` O(n²) real-corpus computation with ZERO import overlap and ZERO changed-file overlap with Phase 42 (see Anti-Patterns / Notes). |

**Score:** 14/14 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/data/crs_rules/additional.yaml` | Grounded effective-dated physician row | ✓ VERIFIED | Row present (lines 124-159), grounds live + hermetically, disjoint citations, no `effective_to`. |
| `crawler/crs_rules.py` | Physician label in `REQUIRED_RULE_IDS` | ✓ VERIFIED | Line 85 appended (prefix-exact `_covers`); coverage stays COMPLETE. |
| `crawler/data/crs_rules/COVERAGE.md` | Regenerated pure render | ✓ VERIFIED | Physician slot `present`; not stale (fresh-render equality test passes). |
| `crawler/auditors/additional.py` | `decide_job_offer` physician branch (AT-RISK/manual, pre-guard) + reason-aware `rule_ids` | ✓ VERIFIED | Lines 44-129; delegates all non-matching paths to frozen guard unchanged. |
| `crawler/auditors/__init__.py` | `DecisionResult.rule_ids` optional field | ✓ VERIFIED | Line 92, default None → union preserved for every other factor. |
| `crawler/auditor.py` | Reason-aware citation attachment, subset fully gated | ✓ VERIFIED | `_rule_citation_ids_for` (:109-132); gate at :240 before scoping at :268-271. |
| `crawler/extraction.py` | `job_offer` doc type → `additional.job_offer` | ✓ VERIFIED | Lines 239-264; reuses `noc_code` FieldName (no migration). |
| `crawler/policy_offer.py` | Inert constant-0 PII-light sidecar | ✓ VERIFIED | Lines 1-80; unregistered, not in grid/envelope, reused citation. |
| `crawler/remediation.py` | Physician + offer-for-eligibility templates | ✓ VERIFIED | Lines 127-132; generic `{factor}`-only, no volatile literal, safe fallback. |
| `crawler/tests/fixtures/extraction/make_fixtures.py` | `job_offer_pdf()` physician-NOC fixture | ✓ VERIFIED | Synthetic FAKE values; drives the linkage tests. |
| `crawler/tests/test_physician_policy.py` | POLICY-02/03 unit + linkage + sidecar + remediation + no-inlined | ✓ VERIFIED | 35 tests (with v5 file) / all classes pass; non-vacuous. |
| `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py` | Physician grounding (real + hermetic) | ✓ VERIFIED | 18 tests / 37 subtests pass; physician classes ran (not skipped). |
| `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` | Exhaustive POLICY negative control | ✓ VERIFIED | 6 tests / 41 subtests pass; frozen byte-identity ran. |
| `crawler/tests/test_dli_conformance.py` | Realigned `_FROZEN_CONTRACT_PATHS` (guard kept frozen) | ✓ VERIFIED | `crs_audit.py` in tuple (line 92); `additional.yaml`/`COVERAGE.md` dropped (legit Phase-42 targets). |
| `crawler/crs_audit.py` | Frozen guard byte-for-byte unchanged | ✓ VERIFIED (unchanged) | 0 diff vs HEAD and across the entire phase. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `additional.job_offer.physician` (YAML) | corpus `guidance/job-offer.md#002` + FSW-PDI `#020` | `validate_registry` + `retrieve_what_you_cite` verbatim substring | ✓ WIRED | agrees + grounds; disjoint from current/legacy; hermetic gate bites on drift. |
| `decide_job_offer` | `crs_audit.row_in_effect` | consumed Phase-40 predicate, `try/except`→not-in-effect | ✓ WIRED | no re-added window math; malformed date fails closed. |
| `decide_job_offer` | `phys.machine_check.accepted_values` | NOC set read from grounded row | ✓ WIRED | no inlined NOC literal. |
| `extraction._DOC_TYPE_FACTOR['job_offer']` | `additional.job_offer` via `_resolve_factor` | per-document claimed-only linkage | ✓ WIRED | non-leak both ways; unclaimed → unlinked. |
| `decide_job_offer.rule_ids` | spine `_rule_citation_ids_for` | reason-aware scoping over already-gated subset | ✓ WIRED | union preserved for other factors; whole subset still gated. |
| `policy_offer.offer_for_program_eligibility` | `additional.job_offer.current` citation | reused grounded citation, no new surface | ✓ WIRED | inert; returns None when row absent. |
| `remediation._ACTION_TEMPLATES` | review_packet reason projection | generic reason string flows unchanged | ✓ WIRED | `review_packet.py` untouched. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| physician verdict path | `by_field["noc_code"]` | vault `audit_eligible_values` (confirmed/corrected only) → extraction `job_offer` doc | Yes — real confirmed evidence reaches the branch (linkage test) | ✓ FLOWING |
| physician row NOC set / window | `phys.machine_check.accepted_values` / `effective_from` | grounded `additional.yaml` row (verbatim corpus-backed) | Yes — grounds against real `corpus/index.db` | ✓ FLOWING |
| sidecar citation | `current.citations[0].chunk_id` | grounded `additional.job_offer.current` row | Yes — reused grounded id (None only if row absent, by design) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Focused POLICY unit + v5 negative control | `pytest test_physician_policy.py test_conformance_v5_policy_no_job_offer_green.py -v` | 35 passed / 41 subtests | ✓ PASS |
| Grounding + no-inlined + frozen-contract + linkage + remediation | `pytest test_conformance_v40_… test_crs_no_inlined_rules test_dli_conformance test_auditors_additional test_extraction_factor_linkage test_remediation` | 78 passed / 61 subtests | ✓ PASS |
| Frozen guard byte-identity | `git diff --quiet HEAD -- crawler/crs_audit.py` (+ 0a86920..HEAD) | exit 0 / empty | ✓ PASS |
| Zero new dependency | `pytest test_dli_conformance.py -k dependencies` | 2 passed | ✓ PASS |
| Publish-safe perimeter | `scripts/check_publish_safe.py` | 415 files, 0 violations (exit 0) | ✓ PASS |
| v4.x conformance release gate | `scripts/run_conformance.py` | 82 passed, SAFE-01..08 PASS (exit 0) | ✓ PASS |
| Fresh full suite (minus pre-existing dedup hang) | `pytest crawler/tests --deselect …TestRealCorpus…` | 1029 passed / 2 skipped / 1 deselected / 468 subtests | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared or discovered for this phase; verification uses
the phase's own pytest conformance suites + release-gate scripts, all of which were executed above.

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| (none declared) | — | — | N/A |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| POLICY-01 | 42-01, 42-04 | Legacy in-window `AT-RISK`/manual by effective windows; post-repeal `AT-RISK`/0; guard frozen | ✓ SATISFIED | Truths 1, 10, 14; guard byte-identity |
| POLICY-02 | 42-01, 42-02, 42-04 | Physician grounded `AT-RISK`/manual, distinct row/citation | ✓ SATISFIED | Truths 2, 3, 4, 5, 6, 10 |
| POLICY-03 | 42-03, 42-04 | Separate offer-for-eligibility from CRS points; guard frozen | ✓ SATISFIED | Truths 7, 8, 11; sidecar constant-0 |

No orphaned requirements: REQUIREMENTS.md maps only POLICY-01/02/03 to Phase 42, all claimed by plans and all marked Complete.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (production files) | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER/stub found | ℹ️ Info | Clean — no debt markers in any Phase-42 production file |
| `test_conformance_v5_policy_no_job_offer_green.py` | 89 | `_PHYS_WINDOW="2023-06-01"` comment says "physician-only" but date is inside both windows (branch-order case) | ℹ️ Info | Documentation-only; test still passes correctly (IN-01, carried forward from review). Not a behavior defect. |
| `test_physician_policy.py` | — | No Phase-42 test drives an *unconfirmed* physician NOC through the spine's fail-closed exclusion specifically | ℹ️ Info | Coverage-placement nit (IN-03). The guarantee is structurally enforced by the spine's `audit_eligible_values` filter and exercised in other suites; no code bug. |

### Human Verification Required

None. All phase behavior is deterministic and covered by executed automated tests. The WR-02 fix report
raised a "human glance" note on the **N/A job-offer card citing the current-repeal row** (rather than no
citation); this is a deterministic, test-covered design choice (`test_no_points_card_has_no_irrelevant_citations`
and `test_nonphysician_current_card_excludes_physician_and_legacy` both pass, and it mirrors the guard's
current-policy citation), and the post-fix re-review (`42-REVIEW.md`, critical:0/warning:0) treated it as
resolved. Per the deterministic-verification standard, no human UAT gate is raised.

### Notes — Dedup Hang Investigation (phase-independence proven)

`crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts` times out in
this environment (probe: `timeout 180 … → RC 124`). It is **not** phase-related:

- **No changed-file overlap:** `git diff --stat 0a86920..HEAD` for Phase 42 touches only
  `auditor.py`, `auditors/__init__.py`, `additional.py`, `crs_rules.py`, `COVERAGE.md`, `additional.yaml`,
  `extraction.py`, `policy_offer.py`, `remediation.py`, `make_fixtures.py`, and 4 test files — no dedup file.
- **No import overlap:** `dupaudit.py` imports only stdlib + `yaml` + `crawler.eval_runner` + `crawler.profile`;
  it references none of the Phase-42 surfaces.
- **Root cause is inherent cost, not a regression:** the test runs `dupaudit.audit(Path("corpus"))` — a
  `difflib.SequenceMatcher` O(n²) near-duplicate clustering over 742+ real-corpus docs — guarded only by
  `corpus/` existence. This matches the pre-existing note in the 42-01 SUMMARY and the 42-REVIEW-FIX report
  (reproduces on unmodified `master`/`4d105de`).

The fresh full-suite result above **deselects only this one pre-existing hang** and is reported honestly as
`1029 passed / 2 skipped / 1 deselected`. No false full-suite green is claimed; every other collected test
in `crawler/tests` executed and passed.

### Gaps Summary

None. All 14 observable truths are VERIFIED with executed-test evidence. The three ROADMAP Success Criteria
(POLICY-01/02/03) hold in the codebase: (1) the legacy/repeal paths and the physician branch never green and
the `arranged_employment_guard` is byte-for-byte frozen across the entire phase; (2) the physician case is a
grounded, distinctly-cited `AT-RISK`/manual verdict reachable through real confirmed `job_offer` extraction,
with reason-aware citations preventing over-citation; (3) the inert `policy_offer` sidecar structurally
separates program-eligibility from CRS points (constant `crs_points=0`, unregistered, PII-light) and the CRS
total / `PublicAuditEnvelope` are untouched. Publish-safe (0 violations), the v4.x conformance gate
(SAFE-01..08), the zero-dependency gate, the no-inlined-volatile static gate, and coverage freshness are all
green. Code review is critical:0 / warning:0 after the WR-01/WR-02 fixes, both independently re-run green.
The only open items are three non-blocking Info notes (documentation wording + coverage placement) that do
not affect goal achievement.

---

_Verified: 2026-07-19T07:10:00Z_
_Verifier: the agent (gsd-verifier)_
