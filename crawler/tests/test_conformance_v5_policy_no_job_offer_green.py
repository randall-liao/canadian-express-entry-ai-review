"""v5 POLICY negative-control conformance — NO ``additional.job_offer`` path greens.

Phase 42 (42-04, POLICY-01 / POLICY-02 / POLICY-03; threat register T-42-01..T-42-06).

The phase's highest-stakes regression is a legacy / physician arranged-employment
input silently auto-**greening** into a ``SUBSTANTIATED`` verdict or a non-zero CRS
additional-points award. This module is the exhaustive negative control that proves
it can NEVER happen: it sweeps EVERY outcome the three shipped surfaces can produce
over a synthetic registry (current + legacy + physician rows) and asserts, for every
case, that the verdict is NOT ``SUBSTANTIATED`` and the award is ``in (None, 0)`` /
``crs_points == 0``:

  * :func:`crawler.auditors.additional.decide_job_offer` — the real decider, swept
    across missing / unconfirmed / stale / malformed / non-physician / legacy /
    post-repeal / physician / no-ITA / zero-claim inputs and both window edges
    (``TestNoJobOfferPathGreens``);
  * :func:`crawler.crs_audit.arranged_employment_guard` — the sole frozen award
    chokepoint, swept across a non-zero claim on the legacy edge (2024-06-01) and
    post-repeal (2026-01-01) plus the zero-claim N/A path (``TestGuardNeverGreens``);
  * :func:`crawler.policy_offer.offer_for_program_eligibility` — the inert sidecar,
    swept across ``claim_points ∈ {0, 200, 999}`` and both window edges
    (``TestSidecarNeverGreens``).

Plus a byte-identity assertion that the shipped guard ``crawler/crs_audit.py`` is
frozen byte-for-byte vs ``HEAD`` (``git diff --quiet``), skip-guarded off a git
checkout (``TestFrozenGuardByteIdentity``) — proving the frozen guard drifted zero
this phase.

Grounding note: every volatile literal (the ``2023-04-25`` physician date and the
``31100/31101/31102`` NOC set) lives ONLY in the synthetic-registry FIXTURES reused
from ``test_physician_policy.py`` — never inlined into the production surfaces (that
is proven separately by ``TestNoInlinedRules`` scanning ``ad.__file__`` /
``policy_offer.__file__``). This module drives the REAL production functions over
those fixtures; it inlines no production policy value of its own.

Naming (no Phase-45/46 wiring): the ``v5`` prefix is intentional. The v4.x
release-gate runner glob is ``crawler/tests/test_conformance_v4[01]_*.py``
(``scripts/run_conformance.py``), so this file is deliberately NOT captured by the
v4.x gate this phase — Phase 46 introduces the v5 glob. It still runs inside the
full ``crawler/tests`` suite. ``scripts/run_conformance.py`` is NOT touched.

Stdlib ``unittest`` ONLY — NO network, NO vault. Run from the repo root::

    .venv/bin/python -m pytest \
        crawler/tests/test_conformance_v5_policy_no_job_offer_green.py -q
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import pytest

from crawler import crs_audit, policy_offer
from crawler.auditors import additional as ad
from crawler.models.crs_rules import Registry

# Reuse the proven synthetic-registry + by_field builders (current + legacy +
# physician rows) rather than re-declaring the volatile fixtures here — the same
# cross-test-helper reuse pattern test_conformance_v41_coverage.py applies to
# test_auditors_additional.py. Importing helper functions does NOT re-collect the
# donor module's TestCase classes.
from crawler.tests.test_physician_policy import (
    _PHYS_NOCS,
    _ctx,
    _offer_factor,
    _physician_row,
    _registry,
    _val,
)

# Marker-tagged like the sibling conformance modules (the marker is registered in
# pyproject). This does NOT enrol the file into the v4.x release gate, which selects
# by the file glob `test_conformance_v4[01]_*.py`, not by the marker.
pytestmark = pytest.mark.conformance

# --------------------------------------------------------------------------- #
# Repo-root-anchored coordinates + window edges (all test fixtures only).
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FROZEN_GUARD_REL = "crawler/crs_audit.py"

# Grounded window edges the sweep drives (fixture dates only — the production
# surfaces read their real windows from the grounded registry rows):
_LEGACY_EDGE = "2024-06-01"     # inside the legacy window (< 2025-03-25 repeal)
_POST_REPEAL = "2026-01-01"     # after the 2025-03-25 repeal (current policy: 0)
_PHYS_WINDOW = "2023-06-01"     # after the physician effective_from, physician-only
_NON_PHYSICIAN_NOC = "21234"    # a NOC NOT in the physician accepted-set

# The verdict/points invariant every job-offer outcome must satisfy.
_FORBIDDEN_VERDICT = "SUBSTANTIATED"
_ALLOWED_POINTS = (None, 0)


def _git_root() -> Path | None:
    """The git work-tree root, or ``None`` when this is not a git checkout.

    Copied from ``test_dli_conformance.py`` so the frozen-guard byte-identity
    proof skips cleanly (never fails) on a fresh export / non-git tree.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return Path(out.stdout.strip())


_GIT_ROOT = _git_root()


# --------------------------------------------------------------------------- #
# The exhaustive decider sweep (POLICY-01/02/03 — no path greens).
# --------------------------------------------------------------------------- #
class TestNoJobOfferPathGreens(unittest.TestCase):
    """Every ``decide_job_offer`` outcome is AT-RISK/N/A — never SUBSTANTIATED.

    Drives the REAL ``additional.decide_job_offer`` over an exhaustive input matrix
    (missing / unconfirmed / stale / malformed / non-physician / legacy /
    post-repeal / physician / no-ITA / zero-claim) and both window edges, asserting
    for EVERY case ``verdict != "SUBSTANTIATED"`` AND
    ``substantiated_points in (None, 0)`` — no truthy award on any path or window
    edge (threat T-42-01 / T-42-03).
    """

    def _cases(self):
        """(label, by_field, factor, ita_date, registry) tuples for the sweep."""
        phys_by = {"noc_code": _val("noc_code", _PHYS_NOCS[0])}
        nonphys_by = {"noc_code": _val("noc_code", _NON_PHYSICIAN_NOC)}
        cases = [
            # (a) physician NOC in the physician-only window → physician branch.
            ("physician_noc_physician_window", phys_by, _offer_factor(),
             _PHYS_WINDOW, None),
            # (b) physician NOC inside the OVERLAPPING legacy window → branch order.
            ("physician_noc_legacy_window", phys_by, _offer_factor(),
             _LEGACY_EDGE, None),
            # (c) non-physician NOC in the legacy window → guard legacy manual.
            ("nonphysician_noc_legacy_window", nonphys_by, _offer_factor(),
             _LEGACY_EDGE, None),
            # (d) non-physician NOC post-repeal → guard current (0).
            ("nonphysician_noc_post_repeal", nonphys_by, _offer_factor(),
             _POST_REPEAL, None),
            # (e) missing noc_code (physician branch cannot fire) → guard legacy.
            ("missing_noc_legacy_window", {}, _offer_factor(), _LEGACY_EDGE, None),
            # (e') missing noc_code post-repeal → guard current (0).
            ("missing_noc_post_repeal", {}, _offer_factor(), _POST_REPEAL, None),
            # (f) physician NOC but no ITA date → window unevaluable → current (0).
            ("physician_noc_no_ita_date", phys_by, _offer_factor(), None, None),
            # (g) zero / unclaimed offer → N/A (no claim path), even w/ physician NOC.
            ("zero_claim_with_physician_noc", phys_by, _offer_factor(0),
             _LEGACY_EDGE, None),
            ("zero_claim_no_noc", {}, _offer_factor(0), _POST_REPEAL, None),
            # malformed grounded physician window → fail-closed → guard legacy.
            ("malformed_physician_window", phys_by, _offer_factor(), _LEGACY_EDGE,
             _registry(physician_eff_from="not-a-real-date")),
        ]
        # Sweep EVERY physician NOC in the accepted set across both windows so no
        # single member of the set can slip a green through.
        for noc in _PHYS_NOCS:
            by = {"noc_code": _val("noc_code", noc)}
            cases.append((f"physician_noc_{noc}_physician_window", by,
                          _offer_factor(), _PHYS_WINDOW, None))
            cases.append((f"physician_noc_{noc}_legacy_window", by,
                          _offer_factor(), _LEGACY_EDGE, None))
            cases.append((f"physician_noc_{noc}_post_repeal", by,
                          _offer_factor(), _POST_REPEAL, None))
        return cases

    def test_no_decider_outcome_is_substantiated_or_nonzero(self) -> None:
        for label, by_field, factor, ita_date, registry in self._cases():
            with self.subTest(case=label):
                res = ad.decide_job_offer(_ctx(
                    by_field=by_field, factor=factor, ita_date=ita_date,
                    registry=registry))
                # Never green.
                self.assertNotEqual(
                    res.verdict, _FORBIDDEN_VERDICT,
                    f"{label}: decider returned SUBSTANTIATED")
                # Never a truthy / non-None award on any path or window edge.
                self.assertIn(
                    res.substantiated_points, _ALLOWED_POINTS,
                    f"{label}: substantiated_points={res.substantiated_points!r} "
                    "is not in (None, 0)")
                self.assertFalse(
                    bool(res.substantiated_points),
                    f"{label}: substantiated_points is truthy "
                    f"({res.substantiated_points!r})")
                # The verdict is always one of the safe outcomes.
                self.assertIn(
                    res.verdict, ("AT-RISK", "N/A"),
                    f"{label}: unexpected verdict {res.verdict!r}")


# --------------------------------------------------------------------------- #
# The frozen award chokepoint sweep — the guard never greens.
# --------------------------------------------------------------------------- #
class TestGuardNeverGreens(unittest.TestCase):
    """``crs_audit.arranged_employment_guard`` never SUBSTANTIATED / never non-zero.

    A non-zero claim across the legacy edge (2024-06-01) and post-repeal
    (2026-01-01) returns ``status != "SUBSTANTIATED"`` and ``points in (None, 0)``;
    a zero claim returns ``status == "N/A"`` / ``points == 0`` (threat T-42-01).
    """

    def test_non_zero_claim_never_green_across_window_edges(self) -> None:
        reg = _registry()
        for ita_date in (_LEGACY_EDGE, _POST_REPEAL):
            for claim_points in (1, 50, 200, 600, 100_000):
                with self.subTest(ita=ita_date, claim=claim_points):
                    guard = crs_audit.arranged_employment_guard(
                        claim_points, ita_date, reg)
                    self.assertNotEqual(
                        guard["status"], _FORBIDDEN_VERDICT,
                        f"guard SUBSTANTIATED at ita={ita_date}, claim={claim_points}")
                    self.assertIn(
                        guard["points"], _ALLOWED_POINTS,
                        f"guard points={guard['points']!r} not in (None, 0)")
                    self.assertFalse(
                        bool(guard["points"]),
                        f"guard points is truthy ({guard['points']!r})")
                    self.assertEqual(guard["status"], "AT-RISK")

    def test_zero_claim_is_na_zero(self) -> None:
        reg = _registry()
        for ita_date in (_LEGACY_EDGE, _POST_REPEAL, None):
            with self.subTest(ita=ita_date):
                guard = crs_audit.arranged_employment_guard(0, ita_date, reg)
                self.assertEqual(guard["status"], "N/A")
                self.assertEqual(guard["points"], 0)
                self.assertNotEqual(guard["status"], _FORBIDDEN_VERDICT)


# --------------------------------------------------------------------------- #
# The inert sidecar sweep — constant 0, never SUBSTANTIATED.
# --------------------------------------------------------------------------- #
class TestSidecarNeverGreens(unittest.TestCase):
    """``policy_offer.offer_for_program_eligibility`` is constant-0 / never green.

    For ``claim_points ∈ {0, 200, 999}`` across both window edges the sidecar
    returns ``crs_points == 0`` and ``eligibility_status != "SUBSTANTIATED"``
    (AT-RISK when a claim is present, N/A when absent) — threat T-42-04.
    """

    def test_sidecar_crs_points_zero_never_substantiated_all_inputs(self) -> None:
        reg = _registry()
        for ita_date in (_LEGACY_EDGE, _POST_REPEAL):
            for claim_points in (0, 200, 999):
                with self.subTest(ita=ita_date, claim=claim_points):
                    d = policy_offer.offer_for_program_eligibility(
                        claim_points, ita_date, reg)
                    self.assertEqual(
                        d["crs_points"], 0,
                        f"sidecar crs_points non-zero for claim={claim_points}")
                    self.assertNotEqual(
                        d["eligibility_status"], _FORBIDDEN_VERDICT,
                        f"sidecar SUBSTANTIATED for claim={claim_points}")
                    self.assertIn(
                        d["eligibility_status"], ("AT-RISK", "N/A"),
                        f"sidecar unexpected status {d['eligibility_status']!r}")
                    self.assertEqual(
                        d["eligibility_status"],
                        "AT-RISK" if claim_points else "N/A")

    def test_sidecar_never_green_even_with_no_current_row(self) -> None:
        # A registry carrying ONLY the physician row (no current row to reuse a
        # citation from) still returns a constant 0 and never greens — the inert
        # contract does not depend on the grounded citation being present.
        reg = Registry(rows=[_physician_row()])
        for claim_points in (0, 200, 999):
            with self.subTest(claim=claim_points):
                d = policy_offer.offer_for_program_eligibility(
                    claim_points, _POST_REPEAL, reg)
                self.assertEqual(d["crs_points"], 0)
                self.assertNotEqual(d["eligibility_status"], _FORBIDDEN_VERDICT)


# --------------------------------------------------------------------------- #
# The shipped guard stays byte-for-byte frozen (threat T-42-06).
# --------------------------------------------------------------------------- #
@unittest.skipUnless(
    _GIT_ROOT is not None,
    "not a git checkout — the frozen-guard byte-identity diff proof did NOT run",
)
class TestFrozenGuardByteIdentity(unittest.TestCase):
    """``crawler/crs_audit.py`` is byte-for-byte identical to HEAD.

    Copies ``test_dli_conformance.py::TestFrozenContractsUnchanged``'s
    ``git diff --quiet HEAD`` byte-identity pattern, scoped to the frozen guard, so
    a green run proves the sole CRS-additional-points award chokepoint drifted ZERO
    this phase. Skips cleanly outside a git checkout (structural-only on a fresh
    export).
    """

    def test_frozen_guard_unchanged_vs_head(self) -> None:
        assert _GIT_ROOT is not None  # for type-checkers; guarded by skipUnless
        guard_path = _GIT_ROOT / _FROZEN_GUARD_REL
        self.assertTrue(
            guard_path.is_file(),
            f"frozen guard file missing: {_FROZEN_GUARD_REL}")
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", _FROZEN_GUARD_REL],
            cwd=_GIT_ROOT,
        )
        self.assertEqual(
            result.returncode,
            0,
            "crawler/crs_audit.py changed vs HEAD — the frozen arranged-employment "
            "guard MUST stay byte-for-byte identical this phase")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
