"""Conformance for the redacted review packet (PKT-02/03; Phase-39 SAFE-06/07 fwd-guard).

Proves the packet is a structurally-safe, single-trust-path, retrieve-what-you-cite
redacted projection with a non-vacuous render-then-scan gate. Stdlib unittest ONLY.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from pydantic import ValidationError

from crawler import auditors, crs_rules, review_packet
from crawler.remediation import (
    PrivateRemediationChecklist,
    PrivateRemediationItem,
    RemediationCitation,
)

_MODULE = Path(review_packet.__file__)


def _real_citation(registry, factor_id):
    wanted = set(auditors.consumed_factor_ids(factor_id))
    for row in registry.rows:
        if wanted.intersection(row.factor_ids) and row.citations:
            return RemediationCitation(
                citation_id=row.citations[0].chunk_id, quote=row.citations[0].quote)
    raise AssertionError(f"no registry citation for {factor_id}")


def _checklist(registry):
    return PrivateRemediationChecklist(
        source_audit_run_id="aud_c", candidate_id="c",
        items=[PrivateRemediationItem(
            factor_id="core.language.first", factor_group="core_human_capital",
            verdict="GAP", reason_code="missing_evidence", finding_kind="gap",
            score_delta=124, evidence_ids=["ev_leak123"],
            citations=[_real_citation(registry, "core.language.first")],
            action="Do the thing for core.language.first.")])


class StructuralFirewall(unittest.TestCase):
    def test_models_reject_injected_pii_keys(self) -> None:
        base = dict(factor_id="core.age", verdict="GAP", finding_kind="gap", action="x")
        for bad in ({"raw_value": "X"}, {"evidence_id": "ev_x"},
                    {"absolute_path": "/x"}, {"claimed_value": "secret"}):
            with self.assertRaises(ValidationError):
                review_packet.PacketFinding(**base, **bad)
        with self.assertRaises(ValidationError):
            review_packet.PacketCitation(citation_id="ev_abc", quote="q")

    def test_packet_dump_carries_no_ev_or_abspath(self) -> None:
        registry = crs_rules.load_registry()
        packet, _ = review_packet.build_packet(_checklist(registry))
        blob = packet.model_dump_json()
        self.assertNotIn("ev_leak123", blob)
        self.assertNotIn("ev_", blob)
        md = review_packet.render_packet_markdown(packet)
        self.assertEqual(review_packet._scan_rendered_bytes(md), [])


class RenderThenScanBites(unittest.TestCase):
    def test_scan_flags_abs_path(self) -> None:
        self.assertTrue(
            review_packet._scan_rendered_bytes("see /home/user/secret here"))

    def test_scan_flags_evidence_id(self) -> None:
        self.assertTrue(review_packet._scan_rendered_bytes("id ev_deadbeef99 here"))

    def test_scan_flags_windows_and_secret(self) -> None:
        self.assertTrue(review_packet._scan_rendered_bytes(r"C:\\Users\\x"))
        self.assertTrue(review_packet._scan_rendered_bytes(
            "-----BEGIN RSA PRIVATE KEY-----"))

    def test_scan_clean_returns_empty(self) -> None:
        self.assertEqual(
            review_packet._scan_rendered_bytes(
                "The applicant should obtain a current language test report."),
            [])


class RetrieveWhatYouCite(unittest.TestCase):
    def test_every_packet_citation_is_a_real_registry_pair(self) -> None:
        registry = crs_rules.load_registry()
        packet, _ = review_packet.build_packet(_checklist(registry))
        registry_pairs = {
            (c.chunk_id, c.quote)
            for row in registry.rows for c in row.citations}
        emitted = 0
        for finding in packet.findings:
            for cit in finding.citations:
                self.assertIn((cit.citation_id, cit.quote), registry_pairs)
                emitted += 1
        self.assertGreater(emitted, 0)


class NoSecondTrustPath(unittest.TestCase):
    def test_no_searchindex_or_grounding_import(self) -> None:
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
                names.extend(a.name for a in node.names)
        for name in names:
            self.assertNotIn("searchindex", name)
            self.assertNotIn("grounding", name)

    def test_no_inlined_volatile_rules(self) -> None:
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([_MODULE]), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
