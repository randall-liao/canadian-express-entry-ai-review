---
phase: 21-corpus-cleanup-re-validation
verified: 2026-06-11T04:24:04Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
requirements:
  - id: CLEAN-02
    status: satisfied
  - id: CLEAN-03
    status: satisfied
---

# Phase 21: Corpus Cleanup & Re-validation — Verification Report

**Phase Goal:** The local corpus holds exactly one canonical copy per duplicate cluster, with QC/completeness integrity intact, counts updated, and deletions kept local.
**Verified:** 2026-06-11T04:24:04Z
**Status:** passed
**Re-verification:** No — initial verification

> NOTE: The destructive `--apply` was already run against the real local
> corpus prior to this verification. Every check below validates the
> **resulting on-disk state**, not the SUMMARY narrative.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Every non-canonical copy named in the Phase 20 report is removed from live `corpus/`, leaving one canonical per cluster (CLEAN-02) | ✓ VERIFIED | All 10 high-confidence targets are absent from the live set and present under their family `_dropped/` (recoverable). 6 overlap-only false positives correctly retained in live set. |
| 2 | Re-running the detector reports zero remaining cross-family clusters (CLEAN-02) | ✓ VERIFIED | `dupclean.recheck_zero_clusters(corpus)` → `[]`; report `result.recheck_clusters == []`. |
| 3 | Live-document counts updated and recorded (CLEAN-03) | ✓ VERIFIED | `dupaudit.live_docs(corpus)` count = **742** (was 752). `duplicate-clean.json`: `live_before=752`, `live_after=742`, `moved=10`. |
| 4 | QC/completeness validators pass; no dangling references to deleted files (CLEAN-03) | ✓ VERIFIED | All 4 touched families `verdict=pass` (none "fail"). Moved URLs pruned from manifests (spot-checked mi-rounds, police-certificates). No moved basename remains in any touched family's `sample.json` pairs / `REPORT.md`; orphaned `.check.json`/`.live.md` captures moved out of live completeness dirs. |
| 5 | `git status` confirms deletions stayed local — no `corpus/` content committed | ✓ VERIFIED | `git status --porcelain corpus/` empty; `git check-ignore corpus/` confirms the tree is git-ignored. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `crawler/dupclean.py` | Move-to-_dropped engine + manifest/completeness prune + re-validate + zero-cluster recheck + CLI | ✓ VERIFIED | All functions implemented (`load_plan`, `confine`, `move_to_dropped`, `prune_manifest`, `prune_completeness_orphans`, `revalidate_family`, `recheck_zero_clusters`, `clean`, `main`). No stubs / `NotImplementedError` remain. |
| `crawler/tests/test_dupclean.py` | RED→GREEN suite | ✓ VERIFIED | 15/15 tests pass. |
| `reports/duplicate-clean.json` | Real-run record, verdict=pass, shareable | ✓ VERIFIED | `ok=true`, `verdict=pass`, `moved=10`, `retained_overlap_only=6`, all family verdicts `pass`; passes publish-safe gate (tracked). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `clean(apply=True)` | family `_dropped/` | `move_to_dropped` → `shutil.move` (no unlink) | ✓ WIRED | 10 docs + eval siblings + audit logs present under `_dropped/`. |
| `clean(apply=True)` | `manifest.json` | `prune_manifest` | ✓ WIRED | Moved URLs absent from family manifests. |
| `clean(apply=True)` | `completeness/sample.json` | `prune_completeness_orphans` | ✓ WIRED | No orphan pairs; captures moved to `_dropped/`. |
| `clean(apply=True)` | `REPORT.md` | `revalidate_family` → `completeness.build_report` (offline) | ✓ WIRED | All touched families re-validated `verdict=pass`. |
| `main(--apply)` | verdict | `recheck_zero_clusters` | ✓ WIRED | recheck `[]` folded into verdict=pass. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Test suite green | `poetry run python -m unittest crawler.tests.test_dupclean -v` | Ran 15, OK | ✓ PASS |
| Live count = 742 | `dupaudit.live_docs(corpus)` | 742 | ✓ PASS |
| Zero clusters | `dupclean.recheck_zero_clusters(corpus)` | `[]` | ✓ PASS |
| CLI dry-run non-mutating | `python -m crawler.dupclean corpus/ --report ... --json` | ok=true, verdict=dry-run, planned moved=10, retained=6 | ✓ PASS |
| Publish-safe | `poetry run python scripts/check_publish_safe.py` | 93 files scanned, 0 violations | ✓ PASS |
| Git-local | `git status --porcelain corpus/` | empty | ✓ PASS |

### Safety Verification

| Check | Status | Evidence |
|-------|--------|----------|
| 6 overlap-only false positives survive in live set | ✓ PASS | `police-certificates/{tokelau,guadeloupe,mayotte}.md`, `mi-rounds/invitations-12.md`, `guidance/{check-score,grid}.md` all present. |
| No hard-delete of corpus files | ✓ PASS | `grep unlink/remove/rmtree crawler/dupclean.py` → only docstring/comment mentions; the only fs-mutation primitive is `shutil.move` into `_dropped/`. `TestContract.test_no_hard_delete_primitive_in_source` passes. Moves are recoverable. |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| CLEAN-02 | Delete all non-canonical copies from local git-ignored corpus, one canonical per cluster | ✓ SATISFIED | Code: `load_plan`/`move_to_dropped`/`clean(apply=True)`/`recheck_zero_clusters`. Tests: TestScope, TestApply (4), TestRecheck. Real run: 10 moved, recheck `[]`, 6 FPs retained. |
| CLEAN-03 | Re-validate after deletion — update counts, QC/completeness integrity, no dangling refs | ✓ SATISFIED | Code: `prune_manifest`/`prune_completeness_orphans`/`revalidate_family` + live_before/after. Tests: TestRevalidate (3), TestGit. Real run: 752→742, all family verdicts pass, manifests/sidecars pruned, no dangling refs. |

> ROADMAP/REQUIREMENTS.md still mark CLEAN-03 "Pending" and Phase 21 "4/5 In Progress"
> with 21-05-PLAN unchecked — these are tracking-doc lag. The 21-05 work was
> executed (per 21-05-SUMMARY) and is fully evidenced in the codebase state above.
> Recommend updating ROADMAP/REQUIREMENTS to mark Phase 21 / CLEAN-03 complete.

### Anti-Patterns Found

None blocking. `dupclean.py` "unlink/remove" matches are docstring/comment negative-affirmations of the no-hard-delete invariant, not live calls. No TBD/FIXME/XXX markers in modified source.

### Gaps Summary

None. All 5 success criteria observably hold against the post-`--apply` corpus
state, both requirements map to delivered code with passing tests, the
destructive operation used a recoverable move (not hard delete), and the
6 verified-distinct false positives were correctly retained.

---

_Verified: 2026-06-11T04:24:04Z_
_Verifier: the agent (gsd-verifier)_
