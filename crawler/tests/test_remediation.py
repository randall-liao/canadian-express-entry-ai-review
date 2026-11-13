"""Projection + determinism proof for the remediation layer (REM-01/02/03).

Builds synthetic PrivateAuditReports and asserts build_remediation projects exactly
one item per unresolved finding, with correct fields, deterministically, using the
REAL registry so quotes resolve fail-closed. Stdlib unittest ONLY.
"""

from __future__ import annotations

import unittest

from crawler import crs_rules, remediation
from crawler.models.audit import PrivateAuditReport, PrivateFactorCard


def _registry():
    return crs_rules.load_registry()


def _cites_for(registry, factor_id, n=2):
    """A few real citation ids for a factor (so quotes resolve fail-closed)."""
    ids: list[str] = []
    wanted = set()
    from crawler import auditors
    wanted.update(auditors.consumed_factor_ids(factor_id))
    for row in registry.rows:
        if wanted.intersection(row.factor_ids):
            for c in row.citations:
                if c.chunk_id not in ids:
                    ids.append(c.chunk_id)
    return ids[:n]


def _report(registry) -> PrivateAuditReport:
    gap = PrivateFactorCard(
        factor_id="core.language.first", factor_group="core_human_capital",
        verdict="GAP", reason_code="missing_evidence",
        rule_citation_ids=_cites_for(registry, "core.language.first"),
        evidence_ids=["ev_aaa111"])
    at_risk = PrivateFactorCard(
        factor_id="additional.sibling", factor_group="additional_points",
        verdict="AT-RISK", reason_code="unresolved_sibling",
        rule_citation_ids=_cites_for(registry, "additional.sibling"),
        evidence_ids=["ev_bbb222"])
    unpriced = PrivateFactorCard(
        factor_id="core.age", factor_group="core_human_capital",
        verdict="SUBSTANTIATED", reason_code="grounded_substantiated",
        substantiated_points=None, points_unresolved=True,
        rule_citation_ids=_cites_for(registry, "core.age"))
    priced = PrivateFactorCard(
        factor_id="core.education", factor_group="core_human_capital",
        verdict="SUBSTANTIATED", reason_code="grounded_substantiated",
        substantiated_points=120, points_unresolved=False,
        rule_citation_ids=_cites_for(registry, "core.education"))
    na = PrivateFactorCard(
        factor_id="spouse.education", factor_group="spouse_common_law",
        verdict="N/A", reason_code="not_applicable")
    return PrivateAuditReport(
        run_id="aud_deadbeef0005", candidate_id="cand-x",
        factor_cards=[gap, at_risk, unpriced, priced, na])


class BuildRemediationProjection(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = _registry()
        self.report = _report(self.registry)

    def test_exactly_one_item_per_unresolved_finding(self) -> None:
        checklist = remediation.build_remediation(self.report, self.registry)
        self.assertEqual(len(checklist.items), 3)
        by_factor = {i.factor_id: i for i in checklist.items}
        self.assertEqual(set(by_factor), {
            "core.language.first", "additional.sibling", "core.age"})
        # priced SUBSTANTIATED + N/A produced NO item
        self.assertNotIn("core.education", by_factor)
        self.assertNotIn("spouse.education", by_factor)

    def test_finding_kinds_are_correct(self) -> None:
        checklist = remediation.build_remediation(self.report, self.registry)
        kinds = {i.factor_id: i.finding_kind for i in checklist.items}
        self.assertEqual(kinds["core.language.first"], "gap")
        self.assertEqual(kinds["additional.sibling"], "at_risk")
        self.assertEqual(kinds["core.age"], "unpriced")

    def test_item_fields_and_action_mentions_factor(self) -> None:
        checklist = remediation.build_remediation(self.report, self.registry)
        item = next(i for i in checklist.items if i.factor_id == "core.language.first")
        self.assertEqual(item.verdict, "GAP")
        self.assertEqual(item.reason_code, "missing_evidence")
        self.assertEqual(item.evidence_ids, ["ev_aaa111"])
        self.assertIn("core.language.first", item.action)
        self.assertTrue(item.action)

    def test_citations_pair_with_verbatim_registry_quote(self) -> None:
        checklist = remediation.build_remediation(self.report, self.registry)
        # A (chunk_id, quote) pair is valid iff SOME registry row cites that chunk
        # with that exact verbatim quote (a chunk may be cited with different spans
        # by different rules — remediation reuses a real grounded one, never invents).
        registry_pairs = {
            (c.chunk_id, c.quote)
            for row in self.registry.rows for c in row.citations}
        for item in checklist.items:
            for cit in item.citations:
                self.assertIn((cit.citation_id, cit.quote), registry_pairs)

    def test_determinism(self) -> None:
        a = remediation.build_remediation(self.report, self.registry)
        b = remediation.build_remediation(self.report, self.registry)
        self.assertEqual(a.model_dump(), b.model_dump())

    def test_public_summary_is_pii_light(self) -> None:
        checklist = remediation.build_remediation(self.report, self.registry)
        summary = remediation.to_public_summary(
            checklist,
            "output/remediation/rem_deadbeef0005.json",
            run_id="rem_deadbeef0005",
        )
        dumped = summary.model_dump()
        blob = str(dumped)
        self.assertNotIn("ev_", blob)          # no evidence pointer
        self.assertNotIn("cand-x", blob)       # candidate id is not surfaced here
        self.assertEqual(dumped["item_count"], 3)
        self.assertEqual(dumped["counts"]["gap"], 1)
        self.assertEqual(dumped["counts"]["at_risk"], 1)
        self.assertEqual(dumped["counts"]["unpriced"], 1)

    def test_fail_closed_on_registry_drift(self) -> None:
        # A card citing an id absent from the registry -> RemediationError (never an
        # item with a missing/invented quote).
        drifted = PrivateFactorCard(
            factor_id="core.age", factor_group="core_human_capital",
            verdict="GAP", reason_code="missing_evidence",
            rule_citation_ids=["nonexistent/doc.md#999"])
        report = PrivateAuditReport(
            run_id="aud_drift", candidate_id="c", factor_cards=[drifted])
        with self.assertRaises(remediation.RemediationError):
            remediation.build_remediation(report, self.registry)

    def test_render_carries_screening_notice(self) -> None:
        checklist = remediation.build_remediation(self.report, self.registry)
        md = remediation.render_remediation_markdown(checklist)
        self.assertIn("Substantiation screening", md)
        self.assertIn("not legal", md.lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
