---
phase: 35-coverage-completion
reviewed: 2026-07-17T09:13:15Z
re_reviewed: 2026-07-17T09:41:08Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - crawler/audit_report.py
  - crawler/auditor.py
  - crawler/auditors/additional.py
  - crawler/data/crs_rules/additional.yaml
  - crawler/data/crs_rules/core.yaml
  - crawler/extraction.py
  - crawler/models/audit.py
  - crawler/models/vault.py
  - crawler/siblingfields.py
  - crawler/tests/fixtures/extraction/make_fixtures.py
  - crawler/tests/test_auditors_additional.py
  - crawler/tests/test_conformance_v40_no_false_green.py
  - crawler/tests/test_crs_audit.py
  - crawler/tests/test_extract_confirm_cli.py
  - crawler/tests/test_extraction.py
  - crawler/tests/test_extraction_store.py
  - crawler/tests/test_full_audit_real_seam.py
  - crawler/tests/test_language_points_coverage.py
  - crawler/tests/test_siblingfields_vocab.py
  - crawler/tests/test_unpriced_surfacing.py
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
  warning_fixed: 1
status: clean
fixed:
  - id: WR-01
    fixed_at: 2026-07-17T09:28:20Z
    commits:
      - 4bf084f  # fix(35): canonicalize sibling status/relationship at extraction (WR-01)
      - ad92fdb  # test(35): prove sibling canonicalization + realistic real-seam SUBSTANTIATED (WR-01)
    note: >-
      Added a deterministic, fail-closed extraction-side canonicalizer in
      siblingfields.py (normalize_sibling_status / normalize_sibling_relationship)
      keyed on the shared *_ACCEPTED enums and applied in extraction._extract_fields;
      a realistically-cased real-seam (Brother / Permanent Resident) now reaches
      SUBSTANTIATED and unknown tokens stay AT-RISK unresolved_sibling. decide_sibling
      unchanged; no cloud/model/fuzzy matching; no new dependencies. IN-01 remains
      open (info, deferred).
---

# Phase 35: Code Review Report

**Reviewed:** 2026-07-17T09:13:15Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** clean (WR-01 fixed and verified on re-review; only IN-01 info remains open)

## Summary

Phase 35 (coverage completion) delivers four coherent, well-grounded changes:

- **COV-01** — grounded first-official-language points for every conversion-emitted CLB band `{3–8,10}` in `core.yaml`. I verified against the shipped `corpus/index.db`: every added `#006` quote is a verbatim substring of chunk `guidance/crs-criteria.md#006`, and every point value matches the official IRCC per-ability table (`0/0, 6/6, 8/9, 16/17, 22/23, 29/31, 32/34`). No fabrication; `validate_registry` grounds the row `1/1`.
- **COV-02** — the unpriced-`SUBSTANTIATED` surfacing net (additive `points_unresolved` flag, intrinsic-derived `counts["unpriced"]`, explicit `UNRESOLVED (unpriced)` render). Correct, additive, PII-light; `substantiated_total` is never inflated. Confirmed the net is genuinely reachable (`core.language.second` still only prices CLB 9, so `_sum_points` → `None` → SUBSTANTIATED-but-unpriced fires the flag).
- **COV-03** — shared sibling vocabulary (`siblingfields.py`), `FieldName` + `_FIELD_SPECS['sibling_proof']` extension, claimed-only linkage, three-way anti-drift pin. Producer/consumer agreement holds.
- **COV-04** — reachable, fail-closed `decide_sibling` with an ENFORCED grounded adult gate. The new `additional.sibling.adult` threshold row (`min_value: 18`, `#018`) grounds verbatim ("18 years or older"), the strict `<` boundary math is correct (age 17 → `sibling_minor`; age 18 → adult), and the real-seam adult/minor controls run and pass against the corpus.

**Correctness/security posture is strong:** the frozen `search`→`--cite`→grounding-gate→envelope path is untouched, the grounding gate still consumes and gates BOTH sibling rows, the PII perimeter holds (all `*_pii_perimeter` / publish-safe / privacy-containment gates pass), linkage stays claimed-only with parameterized SQL, and the decider is conjunctive fail-closed with **no false-green path**. Full local suite: **716 passed, 1 skipped** (dupaudit excluded as pre-existingly slow). Grounding: full grid `35/35`, zero violations. The integration-gate fix (`0648d1e`) correctly closed the stale `FieldName` completeness pin and the `.planning/`-prose publish-safe triggers.

The findings below are a robustness gap that undermines the phase's "reachable sibling factor" claim for real-world inputs (fail-closed, so not a blocker) and one low-impact pattern note. No blockers.

## Warnings

### WR-01: Sibling status/relationship enum matching has no extraction-side normalization — genuine documents fail-closed and cannot substantiate; the happy-path tests mask this with pre-normalized fixture tokens

> **STATUS: FIXED** (2026-07-17) — commits `4bf084f` (fix), `ad92fdb` (test).
> An extraction-side canonicalizer now maps natural surface forms onto the shared
> accepted vocabulary; see the **Resolution** block at the end of this finding.
>
> **RE-REVIEW VERIFIED** (2026-07-17T09:41:08Z) — independently confirmed the
> canonicalizer is deterministic, source-of-truth-aligned (`*_ALIASES.values() ⊆
> *_ACCEPTED`), fail-closed for unknown/adversarial tokens (no substring matching;
> `permanent_resident` unreachable as a folded key), idempotent, and touches neither
> dates (DOB stays `kind="date"`) nor `raw_text`. The realistic real-seam
> (`Brother` / `Permanent Resident` → SUBSTANTIATED, grounded 15 pts, `ev_` evidence
> through the real corpus) proves reachability; `decide_sibling`/`core.py`/registry
> YAMLs are byte-identical across the fix (decider NOT weakened). Full crawler suite
> 726 passed / 1 skipped; conformance no-false-green + PII perimeter green;
> publish-safe 0 violations. No Critical/Warning findings remain.

**Files:**
- `crawler/auditors/additional.py:187-190` (exact-token match)
- `crawler/extraction.py:342-343` (text fields stored raw) vs. `crawler/extraction.py:317` (test_type IS normalized)
- `crawler/siblingfields.py:38-47` (snake_case accepted tokens)
- `crawler/tests/fixtures/extraction/make_fixtures.py:101-102,216-219` (fixture pre-formats tokens)

**Issue:**
`decide_sibling` accepts a sibling only when the confirmed value is an EXACT member of the internal snake_case vocabularies `SIBLING_RELATIONSHIP_ACCEPTED = {"brother","sister"}` / `SIBLING_STATUS_ACCEPTED = {"citizen","permanent_resident"}`:

```python
relationship = str(_effective_value(ctx.by_field["sibling_relationship"]))
status = str(_effective_value(ctx.by_field["sibling_status"]))
if (relationship not in siblingfields.SIBLING_RELATIONSHIP_ACCEPTED
        or status not in siblingfields.SIBLING_STATUS_ACCEPTED):
    return DecisionResult("AT-RISK", "unresolved_sibling", confirmed_value=confirmed)
```

But the extractor stores text fields **verbatim** — `raw = norm = val.strip()` (`extraction.py:343`) — with **no canonicalization**, unlike the `test_type` field which is explicitly normalized to the registry vocabulary via `testtypes.normalize_test_type(...)` (`extraction.py:317`, the Phase-30 BLOCKER-B pattern). A real "proof of relative" document prints natural-language values ("Brother", "Permanent Resident", "PR", "Canadian Citizen"), none of which equal the snake_case tokens. I confirmed empirically through the real extraction seam:

```
Extracted from a realistic document:
  sibling_relationship  -> 'Brother'
  sibling_status        -> 'Permanent Resident'
decide_sibling(adult) -> verdict=AT-RISK  reason=unresolved_sibling  points=None
```

The factor only reaches `SUBSTANTIATED` because `make_fixtures.py` hard-codes the exact enum tokens as document text (`FAKE_SIBLING_RELATIONSHIP = "brother"`, `FAKE_SIBLING_STATUS = "permanent_resident"`) — values no genuine document would contain. Every sibling test (`test_auditors_additional.py::TestSibling`, `test_extraction.py::TestSiblingExtraction`, `test_full_audit_real_seam.py` adult control) inherits these pre-normalized tokens, so a green suite does **not** prove the extraction→decide path works for realistic input.

**Impact:** The phase's stated goal — make the already-grounded sibling factor *reachable* through confirmed, claimed-scoped evidence — is only met for synthetic input. For a real applicant, the sibling factor stays `AT-RISK unresolved_sibling` unless they manually *correct* every value to an internal token whose spelling (lowercase, underscore) is surfaced nowhere in the CLI, report, or vocabulary. This is safe (fail-closed, never a false green, no PII/security impact) but leaves the delivered feature effectively non-functional end-to-end and the test coverage over-optimistic — hence WARNING, not BLOCKER.

**Fix:** Add a canonicalizer for the two closed-enum sibling text fields, mirroring `testtypes.normalize_test_type`, applied in `_extract_fields` for `sibling_status`/`sibling_relationship` (case-fold + map common surface forms: `"permanent resident"|"pr"→"permanent_resident"`, `"canadian citizen"|"citizen"→"citizen"`, `"brother"→"brother"`, `"sister"→"sister"`), leaving any unmapped token non-accepted (fail-closed, unchanged verdict). Then add a real-seam/extraction case that drives a **realistically-cased** sibling page (e.g. `Status: Permanent Resident`, `Relationship: Brother`) and asserts `SUBSTANTIATED` — so the happy path is proven on input a real document produces, not on tokens engineered to match the enum.

**Resolution (FIXED 2026-07-17):**

- `crawler/siblingfields.py` — added a deterministic, fail-closed canonicalizer (`_lookup_key` + `SIBLING_STATUS_ALIASES` / `SIBLING_RELATIONSHIP_ALIASES` + `normalize_sibling_status` / `normalize_sibling_relationship`), keyed on the SAME `*_ACCEPTED` enums (the shared source of truth). Case/space/underscore folded; idempotent on canonical tokens; an unrecognized surface form collapses to its own lookup key (NOT an accepted member), so it is never coerced. Stdlib `re` only — no new dependencies.
- `crawler/extraction.py:_extract_fields` — applies the canonicalizer to `sibling_status`/`sibling_relationship` (mirroring the `test_type` BLOCKER-B pattern): `normalized_value` becomes the accepted token while `raw_text` keeps the verbatim surface form. Dates are NOT routed through this path; `decide_sibling` is untouched.
- Coverage: `test_siblingfields_vocab.py::TestSiblingCanonicalization` (fold/idempotency/alias-subset/fail-closed/empty), `test_extraction.py` realistic-cased normalization + unknown-token non-coercion, and `test_full_audit_real_seam.py::test_real_seam_realistic_cased_sibling_reaches_substantiated` (Brother / Permanent Resident → SUBSTANTIATED, 15 pts) plus `test_real_seam_unknown_sibling_tokens_stay_at_risk`. The pre-existing minor AT-RISK control is retained.
- Gates: targeted sibling/extraction/auditor/real-seam suites green (55 passed); `test_crs_no_inlined_rules`, `test_conformance_v40_no_false_green`, `test_extraction_conformance`, privacy-containment + PII-perimeter suites green; `scripts/check_publish_safe.py` clean.

Commits: `4bf084f` (fix), `ad92fdb` (test).


## Info

### IN-01: Import-time producer guard uses a bare `assert`, which is stripped under `python -O`

**File:** `crawler/extraction.py:255-257`

**Issue:** The sibling producer anti-drift guard is an import-time `assert`:

```python
assert {name for name, _regex, _kind in _FIELD_SPECS["sibling_proof"]} == set(
    siblingfields.SIBLING_FIELDS
), "sibling_proof _FIELD_SPECS drifted from siblingfields.SIBLING_FIELDS"
```

Python removes `assert` statements when run with `-O`/`PYTHONOPTIMIZE`, so this "fail-fast at import" guard silently becomes a no-op in an optimized deployment. The practical risk is low — drift can only be introduced by a source edit, and the test-time pin (`test_siblingfields_vocab.py::test_all_three_sibling_field_sets_are_equal`) catches it in CI regardless of `-O` — so this is defense-in-depth only.

**Fix:** If the guard is meant to hold at runtime, replace the bare `assert` with an explicit check that raises unconditionally, e.g.:
```python
if {name for name, *_ in _FIELD_SPECS["sibling_proof"]} != set(siblingfields.SIBLING_FIELDS):
    raise RuntimeError("sibling_proof _FIELD_SPECS drifted from siblingfields.SIBLING_FIELDS")
```
Otherwise, leave it and rely on the CI pin (acceptable — noted for awareness).

---

_Reviewed: 2026-07-17T09:13:15Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
