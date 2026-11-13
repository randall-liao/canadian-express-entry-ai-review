"""Release-gate conformance: the single entry point covers the complete v4.1 flow
(Phase 39 — SAFE-08).

Proves that ONE authoritative command — ``scripts/run_conformance.py`` — discovers and
collects the whole v4.0 + v4.1 conformance layer (coverage / refusal / remediation /
packet / privacy / grounding / screening), WITHOUT recursively executing the full gate.
It (a) asserts the three v4.1 SAFE modules exist and are matched by the runner glob,
(b) invokes the runner with ``--collect-only`` and asserts the collected node ids
include a test from each v4.1 module AND the v4.0 modules (the single command exercises
the complete flow), and (c) asserts every v4.1 conformance module carries the
``conformance`` marker.

Stdlib ``unittest`` ONLY — NO network. ALWAYS RUNS.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

pytestmark = pytest.mark.conformance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "scripts" / "run_conformance.py"
_TESTS_DIR = _REPO_ROOT / "crawler" / "tests"
_GUARD_ENV = "PR_CONFORMANCE_RUNNER"

# The v4.1 SAFE criteria + their authoritative conformance module filenames.
_V41_MODULES = (
    ("SAFE-05", "test_conformance_v41_coverage.py"),
    ("SAFE-06", "test_conformance_v41_privacy.py"),
    ("SAFE-07", "test_conformance_v41_grounding.py"),
)
# A representative v4.0 module the single command must still collect.
_V40_SENTINEL = "test_conformance_v40_no_false_green.py"


class TestReleaseGateCoversV41Flow(unittest.TestCase):
    def test_runner_glob_matches_v40_and_v41_modules(self) -> None:
        self.assertTrue(_RUNNER.is_file(), "scripts/run_conformance.py missing")
        globbed = {p.name for p in _TESTS_DIR.glob("test_conformance_v4[01]_*.py")}
        for _, module in _V41_MODULES:
            self.assertIn(module, globbed, module)
            self.assertTrue((_TESTS_DIR / module).is_file(), module)
        self.assertIn(_V40_SENTINEL, globbed)

    def test_one_command_collects_the_complete_v41_flow(self) -> None:
        env = dict(os.environ)
        env[_GUARD_ENV] = "1"
        proc = subprocess.run(
            [sys.executable, str(_RUNNER), "--collect-only", "-q"],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        collected = proc.stdout
        for criterion, module in _V41_MODULES:
            self.assertIn(module, collected, f"{criterion} not collected")
        # The single command still exercises the v4.0 flow too (complete v4.x).
        self.assertIn(_V40_SENTINEL, collected)

    def test_all_v41_modules_carry_the_conformance_marker(self) -> None:
        for criterion, module in _V41_MODULES:
            src = (_TESTS_DIR / module).read_text(encoding="utf-8")
            self.assertIn("pytestmark = pytest.mark.conformance", src,
                          f"{criterion} ({module}) missing the conformance marker")

    def test_release_gate_module_itself_carries_the_marker(self) -> None:
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("pytestmark = pytest.mark.conformance", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
