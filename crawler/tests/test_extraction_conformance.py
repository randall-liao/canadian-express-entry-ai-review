"""Phase-30 milestone conformance gate (Plan 04 — SC1–SC5 + no-PII).

Stdlib ``unittest`` ONLY — NO pytest, NO network. Proves all five Phase-30
success criteria end-to-end with ADVERSARIAL synthetic fixtures (PITFALLS-v4.0
Pitfall 1 misreads + Pitfall 12 staleness), and that NO extraction PII reaches
any ``--json`` stdout envelope across the whole extract→fields→confirm→doctor
flow. ALL fixtures are SYNTHETIC (Plan-02 generator + directly-inserted rows),
tempdir-only, never real PII.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_extraction_conformance.py -q
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import confirm, doctor, extraction, mecfields, vault
from crawler.models.vault import CrsProfileFactor
from crawler.tests.fixtures.extraction import make_fixtures as mf


class _ConformanceCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self._json_stdout: list[str] = []

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        from crawler import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        if "--json" in argv:
            self._json_stdout.append(out.getvalue())
        return rc, out.getvalue(), err.getvalue()

    def _import_cli(self, data: bytes, doc_type: str) -> str:
        src = Path(self._tmp.name) / "d.pdf"
        src.write_bytes(data)
        rc, out, _ = self._run(
            ["--json", "vault", "import", str(src), "--doc-type", doc_type])
        self.assertEqual(rc, 0)
        return json.loads(out)["result"]["document_id"]

    def _seed_value(self, v, *, field_name, quality_flag="ok",
                    normalized_value=0, raw_text="x", factor_id="core_lang"):
        """Directly insert one synthetic pending value (adversarial rows)."""
        cid = v.candidate_id
        vault.create_candidate(v, cid)
        document_id = vault.new_document_id()
        now = vault._now()
        v.con.execute(
            "INSERT INTO documents(document_id, candidate_id, evidence_id, "
            "doc_type, file_sha256, storage_relpath, original_name, mime_type, "
            "byte_size, page_count, added_at, status) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (document_id, cid, vault.new_evidence_id(), "language_test",
             "a" * 64, f"files/raw/{'a' * 64}.pdf", None, None, 1, 1, now,
             "extracted"))
        v.con.commit()
        run_id = vault.record_extraction_run(
            v, document_id=document_id, parser_version="1",
            engine_json={"e": 1}, status="complete")
        page_id = vault.add_document_page(
            v, document_id=document_id, page_number=1,
            image_relpath=f"files/rendered/{document_id}/page-0001.png",
            render_sha256="b" * 64, extraction_run_id=run_id)
        if factor_id is not None:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id=factor_id, factor_group="core_human_capital",
                claimed_points=124, claimed_level="CLB 9",
                claimed_value={"clb": 9}, source="user_entry"))
        return vault.add_extracted_value(
            v, document_id=document_id, page_id=page_id, factor_id=factor_id,
            field_name=field_name, raw_text=raw_text,
            normalized_value=normalized_value, bbox=[0, 0, 1, 1],
            extractor_confidence=0.9, quality_flag=quality_flag,
            extraction_run_id=run_id)

    def _set_factor_cli(self) -> None:
        # The language_test doc_type deterministically links to the SPECIFIC grid
        # factor core.language.first (BLOCKER-A fix), so claim THAT factor.
        self._run(["--json", "vault", "profile", "set", "--factor-id",
                   "core.language.first", "--group", "core_human_capital",
                   "--points", "124", "--level", "CLB 9",
                   "--value-json", '{"clb": 9}'])


class TestSC1(_ConformanceCase):
    def test_extraction_produces_pending_only(self) -> None:
        doc = self._import_cli(mf.language_test_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        rc, out, _ = self._run(["--json", "vault", "fields"])
        for f in json.loads(out)["result"]["fields"]:
            self.assertEqual(f["confirmation_status"], "pending")
            self.assertFalse(f["audit_eligible"])


class TestSC2(_ConformanceCase):
    def test_view_exposes_five_facets(self) -> None:
        self._set_factor_cli()
        doc = self._import_cli(mf.language_test_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        v = vault.open_vault("default")
        try:
            vals = vault.list_extracted_values(v, document_id=doc)
            listening = next(x for x in vals
                             if x.field_name == "raw_score_listening")
            view = confirm.build_field_view(v, listening.value_id)
            self.assertEqual(view["raw_value"], mf.FAKE_LISTENING)  # "8.5"
            self.assertEqual(view["normalized_value"], float(mf.FAKE_LISTENING))
            self.assertTrue(view["image_relpath"].startswith("files/rendered/"))
            self.assertEqual(view["factor_id"], "core.language.first")
            self.assertEqual(view["claimed_level"], "CLB 9")
        finally:
            v.con.close()


class TestSC3Adversarial(_ConformanceCase):
    """No pending / rejected / low_quality / ambiguous / stale value is eligible."""

    def test_adversarial_matrix_never_eligible(self) -> None:
        v = vault.open_vault("default")
        try:
            # (1) CLB 8-vs-9 boundary read left PENDING → not eligible.
            clb = self._seed_value(v, field_name="clb_reading",
                                   normalized_value=8, raw_text="CLB 8")
            self.assertFalse(vault.is_audit_eligible(v, clb))
            # (2) IELTS listening/reading column SWAP, pending → not eligible.
            swap = self._seed_value(v, field_name="raw_score_listening",
                                    normalized_value=7.5,
                                    raw_text="Listening: 7.5 (reading value)")
            self.assertFalse(vault.is_audit_eligible(v, swap))
            # (3) ambiguous date, even CONFIRMED → not eligible (quality != ok).
            amb = self._seed_value(v, field_name="test_date",
                                   quality_flag="ambiguous",
                                   normalized_value="2024-03-04",
                                   raw_text="03/04/2024")
            vault.confirm_value(v, amb, "confirm")
            self.assertFalse(vault.is_audit_eligible(v, amb))
            # (4) NOC read from a footer, low_quality, confirmed → not eligible.
            noc = self._seed_value(v, field_name="noc_code",
                                   quality_flag="low_quality",
                                   normalized_value="21231",
                                   raw_text="footer: 21231",
                                   factor_id=None)
            vault.confirm_value(v, noc, "confirm")
            self.assertFalse(vault.is_audit_eligible(v, noc))
            # (5) low-text scan value, confirmed → not eligible.
            scan = self._seed_value(v, field_name="raw_score_speaking",
                                    quality_flag="low_quality",
                                    normalized_value=6.0, factor_id=None)
            vault.confirm_value(v, scan, "confirm")
            self.assertFalse(vault.is_audit_eligible(v, scan))
            # (6) stale confirmation → not eligible.
            stale = self._seed_value(v, field_name="clb_writing",
                                     normalized_value=9, factor_id=None)
            vault.confirm_value(v, stale, "confirm")
            self.assertTrue(vault.is_audit_eligible(v, stale))  # control before
            v.con.execute(
                "UPDATE extracted_values "
                "SET confirmed_rule_registry_version = 'obsolete' "
                "WHERE value_id = ?", (stale,))
            v.con.commit()
            self.assertFalse(vault.is_audit_eligible(v, stale))
            # positive control: confirmed + ok + fresh IS eligible.
            good = self._seed_value(v, field_name="clb_listening",
                                    normalized_value=9, factor_id=None)
            vault.confirm_value(v, good, "confirm")
            self.assertTrue(vault.is_audit_eligible(v, good))
        finally:
            v.con.close()


class TestSC4Staleness(_ConformanceCase):
    def test_all_four_triggers_mark_stale(self) -> None:
        for trigger in ("file", "parser", "claim", "registry"):
            with self.subTest(trigger=trigger):
                v = vault.open_vault(f"sc4-{trigger}")
                try:
                    vid = self._seed_value(v, field_name="clb_speaking",
                                           normalized_value=9)
                    vault.confirm_value(v, vid, "confirm")
                    self.assertTrue(vault.is_audit_eligible(v, vid))
                    val = vault.get_extracted_value(v, vid)
                    if trigger == "file":
                        v.con.execute(
                            "UPDATE documents SET file_sha256 = ? "
                            "WHERE document_id = ?", ("f" * 64, val.document_id))
                        v.con.commit()
                        self.assertTrue(vault.is_stale(v, vid))
                        self.assertFalse(vault.is_audit_eligible(v, vid))
                    elif trigger == "parser":
                        with mock.patch.object(vault, "current_parser_version",
                                               return_value="2"):
                            self.assertTrue(vault.is_stale(v, vid))
                            self.assertFalse(vault.is_audit_eligible(v, vid))
                    elif trigger == "claim":
                        vault.upsert_profile_factor(v, CrsProfileFactor(
                            factor_id="core_lang",
                            factor_group="core_human_capital",
                            claimed_points=999, claimed_level="CLB 10",
                            claimed_value={"clb": 10}, source="user_entry"))
                        self.assertTrue(vault.is_stale(v, vid))
                        self.assertFalse(vault.is_audit_eligible(v, vid))
                    else:  # registry
                        v.con.execute(
                            "UPDATE extracted_values "
                            "SET confirmed_rule_registry_version = 'obsolete' "
                            "WHERE value_id = ?", (vid,))
                        v.con.commit()
                        self.assertTrue(vault.is_stale(v, vid))
                        self.assertFalse(vault.is_audit_eligible(v, vid))
                    # ...re-confirmation clears it.
                    if trigger == "parser":
                        # confirmed_parser_version is captured from the run (="1");
                        # under the real current version ("1") it is fresh again.
                        vault.confirm_value(v, vid, "confirm")
                        self.assertFalse(vault.is_stale(v, vid))
                    else:
                        vault.confirm_value(v, vid, "confirm")
                        self.assertFalse(vault.is_stale(v, vid))
                        self.assertTrue(vault.is_audit_eligible(v, vid))
                finally:
                    v.con.close()


class TestSC5Doctor(_ConformanceCase):
    def test_doctor_surfaces_missing_deps(self) -> None:
        with mock.patch.object(
                extraction, "_import_pdfium",
                side_effect=extraction.MissingExtractionDependency(
                    "pypdfium2", "doc-extract")):
            report = doctor.run_doctor()
        self.assertEqual(report.overall, "missing_dependency")
        self.assertIn("pypdfium2", report.missing_required())

    def test_doctor_surfaces_scan_quality(self) -> None:
        doc = self._import_cli(mf.language_test_multipage_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        report = doctor.run_doctor(candidate="default", document_id=doc)
        self.assertEqual(report.overall, "ok")
        self.assertEqual(report.quality_counts["pages"], 3)
        self.assertGreaterEqual(report.quality_counts["scanned"], 1)
        self.assertGreaterEqual(report.quality_counts["low_text"], 1)


class TestNoPiiAcrossFlow(_ConformanceCase):
    def test_no_fake_pii_on_any_json_envelope(self) -> None:
        self._set_factor_cli()
        doc = self._import_cli(mf.employment_reference_pdf(),
                               "employment_reference")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        rc, out, _ = self._run(["--json", "vault", "fields"])
        fields = json.loads(out)["result"]["fields"]
        self._run(["--json", "vault", "confirm", "--value-id",
                   fields[0]["value_id"], "--decision", "confirm"])
        self._run(["--json", "doctor", "--candidate", "default",
                   "--document-id", doc])
        combined = "".join(self._json_stdout)
        for token in (mf.FAKE_NOC, mf.FAKE_EMPLOYER, "37.5", "2022-03-01",
                      "files/rendered", "files/text", self._tmp.name):
            self.assertNotIn(token, combined)


class TestMecEvidenceConformance(_ConformanceCase):
    def test_all_canonical_forms_are_closed_normalized_and_period_safe(self) -> None:
        self.assertEqual(
            set(mecfields.MEC_DOCUMENT_FIELDS),
            {
                "mec-profile",
                "mec-employment-period",
                "mec-trade-certificate",
                "mec-valid-offer",
                "mec-funds",
                "mec-province-status",
            },
        )
        self.assertEqual(
            {
                name for name, _label, _kind
                in extraction._FIELD_SPECS["mec-employment-period"]
            },
            mecfields.MEC_DOCUMENT_FIELDS["mec-employment-period"]
            - {"employment_period_id"},
        )
        first = mecfields.employment_period_id("a" * 64)
        self.assertEqual(first, mecfields.employment_period_id("a" * 64))
        self.assertNotEqual(first, mecfields.employment_period_id("b" * 64))

        text = "\n".join(
            (
                "Employment Start: 2024-01-01",
                "Employment End: 2024-12-31",
                "Paid Status: yes",
                "Student Status: no",
                "Self Employed: no",
                "Work Country: Canada",
                "Work Province: Ontario",
                "Work Authorized: yes",
                "Temporary Resident Status: valid",
                "NOC Code: 21231",
                "TEER: 1",
                "NOC Version Date: 2021-10-27",
                "NOC Version: NOC 2021",
                "Hours per Week: 30",
                "Total Hours: 1560",
                "Qualified to Practise: yes",
            )
        )
        values = extraction._extract_fields("mec-employment-period", text)
        self.assertTrue(values)
        self.assertTrue(all(not value["ambiguous"] for value in values))
        invalid = extraction._extract_fields(
            "mec-employment-period", "Paid Status: perhaps"
        )
        self.assertEqual(invalid[0]["normalized_value"], None)
        self.assertTrue(invalid[0]["ambiguous"])

        offer_values = extraction._extract_fields(
            "mec-valid-offer",
            "\n".join(
                (
                    "Offer Permit Valid at Visa Issuance: yes",
                    "Offer LMIA Exemption Basis: significant_benefit",
                )
            ),
        )
        self.assertEqual(
            {
                value["field_name"]: value["normalized_value"]
                for value in offer_values
            },
            {
                "offer_permit_valid_at_visa_issuance": True,
                "offer_lmia_exemption_basis": "significant_benefit",
            },
        )
        for invalid_basis in (
            "lmia exempt",
            "International_Agreement",
            "unknown",
        ):
            normalized, ambiguous = mecfields.normalize_mec_field(
                "offer_lmia_exemption_basis",
                invalid_basis,
            )
            with self.subTest(invalid_basis=invalid_basis):
                self.assertIsNone(normalized)
                self.assertTrue(ambiguous)

    def test_mec_factor_is_locked_and_never_enters_crs_grid(self) -> None:
        from crawler import auditors
        from crawler.models import audit

        self.assertEqual(
            extraction._DOC_TYPE_FACTOR["mec-funds"],
            "review.mec",
        )
        self.assertNotIn("review.mec", auditors.FULL_GRID_FACTORS)
        self.assertNotIn("mec", audit.PublicAuditEnvelope.model_fields)


if __name__ == "__main__":
    unittest.main()
