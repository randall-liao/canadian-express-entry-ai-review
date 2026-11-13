"""Corpus-gated conformance for the core + spouse CRS rule rows (Phase 31 — Plan 02).

Two-class structure mirroring ``crawler/tests/test_document_agents.py``:

* ``TestCoreSpouseRealCorpus`` — ``@skipUnless(corpus/index.db)``: loads the
  authored ``core.yaml`` + ``spouse.yaml``, runs the SHIPPED registry engine over
  the REAL corpus and asserts ZERO grounding violations for every non-gap row,
  retrieve-what-you-cite AGREEMENT for every non-gap row (guards against
  historical/adjacent chunk grounding), that every gap:true row is surfaced by
  ``coverage_report``, and that the rendered rows are publish-safe. On CI / a
  fresh clone the git-ignored index is absent and this class SKIPS — a green
  suite there is STRUCTURAL ONLY.

* ``TestCoreSpouseSyntheticMirror`` — ALWAYS-RUNS: builds a SYNTHETIC index in a
  ``TemporaryDirectory`` and exercises the SAME validate/retrieve loop
  mechanically, so a corpus-less run still proves the mechanism (not just static
  YAML).
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
_GROUPS = ("core_human_capital", "spouse_common_law")


def _load_cps():
    """Import scripts/check_publish_safe via a sys.path shim (mirrors test_document_agents)."""
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps

    return cps


def _core_spouse_registry() -> Registry:
    """Load the whole registry, then keep only core + spouse rows (plan-scoped)."""
    reg = crs_rules.load_registry(_DATA_DIR)
    return Registry(rows=[r for r in reg.rows if r.factor_group in _GROUPS])


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY GROUNDING GATE: corpus/index.db is git-ignored and absent — the "
    "core/spouse grounding proof did NOT run; a green suite here is STRUCTURAL ONLY",
)
class TestCoreSpouseRealCorpus(unittest.TestCase):
    """Every authored core/spouse row grounds + retrieves against the REAL corpus."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _core_spouse_registry()
        cls.nongap = [r for r in cls.reg.rows if not r.gap]

    def test_registry_has_core_and_spouse_rows(self) -> None:
        core = [r for r in self.reg.rows if r.factor_group == "core_human_capital"]
        spouse = [r for r in self.reg.rows if r.factor_group == "spouse_common_law"]
        self.assertGreaterEqual(len(core), 6, "expected >=6 core rows")
        self.assertGreaterEqual(len(spouse), 3, "expected >=3 spouse rows")

    def test_validate_registry_zero_violations(self) -> None:
        result = crs_rules.validate_registry(self.reg, _REAL_DB)
        self.assertEqual(result["violations"], [], result["violations"])
        self.assertEqual(result["grounded"], result["total"])

    def test_retrieve_what_you_cite_agrees_for_every_row(self) -> None:
        report = crs_rules.retrieve_what_you_cite(self.reg, _REAL_DB)
        for row in self.nongap:
            with self.subTest(rule_id=row.rule_id):
                entry = report[row.rule_id]
                self.assertIsNotNone(
                    entry["selected_chunk_id"],
                    f"{row.rule_id}: selector abstained on an answerable query",
                )
                self.assertTrue(
                    entry["agrees_with_citation"],
                    f"{row.rule_id}: re-selected {entry['selected_chunk_id']} disagrees "
                    f"with cited chunk(s) {[c.chunk_id for c in row.citations]}",
                )
                self.assertTrue(
                    entry["grounds"],
                    f"{row.rule_id}: re-selected chunk does not ground the row quote",
                )

    def test_conversion_row_cites_equivalency_chart(self) -> None:
        # Key link: CLB/NCLC conversion rows cite the language equivalency chart.
        conv = [r for r in self.reg.rows if r.check_type == "conversion"]
        self.assertTrue(conv, "expected at least one CLB/NCLC conversion row")
        cited = {c.chunk_id for r in conv for c in r.citations}
        self.assertTrue(
            any("language/test-equivalency-charts" in cid for cid in cited),
            f"conversion rows must cite the equivalency chart; cited={sorted(cited)}",
        )

    def test_gap_rows_are_surfaced_by_coverage(self) -> None:
        cov = crs_rules.coverage_report(self.reg)
        gap_rows = [r for r in self.reg.rows if r.gap]
        for row in gap_rows:
            with self.subTest(rule_id=row.rule_id):
                group = cov["by_group"][row.factor_group]
                self.assertTrue(
                    any(row.rule_id.startswith(lbl) for lbl in group["gaps"]),
                    f"gap row {row.rule_id} not surfaced in coverage gaps {group['gaps']}",
                )

    def test_rendered_rows_are_publish_safe(self) -> None:
        cps = _load_cps()
        for row in self.nongap:
            rendered = grounding.render_answer(crs_rules.row_to_answer(row), _REAL_DB)
            violations = cps.scan_text(f"rendered::{row.rule_id}", rendered)
            self.assertEqual(
                violations, [], [v.render() for v in violations]
            )


class TestCoreSpouseSyntheticMirror(unittest.TestCase):
    """ALWAYS-RUNS: prove the validate/retrieve loop against a synthetic index."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
        self.db = Path(self._tmp.name) / "index.db"
        searchindex.build_index(self.root, self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _syn_row(self) -> RuleRow:
        # A core row whose quote is a verbatim span of the synthetic tiny chunk.
        return RuleRow(
            rule_id="core.age.table",
            factor_group="core_human_capital",
            factor_ids=["core.age"],
            check_type="points",
            query="police certificates",
            selector=Selector(
                family="pr-pdi",
                marker="Permanent residence applicants must provide police certificates",
            ),
            claim_text="A synthetic grounded core rule.",
            citations=[
                Citation(
                    chunk_id="pr-pdi/tiny.md#000",
                    quote="Permanent residence applicants must provide police certificates",
                )
            ],
            machine_check=MachineCheck(kind="points_table", field="age_years"),
            volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi"),
        )

    def test_validate_and_retrieve_loop(self) -> None:
        reg = Registry(rows=[self._syn_row()])
        val = crs_rules.validate_registry(reg, self.db)
        self.assertEqual(val["violations"], [], val)
        self.assertEqual(val["grounded"], 1)
        ret = crs_rules.retrieve_what_you_cite(reg, self.db)["core.age.table"]
        self.assertEqual(ret["selected_chunk_id"], "pr-pdi/tiny.md#000")
        self.assertTrue(ret["agrees_with_citation"])
        self.assertTrue(ret["grounds"])

    def test_wrong_chunk_is_flagged(self) -> None:
        row = self._syn_row()
        # Cite a DIFFERENT chunk than the query+selector select.
        row.citations = [
            Citation(
                chunk_id="legislation-irpa/statute.md#000",
                quote="an officer may examine an applicant",
            )
        ]
        ret = crs_rules.retrieve_what_you_cite(Registry(rows=[row]), self.db)["core.age.table"]
        self.assertEqual(ret["selected_chunk_id"], "pr-pdi/tiny.md#000")
        self.assertFalse(ret["agrees_with_citation"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
