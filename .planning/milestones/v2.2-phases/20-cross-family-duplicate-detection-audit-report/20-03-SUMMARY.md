---
phase: 20-cross-family-duplicate-detection-audit-report
plan: 03
subsystem: tooling
tags: [dedup, report, json-contract, publish-safety, scan_text, argparse, read-only]

# Dependency graph
requires:
  - phase: 20-01
    provides: "crawler/dupaudit.py typed contract (AuditResult/Cluster/Doc dataclasses) + RED test suite"
  - phase: 20-02
    provides: "live_docs enumeration, parse_doc, three detectors, union-find cluster, cluster_signals, select_canonical"
provides:
  - "audit() orchestrator: enumerate -> parse -> 3 detectors -> union-find -> canonical, assembling per-cluster records (signals + canonical + per-member keep/delete reasons)"
  - "Per-signal cluster counts (exact/url/overlap counted as clusters whose signal set contains that detector)"
  - "render_markdown: shareable human report with separated EXACT / same-URL / overlap-only sections, each member showing relpath/family/url/KEEP|DELETE/reason"
  - "render_json: machine-readable dict sidecar with per-cluster signals + per-member fields"
  - "main(argv) CLI: positional corpus, --json (audit-duplicates envelope), --overlap-threshold (0.95), --out (default reports/); RPT-03 share-safety gate over the rendered report that FAILS CLOSED on any violation"
  - "Generated reports/duplicate-audit.md + reports/duplicate-audit.json against the real 752-doc corpus"
affects: [phase-21-deletion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Render-then-gate: scan_text runs on the rendered markdown string BEFORE writing, so the gate works even before git-add (Pitfall 6)"
    - "Fail-closed share-safety: any scan_text violation aborts with non-zero exit and ok:false envelope; the report is still written only when clean"
    - "One-section-per-cluster partition (exact | url-not-exact | overlap-only) so every cluster appears exactly once"
    - "Reuse contract.envelope/emit for the audit-duplicates --json contract; INVALID_INPUT for bad corpus path, INTERNAL_ERROR for unexpected exceptions / publish-unsafe report"

key-files:
  created:
    - reports/duplicate-audit.md
    - reports/duplicate-audit.json
  modified:
    - crawler/dupaudit.py

key-decisions:
  - "audit() loads the 'ircc' profile internally so normalize_url matches ingest (TestRealCorpus calls audit(corpus) with no profile arg)"
  - "Report categorized into exact / same-URL (url but not exact) / overlap-only sections for clear visual separation per RPT-02"
  - "Publish-unsafe report mapped to ok:false + INTERNAL_ERROR + non-zero exit (EXIT_INTERNAL_ERROR) — refuse to ship a leaky report"
  - "audit/main perform zero writes under corpus/; reports always go to --out (default reports/, git-tracked, outside any family dir)"

patterns-established:
  - "Pattern: render markdown -> scan_text gate -> write only if clean -> emit envelope"
  - "Pattern: per-cluster record dict {signals, canonical, size, members[{relpath,family,url,decision,reason}]} shared by both renderers"

requirements-completed: [RPT-01, RPT-02, RPT-03]

# Metrics
duration: 30min
completed: 2026-06-11
---

# Phase 20 Plan 03: Cross-Family Duplicate Audit Report Summary

**Read-only audit tool that orchestrates the Phase-20 detection core into a shareable keep/delete report (markdown + JSON), gated through `check_publish_safe.scan_text` (fail-closed), exposed via a `--json` `audit-duplicates` envelope, and proven to make zero changes to `corpus/`.**

## Performance

- **Duration:** ~30 min (dominated by two ~9-min real-corpus overlap-detector runs)
- **Started:** 2026-06-11T01:14:01Z
- **Completed:** 2026-06-11T01:44Z
- **Tasks:** 3
- **Files modified:** 1 source (`crawler/dupaudit.py`) + 2 generated reports + 4 publish-safe marker edits

## Accomplishments
- Implemented `audit()`, `render_markdown()`, `render_json()`, and `main(argv)` — turning the last four stubs GREEN.
- Real-corpus run: **752 live docs**, **1 exact**, **4 same-URL**, **8 high-overlap** clusters (11 total).
- RPT-03 share-safety gate runs `scan_text` on the rendered report and fails closed (non-zero + `ok:false`) on any abs-path/secret/PII violation; the generated report has 0 violations.
- Proven read-only over `corpus/` (Success Criterion 5): `git status --porcelain corpus/` empty after a full run; `TestReadOnly` manifest identical before/after.
- Full offline suite GREEN: **89 tests OK** (1 skipped — crawl4ai-dependent deepcrawl test).

## Task Commits

1. **Task 1+2: audit orchestrator + markdown/JSON rendering + main(argv)/--json/share-safety gate** - `b83983f` (feat)
2. **Task 3: publish-safe allow markers (deviation) + generated real-corpus report** - `813527c` (chore; bundled the report which was pre-staged)

_Note: Tasks 1 and 2 were implemented in a single edit to `crawler/dupaudit.py` and committed together (see Deviations); Task 3 required no source change (read-only already held) — its artifact is the generated report._

## Files Created/Modified
- `crawler/dupaudit.py` - Implemented `audit`, `render_markdown`, `render_json`, `main(argv)`; added `json` + `load_profile` imports.
- `reports/duplicate-audit.md` - Generated human report (752 docs, 11 clusters).
- `reports/duplicate-audit.json` - Generated machine sidecar.
- `crawler/tests/test_dupaudit.py`, `20-01-PLAN.md`, `20-03-PLAN.md`, `20-RESEARCH.md` - appended `# publish-safe: allow` markers to pre-existing benign `/home/u/x` example strings (deviation).

## Decisions Made
- `audit()` loads the `ircc` profile internally (TestRealCorpus calls `audit(corpus)` with no profile).
- Report sections: exact / same-URL-not-exact / overlap-only — one section per cluster, no duplication.
- Publish-unsafe report → `ok:false` + `INTERNAL_ERROR` + non-zero exit (refuse to ship a leaky report).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Suppressed pre-existing publish-safety violations to green the phase gate**
- **Found during:** Task 3 (running `scripts/check_publish_safe.py`, a listed phase gate)
- **Issue:** The checker was already RED before this plan: 5 pre-existing benign home-directory example strings in `20-01-PLAN.md`, `20-03-PLAN.md`, `20-RESEARCH.md`, and the intentional RPT-03 poison fixture in `test_dupaudit.py:494`. None were in my report or source.
- **Fix:** Appended the sanctioned `# publish-safe: allow` escape-hatch marker to those 5 lines. The poison test still detects the violation (the marker is a source comment, not part of the asserted string).
- **Files modified:** `crawler/tests/test_dupaudit.py`, `20-01-PLAN.md`, `20-03-PLAN.md`, `20-RESEARCH.md`
- **Verification:** `check_publish_safe.py` → `0 violations`; `TestPublishSafe` still GREEN.
- **Committed in:** `813527c`

### Commit-granularity note
Tasks 1 and 2 were implemented in one edit (single file, `crawler/dupaudit.py`) and committed together as `b83983f` rather than as two separate commits. All three tasks' verifications were run and passed in order.

---

**Total deviations:** 1 auto-fixed (1 blocking, via sanctioned escape hatch)
**Impact on plan:** No scope creep. The marker fix unblocks the plan's own verification gate; the generated report itself has 0 violations.

## Issues Encountered
- **Overlap detector runtime (~9 min on 752 docs):** `overlap_edges` (Plan 02, length-bucketed difflib) is the dominant cost; the full suite (which runs `TestRealCorpus`) takes ~525s. Pre-existing Plan-02 behavior, out of this plan's scope — not modified. Logged as a performance observation for Phase 21 if iterated runs become painful.
- **`TestJson` writes to the real `reports/` dir:** because its default `--out` is `reports`, running the suite overwrites the real report with the synthetic 8-doc one. Regenerated the authoritative 752-doc report after the suite before committing. (Test-design side-effect from Wave 0; not changed.)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The shareable `reports/duplicate-audit.md` is the deliverable Phase 21 (deletion) acts on: 1 exact, 4 same-URL, 8 overlap-only clusters with a named canonical keep + per-member delete reasons.
- **Advisory (human_verify_mode=end-of-phase):** the 8 overlap-only clusters should be human-reviewed before any deletion — confirm they are true logical duplicates rather than boilerplate-similar templated pages (e.g. police-certificate / NOC). No corpus change was made in Phase 20.

---
*Phase: 20-cross-family-duplicate-detection-audit-report*
*Completed: 2026-06-11*

## Self-Check: PASSED

All created files exist on disk and both task commits (`b83983f`, `813527c`) are present in git history.
