"""SAFE-12 privacy, publication, and release-contract conformance proof."""

from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import io
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import unittest
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import tomli
from pydantic import ValidationError

from crawler import (
    audit_report,
    auditor,
    auditors,
    cli,
    crs_audit,
    crs_rules,
    mec_publish,
    mec_screen,
    mecfields,
    noc_review,
    noc_worksheet,
    paths,
    policy_offer,
    searchindex,
    study_review,
    vault,
)
from crawler.models.audit import (
    PrivateAuditReport,
    PublicAuditEnvelope,
    PublicClaim,
)
from crawler.models.mec import (
    MecCounts,
    PrivateMecCriterion,
    PrivateMecReport,
    PublicMecSummary,
    to_public_mec_summary,
)
from crawler.models.crs_rules import Registry
from crawler.models.vault import CrsProfileFactor


pytestmark = pytest.mark.conformance

_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _ROOT / "corpus" / "index.db"
_DLI_ROOT = _ROOT / "corpus" / "dli"

_NAME = "Synthetic Privacy Applicant XQZ"
_VALUE = "Synthetic-value-847263"
_DATE = "1988-12-27"
_EMPLOYER = "Synthetic Employer QZX Holdings"
_PRIVATE_NOC = "99999"
_EVIDENCE_ID = "ev_deadbeefcafefeed"
_CANDIDATE_ID = "privacy-candidate-xqz"
_STATIC_CANARIES = (
    _NAME,
    _VALUE,
    _DATE,
    _EMPLOYER,
    _PRIVATE_NOC,
    _EVIDENCE_ID,
    _CANDIDATE_ID,
)


def _load_publish_safe():
    scripts = str(_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import check_publish_safe

    return check_publish_safe


def _mec_bundle() -> mec_screen.MecPublicationBundle:
    criterion = PrivateMecCriterion(
        criterion_id="cec.work.paid",
        status="AT-RISK",
        reason_code="evidence_missing",
        wired=True,
        grounded=True,
        applicability_grounded=False,
        applicable=None,
        rule_ids=["cec.work.paid"],
        applicant_values={"points": 1},
        evidence_ids=[_EVIDENCE_ID],
        employment_traces=[],
        sidecar_inputs={},
        grid_bounds={},
        completeness_attestations={},
        render_details={},
    )
    report = PrivateMecReport(
        schema_version="1.0",
        run_id="mec_deadbeef0009deadbeef0009deadbeef",
        candidate_id=_CANDIDATE_ID,
        program="cec",
        status="AT-RISK",
        criteria=[criterion],
        counts=MecCounts(criteria=1, at_risk=1),
        registry_fingerprint="a" * 64,
        created_at="2026-07-20T00:00:00Z",
        private_report_path="output/mec/cec/latest.json",
    )
    public = to_public_mec_summary(report, report.private_report_path)
    public = public.model_copy(
        update={
            "criteria": [
                item.model_copy(update={"corpus_citation_ids": []})
                for item in public.criteria
            ]
        },
        deep=True,
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


def _private_study_payload(private_root: Path) -> str:
    return json.dumps(
        {
            "candidate_id": _CANDIDATE_ID,
            "applicant_fields": {
                "applicant_name": _NAME,
                "private_value": _VALUE,
                "date_of_birth": _DATE,
                "employer": _EMPLOYER,
                "noc_code": _PRIVATE_NOC,
                "absolute_root": str(private_root),
            },
            "evidence_ids": {"private_value": [_EVIDENCE_ID]},
            "static_citations": ["guidance/study.md#001"],
            "notice": study_review._NOTICE,
        },
        sort_keys=True,
    )


def _assert_excludes(
    case: unittest.TestCase, text: str, canaries: Iterable[str]
) -> None:
    explicit = tuple(canaries)
    case.assertTrue(explicit, "privacy assertion requires explicit live canaries")
    for canary in explicit:
        case.assertNotIn(canary, text, f"private canary escaped: {canary!r}")


def _assert_private_contains(
    case: unittest.TestCase, text: str, canaries: Iterable[str]
) -> None:
    """Prove each flow canary is live before using it as a leak oracle."""
    for canary in canaries:
        case.assertIn(canary, text, f"private canary is vacuous: {canary!r}")


class TestPrivacyReleaseManifest(unittest.TestCase):
    """Keep every independent privacy/atomic proof load-bearing."""

    def test_privacy_and_atomic_case_manifest_is_exact(self) -> None:
        expected = {
            "test_privacy_public_surfaces_exclude_independent_canaries",
            "test_privacy_dli_snapshot_family_and_index_are_read_only",
            "test_containment_public_models_and_private_targets_fail_closed",
            "test_atomic_mec_failures_preserve_last_known_good",
            "test_atomic_study_failures_preserve_last_known_good",
            "test_privacy_publish_safe_scanner_real_tree_and_positive_controls",
            "test_confirmed_vault_cross_phase_release_flow",
            "test_authoritative_prerequisites_fail_without_path_disclosure",
            "test_confirmed_vault_drift_replay_preserves_all_lkg_reports",
        }
        actual = {
            name
            for cls in (
                TestPrivacyPublicSurfaces,
                TestPrivateContainmentAndAtomicity,
                TestPublishSafeReleaseBoundary,
                TestConfirmedVaultCrossPhaseE2E,
            )
            for name in cls.__dict__
            if name.startswith("test_")
        }
        self.assertEqual(actual, expected)

    def test_supply_chain_framing_and_contract_manifest_is_exact(self) -> None:
        expected = {
            "test_dependency_set_and_lock_hash_are_exact",
            "test_enrolled_import_closure_has_no_network_or_alternate_loader",
            "test_runtime_composition_succeeds_with_socket_denied",
            "test_public_envelope_grid_crs_and_named_hashes_are_frozen",
            "test_rendered_release_artifacts_have_screening_framing",
            "test_affirmative_outcome_denylist_has_positive_control",
        }
        actual = {
            name
            for cls in (
                TestSupplyChainAndNetwork,
                TestFrozenReleaseContracts,
                TestReleaseArtifactFraming,
            )
            for name in cls.__dict__
            if name.startswith("test_")
        }
        self.assertEqual(actual, expected)


class TestPrivacyPublicSurfaces(unittest.TestCase):
    def setUp(self) -> None:
        _require_release_prerequisites(self)

    def test_privacy_public_surfaces_exclude_independent_canaries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            private_root = Path(td)
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": td}):
                candidate = vault.open_vault(_CANDIDATE_ID)
                vault.create_candidate(candidate, _CANDIDATE_ID)
                candidate.con.close()

                stdout, stderr = io.StringIO(), io.StringIO()
                with (
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    rc = cli.main(
                        [
                            "--json",
                            "vault",
                            "noc-review",
                            "--candidate",
                            _CANDIDATE_ID,
                            "--db",
                            str(_REAL_DB),
                            "--noc-code",
                            "21231",
                        ]
                    )
                self.assertEqual(rc, 0, stdout.getvalue() + stderr.getvalue())
                noc_envelope = json.loads(stdout.getvalue())

                study_public = study_review._pack(
                    "AT-RISK",
                    "evidence_missing",
                    confirmed_count=0,
                    eligible_count=0,
                    as_of="2026-07-20",
                )
                audit_public = PublicAuditEnvelope(
                    run_id="aud_deadbeef0009",
                    factor_id="core.work",
                    private_output_path=(
                        "output/crs-audit/aud_deadbeef0009.json"
                    ),
                )
                bundle = _mec_bundle()
                public_surfaces = json.dumps(
                    {
                        "stdout": stdout.getvalue(),
                        "stderr": stderr.getvalue(),
                        "noc": noc_envelope,
                        "study": study_public,
                        "audit": audit_public.model_dump(mode="json"),
                        "mec": json.loads(bundle.public_json),
                    },
                    sort_keys=True,
                )
                mec_publish.publish_mec_bundle(
                    SimpleNamespace(root=private_root), bundle
                )
                study_path = paths.resolve_within(
                    private_root, "output", "study-review", "latest.json"
                )
                study_review._publish_private_report(
                    study_path, _private_study_payload(private_root)
                )
                private_bytes = (
                    (private_root / "output/mec/cec/latest.json").read_text()
                    + (private_root / "output/mec/cec/latest.md").read_text()
                    + study_path.read_text()
                )
                canaries = (*_STATIC_CANARIES, str(private_root))
                _assert_private_contains(self, private_bytes, canaries)
                _assert_excludes(self, public_surfaces, canaries)

    def test_privacy_dli_snapshot_family_and_index_are_read_only(self) -> None:
        tracked = sorted(_DLI_ROOT.glob("*.md")) + [_DLI_ROOT / "manifest.json"]
        self.assertTrue(all(path.is_file() for path in tracked))
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (*tracked, _REAL_DB)
        }
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": td}):
                candidate = vault.open_vault(_CANDIDATE_ID)
                vault.create_candidate(candidate, _CANDIDATE_ID)
                try:
                    result = study_review.review_study(
                        candidate,
                        _REAL_DB,
                        candidate_id=_CANDIDATE_ID,
                        max_age_days=30,
                    )
                    _assert_excludes(
                        self,
                        json.dumps(result, sort_keys=True),
                        (*_STATIC_CANARIES, str(Path(td))),
                    )
                finally:
                    candidate.con.close()

            forbidden = tuple(
                value.encode() for value in (*_STATIC_CANARIES, td, "ev_")
            )
            for path in (*tracked, _REAL_DB):
                raw = path.read_bytes()
                with self.subTest(path=path):
                    for canary in forbidden:
                        self.assertNotIn(canary, raw)
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (*tracked, _REAL_DB)
        }
        self.assertEqual(after, before)


def _require_release_prerequisites(
    case: unittest.TestCase,
    *,
    overrides: dict[str, bool] | None = None,
) -> None:
    """Skip honestly for local runs, but fail authoritatively with safe labels."""
    manifest: dict = {}
    manifest_path = _DLI_ROOT / "manifest.json"
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            manifest = {}
    entries = manifest.get("files")
    canonical_files = (
        isinstance(entries, list)
        and bool(entries)
        and all(
            isinstance(entry, dict)
            and isinstance(entry.get("file"), str)
            and (_DLI_ROOT / entry["file"]).is_file()
            for entry in entries
        )
    )
    canonical_chunks = False
    if _REAL_DB.is_file() and isinstance(entries, list) and entries:
        try:
            with sqlite3.connect(f"file:{_REAL_DB}?mode=ro", uri=True) as con:
                indexed = {
                    row[0]
                    for row in con.execute(
                        "SELECT DISTINCT relpath FROM chunks "
                        "WHERE relpath LIKE 'dli/%'"
                    )
                }
            expected = {
                f"dli/{entry['file']}"
                for entry in entries
                if isinstance(entry, dict)
                and isinstance(entry.get("file"), str)
            }
            canonical_chunks = bool(expected) and expected <= indexed
        except (OSError, sqlite3.Error, TypeError, ValueError):
            canonical_chunks = False

    checks = {
        "corpus index": _REAL_DB.is_file(),
        "DLI family": _DLI_ROOT.is_dir() and any(_DLI_ROOT.glob("*.md")),
        "DLI manifest": bool(manifest),
        "DLI canonical files": canonical_files,
        "DLI canonical chunks": canonical_chunks,
        "confirmed vault fixture": True,
    }
    checks.update(overrides or {})
    for label, available in checks.items():
        if available:
            continue
        message = f"release prerequisite unavailable: {label}"
        if os.environ.get("PR_CONFORMANCE_RUNNER") == "1":
            case.fail(message)
        case.skipTest(message)


class TestConfirmedVaultCrossPhaseE2E(unittest.TestCase):
    """One real pending→confirmed vault drives every v5 release boundary."""

    _CANDIDATE = "confirmed-vault-e2e"
    _NOC = "21231"
    _DLI = "O19332746152"
    _INSTITUTION = "E2E Private Institution Canary 46-XQZ"
    _AS_OF = "2026-07-16T18:08:26Z"

    def setUp(self) -> None:
        _require_release_prerequisites(self)
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name}
        )
        self._env.start()
        self.snapshot = crs_rules.load_registry_snapshot()
        self.private = vault.open_vault(self._CANDIDATE)
        vault.create_candidate(self.private, self._CANDIDATE)
        self._serial = 0
        self._seeded_value_ids: list[str] = []
        self._seeded_evidence_ids: list[str] = []

    def tearDown(self) -> None:
        self.private.con.close()
        self._env.stop()
        self._tmp.cleanup()

    def _confirmed_field(
        self,
        *,
        factor_id: str,
        doc_type: str,
        field_name: str,
        value,
        raw_text: str | None = None,
    ) -> str:
        """Use every shipped vault write, proving quarantine before confirmation."""
        self._serial += 1
        token = f"{self._serial:03d}-{factor_id}-{field_name}"
        source = Path(self._tmp.name) / f"source-{self._serial:03d}.pdf"
        source.write_bytes(
            b"%PDF-1.4\n"
            + token.encode("utf-8")
            + b"\n"
            + _VALUE.encode("utf-8")
        )
        document = vault.import_document(
            self.private, self._CANDIDATE, source, doc_type=doc_type
        )
        run_id = vault.record_extraction_run(
            self.private,
            document_id=document.document_id,
            parser_version=vault.current_parser_version(),
            engine_json={"fixture": token},
            status="complete",
        )
        render_sha = hashlib.sha256(f"render:{token}".encode()).hexdigest()
        page_id = vault.add_document_page(
            self.private,
            document_id=document.document_id,
            page_number=1,
            image_relpath=f"files/rendered/{token}/page-0001.png",
            render_sha256=render_sha,
            extraction_run_id=run_id,
        )
        value_id = vault.add_extracted_value(
            self.private,
            document_id=document.document_id,
            page_id=page_id,
            factor_id=factor_id,
            field_name=field_name,
            raw_text=str(value) if raw_text is None else raw_text,
            normalized_value=value,
            bbox=None,
            extractor_confidence=1.0,
            quality_flag="ok",
            extraction_run_id=run_id,
        )
        pending = vault.get_extracted_value(self.private, value_id)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.confirmation_status, "pending")
        vault.confirm_value(
            self.private,
            value_id,
            "confirm",
            registry_fingerprint=self.snapshot.fingerprint,
        )
        self.assertTrue(
            vault.is_audit_eligible(
                self.private,
                value_id,
                registry_fingerprint=self.snapshot.fingerprint,
            )
        )
        self._seeded_value_ids.append(value_id)
        return value_id

    def _seed_real_inputs(self) -> str:
        factors = (
            CrsProfileFactor(
                factor_id="core.age",
                factor_group="core_human_capital",
                claimed_points=66,
                claimed_value=str(self.private.root),
            ),
            CrsProfileFactor(
                factor_id="additional.job_offer",
                factor_group="additional_points",
                claimed_points=200,
                claimed_value=200,
            ),
            CrsProfileFactor(
                factor_id="review.study",
                factor_group="additional_points",
                claimed_value={"institution": _NAME},
            ),
            CrsProfileFactor(
                factor_id="review.mec",
                factor_group="program_eligibility",
                claimed_value={},
            ),
        )
        for factor in factors:
            vault.upsert_profile_factor(self.private, factor)

        self._confirmed_field(
            factor_id="core.age",
            doc_type="passport",
            field_name="date_of_birth",
            value=_DATE,
        )
        self._confirmed_field(
            factor_id="additional.job_offer",
            doc_type="job_offer",
            field_name="noc_code",
            value="31100",
            raw_text=_EMPLOYER,
        )
        study_values = {
            "institution_name": f"{self._INSTITUTION}::{self.private.root}",
            "dli_number": self._DLI,
            "credential_level": "3+",
            "program_start": "2022-09-15",
            "program_end": "2026-04-30",
            "study_status": "graduated",
        }
        for field_name, value in study_values.items():
            self._confirmed_field(
                factor_id="review.study",
                doc_type="study_proof",
                field_name=field_name,
                value=value,
            )
        mec_values = (
            ("mec-profile", "eligibility_reference_date", "2026-06-15"),
            ("mec-profile", "work_history_scope_complete", True),
            ("mec-profile", "education_scope_complete", True),
            ("mec-profile", "language_scope_complete", True),
            ("mec-profile", "offer_certificate_scope_complete", True),
            ("mec-profile", "adaptability_scope_complete", True),
            ("mec-valid-offer", "offer_full_time", True),
            ("mec-province-status", "intended_destination_province", "ON"),
        )
        for doc_type, field_name, value in mec_values:
            self._confirmed_field(
                factor_id="review.mec",
                doc_type=doc_type,
                field_name=field_name,
                value=value,
            )

        placeholders = ",".join("?" for _ in self._seeded_value_ids)
        rows = self.private.con.execute(
            "SELECT ev.value_id, ev.confirmation_status, "
            "ev.confirmed_rule_registry_version, ev.extraction_run_id, "
            "d.evidence_id, d.file_sha256, p.render_sha256 "
            "FROM extracted_values ev "
            "JOIN documents d ON d.document_id = ev.document_id "
            "JOIN document_pages p ON p.page_id = ev.page_id "
            f"WHERE ev.value_id IN ({placeholders})",
            tuple(self._seeded_value_ids),
        ).fetchall()
        self.assertEqual(len(rows), 16)
        self.assertEqual({row["confirmation_status"] for row in rows}, {"confirmed"})
        self.assertEqual(
            {row["confirmed_rule_registry_version"] for row in rows},
            {self.snapshot.fingerprint},
        )
        for column in (
            "value_id",
            "extraction_run_id",
            "evidence_id",
            "file_sha256",
            "render_sha256",
        ):
            self.assertEqual(len({row[column] for row in rows}), 16, column)
        self._seeded_evidence_ids = [row["evidence_id"] for row in rows]

        ita = vault.set_ita_round(
            self.private,
            self._CANDIDATE,
            "authoritative-e2e",
            "2026-07-20",
            "EE",
            cutoff_score=500,
        )
        return ita.round_id

    def test_confirmed_vault_cross_phase_release_flow(self) -> None:
        round_id = self._seed_real_inputs()
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch.object(
                socket,
                "socket",
                side_effect=AssertionError("network forbidden"),
            ),
        ):
            before_report, before_public = audit_report.run_full_audit_report(
                self.private,
                _REAL_DB,
                self.snapshot.registry,
                ita_round_id=round_id,
                registry_fingerprint=self.snapshot.fingerprint,
            )
            before_path = (
                self.private.root
                / "output"
                / "crs-audit"
                / f"{before_report.run_id}.json"
            )
            before_bytes = before_path.read_bytes()

            policy = policy_offer.offer_for_program_eligibility(
                True, "2026-07-20", self.snapshot.registry
            )
            study = study_review.review_study(
                self.private,
                _REAL_DB,
                candidate_id=self._CANDIDATE,
                max_age_days=30,
                registry_snapshot=self.snapshot,
            )
            worksheet = noc_worksheet.generate_worksheet(
                self.private, _REAL_DB, self._CANDIDATE, self._NOC
            )
            self.assertEqual(
                len(worksheet["value_ids"]), worksheet["duty_count"] + 1
            )
            for value_id in worksheet["value_ids"]:
                self.assertEqual(
                    vault.get_extracted_value(
                        self.private, value_id
                    ).confirmation_status,
                    "pending",
                )
                vault.confirm_value(
                    self.private,
                    value_id,
                    "confirm",
                    registry_fingerprint=self.snapshot.fingerprint,
                )
            noc = noc_review.review_noc_duties(
                self.private,
                str(_REAL_DB),
                self._NOC,
                candidate_id=self._CANDIDATE,
                registry_snapshot=self.snapshot,
                registry_fingerprint=self.snapshot.fingerprint,
            )

            evidence = mecfields.load_mec_evidence(
                self.private, self._CANDIDATE, self.snapshot.fingerprint
            )
            context = mec_screen.prepare_mec_gate(
                "fsw",
                self.snapshot,
                _REAL_DB,
                date(2026, 6, 15),
                120,
                as_of=date(2026, 7, 20),
            )
            confirmed_inputs = mec_screen.build_confirmed_mec_inputs(
                "fsw", context, evidence, self.private, _REAL_DB
            )
            bundle = mec_screen.screen_mec(
                "fsw",
                context,
                evidence,
                confirmed_inputs,
                vault_=self.private,
                db=_REAL_DB,
                study_max_age_days=30,
                run_id="mec_deadbeef0010deadbeef0010deadbeef",
                created_at="2026-07-20T00:00:00Z",
                private_output_path="output/mec/fsw/latest.json",
            )
            mec_public = mec_publish.publish_mec_bundle(self.private, bundle)

            after_report, after_public = audit_report.run_full_audit_report(
                self.private,
                _REAL_DB,
                self.snapshot.registry,
                ita_round_id=round_id,
                registry_fingerprint=self.snapshot.fingerprint,
            )

        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(tuple(policy), policy_offer.PUBLIC_FIELDS)
        self.assertEqual(
            (
                policy["eligibility_status"],
                policy["reason"],
                policy["crs_points"],
                policy["citation"],
            ),
            (
                "AT-RISK",
                "offer_for_eligibility_manual",
                0,
                "guidance/job-offer.md#001",
            ),
        )
        self.assertEqual(tuple(study), study_review.PUBLIC_FIELDS)
        self.assertEqual(
            (
                study["status"],
                study["reason"],
                study["required_count"],
                study["confirmed_count"],
                study["eligible_count"],
                study["as_of"],
            ),
            (
                "AT-RISK",
                "designation_historical_unproven",
                5,
                6,
                6,
                self._AS_OF,
            ),
        )
        self.assertTrue(study.report_created)
        self.assertEqual(study.registry_fingerprint, self.snapshot.fingerprint)
        self.assertEqual(tuple(noc), noc_review.PUBLIC_FIELDS)
        self.assertEqual(
            (
                noc["noc_code"],
                noc["duty_count"],
                noc["confirmed_count"],
                noc["status"],
                noc["reason"],
                noc["citations"],
            ),
            (
                "21231",
                6,
                6,
                "AT-RISK",
                "duty_review_manual",
                [
                    "noc-2021/noc-21231.md#001",
                    "noc-2021/noc-21231.md#002",
                    "noc-2021/noc-21231.md#003",
                ],
            ),
        )
        self.assertTrue(
            all(searchindex.resolve(_REAL_DB, cid) for cid in noc["citations"])
        )

        self.assertEqual(bundle.private_report.program, "fsw")
        self.assertEqual(bundle.private_report.status, "AT-RISK")
        self.assertEqual(bundle.private_report.counts.criteria, 17)
        self.assertGreater(bundle.private_report.counts.passed, 0)
        self.assertEqual(
            bundle.private_report.registry_fingerprint, self.snapshot.fingerprint
        )
        self.assertEqual(mec_public.model_dump(), bundle.public_summary.model_dump())
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

        self.assertEqual(
            [card.model_dump() for card in before_report.factor_cards],
            [card.model_dump() for card in after_report.factor_cards],
        )
        self.assertEqual(
            (
                before_report.substantiated_total,
                before_report.cutoff_delta,
                before_report.meets_cutoff,
            ),
            (
                after_report.substantiated_total,
                after_report.cutoff_delta,
                after_report.meets_cutoff,
            ),
        )
        self.assertEqual(
            (
                [item.model_dump() for item in before_public.verdicts],
                [item.model_dump() for item in before_public.claims],
                before_public.counts,
            ),
            (
                [item.model_dump() for item in after_public.verdicts],
                [item.model_dump() for item in after_public.claims],
                after_public.counts,
            ),
        )
        self.assertEqual(before_path.read_bytes(), before_bytes)
        self.assertEqual(
            before_report.registry_fingerprint, self.snapshot.fingerprint
        )
        self.assertGreater(len(before_report.factor_cards), 0)
        self.assertGreater(len(before_public.claims), 0)

        # Scan complete, unmodified public envelopes, including their opaque
        # candidate-root-relative locators.
        crs_before_projection = before_public.model_dump(mode="json")
        crs_after_projection = after_public.model_dump(mode="json")
        for projection in (crs_before_projection, crs_after_projection):
            locator = projection["private_output_path"]
            self.assertFalse(Path(locator).is_absolute())
            self.assertTrue(locator.startswith("output/crs-audit/"))
            self.assertNotIn(self._CANDIDATE, locator)
            self.assertNotIn(str(self.private.root), locator)

        public_blob = json.dumps(
            {
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
                "policy": policy,
                "study": study,
                "noc": noc,
                "mec": mec_public.model_dump(mode="json"),
                "crs_before": crs_before_projection,
                "crs_after": crs_after_projection,
            },
            sort_keys=True,
        )
        private_outputs = b"\n".join(
            path.read_bytes()
            for path in sorted((self.private.root / "output").rglob("*"))
            if path.is_file()
        ).decode("utf-8")
        private_database = "\n".join(self.private.con.iterdump())
        flow_canaries = (
            self._CANDIDATE,
            self._DLI,
            self._INSTITUTION,
            *self._seeded_evidence_ids,
            str(self.private.root),
        )
        _assert_private_contains(
            self, private_database + "\n" + private_outputs, flow_canaries
        )
        public_snapshot = json.dumps(
            {
                "policy": policy,
                "study": study,
                "noc": noc,
                "mec": mec_public.model_dump(mode="json"),
                "crs_before": crs_before_projection,
                "crs_after": crs_after_projection,
            },
            sort_keys=True,
        )
        _assert_excludes(
            self,
            public_blob + "\n" + public_snapshot,
            flow_canaries,
        )

    def test_authoritative_prerequisites_fail_without_path_disclosure(self) -> None:
        labels = (
            "corpus index",
            "DLI family",
            "DLI manifest",
            "DLI canonical files",
            "DLI canonical chunks",
            "confirmed vault fixture",
        )
        for label in labels:
            with self.subTest(mode="normal", prerequisite=label):
                with (
                    mock.patch.dict(
                        os.environ, {"PR_CONFORMANCE_RUNNER": "0"}
                    ),
                    self.assertRaises(unittest.SkipTest) as skipped,
                ):
                    _require_release_prerequisites(
                        self, overrides={label: False}
                    )
                self.assertEqual(
                    str(skipped.exception),
                    f"release prerequisite unavailable: {label}",
                )
            with self.subTest(mode="authoritative", prerequisite=label):
                with (
                    mock.patch.dict(
                        os.environ, {"PR_CONFORMANCE_RUNNER": "1"}
                    ),
                    self.assertRaises(AssertionError) as failed,
                ):
                    _require_release_prerequisites(
                        self, overrides={label: False}
                    )
                message = str(failed.exception)
                self.assertEqual(
                    message, f"release prerequisite unavailable: {label}"
                )
                self.assertNotIn(str(_ROOT), message)
                self.assertNotIn(str(self.private.root), message)
                self.assertNotIn("ev_", message)

    def test_confirmed_vault_drift_replay_preserves_all_lkg_reports(self) -> None:
        round_id = self._seed_real_inputs()
        worksheet = noc_worksheet.generate_worksheet(
            self.private, _REAL_DB, self._CANDIDATE, self._NOC
        )
        self.assertEqual(worksheet["duty_count"], 6)
        for value_id in worksheet["value_ids"]:
            self.assertEqual(
                vault.get_extracted_value(
                    self.private, value_id
                ).confirmation_status,
                "pending",
            )
            vault.confirm_value(
                self.private,
                value_id,
                "confirm",
                registry_fingerprint=self.snapshot.fingerprint,
            )

        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network forbidden"),
        ):
            study_a = study_review.review_study(
                self.private,
                _REAL_DB,
                candidate_id=self._CANDIDATE,
                max_age_days=30,
                registry_snapshot=self.snapshot,
            )
            noc_a = noc_review.review_noc_duties(
                self.private,
                str(_REAL_DB),
                self._NOC,
                registry_snapshot=self.snapshot,
                registry_fingerprint=self.snapshot.fingerprint,
            )
            evidence_a = mecfields.load_mec_evidence(
                self.private, self._CANDIDATE, self.snapshot.fingerprint
            )
            context_a = mec_screen.prepare_mec_gate(
                "fsw",
                self.snapshot,
                _REAL_DB,
                date(2026, 6, 15),
                120,
                as_of=date(2026, 7, 20),
            )
            inputs_a = mec_screen.build_confirmed_mec_inputs(
                "fsw", context_a, evidence_a, self.private, _REAL_DB
            )
            bundle_a = mec_screen.screen_mec(
                "fsw",
                context_a,
                evidence_a,
                inputs_a,
                vault_=self.private,
                db=_REAL_DB,
                study_max_age_days=30,
                run_id="mec_deadbeef0011deadbeef0011deadbeef",
                created_at="2026-07-20T00:00:00Z",
                private_output_path="output/mec/fsw/latest.json",
            )
            mec_publish.publish_mec_bundle(self.private, bundle_a)
            crs_a, _ = audit_report.run_full_audit_report(
                self.private,
                _REAL_DB,
                self.snapshot.registry,
                ita_round_id=round_id,
                registry_fingerprint=self.snapshot.fingerprint,
            )

        self.assertTrue(study_a.report_created)
        self.assertEqual(
            (study_a["status"], study_a["reason"]),
            ("AT-RISK", "designation_historical_unproven"),
        )
        self.assertEqual(
            (noc_a["status"], noc_a["reason"], noc_a["confirmed_count"]),
            ("AT-RISK", "duty_review_manual", 6),
        )
        self.assertEqual(bundle_a.private_report.status, "AT-RISK")
        self.assertTrue(
            any(card.evidence_ids for card in crs_a.factor_cards)
        )
        output_root = self.private.root / "output"
        lkg = {
            path.relative_to(output_root).as_posix(): path.read_bytes()
            for path in sorted(output_root.rglob("*"))
            if path.is_file()
        }
        self.assertGreaterEqual(len(lkg), 6)

        registry_a = self.snapshot.registry
        changed_rows = []
        mutated_count = 0
        for row in registry_a.rows:
            if row.rule_id == "additional.job_offer.current":
                row = row.model_copy(
                    update={
                        "claim_text": (
                            row.claim_text
                            + " Snapshot-B registry replay mutation."
                        )
                    }
                )
                mutated_count += 1
            changed_rows.append(row)
        self.assertEqual(mutated_count, 1)
        snapshot_b = crs_rules.RegistrySnapshot(Registry(rows=changed_rows))
        self.assertEqual(len(snapshot_b.registry.rows), 76)
        self.assertNotEqual(snapshot_b.fingerprint, self.snapshot.fingerprint)

        copied_index = Path(self._tmp.name) / "snapshot-b-index.db"
        shutil.copy2(_REAL_DB, copied_index)
        relpath = f"dli/{self._DLI}.md"
        before_rows = searchindex.canonical_rows_for_relpath(
            copied_index, relpath
        )
        self.assertGreaterEqual(len(before_rows), 2)
        with sqlite3.connect(copied_index) as con:
            changed = con.execute(
                "UPDATE chunks SET crawl_date = ? WHERE relpath = ?",
                ("2026-07-15T00:00:00Z", relpath),
            ).rowcount
            con.commit()
        after_rows = searchindex.canonical_rows_for_relpath(
            copied_index, relpath
        )
        self.assertEqual(changed, len(before_rows))
        self.assertEqual(len(after_rows), len(before_rows))
        self.assertNotEqual(
            {row["crawl_date"] for row in after_rows},
            {row["crawl_date"] for row in before_rows},
        )

        all_confirmed = self.private.con.execute(
            "SELECT value_id FROM extracted_values "
            "WHERE confirmation_status = 'confirmed'"
        ).fetchall()
        self.assertGreater(len(all_confirmed), 16)
        self.assertFalse(
            any(
                vault.is_audit_eligible(
                    self.private,
                    row["value_id"],
                    registry_fingerprint=snapshot_b.fingerprint,
                )
                for row in all_confirmed
            )
        )

        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("network forbidden"),
        ):
            evidence_b = mecfields.load_mec_evidence(
                self.private, self._CANDIDATE, snapshot_b.fingerprint
            )
            self.assertEqual(dict(evidence_b.scalars), {})
            self.assertEqual(evidence_b.periods, ())
            context_b = mec_screen.prepare_mec_gate(
                "fsw",
                snapshot_b,
                copied_index,
                date(2026, 6, 15),
                120,
                as_of=date(2026, 7, 20),
            )
            inputs_b = mec_screen.build_confirmed_mec_inputs(
                "fsw", context_b, evidence_b, self.private, copied_index
            )
            bundle_b = mec_screen.screen_mec(
                "fsw",
                context_b,
                evidence_b,
                inputs_b,
                vault_=self.private,
                db=copied_index,
                study_max_age_days=30,
                run_id="mec_deadbeef0012deadbeef0012deadbeef",
                created_at="2026-07-20T00:00:00Z",
                private_output_path="output/mec/fsw/latest.json",
            )

            profile = {
                item.factor_id: item
                for item in vault.load_profile_factors(self.private)
            }
            policy_b = auditor.audit_one(
                self.private,
                "additional.job_offer",
                copied_index,
                snapshot_b.registry,
                spouse_mode=False,
                reference_date="2026-07-20",
                ita_date="2026-07-20",
                prior_cards={},
                registry_fingerprint=snapshot_b.fingerprint,
                profile_factors=profile,
            )
            study_registry_b = study_review.review_study(
                self.private,
                _REAL_DB,
                candidate_id=self._CANDIDATE,
                max_age_days=30,
                registry_snapshot=snapshot_b,
            )
            study_index_b = study_review.review_study(
                self.private,
                copied_index,
                candidate_id=self._CANDIDATE,
                max_age_days=30,
                registry_snapshot=self.snapshot,
            )
            noc_b = noc_review.review_noc_duties(
                self.private,
                str(copied_index),
                self._NOC,
                registry_snapshot=snapshot_b,
                registry_fingerprint=self.snapshot.fingerprint,
            )
            crs_b = auditor.run_full_audit(
                self.private,
                copied_index,
                snapshot_b.registry,
                ita_round_id=round_id,
                registry_fingerprint=snapshot_b.fingerprint,
            )

        self.assertEqual(bundle_b.private_report.status, "AT-RISK")
        self.assertNotEqual(bundle_b.private_report.status, "MEETS")
        self.assertEqual(
            bundle_b.private_report.run_id,
            "mec_deadbeef0012deadbeef0012deadbeef",
        )
        self.assertEqual(
            (policy_b.verdict, policy_b.reason_code, policy_b.evidence_ids),
            ("AT-RISK", "arranged_employment_current", []),
        )
        self.assertEqual(
            (
                study_registry_b["status"],
                study_registry_b["reason"],
                study_registry_b["confirmed_count"],
                study_registry_b["eligible_count"],
            ),
            ("N/A", "no_study_evidence", 6, 0),
        )
        self.assertEqual(
            (
                study_index_b["status"],
                study_index_b["reason"],
                study_index_b["as_of"],
            ),
            ("AT-RISK", "snapshot_provenance_mismatch", None),
        )
        self.assertEqual(
            (
                noc_b["status"],
                noc_b["reason"],
                noc_b["confirmed_count"],
            ),
            ("AT-RISK", "registry_fingerprint_mismatch", 0),
        )
        core_age_b = next(
            card for card in crs_b.factor_cards if card.factor_id == "core.age"
        )
        self.assertEqual(
            (core_age_b.verdict, core_age_b.reason_code, core_age_b.evidence_ids),
            ("GAP", "missing_evidence", []),
        )
        after_lkg = {
            path.relative_to(output_root).as_posix(): path.read_bytes()
            for path in sorted(output_root.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(after_lkg, lkg)

        refusal_blob = json.dumps(
            {
                "mec": bundle_b.public_summary.model_dump(mode="json"),
                "policy": policy_b.model_dump(mode="json"),
                "study_registry": study_registry_b,
                "study_index": study_index_b,
                "noc": noc_b,
            },
            sort_keys=True,
        )
        _assert_excludes(
            self,
            refusal_blob,
            (
                self._CANDIDATE,
                self._DLI,
                self._INSTITUTION,
                *self._seeded_evidence_ids,
                str(self.private.root),
            ),
        )


class TestPrivateContainmentAndAtomicity(unittest.TestCase):
    def test_containment_public_models_and_private_targets_fail_closed(self) -> None:
        base = {
            "run_id": "aud_private_release",
            "factor_id": "core.work",
            "private_output_path": "output/crs-audit/aud_private_release.json",
        }
        for hostile in (
            {"applicant_name": _NAME},
            {"evidence_id": _EVIDENCE_ID},
            {
                "private_output_path": (
                    "candidates/default/output/crs-audit/aud_private_release.json"
                )
            },
            {"private_output_path": "../outside.json"},
            {"private_output_path": "/private/outside.json"},
        ):
            with self.subTest(hostile=hostile), self.assertRaises(ValidationError):
                PublicAuditEnvelope.model_validate({**base, **hostile})
        with self.assertRaises(ValidationError):
            PublicClaim(
                claim_text="synthetic",
                citation_id=_EVIDENCE_ID,
                verdict="AT-RISK",
            )
        with self.assertRaises(ValidationError):
            PublicMecSummary.model_validate(
                {
                    **_mec_bundle().public_summary.model_dump(mode="json"),
                    "applicant_name": _NAME,
                }
            )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            targets = (
                paths.resolve_within(root, "output", "mec", "cec", "latest.json"),
                study_review._latest_report_path(root),
                paths.resolve_within(
                    root, "output", "noc-worksheets", "noc-21231.md"
                ),
                paths.resolve_within(
                    root, "output", "crs-audit", "aud_private_release.json"
                ),
            )
            for target in targets:
                self.assertTrue(target.is_relative_to(root))
            for hostile in ("../escape.json", "/private/escape.json"):
                with self.assertRaises(paths.PathEscapeError):
                    paths.resolve_within(root, hostile)

            outside = root.parent / f"{root.name}-outside"
            outside.mkdir()
            link = root / "link"
            link.symlink_to(outside, target_is_directory=True)
            try:
                with self.assertRaises(paths.PathEscapeError):
                    paths.resolve_within(root, "link", "escape.json")
            finally:
                link.unlink()
                outside.rmdir()

    def test_atomic_mec_failures_preserve_last_known_good(self) -> None:
        module = mec_publish
        source = (
            "def _cmd_vault_screen_mec"
            + __import__("inspect").getsource(cli._cmd_vault_screen_mec)
        )
        self.assertLess(
            source.index("publish_mec_bundle"),
            source.rindex("_vault_ok"),
            "public success must follow durable publication",
        )
        seams = (
            ("_validate_and_render", 1),
            ("_scan_private_bytes", 1),
            ("_scan_public_bytes", 1),
            ("_stage_bytes", 1),
            ("_stage_bytes", 2),
            ("_replace", 1),
            ("_replace", 2),
            ("_replace", 3),
            ("_replace", 4),
            ("_fsync_dir", 1),
        )
        for seam, fail_at in seams:
            with self.subTest(seam=seam, fail_at=fail_at):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    directory = root / "output" / "mec" / "cec"
                    directory.mkdir(parents=True)
                    json_path = directory / "latest.json"
                    markdown_path = directory / "latest.md"
                    old = (b'{"lkg":"private-json"}', b"# private LKG\n")
                    json_path.write_bytes(old[0])
                    markdown_path.write_bytes(old[1])
                    original = getattr(module, seam)
                    calls = 0

                    def injected(*args, **kwargs):
                        nonlocal calls
                        calls += 1
                        if calls == fail_at:
                            raise OSError("injected private failure")
                        return original(*args, **kwargs)

                    with (
                        mock.patch.object(module, seam, side_effect=injected),
                        self.assertRaises(mec_publish.MecPublicationError),
                    ):
                        mec_publish.publish_mec_bundle(
                            SimpleNamespace(root=root), _mec_bundle()
                        )
                    self.assertEqual(json_path.read_bytes(), old[0])
                    self.assertEqual(markdown_path.read_bytes(), old[1])
                    self.assertEqual(
                        [item for item in directory.iterdir() if item.name[0] == "."],
                        [],
                    )

    def test_atomic_study_failures_preserve_last_known_good(self) -> None:
        seams = (
            ("crawler.study_review.tempfile.mkstemp", 1),
            ("crawler.study_review.tempfile.mkstemp", 2),
            ("crawler.study_review._write_report_payload", 1),
            ("crawler.study_review.os.replace", 1),
            ("crawler.paths.fsync_dir", 1),
            ("crawler.paths.fsync_dir", 2),
        )
        for target, fail_at in seams:
            with self.subTest(
                target=target, fail_at=fail_at
            ), tempfile.TemporaryDirectory() as td:
                report = (
                    Path(td) / "output" / "study-review" / "latest.json"
                )
                report.parent.mkdir(parents=True)
                prior = b'{"lkg":"study-private"}\n'
                report.write_bytes(prior)
                original = mock.patch(target).get_original()[0]
                calls = 0

                def injected(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise OSError("injected private failure")
                    return original(*args, **kwargs)

                with (
                    mock.patch(target, side_effect=injected),
                    self.assertRaises(study_review.StudyReportPersistenceError),
                ):
                    study_review._publish_private_report(
                        report, _private_study_payload(Path(td))
                    )
                self.assertEqual(report.read_bytes(), prior)
                self.assertEqual(list(report.parent.glob(".latest-*.tmp")), [])
                self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])


class TestPublishSafeReleaseBoundary(unittest.TestCase):
    def test_privacy_publish_safe_scanner_real_tree_and_positive_controls(
        self,
    ) -> None:
        scanner = _load_publish_safe()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = scanner.main()
        self.assertEqual(rc, 0, stdout.getvalue())
        self.assertIn("0 violations", stdout.getvalue())

        abs_path = "/home/" + "synthetic-private/applicant.json"
        token = "api_" + "key=syntheticcredentialvalue"
        text_flags = scanner.scan_text(
            "release-artifact.md", f"{abs_path}\n{token}\n"
        )
        self.assertEqual(
            {flag.category for flag in text_flags}, {"ABS_PATH", "SECRET"}
        )
        self.assertEqual(
            scanner.scan_path_name("personal/private-report.json")[0].category,
            "TRACKED_CORPORA",
        )
        self.assertEqual(
            scanner.scan_vault_artifact(
                "build/candidates/default/output/crs-audit/aud.json"
            )[0].category,
            "VAULT_ARTIFACT",
        )


_AUDIT_ROOTS = (
    "crawler/audit_report.py",
    "crawler/auditor.py",
    "crawler/auditors/__init__.py",
    "crawler/crs_audit.py",
    "crawler/mec_publish.py",
    "crawler/mec_screen.py",
    "crawler/noc_review.py",
    "crawler/noc_worksheet.py",
    "crawler/policy_offer.py",
    "crawler/study_review.py",
)
_EXPECTED_AUDIT_CLOSURE = {
    "crawler/__init__.py",
    "crawler/audit_report.py",
    "crawler/auditor.py",
    "crawler/auditors/__init__.py",
    "crawler/auditors/additional.py",
    "crawler/auditors/core.py",
    "crawler/auditors/spouse.py",
    "crawler/auditors/transferability.py",
    "crawler/contract.py",
    "crawler/crs_audit.py",
    "crawler/crs_rules.py",
    "crawler/dli_contract.py",
    "crawler/dlifields.py",
    "crawler/dupaudit.py",
    "crawler/eval_runner.py",
    "crawler/extraction.py",
    "crawler/grounding.py",
    "crawler/index_health.py",
    "crawler/mec_publish.py",
    "crawler/mec_screen.py",
    "crawler/mecfields.py",
    "crawler/models/audit.py",
    "crawler/models/crs_rules.py",
    "crawler/models/mec.py",
    "crawler/models/public_locator.py",
    "crawler/models/vault.py",
    "crawler/noc_review.py",
    "crawler/noc_worksheet.py",
    "crawler/paths.py",
    "crawler/policy_offer.py",
    "crawler/profile.py",
    "crawler/searchindex.py",
    "crawler/siblingfields.py",
    "crawler/snapshot_policy.py",
    "crawler/study_review.py",
    "crawler/testtypes.py",
    "crawler/vault.py",
}
_EXPECTED_LOADER_CALLS = {
    "load_registry": {
        "crawler/crs_audit.py": 1,
        "crawler/crs_rules.py": 1,
    },
    "load_registry_snapshot": {
        "crawler/study_review.py": 1,
        "crawler/vault.py": 1,
    },
    "safe_load": {
        "crawler/crs_rules.py": 2,
        "crawler/dupaudit.py": 1,
        "crawler/noc_worksheet.py": 1,
        "crawler/profile.py": 1,
        "crawler/searchindex.py": 1,
        "crawler/study_review.py": 1,
        "crawler/vault.py": 1,
    },
    "connect": {
        "crawler/index_health.py": 2,
        "crawler/searchindex.py": 5,
        "crawler/vault.py": 1,
    },
}
_CONTRACT_HASHES = {
    "poetry.lock":
        "5561be20ae437b6ecabd66f3c5948f744c1f6562cb0d8929f386466323b42753",
    "crawler/models/audit.py":
        "1ed3dbba6d899dbfa89aeb9753471e15353efa5623578b60bcaebd86c0880910",
    "crawler/crs_audit.py":
        "cac7049a2d5e7e5cf7832f521c8da316ba201780a1f9fe1d94eb9658c924f5ac",
    "crawler/auditors/__init__.py":
        "48305e49d8763c81ca41004c4081ec59b6cedf78f5e01f7e60e745f81626e01d",
    "crawler/policy_offer.py":
        "61ead827c1b9f833a3e8b6640a080df646b61c3590074fda04cc73f5296ad443",
    "crawler/auditor.py":
        "d11f25eb578021bc49f6cd88a703fd64782a3c5b2ac92bb95e1c7685b5a35b15",
    "crawler/audit_report.py":
        "4589ab3079d31c7df036ac13c22c2b767dae3c1b37207e3b13f6a67803f9c846",
    "crawler/models/mec.py":
        "7780d17658e3026477f26f817b5615d1fa0095ea2b99bb64cb32bad829aa87a8",
    "crawler/mec_screen.py":
        "6746726604fcfb0cf9bd620ec184e32ffa5bcdcf654253f55d7323383ad18dc5",
    "crawler/mec_publish.py":
        "7b55e61be47137668018e51dfe2e2dccd17b6e651b3e8478f28c023b39de2f24",
    "crawler/dli_contract.py":
        "7fa6bb56e16b074f46114dc0796ec771f086ff5584cc76429ab2d6a135518505",
    "crawler/dli_snapshot.py":
        "b283c12cb6d09907ce94be8aa61b8685ab2bffdd42ff740a6d99ea9fd34f4ca4",
    "crawler/study_review.py":
        "9865756a541f50b5c4411a73c148129a9cd0d837bb6ee76fa13228f94e935c96",
    "crawler/noc_worksheet.py":
        "38c5b8f361f9106a39717847f74fdeda723e4a2be4cb0cdac59c37b20c3a2d2e",
    "crawler/noc_review.py":
        "64634b31d1a99d4eaf89c80a1815ef584b0b0490423fb13b5075a1488eb6a434",
    "crawler/cli.py":
        "75a3055723706b6daecff3949bebb739119759daf29bde8ab12cf24f428988eb",
    "crawler/crs_rules.py":
        "5e465b7b99069a25fdab160c94b38f90a612ed72360c89b355754c51e328662a",
    "crawler/paths.py":
        "aeea71c1e256cf0b9606c204feee19252f6bcd09c0028984930d8ec937c61b4f",
}


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_project_module(name: str) -> Path | None:
    stem = _ROOT.joinpath(*name.split("."))
    module = stem.with_suffix(".py")
    package = stem / "__init__.py"
    if module.is_file():
        return module
    if package.is_file():
        return package
    return None


def _project_imports(path: Path) -> set[Path]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    current = _module_name(path)
    package = current if path.name == "__init__.py" else current.rsplit(".", 1)[0]
    found: set[Path] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = package.split(".")
                package_parts = package_parts[
                    : len(package_parts) - (node.level - 1)
                ]
                if node.module:
                    package_parts.extend(node.module.split("."))
                prefix = ".".join(package_parts)
            else:
                prefix = node.module or ""
            if prefix:
                names.append(prefix)
            names.extend(
                f"{prefix}.{alias.name}" if prefix else alias.name
                for alias in node.names
            )
        for name in names:
            if name == "crawler" or name.startswith("crawler."):
                resolved = _resolve_project_module(name)
                if resolved is not None:
                    found.add(resolved)
    return found


def _audit_import_closure() -> set[Path]:
    pending = [_ROOT / relative for relative in _AUDIT_ROOTS]
    closure: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in closure:
            continue
        closure.add(path)
        pending.extend(_project_imports(path) - closure)
    return closure


def _named_call_sites(
    paths_: set[Path], names: set[str]
) -> dict[str, dict[str, int]]:
    result = {name: {} for name in names}
    for path in paths_:
        relative = path.relative_to(_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if name in names:
                result[name][relative] = result[name].get(relative, 0) + 1
    return result


class TestSupplyChainAndNetwork(unittest.TestCase):
    def test_dependency_set_and_lock_hash_are_exact(self) -> None:
        parsed = tomli.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            set(parsed["project"]["dependencies"]),
            {
                "pyyaml>=6.0,<7.0",
                "pydantic (>=2.13,<3.0)",
                "platformdirs (>=4.10,<5.0)",
                "github-copilot-sdk>=1.0.8,<1.1.0",
            },
        )
        self.assertEqual(
            hashlib.sha256((_ROOT / "poetry.lock").read_bytes()).hexdigest(),
            _CONTRACT_HASHES["poetry.lock"],
        )

    def test_enrolled_import_closure_has_no_network_or_alternate_loader(
        self,
    ) -> None:
        closure = _audit_import_closure()
        relative = {path.relative_to(_ROOT).as_posix() for path in closure}
        self.assertEqual(relative, _EXPECTED_AUDIT_CLOSURE)

        forbidden_imports = {
            "aiohttp",
            "curl",
            "httpx",
            "requests",
            "socket",
            "urllib.request",
            "urllib3",
        }
        forbidden_calls = {
            "create_connection",
            "urlopen",
            "urlretrieve",
            "refresh",
            "refresh_snapshot",
            "build_snapshot_family",
            "crawl",
        }
        for path in closure:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            network_imports = {
                imported
                for imported in imports
                if any(
                    imported == forbidden
                    or imported.startswith(f"{forbidden}.")
                    for forbidden in forbidden_imports
                )
            }
            self.assertFalse(network_imports, path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                self.assertNotIn(name, forbidden_calls, (path, node.lineno))

        self.assertEqual(
            _named_call_sites(closure, set(_EXPECTED_LOADER_CALLS)),
            _EXPECTED_LOADER_CALLS,
        )

    def test_runtime_composition_succeeds_with_socket_denied(self) -> None:
        _require_release_prerequisites(self)
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": td}):
                private = vault.open_vault("runtime-network-proof")
                vault.create_candidate(private, "runtime-network-proof")
                snapshot = crs_rules.load_registry_snapshot()
                try:
                    with mock.patch.object(
                        socket,
                        "socket",
                        side_effect=AssertionError("network forbidden"),
                    ):
                        evidence = mecfields.load_mec_evidence(
                            private,
                            "runtime-network-proof",
                            snapshot.fingerprint,
                        )
                        context = mec_screen.prepare_mec_gate(
                            "cec",
                            snapshot,
                            _REAL_DB,
                            date(2026, 7, 20),
                            90,
                            as_of=date(2026, 7, 20),
                        )
                        inputs = mec_screen.build_confirmed_mec_inputs(
                            "cec", context, evidence, private, _REAL_DB
                        )
                        bundle = mec_screen.screen_mec(
                            "cec",
                            context,
                            evidence,
                            inputs,
                            vault_=private,
                            db=_REAL_DB,
                            private_output_path="output/mec/cec/latest.json",
                        )
                        public = mec_publish.publish_mec_bundle(private, bundle)
                    self.assertEqual(public.status, "AT-RISK")
                    self.assertTrue(
                        (private.root / "output/mec/cec/latest.json").is_file()
                    )
                finally:
                    private.con.close()


class TestFrozenReleaseContracts(unittest.TestCase):
    def test_public_envelope_grid_crs_and_named_hashes_are_frozen(self) -> None:
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
            auditors.FULL_GRID_FACTORS,
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
        self.assertEqual(
            tuple(PrivateAuditReport.model_fields),
            (
                "run_id",
                "candidate_id",
                "created_at",
                "factor_cards",
                "substantiated_total",
                "cutoff_delta",
                "meets_cutoff",
                "registry_fingerprint",
            ),
        )
        registry = crs_rules.load_registry()
        self.assertEqual(
            crs_audit.compare_to_cutoff(500, 480, registry),
            {"delta": 20, "meets_cutoff": True},
        )
        self.assertEqual(
            crs_audit.arranged_employment_guard(
                200, "2026-07-20", registry
            ),
            {
                "status": "AT-RISK",
                "points": 0,
                "citation": "guidance/job-offer.md#001",
            },
        )
        self.assertEqual(
            policy_offer.offer_for_program_eligibility(
                True, "2026-07-20", registry
            )["crs_points"],
            0,
        )
        for relative, expected in _CONTRACT_HASHES.items():
            with self.subTest(path=relative):
                self.assertEqual(
                    hashlib.sha256((_ROOT / relative).read_bytes()).hexdigest(),
                    expected,
                )


_OUTCOME_DENYLIST = (
    "you are eligible",
    "you qualify",
    "guaranteed approval",
    "will be approved",
    "outcome is certain",
    "no misrepresentation risk",
)


def _affirmative_outcome_flags(text: str) -> list[str]:
    lowered = text.lower()
    normalized = (
        lowered.replace("not legal advice", "")
        .replace("not a final eligibility decision", "")
        .replace("no eligibility ruling", "")
        .replace("no outcome prediction", "")
    )
    flags = [phrase for phrase in _OUTCOME_DENYLIST if phrase in normalized]
    if "legal advice" in normalized:
        flags.append("legal advice")
    return flags


class TestReleaseArtifactFraming(unittest.TestCase):
    def _artifacts(self) -> dict[str, str]:
        bundle = _mec_bundle()
        noc = noc_worksheet._render_worksheet(
            {
                "lead": {
                    "chunk_id": "noc-2021/noc-21231.md#001",
                    "text": "Synthetic lead statement.",
                },
                "main": [
                    {
                        "chunk_id": "noc-2021/noc-21231.md#002",
                        "text": "Synthetic main duty.",
                    }
                ],
                "reqs": [
                    {
                        "chunk_id": "noc-2021/noc-21231.md#003",
                        "text": "Synthetic employment requirement.",
                    }
                ],
            },
            [
                {
                    "text": "Synthetic main duty.",
                    "duty_id": "21231:02:01",
                    "citations": [
                        {
                            "chunk_id": "noc-2021/noc-21231.md#002",
                            "quote": "Synthetic main duty.",
                        }
                    ],
                }
            ],
            "21231",
        )
        audit = audit_report._render_factor_card_markdown(
            PrivateAuditReport(
                run_id="aud_release_framing",
                candidate_id="synthetic",
                factor_cards=[],
            )
        )
        return {
            "mec-private.md": bundle.private_markdown.decode(),
            "mec-public.json": bundle.public_json.decode(),
            "study-private.json": _private_study_payload(Path("private-root")),
            "noc-worksheet.md": noc,
            "crs-report.md": audit,
            "crawler/README.md": (
                _ROOT / "crawler" / "README.md"
            ).read_text(encoding="utf-8"),
            "SCREENING.md": (_ROOT / "SCREENING.md").read_text(encoding="utf-8"),
        }

    def test_rendered_release_artifacts_have_screening_framing(self) -> None:
        scanner = _load_publish_safe()
        for name, text in self._artifacts().items():
            with self.subTest(artifact=name):
                lowered = text.lower()
                self.assertIn("screen", lowered)
                self.assertTrue(
                    "grounded" in lowered
                    or "cited" in lowered
                    or "citation" in lowered
                )
                self.assertTrue(
                    "not legal advice" in lowered
                    or "not a substitute" in lowered
                )
                self.assertEqual(_affirmative_outcome_flags(text), [])
                self.assertEqual(
                    scanner.scan_text(f"release/{Path(name).name}", text),
                    [],
                )

        combined = "\n".join(self._artifacts().values()).lower()
        for phrase in (
            "at-risk",
            "semantic fit",
            "noc-duty",
            "officer discretion",
        ):
            self.assertIn(phrase, combined)

    def test_affirmative_outcome_denylist_has_positive_control(self) -> None:
        crafted = (
            "You are eligible, will be approved, and the outcome is certain. "
            "This is legal advice."
        )
        flags = _affirmative_outcome_flags(crafted)
        self.assertIn("you are eligible", flags)
        self.assertIn("will be approved", flags)
        self.assertIn("outcome is certain", flags)
        self.assertIn("legal advice", flags)
        self.assertEqual(
            _affirmative_outcome_flags(
                "This screening is not legal advice and makes no outcome prediction."
            ),
            [],
        )
