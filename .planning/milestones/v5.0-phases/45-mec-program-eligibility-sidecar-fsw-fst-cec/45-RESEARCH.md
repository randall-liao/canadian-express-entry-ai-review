# Phase 45: MEC Program-Eligibility Sidecar (FSW/FST/CEC) — Revised Research

**Researched:** 2026-07-20
**Revised:** 2026-07-19T23:06:05-04:00
**Domain:** Grounded, fail-closed Express Entry minimum-entry-criteria screening
**Confidence:** HIGH for repository architecture; MEDIUM-HIGH for current official policy facts

## Summary

Phase 45 adds a separate vault-backed minimum-entry-criteria screen for Federal Skilled Worker (FSW), Federal Skilled Trades (FST), and Canadian Experience Class (CEC). It does not add a CRS factor, change a CRS card/total/cutoff, extend `PublicAuditEnvelope`, or create the Phase-46 release gate.

The command contract is exactly:

`vault screen-mec --program fsw|fst|cec`

One command-boundary `RegistrySnapshot` is loaded after configuration validation and before vault access. The same immutable object/fingerprint is injected into MEC, NOC, policy-offer, and study composition. “One gate” means the one shared `crawler.auditor.gate_subset` implementation over one immutable snapshot, not literally one invocation: an exact MEC subset and a candidate-specific study subset may each gate through that same function.

The canonical criterion statuses are exactly `PASS | FAIL | AT-RISK | N/A`. Program outcomes use this precedence:

1. Any confirmed deterministic `FAIL` → `DOES-NOT-MEET`, even if another criterion is `AT-RISK`.
2. Otherwise any `AT-RISK`, missing, unknown, malformed, or unwired criterion → `AT-RISK`.
3. Otherwise all exact manifest criteria `PASS` or manifest-valid `N/A` → `MEETS`.
4. Unknown statuses/criteria are treated as `AT-RISK`.

`N/A` is not a caller-selected escape hatch. It is legal only for a known criterion whose structural manifest declares a conditional applicability branch and whose grounded predicate proves the branch genuinely inapplicable.

No refreshable proof-of-funds amount snapshot exists. Therefore a stored household size or amount can never produce `PASS` or `FAIL`. Unless a grounded confirmed exemption deterministically makes the amount branch `N/A`, the criterion is `AT-RISK` with exact reason `funds_snapshot_unavailable`. No amount/LICO literal belongs in YAML, Python, tests, rendered prose, or public output.

## Architectural Responsibility Map

| Capability | Primary tier | Secondary tier | Required behavior |
|---|---|---|---|
| MEC rows/manifest | Public local registry | Corpus grounding | Typed/cited rows, exact coverage, no amount table |
| Rule effectivity/freshness | Shared domain helpers | CLI config boundary | `row_in_effect` plus one configured positive max age |
| Candidate facts | Private vault | `mecfields` adapter | Pending-first, per-field decisions, five-key freshness |
| Employment joins | `mecfields` adapter | Evaluators | Deterministic `employment_period_id`; no cross-job mixing |
| Program evaluation | `mec_screen` | Shipped sidecars | Exact manifest, side-effect-free, no CRS conclusions |
| Publication | `mec_publish` | CLI | Render/scan/stage/backup/replace/fsync/rollback |
| Public output | Strict Pydantic projection | Five-key envelope | PII-light summary only |

Responsibility-map checks:

- `crawler/mecfields.py`, not `crawler/vault.py`, owns the new candidate-scoped MEC evidence adapter. It delegates eligibility to the shipped `vault.is_audit_eligible`; no vault schema/store helper is required.
- `crawler/crs_audit.row_in_effect` is reused unchanged for effective windows.
- `crawler/snapshot_policy.py` owns the new operational MEC rule max-age resolver and shared row-age predicate.
- `crawler/study_review.py` already accepts optional `registry_snapshot`; Phase 45 adds read-only/no-report composition and forbids reload in injected mode.
- `crawler/noc_review.py` needs optional snapshot/fingerprint injection because its current candidate query calls `is_audit_eligible` without the command fingerprint.
- `crawler/policy_offer.py` already accepts a registry argument and needs no source change.
- `crawler/audit_report.py` is the correct durability analog; `study_review` deletes/replaces `latest.json` and is not the LKG-preserving MEC publication pattern.

## Phase Requirements

| ID | Required outcome | Research support |
|---|---|---|
| MEC-01 | Own FSW/FST/CEC summary with MEETS/DOES-NOT-MEET/AT-RISK and no CRS/public-audit mutation | Separate strict MEC models and exact CLI |
| MEC-02 | Complete FSW minima and selection grid from confirmed evidence | Exact manifest, grounded rows, period-safe intake, grid bounds |
| MEC-03 | Complete distinct FST and CEC criteria | Program-specific period filters and branch logic |
| MEC-04 | Every policy value grounded; stale/missing/manual cannot MEETS | Shared gate, effectivity/freshness, no-inline scanner |

## Official Criteria Baseline

Policy values below are deliberately not copied into this prose. Implementers must transcribe them into cited `machine_check` payloads from the pinned official corpus and verify them through retrieve-what-you-cite.

### FSW

The structural inventory is:

- primary occupation and eligible NOC/TEER;
- paid skilled work, recency, continuity, duration, hours, and NOC lead/main-duty review;
- current approved first-official-language evidence;
- Canadian education or foreign education plus applicable ECA evidence;
- selection factors for first/second language, education, work experience, age, arranged employment, and adaptability;
- selection-grid pass logic and caps;
- settlement-funds applicability/exemption/accessibility, but no amount sufficiency table;
- intended destination outside Quebec.

Official sources:

- IRCC Federal Skilled Worker program page.
- IRCC language-test guidance.
- IRCC FSW education and adaptability PDIs.
- Justice Laws IRPR sections governing FSW minimum and selection criteria.

### FST

The structural inventory is:

- eligible skilled-trade hierarchy with explicit inclusions and exclusions;
- same-NOC work;
- paid work;
- qualified-to-practise status for the location and period;
- student-work exclusion;
- recency, duration, hours, NOC lead/main duties, and employment requirements;
- language requirements by ability;
- qualifying offer OR trade certificate;
- settlement-funds applicability/exemption/accessibility, but no amount table;
- intended destination outside Quebec.

Official sources:

- IRCC Federal Skilled Trades program page.
- IRCC language-test guidance.
- Justice Laws IRPR FST provisions.

### CEC

The structural inventory is:

- eligible TEER;
- work physically in Canada with province/territory recorded;
- authorization and temporary-resident status during each period;
- paid work;
- recency, duration, and hours;
- student-work and self-employment exclusions;
- NOC lead/main-duty review;
- TEER-sensitive language requirements;
- physician exception kept manual/`AT-RISK`;
- intended destination outside Quebec.

Official sources:

- IRCC Canadian Experience Class program page.
- IRCC language-test guidance.
- Justice Laws IRPR CEC provisions.

## Exact Structural Criterion Manifest

The manifest contains IDs and applicability declarations only—no policy values.

| Program | Criterion IDs |
|---|---|
| FSW | `fsw.work.primary_noc`, `fsw.work.teer`, `fsw.work.paid`, `fsw.work.recency`, `fsw.work.continuity_duration_hours`, `fsw.work.noc_duties`, `fsw.language.first`, `fsw.education.minimum`, `fsw.grid.language`, `fsw.grid.education`, `fsw.grid.experience`, `fsw.grid.age`, `fsw.grid.arranged_employment`, `fsw.grid.adaptability`, `fsw.grid.pass_mark`, `fsw.funds.requirement`, `fsw.destination.outside_quebec` |
| FST | `fst.work.trade_noc`, `fst.work.same_noc`, `fst.work.paid`, `fst.work.qualified_to_practise`, `fst.work.student_exclusion`, `fst.work.recency_duration_hours`, `fst.work.noc_duties_requirements`, `fst.language.minimum`, `fst.offer_or_certificate`, `fst.funds.requirement`, `fst.destination.outside_quebec` |
| CEC | `cec.work.teer`, `cec.work.in_canada`, `cec.work.authorized_tr_status`, `cec.work.paid`, `cec.work.recency_duration_hours`, `cec.work.student_exclusion`, `cec.work.self_employment_exclusion`, `cec.work.noc_duties`, `cec.language.minimum`, `cec.destination.outside_quebec` |

Manifest-declared conditional branches include:

- FSW/FST funds amount branch when a grounded exemption deterministically applies.
- FST offer/certificate alternatives when one branch completely satisfies the parent OR.
- Any other criterion that official policy and its grounded row explicitly declare inapplicable.

CEC education/funds and FST education are absent, not fake `N/A` criteria.

## Status Algebra and Deterministic Failure

### Criterion status

- `PASS`: all required inputs are confirmed/current, all rows are grounded/in-effect/fresh, and the grounded predicate is satisfied.
- `FAIL`: confirmed facts deterministically violate the grounded criterion. If omitted evidence could change the result, the relevant scope must also be confirmed complete.
- `AT-RISK`: every unresolved state, including missing, pending, rejected, low-quality, ambiguous, five-key stale, superseded, stale rule, out-of-window rule, manual semantics, incomplete scope, unavailable snapshot, unknown status/criterion, or unwired row.
- `N/A`: manifest-declared and grounded deterministic inapplicability only.

### Program outcome

The canonical pure ordering is:

1. Normalize exact criterion set. Unknown/missing/unwired/invalid-N/A becomes `AT-RISK`.
2. If any criterion is confirmed deterministic `FAIL`, return `DOES-NOT-MEET`.
3. Else if any criterion is `AT-RISK`, return `AT-RISK`.
4. Else if all criteria are `PASS`/valid `N/A`, return `MEETS`.
5. Else return `AT-RISK`.

This ordering intentionally prevents a real deterministic failure from being hidden by an unrelated unresolved criterion.

### Public reasons

The public enum is closed and PII-light. It includes:

- criterion satisfied;
- confirmed deterministic failure categories;
- evidence missing/unconfirmed/incomplete;
- rule unavailable/stale/out-of-window;
- manual NOC/offer/study/physician categories;
- `funds_snapshot_unavailable`;
- unknown/unwired/invalid applicability categories;
- composition/publication refusal categories.

Private detail carries exact rows, evidence IDs, values, and traces.

## Rule Effectivity and Operational Freshness

Every selected MEC row, including durable legislation, must pass both:

1. `crawler.crs_audit.row_in_effect(row, reference_date)`.
2. A shared operational freshness predicate over `volatility.crawl_date`, the same required non-`None` reference date, and one positive max age.

The max-age resolver contract is:

- explicit `--rule-max-age-days`;
- otherwise `PR_MEC_RULE_MAX_AGE_DAYS`;
- positive integer only;
- no default;
- invalid explicit input never falls back;
- absence/invalidity refuses before registry load, index probe, vault open, evaluation, or write.

This max age is operator policy, not an authoritative claim about how often IRCC changes a rule. Sidecar snapshots retain their own freshness configuration: DLI still uses its own explicit/environment resolver and probe. A composed run passes both configured values separately when study is consumed.

Out-of-window, superseded, future-crawl, malformed-crawl, and stale rows produce unusable criterion inputs and therefore `AT-RISK`, not a green result.

## Complete Private Evidence Vocabulary

All new values are vault-only, born `pending`, and become usable only through the existing per-value confirm/correct/reject path plus quality and five-key staleness.

### Canonical document types

| Document type | Exact responsibility |
|---|---|
| `mec-profile` | Application/reference/ITA anchors, scope-completeness attestations, destination |
| `mec-employment-period` | One employment period and all period predicates |
| `mec-trade-certificate` | Trade certificate authority/jurisdiction/NOC/status/dates |
| `mec-valid-offer` | Offer structure/NOC/location/status facts; policy validity remains manual |
| `mec-funds` | Household size, amount/currency/as-of, accessibility, borrowed/equity facts; no comparison |
| `mec-province-status` | Province/territory intent, residence/status, authorization/status dates |

All six route only to inert `review.mec` in factor group `program_eligibility`, ignore factor overrides, and never enter `FULL_GRID_FACTORS`.

### Required field groups

- Anchors/completeness: application date, applicable reference/ITA date, complete work/education/offer-certificate/adaptability scopes.
- Employment period: deterministic `employment_period_id`, start/end, paid/unpaid, student status during period, self-employment, work country/province, authorization status, temporary-resident status, NOC, TEER, NOC date/version, hours, qualification-to-practise.
- Trade certificate: authority, province/territory/federal jurisdiction, linked NOC/trade, status, issue/expiry.
- Valid offer: full-time/continuous/non-seasonal/duration, NOC, work location, employer-count/LMIA/work-permit-basis facts.
- Funds: household size, amount, currency, as-of, accessibility, borrowed status, real-property equity.
- Province/territorial status: intended destination, current status, authorization/status windows.

### Deterministic employment-period join

One `mec-employment-period` document represents one period. A stable key is derived from stable content identity plus a fixed period slot. Every value from that document carries the same `employment_period_id`.

The adapter:

- groups only by this ID;
- requires internal key agreement;
- does not join by employer text, NOC, date, candidate, row order, or “closest” value;
- rejects missing/duplicate/conflicting/mismatched groups to `AT-RISK`;
- filters period predicates before aggregation.

### Manual reachability

Paid/student/self-employment/authorization/status/accessibility facts cannot always be extracted reliably from arbitrary prose. The supported path is an exact labeled private form:

1. `vault import ... --doc-type <canonical-type>`
2. `vault extract`
3. `vault fields`
4. one-value `vault confirm --decision confirm|correct|reject`

Strict label parsing creates pending values. The user reviews/corrects each value. No bulk confirmation, schema migration, parser-version change, semantic model, or inferred truth is introduced.

## One Snapshot and Sidecar Composition

### MEC gate context

`prepare_mec_gate(program, snapshot, db, reference_date, max_age_days)`:

- accepts a caller-supplied `RegistrySnapshot`;
- selects the exact manifest rows;
- calls `auditor.gate_subset`;
- applies effectivity/freshness to every selected row;
- returns a frozen context retaining snapshot object/fingerprint and per-row usability;
- never reloads YAML or recomputes a fingerprint.

### NOC

Current `review_noc_duties` delegates to `vault.is_audit_eligible` without a supplied fingerprint. Add optional `RegistrySnapshot`/fingerprint injection and pass it to every eligibility check. Its status remains manual/never-green.

### Study

Current `review_study` already accepts optional `registry_snapshot`, but invalidates/writes a study report. Add read-only/no-report mode for MEC:

- no report invalidation;
- no study report write;
- no reload when snapshot is injected;
- static rows from the injected snapshot;
- candidate-dynamic rows remain transient;
- dynamic subset uses the same `auditor.gate_subset`;
- same fingerprint is retained in composition.

### Policy offer

`offer_for_program_eligibility` already accepts a registry. Pass `snapshot.registry`; no source modification is needed.

## No-Inline Scanner

Extend the shared `crs_rules.no_inlined_volatile_rules`, not a second scanner.

MEC categories:

- hours, durations, months, years, and work windows;
- CLB/NCLC levels;
- NOC/TEER/trade groups and exclusions;
- FSW grid values, bands, caps, and pass mark;
- policy/effective dates;
- funds amounts/LICO values.

Allowed contexts:

- typed grounded `machine_check` payload values;
- citations and verbatim quotes;
- YAML selector/provenance carriers required by the row schema.

Scanned surfaces:

- `crawler/models/mec.py`;
- `crawler/mecfields.py`;
- `crawler/mec_screen.py`;
- `crawler/mec_publish.py`;
- MEC-rendered prose/templates;
- registry YAML for stray values outside allowed carriers.

Python scanning must be AST/token-aware so comments/docstrings do not trip it and executable literals do. Markdown scanning skips headings but scans substantive prose. Each category needs a positive control and a false-positive control.

## Atomic Publication

Evaluation returns a validated in-memory bundle:

- `PrivateMecReport`;
- deterministic private JSON bytes;
- deterministic private Markdown bytes;
- explicit `PublicMecSummary`;
- public JSON bytes for scanning/emission.

Publication sequence:

1. Render and validate all bytes in memory.
2. Scan public bytes against exact public schema and PII/evidence/path deny rules.
3. Scan private bytes against the closed private schema/field-location allowlist; private evidence is allowed only in declared fields, while secrets and absolute paths remain forbidden.
4. Create contained output directory.
5. Stage and file-fsync every private file.
6. Move existing LKG targets to backups.
7. Replace all final targets.
8. Directory-fsync.
9. Remove backups and directory-fsync again.
10. Only then emit `_vault_ok`.

On render, scan, DB/evidence read, stage/write, file-fsync, replace, or directory-fsync failure:

- no success envelope;
- no standalone public artifact;
- clean new/staged targets;
- restore and fsync prior LKG;
- if rollback is ambiguous, retain backups rather than destroy the only known-good copy.

This follows `crawler/audit_report.py` backup/rollback/durability, not `study_review`'s delete-first lifecycle.

## Exact File Surface

### Create

| Path | Responsibility |
|---|---|
| `crawler/models/mec.py` | Strict private/public models and projection |
| `crawler/mecfields.py` | Vocabularies, normalizers, candidate adapter, period grouping |
| `crawler/mec_screen.py` | Manifest, gate context, rollup, evaluators, in-memory bundle |
| `crawler/mec_publish.py` | Scan/stage/backup/replace/fsync/rollback |
| `crawler/data/crs_rules/mec.yaml` | Grounded MEC rows without funds amounts |
| Four canonical MEC test files | Rules, screen, CLI, conformance |

### Modify

| Path | Exact change |
|---|---|
| `crawler/models/crs_rules.py` | Additive MEC machine-check payload support |
| `crawler/models/vault.py` | Wave 1: add only `program_eligibility` to FactorGroup before mec.yaml/RuleRow validation. Wave 3: consume that member unchanged and add the exact MEC FieldName evidence vocabulary |
| `crawler/crs_rules.py` | Exact manifest and shared scanner categories |
| `crawler/snapshot_policy.py` | MEC operational max-age resolver/shared age predicate |
| `crawler/extraction.py` | Six locked review.mec routes and strict labeled intake |
| `crawler/noc_review.py` | Optional snapshot/fingerprint injection |
| `crawler/study_review.py` | Injected-snapshot read-only/no-report composition |
| `crawler/cli.py` | Exact `vault screen-mec` |
| `crawler/data/crs_rules/COVERAGE.md` | Generated coverage |
| Existing extraction/vault/sidecar/scanner tests | Vocabulary, reachability, injection, conformance |

### Do not modify

- `crawler/vault.py` — the adapter belongs in `mecfields.py`; shipped store/eligibility API is sufficient.
- `crawler/policy_offer.py` — existing registry argument is sufficient.
- `crawler/crs_audit.py` — reuse `row_in_effect` unchanged.
- `crawler/auditor.py` — reuse `gate_subset` unchanged.
- `crawler/models/audit.py`, CRS auditor modules/totals/cutoff, `PublicAuditEnvelope`.
- `pyproject.toml`, `poetry.lock`.
- `scripts/run_conformance.py` — Phase 46 owns the v5 release gate.
- corpus sources, DLI snapshot/golden, or a funds snapshot.

## Validation Architecture

| Task | Primary proof |
|---|---|
| 45-01-01 | Wave-1 `program_eligibility` FactorGroup validation, typed manifest, no-default max age, all-row effectivity/freshness |
| 45-01-02 | Grounding, exact coverage, no funds values, scanner controls |
| 45-02-01 | Strict models, FAIL-first rollup, manifest-only N/A |
| 45-02-02 | One loader/snapshot, shared gate implementation, no side artifacts |
| 45-03-00 | FieldName-only model extension, full reachable evidence vocabulary, and period isolation while consuming the Wave-1 FactorGroup unchanged |
| 45-03-01 | Complete FSW and funds behavior |
| 45-03-02 | Complete FST/CEC and in-memory bundle |
| 45-04-01 | Exact CLI and LKG-preserving failure injection |
| 45-04-02 | Cross-program conformance/frozen surfaces |

Required failure seams include render, public scan, private scan, staged write, file fsync, each replace, directory fsync, and database/evidence read.

## Package Legitimacy Audit

No package-manager install is planned. `pyproject.toml` and `poetry.lock` remain read-only frozen surfaces. A package-legitimacy checkpoint becomes mandatory if execution proposes any dependency.

## Security Domain

| Threat | Required mitigation |
|---|---|
| Cross-candidate evidence | Candidate-bound query and contained candidate root |
| Cross-job fact mixing | Deterministic `employment_period_id`, strict grouping |
| Stale/superseded rule green | Shared effectivity + mandatory configured freshness |
| Registry TOCTOU | One immutable snapshot/fingerprint |
| Alternate grounding | `auditor.gate_subset` only |
| False outcome precedence | Exhaustive FAIL-first rollup |
| Arbitrary N/A | Manifest declaration plus grounded inapplicability |
| Funds fabrication | No snapshot/value/comparison; exact unavailable reason |
| Public leakage | Strict projection and pre-publish public scan |
| Private secret/path leakage | Closed private allowlist and scan |
| LKG destruction | Backup/rollback/fsync transaction |
| Dependency/network expansion | Frozen files and AST/runtime tests |

## Sources

### Official

- [IRCC Federal Skilled Worker](https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/who-can-apply/federal-skilled-workers.html)
- [IRCC Federal Skilled Trades](https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/who-can-apply/federal-skilled-trades.html)
- [IRCC Canadian Experience Class](https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/who-can-apply/canadian-experience-class.html)
- [IRCC language tests](https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/language-test.html)
- [IRCC proof of funds](https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/proof-funds.html)
- [Justice Laws IRPR](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2002-227/)
- Pinned equivalents under `corpus/guidance/`, `corpus/pr-pdi/`, and `corpus/legislation-irpr/`.

### Repository

- `crawler/crs_rules.py`, `crawler/crs_audit.py`, `crawler/auditor.py`.
- `crawler/vault.py`, `crawler/extraction.py`, `crawler/models/vault.py`.
- `crawler/policy_offer.py`, `crawler/noc_review.py`, `crawler/study_review.py`.
- `crawler/audit_report.py`, `crawler/review_packet.py`, `crawler/paths.py`, `crawler/cli.py`.
- Phase 40, 42, 43, and 44 summaries/verifications.

## Metadata

- Architecture confidence: **HIGH** — verified against live source.
- Status/outcome contract: **HIGH** — canonical checker contract.
- Official policy inventory: **MEDIUM-HIGH** — official pages and pinned corpus agree; values still require row-level citation grounding.
- Funds behavior: **HIGH** — no authorized snapshot exists.
- Dependencies: **HIGH** — existing stack is sufficient.

**Valid until:** Re-check official program pages before authoring `mec.yaml`; architecture remains tied to the inspected repository revision.
