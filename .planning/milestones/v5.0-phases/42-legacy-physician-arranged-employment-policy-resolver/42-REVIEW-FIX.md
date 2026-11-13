---
phase: 42-legacy-physician-arranged-employment-policy-resolver
fixed_at: 2026-07-19T06:38:52Z
review_path: .planning/phases/42-legacy-physician-arranged-employment-policy-resolver/42-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 42: Code Review Fix Report

**Fixed at:** 2026-07-19T06:38:52Z
**Source review:** `.planning/phases/42-legacy-physician-arranged-employment-policy-resolver/42-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (both Warnings — `WR-01`, `WR-02`)
- Fixed: 2
- Skipped: 0
- Info findings (`IN-01`..`IN-04`): intentionally **not** implemented (out of scope for a
  critical+warning fix pass; each is documentation-quality / coverage-placement guidance the
  review itself marks "no code bug").

Both fixes were applied WITHOUT weakening any existing safety invariant: `crawler/crs_audit.py`
stays **byte-for-byte frozen** (zero diff across both commits), the whole-registry live grounding
tests are unchanged, the `PrivateFactorCard` / `PublicAuditEnvelope` schema is untouched, the
no-inlined-volatile static gate stays clean, publish-safe reports 0 violations, and the v4.x
conformance release gate passes.

## Fixed Issues

### WR-01: Physician row makes two new corpus chunks load-bearing for the ENTIRE job-offer factor, but its grounding is only proven in a local-only (skip-guarded) test

**Files modified:** `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py`, `crawler/data/crs_rules/additional.yaml`
**Commit:** `58372d8`
**Applied fix (review Fix option (a)+(c), off-corpus grounding gate):**
Added an **ALWAYS-RUN** hermetic grounding class `TestJobOfferPhysicianHermeticGrounding` to the
retrieve-what-you-cite conformance module. It builds a minimal in-memory FTS5 index carrying ONLY
the exact **two authoritative physician chunk spans** the row cites
(`guidance/job-offer.md#002` + the FSW arranged-employment PDI `#020`), with text copied
**verbatim** from the pinned corpus (inserted directly with a real `searchindex.chunk_sha`
fingerprint and an FTS `'rebuild'`, so `searchindex.resolve` accepts them). It loads the **real**
registry row from `additional.yaml` and drives the **shipped** spine gate
(`auditor.gate_subset`), `crs_rules.validate_registry`, and `crs_rules.retrieve_what_you_cite`
over it — proving `agrees_with_citation` + `grounds` **without** `corpus/index.db`, so a
physician row / citation / marker drift is caught in CI. A non-vacuity control drops the FSW-PDI
span and asserts the shipped gate then **fail-closes** (`AuditGroundingError`), so the guard
demonstrably bites. Also documented the shared-factor **load-bearing coupling** in the physician
YAML row comment (prose only — no volatile literal added, so the no-inlined static gate stays
clean). The verbatim fixtures live in a test file, which the static gate surface deliberately
does not scan. Whole-registry live tests were not weakened.

### WR-02: Every job-offer verdict card now surfaces the physician-specific citations, including for non-physician applicants

**Files modified:** `crawler/auditors/__init__.py`, `crawler/auditor.py`, `crawler/auditors/additional.py`, `crawler/tests/test_physician_policy.py`
**Commit:** `27c4b8d`
**Applied fix (review's preferred generalized-contract design — requires human verification of the N/A citation-scoping choice):**
Made citation attachment verdict/reason-aware through a **generalized internal contract**, not a
job-offer hardcode in the spine:
- `DecisionResult` gains an optional `rule_ids: tuple[str, ...] | None = None`. Empty / `None`
  (the default for **every other factor**) → the spine attaches the historical **union** of all
  consumed rows' citations (byte-identical behavior); a **non-empty** value → only those rows'
  citations.
- The spine (`crawler/auditor.py`) adds `_rule_citation_ids_for(subset, rule_ids)` (order-stable,
  taken from the **already-gated** consumed subset) and, in `audit_one`, attaches the union when
  `rule_ids` is empty/None else the selected rows. **The ENTIRE consumed subset is still
  grounding-gated upstream (fail-closed)** — only what the card *surfaces* is narrowed.
- `decide_job_offer` scopes `rule_ids` per verdict: physician → physician row; legacy → legacy
  row; current-repeal / no-ITA / N-A(no-claim) → current-repeal row. All other factors and the
  frozen guard delegation are unchanged.
- Focused tests (`TestJobOfferReasonAwareCitations`, real registry + shipped spine helper):
  non-physician current card **excludes** physician/legacy citations; legacy → only legacy;
  physician → only physician; a no-points card carries no irrelevant citations; an invalid
  selected rule id is **safely empty** (fail-closed convention); an unset `rule_ids` preserves
  the union for other factors.
- `PrivateFactorCard` / `PublicAuditEnvelope` schema unchanged.

> **Human-verification note (per fixer logic-change convention):** WR-02 changes decider→card
> citation behavior. The mapping is fully covered by the focused tests above, but one design
> choice warrants a human glance: a **no-claim `N/A`** job-offer card is scoped to the
> current-repeal row (`additional.job_offer.current`) — the grounded basis for "a job offer
> yields no additional CRS points" — rather than carrying no citation at all. This mirrors the
> `arranged_employment_guard`'s current-policy citation and excludes the irrelevant
> physician/legacy citations; confirm this is the intended N/A framing before sign-off.

## Verification Evidence

- `test_conformance_v40_retrieve_what_you_cite.py` (incl. new hermetic class): **18 passed, 37 subtests**.
- `test_physician_policy.py` (incl. new `TestJobOfferReasonAwareCitations`): **29 passed**.
- Targeted spine/decider regression (`test_auditor.py`, `test_auditor_dispatch.py`,
  `test_auditors_additional.py`, `test_audit_models.py`, `test_audit_store.py`,
  `test_full_audit_integration.py`, `test_crs_registry_transfer_additional.py`,
  `test_conformance_v5_policy_no_job_offer_green.py`, `test_conformance_v40_no_false_green.py`):
  **101 passed, 206 subtests**.
- No-inlined volatile static gate (`test_crs_no_inlined_rules.py`): **clean (4 passed)**.
- Full crawler suite (excluding the pre-existing-hanging dedup real-corpus test — see note):
  **986 passed, 2 skipped, 468 subtests** + `test_dupclean.py` **18 passed** +
  `test_dupaudit.py` minus the one hang **25 passed** = the entire collected suite (1032) green
  save the single pre-existing hang.
- Publish-safe gate (`scripts/check_publish_safe.py`): **413 tracked files, 0 violations**.
- Conformance release gate (`scripts/run_conformance.py`): **PASS — SAFE-01..08, 82 passed**.
- Frozen guard: `git diff --stat crawler/crs_audit.py` across both fix commits → **empty (byte-frozen)**.

**Pre-existing hang (NOT introduced by these fixes):**
`crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts`
(a heavy real-corpus dedup smoke test in a subsystem this phase does not touch) hangs/times out
in this environment. It reproduces identically on **unmodified `master` (HEAD `4d105de`) in the
main repo**, so it is environmental / pre-existing and unrelated to the WR-01/WR-02 changes
(consistent with the 42-01 summary note that the full sweep does not surface under `pytest -q`).
Every other collected test passes.

---

_Fixed: 2026-07-19T06:38:52Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
