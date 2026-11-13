"""Corpus-gated conformance for the transferability + additional CRS rule rows (Plan 03).

Two-class structure mirroring ``crawler/tests/test_document_agents.py``:

* ``TestTransferAdditionalRealCorpus`` — ``@skipUnless(corpus/index.db)``: loads
  the authored ``transferability.yaml`` + ``additional.yaml``, runs the SHIPPED
  registry engine over the REAL corpus and asserts ZERO grounding violations,
  retrieve-what-you-cite AGREEMENT for every non-gap row, the three grounded cap
  rows (50/50/100) ground, and — the dedicated RULE-05 proof — the current
  arranged-employment repeal grounds guidance/job-offer.md and does NOT
  cross-ground the ITA-era legacy row (and vice versa).

* ``TestTransferAdditionalSyntheticMirror`` — ALWAYS-RUNS synthetic mirror.
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
_GROUPS = ("skill_transferability", "additional_points")


def _load_cps():
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps

    return cps


def _transfer_additional_registry() -> Registry:
    reg = crs_rules.load_registry(_DATA_DIR)
    return Registry(rows=[r for r in reg.rows if r.factor_group in _GROUPS])


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY GROUNDING GATE: corpus/index.db is git-ignored and absent — the "
    "transferability/additional grounding proof did NOT run; green here is STRUCTURAL ONLY",
)
class TestTransferAdditionalRealCorpus(unittest.TestCase):
    """Every authored transferability/additional row grounds against the REAL corpus."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _transfer_additional_registry()
        cls.nongap = [r for r in cls.reg.rows if not r.gap]

    def test_registry_has_transfer_and_additional_rows(self) -> None:
        c = [r for r in self.reg.rows if r.factor_group == "skill_transferability"]
        d = [r for r in self.reg.rows if r.factor_group == "additional_points"]
        caps = [r for r in c if r.machine_check.kind == "cap"]
        self.assertGreaterEqual(len(c), 5, "expected >=5 skill-transferability rows")
        self.assertGreaterEqual(len(caps), 3, "expected >=3 grounded cap rows")
        self.assertGreaterEqual(len(d), 5, "expected >=5 additional-points rows")

    def test_validate_registry_zero_violations(self) -> None:
        result = crs_rules.validate_registry(self.reg, _REAL_DB)
        self.assertEqual(result["violations"], [], result["violations"])
        self.assertEqual(result["grounded"], result["total"])

    def test_retrieve_what_you_cite_agrees_for_every_row(self) -> None:
        report = crs_rules.retrieve_what_you_cite(self.reg, _REAL_DB)
        for row in self.nongap:
            with self.subTest(rule_id=row.rule_id):
                entry = report[row.rule_id]
                self.assertIsNotNone(entry["selected_chunk_id"], row.rule_id)
                self.assertTrue(entry["agrees_with_citation"], row.rule_id)
                self.assertTrue(entry["grounds"], row.rule_id)

    def test_three_caps_ground(self) -> None:
        caps = {
            r.rule_id: r
            for r in self.reg.rows
            if r.machine_check.kind == "cap"
        }
        for rid in ("transfer.cap.education", "transfer.cap.foreign_work", "transfer.cap.total"):
            self.assertIn(rid, caps, f"missing grounded cap row {rid}")
        result = crs_rules.validate_registry(
            Registry(rows=list(caps.values())), _REAL_DB
        )
        self.assertEqual(result["violations"], [], result["violations"])
        self.assertEqual(caps["transfer.cap.total"].machine_check.cap_value, 100)

    def test_rule05_arranged_employment_current_grounds_and_no_cross_ground(self) -> None:
        # RULE-05: the current repeal row grounds guidance/job-offer.md and does NOT
        # cross-ground the ITA-era legacy MI chunk (and vice versa).
        report = crs_rules.retrieve_what_you_cite(self.reg, _REAL_DB)
        cur = report["additional.job_offer.current"]
        leg = report["additional.job_offer.legacy"]
        self.assertTrue(
            cur["selected_chunk_id"].startswith("guidance/job-offer"),
            f"current repeal selected {cur['selected_chunk_id']!r}",
        )
        self.assertTrue(cur["agrees_with_citation"] and cur["grounds"])
        self.assertTrue(
            leg["selected_chunk_id"].startswith("ministerial-instructions/"),
            f"legacy selected {leg['selected_chunk_id']!r}",
        )
        self.assertNotEqual(cur["selected_chunk_id"], leg["selected_chunk_id"])
        # The current row carries the effective repeal date from grounded metadata.
        cur_row = next(
            r for r in self.reg.rows if r.rule_id == "additional.job_offer.current"
        )
        self.assertEqual(cur_row.machine_check.effective_from, "2025-03-25")

    def test_gap_rows_are_surfaced_by_coverage(self) -> None:
        cov = crs_rules.coverage_report(self.reg)
        for row in (r for r in self.reg.rows if r.gap):
            with self.subTest(rule_id=row.rule_id):
                group = cov["by_group"][row.factor_group]
                self.assertTrue(
                    any(row.rule_id.startswith(lbl) for lbl in group["gaps"]),
                    f"gap row {row.rule_id} not surfaced in {group['gaps']}",
                )

    def test_rendered_rows_are_publish_safe(self) -> None:
        cps = _load_cps()
        for row in self.nongap:
            rendered = grounding.render_answer(crs_rules.row_to_answer(row), _REAL_DB)
            violations = cps.scan_text(f"rendered::{row.rule_id}", rendered)
            self.assertEqual(violations, [], [v.render() for v in violations])


class TestTransferAdditionalSyntheticMirror(unittest.TestCase):
    """ALWAYS-RUNS: prove the validate/retrieve loop against a synthetic index."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
        self.db = Path(self._tmp.name) / "index.db"
        searchindex.build_index(self.root, self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cap_and_policy_rows_loop(self) -> None:
        cap = RuleRow(
            rule_id="transfer.cap.total",
            factor_group="skill_transferability",
            factor_ids=["transfer.cap.total"],
            check_type="cap",
            query="police certificates",
            selector=Selector(
                family="pr-pdi",
                marker="Permanent residence applicants must provide police certificates",
            ),
            claim_text="A synthetic grounded cap row.",
            citations=[
                Citation(
                    chunk_id="pr-pdi/tiny.md#000",
                    quote="Permanent residence applicants must provide police certificates",
                )
            ],
            machine_check=MachineCheck(kind="cap", field="total", cap_value=100),
            volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi"),
        )
        val = crs_rules.validate_registry(Registry(rows=[cap]), self.db)
        self.assertEqual(val["violations"], [], val)
        ret = crs_rules.retrieve_what_you_cite(Registry(rows=[cap]), self.db)
        entry = ret["transfer.cap.total"]
        self.assertTrue(entry["agrees_with_citation"] and entry["grounds"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
