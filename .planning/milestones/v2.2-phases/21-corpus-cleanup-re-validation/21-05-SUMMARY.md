---
phase: 21-corpus-cleanup-re-validation
plan: 05
type: execute
status: complete
requirements-completed: [CLEAN-02, CLEAN-03]
completed: 2026-06-11
---

# Plan 21-05 Summary — Real-Corpus `--apply` + Re-validation

## What was done

Executed the destructive cleanup against the real local corpus, gated by a
human-verify checkpoint that was reviewed and approved inline (YOLO auto mode).

**Wave 5 sequence:**
1. **Dry-run** (`python -m crawler.dupclean corpus/ --report reports/duplicate-audit.json --json`) → `ok:true`, 10 planned moves, 6 retained overlap-only. Zero filesystem changes.
2. **Checkpoint (approved):** verified via `load_plan` that the 10 high-confidence delete targets are genuine exact/URL duplicates and the 6 retained are the verified-distinct false positives (different countries / EE rounds).
3. **`--apply`:** moved the 10 non-canonical copies (+ eval siblings) into their family `_dropped/` with per-family `duplicate-clean.log.json` audit trails; pruned moved URLs from family `manifest.json`; pruned orphaned `completeness/` sidecars; regenerated each touched family's `REPORT.md`; folded in the exact+URL zero-cluster re-check.

## 10 high-confidence targets moved (recoverable, in `_dropped/`)

- `mi-rounds/express-entry-rounds.md`, `mi-rounds/invitations-{11,18,22,28,31,35}.md`
- `ministerial-instructions/express-entry-application-management-system.md`
- `pdi-completeness-check/applications-received-on-after-january-1-2016-completeness-check.md`
- `police-certificates/police-certificates-1.md` (the verified cross-family EXACT dup of `guidance/police-certificates.md`)

## 6 overlap-only false positives RETAINED (untouched)

`police-certificates/{tokelau,guadeloupe,mayotte}.md`, `mi-rounds/invitations-12.md`, `guidance/{check-score,grid}.md` — verified distinct (different countries / EE rounds).

## Success criteria — all met

| SC | Result |
|----|--------|
| SC1 — 10 non-canonical moved, one canonical per cluster | ✅ moved=10 |
| SC2 — re-run detector → zero cross-family clusters | ✅ `recheck_clusters=[]` (exact+URL) |
| SC3 — live counts updated/recorded | ✅ 752 → 742 |
| SC4 — QC/completeness verdicts not "fail"; no dangling refs | ✅ all 4 families `verdict=pass`; manifests + completeness pruned |
| SC5 — deletions stayed local | ✅ `git status --porcelain corpus/` empty (corpus/ git-ignored) |

Envelope: `ok:true`, `verdict:pass`, `live_before:752`, `live_after:742`, `moved:10`, `retained_overlap_only:6`.

## Verification

- `poetry run python -m unittest crawler.tests.test_dupclean` → 15/15 OK.
- `poetry run python scripts/check_publish_safe.py` → 0 violations (`reports/duplicate-clean.json` shareable — source URLs only).

## Deviations

- Ran Wave 5 inline (not via a subagent) so the orchestrator could adjudicate the blocking checkpoint under the user's YOLO directive; the move is recoverable (`_dropped/`) and `corpus/` is git-ignored, so the destructive step is reversible.
- `pdi-completeness-check` now has 0 live docs (its only doc was a duplicate whose canonical lives in another family); `revalidate_family` reports `verdict=pass` for it.

## Notes for the milestone

- Smarter near-duplicate detection (to catch the kind of boilerplate-similar-but-distinct pages that produced the 6 false positives) remains deferred as DUP-05/06.
- The 10 dropped copies are recoverable from each family's `_dropped/`; re-running the crawler also regenerates them.
