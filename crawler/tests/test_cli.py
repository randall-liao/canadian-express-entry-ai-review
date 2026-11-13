"""Offline tests for the corpus-crawler console CLI (PKG-02).

Stdlib unittest only — NO pytest, NO crawl4ai, NO network, NO browser. These
run on a standard Python interpreter where crawl4ai is absent, which is exactly what
makes the graceful-degradation path testable. Run from the repo root::

    python -m unittest crawler.tests.test_cli -v
"""

from __future__ import annotations

import argparse
import builtins
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import crawler.cli as cli

_CRAWL4AI_PRESENT = importlib.util.find_spec("crawl4ai") is not None
_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestCliHelp(unittest.TestCase):
    def test_help_lists_subcommands(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        for sub in ("crawl", "apply-verdicts", "completeness", "report"):
            self.assertIn(sub, text)

    def test_json_argparse_error_remains_system_exit(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            self.assertRaises(SystemExit) as caught,
        ):
            cli.main(["--json", "not-a-command"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("invalid choice", err.getvalue())

    def test_cli_import_does_not_pull_crawl4ai(self) -> None:
        # Importing the CLI module must never import crawl4ai (it would break the
        # whole CLI on a lean install). Re-import is a no-op; assert it stays out
        # of sys.modules after a fresh interpreter would import only cli.
        import sys
        # cli is already imported at top; crawl4ai must not have been pulled in
        # transitively by that import.
        if not _CRAWL4AI_PRESENT:
            self.assertNotIn("crawl4ai", sys.modules)


class TestCrawlDegradation(unittest.TestCase):
    def test_crawl_degrades_gracefully(self) -> None:
        if _CRAWL4AI_PRESENT:
            self.skipTest("crawl4ai is importable in this interpreter; "
                          "degradation path not exercised")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["crawl", "--seed", "https://example.org",
                           "--out", "build/cli-test-out"])
        # Must be a returned non-zero int, NOT a raised ModuleNotFoundError.
        self.assertIsInstance(rc, int)
        self.assertNotEqual(rc, 0)
        combined = (out.getvalue() + err.getvalue()).lower()
        self.assertIn("crawl", combined)
        self.assertIn("extra", combined)

    def test_non_crawl4ai_import_error_propagates(self) -> None:
        # A broken transitive import (e.g. crawler.profile / crawler.pipeline)
        # is a genuine bug. It must NOT be disguised as a missing 'crawl' extra:
        # the handler should re-raise it rather than print the hint + return 3.
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "crawler" and fromlist and "deepcrawl" in fromlist:
                exc = ImportError("simulated breakage in crawler.profile")
                exc.name = "crawler.profile"
                raise exc
            return real_import(name, globals, locals, fromlist, level)

        args = argparse.Namespace(
            seed="https://example.org", out="build/cli-test-out",
            depth=None, max_pages=None, profile=None, source_type=None,
            include_pattern=None, label=None)

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with unittest.mock.patch.object(builtins, "__import__", fake_import):
                with self.assertRaises(ImportError) as ctx:
                    cli._cmd_crawl(args)
        # It is the real, non-crawl4ai error that surfaces...
        self.assertEqual(ctx.exception.name, "crawler.profile")
        # ...and the misleading "install the crawl extra" hint was NOT printed.
        self.assertNotIn("extra", (out.getvalue() + err.getvalue()).lower())


class TestLeanDispatch(unittest.TestCase):
    def test_report_runs_lean(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            (corpus / "doc.md").write_text(
                "---\nurl: \"https://www.canada.ca/example\"\n---\n\nBody text.\n",
                encoding="utf-8")
            (corpus / "crawl_stats.json").write_text(
                json.dumps({"seed": "https://www.canada.ca/example", "recorded": 1,
                            "skipped_stub": 0, "skipped_scope": 0, "skipped_dup": 0,
                            "depth": 2, "max_pages": 40}),
                encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["report", str(corpus)])
            self.assertIsInstance(rc, int)
            self.assertTrue((corpus / "REPORT.md").is_file(),
                            "lean report path must write REPORT.md without crawl4ai")

    def test_apply_verdicts_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["apply-verdicts", str(corpus), "--dry-run"])
            self.assertEqual(rc, 0)
            # On an empty corpus the dry-run summary is exactly "would drop 0
            # document(s); ...". Assert that specific phrasing rather than a
            # bare "0" substring that any count/path/timestamp could satisfy.
            self.assertIn("would drop 0 document(s)", out.getvalue())


class TestJsonDispatchErrors(unittest.TestCase):
    def test_unexpected_exception_is_stable_and_path_free(self) -> None:
        private_detail = "/private/vault/candidates/default/ev_secret"
        out, err = io.StringIO(), io.StringIO()
        with (
            unittest.mock.patch(
                "crawler.cli._cmd_report",
                side_effect=RuntimeError(private_detail),
            ),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            rc = cli.main(["--json", "report", "unused"])
        self.assertNotEqual(rc, 0)
        envelope = json.loads(out.getvalue())
        self.assertEqual(envelope["error"], {
            "type": "internal_error",
            "message": "unexpected internal error",
        })
        self.assertNotIn(private_detail, out.getvalue())
        self.assertNotIn("ev_secret", out.getvalue())
        self.assertEqual(err.getvalue().strip(), "unexpected internal error")
        self.assertNotIn(private_detail, err.getvalue())

    def test_control_flow_base_exceptions_propagate_without_json(self) -> None:
        for exception in (
            SystemExit(17),
            KeyboardInterrupt("/private/vault/ev_interrupt"),
            GeneratorExit("/private/vault/ev_generator"),
        ):
            with self.subTest(exception=type(exception).__name__):
                out, err = io.StringIO(), io.StringIO()
                with (
                    unittest.mock.patch(
                        "crawler.cli._cmd_report",
                        side_effect=exception,
                    ),
                    contextlib.redirect_stdout(out),
                    contextlib.redirect_stderr(err),
                    self.assertRaises(type(exception)) as caught,
                ):
                    cli.main(["--json", "report", "unused"])
                self.assertIs(caught.exception, exception)
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(err.getvalue(), "")


class TestInstalledEntrypoint(unittest.TestCase):
    @staticmethod
    def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", script, *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_control_flow_payloads_are_never_rendered(self) -> None:
        private_detail = "/private/vault/candidates/default/ev_secret"
        cases = (
            ("SystemExit", f"SystemExit({private_detail!r})", 1),
            ("SystemExit object", f"SystemExit({{'path': {private_detail!r}}})", 1),
            ("KeyboardInterrupt", f"KeyboardInterrupt({private_detail!r})", 130),
            ("GeneratorExit", f"GeneratorExit({private_detail!r})", 1),
        )
        for label, expression, expected in cases:
            with self.subTest(exception=label):
                proc = self._run(
                    "import sys\n"
                    "from crawler import cli\n"
                    f"def injected(): raise {expression}\n"
                    "cli.main = injected\n"
                    "sys.exit(cli.entrypoint())\n"
                )
                self.assertEqual(proc.returncode, expected)
                self.assertEqual(proc.stdout, "")
                self.assertEqual(proc.stderr, "")
                self.assertNotIn(private_detail, proc.stdout + proc.stderr)
                self.assertNotIn("ev_secret", proc.stdout + proc.stderr)

    def test_numeric_system_exit_codes_and_none_are_preserved(self) -> None:
        for code, expected in (("None", 0), ("17", 17)):
            with self.subTest(code=code):
                proc = self._run(
                    "import sys\n"
                    "from crawler import cli\n"
                    f"def injected(): raise SystemExit({code})\n"
                    "cli.main = injected\n"
                    "sys.exit(cli.entrypoint())\n"
                )
                self.assertEqual(proc.returncode, expected)
                self.assertEqual(proc.stdout, "")
                self.assertEqual(proc.stderr, "")

    def test_normal_installed_style_command(self) -> None:
        proc = self._run(
            "import sys\n"
            "from crawler.cli import entrypoint\n"
            "sys.exit(entrypoint())\n",
            "--help",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage:", proc.stdout)
        self.assertEqual(proc.stderr, "")


if __name__ == "__main__":
    unittest.main()
