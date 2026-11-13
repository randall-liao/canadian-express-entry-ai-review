---
phase: 29-candidate-vault-pii-perimeter
plan: 04
subsystem: infra
tags: [publish-safety, gitignore, pii-perimeter, conformance, vault, security]

# Dependency graph
requires:
  - phase: 29-candidate-vault-pii-perimeter (plan 02)
    provides: "crawler.vault (open_vault, import_document, is_evidence_id/is_citation_id)"
  - phase: 29-candidate-vault-pii-perimeter (plan 01)
    provides: "crawler.paths.resolve_within / PathEscapeError / candidate_root"
provides:
  - "VAULT_ARTIFACT publish-safe category covering vault DB/WAL/SHM, candidates/ tree, and vault-subtree render/OCR/report files"
  - ".gitignore *.sqlite/*.sqlite-shm/*.sqlite-wal defense-in-depth lines"
  - "SC3+SC4 conformance suite proving the PII perimeter holds end-to-end"
affects: [phase-30-extraction, phase-31-rule-registry, phase-32-auditor, phase-34-safety-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Path-name publish-safe category (scan_vault_artifact) complements the existing CORPORA_PREFIXES scan; vault DB trips BOTH categories"
    - "Vault-subtree extension scoping (files/raw, rendered, pages, text, output/crs-audit) so ordinary repo .md/.png/.json are never false-positives"
    - "git-staging conformance via throwaway git repo seeded with the project .gitignore"

key-files:
  created:
    - crawler/tests/test_vault_pii_perimeter.py
  modified:
    - scripts/check_publish_safe.py
    - .gitignore
    - scripts/tests/test_check_publish_safe.py

key-decisions:
  - "scan_vault_artifact anchors subtree tokens at path boundaries ('/'+sub) to reduce false positives while honoring the plan's subtree list"
  - "Vault DB detection is by basename suffix (.sqlite/.sqlite-wal/.sqlite-shm/.db-wal/.db-shm) so vault.sqlite + all sidecars are covered by one rule"
  - "Conformance git-staging test isolates git config (GIT_CONFIG_GLOBAL/SYSTEM=/dev/null) so it never depends on developer git settings"

patterns-established:
  - "The publish-safe guard + .gitignore + path guard are regression-tested, not assumed (PITFALLS-v4.0 Pitfall 2/3)"

requirements-completed: [VAULT-03, VAULT-04]

# Metrics
duration: 12min
completed: 2026-07-06
---

# Phase 29 Plan 04: PII Perimeter Close-out Summary

**Extends publish-safe + `.gitignore` to flag every vault artifact type (SQLite DB + WAL/SHM sidecars, the `candidates/` tree, rendered/OCR/report files) and ships an SC3+SC4 conformance suite proving a candidate `evidence_id` is never citable as authority and vault artifacts can neither be staged nor written outside the vault.**

## Performance

- **Duration:** ~12 min (incl. two full ~13-min suite runs)
- **Started:** 2026-07-06T05:23:50Z
- **Completed:** 2026-07-06T05:41:49Z
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Added the `VAULT_ARTIFACT` publish-safe category (`scan_vault_artifact`) wired into `main()`: flags the `candidates` namespace segment, vault DB + WAL/SHM sidecars, and vault-subtree document/render/OCR/report files — with zero false positives on ordinary repo files.
- Extended `.gitignore` with `*.sqlite`/`*.sqlite-shm`/`*.sqlite-wal` (the existing `personal/` + `*.db*` lines already cover the real vault location).
- Extended the guard unit tests (7 new methods + subtests) and added a full SC3+SC4 conformance suite (`test_vault_pii_perimeter.py`, 8 tests).
- Proved end-to-end: vault DB trips both categories; `git add -A` leaves vault DB/WAL/`files/raw` unstaged under the project `.gitignore`; `resolve_within` refuses `..`/symlink escapes; `evidence_id` is never a corpus `citation_id` nor resolvable via `searchindex.resolve`; importing never contaminates a sibling `corpus/`.

## Task Commits

1. **Task 1: Extend publish-safe + .gitignore for vault artifacts (VAULT-04)** — `4db9f4d` (feat)
2. **Task 2: PII-perimeter conformance suite — SC3 + SC4** — `3047e47` (test, TDD)

## Files Created/Modified
- `scripts/check_publish_safe.py` - `VAULT_ARTIFACT` category + `scan_vault_artifact()` + main()-loop wiring + vault constants
- `.gitignore` - `*.sqlite`/`*.sqlite-shm`/`*.sqlite-wal` defense-in-depth lines
- `scripts/tests/test_check_publish_safe.py` - `VaultArtifactTests` (DB/sidecars/candidates/subtree flagged; zero false positives)
- `crawler/tests/test_vault_pii_perimeter.py` - SC3+SC4 conformance suite (publish-safe, git-staging, path guard, id separation, never-citable, no-contamination)

## Decisions Made
- Vault-subtree tokens are anchored at path boundaries (`"/" + sub`) to reduce false-positive risk while honoring the plan's subtree list; verified the current tree has no matches (`check_publish_safe.py` still exits 0).
- The git-staging conformance test pins `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` to `/dev/null` so it is hermetic and never depends on developer git config.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None during planned work.

## Known Stubs
None.

## Threat Flags
None — this plan closes the perimeter; no new trust-boundary surface introduced beyond the vault already covered.

## Verification Results
- `.venv/bin/python -m pytest scripts/tests/test_check_publish_safe.py crawler/tests/test_vault_pii_perimeter.py -q` — pass (36 + 8).
- `.venv/bin/python scripts/check_publish_safe.py` — `✓ publish-safe: 201 tracked files scanned, 0 violations` (exit 0; no false positives).
- Full relevant suite: `.venv/bin/python -m pytest crawler/tests scripts/tests -q` — **400 passed, 1 skipped, 106 subtests passed** (baseline 332 → +68 new, zero regressions).
- `git grep -n "VAULT_ARTIFACT" scripts/check_publish_safe.py` and `git grep -n "\*.sqlite" .gitignore` — both return hits.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The PII perimeter is regression-tested and closed; Phase 30 (extraction) can render/OCR into the vault knowing every new artifact type (images, OCR text, DB sidecars, private reports) is already guard-covered.
- SC1–SC4 for Phase 29 are all satisfied; the frozen v3.x trust path (search/`--cite`/grounding/JSON envelope) is untouched.

---
*Phase: 29-candidate-vault-pii-perimeter*
*Completed: 2026-07-06*

## Self-Check: PASSED
- crawler/tests/test_vault_pii_perimeter.py — FOUND
- scripts/check_publish_safe.py / .gitignore / scripts/tests/test_check_publish_safe.py — modified & committed
- commits 4db9f4d, 3047e47 — FOUND
