"""Adversarial extraction quarantine — REAL import->extract->confirm->audit (HARD-04).

Proves rotated / low-text / password-protected(unparseable) / ambiguous-date documents
remain quarantined and cannot green or contaminate another factor through the ACTUAL
shipped seam (``import_document`` -> ``extraction.extract_document`` ->
``vault.confirm_value`` -> ``audit_report.run_full_audit_report``). NEVER calls
``vault.add_extracted_value`` directly.

Adversarial fixtures are GENERATED AT TEST TIME via the reportlab-free
``make_fixtures.build_pdf`` writer (make_fixtures itself is left untouched). SKIPPED
(never failed) on a fresh clone where ``corpus/index.db`` is absent OR the extraction
deps are not installed — a green suite there is STRUCTURAL ONLY.

Stdlib ``unittest`` ONLY — no network.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import audit_report, crs_rules, extraction, vault
from crawler.models.vault import CrsProfileFactor
from crawler.tests.fixtures.extraction import make_fixtures as mf

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"

# A language page carrying REAL extractable ability scores (so a rotated version is a
# genuine — not vacuous — quarantine test: the page has content, only its rotation
# metadata makes it low_quality).
_LANG_PAGE = "\n".join([
    "IELTS Academic Test Report Form",
    "Test Date: 15 January 2026",
    "TRF Number: TRF-000000",
    "Listening: 8.0",
    "Reading: 8.0",
    "Writing: 7.5",
    "Speaking: 7.5",
])


def _extraction_available() -> bool:
    try:
        extraction._import_pdfium()
        extraction._import_pil()
        extraction._import_pdfminer()
        return True
    except extraction.MissingExtractionDependency:  # pragma: no cover
        return False


_EXTRACTION_OK = _extraction_available()


@unittest.skipUnless(
    _REAL_DB.is_file() and _EXTRACTION_OK,
    "LOCAL-ONLY: corpus/index.db is git-ignored and/or extraction deps are absent — "
    "the adversarial real-seam proof did NOT run; a green suite here is STRUCTURAL ONLY",
)
class AdversarialExtractionSeam(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.db = str(_REAL_DB)
        self.registry = crs_rules.load_registry()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    # -- helpers (mirror test_full_audit_real_seam) ------------------------- #
    def _claim(self, v, factor_id, group, **kw):
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id=factor_id, factor_group=group, **kw))

    def _import(self, v, data: bytes, doc_type: str, name: str) -> str:
        src = Path(self._tmp.name) / f"{name}.pdf"
        src.write_bytes(data)
        return vault.import_document(v, "default", src, doc_type=doc_type).document_id

    def _extract(self, v, doc_id):
        try:
            extraction.extract_document(v, doc_id)
        except extraction.MissingExtractionDependency as exc:  # pragma: no cover
            self.skipTest(f"extraction deps unavailable: {exc.module}")

    def _page_quality(self, v, doc_id):
        return [json.loads(r["quality_json"])
                for r in v.con.execute(
                    "SELECT quality_json FROM document_pages WHERE document_id = ? "
                    "ORDER BY page_number", (doc_id,))]

    @staticmethod
    def _card(report, factor_id):
        return next(c for c in report.factor_cards if c.factor_id == factor_id)

    @staticmethod
    def _add_round(v):
        return vault.set_ita_round(
            v, "default", "adversarial", None, "EE", cutoff_score=None)

    # -- 1. rotated scan quarantined --------------------------------------- #
    def test_rotated_scan_stays_quarantined(self) -> None:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        self._claim(v, "core.language.first", "core_human_capital",
                    claimed_points=124, claimed_level="9", claimed_value=9)
        doc = self._import(v, mf.build_pdf([_LANG_PAGE], rotations=[90]),
                           "language_test", "rot")
        self._extract(v, doc)
        # The rotation classifier fired (non-vacuous: asserts the rotated flag).
        self.assertTrue(any(q["rotated"] for q in self._page_quality(v, doc)))
        # Any produced value is low_quality; none is audit-eligible.
        for val in vault.list_extracted_values(v, document_id=doc):
            self.assertEqual(val.quality_flag, "low_quality")
        self.assertEqual(
            vault.audit_eligible_values(v, "core.language.first"), [])
        self._add_round(v)
        report, _ = audit_report.run_full_audit_report(v, self.db, self.registry)
        self.assertNotEqual(
            self._card(report, "core.language.first").verdict, "SUBSTANTIATED")
        v.con.close()

    # -- 2. low-text page quarantined -------------------------------------- #
    def test_low_text_page_stays_quarantined(self) -> None:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        self._claim(v, "core.language.first", "core_human_capital",
                    claimed_points=124, claimed_level="9", claimed_value=9)
        # A single SPARSE page (below the low-text density threshold).
        doc = self._import(v, mf.build_pdf(["Reading: 8.0"]), "language_test", "sparse")
        self._extract(v, doc)
        self.assertTrue(any(q["low_text"] for q in self._page_quality(v, doc)))
        vals = vault.list_extracted_values(v, document_id=doc)
        self.assertTrue(vals, "expected at least one extracted value from the sparse page")
        for val in vals:
            self.assertEqual(val.quality_flag, "low_quality")
            self.assertFalse(vault.is_audit_eligible(v, val.value_id))
        v.con.close()

    # -- 3. password-protected / unparseable quarantined ------------------- #
    def test_password_protected_stays_quarantined(self) -> None:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        self._claim(v, "core.age", "core_human_capital",
                    claimed_points=100, claimed_value=25)
        # A truncated/unparseable .pdf raises pdfium.PdfiumError -> password_protected.
        doc = self._import(v, b"%PDF-1.4\ntruncated garbage not a real pdf",
                           "passport", "locked")
        self._extract(v, doc)
        pages = self._page_quality(v, doc)
        self.assertTrue(any(q["password_protected"] for q in pages))
        # Unparseable -> no text -> no values -> nothing eligible (quarantine by absence).
        self.assertEqual(vault.audit_eligible_values(v, "core.age"), [])
        self._add_round(v)
        report, _ = audit_report.run_full_audit_report(v, self.db, self.registry)
        self.assertNotEqual(self._card(report, "core.age").verdict, "SUBSTANTIATED")
        v.con.close()

    # -- 4. ambiguous DOB quarantined -------------------------------------- #
    def test_ambiguous_dob_stays_quarantined(self) -> None:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        self._claim(v, "core.age", "core_human_capital",
                    claimed_points=100, claimed_value=25)
        page = "\n".join([
            "Passport / Travel Document",
            "Surname: FAKE",
            "Passport Number: X0000000",
            "Date of Birth: 05/06/1994",   # both components <= 12 -> ambiguous
            "Nationality: Syntheticania",
        ])
        doc = self._import(v, mf.build_pdf([page]), "passport", "ambig")
        self._extract(v, doc)
        dob = [val for val in vault.list_extracted_values(v, document_id=doc)
               if val.field_name == "date_of_birth"]
        self.assertTrue(dob, "expected a date_of_birth value")
        self.assertEqual(dob[0].quality_flag, "ambiguous")
        self.assertFalse(vault.is_audit_eligible(v, dob[0].value_id))
        self._add_round(v)
        report, _ = audit_report.run_full_audit_report(v, self.db, self.registry)
        self.assertNotEqual(self._card(report, "core.age").verdict, "SUBSTANTIATED")
        v.con.close()

    # -- 5. no cross-factor contamination ---------------------------------- #
    def test_no_cross_factor_contamination(self) -> None:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        # Claim ONLY the language factor; import an adversarial language doc.
        self._claim(v, "core.language.first", "core_human_capital",
                    claimed_points=124, claimed_level="9", claimed_value=9)
        self._claim(v, "core.age", "core_human_capital",
                    claimed_points=100, claimed_value=25)
        doc = self._import(v, mf.build_pdf([_LANG_PAGE], rotations=[90]),
                           "language_test", "rot")
        self._extract(v, doc)
        # No value from this language doc lands on a DIFFERENT factor (claimed-only linkage).
        for val in vault.list_extracted_values(v, document_id=doc):
            self.assertIn(val.factor_id, (None, "core.language.first"))
        # And no factor other than the (quarantined) language one has an eligible value.
        from crawler import auditors
        for fid in auditors.FULL_GRID_FACTORS:
            self.assertEqual(
                vault.audit_eligible_values(v, fid), [],
                f"factor {fid} unexpectedly has an audit-eligible value")
        v.con.close()

    # -- 6. confirm/correct cannot green an adversarial value -------------- #
    def test_confirm_or_correct_cannot_green_adversarial_value(self) -> None:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        self._claim(v, "core.age", "core_human_capital",
                    claimed_points=100, claimed_value=25)
        page = "\n".join([
            "Passport / Travel Document",
            "Surname: FAKE",
            "Date of Birth: 05/06/1994",   # ambiguous
        ])
        doc = self._import(v, mf.build_pdf([page]), "passport", "ambig2")
        self._extract(v, doc)
        dob = next(val for val in vault.list_extracted_values(v, document_id=doc)
                   if val.field_name == "date_of_birth")
        # Confirm: quality gate not bypassed (confirm_value never mutates quality_flag).
        vault.confirm_value(v, dob.value_id, "confirm")
        self.assertFalse(vault.is_audit_eligible(v, dob.value_id))
        # Correct: still not eligible (an ambiguous value stays quarantined).
        vault.confirm_value(v, dob.value_id, "correct", corrected_value="1994-05-06")
        self.assertFalse(vault.is_audit_eligible(v, dob.value_id))
        self.assertEqual(vault.audit_eligible_values(v, "core.age"), [])
        v.con.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
