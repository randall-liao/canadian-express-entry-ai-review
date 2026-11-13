"""SAFE-01..12 bounded authoritative release-runner conformance."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest


pytestmark = pytest.mark.conformance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "scripts" / "run_conformance.py"
_TESTS_DIR = _REPO_ROOT / "crawler" / "tests"
_GUARD_ENV = "PR_CONFORMANCE_RUNNER"
_BOUNDED_GLOBS = (
    "test_conformance_v4[01]_*.py",
    "test_conformance_v5_*.py",
)
_REQUIRED_MODULES = frozenset({
    "test_conformance_v40_no_false_green.py",
    "test_conformance_v40_privacy_containment.py",
    "test_conformance_v40_release_gate.py",
    "test_conformance_v40_retrieve_what_you_cite.py",
    "test_conformance_v40_screening_framing.py",
    "test_conformance_v41_coverage.py",
    "test_conformance_v41_grounding.py",
    "test_conformance_v41_privacy.py",
    "test_conformance_v41_release_gate.py",
    "test_conformance_v5_grounding.py",
    "test_conformance_v5_mec_no_false_meets.py",
    "test_conformance_v5_noc_no_auto_green.py",
    "test_conformance_v5_policy_no_job_offer_green.py",
    "test_conformance_v5_privacy_release.py",
    "test_conformance_v5_release_gate.py",
    "test_conformance_v5_release_matrix.py",
    "test_conformance_v5_study_no_false_green.py",
})
_REQUIRED_NODE_IDS = (
    "test_conformance_v5_grounding.py::TestExactStaticV5Manifest"
    "::test_exact_nonempty_family_rows_and_citation_counts",
    "test_conformance_v5_mec_no_false_meets.py::TestExhaustiveMecOutcomeAlgebra"
    "::test_every_required_criterion_demotes_for_each_closed_at_risk_reason",
    "test_conformance_v5_noc_no_auto_green.py::TestNoNocPathGreens"
    "::test_no_review_outcome_is_substantiated_or_scored",
    "test_conformance_v5_policy_no_job_offer_green.py::TestNoJobOfferPathGreens"
    "::test_no_decider_outcome_is_substantiated_or_nonzero",
    "test_conformance_v5_privacy_release.py::TestPrivacyReleaseManifest"
    "::test_privacy_and_atomic_case_manifest_is_exact",
    "test_conformance_v5_release_gate.py::TestBoundedReleaseDiscovery"
    "::test_discovery_is_exact_bounded_deduplicated_union",
    "test_conformance_v5_release_matrix.py::TestIndependentMecReleaseMatrix"
    "::test_valid_controls_reach_exact_real_screen_manifests",
    "test_conformance_v5_study_no_false_green.py::TestCanonicalMembershipSynthetic"
    "::test_legitimate_multichunk_build_passes_and_each_tamper_refuses",
)


def _load_runner():
    spec = importlib.util.spec_from_file_location("_v5_release_runner", _RUNNER)
    if spec is None or spec.loader is None:  # pragma: no cover - import invariant
        raise AssertionError("release runner is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBoundedReleaseDiscovery(unittest.TestCase):
    def test_discovery_is_exact_bounded_deduplicated_union(self) -> None:
        runner = _load_runner()
        expected = sorted({
            path
            for pattern in _BOUNDED_GLOBS
            for path in _TESTS_DIR.glob(pattern)
        })
        self.assertTrue(expected, "bounded release discovery must be non-empty")
        self.assertTrue(
            any(path.name.startswith("test_conformance_v5_") for path in expected),
            "bounded release discovery must contain v5 modules",
        )
        self.assertEqual(runner.conformance_modules(), expected)
        self.assertTrue(_REQUIRED_MODULES.issubset({p.name for p in expected}))

    def test_every_selected_module_has_conformance_marker(self) -> None:
        runner = _load_runner()
        selected = runner.conformance_modules()
        self.assertTrue(selected)
        for module in selected:
            source = module.read_text(encoding="utf-8")
            self.assertIn(
                "pytestmark = pytest.mark.conformance",
                source,
                f"{module.name} missing conformance marker",
            )

    def test_collect_only_contains_every_required_module_and_exact_node(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(_RUNNER), "--collect-only", "-q"],
            cwd=str(_REPO_ROOT),
            env=dict(os.environ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        for module in sorted(_REQUIRED_MODULES):
            self.assertIn(module, proc.stdout, f"{module} not collected")
        for node_id in _REQUIRED_NODE_IDS:
            self.assertIn(node_id, proc.stdout, f"{node_id} not collected")


class TestReleaseRunnerFailureSemantics(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = _load_runner()
        self.v4 = sorted(_TESTS_DIR.glob("test_conformance_v4[01]_*.py"))
        self.v5 = sorted(_TESTS_DIR.glob("test_conformance_v5_*.py"))
        self.assertTrue(self.v4)
        self.assertTrue(self.v5)

    def _assert_pre_pytest_failure(
        self, modules: list[Path], expected_diagnostic: str
    ) -> None:
        stderr = io.StringIO()
        with mock.patch.object(
            self.runner, "conformance_modules", return_value=modules
        ), mock.patch.object(self.runner.subprocess, "run") as run, (
            contextlib.redirect_stderr(stderr)
        ):
            rc = self.runner.main([])
        self.assertNotEqual(rc, 0)
        run.assert_not_called()
        self.assertIn(expected_diagnostic, stderr.getvalue())
        self.assertNotIn(str(_REPO_ROOT), stderr.getvalue())

    @staticmethod
    def _write_report(call, *, outcome: str = "passed") -> None:
        report_path = Path(call.kwargs["env"]["PR_CONFORMANCE_REPORT"])
        command = call.args[0]
        nodeids = [
            f"crawler/tests/{name}::TestSynthetic::test_complete"
            for name in sorted(_REQUIRED_MODULES)
        ]
        reports = []
        if "--collect-only" not in command:
            reports = [
                {
                    "nodeid": nodeid,
                    "when": when,
                    "outcome": outcome,
                    "wasxfail": False,
                }
                for nodeid in nodeids
                for when in ("setup", "call", "teardown")
            ]
        report_path.write_text(
            json.dumps(
                {
                    "collected": nodeids,
                    "deselected": [],
                    "reports": reports,
                    "exitstatus": 0,
                }
            ),
            encoding="utf-8",
        )

    def _successful_subprocess(self, *args, **kwargs):
        completed = subprocess.CompletedProcess(args[0], 0)
        call = mock.Mock(args=args, kwargs=kwargs)
        if "PR_CONFORMANCE_REPORT" in kwargs.get("env", {}):
            self._write_report(call)
        return completed

    def test_empty_discovery_fails_before_pytest(self) -> None:
        self._assert_pre_pytest_failure([], "no modules matched bounded release globs")

    def test_no_v5_discovery_fails_before_pytest(self) -> None:
        self._assert_pre_pytest_failure(
            self.v4, "no v5 modules matched bounded release glob"
        )

    def test_each_missing_required_module_fails_before_pytest(self) -> None:
        for missing in sorted(_REQUIRED_MODULES):
            with self.subTest(missing=missing):
                modules = [
                    path for path in self.v4 + self.v5 if path.name != missing
                ]
                self._assert_pre_pytest_failure(
                    modules, f"missing required modules: {missing}"
                )

    def test_each_required_module_must_collect_a_nonzero_node_manifest(self) -> None:
        complete = [
            f"crawler/tests/{module}::TestProof::test_load_bearing"
            for module in sorted(_REQUIRED_MODULES)
        ]
        self.assertIsNone(self.runner._collection_error(complete))
        for missing in sorted(_REQUIRED_MODULES):
            with self.subTest(missing=missing):
                manifest = [
                    nodeid
                    for nodeid in complete
                    if not nodeid.startswith(f"crawler/tests/{missing}::")
                ]
                self.assertEqual(
                    self.runner._collection_error(manifest),
                    f"required module collected zero tests: {missing}",
                )

    def test_safe_banner_mapping_is_explicit_and_exact(self) -> None:
        self.assertEqual(
            self.runner._SAFE_CRITERIA,
            (
                ("SAFE-01", "test_conformance_v40_no_false_green.py"),
                ("SAFE-02", "test_conformance_v40_privacy_containment.py"),
                ("SAFE-03", "test_conformance_v40_retrieve_what_you_cite.py"),
                ("SAFE-04", "test_conformance_v40_screening_framing.py"),
                ("SAFE-05", "test_conformance_v41_coverage.py"),
                ("SAFE-06", "test_conformance_v41_privacy.py"),
                ("SAFE-07", "test_conformance_v41_grounding.py"),
                ("SAFE-08", "test_conformance_v41_release_gate.py"),
                ("SAFE-09", "test_conformance_v5_mec_no_false_meets.py"),
                ("SAFE-10", "test_conformance_v5_study_no_false_green.py"),
                ("SAFE-11", "test_conformance_v5_grounding.py"),
                ("SAFE-12", "test_conformance_v5_release_gate.py"),
            ),
        )

    def test_collect_and_list_are_non_recursive_and_clear_inherited_addopts(self) -> None:
        for option in ("--collect-only", "--list"):
            with self.subTest(option=option), mock.patch.dict(
                os.environ, {"PYTEST_ADDOPTS": "-k inherited"}
            ), mock.patch.object(
                self.runner.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0),
            ) as run:
                rc = self.runner.main([option, "-q"])
                self.assertEqual(rc, 0)
                command = run.call_args.args[0]
                self.assertIn("--collect-only", command)
                self.assertEqual(command[-1:], ["-q"])
                child_env = run.call_args.kwargs["env"]
                self.assertNotIn("PYTEST_ADDOPTS", child_env)
                self.assertEqual(
                    child_env.get(_GUARD_ENV), os.environ.get(_GUARD_ENV)
                )

    def test_real_run_sets_guard_uses_repo_cwd_and_propagates_exact_code(self) -> None:
        with mock.patch.dict(os.environ, {_GUARD_ENV: ""}), mock.patch.object(
            self.runner.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 17),
        ) as run:
            rc = self.runner.main(["-q"])
        self.assertEqual(rc, 17)
        self.assertEqual(run.call_args.kwargs["cwd"], str(_REPO_ROOT))
        self.assertEqual(run.call_args.kwargs["env"][_GUARD_ENV], "1")
        self.assertIn("--collect-only", run.call_args.args[0])
        self.assertIsInstance(run.call_args.args[0], list)

    def test_banner_and_pass_line_name_safe_01_through_12(self) -> None:
        stdout = io.StringIO()
        with mock.patch.object(
            self.runner.subprocess,
            "run",
            side_effect=self._successful_subprocess,
        ), contextlib.redirect_stdout(stdout):
            rc = self.runner.main([])
        self.assertEqual(rc, 0)
        rendered = stdout.getvalue()
        for number in range(1, 13):
            self.assertIn(f"SAFE-{number:02d}", rendered)
        self.assertIn("conformance gate: PASS", rendered)

    def test_authoritative_run_rejects_selection_and_early_exit_forms(self) -> None:
        unsafe = (
            ["-k", "one"],
            ["-m", "conformance"],
            ["--ignore", "crawler/tests"],
            ["--ignore-glob=*.py"],
            ["--deselect", "module.py::test_one"],
            ["crawler/tests/test_conformance_v5_release_gate.py"],
            ["module.py::test_one"],
            ["--maxfail=1"],
            ["-x"],
            ["--lf"],
            ["--ff"],
            ["--co"],
            ["--stepwise"],
            ["--sw"],
            ["--stepwise-skip"],
        )
        for arguments in unsafe:
            with self.subTest(arguments=arguments), mock.patch.object(
                self.runner.subprocess, "run"
            ) as run:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    rc = self.runner.main(list(arguments))
                self.assertNotEqual(rc, 0)
                run.assert_not_called()
                self.assertIn(
                    "selection or execution-changing pytest arguments are not allowed",
                    stderr.getvalue(),
                )

    def test_inherited_pytest_addopts_cannot_filter_authoritative_run(self) -> None:
        with mock.patch.dict(
            os.environ, {"PYTEST_ADDOPTS": "-k only_one"}, clear=False
        ), mock.patch.object(
            self.runner.subprocess, "run", side_effect=self._successful_subprocess
        ) as run:
            rc = self.runner.main(["-q"])
        self.assertEqual(rc, 0)
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertNotIn("PYTEST_ADDOPTS", call.kwargs["env"])

    def test_malicious_inherited_plugins_cannot_hide_manifest_items(self) -> None:
        """Ignore both PYTEST_PLUGINS and installed pytest11 entry-point plugins."""
        with tempfile.TemporaryDirectory(
            prefix=".plugin-isolation-", dir=_REPO_ROOT
        ) as raw_temp:
            temporary = Path(raw_temp)
            (temporary / "malicious_plugin.py").write_text(
                "def pytest_collection_modifyitems(items):\n"
                "    items.clear()\n",
                encoding="utf-8",
            )
            dist_info = temporary / "malicious_pytest-1.0.dist-info"
            dist_info.mkdir()
            (dist_info / "entry_points.txt").write_text(
                "[pytest11]\nmalicious = malicious_plugin\n",
                encoding="utf-8",
            )
            test_file = temporary / "test_plugin_isolation.py"
            test_file.write_text(
                "import pytest\n"
                "pytestmark = pytest.mark.conformance\n"
                "def test_first(): pass\n"
                "def test_second(): pass\n",
                encoding="utf-8",
            )

            inherited = dict(os.environ)
            inherited["PYTHONPATH"] = os.pathsep.join(
                filter(None, (str(temporary), inherited.get("PYTHONPATH")))
            )
            inherited["PYTEST_PLUGINS"] = "malicious_plugin"
            inherited["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "0"
            inherited["PYTEST_CURRENT_TEST"] = "attacker::selector"
            with mock.patch.dict(os.environ, inherited, clear=True):
                child_env = self.runner._pytest_env()

            self.assertNotIn("PYTEST_PLUGINS", child_env)
            self.assertNotIn("PYTEST_CURRENT_TEST", child_env)
            self.assertEqual(child_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")

            reports = []
            for mode in ("discovery", "execution"):
                report_path = temporary / f"{mode}.json"
                env = dict(child_env)
                env["PR_CONFORMANCE_REPORT"] = str(report_path)
                command = [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "scripts.conformance_report_plugin",
                    str(test_file),
                    "-q",
                ]
                if mode == "discovery":
                    command.append("--collect-only")
                proc = subprocess.run(
                    command,
                    cwd=str(_REPO_ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
                reports.append(json.loads(report_path.read_text(encoding="utf-8")))

            expected = [
                f"{test_file.relative_to(_REPO_ROOT)}::test_first",
                f"{test_file.relative_to(_REPO_ROOT)}::test_second",
            ]
            self.assertEqual(reports[0]["collected"], expected)
            self.assertEqual(reports[0]["deselected"], [])
            self.assertEqual(
                self.runner._execution_error(expected, reports[1]),
                None,
            )

    def test_zero_status_with_incomplete_manifest_never_passes(self) -> None:
        calls = 0

        def incomplete(*args, **kwargs):
            nonlocal calls
            calls += 1
            call = mock.Mock(args=args, kwargs=kwargs)
            self._write_report(call)
            if calls == 2:
                path = Path(kwargs["env"]["PR_CONFORMANCE_REPORT"])
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["collected"] = payload["collected"][:-1]
                path.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.CompletedProcess(args[0], 0)

        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(
            self.runner.subprocess, "run", side_effect=incomplete
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = self.runner.main([])
        self.assertNotEqual(rc, 0)
        self.assertNotIn("conformance gate: PASS", stdout.getvalue())
        self.assertIn("manifest differs", stderr.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
