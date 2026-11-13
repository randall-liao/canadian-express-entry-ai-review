"""Operational DLI snapshot freshness configuration, not an IRCC claim.

The CLI boundary must convert ``None`` from this module into a refusal before
any index probe, vault open, or write. In particular, it must never call
``probe_snapshot(..., max_age_days=None)`` because that disables the staleness
check.
"""

from __future__ import annotations

import os
from datetime import date

from crawler.models.crs_rules import RuleRow

_DLI_ENV = "PR_DLI_SNAPSHOT_MAX_AGE_DAYS"
_MEC_ENV = "PR_MEC_RULE_MAX_AGE_DAYS"


def dli_snapshot_max_age_days(explicit: int | str | None = None) -> int | None:
    """Resolve the explicit-then-environment operational bound, if positive."""
    value = explicit if explicit is not None else os.environ.get(_DLI_ENV)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
    else:
        parsed = value
    return parsed if parsed > 0 else None


def mec_rule_max_age_days(explicit: int | str | None = None) -> int | None:
    """Resolve the required operational MEC row-age bound without a default."""
    value = explicit if explicit is not None else os.environ.get(_MEC_ENV)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
    else:
        parsed = value
    return parsed if parsed > 0 else None


def mec_rule_row_is_fresh(
    row: RuleRow,
    reference_date: date | str | None,
    max_age_days: int | None,
) -> bool:
    """Apply the configured operational age bound to one MEC registry row.

    This is operator policy, not a claim about the cadence of authoritative
    changes. Missing, malformed, future, or over-age crawl dates fail closed.
    """
    if (
        reference_date is None
        or isinstance(max_age_days, bool)
        or not isinstance(max_age_days, int)
        or max_age_days <= 0
        or not row.volatility.crawl_date
    ):
        return False
    try:
        reference = (
            reference_date
            if isinstance(reference_date, date)
            else date.fromisoformat(str(reference_date)[:10])
        )
        crawled = date.fromisoformat(str(row.volatility.crawl_date)[:10])
    except (TypeError, ValueError):
        return False
    age = (reference - crawled).days
    return 0 <= age <= max_age_days
