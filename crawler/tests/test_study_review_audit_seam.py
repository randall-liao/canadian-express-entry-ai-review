"""Real audit-spine proof for the credential-only Canadian-study seam."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import auditor, crs_rules, vault
from crawler import auditors
from crawler.models.vault import CrsProfileFactor

_REAL_DB = Path(__file__).resolve().parents[2] / "corpus" / "index.db"


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY: real corpus index is required for the real audit seam",
)
class TestStudyReviewAuditSeam(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        # ``audit_one`` is the low-level spine and intentionally does not perform
        # package registration itself.  Make this seam order-independent instead
        # of relying on another test module to have called ``load_all`` first.
        auditors.load_all()
        self.registry = crs_rules.load_registry()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _vault(self, candidate_id: str):
        v = vault.open_vault(candidate_id)
        vault.create_candidate(v, candidate_id)
        return v

    def _confirmed_value(self, v, *, factor_id: str, field_name: str,
                         value: str) -> str:
        source = Path(self._tmp.name) / f"{v.candidate_id}-{field_name}.pdf"
        source.write_bytes(b"%PDF-1.4\n% synthetic private fixture\n")
        document = vault.import_document(
            v, v.candidate_id, source, doc_type="study_proof")
        run_id = vault.record_extraction_run(
            v, document_id=document.document_id,
            parser_version=vault.current_parser_version(),
            status="complete",
        )
        value_id = vault.add_extracted_value(
            v,
            document_id=document.document_id,
            page_id=None,
            factor_id=factor_id,
            field_name=field_name,
            raw_text=value,
            normalized_value=value,
            bbox=None,
            extractor_confidence=1.0,
            quality_flag="ok",
            extraction_run_id=run_id,
        )
        vault.confirm_value(v, value_id, "confirm")
        self.assertTrue(vault.is_audit_eligible(v, value_id))
        return value_id

    def test_forced_credential_through_audit_one_never_greens(self) -> None:
        v = self._vault("forced-study")
        try:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="additional.study",
                factor_group="additional_points",
                claimed_value="3+",
                claimed_points=30,
            ))
            self._confirmed_value(
                v,
                factor_id="additional.study",
                field_name="credential_level",
                value="3+",
            )
            card = auditor.audit_one(
                v,
                "additional.study",
                _REAL_DB,
                self.registry,
                spouse_mode=False,
                reference_date="2026-07-19",
                prior_cards={},
            )
            self.assertEqual(card.verdict, "AT-RISK")
            self.assertEqual(
                card.reason_code, "credential_only_no_designation")
            self.assertIsNone(card.substantiated_points)
            self.assertNotEqual(card.verdict, "SUBSTANTIATED")
        finally:
            v.con.close()

    def test_normal_review_study_evidence_never_reaches_additional_study(self) -> None:
        v = self._vault("isolated-study")
        try:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="additional.study",
                factor_group="additional_points",
                claimed_value="3+",
                claimed_points=30,
            ))
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="review.study",
                factor_group="additional_points",
                claimed_value={},
            ))
            self._confirmed_value(
                v,
                factor_id="review.study",
                field_name="credential_level",
                value="3+",
            )
            self.assertEqual(
                vault.audit_eligible_values(v, "additional.study"), [])
            card = auditor.audit_one(
                v,
                "additional.study",
                _REAL_DB,
                self.registry,
                spouse_mode=False,
                reference_date="2026-07-19",
                prior_cards={},
            )
            self.assertEqual(card.verdict, "GAP")
            self.assertEqual(card.reason_code, "missing_evidence")
            self.assertEqual(card.evidence_ids, [])
            self.assertIsNone(card.substantiated_points)
        finally:
            v.con.close()

    def test_review_study_addition_leaves_every_non_study_card_unchanged(self) -> None:
        v = self._vault("factor-isolation")
        try:
            before = auditor.run_full_audit(
                v, _REAL_DB, self.registry, spouse_mode=False)
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="review.study",
                factor_group="additional_points",
                claimed_value={},
            ))
            self._confirmed_value(
                v,
                factor_id="review.study",
                field_name="credential_level",
                value="3+",
            )
            after = auditor.run_full_audit(
                v, _REAL_DB, self.registry, spouse_mode=False)
            before_cards = {
                card.factor_id: card.model_dump_json()
                for card in before.factor_cards
            }
            after_cards = {
                card.factor_id: card.model_dump_json()
                for card in after.factor_cards
            }
            self.assertIn("core.age", before_cards)
            self.assertEqual(before_cards, after_cards)
        finally:
            v.con.close()

    def test_dispatch_contract_remains_credential_only_and_fail_closed(self) -> None:
        self.assertEqual(
            auditors.consumed_factor_ids("additional.study"),
            ["additional.study"],
        )
        ctx = auditors.DecisionContext(
            factor_id="unwired.study",
            factor=None,
            by_field={},
            registry=self.registry,
            consumed=crs_rules.Registry(rows=[]),
            spouse_mode=False,
            reference_date="2026-07-19",
        )
        result = auditors._default_decider(ctx)
        self.assertEqual(result.verdict, "AT-RISK")
        self.assertIsNone(result.substantiated_points)
