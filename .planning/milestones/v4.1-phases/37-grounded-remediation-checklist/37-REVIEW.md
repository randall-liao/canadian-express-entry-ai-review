---
phase: 37-grounded-remediation-checklist
reviewed: 2026-07-17T08:13:45Z
depth: deep
files_reviewed: 8
files_reviewed_list:
  - crawler/remediation.py
  - crawler/vault.py
  - crawler/cli.py
  - scripts/check_publish_safe.py
  - crawler/tests/test_remediation.py
  - crawler/tests/test_remediation_cli.py
  - crawler/tests/test_remediation_projection.py
  - crawler/tests/test_crs_no_inlined_rules.py
findings:
  critical: 0
  warning: 1
  info: 5
  total: 6
status: resolved
resolution:
  warning_fixed: 1
  info_addressed: 0
  note: "WR-01 (registry drift: remediation re-derived quotes from the current registry without gating on the audit-time registry) fixed by stamping crs_rules.registry_fingerprint(registry) into PrivateAuditReport (additive optional field) and gating run_remediation on a fingerprint match — a drifted registry now fails closed with reason=registry_drift, zero artifacts. New test test_refusal_registry_drift. Info findings acknowledged as advisory (bounded/by-design)."
---

# Phase 37: Code Review Report — Grounded Remediation Checklist

**Reviewed:** 2026-07-17T08:13:45Z
**Depth:** deep (cross-file call-chain + import-graph trace)
**Files Reviewed:** 8
**Status:** issues_found (0 Critical / 1 Warning / 5 Info)

## Summary

Phase 37 (`d2a4538`, `59a1ccc`, `d27e3ab`) adds a pure grounded-remediation projection
(`crawler/remediation.py`), a `vault remediate` CLI verb, two vault helpers, and a
publish-safe subtree entry. I traced the full runtime path — `_cmd_vault_remediate` →
`run_remediation` → `load_audit_run`/`latest_completed_audit_run` → `_load_report` →
`build_remediation`/`_quote_map` → vault write → `to_public_summary` — plus the two
supporting seams it reuses (`audit_report._vault_relative`, `auditor._rule_citation_ids`)
and the trust-path modules it must avoid (`crs_rules`, `searchindex`, `grounding`).

**The change set is correct on every hard constraint the prompt flagged.** Confirmed:

- **Fail-closed ordering (REM-04):** `_load_report` and `build_remediation` both run
  *before* any `mkdir`/`write_text`; every `RemediationError` path (`no_completed_audit`,
  `audit_run_not_found`, `audit_report_unreadable`, `registry_drift`) leaves zero
  artifacts. `_remediation_files() == []` on every refusal is asserted by the CLI tests
  and holds because the write block (remediation.py:405-412) is unreachable on refusal.
- **Path resolution:** `_load_report` anchors `report_relpath` at `vault.root.parent.parent`
  (personal root) — the exact inverse of `audit_report._vault_relative`
  (audit_report.py:79-88) and of where `run_audit` writes (audit_report.py:175-184).
  `resolve_within` is applied on both the read (remediation.py:370) and write
  (remediation.py:406-409) paths; a `..`/absolute/symlink `report_relpath` is a
  `PathEscapeError` (a `ValueError` subclass) caught and downgraded to fail-closed
  `audit_report_unreadable` (remediation.py:373-374).
- **Purity/determinism (REM-03):** `build_remediation` has no id/timestamp/I-O; it walks
  `report.factor_cards` (list) and `card.rule_citation_ids` (list); the only `set` is
  `wanted` in `_quote_map`, used for membership only, never iterated into output. Same
  `(report, registry)` → byte-identical `model_dump()` (proven in tests).
- **No second trust path (REM-03):** `remediation.py` never imports or calls
  `searchindex`/`grounding`; `build_remediation`'s only transitive call is
  `auditors.consumed_factor_ids` (a pure constant lookup) + registry-row iteration.
  `crs_rules.load_registry` (remediation.py:400) is pure `yaml.safe_load` + pydantic
  (crs_rules.py:94-118) — it never reaches `validate_registry`/`grounding.check_answer`.
- **PII boundary (REM-04):** stdout carries only `PublicRemediationSummary.model_dump()`
  (5 scalar/int fields, `extra="forbid"`, `_reject_absolute_path` on the path); item
  detail (factor/verdict/reason/action) routes to **stderr** and is skipped entirely
  under `--json` (cli.py:1207-1211). `ev_` ids and applicant values live only in the
  vault-only JSON/MD. `personal/` is git-ignored (never tracked), and
  `output/remediation/` is now in `VAULT_SUBTREES` as defense-in-depth.
- **SQL:** `load_audit_run` is `?`-bound (vault.py:1209); `latest_completed_audit_run`
  filters `status = 'complete'` with no interpolation (vault.py:1221-1227). No injection
  surface on the user-supplied `--audit-run-id`.
- **Templates (REM-02):** `_action_for` is total (`kind ∈ {gap,at_risk,unpriced}` are all
  `_DEFAULT_ACTION_BY_KIND` keys; unknown `reason_code` falls through cleanly); every
  template is generic screening prose parameterized only by `{factor}` — no CLB level,
  points value, cap, window, or date. The `no_inlined_volatile_rules` gate now includes
  `remediation.py` and passes.
- **No new contract type/exit code:** `RemediationError` is internal and maps to the
  frozen `contract.INVALID_INPUT` / `EXIT_INVALID_INPUT` (cli.py:1199-1202).

Full suite: **797 passed, 1 skipped**; `check_publish_safe.py`: **0 violations**.

The single Warning concerns an *overstated* verbatim-reuse guarantee: the checklist
re-derives quotes from the *current* on-disk registry rather than the audit-time span,
and the drift guard only catches *removed* citation ids — not changed quote text.

## Warnings

### WR-01: Drift guard is incomplete — verbatim spans are re-derived from the current registry, not the audit-time grounding

**File:** `crawler/remediation.py:242-256` (`_quote_map`), `:277-283` (drift check), `:399-403` (`run_remediation` loads current registry); overstated claim at `:12-14`.

**Issue:**
The audit report stores only citation **ids** (`PrivateFactorCard.rule_citation_ids`,
chunk_ids) — never the quotes themselves. So `build_remediation` reconstructs each
"verbatim rule span" by looking the chunk_id up in whatever registry
`crs_rules.load_registry()` reads off disk *at remediate time* (remediation.py:400), then
`_quote_map` picks a quote via `setdefault` (first-in-registry-order wins when several
rows cite the same chunk with different spans, remediation.py:255).

The fail-closed guard (remediation.py:277-283) raises `registry_drift` **only when a cited
chunk_id has no quote at all** in the current registry. It does **not** detect the case
where the chunk_id still resolves but its quote text changed, nor does it verify that the
registry is the same one the audit gated against. `audit_runs.rule_registry_version` is
selected by both `load_audit_run` and `latest_completed_audit_run` (vault.py:1206-1207,
1222-1223) but is **never compared** in `run_remediation`.

Consequences if the registry is edited between `vault audit` and `vault remediate`:
- A rule whose `quote` was re-worded (e.g. corpus re-chunk, typo fix) is presented with
  the **new** span, not the one the audit actually grounded.
- When multiple rows cite the same chunk with different spans, the span shown is whichever
  row appears first in registry order — not necessarily the row behind that verdict.

This contradicts the module's own claim that the span is "already proven verbatim-grounded
**when the audit ran**" (remediation.py:12-14) and REM-03's "reuse already-grounded …
citations without re-grounding." Impact is bounded — the emitted `(id, quote)` pair is
always a *self-consistent, currently-grounded* span (never fabricated or cross-wired), and
determinism holds for a fixed registry — so REM-02's "existing grounded citation + verbatim
rule span" is technically satisfied. But the "same grounding as the audit" guarantee the
docstring asserts is not enforced. (Note: `rule_registry_version` defaults to `"0"` and is
only ever set from tests — vault.py:900-904 — so a naive version compare would be a no-op
in production; a real fix must persist the audit-time span or a content hash.)

**Fix (pick one):**
1. Persist the verbatim quote at audit time so remediation reuses it without re-reading
   the registry — e.g. store `rule_citations: list[{chunk_id, quote}]` on
   `PrivateFactorCard` and project directly in `build_remediation`, dropping the
   `_quote_map` re-derivation entirely; or
2. Tighten the drift guard to fail closed on a *content* mismatch rather than only a
   missing id — e.g. stamp a registry content hash into `audit_runs` at audit time and
   compare it in `run_remediation` before building:
   ```python
   report = _load_report(vault, run_row)
   if registry is None:
       registry = crs_rules.load_registry()
   audit_reg_hash = run_row.get("rule_registry_hash")
   if audit_reg_hash and audit_reg_hash != registry.content_hash():
       raise RemediationError("registry_drift")
   checklist = build_remediation(report, registry)
   ```
   and correct the docstring (remediation.py:12-14) to state the span is reused from the
   *current* registry when no audit-time span is persisted.

## Info

### IN-01: `latest_completed_audit_run` ignores audit scope — a single-factor run can silently shadow a full-grid audit

**File:** `crawler/vault.py:1214-1228`, consumed at `crawler/remediation.py:394-396`.

**Issue:** The default run selection is purely `ORDER BY completed_at DESC, audit_run_id
DESC LIMIT 1`, with no consideration of `factor_id`. If the operator last ran a
single-factor audit (`vault audit --factor core.age`) after a full-grid audit,
`vault remediate` (no `--audit-run-id`) projects only that one card and reports e.g.
"1 remediation item(s)", silently omitting gaps a prior full-grid run surfaced. This is
consistent with REM-01's "from a *selected* completed audit run" and the `source_audit_run_id`
is echoed in the summary, so it is traceable — but it is a completeness footgun.

**Fix:** Either prefer the latest full-grid run (`factor_id = '*full-grid*'`) for the
default, or have the CLI emit a stderr note when the selected run is single-factor (e.g.
`selected single-factor run <id>; pass --audit-run-id for a full-grid run`).

### IN-02: No-second-trust-path proof guards only `build_remediation`, and the AST check is direct-import-only

**File:** `crawler/tests/test_remediation_projection.py:48-82`.

**Issue:** The call-level booby-trap (`_boom`) wraps `grounding.check_answer`,
`searchindex.search`, `searchindex.resolve` and runs **only `build_remediation`** — not
`run_remediation`, whose `crs_rules.load_registry()` and `_load_report` are the paths that
touch the wider module graph. The AST check (`:49-62`) inspects only `remediation.py`'s
*direct* imports; because `remediation → crs_rules → grounding/searchindex` is a transitive
import, a future regression that reached the gate through `run_remediation` would slip past
both guards. The runtime is currently clean (verified: `load_registry` is pure), so this is
a test-robustness gap, not a live defect.

**Fix:** Add a call-level guard that booby-traps the trust path and drives
`run_remediation` end-to-end against a seeded synthetic report (as `test_remediation_cli.py`
already does), and/or assert the trust-path modules are absent from
`sys.modules`-reachable *calls* rather than only direct imports.

### IN-03: `check_publish_safe.py` docstring/comment not updated for the new subtree

**File:** `scripts/check_publish_safe.py:62-72` (comment), `:183-186` (`scan_vault_artifact` docstring).

**Issue:** The functional change (adding `"output/remediation/"` to `VAULT_SUBTREES`,
line 71) is correct and effective, but the explanatory comment block (62-68) and the
`scan_vault_artifact` docstring enumeration (183-186) still list only `output/crs-audit/`
and omit `output/remediation/`. Doc drift only — the tuple is authoritative and the scan
works — but it makes the self-documenting coverage claim inaccurate.

**Fix:** Add `output/remediation/` to the comment at lines 67-68 and to the `(c)` subtree
list at lines 183-185.

### IN-04: Partial-artifact window between the two `write_text` calls

**File:** `crawler/remediation.py:410-412`.

**Issue:** `json_path.write_text(...)` then `md_path.write_text(...)` are two separate
writes. An I/O failure (disk full, permissions) after the JSON write but before the MD
write leaves a `.json` with no matching `.md`. This is not a fail-closed *refusal* (build
already succeeded), and it mirrors the existing `audit_report` writer pattern
(audit_report.py:179-182), so it is pre-existing behavior — but the remediation subtree can
still end up half-populated.

**Fix (optional):** Write both bodies to temp names under the subtree and `os.replace` them
into place, or write MD first and JSON last, so a reader keying off the JSON never sees a
render-less entry. Low priority given the shared pattern.

### IN-05: `remediate` opens (creates) the vault before the `no_completed_audit` refusal

**File:** `crawler/cli.py:1188` (`open_vault`) vs. `crawler/remediation.py:394-396`.

**Issue:** `open_vault` is called before any prerequisite check, and it *creates*
`candidates/<id>/vault.sqlite` + the candidate directory if absent (vault.py:395-401).
Running `vault remediate --candidate <never-initialized>` therefore materializes an empty
vault DB, then refuses with `no_completed_audit`. The remediation *output* subtree stays
empty (the specific REM-04 invariant the tests assert), and this matches how every vault
verb opens/creates the vault, so it is consistent existing behavior — but it is a minor
asymmetry with the audit path, which preflights the corpus index *before* `open_vault`
(cli.py:768-770) specifically to avoid creating DB artifacts on a refusal.

**Fix (optional):** If "refusal creates zero DB artifacts" is desired for `remediate`,
gate on `select_candidate(...) is not None` before `open_vault`, or document that opening
the vault is inherent to querying `audit_runs`. Not required for REM-04 conformance.

---

_Reviewed: 2026-07-17T08:13:45Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
