# Phase 39: SAFE Conformance & Release Consolidation - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via `workflow.skip_discuss`)

<domain>
## Phase Boundary

Consolidate the v4.1 safety guarantees into an authoritative, clearly-labelled
conformance layer and a SINGLE release-gate command that proves the complete v4.1 flow
holds every frozen invariant. This phase adds NO new runtime behaviour or dependency —
it strengthens coverage and packages it behind one command, exactly as the v4.0
`test_conformance_v40_*` layer + `scripts/run_conformance.py` did.

Three seams:

1. **Coverage / no-false-green consolidation (SAFE-05).** An authoritative
   `test_conformance_v41_coverage.py` proving every supported first-official-language
   benchmark the conversion tables emit is priced OR explicitly unresolved (never a
   silent gap), and that no sibling extraction state (minor / ambiguous / stale /
   missing / cross-factor) and no adversarial extraction state (rotated / low-text /
   password-protected / ambiguous-date) can produce a false-green (`SUBSTANTIATED`)
   verdict through the real seam.

2. **Remediation / packet privacy consolidation (SAFE-06).** An authoritative
   `test_conformance_v41_privacy.py` proving remediation and packet DEFAULTS leak no
   PII, raw document bytes, absolute paths, or `ev_` ids on stdout / in a tracked
   artifact; both new output subtrees (`output/remediation/`, `output/review-packet/`)
   are in the publish-safe allow-list (unstageable); and non-vault writes / missing
   prerequisites fail closed with zero artifacts.

3. **Grounding / determinism / screening + single release gate (SAFE-07, SAFE-08).**
   An authoritative `test_conformance_v41_grounding.py` proving every requirement-bearing
   remediation/packet line is retrieve-what-you-cite (its citation+quote is a real
   grounded registry row), deterministic, screening-framed, and carries no inlined
   volatile rule / second trust path. And a SINGLE release-gate command
   (`scripts/run_conformance.py` extended to the complete v4.x flow) + a
   `test_conformance_v41_release_gate.py` proving the one command exercises coverage,
   refusal, remediation, packet, privacy, grounding, and screening-framing checks.

Do NOT add new runtime behaviour, re-ground/re-score, or a runtime dependency; the
conformance layer only STRENGTHENS coverage and consolidates the release gate.

</domain>

<decisions>
## Implementation Decisions

### Locked Decisions

- Mirror the v4.0 conformance pattern EXACTLY: `crawler/tests/test_conformance_v41_*.py`
  modules, each carrying `pytestmark = pytest.mark.conformance`, selected by a
  marker-independent file glob, run under one `scripts/run_conformance.py` command.
- Extend `run_conformance.py` to run BOTH `test_conformance_v40_*.py` AND
  `test_conformance_v41_*.py` (the complete v4.x flow) without breaking the v4.0
  release-gate self-test; update the SAFE-criteria banner to SAFE-01..08.
- Conformance modules exercise the REAL seams (registry / extraction / audit /
  remediation / packet), skip-guarded on the git-ignored `corpus/index.db` + extraction
  deps exactly like the existing real-seam tests; the pure/structural checks run
  unguarded.
- The v4.1 conformance layer REUSES the already-proven Phase-35..38 assertions
  (language pricing completeness, sibling/adversarial no-false-green, remediation/packet
  privacy + retrieve-what-you-cite + no-inlined + render-then-scan) and consolidates
  them authoritatively — no new trust path.
- Zero new runtime dependencies; publish-safe tracked tree stays clean.

### Agent Discretion

All remaining implementation choices are at the agent's discretion. Prefer the existing
v4.0 conformance module + release-gate patterns. Add no runtime dependency.

</decisions>

<code_context>
## Existing Code Insights

- `scripts/run_conformance.py` globs `test_conformance_v40_*.py`, exports
  `PR_CONFORMANCE_RUNNER=1`, supports `--collect-only`, exits with pytest's rc — the
  single-gate pattern to extend to `test_conformance_v4[01]_*.py`.
- `crawler/tests/test_conformance_v40_release_gate.py` asserts the gate collects the
  four v4.0 SAFE modules (using its OWN `test_conformance_v40_*.py` glob) + the
  `conformance` marker — extending the runner glob to also match v41 keeps it green.
- The v4.1 forward-guard tests already exist and can be reused/consolidated:
  Phase-35 language pricing (`test_language_points_coverage.py`), sibling no-false-green
  (`test_auditors_additional.py`, `test_full_audit_real_seam.py`); Phase-36 adversarial
  quarantine (`test_adversarial_extraction_seam.py`), index-refusal
  (`test_audit_index_refusal.py`); Phase-37 remediation projection/privacy
  (`test_remediation_projection.py`, `test_remediation_cli.py`); Phase-38 packet
  firewall/privacy (`test_review_packet_conformance.py`, `test_review_packet_cli.py`).
- `crawler/crs_audit.score_factor`, `auditors.FULL_GRID_FACTORS`, `crs_rules.load_registry`
  / `no_inlined_volatile_rules` / `registry_fingerprint`, `remediation.build_remediation`,
  `review_packet.build_packet` / `_scan_rendered_bytes` are the seams to assert against.
- `scripts/check_publish_safe.py::VAULT_SUBTREES` includes `output/crs-audit/`,
  `output/remediation/`, `output/review-packet/`.

</code_context>

<specifics>
## Specific Ideas

- The single release-gate command is the SAFE-08 deliverable; it must exercise the
  complete v4.1 flow (coverage / refusal / remediation / packet / privacy / grounding /
  screening) in one invocation.
- Each conformance module is a durable, authoritative contract, not a smoke test.

</specifics>

<deferred>
## Deferred Ideas

No new domain behaviour. Encrypted packets (LATER-07), recipient presets (LATER-06),
and semantic entailment (VAL-02) remain out of scope.

</deferred>
