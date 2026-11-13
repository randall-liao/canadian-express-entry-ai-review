"""Deprecated Legacy Self-Optimizer Module.

This legacy module formerly generated fake patch proposals from benchmark results.
It has been deprecated per Phase 74 contracts (D-15..D-18).
All candidate optimization is driven by crawler.eval.genuine_optimizer and crawler.eval.patch_evaluator.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Sequence


class SelfOptimizer:
    """Deprecated self-optimizer stub delegating to real optimizer modules."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def apply_optimization_pass(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError(
            "apply_optimization_pass is disabled per Phase 74 contracts. "
            "Use run_candidate_optimization_pass in crawler.eval.genuine_optimizer."
        )


def main(argv: Sequence[str] | None = None) -> int:
    print("self_optimizer is deprecated. Use crawler.eval.loop_orchestrator instead.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
