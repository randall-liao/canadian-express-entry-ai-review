# Phase 40: SAFE Freshness & Effective-Date Foundation - Research

**Researched:** 2026-07-17
**Domain:** Deterministic fail-closed grounding / freshness / effective-date guards over the shipped Python CRS-audit trust path (no external ecosystem)
**Confidence:** HIGH — every recommendation is anchored to a specific shipped symbol read this session; the phase is a promote-and-extend over tested code, not new machinery.

## Summary

Phase 40 lands the *mechanisms* half of the milestone's dominant safety invariant — **"stale / superseded / out-of-window / unconfirmed never greens"** — as a small, shared, fail-closed foundation that the later v5.0 screens (Phases 41/42/44/45) consume, and that the final SAFE conformance gate (Phase 46) proves centrally. It is deliberately a *foundation* phase: it ships no new screen, no new corpus artifact, and no new dependency. It promotes and extends four already-shipped, already-tested primitives.

The investigation confirms the milestone research's core claim against live code: the machinery this phase needs is **already present and tested** and the work is a promote/extend, not an invention. Specifically: (a) freshness-from-a-grounded-window already exists as `crawler/crs_audit.within_validity` (`crawler/crs_audit.py:142`) reading a grounded `validity_window` row via `_window_days` (`crawler/crs_audit.py:58`); (b) effective-window comparison already exists as `crawler/crs_audit._in_window` (`crawler/crs_audit.py:333`), used today only inside the frozen `arranged_employment_guard` (`crawler/crs_audit.py:343`); (c) the grounding-gate reuse pattern is `crawler/auditor._gate_or_raise` (`crawler/auditor.py:75`) + `_consumed_rows` (`crawler/auditor.py:68`), currently private to the spine; (d) the read-only, closed-reason-code, zero-artifact preflight is `crawler/index_health.probe_index` (`crawler/index_health.py:85`) wired at `crawler/cli._require_readable_index` (`crawler/cli.py:760`) and called *before* `open_vault` in `_cmd_vault_audit` (`crawler/cli.py:1121`). The registry drift fingerprint `crawler/crs_rules.registry_fingerprint` (`crawler/crs_rules.py:121`) already covers any row `load_registry` loads.

**Primary recommendation:** Deliver exactly four small, behavior-preserving changes and prove each with negative controls: (1) add `crs_audit.within_freshness()` (mirror `within_validity` — no grounded window or stale ⇒ `False`) plus a shared `crs_audit.row_in_effect(row, reference_date)` that composes `_in_window` over a row's grounded `machine_check`/`volatility` window; (2) ground the staleness bound as a `validity_window` registry row (read via the shipped `_window_days`), never an inlined literal; (3) promote `auditor.gate_subset(subset, db)` as a byte-for-byte extraction of `_gate_or_raise` so v5.0 screens reuse the ONE gate; (4) add `index_health.probe_snapshot(...)` + `cli._require_readable_snapshot(...)` mirroring the shipped preflight — a generic snapshot presence/empty/unreadable/corrupt/**stale**/**drifted** classifier with a closed reason-code vocabulary, non-zero exit, and zero artifacts, callable before any vault open. Keep `audit_one`, `arranged_employment_guard`, `PublicAuditEnvelope`, and the CRS grid byte-for-byte frozen; the new helpers are *additively callable* by future screens and are unit-proven here.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support (how this phase enables it) |
|----|-------------|-----------------------------------------------|
| **SAFE-09** | A shared freshness/effective-date guard ensures no grounded rule row or local snapshot outside its effective window or beyond its staleness bound can contribute to a green verdict; the staleness bound is a grounded/config value, not an inlined literal | New `crs_audit.within_freshness()` (mirrors `within_validity` `crawler/crs_audit.py:142`) + shared `row_in_effect()` composing `_in_window` (`crawler/crs_audit.py:333`); the bound is a grounded `validity_window` row read via `_window_days` (`crawler/crs_audit.py:58`) — the same pattern the shipped ECA `1825`/language `730` day windows use (`crawler/data/crs_rules/core.yaml:99,212`); the `no_inlined_volatile_rules` static gate (`crawler/crs_rules.py:458`) already trips on an inlined window literal, so "not inlined" is machine-enforced. Fail-closed: no grounded window ⇒ `False`; out-of-window/superseded ⇒ not applicable. |
| **SAFE-10** | The corpus/index/snapshot preflight refuses cleanly — stable PII-free reason code, non-zero exit, and zero audit/screen/database artifacts written — when a required snapshot or index is missing, empty, unreadable, corrupt, stale, or content-drifted; a healthy preflight permits downstream screens | New `index_health.probe_snapshot()` + `cli._require_readable_snapshot()` mirror the shipped `probe_index` (`crawler/index_health.py:85`) + `_require_readable_index` (`crawler/cli.py:760`): read-only URI connect, closed reason-code vocabulary, `invalid_input`/exit-2 refusal (`crawler/contract.py:48,57`), called BEFORE `open_vault` (as at `crawler/cli.py:1121`) so a refusal writes zero artifacts. Adds two new closed codes (`snapshot_stale`, `snapshot_missing`) on top of the reused missing/empty/unreadable/corrupt/drifted classification. |

**Note:** No CONTEXT.md exists for this phase — intentional (PROJECT.md directs autonomous planning/execution without clarification questions; `.planning/config.json` `workflow.skip_discuss: true`). ROADMAP.md Phase 40 details, REQUIREMENTS.md SAFE-09/SAFE-10, and the shipped code patterns are treated as authoritative.
</phase_requirements>

## Frozen Constraints (authoritative — planner MUST honor)

These are locked by ROADMAP.md "Standing constraints" (`.planning/ROADMAP.md:101-111`), REQUIREMENTS.md (`.planning/REQUIREMENTS.md:15`), and STATE.md Decisions (`.planning/STATE.md:88-150`). They have the force of locked decisions for this phase.

- **Zero new runtime dependencies.** `[project].dependencies` stays exactly `pyyaml`, `pydantic`, `platformdirs` (`pyproject.toml:12-16`). Everything Phase 40 needs is stdlib (`datetime`, `sqlite3`, `hashlib`, `dataclasses`, `pathlib`) already used by `crs_audit`/`index_health`. `[VERIFIED: pyproject.toml]`
- **No new/second trust path.** Every grounded decision still flows through the ONE gate: `crs_rules.validate_registry` → `grounding.check_answer` → `searchindex.resolve/search`. The promoted `gate_subset` is *literally the same call*, deduped — never a parallel gate. `[VERIFIED: crawler/auditor.py:82]`
- **Fail-closed verdicts.** Missing/stale/superseded/out-of-window/unconfirmed ⇒ refusal or `AT-RISK`, never a green. Mirrors the shipped `_default_decider` (`crawler/auditors/__init__.py:103`) and `within_validity`'s "no window ⇒ False" (`crawler/crs_audit.py:152`).
- **No inlined volatile literal.** The staleness bound and every dated value live in a grounded registry row; the `no_inlined_volatile_rules` gate (`crawler/crs_rules.py:458`) enforces this over the auditor/registry surface.
- **PII vault-only; stdout PII-light.** The preflight message echoes only the caller-supplied `--db`/snapshot path (a corpus path, not applicant PII) — matching the shipped `IndexHealth.message` precedent (`crawler/index_health.py:70`). No applicant value, no `ev_` id, no absolute path on stdout/envelope.
- **Frozen `PublicAuditEnvelope`** (`crawler/models/audit.py:125`, `extra="forbid"`) and the CRS total — untouched. Phase 40 adds no envelope field.
- **No live audit-time lookup; no model/NLI/vector/cloud path.** Freshness is computed against a grounded `crawl_date` already indexed from front matter (`crawler/searchindex.py:344`), never a network call.
- **Freeze byte-for-byte:** `arranged_employment_guard` + `_in_window` semantics (`crawler/crs_audit.py:333-379`), the `audit_one` spine (`crawler/auditor.py:181`), and the whole CRS grid contract (`crawler/tests/test_auditor.py`).

## Project Constraints (from copilot-instructions.md)

From `.github/copilot-instructions.md` (the canonical `claude_md_path` per `.planning/config.json`):
- **Tech stack is Python**; shared tools stay dependency-light and easy for others to run.
- **No PII may ever enter the public repo** — personal data stays in the local, git-ignored `personal/` area, structurally separated from the shareable harness. (Phase 40 touches only PII-free public modules — `crs_audit`, `auditor`, `index_health`, `crs_rules` data — so the perimeter is preserved by construction.)
- **Harness must be CLI-agnostic** — tools invoked as ordinary CLI verbs; no proprietary CLI/MCP API.
- **All requirement claims grounded and cited** from the authoritative corpus (IRCC / IRPA / IRPR / PDIs); no ungrounded assertions. The staleness bound must therefore be a *grounded* row, not an ungrounded config literal (this shapes the SAFE-09 design below).
- **Source authority:** corpus limited to authoritative sources.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Freshness / staleness bound check | Grounded decision core (`crs_audit.py`) | Registry data (`data/crs_rules/*.yaml`) | Pure date arithmetic over a grounded window — sits beside `within_validity`/`_in_window`; the bound is data, not code. |
| Effective-window applicability | Grounded decision core (`crs_audit.py`) | Registry model (`models/crs_rules.py`) | `_in_window` already lives here; `row_in_effect` composes it over `machine_check`/`volatility` metadata the model already carries. |
| Shared grounding-gate reuse (`gate_subset`) | Audit spine (`auditor.py`) | Grounding gate (`crs_rules.validate_registry`) | Promotion of the existing private `_gate_or_raise`; keeps ONE trust path for all screens. |
| Snapshot / index preflight refusal | Preflight (`index_health.py`) | CLI boundary (`cli.py`) | Read-only classification into a closed reason vocab belongs in `index_health`; the CLI maps it to the frozen refusal envelope before any write. |
| Zero-artifact ordering | CLI command handlers (`cli.py`) | — | Refusal must precede `open_vault`/compute; the ordering is a CLI-handler property (as at `crawler/cli.py:1120-1123`). |
| Registry drift coverage of new rows | Registry engine (`crs_rules.py`) | Audit report stamp (`models/audit.py`) | `registry_fingerprint` auto-covers any row `load_registry` reads — Phase 40 only confirms/wires the reuse pattern. |

## Standard Stack

No new packages. Phase 40 is stdlib-only over the frozen 3-dependency stack.

### Core (already installed — reused)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `datetime` | 3.10.12 | Effective-window + staleness date math | Already the basis of `within_validity`/`_in_window`/`age_on_date` (`crawler/crs_audit.py:25`). No third-party date lib. `[VERIFIED: crawler/crs_audit.py]` |
| Python stdlib `sqlite3` | 3.10.12 | Read-only snapshot/index probe | Already the basis of `probe_index` read-only URI connect (`crawler/index_health.py:116`). FTS5 confirmed present. `[VERIFIED: crawler/index_health.py]` |
| Python stdlib `hashlib` | 3.10.12 | Content-drift fingerprints (`chunk_sha`, `registry_fingerprint`, snapshot sha256) | `sha1` short fingerprint (`crawler/searchindex.py:135`) + `sha256` registry fingerprint (`crawler/crs_rules.py:131`) already ship. `[VERIFIED: crawler/searchindex.py]` |
| pydantic | 2.13.x | Typed registry rows (freshness bound row validates at load) | Frozen model surface — no schema change needed; `MachineCheck.validity_window`/`window_days` already exist (`crawler/models/crs_rules.py:159`). `[VERIFIED: crawler/models/crs_rules.py]` |
| pyyaml | 6.0.x | Registry `*.yaml` load (the grounded bound row) | `load_registry` reads every `*.yaml` (`crawler/crs_rules.py:104`). `[VERIFIED: crawler/crs_rules.py]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Reuse `crs_audit._window_days` for the staleness bound | A new `config.json` scalar / env var for max-age | Rejected: an ungrounded config literal violates the "bound is grounded, never inlined" clause of SAFE-09 and the project grounding constraint. A grounded `validity_window` row keeps the bound auditable and inside the drift fingerprint. |
| Extend `probe_index` with a `family`+`max_age` parameter | Separate `probe_snapshot` function | Recommend a **separate** `probe_snapshot` (see Open Questions) to keep `probe_index`'s frozen signature byte-stable for its shipped callers/tests (`crawler/tests/test_index_health.py`), while sharing internals. |
| `gate_subset` in `auditor.py` | `mec_screen` calls `crs_rules.validate_registry` directly | Either keeps ONE gate; a named `gate_subset` is clearer and lets the conformance grep-assert a single call site. |

**Installation:** None. `.venv/bin/python -m pytest` already runs the suite (pytest 9.0.3 confirmed).

## Package Legitimacy Audit

**Not applicable — Phase 40 installs zero packages.** `[project].dependencies` is unchanged (`pyproject.toml:12-16`). The milestone's zero-new-dependency invariant is a Phase 46 conformance assertion (AST-import scan + `[project].dependencies` unchanged). No SLOP/SUS surface exists for this phase.

## Exact File & Symbol Map

### CREATE (new symbols — small, additive)
| Symbol | File | Shape (mirror of) | Purpose |
|--------|------|-------------------|---------|
| `within_freshness(kind, crawl_date, reference_date, registry) -> bool` | `crawler/crs_audit.py` (new fn beside `within_validity`) | mirrors `within_validity` (`crawler/crs_audit.py:142`) | True iff a snapshot/rule `crawl_date` is within the grounded max-age window for `kind`; no grounded window ⇒ `False` (fail-closed). Reuses `_window_days` + `_as_date`. |
| `row_in_effect(row, reference_date) -> bool` | `crawler/crs_audit.py` (new fn beside `_in_window`) | composes `_in_window` (`crawler/crs_audit.py:333`) | True iff `reference_date` is within the row's grounded effective window, checking BOTH `machine_check.effective_from/to` and `volatility.effective_from/to`; a row with no window is stable/effective; fail-closed on a malformed date. Consolidates the two window sources `arranged_employment_guard` reads today (`crawler/crs_audit.py:364-371`). |
| `gate_subset(subset, db) -> None` | `crawler/auditor.py` (promoted from `_gate_or_raise`) | identical body to `_gate_or_raise` (`crawler/auditor.py:75`) | The ONE public grounding-gate call for every screen. `_gate_or_raise` becomes a thin alias (or is renamed with the old name kept as an alias) to preserve `audit_one` verbatim. |
| `SnapshotHealth` (frozen dataclass) + `probe_snapshot(db, family, *, max_age_days=None, as_of=None) -> SnapshotHealth` | `crawler/index_health.py` | mirrors `IndexHealth` + `probe_index` (`crawler/index_health.py:59,85`) | Read-only classification of a required snapshot family into a closed reason vocab: present rows for `family`? empty? unreadable? corrupt? per-chunk drifted (`chunk_sha`)? **stale** (max `crawl_date` older than `max_age_days`)? `max_age_days` is passed IN by the caller (read from the grounded window) — no literal in `index_health`. |
| `SNAPSHOT_OK/_MISSING/_EMPTY/_UNREADABLE/_CORRUPT/_DRIFTED/_STALE` | `crawler/index_health.py` | mirrors the `INDEX_*` closed vocab (`crawler/index_health.py:43-48`) | The stable `reason=<code>` tokens the CLI embeds. |
| `_require_readable_snapshot(args, db, family, max_age_days) -> int | None` | `crawler/cli.py` (beside `_require_readable_index`) | mirrors `_require_readable_index` (`crawler/cli.py:760`) | Turns a non-`ok` `SnapshotHealth` into the frozen `invalid_input`/exit-2 refusal (`crawler/contract.py:48,57`) with a `reason=<code>` token + recovery hint; returns before any vault open ⇒ zero artifacts. |
| Grounded staleness-bound row(s) | **Deferred to Phase 41 (STUDY-01)** — future `crawler/data/crs_rules/*.yaml` row | mirrors the ECA/language `validity_window` rows (`crawler/data/crs_rules/core.yaml:99,212`) | The current corpus has no authoritative fixed DLI max-age span, so Phase 40 must not fabricate a row. Phase 40 ships the fail-closed reader/field contract and proves grounded/config-driven behavior with synthetic grounded fixtures; Phase 41 owns the real value and citation alongside the DLI snapshot family. See Plan 40-01 T-40-A2. |

### FREEZE (must not change behavior — byte-for-byte)
| Symbol | File | Why frozen |
|--------|------|-----------|
| `arranged_employment_guard`, `_in_window` semantics | `crawler/crs_audit.py:333-379` | POLICY (Phase 42) extends via a new grounded row, never a code change; parity test `test_crs_audit.py:412`. |
| `within_validity` | `crawler/crs_audit.py:142` | Language/ECA document validity contract; `within_freshness` is a *sibling*, not a rewrite. |
| `audit_one` spine + `_consumed_rows` + `_rule_citation_ids` | `crawler/auditor.py:68-260` | The whole `test_auditor.py` grid contract depends on it; promotion of `gate_subset` must not alter the gate call at `crawler/auditor.py:207`. |
| `probe_index`, `IndexHealth`, `INDEX_*` | `crawler/index_health.py:43-165` | Shipped preflight + its tests (`test_index_health.py`); `probe_snapshot` is additive. |
| `_require_readable_index` | `crawler/cli.py:760` | Shipped `vault audit` refusal (`test_audit_index_refusal.py`). |
| `PublicAuditEnvelope`, CRS total | `crawler/models/audit.py:125` | Milestone-frozen public boundary. |
| `registry_fingerprint`, `load_registry` | `crawler/crs_rules.py:104-132` | Phase 40 proves with a synthetic grounded row that bound changes alter the fingerprint; a future Phase 41 registry row will be covered automatically because `load_registry` reads normal `*.yaml` files. |

### MODIFY (small, careful)
| Symbol | File | Change |
|--------|------|--------|
| `_gate_or_raise` → `gate_subset` | `crawler/auditor.py:75` | Rename to public `gate_subset`; keep `_gate_or_raise = gate_subset` alias so `audit_one` and any importer are untouched. Pure extraction — assert identical behavior. |
| Static-gate scan surface | `crawler/tests/test_crs_no_inlined_rules.py:29-49` | Phase 40 keeps bound-reading logic in the already-scanned `crs_audit.py`; add a scan path only if implementation moves it to a new Python module. A future Phase 41 YAML row is automatically covered by `_DATA_DIR.glob("*.yaml")`. |

## Architecture Patterns

### System Architecture Diagram

```
                        Phase 40 FOUNDATION (mechanisms; no new screen)

  operator CLI verb (future: vault screen-mec / vault study / corpus refresh-dli)
        │
        ▼
  ┌─────────────────────────── PREFLIGHT (SAFE-10) ───────────────────────────┐
  │  cli._require_readable_index(args, db)   ── shipped, before open_vault ──┐ │
  │  cli._require_readable_snapshot(args, db, family, max_age_days)  ── NEW ─┤ │
  │        │                                                                 │ │
  │        ▼                                                                 │ │
  │  index_health.probe_index(db)      → IndexHealth  (missing/empty/…)      │ │
  │  index_health.probe_snapshot(db, family, max_age_days, as_of) → NEW      │ │
  │        │  status != ok                                                   │ │
  │        ▼                                                                 │ │
  │  contract.envelope(invalid_input, "reason=<code> …", exit 2)  ── ZERO ───┘ │
  │        (returns BEFORE open_vault / compute / any write)     ARTIFACTS      │
  └────────────────────────────────────────────────────────────────────────────┘
        │ status == ok  (healthy ⇒ proceed — SAFE-10 SC4)
        ▼
  ┌─────────────────────────── GROUNDING (ONE trust path) ────────────────────┐
  │  auditor.gate_subset(consumed_rows, db)   ── promoted from _gate_or_raise ─┤
  │     → crs_rules.validate_registry → grounding.check_answer → searchindex   │
  │     ungrounded / gap:true row ⇒ AuditGroundingError (no verdict, no write) │
  └────────────────────────────────────────────────────────────────────────────┘
        │ gated rows only
        ▼
  ┌─────────────────────── FRESHNESS / EFFECTIVE-DATE (SAFE-09) ───────────────┐
  │  crs_audit.row_in_effect(row, reference_date)                              │
  │     → _in_window(machine_check.effective_from/to)  AND  volatility window  │
  │  crs_audit.within_freshness(kind, snapshot.crawl_date, reference_date, reg)│
  │     → _window_days(reg, field)  (GROUNDED bound, never inlined)            │
  │     no window / out-of-window / stale  ⇒  NOT green  (GAP / AT-RISK)       │
  └────────────────────────────────────────────────────────────────────────────┘
        │ in-effect + fresh + grounded + audit-eligible evidence
        ▼
   downstream decider verdict (SUBSTANTIATED possible)   ── else fail-closed
```

### Pattern 1: Freshness-from-a-grounded-window (SAFE-09 staleness half)
**What:** `within_freshness` reads the max-age window from a grounded `validity_window` row (never a literal) and returns `False` when there is no grounded window or the `crawl_date` is older than it — exactly the shape of `within_validity`.
**When:** Any dated/snapshot-backed value (DLI snapshot in Phase 44, LICO if added, any policy window).
**Example:**
```python
# Source: mirror of crawler/crs_audit.py:142 (within_validity) + :58 (_window_days)
_FRESHNESS_FIELD = {"dli_snapshot": "snapshot_max_age"}  # kind → grounded window field

def within_freshness(kind, crawl_date, reference_date, registry) -> bool:
    """True iff crawl_date is within the GROUNDED max-age window of kind.
    No grounded window ⇒ False (fail-closed, like within_validity:152).
    A crawl_date after the reference date, or older than the window, is stale.
    """
    field = _FRESHNESS_FIELD.get(kind, kind)
    window = _window_days(registry, field)      # GROUNDED — never an inlined literal
    if window is None:
        return False
    delta = (_as_date(reference_date) - _as_date(crawl_date)).days
    return 0 <= delta <= window
```

### Pattern 2: Effective-window composition (SAFE-09 out-of-window half)
**What:** A single `row_in_effect(row, reference_date)` that any screen calls to ask "is this grounded row applicable on the reference date?", checking both window sources the model carries. Consolidates the two `_in_window` reads `arranged_employment_guard` performs today.
**When:** POLICY (dated repeal/physician rows), MEC (dated criteria), STUDY (dated designations).
**Example:**
```python
# Source: composes crawler/crs_audit.py:333 (_in_window) over the grounded metadata at
# crawler/models/crs_rules.py:159-189 (MachineCheck + VolatilityMeta effective_from/to)
def row_in_effect(row, reference_date) -> bool:
    mc, vol = row.machine_check, row.volatility
    if not _in_window(reference_date, mc.effective_from, mc.effective_to):
        return False
    if not _in_window(reference_date, vol.effective_from, vol.effective_to):
        return False
    return True   # a row with no windows (both None) is stable/effective — _in_window True
```

### Pattern 3: Promoted single gate (`gate_subset`) — no second trust path
**What:** Rename the private `_gate_or_raise` to a public `gate_subset` with an identical body; keep the old name as an alias so `audit_one` is untouched. Future screens (`mec_screen`, study/policy) import `auditor.gate_subset` instead of duplicating the gate.
**When:** Every v5.0 screen that consumes grounded rows.
**Example:**
```python
# Source: verbatim extraction of crawler/auditor.py:75-91
def gate_subset(subset, db) -> None:
    """Gate every consumed row through the SHIPPED grounding gate (fail-closed).
    Reuses crs_rules.validate_registry (→ grounding.check_answer); never forks it."""
    result = crs_rules.validate_registry(subset, db)
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

### Pattern 4: Snapshot preflight → clean refusal, zero artifacts (SAFE-10)
**What:** `probe_snapshot` mirrors `probe_index` but classifies a *required corpus family* (rows whose `relpath` is under `family/`) and adds a **stale** classification (max `crawl_date` vs a caller-supplied grounded `max_age_days`) and reuses the per-chunk `chunk_sha` **drift** check. The CLI wrapper refuses BEFORE `open_vault`.
**When:** Phase 44 (STUDY) and Phase 45 (MEC-CEC) preflight the DLI family; Phase 40 ships the mechanism + a fixture-family test.
**Example:**
```python
# Source: mirror of crawler/index_health.py:85-165 (read-only URI connect + closed vocab)
# + crawler/cli.py:760-776 (refusal wrapper) + crawler/cli.py:1119-1123 (ordering).
def probe_snapshot(db, family, *, max_age_days=None, as_of=None) -> SnapshotHealth:
    base = probe_index(db)                       # reuse: missing/empty/unreadable/corrupt
    if not base.ok():
        return SnapshotHealth(_map(base.status), base.reason)
    con = sqlite3.connect(f"file:{Path(db)}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT text, chunk_sha, crawl_date FROM chunks WHERE relpath LIKE ?",
            (f"{family}/%",)).fetchall()
        if not rows:
            return SnapshotHealth(SNAPSHOT_MISSING, f"no snapshot rows under {family}/")
        for text, sha, _cd in rows:
            if not isinstance(text, str) or chunk_sha(text) != sha:
                return SnapshotHealth(SNAPSHOT_DRIFTED, "snapshot chunk drifted from fingerprint")
        if max_age_days is not None:             # GROUNDED bound passed by caller
            newest = max(_as_date(cd) for _t, _s, cd in rows if cd)
            if (_as_date(as_of) - newest).days > max_age_days:
                return SnapshotHealth(SNAPSHOT_STALE, f"snapshot older than {max_age_days}d")
    finally:
        con.close()
    return SnapshotHealth(SNAPSHOT_OK, "snapshot present and fresh")
```

### Anti-Patterns to Avoid
- **Inlining the staleness bound** (`if age > 180:`): trips SAFE-09 and the `no_inlined_volatile_rules` gate. Read it from a grounded `validity_window` row via `_window_days`.
- **A second gate / index / datastore:** `mec_screen` must call `auditor.gate_subset`, not re-implement `validate_registry`. One FTS5 index; the snapshot is a normal `corpus/` family.
- **Refusing after `open_vault`/compute:** breaks the zero-artifact guarantee. Order the preflight first, exactly as `_cmd_vault_audit` does (`crawler/cli.py:1120-1123`).
- **Passing the bound *into* `index_health` as a literal default:** keep `index_health` literal-free; the caller reads the grounded window and passes `max_age_days`.
- **Changing `audit_one`/`arranged_employment_guard` to add freshness:** freeze them; new screens *call* the helpers.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Date-window / staleness math | A new date-parsing/window comparator | `crs_audit._as_date` + `_window_days` + `_in_window` (`crawler/crs_audit.py:48,58,333`) | Handles ISO `YYYY-MM-DD[THH:MM:SSZ]` truncation, None windows, after-reference guard, already tested. |
| Grounding a rule row | A new validate loop | `auditor.gate_subset` → `crs_rules.validate_registry` (`crawler/auditor.py:82`) | ONE trust path; forking silently widens the guarantee. |
| Read-only DB probe / corruption classification | A fresh `sqlite3.connect` + try/except | `index_health.probe_index` internals (`crawler/index_health.py:85`) | Read-only URI, never creates a 0-byte DB, catches truncated/malformed/non-text-cell cases. |
| Content-drift fingerprint | A new hash scheme | `searchindex.chunk_sha` (`crawler/searchindex.py:128`) + `crs_rules.registry_fingerprint` (`crawler/crs_rules.py:121`) | Row-level and registry-level drift already covered; snapshot reuses `chunk_sha`. |
| Refusal envelope + exit code | A new error type | `contract.INVALID_INPUT`/`EXIT_INVALID_INPUT` (`crawler/contract.py:48,57`) via `_vault_fail` | The exact code `search`/`ground`/`vault audit` already return for a bad `--db`. |
| Fail-closed default | A new "unknown ⇒ pass" branch | `_default_decider` AT-RISK (`crawler/auditors/__init__.py:103`) | Elevation-of-privilege mitigation already the norm. |

**Key insight:** In this codebase the fail-closed primitives are already tested and adversarially probed; the risk in Phase 40 is *omission* (a new decider that forgets to call the guard), not construction. The deliverable is therefore a small, discoverable, well-named shared API plus negative-control tests — not new algorithms.

## Runtime State Inventory

> Phase 40 is a mechanism foundation (new helpers, synthetic grounded-row proof, and a promotion refactor). It writes no new datastore or shipped registry row and renames no runtime-registered string. Each category checked explicitly:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None** — no vault schema change; `extracted_values`/`audit_runs` untouched. The freshness bound is a grounded YAML row loaded into an in-memory `Registry`, not persisted state. Verified: no `ALTER TABLE`/migration implied; `vault.py` staleness keys (`crawler/vault.py:1048-1075`) unchanged. | None |
| Live service config | **None** — no external service; no crawler/CI schedule change in this phase. The DLI refresh generator is Phase 41, not 40. | None |
| OS-registered state | **None** — no scheduled task, daemon, or process name. | None |
| Secrets / env vars | **None** — no new secret/env var. `PR_PERSONAL_DIR`/`PR_CONFORMANCE_RUNNER` are read but unchanged. | None |
| Build artifacts / installed packages | **None new** — no `pyproject.toml` dependency change, no new console entry point (`corpus-crawler` unchanged, `pyproject.toml:29`). The new symbols are inside the already-installed `crawler` package; a `pip install -e .` reinstall is not required for source-run via `.venv/bin/python`. | None |

**The canonical question** ("after every file is updated, what runtime systems still hold old state?"): **nothing** — this phase adds capability without renaming or persisting runtime state. The one *forward-looking* state concern (a stale DLI snapshot's `crawl_date`) is a Phase 41/44 artifact; Phase 40 only ships the guard that reads it.

## Common Pitfalls

### Pitfall 1: A new decider never calls the freshness/effective guard (the milestone's dominant risk)
**What goes wrong:** A future screen returns `SUBSTANTIATED`/`MEETS` from a row whose `effective_to` precedes the reference date, or from a stale snapshot, because it grounded the row but never checked the window. `[VERIFIED: .planning/research/PITFALLS.md:18-24]`
**Why it happens:** The window metadata exists but is *optional to read*; a test that only uses in-window fixtures looks green.
**How to avoid:** Ship `row_in_effect`/`within_freshness` as *the* discoverable API beside `within_validity`, document "no in-window grounded row ⇒ not green" as the default, and — critically for Phase 40 — prove the helpers themselves with **out-of-window and stale negative controls**, not just current-dated fixtures. Wiring into each screen is Phases 42/44/45; the central proof is Phase 46.
**Warning signs:** A verdict with no as-of provenance; a helper with only positive tests.

### Pitfall 2: The promotion silently changes `audit_one` behavior
**What goes wrong:** Extracting `gate_subset` accidentally alters the gate call order or exception message, breaking the frozen `test_auditor.py` grid.
**How to avoid:** Pure rename + alias (`_gate_or_raise = gate_subset`); run the full `crawler/tests` suite (852 tests) and assert zero deltas. Add a small test asserting `gate_subset is _gate_or_raise` (or same behavior on a synthetic subset).
**Warning signs:** Any diff in `test_auditor.py`, `test_auditor_dispatch.py`, `test_full_audit_*` output.

### Pitfall 3: The staleness bound leaks in as an inlined literal
**What goes wrong:** `max_age_days=180` default in `probe_snapshot`/`within_freshness` becomes the de-facto bound — ungrounded, undetectable, exactly Pitfall 1 with no metadata.
**How to avoid:** No numeric default; the caller reads `_window_days(registry, "snapshot_max_age")` and passes it in. Phase 40 proves this with a synthetic grounded fixture; Phase 41 adds the real authoritative bound row. Extend the `no_inlined_volatile_rules` scan surface only if a new Python module carries the helper.
**Warning signs:** A numeric literal in `index_health.py`/`crs_audit.py` outside a synthetic grounded-payload fixture; the static-gate test not covering the helper's module.

### Pitfall 4: Snapshot preflight refuses AFTER a partial write
**What goes wrong:** The snapshot check runs after `open_vault` or after a compute step, leaving an orphan `audit_runs` row / report file.
**How to avoid:** Order it identically to the shipped index preflight — first statement in the handler, before `open_vault` (`crawler/cli.py:1120-1123`). Prove zero artifacts by asserting no report file and no `audit_runs`/screen row after a refusal (the exact shape of `test_audit_index_refusal.py`).
**Warning signs:** A refusal test that doesn't assert artifact absence.

### Pitfall 5: PII / absolute path in the refusal message
**What goes wrong:** The snapshot message echoes an applicant path or absolute filesystem path.
**How to avoid:** Echo only the caller-supplied corpus `--db`/family (PII-free), matching `IndexHealth.message` (`crawler/index_health.py:70`). Add a PII-perimeter assertion (no `ev_`, no absolute path) to the refusal test.

## Code Examples

### Grounded staleness-bound registry row (SAFE-09 — bound is data, not code)
```yaml
# Source: mirror of crawler/data/crs_rules/core.yaml:99-106 (ECA validity_window, 1825 days)
# Illustrative row shape for Phase 41; Phase 40 uses this shape only in a synthetic test fixture.
rows:
  - rule_id: safe.snapshot.freshness
    factor_group: additional_points          # any valid group; not an audited factor
    factor_ids: [safe.snapshot.freshness]
    check_type: threshold
    query: "how current must the designated learning institution list be"
    selector: { family: guidance, marker: "updated" }
    claim_text: "The DLI/PGWP snapshot must be no older than the grounded refresh window."
    citations:
      - chunk_id: "guidance/dli-list-note.md#001"   # a real, resolvable authoritative chunk
        quote: "the list is updated regularly"       # verbatim substring of the cited chunk
    machine_check:
      kind: validity_window
      field: snapshot_max_age
      window_days: 180                         # GROUNDED — read via _window_days, never inlined in code
      citation_index: 0
    volatility:
      volatility: volatile
      source_family: guidance
      crawl_date: "2026-07-17T00:00:00Z"
```
> **Resolved:** the *mechanism* is what Phase 40 delivers. The current corpus cannot ground a fixed DLI max-age, so Phase 40 does not ship this example row; Phase 41 owns the concrete bound and authoritative citation alongside the DLI family.

### CLI wrapper preserving zero-artifact ordering (SAFE-10)
```python
# Source: mirror of crawler/cli.py:760-776 + the ordering at crawler/cli.py:1119-1123
def _require_readable_snapshot(args, db, family, max_age_days) -> "int | None":
    from crawler import index_health
    health = index_health.probe_snapshot(
        db, family, max_age_days=max_age_days, as_of=date.today().isoformat())
    if health.ok():
        return None
    return _vault_fail(args, contract.INVALID_INPUT, health.message(db),
                       contract.EXIT_INVALID_INPUT)   # exit 2, reason=<code>, ZERO artifacts

# In a future screen handler (Phase 44/45), FIRST — before open_vault:
#   refusal = _require_readable_index(args, args.db)         ... or None
#   refusal = refusal or _require_readable_snapshot(args, args.db, "dli", bound)
#   if refusal is not None: return refusal
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Freshness only for applicant documents (`within_validity` language/ECA) | Freshness generalized to snapshots/rows (`within_freshness` + `row_in_effect`) | Phase 40 | One idiom for every dated value; no bespoke per-screen date math. |
| Grounding gate private to the audit spine (`_gate_or_raise`) | Public `gate_subset` reused by sidecars | Phase 40 | Guarantees ONE trust path across CRS + MEC + POLICY + STUDY. |
| Preflight covers the whole index only (`probe_index`) | Preflight also covers a required *snapshot family* with stale/drift codes (`probe_snapshot`) | Phase 40 | STUDY/MEC-CEC can refuse cleanly on an absent/stale DLI family before any write. |

**Deprecated/outdated:** none — this phase only adds. No shipped symbol is removed; `_gate_or_raise` survives as an alias.

## Implementation Strategy & Plan Decomposition

**Overall:** four small, independently-testable deliverables, best sequenced as two waves. Fine granularity (per `.planning/config.json` `granularity: fine`). All work is inside PII-free public modules.

### Wave 1 — Pure helpers (no I/O; unit-testable in isolation)
1. **`crs_audit.within_freshness` + `row_in_effect`** (+ `_FRESHNESS_FIELD` map). Unit tests with in-window/out-of-window/stale/no-window/after-reference negative controls (mirror `test_crs_audit.py:138-146`). Prove the `no_inlined_volatile_rules` self-scan over `crawler/crs_audit.py` still returns `[]` (`test_crs_audit.py:367`).
2. **Grounded-bound mechanism and drift contract** via synthetic grounded `validity_window` fixtures: prove `_window_days(registry, "snapshot_max_age")` reads configuration data, a changed bound flips `registry_fingerprint`, and no numeric bound is inlined. The concrete authoritative DLI bound row is deferred to Phase 41 because the current corpus cannot ground a fixed max-age value.
3. **Promote `gate_subset`** in `auditor.py` (rename + alias). Full-suite parity run; a focused test asserting behavior identity on a synthetic subset.

### Wave 2 — Preflight + CLI wiring (I/O; fixture-DB tests)
4. **`index_health.probe_snapshot` + `SnapshotHealth` + `SNAPSHOT_*` codes**, and **`cli._require_readable_snapshot`**. Table-driven tests building each snapshot state in a tempdir (mirror `test_index_health.py`): missing family, empty family, unreadable, corrupt (reuse `probe_index`), per-chunk drifted, **stale** (crawl_date beyond a passed bound), and **ok/fresh** (positive control). CLI refusal + zero-artifact + PII-perimeter test (mirror `test_audit_index_refusal.py`), driven through a fixture snapshot family (no real corpus/DLI needed — Phase 40 must not depend on Phase 41).

**Sequencing rationale:** Wave 1 has no dependency on Wave 2; both can proceed in parallel if the planner wants, but the grounded bound (1.2) is an input to `probe_snapshot`'s test (2.4), so ground-truth the bound first. `gate_subset` (1.3) is independent and low-risk — good first commit.

### Out-of-Scope Boundaries (explicit — do NOT do in Phase 40)
- **No DLI snapshot artifact or refresh generator** (`dli_snapshot.py`, `corpus/dli/*.md`, `corpus refresh-dli`) — that is **Phase 41** (STUDY-01). Phase 40 tests use a synthetic fixture family. `[VERIFIED: .planning/ROADMAP.md:121,156-168]`
- **No `decide_study` change / no DLI-match gate** — **Phase 44** (STUDY-02..04). `[VERIFIED: .planning/ROADMAP.md:197-208]`
- **No physician/legacy POLICY row or guard change** — **Phase 42**. `[VERIFIED: .planning/ROADMAP.md:170-182]`
- **No MEC screen, `mec.yaml`, `PublicMecSummary`, or NOC worksheet** — **Phases 43/45**.
- **No new conformance release-gate command / no `run_conformance.py` glob change** — **Phase 46** (SAFE-11/12). Phase 40 ships unit + refusal tests, not the composite gate. `[VERIFIED: .planning/ROADMAP.md:225-237]`
- **No wiring of `within_freshness`/`row_in_effect` into an existing shipped decider** — that would change the frozen CRS grid; Phase 40 exposes callable helpers only.
- **No `PublicAuditEnvelope` field, no vault schema/migration, no new dependency.**

## Validation Architecture

> `.planning/config.json` `workflow.nyquist_validation: true` — this section is REQUIRED.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (Python 3.10.12) `[VERIFIED: .venv/bin/python -m pytest]` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (only a `conformance` marker registered; `pyproject.toml:33-36`) |
| Quick run command | `.venv/bin/python -m pytest crawler/tests/test_crs_audit.py crawler/tests/test_freshness_staleness.py crawler/tests/test_snapshot_health.py -q` |
| Full suite command | `.venv/bin/python -m pytest crawler/tests -q` (852 tests collected as baseline `[VERIFIED]`) |
| Release-gate (v4.x, must stay green) | `.venv/bin/python scripts/run_conformance.py` (SAFE-01..08; `scripts/run_conformance.py`) |

**Always use `.venv/bin/python`, never bare `python`.**

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SAFE-09 | `within_freshness` returns False for no grounded window / stale / after-reference; True in-window | unit | `.venv/bin/python -m pytest crawler/tests/test_freshness_staleness.py -x` | ❌ Wave 1 (new) |
| SAFE-09 | `row_in_effect` returns False out-of-window / superseded (both window sources); True for no-window stable row | unit | `.venv/bin/python -m pytest crawler/tests/test_freshness_staleness.py -x -k in_effect` | ❌ Wave 1 (new) |
| SAFE-09 | `_window_days` reads a synthetic grounded bound fixture and no numeric bound is inlined in Python (static gate clean over the helper surface) | unit + static-gate | `.venv/bin/python -m pytest crawler/tests/test_crs_no_inlined_rules.py crawler/tests/test_crs_audit.py -k "no_inlined or freshness" -x` | ⚠️ extend `test_crs_no_inlined_rules.py` only if a new module is created |
| SAFE-09 | Drift fingerprint covers the synthetic freshness-bound row shape (tamper flips `registry_fingerprint`) | unit | `.venv/bin/python -m pytest crawler/tests/test_crs_rules.py -k fingerprint -x` | ⚠️ extend |
| SAFE-09 | `gate_subset` promotion is behavior-identical (frozen grid green) | regression | `.venv/bin/python -m pytest crawler/tests/test_auditor.py crawler/tests/test_auditor_dispatch.py -q` | ✅ exists (parity) |
| SAFE-10 | `probe_snapshot` classifies missing/empty/unreadable/corrupt/drifted/stale/ok into the closed vocab (read-only, side-effect-free) | unit table | `.venv/bin/python -m pytest crawler/tests/test_snapshot_health.py -q` | ❌ Wave 2 (new) |
| SAFE-10 | CLI `_require_readable_snapshot` → `invalid_input`/exit-2, `reason=<code>`, ZERO artifacts, PII-free/no absolute path | integration | `.venv/bin/python -m pytest crawler/tests/test_snapshot_refusal.py -q` | ❌ Wave 2 (new) |
| SAFE-10 | Healthy snapshot preflight returns ok and permits proceed (positive control) | integration | `.venv/bin/python -m pytest crawler/tests/test_snapshot_refusal.py -k positive -q` | ❌ Wave 2 (new) |

### Sampling Rate
- **Per task commit:** the Quick run command above (freshness + snapshot-health files) — sub-second.
- **Per wave merge:** `.venv/bin/python -m pytest crawler/tests -q` (full 852+ baseline; must stay green — proves the `gate_subset` promotion is non-breaking).
- **Phase gate:** full suite green **and** `.venv/bin/python scripts/run_conformance.py` green (v4.x SAFE-01..08 unchanged) before `/gsd-verify-work`.

### Real-corpus / fixture split
- **Fixture-only (Phase 40):** all new tests build synthetic index/snapshot DBs in a tempdir (the shipped `_build_valid_index` helper pattern in `test_index_health.py:19`) and synthetic registries (the `test_crs_audit.py` pattern). **No dependency on the real corpus or the not-yet-existent `corpus/dli/` family** — Phase 40 must be testable before Phase 41.
- **Real-corpus (later):** the DLI family's verbatim grounding and end-to-end freshness are proven in Phase 41/44/46 against the pinned snapshot fixture and the real index.

### Wave 0 Gaps
- [ ] `crawler/tests/test_freshness_staleness.py` — covers SAFE-09 (`within_freshness`, `row_in_effect`, grounded-bound read) with negative controls.
- [ ] `crawler/tests/test_snapshot_health.py` — covers SAFE-10 `probe_snapshot` classification table.
- [ ] `crawler/tests/test_snapshot_refusal.py` — covers SAFE-10 CLI refusal + zero-artifact + PII-perimeter (positive control included).
- [ ] Extend `crawler/tests/test_crs_no_inlined_rules.py` only if the helper lands in a new Python module; `crs_audit.py` is already scanned.
- [ ] Extend a `registry_fingerprint` test with a synthetic freshness-bound row shape and assert tampering flips the hash.
- Framework install: none — pytest present.

## Security Domain

> `.planning/config.json` `workflow.security_enforcement: true`, `security_asvs_level: 1`.

### Applicable ASVS Categories (Level 1)
| ASVS Category | Applies | Standard Control (this phase) |
|---------------|---------|-------------------------------|
| V1 Architecture | yes | Single trust path preserved (`gate_subset` = the one gate); no second grounding path. `[VERIFIED: crawler/auditor.py:82]` |
| V5 Input Validation & Encoding | yes | `probe_snapshot` treats a non-`str`/BLOB chunk cell as corrupt (reuse `probe_index`'s WR-02 guard, `crawler/index_health.py:152`); registry row validates at load (`extra="forbid"`, `crawler/models/crs_rules.py:150`). Fail-closed on malformed date (`_as_date`). |
| V6 Cryptography | yes (integrity only) | Content-drift uses stdlib `hashlib` (`chunk_sha` sha1 short fingerprint, `registry_fingerprint` sha256) — **integrity fingerprints, never secrets**; never hand-rolled. `[VERIFIED: crawler/searchindex.py:128, crawler/crs_rules.py:131]` |
| V7 Error Handling & Logging | yes | Refusal is a stable PII-free `reason=<code>` on the frozen contract; no traceback leak (the whole `probe_index` body is guarded, `crawler/index_health.py:120-163`). No PII/absolute path on stdout. |
| V12 File & Resource | yes | Read-only URI connect (`mode=ro`), never creates a 0-byte DB, never writes on refusal (`crawler/index_health.py:116`). |
| V2/V3/V4 (authn/session/access) | no | No auth/session/network surface in this phase. |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stale/superseded row greens a screen (dominant risk) | Tampering / Spoofing (of freshness) | `within_freshness` + `row_in_effect` fail-closed; grounded bound; negative-control tests. `[VERIFIED: .planning/research/PITFALLS.md:15-31]` |
| Snapshot content tamper/drift | Tampering | Per-chunk `chunk_sha` drift + snapshot `SNAPSHOT_DRIFTED`; registry tamper → `registry_fingerprint` drift. |
| SQL injection into the family probe | Tampering | Parameter-bound query (`WHERE relpath LIKE ?`) — never f-string, matching `build_index` discipline (`crawler/searchindex.py:355`). |
| PII/absolute-path leak on refusal | Information Disclosure | Echo only the corpus `--db`/family path; PII-perimeter assertion in the refusal test. |
| Second trust path / privilege elevation via unwired screen | Elevation of Privilege | ONE `gate_subset`; `_default_decider` AT-RISK for anything unwired. |
| Partial artifact on failure | Tampering (of state) | Preflight before `open_vault`/compute → zero-artifact refusal. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (`.venv`) | all | ✓ | 3.10.12 | — |
| pytest | tests | ✓ | 9.0.3 | — |
| SQLite FTS5 | index/snapshot probe | ✓ | bundled (FTS5 present; `test_index_health.py` runs) | — |
| pyyaml / pydantic / platformdirs | registry load / models | ✓ | 6.0.x / 2.13.x / 4.10.x | — |
| Real corpus / `corpus/dli/` | — | ✗ (not needed) | — | Synthetic fixture DBs/registries (Phase 40 is fixture-only by design) |

**Missing dependencies with no fallback:** none. **Missing with fallback:** the DLI family (Phase 41) — Phase 40 uses synthetic fixtures, so its absence does not block.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `within_freshness` belongs in `crs_audit.py` and `gate_subset` in `auditor.py` (vs a new `screening.py` module) | File Map / Patterns | LOW — placement is refactorable; the milestone research recommends these exact homes (`.planning/research/ARCHITECTURE.md:76,79`). If a new module is preferred, add it to the `no_inlined_volatile_rules` scan surface. |
| A2 | **Resolved:** the current corpus cannot ground an authoritative fixed DLI max-age, so Phase 40 ships only the fail-closed field/reader mechanism and synthetic grounded fixture proof; Phase 41 owns the concrete row with the DLI family | Code Examples / Plan 40-01 T-40-A2 | LOW — no value is fabricated or inlined; absence of a real bound fails closed until Phase 41 supplies grounded data. |
| A3 | A **separate** `probe_snapshot` (not a new parameter on `probe_index`) best preserves the frozen `probe_index` signature/tests | File Map / Alternatives | LOW — both work; separation keeps shipped tests byte-stable. |
| A4 | `probe_snapshot` classifies a snapshot family by `relpath LIKE 'family/%'` in the existing `chunks` table (the DLI family is a normal corpus family in the one index) | Pattern 4 | LOW — matches the "one FTS5 index, no second datastore" decision (`.planning/research/SUMMARY.md:141`) and `build_index` relpath shape (`crawler/searchindex.py:352`). |
| A5 | Phase 40 needs no new CLI *verb* (the helpers/preflight are consumed by later screens' handlers); it may add only internal functions | Out-of-Scope / File Map | LOW — no ROADMAP success criterion for Phase 40 requires a user-facing verb; SAFE-10's SC is about the preflight *mechanism*. A tiny `doctor`-style probe verb could be added if the planner wants a demonstrable entry point, but is not required. |

**These `[ASSUMED]`/discretion items are safe to resolve autonomously** per PROJECT.md's autonomous-execution directive; record the chosen rationale in the plan/PR. Only A2 carries a grounding nuance worth an explicit note in the plan.

## Open Questions (RESOLVED)

1. **Grounded staleness bound — value + citation.**
   - What we know: the *mechanism* is a `validity_window` row read via `_window_days`; the shipped ECA/language windows prove the pattern (`crawler/data/crs_rules/core.yaml:99,212`).
   - What's unclear: the authoritative source + exact `window_days` for the DLI/snapshot max-age (IRCC does not publish a fixed "valid for N days").
   - **Resolved:** Phase 40 ships the mechanism and synthetic grounded fixture proof without a placeholder row. Phase 41 owns the real bound and authoritative citation alongside the DLI family. No value is fabricated or inlined.

2. **Should `row_in_effect` be applied centrally inside `gate_subset` (dropping out-of-window rows) or left to each decider?**
   - What we know: applying it centrally would make "no in-window row ⇒ not green" the default, but changing the gate/consumed-subset behavior risks the frozen CRS grid (existing rows mostly carry no effective window, so `_in_window` True is safe — but the spine is frozen this milestone).
   - What's unclear: whether the planner wants central enforcement now or per-screen wiring in 42/44/45 + the Phase-46 conformance proof.
   - **Resolved:** keep `gate_subset` behavior-identical (grounding only); expose `row_in_effect`/`within_freshness` as separately-callable helpers; enforce per-screen and prove centrally in Phase 46.

3. **Demonstrable entry point for SAFE-10 in Phase 40 (no screen exists yet).**
   - What we know: the CLI wrapper + preflight are proven via unit/integration tests against a fixture family; no shipped verb calls `probe_snapshot` until Phase 44/45.
   - **Resolved:** prove SAFE-10 with a fixture-driven CLI refusal test (mirror `test_audit_index_refusal.py`); do not add a user-facing verb in Phase 40.

## Sources

### Primary (HIGH confidence — live codebase, read this session)
- `crawler/crs_audit.py` (`within_validity:142`, `_in_window:333`, `arranged_employment_guard:343`, `_window_days:58`, `_as_date:48`, `_VALIDITY_FIELD:35`) — freshness/effective-date primitives to mirror/compose.
- `crawler/auditor.py` (`_consumed_rows:68`, `_gate_or_raise:75`, `audit_one:181`, gate call `:207`) — the gate to promote.
- `crawler/index_health.py` (closed vocab `:43-48`, `IndexHealth:59`, `probe_index:85`, read-only connect `:116`, WR-02 non-text guard `:152`) — the preflight to mirror.
- `crawler/cli.py` (`_require_readable_index:760`, zero-artifact ordering `_cmd_vault_audit:1119-1123`) — refusal wrapper + ordering.
- `crawler/contract.py` (`INVALID_INPUT:48`, `EXIT_INVALID_INPUT:57`, `envelope:63`) — refusal envelope.
- `crawler/crs_rules.py` (`load_registry:104`, `registry_fingerprint:121`, `no_inlined_volatile_rules:458`, `_ALLOW_KEYS:402`) — drift + static gate.
- `crawler/models/crs_rules.py` (`MachineCheck:139`, `validity_window` fields `:159-162`, `VolatilityMeta:173`) — the frozen row model (already carries every needed field).
- `crawler/models/audit.py` (`PublicAuditEnvelope:125`, `registry_fingerprint` stamp `:210`) — frozen public boundary.
- `crawler/vault.py` (`is_audit_eligible:1078`, `is_stale:1048`, `audit_eligible_values:1099`) — evidence quarantine choke point (unchanged).
- `crawler/searchindex.py` (`chunk_sha:128`, `build_index` crawl_date/relpath `:344-356`, resolve drift `:548`) — content-hash + snapshot family shape.
- `crawler/data/crs_rules/core.yaml` (`:99-106`, `:212-219`) — grounded `validity_window` row precedent.
- Test precedents: `crawler/tests/test_index_health.py:19`, `test_audit_index_refusal.py`, `test_crs_audit.py:138-146,412`, `test_crs_no_inlined_rules.py:20-49`.
- `pyproject.toml:12-36` (dependencies + pytest config), `scripts/run_conformance.py` (release gate glob).

### Secondary (HIGH confidence — project planning artifacts, this milestone)
- `.planning/ROADMAP.md:120-154` (Phase 40 goal, success criteria, threat/privacy/grounding note; downstream dependencies `:160,175,188,201,229`).
- `.planning/REQUIREMENTS.md:45-46` (SAFE-09/SAFE-10), `:69` (no live lookup out of scope), `:100-101` (traceability).
- `.planning/research/ARCHITECTURE.md:73-84,101-121,135-139,213-230,264-268,452-500` (module map, seams, patterns, gate_subset/within_freshness recommendations).
- `.planning/research/PITFALLS.md:15-31,148-163,205-220,285-295` (Pitfalls 1/8/11 + checklist).
- `.planning/research/SUMMARY.md:15,61-62,84-88` (build-order + Phase 40 delivers).
- `.planning/STATE.md:81,88-150,180` (decisions, dominant-risk ownership, next step).
- `.github/copilot-instructions.md` (project constraints).

### Tertiary (LOW confidence)
- None — every recommendation traces to a shipped symbol or a milestone artifact read this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; every primitive verified in-repo.
- Architecture (helpers + promotion + preflight): HIGH — direct mirrors of tested shipped symbols; the only MEDIUM item is the concrete grounded bound value (A2).
- Pitfalls: HIGH — enumerated from live code + milestone PITFALLS.md with file:line evidence.
- Validation architecture: HIGH — framework/commands verified (`pytest 9.0.3`, 852-test baseline).

**Research date:** 2026-07-17
**Valid until:** 2026-08-16 (stable — internal codebase; no fast-moving external dependency). Re-verify only if `crs_audit.py`/`auditor.py`/`index_health.py` change before planning.
