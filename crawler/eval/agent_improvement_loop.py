"""Deprecated Legacy Improvement Loop Module.

This legacy module formerly generated fake/synthetic Worker AnswerObjects and score fallbacks.
It has been deprecated per Phase 74 contracts (D-04, D-11, D-21).
All pipeline orchestration is driven by crawler.eval.loop_orchestrator.LoopOrchestrator.
"""

from __future__ import annotations

import sys
from typing import Any, Dict


def build_worker_output(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    raise NotImplementedError(
        "build_worker_output (synthetic worker simulation) is disabled. "
        "Use run_blind_worker_task in crawler.eval.pipeline_worker for real Gemini sessions."
    )


def evaluate_worker_output(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    raise NotImplementedError(
        "evaluate_worker_output is disabled. "
        "Use run_batched_document_judge in crawler.eval.pipeline_judge for privileged Opus Judge sessions."
    )


def run_eval_loop(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    raise NotImplementedError(
        "run_eval_loop is disabled. "
        "Use LoopOrchestrator in crawler.eval.loop_orchestrator for real self-improvement loops."
    )


def main() -> int:
    print("agent_improvement_loop is deprecated. Use crawler.eval.loop_orchestrator instead.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
