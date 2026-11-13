"""SAFE-04 screening-framing conformance gate (Phase 34 — Plan 04, Task 3).

Asserts the SAFE-04 framing is PRESENT — in the rendered vault report
(``audit_report.SCREENING_NOTICE``), ``crawler/README.md``, and ``SCREENING.md``
— and that prohibited legal-advice / eligibility phrasing is ABSENT (a
non-vacuous denylist), and that the release docs are generic / PII-free.

Stdlib ``unittest`` ONLY — NO network. ALWAYS RUNS (no corpus needed).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_conformance_v40_screening_framing.py -q
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

from crawler import audit_report
from crawler.models.audit import PrivateAuditReport, PrivateFactorCard

pytestmark = pytest.mark.conformance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_README = _REPO_ROOT / "crawler" / "README.md"
_SCREENING = _REPO_ROOT / "SCREENING.md"
_SECTION_HEADER = "## Substantiation screening"

# Prohibited legal-advice / eligibility phrasing — none may appear in the docs or
# the rendered report (the negated disclaimer "not legal advice" is normalized out
# first, so the disclaimer itself never trips the gate).
_DENYLIST = (
    "you are eligible",
    "you qualify",
    "guaranteed",
    "approved",
    "no misrepresentation risk",
    "we recommend that you",
    "eligibility guarantee",
)


def _load_cps():
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # noqa: E402
    return cps


def _prohibited_flags(text: str) -> list[str]:
    """Return the prohibited-phrasing flags in *text* (the SAFE-04 denylist).

    Normalizes out the NEGATED disclaimer ("not legal advice" / "not a
    substitute") before scanning, so a proper disclaimer does not trip the gate;
    a BARE "legal advice" claim that remains after normalization IS flagged.
    """
    lowered = text.lower()
    normalized = (lowered.replace("not legal advice", "")
                  .replace("not a substitute", ""))
    flags = [phrase for phrase in _DENYLIST if phrase in normalized]
    if "legal advice" in normalized:
        flags.append("legal advice")
    return flags


def _rendered_report_md() -> str:
    """Render a synthetic-report factor-card markdown (carries the notice)."""
    report = PrivateAuditReport(
        run_id="aud_conf", candidate_id="default",
        substantiated_total=600, cutoff_delta=100, meets_cutoff=True,
        factor_cards=[
            PrivateFactorCard(
                factor_id="additional.nomination",
                factor_group="additional_points", verdict="SUBSTANTIATED",
                reason_code="grounded_substantiated", substantiated_points=600,
                rule_citation_ids=["guidance/crs-criteria.md#018"]),
            PrivateFactorCard(
                factor_id="core.work", factor_group="core_human_capital",
                verdict="GAP", reason_code="below_threshold"),
        ])
    return audit_report._render_factor_card_markdown(report)


class TestScreeningFramingPresent(unittest.TestCase):
    """The narrow-SUBSTANTIATED + AT-RISK-scope + not-legal-advice framing is
    present in the report notice, the README, and SCREENING.md."""

    def _assert_framing_present(self, text: str, where: str) -> None:
        low = text.lower()
        # not-legal-advice framing.
        self.assertTrue("not legal advice" in low or "not a substitute" in low,
                        f"{where}: missing not-legal-advice framing")
        # narrow SUBSTANTIATED definition.
        self.assertIn("audit-eligible", low, where)
        self.assertIn("threshold", low, where)
        self.assertTrue("grounded" in low or "cited" in low, where)
        # AT-RISK scope for semantic / NOC-duty fit + officer discretion.
        self.assertIn("at-risk", low, where)
        self.assertIn("semantic fit", low, where)
        self.assertIn("officer discretion", low, where)
        self.assertIn("noc", low, where)  # NOC-duty fit

    def test_screening_notice_present(self) -> None:
        self._assert_framing_present(
            audit_report.SCREENING_NOTICE, "SCREENING_NOTICE")

    def test_readme_present(self) -> None:
        text = _README.read_text(encoding="utf-8")
        self.assertIn(_SECTION_HEADER, text)
        self._assert_framing_present(text, "crawler/README.md")

    def test_screening_md_present(self) -> None:
        self.assertTrue(_SCREENING.is_file())
        self._assert_framing_present(
            _SCREENING.read_text(encoding="utf-8"), "SCREENING.md")

    def test_rendered_report_carries_the_screening_notice(self) -> None:
        md = _rendered_report_md()
        self.assertIn(audit_report.SCREENING_NOTICE, md)
        self.assertIn("not legal advice", md.lower())
        self._assert_framing_present(md, "rendered report")


class TestProhibitedPhrasingAbsent(unittest.TestCase):
    """No prohibited legal-advice / eligibility phrasing — denylist non-vacuous."""

    def test_denylist_helper_is_non_vacuous(self) -> None:
        # POSITIVE CONTROL: a crafted legal-advice/eligibility claim IS flagged.
        flags = _prohibited_flags(
            "You are eligible and the outcome is guaranteed. This is legal advice.")
        self.assertIn("you are eligible", flags)
        self.assertIn("guaranteed", flags)
        self.assertIn("legal advice", flags)
        # The proper negated disclaimer is NOT flagged.
        self.assertEqual(
            _prohibited_flags("This is not legal advice and not a substitute."),
            [])

    def test_readme_has_no_prohibited_phrasing(self) -> None:
        flags = _prohibited_flags(_README.read_text(encoding="utf-8"))
        self.assertEqual(flags, [], f"README prohibited phrasing: {flags}")

    def test_screening_md_has_no_prohibited_phrasing(self) -> None:
        flags = _prohibited_flags(_SCREENING.read_text(encoding="utf-8"))
        self.assertEqual(flags, [], f"SCREENING.md prohibited phrasing: {flags}")

    def test_rendered_report_has_no_prohibited_phrasing(self) -> None:
        flags = _prohibited_flags(_rendered_report_md())
        self.assertEqual(flags, [], f"rendered report prohibited phrasing: {flags}")

    def test_screening_notice_has_no_prohibited_phrasing(self) -> None:
        flags = _prohibited_flags(audit_report.SCREENING_NOTICE)
        self.assertEqual(flags, [], f"SCREENING_NOTICE prohibited phrasing: {flags}")


class TestReleaseDocsArePiiFree(unittest.TestCase):
    """SCREENING.md and the README screening section are generic / shareable."""

    def _readme_screening_section(self) -> str:
        text = _README.read_text(encoding="utf-8")
        self.assertIn(_SECTION_HEADER, text)
        after = text.split(_SECTION_HEADER, 1)[1]
        # Up to the next top-level heading.
        return _SECTION_HEADER + after.split("\n## ", 1)[0]

    def test_screening_md_scans_publish_safe(self) -> None:
        cps = _load_cps()
        violations = cps.scan_text(
            "SCREENING.md", _SCREENING.read_text(encoding="utf-8"))
        self.assertEqual(violations, [], [v.render() for v in violations])

    def test_readme_screening_section_scans_publish_safe(self) -> None:
        cps = _load_cps()
        section = self._readme_screening_section()
        violations = cps.scan_text("crawler/README.md", section)
        self.assertEqual(violations, [], [v.render() for v in violations])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
