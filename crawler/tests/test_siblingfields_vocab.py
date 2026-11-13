"""Anti-drift gate for the shared sibling evidence field vocabulary (COV-03).

Stdlib ``unittest`` ONLY — NO network, NO vault, NO pytest fixtures. This is the
producer<->consumer seam guard for the sibling-in-Canada evidence factor (mirrors
``test_testtype_vocab.py``, the BLOCKER-B P30<->P31 pattern):

  * PRODUCER — ``crawler.extraction._FIELD_SPECS["sibling_proof"]`` proposes the
    sibling fields a document can yield.
  * BOUNDARY — ``crawler.models.vault.FieldName`` (a ``Literal``) is the pydantic
    gate every extracted value's ``field_name`` must satisfy.
  * VOCAB — ``crawler.siblingfields.SIBLING_FIELDS`` is the ONE shared source of
    truth both sides are pinned to.

If ANY of the three drifts (a spec field the boundary rejects, a boundary member
the vocab does not mirror, a vocab name no spec emits) the set-equality assertion
here fails loudly instead of silently GAP-ing a genuinely-qualified applicant —
exactly the failure mode ``test_testtype_vocab.py`` guards for language.

The three sides are each read EXACTLY the way their owner reads them (no second
hard-coded interpretation): ``FieldName`` via ``typing.get_args`` filtered to the
``sibling_`` prefix, and the spec via tuple-unpacking of the ``(name, regex, kind)``
rows. A future rename on ONE side therefore trips this gate rather than passing.

``siblingfields`` carries NAMES/ENUMS ONLY — no CRS points, levels, or caps — so it
stays OUTSIDE the ``no_inlined_volatile_rules`` scan surface (35-04's decider reads
the sibling points from a grounded registry row, never from here).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_siblingfields_vocab.py -q
"""

from __future__ import annotations

import typing
import unittest

from crawler import extraction, siblingfields
from crawler.models import vault as vault_models

_EXPECTED_SIBLING_FIELDS = {
    "sibling_relationship",
    "sibling_status",
    "sibling_residence",
    "sibling_date_of_birth",
}


def _fieldname_sibling_members() -> set[str]:
    """The ``sibling_``-prefixed members of the ``FieldName`` Literal.

    Read the SAME way the pydantic boundary introspects the Literal
    (``typing.get_args``), filtered to the sibling namespace — NOT a second
    hard-coded list, so a rename of a boundary member is caught as drift.
    """
    return {m for m in typing.get_args(vault_models.FieldName)
            if isinstance(m, str) and m.startswith("sibling_")}


def _spec_field_names() -> set[str]:
    """The field names in ``_FIELD_SPECS['sibling_proof']``.

    Read the SAME way the extractor consumes the spec — tuple-unpacking each
    ``(field_name, label_regex, kind)`` row — so a spec edit is caught as drift.
    """
    return {name for name, _regex, _kind
            in extraction._FIELD_SPECS["sibling_proof"]}


class TestSiblingVocabPinnedProducerConsumer(unittest.TestCase):
    def test_all_three_sibling_field_sets_are_equal(self) -> None:
        """Drift in ANY direction fails (mirror of BLOCKER-B anti-drift)."""
        vocab = set(siblingfields.SIBLING_FIELDS)
        boundary = _fieldname_sibling_members()
        spec = _spec_field_names()
        self.assertEqual(
            vocab, boundary,
            "SIBLING_FIELDS has drifted from the FieldName Literal sibling "
            "members — the extraction<->vault boundary is broken")
        self.assertEqual(
            vocab, spec,
            "SIBLING_FIELDS has drifted from _FIELD_SPECS['sibling_proof'] — the "
            "extractor emits a field the shared vocabulary does not declare")

    def test_sibling_fields_are_exactly_the_four_members(self) -> None:
        self.assertEqual(set(siblingfields.SIBLING_FIELDS),
                         _EXPECTED_SIBLING_FIELDS)


class TestSiblingAcceptedEnums(unittest.TestCase):
    def test_status_accepted_enum_is_fail_closed(self) -> None:
        self.assertEqual(
            siblingfields.SIBLING_STATUS_ACCEPTED,
            frozenset({"citizen", "permanent_resident"}))
        # An unknown token is NOT a member (fail-closed — never coerced accepted).
        self.assertNotIn("visitor", siblingfields.SIBLING_STATUS_ACCEPTED)
        self.assertNotIn("", siblingfields.SIBLING_STATUS_ACCEPTED)

    def test_relationship_accepted_enum_is_fail_closed(self) -> None:
        self.assertEqual(
            siblingfields.SIBLING_RELATIONSHIP_ACCEPTED,
            frozenset({"brother", "sister"}))
        self.assertNotIn("cousin", siblingfields.SIBLING_RELATIONSHIP_ACCEPTED)
        self.assertNotIn("parent", siblingfields.SIBLING_RELATIONSHIP_ACCEPTED)


class TestSiblingLinkageTarget(unittest.TestCase):
    def test_doc_type_factor_targets_additional_sibling(self) -> None:
        self.assertEqual(
            extraction._DOC_TYPE_FACTOR["sibling_proof"], "additional.sibling")


class TestSiblingCanonicalization(unittest.TestCase):
    """WR-01: the extraction-side canonicalizer maps a document's natural surface
    forms onto the SAME accepted ENUMS above, fail-closed. Mirrors the BLOCKER-B
    ``test_testtype_vocab.py`` normalization coverage."""

    def test_alias_targets_are_members_of_the_accepted_enums(self) -> None:
        # The alias tables can ONLY ever resolve to an accepted token — a stray
        # value that is not a member would be a silent false-green vector.
        self.assertTrue(
            set(siblingfields.SIBLING_STATUS_ALIASES.values())
            <= set(siblingfields.SIBLING_STATUS_ACCEPTED),
            "a status alias resolves to a non-accepted token")
        self.assertTrue(
            set(siblingfields.SIBLING_RELATIONSHIP_ALIASES.values())
            <= set(siblingfields.SIBLING_RELATIONSHIP_ACCEPTED),
            "a relationship alias resolves to a non-accepted token")

    def test_status_surface_forms_canonicalize_to_accepted_tokens(self) -> None:
        for raw in ("Permanent Resident", "permanent resident", "PERMANENT  RESIDENT",
                    "PR", "pr", "permanent_resident", "permanent-resident"):
            got = siblingfields.normalize_sibling_status(raw)
            self.assertEqual(got, "permanent_resident", raw)
            self.assertIn(got, siblingfields.SIBLING_STATUS_ACCEPTED)
        for raw in ("Citizen", "citizen", "Canadian Citizen", "Citizen of Canada"):
            got = siblingfields.normalize_sibling_status(raw)
            self.assertEqual(got, "citizen", raw)
            self.assertIn(got, siblingfields.SIBLING_STATUS_ACCEPTED)

    def test_relationship_surface_forms_canonicalize_to_accepted_tokens(self) -> None:
        for raw in ("Brother", "brother", "  BROTHER "):
            got = siblingfields.normalize_sibling_relationship(raw)
            self.assertEqual(got, "brother", raw)
            self.assertIn(got, siblingfields.SIBLING_RELATIONSHIP_ACCEPTED)
        for raw in ("Sister", "sister"):
            got = siblingfields.normalize_sibling_relationship(raw)
            self.assertEqual(got, "sister", raw)
            self.assertIn(got, siblingfields.SIBLING_RELATIONSHIP_ACCEPTED)

    def test_canonicalization_is_idempotent_on_accepted_tokens(self) -> None:
        for tok in siblingfields.SIBLING_STATUS_ACCEPTED:
            self.assertEqual(siblingfields.normalize_sibling_status(tok), tok)
        for tok in siblingfields.SIBLING_RELATIONSHIP_ACCEPTED:
            self.assertEqual(siblingfields.normalize_sibling_relationship(tok), tok)

    def test_unknown_surface_forms_stay_non_accepted_fail_closed(self) -> None:
        # An unrecognized token is NEVER coerced to an accepted value — it stays
        # its own (non-member) lookup key so decide_sibling fail-closes.
        for raw in ("Cousin", "Parent", "Temporary Visitor", "Work Permit",
                    "Refugee Claimant", "Study Permit"):
            self.assertNotIn(siblingfields.normalize_sibling_status(raw),
                             siblingfields.SIBLING_STATUS_ACCEPTED)
            self.assertNotIn(siblingfields.normalize_sibling_relationship(raw),
                             siblingfields.SIBLING_RELATIONSHIP_ACCEPTED)
        # A relationship word must NOT satisfy the status enum (and vice versa).
        self.assertNotIn(siblingfields.normalize_sibling_status("Brother"),
                         siblingfields.SIBLING_STATUS_ACCEPTED)
        self.assertNotIn(
            siblingfields.normalize_sibling_relationship("Permanent Resident"),
            siblingfields.SIBLING_RELATIONSHIP_ACCEPTED)

    def test_empty_or_missing_input_returns_none(self) -> None:
        for raw in ("", "   ", "\t\n"):
            self.assertIsNone(siblingfields.normalize_sibling_status(raw))
            self.assertIsNone(siblingfields.normalize_sibling_relationship(raw))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
