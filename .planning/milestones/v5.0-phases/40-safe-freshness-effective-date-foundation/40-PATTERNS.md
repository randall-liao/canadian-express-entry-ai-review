# Phase 40: SAFE Freshness & Effective-Date Foundation - Pattern Map

**Mapped:** 2026-07-17
**Files analyzed:** 7 source/data symbols created/modified + 5 test files (2 extended, 3 new)
**Analogs found:** 12 / 12 (every deliverable is a promote-or-mirror of a shipped, tested symbol)

> **Phase nature:** This is a *foundation* phase — every new symbol is a byte-close mirror or a
> literal extraction of an already-shipped primitive. There is **no green-field construction**;
> the risk is *omission* (a helper that forgets to fail closed) and *drift* (a promotion that
> silently changes the frozen CRS grid), not invention. Copy the analogs' fail-closed shape exactly.
>
> **No CONTEXT.md** — intentional (`workflow.skip_discuss: true`, autonomous execution). ROADMAP.md
> Phase 40, REQUIREMENTS.md SAFE-09/SAFE-10, RESEARCH.md, VALIDATION.md, and the shipped code are
> authoritative.

---

## File Classification

| New/Modified Symbol | File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|------|-----------|----------------|---------------|
| `within_freshness()` (CREATE) | `crawler/crs_audit.py` | decision-core utility | transform (pure date math over grounded window) | `within_validity` `crs_audit.py:142` | exact (sibling) |
| `row_in_effect()` (CREATE) | `crawler/crs_audit.py` | decision-core utility | transform (effective-window predicate) | `_in_window` `crs_audit.py:333` + guard `:364-371` | exact (composition) |
| `_FRESHNESS_FIELD` map (CREATE) | `crawler/crs_audit.py` | config constant | lookup | `_VALIDITY_FIELD` `crs_audit.py:35` | exact |
| `gate_subset()` (CREATE via rename) | `crawler/auditor.py` | grounding-gate service | request-response / validation | `_gate_or_raise` `auditor.py:75` | exact (literal extraction + alias) |
| `probe_snapshot()` + `SnapshotHealth` (CREATE) | `crawler/index_health.py` | preflight service | file-I/O (read-only DB probe) | `probe_index` + `IndexHealth` `index_health.py:59,85` | exact (mirror + 2 new codes) |
| `SNAPSHOT_*` reason codes (CREATE) | `crawler/index_health.py` | closed vocabulary constants | lookup | `INDEX_*` `index_health.py:43-48` | exact |
| `_require_readable_snapshot()` (CREATE) | `crawler/cli.py` | CLI preflight wrapper | request-response / guard | `_require_readable_index` `cli.py:760` | exact |
| Grounded staleness-bound row (DEFERRED to Phase 41 / STUDY-01) | Future `crawler/data/crs_rules/*.yaml` row | grounded config/data | data (registry row) | ECA/language `validity_window` rows `core.yaml:81-106,195-219` | exact; Phase 40 proves the mechanism with synthetic grounded fixtures because the current corpus has no authoritative fixed DLI max-age span (see Plan 40-01 T-40-A2) |
| `_gate_or_raise` → `gate_subset` (MODIFY) | `crawler/auditor.py` | grounding-gate service | request-response | self (rename + `_gate_or_raise = gate_subset` alias) | exact |
| Static-gate scan surface (MODIFY, if a new `.py` module lands) | `crawler/tests/test_crs_no_inlined_rules.py:35-49` | test surface list | batch scan | existing `_registry_and_auditor_surface()` | exact |
| `test_freshness_staleness.py` (CREATE) | `crawler/tests/` | test (unit) | table / negative controls | `test_crs_audit.py` (`TestWithinValidity:137`, `_row:28`, `_validity_registry:70`) | exact |
| `test_snapshot_health.py` (CREATE) | `crawler/tests/` | test (unit table) | table / fixture DB | `test_index_health.py` (`_build_valid_index:20`) | exact |
| `test_snapshot_refusal.py` (CREATE) | `crawler/tests/` | test (integration CLI) | request-response + artifact assertion | `test_audit_index_refusal.py` (`_assert_refusal:71`) | exact |
| `test_crs_rules.py` fingerprint extension (MODIFY) | `crawler/tests/` | test (unit) | transform | `registry_fingerprint` `crs_rules.py:121` (usage in `test_review_packet_cli.py:75`) | role-match |

---

## Pattern Assignments

### `crawler/crs_audit.py` :: `within_freshness()` + `row_in_effect()` (decision-core utility, transform)

**Analog:** `crawler/crs_audit.py` — `within_validity` (`:142`), `_window_days` (`:58`), `_as_date` (`:48`), `_in_window` (`:333`), `_VALIDITY_FIELD` (`:35`). New functions live in this SAME module, beside their analogs.

**Imports / constants pattern** (`crs_audit.py:23-35`) — the module is stdlib `datetime` only; add the new kind→field map beside `_VALIDITY_FIELD`:
```python
from datetime import date, timedelta
from crawler import crs_rules
from crawler.models.crs_rules import Registry, RuleRow

# Semantic validity kinds → the grounded machine_check field carrying the window.
_VALIDITY_FIELD = {"language": "test_date", "eca": "eca_report_date"}
# NEW — sibling map for freshness kinds (e.g. {"dli_snapshot": "snapshot_max_age"})
```

**Core pattern to COPY — grounded-window freshness** (`within_validity`, `crs_audit.py:142-155`). `within_freshness` is a byte-close sibling; the ONLY structural rule is "no grounded window ⇒ `False`":
```python
def within_validity(kind: str, issued_date, reference_date, registry: Registry) -> bool:
    field = _VALIDITY_FIELD.get(kind, kind)
    window = _window_days(registry, field)     # grounded — never a literal
    if window is None:
        return False                           # <-- FAIL-CLOSED: no window ⇒ not valid
    delta = (_as_date(reference_date) - _as_date(issued_date)).days
    return 0 <= delta <= window                # after-reference (delta<0) also fails
```
The grounded-window reader it MUST reuse (never re-implement) — `_window_days` (`crs_audit.py:58-63`):
```python
def _window_days(registry: Registry, field: str):
    for row in registry.rows:
        mc = row.machine_check
        if mc.kind == "validity_window" and mc.field == field:
            return mc.window_days
    return None
```

**Core pattern to COPY — effective-window predicate** (`_in_window`, `crs_audit.py:333-340`) and the two window sources `arranged_employment_guard` reads today (`crs_audit.py:364-371`, `MachineCheck.effective_from/to` + `VolatilityMeta.effective_from/to`). `row_in_effect` composes `_in_window` over BOTH sources; a row with both windows `None` is stable/effective (returns `True`):
```python
def _in_window(when, effective_from, effective_to) -> bool:
    d = _as_date(when)
    if effective_from is not None and d < _as_date(effective_from):
        return False
    if effective_to is not None and d >= _as_date(effective_to):   # half-open [from, to)
        return False
    return True
```
The `arranged_employment_guard` read to consolidate (`crs_audit.py:370-371`) — this is the exact pair of window checks `row_in_effect` should generalize:
```python
if legacy is not None and not legacy.gap:
    if _in_window(ita_date, legacy.volatility.effective_from, legacy.volatility.effective_to):
        ...
```

**Fail-closed convention (frozen):** `within_validity`'s "no window ⇒ `False`" (`:152`) is the milestone's dominant-risk mitigation — replicate it verbatim in `within_freshness`; do NOT add a numeric default (Pitfall 3). `row_in_effect` must fail closed on a malformed date too (`_as_date` raises → let the decider treat it as not-in-effect).

**Self-scan gate (frozen contract):** `crawler/crs_audit.py` is held to `no_inlined_volatile_rules == []` by `test_crs_audit.py:363-368`. The new helpers must read every number from a grounded row — NO literal window/age. The `_FRESHNESS_FIELD` values are field NAMES (strings), not volatile numbers, so they pass.

**FREEZE:** `within_validity`, `_in_window`, `arranged_employment_guard` (`crs_audit.py:333-379`) stay byte-for-byte — new helpers are *additive siblings*, not rewrites (parity: `test_crs_audit.py:398-422`).

---

### `crawler/auditor.py` :: `gate_subset()` (grounding-gate service, request-response)

**Analog:** `_gate_or_raise` (`auditor.py:75-91`) — this is a **literal rename**, not a re-implementation.

**Core pattern to COPY EXACTLY** (`auditor.py:75-91`) — promote the body verbatim, keep the old name as an alias:
```python
def gate_subset(subset: Registry, db) -> None:               # renamed from _gate_or_raise
    """Gate every consumed row through the SHIPPED grounding gate (fail-closed)."""
    result = crs_rules.validate_registry(subset, db)         # THE one gate — never forked
    if result["violations"]:
        ids = sorted({v["rule_id"] for v in result["violations"]})
        reasons = sorted({r for v in result["violations"] for r in v["reasons"]})
        raise AuditGroundingError(f"ungrounded rule row(s) {ids}: {reasons}")
    for row in subset.rows:
        if row.gap:
            raise AuditGroundingError(
                f"consumed rule row {row.rule_id!r} is an ungrounded coverage gap")

_gate_or_raise = gate_subset   # back-compat alias — audit_one stays byte-for-byte
```

**Frozen call site that must NOT change** (`auditor.py:206-207`) — `audit_one` calls the gate; the alias keeps this line and its behavior identical:
```python
subset = _consumed_rows(registry, factor_id)
_gate_or_raise(subset, db)        # ← unchanged; now resolves to gate_subset via alias
```

**One-gate invariant (frozen):** `validate_registry` (`crs_rules.py:168`) → `grounding.check_answer` → `searchindex` is THE trust path. `gate_subset` must be *literally the same call*, deduped — never a parallel gate (STATE.md v4.0/v5.0 decisions; ROADMAP.md standing constraint).

**Pitfall 2 guardrail:** the promotion must produce ZERO delta in `test_auditor.py` / `test_auditor_dispatch.py`. Add a focused test asserting `auditor.gate_subset is auditor._gate_or_raise` (or identical behavior on a synthetic subset). Run the full 852-test suite as parity.

**FREEZE:** `audit_one` spine + `_consumed_rows` (`:68`) + `_rule_citation_ids` (`:94`) — the whole `test_auditor.py` grid depends on them.

---

### `crawler/index_health.py` :: `SnapshotHealth` + `probe_snapshot()` + `SNAPSHOT_*` (preflight service, file-I/O)

**Analog:** `IndexHealth` (`index_health.py:59-82`), `probe_index` (`:85-165`), `INDEX_*` vocab (`:43-48`). A **separate** `probe_snapshot` (NOT a new parameter on `probe_index`) keeps the frozen `probe_index` signature/tests byte-stable (Assumption A3); it *reuses* `probe_index` internally for missing/empty/unreadable/corrupt.

**Closed-vocabulary pattern to COPY** (`index_health.py:43-48`) — add the snapshot vocab beside it. Two NEW codes (`snapshot_stale`, `snapshot_missing`) on top of the reused base classifications:
```python
INDEX_OK = "ok"
INDEX_MISSING = "index_missing"
INDEX_EMPTY = "index_empty"
INDEX_UNREADABLE = "index_unreadable"
INDEX_CORRUPT = "index_corrupt"
INDEX_DRIFTED = "index_drifted"
# NEW closed vocab: SNAPSHOT_OK / _MISSING / _EMPTY / _UNREADABLE / _CORRUPT / _DRIFTED / _STALE
```

**Typed-result dataclass pattern to COPY** (`IndexHealth`, `index_health.py:59-82`) — `SnapshotHealth` mirrors it (`frozen=True`, `.ok()`, PII-free `.message(db)` echoing ONLY the caller-supplied `--db`/family):
```python
@dataclass(frozen=True)
class IndexHealth:
    status: str
    reason: str
    def ok(self) -> bool:
        return self.status == INDEX_OK
    def message(self, db) -> str:
        return (f"corpus index unusable (reason={self.status}): {self.reason}. "
                f"Recover: rebuild it with 'corpus-crawler --json index corpus/ --db {db}', ...")
```

**Read-only probe pattern to COPY** (`probe_index`, `index_health.py:85-165`) — the discipline `probe_snapshot` must inherit: read-only URI connect (`mode=ro`, never creates a 0-byte DB), guard the ENTIRE post-connect body so a truncated/malformed DB refuses as `corrupt` (never a traceback), the WR-02 non-`str` cell guard, and the bounded `chunk_sha` drift check:
```python
con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)         # WR-03: never writes/creates
try:
    ...
    for text, sha in con.execute("SELECT text, chunk_sha FROM chunks LIMIT ?", (_DRIFT_SAMPLE,)):
        if not isinstance(text, str):                        # WR-02: BLOB/NULL cell ⇒ corrupt
            return IndexHealth(INDEX_CORRUPT, "index chunk text is not stored as text")
        if chunk_sha(text) != sha:                           # content drift
            return IndexHealth(INDEX_DRIFTED, "indexed chunk text drifted ...")
except (sqlite3.DatabaseError, TypeError, ValueError):
    return IndexHealth(INDEX_CORRUPT, "index tables unreadable")
finally:
    con.close()
```

**NEW logic `probe_snapshot` adds over `probe_index`** (RESEARCH.md Pattern 4, `40-RESEARCH.md:222-245`) — reuse `probe_index` for the base classes, then classify a *required corpus family* (rows whose `relpath LIKE 'family/%'`), adding **empty-family ⇒ `snapshot_missing`**, per-chunk `chunk_sha` **drift**, and a **stale** check against a caller-supplied grounded `max_age_days`:
```python
def probe_snapshot(db, family, *, max_age_days=None, as_of=None) -> SnapshotHealth:
    base = probe_index(db)                                   # reuse missing/empty/unreadable/corrupt
    if not base.ok():
        return SnapshotHealth(_map(base.status), base.reason)
    con = sqlite3.connect(f"file:{Path(db)}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT text, chunk_sha, crawl_date FROM chunks WHERE relpath LIKE ?",
            (f"{family}/%",)).fetchall()                     # PARAM-BOUND — never f-string (SQLi)
        if not rows:
            return SnapshotHealth(SNAPSHOT_MISSING, f"no snapshot rows under {family}/")
        for text, sha, _cd in rows:
            if not isinstance(text, str) or chunk_sha(text) != sha:
                return SnapshotHealth(SNAPSHOT_DRIFTED, "snapshot chunk drifted from fingerprint")
        if max_age_days is not None:                         # GROUNDED bound passed IN by caller
            newest = max(_as_date(cd) for _t, _s, cd in rows if cd)
            if (_as_date(as_of) - newest).days > max_age_days:
                return SnapshotHealth(SNAPSHOT_STALE, f"snapshot older than {max_age_days}d")
    finally:
        con.close()
    return SnapshotHealth(SNAPSHOT_OK, "snapshot present and fresh")
```

**Content-hash reuse (Don't-Hand-Roll):** import `chunk_sha` from `crawler.searchindex` (`searchindex.py:128-135`, sha1 12-hex short fingerprint) exactly as `probe_index` does at `index_health.py:95` — do NOT invent a new hash scheme.

**No-inlined-literal rule (Pitfall 3):** `max_age_days` has NO numeric default — `index_health` stays literal-free; the *caller* reads the grounded window and passes it in.

**FREEZE:** `probe_index`, `IndexHealth`, `INDEX_*` (`index_health.py:43-165`) and their tests (`test_index_health.py`) — `probe_snapshot` is strictly additive.

---

### `crawler/cli.py` :: `_require_readable_snapshot()` (CLI preflight wrapper, request-response guard)

**Analog:** `_require_readable_index` (`cli.py:760-776`), `_vault_fail` (`cli.py:742-748`), and the zero-artifact ordering in `_cmd_vault_audit` (`cli.py:1119-1123`).

**Refusal-wrapper pattern to COPY** (`_require_readable_index`, `cli.py:760-776`) — turn a non-`ok` health into ONE `invalid_input`/exit-2 refusal via `_vault_fail`; return `None` when healthy:
```python
def _require_readable_index(args, db) -> "int | None":
    from crawler import index_health
    health = index_health.probe_index(db)
    if health.ok():
        return None
    return _vault_fail(args, contract.INVALID_INPUT, health.message(db),
                       contract.EXIT_INVALID_INPUT)          # exit 2, reason=<code>, PII-free
```
The refusal envelope helper it uses (`_vault_fail`, `cli.py:742-748`) — ONE PII-safe envelope, no traceback:
```python
def _vault_fail(args, err_type, msg, code) -> int:
    if args.json:
        contract.emit(contract.envelope("vault", error=(err_type, msg)))
    else:
        print(f"error: {msg}", file=sys.stderr)
    return code
```

**Zero-artifact ORDERING (frozen invariant, Pitfall 4)** — the preflight is the FIRST statement in the handler, BEFORE `open_vault`/compute (`_cmd_vault_audit`, `cli.py:1119-1123`). Any future screen wiring must chain the same way:
```python
# HARD-01/02: refuse a bad index cleanly, BEFORE opening the vault → zero artifacts.
refusal = _require_readable_index(args, args.db)
if refusal is not None:
    return refusal
try:
    v = vault.open_vault(args.candidate)   # ← only reached AFTER the preflight passes
```
`_require_readable_snapshot` (`40-RESEARCH.md:340-352`) mirrors this, passing `max_age_days` read from the grounded window and `as_of=date.today().isoformat()`; a healthy snapshot returns `None` (SAFE-10 SC4 positive control).

**Contract constants (Don't-Hand-Roll):** reuse `contract.INVALID_INPUT` (`contract.py:48`) + `contract.EXIT_INVALID_INPUT` (`= 2`, `contract.py:57`) — the exact code `search`/`ground`/`vault audit` already return for a bad `--db`. No new error type.

**Phase-40 scope note (A5):** Phase 40 ships `_require_readable_snapshot` as a callable + proves it via a fixture-driven CLI refusal test — it does NOT add a user-facing verb (the shipped verbs that call it are Phase 44/45). A `doctor`-style probe is optional/discretionary.

---

### Grounded staleness-bound row shape (DEFERRED to Phase 41 / STUDY-01; synthetic fixture only in Phase 40)

**Analog:** the shipped ECA/language `validity_window` rows — `core.education.eca_validity` (`core.yaml:81-106`, `window_days: 1825`) and `core.language.first.validity` (`core.yaml:195-219`, `window_days: 730`).

**Synthetic fixture shape for Phase 40** (`core.yaml:81-106`) — mirror a `validity_window` `machine_check` with a `field` + `window_days`, a resolvable synthetic `chunk_id`, and a matching `quote` to prove the reader, no-inline gate, and fingerprint behavior without modifying the shipped registry:
```yaml
  - rule_id: core.education.eca_validity
    factor_group: core_human_capital
    factor_ids: [core.education]
    check_type: threshold
    query: ECA validity years profile
    selector:
      family: guidance
      marker: "less than 5 years"
    claim_text: >-
      A foreign educational credential assessment (ECA) must be under the validity window ...
    citations:
      - chunk_id: guidance/education-assessment.md#003
        quote: "Your ECA must be **less than 5 years** old when you"     # verbatim substring
    machine_check:
      kind: validity_window
      field: eca_report_date
      window_days: 1825                    # GROUNDED — read via _window_days, NEVER inlined in code
      citation_index: 0
    volatility:
      volatility: volatile
      source_family: guidance
      crawl_date: "2026-06-11T01:09:06Z"
```
The Phase 40 fixture uses `field: snapshot_max_age` (matching `_FRESHNESS_FIELD["dli_snapshot"]`), read via `_window_days(registry, "snapshot_max_age")`. Phase 41 owns the future shipped row, concrete value, and authoritative citation. Full illustrative shape: `40-RESEARCH.md:311-334`.

**Future Phase 41 loader behavior (Don't-Hand-Roll):** `load_registry` globs every `*.yaml` under `crawler/data/crs_rules/` (`crs_rules.py:104-118`), so a future grounded bound row will be auto-loaded and covered by `registry_fingerprint` (`crs_rules.py:121-132`) without loader changes. Phase 40 does not add or modify a registry YAML file.

**Static-gate pass (frozen):** the `window_days` key is allow-listed in `_ALLOW_KEYS` (`crs_rules.py:402-415`), so a future *grounded* bound row passes `no_inlined_volatile_rules`; only an *inlined* literal trips it. Phase 40 reasserts the Python self-scan and uses the synthetic fixture for reader/fingerprint proof.

**Resolved grounding boundary:** IRCC does not publish a fixed "valid for N days" for the DLI list in the current corpus. Phase 40 ships the fail-closed mechanism and synthetic fixture proof only; Phase 41 must ground the real value and citation alongside the DLI family. Do not inline or fabricate a number.

---

## Shared Patterns

### Fail-closed default (applies to `within_freshness`, `row_in_effect`, every decider)
**Source:** `within_validity` "no window ⇒ `False`" (`crs_audit.py:152`); `_default_decider` AT-RISK (`crawler/auditors/__init__.py:103`).
**Apply to:** all SAFE-09 helpers. Missing/stale/superseded/out-of-window/unconfirmed ⇒ NOT green — never a "unknown ⇒ pass" branch. Prove with **out-of-window and stale negative controls**, not just current-dated fixtures (Pitfall 1 — the milestone's dominant risk).

### Grounded value, never an inlined literal (SAFE-09 core clause)
**Source:** `_window_days` reader (`crs_audit.py:58`) + `_ALLOW_KEYS` allow-list (`crs_rules.py:402-415`) + the `no_inlined_volatile_rules` gate (`crs_rules.py:458`).
**Apply to:** the staleness bound and every dated value. Read via `_window_days(registry, field)`; keep `index_health`/`crs_audit`/`cli` literal-free (`max_age_days` passed IN by the caller). Self-scan of `crawler/crs_audit.py` stays `== []` (`test_crs_audit.py:363-368`).

### ONE trust path (no second gate)
**Source:** `validate_registry` (`crs_rules.py:168`) via `gate_subset` (`auditor.py:75`, promoted).
**Apply to:** every consumer. Screens call `auditor.gate_subset`, never a fresh `validate_registry` loop or a parallel index.

### Read-only, side-effect-free DB access
**Source:** `probe_index` read-only URI connect (`index_health.py:116`), WR-01/02/03 guards (`:98-163`).
**Apply to:** `probe_snapshot`. `file:<db>?mode=ro`, never create a 0-byte DB, param-bound `LIKE ?` query (never f-string — SQLi mitigation), whole post-connect body guarded ⇒ `corrupt` on any `DatabaseError`.

### Zero-artifact refusal ordering
**Source:** `_cmd_vault_audit` preflight-before-`open_vault` (`cli.py:1119-1123`).
**Apply to:** any handler wiring `_require_readable_snapshot`. Preflight FIRST; refusal returns before any vault open/compute/write.

### PII-free refusal message
**Source:** `IndexHealth.message` (`index_health.py:70-82`) — echoes ONLY the caller-supplied `--db`/family (a corpus path, not applicant PII).
**Apply to:** `SnapshotHealth.message`. No `ev_` id, no absolute filesystem path, no applicant value (Pitfall 5). Assert `assertNotIn("ev_", msg)` in the refusal test.

### Content-drift fingerprint reuse
**Source:** `searchindex.chunk_sha` (`searchindex.py:128-135`, sha1 short) + `crs_rules.registry_fingerprint` (`crs_rules.py:121-132`, sha256).
**Apply to:** `probe_snapshot` per-chunk drift (reuse `chunk_sha`) and the new bound-row drift coverage (auto-covered by `registry_fingerprint`). Never a new hash scheme.

---

## Test Pattern Assignments (Wave 0 — new/extended tests gate their owning tasks)

### `crawler/tests/test_freshness_staleness.py` (NEW) — SAFE-09
**Analog:** `test_crs_audit.py` — `_row` fixture builder (`:28-46`), `_validity_registry` (`:70-83`), `TestWithinValidity` (`:137-146`), `TestSelfNoInlineScan` (`:363-368`). Build SYNTHETIC `Registry`/`RuleRow` objects in-test (no real corpus).
**Copy:** the `_row(...)` + `MachineCheck(kind="validity_window", field=..., window_days=...)` fixture shape; assert `within_freshness` True in-window, `False` for no-window / stale / after-reference; assert `row_in_effect` False out-of-window on BOTH `machine_check` and `volatility` windows, True for a no-window row. Re-assert `no_inlined_volatile_rules(["crawler/crs_audit.py"]) == []`.

### `crawler/tests/test_snapshot_health.py` (NEW) — SAFE-10
**Analog:** `test_index_health.py` — `_build_valid_index` tempdir helper (`:20-56`, imports `CHUNKS_DDL`/`FTS_DDL`/`chunk_sha` from `crawler.searchindex`), the `ProbeIndexReasonCodes` table (`:59-140`).
**Copy:** the tempdir fixture-DB builder; add `relpath`-under-`family/` rows. One assertion per closed code: missing-family ⇒ `snapshot_missing`, empty/unreadable/corrupt (reuse `probe_index` base), per-chunk drifted (`tamper_first_sha` pattern `:40-41`), **stale** (`crawl_date` beyond a passed `max_age_days`), **ok/fresh** (positive control). Assert read-only/side-effect-free (`assertFalse(db.exists())` on missing, `:72`).

### `crawler/tests/test_snapshot_refusal.py` (NEW) — SAFE-10
**Analog:** `test_audit_index_refusal.py` — `_run_json` (`:23-28`), `PR_PERSONAL_DIR` tempdir vault setUp (`:32-51`), `_audit_runs_count`/`_report_files` artifact probes (`:60-69`), `_assert_refusal` (`:71-86`), `AuditIndexPositiveControl` skip-guarded positive control (`:106-116`).
**Copy:** drive the CLI via `cli.main(["--json", ...])`; assert `env["ok"] is False`, `error.type == contract.INVALID_INPUT`, `code == contract.EXIT_INVALID_INPUT` (2), `reason=<code>` in message, `assertNotIn("ev_", msg)`, and ZERO artifacts (`audit_runs` count 0, no report files). Add a healthy-snapshot positive control (SAFE-10 SC4). Use a fixture snapshot family — NO dependency on Phase 41's `corpus/dli/`.

### `crawler/tests/test_crs_rules.py` (EXTEND) — SAFE-09 drift coverage
**Analog:** `registry_fingerprint` (`crs_rules.py:121`); current usages in `test_review_packet_cli.py:75` / `test_remediation_cli.py:166` (no dedicated fingerprint test exists yet — this is a role-match, not an exact copy).
**Add:** build a synthetic `Registry` in-test with one grounded `MachineCheck(kind="validity_window", field="snapshot_max_age", window_days=...)` row, fingerprint it, tamper `window_days`, re-fingerprint, and assert the hash flips. Do not load or add a shipped `safe.yaml`; the concrete grounded row is a Phase 41 responsibility.

### `crawler/tests/test_crs_no_inlined_rules.py` (EXTEND, only if a new `.py` module lands) — SAFE-09 static gate
**Analog:** `_registry_and_auditor_surface()` (`:35-49`) already scans `crawler/crs_audit.py`, so Phase 40's bound-reading helper is covered without a surface change. If the implementation instead creates a new `.py` module, append that path to the surface list (mirror `_EXPORT_MODULES`, `:29-32`). The future Phase 41 registry row will already be covered by `_DATA_DIR.glob("*.yaml")`.

---

## No Analog Found

**None.** Every Phase-40 deliverable is a promote-or-mirror of a shipped, tested symbol read this
session. The single MEDIUM-confidence item is not a *missing analog* but a *grounding decision*:

| Item | Nature | Resolution |
|------|--------|------------|
| The exact `window_days` value + its authoritative citation for the snapshot max-age | Grounding decision, not a code analog (resolved Assumption A2 / Open Question 1) | Deferred to Phase 41 alongside the DLI family. Phase 40 ships the fail-closed mechanism and synthetic grounded fixture proof only; never inline or fabricate the number. |

---

## Phase Boundary Guard (do NOT build in Phase 40)

Explicit out-of-scope — these belong to later phases (`40-RESEARCH.md:379-386`, ROADMAP.md):

| Deferred item | Owner phase |
|---------------|-------------|
| DLI snapshot artifact / `corpus refresh-dli` / `dli_snapshot.py` (Phase 40 uses synthetic fixtures) | Phase 41 (STUDY-01) |
| `decide_study` change / DLI-match gate | Phase 44 (STUDY-02..04) |
| Physician/legacy POLICY row or `arranged_employment_guard` change | Phase 42 (POLICY) |
| MEC screen / `mec.yaml` / `PublicMecSummary` / NOC worksheet | Phases 43/45 |
| New conformance release-gate command / `run_conformance.py` glob change | Phase 46 (SAFE-11/12) |
| Wiring `within_freshness`/`row_in_effect` into an existing shipped decider (would change the frozen CRS grid) | Phase 42/44/45 (central proof Phase 46) |
| `PublicAuditEnvelope` field / vault schema/migration / new dependency | — (never in v5.0 foundation) |

**Frozen boundaries confirmed live:** `PublicAuditEnvelope` (`models/audit.py:125`, `extra="forbid"`),
`arranged_employment_guard`+`_in_window` (`crs_audit.py:333-379`), `audit_one` spine (`auditor.py:181`),
`probe_index`/`IndexHealth`/`INDEX_*` (`index_health.py:43-165`), `_require_readable_index` (`cli.py:760`),
`registry_fingerprint`/`load_registry` (`crs_rules.py:104-132`), `[project].dependencies` (`pyproject.toml`,
unchanged: `pyyaml`, `pydantic`, `platformdirs`).

---

## Metadata

**Analog search scope:** `crawler/crs_audit.py`, `crawler/auditor.py`, `crawler/index_health.py`,
`crawler/cli.py`, `crawler/contract.py`, `crawler/crs_rules.py`, `crawler/models/crs_rules.py`,
`crawler/models/audit.py`, `crawler/searchindex.py`, `crawler/data/crs_rules/*.yaml`,
`crawler/tests/{test_crs_audit,test_index_health,test_audit_index_refusal,test_crs_no_inlined_rules,test_crs_rules}.py`.
**Files scanned:** 14 source/data files + 5 test files read this session (all line references verified live).
**Pattern extraction date:** 2026-07-17
