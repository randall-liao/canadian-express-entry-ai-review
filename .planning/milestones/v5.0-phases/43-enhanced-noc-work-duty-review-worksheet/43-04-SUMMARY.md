---
phase: 43-enhanced-noc-work-duty-review-worksheet
plan: 04
subsystem: testing

tags: [noc-2021, conformance, negative-control, never-green, byte-identity, factor-isolation, review.noc, core.work, idempotency, no-inlined-rules, ast-scan, release-gate]

# Dependency graph
requires:
  - phase: 43-01
    provides: "noc_worksheet.generate_worksheet — idempotent (duty_id, duty_sha) born-pending capture on the inert review.noc factor + resolve_noc_spans/split_duties"
  - phase: 43-02
    provides: "noc_review.review_noc_duties — inert never-green {AT-RISK,GAP,N/A} roll-up with two-layer staleness + current-worksheet-key dedup + closed PUBLIC_FIELDS"
  - phase: 32-audit
    provides: "auditor.audit_factor/audit_one/run_full_audit + PrivateFactorCard/PublicAuditEnvelope/to_public_envelope (the FROZEN grid + public projection)"
  - phase: 33-full-modular-crs-auditor-pack
    provides: "auditors._REGISTRY / FULL_GRID_FACTORS / resolve (dispatch spine the sidecar is proven absent from)"
  - phase: 42-legacy-physician-arranged-employment-policy-resolver
    provides: "crawler/tests/test_conformance_v5_policy_no_job_offer_green.py — the negative-control mirror (sweep + git-diff byte-identity + _git_root skip-guard)"
  - phase: 31-grounded-crs-rule-registry
    provides: "crs_rules.no_inlined_volatile_rules + the aggregate _EXPORT_MODULES static gate"
provides:
  - "crawler/tests/test_conformance_v5_noc_no_auto_green.py: the release-gate-grade NOC-03 negative control — exhaustive never-green sweep + FREEZE-set byte-identity + sidecar inertness + closed PII-light set + B1 core.work factor-isolation (before/after confirmed review.noc + idempotent-regeneration + changed-sha) + no-NOC-id-in-any-PublicAuditEnvelope"
  - "Extended _EXPORT_MODULES no-inlined-volatile gate covering crawler/noc_worksheet.py + crawler/noc_review.py"
affects: [45-mec-integrator, 46-v5-release-gate-glob]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies — stdlib unittest + already-frozen primitives only
  patterns:
    - "Negative-control conformance clone (physician v5 mirror): exhaustive real-decider sweep asserting no path greens + git diff --quiet HEAD byte-identity over a FREEZE set, skip-guarded off a git checkout via _git_root"
    - "Runtime factor-isolation proof: audit the FROZEN core.work card BEFORE and AFTER confirming values on a SIBLING inert factor and assert model_dump() byte-identity — the structural reason (audit_eligible_values('core.work') never returns a review.noc value) is asserted directly"
    - "Two-corpus test vault: a synthetic core.work index (self.db) for the frozen-grid audit + the pinned NOC corpus (real_db) for the worksheet generator, both driving the SAME vault so cross-factor contamination would surface"
    - "Envelope inertness: down-project a real single-factor AND full-grid report via to_public_envelope and assert no NOC/review.noc id in the PII-light dump"

key-files:
  created:
    - crawler/tests/test_conformance_v5_noc_no_auto_green.py
  modified:
    - crawler/tests/test_crs_no_inlined_rules.py

key-decisions:
  - "The v5 prefix is DELIBERATELY outside the v4.x release-gate glob test_conformance_v4[01]_*.py (Phase 46 introduces the v5 glob); scripts/run_conformance.py was NOT touched — the file still runs inside the full crawler/tests suite"
  - "The B1 isolation proof audits core.work over a SYNTHETIC registry+index (self.db) while the NOC worksheet resolves the pinned corpus (real_db); both share one vault, so a leak of a review.noc value into core.work would break the byte-identity assertion"
  - "Byte-identity is asserted at BOTH the named-field fingerprint level (verdict/reason_code/confirmed_value/sorted evidence_ids/substantiated_points/score_delta) AND the full PrivateFactorCard.model_dump() level (no field drifts at all)"
  - "The changed-sha rerun is simulated the same grounded way the Plan-01/02 slice proves it: an OLD confirmed value carries a superseded duty_sha while the live generator mints the fresh sha — the sidecar counts the duty via the CURRENT key set exactly once, old value ignored"
  - "The never-green sweep drives the REAL review_noc_duties over 10 input classes (incl. a GROUPED sub-occupation NOC) and asserts the closed PUBLIC_FIELDS keys exactly — proving no crs_points/score/substantiated_points key is even representable (no non-zero CRS delta possible)"
  - "NOC-01/NOC-02/NOC-03 are marked complete here (not in Plans 01-03): the phase deliberately held all three Pending until this freeze/conformance proof closed"

patterns-established:
  - "Pattern: v5 negative-control conformance module (mirror the sibling phase's *_no_*_green.py wholesale, retarget the decider/sidecar + FREEZE set, keep the marker but stay outside the release-gate glob)"
  - "Pattern: runtime cross-factor isolation via before/after model_dump() byte-identity of a frozen card over a sibling factor's confirmations"

requirements-completed: [NOC-01, NOC-02, NOC-03]

# Metrics
duration: 32min
completed: 2026-07-19
---

# Phase 43 Plan 04: NOC Never-Auto-Green Conformance + Frozen-Surface Byte-Identity Summary

**The release-gate-grade NOC-03 negative control: an exhaustive sweep proving no duty-review path can reach `SUBSTANTIATED` or a non-zero CRS delta, a `git diff --quiet HEAD` byte-identity over the FREEZE set, structural + runtime proof the `review.noc` sidecar is inert, and a B1 factor-isolation proof that the frozen `core.work` `PrivateFactorCard` is byte-identical before/after confirmed `review.noc` values and across idempotent exact/changed-sha regenerations — plus the no-inlined-volatile static gate extended to both NOC modules.**

## Performance

- **Duration:** ~32 min
- **Started:** 2026-07-19T06:24:00-04:00
- **Completed:** 2026-07-19T06:56:00-04:00
- **Tasks:** 2 (both complete)
- **Files modified:** 2 (1 created, 1 extended)

## Accomplishments

- **Task 1 — no-inlined-volatile gate extension (`crawler/tests/test_crs_no_inlined_rules.py`):** added `crawler/noc_worksheet.py` + `crawler/noc_review.py` to the `_EXPORT_MODULES` tuple. Any future inlined duty text, lead statement, threshold, or the R87.1 essential-duties standard in either NOC module now trips the aggregate `no_inlined_volatile_rules` gate. A missing path stays silently skipped (the gate remains WIRED), and the existing positive controls still bite over the extended surface (`4 passed`).
- **Task 2 — v5 NOC negative-control conformance (`crawler/tests/test_conformance_v5_noc_no_auto_green.py`, 686 lines, `pytestmark = pytest.mark.conformance`):** a wholesale mirror of the Phase-42 `test_conformance_v5_policy_no_job_offer_green.py`, retargeted to the NOC sidecar + FREEZE set. Six test classes (`12 passed, 14 subtests`):
  - **`TestNoNocPathGreens`** — an exhaustive sweep driving the REAL `noc_review.review_noc_duties` over 10 input classes (`none / pending-only / partial / all-rejected / Layer-1-stale / Layer-2-drifted / changed-sha / all-confirmed-fresh`, plus a GROUPED sub-occupation NOC), asserting for every case `status != "SUBSTANTIATED"`, `status ∈ {AT-RISK,GAP,N/A}`, keys exactly `PUBLIC_FIELDS` (no `crs_points`/`score`/`substantiated_points` key — so no non-zero CRS/points delta is even representable), and `confirmed_count <= duty_count`. Spot-checks the poles (absent NOC → N/A; all-confirmed-fresh → `AT-RISK duty_review_manual`; changed-sha counted once).
  - **`TestFrozenSurfacesByteIdentity`** — `git diff --quiet HEAD -- <path>` byte-identity over the FREEZE set (`crawler/auditors/core.py`, `crawler/crs_audit.py`, `crawler/models/audit.py`, `crawler/auditors/__init__.py`), skip-guarded off a git checkout via `_git_root`.
  - **`TestSidecarInert`** — `noc_review.review_noc_duties` is not any registered decider value, `review.noc` resolves to the fail-closed default and is absent from `_REGISTRY`, no NOC-flavoured factor is on `FULL_GRID_FACTORS`, and a prose-immune AST scan proves the sidecar imports nothing from `crawler.auditors`.
  - **`TestSidecarPiiLightClosedSet`** — the returned dict keys equal the closed `PUBLIC_FIELDS` exactly (structural + a live all-confirmed run), with no `ev_` id or absolute path and only the PII-light chunk_id citation set.
  - **`TestCoreWorkFactorIsolation` (B1)** — seeds + confirms a real `core.work` claim (verdict `SUBSTANTIATED`), then audits `core.work` at three snapshots (pre-worksheet baseline, post-worksheet, post-confirmation of the lead + 4 duties): the `PrivateFactorCard` is byte-for-behavior AND full-`model_dump()` IDENTICAL across all three; no NOC evidence id enters the card; `audit_eligible_values("core.work")` never returns a `review.noc` value; the sidecar meanwhile genuinely counts the confirmations (proving isolation ≠ no-op) yet never greens; and no NOC id appears in a built single-factor OR full-grid `PublicAuditEnvelope`.
  - **`TestIdempotentRegenerationIsolation` (B1 / T43-09)** — an EXACT rerun returns the identical `{worksheet_doc_id, value_ids, duty_count}`, mints no duplicate `review.noc` row, preserves each confirmed value's state, and leaves the `core.work` card byte-identical to baseline; a changed-`duty_sha` rerun (old superseded-sha value + fresh current value, both confirmed) counts the duty exactly once (`confirmed_count == 1 <= duty_count`), leaves the old drifted value untouched, never greens, and keeps the `core.work` card byte-identical.

## Task Commits

Each task was committed atomically:

1. **Task 1: extend no-inlined-volatile gate to both NOC modules** — `a77dc81` (test)
2. **Task 2: v5 NOC never-auto-green negative-control conformance** — `6aeb082` (test)

**Plan metadata:** _(final docs commit — see completion)_

## Files Created/Modified

- `crawler/tests/test_conformance_v5_noc_no_auto_green.py` (686 lines, **created**) — the six-class NOC-03 negative control (sweep + FREEZE-set byte-identity + inertness + closed PII-light set + B1 factor-isolation + idempotent-regeneration + envelope inertness).
- `crawler/tests/test_crs_no_inlined_rules.py` (+10 lines) — `_EXPORT_MODULES` extended with both NOC modules under a Phase-43 comment.

## Decisions Made

- The `v5` prefix keeps the file deliberately OUTSIDE the v4.x release-gate glob `test_conformance_v4[01]_*.py`; `scripts/run_conformance.py` was verified byte-clean (untouched). Phase 46 introduces the v5 glob.
- The B1 proof uses TWO corpora in one vault — a synthetic `core.work` index (`self.db`, cited verbatim by a synthetic registry) for the frozen-grid audit and the pinned NOC corpus (`real_db`) for the worksheet generator — so a cross-factor leak would break the byte-identity assertion.
- Byte-identity is asserted at both the named-field fingerprint AND the full `PrivateFactorCard.model_dump()` level.
- NOC-01/NOC-02/NOC-03 are marked complete here (Plans 01–03 held them Pending until this freeze/conformance proof landed).

## Deviations from Plan

### Auto-fixed Issues

None — the plan executed exactly as written for both tasks (no code deviations, no auto-fixes, no architectural changes, no package installs, no authentication gates). The only production surfaces touched are the two named test files; every frozen surface shows zero diff vs HEAD (proven by the new byte-identity test itself).

## Issues Encountered

- Consistent with the 43-01/43-02/43-03 precedent, the plan's `<verification>` names `.venv/bin/python -m pytest -q` (the whole `crawler/tests` sweep). Part of that sweep is real-network integration/seam suites (`test_full_audit_real_seam.py`, `test_dli_snapshot.py`, `test_dli_conformance.py`, `test_dli_grounding.py`) plus the heavy full-corpus duplicate-audit files (`test_dupaudit.py::TestRealCorpus`, `test_dupclean.py`) that hang / run for minutes offline. Those were excluded; the remaining **935 offline tests passed (1 skipped, 439 subtests)** with no regression. This plan's changes are TEST-ONLY, and the new byte-identity test independently proves the frozen production surfaces drifted zero.

## Verification Results

- `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_noc_no_auto_green.py -q` → **12 passed, 14 subtests** (no skips — corpus + git both present).
- `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_noc_no_auto_green.py crawler/tests/test_crs_no_inlined_rules.py -q` → **16 passed, 14 subtests** (negative control + static gate green).
- Directly-relevant regression (`test_noc_review*`, `test_auditor*`, `test_conformance_v40/41*`, `test_physician_policy`, the v5 policy mirror) → **136 passed, 213 subtests**.
- Full offline suite (excluding the 4 real-network seams + 2 heavy full-corpus dup-audit files) → **935 passed, 1 skipped, 439 subtests** in ~112s (no regression).
- FREEZE-set byte-identity: `git diff --quiet HEAD` over all four frozen surfaces → **CLEAN** (zero drift).
- v5 file outside the release-gate glob: `glob("test_conformance_v4[01]_*.py")` does **not** capture the v5 file (9 files matched, none the v5). `scripts/run_conformance.py` → **CLEAN** (untouched).
- `.venv/bin/python scripts/check_publish_safe.py` → **0 violations** (428 tracked files, including the new test file).
- No-new-dependency gate: `git diff 2636670 HEAD -- pyproject.toml poetry.lock` → **empty**.

## Known Stubs

None — the conformance module drives the SHIPPED generator + sidecar + auditor spine over grounded corpus fixtures; there are no hardcoded empty values, placeholder text, or unwired data sources on the new test surface.

## Threat Flags

None — this plan adds only test surface; it introduces no new network endpoint, auth path, file-access pattern, or schema change. Every threat in the plan's register (T43-02/03/04/06/07/08/09) is now covered by an executing assertion.

## Next Phase Readiness

- **Phase 45 (MEC integrator):** the inert, never-green `review_noc_duties` is now release-gate-proven — it can be consumed LATER as an `AT-RISK` human-confirmed skilled-work input with certainty it can never contribute an automatic award or perturb the frozen `core.work` grid.
- **Phase 46 (v5 release-gate glob):** this file is intentionally staged for the future `test_conformance_v5_*.py` gate; wiring it into `scripts/run_conformance.py` is Phase 46's job (not done here).
- **REQUIREMENTS:** NOC-01, NOC-02, NOC-03 are now complete — the worksheet view, the per-duty confirm flow, and the never-auto-green / frozen-surface conformance proof have all landed.

---
*Phase: 43-enhanced-noc-work-duty-review-worksheet*
*Completed: 2026-07-19*

## Self-Check: PASSED
- Files verified on disk: `crawler/tests/test_conformance_v5_noc_no_auto_green.py`, `crawler/tests/test_crs_no_inlined_rules.py`, `43-04-SUMMARY.md` — all FOUND.
- Commits verified in git history: `a77dc81` (Task 1 gate extension), `6aeb082` (Task 2 v5 negative control) — all FOUND.
