"""Full-registry conformance — the phase-level acceptance gate (Phase 31 — Plan 05).

Runs the Plan 31-01 engine over the WHOLE registry (all four YAML files):

* ``TestFullRegistryRealCorpus`` — ``@skipUnless(corpus/index.db)``: zero grounding
  violations across every non-gap row of all four groups, retrieve-what-you-cite
  agreement for every non-gap row, coverage complete-or-documented-gaps, and a
  publish-safe self-scan of every rendered row. On CI / a fresh clone this SKIPS.

* ``TestFullRegistrySyntheticMirror`` — ALWAYS-RUNS: exercises validate_registry +
  coverage_report over a small SYNTHETIC registry (a complete grid + one
  deliberately-missing required id + one gap:true row) so CI proves the full-loop
  mechanism (completeness detection + gap surfacing) without the real corpus.

Also owns the committed public COVERAGE.md drift guard (Task 2).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from crawler import crs_rules, grounding, searchindex
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.tests.test_searchindex import _make_index_corpus

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"
_DATA_DIR = _REPO_ROOT / "crawler" / "data" / "crs_rules"
_COVERAGE_MD = _DATA_DIR / "COVERAGE.md"

_TINY_ID = "pr-pdi/tiny.md#000"
_TINY_QUOTE = "Permanent residence applicants must provide police certificates"


def _load_cps():
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps

    return cps


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY GROUNDING GATE: corpus/index.db is git-ignored and absent — the "
    "full-registry grounding proof did NOT run; a green suite here is STRUCTURAL ONLY",
)
class TestFullRegistryRealCorpus(unittest.TestCase):
    """The whole registry grounds + retrieves + is complete against the REAL corpus."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = crs_rules.load_registry(_DATA_DIR)
        cls.nongap = [r for r in cls.reg.rows if not r.gap]

    def test_validate_whole_registry_zero_violations(self) -> None:
        result = crs_rules.validate_registry(self.reg, _REAL_DB)
        self.assertEqual(result["violations"], [], result["violations"])
        self.assertEqual(result["grounded"], result["total"])
        self.assertGreaterEqual(result["total"], 20)

    def test_retrieve_what_you_cite_agrees_across_all_groups(self) -> None:
        report = crs_rules.retrieve_what_you_cite(self.reg, _REAL_DB)
        for row in self.nongap:
            with self.subTest(rule_id=row.rule_id):
                entry = report[row.rule_id]
                self.assertTrue(entry["agrees_with_citation"], row.rule_id)
                self.assertTrue(entry["grounds"], row.rule_id)

    def test_coverage_complete_or_documented_gaps(self) -> None:
        cov = crs_rules.coverage_report(self.reg)
        for group, info in cov["by_group"].items():
            # RULE-03: no silent omission — every not-present required id is a GAP.
            self.assertEqual(
                info["missing"], [],
                f"{group}: required rule_ids missing (not present, not documented GAP): "
                f"{info['missing']}",
            )
        self.assertTrue(cov["complete"])

    def test_rendered_whole_registry_is_publish_safe(self) -> None:
        cps = _load_cps()
        for row in self.nongap:
            rendered = grounding.render_answer(crs_rules.row_to_answer(row), _REAL_DB)
            violations = cps.scan_text(f"rendered::{row.rule_id}", rendered)
            self.assertEqual(violations, [], [v.render() for v in violations])

    # ---- Task 2: committed COVERAGE.md drift guard --------------------------- #
    def test_committed_coverage_md_matches_fresh_output(self) -> None:
        self.assertTrue(_COVERAGE_MD.is_file(), "COVERAGE.md is not committed")
        fresh = crs_rules.render_coverage_markdown(self.reg)
        committed = _COVERAGE_MD.read_text(encoding="utf-8")
        self.assertEqual(
            committed, fresh,
            "COVERAGE.md is stale — regenerate with "
            "`.venv/bin/python -m crawler.crs_rules > crawler/data/crs_rules/COVERAGE.md`",
        )

    def test_generated_coverage_is_publish_safe(self) -> None:
        cps = _load_cps()
        fresh = crs_rules.render_coverage_markdown(self.reg)
        violations = cps.scan_text("crawler/data/crs_rules/COVERAGE.md", fresh)
        self.assertEqual(violations, [], [v.render() for v in violations])


class TestFullRegistrySyntheticMirror(unittest.TestCase):
    """ALWAYS-RUNS: completeness detection + gap surfacing over a synthetic index."""

    _MISSING = "core.age"          # deliberately omitted required label
    _GAP = "additional.sibling"    # deliberately gap:true

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
        self.db = Path(self._tmp.name) / "index.db"
        searchindex.build_index(self.root, self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _synthetic_grid(self) -> Registry:
        rows: list[RuleRow] = []
        for group, labels in crs_rules.REQUIRED_RULE_IDS.items():
            for label in labels:
                if label == self._MISSING:
                    continue  # omit one required id
                rows.append(
                    RuleRow(
                        rule_id=label,
                        factor_group=group,
                        factor_ids=[label],
                        check_type="admissibility",
                        query="police certificates",
                        selector=Selector(family="pr-pdi", marker=_TINY_QUOTE),
                        claim_text="synthetic grid row",
                        citations=[Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
                        machine_check=MachineCheck(kind="policy_flag", field="x"),
                        volatility=VolatilityMeta(volatility="stable", source_family="pr-pdi"),
                        gap=(label == self._GAP),
                        gap_reason="synthetic documented gap" if label == self._GAP else None,
                    )
                )
        return Registry(rows=rows)

    def test_validate_grounds_all_non_gap_rows(self) -> None:
        reg = self._synthetic_grid()
        result = crs_rules.validate_registry(reg, self.db)
        self.assertEqual(result["violations"], [], result)
        self.assertEqual(result["grounded"], result["total"])

    def test_coverage_detects_missing_and_gap(self) -> None:
        reg = self._synthetic_grid()
        cov = crs_rules.coverage_report(reg)
        self.assertFalse(cov["complete"], "a deliberately-missing id must break completeness")
        self.assertIn(self._MISSING, cov["by_group"]["core_human_capital"]["missing"])
        self.assertIn(self._GAP, cov["by_group"]["additional_points"]["gaps"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
