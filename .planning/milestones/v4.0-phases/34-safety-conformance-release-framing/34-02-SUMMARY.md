---
phase: 34-safety-conformance-release-framing
plan: 02
subsystem: testing
tags: [conformance, privacy, pii-perimeter, publish-safe, vault, pydantic, safety]

# Dependency graph
requires:
  - phase: 29-vault-pii-perimeter
    provides: publish-safe VAULT_ARTIFACT scan + .gitignore + resolve_within path guard
  - phase: 32-audit-slice
    provides: PII-light PublicAuditEnvelope + vault-only evidence-bearing report
  - phase: 33-full-auditor-pack
    provides: full-grid vault audit --all CLI flow
provides:
  - Authoritative SAFE-02 privacy-containment conformance module (end-to-end no-PII proof)
  - Non-vault-output-refusal + git-staging + tracked-tree publish-safe proofs
  - Public model firewall proof (ev_ citation / injected applicant key rejected by construction)
affects: [milestone-audit, release-gate, safety-conformance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "End-to-end CLI --json capture with distinctive synthetic sentinels"
    - "Report-is-vault-only vs stdout-is-PII-light dual assertion over the whole grid"

key-files:
  created:
    - crawler/tests/test_conformance_v40_privacy_containment.py
  modified: []

key-decisions:
  - "Consolidate the four shipped perimeter proofs into ONE end-to-end module without replacing them"
  - "Drive the error path via a patched ungrounded registry so the CLI emits a PII-free error envelope"
  - "Assert leaks impossible by construction (extra=forbid + ev_ citation_id validator), not just by test"

patterns-established:
  - "git add -A throwaway-repo staging test across every vault-artifact type"
  - "check_publish_safe.main() over the real tracked tree == 0 as a conformance assertion"

requirements-completed: [SAFE-02]

# Metrics
duration: 22min
completed: 2026-07-06
---

# Phase 34 Plan 02: SAFE-02 Privacy-Containment Conformance Summary

**Authoritative end-to-end privacy proof that no applicant value or ev_ evidence id reaches stdout / the public envelope across the whole import→confirm→full-grid-audit→report flow, the PII-bearing report stays vault-only, non-vault output is refused, and the tracked tree scans publish-safe.**

## Performance

- **Duration:** ~22 min (whole phase, parallel wave)
- **Tasks:** 2
- **Files created:** 1
- **Tests added:** 13 tests

## Accomplishments
- Full `vault audit --all` CLI flow with distinctive synthetic sentinels (fake nomination stream, distinctive raw score, distinctive DOB) proves no sentinel/PII and no `ev_` id appears on stdout or in the `PublicAuditEnvelope`; claims cite only corpus `relpath#ordinal` coordinates; `private_output_path` stays vault-relative; the evidence-bearing report exists ONLY under `candidates/<id>/output/crs-audit/` and DOES carry the sentinels + `ev_` ids.
- Error-path proof: a patched ungrounded consumed rule makes the CLI emit a PII-free error envelope (no sentinel / ev_ / tempdir path on stdout or stderr).
- Public model firewall: `PublicClaim` rejects an `ev_` citation_id, `PublicAuditEnvelope` rejects an injected applicant key and an absolute path — a leak is impossible by construction.
- Containment: `resolve_within` refuses `..`/symlink escapes and the writer targets only the crs-audit subtree; `scan_vault_artifact` flags every vault-artifact type and no ordinary repo JSON/MD; `git add -A` stages no vault artifact; `check_publish_safe.main()` returns 0 over the real tree; the tracked eval fixture is synthetic (no ev_, closed vocab, all four modules).

## Task Commits

1. **Task 1: End-to-end no-PII-to-stdout/envelope + vault-only report** - `b553502` (test)
2. **Task 2: Non-vault refusal + git-staging + tracked-tree publish-safe scan** - `b553502` (test)

## Files Created/Modified
- `crawler/tests/test_conformance_v40_privacy_containment.py` - SAFE-02 authoritative privacy-containment conformance module (361 lines).

## Decisions Made
- Consolidate the four shipped perimeter proofs into one end-to-end module (does not replace them; all four still pass).
- Drive the error path via a mocked `crs_rules.load_registry` returning an ungrounded registry so the real CLI emits the PII-free error envelope.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## Next Phase Readiness
SAFE-02 module is collected by the release gate. The tracked tree scans publish-safe (284 files, 0 violations) including the new release docs added in Plan 04.

---
*Phase: 34-safety-conformance-release-framing*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created files exist on disk; all task commit hashes are present in git history.
