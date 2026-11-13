"""Dispatch-spine tests for the Phase-33 core module (33-01 Task 2, AUDIT-01/03).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Reuses the Plan 03
synthetic fixtures (``_AuditorCase``: a synthetic corpus index + a tmp vault under
``$PR_PERSONAL_DIR``) and a SYNTHETIC registry that cites the tiny chunk verbatim.
NO real corpus, NO real applicant data.

Proves:
  * (a) ``resolve`` returns the real core deciders; an unregistered id returns the
    fail-closed AT-RISK default (T-33-04);
  * (b) ``run_full_audit`` emits exactly one card per ``FULL_GRID_FACTORS`` entry,
    each with a verdict from the closed vocabulary (SC1);
  * (c) two overlapping full-time work periods that individually look valid but
    aggregate BELOW the claimed years surface as ``core.work`` GAP (SC5 — no
    hidden document pass, no overlap double-count);
  * (d) a self-scan ``no_inlined_volatile_rules`` over the core module is clean.
"""

from __future__ import annotations

from unittest import mock

from crawler import auditor, auditors, crs_rules
from crawler.auditors import core as core_mod
from crawler.models.crs_rules import (
    AcceptedValue,
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor
from crawler.tests.test_auditor import _TINY_ID, _TINY_QUOTE, _AuditorCase


def _row(rule_id: str, factor_id: str, mc: MachineCheck, check_type: str = "threshold",
         group: str = "core_human_capital") -> RuleRow:
    return RuleRow(
        rule_id=rule_id,
        factor_group=group,
        factor_ids=[factor_id],
        check_type=check_type,
        query="police certificates",
        selector=Selector(family="pr-pdi", marker=_TINY_QUOTE),
        claim_text="A grounded core rule.",
        citations=[Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
        machine_check=mc,
        volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi"),
    )


def _work_registry() -> Registry:
    """A grounded synthetic core.work registry (teer + hours ceiling + window)."""
    return Registry(rows=[
        _row("core.work.definition", "core.work",
             MachineCheck(kind="accepted_enum", field="teer",
                          accepted_values=[AcceptedValue(value=v) for v in
                                           ("0", "1", "2", "3")]),
             check_type="admissibility"),
        _row("core.work.hours", "core.work",
             MachineCheck(kind="threshold", field="hours_per_week", max_value=30)),
        _row("core.work.window", "core.work",
             MachineCheck(kind="validity_window", field="work_reference_period",
                          window_days=3653)),
    ])


class _DispatchCase(_AuditorCase):
    def _seed_work_vault(self, periods, *, claimed_years):
        """Seed a candidate claiming core.work with one document per work period."""
        from crawler import vault
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id="core.work", factor_group="core_human_capital",
            claimed_points=40, claimed_value=claimed_years, source="user_entry"))
        run_id_extract = None
        for i, p in enumerate(periods):
            from pathlib import Path
            src = Path(self._tmp.name) / f"work_{i}.pdf"
            src.write_bytes(b"%PDF-1.4 synthetic work letter " + str(i).encode())
            doc = vault.import_document(v, "default", src, doc_type="employment_reference_letter")
            run_id_extract = vault.record_extraction_run(
                v, document_id=doc.document_id,
                parser_version=vault.current_parser_version())
            for field, value in p.items():
                vid = vault.add_extracted_value(
                    v, document_id=doc.document_id, page_id=None,
                    factor_id="core.work", field_name=field,
                    raw_text=str(value), normalized_value=value, bbox=None,
                    extractor_confidence=0.9, quality_flag="ok",
                    extraction_run_id=run_id_extract)
                vault.confirm_value(
                    v,
                    vid,
                    "confirm",
                    registry_fingerprint=crs_rules.registry_fingerprint(
                        _work_registry()),
                )
        return v


class TestResolve(_DispatchCase):
    def test_core_deciders_registered(self) -> None:
        auditors.load_all()
        self.assertIs(auditors.resolve("core.age"), core_mod.decide_age)
        self.assertIs(auditors.resolve("core.education"), core_mod.decide_education)
        self.assertIs(auditors.resolve("core.work"), core_mod.decide_work)
        self.assertIs(auditors.resolve("core.language.first"),
                      core_mod.decide_first_language)

    def test_unregistered_factor_is_at_risk_default(self) -> None:
        auditors.load_all()
        decider = auditors.resolve("core.not.a.real.factor")
        self.assertIs(decider, auditors._default_decider)
        # And its verdict is fail-closed AT-RISK, never SUBSTANTIATED.
        from crawler.auditors import DecisionContext
        ctx = DecisionContext(
            factor_id="x", factor=None, by_field={}, registry=Registry(rows=[]),
            consumed=Registry(rows=[]), spouse_mode=False, reference_date="2025-01-01")
        result = decider(ctx)
        self.assertEqual(result.verdict, "AT-RISK")
        self.assertNotEqual(result.verdict, "SUBSTANTIATED")


class TestFullGridOneVerdictPerFactor(_DispatchCase):
    def test_run_full_audit_one_card_per_grid_factor(self) -> None:
        v = self._seed_work_vault(
            [{"employment_start": "2020-01-01", "employment_end": "2021-12-31",
              "hours_per_week": 40, "teer": "1"}],
            claimed_years=1.0)
        try:
            report = auditor.run_full_audit(v, self.db, _work_registry())
        finally:
            v.con.close()
        ids = [c.factor_id for c in report.factor_cards]
        # Exactly one card per grid factor: no missing, no duplicate.
        self.assertEqual(sorted(ids), sorted(auditors.FULL_GRID_FACTORS))
        self.assertEqual(len(ids), len(set(ids)))
        for card in report.factor_cards:
            self.assertIn(card.verdict, {"SUBSTANTIATED", "GAP", "AT-RISK", "N/A"})

    def test_full_grid_computes_and_threads_one_registry_fingerprint(self) -> None:
        registry = _work_registry()
        expected = crs_rules.registry_fingerprint(registry)
        v = self._seed_work_vault([], claimed_years=1.0)
        seen: list[str | None] = []
        from crawler import vault
        real_eligible = vault.audit_eligible_values

        def eligible(vault_, factor_id, *, registry_fingerprint=None):
            seen.append(registry_fingerprint)
            return real_eligible(
                vault_,
                factor_id,
                registry_fingerprint=registry_fingerprint,
            )

        try:
            with (
                mock.patch(
                    "crawler.crs_rules.registry_fingerprint",
                    wraps=crs_rules.registry_fingerprint,
                ) as fingerprint,
                mock.patch(
                    "crawler.vault.audit_eligible_values",
                    side_effect=eligible,
                ),
            ):
                report = auditor.run_full_audit(v, self.db, registry)
        finally:
            v.con.close()
        self.assertEqual(fingerprint.call_count, 1)
        self.assertTrue(seen)
        self.assertEqual(set(seen), {expected})
        self.assertEqual(report.registry_fingerprint, expected)


class TestWorkAggregationGap(_DispatchCase):
    def test_overlapping_periods_aggregate_below_claim_is_gap(self) -> None:
        # Two overlapping full-time spans; the naive SUM (~3.08y) would meet the
        # claim, but the UNION (2.0y, no double-count) does not → GAP (SC5).
        periods = [
            {"employment_start": "2020-01-01", "employment_end": "2021-06-30",
             "hours_per_week": 40, "teer": "1"},
            {"employment_start": "2020-06-01", "employment_end": "2021-12-31",
             "hours_per_week": 40, "teer": "1"},
        ]
        v = self._seed_work_vault(periods, claimed_years=3.0)
        try:
            card = auditor.audit_one(
                v, "core.work", self.db, _work_registry(),
                spouse_mode=False, reference_date="2022-01-01", prior_cards={})
        finally:
            v.con.close()
        self.assertEqual(card.verdict, "GAP")
        self.assertEqual(card.reason_code, "below_threshold")


class TestNoInlinedRules(_DispatchCase):
    def test_core_module_has_no_inlined_volatile_rules(self) -> None:
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([core_mod.__file__]), [])


if __name__ == "__main__":  # pragma: no cover
    import unittest
    unittest.main()
