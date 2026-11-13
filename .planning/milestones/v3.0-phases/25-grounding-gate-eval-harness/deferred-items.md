# Deferred Items — Phase 25 (Grounding Gate + Eval Harness)

Out-of-scope discoveries logged during execution. NOT fixed (SCOPE BOUNDARY:
only auto-fix issues directly caused by the current task's changes).

## Pre-existing test failure (real-corpus dependent) — logged in Plan 25-01

- **Test:** `crawler/tests/test_dupaudit.py::TestRealCorpus::test_audit_runs_clean_with_expected_counts`
- **Symptom:** `AssertionError: 0 not greater than or equal to 1` at
  `test_dupaudit.py:548` — `self.assertGreaterEqual(result.exact, 1)`.
- **Status:** PRE-EXISTING on a clean tree (reproduced before any 25-01 change was
  made — see baseline run prior to creating `crawler/grounding.py`).
- **Cause:** This test runs `dupaudit.audit(Path("corpus"))` against the REAL,
  git-ignored `corpus/` and asserts at least one exact-duplicate signal. The
  current real corpus apparently contains zero exact duplicates, so the assertion
  fails. It is wholly unrelated to the grounding gate (Plan 25-01 touches only
  `crawler/grounding.py` + `crawler/tests/test_grounding.py`).
- **Disposition:** Deferred — outside the scope of Plan 25-01. Whoever owns the
  dupaudit real-corpus invariant should decide whether the assertion or the
  corpus expectation needs updating.
