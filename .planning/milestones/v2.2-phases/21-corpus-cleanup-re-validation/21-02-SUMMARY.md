---
phase: 21-corpus-cleanup-re-validation
plan: 02
subsystem: testing
tags: [duplicate-cleanup, move-to-dropped, path-confinement, dry-run, audit-log, tdd-green]

# Dependency graph
requires:
  - phase: 21-corpus-cleanup-re-validation
    provides: "21-01 — crawler/dupclean.py interface contract (typed stubs) + crawler/tests/test_dupclean.py RED Wave-0 suite + _make_clean_corpus/_mint_report fixtures"
  - phase: 20-cross-family-duplicate-detection-audit-report
    provides: "duplicate-audit.json schema (clusters[].signals/canonical/members[].decision/family/url) via dupaudit.audit()+render_json()"
  - phase: pre-existing crawler primitives
    provides: "apply_verdicts move-to-_dropped + audit-log + is_file() idempotency precedent; dupaudit resolve()/relative_to confinement idiom; eval-sibling dual naming (Pitfall 5)"
provides:
  - "load_plan() — consumes duplicate-audit.json VERBATIM, returns only decision=='delete' targets, default-excludes overlap-only clusters (signals=={'overlap'}) behind include_overlap"
  - "confine() — path-traversal guard rejecting absolute / '..' relpaths before any move (threat T-21-01)"
  - "move_to_dropped() — recoverable shutil.move of the .md + its .eval.json sibling(s) in BOTH naming forms into the family _dropped/; idempotent is_file() no-op; never unlinks (T-21-03)"
  - "clean() — dry-run by default (zero fs changes, PLANNED-move count under the same `moved` key as apply); apply=True moves + writes per-family _dropped/duplicate-clean.log.json audit trail; move boundary asserts decision=='delete' (keep-canonical guarantee, T-21-02)"
affects: [21-03, 21-04, 21-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Report consumed verbatim — no canonical/decision recomputation (frozen from Phase 20)"
    - "Confine-before-move: every report relpath passes confine() prior to any shutil.move (T-21-01)"
    - "Dry-run by default, --apply to mutate; PLANNED count and ACTUAL count share the single `moved` key (Plan 05 gate asserts moved==10)"
    - "Re-validation hooks left as a clearly-separated TODO invoked only after a successful move pass (Plan 03 wiring)"

key-files:
  created: []
  modified:
    - crawler/dupclean.py

key-decisions:
  - "load_plan returns extra keys (decision/canonical/reason) beyond the contracted relpath/family/url/overlap_only so clean() can assert the keep-canonical invariant at the move boundary and write a rich audit record"
  - "retained_overlap_only computed by re-loading the plan with include_overlap=True and counting overlap_only targets (0 when scope is already widened)"
  - "Re-validation (prune_manifest/prune_completeness_orphans/revalidate_family/recheck_zero_clusters) intentionally NOT called yet — they still raise NotImplementedError; calling them would break the GREEN move tests. Left as a documented TODO block after the move pass."
  - "confine() uses defense-in-depth: reject is_absolute()/'..'-in-parts up front, THEN resolve()+parent-check, so escapes are refused even on path-separator edge cases"
  - "CLEAN-02 NOT marked complete this wave — it spans Plans 02–05 (real-corpus enactment is Plan 05); marking it now would be premature"

patterns-established:
  - "move_to_dropped mirrors apply_verdicts exactly: confine → is_file() idempotency guard → lazy _dropped/ mkdir → shutil.move doc + eval sibling(s) → never unlink"
  - "Audit trail appended (read-existing + concat) to per-family _dropped/duplicate-clean.log.json, timestamped via _now()"

requirements-completed: []  # CLEAN-02 spans Plans 02-05; not complete until real-corpus enactment (Plan 05)

# Metrics
duration: 4min
completed: 2026-06-11
---

# Phase 21 Plan 02: Report consumption, scoping gate, path-confinement & safe move-to-_dropped Summary

**Destructive-safety core of CLEAN-02: a dry-run-by-default `clean()` that moves only high-confidence non-canonical copies (+ both eval-sibling forms) into recoverable `_dropped/` quarantine, with overlap-only false positives excluded by default and `../`/absolute relpaths refused before any move.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-11T03:13:00Z
- **Completed:** 2026-06-11T03:16:00Z
- **Tasks:** 2 completed
- **Files modified:** 1 (`crawler/dupclean.py`)

## Accomplishments
- Implemented `load_plan()` — reads `duplicate-audit.json` verbatim, returns only `decision=="delete"` targets, default-excludes overlap-only (`signals=={"overlap"}`) clusters behind `include_overlap`; never returns canonicals.
- Implemented `confine()` path-traversal guard — rejects absolute paths and `..` escapes before any filesystem move (threat T-21-01).
- Implemented `move_to_dropped()` — recoverable `shutil.move` of the `.md` plus its `.eval.json` sibling(s) in BOTH naming forms (`<doc>.md.eval.json` and `<stem>.eval.json`) into the owning family's `_dropped/`; idempotent (`is_file()` no-op); never hard-deletes.
- Implemented `clean()` orchestrator — pure dry-run by default (corpus byte-identical), `apply=True` moves targets and writes a per-family `_dropped/duplicate-clean.log.json` audit trail; the move boundary asserts `decision=="delete"` (keep-canonical guarantee, T-21-02).
- TestScope, TestSecurity, TestDryRun, TestApply (moves-only-noncanonical / canonical-untouched / idempotent-reapply / eval-sibling-moved) all GREEN; TestGit became GREEN as a bonus.

## Task Commits

Each task was committed atomically:

1. **Task 1: load_plan() scoping gate + confine() path guard** - `adf49da` (feat)
2. **Task 2: move_to_dropped() + clean() dry-run/apply skeleton** - `a470bdf` (feat)

_Note: tasks were TDD-GREEN phases against the RED suite landed in Plan 21-01; no new RED commits were needed this wave._

## Files Created/Modified
- `crawler/dupclean.py` - Filled the Plan-02 stubs: `load_plan`, `confine`, `move_to_dropped`, and the `clean()` dry-run/apply move skeleton with the per-family audit trail. Re-validation stubs (`prune_manifest`/`prune_completeness_orphans`/`revalidate_family`/`recheck_zero_clusters`) remain `NotImplementedError` for Plan 03.

## Decisions Made
- **Re-validation deferred, not stubbed-into-clean():** Calling the Plan-03 functions from `clean()` now would raise `NotImplementedError` and break the GREEN move tests, so they are left as a clearly-separated `TODO(Plan 03)` block positioned after a successful move pass — exactly where they will be wired.
- **`load_plan` carries extra keys** (`decision`/`canonical`/`reason`) beyond the contracted four so `clean()` can assert the keep-canonical invariant at the move boundary and emit a rich audit record. The tests only read `relpath`/`overlap_only`, so extra keys are harmless.
- **`moved` is a single shared key:** PLANNED-move count in dry-run, ACTUAL-moved count in apply — satisfying the plan-check semantics that Plan 05's dry-run gate asserts `moved==10`.
- **CLEAN-02 not marked complete:** the requirement spans Plans 02–05; real-corpus enactment is Plan 05. Marking it now would misrepresent traceability.

## Deviations from Plan

None - plan executed exactly as written. Both `<automated>` verifications passed on first GREEN; no auto-fixes (Rules 1–3) or architectural escalations (Rule 4) were required.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required (stdlib + repo modules only; no new deps, no network).

## Known Stubs
The following remain intentional `NotImplementedError` stubs, scheduled for Plan 03 (re-validation) — this is by design, not incomplete work for this wave:
- `prune_manifest()` — `crawler/dupclean.py`
- `prune_completeness_orphans()` — `crawler/dupclean.py`
- `revalidate_family()` — `crawler/dupclean.py`
- `recheck_zero_clusters()` — `crawler/dupclean.py`

Consequently `TestRecheck` and `TestRevalidate` (manifest/completeness/report) remain RED, as expected for this wave. `clean()` includes a documented `TODO(Plan 03)` call-site where these will be invoked after the move pass.

## Next Phase Readiness
- The destructive-safety core (scope gate + confinement + recoverable move + dry-run default + audit log) is in place and GREEN.
- Plan 03 wires the re-validation hooks (manifest prune, completeness-orphan prune, `REPORT.md` regeneration, zero-cluster re-check) into the `clean()` TODO block to turn `TestRecheck`/`TestRevalidate` GREEN.
- No blockers.

---
*Phase: 21-corpus-cleanup-re-validation*
*Completed: 2026-06-11*

## Self-Check: PASSED
- `crawler/dupclean.py` modified and present ✓
- Commit `adf49da` (Task 1) found in history ✓
- Commit `a470bdf` (Task 2) found in history ✓
- Target tests GREEN: TestContract, TestScope, TestSecurity, TestDryRun, TestApply (10/10) ✓
- `grep -nE "os\.remove|\.unlink\(|os\.unlink" crawler/dupclean.py` returns nothing ✓
- Later-wave tests RED as expected: TestRecheck, TestRevalidate (Plan 03) ✓
