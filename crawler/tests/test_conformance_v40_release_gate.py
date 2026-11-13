"""Release-gate conformance: the single entry point covers all four SAFE modules
(Phase 34 — Plan 04, Task 3).

Proves that ONE authoritative command — ``scripts/run_conformance.py`` — discovers
and collects the whole SAFE-01..04 conformance layer, WITHOUT recursively
executing the full gate. It (a) asserts the four SAFE criterion modules exist on
disk, (b) invokes the runner with ``--collect-only`` (collection, never a nested
real run) and asserts the collected node ids include a test from each of the four
SAFE modules, and (c) asserts every SAFE module (and the runner glob) carries the
``conformance`` marker so ``-m conformance`` and the glob select the same set.

Stdlib ``unittest`` ONLY — NO network. ALWAYS RUNS.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_conformance_v40_release_gate.py -q
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

# The four SAFE criteria and their authoritative conformance module filenames.
_SAFE_MODULES = (
    ("SAFE-01", "test_conformance_v40_no_false_green.py"),
    ("SAFE-02", "test_conformance_v40_privacy_containment.py"),
    ("SAFE-03", "test_conformance_v40_retrieve_what_you_cite.py"),
    ("SAFE-04", "test_conformance_v40_screening_framing.py"),
)


class TestReleaseGateEntryPoint(unittest.TestCase):
    def test_runner_exists_and_glob_resolves_to_four_safe_modules(self) -> None:
        self.assertTrue(_RUNNER.is_file(), "scripts/run_conformance.py missing")
        # The runner's own glob, evaluated on disk, must include every SAFE module.
        globbed = {p.name for p in _TESTS_DIR.glob("test_conformance_v40_*.py")}
        for _, module in _SAFE_MODULES:
            self.assertIn(module, globbed, module)
            self.assertTrue((_TESTS_DIR / module).is_file(), module)

    def test_one_command_collects_all_four_safe_modules(self) -> None:
        # --collect-only enumerates the gate WITHOUT executing it, so this can run
        # safely even inside a real gate run (no recursive re-invocation). Marking
        # the guard env documents that intent.
        env = dict(os.environ)
        env[_GUARD_ENV] = "1"
        proc = subprocess.run(
            [sys.executable, str(_RUNNER), "--collect-only", "-q"],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        collected = proc.stdout
        # One command enumerates the whole SAFE-01..04 layer.
        for criterion, module in _SAFE_MODULES:
            self.assertIn(module, collected, f"{criterion} not collected")

    def test_all_four_safe_modules_carry_the_conformance_marker(self) -> None:
        for criterion, module in _SAFE_MODULES:
            src = (_TESTS_DIR / module).read_text(encoding="utf-8")
            self.assertIn("pytestmark = pytest.mark.conformance", src,
                          f"{criterion} ({module}) missing the conformance marker")

    def test_release_gate_module_itself_carries_the_marker(self) -> None:
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("pytestmark = pytest.mark.conformance", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
