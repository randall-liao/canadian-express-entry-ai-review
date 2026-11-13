---
phase: 21-corpus-cleanup-re-validation
plan: 01
subsystem: testing
tags: [duplicate-cleanup, move-to-dropped, re-validation, unittest, contract, tdd-red, path-confinement]

# Dependency graph
requires:
  - phase: 20-cross-family-duplicate-detection-audit-report
    provides: "crawler.dupaudit (audit/render_json/live_docs/exact_edges/url_edges/cluster/parse_doc) + the duplicate-audit.json report schema + test_dupaudit._make_dup_corpus fixture"
  - phase: pre-existing crawler primitives
    provides: "apply_verdicts move-to-_dropped pattern, completeness.build_report/live_docs, profile.load_profile/normalize_url, contract envelope/EXIT_*"
provides:
  - "crawler/dupclean.py — the public interface contract (typed stubs raising NotImplementedError + the _now() helper + an argparse CLI scaffold) for the offline corpus-cleanup module"
  - "crawler/tests/test_dupclean.py — the full failing (RED) Nyquist Wave-0 spec covering CLEAN-02/03 + SC5 + path-traversal security"
  - "_make_clean_corpus / _mint_report fixtures: a synthetic clean-corpus that mints a real duplicate-audit.json via dupaudit.audit()+render_json() and plants per-family manifest.json + completeness sidecars for a high-confidence delete target"
affects: [21-02, 21-03, 21-04, 21-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tests-first Wave-0 contract: typed NotImplementedError stubs pin the module surface Plans 02-04 implement against; Plan 05 runs it on the real corpus"
    - "Report fixture minted from the real dupaudit producer (audit()+render_json()) — never hand-authored — so the consumed schema stays in lock-step with Phase 20"
    - "Deterministic report minted exactly ONCE and reused across tests (the O(n^2) overlap detector costs ~2s) to keep the whole suite ~1.5s"
    - "move-to-_dropped is the only removal primitive — no os.unlink/os.remove/.unlink( anywhere (threat T-21-03)"

key-files:
  created:
    - crawler/dupclean.py
    - crawler/tests/test_dupclean.py
  modified: []

key-decisions:
  - "Only _now() is implemented; load_plan/confine/move_to_dropped/prune_manifest/prune_completeness_orphans/revalidate_family/recheck_zero_clusters/clean raise NotImplementedError so Wave 0 is a pure contract"
  - "main() builds the argparse parser (so --help works on import) then delegates to the clean() stub — execution may still hit the stub, but import never crashes"
  - "Fixture uses famB/exact_two.md (exact) and famC/url_two.md (url) as high-confidence delete targets; famB/near_close.md is the overlap-ONLY delete target — distinct, so the default-scoping test is meaningful"
  - "famB/exact_two.md carries BOTH eval naming forms (<stem>.eval.json and <doc>.md.eval.json) so a single delete target exercises both forms moving"
  - "famC manifest keys + completeness sample are computed with the SAME profile.normalize_url the implementation will use, so prune_manifest/prune_completeness_orphans assertions match without hardcoding URLs"
  - "Zero-cluster re-check test asserts both dupclean.recheck_zero_clusters(root)==[] and the independent dupaudit exact+url cluster()==[] (overlap detector deliberately skipped — Pattern 4)"

patterns-established:
  - "Contract anchor class (TestContract) stays GREEN in Wave 0 (surface presence + no hard-delete primitive + report-mint proof); behavior classes are RED"
  - "SC5 git-local proven as a unit invariant: snapshot the whole tempdir, assert every changed/new path stays under corpus/ (the report json lives beside, not under, corpus/)"
  - "Re-validation verdict asserted on the regenerated REPORT.md text (decremented Live documents count + no hard FAIL) rather than a brittle dict shape"

requirements-completed: [CLEAN-02, CLEAN-03]  # SCAFFOLDED (RED) this wave; behavior + REQUIREMENTS.md completion land in Plans 02-05

# Metrics
duration: 14min
completed: 2026-06-11
---

# Phase 21 Plan 01: Nyquist Wave-0 Cleanup Contract & RED Test Suite Summary

**Established the offline corpus-cleanup module's typed interface contract (`crawler/dupclean.py`) and a complete failing (RED) executable specification — 15 tests pinning CLEAN-02 safe move-to-`_dropped`/scoping/idempotency, CLEAN-03 manifest+completeness re-validation, SC5 git-local, and path-traversal security — with the consumed `duplicate-audit.json` minted from the real `dupaudit` producer, so Plans 02–04 are pure GREEN phases.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-06-11T02:56:00Z
- **Completed:** 2026-06-11T03:10:00Z
- **Tasks:** 2 completed
- **Files modified:** 2 created

## Accomplishments
- Locked the cleanup module's full surface (9 contracted callables) as import-safe, OFFLINE stubs raising `NotImplementedError`, with no hard-delete primitive anywhere (move-to-`_dropped/` only).
- Authored the complete RED Wave-0 suite (every test method named in `21-VALIDATION.md`'s verification map) — 12 behavior tests fail solely with `NotImplementedError`, 3 contract tests pass, zero import/collection errors.
- Built a synthetic clean-corpus fixture that mints a real `duplicate-audit.json` via `dupaudit.audit()` + `render_json()` (no literal JSON), and plants per-family `manifest.json` + a `completeness/` sample/sidecars for a high-confidence delete target so re-validation is fully exercisable.
- Kept the suite at ~1.5s (well under the 5s feedback budget) by minting the deterministic report once and reusing it.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author the crawler/dupclean.py interface contract (stubs)** — `9627252` (feat)
2. **Task 2: Author the RED Wave-0 unittest suite + synthetic clean-corpus fixture** — `eea5ae2` (test)

## Files Created/Modified
- `crawler/dupclean.py` (230 lines) — Typed contract: `load_plan`, `confine`, `move_to_dropped`, `prune_manifest`, `prune_completeness_orphans`, `revalidate_family`, `recheck_zero_clusters`, `clean`, `main`. Implements only `_now()` + an argparse CLI scaffold; everything else raises `NotImplementedError`. Module docstring fixes the move-not-delete / dry-run-by-default / overlap-excluded-by-default contract.
- `crawler/tests/test_dupclean.py` (413 lines) — RED suite: `TestContract` (GREEN anchor), `TestScope`, `TestDryRun`, `TestApply`, `TestRecheck`, `TestRevalidate`, `TestGit`, `TestSecurity`; helpers `_make_clean_corpus`, `_mint_report`, `_minted_payload`, `_write_report`.

## Verification Outcomes

- `import crawler.dupclean` + all 9 symbols present — **PASS**
- `grep -E "os\.unlink|os\.remove|\.unlink\(|\.remove\("` over `crawler/dupclean.py` — **no match** (no hard-delete primitive)
- `python -m crawler.dupclean --help` — **renders** (no import crash)
- `python -m unittest crawler.tests.test_dupclean` — **RED-OK**: `Ran 15 tests ... FAILED (errors=12)` in ~1.5s; all 12 errors are `NotImplementedError`; the 3 `TestContract` tests pass.
- `unittest` discovery over `crawler/tests` — **0 collection errors** (104 tests collected).

## Decisions Made
See `key-decisions` in frontmatter. Key call: this is a test-first RED wave — only the trivial `_now()` helper and the argparse scaffold are implemented; the deletion/prune/re-validation logic is intentionally absent (lands in Plans 02–04).

## Deviations from Plan

**1. [Rule 2 — Missing critical correctness] Docstring reworded to avoid hard-delete token substrings**
- **Found during:** Task 1 (verify step)
- **Issue:** The acceptance criterion forbids `os.unlink`/`os.remove`/`Path.unlink` appearing "anywhere in the file"; the initial docstring mentioned `os.unlink`/`os.remove`/`Path.unlink` in prose, which a naive grep (and the suite's own `test_no_hard_delete_primitive_in_source`) would flag as a false positive.
- **Fix:** Reworded the prose to "hard-delete (no `unlink`/`remove` primitive)" so the file contains no forbidden token substrings while preserving the warning's intent.
- **Files modified:** `crawler/dupclean.py`
- **Verification:** `grep -E "os\.unlink|os\.remove|\.unlink\(|\.remove\("` → no match; `TestContract.test_no_hard_delete_primitive_in_source` passes.
- **Committed in:** `9627252` (part of Task 1 commit)

**2. [Rule 3 — Blocking: feedback-latency budget] Mint the report once instead of per-test**
- **Found during:** Task 2 (verify step)
- **Issue:** Minting the report in every `_CleanCase.setUp` ran `dupaudit.audit()` (whose `O(n^2)` overlap detector costs ~2s) 12+ times → ~24.8s, violating the "<5s" acceptance criterion.
- **Fix:** The report is deterministic over the structurally identical synthetic corpus, so it is minted exactly once via `_minted_payload()` (which exercises `_mint_report` end-to-end) and the cached payload is written beside each fresh corpus by `_write_report`.
- **Files modified:** `crawler/tests/test_dupclean.py`
- **Verification:** Suite runtime dropped to ~1.5s; still minted from `dupaudit.audit()`+`render_json()` (no hand-authored JSON).
- **Committed in:** `eea5ae2` (part of Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1× Rule 2, 1× Rule 3)
**Impact on plan:** Both fixes preserve the plan's intent (no hard-delete primitive; report minted from dupaudit) and were required to satisfy stated acceptance criteria. No scope creep.

## Issues Encountered
None beyond the two deviations above.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- The contract surface and RED suite are frozen; **Plan 02** can implement `load_plan`/`confine`/`move_to_dropped` (CLEAN-02 scoping + safe move + path-confinement) directly against the failing tests.
- `TestScope`, `TestApply`, `TestSecurity` define the exact GREEN target for Plan 02; `TestRevalidate`/`TestRecheck` for Plan 03; `TestGit` + the CLI envelope for Plan 04.
- REQUIREMENTS.md CLEAN-02/CLEAN-03 remain **Pending** (correctly) — they flip to Complete only after the implementation plans land, mirroring how Phase 20 marked DUP-01..04 complete after its full phase.

---
*Phase: 21-corpus-cleanup-re-validation*
*Completed: 2026-06-11*

## Self-Check: PASSED

- Files: `crawler/dupclean.py`, `crawler/tests/test_dupclean.py`, `21-01-SUMMARY.md` — all present.
- Commits: `9627252` (Task 1), `eea5ae2` (Task 2) — both in git history.
