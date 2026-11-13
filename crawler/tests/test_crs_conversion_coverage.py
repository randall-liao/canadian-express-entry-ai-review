"""Conversion-table completeness + grounding + to_clb resolution (33-02, AUDIT-01/03).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Loads the REAL registry
(``crawler.data.crs_rules``) and — where it needs grounding — grounds against the
REAL ``corpus/index.db`` (the anti-fabrication guard; SKIPPED on a fresh clone).

Proves the Phase-32-surfaced known item is closed:
  * completeness — every accepted test × four abilities has at least one non-gap
    conversion band (a truthful ``gap:true`` row is allowed; only a SILENT
    omission fails);
  * to_clb resolution — a representative in-band raw score (incl. top + bottom
    band boundaries) resolves to a non-None level; an out-of-table score is None
    (fail-closed);
  * grounding — every non-gap conversion row grounds against the real corpus with
    zero violations (no fabricated quote);
  * SUBSTANTIATED reachability — all four abilities of an accepted test resolve to
    a level, so the conversion layer no longer forces ``unresolved_conversion``.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from crawler import crs_audit, crs_rules

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"

_ACCEPTED_TESTS = (
    "CELPIP-General", "IELTS General Training", "PTE Core",
    "TEF Canada", "TCF Canada",
)
_ABILITIES = ("reading", "writing", "listening", "speaking")


def _conversion_bands(registry):
    """Map (test_type, ability) -> list of non-gap (min, max, level) bands."""
    bands: dict[tuple[str, str], list] = {}
    for row in registry.rows:
        if row.gap or row.machine_check.kind != "conversion":
            continue
        for entry in row.machine_check.points_by_level or []:
            if entry.test_type is None or entry.ability is None:
                continue
            bands.setdefault((entry.test_type, entry.ability), []).append(
                (entry.min_score, entry.max_score, int(entry.level)))
    return bands


class TestConversionCompleteness(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = crs_rules.load_registry()
        self.bands = _conversion_bands(self.reg)

    def test_every_test_and_ability_has_a_band(self) -> None:
        gap_rows = {
            (e.test_type, e.ability)
            for row in self.reg.rows if row.gap and row.machine_check.kind == "conversion"
            for e in (row.machine_check.points_by_level or [])
        }
        for test in _ACCEPTED_TESTS:
            for ability in _ABILITIES:
                present = bool(self.bands.get((test, ability)))
                documented_gap = (test, ability) in gap_rows
                self.assertTrue(
                    present or documented_gap,
                    f"silent omission: no conversion band for {test} / {ability}")

    def test_to_clb_resolves_top_and_bottom_boundaries(self) -> None:
        for (test, ability), bands in self.bands.items():
            bands = sorted(bands)
            lo_min = bands[0][0]
            hi_max = bands[-1][1]
            for boundary in (lo_min, hi_max):
                level = crs_audit.to_clb(test, ability, float(boundary), self.reg)
                self.assertIsNotNone(
                    level, f"{test}/{ability} boundary {boundary} did not resolve")

    def test_out_of_table_score_is_none(self) -> None:
        # A wildly out-of-range score never resolves (fail-closed).
        self.assertIsNone(
            crs_audit.to_clb("IELTS General Training", "reading", -1.0, self.reg))
        self.assertIsNone(
            crs_audit.to_clb("PTE Core", "reading", 1000.0, self.reg))

    def test_bands_do_not_overlap(self) -> None:
        for (test, ability), bands in self.bands.items():
            bands = sorted(bands)
            for i in range(len(bands) - 1):
                self.assertLess(
                    bands[i][1], bands[i + 1][0],
                    f"{test}/{ability} bands overlap: {bands[i]} vs {bands[i + 1]}")

    def test_substantiated_reachable_all_four_abilities_resolve(self) -> None:
        # A fully-satisfying IELTS candidate: all four abilities resolve to a
        # level >= 9, so the conversion layer no longer forces unresolved_conversion.
        raws = {"reading": 7.0, "writing": 7.0, "listening": 8.0, "speaking": 7.0}
        for ability, raw in raws.items():
            level = crs_audit.to_clb("IELTS General Training", ability, raw, self.reg)
            self.assertIsNotNone(level)
            self.assertGreaterEqual(level, 9)


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY GROUNDING GATE: corpus/index.db is git-ignored and absent — the "
    "conversion grounding proof did NOT run; a green suite here is STRUCTURAL ONLY",
)
class TestConversionGrounding(unittest.TestCase):
    def test_every_conversion_row_grounds(self) -> None:
        reg = crs_rules.load_registry()
        conv = crs_rules.Registry(rows=[
            r for r in reg.rows
            if not r.gap and r.machine_check.kind == "conversion"])
        result = crs_rules.validate_registry(conv, _REAL_DB)
        self.assertEqual(result["violations"], [], result["violations"])
        self.assertEqual(result["grounded"], result["total"])
        self.assertGreaterEqual(result["total"], 5)

    def test_retrieve_what_you_cite_agrees(self) -> None:
        reg = crs_rules.load_registry()
        report = crs_rules.retrieve_what_you_cite(reg, _REAL_DB)
        for row in reg.rows:
            if row.gap or row.machine_check.kind != "conversion":
                continue
            with self.subTest(rule_id=row.rule_id):
                self.assertTrue(report[row.rule_id]["agrees_with_citation"])
                self.assertTrue(report[row.rule_id]["grounds"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
