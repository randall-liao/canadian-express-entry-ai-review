"""Verdict-matrix tests for the fail-closed first-official-language engine (32-03, AUDIT-02).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Every case is driven
over a SYNTHETIC corpus index (``test_searchindex._make_index_corpus`` +
``searchindex.build_index``), a SYNTHETIC registry whose rows cite the synthetic
tiny chunk verbatim, and a SYNTHETIC vault (tempdir + ``$PR_PERSONAL_DIR``) seeded
with extracted values at chosen confirmation / quality / staleness states. NO real
corpus, NO real applicant data.

The matrix proves the SC2/SC3 "never green" contract and the SC1/SC5 grounding
gate:
  * happy path → SUBSTANTIATED;
  * pending / low_quality / stale / missing evidence → GAP (never green);
  * below-threshold / wrong-test-type → GAP;
  * expired test / semantically-unresolved conversion → AT-RISK;
  * not-claimed → N/A;
  * an ungrounded (or gap:true) consumed rule → AuditGroundingError, no report;
  * a grounded GAP/AT-RISK is a RESULT (a valid report), not an exception.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_auditor.py -q
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from crawler import auditor, crs_rules, searchindex, vault
from crawler.models.crs_rules import (
    AcceptedValue,
    Citation,
    MachineCheck,
    PointsEntry,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor
from crawler.tests.test_searchindex import _make_index_corpus

_TINY_ID = "pr-pdi/tiny.md#000"
_TINY_QUOTE = "Permanent residence applicants must provide police certificates"

_ABILITIES = ("listening", "reading", "writing", "speaking")
_ABILITY_FIELD = {a: f"raw_score_{a}" for a in _ABILITIES}


def _cite(quote: str = _TINY_QUOTE) -> list[Citation]:
    return [Citation(chunk_id=_TINY_ID, quote=quote)]


def _lang_row(rule_id: str, check_type: str, mc: MachineCheck, *,
              factor_ids=None, quote: str = _TINY_QUOTE, gap: bool = False) -> RuleRow:
    return RuleRow(
        rule_id=rule_id,
        factor_group="core_human_capital",
        factor_ids=factor_ids or ["core.language.first"],
        check_type=check_type,
        query="police certificates",
        selector=Selector(family="pr-pdi", marker=quote),
        claim_text="A grounded first-official-language rule.",
        citations=_cite(quote),
        machine_check=mc,
        volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi"),
        gap=gap,
        gap_reason="synthetic coverage gap" if gap else None,
    )


def _conversion_entries() -> list[PointsEntry]:
    entries: list[PointsEntry] = []
    for ability in _ABILITIES:
        # Upper band: raw in [7.0, 9.0] -> the higher benchmark.
        entries.append(PointsEntry(
            test_type="IELTS General Training", ability=ability,
            level=9, min_score=7.0, max_score=9.0, citation_index=0))
        # Lower band: raw in [6.0, 6.9] -> one benchmark down.
        entries.append(PointsEntry(
            test_type="IELTS General Training", ability=ability,
            level=8, min_score=6.0, max_score=6.9, citation_index=0))
    return entries


def _language_registry(*, points_quote: str = _TINY_QUOTE,
                       extra_gap_row: bool = False) -> Registry:
    """A fully-grounded synthetic first-language + conversion registry."""
    rows = [
        _lang_row(
            "core.language.first.accepted_tests", "admissibility",
            MachineCheck(kind="accepted_enum", field="test_type",
                         accepted_values=[
                             AcceptedValue(value="IELTS General Training"),
                             AcceptedValue(value="CELPIP-General"),
                         ])),
        _lang_row(
            "core.language.first.validity", "threshold",
            MachineCheck(kind="validity_window", field="test_date",
                         window_days=730)),
        _lang_row(
            "core.language.first.points", "points",
            MachineCheck(kind="points_table", field="clb_per_ability",
                         points_by_level=[
                             PointsEntry(level=9, points=29),
                             PointsEntry(level=8, points=23),
                             PointsEntry(level=7, points=17),
                         ]),
            quote=points_quote),
        _lang_row(
            "core.language.conversion.ielts", "conversion",
            MachineCheck(kind="conversion", field="clb",
                         points_by_level=_conversion_entries()),
            factor_ids=["core.language.conversion"]),
    ]
    if extra_gap_row:
        rows.append(_lang_row(
            "core.language.first.gap", "admissibility",
            MachineCheck(kind="policy_flag", field="approved_test_required",
                         flag_value=True),
            gap=True))
    return Registry(rows=rows)


class _AuditorCase(unittest.TestCase):
    """Fresh synthetic index + tmp vault per test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.root = _make_index_corpus(Path(self._tmp.name))
        self.db = Path(self._tmp.name) / "index.db"
        searchindex.build_index(self.root, self.db)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    # -- vault seeding ------------------------------------------------------ #
    def _seed_vault(self, raw_scores: dict, *, test_type="IELTS General Training",
                    test_date=None, missing=(), pending=(), low_quality=(),
                    stale=False, with_factor=True,
                    registry_fingerprint=None):
        if test_date is None:
            test_date = (date.today() - timedelta(days=30)).isoformat()
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        if with_factor:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="core.language.first",
                factor_group="core_human_capital",
                claimed_points=116, claimed_level="9", claimed_value=9,
                source="user_entry"))
        src = Path(self._tmp.name) / "lang.pdf"
        src.write_bytes(b"%PDF-1.4 synthetic language test")
        doc = vault.import_document(v, "default", src, doc_type="language_test")
        run_id = vault.record_extraction_run(
            v, document_id=doc.document_id,
            parser_version=vault.current_parser_version())
        fields: dict = {"test_type": test_type, "test_date": test_date}
        for ability, field in _ABILITY_FIELD.items():
            fields[field] = raw_scores.get(ability)
        # When the factor is not claimed, evidence stays unlinked (factor_id=None)
        # so the crs_profile_factors FK is satisfied (N/A short-circuits anyway).
        value_factor_id = "core.language.first" if with_factor else None
        for field, value in fields.items():
            if field in missing or value is None:
                continue
            quality = "low_quality" if field in low_quality else "ok"
            value_id = vault.add_extracted_value(
                v, document_id=doc.document_id, page_id=None,
                factor_id=value_factor_id, field_name=field,
                raw_text=str(value), normalized_value=value, bbox=None,
                extractor_confidence=0.9, quality_flag=quality,
                extraction_run_id=run_id)
            if field in pending:
                continue  # left pending -> not eligible
            vault.confirm_value(
                v,
                value_id,
                "confirm",
                registry_fingerprint=(
                    registry_fingerprint
                    if registry_fingerprint is not None
                    else crs_rules.registry_fingerprint(_language_registry())
                ),
            )
        if stale:
            # Invalidate every confirmation's rule-registry binding key.
            v.con.execute(
                "UPDATE extracted_values "
                "SET confirmed_rule_registry_version = 'obsolete' "
                "WHERE confirmation_status IN ('confirmed', 'corrected')")
            v.con.commit()
        return v

    def _all(self, score: float) -> dict:
        return {a: score for a in _ABILITIES}


class TestSubstantiated(_AuditorCase):
    def test_happy_path_is_substantiated(self) -> None:
        v = self._seed_vault(self._all(7.5))
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, _language_registry())
        finally:
            v.con.close()
        card = report.factor_cards[0]
        self.assertEqual(card.verdict, "SUBSTANTIATED")
        self.assertEqual(card.substantiated_points, 116)
        self.assertEqual(card.score_delta, 0)
        self.assertTrue(card.evidence_ids)
        self.assertTrue(all(e.startswith("ev_") for e in card.evidence_ids))
        self.assertIn(_TINY_ID, card.rule_citation_ids)
        self.assertEqual(report.substantiated_total, 116)


class TestRegistrySnapshotBinding(_AuditorCase):
    def test_direct_audit_uses_supplied_registry_fingerprint_once(self) -> None:
        registry = _language_registry()
        expected = crs_rules.registry_fingerprint(registry)
        v = self._seed_vault(
            self._all(7.5), registry_fingerprint=expected)
        try:
            with (
                mock.patch(
                    "crawler.crs_rules.registry_fingerprint",
                    wraps=crs_rules.registry_fingerprint,
                ) as fingerprint,
                mock.patch(
                    "crawler.vault.live_registry_fingerprint",
                    side_effect=AssertionError("live registry fallback"),
                ),
            ):
                report = auditor.audit_factor(
                    v, "core.language.first", self.db, registry)
        finally:
            v.con.close()
        self.assertEqual(fingerprint.call_count, 1)
        self.assertEqual(report.registry_fingerprint, expected)
        self.assertEqual(
            report.factor_cards[0].verdict, "SUBSTANTIATED")

    def test_explicit_fingerprint_mismatch_fails_before_evidence_read(self) -> None:
        registry = _language_registry()
        v = self._seed_vault(self._all(7.5))
        try:
            with mock.patch(
                    "crawler.vault.audit_eligible_values") as eligible:
                with self.assertRaisesRegex(
                        auditor.AuditGroundingError,
                        "^supplied registry fingerprint does not match registry$"):
                    auditor.audit_factor(
                        v,
                        "core.language.first",
                        self.db,
                        registry,
                        registry_fingerprint="0" * 64,
                    )
            eligible.assert_not_called()
        finally:
            v.con.close()

    def test_evidence_bound_to_registry_a_is_excluded_under_registry_b(self) -> None:
        registry_a = _language_registry()
        fingerprint_a = crs_rules.registry_fingerprint(registry_a)
        v = self._seed_vault(
            self._all(7.5), registry_fingerprint=fingerprint_a)
        registry_b = registry_a.model_copy(deep=True)
        registry_b.rows[0].claim_text = "Changed, still-grounded synthetic rule."
        self.assertNotEqual(
            fingerprint_a, crs_rules.registry_fingerprint(registry_b))
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, registry_b)
        finally:
            v.con.close()
        self.assertEqual(report.factor_cards[0].verdict, "GAP")
        self.assertEqual(
            report.factor_cards[0].reason_code, "missing_evidence")
        self.assertNotEqual(
            report.factor_cards[0].verdict, "SUBSTANTIATED")


class TestNeverGreen(_AuditorCase):
    def _verdict(self, **kw) -> str:
        v = self._seed_vault(**kw)
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, _language_registry())
        finally:
            v.con.close()
        return report.factor_cards[0].verdict

    def test_pending_evidence_is_gap(self) -> None:
        self.assertEqual(
            self._verdict(raw_scores=self._all(7.5),
                          pending=("raw_score_reading",)), "GAP")

    def test_low_quality_is_not_green(self) -> None:
        verdict = self._verdict(raw_scores=self._all(7.5),
                                low_quality=("raw_score_reading",))
        self.assertIn(verdict, ("GAP", "AT-RISK"))
        self.assertNotEqual(verdict, "SUBSTANTIATED")

    def test_stale_is_not_green(self) -> None:
        verdict = self._verdict(raw_scores=self._all(7.5), stale=True)
        self.assertIn(verdict, ("GAP", "AT-RISK"))
        self.assertNotEqual(verdict, "SUBSTANTIATED")

    def test_missing_proof_is_gap(self) -> None:
        self.assertEqual(
            self._verdict(raw_scores=self._all(7.5),
                          missing=("raw_score_speaking",)), "GAP")

    def test_below_threshold_is_gap(self) -> None:
        v = self._seed_vault(self._all(6.5))
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, _language_registry())
        finally:
            v.con.close()
        card = report.factor_cards[0]
        self.assertEqual(card.verdict, "GAP")
        # Recalculated downward: 4 abilities at the lower benchmark.
        self.assertEqual(card.substantiated_points, 92)

    def test_wrong_test_type_is_gap(self) -> None:
        self.assertEqual(
            self._verdict(raw_scores=self._all(7.5), test_type="TOEFL"), "GAP")


class TestAtRisk(_AuditorCase):
    def test_expired_test_is_at_risk(self) -> None:
        old = (date.today() - timedelta(days=900)).isoformat()
        v = self._seed_vault(self._all(7.5), test_date=old)
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, _language_registry())
        finally:
            v.con.close()
        self.assertEqual(report.factor_cards[0].verdict, "AT-RISK")

    def test_unresolved_conversion_is_at_risk(self) -> None:
        scores = self._all(7.5)
        scores["reading"] = 3.0  # out of every grounded band -> to_clb None
        v = self._seed_vault(scores)
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, _language_registry())
        finally:
            v.con.close()
        self.assertEqual(report.factor_cards[0].verdict, "AT-RISK")

    def test_grounded_at_risk_is_a_result_not_error(self) -> None:
        old = (date.today() - timedelta(days=900)).isoformat()
        v = self._seed_vault(self._all(7.5), test_date=old)
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, _language_registry())
        finally:
            v.con.close()
        # A valid PrivateAuditReport was returned (no exception).
        self.assertEqual(len(report.factor_cards), 1)


class TestNotApplicable(_AuditorCase):
    def test_not_claimed_is_na(self) -> None:
        v = self._seed_vault(self._all(7.5), with_factor=False)
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, _language_registry())
        finally:
            v.con.close()
        card = report.factor_cards[0]
        self.assertEqual(card.verdict, "N/A")
        self.assertEqual(card.reason_code, "not_claimed")


class TestGroundingGate(_AuditorCase):
    def test_ungrounded_rule_raises_and_writes_no_report(self) -> None:
        bad = _language_registry(points_quote="this span is absolutely not present zzz")
        v = self._seed_vault(self._all(7.5))
        try:
            with self.assertRaises(auditor.AuditGroundingError):
                auditor.audit_factor(v, "core.language.first", self.db, bad)
        finally:
            v.con.close()

    def test_consumed_gap_row_raises(self) -> None:
        reg = _language_registry(extra_gap_row=True)
        v = self._seed_vault(self._all(7.5))
        try:
            with self.assertRaises(auditor.AuditGroundingError):
                auditor.audit_factor(v, "core.language.first", self.db, reg)
        finally:
            v.con.close()

    def test_grounded_gap_verdict_returns_report_no_raise(self) -> None:
        # A below-threshold (grounded) run is a RESULT, never a grounding error.
        v = self._seed_vault(self._all(6.5))
        try:
            report = auditor.audit_factor(
                v, "core.language.first", self.db, _language_registry())
        finally:
            v.con.close()
        self.assertEqual(report.factor_cards[0].verdict, "GAP")


class TestStaticGateAndReuse(unittest.TestCase):
    def test_no_inlined_volatile_rules_in_auditor(self) -> None:
        from crawler import crs_rules
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([auditor.__file__]), [])

    def test_reuses_frozen_gate_and_primitives(self) -> None:
        src = Path(auditor.__file__).read_text(encoding="utf-8")
        self.assertTrue("validate_registry" in src or "check_answer" in src)
        self.assertIn("audit_eligible_values", src)
        self.assertIn("crs_audit.", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
