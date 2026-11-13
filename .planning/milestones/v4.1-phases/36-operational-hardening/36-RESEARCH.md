# Phase 36 — Research: Operational Hardening

**Researched:** 2026-07-17
**Consumed by:** 36-01/02/03 plans, 36-VALIDATION.md
**Scope:** grounding-prerequisite preflight/refusal, re-keyed pinned example profile,
adversarial extraction regressions. Zero new runtime dependencies.

This phase adds NO new domain logic — it hardens the operational edges of the
already-shipped v4.0/v4.1 auditor. All findings are grounded in the live codebase
(probed 2026-07-17) and the v4.1 milestone research under `.planning/research/`.

---

## Seam 1 — Grounding-prerequisite preflight & clean refusal (HARD-01, HARD-02)

### Current behaviour (probed)

`crawler/cli.py::_cmd_vault_audit` calls `audit_report.run_full_audit_report` /
`run_audit` with `args.db` (default `corpus/index.db`) and has **no `--db`
preflight**. A bad `--db` therefore escapes deep in the gate:

```
_cmd_vault_audit → run_full_audit_report → auditor.run_full_audit
  → audit_one → _gate_or_raise → crs_rules.validate_registry
  → grounding.check_answer → searchindex.resolve → sqlite3.connect(mode=ro).execute
  → sqlite3.OperationalError: unable to open database file
```

Observed for `--db corpus/NOPE.db`:
`{"ok": false, "error": {"type": "internal_error", "message": "OperationalError: unable to open database file"}}`, **exit 4**, plus a raw
Python traceback on stderr. Empty (`0`-byte) and corrupt (`printf 'not sqlite'`)
DBs crash the same way. This violates HARD-01 (not stable, not actionable, no
reason code, not "frozen contract vocabulary") and the spirit of HARD-02 (a
traceback, no recovery hint).

**Already-satisfied part of HARD-02:** the fail-closed *ordering* of `run_audit` /
`run_full_audit_report` computes the verdict FIRST and only then writes the report
+ `audit_runs`/`factor_verdicts` rows, so today's crash already writes **no**
audit artifact. Phase 36 must PRESERVE that and additionally make the refusal
clean, and it must refuse BEFORE opening the vault so no DB is even touched.

### Design

New module `crawler/index_health.py` — a typed, read-only, stdlib-`sqlite3`
preflight mirroring `crawler/doctor.py`'s dataclass/PII-light shape:

- `IndexHealth(status, reason)` frozen dataclass; `status` ∈ closed reason-code
  vocabulary `{ok, index_missing, index_empty, index_unreadable, index_corrupt,
  index_drifted}`.
- `probe_index(db) -> IndexHealth`, checks in fail-closed order:
  1. `not Path(db).is_file()` → `index_missing`.
  2. `st_size == 0` → `index_empty` (before opening; a 0-byte file is otherwise a
     valid empty SQLite DB).
  3. `sqlite3.connect("file:<db>?mode=ro", uri=True)` (read-only; never creates a
     0-byte DB — the WR-03 discipline `searchindex.resolve` already uses); an
     `OperationalError` at connect → `index_unreadable`.
  4. `SELECT name FROM sqlite_master` — a non-SQLite/corrupt file raises
     `sqlite3.DatabaseError: file is not a database` → `index_corrupt`.
  5. required tables `{chunks, chunks_fts, meta}` present, else `index_corrupt`.
  6. `SELECT count(*) FROM chunks` == 0 → `index_empty`; unreadable → `index_corrupt`.
  7. `SELECT count(*) FROM chunks_fts` (catches a malformed FTS vtable) →
     `index_corrupt` on `DatabaseError`.
  8. content-drift probe: sample the first `_DRIFT_SAMPLE` (=64) chunks, recompute
     `searchindex.chunk_sha(text)` and compare to the stored `chunk_sha`; any
     mismatch → `index_drifted` (defense-in-depth over the per-citation drift guard
     `searchindex.resolve` already enforces).
- `IndexHealth.message(db)` returns a stable, PII-free string:
  `corpus index unusable (reason=<status>): <reason>. Recover: rebuild it with
  'corpus-crawler --json index corpus/ --db <db>' (then verify with
  'corpus-crawler --json doctor').`

CLI wiring: a reusable helper `cli._require_readable_index(args, db)` returns an
`int` exit code (via `_vault_fail`, `invalid_input`/exit 2 — the SAME code
`_cmd_search`/`_cmd_ground` already return for `not a file: {db}`) on refusal, or
`None` when the index is healthy. `_cmd_vault_audit` calls it FIRST, before
`vault.open_vault`, so a refusal touches no vault, writes no artifact. The helper is
authored to be reused by Phases 37 (`remediate`) and 38 (`review-packet`) on the
shared report-load/audit path.

**Frozen-vocabulary compliance:** no new `contract.EXIT_*` constant, no new
`error.type`; the specific reason code lives in the message with a stable
`reason=<code>` prefix that a test can assert. `PRAGMA integrity_check` is
deliberately NOT run on the happy path (it is O(db) on a 14 MB file); table
presence + a bounded drift sample are sufficient and cheap.

### Risks / pitfalls (from `.planning/research/PITFALLS.md`)
- Do NOT open the index writable — a write-DDL FTS5 probe on a read path misreports
  a locked/read-only DB as "FTS5 missing" (the WR-01 lesson in `searchindex.search`).
  The preflight is SELECT-only.
- Do NOT echo an applicant value or an absolute personal-root path; the only path in
  the message is the caller-supplied `--db` (a corpus path, not PII), matching the
  existing `not a file: {db}` precedent.

---

## Seam 2 — Re-keyed + pinned example profile (HARD-03)

### Current behaviour (probed)

`personal.example/crs-profile.example.yaml` uses non-canonical `factor_id`s
(`core_age`, `core_education`, `core_first_language`, `spouse_education`,
`skill_education_language`, `additional_provincial_nomination`). `audit_one` maps a
claimed factor whose id is not on `auditors.FULL_GRID_FACTORS` to `N/A`
`not_claimed`. Probed `vault audit --all` with the example loaded:

```
counts = {factors:18, substantiated:0, gap:5, at_risk:0, na:13, ...}
core.* / spouse.* / additional.* claimed factors  → all N/A (not_claimed)
transfer.*  → GAP (derived, no substantiated core to recombine)
```

So the shipped example demonstrates **nothing** — every claimed factor is `N/A`.

### Design

Re-key the example in place to the canonical dotted grid ids and groups used by
`auditors.FULL_GRID_FACTORS` / `FACTOR_GROUP`:

| old id | new dotted id | group |
|---|---|---|
| core_age | core.age | core_human_capital |
| core_education | core.education | core_human_capital |
| core_first_language | core.language.first | core_human_capital |
| spouse_education | spouse.education | spouse_common_law |
| skill_education_language | transfer.education_language | skill_transferability |
| additional_provincial_nomination | additional.nomination | additional_points |

Keep every value SYNTHETIC/PII-free. A new anti-drift pin test asserts (a) every
example `factor_id` ∈ `FULL_GRID_FACTORS` (so the example can never silently drift
off the grid again) and (b) loading the example and running the real audit path
(`run_full_audit_report` against the real corpus, skip-guarded) yields **≥1**
applicable non-`N/A` verdict. Applicant-facing comments in the YAML are updated so
the illustration is honest about what audits.

**Note:** a claimed factor becomes non-`N/A` (SUBSTANTIATED/GAP/AT-RISK) the moment
it is on the grid AND claimed — SUBSTANTIATED additionally needs confirmed
audit-eligible evidence (which a bare profile has none of), so the example's claimed
factors will read `GAP`/`AT-RISK` (a truthful "claimed but unproven" state), which
is exactly the non-`N/A` "applicable verdict" HARD-03 wants. The pin proves
"applicable, not `N/A`", not "green".

---

## Seam 3 — Strengthened adversarial extraction regressions (HARD-04)

### Current behaviour

`crawler/extraction.py::classify_page_quality` already flags `scanned`
(density 0), `low_text` (`0 < density < _LOW_TEXT_THRESHOLD`), `rotated`
(`/Rotate` ∈ {90,180,270}), and `password_protected`; `_quality_flag` maps any of
these to `low_quality`. `_normalize_date` flags a numeric `A/B/YYYY` where both
components ≤ 12 as `ambiguous`. Extracted values are born `pending`;
`vault.is_audit_eligible` is True ONLY for confirmed/corrected + quality `ok` +
not-stale. The `_DOC_TYPE_FACTOR` claimed-only linkage (Phase 30-05) resolves a
document's values to the ONE factor its doc-type owns, scoped to CLAIMED factors,
so an injected/unclaimed target leaves values UNLINKED.

The gap HARD-04 closes is **coverage**: there is no regression proving these
adversarial states survive the REAL `import → extract → confirm → audit` seam
(today's real-seam tests use only clean fixtures). A future refactor could relax the
gate and no test would catch it.

### Design

Reuse the reportlab-free `make_fixtures.build_pdf` writer (supports per-page
`rotations` and empty/low-text page text) plus a small password-protected-flag hook
and an ambiguous-date page. Add `test_adversarial_extraction_seam.py`, skip-guarded
on `corpus/index.db` + extraction deps exactly like `test_full_audit_real_seam.py`.
Assertions, all through the shipped seam (never `add_extracted_value`):

1. A **rotated** language-test scan extracts `low_quality` values that CANNOT be
   confirmed to audit-eligible → `core.language.first` stays non-SUBSTANTIATED.
2. A **low-text** page → `low_quality`, same quarantine.
3. A **password-protected** page → `low_quality`, same quarantine.
4. An **ambiguous-date** (`05/06/1994`, both ≤ 12) DOB → `ambiguous`, not
   audit-eligible → `core.age` stays non-SUBSTANTIATED.
5. **No cross-factor contamination:** an adversarial document of one doc-type cannot
   place an audit-eligible value on a *different* factor (the claimed-only linkage
   holds through the real seam); and a `confirm`/`correct` on a `low_quality`/`ambiguous`
   value never makes it audit-eligible — the quarantine holds STRUCTURALLY because
   `confirm_value` sets `confirmation_status` but never mutates `quality_flag`, and
   `is_audit_eligible` requires `quality_flag=='ok'` — so it can never green.

No production code change is expected in Seam 3 unless a probe reveals a real gate
gap; the deliverable is a durable regression net. If the confirm path allows a
`correct` to bypass the quality gate, that is a genuine bug to fix (tightly coupled)
— to be confirmed during execution.

---

## Cross-cutting constraints (carried forward, frozen)

- Zero new runtime dependencies (pure stdlib `sqlite3`/`dataclasses`; reuse
  `searchindex.chunk_sha`, `contract`, `paths`, `doctor` patterns).
- No second trust path; no re-grounding/re-scoring; `search`→`--cite`→gate→envelope
  pipeline unchanged.
- Vault-only PII boundary; stdout/`--json` PII-light; refusal messages PII-free.
- Fail closed; every new refusal writes zero artifacts.
- Tracked tree stays publish-safe (`scripts/check_publish_safe.py` clean).
