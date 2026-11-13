"""Independent v5 MEC, POLICY, STUDY, and NOC production-screen release matrix.

Fixtures in this module are deliberately local.  The matrix does not import a
donor test helper and does not manufacture ``PrivateMecCriterion`` objects:
every MEC assertion crosses :func:`crawler.mec_screen.screen_mec`.
"""

from __future__ import annotations

import contextlib
import os
import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType
from unittest import mock

import pytest

from crawler import (
    auditor,
    crs_audit,
    crs_rules,
    index_health,
    mec_screen,
    mecfields,
    noc_review,
    noc_worksheet,
    searchindex,
    study_review,
    policy_offer,
    vault,
)
from crawler.auditors import DecisionContext
from crawler.auditors import additional as additional_auditor
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


pytestmark = pytest.mark.conformance

_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _ROOT / "corpus" / "index.db"
_DLI_ROOT = _ROOT / "corpus" / "dli"
_REFERENCE = date(2026, 6, 15)
_OPERATIONAL_AS_OF = date(2026, 7, 20)
_MAX_AGE_DAYS = 120


def _require_release_prerequisite(
    case: unittest.TestCase, available: bool, label: str
) -> None:
    """Fail authoritative release runs; skip only focused local invocations."""
    if available:
        return
    message = f"release prerequisite unavailable: {label}"
    if os.environ.get("PR_CONFORMANCE_RUNNER") == "1":
        pytest.fail(message, pytrace=False)
    case.skipTest(message)


class TestReleaseAwareMatrixPrerequisites(unittest.TestCase):
    def test_each_missing_prerequisite_fails_authoritative_and_skips_local(self) -> None:
        labels = (
            "corpus database",
            "corpus snapshot family",
            "private vault fixture",
            "release configuration",
        )
        for label in labels:
            with self.subTest(label=label, mode="local"), mock.patch.dict(
                os.environ, {"PR_CONFORMANCE_RUNNER": "0"}
            ), self.assertRaises(unittest.SkipTest) as skipped:
                _require_release_prerequisite(self, False, label)
            self.assertEqual(
                str(skipped.exception),
                f"release prerequisite unavailable: {label}",
            )

            with self.subTest(label=label, mode="authoritative"), mock.patch.dict(
                os.environ, {"PR_CONFORMANCE_RUNNER": "1"}
            ), pytest.raises(
                pytest.fail.Exception,
                match=f"^release prerequisite unavailable: {label}$",
            ):
                _require_release_prerequisite(self, False, label)


_STUDY_RELEASE_CASES = {
    "pgwp_yes_current_only",
    "pgwp_details",
    "pgwp_no",
    "pending",
    "rejected",
    "low_quality",
    "stale_file",
    "stale_render",
    "stale_parser",
    "stale_claim",
    "stale_registry",
    "exact_dli_mismatch",
    "missing_start",
    "missing_end",
    "missing_status",
    "missing_tier",
    "invalid_start",
    "invalid_end",
    "reversed_dates",
    "invalid_status",
    "invalid_tier",
    "config_missing",
    "config_invalid",
    "index_missing",
    "index_empty",
    "index_unreadable",
    "index_corrupt",
    "index_drifted",
    "snapshot_stale",
    "snapshot_healthy",
    "snapshot_future",
    "file_hash_drift",
    "manifest_hash_drift",
    "chunk_hash_drift",
    "crawl_date_drift",
    "wrong_family",
    "wrong_quote",
    "wrong_marker",
    "wrong_citation",
    "unmanifested_chunk",
}
_STUDY_GROUPS = {
    "controls": {
        "pgwp_yes_current_only",
        "pgwp_details",
        "pgwp_no",
    },
    "evidence": {
        "pending",
        "rejected",
        "low_quality",
        "stale_file",
        "stale_render",
        "stale_parser",
        "stale_claim",
        "stale_registry",
        "exact_dli_mismatch",
        "missing_start",
        "missing_end",
        "missing_status",
        "missing_tier",
        "invalid_start",
        "invalid_end",
        "reversed_dates",
        "invalid_status",
        "invalid_tier",
    },
    "preflight": {
        "config_missing",
        "config_invalid",
        "index_missing",
        "index_empty",
        "index_unreadable",
        "index_corrupt",
        "index_drifted",
        "snapshot_stale",
        "snapshot_healthy",
    },
    "provenance": {
        "snapshot_future",
        "file_hash_drift",
        "manifest_hash_drift",
        "chunk_hash_drift",
        "crawl_date_drift",
        "wrong_family",
        "wrong_quote",
        "wrong_marker",
        "wrong_citation",
        "unmanifested_chunk",
    },
}
_STUDY_VALUES = {
    "institution_name": "University of Toronto",
    "dli_number": "O19332746152",
    "credential_level": "3+",
    "program_start": "2022-09-15",
    "program_end": "2026-04-30",
    "study_status": "graduated",
}
_STUDY_CONTROLS = {
    "pgwp_yes_current_only": (
        "O19332746152",
        "University of Toronto",
        "designation_historical_unproven",
    ),
    "pgwp_details": (
        "O246878951383",
        "Centre de formation professionnelle de l’Envolée",
        "pgwp_details_manual",
    ),
    "pgwp_no": (
        "O110032269317",
        "Eston College",
        "pgwp_no",
    ),
}
_NOC_RELEASE_CASES = {
    "missing",
    "source_unavailable",
    "pending",
    "partial",
    "rejected",
    "layer1_stale",
    "layer2_citation_drift",
    "superseded_duty_sha",
    "all_confirmed_manual",
}
_REGISTRY_REPLAY_SCREENS = {"mec", "policy", "study", "noc"}

# Literal release oracle: this must not derive its expected inventory from the
# production manifest that it is intended to police.
_MEC_CRITERIA = {
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

_CLOSED_STATUSES = {"AT-RISK", "DOES-NOT-MEET"}
_EVIDENCE_STATES = (
    "pending",
    "rejected",
    "low_quality",
    "stale_file",
    "stale_render",
    "stale_parser",
    "stale_claim",
    "stale_registry",
)
_STALE_COLUMNS = {
    "stale_file": "confirmed_file_sha256",
    "stale_render": "confirmed_render_sha256",
    "stale_parser": "confirmed_parser_version",
    "stale_claim": "confirmed_profile_claim_version",
    "stale_registry": "confirmed_rule_registry_version",
}

_POLICY_FACTOR = "additional.job_offer"
_CURRENT_RULE = "additional.job_offer.current"
_LEGACY_RULE = "additional.job_offer.legacy"
_PHYSICIAN_RULE = "additional.job_offer.physician"


def _policy_registry(
    *,
    malformed_physician_window: bool = False,
) -> Registry:
    """Build independent raw current, legacy, and physician POLICY rows."""
    repeal = "2025-03-25"
    physician_start = (
        "not-a-date" if malformed_physician_window else "2023-04-25"
    )
    current = RuleRow(
        rule_id=_CURRENT_RULE,
        factor_group="additional_points",
        factor_ids=[_POLICY_FACTOR],
        check_type="policy",
        query="job offer points removing Comprehensive Ranking",
        selector=Selector(
            family="guidance",
            marker="We no longer give points for job offers",
            deny_families=[
                "guidance/express-entry-year-end-report",
                "guidance/express-entry-midyear",
            ],
        ),
        claim_text="Current job-offer additional points are removed.",
        citations=[
            Citation(
                chunk_id="guidance/job-offer.md#001",
                quote="We no longer give points for job offers",
            )
        ],
        machine_check=MachineCheck(
            kind="policy_flag",
            field="job_offer_additional_points",
            flag_value=False,
            effective_from=repeal,
        ),
        volatility=VolatilityMeta(
            volatility="volatile",
            source_family="guidance",
            crawl_date="2026-06-11T01:09:06Z",
            effective_from=repeal,
        ),
    )
    legacy = RuleRow(
        rule_id=_LEGACY_RULE,
        factor_group="additional_points",
        factor_ids=[_POLICY_FACTOR],
        check_type="policy",
        query="occupation Major Group matrix",
        selector=Selector(
            family="ministerial-instructions",
            marker=(
                "200 points, if the offer is for employment in an occupation "
                "contained in Major Group 00"
            ),
        ),
        claim_text="An in-window legacy claim stays manual.",
        citations=[
            Citation(
                chunk_id="ministerial-instructions/amendment-2017-2.md#006",
                quote=(
                    "200 points, if the offer is for employment in an "
                    "occupation contained in Major Group 00"
                ),
            )
        ],
        machine_check=MachineCheck(
            kind="points_table",
            field="job_offer_legacy",
            points_by_level=[
                PointsEntry(
                    label="major_group_00",
                    level="Major Group 00",
                    points=200,
                )
            ],
        ),
        volatility=VolatilityMeta(
            volatility="volatile",
            source_family="ministerial-instructions",
            crawl_date="2026-06-11T03:41:00Z",
            effective_from="2010-01-01",
            effective_to=repeal,
        ),
    )
    physician = RuleRow(
        rule_id=_PHYSICIAN_RULE,
        factor_group="additional_points",
        factor_ids=[_POLICY_FACTOR],
        check_type="policy",
        query="physician arranged employment public policy",
        selector=Selector(
            family="guidance",
            marker="If you’re a physician with a job offer in Canada",
            deny_families=[
                "guidance/express-entry-year-end-report",
                "guidance/express-entry-midyear",
            ],
        ),
        claim_text="A physician public-policy match stays manual.",
        citations=[
            Citation(
                chunk_id="guidance/job-offer.md#002",
                quote=(
                    "were invited to apply for permanent residence through "
                    "Express Entry on or after April 25, 2023"
                ),
            ),
            Citation(
                chunk_id=(
                    "pr-pdi/economic-classes-federal-skilled-workers-arranged-"
                    "employment-awarding-points-applications-received-on-after-"
                    "may-4-2013.md#020"
                ),
                quote=(
                    "a specialist in clinical and laboratory medicine (NOC "
                    "31100), a specialist in surgery (NOC 31101) or a general "
                    "practitioner and family physician (NOC 31102) under NOC 2021"
                ),
            ),
        ],
        machine_check=MachineCheck(
            kind="accepted_enum",
            field="physician_noc",
            accepted_values=[
                AcceptedValue(value="31100", citation_index=1),
                AcceptedValue(value="31101", citation_index=1),
                AcceptedValue(value="31102", citation_index=1),
            ],
            effective_from=physician_start,
            citation_index=0,
        ),
        volatility=VolatilityMeta(
            volatility="volatile",
            source_family="guidance",
            crawl_date="2026-06-11T01:09:06Z",
            effective_from=physician_start,
        ),
    )
    return Registry(rows=[current, legacy, physician])


def _policy_factor(points: int = 200) -> CrsProfileFactor:
    return CrsProfileFactor(
        factor_id=_POLICY_FACTOR,
        factor_group="additional_points",
        claimed_points=points,
        claimed_value=points,
    )


def _policy_value(noc: str) -> ExtractedValue:
    """A raw model input representing an already quarantined/confirmed NOC."""
    return ExtractedValue(
        value_id="val_" + "1" * 32,
        document_id="doc_" + "2" * 32,
        field_name="noc_code",
        raw_text=noc,
        normalized_value=noc,
        extraction_run_id="ext_" + "3" * 32,
        confirmation_status="confirmed",
        quality_flag="ok",
    )


def _policy_context(
    registry: Registry,
    *,
    noc: str | None,
    ita_date: str | None,
    points: int = 200,
) -> DecisionContext:
    return DecisionContext(
        factor_id=_POLICY_FACTOR,
        factor=_policy_factor(points),
        by_field={} if noc is None else {"noc_code": _policy_value(noc)},
        registry=registry,
        consumed=Registry(rows=[]),
        spouse_mode=False,
        reference_date=_OPERATIONAL_AS_OF.isoformat(),
        ita_date=ita_date,
    )


def _policy_rows(registry: Registry) -> dict[str, RuleRow]:
    return {row.rule_id: row for row in registry.rows}


def _period(token: str, **values: object) -> mecfields.EmploymentPeriod:
    return mecfields.EmploymentPeriod(
        employment_period_id="mep_" + token * 32,
        document_id="doc_" + token * 32,
        values=MappingProxyType(dict(values)),
        evidence_ids=("val_" + token * 32,),
    )


def _evidence(
    program: str,
    fingerprint: str,
    *,
    extra: dict[str, object] | None = None,
) -> mecfields.MecEvidence:
    """Create raw, independent valid-path inputs from row-compatible facts."""
    days_2025 = (date(2025, 12, 31) - date(2025, 1, 1)).days + 1
    scalars: dict[str, object] = {
        "work_history_scope_complete": True,
        "intended_destination_province": "ON",
        "eligibility_reference_date": _REFERENCE.isoformat(),
    }
    if program == "cec":
        periods = (
            _period(
                "c",
                noc_code="21231",
                teer=2,
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
                employment_end="2025-12-31",
                duration_months=12,
                total_hours=30 * days_2025 / 7,
                hours_per_week=30,
            ),
        )
    elif program == "fst":
        days = (date(2025, 12, 31) - date(2024, 1, 1)).days + 1
        periods = (
            _period(
                "b",
                noc_code="72200",
                teer=2,
                paid_status=True,
                student_status=False,
                qualified_to_practise=True,
                employment_start="2024-01-01",
                employment_end="2025-12-31",
                duration_months=24,
                total_hours=30 * days / 7,
                hours_per_week=30,
            ),
        )
        scalars.update(
            {
                "offer_certificate_scope_complete": True,
                "trade_certificate_authority": "Ontario authority",
                "trade_certificate_jurisdiction": "ON",
                "trade_certificate_noc_code": "72200",
                "trade_certificate_status": "valid",
                "trade_certificate_issue_date": "2025-01-01",
                "trade_certificate_expiry_date": "2027-01-01",
            }
        )
    else:
        days = (date(2025, 12, 31) - date(2024, 1, 1)).days + 1
        periods = (
            _period(
                "a",
                noc_code="21231",
                teer=1,
                paid_status=True,
                employment_continuous=True,
                employment_start="2024-01-01",
                employment_end="2025-12-31",
                duration_months=24,
                total_hours=30 * days / 7,
                hours_per_week=30,
            ),
        )
        scalars.update(
            {
                "primary_noc_code": "21231",
                "adaptability_scope_complete": True,
                "fsw_education_branch": (
                    "canadian_secondary_or_post_secondary_credential"
                ),
            }
        )
    if extra:
        scalars.update(extra)
    return mecfields.MecEvidence(
        candidate_id=f"release-{program}",
        registry_fingerprint=fingerprint,
        scalars=MappingProxyType(scalars),
        scalar_evidence_ids=MappingProxyType(
            {
                field: (f"val_{index:032x}",)
                for index, field in enumerate(scalars, start=1)
            }
        ),
        periods=periods,
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


def _prepare(program: str, snapshot: crs_rules.RegistrySnapshot):
    return mec_screen.prepare_mec_gate(
        program,
        snapshot,
        str(_REAL_DB),
        _REFERENCE,
        _MAX_AGE_DAYS,
        as_of=_OPERATIONAL_AS_OF,
    )


def _screen(
    program: str,
    snapshot: crs_rules.RegistrySnapshot,
    *,
    evidence: mecfields.MecEvidence | None = None,
    inputs: mec_screen.ConfirmedMecInputs | None = None,
):
    context = _prepare(program, snapshot)
    return mec_screen.screen_mec(
        program,
        context,
        evidence or _evidence(program, snapshot.fingerprint),
        inputs or _inputs(),
        run_id={
            "fsw": "mec_f0000000000000000000000000000000",
            "fst": "mec_f1000000000000000000000000000000",
            "cec": "mec_cec00000000000000000000000000000",
        }[program],
        created_at="2026-07-20T00:00:00Z",
    )


def _mutated_snapshot(
    source: crs_rules.RegistrySnapshot,
    criterion_id: str,
    mutation: str,
) -> crs_rules.RegistrySnapshot:
    rows = []
    for row in source.registry.rows:
        if row.rule_id != criterion_id:
            rows.append(row)
            continue
        if mutation == "missing":
            continue
        if mutation == "unwired":
            rows.append(row.model_copy(update={"factor_ids": ["unwired.release"]}))
        elif mutation == "stale":
            rows.append(
                row.model_copy(
                    update={
                        "volatility": row.volatility.model_copy(
                            update={"crawl_date": "2000-01-01T00:00:00Z"}
                        )
                    }
                )
            )
        elif mutation in {"superseded", "out_of_window"}:
            rows.append(
                row.model_copy(
                    update={
                        "machine_check": row.machine_check.model_copy(
                            update={"effective_to": "2000-01-02"}
                        ),
                        "volatility": row.volatility.model_copy(
                            update={"effective_to": "2000-01-02"}
                        ),
                    }
                )
            )
        elif mutation == "future":
            rows.append(
                row.model_copy(
                    update={
                        "volatility": row.volatility.model_copy(
                            update={"crawl_date": "2099-01-01T00:00:00Z"}
                        )
                    }
                )
            )
        else:  # pragma: no cover - local fixture programmer error
            raise AssertionError(f"unknown release mutation: {mutation}")
    return crs_rules.RegistrySnapshot(Registry(rows=rows))


class TestIndependentMecReleaseMatrix(unittest.TestCase):
    """Drive raw registry and evidence mutations through the public MEC screen."""

    @classmethod
    def setUpClass(cls) -> None:
        _require_release_prerequisite(
            cls, _REAL_DB.is_file(), "corpus database for MEC release matrix"
        )
        cls.snapshot = crs_rules.load_registry_snapshot()

    def test_valid_controls_reach_exact_real_screen_manifests(self) -> None:
        seen: set[str] = set()
        for program, expected in _MEC_CRITERIA.items():
            bundle = _screen(program, self.snapshot)
            actual = tuple(
                item.criterion_id for item in bundle.private_report.criteria
            )
            with self.subTest(program=program):
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), len(set(actual)))
                self.assertGreater(bundle.private_report.counts.passed, 0)
                self.assertIn(
                    bundle.private_report.status,
                    _CLOSED_STATUSES,
                    "manual/funds paths in a valid control must remain closed",
                )
                self.assertNotEqual(bundle.private_report.status, "MEETS")
            seen.add(program)
        self.assertEqual(seen, {"fsw", "fst", "cec"})

    def test_every_criterion_stale_and_window_mutation_is_exactly_closed(self) -> None:
        expected = {
            (program, criterion, mutation)
            for program, criteria in _MEC_CRITERIA.items()
            for criterion in criteria
            for mutation in ("stale", "superseded", "out_of_window")
        }
        seen: set[tuple[str, str, str]] = set()
        control_by_program = {
            program: {
                item.criterion_id: item
                for item in _screen(program, self.snapshot).private_report.criteria
            }
            for program in _MEC_CRITERIA
        }
        for program, criterion, mutation in sorted(expected):
            control = control_by_program[program][criterion]
            self.assertNotIn(
                control.reason_code, {"rule_stale", "rule_out_of_window"}
            )
            mutated = _mutated_snapshot(self.snapshot, criterion, mutation)
            bundle = _screen(program, mutated)
            result = {
                item.criterion_id: item
                for item in bundle.private_report.criteria
            }[criterion]
            want_reason = (
                "rule_stale" if mutation == "stale" else "rule_out_of_window"
            )
            with self.subTest(
                program=program, criterion=criterion, mutation=mutation
            ):
                self.assertEqual(
                    (result.status, result.reason_code),
                    ("AT-RISK", want_reason),
                )
                self.assertIn(bundle.private_report.status, _CLOSED_STATUSES)
                self.assertNotEqual(bundle.private_report.status, "MEETS")
            seen.add((program, criterion, mutation))
        self.assertEqual(seen, expected)
        self.assertEqual(len(seen), 114)

    def test_every_missing_or_unwired_criterion_refuses_before_screen_output(
        self,
    ) -> None:
        expected = {
            (program, criterion, mutation)
            for program, criteria in _MEC_CRITERIA.items()
            for criterion in criteria
            for mutation in ("missing", "unwired")
        }
        seen: set[tuple[str, str, str]] = set()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist.json"
            for program, criterion, mutation in sorted(expected):
                mutated = _mutated_snapshot(self.snapshot, criterion, mutation)
                with self.subTest(
                    program=program, criterion=criterion, mutation=mutation
                ):
                    with self.assertRaisesRegex(
                        mec_screen.MecGatePreparationError,
                        "^MEC criterion manifest is not exactly wired$",
                    ):
                        _prepare(program, mutated)
                    self.assertFalse(output.exists())
                seen.add((program, criterion, mutation))
        self.assertEqual(seen, expected)
        self.assertEqual(len(seen), 76)

    def _vault_destination(
        self, directory: str, state: str
    ) -> mecfields.MecEvidence:
        candidate = f"mec-{state.replace('_', '-')}"
        with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": directory}):
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
                source = Path(directory) / f"{candidate}.txt"
                source.write_text("independent release evidence", encoding="utf-8")
                document = vault.import_document(
                    vault_,
                    candidate,
                    source,
                    doc_type="mec-province-status",
                )
                run_id = vault.record_extraction_run(
                    vault_,
                    document_id=document.document_id,
                    parser_version=vault.current_parser_version(),
                )
                page_id = vault.add_document_page(
                    vault_,
                    document_id=document.document_id,
                    page_number=1,
                    render_sha256="a" * 64,
                    extraction_run_id=run_id,
                )
                value_id = vault.add_extracted_value(
                    vault_,
                    document_id=document.document_id,
                    page_id=page_id,
                    factor_id="review.mec",
                    field_name="intended_destination_province",
                    raw_text="ON",
                    normalized_value="ON",
                    bbox=None,
                    extractor_confidence=1.0,
                    quality_flag="low_quality" if state == "low_quality" else "ok",
                    extraction_run_id=run_id,
                )
                if state == "rejected":
                    vault.confirm_value(
                        vault_,
                        value_id,
                        "reject",
                        registry_fingerprint=self.snapshot.fingerprint,
                    )
                elif state != "pending":
                    vault.confirm_value(
                        vault_,
                        value_id,
                        "confirm",
                        registry_fingerprint=self.snapshot.fingerprint,
                    )
                stale_column = _STALE_COLUMNS.get(state)
                if stale_column is not None:
                    vault_.con.execute(
                        f"UPDATE extracted_values SET {stale_column} = ? "
                        "WHERE value_id = ?",
                        ("stale-release-binding", value_id),
                    )
                    vault_.con.commit()
                return mecfields.load_mec_evidence(
                    vault_, candidate, self.snapshot.fingerprint
                )
            finally:
                vault_.con.close()

    def test_pending_rejected_low_quality_and_all_five_stale_keys_never_meet(
        self,
    ) -> None:
        expected = {
            (program, state)
            for program in _MEC_CRITERIA
            for state in _EVIDENCE_STATES
        }
        seen: set[tuple[str, str]] = set()
        destination = {
            "fsw": "fsw.destination.outside_quebec",
            "fst": "fst.destination.outside_quebec",
            "cec": "cec.destination.outside_quebec",
        }
        with tempfile.TemporaryDirectory() as directory:
            control = self._vault_destination(directory, "confirmed")
            self.assertEqual(
                control.value("intended_destination_province"), "ON"
            )
            for program in _MEC_CRITERIA:
                control_bundle = _screen(
                    program,
                    self.snapshot,
                    evidence=replace(
                        control,
                        candidate_id=f"control-{program}",
                    ),
                )
                control_result = {
                    item.criterion_id: item
                    for item in control_bundle.private_report.criteria
                }[destination[program]]
                self.assertEqual(
                    (control_result.status, control_result.reason_code),
                    ("PASS", "criterion_satisfied"),
                )
            for state in _EVIDENCE_STATES:
                blocked = self._vault_destination(directory, state)
                self.assertIsNone(
                    blocked.value("intended_destination_province"), state
                )
                for program in _MEC_CRITERIA:
                    bundle = _screen(
                        program,
                        self.snapshot,
                        evidence=replace(
                            blocked,
                            candidate_id=f"{state}-{program}",
                        ),
                    )
                    result = {
                        item.criterion_id: item
                        for item in bundle.private_report.criteria
                    }[destination[program]]
                    with self.subTest(program=program, state=state):
                        self.assertEqual(
                            (result.status, result.reason_code),
                            ("AT-RISK", "evidence_missing"),
                        )
                        self.assertIn(bundle.private_report.status, _CLOSED_STATUSES)
                        self.assertNotEqual(bundle.private_report.status, "MEETS")
                    seen.add((program, state))
        self.assertEqual(seen, expected)
        self.assertEqual(len(seen), 24)

    def test_invalid_config_index_snapshot_drift_and_future_rows_refuse(self) -> None:
        output_root = tempfile.TemporaryDirectory()
        self.addCleanup(output_root.cleanup)
        output = Path(output_root.name) / "report.json"
        for value in (None, 0, -1, True):
            with self.subTest(max_age=value), self.assertRaisesRegex(
                mec_screen.MecGatePreparationError,
                "^MEC gate configuration unavailable$",
            ):
                mec_screen.prepare_mec_gate(
                    "cec",
                    self.snapshot,
                    str(_REAL_DB),
                    _REFERENCE,
                    value,
                    as_of=_OPERATIONAL_AS_OF,
                )
        with self.assertRaisesRegex(
            mec_screen.MecGatePreparationError,
            "^MEC gate configuration unavailable$",
        ):
            mec_screen.prepare_mec_gate(
                "cec",
                None,
                str(_REAL_DB),
                _REFERENCE,
                _MAX_AGE_DAYS,
                as_of=_OPERATIONAL_AS_OF,
            )
        missing_db = Path(output_root.name) / "absent" / "index.db"
        with self.assertRaises(Exception):
            mec_screen.prepare_mec_gate(
                "cec",
                self.snapshot,
                str(missing_db),
                _REFERENCE,
                _MAX_AGE_DAYS,
                as_of=_OPERATIONAL_AS_OF,
            )
        future = _mutated_snapshot(
            self.snapshot, "cec.destination.outside_quebec", "future"
        )
        future_bundle = _screen("cec", future)
        future_result = {
            item.criterion_id: item
            for item in future_bundle.private_report.criteria
        }["cec.destination.outside_quebec"]
        self.assertEqual(
            (future_result.status, future_result.reason_code),
            ("AT-RISK", "rule_stale"),
        )
        with self.assertRaisesRegex(
            mec_screen.MecGatePreparationError,
            "^MEC evidence fingerprint mismatch$",
        ):
            _screen(
                "cec",
                future,
                evidence=_evidence("cec", self.snapshot.fingerprint),
            )
        self.assertFalse(output.exists())

    def test_funds_offer_manual_and_physician_inputs_never_manufacture_meets(
        self,
    ) -> None:
        expected = {
            (program, amount, offer)
            for program in ("fsw", "fst")
            for amount in (None, "0", "999999999999999999", "-1")
            for offer in (False, True)
        }
        seen: set[tuple[str, str | None, bool]] = set()
        for program, amount, offer in sorted(
            expected, key=lambda item: (item[0], str(item[1]), item[2])
        ):
            extra: dict[str, object] = {
                "funds_household_size": 1,
                "funds_accessible": True,
            }
            if amount is not None:
                extra["funds_amount"] = amount
            if offer:
                extra.update(
                    {
                        "offer_full_time": True,
                        "offer_paid_status": True,
                        "offer_noc_code": "72200" if program == "fst" else "21231",
                    }
                )
            evidence = _evidence(
                program, self.snapshot.fingerprint, extra=extra
            )
            inputs = _inputs().with_updates(
                sidecars={
                    "offer": {"eligibility_status": "AT-RISK", "crs_points": 0},
                    "physician_exception_claimed": True,
                }
            )
            bundle = _screen(
                program, self.snapshot, evidence=evidence, inputs=inputs
            )
            criterion_id = f"{program}.funds.requirement"
            result = {
                item.criterion_id: item
                for item in bundle.private_report.criteria
            }[criterion_id]
            with self.subTest(program=program, amount=amount, offer=offer):
                self.assertEqual(
                    (result.status, result.reason_code),
                    ("AT-RISK", "funds_snapshot_unavailable"),
                )
                self.assertTrue(result.applicability_grounded)
                self.assertTrue(result.applicable)
                self.assertIn(bundle.private_report.status, _CLOSED_STATUSES)
                self.assertNotEqual(bundle.private_report.status, "MEETS")
            seen.add((program, amount, offer))
        self.assertEqual(seen, expected)
        self.assertEqual(len(seen), 16)


class TestIndependentStudyReleaseMatrix(unittest.TestCase):
    """Drive fresh vault/index/source fixtures through the real STUDY screen."""

    def setUp(self) -> None:
        _require_release_prerequisite(
            self, _REAL_DB.is_file(), "corpus database for STUDY release matrix"
        )
        _require_release_prerequisite(
            self, _DLI_ROOT.is_dir(), "DLI corpus family for STUDY release matrix"
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self.temp.name}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.snapshot = crs_rules.load_registry_snapshot()

    def _seed_study(
        self,
        candidate: str,
        *,
        values: dict[str, object] | None = None,
        state: str = "confirmed",
    ) -> tuple[vault.Vault, dict[str, str]]:
        active = dict(_STUDY_VALUES if values is None else values)
        vault_ = vault.open_vault(candidate)
        vault.create_candidate(vault_, candidate)
        vault.upsert_profile_factor(
            vault_,
            CrsProfileFactor(
                factor_id="review.study",
                factor_group="additional_points",
                claimed_value={"candidate": candidate},
            ),
        )
        source = Path(self.temp.name) / f"{candidate}.pdf"
        source.write_bytes(
            b"%PDF-1.4\n% independent study release fixture\n"
            + candidate.encode("ascii")
        )
        document = vault.import_document(
            vault_, candidate, source, doc_type="study_proof"
        )
        run_id = vault.record_extraction_run(
            vault_,
            document_id=document.document_id,
            parser_version=vault.current_parser_version(),
            status="complete",
        )
        render_sha = hashlib.sha256(
            f"render:{candidate}".encode("ascii")
        ).hexdigest()
        page_id = vault.add_document_page(
            vault_,
            document_id=document.document_id,
            page_number=1,
            image_relpath=f"rendered/{candidate}/page-0001.png",
            render_sha256=render_sha,
            extraction_run_id=run_id,
        )
        ids: dict[str, str] = {}
        for field, value in active.items():
            value_id = vault.add_extracted_value(
                vault_,
                document_id=document.document_id,
                page_id=page_id,
                factor_id="review.study",
                field_name=field,
                raw_text=str(value),
                normalized_value=value,
                bbox=None,
                extractor_confidence=1.0,
                quality_flag="low_quality" if state == "low_quality" else "ok",
                extraction_run_id=run_id,
            )
            ids[field] = value_id
            if state == "pending":
                continue
            vault.confirm_value(
                vault_,
                value_id,
                "reject" if state == "rejected" else "confirm",
                registry_fingerprint=self.snapshot.fingerprint,
            )
        stale_column = {
            "stale_file": "confirmed_file_sha256",
            "stale_render": "confirmed_render_sha256",
            "stale_parser": "confirmed_parser_version",
            "stale_claim": "confirmed_profile_claim_version",
            "stale_registry": "confirmed_rule_registry_version",
        }.get(state)
        if stale_column:
            vault_.con.execute(
                f"UPDATE extracted_values SET {stale_column} = ? "
                "WHERE factor_id = 'review.study'",
                (f"stale-{state}",),
            )
            vault_.con.commit()
        self.assertEqual(len(ids), len(active))
        self.assertEqual(len(ids), len(set(ids.values())))
        return vault_, ids

    def _copy_fixture(
        self, label: str, *dlis: str
    ) -> tuple[Path, Path]:
        root = Path(self.temp.name) / f"snapshot-{label}" / "dli"
        root.mkdir(parents=True)
        shutil.copy2(_DLI_ROOT / "manifest.json", root / "manifest.json")
        for dli in dlis or ("O19332746152",):
            shutil.copy2(_DLI_ROOT / f"{dli}.md", root / f"{dli}.md")
        db = Path(self.temp.name) / f"{label}.db"
        shutil.copy2(_REAL_DB, db)
        return root, db

    def _build_preflight_index(
        self,
        label: str,
        *,
        crawl_date: str = "2026-07-16",
        drift: bool = False,
    ) -> Path:
        """Build an independent minimal searchindex-shaped DLI database."""
        db = Path(self.temp.name) / f"preflight-{label}.db"
        text = "Independent DLI preflight fixture"
        con = sqlite3.connect(db)
        try:
            con.executescript(searchindex.CHUNKS_DDL)
            con.executescript(searchindex.FTS_DDL)
            con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            con.execute(
                "INSERT INTO chunks("
                "chunk_id, relpath, source_url, title, section, crawl_date, "
                "source_type, chunk_sha, ordinal, text"
                ") VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    "dli/independent.md#001",
                    "dli/independent.md",
                    "",
                    "",
                    "",
                    crawl_date,
                    "",
                    "0" * 64 if drift else searchindex.chunk_sha(text),
                    1,
                    text,
                ),
            )
            con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
            con.commit()
        finally:
            con.close()
        return db

    def _review(
        self,
        vault_: vault.Vault,
        candidate: str,
        source_root: Path,
        db: Path,
        *,
        max_age_days: object = 30,
        dynamic_rows=None,
    ) -> dict:
        patches = [
            mock.patch.object(study_review, "_DLI_SNAPSHOT_ROOT", source_root),
            mock.patch.object(
                study_review, "_today", return_value=date(2026, 7, 19)
            ),
        ]
        if dynamic_rows is not None:
            patches.append(
                mock.patch.object(
                    study_review, "_dynamic_rows", side_effect=dynamic_rows
                )
            )
        with patches[0], patches[1]:
            if len(patches) == 3:
                with patches[2]:
                    return study_review.review_study(
                        vault_,
                        db,
                        candidate_id=candidate,
                        max_age_days=max_age_days,
                        registry_snapshot=self.snapshot,
                    )
            return study_review.review_study(
                vault_,
                db,
                candidate_id=candidate,
                max_age_days=max_age_days,
                registry_snapshot=self.snapshot,
            )

    def _report(self, vault_: vault.Vault) -> Path:
        return vault_.root / "output" / "study-review" / "latest.json"

    def _seed_lkg(self, vault_: vault.Vault, label: str) -> bytes:
        """Seed a historical successful report whose lineage is explicitly old."""
        payload = (
            json.dumps(
                {
                    "as_of": "2000-01-01T00:00:00Z",
                    "registry_fingerprint": "0" * 64,
                    "verdict": {
                        "status": "AT-RISK",
                        "reason": f"historical-{label}",
                    },
                },
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        report = self._report(vault_)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes(payload)
        return payload

    def _assert_public(
        self,
        result: dict,
        expected: tuple[str, str, str | None],
        *,
        label: str,
    ) -> None:
        self.assertEqual(tuple(result), study_review.PUBLIC_FIELDS, label)
        self.assertEqual(
            (result["status"], result["reason"], result["as_of"]),
            expected,
            label,
        )
        self.assertIn(result["status"], {"AT-RISK", "GAP", "N/A"}, label)
        for forbidden in (
            "SUBSTANTIATED",
            "crs_points",
            "score",
            "substantiated_points",
            "points",
            "evidence_ids",
            "raw_text",
            "path",
        ):
            self.assertNotIn(forbidden, result, label)

    def _assert_review_read_only(
        self,
        vault_: vault.Vault,
        source_root: Path,
        db: Path,
        before_values: list[tuple],
        before_source: dict[str, bytes],
        before_db: bytes,
    ) -> None:
        after_values = [
            tuple(row)
            for row in vault_.con.execute(
                "SELECT value_id, confirmation_status, normalized_value_json "
                "FROM extracted_values ORDER BY value_id"
            ).fetchall()
        ]
        self.assertEqual(after_values, before_values)
        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in sorted(source_root.iterdir())
                if path.is_file()
            },
            before_source,
        )
        self.assertEqual(db.read_bytes(), before_db)

    def test_study_release_case_manifest_is_complete(self) -> None:
        groups = list(_STUDY_GROUPS.values())
        self.assertTrue(all(groups))
        self.assertEqual(sum(map(len, groups)), len(_STUDY_RELEASE_CASES))
        self.assertEqual(set().union(*groups), _STUDY_RELEASE_CASES)

    def test_pgwp_controls_are_dynamic_current_only_and_never_green(self) -> None:
        seen: set[str] = set()
        all_ids: set[str] = set()
        for label, (dli, institution, reason) in _STUDY_CONTROLS.items():
            with self.subTest(case=label):
                source_root, db = self._copy_fixture(label, dli)
                raw_manifest = (source_root / "manifest.json").read_bytes()
                manifest = json.loads(raw_manifest)
                entry = next(
                    item
                    for item in manifest["files"]
                    if item["file"] == f"{dli}.md"
                )
                raw_document = (source_root / f"{dli}.md").read_bytes()
                body = raw_document.split(b"\n---\n\n", 1)[1]
                self.assertEqual(
                    hashlib.sha256(body).hexdigest(),
                    entry["content_sha256"],
                )

                values = {
                    **_STUDY_VALUES,
                    "dli_number": dli,
                    "institution_name": institution,
                }
                vault_, ids = self._seed_study(label, values=values)
                self.addCleanup(vault_.con.close)
                self.assertFalse(all_ids & set(ids.values()))
                all_ids.update(ids.values())
                with mock.patch(
                    "crawler.auditor.gate_subset",
                    wraps=auditor.gate_subset,
                ) as gate:
                    result = self._review(
                        vault_, label, source_root, db
                    )
                self._assert_public(
                    result,
                    ("AT-RISK", reason, manifest["as_of"]),
                    label=label,
                )
                self.assertTrue(result.report_created)
                registry = gate.call_args.args[0]
                self.assertEqual(
                    [row.rule_id for row in registry.rows[:2]],
                    ["additional.study", "study.r73_definition"],
                )
                uri = f"file:{db.resolve()}?mode=ro"
                with sqlite3.connect(uri, uri=True) as con:
                    expected_chunks = [
                        row[0]
                        for row in con.execute(
                            "SELECT chunk_id FROM chunks WHERE relpath = ? "
                            "ORDER BY ordinal",
                            (f"dli/{dli}.md",),
                        ).fetchall()
                    ]
                self.assertGreaterEqual(len(expected_chunks), 2)
                self.assertEqual(
                    [
                        row.citations[0].chunk_id
                        for row in registry.rows[2:]
                    ],
                    expected_chunks,
                )
                private = json.loads(
                    self._report(vault_).read_text(encoding="utf-8")
                )
                self.assertEqual(
                    [
                        citation["chunk_id"]
                        for citation in private["dynamic_citations"]
                    ],
                    expected_chunks,
                )
                seen.add(label)
        self.assertEqual(seen, _STUDY_GROUPS["controls"])
        self.assertEqual(len(seen), 3)

    def test_evidence_and_field_matrix_has_exact_closed_results(self) -> None:
        cases: dict[str, tuple[dict[str, object], str, tuple[str, str, str | None]]] = {
            "pending": (
                _STUDY_VALUES,
                "pending",
                ("N/A", "no_study_evidence", None),
            ),
            "rejected": (
                _STUDY_VALUES,
                "rejected",
                ("N/A", "no_study_evidence", None),
            ),
            "low_quality": (
                _STUDY_VALUES,
                "low_quality",
                ("N/A", "no_study_evidence", None),
            ),
            **{
                state: (
                    _STUDY_VALUES,
                    state,
                    ("N/A", "no_study_evidence", None),
                )
                for state in (
                    "stale_file",
                    "stale_render",
                    "stale_parser",
                    "stale_claim",
                    "stale_registry",
                )
            },
            "exact_dli_mismatch": (
                {**_STUDY_VALUES, "dli_number": "O99999999999"},
                "confirmed",
                ("AT-RISK", "exact_dli_mismatch", None),
            ),
            "missing_start": (
                {
                    key: value
                    for key, value in _STUDY_VALUES.items()
                    if key != "program_start"
                },
                "confirmed",
                ("GAP", "missing_study_fields", None),
            ),
            "missing_end": (
                {
                    key: value
                    for key, value in _STUDY_VALUES.items()
                    if key != "program_end"
                },
                "confirmed",
                ("GAP", "missing_study_fields", None),
            ),
            "missing_status": (
                {
                    key: value
                    for key, value in _STUDY_VALUES.items()
                    if key != "study_status"
                },
                "confirmed",
                ("GAP", "missing_study_fields", None),
            ),
            "missing_tier": (
                {
                    key: value
                    for key, value in _STUDY_VALUES.items()
                    if key != "credential_level"
                },
                "confirmed",
                ("GAP", "missing_study_fields", None),
            ),
            "invalid_start": (
                {**_STUDY_VALUES, "program_start": "not-a-date"},
                "confirmed",
                ("AT-RISK", "ambiguous_study_evidence", None),
            ),
            "invalid_end": (
                {**_STUDY_VALUES, "program_end": "2020-00-90"},
                "confirmed",
                ("AT-RISK", "ambiguous_study_evidence", None),
            ),
            "reversed_dates": (
                {**_STUDY_VALUES, "program_start": "2027-01-01"},
                "confirmed",
                ("AT-RISK", "ambiguous_study_evidence", None),
            ),
            "invalid_status": (
                {**_STUDY_VALUES, "study_status": "enrolled"},
                "confirmed",
                ("GAP", "study_not_completed", "2026-07-16T18:08:26Z"),
            ),
            "invalid_tier": (
                {**_STUDY_VALUES, "credential_level": "secondary"},
                "confirmed",
                (
                    "GAP",
                    "below_grounded_credential_tier",
                    "2026-07-16T18:08:26Z",
                ),
            ),
        }
        seen: set[str] = set()
        for label, (values, state, expected) in cases.items():
            with self.subTest(case=label):
                source_root, db = self._copy_fixture(label)
                vault_, _ = self._seed_study(
                    label, values=values, state=state
                )
                self.addCleanup(vault_.con.close)
                prior = (
                    self._seed_lkg(vault_, label)
                    if expected[2] is None
                    else None
                )
                result = self._review(vault_, label, source_root, db)
                self._assert_public(result, expected, label=label)
                self.assertNotEqual(result["status"], "SUBSTANTIATED")
                if result["as_of"] is None:
                    self.assertEqual(self._report(vault_).read_bytes(), prior)
                seen.add(label)
        self.assertEqual(seen, _STUDY_GROUPS["evidence"])
        self.assertEqual(len(seen), 18)

    def test_config_index_and_snapshot_states_refuse_without_artifacts(self) -> None:
        seen: set[str] = set()
        source_root, control_db = self._copy_fixture("preflight-control")

        for value in (None, "", "days", 0, -1, True):
            label = "config_missing" if value is None else "config_invalid"
            with self.subTest(case=label, value=value):
                candidate = f"{label}-{str(value).replace('-', 'n')}"
                vault_, _ = self._seed_study(candidate)
                self.addCleanup(vault_.con.close)
                report = self._report(vault_)
                prior = self._seed_lkg(vault_, candidate)
                with mock.patch(
                    "crawler.study_review.index_health.probe_snapshot"
                ) as probe:
                    result = self._review(
                        vault_,
                        candidate,
                        source_root,
                        control_db,
                        max_age_days=value,
                    )
                self._assert_public(
                    result,
                    ("AT-RISK", "snapshot_config_invalid", None),
                    label=label,
                )
                probe.assert_not_called()
                self.assertEqual(self._report(vault_).read_bytes(), prior)
                seen.add(label)

        missing_db = Path(self.temp.name) / "preflight-missing.db"
        empty_db = Path(self.temp.name) / "preflight-empty.db"
        empty_db.write_bytes(b"")
        corrupt_db = Path(self.temp.name) / "preflight-corrupt.db"
        corrupt_db.write_bytes(b"not a sqlite database")
        unreadable_db = self._build_preflight_index("unreadable")
        drifted_db = self._build_preflight_index("drifted", drift=True)
        stale_db = self._build_preflight_index(
            "stale", crawl_date="2000-01-01"
        )
        status_cases = {
            "index_missing": (
                missing_db,
                index_health.SNAPSHOT_MISSING,
                f"no index file at {missing_db}",
            ),
            "index_empty": (
                empty_db,
                index_health.SNAPSHOT_EMPTY,
                f"index file is empty (0 bytes): {empty_db}",
            ),
            "index_unreadable": (
                unreadable_db,
                index_health.SNAPSHOT_UNREADABLE,
                "cannot open index read-only",
            ),
            "index_corrupt": (
                corrupt_db,
                index_health.SNAPSHOT_CORRUPT,
                "index tables unreadable",
            ),
            "index_drifted": (
                drifted_db,
                index_health.SNAPSHOT_DRIFTED,
                "indexed chunk text drifted from its integrity fingerprint",
            ),
            "snapshot_stale": (
                stale_db,
                index_health.SNAPSHOT_STALE,
                "snapshot older than 30d",
            ),
            "snapshot_healthy": (
                control_db,
                index_health.SNAPSHOT_OK,
                "snapshot present and fresh",
            ),
        }
        for label, (db, status, reason) in status_cases.items():
            with self.subTest(case=label):
                vault_, _ = self._seed_study(label)
                self.addCleanup(vault_.con.close)
                report = self._report(vault_)
                prior = self._seed_lkg(vault_, label)
                connect_guard = (
                    mock.patch(
                        "crawler.index_health.sqlite3.connect",
                        side_effect=sqlite3.OperationalError(
                            "injected unreadable index"
                        ),
                    )
                    if label == "index_unreadable"
                    else contextlib.nullcontext()
                )
                with connect_guard as guarded_connect:
                    health = index_health.probe_snapshot(
                        db,
                        "dli",
                        max_age_days=30,
                        as_of="2026-07-20",
                    )
                    result = self._review(
                        vault_, label, source_root, db
                    )
                self.assertEqual((health.status, health.reason), (status, reason))
                if label == "index_unreadable":
                    self.assertGreaterEqual(guarded_connect.call_count, 2)
                if label == "snapshot_healthy":
                    self._assert_public(
                        result,
                        (
                            "AT-RISK",
                            "designation_historical_unproven",
                            "2026-07-16T18:08:26Z",
                        ),
                        label=label,
                    )
                    self.assertTrue(result.report_created)
                    self.assertNotEqual(report.read_bytes(), prior)
                else:
                    self._assert_public(
                        result,
                        ("AT-RISK", "snapshot_unusable", None),
                        label=label,
                    )
                    self.assertEqual(report.read_bytes(), prior)
                seen.add(label)
        self.assertEqual(seen, _STUDY_GROUPS["preflight"])
        self.assertEqual(len(seen), 9)

    def test_snapshot_and_dynamic_provenance_mutations_fail_closed(self) -> None:
        seen: set[str] = set()
        sqlite_mutations = {
            "snapshot_future": (
                "UPDATE chunks SET crawl_date = '2099-01-01' "
                "WHERE relpath LIKE 'dli/%'",
                ("AT-RISK", "snapshot_unusable", None),
            ),
            "chunk_hash_drift": (
                "UPDATE chunks SET text = text || ' drift' "
                "WHERE relpath = 'dli/O19332746152.md' AND ordinal = 1",
                ("AT-RISK", "snapshot_unusable", None),
            ),
            "crawl_date_drift": (
                "UPDATE chunks SET crawl_date = '2026-07-15' "
                "WHERE relpath = 'dli/O19332746152.md' AND ordinal = 1",
                ("AT-RISK", "snapshot_provenance_mismatch", None),
            ),
        }
        for label, (sql, expected) in sqlite_mutations.items():
            with self.subTest(case=label):
                source_root, db = self._copy_fixture(label)
                before_rows = searchindex.canonical_rows_for_relpath(
                    db, "dli/O19332746152.md"
                )
                self.assertGreaterEqual(len(before_rows), 2)
                with sqlite3.connect(db) as con:
                    con.execute(sql)
                with sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True) as con:
                    mutated = con.execute(
                        "SELECT crawl_date, text, chunk_sha FROM chunks "
                        "WHERE relpath = ? ORDER BY ordinal",
                        ("dli/O19332746152.md",),
                    ).fetchall()
                self.assertGreaterEqual(len(mutated), 2)
                self.assertNotEqual(
                    [tuple(row) for row in mutated],
                    [
                        (
                            row["crawl_date"],
                            row["text"],
                            row["chunk_sha"],
                        )
                        for row in before_rows
                    ],
                )
                vault_, _ = self._seed_study(label)
                self.addCleanup(vault_.con.close)
                before_values = [
                    tuple(row)
                    for row in vault_.con.execute(
                        "SELECT value_id, confirmation_status, "
                        "normalized_value_json FROM extracted_values "
                        "ORDER BY value_id"
                    ).fetchall()
                ]
                before_source = {
                    path.name: path.read_bytes()
                    for path in sorted(source_root.iterdir())
                    if path.is_file()
                }
                before_db = db.read_bytes()
                prior = self._seed_lkg(vault_, label)
                result = self._review(vault_, label, source_root, db)
                self._assert_public(result, expected, label=label)
                self.assertEqual(self._report(vault_).read_bytes(), prior)
                self._assert_review_read_only(
                    vault_,
                    source_root,
                    db,
                    before_values,
                    before_source,
                    before_db,
                )
                seen.add(label)

        for label in ("file_hash_drift", "manifest_hash_drift"):
            with self.subTest(case=label):
                source_root, db = self._copy_fixture(label)
                if label == "file_hash_drift":
                    document = source_root / "O19332746152.md"
                    document.write_bytes(
                        document.read_bytes() + b"\nsource drift\n"
                    )
                else:
                    manifest_path = source_root / "manifest.json"
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    target = next(
                        item
                        for item in manifest["files"]
                        if item["file"] == "O19332746152.md"
                    )
                    target["content_sha256"] = "f" * 64
                    manifest_path.write_text(
                        json.dumps(manifest), encoding="utf-8"
                    )
                vault_, _ = self._seed_study(label)
                self.addCleanup(vault_.con.close)
                prior = self._seed_lkg(vault_, label)
                result = self._review(vault_, label, source_root, db)
                self._assert_public(
                    result,
                    ("AT-RISK", "snapshot_provenance_mismatch", None),
                    label=label,
                )
                self.assertEqual(self._report(vault_).read_bytes(), prior)
                seen.add(label)

        source_root, db = self._copy_fixture("unmanifested_chunk")
        with sqlite3.connect(db) as con:
            row = con.execute(
                "SELECT relpath, source_url, title, section, crawl_date, "
                "source_type, text FROM chunks WHERE chunk_id = ?",
                ("dli/O19332746152.md#001",),
            ).fetchone()
            con.execute(
                "INSERT INTO chunks(chunk_id, relpath, source_url, title, "
                "section, crawl_date, source_type, chunk_sha, ordinal, text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "dli/O19332746152.md#002",
                    *row[:6],
                    hashlib.sha1(row[6].encode("utf-8")).hexdigest()[:12],
                    2,
                    row[6],
                ),
            )
        self.assertEqual(
            len(
                searchindex.canonical_rows_for_relpath(
                    db, "dli/O19332746152.md"
                )
            ),
            3,
        )
        vault_, _ = self._seed_study("unmanifested_chunk")
        self.addCleanup(vault_.con.close)
        prior = self._seed_lkg(vault_, "unmanifested_chunk")
        result = self._review(
            vault_, "unmanifested_chunk", source_root, db
        )
        self._assert_public(
            result,
            ("AT-RISK", "snapshot_provenance_mismatch", None),
            label="unmanifested_chunk",
        )
        self.assertEqual(self._report(vault_).read_bytes(), prior)
        seen.add("unmanifested_chunk")

        original_dynamic_rows = study_review._dynamic_rows
        for label in (
            "wrong_family",
            "wrong_quote",
            "wrong_marker",
            "wrong_citation",
        ):
            with self.subTest(case=label):
                source_root, db = self._copy_fixture(label)

                def tamper(*args, _label=label):
                    built = original_dynamic_rows(*args)
                    self.assertIsNotNone(built)
                    rows, citations = built
                    target = rows[0]
                    if _label == "wrong_family":
                        target = target.model_copy(
                            update={
                                "selector": target.selector.model_copy(
                                    update={"family": "guidance"}
                                )
                            }
                        )
                    elif _label == "wrong_marker":
                        target = target.model_copy(
                            update={
                                "selector": target.selector.model_copy(
                                    update={"marker": "missing release marker"}
                                )
                            }
                        )
                    elif _label == "wrong_quote":
                        target = target.model_copy(
                            update={
                                "citations": [
                                    target.citations[0].model_copy(
                                        update={"quote": "tampered release quote"}
                                    )
                                ]
                            }
                        )
                    else:
                        target = target.model_copy(
                            update={
                                "citations": [
                                    target.citations[0].model_copy(
                                        update={
                                            "chunk_id": (
                                                "dli/O19332746152.md#999"
                                            )
                                        }
                                    )
                                ]
                            }
                        )
                    return [target, *rows[1:]], citations

                vault_, _ = self._seed_study(label)
                self.addCleanup(vault_.con.close)
                prior = self._seed_lkg(vault_, label)
                result = self._review(
                    vault_,
                    label,
                    source_root,
                    db,
                    dynamic_rows=tamper,
                )
                self._assert_public(
                    result,
                    ("AT-RISK", "grounding_refused", None),
                    label=label,
                )
                self.assertEqual(self._report(vault_).read_bytes(), prior)
                seen.add(label)
        self.assertEqual(seen, _STUDY_GROUPS["provenance"])
        self.assertEqual(len(seen), 10)


class TestIndependentNocAndRegistryReplay(unittest.TestCase):
    """Drive raw NOC rows and completed A evidence against immutable snapshot B."""

    _NOC = "21232"

    def setUp(self) -> None:
        _require_release_prerequisite(
            self, _REAL_DB.is_file(), "corpus database for NOC and registry replay"
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self.temp.name}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.snapshot_a = crs_rules.load_registry_snapshot()
        self.snapshot = self.snapshot_a

    def _new_noc_vault(self, candidate: str) -> vault.Vault:
        vault_ = vault.open_vault(candidate)
        vault.create_candidate(vault_, candidate)
        self.addCleanup(vault_.con.close)
        return vault_

    def _noc_rows(self, vault_: vault.Vault) -> list:
        rows = vault_.con.execute(
            "SELECT value_id FROM extracted_values "
            "WHERE factor_id = 'review.noc' ORDER BY value_id"
        ).fetchall()
        return [
            vault.get_extracted_value(vault_, row["value_id"])
            for row in rows
        ]

    def _generate_noc(self, vault_: vault.Vault, candidate: str) -> dict:
        worksheet = noc_worksheet.generate_worksheet(
            vault_, _REAL_DB, candidate, self._NOC
        )
        self.assertEqual(worksheet["noc_code"], self._NOC)
        self.assertGreater(worksheet["duty_count"], 0)
        self.assertTrue(worksheet["citations"])
        self.assertEqual(
            len(worksheet["value_ids"]), worksheet["duty_count"] + 1
        )
        self.assertTrue(
            all(searchindex.resolve(_REAL_DB, cid) for cid in worksheet["citations"])
        )
        return worksheet

    def _confirm_noc(
        self,
        vault_: vault.Vault,
        value_id: str,
        decision: str = "confirm",
    ) -> None:
        vault.confirm_value(
            vault_,
            value_id,
            decision,
            registry_fingerprint=self.snapshot_a.fingerprint,
        )

    def _review_noc(
        self,
        vault_: vault.Vault,
        code: str | None = None,
        *,
        db: Path = _REAL_DB,
        snapshot: crs_rules.RegistrySnapshot | None = None,
        fingerprint: str | None = None,
    ) -> dict:
        return noc_review.review_noc_duties(
            vault_,
            str(db),
            code or self._NOC,
            registry_snapshot=snapshot or self.snapshot_a,
            registry_fingerprint=fingerprint,
        )

    def _assert_noc_public(
        self,
        result: dict,
        expected: tuple[str, str, int],
        label: str,
    ) -> None:
        self.assertEqual(tuple(result), noc_review.PUBLIC_FIELDS, label)
        self.assertEqual(
            (result["status"], result["reason"], result["confirmed_count"]),
            expected,
            label,
        )
        self.assertIn(result["status"], {"AT-RISK", "GAP", "N/A"}, label)
        self.assertLessEqual(
            result["confirmed_count"], result["duty_count"], label
        )
        for forbidden in (
            "SUBSTANTIATED",
            "crs_points",
            "score",
            "substantiated_points",
            "points",
            "evidence_ids",
            "raw_text",
            "path",
        ):
            self.assertNotIn(forbidden, result, label)

    def _snapshot_b(self) -> crs_rules.RegistrySnapshot:
        registry_a = self.snapshot_a.registry
        donor = next(
            row
            for row in registry_a.rows
            if row.rule_id == "study.r73_definition"
        )
        added = donor.model_copy(
            update={
                "rule_id": "release.registry.drift",
                "factor_ids": ["release.registry.drift"],
            }
        )
        snapshot_b = crs_rules.RegistrySnapshot(
            Registry(rows=[*registry_a.rows, added])
        )
        self.assertEqual(
            len(snapshot_b.registry.rows), len(registry_a.rows) + 1
        )
        self.assertEqual(
            snapshot_b.registry.rows[-1].citations,
            donor.citations,
        )
        self.assertNotEqual(
            snapshot_b.fingerprint, self.snapshot_a.fingerprint
        )
        return snapshot_b

    def test_noc_and_registry_replay_manifests_are_complete(self) -> None:
        self.assertEqual(len(_NOC_RELEASE_CASES), 9)
        self.assertEqual(
            _REGISTRY_REPLAY_SCREENS, {"mec", "policy", "study", "noc"}
        )

    def test_noc_source_confirmation_and_drift_matrix_never_greens(self) -> None:
        seen: set[str] = set()

        missing_vault = self._new_noc_vault("noc-missing")
        missing = self._review_noc(missing_vault, "99999")
        self._assert_noc_public(
            missing, ("N/A", "no_worksheet", 0), "missing"
        )
        self.assertEqual(missing["duty_count"], 0)
        seen.add("missing")

        copied_db = Path(self.temp.name) / "source-unavailable.db"
        shutil.copy2(_REAL_DB, copied_db)
        source_vault = self._new_noc_vault("noc-source-unavailable")
        unavailable = self._review_noc(source_vault, db=copied_db)
        self._assert_noc_public(
            unavailable,
            ("AT-RISK", "noc_source_unavailable", 0),
            "source_unavailable",
        )
        self.assertEqual(unavailable["duty_count"], 0)
        seen.add("source_unavailable")

        expected_by_case = {
            "pending": ("AT-RISK", "unresolved_noc", 0),
            "partial": ("AT-RISK", "unresolved_noc", 1),
            "rejected": ("GAP", "unresolved_noc", 0),
            "layer1_stale": ("AT-RISK", "unresolved_noc", 6),
            "layer2_citation_drift": ("AT-RISK", "unresolved_noc", 6),
            "superseded_duty_sha": ("AT-RISK", "unresolved_noc", 0),
            "all_confirmed_manual": (
                "AT-RISK",
                "duty_review_manual",
                7,
            ),
        }
        for label, expected in expected_by_case.items():
            with self.subTest(case=label):
                candidate = f"noc-{label.replace('_', '-')}"
                vault_ = self._new_noc_vault(candidate)
                worksheet = self._generate_noc(vault_, candidate)
                rows = self._noc_rows(vault_)
                duties = [row for row in rows if row.field_name == "noc_duty"]
                lead = [
                    row
                    for row in rows
                    if row.field_name == "noc_lead_statement"
                ]
                self.assertEqual(len(duties), worksheet["duty_count"])
                self.assertEqual(len(lead), 1)

                if label == "partial":
                    self._confirm_noc(vault_, duties[0].value_id)
                elif label == "rejected":
                    for row in rows:
                        self._confirm_noc(vault_, row.value_id, "reject")
                elif label in {
                    "layer1_stale",
                    "layer2_citation_drift",
                    "all_confirmed_manual",
                }:
                    for row in rows:
                        self._confirm_noc(vault_, row.value_id)
                    if label == "layer1_stale":
                        vault_.con.execute(
                            "UPDATE extracted_values "
                            "SET confirmed_file_sha256 = ? WHERE value_id = ?",
                            ("stale-noc-file", duties[0].value_id),
                        )
                        vault_.con.commit()
                        self.assertTrue(
                            vault.is_stale(vault_, duties[0].value_id)
                        )
                    elif label == "layer2_citation_drift":
                        changed = dict(duties[0].normalized_value)
                        changed["citations"] = [
                            {
                                **fragment,
                                "quote": "citation drift cannot reground",
                            }
                            for fragment in changed["citations"]
                        ]
                        vault_.con.execute(
                            "UPDATE extracted_values "
                            "SET normalized_value_json = ? WHERE value_id = ?",
                            (
                                json.dumps(changed),
                                duties[0].value_id,
                            ),
                        )
                        vault_.con.commit()
                elif label == "superseded_duty_sha":
                    source = duties[0]
                    changed = dict(source.normalized_value)
                    changed["duty_sha"] = "superseded000"
                    old_id = vault.add_extracted_value(
                        vault_,
                        document_id=source.document_id,
                        page_id=source.page_id,
                        factor_id="review.noc",
                        field_name="noc_duty",
                        raw_text=source.raw_text,
                        normalized_value=changed,
                        bbox=None,
                        extractor_confidence=None,
                        quality_flag="ok",
                        extraction_run_id=source.extraction_run_id,
                    )
                    self.assertNotIn(old_id, worksheet["value_ids"])
                    self._confirm_noc(vault_, old_id)

                result = self._review_noc(vault_)
                self._assert_noc_public(result, expected, label)
                self.assertEqual(
                    result["duty_count"], worksheet["duty_count"], label
                )
                self.assertTrue(result["citations"], label)
                seen.add(label)
        self.assertEqual(seen, _NOC_RELEASE_CASES)
        self.assertEqual(len(seen), 9)

    def test_completed_snapshot_a_state_cannot_cross_snapshot_b(self) -> None:
        snapshot_b = self._snapshot_b()
        seen: set[str] = set()

        mec_a = _screen("cec", self.snapshot_a)
        self.assertNotEqual(mec_a.private_report.status, "MEETS")
        evidence_a = _evidence("cec", self.snapshot_a.fingerprint)
        with self.assertRaisesRegex(
            mec_screen.MecGatePreparationError,
            "^MEC evidence fingerprint mismatch$",
        ):
            _screen("cec", snapshot_b, evidence=evidence_a)
        seen.add("mec")

        policy_vault = self._new_noc_vault("registry-policy")
        factor = _policy_factor()
        vault.upsert_profile_factor(policy_vault, factor)
        policy_source = Path(self.temp.name) / "registry-policy.txt"
        policy_source.write_text(
            "independent registry replay policy evidence",
            encoding="utf-8",
        )
        policy_document = vault.import_document(
            policy_vault,
            "registry-policy",
            policy_source,
            doc_type="job_offer",
        )
        policy_run = vault.record_extraction_run(
            policy_vault,
            document_id=policy_document.document_id,
            parser_version=vault.current_parser_version(),
        )
        policy_value = vault.add_extracted_value(
            policy_vault,
            document_id=policy_document.document_id,
            page_id=None,
            factor_id=_POLICY_FACTOR,
            field_name="noc_code",
            raw_text="31100",
            normalized_value="31100",
            bbox=None,
            extractor_confidence=1.0,
            quality_flag="ok",
            extraction_run_id=policy_run,
        )
        vault.confirm_value(
            policy_vault,
            policy_value,
            "confirm",
            registry_fingerprint=self.snapshot_a.fingerprint,
        )
        policy_a = auditor.audit_one(
            policy_vault,
            _POLICY_FACTOR,
            str(_REAL_DB),
            self.snapshot_a.registry,
            spouse_mode=False,
            reference_date="2026-07-20",
            ita_date="2026-07-20",
            prior_cards={},
            registry_fingerprint=self.snapshot_a.fingerprint,
            profile_factors={_POLICY_FACTOR: factor},
        )
        self.assertTrue(policy_a.evidence_ids)
        self.assertNotEqual(policy_a.verdict, "SUBSTANTIATED")
        policy_report = (
            policy_vault.root / "output" / "crs-audit" / "prior-private.json"
        )
        policy_report.parent.mkdir(parents=True)
        policy_report.write_bytes(b"snapshot-a-private-report")
        with (
            mock.patch.object(
                policy_offer,
                "offer_for_program_eligibility",
                side_effect=AssertionError("sidecar must not consume A state"),
            ) as sidecar,
            self.assertRaisesRegex(
                auditor.AuditGroundingError,
                "^supplied registry fingerprint does not match registry$",
            ),
        ):
            auditor.audit_one(
                policy_vault,
                _POLICY_FACTOR,
                str(_REAL_DB),
                snapshot_b.registry,
                spouse_mode=False,
                reference_date="2026-07-20",
                ita_date="2026-07-20",
                prior_cards={},
                registry_fingerprint=self.snapshot_a.fingerprint,
                profile_factors={_POLICY_FACTOR: factor},
            )
        sidecar.assert_not_called()
        self.assertEqual(
            policy_report.read_bytes(), b"snapshot-a-private-report"
        )
        seen.add("policy")

        study_source, study_db = (
            TestIndependentStudyReleaseMatrix._copy_fixture(
                self, "registry-study"
            )
        )
        study_vault, _ = TestIndependentStudyReleaseMatrix._seed_study(
            self, "registry-study"
        )
        study_a = TestIndependentStudyReleaseMatrix._review(
            self,
            study_vault,
            "registry-study",
            study_source,
            study_db,
        )
        self.assertTrue(study_a.report_created)
        study_report = TestIndependentStudyReleaseMatrix._report(
            self, study_vault
        )
        prior_study = study_report.read_bytes()
        self.assertTrue(prior_study)
        with (
            mock.patch.object(
                study_review, "_DLI_SNAPSHOT_ROOT", study_source
            ),
            mock.patch.object(
                study_review, "_today", return_value=date(2026, 7, 19)
            ),
        ):
            study_b = study_review.review_study(
                study_vault,
                study_db,
                candidate_id="registry-study",
                max_age_days=30,
                registry_snapshot=snapshot_b,
            )
        self.assertEqual(tuple(study_b), study_review.PUBLIC_FIELDS)
        self.assertEqual(
            (
                study_b["status"],
                study_b["reason"],
                study_b["as_of"],
            ),
            ("N/A", "no_study_evidence", None),
        )
        self.assertFalse(study_b.report_created)
        self.assertEqual(study_report.read_bytes(), prior_study)
        seen.add("study")

        noc_vault = self._new_noc_vault("registry-noc")
        worksheet = self._generate_noc(noc_vault, "registry-noc")
        for row in self._noc_rows(noc_vault):
            self._confirm_noc(noc_vault, row.value_id)
        noc_a = self._review_noc(noc_vault)
        self._assert_noc_public(
            noc_a,
            ("AT-RISK", "duty_review_manual", worksheet["duty_count"]),
            "noc-a",
        )
        noc_b = self._review_noc(
            noc_vault,
            snapshot=snapshot_b,
            fingerprint=self.snapshot_a.fingerprint,
        )
        self._assert_noc_public(
            noc_b,
            ("AT-RISK", "registry_fingerprint_mismatch", 0),
            "noc-b",
        )
        self.assertEqual(noc_b["duty_count"], 0)
        filtered_b = self._review_noc(noc_vault, snapshot=snapshot_b)
        self._assert_noc_public(
            filtered_b,
            ("AT-RISK", "unresolved_noc", 0),
            "noc-b-filtered",
        )
        seen.add("noc")

        self.assertEqual(seen, _REGISTRY_REPLAY_SCREENS)
        self.assertEqual(len(seen), 4)


class TestIndependentPolicyReleaseMatrix(unittest.TestCase):
    """Drive independent raw POLICY inputs through all three production surfaces."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _policy_registry()
        cls.rows = _policy_rows(cls.registry)
        legacy_to = date.fromisoformat(
            cls.rows[_LEGACY_RULE].volatility.effective_to or ""
        )
        physician_from = date.fromisoformat(
            cls.rows[_PHYSICIAN_RULE].volatility.effective_from or ""
        )
        cls.legacy_in = (legacy_to - timedelta(days=1)).isoformat()
        cls.legacy_out = legacy_to.isoformat()
        cls.post_repeal = (legacy_to + timedelta(days=1)).isoformat()
        cls.physician_in = physician_from.isoformat()
        cls.physician_noc = str(
            cls.rows[_PHYSICIAN_RULE].machine_check.accepted_values[0].value
        )
        cls.nonphysician_noc = "21234"

    def _assert_never_green(
        self,
        label: str,
        *,
        registry: Registry | None = None,
        noc: str | None,
        ita_date: str | None,
        points: int = 200,
        expected_verdict: str,
        expected_reason: str,
        expected_points: int | None,
        expected_rule: str,
    ) -> None:
        active_registry = registry or self.registry
        result = additional_auditor.decide_job_offer(
            _policy_context(
                active_registry,
                noc=noc,
                ita_date=ita_date,
                points=points,
            )
        )
        self.assertEqual(
            (result.verdict, result.reason_code, result.substantiated_points),
            (expected_verdict, expected_reason, expected_points),
            label,
        )
        self.assertEqual(result.rule_ids, (expected_rule,), label)
        self.assertNotEqual(result.verdict, "SUBSTANTIATED", label)
        self.assertIn(result.substantiated_points, (None, 0), label)
        self.assertFalse(bool(result.substantiated_points), label)

        sidecar = policy_offer.offer_for_program_eligibility(
            points, ita_date, active_registry
        )
        self.assertEqual(sidecar["crs_points"], 0, label)
        self.assertEqual(
            sidecar["eligibility_status"],
            "AT-RISK" if points else "N/A",
            label,
        )
        self.assertNotEqual(
            sidecar["eligibility_status"], "SUBSTANTIATED", label
        )

        if points and ita_date is None:
            with self.assertRaisesRegex(ValueError, "Invalid isoformat string"):
                crs_audit.arranged_employment_guard(
                    points, ita_date, active_registry
                )
            return
        guard = crs_audit.arranged_employment_guard(points, ita_date, active_registry)
        self.assertEqual(
            guard["status"], "AT-RISK" if points else "N/A", label
        )
        self.assertIn(guard["points"], (None, 0), label)
        self.assertFalse(bool(guard["points"]), label)
        self.assertNotEqual(guard["status"], "SUBSTANTIATED", label)

    def test_local_policy_rows_and_window_controls_are_nonvacuous(self) -> None:
        self.assertEqual(
            tuple(row.rule_id for row in self.registry.rows),
            (_CURRENT_RULE, _LEGACY_RULE, _PHYSICIAN_RULE),
        )
        self.assertTrue(
            crs_audit.row_in_effect(
                self.rows[_LEGACY_RULE], self.legacy_in
            )
        )
        self.assertFalse(
            crs_audit.row_in_effect(
                self.rows[_LEGACY_RULE], self.legacy_out
            )
        )
        self.assertTrue(
            crs_audit.row_in_effect(
                self.rows[_PHYSICIAN_RULE], self.physician_in
            )
        )
        self.assertNotEqual(
            self.rows[_CURRENT_RULE].citations[0].chunk_id,
            self.rows[_LEGACY_RULE].citations[0].chunk_id,
        )
        self.assertNotEqual(
            self.rows[_LEGACY_RULE].citations[0].chunk_id,
            self.rows[_PHYSICIAN_RULE].citations[0].chunk_id,
        )

    def test_exact_policy_window_and_claim_matrix_never_greens(self) -> None:
        cases = {
            "legacy_in_window": {
                "noc": self.nonphysician_noc,
                "ita_date": self.legacy_in,
                "expected_verdict": "AT-RISK",
                "expected_reason": "arranged_employment_legacy_manual",
                "expected_points": None,
                "expected_rule": _LEGACY_RULE,
            },
            "legacy_out_of_window": {
                "noc": self.nonphysician_noc,
                "ita_date": self.legacy_out,
                "expected_verdict": "AT-RISK",
                "expected_reason": "arranged_employment_current",
                "expected_points": 0,
                "expected_rule": _CURRENT_RULE,
            },
            "post_repeal": {
                "noc": self.nonphysician_noc,
                "ita_date": self.post_repeal,
                "expected_verdict": "AT-RISK",
                "expected_reason": "arranged_employment_current",
                "expected_points": 0,
                "expected_rule": _CURRENT_RULE,
            },
            "physician": {
                "noc": self.physician_noc,
                "ita_date": self.physician_in,
                "expected_verdict": "AT-RISK",
                "expected_reason": "physician_policy_manual",
                "expected_points": None,
                "expected_rule": _PHYSICIAN_RULE,
            },
            "non_physician": {
                "noc": self.nonphysician_noc,
                "ita_date": self.physician_in,
                "expected_verdict": "AT-RISK",
                "expected_reason": "arranged_employment_legacy_manual",
                "expected_points": None,
                "expected_rule": _LEGACY_RULE,
            },
            "no_ita": {
                "noc": self.physician_noc,
                "ita_date": None,
                "expected_verdict": "AT-RISK",
                "expected_reason": "arranged_employment_current",
                "expected_points": 0,
                "expected_rule": _CURRENT_RULE,
            },
            "absent_noc": {
                "noc": None,
                "ita_date": self.legacy_in,
                "expected_verdict": "AT-RISK",
                "expected_reason": "arranged_employment_legacy_manual",
                "expected_points": None,
                "expected_rule": _LEGACY_RULE,
            },
            "zero_claim": {
                "noc": self.physician_noc,
                "ita_date": self.physician_in,
                "points": 0,
                "expected_verdict": "N/A",
                "expected_reason": "no_job_offer_points",
                "expected_points": None,
                "expected_rule": _CURRENT_RULE,
            },
        }
        seen: set[str] = set()
        for label, case in cases.items():
            with self.subTest(case=label):
                self._assert_never_green(label, **case)
            seen.add(label)
        malformed = _policy_registry(malformed_physician_window=True)
        self._assert_never_green(
            "malformed_physician_window",
            registry=malformed,
            noc=self.physician_noc,
            ita_date=self.legacy_in,
            expected_verdict="AT-RISK",
            expected_reason="arranged_employment_legacy_manual",
            expected_points=None,
            expected_rule=_LEGACY_RULE,
        )
        seen.add("malformed_physician_window")
        self.assertEqual(seen, {*cases, "malformed_physician_window"})
        self.assertEqual(len(seen), 9)

    def test_distinct_manual_controls_have_exact_row_citations(self) -> None:
        physician = additional_auditor.decide_job_offer(
            _policy_context(
                self.registry,
                noc=self.physician_noc,
                ita_date=self.physician_in,
            )
        )
        legacy = additional_auditor.decide_job_offer(
            _policy_context(
                self.registry,
                noc=self.nonphysician_noc,
                ita_date=self.legacy_in,
            )
        )
        self.assertEqual(
            (physician.reason_code, physician.rule_ids),
            ("physician_policy_manual", (_PHYSICIAN_RULE,)),
        )
        self.assertEqual(
            (legacy.reason_code, legacy.rule_ids),
            ("arranged_employment_legacy_manual", (_LEGACY_RULE,)),
        )
        physician_citations = {
            citation.chunk_id
            for citation in self.rows[physician.rule_ids[0]].citations
        }
        legacy_citations = {
            citation.chunk_id
            for citation in self.rows[legacy.rule_ids[0]].citations
        }
        self.assertTrue(physician_citations)
        self.assertTrue(legacy_citations)
        self.assertEqual(physician_citations & legacy_citations, set())
        legacy_guard = crs_audit.arranged_employment_guard(
            200, self.legacy_in, self.registry
        )
        self.assertEqual(
            legacy_guard["citation"],
            self.rows[_LEGACY_RULE].citations[0].chunk_id,
        )
        sidecar = policy_offer.offer_for_program_eligibility(
            200, self.post_repeal, self.registry
        )
        self.assertEqual(
            sidecar["citation"],
            self.rows[_CURRENT_RULE].citations[0].chunk_id,
        )

    def _audit_policy_state(self, directory: str, state: str):
        candidate = f"policy-{state.replace('_', '-')}"
        with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": directory}):
            vault_ = vault.open_vault(candidate)
            try:
                vault.create_candidate(vault_, candidate)
                factor = _policy_factor()
                vault.upsert_profile_factor(vault_, factor)
                source = Path(directory) / f"{candidate}.txt"
                source.write_text("independent policy evidence", encoding="utf-8")
                document = vault.import_document(
                    vault_, candidate, source, doc_type="job_offer"
                )
                run_id = vault.record_extraction_run(
                    vault_,
                    document_id=document.document_id,
                    parser_version=vault.current_parser_version(),
                )
                page_id = vault.add_document_page(
                    vault_,
                    document_id=document.document_id,
                    page_number=1,
                    render_sha256="b" * 64,
                    extraction_run_id=run_id,
                )
                value_id = vault.add_extracted_value(
                    vault_,
                    document_id=document.document_id,
                    page_id=page_id,
                    factor_id=_POLICY_FACTOR,
                    field_name="noc_code",
                    raw_text=self.physician_noc,
                    normalized_value=self.physician_noc,
                    bbox=None,
                    extractor_confidence=1.0,
                    quality_flag="low_quality" if state == "low_quality" else "ok",
                    extraction_run_id=run_id,
                )
                fingerprint = crs_rules.registry_fingerprint(self.registry)
                if state == "rejected":
                    vault.confirm_value(
                        vault_,
                        value_id,
                        "reject",
                        registry_fingerprint=fingerprint,
                    )
                elif state != "pending":
                    vault.confirm_value(
                        vault_,
                        value_id,
                        "confirm",
                        registry_fingerprint=fingerprint,
                    )
                stale_column = _STALE_COLUMNS.get(state)
                if stale_column is not None:
                    vault_.con.execute(
                        f"UPDATE extracted_values SET {stale_column} = ? "
                        "WHERE value_id = ?",
                        ("stale-policy-binding", value_id),
                    )
                    vault_.con.commit()
                eligible = vault.audit_eligible_values(
                    vault_,
                    _POLICY_FACTOR,
                    registry_fingerprint=fingerprint,
                )
                card = auditor.audit_one(
                    vault_,
                    _POLICY_FACTOR,
                    str(_REAL_DB),
                    self.registry,
                    spouse_mode=False,
                    reference_date=_OPERATIONAL_AS_OF.isoformat(),
                    ita_date=self.legacy_in,
                    prior_cards={},
                    registry_fingerprint=fingerprint,
                    profile_factors={_POLICY_FACTOR: factor},
                )
                return eligible, card
            finally:
                vault_.con.close()

    def test_pending_rejected_low_quality_and_five_stale_keys_stay_manual(
        self,
    ) -> None:
        _require_release_prerequisite(
            self, _REAL_DB.is_file(), "corpus database for POLICY spine controls"
        )
        expected = set(_EVIDENCE_STATES)
        seen: set[str] = set()
        with tempfile.TemporaryDirectory() as directory:
            confirmed, physician_card = self._audit_policy_state(
                directory, "confirmed"
            )
            self.assertEqual(len(confirmed), 1)
            self.assertEqual(
                (
                    physician_card.verdict,
                    physician_card.reason_code,
                    physician_card.substantiated_points,
                ),
                ("AT-RISK", "physician_policy_manual", None),
            )
            self.assertTrue(physician_card.evidence_ids)

            for state in _EVIDENCE_STATES:
                eligible, card = self._audit_policy_state(directory, state)
                with self.subTest(state=state):
                    self.assertEqual(eligible, [])
                    self.assertEqual(card.evidence_ids, [])
                    self.assertEqual(
                        (
                            card.verdict,
                            card.reason_code,
                            card.substantiated_points,
                        ),
                        (
                            "AT-RISK",
                            "arranged_employment_legacy_manual",
                            None,
                        ),
                    )
                    self.assertNotEqual(card.verdict, "SUBSTANTIATED")
                    self.assertFalse(bool(card.substantiated_points))
                seen.add(state)
        self.assertEqual(seen, expected)
        self.assertEqual(len(seen), 8)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
