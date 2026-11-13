"""Grounded MEC registry contracts for FSW, FST, and CEC."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import get_args
from unittest.mock import patch

from pydantic import ValidationError

from crawler import auditor, crs_audit, crs_rules, searchindex, snapshot_policy
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    PolicyValue,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import FactorGroup, FieldName


EXPECTED_MEC_MANIFEST = {
    "fsw": (
        "fsw.work.primary_noc",
        "fsw.work.teer",
        "fsw.work.paid",
        "fsw.work.recency",
        "fsw.work.continuity_duration_hours",
        "fsw.work.noc_duties",
        "fsw.language.first",
        "fsw.education.minimum",
        "fsw.grid.language",
        "fsw.grid.education",
        "fsw.grid.experience",
        "fsw.grid.age",
        "fsw.grid.arranged_employment",
        "fsw.grid.adaptability",
        "fsw.grid.pass_mark",
        "fsw.funds.requirement",
        "fsw.destination.outside_quebec",
    ),
    "fst": (
        "fst.work.trade_noc",
        "fst.work.same_noc",
        "fst.work.paid",
        "fst.work.qualified_to_practise",
        "fst.work.student_exclusion",
        "fst.work.recency_duration_hours",
        "fst.work.noc_duties_requirements",
        "fst.language.minimum",
        "fst.offer_or_certificate",
        "fst.funds.requirement",
        "fst.destination.outside_quebec",
    ),
    "cec": (
        "cec.work.teer",
        "cec.work.in_canada",
        "cec.work.authorized_tr_status",
        "cec.work.paid",
        "cec.work.recency_duration_hours",
        "cec.work.student_exclusion",
        "cec.work.self_employment_exclusion",
        "cec.work.noc_duties",
        "cec.language.minimum",
        "cec.destination.outside_quebec",
    ),
}


def _row(rule_id: str, *, gap: bool = False, crawl_date: str | None = "2026-06-11") -> RuleRow:
    return RuleRow(
        rule_id=rule_id,
        factor_group="program_eligibility",
        factor_ids=[rule_id],
        check_type="admissibility",
        query="official program eligibility criterion",
        selector=Selector(family="guidance"),
        claim_text="The official criterion applies.",
        citations=[Citation(chunk_id="guidance/example.md#001", quote="official criterion")],
        machine_check=MachineCheck(
            kind="accepted_enum",
            field=rule_id,
            accepted_values=[{"value": "required", "citation_index": 0}],
        ),
        volatility=VolatilityMeta(
            volatility="volatile",
            source_family="guidance",
            crawl_date=crawl_date,
        ),
        gap=gap,
        gap_reason="not grounded" if gap else None,
    )


class TestMecFactorGroupContract(unittest.TestCase):
    def test_factor_group_adds_only_program_eligibility(self) -> None:
        self.assertEqual(
            get_args(FactorGroup),
            (
                "core_human_capital",
                "spouse_common_law",
                "skill_transferability",
                "additional_points",
                "program_eligibility",
            ),
        )

    def test_wave_three_extends_only_the_field_name_contract(self) -> None:
        from crawler import mecfields

        fields = set(get_args(FieldName))
        self.assertTrue(mecfields.MEC_ADDITIVE_FIELDS <= fields)
        self.assertIn("employment_period_id", fields)
        self.assertEqual(get_args(FactorGroup)[-1], "program_eligibility")

    def test_real_program_eligibility_row_validates(self) -> None:
        self.assertEqual(_row("fsw.work.paid").factor_group, "program_eligibility")


class TestMecTypedPayloadContract(unittest.TestCase):
    def test_payload_represents_duration_hierarchy_and_applicability(self) -> None:
        check = MachineCheck(
            kind="duration_hours",
            field="fst_work",
            minimum_duration_months=PolicyValue(value=24, citation_index=0),
            minimum_hours=PolicyValue(value=3120, citation_index=0),
            maximum_hours_per_week=PolicyValue(value=30, citation_index=0),
            lookback_years=PolicyValue(value=5, citation_index=0),
            included_hierarchy=[
                PolicyValue(value="Major Group 72", citation_index=0),
                PolicyValue(value="Minor Group 6320", citation_index=0),
            ],
            excluded_hierarchy=[
                PolicyValue(value="Sub-Major Group 726", citation_index=0),
            ],
            applicability=[
                PolicyValue(value="qualified_to_practise", citation_index=0),
            ],
            conditional_na=[
                PolicyValue(value="valid_offer_and_legal_work_authorization", citation_index=0),
            ],
        )
        self.assertEqual(check.minimum_hours.value, 3120)
        self.assertEqual(check.excluded_hierarchy[0].value, "Sub-Major Group 726")

    def test_every_additive_payload_value_has_a_valid_citation_index(self) -> None:
        raw = _row("fst.work.trade_noc").model_dump()
        raw["machine_check"].update(
            {
                "kind": "hierarchy",
                "included_hierarchy": [{"value": "Major Group 72", "citation_index": 1}],
            }
        )
        with self.assertRaises(ValidationError):
            RuleRow.model_validate(raw)


class TestMecManifestContract(unittest.TestCase):
    def test_manifest_is_exact_nonempty_duplicate_free_and_value_free(self) -> None:
        self.assertEqual(crs_rules.REQUIRED_MEC_RULE_IDS, EXPECTED_MEC_MANIFEST)
        flattened = tuple(
            rule_id
            for program in ("fsw", "fst", "cec")
            for rule_id in EXPECTED_MEC_MANIFEST[program]
        )
        self.assertEqual(crs_rules.REQUIRED_RULE_IDS["program_eligibility"], flattened)
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertFalse(any(any(ch.isdigit() for ch in part) for rule_id in flattened for part in rule_id.split(".")))

    def test_exact_manifest_coverage_is_complete(self) -> None:
        rows = [_row(rule_id) for ids in EXPECTED_MEC_MANIFEST.values() for rule_id in ids]
        info = crs_rules.coverage_report(Registry(rows=rows))["by_group"]["program_eligibility"]
        self.assertEqual(info["missing"], [])
        self.assertEqual(info["duplicates"], [])
        self.assertEqual(info["unknown"], [])
        self.assertEqual(info["malformed"], [])
        self.assertEqual(info["gaps"], [])

    def test_manifest_rejects_missing_duplicate_unknown_gap_and_malformed(self) -> None:
        ids = [rule_id for rules in EXPECTED_MEC_MANIFEST.values() for rule_id in rules]
        cases = {
            "missing": [_row(rule_id) for rule_id in ids[1:]],
            "duplicates": [_row(rule_id) for rule_id in ids] + [_row(ids[0])],
            "unknown": [_row(rule_id) for rule_id in ids] + [_row("fsw.grid.unknown")],
            "gaps": [_row(rule_id, gap=(rule_id == ids[0])) for rule_id in ids],
            "malformed": [_row(rule_id) for rule_id in ids] + [_row("fsw..broken")],
        }
        for expected, rows in cases.items():
            with self.subTest(expected=expected):
                report = crs_rules.coverage_report(Registry.model_construct(rows=rows))
                info = report["by_group"]["program_eligibility"]
                self.assertTrue(info[expected])
                self.assertFalse(report["complete"])


class TestMecOperationalFreshness(unittest.TestCase):
    def test_max_age_explicit_precedes_environment_and_has_no_default(self) -> None:
        with patch.dict(os.environ, {"PR_MEC_RULE_MAX_AGE_DAYS": "90"}, clear=False):
            self.assertEqual(snapshot_policy.mec_rule_max_age_days(30), 30)
            self.assertEqual(snapshot_policy.mec_rule_max_age_days(), 90)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(snapshot_policy.mec_rule_max_age_days())

    def test_invalid_explicit_max_age_never_falls_back(self) -> None:
        with patch.dict(os.environ, {"PR_MEC_RULE_MAX_AGE_DAYS": "90"}, clear=False):
            for value in (True, False, "", " ", "x", 0, -1, "0", "-2", 1.5):
                with self.subTest(value=value):
                    self.assertIsNone(snapshot_policy.mec_rule_max_age_days(value))

    def test_freshness_requires_reference_date_positive_bound_and_valid_crawl_date(self) -> None:
        reference = date(2026, 7, 1)
        fresh = _row("fsw.work.paid", crawl_date="2026-06-11T01:09:06Z")
        stale = _row("fsw.work.teer", crawl_date="2025-01-01")
        future = _row("fsw.work.recency", crawl_date="2026-07-02")
        malformed = _row("fsw.work.primary_noc", crawl_date="not-a-date")
        missing = _row("fsw.work.noc_duties", crawl_date=None)

        self.assertTrue(snapshot_policy.mec_rule_row_is_fresh(fresh, reference, 30))
        for row in (stale, future, malformed, missing):
            with self.subTest(rule_id=row.rule_id):
                self.assertFalse(snapshot_policy.mec_rule_row_is_fresh(row, reference, 30))
        for bad_reference in (None, "not-a-date"):
            self.assertFalse(snapshot_policy.mec_rule_row_is_fresh(fresh, bad_reference, 30))
        for bad_bound in (True, 0, -1, None):
            self.assertFalse(snapshot_policy.mec_rule_row_is_fresh(fresh, reference, bad_bound))

    def test_effectivity_and_freshness_are_both_required(self) -> None:
        raw = _row("cec.work.paid").model_dump()
        raw["volatility"]["effective_to"] = "2026-06-15"
        superseded = RuleRow.model_validate(raw)
        reference = date(2026, 7, 1)
        self.assertFalse(crs_audit.row_in_effect(superseded, reference))
        self.assertTrue(snapshot_policy.mec_rule_row_is_fresh(superseded, reference, 30))


class TestGroundedMecRegistry(unittest.TestCase):
    DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "crs_rules"
    REAL_DB = Path(__file__).resolve().parents[2] / "corpus" / "index.db"

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = crs_rules.load_registry(cls.DATA_DIR)
        cls.rows = [
            row for row in cls.registry.rows
            if row.factor_group == "program_eligibility"
        ]

    def test_registry_has_exact_complete_mec_rows(self) -> None:
        expected = {
            rule_id for rules in EXPECTED_MEC_MANIFEST.values() for rule_id in rules
        }
        self.assertEqual({row.rule_id for row in self.rows}, expected)
        info = crs_rules.coverage_report(self.registry)["by_group"]["program_eligibility"]
        for key in ("missing", "duplicates", "unknown", "malformed", "gaps"):
            self.assertEqual(info[key], [], f"{key}: {info[key]}")

    def test_registry_snapshot_is_deeply_isolated_from_every_mutable_view(self) -> None:
        original = crs_rules.load_registry(self.DATA_DIR)
        snapshot = crs_rules.RegistrySnapshot(
            registry=original,
            fingerprint=crs_rules.registry_fingerprint(original),
        )
        expected_ids = tuple(row.rule_id for row in snapshot.registry.rows)
        expected_fingerprint = snapshot.fingerprint

        original.rows.clear()
        exposed = snapshot.registry
        exposed.rows.clear()
        nested = snapshot.registry
        nested.rows[0].citations.clear()
        nested.rows[0].machine_check.accepted_values = []

        self.assertEqual(
            tuple(row.rule_id for row in snapshot.registry.rows), expected_ids
        )
        self.assertEqual(snapshot.fingerprint, expected_fingerprint)
        self.assertEqual(
            crs_rules.registry_fingerprint(snapshot.registry), expected_fingerprint
        )

    def test_registry_snapshot_rejects_detached_fingerprint(self) -> None:
        registry = crs_rules.load_registry(self.DATA_DIR)
        with self.assertRaises(ValueError):
            crs_rules.RegistrySnapshot(
                registry=registry,
                fingerprint="0" * 64,
            )

    def test_every_row_is_typed_cited_dated_effective_and_fresh(self) -> None:
        reference = date(2026, 7, 1)
        for row in self.rows:
            with self.subTest(rule_id=row.rule_id):
                self.assertTrue(row.citations)
                self.assertTrue(row.selector.marker)
                self.assertTrue(row.volatility.crawl_date)
                self.assertFalse(row.gap)
                self.assertTrue(crs_audit.row_in_effect(row, reference))
                self.assertTrue(
                    snapshot_policy.mec_rule_row_is_fresh(row, reference, 90)
                )

    def test_adaptability_entries_bind_to_exact_supporting_spans(self) -> None:
        row = next(item for item in self.rows if item.rule_id == "fsw.grid.adaptability")
        support_tokens = {
            "spouse_language": ("spouse", "language", "clb"),
            "applicant_study": ("applicant", "study"),
            "spouse_study": ("spouse", "study"),
            "applicant_work": ("applicant", "work"),
            "spouse_work": ("spouse", "work"),
            "arranged_employment": ("arranged employment",),
            "relative": ("relative",),
        }
        for entry in row.machine_check.points_by_level or []:
            citation = row.citations[entry.citation_index]
            normalized = citation.quote.casefold()
            with self.subTest(label=entry.label):
                self.assertIn(f"award {entry.points} points", normalized)
                for token in support_tokens[entry.label]:
                    self.assertIn(token, normalized)

    def test_fsw_offer_row_has_no_machine_pass_branch(self) -> None:
        row = next(
            item
            for item in self.rows
            if item.rule_id == "fsw.grid.arranged_employment"
        )
        self.assertFalse(row.machine_check.branches)

    def test_fst_offer_branch_is_manual_and_cites_unavailable_officer_facts(self) -> None:
        row = next(
            item for item in self.rows if item.rule_id == "fst.offer_or_certificate"
        )
        self.assertFalse(row.machine_check.branches)
        statutory_text = "\n".join(
            citation.quote
            for citation in row.citations
            if citation.chunk_id.startswith("legislation-irpr/")
        )
        self.assertIn("none of whom is an embassy", statutory_text)
        self.assertIn("an officer has approved the offer", statutory_text)

    def test_fsw_manual_offer_row_cites_exact_officer_determination(self) -> None:
        row = next(
            item
            for item in self.rows
            if item.rule_id == "fsw.grid.arranged_employment"
        )
        citation = next(
            citation
            for citation in row.citations
            if citation.chunk_id.endswith(
                "arranged-employment-licensing-certification.md#000"
            )
        )
        self.assertIn("officers must be satisfied", citation.quote)
        self.assertIn("capable of performing", citation.quote)
        self.assertIn("qualify for licensing/certification", citation.quote)

    def test_fsw_manual_offer_row_has_no_misbound_noc_or_teer_predicates(
        self,
    ) -> None:
        row = next(
            item
            for item in self.rows
            if item.rule_id == "fsw.grid.arranged_employment"
        )
        requirements = [
            requirement
            for branch in row.machine_check.branches or []
            for requirement in branch.requirements
        ]
        self.assertFalse(
            {
                requirement.field
                for requirement in requirements
                if requirement.field in {"offer_noc_code", "offer_teer"}
            }
        )
        teer_quote = next(
            citation.quote
            for citation in row.citations
            if "TEER category 0, 1, 2 or 3" in citation.quote
        )
        self.assertIn("of the NOC", teer_quote)

    def test_funds_exemption_branches_require_authorization_not_employment(self) -> None:
        for rule_id in ("fsw.funds.requirement", "fst.funds.requirement"):
            row = next(item for item in self.rows if item.rule_id == rule_id)
            branch = next(
                item
                for item in row.machine_check.branches or []
                if item.label == "funds_exemption"
            )
            with self.subTest(rule_id=rule_id):
                self.assertEqual(
                    [
                        (item.field, item.operator, item.value)
                        for item in branch.requirements
                    ],
                    [
                        (
                            "legally_authorized_to_work_canada",
                            "equals",
                            True,
                        )
                    ],
                )
                self.assertEqual(
                    [
                        item.value
                        for item in row.machine_check.conditional_na or []
                    ],
                    ["legal_work_authorization_and_valid_offer"],
                )

    def test_no_funds_amount_or_lico_value_is_shipped(self) -> None:
        text = (self.DATA_DIR / "mec.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?i)LICO|low.income.cut.off")
        self.assertNotRegex(text, r"[$€£]\s*\d|\bCAD\s*\d")
        for row in self.rows:
            if ".funds." in row.rule_id:
                payload = row.machine_check.model_dump()
                self.assertIsNone(payload["min_value"])
                self.assertIsNone(payload["max_value"])
                self.assertIsNone(payload["minimum_hours"])

    @unittest.skipUnless(
        REAL_DB.is_file(),
        "LOCAL-ONLY: real corpus index required for MEC grounding",
    )
    def test_real_rows_retrieve_what_they_cite_through_shared_gate(self) -> None:
        subset = Registry(rows=self.rows)
        self.assertIsNone(auditor.gate_subset(subset, self.REAL_DB))

    @unittest.skipUnless(
        REAL_DB.is_file(),
        "LOCAL-ONLY: real corpus index required for MEC grounding",
    )
    def test_grounding_tampering_fails_independently(self) -> None:
        row = self.rows[0]
        mutations = {
            "quote": lambda raw: raw["citations"][0].update(quote="not in the source"),
            "marker": lambda raw: raw["selector"].update(marker="not in the source"),
            "family": lambda raw: raw["selector"].update(family="legislation-irpa"),
            "title": lambda raw: raw["selector"].update(require_title_contains="wrong title"),
            "citation": lambda raw: raw["citations"][0].update(
                chunk_id="guidance/job-offer.md#001"
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                raw = row.model_dump()
                mutate(raw)
                with self.assertRaises(auditor.AuditGroundingError):
                    auditor.gate_subset(
                        Registry(rows=[RuleRow.model_validate(raw)]), self.REAL_DB
                    )

    def test_effective_and_freshness_tampering_fails_closed(self) -> None:
        row = self.rows[0]
        raw = row.model_dump()
        raw["volatility"]["effective_to"] = "2026-01-01"
        expired = RuleRow.model_validate(raw)
        self.assertFalse(crs_audit.row_in_effect(expired, date(2026, 7, 1)))

        raw = row.model_dump()
        raw["volatility"]["crawl_date"] = "2020-01-01"
        stale = RuleRow.model_validate(raw)
        self.assertFalse(
            snapshot_policy.mec_rule_row_is_fresh(stale, date(2026, 7, 1), 90)
        )

    def test_synthetic_row_grounds_through_shared_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "corpus"
            source = root / "guidance" / "mec.md"
            source.parent.mkdir(parents=True)
            source.write_text(
                "---\n"
                'url: "https://www.canada.ca/mec"\n'
                'title: "Official MEC"\n'
                'source_type: "guidance"\n'
                "---\n\n"
                "# Official MEC\n"
                "Applicants must satisfy the official criterion.\n",
                encoding="utf-8",
            )
            db = Path(tmp) / "index.db"
            searchindex.build_index(root, db)
            row = _row("fsw.work.paid")
            raw = row.model_dump()
            raw["query"] = "official criterion"
            raw["selector"]["marker"] = "Applicants must satisfy the official criterion."
            raw["citations"][0] = {
                "chunk_id": "guidance/mec.md#000",
                "quote": "Applicants must satisfy the official criterion.",
            }
            self.assertIsNone(
                auditor.gate_subset(
                    Registry(rows=[RuleRow.model_validate(raw)]), db
                )
            )

    def test_coverage_markdown_is_generated_without_drift(self) -> None:
        expected = crs_rules.render_coverage_markdown(self.registry)
        actual = (self.DATA_DIR / "COVERAGE.md").read_text(encoding="utf-8")
        self.assertEqual(actual, expected)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
