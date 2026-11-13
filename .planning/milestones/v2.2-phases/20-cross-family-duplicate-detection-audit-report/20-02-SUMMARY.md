---
phase: 20-cross-family-duplicate-detection-audit-report
plan: 02
subsystem: tooling
tags: [dedup, difflib, union-find, sha1, normalize_url, pyyaml, qc]

# Dependency graph
requires:
  - phase: 20-01
    provides: "crawler/dupaudit.py typed contract (dataclasses + stubs) and the RED test_dupaudit.py suite"
provides:
  - "Implemented live-doc enumeration (the 752-filter) confined to the resolved corpus root"
  - "parse_doc: yaml.safe_load-only frontmatter parse, normalize_url canonicalization, check_doc-based passed_qc"
  - "Three distinct duplicate detectors: exact body-sha1 (DUP-01), normalized-URL (DUP-02), length-blocked difflib overlap (DUP-03)"
  - "Union-find clustering (DUP-04) with per-component signal attribution"
  - "Deterministic, reason-annotated canonical selection (CLEAN-01)"
affects: [20-03, phase-21-deletion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reuse-the-crawler's-own-semantics: body-only sha1 (pipeline.py:115), normalize_url (profile.py), check_doc QC (eval_runner.py)"
    - "Length-bucket blocking + real_quick_ratio/quick_ratio prefilter before difflib ratio()"
    - "Negated-ordinal total-order key so a single max() yields the full canonical ranking deterministically"

key-files:
  created: []
  modified:
    - crawler/dupaudit.py

key-decisions:
  - "Doc.url stores the NORMALIZED url so url_edges groups directly by d.url"
  - "live_docs resolves the corpus root to absolute and walks only via rglob within it (T-20-01)"
  - "Frontmatter parsed with yaml.safe_load ONLY — never yaml.load (T-20-02)"
  - "Missing .eval.json sibling resolves to passed_qc=False (not an error)"

patterns-established:
  - "Three detectors return independent edge sets; union happens only at clustering time"
  - "cluster() returns sorted components of size >=2; singletons excluded"

requirements-completed: [DUP-01, DUP-02, DUP-03, DUP-04, CLEAN-01]

# Metrics
duration: ~20min
completed: 2026-06-11
---

# Phase 20 Plan 02: Cross-Family Duplicate Detection Engine Summary

**Implemented the read-only duplicate DETECTION core in `crawler/dupaudit.py` — live-doc enumeration, frontmatter parsing, three independent dup signals (body-sha1 / normalized-URL / length-blocked difflib overlap), union-find clustering, and deterministic canonical selection — turning all six Wave-2 detector test classes from RED to GREEN.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-11T01:09Z (approx)
- **Completed:** 2026-06-11T01:30Z (approx)
- **Tasks:** 3 completed
- **Files modified:** 1 (`crawler/dupaudit.py`)

## Accomplishments
- Filled in every Wave-2 stub in `crawler/dupaudit.py` (enumeration, parsing, 3 detectors, UF/cluster/cluster_signals, select_canonical) reusing the crawler's tested primitives so the audit's duplicate definition stays consistent with ingestion.
- Turned the 6 target test classes (17 tests) GREEN: `TestEnumerate`, `TestExact`, `TestUrl`, `TestOverlap`, `TestCluster`, `TestCanonical`.
- Honored all phase constraints: no new dependencies (`git diff pyproject.toml poetry.lock` empty), `yaml.safe_load` only, enumeration confined to the resolved corpus root, pure-read (no writes under `corpus/`).

## Task Commits

Each task was committed atomically:

1. **Task 1: live-doc enumeration + frontmatter parsing** — `e01b206` (feat)
2. **Task 2: three duplicate detectors (exact/url/overlap)** — `ac8c207` (feat)
3. **Task 3: union-find clustering + canonical selection** — `a3753af` (feat)

## Files Created/Modified
- `crawler/dupaudit.py` — implemented `live_docs`, `_frontmatter_of`, `parse_doc`, `exact_edges`, `url_edges`, `overlap_edges`, `UF`, `cluster`, `cluster_signals`, `select_canonical`. Added imports of `check_doc`, `normalize_url`, `SequenceMatcher`, `defaultdict`. (379 lines.)

## Verification Outcomes
- `poetry run python -m unittest crawler.tests.test_dupaudit.TestEnumerate TestExact TestUrl TestOverlap TestCluster TestCanonical` → **17 tests, OK** (all GREEN).
- `git diff pyproject.toml poetry.lock` → **empty** (no new dependency).
- Full `test_dupaudit` module: 7 errors remaining — `TestReport`, `TestPublishSafe`, `TestReadOnly`, `TestJson` (and `TestRealCorpus`). These exercise `audit()`/`render_markdown()`/`render_json()`/`main()`, which are **Plan 03 (Wave 3) scope** and correctly still raise `NotImplementedError`. Expected RED.
- Only `yaml.safe_load` is invoked (line 177); all other `yaml.load` mentions are docstring/comment warnings (T-20-02 satisfied).

## Deviations from Plan
None — plan executed exactly as written. No bugs, missing functionality, or blocking issues encountered; Rules 1–4 did not trigger.

## Known Stubs
The following remain stubbed **by design** (Plan 03 / Wave 3 scope, explicitly out of scope for this plan): `audit`, `render_markdown`, `render_json`, `main`. These are tracked by the still-RED Wave-3 test classes and will be implemented in Plan 03.

## Self-Check: PASSED
- `crawler/dupaudit.py` — FOUND (379 lines, contains `SequenceMatcher`, ≥180 lines).
- Commit `e01b206` — FOUND.
- Commit `ac8c207` — FOUND.
- Commit `a3753af` — FOUND.
