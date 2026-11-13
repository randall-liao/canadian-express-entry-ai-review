---
phase: 29-candidate-vault-pii-perimeter
plan: 03
subsystem: api
tags: [cli, argparse, json-envelope, vault, pii-light, contract]

# Dependency graph
requires:
  - phase: 29-candidate-vault-pii-perimeter (plan 02)
    provides: "crawler.vault module (open_vault, profile/ITA store, import_document, summaries)"
  - phase: 29-candidate-vault-pii-perimeter (plan 01)
    provides: "crawler.paths.PathEscapeError for invalid_input mapping"
provides:
  - "Additive `vault` CLI subcommand: init / profile set|show / ita set / import / list"
  - "PII-light --json envelopes for every vault verb (ids/counts/status/sha-prefix only)"
  - "CONTRACT.md vault result-shape docs (five-key envelope + SCHEMA_VERSION 1.0 unchanged)"
affects: [29-04-pii-perimeter, phase-30-extraction, phase-32-auditor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive subcommand: reuse the frozen five-key envelope + stdout=JSON/stderr=human invariant; command value 'vault' added without a schema bump"
    - "Lazy `from crawler import vault` inside each handler keeps importing crawler.cli cheap (no pydantic on non-vault calls)"
    - "PII-light-by-construction: handlers build explicit result dicts from PII-light summaries; original_name/abs-path/claimed_points never reach stdout"

key-files:
  created:
    - crawler/tests/test_vault_cli.py
  modified:
    - crawler/cli.py
    - crawler/contract.py
    - crawler/CONTRACT.md

key-decisions:
  - "Implemented all five vault verbs together in the Task 1 commit; the Task 2 commit adds the import/list PII-light proof tests + CONTRACT.md/contract.py docs (clean split by concern)"
  - "vault import surfaces a sha256_prefix (first 12 hex) as a non-PII content fingerprint; never the original filename or absolute path"
  - "Bad input (missing file, bad slug, PathEscapeError, invalid inline JSON/factor) maps to invalid_input/exit 2 without echoing the offending value"

patterns-established:
  - "_vault_ok/_vault_fail helpers emit exactly one contract.envelope(\"vault\", ...) to stdout in --json mode, human text to stderr"
  - "vault subparser uses nested sub-subparsers (profile set|show, ita set) each with set_defaults(func=...)"

requirements-completed: [VAULT-01, VAULT-02, VAULT-03]

# Metrics
duration: 6min
completed: 2026-07-06
---

# Phase 29 Plan 03: Vault CLI Verbs Summary

**Additive `corpus-crawler vault` subcommand (init / profile set·show / ita set / import / list) that drives the private vault through the frozen five-key JSON envelope, with every `--json` result proven PII-light — original filenames, absolute paths, and claimed point values never cross the stdout boundary.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-06T05:17:44Z
- **Completed:** 2026-07-06T05:23:50Z
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Added a `vault` subparser (nested verb sub-subparsers) wired into `build_parser()`; the global `--json` flag + five-key envelope are reused unchanged.
- Six handlers (`init`, `profile set`, `profile show`, `ita set`, `import`, `list`) each emit exactly one `contract.envelope("vault", ...)` to stdout and route human text to stderr; bad input → `invalid_input`/exit 2 without echoing the offending value.
- Documented the additive vault result shapes in `CONTRACT.md` and added `vault` to `contract.py`'s command enumeration — with `SCHEMA_VERSION` staying `"1.0"` (no envelope bump).
- 10 CLI tests including the decisive PII-light proof: importing `Jane_Doe_UCI123.pdf` yields an `ev_` evidence id on stdout while the filename token and absolute path are absent.

## Task Commits

1. **Task 1: `vault init` / `profile set|show` / `ita set` verbs** — `f326e4a` (feat) — added the full vault subparser + all handlers + init/profile/ita tests
2. **Task 2: `vault import` / `list` + PII-light proof + CONTRACT.md** — `4553aa1` (feat) — import/list PII-light proof tests, CONTRACT.md vault section, contract.py enumeration

## Files Created/Modified
- `crawler/cli.py` - `vault` subparser + `_add_vault_subparser` + six `_cmd_vault_*` handlers + `_vault_ok`/`_vault_fail` helpers
- `crawler/contract.py` - added `vault` to the command enumeration in the module docstring + `envelope` docstring (no schema/envelope change)
- `crawler/CONTRACT.md` - new `vault` per-command section + `vault` added to the command key row
- `crawler/tests/test_vault_cli.py` - 10 tests: one valid envelope per verb, PII-light profile show / import / list, invalid_input on missing file

## Decisions Made
- All five verbs were implemented together in Task 1's commit (they share one subparser); Task 2's commit contributes the import/list PII-light proof tests plus the CONTRACT.md/contract.py documentation — split by concern rather than by handler.
- `vault import` exposes a `sha256_prefix` (first 12 hex) content fingerprint as an explicitly non-PII field; the original filename stays in the DB only.
- The CONTRACT.md vault section is an `### vault` h3 to match the sibling `### ground`/`### checklist` per-command sections.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Restored CONTRACT.md lines dropped during section insertion**
- **Found during:** Task 2 (CONTRACT.md edit)
- **Issue:** Inserting the vault section initially removed the "## Error object + types" intro sentence.
- **Fix:** Re-added the intro sentence; verified the Error section is intact.
- **Files modified:** crawler/CONTRACT.md
- **Verification:** Section renders correctly; grep confirms the vault section + intact error table.
- **Committed in:** 4553aa1

---

**Total deviations:** 1 auto-fixed (blocking doc-edit cleanup)
**Impact on plan:** No scope creep; documentation integrity restored.

## Issues Encountered
None during planned work.

## Known Stubs
None — all verbs dispatch to real vault compute; no placeholder data.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The vault is now usable end-to-end from the CLI (SC1/SC2 met via CLI); Plan 29-04 closes the perimeter (publish-safe/.gitignore/conformance).
- Frozen v3.x trust path (search/`--cite`/grounding/JSON envelope) untouched; the `vault` command is purely additive.

---
*Phase: 29-candidate-vault-pii-perimeter*
*Completed: 2026-07-06*

## Self-Check: PASSED
- crawler/tests/test_vault_cli.py — FOUND
- crawler/cli.py / contract.py / CONTRACT.md — modified & committed
- commits f326e4a, 4553aa1 — FOUND
