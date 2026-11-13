"""Canonical sibling-in-Canada evidence field vocabulary — the ONE source of truth
shared by Phase-35 sibling extraction and pinned to the ``FieldName`` boundary.

Why this module exists (COV-03): the ``additional.sibling`` rule row already grounds
(15 pts, ``crs-criteria.md#019``), but the sibling factor was structurally
unreachable because the EXTRACT-01 field vocabulary carried NO sibling fields — an
applicant could not import, extract, or confirm sibling relationship/status/age/
Canadian-residence proof. This mirrors the Phase-30 shared-vocabulary template
(``testtypes.py`` + ``test_testtype_vocab.py``): centralize the sibling field NAMES
here, extend the ``FieldName`` Literal + ``_FIELD_SPECS['sibling_proof']`` to match,
and pin producer<->consumer agreement with ``test_siblingfields_vocab.py`` so the two
sides cannot silently re-diverge and GAP a qualified applicant.

Scope discipline: this module carries field NAMES, fail-closed accepted-token
ENUMS, and the EXTRACTION-side canonicalizer that maps a document's natural
surface forms onto those tokens (WR-01). It contains NO CRS points, levels,
thresholds, or caps — the sibling points (and the adult/minor age threshold) live
EXCLUSIVELY in the grounded registry row that plan 35-04's decider reads. Because
it carries no volatile scoring number, this module stays OUTSIDE the
``no_inlined_volatile_rules`` scan surface. Pure stdlib — no runtime dependencies.

Why the canonicalizer exists (WR-01): the extractor stored the two closed-enum
sibling text fields VERBATIM, so a genuine "proof of relative" document printing
natural values (``Brother``, ``Permanent Resident``, ``PR``, ``Canadian Citizen``)
never equalled the internal snake_case tokens and the already-grounded sibling
factor fail-closed to AT-RISK for every real applicant. This mirrors the Phase-30
``testtypes.normalize_test_type`` (BLOCKER-B) pattern: a deterministic, case/space
folding alias map keyed on the SAME accepted ENUMS above, applied at extraction so
the confirmed ``normalized_value`` is the canonical token the decider gates on.
Discipline is preserved — an UNKNOWN surface form is NEVER coerced to an accepted
token (it collapses to its own lookup key, which is not a member of the ENUM), so
``decide_sibling`` stays conjunctive fail-closed with no new false-green path.
"""

from __future__ import annotations

import re

# The four sibling evidence field names. This set is asserted EQUAL to the
# ``sibling_``-prefixed members of ``crawler.models.vault.FieldName`` AND to the
# field names in ``crawler.extraction._FIELD_SPECS['sibling_proof']`` by
# ``crawler/tests/test_siblingfields_vocab.py`` — drift in ANY direction fails.
SIBLING_FIELDS: frozenset[str] = frozenset({
    "sibling_relationship",
    "sibling_status",
    "sibling_residence",
    "sibling_date_of_birth",
})

# Fail-closed accepted immigration-status tokens for a Canadian sibling. An
# unknown token is deliberately NOT a member, so the (35-04) decider treats it as
# non-substantiating rather than silently crediting an unearned status.
SIBLING_STATUS_ACCEPTED: frozenset[str] = frozenset({
    "citizen",
    "permanent_resident",
})

# Fail-closed accepted sibling-relationship tokens (a full/half/step sibling in
# CRS terms). Any other relationship is non-accepted (not a sibling for the grid).
SIBLING_RELATIONSHIP_ACCEPTED: frozenset[str] = frozenset({
    "brother",
    "sister",
})


def _lookup_key(raw: str) -> str:
    """Collapse a raw surface form to a stable lookup key.

    Case-fold, treat ``-`` and ``_`` as spaces, and collapse runs of whitespace
    to a single space so ``"Permanent Resident"``, ``"permanent_resident"``, and
    ``"PERMANENT  RESIDENT"`` all key to ``"permanent resident"``. The alias table
    therefore needs a single entry per accepted token regardless of the document's
    casing / spacing / joining, and normalization is idempotent on already-canonical
    input (the snake_case token collapses to the same key as its surface form).
    """
    s = raw.strip().casefold().replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", s)


# Deterministic surface-form -> canonical accepted-token maps for the two
# closed-enum sibling text fields. EVERY value is a member of the corresponding
# ``*_ACCEPTED`` frozenset above (pinned by test_siblingfields_vocab.py), and every
# accepted token maps to itself (via its collapsed key) so normalization is
# idempotent. An UNKNOWN surface form is deliberately ABSENT — ``normalize_*``
# returns the collapsed key unchanged, which is NOT an accepted member, so the
# decider fail-closes rather than crediting an unearned status / relationship.
SIBLING_STATUS_ALIASES: dict[str, str] = {
    _lookup_key("citizen"): "citizen",
    _lookup_key("canadian citizen"): "citizen",
    _lookup_key("citizen of canada"): "citizen",
    _lookup_key("permanent_resident"): "permanent_resident",
    _lookup_key("permanent resident"): "permanent_resident",
    _lookup_key("pr"): "permanent_resident",
}

SIBLING_RELATIONSHIP_ALIASES: dict[str, str] = {
    _lookup_key("brother"): "brother",
    _lookup_key("sister"): "sister",
}


def _normalize(raw: str, aliases: dict[str, str]) -> str | None:
    """Map a raw token to its canonical accepted value via *aliases* (fail-closed).

    Returns the canonical token for a known surface form, ``None`` for empty /
    ``None`` input, and the collapsed lookup key UNCHANGED for an unknown token. An
    unknown token is deliberately NOT coerced to an accepted value — it stays
    non-accepted so ``decide_sibling`` leaves the factor AT-RISK ``unresolved_sibling``
    rather than silently crediting an unearned relationship / status.
    """
    if not raw or not raw.strip():
        return None
    key = _lookup_key(raw)
    return aliases.get(key, key)


def normalize_sibling_status(raw: str) -> str | None:
    """Canonicalize a sibling immigration-status surface form (fail-closed).

    ``"Permanent Resident"`` / ``"PR"`` -> ``"permanent_resident"``,
    ``"Canadian Citizen"`` / ``"Citizen"`` -> ``"citizen"``; any unmapped token
    stays its own (non-accepted) lookup key. See :func:`_normalize`.
    """
    return _normalize(raw, SIBLING_STATUS_ALIASES)


def normalize_sibling_relationship(raw: str) -> str | None:
    """Canonicalize a sibling-relationship surface form (fail-closed).

    ``"Brother"`` -> ``"brother"``, ``"Sister"`` -> ``"sister"``; any unmapped
    token (e.g. ``"Cousin"``) stays its own (non-accepted) lookup key. See
    :func:`_normalize`.
    """
    return _normalize(raw, SIBLING_RELATIONSHIP_ALIASES)

