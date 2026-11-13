"""Real-seam factor-linkage tests (BLOCKER A) — deterministic per-document linkage.

Stdlib ``unittest`` ONLY — NO network, NO pytest fixtures. Every test drives the
REAL extraction seam (``import_document`` -> ``extraction.extract_document``) over a
SYNTHETIC born-digital PDF built at test time, then reads back
``extracted_values.factor_id`` to prove each document's values link to its SPECIFIC
claimed grid factor (language -> ``core.language.first``, nomination ->
``additional.nomination``, work -> ``core.work``, eca -> ``core.education``) and
NEVER to the alphabetically-first factor of the group (the old ``ORDER BY factor_id
LIMIT 1`` bug that landed every language value on ``core.age``).

No corpus DB is needed (this is pure extraction linkage); the class skips ONLY if
the extraction dependencies are unavailable.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_extraction_factor_linkage.py -q
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import extraction, vault
from crawler.models.vault import CrsProfileFactor
from crawler.tests.fixtures.extraction import make_fixtures as mf


class _LinkageTmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    # -- seeding helpers ---------------------------------------------------- #
    def _open(self):
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        return v

    def _claim(self, v, factor_id, group, **kw):
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id=factor_id, factor_group=group, **kw))

    def _import(self, v, data: bytes, doc_type: str, name: str = "fixture") -> str:
        src = Path(self._tmp.name) / f"{name}.pdf"
        src.write_bytes(data)
        return vault.import_document(v, "default", src, doc_type=doc_type).document_id

    def _extract(self, v, doc_id: str, **kw):
        try:
            return extraction.extract_document(v, doc_id, **kw)
        except extraction.MissingExtractionDependency as exc:  # pragma: no cover
            self.skipTest(f"extraction deps unavailable: {exc.module}")

    def _factor_ids(self, v, doc_id: str) -> list:
        return [val.factor_id
                for val in vault.list_extracted_values(v, document_id=doc_id)]

    def _values(self, v, doc_id: str):
        return vault.list_extracted_values(v, document_id=doc_id)


class TestPerDocumentFactorLinkage(_LinkageTmpCase):
    def test_language_values_link_to_claimed_first_language(self) -> None:
        v = self._open()
        try:
            self._claim(v, "core.age", "core_human_capital", claimed_value=25)
            self._claim(v, "core.language.first", "core_human_capital",
                        claimed_level="9", claimed_value=9)
            doc = self._import(v, mf.language_test_pdf(), "language_test", "lang")
            self._extract(v, doc)
            factor_ids = self._factor_ids(v, doc)
            self.assertTrue(factor_ids, "no values extracted")
            for fid in factor_ids:
                self.assertEqual(fid, "core.language.first")
                self.assertNotEqual(fid, "core.age")
        finally:
            v.con.close()

    def test_nomination_values_link_to_additional_nomination(self) -> None:
        v = self._open()
        try:
            self._claim(v, "additional.french", "additional_points",
                        claimed_value="french")
            self._claim(v, "additional.nomination", "additional_points",
                        claimed_value="nominated")
            doc = self._import(v, mf.nomination_pdf(), "nomination", "nom")
            self._extract(v, doc)
            factor_ids = self._factor_ids(v, doc)
            self.assertTrue(factor_ids)
            for fid in factor_ids:
                self.assertEqual(fid, "additional.nomination")
                self.assertNotEqual(fid, "additional.french")
        finally:
            v.con.close()

    def test_employment_values_link_to_core_work(self) -> None:
        v = self._open()
        try:
            self._claim(v, "core.work", "core_human_capital", claimed_value=3.0)
            doc = self._import(v, mf.employment_reference_pdf(),
                               "employment_reference", "emp")
            self._extract(v, doc)
            factor_ids = self._factor_ids(v, doc)
            self.assertTrue(factor_ids)
            for fid in factor_ids:
                self.assertEqual(fid, "core.work")
        finally:
            v.con.close()

    def test_eca_values_link_to_core_education(self) -> None:
        v = self._open()
        try:
            self._claim(v, "core.education", "core_human_capital",
                        claimed_level="bachelor")
            doc = self._import(v, mf.eca_pdf(), "eca", "eca")
            self._extract(v, doc)
            factor_ids = self._factor_ids(v, doc)
            self.assertTrue(factor_ids)
            for fid in factor_ids:
                self.assertEqual(fid, "core.education")
        finally:
            v.con.close()

    def test_issuer_field_does_not_leak_across_doc_types(self) -> None:
        """The shared ``issuer`` field links per-DOCUMENT, never cross-doc."""
        v = self._open()
        try:
            self._claim(v, "core.work", "core_human_capital", claimed_value=3.0)
            self._claim(v, "additional.nomination", "additional_points",
                        claimed_value="nominated")
            emp = self._import(v, mf.employment_reference_pdf(),
                               "employment_reference", "emp")
            nom = self._import(v, mf.nomination_pdf(), "nomination", "nom")
            self._extract(v, emp)
            self._extract(v, nom)
            emp_issuer = [val for val in self._values(v, emp)
                          if val.field_name == "issuer"]
            nom_issuer = [val for val in self._values(v, nom)
                          if val.field_name == "issuer"]
            self.assertTrue(emp_issuer, "employment issuer not extracted")
            self.assertTrue(nom_issuer, "nomination issuer not extracted")
            for val in emp_issuer:
                self.assertEqual(val.factor_id, "core.work")
            for val in nom_issuer:
                self.assertEqual(val.factor_id, "additional.nomination")
        finally:
            v.con.close()

    def test_no_cross_group_contamination(self) -> None:
        """No value links to a factor whose group differs from the document's."""
        v = self._open()
        try:
            self._claim(v, "core.language.first", "core_human_capital",
                        claimed_level="9", claimed_value=9)
            doc = self._import(v, mf.language_test_pdf(), "language_test", "lang")
            self._extract(v, doc)
            for val in self._values(v, doc):
                # A language document links ONLY to the core language factor.
                self.assertIn(val.factor_id, {"core.language.first", None})
                self.assertNotIn(val.factor_id,
                                 {"additional.nomination", "additional.french",
                                  "core.work"})
        finally:
            v.con.close()


class TestFactorOverride(_LinkageTmpCase):
    def test_override_links_to_claimed_second_language(self) -> None:
        v = self._open()
        try:
            self._claim(v, "core.language.second", "core_human_capital",
                        claimed_level="7", claimed_value=7)
            doc = self._import(v, mf.language_test_pdf(), "language_test", "lang2")
            self._extract(v, doc, factor_override="core.language.second")
            factor_ids = self._factor_ids(v, doc)
            self.assertTrue(factor_ids)
            for fid in factor_ids:
                self.assertEqual(fid, "core.language.second")
        finally:
            v.con.close()

    def test_cli_factor_override_threads_through(self) -> None:
        from crawler import cli
        v = self._open()
        self._claim(v, "core.language.second", "core_human_capital",
                    claimed_level="7", claimed_value=7)
        doc = self._import(v, mf.language_test_pdf(), "language_test", "lang2cli")
        v.con.close()
        rc = cli.main(["vault", "extract", "--document-id", doc,
                       "--factor", "core.language.second"])
        self.assertEqual(rc, 0)
        v2 = vault.open_vault("default")
        try:
            factor_ids = self._factor_ids(v2, doc)
            self.assertTrue(factor_ids)
            for fid in factor_ids:
                self.assertEqual(fid, "core.language.second")
        finally:
            v2.con.close()

    def test_unclaimed_target_leaves_value_unlinked(self) -> None:
        """Fail-closed: an unclaimed target factor stores values pending+unlinked."""
        v = self._open()
        try:
            # Claim NOTHING for the language group.
            doc = self._import(v, mf.language_test_pdf(), "language_test", "uncl")
            self._extract(v, doc)
            vals = self._values(v, doc)
            self.assertTrue(vals)
            for val in vals:
                self.assertIsNone(val.factor_id)
                self.assertEqual(val.confirmation_status, "pending")
        finally:
            v.con.close()

    def test_injected_non_grid_factor_override_is_not_linked(self) -> None:
        """A non-claimed / injected ``--factor`` value resolves to None (T-30GC-03)."""
        v = self._open()
        try:
            self._claim(v, "core.language.first", "core_human_capital",
                        claimed_level="9", claimed_value=9)
            doc = self._import(v, mf.language_test_pdf(), "language_test", "inj")
            self._extract(v, doc,
                          factor_override="core.language.first'; DROP TABLE x;--")
            for val in self._values(v, doc):
                self.assertIsNone(val.factor_id)
        finally:
            v.con.close()


class TestPassportDateOfBirth(_LinkageTmpCase):
    def test_passport_date_of_birth_extracted_and_linked_to_core_age(self) -> None:
        v = self._open()
        try:
            self._claim(v, "core.age", "core_human_capital", claimed_value=25)
            doc = self._import(v, mf.passport_pdf(), "passport", "passport")
            self._extract(v, doc)
            dob = [val for val in self._values(v, doc)
                   if val.field_name == "date_of_birth"]
            self.assertEqual(len(dob), 1, "expected exactly one date_of_birth value")
            self.assertEqual(dob[0].normalized_value, "1990-03-12")  # ISO
            self.assertEqual(dob[0].factor_id, "core.age")
        finally:
            v.con.close()

    def test_identity_doc_type_also_links_to_core_age(self) -> None:
        v = self._open()
        try:
            self._claim(v, "core.age", "core_human_capital", claimed_value=25)
            doc = self._import(v, mf.passport_pdf(), "identity", "identity")
            self._extract(v, doc)
            dob = [val for val in self._values(v, doc)
                   if val.field_name == "date_of_birth"]
            self.assertEqual(len(dob), 1)
            self.assertEqual(dob[0].factor_id, "core.age")
        finally:
            v.con.close()

    def test_age_fix_is_extraction_only_auditor_untouched(self) -> None:
        """The age fix is EXTRACTION-side: the frozen auditor/crs_audit are untouched.

        A tiny structural self-scan (git-independent): the passport/identity doc_type
        wiring lives in ``crawler.extraction`` (``_DOC_TYPE_FACTOR``), never inside
        the frozen auditor deciders or ``crs_audit``; and ``decide_age`` still reads
        ``date_of_birth`` from ``by_field`` (its contract is unchanged).
        """
        import inspect

        import crawler.crs_audit as crs_audit_mod
        from crawler.auditors import core as core_mod

        for mod in (crs_audit_mod, core_mod):
            src = inspect.getsource(mod)
            self.assertNotIn("passport", src)
            self.assertNotIn("_DOC_TYPE_FACTOR", src)
        # Extraction owns the identity->age link.
        self.assertEqual(extraction._DOC_TYPE_FACTOR["passport"], "core.age")
        self.assertEqual(extraction._DOC_TYPE_FACTOR["identity"], "core.age")
        # The frozen age decider still keys on date_of_birth (unchanged contract).
        self.assertIn('by_field.get("date_of_birth")',
                      inspect.getsource(core_mod.decide_age))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
