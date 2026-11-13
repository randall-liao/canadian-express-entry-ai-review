"""Deprecated Legacy Benchmark Runner Module.

This legacy module formerly produced synthetic document reviews and fake benchmark metrics.
It has been deprecated per Phase 74 contracts (D-04, D-11, D-21).
All evaluation is driven by crawler.eval.pipeline_judge and crawler.eval.loop_orchestrator.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Sequence


class BenchmarkRunner:
    """Deprecated benchmark runner stub delegating to real pipeline modules."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def generate_synthetic_doc_review(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError(
            "generate_synthetic_doc_review is disabled per Phase 74 contracts. "
            "Use run_blind_worker_task in crawler.eval.pipeline_worker."
        )

    def run_benchmark(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError(
            "run_benchmark with synthetic reviews is disabled. "
            "Use LoopOrchestrator in crawler.eval.loop_orchestrator."
        )


def main(argv: Sequence[str] | None = None) -> int:
    print("benchmark_runner is deprecated. Use crawler.eval.loop_orchestrator instead.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
