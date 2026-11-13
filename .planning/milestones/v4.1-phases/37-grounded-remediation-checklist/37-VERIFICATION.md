---
phase: 37-grounded-remediation-checklist
verified: 2026-07-17T12:55:32Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification. No prior 37-VERIFICATION.md existed."
---

# Phase 37: Grounded Remediation Checklist Verification Report

**Phase Goal:** The applicant can turn a completed audit into a private, corpus-cited fix checklist — exactly one actionable item per unresolved finding — reusing already-grounded verdicts with no second advice path.
**Verified:** 2026-07-17T12:55:32Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

Verification was performed goal-backward against the ACTUAL codebase and the real
14 MB `corpus/index.db` (present + extraction deps installed), NOT SUMMARY.md claims.
The whole applicant path was reproduced end-to-end through the real `crawler.cli`:
`vault profile set` (the shipped `personal.example/crs-profile.example.yaml`) →
`vault audit --all --db corpus/index.db` → `vault remediate` against a scratch vault
under a `PR_PERSONAL_DIR` tempdir. The audit produced **18 cards (9 GAP + 9 N/A)** and
`vault remediate` projected **exactly 9 items — one per GAP finding, zero for the 9 N/A
cards** — with a PII-light stdout summary and the full checklist written ONLY under
`candidates/ex/output/remediation/`. Every fail-closed refusal (`no_completed_audit`,
`registry_drift`) was re-triggered at runtime (exit 2, PII-free reason token, zero
artifacts). The no-second-trust-path guarantee was re-checked by AST import walk, by a
runtime booby-trap over `load_registry`+`registry_fingerprint`+`build_remediation`, and
by the no-inlined-volatile-rules self-scan. The full suite was independently re-run:
**798 passed, 1 skipped, 355 subtests passed** in 587.73s (0:09:47) — exactly the
pre-fix baseline of 797 + the 1 new WR-01 regression test, the single skip being the
pre-existing baseline item — with 0 failures; `check_publish_safe.py` 0 violations;
`run_conformance.py` PASS SAFE-01..04.

### Observable Truths (ROADMAP Success Criteria + PLAN must_haves)

| #   | Truth (requirement) | Status | Evidence |
| --- | ------------------- | ------ | -------- |
| 1 | Applicant can generate a private remediation checklist from a selected completed audit run, with exactly one actionable item for each `GAP`, `AT-RISK`, or unresolved/unpriced factor (REM-01) | ✓ VERIFIED | `_finding_kind` (`remediation.py:231-239`) buckets GAP→gap, AT-RISK→at_risk, SUBSTANTIATED+`points_unresolved`→unpriced, else None (skipped). `build_remediation` (`:259-301`) emits one item per non-None card in card order. Live: real audit → 9 GAP + 9 N/A cards; `vault remediate` → **item_count 9**, `counts.gap=9`, item factor_ids == the 9 GAP factors exactly; the 9 N/A cards produced NO item. Default run selection via `latest_completed_audit_run` (`vault.py:1214-1228`, `status='complete'`); `--audit-run-id` honored (`test_remediate_specific_run_id`). |
| 2 | Each item identifies factor, verdict/reason, score impact, the existing grounded citation + verbatim rule span, and a deterministic action template keyed by factor and reason (REM-02) | ✓ VERIFIED | `PrivateRemediationItem` (`:176-191`) carries `factor_id`, `factor_group`, `verdict`, `reason_code`, `finding_kind`, `substantiated_points`, `score_delta`, `points_unresolved`, `evidence_ids`, `citations`, `action`. Live JSON item: `core.age`/`GAP`/`missing_evidence`, citation `guidance/crs-criteria.md#004` quote `"20 to 29 years of age | 100 | 110"` — confirmed **verbatim in the registry** (`(chunk_id,quote)∈registry_pairs`). All 9/9 items carry ≥1 citation with a real quote; all 9/9 carry a non-empty `action` mentioning the factor id. `_ACTION_TEMPLATES` (21 reason keys) + `_DEFAULT_ACTION_BY_KIND` fallback, `_action_for(factor,reason,kind)` → `template.format(factor=...)` (`:148-153`, `:68-145`). |
| 3 | Remediation reuses already-grounded verdicts+citations with NO re-scoring / re-grounding / synthesized volatile requirement / second advice path — same vault in → identical checklist out (REM-03) | ✓ VERIFIED | AST import walk of `remediation.py`: **no import names `searchindex` or `grounding`**. `crs_rules.load_registry` (`crs_rules.py:95-118`) is pure `yaml.safe_load`+pydantic — source references neither `grounding` nor `validate_registry`. Runtime booby-trap (grounding/searchindex→`_boom`): `load_registry`+`registry_fingerprint`+`build_remediation` all ran clean. `build_remediation` has no id/timestamp/I-O; called twice → identical `model_dump()`; `registry_fingerprint` deterministic. `no_inlined_volatile_rules([remediation.py])` → `[]`. |
| 4 | The full checklist + evidence pointers stay vault-only; stdout exposes only a PII-light summary; every rendered artifact carries the substantiation-screening notice (REM-04) | ✓ VERIFIED | Live: JSON+MD written ONLY under `candidates/ex/output/remediation/` (`find rem_*` matched nothing outside the subtree). Stdout `--json` = `PublicRemediationSummary` (run_id, source_audit_run_id, item_count, counts, vault-relative `private_output_path`) — **no `ev_`, no applicant value**; `_reject_absolute_path` validator on the path (`:222-225`). Human item detail routes to stderr and is skipped under `--json` (`cli.py:1207-1211`). MD ends with the imported `SCREENING_NOTICE` ("Substantiation screening … not legal advice"). Refusals (`no_completed_audit`, `registry_drift`) → `invalid_input`/exit 2 + PII-free `reason=<code>` + ZERO artifacts. `output/remediation/` registered in publish-safe `VAULT_SUBTREES`. |

**Score:** 4/4 truths verified (each PLAN's detailed sub-truths also verified — see below).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/remediation.py` | two-tier models + PURE `build_remediation` projection + action templates + render + `run_remediation` writer + fingerprint gate | ✓ VERIFIED | 425 lines. `RemediationCitation`/`PrivateRemediationItem`/`PrivateRemediationChecklist` (PII-bearing, `extra="forbid"`) + `PublicRemediationSummary` (PII-light, path validator); pure `build_remediation` (`:259-301`); `_quote_map` static registry read (`:242-256`); `_finding_kind` (`:231-239`); `run_remediation` build-before-write + fingerprint drift gate (`:377-425`); `SCREENING_NOTICE` imported, never forked. |
| `crawler/tests/test_remediation.py` | projection (one item/finding) + item-fields + determinism + PII-light + fail-closed drift | ✓ VERIFIED | 144 lines, 8 tests (projection count, finding kinds, item fields, retrieve-what-you-cite, determinism, PII-light summary, fail-closed-on-drift, screening notice). All pass. |
| `crawler/tests/test_remediation_cli.py` | vault-only write + PII-light stdout + refusals + no-artifact proofs | ✓ VERIFIED | 180 lines, 6 tests (happy path, specific run-id, + 4 refusals incl. `test_refusal_registry_drift`). Uses a SYNTHETIC completed report so the whole path runs UNGUARDED. All pass. |
| `crawler/tests/test_remediation_projection.py` | retrieve-what-you-cite + no-second-trust-path (AST + call-level) + determinism + unpriced-invariant | ✓ VERIFIED | 139 lines, 6 tests. AST import walk + call-level trust-path booby-trap + registry-pair agreement + determinism + unpriced invariant. All pass. |
| `crawler/tests/test_crs_no_inlined_rules.py` | `remediation.py` added to the no-inlined scan surface (positive control still bites) | ✓ VERIFIED | `_SURFACE` includes `crawler/remediation.py` (`:30`); aggregate gate returns `[]`; positive control still trips. |
| `crawler/vault.py` | `new_remediation_id` (`rem_` prefix) + `latest_completed_audit_run` selector | ✓ VERIFIED | `new_remediation_id` (`:315-321`) mints `rem_`+12 hex; `latest_completed_audit_run` (`:1214-1228`) `?`-bound `WHERE status='complete' ORDER BY completed_at DESC, audit_run_id DESC LIMIT 1`. |
| `crawler/cli.py` | `_cmd_vault_remediate` + `remediate` subparser + fail-closed refusals | ✓ VERIFIED | `_cmd_vault_remediate` (`:1176-1217`); `RemediationError`→`invalid_input`/`EXIT_INVALID_INPUT` with `_REMEDIATION_HINTS` recovery text; `remediate` sub-subparser (`:1387-1397`), no `--db`; metavar updated. |
| `scripts/check_publish_safe.py` | `output/remediation/` in `VAULT_SUBTREES` | ✓ VERIFIED | `VAULT_SUBTREES` includes `"output/remediation/"` (`:71`); scanner 0 violations over 336 tracked files. |
| `crawler/models/audit.py` + `crawler/auditor.py` (WR-01) | `PrivateAuditReport.registry_fingerprint` stamped by the auditor | ✓ VERIFIED | Additive optional `registry_fingerprint: str = ""` (`audit.py:210`); stamped in `run_single_factor_audit` (`auditor.py:290`) AND `run_full_audit` (`auditor.py:350`) via `crs_rules.registry_fingerprint(registry)`. Live audit report carried a real 64-hex fingerprint. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `remediation.build_remediation` | `models/audit.PrivateAuditReport` | projects `factor_cards` → items (`points_unresolved` gate) | ✓ WIRED | Iterates `report.factor_cards`; `_finding_kind` reads `verdict`/`points_unresolved`; item copies card fields verbatim. |
| `remediation` | `crs_rules.load_registry` | `citation_id → verbatim quote` map (no re-ground) | ✓ WIRED | `_quote_map` scopes to `auditors.consumed_factor_ids`, `setdefault(chunk_id, quote)`; static read only; drift → `RemediationError`. |
| `cli._cmd_vault_remediate` | `remediation.run_remediation` | load completed report → build → vault-only write | ✓ WIRED | `cli.py:1194`; `RemediationError`/`PathEscapeError`→`invalid_input`/exit 2; success → PII-light `_vault_ok`. |
| `remediation.run_remediation` | `paths.resolve_within` | `output/remediation` write path re-anchored | ✓ WIRED | `resolve_within(vault.root, "output","remediation")` (`:415`); `_load_report` reads via `resolve_within(vault.root.parent.parent, ...)` (the inverse of `_vault_relative`). |
| `auditor.run_full_audit` / `run_single_factor_audit` | `crs_rules.registry_fingerprint` | stamp audit-time fingerprint into the report | ✓ WIRED | `auditor.py:290,350`; `run_remediation` compares `report.registry_fingerprint` to the current registry (`:407-409`) → `registry_drift` on mismatch. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| remediation checklist | `checklist.items` | `build_remediation` over the stored `PrivateAuditReport` (real `vault audit --all` over `corpus/index.db`) | Yes — 9 items derived from 9 real GAP cards, factor_ids match exactly, not empty/static | ✓ FLOWING |
| item citations | `item.citations[].quote` | `_quote_map` over `crs_rules.load_registry()` rows | Yes — live quote `"20 to 29 years of age | 100 | 110"` confirmed verbatim in a real registry citation | ✓ FLOWING |
| public summary | `PublicRemediationSummary` | `to_public_summary(checklist, vault-relative path)` | Yes — real counts (`item_count=9`, `gap=9`), vault-relative path, no PII | ✓ FLOWING |
| registry_fingerprint gate | `report.registry_fingerprint` | `crs_rules.registry_fingerprint(registry)` stamped at audit time | Yes — real 64-hex fp stamped; tampered fp → live `registry_drift` refusal | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full applicant path over real index | `vault profile set` → `vault audit --all --db corpus/index.db` → `vault remediate` | `ok:true`, `item_count=9`, `counts.gap=9`, all items match the 9 GAP factors | ✓ PASS |
| PII-light stdout | inspect `--json` result | no `ev_`, vault-relative `private_output_path` under `candidates/ex/output/remediation/` | ✓ PASS |
| Vault-only write + screening notice | `find` + read MD | JSON+MD only under `output/remediation/`; MD ends with "Substantiation screening … not legal advice" | ✓ PASS |
| Verbatim citation | registry-pair membership | live `(chunk_id, quote)` ∈ real registry citations | ✓ PASS |
| Refuse: no completed audit | fresh vault → `vault remediate` | `ok:false`, `invalid_input`, exit **2**, `reason=no_completed_audit`, PII-free, 0 artifacts | ✓ PASS |
| Refuse: registry drift (WR-01) | tamper stored fp → `vault remediate` | `ok:false`, `invalid_input`, exit **2**, `reason=registry_drift`, no new artifact | ✓ PASS |
| No second trust path | AST import walk + runtime booby-trap | no `searchindex`/`grounding` import; load+fingerprint+build ran with trust path trapped | ✓ PASS |
| Determinism + no-inlined | build twice + self-scan | identical `model_dump()`; `no_inlined_volatile_rules([remediation.py])==[]` | ✓ PASS |
| Phase-37 test files | `pytest test_remediation test_remediation_cli test_remediation_projection test_crs_no_inlined_rules -q` | 24 passed | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared or implied by this phase's
plans/summaries. Verification used the phase pytest suites + full suite +
`scripts/run_conformance.py` + `scripts/check_publish_safe.py` + live `crawler.cli`
reproductions, all run independently.

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| conformance gate | `.venv/bin/python scripts/run_conformance.py` | exit 0, `PASS — SAFE-01, SAFE-02, SAFE-03, SAFE-04` (51 passed) | PASS |
| publish-safe scanner | `.venv/bin/python scripts/check_publish_safe.py` | exit 0, 0 violations (336 tracked files) | PASS |
| full suite | `.venv/bin/python -m pytest crawler/tests -q` | **798 passed, 1 skipped, 355 subtests, 0 failed** (587.73s) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| REM-01 | 37-01 | Private checklist from a selected completed audit run, one item per GAP/AT-RISK/unpriced factor | ✓ SATISFIED | Truth 1 — live 9 GAP → 9 items, N/A → 0, `latest_completed_audit_run`/`--audit-run-id` selection. |
| REM-02 | 37-01 | Each item: factor, verdict/reason, score impact, grounded citation + verbatim rule span, deterministic action keyed by factor+reason | ✓ SATISFIED | Truth 2 — full item schema, verbatim registry quote, factor-parameterized action templates. |
| REM-03 | 37-01/37-03 | Reuse grounded verdicts+citations, no re-score/re-ground/synthesize/second trust path; identical out | ✓ SATISFIED | Truth 3 — no `searchindex`/`grounding` import (AST + runtime), pure `load_registry`, determinism, `no_inlined_volatile_rules==[]`, fingerprint-gated. |
| REM-04 | 37-02 | Full checklist + `ev_` pointers vault-only; PII-light stdout; screening notice on every artifact; fail-closed refusals | ✓ SATISFIED | Truth 4 — artifacts only under `output/remediation/`, PII-light summary, MD screening notice, `no_completed_audit`/`registry_drift` refusals with zero artifacts. |

All four v4.1 REM requirements map to Phase 37 exactly once (REQUIREMENTS.md /
ROADMAP.md), each claimed by a plan (37-01→REM-01/02/03, 37-02→REM-04, 37-03→REM-03),
and implemented. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | — | No `TBD`/`FIXME`/`XXX` debt markers and no `TODO`/`HACK`/`PLACEHOLDER` in any phase-modified source/test/data file | — | Completion is auditable. |

The `_finding_kind` early `return None` and `build_remediation`'s `RemediationError`
raise are intentional projection/fail-closed semantics (verified by tests + live runs),
not empty handlers. The example profile's "illustrative placeholder" comment is
descriptive prose, not a stub.

### Code Review Status (WR-01)

- 37-REVIEW.md: **0 Critical, 1 Warning, 5 Info** — resolution `resolved` (the Warning fixed).
- **WR-01** (drift guard incomplete: remediation re-derived verbatim spans from the
  *current* on-disk registry rather than the audit-time grounding; the per-citation
  guard only caught *removed* ids, not a changed quote or a swapped registry) is
  **FIXED** by stamping `crs_rules.registry_fingerprint(registry)` into
  `PrivateAuditReport.registry_fingerprint` at audit time (`auditor.py:290,350`) and
  gating `run_remediation` on a fingerprint match (`remediation.py:407-409`): a drifted
  registry now fails closed with `reason=registry_drift` and zero artifacts. Confirmed
  live (tampered stored fingerprint → `registry_drift`, exit 2, no new artifact) and by
  the new regression test `test_refusal_registry_drift` (present + passing). A legacy
  report with an empty fingerprint skips the gate and relies on the per-citation drift
  check — a documented, backward-compatible fallback.
- The 5 Info items are acknowledged advisory (see Residual Advisory Debt) — none block the goal.

### Human Verification Required

None. This phase delivers a deterministic projection layer, a CLI verb, two vault
selectors, and a publish-safe subtree entry — no visual, real-time, or external-service
surface. Every observable behavior was covered by automated evidence AND independently
reproduced during this verification (the full `profile set → audit → remediate` path over
the real 14 MB `corpus/index.db`, PII-light stdout + vault-only artifacts, the screening
notice, verbatim-quote agreement, the `no_completed_audit`/`registry_drift` fail-closed
refusals, the AST + runtime no-trust-path proofs, determinism, the 24 Phase-37 tests, the
full suite, publish-safe, and the conformance gate). No human-only item is invented where
automated evidence suffices.

### Residual Advisory Debt (non-blocking)

- **IN-01 (info):** `latest_completed_audit_run` ignores audit scope — a later
  single-factor audit can shadow a full-grid run in the no-`--audit-run-id` default.
  Traceable (`source_audit_run_id` is echoed) and `--audit-run-id` overrides. Advisory.
- **IN-02 (info):** the call-level no-trust-path guard drives only `build_remediation`,
  and the AST check is direct-import-only; a transitive regression via `run_remediation`
  could slip past both. Runtime is currently clean (independently re-confirmed here by a
  booby-trap over `load_registry`+`fingerprint`+`build`). Test-robustness gap, not a live
  defect. Advisory.
- **IN-03 (info):** `check_publish_safe.py`'s comment/docstring enumeration was not
  updated for the new `output/remediation/` subtree; the `VAULT_SUBTREES` tuple is
  authoritative and the scan works (0 violations). Doc drift only. Advisory.
- **IN-04 (info):** `run_remediation` writes JSON then MD as two calls — an I/O failure
  between them could leave a `.json` with no `.md`. Post-build (not a refusal) and mirrors
  the existing `audit_report` writer pattern. Advisory.
- **IN-05 (info):** `remediate` opens (and, for a never-initialized candidate, creates)
  the vault DB before the `no_completed_audit` refusal — consistent with every vault verb;
  the remediation *output* subtree stays empty (the asserted REM-04 invariant). Advisory.

### Gaps Summary

No gaps. All four ROADMAP success criteria (REM-01..04) and all three PLAN must_have
truth sets are satisfied by substantive, wired, data-flowing code proven against the real
14 MB `corpus/index.db` through the live `profile set → audit --all → remediate` path. A
completed audit is projected into a private, corpus-cited fix checklist with exactly one
actionable item per unresolved finding (9 GAP cards → 9 items; 9 N/A → 0), each item
carrying factor, verdict/reason, score impact, the existing grounded citation paired with
its verbatim registry quote, and a deterministic factor-parameterized action template.
The projection is a single trust path: `crawler/remediation.py` imports neither
`searchindex` nor `grounding` (AST + runtime booby-trap), `crs_rules.load_registry` is
pure YAML, `build_remediation` is deterministic (identical `model_dump()` on repeat), and
no volatile CRS literal is inlined (`no_inlined_volatile_rules==[]`). The full checklist
and `ev_` pointers stay vault-only under `output/remediation/`; stdout is a PII-light
summary (no `ev_`, vault-relative path); every rendered artifact carries the
substantiation-screening notice; and `no_completed_audit` / `registry_drift` prerequisites
refuse cleanly (`invalid_input`/exit 2 + reason code) with zero artifacts. The one
code-review Warning (WR-01, audit-time registry drift) is fixed by an auditor-stamped
`registry_fingerprint` and a fail-closed gate in `run_remediation`, re-triggered live and
covered by a passing regression test. Full suite independently reproduced: **798 passed,
1 skipped, 355 subtests passed, 0 failed** (baseline 797 + 1 new WR-01 test; the single
skip is the pre-existing baseline item); publish-safe 0 violations; conformance PASS
SAFE-01..04.

---

_Verified: 2026-07-17T12:55:32Z_
_Verifier: the agent (gsd-verifier)_
