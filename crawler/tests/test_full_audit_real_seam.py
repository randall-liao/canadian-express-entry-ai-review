"""REAL extract -> confirm -> audit end-to-end regression (Phase 30 — Plan 05, Task 4).

This is the file that exercises the ACTUAL shipped seam — ``import_document`` ->
``extraction.extract_document`` -> ``vault.confirm_value`` ->
``audit_report.run_full_audit_report`` — the path that was previously UNTESTED
(``test_full_audit_integration.py`` bypasses it by calling
``vault.add_extracted_value(...)`` with hard-coded grid factor ids / test_type /
doc_types). It NEVER calls ``add_extracted_value`` directly.

It proves the two milestone INTEGRATION blockers are closed through the real code:

* BLOCKER A (factor linkage): a language document's values land on
  ``core.language.first`` (not the alphabetically-first ``core.age``), so the
  factor-specific auditor read finds its evidence.
* BLOCKER B (test_type vocabulary): the ``IELTS`` token the fixture prints is
  normalized to the registry-accepted ``IELTS General Training`` at extraction, so
  the conversion tables ground and the language card reaches SUBSTANTIATED.

Stdlib ``unittest`` ONLY — NO network. SKIPPED (never failed) on a fresh clone
where the git-ignored ``corpus/index.db`` is absent OR the extraction deps are not
installed — a green suite there is STRUCTURAL ONLY.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_full_audit_real_seam.py -q
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from crawler import audit_report, crs_rules, extraction, vault
from crawler.models.vault import CrsProfileFactor
from crawler.tests.fixtures.extraction import make_fixtures as mf

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"

# A FIXED reference date shortly AFTER the fixture's language test date
# (15 January 2026) so the grounded 2-year language validity window holds
# DETERMINISTICALLY, independent of the wall clock the test runs on.
_ROUND_DATE = "2026-06-15"


def _extraction_available() -> bool:
    """True iff the heavy extraction deps (pypdfium2/Pillow/pdfminer) import."""
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
    "LOCAL-ONLY: corpus/index.db is git-ignored and/or extraction deps are absent "
    "— the REAL extract->confirm->audit seam proof did NOT run; a green suite here "
    "is STRUCTURAL ONLY",
)
class RealExtractConfirmAuditSeam(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.db = str(_REAL_DB)
        self.registry = crs_rules.load_registry()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    # -- real-seam seeding -------------------------------------------------- #
    def _claim(self, v, factor_id, group, **kw):
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id=factor_id, factor_group=group, **kw))

    def _import(self, v, data: bytes, doc_type: str, name: str) -> str:
        src = Path(self._tmp.name) / f"{name}.pdf"
        src.write_bytes(data)
        return vault.import_document(
            v, "default", src, doc_type=doc_type).document_id

    def _seed_and_run(self):
        """Drive the ACTUAL seam and return (vault, report, round_id).

        A synthetic-but-realistic QUALIFIED applicant: a claimed first-language
        (CLB 9), age, education, and provincial nomination, each backed by the
        matching born-digital fixture; extracted, confirmed, and audited through
        the real full-grid entry point against the real corpus.
        """
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")

        # Claimed core factors (a real applicant's profile).
        self._claim(v, "core.language.first", "core_human_capital",
                    claimed_points=124, claimed_level="9", claimed_value=9)
        self._claim(v, "core.age", "core_human_capital",
                    claimed_points=100, claimed_value=25)
        self._claim(v, "core.education", "core_human_capital",
                    claimed_points=120, claimed_level="bachelor",
                    claimed_value="bachelor")
        self._claim(v, "additional.nomination", "additional_points",
                    claimed_points=600, claimed_value="nominated")
        # A claimed sibling-in-Canada factor (COV-04). The imported sibling_proof
        # fixture carries a FAKE ADULT DOB ("12 March 1988"), so the confirmed
        # chain proves ADULT at the ITA date and substantiates 15.
        self._claim(v, "additional.sibling", "additional_points",
                    claimed_points=15, claimed_value="sibling")

        # One document per factor — the REAL doc_types the extractor understands.
        docs = [
            self._import(v, mf.language_test_pdf(), "language_test", "lang"),
            self._import(v, mf.passport_pdf(), "passport", "passport"),
            self._import(v, mf.eca_pdf(), "eca", "eca"),
            self._import(v, mf.nomination_pdf(), "nomination", "nomination"),
            self._import(v, mf.sibling_proof_pdf(), "sibling_proof", "sibling"),
        ]

        # REAL extraction (NOT add_extracted_value). Skip on a missing dep.
        for doc_id in docs:
            try:
                extraction.extract_document(v, doc_id)
            except extraction.MissingExtractionDependency as exc:  # pragma: no cover
                self.skipTest(f"extraction deps unavailable: {exc.module}")

        # REAL confirmation seam (captures the staleness-binding keys).
        for doc_id in docs:
            for val in vault.list_extracted_values(
                    v, document_id=doc_id, status="pending"):
                vault.confirm_value(v, val.value_id, "confirm")

        rnd = vault.set_ita_round(
            v, "default", "r-seam", _ROUND_DATE, "EE", cutoff_score=470)

        report, _ = audit_report.run_full_audit_report(
            v, self.db, self.registry, ita_round_id=rnd.round_id)
        return v, report, rnd.round_id

    @staticmethod
    def _cards(report):
        return {c.factor_id: c for c in report.factor_cards}

    # -- assertions --------------------------------------------------------- #
    def test_real_extract_confirm_audit_reaches_substantiated_language(self) -> None:
        v, report, _ = self._seed_and_run()
        try:
            lang = self._cards(report)["core.language.first"]
            self.assertEqual(
                lang.verdict, "SUBSTANTIATED",
                f"language card is {lang.verdict}/{lang.reason_code} through the "
                f"real seam (BLOCKER A/B not closed)")
            # None of the three seam-defect reason codes may appear.
            for banned in ("unresolved_conversion", "unaccepted_test_type",
                           "missing_evidence"):
                self.assertNotEqual(lang.reason_code, banned)
            self.assertTrue(lang.evidence_ids)
            self.assertTrue(all(e.startswith("ev_") for e in lang.evidence_ids))
        finally:
            v.con.close()

    def test_real_seam_substantiated_total_nonzero_and_in_cutoff(self) -> None:
        v, report, _ = self._seed_and_run()
        try:
            summed = sum(c.substantiated_points or 0 for c in report.factor_cards
                         if c.verdict == "SUBSTANTIATED")
            self.assertGreater(report.substantiated_total, 0,
                               "no factor substantiated through the real seam")
            self.assertEqual(report.substantiated_total, summed)
            # The substantiated total is actually fed into the cutoff comparison.
            self.assertIsNotNone(report.cutoff_delta)
            self.assertEqual(report.cutoff_delta,
                             report.substantiated_total - 470)
            # The language card is SUBSTANTIATED and IS one of the cards folded into
            # the total. COV-01 (35-01) grounded EVERY conversion-emitted CLB band
            # (3-8, 10 added alongside the shipped CLB 9), so this fixture's
            # 8.5/7.5/7.0/8.0 IELTS abilities — which convert to CLB 10/9/9/10 — are
            # now FULLY PRICED: the no-spouse per-ability sum is 34+31+31+34 = 130.
            # The card's claimed_points is 124, so score_delta = 124 - 130 = -6, a
            # valid over-claim-safe (negative) delta. The BLOCKER A/B proof is that
            # language reaches SUBSTANTIATED through the real seam, and the fully
            # priced total flows into the cutoff comparison.
            substantiated = [c for c in report.factor_cards
                             if c.verdict == "SUBSTANTIATED"]
            lang = self._cards(report)["core.language.first"]
            self.assertIn(lang, substantiated)
            self.assertEqual(
                lang.substantiated_points, 130,
                f"language card no-spouse points {lang.substantiated_points} != 130 "
                f"(COV-01 grounds CLB 10/9/9/10 -> 34+31+31+34)")
            self.assertEqual(
                lang.score_delta, -6,
                f"language card score_delta {lang.score_delta} != -6 "
                f"(claimed 124 - substantiated 130)")
        finally:
            v.con.close()

    def test_real_seam_no_cross_factor_contamination(self) -> None:
        v, report, _ = self._seed_and_run()
        try:
            cards = self._cards(report)
            lang = cards["core.language.first"]
            self.assertEqual(lang.verdict, "SUBSTANTIATED")

            # (a) core.age must NOT be credited with the language card's evidence.
            age = cards["core.age"]
            language_evidence = set(lang.evidence_ids)
            self.assertTrue(
                language_evidence.isdisjoint(set(age.evidence_ids)),
                "core.age shares evidence with the language card (contamination)")

            # (b) Re-read the raw store: NO language raw_score_* value is linked
            #     under core.age (the exact BLOCKER-A failure mode).
            all_values = vault.list_extracted_values(v)
            language_score_factors = {
                val.factor_id for val in all_values
                if val.field_name.startswith("raw_score_")}
            self.assertNotIn("core.age", language_score_factors)
            self.assertIn("core.language.first", language_score_factors)

            # (c) The DOB (age evidence) is linked to core.age, never a language id.
            dob_factors = {val.factor_id for val in all_values
                           if val.field_name == "date_of_birth"}
            self.assertEqual(dob_factors, {"core.age"})

            # (d) Sibling evidence is claimed-scoped: the sibling card's evidence
            #     is disjoint from BOTH core.age and additional.nomination.
            sibling = cards["additional.sibling"]
            sibling_evidence = set(sibling.evidence_ids)
            nomination = cards["additional.nomination"]
            self.assertTrue(
                sibling_evidence.isdisjoint(set(age.evidence_ids)),
                "sibling shares evidence with core.age (contamination)")
            self.assertTrue(
                sibling_evidence.isdisjoint(set(nomination.evidence_ids)),
                "sibling shares evidence with additional.nomination (contamination)")

            # (e) Re-read the raw store: EVERY sibling_* value links ONLY to
            #     additional.sibling — never to core.age / additional.nomination.
            sibling_factors = {val.factor_id for val in all_values
                               if val.field_name.startswith("sibling_")}
            self.assertEqual(sibling_factors, {"additional.sibling"})

            # (f) Conversely, the DOB (age) and nomination_stream values are NEVER
            #     linked to additional.sibling (disjointness both directions).
            self.assertNotIn("additional.sibling", dob_factors)
            nomination_factors = {val.factor_id for val in all_values
                                  if val.field_name == "nomination_stream"}
            self.assertNotIn("additional.sibling", nomination_factors)
        finally:
            v.con.close()

    def test_real_seam_sibling_reaches_substantiated(self) -> None:
        v, report, _ = self._seed_and_run()
        try:
            sibling = self._cards(report)["additional.sibling"]
            self.assertEqual(
                sibling.verdict, "SUBSTANTIATED",
                f"sibling card is {sibling.verdict}/{sibling.reason_code} through "
                f"the real seam (adult chain not substantiated)")
            self.assertEqual(sibling.reason_code, "grounded_substantiated")
            self.assertEqual(sibling.substantiated_points, 15)
            self.assertTrue(sibling.evidence_ids)
            self.assertTrue(all(e.startswith("ev_") for e in sibling.evidence_ids))
        finally:
            v.con.close()

    def _run_minor_sibling_seam(self):
        """A SEPARATE minimal seam importing exactly ONE confirmed MINOR sibling.

        Reuses the accepted relationship / status / residence FAKE tokens but a
        MINOR date of birth ("15 January 2015" — a child at the ITA date), built
        in-test from the shared ``mf.build_pdf`` writer (make_fixtures is owned by
        35-03 and left untouched). Drives the REAL extract -> confirm -> audit
        path so the confirmed minor reaches the decider through the real age
        pipeline.
        """
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        self._claim(v, "additional.sibling", "additional_points",
                    claimed_points=15, claimed_value="sibling")

        # A MINOR sibling page mirroring sibling_proof_pdf()'s label lines (so the
        # real extractor yields the four sibling fields) but with a MINOR DOB. The
        # day-name-year format keeps _normalize_date unambiguous.
        page = "\n".join([
            "Proof of Relative in Canada",
            f"Relationship: {mf.FAKE_SIBLING_RELATIONSHIP}",
            f"Status: {mf.FAKE_SIBLING_STATUS}",
            f"Residence: {mf.FAKE_SIBLING_RESIDENCE}",
            "Date of Birth: 15 January 2015",
        ])
        doc_id = self._import(v, mf.build_pdf([page]), "sibling_proof", "minor")

        try:
            extraction.extract_document(v, doc_id)
        except extraction.MissingExtractionDependency as exc:  # pragma: no cover
            self.skipTest(f"extraction deps unavailable: {exc.module}")
        for val in vault.list_extracted_values(
                v, document_id=doc_id, status="pending"):
            vault.confirm_value(v, val.value_id, "confirm")

        rnd = vault.set_ita_round(
            v, "default", "r-minor", _ROUND_DATE, "EE", cutoff_score=470)
        report, _ = audit_report.run_full_audit_report(
            v, self.db, self.registry, ita_round_id=rnd.round_id)
        return v, report

    def test_real_seam_minor_sibling_stays_at_risk(self) -> None:
        # The REAL-SEAM MINOR NEGATIVE CONTROL: a confirmed minor can NEVER green
        # additional.sibling through the real extraction -> age path.
        v, report = self._run_minor_sibling_seam()
        try:
            sibling = self._cards(report)["additional.sibling"]
            self.assertEqual(
                sibling.verdict, "AT-RISK",
                f"minor sibling card is {sibling.verdict}/{sibling.reason_code} "
                f"(a confirmed minor must stay AT-RISK)")
            self.assertEqual(sibling.reason_code, "sibling_minor")
            self.assertIsNone(sibling.substantiated_points)
            self.assertNotEqual(sibling.verdict, "SUBSTANTIATED")
        finally:
            v.con.close()

    def _run_isolated_sibling_seam(self, page_lines, *, round_id):
        """Drive exactly ONE sibling_proof page through the REAL extract -> confirm
        -> audit seam against the real corpus and return (vault, sibling card).

        The label lines mirror ``sibling_proof_pdf()`` so the shipped extractor
        yields the four sibling fields; the CALLER supplies the realistically-cased
        document VALUES. This is the WR-01 proof: exercise the happy path on input a
        genuine document produces (natural casing/spacing), not on tokens engineered
        to equal the internal snake_case enum. Built in-test from the shared
        ``mf.build_pdf`` writer (make_fixtures is owned by 35-03, left untouched).
        """
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        self._claim(v, "additional.sibling", "additional_points",
                    claimed_points=15, claimed_value="sibling")
        doc_id = self._import(
            v, mf.build_pdf(["\n".join(page_lines)]), "sibling_proof", "realsib")
        try:
            extraction.extract_document(v, doc_id)
        except extraction.MissingExtractionDependency as exc:  # pragma: no cover
            self.skipTest(f"extraction deps unavailable: {exc.module}")
        for val in vault.list_extracted_values(
                v, document_id=doc_id, status="pending"):
            vault.confirm_value(v, val.value_id, "confirm")
        rnd = vault.set_ita_round(
            v, "default", round_id, _ROUND_DATE, "EE", cutoff_score=470)
        report, _ = audit_report.run_full_audit_report(
            v, self.db, self.registry, ita_round_id=rnd.round_id)
        return v, self._cards(report)["additional.sibling"]

    # Realistic document VALUES a genuine "proof of relative" prints — natural
    # casing/spacing (NOT the snake_case enum). Canonicalization (WR-01) maps them
    # onto the accepted vocabulary at extraction; without it the factor fail-closed
    # to AT-RISK unresolved_sibling for every real applicant.
    _REALISTIC_ADULT_SIBLING_PAGE = [
        "Proof of Relative in Canada",
        "Relationship: Brother",
        "Immigration Status: Permanent Resident",
        "Current Residence: Toronto, Ontario, Canada",
        "Date of Birth: 12 March 1988",
    ]

    def test_real_seam_realistic_cased_sibling_reaches_substantiated(self) -> None:
        """WR-01: the sibling happy path proven on REALISTICALLY-CASED document
        values (``Brother`` / ``Permanent Resident``) through the real
        extract -> confirm -> audit seam — not on enum-spelled fixture tokens."""
        v, sibling = self._run_isolated_sibling_seam(
            self._REALISTIC_ADULT_SIBLING_PAGE, round_id="r-real-sib")
        try:
            self.assertEqual(
                sibling.verdict, "SUBSTANTIATED",
                f"realistic-cased sibling card is {sibling.verdict}/"
                f"{sibling.reason_code} — canonicalization did not reach the "
                f"decider (a real document's values fail-closed)")
            self.assertEqual(sibling.reason_code, "grounded_substantiated")
            self.assertEqual(sibling.substantiated_points, 15)
            self.assertTrue(sibling.evidence_ids)
            self.assertTrue(all(e.startswith("ev_") for e in sibling.evidence_ids))
        finally:
            v.con.close()

    def test_real_seam_unknown_sibling_tokens_stay_at_risk(self) -> None:
        """WR-01 fail-closed control: unrecognized relationship/status surface forms
        are NEVER coerced to an accepted token — the factor stays AT-RISK
        unresolved_sibling through the real seam (no new false-green path)."""
        page = [
            "Proof of Relative in Canada",
            "Relationship: Cousin",
            "Immigration Status: Temporary Visitor",
            "Current Residence: Toronto, Ontario, Canada",
            "Date of Birth: 12 March 1988",
        ]
        v, sibling = self._run_isolated_sibling_seam(page, round_id="r-unknown-sib")
        try:
            self.assertEqual(
                sibling.verdict, "AT-RISK",
                f"unknown-token sibling card is {sibling.verdict}/"
                f"{sibling.reason_code} (a non-accepted token must stay AT-RISK)")
            self.assertEqual(sibling.reason_code, "unresolved_sibling")
            self.assertIsNone(sibling.substantiated_points)
            self.assertNotEqual(sibling.verdict, "SUBSTANTIATED")
        finally:
            v.con.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
