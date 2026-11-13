---
phase: 43-enhanced-noc-work-duty-review-worksheet
plan: 02
subsystem: api

tags: [noc-2021, review.noc, inert-sidecar, staleness, grounding, vault, quarantine, never-green, pii-light, ast-scan]

# Dependency graph
requires:
  - phase: 43-01
    provides: "noc_worksheet.resolve_noc_spans + split_duties (deterministic (duty_id, duty_sha) key), born-pending noc_duty/noc_lead_statement values on the inert review.noc factor"
  - phase: 30-extraction-confirmation-store
    provides: "vault.audit_eligible_values / is_audit_eligible / is_stale (5-key Layer 1), confirm_value"
  - phase: 25-retrieval
    provides: "searchindex.resolve exact chunk_id lookup + chunk_sha fingerprint (Layer 2 drift)"
  - phase: 25-grounding
    provides: "grounding.quote_is_grounded retrieve-what-you-cite predicate (Layer 2 drift)"
  - phase: 42-legacy-physician-arranged-employment-policy-resolver
    provides: "crawler/policy_offer.py inert-sidecar template (closed PUBLIC_FIELDS, constant never-green status)"
provides:
  - "crawler/noc_review.py: inert AT-RISK/GAP/N/A duty-review roll-up (review_noc_duties) — structurally never SUBSTANTIATED, no score; reads only audit_eligible_values('review.noc'), never core.work"
  - "Two-layer staleness: Layer 1 = shipped 5-key is_audit_eligible; Layer 2 = searchindex.resolve + grounding.quote_is_grounded corpus-drift re-check"
  - "Current-worksheet-key dedup: counts a confirmed duty only if its parsed (duty_id, duty_sha) is in the live noc_worksheet.split_duties key set, each duty_id once (old drifted value ignored -> confirmed_count <= duty_count)"
  - "Closed PII-light PUBLIC_FIELDS contract + AST-aware no-scoring / no-SUBSTANTIATED source scan over both NOC modules"
affects: [43-03-cli, 43-04-core-work-byte-identity, 45-mec-integrator]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies — composes only frozen primitives (pyproject/poetry.lock byte-identical)
  patterns:
    - "Inert sidecar (policy_offer clone): a pure read-only roll-up returning a closed PII-light dict with a status structurally constrained to {AT-RISK, GAP, N/A}; no SUBSTANTIATED branch, no crs_points/score, not registered in auditors, not in FULL_GRID_FACTORS"
    - "Two-layer staleness: the generic 5-key is_stale (Layer 1) does NOT bind the corpus chunk, so a sidecar-side Layer-2 resolve+quote re-check catches re-crawl drift with no 6th schema column and no status mutation"
    - "Current-worksheet-key membership as count-inflation defense: rebuild {(duty_id, duty_sha)} from the SAME deterministic Plan-01 split and count only current keys, collapsing per duty_id (T43-09)"
    - "Prose-immune AST source scan: exclude docstring string-constants so 'never SUBSTANTIATED' documentation cannot false-trip the no-SUBSTANTIATED / no-scoring assertion"

key-files:
  created:
    - crawler/noc_review.py
  modified:
    - crawler/tests/test_noc_review.py

key-decisions:
  - "duty_count = size of the current DUTY key set (from split_duties, matches Plan-01's duty_count); the lead statement carries its own separate current key and gates the terminal reason but is not counted in duty_count"
  - "Status mapping: no current worksheet -> N/A; an explicit rejection of a current-key duty -> GAP; everything else (none/partial/stale/drifted) -> AT-RISK unresolved_noc; lead + all current duties confirmed+fresh+grounded -> AT-RISK duty_review_manual (STILL not green)"
  - "Layer 2 gates BOTH the lead and each duty; a resolve miss OR a quote mismatch demotes even a Layer-1-eligible, current-key value"
  - "noc_review.py is strictly read-only: no INSERT/UPDATE/DELETE/ALTER, no confirm_value, no add_extracted_value — drift/dedup live entirely in the read path (no migration, no status mutation)"
  - "NOC-02/NOC-03 kept Pending: the sidecar library ships here, but the user-facing per-duty review flow (Plan 03 CLI) and the freeze/conformance proof (Plan 04) must close before the requirements are marked complete (continues commit 38696df)"

patterns-established:
  - "Pattern: inert never-green sidecar with a closed PII-light PUBLIC_FIELDS constant asserted structurally"
  - "Pattern: two-layer staleness (shipped 5-key gate + sidecar corpus-drift re-check) with zero schema change"
  - "Pattern: AST-aware, docstring-excluding source scan for forbidden primitives (scoring libs, .ratio/SequenceMatcher, code-level SUBSTANTIATED)"

requirements-completed: []  # NOC-02/NOC-03 intentionally remain Pending until the review flow closes (Plans 03-04); see key-decisions

# Metrics
duration: 13min
completed: 2026-07-19
---

# Phase 43 Plan 02: Inert NOC Duty-Review Sidecar + Two-Layer Staleness Summary

**A pure, read-only `noc_review` sidecar that rolls the born-pending/confirmed `review.noc` duty values into a closed PII-light `{AT-RISK, GAP, N/A}` verdict — structurally incapable of `SUBSTANTIATED` or a score — with Layer-1 (5-key) + Layer-2 (corpus-drift) staleness and current-worksheet-key dedup so stale/drifted/old-sha confirmations can never inflate the count or green the review.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-07-19T09:51:56Z
- **Completed:** 2026-07-19T10:05:11Z
- **Tasks:** 2 (both complete, each RED→GREEN)
- **Files modified:** 2 (1 created, 1 extended)

## Accomplishments

- **`crawler/noc_review.py` (new, 211 lines, pure stdlib + frozen primitives):** `review_noc_duties(vault, db, noc_code)` clones the `crawler/policy_offer.py` inert-sidecar shape — a closed `PUBLIC_FIELDS` constant `(noc_code, duty_count, confirmed_count, status, reason, citations)` and a status literal set of exactly `{AT-RISK, GAP, N/A}`. There is **no** `return "SUBSTANTIATED"` branch and **no** `crs_points`/score anywhere; the terminal all-confirmed state is `("AT-RISK", "duty_review_manual")` — STILL not green (Pitfall 1 / NOC-03).
- **Factor isolation (B1, T43-06):** duty values are read ONLY via `vault.audit_eligible_values(vault, "review.noc")` — the dedicated inert factor. The string `core.work` appears in `noc_review.py` only as negated prose; the frozen `core.work` audit is never read or touched.
- **Layer 1 (NOC-02):** eligibility delegates entirely to the shipped 5-key `is_audit_eligible` choke point (via `audit_eligible_values`) — no re-implemented staleness.
- **Current-worksheet-key dedup (T43-09):** the current `{(duty_id, duty_sha)}` set is rebuilt from the SAME deterministic Plan-01 `resolve_noc_spans` + `split_duties` (no second retrieval/split path); a confirmed value counts only if its parsed key is current, collapsed per `duty_id`, so an old drifted value (superseded `duty_sha`) or an orphan key is ignored and `confirmed_count <= duty_count` always.
- **Layer 2 (NOC-02, Pitfall 3 / T43-01):** `_layer2_fresh` re-`searchindex.resolve`s each surviving value's stored `citation` and re-verifies the stored `raw_text` with `grounding.quote_is_grounded`; a resolve miss (unknown id / chunk-sha drift → `None`) OR a quote mismatch demotes the duty to unresolved — even when Layer 1 and current-key membership both pass. Binary grounded/not-grounded only — no score/overlap.
- **Read-only / no-migration:** `noc_review.py` contains no `INSERT/UPDATE/DELETE/ALTER`, no `confirm_value`, no `add_extracted_value`, no `commit` — drift and dedup live in the read path, so there is no 6th schema column and no status mutation.
- **Test slice (+510 lines in `crawler/tests/test_noc_review.py`):** never-green + closed-PII-set proof; N/A on an unresolvable NOC; partial/rejected(→GAP)/Layer-1-stale/Layer-2-quote-drift/Layer-2-citation-miss/changed-sha-replacement demotion; an exhaustive 8-class input sweep asserting no case is `SUBSTANTIATED` and `confirmed_count <= duty_count`; and an AST-aware, docstring-excluding no-scoring scan over BOTH NOC modules.

## Task Commits

Each task followed the RED → GREEN TDD gate and was committed atomically:

1. **Task 1: inert `noc_review` sidecar (closed PII-light, structurally never-green)**
   - RED  — `471bfe4` (test): never-green + closed-PII + inert RED tests
   - GREEN — `cb31895` (feat): `review_noc_duties` sidecar + current-key rebuild + Layer 1 + roll-up; hardened the Task-1 inert test to a prose-immune AST import check
2. **Task 2: two-layer staleness + current-key dedup demotion + no-scoring sweep**
   - RED  — `cc935f0` (test): Layer-1 stale + Layer-2 drift + changed-sha + exhaustive sweep + AST no-scoring scan (Layer-2 drift cases RED)
   - GREEN — `c71fcb5` (feat): `_layer2_fresh` corpus-drift re-check wired into the count loop (both lead + duties)

**Plan metadata:** _(final docs commit — see completion)_

## Files Created/Modified

- `crawler/noc_review.py` (211 lines, **created**) — inert AT-RISK/GAP/N/A duty-review roll-up with two-layer staleness + current-worksheet-key dedup; closed PII-light dict; reads only `review.noc`.
- `crawler/tests/test_noc_review.py` (+510 lines, now 811) — `NocSidecarRollup` (Task 1) + `NocTwoLayerStaleness` (Task 2) classes and shared seeding helpers (all confirmed/stale/drifted values minted through the shipped Plan-01 generator + `vault.confirm_value`).

## Decisions Made

- `duty_count` counts DUTIES only (from `split_duties`, matching Plan 01); the lead statement is a separate current key that gates the terminal `duty_review_manual` reason.
- `GAP` is reserved for an explicit rejection of a current-key duty (read directly, since `audit_eligible_values` correctly excludes rejected rows); all non-rejection incompleteness (none/partial/stale/drifted) is `AT-RISK unresolved_noc`; `N/A` is only an unresolvable/absent current worksheet.
- Layer 2 gates both the lead and each duty; the check is fail-closed on a resolve miss or a quote mismatch.
- NOC-02/NOC-03 remain **Pending** in REQUIREMENTS.md — the library ships here; the user-facing review flow (Plan 03) and freeze/conformance proof (Plan 04) must close first.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task-1 inert test was a raw-source grep that false-tripped on docstring prose**
- **Found during:** Task 1 GREEN verification.
- **Issue:** The first draft of `test_sidecar_inert_imports_no_auditors_no_score` asserted `"crawler.auditors" not in <raw source>`. The module docstring legitimately documents that the sidecar is NOT wired into `crawler.auditors`, so the naive grep false-failed — exactly the prose false-trip the plan warns about for the no-SUBSTANTIATED scan.
- **Fix:** Rewrote the check to parse the module with `ast` and inspect ACTUAL `Import`/`ImportFrom` nodes (prose-immune), plus assert no `crs_points`/`score` binding is defined.
- **Files modified:** `crawler/tests/test_noc_review.py`
- **Committed in:** `cb31895` (folded into Task 1 GREEN, as it is the test authored for that task).

**2. [Rule 1 - Bug] `_current_duty_value_id` test helper omitted the lead key**
- **Found during:** Task 2 RED (first run).
- **Issue:** The helper rebuilt the current key set from `split_duties` only (duties), so resolving the lead item `21232:1:00` raised `AssertionError: no current value`, failing the partial-confirm test and the sweep's `partial` subcase for the wrong reason.
- **Fix:** Added the lead key `(f"{code}:1:00", chunk_sha(lead_text))` to the helper's current set. After the fix, only the two intended Layer-2 drift tests were RED.
- **Files modified:** `crawler/tests/test_noc_review.py`
- **Committed in:** `cc935f0` (Task 2 RED, before the RED gate commit).

---

**Total deviations:** 2 auto-fixed (both test-harness bugs; no source-behavior change). No architectural (Rule 4) changes. No package installs. No authentication gates.

## Issues Encountered

- None blocking. The plan's verification also names the broader `crawler/tests/` sweep, part of which (real-network integration seams) hangs offline; per the Plan-01 precedent those were not run. The offline suites touching this change (`test_noc_review.py`, `test_auditor_dispatch.py`, `test_vault.py`, `test_extraction_store.py`, `test_conformance_v40_no_false_green.py`) all pass.

## Verification Results

- `.venv/bin/python -m pytest crawler/tests/test_noc_review.py -q` → **25 passed, 8 subtests** (full worksheet + sidecar slice green).
- `.venv/bin/python -m pytest crawler/tests/test_auditor_dispatch.py -q` → **5 passed** (auditor registry unchanged; the inert sidecar is absent).
- AST-aware `no_scoring` test → **passes** over BOTH `noc_review.py` and `noc_worksheet.py`: no `difflib`/model/vector import, no `SequenceMatcher(`/`.ratio(`, no `return "SUBSTANTIATED"` branch and no code-level `SUBSTANTIATED` literal (docstring mentions excluded).
- Read-only / no-migration scan of `noc_review.py` → **clean** (no `INSERT/UPDATE/DELETE/ALTER/confirm_value/commit`).
- `core.work` isolation → all 7 occurrences in `noc_review.py` are negated prose; the only factor read is `review.noc`.
- Related offline regression (`test_vault.py` + `test_extraction_store.py` + `test_conformance_v40_no_false_green.py`) → **60 passed, 160 subtests** (no wider regression).
- No-new-dependency gate: `git diff HEAD~4 HEAD -- pyproject.toml poetry.lock` → **empty**.

## Known Stubs

None — the sidecar computes its verdict entirely from resolved corpus keys + shipped quarantine/staleness/grounding primitives; there are no hardcoded empty values, placeholder text, or unwired data sources.

## TDD Gate Compliance

Both `tdd="true"` tasks recorded a `test(...)` RED gate before its `feat(...)` GREEN gate: Task 1 = `471bfe4` → `cb31895`; Task 2 = `cc935f0` → `c71fcb5`. No REFACTOR commit was needed (the code was clean at GREEN).

## Next Phase Readiness

- **Plan 03 (CLI):** `review_noc_duties(vault, db, noc_code)` returns a PII-light closed dict ready to render on `--json` (no `raw_text`/path/`ev_`); the one-duty-at-a-time confirm reuses the shipped `vault confirm` verb (no new confirmation path).
- **Plan 04 (core.work byte-identity + conformance):** the read-only, `review.noc`-scoped, unregistered sidecar is the enabling invariant — Plan 04 asserts wholesale that it is not in `_REGISTRY`/`FULL_GRID_FACTORS`, never summed into any `PublicAuditEnvelope`, and that `core.work` shows zero diff before/after confirmed duty values.
- **REQUIREMENTS:** NOC-02/NOC-03 stay Pending until the above land.

---
*Phase: 43-enhanced-noc-work-duty-review-worksheet*
*Completed: 2026-07-19*

## Self-Check: PASSED
- Files verified on disk: `crawler/noc_review.py`, `crawler/tests/test_noc_review.py`, `43-02-SUMMARY.md` — all FOUND.
- Commits verified in git history: `471bfe4` (Task 1 RED), `cb31895` (Task 1 GREEN), `cc935f0` (Task 2 RED), `c71fcb5` (Task 2 GREEN) — all FOUND.
