---
phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
plan: 04
subsystem: corpus
tags: [dli, pgwp, ircc, conformance, grounding, crs-rules, searchindex, fts5, publish-safe, refresh-dli, zero-dep, network-free, offline]

# Dependency graph
requires:
  - phase: 41-01
    provides: "crawler/dli_snapshot.py generator + the c6a0d65/e3c08f1 live-refresh UA/url fix that unblocked the real refresh"
  - phase: 41-02
    provides: "top-level `refresh-dli` CLI verb (fixed endpoint, five-key envelope, fail-closed refusal)"
  - phase: 41-03
    provides: "crawler/data/crs_rules/study_dli.yaml — the one grounded study.dli.designation row + auto-index/grounding proof over the golden family"
  - phase: 31-crs-rule-registry
    provides: "crs_rules.load_registry/validate_registry/retrieve_what_you_cite/coverage_report/no_inlined_volatile_rules"
  - phase: 23-searchindex
    provides: "searchindex.build_index/resolve (frozen FTS5 builder + citation resolver)"
provides:
  - "crawler/tests/test_dli_conformance.py — phase-level static + regression conformance gate (no-inline / no-max-age / zero-dep / network-free-audit / frozen-contract / inert-decider) + skip-guarded LOCAL live study.dli.designation grounding against the REAL dli-bearing corpus/index.db"
  - "Real end-to-end closeout: live `refresh-dli` (exit 0, 1136 institutions) -> real git-ignored corpus/dli/ family -> rebuilt corpus/index.db (10207 chunks, 2272 dli) -> whole-registry conformance grounds study.dli.designation (agrees + grounds, 0 violations)"
  - "STUDY-01 closed end-to-end: refreshable, as-of/crawl_date-stamped, content-hashed, auto-indexed DLI/PGWP family grounded for citation with a structurally network-free audit path"
affects: [phase-44-study-decider, phase-42, phase-43]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Phase-level static conformance gate: no_inlined_volatile_rules + no-max-age registry scan + tomllib zero-dep parse + AST network-import scan of the audit path + git-diff-quiet frozen-contract proof — all offline"
    - "Skip-guarded LOCAL-ONLY live grounding: @skipUnless(real dli-bearing corpus/index.db present) mirrors the _REAL_DB.is_file() precedent so CI / fresh clone stays green + structural-only"
    - "dli-aware live-doc counts: git-ignored corpus/dli/ makes the real-corpus smoke count 742 + <dli .md count>; CI (no dli) stays 742"

key-files:
  created: []
  modified:
    - "crawler/tests/test_searchindex.py — TestRealCorpus docs count made dli-aware (deviation)"
    - "crawler/tests/test_dupaudit.py — TestRealCorpus live_docs count made dli-aware (deviation)"

key-decisions:
  - "The REQUIRED real refresh (Task 2 step 1) succeeded on resume (exit 0, ok:true) because the pre-resume 41-01 fix c6a0d65 removed the custom _UA that the upstream Akamai CDN blackholed — the audit path stays structurally network-free (proven by test_dli_conformance)"
  - "Real corpus/index.db rebuilt over corpus/ INCLUDING the live dli family (10207 chunks, 2272 dli) so the shipped whole-registry v4.x conformance grounds study.dli.designation against a REAL dli-bearing index — never a dli-less rebuild"
  - "Two TestRealCorpus smoke tests hardcoded the 742 committed-corpus baseline; the phase's REQUIRED real refresh legitimately raises the on-disk count to 1878 (742 + 1136 dli). Fixed the STALE test expectation dli-aware (Rule 1) — production searchindex/dupaudit stay byte-for-byte frozen and correct"

patterns-established:
  - "Pattern: real-index conformance closeout — a git-ignored corpus family is proven end-to-end (refresh -> reindex -> whole-registry grounding) with skip-guarded LOCAL tests, never claiming green on a dli-less index"
  - "Pattern: dli-aware real-corpus assertions — hardcoded committed-corpus counts must add the git-ignored family delta when a local refresh has populated it, so the same test stays green in CI (742) and locally (1878)"

requirements-completed: [STUDY-01]

# Metrics
duration: ~80min
completed: 2026-07-18
---

# Phase 41 Plan 04: Phase Conformance Gate + Real End-to-End DLI Closeout Summary

**Shipped the offline phase-level conformance gate (no inlined/self-grounded max-age, zero new dependencies, structurally network-free audit path, frozen Phase-40/index/decider contracts, inert study decider) AND completed the REAL end-to-end closeout: a live `refresh-dli` (exit 0, 1,136 institutions / 1,454 campuses, `as_of=2026-07-16T18:08:26Z`) wrote the real git-ignored `corpus/dli/` family, the frozen indexer rebuilt `corpus/index.db` (10,207 chunks, 2,272 dli) including it, and the whole-registry v4.x conformance grounds `study.dli.designation` against the REAL dli-bearing index (agrees + grounds, 0 violations) — full suite 967 passed / 2 skipped, publish-safe 0 violations, conformance PASS. STUDY-01 closed.**

## Performance

- **Duration:** ~80 min (resume closeout; dominated by two ~18-min full-suite runs + a ~16-min real-corpus smoke reverify + the real refresh/reindex)
- **Started:** 2026-07-18T18:04:12Z (resume)
- **Completed:** 2026-07-18T22:00:00Z (approx)
- **Tasks:** 2 (both complete)
- **Files modified:** 2 (deviation) + 0 created this resume (test_dli_conformance.py was created in the pre-checkpoint Task 1/Task 2 commits)

## Accomplishments

- **Task 1 (pre-checkpoint) — phase-level static + regression conformance gate**: `crawler/tests/test_dli_conformance.py` asserts (all offline): `no_inlined_volatile_rules([dli_snapshot.py, cli.py, study_dli.yaml]) == []`; no shipped `max_age`/`snapshot_max_age` registry row and no max-age/window token in `study_dli.yaml`; `[project].dependencies == {pyyaml, pydantic, platformdirs}` (zero new deps); no network client or `dli_snapshot` import on the audit path (`crs_audit`/`crs_rules`/`grounding`/`searchindex`/`auditors/*`); frozen Phase-40/index/decider contracts byte-for-byte unchanged (git diff --quiet); coverage stays `complete`, `additional.study` present, the new row covers no required grid label.
- **Task 2 — real out-of-band refresh + reindex + live grounding + full gates**:
  - Real refresh: `--json refresh-dli` → **exit 0**, `ok:true`, 1,136 institutions / 1,454 campuses, `as_of=2026-07-16T18:08:26Z`, `family_sha256=a3a5397…` — real git-ignored `corpus/dli/` (1,136 `.md` + `manifest.json`).
  - Real reindex: `index corpus/ --db corpus/index.db` → **1,878 docs → 10,207 chunks** (was 7,935; **2,272 dli chunks**).
  - Live grounding proof (now RUNS, no longer skipped): UofT chunk `dli/O19332746152.md#000` resolves; `source_type='dli'`, `crawl_date='2026-07-16T18:08:26Z'`; `retrieve_what_you_cite(...)['study.dli.designation']` → `agrees_with_citation=True`, `grounds=True`; `validate_registry` → **0 violations** (whole registry).
  - Phase-close gates all green (see below).

## Task Commits

Each task was committed atomically (pre-checkpoint commits preserved, not rewritten):

1. **Task 1: Phase-level static + regression conformance gate** — `2459c4a` (test) — created `crawler/tests/test_dli_conformance.py`.
2. **Task 2 step 3: skip-guarded live study.dli.designation grounding proof** — `774dd94` (test) — added the `TestLiveDliGroundingRealIndex` class.
3. **Task 2 deviation (Rule 1): dli-aware real-corpus live-doc counts** — `8a68fc4` (fix) — `test_searchindex.py` + `test_dupaudit.py`.

Superseded checkpoint marker (pre-resume): `68ee80e` (docs — recorded the then-BLOCKED real-refresh gate; the blocker was subsequently resolved by `c6a0d65`/`e3c08f1`).

Task 2 steps 1/2/4 operate on **git-ignored** artifacts (`corpus/dli/`, `corpus/index.db`) and produce no source commit by design — they are proven by the live evidence and the now-running skip-guarded grounding test.

**Plan metadata:** _(final docs commit — this SUMMARY + STATE + ROADMAP + REQUIREMENTS)_

## Files Created/Modified

- `crawler/tests/test_dli_conformance.py` — created pre-checkpoint (`2459c4a`/`774dd94`); the phase-level offline conformance gate + skip-guarded live grounding. Unchanged this resume.
- `crawler/tests/test_searchindex.py` — **modified (deviation)**: `TestRealCorpus` docs count made dli-aware (`_expected_live_docs() = 742 + corpus/dli *.md count`).
- `crawler/tests/test_dupaudit.py` — **modified (deviation)**: `TestRealCorpus` `live_docs` count made dli-aware (same 742 + dli-delta), `exact == 0` preserved.
- `corpus/dli/*.md` + `manifest.json` — **generated, git-ignored** (real live refresh; 1,136 institutions).
- `corpus/index.db` — **generated, git-ignored** (rebuilt over the full corpus including the dli family).

## Blocker & Resolution (real-refresh gate)

- **Blocker (checkpoint):** Task 2 step 1's REQUIRED real refresh returned exit 2 (read timeout) because the upstream Akamai CDN deterministically blackholed the shipped verb's custom `User-Agent` over HTTP/1.1 from this environment (endpoint was UP; default-UA fetch returned HTTP 200). The verb failed closed correctly — no partial `corpus/dli/`, `corpus/index.db` untouched.
- **Resolution (pre-resume, 41-01 scope):** `c6a0d65` dropped the custom `_UA` (stdlib urllib's honest default identity is used — not identity evasion, no browser-spoofed UA) and removed `fetch`'s caller-overridable `url` (fixed-source SSRF hardening). `e3c08f1` recorded it and moved the deferred item BLOCKED → RESOLVED. On resume, the live refresh succeeds (exit 0), unblocking the whole closeout.

## Verification Evidence (all green)

- `pytest crawler/tests/test_dli_conformance.py -v` → **15 passed, 25 subtests** (incl. the 3 `TestLiveDliGroundingRealIndex` tests now RUNNING against the real dli-bearing index).
- `--json refresh-dli` → **exit 0**; `index corpus/ --db corpus/index.db` → 1,878 docs / 10,207 chunks.
- Whole-registry: `study.dli.designation` selected `dli/O19332746152.md#000`, agrees + grounds; `validate_registry` **0 violations**; resolved chunk `source_type='dli'`.
- `pytest crawler/tests -q` → **967 passed, 2 skipped, 0 failed** (18:38).
- `scripts/check_publish_safe.py` → **397 tracked files, 0 violations**.
- `scripts/run_conformance.py` → **PASS — SAFE-01..08** (75 passed), incl. `retrieve_what_you_cite` grounding `study.dli.designation` against the real index.
- `pytest scripts/tests -q` → **36 passed**.

## Decisions Made

- Treated the real refresh success as gating: the whole closeout (reindex, full suite, live grounding) ran ONLY after `refresh-dli` returned exit 0 — never a dli-less rebuild, never a green claim on a dli-less index.
- Rebuilt the REAL `corpus/index.db` (not a throwaway temp) so the shipped whole-registry v4.x conformance grounds `study.dli.designation` end-to-end.
- Fixed the stale hardcoded `742` real-corpus smoke counts dli-aware rather than deselecting the tests, keeping the full suite genuinely green with the git-ignored dli family present, and still exactly 742 in CI / a fresh clone.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] dli-aware `TestRealCorpus` live-doc counts**
- **Found during:** Task 2 step 4 (full suite) — 2 failures: `test_searchindex.py::TestRealCorpus::test_real_corpus_builds_742_docs_bounded_and_idempotent` (`1878 != 742`) and `test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts` (`1878 != 742`).
- **Issue:** Both smoke tests hardcoded the committed-corpus baseline of 742 live docs. Phase 41's REQUIRED real refresh writes the git-ignored `corpus/dli/` family (1,136 `.md`), so building/auditing the on-disk `corpus/` legitimately yields `742 + 1136 = 1878`. The plan mandates rebuilding the real dli-bearing index, so these hardcoded expectations became stale and broke the full-suite gate. Root cause is entirely the phase's dli family — a tightly-coupled Phase-41 defect. The production `searchindex`/`dupaudit` code is byte-for-byte frozen and correct (it indexes/audits the dli family as designed).
- **Fix:** Made the expected count dli-aware: `742 + (count of corpus/dli/*.md when corpus/dli exists else 0)`. Since `corpus/dli/` is git-ignored, CI / a fresh clone still sees exactly 742; a locally-refreshed tree sees 742 + the dli family. This is strictly MORE correct — not a weakening (idempotency, bounded chunks, `exact == 0` assertions all preserved).
- **Files modified:** `crawler/tests/test_searchindex.py`, `crawler/tests/test_dupaudit.py`
- **Verification:** Both tests rerun green (16:04); full suite → 967 passed / 2 skipped / 0 failed; frozen-contract test still passes (searchindex.py/dupaudit.py production code untouched).
- **Committed in:** `8a68fc4`

---

**Total deviations:** 1 auto-fixed (1 Rule-1 bug)
**Impact on plan:** Necessary to make the full-suite gate honestly green with the REQUIRED real dli-bearing corpus present. No production code changed; no scope creep. The two touched test files are outside the plan's declared `files_modified` (only `test_dli_conformance.py`) but are not in the frozen-contract list, so the frozen-contract assertion is unaffected.

## Issues Encountered

- The full crawler suite is slow (~18 min) because `dupaudit.audit` runs an O(n²) near-duplicate comparison over the now-1,878-doc corpus; this is expected behavior, not a regression. No action needed.

## User Setup Required

None — no external service configuration required. The real refresh runs against the fixed IRCC endpoint with the stdlib urllib default identity; the audit path performs no network lookup.

## Next Phase Readiness

- STUDY-01 is closed end-to-end: a refreshable, `crawl_date`/`content_sha256`-stamped, auto-indexed DLI/PGWP family grounded for citation with a structurally network-free audit path.
- Phase 44 (study decider) can now consume the grounded `study.dli.designation` row on its dedicated inert namespace (the credential-only `additional.study` decider + CRS grid remain byte-for-byte unchanged).
- Phase closeout stays in the orchestrator's Verifying state pending the phase verifier.

---
*Phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator*
*Completed: 2026-07-18*

## Self-Check: PASSED

- Files verified present: `41-04-SUMMARY.md`, `crawler/tests/test_dli_conformance.py`, `crawler/tests/test_searchindex.py`, `crawler/tests/test_dupaudit.py`.
- Commits verified in history: `2459c4a` (Task 1 conformance gate), `774dd94` (Task 2 live-grounding test), `8a68fc4` (Task 2 dli-aware count fix).
- Git-ignored real closeout artifacts present: `corpus/dli/manifest.json` + 1,136 `.md`, rebuilt `corpus/index.db` (2,272 dli chunks).
- Gates green: conformance 15/15 (incl. live grounding), full suite 967 passed / 2 skipped / 0 failed, publish-safe 0 violations, v4.x conformance PASS (SAFE-01..08), scripts tests 36 passed.
