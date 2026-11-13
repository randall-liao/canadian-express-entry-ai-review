"""First-official-language pricing completeness + grounding pin (35-01, COV-01).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Loads the REAL registry
(``crawler.data.crs_rules``) and — where it needs grounding — grounds against the
REAL ``corpus/index.db`` (the anti-fabrication guard; SKIPPED on a fresh clone).

Proves COV-01 is closed and stays closed:
  * completeness — EVERY first-official-language benchmark that the supported
    test-conversion tables actually emit prices in BOTH the spouse and no-spouse
    modes. The expected level set is derived LIVE from the loaded conversion rows
    (never a hard-coded numeric interval), so a future conversion band with no
    matching grounded point row fails loudly instead of silently pricing 0
    (Pitfall 1: a ``None``-points ``SUBSTANTIATED`` card contributes 0);
  * anti-drift — the priced first-language level set is pinned set-equal to the
    conversion-emitted level set, so the two can never diverge silently again;
  * grounding — the one ``core.language.first.points`` row grounds against the
    real corpus with zero violations (no fabricated quote fills the gap).

The completeness class FAILS RED against the current registry (only CLB 9 priced)
and turns GREEN once the CLB 3-8,10 grounded rows land.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from crawler import crs_audit, crs_rules

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"

# The first-official-language points row under test. Its grounded per-ability
# points must cover every benchmark the conversion tables can emit.
_FIRST_LANGUAGE_FACTOR = "core.language.first"
_FIRST_LANGUAGE_POINTS_RULE = "core.language.first.points"


def _conversion_emitted_levels(registry) -> set[int]:
    """The set of CLB levels the LIVE non-gap conversion rows can emit.

    Derived at runtime from the loaded registry — NOT a hard-coded numeric
    interval (Pitfall 2: PTE Core emits CLB 3, so a naive 4..10 interval would
    miss it). Resolves to ``{3, 4, 5, 6, 7, 8, 9, 10}`` against the shipped corpus.
    """
    return {
        int(entry.level)
        for row in registry.rows
        if row.machine_check.kind == "conversion" and not row.gap
        for entry in (row.machine_check.points_by_level or [])
    }


def _priced_first_language_levels(registry) -> set[int]:
    """The set of CLB levels the ``core.language.first.points`` row actually prices."""
    return {
        int(entry.level)
        for row in registry.rows
        if row.factor_ids
        and row.factor_ids[0] == _FIRST_LANGUAGE_FACTOR
        and row.machine_check.kind == "points_table"
        for entry in (row.machine_check.points_by_level or [])
    }


class TestFirstLanguagePricingCompleteness(unittest.TestCase):
    """Every conversion-emitted benchmark prices in both modes (no corpus needed)."""

    def setUp(self) -> None:
        self.reg = crs_rules.load_registry()
        self.levels = _conversion_emitted_levels(self.reg)

    def test_conversion_levels_are_derived_not_empty(self) -> None:
        # Guard the guard: if the live conversion rows vanished, the pin below
        # would vacuously pass. Prove we are actually measuring emitted bands.
        self.assertTrue(
            self.levels,
            "no conversion-emitted levels found — the completeness pin would be vacuous")

    def test_every_emitted_level_prices_in_both_modes(self) -> None:
        for lvl in sorted(self.levels):
            for spouse_mode in (False, True):
                points = crs_audit.score_factor(
                    _FIRST_LANGUAGE_FACTOR, lvl, spouse_mode, self.reg)
                self.assertIsNotNone(
                    points,
                    f"first-official-language points UNPRICED at CLB {lvl} "
                    f"(spouse_mode={spouse_mode}) — score_factor returned None; a "
                    f"conversion-emitted benchmark silently contributes 0")

    def test_priced_set_equals_conversion_emitted_set(self) -> None:
        # Anti-drift: the priced level set must be EXACTLY the conversion-emitted
        # set. A new conversion band with no matching point row (under-pricing) OR
        # a stray point row for a level no conversion emits (over-reach) both fail.
        priced = _priced_first_language_levels(self.reg)
        self.assertEqual(
            priced, self.levels,
            f"priced first-language levels {sorted(priced)} != conversion-emitted "
            f"levels {sorted(self.levels)} (drift between pricing and conversion)")


@unittest.skipUnless(
    _REAL_DB.is_file(),  # skipUnless(_REAL_DB.is_file(), ...) — grounding gate
    "LOCAL-ONLY GROUNDING GATE: corpus/index.db is git-ignored and absent — the "
    "first-language pricing grounding proof did NOT run; a green suite here is "
    "STRUCTURAL ONLY",
)
class TestFirstLanguagePricingGrounding(unittest.TestCase):
    """The extended points row grounds against the real corpus (zero violations)."""

    def test_first_language_points_row_grounds(self) -> None:
        reg = crs_rules.load_registry()
        only = crs_rules.Registry(rows=[
            r for r in reg.rows if r.rule_id == _FIRST_LANGUAGE_POINTS_RULE])
        self.assertEqual(
            len(only.rows), 1,
            f"expected exactly one {_FIRST_LANGUAGE_POINTS_RULE} row")
        result = crs_rules.validate_registry(only, _REAL_DB)
        self.assertEqual(result["violations"], [], result["violations"])
        self.assertEqual(result["grounded"], result["total"])
        self.assertEqual(result["total"], 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
