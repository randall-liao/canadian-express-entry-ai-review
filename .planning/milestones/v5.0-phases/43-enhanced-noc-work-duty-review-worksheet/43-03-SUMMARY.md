---
phase: 43-enhanced-noc-work-duty-review-worksheet
plan: 03
subsystem: cli

tags: [noc-2021, cli, vault, worksheet, review.noc, pii-light, index-preflight, idempotency, remediation-alias, safe-10]

# Dependency graph
requires:
  - phase: 43-01
    provides: "noc_worksheet.generate_worksheet — idempotent (duty_id, duty_sha) born-pending capture + vault-only cited artifact + PII-light summary"
  - phase: 43-02
    provides: "noc_review.review_noc_duties — inert never-green {AT-RISK,GAP,N/A} roll-up returning the closed PII-light PUBLIC_FIELDS dict"
  - phase: 29-vault-cli
    provides: "_vault_ok/_vault_fail PII-light envelope helpers, _require_readable_index SAFE-10 preflight, _add_vault_subparser, the shipped per---value-id 'vault confirm' verb"
  - phase: 37-remediation
    provides: "crawler/remediation.py _action_for + the shipped unresolved_noc {factor}-parameterized action template"
provides:
  - "crawler/cli.py: 'vault noc-worksheet' + 'vault noc-review' subverbs — index-preflighted, PII-light --json envelopes, human duty detail to stderr, per-duty confirm via the shipped 'vault confirm' verb only"
  - "crawler/remediation.py: _REASON_ALIASES {duty_review_manual -> unresolved_noc} resolved at the top of _action_for (reuses the shipped action; no duplicate template)"
  - "End-to-end CLI conformance for NOC-01/NOC-02: vault-only artifact, PII-light stdout, one-duty-at-a-time confirm, zero-artifact index-preflight refusal, idempotent rerun"
affects: [43-04-core-work-byte-identity, 45-mec-integrator]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies — composes only frozen CLI/generator/sidecar seams
  patterns:
    - "SAFE-10 zero-artifact ordering: _require_readable_index preflight FIRST — refuse invalid_input/exit-2 BEFORE open_vault/compute so a refusal writes zero artifacts"
    - "PII-light --json via the shipped _vault_ok helper (ids/counts/corpus-citations only); raw duty text + the cited worksheet body route to stderr / vault-only"
    - "No new confirmation path: per-duty confirm/correct/reject is the shipped per---value-id 'vault confirm' verb (no bulk confirm-all); idempotency inherited from the Plan-01 generator"
    - "Reason alias (not a duplicate template): a downstream reason token reuses an existing {factor}-parameterized action, keeping the no-inlined-volatile-rules gate clean"

key-files:
  created:
    - crawler/tests/test_noc_review_cli.py
  modified:
    - crawler/cli.py
    - crawler/remediation.py

key-decisions:
  - "An unresolvable / malformed --noc-code on 'vault noc-worksheet' (the generator validates \\d{5} and fails closed to a None-worksheet) is surfaced as one PII-free invalid_input/exit-2 refusal — the generator wrote zero artifacts, so this is fail-closed consistent"
  - "'vault noc-review' does NOT refuse on an unresolvable NOC — it returns the sidecar's valid inert N/A verdict (ok:true); only a bad/corrupt index preflights to a refusal"
  - "Human duty detail for 'vault noc-worksheet' is the cited worksheet body read back from the vault artifact and printed to stderr (mirrors 'vault fields'/'vault audit' PII-to-stderr routing); stdout stays PII-light"
  - "The worksheet verb adds NO idempotency logic of its own — a rerun returns the byte-stable Plan-01 envelope (same worksheet_doc_id/value_ids/duty_count) and creates no duplicate confirmable row"
  - "duty_review_manual aliases to the shipped unresolved_noc action rather than adding a duplicate _ACTION_TEMPLATES entry (W1); the aliased prose is the existing {factor}-parameterized string, no volatile literal introduced"

patterns-established:
  - "Pattern: additive vault subverb = index preflight -> open_vault -> drive frozen lib -> PII-light _vault_ok on stdout + human detail to stderr"
  - "Pattern: reason-code alias map resolved at the top of the action lookup to reuse a shipped template with zero duplication"

requirements-completed: []  # NOC-01/NOC-02 stay Pending until Plan 04 freeze/conformance closes (see Next Phase Readiness)

# Metrics
duration: 6min
completed: 2026-07-19
---

# Phase 43 Plan 03: NOC Work-Duty Review CLI Wiring Summary

**Wired the Plan-01 worksheet generator and the Plan-02 inert sidecar into the CLI as `vault noc-worksheet` / `vault noc-review` — index-preflighted (SAFE-10 zero-artifact refusal), PII-light `--json` stdout, the cited worksheet body + human verdict detail to stderr only, per-duty confirm via the shipped `vault confirm` verb with no bulk path, and an idempotent rerun — plus a `duty_review_manual -> unresolved_noc` remediation reason alias that reuses the shipped action with no duplicate template.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-19T10:14:27Z
- **Completed:** 2026-07-19T10:21:00Z
- **Tasks:** 2 (both complete)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- **Task 1 — reason alias (`crawler/remediation.py`):** added a module-level `_REASON_ALIASES = {"duty_review_manual": "unresolved_noc"}` and resolved it at the TOP of `_action_for` (before the `_ACTION_TEMPLATES` lookup). `_action_for('core.work','duty_review_manual',...)` is now byte-identical to the `unresolved_noc` action ("The occupation details for … need review …"). No duplicate template was added, no volatile literal introduced — the `no_inlined_volatile_rules` gate over `remediation.py` stays green, and unknown codes still degrade via `_DEFAULT_ACTION_BY_KIND`.
- **Task 2 — the two vault subverbs (`crawler/cli.py`):** registered `noc-worksheet` and `noc-review` under `_add_vault_subparser` (both added to the vault metavar + help), each taking `--candidate`/`--noc-code`/`--db`.
  - `_cmd_vault_noc_worksheet`: calls `_require_readable_index(args, args.db)` FIRST (SAFE-10 — refuse `invalid_input`/exit-2 before `open_vault`/compute, zero artifacts), then drives the idempotent `noc_worksheet.generate_worksheet`; emits the PII-light `{noc_code, duty_count, value_ids, worksheet_doc_id, citations}` via the shipped `_vault_ok`; the cited worksheet body routes to STDERR only in human mode; an unresolvable/malformed `--noc-code` (None-worksheet) fails closed to one `invalid_input`/exit-2 refusal.
  - `_cmd_vault_noc_review`: same index preflight, then emits the Plan-02 sidecar's CLOSED PII-light never-green dict (`PUBLIC_FIELDS`) on stdout; human verdict detail to stderr only.
  - Added NO new confirmation path — per-duty confirm/correct/reject remains the shipped per-`--value-id` `vault confirm` verb (no bulk confirm-all).
- **Task 2 — end-to-end tests (`crawler/tests/test_noc_review_cli.py`, 242 lines):** a `_run(argv)->(rc,out,err)` harness over `crawler.cli.main` under a throwaway `$PR_PERSONAL_DIR` asserting: worksheet artifact written only under the vault; `--json` stdout PII-light (no raw duty text / absolute path / `raw_text`); human mode leaves stdout empty and puts duty detail on stderr; one duty confirmed at a time via `vault confirm` (+ structural no-bulk-confirm-all defense); a missing/corrupt index → one `invalid_input`/exit-2 refusal with zero artifacts (both verbs); and an idempotent rerun — same `worksheet_doc_id`/`value_ids`/`duty_count`, a between-run confirmation preserved, and `vault noc-review` `confirmed_count` not inflated.

## Task Commits

Each task was committed atomically:

1. **Task 1: alias duty_review_manual → unresolved_noc (no duplicate template)** — `7be65ac` (feat)
2. **Task 2: wire vault noc-worksheet + noc-review verbs + end-to-end tests** — `b786baa` (feat)

**Plan metadata:** _(final docs commit — see completion)_

## Files Created/Modified

- `crawler/remediation.py` — `_REASON_ALIASES` map + one-line alias resolution at the top of `_action_for` (reuses the shipped `unresolved_noc` action; no duplicate template).
- `crawler/cli.py` (+133 lines) — `_cmd_vault_noc_worksheet` / `_cmd_vault_noc_review` handlers + their subparser registration under `_add_vault_subparser` (metavar/help updated for both verbs).
- `crawler/tests/test_noc_review_cli.py` (242 lines, **created**) — end-to-end CLI coverage for both verbs.

## Decisions Made

- An unresolvable/malformed `--noc-code` on `noc-worksheet` is a fail-closed `invalid_input`/exit-2 refusal (the generator already wrote nothing); `noc-review` instead returns the valid inert `N/A` verdict for an unresolvable NOC — only a bad index preflights to a refusal there.
- Human duty detail for `noc-worksheet` is the cited worksheet body read back from the vault artifact and printed to stderr (PII-to-stderr routing consistent with `vault fields`/`vault audit`); stdout stays PII-light.
- The worksheet verb inherits idempotency entirely from the Plan-01 generator — a rerun returns the byte-stable envelope and creates no duplicate confirmable row.

## Deviations from Plan

### Auto-fixed Issues

None — the plan executed as written for both tasks (no code deviations, no auto-fixes, no architectural changes, no package installs, no authentication gates).

## Issues Encountered

- The plan's `<verification>` names `crawler/tests/test_cli_contract.py`, which does not exist in this repo (same class of stale-path reference noted in the 43-01 summary). The envelope-contract coverage lives in `crawler/tests/test_json_contract.py` (plus `test_cli.py` / `test_vault_cli.py`); those were run instead and all pass, confirming the five-key envelope contract is unchanged.
- Consistent with the 43-01/43-02 precedent, `corpus/index.db` is git-ignored (local-only), so the new CLI test class is guarded by `@unittest.skipUnless(_REAL_DB.is_file())`. In this environment the corpus IS present, so the full slice ran (6 tests + 2 subtests green).

## Verification Results

- `.venv/bin/python -m pytest crawler/tests/test_noc_review_cli.py -q` → **6 passed, 2 subtests** (both verbs end-to-end).
- Task-1 alias check → `_action_for('core.work','duty_review_manual','at_risk')` byte-identical to `unresolved_noc`; `duty_review_manual` NOT in `_ACTION_TEMPLATES`; `_REASON_ALIASES == {'duty_review_manual':'unresolved_noc'}`.
- `.venv/bin/python -m pytest crawler/tests/test_crs_no_inlined_rules.py -q` → **4 passed** (no-inlined-volatile-rules gate green over `remediation.py`).
- `.venv/bin/python -m pytest test_noc_review_cli.py test_extract_confirm_cli.py test_json_contract.py test_cli.py test_vault_cli.py -q` → **71 passed, 1 skipped, 2 subtests** (new + existing CLI flows + envelope contract unchanged).
- Regression: `test_noc_review.py test_remediation_projection.py test_remediation_cli.py test_vault_audit_cli.py` → **all passed** (46 passed, 8 subtests across the remediation/audit set).
- Conformance gates: `test_conformance_v40_no_false_green.py test_auditor_dispatch.py` → **17 passed, 148 subtests**; `test_conformance_v40_privacy_containment.py test_conformance_v41_privacy.py` → **21 passed** (no false-green, inert sidecar still absent from the registry, PII containment intact).
- No-bulk-confirm gate: `grep -rniE 'confirm[_-]all|bulk_confirm'` over `crawler/*.py` returns ONLY negated prose ("no bulk confirm-all") — no bulk handler exists.
- No-new-dependency gate: `git diff fdcc988 HEAD -- pyproject.toml poetry.lock` → **empty** (zero dependency change).

## Known Stubs

None — both verbs drive the shipped, corpus-grounded generator/sidecar; there are no hardcoded empty values, placeholder text, or unwired data sources on the new surface.

## Next Phase Readiness

- **Plan 04 (core.work byte-identity + conformance):** the operator surface is now complete (NOC-01 view + NOC-02 per-duty confirm via the shipped verb). Plan 04 can assert the frozen `core.work` audit shows zero diff before/after worksheet generation/regeneration and confirmed duty values, then flip NOC-01/NOC-02/NOC-03 to complete once the freeze/conformance proof lands.
- **REQUIREMENTS:** NOC-01/NOC-02/NOC-03 remain **Pending** — per the 43-02 decision, the requirements are marked complete only after the Plan-04 conformance/byte-identity proof closes.
- **Phase 45 (MEC integrator):** consumes `review_noc_duties` LATER as an AT-RISK human-confirmed skilled-work input; the CLI verbs shipped here are the operator entry point, with no MEC wiring done in this plan (as scoped).

---
*Phase: 43-enhanced-noc-work-duty-review-worksheet*
*Completed: 2026-07-19*

## Self-Check: PASSED
- Files verified on disk: `crawler/cli.py`, `crawler/remediation.py`, `crawler/tests/test_noc_review_cli.py`, `43-03-SUMMARY.md` — all FOUND.
- Commits verified in git history: `7be65ac` (Task 1 remediation alias), `b786baa` (Task 2 CLI wiring + tests) — all FOUND.
