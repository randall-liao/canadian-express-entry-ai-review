---
phase: 30-extraction-quarantine-field-confirmation
verified: 2026-07-06T08:20:25Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run `corpus-crawler vault extract --candidate demo --document-id <id>` then `corpus-crawler vault fields --candidate demo` against a synthetic PDF, and separately `corpus-crawler --json vault fields --candidate demo`."
    expected: "The plain terminal (stderr) view legibly shows, for each field: raw value, normalized value, source page/crop reference, affected CRS factor, and the profile claim. The `--json` stdout envelope contains ONLY PII-light summaries (no raw/normalized value, no path/bbox) and passes the five-key envelope check."
    why_human: "Planner-deferred `<human-check>` on an `auto` task (30-03-PLAN.md:182). The verifier confirmed the exact string content programmatically (build_field_view returns all five facets; format_field_view_human renders them; --json summary is PII-light; raw value '8.5' absent from --json stdout), but the final visual/UX confirmation of the interactive terminal rendering is a human eyeball check (phase carries UI hint: yes)."
---

# Phase 30: Extraction Quarantine & Field Confirmation Verification Report

**Phase Goal:** Applicant can turn vault documents into field-level confirmed evidence while all automated extraction remains quarantined until reviewed.
**Verified:** 2026-07-06T08:20:25Z
**Status:** human_needed (all 5 success criteria VERIFIED in code; 1 planner-deferred visual/UX confirmation remains)
**Re-verification:** No — initial verification

## Goal Achievement

Every roadmap success criterion was verified against the **shipped code** — not the SUMMARY narrative — via (a) direct inspection of the trust logic, (b) an independent synthetic-data proof of the SC3 status×quality matrix and the SC4 five-key staleness, (c) a real end-to-end `extract→fields→confirm` loop through the actual CLI + engine on a synthetic PDF (real pypdfium2 render + pdfminer text), and (d) live `doctor` + `check_publish_safe.py` runs. All data used was synthetic/FAKE.

### Observable Truths

| #   | Truth (ROADMAP Success Criterion) | Status | Evidence |
| --- | --------------------------------- | ------ | -------- |
| 1 | Extraction renders/reads vault documents → structured fields only as `pending` vault values (scores, dates, credentials, NOC/TEER, hours, duration, issuer) | ✓ VERIFIED | Live CLI e2e: `vault extract` on a synthetic 3-page language-test PDF rendered **3 pages** (never page-one-only), read embedded text, and proposed **8 fields**, **all `confirmation_status=pending`** and **none `audit_eligible`**. `_FIELD_SPECS`/`_TEST_TYPE_RE` (extraction.py:163-205) cover test_type/scores/dates/credential/eca/NOC/TEER/hours/duration/issuer/nomination. `add_extracted_value` FORCES `'pending'` on every insert (vault.py:749; proven: born status = `pending`). |
| 2 | Applicant can confirm/correct/reject each field, seeing raw value, normalized value, source page/crop, affected CRS factor, profile claim | ✓ VERIFIED (see human item) | `confirm.build_field_view` (confirm.py:28-87) returns all five facets; live e2e view: `raw_value='8.5'`, `normalized_value=8.5`, `image_relpath='files/rendered/…/page-0001.png'`+`bbox`, `factor_id='core_lang'`/`factor_group`, `claimed_level='CLB 9'`/`claimed_value`. `vault confirm` acts on exactly one `--value-id` (decisions confirm\|correct\|reject); no bulk "confirm all". Terminal-render UX deferred to human item. |
| 3 | Pending/rejected/low-quality/ambiguous/stale fields cannot become audit-eligible / support a green verdict | ✓ VERIFIED | Independent synthetic matrix (status×quality): `is_audit_eligible` returned True ONLY for `confirmed`/`corrected` × `quality='ok'` × not-stale. pending, rejected, low_quality, ambiguous were **all False** (12/12 cells correct). `audit_eligible_values` is the single auditor entry (vault.py:1012). |
| 4 | Replacing source file / parser version / profile claim / rule-registry version marks confirmations stale until re-confirmed | ✓ VERIFIED | Independent synthetic proof: after `confirm`, mutating each of the **five** bound keys (file sha256, page render sha256, parser version, profile-claim version, rule-registry version) flipped `is_stale→True` and `is_audit_eligible→False`; **re-confirm cleared** it (`is_stale→False`, eligible→True). `confirm_value` captures all five keys (vault.py:938-957); `is_stale` compares current vs captured (vault.py:961-988). |
| 5 | `doctor`/preflight reports missing extraction deps & scan-quality issues instead of failing silently | ✓ VERIFIED | Live `doctor`: required pypdfium2/Pillow/pdfminer.six present; optional pytesseract present, `tesseract` binary **MISSING → non-failing optional warning** (overall=ok, exit 0). `doctor --candidate --document-id` returned `quality_counts={pages:3, scanned:1, low_text:1, rotated:0, password_protected:0}`. Simulated missing REQUIRED dep → envelope `error.type=missing_dependency`, **exit 3** (not internal_error). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/models/vault.py` | ExtractionRun/DocumentPage/ExtractedValue/Confirmation models + status/quality/field_name Literals + PII-light summaries | ✓ VERIFIED | Contains `class ExtractedValue`; summaries carry no raw/normalized/bbox/path. |
| `crawler/vault.py` | v2 migration + store fns + `is_audit_eligible` + `is_stale` + version helpers | ✓ VERIFIED | `SCHEMA_VERSION="2"`; additive user_version 1→2 migration; forced-pending insert; five-key staleness; single gate. |
| `crawler/extraction.py` | render/text/OCR + field extractors + scan-quality, writing pending values | ✓ VERIFIED | `PARSER_VERSION="1"`; renders every page; text-first pdfminer; typed `MissingExtractionDependency`; vault-only writes via `resolve_within`; `classify_page_quality`. |
| `crawler/confirm.py` | field-level confirm/correct/reject + five-facet view + PII split | ✓ VERIFIED | `build_field_view` (full/PII) + `build_field_view_summary` (PII-light) + `apply_decision` (exactly one value). |
| `crawler/doctor.py` | dependency preflight + scan-quality (EXTRACT-05) | ✓ VERIFIED | `run_doctor`/`probe_dependencies`/`scan_quality_report`; missing required → `missing_dependency`; optional OCR → warning. |
| `crawler/cli.py` | additive `vault extract/fields/confirm` + top-level `doctor` | ✓ VERIFIED | Verbs registered + wired (`_cmd_vault_extract/fields/confirm`, `_cmd_doctor`); frozen 5-key envelope untouched. |
| `scripts/check_publish_safe.py` | extended VAULT_SUBTREES/EXTS for extraction artifacts | ✓ VERIFIED | `files/rendered/`,`files/text/` listed; live run: 215 tracked files, **0 violations**. |
| `crawler/CONTRACT.md` | documents doctor/extract/fields/confirm; envelope + schema_version "1.0" unchanged | ✓ VERIFIED | Rows for all verbs; explicit "5-key envelope and schema_version (`\"1.0\"`) unchanged". |
| Phase-30 test files (6) | SC1–SC5 + PII-perimeter + conformance proofs | ✓ VERIFIED | 75 passed + 16 subtests (11.1s). |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `vault.is_audit_eligible` | confirmation_status + quality_flag + is_stale | single tested predicate | ✓ WIRED | Returns True only for confirmed/corrected + ok + not-stale (matrix proof). |
| `vault.confirm_value` | 5 `confirmed_*` binding columns | capture-at-confirm | ✓ WIRED | All five keys written; staleness proof flips on each. |
| `extraction.extract_document` | `vault.add_extracted_value` | pending writes | ✓ WIRED | Live e2e produced 8 pending values through the store. |
| `extraction` render/text writers | `paths.resolve_within(..., 'files', ...)` | vault-anchored writes | ✓ WIRED | Live e2e: 3 PNGs under `files/rendered/`, 1 text file under `files/text/`; corpus/ untouched. |
| `confirm.build_field_view` | crs_profile_factors (claim) + document_pages (page/crop) | join value→factor+page | ✓ WIRED | Live view exposed factor_id/group + page_number/image_relpath/bbox + claim. |
| `cli._cmd_vault_confirm` | `vault.confirm_value` + `is_audit_eligible` | field-level decision + gate surfacing | ✓ WIRED | Live confirm returned audit_eligible=True/stale=False for a confirmed ok field. |
| `doctor.run_doctor` | `extraction` dep probes + scan-quality | reuse engine imports + classifier | ✓ WIRED | Live deps + per-doc quality counts; missing-dep exit 3. |
| `check_publish_safe.scan_vault_artifact` | rendered/text/value-export paths | VAULT_SUBTREES + EXTS | ✓ WIRED | 0 violations; artifacts also git-ignored. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `vault fields` (CLI) | `fields[]` | `vault.list_extracted_values` → sqlite `extracted_values` | Yes — 8 rows from a real render/read of a synthetic PDF | ✓ FLOWING |
| `build_field_view` | five facets | joins to `document_pages` + `crs_profile_factors` | Yes — live values (8.5 / page-0001.png / core_lang / CLB 9) | ✓ FLOWING |
| `doctor` scan-quality | `quality_counts` | persisted `document_pages.quality_json` | Yes — {pages:3, scanned:1, low_text:1} | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase-30 test suite | `pytest` (6 phase-30 files) | 75 passed + 16 subtests (11.1s) | ✓ PASS |
| Full suite minus slow `test_dupaudit` (incl. all frozen-path tests) | `pytest crawler/tests scripts/tests --ignore=test_dupaudit` | 449 passed, 1 skipped, 122 subtests (29.5s) | ✓ PASS |
| SC3 quarantine matrix (synthetic) | independent `sc_proof.py` | born-pending + 12/12 status×quality cells correct | ✓ PASS |
| SC4 five-key staleness (synthetic) | independent `sc_proof.py` | all 5 keys flip stale→True/eligible→False; re-confirm clears | ✓ PASS |
| SC1/SC2/SC3 end-to-end (synthetic PDF via CLI) | independent `e2e_proof.py` | 3 pages rendered, 8 pending, five facets, PII-light --json, confirm→eligible | ✓ PASS |
| SC5 doctor deps + scan-quality + missing-dep | `--json doctor` / `doctor --candidate --document-id` / simulated missing dep | overall=ok; quality_counts surfaced; missing req dep→exit 3 (missing_dependency) | ✓ PASS |
| Publish-safe perimeter | `python scripts/check_publish_safe.py` | 215 files scanned, 0 violations (exit 0) | ✓ PASS |
| Extraction artifacts unstageable | `git check-ignore` on rendered/text/sqlite | all ignored under `personal/` + `*.sqlite` | ✓ PASS |
| Frozen envelope unchanged | grep `contract.SCHEMA_VERSION` + `--json doctor` | `"1.0"`, 5-key `{schema_version,ok,command,result,error}` | ✓ PASS |
| Slow duplicate-audit regression | `pytest crawler/tests/test_dupaudit.py` | ? not run to completion (>9 min; orthogonal — no dedup/audit source changed) | ? SKIP (scoped per instruction) |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| ----------- | -------------- | ----------- | ------ | -------- |
| EXTRACT-01 | 30-02, 30-04 | Auto-extract structured values; render pages + read text | ✓ SATISFIED | Live e2e: 3 pages rendered + text read → 8 structured fields (SC1). |
| EXTRACT-02 | 30-01, 30-02, 30-03, 30-04 | All extracted values start `pending`; no green verdict until confirmed | ✓ SATISFIED | Forced-pending insert + gate matrix (SC1/SC3). |
| EXTRACT-03 | 30-01, 30-03, 30-04 | Confirm/correct/reject each field with raw/normalized/page-crop/factor/claim | ✓ SATISFIED | build_field_view five facets + per-field decisions (SC2); terminal UX → human item. |
| EXTRACT-04 | 30-01, 30-03, 30-04 | Confirmations invalidated on file/parser/claim/registry change | ✓ SATISFIED | Five-key staleness proof (SC4). |
| EXTRACT-05 | 30-02, 30-04 | Doctor/preflight reports dep + scan-quality problems, not silent failure | ✓ SATISFIED | Live doctor deps + scan-quality + exit-3 missing-dep (SC5). |

No orphaned requirements — REQUIREMENTS.md maps EXTRACT-01..05 to Phase 30 and all five are claimed and satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TODO/FIXME/XXX/HACK/PLACEHOLDER debt markers or stub returns in any Phase-30 source | ℹ️ Info | Clean. (Two "placeholder" hits in `check_publish_safe.py` are comments describing third-party framework paths, not stubs.) |

### Human Verification Required

#### 1. Confirm-what-I-read terminal display (planner-deferred, 30-03-PLAN.md:182)

**Test:** Import a synthetic PDF into a demo vault, run `corpus-crawler vault extract --candidate demo --document-id <id>`, then `corpus-crawler vault fields --candidate demo`; separately run `corpus-crawler --json vault fields --candidate demo`.
**Expected:** The plain (stderr) terminal view legibly shows, per field, the raw value, normalized value, source page/crop reference, affected CRS factor, and profile claim; the `--json` stdout envelope carries ONLY PII-light summaries (no raw/normalized value, path, or bbox) and passes the five-key envelope check.
**Why human:** The exact printed content and PII-light `--json` shape were confirmed programmatically (five facets present in `build_field_view`; `format_field_view_human` renders them; `--json` summary keys are the 7 PII-light keys; raw value `'8.5'` absent from `--json` stdout). The residual is a visual/UX confirmation of the real interactive terminal rendering, which the planner deliberately deferred (`auto` task `<human-check>`; phase UI hint: yes).

### Gaps Summary

No gaps. Every ROADMAP success criterion is objectively TRUE in the shipped code and was proven with independent synthetic-data checks and a live end-to-end CLI/engine run — not accepted from SUMMARY claims:

- **SC1–SC5 all VERIFIED (5/5).** Extraction is born-quarantined (`pending`), the SC3 gate admits only confirmed/corrected + quality-ok + not-stale, the SC4 five-key staleness invalidates on any of file/render/parser/claim/registry change (and re-confirm clears it), and `doctor` surfaces deps + scan-quality (missing required dep → `missing_dependency`/exit 3, optional OCR absence → non-failing warning).
- **Frozen v3.x trust path intact and additive.** `contract.SCHEMA_VERSION` stays `"1.0"` with the unchanged five-key envelope; the git diff is purely additive (no dedup/audit/search source touched); the frozen-path suites (`test_json_contract`, `test_grounding`, `test_searchindex`, `test_cli`, `test_parity_ircc`) pass.
- **PII contained.** Rendered images / extracted text / vault DB are git-ignored under `personal/` (+ `*.sqlite` defense-in-depth) and flagged `VAULT_ARTIFACT`; publish-safe reports 0 violations; no fake value/path reaches any `--json` stdout envelope.

The single reason status is `human_needed` rather than `passed` is the one planner-deferred `<human-check>` (visual terminal-display confirmation) harvested per process — the underlying content is already corroborated in code.

**Note on `test_dupaudit`:** not run to completion (>9 minutes wall time, repeatedly timed out; the context explicitly permits scoping it). It exercises v3.x duplicate-audit detection and depends on no file Phase 30 changed (diff is additive: extraction/confirm/doctor/cli/publish-safe/tests only), so it carries no regression risk from this phase. The remainder of the suite (449 passed) plus all 6 Phase-30 files (75 passed) is green.

---

_Verified: 2026-07-06T08:20:25Z_
_Verifier: the agent (gsd-verifier)_
