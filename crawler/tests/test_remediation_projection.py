"""Projection conformance for the remediation layer (REM-03; Phase-39 SAFE-07 fwd-guard).

Proves remediation is a single-trust-path, retrieve-what-you-cite, deterministic
projection: it never imports/calls searchindex or grounding, every citation+quote it
emits derives from a real registry row, and the projection is stable. Stdlib unittest.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from crawler import auditors, crs_rules, remediation
from crawler.models.audit import PrivateAuditReport, PrivateFactorCard

_MODULE = Path(remediation.__file__)


def _cites(registry, factor_id, n=2):
    wanted = set(auditors.consumed_factor_ids(factor_id))
    ids: list[str] = []
    for row in registry.rows:
        if wanted.intersection(row.factor_ids):
            for c in row.citations:
                if c.chunk_id not in ids:
                    ids.append(c.chunk_id)
    return ids[:n]


def _report(registry):
    return PrivateAuditReport(
        run_id="aud_proj", candidate_id="c",
        factor_cards=[
            PrivateFactorCard(
                factor_id="core.language.first",
                factor_group="core_human_capital", verdict="GAP",
                reason_code="missing_evidence",
                rule_citation_ids=_cites(registry, "core.language.first")),
            PrivateFactorCard(
                factor_id="additional.sibling",
                factor_group="additional_points", verdict="AT-RISK",
                reason_code="unresolved_sibling",
                rule_citation_ids=_cites(registry, "additional.sibling")),
        ])


class NoSecondTrustPath(unittest.TestCase):
    def test_no_searchindex_or_grounding_import(self) -> None:
        # AST-scoped: inspect ONLY import statements (not comments/docstrings, which
        # legitimately mention 'grounding'/'re-grounding'/'searchindex').
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
                imported.extend(a.name for a in node.names)
        for name in imported:
            self.assertNotIn("searchindex", name)
            self.assertNotIn("grounding", name)

    def test_build_remediation_never_calls_trust_path(self) -> None:
        # Call-level guard: even with the trust path booby-trapped, build succeeds.
        from crawler import grounding, searchindex
        registry = crs_rules.load_registry()
        report = _report(registry)

        def _boom(*_a, **_k):
            raise AssertionError("trust path must not be called by remediation")

        orig = (grounding.check_answer, searchindex.search, searchindex.resolve)
        grounding.check_answer = _boom
        searchindex.search = _boom
        searchindex.resolve = _boom
        try:
            checklist = remediation.build_remediation(report, registry)
            self.assertEqual(len(checklist.items), 2)
        finally:
            (grounding.check_answer, searchindex.search,
             searchindex.resolve) = orig


class RetrieveWhatYouCite(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = crs_rules.load_registry()

    def test_every_citation_quote_is_a_real_registry_pair(self) -> None:
        checklist = remediation.build_remediation(_report(self.registry), self.registry)
        registry_pairs = {
            (c.chunk_id, c.quote)
            for row in self.registry.rows for c in row.citations}
        emitted = 0
        for item in checklist.items:
            for cit in item.citations:
                self.assertIn((cit.citation_id, cit.quote), registry_pairs)
                emitted += 1
        self.assertGreater(emitted, 0, "expected at least one grounded citation")

    def test_determinism_against_real_registry(self) -> None:
        report = _report(self.registry)
        a = remediation.build_remediation(report, self.registry)
        b = remediation.build_remediation(report, self.registry)
        self.assertEqual(a.model_dump(), b.model_dump())


class UnpricedInvariant(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = crs_rules.load_registry()

    def test_unpriced_substantiated_yields_exactly_one_item(self) -> None:
        card = PrivateFactorCard(
            factor_id="core.age", factor_group="core_human_capital",
            verdict="SUBSTANTIATED", reason_code="grounded_substantiated",
            substantiated_points=None, points_unresolved=True,
            rule_citation_ids=_cites(self.registry, "core.age"))
        report = PrivateAuditReport(
            run_id="aud_u", candidate_id="c", factor_cards=[card])
        checklist = remediation.build_remediation(report, self.registry)
        self.assertEqual(len(checklist.items), 1)
        self.assertEqual(checklist.items[0].finding_kind, "unpriced")

    def test_substantiated_without_flag_and_with_points_yields_no_item(self) -> None:
        # A genuinely priced SUBSTANTIATED card (points set, flag False) is resolved
        # -> NOT a finding (the two surfaces agree: no unpriced item).
        card = PrivateFactorCard(
            factor_id="core.age", factor_group="core_human_capital",
            verdict="SUBSTANTIATED", reason_code="grounded_substantiated",
            substantiated_points=100, points_unresolved=False,
            rule_citation_ids=_cites(self.registry, "core.age"))
        report = PrivateAuditReport(
            run_id="aud_p", candidate_id="c", factor_cards=[card])
        checklist = remediation.build_remediation(report, self.registry)
        self.assertEqual(checklist.items, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
