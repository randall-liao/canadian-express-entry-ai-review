"""Canonical language ``test_type`` vocabulary — the ONE source of truth shared by
Phase-30 extraction and pinned to the Phase-31 registry accepted-enum.

Why this module exists (BLOCKER B): the extractor used to emit bare tokens
(``IELTS`` / ``CELPIP``) while the grounded registry accepted-enum + conversion
tables key on the full IRCC spellings (``IELTS General Training`` /
``CELPIP-General``). That mismatch GAP-ed a genuinely-qualified applicant as
``unaccepted_test_type`` at the extraction->registry seam even though every phase
passed in isolation. Centralizing the vocabulary here — and pinning it to the
registry with an anti-drift test (``test_testtype_vocab.py``) — makes the two
sides provably agree and prevents silent re-divergence.

Scope discipline: this module carries test NAMES only. It contains NO CRS points,
levels, benchmarks, or caps, so it stays OUTSIDE the ``no_inlined_volatile_rules``
surface (the volatile scoring numbers still live exclusively in the grounded
registry). Pure stdlib — no runtime dependencies.
"""

from __future__ import annotations

import re

# The five registry-accepted language test types (IRCC canonical spellings).
# This set is asserted EQUAL to the registry ``test_type`` accepted-enum by
# ``crawler/tests/test_testtype_vocab.py`` — drift in either direction fails.
CANONICAL_TEST_TYPES: frozenset[str] = frozenset({
    "CELPIP-General",
    "IELTS General Training",
    "PTE Core",
    "TEF Canada",
    "TCF Canada",
})


def _lookup_key(raw: str) -> str:
    """Build a stable lookup key: lowercase, hyphen->space, collapse whitespace.

    ``CELPIP-General`` and ``celpip   general`` both collapse to ``celpip general``
    so the alias table needs only one entry per test regardless of casing/spacing.
    """
    s = raw.strip().lower().replace("-", " ")
    return re.sub(r"\s+", " ", s)


# Every raw extractor token AND every canonical spelling maps (via its collapsed
# lookup key) to its canonical registry value. Bare exam abbreviations (the tokens
# the extractor's ``_TEST_TYPE_RE`` captures) and the full spellings are both
# covered so ``normalize_test_type`` is idempotent on already-canonical input.
TEST_TYPE_ALIASES: dict[str, str] = {
    _lookup_key("IELTS"): "IELTS General Training",
    _lookup_key("IELTS General Training"): "IELTS General Training",
    _lookup_key("CELPIP"): "CELPIP-General",
    _lookup_key("CELPIP-General"): "CELPIP-General",
    _lookup_key("PTE"): "PTE Core",
    _lookup_key("PTE Core"): "PTE Core",
    _lookup_key("TEF"): "TEF Canada",
    _lookup_key("TEF Canada"): "TEF Canada",
    _lookup_key("TCF"): "TCF Canada",
    _lookup_key("TCF Canada"): "TCF Canada",
}


def normalize_test_type(raw: str) -> str | None:
    """Map a raw test-type token to its canonical registry value (fail-closed).

    Returns the canonical accepted spelling for a known token/spelling, ``None``
    for empty/``None`` input, and the collapsed lookup key UNCHANGED for an unknown
    token. An unknown token is deliberately NOT coerced to an accepted value — it
    stays non-accepted so the untouched language decider GAP-s it
    ``unaccepted_test_type`` rather than silently crediting an unearned test.
    """
    if not raw or not raw.strip():
        return None
    key = _lookup_key(raw)
    return TEST_TYPE_ALIASES.get(key, key)
