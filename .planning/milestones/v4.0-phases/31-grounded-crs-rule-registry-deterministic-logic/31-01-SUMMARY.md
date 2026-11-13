---
phase: 31-grounded-crs-rule-registry-deterministic-logic
plan: 01
subsystem: crs-rule-registry
tags: [pydantic, yaml, grounding, fts5, crs, registry]

# Dependency graph
requires:
  - phase: 25-grounding-gate
    provides: grounding.check_answer fail-closed gate + render_answer
  - phase: 24-search-verb
    provides: searchindex.search / resolve (FTS5 resolver)
  - phase: 29-candidate-vault-pii-perimeter
    provides: crawler.models.vault.FactorGroup Literal (single source of truth)
provides:
  - Typed PII-free CRS rule-row schema (crawler/models/crs_rules.py)
  - Registry engine (load/validate/retrieve-what-you-cite/coverage) reusing the frozen gate
  - REQUIRED_RULE_IDS full-grid manifest (four factor groups)
  - Static no_inlined_volatile_rules gate (RULE-02)
  - PII-free COVERAGE.md markdown emitter (python -m crawler.crs_rules)
affects: [31-02, 31-03, 31-04, 31-05, 32-auditor-vertical-slice]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PII-free public registry as typed pydantic v2 boundary models (extra=forbid, Literal enums)"
    - "Rule row -> grounding-gate answer object (one claim per citation, fail-closed)"
    - "retrieve-what-you-cite mirrors test_document_agents._apply_selection_rule"
    - "Coverage manifest as component-prefix matching over dotted rule_ids"

key-files:
  created:
    - crawler/models/crs_rules.py
    - crawler/crs_rules.py
    - crawler/tests/test_crs_rules.py
  modified: []

key-decisions:
  - "row_to_answer emits ONE claim per Citation so every citation's verbatim quote must ground (strict fail-closed)"
  - "validate_registry SKIPS gap:true rows (a documented coverage GAP is not expected to ground; coverage_report surfaces it)"
  - "no_inlined_volatile_rules allow-keys are derived from the registry models (machine_check payload + quote + citation coordinate), so the allow context is defined BY the schema"
  - "Added a 'conversion' MachineCheck kind + gap/gap_reason RuleRow fields beyond the 31-01 sketch to support 31-02 CLB conversion rows and documented GAPs"

patterns-established:
  - "Pattern: PII-free grounded rule row (ARCHITECTURE-v4.0 Pattern 3) as pydantic model"
  - "Pattern: corpus-less synthetic tests build a TemporaryDirectory FTS5 index to prove the loop in CI"

requirements-completed: [RULE-01, RULE-02, RULE-03]

# Metrics
duration: 40min
completed: 2026-07-06
---

# Phase 31 Plan 01: Grounded CRS Rule Registry Engine Summary

**PII-free typed CRS rule-row schema + a registry engine that validates every row through the SHIPPED grounding gate, reproduces cited chunks (retrieve-what-you-cite), reports full-grid coverage, and statically rejects inlined volatile thresholds — all proven corpus-less in CI.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 3 completed
- **Files modified:** 3 created

## Accomplishments
- Defined the interface-first rule-row contract (`RuleRow` composing `Selector`/`Citation`/`MachineCheck`/`VolatilityMeta`) with fail-closed pydantic v2 validation (`extra="forbid"`, Literal enums, `relpath#ordinal` citation shape, citation_index range checks, duplicate-rule_id guard).
- Built the registry engine that REUSES the frozen v3.x trust path verbatim (`grounding.check_answer`, `searchindex.search`/`resolve`) — grep-asserted, never forked.
- Implemented `REQUIRED_RULE_IDS` (the authoritative four-group grid) + `coverage_report` (present/missing/gaps) + a deterministic PII-free `COVERAGE.md` markdown emitter.
- Implemented `no_inlined_volatile_rules` — the static RULE-02 gate — with allow-keys derived from the registry models and comment/heading stripping so a docstring can't self-invalidate it.
- 16 corpus-less synthetic tests build a `TemporaryDirectory` FTS5 index and drive the whole loop, so a corpus-less green is a real mechanism proof.

## Task Commits

1. **Task 1: Typed CRS rule-row schema** - `5cac068` (feat)
2. **Task 2: Registry loader + grounding-validation + retrieve-what-you-cite + coverage** - `06f42be` (feat, TDD)
3. **Task 3: Static "no inlined volatile rule" check** - `8fd37c1` (feat, TDD)

## Files Created/Modified
- `crawler/models/crs_rules.py` - PII-free pydantic v2 boundary models for the rule row.
- `crawler/crs_rules.py` - Registry engine: load/validate/retrieve/coverage + static gate + COVERAGE emitter.
- `crawler/tests/test_crs_rules.py` - 16 corpus-less synthetic tests (schema, gate reuse, retrieve, coverage, static gate).

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_crs_rules.py -q` → 16 passed.
- Engine surface exports load_registry, validate_registry, retrieve_what_you_cite, coverage_report, no_inlined_volatile_rules, row_to_answer, REQUIRED_RULE_IDS.
- `grep` confirms grounding.check_answer + searchindex.search/resolve are CALLED (frozen gate reused, not forked).
- No regression: `test_grounding.py` + `test_searchindex.py` → 105 passed.

## Deviations from Plan

### Auto-added (Rule 2 — required functionality for downstream plans)

**1. [Rule 2] Added a `conversion` MachineCheck kind and `gap`/`gap_reason` RuleRow fields**
- **Found during:** Task 1 (schema), reconciling the 31-01 sketch against 31-02/31-03 needs.
- **Issue:** 31-02 authors CLB/NCLC conversion rows (`machine_check.kind = conversion`) and 31-02/03 require a `gap:true` marker for documented coverage GAPs — neither was in the literal 31-01 kind list.
- **Fix:** Added `"conversion"` to `MachineCheckKind` and `gap: bool` + `gap_reason: str | None` to `RuleRow`; both are validated and consumed by `coverage_report`/`validate_registry`.
- **Files modified:** crawler/models/crs_rules.py
- **Commit:** `5cac068`

## Known Stubs
None — the engine is fully exercised against a synthetic index. Content YAML files are authored in Plans 31-02/31-03 (by design; this plan is the engine).

## Self-Check: PASSED
- FOUND: crawler/models/crs_rules.py, crawler/crs_rules.py, crawler/tests/test_crs_rules.py
- FOUND commits: 5cac068, 06f42be, 8fd37c1
