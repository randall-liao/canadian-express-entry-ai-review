---
phase: 32-auditor-vertical-slice-private-report-contract
plan: 05
subsystem: cli
tags: [cli, contract, pii-perimeter, publish-safe, audit]

requires:
  - phase: 32-03
    provides: audit_factor + AuditGroundingError
  - phase: 32-04
    provides: run_audit (compute + vault-only write) + PublicAuditEnvelope
  - phase: 32-01
    provides: PublicAuditEnvelope PII-light model
provides:
  - vault audit CLI subverb emitting a PII-light 5-key envelope
  - CONTRACT.md vault audit result-shape documentation
  - publish-safe coverage confirmation for the crs-audit report artifact
affects: [33 fan-out CLI, operator workflow]

tech-stack:
  added: []
  patterns:
    - "vault subverb reuses command:\"vault\" (frozen envelope + allowlist unchanged)"
    - "Grounding failure -> ok:false + invalid_input + exit 2 (verdict-not-error rule)"

key-files:
  created:
    - crawler/tests/test_vault_audit_cli.py
    - crawler/tests/test_audit_pii_perimeter.py
  modified:
    - crawler/cli.py
    - crawler/CONTRACT.md
    - scripts/check_publish_safe.py

key-decisions:
  - "vault audit emits only PublicAuditEnvelope.model_dump() on stdout; applicant detail -> stderr"
  - "AuditGroundingError -> _vault_fail(INVALID_INPUT, exit 2), no report (SC5)"
  - "Tests patch crs_rules.load_registry to a synthetic registry for a hermetic slice"

patterns-established:
  - "Publish-safe already covered output/crs-audit + .json/.md; only a doc comment was added"

requirements-completed: [AUDIT-02, AUDIT-06]

duration: 16min
completed: 2026-07-06
---

# Phase 32 Plan 05: vault audit CLI + PII Perimeter Summary

**The operator surface that slams the PII door: an additive `vault audit` verb that runs the first-official-language slice and emits ONE PII-light envelope (run id, verdicts, counts, corpus-cited claims, vault-relative report path) — with the full evidence-bearing report quarantined to the vault, grounded GAP/AT-RISK as `ok:true`, and a grounding failure as `ok:false` + exit 2 writing no report.**

## Performance

- **Duration:** ~16 min
- **Tasks:** 2 (auto)
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- Added `_cmd_vault_audit` (+ `_add_vault_subparser` wiring) emitting a PII-light `PublicAuditEnvelope` on stdout under the reused `command: "vault"` — the frozen 5-key envelope + allow-list untouched.
- Routed applicant factor-card detail to stderr only; grounded verdicts are `ok:true`, a grounding failure is `ok:false` + `invalid_input` + exit 2 with no report.
- Proved the SC4 perimeter end-to-end (no sentinel value / `ev_` id / absolute path on stdout; the vault report retains them; claims carry only corpus citation ids) and confirmed publish-safe `VAULT_ARTIFACT` coverage for `output/crs-audit/*.json|.md` + `*.sqlite`.

## Task Commits

1. **Tasks 1+2: vault audit verb + CONTRACT.md + publish-safe + perimeter tests** - `13a72fc` (feat)

## Files Created/Modified
- `crawler/cli.py` — `_cmd_vault_audit` + `audit` subparser registration.
- `crawler/CONTRACT.md` — `vault audit` result-shape row + subsection + vault-only artifact note.
- `scripts/check_publish_safe.py` — comment tying `output/crs-audit/` to the Phase-32 report (coverage already present).
- `crawler/tests/test_vault_audit_cli.py` — 5 CLI envelope tests (ok:true grounded, ok:false failure, PII-light stdout).
- `crawler/tests/test_audit_pii_perimeter.py` — 3 perimeter tests (SC4 no-PII stdout + publish-safe coverage).

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_vault_audit_cli.py crawler/tests/test_audit_pii_perimeter.py -q` → 8 passed.
- `.venv/bin/python scripts/check_publish_safe.py` → 0 violations (exit 0).
- `.venv/bin/python -m pytest crawler/tests/test_json_contract.py crawler/tests/test_vault_cli.py -q` → green (envelope command allow-list unchanged).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Hermetic CLI test needed a synthetic registry**
- **Found during:** Task 1 test authoring
- **Issue:** `_cmd_vault_audit` loads the REAL registry via `crs_rules.load_registry()`, whose rows cite the real (git-ignored) corpus — a synthetic index would fail grounding, making an `ok:true` unit test non-hermetic.
- **Fix:** the CLI tests patch `crawler.crs_rules.load_registry` to return the Plan-03 synthetic registry and pass `--db <synthetic index>`, keeping the slice fully hermetic. No production code changed for this.
- **Files modified:** `crawler/tests/test_vault_audit_cli.py`, `crawler/tests/test_audit_pii_perimeter.py`
- **Commit:** `13a72fc`

## Known Stubs
None.

## Threat Flags
None — no new trust boundary beyond the documented `vault audit` → stdout and report → filesystem boundaries (both mitigated).

## Self-Check: PASSED
- All Phase-32 source + test files verified present on disk.
- All per-task commits (RED/GREEN/feat) verified in git history.
- Full suite (excl. slow test_dupaudit): 568 passed, 1 skipped, 184 subtests.
- Publish-safe: 0 violations across 250 tracked files.
- End-to-end `vault audit` vs real corpus: grounded AT-RISK (ok:true), PII-light stdout, vault-only report.
