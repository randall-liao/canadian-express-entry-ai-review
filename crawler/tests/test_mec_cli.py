"""Exact MEC command boundary and recoverable private publication tests."""

from __future__ import annotations

import json
import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest import mock

from crawler import cli, crs_rules, mec_screen, mecfields, vault
from crawler.mec_publish import MecPublicationError, publish_mec_bundle
from crawler.mec_screen import MecPublicationBundle
from crawler.models.mec import (
    MecCounts,
    PrivateMecCriterion,
    PrivateMecReport,
    PublicMecSummary,
)
from crawler.models.vault import CrsProfileFactor


_REAL_DB = Path(__file__).resolve().parents[2] / "corpus" / "index.db"


def _criterion(*, private_value: str = "private applicant value") -> PrivateMecCriterion:
    return PrivateMecCriterion(
        criterion_id="cec.work.paid",
        status="AT-RISK",
        reason_code="evidence_missing",
        corpus_citation_ids=["guidance/mec.md#001"],
        wired=True,
        grounded=True,
        applicability_grounded=False,
        applicable=None,
        rule_ids=["cec.work.paid"],
        applicant_values={},
        evidence_ids=[private_value],
        employment_traces=[],
        sidecar_inputs={},
        grid_bounds={},
        completeness_attestations={"work": False},
        render_details={},
    )


def _bundle(*, private_value: str = "private applicant value") -> MecPublicationBundle:
    report = PrivateMecReport(
        schema_version="1.0",
        run_id="mec_deadbeef0004deadbeef0004deadbeef",
        candidate_id="private-candidate",
        program="cec",
        status="AT-RISK",
        criteria=[_criterion(private_value=private_value)],
        counts=MecCounts(criteria=1, at_risk=1),
        registry_fingerprint="a" * 64,
        created_at="2026-07-20T00:00:00Z",
        private_report_path="output/mec/cec/latest.json",
    )
    public = PublicMecSummary(
        schema_version="1.0",
        run_id=report.run_id,
        program=report.program,
        status=report.status,
        criteria=[
            {
                "criterion_id": "cec.work.paid",
                "status": "AT-RISK",
                "reason_code": "evidence_missing",
                "corpus_citation_ids": [],
            }
        ],
        counts=report.counts,
        registry_fingerprint=report.registry_fingerprint,
        private_output_path=report.private_report_path,
    )
    private_json = json.dumps(
        report.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    private_markdown = mec_screen._render_private_markdown(report)
    public_json = json.dumps(
        public.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return MecPublicationBundle(
        private_report=report,
        public_summary=public,
        private_json=private_json,
        private_markdown=private_markdown,
        public_json=public_json,
    )


class TestMecParser(unittest.TestCase):
    def test_exact_command_spelling_and_required_program(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "vault",
                "screen-mec",
                "--program",
                "fsw",
                "--rule-max-age-days",
                "30",
            ]
        )
        self.assertEqual(args.vault_verb, "screen-mec")
        self.assertEqual(args.program, "fsw")
        with self.assertRaises(SystemExit):
            parser.parse_args(["vault", "mec", "--program", "fsw"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["vault", "screen-mec"])

    def test_all_programs_parse_and_only_fsw_consumes_dli_config(self) -> None:
        for program in ("fsw", "fst", "cec"):
            with self.subTest(program=program):
                args = cli.build_parser().parse_args(
                    ["vault", "screen-mec", "--program", program]
                )
                self.assertEqual(args.program, program)
                self.assertTrue(hasattr(args, "snapshot_max_age_days"))


class TestMecCliOrdering(unittest.TestCase):
    def test_missing_rule_freshness_refuses_before_every_read_or_write(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                "crawler.snapshot_policy.mec_rule_max_age_days", return_value=None
            ) as resolve,
            mock.patch("crawler.crs_rules.load_registry_snapshot") as load,
            mock.patch("crawler.cli._require_readable_index") as index,
            mock.patch("crawler.vault.open_vault") as open_vault,
            mock.patch("crawler.mec_publish.publish_mec_bundle") as publish,
            mock.patch("crawler.contract.emit") as emit,
        ):
            code = cli.main(["--json", "vault", "screen-mec", "--program", "cec"])
        self.assertEqual(code, 2)
        resolve.assert_called_once_with(None)
        load.assert_not_called()
        index.assert_not_called()
        open_vault.assert_not_called()
        publish.assert_not_called()
        payload = emit.call_args.args[0]
        self.assertEqual(set(payload), {"schema_version", "ok", "command", "result", "error"})
        self.assertFalse(payload["ok"])

    def test_one_snapshot_and_unchanged_identity_reach_the_complete_run(self) -> None:
        snapshot = crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(rows=[])
        )
        context = SimpleNamespace(
            registry_snapshot=snapshot,
            registry_fingerprint=snapshot.fingerprint,
            max_age_days=45,
        )
        evidence = SimpleNamespace(candidate_id="candidate")
        confirmed_inputs = object()
        bundle = _bundle()
        published = bundle.public_summary
        connection = mock.Mock()
        vault_object = SimpleNamespace(con=connection)
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                "crawler.snapshot_policy.mec_rule_max_age_days", return_value=45
            ) as resolve,
            mock.patch(
                "crawler.snapshot_policy.dli_snapshot_max_age_days", return_value=None
            ),
            mock.patch(
                "crawler.crs_rules.load_registry_snapshot", return_value=snapshot
            ) as load,
            mock.patch("crawler.cli._require_readable_index", return_value=None) as index,
            mock.patch(
                "crawler.mec_screen.prepare_mec_gate", return_value=context
            ) as prepare,
            mock.patch("crawler.vault.open_vault", return_value=vault_object),
            mock.patch(
                "crawler.mecfields.load_mec_evidence", return_value=evidence
            ) as load_evidence,
            mock.patch(
                "crawler.mecfields.eligibility_reference_date",
                return_value=date(2025, 6, 1),
            ) as reference,
            mock.patch(
                "crawler.mec_screen.build_confirmed_mec_inputs",
                return_value=confirmed_inputs,
            ) as build_inputs,
            mock.patch("crawler.mec_screen.screen_mec", return_value=bundle) as screen,
            mock.patch(
                "crawler.mec_publish.publish_mec_bundle", return_value=published
            ) as publish,
            mock.patch("crawler.contract.emit") as emit,
        ):
            code = cli.main(
                [
                    "--json",
                    "vault",
                    "screen-mec",
                    "--program",
                    "cec",
                    "--candidate",
                    "candidate",
                    "--db",
                    "corpus.db",
                    "--rule-max-age-days",
                    "45",
                ]
            )
        self.assertEqual(code, 0)
        resolve.assert_called_once_with("45")
        load.assert_called_once_with()
        index.assert_called_once()
        self.assertIs(prepare.call_args.args[1], snapshot)
        self.assertEqual(prepare.call_args.args[4], 45)
        self.assertEqual(prepare.call_args.args[3], date(2025, 6, 1))
        self.assertEqual(prepare.call_args.kwargs["as_of"], date.today())
        self.assertEqual(
            load_evidence.call_args.args[2], snapshot.fingerprint
        )
        reference.assert_called_once_with(evidence)
        build_inputs.assert_called_once_with(
            "cec", context, evidence, vault_object, "corpus.db"
        )
        self.assertIs(screen.call_args.args[1], context)
        self.assertIs(screen.call_args.args[2], evidence)
        self.assertIs(screen.call_args.args[3], confirmed_inputs)
        self.assertEqual(screen.call_args.kwargs["study_max_age_days"], None)
        self.assertIs(publish.call_args.args[0], vault_object)
        self.assertIs(publish.call_args.args[1], bundle)
        connection.close.assert_called_once_with()
        payload = emit.call_args.args[0]
        self.assertEqual(set(payload), {"schema_version", "ok", "command", "result", "error"})
        self.assertEqual(payload["result"], published.model_dump(mode="json"))
        self.assertNotIn("private-candidate", json.dumps(payload))
        self.assertNotIn("ev_", json.dumps(payload))
        self.assertNotIn("guidance/mec", json.dumps(payload))

    def test_dli_preflight_occurs_only_when_fsw_study_is_consumed(self) -> None:
        snapshot = crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(rows=[])
        )
        refusal_args = [
            "--json",
            "vault",
            "screen-mec",
            "--program",
            "fsw",
            "--rule-max-age-days",
            "30",
            "--snapshot-max-age-days",
            "10",
        ]
        with (
            mock.patch(
                "crawler.snapshot_policy.mec_rule_max_age_days", return_value=30
            ),
            mock.patch(
                "crawler.snapshot_policy.dli_snapshot_max_age_days", return_value=10
            ),
            mock.patch(
                "crawler.crs_rules.load_registry_snapshot", return_value=snapshot
            ),
            mock.patch("crawler.cli._require_readable_index", return_value=None),
            mock.patch("crawler.mec_screen.prepare_mec_gate", return_value=object()),
            mock.patch(
                "crawler.cli._require_readable_snapshot", return_value=2
            ) as dli,
            mock.patch("crawler.vault.open_vault") as open_vault,
        ):
            self.assertEqual(cli.main(refusal_args), 2)
        dli.assert_called_once_with(mock.ANY, mock.ANY, "dli", 10)
        open_vault.assert_not_called()

    def test_missing_candidate_reference_refuses_before_screen_or_publish(self) -> None:
        snapshot = crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(rows=[])
        )
        connection = mock.Mock()
        vault_object = SimpleNamespace(con=connection)
        with (
            mock.patch(
                "crawler.snapshot_policy.mec_rule_max_age_days", return_value=30
            ),
            mock.patch(
                "crawler.crs_rules.load_registry_snapshot", return_value=snapshot
            ),
            mock.patch("crawler.cli._require_readable_index", return_value=None),
            mock.patch("crawler.vault.open_vault", return_value=vault_object),
            mock.patch(
                "crawler.mecfields.load_mec_evidence", return_value=object()
            ),
            mock.patch(
                "crawler.mecfields.eligibility_reference_date",
                side_effect=ValueError("private detail"),
            ),
            mock.patch("crawler.mec_screen.screen_mec") as screen,
            mock.patch("crawler.mec_publish.publish_mec_bundle") as publish,
            mock.patch("crawler.contract.emit") as emit,
        ):
            code = cli.main(
                [
                    "--json",
                    "vault",
                    "screen-mec",
                    "--program",
                    "cec",
                    "--rule-max-age-days",
                    "30",
                ]
            )
        self.assertNotEqual(code, 0)
        screen.assert_not_called()
        publish.assert_not_called()
        connection.close.assert_called_once_with()
        self.assertNotIn("private detail", json.dumps(emit.call_args.args[0]))

    def test_sqlite_read_and_close_errors_are_stable_in_both_output_modes(self) -> None:
        snapshot = crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(rows=[])
        )
        for json_mode in (False, True):
            connection = mock.Mock()
            connection.close.side_effect = sqlite3.DatabaseError(
                "/private/candidate/vault.sqlite close failed"
            )
            vault_object = SimpleNamespace(con=connection)
            emitted = []
            arguments = ["vault", "screen-mec", "--program", "cec"]
            if json_mode:
                arguments.insert(0, "--json")
            stderr = io.StringIO()
            with (
                self.subTest(json_mode=json_mode),
                mock.patch(
                    "crawler.snapshot_policy.mec_rule_max_age_days",
                    return_value=30,
                ),
                mock.patch(
                    "crawler.crs_rules.load_registry_snapshot",
                    return_value=snapshot,
                ),
                mock.patch("crawler.cli._require_readable_index", return_value=None),
                mock.patch("crawler.vault.open_vault", return_value=vault_object),
                mock.patch(
                    "crawler.mecfields.load_mec_evidence",
                    side_effect=sqlite3.DatabaseError(
                        "/private/candidate/vault.sqlite corrupt"
                    ),
                ),
                mock.patch(
                    "crawler.contract.emit", side_effect=emitted.append
                ),
                redirect_stderr(stderr),
            ):
                code = cli.main(arguments)
            self.assertNotEqual(code, 0)
            connection.close.assert_called_once_with()
            surfaced = json.dumps(emitted) if json_mode else stderr.getvalue()
            self.assertIn("MEC screening unavailable", surfaced)
            self.assertNotIn("/private", surfaced)


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY: corpus/index.db is required for the real MEC CLI seam",
)
class TestMecRealCliEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.environment = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self.temp.name}
        )
        self.environment.start()
        self.snapshot = crs_rules.load_registry_snapshot()
        self.vault = vault.open_vault("default")
        vault.create_candidate(self.vault, "default")
        for factor in (
            CrsProfileFactor(
                factor_id="core.language.first",
                factor_group="core_human_capital",
                claimed_points=116,
                claimed_level="9",
                claimed_value=9,
            ),
            CrsProfileFactor(
                factor_id="review.mec",
                factor_group="program_eligibility",
                claimed_value={},
            ),
        ):
            vault.upsert_profile_factor(self.vault, factor)

    def tearDown(self) -> None:
        self.vault.con.close()
        self.environment.stop()
        self.temp.cleanup()

    def _confirmed_document(
        self,
        name: str,
        doc_type: str,
        factor_id: str,
        fields: dict[str, object],
    ) -> None:
        source = Path(self.temp.name) / name
        source.write_text("private fixture", encoding="utf-8")
        document = vault.import_document(
            self.vault, "default", source, doc_type=doc_type
        )
        run_id = vault.record_extraction_run(
            self.vault,
            document_id=document.document_id,
            parser_version=vault.current_parser_version(),
        )
        for field_name, value in fields.items():
            value_id = vault.add_extracted_value(
                self.vault,
                document_id=document.document_id,
                page_id=None,
                factor_id=factor_id,
                field_name=field_name,
                raw_text=str(value),
                normalized_value=value,
                bbox=None,
                extractor_confidence=1.0,
                quality_flag="ok",
                extraction_run_id=run_id,
            )
            vault.confirm_value(
                self.vault,
                value_id,
                "confirm",
                registry_fingerprint=self.snapshot.fingerprint,
            )

    def _run_program(self, program: str) -> dict:
        code = cli.main(
            [
                "--json",
                "vault",
                "screen-mec",
                "--candidate",
                "default",
                "--program",
                program,
                "--db",
                str(_REAL_DB),
                "--rule-max-age-days",
                "120",
                "--as-of",
                "2026-07-20",
            ]
        )
        self.assertEqual(code, 0)
        report_path = (
            self.vault.root / "output" / "mec" / program / "latest.json"
        )
        return json.loads(report_path.read_text(encoding="utf-8"))

    def _run_fsw(self) -> dict:
        return self._run_program("fsw")

    def test_real_cli_uses_only_current_confirmed_language_card(self) -> None:
        self._confirmed_document(
            "language.txt",
            "language_test",
            "core.language.first",
            {
                "test_type": "IELTS General Training",
                "test_date": "2026-01-15",
                "raw_score_listening": 9,
                "raw_score_reading": 9,
                "raw_score_writing": 9,
                "raw_score_speaking": 9,
            },
        )
        self._confirmed_document(
            "mec-profile.txt",
            "mec-profile",
            "review.mec",
            {
                "eligibility_reference_date": "2026-06-15",
                "language_scope_complete": True,
            },
        )

        report = self._run_fsw()
        language = next(
            item
            for item in report["criteria"]
            if item["criterion_id"] == "fsw.language.first"
        )
        self.assertEqual(language["status"], "PASS")

        self.vault.con.execute(
            "UPDATE extracted_values "
            "SET confirmed_rule_registry_version = 'obsolete' "
            "WHERE factor_id = 'core.language.first'"
        )
        self.vault.con.commit()
        stale_report = self._run_fsw()
        stale_language = next(
            item
            for item in stale_report["criteria"]
            if item["criterion_id"] == "fsw.language.first"
        )
        self.assertEqual(stale_language["status"], "AT-RISK")

    def test_real_cli_requires_confirmed_complete_fst_certificate_scope(
        self,
    ) -> None:
        period = mecfields.EmploymentPeriod(
            employment_period_id="mep_" + "d" * 32,
            document_id="doc_fst_period",
            values=MappingProxyType(
                {
                    "noc_code": "72200",
                    "paid_status": True,
                    "student_status": False,
                    "qualified_to_practise": True,
                    "employment_start": "2024-01-02",
                    "employment_end": "2026-01-01",
                    "duration_months": 24,
                    "total_hours": 30 * 731 / 7,
                    "hours_per_week": 30,
                }
            ),
            evidence_ids=("val_fst_period",),
        )
        certificate = {
            "eligibility_reference_date": "2026-06-15",
            "work_history_scope_complete": True,
            "trade_certificate_authority": "Ontario authority",
            "trade_certificate_jurisdiction": "ON",
            "trade_certificate_noc_code": "72200",
            "trade_certificate_status": "valid",
            "trade_certificate_issue_date": "2025-01-01",
            "trade_certificate_expiry_date": "2027-01-01",
        }

        def evidence(*, scope_complete: bool | None) -> mecfields.MecEvidence:
            scalars = dict(certificate)
            if scope_complete is not None:
                scalars["offer_certificate_scope_complete"] = scope_complete
            return mecfields.MecEvidence(
                candidate_id="default",
                registry_fingerprint=self.snapshot.fingerprint,
                scalars=MappingProxyType(scalars),
                scalar_evidence_ids=MappingProxyType(
                    {
                        name: (f"val_fst_{index}",)
                        for index, name in enumerate(scalars)
                    }
                ),
                periods=(period,),
            )

        for scope_complete, expected in ((None, "AT-RISK"), (True, "PASS")):
            with (
                self.subTest(scope_complete=scope_complete),
                mock.patch(
                    "crawler.mecfields.load_mec_evidence",
                    return_value=evidence(scope_complete=scope_complete),
                ),
            ):
                report = self._run_program("fst")
            criterion = next(
                item
                for item in report["criteria"]
                if item["criterion_id"] == "fst.offer_or_certificate"
            )
            self.assertEqual(criterion["status"], expected)
            self.assertEqual(
                criterion["completeness_attestations"]["offer_certificate"],
                scope_complete is True,
            )


class TestMecPublisher(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = SimpleNamespace(root=self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _latest(self) -> tuple[Path, Path]:
        directory = self.root / "output" / "mec" / "cec"
        return directory / "latest.json", directory / "latest.md"

    def _seed_lkg(self) -> tuple[bytes, bytes]:
        json_path, markdown_path = self._latest()
        json_path.parent.mkdir(parents=True)
        old = (b'{"old":"json"}', b"# old markdown\n")
        json_path.write_bytes(old[0])
        markdown_path.write_bytes(old[1])
        return old

    def _assert_lkg(self, old: tuple[bytes, bytes]) -> None:
        json_path, markdown_path = self._latest()
        self.assertEqual(json_path.read_bytes(), old[0])
        self.assertEqual(markdown_path.read_bytes(), old[1])
        self.assertEqual(
            sorted(path.name for path in json_path.parent.iterdir()),
            ["latest.json", "latest.md"],
        )

    def test_scans_then_publishes_only_two_private_files(self) -> None:
        bundle = _bundle()
        with (
            mock.patch("crawler.mec_publish._scan_private_bytes", wraps=__import__(
                "crawler.mec_publish", fromlist=["_scan_private_bytes"]
            )._scan_private_bytes) as private_scan,
            mock.patch("crawler.mec_publish._scan_public_bytes", wraps=__import__(
                "crawler.mec_publish", fromlist=["_scan_public_bytes"]
            )._scan_public_bytes) as public_scan,
        ):
            summary = publish_mec_bundle(self.vault, bundle)
        json_path, markdown_path = self._latest()
        self.assertEqual(json_path.read_bytes(), bundle.private_json)
        self.assertEqual(markdown_path.read_bytes(), bundle.private_markdown)
        self.assertEqual(summary, bundle.public_summary)
        self.assertEqual(private_scan.call_count, 2)
        public_scan.assert_called_once_with(bundle.public_json)
        self.assertFalse(any("public" in path.name for path in json_path.parent.iterdir()))
        self.assertFalse(any(path.suffix in {".tmp", ".bak"} for path in json_path.parent.iterdir()))

    def test_public_citations_and_private_paths_or_secrets_refuse_before_write(self) -> None:
        public_with_citation = _bundle()
        public_with_citation.public_summary.criteria[0].corpus_citation_ids = [
            "guidance/mec.md#001"
        ]
        public_with_citation = MecPublicationBundle(
            **{
                **public_with_citation.__dict__,
                "public_json": json.dumps(
                    public_with_citation.public_summary.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode(),
            }
        )
        for hostile in (
            public_with_citation,
            _bundle(private_value="api_key=abcdefghijklmnop"),
        ):
            with self.subTest(hostile=hostile.private_report.criteria[0].applicant_values):
                with self.assertRaises(MecPublicationError):
                    publish_mec_bundle(self.vault, hostile)
                self.assertFalse((self.root / "output").exists())

        raw = json.loads(_bundle().private_json)
        raw["criteria"][0]["evidence_ids"] = ["/etc/passwd"]
        with self.assertRaises(MecPublicationError):
            __import__(
                "crawler.mec_publish", fromlist=["_scan_private_bytes"]
            )._scan_private_bytes(
                json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
            )

    def test_every_render_scan_stage_replace_and_fsync_failure_preserves_lkg(self) -> None:
        seams = (
            ("render", "_validate_and_render", 1),
            ("private_scan", "_scan_private_bytes", 1),
            ("public_scan", "_scan_public_bytes", 1),
            ("stage_first", "_stage_bytes", 1),
            ("stage_second", "_stage_bytes", 2),
            ("replace_first", "_replace", 1),
            ("replace_second", "_replace", 2),
            ("replace_third", "_replace", 3),
            ("replace_fourth", "_replace", 4),
            ("directory_fsync", "_fsync_dir", 1),
        )
        module = __import__("crawler.mec_publish", fromlist=["publish_mec_bundle"])
        for label, seam, fail_at in seams:
            with self.subTest(seam=label):
                for child in list(self.root.iterdir()):
                    if child.is_dir():
                        import shutil

                        shutil.rmtree(child)
                    else:
                        child.unlink()
                old = self._seed_lkg()
                original = getattr(module, seam)
                calls = 0

                def injected(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise OSError("private injected detail")
                    return original(*args, **kwargs)

                with (
                    mock.patch.object(module, seam, side_effect=injected),
                    self.assertRaises(MecPublicationError),
                ):
                    publish_mec_bundle(self.vault, _bundle())
                self._assert_lkg(old)

    def test_backup_cleanup_is_checked_retried_and_directory_fsynced_last(self) -> None:
        module = __import__("crawler.mec_publish", fromlist=["publish_mec_bundle"])
        self._seed_lkg()
        events = []
        remove_calls = 0
        original_replace = module._replace
        original_remove = module._remove_backup
        original_fsync = module._fsync_dir

        def replace(*args):
            events.append("replace")
            return original_replace(*args)

        def remove(*args):
            nonlocal remove_calls
            remove_calls += 1
            events.append("remove")
            if remove_calls == 1:
                raise OSError("transient private cleanup detail")
            return original_remove(*args)

        def fsync(*args):
            events.append("fsync")
            return original_fsync(*args)

        with (
            mock.patch.object(module, "_replace", side_effect=replace),
            mock.patch.object(module, "_remove_backup", side_effect=remove),
            mock.patch.object(module, "_fsync_dir", side_effect=fsync),
        ):
            publish_mec_bundle(self.vault, _bundle())

        self.assertEqual(events[-4:], ["remove", "remove", "remove", "fsync"])
        self.assertFalse(any(self._latest()[0].parent.glob(".*.bak")))

    def test_persistent_backup_cleanup_failure_keeps_new_reports_and_is_path_free(
        self,
    ) -> None:
        module = __import__("crawler.mec_publish", fromlist=["publish_mec_bundle"])
        old = self._seed_lkg()
        bundle = _bundle()
        with (
            mock.patch.object(
                module,
                "_remove_backup",
                side_effect=OSError("/private/report/path cleanup failed"),
            ),
            self.assertRaises(MecPublicationError) as raised,
        ):
            publish_mec_bundle(self.vault, bundle)

        json_path, markdown_path = self._latest()
        self.assertEqual(json_path.read_bytes(), bundle.private_json)
        self.assertEqual(markdown_path.read_bytes(), bundle.private_markdown)
        backups = list(json_path.parent.glob(".*.bak"))
        self.assertEqual({path.read_bytes() for path in backups}, {old[0], old[1]})
        self.assertEqual(str(raised.exception), "MEC report publication failed")
        self.assertNotIn("/private", str(raised.exception))

    def test_persistent_stage_and_forward_replace_failures_never_touch_untouched_lkg(
        self,
    ) -> None:
        module = __import__("crawler.mec_publish", fromlist=["publish_mec_bundle"])
        for seam in ("_stage_bytes", "_replace"):
            with self.subTest(seam=seam):
                for child in list(self.root.iterdir()):
                    import shutil

                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                old = self._seed_lkg()
                with (
                    mock.patch.object(
                        module, seam, side_effect=OSError("persistent failure")
                    ),
                    self.assertRaises(MecPublicationError),
                ):
                    publish_mec_bundle(self.vault, _bundle())
                self._assert_lkg(old)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
