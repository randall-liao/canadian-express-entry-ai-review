"""SAFE-09 freshness / effective-date negative-control tests (Phase 40 — Plan 01).

These prove the additive fail-closed freshness API — :func:`crawler.crs_audit.within_freshness`
and :func:`crawler.crs_audit.row_in_effect` — that ships BESIDE the frozen
``within_validity`` / ``_in_window`` primitives without wiring into any decider.

Every bound is read from a SYNTHETIC grounded ``validity_window`` row (never an
inlined literal — a self-scan re-asserts the module stays clean), exactly the way
``test_crs_audit._validity_registry`` proves ``within_validity``. There is NO real
corpus, NO real registry file, and NO dependency on the not-yet-existent DLI corpus
family (the concrete grounded DLI snapshot max-age value + its authoritative citation
are a Phase 41 / STUDY-01 data responsibility — see ``_freshness_registry``).

The tests are NEGATIVE controls (out-of-window / stale / after-reference / no-window /
outside-either-effective-window), not just current-dated fixtures, because a helper
that quietly greened a stale or out-of-window value is the milestone's dominant
false-green risk (threat T-40-01).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from crawler import crs_audit, crs_rules, snapshot_policy
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)

_CIT = Citation(chunk_id="guidance/crs-criteria.md#000", quote="x")


def _row(rule_id, group, check_type, mc, factor_ids=None, **vol):
    """Synthetic grounded RuleRow builder (mirrors ``test_crs_audit._row``).

    ``**vol`` carries the VolatilityMeta window (``effective_from`` / ``effective_to``)
    — the SECOND effective-window source ``row_in_effect`` composes over — plus an
    optional ``volatility`` marker and ``gap`` flag.
    """
    return RuleRow(
        rule_id=rule_id,
        factor_group=group,
        factor_ids=factor_ids or [rule_id],
        check_type=check_type,
        query="q",
        selector=Selector(family="guidance"),
        claim_text="synthetic grounded rule",
        citations=[_CIT],
        machine_check=mc,
        volatility=VolatilityMeta(
            volatility=vol.get("volatility", "volatile"),
            source_family="guidance",
            effective_from=vol.get("effective_from"),
            effective_to=vol.get("effective_to"),
        ),
        gap=vol.get("gap", False),
    )


def _freshness_registry() -> Registry:
    """One SYNTHETIC grounded snapshot max-age window row.

    Mirrors ``test_crs_audit._validity_registry``: a single ``validity_window``
    ``MachineCheck`` whose ``field`` is the frozen ``snapshot_max_age`` field-name
    contract Phase 41's real grounded DLI row will populate. The window length here
    (a synthetic bound) is what ``within_freshness`` reads via ``_window_days`` — the
    helper never inlines it. No authoritative DLI max-age is groundable in the current
    corpus, so no bound row is shipped to ``crawler/data/crs_rules/`` this phase; the
    MECHANISM is proven with this synthetic grounded fixture instead.
    """
    snap = _row(
        "safe.dli_snapshot.max_age",
        "core_human_capital",
        "threshold",
        MachineCheck(kind="validity_window", field="snapshot_max_age", window_days=180),
    )
    return Registry(rows=[snap])


class TestWithinFreshness(unittest.TestCase):
    """within_freshness reads a GROUNDED window and fails closed off the happy path."""

    def test_in_window_crawl_is_fresh(self) -> None:
        reg = _freshness_registry()
        # delta 0 (crawl == reference) is strictly in-window → fresh.
        self.assertTrue(
            crs_audit.within_freshness("dli_snapshot", "2026-07-06", "2026-07-06", reg)
        )
        # a crawl just inside the grounded window is still fresh.
        self.assertTrue(
            crs_audit.within_freshness("dli_snapshot", "2026-01-08", "2026-07-06", reg)
        )

    def test_stale_crawl_is_not_fresh(self) -> None:
        reg = _freshness_registry()
        # a crawl OLDER than the grounded window (delta > window_days) is stale → False.
        self.assertFalse(
            crs_audit.within_freshness("dli_snapshot", "2025-01-01", "2026-07-06", reg)
        )

    def test_crawl_after_reference_is_not_fresh(self) -> None:
        reg = _freshness_registry()
        # a crawl AFTER the reference date (delta < 0) → False (future / after-reference).
        self.assertFalse(
            crs_audit.within_freshness("dli_snapshot", "2026-07-07", "2026-07-06", reg)
        )

    def test_no_grounded_window_fails_closed(self) -> None:
        # an EMPTY registry carries no grounded snapshot_max_age window → fail-closed False.
        self.assertFalse(
            crs_audit.within_freshness(
                "dli_snapshot", "2026-07-06", "2026-07-06", Registry(rows=[])
            )
        )

    def test_unknown_kind_without_window_fails_closed(self) -> None:
        # an unmapped kind falls through to its own field name; absent a grounded
        # window for it, the result is still fail-closed False.
        self.assertFalse(
            crs_audit.within_freshness(
                "lico_snapshot", "2026-07-06", "2026-07-06", _freshness_registry()
            )
        )


class TestDliSnapshotMaxAgeConfig(unittest.TestCase):
    """Operational max-age resolution is explicit-first and fails closed."""

    def test_explicit_value_wins_over_environment(self) -> None:
        with patch.dict(
            "os.environ",
            {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "90"},
            clear=True,
        ):
            self.assertEqual(snapshot_policy.dli_snapshot_max_age_days(30), 30)

    def test_environment_is_used_when_explicit_is_absent(self) -> None:
        with patch.dict(
            "os.environ",
            {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "90"},
            clear=True,
        ):
            self.assertEqual(snapshot_policy.dli_snapshot_max_age_days(), 90)

    def test_absent_config_has_no_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(snapshot_policy.dli_snapshot_max_age_days())

    def test_invalid_explicit_values_fail_closed_without_env_fallback(self) -> None:
        invalid = ("not-an-integer", " ", 0, -1, True, False)
        for value in invalid:
            with self.subTest(value=value), patch.dict(
                "os.environ",
                {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "90"},
                clear=True,
            ):
                self.assertIsNone(snapshot_policy.dli_snapshot_max_age_days(value))

    def test_invalid_environment_values_fail_closed(self) -> None:
        invalid = ("not-an-integer", " ", "0", "-1")
        for value in invalid:
            with self.subTest(value=value), patch.dict(
                "os.environ",
                {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": value},
                clear=True,
            ):
                self.assertIsNone(snapshot_policy.dli_snapshot_max_age_days())

    def test_positive_integer_strings_resolve(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(snapshot_policy.dli_snapshot_max_age_days("30"), 30)


class TestRowInEffect(unittest.TestCase):
    """row_in_effect composes _in_window over BOTH grounded window sources."""

    def test_out_of_machine_check_window_not_in_effect(self) -> None:
        # machine_check effective window [effective_from, effective_to) — the FIRST source.
        row = _row(
            "policy.dated.mc",
            "additional_points",
            "policy",
            MachineCheck(
                kind="policy_flag",
                field="job_offer",
                flag_value=False,
                effective_from="2025-01-01",
                effective_to="2025-06-01",
            ),
        )
        # ref BEFORE effective_from → not in effect.
        self.assertFalse(crs_audit.row_in_effect(row, "2024-12-31"))
        # ref >= effective_to (half-open) → not in effect.
        self.assertFalse(crs_audit.row_in_effect(row, "2025-06-01"))
        # ref inside the window → in effect.
        self.assertTrue(crs_audit.row_in_effect(row, "2025-03-01"))

    def test_out_of_volatility_window_not_in_effect(self) -> None:
        # the SECOND source: volatility.effective_from/to (passed via **vol on _row).
        row = _row(
            "policy.dated.vol",
            "additional_points",
            "policy",
            MachineCheck(kind="policy_flag", field="job_offer", flag_value=False),
            effective_from="2025-01-01",
            effective_to="2025-06-01",
        )
        self.assertFalse(crs_audit.row_in_effect(row, "2024-06-01"))
        self.assertFalse(crs_audit.row_in_effect(row, "2025-06-01"))
        self.assertTrue(crs_audit.row_in_effect(row, "2025-03-01"))

    def test_row_with_no_windows_is_in_effect(self) -> None:
        # a row whose windows are BOTH None is stable/effective → True.
        row = _row(
            "stable.definition",
            "core_human_capital",
            "threshold",
            MachineCheck(kind="accepted_enum", field="doc_type"),
        )
        self.assertTrue(crs_audit.row_in_effect(row, "2026-07-06"))


class TestNewFreshnessHelpersNoInline(unittest.TestCase):
    """Re-prove the static self-scan over the MODIFIED crs_audit module."""

    def test_crs_audit_freshness_helpers_have_no_inlined_rule(self) -> None:
        # within_freshness / row_in_effect / _FRESHNESS_FIELD introduce NO inlined
        # window/age literal — every bound is read from a grounded row via _window_days.
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules(["crawler/crs_audit.py"]), []
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
