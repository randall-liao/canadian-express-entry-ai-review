---
phase: 40-safe-freshness-effective-date-foundation
reviewed: 2026-07-18T05:16:51Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - crawler/auditor.py
  - crawler/cli.py
  - crawler/crs_audit.py
  - crawler/index_health.py
  - crawler/tests/test_crs_rules.py
  - crawler/tests/test_freshness_staleness.py
  - crawler/tests/test_gate_subset.py
  - crawler/tests/test_snapshot_health.py
  - crawler/tests/test_snapshot_refusal.py
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: issues_found
---

# Phase 40: Code Review Report

**Reviewed:** 2026-07-18T05:16:51Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Final re-review of the Phase 40 SAFE freshness / effective-date foundation after all
three Warning fixes. Phase 40 ships four fail-closed foundation surfaces, none wired into
a decider or user-facing verb this phase (defined-only): `crs_audit.within_freshness` +
`row_in_effect`, the `_gate_or_raise → gate_subset` public promotion (verbatim body +
identity alias), `index_health.probe_snapshot` + `SnapshotHealth` + the `SNAPSHOT_*`
closed vocabulary, and the `cli._require_readable_snapshot` refusal wrapper.

**No Critical or Warning findings remain.** The three prior Warnings are fixed and every
fix was reproduced empirically and is pinned by a deterministic, wall-clock-free
regression test. Three low-risk Info observations from the prior review are still present
in the current code and are re-reported below (unchanged); they are documentation /
coupling / latent-generality notes with no live failing path this phase.

### Fix verification (all three confirmed fixed — reproduced + regression-pinned)

- **`a57cd70` (WR-01, default `as_of`) — confirmed.** With `max_age_days` supplied and
  `as_of` omitted, `probe_snapshot` resolves `as_of` to `date.today().isoformat()` inside
  the `max_age_days is not None` branch (`index_health.py:299`) instead of parsing the
  literal `"None"`. Reproduced: a fresh family (`crawl_date=2026-07-10`, `max_age_days=3650`,
  no `as_of`) → `SNAPSHOT_OK` (previously `snapshot_corrupt`). Fail-closed preserved — an
  explicit malformed `as_of` (e.g. `"not-a-date"`) still flows through `_as_date` and
  returns `snapshot_corrupt`. No inlined volatile bound
  (`no_inlined_volatile_rules(["crawler/index_health.py"]) == []`). Regression
  `test_default_as_of_uses_today_not_literal_none` passes.

- **`7640bbb` (WR-02, TOCTOU second connect) — confirmed.** The second read-only connect
  (`index_health.py:264-267`) is wrapped `except sqlite3.OperationalError →
  SNAPSHOT_UNREADABLE`, and the `try/finally: con.close()` is entered only once `con` is
  bound (never closes an unbound name). `OperationalError` is a subclass of `DatabaseError`,
  so the inner post-connect `except (sqlite3.DatabaseError, TypeError, ValueError)` guard is
  unchanged and programming errors are not swallowed more broadly. Reproduced (base probe
  forced `INDEX_OK`, target path absent) → `snapshot_unreadable`. Regression
  `test_toctou_second_open_failure_refuses_snapshot_unreadable` passes.

- **`88f2657` (WR-01 re-review, future-dated snapshot) — confirmed.** `probe_snapshot`
  now computes the delta once and, **before** the max-age comparison, fails closed to
  `SNAPSHOT_STALE` when `delta < 0` (`index_health.py:317-320`), so a `crawl_date` after
  `as_of` (clock skew / crawler bug / tampering) is no longer greened. This is a genuine
  two-sided window (`0 <= delta <= max_age_days`) matching the sibling
  `crs_audit.within_freshness`'s `0 <= delta <= window`. Reproduced: newest
  `crawl_date=2099-01-01`, `as_of=2026-07-17`, `max_age_days=30` → `snapshot_stale`
  (previously `ok`). Boundary confirmed: `crawl_date == as_of` (delta 0) → `SNAPSHOT_OK`
  (inclusive lower bound, matching the sibling). The too-old branch keeps its original
  `"snapshot older than {max_age_days}d"` message and no new reason code was added.
  Regression `test_future_crawl_date_after_as_of_fails_closed_to_stale` passes. **The prior
  WR-01 (future-date) finding is RESOLVED and is not carried forward.**

### Deterministic regression + trust-path checks (all green)

- Phase-40 surface: `test_snapshot_health.py`, `test_snapshot_refusal.py`,
  `test_freshness_staleness.py`, `test_gate_subset.py`, `test_crs_rules.py` → **53 passed**.
- Frozen-grid parity + siblings: `test_auditor.py`, `test_auditor_dispatch.py`,
  `test_crs_audit.py`, `test_index_health.py` → **61 passed** (the `gate_subset` promotion
  keeps the frozen grid byte-for-byte green; `auditor.gate_subset is auditor._gate_or_raise`).
- `_INDEX_TO_SNAPSHOT` covers every non-ok `probe_index` status (the `if not base.ok()`
  guard + the four mapped codes = no `KeyError`).
- The snapshot filter binds `family` as a SQL parameter (`WHERE relpath LIKE ?`) — no SQL
  injection. Refusal messages echo only the caller-supplied `--db` corpus path (never the
  vault/personal path or an `ev_` id) — PII perimeter held; zero-artifact ordering proven
  by `test_refusal_writes_zero_artifacts`.
- No import cycle: `crs_audit` / `crs_rules` do not import `index_health`; the
  `index_health → crs_audit._as_date` import is lazy and one-directional.
- No inlined volatile rule in either modified module
  (`no_inlined_volatile_rules` returns `[]` for `crawler/crs_audit.py` and
  `crawler/index_health.py`).

**No blocking (Critical) or Warning findings remain.** Only the three Info observations
below are outstanding; each is low-risk and was intentionally left out of the
Warning-only fix scope.

## Info

### IN-01: `probe_snapshot` imports another module's private `_as_date`

**File:** `crawler/index_health.py:289` (`from crawler.crs_audit import _as_date`)
**Issue:** `index_health` reuses `crs_audit`'s leading-underscore-private `_as_date` for
its freshness date math. Importing a private symbol across a module boundary couples
`index_health` to a `crs_audit` internal — a rename/refactor of `_as_date` would silently
break `probe_snapshot` with no public contract protecting it. There is no import cycle
today (`crs_audit` does not import `index_health`, and the import is lazy inside the
`max_age_days is not None` branch), so this is a maintainability/coupling concern only, not
a correctness or security defect.
**Fix:** Promote a small public date-coercion helper (e.g. `crs_audit.as_date` or a shared
`crawler.dates` util) and import that, or inline the one-line
`date.fromisoformat(str(x)[:10])` coercion locally so `index_health` owns its own parsing.

### IN-02: Stale `auditor.py:207` call-site line reference in the `gate_subset` alias comment (and its test)

**File:** `crawler/auditor.py:94`; also `crawler/tests/test_gate_subset.py:60`
**Issue:** The back-compat-alias comment states `audit_one`'s call site is at
"auditor.py:207", but the actual `_gate_or_raise(subset, db)` call is at `auditor.py:212`
(verified: `grep -n` puts the call at line 212; line 207 is the `if factor is None and not
auditors.is_derived(...)` guard). The identical "auditor.py:207" reference is repeated in
the test comment. Behavior is correct — the alias identity is proven by
`test_gate_subset_is_the_back_compat_alias` (green) — this is only an inaccurate
documentation cross-reference.
**Fix:** Update both comments to reference `auditor.py:212`, or drop the brittle absolute
line number in favor of the symbol name (`audit_one`'s `_gate_or_raise(...)` call).

### IN-03: `probe_snapshot` does not escape SQL `LIKE` metacharacters in `family`, so a family name containing `_` or `%` over-matches sibling families

**File:** `crawler/index_health.py:271-274` (`WHERE relpath LIKE ?`, bound `f"{family}/%"`)
**Issue:** The family filter correctly binds `family` as a SQL parameter (preventing SQL
injection), but the value is used inside a `LIKE` pattern where `_` (any single char) and
`%` (any run) are wildcards. A `family` argument containing either metacharacter silently
over-matches. Reproduced: `probe_snapshot(db, "d_i", max_age_days=3650, as_of="2026-07-17")`
against a family stored under `dxi/` returns `SNAPSHOT_OK` — validating the wrong corpus
family. Today `family` is a controlled constant (`"dli"`) and the function is defined-only
(no verb wires it this phase), so no live path over-matches; this is a latent generality
edge, not a security hole.
**Fix:** Either constrain callers to metacharacter-free family names, or escape the pattern
and add an `ESCAPE` clause, e.g.:
```python
esc = family.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
rows = con.execute(
    "SELECT text, chunk_sha, crawl_date FROM chunks WHERE relpath LIKE ? ESCAPE '\\'",
    (f"{esc}/%",),
).fetchall()
```

---

_Reviewed: 2026-07-18T05:16:51Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
