# Architecture Research — v5.0 Grounded Eligibility & Policy Edge-Case Screening

**Domain:** local-first, PII-safe post-ITA Express Entry auditor — a *screening* milestone (MEC / POLICY / STUDY / NOC / SAFE) layered on the shipped v4.1 codebase
**Researched:** 2026-07-17
**Confidence:** HIGH (grounded in direct inspection of the shipped v4.1 modules + the sibling v5.0 STACK.md / FEATURES.md; not an external ecosystem survey). MEDIUM only on two *new-surface shape* calls flagged inline: the MEC sidecar's exact envelope composition, and whether NOC/MEC warrant a vault schema-v4 trail table vs staying derive-only.

> **Scope note.** This is a *subsequent* milestone (v4.1 → v5.0), not a greenfield build. The "architecture" here is a map of **existing integration seams** plus a disciplined plan for **what to extend vs. freeze**. The single hard invariant, carried verbatim from v3.x/v4.x: **reuse the frozen `searchindex` → `grounding.check_answer` → typed JSON envelope trust path — never invent a second trust path, second index, second grounding engine, or a model/NLI/vector/cloud path.** Every v5.0 screen is either (a) more grounded rows + a decider on the SAME spine, or (b) a *projection* of already-gated verdicts. The one genuinely-new artifact is a pinned **DLI snapshot corpus family**, ingested by the existing "structured dataset → front-matter markdown → FTS5" pattern. Align with STACK.md (zero new runtime deps) and FEATURES.md (MEC as a sidecar; DLI snapshot as the one new corpus artifact; SAFE is a precondition, not a follow-on).

---

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  FROZEN TRUST PATH (v3.x + v4.x — REUSE VERBATIM, do NOT fork)                   │
│  ┌──────────┐   ┌──────────┐   ┌───────────────┐   ┌────────────────────┐       │
│  │ search   │──▶│  --cite  │──▶│ grounding gate│──▶│ 5-key JSON envelope │       │
│  │(FTS5 ro) │   │ resolve  │   │ check_answer  │   │ (PII-light)         │       │
│  └────┬─────┘   └────┬─────┘   └──────┬────────┘   └─────────┬──────────┘        │
│  searchindex.py  searchindex.py   grounding.py           contract.py             │
│      ▲ [v5.0: +corpus/dli/ family auto-indexed by build_index — NO indexer code] │
└──────┼──────────────┼─────────────────┼──────────────────────┼─────────────────┘
       │              │                  │                      │
       ▼              ▼                  ▼                      ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  GROUNDED DECISION CORE (v4.x — mostly frozen; v5.0 EXTENDS data + deciders)     │
│  ┌────────────────────┐   ┌──────────────────┐   ┌───────────────────────────┐  │
│  │ crs_rules.py       │   │ crs_audit.py     │   │ auditors/ (dispatch spine) │  │
│  │ + data/crs_rules/  │──▶│ deterministic    │──▶│ core·spouse·transfer·      │  │
│  │ *.yaml (registry)  │   │ math + date logic│   │ additional  (+register/    │  │
│  └─────────┬──────────┘   └────────┬─────────┘   │  resolve/_default_decider) │  │
│  [v5.0 ▲ +mec.yaml,      [v5.0 reuse _in_window, └───────────┬───────────────┘  │
│   +study_dli.yaml,        within_validity,       auditor.py (audit_one spine)    │
│   +additional.yaml        arranged_employment_    [v5.0 ▲ decide_study DLI gate, │
│   physician row]          guard — FROZEN]          decide_work NOC-confirm path] │
└──────────────────────────────────────────────────────────┬─────────────────────┘
                                                            │ PrivateAuditReport
        ┌───────────────────────────────────────────────────┴──────────────────┐
        ▼                                                                        ▼
┌─────────────────────────────────────────────┐   ┌────────────────────────────────┐
│  VAULT (PII-BEARING, git-ignored)            │   │  PUBLIC (PII-LIGHT stdout)       │
│  candidates/<id>/vault.sqlite (PRAGMA        │   │  PublicAuditEnvelope (FROZEN)    │
│    user_version; v5.0 new field_names,       │   │  ── v5.0 NEW peer envelopes ──   │
│    optional +v4 trail table)                 │   │  PublicMecSummary   [sidecar]    │
│  output/crs-audit/  · remediation/ · review- │   │  PublicNocSummary   [worksheet]  │
│    packet/                                    │   │  (each = its OWN 5-key envelope, │
│  ── v5.0 NEW vault artifacts ──              │──▶│   PublicAuditEnvelope untouched) │
│  output/mec-screen/ · noc-review/  [NEW]     │   └────────────────────────────────┘
└──────────────────────┬──────────────────────┘   ┌────────────────────────────────┐
                       │                           │ publish-safe perimeter (VAULT-04)│
                       └──────────────────────────▶│ check_publish_safe.VAULT_SUBTREES│
                                                   │ ── v5.0 ▲ +2 new subtrees ──     │
                                                   └────────────────────────────────┘

SIDECAR (runs PARALLEL to the CRS grid, reuses the SAME spine, own envelope):
   mec_screen.py ── register(mec.fsw.*/mec.cec.*/mec.fst.*) on the SHARED _REGISTRY
                 ── reads completed audit cards (shared criteria) + runs NEW MEC
                    criterion deciders (program-only gates) ── rolls up per program

REFRESH (out-of-band, network — NEVER during an audit):
   dli_snapshot.py (stdlib urllib+json+hashlib) ─▶ corpus/dli/*.md (crawl_date stamp)
                                                 ─▶ build_index ─▶ FTS5 (grounded)
```

### Component Responsibilities

| Component | Responsibility | v5.0 disposition |
|-----------|----------------|------------------|
| `crawler/searchindex.py` | FTS5 `search`/`resolve`; `build_index` auto-enumerates the live corpus (`dupaudit.live_docs` sorted `rglob`), mints `relpath#ordinal` chunk ids with per-chunk `crawl_date`/`source_type` | **Freeze.** The new `corpus/dli/` family is auto-indexed with **zero indexer change** |
| `crawler/grounding.py` | Frozen grounding-by-construction gate (`check_answer`) | **Freeze** (no fork) |
| `crawler/crs_rules.py` + `data/crs_rules/*.yaml` | PII-free corpus-cited rule registry; `load_registry` reads *every* `*.yaml`; `validate_registry` gate; `retrieve_what_you_cite`+`deny_families`; `registry_fingerprint`; `no_inlined_volatile_rules` | **Modify (data + manifest):** add `mec.yaml`, `study_dli.yaml`, an `additional.yaml` physician row; extend `REQUIRED_RULE_IDS` for the new MEC group; extend the static-gate scan surface to new deciders |
| `crawler/models/crs_rules.py` | `RuleRow`/`MachineCheck`/`VolatilityMeta` — ALREADY carry `check_type:policy`, `MachineCheckKind.policy_flag`, `effective_from/to`, `window_days`, volatility/`crawl_date` | **Freeze.** New screens are *more rows of this model* — no schema change |
| `crawler/crs_audit.py` | Deterministic math + date logic: `_in_window`, `within_validity`, `age_on_date`, `arranged_employment_guard` (already effective-date-driven, fail-closed, `points is None` legacy) | **Freeze** the guard byte-for-byte; **add** one small `within_freshness()` snapshot-staleness helper (mirrors `within_validity`) |
| `crawler/auditors/__init__.py` | Dispatch spine: `DecisionContext`/`DecisionResult`, `register`/`resolve`, `_default_decider` (fail-closed AT-RISK), `FULL_GRID_FACTORS`, `FACTOR_GROUP` | **Freeze the spine contract**; MEC/NOC deciders `register` on the SAME `_REGISTRY`; add a peer `MEC_PROGRAM_CRITERIA` manifest (disjoint id namespace) |
| `crawler/auditors/additional.py` | `decide_job_offer` (guard delegate), `decide_study` | **Modify:** `decide_study` gains a DLI/PGWP grounded precondition (freshness-gated); `decide_job_offer` gains the physician-policy AT-RISK reason branch |
| `crawler/auditors/core.py` | `decide_work` (`unresolved_noc` AT-RISK stub), language/education deciders | **Modify (small):** `decide_work` consumes a confirmed NOC-duty match; unconfirmed → AT-RISK `unresolved_noc` (extend the existing branch) |
| `crawler/auditor.py` | `audit_one` spine + `run_full_audit`; `AuditGroundingError` (sole error) | **Freeze `audit_one`**; extract a shared `gate_subset(subset, db)` from `_gate_or_raise` so `mec_screen` reuses ONE gate (no second trust path) |
| `crawler/extraction.py` | `_FIELD_SPECS` + `_DOC_TYPE_FACTOR`; `noc` kind | **Modify:** add `proof_of_studies` doc-type (DLI/study fields), MEC input fields; NOC-duty *confirmation* fields are seeded (not regex-extracted) |
| `crawler/vault.py` | Vault schema (v3), additive `PRAGMA user_version` migrations, `extracted_values` (arbitrary `field_name`), `is_audit_eligible` choke point, `audit_eligible_values` | **Modify:** new confirmable `field_name`s need **no DDL** (rows, not columns); add a `user_version < 4` branch ONLY if a durable MEC/NOC screen trail table is wanted |
| `crawler/models/vault.py` | `FieldName` / `FactorGroup` Literals (anti-drift pins) | **Modify (data):** extend `FieldName` with DLI/study/MEC/NOC field names, set-pinned to the new vocabularies |
| `crawler/testtypes.py`, `crawler/siblingfields.py` | Fail-closed accepted-token vocabularies pinned by anti-drift tests | **Reference/mirror:** add `crawler/dlifields.py`, `crawler/mecfields.py` following the same pattern |
| `crawler/index_health.py` | Typed read-only preflight → clean refusal (closed reason-code vocab) | **Modify (small):** add a snapshot-presence/freshness classification so a missing/stale `corpus/dli/` family refuses cleanly, zero artifacts |
| `crawler/models/audit.py` | Two-tier PII boundary (`PublicAuditEnvelope` vs `PrivateFactorCard`); `to_public_envelope` | **Freeze `PublicAuditEnvelope`**; the MEC/NOC sidecars use their OWN inline two-tier models (the shipped remediation/packet convention) |
| `crawler/remediation.py` / `crawler/review_packet.py` | Pure projections of gated verdicts; `unresolved_noc` reason code; `SCREENING_NOTICE` | **Modify (small):** add reason codes (`mec_not_met`, `physician_policy_manual`, `dli_unresolved`, `noc_duty_unconfirmed`); MEC/NOC worksheets project into the packet allow-list |
| `crawler/cli.py` | `argparse` subparser tree; `vault` verbs; `_require_readable_index`; error→envelope mapping | **Modify:** new verbs `corpus refresh-dli`, `vault screen-mec`, `vault noc-review`; reuse the frozen five-key envelope |
| `scripts/check_publish_safe.py` | Publish-safe perimeter (`VAULT_SUBTREES`, `VAULT_ARTIFACT_EXTS`) | **Modify (data):** add `output/mec-screen/`, `output/noc-review/`; confirm `corpus/dli/` is PII-free public data |
| `scripts/run_conformance.py` + `tests/test_conformance_v4*` | SAFE-01..08 release gate (file glob `test_conformance_v4[01]_*.py`) | **Modify:** extend the glob to `test_conformance_v5*`; add SAFE-09.. proving stale/superseded never greens any new screen |
| **`crawler/dli_snapshot.py`** | Refresh-time generator: fetch IRCC DLI JSON → `corpus/dli/*.md` with `crawl_date`+`sha256` provenance | **NEW** (stdlib only; network at refresh, never at audit) |
| **`crawler/mec_screen.py`** | MEC sidecar: per-program per-criterion roll-up over the shared spine + new grounded rows; own two-tier models | **NEW** |
| **`crawler/noc_review.py`** | Present-and-confirm NOC duty worksheet (cited lead/duties/requirements); own two-tier models | **NEW** |
| **`crawler/dlifields.py` / `crawler/mecfields.py`** | Fail-closed accepted-token vocabularies (DLI number, program stream, province, TR status, trade cert) | **NEW** |

---

## Existing Integration Points (explicit anchors)

The exact seams v5.0 plugs into — named so plans reference them without re-discovery. Line numbers are indicative (shipped code inspected 2026-07-17).

1. **The grounding gate (the trust path).** `auditor._gate_or_raise(subset, db)` → `crs_rules.validate_registry` → `grounding.check_answer` → `searchindex.resolve/search`. Any consumed row that fails the gate, or any `gap:true` row, raises `AuditGroundingError` **before any evidence read or artifact write**. *Every v5.0 screen consumes rows through this ONE call. MEC's sidecar must reuse it (recommend promoting a `gate_subset()` helper) — never a parallel gate.*

2. **The dispatch spine (`register`/`resolve`/`_default_decider`).** `auditors/__init__.py` holds a module-global `_REGISTRY`; `resolve(factor_id)` returns the registered decider or the fail-closed `_default_decider` (AT-RISK `unaudited_factor`, "an unwired factor can NEVER be SUBSTANTIATED"). *MEC/NOC deciders `register` here under DISJOINT id namespaces (`mec.*`); the elevation-of-privilege guard already protects any unwired MEC criterion.*

3. **`REQUIRED_RULE_IDS` full-grid manifest + `coverage_report`.** `crs_rules.REQUIRED_RULE_IDS` enumerates required rule-id stems per `FactorGroup`; `coverage_report`/`COVERAGE.md` are drift-guarded. *A new MEC criterion set adds a NEW group key (e.g. `program_eligibility`) so MEC coverage is self-documenting without polluting the CRS grid; `FULL_GRID_FACTORS` stays unchanged.*

4. **`load_registry` auto-loads every `*.yaml`.** `crs_rules.load_registry` globs `data/crs_rules/*.yaml` (skips `_`-prefixed), validating each row into a `RuleRow`; duplicate `rule_id`s across files fail closed. *`mec.yaml` and `study_dli.yaml` are picked up with no loader change; `registry_fingerprint` extends automatically.*

5. **`build_index` corpus auto-enumeration.** `searchindex.build_index` walks `dupaudit.live_docs` (sorted `rglob`) and mints `relpath#ordinal` chunk ids carrying front-matter `crawl_date`/`source_type`. *A new `corpus/dli/*.md` family is indexed + grounded with ZERO indexer code — the exact NOC-2021 CSV→markdown→FTS5 precedent.*

6. **The effective-date guard (already shipped, fail-closed).** `crs_audit.arranged_employment_guard(claim_points, ita_date, registry)` reads the current repeal date and the legacy window from grounded metadata (`machine_check.effective_from`, `legacy.volatility.effective_from/to`), returns `AT-RISK`/0 by default and `AT-RISK`/`points is None` for an in-window legacy — **never** auto-awards. `_in_window(when, from, to)` does the inclusive `[from, to)` comparison. *POLICY reuses this verbatim; the physician case adds a NEW grounded row + a NEW AT-RISK reason, never a new award path.*

7. **The evidence quarantine choke point.** `vault.is_audit_eligible(value_id)` (confirmed/corrected + `quality_flag == ok` + not stale via the five staleness keys) gates `audit_eligible_values(factor_id)`, which `audit_one` reads into `DecisionContext.by_field`. *All new confirmed inputs (DLI number, program stream, province, TR status, NOC-duty match) pass this SAME gate; nothing green without an eligible confirmed value.*

8. **`extracted_values` stores arbitrary `field_name`.** New confirmable fields are new `field_name` ROWS, not new columns — no DDL (the sibling-field precedent). The `FieldName` Literal + a `dlifields.py`/`mecfields.py` vocabulary + an anti-drift set-equality pin keep producer↔consumer aligned. *NOC-duty confirmation is the one non-extraction case: a `pending` `noc_*_match` value is seeded from the worksheet, then confirm/reject flows through the SAME choke point.*

9. **Additive `PRAGMA user_version` migration.** `vault._migrate` runs v1→v2→v3 additively, keyed on `user_version`, seeding `vault_meta` and never touching existing rows. *A v5.0 `version < 4` branch (additive `mec_screens`/`noc_duty_worksheets` trail tables) is only needed IF a durable screen trail is wanted; new confirmable fields need no migration.*

10. **Two-tier PII models + `to_public_envelope`.** `models/audit.py` splits `PublicAuditEnvelope` (`extra="forbid"`, `citation_id` rejects `ev_`) from `PrivateFactorCard`. The shipped remediation/packet features carry their OWN inline two-tier models (`PrivateRemediationChecklist`+`PublicRemediationSummary`, `ReviewPacket`+`PublicPacketSummary`). *MEC/NOC follow this convention — new inline models, `PublicAuditEnvelope` frozen.*

11. **`index_health.probe_index` preflight → clean refusal.** Read-only, closed reason-code vocab (`index_missing`/`empty`/`unreadable`/`corrupt`/`drifted`), `cli._require_readable_index` maps to `invalid_input`/exit-2, zero artifacts. *Extend to classify a missing/stale DLI snapshot family; STUDY/MEC-CEC preflight on it.*

12. **The SAFE release gate.** `scripts/run_conformance.py` selects `test_conformance_v4[01]_*.py` by glob and runs SAFE-01..08. *v5.0 extends the glob to `v5` and adds SAFE-09.. (stale/superseded never greens across MEC/POLICY/STUDY/NOC).*

13. **CLI verb + envelope mapping.** `vault` sub-subparsers under `_add_vault_subparser` (`init`/`import`/`extract`/`confirm`/`audit`/`remediate`/`review-packet`), each emitting the frozen five-key `--json` envelope; human PII detail → stderr only. *New verbs `screen-mec`/`noc-review` slot in identically; `refresh-dli` goes on the top-level (`corpus`-side) tree.*

---

## New vs Modified Components

| # | Capability | Change | Kind | Files | Trust-path impact |
|---|-----------|--------|------|-------|-------------------|
| A | **MEC sidecar** (FSW/FST/CEC) | New program-eligibility screen parallel to the CRS grid | **NEW + MOD** | NEW `mec_screen.py`, `mecfields.py`, `data/crs_rules/mec.yaml`; MOD `crs_rules.REQUIRED_RULE_IDS` (new group), `models/vault.FieldName`, `extraction.py`, `cli.py`, `check_publish_safe.py` | none — same gate, own envelope, `_default_decider` fail-closed for unwired MEC criteria |
| B | **Physician arranged-employment** | New grounded physician-policy row + AT-RISK reason | **DATA + MOD (small)** | MOD `data/crs_rules/additional.yaml` (new `additional.job_offer.physician` row), `auditors/additional.decide_job_offer` (reason branch), `remediation.py` (reason code) | none — `arranged_employment_guard` FROZEN; physician case is AT-RISK/manual only |
| C | **DLI/PGWP snapshot** | New pinned corpus family + refresh generator | **NEW (artifact + generator)** | NEW `dli_snapshot.py`, `corpus/dli/*.md` (generated), `data/crs_rules/study_dli.yaml`, `dlifields.py`; MOD `cli.py` (`refresh-dli`), `index_health.py` (freshness) | none — refresh is out-of-band; audit reads only the local snapshot via the frozen gate |
| D | **DLI study gate** | Gate `additional.study` on DLI + freshness | **MOD** | MOD `auditors/additional.decide_study`, `extraction.py` (`proof_of_studies` fields), `models/vault.FieldName` | none — new grounded precondition on an existing factor; fail-closed on stale/missing |
| E | **NOC duty worksheet** | Present cited duties + capture human confirmation | **NEW + MOD** | NEW `noc_review.py`; MOD `auditors/core.decide_work` (consume confirmed match), `models/vault.FieldName`, `vault.py` (seed pending), `cli.py`, `check_publish_safe.py` | none — no NLI/model; AT-RISK until human confirms cited duties |
| F | **Effective-date / freshness helper** | `within_freshness()` snapshot staleness + `index_health` extension | **NEW (small) + MOD** | NEW `crs_audit.within_freshness`; MOD `index_health.py` | strengthens fail-closed; no new grounding |
| G | **Shared gate helper** | Promote `gate_subset()` so MEC reuses ONE gate | **MOD (refactor)** | MOD `auditor.py` (extract from `_gate_or_raise`), `mec_screen.py` imports it | none — literally the SAME gate call, deduped |
| H | **SAFE v5.0 conformance** | Extend the release gate to the new screens | **TEST** | MOD `scripts/run_conformance.py` (glob), NEW `tests/test_conformance_v5*_*.py` | proves the above hold the line |

---

## Recommended Project Structure

New/changed files, following the established `crawler/` flat-module + `crawler/data/` + inline-two-tier-model conventions:

```
crawler/
├── dli_snapshot.py           # NEW — stdlib refresh generator: IRCC DLI JSON → corpus/dli/*.md
├── mec_screen.py             # NEW — MEC sidecar orchestrator + inline two-tier models
├── noc_review.py             # NEW — present-and-confirm NOC duty worksheet + inline models
├── dlifields.py              # NEW — DLI-number / program-stream fail-closed vocabulary (anti-drift)
├── mecfields.py              # NEW — province / TR-status / trade-cert fail-closed vocabulary
├── crs_audit.py              # MOD — add within_freshness(); guard + _in_window FROZEN
├── auditor.py                # MOD — extract shared gate_subset() from _gate_or_raise (spine frozen)
├── crs_rules.py              # MOD — REQUIRED_RULE_IDS += program_eligibility group; static-gate paths
├── index_health.py           # MOD — snapshot-presence/freshness classification (closed reason codes)
├── extraction.py             # MOD — proof_of_studies doc-type + MEC input fields
├── vault.py                  # MOD — (optional) user_version<4 trail table; seed pending noc_*_match
├── cli.py                    # MOD — corpus refresh-dli / vault screen-mec / vault noc-review verbs
├── auditors/
│   ├── additional.py         # MOD — decide_study DLI+freshness gate; decide_job_offer physician branch
│   └── core.py               # MOD — decide_work consumes confirmed NOC-duty match
├── models/
│   ├── vault.py              # MOD — FieldName += dli/study/mec/noc field names (set-pinned)
│   ├── crs_rules.py          # FREEZE — policy/effective-date/volatility fields already present
│   └── audit.py              # FREEZE — PublicAuditEnvelope untouched
├── data/crs_rules/
│   ├── mec.yaml              # NEW — FSW/FST/CEC minimum-entry-criterion rows (over existing corpus)
│   ├── study_dli.yaml        # NEW — DLI/PGWP grounded rows (selector.family: dli)
│   ├── additional.yaml       # MOD — physician public-policy row (additional.job_offer.physician)
│   └── COVERAGE.md           # MOD — regenerated (adds the program_eligibility group)
└── tests/
    ├── test_mec_screen.py                    # NEW
    ├── test_noc_review.py                    # NEW
    ├── test_dli_snapshot_generator.py        # NEW
    ├── test_study_dli_gate.py                # NEW
    ├── test_physician_policy.py              # NEW
    ├── test_freshness_staleness.py           # NEW
    ├── test_dlifields_vocab.py               # NEW — anti-drift set-equality pin
    ├── test_mecfields_vocab.py               # NEW — anti-drift set-equality pin
    └── test_conformance_v5*_*.py             # NEW — SAFE-09.. (stale/superseded never greens)

corpus/
└── dli/                      # NEW FAMILY (git-ignored, public authoritative data) — generated snapshot
    └── o*.md                 # one front-matter doc per DLI number (source_type: dli, crawl_date stamp)

scripts/
├── check_publish_safe.py     # MOD — VAULT_SUBTREES += output/mec-screen/, output/noc-review/
└── run_conformance.py        # MOD — glob += test_conformance_v5*_*.py
```

### Structure Rationale

- **`mec_screen.py` / `noc_review.py` are peers of `remediation.py` / `review_packet.py`, not extensions of `audit_report.py`.** Each is a distinct output *projection/screen* with its own inline two-tier models and its own vault subtree — the shipped v4.1 convention (models live inline in the module, not in `crawler/models/`). This keeps the frozen audit writer + `PublicAuditEnvelope` untouched.
- **`dli_snapshot.py` is a refresh-time generator, structurally separate from the audit path.** It mirrors the NOC-CSV generator: pure `urllib.request`+`json`+`hashlib`, network only at refresh, emits front-matter markdown the FTS5 builder indexes. The audit path never imports it.
- **`dlifields.py` / `mecfields.py` mirror `siblingfields.py` / `testtypes.py`.** The one lesson from v4.0's BLOCKER-B drift class: any new extraction↔consumer vocabulary MUST be a shared, test-pinned constant — never two hand-copied string lists.
- **MEC's new rules live in `mec.yaml` under a NEW `REQUIRED_RULE_IDS` group**, so the drift-guarded `COVERAGE.md` documents program-eligibility coverage separately from the CRS grid — a MEC gap is visible, never a silent green.

---

## Architectural Patterns

### Pattern 1: Sidecar screen on the shared spine (MEC) — parallel to, never inside, the CRS grid

**What:** MEC is a program-eligibility SCREEN that runs *parallel* to CRS scoring. It reuses the SAME `register`/`resolve`/`_default_decider` spine and grounding gate, but over a DISJOINT factor-id namespace (`mec.fsw.*`, `mec.cec.*`, `mec.fst.*`) driven by a peer `MEC_PROGRAM_CRITERIA` manifest — NOT `FULL_GRID_FACTORS`. Shared criteria (language/work/education already substantiated) are read from the completed audit's cards; program-only criteria (intended province, TR status, cert-or-offer) run NEW MEC deciders over NEW grounded rows + NEW confirmed vault fields. A per-program roll-up composes per-criterion verdicts: **MEETS** only if every criterion is `SUBSTANTIATED`/`N/A`; any `GAP` → **DOES-NOT-MEET**; any `AT-RISK` → **NEEDS-REVIEW** (never auto-green).
**When:** The MEC capability. Do NOT fold MEC into `run_full_audit` — screening ≠ scoring; mixing them risks a MEC criterion leaking into the CRS total.
**Trade-off:** A separate orchestrator + envelope is slightly more surface, but keeps `PublicAuditEnvelope` frozen and the elevation-of-privilege guard (`_default_decider` AT-RISK) automatically protects any unwired MEC criterion.

**Example:**
```python
# mec_screen.py — reuse the spine + the ONE gate; own two-tier models.
MEC_PROGRAM_CRITERIA = {
    "fsw": ("mec.fsw.work", "mec.fsw.language", "mec.fsw.education", "mec.fsw.pass_mark"),
    "cec": ("mec.cec.work", "mec.cec.language", "mec.cec.tr_status", "mec.cec.province"),
    "fst": ("mec.fst.work", "mec.fst.language", "mec.fst.cert_or_offer"),
}
def screen_program(vault, db, registry, program, prior_cards):
    cards = []
    for cid in MEC_PROGRAM_CRITERIA[program]:
        subset = _consumed_rows(registry, cid)
        auditor.gate_subset(subset, db)              # the SAME frozen gate (promoted helper)
        ctx = DecisionContext(factor_id=cid, ...,    # shared criteria read prior_cards
                              prior_cards=prior_cards)
        result = auditors.resolve(cid)(ctx)          # NEW mec.* decider or _default_decider
        cards.append(PrivateMecCriterion.from_result(cid, result))
    verdict = _rollup(cards)                          # MEETS iff all SUBSTANTIATED/N/A
    return PrivateMecProgram(program=program, criteria=cards, verdict=verdict)
```

### Pattern 2: Envelope composition without breaking the frozen `PublicAuditEnvelope`

**What:** The MEC/NOC sidecars emit their OWN five-key `--json` envelope (`command: "vault"`, `result` = a NEW `PublicMecSummary` / `PublicNocSummary` PII-light model) and write a PII-bearing artifact ONLY under a NEW vault subtree (`output/mec-screen/`, `output/noc-review/`). The frozen `PublicAuditEnvelope` schema (`extra="forbid"`) is never touched. When MEC is run alongside a full audit, at most a PII-light breadcrumb is added to the audit envelope's OPEN `counts: dict[str, int]` (e.g. `counts["mec_programs_met"] = 2`) — a pure additive int key that keeps `extra="forbid"` intact and carries no PII.
**When:** Any new screen that must surface a result on stdout.
**Trade-off:** Two models per screen (as v4.1 already accepted for remediation/packet) — but the PII firewall becomes a *structural* load-time guarantee, not a runtime hope, and the audit contract stays byte-stable for existing agents.

### Pattern 3: Volatile external fact as a pinned snapshot corpus family (DLI/PGWP)

**What:** A volatile external fact (DLI list, PGWP flag) is ingested as a **pinned local snapshot corpus family** via a stdlib refresh generator, indexed by the existing FTS5 builder, and grounded by a `RuleRow` (`selector.family: dli`, `marker` = the DLI number, verbatim `quote` of the PGWP flag) — NEVER a live lookup. The generator stamps `crawl_date` (freshness key) + a `sha256` content hash (version/provenance). The audit path reads only `corpus/index.db`.
**When:** Capability #3, and any future volatile-fact family (e.g. a LICO table for settlement funds).
**Trade-off:** The snapshot ages between refreshes — mitigated by the freshness gate (Pattern 5). A live lookup would be "fresher" but breaks the frozen local-corpus trust path, reproducibility, offline PII-safety, and puts a network dep in the fail-closed path — rejected.

**Example:**
```python
# dli_snapshot.py — refresh-time ONLY (network here, never at audit).
def refresh(dst: Path) -> dict:
    payload = urllib.request.urlopen(DLI_JSON_URL, timeout=30).read()   # stdlib
    digest = hashlib.sha256(payload).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    for rec in json.loads(payload)["data"]:
        write_frontmatter_md(dst / f"{rec['DLI #'].lower()}.md", rec,
                             source_type="dli", crawl_date=stamp)       # verbatim quotes
    return {"records": ..., "sha256": digest, "crawl_date": stamp}
# then: corpus-crawler --json index   (build_index auto-includes corpus/dli/)
```

### Pattern 4: Effective-date applicability from grounded metadata (POLICY)

**What:** Every dated policy fact (arranged-employment repeal, physician public policy on/after 2023-04-25, a dated MEC criterion) lives in a grounded row's `machine_check.effective_from/effective_to` or `VolatilityMeta` — never a prose/Python literal (the `no_inlined_volatile_rules` gate enforces this). Applicability is decided by comparing the ITA/reference date via `crs_audit._in_window`. Out-of-window or superseded ⇒ NOT green.
**When:** POLICY (physician), any dated MEC criterion (e.g. CEC's TEER cutover date).
**Trade-off:** None material — this is the shipped `arranged_employment_guard` discipline; the physician row adds data + one AT-RISK reason, not new machinery.

### Pattern 5: Snapshot / rule freshness fail-closed (SAFE)

**What:** A screen consults the grounded snapshot chunk's `crawl_date` (indexed from front matter) against a grounded max-age window via a NEW `crs_audit.within_freshness()` (mirroring `within_validity`: no window or stale ⇒ `False` ⇒ no green). A missing/corrupt/absent snapshot family is caught by an extended `index_health.probe_index` preflight → clean `AuditGroundingError`/refusal, zero artifacts. Superseded amendments/snapshots are suppressed at selection via `selector.deny_families` in `retrieve_what_you_cite`.
**When:** Every dated/snapshot-backed screen (STUDY, MEC LICO if added, POLICY windows).
**Trade-off:** More refusals/AT-RISKs when data is stale — which is the point (a stale green is the milestone's dominant risk).

### Pattern 6: Present-and-confirm human-in-the-loop (NOC), never entailment

**What:** The NOC worksheet retrieves and presents the grounded NOC-2021 lead statement / main duties / employment requirements (via the frozen `search`→`--cite` path), and captures a per-duty human confirmation as a seeded `pending` vault field (`noc_lead_match`, `noc_main_duties_match`) that flows through the SAME `confirm`/`is_audit_eligible` choke point. `decide_work` consumes the confirmed match; unconfirmed/unresolved ⇒ `AT-RISK unresolved_noc` (extend the shipped branch). NO model/NLI/embedding/keyword-overlap score is ever computed.
**When:** NOC duty review, and any semantic judgment (ambiguous legacy/physician policy fit).
**Trade-off:** Requires an explicit human step to reach `SUBSTANTIATED` — deliberate; auto-entailment is fail-open and out of scope (VAL-02).

---

## Data Flow

### Flow 1 — MEC sidecar screen (parallel to the CRS grid)

```
vault screen-mec [--program fsw|cec|fst|all]   (after a completed vault audit --all)
   ↓ index_health preflight (incl. corpus/dli/ for CEC PGWP)  → refuse cleanly if unusable
   ↓ load completed PrivateAuditReport → prior_cards (shared language/work/education verdicts)
   ↓ for each program → for each criterion id (mec.<prog>.*):
   ↓    gate_subset(consumed rows, db)              # the ONE frozen gate
   ↓    resolve(mec.<prog>.<crit>) → NEW decider (or _default_decider AT-RISK)
   ↓      shared criterion  → read prior_cards[core.*] verdict
   ↓      program-only crit  → read confirmed vault field (province / tr_status / cert_or_offer)
   ↓ roll up: MEETS iff all SUBSTANTIATED/N/A; any GAP → DOES-NOT-MEET; any AT-RISK → NEEDS-REVIEW
   ↓ PRIVATE: write output/mec-screen/<run>.md  (PII-bearing, vault-only)
   ↓ PUBLIC:  PublicMecSummary (per-program verdict, counts, citation ids, vault-rel path) → --json
publish-safe: output/mec-screen/ in VAULT_SUBTREES ; PublicAuditEnvelope UNTOUCHED
```

### Flow 2 — Physician / legacy arranged-employment resolver (POLICY)

```
vault audit --all   (job-offer factor)
   ↓ decide_job_offer → crs_audit.arranged_employment_guard(claim, ita_date, registry)  [FROZEN]
   ├─ no claim                     → N/A
   ├─ in-window legacy row grounded → AT-RISK, points is None (manual)          [FROZEN]
   ├─ physician signal (NOC + offer + ITA on/after grounded physician effective_from)
   │     → AT-RISK "physician_policy_manual", cite additional.job_offer.physician  [NEW branch]
   └─ else (post-repeal)           → AT-RISK / 0, cite additional.job_offer.current [FROZEN]
   ↓ feeds MEC (FST offer-or-cert / FSW funds exemption) as an AT-RISK human-confirmed input
   ↓ NEVER feeds CRS additional job-offer points as a green
```

### Flow 3 — DLI/PGWP study evidence gate (STUDY)

```
(refresh, out-of-band) corpus refresh-dli → corpus/dli/*.md (crawl_date) → index → FTS5
--------------------------------------------------------------------------------------
vault import proof_of_studies → vault extract
   ↓ extraction _FIELD_SPECS["proof_of_studies"] = [dli_number, institution_name, study_start, study_end]
   ↓ dlifields canonicalizer (fail-closed: unknown DLI-number form → non-accepted)
   ↓ pending → vault confirm (per field) → audit_eligible_values("additional.study")
vault audit --all   (study factor)
   ↓ decide_study:
   ↓   credential-length tier (existing) → grounded 15/30
   ↓   NEW precondition: confirmed dli_number resolves in corpus/dli/ (exact match) AND
   ↓                     within_freshness(snapshot crawl_date, grounded max-age) is True
   ├─ tier ok + DLI match + fresh          → SUBSTANTIATED (grounded points)
   ├─ no DLI match / ambiguous / stale snap → AT-RISK (never green from unpinned/absent data)
   └─ missing evidence / below tier         → GAP
```

### Flow 4 — NOC duty-review worksheet (present-and-confirm)

```
vault noc-review --document <ev_...> --noc <code>
   ↓ search corpus/noc-2021/noc-<code>.md → --cite lead statement / main duties / employment reqs
   ↓ render worksheet (cited, essential duties flagged) → output/noc-review/<run>.md (vault-only)
   ↓ SEED pending vault fields: noc_lead_match, noc_main_duties_match (per doc/NOC)
vault confirm <value_id> confirm|reject          # the SAME choke point (human judgment)
vault audit --all   (core.work factor)
   ↓ decide_work: aggregate periods (TEER/hours from grounded rows)
   ├─ confirmed noc_*_match eligible        → SUBSTANTIATED (duties human-confirmed)
   └─ unconfirmed / missing TEER            → AT-RISK "unresolved_noc"   [extend shipped branch]
   ↓ same confirmation feeds MEC skilled-work criterion (program-nuanced)
```

### Flow 5 — Freshness / staleness / missing-snapshot refusal (SAFE)

```
vault screen-mec / audit (STUDY) / noc-review
   ↓ index_health.probe_index(db)  [extended: assert corpus/dli/ present + fresh for STUDY/CEC]
   ├─ index_missing/empty/corrupt/drifted     → refuse (invalid_input/exit-2), ZERO artifacts
   ├─ snapshot family absent / crawl_date stale → refuse OR AT-RISK (fail-closed, surfaced as-of date)
   └─ ok → proceed
   ↓ superseded rule/amendment/snapshot → suppressed by retrieve_what_you_cite deny_families
   ↓ out-of-window dated rule → _in_window False → not applicable → not green
   ↓ registry drift since a completed run → registry_fingerprint mismatch → projection fails closed
```

---

## Trust & Privacy Boundaries

| Boundary | Rule | Enforcement in v5.0 |
|----------|------|---------------------|
| **Single trust path** | Only `grounding.check_answer` decides grounded/ungrounded | Every new screen consumes rows through the SHARED `validate_registry`/`gate_subset`; MEC's sidecar reuses the ONE gate — no parallel grounding, no second index (grep-assert like v4.0's frozen-core check) |
| **Corpus authority vs candidate evidence** | `citation_id` (`relpath#ordinal`) ≠ `evidence_id` (`ev_`); candidate text never citable | New envelopes reuse the `models/audit.py` firewall; DLI facts are PUBLIC corpus data (`corpus/dli/`), applicant DLI-number/program values are PII (vault-only) |
| **PII containment** | Applicant values live ONLY under `candidates/<id>/…`; stdout + repo stay PII-light | New artifacts under `output/mec-screen/`, `output/noc-review/`; both added to `VAULT_SUBTREES`; new `--json` envelopes are `extra="forbid"` PII-light; `PublicAuditEnvelope` frozen |
| **No live lookup** | Volatile external facts come from a pinned local snapshot | `dli_snapshot.py` fetches at REFRESH only; the audit path reads `corpus/index.db`; a network import in the audit path is an anti-pattern |
| **Fail-closed everywhere** | Missing/stale/superseded prerequisite → refusal or AT-RISK, never a partial/guessed/stale green | `index_health` preflight + `within_freshness` + `_in_window` + `deny_families` + `_default_decider` AT-RISK; "compute-then-write" ordering (no partial artifact) |
| **No inlined volatile rules** | MEC thresholds, study points, LICO, policy dates never hard-coded | Extend the `no_inlined_volatile_rules` scan surface to `mec_screen.py`/`noc_review.py`/`auditors/*`; every number reads from a grounded row |
| **Screening, not legal advice / no prediction** | Output framed as eligibility SCREENING | MEC/NOC artifacts render `SCREENING_NOTICE`; "meets the minimum entry criteria as grounded" (screen), never "you are eligible / will be invited / apply under X" |
| **No model/NLI/vector/cloud** | Semantic judgments human-confirmed | NOC duty fit + ambiguous policy stay AT-RISK until a human confirms cited text; no entailment, no overlap score, no embeddings |

---

## Schema & Migration Considerations

- **Registry data (A, B, C, D):** No model change — `mec.yaml`, `study_dli.yaml`, and the physician row are new `RuleRow`s over the EXISTING `RuleRow`/`MachineCheck`/`VolatilityMeta` (which already carry `check_type:policy`, `policy_flag`, `effective_from/to`, `window_days`, volatility/`crawl_date`). Verify each new row's `quote` is a verbatim substring of its cited chunk (the gate proves it). Extend `REQUIRED_RULE_IDS` with a `program_eligibility` group and regenerate `COVERAGE.md`.
- **Vault confirmable fields (A, D, E):** **No DDL.** `extracted_values` stores arbitrary `field_name` rows; new fields (`dli_number`, `institution_name`, `study_start`, `study_end`, `intended_province`, `tr_status`, `trade_certificate`, `noc_lead_match`, `noc_main_duties_match`) are new `field_name` VALUES gated by the SAME `is_audit_eligible` choke point + five staleness keys. Extend the `FieldName` Literal + add `dlifields.py`/`mecfields.py` vocabularies, each set-pinned by an anti-drift test.
- **NOC-duty confirmation (the one non-extraction case):** Seed a `pending` `noc_*_match` value from the worksheet (not a regex extraction), then confirm/reject through the SAME choke point. This preserves AT-RISK-until-confirmed with zero new confirm machinery.
- **Optional vault schema v4 (A, E — trail table):** If a durable MEC/NOC screen trail is wanted (analogous to `audit_runs`/`factor_verdicts`), add a `user_version < 4` branch running additive DDL (`mec_screens`, `noc_duty_worksheets`) and bump `schema_version` meta to "4". Fresh DBs fall through v1→v2→v3→v4; existing rows untouched. **Default recommendation: stay derive-only** (write the artifact + reuse `extracted_values`), add the trail table only if the "applicant-controlled audit history" story is deemed valuable.
- **Contract:** No new `error.type` needed — reuse `invalid_input`/exit-2 for refusals (via `_require_readable_index`). `SCHEMA_VERSION` stays "1.0". New verbs emit the frozen five-key envelope.
- **Backward compatibility:** All migrations additive/idempotent; an old vault opened by v5.0 upgrades in place; new registry rows extend `registry_fingerprint`, so a completed-run projection fails closed on drift.

---

## Anti-Patterns

### Anti-Pattern 1: Folding MEC into `run_full_audit` / the CRS total
**What people do:** Add `mec.*` factors to `FULL_GRID_FACTORS` so one pass "does everything."
**Why it's wrong:** Screening ≠ scoring; a MEC criterion could leak into `substantiated_total`, and it pollutes the frozen `PublicAuditEnvelope`.
**Do this instead:** A separate `mec_screen.py` orchestrator over a disjoint `MEC_PROGRAM_CRITERIA` manifest + its own envelope; read shared verdicts from `prior_cards`/the completed report.

### Anti-Pattern 2: A live DLI/PGWP lookup at audit time
**What people do:** `httpx.get(dli_url)` inside `decide_study` "to be current."
**Why it's wrong:** Breaks the frozen local-corpus trust path, reproducibility, offline PII-safety; can green from unpinned data; puts a network dep in the fail-closed path.
**Do this instead:** Refresh a pinned `corpus/dli/` snapshot out-of-band (stdlib); the audit reads `corpus/index.db` and refuses/AT-RISKs if stale.

### Anti-Pattern 3: A second gate / re-grounding inside a new decider or the MEC sidecar
**What people do:** Have `mec_screen` or `noc_review` open the index / call a fresh grounding pass.
**Why it's wrong:** Forks the trust path; produces citations the gate never validated.
**Do this instead:** Reuse the ONE `gate_subset()`/`validate_registry` call; consume only pre-gated grounded rows + cited ids.

### Anti-Pattern 4: A model / NLI / keyword-overlap "match score" for NOC duties or policy fit
**What people do:** Compute a similarity score between the reference letter and the NOC duties.
**Why it's wrong:** Violates no-model/no-vector/no-cloud; fail-open; recreates the false-confidence risk v4.x excluded; VAL-02 is out of scope.
**Do this instead:** Present grounded duties (essential flagged); a human confirms; verdict stays AT-RISK until confirmed.

### Anti-Pattern 5: Inlining MEC thresholds / study points / LICO / policy dates as Python constants
**What people do:** "They rarely change" → a literal in the decider.
**Why it's wrong:** Breaks grounding + trips `no_inlined_volatile_rules`; a silent stale value can green a fail.
**Do this instead:** Every threshold is a grounded `RuleRow` with `volatility`; unresolvable → fail-closed.

### Anti-Pattern 6: Applying a superseded/out-of-window rule "best-effort" to avoid a GAP
**What people do:** Fall back to an old amendment when no current row grounds.
**Why it's wrong:** A superseded rule greening a result is the milestone's dominant risk.
**Do this instead:** `deny_families` suppression + `_in_window`/`within_freshness` fail-closed → GAP/AT-RISK, never a stale green.

### Anti-Pattern 7: Extending `PublicAuditEnvelope` with MEC/NOC keys
**What people do:** Add `mec_verdict`/`noc_worksheet` fields to the frozen envelope.
**Why it's wrong:** Breaks the byte-stable audit contract existing agents parse (`extra="forbid"`).
**Do this instead:** New peer envelopes (`PublicMecSummary`/`PublicNocSummary`); at most an additive int key in the OPEN `counts` dict.

---

## Integration Points (internal boundaries)

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `mec_screen.py` ↔ `auditor` spine | `auditors.resolve()` + promoted `auditor.gate_subset()` + `vault.audit_eligible_values` | Reuse the ONE gate + evidence quarantine; disjoint `mec.*` id namespace; `_default_decider` fail-closed |
| `mec_screen.py` ↔ completed `PrivateAuditReport` | Read `output/crs-audit/<run>.json` for shared criterion verdicts | Derive-from-verdicts (like remediation); fail closed on `registry_fingerprint` drift / missing run |
| `decide_study` ↔ `corpus/dli/` snapshot | `search(family="dli")` + `resolve` (frozen path) + `within_freshness` | Exact DLI-number match; stale/absent/ambiguous → AT-RISK |
| `decide_job_offer` ↔ `arranged_employment_guard` | Direct call (FROZEN) + new physician grounded row + reason branch | Guard byte-for-byte frozen; physician case AT-RISK/manual only |
| `decide_work` ↔ `noc_review` confirmation | `by_field["noc_*_match"]` via `is_audit_eligible` | Confirmed match required for SUBSTANTIATED; else AT-RISK `unresolved_noc` |
| `dli_snapshot.py` ↔ `build_index` | Writes `corpus/dli/*.md`; `build_index` auto-enumerates | Refresh-time only; NO indexer change; audit path never imports the generator |
| new confirmable fields ↔ `dlifields`/`mecfields` vocab | Set-equality anti-drift pin (test) | Mirror `siblingfields`/`testtypes`; unknown surface form never coerced to accepted |
| new artifacts ↔ `check_publish_safe.VAULT_SUBTREES` | Path-prefix allow-list | Add `output/mec-screen/`, `output/noc-review/`; conformance asserts coverage |
| new modules ↔ `no_inlined_volatile_rules` gate | Static self-scan | Extend the scanned path set to `mec_screen.py`/`noc_review.py`/new deciders |
| new outputs ↔ SAFE framing | Rendered `SCREENING_NOTICE` | MEC/NOC artifacts carry the not-legal-advice / no-prediction notice |
| new verbs ↔ CLI + freshness preflight | `vault screen-mec` / `vault noc-review` / `corpus refresh-dli`; `_require_readable_index` | PII-light `--json`; human detail → stderr; preflight refuses cleanly, zero artifacts |

### External Services

| Service | Integration | Notes |
|---------|-------------|-------|
| IRCC DLI JSON dataset | Fetched at REFRESH only (`dli_snapshot.py`, stdlib `urllib.request`) | Never touched at audit time; pinned, content-addressed (`sha256`), `crawl_date`-stamped snapshot; treat the endpoint/schema as *refreshable*, not eternal |
| (all other) | — | Local-only by constraint: no cloud OCR/LLM/vector/API; no network in the audit/screen path |

---

## Dependency-Aware Build Order

Ordered so the snapshot + freshness/effective-date foundation lands EARLY and the cross-cutting SAFE conformance gate lands LAST. Global phase numbering continues after Phase 39 (v5.0 begins at **Phase 40**). Two early tracks (freshness foundation + DLI snapshot) converge on the screens; MEC integrates them; SAFE proves the composite.

1. **Freshness / effective-date foundation (SAFE mechanisms, not the gate).** `crs_audit.within_freshness()` + extend `index_health.probe_index` for snapshot presence/staleness + confirm `_in_window`/`deny_families`/`registry_fingerprint` reuse patterns. *Lands first — every downstream screen depends on it; a screen shipped without staleness handling is a latent false-green.* Also promote the shared `auditor.gate_subset()` helper here.

2. **DLI snapshot family + generator (STUDY infra — the long pole).** `dli_snapshot.py` (stdlib fetch → `corpus/dli/*.md` with `crawl_date`+`sha256`) + `corpus refresh-dli` verb + a fixture snapshot for tests; verify `build_index` auto-indexes it and a `study_dli.yaml` row grounds verbatim. *Early because it is the one new corpus artifact and STUDY + CEC-MEC depend on it; pairs with #1's freshness gate.*

3. **POLICY physician row (small, cheap, low-risk).** Grounded `additional.job_offer.physician` row + `decide_job_offer` AT-RISK reason branch + a remediation reason code. *Independent of #1/#2; the guard already ships — pure data + one branch. Can proceed in parallel with #2.*

4. **NOC duty-review worksheet.** `noc_review.py` (present cited duties) + seeded `noc_*_match` confirmable fields + `FieldName`/vocab extension + `decide_work` consumes the confirmed match + `output/noc-review/` subtree + `vault noc-review` verb. *Underpins MEC's skilled-work criterion and CRS `core.work`; build its confirmation surface before MEC's roll-up depends on it.*

5. **STUDY decider (DLI/PGWP gate).** `dli_number`/study fields + `dlifields.py` + `study_dli.yaml` + `decide_study` DLI + freshness precondition + `proof_of_studies` extraction. *Depends on #1 (freshness) + #2 (snapshot).*

6. **MEC sidecar (the integrator).** `mec.yaml` (new `REQUIRED_RULE_IDS` group) + `mec_screen.py` + criterion deciders + roll-up + inline two-tier models + `mecfields.py` (province/TR-status/cert) + `vault screen-mec` verb + `output/mec-screen/` subtree. Composes shipped deciders (language/work/education) + NOC (#4) + POLICY (#3) + STUDY (#5) + new grounded criterion rows. *Sequences last among the domain features — it integrates everything else.*

7. **SAFE v5.0 conformance gate (last).** Extend `run_conformance.py` glob to `test_conformance_v5*`; add SAFE-09.. proving: a superseded MEC threshold / an out-of-window arranged-employment claim / a stale-or-absent DLI snapshot / an unconfirmed NOC duty / an unwired MEC criterion each **fail closed** (AT-RISK / GAP / refusal), never green; the new `corpus/dli/` snapshot grounds verbatim; new rows can't re-green a completed run; `PublicAuditEnvelope` unchanged; publish-safe covers the new subtrees. *The milestone's proof of correctness.*

**Critical path:** #1 (freshness foundation) → #2 (DLI snapshot) → #5 (STUDY gate) → #6 (MEC) → #7 (SAFE gate). #3 (POLICY) and #4 (NOC) parallelize with #2; #4 must precede #6.

---

## Cross-Cutting SAFE Invariant — "stale / superseded never greens"

How the shipped primitives compose into ONE screen-wide invariant all four screens honor (capability #5):

| Layer | Primitive (shipped / new) | Guarantee |
|-------|---------------------------|-----------|
| Grounding gate | `validate_registry` → `check_answer` (frozen) + `gate_subset` (promoted) | Every consumed row grounds verbatim, or `AuditGroundingError` refusal — no ungrounded/`gap:true` row ever decides |
| Retrieve-what-you-cite | `_select_chunk` + `selector.deny_families` (frozen) | A superseded amendment / historical / adjacent chunk cannot masquerade as the cited rule |
| Effective window | `machine_check.effective_from/to` + `VolatilityMeta` + `_in_window` (frozen) | An out-of-window dated rule (repeal, physician policy, dated MEC criterion) is not applicable → not green |
| Snapshot freshness | per-chunk `crawl_date` (indexed) + `within_freshness()` (NEW) | A snapshot older than its grounded max-age → AT-RISK / refusal, surfaced with the as-of date |
| Index / snapshot presence | `index_health.probe_index` (extended) + `_require_readable_index` | Missing / empty / corrupt / drifted / absent-snapshot → clean refusal, ZERO artifacts |
| Registry drift | `registry_fingerprint` (frozen) | A drifted/stale registry cannot re-green a completed run; projections (remediation/MEC/NOC) fail closed |
| Unwired factor | `_default_decider` AT-RISK (frozen) | Any unwired grid OR MEC criterion is AT-RISK, never SUBSTANTIATED (elevation-of-privilege guard) |
| No inlined volatile | `no_inlined_volatile_rules` (extended path set) | No stale literal escapes grounding into a decider/prose |
| Proof | `run_conformance.py` + `test_conformance_v5*` (NEW) | The composite is proven: each stale/superseded/out-of-window/unconfirmed path fail-closes |

The net invariant: **a value can reach `SUBSTANTIATED`/`MEETS` only when it is grounded verbatim, in-window, from a fresh non-superseded source, over a non-drifted registry, and (for semantic facts) human-confirmed** — every other path fail-closes to `GAP`/`AT-RISK`/refusal.

---

## Open Questions / Verification Flags

- **MEC envelope shape (MEDIUM).** Confirm the sidecar emits its OWN `PublicMecSummary` five-key envelope (recommended) vs. an additive `counts` breadcrumb on the audit envelope. Settle in the MEC plan; either way `PublicAuditEnvelope`'s field set stays frozen.
- **`FactorGroup` for MEC criteria.** MEC criterion cards use NEW inline models (not `PrivateFactorCard`), so they need no `FactorGroup` member; but if a plan chooses to reuse `PrivateFactorCard`, decide whether to add a `program_eligibility` `FactorGroup` Literal (additive) or keep MEC models fully separate (recommended: separate).
- **Vault schema v4 vs derive-only (A, E).** Recommend derive-only (artifact + reuse `extracted_values`); decide per-plan whether a durable `mec_screens`/`noc_duty_worksheets` trail table earns its keep. Low-risk either way (additive migration).
- **DLI "during-program" temporal designation.** The snapshot may carry only CURRENT designation, not historical windows. If it cannot prove designation *during* the study period, the decider must stop at AT-RISK (never assume current == historical). Verify the JSON schema at refresh; flag in the STUDY plan.
- **`gate_subset` extraction.** `_gate_or_raise` is currently private to `auditor.py`; promoting a `gate_subset(subset, db)` public helper (or having `mec_screen` call `crs_rules.validate_registry` directly) is the cleanest way to guarantee ONE gate. Confirm no behavior change to `audit_one`.
- **NOC-duty seeding mechanics.** Confirm seeding a `pending` `noc_*_match` value (vs. a new table) cleanly reuses `is_audit_eligible` + the five staleness keys; verify the staleness keys behave sensibly for a human-judgment field (no document `render_sha256`).
- **LICO / settlement-funds (P2, may defer within v5.0).** If the FSW settlement-funds screen lands, it needs a second volatile snapshot (LICO table) — same snapshot+freshness machinery as DLI. Sequence after the DLI pattern is proven.

## Sources

- **Shipped codebase inspected directly (HIGH — curated first-party):** `crawler/auditors/__init__.py` (`register`/`resolve`/`_default_decider`, `FULL_GRID_FACTORS`, `FACTOR_GROUP`, `DecisionContext/Result`), `crawler/auditor.py` (`audit_one`, `_gate_or_raise`, `run_full_audit`, `AuditGroundingError`), `crawler/crs_audit.py` (`arranged_employment_guard`, `_in_window`, `within_validity`, `age_on_date`), `crawler/crs_rules.py` (`load_registry` glob, `validate_registry`, `retrieve_what_you_cite`/`deny_families`, `registry_fingerprint`, `no_inlined_volatile_rules`, `REQUIRED_RULE_IDS`, `coverage_report`), `crawler/models/crs_rules.py` (`RuleRow`/`MachineCheck` with `policy_flag`+`effective_from/to`+`window_days`, `VolatilityMeta`, `CheckType:policy`, `_CHUNK_ID_PATTERN`, `citation_index` range guard), `crawler/models/audit.py` (`PublicAuditEnvelope` frozen, `PrivateFactorCard`, `to_public_envelope`, `counts` dict), `crawler/models/vault.py` (`FactorGroup`/`FieldName` Literals), `crawler/auditors/additional.py` (`decide_job_offer`/`decide_study`/`decide_sibling`), `crawler/auditors/core.py` (`decide_work` `unresolved_noc`), `crawler/vault.py` (`_migrate` v1→v3 additive, `extracted_values` arbitrary `field_name`, `is_audit_eligible`, `audit_eligible_values`), `crawler/extraction.py` (`_FIELD_SPECS`/`_DOC_TYPE_FACTOR`, `noc` kind), `crawler/siblingfields.py`/`testtypes.py` (fail-closed vocab + anti-drift pin), `crawler/searchindex.py` (`build_index` auto-enumeration, per-chunk `crawl_date`/`source_type`, `relpath#ordinal`), `crawler/index_health.py` (closed reason-code preflight), `crawler/contract.py` (five-key envelope), `crawler/remediation.py`/`review_packet.py` (inline two-tier models, `SCREENING_NOTICE`, `unresolved_noc`), `crawler/cli.py` (`_add_vault_subparser`, `_cmd_vault_audit`, `_require_readable_index`), `scripts/check_publish_safe.py` (`VAULT_SUBTREES`), `scripts/run_conformance.py` (SAFE glob), `crawler/data/crs_rules/additional.yaml` (`job_offer.current/.legacy`, `study`). Corpus: `corpus/` families incl. `pr-pdi`, `noc-2021`, `guidance/job-offer.md` (physician public policy, "on or after April 25, 2023"); confirmed **no `corpus/dli/`** (the one new family).
- **Sibling v5.0 research aligned with (HIGH):** `.planning/research/STACK.md` (zero-new-deps, DLI snapshot mechanics, module-by-module map), `.planning/research/FEATURES.md` (MEC/POLICY/STUDY/NOC/SAFE categories, verdict grammar, dependency notes, MVP + build sequencing).
- **Prior architecture reused, not repeated (HIGH):** `.planning/research/ARCHITECTURE-v4.1.md` (frozen trust path, derive-from-verdicts, two-tier PII, additive-migration, anti-drift vocab, render-then-scan, dependency-aware build order), `.planning/research/ARCHITECTURE-v4.0.md` (vault design, grounded rule registry as a cited table, auditor as deterministic join). `.planning/PROJECT.md` (v5.0 Key Decisions: pinned snapshot not live lookup; effective-date/freshness dominant risk; zero new deps).

---
*Architecture research for: v5.0 Grounded Eligibility & Policy Edge-Case Screening (integration map — NEW vs MODIFIED, data flow, vault migration touchpoints, dependency-aware build order; frozen trust path + `PublicAuditEnvelope` + vault PII boundary preserved).*
*Researched: 2026-07-17*
