"""COV-02 net-proof: an unpriced SUBSTANTIATED factor is surfaced, never hidden.

Stdlib ``unittest`` ONLY — NO network, NO vault, NO pytest fixtures. Synthetic
:class:`crawler.models.audit.PrivateFactorCard` / :class:`PrivateAuditReport`
data ONLY.

This is the durable contract for COV-02 (SUMMARY-v4.1 §Coverage Completion, locked
decision D: "Surface any still-unpriced substantiated factor as unresolved"). It
proves the *structural net* that catches a factor whose verdict is
``SUBSTANTIATED`` yet whose ``substantiated_points is None`` — a truthful-but-
incomplete result that today would silently coalesce to ``0`` in the roll-up with
no visible signal:

  1. the card is FLAGGED (``points_unresolved is True``) — never presented as
     complete, and False for a priced card, a genuine-``0`` card, and a
     non-SUBSTANTIATED card;
  2. the PII-light public envelope TALLIES it via ``counts["unpriced"]`` (an
     additive ``dict[str, int]`` key — no schema change), derived from the intrinsic
     ``verdict``/``points`` state so it holds even when the flag was not pre-set;
  3. the vault-only markdown report RENDERS an explicit ``UNRESOLVED (unpriced)``
     line for such a card, distinct from a numeric ``0``;
  4. NO false completeness — ``substantiated_total`` is NOT inflated to hide the
     gap (the unpriced card contributes ``0`` AND is still counted as unpriced, so a
     consumer can tell "0 points, priced" from "unpriced");
  5. the public surfacing carries NO PII — no applicant value and no ``ev_`` id
     reaches the dumped envelope; the counts value is a plain int.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_unpriced_surfacing.py -q
"""

from __future__ import annotations

import json
import unittest

from crawler import audit_report
from crawler.models import audit

# A distinctive applicant-value sentinel — it MUST live on the private card and
# MUST NOT survive the down-projection into the public envelope (SC / PII-light).
_APPLICANT_SENTINEL = "APPLICANT_SENTINEL_secondlang_7_7654321"
_EV_SENTINEL = "ev_sentinel999"


def _build_report() -> audit.PrivateAuditReport:
    """A synthetic report mixing an unpriced, a priced, a genuine-0, and a GAP card.

    The cards are assembled exactly as ``auditor.audit_one`` would after the net is
    in place: the unpriced SUBSTANTIATED card carries ``points_unresolved=True`` (an
    explicit unresolved item), every other card carries ``False``.
    """
    unpriced = audit.PrivateFactorCard(
        factor_id="core.language.second",
        factor_group="core_human_capital",
        verdict="SUBSTANTIATED",
        claimed_value=_APPLICANT_SENTINEL,
        confirmed_value=_APPLICANT_SENTINEL,
        substantiated_points=None,          # <- the residual unpriced case
        points_unresolved=True,             # <- the net flags it
        evidence_ids=[_EV_SENTINEL],
        rule_citation_ids=["guidance/crs-criteria.md#006"],
        reason_code="grounded_substantiated",
    )
    priced = audit.PrivateFactorCard(
        factor_id="core.language.first",
        factor_group="core_human_capital",
        verdict="SUBSTANTIATED",
        substantiated_points=15,
        points_unresolved=False,
        rule_citation_ids=["guidance/crs-criteria.md#007"],
        reason_code="grounded_substantiated",
    )
    priced_zero = audit.PrivateFactorCard(
        factor_id="additional.french",
        factor_group="additional_points",
        verdict="SUBSTANTIATED",
        substantiated_points=0,             # <- a genuine, priced 0 (NOT unpriced)
        points_unresolved=False,
        rule_citation_ids=["guidance/crs-criteria.md#010"],
        reason_code="grounded_substantiated",
    )
    gap = audit.PrivateFactorCard(
        factor_id="additional.sibling",
        factor_group="additional_points",
        verdict="GAP",
        substantiated_points=None,          # None points, but NOT SUBSTANTIATED
        points_unresolved=False,
        reason_code="missing_evidence",
    )
    cards = [unpriced, priced, priced_zero, gap]
    # The roll-up the auditor computes: (points or 0) for SUBSTANTIATED cards only.
    substantiated_total = sum(
        (c.substantiated_points or 0)
        for c in cards if c.verdict == "SUBSTANTIATED")
    return audit.PrivateAuditReport(
        run_id="aud_deadbeef0013",
        candidate_id="default",
        created_at="2026-07-17T00:00:00Z",
        factor_cards=cards,
        substantiated_total=substantiated_total)


class TestUnpricedFlag(unittest.TestCase):
    """(1) A SUBSTANTIATED-but-None card is flagged; nothing else is."""

    def test_only_unpriced_substantiated_card_is_flagged(self) -> None:
        report = _build_report()
        by_id = {c.factor_id: c for c in report.factor_cards}
        self.assertIs(by_id["core.language.second"].points_unresolved, True)
        self.assertIs(by_id["core.language.first"].points_unresolved, False)
        self.assertIs(by_id["additional.french"].points_unresolved, False)
        self.assertIs(by_id["additional.sibling"].points_unresolved, False)

    def test_default_flag_is_false_additive_optional(self) -> None:
        # The additive optional field loads cleanly and defaults to False even for a
        # bare SUBSTANTIATED card (the auditor is what sets the flag, not the model).
        card = audit.PrivateFactorCard(
            factor_id="x", verdict="SUBSTANTIATED")
        self.assertIs(card.points_unresolved, False)


class TestUnpricedCount(unittest.TestCase):
    """(2) counts["unpriced"] tallies exactly the unpriced SUBSTANTIATED cards."""

    def test_counts_unpriced_is_one(self) -> None:
        report = _build_report()
        env = audit.to_public_envelope(
            report, f"output/crs-audit/{report.run_id}.json")
        self.assertEqual(env.counts["unpriced"], 1)
        # The additive key never disturbs the existing tallies.
        self.assertEqual(env.counts["substantiated"], 3)
        self.assertEqual(env.counts["gap"], 1)

    def test_count_derives_from_intrinsic_state_not_the_flag(self) -> None:
        # A card that is SUBSTANTIATED + None but whose flag was (wrongly) left False
        # is STILL counted — the public tally derives from the ground-truth
        # verdict/points, so it cannot be fooled into hiding the gap.
        card = audit.PrivateFactorCard(
            factor_id="core.language.second",
            factor_group="core_human_capital",
            verdict="SUBSTANTIATED",
            substantiated_points=None,
            points_unresolved=False,          # deliberately NOT flagged
            rule_citation_ids=["guidance/crs-criteria.md#006"])
        report = audit.PrivateAuditReport(
            run_id="aud_deadbeef0007", candidate_id="default", factor_cards=[card],
            substantiated_total=0)
        env = audit.to_public_envelope(
            report, f"output/crs-audit/{report.run_id}.json")
        self.assertEqual(env.counts["unpriced"], 1)


class TestUnpricedRender(unittest.TestCase):
    """(3) The vault-only markdown renders an explicit unresolved line."""

    def test_render_marks_unpriced_and_not_priced(self) -> None:
        report = _build_report()
        md = audit_report._render_factor_card_markdown(report)
        # Exactly the unpriced card gets the explicit unresolved line.
        self.assertIn("UNRESOLVED (unpriced", md)
        self.assertEqual(md.count("UNRESOLVED (unpriced"), 1)
        # The priced cards render their numeric points, distinct from a bare None.
        self.assertIn("- Substantiated points: 15", md)
        self.assertIn("- Substantiated points: 0", md)
        # The unpriced SUBSTANTIATED card's OWN section reads UNRESOLVED — never a
        # bare numeric / None points line. (Scoped to that section: a GAP card
        # legitimately still shows None; the net is narrowly for the
        # SUBSTANTIATED-but-unpriced case.)
        sections = md.split("## Factor:")
        unpriced_section = next(
            s for s in sections if "`core.language.second`" in s)
        self.assertIn("UNRESOLVED (unpriced", unpriced_section)
        self.assertNotIn("- Substantiated points: None", unpriced_section)
        self.assertNotIn("- Substantiated points: 0", unpriced_section)


class TestNoFalseCompleteness(unittest.TestCase):
    """(4) The total is not inflated; unpriced is distinguishable from a priced 0."""

    def test_total_not_inflated_and_unpriced_distinguishable(self) -> None:
        report = _build_report()
        # Priced (15) + genuine-0 (0) + unpriced-contributes-0 == 15. The unpriced
        # card adds nothing (no fabricated value) yet is separately visible.
        self.assertEqual(report.substantiated_total, 15)
        recomputed = sum(
            (c.substantiated_points or 0)
            for c in report.factor_cards if c.verdict == "SUBSTANTIATED")
        self.assertEqual(recomputed, 15)
        env = audit.to_public_envelope(
            report, f"output/crs-audit/{report.run_id}.json")
        # A consumer can tell "0 points, priced" (french) from "unpriced" (second
        # language): the priced-0 card is counted substantiated, NOT unpriced.
        self.assertEqual(env.counts["unpriced"], 1)


class TestPublicSurfacingIsPiiLight(unittest.TestCase):
    """(5) The counts surfacing carries no applicant value and no ev_ id."""

    def test_envelope_dump_carries_no_pii(self) -> None:
        report = _build_report()
        env = audit.to_public_envelope(
            report, f"output/crs-audit/{report.run_id}.json")
        dumped = env.model_dump()
        serialized = json.dumps(dumped)
        self.assertNotIn("ev_", serialized)
        self.assertNotIn(_APPLICANT_SENTINEL, serialized)
        # The new counts key is a plain int.
        self.assertIsInstance(dumped["counts"]["unpriced"], int)
        self.assertEqual(dumped["counts"]["unpriced"], 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
