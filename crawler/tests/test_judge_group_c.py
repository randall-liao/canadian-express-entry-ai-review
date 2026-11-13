"""Tests for the Category C Parallel Judge / Eval Agent (crawler/eval/judge_group_c.py).

Verifies that the Category C judge (Financial, Medical & Police):
1. Scopes strictly to the 6 Category C document types (both vector + scanned variants).
2. Achieves 100% grounding accuracy, 100% defect recall, and 100% PII containment.
3. Confines applicant PII to basis[] with zero leakage into the public surface.
4. Enforces the judge invariants rigorously (ungrounded claims, missed defects, and
   PII leaked into the public surface all fail the evaluation).
5. Runs `main()` cleanly (exit code 0) and emits reports/judge_group_c_report.json.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from crawler.eval.agent_improvement_loop import evaluate_worker_output
from crawler.eval.judge_group_c import (
    CATEGORY_C_DOC_TYPES,
    load_test_fixtures,
    main as judge_main,
    run_group_c_judge,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORT_PATH = _REPO_ROOT / "reports" / "judge_group_c_report.json"
_EXPECTED_DOC_TYPES = 6
_EXPECTED_FIXTURES = 48  # 6 document types x 4 cases x 2 variants


class TestJudgeGroupC(unittest.TestCase):
    """End-to-end verification of the Category C parallel judge shard."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = load_test_fixtures()
        cls.report = run_group_c_judge(cls.fixtures)

    def test_scopes_to_category_c_only(self) -> None:
        """The judge evaluates exactly the 6 Category C doc types, both variants."""
        self.assertEqual(self.report["fixtures_evaluated"], _EXPECTED_FIXTURES)
        self.assertEqual(self.report["unique_doc_types"], _EXPECTED_DOC_TYPES)
        doc_types = {r["doc_type"] for r in self.report["results"]}
        self.assertEqual(doc_types, set(CATEGORY_C_DOC_TYPES))
        for r in self.report["results"]:
            self.assertIn(r["variant"], {"vector", "scanned"})

    def test_verification_targets_met(self) -> None:
        """Grounding, defect recall, and PII containment all hit the 100% target."""
        v = self.report["verification"]
        self.assertTrue(v["grounding_accuracy"]["pass"])
        self.assertEqual(v["grounding_accuracy"]["actual"], 1.0)
        self.assertTrue(v["defect_recall_rate"]["pass"])
        self.assertEqual(v["defect_recall_rate"]["actual"], 1.0)
        self.assertTrue(v["pii_containment"]["pass"])
        self.assertEqual(v["pii_containment"]["actual"], 1.0)

    def test_all_fixtures_clean(self) -> None:
        """Every Category C fixture passes the judge with perfect per-fixture metrics."""
        self.assertEqual(self.report["fixtures_clean"], _EXPECTED_FIXTURES)
        self.assertEqual(self.report["clean_rate"], 1.0)
        self.assertEqual(self.report["failure_summary"], [])
        for r in self.report["results"]:
            m = r["metrics"]
            label = f"{r['doc_type']}/{r['variant']}"
            self.assertEqual(m["grounding_accuracy"], 1.0, f"grounding<1 for {label}")
            self.assertEqual(m["defect_recall_rate"], 1.0, f"recall<1 for {label}")
            self.assertEqual(m["pii_containment_compliance"], 1.0, f"pii<1 for {label}")
            self.assertTrue(r["passed"], f"not clean for {label}")

    def test_pii_confined_to_basis(self) -> None:
        """Applicant PII is located in basis[] and never leaks to the public surface."""
        for r in self.report["results"]:
            pii = r["pii_containment"]
            self.assertTrue(pii["confined_to_basis"], f"pii leaked for {r['doc_id']}")
            self.assertEqual(pii["pii_values_leaked_to_public_surface"], 0)
            self.assertEqual(pii["leaked_values"], [])
            # PII must be substantively present in the basis[] partition, not absent.
            self.assertGreater(pii["pii_values_found_in_basis"], 0, f"no PII in basis for {r['doc_id']}")

    def test_grounding_requires_citations_and_verbatim_quotes(self) -> None:
        """Every worker claim carries a citable source and a verbatim quote."""
        for r in self.report["results"]:
            g = r["grounding"]
            self.assertTrue(g["verbatim_quotes_verified"], f"quotes unverified for {r['doc_id']}")
            self.assertEqual(g["claims_grounded"], g["claims_total"])
            self.assertTrue(g["citable_sources"], f"no citable sources for {r['doc_id']}")
            for source in g["citable_sources"]:
                self.assertIn("#", source, f"citation lacks chunk anchor: {source}")

    def test_judge_flags_ungrounded_claim(self) -> None:
        """An ungrounded worker claim (no citation/quote) fails the shared judge scoring."""
        gt = {"doc_type": "proof_of_funds", "injected_defects": [], "fields": {}}
        ungrounded = {
            "claims": [{"id": "c1", "text": "ok", "citations": [], "quote": ""}],
            "basis": [],
            "abstentions": [],
            "prose": "",
        }
        res = evaluate_worker_output(ungrounded, gt)
        self.assertEqual(res["grounding_score"], 0.0)
        self.assertFalse(res["overall_clean"])

    def test_judge_flags_pii_leak_into_public_surface(self) -> None:
        """Applicant PII surfacing in a public claim fails the Category C PII check."""
        gt = {
            "doc_type": "proof_of_funds",
            "injected_defects": [],
            "fields": {"account_number": "ACCT-981204"},
        }
        leaky = {
            "claims": [{"id": "c1", "text": "balance for ACCT-981204", "citations": ["x"], "quote": "q"}],
            "basis": [],
            "abstentions": [],
            "prose": "",
        }
        res = evaluate_worker_output(leaky, gt)
        self.assertFalse(res["pii_clean"])
        self.assertIn("ACCT-981204", res["pii_violations"])

    def test_main_returns_zero_and_writes_report(self) -> None:
        """`main()` runs clean, returns exit code 0, and emits a structured report."""
        rc = judge_main()
        self.assertEqual(rc, 0)
        self.assertTrue(_REPORT_PATH.is_file())
        data = json.loads(_REPORT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["judge_agent"]["category"], "C")
        self.assertEqual(data["judge_agent"]["model"], "claude-opus-4.8")
        self.assertEqual(data["clean_rate"], 1.0)
        self.assertEqual(data["fixtures_clean"], _EXPECTED_FIXTURES)


if __name__ == "__main__":
    unittest.main()
