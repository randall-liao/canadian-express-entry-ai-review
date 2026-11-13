# Phase 44: Canadian-Study DLI/PGWP Evidence Gate — Revised Research

**Researched:** 2026-07-19
**Revised:** 2026-07-19 after checker review
**Requirements:** STUDY-02, STUDY-03, STUDY-04
**Confidence:** HIGH for live interfaces/data; fail-closed for the historical designation limitation

## Executive Finding

The current `crawler.auditors.additional.decide_study` greens `additional.study` from a credential tier alone. That is unsafe because the db-free `DecisionContext` cannot inspect the pinned DLI index, cannot prove R73(1), and normal Phase-44 evidence is intentionally stored under inert `review.study`.

Phase 44 therefore has two deliberately separate surfaces:

1. **`study_review` sidecar:** db-backed, candidate-scoped, turns every consumed candidate DLI/PGWP chunk into a strict transient in-memory `RuleRow`, and gates those rows with the static credential/R73 rows through one authoritative `auditor.gate_subset`. It writes exact dynamic citations only to a private vault report and returns a closed public summary.
2. **`decide_study` grid seam:** credential-only and fail-closed. It never claims that DLI reaches its db-free context and never returns `SUBSTANTIATED` in Phase 44.

The live snapshot proves only **current** designation. Even an exact current match with all other checks satisfied must terminate at:

`AT-RISK / designation_historical_unproven`

There is no green Phase-44 study path.

## Requirement Support

| ID | Required outcome | Revised implementation |
|----|------------------|------------------------|
| STUDY-02 | Import institution/DLI, credential, dates, status as pending; per-field confirm/correct/reject | Six private `study_proof` fields on inert `review.study`; existing born-pending and five-key eligibility gates |
| STUDY-03 | Exact DLI + grounded credential rule + grounded R73; credential alone never green | Sidecar builds candidate-specific transient rows for #000 and every consumed PGWP chunk, gates them with credential/R73 through the shared validate/retrieve path; grid decider is credential-only fail-closed |
| STUDY-04 | Missing historical proof or stale snapshot stays AT-RISK/refusal | Explicit caller max-age, snapshot preflight, common chunk-provenance validation, and unconditional current-only temporal cap |

## Verified Live Interfaces

### Shared grounding gate

- `crawler.auditor.gate_subset(subset: Registry, db) -> None`
- It currently calls `crs_rules.validate_registry`.
- It raises `AuditGroundingError` for violations and consumed `gap:true` rows.
- `_gate_or_raise is gate_subset` remains the compatibility alias.

Phase 44 must strengthen this same helper—not create a sidecar validator—so it also consumes `crs_rules.retrieve_what_you_cite` for the identical `Registry` and DB. A row fails the authoritative gate if validation fails, retrieval selects nothing, the selected chunk disagrees with the citation, or the selected quote does not ground. This is required because `validate_registry` checks citation+quote but does not inspect selector family/marker/title.

The sidecar creates one temporary `Registry` containing:

- static `additional.study`
- static `study.r73_definition`
- one transient candidate row citing exact `dli/<DLI>.md#000`
- one transient candidate row for every consumed PGWP chunk

The static `study.dli.designation` UofT row remains full-registry/fixture coverage only. It is not runtime candidate evidence, even for UofT, and is never reused for another DLI.

### Registry row shapes

`MachineCheckKind` allows:

- `accepted_enum`
- `threshold`
- `validity_window`
- `cap`
- `points_table`
- `conversion`
- `policy_flag`

There is no `admissibility_note` or `current_status` kind. The R73 row and dynamic observed-current-status rows use `accepted_enum`. The live `additional.study` row is a `points_table` whose accepted tier labels are `1-2` and `3+`; those labels must be read from the row, not duplicated as scoring logic in the sidecar.

Dynamic rows use only existing strict pydantic models and are never persisted or emitted as YAML. They carry no applicant field other than the public DLI identifier needed to select the authoritative institution record.

### Vault eligibility

`vault.is_audit_eligible` is true only for:

- confirmation status `confirmed` or `corrected`
- quality `ok`
- all five confirmation bindings current:
  - source file SHA-256
  - render SHA-256
  - parser version
  - profile-claim version
  - rule-registry version

The sidecar needs a candidate/document/factor/field-scoped query and then must call this predicate for each value. `audit_eligible_values(factor_id)` alone does not make the candidate join explicit enough for this phase’s contract.

### CLI envelope

`contract.envelope` always has exactly:

- `schema_version`
- `ok`
- `command`
- `result`
- `error`

For a successful study review, `env["result"]` must have exactly `study_review.PUBLIC_FIELDS`.

### Vault schema

The live schema is:

- `PRAGMA user_version == 3`
- no Phase-44 DDL is needed
- full sorted table/index fingerprint (including SQLite auto-indexes):
  `9b35bc925c4ee39216980d4f74b937cd0b971c4f423116f1b84bf6bdb561fe50`

Study fields are a typed `FieldName` extension plus data rows only.

## Exact DLI Chunk Layout

The live `corpus/index.db` uses two chunks per sampled DLI document.

### Current designation chunk

`dli/O19332746152.md#000`

- relpath: `dli/O19332746152.md`
- section: `DLI O19332746152 — University of Toronto`
- current live `chunk_sha`: `86d9b026aec4`
- contains exact DLI number
- contains current designation statement
- explicitly says current status does not establish prior-period designation or program-level PGWP eligibility

### PGWP table chunk

`dli/O19332746152.md#001`

- section ends with `Post-Graduation Work Permit (PGWP) eligibility by campus`
- current live `chunk_sha`: `d2e8558bb43d`
- table values are exact `Yes`

Negative fixtures:

- `dli/O246878951383.md#001` — `Details`, candidate-unique complete table marker, current `chunk_sha` `b646c53d5fd3`
- `dli/O110032269317.md#001` — `No`, current `chunk_sha` `491eb9ed1855`

The implementation must not hard-code those hashes as policy. Tests may assert current fixture layout. Runtime exact resolution is discovery/preflight only and must:

1. Normalize exact DLI format.
2. Resolve `dli/<DLI>.md#000`.
3. Enumerate exact `#001`, `#002`, ... until the first miss.
4. Require the returned coordinate/relpath and expected #000/PGWP section class.
5. Supply verbatim #000 lines and complete PGWP table text to transient citations.

The sidecar does not call `searchindex.search`, perform a custom hash/substr acceptance verdict, or match institution names. The strengthened shared gate performs search/selector retrieval and quote grounding.

### Transient candidate rows

The #000 row uses query `<DLI>`, selector `family: dli`, marker `DLI number: <DLI>`, candidate-specific title constraint, exact #000 citation, `accepted_enum` over `dli_number`, and volatile metadata with that chunk's crawl date.

Each consumed PGWP row uses a deterministic ordinal rule id, query and marker derived from the complete verbatim table chunk, selector `family: dli` plus the candidate-specific title constraint, exact citation/quote, `accepted_enum` over distinct observed `Yes`/`No`/`Details` values, and volatile metadata with that chunk's crawl date. The `(family, marker, title constraint)` combination is candidate-unique and retrieve-what-you-cite must select exactly the cited chunk. The claim is only that the snapshot currently records those values.

There is no authoritative PDI row in the current registry that supports historical designation or program-level PGWP eligibility. Do not author one. Current designation/PGWP rows are observed current-status facts only.

## Conjunctive Sidecar Contract

`review_study(vault_, db, *, candidate_id: str, max_age_days: int) -> dict`

The sidecar never imports or calls `snapshot_policy`. The CLI resolves configuration once and passes the exact positive integer. The sidecar validates the runtime type/value and passes it unchanged to `probe_snapshot`.

Required eligible fields:

- `dli_number`
- `credential_level`
- `program_start`
- `program_end`
- `study_status`

Optional private field:

- `institution_name`

Validation order:

1. Validate positive non-bool `max_age_days`.
2. Probe DLI snapshot.
3. Load the two static governing rows and candidate-scoped `review.study` values.
4. Apply shipped eligibility/conflict checks and require every conjunctive field.
5. Parse ISO program dates and require start <= end.
6. Exact-resolve candidate #000 and sequential PGWP chunks for discovery/quotes.
7. Build one strict transient row per consumed chunk, carrying that chunk's crawl date, and combine with credential/R73 rows.
8. Call the strengthened `auditor.gate_subset` once against the real DB.
9. Require one common nonempty `crawl_date` across the gated dynamic rows.
10. Read tier/status/PGWP values only from gated machine-check payloads.
11. Apply PGWP/manual result.
12. Apply terminal historical-designation cap.

Reason classes:

| Condition | Result |
|-----------|--------|
| Invalid supplied bound | `AT-RISK snapshot_config_invalid` |
| Non-ok snapshot | `AT-RISK snapshot_unusable` |
| Missing/bad/ungrounded required row | `AT-RISK grounding_refused` |
| Missing/unequal consumed chunk crawl_date | `AT-RISK snapshot_provenance_mismatch` |
| No eligible study evidence | `N/A no_study_evidence` |
| Missing required field | `GAP missing_study_fields` |
| Conflicting/invalid value or dates | `AT-RISK ambiguous_study_evidence` |
| Tier not grounded | `GAP below_grounded_credential_tier` |
| Status not grounded completion | `GAP study_not_completed` |
| Malformed/missing exact DLI chunk | `AT-RISK exact_dli_mismatch` |
| PGWP Details | `AT-RISK pgwp_details_manual` |
| PGWP No | `AT-RISK pgwp_no` |
| Mixed/malformed PGWP table | `AT-RISK pgwp_ambiguous` |
| Exact/current complete case | `AT-RISK designation_historical_unproven` |

PGWP is reported as snapshot evidence only. It is never used to infer a program’s eligibility or award points.

## Private/Public Projection

Public result fields are exactly:

- `status`
- `reason`
- `required_count`
- `confirmed_count`
- `eligible_count`
- `as_of`

`as_of` is exactly the common validated `crawl_date` of #000 and every consumed PGWP chunk. It is never wall-clock, manifest, or static-row time. Before resolution, and whenever common provenance cannot be established, it is null.

The public result and whole CLI JSON must not contain:

- a DLI number matching `O\d{6,}`
- institution name
- applicant credential/status/dates
- `ev_` evidence id
- raw `relpath#ordinal` citation id
- quote text
- report or absolute filesystem path

The deterministic private artifact is:

`<candidate-vault>/output/study-review/latest.json`

It carries applicant fields, evidence ids, grounded credential/R73 citations/quotes, verdict/common as-of, and the screening-not-legal-advice notice. Its `dynamic_citations` list is ordinal-sorted, has one entry per transient row, and each object has exactly `rule_id`, `kind`, `chunk_id`, `quote`, `crawl_date`, and `observed_values`; `kind` is `designation_current` or `pgwp_current`. The static `study.dli.designation` row never appears in that list. A preflight, provenance, or grounding refusal writes no report.

## Real Grid Seam

Normal extraction links to `review.study`, not `additional.study`. No projection feeds DLI or R73 into `DecisionContext`.

`decide_study` therefore:

- returns `GAP missing_evidence` with no credential
- returns `GAP below_threshold` for a tier absent from the grounded credential row
- returns `AT-RISK credential_only_no_designation` for a grounded tier
- always has `substantiated_points=None`
- has no `SUBSTANTIATED` branch

`consumed_factor_ids("additional.study")` remains `["additional.study"]`. Claiming that DLI reaches this decider would be false.

## One Config Resolver

`snapshot_policy.dli_snapshot_max_age_days(explicit)`:

- explicit override first
- `PR_DLI_SNAPSHOT_MAX_AGE_DAYS` fallback
- positive non-bool integer only
- no default
- invalid/missing returns `None`

The CLI invokes it **before any index probe**, then index preflight, then snapshot preflight, then `open_vault`. The sidecar receives the resolved int and does not re-resolve.

## Conformance Requirements

The negative matrix must include:

- rejected, pending, corrected
- each of five stale keys
- low quality, ambiguous
- missing/non-int/zero/negative config
- missing/empty/unreadable/corrupt/drifted/stale index or snapshot
- exact mismatch, name-only
- PGWP Details and No
- UofT Yes plus independent Details and No candidate fixtures
- one transient row/private citation entry per consumed #000/#001+ chunk
- tampered quote, marker, family, and candidate DLI/title pairing through `gate_subset`
- missing/unequal chunk crawl dates and exact common `as_of`
- missing/invalid program dates
- current-only historical gap
- credential-only real audit seam
- missing R73/credential grounding
- unwired factor
- all-factor contamination/freeze, including `core.age`

Universal rule: no `SUBSTANTIATED`, no nonzero points. Every preflight refusal has zero artifacts.

## Non-Vacuous Freeze Proofs

Ignored artifacts cannot be checked with `git diff`.

- `corpus/dli`: pre/post canonical hash of sorted relative `.md` paths + body hashes + manifest byte hash
- `corpus/index.db`: pre/post SHA-256, size, and mtime; read-only URI open
- tracked golden DLI family: generator byte identity and `git show HEAD:<path>` comparison
- tracked frozen code: `git diff --quiet HEAD -- <tracked paths>`
- vault schema: user_version + table/index fingerprint
- dependencies: exact pyproject dependency set
- lock: `poetry.lock` SHA-256 `6f5d47b3cfd2f78e6b796936b35ce2a3d2078447e0b61953e65114de71af3ef5`

No `pyproject.toml` edit is needed. The existing pytest marker already registers `conformance`.

## Package Legitimacy Audit

No package installation is planned.

| Package | Registry | Verdict | Disposition |
|---------|----------|---------|-------------|
| none | — | N/A | Existing stdlib/internal stack only |

## Explicit Exclusions

- no new dependency
- no max-age default
- no live network lookup at audit time
- no fuzzy institution matching
- no automated program-level PGWP conclusion
- no static UofT row used as runtime candidate evidence
- no persisted/YAML dynamic rows or second validation engine
- no green Phase-44 study result
- no Phase-45 MEC wiring
- no legal/eligibility determination
- no public citation or applicant-detail leakage

## Sources

- Live code: `crawler/auditor.py`, `vault.py`, `searchindex.py`, `index_health.py`, `cli.py`, `contract.py`, `auditors/additional.py`, `models/crs_rules.py`
- Grounded data: `crawler/data/crs_rules/additional.yaml`, `study_dli.yaml`
- Live DLI family/index: `corpus/dli/*.md`, `corpus/index.db`
- Phase 40 summaries: shared gate and snapshot preflight
- Phase 41 summaries: pinned family, grounded designation, real-index closeout
- ROADMAP/REQUIREMENTS: STUDY-02/03/04 and milestone constraints
