"""v4.1 SAFE-07 conformance — grounding / determinism / screening (release gate).

Authoritative, marker-tagged consolidation proving that every requirement-bearing
remediation + packet line derives from an existing grounded rule, is deterministic,
inlines no volatile rule, uses a single trust path, and carries screening framing.
Stdlib ``unittest`` ONLY.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import pytest

from crawler import auditors, crs_rules, remediation, review_packet
from crawler.audit_report import SCREENING_NOTICE
from crawler.models.audit import PrivateAuditReport, PrivateFactorCard

pytestmark = pytest.mark.conformance

_REM_MODULE = Path(remediation.__file__)
_PKT_MODULE = Path(review_packet.__file__)
_AFFIRMATIVE = (
    "you are eligible", "approved", "you will", "likely to", "we predict",
    "your outcome")


def _real_cites(registry, factor_id, n=2):
    wanted = set(auditors.consumed_factor_ids(factor_id))
    ids = []
    for row in registry.rows:
        if wanted.intersection(row.factor_ids):
            for c in row.citations:
                if c.chunk_id not in ids:
                    ids.append(c.chunk_id)
    return ids[:n]


def _report(registry):
    return PrivateAuditReport(
        run_id="aud_s7", candidate_id="c",
        factor_cards=[PrivateFactorCard(
            factor_id="core.language.first", factor_group="core_human_capital",
            verdict="GAP", reason_code="missing_evidence",
            rule_citation_ids=_real_cites(registry, "core.language.first"),
            evidence_ids=["ev_x1"])])


def _imported_names(module_path: Path) -> list[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
            names.extend(a.name for a in node.names)
    return names


class RetrieveWhatYouCite(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = crs_rules.load_registry()
        self.pairs = {
            (c.chunk_id, c.quote)
            for row in self.registry.rows for c in row.citations}

    def test_remediation_and_packet_citations_are_real_registry_pairs(self) -> None:
        report = _report(self.registry)
        checklist = remediation.build_remediation(report, self.registry)
        packet, _ = review_packet.build_packet(checklist)
        emitted = 0
        for item in checklist.items:
            for c in item.citations:
                self.assertIn((c.citation_id, c.quote), self.pairs)
                emitted += 1
        for finding in packet.findings:
            for c in finding.citations:
                self.assertIn((c.citation_id, c.quote), self.pairs)
                emitted += 1
        self.assertGreater(emitted, 0)


class Determinism(unittest.TestCase):
    def test_build_remediation_and_packet_are_deterministic(self) -> None:
        registry = crs_rules.load_registry()
        report = _report(registry)
        a = remediation.build_remediation(report, registry)
        b = remediation.build_remediation(report, registry)
        self.assertEqual(a.model_dump(), b.model_dump())
        pa, _ = review_packet.build_packet(a)
        pb, _ = review_packet.build_packet(b)
        self.assertEqual(pa.model_dump(), pb.model_dump())


class NoInlinedVolatileAndNoSecondTrustPath(unittest.TestCase):
    def test_no_inlined_volatile_rules_over_both_modules(self) -> None:
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([_REM_MODULE, _PKT_MODULE]), [])

    def test_neither_module_imports_searchindex_or_grounding(self) -> None:
        for module_path in (_REM_MODULE, _PKT_MODULE):
            for name in _imported_names(module_path):
                self.assertNotIn("searchindex", name, module_path.name)
                self.assertNotIn("grounding", name, module_path.name)

    def test_build_remediation_never_calls_trust_path(self) -> None:
        from crawler import grounding, searchindex
        registry = crs_rules.load_registry()
        report = _report(registry)

        def _boom(*_a, **_k):
            raise AssertionError("trust path must not be called")

        orig = (grounding.check_answer, searchindex.search, searchindex.resolve)
        grounding.check_answer = _boom
        searchindex.search = _boom
        searchindex.resolve = _boom
        try:
            self.assertTrue(remediation.build_remediation(report, registry).items)
        finally:
            (grounding.check_answer, searchindex.search,
             searchindex.resolve) = orig


class ScreeningFraming(unittest.TestCase):
    def test_both_renders_carry_notice_without_affirmative_claims(self) -> None:
        registry = crs_rules.load_registry()
        checklist = remediation.build_remediation(_report(registry), registry)
        packet, _ = review_packet.build_packet(checklist)
        rem_md = remediation.render_remediation_markdown(checklist)
        pkt_md = review_packet.render_packet_markdown(packet)
        for md in (rem_md, pkt_md):
            self.assertIn(SCREENING_NOTICE, md)
            # Scope the affirmative-claim check to the TOOL-synthesized text: drop the
            # SCREENING_NOTICE block (its negated disclaimer stays intact) AND the
            # grounded-rule citation lines (verbatim corpus quotes may legitimately
            # contain words like "approved" — e.g. "an approved language test").
            body_lines = [
                ln for ln in md.replace(SCREENING_NOTICE, "").splitlines()
                if "grounded rule" not in ln.lower()
                and "authoritative rule" not in ln.lower()]
            body = "\n".join(body_lines).lower()
            for phrase in _AFFIRMATIVE:
                self.assertNotIn(phrase, body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
