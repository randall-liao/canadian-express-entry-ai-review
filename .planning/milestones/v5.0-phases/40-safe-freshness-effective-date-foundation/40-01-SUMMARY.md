---
phase: 40-safe-freshness-effective-date-foundation
plan: 01
subsystem: testing
tags: [crs-registry, freshness, effective-date, staleness, grounding, fail-closed, safe-09, pydantic]

# Dependency graph
requires:
  - phase: 31-crs-rule-registry
    provides: "within_validity / _in_window / _window_days / registry_fingerprint primitives + synthetic grounded RuleRow fixtures reused here"
provides:
  - "crawler.crs_audit.within_freshness — fail-closed grounded max-age (staleness) check"
  - "crawler.crs_audit.row_in_effect — effective-window predicate over both grounded window sources"
  - "crawler.crs_audit._FRESHNESS_FIELD — kind→grounded-field-name contract (snapshot_max_age) for Phase 41's real DLI row"
  - "SAFE-09 negative-control test surface (out-of-window / stale / after-reference / no-window) + registry_fingerprint drift coverage over a freshness-bound row shape"
affects: [phase-41-dli-snapshot, phase-42-policy-resolver, phase-44-study-gate, phase-45-mec-sidecar, phase-46-conformance-release-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fail-closed grounded-window helper (no grounded window ⇒ False), mirroring within_validity"
    - "Effective-window composition (row_in_effect) over machine_check + volatility windows via _in_window"
    - "Field-name contract map (STRINGS only) so a future grounded value is drift-covered without inlining"

key-files:
  created:
    - crawler/tests/test_freshness_staleness.py
  modified:
    - crawler/crs_audit.py
    - crawler/tests/test_crs_rules.py

key-decisions:
  - "No concrete DLI snapshot max-age bound row shipped this phase — deferred to Phase 41 (no authoritative max-age is groundable in the current corpus); SAFE-09 proven with synthetic grounded validity_window fixtures"
  - "SAFE-09 left Pending in REQUIREMENTS/ROADMAP — it is shared with plan 40-02 and only fully delivered when the phase completes, so marking it complete after 40-01 would be premature"
  - "New helpers are additive siblings only — within_validity / _in_window / arranged_employment_guard kept byte-for-byte frozen (diff is 54 insertions, 0 deletions)"

patterns-established:
  - "Pattern 1 (Freshness-from-a-grounded-window): within_freshness reads the max-age window from a grounded validity_window row via _window_days, never an inlined literal; fails closed on no-window/stale/after-reference"
  - "Pattern 2 (Effective-window composition): row_in_effect composes _in_window over both machine_check and volatility effective windows; both-None ⇒ stable/effective"

requirements-completed: []  # SAFE-09 remains Pending — shared with plan 40-02 (see Decisions)

# Metrics
duration: ~24min
completed: 2026-07-18
---

# Phase 40 Plan 01: SAFE Freshness & Effective-Date Foundation Summary

**Fail-closed `within_freshness` (grounded max-age staleness) + `row_in_effect` (effective-window composition) shipped as additive siblings beside the frozen `within_validity`/`_in_window` primitives, proven with out-of-window / stale / after-reference / no-window negative controls and `registry_fingerprint` drift coverage over a `snapshot_max_age` row shape.**

## Performance

- **Duration:** ~24 min (dominated by the ~17-min full `crawler/tests` phase-gate run)
- **Started:** 2026-07-18T02:54:25Z
- **Completed:** 2026-07-18T03:18:28Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- `within_freshness(kind, crawl_date, reference_date, registry)` — reads the max-age window from a grounded `validity_window` row via the shipped `_window_days` reader (never an inlined default) and returns `False` when there is no grounded window, when the crawl is older than the window (stale), or when the crawl is after the reference date. This is the "stale never greens" half of the milestone's dominant safety invariant (SAFE-09, threat T-40-01).
- `row_in_effect(row, reference_date)` — composes `_in_window` over BOTH grounded window sources a row carries (`machine_check.effective_from/to` and `volatility.effective_from/to`); outside EITHER window ⇒ not in effect; a row whose windows are both `None` is stable/effective. This consolidates the exact pair of window checks `arranged_employment_guard` performs, exposed as a separately-callable helper for later screens.
- `_FRESHNESS_FIELD = {"dli_snapshot": "snapshot_max_age"}` — a STRINGS-only kind→grounded-field-name contract; no volatile number lives in code, so the module self-scan stays `[]`. `snapshot_max_age` is the frozen field name Phase 41's real grounded DLI row will populate.
- SAFE-09 negative-control test suite (`test_freshness_staleness.py`) built entirely on synthetic grounded fixtures — no real corpus/registry, no dependency on the not-yet-existent DLI corpus family.
- `registry_fingerprint` drift coverage proven to extend automatically to a `snapshot_max_age` `validity_window` row shape: tampering `window_days` (180 → 365) flips the sha256; byte-identical registries fingerprint equal.

## Task Commits

Each task was committed atomically (Task 1 followed the TDD RED→GREEN cycle):

1. **Task 40-01-01 (RED): failing SAFE-09 freshness/effective-date negative controls** — `142ff92` (test)
2. **Task 40-01-01 (GREEN): fail-closed `within_freshness` + `row_in_effect` + `_FRESHNESS_FIELD`** — `418f018` (feat)
3. **Task 40-01-02: `registry_fingerprint` drift coverage over a freshness-bound row shape** — `4eb6310` (test)

**Plan metadata:** committed separately with this SUMMARY + tracking updates (docs).

_No REFACTOR commit was needed — the GREEN implementation cleanly mirrors the existing `within_validity`/`_in_window` shape._

## Files Created/Modified

- `crawler/tests/test_freshness_staleness.py` (created) — `TestWithinFreshness` (in-window / stale / after-reference / no-window / unknown-kind), `TestRowInEffect` (out-of-machine_check-window / out-of-volatility-window / both-None-in-effect), and `TestNewFreshnessHelpersNoInline` (self-scan re-assertion over the modified module). Uses a synthetic `_freshness_registry()` grounded `snapshot_max_age` window fixture.
- `crawler/crs_audit.py` (modified, +54/-0) — added `_FRESHNESS_FIELD`, `within_freshness`, `row_in_effect`, plus two public-surface docstring entries. `within_validity`, `_in_window`, `arranged_employment_guard` untouched (byte-for-byte frozen).
- `crawler/tests/test_crs_rules.py` (modified, +45) — added `TestSnapshotFreshnessBoundFingerprint` (stable 64-hex sha256, identical-registries-equal, window_days-tamper-flips-fingerprint).

## Decisions Made

- **Honest grounding deferral (Assumption A2 / Open Question 1):** The CONCRETE grounded DLI snapshot max-age value and its authoritative citation are a Phase 41 (STUDY-01) data responsibility. A probe of the shipped registry + the current corpus confirms no authoritative "list refreshed every N days" / max-age span is groundable today. Shipping a non-gap bound row would fail whole-registry grounding conformance; a `gap:true` non-required `safe.*` row would fail `test_gap_rows_are_surfaced_by_coverage`. Therefore SAFE-09's "grounded/config value, never inlined" and "drift-covered" properties are proven with SYNTHETIC grounded `validity_window` fixtures (exactly how `_validity_registry()` proves `within_validity`). The mechanism fails closed (no grounded window ⇒ `False`); `_FRESHNESS_FIELD` ships the field-name contract Phase 41's real row will populate. The shipped `crawler/data/crs_rules/*.yaml` registry and `COVERAGE.md` are byte-for-byte unchanged (`git status --porcelain crawler/data/crs_rules/` is empty).
- **SAFE-09 left `Pending` in tracking:** SAFE-09 is a phase-level requirement claimed by BOTH plan 40-01 and plan 40-02 (which promotes the shared grounding gate). It is not fully delivered until the phase completes, so it was intentionally NOT marked complete after 40-01 — marking it now would misreport a partial delivery. ROADMAP/STATE reflect plan progress (1/3) only.
- **Additive-siblings freeze:** The new helpers are never wired into any shipped decider (that would change the frozen CRS grid — out of scope). The diff to `crawler/crs_audit.py` is purely additive (54 insertions, 0 deletions).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. All targeted verifications and acceptance criteria passed on the first implementation pass; the full `crawler/tests` phase gate is green.

## Verification Evidence

- **Task 40-01-01 verify:** `.venv/bin/python -m pytest crawler/tests/test_freshness_staleness.py crawler/tests/test_crs_audit.py -x -q` → **37 passed**.
- **Acceptance (40-01-01):**
  - `grep -n "def within_freshness" crawler/crs_audit.py` → exactly 1 hit (line 173); `grep -n "def row_in_effect" crawler/crs_audit.py` → exactly 1 hit (line 377).
  - `_FRESHNESS_FIELD = {"dli_snapshot": "snapshot_max_age"}` (strings-only, line 47).
  - `within_freshness('dli_snapshot','2026-07-06','2026-07-06', Registry(rows=[]))` prints `False` (fail-closed no-window).
  - `crs_rules.no_inlined_volatile_rules(['crawler/crs_audit.py'])` → `[]` (self-scan clean).
  - `crs_audit.py` diff: 54 insertions, 0 deletions (frozen functions unchanged).
- **Task 40-01-02 verify:** `.venv/bin/python -m pytest crawler/tests/test_crs_rules.py crawler/tests/test_crs_no_inlined_rules.py -k "fingerprint or no_inlined or freshness" -x -q` → **10 passed, 13 deselected**.
- **Acceptance (40-01-02):**
  - `git status --porcelain crawler/data/crs_rules/` → empty (registry + COVERAGE.md untouched).
  - `pytest crawler/tests/test_crs_rules.py -q` → **19 passed**.
  - `pytest crawler/tests/test_crs_no_inlined_rules.py -q` → **4 passed**.
  - `pytest crawler/tests/test_conformance_v40_retrieve_what_you_cite.py -q` → **11 passed, 35 subtests passed**.
- **Frozen-grid regression:** `pytest crawler/tests/test_crs_audit.py crawler/tests/test_auditor.py crawler/tests/test_auditor_dispatch.py -q` → **49 passed**.
- **Wave/phase gate:** `.venv/bin/python -m pytest crawler/tests -q` → **863 passed, 1 skipped, 355 subtests passed** (0:16:51).

## Threat Model Coverage

- **T-40-01 (Tampering of freshness, HIGH):** mitigated — `within_freshness` returns `False` on missing window, stale (`delta > window`), and after-reference (`delta < 0`); `row_in_effect` returns `False` outside either window source. Proven with negative controls, not current-dated fixtures.
- **T-40-02 (ungrounded bound, HIGH):** mitigated — no numeric default in the new helpers; bound read via `_window_days`; `no_inlined_volatile_rules(["crawler/crs_audit.py"]) == []` re-asserted; drift coverage proven over the bound-row shape.
- **T-40-A2 (fabricated citation, MEDIUM):** accepted/deferred — no concrete bound row shipped; DLI max-age + citation deferred to Phase 41; `git status` on the registry is clean.
- **T-40-SC (supply-chain, LOW):** N/A — zero new runtime dependencies (stdlib-only tests).

## Next Phase Readiness

- `within_freshness` / `row_in_effect` / `_FRESHNESS_FIELD` are discoverable, separately-callable helpers ready for Phases 42/44/45 to wire and Phase 46 to prove centrally.
- Plan 40-02 (promote `_gate_or_raise` → public `gate_subset`) is the remaining Wave 1 plan; it completes the other half of SAFE-09. Plan 40-03 (SAFE-10 snapshot preflight) is Wave 2, blocked on Wave 1.
- Phase 41 must populate the real grounded DLI `snapshot_max_age` row against `_FRESHNESS_FIELD`'s field-name contract before any DLI snapshot freshness check can consume a shipped bound.

---
*Phase: 40-safe-freshness-effective-date-foundation*
*Completed: 2026-07-18*

## Self-Check: PASSED

- Files verified present: `crawler/tests/test_freshness_staleness.py`, `crawler/crs_audit.py`, `crawler/tests/test_crs_rules.py`, `.planning/phases/40-safe-freshness-effective-date-foundation/40-01-SUMMARY.md`.
- Commits verified in history: `142ff92` (RED test), `418f018` (GREEN feat), `4eb6310` (fingerprint drift test).
- New symbols present in `crawler/crs_audit.py`: `within_freshness`, `row_in_effect`, `_FRESHNESS_FIELD`.
