"""Strict MEC contracts, projection firewall, and canonical program rollup."""

from __future__ import annotations

import itertools
import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from unittest import mock

from pydantic import ValidationError

from crawler import auditor, crs_rules, mec_screen, study_review, vault
from crawler.mecfields import EmploymentPeriod, MecEvidence
from crawler import mecfields
from crawler.mec_screen import (
    ConfirmedMecInputs,
    MEC_PROGRAM_CRITERIA,
    MecGatePreparationError,
    MecOfferValidation,
    build_confirmed_mec_inputs,
    evaluate_fsw,
    evaluate_cec,
    evaluate_fst,
    prepare_mec_gate,
    rollup_program_status,
    screen_mec,
    _validate_mec_offer,
)
from crawler.models.mec import (
    CriterionStatus,
    PrivateMecCriterion,
    PrivateMecReport,
    ProgramStatus,
    PublicMecCriterion,
    PublicMecSummary,
    to_public_mec_summary,
)
from crawler.models.vault import CrsProfileFactor


def _criterion(
    criterion_id: str,
    status: str = "PASS",
    *,
    wired: bool = True,
    applicability_grounded: bool = False,
    applicable: bool | None = None,
    reason_code: str | None = None,
) -> PrivateMecCriterion:
    if reason_code is None:
        reason_code = {
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
    elif status == "N/A":
        applicability_grounded = True
        applicable = False
    return PrivateMecCriterion(
        criterion_id=criterion_id,
        status=status,
        reason_code=reason_code,
        corpus_citation_ids=["guidance/mec.md#001"],
        wired=wired,
        grounded=True,
        applicability_grounded=applicability_grounded,
        applicable=applicable,
        rule_ids=[criterion_id],
        applicant_values={"points": 1},
        evidence_ids=["ev_private"],
        employment_traces=[],
        sidecar_inputs={},
        grid_bounds={"lower": 1, "upper": 1},
        completeness_attestations={"work": True},
        render_details={"rule_usability": "usable"},
    )


def _complete(program: str, status: str = "PASS") -> list[PrivateMecCriterion]:
    return [
        _criterion(spec.criterion_id, status)
        for spec in MEC_PROGRAM_CRITERIA[program]
    ]


class TestMecModelContract(unittest.TestCase):
    def test_model_status_vocabularies_are_exact(self) -> None:
        self.assertEqual(get_args(CriterionStatus), ("PASS", "FAIL", "AT-RISK", "N/A"))
        self.assertEqual(
            get_args(ProgramStatus),
            ("MEETS", "DOES-NOT-MEET", "AT-RISK"),
        )
        for invalid in ("pass", "GAP", "UNKNOWN", "", None):
            with self.subTest(invalid=invalid):
                raw = _criterion("fsw.work.paid").model_dump()
                raw["status"] = invalid
                with self.assertRaises(ValidationError):
                    PrivateMecCriterion.model_validate(raw)

    def test_public_reason_is_closed_and_funds_spelling_is_exact(self) -> None:
        valid = _criterion(
            "fsw.funds.requirement",
            "AT-RISK",
            reason_code="funds_snapshot_unavailable",
        )
        self.assertEqual(valid.reason_code, "funds_snapshot_unavailable")
        for invalid in (
            "funds_unavailable",
            "funds_snapshot_missing",
            "Funds snapshot unavailable",
            "free form private reason",
        ):
            with self.subTest(invalid=invalid):
                raw = valid.model_dump()
                raw["reason_code"] = invalid
                with self.assertRaises(ValidationError):
                    PrivateMecCriterion.model_validate(raw)

    def test_public_and_private_models_forbid_extra_fields(self) -> None:
        private = _criterion("cec.work.paid")
        with self.assertRaises(ValidationError):
            PrivateMecCriterion.model_validate(
                {**private.model_dump(), "unexpected": "value"}
            )
        public = PublicMecCriterion(
            criterion_id=private.criterion_id,
            status=private.status,
            reason_code=private.reason_code,
            corpus_citation_ids=private.corpus_citation_ids,
        )
        with self.assertRaises(ValidationError):
            PublicMecCriterion.model_validate(
                {**public.model_dump(), "applicant_value": "secret"}
            )

    def test_fail_rejects_unresolved_or_contradictory_proof_metadata(self) -> None:
        valid = _criterion("cec.work.paid", "FAIL")
        mutations = (
            {"reason_code": "evidence_missing"},
            {"reason_code": "rule_stale"},
            {"wired": False},
            {"applicability_grounded": False},
            {"applicable": None},
            {"applicable": False},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                PrivateMecCriterion.model_validate(
                    {**valid.model_dump(mode="json"), **mutation}
                )

    def test_pass_rejects_unresolved_or_contradictory_proof_metadata(self) -> None:
        valid = _criterion("cec.work.paid")
        mutations = (
            {"reason_code": "evidence_missing"},
            {"wired": False},
            {"grounded": False},
            {"applicability_grounded": False},
            {"applicable": None},
            {"applicable": False},
            {"rule_ids": []},
            {"rule_ids": ["cec.work.teer"]},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                PrivateMecCriterion.model_validate(
                    {**valid.model_dump(mode="json"), **mutation}
                )

    def test_rollup_does_not_trust_unvalidated_fail_copies(self) -> None:
        criteria = _complete("cec")
        criteria[0] = criteria[0].model_copy(
            update={
                "status": "FAIL",
                "reason_code": "evidence_missing",
                "applicability_grounded": False,
                "applicable": None,
            }
        )
        self.assertEqual(rollup_program_status("cec", criteria), "AT-RISK")

    def test_rollup_revalidates_forged_pass_copies_and_manifest_rule_ids(self) -> None:
        criteria = _complete("cec")
        criteria[0] = criteria[0].model_copy(
            update={
                "reason_code": "evidence_missing",
                "grounded": False,
                "applicability_grounded": False,
                "applicable": False,
                "rule_ids": [],
            }
        )
        self.assertEqual(rollup_program_status("cec", criteria), "AT-RISK")

        criteria = _complete("cec")
        criteria[0] = criteria[0].model_copy(
            update={"rule_ids": ["cec.work.paid"]}
        )
        self.assertEqual(rollup_program_status("cec", criteria), "AT-RISK")


class TestMecProjection(unittest.TestCase):
    def test_study_recovery_failure_is_not_downgraded_to_composition_refusal(
            self) -> None:
        context = mock.Mock()
        context.registry_snapshot.registry = mock.Mock()
        context.registry_fingerprint = "a" * 64
        evidence = mock.Mock(
            scalars={},
            candidate_id="candidate",
        )
        inputs = mock.Mock(sidecars={})

        with (
            mock.patch(
                "crawler.mec_screen.employment_periods",
                return_value=[],
            ),
            mock.patch(
                "crawler.policy_offer.offer_for_program_eligibility",
                return_value={"status": "N/A"},
            ),
            mock.patch(
                "crawler.study_review.review_study",
                side_effect=study_review.StudyReportRecoveryError(
                    "study report recovery failed"
                ),
            ),
            self.assertRaises(study_review.StudyReportRecoveryError),
        ):
            mec_screen._compose_sidecars(
                "fsw",
                context,
                evidence,
                inputs,
                vault_=mock.Mock(),
                db="unused.db",
                study_max_age_days=30,
            )

    def test_projection_is_an_explicit_pii_light_allowlist(self) -> None:
        criteria = _complete("fsw")
        report = PrivateMecReport(
            schema_version="1.0",
            run_id="mec_deadbeef0001deadbeef0001deadbeef",
            candidate_id="candidate-private",
            program="fsw",
            status="MEETS",
            criteria=criteria,
            counts={"criteria": len(criteria), "passed": len(criteria)},
            registry_fingerprint="f" * 64,
            created_at="2026-07-20T03:00:00Z",
            private_report_path="output/mec/fsw/latest.json",
        )

        public = to_public_mec_summary(report, "output/mec/fsw/latest.json")
        dumped = public.model_dump()
        serialized = public.model_dump_json()

        self.assertEqual(
            set(dumped),
            {
                "schema_version",
                "run_id",
                "program",
                "status",
                "criteria",
                "counts",
                "registry_fingerprint",
                "private_output_path",
                "screening_notice",
            },
        )
        self.assertNotIn("candidate-private", serialized)
        for private_value in (
            '"points":1',
            "ev_private",
        ):
            self.assertNotIn(private_value, serialized)
        self.assertEqual(
            set(dumped["criteria"][0]),
            {"criterion_id", "status", "reason_code", "corpus_citation_ids"},
        )

    def test_public_paths_reject_absolute_drive_and_traversal_paths(self) -> None:
        criteria = _complete("cec")
        report = PrivateMecReport(
            schema_version="1.0",
            run_id="mec_deadbeef0002deadbeef0002deadbeef",
            candidate_id="candidate-private",
            program="cec",
            status="MEETS",
            criteria=criteria,
            counts={"criteria": len(criteria)},
            registry_fingerprint="a" * 64,
            created_at="2026-07-20T03:00:00Z",
            private_report_path="output/mec/cec/latest.json",
        )
        for path in ("/tmp/report.json", r"C:\private\report.json", "../report.json"):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                to_public_mec_summary(report, path)

    def test_public_citations_reject_evidence_ids(self) -> None:
        with self.assertRaises(ValidationError):
            PublicMecCriterion(
                criterion_id="cec.work.paid",
                status="PASS",
                reason_code="criterion_satisfied",
                corpus_citation_ids=["ev_private"],
            )


class TestMecManifestAndRollup(unittest.TestCase):
    def test_manifest_is_exact_complete_ordered_and_policy_value_free(self) -> None:
        self.assertEqual(tuple(MEC_PROGRAM_CRITERIA), ("fsw", "fst", "cec"))
        for program, specs in MEC_PROGRAM_CRITERIA.items():
            self.assertEqual(
                tuple(spec.criterion_id for spec in specs),
                crs_rules.REQUIRED_MEC_RULE_IDS[program],
            )
            self.assertEqual(
                tuple(spec.rule_ids for spec in specs),
                tuple((criterion_id,) for criterion_id in crs_rules.REQUIRED_MEC_RULE_IDS[program]),
            )
            self.assertEqual(len(specs), len({spec.criterion_id for spec in specs}))

    def test_rollup_keeps_fsw_manual_while_other_all_pass_programs_meet(self) -> None:
        for program in MEC_PROGRAM_CRITERIA:
            with self.subTest(program=program):
                self.assertEqual(
                    rollup_program_status(program, _complete(program)),
                    "AT-RISK" if program == "fsw" else "MEETS",
                )

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
            with self.subTest(left=left, right=right):
                self.assertEqual(rollup_program_status("cec", criteria), expected)

    def test_missing_duplicate_unknown_and_unwired_inputs_fail_closed(self) -> None:
        criteria = _complete("fsw")
        cases = {
            "missing": criteria[1:],
            "duplicate": criteria + [criteria[0]],
            "unknown": criteria
            + [
                {
                    **criteria[0].model_dump(),
                    "criterion_id": "fsw.work.unknown",
                }
            ],
            "unwired": [
                item.model_copy(update={"wired": False})
                if index == 0
                else item
                for index, item in enumerate(criteria)
            ],
            "unknown_status": criteria
            + [
                {
                    **criteria[0].model_dump(),
                    "status": "UNKNOWN",
                }
            ],
        }
        for name, values in cases.items():
            with self.subTest(case=name):
                self.assertEqual(rollup_program_status("fsw", values), "AT-RISK")

    def test_valid_fail_still_wins_over_manifest_errors(self) -> None:
        criteria = _complete("fst")
        criteria[0] = _criterion(criteria[0].criterion_id, "FAIL")
        self.assertEqual(
            rollup_program_status("fst", criteria[1:] + [criteria[0], criteria[0]]),
            "DOES-NOT-MEET",
        )

    def test_na_requires_manifest_declaration_and_grounded_inapplicability(self) -> None:
        declared = "fsw.funds.requirement"
        for grounded, applicable in (
            (False, False),
            (True, True),
            (True, None),
        ):
            with self.subTest(grounded=grounded, applicable=applicable):
                raw = _criterion(declared, "N/A").model_dump(mode="json")
                raw.update(
                    applicability_grounded=grounded,
                    applicable=applicable,
                )
                with self.assertRaises(ValidationError):
                    PrivateMecCriterion.model_validate(raw)

        for grounded, applicable, expected in ((True, False, "AT-RISK"),):
            criteria = _complete("fsw")
            index = next(
                i for i, item in enumerate(criteria) if item.criterion_id == declared
            )
            criteria[index] = _criterion(
                declared,
                "N/A",
                applicability_grounded=grounded,
                applicable=applicable,
            )
            with self.subTest(grounded=grounded, applicable=applicable):
                self.assertEqual(
                    rollup_program_status("fsw", criteria),
                    expected,
                )

    def test_private_schema_rejects_paths_rogue_keys_and_wrong_nested_types(self) -> None:
        clean = _criterion("cec.work.paid").model_dump(mode="json")
        mutations = (
            ("posix", lambda raw: raw["evidence_ids"].append("/etc/passwd")),
            ("drive", lambda raw: raw["evidence_ids"].append(r"C:\private\db")),
            ("unc", lambda raw: raw["evidence_ids"].append(r"\\server\share")),
            ("traversal", lambda raw: raw["evidence_ids"].append("../secret")),
            ("uri", lambda raw: raw["evidence_ids"].append("file:///etc/passwd")),
            (
                "rogue_key",
                lambda raw: raw["sidecar_inputs"].update(
                    {"rogue": {"nested": "value"}}
                ),
            ),
            (
                "wrong_type",
                lambda raw: raw["employment_traces"].append(
                    {
                        "employment_period_id": "mep_" + "1" * 32,
                        "included": [],
                        "reason": "predicate_satisfied",
                    }
                ),
            ),
        )
        for label, mutate in mutations:
            raw = json.loads(json.dumps(clean))
            mutate(raw)
            with self.subTest(label=label), self.assertRaises(ValidationError):
                PrivateMecCriterion.model_validate(raw)

        criteria = _complete("fsw")
        criteria[0] = _criterion(
            criteria[0].criterion_id,
            "N/A",
            applicability_grounded=True,
            applicable=False,
        )
        self.assertEqual(rollup_program_status("fsw", criteria), "AT-RISK")

    def test_unknown_program_fails_closed(self) -> None:
        self.assertEqual(rollup_program_status("unknown", []), "AT-RISK")


class TestMecSnapshotGate(unittest.TestCase):
    @staticmethod
    def _snapshot(program: str = "fsw") -> crs_rules.RegistrySnapshot:
        return crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(
                rows=[
                    __import__(
                        "crawler.tests.test_mec_rules",
                        fromlist=["_row"],
                    )._row(spec.criterion_id)
                    for spec in MEC_PROGRAM_CRITERIA[program]
                ]
            ),
        )

    def test_prepare_gate_preserves_snapshot_identity_and_uses_shared_gate(self) -> None:
        snapshot = self._snapshot()
        with (
            mock.patch(
                "crawler.auditor.gate_subset",
                return_value=None,
            ) as shared_gate,
            mock.patch(
                "crawler.mec_screen.crs_rules.load_registry_snapshot",
                side_effect=AssertionError("MEC must not reload the registry"),
            ) as loader,
            mock.patch(
                "crawler.mec_screen.crs_rules.registry_fingerprint",
                side_effect=AssertionError("MEC must not recompute the fingerprint"),
            ) as fingerprint,
            mock.patch(
                "crawler.mec_screen.crs_audit.row_in_effect",
                return_value=True,
            ) as in_effect,
            mock.patch(
                "crawler.mec_screen.snapshot_policy.mec_rule_row_is_fresh",
                return_value=True,
            ) as fresh,
        ):
            context = prepare_mec_gate(
                "fsw",
                snapshot,
                "corpus/index.db",
                date(2026, 7, 20),
                45,
            )

        self.assertIs(context.registry_snapshot, snapshot)
        self.assertEqual(
            context.registry_snapshot.registry.model_dump(mode="json"),
            snapshot.registry.model_dump(mode="json"),
        )
        self.assertEqual(context.registry_fingerprint, snapshot.fingerprint)
        self.assertEqual(context.reference_date, date(2026, 7, 20))
        self.assertEqual(context.max_age_days, 45)
        self.assertEqual(
            tuple(row.rule_id for row in context.selected_rows),
            crs_rules.REQUIRED_MEC_RULE_IDS["fsw"],
        )
        self.assertTrue(all(item.usable for item in context.row_usability))
        loader.assert_not_called()
        fingerprint.assert_not_called()
        shared_gate.assert_called_once()
        self.assertEqual(in_effect.call_count, len(context.selected_rows))
        self.assertEqual(fresh.call_count, len(context.selected_rows))
        with self.assertRaises(FrozenInstanceError):
            context.max_age_days = 90

    def test_prepare_gate_records_effectivity_and_freshness_per_row(self) -> None:
        snapshot = self._snapshot("cec")
        with (
            mock.patch("crawler.mec_screen.auditor.gate_subset"),
            mock.patch(
                "crawler.mec_screen.crs_audit.row_in_effect",
                side_effect=[False] + [True] * (len(snapshot.registry.rows) - 1),
            ),
            mock.patch(
                "crawler.mec_screen.snapshot_policy.mec_rule_row_is_fresh",
                side_effect=[True, False] + [True] * (len(snapshot.registry.rows) - 2),
            ),
        ):
            context = prepare_mec_gate(
                "cec", snapshot, "unused.db", "2026-07-20", 30
            )
        self.assertEqual(context.row_usability[0].reason, "rule_out_of_window")
        self.assertEqual(context.row_usability[1].reason, "rule_stale")
        self.assertTrue(all(item.usable for item in context.row_usability[2:]))

    def test_effectivity_uses_candidate_reference_while_freshness_uses_as_of(
        self,
    ) -> None:
        snapshot = self._snapshot("cec")
        with (
            mock.patch("crawler.mec_screen.auditor.gate_subset"),
            mock.patch(
                "crawler.mec_screen.crs_audit.row_in_effect", return_value=True
            ) as effective,
            mock.patch(
                "crawler.mec_screen.snapshot_policy.mec_rule_row_is_fresh",
                return_value=True,
            ) as fresh,
        ):
            context = prepare_mec_gate(
                "cec",
                snapshot,
                "unused.db",
                date(2024, 5, 1),
                90,
                as_of=date(2026, 7, 20),
            )
        self.assertTrue(
            all(
                call.args[1] == date(2024, 5, 1)
                for call in effective.call_args_list
            )
        )
        self.assertTrue(
            all(
                call.args[1] == date(2026, 7, 20)
                for call in fresh.call_args_list
            )
        )
        self.assertEqual(context.reference_date, date(2024, 5, 1))
        self.assertEqual(context.operational_as_of, date(2026, 7, 20))

    def test_candidate_reference_requires_confirmed_anchor_and_valid_chronology(
        self,
    ) -> None:
        base = {
            "candidate_id": "candidate",
            "registry_fingerprint": "a" * 64,
            "scalar_evidence_ids": {},
            "periods": (),
        }
        reference = mecfields.eligibility_reference_date(
            MecEvidence(
                **base,
                scalars={
                    "application_date": "2024-05-01",
                    "eligibility_reference_date": "2024-06-01",
                    "ita_date": "2024-04-01",
                },
            )
        )
        self.assertEqual(reference, date(2024, 6, 1))
        fallback = mecfields.eligibility_reference_date(
            MecEvidence(
                **base,
                scalars={"ita_date": "2024-04-01"},
            )
        )
        self.assertEqual(fallback, date(2024, 4, 1))
        for evidence in (
            MecEvidence(**base, scalars={}),
            MecEvidence(
                **base,
                scalars={"eligibility_reference_date": "2024-01-01"},
                conflicts=frozenset({"eligibility_reference_date"}),
            ),
            MecEvidence(
                **base,
                scalars={
                    "application_date": "2024-06-01",
                    "eligibility_reference_date": "2024-05-01",
                },
            ),
        ):
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                mecfields.eligibility_reference_date(evidence)

    def test_prepare_gate_rejects_invalid_config_and_unwired_manifest(self) -> None:
        snapshot = self._snapshot("fst")
        missing = crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(rows=snapshot.registry.rows[1:]),
        )
        for args in (
            ("unknown", snapshot, "unused.db", "2026-07-20", 30),
            ("fst", snapshot, "unused.db", None, 30),
            ("fst", snapshot, "unused.db", "2026-07-20", 0),
            ("fst", missing, "unused.db", "2026-07-20", 30),
        ):
            with self.subTest(args=args), self.assertRaises(MecGatePreparationError):
                prepare_mec_gate(*args)


class TestFswEvaluator(unittest.TestCase):
    @staticmethod
    def _context() -> object:
        snapshot = crs_rules.load_registry_snapshot()
        rows = tuple(
            row for row in snapshot.registry.rows
            if row.rule_id in crs_rules.REQUIRED_MEC_RULE_IDS["fsw"]
        )
        from crawler.mec_screen import MecGateContext, MecRowUsability

        return MecGateContext(
            registry_snapshot=snapshot,
            registry_fingerprint=snapshot.fingerprint,
            selected_rows=rows,
            reference_date=date(2026, 7, 20),
            operational_as_of=date(2026, 7, 20),
            max_age_days=90,
            row_usability=tuple(
                MecRowUsability(row=row, usable=True, reason="usable")
                for row in rows
            ),
        )

    @staticmethod
    def _evidence(periods=(), **scalars) -> MecEvidence:
        return MecEvidence(
            candidate_id="candidate",
            registry_fingerprint=crs_rules.load_registry_snapshot().fingerprint,
            scalars=scalars,
            scalar_evidence_ids={name: (f"val_{index}",)
                                 for index, name in enumerate(scalars)},
            periods=tuple(periods),
        )

    @staticmethod
    def _period(period_id: str, **values) -> EmploymentPeriod:
        return EmploymentPeriod(
            employment_period_id=period_id,
            document_id=f"doc_{period_id}",
            values=values,
            evidence_ids=(f"val_{period_id}",),
        )

    @staticmethod
    def _inputs() -> ConfirmedMecInputs:
        return ConfirmedMecInputs(
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
                "level": "masters",
            },
            age_years=35,
            adaptability_labels=(),
        )

    def test_fsw_never_joins_paid_hours_and_noc_across_periods(self) -> None:
        periods = (
            self._period(
                "mep_" + "1" * 32,
                noc_code="21231",
                teer=1,
                employment_start="2025-01-01",
                employment_end="2025-12-31",
                employment_continuous=True,
            ),
            self._period(
                "mep_" + "2" * 32,
                noc_code="00000",
                paid_status=True,
                total_hours=2000,
                hours_per_week=30,
                duration_months=12,
            ),
        )
        criteria = evaluate_fsw(
            self._context(),
            self._evidence(
                periods,
                primary_noc_code="21231",
                work_history_scope_complete=True,
                intended_destination_province="ON",
            ),
            self._inputs(),
        )
        by_id = {item.criterion_id: item for item in criteria}
        self.assertEqual(by_id["fsw.work.continuity_duration_hours"].status, "AT-RISK")
        self.assertTrue(
            all(
                trace.get("employment_period_id") in {
                    "mep_" + "1" * 32,
                    "mep_" + "2" * 32,
                }
                for item in criteria
                for trace in item.employment_traces
            )
        )

    def test_fsw_funds_amount_is_never_compared_and_exemption_is_grounded(self) -> None:
        evidence = self._evidence(
            funds_household_size=99,
            funds_amount="999999999",
            funds_accessible=True,
            funds_borrowed=False,
            funds_real_property_equity=False,
        )
        normal = {
            item.criterion_id: item
            for item in evaluate_fsw(self._context(), evidence, self._inputs())
        }["fsw.funds.requirement"]
        self.assertEqual(
            (normal.status, normal.reason_code),
            ("AT-RISK", "funds_snapshot_unavailable"),
        )
        forged_inputs = self._inputs()
        object.__setattr__(
            forged_inputs,
            "offer_validation",
            MecOfferValidation(
                status="PASS",
                program="fsw",
                selected_noc="21231",
                reason="grounded_offer_satisfied",
                rule_ids=("fsw.grid.arranged_employment",),
            ),
        )
        exempt_evidence = self._evidence(
            legally_authorized_to_work_canada=True,
            currently_working_in_canada=False,
            funds_amount="0",
        )
        exempt = {
            item.criterion_id: item
            for item in evaluate_fsw(
                self._context(), exempt_evidence, forged_inputs
            )
        }["fsw.funds.requirement"]
        self.assertEqual(
            (exempt.status, exempt.reason_code),
            ("AT-RISK", "funds_snapshot_unavailable"),
        )
        self.assertTrue(exempt.applicability_grounded)
        self.assertTrue(exempt.applicable)
        self.assertNotIn(
            exempt_evidence.scalar_evidence_ids["currently_working_in_canada"][0],
            exempt.evidence_ids,
        )

        unauthorized = {
            item.criterion_id: item
            for item in evaluate_fsw(
                self._context(),
                self._evidence(
                    legally_authorized_to_work_canada=False,
                    currently_working_in_canada=False,
                ),
                forged_inputs,
            )
        }["fsw.funds.requirement"]
        self.assertEqual(
            (unauthorized.status, unauthorized.reason_code),
            ("AT-RISK", "funds_snapshot_unavailable"),
        )

    def test_fsw_offer_points_are_separate_from_funds_exemption(self) -> None:
        evidence = self._evidence(
            offer_certificate_scope_complete=True,
            offer_status="valid",
        )
        validated = self._inputs()
        object.__setattr__(
            validated,
            "offer_validation",
            MecOfferValidation(
                status="PASS",
                program="fsw",
                selected_noc="21231",
                reason="grounded_offer_satisfied",
                rule_ids=("fsw.grid.arranged_employment",),
            ),
        )
        results = {
            item.criterion_id: item
            for item in evaluate_fsw(self._context(), evidence, validated)
        }
        self.assertEqual(
            (
                results["fsw.grid.arranged_employment"].status,
                results["fsw.grid.arranged_employment"].reason_code,
            ),
            ("AT-RISK", "manual_offer_review"),
        )
        self.assertEqual(results["fsw.funds.requirement"].status, "AT-RISK")

        unresolved = {
            item.criterion_id: item
            for item in evaluate_fsw(
                self._context(),
                evidence,
                self._inputs(),
            )
        }["fsw.grid.arranged_employment"]
        self.assertEqual(
            (unresolved.status, unresolved.reason_code),
            ("AT-RISK", "manual_offer_review"),
        )

    def test_fsw_complete_offer_evidence_stays_manual_and_cannot_exempt_funds(
        self,
    ) -> None:
        context = self._context()
        row = next(
            item.row
            for item in context.row_usability
            if item.row.rule_id == "fsw.grid.arranged_employment"
        )
        evidence = self._evidence(
            offer_certificate_scope_complete=True,
            adaptability_scope_complete=True,
            legally_authorized_to_work_canada=True,
            offer_branch="situation_1",
            offer_full_time=True,
            offer_continuous=True,
            offer_paid_status=True,
            offer_non_seasonal=True,
            offer_duration_months=12,
            offer_noc_code="21231",
            offer_teer=1,
            offer_country="CA",
            offer_employer_count=1,
            offer_status="valid",
            offer_valid_from="2026-01-01",
            offer_valid_until="2027-01-01",
            current_work_permit_status="valid",
            offer_permit_valid_at_visa_issuance=True,
            offer_work_permit_basis="lmia",
            offer_lmia_status="positive",
            currently_working_in_canada=True,
            currently_working_for_offer_employer=True,
            offer_employer_matches_work_permit=True,
        )
        validation = _validate_mec_offer(
            "fsw", row, evidence, date(2026, 7, 20)
        )
        self.assertEqual(
            (validation.status, validation.reason),
            ("AT-RISK", "officer_determination_unavailable"),
        )
        results = {
            item.criterion_id: item
            for item in evaluate_fsw(context, evidence, self._inputs())
        }
        offer = results["fsw.grid.arranged_employment"]
        self.assertEqual(
            (offer.status, offer.reason_code),
            ("AT-RISK", "manual_offer_review"),
        )
        self.assertEqual(
            (offer.grid_bounds.lower, offer.grid_bounds.upper),
            (0, 10),
        )
        adaptability = results["fsw.grid.adaptability"]
        self.assertEqual(
            (adaptability.status, adaptability.reason_code),
            ("AT-RISK", "manual_offer_review"),
        )
        self.assertEqual(
            (
                results["fsw.funds.requirement"].status,
                results["fsw.funds.requirement"].reason_code,
            ),
            ("AT-RISK", "funds_snapshot_unavailable"),
        )

    def test_fsw_imported_situation_facts_are_diagnostic_only(self) -> None:
        context = self._context()
        row = next(
            item.row
            for item in context.row_usability
            if item.row.rule_id == "fsw.grid.arranged_employment"
        )
        evidence = self._evidence(
            offer_branch="situation_3",
            offer_full_time=True,
            offer_continuous=True,
            offer_paid_status=True,
            offer_non_seasonal=True,
            offer_duration_months=12,
            offer_noc_code="21231",
            offer_teer=1,
            offer_country="CA",
            offer_employer_count=1,
            offer_status="valid",
            offer_valid_from="2026-01-01",
            offer_valid_until="2027-01-01",
            current_work_permit_status="none",
            plans_work_before_pr=False,
            offer_lmia_status="positive",
        )
        validation = _validate_mec_offer(
            "fsw", row, evidence, date(2026, 7, 20)
        )
        result = {
            item.criterion_id: item
            for item in evaluate_fsw(context, evidence, self._inputs())
        }["fsw.grid.arranged_employment"]
        self.assertEqual(
            (validation.status, validation.reason, validation.selected_branch),
            ("AT-RISK", "officer_determination_unavailable", None),
        )
        self.assertEqual(
            (result.status, result.reason_code),
            ("AT-RISK", "manual_offer_review"),
        )

    def test_fsw_experience_grid_requires_complete_dated_capped_work(self) -> None:
        incomplete = self._period(
            "mep_" + "8" * 32,
            noc_code="21231",
            teer=1,
            paid_status=True,
            duration_months=72,
        )
        incomplete_result = {
            item.criterion_id: item
            for item in evaluate_fsw(
                self._context(),
                self._evidence(
                    (incomplete,),
                    primary_noc_code="21231",
                    work_history_scope_complete=True,
                ),
                self._inputs(),
            )
        }["fsw.grid.experience"]
        self.assertEqual(
            (incomplete_result.status, incomplete_result.reason_code),
            ("AT-RISK", "evidence_missing"),
        )

        start = date(2019, 7, 20)
        end = date(2025, 7, 20)
        days = (end - start).days + 1
        complete = self._period(
            "mep_" + "9" * 32,
            noc_code="21231",
            teer=1,
            paid_status=True,
            employment_continuous=True,
            employment_start=start.isoformat(),
            employment_end=end.isoformat(),
            duration_months=72,
            total_hours=30 * days / 7,
            hours_per_week=30,
        )
        complete_result = {
            item.criterion_id: item
            for item in evaluate_fsw(
                self._context(),
                self._evidence(
                    (complete,),
                    primary_noc_code="21231",
                    work_history_scope_complete=True,
                ),
                self._inputs(),
            )
        }["fsw.grid.experience"]
        self.assertEqual(complete_result.status, "PASS")
        self.assertEqual(complete_result.applicant_values.points, 15)

    def test_fsw_rule_unusable_grid_bounds_and_fail_precedence(self) -> None:
        context = self._context()
        first = context.row_usability[0]
        stale_context = context.__class__(
            registry_snapshot=context.registry_snapshot,
            registry_fingerprint=context.registry_fingerprint,
            selected_rows=context.selected_rows,
            reference_date=context.reference_date,
            max_age_days=context.max_age_days,
            row_usability=(
                first.__class__(row=first.row, usable=False, reason="rule_stale"),
                *context.row_usability[1:],
            ),
        )
        criteria = evaluate_fsw(
            stale_context,
            self._evidence(
                work_history_scope_complete=True,
                intended_destination_province="QC",
            ),
            self._inputs().with_updates(age_years=None),
        )
        by_id = {item.criterion_id: item for item in criteria}
        self.assertEqual(by_id[first.row.rule_id].reason_code, "rule_stale")
        self.assertEqual(by_id["fsw.destination.outside_quebec"].status, "FAIL")
        self.assertEqual(by_id["fsw.grid.age"].status, "AT-RISK")
        self.assertLessEqual(
            by_id["fsw.grid.age"].grid_bounds["lower"],
            by_id["fsw.grid.age"].grid_bounds["upper"],
        )
        self.assertEqual(
            rollup_program_status("fsw", criteria),
            "DOES-NOT-MEET",
        )


class TestFstCecAndBundle(TestFswEvaluator):
    @staticmethod
    def _program_context(program: str) -> object:
        snapshot = crs_rules.load_registry_snapshot()
        rows = tuple(
            row for row in snapshot.registry.rows
            if row.rule_id in crs_rules.REQUIRED_MEC_RULE_IDS[program]
        )
        from crawler.mec_screen import MecGateContext, MecRowUsability

        return MecGateContext(
            registry_snapshot=snapshot,
            registry_fingerprint=snapshot.fingerprint,
            selected_rows=rows,
            reference_date=date(2026, 7, 20),
            operational_as_of=date(2026, 7, 20),
            max_age_days=90,
            row_usability=tuple(
                MecRowUsability(row=row, usable=True, reason="usable")
                for row in rows
            ),
        )

    def test_confirmed_input_adapter_carries_all_grounded_input_classes(self) -> None:
        context = self._program_context("fsw")
        evidence = self._evidence(
            fsw_education_branch="canadian_secondary_or_post_secondary_credential",
            offer_full_time=True,
            offer_continuous=True,
            offer_non_seasonal=True,
            offer_paid_status=True,
            offer_duration_months=12,
            offer_noc_code="21231",
            offer_teer=1,
            offer_country="CA",
            offer_employer_count=1,
            offer_status="valid",
            offer_valid_from="2026-01-01",
            offer_valid_until="2027-01-01",
            offer_branch="situation_1",
            current_work_permit_status="valid",
            offer_permit_valid_at_visa_issuance=True,
            offer_work_permit_basis="lmia",
            offer_lmia_status="positive",
            currently_working_in_canada=True,
            currently_working_for_offer_employer=True,
            offer_employer_matches_work_permit=True,
            legally_authorized_to_work_canada=True,
        )
        card_values = {
            "core.language.first": {
                "test_date": "2026-01-01",
                "benchmarks": {
                    "listening": 9,
                    "reading": 9,
                    "writing": 9,
                    "speaking": 9,
                },
            },
            "core.age": {"age_on_ita": 35},
            "core.education": {"credential_level": "secondary"},
            "core.work": {"aggregated_years": 1.0},
            "spouse.language": {
                "benchmarks": {
                    "listening": 4,
                    "reading": 4,
                    "writing": 4,
                    "speaking": 4,
                }
            },
            "additional.sibling": {},
        }

        def card(_vault, factor_id, *_args, **_kwargs):
            values = card_values.get(factor_id)
            return SimpleNamespace(
                verdict="SUBSTANTIATED" if values is not None else "N/A",
                confirmed_value=values,
            )

        with (
            mock.patch("crawler.vault.load_profile_factors", return_value=[]),
            mock.patch("crawler.mec_screen.auditor.audit_one", side_effect=card),
        ):
            inputs = build_confirmed_mec_inputs(
                "fsw", context, evidence, object(), "unused.db"
            )

        self.assertEqual(inputs.language["first"]["clb_listening"], 9)
        self.assertEqual(inputs.education["level"], "secondary")
        self.assertEqual(
            inputs.education["branch"],
            "canadian_secondary_or_post_secondary_credential",
        )
        self.assertEqual(inputs.age_years, 35)
        self.assertEqual(
            set(inputs.adaptability_labels),
            {
                "applicant_work",
                "relative",
                "spouse_language",
            },
        )
        self.assertNotIn("offer_validation", inputs.__dict__)

    def test_fst_structural_hierarchy_same_noc_and_certificate_or(self) -> None:
        periods = (
            self._period(
                "mep_" + "3" * 32,
                noc_code="72600",
                paid_status=True,
                student_status=False,
                qualified_to_practise=True,
                duration_months=24,
                total_hours=30 * 731 / 7,
                hours_per_week=30,
                employment_start="2024-01-02",
                employment_end="2026-01-01",
            ),
            self._period(
                "mep_" + "4" * 32,
                noc_code="72200",
                paid_status=True,
                student_status=False,
                qualified_to_practise=True,
                duration_months=24,
                total_hours=30 * 731 / 7,
                hours_per_week=30,
                employment_start="2024-01-02",
                employment_end="2026-01-01",
            ),
        )
        evidence = self._evidence(
            periods,
            work_history_scope_complete=True,
            offer_certificate_scope_complete=True,
            trade_certificate_authority="Synthetic authority",
            trade_certificate_jurisdiction="ON",
            trade_certificate_noc_code="72200",
            trade_certificate_status="valid",
            trade_certificate_issue_date="2025-01-01",
            trade_certificate_expiry_date="2027-01-01",
            intended_destination_province="ON",
        )
        criteria = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                evidence,
                self._inputs(),
            )
        }
        self.assertEqual(criteria["fst.work.trade_noc"].status, "PASS")
        self.assertEqual(criteria["fst.offer_or_certificate"].status, "PASS")
        traces = criteria["fst.work.trade_noc"].employment_traces
        self.assertFalse(next(t for t in traces if t["employment_period_id"].endswith("3" * 32))["included"])

        mixed = tuple(
            self._period(
                "mep_" + str(index) * 32,
                noc_code=noc,
                paid_status=True,
                student_status=False,
                qualified_to_practise=True,
                duration_months=12,
                total_hours=2000,
                hours_per_week=30,
                employment_end="2026-01-01",
            )
            for index, noc in ((5, "72200"), (6, "72300"))
        )
        mixed_results = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                self._evidence(mixed, work_history_scope_complete=True),
                self._inputs(),
            )
        }
        self.assertNotEqual(
            mixed_results["fst.work.recency_duration_hours"].status,
            "PASS",
        )

    def test_fst_certificate_requires_current_exact_selected_trade_match(self) -> None:
        period = self._period(
            "mep_" + "7" * 32,
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
        base = {
            "work_history_scope_complete": True,
            "offer_certificate_scope_complete": True,
            "trade_certificate_authority": "Ontario authority",
            "trade_certificate_jurisdiction": "ON",
            "trade_certificate_status": "valid",
            "trade_certificate_issue_date": "2025-01-01",
            "trade_certificate_expiry_date": "2027-01-01",
        }
        statuses = {}
        for label, values in (
            ("matching", {**base, "trade_certificate_noc_code": "72200"}),
            ("unrelated", {**base, "trade_certificate_noc_code": "11111"}),
            (
                "expired",
                {
                    **base,
                    "trade_certificate_noc_code": "72200",
                    "trade_certificate_expiry_date": "2026-01-01",
                },
            ),
            (
                "missing_dates",
                {
                    key: value
                    for key, value in {
                        **base,
                        "trade_certificate_noc_code": "72200",
                    }.items()
                    if key
                    not in {
                        "trade_certificate_issue_date",
                        "trade_certificate_expiry_date",
                    }
                },
            ),
        ):
            result = {
                item.criterion_id: item
                for item in evaluate_fst(
                    self._program_context("fst"),
                    self._evidence((period,), **values),
                    self._inputs(),
                )
            }["fst.offer_or_certificate"]
            statuses[label] = result.status
        self.assertEqual(
            statuses,
            {
                "matching": "PASS",
                "unrelated": "AT-RISK",
                "expired": "AT-RISK",
                "missing_dates": "AT-RISK",
            },
        )

    def test_fst_certificate_requires_confirmed_complete_conflict_free_scope(
        self,
    ) -> None:
        period = self._period(
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
            "trade_certificate_authority": "Ontario authority",
            "trade_certificate_jurisdiction": "ON",
            "trade_certificate_noc_code": "72200",
            "trade_certificate_status": "valid",
            "trade_certificate_issue_date": "2025-01-01",
            "trade_certificate_expiry_date": "2027-01-01",
        }
        cases = (
            ("missing_scope", certificate, frozenset(), "AT-RISK", False),
            (
                "false_scope",
                {**certificate, "offer_certificate_scope_complete": False},
                frozenset(),
                "AT-RISK",
                False,
            ),
            (
                "conflicted_scope",
                {**certificate, "offer_certificate_scope_complete": True},
                frozenset({"offer_certificate_scope_complete"}),
                "AT-RISK",
                False,
            ),
            (
                "conflicted_field",
                {**certificate, "offer_certificate_scope_complete": True},
                frozenset({"trade_certificate_authority"}),
                "AT-RISK",
                True,
            ),
            (
                "complete",
                {**certificate, "offer_certificate_scope_complete": True},
                frozenset(),
                "PASS",
                True,
            ),
        )
        for label, scalars, conflicts, expected_status, expected_complete in cases:
            evidence = replace(
                self._evidence(
                    (period,),
                    work_history_scope_complete=True,
                    **scalars,
                ),
                conflicts=conflicts,
            )
            result = {
                item.criterion_id: item
                for item in evaluate_fst(
                    self._program_context("fst"),
                    evidence,
                    self._inputs(),
                )
            }["fst.offer_or_certificate"]
            with self.subTest(label=label):
                self.assertEqual(result.status, expected_status)
                self.assertEqual(
                    result.completeness_attestations.offer_certificate,
                    expected_complete,
                )
                if expected_status == "PASS":
                    self.assertIn(
                        evidence.scalar_evidence_ids[
                            "offer_certificate_scope_complete"
                        ][0],
                        result.evidence_ids,
                    )

    def test_screen_mec_preserves_certificate_scope_gate_and_attestation(
        self,
    ) -> None:
        period = self._period(
            "mep_" + "c" * 32,
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
        for scope, expected in ((None, "AT-RISK"), (True, "PASS")):
            scalars = dict(certificate)
            if scope is not None:
                scalars["offer_certificate_scope_complete"] = scope
            bundle = screen_mec(
                "fst",
                self._program_context("fst"),
                self._evidence((period,), **scalars),
                self._inputs(),
                run_id="mec_deadbeef0014deadbeef0014deadbeef",
                created_at="2026-07-20T00:00:00Z",
            )
            private = next(
                item
                for item in bundle.private_report.criteria
                if item.criterion_id == "fst.offer_or_certificate"
            )
            public = next(
                item
                for item in bundle.public_summary.criteria
                if item.criterion_id == "fst.offer_or_certificate"
            )
            with self.subTest(scope=scope):
                self.assertEqual(private.status, expected)
                self.assertEqual(public.status, expected)
                self.assertEqual(
                    private.completeness_attestations.offer_certificate,
                    scope is True,
                )

    def test_fst_certificate_cannot_bind_to_short_unrelated_trade(self) -> None:
        def trade_period(
            token: str,
            noc: str,
            start: str,
            end: str,
            months: int,
        ) -> EmploymentPeriod:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
            return self._period(
                "mep_" + token * 32,
                noc_code=noc,
                paid_status=True,
                student_status=False,
                qualified_to_practise=True,
                employment_start=start,
                employment_end=end,
                duration_months=months,
                total_hours=30 * days / 7,
                hours_per_week=30,
            )

        periods = (
            trade_period("1", "72200", "2024-01-01", "2025-12-31", 24),
            trade_period("2", "72300", "2025-12-01", "2025-12-31", 1),
        )
        result = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                self._evidence(
                    periods,
                    work_history_scope_complete=True,
                    offer_certificate_scope_complete=True,
                    trade_certificate_authority="Ontario authority",
                    trade_certificate_jurisdiction="ON",
                    trade_certificate_noc_code="72300",
                    trade_certificate_status="valid",
                    trade_certificate_issue_date="2025-01-01",
                    trade_certificate_expiry_date="2027-01-01",
                ),
                self._inputs(),
            )
        }["fst.offer_or_certificate"]
        self.assertEqual(result.status, "AT-RISK")

        both_qualify = (
            trade_period("3", "72200", "2022-01-01", "2023-12-31", 24),
            trade_period("4", "72300", "2024-01-01", "2025-12-31", 24),
        )
        matching_any_qualifying = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                self._evidence(
                    both_qualify,
                    work_history_scope_complete=True,
                    offer_certificate_scope_complete=True,
                    trade_certificate_authority="Ontario authority",
                    trade_certificate_jurisdiction="ON",
                    trade_certificate_noc_code="72300",
                    trade_certificate_status="valid",
                    trade_certificate_issue_date="2025-01-01",
                    trade_certificate_expiry_date="2027-01-01",
                ),
                self._inputs(),
            )
        }["fst.offer_or_certificate"]
        self.assertEqual(matching_any_qualifying.status, "PASS")

    def test_period_calendar_union_prevents_identical_nested_and_partial_overlap(
        self,
    ) -> None:
        def period(token: str, start: str, end: str) -> EmploymentPeriod:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            days = (end_date - start_date).days + 1
            return self._period(
                "mep_" + token * 32,
                noc_code="72200",
                paid_status=True,
                student_status=False,
                qualified_to_practise=True,
                employment_start=start,
                employment_end=end,
                duration_months=12,
                total_hours=30 * days / 7,
                hours_per_week=30,
            )

        overlap_cases = (
            (
                period("a", "2024-01-01", "2024-12-31"),
                period("b", "2024-01-01", "2024-12-31"),
            ),
            (
                period("c", "2024-01-01", "2024-12-31"),
                period("d", "2024-03-01", "2024-09-30"),
            ),
            (
                period("e", "2024-01-01", "2024-12-31"),
                period("f", "2024-07-01", "2025-06-30"),
            ),
        )
        for periods in overlap_cases:
            result = {
                item.criterion_id: item
                for item in evaluate_fst(
                    self._program_context("fst"),
                    self._evidence(periods, work_history_scope_complete=True),
                    self._inputs(),
                )
            }["fst.work.recency_duration_hours"]
            with self.subTest(periods=tuple(p.employment_period_id for p in periods)):
                self.assertNotEqual(result.status, "PASS")

        non_overlapping = (
            period("1", "2024-01-01", "2024-12-31"),
            period("2", "2025-01-01", "2025-12-31"),
        )
        result = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                self._evidence(non_overlapping, work_history_scope_complete=True),
                self._inputs(),
            )
        }["fst.work.recency_duration_hours"]
        self.assertEqual(result.status, "PASS")

    def test_calendar_anniversary_threshold_handles_leap_and_partial_months(
        self,
    ) -> None:
        def period(token: str, start: str, end: str, months: int) -> EmploymentPeriod:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
            return self._period(
                "mep_" + token * 32,
                noc_code="72200",
                paid_status=True,
                student_status=False,
                qualified_to_practise=True,
                employment_start=start,
                employment_end=end,
                duration_months=months,
                total_hours=30 * days / 7,
                hours_per_week=30,
            )

        cases = (
            ("leap_anniversary", period("a", "2024-02-29", "2026-02-28", 24), "PASS"),
            (
                "partial_month",
                period("b", "2024-03-01", "2026-02-27", 23),
                "FAIL",
            ),
        )
        for label, candidate, expected in cases:
            result = {
                item.criterion_id: item
                for item in evaluate_fst(
                    self._program_context("fst"),
                    self._evidence((candidate,), work_history_scope_complete=True),
                    self._inputs(),
                )
            }["fst.work.recency_duration_hours"]
            with self.subTest(label=label):
                self.assertEqual(result.status, expected)

    def test_program_lookbacks_clip_straddling_intervals_at_exact_cutoff(self) -> None:
        reference = date(2026, 7, 20)

        def period(
            token: str,
            start: date,
            end: date,
            *,
            program: str,
        ) -> EmploymentPeriod:
            days = (end - start).days + 1
            exclusive_end = end + timedelta(days=1)
            months = (
                (exclusive_end.year - start.year) * 12
                + exclusive_end.month
                - start.month
            )
            month_index = start.month - 1 + months
            anniversary_year, month_offset = divmod(month_index, 12)
            anniversary_month = month_offset + 1
            next_month = (
                date(start.year + anniversary_year + 1, 1, 1)
                if anniversary_month == 12
                else date(
                    start.year + anniversary_year,
                    anniversary_month + 1,
                    1,
                )
            )
            anniversary = date(
                start.year + anniversary_year,
                anniversary_month,
                min(start.day, (next_month - timedelta(days=1)).day),
            )
            if anniversary > exclusive_end:
                months -= 1
            common = {
                "noc_code": "72200" if program == "fst" else "21231",
                "paid_status": True,
                "student_status": False,
                "employment_start": start.isoformat(),
                "employment_end": end.isoformat(),
                "duration_months": max(months, 0),
                "total_hours": 30 * days / 7,
                "hours_per_week": 30,
            }
            if program == "fsw":
                common.update(teer=1, employment_continuous=True)
            elif program == "fst":
                common.update(qualified_to_practise=True)
            else:
                common.update(
                    teer=1,
                    self_employed=False,
                    work_country="CA",
                    work_province="ON",
                    physically_in_canada=True,
                    is_remote=False,
                    work_authorized=True,
                    temporary_resident_status="valid",
                )
            return self._period("mep_" + token * 32, **common)

        cases = (
            ("fsw", 10, "fsw.work.continuity_duration_hours", evaluate_fsw),
            ("fst", 5, "fst.work.recency_duration_hours", evaluate_fst),
            ("cec", 3, "cec.work.recency_duration_hours", evaluate_cec),
        )
        for index, (program, years, criterion_id, evaluator) in enumerate(cases):
            cutoff = date(reference.year - years, reference.month, reference.day)
            candidate = period(
                str(index + 1),
                date(cutoff.year - 2, 1, 1),
                cutoff,
                program=program,
            )
            scalars = {"work_history_scope_complete": True}
            if program == "fsw":
                scalars["primary_noc_code"] = "21231"
            result = {
                item.criterion_id: item
                for item in evaluator(
                    self._program_context(program)
                    if program != "fsw"
                    else self._context(),
                    self._evidence((candidate,), **scalars),
                    self._inputs(),
                )
            }[criterion_id]
            with self.subTest(program=program):
                self.assertEqual(
                    (result.status, result.reason_code),
                    ("FAIL", "confirmed_deterministic_failure"),
                )

        combined = (
            period("a", date(2020, 1, 1), date(2024, 1, 19), program="cec"),
            period("b", date(2024, 1, 20), date(2024, 7, 19), program="cec"),
        )
        combined_result = {
            item.criterion_id: item
            for item in evaluate_cec(
                self._program_context("cec"),
                self._evidence(combined, work_history_scope_complete=True),
                self._inputs(),
            )
        }["cec.work.recency_duration_hours"]
        self.assertEqual(combined_result.status, "PASS")

        leap_context = replace(
            self._program_context("cec"),
            reference_date=date(2024, 2, 29),
            operational_as_of=date(2024, 2, 29),
        )
        leap_boundary = period(
            "c",
            date(2019, 1, 1),
            date(2021, 2, 28),
            program="cec",
        )
        leap_result = {
            item.criterion_id: item
            for item in evaluate_cec(
                leap_context,
                self._evidence(
                    (leap_boundary,),
                    work_history_scope_complete=True,
                ),
                self._inputs(),
            )
        }["cec.work.recency_duration_hours"]
        self.assertEqual(leap_result.status, "FAIL")

    def test_fragmented_cec_duration_accumulates_partial_calendar_ranges(self) -> None:
        def periods_for_days(total_days: int) -> tuple[EmploymentPeriod, ...]:
            lengths = [total_days // 5] * 5
            for index in range(total_days % 5):
                lengths[index] += 1
            periods = []
            start = date(2025, 1, 1)
            for index, length in enumerate(lengths):
                end = start + timedelta(days=length - 1)
                periods.append(
                    self._period(
                        "mep_" + f"{index + 10:x}" * 32,
                        noc_code="21231",
                        teer=1,
                        work_country="CA",
                        work_province="ON",
                        physically_in_canada=True,
                        is_remote=False,
                        work_authorized=True,
                        temporary_resident_status="valid",
                        paid_status=True,
                        student_status=False,
                        self_employed=False,
                        employment_start=start.isoformat(),
                        employment_end=end.isoformat(),
                        duration_months=max(length // 31, 0),
                        total_hours=30 * length / 7,
                        hours_per_week=30,
                    )
                )
                start = end + timedelta(days=3)
            return tuple(periods)

        statuses = {}
        for total_days in (378, 364):
            result = {
                item.criterion_id: item
                for item in evaluate_cec(
                    self._program_context("cec"),
                    self._evidence(
                        periods_for_days(total_days),
                        work_history_scope_complete=True,
                    ),
                    self._inputs(),
                )
            }["cec.work.recency_duration_hours"]
            statuses[total_days] = result.status
        self.assertEqual(statuses, {378: "PASS", 364: "FAIL"})

    def test_concurrent_cross_noc_hours_above_shared_cap_are_unresolved(self) -> None:
        def period(token: str, noc: str) -> EmploymentPeriod:
            days = (date(2025, 12, 31) - date(2024, 1, 1)).days + 1
            return self._period(
                "mep_" + token * 32,
                noc_code=noc,
                paid_status=True,
                student_status=False,
                qualified_to_practise=True,
                employment_start="2024-01-01",
                employment_end="2025-12-31",
                duration_months=24,
                total_hours=20 * days / 7,
                hours_per_week=20,
            )

        result = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                self._evidence(
                    (period("3", "72200"), period("4", "72300")),
                    work_history_scope_complete=True,
                ),
                self._inputs(),
            )
        }["fst.work.recency_duration_hours"]
        self.assertEqual((result.status, result.reason_code), ("AT-RISK", "evidence_missing"))

    def test_fst_offer_facts_remain_manual_without_a_certificate(self) -> None:
        days = (date(2025, 12, 31) - date(2024, 1, 1)).days + 1
        period = self._period(
            "mep_" + "9" * 32,
            noc_code="72200",
            paid_status=True,
            student_status=False,
            qualified_to_practise=True,
            employment_start="2024-01-01",
            employment_end="2025-12-31",
            duration_months=24,
            total_hours=30 * days / 7,
            hours_per_week=30,
        )
        evidence = self._evidence(
            (period,),
            work_history_scope_complete=True,
            offer_certificate_scope_complete=True,
            offer_status="valid",
            offer_full_time=True,
            offer_continuous=True,
            offer_paid_status=True,
            offer_duration_months=12,
            offer_employer_count=1,
            offer_noc_code="72200",
            offer_valid_from="2026-01-01",
            offer_valid_until="2027-01-01",
            funds_amount="999999999",
            funds_household_size=1,
        )
        validated = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                evidence,
                self._inputs(),
            )
        }
        self.assertEqual(
            (
                validated["fst.offer_or_certificate"].status,
                validated["fst.offer_or_certificate"].reason_code,
            ),
            ("AT-RISK", "manual_offer_review"),
        )

        bundle = screen_mec(
            "fst",
            self._program_context("fst"),
            evidence,
            self._inputs(),
            run_id="mec_deadbeef0015deadbeef0015deadbeef",
            created_at="2026-07-20T00:00:00Z",
        )
        criteria = {
            item.criterion_id: item for item in bundle.private_report.criteria
        }
        self.assertEqual(
            (criteria["fst.offer_or_certificate"].status,
             criteria["fst.offer_or_certificate"].reason_code),
            ("AT-RISK", "manual_offer_review"),
        )
        self.assertEqual(
            (criteria["fst.funds.requirement"].status,
             criteria["fst.funds.requirement"].reason_code),
            ("AT-RISK", "funds_snapshot_unavailable"),
        )

        incomplete = MecEvidence(
            **{
                **evidence.__dict__,
                "scalars": {
                    key: value
                    for key, value in evidence.scalars.items()
                    if key != "offer_employer_count"
                },
            }
        )
        incomplete_result = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                incomplete,
                self._inputs(),
            )
        }["fst.offer_or_certificate"]
        self.assertEqual(incomplete_result.status, "AT-RISK")

        false_offer = MecEvidence(
            **{
                **evidence.__dict__,
                "scalars": {**evidence.scalars, "offer_full_time": False},
            }
        )
        false_result = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"),
                false_offer,
                self._inputs(),
            )
        }["fst.offer_or_certificate"]
        self.assertEqual(false_result.status, "AT-RISK")

        for field in ("offer_continuous", "offer_paid_status"):
            for value, expected in ((None, "AT-RISK"), (False, "AT-RISK")):
                scalars = dict(evidence.scalars)
                if value is None:
                    scalars.pop(field)
                else:
                    scalars[field] = value
                changed = MecEvidence(
                    **{
                        **evidence.__dict__,
                        "scalars": scalars,
                    }
                )
                result = {
                    item.criterion_id: item
                    for item in evaluate_fst(
                        self._program_context("fst"),
                        changed,
                        self._inputs(),
                    )
                }["fst.offer_or_certificate"]
                with self.subTest(field=field, value=value):
                    self.assertEqual(result.status, expected)

    def test_offer_employer_counts_remain_diagnostic_for_manual_branches(self) -> None:
        self.assertEqual(
            mecfields.normalize_mec_field("offer_employer_count", -1),
            (None, True),
        )
        self.assertEqual(
            mecfields.normalize_mec_field("offer_employer_count", 0),
            (0, False),
        )
        fsw_context = self._context()
        fsw_row = next(
            item.row
            for item in fsw_context.row_usability
            if item.row.rule_id == "fsw.grid.arranged_employment"
        )
        fsw_common = {
            "offer_branch": "situation_3",
            "offer_full_time": True,
            "offer_continuous": True,
            "offer_paid_status": True,
            "offer_non_seasonal": True,
            "offer_duration_months": 12,
            "offer_noc_code": "21231",
            "offer_teer": 1,
            "offer_country": "CA",
            "offer_status": "valid",
            "offer_valid_from": "2026-01-01",
            "offer_valid_until": "2027-01-01",
            "current_work_permit_status": "none",
            "plans_work_before_pr": False,
            "offer_lmia_status": "positive",
        }
        for count, expected in (
            (None, "AT-RISK"),
            (0, "AT-RISK"),
            (1, "AT-RISK"),
            (2, "AT-RISK"),
        ):
            scalars = dict(fsw_common)
            if count is not None:
                scalars["offer_employer_count"] = count
            evidence = self._evidence(offer_certificate_scope_complete=True, **scalars)
            validation = _validate_mec_offer(
                "fsw",
                fsw_row,
                evidence,
                date(2026, 7, 20),
            )
            bundle = screen_mec(
                "fsw",
                fsw_context,
                evidence,
                self._inputs(),
                run_id="mec_deadbeef0016deadbeef0016deadbeef",
                created_at="2026-07-20T00:00:00Z",
            )
            result = next(
                item
                for item in bundle.private_report.criteria
                if item.criterion_id == "fsw.grid.arranged_employment"
            )
            with self.subTest(program="fsw", count=count):
                self.assertEqual(
                    validation.reason, "officer_determination_unavailable"
                )
                self.assertEqual(result.status, expected)

        fst_context = self._program_context("fst")
        period = self._period(
            "mep_" + "d" * 32,
            noc_code="72200",
            paid_status=True,
            student_status=False,
            qualified_to_practise=True,
            employment_start="2024-01-01",
            employment_end="2025-12-31",
            duration_months=24,
            total_hours=30 * 731 / 7,
            hours_per_week=30,
        )
        fst_common = {
            "work_history_scope_complete": True,
            "offer_certificate_scope_complete": True,
            "offer_full_time": True,
            "offer_continuous": True,
            "offer_paid_status": True,
            "offer_duration_months": 12,
            "offer_noc_code": "72200",
            "offer_status": "valid",
            "offer_valid_from": "2026-01-01",
            "offer_valid_until": "2027-01-01",
        }
        for count, expected in (
            (None, "AT-RISK"),
            (0, "AT-RISK"),
            (1, "AT-RISK"),
            (2, "AT-RISK"),
            (3, "AT-RISK"),
        ):
            scalars = dict(fst_common)
            if count is not None:
                scalars["offer_employer_count"] = count
            bundle = screen_mec(
                "fst",
                fst_context,
                self._evidence((period,), **scalars),
                self._inputs(),
                run_id="mec_deadbeef0017deadbeef0017deadbeef",
                created_at="2026-07-20T00:00:00Z",
            )
            result = next(
                item
                for item in bundle.private_report.criteria
                if item.criterion_id == "fst.offer_or_certificate"
            )
            with self.subTest(program="fst", count=count):
                self.assertEqual(result.status, expected)

    def test_stale_trade_hierarchy_demotes_every_period_dependent_fst_criterion(
        self,
    ) -> None:
        context = self._program_context("fst")
        stale = tuple(
            item.__class__(row=item.row, usable=False, reason="rule_stale")
            if item.row.rule_id == "fst.work.trade_noc"
            else item
            for item in context.row_usability
        )
        context = context.__class__(
            registry_snapshot=context.registry_snapshot,
            registry_fingerprint=context.registry_fingerprint,
            selected_rows=context.selected_rows,
            reference_date=context.reference_date,
            max_age_days=context.max_age_days,
            row_usability=stale,
        )
        results = {
            item.criterion_id: item
            for item in evaluate_fst(
                context,
                self._evidence(
                    work_history_scope_complete=True,
                    offer_certificate_scope_complete=True,
                ),
                self._inputs(),
            )
        }
        dependent = (
            "fst.work.paid",
            "fst.work.qualified_to_practise",
            "fst.work.student_exclusion",
            "fst.work.recency_duration_hours",
            "fst.work.same_noc",
            "fst.work.noc_duties_requirements",
            "fst.offer_or_certificate",
        )
        for criterion_id in dependent:
            with self.subTest(criterion_id=criterion_id):
                self.assertEqual(
                    (results[criterion_id].status, results[criterion_id].reason_code),
                    ("AT-RISK", "rule_stale"),
                )

    def test_cec_excludes_student_self_employment_and_requires_period_auth(self) -> None:
        split = (
            self._period(
                "mep_" + "7" * 32,
                noc_code="21231",
                teer=1,
                work_country="CA",
                work_province="ON",
                physically_in_canada=True,
                is_remote=False,
                paid_status=True,
                student_status=False,
                self_employed=False,
                duration_months=12,
                total_hours=1600,
                hours_per_week=30,
                employment_end="2026-01-01",
            ),
            self._period(
                "mep_" + "8" * 32,
                noc_code="21231",
                teer=1,
                work_authorized=True,
                temporary_resident_status="valid",
            ),
        )
        criteria = {
            item.criterion_id: item
            for item in evaluate_cec(
                self._program_context("cec"),
                self._evidence(split, work_history_scope_complete=True),
                self._inputs(),
            )
        }
        self.assertNotEqual(
            criteria["cec.work.recency_duration_hours"].status,
            "PASS",
        )

        excluded = self._period(
            "mep_" + "9" * 32,
            noc_code="21231",
            teer=1,
            work_country="CA",
            work_province="ON",
            physically_in_canada=True,
            is_remote=False,
            work_authorized=True,
            temporary_resident_status="valid",
            paid_status=True,
            student_status=True,
            self_employed=True,
            duration_months=24,
            total_hours=4000,
            hours_per_week=30,
            employment_end="2026-01-01",
        )
        excluded_results = {
            item.criterion_id: item
            for item in evaluate_cec(
                self._program_context("cec"),
                self._evidence((excluded,), work_history_scope_complete=True),
                self._inputs().with_updates(
                    sidecars={"physician_exception_claimed": True}
                ),
            )
        }
        self.assertEqual(
            excluded_results["cec.work.student_exclusion"].status,
            "FAIL",
        )
        self.assertEqual(
            excluded_results["cec.work.self_employment_exclusion"].reason_code,
            "manual_physician_review",
        )

    def test_cec_remote_work_requires_known_canadian_employer(self) -> None:
        base = {
            "noc_code": "21231",
            "teer": 1,
            "work_country": "CA",
            "work_province": "ON",
            "physically_in_canada": True,
        }
        cases = (
            ("nonremote", {**base, "is_remote": False}, "PASS"),
            (
                "remote_canadian",
                {**base, "is_remote": True, "canadian_employer_if_remote": True},
                "PASS",
            ),
            (
                "remote_foreign",
                {**base, "is_remote": True, "canadian_employer_if_remote": False},
                "FAIL",
            ),
            ("remote_unknown_employer", {**base, "is_remote": True}, "AT-RISK"),
            ("remote_applicability_unknown", base, "AT-RISK"),
            (
                "remote_outside_canada",
                {
                    **base,
                    "is_remote": True,
                    "physically_in_canada": False,
                    "canadian_employer_if_remote": True,
                },
                "FAIL",
            ),
        )
        for index, (label, values, expected) in enumerate(cases):
            result = {
                item.criterion_id: item
                for item in evaluate_cec(
                    self._program_context("cec"),
                    self._evidence(
                        (
                            self._period(
                                "mep_" + f"{index + 1:x}" * 32,
                                **values,
                            ),
                        ),
                        work_history_scope_complete=True,
                    ),
                    self._inputs(),
                )
            }["cec.work.in_canada"]
            with self.subTest(label=label):
                self.assertEqual(result.status, expected)

    def test_period_fail_requires_complete_fields_for_every_relevant_period(
        self,
    ) -> None:
        missing_teer = self._period(
            "mep_" + "a" * 32,
            noc_code="21231",
        )
        known_ineligible = self._period(
            "mep_" + "b" * 32,
            noc_code="00000",
            teer=5,
        )
        teer_results = {
            item.criterion_id: item
            for item in evaluate_cec(
                self._program_context("cec"),
                self._evidence(
                    (missing_teer, known_ineligible),
                    work_history_scope_complete=True,
                ),
                self._inputs(),
            )
        }
        self.assertEqual(teer_results["cec.work.teer"].status, "AT-RISK")
        self.assertFalse(any(item.status == "FAIL" for item in teer_results.values()))

        common = {
            "noc_code": "21231",
            "teer": 1,
            "work_country": "CA",
            "work_province": "ON",
            "physically_in_canada": True,
            "is_remote": False,
            "work_authorized": True,
            "temporary_resident_status": "valid",
        }
        missing_paid = self._period("mep_" + "c" * 32, **common)
        known_unpaid = self._period(
            "mep_" + "d" * 32,
            **common,
            paid_status=False,
        )
        paid_results = {
            item.criterion_id: item
            for item in evaluate_cec(
                self._program_context("cec"),
                self._evidence(
                    (missing_paid, known_unpaid),
                    work_history_scope_complete=True,
                ),
                self._inputs(),
            )
        }
        self.assertEqual(paid_results["cec.work.paid"].status, "AT-RISK")

        conflicted = EmploymentPeriod(
            employment_period_id="mep_" + "e" * 32,
            document_id="doc_conflicted",
            values={"noc_code": "00000", "teer": 5},
            evidence_ids=("val_conflicted",),
            issues=("period_value_conflict:teer",),
        )
        conflict_result = {
            item.criterion_id: item
            for item in evaluate_cec(
                self._program_context("cec"),
                self._evidence((conflicted,), work_history_scope_complete=True),
                self._inputs(),
            )
        }["cec.work.teer"]
        self.assertEqual(conflict_result.status, "AT-RISK")

    def test_period_envelope_issues_make_work_scope_incomplete(self) -> None:
        known_ineligible = self._period(
            "mep_" + "f" * 32,
            noc_code="00000",
            teer=5,
        )
        issue_variants = (
            "period_key_invalid:missing-or-duplicate",
            "period_key_mismatch:mismatched",
            "period_cross_document:mep_duplicate",
            "period_value_invalid:teer",
            "period_value_conflict:teer",
        )
        for issue in issue_variants:
            evidence = self._evidence(
                (known_ineligible,),
                work_history_scope_complete=True,
            )
            evidence = MecEvidence(
                **{
                    **evidence.__dict__,
                    "issues": (issue,),
                }
            )
            result = {
                item.criterion_id: item
                for item in evaluate_cec(
                    self._program_context("cec"),
                    evidence,
                    self._inputs(),
                )
            }["cec.work.teer"]
            with self.subTest(issue=issue):
                self.assertEqual(
                    (result.status, result.reason_code),
                    ("AT-RISK", "scope_incomplete"),
                )

        unrelated = self._evidence(
            (known_ineligible,),
            work_history_scope_complete=True,
        )
        unrelated = MecEvidence(
            **{
                **unrelated.__dict__,
                "issues": ("unrelated_document_warning:profile",),
            }
        )
        unrelated_result = {
            item.criterion_id: item
            for item in evaluate_cec(
                self._program_context("cec"),
                unrelated,
                self._inputs(),
            )
        }["cec.work.teer"]
        self.assertEqual(unrelated_result.status, "FAIL")

    def test_loader_period_key_errors_demote_known_failure_to_at_risk(self) -> None:
        def loaded(mode: str) -> MecEvidence:
            with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ,
                {"PR_PERSONAL_DIR": directory},
            ):
                candidate = f"period-{mode}"
                vault_ = vault.open_vault(candidate)
                try:
                    vault.create_candidate(vault_, candidate)
                    vault.upsert_profile_factor(
                        vault_,
                        CrsProfileFactor(
                            factor_id="review.mec",
                            factor_group="program_eligibility",
                            claimed_value={},
                            source="user_entry",
                        ),
                    )

                    def add_document(
                        name: str,
                        doc_type: str,
                        fields: list[tuple[str, object]],
                    ) -> None:
                        source = Path(directory) / name
                        source.write_text(name, encoding="utf-8")
                        document = vault.import_document(
                            vault_,
                            candidate,
                            source,
                            doc_type=doc_type,
                        )
                        run_id = vault.record_extraction_run(
                            vault_,
                            document_id=document.document_id,
                            parser_version=vault.current_parser_version(),
                        )
                        for field_name, normalized_value in fields:
                            value_id = vault.add_extracted_value(
                                vault_,
                                document_id=document.document_id,
                                page_id=None,
                                factor_id="review.mec",
                                field_name=field_name,
                                raw_text=str(normalized_value),
                                normalized_value=normalized_value,
                                bbox=None,
                                extractor_confidence=1.0,
                                quality_flag="ok",
                                extraction_run_id=run_id,
                            )
                            vault.confirm_value(
                                vault_,
                                value_id,
                                "confirm",
                                registry_fingerprint=self._program_context(
                                    "cec"
                                ).registry_fingerprint,
                            )

                    add_document(
                        "profile.txt",
                        "mec-profile",
                        [("work_history_scope_complete", True)],
                    )
                    valid_source = Path(directory) / "known.txt"
                    valid_source.write_text("known", encoding="utf-8")
                    valid_document = vault.import_document(
                        vault_,
                        candidate,
                        valid_source,
                        doc_type="mec-employment-period",
                    )
                    valid_sha = vault_.con.execute(
                        "SELECT file_sha256 FROM documents WHERE document_id = ?",
                        (valid_document.document_id,),
                    ).fetchone()["file_sha256"]
                    valid_id = mecfields.employment_period_id(valid_sha)
                    run_id = vault.record_extraction_run(
                        vault_,
                        document_id=valid_document.document_id,
                        parser_version=vault.current_parser_version(),
                    )
                    for field_name, normalized_value in (
                        ("employment_period_id", valid_id),
                        ("noc_code", {"employment_period_id": valid_id, "value": "00000"}),
                        ("teer", {"employment_period_id": valid_id, "value": 5}),
                    ):
                        value_id = vault.add_extracted_value(
                            vault_,
                            document_id=valid_document.document_id,
                            page_id=None,
                            factor_id="review.mec",
                            field_name=field_name,
                            raw_text=str(normalized_value),
                            normalized_value=normalized_value,
                            bbox=None,
                            extractor_confidence=1.0,
                            quality_flag="ok",
                            extraction_run_id=run_id,
                        )
                        vault.confirm_value(
                            vault_,
                            value_id,
                            "confirm",
                            registry_fingerprint=self._program_context(
                                "cec"
                            ).registry_fingerprint,
                        )

                    malformed_source = Path(directory) / f"{mode}.txt"
                    malformed_source.write_text(mode, encoding="utf-8")
                    malformed_document = vault.import_document(
                        vault_,
                        candidate,
                        malformed_source,
                        doc_type="mec-employment-period",
                    )
                    malformed_sha = vault_.con.execute(
                        "SELECT file_sha256 FROM documents WHERE document_id = ?",
                        (malformed_document.document_id,),
                    ).fetchone()["file_sha256"]
                    expected = mecfields.employment_period_id(malformed_sha)
                    key_values = {
                        "zero_values": [],
                        "missing": [],
                        "mismatch": ["mep_" + "0" * 32],
                        "duplicate": [expected, expected],
                    }[mode]
                    if mode == "zero_values":
                        return mecfields.load_mec_evidence(
                            vault_,
                            candidate,
                            self._program_context("cec").registry_fingerprint,
                        )
                    malformed_fields = [
                        *[("employment_period_id", value) for value in key_values],
                        (
                            "teer",
                            {"employment_period_id": expected, "value": 5},
                        ),
                    ]
                    add_document(
                        f"{mode}-values.txt",
                        "mec-employment-period",
                        malformed_fields,
                    )
                    return mecfields.load_mec_evidence(
                        vault_,
                        candidate,
                        self._program_context("cec").registry_fingerprint,
                    )
                finally:
                    vault_.con.close()

        for mode in ("zero_values", "missing", "mismatch", "duplicate"):
            evidence = loaded(mode)
            result = {
                item.criterion_id: item
                for item in evaluate_cec(
                    self._program_context("cec"),
                    evidence,
                    self._inputs(),
                )
            }["cec.work.teer"]
            with self.subTest(mode=mode):
                self.assertEqual(result.status, "AT-RISK")

    def test_bundle_is_deterministic_side_effect_free_and_public_pii_light(self) -> None:
        context = self._program_context("cec")
        evidence = self._evidence(
            intended_destination_province="ON",
            funds_amount="123456789",
        )
        kwargs = dict(
            program="cec",
            context=context,
            evidence=evidence,
            confirmed_inputs=self._inputs(),
            run_id="mec_deadbeef0003deadbeef0003deadbeef",
            created_at="2026-07-20T03:00:00Z",
            private_output_path="output/mec/cec/latest.json",
        )
        with mock.patch("pathlib.Path.write_bytes") as write:
            first = screen_mec(**kwargs)
            second = screen_mec(**kwargs)
        write.assert_not_called()
        self.assertEqual(first.private_json, second.private_json)
        self.assertEqual(first.private_markdown, second.private_markdown)
        self.assertEqual(first.public_json, second.public_json)
        self.assertEqual(
            first.private_report.registry_fingerprint,
            first.public_summary.registry_fingerprint,
        )
        public = first.public_json.decode()
        for private in (
            "candidate",
            "val_",
            "123456789",
            "employment_traces",
            "applicant_values",
        ):
            self.assertNotIn(private, public)

    def test_default_run_ids_are_opaque_and_unlinkable_across_reruns(self) -> None:
        context = self._program_context("cec")
        evidence = self._evidence()
        kwargs = {
            "program": "cec",
            "context": context,
            "evidence": evidence,
            "confirmed_inputs": self._inputs(),
            "created_at": "2026-07-20T03:00:00Z",
        }
        first = screen_mec(**kwargs)
        second = screen_mec(**kwargs)
        self.assertRegex(first.private_report.run_id, r"^mec_[0-9a-f]{32}$")
        self.assertNotEqual(
            first.private_report.run_id, second.private_report.run_id
        )
        self.assertEqual(
            first.public_summary.run_id, first.private_report.run_id
        )
        self.assertNotIn(
            evidence.candidate_id,
            first.public_json.decode(),
        )
        self.assertEqual(
            first.private_report.candidate_id,
            evidence.candidate_id,
        )

    def test_fst_and_cec_language_thresholds_remain_distinct(self) -> None:
        low_language = self._inputs().with_updates(
            language={
                "first": {
                    "test_date": "2026-01-01",
                    "clb_listening": 4,
                    "clb_reading": 4,
                    "clb_writing": 4,
                    "clb_speaking": 4,
                }
            }
        )
        fst = {
            item.criterion_id: item
            for item in evaluate_fst(
                self._program_context("fst"), self._evidence(), low_language
            )
        }
        self.assertEqual(fst["fst.language.minimum"].status, "FAIL")

        def cec_period(teer: int) -> EmploymentPeriod:
            days = (date(2025, 12, 31) - date(2025, 1, 1)).days + 1
            return self._period(
                "mep_" + str(teer) * 32,
                noc_code="21231",
                teer=teer,
                work_country="CA",
                work_province="ON",
                physically_in_canada=True,
                is_remote=False,
                work_authorized=True,
                temporary_resident_status="valid",
                paid_status=True,
                student_status=False,
                self_employed=False,
                employment_start="2025-01-01",
                duration_months=12,
                total_hours=30 * days / 7,
                hours_per_week=30,
                employment_end="2025-12-31",
            )

        level_five = low_language.with_updates(
            language={
                "first": {
                    "test_date": "2026-01-01",
                    "clb_listening": 5,
                    "clb_reading": 5,
                    "clb_writing": 5,
                    "clb_speaking": 5,
                }
            }
        )
        statuses = {}
        for teer in (1, 2):
            result = {
                item.criterion_id: item
                for item in evaluate_cec(
                    self._program_context("cec"),
                    self._evidence((cec_period(teer),), work_history_scope_complete=True),
                    level_five,
                )
            }
            statuses[teer] = result["cec.language.minimum"].status
        self.assertEqual(statuses, {1: "FAIL", 2: "PASS"})

    def test_cec_language_ignores_teer_from_student_excluded_work(self) -> None:
        days = (date(2025, 12, 31) - date(2025, 1, 1)).days + 1

        def period(token: str, teer: int, *, student: bool) -> EmploymentPeriod:
            return self._period(
                "mep_" + token * 32,
                noc_code="21231",
                teer=teer,
                work_country="CA",
                work_province="ON",
                physically_in_canada=True,
                is_remote=False,
                work_authorized=True,
                temporary_resident_status="valid",
                paid_status=True,
                student_status=student,
                self_employed=False,
                employment_start="2025-01-01",
                employment_end="2025-12-31",
                duration_months=12,
                total_hours=30 * days / 7,
                hours_per_week=30,
            )

        language = self._inputs().with_updates(
            language={
                "first": {
                    "test_date": "2026-01-01",
                    "clb_listening": 5,
                    "clb_reading": 5,
                    "clb_writing": 5,
                    "clb_speaking": 5,
                }
            }
        )
        result = {
            item.criterion_id: item
            for item in evaluate_cec(
                self._program_context("cec"),
                self._evidence(
                    (
                        period("5", 2, student=False),
                        period("6", 0, student=True),
                    ),
                    work_history_scope_complete=True,
                ),
                language,
            )
        }["cec.language.minimum"]
        self.assertEqual((result.status, result.reason_code), ("PASS", "criterion_satisfied"))

    def test_screen_propagates_one_snapshot_to_read_only_sidecars(self) -> None:
        context = self._program_context("fsw")
        period = self._period(
            "mep_" + "a" * 32,
            noc_code="21231",
        )
        evidence = self._evidence((period,), adaptability_scope_complete=True)
        fake_vault = object()
        with (
            mock.patch(
                "crawler.policy_offer.offer_for_program_eligibility",
                return_value={"eligibility_status": "AT-RISK"},
            ) as offer,
            mock.patch(
                "crawler.noc_review.review_noc_duties",
                return_value={"status": "AT-RISK"},
            ) as noc,
            mock.patch(
                "crawler.study_review.review_study",
                return_value={"status": "AT-RISK"},
            ) as study,
        ):
            bundle = screen_mec(
                "fsw",
                context,
                evidence,
                self._inputs(),
                vault_=fake_vault,
                db="corpus.db",
                study_max_age_days=30,
            )
        offer.assert_called_once()
        self.assertEqual(
            offer.call_args.args[2].model_dump(mode="json"),
            context.registry_snapshot.registry.model_dump(mode="json"),
        )
        self.assertIs(
            noc.call_args.kwargs["registry_snapshot"],
            context.registry_snapshot,
        )
        self.assertEqual(
            noc.call_args.kwargs["registry_fingerprint"],
            context.registry_fingerprint,
        )
        self.assertIs(
            study.call_args.kwargs["registry_snapshot"],
            context.registry_snapshot,
        )
        self.assertTrue(study.call_args.kwargs["read_only"])
        self.assertTrue(study.call_args.kwargs["no_report"])
        self.assertEqual(bundle.private_report.status, "AT-RISK")


if __name__ == "__main__":
    unittest.main()
