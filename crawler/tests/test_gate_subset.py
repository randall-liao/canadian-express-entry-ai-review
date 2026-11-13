"""Hermetic parity tests for the promoted public grounding gate ``auditor.gate_subset``.

Plan 40-02 promotes the private ``_gate_or_raise`` to a public ``gate_subset`` via a
VERBATIM body extraction plus a ``_gate_or_raise = gate_subset`` back-compat alias, so
every v5.0 screen (MEC / POLICY / STUDY) reuses the ONE shipped grounding gate rather
than re-implementing ``crs_rules.validate_registry`` (SAFE-09 SC2).

These tests are HERMETIC: they build synthetic ``Registry`` / ``RuleRow`` objects
in-process and never touch a real corpus or ``searchindex`` db. That is possible because
``crs_rules.validate_registry`` SKIPS every ``gap:true`` row via ``continue`` BEFORE any
db access, and an empty subset carries zero non-gap rows — so both exercised paths
raise/return WITHOUT ever opening the (deliberately non-existent) db path below.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from crawler import auditor
from crawler.models.crs_rules import (
    AcceptedValue,
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)

# A db path that does NOT exist — proves the exercised paths never open a db (hermetic).
_NO_DB = "/nonexistent/index.db"
_REAL_DB = Path(__file__).resolve().parents[2] / "corpus" / "index.db"


def _gap_row(rule_id: str = "safe.freshness.gap") -> RuleRow:
    """A structurally valid ``gap:true`` coverage-gap row (placeholder citation only).

    Mirrors the ``test_crs_audit._row`` shape: a single placeholder citation and a
    minimal machine check, marked ``gap=True`` so ``validate_registry`` skips it before
    any db access and the promoted gate's gap loop raises hermetically.
    """
    return RuleRow(
        rule_id=rule_id,
        factor_group="core_human_capital",
        factor_ids=[rule_id],
        check_type="policy",
        query="q",
        selector=Selector(family="guidance"),
        claim_text="synthetic coverage-gap row",
        citations=[Citation(chunk_id="g/p.md#000", quote="p")],
        machine_check=MachineCheck(kind="policy_flag", field="gap", flag_value=False),
        volatility=VolatilityMeta(volatility="stable", source_family="guidance"),
        gap=True,
        gap_reason="doc",
    )


class TestGateSubsetAliasIdentity(unittest.TestCase):
    def test_gate_subset_is_the_back_compat_alias(self):
        # The promotion is a pure rename + alias: audit_one's frozen call site
        # (``_gate_or_raise``) MUST resolve to the EXACT same object as ``gate_subset``,
        # which is what keeps auditor.py:207 byte-for-byte and the frozen grid green.
        self.assertIs(auditor.gate_subset, auditor._gate_or_raise)


class TestGateSubsetBehaviorParity(unittest.TestCase):
    def test_empty_subset_is_a_no_op(self):
        # Zero non-gap rows -> validate_registry never opens the db -> no raise, returns None.
        self.assertIsNone(auditor.gate_subset(Registry(rows=[]), _NO_DB))

    def test_consumed_gap_row_raises_grounding_error(self):
        # A consumed gap:true row is an ungrounded coverage gap -> AuditGroundingError.
        # validate_registry SKIPS the gap row BEFORE any db access, so this is hermetic.
        with self.assertRaises(auditor.AuditGroundingError) as ctx:
            auditor.gate_subset(Registry(rows=[_gap_row("safe.freshness.gap")]), _NO_DB)
        self.assertIn("safe.freshness.gap", str(ctx.exception))

    def test_grounding_error_message_is_pii_free(self):
        # The gate's error surface names rule ids / reasons only — never an ``ev_`` id.
        with self.assertRaises(auditor.AuditGroundingError) as ctx:
            auditor.gate_subset(Registry(rows=[_gap_row()]), _NO_DB)
        self.assertNotIn("ev_", str(ctx.exception))


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY: real corpus index is required for non-vacuous selector controls",
)
class TestGateSubsetRetrieveWhatYouCite(unittest.TestCase):
    """The shared gate must enforce selector/citation agreement, not only quotes."""

    @staticmethod
    def _row() -> RuleRow:
        return RuleRow(
            rule_id="study.dynamic.O19332746152.designation",
            factor_group="additional_points",
            factor_ids=["review.study"],
            check_type="admissibility",
            query="O19332746152",
            selector=Selector(
                family="dli",
                marker="DLI number: O19332746152",
                require_title_contains="DLI O19332746152",
            ),
            claim_text="The current snapshot records this DLI identifier.",
            citations=[Citation(
                chunk_id="dli/O19332746152.md#000",
                quote="DLI number: O19332746152",
            )],
            machine_check=MachineCheck(
                kind="accepted_enum",
                field="dli_number",
                accepted_values=[AcceptedValue(value="O19332746152")],
            ),
            volatility=VolatilityMeta(
                volatility="volatile",
                source_family="dli",
                crawl_date="2026-07-16T18:08:26Z",
            ),
        )

    def test_gate_accepts_valid_candidate_unique_selector(self) -> None:
        with mock.patch(
                "crawler.crs_rules.retrieve_what_you_cite",
                wraps=__import__(
                    "crawler.crs_rules", fromlist=["retrieve_what_you_cite"]
                ).retrieve_what_you_cite) as retrieve:
            self.assertIsNone(
                auditor.gate_subset(Registry(rows=[self._row()]), _REAL_DB))
        retrieve.assert_called_once()

    def test_gate_rejects_quote_marker_family_and_title_dli_tampering(self) -> None:
        mutations = {
            "quote": {
                "citations": [{
                    "chunk_id": "dli/O19332746152.md#000",
                    "quote": "DLI number: O00000000000",
                }],
            },
            "marker": {
                "selector": {
                    "family": "dli",
                    "marker": "DLI number: O00000000000",
                    "require_title_contains": "DLI O19332746152",
                },
            },
            "family": {
                "selector": {
                    "family": "guidance",
                    "marker": "DLI number: O19332746152",
                    "require_title_contains": "DLI O19332746152",
                },
            },
            "title_dli": {
                "selector": {
                    "family": "dli",
                    "marker": "DLI number: O19332746152",
                    "require_title_contains": "DLI O246878951383",
                },
            },
        }
        for label, update in mutations.items():
            with self.subTest(label=label):
                raw = self._row().model_dump()
                raw.update(update)
                row = RuleRow.model_validate(raw)
                with self.assertRaises(auditor.AuditGroundingError):
                    auditor.gate_subset(Registry(rows=[row]), _REAL_DB)


if __name__ == "__main__":
    unittest.main()
