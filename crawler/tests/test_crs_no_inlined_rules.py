"""Aggregate static "no inlined volatile rule" gate (Phase 31 — Plan 05, RULE-02).

Runs ``crs_rules.no_inlined_volatile_rules`` over the registry-adjacent prose
surface — every file under ``skills/crs-auditors/`` (the Phase-33 auditor pack,
which may not exist yet; a missing/empty glob is clean, but the gate is WIRED and
trips the moment a future auditor markdown inlines a volatile threshold) PLUS the
registry YAML files (volatile values must live ONLY inside grounded machine_check
payloads / verbatim quotes, never as stray prose). A POSITIVE CONTROL proves the
gate actually bites, so an empty auditor directory cannot mask a broken gate.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from crawler import crs_rules

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUDITORS_DIR = _REPO_ROOT / "skills" / "crs-auditors"
_DATA_DIR = _REPO_ROOT / "crawler" / "data" / "crs_rules"
_AUDITOR_PKG = _REPO_ROOT / "crawler" / "auditors"
_AUDITOR_SPINE = _REPO_ROOT / "crawler" / "auditor.py"
# Phase 37/38 export layers: pure projections of the grounded audit — a remediation /
# review-packet line that inlines a volatile CRS threshold instead of reusing a
# grounded rule trips the same gate (a missing path is skipped, so this is WIRED even
# before review_packet.py exists).
#
# Phase 43 NOC work-duty review modules (NOC-03 / no-inlined-volatile invariant): the
# worksheet generator + the inert never-green sidecar. Any future inlined duty text,
# lead statement, threshold, or the R87.1 standard in either module trips this same
# static gate — the volatile facts (duty text, the R87.1 essential-duties standard)
# MUST stay grounded in the corpus, never inlined into a production surface. A missing
# path is silently skipped, so the gate stays WIRED (the positive control proves it
# still bites over the extended surface).
#
# Phase 44 study review and Phase 46 POLICY/DLI surfaces: every v5 production
# consumer or generator is named explicitly.  Keep this exact rather than hiding
# enrollment behind a recursive production glob.
_V5_NAMED_MODULES = (
    _REPO_ROOT / "crawler" / "models" / "mec.py",
    _REPO_ROOT / "crawler" / "mecfields.py",
    _REPO_ROOT / "crawler" / "mec_screen.py",
    _REPO_ROOT / "crawler" / "mec_publish.py",
    _REPO_ROOT / "crawler" / "snapshot_policy.py",
    _REPO_ROOT / "crawler" / "policy_offer.py",
    _REPO_ROOT / "crawler" / "study_review.py",
    _REPO_ROOT / "crawler" / "noc_worksheet.py",
    _REPO_ROOT / "crawler" / "noc_review.py",
    _REPO_ROOT / "crawler" / "dli_contract.py",
    _REPO_ROOT / "crawler" / "dli_snapshot.py",
)

_EXPORT_MODULES = (
    _REPO_ROOT / "crawler" / "remediation.py",
    _REPO_ROOT / "crawler" / "review_packet.py",
)

_EXPECTED_V5_NAMED_MODULES = {
    "crawler/models/mec.py",
    "crawler/mecfields.py",
    "crawler/mec_screen.py",
    "crawler/mec_publish.py",
    "crawler/snapshot_policy.py",
    "crawler/policy_offer.py",
    "crawler/study_review.py",
    "crawler/noc_worksheet.py",
    "crawler/noc_review.py",
    "crawler/dli_contract.py",
    "crawler/dli_snapshot.py",
}


def _registry_and_auditor_surface() -> list[Path]:
    surface: list[Path] = []
    if _AUDITORS_DIR.is_dir():
        surface.extend(sorted(_AUDITORS_DIR.rglob("*.md")))
        surface.extend(sorted(_AUDITORS_DIR.rglob("*.py")))
    # The Phase-33 decider modules + the generic spine: any inlined CLB level,
    # points value, cap, window, or policy date in a decider trips the gate.
    if _AUDITOR_PKG.is_dir():
        surface.extend(sorted(_AUDITOR_PKG.rglob("*.py")))
    if _AUDITOR_SPINE.is_file():
        surface.append(_AUDITOR_SPINE)
    # Phase 37/38 export layers (remediation, review packet).
    surface.extend(m for m in (*_EXPORT_MODULES, *_V5_NAMED_MODULES)
                   if m.is_file())
    surface.extend(sorted(_DATA_DIR.glob("*.yaml")))
    return surface


class TestAggregateNoInlinedRules(unittest.TestCase):
    def test_v5_named_module_enrollment_is_exact_and_nonempty(self) -> None:
        actual = {
            path.relative_to(_REPO_ROOT).as_posix()
            for path in _V5_NAMED_MODULES
        }
        self.assertTrue(actual)
        self.assertEqual(actual, _EXPECTED_V5_NAMED_MODULES)

    def test_registry_and_auditor_surface_is_clean(self) -> None:
        violations = crs_rules.no_inlined_volatile_rules(_registry_and_auditor_surface())
        self.assertEqual(
            violations, [], [f"{v['path']}:{v['line']} {v['kind']} {v['snippet']}" for v in violations]
        )

    def test_missing_auditor_dir_is_not_an_error(self) -> None:
        # A path that does not exist is silently skipped (the gate stays WIRED).
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([_REPO_ROOT / "skills" / "does-not-exist" / "x.md"]),
            [],
        )

    def test_positive_control_gate_bites(self) -> None:
        # An inlined "CLB 9 -> 50 points" prose claim MUST be flagged (non-vacuous).
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "auditor.md"
            p.write_text(
                "The core auditor awards 50 points when the applicant reaches CLB 9 "
                "on all four abilities.\n",
                encoding="utf-8",
            )
            violations = crs_rules.no_inlined_volatile_rules([p])
        self.assertTrue(violations, "the static gate did not flag an inlined volatile threshold")

    def test_positive_control_python_literal_bites(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "auditor.py"
            p.write_text("def score():\n    cap = 600  # nomination points\n    return cap\n", encoding="utf-8")
            violations = crs_rules.no_inlined_volatile_rules([p])
        self.assertTrue(violations, "the static gate did not flag an inlined Python literal")

    def test_mec_positive_control_for_each_category(self) -> None:
        samples = {
            "mec_duration": "minimum_work = '24 months and 3120 hours'",
            "mec_language_level": "minimum_language = 'CLB 7'",
            "mec_noc_hierarchy": "eligible_trade = 'Major Group 72'",
            "mec_grid_value": "fsw_pass_mark = 67",
            "mec_policy_date": "mec_effective_date = '2025-03-25'",
            "mec_funds_value": f"settlement_funds = '${12000 + 345}'",
        }
        with tempfile.TemporaryDirectory() as d:
            for expected_kind, source in samples.items():
                with self.subTest(expected_kind=expected_kind):
                    path = Path(d) / f"{expected_kind}.py"
                    path.write_text(source + "\n", encoding="utf-8")
                    violations = crs_rules.no_inlined_volatile_rules([path])
                    self.assertIn(expected_kind, {item["kind"] for item in violations})

    def test_dli_positive_control_for_policy_date_and_threshold(self) -> None:
        samples = {
            "dli_policy_date": "dli_effective_date = '2026-01-01'",
            "dli_threshold": "pgwp_minimum_duration = '8 months'",
        }
        with tempfile.TemporaryDirectory() as d:
            for expected_kind, source in samples.items():
                with self.subTest(expected_kind=expected_kind):
                    path = Path(d) / f"{expected_kind}.py"
                    path.write_text(source + "\n", encoding="utf-8")
                    violations = crs_rules.no_inlined_volatile_rules([path])
                    self.assertEqual(
                        [item["kind"] for item in violations],
                        [expected_kind],
                    )

    def test_python_comments_docstrings_identifiers_and_arithmetic_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "clean.py"
            path.write_text(
                "# FSW pass mark 67 and CLB 7 are discussed here only.\n"
                '"""Major Group 72, 24 months, and $12345 are documentation."""\n'
                "fsw_pass_mark_from_registry = row.machine_check.min_value\n"
                "ordinary_total = 60 + 7\n",
                encoding="utf-8",
            )
            self.assertEqual(crs_rules.no_inlined_volatile_rules([path]), [])

    def test_markdown_headings_are_ignored_but_policy_prose_bites(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            heading = Path(d) / "heading.md"
            heading.write_text("# FSW CLB 7 and pass mark 67\n", encoding="utf-8")
            prose = Path(d) / "prose.md"
            prose.write_text("FSW requires a pass mark of 67.\n", encoding="utf-8")
            self.assertEqual(crs_rules.no_inlined_volatile_rules([heading]), [])
            kinds = {
                item["kind"] for item in crs_rules.no_inlined_volatile_rules([prose])
            }
            self.assertIn("mec_grid_value", kinds)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
