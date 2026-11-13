# Phase 42: Legacy & Physician Arranged-Employment Policy Resolver - Research

**Researched:** 2026-07-18
**Domain:** Grounded, fail-closed, effective-dated CRS policy resolution over a shipped 900+-test local-first, PII-safe, corpus-grounded post-ITA Express Entry auditor (Python 3.10, zero-runtime-dep). Extends — never weakens — the frozen `arranged_employment_guard`.
**Confidence:** HIGH (every recommendation is tied to a directly-inspected code seam and a corpus span whose grounding was executed live this session; the two authoritative policy facts were additionally cross-checked against the live canada.ca pages.)

## Summary

Phase 42 resolves the three arranged-employment edge cases v4.x deliberately left `AT-RISK`, using **grounded, effective-dated rule rows** and a distinct physician branch, while keeping the shipped `crawler/crs_audit.py::arranged_employment_guard` **byte-for-byte frozen**. The mechanics already exist: the guard reads the 2025-03-25 repeal date and the legacy window from grounded metadata and returns `AT-RISK`/0 (post-repeal) or `AT-RISK`/`points is None` (in-window legacy), **never** `SUBSTANTIATED`. Phase 40 already shipped the additive `crs_audit.row_in_effect(row, reference_date)` predicate (composes `_in_window` over both grounded window sources) — Phase 42 **consumes it**, it does not add date machinery.

The net-new work is small and data-centric: (1) one grounded `additional.job_offer.physician` rule row in `additional.yaml` carrying an `effective_from: "2023-04-25"` window and a physician-NOC accepted set, both grounded from the pinned corpus; (2) a new physician branch in `decide_job_offer` (the MODIFY-able auditor, not the frozen guard) that emits a distinct `AT-RISK "physician_policy_manual"` verdict citing that row; (3) a new remediation reason code; and (4) an **inert** offer-for-program-eligibility sidecar that structurally cannot award CRS points, ready for Phase 45 (MEC) to consume as an `AT-RISK` input. The single highest-stakes regression is a legacy/physician **auto-green** — the entire phase is engineered so no `additional.job_offer` path can ever return `SUBSTANTIATED` or non-zero/non-`None` points.

**Two authoritative facts were verified live and are grounded in the pinned corpus:** the **2025-03-25** CRS job-offer removal (current *and* future candidates) and the physician temporary public policy for candidates **invited on/after April 25, 2023** providing **publicly funded medical services** (in effect until revoked by the Minister — no fixed end date). The corpus crawl (2026-06-11) matches the live canada.ca pages (date-modified 2026-06-22 / 2023-05-02).

**Primary recommendation:** Ship the physician case as a grounded, effective-dated **data + decider-branch + reason-code** change (no new machinery, guard untouched); trigger the physician branch from a confirmed physician `noc_code` matched against a grounded physician-NOC set + `row_in_effect(physician_row, ita_date)`; keep every output `AT-RISK`/manual or 0; deliver the offer-for-MEC surface as an inert, constant-`crs_points=0` sidecar. **Do not modify `crawler/crs_audit.py`.**

## Project Constraints (from copilot-instructions.md + REQUIREMENTS standing constraints)

> No `CONTEXT.md` exists for this phase by design (`workflow.skip_discuss: true`; "Planning and execution are autonomous… do not interrupt the operator"). These standing constraints therefore carry locked-decision authority and the plan MUST honor them.

- **Authoritative sources only** — IRCC canada.ca guidance, Justice Laws IRPA/IRPR, IRCC PDIs, Ministerial Instructions. Third-party/blog content is not authoritative. `[CITED: .github/copilot-instructions.md ## Constraints]`
- **Grounding is mandatory** — every requirement claim (every date, points value, policy fact) must be backed by a citation resolvable to the curated corpus; the `no_inlined_volatile_rules` static gate + the retrieve-what-you-cite grounding check enforce this. No ungrounded assertions; no inlined volatile literals in Python/prose. `[VERIFIED: crawler/crs_rules.py]`
- **Fail-closed verdicts** — stale / superseded / out-of-window / unconfirmed can NEVER green. `[VERIFIED: REQUIREMENTS.md standing constraints]`
- **No new trust path** — reuse the frozen search → `--cite` → grounding-gate → JSON-envelope pipeline. No model / NLI / vector / cloud semantic auto-resolution. `[CITED: REQUIREMENTS.md]`
- **Prefer zero new dependencies** — any addition needs strong justification + a supply-chain gate. Current runtime deps are exactly `{pyyaml, pydantic, platformdirs}` (pinned by `test_dli_conformance.py`). `[VERIFIED: pyproject.toml + crawler/tests/test_dli_conformance.py]`
- **No legal advice / no eligibility-or-outcome prediction / no automated IRCC submission.** Output is *screening* + evidence organization, framed via `SCREENING_NOTICE`. `[CITED: REQUIREMENTS.md]`
- **PII stays vault-only; stdout / envelope / snapshot PII-light** — `ev_` ids never mixed with corpus `relpath#ordinal` citation ids; no absolute paths on stdout. `[VERIFIED: crawler/models/crs_rules.py, crawler/vault.py]`
- **Tech stack** — Python 3.10–3.13; stdlib + the three pinned deps. Tests via `pytest`. `[VERIFIED: pyproject.toml]`

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **POLICY-01** | A pre-2025-03-25 in-window legacy arranged-employment claim receives a grounded `AT-RISK`/manual verdict selected by effective-dated rule windows — never `SUBSTANTIATED`/auto-green — while a post-repeal claim stays `AT-RISK`/0. | **Already shipped and frozen.** `arranged_employment_guard` returns `AT-RISK`/`points is None` for a grounded in-window legacy row (`additional.job_offer.legacy`, `volatility.effective_to: "2025-03-25"`) and `AT-RISK`/0 default citing `additional.job_offer.current` (`effective_from: "2025-03-25"`). Phase 42 must PRESERVE this — verified by `test_auditors_additional.py::test_in_window_legacy_is_at_risk_manual` / `::test_non_zero_claim_is_at_risk_zero_current`. See Standard Stack + Pitfall 1. |
| **POLICY-02** | A physician / public-policy special case receives a grounded `AT-RISK`/manual verdict citing the distinct physician public-policy rule row, separate from the general repeal path. | **Net-new.** Add grounded `additional.job_offer.physician` row (`effective_from: "2023-04-25"`, physician-NOC accepted set) + a `decide_job_offer` physician branch emitting `AT-RISK "physician_policy_manual"`. Grounding verified live against `guidance/job-offer.md#002` (date) and the FSW arranged-employment PDI `#020` (NOC 31100/31101/31102). See Pattern 1 + Code Examples. |
| **POLICY-03** | A valid offer can inform an MEC program-eligibility input without ever greening CRS additional points, and the shipped `arranged_employment_guard` remains byte-for-byte frozen. | **Net-new, inert.** Deliver a standalone sidecar (`offer_for_program_eligibility`) that returns a constant `crs_points = 0`, an `AT-RISK`/`N/A` eligibility status (never `SUBSTANTIATED`), and a grounded citation — not registered as a CRS decider, not summed into the envelope. Guard file stays frozen (asserted by `test_dli_conformance.py`). See Pattern 2 + Don't-Hand-Roll. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Effective-dated policy applicability (legacy / repeal / physician window) | **Grounded rule registry** (`data/crs_rules/*.yaml` + `models/crs_rules.py`) | Deterministic date logic (`crs_audit.row_in_effect`/`_in_window`) | Every date lives in a grounded `machine_check`/`volatility` field; the predicate is pure math reading those windows — no date literal in code. |
| Fail-closed award decision (never green) | **`crs_audit.arranged_employment_guard`** (FROZEN) | — | The guard is the single chokepoint for the CRS additional-points award; it is byte-for-byte frozen and returns `AT-RISK` only. |
| Verdict/reason selection (legacy vs current vs physician) | **`auditors/additional.decide_job_offer`** (MODIFY) | The guard (delegated to) | The decider chooses the *reason code + citation*; it delegates the *award* to the frozen guard, extending routing without weakening the guard. |
| Program-eligibility offer signal (≠ CRS points) | **New inert sidecar module** | MEC integrator (Phase 45, downstream) | Structurally separates "valid offer for eligibility" from "CRS additional points"; capped `AT-RISK`, constant 0 points, not in the CRS envelope. |
| Physician-vs-general discrimination | **Grounded physician-NOC set** + confirmed `noc_code` (extraction/vault quarantine) | Decider match | Deterministic exact NOC match against a grounded set — no semantic inference / NLI (prohibited trust path). |
| Remediation / packet surfacing of the new reason | **`remediation.py` / `review_packet.py`** (MODIFY, small) | — | Reason codes are free-form strings projected into the PII-light two-tier surfaces; a new code is a template addition only. |

## Standard Stack

This is a data + deciders phase over an already-shipped stack. **No external packages are added.** "Stack" here means the internal, tested modules the plan builds on.

### Core (shipped modules the phase depends on — reuse verbatim)
| Module / Symbol | Role | Why Standard (do not reinvent) |
|-----------------|------|--------------------------------|
| `crawler/crs_audit.py::arranged_employment_guard` | Fail-closed CRS job-offer award guard | **FROZEN.** Single chokepoint; already reads repeal/legacy dates from grounded metadata; returns `AT-RISK` only. `[VERIFIED: crawler/crs_audit.py:397]` |
| `crawler/crs_audit.py::row_in_effect` / `_in_window` | Effective-window predicate over `machine_check` + `volatility` windows | **Shipped by Phase 40 (additive).** Consume it for the physician window — no new date math. `[VERIFIED: crawler/crs_audit.py:367,377]` |
| `crawler/auditors/additional.py::decide_job_offer` | Job-offer factor decider (delegates to guard) | The **MODIFY** seam for the physician branch; registered as `additional.job_offer`. `[VERIFIED: crawler/auditors/additional.py:36]` |
| `crawler/models/crs_rules.py` (`RuleRow`/`MachineCheck`/`VolatilityMeta`) | Typed, fail-closed registry boundary; `MachineCheck.effective_from/to`, `policy_flag`, `accepted_enum`, `CheckType: policy` | The physician row is a NEW `RuleRow` over the EXISTING model — no model change. `[VERIFIED: crawler/models/crs_rules.py:45,59,139]` |
| `crawler/crs_rules.py` (`load_registry`, `validate_registry`, `retrieve_what_you_cite`, `no_inlined_volatile_rules`, `REQUIRED_RULE_IDS`, `coverage_report`, `registry_fingerprint`) | Registry load + grounding + static gate + coverage | Add the physician `rule_id` to `REQUIRED_RULE_IDS["additional_points"]`; extend the static-gate surface (already covers `auditors/` + `*.yaml`). `[VERIFIED: crawler/crs_rules.py:57,168,231,458]` |
| `crawler/grounding.py::check_answer` | Verbatim quote-substring grounding gate (whitespace/case-normalized; NOT semantic) | Proves every physician citation quote is a real corpus substring. `[VERIFIED: crawler/grounding.py:88,185]` |
| `crawler/remediation.py::_ACTION_TEMPLATES` / `review_packet.py` | PII-light reason→action projection (free-form reason strings) | Add `physician_policy_manual` (+ optional sidecar reason) template. `[VERIFIED: crawler/remediation.py:68]` |
| `crawler/auditors/__init__.py` (`DecisionContext/Result`, `register`, `_default_decider`) | Decider dispatch spine; unregistered ⇒ `AT-RISK` | The sidecar is deliberately NOT registered here (inert). `[VERIFIED: crawler/auditors/__init__.py:48,93,103]` |

### Supporting (touch only if the recommended physician-signal design is chosen)
| Module / Symbol | Role | When to Use |
|-----------------|------|-------------|
| `crawler/extraction.py` (`_FIELD_SPECS`, `_DOC_TYPE_FACTOR`) | Document→factor field routing | Add a `job_offer` doc type routing `noc_code` (+ `issuer`, `employment_start`) to `additional.job_offer` so a confirmed physician NOC reaches `decide_job_offer`'s `by_field`. **Reuses existing `noc_code` FieldName — no vault schema migration.** `[VERIFIED: crawler/extraction.py:167,239]` |
| `crawler/models/vault.py::FieldName` | Closed extraction-field vocabulary | Only if you choose a dedicated human-confirmed physician flag field (heavier alternative). **Not recommended** — `noc_code` already exists. `[VERIFIED: crawler/models/vault.py:75]` |
| `crawler/vault.py::audit_eligible_values` | Per-factor confirmed-value gate (`factor_id`-scoped, quality-ok, non-stale) | Explains WHY `by_field` for `additional.job_offer` is empty today (see Pitfall 4). `[VERIFIED: crawler/vault.py:1099]` |

### Alternatives Considered (physician-signal trigger)
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| **[RECOMMENDED]** Confirmed `noc_code` ∈ grounded physician-NOC set (add a `job_offer` extraction doc type) | Claimed-side signal only (read a physician marker off the claimed factor, no extraction change) | Claimed-side is lighter (no extraction touch) and still fail-closed (AT-RISK only), but not evidence-confirmed and harder to test end-to-end. Acceptable *only* because the outcome is AT-RISK regardless. |
| Confirmed `noc_code` match | New dedicated human-confirmed `physician_public_policy` `FieldName` + confirm surface | Most explicit human confirmation, but adds a vault vocabulary migration + extraction + confirm-CLI wiring — heaviest footprint for an AT-RISK-only branch. |
| Grounded physician-NOC `accepted_enum` in the physician row | Inlining the NOC list in `decide_job_offer` | Inlining risks the `no_inlined_volatile_rules` gate and violates the grounding constraint — grounded row is mandatory. |

**Installation:** none.

```bash
# No packages installed this phase. Verify the zero-dep baseline is intact:
.venv/bin/python -m pytest crawler/tests/test_dli_conformance.py -q -k dependencies
```

**Version verification:** N/A — no external package is added or upgraded. Runtime deps remain the pinned `pyyaml>=6.0,<7.0`, `pydantic>=2.13,<3.0`, `platformdirs>=4.10,<5.0` (`pyproject.toml`, verified 2026-07-18).

## Package Legitimacy Audit

> No external packages are installed, upgraded, or introduced in Phase 42. The milestone standing constraint is **zero new dependencies**; the plan is pure first-party data + Python. `gsd-tools query package-legitimacy check` is therefore N/A this phase.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — (none added) | — | — | — | — | — | No packages introduced |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
                          vault audit --all   (job-offer factor claimed)
                                    │
                                    ▼
          ┌──────────────────────────────────────────────────────────┐
          │  auditors/additional.decide_job_offer(ctx)   [MODIFY]      │
          │                                                            │
          │   claim_points = ctx.factor.claimed_points  (0 ⇒ N/A)      │
          │   confirmed    = _confirmed_snapshot(ctx.by_field)         │
          │                                                            │
          │   ┌── ita_date is None ─────────────► AT-RISK / 0          │
          │   │                                    "arranged_employment_current"
          │   │                                                        │
          │   ├── [NEW] physician signal? ─────────────────────────┐   │
          │   │   confirmed noc_code ∈ grounded physician-NOC set   │   │
          │   │   AND row_in_effect(physician_row, ita_date)        │   │
          │   │        │ yes                                        │   │
          │   │        ▼                                            │   │
          │   │   AT-RISK / points=None  "physician_policy_manual"  │   │
          │   │   cite additional.job_offer.physician               │   │
          │   │                                                     │   │
          │   └── else delegate ────────────────────────────────┐  │   │
          │                                                      ▼  ▼   │
          │              crs_audit.arranged_employment_guard(...)      │
          │                        [FROZEN — byte-for-byte]            │
          │   ┌── in-window legacy row grounded ─► AT-RISK / None      │
          │   │       cite additional.job_offer.legacy   (POLICY-01)   │
          │   └── else (post-repeal) ───────────► AT-RISK / 0          │
          │           cite additional.job_offer.current  (POLICY-01)   │
          └──────────────────────────────────────────────────────────┘
                                    │
                                    ▼   (verdict + reason + citation via spine)
                     PrivateFactorCard → remediation / review_packet
                                    ▲
                                    │  NEVER SUBSTANTIATED, NEVER non-zero/non-None award

  ── SEPARATE, INERT SURFACE (POLICY-03) ────────────────────────────────
     policy_offer.offer_for_program_eligibility(claim, ita_date, registry)  [NEW]
        → { offer_present, eligibility_status ∈ {AT-RISK, N/A}, crs_points = 0 (const),
            citation, for_program_eligibility_only: true }
        → consumed by Phase 45 MEC as an AT-RISK input; NOT registered as a CRS decider,
          NOT summed into PublicAuditEnvelope.  Structurally cannot green CRS points.
```

Grounded windows read by `row_in_effect`/the guard (all from `additional.yaml`, never code):
- `additional.job_offer.current` — `machine_check.effective_from: "2025-03-25"` (repeal).
- `additional.job_offer.legacy` — `volatility.effective_to: "2025-03-25"` (legacy window `(-∞, 2025-03-25)`).
- `additional.job_offer.physician` **[NEW]** — `effective_from: "2023-04-25"`, `effective_to: null` (until revoked).

### Recommended Project Structure (files touched)
```
crawler/
├── crs_audit.py                     # FREEZE — do NOT edit (guard + row_in_effect already shipped)
├── auditors/
│   └── additional.py                # MODIFY — decide_job_offer: add physician branch
├── data/crs_rules/
│   ├── additional.yaml              # MODIFY — add additional.job_offer.physician row
│   └── COVERAGE.md                  # MODIFY — regenerate after registry change
├── crs_rules.py                     # MODIFY — REQUIRED_RULE_IDS[additional_points] += physician
├── remediation.py                   # MODIFY — add "physician_policy_manual" (+ sidecar reason) template
├── policy_offer.py                  # CREATE — inert offer-for-program-eligibility sidecar (POLICY-03)
├── extraction.py                    # MODIFY (recommended) — add "job_offer" doc type → additional.job_offer
└── tests/
    ├── test_physician_policy.py                       # CREATE — physician + legacy + repeal + sidecar
    └── test_conformance_v5_policy_no_job_offer_green.py  # CREATE — POLICY negative-control (Phase 46 will glob it)
```

### Pattern 1: Grounded, effective-dated physician policy row (data-driven, no code literal)
**What:** A NEW `RuleRow` whose dated applicability and physician-NOC scope both come from grounded corpus spans; the decider reads the window via `row_in_effect` and matches the NOC via the grounded `accepted_enum`.
**When to use:** POLICY-02 (physician branch). The same discipline the frozen guard uses.
**Example (recommended `additional.yaml` row — grounding verified live this session):**
```yaml
# Source: corpus/guidance/job-offer.md (canada.ca Express Entry: Job offer) +
#         corpus/pr-pdi/...arranged-employment/awarding-points-...-may-4-2013.md (FSW PDI)
- rule_id: additional.job_offer.physician
  factor_group: additional_points
  factor_ids: [additional.job_offer]
  check_type: policy
  query: physician arranged employment offer of employment public policy
  selector:
    family: guidance
    marker: "If you\u2019re a physician with a job offer in Canada"   # NOTE: curly apostrophe U+2019
    deny_families:
      - guidance/express-entry-year-end-report
      - guidance/express-entry-midyear
  claim_text: >-
    A physician special-case arranged-employment claim under the temporary public
    policy for foreign national physicians (invited on or after April 25, 2023,
    providing publicly funded medical services) is a distinct, manual (AT-RISK)
    resolution path — it is never an automatic CRS additional-points award.
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
    effective_from: "2023-04-25"   # grounded via citation_index 0 (the April 25, 2023 quote)
    citation_index: 0
  volatility:
    volatility: volatile
    source_family: guidance
    crawl_date: "2026-06-11T01:09:06Z"
    effective_from: "2023-04-25"
```
- `retrieve_what_you_cite` re-selects `guidance/job-offer.md#002` as the FIRST hit (verified) so `agrees_with_citation = True`; `validate_registry` grounds BOTH citation quotes independently (both verified `PASS` against `corpus/index.db`).
- The physician policy has **no fixed end date** ("remains in effect until it is revoked by the Minister" — verified live), so `effective_to` is intentionally omitted (`null`). If IRCC later revokes it, add a grounded `effective_to` — do not inline.

### Pattern 2: Inert sidecar — separation of "offer for eligibility" from "CRS points" (POLICY-03)
**What:** A pure function on its own surface that exposes a claimed offer as an `AT-RISK` program-eligibility input with a **constant `crs_points = 0`** and no code path that can set it non-zero. Not a registered CRS decider; not summed into the envelope.
**When to use:** POLICY-03. Phase 45 (MEC) reads it as an `AT-RISK` human-confirmed input (FST offer-or-certificate, FSW funds exemption) — never as a green.
**Example:**
```python
# crawler/policy_offer.py  (NEW, inert until MEC consumes it)
def offer_for_program_eligibility(claim_points, ita_date, registry) -> dict:
    """Expose a claimed job offer as an AT-RISK program-eligibility input.

    STRUCTURALLY cannot award CRS points: crs_points is a CONSTANT 0 and no branch
    assigns it otherwise; the status is never 'SUBSTANTIATED'. This is a screening
    input for MEC (FST R87.2(3)(d) / FSW R76(1)(b)(ii)), separate from the frozen
    arranged_employment_guard CRS-additional-points path.
    """
    present = bool(claim_points)
    current = next((r for r in registry.rows
                    if r.rule_id == "additional.job_offer.current"), None)
    return {
        "offer_present": present,
        "eligibility_status": "AT-RISK" if present else "N/A",  # NEVER SUBSTANTIATED
        "crs_points": 0,                                        # constant — no award path
        "for_program_eligibility_only": True,
        "reason": "offer_for_eligibility_manual",
        "citation": current.citations[0].chunk_id if current else None,
    }
```

### Anti-Patterns to Avoid
- **Editing `crawler/crs_audit.py`** — it is FROZEN (asserted byte-for-byte by `test_dli_conformance.py::test_frozen_files_unchanged_vs_head`). `row_in_effect`/`_in_window` already exist; consume them, don't re-add.
- **"Finishing" the legacy branch** by awarding the MI's 200/50 points — recreates the exact false-green the guard exists to prevent.
- **Letting the sidecar or MEC promote an offer to a green** — the offer input is capped `AT-RISK`; the guard's `additional.job_offer` verdict is the only CRS-points path and it never greens.
- **Inlining any date or NOC/points literal in Python/prose** — the `no_inlined_volatile_rules` gate flags a `20\d\d-\d\d-\d\d` date or a `15|25|30|50|100|200|600` value in a CRS context unless it lives in an allow-listed grounded key (`effective_from`, `quote`, `value`, …).
- **Automated semantic physician detection (NLI / keyword scoring)** — prohibited trust path; use deterministic exact NOC match against the grounded set only.
- **Curly-vs-straight apostrophe drift** — the guidance chunk uses `U+2019` ("If you’re a physician…"); the selector `marker` and any quote must match the exact codepoint (grounding is whitespace/case-normalized only, NOT Unicode-folded).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Effective-window applicability | A new date-window comparator in the decider | `crs_audit.row_in_effect(row, ref)` / `_in_window` (Phase 40, shipped) | Already composes both grounded window sources with inclusive `[from, to)` semantics + fail-closed exception behavior. |
| The award decision for a job-offer claim | A physician award path or a second guard | `crs_audit.arranged_employment_guard` (FROZEN) delegated to | Single chokepoint; provably never greens. The physician branch overlays only a *reason + citation*. |
| Proving a quote is grounded | A bespoke substring check | `grounding.check_answer` via `validate_registry`/`row_to_answer` | The shipped gate is the trust boundary; a forked check is a second trust path (prohibited). |
| Detecting a physician case | An NLI/keyword classifier over the NOC title | Exact `noc_code ∈ grounded accepted_enum` match | Deterministic, grounded, human-confirmed — no model, no prohibited semantic path. |
| Reason→remediation text | Ad-hoc prose in the decider | A `_ACTION_TEMPLATES` entry keyed by the new reason code | Keeps volatile-rule gate clean and PII-light projection centralized. |

**Key insight:** In this codebase the "hard" parts (fail-closed award, effective-date math, grounding) are already shipped and *frozen*; hand-rolling any of them re-introduces exactly the false-green / ungrounded-claim risks the milestone exists to prevent. Phase 42 is deliberately additive: one grounded row, one reason branch, one inert sidecar.

## Runtime State Inventory

> Not a rename/refactor phase, but this system carries non-source state a grep won't surface. Recorded so the plan doesn't miss it.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `corpus/index.db` (git-ignored, operator-generated FTS5 index) is the grounding source for `validate_registry`/`retrieve_what_you_cite`. The physician quotes ground against the CURRENT index (verified). | None to migrate. Re-`index` only if the corpus markdown changes. Tests that need the real index SKIP cleanly when absent (mirrors `_REAL_DB.is_file()` precedent). |
| Derived registry artifact | `crawler/data/crs_rules/COVERAGE.md` is a GENERATED file pinned for staleness by `test_conformance_v40_retrieve_what_you_cite.py` (and listed in `test_dli_conformance.py::_FROZEN_CONTRACT_PATHS`). | **Regenerate** after adding the physician row + `REQUIRED_RULE_IDS` label, and COMMIT it, or the freshness assertion fails. |
| Registry fingerprint | `crs_rules.registry_fingerprint` stamps audit reports; `vault remediate` fails closed if the registry drifted between audit and remediation. | No action — additive row changes the fingerprint by design; re-run audits after the change (existing behavior). |
| Cross-phase frozen-file test | `test_dli_conformance.py::_FROZEN_CONTRACT_PATHS` includes `additional.yaml` + `COVERAGE.md`; it uses `git diff --quiet HEAD` (working-tree vs HEAD), so it stays green once Phase 42's edits are COMMITTED, but its INTENT ("additional.yaml frozen") is now stale. | **Update** `_FROZEN_CONTRACT_PATHS` to drop `additional.yaml` + `COVERAGE.md` (they are legitimate Phase-42 mutation targets); keep `crs_audit.py` frozen. See Pitfall 5. |
| Secrets / env / OS state | None — no env vars, secrets, OS registrations, or services touched by this phase. | None — verified by inspection (pure library + data change). |
| Installed/build artifacts | No package installs; `pyproject.toml` deps unchanged. | None. |

## Common Pitfalls

### Pitfall 1: Legacy / physician auto-green (the milestone's highest-stakes regression)
**What goes wrong:** A physician branch (or the sidecar/MEC) returns `SUBSTANTIATED` or non-zero/non-`None` points, re-creating the false-green the guard exists to prevent. Note the corpus text literally says the physician policy "allows you to earn points … toward your total Express Entry score in the CRS" — a tempting but WRONG basis to auto-award, because the 2025-03-25 repeal removed job-offer CRS points for *all* candidates and the interaction is a genuine legal edge case.
**Why it happens:** Over-reading the physician policy prose as an award instruction; treating the offer-for-eligibility signal as a CRS input.
**How to avoid:** Physician branch returns `AT-RISK "physician_policy_manual"` with `substantiated_points=None`; the sidecar's `crs_points` is a constant 0 with no assignment path; the guard stays frozen. Add a negative-control test asserting NO `additional.job_offer` path yields `SUBSTANTIATED`/non-zero/non-`None`.
**Warning signs:** any `substantiated_points` truthy on a job-offer card; the sidecar returning `eligibility_status == "SUBSTANTIATED"`; a `points_table`/`points:` payload on the physician row (use `accepted_enum`/`policy_flag`, never a points table).

### Pitfall 2: Ungrounded or drifted physician citation
**What goes wrong:** The physician quote isn't a verbatim corpus substring (curly apostrophe, a paraphrase, or a section-header-only date), so `validate_registry` / the SAFE grounding gate fails.
**Why it happens:** The "April 25, 2023" string appears in the PDI *section header* (`#020`'s `section`) but the grounding gate checks the chunk **text**; copying from a rendered page can swap `’` (U+2019) for `'`.
**How to avoid:** Ground the DATE from `guidance/job-offer.md#002` text ("…on or after April 25, 2023") and the NOC SET from PDI `#020` text (both verified `PASS` this session). Keep the marker's curly apostrophe.
**Warning signs:** `retrieve_what_you_cite[...]["grounds"] == False`; `validate_registry` violations list includes `additional.job_offer.physician`.

### Pitfall 3: Physician window mis-scoped against the legacy window
**What goes wrong:** A physician invited between 2023-04-25 and 2025-03-25 ALSO falls inside the legacy window (`< 2025-03-25`). If the branch order is wrong, the guard's legacy path fires first and the distinct physician reason/citation is lost.
**Why it happens:** The legacy window `(-∞, 2025-03-25)` overlaps the open physician window `[2023-04-25, ∞)`.
**How to avoid:** Check the physician signal + `row_in_effect(physician_row, ita_date)` **before** delegating to the guard (ARCHITECTURE Flow-2 order). Both outcomes are `AT-RISK`/manual, so precedence only affects the *reason/citation*, not safety — but POLICY-02 requires the DISTINCT physician citation.
**Warning signs:** a physician test case surfaces `arranged_employment_legacy_manual` instead of `physician_policy_manual`.

### Pitfall 4: `by_field` for `additional.job_offer` is empty today
**What goes wrong:** The decider reads `ctx.by_field["noc_code"]` for the physician signal, but no document type routes any field to `additional.job_offer`, so `by_field` is always `{}` and the physician branch never fires from confirmed evidence.
**Why it happens:** `audit_eligible_values(vault, factor_id)` is `factor_id`-scoped; `extraction._DOC_TYPE_FACTOR` has NO `job_offer` doc type (only language/eca/employment/nomination/passport/sibling). `noc_code` today routes to `core.work`.
**How to avoid:** Add a `job_offer` doc type to `_FIELD_SPECS` + `_DOC_TYPE_FACTOR["job_offer"] = "additional.job_offer"` (reuses `noc_code`, no vault migration). OR use the lighter claimed-side signal (still AT-RISK-safe). Decide explicitly in the plan.
**Warning signs:** physician end-to-end test passes only with a hand-constructed `by_field`; real `vault audit` never reaches the physician branch.

### Pitfall 5: COVERAGE.md staleness + the cross-phase frozen-file test
**What goes wrong:** After adding the physician row / `REQUIRED_RULE_IDS` label, `COVERAGE.md` goes stale (fails `test_conformance_v40_retrieve_what_you_cite.py`) and/or `test_dli_conformance.py::_FROZEN_CONTRACT_PATHS` flags an uncommitted `additional.yaml`/`COVERAGE.md`.
**Why it happens:** `COVERAGE.md` is generated; a Phase-41 test froze `additional.yaml` byte-for-byte.
**How to avoid:** Regenerate + commit `COVERAGE.md`; drop `additional.yaml` + `COVERAGE.md` from `_FROZEN_CONTRACT_PATHS` in `test_dli_conformance.py` (they are Phase-42 mutation targets). Keep `crs_audit.py` in the frozen list. The frozen test uses `git diff --quiet HEAD`, so committed edits pass — but update the intent to avoid a misleading green/red.
**Warning signs:** "COVERAGE.md is stale — regenerate…" assertion; "frozen contract changed vs HEAD: crawler/data/crs_rules/additional.yaml" on an uncommitted tree.

### Pitfall 6: Conflating the physician *public policy* with the physician *category-based round*
**What goes wrong:** Citing `mi-rounds/invitations-12.md` ("Physicians with Canadian Work Experience" category) or category-based-selection content for the physician arranged-employment case.
**Why it happens:** Both mention "physicians"; they are different mechanisms (category-based ITA vs the arranged-employment public policy).
**How to avoid:** POLICY-02 is specifically the **arranged-employment temporary public policy** (`guidance/job-offer.md` "If you're a physician…" + the FSW arranged-employment PDI). The category-based round is out of scope here.
**Warning signs:** the physician row cites `mi-rounds/*` or `category-based-selection.md`.

## Code Examples

Verified patterns from the shipped codebase / grounded corpus.

### The frozen guard contract the physician branch delegates to (do NOT change)
```python
# Source: crawler/crs_audit.py:397 (FROZEN)
def arranged_employment_guard(claim_points, ita_date, registry) -> dict:
    if not claim_points:
        return {"status": "N/A", "points": 0, "citation": None}
    current = _find_row(registry, "additional.job_offer.current")
    legacy  = _find_row(registry, "additional.job_offer.legacy")
    current_citation = current.citations[0].chunk_id if current else None
    if legacy is not None and not legacy.gap:
        if _in_window(ita_date, legacy.volatility.effective_from, legacy.volatility.effective_to):
            return {"status": "AT-RISK", "points": None, "citation": legacy.citations[0].chunk_id}
    return {"status": "AT-RISK", "points": 0, "citation": current_citation}
```

### Recommended `decide_job_offer` physician branch (MODIFY — additive, delegates unchanged)
```python
# Source: crawler/auditors/additional.py:36 (add the [NEW] block; keep the rest verbatim)
def decide_job_offer(ctx):
    claim_points = getattr(ctx.factor, "claimed_points", None) or 0
    confirmed = _confirmed_snapshot(ctx.by_field)
    if not claim_points:
        return DecisionResult("N/A", "no_job_offer_points",
                              claimed_value=claim_points, confirmed_value=confirmed)
    if ctx.ita_date is None:
        return DecisionResult("AT-RISK", "arranged_employment_current",
                              claimed_value=claim_points, confirmed_value=confirmed,
                              substantiated_points=0)

    # [NEW] Distinct physician public-policy branch — grounded, AT-RISK/manual only.
    phys = next((r for r in ctx.registry.rows
                 if r.rule_id == "additional.job_offer.physician"), None)
    noc_val = ctx.by_field.get("noc_code")
    if phys is not None and not phys.gap and noc_val is not None:
        noc = str(_effective_value(noc_val))
        phys_nocs = {av.value for av in (phys.machine_check.accepted_values or [])}
        try:
            in_effect = crs_audit.row_in_effect(phys, ctx.ita_date)
        except (TypeError, ValueError):
            in_effect = False
        if noc in phys_nocs and in_effect:
            return DecisionResult("AT-RISK", "physician_policy_manual",
                                  claimed_value=claim_points, confirmed_value=confirmed,
                                  substantiated_points=None)  # manual; never an award

    guard = crs_audit.arranged_employment_guard(claim_points, ctx.ita_date, ctx.registry)
    if guard["status"] == "N/A":
        return DecisionResult("N/A", "no_job_offer_points",
                              claimed_value=claim_points, confirmed_value=confirmed)
    reason = ("arranged_employment_legacy_manual" if guard["points"] is None
              else "arranged_employment_current")
    return DecisionResult("AT-RISK", reason, claimed_value=claim_points,
                          confirmed_value=confirmed, substantiated_points=guard["points"])
```
> The spine attaches the corpus citation id from the gated consumed subset; ensure the physician row's `factor_ids` include `additional.job_offer` so its citation is available to the card (it does, in Pattern 1).

### Verified authoritative facts (live + pinned corpus)
```
# 2025-03-25 repeal — grounded: corpus/guidance/job-offer.md#001; live-confirmed 2026-07-18
"We no longer give points for job offers"
"As of March 25, 2025, we're removing job offer points from the Comprehensive Ranking System
 for current and future candidates in the Express Entry pool"
    → classified under Major Group 00 (200 points); any other skilled occupation (50 points)
"What isn't changing … If having a valid job offer is part of your eligibility criteria …
 the Federal Skilled Trades Program / the Federal Skilled Worker Program"     ← POLICY-03 basis

# Physician temporary public policy — grounded: corpus/guidance/job-offer.md#002 +
#   corpus/pr-pdi/...arranged-employment/awarding-points-...may-4-2013.md#020-022; live-confirmed
"We introduced a temporary public policy for foreign national physicians who:
   were invited to apply for permanent residence through Express Entry on or after April 25, 2023,
   and submitted an application
   have a job offer to provide publicly funded medical services in Canada"
"This temporary public policy will come into effect on April 25, 2023 and remains in effect
 until it is revoked by the Minister"      ← no fixed end date ⇒ effective_to: null
# physician NOC scope (NOC 2021): 31100 (clinical & lab medicine), 31101 (surgery), 31102 (GP/family)

# Legacy MI (pre-repeal) — grounded: corpus/ministerial-instructions/amendment-2017-2.md#006
"200 points, if the offer is for employment in an occupation contained in Major Group 00"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Job offer awards CRS additional points (200 / 50) | **No CRS additional points for job offers**, current & future candidates | **2025-03-25** (IRCC) | The default job-offer verdict is `AT-RISK`/0; the legacy award path is history, admissible only as an in-window manual (`points is None`) case. |
| No physician-specific arranged-employment facilitation | **Temporary public policy** facilitating physician arranged employment (publicly funded medical services) | Effective **2023-04-25**, until revoked | Distinct grounded row + `physician_policy_manual` verdict; still `AT-RISK`/manual (never auto-award) given the repeal + edge-case interaction. |
| Effective-window checks inline in the guard only | `crs_audit.row_in_effect` additive predicate composing both window sources | Phase 40 (v5.0) | Phase 42 reuses it for the physician window — zero new date machinery. |

**Deprecated/outdated:**
- Awarding job-offer CRS points on any path — removed 2025-03-25; any such path is a P0 regression.
- Reading policy dates from prose/Python — forbidden by the `no_inlined_volatile_rules` gate; dates live in grounded `effective_from`/`effective_to`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Physician branch outputs `substantiated_points=None` (manual), mirroring the legacy branch, rather than 0. | decide_job_offer / Pattern 1 | Low — both `None` and `0` satisfy "never green/never non-zero"; choice affects only remediation phrasing. Planner may pick `0` for symmetry with the repeal path. |
| A2 | Physician signal = confirmed `noc_code` ∈ grounded physician-NOC set, requiring a new `job_offer` extraction doc type. | Standard Stack / Pitfall 4 | Medium — if extraction wiring is judged out of scope, the lighter claimed-side signal is used (still AT-RISK-safe). Resolved as a recommendation, not a lock. |
| A3 | The offer-for-MEC sidecar ships **inert** (not registered, not in the envelope) this phase; MEC wires it in Phase 45. | Pattern 2 / POLICY-03 | Low — matches the roadmap dependency (Phase 45 depends on Phase 42's offer input); shipping it live now would be premature. |
| A4 | `effective_to` for the physician row is `null` (policy "remains in effect until revoked by the Minister"). | Pattern 1 | Low — verified live 2026-07-18; if IRCC revokes, add a grounded `effective_to` (fail-closed regardless, since AT-RISK). |
| A5 | The plan updates `test_dli_conformance.py::_FROZEN_CONTRACT_PATHS` to drop `additional.yaml`+`COVERAGE.md`. | Runtime State Inventory / Pitfall 5 | Low — mechanically the git-diff-vs-HEAD test stays green once committed; the update only realigns intent. |

**Note:** all *policy facts* (dates, NOC scope, repeal scope) are `[VERIFIED]` (live + grounded), not assumed. The assumptions above are *implementation-design* choices the planner may finalize.

## Open Questions (RESOLVED)

1. **How does the physician branch distinguish a physician from a general offer without a semantic model?** — RESOLVED: deterministic exact `noc_code ∈ grounded physician-NOC accepted_enum` (NOC 31100/31101/31102), grounded from the FSW arranged-employment PDI `#020`. No NLI/keyword scoring.
2. **Where does the physician signal enter, given `by_field` for `additional.job_offer` is empty today?** — RESOLVED: add a `job_offer` doc type in `extraction._FIELD_SPECS`/`_DOC_TYPE_FACTOR` routing `noc_code` to `additional.job_offer` (reuses existing `noc_code` FieldName, no vault migration). Lighter claimed-side fallback documented.
3. **Does the physician policy award CRS points (the prose says it "allows you to earn points toward the CRS")?** — RESOLVED: NO auto-award. The 2025-03-25 repeal removed job-offer CRS points for all candidates; the interaction is a legal edge case → `AT-RISK "physician_policy_manual"`, manual resolution, distinct citation. Never `SUBSTANTIATED`.
4. **Does the physician policy have an end date?** — RESOLVED: No fixed end — "remains in effect until it is revoked by the Minister" (verified live). `effective_to: null`.
5. **Is `crs_audit.row_in_effect` available, or must the phase add window math?** — RESOLVED: shipped by Phase 40 (`crawler/crs_audit.py:377`); consume it. Do not edit the frozen file.
6. **Which grounding source for the physician row?** — RESOLVED: date from `guidance/job-offer.md#002`, NOC set from the FSW arranged-employment PDI `#020` (both `PASS` the live grounding gate this session; selector re-selects the correct chunk).
7. **Will the sidecar be consumed this phase?** — RESOLVED: No — inert; Phase 45 (MEC) consumes it as an `AT-RISK` input. Shipped + unit-tested for the "constant 0 / never SUBSTANTIATED" invariant.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (`.venv/bin/python`) | All code + tests | ✓ | 3.10.12 | — |
| pytest | Validation | ✓ | 9.0.3 | — |
| pydantic | Registry models | ✓ | 2.13.x (pinned `>=2.13,<3.0`) | — |
| pyyaml | Registry load | ✓ | pinned `>=6.0,<7.0` | — |
| platformdirs | Vault paths | ✓ | pinned `>=4.10,<5.0` | — |
| `corpus/index.db` (FTS5) | Live grounding of the physician row | ✓ (present; physician chunks resolve) | operator-generated | Structural-only tests SKIP when absent (`_REAL_DB.is_file()` precedent) — grounding re-verified opportunistically |
| Network (canada.ca) | One-time policy-fact cross-check only | ✓ (this session) | — | Not needed at audit time — facts are grounded in the pinned corpus (project's no-live-lookup model) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none blocking — the real corpus index is present and the physician spans ground; absent-index CI stays green via skip-guards.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 (unittest-style `TestCase` classes) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (marker: `conformance`) |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_physician_policy.py -q` |
| Full suite command | `.venv/bin/python -m pytest crawler/tests -q` |
| Registry/coverage gate | `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_retrieve_what_you_cite.py crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_dli_conformance.py -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| POLICY-01 | In-window legacy ⇒ `AT-RISK`/`points is None`; post-repeal ⇒ `AT-RISK`/0 (preserved) | unit | `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py -q -k "legacy or current"` | ✅ (regression guard) |
| POLICY-01 | Guard byte-for-byte frozen | conformance | `.venv/bin/python -m pytest crawler/tests/test_dli_conformance.py -q -k frozen` | ✅ (keep `crs_audit.py` frozen) |
| POLICY-02 | Physician case ⇒ `AT-RISK "physician_policy_manual"`, cites `additional.job_offer.physician`; distinct from repeal | unit | `.venv/bin/python -m pytest crawler/tests/test_physician_policy.py -q -k physician` | ❌ Wave 0 |
| POLICY-02 | Physician row grounds (both citations) + `retrieve_what_you_cite` agrees | conformance | `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_retrieve_what_you_cite.py -q` | ✅ (extend to assert physician row) |
| POLICY-02 | No inlined date/NOC literal in the new decider branch | conformance | `.venv/bin/python -m pytest crawler/tests/test_crs_no_inlined_rules.py -q` | ✅ (self-scan already covers `auditors/` + `*.yaml`) |
| POLICY-03 | Sidecar returns constant `crs_points == 0`, status ∈ {AT-RISK, N/A}, never SUBSTANTIATED, for ALL inputs | unit | `.venv/bin/python -m pytest crawler/tests/test_physician_policy.py -q -k sidecar` | ❌ Wave 0 |
| POLICY-03 | No `additional.job_offer` path yields SUBSTANTIATED / non-zero / non-`None` (negative control) | conformance | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_policy_no_job_offer_green.py -q` | ❌ Wave 0 |
| POLICY (data) | `coverage_report` stays `complete`; `COVERAGE.md` fresh after adding the physician label | conformance | `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_retrieve_what_you_cite.py -q` | ✅ (regenerate COVERAGE.md) |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_physician_policy.py crawler/tests/test_crs_no_inlined_rules.py -q`
- **Per wave merge:** `.venv/bin/python -m pytest crawler/tests -q`
- **Phase gate:** full `crawler/tests` suite green (incl. the v4.x conformance gate via `.venv/bin/python scripts/run_conformance.py`) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `crawler/tests/test_physician_policy.py` — physician branch (AT-RISK/manual, distinct reason+citation), legacy/repeal regression, sidecar invariant — covers POLICY-01/02/03.
- [ ] `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` — negative control: no `additional.job_offer` path SUBSTANTIATED/non-zero (Phase 46 will glob `test_conformance_v5*`).
- [ ] Extend `test_conformance_v40_retrieve_what_you_cite.py` assertions to include `additional.job_offer.physician` (agrees + grounds) and regenerate/commit `COVERAGE.md`.
- [ ] Update `test_dli_conformance.py::_FROZEN_CONTRACT_PATHS` (drop `additional.yaml` + `COVERAGE.md`; keep `crs_audit.py`).
- Framework install: none — pytest present.

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high`. This is a local, no-network-at-audit CLI with a hard PII perimeter; the dominant risk is **integrity (false-green)**, then **information disclosure (PII)**.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface (local CLI). |
| V3 Session Management | no | Stateless CLI. |
| V4 Access Control | no | Single local operator. |
| V5 Input Validation | **yes** | Pydantic v2 `extra="forbid"` boundary on every `RuleRow`/`MachineCheck`; closed `Literal` vocabularies; `chunk_id` shape-validated to `relpath#ordinal`; `noc_code` matched against a grounded closed set — malformed rows fail LOUD at load. |
| V6 Cryptography | no (n/a) | No secrets/crypto; `registry_fingerprint` is sha256 for drift detection only (integrity, not confidentiality). |
| V7 Errors & Logging | **yes** | Fail-closed verdicts; PII-free reason tokens (`physician_policy_manual`, `offer_for_eligibility_manual`); stdout PII-light; no absolute paths. |
| V8 Data Protection / Privacy | **yes** | PII stays vault-only; `ev_` evidence ids never mixed with corpus citation ids; the physician row + sidecar are PII-free by construction (public registry). |
| V14 Config & Supply Chain | **yes** | Zero new dependencies (pinned `{pyyaml, pydantic, platformdirs}`); no network at audit; the `no_inlined_volatile_rules` static gate is a build-time control. |

### Known Threat Patterns for {grounded fail-closed policy resolver}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Legacy/physician **auto-green** (award CRS points on a repealed/edge regime) | Tampering / Elevation of Privilege | Frozen guard as sole award chokepoint; physician branch + sidecar are `AT-RISK`/constant-0; negative-control conformance test. |
| **Ungrounded** or paraphrased policy citation | Tampering (integrity of claim) | `validate_registry`/`retrieve_what_you_cite` gate every non-gap row; verbatim quotes verified against `corpus/index.db`. |
| **Inlined** volatile date/NOC/points in code or prose | Tampering | `no_inlined_volatile_rules` static gate (covers `auditors/` + `*.yaml`); values live only in allow-listed grounded keys. |
| Registry **drift** between audit and remediation | Tampering | `registry_fingerprint` mismatch fails `vault remediate` closed. |
| **PII leak** via the new reason/sidecar surfaces | Information Disclosure | Reason codes are PII-free string tokens; sidecar returns only public/derived fields; publish-safe scan covers vault subtrees. |
| Physician **NOC spoof** (claiming a physician NOC to trigger a green) | Spoofing → but capped | Even a spoofed NOC only yields `AT-RISK`/manual — there is no green to reach; human resolves. |
| Semantic **auto-resolution creep** (adding NLI/keyword matching) | Elevation of Privilege (new trust path) | Deterministic exact NOC match only; no model/vector/keyword scoring (milestone constraint). |

## Sources

### Primary (HIGH confidence)
- **Shipped codebase — direct inspection (curated first-party):** `crawler/crs_audit.py` (`arranged_employment_guard`, `row_in_effect`, `_in_window`, `within_freshness`), `crawler/auditors/additional.py` (`decide_job_offer` + registration), `crawler/auditors/__init__.py` (`DecisionContext/Result`, `register`, `_default_decider`), `crawler/models/crs_rules.py` (`RuleRow`/`MachineCheck`/`VolatilityMeta`, `CheckType`/`MachineCheckKind`), `crawler/crs_rules.py` (`REQUIRED_RULE_IDS`, `load_registry`, `validate_registry`, `retrieve_what_you_cite`/`_select_chunk`, `no_inlined_volatile_rules`/`_ALLOW_KEYS`/`_VOLATILE_POINTS_RE`, `registry_fingerprint`, `coverage_report`, `row_to_answer`), `crawler/grounding.py` (`check_answer` normalization), `crawler/remediation.py` (`_ACTION_TEMPLATES`), `crawler/review_packet.py`, `crawler/extraction.py` (`_FIELD_SPECS`/`_DOC_TYPE_FACTOR`), `crawler/vault.py` (`audit_eligible_values`), `crawler/data/crs_rules/additional.yaml`.
- **Pinned authoritative corpus (project's no-live-lookup source):** `corpus/guidance/job-offer.md#001` (2025-03-25 repeal), `#002` (physician policy + April 25, 2023); `corpus/pr-pdi/economic-classes-federal-skilled-workers-arranged-employment-awarding-points-applications-received-on-after-may-4-2013.md#020-022` (physician NOC scope + facilitative requirements); `corpus/ministerial-instructions/amendment-2017-2.md#006` (legacy 200-pt Major Group 00). Grounding **executed live** this session against `corpus/index.db` (all `PASS`).
- **Live canada.ca cross-check (2026-07-18, one-time verification, not an audit-time dependency):**
  - `https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/job-offer.html` (date-modified 2026-06-22) — confirmed "As of March 25, 2025 … removing job offer points from the Comprehensive Ranking System for current and future candidates"; physician policy "invited … on or after April 25, 2023 … publicly funded medical services".
  - `https://www.canada.ca/en/immigration-refugees-citizenship/corporate/mandate/policies-operational-instructions-agreements/public-policies/physicians-4-2023.html` (date-modified 2023-05-02) — confirmed "come into effect on April 25, 2023 and remains in effect until it is revoked by the Minister".
- **Milestone research (v5.0):** `.planning/research/ARCHITECTURE.md` (Flow 2 physician/legacy resolver, CREATE/MODIFY/FREEZE map), `PITFALLS.md` (Pitfall 3 legacy/physician auto-green), `FEATURES.md`, `STACK.md`; `.planning/ROADMAP.md` Phase 42; `.planning/REQUIREMENTS.md` POLICY-01/02/03 + standing constraints.

### Secondary (MEDIUM confidence)
- Phase 40 `40-RESEARCH.md`/`40-VERIFICATION.md` (row_in_effect / within_freshness delivery) — corroborated by direct code inspection (elevates to HIGH for the specific symbols).

### Tertiary (LOW confidence)
- None relied upon. No web-search providers are enabled in `config.json`; all facts are grounded/live-verified rather than search-inferred.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every module/symbol inspected directly; baseline suite green (52 + 34 relevant tests passing 2026-07-18).
- Architecture / physician design: HIGH — grounding + selector re-selection executed live and passed; guard/`row_in_effect` contracts read from source.
- Policy facts (dates/NOC/scope): HIGH — grounded in pinned corpus AND cross-checked against live canada.ca pages.
- Pitfalls / cross-phase test impact: HIGH — the frozen-file test, `by_field` scoping, and COVERAGE.md staleness were each read from the actual test/source files.

**Research date:** 2026-07-18
**Valid until:** 2026-08-17 (code seams stable). Policy facts are durable: the 2025-03-25 repeal is a historical fact; the physician policy runs until revoked by the Minister — re-verify `effective_to` only if IRCC announces a revocation.
