"""Fail-closed contracts for deprecated fake benchmark/optimizer paths."""

from __future__ import annotations

import pytest

from crawler.eval.benchmark_runner import BenchmarkRunner, main as benchmark_main
from crawler.eval.self_optimizer import SelfOptimizer, main as optimizer_main


def test_legacy_benchmark_worker_generation_is_disabled() -> None:
    runner = BenchmarkRunner()

    with pytest.raises(NotImplementedError, match="run_blind_worker_task"):
        runner.generate_synthetic_doc_review({})


def test_legacy_benchmark_scoring_loop_is_disabled() -> None:
    runner = BenchmarkRunner()

    with pytest.raises(NotImplementedError, match="LoopOrchestrator"):
        runner.run_benchmark()


def test_legacy_canned_optimizer_is_disabled() -> None:
    optimizer = SelfOptimizer()

    with pytest.raises(
        NotImplementedError,
        match="run_candidate_optimization_pass",
    ):
        optimizer.apply_optimization_pass({})


@pytest.mark.parametrize("entrypoint", [benchmark_main, optimizer_main])
def test_legacy_cli_entrypoints_are_disabled(
    entrypoint,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert entrypoint([]) == 1
    assert "deprecated" in capsys.readouterr().err
