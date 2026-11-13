"""Tests for the live Copilot Worker/Judge execution engine."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from crawler.eval import genuine_optimizer, real_judge, real_worker


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_REPORTS = _REPO_ROOT / "reports" / "test_real_llm_engine"


def _answer() -> dict:
    return {
        "question": "Review the passport",
        "claims": [],
        "basis": ["Synthetic document reviewed."],
        "abstentions": [{"text": "No corpus proof.", "reason": "not_in_corpus"}],
        "prose": "The review abstained.",
    }


class TestRealWorker(unittest.TestCase):
    def tearDown(self) -> None:
        shutil.rmtree(_TEST_REPORTS, ignore_errors=True)

    def test_parses_fenced_answer_object(self) -> None:
        parsed = real_worker._extract_json_object(
            "Model preface\n```json\n" + json.dumps(_answer()) + "\n```\n"
        )
        self.assertEqual(parsed, _answer())

    @mock.patch("crawler.eval.real_worker.subprocess.run")
    def test_runs_exact_worker_model_and_persists_authentic_output(self, run: mock.Mock) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(_answer()), stderr=""
        )

        with mock.patch.object(real_worker, "_WORKER_OUTPUTS_DIR", _TEST_REPORTS):
            output = real_worker.run_worker_review_task(
                "passport",
                _REPO_ROOT / "crawler/eval/test_data/case_001_vec.pdf",
                "case_001_vec",
                extracted_text="SYNTHETIC PASSPORT TEXT",
            )

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/home/linuxbrew/.linuxbrew/bin/copilot")
        self.assertEqual(
            command[3:],
            ["--allow-all", "--model", "gemini-3.6-flash", "-s"],
        )
        self.assertEqual(output["_execution"]["status"], "success")
        persisted = json.loads((_TEST_REPORTS / "case_001_vec.json").read_text())
        self.assertEqual(persisted["question"], _answer()["question"])
        self.assertEqual(persisted["_execution"]["model"], "gemini-3.6-flash")

    @mock.patch("crawler.eval.real_worker.subprocess.run")
    def test_failure_never_persists_mock_answer(self, run: mock.Mock) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="model unavailable"
        )
        _TEST_REPORTS.mkdir(parents=True, exist_ok=True)
        stale = _TEST_REPORTS / "case_failure.json"
        stale.write_text(json.dumps(_answer()), encoding="utf-8")

        with mock.patch.object(real_worker, "_WORKER_OUTPUTS_DIR", _TEST_REPORTS):
            with self.assertRaises(real_worker.CopilotExecutionError):
                real_worker.run_worker_review_task(
                    "passport", "unused.pdf", "case_failure", extracted_text="text"
                )

        self.assertFalse(stale.exists())
        error = json.loads((_TEST_REPORTS / "case_failure.error.json").read_text())
        self.assertEqual(error["status"], "failed")


class TestRealJudge(unittest.TestCase):
    @mock.patch("crawler.eval.real_judge.subprocess.run")
    @mock.patch("crawler.eval.real_judge.extract_document_text", return_value="DOCUMENT TEXT")
    @mock.patch("crawler.eval.real_judge.run_worker_review_task")
    def test_runs_exact_judge_model_with_all_evidence(
        self,
        worker: mock.Mock,
        _extract: mock.Mock,
        run: mock.Mock,
    ) -> None:
        worker.return_value = {
            **_answer(),
            "_execution": {"status": "success", "model": "gemini-3.6-flash"},
        }
        evaluation = {
            "verdict": "PASS",
            "passed": True,
            "scores": {
                "grounding_accuracy": 1.0,
                "citation_exactness": 1.0,
                "defect_recall": 1.0,
                "pii_containment": 1.0,
            },
            "defects_detected": [],
            "defects_missed": [],
            "findings": [],
            "rationale": "All criteria passed.",
        }
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(evaluation), stderr=""
        )

        with mock.patch.object(real_judge, "_WORKER_OUTPUTS_DIR", _TEST_REPORTS):
            result = real_judge.judge_real_worker_output("case_001_vec")

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/home/linuxbrew/.linuxbrew/bin/copilot")
        self.assertEqual(
            command[3:],
            [
                "--allow-all",
                "--model",
                "claude-opus-4.8",
                "--effort",
                "xhigh",
                "-s",
            ],
        )
        prompt = command[2]
        self.assertIn("DOCUMENT TEXT", prompt)
        self.assertIn('"case_id": "case_001_vec"', prompt)
        self.assertIn(_answer()["question"], prompt)
        self.assertTrue(result["passed"])
        self.assertEqual(result["execution"]["status"], "success")


class TestGenuineOptimizer(unittest.TestCase):
    def tearDown(self) -> None:
        shutil.rmtree(_TEST_REPORTS, ignore_errors=True)

    def test_clear_worker_cache_removes_success_and_error_outputs(self) -> None:
        _TEST_REPORTS.mkdir(parents=True, exist_ok=True)
        (_TEST_REPORTS / "case.json").write_text("{}", encoding="utf-8")
        (_TEST_REPORTS / "case.error.json").write_text("{}", encoding="utf-8")

        with mock.patch.object(genuine_optimizer, "_WORKER_OUTPUTS_DIR", _TEST_REPORTS):
            cleared = genuine_optimizer._clear_worker_output_cache()

        self.assertEqual(cleared, 2)
        self.assertEqual(list(_TEST_REPORTS.glob("*.json")), [])

    def test_optimization_records_fresh_before_after_delta(self) -> None:
        before = {
            "timestamp": "before",
            "total_cases": 2,
            "passed_cases": 1,
            "judge_calls_succeeded": 2,
            "score": 0.5,
            "metrics": {"defect_recall": 0.5},
            "categories": {},
        }
        after = {
            "timestamp": "after",
            "total_cases": 2,
            "passed_cases": 2,
            "judge_calls_succeeded": 2,
            "score": 1.0,
            "metrics": {"defect_recall": 1.0},
            "categories": {},
        }
        with (
            mock.patch.object(
                genuine_optimizer, "_clear_worker_output_cache", side_effect=[3, 2]
            ) as clear,
            mock.patch.object(
                genuine_optimizer, "_run_evaluation_pass", side_effect=[before, after]
            ),
            mock.patch.object(
                genuine_optimizer,
                "apply_prompt_and_skill_patches",
                return_value={"AGENTS.md": "patched"},
            ),
            mock.patch.object(genuine_optimizer, "_REPORTS_DIR", _TEST_REPORTS),
        ):
            report = genuine_optimizer.run_genuine_optimization_loop()

        self.assertEqual(clear.call_count, 2)
        self.assertEqual(report["before"], before)
        self.assertEqual(report["after"], after)
        self.assertEqual(report["score_delta"], 0.5)
        self.assertEqual(report["metric_deltas"]["defect_recall"], 0.5)
        self.assertEqual(
            report["execution"]["worker_cache_entries_cleared"],
            {"before_pass": 3, "after_patches": 2},
        )


if __name__ == "__main__":
    unittest.main()
