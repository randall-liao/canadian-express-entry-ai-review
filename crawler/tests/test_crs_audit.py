"""Golden-fixture tests for the deterministic CRS logic (Phase 31 — Plan 04).

Every threshold / cap / validity window / conversion / policy date the module
reads is supplied via SYNTHETIC grounded RuleRow objects built in-test, so the
arithmetic is exercised WITHOUT depending on exact corpus quotes (and the module
under test carries NO inlined volatile literal — a self-scan test asserts that).
"""

from __future__ import annotations

import unittest

from crawler import crs_audit
from crawler.models.crs_rules import (
    Citation,
    AcceptedValue,
    MachineCheck,
    PointsEntry,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)

_CIT = Citation(chunk_id="guidance/crs-criteria.md#000", quote="x")


def _row(rule_id, group, check_type, mc, factor_ids=None, **vol):
    return RuleRow(
        rule_id=rule_id,
        factor_group=group,
        factor_ids=factor_ids or [rule_id],
        check_type=check_type,
        query="q",
        selector=Selector(family="guidance"),
        claim_text="synthetic grounded rule",
        citations=[_CIT],
        machine_check=mc,
        volatility=VolatilityMeta(
            volatility=vol.get("volatility", "volatile"),
            source_family="guidance",
            effective_from=vol.get("effective_from"),
            effective_to=vol.get("effective_to"),
        ),
        gap=vol.get("gap", False),
    )


def _conversion_registry() -> Registry:
    # IELTS reading: CLB 9 band [7.0, 8.0], CLB 8 band [6.5, 6.9]  (boundary at 7.0)
    conv = _row(
        "core.language.conversion.ielts",
        "core_human_capital",
        "conversion",
        MachineCheck(
            kind="conversion",
            field="clb",
            points_by_level=[
                PointsEntry(test_type="IELTS General Training", ability="reading",
                            level=9, min_score=7.0, max_score=8.0, citation_index=0),
                PointsEntry(test_type="IELTS General Training", ability="reading",
                            level=8, min_score=6.5, max_score=6.9, citation_index=0),
            ],
        ),
        factor_ids=["core.language.conversion"],
    )
    return Registry(rows=[conv])


def _validity_registry() -> Registry:
    lang = _row(
        "core.language.first.validity",
        "core_human_capital",
        "threshold",
        MachineCheck(kind="validity_window", field="test_date", window_days=730),
    )
    eca = _row(
        "core.education.eca_validity",
        "core_human_capital",
        "threshold",
        MachineCheck(kind="validity_window", field="eca_report_date", window_days=1825),
    )
    return Registry(rows=[lang, eca])


def _work_registry() -> Registry:
    hours = _row(
        "core.work.hours",
        "core_human_capital",
        "threshold",
        MachineCheck(kind="threshold", field="hours_per_week", max_value=30),
    )
    window = _row(
        "core.work.window",
        "core_human_capital",
        "threshold",
        MachineCheck(kind="validity_window", field="work_reference_period", window_days=3650),
    )
    teer = _row(
        "core.work.definition",
        "core_human_capital",
        "admissibility",
        MachineCheck(kind="accepted_enum", field="teer",
                     accepted_values=[
                         AcceptedValue(value="0"), AcceptedValue(value="1"),
                         AcceptedValue(value="2"), AcceptedValue(value="3"),
                     ]),
    )
    return Registry(rows=[hours, window, teer])


class TestToClb(unittest.TestCase):
    def test_boundary_maps_to_9_and_one_below_maps_to_8(self) -> None:
        reg = _conversion_registry()
        self.assertEqual(crs_audit.to_clb("IELTS General Training", "reading", 7.0, reg), 9)
        self.assertEqual(crs_audit.to_clb("IELTS General Training", "reading", 6.9, reg), 8)

    def test_unknown_test_or_out_of_table_returns_none(self) -> None:
        reg = _conversion_registry()
        self.assertIsNone(crs_audit.to_clb("UNKNOWN", "reading", 7.0, reg))
        self.assertIsNone(crs_audit.to_clb("IELTS General Training", "reading", 3.0, reg))
        self.assertIsNone(crs_audit.to_clb("IELTS General Training", "speaking", 7.0, reg))


class TestAgeOnDate(unittest.TestCase):
    def test_age_on_ita_date(self) -> None:
        self.assertEqual(crs_audit.age_on_date("1994-06-01", "2026-07-06"), 32)

    def test_birthday_after_ita_does_not_lower_age(self) -> None:
        # DOB Dec 31; ITA in July -> birthday later in the year does NOT raise the count.
        self.assertEqual(crs_audit.age_on_date("1994-12-31", "2026-07-06"), 31)

    def test_birthday_on_ita_date_counts(self) -> None:
        self.assertEqual(crs_audit.age_on_date("1994-07-06", "2026-07-06"), 32)


class TestWithinValidity(unittest.TestCase):
    def test_language_in_window_and_expired(self) -> None:
        reg = _validity_registry()
        self.assertTrue(crs_audit.within_validity("language", "2025-07-06", "2026-07-06", reg))
        self.assertFalse(crs_audit.within_validity("language", "2024-01-01", "2026-07-06", reg))

    def test_eca_in_window_and_expired(self) -> None:
        reg = _validity_registry()
        self.assertTrue(crs_audit.within_validity("eca", "2023-01-01", "2026-07-06", reg))
        self.assertFalse(crs_audit.within_validity("eca", "2019-01-01", "2026-07-06", reg))


class TestAggregateWork(unittest.TestCase):
    def test_over_30h_week_does_not_over_count(self) -> None:
        reg = _work_registry()
        # 50h/week for 12 months is still ONE full-time year (capped at 30h equivalent).
        periods = [{"start": "2024-01-01", "end": "2024-12-31", "hours_per_week": 50, "teer": "1"}]
        result = crs_audit.aggregate_work(periods, reg)
        self.assertAlmostEqual(result["years"], 1.0, places=1)

    def test_overlapping_periods_not_double_counted(self) -> None:
        reg = _work_registry()
        periods = [
            {"start": "2024-01-01", "end": "2024-12-31", "hours_per_week": 30, "teer": "1"},
            {"start": "2024-07-01", "end": "2025-06-30", "hours_per_week": 30, "teer": "1"},
        ]
        result = crs_audit.aggregate_work(periods, reg)
        # 2024-01-01 .. 2025-06-30 is ~18 months, NOT 24 (the 6-month overlap is merged).
        self.assertLess(result["months"], 20)
        self.assertGreater(result["months"], 16)

    def test_ineligible_teer_excluded(self) -> None:
        reg = _work_registry()
        periods = [{"start": "2024-01-01", "end": "2024-12-31", "hours_per_week": 30, "teer": "5"}]
        result = crs_audit.aggregate_work(periods, reg)
        self.assertEqual(result["months"], 0)


def _spouse_mode_registry() -> Registry:
    core = _row(
        "core.language.first.points",
        "core_human_capital",
        "points",
        MachineCheck(kind="points_table", field="clb_per_ability",
                     points_by_level=[PointsEntry(level=9, points=31, citation_index=0)]),
        factor_ids=["language"],
    )
    spouse = _row(
        "spouse.language",
        "spouse_common_law",
        "points",
        MachineCheck(kind="points_table", field="clb_per_ability",
                     points_by_level=[PointsEntry(level=9, points=5, citation_index=0)]),
        factor_ids=["language"],
    )
    spouse_cap = _row(
        "spouse.language.cap",
        "spouse_common_law",
        "cap",
        MachineCheck(kind="cap", field="spouse_language_section", cap_value=20),
        factor_ids=["language"],
    )
    return Registry(rows=[core, spouse, spouse_cap])


def _caps_registry() -> Registry:
    edu = _row("transfer.cap.education", "skill_transferability", "cap",
               MachineCheck(kind="cap", field="education_combination", cap_value=50))
    fw = _row("transfer.cap.foreign_work", "skill_transferability", "cap",
              MachineCheck(kind="cap", field="foreign_work_combination", cap_value=50))
    total = _row("transfer.cap.total", "skill_transferability", "cap",
                 MachineCheck(kind="cap", field="skill_transferability_total", cap_value=100))
    return Registry(rows=[edu, fw, total])


def _labelled_core_language_registry() -> Registry:
    """Mirror the REAL core.yaml encoding: labelled with/without-spouse columns
    INSIDE one owning core row (NOT a separate spouse group), plus a DECOY
    transferability row that lists a core factor only as a later component."""
    first = _row(
        "core.language.first.points",
        "core_human_capital",
        "points",
        MachineCheck(kind="points_table", field="clb_per_ability",
                     points_by_level=[
                         PointsEntry(label="clb9_with_spouse", level=9, points=29,
                                     citation_index=0),
                         PointsEntry(label="clb9_without_spouse", level=9, points=31,
                                     citation_index=0),
                     ]),
        factor_ids=["core.language.first"],
    )
    second = _row(
        "core.language.second.points",
        "core_human_capital",
        "points",
        MachineCheck(kind="points_table", field="clb_per_ability",
                     points_by_level=[
                         PointsEntry(label="clb9_or_more_without_spouse", level=9,
                                     points=6, citation_index=0),
                     ]),
        factor_ids=["core.language.second"],
    )
    # DECOY: a transferability row that OWNS transfer.foreign_language but lists
    # core.language.first only as a later component — its tier points must NEVER
    # leak into core.language.first's own lookup (factor_ids[0] ownership guard).
    decoy = _row(
        "transfer.foreign_language.tier",
        "skill_transferability",
        "points",
        MachineCheck(kind="points_table", field="foreign_language_tier",
                     points_by_level=[PointsEntry(level=9, points=50,
                                                  citation_index=0)]),
        factor_ids=["transfer.foreign_language", "core.language.first"],
    )
    return Registry(rows=[first, second, decoy])


class TestSpouseMode(unittest.TestCase):
    def test_spouse_vs_no_spouse_diverge(self) -> None:
        reg = _spouse_mode_registry()
        self.assertEqual(crs_audit.score_factor("language", 9, False, reg), 31)
        self.assertEqual(crs_audit.score_factor("language", 9, True, reg), 5)

    def test_unknown_value_returns_none(self) -> None:
        reg = _spouse_mode_registry()
        self.assertIsNone(crs_audit.score_factor("language", 3, False, reg))

    def test_core_language_first_selects_with_spouse_column(self) -> None:
        reg = _labelled_core_language_registry()
        self.assertEqual(
            crs_audit.score_factor("core.language.first", 9, True, reg), 29)
        self.assertEqual(
            crs_audit.score_factor("core.language.first", 9, False, reg), 31)

    def test_core_language_second_falls_back_to_grounded_in_both_modes(self) -> None:
        reg = _labelled_core_language_registry()
        self.assertEqual(
            crs_audit.score_factor("core.language.second", 9, True, reg), 6)
        self.assertEqual(
            crs_audit.score_factor("core.language.second", 9, False, reg), 6)

    def test_transferability_component_does_not_leak_into_core_language(self) -> None:
        reg = _labelled_core_language_registry()
        # The owning core value (29 / 31) — NEVER the decoy transfer tier (50).
        self.assertEqual(
            crs_audit.score_factor("core.language.first", 9, True, reg), 29)
        self.assertEqual(
            crs_audit.score_factor("core.language.first", 9, False, reg), 31)

    def test_unmatched_level_still_none_with_labelled_rows(self) -> None:
        reg = _labelled_core_language_registry()
        self.assertIsNone(
            crs_audit.score_factor("core.language.first", 4, False, reg))


class TestScoreFactorRealRegistry(unittest.TestCase):
    """Task 1 (33-07): score_factor picks the mode column by grounded LABEL over
    the REAL public registry (``default_registry`` — YAML-only, no corpus).

    A principal CORE language factor encodes both the with-spouse and no-spouse
    columns as labelled ``PointsEntry`` rows INSIDE one owning ``core_human_capital``
    row (``clb9_with_spouse`` / ``clb9_without_spouse``), so spouse mode must NOT
    drop the core row — it must select the with-spouse label.
    """

    def test_core_language_first_selects_with_spouse_in_spouse_mode(self) -> None:
        reg = crs_audit.default_registry()
        self.assertEqual(
            crs_audit.score_factor("core.language.first", 9, True, reg), 29)

    def test_core_language_first_selects_without_spouse_no_spouse(self) -> None:
        reg = crs_audit.default_registry()
        self.assertEqual(
            crs_audit.score_factor("core.language.first", 9, False, reg), 31)

    def test_core_language_second_grounded_in_both_modes(self) -> None:
        reg = crs_audit.default_registry()
        # Only a ``*_without_spouse`` entry exists -> it is the grounded fallback
        # in BOTH modes (never None in spouse mode).
        self.assertEqual(
            crs_audit.score_factor("core.language.second", 9, True, reg), 6)
        self.assertEqual(
            crs_audit.score_factor("core.language.second", 9, False, reg), 6)

    def test_unmatched_level_returns_none_over_real_registry(self) -> None:
        reg = crs_audit.default_registry()
        # COV-01 (35-01) grounded every conversion-emitted first-language band
        # {3..10}, so a genuinely UNMATCHED level is now one OUTSIDE that set
        # (e.g. CLB 11, above the grounded ceiling). score_factor still returns
        # None — never a guessed award — for a level no grounded row prices.
        self.assertIsNone(
            crs_audit.score_factor("core.language.first", 11, False, reg))


class TestTransferabilityCaps(unittest.TestCase):
    def test_subcaps_and_total_clamp(self) -> None:
        reg = _caps_registry()
        out = crs_audit.apply_transferability_caps(
            {"education_combination": 60, "foreign_work_combination": 60}, reg
        )
        self.assertEqual(out["education_combination"], 50)
        self.assertEqual(out["foreign_work_combination"], 50)
        self.assertEqual(out["total"], 100)

    def test_under_cap_not_clamped(self) -> None:
        reg = _caps_registry()
        out = crs_audit.apply_transferability_caps(
            {"education_combination": 40, "foreign_work_combination": 30}, reg
        )
        self.assertEqual(out["education_combination"], 40)
        self.assertEqual(out["foreign_work_combination"], 30)
        self.assertEqual(out["total"], 70)


class TestCompareToCutoff(unittest.TestCase):
    def test_meets_and_misses(self) -> None:
        reg = _caps_registry()
        above = crs_audit.compare_to_cutoff(500, 480, reg)
        self.assertEqual(above["delta"], 20)
        self.assertTrue(above["meets_cutoff"])
        below = crs_audit.compare_to_cutoff(450, {"cutoff": 480}, reg)
        self.assertEqual(below["delta"], -30)
        self.assertFalse(below["meets_cutoff"])


class TestSelfNoInlineScan(unittest.TestCase):
    def test_crs_audit_has_no_inlined_volatile_rule(self) -> None:
        from crawler import crs_rules
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules(["crawler/crs_audit.py"]), []
        )


def _job_offer_registry(with_legacy=True, legacy_gap=False) -> Registry:
    current = _row(
        "additional.job_offer.current",
        "additional_points",
        "policy",
        MachineCheck(kind="policy_flag", field="job_offer_additional_points",
                     flag_value=False, effective_from="2025-03-25"),
        factor_ids=["additional.job_offer"],
        effective_from="2025-03-25",
    )
    rows = [current]
    if with_legacy:
        legacy = _row(
            "additional.job_offer.legacy",
            "additional_points",
            "policy",
            MachineCheck(kind="points_table", field="job_offer_legacy",
                         points_by_level=[PointsEntry(level="Major Group 00",
                                                      points=200, citation_index=0)]),
            factor_ids=["additional.job_offer"],
            effective_to="2025-03-25",
            gap=legacy_gap,
        )
        rows.append(legacy)
    return Registry(rows=rows)


class TestArrangedEmploymentGuard(unittest.TestCase):
    def test_current_era_nonzero_claim_is_at_risk_zero(self) -> None:
        reg = _job_offer_registry()
        v = crs_audit.arranged_employment_guard(200, "2025-06-01", reg)
        self.assertEqual(v["status"], "AT-RISK")
        self.assertEqual(v["points"], 0)
        self.assertEqual(v["citation"], "guidance/crs-criteria.md#000")

    def test_missing_or_gap_legacy_fails_closed_even_pre_repeal(self) -> None:
        no_legacy = crs_audit.arranged_employment_guard(50, "2024-06-01", _job_offer_registry(with_legacy=False))
        self.assertEqual((no_legacy["status"], no_legacy["points"]), ("AT-RISK", 0))
        gap_legacy = crs_audit.arranged_employment_guard(50, "2024-06-01", _job_offer_registry(legacy_gap=True))
        self.assertEqual((gap_legacy["status"], gap_legacy["points"]), ("AT-RISK", 0))

    def test_grounded_legacy_in_window_is_at_risk_manual_not_green(self) -> None:
        reg = _job_offer_registry()
        v = crs_audit.arranged_employment_guard(200, "2024-06-01", reg)
        self.assertEqual(v["status"], "AT-RISK")
        self.assertIsNone(v["points"])  # left for manual legacy resolution, NOT auto-award
        self.assertNotEqual(v["points"], 200)

    def test_zero_or_unclaimed_is_na(self) -> None:
        reg = _job_offer_registry()
        self.assertEqual(crs_audit.arranged_employment_guard(0, "2025-06-01", reg)["status"], "N/A")
        self.assertEqual(crs_audit.arranged_employment_guard(None, "2025-06-01", reg)["status"], "N/A")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
