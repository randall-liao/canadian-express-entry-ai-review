---
phase: 43-enhanced-noc-work-duty-review-worksheet
verified: 2026-07-19T14:47:50Z
status: passed
score: 14/14 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
  note: "Initial verification — no previous VERIFICATION.md existed."
---

# Phase 43: Enhanced NOC Work-Duty Review Worksheet — Verification Report

**Phase Goal:** Give the applicant a structured, cited NOC-2021 duty worksheet plus a
per-duty human confirmation surface that feeds MEC's skilled-work criterion and the CRS
work factor — with no automated semantic entailment, capped at `AT-RISK` until a human
confirms.
**Verified:** 2026-07-19T14:47:50Z
**Status:** passed
**Re-verification:** No — initial verification

## Methodology

Goal-backward, adversarial. SUMMARY/REVIEW claims were treated as leads, not evidence.
Every truth was checked against the actual code at four levels (exists → substantive →
wired → data-flows) and, for runnable behavior, reproduced end-to-end. Independently
executed against the pinned `corpus/index.db` (376 NOC-2021 groups) and a throwaway
vault:

- **Focused NOC suite** (`test_noc_review.py`, `test_noc_review_cli.py`,
  `test_noc_overflow_regression.py`, `test_conformance_v5_noc_no_auto_green.py`,
  `test_crs_no_inlined_rules.py`): **72 passed, 405 subtests** (14.2s).
- **Real 376-group scan** (`test_all_376_noc_groups_emit_source_bullets_and_ground`):
  **1 passed, 376 subtests** — byte-for-byte source-bullet parity + every citation
  fragment grounds against its sha-validated chunk + ≥2 multi-chunk duties exercised.
- **WR-01 source-unavailable slice** (`TestNocSourceUnavailableHermetic` +
  `TestNocSourceUnavailableCli`): **11 passed, 5 subtests**.
- **Full crawler suite** (`pytest crawler/`): **1098 passed, 2 skipped, 873 subtests**
  (0:17:34) — no regressions anywhere.
- **Conformance gate** (`scripts/run_conformance.py`): **PASS** (82 tests, SAFE-01…08).
- **Publish-safe gate** (`scripts/check_publish_safe.py`): **PASS** (431 tracked files,
  0 violations).
- **Live CLI reproduction** in a throwaway vault (worksheet → confirm-all → review →
  idempotent regen; absent/source-missing refusals).
- **Frozen-surface byte-identity** verified via `git diff` across the FULL phase span
  (`9a21bfa^..edc09c4`), not just the working tree.

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
| -- | ----- | ------ | -------- |
| 1  | **[SC1]** Applicant can view a structured, cited worksheet of the grounded NOC-2021 lead statement, main duties, and employment requirements, resolved from the corpus with resolvable citations | ✓ VERIFIED | `resolve_noc_spans` classifies chunks by EXACT section breadcrumb (lead / Main duties / Employment requirements), never positional; every span via frozen sha-validated `searchindex.resolve`, never `search()`/BM25. Live CLI on real NOC 72400 → 18 duties + lead, `citations=[#001,#002,#003,#004]` (resolvable chunk_ids). 376-group scan grounds every fragment. |
| 2  | **[SC2]** Applicant can confirm, per duty, whether their claimed work performed that duty; each confirmation captured as a vault field under the extraction-quarantine (confirm/correct/reject, staleness-keyed) | ✓ VERIFIED | Values born `confirmation_status="pending"` on the inert `review.noc` factor (live: 19 pending after generate). Confirm flows through the shipped `vault confirm --value-id <one> --decision {confirm,correct,reject}` — singular required arg (no bulk path). Staleness-keyed via shipped 5-key `is_audit_eligible` + Layer-2 corpus drift. |
| 3  | **[SC3]** Duty-review verdict stays `AT-RISK` until human confirms; can never reach `SUBSTANTIATED` by automated matching; unconfirmed/partial/stale remain `AT-RISK`/`GAP` | ✓ VERIFIED | `review_noc_duties` is STRUCTURALLY closed to `{AT-RISK,GAP,N/A}` (no SUBSTANTIATED branch, no score field). Live: all 18 duties+lead confirmed → `("AT-RISK","duty_review_manual")`, confirmed 18/18, STILL not green. Conformance sweep of 10 input classes asserts never-SUBSTANTIATED + `confirmed_count ≤ duty_count`. |
| 4  | Exact source-structured section parsing (section-classified retrieval + authoritative structural source parse) | ✓ VERIFIED | `_source_main_duty_items` reads the co-located `noc-2021/noc-{code}.md` SOURCE (contained via `paths.resolve_within`, frontmatter-validated `source_type==noc` + `noc_code==code`), each physical `- ` line = ONE verbatim item; grouped headers kept whole (72410 = 17 items, not 18); only boilerplate dropped. |
| 5  | Index-grounded multi-citations across all 376 groups | ✓ VERIFIED | 376-subtest scan: emitted items == source bullets byte-for-byte; every `{chunk_id,quote}` fragment `quote_is_grounded` in its own sha-validated chunk; fragments cover full item in order; boundary-split duties (11202/31100) carry two grounded citations. `total_multi ≥ 2` enforced. |
| 6  | Stable id/hash + idempotent, state-preserving regeneration | ✓ VERIFIED | `duty_id=f"{code}:{ordinal:02d}"` (source ordinal, not fragile chunk ordinal); `duty_sha=chunk_sha(full item)`. Live: exact rerun → byte-identical result JSON, same `doc_id`, 19 values / 1 doc unchanged; after confirming all, regen preserves 19 confirmed / 0 new rows. `_existing_duty_values` dedup is read-only (no bulk status mutation). |
| 7  | Dedicated inert `review.noc` FK-parent isolation (never `core.work`) | ✓ VERIFIED | `_review_noc_factor()` seeded once via `upsert_profile_factor` as the enforced FK parent; all duty/lead values link `factor_id="review.noc"`. `review.noc` absent from `FULL_GRID_FACTORS` and `_REGISTRY`. Runtime isolation test: `core.work` card byte-identical before/after confirmations. |
| 8  | Born-pending + per-duty one-at-a-time confirm + two-layer staleness + current-key dedup + candidate scoping | ✓ VERIFIED | Layer 1 = shipped 5-key `is_audit_eligible`; Layer 2 = `_layer2_fresh` re-resolve + re-ground of every citation fragment. Current-key rebuild from live split → each `duty_id` counts at most once (`changed_sha` → confirmed_count 1). All three read helpers thread explicit `candidate_id` via `JOIN documents … WHERE candidate_id=?`. |
| 9  | Vault-only cited artifact + PII-light CLI envelope | ✓ VERIFIED | Artifact written under `vault/candidates/<c>/output/noc-worksheets/noc-<code>.md` via `resolve_within` (never `corpus/`); confirmed on disk. `--json` stdout carries only `{noc_code,duty_count,value_ids,worksheet_doc_id,citations}` / closed `PUBLIC_FIELDS`; scanned stdout has no `/tmp`, `/home`, `ev_`, `candidates/`, `.sqlite`, `raw_text`, or `quote`. Human duty detail → stderr only. |
| 10 | Source-unavailable typed fail-closed (distinct reason, zero artifacts, no path leak) | ✓ VERIFIED | `NocSourceUnavailable` raised (never returned) for missing/uncontained/unreadable/frontmatter-drifted/ungroundable source; generator → `reason="noc_source_unavailable"` (distinct from `unresolved_noc`); sidecar → `("AT-RISK","noc_source_unavailable")`; CLI → `invalid_input`/exit 2 with "refresh/rebuild the corpus (NOT a bad --noc-code)". 11 hermetic tests pass; message carries code+reason only, `raise … from None` prevents path chaining. |
| 11 | Sidecar is inert / never-green | ✓ VERIFIED | Only `crawler/cli.py` imports the NOC modules (2 verbs); no auditor/`crs_audit`/envelope importer. Not registered as a decider (`review.noc` → fail-closed default), not in `FULL_GRID_FACTORS`, no NOC id in any `PublicAuditEnvelope`. Docstring confirms "NO Phase-45 / MEC wiring here". |
| 12 | Frozen surfaces byte-identical (`core.py`/`crs_audit.py`/`models/audit.py`/`auditors/__init__.py`) | ✓ VERIFIED | `git diff --quiet 9a21bfa^..edc09c4` clean for all four across the FULL phase span. CRS total / `PublicAuditEnvelope` shape untouched; runtime `core.work` card proven byte-identical over confirmed `review.noc` values. |
| 13 | Duty-review remediation reason alias (no dup template, no volatile literal) | ✓ VERIFIED | `_REASON_ALIASES` maps `duty_review_manual → unresolved_noc` and `noc_source_unavailable → unresolved_noc`, reusing the shipped `unresolved_noc` action; no duplicate template. Both NOC modules covered by the no-inlined-volatile static gate (positive controls bite). |
| 14 | No model/scoring/semantic matching · no new deps · no Phase-45 wiring | ✓ VERIFIED | Grep of both NOC modules: no numpy/sklearn/torch/transformers/embedding/cosine/vector/nli/entail/similarity/bm25/overlap/fuzz/difflib in code (only docstrings stating their ABSENCE). Imports are stdlib + pre-existing `yaml` + internal crawler. `pyproject.toml`/`poetry.lock` unchanged in-phase. No MEC module / consumer exists. |

**Score:** 14/14 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/noc_worksheet.py` | Exact-NOC retrieval, structural per-duty split, vault-only cited worksheet, inert review.noc FK seed, born-pending capture, idempotent regen | ✓ VERIFIED | 767 net LOC; wired via 2 CLI verbs + sidecar; live output correct; 376-group scan grounds all fragments. |
| `crawler/noc_review.py` | Inert AT-RISK/GAP/N/A roll-up, two-layer staleness, current-key dedup, closed PII-light dict | ✓ VERIFIED | 323 net LOC; structurally never-green; imported only by CLI; sweep of 10 classes passes. |
| `crawler/cli.py` (`noc-worksheet`/`noc-review`) | PII-light envelopes, index preflight, vault-only detail, one-at-a-time confirm reuse | ✓ VERIFIED | Both verbs registered; index preflight before compute; stdout PII-light; refusals zero-artifact. |
| `crawler/remediation.py` | `duty_review_manual`/`noc_source_unavailable` → `unresolved_noc` alias | ✓ VERIFIED | `_REASON_ALIASES` present; no dup template; gate-clean. |
| `crawler/models/vault.py` | `noc_duty` + `noc_lead_statement` FieldName members, no migration | ✓ VERIFIED | +6 additive Literal lines; `extracted_values` DDL untouched (no CHECK/migration). |
| `crawler/searchindex.py` | Read-only `relpath_sections` TOC helper (additive) | ✓ VERIFIED | +37 additive LOC; frozen `resolve`/`chunk_sha`/indexer untouched; param-bound, ro-mode. |
| `crawler/tests/test_conformance_v5_noc_no_auto_green.py` | Never-green sweep + frozen byte-identity + inertness + core.work isolation | ✓ VERIFIED | Real, non-vacuous; 10-class sweep + git-diff freeze + runtime isolation; all pass. |
| `crawler/tests/test_crs_no_inlined_rules.py` | `_EXPORT_MODULES` scan covers both NOC modules | ✓ VERIFIED | Both modules in `_EXPORT_MODULES`; positive controls bite. |
| `crawler/tests/test_noc_review.py` / `_cli.py` / `test_noc_overflow_regression.py` | Retrieval/split/citation/fail-closed/vault-only/idempotency/376-scan coverage | ✓ VERIFIED | 72 passed / 405 subtests focused; 376-subtest real-corpus scan green. |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| `noc_worksheet.generate_worksheet` | `searchindex.resolve` / `relpath_sections` | exact chunk_id lookup (never `search()`) | ✓ WIRED |
| `noc_worksheet` | `vault.upsert_profile_factor` | seed inert `review.noc` FK parent once | ✓ WIRED |
| `noc_worksheet` | `vault.add_extracted_value` | born-pending value on `review.noc` (never `core.work`) | ✓ WIRED |
| `noc_worksheet` | `paths.resolve_within` | vault-only artifact write | ✓ WIRED |
| `noc_worksheet._existing_duty_values` | `extracted_values` (review.noc) via `documents.candidate_id` | `(duty_id,duty_sha)` dedup, read-only | ✓ WIRED |
| `noc_review` | `vault.audit_eligible_values` / `is_audit_eligible` | Layer-1 gate on `review.noc`, candidate-scoped | ✓ WIRED |
| `noc_review._layer2_fresh` | `searchindex.resolve` + `grounding.quote_is_grounded` | Layer-2 corpus-drift re-check | ✓ WIRED |
| `noc_review._current_key_sets` | `noc_worksheet.split_duties` | rebuild current `(duty_id,duty_sha)` key set | ✓ WIRED |
| `cli._cmd_vault_noc_worksheet/review` | `generate_worksheet` / `review_noc_duties` | CLI drives frozen libs | ✓ WIRED |
| `cli` | `_require_readable_index` | index preflight (zero-artifact refusal) | ✓ WIRED |
| conformance test | `auditor.audit_factor (core.work)` | before/after byte-identity over confirmed review.noc | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| worksheet CLI envelope | `duty_count`, `value_ids`, `citations` | `generate_worksheet` → `resolve_noc_spans` (real `corpus/index.db`) + source parse | Yes — 18 duties + 19 values + 4 chunk_id citations on live NOC 72400 | ✓ FLOWING |
| noc-review dict | `status`, `confirmed_count`, `citations` | `review_noc_duties` → vault reads + live split | Yes — 18/18 confirmed → AT-RISK/duty_review_manual | ✓ FLOWING |
| worksheet artifact body | rendered lead/duties/reqs | verbatim sha-validated spans | Yes — written under vault, cited | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Cited worksheet for real NOC | `vault noc-worksheet --noc-code 72400 --db corpus/index.db` | `duty_count=18`, 19 value_ids, citations `#001..#004`, exit 0 | ✓ PASS |
| Idempotent rerun | rerun same worksheet | byte-identical result JSON, same `doc_id`, 1 doc / 19 values (no dup) | ✓ PASS |
| Confirmed-state preserved on regen | confirm-all → regen | 19 confirmed preserved, 0 new rows | ✓ PASS |
| Never-green terminal | confirm all 18+lead → `vault noc-review` | `AT-RISK` / `duty_review_manual`, 18/18, NOT SUBSTANTIATED | ✓ PASS |
| Fail-closed absent NOC | `vault noc-worksheet --noc-code 99999` | `invalid_input`/exit 2, `reason=unresolved_noc`, zero artifacts | ✓ PASS |
| Fail-closed review absent | `vault noc-review --noc-code 99999` | `N/A` / `no_worksheet`, exit 0 | ✓ PASS |
| PII-light stdout | scan review JSON | no path / `ev_` / `raw_text` / `quote` | ✓ PASS |
| Per-duty confirm only | `vault confirm --help` | single required `--value-id` + `--decision`; no bulk path | ✓ PASS |
| Artifact vault-only | locate `noc-72400.md` | under `vault/.../output/noc-worksheets/`, none under `corpus/` | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| Conformance gate | `scripts/run_conformance.py` | 82 passed; "conformance gate: PASS — SAFE-01…08" | ✓ PASS |
| Publish-safety | `scripts/check_publish_safe.py` | 431 files, 0 violations | ✓ PASS |
| Focused NOC suite | `pytest` (5 NOC files) | 72 passed, 405 subtests | ✓ PASS |
| Real 376-group scan | `pytest …test_all_376_noc_groups…` | 1 passed, 376 subtests | ✓ PASS |
| WR-01 source-unavailable | `pytest TestNocSourceUnavailable{Hermetic,Cli}` | 11 passed, 5 subtests | ✓ PASS |
| Full crawler suite | `pytest crawler/` | 1098 passed, 2 skipped, 873 subtests (0:17:34) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| ----------- | -------------- | ----------- | ------ | -------- |
| NOC-01 | 43-01, 43-03 | View structured, cited grounded NOC-2021 worksheet with resolvable citations | ✓ SATISFIED | Truths 1,4,5,9; 376-group scan; live CLI |
| NOC-02 | 43-01, 43-02, 43-03 | Per-duty human confirmation as staleness-keyed vault field; no semantic/keyword-overlap scoring | ✓ SATISFIED | Truths 2,6,8,14; born-pending + one-at-a-time confirm; no-scoring scan |
| NOC-03 | 43-02, 43-04 | Verdict stays AT-RISK; never SUBSTANTIATED by automation; partial/stale → AT-RISK/GAP | ✓ SATISFIED | Truths 3,10,11,12; never-green sweep; frozen isolation; live all-confirmed → AT-RISK |

No orphaned requirements — REQUIREMENTS.md maps only NOC-01/02/03 to Phase 43, all declared across plans and marked Complete.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` in any phase-modified source | — | None — clean |

`return None` occurrences in the NOC modules are all deliberate, commented fail-closed
refusals (malformed code / absent section / drift), not stubs. The final code review
(`43-REVIEW.md`) records **0 Blocker, 0 Warning, 6 Info** (all deferrable
docstring/cosmetic items IN-01…IN-06, none reachable/behavioral). No blocker
anti-patterns.

### Human Verification Required

None. All three success criteria are deterministic and were verified programmatically
(376-group byte-for-byte grounding, structural never-green sweep, live confirm-all →
AT-RISK, idempotency, fail-closed refusals) — the strongest available evidence is the
independently-reproduced real-corpus scan, not a subjective judgment. There is no UI
surface; the worksheet is a text artifact whose content is checked verbatim against the
corpus source. No `<verify><human-check>` blocks were deferred by the planner. Per the
deterministic coverage, no end-of-phase UAT is warranted.

### Gaps Summary

No gaps. All 14 must-haves (3 ROADMAP success criteria + 11 plan-level invariants)
verified at the code, wiring, and behavioral levels. The phase goal — a grounded, cited
NOC-2021 duty worksheet with a per-duty human confirmation surface, capped at `AT-RISK`
with zero automated semantic entailment and full isolation from the frozen `core.work`
audit / CRS total / public envelope — is achieved. Frozen surfaces are byte-identical
across the entire phase span; no new dependencies; no Phase-45/MEC wiring; publish-safe
and v4.x conformance gates green; full suite green with no regressions.

---

_Verified: 2026-07-19T14:47:50Z_
_Verifier: the agent (gsd-verifier)_
