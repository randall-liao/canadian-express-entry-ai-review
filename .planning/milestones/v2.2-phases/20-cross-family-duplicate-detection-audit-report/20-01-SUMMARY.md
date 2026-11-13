---
phase: 20-cross-family-duplicate-detection-audit-report
plan: 01
subsystem: testing
tags: [duplicate-detection, audit, unittest, difflib, union-find, contract, tdd-red]

# Dependency graph
requires:
  - phase: pre-existing crawler primitives
    provides: "eval_runner._strip_frontmatter, pipeline sha1 body-hash, profile.normalize_url, contract.envelope, check_publish_safe.scan_text"
provides:
  - "crawler/dupaudit.py — the public interface contract (Doc/Cluster/AuditResult dataclasses + typed stubs) for the offline cross-family duplicate-audit pipeline"
  - "Implemented body_of/body_hash primitives (mirror the crawler's exact-dup definition)"
  - "crawler/tests/test_dupaudit.py — the full failing (RED) Nyquist Wave-0 spec + _make_dup_corpus synthetic fixture"
affects: [20-02, 20-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tests-first Wave-0 contract: dataclasses + NotImplementedError stubs pin the shape Plans 02/03 implement against"
    - "Synthetic multi-family tempdir corpus fixture (mirrors test_json_contract._make_lean_corpus)"
    - "Three distinct duplicate signals kept separate (exact body hash / normalized URL / text overlap), unioned via union-find"

key-files:
  created:
    - crawler/dupaudit.py
    - crawler/tests/test_dupaudit.py
  modified: []

key-decisions:
  - "body_of/body_hash implemented now (trivial); all detection/clustering/report functions are stubs raising NotImplementedError so Wave 0 stays a pure contract"
  - "Near-dup fixture bodies tuned with difflib so the positive pair lands at ratio ≈0.9675 (clusters @0.95) and the negative at ≈0.9007 (does not) — a real threshold-boundary test"
  - "UF (union-find) is a stubbed class (each method raises NotImplementedError) to remain part of the contract without inlining logic"
  - "scripts/check_publish_safe.py imported via sys.path insertion (mirrors scripts/tests convention) since scripts is not a package"

patterns-established:
  - "Hybrid test strategy: detector boundary tests build Doc objects directly (deterministic); corpus-integration tests load via live_docs+parse_doc"
  - "Edge assertions normalized to sets of frozensets for order-insensitive comparison"

requirements-completed: [DUP-01, DUP-02, DUP-03, DUP-04, CLEAN-01, RPT-01, RPT-02, RPT-03]

# Metrics
duration: 18min
completed: 2026-06-11
---

# Phase 20 Plan 01: Nyquist Wave-0 Contract & RED Test Suite Summary

**Established the offline duplicate-audit module's typed interface contract and a complete failing (RED) executable specification — 25 tests pinning DUP-01..04, CLEAN-01, RPT-01..03, and the read-only guarantee — so Plans 02/03 are pure GREEN phases.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-11T04:59:03Z
- **Completed:** 2026-06-11T05:17:00Z
- **Tasks:** 2 completed
- **Files modified:** 2 created

## Accomplishments
- Declared `crawler/dupaudit.py` — a standalone OFFLINE module (no crawl4ai/network) with the full public contract: `Doc`/`Cluster`/`AuditResult` dataclasses, implemented `body_of`/`body_hash`, and `NotImplementedError` stubs for `live_docs`, `parse_doc`, `exact_edges`, `url_edges`, `overlap_edges`, `UF`, `cluster`, `cluster_signals`, `select_canonical`, `audit`, `render_markdown`, `render_json`, `main`.
- Wrote `crawler/tests/test_dupaudit.py` (stdlib `unittest` only) with the `_make_dup_corpus` synthetic multi-family fixture and ten test classes (+ optional real-corpus smoke), discovering 25 tests.
- Suite runs RED exactly as intended: 24 errors, all `NotImplementedError`; zero ImportError/collection errors; the one passing test is the GREEN `scan_text` publish-safety reuse check.
- No new dependency introduced (`git diff pyproject.toml poetry.lock` is empty).

## Task Commits

Each task was committed atomically:

1. **Task 1: Declare the dupaudit module interface contract (typed stubs)** - `00b1ee9` (feat)
2. **Task 2: Write the full RED test suite + synthetic-corpus fixture** - `525bcb2` (test)

_No TDD multi-commit split: Wave 0 is a contract+spec phase, not a feature implementation._

## Files Created/Modified
- `crawler/dupaudit.py` (245 lines) — Public interface contract for the offline cross-family duplicate-audit pipeline; only `body_of`/`body_hash` implemented, all detection/report logic stubbed. Documents the `yaml.safe_load`-only mandate for frontmatter parsing (threat T-20-02).
- `crawler/tests/test_dupaudit.py` (550 lines) — Full Wave-0 RED suite + `_make_dup_corpus(tmp)` fixture planting exact/same-URL/near-dup(0.96)/far(0.90)/singleton docs across three family dirs, noise the 752-filter must exclude, and `.eval.json` siblings in both naming forms (one missing eval).

## Key Decisions
- **`body_of`/`body_hash` implemented now:** trivial primitives that mirror `eval_runner._strip_frontmatter` + `pipeline.py:115` sha1; everything else is a stub so Wave 0 remains a pure contract.
- **Near-dup ratios empirically tuned:** the positive pair (`_near_body`) measures ratio ≈0.9675 and clusters at 0.95; the negative (`_far_body`) measures ≈0.9007 and does not — a genuine threshold-boundary test, not a hand-waved one.
- **`cluster_signals` included in the contract:** added during plan-check; the Plan-02 producer for `Cluster.signals`, tested independently in `TestCluster`.

## Verification
- `poetry run python -c "import crawler.dupaudit"` — succeeds, all 18 public symbols present (Task 1 verify: `contract ok`).
- `body_hash` equals `sha1(body-minus-frontmatter)` — verified.
- `poetry run python -m unittest crawler.tests.test_dupaudit -v` — 25 tests discovered, suite RED (24 `NotImplementedError`, 0 ImportError/collection errors); the 1 pass is the `scan_text` reuse test.
- `git diff --stat pyproject.toml poetry.lock` — empty (no new dependency).
- No `pytest`/`crawl4ai`/network imports in either file.

## Deviations from Plan

None — plan executed exactly as written. Two trivial cleanups (removed an unused `from dataclasses import field` in the module and an unused `import os` in the test) were made before commit; neither alters behavior or scope.

## Known Stubs

All non-trivial functions in `crawler/dupaudit.py` are intentional contract stubs raising `NotImplementedError` (`live_docs`, `parse_doc`, `exact_edges`, `url_edges`, `overlap_edges`, `UF`, `cluster`, `cluster_signals`, `select_canonical`, `audit`, `render_markdown`, `render_json`, `main`). This is the deliberate Wave-0 (RED) state — these are implemented in Plan 02 (detectors/clustering/canonical) and Plan 03 (`audit`/render/`main`). The RED test suite is the executable specification that gates those implementations.

## Self-Check: PASSED
- FOUND: crawler/dupaudit.py
- FOUND: crawler/tests/test_dupaudit.py
- FOUND commit: 00b1ee9 (Task 1)
- FOUND commit: 525bcb2 (Task 2)
