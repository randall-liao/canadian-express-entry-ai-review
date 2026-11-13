"""Anti-drift gate for the shared canonical language test_type vocabulary.

Stdlib ``unittest`` ONLY — NO network, NO pytest fixtures. This is the P30<->P31
seam guard (BLOCKER B): the Phase-30 extractor MUST normalize its raw test-type
tokens to EXACTLY the Phase-31 registry accepted-enum vocabulary. If either side
drifts (a token the extractor emits stops being registry-accepted, or the registry
enum gains/loses a value the vocab does not mirror), the set-equality assertion
here fails loudly instead of silently GAP-ing a qualified applicant as
``unaccepted_test_type``.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_testtype_vocab.py -q
"""

from __future__ import annotations

import unittest

from crawler import crs_rules, extraction, testtypes


def _registry_accepted_test_types() -> set[str]:
    """Read the registry ``test_type`` accepted-enum EXACTLY as core.py does.

    Mirrors ``crawler.auditors.core._accepted_test_types`` (iterate ``registry.rows``,
    match ``machine_check.kind == 'accepted_enum'`` and ``field == 'test_type'``,
    collect ``av.value``) so this gate pins to the SAME source of truth the auditor
    reads — no second interpretation of the enum.
    """
    registry = crs_rules.load_registry()
    for row in registry.rows:
        mc = row.machine_check
        if (mc.kind == "accepted_enum" and mc.field == "test_type"
                and mc.accepted_values):
            return {av.value for av in mc.accepted_values}
    raise AssertionError("registry has no accepted_enum for field test_type")


class TestCanonicalVocabPinnedToRegistry(unittest.TestCase):
    def test_canonical_set_equals_registry_accepted_enum(self) -> None:
        """Drift in EITHER direction fails (BLOCKER-B anti-drift gate)."""
        accepted = _registry_accepted_test_types()
        self.assertEqual(
            set(testtypes.CANONICAL_TEST_TYPES), accepted,
            "P30 CANONICAL_TEST_TYPES has drifted from the P31 registry "
            "test_type accepted-enum — the extraction<->registry seam is broken")

    def test_canonical_values_are_the_five_registry_values(self) -> None:
        self.assertEqual(
            set(testtypes.CANONICAL_TEST_TYPES),
            {"CELPIP-General", "IELTS General Training", "PTE Core",
             "TEF Canada", "TCF Canada"})


class TestNormalizeTestType(unittest.TestCase):
    def test_ielts_token_normalizes_to_general_training(self) -> None:
        self.assertEqual(
            testtypes.normalize_test_type("IELTS"), "IELTS General Training")

    def test_celpip_token_normalizes_to_celpip_general(self) -> None:
        self.assertEqual(
            testtypes.normalize_test_type("CELPIP"), "CELPIP-General")

    def test_pte_tokens_normalize_to_pte_core(self) -> None:
        self.assertEqual(testtypes.normalize_test_type("PTE Core"), "PTE Core")
        self.assertEqual(testtypes.normalize_test_type("PTE"), "PTE Core")

    def test_tef_tokens_normalize_to_tef_canada(self) -> None:
        self.assertEqual(testtypes.normalize_test_type("TEF Canada"), "TEF Canada")
        self.assertEqual(testtypes.normalize_test_type("TEF"), "TEF Canada")

    def test_tcf_tokens_normalize_to_tcf_canada(self) -> None:
        self.assertEqual(testtypes.normalize_test_type("TCF Canada"), "TCF Canada")
        self.assertEqual(testtypes.normalize_test_type("TCF"), "TCF Canada")

    def test_case_and_spacing_insensitive(self) -> None:
        self.assertEqual(
            testtypes.normalize_test_type("ielts   general training"),
            "IELTS General Training")
        self.assertEqual(
            testtypes.normalize_test_type("celpip-general"), "CELPIP-General")
        self.assertEqual(
            testtypes.normalize_test_type("  IELTS  "), "IELTS General Training")

    def test_every_canonical_output_is_a_member_of_the_set(self) -> None:
        for token in ("IELTS", "CELPIP", "PTE", "PTE Core", "TEF", "TEF Canada",
                      "TCF", "TCF Canada"):
            self.assertIn(
                testtypes.normalize_test_type(token),
                testtypes.CANONICAL_TEST_TYPES, token)

    def test_unknown_token_fails_closed_not_accepted(self) -> None:
        """An unknown token stays NON-accepted (never coerced to an accepted value)."""
        result = testtypes.normalize_test_type("Duolingo English Test")
        self.assertNotIn(result, testtypes.CANONICAL_TEST_TYPES)

    def test_empty_or_none_returns_none(self) -> None:
        self.assertIsNone(testtypes.normalize_test_type(""))
        self.assertIsNone(testtypes.normalize_test_type("   "))
        self.assertIsNone(testtypes.normalize_test_type(None))  # type: ignore[arg-type]


class TestExtractorTokensAllNormalizeAccepted(unittest.TestCase):
    """Every token the extractor ``_TEST_TYPE_RE`` can capture must land in the
    accepted set — otherwise a real extracted document could silently GAP."""

    # The concrete alternatives inside crawler.extraction._TEST_TYPE_RE.
    _CAPTURABLE = (
        "IELTS", "CELPIP", "TEF Canada", "TEF", "TCF Canada", "TCF",
        "PTE Core", "PTE",
    )

    def test_regex_alternatives_are_the_ones_asserted(self) -> None:
        # Guard against the regex growing a new alternative that this test forgets
        # to cover: assert each capturable token is actually matchable.
        for token in self._CAPTURABLE:
            self.assertIsNotNone(
                extraction._TEST_TYPE_RE.search(token), token)

    def test_all_captured_tokens_normalize_into_canonical_set(self) -> None:
        for token in self._CAPTURABLE:
            self.assertIn(
                testtypes.normalize_test_type(token),
                testtypes.CANONICAL_TEST_TYPES, token)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
