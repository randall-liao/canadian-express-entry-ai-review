# Architecture Research — v4.1 CRS Auditor Hardening & Remediation

**Domain:** local-first, PII-safe CRS substantiation auditor (post-ITA Express Entry) — a hardening + remediation milestone layered on the shipped v4.0 codebase
**Researched:** 2026-07-17
**Confidence:** HIGH (grounded in direct source inspection of the shipped v4.0 modules, not external ecosystem survey)

> **Scope note.** This is a v4.0.x *hardening* milestone, not a greenfield build. The "architecture" here is therefore mostly a map of **existing integration points** and a disciplined plan for **what to extend vs. what to freeze**. The single most important constraint: **reuse the frozen `search` → `--cite` → grounding gate → JSON envelope trust path — do NOT invent a second trust path, second index, or second advice engine.** Every new output (remediation checklist, review packet) is a *projection of already-grounded audit verdicts*, never a fresh grounding surface.

---

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│  FROZEN TRUST PATH (v3.x + v4.0 — REUSE VERBATIM, do not fork)              │
│  ┌──────────┐   ┌──────────┐   ┌───────────────┐   ┌────────────────────┐   │
│  │ search   │──▶│  --cite  │──▶│ grounding gate│──▶│ JSON envelope       │   │
│  │(FTS5 ro) │   │ resolve  │   │ check_answer  │   │ (5-key, PII-light)  │   │
│  └────┬─────┘   └────┬─────┘   └──────┬────────┘   └─────────┬──────────┘   │
│   searchindex.py  searchindex.py   grounding.py          contract.py         │
└───────┼──────────────┼─────────────────┼──────────────────────┼────────────┘
        │              │                  │                      │
        ▼              ▼                  ▼                      ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  GROUNDED CRS DECISION CORE (v4.0 — mostly frozen; v4.1 EXTENDS data only)  │
│  ┌────────────────────┐   ┌──────────────────┐   ┌──────────────────────┐   │
│  │ crs_rules.py       │   │ crs_audit.py     │   │ auditors/ (dispatch)  │   │
│  │ + data/crs_rules/  │──▶│ deterministic    │──▶│ core · spouse ·       │   │
│  │ *.yaml (registry)  │   │ math (grounded)  │   │ transfer · additional │   │
│  └─────────┬──────────┘   └──────────────────┘   └───────────┬──────────┘   │
│   [v4.1 ▲ add CLB10 first-lang points rows]      [v4.1 ▲ decide_sibling]    │
│                                                   auditor.py (audit_one spine)│
└───────────────────────────────────────────────────────────┬────────────────┘
                                                              │ PrivateAuditReport
                       ┌──────────────────────────────────────┴─────────────┐
                       ▼                                                     ▼
┌───────────────────────────────────────┐   ┌────────────────────────────────────┐
│  VAULT (PII-BEARING, git-ignored)      │   │  PUBLIC (PII-LIGHT stdout)          │
│  candidates/<id>/vault.sqlite          │   │  PublicAuditEnvelope (5-key)        │
│  files/raw · rendered · text           │   │  verdicts · counts · citation ids   │
│  output/crs-audit/<run>.{json,md}      │   │  vault-RELATIVE report path only    │
│  ── v4.1 NEW artifacts ──              │   └────────────────────────────────────┘
│  output/remediation/<run>.md   [NEW]   │   ┌────────────────────────────────────┐
│  output/review-packet/<pkt>.*  [NEW]   │──▶│ publish-safe perimeter (VAULT-04)   │
└───────────────────────────────────────┘   │ check_publish_safe.py VAULT_SUBTREES│
                                             │  ── v4.1 ▲ add 2 new subtrees ──    │
                                             └────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | v4.1 disposition |
|-----------|----------------|------------------|
| `crawler/searchindex.py` | FTS5 read-only `search` + `resolve`; raises `sqlite3.OperationalError` on missing/corrupt DB | **Modify (small):** add a typed, PII-free index-availability probe reused by the auditor refusal path |
| `crawler/grounding.py` | Frozen grounding-by-construction gate (`check_answer`) | **Freeze** (no fork) |
| `crawler/crs_rules.py` + `data/crs_rules/*.yaml` | PII-free, corpus-cited CRS rule registry + `validate_registry` gate | **Modify (data):** add CLB 10 first-language points entries; regenerate `COVERAGE.md` |
| `crawler/crs_audit.py` | Deterministic CRS math (`to_clb`, `score_factor`, `age_on_date`, caps, cutoff, arranged-employment guard) — reads every number from grounded rows | **Freeze** (already generalizes over CLB levels; no code change to score CLB 10) |
| `crawler/auditors/__init__.py` | Dispatch spine: `DecisionContext`/`DecisionResult`, `register`/`resolve`, `FULL_GRID_FACTORS`, fail-closed default | **Freeze** (contract stays) |
| `crawler/auditors/core.py` | Core deciders (`_decide_language`, `_grounded_points`, age/education/work) | **Freeze** (data extension flows through unchanged) |
| `crawler/auditors/additional.py` | `decide_sibling` (currently fail-closed GAP), nomination/study/french/job-offer | **Modify:** `decide_sibling` consumes new confirmed sibling evidence |
| `crawler/auditor.py` | Generic `audit_one` spine + `audit_factor` shim + `run_full_audit`; `AuditGroundingError` (sole error surface) | **Modify (small):** raise a clean prerequisite refusal when the grounding index is missing/corrupt |
| `crawler/extraction.py` | Deterministic field extractors, `_FIELD_SPECS`, `_DOC_TYPE_FACTOR`, scan-quality classification | **Modify:** add sibling-relationship doc-type + fields; harden low-quality/ambiguous regressions |
| `crawler/audit_report.py` | Vault-only report writer, fail-closed ordering, `SCREENING_NOTICE`, PII-light down-projection | **Reference / light reuse** (the remediation + packet writers mirror its ordering) |
| `crawler/vault.py` | Vault schema (v3), additive migrations, `audit_runs`/`factor_verdicts`, `audit_eligible_values` | **Modify (maybe schema v4):** optional export-manifest trail table (additive) |
| `crawler/cli.py` | `--json` dispatch, `vault audit`, error→envelope mapping | **Modify:** new `vault remediate` / `vault review-packet` verbs; audit index-refusal mapping |
| `crawler/models/audit.py` | Two-tier PII boundary models (`PublicAuditEnvelope` vs `PrivateFactorCard`) | **Reference:** new public/private models for remediation + packet mirror this split |
| `scripts/check_publish_safe.py` | Publish-safe perimeter (`VAULT_SUBTREES`, `VAULT_ARTIFACT_EXTS`) | **Modify (data):** add `output/remediation/` + `output/review-packet/` subtrees |
| `personal.example/crs-profile.example.yaml` | Tracked synthetic example profile | **Modify:** re-key to dotted grid factor ids |
| **`crawler/remediation.py`** | Derive per-factor next actions from `GAP`/`AT-RISK` cards | **NEW** |
| **`crawler/review_packet.py`** | Build an opt-in, explicitly-redacted lawyer/RCIC packet from selected findings | **NEW** |

---

## Existing Integration Points (explicit anchors)

These are the exact seams v4.1 plugs into. Named so plans can reference them without re-discovery.

1. **Grounding gate reuse (the trust path).**
   `auditor._gate_or_raise()` → `crs_rules.validate_registry(subset, db)` → `grounding.check_answer` → `searchindex.resolve/search`. Any consumed rule that fails the gate, or any consumed `gap:true` row, raises `auditor.AuditGroundingError` **before any evidence read or artifact write** (`auditor.py:75-91`, `auditor.py:205-208`). *Remediation and the review packet must not add a new call into this gate — they consume the citation ids the audit already gated.*

2. **Verdict → report seam (SC5 fail-closed ordering).**
   `audit_report.run_audit()` / `run_full_audit_report()` compute the verdict **first**; only on success do they mint the `aud_` run id, write `output/crs-audit/<run>.{json,md}`, persist `audit_runs` + `factor_verdicts`, and down-project to `PublicAuditEnvelope` (`audit_report.py:134-265`). A grounding failure leaves **zero artifacts**. The remediation/packet writers must replicate this "compute-then-write, refuse-writes-nothing" ordering.

3. **Persisted audit trail (the read source for remediation/packet).**
   `output/crs-audit/<aud_run_id>.json` is the full `PrivateAuditReport` (PII-bearing, vault-only), and `audit_runs` / `factor_verdicts` rows hold the same verdicts keyed by `aud_run_id` (`vault.py:194-219`, `audit_report.py:176-190`). **Remediation and the packet read a completed run by id** rather than re-auditing — decoupling them from grounding entirely.

4. **Grounded points lookup (the higher-CLB seam).**
   `auditors/core._grounded_points()` and `crs_audit.score_factor()` iterate a factor's `points_by_level` entries and return `None` when no grounded entry covers the value (`core.py:180-203`, `crs_audit.py:231-284`). The CLB 10 gap is that `core.language.first.points` only encodes CLB 9 entries (`data/crs_rules/core.yaml:221-253`); adding CLB 10 entries makes `substantiated_points` non-`None` **with no code change** — the lookups already generalize over levels.

5. **Extraction → factor linkage (the sibling seam).**
   `extraction._FIELD_SPECS` (per-doc-type field regexes) + `extraction._DOC_TYPE_FACTOR` (document→grid-factor map, `extraction.py:167-232`) feed confirmed values into `vault.audit_eligible_values(factor_id)` → `auditor.audit_one` → `DecisionContext.by_field`. `decide_sibling` currently returns a truthful `GAP` because no sibling field exists (`additional.py:146-158`). The `additional.sibling` **grounded rule row already exists** (`data/crs_rules/additional.yaml:186-213`, `level: sibling → 15 points`), so closing the gap is purely extraction-side + a decider update.

6. **Test-type / field vocabulary anti-drift pin.**
   `crawler/testtypes.py` is the single source of truth for language test types, pinned set-equal to the registry accepted-enum by an anti-drift test (v4.0 gap-closure 30-05). Any **new sibling field vocabulary** must follow the same pattern: one canonical name set, pinned by a test so P30 extraction and the `decide_sibling` consumer can never silently diverge.

7. **CLI error → envelope mapping.**
   `_cmd_vault_audit` (`cli.py:1087-1139`) catches `AuditGroundingError` and `PathEscapeError` → `invalid_input`/exit 2, but **not** `sqlite3.OperationalError`; a missing/corrupt `--db` therefore falls through to the top-level catch-all → `internal_error`/exit 4 (`cli.py:1447-1469`). This is the exact tech-debt surface v4.1 must convert into a clean, actionable refusal.

8. **Publish-safe perimeter (VAULT-04).**
   `check_publish_safe.py` flags any tracked file under `VAULT_SUBTREES` with a `VAULT_ARTIFACT_EXTS` extension, plus any `candidates/` segment or `*.sqlite*` (`check_publish_safe.py:69-77, 174-200`). New vault artifact subtrees must be **added to `VAULT_SUBTREES`** so coverage is self-documenting (belt-and-suspenders with the `candidates/` catch-all).

9. **Two-tier PII model boundary.**
   `models/audit.py` splits PII-light public tier (`PublicAuditEnvelope`, `citation_id` firewall rejecting `ev_`) from PII-bearing private tier (`PrivateFactorCard`, holds `ev_` + applicant values). New remediation/packet outputs must instantiate the **same split**: a PII-light `--json` envelope + a vault-only PII-bearing artifact.

---

## New vs Modified Components

| # | Change | Kind | Files | Trust-path impact |
|---|--------|------|-------|-------------------|
| A | CLB 10 first-language points rows (+ audit second-lang/French maxima) | **Data** | `data/crs_rules/core.yaml`, `COVERAGE.md` | none — same gate, retrieve-what-you-cite |
| B | Sibling-relationship evidence: doc-type, field specs, factor link, vocabulary pin | **Modify** | `extraction.py`, new `crawler/siblingfields.py` (vocab), `auditors/additional.py` | none — grounded row already exists |
| C | Missing/corrupt-index → clean fail-closed refusal | **Modify (small)** | `searchindex.py` (typed probe), `auditor.py` (raise typed error), `cli.py` (map to envelope), `contract.py` (new error-type constant) | strengthens fail-closed; no new grounding |
| D | Example-profile re-key to dotted grid ids + end-to-end conformance | **Modify + test** | `personal.example/crs-profile.example.yaml`, new conformance test | none |
| E | Extraction regressions for low-quality/ambiguous docs | **Test (+ maybe thresholds)** | `test_extraction*.py`, fixtures | none |
| F | Grounded remediation checklist | **NEW** | `crawler/remediation.py`, `models/remediation.py`, `cli.py`, `check_publish_safe.py` | none — derives from gated verdicts |
| G | Redacted lawyer/RCIC review packet | **NEW** | `crawler/review_packet.py`, `models/review_packet.py`, `cli.py`, `check_publish_safe.py`, (opt.) `vault.py` schema v4 | none — projection + redaction + render-then-scan |
| H | Conformance/release-gate extension | **Test** | `test_conformance_v40_*.py` (or new `_v41_`), `scripts/run_conformance.py` | proves the above hold the line |

---

## Recommended Project Structure

New/changed files, following the established `crawler/` flat-module + `crawler/models/` + `crawler/data/` conventions:

```
crawler/
├── remediation.py            # NEW — GAP/AT-RISK cards → grounded next-action checklist
├── review_packet.py          # NEW — selected findings → redacted, render-then-scanned packet
├── siblingfields.py          # NEW — canonical sibling field-name vocabulary (anti-drift pin)
├── extraction.py             # MOD — sibling doc-type in _FIELD_SPECS + _DOC_TYPE_FACTOR
├── auditor.py                # MOD — typed prerequisite refusal (missing/corrupt index)
├── searchindex.py            # MOD — ensure_readable(db) typed probe (reused by auditor)
├── cli.py                    # MOD — vault remediate / vault review-packet verbs + refusal mapping
├── contract.py               # MOD — GROUNDING_UNAVAILABLE error-type constant (non-breaking)
├── auditors/additional.py    # MOD — decide_sibling consumes confirmed sibling chain
├── models/
│   ├── remediation.py        # NEW — PublicRemediationEnvelope + PrivateRemediationChecklist
│   └── review_packet.py      # NEW — PublicPacketEnvelope + PrivateReviewPacket + RedactionManifest
├── data/crs_rules/
│   ├── core.yaml             # MOD — CLB 10 first-language PointsEntry rows
│   └── COVERAGE.md           # MOD — regenerated (still COMPLETE, 0 gaps)
└── tests/
    ├── test_remediation.py                 # NEW
    ├── test_review_packet_redaction.py     # NEW
    ├── test_example_profile_audit.py       # NEW — dotted-id example audits end-to-end
    ├── test_audit_missing_index_refusal.py # NEW
    ├── test_sibling_evidence.py            # NEW
    └── test_conformance_v40_*.py           # MOD — extend privacy/no-false-green/framing

personal.example/
└── crs-profile.example.yaml  # MOD — dotted grid factor ids

scripts/
└── check_publish_safe.py     # MOD — VAULT_SUBTREES += output/remediation/, output/review-packet/
```

### Structure Rationale

- **`remediation.py` / `review_packet.py` are peers of `audit_report.py`, not extensions of it.** Each is a distinct output *projection* with its own two-tier model and its own vault subtree. Keeping them separate preserves single-responsibility and lets the audit writer stay frozen.
- **`siblingfields.py` mirrors `testtypes.py`.** The one lesson from the v4.0 integration blockers (BLOCKER B) was that any new extraction↔consumer vocabulary MUST be a shared, test-pinned constant — never two hand-copied string lists.
- **`searchindex.ensure_readable` lives in the retrieval module, not the auditor**, so the same typed refusal is available to any grounding consumer (audit today, remediation-that-re-audits never, but future callers benefit).

---

## Architectural Patterns

### Pattern 1: Grounding-by-construction reuse (NO second trust path)

**What:** Every requirement claim resolves through `search` → `--cite` → `grounding.check_answer` → PII-light envelope. New v4.1 outputs never open a new index, never call a model/NLI, never craft new citations.
**When:** All of it. This is the milestone's hard invariant.
**Trade-off:** Remediation/packet can only cite what the audit already grounded — that is the point (it keeps action guidance auditable and prevents an ungrounded advice engine).

**Example:**
```python
# remediation.py — cite ONLY the ids the audit already gated; never re-ground.
def remediation_items(report: PrivateAuditReport) -> list[RemediationItem]:
    items = []
    for card in report.factor_cards:
        if card.verdict in ("GAP", "AT-RISK"):
            action = ACTION_TEMPLATES[(card.factor_id, card.reason_code)]  # non-volatile prose
            items.append(RemediationItem(
                factor_id=card.factor_id, verdict=card.verdict,
                action=action,                                  # generic, PII-free template
                rule_citation_ids=card.rule_citation_ids))       # reuse gated corpus ids
    return items
```

### Pattern 2: Derive-from-verdicts (consume `PrivateAuditReport`, never re-audit)

**What:** Remediation and the review packet read a *completed* audit run (`output/crs-audit/<aud_id>.json`) by id and project it. They do not touch the registry, the gate, or the vault evidence tables.
**When:** Both new outputs.
**Trade-off:** Requires an audit to have run first (a clean prerequisite, surfaced as a fail-closed refusal if the run id is unknown) — in exchange, the two features are fully decoupled from grounding and cannot introduce a false-green.

### Pattern 3: Two-tier PII boundary (public envelope vs vault-only artifact)

**What:** Each output has a PII-light pydantic envelope (`extra="forbid"`, `citation_id` rejects `ev_`) emitted on `--json` stdout, and a PII-bearing artifact written ONLY under the vault. Mirror `models/audit.py`.
**When:** All new outputs.
**Trade-off:** Two models per feature — but the firewall becomes a *structural* load-time guarantee, not a runtime hope.

### Pattern 4: Fail-closed prerequisite guard (typed refusal before any write)

**What:** Detect a missing prerequisite (corrupt/absent corpus index; unknown audit run id) and raise a **typed, PII-free** exception carrying an *actionable* message, mapped by the CLI to a stable error envelope + non-zero exit. No artifact is written.
**When:** Missing/corrupt index (work C); unknown/incomplete run id (F, G).
**Trade-off:** Slightly more surface than "let it throw," but converts a raw `internal_error`/traceback into a stable contract an agent can branch on.

**Example:**
```python
# searchindex.py — one place owns the "is this a usable index?" question.
class IndexUnavailable(RuntimeError):
    """Corpus index missing/corrupt — PII-free, actionable message."""

def ensure_readable(db: Path) -> None:
    if not Path(db).exists():
        raise IndexUnavailable(
            f"corpus index not found at {db!s} — run `corpus-crawler --json index`")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.execute("SELECT 1 FROM chunks LIMIT 1"); con.close()
    except sqlite3.DatabaseError as exc:
        raise IndexUnavailable(f"corpus index unreadable/corrupt at {db!s}: {exc}")

# auditor.audit_factor / run_full_audit: call ensure_readable(db) up-front, and
# let IndexUnavailable propagate like AuditGroundingError (no artifact written).
# cli._cmd_vault_audit: except (AuditGroundingError, IndexUnavailable) -> envelope.
```
> Design choice: introduce a new `contract.GROUNDING_UNAVAILABLE = "grounding_unavailable"` error-type string (the envelope schema does not enumerate error types, so this is **non-breaking**) with a dedicated exit code, OR reuse `invalid_input`/exit 2. Recommend a distinct type + exit so operators can distinguish "your inputs are bad" from "the corpus index is missing" — but either preserves fail-closed + artifact-free.

### Pattern 5: Additive migration keyed on `PRAGMA user_version`

**What:** If the review packet needs an audit trail (which findings were exported, at what redaction level, when), add a `user_version < 4` branch to `vault._migrate` that runs additive DDL for an `export_manifests` table and bumps to 4 — existing rows untouched (`vault.py:328-375`).
**When:** Only if we persist an export trail (recommended for the "applicant-controlled" audit story). Remediation can stay **derive-only** (no schema change).
**Trade-off:** Schema v4 adds durability/auditability; derive-only keeps the surface minimal. Prefer derive-only for remediation; add the manifest table for the packet if the audit trail is deemed valuable.

### Pattern 6: Shared vocabulary pin (anti-drift) for new fields

**What:** New sibling field names live in one module (`siblingfields.py`) and are pinned set-equal to the consumer's expectations by a test — exactly like `testtypes.py` ↔ registry accepted-enum.
**When:** Sibling evidence (work B).
**Trade-off:** One extra module + one pin test; eliminates the class of "phases pass individually, integration fails" bug that produced v4.0's BLOCKER A/B.

### Pattern 7: Render-then-scan double gate for the redacted packet

**What:** The review packet is (1) path-contained to the vault (primary control), (2) built via an explicit redaction transform that strips direct identifiers, and (3) run through `check_publish_safe.scan_text` before write — a scan hit is a fail-closed refusal that writes nothing. This mirrors the shipped `ground`/`checklist` render→scan→write-to-`personal/` flow (`cli.py:455-584`).
**When:** Review packet only (remediation stays vault-path-contained like the audit report).
**Trade-off:** The scanner catches secrets/abs-paths, NOT intended finding content — so it is a *tripwire*, never the primary privacy control. Path containment + explicit redaction remain primary.

---

## Data Flow

### Flow 1 — Higher-CLB completion (data-only)

```
data/crs_rules/core.yaml (add CLB10 PointsEntry: 32/34, cite crs-criteria.md#006)
   ↓ load_registry()
crs_rules.validate_registry (frozen gate) — verbatim quote "CLB 10 or more  | 32  | 34"
   ↓ (already in chunk #006 — VERIFIED groundable)
audit_one → decider → core._grounded_points / crs_audit.score_factor
   ↓ (now returns 32/34 instead of None for a CLB10 candidate)
PrivateFactorCard.substantiated_points = non-None  →  substantiated_total correct
```
*No Python change. The verdict was already `SUBSTANTIATED`; only the points figure was `None`.*

### Flow 2 — Sibling evidence (extraction-side + decider)

```
vault import (sibling_relationship doc)  →  vault extract
   ↓ extraction._FIELD_SPECS["sibling_relationship"] = [relationship, sibling_status, sibling_residence, ...]
   ↓ _DOC_TYPE_FACTOR["sibling_relationship"] = "additional.sibling"
pending values  →  vault confirm (per field)  →  audit_eligible_values("additional.sibling")
   ↓ audit_one → decide_sibling(ctx)
   ↓ (relationship + citizen/PR status + Canadian residence ALL confirmed?)
   ├─ yes → _grounded_points(registry, "additional.sibling", "sibling") = 15 → SUBSTANTIATED
   └─ any missing → GAP "missing_evidence" (fail-closed, unchanged default)
```

### Flow 3 — Missing/corrupt-index refusal

```
vault audit --db <bad/missing>.db
   ↓ auditor.audit_factor / run_full_audit → searchindex.ensure_readable(db)  [NEW, up-front]
   ↓ IndexUnavailable raised BEFORE any evidence read / verdict / write
cli._cmd_vault_audit: except IndexUnavailable → envelope(grounding_unavailable, actionable msg)
   ↓ ok:false, non-zero exit, ZERO artifacts (report/rows never reached)
```

### Flow 4 — Grounded remediation checklist

```
vault remediate --run <aud_id>   (or --latest)
   ↓ load output/crs-audit/<aud_id>.json  →  PrivateAuditReport
   ↓ remediation.remediation_items(report)  — GAP/AT-RISK cards only
   ↓   action = ACTION_TEMPLATES[(factor_id, reason_code)]  (non-volatile; volatile figures read from grounded rows)
   ↓ PRIVATE: write output/remediation/<aud_id>.md  (PII-bearing, vault-only)
   ↓ PUBLIC:  PublicRemediationEnvelope (counts, factor ids, citation ids, vault-relative path) → --json
publish-safe: output/remediation/ in VAULT_SUBTREES
```

### Flow 5 — Redacted lawyer/RCIC review packet

```
vault review-packet --run <aud_id> --factor core.work --factor additional.sibling [--include-documents]
   ↓ load PrivateAuditReport  →  select findings the applicant chose
   ↓ review_packet.redact(finding) — replace name/UCI/DOB/score/employer/NOC with placeholders/ranges
   ↓ raw documents EXCLUDED by default (--include-documents is an explicit vault-internal opt-in)
   ↓ render markdown  →  check_publish_safe.scan_text(...)   [double gate]
   ├─ scan hit → REFUSE, write nothing (fail-closed)
   └─ clean → write output/review-packet/<pkt_id>.md (+ optional RedactionManifest json), vault-only
   ↓ (optional schema v4) record export_manifests row (pkt_id, aud_id, factors, redaction_level, ts)
   ↓ PUBLIC: PublicPacketEnvelope (counts, redaction summary, vault-relative path) → --json
publish-safe: output/review-packet/ in VAULT_SUBTREES
```

---

## Trust & Privacy Boundaries

| Boundary | Rule | Enforcement in v4.1 |
|----------|------|---------------------|
| **Corpus authority vs candidate evidence** | `citation_id` (`relpath#ordinal`) ≠ `evidence_id` (`ev_`); candidate text never citable | Reuse `models/audit.py` firewall in new envelopes; remediation/packet carry corpus citation ids only in PII-light tier, `ev_` only in vault-only tier |
| **Single trust path** | Only `grounding.check_answer` decides grounded/ungrounded | New outputs cite pre-gated ids; **no** new gate/index/model call (grep-assert like v4.0's frozen-core check) |
| **PII containment** | Applicant values live ONLY under `personal/candidates/<id>/…`; stdout + repo stay PII-light | New artifacts under `output/remediation/`, `output/review-packet/`; both added to `VAULT_SUBTREES`; `--json` envelopes are `extra="forbid"` PII-light |
| **No shareable raw docs** | Raw documents excluded from the packet by default | `--include-documents` is an explicit opt-in and even then stays vault-internal; packet defaults to redacted findings only |
| **Fail-closed everywhere** | Missing prerequisite → refusal, never a partial/guessed artifact | Typed `IndexUnavailable` + "compute/select-then-write" ordering; unknown/incomplete run id refuses |
| **No inlined volatile rules** | CLB/points/caps/dates never hard-coded in prose | Extend the `no_inlined_volatile_rules` static gate to `crawler/remediation.py` + `crawler/review_packet.py`; action templates are non-volatile, figures read from grounded rows |
| **Screening, not legal advice** | Output framed as substantiation screening | Remediation + packet MUST render the `SCREENING_NOTICE` (or an analog); SAFE-04 denylist scan stays clean |

---

## Schema & Migration Considerations

- **Registry data (work A):** No schema change — `core.language.first.points` gains CLB 10 `PointsEntry` rows; `PointsEntry`/`points_table` models already support labelled with/without-spouse columns. Regenerate `COVERAGE.md` (stays COMPLETE, 0 gaps). Verify the CLB 10 quote is a verbatim substring of `guidance/crs-criteria.md#006` — **confirmed present** ("CLB 10 or more  | 32  | 34").
- **Vault schema (work G, optional):** If persisting an export trail, add `user_version < 4` branch → additive `export_manifests(packet_id, audit_run_id, included_factors_json, redaction_level, created_at, packet_relpath)` + bump `schema_version` meta to "4". Fresh DBs fall through v1→v2→v3→v4; existing rows untouched (`vault.py` pattern). **Remediation needs no schema change** (derive-only).
- **Extraction fields (work B):** No DDL change — `extracted_values` already stores arbitrary `field_name`/`normalized_value` rows; sibling fields are new `field_name` values, not new columns. Staleness keys and `is_audit_eligible` apply unchanged.
- **Contract (work C):** New `error.type` string constant is non-breaking (the 5-key envelope schema does not enumerate error types); `SCHEMA_VERSION` stays "1.0".
- **Backward compatibility:** All migrations additive and idempotent; an old vault opened by v4.1 upgrades in place; a v4.1 vault is never downgraded.

---

## Anti-Patterns

### Anti-Pattern 1: Re-grounding inside remediation/packet
**What people do:** Have the remediation writer call `search`/`ground` to "find how to fix X."
**Why it's wrong:** Opens a second trust path; produces citations the audit never validated; risks ungrounded advice.
**Do this instead:** Cite only the `rule_citation_ids` already on the verdict card. If a genuinely new citation is ever needed, route it through the *same* frozen gate — but default to reuse.

### Anti-Pattern 2: Treating the publish-safe scanner as the packet's primary privacy control
**What people do:** Write the packet anywhere and rely on `scan_text` to catch leaks.
**Why it's wrong:** The scanner hunts secrets/abs-paths, not the applicant's employer/score/DOB — intended finding content sails through.
**Do this instead:** Path-contain to the vault (primary) + explicit redaction transform (primary) + scan as a tripwire (secondary). Never accept an arbitrary `--out`.

### Anti-Pattern 3: Hand-copying the sibling field names into the decider
**What people do:** List sibling field strings in `extraction.py` and again in `decide_sibling`.
**Why it's wrong:** This is exactly the v4.0 BLOCKER B drift class ("phases pass, integration fails").
**Do this instead:** One `siblingfields.py` constant, pinned set-equal by a test.

### Anti-Pattern 4: Fixing higher-CLB by relaxing the decider
**What people do:** Make `_grounded_points` fall back to a guessed value when no row matches.
**Why it's wrong:** Fabricates points — violates grounding-by-construction.
**Do this instead:** Add the grounded CLB 10 row (data). `None`-on-miss stays the fail-closed default.

### Anti-Pattern 5: Writing a partial artifact before the refusal is decided
**What people do:** Open/write the checklist/packet file, then validate.
**Why it's wrong:** Breaks the SC5 "grounding failure writes no partial report" guarantee.
**Do this instead:** Compute/select/redact/scan fully in memory; write only after all guards pass.

### Anti-Pattern 6: Auditing the example profile with mismatched ids and calling N/A "fine"
**What people do:** Ship `core_age` while the grid expects `core.age`; every factor silently becomes `N/A not_claimed`.
**Why it's wrong:** The example demonstrates nothing and hides the linkage; operators lose trust.
**Do this instead:** Re-key to dotted grid ids + a conformance test that asserts represented factors reach real verdicts against the real corpus (skip-guarded like `test_full_audit_real_seam.py`).

---

## Integration Points (internal boundaries)

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `remediation.py` ↔ `audit_report` output | Reads `output/crs-audit/<run>.json` (file), or a shared `load_report(run_id)` helper | Decouples remediation from grounding; refuse on unknown/incomplete run |
| `review_packet.py` ↔ `remediation.py` | May reuse remediation's finding-selection + citation reuse | Keep redaction logic in the packet module; share the selection primitive |
| `auditor.py` ↔ `searchindex.ensure_readable` | Direct call, up-front, raises `IndexUnavailable` | Single owner of "is the index usable?"; benefits all grounding consumers |
| `extraction.py` ↔ `auditors/additional.decide_sibling` | Via `siblingfields.py` vocab + `vault.audit_eligible_values` | Pinned set-equal by test (Pattern 6) |
| `cli.py` ↔ new verbs | `vault remediate`, `vault review-packet` sub-subparsers under `_add_vault_subparser` | PII-light `--json`; human detail → stderr (mirror `_cmd_vault_audit`) |
| new artifacts ↔ `check_publish_safe.VAULT_SUBTREES` | Path-prefix allow-list | Add `output/remediation/`, `output/review-packet/`; conformance test asserts coverage |
| new modules ↔ `no_inlined_volatile_rules` gate | Static self-scan | Extend the scanned path set to the two new modules |
| new outputs ↔ SAFE-04 framing | Rendered `SCREENING_NOTICE` + denylist scan | Remediation/packet carry the not-legal-advice notice |

### External Services

| Service | Integration | Notes |
|---------|-------------|-------|
| (none) | — | Local-only by constraint: no cloud OCR/LLM/vector/API; no network. All new work is stdlib + existing optional local extraction extras. |

---

## Dependency-Aware Build Order

Ordered so each step lands on a stable base and later steps reuse earlier fixtures. Roughly two independent early tracks that converge on remediation/packet.

1. **Track 1 — Coverage completion (data + evidence), unblocks a *complete* audit report.**
   1a. **Higher-CLB first-language points** (work A) — data-only, lowest risk; re-run retrieve-what-you-cite. *(Also audit second-language/French maxima for the same latent gap.)*
   1b. **Sibling evidence** (work B) — `siblingfields.py` + `_FIELD_SPECS`/`_DOC_TYPE_FACTOR` + `decide_sibling` + pin test. Independent of 1a.

2. **Track 2 — Operational hardening (parallel to Track 1).**
   2a. **Missing/corrupt-index refusal** (work C) — `searchindex.ensure_readable` + `auditor` up-front call + CLI mapping + contract constant. Land before remediation/packet since they exercise the audit path.
   2b. **Example-profile re-key + end-to-end conformance** (work D) — produces the reusable dotted-id fixture that remediation/packet tests consume.
   2c. **Extraction low-quality/ambiguous regressions** (work E) — adversarial fixtures; independent.

3. **Grounded remediation checklist** (work F) — depends on Track 1 (complete report) + step 2b (fixture) + step 2a (clean refusal on the shared audit path). New models + module + `output/remediation/` subtree + CLI verb + extend `no_inlined_volatile_rules`.

4. **Redacted review packet** (work G) — depends on F (reuses finding-selection + report-load) + redaction + render-then-scan double gate + `output/review-packet/` subtree + optional schema v4 export trail + CLI verb.

5. **Conformance / release-gate extension** (work H) — last: extend no-false-green (new rows/fields can't green a pending/stale value), privacy-containment (two new subtrees, non-vault output refused, packet redaction clean), retrieve-what-you-cite (CLB 10 + sibling rows ground the intended chunk), screening-framing (remediation/packet notice), and `scripts/run_conformance.py` glob.

**Critical path:** A/B (data completeness) → F (remediation) → G (packet) → H (gate). C/D/E are parallelizable but C and D should precede F.

---

## Open Questions / Verification Flags

- **Second-language / French higher-CLB parity.** The v4.0 tech-debt names only *first*-language CLB 10. Confirm whether `core.language.second.points` and `additional.french` rows have the same latent "grounded verdict, `None` points" gap and fold them into work A if so. *(Flag: verify against `core.yaml` second-language + French points rows.)*
- **Export audit trail: schema v4 vs derive-only.** Recommend derive-only for remediation; decide whether the review packet warrants an `export_manifests` table for the "applicant-controlled" audit story. Low-risk either way (additive migration).
- **Error-type + exit-code for index refusal.** Choose `grounding_unavailable` (+ new exit code) vs reusing `invalid_input`/exit 2. Recommend a distinct type so agents distinguish "bad input" from "missing corpus index." *(Non-breaking; `SCHEMA_VERSION` unchanged.)*
- **Redaction depth.** Define the default redaction allow/deny set (name, UCI, application/passport number, DOB → placeholder; scores/dates → range or coarse label) and whether the lawyer packet keeps enough substance to be useful while excluding raw docs by default. This is a policy call to settle in the F/G plans.
- **Remediation action-template grounding boundary.** Templates keyed by `(factor_id, reason_code)` must be *generic and non-volatile*; any concrete figure ("needs CLB N", "within M months") must be read from the grounded rule row, not the template — hold the two new modules to the `no_inlined_volatile_rules` gate.

## Sources

- Direct source inspection (HIGH confidence): `crawler/auditor.py`, `crawler/auditors/{__init__,core,additional}.py`, `crawler/crs_audit.py`, `crawler/crs_rules.py`, `crawler/data/crs_rules/{core,additional}.yaml` + `COVERAGE.md`, `crawler/searchindex.py`, `crawler/cli.py`, `crawler/contract.py`, `crawler/audit_report.py`, `crawler/vault.py`, `crawler/models/audit.py`, `crawler/extraction.py`, `scripts/check_publish_safe.py`, `personal.example/crs-profile.example.yaml`.
- Corpus groundability probe (HIGH): `guidance/crs-criteria.md#006` verified to contain "CLB 10 or more  | 32  | 34" (higher-CLB is a data-only change).
- Planning context: `.planning/PROJECT.md`, `.planning/STATE.md`, `.planning/milestones/v4.0-MILESTONE-AUDIT.md` (tech-debt frontmatter), `.planning/milestones/v4.0-REQUIREMENTS.md` (LATER-01..05), `.planning/research/{PITFALLS,FEATURES,SUMMARY}-v4.0.md`.

---
*Architecture research for: v4.1 CRS Auditor Hardening & Remediation (hardening milestone on the shipped v4.0 auditor)*
*Researched: 2026-07-17*
