---
phase: 39-safe-conformance-release-consolidation
reviewed: 2026-07-17T14:55:27Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - crawler/tests/test_conformance_v41_coverage.py
  - crawler/tests/test_conformance_v41_privacy.py
  - crawler/tests/test_conformance_v41_grounding.py
  - crawler/tests/test_conformance_v41_release_gate.py
  - scripts/run_conformance.py
  - pyproject.toml
findings:
  critical: 0
  warning: 0
  info: 4
  total: 4
status: clean
---

# Phase 39: Code Review Report

**Reviewed:** 2026-07-17T14:55:27Z
**Depth:** deep (cross-file: gate runner ↔ 4 new conformance modules ↔ production seams)
**Files Reviewed:** 6 (4 new tests + gate runner + pyproject)
**Status:** clean — **0 Critical, 0 Warning**

## Summary

Phase 39 consolidates the v4.1 SAFE conformance layer (SAFE-05 coverage/no-false-green,
SAFE-06 remediation/packet privacy, SAFE-07 grounding/determinism/screening, SAFE-08
single release-gate command) and widens the one authoritative gate runner to discover both
v4.0 and v4.1 modules via the file glob `test_conformance_v4[01]_*.py`.

The change set is **test-only + the gate glob + a pyproject marker string** — I confirmed
with `git diff 53febbf..HEAD --name-only` that **no production trust-path module changed**.
I ran the full gate (`.venv/bin/python scripts/run_conformance.py` → **75 passed**, PASS
SAFE-01..08) and the two release-gate self-tests
(`test_conformance_v40_release_gate.py` + `test_conformance_v41_release_gate.py` → **8
passed**). I then read every assertion against its production seam to confirm each one is
**non-vacuous** and would actually fail if the underlying invariant regressed.

I adopted a FORCE stance and specifically hunted for: a glob that silently drops or
over-includes modules, vacuous/empty-loop assertions, false-green assertions that pass
even when the invariant breaks, skip guards that mask real-seam checks, and any privacy or
subprocess-injection regression in the runner. **I found no Critical or Warning defects.**
The four INFO items below are optional hardening notes, not bugs — the invariants they
touch are all still protected by a companion assertion.

### Verification performed (evidence)

- **Glob correctness (SCRUTINIZE #1).** `crawler/tests/*conformance*.py` resolved on disk:
  `test_conformance_v4[01]_*.py` matches exactly the **9** intended modules (5 × v40 + 4 ×
  v41) and correctly **excludes** the three unrelated suites (`test_crs_rules_conformance`,
  `test_extraction_conformance`, `test_review_packet_conformance`). The new glob is a strict
  **superset** of the old `test_conformance_v40_*.py` (no v4.0 coverage dropped). `[01]` is a
  single-char class, so it will NOT accidentally pull a future `v42_*` module.
- **v4.0 self-test still green.** `test_conformance_v40_release_gate.py` globs with its OWN
  literal `test_conformance_v40_*.py` and invokes the runner via `--collect-only`; the runner
  now collecting v40+v41 is a superset, so both its on-disk check and its collect assertion
  still pass. Confirmed by the 8-passed run.
- **No recursion / no fork-bomb.** The full gate executes both release-gate modules, each of
  which spawns `run_conformance.py --collect-only`; `--collect-only` only imports (never
  executes) the suite, and the runner sets `PR_CONFORMANCE_RUNNER=1` only on real runs. Whole
  gate finishes in ~28s.
- **Non-vacuous assertions (SCRUTINIZE #2).**
  - Coverage: `PricedOrExplicitlyUnresolved` proves the conversion-emitted level set is
    non-empty (`test_conversion_levels_non_empty`) AND that `crs_audit.score_factor(...)` is
    non-`None` for every emitted CLB band in both spouse modes — `score_factor` returns `None`
    only when no grounded row covers the value, and `assertIsNotNone(0)` is True, so a grounded
    0 passes while an *unpriced* factor (None) fails. `test_unpriced_substantiated_is_surfaced`
    drives `to_public_envelope` on a SUBSTANTIATED card with `substantiated_points=None` and
    asserts `counts["unpriced"] >= 1` — bites on the real down-projection seam.
  - Sibling no-false-green: `test_confirmed_adult_chain_substantiates` proves the green path
    *can* go green, so the 6 blocking states (missing field / non-accepted relationship /
    non-accepted status / unresolvable DOB / clear minor / no ITA date) that assert
    `!= SUBSTANTIATED` are genuinely exercised, not a dead branch.
  - Adversarial real seam: `AdversarialNoFalseGreenRealSeam` **ran** (not skipped) in this
    environment (corpus/index.db + extraction deps present) and passed; its `skipUnless` guard
    degrades to a clearly-labelled STRUCTURAL-ONLY skip on a fresh clone.
  - Privacy: `test_tracked_tree_scans_clean` calls `check_publish_safe.main()` over the whole
    tracked tree (real bite); `test_full_artifacts_are_vault_only` proves the checklist JSON
    keeps `ev_` while the packet JSON drops it; `_seed()` stamps
    `registry_fingerprint=crs_rules.registry_fingerprint(...)` so the drift gate in
    `remediation._build_checklist_for_run` matches and does not fail-closed on the happy path.
    The rendered-leak test monkeypatches the module-global `remediation.build_remediation`,
    which `_build_checklist_for_run` calls by name, so the injected abs-path shape genuinely
    reaches the render-then-scan gate → `rendered_leak`, zero artifacts.
  - Grounding: screening-framing check strips the `SCREENING_NOTICE` block and the
    "grounded rule" / "authoritative rule" citation lines (where verbatim corpus quotes live)
    before scanning tool-synthesized body text for affirmative claims — correct, because both
    renderers emit each quote on the same line as those markers; the action/reason lines are
    NOT stripped, so a tool-synthesized affirmative claim would still be caught.
- **No duplicate test execution (SCRUTINIZE #5).** `test_conformance_v41_coverage.py` imports
  only `_SIBLING_ITA` (str), `_ctx` / `_sibling_fields` (functions) and
  `_conversion_emitted_levels` (function) from sibling test modules — **no `TestCase`
  subclass** is imported, so pytest does not re-collect/re-run those classes here.
- **No security regression (SCRUTINIZE #6).** The runner builds `cmd` as a list and calls
  `subprocess.run(cmd, ...)` (no `shell=True`); module paths come from an on-disk glob, and
  passthrough args are forwarded verbatim to pytest — no injection surface. No production code
  changed.

All reviewed files meet quality standards for correctness, security, and privacy. The four
notes below are optional maintainability/robustness hardening only.

## Info

### IN-01: Release-gate "glob matches" test re-hardcodes the runner glob instead of importing `_GLOB`

**File:** `crawler/tests/test_conformance_v41_release_gate.py:46`
**Issue:** `test_runner_glob_matches_v40_and_v41_modules` globs the tests dir with a *duplicated
literal* `test_conformance_v4[01]_*.py` rather than importing `run_conformance._GLOB`. If the
runner's real `_GLOB` regressed (e.g. reverted to `v40`), this test would still pass because it
never reads the runner's actual pattern. The regression IS still caught by
`test_one_command_collects_the_complete_v41_flow` (which invokes the real runner via
`--collect-only` and asserts each v4.1 module + the v4.0 sentinel appear), so there is no
false-green at the module level — but the method's own stated purpose ("runner glob matches")
is only indirectly true. The same pattern pre-exists in `test_conformance_v40_release_gate.py:49`.
**Fix:** Source the pattern from the runner so the two cannot drift:
```python
import importlib.util, sys
spec = importlib.util.spec_from_file_location("run_conformance", _RUNNER)
rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)
globbed = {p.name for p in _TESTS_DIR.glob(Path(rc._GLOB).name)}
```

### IN-02: Gate banner `_SAFE_CRITERIA` names 8 modules while the glob executes 9

**File:** `scripts/run_conformance.py:40`
**Issue:** `_SAFE_CRITERIA` enumerates SAFE-01..08 (8 modules) for the pass/fail banner, but the
authoritative selection is the glob, which matches 9 modules — the extra one being
`test_conformance_v40_release_gate.py` (the legacy self-check, deliberately not a SAFE criterion).
This mirrors the pre-existing v4.0 design (banner named 4, glob ran 5) and is transparent because
the runner also prints the full resolved module list. Not a correctness defect, but the banner
implies the criteria list is the run set when it is not.
**Fix:** Optional — add a one-line comment at `_SAFE_CRITERIA` noting the release-gate self-check
module is intentionally unnamed, or derive the banner count from `conformance_modules()` minus the
self-check module so the two stay reconciled.

### IN-03: `scan_vault_artifact` assertion passes via the `candidates` namespace rule, not the subtree rule it purports to exercise

**File:** `crawler/tests/test_conformance_v41_privacy.py:147-150`
**Issue:** `test_both_subtrees_are_unstageable` asserts
`scan_vault_artifact("personal/candidates/x/output/remediation/rem_x.json")` is truthy, but that
path already trips `check_publish_safe` rule (a) — the `candidates` path segment — so the call
would return a violation even if `output/remediation/` were removed from `VAULT_SUBTREES`. The
subtree-scoping invariant is still protected by the companion
`assertIn("output/remediation/", cps.VAULT_SUBTREES)` on the same test, so there is no false-green;
the scan assertion is just weaker than its name implies.
**Fix:** To make the scan call specifically exercise the subtree rule (c), use a path with no
`candidates` segment, e.g. `scan_vault_artifact("misc/output/remediation/rem_x.json")` (still trips
via the `output/remediation/` subtree + `.json` extension), keeping the `candidates`-segment path as
a separate defense-in-depth assertion.

### IN-04: Screening-framing filter drops whole citation lines (coarser than stripping exact quotes)

**File:** `crawler/tests/test_conformance_v41_grounding.py:141-147`
**Issue:** The affirmative-claim scan excludes any body line containing "grounded rule" or
"authoritative rule". For today's fixed renderers this is exactly right — every verbatim corpus
quote (which may legitimately contain e.g. "approved") is emitted on such a line, and all
tool-synthesized action/reason lines are retained and scanned. The residual risk is only latent: a
future renderer change that placed tool text on a citation line could mask an affirmative claim.
**Fix:** Optional hardening — strip the exact registry quote strings
(`{c.quote for row in registry.rows for c in row.citations}`) from the body instead of dropping
whole marker lines, so the affirmative-claim scan remains total over all tool-synthesized text
regardless of layout.

---

_Reviewed: 2026-07-17T14:55:27Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
