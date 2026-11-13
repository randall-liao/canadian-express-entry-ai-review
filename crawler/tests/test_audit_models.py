"""Boundary tests for the Phase 32 audit CORE contract (AUDIT-02 / AUDIT-06).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. These tests prove the
STRUCTURAL PII firewall of ``crawler.models.audit``:

* the four-value :data:`Verdict` vocabulary is a closed ``Literal`` (SC1);
* the PII-LIGHT public tier (``PublicClaim`` / ``FactorVerdict`` /
  ``PublicAuditEnvelope``) can carry a corpus ``citation_id`` but is
  structurally incapable of carrying a vault ``ev_`` evidence id or any
  applicant value (``extra="forbid"`` + an ``ev_`` field_validator) — SC4;
* the PII-BEARING private tier (``PrivateFactorCard`` / ``PrivateAuditReport``)
  IS the one tier permitted to hold applicant values + ``ev_`` pointers;
* ``to_public_envelope`` is a tested strict down-projection that strips PII.

Synthetic data ONLY.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_audit_models.py -q
"""

from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from crawler.models import audit


class TestVerdictVocabulary(unittest.TestCase):
    """SC1: the verdict vocabulary is a closed four-value Literal."""

    def test_four_verdicts_accepted(self) -> None:
        for verdict in ("SUBSTANTIATED", "GAP", "AT-RISK", "N/A"):
            claim = audit.PublicClaim(
                claim_text="a grounded corpus rule",
                citation_id="guidance/language-test.md#001",
                verdict=verdict,
            )
            self.assertEqual(claim.verdict, verdict)

    def test_out_of_vocabulary_verdict_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            audit.PublicClaim(
                claim_text="x",
                citation_id="guidance/language-test.md#001",
                verdict="GREEN",  # not one of the four
            )


class TestPublicClaimFirewall(unittest.TestCase):
    """SC4: PublicClaim carries a corpus citation_id but never an ev_ id / PII."""

    def test_corpus_citation_id_accepted(self) -> None:
        claim = audit.PublicClaim(
            claim_text="First-language points are awarded from the CLB level.",
            citation_id="guidance/crs-criteria.md#006",
            verdict="SUBSTANTIATED",
        )
        self.assertEqual(claim.citation_id, "guidance/crs-criteria.md#006")

    def test_ev_prefixed_citation_id_rejected(self) -> None:
        # A bare ev_ id has no '#ordinal' shape AND is ev_-prefixed — rejected.
        with self.assertRaises(ValidationError):
            audit.PublicClaim(
                claim_text="x",
                citation_id="ev_abc123",
                verdict="GAP",
            )

    def test_ev_prefixed_even_with_ordinal_shape_rejected(self) -> None:
        # Even a value that satisfies the relpath#ordinal shape is rejected the
        # moment it is ev_-prefixed (the structural firewall).
        with self.assertRaises(ValidationError):
            audit.PublicClaim(
                claim_text="x",
                citation_id="ev_abc#001",
                verdict="GAP",
            )

    def test_extra_pii_key_rejected(self) -> None:
        # extra="forbid": an injected applicant/evidence key fails at load.
        for bad_key in ("raw_value", "normalized_value", "evidence_id"):
            with self.assertRaises(ValidationError):
                audit.PublicClaim(**{
                    "claim_text": "x",
                    "citation_id": "guidance/language-test.md#001",
                    "verdict": "GAP",
                    bad_key: "9",
                })


class TestPublicAuditEnvelope(unittest.TestCase):
    """SC4: the public envelope round-trips PII-light only."""

    def _envelope(self) -> audit.PublicAuditEnvelope:
        return audit.PublicAuditEnvelope(
            run_id="aud_deadbeef0001",
            factor_id="core.language.first",
            verdicts=[
                audit.FactorVerdict(
                    factor_id="core.language.first",
                    factor_group="core_human_capital",
                    verdict="SUBSTANTIATED",
                    reason_code="grounded_substantiated",
                    claim_count=1,
                )
            ],
            claims=[
                audit.PublicClaim(
                    claim_text="grounded corpus rule",
                    citation_id="guidance/crs-criteria.md#006",
                    verdict="SUBSTANTIATED",
                )
            ],
            counts={"eligible": 6, "grounded": 4},
            private_output_path="output/crs-audit/aud_deadbeef0001.json",
        )

    def test_valid_envelope_round_trips_pii_light(self) -> None:
        env = self._envelope()
        dumped = env.model_dump()
        serialized = json.dumps(dumped)
        # Only PII-light keys are present; no applicant-value / ev_ carrier.
        self.assertEqual(dumped["run_id"], "aud_deadbeef0001")
        self.assertEqual(dumped["factor_id"], "core.language.first")
        self.assertIn("verdicts", dumped)
        self.assertIn("claims", dumped)
        self.assertIn("counts", dumped)
        self.assertEqual(
            dumped["private_output_path"],
            "output/crs-audit/aud_deadbeef0001.json",
        )
        self.assertNotIn("ev_", serialized)
        self.assertNotIn("raw_value", serialized)

    def test_extra_applicant_key_rejected(self) -> None:
        for bad_key in ("applicant_value", "evidence_id", "raw_text"):
            with self.assertRaises(ValidationError):
                audit.PublicAuditEnvelope(**{
                    "run_id": "aud_deadbeef0001",
                    "factor_id": "core.language.first",
                    "verdicts": [],
                    "claims": [],
                    "counts": {},
                    "private_output_path": (
                        "output/crs-audit/aud_deadbeef0001.json"
                    ),
                    bad_key: "9",
                })

    def test_absolute_private_output_path_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            audit.PublicAuditEnvelope(
                run_id="aud_deadbeef0001",
                factor_id="core.language.first",
                private_output_path="/home/user/personal/candidates/x/out.json",
            )
        with self.assertRaises(ValidationError):
            audit.PublicAuditEnvelope(
                run_id="aud_deadbeef0001",
                factor_id="core.language.first",
                private_output_path="candidates/x/output/crs-audit/aud_x.json",
            )


class TestPrivateTier(unittest.TestCase):
    """The PII-BEARING private tier IS allowed to hold applicant values + ev_ ids."""

    def test_private_factor_card_carries_applicant_values(self) -> None:
        card = audit.PrivateFactorCard(
            factor_id="core.language.first",
            verdict="SUBSTANTIATED",
            claimed_value=9,
            confirmed_value=9,
            substantiated_points=29,
            score_delta=0,
            evidence_ids=["ev_abc123"],
            rule_citation_ids=["guidance/crs-criteria.md#006"],
        )
        self.assertEqual(card.claimed_value, 9)
        self.assertEqual(card.confirmed_value, 9)
        # This is the ONE tier permitted to reference vault evidence ids.
        self.assertEqual(card.evidence_ids, ["ev_abc123"])
        self.assertEqual(card.rule_citation_ids, ["guidance/crs-criteria.md#006"])

    def test_private_factor_card_group_optional(self) -> None:
        card = audit.PrivateFactorCard(factor_id="core.language.first", verdict="N/A")
        self.assertIsNone(card.factor_group)

    def test_private_audit_report_round_trips(self) -> None:
        report = audit.PrivateAuditReport(
            run_id="aud_deadbeef0001",
            candidate_id="default",
            created_at="2026-07-06T00:00:00Z",
            factor_cards=[
                audit.PrivateFactorCard(
                    factor_id="core.language.first",
                    factor_group="core_human_capital",
                    verdict="SUBSTANTIATED",
                    claimed_value=9,
                    confirmed_value=9,
                    substantiated_points=116,
                    score_delta=0,
                    evidence_ids=["ev_abc123"],
                    rule_citation_ids=["guidance/crs-criteria.md#006"],
                )
            ],
            substantiated_total=116,
            cutoff_delta=None,
        )
        again = audit.PrivateAuditReport.model_validate(report.model_dump())
        self.assertEqual(again.run_id, "aud_deadbeef0001")
        self.assertEqual(again.factor_cards[0].evidence_ids, ["ev_abc123"])

    def test_private_report_rejects_extra_key(self) -> None:
        with self.assertRaises(ValidationError):
            audit.PrivateAuditReport(
                run_id="aud_x", candidate_id="default",
                created_at="2026-07-06T00:00:00Z",
                unexpected_key="oops",
            )


class TestDownProjection(unittest.TestCase):
    """SC4: to_public_envelope strips PII — no ev_ value, no applicant-value key."""

    def _report(self) -> audit.PrivateAuditReport:
        return audit.PrivateAuditReport(
            run_id="aud_deadbeef0001",
            candidate_id="default",
            created_at="2026-07-06T00:00:00Z",
            factor_cards=[
                audit.PrivateFactorCard(
                    factor_id="core.language.first",
                    factor_group="core_human_capital",
                    verdict="SUBSTANTIATED",
                    claimed_value=9,
                    confirmed_value={"raw_score_reading": 7.7654321, "min_clb": 9},
                    substantiated_points=116,
                    score_delta=0,
                    reason_code="grounded_substantiated",
                    evidence_ids=["ev_sentinel999"],
                    rule_citation_ids=["guidance/crs-criteria.md#006"],
                )
            ],
            substantiated_total=116,
        )

    def test_down_projection_is_pii_light(self) -> None:
        report = self._report()
        env = audit.to_public_envelope(
            report,
            private_output_path="output/crs-audit/aud_deadbeef0001.json",
        )
        self.assertIsInstance(env, audit.PublicAuditEnvelope)
        serialized = json.dumps(env.model_dump())
        # No ev_ evidence pointer, no applicant-value key, no raw sentinel value.
        self.assertNotIn("ev_sentinel999", serialized)
        self.assertNotIn("ev_", serialized)
        self.assertNotIn("claimed_value", serialized)
        self.assertNotIn("confirmed_value", serialized)
        self.assertNotIn("7.7654321", serialized)
        # The claims carry ONLY corpus citation ids (never evidence ids).
        self.assertTrue(env.claims)
        for claim in env.claims:
            self.assertFalse(claim.citation_id.startswith("ev_"))
        self.assertEqual(
            env.private_output_path,
            "output/crs-audit/aud_deadbeef0001.json",
        )
        # The per-factor verdict survives; the score/values do not.
        self.assertEqual(env.verdicts[0].verdict, "SUBSTANTIATED")
        self.assertEqual(env.verdicts[0].factor_id, "core.language.first")

    def test_down_projection_carries_run_id_and_factor(self) -> None:
        report = self._report()
        env = audit.to_public_envelope(
            report,
            private_output_path="output/crs-audit/aud_deadbeef0001.json",
        )
        self.assertEqual(env.run_id, "aud_deadbeef0001")
        self.assertEqual(env.factor_id, "core.language.first")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
