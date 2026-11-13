#!/usr/bin/env python3
"""Single authoritative v4.x + v5 safety-conformance entry point.

Runs the WHOLE v4.0 + v4.1 + v5 safety conformance layer — every
``crawler/tests/test_conformance_v4[01]_*.py`` module (v4.0 SAFE-01..04 +
v4.1 SAFE-05 coverage/no-false-green, SAFE-06 remediation/packet privacy,
SAFE-07 grounding/determinism/screening, SAFE-08 the release-gate self-check) and
every ``crawler/tests/test_conformance_v5_*.py`` module (SAFE-09..12) — under
ONE reproducible command so the milestone audit runs the complete bounded flow::

    .venv/bin/python scripts/run_conformance.py

It selects the suite by a deterministic, marker-INDEPENDENT bounded glob union.
A real run first discovers the clean node manifest, then executes the same suite
and refuses PASS unless every discovered node ran and passed with no deselection,
skip, or xfail. Pass ``--collect-only`` (or ``--list``) to enumerate coverage.
Only presentation-only pytest flags are accepted; selectors are rejected.

On a REAL run it exports the guard env var ``PR_CONFORMANCE_RUNNER=1`` so the
release-gate test can detect it is running inside the gate and avoid a recursive
invocation. Pure stdlib only (``argparse`` / ``os`` / ``subprocess`` / ``sys``) —
NO new dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GLOBS = (
    "crawler/tests/test_conformance_v4[01]_*.py",
    "crawler/tests/test_conformance_v5_*.py",
)
_GUARD_ENV = "PR_CONFORMANCE_RUNNER"
_REPORT_ENV = "PR_CONFORMANCE_REPORT"
_PLUGIN = "scripts.conformance_report_plugin"
_DISCOVERY_ERROR = 2
_SAFE_FLAG = re.compile(r"^-[qv]+$")
_SAFE_OPTIONS = frozenset({
    "-s",
    "--disable-warnings",
    "--no-header",
    "--no-summary",
})
_SAFE_PREFIXES = (
    "--capture=",
    "--color=",
    "--show-capture=",
    "--tb=",
)
_INHERITED_PYTEST_ENV = (
    "PYTEST_ADDOPTS",
    "PYTEST_CURRENT_TEST",
    "PYTEST_PLUGINS",
)

# These modules are release prerequisites, not an opportunistic glob result.
# Keep the set literal so deleting or renaming any proof fails before pytest.
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

# The SAFE criteria named in the banner. One command runs the complete flow.
_SAFE_CRITERIA = (
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
)


def conformance_modules() -> list[Path]:
    """Resolve the sorted, deduplicated bounded release-suite union on disk."""
    return sorted({
        path
        for pattern in _GLOBS
        for path in _REPO_ROOT.glob(pattern)
    })


def _discovery_error(modules: list[Path]) -> str | None:
    """Return a stable PII-free diagnostic when release discovery is incomplete."""
    if not modules:
        return "no modules matched bounded release globs"
    names = {path.name for path in modules}
    if not any(name.startswith("test_conformance_v5_") for name in names):
        return "no v5 modules matched bounded release glob"
    missing = sorted(_REQUIRED_MODULES - names)
    if missing:
        return f"missing required modules: {', '.join(missing)}"
    return None


def _collection_error(nodeids: list[str]) -> str | None:
    """Require at least one concretely discovered test from every named module."""
    for module in sorted(_REQUIRED_MODULES):
        prefix = f"crawler/tests/{module}::"
        if not any(nodeid.startswith(prefix) for nodeid in nodeids):
            return f"required module collected zero tests: {module}"
    return None


def _passthrough_error(arguments: list[str]) -> str | None:
    """Reject every non-presentation pytest argument with one stable diagnostic."""
    for argument in arguments:
        if (
            _SAFE_FLAG.fullmatch(argument)
            or argument in _SAFE_OPTIONS
            or any(argument.startswith(prefix) for prefix in _SAFE_PREFIXES)
        ):
            continue
        return "selection or execution-changing pytest arguments are not allowed"
    return None


def _load_report(path: Path) -> dict | None:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return report if isinstance(report, dict) else None


def _pytest_env() -> dict[str, str]:
    """Return an isolated child environment for authoritative pytest processes."""
    env = dict(os.environ)
    for name in _INHERITED_PYTEST_ENV:
        env.pop(name, None)
    # Built-in plugins and registered markers from pyproject.toml remain available.
    # Third-party pytest11 entry points are not part of the reviewed release runner.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def _execution_error(expected: list[str], report: dict | None) -> str | None:
    """Validate exact collection and one clean passing call per expected node."""
    if report is None:
        return "pytest completeness report unavailable"
    collected = report.get("collected")
    deselected = report.get("deselected")
    reports = report.get("reports")
    if collected != expected:
        return "executed node manifest differs from clean discovery"
    if deselected != []:
        return "authoritative run deselected conformance nodes"
    if not isinstance(reports, list):
        return "pytest completeness report unavailable"

    calls: dict[str, int] = {nodeid: 0 for nodeid in expected}
    for item in reports:
        if not isinstance(item, dict):
            return "pytest completeness report unavailable"
        nodeid = item.get("nodeid")
        if nodeid not in calls:
            return "pytest reported an unexpected conformance node"
        if item.get("outcome") != "passed" or item.get("wasxfail") is not False:
            return "authoritative run contains a non-passing test outcome"
        if item.get("when") == "call" and item.get("subtest", False) is False:
            calls[nodeid] += 1
    if any(count != 1 for count in calls.values()):
        return "not every discovered conformance node executed exactly once"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_conformance",
        description="v4.x + v5 safety conformance release gate (SAFE-01..12).",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--collect-only", "--list", dest="collect_only", action="store_true",
        help="enumerate the conformance suite WITHOUT executing it")
    args, passthrough = parser.parse_known_args(argv)

    modules = conformance_modules()
    discovery_error = _discovery_error(modules)
    if discovery_error is not None:
        print(f"conformance gate: {discovery_error}", file=sys.stderr)
        return _DISCOVERY_ERROR
    passthrough_error = _passthrough_error(passthrough)
    if passthrough_error is not None:
        print(f"conformance gate: {passthrough_error}", file=sys.stderr)
        return _DISCOVERY_ERROR

    rel_modules = [str(m.relative_to(_REPO_ROOT)) for m in modules]
    env = _pytest_env()
    if not args.collect_only:
        # A REAL run — the release-gate test detects this and avoids recursion.
        env[_GUARD_ENV] = "1"

    criteria = ", ".join(name for name, _ in _SAFE_CRITERIA)
    print(f"== v4.x + v5 safety conformance gate — {criteria} ==")
    print(f"   modules: {[m.name for m in modules]}")

    if args.collect_only:
        cmd = [
            sys.executable, "-m", "pytest", *rel_modules,
            "--collect-only", *passthrough,
        ]
        proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), env=env)
        rc = proc.returncode
        print(f"== conformance gate: collected (no execution), pytest rc={rc} ==")
        return rc

    with tempfile.TemporaryDirectory(prefix="pr-conformance-") as raw_temp:
        temporary = Path(raw_temp)
        discovery_report = temporary / "discovery.json"
        discovery_env = dict(env)
        discovery_env[_REPORT_ENV] = str(discovery_report)
        discovery_cmd = [
            sys.executable, "-m", "pytest", "-p", _PLUGIN,
            *rel_modules, "--collect-only", "-q",
        ]
        discovery = subprocess.run(
            discovery_cmd,
            cwd=str(_REPO_ROOT),
            env=discovery_env,
            capture_output=True,
            text=True,
        )
        discovered = _load_report(discovery_report)
        if (
            discovery.returncode != 0
            or discovered is None
            or not isinstance(discovered.get("collected"), list)
            or discovered.get("deselected") != []
            or not discovered["collected"]
        ):
            print("conformance gate: clean node discovery failed", file=sys.stderr)
            return discovery.returncode or _DISCOVERY_ERROR

        expected = discovered["collected"]
        collection_error = _collection_error(expected)
        if collection_error is not None:
            print(f"conformance gate: {collection_error}", file=sys.stderr)
            return _DISCOVERY_ERROR
        execution_report = temporary / "execution.json"
        execution_env = dict(env)
        execution_env[_REPORT_ENV] = str(execution_report)
        cmd = [
            sys.executable, "-m", "pytest", "-p", _PLUGIN,
            *rel_modules, *passthrough,
        ]
        proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), env=execution_env)
        rc = proc.returncode
        completeness_error = _execution_error(
            expected, _load_report(execution_report)
        )

    if rc != 0:
        print(f"== conformance gate: FAIL — pytest rc={rc} ==")
        return rc
    if completeness_error is not None:
        print(f"conformance gate: {completeness_error}", file=sys.stderr)
        return _DISCOVERY_ERROR
    print(f"== conformance gate: PASS — {criteria} ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
