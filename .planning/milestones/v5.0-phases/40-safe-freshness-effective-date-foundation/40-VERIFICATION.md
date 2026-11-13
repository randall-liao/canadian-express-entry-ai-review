---
phase: 40-safe-freshness-effective-date-foundation
verified: 2026-07-18T01:40:00-04:00
status: passed
score: 15/15 must-haves verified
overrides_applied: 0
gaps: []
human_verification: []
requirements_verified:
  - SAFE-09
  - SAFE-10
gates:
  focused_phase_tests: "53 passed (freshness_staleness + gate_subset + snapshot_health + snapshot_refusal + crs_rules)"
  frozen_grid_regression: "69 passed (auditor + auditor_dispatch + crs_audit + index_health + audit_index_refusal + crs_no_inlined_rules)"
  full_suite: "888 passed, 1 skipped (LOCAL-ONLY real-index positive control), 355 subtests passed — 0:15:19"
  conformance: "PASS — 75 passed (SAFE-01..SAFE-08)"
  publish_safe: "0 violations (383 tracked files scanned)"
review_fixes_verified:
  - "a57cd70 — WR-01 default as_of=today (index_health.py:299)"
  - "7640bbb — WR-02 TOCTOU second-open guard (index_health.py:264-267)"
  - "88f2657 — WR-01 re-review future-date fails closed to stale (index_health.py:317-320)"
info_observations_non_blocking:
  - "IN-01 index_health imports crs_audit._as_date (private cross-module; lazy, no cycle)"
  - "IN-02 stale 'auditor.py:207' line reference in alias comment (actual call at :212)"
  - "IN-03 probe_snapshot LIKE metacharacters unescaped (family is controlled constant 'dli', defined-only, param-bound — latent edge for Phase 44/45)"
---

# Phase 40: SAFE Freshness & Effective-Date Foundation — Verification Report

**Phase Goal:** Land the shared freshness/effective-date/staleness guard and snapshot-aware
preflight *before* later v5.0 screens depend on them, so no out-of-window or stale grounded row or
local snapshot can contribute to a green verdict.
**Verified:** 2026-07-18T01:40:00-04:00
**Status:** passed
**Re-verification:** No — initial verification.
**Requirements:** SAFE-09, SAFE-10

---

## Goal Achievement

Phase 40 is a **foundation phase** — it lands four fail-closed MECHANISMS (`within_freshness` /
`row_in_effect`; the promoted public `gate_subset`; `probe_snapshot`/`SnapshotHealth`/`SNAPSHOT_*`;
and the `_require_readable_snapshot` refusal wrapper) that later screens (Phases 42/44/45) will wire
and Phase 46 will prove centrally. The plans explicitly scope these as *defined-only* (not wired
into any shipped decider or user-facing verb this phase — wiring them would mutate the frozen CRS
grid). I verified the mechanisms **exist, are substantive, are correctly composed, and fail closed**
against independent hermetic exercises + the full test/conformance/publish-safe gate battery. Every
"defined-only, not wired" claim was confirmed as the intended scope, not a stub.

### Observable Truths — ROADMAP Success Criteria (the contract)

| #    | Success Criterion                                                                                                                    | Status     | Evidence |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------- | -------- |
| SC1  | Shared freshness guard rejects any grounded row / snapshot outside its effective window or beyond its staleness bound (mirrors `within_validity`/`_in_window`) | ✓ VERIFIED | `within_freshness` fails closed on no-window/stale/after-reference; `row_in_effect` fails closed outside either window source; `probe_snapshot` classifies stale/drifted/future→`snapshot_stale`/`snapshot_drifted`. All spot-checked (see below). |
| SC2  | Staleness bound read from a grounded/config value — never inlined — AND a single promoted gate-subset helper reused per screen         | ✓ VERIFIED | Bound read via `_window_days` (crs_audit.py:185); `no_inlined_volatile_rules(["crawler/crs_audit.py"])==[]` and `["crawler/index_health.py"]==[]`; `gate_subset` is the ONE public gate (auditor.py:75), `_gate_or_raise = gate_subset` alias (auditor.py:96). |
| SC3  | Preflight refuses cleanly — stable PII-free reason code, non-zero exit, zero artifacts — on missing/empty/unreadable/corrupt/stale/drifted | ✓ VERIFIED | `_require_readable_snapshot` → exit 2 (`EXIT_INVALID_INPUT`), envelope `ok=False`, `error.type=invalid_input`, message carries `reason=snapshot_<code>`, PII-free (`ev_` absent); `test_snapshot_refusal.py` asserts `audit_runs==0` + no report files. |
| SC4  | Same preflight passes a healthy index/snapshot and permits downstream                                                                 | ✓ VERIFIED | Healthy fixture → `probe_snapshot(...).status == "ok"`; `_require_readable_snapshot(...) is None` with no stdout emitted. |

### Observable Truths — PLAN must-have truths

**Plan 40-01 (SAFE-09 freshness/effective-date mechanism)**

| #     | Truth | Status | Evidence |
| ----- | ----- | ------ | -------- |
| 01-T1 | `within_freshness` False for no-window / stale / after-reference; True only strictly in-window | ✓ VERIFIED | Direct exercise: no-window→False, delta0→True, delta180 (boundary inclusive)→True, delta181→False, delta<0→False. Impl crs_audit.py:173-189 (`0 <= delta <= window`). |
| 01-T2 | `row_in_effect` False outside EITHER machine_check or volatility window; True when both None | ✓ VERIFIED | Direct exercise: mc before/at-`effective_to`→False, in-window→True; volatility before→False, in→True; both-None→True; malformed date **raises** (fail-closed, not swallowed). Impl crs_audit.py:377-394. |
| 01-T3 | Bound read from grounded `validity_window` via `_window_days`; no inlined literal (self-scan `[]`) | ✓ VERIFIED | `_FRESHNESS_FIELD={"dli_snapshot":"snapshot_max_age"}` strings-only (crs_audit.py:47); `no_inlined_volatile_rules([...crs_audit.py])==[]`. |
| 01-T4 | `registry_fingerprint` changes when a `snapshot_max_age` `window_days` is tampered | ✓ VERIFIED | `TestSnapshotFreshnessBoundFingerprint` (3 tests) PASS: 64-hex stable, identical-equal, tamper 180→365 flips hash. |

**Plan 40-02 (SAFE-09 promote `_gate_or_raise` → public `gate_subset`)**

| #     | Truth | Status | Evidence |
| ----- | ----- | ------ | -------- |
| 02-T1 | `gate_subset` is the ONE public grounding-gate entry point, verbatim extraction of `_gate_or_raise` | ✓ VERIFIED | auditor.py diff = pure rename (`def _gate_or_raise`→`def gate_subset`) + alias, body byte-identical (`+7/-1`); calls only `crs_rules.validate_registry` (auditor.py:82) — no forked path. |
| 02-T2 | `_gate_or_raise` alias bound to `gate_subset`; `audit_one` call site unchanged; frozen grid green | ✓ VERIFIED | `auditor.gate_subset is auditor._gate_or_raise` → True; call site `_gate_or_raise(subset, db)` unchanged (auditor.py:212); `test_auditor.py`+`test_auditor_dispatch.py` green in the 69-test frozen-grid run. |
| 02-T3 | Raises `AuditGroundingError` on a consumed gap row / ungrounded subset; empty subset is a no-op | ✓ VERIFIED | Direct exercise: empty→None; gap row→`AuditGroundingError` PII-free (`consumed rule row 'safe.freshness.gap' is an ungrounded coverage gap`). |

**Plan 40-03 (SAFE-10 snapshot preflight)**

| #     | Truth | Status | Evidence |
| ----- | ----- | ------ | -------- |
| 03-T1 | `probe_snapshot` classifies into closed `SNAPSHOT_*` vocab, read-only + side-effect-free | ✓ VERIFIED | All 7 codes reproduced (ok/missing/empty/unreadable/corrupt/drifted/stale); missing-path proof `db.exists()==False` (creates nothing); read-only `file:<db>?mode=ro` connect (index_health.py:265). |
| 03-T2 | Missing/empty, per-chunk drift, and beyond-`max_age_days` each map to a distinct code; healthy→OK | ✓ VERIFIED | family-missing→`snapshot_missing`, tampered sha→`snapshot_drifted`, old date→`snapshot_stale`, blank date→`snapshot_stale` (fail-closed), future date→`snapshot_stale`, `max_age_days=None`→ok, present+fresh→ok. |
| 03-T3 | `_require_readable_snapshot` → ONE invalid_input/exit-2 refusal, stable `reason=<code>`, PII-free, ZERO artifacts (before `open_vault`) | ✓ VERIFIED | Direct drive: code=2, envelope `ok=False`/`invalid_input`, `reason=snapshot_stale` present, no `ev_`; `test_refusal_writes_zero_artifacts` asserts `audit_runs==0`; wrapper never calls `open_vault`. |
| 03-T4 | Healthy family returns None (SC4) | ✓ VERIFIED | Direct drive over a healthy fixture → `None`, no stdout. |

**Score:** 15/15 truths verified (4 ROADMAP SCs + 11 PLAN must-have truths; SAFE-09 + SAFE-10 both satisfied).

### Deferred Items

None. The concrete grounded DLI `snapshot_max_age` bound row + its authoritative citation are an
explicit Phase 41 (STUDY-01) data responsibility (ROADMAP Phase 41: "The one new corpus artifact: a
refreshable, dated, content-hashed, auto-indexed DLI/PGWP family"). This is a **frozen contract**,
not a Phase 40 gap — Phase 40 ships the field-name contract (`_FRESHNESS_FIELD`) and proves the
mechanism against synthetic grounded fixtures. Wiring the mechanisms into deciders/verbs is scoped to
Phases 42/44/45; proving them centrally is Phase 46. None of these are Phase-40 must-haves.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/crs_audit.py` | `within_freshness`, `row_in_effect`, `_FRESHNESS_FIELD` | ✓ VERIFIED | Symbols at :173, :377, :47. Diff `+54/-0` — purely additive; frozen `within_validity`/`_in_window`/`arranged_employment_guard` unchanged. |
| `crawler/tests/test_freshness_staleness.py` | SAFE-09 negative controls + self-scan | ✓ VERIFIED | 191 lines; `TestWithinFreshness`, `TestRowInEffect`, `TestNewFreshnessHelpersNoInline`. Part of the 53-pass focused run. |
| `crawler/tests/test_crs_rules.py` | fingerprint-drift over `snapshot_max_age` row | ✓ VERIFIED | `TestSnapshotFreshnessBoundFingerprint` (+45 lines), 3 tests PASS. |
| `crawler/auditor.py` | public `gate_subset` + `_gate_or_raise` alias | ✓ VERIFIED | :75 def, :96 alias. Diff `+7/-1`, body verbatim. |
| `crawler/tests/test_gate_subset.py` | alias-identity + hermetic parity | ✓ VERIFIED | 84 lines; identity + empty no-op + gap-raise + PII-free. |
| `crawler/index_health.py` | `SnapshotHealth`, `probe_snapshot`, `SNAPSHOT_*`, `_INDEX_TO_SNAPSHOT` | ✓ VERIFIED | :196, :224, :59-65, :69. Diff `+164` additive; frozen `probe_index`/`IndexHealth`/`INDEX_*` untouched. |
| `crawler/cli.py` | `_require_readable_snapshot` preflight wrapper | ✓ VERIFIED | :779. Diff `+32` additive; `_require_readable_index` unchanged; not wired to any verb. |
| `crawler/tests/test_snapshot_health.py` | closed-code classification table | ✓ VERIFIED | 199 lines; `ProbeSnapshotReasonCodes` + `_build_snapshot_index` fixture. |
| `crawler/tests/test_snapshot_refusal.py` | CLI refusal + zero-artifact + PII + healthy control | ✓ VERIFIED | 141 lines; drives wrapper directly (no verb exists this phase). |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `crs_audit.within_freshness` | `crs_audit._window_days` | grounded bound read (never inlined) | ✓ WIRED | `window = _window_days(registry, field)` (crs_audit.py:185); fail-closed `if window is None: return False`. |
| `crs_audit.row_in_effect` | `crs_audit._in_window` | composition over machine_check + volatility windows | ✓ WIRED | Two `_in_window(...)` guards (crs_audit.py:390,392). |
| `auditor.audit_one` | `auditor.gate_subset` | `_gate_or_raise` alias at frozen call site | ✓ WIRED | `_gate_or_raise(subset, db)` (auditor.py:212), alias `is` gate_subset. |
| `auditor.gate_subset` | `crs_rules.validate_registry` | the ONE shipped grounding gate (never forked) | ✓ WIRED | `crs_rules.validate_registry(subset, db)` (auditor.py:82) — only gate call in the module. |
| `index_health.probe_snapshot` | `index_health.probe_index` | reuse of missing/empty/unreadable/corrupt/drifted base | ✓ WIRED | `base = probe_index(db)` + `_INDEX_TO_SNAPSHOT[base.status]` (index_health.py:251-253). |
| `index_health.probe_snapshot` | `searchindex.chunk_sha` | per-chunk content-drift fingerprint (no new hash) | ✓ WIRED | `chunk_sha(text) != sha → SNAPSHOT_DRIFTED` (index_health.py:281). |
| `cli._require_readable_snapshot` | `contract.EXIT_INVALID_INPUT` | frozen invalid_input/exit-2 refusal via `_vault_fail` (before open_vault) | ✓ WIRED | `_vault_fail(args, contract.INVALID_INPUT, health.message(db), contract.EXIT_INVALID_INPUT)` (cli.py:807). |

> **Scope note on wiring:** `within_freshness`, `row_in_effect`, `probe_snapshot`, and
> `_require_readable_snapshot` are correctly **defined-only** (no shipped decider or user-facing verb
> calls them this phase). Grep confirms zero `_cmd_*` call sites for `_require_readable_snapshot` and
> zero decider references for the freshness helpers. This is the explicit, planned scope ("land …
> *before* the screens that depend on them"), not an ORPHANED-artifact defect.

### Data-Flow Trace (Level 4)

Not applicable in the rendering sense — Phase 40 ships deterministic backend predicates/classifiers,
not UI. The equivalent "does real data flow" check is the grounded-bound trace: `within_freshness`
sources its window from a grounded `validity_window` row (never a literal); `probe_snapshot` reads
real `chunk_sha`/`crawl_date` from the snapshot DB and the caller supplies `max_age_days`. All three
were exercised against synthetic-but-real fixture DBs and produced correct, non-hardcoded verdicts.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| `within_freshness` boundary/fail-closed | direct import exercise | no-window→F, delta0→T, delta180→T, delta181→F, delta<0→F | ✓ PASS |
| `row_in_effect` both window sources + malformed | direct import exercise | mc F/F/T, vol F/T, both-None T, malformed→ValueError | ✓ PASS |
| self-scan clean | `no_inlined_volatile_rules([...])` | `[]` for both crs_audit.py and index_health.py | ✓ PASS |
| `gate_subset` identity + parity | direct import exercise | identity True, empty→None, gap→AuditGroundingError PII-free | ✓ PASS |
| `probe_snapshot` full closed vocab | 12-case direct exercise | ok/missing(family)/missing(path,no-create)/empty/corrupt/drifted/stale/blank-stale/omitted-as_of-ok/future-stale/None-skip/boundary-ok all correct | ✓ PASS |
| TOCTOU second-open guard | mock probe_index OK + absent target | `snapshot_unreadable` (no traceback) | ✓ PASS |
| SQL param-binding | family `dli' OR '1'='1` | safe `snapshot_missing` (no injection/error) | ✓ PASS |
| `_require_readable_snapshot` refusal | direct drive, `--json` | exit 2, `ok=False`, `invalid_input`, `reason=snapshot_stale`, PII-free | ✓ PASS |
| `_require_readable_snapshot` healthy | direct drive | returns `None`, no stdout | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared by the Phase 40 plans/summaries; the phase's
runnable-verification contract is the pytest/conformance/publish-safe gate battery below, all
executed fresh at HEAD by the verifier.

| Gate | Command | Result | Status |
| ---- | ------- | ------ | ------ |
| Phase-40 focused | `.venv/bin/python -m pytest crawler/tests/test_freshness_staleness.py test_gate_subset.py test_snapshot_health.py test_snapshot_refusal.py test_crs_rules.py -q` | 53 passed | ✓ PASS |
| Frozen-grid regression | `.venv/bin/python -m pytest test_auditor.py test_auditor_dispatch.py test_crs_audit.py test_index_health.py test_audit_index_refusal.py test_crs_no_inlined_rules.py -q` | 69 passed | ✓ PASS |
| Full suite | `.venv/bin/python -m pytest crawler/tests -q` | 888 passed, 1 skipped, 355 subtests passed (0:15:19) | ✓ PASS |
| Conformance | `.venv/bin/python scripts/run_conformance.py` | PASS — 75 passed (SAFE-01..08) | ✓ PASS |
| Publish-safe | `.venv/bin/python scripts/check_publish_safe.py` | 0 violations (383 tracked files) | ✓ PASS |

The single skip is `@unittest.skipUnless`-guarded and requires the git-ignored LOCAL-ONLY real
`corpus/index.db` (a positive-control that only runs when the full corpus is present locally). It is
a documented environmental skip, unrelated to Phase 40's synthetic-fixture tests, and not a masked
failure.

### Review-Fix Verification (all three Warning fixes confirmed at HEAD)

| Commit | Fix | Evidence at HEAD | Status |
| ------ | --- | ---------------- | ------ |
| `a57cd70` | WR-01: default `as_of` to today, never parse literal `"None"` | index_health.py:299 `as_of = as_of if as_of is not None else date.today().isoformat()`; omitted-`as_of` fresh fixture → `ok` reproduced | ✓ FIXED |
| `7640bbb` | WR-02: guard the second read-only connect against a TOCTOU race | index_health.py:264-267 `except sqlite3.OperationalError → SNAPSHOT_UNREADABLE`; `try/finally` entered only after connect; mock-forced base-OK + absent target → `snapshot_unreadable` reproduced | ✓ FIXED |
| `88f2657` | WR-01 re-review: a future-dated snapshot fails closed to stale (two-sided window) | index_health.py:317-320 `if delta < 0: return SNAPSHOT_STALE`; future `crawl_date=2099-01-01` → `snapshot_stale` reproduced; `delta==0` boundary still `ok` (inclusive, matches sibling) | ✓ FIXED |

All ten task/fix commits (`142ff92`, `418f018`, `4eb6310`, `529f788`, `0ee89c3`, `ba64671`,
`3818c0d`, `a57cd70`, `7640bbb`, `88f2657`) are present in `git log`. Working tree is clean except
the pre-existing untracked `.planning/research/.cache/` (explicitly ignorable).

### Frozen-Contract & Scope Checks

| Check | Result | Status |
| ----- | ------ | ------ |
| Shipped registry `crawler/data/crs_rules/*.yaml` + COVERAGE.md unchanged | `git status --porcelain crawler/data/crs_rules/` empty | ✓ |
| No concrete DLI `snapshot_max_age` bound/value fabricated | No registry row added; deferred to Phase 41 per ROADMAP | ✓ |
| `within_validity` / `_in_window` / `arranged_employment_guard` byte-frozen | crs_audit.py diff `+54/-0`, no frozen-fn signature changes | ✓ |
| `probe_index` / `IndexHealth` / `INDEX_*` / `_require_readable_index` byte-frozen | index_health.py additive-only (no deletions to frozen lines); cli.py additive-only; all importable, `INDEX_OK=="ok"` | ✓ |
| `_gate_or_raise` back-compat alias + `audit_one` call site unchanged | identity `is` holds; call text unchanged at :212 | ✓ |
| No `PublicAuditEnvelope` / CRS-total / decider / CLI-verb / `add_argument`/`add_parser` changes | grep of phase diff finds only a docstring reference to `_cmd_vault_audit` | ✓ |
| No new runtime dependencies | `pyproject.toml` + `poetry.lock` unchanged in phase diff | ✓ |
| Only `crawler/` source + tests changed (plus `.planning/`) | 4 source + 5 test files, nothing else | ✓ |
| `probe_index`, `within_validity`, `_in_window`, `arranged_employment_guard`, `_require_readable_index`, audit behavior remain compatible | 69-test frozen-grid + 75 conformance + 888 full suite all green | ✓ |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| SAFE-09 | 40-01, 40-02 | Shared freshness/effective-date guard; staleness bound grounded/config, not inlined | ✓ SATISFIED | `within_freshness`+`row_in_effect` fail-closed mechanism; bound via `_window_days`, self-scan `[]`; single promoted `gate_subset` reused. |
| SAFE-10 | 40-03 | Corpus/index/snapshot preflight refuses cleanly (PII-free reason, non-zero exit, zero artifacts) on missing/empty/unreadable/corrupt/stale/drifted | ✓ SATISFIED | `probe_snapshot` closed vocab + `_require_readable_snapshot` exit-2/PII-free/zero-artifact refusal + healthy None. |

No orphaned requirements: REQUIREMENTS.md maps only SAFE-09 and SAFE-10 to Phase 40, both claimed by
plans and verified.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `crawler/index_health.py` | 289 | imports private `crs_audit._as_date` across module boundary (IN-01) | ℹ️ Info | Maintainability/coupling only; lazy import, no cycle. Does not affect Phase 40 goal. |
| `crawler/auditor.py` / `test_gate_subset.py` | 94 / 60 | stale `auditor.py:207` line reference (actual call at :212) (IN-02) | ℹ️ Info | Documentation cross-reference inaccuracy; alias identity proven green. Does not affect goal. |
| `crawler/index_health.py` | 271-274 | `LIKE ?` pattern does not escape `_`/`%` metacharacters (IN-03) | ℹ️ Info | Latent generality edge. `family` is the controlled constant `"dli"` (no metacharacters), the function is defined-only (no verb wires it), and binding is parameterized (no SQLi). No live path over-matches this phase. Should be addressed when Phase 44/45 wires a verb. |

No `TODO`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` debt markers were introduced in the modified files. No
stub `return null`/`return []`/empty-handler patterns that flow to output — the `SNAPSHOT_OK`
"present and fresh" path is a genuine positive verdict, and empty/None returns are deliberate
fail-closed / permit-downstream contract values proven by tests.

**Independent adjudication of the 3 Info observations:** None invalidate the phase goal. IN-01 and
IN-02 are cosmetic/coupling notes with no behavioral effect. IN-03 is a real but *latent* edge that
can only manifest once a future phase wires a verb with an attacker-influenced or metacharacter-bearing
family name; with the controlled `"dli"` constant and defined-only status, no Phase-40 must-have or
success criterion is affected. The final REVIEW correctly recorded 0 Critical / 0 Warning.

### Human Verification Required

**None.** Phase 40 is deterministic backend/CLI behavior (predicates, classifiers, a refusal
wrapper). Every observable truth is provable programmatically and was independently exercised by the
verifier (hermetic import-level spot-checks + full pytest/conformance/publish-safe gates). No plan
declared a `<verify><human-check>` block. No visual/real-time/external-service surface exists this
phase. Inventing manual UAT here would be noise.

### Gaps Summary

None. All 15 must-haves (4 ROADMAP success criteria + 11 PLAN must-have truths) are VERIFIED, both
requirements (SAFE-09, SAFE-10) are SATISFIED, all three review-fix commits are confirmed present and
behaviorally correct at HEAD, every frozen contract holds, and the full validation battery is green
(888 passed / 1 benign skip; conformance PASS 75; publish-safe 0 violations). The phase goal —
landing the shared fail-closed freshness/effective-date/staleness guard and the snapshot-aware
preflight as reusable foundations before dependent v5.0 screens — is achieved.

---

_Verified: 2026-07-18T01:40:00-04:00_
_Verifier: the agent (gsd-verifier)_
