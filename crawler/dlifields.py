"""Closed Canadian-study evidence vocabulary and fail-closed normalizers.

This module is extraction-only.  It defines private field names and canonical
tokens, but contains no CRS scoring, freshness, eligibility, or legal logic.
"""

from __future__ import annotations

import re
import unicodedata


STUDY_FIELDS: frozenset[str] = frozenset({
    "institution_name",
    "dli_number",
    "credential_level",
    "program_start",
    "program_end",
    "study_status",
})

CREDENTIAL_TIERS_ACCEPTED: frozenset[str] = frozenset({"1-2", "3+"})

STUDY_STATUSES_ACCEPTED: frozenset[str] = frozenset({
    "completed",
    "graduated",
    "enrolled",
    "withdrawn",
})


def _lookup_key(raw: str) -> str:
    """Return a stable alias lookup key without inferring an unknown value."""
    value = unicodedata.normalize("NFC", raw)
    value = value.strip().casefold().replace("_", " ").replace("-", " ")
    value = value.replace("’", "'")
    return re.sub(r"\s+", " ", value)


CREDENTIAL_TIER_ALIASES: dict[str, str] = {
    _lookup_key("1-2"): "1-2",
    _lookup_key("one-year certificate"): "1-2",
    _lookup_key("one year certificate"): "1-2",
    _lookup_key("one-year diploma"): "1-2",
    _lookup_key("one year diploma"): "1-2",
    _lookup_key("two-year certificate"): "1-2",
    _lookup_key("two year certificate"): "1-2",
    _lookup_key("two-year diploma"): "1-2",
    _lookup_key("two year diploma"): "1-2",
    _lookup_key("3+"): "3+",
    _lookup_key("bachelor's degree"): "3+",
    _lookup_key("bachelor degree"): "3+",
    _lookup_key("three-year diploma"): "3+",
    _lookup_key("three year diploma"): "3+",
    _lookup_key("three-year degree"): "3+",
    _lookup_key("three year degree"): "3+",
    _lookup_key("master's degree"): "3+",
    _lookup_key("master degree"): "3+",
    _lookup_key("doctoral degree"): "3+",
    _lookup_key("doctorate"): "3+",
    _lookup_key("phd"): "3+",
    _lookup_key("professional degree"): "3+",
}

STUDY_STATUS_ALIASES: dict[str, str] = {
    _lookup_key("completed"): "completed",
    _lookup_key("complete"): "completed",
    _lookup_key("graduated"): "graduated",
    _lookup_key("graduate"): "graduated",
    _lookup_key("enrolled"): "enrolled",
    _lookup_key("currently enrolled"): "enrolled",
    _lookup_key("withdrawn"): "withdrawn",
    _lookup_key("withdrew"): "withdrawn",
}


def normalize_dli(raw: object) -> str | None:
    """Normalize an exact DLI identifier, returning ``None`` for any other form."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = unicodedata.normalize("NFC", raw).strip().upper()
    value = re.sub(r"\s+", "", value)
    return value if re.fullmatch(r"O\d{6,}", value) else None


def _normalize_alias(raw: str, aliases: dict[str, str]) -> str | None:
    """Map a known alias; preserve unknown keys outside the accepted vocabulary."""
    if not raw or not raw.strip():
        return None
    key = _lookup_key(raw)
    return aliases.get(key, key)


def normalize_credential_level(raw: str) -> str | None:
    """Canonicalize a credential label to a closed study tier."""
    return _normalize_alias(raw, CREDENTIAL_TIER_ALIASES)


def normalize_study_status(raw: str) -> str | None:
    """Canonicalize a study-status label to a closed status token."""
    return _normalize_alias(raw, STUDY_STATUS_ALIASES)
