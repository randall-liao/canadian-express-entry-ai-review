---
phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
plan: 04
subsystem: eligibility-screening
tags: [mec, cli, atomic-publication, privacy, conformance, fsync]

requires:
  - phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec
    plan: 03
    provides: Grounded FSW/FST/CEC evaluators and deterministic in-memory MEC bundle
provides:
  - Exact preflight-first `vault screen-mec --program fsw|fst|cec` command
  - Recoverable scan-stage-backup-replace-fsync private MEC LKG publication
  - Citation-free PII-light public MEC result inside the unchanged five-key envelope
  - Exhaustive MEC no-false-MEETS, privacy, freshness, freeze, dependency, and network conformance
affects: [46-safe-v5-conformance-release-gate, mec-release, eligibility-screening]

tech-stack:
  added: []
  patterns: [scan before filesystem mutation, recoverable two-file LKG transaction, one immutable registry snapshot, FAIL-first exhaustive conformance]

key-files:
  created:
    - crawler/mec_publish.py
    - crawler/tests/test_mec_cli.py
    - crawler/tests/test_conformance_v5_mec_no_false_meets.py
  modified:
    - crawler/cli.py
    - crawler/mec_screen.py
    - crawler/tests/test_crs_no_inlined_rules.py
    - crawler/tests/test_conformance_v5_study_no_false_green.py

key-decisions:
  - "FSW consumes and preflights DLI freshness only when optional study composition is configured; FST and CEC never resolve that sidecar setting."
  - "The command-owned public MEC projection carries no corpus citations, evidence identifiers, raw values, dates, amounts, NOC values, employer data, or absolute paths."
  - "Rollback retains or reconstructs prior bytes through every stage, replace, and directory-fsync failure; ambiguous restoration keeps the backup."

patterns-established:
  - "MEC publication validates and scans all private/public bytes before mkdir, stages and file-fsyncs both private formats, then backs up, replaces, directory-fsyncs, removes backups, and fsyncs again."
  - "The CLI emits `_vault_ok` only after `publish_mec_bundle` returns from a durable private commit."

requirements-completed: [MEC-01, MEC-02, MEC-03, MEC-04]

duration: 44min
completed: 2026-07-20
---

# Phase 45 Plan 04: MEC CLI and Conformance Summary

**Exact `vault screen-mec` with one freshness-bound registry snapshot, recoverable private LKG publication, citation-free public output, and exhaustive no-false-MEETS conformance**

## Performance

- **Duration:** 44 min
- **Started:** 2026-07-20T04:26:48Z
- **Completed:** 2026-07-20T05:10:36Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added only the exact `vault screen-mec --program fsw|fst|cec` spelling with required MEC rule freshness resolution before registry, index, vault, database, evaluation, or write access.
- Preserved one `RegistrySnapshot` object/fingerprint and one unchanged rule age through gate preparation, evidence loading, sidecar composition, evaluation, private report, and public summary.
- Added private JSON/Markdown render validation and closed private/public scans before any directory creation, followed by staged file fsync, LKG backups, atomic replacement, durable directory fsync, cleanup, and rollback.
- Proved deterministic FAIL precedence and exhaustive demotion across missing, unconfirmed, low-quality, ambiguous, stale, superseded, out-of-window, malformed, unwired, unknown, invalid-N/A, sidecar-risk, funds-without-snapshot, and no-snapshot states.
- Froze `PublicAuditEnvelope`, CRS grid/cards/totals/cutoff sources, dependencies, lockfile, network behavior, and Phase-46 release-gate ownership.

## Task Commits

Each TDD task was committed atomically with RED before GREEN:

1. **Task 45-04-01 RED: CLI and publication failure tests** - `1a54b9f` (test)
2. **Task 45-04-01 GREEN: exact command and recoverable publisher** - `1f6a9a1` (feat)
3. **Task 45-04-02 RED: exhaustive MEC conformance** - `ab9038b` (test)
4. **Task 45-04-02 GREEN: complete MEC scanner enrollment** - `6b16cbc` (test)
5. **Frozen-source conformance correction** - `d7b3ed0` (test)

## Files Created/Modified

- `crawler/mec_publish.py` - Closed render/scan and recoverable two-file private publication transaction.
- `crawler/mec_screen.py` - Citation-free public command projection while retaining citations in the private report.
- `crawler/cli.py` - Exact MEC parser, preflight ordering, one-snapshot handoff, safe failure routing, and post-durability success emission.
- `crawler/tests/test_mec_cli.py` - Parser, ordering, identity, privacy, publication, and injected rollback seam coverage.
- `crawler/tests/test_conformance_v5_mec_no_false_meets.py` - Exhaustive outcome, freshness, evidence, funds, period, privacy, freeze, dependency, loader, and network controls.
- `crawler/tests/test_crs_no_inlined_rules.py` - Named complete MEC production scanner surface.
- `crawler/tests/test_conformance_v5_study_no_false_green.py` - Re-approved Phase-45-owned registry, study injection, and CLI source hashes.

## Decisions Made

- Optional DLI composition remains separately configured: no MEC rule age is reused as a DLI snapshot bound.
- No standalone public artifact is written; `PublicMecSummary` exists only in memory and in the successful five-key stdout envelope.
- Public MEC criteria keep their closed schema but expose empty citation lists; grounded citations remain available only in the vault-private report.
- Existing confirmed MEC/CRS adapters were not expanded or duplicated; empty confirmed non-MEC inputs conservatively produce `AT-RISK`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved untouched LKG files on early stage failure**
- **Found during:** Task 45-04-01 GREEN failure-injection verification
- **Issue:** The first rollback draft captured old bytes after staging, so a first/second-stage failure could misclassify untouched latest files as new output.
- **Fix:** Captured both prior payloads before staging and appended staged paths incrementally so every created temp is tracked.
- **Files modified:** `crawler/mec_publish.py`
- **Verification:** Every render, scanner, stage, replace, and both directory-fsync injections preserves exact prior bytes and leaves only `latest.json`/`latest.md`.
- **Committed in:** `1f6a9a1`

**2. [Rule 2 - Missing Critical] Removed public corpus citations at the command projection**
- **Found during:** Task 45-04-01 privacy-boundary implementation
- **Issue:** The inherited in-memory projection could retain corpus coordinates even though the authoritative command contract requires public output with no citations or raw/private values.
- **Fix:** Kept citations in `PrivateMecReport`, emitted empty citation lists publicly, and made the public scanner reject any non-empty citation.
- **Files modified:** `crawler/mec_screen.py`, `crawler/mec_publish.py`
- **Verification:** CLI envelope and hostile-value conformance contain no citation, evidence, applicant, NOC value, date, amount, employer, secret, or absolute path.
- **Committed in:** `1f6a9a1`

**3. [Rule 3 - Blocking] Advanced stale Phase-45 frozen-source approvals**
- **Found during:** Overall prior-sidecar conformance verification
- **Issue:** The study conformance SHA map still pinned pre-Phase-45 bytes for the intentionally injected study seam, grounded MEC registry scanner, and newly additive CLI.
- **Fix:** Re-approved only those three Phase-45-owned source hashes after dedicated no-network/no-loader/frozen-surface conformance passed.
- **Files modified:** `crawler/tests/test_conformance_v5_study_no_false_green.py`
- **Verification:** The full prior v5 sidecar conformance and complete crawler suite pass.
- **Committed in:** `d7b3ed0`

---

**Total deviations:** 3 auto-fixed (1 bug, 1 missing critical privacy control, 1 blocking conformance correction)
**Impact on plan:** All fixes directly enforce publication recoverability, the requested public privacy boundary, and Phase-45 freeze verification; no dependency, schema, CRS, release-gate, or cache scope changed.

## Issues Encountered

- The complete crawler suite is CPU-intensive and required approximately 30 minutes; it completed successfully with 1327 passed, 2 skipped, and 1983 subtests passed.

## Verification

- Phase-45 MEC target suite: 89 passed, 786 subtests passed.
- Plan target suite: 42 passed, 687 subtests passed.
- Full crawler suite: 1327 passed, 2 skipped, 1983 subtests passed.
- `scripts/check_publish_safe.py`: 465 tracked files scanned, 0 violations.
- Frozen `pyproject.toml`, `poetry.lock`, `PublicAuditEnvelope`, CRS sources, policy sidecar, and `scripts/run_conformance.py` diff: clean.
- `.planning/research/.cache/`: untouched and remains untracked.

## Known Stubs

None.

## User Setup Required

None - no dependencies or external services were added. Operators must provide the required positive `--rule-max-age-days` or `PR_MEC_RULE_MAX_AGE_DAYS`.

## Next Phase Readiness

- MEC-01 through MEC-04 are complete and Phase 45 is ready for verification.
- Phase 46 can own SAFE-11/SAFE-12 and the v5 release-gate command without changing MEC, CRS, dependencies, or the public audit envelope.

## Self-Check: PASSED

All created implementation/test files, the summary, and all five Plan 45-04 task/correction commits were verified on disk.

---
*Phase: 45-mec-program-eligibility-sidecar-fsw-fst-cec*
*Completed: 2026-07-20*
