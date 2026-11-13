---
phase: 40-safe-freshness-effective-date-foundation
plan: 02
subsystem: api
tags: [crs-registry, grounding, gate-subset, single-trust-path, safe-09, auditor, fail-closed]

# Dependency graph
requires:
  - phase: 32-crs-audit-vertical-slice
    provides: "_gate_or_raise private grounding gate + audit_one spine (auditor.py) — the body promoted verbatim here"
  - phase: 40-safe-freshness-effective-date-foundation
    provides: "40-01 within_freshness / row_in_effect / _FRESHNESS_FIELD freshness mechanism — the other half of SAFE-09"
provides:
  - "crawler.auditor.gate_subset(subset, db) — the ONE public grounding-gate entry point (verbatim promotion of _gate_or_raise), reused by every v5.0 screen instead of re-implementing validate_registry"
  - "crawler.auditor._gate_or_raise — a working module-level back-compat alias bound to gate_subset (identity holds), preserving audit_one's frozen call site byte-for-byte"
  - "crawler/tests/test_gate_subset.py — alias-identity + hermetic behavior-parity coverage (empty no-op, consumed gap-row raise, PII-free error)"
affects: [phase-42-policy-resolver, phase-44-study-gate, phase-45-mec-sidecar, phase-46-conformance-release-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-trust-path promotion: a private gate is exposed as ONE public helper (verbatim body) + a back-compat alias, so future screens reuse the gate rather than forking validate_registry"
    - "Hermetic gate parity test: exploit that validate_registry SKIPS gap:true rows (and short-circuits an empty subset) BEFORE any db access, so the gate's raise/no-op paths are provable without a real corpus/searchindex db"

key-files:
  created:
    - crawler/tests/test_gate_subset.py
  modified:
    - crawler/auditor.py

key-decisions:
  - "SAFE-09 marked COMPLETE after 40-02: per the ROADMAP plan→requirement mapping (40-01→SAFE-09, 40-02→SAFE-09, 40-03→SAFE-10), SAFE-09's two Wave-1 plans are now both done; 40-03 delivers the distinct SAFE-10 snapshot preflight. The 40-01 deferral (leave Pending while shared with 40-02) is now resolved."
  - "gate_subset is a LITERAL body extraction (zero behavior change); the promotion adds a new public name + alias only — audit_one, _consumed_rows, _rule_citation_ids, gate call ordering, and the AuditGroundingError message strings are byte-for-byte frozen (Pitfall 2)."
  - "Commit typed feat (new public API surface gate_subset) rather than refactor, since the deliverable is a reusable public grounding-gate entry point for later screens; the underlying behavior is unchanged."
  - "Docstring kept verbatim (only the name changed via the def line) per the plan's 'keep the docstring content' instruction — no extra prose added to the extracted body."

patterns-established:
  - "Pattern 3 (Promoted single gate): auditor.gate_subset IS crs_rules.validate_registry (→ grounding.check_answer → searchindex), deduped and never forked; grep-assertable single call site the Phase 46 conformance gate can pin."

requirements-completed: [SAFE-09]

# Metrics
duration: ~22min
completed: 2026-07-18
---

# Phase 40 Plan 02: SAFE Freshness & Effective-Date Foundation Summary

**Promoted the private `auditor._gate_or_raise` to the ONE public `gate_subset(subset, db)` grounding-gate entry point via a verbatim body extraction + a `_gate_or_raise = gate_subset` back-compat alias, so every v5.0 screen reuses a single, grep-assertable trust path (`validate_registry` → `grounding.check_answer` → `searchindex`) instead of re-implementing it — proven with an alias-identity assertion, a hermetic empty/gap/PII-free parity test, and a zero-delta frozen-grid regression.**

## Performance

- **Duration:** ~22 min (dominated by the ~17-min full `crawler/tests` phase-gate run)
- **Started:** 2026-07-18T03:22:25Z
- **Completed:** 2026-07-18T03:44:39Z
- **Tasks:** 1
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- **`crawler.auditor.gate_subset(subset, db)`** — the former private `_gate_or_raise` promoted to a public helper via a byte-for-byte body extraction (the `crs_rules.validate_registry` call, the `violations → AuditGroundingError` raise, and the `for row in subset.rows: if row.gap: raise` loop). This is SAFE-09 SC2's "a single promoted gate-subset helper is reused by every screen rather than re-implemented per screen" — the ONE grounding gate Phases 42/44/45 will import instead of forking `validate_registry`.
- **`_gate_or_raise = gate_subset`** — a module-level back-compat alias placed immediately after the function, so `audit_one`'s call site (`_gate_or_raise(subset, db)`, unchanged in text) and any importer resolve to the SAME object. The `is` identity holds, keeping the frozen `test_auditor.py` / `test_auditor_dispatch.py` grid byte-for-byte green (Pitfall 2 / threat T-40-03).
- **`crawler/tests/test_gate_subset.py`** (84 lines) — hermetic, stdlib-`unittest`, synthetic-`Registry` coverage: (1) `gate_subset is _gate_or_raise` alias identity, (2) empty subset → `None` no-op, (3) consumed `gap:true` row → `AuditGroundingError` naming the gap `rule_id`, (4) error message PII-free (`assertNotIn("ev_", ...)`). No real corpus is touched: `validate_registry` skips gap rows via `continue` before any db access, so a `/nonexistent/index.db` path proves the paths never open a db.
- **No second/forked trust path introduced** — `gate_subset` calls only `crs_rules.validate_registry`; `grep -c "def _gate_or_raise"` is now 0 (only the alias remains).

## Task Commits

Each task was committed atomically:

1. **Task 40-02-01: Promote `_gate_or_raise` → public `gate_subset` (literal extraction + back-compat alias) + hermetic parity test** — `529f788` (feat)

**Plan metadata:** committed separately with this SUMMARY + tracking updates (docs).

_No deviation or extra fix commits were needed — the promotion is a pure rename + alias with zero behavior change._

## Files Created/Modified

- `crawler/auditor.py` (modified, +6/-1) — renamed `def _gate_or_raise(subset: Registry, db) -> None:` → `def gate_subset(...)` (docstring/body verbatim), added the `_gate_or_raise = gate_subset` alias. `audit_one`, `_consumed_rows`, `_rule_citation_ids`, gate ordering, and the `AuditGroundingError` message strings are untouched.
- `crawler/tests/test_gate_subset.py` (created, 84 lines) — `TestGateSubsetAliasIdentity` (alias `is` identity) + `TestGateSubsetBehaviorParity` (empty no-op / consumed gap-row raise / PII-free error), built on an in-test `_gap_row()` factory (placeholder `Citation(chunk_id="g/p.md#000", quote="p")`, `gap=True`, `gap_reason="doc"`).

## Decisions Made

- **SAFE-09 marked COMPLETE after 40-02.** The ROADMAP's explicit plan→requirement mapping assigns SAFE-09 to plans 40-01 **and** 40-02 (both Wave 1) and SAFE-10 to plan 40-03 (Wave 2). 40-01 shipped the freshness/effective-date/staleness-bound mechanism; 40-02 ships the shared-gate-reuse half. With both SAFE-09 plans done, the requirement is fully delivered — the 40-01 "leave Pending while shared with 40-02" deferral is now resolved, and 40-03 delivers the distinct SAFE-10. REQUIREMENTS.md/ROADMAP.md updated accordingly.
- **`feat` commit type.** The deliverable is a new public API surface (`gate_subset`) reused by later screens, so `feat` is more honest than `refactor` even though the extracted behavior is byte-for-byte identical.
- **Verbatim docstring.** Per the plan's "keep the docstring content (update only the name)", the function docstring was preserved exactly; only the `def` name changed and an explanatory comment was added on the alias line (outside the function body).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The alias identity, targeted verification, all six acceptance criteria, the frozen-grid regression, the full suite, and the conformance gate passed on the first implementation pass.

## Verification Evidence

- **Task 40-02-01 verify (targeted):** `.venv/bin/python -m pytest crawler/tests/test_gate_subset.py crawler/tests/test_auditor.py crawler/tests/test_auditor_dispatch.py -q` → **25 passed** (4 new gate_subset + 21 frozen grid).
- **Acceptance criteria (40-02-01):**
  - `grep -n "def gate_subset" crawler/auditor.py` → exactly 1 hit (line 75).
  - `grep -n "_gate_or_raise = gate_subset" crawler/auditor.py` → exactly 1 hit (line 96, the alias).
  - `grep -c "def _gate_or_raise" crawler/auditor.py` → **0** (old def gone; only the alias remains).
  - `.venv/bin/python -c "from crawler import auditor; print(auditor.gate_subset is auditor._gate_or_raise)"` → **True**.
  - `.venv/bin/python -m pytest crawler/tests/test_gate_subset.py -q` → **4 passed** (identity + empty no-op + gap-raise + PII-free).
  - `.venv/bin/python -m pytest crawler/tests/test_auditor.py crawler/tests/test_auditor_dispatch.py -q` → **21 passed**, ZERO deltas vs. the pre-change baseline (also 21 passed) — frozen grid preserved (Pitfall 2).
  - `git diff --stat crawler/auditor.py` → 1 file changed, 6 insertions(+), 1 deletion(-): only the gate rename + alias (no change to `audit_one`, `_consumed_rows`, `_rule_citation_ids`).
- **Call-site parity:** `grep -nE "_gate_or_raise\(subset, db\)" crawler/auditor.py` → the call text is byte-for-byte unchanged (now line 212; the original `:207` reference shifted only because the 5-line alias block precedes `audit_one`).
- **One-trust-path:** the only gate call in `auditor.py` is `crs_rules.validate_registry(subset, db)` (line 82) — no forked/parallel gate.
- **Wave/phase gate — full suite:** `.venv/bin/python -m pytest crawler/tests -q` → **867 passed, 1 skipped, 355 subtests passed** (0:16:57). This is exactly 40-01's 863 + 4 new `test_gate_subset.py` tests — the definitive parity proof for the promotion.
- **Wave/phase gate — conformance:** `.venv/bin/python scripts/run_conformance.py` → **PASS** (SAFE-01..SAFE-08, 75 passed) — v4.x safety conformance unchanged.

## Threat Model Coverage

- **T-40-03 (EoP/Tampering: gate drift or forked trust path, HIGH):** mitigated — pure rename + `_gate_or_raise = gate_subset` alias (identity assertion), body extracted VERBATIM, full `test_auditor.py`/`test_auditor_dispatch.py`/`test_full_audit_*` regression asserts zero delta (867 vs 863+4), and `gate_subset` calls `crs_rules.validate_registry` only (grep-assertable single gate). The AuditGroundingError message strings are unchanged and PII-free.
- **T-40-SC (supply-chain, LOW):** N/A — zero new runtime dependencies; `pyproject.toml` `[project].dependencies` unchanged (stdlib-only test).

## Next Phase Readiness

- `auditor.gate_subset` is the discoverable, grep-assertable single grounding-gate entry point Phases 42 (POLICY), 44 (STUDY), and 45 (MEC) will import and reuse — no screen needs to re-implement `validate_registry`.
- Phase 46's conformance/release gate can pin the single call site (`gate_subset` → `crs_rules.validate_registry`) as the ONE trust path across CRS + all v5.0 sidecars.
- SAFE-09 is complete (freshness/effective-date mechanism from 40-01 + shared gate reuse from 40-02). Plan 40-03 (SAFE-10 snapshot preflight — `probe_snapshot`/`SnapshotHealth`/clean refusal) is the remaining Wave 2 plan for this phase.

---
*Phase: 40-safe-freshness-effective-date-foundation*
*Completed: 2026-07-18*

## Self-Check: PASSED

- Files verified present: `crawler/auditor.py`, `crawler/tests/test_gate_subset.py`, `.planning/phases/40-safe-freshness-effective-date-foundation/40-02-SUMMARY.md`.
- Commit verified in history: `529f788` (feat: promote `_gate_or_raise` → `gate_subset` + alias + hermetic parity test).
- Symbols verified in `crawler.auditor`: `gate_subset` present; `gate_subset is _gate_or_raise` → `True` (alias identity holds).
