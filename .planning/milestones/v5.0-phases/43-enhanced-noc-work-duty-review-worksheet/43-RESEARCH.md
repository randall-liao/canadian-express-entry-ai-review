# Phase 43: Enhanced NOC Work-Duty Review Worksheet - Research

**Researched:** 2026-07-19
**Domain:** Grounded NOC-2021 duty worksheet + per-duty human-confirmation surface, capped at `AT-RISK`, feeding MEC (Phase 45) without touching the frozen CRS total
**Confidence:** HIGH

## Summary

Phase 43 adds a **structured, cited NOC-2021 duty worksheet** and a **per-duty confirm/correct/reject surface** that reuses the shipped extraction-quarantine / staleness / vault machinery **verbatim** and produces an `AT-RISK`-capped duty-review signal — never an automated `SUBSTANTIATED`. The domain is almost entirely *internal*: the NOC-2021 corpus family (`corpus/noc-2021/`, 376 unit-group files, TEER 0/1/2/3 only) is already crawled, pinned, indexed, and per-section chunked with resolvable `chunk_id`s; the grounded duty-match *rule* (IRCC R87.1(2)(b)/(c)) is already in the corpus (`pr-pdi/economic-classes-experience-qualifying-work-experience.md`). There is **no new external technology, no new dependency, and no schema migration** — the entire feature is a small number of new pure-stdlib modules plus one closed-enum vocabulary extension. `[VERIFIED: corpus/index.db + grep across corpus/noc-2021/]`

The load-bearing design insight: the NOC-2021 descriptions **do not flag which main duties are "essential,"** yet IRCC R87.1(2)(c) requires "a substantial number of the main duties, **including all the essential duties**." Whether a given applicant's work performed the lead-statement actions and a substantial number of the essential duties is an **irreducibly human / officer judgment**. This is precisely why NOC-03 caps the verdict at `AT-RISK`: present the cited lead statement + each main duty verbatim, capture a **binary human confirmation per duty**, and never compute a match score. `[VERIFIED: grep corpus/noc-2021 + corpus/pr-pdi/economic-classes-experience-qualifying-work-experience.md#003 + live canada.ca FSW page]`

The verdict/integration shape is a near-exact clone of the Phase-42 `crawler/policy_offer.py` **inert sidecar**: a pure module that returns a PII-light closed dict with an `AT-RISK`/`GAP`/`N/A`-only status, is **not** wired into the `crawler.auditors` dispatch, **not** in `FULL_GRID_FACTORS`, and **not** summed into any `PublicAuditEnvelope`. `core.work` stays **byte-for-byte frozen** (it already returns `AT-RISK unresolved_noc` when TEER is missing); duty confirmations never flip it green. Phase 45 (MEC) consumes the sidecar later as an `AT-RISK` human-confirmed skilled-work input. `[VERIFIED: crawler/policy_offer.py + crawler/auditors/core.py:334-389 + crawler/auditors/__init__.py]`

**Primary recommendation:** Ship (1) a **new closed-enum `FieldName` member `noc_duty`** (code-only, no migration); (2) a pure-stdlib **`crawler/noc_worksheet.py`** that resolves the *exact* claimed NOC's corpus chunks via `searchindex.resolve` (no BM25 fuzzy), deterministically splits the Main-duties chunk into per-duty items with stable IDs + `chunk_sha` fingerprints, writes a **vault-only** worksheet artifact, imports it as a `noc_worksheet` document, seeds a **dedicated inert `review.noc` profile-factor row** (the enforced FK parent — see **Open Questions Q5 → RESOLVED**), and creates one **born-pending** `ExtractedValue` per duty linked to `review.noc` (**never `core.work`**); (3) reuse the **existing `vault confirm`** verb for per-duty confirm/correct/reject; (4) a pure-stdlib **`crawler/noc_review.py`** inert sidecar (policy_offer clone) that reads the confirmed duty values via `vault.audit_eligible_values(v,'review.noc')` and rolls them up to `AT-RISK`/`GAP`/`N/A` (never `SUBSTANTIATED`), re-verifying each confirmed duty against the live corpus (retrieve-what-you-cite + `chunk_sha` drift). Everything else is frozen.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **NOC-01** | Applicant can view a structured, **cited** worksheet of the grounded NOC-2021 lead statement, main duties, and employment requirements for their claimed NOC, resolved from the corpus with resolvable citations. | Corpus is per-section chunked with resolvable `chunk_id`s: `#001` lead statement, `#002` main duties, `#003` employment requirements (see **Standard Stack** + **Code Examples §1**). Exact-claimed-NOC retrieval via `searchindex.resolve('noc-2021/noc-<code>.md#00X')` (no fuzzy match); absent NOC → `None` fail-closed. `[VERIFIED]` |
| **NOC-02** | Applicant confirms, **per duty**, whether their claimed work performed that duty; each confirmation captured as a vault field under the extraction-quarantine (confirm/correct/reject, staleness-keyed) — **no automated semantic entailment or keyword-overlap match scoring**. | One `ExtractedValue` per duty (new `FieldName='noc_duty'`), born `pending` via `vault.add_extracted_value`, confirmed via the shipped `vault confirm` verb; deterministic per-duty IDs + `chunk_sha`. No scoring anywhere (see **Architecture Patterns §2-§4**, **Don't Hand-Roll**). `[VERIFIED]` |
| **NOC-03** | Duty-review verdict stays `AT-RISK` until the human confirms the required duty match; can **never** reach `SUBSTANTIATED` by automated matching; unconfirmed/partial/stale confirmations remain `AT-RISK`/`GAP`. | Inert `noc_review` sidecar (policy_offer clone): `AT-RISK`/`GAP`/`N/A` only, structurally never `SUBSTANTIATED`; two-layer staleness (5-key `is_audit_eligible` + corpus `chunk_sha` drift re-check). `core.work` frozen. (See **Architecture Patterns §5**, **Pitfalls 1-3**.) `[VERIFIED]` |
</phase_requirements>

> **Note — no CONTEXT.md:** Phase 43 has no `*-CONTEXT.md` (config `skip_discuss: true`). Upstream constraints are taken from `REQUIREMENTS.md` "Standing constraints", the `ROADMAP.md` Phase-43 threat/privacy/grounding note, and the frozen invariants in `STATE.md`. These are treated with locked-decision authority and reproduced in **Project Constraints** below.

## Project Constraints (from copilot-instructions.md + REQUIREMENTS.md standing constraints)

These are non-negotiable and constrain every plan in this phase (authority equal to locked decisions):

- **PII vault-only, stdout PII-light.** Applicant per-duty answers, the worksheet artifact, and any raw duty text tied to a candidate stay inside the git-ignored vault; stdout `--json` carries only ids/counts/status/verdict. `[CITED: REQUIREMENTS.md L15]`
- **Authoritative sources only.** NOC content from the pinned `corpus/noc-2021/` StatCan family; the duty-match rule from IRCC PDI/IRPR corpus rows. No third-party/blog content. `[CITED: PROJECT.md Constraints]`
- **No new/second trust path.** Reuse the frozen `search → resolve/--cite → grounding-gate → JSON-envelope` pipeline. No new retrieval or grounding path. `[CITED: REQUIREMENTS.md L15]`
- **Prefer zero new dependencies.** Any addition needs strong justification + a supply-chain gate. This phase needs **none** — stdlib + already-present `pydantic`. `[CITED: REQUIREMENTS.md L15]`
- **No model / NLI / vector / cloud semantic auto-resolution; no keyword-overlap match scoring.** Present cited duties + capture a binary human confirmation only. `[CITED: REQUIREMENTS.md NOC-02 + Out-of-Scope table]`
- **Fail-closed verdicts.** Stale / superseded / out-of-window / unconfirmed **never greens**. `[CITED: REQUIREMENTS.md L15]`
- **No legal advice, no eligibility/outcome prediction.** Screening framing (`SCREENING_NOTICE`) on every rendered artifact. `[CITED: crawler/audit_report.py:54]`
- **No inlined volatile rules.** Duty text / lead statements / the R87.1 standard are read from grounded corpus spans, never inlined in code. `[CITED: STATE.md frozen invariants]`
- **Frozen contracts stay frozen.** `crawler/crs_audit.py`, `crawler/auditors/core.py::decide_work`, `PublicAuditEnvelope`, and the CRS `substantiated_total` must show **zero diff** vs HEAD. `[CITED: ROADMAP.md Phase-43 note + STATE.md]`

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Resolve claimed NOC → cited corpus spans (lead/duties/reqs) | Grounded corpus / retrieval (`searchindex.resolve`) | — | The one frozen grounding path; exact `chunk_id` lookup, fail-closed on miss. `[VERIFIED]` |
| Deterministic per-duty split + stable IDs + fingerprints | Worksheet generator (`noc_worksheet.py`, pure stdlib) | Corpus retrieval | Pure deterministic text op over the resolved chunk; no scoring, no model. |
| Worksheet artifact (cited, human-readable) | Vault (PII-adjacent, git-ignored) | Worksheet generator | Worksheet output is **vault-only**; imported as a `noc_worksheet` document to anchor staleness. |
| Per-duty pending values (quarantine) | Vault extraction store (`add_extracted_value`) | Worksheet generator | Reuse the born-`pending` quarantine invariant verbatim; no new store. |
| Per-duty confirm/correct/reject | Vault confirmation (`vault confirm`, shipped) | CLI | Reuse the shipped per-field decision; **no bulk confirm-all** (rubber-stamp defense). |
| Staleness / audit-eligibility of a duty confirmation | Vault trust predicates (`is_audit_eligible`, `is_stale`) | `noc_review` sidecar (corpus `chunk_sha` drift re-check) | Layer 1 = shipped 5-key gate; Layer 2 = corpus-drift re-check specific to NOC. |
| Duty-review verdict roll-up (`AT-RISK`/`GAP`/`N/A`) | Inert sidecar (`noc_review.py`, pure stdlib) | Vault predicates + retrieval | policy_offer clone: never `SUBSTANTIATED`, not in dispatch/grid/envelope. |
| CRS work verdict (`core.work`) | **FROZEN** — `crawler/auditors/core.py` | — | Stays `AT-RISK unresolved_noc`; duty confirmations never flip it green. Duty values live on the inert `review.noc` factor, never `core.work`, so `audit_eligible_values('core.work')` never returns one. |
| MEC skilled-work input | Phase 45 (consumer, out of scope here) | `noc_review` sidecar | Sidecar is the shipped, unit-tested contract Phase 45 reads as an `AT-RISK` input. |

## Standard Stack

**Zero new runtime dependencies.** The phase is built entirely from the standard library + modules and data already in the repo. This is the correct outcome — the dependency-light / no-second-trust-path constraints forbid additions here.

### Core (already present — reuse verbatim)
| Component | Where | Purpose | Why Standard |
|-----------|-------|---------|--------------|
| `crawler.searchindex.resolve(db, chunk_id)` | `crawler/searchindex.py:502` | Exact `chunk_id` → verbatim stored span (`{chunk_id, relpath, source_url, title, section, crawl_date, text}`); `None` on miss/drift | The frozen retrieval path; already fail-closed + tamper-guarded (recomputes `chunk_sha`, returns `None` on drift). `[VERIFIED]` |
| `crawler.searchindex.chunk_sha(text)` | `crawler/searchindex.py:128` | `sha1(text)[:12]` fingerprint | Deterministic per-duty + per-chunk drift fingerprint; already the corpus staleness primitive. `[VERIFIED]` |
| `crawler.grounding.quote_is_grounded(quote, chunk_text)` | `crawler/grounding.py:87` | Verbatim retrieve-what-you-cite check | Confirms a stored duty span is still present in the live corpus chunk. `[VERIFIED]` (returns `True` for a real duty span this session) |
| `crawler.vault.add_extracted_value(...)` | `crawler/vault.py:803` | Insert one **born-`pending`** value (quarantine invariant) | Pure sqlite/pydantic; validates `field_name` against the `FieldName` Literal at the boundary. Works on a lean install (no doc-extract deps). `[VERIFIED]` |
| `crawler.vault.record_extraction_run(...)` | `crawler/vault.py:728` | Mint an extraction-run row (stamps `parser_version` for SC4) | Pure sqlite; no heavy deps. `[VERIFIED]` |
| `crawler.vault.import_document(...)` | `crawler/vault.py:670` | Content-addressed vault document (`file_sha256`, `doc_type` free-text) | Anchors the worksheet artifact + its `file_sha256` staleness key. `doc_type` is a free-text TEXT column → `noc_worksheet` needs no migration. `[VERIFIED]` |
| `crawler.confirm.apply_decision` / `vault.confirm_value` | `crawler/confirm.py:119` / `crawler/vault.py:994` | Per-field confirm/correct/reject + capture the 5 staleness keys | The shipped per-duty decision surface; reused unchanged. `[VERIFIED]` |
| `crawler.vault.is_audit_eligible` / `is_stale` | `crawler/vault.py:1078` / `:1048` | The SC3/SC4 trust gate (confirmed/corrected + `quality_flag=='ok'` + not-stale) | The single choke point every duty confirmation must cross. `[VERIFIED]` |
| `crawler/policy_offer.py` (pattern) | `crawler/policy_offer.py` | Inert sidecar template | The exact shape for `noc_review`: closed PII-light dict, constant never-green status, unwired from dispatch/grid/envelope. `[VERIFIED]` |
| `pydantic` v2 | already in `[project].dependencies` | Boundary models / closed-enum vocabularies | Enforces the `FieldName` Literal fail-closed at the boundary. `[VERIFIED: pyproject.toml]` |

### Supporting (already present)
| Component | Where | When to Use |
|-----------|-------|-------------|
| `crawler.remediation._ACTION_TEMPLATES` | `crawler/remediation.py:68` | Add one generic `{factor}`-parameterized reason→action string for the duty-review finding (mirrors the Phase-42 `offer_for_eligibility_manual` addition). The `unresolved_noc` template (`:103`) already exists and fits. `[VERIFIED]` |
| `crawler.audit_report.SCREENING_NOTICE` | `crawler/audit_report.py:54` | Prepend to any rendered worksheet artifact (screening-not-legal-advice framing). `[VERIFIED]` |
| `crawler.paths.resolve_within` | `crawler/paths.py` | Write the worksheet artifact strictly inside the vault (path-escape guard). `[VERIFIED: used by import_document + extraction]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New `noc_review.py` inert sidecar | Wire a real `core.work`-greening path off duty confirmations | **Rejected** — violates NOC-03 (never auto-`SUBSTANTIATED`) and would mutate the frozen `core.work`. Sidecar is the only compliant shape. |
| Exact `chunk_id` `resolve()` | `searchindex.search()` BM25 over the NOC family | **Rejected** — fuzzy/ranked retrieval is a match-scoring path and can return the wrong NOC; "exact claimed NOC retrieval" demands a direct `chunk_id` lookup, fail-closed on miss. |
| Reuse existing 5-key staleness | Add a 6th `confirmed_corpus_chunk_sha` column | **Avoid if possible** — a schema column is a migration. The corpus-drift check can live in the sidecar (Layer 2) by comparing the stored `duty_sha` to the live `chunk_sha(text)`, so **no migration is needed**. (See **Open Question Q1 → RESOLVED**.) |
| Worksheet imported as a vault document | Hang duty values off the existing employment-reference document | Both viable; importing a dedicated `noc_worksheet` doc gives a clean per-NOC `file_sha256` anchor and keeps the worksheet artifact addressable. Recommended. |

**Installation:** none. `pip`/`poetry` unchanged; `[project].dependencies` must show **zero diff** (a Phase-46 SAFE-12 zero-new-dependency gate will assert this).

**Version verification:** No package to verify — the phase adds no third-party import. The relevant "versions" are internal fingerprints: `extraction.PARSER_VERSION = "1"` (bump invalidates confirmations via SC4) `[VERIFIED: crawler/extraction.py:41]`, and the corpus `chunk_sha` fingerprints (recomputed live). `[VERIFIED]`

## Package Legitimacy Audit

**No external packages are installed by this phase.** The zero-new-dependency constraint is a hard project invariant; the entire feature is stdlib + already-vendored `pydantic`.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none — no new packages)* | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*If a plan proposes any new import, that plan is out of compliance with the standing zero-new-dependency constraint and must be rejected or gated behind an explicit supply-chain justification + `checkpoint:human-verify`.*

## Architecture Patterns

### System Architecture Diagram

```
                       (already crawled, pinned, indexed — FROZEN)
   corpus/noc-2021/noc-<code>.md ──build_index──► corpus/index.db (chunks + FTS5)
                                                        │
 claimed NOC (confirmed `noc_code` on a core.work       │  exact chunk_id lookup
 employment_reference document)                         ▼  (NO fuzzy / NO BM25)
        │                                   searchindex.resolve('noc-2021/noc-<code>.md#001|#002|#003')
        ▼                                               │  → verbatim span or None (fail-closed)
  ┌─────────────────────────── crawler/noc_worksheet.py (NEW, pure stdlib) ───────────────────────────┐
  │  • resolve lead statement (#001), main duties (#002), employment requirements (#003)               │
  │  • deterministic split of #002 into per-duty items (drop the "This group performs…" lead line)     │
  │  • stable duty_id = "<noc>:<chunk_ordinal>:<item_idx>"  + duty_sha = chunk_sha(duty_text)          │
  │  • retrieve-what-you-cite: grounding.quote_is_grounded(duty_text, chunk_text)                      │
  │  • render worksheet artifact (SCREENING_NOTICE + cited spans)  ─► VAULT-ONLY file                  │
  │  • import_document(doc_type="noc_worksheet")  +  record_extraction_run(PARSER_VERSION)             │
  │  • add_extracted_value(field_name="noc_duty", factor_id="review.noc", pending) × N duties          │
  │  • upsert_profile_factor("review.noc") ONCE — the enforced FK parent (foreign_keys=ON, no migration)│
  └────────────────────────────────────────────────────────────────────────────────────────────────┘
        │  (born pending, quarantined)                          ▲ human detail → stderr; --json PII-light
        ▼                                                       │
  vault confirm --value-id <val_…> --decision confirm|correct|reject   (SHIPPED verb — unchanged)
        │  captures 5 staleness keys (file_sha of worksheet, parser_version, profile_claim_version, …)
        ▼
  ┌─────────────────────────── crawler/noc_review.py (NEW, pure stdlib, INERT) ────────────────────────┐
  │  read: vault.audit_eligible_values(v, "review.noc")  (dedicated inert factor — NEVER core.work)     │
  │  Layer 1: vault.is_audit_eligible(duty_value)  (confirmed/corrected + quality ok + not 5-key stale) │
  │  Layer 2: corpus drift — resolve(current) → chunk_sha(text) == stored duty_sha ? + quote_is_grounded│
  │  roll-up:  no confirmations → AT-RISK unresolved_noc                                                │
  │            any rejected / partial / stale / drifted → GAP or AT-RISK                                │
  │            all required duties confirmed+fresh+grounded → **still AT-RISK** (never auto-green)       │
  │  returns a CLOSED PII-light dict {noc_code, duty_count, confirmed_count, status, reason, citations}  │
  └────────────────────────────────────────────────────────────────────────────────────────────────┘
        │  NOT wired into crawler.auditors dispatch · NOT in FULL_GRID_FACTORS · NOT summed into envelope
        ├───────────────►  core.work  (FROZEN: still AT-RISK unresolved_noc — never sees a duty value)
        └───────────────►  Phase 45 MEC (LATER consumer: AT-RISK human-confirmed skilled-work input)
```

*File-to-implementation detail is in the Create / Modify / Freeze Map, not the diagram.*

### Recommended Project Structure
```
crawler/
├── noc_worksheet.py        # NEW — generate cited worksheet + born-pending per-duty values (pure stdlib)
├── noc_review.py           # NEW — inert AT-RISK/GAP/N/A duty-review sidecar (policy_offer clone)
├── models/vault.py         # MODIFY — add "noc_duty" (+ optional "noc_lead_statement") to FieldName Literal
├── extraction.py           # MODIFY (optional) — the worksheet generator sets factor_id="review.noc" DIRECTLY; do NOT add "noc_worksheet"→core.work to _DOC_TYPE_FACTOR (that would link duty values to core.work)
├── remediation.py          # MODIFY — one generic {factor} template for the duty-review reason (or reuse unresolved_noc)
├── cli.py                  # MODIFY — new `vault noc-worksheet` + `vault noc-review` subverbs (reuse `vault confirm`/`fields`)
└── tests/
    ├── test_noc_review.py          # NEW — worksheet slice (deterministic split/IDs, exact-retrieval, fail-closed absent NOC, vault-only, idempotent rerun) + never-SUBSTANTIATED sweep, staleness/drift → AT-RISK/GAP, PII-light closed set
    ├── test_noc_review_cli.py      # NEW — end-to-end CLI: vault-only artifact, PII-light stdout, one-duty-at-a-time confirm, index-preflight refusal, idempotent rerun
    └── test_conformance_v5_noc_no_auto_green.py  # NEW — negative control: no NOC path can green CRS / envelope; idempotent-regeneration isolation
```

### Pattern 1: Exact claimed-NOC retrieval (no fuzzy match, fail-closed)
**What:** Read the confirmed `noc_code` (5 digits) from the `core.work` evidence, build the deterministic `chunk_id`s, and `resolve()` them directly. A miss returns `None` → refuse (`AT-RISK`/`GAP`, "NOC not in corpus"). Never `search()`.
**When to use:** Worksheet generation start; every duty-review re-check.
**Example:**
```python
# Source: verified this session against corpus/index.db
from crawler import searchindex
db = "corpus/index.db"
code = "21232"                       # confirmed noc_code from the core.work evidence
rel  = f"noc-2021/noc-{code}.md"
lead = searchindex.resolve(db, f"{rel}#001")   # Lead statement chunk
main = searchindex.resolve(db, f"{rel}#002")   # Main duties chunk
reqs = searchindex.resolve(db, f"{rel}#003")   # Employment requirements chunk
if None in (lead, main, reqs):                 # absent/drifted → fail-closed
    return {"status": "AT-RISK", "reason": "unresolved_noc"}   # never fabricate
```

### Pattern 2: Deterministic per-duty split + stable IDs
**What:** Split the Main-duties chunk into duty items deterministically; drop the boilerplate lead line; keep each remaining bullet verbatim; assign a stable ordinal ID + content fingerprint.
**When to use:** Worksheet generation.
**Example:**
```python
# Source: verified this session (noc-21232 → 7 duties; noc-53124 has sub-occupation headers)
def split_duties(main_chunk_text: str) -> list[dict]:
    items, idx = [], 0
    for line in main_chunk_text.splitlines():
        if not line.startswith("- "):
            continue
        duty = line[2:].strip()
        if duty.lower().startswith("this group performs"):
            continue                              # boilerplate lead line — skip
        items.append({
            "duty_id":  f"{{noc}}:2:{idx:02d}",   # stable: <noc>:<chunk_ordinal>:<item_idx>
            "duty_sha": searchindex.chunk_sha(duty),   # drift fingerprint
            "text":     duty,                     # verbatim cited span
        })
        idx += 1
    return items
```
**Note (grouped NOCs):** In a minority of unit groups (e.g. `53124` Artisans and craftspersons), the Main-duties list interleaves **sub-occupation header lines** ("Carvers", "Potters") with duty lines. **Do not** attempt to semantically classify these — that is the forbidden scoring path. Present every bullet verbatim as an item; the human simply does not confirm a header line. Determinism and honesty over cleverness. `[VERIFIED: cat corpus/noc-2021/noc-53124.md]`

### Pattern 3: Born-pending per-duty value via the shipped quarantine store (on the inert `review.noc` factor)
**What:** Each duty → one `ExtractedValue` (`field_name="noc_duty"`, `factor_id="review.noc"`) inserted `pending`; the deterministic `duty_id`/`duty_sha`/`chunk_id` ride in `normalized_value`; the verbatim duty span rides in `raw_text`. **The values NEVER use `core.work`** — that keeps the frozen `core.work` audit from ever reading a duty value (B1). Because `extracted_values.factor_id` carries an **enforced FK** to `crs_profile_factors` (`foreign_keys=ON`), the generator first `upsert_profile_factor("review.noc")` ONCE as the inert FK parent (a data upsert, not a schema migration; `review.noc` is never added to `FULL_GRID_FACTORS`).
**When to use:** Worksheet generation, after the split.
**Example:**
```python
# Source: crawler/vault.py:803 (add_extracted_value) — pure sqlite/pydantic, no heavy deps
# FK parent (once): extracted_values.factor_id -> crs_profile_factors, foreign_keys=ON.
vault.upsert_profile_factor(v, CrsProfileFactor(
    factor_id="review.noc", factor_group="additional_points",   # inert; NOT in FULL_GRID_FACTORS
    claimed_points=None, claimed_level=None, claimed_value={}, source="user_entry"))
run = vault.record_extraction_run(v, document_id=ws_doc_id,
                                  parser_version=extraction.PARSER_VERSION)   # SC4 anchor
for d in duties:
    vault.add_extracted_value(
        v, document_id=ws_doc_id, page_id=None, factor_id="review.noc",   # NEVER core.work
        field_name="noc_duty",                       # NEW closed-enum member
        raw_text=d["text"],                          # verbatim cited span (PII-adjacent → vault only)
        normalized_value={"duty_id": d["duty_id"], "duty_sha": d["duty_sha"],
                          "citation": f"noc-2021/noc-{code}.md#002"},
        bbox=None, extractor_confidence=None, quality_flag="ok",
        extraction_run_id=run)                        # status forced to 'pending' by the store
```

### Pattern 4: Per-duty confirmation reuses the shipped verb (no new decision path)
**What:** `vault confirm --value-id <val_…> --decision confirm|correct|reject` captures the human's per-duty answer and stamps the 5 staleness keys. `confirm` = "my work performed this duty"; `reject` = "it did not"; `correct` = attach a clarifying corrected value. **No bulk confirm-all** (structural rubber-stamp defense).
**Why:** Reuses `confirm.apply_decision` / `vault.confirm_value` verbatim — no second confirmation path, no migration. `[VERIFIED: crawler/confirm.py:119]`

### Pattern 5: Inert duty-review sidecar (policy_offer clone) + two-layer staleness
**What:** A pure module returning a closed PII-light dict; status ∈ {`AT-RISK`, `GAP`, `N/A`} — **never** `SUBSTANTIATED`. Not registered in `auditors`, not in `FULL_GRID_FACTORS`, not summed into any envelope.
**When to use:** `vault noc-review`; Phase 45 MEC input.
**Example (contract shape — mirror `crawler/policy_offer.py`):**
```python
# Source: crawler/policy_offer.py (verified) — constant never-green status, closed field set
PUBLIC_FIELDS = ("noc_code", "duty_count", "confirmed_count",
                 "status", "reason", "citations")   # PII-light closed set

def review_noc_duties(v, db, noc_code) -> dict:
    # Read: the confirmed duty values on the dedicated inert factor (NEVER core.work)
    #   values = vault.audit_eligible_values(v, "review.noc")   # factor-scoped read
    # Layer 1: shipped gate — confirmed/corrected + quality ok + not 5-key stale
    #   (audit_eligible_values already applies is_audit_eligible; factor-agnostic)
    # Layer 2: corpus drift — for each eligible duty value:
    #   cur = searchindex.resolve(db, value.normalized_value["citation"])
    #   fresh = cur is not None and grounding.quote_is_grounded(value.raw_text, cur["text"])
    #   (equivalently: chunk_sha(duty_text) still present in cur["text"])
    # roll-up (fail-closed):
    #   no eligible confirmations           -> ("AT-RISK", "unresolved_noc")
    #   any rejected / drifted / partial     -> ("GAP"|"AT-RISK", "unresolved_noc")
    #   all required duties confirmed+fresh  -> ("AT-RISK", "duty_review_manual")  # STILL not green
    return {"noc_code": noc_code, "status": "AT-RISK", ...}   # crs impact: none
```

### Anti-Patterns to Avoid
- **Any match score / overlap / entailment.** No `SequenceMatcher`, no token overlap %, no "confidence" number for duty fit. The verdict is human-confirmed or `AT-RISK` — period. (Pitfall 5 from `ROADMAP.md`.)
- **`searchindex.search()` (BM25) to find the NOC.** Ranked retrieval can return the wrong occupation; use exact `resolve()` on the deterministic `chunk_id`.
- **Auto-`SUBSTANTIATED` when all duties are confirmed.** NOC-03 forbids it; the sidecar caps at `AT-RISK` even on full confirmation (a human confirming a duty is not the same as an officer's essential-duty finding).
- **Mutating `core.work` / the CRS total / `PublicAuditEnvelope`.** The frozen surfaces must show zero diff.
- **Worksheet or per-duty text on stdout.** Worksheet is vault-only; stdout is the PII-light closed dict only.
- **A schema column for corpus-chunk staleness.** Unnecessary — Layer-2 drift lives in the sidecar (no migration).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exact NOC span retrieval | A bespoke file reader over `corpus/noc-2021/*.md` | `searchindex.resolve(db, chunk_id)` | Already fail-closed, tamper-guarded (`chunk_sha` re-check), read-only, and the single frozen grounding path. Reading files directly forks the trust path. `[VERIFIED]` |
| Per-duty confirmation lifecycle | A new "duty answers" table + confirm flow | `add_extracted_value` (pending) + `vault confirm` + `is_audit_eligible` | The quarantine/confirm/staleness machinery is shipped, tested, and PII-safe; a parallel store is a second trust path + a migration. `[VERIFIED]` |
| Staleness of a confirmation | A custom timestamp/expiry check | 5-key `is_stale` (Layer 1) + `chunk_sha` drift (Layer 2) | Layer 1 already binds parser/claim/registry/file/render; Layer 2 adds corpus drift with the existing `chunk_sha` primitive — no new fields. `[VERIFIED]` |
| Retrieve-what-you-cite | A substring/regex check that a duty is "in the corpus" | `grounding.quote_is_grounded(quote, chunk_text)` | The shipped verbatim-grounding predicate the whole milestone's grounding gate uses. `[VERIFIED: returns True for a real duty span]` |
| Duty-fit judgment | An NLI/keyword/overlap scorer | A **binary human confirmation**, capped at `AT-RISK` | Duty fit (esp. "all essential duties") is an irreducible officer judgment; automating it is explicitly out of scope (VAL-02, deferred). `[CITED: REQUIREMENTS.md Out-of-Scope + VAL-02]` |
| Verdict/MEC integration | A new decider registered on the dispatch spine | An **inert sidecar** (policy_offer clone) | Registering it risks the `_default_decider`/grid summing a NOC verdict into the CRS total; the inert, unwired sidecar is structurally never-green. `[VERIFIED: crawler/policy_offer.py]` |
| Screening framing | New disclaimer prose | `audit_report.SCREENING_NOTICE` | One canonical notice already covers "not legal advice / no outcome prediction." `[VERIFIED]` |

**Key insight:** Phase 43 is a **composition** phase, not a construction phase. Every hard part (grounded retrieval, quarantine, per-field confirm, 5-key staleness, inert-sidecar integration, screening framing) already exists and is release-gate-proven. The new code is thin glue: a deterministic split, a vault-only artifact, a closed-enum member, and a never-green roll-up. Building anything custom here almost certainly forks a frozen trust path or adds a migration the constraints forbid.

## Create / Modify / Freeze Map

> Requested explicitly. This is the plan-ready blast radius. "Modify" items are **additive/closed-enum-extension only** — no behavior change to existing paths, no data migration.

### CREATE (new files, pure stdlib)
| File | Responsibility | Notes |
|------|----------------|-------|
| `crawler/noc_worksheet.py` | Resolve exact NOC spans → deterministic per-duty split → vault-only worksheet artifact → `import_document(doc_type="noc_worksheet")` + `upsert_profile_factor("review.noc")` (FK parent) + `record_extraction_run` + born-`pending` `noc_duty` values linked to `review.noc` (never `core.work`) | No heavy deps (store fns are sqlite/pydantic). Reuses `searchindex.resolve`, `grounding.quote_is_grounded`, `paths.resolve_within`, `SCREENING_NOTICE`. |
| `crawler/noc_review.py` | Inert `AT-RISK`/`GAP`/`N/A` duty-review roll-up + two-layer staleness; closed PII-light dict | policy_offer clone. **Not** imported by `crawler/auditors/*`. |
| `crawler/tests/test_noc_review.py` | Worksheet slice (deterministic split/IDs; exact-retrieval + fail-closed absent NOC; grouped-NOC verbatim; vault-only (no stdout PII); born-`pending`; idempotent rerun) + never-`SUBSTANTIATED` sweep; unconfirmed/partial/rejected/stale/drift → `AT-RISK`/`GAP`; PII-light closed-set proof; inert (not in dispatch/grid/envelope) | |
| `crawler/tests/test_noc_review_cli.py` | End-to-end CLI: vault-only artifact; PII-light stdout; one-duty-at-a-time confirm; index-preflight refusal; idempotent rerun (stable envelope, confirmed state preserved) | |
| `crawler/tests/test_conformance_v5_noc_no_auto_green.py` | Negative control: no NOC path yields a non-zero CRS delta / `SUBSTANTIATED`; `PublicAuditEnvelope` + `substantiated_total` unchanged; `core.work` frozen (zero diff); idempotent-regeneration isolation | Mirrors `test_conformance_v5_policy_no_job_offer_green.py`. |

### MODIFY (additive only — no migration, no behavior change to existing paths)
| File | Change | Migration? |
|------|--------|------------|
| `crawler/models/vault.py` | Add `"noc_duty"` (and optionally `"noc_lead_statement"`) to the `FieldName` Literal (`:75`) | **No** — `extracted_values.field_name` is `TEXT NOT NULL` with **no DB CHECK**; the enum is enforced by pydantic only. Code-only. `[VERIFIED: schema at vault.py:149-171]` |
| `crawler/cli.py` | Add `vault noc-worksheet` (generate) + `vault noc-review` (roll-up) subverbs under the existing `vault` subparser (`_add_vault_subparser`, `:1428`); human detail → stderr, `--json` PII-light | No |
| **vault data (not code): `crs_profile_factors` `review.noc` row** | Worksheet generation `upsert_profile_factor("review.noc")` ONCE as the FK parent for duty values. `extracted_values.factor_id` carries an **ENFORCED FK** to `crs_profile_factors` (`foreign_keys=ON` — `add_extracted_value(factor_id="review.noc")` FAILS with `FOREIGN KEY constraint failed` without it, VERIFIED this session). Inert: never in `FULL_GRID_FACTORS`, never audited/summed. | **No** — a data upsert, not a schema/DDL migration |
| `crawler/remediation.py` | Alias the sidecar reason `duty_review_manual` → the shipped `unresolved_noc` action via a one-entry `_REASON_ALIASES` map resolved in `_action_for` (`:154`); **no duplicate template** (W1) | No |
| `crawler/extraction.py` | **Do NOT** add `_DOC_TYPE_FACTOR["noc_worksheet"]` (`:252`) — that would link duty values to `core.work`. The worksheet generator sets `factor_id="review.noc"` DIRECTLY. | No |

### FREEZE (must show zero diff vs HEAD — assert in the negative-control test)
| File / surface | Why frozen |
|----------------|-----------|
| `crawler/auditors/core.py::decide_work` | `core.work` stays `AT-RISK unresolved_noc`; duty confirmations never flip it green (NOC-03). `[VERIFIED: :334-389]` |
| `crawler/crs_audit.py` (incl. `arranged_employment_guard`, `aggregate_work`) | The frozen CRS logic + guard. |
| `crawler/auditors/__init__.py::FULL_GRID_FACTORS` / dispatch registry | The NOC sidecar is **not** added here (inert). |
| `crawler/models/audit.py::PublicAuditEnvelope`, `to_public_envelope`, `substantiated_total` | No NOC value ever summed into the CRS total or the public envelope. |
| `crawler/review_packet.py` | Unchanged (as in Phase 42). |

## Common Pitfalls

### Pitfall 1: Auto-greening on full duty confirmation (the headline regression)
**What goes wrong:** A tempting "if every duty is confirmed → `SUBSTANTIATED`" roll-up.
**Why it happens:** It feels like the human "confirmed the match." But confirming individual duties ≠ the officer's R87.1(2)(c) essential-duty finding, and the corpus doesn't label essential duties.
**How to avoid:** The sidecar's terminal state on full confirmation is **`AT-RISK` (`duty_review_manual`)**, not `SUBSTANTIATED`. Assert this in a sweep over all-confirmed inputs.
**Warning signs:** Any code path in `noc_review.py` that can emit `"SUBSTANTIATED"`; any non-zero CRS delta after a NOC review.

### Pitfall 2: Semantic-auto-resolution creep (ROADMAP Pitfall 5)
**What goes wrong:** Adding a "helpful" overlap/keyword/NLI score to pre-fill or rank duties.
**Why it happens:** Scoring looks like a UX win.
**How to avoid:** No scoring primitive anywhere. Present verbatim, capture binary confirmations. A test should assert `noc_worksheet.py`/`noc_review.py` import no `difflib`/model/vector lib and contain no ratio/score arithmetic over duty text.
**Warning signs:** `SequenceMatcher`, `.ratio(`, token-set intersection over duty text, any float "match confidence."

### Pitfall 3: Stale/drifted confirmations silently counting (ROADMAP Pitfall 8/12)
**What goes wrong:** The corpus is re-crawled and a duty's wording changes, but an old confirmation still counts.
**Why it happens:** The generic 5-key `is_stale` does **not** include a corpus-chunk fingerprint (its keys are file/render/parser/claim/registry).
**How to avoid:** Layer-2 drift check in the sidecar — recompute `chunk_sha(live_chunk_text)` / `quote_is_grounded(stored_duty_text, live_chunk_text)`; a mismatch demotes the duty to unresolved (`AT-RISK`/`GAP`). This is the resolution to **Open Question Q1**.
**Warning signs:** A duty-review status that ignores `searchindex.resolve` returning `None`; no re-verification of the stored `duty_sha`.

### Pitfall 4: Wrong-NOC retrieval via fuzzy search
**What goes wrong:** Using `search()` (BM25) to "find" the NOC returns a neighbor occupation.
**How to avoid:** Exact `resolve('noc-2021/noc-<code>.md#00X')` only; `None` → refuse. Never rank.
**Warning signs:** `searchindex.search(` in the NOC modules; any ranking/limit over the NOC family.

### Pitfall 5: NOC absent from the curated corpus (coverage gap)
**What goes wrong:** The corpus has **376** unit groups, **TEER 0/1/2/3 only** — not the full NOC-2021 set (~516 unit groups), and no TEER 4/5. A claimed NOC outside the 376 (e.g. a TEER 4/5 code) resolves to `None`.
**Why it happens:** The corpus is deliberately scoped to Express-Entry-eligible skilled occupations.
**How to avoid:** Treat an absent NOC as a **fail-closed refusal** (`AT-RISK`/`GAP`, "NOC not in corpus / not skilled-work TEER"), never fabricate duties. `[VERIFIED: 376 files, teer ∈ {0,1,2,3}]`
**Warning signs:** A worksheet generated for a code with no `corpus/noc-2021/noc-<code>.md`.

### Pitfall 6: PII leak via worksheet or duty text on stdout (ROADMAP Pitfall 6/11)
**What goes wrong:** Emitting the worksheet or a per-duty answer on the `--json` envelope.
**How to avoid:** Worksheet artifact is vault-only (`paths.resolve_within`); the sidecar's public dict is a **closed field set** (ids/counts/status/reason/citations). Assert no `raw_text`/`normalized_value`/absolute path crosses `--json` (mirror `test_..._pii_perimeter.py`).
**Warning signs:** `print`/`--json` carrying `raw_text`, `duty` text, or an absolute path.

## Code Examples

Verified patterns from this session (all against the live repo + corpus):

### 1. NOC corpus is per-section chunked with resolvable citations `[VERIFIED]`
```text
# sqlite over corpus/index.db — chunks for noc-2021/noc-21232.md
#000  section "… Software developers and programmers"                      (TEER)
#001  section "… › Lead statement"           → R87.1(2)(b) evidence
#002  section "… › Main duties"              → R87.1(2)(c) evidence (all duties in ONE chunk)
#003  section "… › Employment requirements"  → TEER/eligibility context (NOT the duty-match test)
#004  "… › Illustrative example(s)"   #005 "… › All examples"   #006 "… › Exclusion(s)"   #007 "… › Additional information"
```

### 2. The grounded duty-match standard (already in corpus) `[VERIFIED: corpus + live canada.ca]`
```text
# corpus/pr-pdi/economic-classes-experience-qualifying-work-experience.md#003
"performed the actions described in the lead statement … [R87.1(2)(b)]"
"performed a substantial number of the main duties, including all the essential duties … [R87.1(2)(c)]"
# live canada.ca FSW eligibility page (public wording):
"performed: the actions in the lead statement of the NOC job description, and most of the main duties listed"
```

### 3. Deterministic split + fingerprint + retrieve-what-you-cite `[VERIFIED this session]`
```python
r = searchindex.resolve("corpus/index.db", "noc-2021/noc-21232.md#002")
lines  = [ln[2:].strip() for ln in r["text"].splitlines() if ln.startswith("- ")]
duties = [d for d in lines if not d.lower().startswith("this group performs")]   # → 7 duties
searchindex.chunk_sha(duties[0])                       # '87729cb40ece'  (stable duty fingerprint)
grounding.quote_is_grounded(duties[0], r["text"])      # True (verbatim in the cited chunk)
```

### 4. Fail-closed on absent NOC `[VERIFIED this session]`
```python
searchindex.resolve("corpus/index.db", "noc-2021/noc-99999.md#002")   # → None  (refuse; never fabricate)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| NOC 2016 4-digit codes + Skill Levels A/B/C/D | **NOC 2021** 5-digit codes + **TEER 0-5** | IRCC switched to NOC 2021 for Express Entry on **2022-11-16** | The corpus is NOC-2021 (`teer` frontmatter, 5-digit files); the R87.1 rule text has an "on/after November 16, 2022" branch (`#003`) — cite that branch, not the pre-2022 one. `[VERIFIED: corpus chunk sections]` |
| Duty text scraped from StatCan HTML | Generated from StatCan's **NOC CSV/structure** (`generator: statcan-noc-csv`) | Corpus build | StatCan NOC profile pages are a JS single-page app — `curl` returns no section text. Verification of *structure* is against the pinned corpus + IRCC's rule; live StatCan HTML scraping is not viable and not needed. `[VERIFIED: fetched page is JS-driven]` |

**Deprecated/outdated:**
- **Skill Level A/B/C/D** language: gone in NOC 2021 — use **TEER 0/1/2/3** (the EE-eligible tiers present in the corpus).
- **Fuzzy/BM25 NOC lookup for this feature:** not used — exact `chunk_id` `resolve()` only.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Naming the two new modules `crawler/noc_worksheet.py` and `crawler/noc_review.py`, and the new `FieldName` member `noc_duty`, is the planner's call (names are conventions, not verified constraints). | Create/Modify Map | Low — cosmetic; adjust names in the plan. |
| A2 | New CLI verbs `vault noc-worksheet` / `vault noc-review` are the chosen surface; a single `vault noc <subverb>` grouping is equally valid. | Architecture / CLI | Low — UX shape; either is compliant. `[ASSUMED]` |
| A3 | "Required duty match" for the roll-up = lead statement confirmed **and** a project-chosen minimum of main duties confirmed. The exact "substantial number" threshold is deliberately **not** encoded (it is an officer judgment); the sidecar caps at `AT-RISK` regardless, so any threshold choice only affects `GAP` vs `AT-RISK` labeling, never a green. | Pattern 5 / Pitfall 1 | Low — cannot cause a false green by construction; confirm the `GAP`/`AT-RISK` boundary during planning. `[ASSUMED]` |
| A4 | Importing the worksheet as a `noc_worksheet` vault **document** (vs. hanging duty values off the employment-reference document) is the recommended anchor. | Standard Stack / Alternatives | Low — both compliant; document import gives a cleaner `file_sha256` anchor. `[ASSUMED]` |

**All corpus-structure, retrieval, staleness, and grounded-rule claims are `[VERIFIED]` against the live repo/corpus this session — the only `[ASSUMED]` items are naming/UX/threshold-labeling choices that cannot affect the fail-closed guarantee.**

## Open Questions (RESOLVED)

1. **How should corpus drift invalidate a confirmed duty without a schema migration?** — **RESOLVED.**
   - What we know: the 5-key `is_stale` binds file/render/parser/claim/registry, **not** a corpus-chunk fingerprint; `resolve()` already fails closed on stored-text tamper, and `chunk_sha`/`quote_is_grounded` are public primitives. `[VERIFIED]`
   - Resolution: **Layer-2 drift check in the `noc_review` sidecar** — recompute `chunk_sha(live_chunk_text)` / `quote_is_grounded(stored_duty_text, live_chunk_text)`; a mismatch demotes the duty to unresolved (`AT-RISK`/`GAP`). No 6th column, no migration. (Optionally, a corpus refresh can also bump the vault `rule_registry_version` to re-stale via Layer 1, but Layer 2 is the precise, per-duty mechanism.)

2. **Does the duty-review signal feed back into `core.work`?** — **RESOLVED: No.**
   - What we know: `core.work` returns `AT-RISK unresolved_noc` on missing TEER and is a frozen surface; NOC-03 forbids automated `SUBSTANTIATED`. `[VERIFIED: core.py:334-389]`
   - Resolution: `core.work` stays **byte-for-byte frozen**. The duty-review is a **separate inert sidecar signal** (policy_offer pattern) consumed by Phase 45 MEC as an `AT-RISK` human-confirmed input. It never mutates `core.work`, the CRS total, or `PublicAuditEnvelope`. This is the "separate sidecar / inert signal" the phase brief anticipated.

3. **Are Employment requirements (`#003`) part of the confirmation surface?** — **RESOLVED: informational only.**
   - What we know: R87.1's duty-match test is lead statement (`#001`) + main duties (`#002`); employment requirements describe typical credentials/licensing (TEER context), not duty fit. `[VERIFIED: corpus + PDI]`
   - Resolution: Show `#003` **cited but read-only** in the worksheet (satisfies NOC-01's "employment requirements … with resolvable citations"); do **not** create per-item confirmations for it. Confirmations are for the lead statement + each main duty.

4. **What is the canonical citation for the "duty-match" standard itself?** — **RESOLVED.**
   - Resolution: cite the NOC-2021 per-section chunks for the *content* (`noc-2021/noc-<code>.md#001|#002|#003`) **and** the grounded IRCC rule for the *standard* (`pr-pdi/economic-classes-experience-qualifying-work-experience.md#003`, the on/after 2022-11-16 branch, carrying R87.1(2)(b)/(c)). Both are already in the pinned corpus. `[VERIFIED]`

5. **Which `factor_id` do the born-pending duty values use, and can an arbitrary factor id be inserted?** — **RESOLVED (B1).**
   - What we know: `extracted_values.factor_id` is declared `TEXT REFERENCES crs_profile_factors(factor_id)` and the vault opens with `PRAGMA foreign_keys = ON` (`crawler/vault.py:409`). An `add_extracted_value(factor_id="review.noc")` with **no** parent row FAILS with `FOREIGN KEY constraint failed` — the FK **is** enforced (VERIFIED this session; the earlier "TEXT no FK" assumption is corrected here). `[VERIFIED]`
   - Resolution: The duty values MUST use a **dedicated inert `factor_id="review.noc"`, never `core.work`** — this is what keeps confirmed duty text / evidence ids out of the frozen `core.work` `PrivateFactorCard` (`audit_eligible_values("core.work")` never returns a `review.noc` value — VERIFIED: 0 before and after confirm). To satisfy the enforced FK **without a schema migration**, worksheet generation `upsert_profile_factor("review.noc")` ONCE (a data upsert with a valid closed `FactorGroup`, e.g. `additional_points`, `claimed_points=None`). `review.noc` is **never** added to `FULL_GRID_FACTORS`, so `run_full_audit` never audits or sums it, and no NOC value reaches `substantiated_total` or any `PublicAuditEnvelope`. The sidecar reads the values via `vault.audit_eligible_values(v, "review.noc")` and applies the factor-agnostic `is_audit_eligible` + Layer-2 corpus-drift gate. `[VERIFIED: seed→add→confirm→audit_eligible_values isolation flow this session]`

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv (`.venv`) | all tooling | ✓ | CPython + `pydantic` 2.13 | — |
| `pytest` | validation suite | ✓ | 9.0.3 | — |
| `corpus/index.db` (FTS5 + `chunks`) | NOC retrieval | ✓ | 376 NOC docs indexed, per-section chunks | — (preflight refuses if absent/stale — SAFE-10) |
| `corpus/noc-2021/` family | worksheet content | ✓ | 376 files, TEER 0/1/2/3 | — |
| `crawler/policy_offer.py` (pattern) | sidecar template | ✓ | shipped Phase 42 | — |
| doc-extract extras (pypdfium2/pdfminer) | **NOT** needed — duty capture uses the pure sqlite store fns, not the render engine | n/a | — | — |
| Any new PyPI package | — | ✗ by policy | — | **none** — zero-new-dependency constraint |

**Missing dependencies with no fallback:** none — the phase runs entirely on already-present infrastructure.
**Missing dependencies with fallback:** none required.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 (`.venv/bin/python -m pytest`) `[VERIFIED]` |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` (markers incl. `conformance`) `[VERIFIED]` |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_noc_review.py crawler/tests/test_noc_review_cli.py -x -q` |
| Full suite command | `.venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NOC-01 | Cited worksheet resolves lead/duties/reqs by exact `chunk_id`; absent NOC fails closed | unit | `pytest crawler/tests/test_noc_review.py -k "worksheet or duties or citation" -x -q` | ❌ Wave 0 |
| NOC-01 | Deterministic per-duty split + stable IDs (idempotent across runs); grouped-NOC verbatim | unit | `pytest crawler/tests/test_noc_review.py -k split -x` | ❌ Wave 0 |
| NOC-01/02 | Idempotent regeneration: exact rerun reuses `(duty_id, duty_sha)` values (no duplicate row/document, confirmed state preserved); changed-sha inserts one new pending row, old ignored; sidecar counts once | unit | `pytest crawler/tests/test_noc_review.py -k "idempotent or rerun or replaced" -x` | ❌ Wave 0 |
| NOC-02 | Per-duty value born `pending`; confirm/correct/reject via shipped `vault confirm`; staleness-keyed | unit | `pytest crawler/tests/test_noc_review.py -k confirm_or_stale -x` | ❌ Wave 0 |
| NOC-02 | No scoring/overlap/NLI primitive in NOC modules | unit (source scan) | `pytest crawler/tests/test_noc_review.py -k no_scoring -x` | ❌ Wave 0 |
| NOC-03 | Never `SUBSTANTIATED` (all-confirmed sweep); partial/stale/rejected/drift → `AT-RISK`/`GAP` | unit | `pytest crawler/tests/test_noc_review.py -k never_green -x` | ❌ Wave 0 |
| NOC-03 | `core.work` / CRS total / `PublicAuditEnvelope` unchanged; sidecar not in dispatch/grid | conformance | `pytest crawler/tests/test_conformance_v5_noc_no_auto_green.py -q` | ❌ Wave 0 |
| (privacy) | Worksheet vault-only; sidecar `--json` is a PII-light closed set (no raw_text/abs path) | conformance | `pytest crawler/tests/ -k "noc and pii" -q` | ❌ Wave 0 |
| (regression) | Existing suite stays green (frozen surfaces) | full | `.venv/bin/python -m pytest -q` | ✅ existing |

### Sampling Rate
- **Per task commit:** `pytest crawler/tests/test_noc_review.py crawler/tests/test_noc_review_cli.py -x -q` (< 30 s)
- **Per wave merge:** `pytest crawler/tests/ -k noc -q` + the touched frozen-surface tests (`test_full_audit_cutoff.py`, `test_auditor_dispatch.py`, `test_crs_no_inlined_rules.py`)
- **Phase gate:** full `.venv/bin/python -m pytest -q` green + `scripts/tests/test_check_publish_safe.py` (0 violations) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `crawler/tests/test_noc_review.py` — covers NOC-01/NOC-02 (retrieval, split, born-pending, vault-only, idempotent rerun, never-green sweep, staleness/drift, no-scoring, PII-light)
- [ ] `crawler/tests/test_noc_review_cli.py` — covers NOC-01/NOC-02 CLI (vault-only artifact, PII-light stdout, one-duty-at-a-time confirm, index-preflight refusal, idempotent rerun)
- [ ] `crawler/tests/test_conformance_v5_noc_no_auto_green.py` — negative control (frozen surfaces, no CRS/envelope mutation, idempotent-regeneration isolation) — mirror `test_conformance_v5_policy_no_job_offer_green.py`
- [ ] Extend `test_crs_no_inlined_rules.py` (or the module's own test) to scan `noc_worksheet.__file__` + `noc_review.__file__` (mirror how `policy_offer.__file__` was added)

*(Framework already installed — no framework-install gap.)*

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high` — section included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-user local CLI; no auth surface. |
| V3 Session Management | no | No sessions. |
| V4 Access Control | yes (data-plane) | Worksheet + per-duty answers are vault-only; `paths.resolve_within` prevents write-escape; stdout is PII-light. `[VERIFIED: import_document/extraction use resolve_within]` |
| V5 Input Validation | **yes** | `noc_code` validated to `\d{5}` before building the `chunk_id`; `chunk_id` bound **positionally** in `resolve()` (no FTS/SQL injection); new `FieldName='noc_duty'` rejected-if-unknown at the pydantic boundary; `--decision` restricted to `confirm/correct/reject`. `[VERIFIED: searchindex.resolve param-binding + vault add_extracted_value boundary validation]` |
| V6 Cryptography | n/a (integrity, not secrecy) | `sha256` (content-addressed docs) + `sha1`-based `chunk_sha` are integrity fingerprints only — never hand-rolled crypto; no secrets handled. `[VERIFIED]` |
| V7 Error Handling / Logging | yes | Refusals carry stable PII-free reason tokens (`unresolved_noc`), never applicant values — mirror `VaultError`/`AuditGroundingError`. `[VERIFIED: pattern in vault.py/auditor.py]` |
| V12 Files/Resources | yes | Worksheet artifact written only under the vault via `resolve_within`; never touches `corpus/`. `[VERIFIED]` |

### Known Threat Patterns for {stdlib CLI + SQLite corpus + git-ignored vault}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Wrong-NOC / injected `chunk_id` retrieval | Spoofing / Tampering | Exact `resolve()` with positional binding; `\d{5}` NOC validation; `None` on miss → refuse. `[VERIFIED]` |
| Stale/drifted duty confirmation counts | Tampering (data staleness) | Two-layer staleness (5-key gate + corpus `chunk_sha`/`quote_is_grounded` drift). `[VERIFIED primitives]` |
| Duty text / worksheet / answer on stdout | Information Disclosure | Vault-only artifact; closed PII-light sidecar dict; PII-perimeter test. |
| Auto-green elevation (NOC → CRS points) | Elevation of Privilege | Inert sidecar (never `SUBSTANTIATED`), unwired from dispatch/grid/envelope; duty values on the dedicated inert `review.noc` factor (never `core.work`), so the frozen `core.work` card never reads one; `review.noc` never in `FULL_GRID_FACTORS`; negative-control conformance (before/after `core.work` card byte-identity). `[VERIFIED: policy_offer precedent + review.noc isolation this session]` |
| Silent NOC-absence fabrication | Tampering | Fail-closed refusal on absent/TEER-4/5 NOC (not in the 376-doc corpus). `[VERIFIED: 376 files]` |
| New inlined rule/threshold | Tampering (ungrounded claim) | Read duty text/standard from grounded corpus spans; extend the no-inlined-volatile scan to the two new modules. `[VERIFIED gate exists]` |

## Sources

### Primary (HIGH confidence — verified this session via tool against the live repo/corpus)
- `corpus/index.db` (sqlite) — `chunks` schema; NOC per-section chunking (`#000`–`#007`); exact `resolve()` behavior + `None` on absent NOC; `chunk_sha`/`quote_is_grounded` over a real duty span.
- `corpus/noc-2021/*.md` (grep, 376 files) — section-header frequency (Lead statement / Main duties / Employment requirements = 376/376); TEER distribution {0:48, 1:97, 2:162, 3:69}; grouped-NOC main-duties structure (`noc-53124`).
- `corpus/pr-pdi/economic-classes-experience-qualifying-work-experience.md` — R87.1(2)(b)/(c) lead-statement + "substantial number … including all the essential duties" (the grounded duty-match standard, on/after 2022-11-16 branch `#003`).
- `crawler/vault.py`, `crawler/confirm.py`, `crawler/extraction.py`, `crawler/models/vault.py` — quarantine store, 5-key staleness, `is_audit_eligible` choke point, `FieldName` Literal (no DB CHECK → no migration for a new member).
- `crawler/auditors/core.py` (`decide_work` → `AT-RISK unresolved_noc`), `crawler/auditors/__init__.py` (dispatch/grid), `crawler/policy_offer.py` (inert-sidecar pattern), `crawler/models/audit.py` (`Verdict`, `PublicAuditEnvelope`).
- `.planning/ROADMAP.md` (Phase-43 goal/success-criteria/threat note), `.planning/REQUIREMENTS.md` (NOC-01/02/03 + standing constraints + Out-of-Scope), `.planning/phases/42-.../42-03-SUMMARY.md` (policy_offer precedent).

### Secondary (MEDIUM confidence — official source cross-check)
- **canada.ca** IRCC FSW eligibility page (live fetch 2026-07-19): public duty-match wording "the actions in the lead statement … and most of the main duties listed" — corroborates the corpus PDI/IRPR rule. `[VERIFIED: MEDIUM per classify-confidence(webfetch, verified)]`

### Tertiary (LOW confidence)
- StatCan NOC-2021 profile HTML (live fetch) is a JS single-page app — **could not** extract section text via `curl`; structure verification relied on the pinned corpus + IRCC rule instead (documented in State of the Art). No claim rests on scraped StatCan HTML.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — every component is already in-repo and exercised this session; zero new dependencies by construction.
- Architecture (inert sidecar + two-layer staleness + frozen `core.work`): **HIGH** — direct clone of the shipped, release-gate-proven `policy_offer.py` pattern; frozen surfaces identified precisely.
- Grounded rule + corpus structure: **HIGH** — verified in the pinned corpus and cross-checked against live canada.ca.
- Pitfalls: **HIGH** — derived from the ROADMAP threat note + shipped conformance precedents (Phase 42 negative control).
- Naming/UX/threshold-labeling: **MEDIUM/LOW** — `[ASSUMED]`, planner's discretion; cannot affect the fail-closed guarantee.

**Research date:** 2026-07-19
**Valid until:** 2026-08-18 (stable — internal corpus/code; re-verify only if `corpus/index.db` is re-crawled or the NOC-2021 / R87.1 rule text changes).
