"""Exact public private-output locator contracts."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from crawler import remediation, review_packet
from crawler.models.audit import PublicAuditEnvelope
from crawler.models.mec import MecCounts, PublicMecSummary

_AUDIT_ID = "aud_deadbeef0001"
_REMEDIATION_ID = "rem_deadbeef0001"
_PACKET_ID = "pkt_deadbeef0001"
_MEC_ID = "mec_deadbeef0001deadbeef0001deadbeef"


class ExactPublicLocatorContracts(unittest.TestCase):
    @staticmethod
    def _audit(
        path: str = f"output/crs-audit/{_AUDIT_ID}.json",
        *,
        run_id: str = _AUDIT_ID,
    ):
        return PublicAuditEnvelope(
            run_id=run_id,
            factor_id="core.age",
            private_output_path=path,
        )

    @staticmethod
    def _mec(
        path: str = "output/mec/cec/latest.json",
        *,
        run_id: str = _MEC_ID,
    ):
        return PublicMecSummary(
            schema_version="1.0",
            run_id=run_id,
            program="cec",
            status="AT-RISK",
            criteria=[],
            counts=MecCounts(),
            registry_fingerprint="a" * 64,
            private_output_path=path,
        )

    @staticmethod
    def _remediation(
        path: str = f"output/remediation/{_REMEDIATION_ID}.json",
        *,
        run_id: str = _REMEDIATION_ID,
        source_audit_run_id: str = _AUDIT_ID,
    ):
        return remediation.PublicRemediationSummary(
            run_id=run_id,
            source_audit_run_id=source_audit_run_id,
            private_output_path=path,
        )

    @staticmethod
    def _packet(
        path: str | None = f"output/review-packet/{_PACKET_ID}.json",
        *,
        run_id: str | None = _PACKET_ID,
        source_audit_run_id: str = _AUDIT_ID,
    ):
        return review_packet.PublicPacketSummary(
            run_id=run_id,
            source_audit_run_id=source_audit_run_id,
            private_output_path=path,
        )

    def test_valid_models_serialize_only_the_exact_locator(self) -> None:
        models = (
            self._audit(),
            self._mec(),
            self._remediation(),
            self._packet(),
        )
        expected = (
            f"output/crs-audit/{_AUDIT_ID}.json",
            "output/mec/cec/latest.json",
            f"output/remediation/{_REMEDIATION_ID}.json",
            f"output/review-packet/{_PACKET_ID}.json",
        )
        self.assertEqual(
            tuple(
                model.model_dump(mode="json")["private_output_path"]
                for model in models
            ),
            expected,
        )

    def test_mismatched_run_or_program_is_rejected(self) -> None:
        invalid = (
            lambda: self._audit("output/crs-audit/aud_deadbeef0002.json"),
            lambda: self._mec("output/mec/fsw/latest.json"),
            lambda: self._remediation(
                "output/remediation/rem_deadbeef0002.json"
            ),
            lambda: self._packet(
                "output/review-packet/pkt_deadbeef0002.json"
            ),
        )
        for constructor in invalid:
            with self.subTest(constructor=constructor), self.assertRaises(
                ValidationError
            ):
                constructor()

    def test_uri_candidate_bearing_and_extra_segment_are_rejected(self) -> None:
        invalid = (
            lambda path: self._audit(path),
            lambda path: self._mec(path),
            lambda path: self._remediation(path),
            lambda path: self._packet(path),
        )
        bad_paths = (
            "https://host/report.json",
            "output/privacy-candidate-xqz/report.json",
            "candidates/privacy-candidate-xqz/output/report.json",
            "output/extra/segment/report.json",
            f"output/crs-audit/{_AUDIT_ID}.md",
            r"C:\output\report.json",
            r"\\server\share\report.json",
            "../output/report.json",
        )
        for constructor in invalid:
            for path in bad_paths:
                with (
                    self.subTest(constructor=constructor, path=path),
                    self.assertRaises(ValidationError),
                ):
                    constructor(path)

    def test_packet_dry_run_serializes_none_and_writes_require_locator(
            self) -> None:
        dry_run = review_packet.PublicPacketSummary(
            run_id=None,
            source_audit_run_id=_AUDIT_ID,
            private_output_path=None,
        )
        self.assertIsNone(dry_run.model_dump(mode="json")["run_id"])
        self.assertIsNone(
            dry_run.model_dump(mode="json")["private_output_path"]
        )
        with self.assertRaises(ValidationError):
            review_packet.PublicPacketSummary(
                run_id=None,
                source_audit_run_id=_AUDIT_ID,
                private_output_path="(dry-run — not written)",
            )
        with self.assertRaises(ValidationError):
            self._packet(None)

    def test_run_identifiers_are_exact_opaque_types(self) -> None:
        invalid = (
            "candidate-name",
            "ev_deadbeef0001",
            "Alice",
            "AUD_deadbeef0001",
            "aud_DEADBEEF0001",
            "aud_deadbeef001",
            "aud_deadbeef00011",
            "aud_deadbeef000g",
        )
        for value in invalid:
            with self.subTest(kind="audit", value=value), self.assertRaises(
                ValidationError
            ):
                self._audit(run_id=value)
            with self.subTest(kind="source-rem", value=value), self.assertRaises(
                ValidationError
            ):
                self._remediation(source_audit_run_id=value)
            with self.subTest(kind="source-pkt", value=value), self.assertRaises(
                ValidationError
            ):
                self._packet(source_audit_run_id=value)

        cases = (
            ("remediation", self._remediation, (
                "candidate-name",
                "ev_deadbeef0001",
                "REM_deadbeef0001",
                "rem_DEADBEEF0001",
                "rem_deadbeef001",
                "rem_deadbeef00011",
                "rem_deadbeef000g",
            )),
            ("packet", self._packet, (
                "candidate-name",
                "ev_deadbeef0001",
                "PKT_deadbeef0001",
                "pkt_DEADBEEF0001",
                "pkt_deadbeef001",
                "pkt_deadbeef00011",
                "pkt_deadbeef000g",
            )),
            ("mec", self._mec, (
                "candidate-name",
                "ev_deadbeef0001",
                "MEC_" + "d" * 32,
                "mec_" + "D" * 32,
                "mec_" + "d" * 31,
                "mec_" + "d" * 33,
                "mec_" + "d" * 31 + "g",
            )),
        )
        for kind, constructor, values in cases:
            for value in values:
                with self.subTest(kind=kind, value=value), self.assertRaises(
                    ValidationError
                ):
                    constructor(run_id=value)

    def test_valid_identifiers_serialize_unchanged(self) -> None:
        self.assertEqual(self._audit().model_dump(mode="json")["run_id"], _AUDIT_ID)
        self.assertEqual(
            self._remediation().model_dump(mode="json"),
            {
                "run_id": _REMEDIATION_ID,
                "source_audit_run_id": _AUDIT_ID,
                "item_count": 0,
                "counts": {},
                "private_output_path": (
                    f"output/remediation/{_REMEDIATION_ID}.json"
                ),
            },
        )
        self.assertEqual(self._packet().model_dump(mode="json")["run_id"], _PACKET_ID)
        self.assertEqual(self._mec().model_dump(mode="json")["run_id"], _MEC_ID)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
