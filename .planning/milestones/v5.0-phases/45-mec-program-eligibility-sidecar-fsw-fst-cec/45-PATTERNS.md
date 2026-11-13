# Phase 45: MEC Program-Eligibility Sidecar — Revised Pattern Map

**Mapped:** 2026-07-20  
**Revised from live source:** 2026-07-19T23:06:05-04:00
**Canonical test files:** 4 new MEC modules plus existing seam tests

## Canonical Test Layout

Create only:

- `crawler/tests/test_mec_rules.py`
- `crawler/tests/test_mec_screen.py`
- `crawler/tests/test_mec_cli.py`
- `crawler/tests/test_conformance_v5_mec_no_false_meets.py`

Extend existing:

- `crawler/tests/test_crs_no_inlined_rules.py`
- `crawler/tests/test_extraction_store.py`
- `crawler/tests/test_extraction_conformance.py`
- `crawler/tests/test_vault_cli.py`
- `crawler/tests/test_noc_review.py`
- `crawler/tests/test_study_review.py`
- `crawler/tests/test_study_review_audit_seam.py`

Do not create the obsolete split `test_mec_fsw.py`, `test_mec_fst_cec.py`, `test_mec_composition.py`, or `no_false_green` variants.

## Live-Code Findings

| Finding | Live source | Planning consequence |
|---|---|---|
| One immutable registry contract exists | `crs_rules.RegistrySnapshot` and `load_registry_snapshot` | Inject it; never add a MEC loader |
| One shared grounding implementation exists | `auditor.gate_subset` | All exact subsets call it |
| Effective-window helper exists | `crs_audit.row_in_effect` | Reuse unchanged for every MEC row |
| RuleRow imports the closed vault FactorGroup | `models.crs_rules.RuleRow.factor_group` → `models.vault.FactorGroup` | Add `program_eligibility` in Wave 1 before mec.yaml validation; defer only FieldName additions to Wave 3 |
| DLI max age is explicit/no-default | `snapshot_policy.dli_snapshot_max_age_days` | Add parallel MEC resolver in same module |
| NOC eligible reads omit fingerprint injection | `noc_review._candidate_eligible_duty_values` | Add optional snapshot/fingerprint and pass it to `is_audit_eligible` |
| Study accepts optional snapshot but writes/invalidate reports | `study_review.review_study` | Add read-only/no-report mode |
| Policy offer accepts a registry | `policy_offer.offer_for_program_eligibility` | Pass `snapshot.registry`; no file change |
| Vault already forces pending and owns five-key eligibility | `vault.add_extracted_value`, `confirm_value`, `is_audit_eligible` | Reuse unchanged |
| Extraction owns doc/field producers and inert route seeding | `extraction._FIELD_SPECS`, `_DOC_TYPE_FACTOR`, review.study parent | Add locked review.mec routes here |
| Candidate-scoped adapter precedent lives in sidecars | `noc_review`, `study_review` | Put MEC adapter in `mecfields.py`, not `vault.py` |
| Study writer deletes/replaces one latest file | `study_review._publish_private_report` | Not sufficient for MEC LKG preservation |
| Audit report has backup/rollback/fsync transaction | `audit_report._stage_text` through `_persist_report` | Use as MEC publication analog |
| Shared scanner is line-based today | `crs_rules.no_inlined_volatile_rules` | Extend it with Python AST/token context and MEC categories |

## File Ownership

| File | Role | Closest analog |
|---|---|---|
| `crawler/models/mec.py` | Strict private/public model | `crawler/models/audit.py` |
| `crawler/mecfields.py` | Vocabulary, normalization, candidate adapter, period grouping | `crawler/dlifields.py` + sidecar candidate query |
| `crawler/mec_screen.py` | Manifest, gate context, rollup, evaluators, in-memory bundle | `crawler/study_review.py` without write coupling |
| `crawler/mec_publish.py` | Recoverable private publication | `crawler/audit_report.py` |
| `crawler/data/crs_rules/mec.yaml` | Grounded policy rows | `additional.yaml`, `study_dli.yaml` |
| `crawler/models/crs_rules.py` | Additive typed payload fields | Existing `MachineCheck` |
| `crawler/models/vault.py` | Wave-1 `program_eligibility` FactorGroup addition; Wave-3 MEC FieldName additions | Existing closed literals |
| `crawler/crs_rules.py` | Manifest, loader reuse, scanner | Existing registry engine |
| `crawler/snapshot_policy.py` | MEC operational freshness config | Existing DLI resolver |
| `crawler/extraction.py` | Six doc routes and strict manual forms | Existing study route |
| `crawler/noc_review.py` | Snapshot/fingerprint injection | Existing candidate read |
| `crawler/study_review.py` | Injected read-only/no-report mode | Existing optional snapshot |
| `crawler/cli.py` | Exact command boundary | `_cmd_vault_study_review`, `_cmd_vault_audit` |

## Pattern 1: Typed Grounded Rows, Structural Manifests

Use the existing strict row stack:

- `MachineCheck`/`RuleRow` use `ConfigDict(extra="forbid")`.
- Every payload value has a citation index.
- `load_registry_snapshot` reads sorted YAML once and fingerprints the same validated model.
- `coverage_report` uses structural labels.
- `COVERAGE.md` is generated through `render_coverage_markdown`.

Add `program_eligibility` structural labels only. Program manifests contain:

- criterion ID;
- exact required rule IDs;
- conditional applicability declaration;
- no thresholds, dates, durations, levels, points, caps, groups, or amounts.

Before loading `mec.yaml` in Wave 1, add exactly `program_eligibility` to
`crawler.models.vault.FactorGroup`; `RuleRow.factor_group` imports that Literal and
otherwise rejects every MEC row. This early model change is inert typing only:
Wave 1 does not add `FieldName` evidence members or any CRS scoring/dispatch entry.

Coverage must reject duplicate, missing, gap-only, malformed, and unknown MEC wiring.

## Pattern 2: One Snapshot, One Gate Implementation

At the command boundary:

1. Resolve required config.
2. Load one `RegistrySnapshot`.
3. Preflight the index.
4. Build exact subset(s).
5. Call `auditor.gate_subset`.
6. Open the vault.

The MEC gate context retains the actual snapshot object and fingerprint. Inject it into:

- MEC criteria;
- `noc_review`;
- `policy_offer` as `snapshot.registry`;
- `study_review`.

“One gate” is one shared function implementation. It is correct for:

- the exact MEC subset to call `gate_subset`;
- candidate-dynamic study rows to form a separate transient subset and call the same `gate_subset`.

It is incorrect to:

- call `validate_registry` or retrieve functions directly;
- reload YAML in a sidecar;
- recompute a fingerprint;
- claim one literal call when distinct consumed subsets require validation.

Required tests:

- `load_registry_snapshot` count equals one;
- injected object identity is preserved;
- every fingerprint equals the command fingerprint;
- all gate calls resolve to `auditor.gate_subset`;
- injected sidecars never load registry.

## Pattern 3: Effectivity Plus Operational Freshness

For every selected MEC row:

1. Require a non-`None` criterion reference date.
2. Call existing `crs_audit.row_in_effect`.
3. Call one shared operational age helper with row crawl date, reference date, and resolved MEC max age.
4. Mark stale, future, malformed, superseded, or out-of-window rows unusable.

Resolver pattern mirrors `dli_snapshot_max_age_days`:

- explicit input first;
- otherwise `PR_MEC_RULE_MAX_AGE_DAYS`;
- positive integer only;
- no default;
- invalid explicit input does not fall back.

The bound is operational configuration, not an authoritative age claim. Durable legislation still crosses both checks.

The DLI snapshot retains its own max-age resolver/probe; do not substitute MEC rule max age for DLI snapshot age.

## Pattern 4: Exact Status and Outcome Algebra

Criterion:

- `PASS`
- `FAIL`
- `AT-RISK`
- `N/A`

Program:

- `MEETS`
- `DOES-NOT-MEET`
- `AT-RISK`

Rollup:

1. Exact-set validation; unknown/missing/unwired/invalid-N/A → `AT-RISK`.
2. Any confirmed deterministic `FAIL` → `DOES-NOT-MEET`.
3. Else any `AT-RISK` → `AT-RISK`.
4. Else all `PASS`/valid `N/A` → `MEETS`.
5. Else `AT-RISK`.

Do not use the previous AT-RISK-before-FAIL ordering. A real deterministic failure is not hidden by unrelated uncertainty.

`N/A` requires:

- known criterion;
- manifest conditional declaration;
- grounded applicability predicate;
- deterministic inapplicability.

Any other N/A attempt is `AT-RISK`.

## Pattern 5: Closed Public/Private Models

Follow `crawler/models/audit.py`:

- strict models with `extra="forbid"`;
- public corpus citation shape;
- reject `ev_` IDs publicly;
- reject absolute/traversal paths publicly;
- explicit field-by-field projection;
- never dump private then delete keys.

Private criteria may include:

- applicant values;
- evidence IDs;
- exact rule IDs/citations;
- keyed employment-period traces;
- completeness flags;
- sidecar inputs;
- grid bounds;
- row usability/freshness details.

Public criteria include only:

- criterion ID;
- canonical status;
- closed reason;
- corpus citations.

Use exact reason `funds_snapshot_unavailable`.

## Pattern 6: Complete Reachable Evidence on `review.mec`

Canonical document types:

- `mec-profile`
- `mec-employment-period`
- `mec-trade-certificate`
- `mec-valid-offer`
- `mec-funds`
- `mec-province-status`

All are locked to inert `review.mec` in group `program_eligibility`, regardless of factor override.

The FactorGroup member already exists from Wave 1 so registry rows validate before
this evidence slice. Wave 3 consumes it unchanged and extends only the closed
`FieldName` vocabulary needed by these documents.

`mecfields.py` owns:

- `MEC_DOCUMENT_FIELDS`;
- closed normalizers;
- field/doc allowlists;
- candidate-scoped query;
- calls to `vault.is_audit_eligible(..., registry_fingerprint=...)`;
- scalar conflict detection;
- employment-period grouping.

`crawler/vault.py` is not modified. Its existing store and five-key predicate are
the canonical path. `crawler/models/vault.py` is modified only at the two explicit
contract seams above: FactorGroup in Wave 1 and FieldName in Wave 3.

### Manual form path

Strict labeled private forms use the existing:

`vault import → vault extract → vault fields → vault confirm/correct/reject`

This makes hard-to-extract facts reachable without semantic inference or a new bulk/manual DB API. Exact labels produce pending values; unknown labels produce nothing; corrections remain per-value.

## Pattern 7: Deterministic Employment-Period Join

One `mec-employment-period` document is one period envelope.

Derive `employment_period_id` from stable content identity and a fixed period slot. Stamp/reference that exact key for every period value.

The adapter:

- groups only by `employment_period_id`;
- requires one internally consistent key;
- rejects duplicates/conflicts;
- never joins across documents by NOC, dates, employer text, candidate, or insertion order;
- exposes complete period records to evaluators.

Evaluators:

1. classify each period against every applicable predicate;
2. record include/exclude reasons privately;
3. aggregate only included periods;
4. require confirmed complete scope before an absence-based `FAIL`.

Required negative test: combine qualifying dates/hours from one job with authorization/paid status from another and prove no criterion passes.

## Pattern 8: Shipped Sidecars in Read-Only Composition

### NOC

Add optional `registry_snapshot` or fingerprint. Pass it to every `is_audit_eligible` call. Preserve current `AT-RISK/GAP/N/A` semantics; never convert fully confirmed duties to PASS.

### Study

Add an explicit read-only/no-report mode:

- skip `invalidate_latest_report`;
- skip `_write_private_report`;
- use injected snapshot;
- retain dynamic transient rows;
- gate dynamic subset through `auditor.gate_subset`;
- return composition material without side artifacts.

Direct `vault study-review` behavior remains unchanged by default.

### Policy offer

No source change. Pass `snapshot.registry`. Its manual/zero-CRS result is unchanged.

## Pattern 9: Funds Without an Amount Snapshot

Ground only:

- applicability;
- exemption;
- accessibility;
- borrowed/equity restrictions.

Do not ground or compare:

- household amount thresholds;
- currency values;
- LICO values.

Behavior:

- grounded confirmed exemption → manifest-declared amount branch `N/A`;
- otherwise → criterion `AT-RISK`, reason `funds_snapshot_unavailable`;
- stored amount/household data stays private and cannot change status.

## Pattern 10: Shared AST/Token-Aware No-Inline Scanner

Extend `crs_rules.no_inlined_volatile_rules`.

MEC categories:

- hours/durations/months/years;
- CLB/NCLC;
- NOC/TEER/trade groups;
- FSW grid values/pass mark/caps;
- dates;
- funds/LICO values.

For Python:

- parse/tokenize;
- ignore comments/docstrings;
- inspect executable constants and policy context;
- avoid identifier-substring and generic arithmetic false positives.

For YAML:

- permit only typed machine-check/citation/selector/provenance carriers;
- flag stray prose/literals.

For Markdown/rendered prose:

- skip headings;
- scan substantive claims.

Enroll every MEC module and rendered text. Keep one biting positive control and one false-positive control per category.

## Pattern 11: Side-Effect-Free Evaluation

`mec_screen` returns an in-memory bundle:

- strict private report;
- deterministic private JSON/Markdown;
- explicit public summary;
- public bytes for scan/emission.

It does not:

- create directories;
- invalidate reports;
- write temp/final files;
- commit/rollback DB;
- emit stdout.

This allows every evaluation/DB/model/render failure to occur before publication.

## Pattern 12: LKG-Preserving Atomic Publication

Use `audit_report.py` patterns:

- sibling stage files;
- file flush/fsync;
- collision backup;
- `os.replace`;
- directory fsync;
- backup restoration;
- conservative handling of ambiguous rollback.

Publication order:

1. render/validate;
2. scan public/private bytes;
3. stage all private files;
4. back up all prior LKG targets;
5. replace all targets;
6. fsync directory;
7. remove backups;
8. fsync directory again;
9. return success to CLI.

No public artifact is written. Public summary is emitted only after private publication succeeds.

Failure tests:

- render;
- public scan;
- private scan;
- stage write;
- file fsync;
- each replace;
- directory fsync;
- DB/evidence read before publish.

Every failure preserves prior LKG bytes, creates no success envelope, and leaves no new public artifact.

## Pattern 13: Exact CLI Boundary

Command is exactly:

`vault screen-mec --program fsw|fst|cec`

Order:

1. parse/validate program and raw config;
2. resolve MEC rule max age;
3. load one registry snapshot;
4. preflight corpus index;
5. prepare exact MEC gate context;
6. preflight DLI only if FSW study composition is consumed;
7. open vault;
8. evaluate read-only;
9. publish private LKG atomically;
10. emit `_vault_ok`.

Do not register an alternate alias.

Outer JSON remains the existing five-key envelope. Human mode prints only safe status/reason/count/path detail.

## Frozen Surfaces

Do not modify:

- `crawler/vault.py`
- `crawler/policy_offer.py`
- `crawler/crs_audit.py`
- `crawler/auditor.py`
- `crawler/models/audit.py`
- CRS deciders/cards/totals/cutoff
- `PublicAuditEnvelope`
- `pyproject.toml`
- `poetry.lock`
- `scripts/run_conformance.py`
- corpus/DLI snapshot

Phase 46 owns SAFE-11/SAFE-12 and the v5 release-gate command.

## Anti-Patterns

- Legacy criterion-status spellings.
- AT-RISK precedence over a confirmed deterministic FAIL.
- Caller-selected N/A.
- Any alternate MEC command spelling.
- Reloading registry in NOC/STUDY composition.
- Interpreting “one gate” as forbidding valid subset calls.
- Passing `None` for MEC max age.
- Exempting static legislation from operational freshness.
- Joining work facts without `employment_period_id`.
- Extracting uncertain facts as confirmed.
- Comparing funds amount without a snapshot.
- Writing/deleting a report before all scans pass.
- Using study's delete-first writer for MEC LKG.
- Emitting public success before directory fsync.
- Modifying PublicAuditEnvelope/CRS total.
- Adding Phase-46 release-gate wiring.

## Verification Commands

- `.venv/bin/python -m pytest crawler/tests/test_mec_rules.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_mec_screen.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_mec_cli.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_mec_no_false_meets.py crawler/tests/test_crs_no_inlined_rules.py -q`
- `.venv/bin/python -m pytest crawler/tests -q`
- `.venv/bin/python scripts/check_publish_safe.py`

## Metadata

**Strong analogs:** typed registry, `gate_subset`, five-key evidence quarantine, NOC candidate scoping, study transient rows, audit report transaction, strict public projection.
**Intentional non-analogs:** CRS outcome summing, study delete-first report lifecycle, direct public/private model dumping.
**No package install:** existing stdlib/Pydantic/PyYAML/SQLite stack is sufficient.
