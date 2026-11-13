# Stack Research

**Domain:** v5.0 Grounded Eligibility & Policy Edge-Case Screening — extend the shipped, 851-test, local-first, PII-safe, corpus-grounded post-ITA Express Entry auditor beyond CRS *substantiation* into deterministic, authoritative-source-grounded *screening* for program eligibility (FSW/FST/CEC MEC), legacy/physician arranged-employment, DLI/PGWP study evidence (via a refreshable local snapshot), enhanced NOC work-duty review (human-confirmed), and cross-cutting effective-date/freshness/drift handling — with no new trust path, no legal advice, and PII vault-only.
**Researched:** 2026-07-17
**Confidence:** HIGH (this is a data + deciders milestone over an already-shipped stack whose rule model *already carries* effective-date/policy-flag/volatility machinery; every capability maps to existing, tested modules. The one genuinely-new input — the DLI list — is a single authoritative IRCC JSON dataset that fits the shipped "structured dataset → front-matter markdown → FTS5 index" pattern verbatim and was fetched + schema-verified live.)

## Executive Recommendation

**Add nothing to the runtime dependency graph. Ship v5.0 on the exact three-dependency stack that shipped v4.0/v4.1** (`pyyaml`, `pydantic`, `platformdirs` — verified below as the *only* entries in `[project].dependencies`). All five v5.0 capabilities are **grounded YAML data + deterministic Python deciders + one new corpus family (a pinned DLI snapshot)** over primitives that already exist, are already tested, and are already inside the PII / publish-safe perimeter.

The decisive finding is that **the hard machinery v5.0 appears to "need" is already shipped and unused-or-underused:**

- The CRS rule model (`crawler/models/crs_rules.py`) **already** carries `check_type: policy`, `MachineCheckKind.policy_flag`, `MachineCheck.effective_from/effective_to/window_days`, and a `VolatilityMeta` block with `volatility` / `crawl_date` / `effective_from` / `effective_to`. Effective-date/freshness metadata is a *field that already exists*, not a schema to invent.
- The arranged-employment resolver is **already** effective-date-driven and fail-closed: `crs_audit.arranged_employment_guard` reads the grounded current-repeal date (`2025-03-25`) and the legacy row's grounded window, and returns `AT-RISK` with `points is None` (manual legacy resolution) for an in-window legacy claim — it never auto-awards. `decide_job_offer` already emits `arranged_employment_legacy_manual`.
- The corpus **already** contains the FSW/FST/CEC PDIs that carry the MEC facts (`corpus/pr-pdi/economic-classes-federal-skilled-workers-assessing-applications-against-minimum-requirements.md`, `…-selection-criteria*.md`, `…-making-selection-decision.md`, plus CEC/FST equivalents and `corpus/guidance/{federal-skilled-workers,federal-skilled-trades,canadian-experience-class}.md`) — MEC needs **new grounded rows over the existing corpus, not a new crawl**.
- The physician arranged-employment public policy is **already** in the corpus (`corpus/guidance/job-offer.md` §"If you're a physician with a job offer in Canada" — the temporary public policy, "for arranged employment under the FSWP selection factors").
- The **376-unit-group NOC 2021 family** (`corpus/noc-2021/`, `source_type: noc`, `teer`, lead statement + main duties) is already indexed — NOC-duty review grounds a claimed unit group's *verbatim official duties* and leaves fit `AT-RISK` for human confirmation. `remediation.py` already ships an `unresolved_noc` reason code and `SCREENING_NOTICE` already scopes "NOC-duty fit … stays AT-RISK."
- `searchindex.build_index` enumerates the **entire live corpus** (`dupaudit.live_docs` sorted `rglob`) and mints `relpath#ordinal` chunk ids with per-chunk `crawl_date` + `source_type` from front matter — so a **new `corpus/dli/` family is auto-indexed and auto-grounded with zero indexer code change**.

**The single new build is the DLI/PGWP snapshot, and it is a solved pattern.** The authoritative DLI list is a single IRCC-published JSON dataset — `https://www.canada.ca/content/dam/ircc/documents/json/dli/dli-full-list.json` (~432 KB, **1,454 records**, each `{Province, Institution, "DLI #", City, Campus, "Grad Program", PGWP, HTML, "Public/Private"}` — the `PGWP` field is a literal `"Yes"/"No"` PGWP-eligibility flag and `"DLI #"` is the `O#########` designation number). This is the exact analogue of the shipped **NOC 2021 StatCan-CSV → per-unit-group front-matter markdown** ingestion (`generator: statcan-noc-csv`). A tiny **refresh-time** generator (stdlib `urllib.request` + `json` + `hashlib`, **no browser, no crawl4ai, no new dep**) turns that JSON into per-institution `corpus/dli/*.md` docs with a `crawl_date` stamp, which `build_index` then indexes into the frozen FTS5 store. **The audit-time path never touches the network** — it queries the local snapshot exactly like any other corpus family.

**Zero new runtime dependencies is the headline, verified module-by-module below.** The only `pyproject.toml` edits that may be justified are **non-dependency metadata** (a new pytest `conformance` sub-marker for the v5.0 SAFE gate; optionally new `argparse` verbs). The temptations to reject are the same discipline as v4.1 plus two milestone-specific ones: **(a) an HTTP-at-audit-time client** (breaks the frozen local-corpus trust path — the whole point of a *snapshot*), and **(b) a rules engine / a third-party date library** (stdlib `datetime` already does every effective-date comparison; a "policy DSL" would fork a second trust path around the grounded registry).

## Recommended Stack

### Core Technologies

| Technology | Version (locked) | Purpose in v5.0 | Why Recommended |
|------------|------------------|-----------------|-----------------|
| Python | `>=3.10,<4.0` (unchanged) | Runtime for all new deciders, generators, field vocabularies | No v5.0 capability needs a newer floor or new runtime feature. |
| `pydantic` | 2.13.4 (pydantic-core 2.46.4) | Typed boundary rows for the new MEC/DLI/NOC/policy grounded rules; the DLI snapshot record model; any new PII-bearing decision result | `RuleRow`/`MachineCheck`/`VolatilityMeta` (extra=forbid, `Literal` enums, `relpath#ordinal` citation shape, `citation_index` range guard) already model *exactly* the policy-date + policy-flag + points-table shapes v5.0 needs. New screens are **more rows of an existing model**. |
| `pyyaml` | 6.0.3 | Source format for the new grounded rule files (`mec.yaml`, `study_dli.yaml`, extended `additional.yaml` policy rows) | The registry is already PII-free repo-safe YAML compiled into pydantic rows and re-validated through the shipped grounding gate; MEC/DLI/policy rules are new YAML rows, not new machinery. |
| SQLite / `sqlite3` (FTS5) | stdlib (validated) | (a) Corpus index for the new `corpus/dli/` family + MEC/NOC grounding; (b) additive vault fields for new confirmed inputs (DLI number, program, claimed program stream, MEC inputs) | The corpus index auto-includes any new family (no DDL). New vault fields are an **additive `PRAGMA user_version` migration** — the shipped v1→v2→v3 pattern (`crawler/vault.py::_migrate`). Local, offline, PII-safe. |
| `platformdirs` | 4.10.0 | Vault-root + corpus-root resolution for the new snapshot family and any new vault artifacts | Already the shared `crawler/paths.py` fallback; unchanged. |
| `argparse` | stdlib | New CLI verbs (e.g. `corpus refresh-dli`, `vault screen-mec`, `vault noc-review`) and the v5.0 SAFE release-gate verb | The shipped CLI is a **stdlib `argparse` subparser tree, not typer/click** — new verbs extend `vsub.add_parser(...)` and emit the frozen five-key `--json` envelope. |
| `datetime` (stdlib) | stdlib | Every effective-date / freshness / supersession comparison (repeal windows, snapshot staleness, MEC dated criteria) | `crs_audit.py` already does all date math with `from datetime import date, timedelta` (`age_on_date`, `within_validity`, `_in_window`). **No third-party date library is present or needed.** |
| `urllib.request` + `json` + `hashlib` (stdlib) | stdlib | **Refresh-time only:** fetch the IRCC DLI JSON, content-address/version it, and generate the pinned `corpus/dli/*.md` snapshot | A static JSON/CSV fetch needs no browser and no `httpx` (which is **transitive-only** via the optional `crawl` extra). Mirrors the NOC-CSV generator's zero-dependency, offline-reproducible ingestion. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `hashlib` (`sha256`) | stdlib | Snapshot content-hash / provenance id + refresh idempotency; registry fingerprint (`crs_rules.registry_fingerprint`) covering the new rows; the five-key staleness scheme for new confirmed fields | Reuse everywhere; no new hashing dep. A DLI snapshot's content hash is its version stamp; a changed hash means "refreshed" and is diffable. |
| `re` (stdlib) | stdlib | Fail-closed accepted-token canonicalizers for new confirmed-input field vocabularies (NOC code, DLI number, program stream, MEC flags) | The exact `crawler/siblingfields.py` / `crawler/testtypes.py` pattern: case/space-folding alias maps keyed on closed enums, pinned by anti-drift tests, **never coercing an unknown surface form to an accepted token**. |
| `pypdfium2` / `Pillow` / `pdfminer.six` | 5.11 / 12.3 / 20260107 (existing `doc-extract` extra) | Only relevant if new confirmed inputs (e.g. a DLI enrolment letter, a NOC reference letter) are extracted from applicant PDFs | No version change, no new code path — extraction stays the shipped quarantine (`crawler/extraction.py`) behind the OPTIONAL extra; new fields are `_FIELD_SPECS` entries + a vocabulary, not new deps. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` (+ `conformance` marker) | Extend the SAFE release gate (`scripts/run_conformance.py`, `test_conformance_v4x_*`) to prove: a stale/superseded rule never greens; a snapshot older than its freshness bound refuses/AT-RISKs; MEC/NOC/DLI deciders fail closed; the DLI snapshot grounds verbatim | Register a v5.0 sub-marker if the suite grows one (metadata, not a package). New proofs must be non-vacuous (grounded on the real corpus + a real snapshot fixture). |
| `scripts/check_publish_safe.py` | Confirm the new `corpus/dli/` snapshot is **PII-free and repo-shareable** (institution/DLI-number/PGWP flag are public facts, not applicant PII) and that any new vault artifacts stay inside the allow-listed vault subtrees | The DLI snapshot is public corpus data (like NOC), so it lives in the git-ignored `corpus/` beside the other families; applicant program/enrolment values stay vault-only. Extend `VAULT_SUBTREES` only if a new vault artifact type lands. |
| `ruff` | Lint/format | Existing; no change. |
| `no_inlined_volatile_rules` static gate (`crawler/crs_rules.py`) | Keep every new volatile number (MEC thresholds, study points, policy dates) in a grounded row's `machine_check`, never inlined in Python/prose | The gate already scans `crawler/auditors/`; the new MEC/NOC deciders must stay literal-free and read all numbers from grounded rows. |

## The DLI/PGWP Snapshot Mechanics (concrete, offline-reproducible — capability #3)

**Where the facts live authoritatively:**

| Fact | Authoritative source | Nature | v5.0 handling |
|------|----------------------|--------|---------------|
| Is `<institution/campus>` a DLI? Its `O#########` DLI number? Does it offer PGWP? | **`https://www.canada.ca/content/dam/ircc/documents/json/dli/dli-full-list.json`** (the data source behind the IRCC "Designated learning institutions list" page) | Single ~432 KB JSON, `{"data":[{Province, Institution, "DLI #", City, Campus, "Grad Program", PGWP, HTML, "Public/Private"}, …]}`, 1,454 rows | Refresh-time generator → pinned `corpus/dli/*.md` snapshot family, indexed by FTS5, grounded by `relpath#ordinal` |
| Program-level PGWP eligibility (field-of-study, program length, delivery) | IRCC PGWP guidance + `corpus/pr-pdi/economic-classes-experience-education-requirement-post-graduation-stream.md` (already crawled) | HTML guidance | Grounded rows over existing/refreshed guidance; **semantic "does the applicant's specific program qualify" stays human-confirmed / AT-RISK** |
| Canadian-study CRS additional points (15/30 by credential length) | `corpus/guidance/crs-criteria.md#019` | Already grounded (`additional.study` row) | Existing decider `decide_study`; v5.0 adds a **DLI/PGWP eligibility precondition** grounded on the snapshot |

**Refresh → snapshot → ground pipeline (all stdlib, all offline after fetch):**

1. **Refresh (crawler side, network — run on demand, never during audit):** a new generator (e.g. `crawler/dli_snapshot.py` or a `corpus refresh-dli` verb) fetches the JSON with stdlib `urllib.request`, records the fetch timestamp as `crawl_date`, and content-hashes the payload (sha256) as the snapshot version.
2. **Generate (pure function):** emit one front-matter markdown doc per DLI number (campuses folded, or one per campus row) under `corpus/dli/`, e.g. `corpus/dli/o242632228347.md`, with front matter mirroring the NOC family:
   ```yaml
   ---
   url: "https://www.canada.ca/content/dam/ircc/documents/json/dli/dli-full-list.json"
   title: "DLI O242632228347 - ABM College of Business and Technology (Calgary, AB)"
   source_type: "dli"
   dli_number: "O242632228347"
   province: "Alberta"
   pgwp: "No"
   crawl_date: "2026-07-17T00:00:00Z"      # snapshot refresh time = freshness key
   label: "Source: IRCC (canada.ca) Designated Learning Institutions list, reproduced for personal non-commercial use; verify against the live list."
   generator: "ircc-dli-json"
   ---
   # DLI O242632228347 — ABM College of Business and Technology
   **DLI number:** O242632228347
   **Province:** Alberta   **City/Campus:** Calgary / Calgary
   **Offers PGWP:** No
   **Institution type:** Private institution
   ```
   The body carries the **verbatim** authoritative strings a grounded rule row will quote (DLI number, PGWP flag) so the grounding gate can prove a verbatim substring match.
3. **Index (unchanged):** `corpus-crawler --json index` (`searchindex.build_index`) auto-enumerates the new family and mints `dli/o242632228347.md#000` chunk ids carrying `crawl_date` + `source_type: dli`. **No indexer change.**
4. **Ground (unchanged trust path):** a grounded rule row (`selector.family: dli`, a `marker` = the DLI number, a verbatim `quote` of the PGWP flag) resolves through `search → --cite → grounding gate` exactly like any CRS rule. A DLI/PGWP screen decider reads the applicant's **confirmed** DLI number (a new vault field + fail-closed vocabulary) and looks up the grounded snapshot fact; a non-DLI / non-PGWP institution → `GAP`/`AT-RISK`, never green.

**Why this is not a live lookup:** the audit reads only the local `corpus/index.db`; the snapshot is pinned, content-addressed, and citable; a re-run over the same snapshot is byte-identical. A live remote lookup at audit time would (a) break the frozen local-corpus trust path, (b) make results non-reproducible, (c) risk greening from unpinned data, and (d) put a network dependency in the fail-closed path. The refresh is a **separate, explicit operator action** with its own provenance stamp.

## Cross-Cutting Effective-Date / Freshness / Drift + SAFE (capability #5)

**All primitives exist; v5.0 wires them into a screen-wide invariant.**

| Concern | Existing primitive | v5.0 use |
|---------|--------------------|----------|
| Policy effective window (repeal / physician public policy / MEC dated criteria) | `MachineCheck.effective_from/effective_to`, `VolatilityMeta.effective_from/effective_to`, `crs_audit._in_window`, `CheckType: policy`, `MachineCheckKind: policy_flag` | New/extended grounded policy rows carry the dates; deciders compare against the ITA/reference date with stdlib `datetime`; **out-of-window or superseded ⇒ not green** |
| Snapshot / corpus freshness | Per-chunk `crawl_date` in the FTS5 index (from front matter) + the five-key staleness scheme + `crawler/index_health.py` read-only preflight | A screen consults `crawl_date` on the grounded snapshot chunk; a snapshot older than a grounded freshness bound (or a missing/corrupt index) ⇒ fail-closed refusal/AT-RISK, artifact-free (reuse `AuditGroundingError` + the shipped `index_health` refusal) |
| Rule/registry drift between audit and downstream projection | `crs_rules.registry_fingerprint` (already stamps the report; `vault remediate` fails closed on drift) | The new rows extend the fingerprint automatically; the SAFE gate proves a drifted/stale rule cannot re-green a completed run |
| "Stale can never green" conformance | `scripts/run_conformance.py` SAFE-01..08 series | Add SAFE proofs: superseded policy row + in-pool candidate ⇒ AT-RISK; expired snapshot ⇒ refusal; unaudited/unwired new factor ⇒ `_default_decider` AT-RISK (elevation-of-privilege guard already enforced) |

## Installation

**No `poetry add`. No `pyproject.toml` dependency change. No `poetry.lock` churn.** v5.0 ships on the locked graph as-is:

```bash
# Nothing to install for the core v5.0 screens, deciders, grounded rules, or the DLI snapshot generator.
poetry install

# Refresh the DLI snapshot on demand (stdlib fetch; never during an audit):
poetry run corpus-crawler --json refresh-dli          # (new verb) → writes corpus/dli/*.md
poetry run corpus-crawler --json index                # rebuild FTS5 over the corpus (incl. dli/)

# Optional extraction of applicant enrolment/reference PDFs uses the ALREADY-DECLARED extras (unchanged):
poetry install --extras "doc-extract"                 # pypdfium2 + Pillow + pdfminer.six (existing)
poetry install --extras "ocr"                         # pytesseract (existing; needs local Tesseract)
```

## Zero-New-Dependency Verification (module-by-module, per capability)

`[project].dependencies` in `pyproject.toml` is verified to be **exactly** `pyyaml>=6.0,<7.0`, `pydantic (>=2.13,<3.0)`, `platformdirs (>=4.10,<5.0)`. Everything else in `poetry.lock` (crawl4ai, litellm, playwright/patchright, openai, jinja2, typer, click, cryptography, httpx, numpy, nltk, …) is **transitive-only via the optional `crawl` / `doc-extract` / `ocr` extras** and must not be relied on in core runtime code.

| # | v5.0 capability | Realized as (named modules/data) | New dependency? |
|---|------------------|----------------------------------|-----------------|
| 1 | **MEC sidecar screening (FSW/FST/CEC)** | New grounded rows `crawler/data/crs_rules/mec.yaml` (pydantic `RuleRow` over the **existing** `corpus/pr-pdi/economic-classes-*` + `corpus/guidance/{fsw,fst,cec}` docs) + new decider module `crawler/auditors/mec.py` registering MEC factor ids on the existing `register`/`resolve` spine + a MEC "sidecar" verdict projection; fail-closed `_default_decider` (AT-RISK) for any unwired MEC factor | **No** |
| 2 | **Legacy / physician arranged-employment resolver** | Extend `crawler/data/crs_rules/additional.yaml` policy rows (`additional.job_offer.legacy` exists; add a grounded **physician public-policy** row citing `corpus/guidance/job-offer.md`) consumed by the **existing** `crs_audit.arranged_employment_guard` + `auditors/additional.decide_job_offer` (already effective-date-driven, already `arranged_employment_legacy_manual` → `points is None`, never auto-award) | **No** |
| 3 | **DLI/PGWP eligibility via refreshable local snapshot** | New refresh-time generator `crawler/dli_snapshot.py` (stdlib `urllib.request`+`json`+`hashlib`) → new `corpus/dli/*.md` family → **unchanged** `searchindex.build_index` → new grounded row(s) `crawler/data/crs_rules/study_dli.yaml` (`selector.family: dli`) → new decider extending `auditors/additional.decide_study` + a new confirmed vault field (`dli_number`, additive migration) + a fail-closed vocabulary (`crawler/dlifields.py`, the `siblingfields.py` pattern) | **No** |
| 4 | **Enhanced NOC work-duty review (human-confirmed)** | Grounded rows over the **existing** `corpus/noc-2021/noc-XXXXX.md` family (verbatim lead statement + main duties) + a new structured review decider (`auditors` NOC-duty factor) that presents cited official duties and stays **AT-RISK** (`unresolved_noc` already in `remediation.py`); confirmed `noc_code` field already extracted (`extraction.py` `noc` kind); **no NLI/model/vector** | **No** |
| 5 | **Effective-date / freshness / drift + SAFE conformance** | **Existing** `MachineCheck.effective_from/to`, `VolatilityMeta`, `crs_audit._in_window`, per-chunk `crawl_date`, `index_health.py` refusal, `registry_fingerprint` drift guard, `scripts/run_conformance.py` — wired into a screen-wide "stale/superseded never greens" invariant + new SAFE proofs | **No** |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Pinned local DLI **snapshot** (stdlib fetch → `corpus/dli/` → FTS5) | Live remote DLI lookup at audit time (`httpx`/`requests`) | **Never for this milestone.** It breaks the frozen local-corpus trust path, makes audits non-reproducible, and risks greening from unpinned data. A live lookup is only defensible in a hypothetical online-first product with a different trust model. |
| stdlib `urllib.request` for the refresh fetch | `httpx` / `requests` (both in the lock, transitive-only) | Only if the refresh ever needs streaming/HTTP-2/retry policy the stdlib can't express cheaply — unlikely for a 432 KB static JSON. Adopting either promotes a transitive dep to a hard one. |
| Grounded `RuleRow` + stdlib `datetime` for policy dates | A rules-engine / policy-DSL (`durable-rules`, `business-rules`, a homegrown interpreter) | **Never.** It forks a second trust path around the grounded registry and the `no_inlined_volatile_rules` gate. Every dated policy is already a grounded row with `effective_from/to` compared by stdlib `datetime`. |
| stdlib `datetime` | `python-dateutil` / `arrow` / `pendulum` | Never — all v5.0 date math is inclusive `date` comparison and window arithmetic the stdlib already does (`age_on_date`, `within_validity`, `_in_window`). |
| DLI snapshot as a **corpus family** (public, git-ignored `corpus/`, indexed, grounded) | DLI facts as a **vault** table or an ungrounded JSON blob read directly by a decider | Never — the DLI list is public authoritative data (like NOC); reading it outside the grounding gate would create an ungrounded fact source. Ground it like every other corpus fact. |
| New `argparse` verbs on the shipped tree | `typer` / `click` (lock, transitive-only via `crawl`) | Never — reusing them for core CLI silently makes the heavy `crawl` extra mandatory. |
| Human-confirmed NOC-duty review (cited duties, AT-RISK) | Semantic NOC/duty entailment (NLI/embeddings/LLM) | Never — VAL-02 is explicitly out of scope; a model breaks the no-model/no-vector/no-cloud constraint and is fail-open. Present grounded duties, let a human confirm, keep AT-RISK. |

## What NOT to Use (explicit — for the roadmapper)

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **HTTP-at-audit-time client** (`httpx`/`requests`/`aiohttp`) in the audit path | Breaks the frozen local-corpus trust path; non-reproducible; can green from unpinned data; puts a network dep in the fail-closed path | Refresh a **pinned local snapshot** out-of-band (stdlib `urllib` at refresh time); audit reads only `corpus/index.db` |
| **A rules engine / policy DSL** | Forks a second trust path around the grounded registry + `no_inlined_volatile_rules` gate; volatile dates/thresholds escape grounding | Grounded `RuleRow.machine_check` (`policy_flag`, `effective_from/to`) + deterministic deciders + stdlib `datetime` |
| **A third-party date library** (`dateutil`/`arrow`/`pendulum`) | Nothing in v5.0 exceeds stdlib inclusive-date + window math already shipped in `crs_audit.py` | stdlib `datetime` (`date`, `timedelta`) |
| **ML / NLI / embeddings / vector index / cloud semantic** for NOC-duty or ambiguous policy fit | Violates the no-model/no-vector/no-cloud constraint; fail-open; VAL-02 is out of scope | Cited verbatim duties from `corpus/noc-2021/`, human-confirmed, verdict stays AT-RISK |
| **A PDF renderer / templating engine** (`reportlab`/`weasyprint`/`jinja2`) for screen reports | Cosmetic; `jinja2` is transitive-only via the `crawl` extra | f-string / `"\n".join(lines)` rendering (the shipped `audit_report.py` pattern) + `json` |
| **`typer` / `click`** for new CLI verbs | Transitive-only via the `crawl` extra; shipped CLI is stdlib argparse | Extend the `argparse` subparser tree; emit the frozen five-key `--json` envelope |
| **A separate DLI datastore / second index** | A second retrieval path outside the grounding gate is an ungrounded fact source | The DLI snapshot is a normal `corpus/` family in the one FTS5 index, grounded by `relpath#ordinal` |
| **A second trust path / re-grounding inside new deciders** | Any parallel grounding engine widens the guarantee silently | Reuse `search → --cite → grounding gate → typed envelope`; new deciders consume gated grounded rows only |
| **Storing DLI/MEC applicant inputs anywhere but the vault** | PII in the repo/corpus | Additive `PRAGMA user_version` vault fields + fail-closed vocabularies; snapshot facts (public) in `corpus/dli/`, applicant program/enrolment values in the vault |

## Stack Patterns by Variant

**If a v5.0 screen needs a volatile external fact (DLI number, PGWP flag, program list):**
- Ingest it as a **pinned local snapshot corpus family** via a stdlib refresh generator, index it with the existing FTS5 builder, and ground it with a `RuleRow` — never a live lookup.
- Because grounding must stay reproducible, offline, citable, and inside the one trust path.

**If a v5.0 fact is dated (repeal, public policy, MEC criterion effective date):**
- Carry the date in the grounded row's `machine_check.effective_from/effective_to` (or `VolatilityMeta`), and decide applicability by comparing the ITA/reference date with stdlib `datetime` (`_in_window`).
- Because a policy date must be grounded metadata, never a prose/Python literal (the `no_inlined_volatile_rules` gate enforces this).

**If a v5.0 judgment is semantic (NOC-duty fit, ambiguous legacy/physician policy):**
- Present the grounded, cited authoritative text and leave the verdict **AT-RISK** for human confirmation; route it into `remediation.py` / the review packet.
- Because semantic auto-resolution needs a model — out of scope and fail-open.

**If a new confirmed applicant input is required (DLI number, program stream, MEC flags):**
- Add an additive `PRAGMA user_version` vault field + a fail-closed accepted-token vocabulary (the `siblingfields.py`/`testtypes.py` pattern) pinned by an anti-drift test; gate audit on the `is_audit_eligible` choke point.
- Because a new evidence type must pass the same confirm-first, fail-closed quarantine as every existing field.

**If the DLI snapshot (or corpus index) is missing / stale / corrupt at audit time:**
- Preflight via `index_health` read-only open + a freshness check on the grounded snapshot's `crawl_date`; on failure raise `AuditGroundingError` and refuse with a stable, PII-free reason code, writing zero artifacts.
- Because a stale/absent grounding prerequisite is a fail-closed refusal, never a green result or a traceback.

## Version Compatibility

| Package | Version (locked) | Compatible With | Notes |
|---------|------------------|-----------------|-------|
| `pydantic` | 2.13.4 (pydantic-core 2.46.4) | Python `>=3.10,<4.0` | New MEC/DLI/policy rows reuse the shipped v2 idioms (`ConfigDict(extra="forbid")`, `Literal`, `field_validator`, `model_validator`). |
| `pyyaml` | 6.0.3 | Python `>=3.10` | MEC/DLI/policy rules are plain YAML compiled into pydantic rows and re-validated through the grounding gate. |
| `platformdirs` | 4.10.0 | Python `>=3.10` | Vault/corpus root resolution unchanged for the new family + fields. |
| SQLite / `sqlite3` (FTS5) | stdlib | Python `>=3.10` | New `corpus/dli/` family auto-indexes; new vault fields via additive `PRAGMA user_version` migration (shipped v1→v3 pattern). |
| `datetime` / `urllib.request` / `json` / `hashlib` / `re` | stdlib | Python `>=3.10` | All effective-date math, snapshot refresh, provenance hashing, and field canonicalization are stdlib. |
| `pypdfium2` / `Pillow` / `pdfminer.six` | 5.11 / 12.3 / 20260107 | project `>=3.10,<4.0` | Unchanged; OPTIONAL `doc-extract` extra, touched only if new applicant PDFs are extracted. |

**Transitive-only packages that must NOT be treated as available for core runtime:** `httpx`/`requests`/`aiohttp` (network), `crawl4ai`/`playwright`/`patchright` (browser), `litellm`/`openai`/`tiktoken`/`nltk`/`numpy` (ML), `jinja2`, `typer`, `click`, `cryptography` — all reachable only via the optional `crawl` / `doc-extract` / `ocr` extras. Relying on any in core v5.0 code would silently promote a heavy optional extra to a hard dependency.

## Sources

- **Codebase inspected (integration points + zero-new-dep proof) — HIGH (curated, first-party):**
  `pyproject.toml` (verified `[project].dependencies` = exactly pyyaml/pydantic/platformdirs; extras crawl/doc-extract/ocr) + `poetry.lock` (transitive-only typer/click/jinja2/cryptography/httpx/crawl4ai/litellm); `crawler/models/crs_rules.py` (`RuleRow`/`MachineCheck` with `policy_flag`+`effective_from/to`+`window_days`, `VolatilityMeta`, `CheckType: policy`, `relpath#ordinal` citation shape, `citation_index` range guard); `crawler/crs_rules.py` (`load_registry`, `validate_registry` via the shipped gate, `registry_fingerprint`, `no_inlined_volatile_rules`, `_select_chunk` deny-families); `crawler/data/crs_rules/additional.yaml` (`additional.job_offer.current`/`.legacy` effective-date rows, `additional.study`); `crawler/crs_audit.py` (`arranged_employment_guard`, `_in_window`, `age_on_date`, `within_validity`, stdlib `datetime`); `crawler/auditors/__init__.py` (`register`/`resolve`/`_default_decider` AT-RISK, `DecisionContext/Result`, `FULL_GRID_FACTORS`) + `crawler/auditors/additional.py` (`decide_job_offer` legacy-manual, `decide_study`, `decide_sibling`); `crawler/searchindex.py` (`build_index` auto-enumerates the live corpus, per-chunk `crawl_date`/`source_type`, `relpath#ordinal`); `crawler/pipeline.py`/`deepcrawl.py` (front-matter doc writer, `generator` field); `crawler/vault.py` (`PRAGMA user_version` v1→v3 additive migrations); `crawler/siblingfields.py`/`testtypes.py` (fail-closed field vocabulary + anti-drift pattern); `crawler/extraction.py` (`noc_code` `noc` kind); `crawler/remediation.py` (`unresolved_noc` + reason-code map); `crawler/audit_report.py` (`SCREENING_NOTICE`); `crawler/index_health.py` (read-only preflight refusal); `scripts/check_publish_safe.py`, `scripts/run_conformance.py`.
- **Corpus inspected (facts already grounded vs. genuinely new) — HIGH (curated, first-party):**
  `corpus/pr-pdi/economic-classes-federal-skilled-workers-assessing-applications-against-minimum-requirements.md` + `…-selection-criteria*.md` + `…-making-selection-decision.md` + CEC/FST equivalents (MEC facts present); `corpus/guidance/{federal-skilled-workers,federal-skilled-trades,canadian-experience-class,job-offer,crs-criteria,category-based-selection}.md` (MEC/physician-public-policy/study-points present); `corpus/noc-2021/` (376 unit groups, duties present); confirmed the DLI **list is NOT yet in the corpus** (the one new family).
- **Authoritative external source fetched + schema-verified live — HIGH for "this dataset exists with these fields now" (it is the IRCC primary source the project designates authoritative), but endpoint/schema can drift — which is exactly why the design pins a versioned snapshot with `crawl_date`; the generic web-fetch confidence tier is LOW, so this fact is treated as *refreshable*, not eternal:**
  `https://www.canada.ca/content/dam/ircc/documents/json/dli/dli-full-list.json` (referenced from the IRCC "Designated learning institutions list" page; fetched ~432 KB, 1,454 records, fields `Province/Institution/"DLI #"/City/Campus/"Grad Program"/PGWP/HTML/"Public/Private"`); arranged-employment repeal date `2025-03-25` and physician public policy cross-checked against `corpus/guidance/job-offer.md`.
- **Prior research built upon (not repeated) — HIGH:** `.planning/research/STACK-v4.1.md` (the "add nothing" module map + transitive-only anti-stack), `.planning/research/SUMMARY-v4.1.md`; `.planning/PROJECT.md` (v5.0 Current Milestone + Key Decisions), `.planning/ROADMAP.md` (LATER-01..04 deferrals now promoted).

---
*Stack research for: v5.0 Grounded Eligibility & Policy Edge-Case Screening (reuse-first; zero new runtime dependencies; one new pinned-snapshot corpus family via stdlib).*
*Researched: 2026-07-17*
