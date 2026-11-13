"""Fail-closed contracts for the deprecated fake agent improvement loop."""

from __future__ import annotations

import pytest

from crawler.eval.agent_improvement_loop import (
    build_worker_output,
    evaluate_worker_output,
    main,
    run_eval_loop,
)


@pytest.mark.parametrize(
    ("function", "replacement"),
    [
        (build_worker_output, "run_blind_worker_task"),
        (evaluate_worker_output, "run_batched_document_judge"),
        (run_eval_loop, "LoopOrchestrator"),
    ],
)
def test_legacy_fake_agent_paths_fail_closed(
    function,
    replacement: str,
) -> None:
    with pytest.raises(NotImplementedError, match=replacement):
        function({})


def test_legacy_agent_improvement_entrypoint_is_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main() == 1
    assert "deprecated" in capsys.readouterr().err
