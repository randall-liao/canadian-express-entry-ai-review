"""Tests for the Parallel Judge / Eval Agent (crawler/eval/parallel_judge.py).

Verifies the Category A ("Core Identity & Language") judge:
1. Scopes evaluation to exactly the passport, digital_photo, language_test,
   certified_translation, and proof_of_other_name document types (vector +
   scanned = 10 fixtures).
2. Enforces the three release-gate invariants (grounding accuracy, defect
   recall, PII containment) at 100% for the clean Category A fixtures.
3. Fails a fixture when PII leaks into the public surface, when a claim is
   ungrounded, or when an injected defect is missed.
4. Runs main() cleanly (exit 0) and writes reports/judge_group_<key>_report.json.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from crawler.eval.parallel_judge import (
    CATEGORY_GROUPS,
    _audit_pii_containment,
    _score_citation_exactness,
    judge_fixture,
    main as judge_main,
    run_group_judge,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CATEGORY_A_DOC_TYPES = {
    "passport",
    "digital_photo",
    "language_test",
    "certified_translation",
    "proof_of_other_name",
}


class TestParallelJudgeGroupA(unittest.TestCase):
    """End-to-end verification of the Category A parallel judge."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_group_judge("a")

    def test_category_definition(self) -> None:
        self.assertIn("a", CATEGORY_GROUPS)
        self.assertEqual(set(CATEGORY_GROUPS["a"]["doc_types"]), _CATEGORY_A_DOC_TYPES)

    def test_scopes_to_category_a_fixtures(self) -> None:
        """Exactly the 5 Category A doc types across 4 cases x 2 variants = 40 fixtures."""
        self.assertEqual(self.report["summary"]["total_fixtures"], 40)
        self.assertEqual(self.report["summary"]["unique_doc_types"], 5)
        seen = {r["doc_type"] for r in self.report["results"]}
        self.assertEqual(seen, _CATEGORY_A_DOC_TYPES)

    def test_all_invariants_perfect(self) -> None:
        """Clean Category A fixtures achieve 100% on every invariant."""
        metrics = self.report["summary"]["metrics"]
        self.assertEqual(metrics["grounding_accuracy"], 1.0)
        self.assertEqual(metrics["citation_exactness"], 1.0)
        self.assertEqual(metrics["defect_recall_rate"], 1.0)
        self.assertEqual(metrics["pii_containment_compliance"], 1.0)
        for inv in self.report["invariants"].values():
            self.assertTrue(inv["pass"])
        self.assertEqual(self.report["verdict"], "PASS")
        self.assertEqual(self.report["failure_summary"], [])

    def test_pii_confined_to_basis(self) -> None:
        """Every fixture confines applicant PII to basis[] with zero public leaks."""
        for r in self.report["results"]:
            audit = r["pii_audit"]
            self.assertEqual(audit["public_surface_leaks"], [])
            self.assertTrue(audit["pii_clean"])
            self.assertGreater(audit["pii_values_checked_count"], 0)

    def test_judge_flags_pii_leak_in_public_surface(self) -> None:
        gt = {
            "doc_type": "passport",
            "variant": "vector",
            "fields": {"full_name": "Jane Doe", "passport_number": "N9823411"},
            "injected_defects": [],
        }
        leaky_worker = {
            "claims": [{"id": "c1", "text": "Applicant Jane Doe holds passport N9823411.",
                        "citations": ["passport/passport.md#001"], "quote": "quote"}],
            "basis": ["full_name: Jane Doe"],
            "abstentions": [],
            "prose": "Reviewed passport for Jane Doe.",
        }
        audit = _audit_pii_containment(leaky_worker, gt, pdf_text="")
        self.assertFalse(audit["pii_clean"])
        self.assertIn("Jane Doe", audit["public_surface_leaks"])

    def test_judge_flags_missed_defect(self) -> None:
        fixture = {
            "pdf_path": "",
            "ground_truth": {
                "doc_type": "passport",
                "variant": "vector",
                "injected_defects": [{"category": "expired_credential"}],
                "fields": {},
            },
        }
        # Worker that ignores the defect entirely.
        from crawler.eval import parallel_judge

        original = parallel_judge.build_worker_output
        parallel_judge.build_worker_output = lambda gt: {
            "claims": [{"id": "c1", "text": "clean", "citations": ["x/x.md#1"], "quote": "q"}],
            "basis": [],
            "abstentions": [],
            "prose": "clean",
        }
        try:
            result = judge_fixture(fixture)
        finally:
            parallel_judge.build_worker_output = original
        self.assertLess(result["metrics"]["defect_recall_rate"], 1.0)
        self.assertFalse(result["passed"])

    def test_citation_exactness_scoring(self) -> None:
        exact = {"claims": [{"citations": ["a/b.md#1"], "quote": "a verbatim quote"}]}
        trivial = {"claims": [{"citations": ["a/b.md#1"], "quote": "ab"}]}
        uncited = {"claims": [{"citations": [], "quote": "a verbatim quote"}]}
        self.assertEqual(_score_citation_exactness(exact, must_abstain=False), 1.0)
        self.assertEqual(_score_citation_exactness(trivial, must_abstain=False), 0.0)
        self.assertEqual(_score_citation_exactness(uncited, must_abstain=False), 0.0)
        self.assertEqual(_score_citation_exactness({"claims": []}, must_abstain=True), 1.0)

    def test_main_writes_report(self) -> None:
        rc = judge_main(["--group", "a"])
        self.assertEqual(rc, 0)
        report_path = _REPO_ROOT / "reports" / "judge_group_a_report.json"
        self.assertTrue(report_path.is_file())
        data = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(data["category_key"], "A")
        self.assertEqual(data["verdict"], "PASS")
        self.assertEqual(data["summary"]["total_fixtures"], 40)


if __name__ == "__main__":
    unittest.main()
