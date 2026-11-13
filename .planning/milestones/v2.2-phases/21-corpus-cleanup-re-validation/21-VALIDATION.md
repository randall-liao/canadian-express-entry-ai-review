---
phase: 21
slug: corpus-cleanup-re-validation
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-11
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `21-RESEARCH.md` § Validation Architecture. Tests use **stdlib `unittest` ONLY**
> — no pytest, no crawl4ai, no network.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python stdlib `unittest` (3.10+) |
| **Config file** | none — discovered by module path |
| **Quick run command** | `poetry run python -m unittest crawler.tests.test_dupclean -v` |
| **Full suite command** | `poetry run python -m unittest discover -s crawler/tests -v` |
| **Estimated runtime** | ~5 seconds (synthetic fixtures; full suite ~10 min due to Phase 20 real-corpus smoke) |

---

## Sampling Rate

- **After every task commit:** `poetry run python -m unittest crawler.tests.test_dupclean -v`
- **After every plan wave:** `poetry run python -m unittest discover -s crawler/tests -v`
- **Before `/gsd-verify-work`:** full suite green + a real-corpus `--apply` dry-run shows the expected 10 high-confidence moves and 6 retained overlap-only clusters
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| CLEAN-02 | Each high-confidence delete target leaves the live set; canonical stays | unit | `... TestApply.test_moves_only_noncanonical` | ❌ W0 | ⬜ |
| CLEAN-02 | Keep-canonical guarantee: canonical relpath is NEVER moved | unit | `... TestApply.test_canonical_untouched` | ❌ W0 | ⬜ |
| CLEAN-02 | Overlap-only excluded by default; included only with `--include-overlap` | unit | `... TestScope.test_overlap_only_excluded_by_default` | ❌ W0 | ⬜ |
| CLEAN-02 | Idempotency: second `--apply` is a no-op | unit | `... TestApply.test_idempotent_reapply` | ❌ W0 | ⬜ |
| CLEAN-02 | Dry-run default: filesystem snapshot unchanged | unit | `... TestDryRun.test_default_is_dry_run` | ❌ W0 | ⬜ |
| CLEAN-02 | Zero-cluster re-check: post-apply `exact_edges+url_edges → cluster()==[]` | unit | `... TestRecheck.test_no_exact_or_url_clusters_after_apply` | ❌ W0 | ⬜ |
| CLEAN-03 | Moved doc's URL removed from family `manifest.json` | unit | `... TestRevalidate.test_manifest_pruned` | ❌ W0 | ⬜ |
| CLEAN-03 | Orphaned `completeness/*.check.json`/sample pruned | unit | `... TestRevalidate.test_completeness_orphans_pruned` | ❌ W0 | ⬜ |
| CLEAN-03 | REPORT.md regenerated with decremented live count, verdict still pass | unit | `... TestRevalidate.test_report_count_updated` | ❌ W0 | ⬜ |
| CLEAN-03 | `.eval.json` sibling moves with its `.md` (both naming forms) | unit | `... TestApply.test_eval_sibling_moved` | ❌ W0 | ⬜ |
| SC5 | Git-status-local: `git status --porcelain corpus/` empty after apply | unit/integration | `... TestGit.test_corpus_changes_stay_ignored` | ❌ W0 | ⬜ |
| Security | Path-traversal `relpath` (`../`, absolute) refused before move | unit | `... TestSecurity.test_rejects_escaping_relpath` | ❌ W0 | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `crawler/tests/test_dupclean.py` — new suite (CLEAN-02/03 + SC5 + security)
- [ ] Report fixture: run `dupaudit.audit()` + `render_json()` over the synthetic `_make_dup_corpus` to mint a real `duplicate-audit.json` in-tempdir (no hand-authored JSON — keeps schema in sync)
- [ ] No framework install needed (stdlib unittest already used)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| The 6 overlap-only delete targets are confirmed retained, NOT moved, by default | CLEAN-02 | They are verified false positives (different countries / EE rounds); deleting them would lose authoritative docs | After a real `--apply`, confirm those 6 source paths still exist under their family dirs and only the 10 exact/URL targets moved to `_dropped/` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-11
