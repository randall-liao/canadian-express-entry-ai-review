---
phase: 44-canadian-study-dli-pgwp-evidence-gate
fixed_at: 2026-07-19T20:58:14-04:00
review_path: .planning/phases/44-canadian-study-dli-pgwp-evidence-gate/44-REVIEW.md
iteration: 9
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
phase_status: verifying
cumulative_fixed: 27
---

# Phase 44: Code Review Fix Report

**Fixed at:** 2026-07-19T20:58:14-04:00
**Source review:** `.planning/phases/44-canadian-study-dli-pgwp-evidence-gate/44-REVIEW.md`
**Iteration:** 9

**Iteration-9 summary:**
- Findings in scope: 1
- Fixed: 1
- Skipped: 0
- Phase remains **Verifying** for verifier sign-off.

## Iteration 9 — Fixed Issues

### CR-01: Study report invalidation and publication are not crash-durable

**Files modified:** `crawler/paths.py`, `crawler/audit_report.py`,
`crawler/study_review.py`, `crawler/cli.py`, `crawler/tests/test_audit_report.py`,
`crawler/tests/test_study_review.py`, `crawler/tests/test_study_review_cli.py`,
`crawler/tests/test_conformance_v5_study_no_false_green.py`
**Commit:** `8e32c88`
**Status:** fixed: requires human verification

**Applied fix:** Directory fsync and durable recursive creation now live in the
stdlib-only `crawler.paths` layer and are shared by audit and study report
publication. Each study-review invalidation durably syncs the report directory
before any evidence work; failures return stable path-free lifecycle refusals.
Successful publication fsyncs and closes the staged file, atomically replaces
`latest.json`, and fsyncs its directory before setting `report_created`. A
post-replace sync failure removes the new target, syncs the cleanup, and never
advertises a report; stale evidence is not restored. Failure-injection and ordering
regressions cover mkdir, unlink, file/directory fsync, replace, cleanup, CLI
advertising, path privacy, and the intentionally refreshed source pins.

## Iteration 9 — Verification

- Focused study/audit-report/CLI/v5 conformance slice:
  **111 passed, 195 subtests passed**.
- Full crawler suite:
  **1065 passed, 170 skipped, 362 subtests passed**.
- Full marked conformance:
  **76 passed, 48 skipped, 80 subtests passed**.
- SAFE-01 through SAFE-08:
  **59 passed, 23 skipped**.
- Publish-safe: **446 tracked files scanned, 0 violations**.
- Python compilation, independent fifteen-source freeze verification, and
  `git diff --check`: passed.
- `pyproject.toml`, `poetry.lock`, Phase 45, restricted-add/trailer surfaces,
  and production corpus/cache artifacts were not modified.

## Iteration 8 — Fixed Issues

### CR-01: Control-flow exceptions leak private details at the real CLI boundary

**Files modified:** `crawler/cli.py`, `crawler/tests/test_cli.py`,
`crawler/tests/test_conformance_v5_study_no_false_green.py`, `pyproject.toml`
**Commit:** `c2702ca`
**Status:** fixed: requires human verification

**Applied fix:** The installed console script now targets a dedicated `entrypoint`
wrapper while `main(argv)` retains its programmatic behavior. The wrapper maps
interrupt and generator control flow to stable numeric exits, preserves only integer
or `None` `SystemExit` codes, and discards string/object payloads without output.
Installed-style subprocess regressions cover private path/evidence payloads, numeric
codes, and a normal help command. The reviewed `pyproject.toml` bytes are pinned
independently; runtime dependencies and `poetry.lock` are unchanged.

### CR-02: Database rows can outlive report files after a crash

**Files modified:** `crawler/audit_report.py`,
`crawler/tests/test_audit_report.py`
**Commit:** `87d3bca`
**Status:** fixed: requires human verification

**Applied fix:** Report publication now durably creates missing path components,
fsyncs both staged file contents, atomically replaces JSON and Markdown, fsyncs the
report directory, and only then commits SQLite. Unsupported directory fsync fails
closed before commit with a stable path-free persistence error. Collision restoration
and backup/temp cleanup receive best-effort directory syncs, and the recovery
documentation explicitly avoids claiming global two-file-plus-database atomicity.
Regressions prove both replacements precede directory sync and commit, parent
directories are synced, descriptors close, and fsync failure restores files and rows
without leaking private paths.

### WR-01: Phase 44 fingerprint binding broke a corpus-enabled conformance gate

**Files modified:**
`crawler/tests/test_conformance_v5_noc_no_auto_green.py`
**Commit:** `2a53bf0`
**Status:** fixed

**Applied fix:** The NOC isolation fixture now constructs one synthetic work registry
and fingerprint per setup, binds every synthetic confirmation to that fingerprint,
and passes the same pair to factor and full-grid audits. The hermetic
`SUBSTANTIATED` baseline and structural grid exclusion run without the local corpus;
only genuinely corpus-backed NOC scenarios remain skip-guarded.

## Iteration 8 — Verification

- Focused entrypoint/audit-report/NOC gates:
  **50 passed, 6 skipped, 20 subtests passed**.
- Full crawler suite:
  **1055 passed, 170 skipped, 356 subtests passed**.
- Full marked conformance:
  **76 passed, 48 skipped, 1101 deselected, 80 subtests passed**.
- v4 safety conformance runner:
  **59 passed, 23 skipped**; SAFE-01 through SAFE-08 passed.
- Publish-safe: **446 tracked files scanned, 0 violations**.
- Python compile checks and `git diff --check`: passed.
- No dependency or lock changes were made. Restricted adds/trailers and
  production/research caches were untouched.

**Iteration-7 summary:**
- Findings in scope: 2
- Fixed: 2
- Skipped: 0
- Phase remains **Verifying** for verifier sign-off.

## Iteration 7 — Fixed Issues

### CR-01: An exception after a successful commit deletes the committed report files

**Files modified:** `crawler/audit_report.py`,
`crawler/tests/test_audit_report.py`
**Commit:** `7738d12`
**Status:** fixed: requires human verification

**Applied fix:** Post-commit exception handling now confirms durability only when
the connection is out of transaction and a parameter-bound run-id query matches
the completed status, registry fingerprint, report path, completion timestamp,
and exact verdict count. A confirmed commit keeps both published reports, removes
only backups/temps, returns normally for ordinary exceptions, and re-raises
control-flow exceptions after preserving state. Failed commits still roll back and
restore collisions. An unavailable confirmation query fails closed while retaining
published files and recovery backups rather than risking deletion of committed
report targets.

### CR-02: Re-raised persistence BaseExceptions leak private paths in JSON

**Files modified:** `crawler/cli.py`, `crawler/tests/test_cli.py`,
`crawler/tests/test_json_contract.py`, `crawler/tests/test_vault_audit_cli.py`
**Commits:** `b42a43f`, `87c439f`
**Status:** fixed: requires human verification

**Applied fix:** JSON dispatch now explicitly re-raises `SystemExit`,
`KeyboardInterrupt`, and `GeneratorExit`. Its ordinary unexpected-exception
boundary emits only the stable `unexpected internal error` envelope and the same
generic stderr diagnostic, never raw exception text or a traceback. Regressions
cover argparse behavior, every control-flow exception, a path-bearing global
`RuntimeError`, and a path-bearing post-commit audit interrupt that emits no JSON
while preserving the completed row, verdict, and both reports.

## Iteration 7 — Verification

- Focused persistence/CLI/contract/study gates:
  **108 passed, 38 skipped, 125 subtests passed**.
- Full crawler suite:
  **1045 passed, 171 skipped, 350 subtests passed**.
- Full marked conformance:
  **74 passed, 49 skipped, 1093 deselected, 80 subtests passed**.
- v4 safety conformance runner:
  **59 passed, 23 skipped**; SAFE-01 through SAFE-08 passed.
- Publish-safe: **446 tracked files scanned, 0 violations**.
- Python compile-all and `git diff --check`: passed.
- Skips remain local-only corpus/extraction gates. No dependency, restricted-add,
  trailer, production-cache, or Phase 45 changes were made.

**Iteration-6 summary:**
- Findings in scope: 2
- Fixed: 2
- Skipped: 0
- Phase remains **Verifying** for verifier sign-off.

## Iteration 6 — Fixed Issues

### CR-01: Unexpected persistence exceptions bypass both cleanup and privacy normalization

**Files modified:** `crawler/audit_report.py`,
`crawler/tests/test_audit_report.py`, `crawler/tests/test_vault_audit_cli.py`
**Commit:** `7f37b79`
**Status:** fixed: requires human verification

**Applied fix:** `_persist_report` now tracks its owned transaction, staged and
published files, and collision backups across the complete `BaseException`
surface. Every failure performs best-effort rollback and file restoration without
allowing cleanup errors to mask the original. Ordinary exceptions become the
stable path-free `AuditPersistenceError`; interrupt-like base exceptions are
cleaned up and re-raised unchanged. Runtime failure injection covers output
creation/staging/replacement, audit-run/verdict/completion inserts, and commit,
while proving clean transactions, unchanged rows/files, and path-free CLI JSON.

### WR-01: A nonexistent explicit round is accepted as effective provenance

**Files modified:** `crawler/auditor.py`, `crawler/audit_report.py`,
`crawler/tests/test_full_audit_cutoff.py`, `crawler/tests/test_audit_report.py`,
`crawler/tests/test_vault_audit_cli.py`
**Commit:** `d35641b`
**Status:** fixed: requires human verification

**Applied fix:** Explicit ITA round IDs are now resolved by parameter-bound,
candidate-scoped queries before factor evaluation or report staging. Latest-round,
date, and cutoff lookups are candidate-scoped and deterministic, and the single
validated ID is threaded through audit, cutoff, artifacts, and persistence.
Missing and other-candidate IDs raise one stable PII-free
`AuditGroundingError`; direct and persisting APIs agree, and the CLI returns the
existing nonzero `invalid_input` envelope rather than a persistence error.

## Iteration 6 — Verification

- Focused report/full-audit/CLI gates:
  **43 passed, 13 subtests passed**.
- Full crawler suite:
  **1037 passed, 171 skipped, 347 subtests passed**.
- v4 safety conformance runner:
  **59 passed, 23 skipped**; SAFE-01 through SAFE-08 passed.
- Publish-safe: **446 tracked files scanned, 0 violations**.
- Python syntax checks and `git diff --check`: passed.
- Skips remain local-only corpus/extraction gates. No dependency, Phase 45,
  restricted-add, trailer, or production-cache changes were made.

**Iteration-5 summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0
- Phase remains **Verifying** for verifier sign-off.

## Iteration 5 — Fixed Issues

### CR-01: Report I/O failures leak private vault paths through JSON stdout

**Files modified:** `crawler/audit_report.py`, `crawler/cli.py`,
`crawler/tests/test_audit_report.py`, `crawler/tests/test_vault_audit_cli.py`
**Commit:** `1004a36`
**Status:** fixed

**Applied fix:** Added the stable, path-free `AuditPersistenceError` boundary.
Expected filesystem and SQLite persistence failures are normalized only after
rollback and best-effort cleanup. `vault audit` catches the dedicated error and
returns a generic `internal_error` without passing raw I/O to the global handler.
Failure injection covers directory creation, temp creation/write/cleanup, replace,
SQLite mutation, and commit while proving prior reports and completed rows remain
intact and public JSON contains no absolute path or evidence identifier.

### CR-02: A nested audit transaction rolls back unrelated caller data

**Files modified:** `crawler/audit_report.py`, `crawler/tests/test_audit_report.py`
**Commit:** `194b33e`
**Status:** fixed: requires human verification

**Applied fix:** `_persist_report` now rejects an existing caller transaction before
staging or mutation. It records ownership only after a successful `BEGIN` and
rolls back only its own transaction. The regression leaves an unrelated
uncommitted update visible and the connection in-transaction after refusal, writes
no report or audit rows, and confirms the caller can roll back itself; normal
no-active-transaction persistence remains covered.

### WR-01: Implicit latest-round audits persist no round provenance

**Files modified:** `crawler/auditor.py`, `crawler/audit_report.py`,
`crawler/remediation.py`, `crawler/tests/test_full_audit_cutoff.py`,
`crawler/tests/test_vault_audit_cli.py`,
`crawler/tests/test_conformance_v41_coverage.py`,
`crawler/tests/test_adversarial_extraction_seam.py`,
`crawler/tests/test_example_profile_pinned.py`
**Commit:** `cfc2dff`
**Status:** fixed: requires human verification

**Applied fix:** Persisting full-grid audits resolve one canonical effective ITA
round before grid computation and pass that exact ID through cutoff/freshness,
the returned private report, JSON/Markdown artifacts, and `audit_runs`. Explicit
IDs bypass latest selection unchanged; a missing implicit round fails closed
before artifacts. Tests prove latest selection occurs once and every provenance
surface agrees with the round that produced the cutoff delta.

### WR-02: The Phase 44 source-freeze conformance gate is stale

**Files modified:**
`crawler/tests/test_conformance_v5_study_no_false_green.py`
**Commit:** `4a6a9be`
**Status:** fixed

**Applied fix:** Verified `crawler/crs_rules.py` exactly matches the reviewed
iteration-fix bytes (`a585c99d…`) and updated only its independent SHA-256 pin.
The provenance comment names the Phase 44 final deep-review iteration fix; an
independent map check confirms all eleven frozen source hashes match with no
other pin drift.

## Iteration 5 — Verification

- Focused report/CLI/auditor/study/freeze gates:
  **127 passed, 56 skipped, 123 subtests passed**.
- Full crawler suite:
  **1030 passed, 171 skipped, 336 subtests passed**.
- v4 safety conformance runner:
  **59 passed, 23 skipped**; SAFE-01 through SAFE-08 passed.
- Publish-safe: **446 tracked files scanned, 0 violations**.
- Python syntax checks, independent eleven-source freeze verification, and
  `git diff --check`: passed.
- Skips are local-only real-corpus/extraction gates unavailable in the isolated
  worktree; their structural gates ran. No dependency, Phase 45, restricted-add,
  trailer, or production cache changes were made.

## Iteration 4 — Fixed Issues

### CR-01: Mandatory auxiliary rows could be unusable gaps

**Files modified:** `crawler/crs_rules.py`, `crawler/tests/test_crs_rules.py`
**Commit:** `4e91e62`
**Status:** fixed: requires human verification

**Applied fix:** `load_registry_snapshot` now requires every load-bearing auxiliary
row to exist, be non-gap, and retain usable citations and a machine check. Tests
copy the real registry, mark each required auxiliary row `gap:true` in turn, and
assert the stable `RegistryUnavailable` refusal; the real registry still loads and
fingerprints successfully.

### CR-02: Direct audit APIs could split Registry content from the evidence fingerprint

**Files modified:** `crawler/auditor.py`, `crawler/audit_report.py`,
`crawler/tests/test_auditor.py`, `crawler/tests/test_auditor_dispatch.py`,
`crawler/tests/test_auditors_spouse.py`, `crawler/tests/test_audit_report.py`
**Commit:** `31b008e`
**Status:** fixed: requires human verification

**Applied fix:** Every public audit entry verifies the fingerprint of the supplied
in-memory `Registry` before reading evidence or writing artifacts. An explicit
mismatch raises the stable fail-closed `AuditGroundingError`; verified internal
entry points prevent nested recomputation. The one verified fingerprint is threaded
through every eligibility read and report metadata, with no live-registry fallback.
Synthetic confirmations now bind through an explicit synthetic fingerprint seam.
Regressions cover explicit mismatch/zero artifacts, evidence bound to registry A
being excluded under registry B, one fingerprint across a full-grid batch, report
metadata, and the CLI's one-loader-call contract.

### WR-01: Audit report files and database rows were persisted piecemeal

**Files modified:** `crawler/audit_report.py`, `crawler/vault.py`,
`crawler/tests/test_audit_report.py`
**Commit:** `aeed1cd`
**Status:** fixed: requires human verification

**Applied fix:** JSON and Markdown are fully written and fsynced to unique sibling
temp files before persistence begins. One SQLite transaction inserts the run, every
verdict, and completed status through transaction-aware internal helpers. Immutable
run-id files are atomically replaced before commit; any exception rolls back the
database, removes newly published files and temps, and preserves prior reports.
Failure injection covers JSON staging, Markdown staging, second replace, verdict
insert, and transaction commit.

## Iteration 4 — Verification

- Focused auditor/vault/report/study slice:
  **135 passed, 37 skipped, 119 subtests passed**.
- Full crawler suite:
  **1021 passed, 171 skipped, 336 subtests passed**.
- Conformance marker gate:
  **74 passed, 49 skipped, 1069 deselected, 80 subtests passed**.
- Publish-safe: **446 tracked files scanned, 0 violations**.
- `pyproject.toml`, `poetry.lock`, Phase 45, corpus/cache artifacts, and planning
  status were not modified. Restricted path staging was used; history was not
  rewritten.

## Iteration 3 — Previously Fixed Issues

**Iteration-3 summary:**
- Findings in scope: 3
- Fixed: 3
- Skipped: 0
- Phase remains **Verifying** for verifier sign-off.

### CR-01: RegistrySnapshot accepted malformed files and omitted required auxiliary rows

**Files modified:** `crawler/crs_rules.py`, `crawler/tests/test_crs_rules.py`,
`crawler/tests/test_conformance_v5_study_no_false_green.py`
**Commits:** `679e795`, `b7ee2a8`
**Status:** fixed: requires human verification

**Applied fix:** The validated snapshot loader now enumerates and strictly parses
every non-underscore YAML file, rejects missing/empty directories and every
invalid `rows` shape with one stable path-free error, and requires both complete
structural grid coverage and the canonical auxiliary manifest
`study.dli.designation`/`study.r73_definition`. Low-level synthetic compatibility
remains unchanged. Regression coverage includes malformed, null, empty,
wrong-type, I/O, missing-file, missing-row, incomplete-grid, duplicate, and real
registry cases.

### CR-02: Vault audit mixed rule rows and evidence eligibility snapshots

**Files modified:** `crawler/cli.py`, `crawler/auditor.py`,
`crawler/audit_report.py`, `crawler/vault.py`,
`crawler/tests/test_vault_audit_cli.py`, `crawler/tests/test_extract_confirm_cli.py`,
`crawler/tests/test_extraction_store.py`,
`crawler/tests/test_conformance_v40_privacy_containment.py`
**Commits:** `1fdfa40`, `1e59c67`
**Status:** fixed: requires human verification

**Applied fix:** `vault audit` now loads one validated registry snapshot before
opening the vault and threads its exact registry and fingerprint through single
and full-grid reports, every factor audit, confirmation staleness, evidence
eligibility, and persisted audit metadata. Optional fingerprint parameters keep
standalone callers compatible without a mutable cache. Tests prove one loader
call, no vault/output on missing or empty registries, no split after live
registry mutation, one full-grid fingerprint, and exclusion of confirmations
bound to another fingerprint.

### WR-01: Provenance-date conformance patched a dead resolver seam

**Files modified:**
`crawler/tests/test_conformance_v5_study_no_false_green.py`
**Commit:** `86b93fc`
**Status:** fixed

**Applied fix:** Replaced the obsolete resolver mock with independent copied
SQLite metadata mutations. The matrix verifies the canonical row helper sees
stale, future, missing, and mismatched common dates and asserts provenance
refusal occurs before the grounding gate or report creation.

## Iteration 3 — Verification

- Focused registry/vault/auditor/study slices:
  **137 passed, 199 subtests passed**.
- Independent real-index provenance-date matrix:
  **1 passed, 6 subtests passed**.
- Full crawler suite:
  **1180 passed, 2 skipped, 1087 subtests passed**.
- Conformance marker gate:
  **123 passed, 321 subtests passed**.
- Publish-safe: **446 tracked files scanned, 0 violations**.
- Python compile-all and `git diff --check`: passed.
- No dependencies, schema migration, Phase 45 work, production cache writes, or
  history rewrite. Restricted path staging and required co-author trailers were
  used.

## Iteration 2 — Previously Fixed Issues

### CR-01: Manifest validation did not bind accepted index chunks to canonical source bytes

**Files modified:** `crawler/searchindex.py`, `crawler/study_review.py`
**Commit:** `cc1ce6d`
**Status:** fixed: requires human verification

**Applied fix:** Added one read-only canonical document-row projection and made
`build_index` consume it. Study review now reads every candidate relpath row and
compares the complete ordered canonical projection: IDs, ordinals, sections,
exact text and hash, URL, title, crawl date, source type, and relpath. Any extra,
missing, reordered, or replaced row refuses with
`snapshot_provenance_mismatch` before dynamic rows, grounding, or report creation.

### CR-02: Registry-unavailable paths could remain eligible or crash review

**Files modified:** `crawler/crs_rules.py`, `crawler/vault.py`,
`crawler/confirm.py`, `crawler/cli.py`, `crawler/study_review.py`,
`crawler/tests/test_crs_rules.py`, `crawler/tests/test_extract_confirm_cli.py`,
`crawler/tests/test_study_review.py`, `crawler/tests/test_vault_audit_cli.py`
**Commits:** `a18b161`, `d52de29`
**Status:** fixed: requires human verification

**Applied fix:** Introduced `RegistrySnapshot` and the stable, path-free
`RegistryUnavailable` failure. The loader rejects missing, empty, malformed,
model-invalid, duplicate, and incomplete registries, then fingerprints the same
validated in-memory model. Confirmation, field views, staleness/eligibility, and
study review share one snapshot per command/review. Study review loads it once
before candidate reads; confirmation fails before opening a vault. Explicit
snapshot/fingerprint seams preserve hermetic synthetic-registry tests.

### WR-01: The adversarial matrix asserted forged candidate evidence was valid

**Files modified:**
`crawler/tests/test_conformance_v5_study_no_false_green.py`
**Commits:** `f19bcf4`, `50d0d9f`
**Status:** fixed

**Applied fix:** Changed the unmanifested extra-row case to require provenance
refusal and no report. Added an always-run, independently asserted three-chunk
fixture built by `build_index`; the legitimate fixture passes, while extra,
intermediate/trailing missing, reordered ID/ordinal, rehashed replacement text,
section, title, source-type, crawl-date, and source-URL mutations independently
refuse before the shared gate. Reviewed source freeze pins were updated.

## Iteration 2 — Verification

- Focused Phase 44/index/registry/vault/CLI/conformance slices:
  **128 passed, 35 skipped, 114 subtests passed**.
- Vault and auditor slice: **39 passed, 6 skipped**.
- Independent canonical membership matrix:
  **1 passed, 10 subtests passed**.
- Full crawler suite:
  **1005 passed, 171 skipped, 323 subtests passed**.
- Conformance marker gate:
  **74 passed, 49 skipped, 80 subtests passed**.
- Publish-safe: **446 tracked files scanned, 0 violations**.
- Python syntax checks and `git diff --check`: passed.
- No dependencies, schema migration, Phase 45 work, production cache writes, or
  history rewrite. Restricted path staging and required co-author trailers were
  used.

## Iteration 1 — Previously Fixed

| Finding | Commits | Result |
|---|---|---|
| CR-01 candidate freshness/provenance | `257fd79` | Candidate date and manifest lineage bound before reporting |
| CR-02 arbitrary corrected JSON type | `0c46620` | Non-string DLI corrections fail closed |
| CR-03 stale `latest.json` lifecycle | `3193c65` | Pre-invalidation and atomic report replacement |
| CR-04 live registry fingerprint | `238a801`, `ea047a5` | Confirmations bound to live registry content |
| WR-01 independent freeze hashes | `53f1db1` | Phase 43 source/golden hashes pinned |
| WR-02 no-false-green matrix | `08a15ec` | Independent freshness, evidence, ordering, and lifecycle controls |

---

_Fixed: 2026-07-19T20:58:14-04:00_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 9_
