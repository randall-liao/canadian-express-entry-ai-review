---
phase: 21-corpus-cleanup-re-validation
plan: 03
subsystem: testing
tags: [duplicate-cleanup, re-validation, manifest-prune, completeness-orphans, build-report, offline, tdd-green]

# Dependency graph
requires:
  - phase: 21-corpus-cleanup-re-validation
    provides: "21-02 — clean(apply=True) move-to-_dropped engine + per-family audit_by_family records (relpath/url/basename) + confine() guard"
  - phase: pre-existing crawler primitives
    provides: "apply_verdicts manifest-prune pattern (drop dropped URLs, sorted/indented rewrite); completeness.build_report offline --report path + live_docs glob; dupaudit.live_docs live-set enumeration"
provides:
  - "prune_manifest(corpus_root, family, urls) — drops the moved docs' normalized URLs from <family>/manifest.json so it mirrors the live corpus; sorted/indented rewrite; no-op if absent/empty; returns prune count"
  - "prune_completeness_orphans(corpus_root, family, moved_basenames) — drops orphaned sample.json pairs, MOVES the matching .live.md/.check.json into _dropped/ (never hard-delete; T-21-03), sets sampled to remaining pair count; returns sidecars pruned"
  - "revalidate_family(corpus_root, family) — thin offline wrapper over completeness.build_report regenerating <family>/REPORT.md with a recomputed live count; returns {family, live_docs, verdict}; never invokes --fetch/crawl4ai; never edits crawl_stats.json.recorded"
  - "clean(apply=True) re-validation wiring — per touched family: prune_manifest → prune_completeness_orphans → revalidate_family; returns live_before/live_after (recomputed by globbing), moved, skipped, retained_overlap_only, and per-family results [{family, verdict, live_docs, pruned_urls, regenerated_report}]"
affects: [21-04, 21-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Re-validation runs ONLY on touched families (audit_by_family keys) and ONLY after a successful move pass"
    - "Live count of record is recomputed by globbing (build_report.live_docs / dupaudit.live_docs), never read from / written to crawl_stats.json.recorded"
    - "Orphaned completeness sidecars are MOVED to _dropped/ (recoverable), never unlinked — same no-hard-delete invariant as the doc move"
    - "Report members' URLs are already normalized by Phase 20 dupaudit, so they match manifest keys directly (mirrors apply_verdicts using a['url'] verbatim)"

key-files:
  created: []
  modified:
    - crawler/dupclean.py

key-decisions:
  - "revalidate_family is a thin wrapper over completeness.build_report only (no internal prune) — clean() orchestrates prune_manifest → prune_completeness_orphans → revalidate_family in that order, per Task 2 behavior"
  - "live_before/live_after computed via sum(1 for _ in dupaudit.live_docs(...)) because live_docs is a generator (no len()) — corpus-wide before/after delta"
  - "prune_completeness_orphans collects orphaned sidecar names from BOTH the pair's recorded live/check fields AND the doc-stem derivation, so a pair missing those keys still has its conventional <stem>.live.md/.check.json pruned"
  - "sample.json 'sampled' is set to the new len(pairs) so build_report's completeness_done = len(checks) >= sampled stays satisfiable after orphan removal"
  - "CLEAN-03 NOT marked complete this wave — the re-validation logic lands here but the real-corpus re-validated counts + zero-cluster proof complete in Plan 04 (recheck) / Plan 05 (real --apply); marking it now would be premature (same conservative stance as 21-02 for CLEAN-02)"

patterns-established:
  - "prune_manifest mirrors apply_verdicts.py:54-62 exactly (read JSON, filter out dropped URLs, rewrite sorted/indented)"
  - "Completeness sidecar moves confined via confine(corpus_root, f'{family}/completeness/{name}') before any shutil.move (T-21-01)"

requirements-completed: []  # CLEAN-03 re-validation logic implemented; requirement completes after Plan 05 real-corpus re-validation

# Metrics
duration: ~6min
completed: 2026-06-11
---

# Phase 21 Plan 03: CLEAN-03 Re-validation Summary

**After the move pass, `clean(apply=True)` now prunes each moved doc's URL from its family `manifest.json`, moves orphaned completeness sidecars to `_dropped/`, and regenerates `REPORT.md` offline via `completeness.build_report` with a recomputed live count — leaving the corpus self-consistent with zero dangling references.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-11T03:18:53Z
- **Completed:** 2026-06-11T03:23:14Z
- **Tasks:** 2 completed
- **Files modified:** 1 (`crawler/dupclean.py`)

## Accomplishments
- `prune_manifest` + `prune_completeness_orphans` implemented and wired into `clean(apply=True)` — `TestRevalidate.test_manifest_pruned` and `test_completeness_orphans_pruned` GREEN.
- `revalidate_family` implemented as an offline `build_report` wrapper; `clean(apply=True)` regenerates each touched family's `REPORT.md` and returns `live_before`/`live_after` plus per-family verdicts — `TestRevalidate.test_report_count_updated` GREEN.
- `TestGit.test_corpus_changes_stay_ignored` GREEN — every written/moved path stays inside the corpus tree.

## Task Commits

Each task was committed atomically:

1. **Task 1: prune_manifest + prune_completeness_orphans (+ wire prunes into clean)** - `7488b46` (feat)
2. **Task 2: revalidate_family + wire re-validation into clean(apply=True)** - `8da4d2e` (feat)

_Note: TDD GREEN-only phase against the existing Wave-0 RED suite — no new RED commits (tests already shipped in 21-01)._

## Files Created/Modified
- `crawler/dupclean.py` - Implemented `prune_manifest`, `prune_completeness_orphans`, `revalidate_family`; extended `clean(apply=True)` with the post-move re-validation pass and an enriched return dict (`live_before`/`live_after`/`moved`/`skipped`/`retained_overlap_only`/`families`).

## Test Results

```
python -m unittest crawler.tests.test_dupclean.TestRevalidate crawler.tests.test_dupclean.TestGit -v
```

| Test | Status |
|------|--------|
| TestRevalidate.test_manifest_pruned | ✅ GREEN |
| TestRevalidate.test_completeness_orphans_pruned | ✅ GREEN |
| TestRevalidate.test_report_count_updated | ✅ GREEN |
| TestGit.test_corpus_changes_stay_ignored | ✅ GREEN |
| TestContract / TestScope / TestDryRun / TestApply / TestSecurity | ✅ GREEN (no regressions) |
| TestRecheck.test_no_exact_or_url_clusters_after_apply | 🔴 RED (intentional — `recheck_zero_clusters` lands in Plan 04) |

Grep verification (from plan):
- `grep -n build_report crawler/dupclean.py` → offline `completeness.build_report` path used (line 296).
- `grep -n "fetch\|crawl4ai" crawler/dupclean.py` → only negative-affirmation comments/docstrings stating the offline constraint; **no import and no call** of the `--fetch`/crawl4ai path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `dupaudit.live_docs` is a generator, not a list**
- **Found during:** Task 2 verification (`TypeError: object of type 'generator' has no len()`)
- **Issue:** `live_before = len(dupaudit.live_docs(corpus_root))` failed because `live_docs` yields `(path, text)` pairs lazily.
- **Fix:** Replaced both call sites with `sum(1 for _ in dupaudit.live_docs(corpus_root))`.
- **Files modified:** `crawler/dupclean.py`
- **Commit:** `8da4d2e`

### Scope notes
- `revalidate_family` is a thin `build_report` wrapper (per Task 2 `<action>`); the prune steps are orchestrated by `clean()` rather than inside `revalidate_family`, despite the stub docstring phrasing "Prunes the family manifest + completeness orphans, then regenerates". The docstring was updated to clarify it wraps the offline `--report` path; orchestration order (prune_manifest → prune_completeness_orphans → revalidate_family) lives in `clean()`.

## Known Stubs

- `recheck_zero_clusters()` still raises `NotImplementedError` — **intentional**, lands in Plan 04 (its stub message currently reads "Plan 03", a pre-existing label inherited from 21-01; behavior is correct). `TestRecheck` stays RED until then, as specified.

## Threat Surface
No new security-relevant surface introduced. T-21-03 (denial-of-recovery) mitigated: orphaned `.live.md`/`.check.json` are MOVED to `_dropped/`, not unlinked. T-21-05 (crawl_stats tampering) accepted/avoided: module never edits `crawl_stats.json.recorded`. T-21-01 confinement preserved: completeness sidecar moves pass through `confine()`.

## Self-Check: PASSED
- `crawler/dupclean.py` exists with `prune_manifest`, `prune_completeness_orphans`, `revalidate_family` (3/3 defs found).
- Task commits `7488b46` and `8da4d2e` present in git history.
- `.planning/phases/21-corpus-cleanup-re-validation/21-03-SUMMARY.md` exists.
