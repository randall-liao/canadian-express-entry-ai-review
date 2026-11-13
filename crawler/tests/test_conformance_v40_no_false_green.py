"""SAFE-01 authoritative no-false-green conformance gate (Phase 34 — Plan 01).

The v4.0 release-gate proof that **no perception can become grounded confidence**:
no ``pending`` / unconfirmed / low-confidence / stale / below-threshold value can
ever produce a ``SUBSTANTIATED`` verdict — proven across ALL FOUR modules (core /
spouse / transferability / additional) and the FULL factor grid
(:data:`crawler.auditors.FULL_GRID_FACTORS`), not just the Phase-32 language
pilot. It consolidates and strengthens the fail-closed guarantees shipped in
Phases 30 / 32 / 33 into ONE clearly-labeled conformance module that exhaustively
drives the ``is_audit_eligible`` choke point (:mod:`crawler.vault`) through the
real dispatch spine (:mod:`crawler.auditor`) against the REAL registry + REAL
``corpus/index.db``.

Stdlib ``unittest`` ONLY — NO network. Every fixture is SYNTHETIC (a tmp
``$PR_PERSONAL_DIR`` vault seeded with distinctive synthetic values); NEVER real
applicant data. Guarded by the shipped ``@skipUnless(corpus/index.db)`` inherited
from :class:`crawler.tests.test_full_audit_integration._IntegrationCase` (the DB
IS present locally so these RUN here; on a fresh clone they SKIP and the suite is
structural-only).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_conformance_v40_no_false_green.py -q
"""

from __future__ import annotations

import os
import unittest
from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from crawler import audit_report, auditor, auditors, vault
from crawler.models.audit import (
    FactorVerdict,
    PrivateAuditReport,
    PrivateFactorCard,
    to_public_envelope,
)
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor
from crawler.tests.test_full_audit_integration import _IntegrationCase

# The release-gate entry point (Plan 34-04) discovers this module by the glob
# test_conformance_v40_*.py AND by the ``conformance`` marker.
pytestmark = pytest.mark.conformance

_VOCAB = {"SUBSTANTIATED", "GAP", "AT-RISK", "N/A"}

# The five blocking evidence states — none of which may EVER green a factor.
_BLOCKING_STATES = ("pending", "rejected", "low_quality", "ambiguous", "stale")

# A representative, VALID EXTRACT-01 field name per DIRECT-EVIDENCE grid factor
# (transfer.* are DERIVED — they recombine prior cards and read no direct
# evidence, so they are proven separately below).
_FIELD_FOR: dict[str, str] = {
    "core.age": "date_of_birth",
    "core.education": "credential_level",
    "core.language.first": "raw_score_reading",
    "core.language.second": "raw_score_reading",
    "core.work": "employment_start",
    "spouse.education": "credential_level",
    "spouse.language": "raw_score_reading",
    "spouse.work": "employment_start",
    "additional.nomination": "nomination_stream",
    "additional.job_offer": "issuer",
    "additional.study": "credential_level",
    "additional.french": "raw_score_reading",
    "additional.sibling": "sibling_relationship",
}

_DIRECT_FACTORS: tuple[str, ...] = tuple(_FIELD_FOR)
_DERIVED_FACTORS: tuple[str, ...] = tuple(
    f for f in auditors.FULL_GRID_FACTORS if f.startswith("transfer."))

# A distinctive synthetic value the seeding stamps into every blocked value.
_SENTINEL_VALUE = "SYNTHETIC-BLOCKED-VALUE-ZZZ"


def _group_of(factor_id: str) -> str:
    """The FactorGroup for any factor id (grid factors + the spouse signal)."""
    grp = auditors.FACTOR_GROUP.get(factor_id)
    if grp is not None:
        return grp
    if factor_id.startswith("spouse."):
        return "spouse_common_law"
    if factor_id.startswith("transfer."):
        return "skill_transferability"
    if factor_id.startswith("additional."):
        return "additional_points"
    return "core_human_capital"


class _NoFalseGreenBase(_IntegrationCase):
    """Seed a fresh synthetic candidate vault + drive the REAL spine per factor."""

    _counter = 0

    def setUp(self) -> None:
        super().setUp()
        # audit_one dispatches to the registered deciders; ensure they self-register.
        auditors.load_all()

    def _fresh_vault(self):
        _NoFalseGreenBase._counter += 1
        cid = f"c{_NoFalseGreenBase._counter:04d}"
        v = vault.open_vault(cid)
        vault.create_candidate(v, cid)
        return v

    def _add_value(self, v, factor_id, field, value, *, quality="ok"):
        """Insert ONE pending synthetic value for *factor_id*; return its value id."""
        src = (Path(self._tmp.name)
               / f"{v.candidate_id}_{factor_id.replace('.', '_')}_{field}.pdf")
        src.write_bytes(b"%PDF-1.4 synthetic " + os.urandom(6))
        doc = vault.import_document(
            v, v.candidate_id, src, doc_type="language_test")
        run = vault.record_extraction_run(
            v, document_id=doc.document_id,
            parser_version=vault.current_parser_version())
        return vault.add_extracted_value(
            v, document_id=doc.document_id, page_id=None, factor_id=factor_id,
            field_name=field, raw_text=str(value), normalized_value=value,
            bbox=None, extractor_confidence=0.9, quality_flag=quality,
            extraction_run_id=run)

    def _seed_blocking(self, v, factor_id, field, state):
        """Seed one value for *factor_id* in the given BLOCKING *state*; return id."""
        if state == "pending":
            # Evidence exists but is never confirmed — quarantined.
            return self._add_value(v, factor_id, field, _SENTINEL_VALUE)
        if state == "rejected":
            vid = self._add_value(v, factor_id, field, _SENTINEL_VALUE)
            vault.confirm_value(v, vid, "reject")
            return vid
        if state == "low_quality":
            vid = self._add_value(v, factor_id, field, _SENTINEL_VALUE,
                                  quality="low_quality")
            vault.confirm_value(v, vid, "confirm")
            return vid
        if state == "ambiguous":
            vid = self._add_value(v, factor_id, field, _SENTINEL_VALUE,
                                  quality="ambiguous")
            vault.confirm_value(v, vid, "confirm")
            return vid
        if state == "stale":
            vid = self._add_value(v, factor_id, field, _SENTINEL_VALUE)
            vault.confirm_value(v, vid, "confirm")
            # Invalidate the five-key staleness binding (rule_registry_version).
            v.con.execute(
                "UPDATE extracted_values "
                "SET confirmed_rule_registry_version = 'obsolete' "
                "WHERE value_id = ?", (vid,))
            v.con.commit()
            return vid
        raise AssertionError(f"unknown blocking state {state!r}")

    def _claim(self, v, factor_id):
        """A generic profile claim so a non-derived factor proceeds past N/A."""
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id=factor_id, factor_group=_group_of(factor_id),
            claimed_points=100, claimed_level="9", claimed_value=9,
            source="user_entry"))


class TestChokePointBlocksEveryState(_NoFalseGreenBase):
    """The ``is_audit_eligible`` choke point rejects EVERY blocking state, admits
    only the legitimate (confirmed + ok + fresh) value — for every direct factor."""

    def test_no_blocking_state_is_audit_eligible(self) -> None:
        exercised: set[str] = set()
        for factor_id in _DIRECT_FACTORS:
            field = _FIELD_FOR[factor_id]
            for state in _BLOCKING_STATES:
                with self.subTest(factor=factor_id, state=state):
                    v = self._fresh_vault()
                    try:
                        self._claim(v, factor_id)  # FK: extracted_values.factor_id
                        vid = self._seed_blocking(v, factor_id, field, state)
                        # The value EXISTS but is not audit-eligible (the gate).
                        self.assertFalse(
                            vault.is_audit_eligible(v, vid),
                            f"{factor_id}/{state} crossed the eligibility gate")
                        eligible_ids = {
                            e.value_id
                            for e in vault.audit_eligible_values(v, factor_id)}
                        self.assertNotIn(vid, eligible_ids)
                    finally:
                        v.con.close()
                    exercised.add(factor_id)
        self.assertEqual(exercised, set(_DIRECT_FACTORS))

    def test_legitimate_value_is_admitted_non_vacuous(self) -> None:
        # The SAME gate ADMITS a confirmed + ok + fresh value for every direct
        # factor — proving the block above is a real discriminator, not a blanket
        # deny that would make the no-false-green matrix vacuous.
        for factor_id in _DIRECT_FACTORS:
            field = _FIELD_FOR[factor_id]
            with self.subTest(factor=factor_id):
                v = self._fresh_vault()
                try:
                    self._claim(v, factor_id)  # FK: extracted_values.factor_id
                    vid = self._add_value(v, factor_id, field, _SENTINEL_VALUE)
                    vault.confirm_value(v, vid, "confirm")
                    self.assertTrue(vault.is_audit_eligible(v, vid))
                    eligible_ids = {
                        e.value_id
                        for e in vault.audit_eligible_values(v, factor_id)}
                    self.assertIn(vid, eligible_ids)
                finally:
                    v.con.close()


class TestNoFalseGreenVerdictMatrix(_NoFalseGreenBase):
    """Through the REAL spine: every blocked direct factor + every derived
    transfer factor yields a NON-SUBSTANTIATED verdict in the closed vocabulary."""

    def test_direct_factor_blocked_state_never_substantiated(self) -> None:
        reg = self.registry
        exercised: set[str] = set()
        for factor_id in _DIRECT_FACTORS:
            field = _FIELD_FOR[factor_id]
            for state in _BLOCKING_STATES:
                with self.subTest(factor=factor_id, state=state):
                    v = self._fresh_vault()
                    try:
                        self._claim(v, factor_id)
                        self._seed_blocking(v, factor_id, field, state)
                        # spouse_mode=True so spouse.* deciders actually run (not
                        # short-circuit to N/A) and truly exercise the gate.
                        card = auditor.audit_one(
                            v, factor_id, self.db, reg, spouse_mode=True,
                            reference_date=date.today().isoformat(),
                            prior_cards={}, ita_date=None)
                    finally:
                        v.con.close()
                    self.assertIn(card.verdict, _VOCAB)
                    self.assertNotEqual(
                        card.verdict, "SUBSTANTIATED",
                        f"{factor_id}/{state} produced a FALSE GREEN")
                    exercised.add(factor_id)
        self.assertEqual(exercised, set(_DIRECT_FACTORS))

    def test_derived_transfer_factor_unproven_component_never_green(self) -> None:
        # A derived transfer.* factor with NO substantiated component (empty
        # prior_cards) can never green — it is a fail-closed unmet_component GAP.
        reg = self.registry
        for factor_id in _DERIVED_FACTORS:
            with self.subTest(factor=factor_id):
                v = self._fresh_vault()
                try:
                    card = auditor.audit_one(
                        v, factor_id, self.db, reg, spouse_mode=False,
                        reference_date=date.today().isoformat(),
                        prior_cards={}, ita_date=None)
                finally:
                    v.con.close()
                self.assertIn(card.verdict, _VOCAB)
                self.assertNotEqual(card.verdict, "SUBSTANTIATED")


class TestFullGridRunNoFalseGreen(_NoFalseGreenBase):
    """Whole-grid ``run_full_audit`` over a vault whose evidence is all blocked:
    NO card greens (one representative blocking state per group)."""

    def test_whole_grid_with_blocked_evidence_has_zero_substantiated(self) -> None:
        v = self._fresh_vault()
        try:
            # Representative factor per group, seeded in a representative blocking
            # state, WITH a claim so the factor proceeds past the N/A short-circuit.
            self._claim(v, "core.language.first")
            self._seed_blocking(v, "core.language.first", "raw_score_reading",
                                "pending")
            self._claim(v, "spouse.accompanying")  # turn spouse mode ON
            self._claim(v, "spouse.language")
            self._seed_blocking(v, "spouse.language", "raw_score_reading",
                                "low_quality")
            self._claim(v, "additional.nomination")
            self._seed_blocking(v, "additional.nomination", "nomination_stream",
                                "rejected")
            self._claim(v, "core.work")
            self._seed_blocking(v, "core.work", "employment_start", "stale")
            report = auditor.run_full_audit(v, self.db, self.registry)
        finally:
            v.con.close()
        # The grid still yields exactly one verdict per factor, in vocabulary...
        ids = [c.factor_id for c in report.factor_cards]
        self.assertEqual(sorted(ids), sorted(auditors.FULL_GRID_FACTORS))
        # ...and NONE is SUBSTANTIATED — every value was blocked.
        substantiated = [c.factor_id for c in report.factor_cards
                         if c.verdict == "SUBSTANTIATED"]
        self.assertEqual(substantiated, [], f"false green(s): {substantiated}")
        for card in report.factor_cards:
            self.assertIn(card.verdict, _VOCAB)


class TestMatrixNonVacuousPositiveControls(_NoFalseGreenBase):
    """A fully-satisfying case in EACH of the four modules DOES reach
    SUBSTANTIATED — so the no-false-green matrix is non-vacuous end-to-end."""

    def _seed_full_green(self, v):
        today = date.today()
        # spouse mode ON
        self._claim(v, "spouse.accompanying")
        # core module green: first official language (four abilities → CLB 9)
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id="core.language.first", factor_group="core_human_capital",
            claimed_points=124, claimed_level="9", claimed_value=9))
        self._doc(v, "language_test", "core.language.first", {
            "test_type": "IELTS General Training",
            "test_date": (today - timedelta(days=30)).isoformat(),
            "raw_score_reading": 7.0, "raw_score_writing": 7.0,
            "raw_score_listening": 8.0, "raw_score_speaking": 7.0})
        # spouse module green: spouse-owned language
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id="spouse.language", factor_group="spouse_common_law",
            claimed_points=20, claimed_level="9", claimed_value=9))
        self._doc(v, "language_test", "spouse.language", {
            "test_type": "IELTS General Training",
            "test_date": (today - timedelta(days=30)).isoformat(),
            "raw_score_reading": 7.0, "raw_score_writing": 7.0,
            "raw_score_listening": 8.0, "raw_score_speaking": 7.0})
        # additional module green: verified, non-expired provincial nomination
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id="additional.nomination", factor_group="additional_points",
            claimed_points=600, claimed_value="nominated"))
        self._doc(v, "provincial_nomination", "additional.nomination", {
            "nomination_stream": "SYNTHETIC-STREAM", "expiry_date": "2099-01-01"})
        rnd = vault.set_ita_round(
            v, "default", "r", today.isoformat(), "EE", cutoff_score=500)
        return rnd.round_id

    def test_each_module_has_a_green_and_grid_is_complete(self) -> None:
        # The _doc/_open helpers use the canonical "default" candidate.
        v = self._open()
        try:
            round_id = self._seed_full_green(v)
            report, _ = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
        finally:
            v.con.close()
        cards = {c.factor_id: c for c in report.factor_cards}
        # The exercised factor set equals the full grid (a future grid addition
        # cannot silently escape this gate).
        self.assertEqual(set(cards), set(auditors.FULL_GRID_FACTORS))
        # One green per module: core / spouse / transferability / additional.
        self.assertEqual(cards["core.language.first"].verdict, "SUBSTANTIATED")
        self.assertEqual(cards["spouse.language"].verdict, "SUBSTANTIATED")
        self.assertEqual(
            cards["transfer.foreign_language"].verdict, "SUBSTANTIATED")
        self.assertEqual(cards["additional.nomination"].verdict, "SUBSTANTIATED")
        # Every card verdict is in the closed vocabulary.
        for card in report.factor_cards:
            self.assertIn(card.verdict, _VOCAB)


_REAL_CHUNK_ID = "guidance/job-offer.md#001"  # a real, resolvable corpus chunk


def _bad_language_row(rule_id: str, *, gap: bool, quote: str) -> RuleRow:
    """A synthetic row consumed by core.language.first (ungrounded or gap:true)."""
    return RuleRow(
        rule_id=rule_id,
        factor_group="core_human_capital",
        factor_ids=["core.language.first"],
        check_type="admissibility",
        query="synthetic conformance probe",
        selector=Selector(family="guidance"),
        claim_text="synthetic conformance rule",
        citations=[Citation(chunk_id=_REAL_CHUNK_ID, quote=quote)],
        machine_check=MachineCheck(kind="policy_flag", field="x", flag_value=True),
        volatility=VolatilityMeta(volatility="stable", source_family="guidance"),
        gap=gap,
        gap_reason="synthetic conformance gap" if gap else None)


class TestFailClosedOrderingNoPartialReport(_NoFalseGreenBase):
    """A grounding failure raises AuditGroundingError and writes ZERO artifacts."""

    def _assert_zero_artifacts(self, v) -> None:
        crs_dir = v.root / "output" / "crs-audit"
        artifacts = list(crs_dir.glob("*")) if crs_dir.is_dir() else []
        self.assertEqual(artifacts, [], f"partial report written: {artifacts}")
        self.assertEqual(
            v.con.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
        self.assertEqual(
            v.con.execute("SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)

    def test_ungrounded_consumed_rule_raises_and_writes_nothing(self) -> None:
        bad = Registry(rows=list(self.registry.rows) + [_bad_language_row(
            "core.language.first.conformance_ungrounded", gap=False,
            quote="this span is absolutely not present in the chunk zzz")])
        v = self._fresh_vault()
        try:
            self._claim(v, "core.language.first")
            with self.assertRaises(auditor.AuditGroundingError):
                audit_report.run_audit(v, "core.language.first", self.db, bad)
            self._assert_zero_artifacts(v)
        finally:
            v.con.close()

    def test_consumed_gap_row_raises_and_writes_nothing(self) -> None:
        bad = Registry(rows=list(self.registry.rows) + [_bad_language_row(
            "core.language.first.conformance_gap", gap=True,
            quote="synthetic placeholder quote")])
        v = self._fresh_vault()
        try:
            self._claim(v, "core.language.first")
            with self.assertRaises(auditor.AuditGroundingError):
                audit_report.run_audit(v, "core.language.first", self.db, bad)
            self._assert_zero_artifacts(v)
        finally:
            v.con.close()


class TestDefaultDeciderIsConservative(unittest.TestCase):
    """An unregistered / unwired factor decides AT-RISK — never green (T-33-04)."""

    def test_unregistered_factor_resolves_to_default_at_risk(self) -> None:
        auditors.load_all()
        decider = auditors.resolve("totally.unwired.factor.zzz")
        self.assertIs(decider, auditors._default_decider)
        ctx = auditors.DecisionContext(
            factor_id="totally.unwired.factor.zzz", factor=None, by_field={},
            registry=Registry(rows=[]), consumed=Registry(rows=[]),
            spouse_mode=False, reference_date="2026-01-01")
        result = decider(ctx)
        self.assertEqual(result.verdict, "AT-RISK")
        self.assertNotEqual(result.verdict, "SUBSTANTIATED")


class TestClosedVerdictVocabulary(unittest.TestCase):
    """No out-of-vocabulary 'green-ish' verdict can cross the model boundary."""

    def test_private_card_rejects_out_of_vocab_verdict(self) -> None:
        with self.assertRaises(ValidationError):
            PrivateFactorCard(factor_id="core.age", verdict="GREEN-ISH")
        # A legitimate closed-vocabulary verdict constructs fine.
        for verdict in _VOCAB:
            PrivateFactorCard(factor_id="core.age", verdict=verdict)

    def test_factor_verdict_rejects_out_of_vocab_verdict(self) -> None:
        with self.assertRaises(ValidationError):
            FactorVerdict(factor_id="core.age",
                          factor_group="core_human_capital",
                          verdict="totally-green", reason_code="r")


class TestPublicDownProjectionPreservesVerdicts(unittest.TestCase):
    """to_public_envelope maps each private verdict 1:1 — never invents a green."""

    def test_down_projection_is_verdict_preserving(self) -> None:
        cards = [
            PrivateFactorCard(factor_id="core.language.first",
                              factor_group="core_human_capital",
                              verdict="SUBSTANTIATED",
                              rule_citation_ids=["guidance/a.md#001"]),
            PrivateFactorCard(factor_id="core.work",
                              factor_group="core_human_capital", verdict="GAP"),
            PrivateFactorCard(factor_id="additional.job_offer",
                              factor_group="additional_points",
                              verdict="AT-RISK"),
            PrivateFactorCard(factor_id="spouse.language",
                              factor_group="spouse_common_law", verdict="N/A"),
        ]
        report = PrivateAuditReport(
            run_id="aud_deadbeef0008", candidate_id="default", factor_cards=cards)
        env = to_public_envelope(
            report,
            private_output_path="output/crs-audit/aud_deadbeef0008.json",
        )
        # 1:1 verdict mapping — a GAP/AT-RISK/N/A card never becomes green.
        by_id = {fv.factor_id: fv.verdict for fv in env.verdicts}
        self.assertEqual(by_id["core.language.first"], "SUBSTANTIATED")
        self.assertEqual(by_id["core.work"], "GAP")
        self.assertEqual(by_id["additional.job_offer"], "AT-RISK")
        self.assertEqual(by_id["spouse.language"], "N/A")
        # Counts add up: exactly one substantiated, no phantom greens.
        self.assertEqual(env.counts["substantiated"], 1)
        self.assertEqual(env.counts["gap"], 1)
        self.assertEqual(env.counts["at_risk"], 1)
        self.assertEqual(env.counts["na"], 1)
        self.assertEqual(env.counts["factors"], 4)
        # Every public claim inherits its card's verdict (never upgraded to green).
        for claim in env.claims:
            self.assertIn(claim.verdict, _VOCAB)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()