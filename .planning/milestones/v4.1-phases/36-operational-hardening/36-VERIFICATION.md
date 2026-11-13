---
phase: 36-operational-hardening
verified: 2026-07-17T11:38:58Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification. No prior 36-VERIFICATION.md existed."
---

# Phase 36: Operational Hardening Verification Report

**Phase Goal:** The auditor fails closed and stays trustworthy when grounding prerequisites are missing or corrupt, ships an accurate pinned example, and cannot be greened by low-quality or ambiguous documents.
**Verified:** 2026-07-17T11:38:58Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

Verification was performed goal-backward against the actual codebase and the real
14 MB `corpus/index.db` (present + extraction deps installed in this environment, so
the skip-guarded real-seam tests DO run here), not SUMMARY.md claims. Every refusal
reason code was reproduced through the real `cli.main` `vault audit` path against a
scratch vault under a tempdir; the zero-artifact invariant was checked by counting
`audit_runs`/`factor_verdicts` rows and globbing the output dir directly; the example
grid pin and non-N/A verdicts were reproduced through the real CLI audit; and the two
code-review Warnings (WR-01/WR-02) were re-triggered at runtime to confirm they now
fail closed instead of raising. The full suite was re-run independently
(**778 passed, 1 skipped, 355 subtests passed** in 600.67s — exactly the Phase-35
baseline of 752 + the 26 new Phase-36 tests, with the single skip being the same
pre-existing baseline item, NOT a Phase-36 real-seam test).

### Observable Truths (ROADMAP Success Criteria + PLAN must_haves)

| #   | Truth (requirement) | Status | Evidence |
| --- | ------------------- | ------ | -------- |
| 1 | A missing / empty / unreadable / corrupt / content-drifted corpus index → a stable, PII-free refusal envelope on the frozen `invalid_input` vocabulary plus a specific `reason=<code>` (HARD-01) | ✓ VERIFIED | `index_health.probe_index` (`index_health.py:85-165`) classifies into the CLOSED vocabulary `{ok, index_missing, index_empty, index_unreadable, index_corrupt, index_drifted}`. Reproduced live through `cli.main`: missing→`reason=index_missing`, empty→`reason=index_empty`, corrupt→`reason=index_corrupt`, drifted→`reason=index_drifted`, all `error.type=invalid_input`. `unreadable` reproduced via direct probe (permission-denied dir). Message echoes ONLY the `--db` corpus path — `assertNotIn("ev_", msg)` and no applicant value. |
| 2 | A grounding-prerequisite refusal exits non-zero (2), recommends the index/doctor recovery command, and writes NO audit/remediation/packet/database artifact (HARD-02) | ✓ VERIFIED | Live `vault audit --all --db corpus/NOPE.db` → exit **2**; message names `'corpus-crawler … index corpus/ --db …'` (rebuild) + `'corpus-crawler … doctor'` (verify). Independently confirmed ZERO artifacts after refusal: `audit_runs`=0, `factor_verdicts`=0, `output/crs-audit` glob empty. Preflight `_require_readable_index(args, args.db)` runs at `cli.py:1121` BEFORE `vault.open_vault` at `:1125`. Healthy `--db corpus/index.db` still runs (`ok:true`, exit 0, `run_id` present). |
| 3 | The shipped synthetic example uses canonical dotted factor ids, is pinned to the live grid, and produces applicable non-`N/A` verdicts through the real CLI path (HARD-03) | ✓ VERIFIED | All 6 `factor_id`s in `crs-profile.example.yaml` are dotted + members of `auditors.FULL_GRID_FACTORS` with `factor_group == auditors.FACTOR_GROUP[id]` (independently checked). Live `profile set` + `vault audit --all --db corpus/index.db`: `core.age`/`core.education`/`core.language.first` → **GAP** (applicable, non-N/A); `spouse.education` → **N/A** `not_applicable` (single-applicant, as designed). Pinned unguarded by `test_example_profile_pinned.py`. |
| 4 | Rotated / low-text / password-protected / ambiguous-date fixtures remain quarantined and cannot green or contaminate another factor through the real import→extract→confirm→audit seam (HARD-04) | ✓ VERIFIED | `test_adversarial_extraction_seam.py` drives the ACTUAL `import_document → extract_document → confirm_value → run_full_audit_report` path: 6/6 pass here (NOT skipped). Rotated page → `rotated` flag + all values `low_quality` + `audit_eligible_values==[]` + verdict≠SUBSTANTIATED; low-text → `low_quality`; unparseable pdf → `password_protected`, no eligible value; ambiguous DOB (05/06/1994) → `ambiguous`, not eligible; no cross-factor contamination (every grid factor's `audit_eligible_values==[]`); confirm AND correct on an ambiguous value stays not-eligible (quality gate not bypassed). |

**Score:** 4/4 truths verified (each PLAN's detailed sub-truths also verified — see below).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/index_health.py` | `IndexHealth` dataclass + read-only `probe_index` + PII-free `message()` over the closed reason-code vocabulary | ✓ VERIFIED | 166 lines. Frozen dataclass (`:59-82`); `probe_index` opens `file:<db>?mode=ro` (`:116`), never creates a 0-byte DB (`test_missing_path…creates_nothing` passes); `message()` (`:70-82`) names `index`/`doctor`, echoes only `--db`. Contains `index_drifted`. |
| `crawler/cli.py` | `_require_readable_index` refusal helper + preflight call at the top of `_cmd_vault_audit` | ✓ VERIFIED | Helper at `:760-776` returns `invalid_input`/exit-2 (or `None`); called at `:1121` `refusal = _require_readable_index(args, args.db)` before `open_vault` (`:1125`); `if refusal is not None` (identity, not truthy — an exit 0 can't be swallowed). |
| `personal.example/crs-profile.example.yaml` | Re-keyed synthetic example using canonical dotted ids + matching groups | ✓ VERIFIED | 6 dotted ids (`core.age`, `core.education`, `core.language.first`, `spouse.education`, `transfer.education_language`, `additional.nomination`), all synthetic/PII-free; publish-safe 0 violations. |
| `crawler/tests/test_index_health.py` | Reason-code unit table over every state (min 60 lines) | ✓ VERIFIED | 173 lines, 12 tests: every reason code + HIGH-1 row-malformation + WR-01 permission-denied + WR-02 non-str-cell + read-only/no-create + PII-free message. 12/12 pass. |
| `crawler/tests/test_audit_index_refusal.py` | CLI refusal + exit code + no-artifact proof (min 40 lines) | ✓ VERIFIED | 121 lines, 4 tests: missing/empty/corrupt refuse cleanly (type+exit+reason+recovery+`ev_`-free+0 `audit_runs`+0 report files) + real-index positive control (runs here). 4/4 pass. |
| `crawler/tests/test_example_profile_pinned.py` | Grid-membership pin + non-N/A real-audit proof (min 50 lines) | ✓ VERIFIED | 100 lines, 4 tests: id⊆grid (unguarded), group agreement (unguarded), core factor present, real-audit non-N/A (runs here). 4/4 pass. |
| `crawler/tests/test_adversarial_extraction_seam.py` | Real-seam adversarial quarantine + no-cross-factor regressions (min 90 lines) | ✓ VERIFIED | 233 lines, 6 tests through the real seam, all run + pass here (not skipped). |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `cli._cmd_vault_audit` | `index_health.probe_index` | `_require_readable_index` preflight before `open_vault` | ✓ WIRED | `cli.py:1121-1123` precedes `:1125`; refusal returns exit 2 with envelope. |
| `index_health.py` | `searchindex.chunk_sha` | Content-drift fingerprint recompute | ✓ WIRED | `import chunk_sha` (`:95`), used `chunk_sha(text) != sha` (`:155`) over a bounded 64-row sample. |
| `_require_readable_index` | `contract` | `INVALID_INPUT` / `EXIT_INVALID_INPUT` | ✓ WIRED | `contract.INVALID_INPUT="invalid_input"`, `EXIT_INVALID_INPUT=2` (`contract.py:48,57`); no new error type / exit constant. |
| `crs-profile.example.yaml` | `auditors.FULL_GRID_FACTORS` / `FACTOR_GROUP` | `factor_id ⊆ grid` + group agreement pin | ✓ WIRED | All 6 ids on grid, groups match; pinned by unguarded tests. |
| `test_adversarial_extraction_seam` | `extraction` quality gate + `run_full_audit_report` | Real import→extract→confirm→audit seam | ✓ WIRED | `confirm_value` never mutates `quality_flag`; `is_audit_eligible` gates on `quality_flag=='ok'`; both re-run here. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `probe_index` result | `IndexHealth.status` | Live filesystem + `mode=ro` sqlite reads of the real/scratch index | Yes — distinct codes reproduced live (missing/empty/corrupt/drifted/ok), not hardcoded | ✓ FLOWING |
| refusal envelope | `error.type` / `error.message` | `health.message(db)` on a non-ok probe | Yes — reason token varies with fault class; recovery hint present | ✓ FLOWING |
| example audit verdicts | `factor_cards[*].verdict` | `run_full_audit_report` over real `corpus/index.db` on the loaded example | Yes — GAP/N/A per factor, not empty/static | ✓ FLOWING |
| adversarial quarantine | `quality_flag` / `audit_eligible_values` | Real `extract_document` of generated adversarial PDFs | Yes — `low_quality`/`ambiguous`/`password_protected` flags + empty eligibility | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Missing `--db` refuses on frozen contract | `vault audit --all --db corpus/NOPE.db` | `ok:false`, `invalid_input`, exit **2**, `reason=index_missing`, names index/doctor | ✓ PASS |
| Empty / corrupt / drifted `--db` reason codes | live CLI over 0-byte / non-sqlite / tampered-sha db | `reason=index_empty` / `index_corrupt` / `index_drifted`, all exit 2 | ✓ PASS |
| Zero artifacts on refusal | `audit_runs`/`factor_verdicts` count + `output/crs-audit` glob | 0 rows, 0 files | ✓ PASS |
| Healthy real index unaffected | `vault audit --all --db corpus/index.db` | `ok:true`, exit 0, `run_id` present | ✓ PASS |
| WR-01 permission-denied dir fails closed | direct `probe_index` on locked-dir index | `index_unreadable` (NO exception) | ✓ PASS |
| WR-02 NULL/BLOB text cell fails closed | direct `probe_index` on non-str `text` | `index_corrupt` for both (NO exception) | ✓ PASS |
| Example grid pin + non-N/A | live `profile set` + `vault audit --all` | 6/6 ids on grid+group; core factors GAP, spouse N/A | ✓ PASS |
| Phase-36 test files | `pytest test_index_health test_audit_index_refusal test_example_profile_pinned test_adversarial_extraction_seam -v` | 26 passed, 0 skipped (real-seam ran) | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared or implied by this phase's
plans/summaries. Verification uses the phase's automated pytest suites +
`scripts/run_conformance.py` + `scripts/check_publish_safe.py` + live `cli.main`
reproductions, all run independently above.

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| conformance gate (release-gate driver) | `.venv/bin/python scripts/run_conformance.py` | exit 0, `PASS — SAFE-01, SAFE-02, SAFE-03, SAFE-04` (51 passed) | PASS |
| publish-safe scanner | `.venv/bin/python scripts/check_publish_safe.py` | exit 0, 0 violations (323 tracked files) | PASS |
| full suite | `.venv/bin/python -m pytest crawler/tests -q` | 778 passed, 1 skipped, 355 subtests, 0 failed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| HARD-01 | 36-01 | Missing/empty/unreadable/corrupt/drifted index → stable PII-free `invalid_input` refusal + reason code | ✓ SATISFIED | Truth 1 + `probe_index` closed vocabulary + live reproduction of every fault class. |
| HARD-02 | 36-01 | Refusal exits non-zero (2), recommends index/doctor, writes zero artifacts | ✓ SATISFIED | Truth 2 + exit 2 + recovery hint + 0 `audit_runs`/report files + preflight-before-open_vault. |
| HARD-03 | 36-02 | Example uses canonical dotted ids, pinned to grid, non-N/A via real CLI | ✓ SATISFIED | Truth 3 + 6/6 ids on grid + real CLI GAP verdicts. |
| HARD-04 | 36-03 | Adversarial fixtures stay quarantined, no green/contamination through the real seam | ✓ SATISFIED | Truth 4 + 6 real-seam regressions run + pass here. |

All four v4.1 HARD requirements map to Phase 36 exactly once (REQUIREMENTS.md /
ROADMAP.md), each claimed by a plan (36-01→HARD-01/02, 36-02→HARD-03, 36-03→HARD-04)
and implemented. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | — | No `TBD`/`FIXME`/`XXX` debt markers in any phase-modified source/test/data file | — | Completion is auditable. |

The two `placeholder` grep hits are legitimate, not stubs: `test_index_health.py:148`
`db.write_bytes(b"placeholder")` (arbitrary bytes for the WR-01 locked-dir fixture),
and `crs-profile.example.yaml:5` ("illustrative placeholder" comment describing the
deliberately-synthetic example). The fail-closed `IndexHealth(...)` early returns are
intentional refusal semantics (verified by tests + live runs), not empty handlers.

### Code Review Status (WR-01 / WR-02)

- 36-REVIEW.md: **0 Critical, 2 Warning, 4 Info** — resolution `resolved` (both Warnings fixed).
- **WR-01** (pre-open `is_file()`/`stat()` unguarded → `PermissionError`/`FileNotFoundError`
  on a permission-denied parent dir / TOCTOU race) is **FIXED** at `index_health.py:98-111`
  (try/except → `index_missing` on `FileNotFoundError`, `index_unreadable` on `OSError`).
  Independently re-triggered at runtime: locked-dir index → `index_unreadable`, no traceback.
  Regression test `test_permission_denied_parent_is_unreadable_not_exception` present + passing.
- **WR-02** (drift loop `chunk_sha(text)` raised `AttributeError`/`TypeError` on a NULL/BLOB
  `text` cell past the `DatabaseError`-only guard) is **FIXED** at `index_health.py:149-160`
  (`if not isinstance(text, str): return index_corrupt`, plus broadened
  `except (sqlite3.DatabaseError, TypeError, ValueError)`). Re-triggered at runtime:
  BLOB cell → `index_corrupt`, NULL cell → `index_corrupt`, no traceback.
  Regression test `test_non_text_cell_is_corrupt_not_exception` present + passing.
- The 4 Info items are acknowledged advisory (see Residual Advisory Debt) — none block the goal.

### Human Verification Required

None. This phase delivers deterministic backend fail-closed preflight logic, a
CLI refusal contract, a grid-pinned data example, and extraction-quarantine
regressions — no visual, real-time, or external-service surface. Every observable
behavior was covered by automated evidence AND independently reproduced during this
verification (live CLI refusals across all five fault classes, zero-artifact counts,
runtime WR-01/WR-02 re-triggers, real-CLI example audit, the 26 Phase-36 tests, the
full suite, publish-safe, and the conformance gate). No human-only item is invented
where automated evidence suffices.

### Residual Advisory Debt (non-blocking)

- **IN-01 (info):** the `mode=ro` URI at `index_health.py:116` is built by naive
  string interpolation (`f"file:{p}?mode=ro"`); a `--db` path containing `?`/`#`
  mis-parses. Pre-existing shared idiom (matches `searchindex.resolve`), operator-
  controlled path, default `corpus/index.db` safe. Advisory.
- **IN-02 (info):** `test_audit_index_refusal.py:80` `assertIn("index", msg)` is
  partially vacuous (the word "index" also appears in "corpus index unusable" /
  "reason=index_missing"). The `doctor` assertion (`:81`) is unique and sound; the
  live refusal message DOES carry the full `index corpus/ --db …` recovery command
  (verified above). Advisory hardening only.
- **IN-03 (info):** HARD-03/HARD-04 real-path proofs are `skipUnless(corpus/index.db
  [and extraction deps])`. They RAN and PASSED in this environment; on a fresh
  clone/CI without the git-ignored index they SKIP (a green suite there is structural
  only). Acknowledged trade-off; flagged so a release gate does not mistake a skip
  for a pass.
- **IN-04 (info):** the password-protected quarantine test asserts the
  `password_protected` flag for a truncated/unparseable PDF (a label misnomer owned
  by `extraction.py`, outside this diff). The quarantine outcome (no eligible value,
  verdict≠SUBSTANTIATED) is still sound. Advisory.

### Gaps Summary

No gaps. All four ROADMAP success criteria (HARD-01..04) and all three PLAN
must_have truth sets are satisfied by substantive, wired, data-flowing code proven
against the real 14 MB `corpus/index.db` and the real import→extract→confirm→audit
seam. A missing/empty/unreadable/corrupt/drifted index yields a stable, PII-free
`invalid_input` refusal carrying a specific `reason=<code>` token, exits 2, names the
`index`/`doctor` recovery commands, and — because the preflight runs before
`open_vault` — writes zero `audit_runs`/`factor_verdicts`/report artifacts; the
healthy index is unaffected. The shipped example is re-keyed to canonical dotted grid
ids (all 6 pinned to `FULL_GRID_FACTORS` with matching groups) and produces
applicable non-N/A (GAP) verdicts through the real CLI. Rotated / low-text /
password-protected / ambiguous-date fixtures stay quarantined and cannot green or
contaminate another factor, with confirm/correct unable to bypass the quality gate.
Both code-review Warnings (WR-01 pre-open OS errors, WR-02 non-str text cell) are
fixed and independently re-triggered at runtime, each with a passing regression test;
no Critical/open-Warning finding remains. Full suite independently reproduced:
**778 passed, 1 skipped, 355 subtests passed** (baseline 752 + 26 new Phase-36 tests;
the single skip is the pre-existing baseline item, not a Phase-36 real-seam test).

---

_Verified: 2026-07-17T11:38:58Z_
_Verifier: the agent (gsd-verifier)_
