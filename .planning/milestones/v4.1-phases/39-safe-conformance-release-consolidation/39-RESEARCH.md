# Phase 39 — Research: SAFE Conformance & Release Consolidation

**Researched:** 2026-07-17
**Consumed by:** 39-01/02/03 plans. Zero new runtime deps; no new domain behaviour.

This phase consolidates the v4.1 safety guarantees into an authoritative
`test_conformance_v41_*` layer + one release gate, mirroring the shipped v4.0 pattern
(`test_conformance_v40_*` + `scripts/run_conformance.py`).

## SAFE-05 — coverage / no-false-green (test_conformance_v41_coverage.py)

- **Priced-or-flagged (unguarded):** every CLB level `crawler/crs_audit.score_factor`
  emits for `core.language.first` (both spouse modes) is non-None (priced) — the
  Phase-35 anti-drift pin; and any `SUBSTANTIATED`-but-unpriced card sets
  `points_unresolved` / `counts["unpriced"]` (never a silent complete-looking 0).
- **Sibling no-false-green (unguarded + skip-guarded):** the `decide_sibling` fail-closed
  matrix — missing / non-accepted token / unresolved DOB / no ITA date / no grounded
  threshold → GAP/AT-RISK; `age < min_age` → AT-RISK `sibling_minor`; only a confirmed,
  claimed-scoped adult chain → SUBSTANTIATED (Phase-35). Real-seam adult→SUBSTANTIATED /
  minor→AT-RISK (skip-guarded on corpus + deps).
- **Adversarial no-false-green (skip-guarded):** rotated / low-text / password-protected
  / ambiguous-date fixtures stay quarantined (`low_quality`/`ambiguous` → never
  audit-eligible) through the real `import→extract→confirm→audit` seam and never green /
  contaminate another factor (Phase-36).

## SAFE-06 — remediation / packet privacy (test_conformance_v41_privacy.py)

- **PII-light stdout (unguarded):** `PublicRemediationSummary` + `PublicPacketSummary`
  `model_dump()` carry no `ev_`, no applicant value, and a vault-relative path (reject
  absolute); the two-tier models are `extra="forbid"`.
- **Vault-only artifacts (unguarded, synthetic report):** the full remediation checklist
  + packet JSON/MD write ONLY under `output/remediation/` / `output/review-packet/`; the
  packet JSON carries no `ev_` (dropped by the allowlist); the checklist JSON keeps `ev_`
  (vault-only).
- **Unstageable subtrees (unguarded):** `output/remediation/` and `output/review-packet/`
  are in `scripts/check_publish_safe.py` `VAULT_SUBTREES`, and `scan_vault_artifact`
  flags a `.json`/`.md` under either subtree — so a stray tracked artifact is caught.
  `scripts/check_publish_safe.py main()` over the real tree returns 0 violations.
- **Non-vault / fail-closed (unguarded):** `paths.resolve_within(vault.root, subtree,
  "../../escape")` raises `PathEscapeError`; `vault remediate` / `review-packet` with no
  completed audit → `invalid_input`/exit 2, zero artifacts; `vault audit` on a bad `--db`
  refuses via the Phase-36 index preflight; a `rendered_leak` refuses before any packet write.

## SAFE-07 — grounding / determinism / static volatile (test_conformance_v41_grounding.py)

- **Retrieve-what-you-cite (unguarded, real registry):** every `build_remediation` and
  `build_packet` citation `(citation_id, quote)` pair exists in a real
  `crs_rules.load_registry()` citation.
- **Deterministic (unguarded):** `build_remediation` and `build_packet` twice → identical
  `model_dump()`.
- **Static volatile-rule + no-second-trust-path (unguarded):**
  `crs_rules.no_inlined_volatile_rules([remediation.py, review_packet.py]) == []`; an AST
  import walk proves neither module imports `searchindex` / `grounding`; a call-level
  guard proves `build_remediation` never calls the trust path.
- **Screening framing (unguarded):** every rendered remediation/packet artifact carries
  `audit_report.SCREENING_NOTICE` and no affirmative approval/eligibility/outcome claim in
  the body.

## SAFE-08 — single release gate (extend run_conformance.py + test_conformance_v41_release_gate.py)

- Extend `scripts/run_conformance.py` `_GLOB` to `test_conformance_v4[01]_*.py` so ONE
  command runs the complete v4.0 + v4.1 conformance flow; update `_SAFE_CRITERIA`/banner to
  SAFE-01..08. The v4.0 release-gate self-test uses its OWN `test_conformance_v40_*.py`
  glob + `--collect-only`, so it stays green (the runner now collects a superset).
- Add `test_conformance_v41_release_gate.py` (marker + `--collect-only`) asserting the one
  command collects the three v4.1 modules and that each carries the `conformance` marker —
  proving the single gate exercises coverage / refusal / remediation / packet / privacy /
  grounding / screening for the complete v4.1 flow.

## Frozen constraints
- Zero new runtime dependency (stdlib + pytest already present).
- No new domain behaviour; no re-ground/re-score; no second trust path.
- Skip-guarded real-seam tests are structural-only on a fresh clone (corpus git-ignored).
- Publish-safe tracked tree stays clean; every conformance module carries the marker.
