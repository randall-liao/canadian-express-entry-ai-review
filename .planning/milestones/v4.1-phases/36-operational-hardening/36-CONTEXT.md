# Phase 36: Operational Hardening - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via `workflow.skip_discuss`)

<domain>
## Phase Boundary

Make the shipped v4.0/v4.1 CRS auditor **fail closed and stay trustworthy** at the
operational edges, on the existing frozen trust path — WITHOUT adding a runtime
dependency or a second trust/advice path. Three seams:

1. **Grounding-prerequisite preflight/refusal (HARD-01, HARD-02).** When the corpus
   index at `--db` is missing, empty, unreadable, corrupt, or content-drifted, the
   `vault audit` path must return a *stable, PII-free, actionable refusal envelope*
   using the frozen `contract` vocabulary plus a *specific reason code*, exit
   non-zero, recommend the existing `index`/`doctor` recovery command, and write
   NO audit / remediation / packet / database artifact. Today a bad `--db` escapes
   as a raw `sqlite3.OperationalError` → generic `internal_error`/exit 4 with a
   traceback and no recovery hint (confirmed by probe).

2. **Re-keyed + pinned example profile (HARD-03).** The shipped synthetic example
   `personal.example/crs-profile.example.yaml` uses NON-canonical factor ids
   (`core_age`, `core_first_language`, …) so every claimed factor audits as `N/A`
   `not_claimed` (confirmed by probe: 13 N/A). Re-key it to the canonical dotted
   grid ids (`core.age`, `core.language.first`, …), pin it to the live
   `auditors.FULL_GRID_FACTORS`, and prove it yields applicable non-`N/A` verdicts
   through the real CLI path.

3. **Strengthened adversarial extraction regressions (HARD-04).** Rotated, low-text,
   password-protected, and ambiguous-date fixtures must remain quarantined
   (`low_quality`/`ambiguous` → not audit-eligible) and must NOT green or
   contaminate another factor through the real `import → extract → confirm →
   audit` seam.

Do NOT expand into new policy domains, relax any verdict rule, re-ground/re-score,
add a PDF/templating/CLI/encryption/NER dependency, or alter the `search` →
`--cite` → grounding gate → JSON envelope pipeline.

</domain>

<decisions>
## Implementation Decisions

### Locked Decisions

- Preserve the frozen `search` → `--cite` → grounding gate → JSON envelope trust
  path and the `ev_`/`citation_id` namespace separation; zero new runtime deps.
- The index preflight is a NEW typed, read-only, stdlib-`sqlite3` probe. It NEVER
  writes, never creates a 0-byte DB, and runs BEFORE any audit compute or vault
  write so a refusal leaves zero artifacts (the fail-closed ordering already used
  by `run_audit`/`run_full_audit_report` is preserved and reinforced).
- The refusal keeps the frozen `contract` `error.type` vocabulary
  (`invalid_input`, exit 2 — the same code `search`/`ground` already use for a bad
  `--db`) and adds a *specific machine reason code* (`index_missing`,
  `index_empty`, `index_unreadable`, `index_corrupt`, `index_drifted`) plus an
  actionable recovery hint naming the existing `index`/`doctor` commands. No new
  `EXIT_*` constant and no new `error.type` are introduced.
- The refusal message is PII-free (index path + reason code + recovery hint only;
  never an applicant value or an absolute personal-root path).
- Re-key the example profile in place to canonical dotted ids; it stays TRACKED
  and PII-free (synthetic placeholders only). A pin test asserts every example
  `factor_id` ∈ `auditors.FULL_GRID_FACTORS` (anti-drift) and the example produces
  ≥1 applicable non-`N/A` verdict through the real CLI/audit path.
- Adversarial fixtures are GENERATED AT TEST TIME (reuse the reportlab-free
  `make_fixtures.build_pdf` writer; rotations, empty/low-text pages,
  password-protected flag, ambiguous `A/B/YYYY` dates) — never committed binaries.
- Adversarial regressions run through the REAL seam (`import_document` →
  `extraction.extract_document` → `confirm_value` → audit), skip-guarded on the
  git-ignored `corpus/index.db` + extraction deps exactly like
  `test_full_audit_real_seam.py`.

### Agent Discretion

All remaining implementation choices are at the agent's discretion. Prefer the
existing `contract`/`paths`/`searchindex`/`doctor` primitives and the established
real-seam + anti-drift test patterns. Add no runtime dependency.

</decisions>

<code_context>
## Existing Code Insights

- `crawler/cli.py::_cmd_vault_audit` opens the vault, loads the registry, and calls
  `audit_report.run_full_audit_report` / `run_audit` with `args.db`
  (default `corpus/index.db`); it has NO `--db` preflight (unlike `_cmd_search` /
  `_cmd_ground`, which return `invalid_input`/exit 2 for `not a file`).
- `crawler/searchindex.py` already opens read-only (`file:<db>?mode=ro`) and
  fail-closes on per-row drift (`chunk_sha` mismatch → `resolve` returns None). It
  exposes `DB_SCHEMA_VERSION`, `chunk_sha`, and the `chunks`/`chunks_fts`/`meta`
  schema — the raw material for a structural + drift preflight.
- `crawler/doctor.py` is the existing PII-light preflight precedent (a `DepStatus`/
  `DoctorReport` dataclass + PII-light `to_result`) — the index preflight mirrors
  its shape and the recovery-hint style.
- `crawler/contract.py` freezes the envelope vocabulary (`invalid_input`,
  `missing_dependency`, `internal_error`; `EXIT_INVALID_INPUT=2`).
- `crawler/auditors/__init__.py::FULL_GRID_FACTORS` is the canonical dotted grid the
  example profile must pin to; `audit_one` maps a claimed `factor_id` to `N/A`
  `not_claimed` when it is not on the grid.
- `crawler/extraction.py` classifies page quality (`scanned`/`low_text`/`rotated`/
  `password_protected` → `low_quality`; ambiguous `A/B/YYYY` → `ambiguous`) and
  forces every extracted value `pending`; `vault.is_audit_eligible` requires
  confirmed/corrected + quality `ok` + not-stale; the `_DOC_TYPE_FACTOR` claimed-only
  linkage prevents cross-factor contamination (Phase 30-05).
- `crawler/tests/test_full_audit_real_seam.py` + `fixtures/extraction/make_fixtures.py`
  are the real-seam + fixture-generation patterns to reuse.
- `scripts/check_publish_safe.py` is the tracked-tree privacy gate; any new tracked
  file (re-keyed example, tests) must stay clean.

</code_context>

<specifics>
## Specific Ideas

- Reason codes are a closed, tested vocabulary; each maps to one recovery hint.
- The preflight is reusable so Phases 37–38 refuse identically on the shared audit/
  report-load path (this phase "produces the clean-refusal path 37–38 rely on").
- Keep the human traceback OFF the refusal path — the refusal is one clean envelope.

</specifics>

<deferred>
## Deferred Ideas

Legacy arranged-employment resolution, live DLI/PGWP lookup, NOC-duty semantic
review, MEC sidecars, encrypted packets, and model-based inference remain out of
scope.

</deferred>
