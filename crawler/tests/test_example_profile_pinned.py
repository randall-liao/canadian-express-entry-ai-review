"""Pin the shipped synthetic example CRS profile to the live factor grid (HARD-03).

Two guarantees:
1. (UNGUARDED) every ``factor_id`` in personal.example/crs-profile.example.yaml is a
   canonical dotted id on ``auditors.FULL_GRID_FACTORS`` and its ``factor_group``
   matches ``auditors.FACTOR_GROUP`` — an anti-drift pin so the shipped example can
   never silently drift off the grid and demonstrate nothing (all-``N/A``).
2. (SKIP-GUARDED on the git-ignored corpus/index.db) loading the example and running
   the REAL audit path yields >= 1 applicable non-``N/A`` verdict for a claimed
   core factor — proving the example illustrates a real audited factor, not N/A.

Stdlib ``unittest`` ONLY.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from crawler import auditors

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE = _REPO_ROOT / "personal.example" / "crs-profile.example.yaml"
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"


def _load_example_factors() -> list[dict]:
    data = yaml.safe_load(_EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and isinstance(data.get("factors"), list)
    return data["factors"]


class ExampleProfileGridPin(unittest.TestCase):
    def test_every_factor_id_is_on_the_canonical_grid(self) -> None:
        grid = set(auditors.FULL_GRID_FACTORS)
        for entry in _load_example_factors():
            fid = entry["factor_id"]
            self.assertIn(
                fid, grid,
                f"example factor_id {fid!r} is not a canonical grid id "
                f"(auditors.FULL_GRID_FACTORS)")

    def test_every_factor_group_matches_the_grid_group(self) -> None:
        for entry in _load_example_factors():
            fid = entry["factor_id"]
            self.assertEqual(
                entry["factor_group"], auditors.FACTOR_GROUP[fid],
                f"example factor_group for {fid!r} disagrees with FACTOR_GROUP")

    def test_example_exercises_a_real_core_factor(self) -> None:
        ids = {e["factor_id"] for e in _load_example_factors()}
        self.assertIn("core.language.first", ids)


class ExampleProfileRealAuditNonNA(unittest.TestCase):
    @unittest.skipUnless(
        _REAL_DB.is_file(),
        "LOCAL-ONLY: corpus/index.db is git-ignored — the real-audit non-N/A proof "
        "did NOT run; a green suite here is STRUCTURAL ONLY",
    )
    def test_example_yields_at_least_one_non_na_claimed_verdict(self) -> None:
        from crawler import audit_report, crs_rules, vault
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        prev = os.environ.get("PR_PERSONAL_DIR")
        os.environ["PR_PERSONAL_DIR"] = tmp.name
        if prev is None:
            self.addCleanup(lambda: os.environ.pop("PR_PERSONAL_DIR", None))
        else:
            self.addCleanup(lambda: os.environ.__setitem__("PR_PERSONAL_DIR", prev))

        candidate = "example-pin"
        v = vault.open_vault(candidate)
        try:
            vault.create_candidate(v, candidate)
            vault.import_profile_yaml(v, candidate, str(_EXAMPLE))
            vault.set_ita_round(
                v, candidate, "example", None, "EE", cutoff_score=None)
            registry = crs_rules.load_registry()
            report, _env = audit_report.run_full_audit_report(
                v, str(_REAL_DB), registry)
        finally:
            v.con.close()

        # A CLAIMED (non-derived, non-spouse) factor should reach an applicable
        # verdict (not N/A). Target the core human-capital factors the example claims.
        claimed_core = {"core.age", "core.education", "core.language.first"}
        non_na = [c for c in report.factor_cards
                  if c.factor_id in claimed_core and c.verdict != "N/A"]
        self.assertTrue(
            non_na,
            "the re-keyed example produced N/A for every claimed core factor — "
            "the example is not pinned to the live grid")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
