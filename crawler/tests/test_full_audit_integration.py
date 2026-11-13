"""Full-grid integration tests (33-06 Task 1, SC1/SC3/SC4/SC5 + language-green).

Stdlib ``unittest`` ONLY — NO network. A SYNTHETIC vault (tmp ``$PR_PERSONAL_DIR``)
seeded with a full claimed profile + an ITA round, audited through the REAL
grounded registry against the REAL ``corpus/index.db`` (so the conversion rows
ground and language can reach SUBSTANTIATED end-to-end). SKIPPED on a fresh clone
where the git-ignored corpus is absent.

Proves the whole phase goal:
  * SC1 — exactly one verdict per grid factor (no missing, no duplicate);
  * SC3/AUDIT-04 — a SUBSTANTIATED card carries all six fields;
  * SC4/AUDIT-05 — substantiated total vs cutoff, no legal-advice wording;
  * SC5 — multi-document work aggregation (no overlap double-count), spouse/
    principal ownership, and transferability dependency all surface as factor-
    level GAP/AT-RISK;
  * language SUBSTANTIATED reachable end-to-end (Phase-32 known item closed).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from crawler import audit_report, auditors, crs_rules, vault
from crawler.models.vault import CrsProfileFactor

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"

# Distinctive synthetic applicant-value sentinels (recognizable in PII checks).
_SENTINEL_STREAM = "SYNTHETIC-OINP-STREAM-ZZZ"


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY: corpus/index.db is git-ignored and absent — the full-grid "
    "grounding + language-green proof did NOT run; a green suite here is "
    "STRUCTURAL ONLY",
)
class _IntegrationCase(unittest.TestCase):
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

    # -- seeding helpers ---------------------------------------------------- #
    def _open(self):
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        return v

    def _claim(self, v, factor_id, group, **kw):
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id=factor_id, factor_group=group, **kw))

    def _doc(self, v, doc_type, factor_id, fields):
        src = Path(self._tmp.name) / f"{factor_id.replace('.', '_')}_{len(fields)}_{doc_type}.pdf"
        src.write_bytes(b"%PDF-1.4 synthetic " + os.urandom(6))
        doc = vault.import_document(v, "default", src, doc_type=doc_type)
        run = vault.record_extraction_run(
            v, document_id=doc.document_id,
            parser_version=vault.current_parser_version())
        for field, value in fields.items():
            vid = vault.add_extracted_value(
                v, document_id=doc.document_id, page_id=None, factor_id=factor_id,
                field_name=field, raw_text=str(value), normalized_value=value,
                bbox=None, extractor_confidence=0.9, quality_flag="ok",
                extraction_run_id=run)
            vault.confirm_value(v, vid, "confirm")

    def _seed_happy(self):
        """A full profile: age + education + green language + below-claim work +
        verified nomination + an ITA round."""
        v = self._open()
        today = date.today()
        self._claim(v, "core.age", "core_human_capital",
                    claimed_points=110, claimed_value=25)
        self._claim(v, "core.education", "core_human_capital",
                    claimed_points=30, claimed_level="secondary",
                    claimed_value="secondary")
        self._claim(v, "core.language.first", "core_human_capital",
                    claimed_points=124, claimed_level="9", claimed_value=9)
        self._claim(v, "core.work", "core_human_capital",
                    claimed_points=40, claimed_value=3.0)
        self._claim(v, "additional.nomination", "additional_points",
                    claimed_points=600, claimed_value="nominated")

        self._doc(v, "passport", "core.age",
                  {"date_of_birth": date(today.year - 25, 1, 1).isoformat()})
        self._doc(v, "educational_credential_assessment", "core.education",
                  {"credential_level": "secondary"})
        # IELTS all four abilities -> CLB 9 (grounded conversion).
        self._doc(v, "language_test", "core.language.first", {
            "test_type": "IELTS General Training",
            "test_date": (today - timedelta(days=30)).isoformat(),
            "raw_score_reading": 7.0, "raw_score_writing": 7.0,
            "raw_score_listening": 8.0, "raw_score_speaking": 7.0})
        # Two OVERLAPPING full-time letters: union ~2y < claimed 3y (SC5 i + iii).
        self._doc(v, "employment_reference_letter", "core.work", {
            "employment_start": "2020-01-01", "employment_end": "2021-06-30",
            "hours_per_week": 40, "teer": "1"})
        self._doc(v, "employment_reference_letter", "core.work", {
            "employment_start": "2020-06-01", "employment_end": "2021-12-31",
            "hours_per_week": 40, "teer": "1"})
        self._doc(v, "provincial_nomination", "additional.nomination", {
            "nomination_stream": _SENTINEL_STREAM, "expiry_date": "2099-01-01"})
        rnd = vault.set_ita_round(
            v, "default", "r", today.isoformat(), "EE", cutoff_score=500)
        return v, rnd.round_id

    def _cards(self, report):
        return {c.factor_id: c for c in report.factor_cards}


class TestFullGridIntegration(_IntegrationCase):
    def test_sc1_one_verdict_per_factor(self) -> None:
        v, round_id = self._seed_happy()
        try:
            report, envelope = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        ids = [c.factor_id for c in report.factor_cards]
        self.assertEqual(sorted(ids), sorted(auditors.FULL_GRID_FACTORS))
        self.assertEqual(len(ids), len(set(ids)))
        vocab = {"SUBSTANTIATED", "GAP", "AT-RISK", "N/A"}
        for card in report.factor_cards:
            self.assertIn(card.verdict, vocab)
        # The public envelope mirrors one verdict per factor.
        self.assertEqual(
            sorted(fv.factor_id for fv in envelope.verdicts),
            sorted(auditors.FULL_GRID_FACTORS))

    def test_language_green_end_to_end(self) -> None:
        v, round_id = self._seed_happy()
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        lang = self._cards(report)["core.language.first"]
        self.assertEqual(lang.verdict, "SUBSTANTIATED")
        self.assertNotEqual(lang.reason_code, "unresolved_conversion")

    def test_audit04_substantiated_card_has_all_six_fields(self) -> None:
        v, round_id = self._seed_happy()
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        lang = self._cards(report)["core.language.first"]
        self.assertEqual(lang.verdict, "SUBSTANTIATED")
        self.assertIsNotNone(lang.claimed_value)
        self.assertIsNotNone(lang.confirmed_value)
        self.assertIsNotNone(lang.substantiated_points)
        self.assertIsNotNone(lang.score_delta)
        self.assertTrue(lang.evidence_ids)
        self.assertTrue(all(e.startswith("ev_") for e in lang.evidence_ids))
        self.assertTrue(lang.rule_citation_ids)
        self.assertTrue(all("#" in c for c in lang.rule_citation_ids))

    def test_sc4_cutoff_and_no_legal_advice(self) -> None:
        v, round_id = self._seed_happy()
        try:
            report, envelope = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
            run_id = envelope.run_id
            md = (v.root / "output" / "crs-audit" / f"{run_id}.md").read_text(
                encoding="utf-8")
        finally:
            v.con.close()
        summed = sum(c.substantiated_points or 0 for c in report.factor_cards
                     if c.verdict == "SUBSTANTIATED")
        self.assertEqual(report.substantiated_total, summed)
        self.assertEqual(report.cutoff_delta, summed - 500)
        self.assertEqual(report.meets_cutoff, summed >= 500)
        self.assertIn("Substantiated total", md)
        self.assertIn("Cutoff comparison", md)
        lowered = md.lower()
        # The SAFE-04 screening notice carries the NEGATED disclaimer ("not legal
        # advice" / "not a substitute"); normalize it out before scanning for a
        # bare legal-advice / eligibility CLAIM.
        normalized = (lowered.replace("not legal advice", "")
                      .replace("not a substitute", ""))
        for banned in ("you are eligible", "legal advice", "guaranteed",
                       "you qualify", "you will be invited"):
            self.assertNotIn(banned, normalized)
        # The screening framing IS present (SAFE-04).
        self.assertIn("not legal advice", lowered)

    def test_sc5_work_aggregation_gap_no_double_count(self) -> None:
        v, round_id = self._seed_happy()
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        work = self._cards(report)["core.work"]
        self.assertEqual(work.verdict, "GAP")
        # The union (~2y), not the naive sum (~3.08y), so it stays below claim.
        self.assertLess(work.confirmed_value["aggregated_years"], 2.5)

    def test_sc5_transferability_dependency_surfaces(self) -> None:
        v, round_id = self._seed_happy()
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        # education x work depends on core.work, which is GAP -> unmet component.
        combo = self._cards(report)["transfer.education_work"]
        self.assertIn(combo.verdict, {"GAP", "AT-RISK"})
        self.assertEqual(combo.reason_code, "unmet_component")


class TestSpouseOwnershipIntegration(_IntegrationCase):
    def _seed_spouse_ownership(self):
        v = self._open()
        today = date.today()
        self._claim(v, "spouse.accompanying", "spouse_common_law",
                    claimed_value=True)
        self._claim(v, "spouse.language", "spouse_common_law",
                    claimed_points=20, claimed_level="9", claimed_value=9)
        self._claim(v, "core.language.first", "core_human_capital",
                    claimed_points=124, claimed_level="9", claimed_value=9)
        # PRINCIPAL-owned language evidence only (linked to core.language.first).
        self._doc(v, "language_test", "core.language.first", {
            "test_type": "IELTS General Training",
            "test_date": (today - timedelta(days=30)).isoformat(),
            "raw_score_reading": 7.0, "raw_score_writing": 7.0,
            "raw_score_listening": 8.0, "raw_score_speaking": 7.0})
        rnd = vault.set_ita_round(
            v, "default", "r", today.isoformat(), "EE", cutoff_score=500)
        return v, rnd.round_id

    def test_spouse_factor_with_only_principal_evidence_is_gap(self) -> None:
        v, round_id = self._seed_spouse_ownership()
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        cards = {c.factor_id: c for c in report.factor_cards}
        spouse_lang = cards["spouse.language"]
        # Spouse mode is ON (explicit signal), but no spouse-owned value exists ->
        # ownership separation surfaces as a factor-level GAP, never SUBSTANTIATED.
        self.assertEqual(spouse_lang.verdict, "GAP")
        self.assertNotEqual(spouse_lang.verdict, "SUBSTANTIATED")


class TestSpouseModeLanguagePoints(_IntegrationCase):
    """SC3/AUDIT-04 + SC4/AUDIT-05: in spouse mode the core language cards carry
    their grounded with-spouse points and the substantiated total includes them;
    the no-spouse path is unchanged (33-07 gap closure)."""

    def _seed_spouse_language(self):
        v = self._open()
        today = date.today()
        # Explicit accompanying-spouse signal turns spouse mode ON.
        self._claim(v, "spouse.accompanying", "spouse_common_law",
                    claimed_value=True)
        self._claim(v, "core.language.first", "core_human_capital",
                    claimed_points=124, claimed_level="9", claimed_value=9)
        # Principal IELTS evidence: reading/writing/speaking 7.0 + listening 8.0
        # ground all four abilities to CLB 9.
        self._doc(v, "language_test", "core.language.first", {
            "test_type": "IELTS General Training",
            "test_date": (today - timedelta(days=30)).isoformat(),
            "raw_score_reading": 7.0, "raw_score_writing": 7.0,
            "raw_score_listening": 8.0, "raw_score_speaking": 7.0})
        rnd = vault.set_ita_round(
            v, "default", "r", today.isoformat(), "EE", cutoff_score=500)
        return v, rnd.round_id

    def test_spouse_mode_core_language_card_carries_with_spouse_points(self) -> None:
        v, round_id = self._seed_spouse_language()
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        lang = self._cards(report)["core.language.first"]
        self.assertEqual(lang.verdict, "SUBSTANTIATED")
        # 4 abilities x grounded clb9_with_spouse (29) = 116 (never 0/blank).
        self.assertIsNotNone(lang.substantiated_points)
        self.assertIsNotNone(lang.score_delta)
        self.assertEqual(lang.substantiated_points, 116)
        self.assertEqual(lang.score_delta, 8)  # claimed 124 - substantiated 116
        self.assertTrue(lang.evidence_ids)
        self.assertTrue(all(e.startswith("ev_") for e in lang.evidence_ids))

    def test_spouse_mode_substantiated_total_includes_language(self) -> None:
        v, round_id = self._seed_spouse_language()
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        lang = self._cards(report)["core.language.first"]
        self.assertEqual(lang.verdict, "SUBSTANTIATED")
        self.assertEqual(lang.substantiated_points, 116)
        summed = sum(c.substantiated_points or 0 for c in report.factor_cards
                     if c.verdict == "SUBSTANTIATED")
        self.assertEqual(report.substantiated_total, summed)
        # The with-spouse language points ARE in the total (NOT undercounted to 0).
        substantiated = [c for c in report.factor_cards
                         if c.verdict == "SUBSTANTIATED"]
        self.assertIn(lang, substantiated)
        self.assertGreaterEqual(report.substantiated_total, 116)

    def test_no_spouse_mode_language_points_unchanged(self) -> None:
        v, round_id = self._seed_happy()
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        lang = self._cards(report)["core.language.first"]
        self.assertEqual(lang.verdict, "SUBSTANTIATED")
        # 4 abilities x grounded clb9_without_spouse (31) = 124; claim 124 -> delta 0.
        self.assertEqual(lang.substantiated_points, 124)
        self.assertEqual(lang.score_delta, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
