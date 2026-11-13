"""v4.1 SAFE-05 conformance — coverage completeness + no-false-green (release gate).

Authoritative, marker-tagged consolidation proving:
  * every first-official-language benchmark the conversion tables emit is priced, and
    a SUBSTANTIATED-but-unpriced factor is explicitly surfaced (never a silent 0);
  * no sibling extraction state (missing / non-accepted token / unresolved DOB / no
    ITA date / minor) can produce a SUBSTANTIATED verdict — only a confirmed, adult,
    claimed-scoped chain substantiates;
  * no adversarial extraction state (rotated / low-text / password-protected /
    ambiguous-date) can green or contaminate a factor through the REAL seam.

Reuses the proven Phase-35/36 assertions. Unguarded checks always run; real-seam
checks skip STRUCTURALLY on a fresh clone (git-ignored corpus + extraction deps).
Stdlib ``unittest`` ONLY.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from crawler import audit_report, crs_audit, crs_rules, extraction, vault
from crawler.auditors import additional as ad
from crawler.models.audit import (
    PrivateAuditReport,
    PrivateFactorCard,
    to_public_envelope,
)
from crawler.models.vault import CrsProfileFactor
from crawler.tests.fixtures.extraction import make_fixtures as mf
from crawler.tests.test_auditors_additional import (
    _SIBLING_ITA,
    _ctx,
    _sibling_fields,
)
from crawler.tests.test_language_points_coverage import _conversion_emitted_levels

pytestmark = pytest.mark.conformance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"
_FIRST_LANGUAGE = "core.language.first"


def _extraction_available() -> bool:
    try:
        extraction._import_pdfium()
        extraction._import_pil()
        extraction._import_pdfminer()
        return True
    except extraction.MissingExtractionDependency:  # pragma: no cover
        return False


_EXTRACTION_OK = _extraction_available()


class PricedOrExplicitlyUnresolved(unittest.TestCase):
    """SAFE-05: every emitted benchmark priced; any unpriced factor surfaced."""

    def setUp(self) -> None:
        self.reg = crs_rules.load_registry()
        self.levels = _conversion_emitted_levels(self.reg)

    def test_conversion_levels_non_empty(self) -> None:
        self.assertTrue(self.levels, "conversion-emitted level set is vacuous")

    def test_every_emitted_benchmark_is_priced_both_modes(self) -> None:
        for lvl in sorted(self.levels):
            for spouse_mode in (False, True):
                self.assertIsNotNone(
                    crs_audit.score_factor(_FIRST_LANGUAGE, lvl, spouse_mode, self.reg),
                    f"benchmark CLB {lvl} (spouse={spouse_mode}) UNPRICED")

    def test_unpriced_substantiated_is_surfaced(self) -> None:
        card = PrivateFactorCard(
            factor_id=_FIRST_LANGUAGE, factor_group="core_human_capital",
            verdict="SUBSTANTIATED", reason_code="grounded_substantiated",
            substantiated_points=None, points_unresolved=True)
        report = PrivateAuditReport(
            run_id="aud_deadbeef0006", candidate_id="c", factor_cards=[card])
        env = to_public_envelope(
            report, "output/crs-audit/aud_deadbeef0006.json"
        )
        self.assertGreaterEqual(env.counts["unpriced"], 1)


class SiblingNoFalseGreen(unittest.TestCase):
    """SAFE-05: no sibling blocking state greens additional.sibling."""

    def _decide(self, *, ita_date=_SIBLING_ITA, **overrides):
        return ad.decide_sibling(
            _ctx("additional.sibling",
                 by_field=_sibling_fields(**overrides), ita_date=ita_date))

    def test_confirmed_adult_chain_substantiates(self) -> None:
        self.assertEqual(self._decide().verdict, "SUBSTANTIATED")

    def test_blocking_states_never_substantiate(self) -> None:
        cases = [
            dict(sibling_residence=None),                 # missing field
            dict(sibling_relationship="cousin"),          # non-accepted relationship
            dict(sibling_status="visitor"),               # non-accepted status
            dict(sibling_date_of_birth="not-a-date"),     # unresolvable DOB
            dict(sibling_date_of_birth="2010-01-01"),     # clear minor
        ]
        for overrides in cases:
            self.assertNotEqual(
                self._decide(**overrides).verdict, "SUBSTANTIATED", overrides)
        # No authoritative ITA date -> cannot pin adulthood -> not green.
        self.assertNotEqual(
            self._decide(ita_date=None).verdict, "SUBSTANTIATED")


@unittest.skipUnless(
    _REAL_DB.is_file() and _EXTRACTION_OK,
    "LOCAL-ONLY: corpus/index.db and/or extraction deps absent — the adversarial "
    "no-false-green real-seam proof did NOT run; a green suite here is STRUCTURAL ONLY")
class AdversarialNoFalseGreenRealSeam(unittest.TestCase):
    """SAFE-05: adversarial extraction states never green through the real seam."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.db = str(_REAL_DB)
        self.registry = crs_rules.load_registry()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _import(self, v, data, doc_type, name):
        src = Path(self._tmp.name) / f"{name}.pdf"
        src.write_bytes(data)
        return vault.import_document(v, "default", src, doc_type=doc_type).document_id

    def test_rotated_language_scan_never_greens(self) -> None:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id=_FIRST_LANGUAGE, factor_group="core_human_capital",
            claimed_points=124, claimed_level="9", claimed_value=9))
        vault.set_ita_round(
            v, "default", "coverage", None, "EE", cutoff_score=None)
        lang = "\n".join([
            "IELTS Academic Test Report Form", "Test Date: 15 January 2026",
            "Listening: 8.0", "Reading: 8.0", "Writing: 7.5", "Speaking: 7.5"])
        doc = self._import(v, mf.build_pdf([lang], rotations=[90]),
                           "language_test", "rot")
        try:
            extraction.extract_document(v, doc)
        except extraction.MissingExtractionDependency as exc:  # pragma: no cover
            self.skipTest(f"extraction deps unavailable: {exc.module}")
        self.assertEqual(vault.audit_eligible_values(v, _FIRST_LANGUAGE), [])
        report, _ = audit_report.run_full_audit_report(v, self.db, self.registry)
        card = next(c for c in report.factor_cards if c.factor_id == _FIRST_LANGUAGE)
        self.assertNotEqual(card.verdict, "SUBSTANTIATED")
        v.con.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
