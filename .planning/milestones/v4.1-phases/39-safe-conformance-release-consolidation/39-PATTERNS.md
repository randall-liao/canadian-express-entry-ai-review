# Phase 39 — Pattern Map: SAFE Conformance & Release Consolidation

**Mapped:** 2026-07-17

## New / changed source

| New or changed | Closest analog | What to mirror |
|---|---|---|
| `crawler/tests/test_conformance_v41_coverage.py` | `test_conformance_v40_no_false_green.py` | `pytestmark = pytest.mark.conformance`; full-grid × blocking-state matrix; skip-guard real seam |
| `crawler/tests/test_conformance_v41_privacy.py` | `test_conformance_v40_privacy_containment.py` | PII-light stdout + vault-only + publish-safe main() 0 violations + non-vault refusal |
| `crawler/tests/test_conformance_v41_grounding.py` | `test_conformance_v40_retrieve_what_you_cite.py` + `test_remediation_projection.py` + `test_review_packet_conformance.py` | retrieve-what-you-cite + determinism + no-inlined + AST no-import + screening framing |
| `crawler/tests/test_conformance_v41_release_gate.py` | `test_conformance_v40_release_gate.py` | runner glob + `--collect-only` + conformance marker assertions |
| `scripts/run_conformance.py` (extended glob + banner) | itself | `_GLOB` → `test_conformance_v4[01]_*.py`; `_SAFE_CRITERIA` → SAFE-01..08 |

## New tests / entry points

| Artifact | Pattern |
|---|---|
| Four `test_conformance_v41_*.py` modules | each carries the `conformance` marker; unguarded structural checks + skip-guarded real-seam checks |
| `scripts/run_conformance.py` | ONE command runs the complete v4.0 + v4.1 conformance flow; `--collect-only` enumerates without executing |

## Anti-patterns explicitly avoided
- No new runtime behaviour / dependency; no re-ground/re-score/second trust path.
- No breaking the v4.0 release-gate self-test (extend the glob to a superset).
- No conformance module without the `conformance` marker.
- No unguarded real-seam test (skip-guard on the git-ignored corpus + deps).
