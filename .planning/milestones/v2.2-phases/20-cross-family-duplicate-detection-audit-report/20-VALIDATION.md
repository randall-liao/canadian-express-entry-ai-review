---
phase: 20
slug: cross-family-duplicate-detection-audit-report
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-11
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `20-RESEARCH.md` § Validation Architecture. Tests use **stdlib `unittest` ONLY**
> — no pytest, no crawl4ai, no network (convention: `crawler/tests/test_json_contract.py:1-12`).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python stdlib `unittest` (3.10+) |
| **Config file** | none — discovered by module path |
| **Quick run command** | `poetry run python -m unittest crawler.tests.test_dupaudit -v` |
| **Full suite command** | `poetry run python -m unittest discover -s crawler/tests -v` |
| **Estimated runtime** | ~5 seconds (synthetic fixtures) |

---

## Sampling Rate

- **After every task commit:** Run `poetry run python -m unittest crawler.tests.test_dupaudit -v`
- **After every plan wave:** Run `poetry run python -m unittest discover -s crawler/tests -v`
- **Before `/gsd-verify-work`:** Full offline suite green + `poetry run python -m crawler.dupaudit corpus/ --json` runs clean against the real corpus + `poetry run python scripts/check_publish_safe.py` green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Wave | Requirement | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|-------------|-----------------|-----------|-------------------|-------------|--------|
| corpus enumeration | 1 | (Criterion 5) | 752-filter excludes `_dropped/`, `completeness/`, `*.live.md`, `REPORT.md`, no-frontmatter | unit | `... TestEnumerate` | ❌ W0 | ⬜ pending |
| exact detection | 1 | DUP-01 | body-only sha1 (strip frontmatter); identical body + different url/date → one cluster | unit | `... TestExact` | ❌ W0 | ⬜ pending |
| url detection | 1 | DUP-02 | same normalized `url` (frag/wbdisable/trailing-slash variants) → one cluster | unit | `... TestUrl` | ❌ W0 | ⬜ pending |
| overlap detection | 1 | DUP-03 | ratio ≈0.96 clustered; ≈0.90 NOT clustered (threshold boundary) | unit | `... TestOverlap` | ❌ W0 | ⬜ pending |
| clustering | 1 | DUP-04 | transitive edges → single cluster; singletons excluded | unit | `... TestCluster` | ❌ W0 | ⬜ pending |
| canonical selection | 1 | CLEAN-01 | passed-QC > non-QC; longest body breaks QC ties; lexicographic path breaks length ties (deterministic) | unit | `... TestCanonical` | ❌ W0 | ⬜ pending |
| report render | 2 | RPT-01, RPT-02 | MD+JSON lists each member path/family/url + keep/delete + reason | unit | `... TestReport` | ❌ W0 | ⬜ pending |
| share-safety | 2 | RPT-03 | `check_publish_safe.scan_text(report)` → 0 violations; poisoned copy → fails | unit | `... TestPublishSafe` | ❌ W0 | ⬜ pending |
| read-only guarantee | 2 | (Criterion 5) | corpus `(relpath→size,mtime,sha1)` manifest unchanged before/after; zero writes in family dirs | unit/integration | `... TestReadOnly` | ❌ W0 | ⬜ pending |
| `--json` contract | 2 | RPT-01 | one `json.loads`-able object on stdout, `ok:true`, `command=="audit-duplicates"` | unit | `... TestJson` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `crawler/tests/test_dupaudit.py` — all detector/cluster/canonical/report/read-only/json tests (covers DUP-01..04, CLEAN-01, RPT-01..03, Criterion 5)
- [ ] `_make_dup_corpus(tmp)` fixture helper — synthetic multi-family corpus with planted exact/url/near-dup/singleton docs + matching `.eval.json` siblings (mirror `test_json_contract._make_lean_corpus`)
- [ ] Framework install: **none** — stdlib `unittest` is present; do NOT add pytest

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Human review of near-dup (DUP-03) clusters before any Phase 21 deletion | DUP-03 | Near-dup keep/delete decisions are advisory; deletion is a separate phase | Read the generated report's near-dup section; confirm clusters are true duplicates |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-11
