"""Skill-transferability module tests (33-04, AUDIT-01/03, SC5).

Stdlib ``unittest`` ONLY — NO network, NO vault. Drives the combination deciders
DIRECTLY over a SYNTHETIC registry + synthetic ``prior_cards`` (the spine's
contract), so the fan-out dependency + cap behaviour is exercised in isolation.

Proves:
  * both components SUBSTANTIATED + meeting the tier → grounded combination points;
  * a GAP component → combination GAP ``unmet_component`` (never points; SC5);
  * an AT-RISK component → combination AT-RISK;
  * caps — a second same-section combination is clamped to the grounded section
    cap; the grand total is clamped to the grounded total cap;
  * lowering the language benchmark flips the tier downward (live dependency);
  * no inlined volatile rules.
"""

from __future__ import annotations

import unittest

from crawler import crs_rules
from crawler.auditors import DecisionContext
from crawler.auditors import transferability as tr
from crawler.models.audit import PrivateFactorCard
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    PointsEntry,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)

_TINY_ID = "pr-pdi/tiny.md#000"
_TINY_QUOTE = "Permanent residence applicants must provide police certificates"


def _trow(rule_id, factor_ids, mc, check_type="points"):
    return RuleRow(
        rule_id=rule_id, factor_group="skill_transferability", factor_ids=factor_ids,
        check_type=check_type, query="police certificates",
        selector=Selector(family="pr-pdi"),
        claim_text="A grounded transferability rule.",
        citations=[Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
        machine_check=mc,
        volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi"))


def _points(pairs):
    return [PointsEntry(label=f"tier_{lvl}", level=lvl, points=pts)
            for lvl, pts in pairs]


def _registry() -> Registry:
    return Registry(rows=[
        _trow("transfer.education_language",
              ["transfer.education_language", "core.education", "core.language.first"],
              MachineCheck(kind="points_table", field="education_x_language",
                           points_by_level=_points([(7, 25), (9, 50)]))),
        _trow("transfer.education_work",
              ["transfer.education_work", "core.education", "core.work"],
              MachineCheck(kind="points_table", field="education_x_work",
                           points_by_level=_points([("1", 25), ("2+", 50)]))),
        _trow("transfer.foreign_language",
              ["transfer.foreign_language", "core.language.first"],
              MachineCheck(kind="points_table", field="foreign_x_language",
                           points_by_level=_points([(7, 25), (9, 50)]))),
        _trow("transfer.foreign_work",
              ["transfer.foreign_work", "core.work"],
              MachineCheck(kind="points_table", field="foreign_x_work",
                           points_by_level=_points([("1", 25), ("2+", 50)]))),
        _trow("transfer.certificate_language",
              ["transfer.certificate_language", "core.language.first"],
              MachineCheck(kind="points_table", field="certificate_x_language",
                           points_by_level=_points([(5, 25), (7, 50)]))),
        _trow("transfer.cap.education", ["transfer.cap.education"],
              MachineCheck(kind="cap", field="education_combination", cap_value=50),
              check_type="cap"),
        _trow("transfer.cap.foreign_work", ["transfer.cap.foreign_work"],
              MachineCheck(kind="cap", field="foreign_work_combination", cap_value=50),
              check_type="cap"),
        _trow("transfer.cap.total", ["transfer.cap.total"],
              MachineCheck(kind="cap", field="skill_transferability_total",
                           cap_value=100), check_type="cap"),
    ])


def _card(factor_id, verdict, *, clb=None, years=None, points=None):
    confirmed = {}
    if clb is not None:
        confirmed["lowest_benchmark"] = clb
    if years is not None:
        confirmed["aggregated_years"] = years
    return PrivateFactorCard(
        factor_id=factor_id, verdict=verdict, confirmed_value=confirmed,
        substantiated_points=points)


def _consumed(registry, factor_id):
    return Registry(rows=[r for r in registry.rows if factor_id in r.factor_ids])


def _ctx(factor_id, prior_cards, registry=None):
    registry = registry or _registry()
    return DecisionContext(
        factor_id=factor_id, factor=None, by_field={}, registry=registry,
        consumed=_consumed(registry, factor_id), spouse_mode=False,
        reference_date="2025-01-01", prior_cards=prior_cards)


class TestCombinationDependency(unittest.TestCase):
    def test_both_substantiated_awards_tier(self) -> None:
        prior = {
            "core.education": _card("core.education", "SUBSTANTIATED", points=30),
            "core.language.first": _card("core.language.first", "SUBSTANTIATED", clb=9),
        }
        res = tr.decide_education_language(_ctx("transfer.education_language", prior))
        self.assertEqual(res.verdict, "SUBSTANTIATED")
        self.assertEqual(res.substantiated_points, 50)

    def test_gap_component_is_unmet(self) -> None:
        prior = {
            "core.education": _card("core.education", "GAP"),
            "core.language.first": _card("core.language.first", "SUBSTANTIATED", clb=9),
        }
        res = tr.decide_education_language(_ctx("transfer.education_language", prior))
        self.assertEqual(res.verdict, "GAP")
        self.assertEqual(res.reason_code, "unmet_component")
        self.assertIsNone(res.substantiated_points)

    def test_at_risk_component_is_at_risk(self) -> None:
        prior = {
            "core.education": _card("core.education", "SUBSTANTIATED", points=30),
            "core.language.first": _card("core.language.first", "AT-RISK"),
        }
        res = tr.decide_education_language(_ctx("transfer.education_language", prior))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "at_risk_component")

    def test_lowering_language_flips_tier(self) -> None:
        base = {"core.education": _card("core.education", "SUBSTANTIATED", points=30)}
        hi = dict(base, **{"core.language.first":
                           _card("core.language.first", "SUBSTANTIATED", clb=9)})
        lo = dict(base, **{"core.language.first":
                           _card("core.language.first", "SUBSTANTIATED", clb=7)})
        hi_res = tr.decide_education_language(_ctx("transfer.education_language", hi))
        lo_res = tr.decide_education_language(_ctx("transfer.education_language", lo))
        self.assertEqual(hi_res.substantiated_points, 50)
        self.assertEqual(lo_res.substantiated_points, 25)
        # Below the lowest tier -> GAP below_tier.
        below = dict(base, **{"core.language.first":
                              _card("core.language.first", "SUBSTANTIATED", clb=5)})
        below_res = tr.decide_education_language(
            _ctx("transfer.education_language", below))
        self.assertEqual(below_res.verdict, "GAP")
        self.assertEqual(below_res.reason_code, "below_tier")


class TestCaps(unittest.TestCase):
    def test_section_cap_clamps_second_education_combo(self) -> None:
        # education_language already awarded 50 (fills education_combination cap);
        # education_work now clamps to 0.
        prior = {
            "core.education": _card("core.education", "SUBSTANTIATED", points=30),
            "core.work": _card("core.work", "SUBSTANTIATED", years=3.0),
            "transfer.education_language": _card(
                "transfer.education_language", "SUBSTANTIATED", points=50),
        }
        res = tr.decide_education_work(_ctx("transfer.education_work", prior))
        self.assertEqual(res.verdict, "SUBSTANTIATED")
        self.assertEqual(res.substantiated_points, 0)

    def test_total_cap_clamps_across_sections(self) -> None:
        # education section 50 + foreign section 50 = total 100 already; the next
        # foreign combination clamps to 0 (grounded total cap).
        prior = {
            "core.language.first": _card("core.language.first", "SUBSTANTIATED", clb=9),
            "transfer.education_language": _card(
                "transfer.education_language", "SUBSTANTIATED", points=50),
            "transfer.foreign_language": _card(
                "transfer.foreign_language", "SUBSTANTIATED", points=50),
        }
        res = tr.decide_certificate_language(
            _ctx("transfer.certificate_language", prior))
        self.assertEqual(res.substantiated_points, 0)


class TestNoInlinedRules(unittest.TestCase):
    def test_module_has_no_inlined_volatile_rules(self) -> None:
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([tr.__file__]), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
