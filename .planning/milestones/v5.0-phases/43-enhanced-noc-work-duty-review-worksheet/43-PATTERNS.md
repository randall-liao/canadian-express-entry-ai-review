# Phase 43: Enhanced NOC Work-Duty Review Worksheet — Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 12 (2 create / 5 modify / 5 freeze) + test & fixture surface
**Analogs found:** 12 / 12 (every new/modified file clones a shipped in-repo surface — this is a **composition** phase, not construction)

> Sourced from `43-RESEARCH.md` (Create/Modify/Freeze Map, Patterns 1–5, Pitfalls) + `43-VALIDATION.md` (Wave-0 test contract) with **no CONTEXT.md** (config `skip_discuss: true`). Standing constraints in `REQUIREMENTS.md` L15 / `STATE.md` frozen invariants carry locked-decision authority.
>
> **Three non-negotiable scope fences the planner must carry into every plan:**
> 1. **No semantic auto-match** — zero scoring/overlap/NLI/vector/`difflib` primitive anywhere in `noc_worksheet.py` / `noc_review.py`. Present cited duties verbatim; capture a **binary human confirmation** only. `[REQUIREMENTS NOC-02, Out-of-Scope L70, VAL-02]`
> 2. **No later-MEC wiring** — the `noc_review` sidecar ships **inert and unit-tested only** (policy_offer precedent). Phase 45 (MEC) consumes it LATER; **do not** import it into any decider/dispatch/grid/envelope this phase. `[RESEARCH §Standard Stack, policy_offer.py:10-18]`
> 3. **Factor isolation (B1)** — every `noc_duty`/`noc_lead_statement` value uses the dedicated inert `factor_id="review.noc"`, **NEVER `core.work`**. The enforced `extracted_values.factor_id` FK (`foreign_keys=ON`) is satisfied by seeding an inert `review.noc` `crs_profile_factors` row (data upsert, no migration); `review.noc` is never in `FULL_GRID_FACTORS`, so the frozen `core.work` card never reads a duty value. `[VERIFIED: FK enforced + isolation flow this session]`

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `crawler/noc_worksheet.py` **(CREATE)** | service / generator | transform + file-I/O + CRUD (seed review.noc FK parent + write pending values) | `crawler/extraction.py` (`_extract_document`→`record_extraction_run`→`add_extracted_value`) + `crawler/searchindex.py::resolve` | role-match (composition of shipped primitives) |
| `crawler/noc_review.py` **(CREATE)** | service (inert sidecar) | transform / read-only roll-up over `audit_eligible_values("review.noc")` (request-response) | `crawler/policy_offer.py` | **exact** (clone the inert-sidecar contract) |
| `crawler/models/vault.py` **(MODIFY)** | model / closed-enum vocab | boundary validation | `FieldName` Literal sibling-fields addition (`:75-96`) | **exact** (additive enum member) |
| `crawler/cli.py` **(MODIFY)** | route / CLI verb | request-response (PII-light envelope) | `_cmd_vault_confirm` (`:1184`) + `_cmd_vault_fields` (`:1151`) + `_add_vault_subparser` (`:1428`) | **exact** |
| **`crs_profile_factors` `review.noc` row (DATA — seeded by worksheet gen)** | inert FK parent | data upsert (not DDL) | `upsert_profile_factor` (`:482`) | **exact** (satisfies the enforced `extracted_values.factor_id` FK; NEVER in `FULL_GRID_FACTORS`) |
| `crawler/remediation.py` **(MODIFY, W1)** | utility / reason alias | transform (reason→action) | `_action_for` (`:154-159`) + reuse `unresolved_noc` (`:103-105`) | **exact** (one-entry alias, no duplicate template) |
| `crawler/extraction.py` **(DO NOT MODIFY — B1)** | config map | lookup | `_DOC_TYPE_FACTOR` (`:264`) | n/a (generator sets `factor_id="review.noc"` directly) |
| `crawler/tests/test_noc_review.py` **(CREATE)** | test | unit sweep | `crawler/tests/test_physician_policy.py` (`TestOfferSidecar` `:353`, `TestNoInlinedRules` `:329`) | **exact** |
| `crawler/tests/test_noc_review_cli.py` **(CREATE)** | test | end-to-end CLI | `crawler/tests/test_extract_confirm_cli.py` (`_run`/`cli.main` `:203`) | **exact** |
| `crawler/tests/test_conformance_v5_noc_no_auto_green.py` **(CREATE)** | test (conformance) | negative control | `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` | **exact** (mirror wholesale) |
| `crawler/tests/test_crs_no_inlined_rules.py` **(MODIFY)** | test (scan) | source scan | `_EXPORT_MODULES` tuple (`:29-32`) | **exact** (add two module paths) |
| deterministic NOC fixture chunks **(CREATE)** | test fixture | data | pinned `corpus/noc-2021/noc-<code>.md#001..#003` via `searchindex.resolve` | corpus (no code fixture needed) |

> **Test-name discrepancy (RESOLVED):** `43-VALIDATION.md` (approved) is authoritative and names the three test files **`test_noc_review.py`, `test_noc_review_cli.py`, `test_conformance_v5_noc_no_auto_green.py`**. `43-RESEARCH.md` has been updated (W-B) to use these canonical names everywhere — worksheet-generation coverage is folded into `test_noc_review.py` (its `-k "worksheet or duties or citation"` slice targets that per the per-task map). Follow the VALIDATION/RESEARCH names.

---

## Pattern Assignments

### `crawler/noc_worksheet.py` (CREATE — service/generator; transform + file-I/O + CRUD)

Composition of five shipped primitives. **No single donor file**; copy each seam below. Reuses the frozen grounding path — never forks a file reader over `corpus/`.

**(A) Exact claimed-NOC chunk retrieval — `searchindex.resolve` (`crawler/searchindex.py:502-562`). NEVER `search()`/BM25.**
```python
def resolve(db: Path, chunk_id: str) -> dict | None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)          # read-only URI (never writes)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT chunk_id, relpath, source_url, title, section, crawl_date, "
            "chunk_sha, text FROM chunks WHERE chunk_id = ?",       # UNIQUE(chunk_id) → 1 row or none
            (chunk_id,),                                            # POSITIONAL bind — no SQL/FTS injection
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None                                                # MISS → fail-closed
    if chunk_sha(row["text"]) != row["chunk_sha"]:
        return None                                                # DRIFT → fail-closed
    return {"chunk_id": ..., "relpath": ..., "text": row["text"], ...}   # text VERBATIM
```
Usage (RESEARCH Pattern 1): build `rel = f"noc-2021/noc-{code}.md"`; `resolve(db, f"{rel}#001")` (lead), `#002` (main duties), `#003` (employment requirements). `None in (lead, main, reqs)` → refuse `AT-RISK unresolved_noc`, never fabricate. Validate `code` to `\d{5}` **before** building the `chunk_id` (V5 input-validation, RESEARCH §Security).

**(B) Content fingerprint for stable per-duty IDs — `searchindex.chunk_sha` (`crawler/searchindex.py:128-135`):**
```python
def chunk_sha(text: str) -> str:
    """Short content fingerprint for staleness detection."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
```
Per-duty `duty_sha = chunk_sha(duty_text)`; stable `duty_id = f"{code}:2:{idx:02d}"` (`<noc>:<chunk_ordinal>:<item_idx>`). Deterministic split (RESEARCH Pattern 2): iterate `main["text"].splitlines()`, keep `- `-prefixed bullets, drop the `"this group performs…"` boilerplate lead line; **present grouped-NOC sub-occupation headers verbatim** as items (the human just won't confirm a header) — **do not** classify them (that is the forbidden scoring path, Pitfall 2).

**(C) Retrieve-what-you-cite — `grounding.quote_is_grounded` (`crawler/grounding.py:87-99`):**
```python
def quote_is_grounded(quote: str, chunk_text: str) -> bool:
    nq = _norm(quote)                                # whitespace-collapse + lowercase; empty ⇒ fail-closed
    return bool(nq) and nq in _norm(chunk_text)
```
Confirm each split duty span is verbatim-present in its cited chunk at generation time (and again at review time in the sidecar).

**(D) Vault-only worksheet artifact — write via `paths.resolve_within` (`crawler/paths.py:123-146`) + prepend `SCREENING_NOTICE` (`crawler/audit_report.py:54`).** Import as a document — `vault.import_document` (`crawler/vault.py:670-719`), which itself re-anchors through `resolve_within` and returns a **PII-light `DocumentSummary` (ids/type/status only — never the filename/abs path)**:
```python
dest = paths.resolve_within(vault.root, "files", "raw", filename)   # cannot escape the vault (T-29-04)
...
return DocumentSummary(document_id=..., evidence_id=..., doc_type=doc_type, status="added")  # PII-light
```
Import with `doc_type="noc_worksheet"` (free-text TEXT column → **no migration**, RESEARCH §Standard Stack). The rendered worksheet + raw duty text are PII-adjacent → **vault-only**; never printed on stdout (Pitfall 6).

**(E) Born-pending per-duty values on the inert `review.noc` factor — `upsert_profile_factor` (FK parent) + `record_extraction_run` + `add_extracted_value` (`crawler/vault.py:482`, `:728-751`, `:803-843`), stamped with `extraction.PARSER_VERSION` (`crawler/extraction.py:41`, currently `"1"`):**

> **B1 — factor isolation.** Duty values use a dedicated inert `factor_id="review.noc"`, **NEVER `core.work`**, so the frozen `core.work` audit never reads a duty value. `extracted_values.factor_id` carries an **ENFORCED FK** to `crs_profile_factors` (`crawler/vault.py:153`; the vault opens `PRAGMA foreign_keys = ON` at `:409`) — `add_extracted_value(factor_id="review.noc")` FAILS with `FOREIGN KEY constraint failed` unless a parent row exists (VERIFIED). So seed it ONCE (a data upsert, **not** a schema migration). `FactorGroup` is a closed 4-member Literal; use any valid value (`additional_points`) — `review.noc` is never in `FULL_GRID_FACTORS`, so it is never audited/summed.
```python
from crawler.models.vault import CrsProfileFactor
vault.upsert_profile_factor(v, CrsProfileFactor(                   # FK parent, once (idempotent)
    factor_id="review.noc", factor_group="additional_points",     # inert; NOT in FULL_GRID_FACTORS
    claimed_points=None, claimed_level=None, claimed_value={}, source="user_entry"))
run = vault.record_extraction_run(v, document_id=ws_doc_id,
                                  parser_version=extraction.PARSER_VERSION)   # SC4 staleness anchor
for d in duties:
    vault.add_extracted_value(
        v, document_id=ws_doc_id, page_id=None, factor_id="review.noc",       # NEVER core.work
        field_name="noc_duty",                                    # NEW closed-enum member (see vault model)
        raw_text=d["text"],                                       # verbatim span (PII-adjacent → vault only)
        normalized_value={"duty_id": d["duty_id"], "duty_sha": d["duty_sha"],
                          "citation": f"noc-2021/noc-{code}.md#002"},
        bbox=None, extractor_confidence=None, quality_flag="ok",
        extraction_run_id=run)                                    # status FORCED to 'pending' by the store
```
The store forces `confirmation_status='pending'` on every insert (quarantine invariant T-30-01) and validates `field_name` through the `ExtractedValue` pydantic model at the boundary (`vault.py:820-831`) — so an unknown field name is rejected fail-closed.

---

### `crawler/noc_review.py` (CREATE — inert sidecar; read-only roll-up) — **EXACT analog: `crawler/policy_offer.py:1-80`**

Clone the whole inert-sidecar shape. **Closed PII-light field set as a module constant** + a status that is **structurally never `SUBSTANTIATED`**, **not** imported by `crawler/auditors/*`, **not** in `FULL_GRID_FACTORS`, **not** summed into any envelope.

**Closed public field set + never-green return (`crawler/policy_offer.py:34-41, 73-80`):**
```python
PUBLIC_FIELDS: tuple[str, ...] = (
    "offer_present", "eligibility_status", "crs_points",
    "for_program_eligibility_only", "reason", "citation",
)
...
return {
    "offer_present": present,
    "eligibility_status": "AT-RISK" if present else "N/A",   # NEVER SUBSTANTIATED
    "crs_points": 0,                                          # CONSTANT — no branch reassigns
    "for_program_eligibility_only": True,
    "reason": "offer_for_eligibility_manual",
    "citation": current.citations[0].chunk_id if current else None,
}
```
NOC adaptation → closed set `("noc_code", "duty_count", "confirmed_count", "status", "reason", "citations")`; `status ∈ {"AT-RISK","GAP","N/A"}` only; roll-up (RESEARCH Pattern 5, Pitfall 1): no eligible confirmations → `("AT-RISK","unresolved_noc")`; any rejected/drifted/partial → `("GAP"|"AT-RISK","unresolved_noc")`; **all required duties confirmed + fresh → STILL `("AT-RISK","duty_review_manual")`, never green.**

**Factor-scoped read (B1) — `vault.audit_eligible_values("review.noc")` (`crawler/vault.py:1099-1117`). The sidecar reads confirmed duty values by the dedicated inert `review.noc` factor ONLY — NEVER `core.work` (the frozen work audit is never read or touched):**
```python
values = vault.audit_eligible_values(v, "review.noc")   # confirmed/corrected + quality ok + not-stale, scoped to review.noc
# Layer 2 (below) re-checks each value against the live corpus for drift.
```

**Layer-1 staleness gate (the single choke point, factor-agnostic) — `vault.is_audit_eligible` (`crawler/vault.py:1078-1096`) over `is_stale` (`:1048-1075`), already applied inside `audit_eligible_values`:**
```python
def is_audit_eligible(vault, value_id) -> bool:
    ...
    if row["confirmation_status"] not in ("confirmed", "corrected"):
        return False
    if row["quality_flag"] != "ok":
        return False
    return not is_stale(vault, value_id)          # 5-key: file/render/parser/claim/registry sha
```

**Layer-2 corpus-drift re-check (NOC-specific; RESEARCH Q1-RESOLVED, Pitfall 3) — resolve current chunk, re-verify the stored duty span. NO 6th column / NO migration:**
```python
cur = searchindex.resolve(db, value.normalized_value["citation"])
fresh = cur is not None and grounding.quote_is_grounded(value.raw_text, cur["text"])
#   (equivalently: chunk_sha(value.raw_text) still present in cur["text"])
```
A drift/miss demotes the duty to unresolved (`AT-RISK`/`GAP`).

**Frozen reference the sidecar must NOT flip — `core.work` stays `AT-RISK unresolved_noc` (`crawler/auditors/core.py:370-372`):**
```python
    if missing_teer:
        return DecisionResult("AT-RISK", "unresolved_noc", ...)   # FROZEN — duty confirmations never green this
```

---

### `crawler/models/vault.py` (MODIFY — add `noc_duty` to `FieldName`) — **EXACT analog: `:75-96`**

Additive closed-enum member. **No migration** — `extracted_values.field_name` is `TEXT NOT NULL` with no DB CHECK; the Literal is enforced by pydantic only (RESEARCH §MODIFY). Mirror the sibling-fields addition precedent (`:93-95`):
```python
FieldName = Literal[
    ...
    "issuer", "noc_code", "teer",
    ...
    # sibling in Canada (COV-03) — names mirror crawler.siblingfields.SIBLING_FIELDS
    "sibling_relationship", "sibling_status", "sibling_residence",
    "sibling_date_of_birth",
    # >>> ADD (Phase 43): NOC duty worksheet confirmation surface
    # "noc_duty",                     (+ optional "noc_lead_statement")
]
```
`noc_code` already exists (`:88`) — reuse it verbatim to read the claimed NOC; only `noc_duty` is new.

> **FK note (B1):** the new values also cross the `extracted_values.factor_id` FK to `crs_profile_factors` (enforced, `foreign_keys=ON`). They are linked to the dedicated inert `review.noc` factor (seeded once via `upsert_profile_factor` — seam (E) above), never `core.work`. `FactorGroup` is a closed 4-member Literal; `review.noc` uses `additional_points` and is never in `FULL_GRID_FACTORS`.

---

### `crawler/cli.py` (MODIFY — `vault noc-worksheet` + `vault noc-review` subverbs) — **EXACT analogs: `:1184`, `:1151`, `:1428`**

Reuse the existing PII-light envelope helpers and the **per-field, no-bulk** confirm surface. Do **not** add a new confirmation path — per-duty confirm/correct/reject flows through the shipped `vault confirm` verb unchanged (RESEARCH Pattern 4).

**PII-light envelope helpers — `_vault_ok` / `_vault_fail` (`crawler/cli.py:828-843`):**
```python
def _vault_fail(args, err_type, msg, code) -> int:
    if args.json: contract.emit(contract.envelope("vault", error=(err_type, msg)))
    else: print(f"error: {msg}", file=sys.stderr)
    return code

def _vault_ok(args, result, human) -> int:
    if args.json: contract.emit(contract.envelope("vault", result=result))   # PII-light dict only
    else: print(human, file=sys.stderr)                                      # human detail → stderr
    return 0
```

**Human-detail-to-stderr / json-PII-light split — `_cmd_vault_fields` (`crawler/cli.py:1169-1177`):**
```python
        if not args.json:
            for val in vals:
                view = confirm.build_field_view(v, val.value_id)
                print(confirm.format_field_view_human(view), file=sys.stderr)   # PII → stderr ONLY
        result = {"candidate_id": v.candidate_id, "count": len(summaries), "fields": summaries}
```
`vault noc-worksheet` mirrors this: worksheet/duty text → stderr in human mode; `--json` carries the PII-light `{noc_code, duty_count, value_ids, worksheet_doc_id, citations}`. `vault noc-review` emits the sidecar's closed dict.

**Subparser registration (one duty at a time; no bulk) — `p_confirm` (`crawler/cli.py:1522-1536`):**
```python
    p_confirm = vsub.add_parser("confirm",
        help="Confirm/correct/reject ONE field by --value-id (per-field only; no bulk confirm-all).")
    p_confirm.add_argument("--decision", required=True, choices=("confirm","correct","reject"))
    ...
    p_confirm.set_defaults(func=_cmd_vault_confirm)
```
Register `noc-worksheet` + `noc-review` under `vsub` (`_add_vault_subparser` `:1428`); add both to the `metavar` list (`:1437`). Preflight the corpus index with `_require_readable_index` (`:846`) before any compute (SAFE-10 zero-artifact ordering).

---

### `crawler/remediation.py` (MODIFY — reason alias, W1) — **EXACT analog: `_action_for` `:154-159`; reuse `:103-105`**

Per **W1**: the sidecar emits reason `duty_review_manual`, but the remediation action REUSES the shipped `unresolved_noc` template — **do NOT add a duplicate template**. Add a one-entry alias map and resolve it at the TOP of `_action_for` (before the `_ACTION_TEMPLATES.get` lookup). The existing `unresolved_noc` template (`:103-105`) is unchanged:
```python
# >>> ADD (Phase 43, W1): the sidecar's terminal manual-review reason reuses the
#     shipped unresolved_noc action — no duplicate template.
_REASON_ALIASES: dict[str, str] = {
    "duty_review_manual": "unresolved_noc",
}

def _action_for(factor_id: str, reason_code: str | None, kind: str) -> str:
    reason_code = _REASON_ALIASES.get(reason_code or "", reason_code)   # <<< resolve alias first
    template = _ACTION_TEMPLATES.get(reason_code or "")
    if template is None:
        template = _DEFAULT_ACTION_BY_KIND[kind]
    return template.format(factor=factor_id)
```
Result: `_action_for('core.work','duty_review_manual',kind)` is byte-identical to the `unresolved_noc` action. No inlined volatile threshold; unknown codes still degrade via `_DEFAULT_ACTION_BY_KIND` (`:141`).

---

### `crawler/extraction.py` (DO NOT MODIFY — factor isolation, B1)

**Do NOT** add `_DOC_TYPE_FACTOR["noc_worksheet"]` (`:264`) — routing the worksheet through the generic extractor would link duty values to a grid factor. The worksheet generator passes `factor_id="review.noc"` DIRECTLY (see seam (E) above), so this map stays untouched:
```python
_DOC_TYPE_FACTOR: dict[str, str] = {
    ...
    "job_offer": "additional.job_offer",
    # NO "noc_worksheet" entry — duty values are set to factor_id="review.noc" directly.
}
```

---

## Shared Patterns (apply across all Phase-43 plans)

### Fail-closed grounded retrieval (no second trust path)
**Source:** `crawler/searchindex.py:502-562` (`resolve`) — **Apply to:** `noc_worksheet.py`, `noc_review.py`.
Exact `chunk_id` lookup, positional bind, read-only URI, `None` on miss **or** drift. **Never** `searchindex.search()` (BM25, `:420`) — ranked retrieval can return a neighbor occupation (Pitfall 4).

### Quarantine → confirm → eligibility choke point (no parallel store) — on the inert `review.noc` factor
**Source:** `crawler/vault.py` `upsert_profile_factor` (`:482`, seed `review.noc` FK parent) → `add_extracted_value` (`:803`, forces `pending`, `factor_id="review.noc"`) → `confirm.apply_decision` (`crawler/confirm.py:119-136`) → `vault.confirm_value` (`:994-1045`, stamps 5 staleness keys) → `vault.audit_eligible_values("review.noc")` / `vault.is_audit_eligible` (`:1099`/`:1078`). **Apply to:** every per-duty value.
`apply_decision` acts on exactly one `--value-id` and never mutates another value — the **rubber-stamp defense is structural** (no bulk confirm-all). The `review.noc` factor keeps every duty value out of the frozen `core.work` card (B1): `audit_eligible_values("core.work")` never returns one.

### PII perimeter (vault-only artifacts, PII-light stdout)
**Source:** `crawler/paths.py::resolve_within` (`:123-146`) + `crawler/audit_report.py::SCREENING_NOTICE` (`:54`) + `_vault_ok`/`_vault_fail` (`crawler/cli.py:828-843`) + closed `PUBLIC_FIELDS` (`policy_offer.py:34-41`). **Apply to:** worksheet write, CLI, sidecar dict.
Worksheet + `raw_text` + absolute paths never cross `--json` (Pitfall 6). Prepend `SCREENING_NOTICE` (screening-not-legal-advice) to every rendered artifact.

### Inert-by-construction never-green (structural, not conditional)
**Source:** `crawler/policy_offer.py:1-80` + `crawler/auditors/__init__.py::_default_decider` (`:114-120`, unregistered ⇒ `AT-RISK`). **Apply to:** `noc_review.py`.
Constant/closed status set with **no branch that can emit `SUBSTANTIATED`**; module absent from dispatch/grid/envelope (Pitfall 1).

### No inlined volatile rules (grounded spans only)
**Source:** `crawler/tests/test_crs_no_inlined_rules.py` `_EXPORT_MODULES` (`:29-32`). **Apply to:** extend the scan to `noc_worksheet.py` + `noc_review.py` (mirror how `test_physician_policy.py::TestNoInlinedRules` `:329-336` added `policy_offer.__file__`). Duty text/lead statement/R87.1 standard come from grounded corpus spans, never inlined.

### Frozen-surface byte-identity (zero-diff regression proof)
**Source:** `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py:288-316` (`git diff --quiet HEAD -- <path>`, skip-guarded off a git checkout). **Apply to:** the new conformance test, scoped to the FREEZE set below.

---

## FREEZE Set (must show zero diff vs HEAD — assert in the negative-control conformance test)

| File / surface | Anchor | Why frozen |
|----------------|--------|-----------|
| `crawler/auditors/core.py::decide_work` | `:334-384` (`AT-RISK unresolved_noc` `:370-372`) | Stays `AT-RISK unresolved_noc`; duty confirmations never flip it green (NOC-03). |
| `crawler/crs_audit.py` (incl. `arranged_employment_guard`, `aggregate_work`) | whole file | Byte-frozen CRS logic; Phase-42 precedent already asserts this. |
| `crawler/auditors/__init__.py::FULL_GRID_FACTORS` / `register` / dispatch registry | `:104-154` | The NOC sidecar is **not** added here (inert); the inert `review.noc` factor is **not** added here either (it is a vault-data row only, never an audited grid factor). |
| `crawler/models/audit.py::PublicAuditEnvelope` / `to_public_envelope` / `substantiated_total` | `:125`, `:202`, `:216-282` | No NOC value ever summed into the CRS total or public envelope. |
| `crawler/review_packet.py` | whole file | Unchanged (as in Phase 42). |

---

## Test Pattern Assignments (Wave 0)

### `crawler/tests/test_noc_review.py` — **analog `crawler/tests/test_physician_policy.py`**
- Never-`SUBSTANTIATED` sweep over all-confirmed inputs → mirror `TestOfferSidecar` (`:353-402`): assert `status != "SUBSTANTIATED"` and `status in ("AT-RISK","GAP","N/A")` for every case; terminal state on full confirmation is `("AT-RISK","duty_review_manual")` (Pitfall 1).
- Deterministic split/stable-IDs idempotence; exact-retrieval + fail-closed absent NOC (`resolve(...#002)` → `None`); grouped-NOC verbatim; born-`pending` invariant; vault-only (no stdout PII).
- Per-duty confirm/correct/reject via shipped verb + staleness (Layer 1) + corpus-drift (Layer 2) demotion.
- **No-scoring source scan** — assert `noc_worksheet`/`noc_review` import no `difflib`/model/vector lib and contain no `.ratio(`/`SequenceMatcher`/float "match confidence" (Pitfall 2).
- Per-task map `-k` slices: `"worksheet or duties or citation"` (43-01), `"confirm or field or stale"` (43-02).

### `crawler/tests/test_noc_review_cli.py` — **analog `crawler/tests/test_extract_confirm_cli.py`**
- Drive `crawler.cli.main` over synthetic fixtures with the `_run(argv) -> (rc, stdout, stderr)` helper (`:203-210`) under a throwaway `$PR_PERSONAL_DIR`; `_one_envelope` (`:212`) parses the single stdout envelope.
- Assert: worksheet written only under vault; `--json` stdout is PII-light (no `raw_text`/duty text/abs path); human mode → stdout empty, detail on stderr; **one duty confirmed at a time** (no bulk).

### `crawler/tests/test_conformance_v5_noc_no_auto_green.py` — **analog `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py` (mirror wholesale)**
- `pytestmark = pytest.mark.conformance`; **v5 prefix intentionally OUTSIDE the v4.x release-gate glob** `test_conformance_v4[01]_*.py` — Phase 46 introduces the v5 glob; do **not** touch `scripts/run_conformance.py` (`:36-40`).
- Exhaustive sidecar sweep (unconfirmed/partial/rejected/stale/drifted) asserting no path is `SUBSTANTIATED`.
- `git diff --quiet HEAD -- <path>` byte-identity over the FREEZE set (`core.py`? scope to `crawler/auditors/core.py`, `crawler/crs_audit.py`, `crawler/models/audit.py`), skip-guarded off a git checkout (`_git_root` `:97-114`).
- Prove the sidecar is inert: not in `auditors._REGISTRY`, not in `FULL_GRID_FACTORS`, no NOC id in any `PublicAuditEnvelope`.
- **B1 factor isolation:** audit `core.work` via `crawler.auditor.audit_factor` (or `audit_one`) BEFORE and AFTER confirmed `review.noc` duty values and assert the `PrivateFactorCard` is byte-for-behavior identical (`verdict`, `reason_code`, `confirmed_value`, sorted `evidence_ids`, `substantiated_points`, `score_delta`) with NO NOC evidence id in `evidence_ids`; assert `review.noc` is absent from `FULL_GRID_FACTORS`. (`audit_eligible_values("core.work")` returns 0 review.noc values — VERIFIED.)

### `crawler/tests/test_crs_no_inlined_rules.py` (MODIFY) — add both new modules to `_EXPORT_MODULES` (`:29-32`).

### Deterministic NOC fixture chunks
Pull from the pinned corpus via `searchindex.resolve('noc-2021/noc-<code>.md#001..#003')` — verified live: `noc-21232` → 7 duties, `noc-53124` → grouped sub-occupation headers, `noc-99999` → `None`. No hand-written duty fixture needed (would fork the grounding path).

---

## No Analog Found

None. Every new/modified surface clones a shipped, release-gate-proven in-repo pattern (RESEARCH §Don't-Hand-Roll "Key insight: this is a composition phase"). The only novel code is thin deterministic glue (bullet split + stable-ID assignment) — itself a pure text op with no external analog needed and **no scoring primitive permitted**.

---

## Metadata

**Analog search scope:** `crawler/` (searchindex, grounding, vault, confirm, extraction, remediation, audit_report, paths, cli, policy_offer, auditors/, models/), `crawler/tests/`, `.planning/` (ROADMAP Phase-43 note, REQUIREMENTS NOC-01/02/03 + Out-of-Scope, STATE frozen invariants, Phase-42 03/04 summaries).
**Files scanned (read):** 18 code files + 4 planning docs (43-RESEARCH, 43-VALIDATION, ROADMAP §Phase-43, REQUIREMENTS, STATE, 42-03-SUMMARY) + 3 test analogs.
**Pattern extraction date:** 2026-07-19
**Read-only run:** the only file written is this `43-PATTERNS.md`; no source file was modified.
