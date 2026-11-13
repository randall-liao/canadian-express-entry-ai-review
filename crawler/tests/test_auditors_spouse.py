"""Spouse / common-law module tests (33-03, AUDIT-01/03, SC5).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Reuses the Plan 03
synthetic fixtures (``_AuditorCase`` + ``_language_registry``): a synthetic corpus
index, a synthetic registry, and a synthetic vault under ``$PR_PERSONAL_DIR``.

Proves:
  * no-spouse mode → every spouse factor is N/A ``not_applicable``;
  * spouse mode + fully-satisfying spouse-owned evidence → SUBSTANTIATED with
    spouse-table points (language section cap enforced);
  * ownership separation (SC5) — a principal-owned language value with the spouse
    factor claimed but NO spouse-owned value → ``spouse.language`` GAP, never green;
  * below-threshold spouse language → GAP;
  * ``determine_spouse_mode`` reads the explicit signal, not stray evidence;
  * the module trips no inlined-threshold violation.
"""

from __future__ import annotations

from pathlib import Path

from crawler import auditor, crs_rules, vault
from crawler.auditors import spouse as spouse_mod
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    PointsEntry,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor
from crawler.tests.test_auditor import (
    _TINY_ID,
    _TINY_QUOTE,
    _ABILITY_FIELD,
    _AuditorCase,
    _language_registry,
)


def _srow(rule_id, factor_id, mc, check_type="points"):
    return RuleRow(
        rule_id=rule_id, factor_group="spouse_common_law", factor_ids=[factor_id],
        check_type=check_type, query="police certificates",
        selector=Selector(family="pr-pdi", marker=_TINY_QUOTE),
        claim_text="A grounded spouse rule.",
        citations=[Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
        machine_check=mc,
        volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi"))


def _spouse_registry() -> Registry:
    rows = list(_language_registry().rows)
    rows += [
        _srow("spouse.education", "spouse.education",
              MachineCheck(kind="points_table", field="spouse_education_level",
                           points_by_level=[PointsEntry(
                               label="doctoral_with_spouse", level="doctoral",
                               points=10)])),
        _srow("spouse.language.points", "spouse.language",
              MachineCheck(kind="points_table", field="clb_per_ability",
                           points_by_level=[PointsEntry(
                               label="clb9_with_spouse", level=9, points=5)])),
        _srow("spouse.language.cap", "spouse.language",
              MachineCheck(kind="cap", field="spouse_language_section",
                           cap_value=20), check_type="cap"),
        _srow("spouse.work.teer", "spouse.work",
              MachineCheck(kind="accepted_enum", field="teer",
                           accepted_values=[]), check_type="admissibility"),
        _srow("spouse.work.hours", "spouse.work",
              MachineCheck(kind="threshold", field="hours_per_week", max_value=30),
              check_type="threshold"),
        _srow("spouse.work.window", "spouse.work",
              MachineCheck(kind="validity_window", field="work_reference_period",
                           window_days=3653), check_type="threshold"),
    ]
    # accepted teer values (rebuild the row with real accepted values)
    from crawler.models.crs_rules import AcceptedValue
    rows = [r for r in rows if r.rule_id != "spouse.work.teer"]
    rows.append(_srow("spouse.work.teer", "spouse.work",
                      MachineCheck(kind="accepted_enum", field="teer",
                                   accepted_values=[AcceptedValue(value=v)
                                                    for v in ("0", "1", "2", "3")]),
                      check_type="admissibility"))
    return Registry(rows=rows)


class _SpouseCase(_AuditorCase):
    def _seed(self, *, accompanying, claim_spouse=(), spouse_lang=None,
              spouse_edu=None, principal_lang=None):
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        if accompanying:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="spouse.accompanying", factor_group="spouse_common_law",
                claimed_value=True, source="user_entry"))
        for fid, claim in claim_spouse:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id=fid, factor_group="spouse_common_law",
                claimed_points=10, claimed_level=claim, claimed_value=claim,
                source="user_entry"))
        run = None
        if spouse_lang is not None:
            self._seed_language(v, spouse_lang, factor_id="spouse.language")
        if principal_lang is not None:
            # The principal must claim core.language.first for the FK to hold; the
            # value is principal-OWNED (linked to core.language.first), which a
            # spouse decider must never see.
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="core.language.first", factor_group="core_human_capital",
                claimed_level="9", claimed_value=9, source="user_entry"))
            self._seed_language(v, principal_lang, factor_id="core.language.first")
        if spouse_edu is not None:
            self._seed_field(v, "credential_level", spouse_edu,
                             factor_id="spouse.education",
                             doc_type="educational_credential_assessment")
        return v

    def _seed_field(self, v, field, value, *, factor_id, doc_type):
        src = Path(self._tmp.name) / f"{factor_id}_{field}.pdf"
        src.write_bytes(b"%PDF-1.4 synthetic " + field.encode())
        doc = vault.import_document(v, "default", src, doc_type=doc_type)
        run = vault.record_extraction_run(
            v, document_id=doc.document_id,
            parser_version=vault.current_parser_version())
        vid = vault.add_extracted_value(
            v, document_id=doc.document_id, page_id=None, factor_id=factor_id,
            field_name=field, raw_text=str(value), normalized_value=value,
            bbox=None, extractor_confidence=0.9, quality_flag="ok",
            extraction_run_id=run)
        vault.confirm_value(
            v,
            vid,
            "confirm",
            registry_fingerprint=crs_rules.registry_fingerprint(
                _spouse_registry()),
        )

    def _seed_language(self, v, score, *, factor_id):
        from datetime import date, timedelta
        src = Path(self._tmp.name) / f"{factor_id}_lang.pdf"
        src.write_bytes(b"%PDF-1.4 synthetic lang " + factor_id.encode())
        doc = vault.import_document(v, "default", src, doc_type="language_test")
        run = vault.record_extraction_run(
            v, document_id=doc.document_id,
            parser_version=vault.current_parser_version())
        fields = {"test_type": "IELTS General Training",
                  "test_date": (date.today() - timedelta(days=30)).isoformat()}
        for ability, field in _ABILITY_FIELD.items():
            fields[field] = score
        for field, value in fields.items():
            vid = vault.add_extracted_value(
                v, document_id=doc.document_id, page_id=None, factor_id=factor_id,
                field_name=field, raw_text=str(value), normalized_value=value,
                bbox=None, extractor_confidence=0.9, quality_flag="ok",
                extraction_run_id=run)
            vault.confirm_value(
                v,
                vid,
                "confirm",
                registry_fingerprint=crs_rules.registry_fingerprint(
                    _spouse_registry()),
            )

    def _audit(self, v, factor_id, *, spouse_mode):
        from datetime import date
        return auditor.audit_one(
            v, factor_id, self.db, _spouse_registry(),
            spouse_mode=spouse_mode, reference_date=date.today().isoformat(),
            prior_cards={})


class TestSpouseMode(_SpouseCase):
    def test_determine_spouse_mode_reads_explicit_signal(self) -> None:
        v = self._seed(accompanying=True)
        try:
            factors = vault.load_profile_factors(v)
            self.assertTrue(spouse_mod.determine_spouse_mode(v, factors))
        finally:
            v.con.close()

    def test_no_signal_is_no_spouse_mode(self) -> None:
        v = self._seed(accompanying=False,
                       spouse_lang=7.5, claim_spouse=[("spouse.language", "9")])
        try:
            # Stray spouse EVIDENCE must NOT flip the mode.
            factors = vault.load_profile_factors(v)
            self.assertFalse(spouse_mod.determine_spouse_mode(v, factors))
        finally:
            v.con.close()

    def test_no_spouse_mode_all_spouse_factors_na(self) -> None:
        v = self._seed(accompanying=False)
        try:
            for fid in ("spouse.education", "spouse.language", "spouse.work"):
                card = self._audit(v, fid, spouse_mode=False)
                self.assertEqual(card.verdict, "N/A")
                self.assertEqual(card.reason_code, "not_applicable")
        finally:
            v.con.close()


class TestSpouseSubstantiation(_SpouseCase):
    def test_spouse_language_substantiated_capped(self) -> None:
        v = self._seed(accompanying=True, spouse_lang=7.5,
                       claim_spouse=[("spouse.language", "9")])
        try:
            card = self._audit(v, "spouse.language", spouse_mode=True)
        finally:
            v.con.close()
        self.assertEqual(card.verdict, "SUBSTANTIATED")
        # 4 abilities x 5 = 20, clamped at the grounded section cap of 20.
        self.assertEqual(card.substantiated_points, 20)

    def test_spouse_education_substantiated(self) -> None:
        v = self._seed(accompanying=True, spouse_edu="doctoral",
                       claim_spouse=[("spouse.education", "doctoral")])
        try:
            card = self._audit(v, "spouse.education", spouse_mode=True)
        finally:
            v.con.close()
        self.assertEqual(card.verdict, "SUBSTANTIATED")
        self.assertEqual(card.substantiated_points, 10)

    def test_below_threshold_spouse_language_is_gap(self) -> None:
        # Claim CLB 10 but score maps to CLB 9 -> below threshold -> GAP.
        v = self._seed(accompanying=True, spouse_lang=7.5,
                       claim_spouse=[("spouse.language", "10")])
        try:
            card = self._audit(v, "spouse.language", spouse_mode=True)
        finally:
            v.con.close()
        self.assertEqual(card.verdict, "GAP")
        self.assertEqual(card.reason_code, "below_threshold")


class TestOwnershipSeparation(_SpouseCase):
    def test_principal_owned_value_cannot_substantiate_spouse(self) -> None:
        # A principal-owned language value + a claimed spouse.language factor, but
        # NO spouse-owned value -> spouse.language GAP missing_evidence (SC5).
        v = self._seed(accompanying=True, principal_lang=7.5,
                       claim_spouse=[("spouse.language", "9")])
        try:
            card = self._audit(v, "spouse.language", spouse_mode=True)
        finally:
            v.con.close()
        self.assertEqual(card.verdict, "GAP")
        self.assertEqual(card.reason_code, "missing_evidence")
        self.assertNotEqual(card.verdict, "SUBSTANTIATED")


class TestNoInlinedRules(_SpouseCase):
    def test_spouse_module_has_no_inlined_volatile_rules(self) -> None:
        from crawler import crs_rules
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([spouse_mod.__file__]), [])


if __name__ == "__main__":  # pragma: no cover
    import unittest
    unittest.main()
