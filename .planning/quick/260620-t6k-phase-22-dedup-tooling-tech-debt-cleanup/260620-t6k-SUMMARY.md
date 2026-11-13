---
phase: 22-dedup-tooling-tech-debt-cleanup
plan: 01
status: complete
subsystem: testing
tags: [dedup, dupclean, dupaudit, publish-safety, check_publish_safe, tech-debt, corpus]

# Dependency graph
requires:
  - phase: 20-dedup-audit
    provides: "dupaudit RPT-03 share-safety gate (check_publish_safe.scan_text render-then-gate pattern) mirrored here"
  - phase: 21-dedup-cleanup
    provides: "dupclean.main() --json contract output + clean()/recheck_zero_clusters() this gate now wraps"
provides:
  - "dupclean.py: lint-tight imports (no dead normalize_url) + --out removed from CLI"
  - "dupclean.py: fail-closed RPT-03 publish-safety self-gate on emitted stdout (EXIT_INTERNAL_ERROR on any abs-path/secret/PII)"
  - "test_dupclean.py: TestPublishSafe (clean passes; poisoned fails closed)"
  - "test_dupaudit.py: corrected 742 real-corpus assertion + TestEmptyFamily robustness regression"
affects: [dedup-tooling, corpus-share-safety]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RPT-03 render-then-gate-then-emit: build emit payload → render to string → cps.scan_text → fail closed BEFORE emitting"
tech-stack-removed: []

key-files:
  created: []
  modified:
    - crawler/dupclean.py
    - crawler/tests/test_dupclean.py
    - crawler/tests/test_dupaudit.py

key-decisions:
  - "Only the genuinely-dead import symbol (normalize_url) and the unused --out arg are removed; dupaudit's consumed --out and the '752-filter' docstring labels are out of scope (no naming churn)."
  - "dupclean's gate scope is its shareable stdout contract output only; the in-corpus regenerated REPORT.md files live under git-ignored corpus/ and are never shared."
  - "Only the real-corpus COUNT assertion changed 752->742; every '752-filter' docstring LABEL left untouched (names the filter logic, not a count; renaming risks confusion vs the historical v2.1 752-live-docs record)."
  - "Item 5 needs NO production-code change — empty/manifest-only families already handled gracefully; the tracked deliverable is a regression test that locks that in."

patterns-established:
  - "Publish-safety self-gate: any tool that emits a public stdout contract surface renders its payload and routes it through check_publish_safe.scan_text, failing closed with EXIT_INTERNAL_ERROR."

requirements-completed: [W1, W2, W3, W4]

# Metrics
duration: 8min
completed: 2026-06-20
---

# Phase 22 Plan 01: Dedup Tooling Tech-Debt Cleanup Summary

**Closed the v2.2 dedup-tooling tech debt: removed dead `normalize_url`/`--out` from `dupclean`, added a fail-closed RPT-03 publish-safety self-gate on `dupclean`'s emitted stdout, and corrected the real-corpus smoke assertion 752→742 plus an empty-family robustness regression.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-20T21:13:24-04:00
- **Completed:** 2026-06-20T21:21:02-04:00
- **Tasks:** 3 (Task 2 was TDD: RED→GREEN)
- **Files modified:** 3

## Accomplishments
- **Item 2/3 (Task 1):** Dropped the unused `normalize_url` import (and the now-unneeded `# noqa: F401`) and the unused `--out` CLI argument from `crawler/dupclean.py`; updated the import-block comment.
- **Item 4 (Task 2):** Added a fail-closed RPT-03 share-safety self-gate to `dupclean.main()` mirroring `dupaudit` — the to-be-emitted output is rendered and scanned with the existing `check_publish_safe.scan_text` BEFORE emitting; any abs-path/secret/PII makes the tool emit nothing normal and return `EXIT_INTERNAL_ERROR`. Proven by a new `TestPublishSafe` (clean passes, poisoned fails closed).
- **Item 1 (Task 3):** Corrected the stale `TestRealCorpus` assertion `752 → 742` (verified against the live on-disk git-ignored corpus: `dupaudit.live_docs(corpus) == 742`).
- **Item 5 (Task 3):** Added `TestEmptyFamily`, a fast synthetic-tempdir regression locking in graceful empty/manifest-only family handling (no production-code defect existed; the test prevents a future refactor from reintroducing a crash/miscount).

## Task Commits

Each task was committed atomically (code only):

1. **Task 1: Remove dead normalize_url import and unused --out arg** — `df38715` (fix)
2. **Task 2 (TDD RED): Add failing publish-safety self-gate tests** — `f29761e` (test)
3. **Task 2 (TDD GREEN): Fail-closed publish-safety self-gate on emitted output** — `b62247e` (feat)
4. **Task 3: Correct 752→742 + add empty-family regression** — `ebea380` (test)

_Docs/state commit (SUMMARY + STATE) is made separately by the orchestrator._

## Files Created/Modified
- `crawler/dupclean.py` — Removed dead `normalize_url` import + `# noqa: F401`, removed unused `--out` arg; added the `check_publish_safe` import block and the render-then-gate-then-emit RPT-03 self-gate in `main()`.
- `crawler/tests/test_dupclean.py` — Added `TestPublishSafe` (3 tests: clean-passes, direct scan_text mapping, poisoned-fails-closed) + the `cps`/`contract`/`io`/`contextlib`/`mock` imports.
- `crawler/tests/test_dupaudit.py` — `752 → 742` real-corpus assertion; added `completeness` import + `TestEmptyFamily` regression; one docstring test-map line added.

## Decisions Made
- **Surgical scope only.** Removed solely the genuinely-dead `normalize_url` symbol and the unused `--out` arg. `dupaudit`'s own `--out` IS consumed and untouched; the `from crawler import dupaudit  # noqa: F401` line was left as-is (out of scope).
- **752-filter labels untouched.** Only the numeric real-corpus count assertion changed 752→742. The "752-filter" docstring LABELS (`dupaudit.py:147`, `test_dupaudit.py:16/142/213`, `test_dupclean.py:185`) name the live-doc filter logic, not a count — renaming them is pure churn that risks confusion against the historical v2.1 "752 live docs" milestone record.
- **Gate scope = shareable stdout.** `dupclean`'s gate covers its public stdout contract surface (the `--json` `clean-duplicates` result dict serialized, or the human summary lines). The in-corpus regenerated `REPORT.md` files live under the git-ignored local `corpus/` and are never shared, so they are intentionally out of scope.
- **No production change for Item 5.** Investigation (confirmed) shows `dupaudit.live_docs` (rglob), `completeness.live_docs` (glob), and `completeness.build_report` all tolerate empty/manifest-only families gracefully; the tracked deliverable is a regression test, not a guard.
- **`--out` consumer check:** `grep "args.out\|--out"` confirmed the `--out` block had no reader in `dupclean.py` and no test passed it — safe to delete.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test comments tripped the repo-wide publish-safe check**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** Two new `TestPublishSafe` comment lines literally contained the token `/home/...`, which the `check_publish_safe` ABS_PATH pattern matched — making the plan-required `poetry run python scripts/check_publish_safe.py` report 2 violations (the poisoned literals themselves already carried `# publish-safe: allow`).
- **Fix:** Reworded both comments to "absolute home-dir path" (no literal `/home/` token). The poisoned test data lines retain their `# publish-safe: allow` markers.
- **Files modified:** `crawler/tests/test_dupclean.py`
- **Verification:** `scripts/check_publish_safe.py` → `✓ publish-safe: 97 tracked files scanned, 0 violations`.
- **Committed in:** `b62247e` (folded into the Task 2 GREEN commit).

---

**Total deviations:** 1 auto-fixed (Rule 1).
**Impact on plan:** Required to satisfy the plan's own publish-safe verification gate. No scope creep — confined to comment wording in the test file added by this task.

## Issues Encountered
None — all three tasks executed as written. TDD RED for Task 2 failed exactly as expected (poisoned output emitted `ok:True` before the gate landed), then went green after implementation.

## Local-Only Corpus Action (DOCUMENTED, NOT committed)

Per the plan and the corpus-isolation constraint, no `corpus/` content was staged or committed. For the maintainer's local awareness (Item 5):

- `corpus/pdi-completeness-check/manifest.json` is already `{}` (pruned by v2.2 `dupclean`) — confirmed.
- `corpus/pdi-completeness-check/completeness/sample.json` still reads `"total_live": 1` (stale sidecar) and the now-empty family directory remains on disk.
- The maintainer **MAY** locally refresh/remove that stale sidecar and/or remove the empty family directory. These are **local-only** operations on the git-ignored `corpus/` tree and are **NOT** part of this plan's tracked diff. The tracked guarantee that the tooling tolerates this state is the new `TestEmptyFamily` regression.

## Verification

Canonical checks (both green):

```
poetry run python -m pytest crawler/tests/test_dupclean.py crawler/tests/test_dupaudit.py -q -k "not RealCorpus"
  → 43 passed, 1 deselected   (+4 over the 39-pass baseline: 3 TestPublishSafe + 1 TestEmptyFamily)
poetry run python scripts/check_publish_safe.py
  → ✓ publish-safe: 97 tracked files scanned, 0 violations
```

Real-corpus count confirmed cheaply (the ~9-min O(n²) `TestRealCorpus` audit was not run in full):

```
poetry run python -c "from pathlib import Path; import crawler.dupaudit as d; print(sum(1 for _ in d.live_docs(Path('corpus'))))"
  → 742
```

Per-task verify gates also passed: Task 1 `CLEANUP_OK`; Task 2 `PublishSafe/Contract/DryRun` (7 passed) + publish-safe 0; Task 3 `COUNT_AND_EMPTYFAMILY_OK`.

## Known Stubs
None — no placeholder/empty-data stubs introduced.

## Next Phase Readiness
The v2.2 dedup tooling is now lint-tight, the real-corpus smoke assertion reflects reality (742), and `dupclean` has the same fail-closed share-safety guarantee as `dupaudit` before the harness is shared. No blockers.

---
*Phase: 22-dedup-tooling-tech-debt-cleanup*
*Completed: 2026-06-20*

## Self-Check: PASSED

- Files modified exist: `crawler/dupclean.py`, `crawler/tests/test_dupclean.py`, `crawler/tests/test_dupaudit.py` — all FOUND.
- Commits exist: `df38715`, `f29761e`, `b62247e`, `ebea380` — all FOUND in git log.
- No `corpus/` content staged or committed (verified `git diff --cached` clean of `corpus/`).
