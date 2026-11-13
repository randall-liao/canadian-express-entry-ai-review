---
phase: 33-full-modular-crs-auditor-pack
plan: 06
subsystem: testing
tags: [crs, integration, pii-perimeter, conformance, cutoff]

requires:
  - phase: 33-full-modular-crs-auditor-pack
    provides: dispatch spine + four modules + completed conversion tables + run_full_audit_report
provides:
  - full-grid integration tests (SC1/SC4/SC5 + language-green end-to-end)
  - full-grid PII-perimeter test + local auditor conformance fixtures
affects: [34-safety-conformance]

tech-stack:
  added: []
  patterns:
    - "goal-backward verification over the REAL registry + real corpus + synthetic vault"

key-files:
  created:
    - crawler/tests/test_full_audit_integration.py
    - crawler/tests/test_full_audit_pii_perimeter.py
    - crawler/eval/crs_auditors.jsonl
  modified:
    - crawler/crs_audit.py (score_factor owning-factor fix)
    - crawler/auditors/core.py (_grounded_points owning-factor fix)
    - crawler/auditor.py (auto-select latest ITA round for --all cutoff)

key-decisions:
  - "integration tests use the REAL registry against corpus/index.db so conversion rows ground and language reaches SUBSTANTIATED"

patterns-established:
  - "one card per grid factor asserted structurally (count == FULL_GRID_FACTORS, no dupes)"

requirements-completed: [AUDIT-01, AUDIT-04, AUDIT-05]

duration: ~50min
completed: 2026-07-06
---

# Phase 33 Plan 06: Full-Grid Integration & Conformance Summary

**Proved the whole phase goal end-to-end: a full claimed profile audits through the four modules over the real registry/corpus, every grid factor gets exactly one verdict, language reaches SUBSTANTIATED, the substantiated total is compared to the ITA cutoff without legal advice, SC5 conflicts surface at the factor level, and the full-grid public envelope leaks no PII.**

## Accomplishments
- Full-grid integration tests: SC1 (one verdict per factor, no dupes), AUDIT-04 (six populated card fields on a SUBSTANTIATED card), SC4 (substantiated-total-vs-cutoff, no legal-advice wording), SC5 (work-aggregation GAP with no overlap double-count, transferability unmet-component GAP, spouse ownership GAP), and language SUBSTANTIATED end-to-end.
- Full-grid PII-perimeter test drives `vault audit --all` through the CLI: no applicant value / no `ev_` id on stdout, vault-relative private path, report vault-only + publish-safe covered, `resolve_within` refuses escapes.
- Added `crawler/eval/crs_auditors.jsonl` — PII-free synthetic conformance fixtures for all four modules.

## Task Commits
1. **Task 1: Full-grid integration tests + score_factor fix** — `370c2b2` (test)
2. **Task 2: Full-grid PII perimeter + conformance fixtures** — `73a9d5f` (test)
3. **--all cutoff auto-round** — `d0a9c27` (fix)

## Files Created/Modified
- `crawler/tests/test_full_audit_integration.py` — SC1/SC4/SC5 + language-green.
- `crawler/tests/test_full_audit_pii_perimeter.py` — AUDIT-06 boundary + fixtures test.
- `crawler/eval/crs_auditors.jsonl` — conformance fixtures.
- `crawler/crs_audit.py`, `crawler/auditors/core.py` — owning-factor scoring fix.
- `crawler/auditor.py` — auto-select latest ITA round for the `--all` cutoff.

## Decisions Made
- Integration tests run against the REAL registry + `corpus/index.db` so the conversion rows ground and language reaches SUBSTANTIATED; edge cases (work overlap, spouse ownership, transferability dependency) are exercised in the same real-registry run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] score_factor / _grounded_points over-matched component factor ids**
- **Found during:** Task 1 (full-grid probe)
- **Issue:** `score_factor("core.language.first", ...)` matched any row whose `factor_ids` included the factor, so a transferability tier (which lists `core.language.first` as a *component*) leaked a CLB-9 → 50 tier into the language score (language read 200 instead of 124). Latent because Phase-32/33 unit tests used synthetic registries without transferability rows tagging core factors.
- **Fix:** Match the OWNING factor (`factor_ids[0]`) in both `crs_audit.score_factor` and `core._grounded_points`. All prior tests stay green.
- **Files modified:** `crawler/crs_audit.py`, `crawler/auditors/core.py`
- **Committed in:** `370c2b2`

**2. [Rule 2 - Missing functionality] `--all` cutoff needs an ITA round**
- **Found during:** end-to-end `vault audit --all` verification
- **Issue:** `vault audit --all` without an explicit `--round` did not surface the substantiated-total-vs-cutoff comparison (AUDIT-05), because `run_full_audit` had no ITA round to compare against.
- **Fix:** `run_full_audit` auto-selects the most recent ITA round when none is specified; explicit `ita_round_id` still wins.
- **Files modified:** `crawler/auditor.py`
- **Committed in:** `d0a9c27`

---

**Total deviations:** 2 auto-fixed (1× Rule 1, 1× Rule 2)
**Impact on plan:** Rule 1 corrects a real scoring error surfaced only at grid scale; Rule 2 makes the AUDIT-05 deliverable usable. No scope creep.

## Issues Encountered
None beyond the deviations above.

## Next Phase Readiness
The full modular auditor pack is complete and green (623 passed, publish-safe 0). Phase 34 (safety conformance & release framing) can build on it.

---
*Phase: 33-full-modular-crs-auditor-pack*
*Completed: 2026-07-06*

## Self-Check: PASSED

All listed files exist on disk and all task commit hashes are present in git history.
