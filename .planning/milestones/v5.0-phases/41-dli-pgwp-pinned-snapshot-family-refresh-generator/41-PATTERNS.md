# Phase 41: DLI/PGWP Pinned Snapshot Family & Refresh Generator — Pattern Map

**Mapped:** 2026-07-18
**Files analyzed:** 8 CREATE + 2 MODIFY (10)
**Analogs found:** 10 / 10 (every planned file rides a shipped, verified seam)

> No CONTEXT.md exists by design (autonomous planning). The CREATE/MODIFY list is
> taken from `41-RESEARCH.md` §CREATE/MODIFY/FREEZE Map (lines 812-836) and the
> recommended structure (lines 286-303). Every analog below was read live in this
> session; line numbers are current as of 2026-07-18.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `crawler/dli_snapshot.py` **(NEW)** | service / generator (stdlib module) | fetch → validate → transform → file-I/O (full-family write) | `crawler/deepcrawl.py` (front-matter emit + manifest) + `crawler/pipeline.py` (pure-fn split) + `searchindex.chunk_sha` (hashing) | composite / role-match (no offline JSON→md generator exists yet) |
| `crawler/data/crs_rules/study_dli.yaml` **(NEW)** | config (declarative rule row) | CRUD (loaded, never mutated at runtime) | `crawler/data/crs_rules/additional.yaml` → `additional.job_offer.current` (44-73) | exact |
| `crawler/cli.py` → `_cmd_refresh_dli` + `refresh-dli` subparser **(MODIFY)** | controller (top-level CLI verb) | request-response | `crawler/cli.py::_cmd_index` (245-291) + `p_index` registration (1567-1572) | exact |
| `corpus/dli/*.md` + `corpus/dli/manifest.json` **(GENERATED, git-ignored)** | data artifact (corpus family + provenance) | file-I/O output | `deepcrawl` per-page `*.md` (135-141) + `manifest.json` (146-147) | role-match |
| `crawler/tests/fixtures/dli/dli-sample.json` + `crawler/tests/fixtures/dli/golden/dli/*.md` **(NEW)** | test fixture (committed, PII-free) | file-I/O input | `crawler/tests/fixtures/*` + `test_searchindex` synthetic corpus (251-357) | role-match |
| `crawler/tests/test_dli_snapshot.py` **(NEW)** | test (unit) | transform / determinism | `test_searchindex.py` (chunk determinism 214, `_IndexCase` 357) | role-match |
| `crawler/tests/test_dli_refresh_cli.py` **(NEW)** | test (CLI integration) | request-response | `test_json_contract.py` (`cli.main` invoke 46, envelope round-trip 88-90) + `test_snapshot_refusal.py` | exact |
| `crawler/tests/test_dli_grounding.py` **(NEW)** | test (integration + grounding) | pub-sub / retrieval | `test_conformance_v40_retrieve_what_you_cite.py` (skipUnless 99-101) + `test_snapshot_health._build_snapshot_index` (24-52) | exact |

---

## Pattern Assignments

### `crawler/dli_snapshot.py` (service/generator — fetch → validate → transform → write)

**Analogs:** `crawler/deepcrawl.py` (front-matter + manifest emit), `crawler/pipeline.py` (pure-function split for offline testability), `crawler/searchindex.py::chunk_sha` (hashing convention), `crawler/paths.py` (containment — GENERIC helpers only).

**Imports pattern** (stdlib-only; mirror `deepcrawl.py:21-28` but DROP the `crawl4ai` imports):
```python
from __future__ import annotations
import hashlib, json, re, unicodedata
import urllib.request, urllib.error
from pathlib import Path
# NO crawl4ai / httpx / requests — zero new dependency (RESEARCH §Standard Stack 191-201).
```

**Pure-function split for network-free testing** — copy the seam discipline from `crawler/pipeline.py:5-9,65-124` (the `classify` pure fn factored out of `deepcrawl`'s loop). Keep `fetch()` a ≤5-line network seam; put ALL logic in `normalize(payload, *, as_of)` / `write(docs, out_dir)` so tests call pure fns or patch `dli_snapshot.fetch` (RESEARCH Pattern 1, 305-335):
```python
def fetch(*, timeout: int = 60) -> tuple[dict, str | None]:
    req = urllib.request.Request(_DLI_URL, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # nosec — FIXED authoritative host
        last_modified = r.headers.get("Last-Modified")
        payload = json.loads(r.read().decode("utf-8"))
    return payload, last_modified
```
> **SSRF guard (V13, RESEARCH 782):** `_DLI_URL` is a hard-coded module constant. Expose NO `--url`. Set an explicit `timeout`. Do not follow off-canada.ca redirects. Add a response-size sanity bound before `json.loads` (DoS mitigation, RESEARCH 789).

**Front-matter emit idiom** — copy VERBATIM from `crawler/deepcrawl.py:135-141` (this is THE corpus front-matter convention; `json.dumps` quotes/escapes safely). Adapt the `front` dict keys per RESEARCH Pattern 2 (338-356) — add `source_type:"dli"`, `dli_number`, `crawl_date` (= upstream `Last-Modified`, NOT `_now()`), `content_sha256`, `status_scope:"current-only"`, `label`, `generator:"ircc-dli-json"`:
```python
# crawler/deepcrawl.py:139-141 (reuse the join idiom verbatim; ensure_ascii=False keeps NFC bytes)
fm = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}"
                         for k, v in front.items()) + "\n---\n\n"
(out_dir / f"{dli}.md").write_text(fm + body, encoding="utf-8")
```
> **CRITICAL divergence from `deepcrawl`:** `deepcrawl.py:137` stamps `"crawl_date": _now()` (wall-clock). Phase 41 MUST derive `crawl_date` from `Last-Modified` (RESEARCH Alternatives 222, Pitfall 2 484-488; SC3). Wall-clock in the hashed body breaks byte-reproducibility.

**Content-hash provenance** — mirror `searchindex.chunk_sha` (`crawler/searchindex.py:128-135`, `hashlib.sha1[:12]`) and `dupaudit.body_hash` (`crawler/dupaudit.py:80-87`, `hashlib.sha1(body_of(text))`). RESEARCH prescribes `hashlib.sha256` over the **body only** (373-376):
```python
def _body_sha256(body: str) -> str:
    return hashlib.sha256(unicodedata.normalize("NFC", body).encode("utf-8")).hexdigest()
```
> Hash the BODY, never the front-matter (the volatile `crawl_date` lives in front-matter). Same upstream payload → identical body → identical hash across runs.

**Normalization / grouping / determinism** (RESEARCH Pattern 1, 324-334 + landmine table 167-177):
```python
_DLI_RE = re.compile(r"^O\d{6,}$")
def _nfc(s: str) -> str: return unicodedata.normalize("NFC", s)
# group by DLI# after .strip(); skip rows failing _DLI_RE (fail-closed, never a garbage doc);
# sort by DLI# asc then (City, Campus); preserve PER-CAMPUS PGWP verbatim incl. "Details".
```
Landmines that MUST be handled deterministically (RESEARCH 167-177): trailing-space DLI# `.strip()`; same DLI# → multiple names (union, per-DLI doc); conflicting per-campus PGWP (2 cases — keep a per-campus table, never collapse); NFC on 332 non-ASCII names; `PGWP ∈ {Yes,No,Details}` verbatim (never follow `Details` sub-pages).

**Strict closed-schema validation** (safe-ingestion boundary — RESEARCH Open-Q2 680-681, Security V5 779): assert top-level `data` is a list; each row has EXACTLY the nine known keys (`Province, Institution, DLI #, City, Campus, Grad Program, PGWP, HTML, Public/Private`) with string values; `DLI #` matches `_DLI_RE` after strip; `PGWP ∈ {Yes,No,Details}`. Any empty/truncated/extra-key/missing-field or malformed row raises
`SchemaError` and aborts the whole refresh — never silently skip a bad row or publish a partial subset.

**Error handling** — define a local `class SchemaError(Exception)` (analog: `searchindex.FTS5Unavailable` at `crawler/searchindex.py:120`, and `paths.PathEscapeError` at `crawler/paths.py:40-48`, both `ValueError`/`Exception` subclasses the CLI maps to `invalid_input`/exit 2). `as_of_from(last_modified)` raises `SchemaError` when `Last-Modified` is absent/unparseable (fail-closed D2, RESEARCH 664) — NEVER substitute wall-clock.

**Atomic full-family replace** (RESEARCH Pattern 3, 378-386): `write(docs, out_dir)` resolves and honors the requested family root, contains each validated DLI filename beneath it, stages into a sibling temp directory, validates, then swaps with rollback. The CLI is the only production caller and passes fixed `Path("corpus/dli")`; tests pass temporary/golden roots. Upstream-removed institutions leave no stale `.md`, and any failed write preserves the prior healthy family.

**Path containment — USE THE GENERIC HELPERS, NOT THE VAULT ONES** (see Pitfalls below): set `root = Path(out_dir).resolve()` and contain each file with `paths.resolve_within(root, f"{dli}.md")` (`crawler/paths.py:123-146`). Filename = validated `^O\d{6,}$` DLI number only. The CLI fixes `out_dir` to `corpus/dli`; accepting `out_dir` at the pure function boundary is required for isolated temp/golden tests.

**Manifest (non-indexed)** — mirror `deepcrawl.py:146-147` `manifest.json` write, but the DLI manifest carries source URL, as-of/`Last-Modified`, `family_sha256`, current-status-only note, generator id. It is `.json` (no `.md`), so `dupaudit.live_docs` never enumerates it (RESEARCH Pattern 4, 388-395) and it is NEVER cited by a rule row.

---

### `crawler/cli.py` — `_cmd_refresh_dli` + `refresh-dli` subparser (controller, request-response)

**Analog:** `crawler/cli.py::_cmd_index` (245-291) — the thin dispatcher: validate → lazy-import compute module → map errors to contract envelope → human summary to stderr.

**Handler skeleton** (copy the `_cmd_index` shape at `cli.py:255-291`; RESEARCH code example 543-579):
```python
def _cmd_refresh_dli(args) -> int:
    from crawler import dli_snapshot                       # LAZY import (cli.py:257 pattern)
    try:
        payload, last_modified = dli_snapshot.fetch()      # network ONLY here
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        msg = f"could not fetch DLI dataset: {exc}"
        if args.json:
            contract.emit(contract.envelope("refresh-dli", error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT
    try:
        as_of = dli_snapshot.as_of_from(last_modified)
        docs = dli_snapshot.normalize(payload, as_of=as_of)
    except dli_snapshot.SchemaError as exc:
        # mirror _cmd_index's FTS5Unavailable branch (cli.py:272-281)
        ...
        return contract.EXIT_INVALID_INPUT
    result = dli_snapshot.write(docs, out_dir=Path("corpus/dli"))
    if args.json:
        contract.emit(contract.envelope("refresh-dli", result={
            "out": "corpus/dli", "institutions": result["docs"], "campuses": result["rows"],
            "as_of": as_of, "family_sha256": result["family_sha256"]}))   # PII-free provenance ONLY
    else:
        print(f"dli: {result['docs']} institutions ... -> corpus/dli", file=sys.stderr)
    return 0
```

**Subparser registration** — copy the `p_index` block at `cli.py:1567-1572` (TOP-LEVEL, on `subparsers` from `cli.py:1520`). Register beside `p_index`/`p_crawl`; call `p_refresh.set_defaults(func=_cmd_refresh_dli)`. **There is NO `corpus` parent** — `_add_vault_subparser` (`cli.py:1629`, defined 1344-1505) is the ONLY nested verb tree (RESEARCH 828). Extend the `add_subparsers(..., metavar=...)` string at `cli.py:1521` to include `refresh-dli`.

**Expose NO `--url`, `--out`, or `--from-file`** (RESEARCH 538-540, 828): the verb fetches `_DLI_URL` and writes only `corpus/dli/`. Unlike `p_index` (which takes a `corpus_dir` positional + `--db`, `cli.py:1569-1571`) and `p_crawl` (`--seed`/`--out`, `cli.py:1526-1531`), `refresh-dli` takes no path/URL args at all. Tests patch `dli_snapshot.fetch` or call pure fns — they never pass a URL.

**Envelope + exit codes** — reuse `contract.envelope`/`contract.emit` (`crawler/contract.py:63-96`) with `command="refresh-dli"`; `contract.INVALID_INPUT`/`EXIT_INVALID_INPUT` (=2) for fetch/schema failure (`contract.py:48,57`). The five-key envelope (`schema_version, ok, command, result, error`) is frozen. `main()`'s `--json` catch-all (`cli.py:1657-1667`) already wraps unexpected exceptions into `internal_error`.

**Do NOT wire `_require_readable_snapshot`** (`cli.py:779-808`) into this verb — that Phase-40 preflight is defined-only and belongs to the Phase-44 audit path (it consumes `max_age_days`, which is Phase-44 config). Phase 41 only WRITES the family.

---

### `crawler/data/crs_rules/study_dli.yaml` (config — one grounded rule row)

**Analog:** `crawler/data/crs_rules/additional.yaml` → `additional.job_offer.current` (44-73) and `additional.nomination` (10-42). Auto-loaded by `crs_rules.load_registry` which globs `*.yaml` sorted, skips `_`-prefixed, `yaml.safe_load` only (`crawler/crs_rules.py:107-116`). Zero loader change.

**Row shape** (validated against `RuleRow`, `crawler/models/crs_rules.py:192-258`) — ship EXACTLY ONE row `study.dli.designation` (RESEARCH 589-615):
```yaml
rows:
  - rule_id: study.dli.designation
    factor_group: additional_points       # FactorGroup Literal — crawler/models/vault.py:33-40 (member 37)
    factor_ids: [study.dli.designation]    # inert namespace; Phase 44 explicitly consumes it
    check_type: admissibility             # CheckType Literal — models/crs_rules.py:59-66
    query: "University of Toronto designated learning institution DLI number"
    selector:
      family: dli                         # -> searchindex.search family='dli' (relpath LIKE 'dli/%')
      marker: "DLI number: O19332746152"  # deterministic chunk #000 selection in the full family
    claim_text: >-
      University of Toronto is a designated learning institution identified by DLI
      number O19332746152 in the current IRCC list (current status only).
    citations:
      - chunk_id: dli/O19332746152.md#000 # must match _CHUNK_ID_PATTERN r"^[^#\s]+#\d+$" (models/crs_rules.py:39)
        quote: "DLI number: O19332746152" # ASCII line — verbatim substring of the generated body
    machine_check:
      kind: accepted_enum                 # MachineCheckKind Literal — models/crs_rules.py:45-53
      field: dli_number
      accepted_values:
        - {value: "O19332746152", citation_index: 0}
    volatility:
      volatility: volatile                # VolatilityMeta — models/crs_rules.py:173-190
      source_family: dli
      crawl_date: "2026-07-16"
```
> **Model constraints to respect:** `extra="forbid"` on every sub-model (a typo'd key fails LOUD at load); `citations` min_length 1 (`models/crs_rules.py:217`); `accepted_values[].citation_index` must be in range (`models/crs_rules.py:236-258`); `rule_id` no whitespace (`models/crs_rules.py:224-234`). Cite an **ASCII** line to dodge the grounding gate's no-Unicode-folding rule (Pitfall 5).

**NO `safe.dli_snapshot.max_age` row this phase** (RESEARCH 586-587, 818): the operational max-age is Phase-44 config. Phase 40 already ships the field-name-only contract `_FRESHNESS_FIELD = {"dli_snapshot": "snapshot_max_age"}` (`crawler/crs_audit.py:47`) and proved the mechanism with a **synthetic** `window_days=180` fixture (`test_freshness_staleness.py:64-81`, illustrative only). The new `study_dli.yaml` is expected; assert specifically that it contains only `study.dli.designation` and no max-age/bound row.

---

### `corpus/dli/*.md` + `corpus/dli/manifest.json` (generated corpus family — git-ignored)

**Analog:** `deepcrawl` per-page `.md` (`deepcrawl.py:135-141`) + `manifest.json` (`deepcrawl.py:146-147`). `.gitignore:8` ignores `corpus/` — the real family is generated by the operator running `corpus-crawler refresh-dli` then `corpus-crawler index`.

**Discovery contract** (must be honored so `dupaudit.live_docs` enumerates each doc — `crawler/dupaudit.py:146-166`):
- Each `.md` MUST start with `---` front-matter (line 164 drops files without it).
- Files under `_dropped/`/`completeness/`, `REPORT.md`, `*.live.md` are excluded (159-161) — irrelevant here but do not name docs that way.
- `manifest.json` is NOT `.md` → never enumerated → never indexed → never cited (RESEARCH Pattern 4).

**Auto-index** (`searchindex.build_index`, `crawler/searchindex.py:336-358`, ZERO change): reads front-matter `url/title/crawl_date/source_type` (342-345), computes `relpath` (346), splits body via `body_of` (347), bakes `chunk_id = f"{relpath}#{ordinal:03d}"` (350) — so `dli/O19332746152.md` → citation `dli/O19332746152.md#000`. The `source_type`/`crawl_date` columns exist (`searchindex.py:71-72`).

---

### Test files — `test_dli_snapshot.py`, `test_dli_refresh_cli.py`, `test_dli_grounding.py`

**Framework:** `unittest` classes run via `pytest` (repo convention). Network-free via committed fixture (`41-VALIDATION.md`).

**`test_dli_snapshot.py`** — analog `test_searchindex.py`. Reuse its synthetic-tempdir discipline (`test_searchindex.py:251-357`) and determinism assertion (`test_chunk_is_deterministic`, 214). Load `fixtures/dli/dli-sample.json`, call `normalize`/`write` into a `TemporaryDirectory`, assert: byte-identical bytes + identical `content_sha256` across two runs; exact `<DLI#>.md` filenames; shared-DLI name union; trailing-space strip; per-campus conflicting PGWP preserved; NFC on non-ASCII; malformed-DLI skip; empty/truncated `data` → refusal; atomic-replace deletes a removed institution's file; `status_scope: current-only` present in EVERY doc front-matter AND body; `no_inlined_volatile_rules(["crawler/dli_snapshot.py","crawler/cli.py"]) == []` (`crs_rules.py:458-498`); no `safe.dli_snapshot.max_age` / max-age literal.

**`test_dli_refresh_cli.py`** — analog `test_json_contract.py` (invoke `cli.main(argv)` at line 46; `json.loads(stdout)` round-trip 88-90) + `test_snapshot_refusal.py`. Patch `dli_snapshot.fetch` to inject the fixture payload. Invoke `cli.main(["--json", "refresh-dli"])`: global `--json` MUST precede the subcommand. Assert the five-key PII-free envelope; fetch/schema error → `ok:false`/`invalid_input`/exit 2 with a healthy prior family untouched.

**`test_dli_grounding.py`** — analog `test_conformance_v40_retrieve_what_you_cite.py` + `test_snapshot_health._build_snapshot_index` (24-52). Build a real FTS5 index with root `fixtures/dli/golden/` (whose child is `dli/`) so citation IDs are `dli/…#000`. Assert `source_type='dli'` via `SELECT source_type FROM chunks WHERE chunk_id=?` (the public `resolve()` result omits this column), and check `crawl_date` through `resolve()`. Then a dli-only registry subset grounds `study.dli.designation`, and `retrieve_what_you_cite` returns `agrees_with_citation=True` + `grounds=True`. Assert NO `safe.dli_snapshot.max_age` row exists.

**`fixtures/dli/dli-sample.json` + golden family** — curated 8-12 rows covering every landmine. Generate the committable `fixtures/dli/golden/dli/*.md` family by running the generator over the sample; `fixtures/dli/corpus/` must not be used because `.gitignore` ignores `corpus/` at any depth.

---

## Shared Patterns

### Contract envelope + exit codes
**Source:** `crawler/contract.py` — `envelope` (63-87), `emit` (90-96), `INVALID_INPUT` (48), `EXIT_INVALID_INPUT`=2 (57), `MISSING_DEPENDENCY`/`EXIT_MISSING_DEPENDENCY`=3 (45,58), `SCHEMA_VERSION`="1.0" (41).
**Apply to:** `_cmd_refresh_dli`, `test_dli_refresh_cli.py`. Exactly one `json.dumps` object to stdout; human/progress → stderr; `refresh-dli` is a NEW `command` value in the five-key envelope.

### Front-matter emit
**Source:** `crawler/deepcrawl.py:135-141` (`"---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" ...)`).
**Apply to:** `dli_snapshot._build_doc`. Reuse verbatim; swap `crawl_date=_now()` → `crawl_date=as_of` (upstream `Last-Modified`).

### Content hashing
**Source:** `searchindex.chunk_sha` (`searchindex.py:128-135`) / `dupaudit.body_hash` (`dupaudit.py:80-87`).
**Apply to:** `dli_snapshot._body_sha256` (sha256, body-only, NFC-normalized).

### Path containment — GENERIC helpers only
**Source:** `crawler/paths.py` — `repo_root` (51-59), `is_within` (112-120), `resolve_within` (123-146), `PathEscapeError` (40-48).
**Apply to:** `dli_snapshot.write`. Anchor containment at resolved `out_dir`; the CLI supplies fixed `corpus/dli`, while tests supply temp/golden roots. **DO NOT call `personal_root`/`candidate_root`/`safe_candidate_id`/`repo_personal_root`** (paths.py:62-109,149-172) — those resolve the git-ignored PII vault, not the public corpus.

### FTS5 auto-index (frozen, zero change)
**Source:** `searchindex.build_index` (300-372) walking `dupaudit.live_docs` (146-166). `chunk_id = relpath#ordinal` (350).
**Apply to:** operator runs `corpus-crawler index corpus/ --db corpus/index.db` after refresh; `test_dli_grounding.py` builds over the fixture family. Nothing in `searchindex`/`dupaudit` is edited.

### Registry load + grounding gate (frozen, zero change)
**Source:** `crs_rules.load_registry` globs `*.yaml` (95-118); `validate_registry` (168-196); `retrieve_what_you_cite` (231-274); `no_inlined_volatile_rules` (458-498); `grounding.quote_is_grounded` (`grounding.py:87-99`, `_norm` 78-84 — whitespace/case only, **no Unicode folding**).
**Apply to:** `study_dli.yaml`, `test_dli_grounding.py`, `test_dli_snapshot.py` (static scan). Cite an ASCII line so the no-fold gate matches.

---

## Frozen Contracts (reuse byte-for-byte — DO NOT MODIFY)

Per `41-RESEARCH.md` FREEZE map (831-836). Consumed here but frozen:

| Symbol | File:line | Role in Phase 41 |
|--------|-----------|------------------|
| `searchindex.build_index` / `chunk_sha` / `search`(family) / `resolve` | `searchindex.py:300,128,420,502` | auto-index + citation resolution (zero change) |
| `dupaudit.live_docs` / `body_of` / `_frontmatter_of` | `dupaudit.py:146,65,90` | doc enumeration requires leading `---` front-matter |
| `crs_rules.load_registry` / `validate_registry` / `retrieve_what_you_cite` / `registry_fingerprint` / `no_inlined_volatile_rules` | `crs_rules.py:95,168,231,121,458` | loads `study_dli.yaml`, grounds the one row |
| `models/crs_rules.RuleRow` / `Citation`(`_CHUNK_ID_PATTERN`) / `MachineCheck` / `VolatilityMeta` / `Selector` | `models/crs_rules.py:192,90/39,139,173,71` | validates the row SHAPE at load |
| `grounding.check_answer` / `quote_is_grounded` / `_norm` | `grounding.py:185,87,78` | the ONE grounding gate (no fork) |
| `index_health.probe_snapshot` / `SnapshotHealth` / `SNAPSHOT_*` | `index_health.py:224,196,59-65` | Phase-40 preflight; consumed by Phase 44/45, NOT wired in 41 |
| `cli._require_readable_snapshot` | `cli.py:779-808` | defined-only; Phase-44 chokepoint, NOT wired here |
| `crs_audit.within_freshness` / `row_in_effect` / `_FRESHNESS_FIELD` | `crs_audit.py:173,377,47` | Phase 41 only stamps the `crawl_date` these read; window is Phase-44 config |
| `contract.envelope` / `emit` / `EXIT_*` | `contract.py:63,90,57-60` | five-key envelope |
| `crawler/paths.py` (`repo_root`/`is_within`/`resolve_within`) | `paths.py:51,112,123` | containment (generic helpers only) |

---

## New Phase-41 Symbols vs Existing (do not confuse)

| NEW (create this phase) | Nearest EXISTING (do not edit/reuse-as-is) |
|-------------------------|--------------------------------------------|
| `dli_snapshot.py` (`fetch`, `as_of_from`, `normalize`, `write`, `SchemaError`, `_DLI_URL`, `_DLI_RE`, `_nfc`, `_build_doc`, `_body_sha256`, `_write_manifest`) | `deepcrawl.crawl` (network+crawl4ai); `pipeline.PageClassifier` (HTML classify); `searchindex.chunk_sha` |
| `cli._cmd_refresh_dli` + `refresh-dli` subparser | `cli._cmd_index` (245); `cli._cmd_crawl`; `_add_vault_subparser` (the ONLY nested tree) |
| rule `study.dli.designation` (in new `study_dli.yaml`) | `additional.job_offer.current` (additional.yaml:44); the **synthetic** `safe.dli_snapshot.max_age` fixture in `test_freshness_staleness.py:74` (NOT a shipped row — do not create it) |
| `corpus/dli/*.md` family + `manifest.json` | `corpus/noc/…`, `deepcrawl` `manifest.json` |
| `test_dli_snapshot.py` / `test_dli_refresh_cli.py` / `test_dli_grounding.py` | `test_searchindex.py` / `test_json_contract.py` / `test_conformance_v40_retrieve_what_you_cite.py` |

**Boundary preservation (Phase 41 does NOT touch these — RESEARCH 800-808):** no `decide_study`/decider wiring; no vault fields/migration; no `Details` sub-page crawl; no `arranged_employment_guard`/CRS-grid/`PublicAuditEnvelope` change; no `safe.dli_snapshot.max_age` (Phase-44 config); no v5.0 conformance module / release gate (Phase 46); no scheduler/cron; no new dependency.

---

## Likely Pitfalls (per file)

- **`dli_snapshot.py`:** wall-clock `crawl_date` in the hashed body (use `Last-Modified`); hashing front-matter instead of body-only; collapsing per-campus PGWP; institution-name filenames/matching (use DLI#); following `Details` links; using `personal_root`/`candidate_root` instead of `repo_root`+generic containment; reading the vault (generator reads ONLY the IRCC dataset — Pitfall 4).
- **`study_dli.yaml`:** citing a non-ASCII line (grounding gate has no Unicode folding — cite the `DLI number: O…` ASCII line, Pitfall 5); shipping a `safe.dli_snapshot.max_age` row / self-grounding a `manifest`/`00-about` doc (Pitfall 7); an out-of-range `citation_index`; a `chunk_id` not matching `relpath#ordinal`.
- **`cli.py`:** nesting under a non-existent `corpus` parent (register top-level on `subparsers`); adding `--url`/`--out`/`--from-file` (SSRF / accidental publication); forgetting to extend the `metavar` at cli.py:1521.
- **Tests:** hand-editing a golden `corpus/dli/*.md` (regenerate from `dli-sample.json`, Pitfall 6); hitting the network (patch `dli_snapshot.fetch`); a max-age literal appearing in Phase-41 code tripping `no_inlined_volatile_rules`.

---

## No Analog Found

| File | Role | Data Flow | Reason / Mitigation |
|------|------|-----------|---------------------|
| `crawler/dli_snapshot.py` (as a whole) | service/generator | offline JSON → markdown family | No shipped module fetches a structured JSON dataset and writes a corpus family offline (the v2.1 NOC-CSV ingest was a one-off, not in-repo). It is a COMPOSITE of verified analogs: `deepcrawl` (front-matter/manifest emit), `pipeline` (pure-fn split), `searchindex.chunk_sha` (hashing), `paths` (containment). Follow RESEARCH §Code Examples (531-632) + Patterns 1-4 (305-404) for the parts with no single analog. |

---

## Metadata

**Analog search scope:** `crawler/` (cli, deepcrawl, pipeline, contract, paths, searchindex, dupaudit, grounding, crs_rules, crs_audit, index_health, models/), `crawler/data/crs_rules/`, `crawler/tests/`, `scripts/`, `.gitignore`.
**Files scanned (read live):** deepcrawl.py, contract.py, paths.py, cli.py (245-340, 742-830, 1508-1672), searchindex.py (120-145, 300-375, 420-560), dupaudit.py (65-167), grounding.py (78-99), crs_rules.py (95-135, 168-320, 458-510), models/crs_rules.py (full), models/vault.py (FactorGroup), crs_audit.py (38-48, 173-200), index_health.py (56-304), additional.yaml, test_snapshot_health.py, test_searchindex.py, test_json_contract.py, test_freshness_staleness.py, test_conformance_v40_retrieve_what_you_cite.py.
**Pattern extraction date:** 2026-07-18
