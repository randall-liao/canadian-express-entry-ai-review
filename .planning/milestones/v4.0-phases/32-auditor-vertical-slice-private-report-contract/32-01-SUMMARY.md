---
phase: 32-auditor-vertical-slice-private-report-contract
plan: 01
subsystem: models
tags: [pydantic, audit, verdict, pii-boundary, crs]

requires:
  - phase: 29-candidate-vault
    provides: FactorGroup literal + ev_/citation_id namespace separation
  - phase: 31-grounded-crs-rule-registry
    provides: corpus relpath#ordinal citation shape (_CHUNK_ID_PATTERN)
provides:
  - Verdict vocabulary (SUBSTANTIATED/GAP/AT-RISK/N/A) as a closed Literal
  - PII-light public tier (PublicClaim, FactorVerdict, PublicAuditEnvelope)
  - PII-bearing private tier (PrivateFactorCard, PrivateAuditReport)
  - to_public_envelope down-projection seam (strict PII-light subset)
affects: [32-03 auditor engine, 32-04 report writer, 32-05 vault audit CLI, 33 fan-out]

tech-stack:
  added: []
  patterns:
    - "Two-tier PII model split enforced structurally by pydantic extra=forbid + field_validator"
    - "citation_id/evidence_id firewall: ev_-prefixed ids rejected in public claims"

key-files:
  created:
    - crawler/models/audit.py
    - crawler/tests/test_audit_models.py
  modified: []

key-decisions:
  - "PublicClaim.citation_id reuses the corpus relpath#ordinal pattern AND rejects ev_ prefixes"
  - "PublicAuditEnvelope.private_output_path guarded to vault-relative (no absolute/drive paths)"
  - "to_public_envelope builds claims from rule_citation_ids ONLY, never evidence_ids"
  - "PrivateAuditReport.created_at defaults to '' so the isolated model constructs without a clock"

patterns-established:
  - "Structural PII firewall: the public tier is incapable of holding an applicant value or ev_ id"

requirements-completed: [AUDIT-02, AUDIT-06]

duration: 12min
completed: 2026-07-06
---

# Phase 32 Plan 01: Audit Core Contract Summary

**Typed two-tier audit contract making the PII boundary a structural pydantic guarantee: a closed four-value verdict vocabulary, a PII-light public envelope that cannot carry applicant values or `ev_` pointers, a vault-only PII-bearing report, and a single tested down-projection seam.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2 (both TDD)
- **Files modified:** 2 (created)

## Accomplishments
- Defined `Verdict = Literal["SUBSTANTIATED","GAP","AT-RISK","N/A"]` — out-of-vocabulary rejected at the boundary (SC1).
- Built the PII-light public tier with an `ev_`-id `field_validator` firewall + `extra="forbid"` so an injected applicant/evidence key fails at load (SC4).
- Built the PII-bearing private tier (the only models permitted to hold applicant values + `ev_` pointers) and the `to_public_envelope` strict down-projection.

## Task Commits

1. **Task 1 (RED): verdict + public model tests** - `a65276b` (test)
2. **Task 1 (GREEN): verdict vocabulary + PII-light public models** - `8802f9e` (feat)
3. **Task 2 (RED): private tier + to_public_envelope tests** - `6181b65` (test)
4. **Task 2 (GREEN): PII-bearing private tier + down-projection seam** - `57497ea` (feat)

## Files Created/Modified
- `crawler/models/audit.py` — the audit CORE contract (verdict + 5 models + `to_public_envelope`).
- `crawler/tests/test_audit_models.py` — 15 boundary tests proving the PII firewall + down-projection.

## Verification
- `.venv/bin/python -m pytest crawler/tests/test_audit_models.py -q` → 15 passed.
- `.venv/bin/python -c "import crawler.models.audit"` → import OK (no new deps).
- `grep -n "ev_" crawler/models/audit.py` → rejection in `PublicClaim`, allowance only in `PrivateFactorCard.evidence_ids`.

## Deviations from Plan
None — plan executed exactly as written.

## Known Stubs
None.
