---
phase: 46
fixed_at: 2026-07-21T04:01:08Z
review_path: .planning/phases/46-safe-conformance-release-gate/46-REVIEW.md
iteration: 7
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 46: Code Review Fix Report

**Fixed at:** 2026-07-21T04:01:08Z
**Source review:** `.planning/phases/46-safe-conformance-release-gate/46-REVIEW.md`
**Iteration:** 7

**Summary:**
- Findings in scope: 3
- Fixed: 3
- Skipped: 0

## Fixed Issues

### CR-01: Cleanup crash creates an unrecoverable markerless LKG

**Files modified:** `crawler/study_review.py`, `crawler/tests/test_study_review.py`
**Commit:** `692f1ba`
**Applied fix:** Added the durable `cleanup_pending` transition. It verifies installed and old-LKG hashes before deleting the backup, deletes the marker last, and retries every cleanup crash boundary without accepting unverified canonical bytes.

### CR-02: Truncating the journal to mark installation can strand the LKG

**Files modified:** `crawler/study_review.py`, `crawler/tests/test_study_review.py`
**Commit:** `692f1ba`
**Applied fix:** Replaced in-place `O_TRUNC` journal rewriting with a private mode-0600 sibling journal, complete short-write-aware write and file fsync, atomic replace, and directory fsync. Prepared remains authoritative before replacement; a complete installed record remains authoritative after it.

### WR-01: Concurrency regressions do not deterministically distinguish the prior unlocked implementation

**Files modified:** `crawler/tests/test_study_review.py`
**Commit:** `692f1ba`
**Applied fix:** Instrumented entry into the unlocked recovery body. Publisher and FSW read-only tests now prove the contender cannot enter while the lock holder runs, then require the ordered recovery trace and final artifact bytes.

### Frozen approvals

**Files modified:** `crawler/tests/test_conformance_v5_study_no_false_green.py`, `crawler/tests/test_conformance_v5_privacy_release.py`
**Commit:** `856970b`
**Applied fix:** Updated only the independent static `crawler/study_review.py` approval values to final SHA-256 `9865756a541f50b5c4411a73c148129a9cd0d837bb6ee76fa13228f94e935c96`.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_study_review.py::TestStudyReportDurability -q`: **20 passed, 21 subtests passed**
- `.venv/bin/python -m pytest crawler/tests/test_study_review.py crawler/tests/test_study_review_cli.py crawler/tests/test_mec_screen.py -q`: **108 passed, 15 skipped, 206 subtests passed**
- Frozen privacy hash gate: **1 passed, 18 subtests passed**. The independent STUDY hash-gate test was invoked but skipped because this isolated worktree lacks the required local DLI family/index; the final SHA was computed directly and both static maps were re-read.
- `.venv/bin/python -m py_compile` on all four changed Python modules: **passed**
- `git diff --check`: **passed**

## Residual Risk

No source release blocker remains. The isolated-worktree environment lacks the local DLI family/index, so its combined STUDY frozen-gate test could not execute; its static source hash assertion remains unchanged and was manually verified against the final source bytes.

---

_Fixed: 2026-07-21T04:01:08Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 7_
