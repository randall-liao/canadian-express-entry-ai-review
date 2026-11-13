---
phase: 41
slug: dli-pgwp-pinned-snapshot-family-refresh-generator
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-18
---

# Phase 41 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x running the repository's unittest-style tests |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest crawler/tests/test_dli_snapshot.py crawler/tests/test_dli_refresh_cli.py crawler/tests/test_dli_grounding.py -x -q` |
| **Full suite command** | `.venv/bin/python -m pytest crawler/tests -q` (~19 min; 988 passed / 2 skipped at sign-off) |
| **Publish-safe gate** | `.venv/bin/python scripts/check_publish_safe.py` |
| **v4.x conformance gate** | `.venv/bin/python scripts/run_conformance.py` |
| **Estimated runtime** | <120 s targeted; ~15 min full suite |

---

## Sampling Rate

- **After every task commit:** run the requirement-specific command in the map below.
- **After every plan wave:** run the quick command plus the existing index/grounding/freshness regressions named by the plan.
- **Before verification:** full suite green + publish-safe (0 violations) + v4.x conformance PASS.
- **Max feedback latency:** <120 seconds for targeted checks.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 41-01-01 | 01 | 1 | STUDY-01 | T-41-01 / T-41-02 | Fixed-host fetch and strict closed-schema parsing reject empty, truncated, missing/extra-field, malformed-DLI, control-character, and invalid-PGWP payloads without partial output | unit | `.venv/bin/python -m pytest crawler/tests/test_dli_snapshot.py -x -q -k "schema or fetch or malformed or empty or control"` | ✅ | ✅ green |
| 41-01-02 | 01 | 1 | STUDY-01 | T-41-03 / T-41-04 | Normalization is deterministic by DLI number; atomic family replacement preserves per-campus tri-state PGWP, NFC, provenance, hashes, deletions, and current-only markers | unit | `.venv/bin/python -m pytest crawler/tests/test_dli_snapshot.py -x -q` | ✅ | ✅ green |
| 41-02-01 | 02 | 2 | STUDY-01 | T-41-02 / T-41-03 / T-41-05 | Top-level `--json refresh-dli` uses only the fixed IRCC endpoint and fixed `corpus/dli/` output; envelope is PII-free; fetch/schema failures return `invalid_input`/exit 2 without replacing a healthy family | CLI integration | `.venv/bin/python -m pytest crawler/tests/test_dli_refresh_cli.py -x -q` | ✅ | ✅ green |
| 41-02-02 | 02 | 2 | STUDY-01 | T-41-02 / T-41-05 | Parser exposes no arbitrary URL/input/output flags; offline CLI tests patch `fetch` and preserve a healthy prior family on failure | CLI/static | `.venv/bin/python -m pytest crawler/tests/test_dli_refresh_cli.py -x -q` | ✅ | ✅ green |
| 41-03-01 | 03 | 2 | STUDY-01 | T-41-01 / T-41-06 | Curated fixture and committable golden family cover every verified upstream landmine and regenerate byte-identically | fixture regression | `.venv/bin/python -m pytest crawler/tests/test_dli_grounding.py -x -q -k "golden or byte or fixture"` | ✅ | ✅ green |
| 41-03-02 | 03 | 2 | STUDY-01 | T-41-04 / T-41-06 | Unchanged indexer discovers the golden family, and the one marked `study.dli.designation` row resolves and grounds a verbatim current-status span; no self-grounded max-age row exists | integration + grounding | `.venv/bin/python -m pytest crawler/tests/test_dli_grounding.py -x -q` | ✅ | ✅ green |
| 41-04-01 | 04 | 3 | STUDY-01 | T-41-02 / T-41-05 / T-41-06 | Complete phase preserves zero dependencies, no audit-path network, no inlined/fabricated freshness bound, current-only framing, publish safety, and frozen Phase 40/index contracts | static + regression | `.venv/bin/python -m pytest crawler/tests/test_dli_conformance.py -q` | ✅ | ✅ green |
| 41-04-02 | 04 | 3 | STUDY-01 | T-41-01 / T-41-04 / T-41-07 | Real refresh and reindex produce 1,136 DLI docs, 2,272 indexed chunks, and a whole-registry grounded `study.dli.designation` row; full suite and release gates pass | live integration + release | `.venv/bin/python -m pytest crawler/tests -q` | ✅ | ✅ green |

---

## Wave 0 Requirements

The new fixture and test files are created by their owning implementation tasks:

- [x] `crawler/tests/fixtures/dli/dli-sample.json` — curated official-payload subset covering every verified landmine.
- [x] `crawler/tests/fixtures/dli/golden/dli/*.md` and `manifest.json` — committable golden generated snapshot family.
- [x] `crawler/tests/test_dli_snapshot.py` — schema, normalization, provenance, hash, atomicity, idempotence, and current-only tests.
- [x] `crawler/tests/test_dli_refresh_cli.py` — fixed-endpoint/fixed-output CLI envelope and refusal tests.
- [x] `crawler/tests/test_dli_grounding.py` — unchanged-indexer discovery and grounded-current-status row tests.
- [x] `crawler/tests/test_dli_conformance.py` — phase static, real-index grounding, and frozen-contract release checks.

No framework or dependency installation is required.

---

## Manual-Only Verifications

All required phase behaviors have network-free automated verification. The optional
live endpoint contract test is skip-guarded by `PR_LIVE_DLI` and is not required for
CI or phase completion.

---

## Validation Sign-Off

- [x] Every planned task has an automated command or Wave 0 dependency.
- [x] Sampling continuity has no three consecutive tasks without automated verification.
- [x] Wave 0 covers every missing fixture/test reference.
- [x] Commands contain no watch-mode flags.
- [x] Targeted feedback latency is under 120 seconds.
- [x] `nyquist_compliant: true` is set in frontmatter.

**Approval:** complete 2026-07-19
