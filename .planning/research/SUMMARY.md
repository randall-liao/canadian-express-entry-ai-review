# Project Research Summary

**Project:** PR Review Agents — Canadian PR application guide (post-ITA Express Entry auditor)
**Milestone:** v5.0 Grounded Eligibility & Policy Edge-Case Screening
**Domain:** local-first, PII-safe, corpus-grounded, fail-closed CLI over a shipped 851-test system — a *screening* milestone (MEC / POLICY / STUDY / NOC / SAFE) layered on v4.1
**Researched:** 2026-07-17
**Confidence:** HIGH (data + deciders over an already-shipped, tested stack whose rule model already carries the effective-date / policy-flag / volatility machinery; two MEDIUM new-surface design calls flagged for phase-time)

## Executive Summary

v5.0 extends the shipped auditor from CRS *substantiation* ("is your claimed score backed by your documents?") into deterministic, authoritative-source-grounded *screening* ("which Express Entry programs do you meet the minimum entry criteria for, and are the policy edge cases v4.x punted on now resolved?") — **without moving the wall.** Every arithmetic / threshold / date fact stays grounded and may green a result; every *semantic* fact (does this work match this NOC? is this a valid legacy offer? is this institution/credential eligible?) stays human-confirmed and can at most reach `AT-RISK`. Nothing predicts an outcome; the officer decides, the tool screens and cites. All four research files converge on one framing: this is a **data + deciders** milestone, not a new-machinery one — the "hard" primitives it appears to need (effective-date windows, policy flags, volatility metadata, a fail-closed default decider, a superseded-family suppressor, a drift fingerprint, a read-only preflight) **already ship and are tested**; v5.0 wires them into new screens over new grounded rows.

The unanimous, load-bearing conclusions across STACK / FEATURES / ARCHITECTURE / PITFALLS are: **(a) ZERO new runtime dependencies** — proven module-by-module against `pyproject.toml` (deps are exactly `pyyaml`, `pydantic`, `platformdirs`; everything else in the lock is transitive-only via optional `crawl`/`doc-extract`/`ocr` extras) and `poetry.lock`; the **DLI list is the ONE genuinely-new artifact and it is a pinned, content-hashed local snapshot, not a live lookup**. **(b) The dominant risk is a FALSE-GREEN from a stale / superseded / out-of-window rule**, best mitigated as a single cross-cutting SAFE conformance invariant — *"stale / superseded / out-of-window / unconfirmed never greens"* — proven once, centrally, over every screen rather than re-implemented per screen. **(c) MEC is a true sidecar** that composes into its OWN five-key envelope (`PublicMecSummary`) and never touches the frozen `PublicAuditEnvelope` or the CRS total. **(d) POLICY is mostly already shipped** (`arranged_employment_guard` is correct and fail-closed today); the new work is a grounded physician-public-policy row plus separating "valid offer for *program eligibility*" from "CRS *additional points*." **(e) NOC-duty review is definitionally human-confirmed / AT-RISK** — present cited duties, capture a binary confirmation, never auto-resolve semantically. **(f) There is a real shipped defect to fix:** `crawler/auditors/additional.py::decide_study` currently greens on `credential_level` alone with no DLI/credential gate — the exact study false-green this milestone exists to close.

The recommended build order flows from the dependencies the research uncovered: land the **freshness / effective-date foundation** (a small `within_freshness()` helper, an `index_health` snapshot-presence/staleness extension, and a promoted single `gate_subset()`) plus the **DLI snapshot long pole** early; run **POLICY (physician row)** and **NOC (worksheet)** in parallel; gate **STUDY** on the snapshot; land **MEC as the integrator**; and close with the **SAFE v5.0 conformance gate** that proves the composite holds the line. Phases begin at **Phase 40** (global numbering continues after Phase 39) at fine granularity, mapped one-to-(one-or-two) onto the five requirement prefixes.

## Key Findings

### Recommended Stack

**Add nothing to the runtime dependency graph.** Ship v5.0 on the exact three-dependency stack that shipped v4.0/v4.1. All five capabilities are grounded YAML data + deterministic Python deciders + one new corpus family (a pinned DLI snapshot) over primitives that already exist, are tested, and are inside the PII / publish-safe perimeter. The decisive finding is that the machinery v5.0 appears to "need" is already shipped and unused-or-underused: `MachineCheck.effective_from/effective_to/window_days`, `MachineCheckKind.policy_flag`, `CheckType: policy`, `VolatilityMeta`, `_in_window`, `within_validity`, `arranged_employment_guard`, `registry_fingerprint`, `retrieve_what_you_cite` + `deny_families`, `index_health.probe_index`, the fail-closed `_default_decider`, and the SAFE-01..08 gate. See `STACK.md`.

**Core technologies (all locked / unchanged):**
- **Python `>=3.10,<4.0`** — no capability needs a newer floor.
- **`pydantic` 2.13.4** — new MEC/DLI/policy rows are *more rows of the existing `RuleRow`/`MachineCheck`/`VolatilityMeta` models* (`extra="forbid"`, `Literal` enums, `relpath#ordinal` citation shape); no schema change.
- **`pyyaml` 6.0.3** — new grounded rules are plain YAML (`mec.yaml`, `study_dli.yaml`, extended `additional.yaml`) compiled into rows and re-validated through the shipped grounding gate.
- **SQLite / `sqlite3` FTS5 (stdlib)** — the new `corpus/dli/` family auto-indexes (no DDL); new confirmed vault fields are additive `PRAGMA user_version` rows (the shipped v1→v3 pattern).
- **`datetime` / `urllib.request` / `json` / `hashlib` / `re` (stdlib)** — every effective-date comparison, the *refresh-time* snapshot fetch, content-address/provenance hashing, and fail-closed field canonicalization are stdlib. No third-party date library, no HTTP client, no rules engine.
- **`argparse` (stdlib)** — new verbs (`corpus refresh-dli`, `vault screen-mec`, `vault noc-review`) extend the shipped subparser tree and emit the frozen five-key `--json` envelope.

**The one new build — the DLI/PGWP snapshot — is a solved pattern.** A tiny *refresh-time* generator (`dli_snapshot.py`, stdlib `urllib`+`json`+`hashlib`, network only at refresh) fetches the IRCC DLI JSON (`.../json/dli/dli-full-list.json`, ~432 KB, ~1,454 records, with `"DLI #"`, `PGWP` `Yes/No`, etc.), stamps `crawl_date` + a sha256, and emits per-institution `corpus/dli/*.md` docs. `searchindex.build_index` then auto-enumerates and grounds them with **zero indexer change** — the exact NOC-2021 CSV→markdown→FTS5 precedent. The audit path never touches the network; it queries the local snapshot like any other corpus family.

### Expected Features

Organized by the five downstream requirement categories (**MEC / POLICY / STUDY / NOC / SAFE**); the four-verdict grammar (`SUBSTANTIATED`/`GAP`/`AT-RISK`/`N/A`) is unchanged and given a per-criterion *screening* reading. See `FEATURES.md`.

**Must have (table stakes / P1):**
- **SAFE effective-date / freshness / staleness extensions** — the precondition, not a follow-on; without it every other feature risks a stale false-green.
- **POLICY: physician public-policy row + eligibility-vs-CRS separation** — small, grounded, cheap; the repeal guard already ships (promotes LATER-01).
- **NOC: present-and-confirm duty-match worksheet** — the human-confirmed input MEC's skilled-work criterion and CRS `core.work` depend on (promotes LATER-03).
- **MEC: three-program minimum-entry-criteria roll-up + FSW 67-point grid as a *screen*** — the headline capability (promotes LATER-04).

**Should have (competitive / P2, add once the snapshot+staleness machinery is proven):**
- **STUDY: DLI/PGWP pinned-snapshot gate** on the Canadian-study points — the long pole; carries the only genuinely-new corpus artifact (promotes LATER-02).
- **Settlement-funds / LICO grounded screen** — high value but needs a *second* volatile snapshot (LICO table) using the same snapshot+freshness machinery as DLI.
- **As-of provenance surfacing** (`source_family` + `crawl_date`/`effective_from`) on every screened verdict — makes staleness auditable.
- **Duty-match worksheet → review-packet projection** — reuses the shipped redacted-packet allow-list.

**Defer / out of scope (do NOT pull in):**
- **Live DLI/PGWP/LICO web lookup during audit** — explicitly rejected (pinned snapshot only).
- **Any model / NLI / vector / cloud semantic auto-resolution** (VAL-02) — permanently out of scope for this trust model.
- **Program recommendation / "apply under X" / pre-ITA CRS optimization** — strategy/advice, out of scope.
- **LATER-06** (multi-recipient export presets), **LATER-07** (encrypted packet bundle) — deferred.

### Architecture Approach

v5.0 is a *subsequent* milestone: the architecture is a map of existing integration seams plus a disciplined plan of what to **extend vs. freeze**. The single hard invariant carried verbatim from v3.x/v4.x is **reuse the frozen `searchindex` → `grounding.check_answer` → typed JSON envelope trust path — never invent a second trust path, second index, second grounding engine, or a model/NLI/vector/cloud path.** Every v5.0 screen is either (a) more grounded rows + a decider on the SAME dispatch spine, or (b) a *projection* of already-gated verdicts. See `ARCHITECTURE.md`.

**Major components:**
1. **Frozen trust path** (`searchindex` → `--cite` → `grounding.check_answer` → five-key envelope) — **freeze;** the new `corpus/dli/` family is auto-indexed with zero indexer code.
2. **Grounded decision core** (`crs_rules.py` + `data/crs_rules/*.yaml` registry; `crs_audit.py` math/date logic; `auditors/` dispatch spine with `register`/`resolve`/`_default_decider`) — **extend data + deciders;** add `mec.yaml`, `study_dli.yaml`, an `additional.yaml` physician row, a `program_eligibility` `REQUIRED_RULE_IDS` group, and one small `within_freshness()` helper; freeze the guard byte-for-byte.
3. **MEC sidecar** (`mec_screen.py`) — runs *parallel* to the CRS grid over a disjoint `mec.fsw.*/mec.cec.*/mec.fst.*` namespace, reuses the ONE promoted `gate_subset()`, reads shared verdicts from prior audit cards, and rolls up per program (**MEETS** only if every criterion is `SUBSTANTIATED`/`N/A`) into its **own** `PublicMecSummary` envelope — the frozen `PublicAuditEnvelope` is never touched.
4. **DLI snapshot pipeline** (`dli_snapshot.py` refresh generator → `corpus/dli/*.md` → `build_index` → FTS5) — structurally separate from the audit path; network only at refresh.
5. **NOC duty worksheet** (`noc_review.py`) — present cited NOC-2021 lead statement / main duties / employment requirements, seed a `pending` `noc_*_match` confirmation through the SAME `is_audit_eligible` choke point; `decide_work` consumes the confirmed match, else `AT-RISK unresolved_noc`.
6. **Vault + publish-safe perimeter** — new confirmable fields are new `field_name` ROWS (no DDL) gated by `is_audit_eligible`; new artifacts under `output/mec-screen/`, `output/noc-review/` added to `VAULT_SUBTREES`; `PublicAuditEnvelope` frozen; a `user_version < 4` trail table is optional (derive-only is the default recommendation).

### Critical Pitfalls

1. **A stale / superseded rule silently greens a screen (the milestone's dominant risk).** The registry already models the windows; the failure is *omission* — a new decider that never calls `_in_window`. Avoid: make "no in-window grounded row ⇒ not green" the default, reuse `deny_families` for superseded families, and prove it centrally in SAFE with out-of-window / superseded / expired-snapshot negative controls. **[SAFE-owned]**
2. **Ungrounded MEC thresholds inlined as Python/prose literals** (67 pass mark, CLB minimums, 12/36-month windows, LICO). Avoid: every volatile number is a grounded `mec.yaml` row; **extend `no_inlined_volatile_rules`'s scanned path set to every new v5.0 decider module** (a brand-new module escapes the fixed scan path otherwise). **[MEC + SAFE]**
3. **Legacy / physician arranged-employment auto-green** — the single highest-stakes regression. Avoid: keep `arranged_employment_guard` the one chokepoint and *extend, never weaken* it (legacy ⇒ `AT-RISK`/`points is None`; repeal ⇒ `AT-RISK`/0; physician ⇒ `AT-RISK`/manual). MEC consumes an offer only as an `AT-RISK` human-confirmed input, never a green. **[POLICY + SAFE]**
4. **Live-lookup / fuzzy-name / institution≠program conflation for DLI/PGWP.** Fix the shipped `decide_study` credential-only green. Avoid: audit reads only `corpus/index.db`; match on the exact confirmed DLI number (never name); keep three distinct grounded checks (DLI-designation-*during-study*, R73(1) credential definition, credential-length tier). **[STUDY + SAFE]**
5. **NOC-duty semantic auto-resolution creep** (a model/NLI/embedding/keyword-overlap "match score"). Avoid: present cited duties, capture a binary human confirmation, default to `AT-RISK unresolved_noc`; no score, no threshold, no ML import. **[NOC]**
6. **MEC roll-up composition false-green** — a program reads `MEETS` while a criterion is `AT-RISK`/unknown because the composer branches on `!= GAP`. Avoid: `MEETS` requires *every* criterion `SUBSTANTIATED`/`N/A`; any `AT-RISK`/unknown/unwired ⇒ `NEEDS-REVIEW`; reserve `N/A` for genuinely inapplicable criteria only. **[MEC]**
7. **Dependency / trust-path creep** (a rules engine, a date library, a PDF/templating engine, a promoted transitive extra, a second DLI datastore, a re-grounding decider). Avoid: zero-new-dep discipline; new deciders consume gated rows only and never `import searchindex`/`grounding`; enforce with an AST-import scan and a `[project].dependencies`-unchanged assertion. **[SAFE]**
8. **Snapshot freshness / provenance missing or non-reproducible** — no `crawl_date`, no staleness bound, non-idempotent refresh. Avoid: stamp `crawl_date` + sha256; a grounded max-age bound forces `AT-RISK`/refusal when exceeded; `index_health` preflight refuses cleanly (zero artifacts) on missing/stale/corrupt snapshot. **[STUDY + SAFE]**

(Also: PII/privacy regression via new fields/sidecar surfaces/the snapshot generator; fail-open field vocabularies; and the drift-guard not covering new rows — all **[SAFE-owned]** with per-screen contributions. See `PITFALLS.md` for all 11 plus the "Looks Done But Isn't" checklist.)

## Implications for Roadmap

All four files agree on a dependency-aware sequence: **the freshness/effective-date foundation and the DLI snapshot land early; POLICY and NOC parallelize; STUDY gates on the snapshot; MEC integrates; SAFE conformance proves the composite last.** Critical path: SAFE-foundation → DLI-snapshot → STUDY-gate → MEC → SAFE-gate; POLICY and NOC parallelize with the snapshot, and NOC must precede MEC. Phases begin at **Phase 40** (fine granularity, mapped to the five requirement prefixes). SAFE is intentionally split: its *mechanisms* land first (Phase 40) as a foundation, and its *conformance gate* lands last (final phase) as the proof.

### Phase 40: SAFE foundation — freshness / effective-date mechanisms + shared gate
**Category:** SAFE (mechanisms, not the gate)
**Rationale:** Every downstream screen is date-sensitive; a screen shipped without staleness handling is a latent false-green. This must land *with or before* the rules it guards.
**Delivers:** `crs_audit.within_freshness()` (mirrors `within_validity`: no window / stale ⇒ not valid); `index_health.probe_index` extended with snapshot-presence/staleness classification (closed reason codes, clean refusal, zero artifacts); a promoted single `auditor.gate_subset()` helper so sidecars reuse the ONE gate; confirmation that `_in_window` / `deny_families` / `registry_fingerprint` reuse patterns are wired for the new families.
**Avoids:** Pitfalls 1, 8, 11 (the machinery half). **Uses:** shipped `within_validity`/`_in_window`/`index_health`/`registry_fingerprint`.

### Phase 41: DLI snapshot family + refresh generator (STUDY infra — the long pole)
**Category:** STUDY (infrastructure)
**Rationale:** The one genuinely-new corpus artifact; STUDY and CEC-MEC depend on it; pairs with Phase 40's freshness gate. Start early despite being P2 because it is the longest pole.
**Delivers:** `dli_snapshot.py` (stdlib fetch → `corpus/dli/*.md` with `crawl_date` + sha256); a `corpus refresh-dli` verb; a fixture snapshot for tests; proof that `build_index` auto-indexes the family and a `study_dli.yaml` row grounds verbatim.
**Avoids:** Pitfalls 4, 7, 8 (snapshot-not-live-lookup; one FTS5 index, no second datastore; provenance).
**Research flag:** verify the JSON schema *at refresh* and whether it carries historical designation windows (see Gaps).

### Phase 42: POLICY — physician public-policy row + eligibility-vs-CRS separation
**Category:** POLICY
**Rationale:** Independent of the snapshot; the `arranged_employment_guard` already ships and is correct — this is pure data + one AT-RISK branch. Parallelizes with Phase 41.
**Delivers:** a grounded `additional.job_offer.physician` row (citing `guidance/job-offer.md`, on/after 2023-04-25); a `decide_job_offer` `physician_policy_manual` AT-RISK branch; a remediation reason code; and the "valid offer for program eligibility ≠ CRS additional points" surface that feeds MEC (FST offer-or-cert, FSW funds exemption) as an `AT-RISK` input.
**Avoids:** Pitfall 3 (never auto-award; guard byte-for-byte frozen).

### Phase 43: NOC — present-and-confirm duty-match worksheet
**Category:** NOC
**Rationale:** Underpins MEC's skilled-work criterion and CRS `core.work`; build its confirmation surface before MEC's roll-up depends on it. Parallelizes with Phases 41–42; must precede MEC.
**Delivers:** `noc_review.py` (cited NOC-2021 lead statement / main duties (essential flagged) / employment requirements via the frozen `search`→`--cite` path); seeded `noc_lead_match`/`noc_main_duties_match` confirmable fields through the SAME choke point; `decide_work` consumes the confirmed match (else `AT-RISK unresolved_noc`); `output/noc-review/` subtree; `vault noc-review` verb; program-nuance linkage (FST applies employment requirements; FSW/CEC do not).
**Avoids:** Pitfall 5 (no ML/NLI/overlap score; human-confirmed only).

### Phase 44: STUDY — DLI/PGWP eligibility gate on `decide_study`
**Category:** STUDY (decider)
**Rationale:** Depends on Phase 40 (freshness) + Phase 41 (snapshot). Closes the shipped `decide_study` credential-only false-green.
**Delivers:** `proof_of_studies` extraction fields (`dli_number`, `institution_name`, `study_start`, `study_end`); `dlifields.py` fail-closed vocabulary (anti-drift pinned); `study_dli.yaml` grounded rows (`selector.family: dli`); `decide_study` gains a DLI-exact-match + `within_freshness` precondition (three distinct checks); fail-closed on no-match/ambiguous/stale.
**Avoids:** Pitfalls 4, 8, 10.
**Research flag:** the "DLI-during-program" temporal check + LICO scope (see Gaps).

### Phase 45: MEC — three-program eligibility sidecar + FSW 67-point grid screen
**Category:** MEC
**Rationale:** The integrator; composes shipped deciders (language/work/education) + NOC (43) + POLICY (42) + STUDY (44) + new grounded criterion rows. Sequences last among domain features.
**Delivers:** `mec.yaml` under a new `program_eligibility` `REQUIRED_RULE_IDS` group; `mec_screen.py` with a `MEC_PROGRAM_CRITERIA` manifest, criterion deciders, and a fail-closed roll-up (MEETS iff all `SUBSTANTIATED`/`N/A`); FSW 67-point grid *as a screen, not a score*; `mecfields.py` (province / TR status / trade-cert); inline two-tier models emitting `PublicMecSummary`; `output/mec-screen/` subtree; `vault screen-mec` verb. Optional within-milestone: settlement-funds/LICO screen (needs a second volatile snapshot — reuse the Phase 41 pattern).
**Avoids:** Pitfalls 2, 6, 9 (grounded thresholds; fail-closed roll-up; no envelope pollution — `PublicAuditEnvelope` frozen).
**Research flag:** MEC roll-up/envelope surface shape is a MEDIUM design call (see Gaps).

### Phase 46: SAFE — v5.0 conformance release gate (SAFE-09..)
**Category:** SAFE (the gate)
**Rationale:** The milestone's proof of correctness; must land last so it exercises every screen. Continues the SAFE-01..08 series.
**Delivers:** extend `run_conformance.py`'s glob to `test_conformance_v5*`; add SAFE-09.. proving a superseded MEC threshold / an out-of-window arranged-employment claim / a stale-or-absent DLI snapshot / an unconfirmed NOC duty / an unwired MEC criterion each **fail closed**; that the new snapshot grounds verbatim; that new rows can't re-green a completed run (`registry_fingerprint`); that `PublicAuditEnvelope` is unchanged; that `check_publish_safe` = 0 over the tree including `corpus/dli/`; and that `[project].dependencies` is unchanged (AST-import scan finds no second trust path).
**Avoids:** locks Pitfalls 1, 6, 7, 9, 11 and the privacy containment across all screens.

### Phase Ordering Rationale
- **Dependencies drive the order:** SAFE-foundation and the DLI snapshot are prerequisites (a dated rule without staleness handling is a latent false-green; STUDY/CEC-MEC need the snapshot). MEC is the integrator, so it must follow NOC, POLICY, and STUDY. The SAFE *gate* proves the composite, so it lands last.
- **Parallelism is explicit:** POLICY (42) and NOC (43) are independent of the snapshot and parallelize with Phase 41; only NOC has a hard "before MEC" ordering.
- **Fine granularity note:** the roadmapper may split further where scope warrants — e.g. MEC into (roll-up core) + (FSW 67-grid) + (optional LICO/settlement-funds), or STUDY into (snapshot infra, Phase 41) + (decider gate, Phase 44) as already suggested. Keep each phase mapped to a single requirement prefix so `COVERAGE.md` stays legible.
- **SAFE is deliberately bracketed:** mechanisms first (40), conformance last (46) — this is the "precondition, not a follow-on" finding from FEATURES/ARCHITECTURE made concrete.

### What NOT to add (explicit anti-stack — unanimous across all four files)
- **HTTP-at-audit-time client** (`httpx`/`requests`/`aiohttp`) in the audit path → breaks the frozen local-corpus trust path, non-reproducible, can green from unpinned data. Refresh a pinned snapshot out-of-band with stdlib `urllib`.
- **A rules engine / policy DSL** → forks a second trust path around the grounded registry + `no_inlined_volatile_rules`. Use grounded `RuleRow.machine_check` + stdlib `datetime`.
- **A third-party date library** (`dateutil`/`arrow`/`pendulum`) → stdlib `datetime` already does every window comparison.
- **A PDF renderer / templating engine** (`reportlab`/`weasyprint`/`jinja2`) → f-string / `"\n".join(...)` + `json` (the shipped `audit_report.py` pattern).
- **ML / NLI / embeddings / vector index / cloud semantic** for NOC-duty or ambiguous policy → fail-open, VAL-02 out of scope. Cited duties, human-confirmed, AT-RISK.
- **A second grounding path / second DLI datastore / second index** → the DLI snapshot is a normal `corpus/` family in the one FTS5 index; new deciders consume gated rows only.
- **`typer`/`click`** for new verbs → transitive-only via the `crawl` extra; extend the stdlib `argparse` tree.

### Standing constraints every phase must preserve
PII vault-only; stdout PII-light (verdict + counts + reason codes); authoritative sources only (IRCC / IRPA / IRPR / PDIs); no legal advice / no outcome prediction (`SCREENING_NOTICE` rendered into every new artifact); no automated IRCC submission; fail-closed everywhere (missing/stale/superseded/unconfirmed ⇒ refusal or `AT-RISK`, never a green); no new trust path; prefer zero new dependencies (any addition requires strong justification + a supply-chain gate).

### Watch Out For (top pitfalls with owning category)
| Pitfall | Owning category | The one-line guard |
|---------|-----------------|--------------------|
| Stale / superseded rule greens (dominant risk) | **SAFE** (+ MEC/POLICY/STUDY gate on dates) | "no in-window grounded row ⇒ not green" is the default; prove with superseded/out-of-window/expired negative controls |
| MEC thresholds inlined as literals | **MEC** (+ SAFE extends the static gate) | every number is a grounded row; extend `no_inlined_volatile_rules` scan path to new modules |
| Legacy/physician offer auto-green | **POLICY** (+ SAFE) | one chokepoint (`arranged_employment_guard`); extend, never weaken; never `SUBSTANTIATED`/non-zero points |
| DLI live-lookup / fuzzy-name / institution≠program | **STUDY** (+ SAFE freshness) | audit reads only `index.db`; exact DLI-number match; three distinct grounded checks |
| NOC semantic auto-resolution creep | **NOC** | present + confirm; no score/threshold/ML import; default `AT-RISK unresolved_noc` |
| MEC roll-up false-green | **MEC** | `MEETS` iff every criterion `SUBSTANTIATED`/`N/A`; any `AT-RISK`/unknown ⇒ `NEEDS-REVIEW` |
| Dependency / trust-path creep | **SAFE** (release/supply-chain gate) | `[project].dependencies` unchanged; AST-scan finds no second trust path |
| Snapshot freshness/provenance missing | **STUDY** (generator) + **SAFE** (bound + preflight) | `crawl_date` + sha256 stamped; stale ⇒ refusal, zero artifacts; refresh byte-reproducible |
| PII / snapshot / sidecar leak | **SAFE** + each screen | vault-only fields; generator reads only the IRCC dataset; `check_publish_safe` = 0 incl. `corpus/dli/` |
| Fail-open field vocabulary | **STUDY/NOC/MEC** | closed-enum alias maps, anti-drift pinned; unknown token never coerced; every value crosses `is_audit_eligible` |

### Research Flags

Phases likely needing deeper verification during planning (`/gsd-plan-phase --research-phase`):
- **Phase 41 (DLI snapshot):** the one MEDIUM data-source area — verify the IRCC JSON endpoint/schema *at refresh time* (treat as refreshable, not eternal) and whether it carries **historical** designation windows or only current status. This is a schema/verification check, not an ecosystem survey.
- **Phase 44 (STUDY gate):** confirm the "DLI-during-program" temporal handling (if the snapshot proves only current designation, the decider must stop at `AT-RISK`) and settle the LICO/settlement-funds snapshot scope if the funds screen is pulled in.
- **Phase 45 (MEC):** a *design* decision (not external research) — the exact MEC roll-up / envelope surface shape; resolve in the phase plan.

Phases with well-documented shipped patterns (skip research-phase):
- **Phase 40 (SAFE foundation):** mirrors `within_validity` / `index_health` / `registry_fingerprint` — established, tested.
- **Phase 42 (POLICY):** the guard already ships; pure data + one AT-RISK branch.
- **Phase 43 (NOC):** retrieval + present-and-confirm reuse the shipped `search`/`--cite`/confirm choke point.
- **Phase 46 (SAFE gate):** extends the SAFE-01..08 conformance harness.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | Zero-new-dep claim proven module-by-module against `pyproject.toml`/`poetry.lock`; every capability maps to an existing, tested module. Only the DLI JSON endpoint/schema is treated as *refreshable* (LOW for a generic web fetch, hence a pinned dated snapshot). |
| Features | **HIGH** | Every feature grounded in a real, verified corpus family (`pr-pdi`, `noc-2021`, `ministerial-instructions`, `legislation-irpr`, `guidance`) and shipped, tested mechanisms. MEDIUM only on two new-surface design points (MEC verdict-composition model; DLI snapshot schema/refresh cadence). |
| Architecture | **HIGH** | Grounded in direct inspection of the shipped v4.1 modules + sibling STACK/FEATURES; a map of existing seams. MEDIUM only on the MEC sidecar envelope shape and vault schema-v4-vs-derive-only. |
| Pitfalls | **HIGH** | Every pitfall tied to a real, inspected seam; the shipped `decide_study` credential-only defect confirmed by inspection. MEDIUM only on the DLI snapshot schema (the endpoint can drift — the reason it is pinned). |

**Overall confidence:** **HIGH**

### Gaps to Address (MEDIUM-confidence design surfaces — treat as phase-time decisions)
- **MEC roll-up / envelope surface shape** — own `PublicMecSummary` five-key envelope (recommended) vs. an additive `counts` breadcrumb on the audit envelope; and whether MEC criterion cards reuse `PrivateFactorCard` or stay fully separate (recommended: separate). Settle in the MEC phase plan; either way `PublicAuditEnvelope`'s field set stays frozen.
- **DLI "during-program" historical-designation window vs AT-RISK fallback** — the snapshot may carry only current designation. If it cannot prove designation *during* the study period, the decider must stop at `AT-RISK` (never assume current == historical). Verify the JSON schema at refresh (Phase 41) and enforce in the STUDY decider (Phase 44).
- **LICO / settlement-funds snapshot scope** — the FSW funds screen needs a *second* volatile snapshot (LICO table) using the same snapshot+freshness machinery as DLI. Decide whether it lands within v5.0 (P2) or defers; sequence it after the DLI pattern is proven.
- **Snapshot staleness bound as a grounded vs config value** — the max-age that forces `AT-RISK`/refusal must itself be authoritative (a grounded row) rather than an inlined constant, to stay inside the no-inlined-volatile discipline. Decide the mechanism in the SAFE foundation (Phase 40) / STUDY (Phase 44) plan.
- **Vault schema-v4 (trail table) vs derive-only** — recommend derive-only (write the artifact + reuse `extracted_values`); add an additive `mec_screens`/`noc_duty_worksheets` trail table only if a durable "applicant-controlled screen history" story earns its keep. Low-risk either way (additive migration). Decide per-phase (MEC/NOC).
- **`gate_subset` extraction / NOC-duty seeding mechanics** — confirm promoting `gate_subset()` causes no behavior change to `audit_one`, and that seeding a `pending` `noc_*_match` cleanly reuses `is_audit_eligible` + the five staleness keys for a human-judgment field (no document `render_sha256`).

## Sources

### Primary (HIGH confidence — curated first-party)
- **Shipped codebase, inspected directly:** `pyproject.toml` / `poetry.lock` (deps = exactly `pyyaml`/`pydantic`/`platformdirs`; all else transitive-only); `crawler/models/crs_rules.py` (`RuleRow`/`MachineCheck` with `policy_flag`+`effective_from/to`+`window_days`, `VolatilityMeta`, `CheckType: policy`); `crawler/crs_rules.py` (`load_registry`, `validate_registry`, `retrieve_what_you_cite`/`deny_families`, `registry_fingerprint`, `no_inlined_volatile_rules`, `REQUIRED_RULE_IDS`); `crawler/crs_audit.py` (`arranged_employment_guard`, `_in_window`, `within_validity`, `age_on_date`); `crawler/auditors/__init__.py` (`register`/`resolve`/`_default_decider`, `FULL_GRID_FACTORS`); `crawler/auditors/additional.py` (`decide_job_offer`, `decide_study` — greens on `credential_level` alone today); `crawler/auditors/core.py` (`decide_work` `unresolved_noc`); `crawler/searchindex.py` (`build_index` auto-enumeration); `crawler/vault.py` (`PRAGMA user_version` v1→v3 additive, `is_audit_eligible`); `crawler/index_health.py`; `crawler/siblingfields.py`/`testtypes.py`; `crawler/remediation.py`/`review_packet.py` (`SCREENING_NOTICE`, `unresolved_noc`); `scripts/check_publish_safe.py`; `scripts/run_conformance.py` (SAFE-01..08).
- **Curated authoritative corpus, inspected directly:** `corpus/pr-pdi/economic-classes-*` (FSW/FST/CEC MEC facts, 67 pass mark, settlement funds); `corpus/guidance/{job-offer,category-based-selection,crs-criteria,federal-skilled-workers,federal-skilled-trades,canadian-experience-class}.md`; `corpus/ministerial-instructions/{current,amendment-2017-2}.md`; `corpus/noc-2021/` (376 TEER 0–3 unit groups); `corpus/legislation-irpr` (R73(1), R75/R76, R87.1/R87.2); `corpus/definitions`. Confirmed **the DLI list is NOT in the corpus** — the one new family.
- **v5.0 sibling research:** `.planning/research/STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md`; `.planning/PROJECT.md` (v5.0 Current Milestone + Key Decisions).

### Secondary (MEDIUM confidence)
- **IRCC DLI JSON dataset** `https://www.canada.ca/content/dam/ircc/documents/json/dli/dli-full-list.json` — fetched + schema-verified live (~432 KB, ~1,454 records; fields `Province/Institution/"DLI #"/City/Campus/"Grad Program"/PGWP/HTML/"Public/Private"`). Treated as *refreshable* (endpoint/schema can drift) — hence pinned as a dated, content-hashed snapshot, not consumed live.

### Tertiary (prior milestone research reused, not repeated)
- `.planning/research/{STACK,FEATURES,ARCHITECTURE,PITFALLS,SUMMARY}-v4.1.md` and `-v4.0.md`; `.planning/milestones/v4.1-*`; `.planning/ROADMAP.md` (LATER-01..04 deferrals now promoted).

---
*Research completed: 2026-07-17*
*Ready for roadmap: yes*
