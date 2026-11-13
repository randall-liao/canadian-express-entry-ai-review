---
phase: 40-safe-freshness-effective-date-foundation
plan: 03
subsystem: api
tags: [snapshot-preflight, index-health, fail-closed, safe-10, freshness, read-only-sqlite, zero-artifact, pii-perimeter]

# Dependency graph
requires:
  - phase: 36-operational-hardening
    provides: "index_health.probe_index / IndexHealth / INDEX_* + cli._require_readable_index / _vault_fail (HARD-01/02) — the byte-frozen preflight this plan mirrors additively"
  - phase: 40-safe-freshness-effective-date-foundation
    provides: "40-01 within_freshness/_FRESHNESS_FIELD staleness idiom + crs_audit._as_date date coercion reused by the stale check"
provides:
  - "crawler.index_health.probe_snapshot(db, family, *, max_age_days=None, as_of=None) -> SnapshotHealth — read-only, side-effect-free required-corpus-family classifier over the closed SNAPSHOT_* vocabulary"
  - "crawler.index_health.SnapshotHealth frozen dataclass (.ok(), PII-free .message(db)) + SNAPSHOT_OK/_MISSING/_EMPTY/_UNREADABLE/_CORRUPT/_DRIFTED/_STALE closed reason codes + _INDEX_TO_SNAPSHOT base map"
  - "crawler.cli._require_readable_snapshot(args, db, family, max_age_days) -> int | None — preflight wrapper turning any non-ok health into ONE frozen invalid_input/exit-2 refusal, None when healthy (defined-only; no verb wired this phase)"
  - "crawler/tests/test_snapshot_health.py + test_snapshot_refusal.py — SAFE-10 closed-code classification table + CLI refusal/zero-artifact/PII-perimeter/healthy positive control"
affects: [phase-41-dli-pgwp-snapshot-family, phase-44-study-dli-pgwp-evidence-gate, phase-45-mec-program-eligibility-sidecar, phase-46-safe-conformance-release-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive mirror preflight: probe_snapshot REUSES the frozen probe_index for missing/empty/unreadable/corrupt/drifted base classes (via _INDEX_TO_SNAPSHOT) and only adds family-scoped snapshot_missing + freshness-scoped snapshot_stale — the frozen original stays byte-stable"
    - "Caller-supplied staleness bound: max_age_days has NO numeric default in index_health (SAFE-09 no-inlined-volatile rule); the caller reads the grounded window and passes it in, and a family that cannot prove its age fails closed to stale"
    - "Zero-artifact preflight ordering: the CLI wrapper refuses BEFORE any open_vault (mirrors _cmd_vault_audit), reusing contract.INVALID_INPUT/EXIT_INVALID_INPUT so a refusal writes no audit/report/database artifact"

key-files:
  created:
    - crawler/tests/test_snapshot_health.py
    - crawler/tests/test_snapshot_refusal.py
  modified:
    - crawler/index_health.py
    - crawler/cli.py

key-decisions:
  - "probe_snapshot is a SEPARATE function (not a new parameter on probe_index) so the frozen probe_index signature + test_index_health.py grid stay byte-stable (Assumption A3); it reuses probe_index internally rather than re-implementing the base classification."
  - "Per-row snapshot drift maps non-str text OR chunk_sha mismatch to SNAPSHOT_DRIFTED (the plan's family-scoped rule), distinct from probe_index which classifies non-str text as CORRUPT; the reused chunk_sha fingerprint is never re-invented."
  - "The stale check fails closed: an all-blank/empty crawl_date set (cannot prove age) returns SNAPSHOT_STALE rather than passing, so a family that cannot substantiate its freshness never greens (T-40-04 mitigation)."
  - "_require_readable_snapshot is defined-only this phase — NOT wired into _cmd_vault_audit or any decider (Assumption A5); the verbs that call it are Phase 44/45, so it is proven via a fixture-driven direct-call refusal test, keeping the frozen CRS grid unchanged."
  - "probe_snapshot signature left unannotated per-param (matching the plan reference + the AC grep for the literal 'max_age_days=None') rather than adding 'int | None' annotations that PEP8-space the '=' and break the acceptance grep."

patterns-established:
  - "Pattern 4 (Snapshot preflight → clean refusal, zero artifacts): a read-only required-family classifier + a preflight-first CLI wrapper on the frozen invalid_input/exit-2 contract, reusing probe_index + chunk_sha + _as_date + _vault_fail (no new trust path, no new dependency)."

requirements-completed: [SAFE-10]

# Metrics
duration: ~24min
completed: 2026-07-18
---

# Phase 40 Plan 03: SAFE Freshness & Effective-Date Foundation Summary

**Shipped the SAFE-10 snapshot preflight MECHANISM — a read-only, side-effect-free `probe_snapshot` that classifies a required corpus family into the closed `SNAPSHOT_OK/_MISSING/_EMPTY/_UNREADABLE/_CORRUPT/_DRIFTED/_STALE` vocabulary (additively reusing the frozen `probe_index` for the base classes + `chunk_sha` for drift + a caller-supplied `max_age_days` for staleness), plus a `cli._require_readable_snapshot` wrapper that turns any non-ok health into ONE frozen `invalid_input`/exit-2 refusal with a PII-free `reason=snapshot_<code>` token BEFORE any `open_vault` so a refusal writes zero artifacts, and returns `None` for a healthy family — proven against SYNTHETIC fixture families only (no `corpus/dli/` dependency).**

## Performance

- **Duration:** ~24 min (dominated by the ~15-min full `crawler/tests` phase-gate run)
- **Started:** 2026-07-18T03:50:00Z
- **Completed:** 2026-07-18T04:14:15Z
- **Tasks:** 2 (Task 40-03-01 was TDD → 2 commits; Task 40-03-02 → 1 commit)
- **Files modified:** 4 (2 created, 2 modified) — +446 lines

## Accomplishments
- `probe_snapshot` + `SnapshotHealth` + seven `SNAPSHOT_*` closed reason codes + `_INDEX_TO_SNAPSHOT` base map added to `crawler/index_health.py` — read-only (`file:<db>?mode=ro`), side-effect-free, parameter-bound `WHERE relpath LIKE ?` (SQLi-safe), whole post-connect body guarded to `snapshot_corrupt`.
- Freshness classification: newest `crawl_date` beyond the caller-supplied `max_age_days` → `snapshot_stale`; a family whose dates are all blank fails closed to `snapshot_stale`; `max_age_days=None` skips the stale check; NO numeric max-age default inlined (SAFE-09).
- `cli._require_readable_snapshot` preflight wrapper on the frozen `contract.INVALID_INPUT` / `EXIT_INVALID_INPUT` (exit 2) path via `_vault_fail`, PII-free `reason=snapshot_<code>`, returns `None` for a healthy family (SC4) — defined-only, no verb wired.
- Two new test files: `test_snapshot_health.py` (12 tests — one per closed code + read-only `assertFalse(db.exists())` proof + fail-closed blank-date stale + `max_age_days=None` skip + PII-free message) and `test_snapshot_refusal.py` (6 tests — missing/drifted/stale refusals, zero-artifact `audit_runs==0`/no report files, non-json stderr path, healthy positive control).
- Frozen originals untouched: `probe_index`, `IndexHealth`, `INDEX_*`, `_REQUIRED_TABLES`, `_DRIFT_SAMPLE`, `_require_readable_index`, and `test_index_health.py`/`test_audit_index_refusal.py` all stay byte-for-byte and green.

## Task Commits

Each task was committed atomically (every commit carries the required `Co-authored-by: Copilot` trailer):

1. **Task 40-03-01 (TDD RED): failing SAFE-10 classification table** — `0ee89c3` (test)
2. **Task 40-03-01 (TDD GREEN): probe_snapshot + SnapshotHealth + SNAPSHOT_* codes** — `ba64671` (feat)
3. **Task 40-03-02: _require_readable_snapshot CLI preflight + refusal test** — `3818c0d` (feat)

**Plan metadata:** _(this commit)_ `docs(40-03): complete SAFE-10 snapshot preflight plan`

_Note: Task 40-03-01 was TDD (`tdd="true"`) → RED then GREEN commits; no REFACTOR needed (implementation mirrored `probe_index` cleanly on first pass)._

## Files Created/Modified
- `crawler/index_health.py` — added `SNAPSHOT_*` closed vocab, `_INDEX_TO_SNAPSHOT` map, `SnapshotHealth` frozen dataclass, and `probe_snapshot()` (strictly additive; `probe_index`/`IndexHealth`/`INDEX_*` unchanged).
- `crawler/cli.py` — added `_require_readable_snapshot()` beside `_require_readable_index()` (defined-only; not wired to any verb/decider).
- `crawler/tests/test_snapshot_health.py` — `ProbeSnapshotReasonCodes` closed-code table + `_build_snapshot_index` synthetic tempdir fixture helper.
- `crawler/tests/test_snapshot_refusal.py` — CLI refusal + zero-artifact + PII-perimeter + healthy positive control (drives the wrapper directly; imports the Task-01 fixture helper).

## Decisions Made
- **Separate `probe_snapshot`, reuse `probe_index`.** Keeps the frozen index preflight byte-stable (Assumption A3) while classifying a required *family* on top of it — the two new codes (`snapshot_missing`, `snapshot_stale`) sit atop the reused missing/empty/unreadable/corrupt/drifted base via `_INDEX_TO_SNAPSHOT`.
- **Fail-closed freshness.** A family that cannot prove its age (all-blank `crawl_date`) is `snapshot_stale`, never OK (T-40-04). The bound is always caller-supplied — `index_health` inlines no numeric max-age (SAFE-09 no-inlined-volatile rule).
- **Defined-only wrapper.** Per Assumption A5, no user-facing verb is added and the wrapper is not wired into `_cmd_vault_audit` or any decider; it is proven via a fixture-driven direct-call refusal test so the frozen CRS grid does not change.
- **Unannotated signature** to satisfy the plan reference + the acceptance grep for the literal `max_age_days=None`.

## Deviations from Plan

None - plan executed exactly as written.

_(The plan's reference `probe_snapshot` signature is unannotated per-param; an initial annotated draft (`max_age_days: "int | None" = None`) was corrected to the unannotated form before any commit to match the plan and its `grep -n "max_age_days=None"` acceptance criterion. This was a pre-commit alignment to the plan, not a deviation from it.)_

## Verification Evidence

All plan `<verification>` commands + both tasks' `<acceptance_criteria>` were run and pass:

- `.venv/bin/python -m pytest crawler/tests/test_snapshot_health.py crawler/tests/test_index_health.py -q` → **24 passed** (SAFE-10 classification table + frozen `probe_index` regression).
- `.venv/bin/python -m pytest crawler/tests/test_snapshot_refusal.py -q` → **6 passed** (refusal exit 2 + `reason=snapshot_*` PII-free; zero-artifact `audit_runs==0`/no report files; healthy → `None`).
- `.venv/bin/python -m pytest crawler/tests/test_audit_index_refusal.py -q` → green (frozen index refusal unchanged).
- **AC greps:** exactly one `def probe_snapshot` + one `class SnapshotHealth`; all seven `SNAPSHOT_*` defined; `relpath LIKE ?` parameter-bound; `max_age_days=None` present with NO numeric-default match; exactly one `def _require_readable_snapshot` calling `probe_snapshot` + `_vault_fail(..., INVALID_INPUT, ..., EXIT_INVALID_INPUT)` and NOT wired into any `_cmd_*` handler.
- **Wave/phase gate:** `.venv/bin/python -m pytest crawler/tests -q` → **885 passed, 1 skipped** (the LOCAL-ONLY git-ignored real-index positive control), 355 subtests passed. `scripts/check_publish_safe.py` → **0 violations** (380 tracked files). `scripts/run_conformance.py` → **PASS** (75 conformance tests).

## Known Stubs
None — no placeholder/empty-data stubs introduced. The absence of a shipped concrete DLI `snapshot_max_age` row is intentional and deferred to Phase 41 (STUDY-01) per the roadmap; Phase 40 ships the mechanism proven against synthetic grounded fixtures.

## Issues Encountered
None — the implementation mirrored the shipped `probe_index`/`_require_readable_index` precedent cleanly; the only pre-commit adjustment was the signature-annotation alignment noted above.

## User Setup Required
None - no external service configuration required (zero new runtime dependencies; `[project].dependencies` unchanged).

## Next Phase Readiness
- **SAFE-10 complete**; both Phase 40 requirements (SAFE-09 + SAFE-10) are now delivered. All three Phase 40 plans (40-01, 40-02, 40-03) are done.
- `probe_snapshot` + `_require_readable_snapshot` are ready for Phase 44 (STUDY DLI/PGWP evidence gate) and Phase 45 (MEC sidecar) to chain as the FIRST preflight — before `open_vault` — passing `max_age_days` read from the grounded validity window (Phase 41 ships the concrete DLI `snapshot_max_age` row + the real `corpus/dli/` family).
- No blockers. Phase completion is deferred to orchestrator verification (this plan does not mark the phase complete).

---

## Self-Check: PASSED

- **Created/modified files present on disk:** `crawler/index_health.py`, `crawler/cli.py`, `crawler/tests/test_snapshot_health.py`, `crawler/tests/test_snapshot_refusal.py`, `40-03-SUMMARY.md` — all FOUND.
- **Task commits present in git history:** `0ee89c3` (RED test), `ba64671` (GREEN feat), `3818c0d` (feat CLI wrapper) — all FOUND, each carrying the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer.
- **Acceptance criteria (both tasks) + plan verification + wave/phase gate:** all re-run and passing (see Verification Evidence). Full suite 885 passed / 1 skipped; publish-safe 0 violations; conformance PASS.

*Phase: 40-safe-freshness-effective-date-foundation*
*Completed: 2026-07-18*
