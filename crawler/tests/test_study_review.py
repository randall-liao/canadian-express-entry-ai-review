"""STUDY-02 tests for quarantined Canadian-study evidence.

The suite is offline and uses only synthetic applicant data.  It drives the real
document extraction and vault confirmation seams inside temporary candidate
vaults; no personal or corpus data is read or written.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import threading
import typing
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from crawler import auditor, crs_rules, dlifields, extraction, study_review, vault
from crawler.auditors import FACTOR_GROUP, FULL_GRID_FACTORS
from crawler.models import vault as vault_models
from crawler.models.vault import CrsProfileFactor
from crawler.tests.fixtures.extraction import make_fixtures as mf


_EXPECTED_STUDY_FIELDS = {
    "institution_name",
    "dli_number",
    "credential_level",
    "program_start",
    "program_end",
    "study_status",
}

_SYNTHETIC_STUDY_TEXT = "\n".join([
    "Synthetic Proof of Canadian Studies",
    "Institution Name: Example Northern Institute",
    "DLI Number: o 19332746152",
    "Credential Level: Bachelor's degree",
    "Program Start: 15 September 2022",
    "Program End: 30 April 2026",
    "Study Status: Graduated",
])


def _fieldname_study_members() -> set[str]:
    """Read the six study members from the actual typed vault boundary."""
    return {
        value for value in typing.get_args(vault_models.FieldName)
        if value in _EXPECTED_STUDY_FIELDS
    }


def _spec_field_names() -> set[str]:
    """Read the producer names exactly as the extractor consumes its spec."""
    return {
        name for name, _label, _kind
        in extraction._FIELD_SPECS["study_proof"]
    }


class _StudyTmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _extract_study(self, candidate_id: str = "default",
                       text: str = _SYNTHETIC_STUDY_TEXT):
        """Import and really extract one synthetic born-digital study proof."""
        v = vault.open_vault(candidate_id)
        vault.create_candidate(v, candidate_id)
        source = Path(self._tmp.name) / f"{candidate_id}-study.pdf"
        source.write_bytes(mf.build_pdf([text]))
        document = vault.import_document(
            v, candidate_id, source, doc_type="study_proof")
        try:
            result = extraction.extract_document(v, document.document_id)
        except extraction.MissingExtractionDependency as exc:  # pragma: no cover
            v.con.close()
            self.skipTest(f"extraction dependency unavailable: {exc.module}")
        values = vault.list_extracted_values(
            v, document_id=document.document_id)
        return v, document, result, values


class TestStudyReadOnlyComposition(_StudyTmpCase):
    def test_recovery_marker_refuses_before_snapshot_or_evaluation(self) -> None:
        candidate = "recovery-refusal"
        v = vault.open_vault(candidate)
        report_dir = study_review._latest_report_path(v.root).parent
        report_dir.mkdir(parents=True)
        (report_dir / study_review._RECOVERY_MARKER_NAME).write_text(
            '{"state":"restore_required"}',
            encoding="ascii",
        )
        try:
            with (
                mock.patch(
                    "crawler.study_review.index_health.probe_snapshot",
                    side_effect=AssertionError("evaluation must not start"),
                ) as probe,
                self.assertRaisesRegex(
                    study_review.StudyReportRecoveryError,
                    "^study report recovery failed$",
                ),
            ):
                study_review.review_study(
                    v,
                    "unused.db",
                    candidate_id=candidate,
                    max_age_days=30,
                    read_only=True,
                    no_report=True,
                )
            probe.assert_not_called()
        finally:
            v.con.close()

    def test_markerless_different_backup_refuses_before_snapshot_or_evaluation(
            self) -> None:
        """STUDY never evaluates while an unproven old recovery copy remains."""
        candidate = "markerless-recovery-refusal"
        v = vault.open_vault(candidate)
        report_dir = study_review._latest_report_path(v.root).parent
        report_dir.mkdir(parents=True)
        (report_dir / "latest.json").write_bytes(b"new")
        backup = report_dir / ".latest-unlabelled.bak"
        backup.write_bytes(b"old")
        try:
            with (
                mock.patch(
                    "crawler.study_review.index_health.probe_snapshot",
                    side_effect=AssertionError("evaluation must not start"),
                ) as probe,
                self.assertRaisesRegex(
                    study_review.StudyReportRecoveryError,
                    "^study report recovery failed$",
                ),
            ):
                study_review.review_study(
                    v,
                    "unused.db",
                    candidate_id=candidate,
                    max_age_days=30,
                    read_only=True,
                    no_report=True,
                )
            probe.assert_not_called()
            self.assertEqual(backup.read_bytes(), b"old")
        finally:
            v.con.close()

    def test_injected_read_only_mode_preserves_artifacts_and_never_reloads(self) -> None:
        candidate = "read-only-composition"
        v = vault.open_vault(candidate)
        vault.create_candidate(v, candidate)
        snapshot = crs_rules.RegistrySnapshot(
            registry=crs_rules.Registry(rows=[]),
        )
        report = v.root / "output" / "study-review" / "latest.json"
        report.parent.mkdir(parents=True)
        report.write_bytes(b"prior-private-report\n")
        before = report.read_bytes()
        healthy = mock.Mock()
        healthy.ok.return_value = True
        try:
            with (
                mock.patch(
                    "crawler.study_review.index_health.probe_snapshot",
                    return_value=healthy,
                ),
                mock.patch("crawler.study_review._static_rows", return_value=[]),
                mock.patch(
                    "crawler.study_review.crs_rules.load_registry_snapshot",
                    side_effect=AssertionError("injected study must not reload"),
                ) as loader,
                mock.patch(
                    "crawler.study_review._write_private_report",
                    side_effect=AssertionError("no-report mode must not write"),
                ) as writer,
            ):
                result = study_review.review_study(
                    v,
                    "unused.db",
                    candidate_id=candidate,
                    max_age_days=30,
                    registry_snapshot=snapshot,
                    read_only=True,
                    no_report=True,
                )
            self.assertEqual(
                (result["status"], result["reason"]),
                ("N/A", "no_study_evidence"),
            )
            self.assertFalse(result.report_created)
            self.assertEqual(result.registry_fingerprint, snapshot.fingerprint)
            self.assertEqual(report.read_bytes(), before)
            self.assertEqual(list(report.parent.glob(".latest-*.tmp")), [])
            loader.assert_not_called()
            writer.assert_not_called()
        finally:
            v.con.close()


class TestStudyFieldVocabulary(unittest.TestCase):
    def test_study_field_vocabulary_matches_producer_and_boundary(self) -> None:
        self.assertEqual(set(dlifields.STUDY_FIELDS), _EXPECTED_STUDY_FIELDS)
        self.assertEqual(set(dlifields.STUDY_FIELDS), _spec_field_names())
        self.assertEqual(set(dlifields.STUDY_FIELDS),
                         _fieldname_study_members())

    def test_study_field_route_is_inert_review_parent(self) -> None:
        self.assertEqual(
            extraction._DOC_TYPE_FACTOR["study_proof"], "review.study")
        self.assertNotIn("review.study", FULL_GRID_FACTORS)


class TestStudyFieldNormalization(unittest.TestCase):
    def test_dli_field_normalizes_exact_o_prefixed_identifier(self) -> None:
        expected = "O19332746152"
        for raw in (
                expected,
                "o19332746152",
                "  o 193 327 461 52  ",
                "Ｏ19332746152",  # full-width O stays distinct under NFC
        ):
            with self.subTest(raw=raw):
                got = dlifields.normalize_dli(raw)
                if raw.startswith("Ｏ"):
                    self.assertIsNone(got)
                else:
                    self.assertEqual(got, expected)

    def test_dli_field_malformed_blank_short_and_name_only_fail_closed(self) -> None:
        for raw in (
                "", "   ", "University of Toronto", "O12345", "0123456",
                "O12345A", "DLI O19332746152", "O-19332746152",
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(dlifields.normalize_dli(raw))

    def test_dli_field_rejects_every_non_string_json_type(self) -> None:
        for raw in (19332746152, ["O19332746152"],
                    {"dli": "O19332746152"}, True, None):
            with self.subTest(raw=raw):
                self.assertIsNone(dlifields.normalize_dli(raw))
        self.assertEqual(
            dlifields.normalize_dli("O19332746152"), "O19332746152")

    def test_credential_field_aliases_only_reach_closed_tiers(self) -> None:
        cases = {
            "One-year certificate": "1-2",
            "Two year diploma": "1-2",
            "Bachelor's degree": "3+",
            "Three-year diploma": "3+",
            "Master's degree": "3+",
            "Doctoral degree": "3+",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                got = dlifields.normalize_credential_level(raw)
                self.assertEqual(got, expected)
                self.assertIn(got, dlifields.CREDENTIAL_TIERS_ACCEPTED)
        for raw in ("Secondary school", "High school diploma", "Unknown award"):
            self.assertNotIn(
                dlifields.normalize_credential_level(raw),
                dlifields.CREDENTIAL_TIERS_ACCEPTED)

    def test_status_field_aliases_only_reach_closed_tokens(self) -> None:
        cases = {
            "Complete": "completed",
            "Completed": "completed",
            "Graduate": "graduated",
            "Graduated": "graduated",
            "Currently enrolled": "enrolled",
            "Enrolled": "enrolled",
            "Withdrawn": "withdrawn",
            "Withdrew": "withdrawn",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                got = dlifields.normalize_study_status(raw)
                self.assertEqual(got, expected)
                self.assertIn(got, dlifields.STUDY_STATUSES_ACCEPTED)
        for raw in ("Applied", "Admitted", "Unknown"):
            self.assertNotIn(
                dlifields.normalize_study_status(raw),
                dlifields.STUDY_STATUSES_ACCEPTED)

    def test_study_field_extractor_canonicalizes_without_scoring(self) -> None:
        fields = {
            item["field_name"]: item
            for item in extraction._extract_fields(
                "study_proof", _SYNTHETIC_STUDY_TEXT)
        }
        self.assertEqual(set(fields), _EXPECTED_STUDY_FIELDS)
        self.assertEqual(
            fields["institution_name"]["normalized_value"],
            "Example Northern Institute")
        self.assertEqual(fields["dli_number"]["normalized_value"],
                         "O19332746152")
        self.assertEqual(fields["credential_level"]["normalized_value"], "3+")
        self.assertEqual(fields["program_start"]["normalized_value"],
                         "2022-09-15")
        self.assertEqual(fields["program_end"]["normalized_value"],
                         "2026-04-30")
        self.assertEqual(fields["study_status"]["normalized_value"],
                         "graduated")


class TestStudyExtractionQuarantine(_StudyTmpCase):
    def test_extract_study_fields_born_pending_and_candidate_private(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            v, document, result, values = self._extract_study()
        try:
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(result.value_ids), len(_EXPECTED_STUDY_FIELDS))
            self.assertEqual({value.field_name for value in values},
                             _EXPECTED_STUDY_FIELDS)
            self.assertEqual(
                {value.confirmation_status for value in values}, {"pending"})
            self.assertEqual(
                {value.factor_id for value in values}, {"review.study"})
            linked_candidate = v.con.execute(
                "SELECT candidate_id FROM documents WHERE document_id = ?",
                (document.document_id,),
            ).fetchone()["candidate_id"]
            self.assertEqual(linked_candidate, "default")
            parent = v.con.execute(
                "SELECT factor_id, claimed_points, claimed_level "
                "FROM crs_profile_factors WHERE factor_id = 'review.study'"
            ).fetchone()
            self.assertIsNotNone(parent)
            self.assertIsNone(parent["claimed_points"])
            self.assertIsNone(parent["claimed_level"])
        finally:
            v.con.close()


    def test_extract_study_contamination_sweep_excludes_full_grid(self) -> None:
        v = vault.open_vault("contamination")
        try:
            vault.create_candidate(v, "contamination")
            for factor_id in FULL_GRID_FACTORS:
                vault.upsert_profile_factor(v, CrsProfileFactor(
                    factor_id=factor_id,
                    factor_group=FACTOR_GROUP[factor_id],
                    claimed_value={"synthetic": True},
                ))
            source = Path(self._tmp.name) / "contamination-study.pdf"
            source.write_bytes(mf.build_pdf([_SYNTHETIC_STUDY_TEXT]))
            document = vault.import_document(
                v, "contamination", source, doc_type="study_proof")
            try:
                extraction.extract_document(v, document.document_id)
            except extraction.MissingExtractionDependency as exc:  # pragma: no cover
                self.skipTest(f"extraction dependency unavailable: {exc.module}")
            values = vault.list_extracted_values(
                v, document_id=document.document_id)
            self.assertEqual({value.factor_id for value in values},
                             {"review.study"})
            for factor_id in FULL_GRID_FACTORS:
                with self.subTest(factor_id=factor_id):
                    count = v.con.execute(
                        "SELECT COUNT(*) FROM extracted_values "
                        "WHERE document_id = ? AND factor_id = ?",
                        (document.document_id, factor_id),
                    ).fetchone()[0]
                    self.assertEqual(count, 0)
            self.assertIn("core.age", FULL_GRID_FACTORS)
            self.assertIn("core.education", FULL_GRID_FACTORS)
            self.assertIn("additional.study", FULL_GRID_FACTORS)
        finally:
            v.con.close()

    def test_confirm_correct_reject_are_independent_per_field(self) -> None:
        v, _document, _result, values = self._extract_study("decisions")
        try:
            by_field = {value.field_name: value for value in values}
            confirmed = by_field["dli_number"].value_id
            corrected = by_field["credential_level"].value_id
            rejected = by_field["institution_name"].value_id
            vault.confirm_value(v, confirmed, "confirm")
            vault.confirm_value(
                v, corrected, "correct", corrected_value="1-2")
            vault.confirm_value(v, rejected, "reject")

            statuses = {
                value.field_name: value.confirmation_status
                for value in vault.list_extracted_values(v)
            }
            self.assertEqual(statuses["dli_number"], "confirmed")
            self.assertEqual(statuses["credential_level"], "corrected")
            self.assertEqual(statuses["institution_name"], "rejected")
            for field_name in ("program_start", "program_end", "study_status"):
                self.assertEqual(statuses[field_name], "pending")
            self.assertTrue(vault.is_audit_eligible(v, confirmed))
            self.assertTrue(vault.is_audit_eligible(v, corrected))
            self.assertFalse(vault.is_audit_eligible(v, rejected))
            for field_name in ("program_start", "program_end", "study_status"):
                self.assertFalse(vault.is_audit_eligible(
                    v, by_field[field_name].value_id))
        finally:
            v.con.close()

    def test_confirmed_low_quality_and_ambiguous_fields_stay_quarantined(self) -> None:
        v, _document, _result, values = self._extract_study("quality")
        try:
            ids = [value.value_id for value in values[:3]]
            for value_id, quality in zip(
                    ids, ("ok", "low_quality", "ambiguous"), strict=True):
                v.con.execute(
                    "UPDATE extracted_values SET quality_flag = ? "
                    "WHERE value_id = ?", (quality, value_id))
                vault.confirm_value(v, value_id, "confirm")
            v.con.commit()
            self.assertTrue(vault.is_audit_eligible(v, ids[0]))
            self.assertFalse(vault.is_audit_eligible(v, ids[1]))
            self.assertFalse(vault.is_audit_eligible(v, ids[2]))
        finally:
            v.con.close()

    def test_confirmed_field_each_five_key_stale_variant_is_quarantined(self) -> None:
        variants = (
            "file_sha",
            "render_sha",
            "parser_version",
            "profile_claim_version",
            "registry_version",
        )
        for variant in variants:
            with self.subTest(variant=variant):
                v, _document, _result, values = self._extract_study(
                    f"stale-{variant.replace('_', '-')}")
                try:
                    value = next(
                        item for item in values
                        if item.field_name == "dli_number")
                    vault.confirm_value(v, value.value_id, "confirm")
                    self.assertTrue(
                        vault.is_audit_eligible(v, value.value_id))

                    if variant == "file_sha":
                        v.con.execute(
                            "UPDATE documents SET file_sha256 = ? "
                            "WHERE document_id = ?",
                            ("f" * 64, value.document_id))
                    elif variant == "render_sha":
                        v.con.execute(
                            "UPDATE document_pages SET render_sha256 = ? "
                            "WHERE page_id = ?",
                            ("f" * 64, value.page_id))
                    elif variant == "profile_claim_version":
                        vault.upsert_profile_factor(v, CrsProfileFactor(
                            factor_id="review.study",
                            factor_group="additional_points",
                            claimed_value={"changed": True},
                        ))
                    elif variant == "registry_version":
                        v.con.execute(
                            "UPDATE extracted_values "
                            "SET confirmed_rule_registry_version = 'changed' "
                            "WHERE value_id = ?", (value.value_id,))
                    v.con.commit()

                    if variant == "parser_version":
                        patch = mock.patch.object(
                            vault, "current_parser_version",
                            return_value="changed")
                    else:
                        patch = contextlib.nullcontext()
                    with patch:
                        self.assertTrue(vault.is_stale(v, value.value_id))
                        self.assertFalse(
                            vault.is_audit_eligible(v, value.value_id))
                finally:
                    v.con.close()

    def test_review_loads_one_validated_registry_before_candidate_reads(
            self) -> None:
        v = vault.open_vault("registry-order")
        vault.create_candidate(v, "registry-order")
        healthy = mock.Mock()
        healthy.ok.return_value = True
        try:
            with (
                mock.patch(
                    "crawler.study_review.index_health.probe_snapshot",
                    return_value=healthy,
                ),
                mock.patch(
                    "crawler.study_review.crs_rules.load_registry_snapshot",
                    wraps=crs_rules.load_registry_snapshot,
                ) as load_snapshot,
            ):
                result = study_review.review_study(
                    v,
                    Path(self._tmp.name) / "unused.db",
                    candidate_id="registry-order",
                    max_age_days=30,
                )
            self.assertEqual(
                (result["status"], result["reason"]), ("N/A", "no_study_evidence"))
            load_snapshot.assert_called_once_with()
        finally:
            v.con.close()

    def test_review_registry_failure_precedes_candidate_reads_and_report(
            self) -> None:
        v = vault.open_vault("registry-refusal")
        vault.create_candidate(v, "registry-refusal")
        healthy = mock.Mock()
        healthy.ok.return_value = True
        report = v.root / "output" / "study-review" / "latest.json"
        try:
            with (
                mock.patch(
                    "crawler.study_review.index_health.probe_snapshot",
                    return_value=healthy,
                ),
                mock.patch(
                    "crawler.study_review.crs_rules.load_registry_snapshot",
                    side_effect=crs_rules.RegistryUnavailable(
                        "CRS rule registry unavailable"),
                ),
                mock.patch(
                    "crawler.study_review._candidate_values",
                    side_effect=AssertionError(
                        "candidate rows must not be read after registry failure"),
                ) as candidate_values,
            ):
                result = study_review.review_study(
                    v,
                    Path(self._tmp.name) / "unused.db",
                    candidate_id="registry-refusal",
                    max_age_days=30,
                )
            self.assertEqual(
                (result["status"], result["reason"], result["as_of"]),
                ("AT-RISK", "grounding_refused", None),
            )
            candidate_values.assert_not_called()
            self.assertFalse(report.exists())
        finally:
            v.con.close()


class TestStudyReportDurability(_StudyTmpCase):
    def _report(self, candidate: str = "durability") -> Path:
        return (
            Path(self._tmp.name) / "candidates" / candidate
            / "output" / "study-review" / "latest.json"
        )

    def test_concurrent_publishers_preserve_inflight_prepared_lkg(self) -> None:
        """A second writer cannot clean the first writer's prepared journal."""
        class SimulatedCrash(BaseException):
            pass

        report = self._report("concurrent-publishers")
        report.parent.mkdir(parents=True)
        prior = b"LAST-KNOWN-GOOD"
        report.write_bytes(prior)
        prepared = threading.Event()
        release_first = threading.Event()
        second_lock_attempted = threading.Event()
        second_recovery_entered = threading.Event()
        first_failures: list[BaseException] = []
        second_failures: list[BaseException] = []
        trace: list[str] = []
        original_begin = study_review._begin_recovery_journal
        original_lock = study_review._report_lock
        original_recover = study_review._ensure_study_report_recovered_unlocked

        def pause_first_after_journal(report_dir: Path, backup: Path) -> None:
            original_begin(report_dir, backup)
            if threading.current_thread().name == "study-publisher-a":
                trace.append("a:prepared")
                prepared.set()
                if not release_first.wait(timeout=2):
                    raise AssertionError("first publisher was not released")
                raise SimulatedCrash()

        def observe_second_lock(report_dir: Path):
            if threading.current_thread().name == "study-publisher-b":
                second_lock_attempted.set()
            return original_lock(report_dir)

        def observe_second_recovery(report_dir: Path) -> None:
            name = threading.current_thread().name
            trace.append(f"{name[-1]}:recovery")
            if name == "study-publisher-b":
                second_recovery_entered.set()
            original_recover(report_dir)

        def publish_first() -> None:
            try:
                study_review._publish_private_report(report, "first")
            except SimulatedCrash as exc:
                first_failures.append(exc)
            except BaseException as exc:  # pragma: no cover - assertion aid
                first_failures.append(exc)

        def publish_second() -> None:
            try:
                study_review._publish_private_report(report, "second")
            except BaseException as exc:  # pragma: no cover - assertion aid
                second_failures.append(exc)

        with (
            mock.patch(
                "crawler.study_review._begin_recovery_journal",
                side_effect=pause_first_after_journal,
            ),
            mock.patch(
                "crawler.study_review._report_lock",
                side_effect=observe_second_lock,
            ),
            mock.patch(
                "crawler.study_review._ensure_study_report_recovered_unlocked",
                side_effect=observe_second_recovery,
            ),
        ):
            first = threading.Thread(
                target=publish_first, name="study-publisher-a")
            second = threading.Thread(
                target=publish_second, name="study-publisher-b")
            first.start()
            self.assertTrue(prepared.wait(timeout=2))
            second.start()
            self.assertTrue(second_lock_attempted.wait(timeout=2))
            try:
                marker = report.parent / study_review._RECOVERY_MARKER_NAME
                backups = list(report.parent.glob(".latest-*.bak"))
                self.assertTrue(marker.is_file())
                self.assertEqual(len(backups), 1)
                self.assertEqual(report.read_bytes(), prior)
                self.assertEqual(backups[0].read_bytes(), prior)
                # B has attempted the lock but cannot enter the unlocked
                # recovery body while A owns it.  The old unlocked publisher
                # implementation deterministically violates this assertion.
                self.assertFalse(second_recovery_entered.is_set())
                self.assertEqual(trace, ["a:recovery", "a:prepared"])
            finally:
                release_first.set()
            first.join(timeout=2)
            second.join(timeout=2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(first_failures), 1)
        self.assertIsInstance(first_failures[0], SimulatedCrash)
        self.assertEqual(second_failures, [])
        self.assertEqual(
            trace, ["a:recovery", "a:prepared", "b:recovery"])
        self.assertEqual(report.read_bytes(), b"second")
        self.assertFalse(
            (report.parent / study_review._RECOVERY_MARKER_NAME).exists()
        )
        self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])

    def test_fsw_read_only_composition_waits_for_active_publisher(self) -> None:
        """FSW composition cannot remove a publisher's recovery artifacts."""
        from crawler import mec_screen

        report = self._report("concurrent-fsw")
        report.parent.mkdir(parents=True)
        prior = b"LAST-KNOWN-GOOD"
        report.write_bytes(prior)
        backup = study_review._create_report_backup(report)
        study_review._begin_recovery_journal(report.parent, backup)
        attempted = threading.Event()
        recovery_entered = threading.Event()
        completed = threading.Event()
        failures: list[BaseException] = []
        original_lock = study_review._report_lock
        original_recover = study_review._ensure_study_report_recovered_unlocked
        trace: list[str] = []
        healthy = mock.Mock()
        healthy.ok.return_value = True
        context = mock.Mock()
        context.registry_snapshot.registry = mock.Mock()
        context.registry_fingerprint = "a" * 64
        evidence = mock.Mock(scalars={}, candidate_id="concurrent-fsw")
        inputs = mock.Mock(sidecars={})
        inputs.with_updates.side_effect = lambda sidecars: sidecars
        vault_ = mock.Mock(root=report.parents[2])

        def observe_composition_lock(report_dir: Path):
            attempted.set()
            return original_lock(report_dir)

        def observe_recovery(report_dir: Path) -> None:
            trace.append("fsw:recovery")
            recovery_entered.set()
            original_recover(report_dir)

        def compose() -> None:
            try:
                mec_screen._compose_sidecars(
                    "fsw",
                    context,
                    evidence,
                    inputs,
                    vault_=vault_,
                    db="unused.db",
                    study_max_age_days=30,
                )
            except BaseException as exc:  # pragma: no cover - assertion aid
                failures.append(exc)
            finally:
                completed.set()

        with (
            mock.patch(
                "crawler.study_review._report_lock",
                side_effect=observe_composition_lock,
            ),
            mock.patch(
                "crawler.study_review._ensure_study_report_recovered_unlocked",
                side_effect=observe_recovery,
            ),
            mock.patch(
                "crawler.study_review.index_health.probe_snapshot",
                return_value=healthy,
            ),
            mock.patch(
                "crawler.study_review._candidate_values",
                return_value=([], []),
            ),
            mock.patch("crawler.mec_screen.employment_periods", return_value=[]),
            mock.patch(
                "crawler.policy_offer.offer_for_program_eligibility",
                return_value={"status": "N/A"},
            ),
        ):
            with original_lock(report.parent):
                worker = threading.Thread(target=compose, name="fsw-composition")
                worker.start()
                self.assertTrue(attempted.wait(timeout=2))
                marker = report.parent / study_review._RECOVERY_MARKER_NAME
                self.assertTrue(marker.is_file())
                self.assertEqual(report.read_bytes(), prior)
                self.assertEqual(backup.read_bytes(), prior)
                self.assertFalse(completed.is_set())
                self.assertFalse(recovery_entered.is_set())
                self.assertEqual(trace, [])
            self.assertTrue(recovery_entered.wait(timeout=2))
            worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertTrue(completed.is_set())
        self.assertEqual(trace, ["fsw:recovery"])
        self.assertEqual(report.read_bytes(), prior)
        self.assertFalse(
            (report.parent / study_review._RECOVERY_MARKER_NAME).exists()
        )
        self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])

    def test_lock_is_private_and_released_after_publisher_exception(self) -> None:
        """A failed publisher leaves a usable mode-0600 lock for later recovery."""
        report = self._report("lock-release")
        report.parent.mkdir(parents=True)
        report.write_bytes(b"old")
        private_detail = f"{self._tmp.name}/private/report"

        with (
            mock.patch(
                "crawler.study_review._write_report_payload",
                side_effect=OSError(private_detail),
            ),
            self.assertRaisesRegex(
                study_review.StudyReportPersistenceError,
                "^study review report persistence failed$",
            ) as caught,
        ):
            study_review._publish_private_report(report, "new")

        self.assertNotIn(private_detail, str(caught.exception))
        lock = report.parent / study_review._REPORT_LOCK_NAME
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)
        study_review._ensure_study_report_recovered(report.parent)
        self.assertEqual(report.read_bytes(), b"old")

    def test_successful_publication_replaces_prior_lkg_bytes(self) -> None:
        report = self._report()
        report.parent.mkdir(parents=True)
        report.write_bytes(b"LAST-KNOWN-GOOD")
        study_review._publish_private_report(report, '{"fresh": true}\n')
        self.assertEqual(report.read_bytes(), b'{"fresh": true}\n')
        self.assertEqual(list(report.parent.glob(".latest-*.tmp")), [])
        self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])

    def test_publication_orders_file_sync_replace_and_directory_sync(self) -> None:
        report = self._report()
        report.parent.mkdir(parents=True)
        events: list[tuple[str, object]] = []
        real_fsync = os.fsync
        real_replace = os.replace

        def fsync(descriptor):
            events.append(("fsync_file", descriptor))
            return real_fsync(descriptor)

        def replace(source, destination):
            events.append(("replace", Path(destination)))
            return real_replace(source, destination)

        with (
            mock.patch(
                "crawler.paths.mkdir_durable",
                side_effect=lambda path: events.append(("mkdir", path)),
            ),
            mock.patch("crawler.study_review.os.fsync", side_effect=fsync),
            mock.patch("crawler.study_review.os.replace", side_effect=replace),
            mock.patch(
                "crawler.paths.fsync_dir",
                side_effect=lambda path: events.append(("fsync_dir", path)),
            ),
        ):
            study_review._publish_private_report(report, '{"ok": true}\n')

        kinds = [event[0] for event in events]
        self.assertEqual(kinds, ["mkdir", "fsync_file", "replace", "fsync_dir"])
        self.assertEqual(events[0], ("mkdir", report.parent))
        self.assertEqual(events[2], ("replace", report))
        self.assertEqual(events[3], ("fsync_dir", report.parent))
        self.assertEqual(report.read_text(encoding="utf-8"), '{"ok": true}\n')
        self.assertEqual(list(report.parent.glob(".latest-*.tmp")), [])

    def test_existing_lkg_stays_canonical_until_single_atomic_swap(self) -> None:
        report = self._report()
        report.parent.mkdir(parents=True)
        prior = b"prior-canonical"
        report.write_bytes(prior)
        events: list[tuple[str, Path]] = []
        real_replace = os.replace

        def replace(source, destination):
            events.append(("replace", Path(destination)))
            if Path(destination) == report:
                self.assertEqual(report.read_bytes(), prior)
            else:
                self.assertEqual(
                    Path(destination),
                    report.parent / study_review._RECOVERY_MARKER_NAME,
                )
            return real_replace(source, destination)

        with (
            mock.patch("crawler.study_review.os.replace", side_effect=replace),
            mock.patch(
                "crawler.paths.fsync_dir",
                side_effect=lambda path: events.append(("fsync_dir", path)),
            ),
        ):
            study_review._publish_private_report(report, "new-canonical")

        self.assertEqual(
            [path for kind, path in events if kind == "replace"],
            [
                report,
                report.parent / study_review._RECOVERY_MARKER_NAME,
                report.parent / study_review._RECOVERY_MARKER_NAME,
            ],
        )
        self.assertEqual(report.read_bytes(), b"new-canonical")
        self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])

    def test_post_replace_sync_failure_atomically_restores_prior_lkg(self) -> None:
        report = self._report()
        report.parent.mkdir(parents=True)
        prior = b"prior-canonical"
        report.write_bytes(prior)
        syncs = 0

        def fsync_dir(_path):
            nonlocal syncs
            syncs += 1
            if syncs == 3:
                raise OSError("private post-replace failure")

        with (
            mock.patch("crawler.paths.fsync_dir", side_effect=fsync_dir),
            self.assertRaisesRegex(
                study_review.StudyReportPersistenceError,
                "^study review report persistence failed$",
            ),
        ):
            study_review._publish_private_report(report, "new-canonical")

        self.assertEqual(report.read_bytes(), prior)
        self.assertEqual(syncs, 7)
        self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])
        self.assertFalse(
            (report.parent / study_review._RECOVERY_MARKER_NAME).exists()
        )

    def test_crash_boundary_keeps_old_before_swap_and_new_after_swap(self) -> None:
        class SimulatedCrash(BaseException):
            pass

        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                report = self._report(f"crash-{boundary}")
                report.parent.mkdir(parents=True)
                report.write_bytes(b"old")
                real_replace = os.replace

                def replace(source, destination):
                    if boundary == "before":
                        raise SimulatedCrash()
                    real_replace(source, destination)
                    raise SimulatedCrash()

                with (
                    mock.patch(
                        "crawler.study_review.os.replace", side_effect=replace
                    ),
                    self.assertRaises(SimulatedCrash),
                ):
                    study_review._publish_private_report(report, "new")
                self.assertEqual(
                    report.read_bytes(), b"old" if boundary == "before" else b"new"
                )

    def test_atomic_restore_failure_quarantines_until_next_call_recovers(
            self) -> None:
        report = self._report("restore-failure")
        report.parent.mkdir(parents=True)
        report.write_bytes(b"old")
        real_replace = os.replace
        replaces = 0
        syncs = 0

        def replace(source, destination):
            nonlocal replaces
            replaces += 1
            if replaces == 2:
                raise OSError(f"{self._tmp.name}/private/restore")
            return real_replace(source, destination)

        def fsync_dir(_path):
            nonlocal syncs
            syncs += 1
            if syncs == 3:
                raise OSError(f"{self._tmp.name}/private/fsync")

        with (
            mock.patch("crawler.study_review.os.replace", side_effect=replace),
            mock.patch("crawler.paths.fsync_dir", side_effect=fsync_dir),
            self.assertRaisesRegex(
                study_review.StudyReportRecoveryError,
                "^study report recovery failed$",
            ) as caught,
        ):
            study_review._publish_private_report(report, "new")

        self.assertNotIn(self._tmp.name, str(caught.exception))
        self.assertEqual(report.read_bytes(), b"new")
        marker = report.parent / study_review._RECOVERY_MARKER_NAME
        backups = list(report.parent.glob(".latest-*.bak"))
        self.assertTrue(marker.is_file())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"old")

        study_review._ensure_study_report_recovered(report.parent)

        self.assertEqual(report.read_bytes(), b"old")
        self.assertFalse(marker.exists())
        self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])

    def test_persistent_atomic_restore_failure_keeps_refusing_without_mutation(
            self) -> None:
        report = self._report("fatal-restore-failure")
        report.parent.mkdir(parents=True)
        report.write_bytes(b"old")
        real_replace = os.replace
        replaces = 0
        syncs = 0

        def replace(source, destination):
            nonlocal replaces
            replaces += 1
            if replaces == 2:
                raise OSError(f"{self._tmp.name}/private/restore")
            return real_replace(source, destination)

        def fsync_dir(_path):
            nonlocal syncs
            syncs += 1
            if syncs == 3:
                raise OSError(f"{self._tmp.name}/private/fsync")

        with (
            mock.patch("crawler.study_review.os.replace", side_effect=replace),
            mock.patch("crawler.paths.fsync_dir", side_effect=fsync_dir),
            self.assertRaisesRegex(
                study_review.StudyReportRecoveryError,
                "^study report recovery failed$",
            ) as caught,
        ):
            study_review._publish_private_report(report, "new")

        self.assertNotIn(self._tmp.name, str(caught.exception))
        backups = list(report.parent.glob(".latest-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"old")
        marker = report.parent / study_review._RECOVERY_MARKER_NAME
        self.assertTrue(marker.is_file())
        quarantined = report.read_bytes()

        with (
            mock.patch(
                "crawler.study_review.os.replace",
                side_effect=OSError(f"{self._tmp.name}/private/restore"),
            ),
            self.assertRaisesRegex(
                study_review.StudyReportRecoveryError,
                "^study report recovery failed$",
            ) as second,
        ):
            study_review._ensure_study_report_recovered(report.parent)

        self.assertNotIn(self._tmp.name, str(second.exception))
        self.assertEqual(report.read_bytes(), quarantined)
        self.assertTrue(marker.is_file())
        self.assertEqual(backups[0].read_bytes(), b"old")

    def test_recovery_marker_is_durable_before_atomic_restore_attempt(self) -> None:
        report = self._report("restore-ordering")
        report.parent.mkdir(parents=True)
        report.write_bytes(b"old")
        real_replace = os.replace
        replaces = 0
        syncs = 0

        def replace(source, destination):
            nonlocal replaces
            replaces += 1
            if replaces == 2:
                marker = report.parent / study_review._RECOVERY_MARKER_NAME
                self.assertTrue(marker.is_file())
                self.assertGreaterEqual(syncs, 4)
                raise OSError("atomic restore failed")
            return real_replace(source, destination)

        def fsync_dir(_path):
            nonlocal syncs
            syncs += 1
            if syncs == 3:
                raise OSError("post-replace sync failed")

        with (
            mock.patch("crawler.study_review.os.replace", side_effect=replace),
            mock.patch("crawler.paths.fsync_dir", side_effect=fsync_dir),
            self.assertRaises(study_review.StudyReportRecoveryError),
        ):
            study_review._publish_private_report(report, "new")

    def test_malformed_marker_refuses_without_reading_canonical(self) -> None:
        report = self._report("malformed-marker")
        report.parent.mkdir(parents=True)
        report.write_bytes(b"quarantined")
        marker = report.parent / study_review._RECOVERY_MARKER_NAME
        marker.write_text('{"state":"restore_required"}', encoding="ascii")

        with (
            mock.patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("canonical must not be read"),
            ),
            self.assertRaisesRegex(
                study_review.StudyReportRecoveryError,
                "^study report recovery failed$",
            ),
        ):
            study_review._ensure_study_report_recovered(report.parent)

        self.assertTrue(marker.exists())

    def test_journal_creation_faults_preserve_or_prove_the_prior_lkg(self) -> None:
        """Failures before replace never make a markerless LKG disposable."""
        real_open = os.open
        cases = ("open", "write", "file_fsync", "directory_fsync")
        for seam in cases:
            with self.subTest(seam=seam):
                report = self._report(f"journal-{seam}")
                report.parent.mkdir(parents=True)
                report.write_bytes(b"old")
                marker = report.parent / study_review._RECOVERY_MARKER_NAME

                if seam == "open":
                    def open_journal(path, *args, **kwargs):
                        if Path(path) == marker:
                            raise OSError("journal open failed")
                        return real_open(path, *args, **kwargs)

                    patcher = mock.patch(
                        "crawler.study_review.os.open",
                        side_effect=open_journal,
                    )
                    expected = study_review.StudyReportPersistenceError
                elif seam == "write":
                    patcher = mock.patch(
                        "crawler.study_review._write_recovery_journal_payload",
                        side_effect=OSError("journal write failed"),
                    )
                    expected = study_review.StudyReportRecoveryError
                elif seam == "file_fsync":
                    patcher = mock.patch(
                        "crawler.study_review._fsync_recovery_journal_file",
                        side_effect=OSError("journal fsync failed"),
                    )
                    expected = study_review.StudyReportPersistenceError
                else:
                    calls = 0

                    def fail_journal_directory_sync(_path):
                        nonlocal calls
                        calls += 1
                        if calls == 2:
                            raise OSError("journal directory fsync failed")

                    patcher = mock.patch(
                        "crawler.paths.fsync_dir",
                        side_effect=fail_journal_directory_sync,
                    )
                    expected = study_review.StudyReportPersistenceError

                with (
                    patcher,
                    self.assertRaisesRegex(
                        expected,
                        "^study review report persistence failed$"
                        if expected is study_review.StudyReportPersistenceError
                        else "^study report recovery failed$",
                    ),
                ):
                    study_review._publish_private_report(report, "new")

                self.assertEqual(report.read_bytes(), b"old")
                backups = list(report.parent.glob(".latest-*.bak"))
                if seam == "write":
                    # A partial journal is a quarantine signal, not permission to
                    # discard the only old bytes.
                    self.assertEqual(len(backups), 1)
                    with self.assertRaises(study_review.StudyReportRecoveryError):
                        study_review._ensure_study_report_recovered(report.parent)
                    self.assertEqual(backups[0].read_bytes(), b"old")
                else:
                    # There is no journal, or its durable prepared state says the
                    # canonical is still byte-identical to the backup.
                    self.assertEqual(backups, [])
                    study_review._ensure_study_report_recovered(report.parent)

    def test_prepared_and_installed_crashes_restore_exact_prior_bytes(self) -> None:
        """Every journal state before final cleanup resolves to the old LKG."""
        for state in ("prepared", "installed"):
            with self.subTest(state=state):
                report = self._report(f"crash-{state}")
                report.parent.mkdir(parents=True)
                report.write_bytes(b"old")
                backup = study_review._create_report_backup(report)
                study_review.paths.fsync_dir(report.parent)
                study_review._begin_recovery_journal(report.parent, backup)
                staged = report.parent / ".latest-crash.tmp"
                staged.write_bytes(b"new")
                os.replace(staged, report)
                if state == "installed":
                    study_review._mark_recovery_journal_installed(
                        report.parent,
                        backup,
                        hashlib.sha256(b"new").hexdigest(),
                    )

                study_review._ensure_study_report_recovered(report.parent)

                self.assertEqual(report.read_bytes(), b"old")
                self.assertFalse(
                    (report.parent / study_review._RECOVERY_MARKER_NAME).exists()
                )
                self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])

    def test_installed_transition_faults_keep_one_complete_authority(self) -> None:
        """Prepared→installed never truncates the only valid recovery record."""
        class SimulatedCrash(BaseException):
            pass

        real_replace = os.replace
        cases = ("partial_write", "file_fsync", "replace", "dir_fsync",
                 "replace_after_side_effect")
        for seam in cases:
            with self.subTest(seam=seam):
                report = self._report(f"installed-transition-{seam}")
                report.parent.mkdir(parents=True)
                report.write_bytes(b"old")
                backup = study_review._create_report_backup(report)
                study_review._begin_recovery_journal(report.parent, backup)
                staged = report.parent / ".latest-installed-transition.tmp"
                staged.write_bytes(b"new")
                os.replace(staged, report)
                marker = report.parent / study_review._RECOVERY_MARKER_NAME

                if seam == "partial_write":
                    def partial_write(handle, payload):
                        handle.write(payload[:1])
                        raise OSError("partial write")

                    patcher = mock.patch(
                        "crawler.study_review._write_recovery_journal_payload",
                        side_effect=partial_write,
                    )
                    expected_state = "prepared"
                    expected_error = study_review.StudyReportRecoveryError
                elif seam == "file_fsync":
                    patcher = mock.patch(
                        "crawler.study_review._fsync_recovery_journal_file",
                        side_effect=OSError("journal fsync failed"),
                    )
                    expected_state = "prepared"
                    expected_error = study_review.StudyReportRecoveryError
                elif seam == "replace":
                    patcher = mock.patch(
                        "crawler.study_review.os.replace",
                        side_effect=OSError("journal replace failed"),
                    )
                    expected_state = "prepared"
                    expected_error = study_review.StudyReportRecoveryError
                elif seam == "dir_fsync":
                    patcher = mock.patch(
                        "crawler.paths.fsync_dir",
                        side_effect=OSError("journal directory fsync failed"),
                    )
                    expected_state = "installed"
                    expected_error = study_review.StudyReportRecoveryError
                else:
                    def replace_after(source, destination):
                        real_replace(source, destination)
                        raise OSError("replace wrapper raised after side effect")

                    patcher = mock.patch(
                        "crawler.study_review.os.replace",
                        side_effect=replace_after,
                    )
                    expected_state = "installed"
                    expected_error = study_review.StudyReportRecoveryError

                with (
                    patcher,
                    self.assertRaises(expected_error),
                ):
                    study_review._mark_recovery_journal_installed(
                        report.parent,
                        backup,
                        hashlib.sha256(b"new").hexdigest(),
                    )

                state = json.loads(marker.read_text(encoding="ascii"))
                self.assertEqual(state["state"], expected_state)
                self.assertEqual(backup.read_bytes(), b"old")
                self.assertEqual(
                    list(report.parent.glob(".latest-recovery-journal-*.tmp")),
                    [],
                )
                study_review._ensure_study_report_recovered(report.parent)
                self.assertEqual(report.read_bytes(), b"old")
                self.assertFalse(marker.exists())
                self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])

    def test_cleanup_pending_crash_boundaries_converge_to_verified_install(
            self) -> None:
        """Every cleanup boundary retains authority until old LKG deletion wins."""
        class SimulatedCrash(BaseException):
            pass

        real_unlink = Path.unlink
        for boundary in ("before_cleanup", "after_transition", "after_backup",
                         "after_marker"):
            with self.subTest(boundary=boundary):
                report = self._report(f"cleanup-{boundary}")
                report.parent.mkdir(parents=True)
                report.write_bytes(b"old")
                backup = study_review._create_report_backup(report)
                study_review._begin_recovery_journal(report.parent, backup)
                staged = report.parent / ".latest-cleanup.tmp"
                staged.write_bytes(b"new")
                os.replace(staged, report)
                study_review._mark_recovery_journal_installed(
                    report.parent, backup, hashlib.sha256(b"new").hexdigest())
                marker = report.parent / study_review._RECOVERY_MARKER_NAME

                if boundary == "before_cleanup":
                    patcher = mock.patch(
                        "crawler.study_review._replace_recovery_journal",
                        side_effect=SimulatedCrash(),
                    )
                elif boundary == "after_transition":
                    patcher = mock.patch(
                        "crawler.study_review._complete_cleanup_pending",
                        side_effect=SimulatedCrash(),
                    )
                else:
                    def crash_after_unlink(path, *args, **kwargs):
                        result = real_unlink(path, *args, **kwargs)
                        if (
                            boundary == "after_backup" and path == backup
                        ) or (
                            boundary == "after_marker" and path == marker
                        ):
                            raise SimulatedCrash()
                        return result

                    patcher = mock.patch.object(
                        Path, "unlink", autospec=True,
                        side_effect=crash_after_unlink,
                    )

                with patcher, self.assertRaises(SimulatedCrash):
                    study_review._finalize_recovery_journal(report.parent, backup)

                if boundary == "before_cleanup":
                    self.assertTrue(marker.exists())
                    self.assertTrue(backup.exists())
                    self.assertEqual(
                        json.loads(marker.read_text(encoding="ascii"))["state"],
                        "installed",
                    )
                    # An installed report is fail-closed and restores the LKG.
                    study_review._ensure_study_report_recovered(report.parent)
                    self.assertEqual(report.read_bytes(), b"old")
                else:
                    # The old reviewed marker-removal boundary is impossible:
                    # marker removal occurs only after old bytes are gone.
                    if boundary != "after_transition":
                        self.assertFalse(marker.exists() and backup.exists())
                    study_review._ensure_study_report_recovered(report.parent)
                    self.assertEqual(report.read_bytes(), b"new")
                self.assertFalse(marker.exists())
                self.assertEqual(list(report.parent.glob(".latest-*.bak")), [])

    def test_markerless_different_or_missing_canonical_quarantines_backup(self) -> None:
        """A stale-looking backup is never deleted unless it equals canonical."""
        for canonical in (b"new", None):
            with self.subTest(canonical=canonical):
                report = self._report(
                    "markerless-new" if canonical is not None else "markerless-missing"
                )
                report.parent.mkdir(parents=True)
                if canonical is not None:
                    report.write_bytes(canonical)
                backup = report.parent / ".latest-unlabelled.bak"
                backup.write_bytes(b"old")

                with self.assertRaisesRegex(
                    study_review.StudyReportRecoveryError,
                    "^study report recovery failed$",
                ):
                    study_review._ensure_study_report_recovered(report.parent)

                self.assertEqual(backup.read_bytes(), b"old")
                if canonical is not None:
                    self.assertEqual(report.read_bytes(), b"new")
                else:
                    self.assertFalse(report.exists())

    def test_post_replace_sync_failure_durably_removes_new_target(self) -> None:
        report = self._report()
        report.parent.mkdir(parents=True)
        private_detail = f"{self._tmp.name}/private/report"
        syncs: list[Path] = []

        def fsync_dir(path):
            syncs.append(path)
            if len(syncs) == 1:
                raise OSError(private_detail)

        with (
            mock.patch("crawler.paths.fsync_dir", side_effect=fsync_dir),
            self.assertRaisesRegex(
                study_review.StudyReportPersistenceError,
                "^study review report persistence failed$",
            ) as caught,
        ):
            study_review._publish_private_report(report, "new report")

        self.assertNotIn(private_detail, str(caught.exception))
        self.assertEqual(syncs, [report.parent, report.parent])
        self.assertFalse(report.exists())
        self.assertEqual(list(report.parent.glob(".latest-*.tmp")), [])

    def test_success_closes_staged_file_descriptor(self) -> None:
        report = self._report()
        descriptors: list[int] = []
        real_mkstemp = tempfile.mkstemp

        def mkstemp(*args, **kwargs):
            descriptor, name = real_mkstemp(*args, **kwargs)
            descriptors.append(descriptor)
            return descriptor, name

        with mock.patch(
                "crawler.study_review.tempfile.mkstemp", side_effect=mkstemp):
            study_review._publish_private_report(report, "durable")

        self.assertEqual(len(descriptors), 1)
        with self.assertRaises(OSError):
            os.fstat(descriptors[0])
        self.assertTrue(report.is_file())

    def test_mkdir_and_replace_failures_leave_no_report_or_temporary(self) -> None:
        private_detail = f"{self._tmp.name}/private/report"
        for seam, patcher in (
            ("mkdir", mock.patch(
                "crawler.paths.mkdir_durable",
                side_effect=OSError(private_detail),
            )),
            ("replace", mock.patch(
                "crawler.study_review.os.replace",
                side_effect=OSError(private_detail),
            )),
        ):
            with self.subTest(seam=seam):
                report = self._report(seam)
                if seam == "replace":
                    report.parent.mkdir(parents=True)
                with (
                    patcher,
                    self.assertRaisesRegex(
                        study_review.StudyReportPersistenceError,
                        "^study review report persistence failed$",
                    ) as caught,
                ):
                    study_review._publish_private_report(report, "new report")
                self.assertNotIn(private_detail, str(caught.exception))
                self.assertFalse(report.exists())
                if report.parent.exists():
                    self.assertEqual(
                        list(report.parent.glob(".latest-*.tmp")), [])

@unittest.skipUnless(
    (Path(__file__).resolve().parents[2] / "corpus" / "index.db").is_file(),
    "LOCAL-ONLY: real DLI-bearing corpus index is required",
)
class TestStudyReviewSidecar(_StudyTmpCase):
    _DB = Path(__file__).resolve().parents[2] / "corpus" / "index.db"

    @staticmethod
    def _study_text(dli: str, institution: str) -> str:
        return "\n".join([
            "Synthetic Proof of Canadian Studies",
            f"Institution Name: {institution}",
            f"DLI Number: {dli}",
            "Credential Level: Bachelor's degree",
            "Program Start: 15 September 2022",
            "Program End: 30 April 2026",
            "Study Status: Graduated",
        ])

    def _confirmed_candidate(self, candidate_id: str, dli: str,
                             institution: str):
        v, _document, _result, values = self._extract_study(
            candidate_id, self._study_text(dli, institution))
        for value in values:
            vault.confirm_value(v, value.value_id, "confirm")
        return v

    def _copy_index(self, name: str) -> Path:
        copied = Path(self._tmp.name) / name
        shutil.copy2(self._DB, copied)
        return copied

    @staticmethod
    def _set_candidate_dates(db: Path, dli: str,
                             designation_date: str,
                             pgwp_date: str | None = None) -> None:
        with sqlite3.connect(db) as con:
            con.execute(
                "UPDATE chunks SET crawl_date = ? WHERE chunk_id = ?",
                (designation_date, f"dli/{dli}.md#000"),
            )
            con.execute(
                "UPDATE chunks SET crawl_date = ? WHERE chunk_id = ?",
                (pgwp_date or designation_date, f"dli/{dli}.md#001"),
            )

    def _assert_provenance_refusal(
            self, name: str, db: Path, *,
            snapshot_root: Path | None = None,
            probe_patch=None) -> None:
        v = self._confirmed_candidate(
            name, "O19332746152", "University of Toronto")
        report = v.root / "output" / "study-review" / "latest.json"
        patches = []
        if snapshot_root is not None:
            patches.append(mock.patch.object(
                study_review, "_DLI_SNAPSHOT_ROOT", snapshot_root))
        if probe_patch is not None:
            patches.append(probe_patch)
        try:
            with contextlib.ExitStack() as stack:
                for patch in patches:
                    stack.enter_context(patch)
                result = study_review.review_study(
                    v, db, candidate_id=name, max_age_days=30)
            self.assertEqual(
                (result["status"], result["reason"], result["as_of"]),
                ("AT-RISK", "snapshot_provenance_mismatch", None),
            )
            self.assertFalse(report.exists())
        finally:
            v.con.close()

    def test_sidecar_exact_yes_is_historical_at_risk_and_private_only(self) -> None:
        v = self._confirmed_candidate(
            "sidecar-yes", "O19332746152", "University of Toronto")
        try:
            with mock.patch(
                    "crawler.auditor.gate_subset",
                    wraps=auditor.gate_subset) as gate:
                result = study_review.review_study(
                    v, self._DB, candidate_id="sidecar-yes", max_age_days=30)

            self.assertEqual(tuple(result), study_review.PUBLIC_FIELDS)
            self.assertEqual(result["status"], "AT-RISK")
            self.assertEqual(
                result["reason"], "designation_historical_unproven")
            self.assertEqual(result["required_count"], 5)
            self.assertEqual(result["confirmed_count"], 6)
            self.assertEqual(result["eligible_count"], 6)
            self.assertEqual(result["as_of"], "2026-07-16T18:08:26Z")
            gate.assert_called_once()

            registry = gate.call_args.args[0]
            ids = [row.rule_id for row in registry.rows]
            self.assertEqual(ids[:2], [
                "additional.study", "study.r73_definition"])
            self.assertNotIn("study.dli.designation", ids)
            dynamic = registry.rows[2:]
            self.assertEqual(len(dynamic), 2)
            self.assertTrue(all(row.factor_ids == ["review.study"]
                                for row in dynamic))
            self.assertEqual(
                [row.citations[0].chunk_id for row in dynamic],
                ["dli/O19332746152.md#000",
                 "dli/O19332746152.md#001"],
            )

            report_path = v.root / "output" / "study-review" / "latest.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["as_of"], result["as_of"])
            self.assertEqual(
                report["registry_fingerprint"], result.registry_fingerprint
            )
            self.assertIn("not legal advice", report["notice"].lower())
            self.assertEqual(
                [entry["chunk_id"] for entry in report["dynamic_citations"]],
                [row.citations[0].chunk_id for row in dynamic],
            )
            self.assertTrue(all(
                set(entry) == {
                    "rule_id", "kind", "chunk_id", "quote", "crawl_date",
                    "observed_values",
                }
                for entry in report["dynamic_citations"]
            ))
            serialized_public = json.dumps(result, ensure_ascii=False)
            for private in (
                    "O19332746152", "University of Toronto", "ev_",
                    "dli/O19332746152.md#000", str(v.root)):
                self.assertNotIn(private, serialized_public)
        finally:
            v.con.close()

    def test_injected_dynamic_composition_uses_one_loader_shared_gate_and_no_report(
            self) -> None:
        candidate = "injected-composition"
        v = self._confirmed_candidate(
            candidate, "O19332746152", "University of Toronto")
        report = v.root / "output" / "study-review" / "latest.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes(b"prior-report\n")
        before = report.read_bytes()
        try:
            with (
                mock.patch(
                    "crawler.study_review.crs_rules.load_registry_snapshot",
                    wraps=crs_rules.load_registry_snapshot,
                ) as loader,
                mock.patch(
                    "crawler.auditor.gate_subset",
                    wraps=auditor.gate_subset,
                ) as gate,
            ):
                snapshot = loader()
                result = study_review.review_study(
                    v,
                    self._DB,
                    candidate_id=candidate,
                    max_age_days=30,
                    registry_snapshot=snapshot,
                    read_only=True,
                    no_report=True,
                )

            loader.assert_called_once_with()
            gate.assert_called_once()
            self.assertEqual(result["status"], "AT-RISK")
            self.assertFalse(result.report_created)
            self.assertEqual(result.registry_fingerprint, snapshot.fingerprint)
            self.assertEqual(report.read_bytes(), before)
            self.assertEqual(list(report.parent.glob(".latest-*.tmp")), [])

            subset = gate.call_args.args[0]
            static_by_id = {
                row.rule_id: row for row in snapshot.registry.rows
                if row.rule_id in study_review._STATIC_RULE_IDS
            }
            self.assertEqual(
                subset.rows[0].model_dump(mode="json"),
                static_by_id["additional.study"].model_dump(mode="json"),
            )
            self.assertEqual(
                subset.rows[1].model_dump(mode="json"),
                static_by_id["study.r73_definition"].model_dump(mode="json"),
            )
            self.assertTrue(all(
                row.factor_ids == ["review.study"] for row in subset.rows[2:]
            ))
        finally:
            v.con.close()

    def test_sidecar_candidate_specific_pgwp_details_and_no(self) -> None:
        cases = (
            ("details", "O246878951383",
             "Centre de formation professionnelle de l’Envolée",
             "pgwp_details_manual"),
            ("no", "O110032269317", "Eston College", "pgwp_no"),
        )
        for suffix, dli, institution, reason in cases:
            with self.subTest(dli=dli):
                v = self._confirmed_candidate(
                    f"sidecar-{suffix}", dli, institution)
                try:
                    with mock.patch(
                            "crawler.auditor.gate_subset",
                            wraps=auditor.gate_subset) as gate:
                        result = study_review.review_study(
                            v, self._DB, candidate_id=f"sidecar-{suffix}",
                            max_age_days=30)
                    self.assertEqual(result["status"], "AT-RISK")
                    self.assertEqual(result["reason"], reason)
                    self.assertEqual(
                        [row.citations[0].chunk_id
                         for row in gate.call_args.args[0].rows[2:]],
                        [f"dli/{dli}.md#000", f"dli/{dli}.md#001"],
                    )
                    report = json.loads(
                        (v.root / "output" / "study-review" /
                         "latest.json").read_text(encoding="utf-8"))
                    self.assertNotIn(
                        "dli/O19332746152.md#000",
                        json.dumps(report["dynamic_citations"]))
                finally:
                    v.con.close()

    def test_candidate_date_must_be_fresh_even_when_family_is_fresh(self) -> None:
        db = self._copy_index("candidate-stale.db")
        self._set_candidate_dates(db, "O19332746152", "2026-05-01")
        with mock.patch(
                "crawler.study_review._today",
                return_value=date(2026, 7, 19)):
            self._assert_provenance_refusal("candidate-stale", db)

    def test_candidate_future_date_fails_after_shared_family_gate(self) -> None:
        db = self._copy_index("candidate-future.db")
        self._set_candidate_dates(db, "O19332746152", "2026-07-20")
        healthy_probe = mock.Mock()
        healthy_probe.ok.return_value = True
        with mock.patch(
                "crawler.study_review._today",
                return_value=date(2026, 7, 19)):
            self._assert_provenance_refusal(
                "candidate-future", db,
                probe_patch=mock.patch(
                    "crawler.study_review.index_health.probe_snapshot",
                    return_value=healthy_probe),
            )

    def test_candidate_db_date_tamper_and_common_date_mismatch_fail(self) -> None:
        cases = (
            ("date-tamper", "2026-07-15", "2026-07-15"),
            ("mixed-dates", "2026-07-16T18:08:26Z", "2026-07-15"),
        )
        for name, designation_date, pgwp_date in cases:
            with self.subTest(name=name):
                db = self._copy_index(f"{name}.db")
                self._set_candidate_dates(
                    db, "O19332746152", designation_date, pgwp_date)
                self._assert_provenance_refusal(name, db)

    def test_manifest_as_of_hash_and_relpath_mismatches_fail_closed(self) -> None:
        source_root = Path(study_review._DLI_SNAPSHOT_ROOT)
        source_manifest = json.loads(
            (source_root / "manifest.json").read_text(encoding="utf-8"))
        source_doc = source_root / "O19332746152.md"
        for variant in ("as_of", "hash", "relpath"):
            with self.subTest(variant=variant):
                root = Path(self._tmp.name) / f"snapshot-{variant}"
                root.mkdir()
                shutil.copy2(source_doc, root / source_doc.name)
                manifest = json.loads(json.dumps(source_manifest))
                if variant == "as_of":
                    manifest["as_of"] = "2026-07-15T18:08:26Z"
                    manifest["last_modified"] = manifest["as_of"]
                elif variant == "hash":
                    entry = next(
                        item for item in manifest["files"]
                        if item["file"] == source_doc.name)
                    entry["content_sha256"] = "0" * 64
                else:
                    entry = next(
                        item for item in manifest["files"]
                        if item["file"] == source_doc.name)
                    entry["file"] = "O000000000001.md"
                    manifest["files"].sort(key=lambda item: item["file"])
                # An independently canonicalized family hash prevents these
                # fixtures from relying on the production validation helper.
                canonical = json.dumps(
                    manifest["files"], ensure_ascii=False,
                    sort_keys=True).encode("utf-8")
                import hashlib
                manifest["family_sha256"] = hashlib.sha256(
                    canonical).hexdigest()
                (root / "manifest.json").write_text(
                    json.dumps(manifest), encoding="utf-8")
                self._assert_provenance_refusal(
                    f"manifest-{variant}", self._DB, snapshot_root=root)

    def test_missing_and_corrupt_manifest_fail_closed(self) -> None:
        for variant in ("missing", "corrupt"):
            with self.subTest(variant=variant):
                root = Path(self._tmp.name) / f"snapshot-{variant}"
                root.mkdir()
                if variant == "corrupt":
                    (root / "manifest.json").write_text(
                        "{not-json", encoding="utf-8")
                self._assert_provenance_refusal(
                    f"manifest-{variant}", self._DB, snapshot_root=root)

    def test_arbitrary_json_dli_corrections_refuse_without_exception(self) -> None:
        corrections = (
            (19332746152, "exact_dli_mismatch"),
            (["O19332746152"], "exact_dli_mismatch"),
            ({"dli": "O19332746152"}, "exact_dli_mismatch"),
            (True, "exact_dli_mismatch"),
            (None, "exact_dli_mismatch"),
            ("O19332746152", "designation_historical_unproven"),
        )
        for index, (correction, expected_reason) in enumerate(corrections):
            with self.subTest(correction=correction):
                candidate = f"dli-type-{index}"
                v = self._confirmed_candidate(
                    candidate, "O19332746152", "University of Toronto")
                try:
                    dli_value = next(
                        value for value in vault.list_extracted_values(v)
                        if value.field_name == "dli_number")
                    vault.confirm_value(
                        v, dli_value.value_id, "correct",
                        corrected_value=correction)
                    result = study_review.review_study(
                        v, self._DB, candidate_id=candidate,
                        max_age_days=30)
                    self.assertEqual(
                        (result["status"], result["reason"]),
                        ("AT-RISK", expected_reason),
                    )
                    report_exists = (
                        v.root / "output" / "study-review" /
                        "latest.json").exists()
                    self.assertEqual(
                        report_exists,
                        expected_reason == "designation_historical_unproven")
                finally:
                    v.con.close()

    def test_every_non_report_outcome_preserves_latest_success_bytes(self) -> None:
        candidate = "report-lifecycle"
        v = self._confirmed_candidate(
            candidate, "O19332746152", "University of Toronto")
        report = v.root / "output" / "study-review" / "latest.json"

        def success() -> None:
            result = study_review.review_study(
                v, self._DB, candidate_id=candidate, max_age_days=30)
            self.assertTrue(result.report_created)
            self.assertTrue(report.is_file())

        try:
            success()
            prior = report.read_bytes()
            result = study_review.review_study(
                v, self._DB, candidate_id=candidate, max_age_days=0)
            self.assertEqual(result["reason"], "snapshot_config_invalid")
            self.assertFalse(result.report_created)
            self.assertEqual(report.read_bytes(), prior)

            success()
            prior = report.read_bytes()
            with mock.patch(
                    "crawler.study_review._static_rows",
                    side_effect=auditor.AuditGroundingError("fixture")):
                result = study_review.review_study(
                    v, self._DB, candidate_id=candidate, max_age_days=30)
            self.assertEqual(result["reason"], "grounding_refused")
            self.assertEqual(report.read_bytes(), prior)

            success()
            prior = report.read_bytes()
            with mock.patch.object(
                    study_review, "_DLI_SNAPSHOT_ROOT",
                    Path(self._tmp.name) / "missing-snapshot"):
                result = study_review.review_study(
                    v, self._DB, candidate_id=candidate, max_age_days=30)
            self.assertEqual(result["reason"], "snapshot_provenance_mismatch")
            self.assertEqual(report.read_bytes(), prior)

            success()
            prior = report.read_bytes()
            with mock.patch(
                    "crawler.study_review.vault.is_audit_eligible",
                    return_value=False):
                result = study_review.review_study(
                    v, self._DB, candidate_id=candidate, max_age_days=30)
            self.assertEqual(result["reason"], "no_study_evidence")
            self.assertEqual(report.read_bytes(), prior)
        finally:
            v.con.close()

    def test_first_review_with_no_evidence_creates_no_report_artifacts(self) -> None:
        candidate = "first-run-empty"
        v = vault.open_vault(candidate)
        vault.create_candidate(v, candidate)
        try:
            result = study_review.review_study(
                v, self._DB, candidate_id=candidate, max_age_days=30)
            self.assertEqual(
                (result["status"], result["reason"]),
                ("N/A", "no_study_evidence"),
            )
            self.assertFalse(result.report_created)
            self.assertFalse(
                (v.root / "output" / "study-review" / "latest.json").exists())
        finally:
            v.con.close()

    def test_report_write_failure_rolls_back_latest_and_temporary(self) -> None:
        candidate = "report-write-failure"
        v = self._confirmed_candidate(
            candidate, "O19332746152", "University of Toronto")
        report = v.root / "output" / "study-review" / "latest.json"
        try:
            first = study_review.review_study(
                v, self._DB, candidate_id=candidate, max_age_days=30)
            self.assertTrue(first.report_created)
            prior = report.read_bytes()
            with mock.patch(
                    "crawler.study_review.os.replace",
                    side_effect=OSError("synthetic write failure")):
                result = study_review.review_study(
                    v, self._DB, candidate_id=candidate, max_age_days=30)
            self.assertEqual(
                (result["status"], result["reason"], result["as_of"]),
                ("AT-RISK", "report_write_failed", None),
            )
            self.assertFalse(result.report_created)
            self.assertEqual(report.read_bytes(), prior)
            self.assertEqual(
                list(report.parent.glob(".latest-*.tmp")), [])
            self.assertEqual(
                list(report.parent.glob(".latest-*.bak")), [])
        finally:
            v.con.close()

    def test_sidecar_invalid_preflight_writes_no_report(self) -> None:
        v = self._confirmed_candidate(
            "sidecar-refusal", "O19332746152", "University of Toronto")
        report = v.root / "output" / "study-review" / "latest.json"
        try:
            for invalid in (True, 0, -1, "30"):
                with self.subTest(max_age_days=invalid):
                    statements: list[str] = []
                    v.con.set_trace_callback(statements.append)
                    with mock.patch(
                            "crawler.study_review.index_health.probe_snapshot"
                    ) as probe:
                        result = study_review.review_study(
                            v, self._DB, candidate_id="sidecar-refusal",
                            max_age_days=invalid)
                    v.con.set_trace_callback(None)
                    probe.assert_not_called()
                    self.assertEqual(statements, [])
                    self.assertEqual(
                        (result["status"], result["reason"], result["as_of"]),
                        ("AT-RISK", "snapshot_config_invalid", None),
                    )
                    self.assertFalse(report.exists())

            with mock.patch(
                    "crawler.study_review.index_health.probe_snapshot"
            ) as probe:
                probe.return_value.ok.return_value = False
                result = study_review.review_study(
                    v, self._DB, candidate_id="sidecar-refusal",
                    max_age_days=17)
            probe.assert_called_once_with(
                self._DB, "dli", max_age_days=17)
            self.assertEqual(result["reason"], "snapshot_unusable")
            self.assertIsNone(result["as_of"])
            self.assertFalse(report.exists())
        finally:
            v.con.close()

    def test_sidecar_static_rows_and_source_shape_are_grounded_and_inert(self) -> None:
        registry = crs_rules.load_registry()
        r73 = [row for row in registry.rows
               if row.rule_id == "study.r73_definition"]
        self.assertEqual(len(r73), 1)
        self.assertEqual(r73[0].factor_ids, ["study.r73_definition"])
        self.assertEqual(r73[0].machine_check.kind, "accepted_enum")
        self.assertEqual(
            {item.value for item in r73[0].machine_check.accepted_values or []},
            {"completed", "graduated"},
        )
        source = Path(study_review.__file__).read_text(encoding="utf-8")
        self.assertNotIn("snapshot_policy", source)
        self.assertNotIn("searchindex.search", source)
        self.assertNotIn("SUBSTANTIATED", source)


if __name__ == "__main__":
    unittest.main()
