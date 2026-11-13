"""Phase-45 MEC conformance: no incomplete, stale, or unknown state can MEET."""

from __future__ import annotations

import ast
import hashlib
import inspect
import itertools
import json
import os
import socket
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest import mock

import pytest

from crawler import crs_rules, mec_publish, mec_screen, mecfields, vault
from crawler.auditors import FULL_GRID_FACTORS
from crawler.models.audit import PublicAuditEnvelope
from crawler.models.mec import (
    MecCounts,
    PrivateMecCriterion,
    PrivateMecReport,
    PublicMecSummary,
)
from crawler.models.vault import CrsProfileFactor
from crawler.tests.test_crs_no_inlined_rules import _V5_NAMED_MODULES

_MEC_MODULES = tuple(
    path
    for path in _V5_NAMED_MODULES
    if path.name
    in {"mec.py", "mecfields.py", "mec_screen.py", "mec_publish.py", "snapshot_policy.py"}
)


pytestmark = pytest.mark.conformance
_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _ROOT / "corpus" / "index.db"


def _criterion(
    criterion_id: str,
    status: str = "PASS",
    *,
    wired: bool = True,
    applicability_grounded: bool = False,
    applicable: bool | None = None,
    reason_code: str | None = None,
) -> PrivateMecCriterion:
    reason = reason_code or {
        "PASS": "criterion_satisfied",
        "FAIL": "confirmed_deterministic_failure",
        "AT-RISK": "evidence_missing",
        "N/A": "not_applicable",
    }[status]
    if status == "FAIL":
        applicability_grounded = True
        applicable = True
    elif status == "PASS":
        applicability_grounded = True
        applicable = True
    return PrivateMecCriterion(
        criterion_id=criterion_id,
        status=status,
        reason_code=reason,
        wired=wired,
        grounded=True,
        applicability_grounded=applicability_grounded,
        applicable=applicable,
        rule_ids=[criterion_id] if wired else [],
        corpus_citation_ids=[],
        applicant_values={},
        evidence_ids=[],
        employment_traces=[],
        sidecar_inputs={},
        grid_bounds={},
        completeness_attestations={"work": True} if status == "FAIL" else {},
        render_details={},
    )


def _complete(program: str) -> list[PrivateMecCriterion]:
    return [
        _criterion(spec.criterion_id)
        for spec in mec_screen.MEC_PROGRAM_CRITERIA[program]
    ]


def _context(program: str) -> mec_screen.MecGateContext:
    snapshot = crs_rules.load_registry_snapshot()
    rows = tuple(
        row
        for row in snapshot.registry.rows
        if row.rule_id in crs_rules.REQUIRED_MEC_RULE_IDS[program]
    )
    return mec_screen.MecGateContext(
        registry_snapshot=snapshot,
        registry_fingerprint=snapshot.fingerprint,
        selected_rows=rows,
        reference_date=date(2026, 7, 20),
        operational_as_of=date(2026, 7, 20),
        max_age_days=90,
        row_usability=tuple(
            mec_screen.MecRowUsability(row=row, usable=True, reason="usable")
            for row in rows
        ),
    )


def _evidence(
    periods: tuple[mecfields.EmploymentPeriod, ...] = (),
    **scalars,
) -> mecfields.MecEvidence:
    return mecfields.MecEvidence(
        candidate_id="conformance-candidate",
        registry_fingerprint=crs_rules.load_registry_snapshot().fingerprint,
        scalars=MappingProxyType(scalars),
        scalar_evidence_ids=MappingProxyType(
            {
                name: (f"val_{index}",)
                for index, name in enumerate(scalars)
            }
        ),
        periods=periods,
    )


def _period(period_id: str, **values) -> mecfields.EmploymentPeriod:
    return mecfields.EmploymentPeriod(
        employment_period_id=period_id,
        document_id=f"doc_{period_id[-8:]}",
        values=MappingProxyType(values),
        evidence_ids=(f"val_{period_id[-8:]}",),
    )


def _inputs() -> mec_screen.ConfirmedMecInputs:
    return mec_screen.ConfirmedMecInputs(
        language={
            "first": {
                "test_date": "2026-01-01",
                "clb_listening": 9,
                "clb_reading": 9,
                "clb_writing": 9,
                "clb_speaking": 9,
            }
        },
        education={
            "branch": "canadian_secondary_or_post_secondary_credential",
            "level": "secondary",
        },
        age_years=35,
    )


def _bundle() -> mec_screen.MecPublicationBundle:
    criterion = _criterion("cec.work.paid", "AT-RISK")
    report = PrivateMecReport(
        schema_version="1.0",
        run_id="mec_deadbeef0013deadbeef0013deadbeef",
        candidate_id="private-candidate",
        program="cec",
        status="AT-RISK",
        criteria=[criterion],
        counts=MecCounts(criteria=1, at_risk=1),
        registry_fingerprint="a" * 64,
        created_at="2026-07-20T00:00:00Z",
        private_report_path="output/mec/cec/latest.json",
    )
    public = mec_screen.to_public_mec_summary(
        report, report.private_report_path
    )
    public = public.model_copy(
        update={
            "criteria": [
                item.model_copy(update={"corpus_citation_ids": []})
                for item in public.criteria
            ]
        }
    )
    return mec_screen.MecPublicationBundle(
        private_report=report,
        public_summary=public,
        private_json=json.dumps(
            report.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
        private_markdown=mec_screen._render_private_markdown(report),
        public_json=json.dumps(
            public.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )


class TestExhaustiveMecOutcomeAlgebra(unittest.TestCase):
    """Every exact-manifest disturbance demotes; deterministic FAIL is first."""

    _AT_RISK_REASONS = (
        "evidence_missing",
        "evidence_unconfirmed",
        "scope_incomplete",
        "rule_out_of_window",
        "rule_stale",
        "rule_unavailable",
        "composition_refused",
    )

    def test_every_required_criterion_demotes_for_each_closed_at_risk_reason(
        self,
    ) -> None:
        for program, specs in mec_screen.MEC_PROGRAM_CRITERIA.items():
            for index, spec in enumerate(specs):
                for reason in self._AT_RISK_REASONS:
                    criteria = _complete(program)
                    criteria[index] = _criterion(
                        spec.criterion_id,
                        "AT-RISK",
                        reason_code=reason,
                    )
                    with self.subTest(
                        program=program, criterion=spec.criterion_id, reason=reason
                    ):
                        self.assertEqual(
                            mec_screen.rollup_program_status(program, criteria),
                            "AT-RISK",
                        )

    def test_missing_unknown_unwired_duplicate_invalid_na_and_unknown_status_demote(
        self,
    ) -> None:
        for program, specs in mec_screen.MEC_PROGRAM_CRITERIA.items():
            complete = _complete(program)
            first = complete[0]
            malformed_status = first.model_dump(mode="json")
            malformed_status["status"] = "UNKNOWN"
            unknown_criterion = first.model_dump(mode="json")
            unknown_criterion["criterion_id"] = f"{program}.unknown"
            invalid_na = first.model_dump(mode="json")
            invalid_na.update(
                {
                    "status": "N/A",
                    "reason_code": "not_applicable",
                    "applicability_grounded": False,
                    "applicable": False,
                }
            )
            cases = {
                "missing": complete[1:],
                "unknown": complete + [unknown_criterion],
                "unwired": [
                    item.model_copy(update={"wired": False, "rule_ids": []})
                    if item.criterion_id == first.criterion_id
                    else item
                    for item in complete
                ],
                "duplicate": complete + [first],
                "invalid_na": [invalid_na, *complete[1:]],
                "unknown_status": complete + [malformed_status],
            }
            for name, criteria in cases.items():
                with self.subTest(program=program, case=name):
                    self.assertEqual(
                        mec_screen.rollup_program_status(program, criteria),
                        "AT-RISK",
                    )

    def test_deterministic_fail_has_precedence_over_every_unresolved_state(self) -> None:
        for program, specs in mec_screen.MEC_PROGRAM_CRITERIA.items():
            if len(specs) < 2:
                continue
            for reason in self._AT_RISK_REASONS:
                criteria = _complete(program)
                criteria[0] = _criterion(specs[0].criterion_id, "FAIL")
                criteria[1] = _criterion(
                    specs[1].criterion_id, "AT-RISK", reason_code=reason
                )
                with self.subTest(program=program, reason=reason):
                    self.assertEqual(
                        mec_screen.rollup_program_status(program, criteria),
                        "DOES-NOT-MEET",
                    )

    def test_all_pass_and_each_manifest_valid_na_remain_representable(self) -> None:
        for program, specs in mec_screen.MEC_PROGRAM_CRITERIA.items():
            self.assertEqual(
                mec_screen.rollup_program_status(program, _complete(program)),
                "AT-RISK" if program == "fsw" else "MEETS",
            )
            for index, spec in enumerate(specs):
                if spec.applicability_predicate is None:
                    continue
                criteria = _complete(program)
                criteria[index] = _criterion(
                    spec.criterion_id,
                    "N/A",
                    applicability_grounded=True,
                    applicable=False,
                )
                with self.subTest(program=program, criterion=spec.criterion_id):
                    self.assertEqual(
                        mec_screen.rollup_program_status(program, criteria),
                        "AT-RISK" if program == "fsw" else "MEETS",
                    )

    def test_pairwise_status_precedence_is_deterministic(self) -> None:
        for left, right in itertools.product(("PASS", "FAIL", "AT-RISK"), repeat=2):
            criteria = _complete("cec")
            criteria[0] = _criterion(criteria[0].criterion_id, left)
            criteria[1] = _criterion(criteria[1].criterion_id, right)
            expected = (
                "DOES-NOT-MEET"
                if "FAIL" in (left, right)
                else "AT-RISK"
                if "AT-RISK" in (left, right)
                else "MEETS"
            )
            self.assertEqual(
                mec_screen.rollup_program_status("cec", criteria), expected
            )


class TestFreshnessSnapshotAndEvidenceControls(unittest.TestCase):
    def test_every_selected_row_uses_effectivity_and_one_unchanged_freshness_bound(
        self,
    ) -> None:
        snapshot = crs_rules.load_registry_snapshot()
        for program in mec_screen.MEC_PROGRAM_CRITERIA:
            with (
                mock.patch("crawler.mec_screen.auditor.gate_subset") as gate,
                mock.patch(
                    "crawler.mec_screen.crs_audit.row_in_effect", return_value=True
                ) as effective,
                mock.patch(
                    "crawler.mec_screen.snapshot_policy.mec_rule_row_is_fresh",
                    return_value=True,
                ) as fresh,
            ):
                context = mec_screen.prepare_mec_gate(
                    program,
                    snapshot,
                    "fixture.db",
                    "2026-07-20",
                    37,
                    as_of="2026-07-20",
                )
            self.assertIs(context.registry_snapshot, snapshot)
            self.assertEqual(context.max_age_days, 37)
            gate.assert_called_once()
            self.assertEqual(effective.call_count, len(context.selected_rows))
            self.assertEqual(fresh.call_count, len(context.selected_rows))
            self.assertTrue(
                all(call.args[2] == 37 for call in fresh.call_args_list)
            )
            self.assertTrue(
                all(call.args[1] == "2026-07-20" for call in fresh.call_args_list)
            )

    def test_none_or_non_snapshot_context_is_never_accepted(self) -> None:
        for snapshot in (None, object()):
            with self.subTest(snapshot=snapshot), self.assertRaises(
                mec_screen.MecGatePreparationError
            ):
                mec_screen.prepare_mec_gate(
                    "cec", snapshot, "fixture.db", "2026-07-20", 30
                )
        real = crs_rules.load_registry_snapshot()
        for max_age in (None, 0, -1, True):
            with self.subTest(max_age=max_age), self.assertRaises(
                mec_screen.MecGatePreparationError
            ):
                mec_screen.prepare_mec_gate(
                    "cec", real, "fixture.db", "2026-07-20", max_age
                )

    def test_all_five_confirmation_freshness_keys_remain_in_the_trust_predicate(
        self,
    ) -> None:
        source = inspect.getsource(vault.is_stale)
        for key in (
            "confirmed_file_sha256",
            "confirmed_render_sha256",
            "confirmed_parser_version",
            "confirmed_profile_claim_version",
            "confirmed_rule_registry_version",
        ):
            self.assertIn(key, source)
        eligible = inspect.getsource(vault.is_audit_eligible)
        self.assertIn("confirmed", eligible)
        self.assertIn("corrected", eligible)
        self.assertIn("quality_flag", eligible)
        self.assertIn("is_stale", eligible)


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY: corpus/index.db is required for production MEC conformance",
)
class TestProductionEvidenceAndGateTransitions(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.environment = mock.patch.dict(
            "os.environ", {"PR_PERSONAL_DIR": self.temp.name}
        )
        self.environment.start()
        self.snapshot = crs_rules.load_registry_snapshot()
        self.context = mec_screen.prepare_mec_gate(
            "cec",
            self.snapshot,
            str(_REAL_DB),
            date(2026, 6, 15),
            120,
            as_of=date(2026, 7, 20),
        )

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def _seed_value(
        self,
        vault_,
        candidate: str,
        *,
        field_name: str,
        normalized_value,
        quality_flag: str = "ok",
        page: bool = False,
    ) -> tuple[str, str, str | None]:
        source = Path(self.temp.name) / f"{candidate}-{field_name}.txt"
        source.write_text("private fixture", encoding="utf-8")
        document = vault.import_document(
            vault_, candidate, source, doc_type="mec-province-status"
        )
        run_id = vault.record_extraction_run(
            vault_,
            document_id=document.document_id,
            parser_version=vault.current_parser_version(),
        )
        page_id = (
            vault.add_document_page(
                vault_,
                document_id=document.document_id,
                page_number=1,
                render_sha256="a" * 64,
                extraction_run_id=run_id,
            )
            if page
            else None
        )
        value_id = vault.add_extracted_value(
            vault_,
            document_id=document.document_id,
            page_id=page_id,
            factor_id="review.mec",
            field_name=field_name,
            raw_text=str(normalized_value),
            normalized_value=normalized_value,
            bbox=None,
            extractor_confidence=1.0,
            quality_flag=quality_flag,
            extraction_run_id=run_id,
        )
        return value_id, document.document_id, page_id

    def _evidence_after_transition(
        self, transition: str
    ) -> mecfields.MecEvidence:
        candidate = f"candidate-{transition.replace('_', '-')}"
        vault_ = vault.open_vault(candidate)
        try:
            vault.create_candidate(vault_, candidate)
            vault.upsert_profile_factor(
                vault_,
                CrsProfileFactor(
                    factor_id="review.mec",
                    factor_group="program_eligibility",
                    claimed_value={},
                ),
            )
            quality = (
                transition
                if transition in {"low_quality", "ambiguous"}
                else "ok"
            )
            value_id, document_id, page_id = self._seed_value(
                vault_,
                candidate,
                field_name="intended_destination_province",
                normalized_value="ON",
                quality_flag=quality,
                page=transition == "stale_render",
            )
            if transition == "rejected":
                vault.confirm_value(
                    vault_,
                    value_id,
                    "reject",
                    registry_fingerprint=self.snapshot.fingerprint,
                )
            elif transition == "corrected":
                vault.confirm_value(
                    vault_,
                    value_id,
                    "correct",
                    corrected_value="ON",
                    registry_fingerprint=self.snapshot.fingerprint,
                )
            elif transition != "pending":
                vault.confirm_value(
                    vault_,
                    value_id,
                    "confirm",
                    registry_fingerprint=self.snapshot.fingerprint,
                )

            if transition == "stale_file":
                vault_.con.execute(
                    "UPDATE documents SET file_sha256 = ? WHERE document_id = ?",
                    ("b" * 64, document_id),
                )
            elif transition == "stale_render":
                vault_.con.execute(
                    "UPDATE document_pages SET render_sha256 = ? WHERE page_id = ?",
                    ("b" * 64, page_id),
                )
            elif transition == "stale_claim":
                vault.upsert_profile_factor(
                    vault_,
                    CrsProfileFactor(
                        factor_id="review.mec",
                        factor_group="program_eligibility",
                        claimed_value={"changed": True},
                    ),
                )
            elif transition == "stale_registry":
                vault_.con.execute(
                    "UPDATE extracted_values "
                    "SET confirmed_rule_registry_version = ? WHERE value_id = ?",
                    ("obsolete", value_id),
                )
            vault_.con.commit()

            parser = (
                mock.patch(
                    "crawler.vault.current_parser_version",
                    return_value="changed-parser",
                )
                if transition == "stale_parser"
                else mock.patch(
                    "crawler.vault.current_parser_version",
                    wraps=vault.current_parser_version,
                )
            )
            with parser:
                return mecfields.load_mec_evidence(
                    vault_,
                    candidate,
                    self.snapshot.fingerprint,
                )
        finally:
            vault_.con.close()

    def test_untrusted_evidence_transitions_demote_through_adapter_and_evaluator(
        self,
    ) -> None:
        transitions = (
            "confirmed",
            "corrected",
            "pending",
            "rejected",
            "low_quality",
            "ambiguous",
            "stale_file",
            "stale_render",
            "stale_parser",
            "stale_claim",
            "stale_registry",
        )
        for transition in transitions:
            evidence = self._evidence_after_transition(transition)
            destination = {
                item.criterion_id: item
                for item in mec_screen.evaluate_cec(
                    self.context,
                    evidence,
                    mec_screen.ConfirmedMecInputs(),
                )
            }["cec.destination.outside_quebec"]
            with self.subTest(transition=transition):
                expected = (
                    "PASS"
                    if transition in {"confirmed", "corrected"}
                    else "AT-RISK"
                )
                self.assertEqual(destination.status, expected)
                self.assertEqual(
                    evidence.value("intended_destination_province"),
                    "ON" if expected == "PASS" else None,
                )

    def test_stale_prerequisite_demotes_every_dependent_fst_criterion(self) -> None:
        stale_rule = "fst.work.trade_noc"
        with mock.patch(
            "crawler.mec_screen.snapshot_policy.mec_rule_row_is_fresh",
            side_effect=lambda row, *_args: row.rule_id != stale_rule,
        ):
            context = mec_screen.prepare_mec_gate(
                "fst",
                self.snapshot,
                str(_REAL_DB),
                date(2026, 6, 15),
                120,
                as_of=date(2026, 7, 20),
            )
        period = _period(
            "mep_" + "a" * 32,
            noc_code="72600",
            teer=2,
            paid_status=False,
            qualified_to_practise=False,
            employment_start="2025-01-01",
            employment_end="2025-12-31",
            duration_months=12,
            total_hours=1560,
            hours_per_week=30,
        )
        criteria = {
            item.criterion_id: item
            for item in mec_screen.evaluate_fst(
                context,
                _evidence((period,), work_history_scope_complete=True),
                _inputs(),
            )
        }
        dependents = (
            "fst.work.same_noc",
            "fst.work.paid",
            "fst.work.qualified_to_practise",
            "fst.work.student_exclusion",
            "fst.work.recency_duration_hours",
            "fst.work.noc_duties_requirements",
            "fst.offer_or_certificate",
        )
        self.assertTrue(
            all(criteria[item].status == "AT-RISK" for item in dependents)
        )
        self.assertNotIn(
            "FAIL", {criteria[item].status for item in dependents}
        )


class TestFundsSidecarsPeriodsAndPrivacy(unittest.TestCase):
    def test_fst_certificate_scope_is_a_closed_no_false_pass_gate(self) -> None:
        context = _context("fst")
        period = _period(
            "mep_" + "b" * 32,
            noc_code="72200",
            paid_status=True,
            student_status=False,
            qualified_to_practise=True,
            employment_start="2024-01-02",
            employment_end="2026-01-01",
            duration_months=24,
            total_hours=30 * 731 / 7,
            hours_per_week=30,
        )
        certificate = {
            "work_history_scope_complete": True,
            "trade_certificate_authority": "Ontario authority",
            "trade_certificate_jurisdiction": "ON",
            "trade_certificate_noc_code": "72200",
            "trade_certificate_status": "valid",
            "trade_certificate_issue_date": "2025-01-01",
            "trade_certificate_expiry_date": "2027-01-01",
        }
        cases = (
            ("missing", certificate, frozenset(), "AT-RISK", False),
            (
                "false",
                {**certificate, "offer_certificate_scope_complete": False},
                frozenset(),
                "AT-RISK",
                False,
            ),
            (
                "scope_conflict",
                {**certificate, "offer_certificate_scope_complete": True},
                frozenset({"offer_certificate_scope_complete"}),
                "AT-RISK",
                False,
            ),
            (
                "certificate_conflict",
                {**certificate, "offer_certificate_scope_complete": True},
                frozenset({"trade_certificate_status"}),
                "AT-RISK",
                True,
            ),
            (
                "confirmed_complete",
                {**certificate, "offer_certificate_scope_complete": True},
                frozenset(),
                "PASS",
                True,
            ),
        )
        for label, scalars, conflicts, expected_status, expected_complete in cases:
            evidence = replace(
                _evidence((period,), **scalars),
                conflicts=conflicts,
            )
            criterion = {
                item.criterion_id: item
                for item in mec_screen.evaluate_fst(context, evidence, _inputs())
            }["fst.offer_or_certificate"]
            with self.subTest(label=label):
                self.assertEqual(criterion.status, expected_status)
                self.assertNotEqual(
                    criterion.status,
                    "FAIL",
                    "unresolved certificate evidence must not hard-fail",
                )
                self.assertEqual(
                    criterion.completeness_attestations.offer_certificate,
                    expected_complete,
                )

    def test_funds_amount_never_changes_unavailable_outcome(self) -> None:
        for program, criterion_id in (
            ("fsw", "fsw.funds.requirement"),
            ("fst", "fst.funds.requirement"),
        ):
            context = _context(program)
            for amount in (None, "0", "999999999999999999", "-1"):
                values = {} if amount is None else {"funds_amount": amount}
                evidence = _evidence(
                    funds_household_size=1,
                    funds_accessible=True,
                    **values,
                )
                evaluator = (
                    mec_screen.evaluate_fsw
                    if program == "fsw"
                    else mec_screen.evaluate_fst
                )
                criterion = {
                    item.criterion_id: item
                    for item in evaluator(context, evidence, _inputs())
                }[criterion_id]
                with self.subTest(program=program, amount=amount):
                    self.assertEqual(
                        (criterion.status, criterion.reason_code),
                        ("AT-RISK", "funds_snapshot_unavailable"),
                    )

    def test_grounded_funds_exemption_is_the_only_na_branch(self) -> None:
        for program, criterion_id in (
            ("fsw", "fsw.funds.requirement"),
            ("fst", "fst.funds.requirement"),
        ):
            evaluator = (
                mec_screen.evaluate_fsw
                if program == "fsw"
                else mec_screen.evaluate_fst
            )
            offer_validation = mec_screen.MecOfferValidation(
                status="PASS",
                program=program,
                selected_noc="72200" if program == "fst" else "21231",
                reason="grounded_offer_satisfied",
                rule_ids=(
                    "fst.offer_or_certificate"
                    if program == "fst"
                    else "fsw.grid.arranged_employment",
                ),
            )
            evidence = _evidence(
                legally_authorized_to_work_canada=True,
                currently_working_in_canada=False,
            )
            inputs = _inputs()
            object.__setattr__(inputs, "offer_validation", offer_validation)
            if program == "fst":
                start = date(2024, 1, 1)
                end = date(2025, 12, 31)
                days = (end - start).days + 1
                evidence = _evidence(
                    (
                        _period(
                            "mep_" + "7" * 32,
                            noc_code="72200",
                            paid_status=True,
                            student_status=False,
                            qualified_to_practise=True,
                            employment_start=start.isoformat(),
                            employment_end=end.isoformat(),
                            duration_months=24,
                            total_hours=30 * days / 7,
                            hours_per_week=30,
                        ),
                    ),
                    work_history_scope_complete=True,
                    offer_certificate_scope_complete=True,
                    legally_authorized_to_work_canada=True,
                    currently_working_in_canada=False,
                    offer_full_time=True,
                    offer_continuous=True,
                    offer_paid_status=True,
                    offer_duration_months=12,
                    offer_employer_count=1,
                    offer_noc_code="72200",
                    offer_status="valid",
                    offer_valid_from="2026-01-01",
                    offer_valid_until="2027-01-01",
                )
            criteria = evaluator(_context(program), evidence, inputs)
            criterion = {
                item.criterion_id: item for item in criteria
            }[criterion_id]
            expected = ("AT-RISK", "funds_snapshot_unavailable")
            self.assertEqual((criterion.status, criterion.reason_code), expected)
            self.assertTrue(criterion.applicability_grounded)
            self.assertTrue(criterion.applicable)
            self.assertNotIn(
                evidence.scalar_evidence_ids["currently_working_in_canada"][0],
                criterion.evidence_ids,
            )

            unauthorized = evidence.__class__(
                **{
                    **evidence.__dict__,
                    "scalars": MappingProxyType(
                        {
                            **evidence.scalars,
                            "legally_authorized_to_work_canada": False,
                        }
                    ),
                }
            )
            unauthorized_criterion = {
                item.criterion_id: item
                for item in evaluator(_context(program), unauthorized, inputs)
            }[criterion_id]
            self.assertEqual(
                (
                    unauthorized_criterion.status,
                    unauthorized_criterion.reason_code,
                ),
                ("AT-RISK", "funds_snapshot_unavailable"),
            )

    def test_sidecar_at_risk_and_split_period_facts_never_false_meet(self) -> None:
        split = (
            _period(
                "mep_" + "1" * 32,
                noc_code="21231",
                paid_status=True,
                employment_end="2026-01-01",
            ),
            _period(
                "mep_" + "2" * 32,
                teer=1,
                total_hours=1600,
                duration_months=12,
                work_country="CA",
            ),
        )
        evidence = _evidence(split, work_history_scope_complete=True)
        with (
            mock.patch(
                "crawler.policy_offer.offer_for_program_eligibility",
                return_value={"eligibility_status": "AT-RISK"},
            ),
            mock.patch(
                "crawler.noc_review.review_noc_duties",
                return_value={"status": "AT-RISK"},
            ),
        ):
            bundle = mec_screen.screen_mec(
                "cec",
                _context("cec"),
                evidence,
                _inputs(),
                vault_=object(),
                db="fixture.db",
            )
        self.assertEqual(bundle.private_report.status, "AT-RISK")
        self.assertNotIn("ev_", bundle.public_json.decode())
        self.assertTrue(
            all(not item.corpus_citation_ids for item in bundle.public_summary.criteria)
        )

    def test_public_scanner_rejects_citations_pii_dates_amounts_noc_and_paths(self) -> None:
        clean = _bundle().public_json
        mec_publish._scan_public_bytes(clean)
        hostile_values = (
            "ev_abcdef123456",
            "/home/private/person",
            "2026-07-20",
            "$999999",
            "noc 21231",
            "employer",
        )
        for hostile in hostile_values:
            payload = json.loads(clean)
            payload["run_id"] = hostile
            with self.subTest(hostile=hostile), self.assertRaises(
                mec_publish.MecPublicationError
            ):
                mec_publish._scan_public_bytes(
                    json.dumps(
                        payload, sort_keys=True, separators=(",", ":")
                    ).encode()
                )


class TestPersistentPublicationFaults(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = SimpleNamespace(root=self.root)
        self.directory = self.root / "output" / "mec" / "cec"
        self.directory.mkdir(parents=True)
        self.json_path = self.directory / "latest.json"
        self.markdown_path = self.directory / "latest.md"
        self.old_json = b'{"lkg":"private-json"}'
        self.old_markdown = b"# private LKG\n"
        self.json_path.write_bytes(self.old_json)
        self.markdown_path.write_bytes(self.old_markdown)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _assert_lkg_unchanged(self) -> None:
        self.assertEqual(self.json_path.read_bytes(), self.old_json)
        self.assertEqual(self.markdown_path.read_bytes(), self.old_markdown)
        self.assertFalse(
            any(
                item.name.startswith(".")
                for item in self.directory.iterdir()
            )
        )

    def test_persistent_stage_failure_never_mutates_lkg(self) -> None:
        with mock.patch(
            "crawler.mec_publish._stage_bytes",
            side_effect=OSError("persistent staging failure"),
        ), self.assertRaises(mec_publish.MecPublicationError):
            mec_publish.publish_mec_bundle(self.vault, _bundle())
        self._assert_lkg_unchanged()

    def test_persistent_replace_failure_after_first_mutation_restores_lkg(
        self,
    ) -> None:
        calls = 0

        def replace_then_fail(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                os.replace(source, destination)
                return
            raise OSError("persistent replacement failure")

        with mock.patch(
            "crawler.mec_publish._replace", side_effect=replace_then_fail
        ), self.assertRaises(mec_publish.MecPublicationError):
            mec_publish.publish_mec_bundle(self.vault, _bundle())
        self.assertGreaterEqual(calls, 2)
        self._assert_lkg_unchanged()

    def test_repeated_directory_fsync_failure_restores_installed_outputs(
        self,
    ) -> None:
        with mock.patch(
            "crawler.mec_publish._fsync_dir",
            side_effect=OSError("persistent fsync failure"),
        ), self.assertRaises(mec_publish.MecPublicationError):
            mec_publish.publish_mec_bundle(self.vault, _bundle())
        self._assert_lkg_unchanged()


class TestFrozenMecSurfaces(unittest.TestCase):
    _HASHES = {
        "pyproject.toml": "14a8f76981990a930d6b41ef0784d23140a81dd3ef4bfb4ffbb7627fee037121",
        "poetry.lock": "5561be20ae437b6ecabd66f3c5948f744c1f6562cb0d8929f386466323b42753",
        "scripts/run_conformance.py": "2ab68b4db1b542b00afec18ddf036e859350f0406390381c4ecbfb8ffcea27dc",
        "crawler/models/audit.py": "1ed3dbba6d899dbfa89aeb9753471e15353efa5623578b60bcaebd86c0880910",
        "crawler/crs_audit.py": "cac7049a2d5e7e5cf7832f521c8da316ba201780a1f9fe1d94eb9658c924f5ac",
        "crawler/auditor.py": "d11f25eb578021bc49f6cd88a703fd64782a3c5b2ac92bb95e1c7685b5a35b15",
        "crawler/policy_offer.py": "61ead827c1b9f833a3e8b6640a080df646b61c3590074fda04cc73f5296ad443",
        "crawler/auditors/__init__.py": "48305e49d8763c81ca41004c4081ec59b6cedf78f5e01f7e60e745f81626e01d",
        "crawler/models/crs_rules.py": "9b76b79d7ea30c54bc3aa8af038ec338ac85c1dd1820de52fb8966dfcb7515ec",
        "crawler/models/mec.py": "7780d17658e3026477f26f817b5615d1fa0095ea2b99bb64cb32bad829aa87a8",
        "crawler/models/vault.py": "db5c277c66b4f77d8ae28ce9db3b43b06a4e9a986d8fe432be40149c752b3cf2",
        "crawler/mecfields.py": "9ab3802b92b92c67af4b01bb0a0cdd0a2ed824117a9abbc43dc3a91df092af85",
        "crawler/mec_screen.py": "6746726604fcfb0cf9bd620ec184e32ffa5bcdcf654253f55d7323383ad18dc5",
        "crawler/extraction.py": "23ab41880cf6fd311f43bbb6ad17efc1c212b969f387a6f51f7a0fc9da22ab75",
        "crawler/data/crs_rules/mec.yaml": "eeedb511346d3f0ad02e7dd496140daa9d533906869ea8759a6db086595d8eb5",
    }

    def test_dependency_release_gate_and_crs_sources_are_frozen(self) -> None:
        for relative, expected in self._HASHES.items():
            with self.subTest(path=relative):
                self.assertEqual(
                    hashlib.sha256((_ROOT / relative).read_bytes()).hexdigest(),
                    expected,
                )

    def test_public_audit_envelope_and_full_grid_are_exactly_unchanged(self) -> None:
        self.assertEqual(
            tuple(PublicAuditEnvelope.model_fields),
            (
                "run_id",
                "factor_id",
                "verdicts",
                "claims",
                "counts",
                "private_output_path",
            ),
        )
        self.assertEqual(
            FULL_GRID_FACTORS,
            (
                "core.age",
                "core.education",
                "core.language.first",
                "core.language.second",
                "core.work",
                "spouse.education",
                "spouse.language",
                "spouse.work",
                "transfer.education_language",
                "transfer.education_work",
                "transfer.foreign_language",
                "transfer.foreign_work",
                "transfer.certificate_language",
                "additional.nomination",
                "additional.job_offer",
                "additional.study",
                "additional.french",
                "additional.sibling",
            ),
        )
        self.assertFalse(
            any("program" in factor or "mec" in factor for factor in FULL_GRID_FACTORS)
        )

    def test_public_mec_summary_is_closed_and_citation_free(self) -> None:
        self.assertEqual(
            tuple(PublicMecSummary.model_fields),
            (
                "schema_version",
                "run_id",
                "program",
                "status",
                "criteria",
                "counts",
                "registry_fingerprint",
                "private_output_path",
                "screening_notice",
            ),
        )
        public = _bundle().public_summary
        self.assertTrue(all(not item.corpus_citation_ids for item in public.criteria))
        with self.assertRaises(Exception):
            PublicMecSummary.model_validate(
                {**public.model_dump(mode="json"), "raw_value": "private"}
            )

    def test_mec_modules_have_no_network_or_alternate_rule_loader(self) -> None:
        forbidden_imports = {"requests", "httpx", "urllib", "aiohttp"}
        loader_calls = 0
        for path in _MEC_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = {
                node.names[0].name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
            } | {
                (node.module or "").split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            self.assertFalse(imports & forbidden_imports, path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = (
                        node.func.attr
                        if isinstance(node.func, ast.Attribute)
                        else node.func.id
                        if isinstance(node.func, ast.Name)
                        else ""
                    )
                    if name == "load_registry_snapshot":
                        loader_calls += 1
                    self.assertNotIn(
                        name,
                        {"load_registry", "safe_load", "connect"},
                        f"alternate rule loader in {path}:{getattr(node, 'lineno', 0)}",
                    )
        # MEC production modules receive the command-owned object. The sole load
        # remains visibly in the exact CLI handler, outside this enrolled set.
        self.assertEqual(loader_calls, 0)
        self.assertEqual(
            inspect.getsource(mec_screen).count("load_registry_snapshot("), 0
        )

    def test_runtime_publication_and_rollup_never_open_a_socket(self) -> None:
        with mock.patch.object(
            socket, "socket", side_effect=AssertionError("network forbidden")
        ):
            self.assertEqual(
                mec_screen.rollup_program_status("cec", _complete("cec")), "MEETS"
            )
            mec_publish._scan_public_bytes(_bundle().public_json)

    def test_scanner_enrolls_every_mec_production_module(self) -> None:
        expected = {
            _ROOT / "crawler" / "models" / "mec.py",
            _ROOT / "crawler" / "mecfields.py",
            _ROOT / "crawler" / "mec_screen.py",
            _ROOT / "crawler" / "mec_publish.py",
            _ROOT / "crawler" / "snapshot_policy.py",
        }
        self.assertEqual(set(_MEC_MODULES), expected)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
