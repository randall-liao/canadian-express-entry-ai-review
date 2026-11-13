"""Additional-points module tests (33-05, AUDIT-01/03).

Stdlib ``unittest`` ONLY — NO network, NO vault. Drives the deciders DIRECTLY
over a SYNTHETIC registry + synthetic ``ExtractedValue`` by_field, so the job-offer
guard, nomination verification, and French thresholds are exercised in isolation.

Proves:
  * a non-zero job-offer claim → AT-RISK / 0 (current policy), NEVER SUBSTANTIATED;
  * an in-window grounded legacy row → AT-RISK / None (manual), still not green;
  * a zero / unclaimed job-offer → N/A;
  * a verified nomination → SUBSTANTIATED grounded points; expired → AT-RISK;
    missing → GAP;
  * strong French below the grounded NCLC threshold → GAP; a satisfying one →
    SUBSTANTIATED with grounded French points;
  * no inlined volatile rules.
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from crawler import crs_rules
from crawler.auditors import DecisionContext
from crawler.auditors import additional as ad
from crawler.models.crs_rules import (
    AcceptedValue,
    Citation,
    MachineCheck,
    PointsEntry,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor, ExtractedValue

_TINY_ID = "pr-pdi/tiny.md#000"
_TINY_QUOTE = "Permanent residence applicants must provide police certificates"
_ABIL = ("reading", "writing", "listening", "speaking")


def _arow(rule_id, mc, *, factor_ids=None, check_type="points", eff_from=None,
          eff_to=None, gap=False, group="additional_points"):
    return RuleRow(
        rule_id=rule_id, factor_group=group,
        factor_ids=factor_ids or ["additional." + rule_id.split(".")[1]],
        check_type=check_type, query="police certificates",
        selector=Selector(family="pr-pdi"),
        claim_text="A grounded additional rule.",
        citations=[Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
        machine_check=mc,
        volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi",
                                  effective_from=eff_from, effective_to=eff_to),
        gap=gap)


def _tef_conversion():
    entries = []
    for ability in _ABIL:
        entries.append(PointsEntry(test_type="TEF Canada", ability=ability,
                                   level=9, min_score=503, max_score=545))
        entries.append(PointsEntry(test_type="TEF Canada", ability=ability,
                                   level=7, min_score=434, max_score=461))
    return entries


def _registry() -> Registry:
    return Registry(rows=[
        _arow("additional.nomination",
              MachineCheck(kind="points_table", field="nomination",
                           points_by_level=[PointsEntry(
                               label="valid_nomination", level="nomination",
                               points=600)]),
              factor_ids=["additional.nomination"]),
        _arow("additional.job_offer.current",
              MachineCheck(kind="policy_flag", field="job_offer_additional_points",
                           flag_value=False, effective_from="2025-03-25"),
              factor_ids=["additional.job_offer"], check_type="policy",
              eff_from="2025-03-25"),
        _arow("additional.job_offer.legacy",
              MachineCheck(kind="points_table", field="job_offer_legacy",
                           points_by_level=[PointsEntry(
                               label="major_group_00", level="Major Group 00",
                               points=200)]),
              factor_ids=["additional.job_offer"], check_type="policy",
              eff_from="2010-01-01", eff_to="2025-03-25"),
        _arow("additional.study",
              MachineCheck(kind="points_table", field="canadian_study",
                           points_by_level=[
                               PointsEntry(label="one_or_two", level="1-2", points=15),
                               PointsEntry(label="three_plus", level="3+", points=30)]),
              factor_ids=["additional.study"]),
        _arow("additional.french",
              MachineCheck(kind="points_table", field="strong_french",
                           points_by_level=[
                               PointsEntry(label="french_only", level="french_only",
                                           points=25),
                               PointsEntry(label="french_plus_english",
                                           level="french_plus_english", points=50)]),
              factor_ids=["additional.french"]),
        _arow("additional.sibling",
              MachineCheck(kind="points_table", field="sibling",
                           points_by_level=[PointsEntry(
                               label="sibling", level="sibling", points=15)]),
              factor_ids=["additional.sibling"]),
        _arow("additional.sibling.adult",
              MachineCheck(kind="threshold", field="sibling_min_age",
                           min_value=18),
              factor_ids=["additional.sibling"], check_type="threshold"),
        _arow("core.language.first.accepted_tests",
              MachineCheck(kind="accepted_enum", field="test_type",
                           accepted_values=[AcceptedValue(value="TEF Canada")]),
              factor_ids=["core.language.first"], check_type="admissibility",
              group="core_human_capital"),
        _arow("core.language.first.validity",
              MachineCheck(kind="validity_window", field="test_date",
                           window_days=730),
              factor_ids=["core.language.first"], check_type="threshold",
              group="core_human_capital"),
        _arow("core.language.conversion.tef",
              MachineCheck(kind="conversion", field="clb",
                           points_by_level=_tef_conversion()),
              factor_ids=["core.language.conversion"], check_type="conversion",
              group="core_human_capital"),
    ])


def _val(field, value):
    return ExtractedValue(
        value_id="val_" + field, document_id="doc_x", field_name=field,
        raw_text=str(value), normalized_value=value, extraction_run_id="run_x",
        confirmation_status="confirmed", quality_flag="ok")


def _ctx(factor_id, *, by_field=None, factor=None, ita_date=None,
         reference_date=None):
    reference_date = reference_date or date.today().isoformat()
    reg = _registry()
    return DecisionContext(
        factor_id=factor_id, factor=factor, by_field=by_field or {},
        registry=reg, consumed=Registry(rows=[]), spouse_mode=False,
        reference_date=reference_date, ita_date=ita_date)


def _french_fields(level_raw):
    fields = {"test_type": _val("test_type", "TEF Canada"),
              "test_date": _val("test_date",
                                (date.today() - timedelta(days=30)).isoformat())}
    for ability in _ABIL:
        fields[f"raw_score_{ability}"] = _val(f"raw_score_{ability}", level_raw)
    return fields


class TestJobOfferTrap(unittest.TestCase):
    def test_non_zero_claim_is_at_risk_zero_current(self) -> None:
        factor = CrsProfileFactor(
            factor_id="additional.job_offer", factor_group="additional_points",
            claimed_points=200, claimed_value=200)
        # ITA after the repeal -> current policy path.
        res = ad.decide_job_offer(
            _ctx("additional.job_offer", factor=factor, ita_date="2026-01-01"))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "arranged_employment_current")
        self.assertEqual(res.substantiated_points, 0)
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    def test_in_window_legacy_is_at_risk_manual(self) -> None:
        factor = CrsProfileFactor(
            factor_id="additional.job_offer", factor_group="additional_points",
            claimed_points=200, claimed_value=200)
        # ITA inside the grounded legacy window -> manual (points None), not green.
        res = ad.decide_job_offer(
            _ctx("additional.job_offer", factor=factor, ita_date="2024-06-01"))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "arranged_employment_legacy_manual")
        self.assertIsNone(res.substantiated_points)
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    def test_zero_claim_is_na(self) -> None:
        factor = CrsProfileFactor(
            factor_id="additional.job_offer", factor_group="additional_points",
            claimed_points=0, claimed_value=0)
        res = ad.decide_job_offer(
            _ctx("additional.job_offer", factor=factor, ita_date="2024-06-01"))
        self.assertEqual(res.verdict, "N/A")


class TestNomination(unittest.TestCase):
    def test_verified_nomination_substantiated(self) -> None:
        by = {"nomination_stream": _val("nomination_stream", "OINP-Tech"),
              "expiry_date": _val("expiry_date", "2099-01-01")}
        res = ad.decide_nomination(_ctx("additional.nomination", by_field=by))
        self.assertEqual(res.verdict, "SUBSTANTIATED")
        self.assertEqual(res.substantiated_points, 600)

    def test_expired_nomination_at_risk(self) -> None:
        by = {"nomination_stream": _val("nomination_stream", "OINP-Tech"),
              "expiry_date": _val("expiry_date", "2000-01-01")}
        res = ad.decide_nomination(_ctx("additional.nomination", by_field=by))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "expired_nomination")

    def test_missing_nomination_is_gap(self) -> None:
        res = ad.decide_nomination(_ctx("additional.nomination", by_field={}))
        self.assertEqual(res.verdict, "GAP")
        self.assertEqual(res.reason_code, "missing_evidence")


class TestFrench(unittest.TestCase):
    def test_below_threshold_is_gap(self) -> None:
        # Score maps to NCLC 7; claim NCLC 9 -> below -> GAP.
        factor = CrsProfileFactor(
            factor_id="additional.french", factor_group="additional_points",
            claimed_level="9", claimed_value=9)
        res = ad.decide_french(
            _ctx("additional.french", by_field=_french_fields(450), factor=factor))
        self.assertEqual(res.verdict, "GAP")
        self.assertEqual(res.reason_code, "below_threshold")

    def test_satisfying_french_substantiated(self) -> None:
        factor = CrsProfileFactor(
            factor_id="additional.french", factor_group="additional_points",
            claimed_level="9", claimed_value=9)
        res = ad.decide_french(
            _ctx("additional.french", by_field=_french_fields(520), factor=factor))
        self.assertEqual(res.verdict, "SUBSTANTIATED")
        self.assertEqual(res.substantiated_points, 25)


class TestStudy(unittest.TestCase):
    def test_missing_credential_is_gap(self) -> None:
        res = ad.decide_study(_ctx("additional.study", by_field={}))
        self.assertEqual(res.verdict, "GAP")
        self.assertEqual(res.reason_code, "missing_evidence")
        self.assertIsNone(res.substantiated_points)

    def test_credential_only_matrix_never_greens_or_awards_points(self) -> None:
        for level in ("secondary", "unknown", "1-2", "3+"):
            for forced_dli in (False, True):
                with self.subTest(level=level, forced_dli=forced_dli):
                    by = {"credential_level": _val("credential_level", level)}
                    if forced_dli:
                        by["dli_number"] = _val(
                            "dli_number", "O19332746152")
                    res = ad.decide_study(
                        _ctx("additional.study", by_field=by))
                    self.assertNotEqual(res.verdict, "SUBSTANTIATED")
                    self.assertIsNone(res.substantiated_points)
                    if level in ("1-2", "3+"):
                        self.assertEqual(res.verdict, "AT-RISK")
                        self.assertEqual(
                            res.reason_code,
                            "credential_only_no_designation",
                        )
                    else:
                        self.assertEqual(res.verdict, "GAP")
                        self.assertEqual(res.reason_code, "below_threshold")


# A shared confirmed ADULT sibling base (each field is confirmed + ok via _val,
# so it is already audit-eligible — the eligibility choke point is exercised
# separately by the conformance / real-seam suites). The DOB is a clear adult at
# the ITA date used below (2024-06-15).
_SIBLING_ADULT_BASE = {
    "sibling_relationship": "brother",
    "sibling_status": "permanent_resident",
    "sibling_residence": "Toronto, Ontario",
    "sibling_date_of_birth": "1988-03-12",
}
_SIBLING_ITA = "2024-06-15"


def _sibling_fields(**overrides):
    """Build a confirmed sibling by_field from the adult base, applying overrides.

    A value of ``None`` DROPS that field (to exercise the missing-field GAP path).
    """
    merged = dict(_SIBLING_ADULT_BASE)
    merged.update(overrides)
    return {field: _val(field, value)
            for field, value in merged.items() if value is not None}


class TestSibling(unittest.TestCase):
    """decide_sibling truth table: SUBSTANTIATED only on a confirmed ADULT chain;
    every missing / unaccepted / unresolvable case — AND a confirmed minor —
    fails closed. Points via the grounded points row, the adult threshold (18)
    via the grounded threshold row — never a Python literal."""

    def _decide(self, *, ita_date=_SIBLING_ITA, **overrides):
        by = _sibling_fields(**overrides)
        return ad.decide_sibling(
            _ctx("additional.sibling", by_field=by, ita_date=ita_date))

    def test_full_adult_chain_substantiated(self) -> None:
        res = self._decide()
        self.assertEqual(res.verdict, "SUBSTANTIATED")
        self.assertEqual(res.reason_code, "grounded_substantiated")
        self.assertEqual(res.substantiated_points, 15)

    def test_missing_required_field_is_gap(self) -> None:
        # Drop the residence field entirely.
        res = self._decide(sibling_residence=None)
        self.assertEqual(res.verdict, "GAP")
        self.assertEqual(res.reason_code, "missing_evidence")

    def test_non_accepted_relationship_is_at_risk(self) -> None:
        res = self._decide(sibling_relationship="cousin")
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "unresolved_sibling")
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    def test_non_accepted_status_is_at_risk(self) -> None:
        res = self._decide(sibling_status="visitor")
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "unresolved_sibling")
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    def test_unresolvable_dob_is_at_risk(self) -> None:
        res = self._decide(sibling_date_of_birth="not-a-date")
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "unresolved_sibling")
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    def test_no_authoritative_ita_date_is_at_risk(self) -> None:
        # Full adult chain, but the age cannot be pinned without an ITA date.
        res = self._decide(ita_date=None)
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "unresolved_sibling")
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    def test_on_eighteenth_birthday_is_adult_substantiated(self) -> None:
        # DOB exactly 18 years before the ITA date -> age_on_date == 18 -> adult.
        res = self._decide(sibling_date_of_birth="2006-06-15")
        self.assertEqual(res.verdict, "SUBSTANTIATED")
        self.assertEqual(res.reason_code, "grounded_substantiated")
        self.assertEqual(res.substantiated_points, 15)

    def test_day_before_eighteenth_birthday_is_minor(self) -> None:
        # DOB one day AFTER the 18-years-prior date -> age_on_date == 17 -> minor.
        res = self._decide(sibling_date_of_birth="2006-06-16")
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "sibling_minor")
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")
        self.assertIsNone(res.substantiated_points)

    def test_clear_minor_is_at_risk_sibling_minor(self) -> None:
        res = self._decide(sibling_date_of_birth="2015-01-01")
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "sibling_minor")
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")
        self.assertIsNone(res.substantiated_points)


class TestNoInlinedRules(unittest.TestCase):
    def test_module_has_no_inlined_volatile_rules(self) -> None:
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([ad.__file__]), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
