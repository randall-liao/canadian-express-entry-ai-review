"""Offline tests for the extraction engine (Phase 30 — Plan 02).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Every test points
``$PR_PERSONAL_DIR`` at a throwaway ``tempfile.TemporaryDirectory`` so the vault
is created under a tmp candidate root and NEVER touches the real ``personal/``
tree. ALL document fixtures are SYNTHETIC, generated at test time with FAKE
values (``crawler/tests/fixtures/extraction/make_fixtures.py``) — never a real
document, never a committed binary fixture.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_extraction.py -q
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import extraction, paths, siblingfields, vault
from crawler.models.vault import CrsProfileFactor
from crawler.tests.fixtures.extraction import make_fixtures as mf


class _ExtractTmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _import(self, v, data: bytes, doc_type: str, ext: str = ".pdf") -> str:
        src = Path(self._tmp.name) / f"fixture{ext}"
        src.write_bytes(data)
        return vault.import_document(v, "default", src, doc_type=doc_type).document_id

    def _values_by_field(self, v, document_id):
        out = {}
        for val in vault.list_extracted_values(v, document_id=document_id):
            out.setdefault(val.field_name, []).append(val)
        return out


class TestPipeline(_ExtractTmpCase):
    def test_parser_version_is_single_source_of_truth(self) -> None:
        self.assertEqual(extraction.PARSER_VERSION, "1")
        self.assertEqual(vault.current_parser_version(), extraction.PARSER_VERSION)

    def test_all_pages_rendered_and_recorded(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.language_test_multipage_pdf(), "language_test")
            result = extraction.extract_document(v, doc)
            self.assertEqual(result.page_count, 3)
            rows = v.con.execute(
                "SELECT page_id, image_relpath, render_sha256 FROM document_pages "
                "WHERE document_id = ? ORDER BY page_number", (doc,)).fetchall()
            self.assertEqual(len(rows), 3)  # never page-one-only
            for r in rows:
                self.assertTrue(r["image_relpath"].startswith("files/rendered/"))
                self.assertIsNotNone(r["render_sha256"])
                png = paths.resolve_within(v.root, *r["image_relpath"].split("/"))
                self.assertTrue(png.is_file())
        finally:
            v.con.close()

    def test_language_fields_extracted_as_pending(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.language_test_pdf(), "language_test")
            extraction.extract_document(v, doc)
            byfield = self._values_by_field(v, doc)
            for fn in ("test_type", "test_date", "reference_number",
                       "raw_score_listening", "raw_score_reading",
                       "raw_score_writing", "raw_score_speaking"):
                self.assertIn(fn, byfield, fn)
            # 100% pending (EXTRACT-02).
            for vals in byfield.values():
                for val in vals:
                    self.assertEqual(val.confirmation_status, "pending")
            self.assertEqual(byfield["test_date"][0].normalized_value, "2026-01-15")
            self.assertEqual(byfield["raw_score_listening"][0].normalized_value, 8.5)
            self.assertEqual(byfield["test_type"][0].normalized_value.upper()[:5],
                             "IELTS")
        finally:
            v.con.close()

    def test_employment_fields_extracted(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.employment_reference_pdf(),
                               "employment_reference")
            extraction.extract_document(v, doc)
            byfield = self._values_by_field(v, doc)
            self.assertEqual(byfield["noc_code"][0].normalized_value, "21231")
            self.assertEqual(byfield["hours_per_week"][0].normalized_value, 37.5)
            self.assertEqual(byfield["duration_months"][0].normalized_value, 27)
            self.assertIn("issuer", byfield)
            self.assertEqual(byfield["employment_start"][0].normalized_value,
                             "2022-03-01")
        finally:
            v.con.close()

    def test_scanned_and_low_text_flag_low_quality(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.language_test_multipage_pdf(), "language_test")
            extraction.extract_document(v, doc)
            # Page 2 is sparse (low_text): its extracted reading value is low_quality.
            rows = v.con.execute(
                "SELECT page_id, page_number, quality_json FROM document_pages "
                "WHERE document_id = ? ORDER BY page_number", (doc,)).fetchall()
            # Page 3 (scanned) is flagged low_quality with no values.
            scanned_page = rows[2]["page_id"]
            n_vals_scanned = v.con.execute(
                "SELECT COUNT(*) FROM extracted_values WHERE page_id = ?",
                (scanned_page,)).fetchone()[0]
            self.assertEqual(n_vals_scanned, 0)
            self.assertIn("scanned", rows[2]["quality_json"])
            # Any value on the sparse page is low_quality (never silent 'ok').
            sparse_vals = v.con.execute(
                "SELECT quality_flag FROM extracted_values WHERE page_id = ?",
                (rows[1]["page_id"],)).fetchall()
            self.assertTrue(sparse_vals)
            for r in sparse_vals:
                self.assertEqual(r["quality_flag"], "low_quality")
        finally:
            v.con.close()

    def test_ambiguous_date_flags_ambiguous(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.ambiguous_date_pdf(), "language_test")
            extraction.extract_document(v, doc)
            byfield = self._values_by_field(v, doc)
            self.assertEqual(byfield["test_date"][0].quality_flag, "ambiguous")
        finally:
            v.con.close()

    def test_rotated_page_flagged_low_quality(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.rotated_scan_pdf(), "language_test")
            extraction.extract_document(v, doc)
            q = v.con.execute(
                "SELECT quality_json FROM document_pages WHERE document_id = ?",
                (doc,)).fetchone()["quality_json"]
            self.assertIn("rotated", q)
        finally:
            v.con.close()

    def test_image_input_single_page(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.synthetic_image_png(), "passport", ext=".png")
            result = extraction.extract_document(v, doc)
            self.assertEqual(result.page_count, 1)
            row = v.con.execute(
                "SELECT quality_json, image_relpath FROM document_pages "
                "WHERE document_id = ?", (doc,)).fetchone()
            self.assertTrue(row["image_relpath"].startswith("files/rendered/"))
            # No embedded text + OCR unavailable → scanned/low_quality (not silent).
            self.assertIn("scanned", row["quality_json"])
        finally:
            v.con.close()

    def test_rerun_uses_render_cache(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.language_test_pdf(), "language_test")
            first = extraction.extract_document(v, doc)
            self.assertGreaterEqual(first.rendered_pages, 1)
            self.assertEqual(first.cached_pages, 0)
            png = paths.resolve_within(
                v.root, "files", "rendered", doc, "page-0001.png")
            mtime_before = png.stat().st_mtime_ns
            second = extraction.extract_document(v, doc)
            self.assertEqual(second.rendered_pages, 0)
            self.assertEqual(second.cached_pages, second.page_count)
            self.assertEqual(png.stat().st_mtime_ns, mtime_before)  # not re-rendered
        finally:
            v.con.close()

    def test_missing_dependency_raises_typed(self) -> None:
        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.language_test_pdf(), "language_test")
            with mock.patch.object(
                    extraction, "_import_pdfium",
                    side_effect=extraction.MissingExtractionDependency(
                        "pypdfium2", "doc-extract")):
                with self.assertRaises(extraction.MissingExtractionDependency):
                    extraction.extract_document(v, doc)
        finally:
            v.con.close()


class TestPiiStaysInVault(_ExtractTmpCase):
    def test_no_pii_to_stdout_or_corpus(self) -> None:
        # A sibling corpus/ must be untouched; stdout must carry no fake values.
        corpus_dir = Path(self._tmp.name) / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "index.db").write_bytes(b"CORPUS-SENTINEL")
        before = sorted((p.name, p.read_bytes()) for p in corpus_dir.iterdir())

        v = vault.open_vault("default")
        try:
            doc = self._import(v, mf.language_test_pdf(), "language_test")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                extraction.extract_document(v, doc)
            captured = buf.getvalue()
            for token in (mf.FAKE_TRF, mf.FAKE_LISTENING, mf.FAKE_SPEAKING):
                self.assertNotIn(token, captured)
            # corpus untouched.
            after = sorted((p.name, p.read_bytes()) for p in corpus_dir.iterdir())
            self.assertEqual(before, after)
            # The fake values DO live in the vault text artifact (files/text/).
            text_file = paths.resolve_within(
                v.root, "files", "text", f"{doc}.txt")
            self.assertTrue(text_file.is_file())
            self.assertIn(mf.FAKE_TRF, text_file.read_text(encoding="utf-8"))
            # And rendered images live under the vault only.
            rendered = paths.resolve_within(v.root, "files", "rendered", doc)
            self.assertTrue(rendered.is_dir())
            self.assertTrue(paths.is_within(v.root, rendered))
        finally:
            v.con.close()


class TestSiblingExtraction(_ExtractTmpCase):
    """COV-03: a ``sibling_proof`` document extracts four born-pending sibling
    fields, linked claimed-only to ``additional.sibling`` (UNLINKED when the factor
    is not claimed, and NEVER to ``core.age`` / ``additional.nomination``).

    Drives the REAL extraction seam over a SYNTHETIC born-digital fixture; skips
    (never errors) if the extraction dependencies are unavailable, mirroring the
    other real-extraction cases.
    """

    _SIBLING_FIELDS = ("sibling_relationship", "sibling_status",
                       "sibling_residence", "sibling_date_of_birth")

    def _open_with_candidate(self):
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        return v

    def _extract_or_skip(self, v, document_id):
        try:
            return extraction.extract_document(v, document_id)
        except extraction.MissingExtractionDependency as exc:  # pragma: no cover
            self.skipTest(f"extraction deps unavailable: {exc.module}")

    def test_sibling_fields_pending_first_and_linked_when_claimed(self) -> None:
        v = self._open_with_candidate()
        try:
            # CLAIM additional.sibling → the document's values link to it.
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="additional.sibling", factor_group="additional_points",
                claimed_value="sibling"))
            doc = self._import(v, mf.sibling_proof_pdf(), "sibling_proof")
            self._extract_or_skip(v, doc)
            byfield = self._values_by_field(v, doc)
            # All four sibling fields appear.
            for fn in self._SIBLING_FIELDS:
                self.assertIn(fn, byfield, fn)
            # Born-quarantined: EVERY sibling value is pending (never born-confirmed).
            for vals in byfield.values():
                for val in vals:
                    self.assertEqual(val.confirmation_status, "pending")
            # DOB normalized to ISO via the shipped _normalize_date path.
            self.assertEqual(
                byfield["sibling_date_of_birth"][0].normalized_value, "1988-03-12")
            # Claimed-only linkage: every value links to additional.sibling and to
            # NOTHING else (no cross-factor contamination).
            for vals in byfield.values():
                for val in vals:
                    self.assertEqual(val.factor_id, "additional.sibling")
                    self.assertNotIn(
                        val.factor_id, {"core.age", "additional.nomination"})
        finally:
            v.con.close()

    def test_sibling_values_unlinked_when_factor_not_claimed(self) -> None:
        v = self._open_with_candidate()
        try:
            # Claim NOTHING → fail-closed: values are pending and UNLINKED.
            doc = self._import(v, mf.sibling_proof_pdf(), "sibling_proof")
            self._extract_or_skip(v, doc)
            vals = vault.list_extracted_values(v, document_id=doc)
            self.assertTrue(vals, "no sibling values extracted")
            for val in vals:
                self.assertIsNone(
                    val.factor_id, "unclaimed sibling value must be UNLINKED")
                self.assertEqual(val.confirmation_status, "pending")
        finally:
            v.con.close()

    def test_sibling_evidence_never_lands_on_core_age_or_nomination(self) -> None:
        """Even with sibling AND unrelated factors claimed, a sibling document's
        values link ONLY to additional.sibling — never bleed into age/nomination."""
        v = self._open_with_candidate()
        try:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="additional.sibling", factor_group="additional_points",
                claimed_value="sibling"))
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="core.age", factor_group="core_human_capital",
                claimed_value=25))
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="additional.nomination", factor_group="additional_points",
                claimed_value="nominated"))
            doc = self._import(v, mf.sibling_proof_pdf(), "sibling_proof")
            self._extract_or_skip(v, doc)
            for val in vault.list_extracted_values(v, document_id=doc):
                self.assertEqual(val.factor_id, "additional.sibling")
                self.assertNotIn(
                    val.factor_id, {"core.age", "additional.nomination"})
        finally:
            v.con.close()

    def test_realistic_cased_sibling_values_canonicalize_at_extraction(self) -> None:
        """WR-01: a document printing NATURAL surface forms (``Brother`` /
        ``Permanent Resident``) canonicalizes the two closed-enum text fields to the
        shared accepted vocabulary at extraction, while ``raw_text`` keeps the
        verbatim value — so the confirmed ``normalized_value`` the decider gates on
        is the accepted token, not the enum-spelled fixture token."""
        v = self._open_with_candidate()
        try:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="additional.sibling", factor_group="additional_points",
                claimed_value="sibling"))
            page = "\n".join([
                "Proof of Relative in Canada",
                "Relationship: Brother",
                "Immigration Status: Permanent Resident",
                "Current Residence: Toronto, Ontario, Canada",
                "Date of Birth: 12 March 1988",
            ])
            doc = self._import(v, mf.build_pdf([page]), "sibling_proof")
            self._extract_or_skip(v, doc)
            byfield = self._values_by_field(v, doc)
            for fn in self._SIBLING_FIELDS:
                self.assertIn(fn, byfield, fn)
            rel = byfield["sibling_relationship"][0]
            status = byfield["sibling_status"][0]
            # normalized_value is the canonical accepted token (decider gates here)…
            self.assertEqual(rel.normalized_value, "brother")
            self.assertEqual(status.normalized_value, "permanent_resident")
            self.assertIn(rel.normalized_value,
                          siblingfields.SIBLING_RELATIONSHIP_ACCEPTED)
            self.assertIn(status.normalized_value,
                          siblingfields.SIBLING_STATUS_ACCEPTED)
            # …while raw_text preserves the verbatim document surface form.
            self.assertEqual(rel.raw_text, "Brother")
            self.assertEqual(status.raw_text, "Permanent Resident")
        finally:
            v.con.close()

    def test_unknown_sibling_status_token_is_not_coerced_at_extraction(self) -> None:
        """WR-01 fail-closed: an unrecognized status surface form is NEVER coerced
        to an accepted token — normalized_value stays a non-member."""
        v = self._open_with_candidate()
        try:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="additional.sibling", factor_group="additional_points",
                claimed_value="sibling"))
            page = "\n".join([
                "Proof of Relative in Canada",
                "Relationship: Cousin",
                "Immigration Status: Temporary Visitor",
                "Current Residence: Toronto, Ontario, Canada",
                "Date of Birth: 12 March 1988",
            ])
            doc = self._import(v, mf.build_pdf([page]), "sibling_proof")
            self._extract_or_skip(v, doc)
            byfield = self._values_by_field(v, doc)
            self.assertNotIn(byfield["sibling_relationship"][0].normalized_value,
                             siblingfields.SIBLING_RELATIONSHIP_ACCEPTED)
            self.assertNotIn(byfield["sibling_status"][0].normalized_value,
                             siblingfields.SIBLING_STATUS_ACCEPTED)
        finally:
            v.con.close()

    def test_sibling_fake_tokens_stay_in_vault_not_stdout(self) -> None:
        """The FAKE sibling PII tokens live in the vault text artifact ONLY — never
        on stdout (reuses the TestPiiStaysInVault perimeter pattern)."""
        v = self._open_with_candidate()
        try:
            doc = self._import(v, mf.sibling_proof_pdf(), "sibling_proof")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    extraction.extract_document(v, doc)
                except extraction.MissingExtractionDependency as exc:  # pragma: no cover
                    self.skipTest(f"extraction deps unavailable: {exc.module}")
            captured = buf.getvalue()
            for token in (mf.FAKE_SIBLING_RELATIONSHIP, mf.FAKE_SIBLING_STATUS,
                          mf.FAKE_SIBLING_RESIDENCE, mf.FAKE_SIBLING_DOB):
                self.assertNotIn(token, captured)
            # The fake values DO live in the vault-only text artifact.
            text_file = paths.resolve_within(
                v.root, "files", "text", f"{doc}.txt")
            self.assertTrue(text_file.is_file())
            self.assertIn(mf.FAKE_SIBLING_RESIDENCE,
                          text_file.read_text(encoding="utf-8"))
        finally:
            v.con.close()


if __name__ == "__main__":
    unittest.main()
