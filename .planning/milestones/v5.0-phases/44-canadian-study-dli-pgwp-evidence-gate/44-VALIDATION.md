---
phase: 44
slug: canadian-study-dli-pgwp-evidence-gate
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-19
revised: 2026-07-19
---

# Phase 44 — Validation Strategy

| Property | Value |
|----------|-------|
| Framework | pytest |
| Quick | `.venv/bin/python -m pytest crawler/tests/test_study_review.py crawler/tests/test_study_review_audit_seam.py crawler/tests/test_study_review_cli.py crawler/tests/test_auditors_additional.py -q` |
| Phase | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_study_no_false_green.py -q` |
| Full | `.venv/bin/python -m pytest crawler/tests -q` |
| Gates | conformance + publish-safe + deterministic freeze pins |

## Per-Task Map

| Task | Plan | Wave | Reqs | Behavior | Exact command | Exists |
|------|------|------|------|----------|---------------|--------|
| 44-01-01 | 01 | 1 | STUDY-02 | Six study fields born pending on review.study; confirm/correct/reject; quality/five-key eligibility; all-factor isolation | `.venv/bin/python -m pytest crawler/tests/test_study_review.py -q -k "extract or field or confirm or quarantine or contamination"` | ❌ create |
| 44-02-01 | 02 | 1 | STUDY-03/04 | Explicit-then-env max-age resolver; invalid matrix; no default/inlined rule | `.venv/bin/python -m pytest crawler/tests/test_freshness_staleness.py crawler/tests/test_crs_no_inlined_rules.py -q -k "config or snapshot or inlined"` | ⚠ extend |
| 44-03-01 | 03 | 2 | STUDY-03/04 | Static + candidate transient Registry; shared validate/retrieve gate; one row per #000/#001+; common crawl_date/as_of; private/public projection | `.venv/bin/python -m pytest crawler/tests/test_gate_subset.py crawler/tests/test_study_review.py -q -k "sidecar or gate or transient or exact or pgwp or provenance or private or public"` | ⚠ extend |
| 44-03-02 | 03 | 2 | STUDY-03/04 | Credential-only decider never greens; real audit seam; every non-study factor including core.age unchanged | `.venv/bin/python -m pytest crawler/tests/test_auditors_additional.py crawler/tests/test_study_review_audit_seam.py -q -k "study or contamination or audit_seam"` | ❌/⚠ |
| 44-04-01 | 04 | 3 | STUDY-02/03/04 | Config-before-probe; exact common public as_of/null refusal; five-key envelope; exact PUBLIC_FIELDS; private data absent; zero artifacts | `.venv/bin/python -m pytest crawler/tests/test_study_review_cli.py -q` | ❌ create |
| 44-04-02 | 04 | 3 | STUDY-02/03/04 | Multi-candidate transient-row/tamper/provenance matrix; no SUBSTANTIATED/nonzero; family/DB/golden/schema/dependency freezes | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_study_no_false_green.py -q` | ❌ create |

Every task has an automated owner and a sub-60-second targeted command goal. The repository-wide full suite is a wave/phase gate, not a per-task command.

## Required Negative Matrix

| Class | Required cases | Owner |
|-------|----------------|-------|
| Confirmation | pending, rejected, corrected | 44-01-01 / 44-04-02 |
| Five-key staleness | file SHA, render SHA, parser version, profile claim version, registry version | 44-01-01 / 44-04-02 |
| Quality | low_quality, ambiguous | 44-01-01 / 44-04-02 |
| Config | missing, non-int, zero, negative, explicit-over-env | 44-02-01 / 44-04-01 |
| Index/snapshot | missing, empty, unreadable, corrupt, drifted, stale | 44-04-01 / 44-04-02 |
| DLI match | malformed, exact mismatch, name-only; UofT plus independent candidates | 44-03-01 / 44-04-02 |
| Dynamic grounding | one transient row per consumed chunk; tampered quote/marker/family/title-DLI pairing fails `gate_subset` | 44-03-01 / 44-04-02 |
| PGWP | UofT Yes, O246878951383 unique-marker Details, Eston No, mixed/malformed | 44-03-01 / 44-04-02 |
| Snapshot provenance | exact common nonempty chunk crawl_date; missing/unequal → snapshot_provenance_mismatch/null; direct pre-resolution sidecar null; CLI boundary `result:null` | 44-03-01 / 44-04-01/02 |
| Study evidence | missing tier/status/start/end, invalid/reversed dates, conflicting duplicates | 44-03-01 / 44-04-02 |
| Historical | exact current-only match | 44-03-01 / 44-04-02 |
| Grounding | missing/gap credential/R73 row; citation/selector disagreement; no static UofT runtime row | 44-03-01 / 44-04-02 |
| Grid seam | credential-only, forced DLI ignored, unwired factor | 44-03-02 / 44-04-02 |
| Contamination | core.age plus every other non-study factor | 44-03-02 / 44-04-02 |

Universal assertion: no case returns `SUBSTANTIATED` or nonzero points. Every config/index/snapshot preflight refusal exits nonzero and creates zero candidate/report/database artifacts; grounding/provenance refusal writes no report.

## Public/Private Contract Assertions

For successful `--json`:

1. Parse one JSON object.
2. Assert top-level keys are exactly `schema_version`, `ok`, `command`, `result`, `error`.
3. Assert `env["result"]` keys are exactly `study_review.PUBLIC_FIELDS`.
4. Assert `as_of` is exactly the common nonempty `crawl_date` across every consumed candidate DLI chunk, or null for sidecar pre-resolution/provenance refusal; boundary error envelopes have `result:null` and no date.
5. Scan the entire serialized object for:
   - seeded DLI number and `O\d{6,}` pattern
   - institution
   - credential/status/program dates
   - `ev_`
   - `relpath#ordinal`
   - source quote
   - absolute vault path
6. Assert all are absent.
7. Assert the vault-private report has ordinal-sorted `dynamic_citations`, exact entry keys, and one entry per transient row/consumed chunk, plus the same common as_of and screening notice.

## Deterministic Freeze Assertions

| Surface | Assertion |
|---------|-----------|
| Ignored `corpus/dli` | Non-empty canonical pre/post hash over sorted `.md` relpaths + body hashes + manifest byte hash |
| Ignored `corpus/index.db` | Pre/post SHA-256, size, mtime unchanged; SQLite opened `mode=ro` |
| Tracked golden DLI | Regenerated byte identity + `git show HEAD:<path>` comparison |
| Tracked frozen source | `git diff --quiet HEAD --` only for declared tracked files |
| Vault schema | `PRAGMA user_version == 3`; full table/index hash `9b35bc925c4ee39216980d4f74b937cd0b971c4f423116f1b84bf6bdb561fe50` |
| Dependencies | Exact existing three-package set |
| Lock | `poetry.lock` SHA-256 `6f5d47b3cfd2f78e6b796936b35ce2a3d2078447e0b61953e65114de71af3ef5` |

`pyproject.toml` is not modified. No marker update is required.

## Wave Gates

### After Wave 1

- `.venv/bin/python -m pytest crawler/tests/test_study_review.py crawler/tests/test_freshness_staleness.py crawler/tests/test_crs_no_inlined_rules.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_extraction.py crawler/tests/test_vault.py crawler/tests/test_siblingfields_vocab.py -q`

### After Wave 2

- `.venv/bin/python -m pytest crawler/tests/test_gate_subset.py crawler/tests/test_study_review.py crawler/tests/test_study_review_audit_seam.py crawler/tests/test_auditors_additional.py -q`
- `.venv/bin/python -m pytest crawler/tests/test_gate_subset.py crawler/tests/test_dli_grounding.py crawler/tests/test_conformance_v40_retrieve_what_you_cite.py -q`

### Phase Gate

- `.venv/bin/python -m pytest crawler/tests/test_study_review_cli.py crawler/tests/test_conformance_v5_study_no_false_green.py -q`
- `.venv/bin/python -m pytest crawler/tests -m conformance -q`
- `.venv/bin/python -m pytest crawler/tests -q`
- `.venv/bin/python scripts/check_publish_safe.py`

## Wave 0 Files

- [x] `crawler/tests/test_study_review.py`
- [x] Extend `crawler/tests/test_gate_subset.py`
- [x] `crawler/tests/test_study_review_audit_seam.py`
- [x] `crawler/tests/test_study_review_cli.py`
- [x] `crawler/tests/test_conformance_v5_study_no_false_green.py`
- [x] Extend `crawler/tests/test_freshness_staleness.py`
- [x] Extend `crawler/tests/test_crs_no_inlined_rules.py`
- [x] Extend `crawler/tests/test_auditors_additional.py`

No dependency installation or manual verification is required.

## Source Coverage Audit

| SOURCE | ID | Feature / constraint | Plan | Status | Notes |
|--------|----|----------------------|------|--------|-------|
| GOAL | — | Close credential-only false-green with exact grounded DLI study evidence and freshness | 01-04 | COVERED | Intake, resolver, sidecar/seam, CLI/conformance |
| REQ | STUDY-02 | Import/extract pending and per-field confirm/correct/reject | 01,04 | COVERED | Six private fields; E2E |
| REQ | STUDY-03 | Exact DLI + grounded credential + R73; credential alone never green | 03,04 | COVERED | Exact subset/chunks and real grid seam |
| REQ | STUDY-04 | Stale or historically unprovable designation stays AT-RISK/refusal | 02-04 | COVERED | Explicit bound, preflight, terminal cap |
| RESEARCH | R-01 | Candidate-scoped six-field eligible load | 01,03 | COVERED | Explicit document/candidate/factor query |
| RESEARCH | R-02 | One shared validate/retrieve gate over static + transient rows | 03,04 | COVERED | Quote/marker/family/DLI tamper controls |
| RESEARCH | R-03 | Exact discovery plus one transient row/private citation per #000/#001+ | 03,04 | COVERED | UofT Yes + Details/No candidates |
| RESEARCH | R-04 | One CLI resolver; sidecar explicit max_age_days | 02,04 | COVERED | No re-resolution |
| RESEARCH | R-05 | Private evidence report and closed public projection | 03,04 | COVERED | Whole-envelope privacy scan |
| RESEARCH | R-06 | Credential-only db-free decider never green | 03,04 | COVERED | No false DLI projection |
| RESEARCH | R-07 | Non-vacuous corpus/index/schema/dependency freezes | 04 | COVERED | Deterministic pins |
| RESEARCH | R-08 | `as_of` equals common validated DLI chunk crawl_date | 03,04 | COVERED | Exact timestamp, missing/mismatch/null matrix |
| CONTEXT | — | No Phase-44 CONTEXT.md exists | — | N/A | No locked/deferred discussion decisions to map |

Excluded, not missing: Phase-45 MEC wiring, live audit-time lookup, semantic/fuzzy matching, legal determination, new dependency, max-age default, and automated program-level PGWP inference.

**Audit result:** all GOAL/REQ/RESEARCH items are covered; no source item is missing.

**Approval:** revised for checker blockers 2026-07-19
