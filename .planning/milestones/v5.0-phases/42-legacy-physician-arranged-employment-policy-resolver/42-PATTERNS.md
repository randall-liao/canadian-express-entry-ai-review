# Phase 42: Legacy & Physician Arranged-Employment Policy Resolver — Pattern Map

**Mapped:** 2026-07-18
**Files analyzed:** 12 (2 create, 8 modify, 2 freeze-verify)
**Analogs found:** 11 / 12 (1 create has no direct analog — `policy_offer.py`, mitigated by the guard's return-dict contract)

> Consumes: `42-RESEARCH.md`, `42-VALIDATION.md`, `.planning/ROADMAP.md` (Phase 42 detail),
> `.planning/REQUIREMENTS.md` (POLICY-01/02/03 + standing constraints), Phase 40 `40-01-SUMMARY.md`
> (`row_in_effect` delivery), and live code. **This is a data + deciders phase over a shipped stack —
> "analog" means the shipped module the new/changed code copies its shape from, not a scaffold.**
>
> **Standing invariants carried into every assignment below (locked; no CONTEXT.md by design):**
> no auto-green on any `additional.job_offer` path (never `SUBSTANTIATED`, never non-zero/non-`None`);
> no inlined volatile date/NOC/points literal in Python or prose (the `no_inlined_volatile_rules` gate —
> all volatile values live only in the grounded YAML row); the frozen `arranged_employment_guard`
> (and all of `crawler/crs_audit.py`) stays byte-for-byte unchanged; the sidecar ships **inert**
> (no Phase-45 MEC wiring, not registered, not summed into the envelope).

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `crawler/data/crs_rules/additional.yaml` | config (grounded rule data) | transform (data-driven policy) | same file: `additional.job_offer.current`/`.legacy` rows + `additional.sibling.adult` accepted/threshold rows | **exact** |
| `crawler/auditors/additional.py` (`decide_job_offer`) | decider (auditor) | request-response (fail-closed branch) | same fn `decide_job_offer` + `decide_sibling` (grounded fail-closed branch) | **exact** |
| `crawler/crs_rules.py` (`REQUIRED_RULE_IDS`) | config (grid manifest) | transform | `REQUIRED_RULE_IDS["additional_points"]` tuple (crs_rules.py:81) | **exact** |
| `crawler/data/crs_rules/COVERAGE.md` | generated artifact | transform (pure render) | `render_coverage_markdown` / `main` (crs_rules.py:327,501) — regenerate, don't hand-edit | **exact** |
| `crawler/remediation.py` (`_ACTION_TEMPLATES`) | utility (PII-light projection) | transform | `arranged_employment_current` / `arranged_employment_legacy_manual` templates (remediation.py:121,124) | **exact** |
| `crawler/policy_offer.py` **[CREATE]** | service (inert sidecar) | request-response (pure fn → dict) | `crs_audit.arranged_employment_guard` return-dict contract (crs_audit.py:397) | **role-match** (no standalone-module analog) |
| `crawler/extraction.py` (`_FIELD_SPECS` + `_DOC_TYPE_FACTOR`) | utility (doc→factor routing) | transform (extraction) | `employment_reference` spec + `_DOC_TYPE_FACTOR["employment_reference"]` (extraction.py:189,242) | **exact** |
| `crawler/tests/test_physician_policy.py` **[CREATE]** | test (unit) | request-response | `test_auditors_additional.py` (synthetic registry + direct decider drive) | **exact** |
| `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` **[CREATE]** | test (conformance) | batch (negative control sweep) | `test_auditors_additional.py::TestJobOfferTrap` + `test_dli_conformance.py` (frozen + coverage) | **role-match** |
| `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py` (extend) | test (conformance) | batch (grounding sweep) | same file: whole-registry + `TestJobOfferCurrentVsLegacyRealCorpus` (line 105, 162) | **exact** |
| `crawler/tests/test_dli_conformance.py` (`_FROZEN_CONTRACT_PATHS`) | test (conformance) | transform | same file: `_FROZEN_CONTRACT_PATHS` tuple (line 84) + `TestFrozenContractsUnchanged` (line 363) | **exact** |
| `crawler/crs_audit.py` | (FREEZE — verify only) | — | itself (byte-for-byte) — asserted by `test_dli_conformance.py::test_frozen_files_unchanged_vs_head` | **frozen** |

---

## Create / Modify / Freeze Map

| Disposition | File | What changes |
|-------------|------|--------------|
| **CREATE** | `crawler/policy_offer.py` | Inert offer-for-program-eligibility sidecar (POLICY-03). Pure fn, constant `crs_points=0`. |
| **CREATE** | `crawler/tests/test_physician_policy.py` | Physician branch + legacy/repeal regression + sidecar invariant (POLICY-01/02/03). |
| **CREATE** | `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` | Negative control: no `additional.job_offer` path SUBSTANTIATED/non-zero/non-`None`. |
| **MODIFY** | `crawler/data/crs_rules/additional.yaml` | Add `additional.job_offer.physician` grounded row. |
| **MODIFY** | `crawler/auditors/additional.py` | `decide_job_offer`: add physician branch (BEFORE guard delegation). |
| **MODIFY** | `crawler/crs_rules.py` | `REQUIRED_RULE_IDS["additional_points"] += ("additional.job_offer.physician",)`. |
| **MODIFY** | `crawler/data/crs_rules/COVERAGE.md` | Regenerate + commit (generated artifact). |
| **MODIFY** | `crawler/remediation.py` | Add `physician_policy_manual` (+ `offer_for_eligibility_manual`) to `_ACTION_TEMPLATES`. |
| **MODIFY** (recommended) | `crawler/extraction.py` | Add `job_offer` doc type → `additional.job_offer` (reuses `noc_code`). See decision box. |
| **MODIFY** | `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py` | Assert `additional.job_offer.physician` agrees + grounds; disjoint-citation from current/legacy. |
| **MODIFY** | `crawler/tests/test_dli_conformance.py` | Drop `additional.yaml` + `COVERAGE.md` from `_FROZEN_CONTRACT_PATHS`; keep `crs_audit.py`. |
| **FREEZE** | `crawler/crs_audit.py` | No edit. `row_in_effect`/`arranged_employment_guard` already shipped — consume, never re-add. |
| **NO CHANGE** | `crawler/review_packet.py` | Reason codes flow through generically (free-form string) — see Pattern §Reason/Remediation. |

---

## Pattern Assignments

### 1. `crawler/data/crs_rules/additional.yaml` — grounded physician row (config / transform)

**Analog:** the two existing dated job-offer rows in the SAME file — `additional.job_offer.current` (yaml:44) and `additional.job_offer.legacy` (yaml:77) — plus the accepted-enum/threshold shape from `additional.sibling.adult` (yaml:220).

**Row skeleton to copy (dated policy row, `check_type: policy`)** — from `additional.job_offer.current`, `crawler/data/crs_rules/additional.yaml:44-75`:
```yaml
  - rule_id: additional.job_offer.current
    factor_group: additional_points
    factor_ids: [additional.job_offer]          # <-- COPY: physician row uses the SAME factor id
    check_type: policy
    query: job offer points removing Comprehensive Ranking
    selector:
      family: guidance
      marker: "We no longer give points for job offers"
      deny_families:
        - guidance/express-entry-year-end-report
        - guidance/express-entry-midyear
    claim_text: >- ...
    citations:
      - chunk_id: guidance/job-offer.md#001
        quote: "We no longer give points for job offers"
    machine_check:
      kind: policy_flag
      field: job_offer_additional_points
      flag_value: false
      effective_from: "2025-03-25"              # <-- date lives HERE, never in Python
      citation_index: 0
    volatility:
      volatility: volatile
      source_family: guidance
      crawl_date: "2026-06-11T01:09:06Z"
      effective_from: "2025-03-25"
```

**Accepted-enum machine_check shape** (for the physician NOC set) — copy from a `kind: accepted_enum` row; `AcceptedValue` model at `crawler/models/crs_rules.py:105` requires `{value, citation_index}`, and `MachineCheck.effective_from/to` at `crawler/models/crs_rules.py:161-162` carry the window `row_in_effect` reads.

**Concrete physician row to add** — verified-grounded skeleton from `42-RESEARCH.md:176-214` (grounding was executed live this session; keep verbatim):
```yaml
  - rule_id: additional.job_offer.physician
    factor_group: additional_points
    factor_ids: [additional.job_offer]          # SAME factor as current/legacy — no new factor id
    check_type: policy
    query: physician arranged employment offer of employment public policy
    selector:
      family: guidance
      marker: "If you\u2019re a physician with a job offer in Canada"   # U+2019 curly apostrophe — VERIFIED live (see Pitfall 3)
      deny_families:
        - guidance/express-entry-year-end-report
        - guidance/express-entry-midyear
    claim_text: >- ...                          # AT-RISK/manual framing — NEVER "awards points"
    citations:
      - chunk_id: guidance/job-offer.md#002
        quote: "were invited to apply for permanent residence through Express Entry on or after April 25, 2023"
      - chunk_id: pr-pdi/economic-classes-federal-skilled-workers-arranged-employment-awarding-points-applications-received-on-after-may-4-2013.md#020
        quote: "a specialist in clinical and laboratory medicine (NOC 31100), a specialist in surgery (NOC 31101) or a general practitioner and family physician (NOC 31102) under NOC 2021"
    machine_check:
      kind: accepted_enum
      field: physician_noc
      accepted_values:
        - {value: "31100", citation_index: 1}
        - {value: "31101", citation_index: 1}
        - {value: "31102", citation_index: 1}
      effective_from: "2023-04-25"              # grounded via citation_index 0
      citation_index: 0
    volatility:
      volatility: volatile
      source_family: guidance
      crawl_date: "2026-06-11T01:09:06Z"
      effective_from: "2023-04-25"
      # effective_to intentionally OMITTED (null) — policy runs "until revoked by the Minister"
```

**Grounding sources VERIFIED to exist in the live corpus (checked this session):**
- `corpus/guidance/job-offer.md:56` — `If you’re a physician with a job offer in Canada` (apostrophe confirmed `U+2019`).
- `corpus/guidance/job-offer.md:58` — `...invited to apply for permanent residence through Express Entry on or after April 25, 2023...`
- `corpus/pr-pdi/economic-classes-federal-skilled-workers-arranged-employment-awarding-points-applications-received-on-after-may-4-2013.md` — contains `31100/31101/31102`.

**Data-flow consequence (critical — read before wiring):** a row whose `factor_ids` include `additional.job_offer` is pulled into the **consumed subset** for that factor by `crawler/auditor.py::_consumed_rows` (auditor.py:68-72) and is then GATED by `_gate_or_raise` (auditor.py:75-91) **before** the decider runs. So the physician row MUST ground against the operator's real `corpus/index.db` at audit time, exactly like `current`/`legacy` do today — if it fails to ground, the WHOLE `additional.job_offer` factor audit raises `AuditGroundingError` (fail-closed / safe, but an availability regression). This is why grounding verification is mandatory, not optional.

---

### 2. `crawler/auditors/additional.py::decide_job_offer` — physician branch (decider / request-response)

**Analog:** the existing `decide_job_offer` (additional.py:36-65) for the delegate-to-guard skeleton; `decide_sibling` (additional.py:160-217) for the "grounded fail-closed branch that never greens" shape (esp. the `crs_audit.age_on_date` try/except at additional.py:201-206 → mirror it for `row_in_effect`).

**Existing body to preserve verbatim** (additional.py:45-65) — the physician block inserts AFTER the `ita_date is None` guard (line 52-55) and BEFORE the guard delegation (line 56):
```python
    claim_points = getattr(ctx.factor, "claimed_points", None) or 0
    confirmed = _confirmed_snapshot(ctx.by_field)
    if not claim_points:
        return DecisionResult("N/A", "no_job_offer_points", ...)
    if ctx.ita_date is None:
        return DecisionResult("AT-RISK", "arranged_employment_current",
                              ..., substantiated_points=0)
    guard = crs_audit.arranged_employment_guard(
        claim_points, ctx.ita_date, ctx.registry)          # FROZEN — delegate unchanged
    ...
```

**Physician branch to add** (from `42-RESEARCH.md:349-363`) — copy the `row_in_effect` try/except from `decide_sibling`'s `age_on_date` guard (additional.py:201-206):
```python
    # [NEW] Distinct physician public-policy branch — grounded, AT-RISK/manual only.
    phys = next((r for r in ctx.registry.rows
                 if r.rule_id == "additional.job_offer.physician"), None)
    noc_val = ctx.by_field.get("noc_code")
    if phys is not None and not phys.gap and noc_val is not None:
        noc = str(_effective_value(noc_val))               # _effective_value already imported (core.py:45)
        phys_nocs = {av.value for av in (phys.machine_check.accepted_values or [])}
        try:
            in_effect = crs_audit.row_in_effect(phys, ctx.ita_date)   # crs_audit.py:377 — CONSUME, don't re-add
        except (TypeError, ValueError):
            in_effect = False
        if noc in phys_nocs and in_effect:
            return DecisionResult("AT-RISK", "physician_policy_manual",
                                  claimed_value=claim_points, confirmed_value=confirmed,
                                  substantiated_points=None)          # manual; NEVER an award
```

**Contracts this branch must honour:**
- `DecisionResult` fields = `verdict, reason_code, claimed_value, confirmed_value, substantiated_points` (`crawler/auditors/__init__.py:67-81`). `substantiated_points=None` ⇒ manual (mirrors legacy). `A1` in research says `0` is equally safe — planner may pick either; `None` matches the legacy path.
- **Branch ORDER matters (Pitfall 4 below):** the physician check must fire BEFORE `arranged_employment_guard`, because the guard's legacy window `(-∞, 2025-03-25)` overlaps the open physician window `[2023-04-25, ∞)`; wrong order surfaces `arranged_employment_legacy_manual` instead of the distinct `physician_policy_manual` (POLICY-02 requires the distinct citation).
- **No inlined literal:** the NOC set + the `2023-04-25` date come from `phys.machine_check` — NEVER a Python literal. The self-scan `test_auditors_additional.py::TestNoInlinedRules` (line 339) and the aggregate `test_crs_no_inlined_rules.py` cover `crawler/auditors/`; a bare `"31100"`/`"2023-04-25"` in this file would trip `_VOLATILE_POINTS_RE`/`_DATE_RE` (crs_rules.py:421,428) unless it lives in an allow-listed grounded key.
- **Citation surfacing is automatic:** because the physician row's `factor_ids` include `additional.job_offer`, the spine adds it to the consumed subset and attaches its citation id to the card (`crawler/auditor.py:99-113, 211-213`). The decider must NOT set citation ids itself (`__init__.py:69-75`).

---

### 3. `crawler/crs_rules.py::REQUIRED_RULE_IDS` — grid manifest (config / transform)

**Analog:** the `additional_points` tuple, `crawler/crs_rules.py:81-88`:
```python
    "additional_points": (
        "additional.nomination",
        "additional.job_offer.current", # arranged-employment repeal (0 as of 2025-03-25)
        "additional.job_offer.legacy",  # distinct ITA-era legacy row (grounded or gap)
        "additional.study",
        "additional.french",
        "additional.sibling",
    ),
```

**Change:** add `"additional.job_offer.physician",` to the tuple. `_covers` (crs_rules.py:280) is prefix-exact on dotted components, so `additional.job_offer.physician` covers ONLY the new label — it does NOT cover `.current` or `.legacy`, and `.current`/`.legacy` do not cover it. Adding the label makes `coverage_report` (crs_rules.py:287) require a present non-gap physician row (a future removal is then caught by `test_conformance_v40::test_coverage_complete_or_documented_gaps`).

> **Is this strictly necessary?** No — `retrieve_what_you_cite` (crs_rules.py:231) already sweeps ALL non-gap rows, so the physician row is grounding-checked whether or not it is a required label. Adding it to `REQUIRED_RULE_IDS` is the **recommended** belt-and-suspenders (research A-note / ROADMAP "coverage remains complete") so the grid manifest documents the physician slot. **Either way, adding it FORCES a COVERAGE.md regeneration (§4).**

---

### 4. `crawler/data/crs_rules/COVERAGE.md` — generated artifact (transform / pure render)

**Analog / generator:** `render_coverage_markdown` (crs_rules.py:327) + `main` (crs_rules.py:501). COVERAGE.md is a **pure function of the registry** — do NOT hand-edit.

**Regenerate command** (from the staleness assertion message, `test_conformance_v40_retrieve_what_you_cite.py:145`):
```bash
.venv/bin/python -m crawler.crs_rules > crawler/data/crs_rules/COVERAGE.md
```
Then COMMIT it. Two tests pin freshness: `test_conformance_v40::test_committed_coverage_md_not_stale` (line 139, byte-compares committed vs fresh render) and — until §11 lands — `test_dli_conformance.py::_FROZEN_CONTRACT_PATHS` (line 94).

---

### 5. `crawler/remediation.py::_ACTION_TEMPLATES` — reason→action projection (utility / transform)

**Analog:** the two existing arranged-employment templates, `crawler/remediation.py:121-126`:
```python
    "arranged_employment_current": (
        "The claimed arranged-employment points for {factor} need review against the "
        "current policy; this requires human or professional assessment."),
    "arranged_employment_legacy_manual": (
        "The claimed legacy arranged-employment points for {factor} require manual, "
        "professional review of the transition-period policy."),
```

**Add:**
```python
    "physician_policy_manual": (
        "The claimed physician public-policy arranged-employment case for {factor} "
        "requires manual, professional review; it is not an automatic points award."),
    "offer_for_eligibility_manual": (           # only if the sidecar reason surfaces
        "The job offer for {factor} may support program eligibility but awards no CRS "
        "additional points; confirm program-eligibility use with a professional."),
```

**Constraints (both templates):** generic screening prose, parameterized ONLY by `{factor}` (see `_action_for`, remediation.py:148-153); carry **NO** volatile threshold (no date/NOC/points) — the aggregate no-inlined gate covers `remediation.py` (`test_crs_no_inlined_rules.py:29-32,47`). Unknown reason codes fall back to `_DEFAULT_ACTION_BY_KIND` (remediation.py:135), so a missing template degrades safely to the generic `at_risk` action — but add the specific template for a clear surface.

---

### 6. `crawler/review_packet.py` — NO CODE CHANGE (reason surfaces generically)

**Why no change:** reason codes are free-form strings that flow verbatim through the two-tier projection. `build_packet` copies `reason_code` straight from the remediation item (`crawler/review_packet.py:170-180`) and `render_packet_markdown` prints ``f"- Reason: `{finding.reason_code}`"`` (review_packet.py:219). `physician_policy_manual` therefore appears on the packet with no template plumbing beyond §5's `_ACTION_TEMPLATES` entry (which supplies `finding.action`). **Do not add a physician special-case to review_packet.py** — that would fork the projection.

---

### 7. `crawler/policy_offer.py` **[CREATE]** — inert offer-for-eligibility sidecar (service / request-response)

**No standalone-module analog exists** (grep confirms no `policy_offer`/`for_program_eligibility` in the tree). Closest shape analog is the **return-dict contract** of `arranged_employment_guard` (crs_audit.py:397-433), which returns `{status, points, citation}`. Copy that dict-return discipline; do NOT register it.

**Pattern (from `42-RESEARCH.md:222-243`):**
```python
# crawler/policy_offer.py  (NEW, inert until Phase 45 MEC consumes it)
def offer_for_program_eligibility(claim_points, ita_date, registry) -> dict:
    present = bool(claim_points)
    current = next((r for r in registry.rows
                    if r.rule_id == "additional.job_offer.current"), None)
    return {
        "offer_present": present,
        "eligibility_status": "AT-RISK" if present else "N/A",  # NEVER "SUBSTANTIATED"
        "crs_points": 0,                                        # CONSTANT — no assignment path
        "for_program_eligibility_only": True,
        "reason": "offer_for_eligibility_manual",
        "citation": current.citations[0].chunk_id if current else None,
    }
```

**Inert-by-construction requirements (POLICY-03):**
- NOT registered via `crawler/auditors/__init__.py::register` (an unregistered factor already resolves to the AT-RISK `_default_decider`, __init__.py:103; the sidecar is separate from that dispatch entirely).
- NOT added to `FULL_GRID_FACTORS` (__init__.py:120) and NOT summed into any envelope.
- `crs_points` is a literal `0` with no branch that reassigns it — the negative-control test (§9) asserts this over all inputs.
- No new Phase-45 wiring: the sidecar is shipped + unit-tested only (research A3/Q7). Reuse `additional.job_offer.current`'s already-grounded citation rather than adding a new grounded surface.
- No inlined volatile literal (the `0` is not in `_VOLATILE_POINTS_RE`'s set `{15,25,30,50,100,200,600}`, so it is clean; keep it that way — do NOT add a 200/50 points reference).

---

### 8. `crawler/extraction.py` — `job_offer` doc type (utility / transform) — RECOMMENDED, see decision box

**Analog:** the `employment_reference` field spec (extraction.py:189-199, which ALREADY carries `noc_code`) and its factor mapping `_DOC_TYPE_FACTOR["employment_reference"] = "core.work"` (extraction.py:242).

**`noc_code` field spec to reuse** (extraction.py:191-192) — same regex + `noc` kind (normalized to a 5-digit string at extraction.py:336-341):
```python
        ("noc_code", r"(?:NOC(?: Code)?|National Occupational Classification)", "noc"),
```

**Change:**
```python
_FIELD_SPECS["job_offer"] = [
    ("noc_code", r"(?:NOC(?: Code)?|National Occupational Classification)", "noc"),
    ("issuer",  r"(?:Employer|Company|Organization)", "text"),          # optional, inert to the decider
    ("employment_start", r"(?:Start Date|Employment Start)", "date"),    # optional, inert to the decider
]
_DOC_TYPE_FACTOR["job_offer"] = "additional.job_offer"
```

**Why this is contamination-free (verified):** value→factor linkage is a property of the **document**, resolved once by `_resolve_factor` (extraction.py:362-381), which links ONLY when the target factor is actually claimed (parameterized lookup — no SQL injection surface) and returns `None` otherwise (fail-closed, no cross-factor leak). A `job_offer` doc's `noc_code` becomes a SEPARATE `ExtractedValue` with `factor_id == "additional.job_offer"`, distinct from an `employment_reference` doc's `noc_code` (`factor_id == "core.work"`); `audit_eligible_values` is factor-scoped (`crawler/vault.py:1099-1117`), so the two never mix. This exact non-leak is already asserted for the shared `issuer` field by `test_extraction_factor_linkage.py::test_issuer_field_does_not_leak_across_doc_types` (line 135-158) and `::test_no_cross_group_contamination` (line 160) — **copy that test shape for a `job_offer`+`employment_reference` NOC non-leak test.**

**No vault migration:** `noc_code` is already in the closed `FieldName` vocabulary (`crawler/models/vault.py:88`) — no `FieldName` change, no confirm-CLI change.

---

### 9. `crawler/tests/test_physician_policy.py` **[CREATE]** — unit (POLICY-01/02/03)

**Analog:** `crawler/tests/test_auditors_additional.py` — the whole file is the template (stdlib `unittest`, NO network, NO vault; synthetic `Registry` + synthetic `ExtractedValue` by_field; drive `ad.decide_job_offer` directly).

**Copy these fixtures verbatim** (test_auditors_additional.py):
- `_arow(...)` grounded-row builder with `eff_from`/`eff_to` (line 43-55) — extend it to build the physician `accepted_enum` row (add an `accepted_values`/`machine_check` path like the `additional.sibling.adult` threshold row at line 107-110).
- `_registry()` (line 68-126) — add a physician row to the synthetic registry.
- `_val(field, value)` confirmed `ExtractedValue` factory (line 129-133) — build `_val("noc_code", "31100")`.
- `_ctx(...)` `DecisionContext` builder (line 136-143).
- `TestJobOfferTrap` (line 155-186) is the direct pattern for the physician/legacy/repeal assertions.

**Assertions to add (mirror TestJobOfferTrap style):**
- Confirmed physician NOC (`31100`) + `ita_date` in the physician window ⇒ `verdict == "AT-RISK"`, `reason_code == "physician_policy_manual"`, `substantiated_points is None`, `assertNotEqual(verdict, "SUBSTANTIATED")`.
- Physician NOC but `ita_date` = `None` ⇒ falls through to `arranged_employment_current` (window unevaluable) — still AT-RISK/0.
- Non-physician NOC (`21234`) in the legacy window ⇒ `arranged_employment_legacy_manual` (NOT physician).
- Physician NOC in legacy window ⇒ `physician_policy_manual` wins (branch-order proof for Pitfall 4).
- Missing `noc_code` (empty `by_field`) ⇒ delegates to guard (never physician).
- Sidecar sweep (`-k sidecar`): for `claim_points` ∈ {0, 200, 999} → `crs_points == 0`, `eligibility_status ∈ {"AT-RISK","N/A"}`, `assertNotEqual(status, "SUBSTANTIATED")`.
- `TestNoInlinedRules` (line 339-342) — copy verbatim, scanning `[ad.__file__, policy_offer.__file__]`.

---

### 10. `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` **[CREATE]** — conformance negative control

**Analogs:** `test_auditors_additional.py::TestJobOfferTrap` (the "never SUBSTANTIATED" assertions) for the mechanism, and `test_dli_conformance.py` (line 84 `_FROZEN_CONTRACT_PATHS`; line 363 `TestFrozenContractsUnchanged`; line 388 `TestInertStudyDecider`) for the conformance-class + frozen-guard + coverage-stays-complete shape.

**What to assert (POLICY-03 negative control — no `additional.job_offer` path greens):**
- Sweep every `additional.job_offer` outcome the decider can produce (repeal, legacy, physician, N/A) over a synthetic registry: assert NONE returns `verdict == "SUBSTANTIATED"` and NONE returns a truthy `substantiated_points` (i.e. `substantiated_points in (None, 0)`).
- `crs_audit.arranged_employment_guard` returns `status != "SUBSTANTIATED"` and `points in (None, 0)` for any non-zero claim across window edges (2024-06-01 legacy, 2026-01-01 post-repeal).
- `policy_offer.offer_for_program_eligibility` returns `crs_points == 0` and `eligibility_status != "SUBSTANTIATED"` for all inputs.
- **Frozen guard**: assert `crawler/crs_audit.py` byte-identity via `git diff --quiet HEAD -- crawler/crs_audit.py` (copy `TestFrozenContractsUnchanged`, test_dli_conformance.py:367-382; guard with `@skipUnless(_GIT_ROOT is not None)`).

**Naming note (no Phase-45/46 wiring):** name it `test_conformance_v5_policy_no_job_offer_green.py`. The current release-gate runner glob is `test_conformance_v4[01]_*.py` (`scripts/run_conformance.py:35`), so this v5 file is intentionally NOT captured by the v4.x gate this phase — Phase 46 will introduce the v5 glob. It still runs in the full `crawler/tests` suite. **Do not touch `scripts/run_conformance.py`.**

---

### 11. `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py` — extend (conformance / grounding)

**Analog:** same file — `TestRetrieveWhatYouCiteWholeRegistry` (line 105, `@skipUnless(_REAL_DB.is_file())`) already sweeps ALL non-gap rows (so the physician row is auto-covered) and `TestJobOfferCurrentVsLegacyRealCorpus` (line 162) is the exact template for a per-row physician assertion.

**Add** (mirroring lines 173-197): a physician-specific check asserting `report["additional.job_offer.physician"]["agrees_with_citation"]` and `["grounds"]` are True, the selected chunk starts with `guidance/`, and the physician citation ids are DISJOINT from `current`/`legacy` (no cross-ground). Reuse the `@skipUnless(_REAL_DB.is_file())` guard (line 157) so a fresh clone stays structural-only. `test_committed_coverage_md_not_stale` (line 139) and `test_static_no_inlined_volatile_gate_is_clean` (line 149) already enforce the COVERAGE.md regen (§4) and the no-inlined gate — no new assertion needed there.

---

### 12. `crawler/tests/test_dli_conformance.py::_FROZEN_CONTRACT_PATHS` — realign frozen intent

**Analog:** the tuple itself, `crawler/tests/test_dli_conformance.py:84-95`:
```python
_FROZEN_CONTRACT_PATHS = (
    "crawler/searchindex.py",
    "crawler/dupaudit.py",
    "crawler/grounding.py",
    "crawler/crs_audit.py",                       # KEEP — the frozen guard
    "crawler/index_health.py",
    "crawler/data/crs_rules/additional.yaml",     # DROP — legitimate Phase-42 mutation target
    "crawler/data/crs_rules/core.yaml",
    "crawler/data/crs_rules/spouse.yaml",
    "crawler/data/crs_rules/transferability.yaml",
    "crawler/data/crs_rules/COVERAGE.md",         # DROP — regenerated this phase
)
```

**Change:** remove `additional.yaml` and `COVERAGE.md` (they are Phase-42 mutation targets); keep `crawler/crs_audit.py` (and the rest) frozen. `TestFrozenContractsUnchanged` uses `git diff --quiet HEAD` (line 374-377), so committed edits pass regardless — but the tuple's INTENT ("additional.yaml frozen") is now stale and MUST be realigned to avoid a misleading green/red (research Pitfall 5, A5).

---

## Shared Patterns

### Frozen-guard delegation (never re-implement the award decision)
**Source:** `crawler/crs_audit.py::arranged_employment_guard` (crs_audit.py:397-433) and `row_in_effect` (crs_audit.py:377-394).
**Apply to:** `decide_job_offer`, `policy_offer.py`, both new tests.
The guard is the SOLE CRS-additional-points award chokepoint and returns AT-RISK-only. The physician branch overlays a *reason + citation* and delegates the award to the guard unchanged. `row_in_effect` is a Phase-40 additive predicate (`40-01-SUMMARY.md:13,64`) — CONSUME it; do not add window math. **crs_audit.py stays byte-for-byte frozen.**

### Grounding-by-construction gate (one trust path)
**Source:** `crawler/auditor.py::_gate_or_raise`/`gate_subset` (auditor.py:75-91) → `crs_rules.validate_registry` (crs_rules.py:168) → `grounding.check_answer`.
**Apply to:** the physician row (it joins the gated consumed subset — must ground live), all conformance tests.
Never fork the substring check; every physician quote is proven a verbatim corpus substring by the shipped gate. `retrieve_what_you_cite` (crs_rules.py:231) additionally proves the baked query+selector re-selects the cited chunk (`agrees_with_citation`).

### No inlined volatile rule (static gate)
**Source:** `crawler/crs_rules.py::no_inlined_volatile_rules` + `_ALLOW_KEYS`/`_VOLATILE_POINTS_RE`/`_DATE_RE` (crs_rules.py:402-455).
**Apply to:** `additional.py` (physician branch), `policy_offer.py`, `remediation.py`, `additional.yaml`.
The `2023-04-25` date and the `31100/31101/31102` NOCs live ONLY in the grounded YAML row (allow-listed keys `effective_from`, `value`, `quote`); a bare literal in Python/prose trips the gate. Covered by `test_crs_no_inlined_rules.py`, `test_auditors_additional.py::TestNoInlinedRules`, and `test_conformance_v40::test_static_no_inlined_volatile_gate_is_clean`.

### Fail-closed / never-green + PII-light reason tokens
**Source:** `_default_decider` (`__init__.py:103`), `decide_sibling`'s minor/unresolved branches (additional.py:191-210), `DecisionResult` (`__init__.py:67-81`).
**Apply to:** every new verdict path.
Every physician/sidecar/legacy outcome is `AT-RISK`/manual or `N/A` — never `SUBSTANTIATED`, never non-zero/non-`None`. Reason codes (`physician_policy_manual`, `offer_for_eligibility_manual`) are PII-free string tokens; PII stays vault-only (`_confirmed_snapshot`, core.py:52) and never crosses into the public reason/citation surface.

### Per-document factor linkage (no cross-factor contamination)
**Source:** `crawler/extraction.py::_resolve_factor` (extraction.py:362-381); `vault.audit_eligible_values` (vault.py:1099).
**Apply to:** the `job_offer` doc type, the extraction non-leak test.
Linkage is per-document and factor-scoped; a `job_offer` NOC (→ `additional.job_offer`) never mixes with an `employment_reference` NOC (→ `core.work`). Guarded by the `issuer`/cross-group non-leak tests (`test_extraction_factor_linkage.py:135,160`).

---

## Targeted Verifications (as requested)

### Is adding a `job_offer` extraction doc type SAFE?
**Yes — safe and contamination-free.**
- Reuses the existing `noc_code` `FieldName` (vault.py:88) → **no vault vocabulary migration**, no confirm-CLI change.
- Value→factor linkage is per-document via `_resolve_factor` (extraction.py:362-381), which links ONLY to a claimed factor and returns `None` otherwise (fail-closed). The `job_offer` NOC (`factor_id=additional.job_offer`) is a distinct row from an `employment_reference` NOC (`factor_id=core.work`); `audit_eligible_values` is factor-scoped (vault.py:1099). The non-leak is the SAME property already tested for `issuer` (`test_extraction_factor_linkage.py:135`).
- Extra fields (`issuer`, `employment_start`) routed under `job_offer` are inert — `decide_job_offer` reads only `noc_code`.
- No frozen-file impact: `extraction.py` is NOT in `_FROZEN_CONTRACT_PATHS`; no test pins the full `_DOC_TYPE_FACTOR` key set (the only pin is `passport`/`identity` → `core.age`, `test_extraction_factor_linkage.py:288-289`, unaffected).

### Is it NECESSARY?
**No — necessary only for the confirmed-evidence trigger, not for safety.** Today `by_field` for `additional.job_offer` is always `{}` (no doc type routes a field there), so the physician branch never fires from real evidence (research Pitfall 4). Wiring the doc type is what lets a confirmed physician NOC reach `decide_job_offer` end-to-end. The lighter **claimed-side** alternative (read a physician marker off the claimed factor, no extraction change) is still AT-RISK-safe because the outcome is AT-RISK regardless (research A2, Alternatives table). **Planner decides**; the recommended path is the extraction doc type (evidence-confirmed, testable end-to-end).

### How to avoid cross-factor contamination (physician vs legacy vs current vs other factors)
1. **Same factor id, distinct rows:** physician/current/legacy all use `factor_ids: [additional.job_offer]` and DISJOINT citation chunks — the disjoint-citation invariant is already asserted for current/legacy (`test_conformance_v40_retrieve_what_you_cite.py:195-197`); extend it to physician.
2. **Distinct rule_id, prefix-exact coverage:** `_covers` (crs_rules.py:280) is prefix-exact, so `additional.job_offer.physician` covers only its own label — no bleed into `.current`/`.legacy`.
3. **Branch order in `decide_job_offer`:** physician check BEFORE guard delegation (overlapping windows — Pitfall 4).
4. **Extraction linkage per-document** (see safety answer above) — no bleed into `core.work`/`additional.study`/etc.
5. **Selector `deny_families`** on the physician row keeps it grounding from `guidance/` (+ PDI), never from category-based-round content (Pitfall 6).

---

## Common Pitfalls (carried from RESEARCH, mapped to code)

1. **Legacy/physician auto-green (P0):** any `substantiated_points` truthy on a job-offer card, or the sidecar returning `SUBSTANTIATED`/non-zero `crs_points`. Mitigation: §2/§7 constants + the §10 negative control. The corpus prose says the physician policy "allows you to earn points… in the CRS" — this is a TRAP; the 2025-03-25 repeal removed job-offer CRS points for ALL candidates, so the physician case is `AT-RISK`/manual, never an award.
2. **Consumed-subset grounding regression:** the physician row joins the gated subset (auditor.py:68-91); if its quote doesn't ground against the operator's `corpus/index.db`, the WHOLE `additional.job_offer` audit fails closed. Mitigation: keep the verified quotes verbatim; verify grounding (§11).
3. **Curly-vs-straight apostrophe drift:** `corpus/guidance/job-offer.md:56` uses `U+2019` (confirmed this session). The `selector.marker` and any quote must match the exact codepoint — grounding is whitespace/case-normalized but NOT Unicode-folded (`grounding.check_answer`).
4. **Physician window mis-scoped vs legacy window:** legacy `(-∞, 2025-03-25)` overlaps physician `[2023-04-25, ∞)`. Check physician + `row_in_effect` BEFORE the guard, else the legacy reason wins and POLICY-02's distinct citation is lost.
5. **COVERAGE.md staleness + frozen-file test:** regenerate + commit COVERAGE.md (§4) AND drop `additional.yaml`/`COVERAGE.md` from `_FROZEN_CONTRACT_PATHS` (§12); keep `crs_audit.py` frozen.
6. **Wrong physician source:** cite `guidance/job-offer.md#002` (date) + the FSW arranged-employment PDI `#020` (NOC set) — NEVER `mi-rounds/*` / category-based-selection (that is the physician category-based ROUND, a different mechanism).

---

## No Analog Found

| File | Role | Data Flow | Reason / Mitigation |
|------|------|-----------|---------------------|
| `crawler/policy_offer.py` | service (inert sidecar) | request-response | No standalone "returns dict, not registered as a decider" module exists in `crawler/`. Mitigation: copy the return-dict contract of `arranged_employment_guard` (crs_audit.py:397) and the inert/never-registered discipline from `_default_decider` (`__init__.py:103`); the exact skeleton is in `42-RESEARCH.md:222-243`. |

---

## Metadata

**Analog search scope:** `crawler/` (crs_audit, crs_rules, auditors/, models/, extraction, vault, remediation, review_packet, auditor), `crawler/data/crs_rules/`, `crawler/tests/`, `corpus/guidance/`, `corpus/pr-pdi/`, `scripts/`.
**Files scanned (read):** 18 source/data/test files + 2 corpus sources + ROADMAP/REQUIREMENTS/RESEARCH/VALIDATION + Phase-40 summary.
**Grounding sources confirmed present:** `corpus/guidance/job-offer.md` (physician + repeal), `corpus/pr-pdi/economic-classes-federal-skilled-workers-arranged-employment-awarding-points-applications-received-on-after-may-4-2013.md` (NOC 31100/31101/31102). Curly apostrophe `U+2019` verified.
**Pattern extraction date:** 2026-07-18
