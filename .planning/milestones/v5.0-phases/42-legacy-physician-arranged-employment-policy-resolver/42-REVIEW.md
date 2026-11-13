---
phase: 42-legacy-physician-arranged-employment-policy-resolver
reviewed: 2026-07-19T06:41:33Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - crawler/auditor.py
  - crawler/auditors/__init__.py
  - crawler/auditors/additional.py
  - crawler/data/crs_rules/additional.yaml
  - crawler/tests/test_conformance_v40_retrieve_what_you_cite.py
  - crawler/tests/test_physician_policy.py
  - crawler/crs_rules.py
  - crawler/tests/test_conformance_v5_policy_no_job_offer_green.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: issues_found
---

# Phase 42: Code Review Report (re-review after WR fixes)

**Reviewed:** 2026-07-19T06:41:33Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found (0 blocking — 2 pre-existing Info only)

## Summary

Adversarial re-review of the two Warning fixes recorded in `42-REVIEW-FIX.md`:
`58372d8` (WR-01, always-run hermetic physician grounding gate), `27c4b8d`
(WR-02, reason-aware job-offer citation attachment), and the fix report `9fc38e0`.
I read every changed source/test file and independently reproduced the load-bearing
claims (I did not accept the report at face value — every count below was re-run).

**Both prior Warnings are genuinely resolved with no new defect, no regression, and
every Phase-42 safety invariant preserved. No Critical or Warning findings.**

### WR-01 — always-run hermetic grounding is FAITHFUL and NON-VACUOUS (verified)

- `TestJobOfferPhysicianHermeticGrounding` has **no** `@skipUnless` — all **5**
  tests run with no `corpus/index.db` (`-v` shows 5 PASSED, no skips). It builds a
  temp FTS5 index from two verbatim spans, loads the **real** registry row, and
  drives the **shipped** `auditor.gate_subset` + `crs_rules.validate_registry` +
  `retrieve_what_you_cite` — the production trust path, not a fork.
- **Non-vacuity is real.** Tracing `crs_rules._select_chunk`
  (`crawler/crs_rules.py:203-229`) + `retrieve_what_you_cite:232-275` confirms the
  hermetic index catches all three drift classes the commit claims:
  - **quote drift** → `grounds`/`validate_registry` fail (quote must be a verbatim
    substring of the chunk text);
  - **marker drift** → `sel.marker not in chunk["text"]` drops the only guidance
    hit → `selected=None` → `agrees_with_citation=False`
    (`test_physician_retrieve_what_you_cite_agrees_and_grounds` would fail);
  - **citation-id drift** → the row's cited id no longer resolves →
    `validate_registry` violation + `agrees=False`.
  - `test_gate_bites_when_physician_citation_chunk_drifts` drops the FSW-PDI span
    and asserts the **shipped** `gate_subset` raises `AuditGroundingError`, so the
    positive assertions cannot pass vacuously.
- The YAML `LOAD-BEARING COUPLING` comment (`additional.yaml:114-122`) is prose only
  — the no-inlined-volatile static gate (`test_crs_no_inlined_rules.py`) stays green
  (re-run: 4 passed), and the static gate deliberately does not scan `crawler/tests/`,
  so the verbatim fixtures are safe.

### WR-02 — reason-aware `rule_ids` preserves gating / other factors / precision / schema (verified)

- **Full-subset grounding gate is intact.** In `auditor.audit_one` the gate runs on
  the ENTIRE consumed subset (`crawler/auditor.py:239-240`, `_gate_or_raise(subset, db)`)
  **before** any reason-aware scoping (`:268-271`). `rule_ids` only narrows what the
  card *surfaces*, never what is gated — traced and confirmed.
- **Other factors are byte-identical.** `DecisionResult.rule_ids` defaults to `None`;
  `if result.rule_ids:` is falsy for both `None` and `()`, so every non-job-offer
  decider still gets the historical `_rule_citation_ids(subset)` union.
  `test_unset_rule_ids_preserves_union_for_other_factors` proves `decide_nomination`
  leaves `rule_ids=None` and the union is preserved.
- **Verdict/reason/points behavior unchanged.** `decide_job_offer` only *adds*
  `rule_ids` to each existing return; the `reason` ternary was refactored to an
  if/else with the identical mapping. All 8 `TestPhysicianBranch` cases still pass,
  confirming the verdict/reason/points contract is untouched.
- **Citation precision improved and covered.** `TestJobOfferReasonAwareCitations`
  (7 tests, all always-run — no DB) proves: physician→physician-only, legacy→legacy-only,
  non-physician current→current-only (excludes physician/legacy), no-points N/A→no
  irrelevant citations, and an unknown selected id is safely empty (fail-closed).
  `_rule_citation_ids_for` iterates the already-gated `subset.rows` in order, so id
  order stays stable and consistent with `_rule_citation_ids`.
- **Schema unchanged.** Only the `DecisionResult` dataclass grew an optional field;
  `PrivateFactorCard`/`PublicAuditEnvelope` and the attached `rule_citation_ids:
  list[str]` shape are unchanged. `test_audit_models.py` passes.

### Independent regression + report-claim verification (all reproduced)

- `crawler/crs_audit.py` (frozen guard): `git diff 4d105de..HEAD` → **empty** (byte-frozen).
- `test_conformance_v40_retrieve_what_you_cite.py`: **18 passed, 37 subtests**.
- `test_physician_policy.py`: **29 passed**.
- Targeted spine/decider regression (auditor, dispatch, additional, models,
  full-audit-integration, v40 no-false-green, v5 no-job-offer-green, no-inlined):
  **88 passed, 189 subtests**.
- Full crawler suite (excluding the heavy dedup real-corpus tests): **986 passed,
  2 skipped, 468 subtests** — exactly matching the fix report.
- Publish-safe gate: **0 violations** (414 tracked files; the report's 413 is a
  stale-by-one count taken before the report file itself was tracked — not a defect).
- Conformance release gate (`run_conformance.py`): **PASS — SAFE-01..08, 82 passed**.

### Hanging test — NOT introduced by these fixes

The `test_dupaudit.py::TestRealCorpus` dedup hang the fix report notes is a subsystem
this phase does not touch: `git show --stat 58372d8 27c4b8d` lists **no** dedup files.
Per scope, a pre-existing/environmental hang not introduced by the reviewed commits is
out of scope and was not further investigated. The rest of the collected suite is green.

Findings below are **pre-existing Info items carried forward** (neither introduced nor
regressed by the WR fixes). They are documentation-/coverage-quality only, non-blocking,
and do not affect sign-off. Note IN-02 from the prior review is now **resolved**: WR-02
added the always-run `test_subset_rows_cite_disjoint_chunks`, so the POLICY-02
distinct-citation invariant now runs in CI without the corpus. IN-04 remains intentional
forward-compat (the `offer_for_eligibility_manual` template is Phase-45-consumed).

## Info

### IN-01: Misleading `_PHYS_WINDOW` comment in the v5 conformance test (still present)

**File:** `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py:89`

**Issue:** `_PHYS_WINDOW = "2023-06-01"  # after the physician effective_from, physician-only`.
Verified still present (this file was untouched by the WR fixes). `2023-06-01` lies
inside **both** the physician window `[2023-04-25, ∞)` and the legacy window
`(-∞, 2025-03-25)`, so it is not "physician-only" — the physician branch merely wins by
branch order at this date. The truly physician-only region is post-repeal
`[2025-03-25, ∞)`. The test still passes; only the comment misdescribes the date.

**Fix:** Reword to "after the physician effective_from; also inside the legacy window
(branch-order case)", or move the constant to a post-repeal date for a genuinely
physician-only edge.

### IN-03: No Phase-42 test drives an unconfirmed physician NOC through the spine's fail-closed path (carried forward)

**File:** `crawler/tests/test_physician_policy.py` (+ `42-VALIDATION.md` per-task map)

**Issue:** The physician branch is only reachable for `confirmed`/`corrected` +
`is_audit_eligible` values (the spine's `vault.audit_eligible_values` filter — confirmed
by inspection of the SQL). WR-02's new `TestJobOfferReasonAwareCitations` drives
`decide_job_offer` **directly** (synthetic `by_field`), so it still does not exercise an
**unconfirmed/stale** physician NOC being excluded by the spine before the branch can
fire. No code bug — the guarantee lives in the spine and is exercised elsewhere — but no
Phase-42 test asserts it for the physician path specifically.

**Fix:** Add one spine-level test that imports/extracts a `job_offer` doc **without**
confirming its `noc_code` and asserts `audit_eligible_values(v, "additional.job_offer")`
excludes it (so the physician branch cannot fire).

---

_Reviewed: 2026-07-19T06:41:33Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
