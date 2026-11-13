---
phase: 40-safe-freshness-effective-date-foundation
fixed_at: 2026-07-18T04:55:40Z
review_path: .planning/phases/40-safe-freshness-effective-date-foundation/40-REVIEW.md
iteration: 2
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 40: Code Review Fix Report

**Fixed at:** 2026-07-18T04:55:40Z
**Source review:** `.planning/phases/40-safe-freshness-effective-date-foundation/40-REVIEW.md`
**Iteration:** 2

**This report spans two fix passes over `crawler/index_health.probe_snapshot`:**

- **Iteration 1** (`fixed_at: 2026-07-18T04:48:08Z`) — 2 Warnings fixed: WR-01
  (default-`as_of` misclassified as corrupt) and WR-02 (unguarded TOCTOU
  second-open). Documented under "Iteration 1" below.
- **Iteration 2** (this pass, `fixed_at: 2026-07-18T04:55:40Z`) — the re-review
  (`reviewed: 2026-07-18T04:49:42Z`) surfaced 1 additional Warning, **WR-01
  (re-review): a future-dated snapshot classified fresh (fail-open)** — a
  fail-closed asymmetry the first pass did not surface. Fixed and documented
  under "Iteration 2" below.

**Cumulative across both passes:** 3 Warnings fixed, 0 skipped, 3 atomic commits,
3 deterministic regression tests added. The 2 Info findings from the review
(private `_as_date` import; stale `auditor.py:207` line-reference) remain
intentionally out of the Warning-only fix scope and were not applied.

---

## Iteration 2 (re-review pass)

**Fixed at:** 2026-07-18T04:55:40Z · **Iteration:** 2

**Summary:**
- Findings in scope: 1 (the sole re-review Warning; the 2 Info findings stay out of scope)
- Fixed: 1
- Skipped: 0

The re-review Warning was reproduced empirically before the fix and re-verified
resolved after, with a new deterministic regression test.

### WR-01 (re-review): `probe_snapshot` accepts a FUTURE-dated snapshot as fresh — fail-open, diverging from its fail-closed sibling `within_freshness`

**Files modified:** `crawler/index_health.py`, `crawler/tests/test_snapshot_health.py`
**Commit:** `88f2657`
**Applied fix:** The freshness comparison was one-sided — it rejected only
snapshots that were too OLD (`(_as_date(as_of) - newest).days > max_age_days`).
When the newest usable `crawl_date` is AFTER `as_of`, that delta is negative, is
never `> max_age_days`, and the family fell through to `SNAPSHOT_OK` — silently
greening an impossible future date (clock skew, a crawler bug, or tampering). The
fix computes the delta once and, **before** the max-age comparison, fails closed
to `SNAPSHOT_STALE` when `delta < 0`. This mirrors the two-sided window of the
sibling shipped the same phase, `crs_audit.within_freshness` (`0 <= delta <=
window`), so both Phase-40 freshness surfaces now agree a future date is NOT
fresh. No new reason code was added and scope was not broadened — both the
future-date and too-old branches surface the existing `SNAPSHOT_STALE` code; the
too-old branch keeps its original `"snapshot older than {max_age_days}d"`
message. The already-fixed iteration-1 behaviors are untouched: the omitted-`as_of`
default (today, never literal `"None"`) and the TOCTOU second-open guard still
apply, and `max_age_days` stays caller-supplied with no inlined numeric default
(SAFE-09).

- **Empirical repro (before):** a family whose newest `crawl_date` is `2099-01-01`
  with `probe_snapshot(db, "dli", max_age_days=30, as_of="2026-07-17")` →
  `ok` / "snapshot present and fresh". The sibling
  `within_freshness(..., "2099-01-01", "2026-07-17", reg)` → `False` on the same
  after-reference input.
- **After:** same call → `snapshot_stale` / "snapshot crawl_date is after as_of —
  cannot prove freshness".
- **Regression test:** `test_future_crawl_date_after_as_of_fails_closed_to_stale`
  — a fixed far-future `crawl_date` (`2099-01-01`) with explicit
  `as_of="2026-07-17"` and `max_age_days=30` asserts `SNAPSHOT_STALE`.
  Deterministic and wall-clock-free, matching
  `test_freshness_staleness.test_crawl_after_reference_is_not_fresh`.

**Note (logic-correctness fix):** this repair changes a freshness comparison, so
its correctness is semantic, not merely structural. It is pinned by the new
deterministic regression test above and the unchanged too-old / blank-date /
default-`as_of` cases, but a reviewer should confirm the `delta < 0` boundary
(a crawl_date exactly equal to `as_of` is `delta == 0` → still fresh, matching
`within_freshness`'s inclusive lower bound) before the phase is marked complete.

### Iteration 2 verification

- **Focused future-date test:**
  `test_future_crawl_date_after_as_of_fails_closed_to_stale` → **1 passed**.
- **Phase 40 surface:** `test_snapshot_health.py`, `test_snapshot_refusal.py`,
  `test_index_health.py`, `test_freshness_staleness.py`, `test_gate_subset.py`,
  `test_crs_rules.py` → **65 passed**.
- **Full suite:** `.venv/bin/python -m pytest crawler/tests -q` → **888 passed,
  1 skipped, 355 subtests passed** (was 887 before; +1 new regression test; the
  1 skip is the documented LOCAL-ONLY git-ignored real-index positive control).
- **Publish-safe:** `scripts/check_publish_safe.py` → **0 violations** (382 tracked
  files).
- **Conformance:** `scripts/run_conformance.py` → **75 passed / PASS** (SAFE-01..08).
- **Frozen invariants preserved:** `probe_index` / `IndexHealth` / `INDEX_*`
  unchanged; exactly one `def probe_snapshot` and one `class SnapshotHealth`; the
  `SNAPSHOT_*` closed vocabulary unchanged (no new reason code); `max_age_days=None`
  retained with NO numeric default; parameter-bound `WHERE relpath LIKE ?` and
  PII-light messages unchanged.

---

## Iteration 1 (original pass)

**Fixed at:** 2026-07-18T04:48:08Z · **Iteration:** 1

**Summary:**
- Findings in scope: 2 (Warnings — default review-fix scope; the 2 Info findings were out of scope and not applied)
- Fixed: 2
- Skipped: 0

Both Warnings were reproduced empirically before fixing and re-verified fixed
after, each with a deterministic regression test. Both live in
`crawler/index_health.probe_snapshot`; they have distinct root causes and distinct
regression tests, so each was fixed and committed as its own atomic commit.

## Fixed Issues

### WR-01: `probe_snapshot` misclassifies a healthy, fresh snapshot as `snapshot_corrupt` when `max_age_days` is supplied but `as_of` is defaulted

**Files modified:** `crawler/index_health.py`, `crawler/tests/test_snapshot_health.py`
**Commit:** `a57cd70`
**Applied fix:** Inside the `max_age_days is not None` freshness branch, the reference
instant now defaults to today (`date.today().isoformat()`) **only** when `as_of is
None`, so the code never evaluates `crs_audit._as_date(None)` →
`date.fromisoformat("None")` → `ValueError` (which the broad
`except (sqlite3.DatabaseError, TypeError, ValueError)` swallowed and returned as
`SNAPSHOT_CORRUPT`). An explicit (even malformed) `as_of` still flows through
`_as_date` unchanged and fails closed exactly as before, and `max_age_days` stays
caller-supplied — no inlined volatile max-age bound (SAFE-09). The `probe_snapshot`
docstring now states the `as_of` default so the contract is no longer a footgun.

- **Empirical repro (before):** `probe_snapshot(fresh_db, "dli", max_age_days=30)` →
  `snapshot_corrupt` / "snapshot rows unreadable".
- **After:** same call → `ok`; and `max_age_days=1, as_of="2026-07-17"` still →
  `snapshot_stale` (explicit-`as_of` behavior preserved).
- **Regression test:** `test_default_as_of_uses_today_not_literal_none` — a fresh
  fixture (`crawl_date="2026-07-10"`) with `max_age_days=3650` and a defaulted
  `as_of` asserts `SNAPSHOT_OK`. A large bound over a fixed fixture date keeps the
  assertion deterministic (no wall-clock dependence).

### WR-02: Second read-only `connect` in `probe_snapshot` is unguarded — a TOCTOU race re-raises the exact traceback this module exists to prevent

**Files modified:** `crawler/index_health.py`, `crawler/tests/test_snapshot_health.py`
**Commit:** `7640bbb`
**Applied fix:** The second read-only connect
(`sqlite3.connect(f"file:{Path(db)}?mode=ro", uri=True)`) is now wrapped exactly the
way `probe_index` wraps its own connect: `except sqlite3.OperationalError` → return
`SnapshotHealth(SNAPSHOT_UNREADABLE, "cannot open snapshot read-only")`, and the
`try/finally: con.close()` is entered only once the connection exists (so `close()`
never runs against an unbound `con`). If the file is deleted / unmounted /
permission-changed in the TOCTOU window between `base = probe_index(db)` and this
open, the race now refuses cleanly instead of escaping as the raw
`sqlite3.OperationalError` / internal_error traceback the module exists to eliminate.
`OperationalError` is a subclass of `DatabaseError`, so this narrows only the
newly-guarded open — the inner post-connect
`except (sqlite3.DatabaseError, TypeError, ValueError)` guard is unchanged and
programming errors are not swallowed more broadly.

- **Empirical repro (before):** with `probe_index` forced to OK and the file gone,
  the second open raised **uncaught** `sqlite3.OperationalError: unable to open
  database file`.
- **After:** same scenario → `snapshot_unreadable` / "cannot open snapshot
  read-only".
- **Regression test:** `test_toctou_second_open_failure_refuses_snapshot_unreadable`
  — `mock.patch.object(index_health, "probe_index", ...)` forces the base probe to
  OK, then points at a path with no database so the second read-only open
  deterministically raises `OperationalError` (no timing race); it asserts
  `SNAPSHOT_UNREADABLE`.

## Skipped Issues

The two Info findings are outside the default Warning fix scope and were intentionally
not implemented (they are not required to be fixed by this review-fix task):

- **IN-01** (`probe_snapshot` imports `crs_audit`'s private `_as_date`) — a
  maintainability/coupling concern with no import cycle today; addressing it means
  promoting a public date helper, which is a refactor beyond this scope.
- **IN-02** (stale `auditor.py:207` line-reference in the `gate_subset` alias comment
  and its test) — a documentation cross-reference inaccuracy in files unrelated to the
  two Warnings; not applied to keep each fix narrowly scoped.

## Verification

- **Reproduced-then-fixed:** both Warnings reproduced empirically before the fix and
  re-verified resolved after.
- **Focused per fix:** WR-01 and WR-02 targeted test selections pass.
- **Phase 40 surface:** `test_snapshot_health.py`, `test_snapshot_refusal.py`,
  `test_index_health.py`, `test_audit_index_refusal.py`, `test_freshness_staleness.py`,
  `test_gate_subset.py`, `test_crs_rules.py` → **68 passed**.
- **Full suite:** `.venv/bin/python -m pytest crawler/tests -q` → **887 passed,
  1 skipped, 355 subtests passed** (was 885 before; +2 new regression tests; the 1
  skip is the documented LOCAL-ONLY git-ignored real-index positive control).
- **Publish-safe:** `scripts/check_publish_safe.py` → **0 violations** (381 tracked
  files).
- **Conformance:** `scripts/run_conformance.py` → **75 passed / PASS** (SAFE-01..08).
- **Frozen invariants preserved:** `probe_index` / `IndexHealth` / `INDEX_*` unchanged;
  exactly one `def probe_snapshot` and one `class SnapshotHealth`; `max_age_days=None`
  retained with NO numeric default; parameter-bound `WHERE relpath LIKE ?` and PII-light
  messages unchanged.

---

_Fixed: 2026-07-18T04:55:40Z (iteration 2 — re-review pass); 2026-07-18T04:48:08Z (iteration 1)_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 2_
