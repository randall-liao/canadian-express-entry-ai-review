"""Closed-allowlist projection + structural firewall for the review packet (PKT-02/05).

Builds synthetic remediation checklists and asserts build_packet projects only the
allowlisted PII-free fields (dropping ev_), records the redaction in a manifest, is
deterministic, and renders the screening notice with no affirmative approval /
eligibility / outcome-prediction claim in the findings body. Stdlib unittest ONLY.
"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from crawler import review_packet
from crawler.audit_report import SCREENING_NOTICE
from crawler.remediation import (
    PrivateRemediationChecklist,
    PrivateRemediationItem,
    RemediationCitation,
)


def _item(factor_id, kind="gap", verdict="GAP", *, ev="ev_secret111"):
    return PrivateRemediationItem(
        factor_id=factor_id, factor_group="core_human_capital", verdict=verdict,
        reason_code="missing_evidence", finding_kind=kind,
        substantiated_points=None, score_delta=100, points_unresolved=False,
        evidence_ids=[ev],
        citations=[RemediationCitation(citation_id="guidance/x.md#001", quote="a rule")],
        action=f"Do the thing for {factor_id}.")


def _checklist(*items):
    return PrivateRemediationChecklist(
        source_audit_run_id="aud_pkt", candidate_id="cand-secret", items=list(items))


class PacketStructuralFirewall(unittest.TestCase):
    def test_packet_finding_rejects_injected_keys(self) -> None:
        base = dict(factor_id="core.age", verdict="GAP", finding_kind="gap",
                    action="x")
        review_packet.PacketFinding(**base)  # constructs
        for bad in ({"raw_value": "X"}, {"evidence_id": "ev_x"},
                    {"absolute_path": "/home/u/x"}, {"claimed_value": "secret"}):
            with self.assertRaises(ValidationError):
                review_packet.PacketFinding(**base, **bad)

    def test_packet_citation_rejects_ev_id(self) -> None:
        review_packet.PacketCitation(citation_id="a/b.md#001", quote="q")
        with self.assertRaises(ValidationError):
            review_packet.PacketCitation(citation_id="ev_abc", quote="q")

    def test_public_summary_rejects_absolute_path(self) -> None:
        with self.assertRaises(ValidationError):
            review_packet.PublicPacketSummary(
                run_id="pkt_deadbeef0014",
                source_audit_run_id="aud_deadbeef0014",
                private_output_path="/abs/x.json",
            )


class BuildPacketProjection(unittest.TestCase):
    def test_projects_all_findings_and_drops_ev(self) -> None:
        checklist = _checklist(_item("core.age"), _item("core.education"))
        packet, manifest = review_packet.build_packet(checklist)
        self.assertEqual(len(packet.findings), 2)
        blob = packet.model_dump_json()
        self.assertNotIn("ev_", blob)              # evidence pointers dropped
        self.assertNotIn("cand-secret", blob)      # candidate id not carried
        self.assertEqual(manifest.redacted_fields, ["evidence_ids"])

    def test_selection_filters_findings(self) -> None:
        checklist = _checklist(_item("core.age"), _item("core.education"))
        packet, manifest = review_packet.build_packet(checklist, selection={"core.age"})
        self.assertEqual([f.factor_id for f in packet.findings], ["core.age"])
        self.assertEqual(manifest.findings_included, 1)
        self.assertEqual(manifest.findings_excluded, 1)
        self.assertEqual(manifest.findings_total, 2)

    def test_finding_fields_projected(self) -> None:
        checklist = _checklist(_item("core.age"))
        packet, _ = review_packet.build_packet(checklist)
        f = packet.findings[0]
        self.assertEqual(f.factor_id, "core.age")
        self.assertEqual(f.verdict, "GAP")
        self.assertEqual(f.reason_code, "missing_evidence")
        self.assertEqual(f.finding_kind, "gap")
        self.assertEqual(f.score_impact, 100)
        self.assertEqual(f.citations[0].citation_id, "guidance/x.md#001")
        self.assertIn("core.age", f.action)

    def test_determinism(self) -> None:
        checklist = _checklist(_item("core.age"), _item("core.education"))
        a, _ = review_packet.build_packet(checklist)
        b, _ = review_packet.build_packet(checklist)
        self.assertEqual(a.model_dump(), b.model_dump())

    def test_manifest_document_counts(self) -> None:
        checklist = _checklist(_item("core.age"))
        _packet, manifest = review_packet.build_packet(
            checklist, documents_excluded=3)
        self.assertEqual(manifest.documents_excluded, 3)
        self.assertEqual(manifest.documents_included, [])


class PacketScreeningFraming(unittest.TestCase):
    def test_render_carries_screening_notice_and_no_affirmative_claims(self) -> None:
        checklist = _checklist(_item("core.age"))
        packet, _ = review_packet.build_packet(checklist)
        md = review_packet.render_packet_markdown(packet)
        # The verbatim screening notice is present.
        self.assertIn("Substantiation screening", md)
        self.assertIn(SCREENING_NOTICE, md)
        # The FINDINGS BODY (notice excluded) carries no affirmative approval /
        # eligibility / outcome-prediction claim (the notice's negated disclaimer stays).
        body = md.replace(SCREENING_NOTICE, "").lower()
        for phrase in ("you are eligible", "approved", "you will", "likely to",
                       "we predict", "your outcome"):
            self.assertNotIn(phrase, body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
