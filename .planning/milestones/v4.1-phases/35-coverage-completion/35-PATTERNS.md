# Phase 35: Coverage Completion - Pattern Map

**Mapped:** 2026-07-17
**Files analyzed:** 16 (9 source create/modify + 7 test create/modify)
**Analogs found:** 16 / 16 (0 with no analog)

> **Core finding (matches RESEARCH.md §Summary):** *both* coverage gaps are "the
> wiring already exists; the data/vocabulary is missing." Every planned file has a
> shipped in-repo analog — most are the *same file* extended, or a byte-for-byte
> mirror of a shipped template (`testtypes.py`, `test_testtype_vocab.py`,
> `test_crs_conversion_coverage.py`). The single biggest risk the planner must
> guard against is *helpfully forking a frozen guarantee* (a points dict in `.py`,
> a second grounding check, a bespoke validator). Add grounded rows + one decider
> body + a stdlib vocab module + tests — nothing else.

---

## File Classification

| Planned File | Op | Role | Data Flow | Closest Analog | Match |
|--------------|----|------|-----------|----------------|-------|
| `crawler/data/crs_rules/core.yaml` | modify-data | grounded registry data | grounded-lookup (points_table) | same-file `core.language.first.points` CLB-9 entry (L221-253) + `additional.study` 2-citation shape (additional.yaml L107-141) | exact |
| `crawler/data/crs_rules/additional.yaml` | modify-data | grounded registry data | grounded threshold lookup | same-file `additional.sibling` row (L186-218) + `core.work.hours` threshold machine-check shape | exact |
| `crawler/siblingfields.py` | **NEW** | utility / shared-vocab module | vocab (names-only, no volatile numbers) | `crawler/testtypes.py` (whole file) | exact (template) |
| `crawler/models/vault.py` | modify | model (Literal boundary) | validation/transform | same-file `FieldName` Literal (L75-93), nomination members (L91-92) | exact |
| `crawler/extraction.py` | modify | service (extraction engine) | file-I/O → structured transform | same-file `_FIELD_SPECS["nomination"]` (L200-204) + passport DOB spec (L205-216) + `_DOC_TYPE_FACTOR` (L225-232) + `_resolve_factor` (L325-344) | exact |
| `crawler/auditors/additional.py` | modify | decider (service) | request-response / deterministic fail-closed join | same-file `decide_nomination` (L71-99) + `decide_study` (L105-121); helpers from `auditors/core.py` | exact |
| `crawler/models/audit.py` | modify-small | model + down-projection | transform / roll-up counts | same-file `to_public_envelope` counts dict (L221-250) + `PrivateFactorCard` additive field (L154-176) | exact |
| `crawler/auditor.py` | modify-small | audit spine (orchestrator) | batch aggregate roll-up | same-file `run_full_audit` `substantiated_total` (L332-334) | exact (same fn) |
| `crawler/audit_report.py` | modify-small | render (view) | transform → markdown | same-file `_render_factor_card_markdown` card loop (L115-127) + cutoff line (L107-113) | exact (same fn) |
| `crawler/tests/test_language_points_coverage.py` | **NEW** | test (unit + grounding) | verification (level-set pin) | `test_crs_conversion_coverage.py` (whole file) | exact (template) |
| `crawler/tests/test_unpriced_surfacing.py` | **NEW** | test (unit) | verification (net proof) | `test_auditors_additional.py` synthetic-registry harness + `models/audit.to_public_envelope` | role-match |
| `crawler/tests/test_siblingfields_vocab.py` | **NEW** | test (unit anti-drift) | verification (set-equality pin) | `test_testtype_vocab.py` (whole file) | exact (template) |
| `crawler/tests/test_auditors_additional.py` | extend | test (unit truth-table) | verification | same-file `TestNomination` / `TestStudy` classes (L180-233) | exact (same file) |
| `crawler/tests/test_full_audit_real_seam.py` | extend | test (integration real-seam) | verification | same-file `_seed_and_run` (L94-142) + contamination test (L193-221) + CLB-10 comment (L180-185) | exact (same file) |
| `crawler/tests/fixtures/extraction/make_fixtures.py` | extend | test fixture builder | file-I/O generation | same-file `nomination_pdf()` (L170-178) + `passport_pdf()` (L181-195) | exact (same file) |
| `crawler/tests/test_conformance_v40_no_false_green.py` | extend | test (conformance) | verification | same-file `_FIELD_FOR` map (L66-80) — correct the sibling placeholder | exact (same file) |

**Verified live this session** (`.venv/bin/python`): conversion-emitted first-language
levels = `{3,4,5,6,7,8,9,10}`; `score_factor("core.language.first", lvl, False, reg)`
returns `None` for `{3,4,5,6,7,8,10}` and `31` only for `9`;
`_grounded_points(reg, "additional.sibling", "sibling", False) == 15`.

---

## Shared Patterns

These seven cross-cutting patterns are the phase's spine. Every plan copies from one
or more of them. Reproduced verbatim from shipped code with file+line anchors.

### Shared Pattern 1 — Grounded rule rows (never a code literal)
**Source:** `crawler/data/crs_rules/core.yaml:221-253` (CLB-9), `crawler/data/crs_rules/additional.yaml:107-141` (two-citation-index study), read by `crawler/auditors/core.py:180-203` (`_grounded_points`) and `crawler/crs_audit.py:231-284` (`score_factor`).
**Apply to:** COV-01 point rows (core.yaml) and the mandatory COV-04 sibling-adulthood threshold row (additional.yaml).
**Rule:** every volatile CRS number lives ONLY inside a `points_by_level` entry paired with a `citations[].quote` that is a verbatim corpus substring, indexed by `citation_index`. A `CLB N` / points literal in `.py` trips `no_inlined_volatile_rules` (see Integration Seam 8).

The shipped CLB-9 entry — the exact shape new bands mirror (add entries, do NOT change readers):
```yaml
# core.yaml:235-249
    citations:
      - chunk_id: guidance/crs-criteria.md#006
        quote: "CLB 9  | 29  | 31"
    machine_check:
      kind: points_table
      field: clb_per_ability
      points_by_level:
        - label: clb9_with_spouse      # first column = with_spouse
          level: 9
          points: 29
          citation_index: 0
        - label: clb9_without_spouse   # second column = without_spouse
          level: 9
          points: 31
          citation_index: 0
```
Multi-citation-index precedent (one `(chunk_id, quote)` per distinct table line, entries reference by index) — copy this for the CLB 3-8,10 bands:
```yaml
# additional.yaml:125-141 (additional.study)
    citations:
      - chunk_id: guidance/crs-criteria.md#019
        quote: "Post-secondary education in Canada - credential of one or two years"
      - chunk_id: guidance/crs-criteria.md#019
        quote: "Post-secondary education in Canada - credential three years or longer"
    machine_check:
      kind: points_table
      field: canadian_study
      points_by_level:
        - {label: one_or_two_years, level: "1-2", points: 15, citation_index: 0}
        - {label: three_or_more_years, level: "3+", points: 30, citation_index: 1}
```
**Column semantics (VERIFIED, do not transpose):** first numeric column = `with_spouse`, second = `without_spouse` (matches `clb9_with_spouse=29` ↔ quote `"CLB 9  | 29  | 31"`). Mode selection is by the `with_spouse` / `without_spouse` substring in `label` — the labels ARE the discriminators `_grounded_points`/`score_factor` read.

**The reader that already generalizes (NO change needed for COV-01):**
```python
# crawler/auditors/core.py:188-203  (_grounded_points)
    for row in registry.rows:
        if not row.factor_ids or row.factor_ids[0] != factor_id:
            continue
        for entry in row.machine_check.points_by_level or []:
            if str(entry.level) == str(value):
                matches.append(entry)
    if not matches:
        return None                       # never a guessed award
    for entry in matches:
        label = entry.label or ""
        if spouse_mode and "with_spouse" in label and "without_spouse" not in label:
            return entry.points
        if not spouse_mode and "without_spouse" in label:
            return entry.points
    return matches[-1].points
```

### Shared Pattern 2 — Shared-vocabulary anti-drift (the `testtypes.py` template)
**Source:** `crawler/testtypes.py` (whole), pinned by `crawler/tests/test_testtype_vocab.py:23-47`.
**Apply to:** COV-03 — new `crawler/siblingfields.py` + `test_siblingfields_vocab.py`.
**Rule:** ONE stdlib module holds names/enums ONLY (no CRS points → stays outside the `no_inlined_volatile_rules` surface), imported by BOTH producer (extractor) and consumer (decider), asserted set-equal to the model boundary + registry by an anti-drift test. Drift in either direction fails loudly.

Template — names-as-frozenset + docstring stating the anti-drift contract:
```python
# crawler/testtypes.py:26-32
CANONICAL_TEST_TYPES: frozenset[str] = frozenset({
    "CELPIP-General", "IELTS General Training", "PTE Core",
    "TEF Canada", "TCF Canada",
})
```
Fail-closed normalizer (unknown token is NOT coerced to an accepted value):
```python
# crawler/testtypes.py:63-75
def normalize_test_type(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    key = _lookup_key(raw)
    return TEST_TYPE_ALIASES.get(key, key)   # unknown → unchanged key (non-accepted)
```
The pin (mirror for sibling; read the source of truth the SAME way the auditor does):
```python
# crawler/tests/test_testtype_vocab.py:41-47
    def test_canonical_set_equals_registry_accepted_enum(self) -> None:
        accepted = _registry_accepted_test_types()
        self.assertEqual(set(testtypes.CANONICAL_TEST_TYPES), accepted, ...)
```

### Shared Pattern 3 — Pending-first (quarantined) extraction
**Source:** `crawler/vault.py:785-825` (`add_extracted_value` FORCES `pending`), `crawler/extraction.py:167-232` (`_FIELD_SPECS` + `_DOC_TYPE_FACTOR`), `crawler/extraction.py:325-344` (`_resolve_factor` claimed-only linkage).
**Apply to:** COV-03 — `_FIELD_SPECS["sibling_proof"]`, `_DOC_TYPE_FACTOR["sibling_proof"]`.
**Rule:** extraction can NEVER write a born-confirmed value; a field name is validated at the pydantic boundary; a value links to a factor ONLY if that factor is CLAIMED (parameterized SQL, no interpolation).

Quarantine invariant (status is `'pending'` regardless of any caller argument):
```python
# crawler/vault.py:814-822
    vault.con.execute(
        "INSERT INTO extracted_values(value_id, ... confirmation_status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')", (...))
```
Field-spec shape to copy for `sibling_proof` (`(field_name, label_regex, kind)`, kind ∈ {text,date,number,noc}):
```python
# crawler/extraction.py:200-204 (nomination — the closest doc_type)
    "nomination": [
        ("nomination_stream", r"(?:Stream|Nomination Stream|Category)", "text"),
        ("expiry_date", r"(?:Expiry Date|Valid Until|Expiration Date)", "date"),
        ("issuer", r"(?:Province|Nominating Province|Issued by)", "text"),
    ],
```
Doc-type → SPECIFIC factor id (add `"sibling_proof": "additional.sibling"`):
```python
# crawler/extraction.py:225-232
_DOC_TYPE_FACTOR: dict[str, str] = {
    "language_test": "core.language.first",
    "eca": "core.education",
    "employment_reference": "core.work",
    "nomination": "additional.nomination",
    "passport": "core.age",
    "identity": "core.age",
}
```
Claimed-only fail-closed linkage (already prevents cross-factor contamination — do NOT bypass):
```python
# crawler/extraction.py:338-344
    target = factor_override or _DOC_TYPE_FACTOR.get(doc_type)
    if target is None:
        return None
    row = v.con.execute(
        "SELECT factor_id FROM crs_profile_factors WHERE factor_id = ? LIMIT 1",
        (target,)).fetchone()          # PARAMETERIZED — injected --factor can't reach SQL
    return row["factor_id"] if row is not None else None
```

### Shared Pattern 4 — Fail-closed deterministic decider (never relaxed)
**Source:** `crawler/auditors/additional.py:71-121` (`decide_nomination` / `decide_study`), helpers `crawler/auditors/core.py:45-54` (`_effective_value` / `_confirmed_snapshot`) and `:180-203` (`_grounded_points`). Current stub to REPLACE: `crawler/auditors/additional.py:146-158`.
**Apply to:** COV-04 — reachable `decide_sibling`.
**Rule:** require ALL confirmed fields present + an accepted enum token, else `GAP`/`AT-RISK`; read points from a grounded row (never a literal); ambiguity/staleness is already filtered upstream by `is_audit_eligible`. The decider only gains real required fields — it is NEVER relaxed to "make it green."

The exact shape to mirror (`decide_nomination`):
```python
# crawler/auditors/additional.py:77-99
    confirmed = _confirmed_snapshot(ctx.by_field)
    stream = ctx.by_field.get("nomination_stream")
    if stream is None:
        return DecisionResult("GAP", "missing_evidence", confirmed_value=confirmed)
    # ... expiry / token checks → AT-RISK on unresolved ...
    points = _grounded_points(ctx.registry, "additional.nomination", "nomination",
                              spouse_mode=False)
    if points is None:
        return DecisionResult("GAP", "below_threshold", confirmed_value=confirmed)
    return DecisionResult("SUBSTANTIATED", "grounded_substantiated",
                          confirmed_value=confirmed, substantiated_points=points)
```
Accepted-token discriminator lives in `siblingfields.py` (Shared Pattern 2), consumed via `_effective_value`:
```python
# crawler/auditors/core.py:45-54
def _effective_value(value) -> Any:
    if value.confirmation_status == "corrected" and value.confirmed_value is not None:
        return value.confirmed_value
    return value.normalized_value
```
**Grounded-points call for sibling (VERIFIED == 15):** `_grounded_points(ctx.registry, "additional.sibling", "sibling", spouse_mode=False)`. Registration already present at `additional.py:165` (`register("additional.sibling", decide_sibling)`) — only the body changes.
**Guard:** the decider body must NOT inline `15` near CRS-context words (`sibling`/`points`) or it trips `points_literal` — always route through `_grounded_points`.

### Shared Pattern 5 — Unpriced `SUBSTANTIATED` surfacing (no false completeness)
**Source:** `crawler/auditor.py:332-334` (roll-up that silently coalesces `None→0`), `crawler/models/audit.py:221-250` (`to_public_envelope` counts dict), `crawler/audit_report.py:115-131` (card render loop).
**Apply to:** COV-02 — `run_full_audit` net + `audit_report` render line + `models/audit` counts and required additive `points_unresolved: bool = False` card field.
**Rule:** a `verdict == "SUBSTANTIATED"` card whose `substantiated_points is None` must become an explicit unresolved item — never a silent `0`. Verdict stays `SUBSTANTIATED` (narrow semantics preserved); nothing is fabricated.

The silent-zero the net must catch:
```python
# crawler/auditor.py:332-334
    substantiated_total = sum(
        (c.substantiated_points or 0)          # <-- None→0 today; COV-02 flags it first
        for c in cards if c.verdict == "SUBSTANTIATED")
```
Counts are a free `dict[str,int]` — add `counts["unpriced"]` here (no schema change; `PublicAuditEnvelope.counts` is `dict[str,int]`, `extra="forbid"` unaffected):
```python
# crawler/models/audit.py:221-227 / 250
    counts = {"factors": ..., "substantiated": 0, "gap": 0, "at_risk": 0, "na": 0}
    ...
    counts["grounded_claims"] = len(claims)     # additive key precedent
```
Render an explicit line inside the per-card loop (mirror the existing `Substantiated points:` line at `audit_report.py:122`):
```python
# crawler/audit_report.py:120-125 (existing card fields)
            f"- Claimed: `{card.claimed_value}`",
            f"- Confirmed: `{card.confirmed_value}`",
            f"- Substantiated points: {card.substantiated_points}",
            f"- Score delta: {card.score_delta}",
```
First-class private flag (additive field with a backward-compatible default — no migration; `PrivateFactorCard` is `extra="forbid"`):
```python
# crawler/models/audit.py:172 (add beside substantiated_points)
    substantiated_points: int | None = None
    points_unresolved: bool = False
```

### Shared Pattern 6 — Real import→extract→confirm→audit seam tests
**Source:** `crawler/tests/test_full_audit_real_seam.py:94-142` (`_seed_and_run`), `:193-221` (no-cross-factor-contamination), skip-guard `:64-69`.
**Apply to:** COV-01 (update CLB-10 comment + assert `substantiated_points == 130`), COV-04 (add a sibling doc case + contamination assertion).
**Rule:** exercise the ACTUAL shipped seam (`import_document → extract_document → confirm_value → run_full_audit_report`); NEVER `add_extracted_value` directly; skip-guard on absent `corpus/index.db` or extraction deps (a green suite there is STRUCTURAL ONLY).

The seam driver (add a `sibling_proof` doc + a `additional.sibling` claim, mirror the nomination lines):
```python
# crawler/tests/test_full_audit_real_seam.py:117-135
        docs = [
            self._import(v, mf.language_test_pdf(), "language_test", "lang"),
            self._import(v, mf.passport_pdf(), "passport", "passport"),
            self._import(v, mf.eca_pdf(), "eca", "eca"),
            self._import(v, mf.nomination_pdf(), "nomination", "nomination"),
        ]
        for doc_id in docs:
            extraction.extract_document(v, doc_id)     # REAL extraction
        for doc_id in docs:
            for val in vault.list_extracted_values(v, document_id=doc_id, status="pending"):
                vault.confirm_value(v, val.value_id, "confirm")   # REAL confirm
```
Contamination assertion shape (assert sibling evidence never appears under age/nomination and vice-versa):
```python
# crawler/tests/test_full_audit_real_seam.py:200-219
            language_evidence = set(lang.evidence_ids)
            self.assertTrue(language_evidence.isdisjoint(set(age.evidence_ids)), ...)
            dob_factors = {val.factor_id for val in all_values
                           if val.field_name == "date_of_birth"}
            self.assertEqual(dob_factors, {"core.age"})
```
**STALE COMMENT to correct (COV-01):** `test_full_audit_real_seam.py:180-185` documents that the language card's points are `None` because the CLB-10 fixture is ungrounded and "MUST NOT be patched by touching the frozen registry." COV-01 is exactly the phase authorized to ground CLB-10 — update the comment and strengthen to `lang.substantiated_points == 130` (no-spouse). Note fixture `claimed_points=124` < 130 ⇒ `score_delta` becomes `-6`; adjust any assertion that assumed `score_delta is None`.
**Fixture builder (COV-03):** add a `sibling_proof_pdf()` to `make_fixtures.py`, mirroring `nomination_pdf()` (`:170-178`) with distinctive FAKE `Relationship:/Status:/Residence:/Date of Birth:` label lines; use the shared `build_pdf([page])` writer (`:37-81`). Never commit a binary fixture.

### Shared Pattern 7 — No-false-green conformance matrix
**Source:** `crawler/tests/test_conformance_v40_no_false_green.py:60-80` (`_BLOCKING_STATES` + `_FIELD_FOR`), `crawler/vault.py:1060-1078` (`is_audit_eligible` choke point).
**Apply to:** COV-03/04 — correct `_FIELD_FOR["additional.sibling"]`.
**Rule:** the five blocking states (`pending, rejected, low_quality, ambiguous, stale`) must never green a factor; the matrix must seed a REAL field the decider reads.

The placeholder to fix (line 79 — `issuer` predates any sibling field; the sibling decider never reads it):
```python
# crawler/tests/test_conformance_v40_no_false_green.py:66-80
_FIELD_FOR: dict[str, str] = {
    ...
    "additional.job_offer": "issuer",
    "additional.study": "credential_level",
    "additional.french": "raw_score_reading",
    "additional.sibling": "issuer",        # <-- CHANGE to "sibling_relationship"
}
```
The single choke point every blocking state must fail (do not fork it):
```python
# crawler/vault.py:1074-1078
    if row["confirmation_status"] not in ("confirmed", "corrected"):
        return False
    if row["quality_flag"] != "ok":
        return False
    return not is_stale(vault, value_id)
```

---

## Pattern Assignments (per planned file)

### `crawler/data/crs_rules/core.yaml` (grounded registry data, COV-01)
**Analog:** same-file `core.language.first.points` (L221-253); multi-index shape from `additional.yaml` study (L125-141).
**Copy:** Shared Pattern 1. Extend the ONE existing `core.language.first.points` row's `citations` list with one `(chunk_id, quote)` per distinct verbatim table line (all `guidance/crs-criteria.md#006` substrings, VERIFIED: `"Less than CLB 4  | 0  | 0"`, `"CLB 4 or 5  | 6  | 6"`, `"CLB 6  | 8  | 9"`, `"CLB 7  | 16  | 17"`, `"CLB 8  | 22  | 23"`, `"CLB 10 or more  | 32  | 34"`), and add `with_spouse`/`without_spouse` `PointsEntry` pairs for levels 3,4,5,6,7,8,10 with matching `citation_index`.
**No code change:** `score_factor`/`_grounded_points` already generalize over levels (verified: only CLB-9 currently priced).
**Seam preserved:** grounding gate re-checks every new quote (Integration Seam 1); `no_inlined_volatile_rules` skips grounded payload/quote lines (Integration Seam 8).

### `crawler/data/crs_rules/additional.yaml` (grounded registry data, COV-04)
**Analog:** same-file `additional.sibling` points row plus the existing threshold `machine_check` rows used by deterministic work/age logic.
**Copy:** Shared Pattern 1. Add `additional.sibling.adult` as a grounded `kind: threshold` row with `field: sibling_min_age`, its minimum value carried only in `machine_check`, and the verbatim `guidance/crs-criteria.md#018` quote `"18 years or older"`. Keep the existing `additional.sibling` points row unchanged.
**Seam preserved:** both sibling rows must pass the frozen registry grounding and retrieve-what-you-cite checks; no adulthood or points literal enters Python.

### `crawler/siblingfields.py` (NEW — utility/shared-vocab, COV-03)
**Analog:** `crawler/testtypes.py` (whole file — the template).
**Copy:** Shared Pattern 2. `from __future__ import annotations`; a `SIBLING_FIELDS: frozenset[str]` (`sibling_relationship`, `sibling_status`, `sibling_residence`, `sibling_date_of_birth`); accepted-enum frozensets (`SIBLING_STATUS_ACCEPTED = {"citizen","permanent_resident"}`, `SIBLING_RELATIONSHIP_ACCEPTED = {"brother","sister"}`); docstring stating the anti-drift contract and the "names-only, no CRS points" scope discipline. Pure stdlib, zero runtime deps.
**Seam preserved:** carries NO points → stays outside `no_inlined_volatile_rules`; imported by BOTH `extraction.py` and `auditors/additional.py` (single source of truth).

### `crawler/models/vault.py` (model / Literal boundary, COV-03)
**Analog:** same-file `FieldName` Literal (L75-93), nomination members (L91-92).
**Copy:** add the four sibling field names to the `FieldName` Literal. **Land in the SAME change as `_FIELD_SPECS` + `siblingfields.py`** (Pitfall 3: extraction persists nothing if the Literal edit is split — `add_extracted_value` raises `ValidationError` on an unknown name).
**Seam preserved:** boundary validation at `add_extracted_value` (Integration Seam 3); `field_name` column is free `TEXT`, so no DDL/migration.

### `crawler/extraction.py` (service / extraction engine, COV-03)
**Analog:** same-file `_FIELD_SPECS["nomination"]` (L200-204), passport DOB spec (L205-216), `_DOC_TYPE_FACTOR` (L225-232), `_extract_fields` (L275-322), `_resolve_factor` (L325-344).
**Copy:** Shared Pattern 3. Add `_FIELD_SPECS["sibling_proof"]` (relationship/status/residence `text` + `sibling_date_of_birth` `date` via the existing `_normalize_date` path) and `_DOC_TYPE_FACTOR["sibling_proof"] = "additional.sibling"`. Field NAMES must match `siblingfields.SIBLING_FIELDS` (import it; do not re-derive).
**Seam preserved:** `_extract_fields` STRUCTURAL-only (no CLB/points math); `_resolve_factor` claimed-only linkage unchanged; `PARSER_VERSION` bump only if parse logic changes (invalidates prior confirmations by design — SC4).

### `crawler/auditors/additional.py` (decider / service, COV-04)
**Analog:** same-file `decide_nomination` (L71-99) + `decide_study` (L105-121); replace the stub at L146-158.
**Copy:** Shared Pattern 4. Real fail-closed join: require `sibling_relationship` + `sibling_status` + `sibling_residence` + `sibling_date_of_birth` (missing → `GAP` `missing_evidence`); reject non-accepted enum tokens or unparseable dates via `siblingfields` (→ `AT-RISK` `unresolved_sibling`); read the grounded minimum age with `_grounded_min_age`, compute age at the ITA date via `crs_audit.age_on_date`, and return `AT-RISK` `sibling_minor` below the grounded threshold. Points come from `_grounded_points(ctx.registry, "additional.sibling", "sibling", spouse_mode=False)`; only a complete eligible adult chain reaches `SUBSTANTIATED`. `register(...)` remains unchanged.
**Seam preserved:** decider NEVER relaxes; no points or adulthood threshold literal appears in `.py`; `is_audit_eligible` filters pending/stale/low-quality/ambiguous evidence upstream.

### `crawler/models/audit.py` (model + down-projection, COV-02)
**Analog:** same-file `to_public_envelope` counts dict (L221-250), `PrivateFactorCard` (L154-176).
**Copy:** Shared Pattern 5. Add a `counts["unpriced"]` tally in `to_public_envelope` (additive dict key, like the existing `counts["grounded_claims"]`) and add `points_unresolved: bool = False` to `PrivateFactorCard`.
**Seam preserved:** `counts` is `dict[str,int]` and card fields additive-optional → no schema change, no migration; `extra="forbid"` + `citation_id`/`evidence_id` firewall untouched.

### `crawler/auditor.py` (audit spine / orchestrator, COV-02)
**Analog:** same-file `run_full_audit` `substantiated_total` roll-up (L332-334), `audit_one` card assembly (L229-250).
**Copy:** Shared Pattern 5. Detect `card.verdict == "SUBSTANTIATED" and card.substantiated_points is None` in the roll-up; count it / flag the card BEFORE the `points or 0` coalesce silently zeroes it. Do not change the verdict.
**Seam preserved:** fail-closed ordering + grounding gate (`_gate_or_raise`) untouched; the frozen `search→--cite→gate→envelope` path unchanged.

### `crawler/audit_report.py` (render / view, COV-02)
**Analog:** same-file `_render_factor_card_markdown` card loop (L115-127) + cutoff line (L107-113).
**Copy:** Shared Pattern 5. Render an explicit "points UNRESOLVED (unpriced)" line inside the per-card loop when a `SUBSTANTIATED` card has `None` points (beside the existing `- Substantiated points:` line at L122). Vault-only write path + `SCREENING_NOTICE` framing unchanged.
**Seam preserved:** report stays vault-only (PII-bearing); `SCREENING_NOTICE` (screening-not-legal-advice) still renders into every report.

### `crawler/tests/test_language_points_coverage.py` (NEW test, COV-01)
**Analog:** `crawler/tests/test_crs_conversion_coverage.py` (whole — `_conversion_bands` L37-48, completeness L56-68, grounding skipUnless L105-119).
**Copy:** Shared Pattern 6 discipline. Derive the expected level set from the LIVE conversion rows at test time (`{int(e.level) for r in reg.rows if r.machine_check.kind=="conversion" and not r.gap for e in ...}` → `{3..10}`), NOT a hard-coded `range(4,11)` (Pitfall 2: PTE Core emits CLB 3). Assert `score_factor("core.language.first", lvl, mode, reg) is not None` for every emitted level × both modes; a grounding subclass (skip-guarded on `corpus/index.db`) proves the new rows ground with zero violations.

### `crawler/tests/test_unpriced_surfacing.py` (NEW test, COV-02)
**Analog:** `test_auditors_additional.py` synthetic-registry harness (`_val` L120-124, `_ctx` L127-134) + `models/audit.to_public_envelope`.
**Copy:** construct a synthetic `PrivateFactorCard(verdict="SUBSTANTIATED", substantiated_points=None)` (or a `PrivateAuditReport` containing one), run the COV-02 net + `to_public_envelope`, assert `counts["unpriced"] >= 1` and the rendered markdown carries the explicit unresolved line — and that the total is NOT silently inflated/zeroed to look complete.

### `crawler/tests/test_siblingfields_vocab.py` (NEW test, COV-03)
**Analog:** `crawler/tests/test_testtype_vocab.py` (whole).
**Copy:** Shared Pattern 2 pin. Assert `siblingfields.SIBLING_FIELDS` == the sibling members of `models/vault.FieldName` == the field names in `extraction._FIELD_SPECS["sibling_proof"]` == the fields `decide_sibling` reads. Drift in any direction fails (mirror `test_canonical_set_equals_registry_accepted_enum` L41-47).

### `crawler/tests/test_auditors_additional.py` (extend test, COV-04)
**Analog:** same-file `TestNomination` / `TestStudy` (L180-233), `_val` / `_ctx` / `_registry` harness (L58-134).
**Copy:** add a `TestSibling` truth table: full confirmed chain → `SUBSTANTIATED`/15; missing field → `GAP` `missing_evidence`; bad enum token → `AT-RISK` `unresolved_sibling`. Extend `_registry()` with a synthetic `additional.sibling` `points_table` row (`level: sibling`, `points: 15`) exactly like the existing `additional.nomination` synthetic row (L70-75). `TestNoInlinedRules` (L235-238) must stay green.

### `crawler/tests/test_full_audit_real_seam.py` (extend test, COV-01 + COV-04)
**Analog:** same-file `_seed_and_run` (L94-142), contamination test (L193-221), CLB-10 comment (L180-185).
**Copy:** Shared Pattern 6. (COV-01) update the stale CLB-10 comment and strengthen to `lang.substantiated_points == 130`; adjust `score_delta` expectation (`124 − 130 = −6`). (COV-04) add a `additional.sibling` claim + a `sibling_proof` document to `_seed_and_run`, assert it reaches `SUBSTANTIATED`, and extend `test_real_seam_no_cross_factor_contamination` to prove sibling evidence never lands under `core.age`/`additional.nomination` and vice-versa.

### `crawler/tests/fixtures/extraction/make_fixtures.py` (extend fixture, COV-03)
**Analog:** same-file `nomination_pdf()` (L170-178), `passport_pdf()` (L181-195), `build_pdf` (L37-81), FAKE constants (L87-98).
**Copy:** add `sibling_proof_pdf()` returning `build_pdf([page])` with distinctive FAKE label lines (`Relationship: brother`, `Status: permanent_resident`, `Residence: ...`, `Date of Birth: <FAKE_DOB>`) matching the `_FIELD_SPECS["sibling_proof"]` label regexes. Generated at test time; never a committed binary; FAKE values only (PII-perimeter tests assert they never reach stdout/corpus).

### `crawler/tests/test_conformance_v40_no_false_green.py` (extend test, COV-03/04)
**Analog:** same-file `_FIELD_FOR` (L66-80), `_BLOCKING_STATES` (L61), seeding helpers (L121-162).
**Copy:** Shared Pattern 7. Change `_FIELD_FOR["additional.sibling"]` from the `"issuer"` placeholder (L79) to a genuine sibling field (`"sibling_relationship"`) so the blocking-state matrix (`pending/rejected/low_quality/ambiguous/stale`) exercises real sibling evidence the decider actually reads.

---

## Integration Seams to Preserve (do NOT modify or fork)

| # | Seam | Location | Why it must be preserved |
|---|------|----------|--------------------------|
| 1 | Frozen grounding gate | `crawler/auditor.py:75-92` (`_gate_or_raise`) → `crs_rules.validate_registry` | The ONLY trust path; every new point row / sibling citation is re-checked. Forking widens the guarantee. Never add a second grounding check. |
| 2 | Generalized point readers | `crawler/auditors/core.py:180-203` (`_grounded_points`), `crawler/crs_audit.py:231-284` (`score_factor`) | Already iterate `points_by_level` by level+label — COV-01 needs NO code change here; touching them risks the parity gate. |
| 3 | Extraction quarantine + boundary | `crawler/vault.py:785-825` (forces `pending`), `models/vault.py:75-93` (`FieldName`) | New sibling fields inherit pending-first quarantine + boundary validation for free. Land `FieldName` + `_FIELD_SPECS` + `siblingfields.py` together or extraction persists nothing. |
| 4 | Eligibility choke point (5-key staleness) | `crawler/vault.py:1060-1099` (`is_audit_eligible` / `audit_eligible_values`) | Blocks pending/rejected/low_quality/ambiguous/stale before any decider sees it — the fail-closed guarantee `decide_sibling` relies on. Do not read raw values around it. |
| 5 | Claimed-scoped linkage | `crawler/extraction.py:325-344` (`_resolve_factor` + `_DOC_TYPE_FACTOR`) | A sibling doc links to `additional.sibling` ONLY if claimed (parameterized SQL). This structurally prevents cross-factor contamination — do not bypass with a bespoke join. |
| 6 | citation_id ↔ evidence_id namespace firewall | `crawler/models/audit.py:80-105, 234-249`; spine attaches ids at `auditor.py:229-250` | `ev_` evidence stays vault-only; corpus `relpath#ordinal` stays public. Deciders never touch either id namespace; COV-02 counts carry no PII. |
| 7 | Public envelope shape | `crawler/models/audit.py:125-147` (`PublicAuditEnvelope`, `counts: dict[str,int]`, `extra="forbid"`) | COV-02 surfacing is an additive `counts["unpriced"]` key plus a backward-compatible card field with a default — no schema change or migration. |
| 8 | `no_inlined_volatile_rules` static gate | `crawler/crs_rules.py:406-440`; scope test `test_crs_no_inlined_rules.py:26-39` (scans `crawler/auditors/`, `crawler/auditor.py`, `skills/crs-auditors/**`, `data/crs_rules/*.yaml`) | A `CLB N` or points literal (`15/25/30/50/100/200/600`) in decider `.py` or auditor prose trips it. Points live ONLY in grounded YAML rows; `siblingfields.py` carries names only. |
| 9 | Vault-only PII + screening framing | `crawler/audit_report.py:54-72` (`SCREENING_NOTICE`), vault-only write path | New sibling values + unpriced lines are PII-bearing → stay under the vault; `SUBSTANTIATED` stays narrowly defined; no approval/outcome language. |
| 10 | Conversion→level→points chain | `crawler/crs_audit.py:100-124` (`to_clb`), `auditors/core.py:78-91` (`_sum_points`) | COV-01 closes the pricing side so `_sum_points` no longer returns `None` for a lowest ability at CLB≠9; conversion rows are unchanged. |

---

## No Analog Found

None. Every planned file extends a shipped analog or mirrors a shipped template. This
is the phase's defining property (RESEARCH.md §Summary: "the wiring already exists;
the data/vocabulary is missing"). If the planner finds itself inventing new machinery
(a `{level:points}` dict, a second grounding check, a bespoke field validator, a new
quarantine path), that is a signal to stop and reuse the seam above instead.

---

## Metadata

**Analog search scope:** `crawler/` (source: `auditors/`, `models/`, `data/crs_rules/`, `extraction.py`, `auditor.py`, `audit_report.py`, `crs_audit.py`, `vault.py`, `testtypes.py`), `crawler/tests/` (test analogs + fixtures), `skills/crs-auditors/` (portable contract).
**Files scanned:** ~26 source + test files read; key symbols located via grep before targeted reads.
**Live verification:** `.venv/bin/python` confirmed conversion levels `{3..10}`, first-language pricing gap (only CLB 9 priced), sibling grounded points `== 15`.
**Read-only:** no source file modified; PATTERNS.md is the only file written.
**Pattern extraction date:** 2026-07-17
