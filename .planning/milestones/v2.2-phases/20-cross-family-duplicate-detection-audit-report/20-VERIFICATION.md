---
phase: 20-cross-family-duplicate-detection-audit-report
verified: 2026-06-11T05:56:03Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
resolved_gaps:
  - truth: "A PII / share-safety scan is green — the repo-wide publish-safety gate `scripts/check_publish_safe.py` passes (RPT-03, Success Criterion 4)."
    status: resolved
    resolution: >
      Fixed after verification: the lone violation was an unmarked absolute-path
      example string narrated inside 20-03-SUMMARY.md:98 (not in the deliverable).
      Rephrased the line to remove the literal example paths. Re-ran
      `scripts/check_publish_safe.py` → "77 tracked files scanned, 0 violations".
      Separately hardened TestJson to write its report to a per-test tempdir
      (`--out`), so running the suite no longer clobbers the authoritative
      reports/duplicate-audit.{md,json} (report md5 confirmed unchanged across a
      full `unittest discover` run). Full suite: 89 OK, 1 skipped (crawl4ai).
human_verification:
  - test: "Human-review the 8 high-overlap (near-duplicate) clusters in reports/duplicate-audit.md section 4 before any Phase 21 deletion."
    expected: "Each overlap-only pair is a true logical duplicate, not two boilerplate-similar-but-distinct templated pages (e.g. police-certificate country pages, NOC pages). Some police-certificate clusters keep a copy with as few as 329/441/1031 chars — confirm these are genuinely the same document."
    why_human: "Text-overlap ≥0.95 over short boilerplate-heavy pages can group distinct logical documents; semantic equivalence cannot be confirmed by grep. Carried forward from 20-03-SUMMARY 'Next Phase Readiness' advisory."
---

# Phase 20: Cross-Family Duplicate Detection & Audit Report — Verification Report

**Phase Goal:** A shareable audit report identifies every cross-family duplicate cluster across all 16 families and names the one canonical copy to keep — with zero changes to the corpus (read-only dry run).
**Verified:** 2026-06-11T05:56:03Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

The detection engine, clustering, canonical selection, and report rendering are
**fully and substantively implemented** (not stubs) and **independently verified
against the real 752-doc corpus**. The committed report is correct, complete, and
clean. One narrow gap blocks a clean pass: the repo-wide publish-safety gate is
RED because this phase's own SUMMARY narrative re-introduced an unmarked example
absolute path — the deliverable report is unaffected but the explicit step-4 check
fails.

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | Exact (content-hash) duplicate clusters across families detected, including dups within-run dedup missed (DUP-01, DUP-04) | ✓ VERIFIED | Real run found **1 exact** cluster (`guidance/police-certificates.md` ≡ `police-certificates/police-certificates-1.md`). `exact_edges` groups by body-only sha1. `TestExact` (2), `TestEnumerate` (3) green. |
| 2   | Near-duplicate clusters surfaced by shared normalized URL AND by high text-overlap (DUP-02, DUP-03) | ✓ VERIFIED | Real run: **4 same-URL** + **8 high-overlap** clusters. `url_edges` (normalize_url), `overlap_edges` (length-blocked difflib ≥0.95). `TestUrl` (2), `TestOverlap` (2, incl. 0.96-clusters / 0.90-excluded boundary) green. |
| 3   | Each cluster lists every member's relpath, family, source URL; names exactly one canonical with keep/delete decision + reason (RPT-01, RPT-02, CLEAN-01) | ✓ VERIFIED | Programmatic JSON check: all 11 clusters have exactly one `keep`, `canonical` == keep member's relpath, every member carries relpath/family/url/decision/reason. Reasons cite QC + body length. `TestReport` (2), `TestCanonical` (4, incl. determinism-across-shuffles) green. |
| 4   | A PII / share-safety scan is green — report safe to share (RPT-03, SC4) | ✓ RESOLVED | **Report is safe** (committed reports/duplicate-audit.{md,json} → 0 violations via scan_text; `TestPublishSafe` green). The one repo-gate violation was a home-directory example string in the 20-03 SUMMARY narrative; it was rephrased post-verification and `scripts/check_publish_safe.py` now exits 0. |
| 5   | The audit makes zero changes to corpus/ (read-only dry run) | ✓ VERIFIED | `find corpus -name '*.md' \| md5sum` identical before/after (`3af77877…`); `git status --porcelain corpus/` empty after a full `--json` run. corpus/ is git-ignored. `TestReadOnly` (2) green. |

**Score:** 4/5 truths verified (1 partial — report safe, repo gate red)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/dupaudit.py` | Full audit pipeline (enumerate→parse→3 detectors→union-find→canonical→render→main/--json/share-gate) | ✓ VERIFIED | 669 lines, all functions implemented (no NotImplementedError remaining). Contains `SequenceMatcher`, `audit-duplicates`, `def main`. `yaml.safe_load` only (T-20-02). Enumeration confined to resolved corpus root (T-20-01). |
| `crawler/tests/test_dupaudit.py` | Wave-0 spec + synthetic fixture | ✓ VERIFIED | `_make_dup_corpus` present; 30 tests across 11 classes, all green (24 fast + TestRealCorpus in full suite). |
| `reports/duplicate-audit.md` | Human shareable report | ✓ VERIFIED | Committed HEAD: 752 docs, 11 clusters, sectioned exact/same-URL/overlap; KEEP/DELETE + reasons per member; 0 publish-safety violations. |
| `reports/duplicate-audit.json` | Machine sidecar | ✓ VERIFIED | Committed HEAD: live_docs=752, exact=1, url=4, overlap=8, total=11; per-member relpath/family/url/decision/reason. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| dupaudit.py | crawler.profile.normalize_url | URL canonicalization | ✓ WIRED | Imported + used in `parse_doc`; `load_profile("ircc")` in `audit()`. |
| dupaudit.py | crawler.eval_runner.check_doc | passed_qc ranking | ✓ WIRED | Imported + used in `parse_doc`; drives `select_canonical`. |
| dupaudit.py | pipeline sha1 body-hash | exact-dup signal | ✓ WIRED | `hashlib.sha1(body_of(text))` mirrors pipeline.py:115. |
| dupaudit.py | scripts/check_publish_safe.scan_text | RPT-03 gate over rendered report | ✓ WIRED | `cps.scan_text(rel_md, report_md)` before write; fails closed (non-zero + ok:false). |
| dupaudit.py | crawler.contract | --json audit-duplicates envelope | ✓ WIRED | `contract.envelope/emit`; INVALID_INPUT for bad path, INTERNAL_ERROR for publish-unsafe. |
| dupaudit.py main | reports/ output dir | report written outside corpus/ | ✓ WIRED | `--out` default `reports/`; never under corpus/. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Real-corpus audit JSON envelope | `python -m crawler.dupaudit corpus/ --json` | exit 0; single JSON object; ok=true, command=audit-duplicates, live_docs=752, exact=1, url=4, overlap=8, 11 clusters | ✓ PASS |
| Read-only over corpus | `md5sum` of corpus md manifest before/after + `git status corpus/` | identical hash `3af77877…`; status empty | ✓ PASS |
| Report share-safety (deliverable) | `scan_text` on committed reports/duplicate-audit.{md,json} | 0 violations each | ✓ PASS |
| Repo-wide publish gate | `python scripts/check_publish_safe.py` | exit 1 — 1 violation in 20-03-SUMMARY.md:98 | ✗ FAIL |
| One canonical per cluster | JSON assertion over all 11 clusters | exactly one keep each; canonical==keep relpath | ✓ PASS |
| dupaudit test classes | `unittest … TestExact/Url/Overlap/Cluster/Canonical/Report/PublishSafe/ReadOnly/Json/Enumerate` | 24 tests OK | ✓ PASS |
| Full offline suite | `unittest discover -s crawler/tests -v` | 89 tests OK, 1 skipped (crawl4ai deepcrawl) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DUP-01 | 20-01/02 | Exact content-hash dups across families | ✓ SATISFIED | `exact_edges` body-sha1; TestExact green; 1 real cluster. |
| DUP-02 | 20-01/02 | Near-dups by shared canonical/source URL | ✓ SATISFIED | `url_edges` + normalize_url; TestUrl green; 4 real clusters. |
| DUP-03 | 20-01/02 | Near-dups by high text-overlap | ✓ SATISFIED | `overlap_edges` difflib ≥0.95; TestOverlap boundary green; 8 real clusters. |
| DUP-04 | 20-01/02 | Group dups into clusters (≥2 copies) | ✓ SATISFIED | `UF`/`cluster` union-find, singletons excluded; TestCluster green. |
| RPT-01 | 20-01/03 | Report lists each member path/family/url | ✓ SATISFIED | render_markdown + render_json; JSON per-member fields verified. |
| RPT-02 | 20-01/03 | Each entry states keep/delete decision + reason | ✓ SATISFIED | KEEP/DELETE + reason per member in MD & JSON; TestReport green. |
| RPT-03 | 20-01/03 | Report safe to share, no PII | ⚠ PARTIAL | Report deliverable clean (0 violations, TestPublishSafe green) BUT repo gate `check_publish_safe.py` RED on 20-03-SUMMARY.md:98. |
| CLEAN-01 | 20-01/02 | Exactly one canonical per cluster (longest cleaned, prefer QC) | ✓ SATISFIED | `select_canonical` deterministic rank; TestCanonical (4) green; verified 1 keep/cluster. |
| CLEAN-02 | Phase 21 | Delete non-canonical copies | n/a | Out of scope (Phase 21). Correctly NOT done — read-only confirmed. |
| CLEAN-03 | Phase 21 | Re-validate corpus after deletion | n/a | Out of scope (Phase 21). |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| 20-03-SUMMARY.md | 98 | Unmarked ABS_PATH example (home-directory example path) | ✓ Resolved | Rephrased post-verification; `check_publish_safe.py` now exits 0. Was never in any shipped deliverable. |
| crawler/tests/test_dupaudit.py (TestJson) | ~521-540 | Test writes to real `reports/` (default `--out=reports`) | ℹ️ Info | Running the suite overwrites the authoritative 752-doc report with synthetic 8-doc test data. Documented in SUMMARY Issue #2. Committed artifact is correct; verification re-runs clobber the working tree (restored during this verification). |

No `TODO`/`FIXME`/`XXX`/`HACK` debt markers found in `crawler/dupaudit.py`. No empty/placeholder implementations — every function has real logic.

### Human Verification Required

#### 1. Near-duplicate (overlap-only) cluster review

**Test:** Review the 8 high-overlap clusters in `reports/duplicate-audit.md` section 4.
**Expected:** Each overlap-only pair is a true logical duplicate rather than two distinct boilerplate-similar templated pages. Note several police-certificate canonicals keep very short bodies (329 / 441 / 1031 chars) — confirm these short pairs are genuinely the same document, not two different country pages sharing a template.
**Why human:** Text-overlap ≥0.95 over short, boilerplate-heavy pages can group distinct logical documents; semantic equivalence cannot be confirmed by grep. This gates safe deletion in Phase 21 (carried forward from the SUMMARY's "Next Phase Readiness" advisory).

### Gaps Summary

The phase goal is **substantively achieved**: a correct, complete, shareable
read-only audit report exists, identifies all cross-family duplicate clusters via
three independent signals, names exactly one canonical per cluster with keep/delete
reasons, and makes zero changes to the corpus. All 30 dupaudit tests pass; the full
offline suite is 89-green/1-skipped; the real-corpus run reproduces the documented
752/1/4/8/11 counts; the committed report scans clean.

**Gap resolved post-verification:** `scripts/check_publish_safe.py` — the repo's
share-safety gate — briefly exited non-zero because the 20-03 SUMMARY narrative
quoted a home-directory example path without a marker while narrating the fix it
applied elsewhere. The actual report deliverable (RPT-03's true subject) was always
clean. The narrative was rephrased to drop the literal example path, and
`check_publish_safe.py` now exits 0 — so the milestone can assert publish-safety
without an override.

**Historical note (no longer needed).** The benign example path inside a planning
SUMMARY narrative (outside any shipped artifact) could alternatively have been
accepted via an override block:

```yaml
overrides:
  - must_have: "share-safety scan green / check_publish_safe.py passes"
    reason: "Violation was a benign example string inside the 20-03 planning SUMMARY narrative, not in the shippable report; the report itself scans 0 violations."
    accepted_by: "{your name}"
    accepted_at: "{ISO timestamp}"
```

Recommended instead: append `# publish-safe: allow` to `20-03-SUMMARY.md:98` (the
same sanctioned escape hatch already used on 5 sibling files) so the gate is green.

---

_Verified: 2026-06-11T05:56:03Z_
_Verifier: the agent (gsd-verifier)_
