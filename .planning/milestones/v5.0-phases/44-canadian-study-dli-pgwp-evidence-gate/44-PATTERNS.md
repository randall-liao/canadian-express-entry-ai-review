# Phase 44 Pattern Map — Revised

**Mapped:** 2026-07-19
**Basis:** Live Phase 40/41 interfaces, current DLI family/index, vault schema, CLI envelope, and checker-required fail-closed seams

## Responsibility Map

| File | Responsibility | Closest live analog | Non-negotiable boundary |
|------|----------------|---------------------|-------------------------|
| `crawler/dlifields.py` | Study field names and fail-closed normalization | `siblingfields.py` | Vocabulary only; no points/defaults |
| `crawler/extraction.py` | `study_proof` producer | `sibling_proof` route | Normal path links only to `review.study` |
| `crawler/snapshot_policy.py` | One operational bound resolver | `paths.py` env precedence | CLI/boundary only; no default |
| `crawler/study_review.py` | Transient-row exact-DLI sidecar, provenance, and private report | `noc_review.py` + `noc_worksheet.py` | Explicit bound; one row per chunk; closed public result |
| `crawler/data/crs_rules/study_dli.yaml` | R73 definition row | existing designation row | Allowed machine-check kind; inert id |
| `crawler/auditor.py` | One authoritative registry gate | existing `validate_registry` + `retrieve_what_you_cite` | Shared validation/retrieval orchestration; no custom quote logic |
| `crawler/auditors/additional.py` | Close credential-only green | existing fail-closed deciders | No DLI claim; never SUBSTANTIATED |
| `crawler/cli.py` | User boundary | `_cmd_vault_noc_review` | config → index → snapshot → vault |
| Phase-44 tests | Negative controls and freeze pins | Phase 40/41/NOC/POLICY tests | Non-vacuous ignored-artifact checks |

## Pattern 1 — Inert evidence producer

Apply the existing extraction quarantine:

- `study_proof` fields: `institution_name`, `dli_number`, `credential_level`, `program_start`, `program_end`, `study_status`
- upsert `review.study` as the FK parent
- link normal extraction only to `review.study`
- call `vault.add_extracted_value`, which forces `pending`
- confirm/correct/reject one value at a time

The test must enumerate every `FULL_GRID_FACTORS` member, including `core.age`, and prove no study value is linked there.

## Pattern 2 — Candidate-scoped eligible load

Do not use an unscoped “latest value” query.

The sidecar query must constrain:

- `documents.candidate_id = requested candidate`
- `extracted_values.factor_id = 'review.study'`
- `field_name` in the six-element study vocabulary

Then call `vault.is_audit_eligible` for every value. Identical duplicates may collapse deterministically; conflicting eligible duplicates are ambiguous and fail closed.

This preserves:

- confirmed/corrected only
- quality `ok`
- all five staleness bindings

## Pattern 3 — One authoritative validate/retrieve gate

Strengthen `auditor.gate_subset` itself:

1. Call `crs_rules.validate_registry` on the supplied Registry and real DB.
2. Call `crs_rules.retrieve_what_you_cite` on the same Registry and DB.
3. Reject every validation violation, gap row, missing selection, citation disagreement, or ungrounded retrieval.

Do not add substring/hash/selector implementations to the sidecar or gate. The gate only orchestrates the existing search/resolve/grounding machinery. This makes tampered quote, marker, family, and candidate title/DLI pairing fail at one shared boundary.

## Pattern 4 — Temporary candidate Registry

The runtime Registry contains exactly:

- static `additional.study`
- static `study.r73_definition`
- one transient `RuleRow` for candidate #000
- one transient `RuleRow` per consumed PGWP chunk

All dynamic rows are strict pydantic objects, in memory only, never persisted/YAML, and carry no applicant data beyond the public DLI identifier needed for selection. The static UofT `study.dli.designation` row stays registry/fixture coverage only and never enters a runtime candidate Registry or report.

There is no current authoritative PDI row for a historical-designation or program-level PGWP implication. Do not invent one. Read accepted tier labels from the gated credential row and completion statuses from the gated R73 row.

## Pattern 5 — Exact resolution supplies transient citations

The candidate’s normalized DLI determines the exact relpath; `searchindex.resolve` is discovery/preflight only.

- `#000`: current designation chunk
- `#001+`: PGWP table sections, enumerated until first miss

For each resolved chunk:

- exact `chunk_id`
- exact `relpath`
- expected section classification
- exact stored text/crawl metadata used to construct a citation

The #000 transient row uses:

- query `<DLI>`
- selector `family=dli`, marker `DLI number: <DLI>`, candidate title constraint
- verbatim DLI/current/current-only lines
- accepted-enum DLI payload and volatile per-chunk crawl date

Each PGWP row uses:

- deterministic candidate/ordinal rule id
- query + marker from the complete verbatim table text
- selector `family=dli` plus candidate title constraint
- exact citation, observed Yes/No/Details accepted-enum payload, and per-chunk crawl date

Treat `(family, marker, candidate title constraint)` as the unique selector; retrieve-what-you-cite must select exactly the cited chunk. Do not call `searchindex.search` from the sidecar, implement a custom hash/substr verdict, or compare institution names. Acceptance comes only from `gate_subset`.

## Pattern 6 — PGWP is evidence, not a program decision

| Table observation | Sidecar result |
|-------------------|----------------|
| any `Details` | `AT-RISK pgwp_details_manual` |
| all `No` | `AT-RISK pgwp_no` |
| mixed Yes/No or malformed | `AT-RISK pgwp_ambiguous` |
| all `Yes` | continue to temporal cap |

No branch concludes that an applicant’s particular program is PGWP eligible.

## Pattern 7 — Common snapshot provenance and temporal cap

Every constructed dynamic row reaches `gate_subset`, then collect the crawl dates of #000 and every consumed PGWP row:

- every value must be a nonempty string
- every value must be exactly equal
- public/private `as_of` is that common value verbatim
- missing/unequal → `AT-RISK snapshot_provenance_mismatch`, `as_of: null`, no report
- refusal before DLI resolution → `as_of: null`

Never use wall-clock, manifest, static-row, or arbitrarily selected chunk time.

All conjunctive checks are necessary but not sufficient.

Even when:

- candidate DLI exact-matches
- the three-row subset grounds
- credential tier is grounded
- status proves completion
- start/end dates are valid
- PGWP cells are Yes

the live snapshot has no historical designation window. The terminal result remains:

`AT-RISK designation_historical_unproven`

There is no `SUBSTANTIATED` literal or branch in `study_review.py`.

## Pattern 8 — One resolver, explicit handoff

`snapshot_policy.dli_snapshot_max_age_days(explicit)` is the sole resolver.

CLI ordering:

1. Resolve explicit/env config.
2. Refuse invalid/missing config before any probe.
3. Preflight index.
4. Preflight DLI snapshot with the resolved int.
5. Open vault.
6. Call `review_study(..., max_age_days=the_same_int)`.

The sidecar validates and uses the supplied int but never imports/calls `snapshot_policy`.

Keep the CLI argument as raw text so non-integer explicit values receive the normal JSON refusal instead of escaping through argparse.

## Pattern 9 — Private/public split

Public fields:

- `status`
- `reason`
- `required_count`
- `confirmed_count`
- `eligible_count`
- `as_of`

Private report:

`output/study-review/latest.json`

Private-only content:

- DLI and institution
- credential/status/dates
- evidence ids
- `dynamic_citations`, ordinal-sorted with one object per transient row and exact keys `rule_id`, `kind`, `chunk_id`, `quote`, `crawl_date`, `observed_values`
- grounded rule citation ids/quotes
- screening notice

`kind` is `designation_current` or `pgwp_current`. The list covers #000 and every consumed PGWP chunk one-to-one. The static UofT row is never runtime gate input or private candidate evidence.

The CLI first asserts the five-key envelope, then `env["result"]` exactly equals `PUBLIC_FIELDS`. Public `as_of` is only the validated common timestamp; public JSON contains no DLI/citation ids. Scan the entire JSON, not only `result`.

## Pattern 10 — Real grid seam stays credential-only

Do not add DLI fields to `DecisionContext`, do not add DLI/R73 to `consumed_factor_ids("additional.study")`, and do not claim the sidecar feeds the grid.

`decide_study`:

- missing credential → GAP
- unknown tier → GAP
- grounded tier → AT-RISK `credential_only_no_designation`
- points always `None`

Real-seam test:

- deliberately force-link a credential to `additional.study`
- drive `auditor.audit_one`
- assert no SUBSTANTIATED/nonzero result
- separately prove normal `review.study` values never reach that factor

## Pattern 11 — Zero-artifact refusal

Preflight failures:

- missing/non-int/zero/negative config
- missing/empty/unreadable/corrupt/drifted index
- missing/empty/corrupt/drifted/stale snapshot

For each:

- nonzero exit
- valid PII-safe envelope
- no candidate vault creation
- no report
- no database mutation

Grounding or snapshot-provenance refusal occurs before private report write and returns a safe closed result.

## Pattern 12 — Non-vacuous freeze checks

### Ignored DLI family

Canonical fingerprint:

- sorted relative `.md` paths
- SHA-256 of each document body
- SHA-256 of `manifest.json` bytes
- canonical serialization hash

Assert non-empty and compare pre/post.

### Ignored index DB

Compare pre/post:

- SHA-256
- size
- mtime

Open with SQLite URI `mode=ro`.

### Tracked golden family

- regenerate and byte-compare
- compare bytes to `git show HEAD:<path>`

### Tracked frozen code

Use `git diff --quiet HEAD --` only for tracked files. Do not apply it to `corpus/dli` or `corpus/index.db`.

### Vault schema

Pin:

- `PRAGMA user_version == 3`
- sorted table/index fingerprint:
  `9b35bc925c4ee39216980d4f74b937cd0b971c4f423116f1b84bf6bdb561fe50`

### Dependencies

- exact existing dependency set
- `poetry.lock` SHA-256:
  `6f5d47b3cfd2f78e6b796936b35ce2a3d2078447e0b61953e65114de71af3ef5`
- tracked diff clean for `pyproject.toml` and `poetry.lock`

No pyproject marker edit is needed.

## Negative Matrix Assignment

| Matrix class | Primary owner |
|--------------|---------------|
| extraction/pending/confirm/correct/reject/quality/staleness | 44-01 + 44-04-02 |
| resolver invalid matrix | 44-02 + 44-04-01 |
| static + transient Registry, shared gate, one-row-per-chunk, tamper failures | 44-03-01 + 44-04-02 |
| exact DLI, PGWP, common crawl_date/as_of, dates, current-only cap | 44-03-01 + 44-04-02 |
| credential-only real grid seam | 44-03-02 + 44-04-02 |
| public/private CLI projection | 44-04-01 + 44-04-02 |
| family/DB/schema/dependency/frozen factors | 44-04-02 |

## File Ownership and Waves

| Wave | Plan | Exclusive production ownership |
|------|------|--------------------------------|
| 1 | 44-01 | dlifields, vault model, extraction |
| 1 | 44-02 | snapshot_policy, freshness/static tests |
| 2 | 44-03 | study_review, study_dli row, strengthened shared gate, additional decider |
| 3 | 44-04 | CLI and final conformance |

`test_study_review.py` is sequentially shared by 44-01 then 44-03; the dependency makes that safe. Same-wave plans have no file overlap.

## Anti-Patterns

- sidecar calls the config resolver
- config checked after index probe
- fuzzy institution search
- hard-coded static public DLI citation
- static UofT row used as runtime candidate evidence
- dynamic candidate rows persisted or written to YAML
- `resolve`/custom substring/hash result treated as authoritative instead of `gate_subset`
- a second sidecar validation engine
- as_of taken from wall clock, manifest, static row, or only one consumed chunk
- public `citations` field
- current designation treated as historical
- `Details` treated as Yes
- DLI/R73 claimed to reach `DecisionContext`
- normal study evidence linked to `additional.study`
- git diff used on ignored corpus/index
- schema checked only by “no migration file”
- pyproject edited just to rename marker help
- Phase-45 wiring or legal/eligibility conclusion
