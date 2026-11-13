# Phase 35: Coverage Completion - Research

**Researched:** 2026-07-17
**Domain:** Corpus-grounded CRS point pricing + quarantined document-evidence extraction on the shipped v4.0 auditor (local-first, PII-safe, deterministic Python + grounded YAML)
**Confidence:** HIGH (all four requirements verified against the live code and `corpus/index.db`)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Preserve the frozen `search` -> `--cite` -> grounding gate -> JSON envelope path.
- Close language-point coverage with corpus-grounded registry data; never fabricate a point value or relax a decider.
- Surface any still-unpriced substantiated factor as unresolved.
- Close sibling support on the extraction/evidence side with pending-first, field-level confirmation and claimed-scoped linkage.
- Keep sibling evidence fields in one shared vocabulary and pin producer/consumer agreement to prevent drift.
- Preserve vault-only PII storage, `ev_` evidence/corpus citation namespace separation, and screening-not-legal-advice framing.

### Agent Discretion

All remaining implementation choices are at the agent's discretion. Prefer existing registry, extraction, vocabulary, migration, and real-seam test patterns. Add no runtime dependency.

### Specific Ideas (in scope)

- Pin the set of supported first-language benchmark outputs to grounded point rows.
- Keep ambiguous, missing, stale, rejected, or low-quality sibling evidence fail-closed.

### Deferred Ideas (OUT OF SCOPE)

Legacy arranged-employment resolution, live DLI/PGWP lookup, NOC-duty semantic review, MEC sidecars, and model-based semantic relationship inference remain out of scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COV-01 | Applicant receives grounded first-official-language points for **every benchmark level** emitted by the supported test-conversion tables, including higher-CLB, without fabricated or silently missing points | §COV-01 — data-only addition of grounded `PointsEntry` rows (CLB 3–8, 10) to `core.language.first.points`; all quotes VERIFIED groundable in `guidance/crs-criteria.md#006`; no code change to `score_factor`/`_grounded_points` |
| COV-02 | Applicant sees any `SUBSTANTIATED` factor whose points still cannot be grounded as an explicit unresolved/unpriced item rather than a complete-looking result | §COV-02 — surfacing mechanism in `auditor.run_full_audit` + `audit_report._render_factor_card_markdown` + `models/audit` counts; anti-drift pin over the conversion-emitted level set |
| COV-03 | Applicant can import sibling relationship, status, age, and Canadian-residence proof into the vault, extract it as `pending`, and confirm/correct/reject each field before audit use | §COV-03 — new sibling `doc_type` + `_FIELD_SPECS`, new `FieldName` Literal members, new shared-vocab module `crawler/siblingfields.py` (mirrors `testtypes.py`), pinned by anti-drift test; quarantine/confirm path reused unchanged |
| COV-04 | `additional.sibling` returns `SUBSTANTIATED` only when the claimed-scoped, confirmed evidence chain satisfies the corpus-grounded sibling rule; missing/stale/ambiguous/cross-factor evidence — AND a confirmed minor sibling — stays `GAP`/`AT-RISK` | §COV-04 — make `decide_sibling` require confirmed relationship+status+residence + an ENFORCED grounded adult gate (age at the ITA date ≥ the grounded `sibling_min_age` threshold row); grounded points row already resolves (`additional.sibling`, 15 pts, `crs-criteria.md#019`) and a new grounded `additional.sibling.adult` threshold row grounds `min_value: 18` from `crs-criteria.md#018` ("18 years or older"); claimed-scoping + `is_audit_eligible` provide the rest of the fail-closed by construction |
</phase_requirements>

## Summary

Phase 35 closes two carried-forward fail-closed **coverage gaps** on the already-shipped v4.0 CRS auditor. It is a **data + one-decider + extraction-vocabulary** phase, not a new-machinery phase. Both gaps are the exact tech-debt items the shipped code documents in its own comments and skipped-assertions.

**Gap 1 — language pricing (COV-01/02).** The `core.language.first.points` registry row grounds **only CLB 9**, but the shipped conversion tables emit CLB levels **{3,4,5,6,7,8,9,10}** (verified). `_sum_points` sums grounded per-ability points and returns `None` if *any* ability is un-priced, so a qualified applicant whose lowest ability is not exactly CLB 9 currently reaches `SUBSTANTIATED` with `substantiated_points=None` — a truthful-but-incomplete result that then contributes **0** to `substantiated_total` silently. The fix is **data-only**: add grounded `PointsEntry` rows for the remaining bands, each carrying a verbatim quote that I confirmed is a substring of chunk `guidance/crs-criteria.md#006`. No auditor code changes; `score_factor`/`_grounded_points` already generalize over levels. COV-02 adds a *structural* unpriced-surfacing net so any residual `SUBSTANTIATED`-but-`None`-points card (e.g. second language at CLB≠9) is shown as unresolved instead of silently zeroed.

**Gap 2 — sibling evidence chain (COV-03/04).** The `additional.sibling` rule row is **already grounded** (15 pts, `crs-criteria.md#019`, verified 1/1), but `decide_sibling` is a hard-coded `GAP` stub because the EXTRACT-01 field vocabulary carries no sibling fields — the decider is structurally unreachable. The fix mirrors the Phase-30 30-05 pattern exactly: close the gap on the **extraction side** (new field names + a shared-vocabulary module pinned by an anti-drift test), then make `decide_sibling` a real fail-closed join over confirmed relationship + status + Canadian-residence (+ adult) evidence. The decider is **never relaxed** — it only becomes reachable.

**Primary recommendation:** Two mostly-parallel tracks. **Track A (COV-01/02):** add grounded CLB 3–8,10 point rows to `core.yaml`; add the unpriced-surfacing net + an anti-drift pin. **Track B (COV-03/04):** add sibling field vocabulary (`crawler/siblingfields.py` + `FieldName` + `_FIELD_SPECS` + `_DOC_TYPE_FACTOR`), then implement the fail-closed `decide_sibling` join and extend the real `import→extract→confirm→audit` seam test. **Zero new runtime dependencies** — everything uses the shipped `pyyaml`/`pydantic`/`platformdirs` + stdlib. No DB migration required.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Higher-CLB first-language point grounding (COV-01) | Grounded rule registry (`data/crs_rules/core.yaml` + `crs_rules`) | — | Volatile point values live ONLY in grounded rows with verbatim quotes; the deterministic math tier reads them |
| Deterministic per-ability point sum (COV-01) | CRS math (`crs_audit.score_factor`, `auditors/core._sum_points`) | — | Already generalizes over levels; consumes grounded rows, carries no literal |
| Unpriced-`SUBSTANTIATED` surfacing (COV-02) | Audit spine + report render (`auditor.run_full_audit`, `audit_report`) | Public boundary (`models/audit` counts) | The total roll-up + report is where "no points" must become an explicit unresolved item, not a silent 0 |
| Sibling document import + quarantined extraction (COV-03) | Extraction vocabulary + engine (`models/vault.FieldName`, `extraction._FIELD_SPECS`, new `siblingfields.py`) | Vault store (`vault.add_extracted_value`, `confirm_value`) | Extraction is the sole non-grounded step; the vault owns the pending→confirm quarantine invariant |
| Sibling verdict (COV-04) | Additional-points decider (`auditors/additional.decide_sibling`) | Grounded rule (`data/crs_rules/additional.yaml`) + audit spine (claimed-scoping) | The decider is a fail-closed deterministic join over confirmed evidence + the grounded rule; the spine supplies claimed-scoped `by_field` |
| Claimed-scoped evidence→factor linkage (COV-03/04) | Extraction linkage (`extraction._resolve_factor`, `_DOC_TYPE_FACTOR`) | Audit spine (`vault.audit_eligible_values` filtered by `factor_id`) | A value reaches a factor's `by_field` only if the document links to a CLAIMED factor — cross-factor contamination is structurally impossible |

## Standard Stack

### Core (all already in the locked graph — no additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | `>=3.10,<4.0` | Runtime for all Phase-35 code | Shipped floor; nothing newer needed |
| `pydantic` | 2.13.4 | Boundary models: `FieldName` Literal (extraction vocab), `PrivateFactorCard`, `PublicAuditEnvelope` | `extra="forbid"` + `Literal` reject out-of-vocab field names / injected keys at load — the structural PII/vocab firewall |
| `pyyaml` | 6.0.3 | Higher-CLB point rows + (new) sibling doc field specs are plain YAML compiled to pydantic rows | More grounded rows, not new machinery |
| `sqlite3` (stdlib) | — | Vault store; sibling evidence is a new `field_name` **row**, no DDL | `extracted_values.field_name` is free `TEXT` — vocabulary is enforced at the pydantic boundary, not by a SQL CHECK |
| `argparse` (stdlib) | — | `vault import/extract/confirm` already accept free-form `--doc-type` + `--factor` override | No CLI change required for sibling import |
| `hashlib` / `re` / `json` (stdlib) | — | Content-addressing, field regexes, JSON report render | Shipped patterns (`testtypes.py`, `extraction.py`) |

**Installation:** none. `poetry install` is unchanged. The only justified `pyproject.toml` edit is **non-dependency metadata** (optionally a v4.1 pytest sub-marker) — no new `[project.dependencies]` entry.

**Version verification (ecosystem = pypi, all pre-existing):**
```bash
.venv/bin/python -c "import pydantic, yaml, platformdirs; print(pydantic.VERSION, yaml.__version__, platformdirs.__version__)"
# 2.13.4 6.0.3 4.10.0  [VERIFIED: local .venv]
```

### Alternatives Considered (all rejected — anti-stack)

| Instead of | Could Use | Tradeoff / Why Rejected |
|------------|-----------|-------------------------|
| A grounded points row per CLB band | Hard-code a `{level: points}` dict in `core.py` | **Violates the frozen no-inlined-volatile-rules gate** (a `CLB\d`/points literal in `.py` is a `clb_benchmark`/`points_literal` violation) and the "never fabricate a point value" decision. Points MUST live in a grounded row with a verbatim quote. |
| A new `siblingfields.py` shared-vocab module | Inline sibling field names in `extraction.py` + re-derive in `decide_sibling` | Re-creates BLOCKER-B drift risk (producer/consumer diverge silently). The locked decision mandates ONE shared vocabulary pinned producer↔consumer. |
| Additive pydantic Literal member | A SQLite `CHECK` constraint + `PRAGMA user_version` migration | Unnecessary: `field_name` is enforced at the model boundary, not in SQL. No migration needed; adding a `Literal` member is a pure additive vocab change. |

## Package Legitimacy Audit

> **Not applicable — this phase installs NO external packages.** Every dependency (`pydantic`, `pyyaml`, `platformdirs`, plus stdlib) already shipped with v4.0 and is verified present in `.venv`. There is no registry lookup to perform because there is nothing new to install.

**Packages removed due to [SLOP] verdict:** none (no new packages proposed).
**Packages flagged as suspicious [SUS]:** none.
**Explicit conclusion:** **NO NEW RUNTIME DEPENDENCY.** Confirmed against `pyproject.toml` (`dependencies = [pyyaml, pydantic, platformdirs]`) — Phase 35 adds grounded YAML rows, one decider body, a stdlib vocab module, and tests, all on the shipped stack.

## Architecture Patterns

### System Architecture Diagram

```
COV-01/02 (language pricing) — DATA + ROLL-UP
──────────────────────────────────────────────
 raw ability scores ──> crs_audit.to_clb ──> CLB level {3..10}
   (confirmed vault evidence)                     │
                                                  ▼
 core.yaml: core.language.first.points  ──> score_factor(level) ──> per-ability points
   [ADD grounded rows CLB 3-8,10]                 │
   (verbatim quotes ⊂ crs-criteria.md#006)        ▼
                                        _sum_points(4 abilities)
                                                  │
                        ┌── all priced ──> substantiated_points (int)
                        └── any None ────> substantiated_points = None
                                                  │
                                                  ▼
                        run_full_audit: substantiated_total = Σ(points or 0)
                                                  │
                   [COV-02 NET] detect verdict==SUBSTANTIATED & points is None
                                                  │
                                                  ▼
                  audit_report render: explicit "points UNRESOLVED (unpriced)"
                  public envelope counts["unpriced"] += 1   (no schema change)

COV-03/04 (sibling chain) — EXTRACTION VOCAB + FAIL-CLOSED DECIDER
──────────────────────────────────────────────────────────────────
 vault import --doc-type sibling_proof ─> documents row
                                                  │
 extraction.extract_document ─> _extract_fields(sibling_proof, text)
   using _FIELD_SPECS["sibling_proof"]            │
   (field names pinned by crawler/siblingfields.py)
                                                  ▼
 add_extracted_value  ── FORCES confirmation_status='pending' (quarantine)
   factor linkage via _DOC_TYPE_FACTOR["sibling_proof"]="additional.sibling"
   ── linked ONLY if additional.sibling is CLAIMED (else UNLINKED, fail-closed)
                                                  │
 vault confirm --value-id ... (per field: confirm|correct|reject; binds 5 staleness keys)
                                                  │
                                                  ▼
 audit_one("additional.sibling"):
   gate additional.sibling rule (grounds: crs-criteria.md#019 [+ #018 for 18+])
   by_field = audit_eligible_values(additional.sibling)  # confirmed+ok+not-stale ONLY
                                                  │
                                                  ▼
 decide_sibling(ctx): require relationship + status + residence (+ adult)
   ├── all confirmed & present ─> SUBSTANTIATED, 15 pts (grounded row)
   └── missing/ambiguous/stale/cross-factor ─> GAP / AT-RISK  (never green)
```

### Recommended Project Structure (files touched — all existing except one new module)

```
crawler/
├── data/crs_rules/core.yaml         # MODIFY-data: add CLB 3-8,10 rows to core.language.first.points
├── data/crs_rules/additional.yaml   # MODIFY-data (optional): add #018 "18 years or older" citation to additional.sibling
├── models/vault.py                  # MODIFY: add sibling members to FieldName Literal
├── models/audit.py                  # MODIFY-small (COV-02): counts["unpriced"] surfacing helper
├── extraction.py                    # MODIFY: _FIELD_SPECS["sibling_proof"], _DOC_TYPE_FACTOR
├── siblingfields.py                 # NEW: shared sibling vocabulary (mirror of testtypes.py)
├── auditors/additional.py           # MODIFY: real fail-closed decide_sibling
├── auditor.py                       # MODIFY-small (COV-02): surface unpriced in roll-up
├── audit_report.py                  # MODIFY-small (COV-02): render explicit unpriced line
└── tests/
    ├── test_language_points_coverage.py     # NEW: COV-01 anti-drift pin (mirror test_crs_conversion_coverage.py)
    ├── test_unpriced_surfacing.py           # NEW: COV-02 net proven
    ├── test_siblingfields_vocab.py          # NEW: COV-03 anti-drift pin (mirror test_testtype_vocab.py)
    ├── test_auditors_additional.py          # EXTEND: decide_sibling truth table
    ├── test_full_audit_real_seam.py         # EXTEND: sibling real seam + update CLB-10 comment/assertion
    └── fixtures/extraction/make_fixtures.py # EXTEND: sibling_proof PDF builder
```

### Pattern 1: Grounded points row per band (COV-01) — data, never code
**What:** Each CLB band is a `PointsEntry` inside the one `core.language.first.points` row, carrying `label`, `level`, `points`, `citation_index`; the row's `citations` list carries one `(chunk_id, quote)` per distinct verbatim table line.
**When to use:** Any volatile CRS number. It is the ONLY place a points literal may appear.
**Example (add to `core.yaml` `core.language.first.points`; mirrors the existing CLB-9 entry):**
```yaml
# Source: crawler/data/crs_rules/core.yaml lines 221-253 (existing shape)
# corpus VERIFIED: every quote below is a substring of guidance/crs-criteria.md#006
    citations:
      - chunk_id: guidance/crs-criteria.md#006
        quote: "CLB 9  | 29  | 31"           # citation_index 0 (existing)
      - chunk_id: guidance/crs-criteria.md#006
        quote: "Less than CLB 4  | 0  | 0"    # citation_index 1
      - chunk_id: guidance/crs-criteria.md#006
        quote: "CLB 4 or 5  | 6  | 6"         # citation_index 2
      - chunk_id: guidance/crs-criteria.md#006
        quote: "CLB 6  | 8  | 9"              # citation_index 3
      - chunk_id: guidance/crs-criteria.md#006
        quote: "CLB 7  | 16  | 17"            # citation_index 4
      - chunk_id: guidance/crs-criteria.md#006
        quote: "CLB 8  | 22  | 23"            # citation_index 5
      - chunk_id: guidance/crs-criteria.md#006
        quote: "CLB 10 or more  | 32  | 34"   # citation_index 6
    machine_check:
      kind: points_table
      field: clb_per_ability
      points_by_level:
        - {label: clb9_with_spouse,     level: 9,  points: 29, citation_index: 0}
        - {label: clb9_without_spouse,  level: 9,  points: 31, citation_index: 0}
        - {label: clb3_with_spouse,     level: 3,  points: 0,  citation_index: 1}
        - {label: clb3_without_spouse,  level: 3,  points: 0,  citation_index: 1}
        - {label: clb4_with_spouse,     level: 4,  points: 6,  citation_index: 2}
        - {label: clb4_without_spouse,  level: 4,  points: 6,  citation_index: 2}
        - {label: clb5_with_spouse,     level: 5,  points: 6,  citation_index: 2}
        - {label: clb5_without_spouse,  level: 5,  points: 6,  citation_index: 2}
        - {label: clb6_with_spouse,     level: 6,  points: 8,  citation_index: 3}
        - {label: clb6_without_spouse,  level: 6,  points: 9,  citation_index: 3}
        - {label: clb7_with_spouse,     level: 7,  points: 16, citation_index: 4}
        - {label: clb7_without_spouse,  level: 7,  points: 17, citation_index: 4}
        - {label: clb8_with_spouse,     level: 8,  points: 22, citation_index: 5}
        - {label: clb8_without_spouse,  level: 8,  points: 23, citation_index: 5}
        - {label: clb10_with_spouse,    level: 10, points: 32, citation_index: 6}
        - {label: clb10_without_spouse, level: 10, points: 34, citation_index: 6}
```
> **Column semantics (VERIFIED against existing CLB-9 row + corpus header "With a spouse or common-law partner"):** first number column = `with_spouse`, second = `without_spouse`. The existing row has `clb9_with_spouse=29`, `clb9_without_spouse=31` and quote `"CLB 9  | 29  | 31"` — so 29 is the with-spouse value. Do not transpose.
> **`_grounded_points`/`score_factor` select the mode column by the `with_spouse`/`without_spouse` substring in the label** — the labels above are exactly the discriminators those functions read (`crawler/auditors/core.py:166-186`, `crawler/crs_audit.py:272-283`). No code change is required.

### Pattern 2: Shared vocabulary pinned producer↔consumer (COV-03) — the `testtypes.py` template
**What:** A stdlib module holding ONLY names/enums (no points), pinned set-equal to the model boundary + registry by an anti-drift test; imported by both the extractor and the decider.
**When to use:** Any field/enum that must agree across extraction and audit (the locked "one shared vocabulary" decision).
**Example (new `crawler/siblingfields.py`, mirroring `crawler/testtypes.py`):**
```python
# Source: crawler/testtypes.py (the shipped template — names only, NO volatile numbers)
from __future__ import annotations

# The sibling evidence fields (names only — no CRS points, stays OUTSIDE the
# no_inlined_volatile_rules surface). Asserted set-equal to the FieldName Literal
# additions AND to what decide_sibling consumes by test_siblingfields_vocab.py.
SIBLING_FIELDS: frozenset[str] = frozenset({
    "sibling_relationship",   # brother / sister
    "sibling_status",         # citizen | permanent_resident
    "sibling_residence",      # lives_in_canada evidence
    "sibling_date_of_birth",  # adult (18+) check; reuses the date-normalization path
})

# Accepted enum tokens the decider treats as satisfying each field (fail-closed:
# an unknown token is NOT coerced to an accepted value).
SIBLING_STATUS_ACCEPTED: frozenset[str] = frozenset({"citizen", "permanent_resident"})
SIBLING_RELATIONSHIP_ACCEPTED: frozenset[str] = frozenset({"brother", "sister"})
```

### Pattern 3: Fail-closed deterministic join (COV-04) — never relax the decider
**What:** The decider requires ALL confirmed fields present + grounded, else GAP/AT-RISK; ambiguity/staleness is already filtered upstream by `is_audit_eligible`. The adult (18+) gate is ENFORCED from grounded threshold data — a confirmed minor can never green the factor.
**When to use:** Any new SUBSTANTIATED-reachable factor.
**Example (replace the stub in `crawler/auditors/additional.py`):**
```python
# Source: crawler/auditors/additional.py decide_nomination + decide_age patterns + crawler/siblingfields.py
def decide_sibling(ctx: DecisionContext) -> DecisionResult:
    confirmed = _confirmed_snapshot(ctx.by_field)
    required = ("sibling_relationship", "sibling_status", "sibling_residence",
                "sibling_date_of_birth")
    if any(f not in ctx.by_field for f in required):
        return DecisionResult("GAP", "missing_evidence", confirmed_value=confirmed)
    status = str(_effective_value(ctx.by_field["sibling_status"]))
    relationship = str(_effective_value(ctx.by_field["sibling_relationship"]))
    if (status not in siblingfields.SIBLING_STATUS_ACCEPTED or
            relationship not in siblingfields.SIBLING_RELATIONSHIP_ACCEPTED):
        return DecisionResult("AT-RISK", "unresolved_sibling", confirmed_value=confirmed)
    # ENFORCED grounded adult gate (mirrors decide_age): read min age from the grounded
    # sibling_min_age threshold row (never a literal), pin the sibling's age to the ITA date.
    min_age = _grounded_min_age(ctx.registry, "sibling_min_age")
    if min_age is None or ctx.ita_date is None:
        return DecisionResult("AT-RISK", "unresolved_sibling", confirmed_value=confirmed)
    try:
        age = crs_audit.age_on_date(_effective_value(ctx.by_field["sibling_date_of_birth"]),
                                    ctx.ita_date)
    except (TypeError, ValueError):
        return DecisionResult("AT-RISK", "unresolved_sibling", confirmed_value=confirmed)
    confirmed["sibling_age_on_ita"] = age
    if age < min_age:  # confirmed minor NEVER substantiates (fail-closed)
        return DecisionResult("AT-RISK", "sibling_minor", confirmed_value=confirmed)
    points = _grounded_points(ctx.registry, "additional.sibling", "sibling", spouse_mode=False)
    if points is None:
        return DecisionResult("GAP", "below_threshold", confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          confirmed_value=confirmed, substantiated_points=points)
```
> **VERIFIED:** `_grounded_points(reg, "additional.sibling", "sibling", False) == 15` and `_grounded_min_age(reg, "sibling_min_age") == 18` (read from grounded rows, no literal); the `additional.sibling` points row AND the new `additional.sibling.adult` threshold row each ground 1/1 through the real gate with `agrees_with_citation`/`grounds` both True against `corpus/index.db`; boundary check confirmed via `age_on_date` (on the 18th birthday → 18 → adult; the day before → 17 → AT-RISK `sibling_minor`).

### Anti-Patterns to Avoid
- **Patching pricing in Python.** Any `CLB N`/points literal in `.py` trips the shipped `no_inlined_volatile_rules` gate (`_CLB_RE`, `_VOLATILE_POINTS_RE`). Points belong in a grounded YAML row only.
- **Relaxing `decide_sibling` (or `decide_age`) to "make it green" — including skipping the adult gate.** COV-04 closes the gap on the **extraction/evidence** side; the decider only gains real required fields and an ENFORCED grounded adult threshold. A confirmed minor sibling (age below the grounded `sibling_min_age`) must return AT-RISK `sibling_minor`, never SUBSTANTIATED — citing "18 years or older" without a numeric age comparison is a false-green. Relaxing a decider is the exact mistake the 30-05 decision forbids.
- **Re-deriving sibling field names in two places.** Use `siblingfields.py` as the single source and pin it; do not duplicate the set in `extraction.py` and `additional.py`.
- **Treating a `None`-points `SUBSTANTIATED` card as "complete."** COV-02 exists precisely to stop that; `substantiated_total`'s `points or 0` silently zeroes it today.
- **Fabricating a sibling `doc_type` factor that isn't claimed.** Leave a document UNLINKED (fail-closed) when `additional.sibling` is not in `crs_profile_factors` — this is what `_resolve_factor` already enforces; do not bypass it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLB band → points mapping | A Python dict / if-ladder of point values | Grounded `PointsEntry` rows read by `score_factor` | Volatile values must be grounded + gate-safe; the reader already exists |
| Verbatim-quote grounding of the new rows | A custom substring check | `crs_rules.validate_registry` + `retrieve_what_you_cite` (frozen gate) | The shipped gate is the ONLY trust path; forking it widens the guarantee |
| Field-name vocabulary enforcement | Manual string validation in the extractor | `FieldName` `Literal` in `models/vault.py` (`add_extracted_value` validates at the boundary) | Out-of-vocab field is rejected at load; no ad-hoc validation |
| Sibling doc quarantine (pending→confirm) | New status handling | `vault.add_extracted_value` (forces `pending`) + `confirm_value` + `is_audit_eligible` | The quarantine invariant + 5-key staleness are already implemented and tested |
| Evidence→factor claimed-scoping | New linkage logic in the decider | `extraction._resolve_factor` + `_DOC_TYPE_FACTOR` + `audit_eligible_values(factor_id)` | Cross-factor contamination is already structurally prevented |
| Cross-factor contamination test | Ad-hoc assertion | Extend `test_full_audit_real_seam.py` (real import→extract→confirm→audit) | The real-seam harness already proves BLOCKER-A/B; sibling slots into it |

**Key insight:** Both gaps are "the wiring already exists; the data/vocabulary is missing." The single biggest risk is *helpfully* adding new machinery (a points dict, a second grounding check, a bespoke validator) that quietly forks a frozen guarantee. Add rows and one decider body — nothing else.

## Runtime State Inventory

> Phase 35 is an **additive feature** phase, not a rename/refactor. There is no string to rewrite, but there ARE contract/state surfaces whose additive impact the planner must account for. Each category is answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing candidate vaults (`extracted_values`) have no sibling rows; the `field_name` column is free `TEXT` (no CHECK). Existing audit run JSON under `output/crs-audit/` carries `substantiated_points: null` for un-priced language cards. | **No data migration.** New sibling fields are just new rows going forward. Old audit JSONs are historical; re-running an audit reprices from the updated registry. |
| Live service config | None — no external service; the corpus index and registry are in-repo files. | None — verified: no live service in this phase. |
| OS-registered state | None — no schedulers/daemons/registered processes touched. | None — verified. |
| Secrets/env vars | Only `PR_PERSONAL_DIR` (vault root) is read; unchanged. No new secret/env var. | None — verified. |
| Build artifacts / installed packages | No new package; no egg-info/DDL change. `PARSER_VERSION` in `extraction.py` is one of the 5 staleness keys — **if extraction logic changes, bumping it invalidates prior confirmations (by design).** | If `_FIELD_SPECS`/parser changes alter `PARSER_VERSION`, note that already-confirmed values become stale until re-confirmed (existing SC4 behavior — expected, not a defect). |
| **Schema / vocabulary contract** | `FieldName` `Literal` (`models/vault.py:75-93`) gains sibling members; `PublicAuditEnvelope.counts` (a `dict[str,int]`) may gain an `unpriced` key. `factor_verdicts`/`audit_runs` tables need **no** column change. | **No `PRAGMA user_version` migration.** Additive Literal member + additive dict key only. Confirm `add_extracted_value` accepts the new names (it will once the Literal is extended). |

**Canonical check performed:** after adding sibling field names, `vault.add_extracted_value(..., field_name="sibling_relationship", ...)` must not raise `ValidationError`. This requires the `FieldName` Literal edit to land in the **same change** as the `_FIELD_SPECS` edit, or extraction persists nothing.

## Common Pitfalls

### Pitfall 1: Silent under-pricing masquerading as completeness (COV-01/02)
**What goes wrong:** A `SUBSTANTIATED` language card with `substantiated_points=None` contributes `0` to `substantiated_total` (`sum(c.substantiated_points or 0 ...)`, `auditor.py:332-334`) with no visible signal.
**Why it happens:** `_sum_points` returns `None` if any ability is un-priced, and the roll-up coalesces `None→0`.
**How to avoid:** (a) Ground **every** conversion-emitted level (COV-01 closes first language for {3..10}); (b) add the COV-02 net that flags any remaining `verdict==SUBSTANTIATED and substantiated_points is None`; (c) pin points-coverage set-equal to the conversion-emitted level set with an anti-drift test.
**Warning signs:** A card renders `- Substantiated points: None` while `**SUBSTANTIATED**`; the substantiated total is lower than the sum of claimed points for green cards.

### Pitfall 2: Anti-drift pin scoped too narrowly (COV-01)
**What goes wrong:** Pin CLB 4–10 but forget CLB 3 (PTE Core emits it, verified) — a PTE candidate with a CLB-3 ability stays un-priced.
**Why it happens:** PTE Core's conversion range starts at 3, unlike the other four tests (start at 4).
**How to avoid:** Derive the pin's expected set from the LIVE conversion rows at test time (like `test_crs_conversion_coverage.py` computes `_conversion_bands`), not a hard-coded `range(4,11)`. Ground CLB 3 → `"Less than CLB 4  | 0  | 0"` (0 pts, VERIFIED substring).
**Warning signs:** The pin passes with a hard-coded set but a real PTE fixture yields `None` points.

### Pitfall 3: Extraction persists nothing because the vocabulary edit is split (COV-03)
**What goes wrong:** `_FIELD_SPECS["sibling_proof"]` emits `sibling_relationship`, but `add_extracted_value` raises `ValidationError` because the `FieldName` Literal wasn't extended.
**Why it happens:** The field-name vocabulary is enforced at the pydantic boundary (`models/vault.FieldName`), separate from the extractor spec.
**How to avoid:** Land the `FieldName` Literal member(s), `_FIELD_SPECS`, `_DOC_TYPE_FACTOR`, and `siblingfields.py` set in ONE change; assert them set-equal in `test_siblingfields_vocab.py`.
**Warning signs:** `vault extract` for a sibling doc reports 0 values; a boundary `ValidationError` on an unknown field name.

### Pitfall 4: Cross-factor contamination from a sibling document (COV-04)
**What goes wrong:** A sibling document's fields green (or feed) `core.age` or `additional.nomination`.
**Why it happens:** Would only happen if the doc-type→factor linkage or `by_field` scoping were bypassed.
**How to avoid:** Rely on the shipped guards — `_DOC_TYPE_FACTOR["sibling_proof"]="additional.sibling"`, linkage only to a CLAIMED factor (`_resolve_factor`), and `by_field = audit_eligible_values(factor_id)`. Extend `test_full_audit_real_seam.py::test_real_seam_no_cross_factor_contamination` to assert a sibling doc's evidence never appears under age/nomination and vice-versa.
**Warning signs:** `additional.sibling` evidence ids intersect another factor's; a sibling field linked under a non-sibling `factor_id` in `list_extracted_values`.

### Pitfall 5: Regression in the real-seam test after COV-01 (COV-01)
**What goes wrong:** `test_full_audit_real_seam.py` currently documents (in a comment) that the language card's points are `None` because the fixture converts to CLB 10 and CLB-10 is ungrounded. After COV-01 the card becomes priced (no-spouse total **130**, verified), so the comment is stale and any assertion assuming `None` must be updated.
**Why it happens:** The fixture (L=8.5→CLB10, R=7.5→CLB9, W=7.0→CLB9, S=8.0→CLB10, VERIFIED) is exactly the higher-CLB case COV-01 closes.
**How to avoid:** Update the comment at `test_full_audit_real_seam.py` (the "CLB 10 ... MUST NOT be patched by touching the frozen registry" note) and strengthen the assertion to `lang.substantiated_points == 130` (no-spouse). Note the fixture's `claimed_points=124` < 130, so `score_delta` becomes negative (−6) — a valid over-claim-safe outcome; adjust any assertion that assumed `score_delta is None`.
**Warning signs:** `test_real_seam_substantiated_total_nonzero_and_in_cutoff` fails because the total now includes 130.

### Pitfall 6: Stale conformance placeholder for sibling (COV-03/04)
**What goes wrong:** `test_conformance_v40_no_false_green.py` maps `_FIELD_FOR["additional.sibling"] = "issuer"` (a placeholder, because sibling had no real field). Left unchanged, the no-false-green matrix seeds a non-sibling field for the sibling factor.
**Why it happens:** The placeholder predated any sibling field.
**How to avoid:** Update the mapping to a genuine sibling field (e.g. `sibling_relationship`) so the blocking-state matrix (`pending/rejected/low_quality/ambiguous/stale`) exercises real sibling evidence. (Consolidation of this belongs to Phase 39, but the mapping should be corrected when the field lands to keep conformance honest.)
**Warning signs:** No-false-green matrix "passes" for sibling using an `issuer` field that the sibling decider never reads.

## Code Examples

### Verify a proposed higher-CLB quote grounds before writing the row (COV-01)
```python
# Source: crawler.searchindex.resolve (RETRIEVAL §4) — VERIFIED against corpus/index.db this session
from pathlib import Path
from crawler import searchindex
chunk = searchindex.resolve(Path("corpus/index.db"), "guidance/crs-criteria.md#006")
assert "CLB 10 or more  | 32  | 34" in chunk["text"]   # True (verified)
assert "Less than CLB 4  | 0  | 0" in chunk["text"]    # True (verified)
```

### Confirm the pricing gap is closed for every conversion-emitted level (COV-01 pin)
```python
# Source: mirror of crawler/tests/test_crs_conversion_coverage.py::_conversion_bands
from crawler import crs_rules, crs_audit
reg = crs_rules.load_registry()
levels = {int(e.level) for r in reg.rows if r.machine_check.kind == "conversion" and not r.gap
          for e in (r.machine_check.points_by_level or [])}   # VERIFIED == {3,4,5,6,7,8,9,10}
for lvl in levels:
    for mode in (False, True):
        assert crs_audit.score_factor("core.language.first", lvl, mode, reg) is not None, (lvl, mode)
```

### Confirm the sibling verdict is reachable through grounded data — points AND adult threshold (COV-04)
```python
# Source: crawler/auditors/core._grounded_points + crawler/crs_rules.validate_registry — VERIFIED
from pathlib import Path
from crawler import crs_rules, crs_audit
from crawler.auditors.core import _grounded_points
reg = crs_rules.load_registry()
assert _grounded_points(reg, "additional.sibling", "sibling", False) == 15
# The adult threshold is grounded machine_check data (min_value on a threshold row), never a literal:
def _grounded_min_age(registry, field):
    for r in registry.rows:
        mc = r.machine_check
        if mc.kind == "threshold" and mc.field == field and mc.min_value is not None:
            return mc.min_value
    return None
assert _grounded_min_age(reg, "sibling_min_age") == 18          # VERIFIED once additional.sibling.adult ships
# On the 18th birthday the sibling is an adult; the day before they are a minor (fail-closed):
assert crs_audit.age_on_date("2006-06-15", "2024-06-15") == 18  # adult
assert crs_audit.age_on_date("2006-06-16", "2024-06-15") == 17  # minor -> AT-RISK sibling_minor
sib = crs_rules.Registry(rows=[r for r in reg.rows if r.rule_id.startswith("additional.sibling")])
res = crs_rules.validate_registry(sib, Path("corpus/index.db"))
assert res["grounded"] == res["total"] == 2 and res["violations"] == []   # points row + adult threshold row
```

## State of the Art

| Old Approach (pre-Phase-35) | Current Approach (Phase 35) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| First-language points grounded for CLB 9 only | Grounded for every conversion-emitted band {3–10} | Phase 35 (COV-01) | Higher-CLB (and CLB<9) candidates get a complete, non-fabricated point total |
| `SUBSTANTIATED`-but-`None`-points silently → 0 | Explicitly surfaced as unresolved/unpriced | Phase 35 (COV-02) | No false completeness; remediation (Phase 37) can treat it as an unresolved item |
| `decide_sibling` a permanent `GAP` stub (no evidence field) | Reachable fail-closed join over confirmed sibling evidence | Phase 35 (COV-03/04) | `additional.sibling` can reach `SUBSTANTIATED` (15 pts) on a real, claimed-scoped, confirmed chain |

**Deprecated/outdated to correct:**
- The `test_full_audit_real_seam.py` comment asserting CLB-10 "MUST NOT be patched by touching the frozen registry" — that scoping note belonged to Phase 30; Phase 35 (COV-01) is exactly the phase authorized to ground CLB-10.
- `_FIELD_FOR["additional.sibling"] = "issuer"` placeholder in the no-false-green conformance test.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The intended `with_spouse` point value is the FIRST numeric column of the corpus table and `without_spouse` the second (e.g. CLB 6 → 8 with-spouse / 9 without-spouse) | §COV-01 Pattern 1 | Transposed columns would misprice spouse-mode language cards. **Low risk** — VERIFIED consistent with the shipped CLB-9 row (`clb9_with_spouse=29`, matching quote `"CLB 9  | 29  | 31"`). |
| A2 | A single `sibling_proof` doc_type carrying all four fields is acceptable; multiple sibling documents each contributing one field is also supported because `by_field` collapses across documents linked to `additional.sibling` | §COV-03 | If real sibling evidence must span separate documents with different `doc_type`s, add each to `_DOC_TYPE_FACTOR`→`additional.sibling`. **Low risk** — the agent's discretion; `by_field` already merges per-field across eligible values. |
| A3 | Enforcing the adult (18+) requirement is MANDATORY and is grounded from `crs-criteria.md#018` ("Brother or sister living in Canada (18 years or older, citizen or permanent resident)") as machine_check registry data — a dedicated grounded threshold ROW `additional.sibling.adult` (`kind: threshold`, `field: sibling_min_age`, `min_value: 18`) — NOT a bare Python literal | §COV-04 | **RESOLVED (Plan 35-04):** the adult gate is enforced, not optional — `decide_sibling` reads `min_value` from the grounded `sibling_min_age` threshold row, computes the sibling's age at the ITA date via `crs_audit.age_on_date` (mirroring `decide_age`), and a confirmed sibling below the grounded threshold returns AT-RISK `sibling_minor` (never SUBSTANTIATED). VERIFIED: the new row grounds 1/1 + `agrees_with_citation`/`grounds` True against `corpus/index.db`; `min_value: 18` is an allow-listed machine_check payload, so no inlined-literal violation. |
| A4 | COV-02 surfacing via a `counts["unpriced"]` dict key + a rendered report line (no new required schema field) satisfies "explicit unresolved/unpriced item" without breaking the `extra="forbid"` public envelope | §COV-02 | If a first-class typed field is preferred, add one additive optional field to `PrivateFactorCard` (`points_unresolved: bool = False`) — still additive, no migration. **Low risk** — `PublicAuditEnvelope.counts` is `dict[str,int]`; adding a key needs no schema change. |
| A5 | Second-official-language higher-CLB pricing is OUT of COV-01's strict scope (COV-01 says "first-official-language") but is a residual COV-02 unpriced case; grounding it too is the agent's discretion | §COV-02 | If stakeholders expect second language priced, add its bands (corpus supports: `"CLB 9 or more | 6 | 6"`, etc.). **Low risk** — COV-02 net catches it regardless; requirement text is first-language only. |

**All A1–A5 are low-risk and either VERIFIED against code/corpus or explicitly the agent's discretion per CONTEXT.**

## Open Questions (RESOLVED)

1. **COV-02 typed field vs. counts-only surfacing. → RESOLVED: do BOTH — typed `points_unresolved` flag + `counts["unpriced"]` + explicit render line.**
   - What we know: `PublicAuditEnvelope.counts` is a free `dict[str,int]` (additive key, no schema change); `PrivateFactorCard` is `extra="forbid"` but accepts additive optional fields.
   - **Resolution (Plan 35-02):** the planner selected the machine-readable option AND the surfacing pair — Plan 35-02 adds a first-class additive `points_unresolved: bool = False` to `PrivateFactorCard` (True iff `verdict == "SUBSTANTIATED" and substantiated_points is None`), tallies it as `counts["unpriced"]` on the PII-light public envelope (`dict[str,int]`, no schema change / no migration), AND renders an explicit `points UNRESOLVED (unpriced)` line in the vault-only markdown report. The typed flag makes the state programmatically inspectable (Phase-37 remediation reads it as an actionable unresolved item); the count + render line make it human-visible in both the public envelope and the vault report. All three are proven together by the new `crawler/tests/test_unpriced_surfacing.py`. The verdict stays narrowly `SUBSTANTIATED`, `substantiated_total` is never inflated (the `points or 0` coalesce stays a truthful 0 contribution — the flag is the visible signal), and no point value is fabricated.

2. **Whether to also ground second-language bands now. → RESOLVED: deliberately DEFERRED; the COV-02 net surfaces any residual second-language unpriced cards.**
   - What we know: the corpus grounds the full second-official-language table; only CLB 9 is currently priced. COV-01's requirement text is scoped to **first-official-language** only.
   - **Resolution:** higher second-official-language pricing is **deliberately deferred out of this phase** (staying within COV-01's first-language scope — grounding it is not required and adding out-of-scope bands would widen the phase). This is safe **because** the COV-02 net is the backstop: any `SUBSTANTIATED` second-language card whose lowest ability is not exactly CLB 9 lands as `substantiated_points is None`, so it is flagged `points_unresolved`, counted in `counts["unpriced"]`, and rendered as an explicit unresolved line rather than silently zeroed. The residual unpriced second-language card is therefore **surfaced, never hidden** — a future phase can ground the remaining second-language bands with the same data-only Pattern 1 add (no code change) when milestone appetite exists.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `corpus/index.db` (FTS5) | Grounding the new point rows / sibling citations (COV-01/04 grounding tests) | ✓ | 14 MB, built 2026-06-21 | Grounding tests skip-guard on absence (structural-only green) — shipped pattern |
| `.venv` Python | All Phase-35 code + tests | ✓ | 3.10.12 | Poetry-managed; `.venv/bin/python` |
| `pydantic` / `pyyaml` / `platformdirs` | Models / rows / vault root | ✓ | 2.13.4 / 6.0.3 / 4.10.0 | none needed (core deps) |
| Extraction extras (`pypdfium2`, `Pillow`, `pdfminer.six`) | Real sibling import→extract seam test (COV-03/04) | ✓ | installed (`_import_pdfium/_pil/_pdfminer` OK) | real-seam test skip-guards when absent; unit tests of `decide_sibling` use `add_extracted_value` directly and need no engine |
| `pytesseract` (`ocr` extra) | Not needed by Phase 35 (born-digital fixtures) | — | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none currently missing; the grounding + real-seam tests already carry skip-guards for a fresh clone (git-ignored corpus/deps) — a green suite there is STRUCTURAL ONLY.

## Validation Architecture

> `workflow.nyquist_validation` is `true` — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 (running stdlib `unittest` TestCases) via `.venv/bin/python -m pytest` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (markers only; no rootdir magic) |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_crs_no_inlined_rules.py -q` |
| Full suite command | `.venv/bin/python -m pytest crawler/tests -q` (705 tests collected today) |
| Grounding/real-seam gate | `.venv/bin/python -m pytest crawler/tests/test_full_audit_real_seam.py crawler/tests/test_crs_conversion_coverage.py -q` (uses real `corpus/index.db`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COV-01 | Every conversion-emitted first-language level {3–10} is priced (no `None`), both modes | unit + grounding | `pytest crawler/tests/test_language_points_coverage.py -x` | ❌ Wave 0 (mirror `test_crs_conversion_coverage.py`) |
| COV-01 | New CLB rows ground verbatim against corpus; no-inlined gate stays clean | grounding + static | `pytest crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_crs_rules_conformance.py -x` | ✅ (extend/keep green) |
| COV-01 | Real IELTS fixture (CLB 10/9/9/10) yields `substantiated_points==130` (no-spouse) through the real seam | integration | `pytest crawler/tests/test_full_audit_real_seam.py -x` | ✅ (update comment + assertion) |
| COV-02 | A `SUBSTANTIATED` card with `None` points is surfaced (render line + `counts["unpriced"]`), never collapsed to complete | unit | `pytest crawler/tests/test_unpriced_surfacing.py -x` | ❌ Wave 0 |
| COV-03 | Sibling fields extract as `pending`; each confirm/correct/reject works; vocab pinned set-equal | unit | `pytest crawler/tests/test_siblingfields_vocab.py crawler/tests/test_extract_confirm_cli.py -x` | ❌ Wave 0 (vocab) / ✅ (confirm CLI) |
| COV-04 | `decide_sibling` truth table: full adult chain → SUBSTANTIATED/15; missing→GAP; bad token/unparseable-DOB/no-ITA-date→AT-RISK `unresolved_sibling`; confirmed MINOR (age below grounded `sibling_min_age`, incl. day-before/on-birthday boundary) → AT-RISK `sibling_minor` (never SUBSTANTIATED) | unit | `pytest crawler/tests/test_auditors_additional.py -x` | ✅ (extend) |
| COV-04 | New `additional.sibling.adult` threshold row grounds `min_value: 18` from `#018` verbatim + retrieve-what-you-cite agrees; no inlined literal | grounding + static | `pytest crawler/tests/test_conformance_v40_retrieve_what_you_cite.py crawler/tests/test_crs_registry_transfer_additional.py crawler/tests/test_crs_no_inlined_rules.py -x` | ✅ (auto-covers the new non-gap row) |
| COV-04 | Real import→extract→confirm→audit sibling seam: an adult sibling → SUBSTANTIATED, a MINOR sibling → AT-RISK `sibling_minor`, no cross-factor contamination | integration | `pytest crawler/tests/test_full_audit_real_seam.py -x` | ✅ (add adult case + minor negative control) |

### Sampling Rate
- **Per task commit:** the requirement's targeted unit test above (`-x`, < 5 s each).
- **Per wave merge:** `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_crs_conversion_coverage.py crawler/tests/test_testtype_vocab.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_full_audit_real_seam.py -q`.
- **Phase gate:** full suite green (`pytest crawler/tests -q`) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `crawler/tests/test_language_points_coverage.py` — COV-01 anti-drift pin (levels set-equal to live conversion range, both modes priced, all rows ground). Mirror `test_crs_conversion_coverage.py`.
- [ ] `crawler/tests/test_unpriced_surfacing.py` — COV-02 net (synthetic SUBSTANTIATED card with `None` points is surfaced/counted).
- [ ] `crawler/tests/test_siblingfields_vocab.py` — COV-03 anti-drift pin (`siblingfields.SIBLING_FIELDS` == `FieldName` sibling members == `_FIELD_SPECS["sibling_proof"]` names == fields `decide_sibling` reads). Mirror `test_testtype_vocab.py`.
- [ ] `crawler/tests/fixtures/extraction/make_fixtures.py` — add a `sibling_proof_pdf()` born-digital fixture.
- [ ] Framework install: none — `pytest` + `.venv` already present.

## Security Domain

> `security_enforcement` is `true` (ASVS level 1) — section included. This phase's "security" is the PII firewall + fail-closed verdict integrity + injection resistance, all inherited from v4.0.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control (existing, reused) |
|---------------|---------|-----------------|
| V2 Authentication | no | Local-first single-user tool; no auth surface added |
| V3 Session Management | no | No sessions |
| V4 Access Control | yes | Claimed-scoped linkage (`_resolve_factor`) + `audit_eligible_values(factor_id)` — a document reaches a factor ONLY if that factor is claimed (least privilege; prevents privilege elevation to an unclaimed/injected factor) |
| V5 Input Validation | yes | `FieldName` `Literal` (extraction vocab) + `add_extracted_value` boundary rejection; grounding gate rejects any un-groundable rule/quote; `is_audit_eligible` rejects pending/rejected/low-quality/ambiguous/stale evidence |
| V6 Cryptography | no (not for secrecy) | `hashlib.sha256` is used for content-addressing + staleness fingerprints only, not confidentiality — never hand-roll and no change here |
| V7/V8 Logging & Data Protection | yes | Two-tier PII boundary: PII-bearing cards/values stay vault-only; stdout/`--json` stays PII-light; `ev_` (vault) vs `relpath#ordinal` (corpus) namespaces kept in separate columns/models |

### Known Threat Patterns for {grounded CRS auditor + document extraction}

| Pattern | STRIDE | Standard Mitigation (this phase) |
|---------|--------|---------------------|
| Fabricated/guessed point value fills a coverage gap | Tampering | Points live ONLY in grounded rows with verbatim quotes gated by `validate_registry`; `no_inlined_volatile_rules` rejects literals in code/prose; COV-01 grounds, never fabricates |
| Un-priced card presented as "complete" | Spoofing (of completeness) | COV-02 surfaces `SUBSTANTIATED`+`None` explicitly; never coalesces to a passing total |
| Malicious/low-quality sibling document greens the factor | Tampering / Elevation | `is_audit_eligible` blocks pending/low_quality/ambiguous/stale; `decide_sibling` requires ALL confirmed fields + accepted enum tokens (fail-closed) |
| Sibling evidence bleeds into age/nomination (or `--factor` injection) | Elevation of Privilege | `_DOC_TYPE_FACTOR` + claimed-only linkage + `by_field` scoping (SQL-parameterized); real-seam contamination test asserts disjoint evidence |
| PII (name/UCI/DOB/`ev_`) leaks to stdout/tracked files | Information Disclosure | New sibling values are vault-only; PII-light envelope + publish-safe allow-list unchanged; `extra="forbid"` public models reject applicant/`ev_` keys structurally |
| Sibling read framed as legal/eligibility advice | Repudiation / misframing | `SCREENING_NOTICE` renders into every vault report; `SUBSTANTIATED` stays narrowly defined; no approval/outcome language added |

## Project Constraints (from copilot-instructions.md / AGENTS.md)

- **No `./copilot-instructions.md` present** in the working directory (verified absent). `AGENTS.md` contains only GSD command-routing directives (no coding conventions that constrain Phase 35 implementation).
- **Frozen invariants carried from the ROADMAP (treated as locked):** zero new runtime deps; no second trust path (reuse `search`→`--cite`→grounding gate→JSON envelope); vault-only PII; fail-closed everywhere (no fabricated points; unpriced surfaced); no legal advice (`SCREENING_NOTICE`); `ev_`↔`relpath#ordinal` namespace separation; Poetry-managed Python; autonomous execution.
- **Tooling rule (from the task):** use `.venv/bin/python` or `poetry`, never bare `python`. All commands in this document follow that.

## Recommended Plan Decomposition (~4 plans, two mostly-parallel tracks)

> Tracks A and B are independent (different files, no shared edit) and can run in parallel. Both must land before Phase 37 (remediation projects a *complete* report).

- **Plan A1 — Higher-CLB first-language pricing (COV-01).**
  Files: `data/crs_rules/core.yaml` (add CLB 3–8,10 rows + citations). Tests: NEW `test_language_points_coverage.py` (level-set pin, both modes, grounding), keep `test_crs_no_inlined_rules.py`/`test_crs_rules_conformance.py` green. Update `test_full_audit_real_seam.py` comment + assert `substantiated_points==130`. *Verifies COV-01.*
- **Plan A2 — Unpriced surfacing net (COV-02).**
  Files: `auditor.run_full_audit` (detect unpriced), `audit_report._render_factor_card_markdown` (explicit line), `models/audit` (`counts["unpriced"]`; optional `points_unresolved` field). Tests: NEW `test_unpriced_surfacing.py`. *Verifies COV-02.* (Depends conceptually on A1's data but is code-independent; can proceed in parallel.)
- **Plan B1 — Sibling extraction vocabulary (COV-03).**
  Files: NEW `crawler/siblingfields.py`; `models/vault.FieldName` (add members); `extraction._FIELD_SPECS["sibling_proof"]` + `_DOC_TYPE_FACTOR`; `fixtures/extraction/make_fixtures.py` (sibling PDF). Tests: NEW `test_siblingfields_vocab.py` (set-equality pin); extend `test_extraction*`. *Verifies COV-03.* **Land `FieldName` + `_FIELD_SPECS` + `siblingfields.py` together (Pitfall 3).**
- **Plan B2 — Reachable fail-closed sibling decider (COV-04).**
  Files: `auditors/additional.decide_sibling` (+ a local `_grounded_min_age` threshold reader); `data/crs_rules/additional.yaml` (add the grounded `additional.sibling.adult` threshold ROW — `min_value: 18` grounded from `#018` "18 years or older"). Tests: extend `test_auditors_additional.py` (truth table + day-before/on-birthday age boundaries + confirmed-minor `sibling_minor`); add an adult sibling case + a real-seam MINOR negative control + contamination assertion to `test_full_audit_real_seam.py`; correct `test_conformance_v40_no_false_green.py::_FIELD_FOR["additional.sibling"]`. Retrieve-what-you-cite + no-inlined coverage of the new row is auto-provided by the existing `test_conformance_v40_retrieve_what_you_cite.py` / `test_crs_registry_transfer_additional.py` / `test_crs_no_inlined_rules.py`. *Verifies COV-04.* (Depends on B1's fields.)

**Build order:** A1‖B1 first; A2 (after/with A1), B2 (after B1). Full-suite gate last.

## Sources

### Primary (HIGH confidence — verified this session against code + corpus)
- `crawler/data/crs_rules/core.yaml` (lines 221-253, 255-...) — `core.language.first.points` grounds CLB 9 only; conversion rows emit {3–10}.
- `corpus/guidance/crs-criteria.md#006` (via `searchindex.resolve`) — full first-language per-ability table; **all 7 higher-CLB quotes VERIFIED substrings**.
- `corpus/guidance/crs-criteria.md#019` / `#018` — sibling rule grounds; adult "18 years or older" quote VERIFIED substring of #018.
- `crawler/auditors/core.py` (`_sum_points`, `_grounded_points`), `crawler/crs_audit.py` (`to_clb`, `score_factor`) — generalize over levels; select mode by `with_spouse`/`without_spouse` label.
- `crawler/auditors/additional.py::decide_sibling` — current hard-coded `GAP` stub.
- `crawler/auditor.py` (`audit_one` scoping, `run_full_audit` total `sum(points or 0)`).
- `crawler/models/vault.py::FieldName` (extraction vocab Literal), `crawler/vault.py` (`add_extracted_value` forces pending, `is_audit_eligible`, `audit_eligible_values`).
- `crawler/extraction.py` (`_FIELD_SPECS`, `_DOC_TYPE_FACTOR`, `_resolve_factor`).
- `crawler/testtypes.py` + `crawler/tests/test_testtype_vocab.py` — the shared-vocab anti-drift template.
- `crawler/tests/test_full_audit_real_seam.py` — real seam; documents the CLB-10 pricing boundary; fixture converts to CLB 10/9/9/10 (VERIFIED).
- Live checks: `score_factor("core.language.first", lvl)` = `None` for {3–8,10}, `31` for 9; `_grounded_points(additional.sibling,'sibling')==15`; `validate_registry` sibling 1/1; projected no-spouse total **130**. Executed via `.venv/bin/python`.

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` (v4.1 project research) — corroborates zero-new-deps, projection-only, the two coverage gaps; cross-checked against code above.
- `.planning/ROADMAP.md` Phase 35 detail + frozen invariants; `.planning/STATE.md` accumulated decisions (Phase 30/31/33 patterns).

### Tertiary (LOW confidence)
- None — no external WebSearch used (all providers disabled in config); every claim is code- or corpus-verified.

## Metadata

**Confidence breakdown:**
- Standard stack (no new deps): HIGH — verified against `pyproject.toml` + `.venv`; nothing to install.
- COV-01 pricing fix: HIGH — corpus quotes verified groundable; conversion level set computed live; no code change needed.
- COV-02 surfacing: HIGH (mechanism), MEDIUM (exact typed-field vs counts choice — the agent's discretion, low risk).
- COV-03 vocabulary: HIGH — `FieldName` boundary + `testtypes.py` template are the exact reusable pattern; no migration.
- COV-04 decider: HIGH — grounded rule + points verified; claimed-scoping/quarantine already structural; only the decider body + fields are new.
- Pitfalls: HIGH — five of six are observed directly in shipped code/tests (including the self-documented CLB-10 comment and the `issuer` placeholder).

**Research date:** 2026-07-17
**Valid until:** 2026-08-16 (30 days — stable local codebase + pinned corpus; the only volatility is upstream IRCC CRS values, which by design live in the grounded corpus and are out of this phase's control).
