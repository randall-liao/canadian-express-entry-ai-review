"""Offline tests for the AGENT-01 JSON output contract.

Stdlib ``unittest`` only — NO pytest, NO crawl4ai, NO network, NO browser (per
the AGENTS.md test convention). The contract is exercised in-process via
``crawler.cli.main(...)`` with ``contextlib.redirect_*`` capture, so the suite
runs on a standard interpreter where crawl4ai is absent — which is exactly what
makes the lean-command and missing_dependency paths testable. Run from the repo
root::

    python -m unittest crawler.tests.test_json_contract -v
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import crawler.cli as cli
from crawler import completeness, contract

_CRAWL4AI_PRESENT = importlib.util.find_spec("crawl4ai") is not None


def _make_lean_corpus(corpus: Path) -> None:
    """Build a tiny lean corpus (one doc + crawl_stats.json) the report and
    apply-verdicts paths can run on without crawl4ai — mirrors test_cli."""
    (corpus / "doc.md").write_text(
        "---\nurl: \"https://www.canada.ca/example\"\n---\n\nBody text.\n",
        encoding="utf-8")
    (corpus / "crawl_stats.json").write_text(
        json.dumps({"seed": "https://www.canada.ca/example", "recorded": 1,
                    "skipped_stub": 0, "skipped_scope": 0, "skipped_dup": 0,
                    "depth": 2, "max_pages": 40}),
        encoding="utf-8")


def _run_json(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the CLI in-process, returning (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(argv)
    return rc, out.getvalue(), err.getvalue()


# --- Task 1: contract module unit tests -------------------------------------

class TestContractEnvelope(unittest.TestCase):
    def test_schema_version_constant(self) -> None:
        self.assertEqual(contract.SCHEMA_VERSION, "1.0")

    def test_ok_envelope_shape(self) -> None:
        e = contract.envelope("report", result={"verdict": "pass"})
        self.assertEqual(e["schema_version"], "1.0")
        self.assertIs(e["ok"], True)
        self.assertEqual(e["command"], "report")
        self.assertEqual(e["result"], {"verdict": "pass"})
        self.assertIsNone(e["error"])
        # Exactly the five stable keys, no more.
        self.assertEqual(set(e), {"schema_version", "ok", "command", "result", "error"})

    def test_error_envelope_shape(self) -> None:
        e = contract.envelope("crawl",
                              error=(contract.MISSING_DEPENDENCY, "crawl4ai not installed"))
        self.assertIs(e["ok"], False)
        self.assertIsNone(e["result"])
        self.assertEqual(e["error"], {"type": "missing_dependency",
                                      "message": "crawl4ai not installed"})
        self.assertEqual(e["command"], "crawl")

    def test_error_forces_result_null(self) -> None:
        # Even if a result is passed alongside an error, ok=false and result=None.
        e = contract.envelope("crawl", result={"x": 1},
                              error=(contract.INVALID_INPUT, "bad"))
        self.assertIs(e["ok"], False)
        self.assertIsNone(e["result"])

    def test_emit_writes_one_json_line(self) -> None:
        obj = contract.envelope("report", result={"verdict": "pass"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            contract.emit(obj)
        text = out.getvalue()
        # Exactly one line, json.loads-able, round-trips to the same object.
        self.assertEqual(text.count("\n"), 1)
        self.assertEqual(json.loads(text), obj)


class TestStructuredCompleteness(unittest.TestCase):
    def test_build_report_returns_structured_dict(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)
            summary = completeness.build_report(corpus)
            # Documented structured keys present.
            for key in ("verdict", "overall_pass", "out", "recorded",
                        "live_docs", "passed", "failed", "drop", "incomplete"):
                self.assertIn(key, summary)
            self.assertIn(summary["verdict"], {"pass", "fail", "incomplete"})
            self.assertIsInstance(summary["overall_pass"], bool)
            # REPORT.md is still written exactly as today.
            self.assertTrue((corpus / "REPORT.md").is_file())

    def test_run_fetch_is_importable_without_crawl4ai(self) -> None:
        # run_fetch must be a callable on the module even on a lean install; its
        # crawl4ai-requiring body is only reached via asyncio.run at call time.
        self.assertTrue(callable(completeness.run_fetch))
        # An empty corpus raises NoLiveDocsError before any crawl4ai import.
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(completeness.NoLiveDocsError):
                completeness.run_fetch(Path(td), 0.1)

    @unittest.skipIf(_CRAWL4AI_PRESENT,
                     "crawl4ai importable; failed-fetch path not exercised")
    def test_failed_fetch_leaves_no_completeness_dir(self) -> None:
        # IN-01: a failed run (crawl4ai missing) must NOT create an empty
        # completeness/ directory as a side effect.
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)  # one live doc → run_fetch reaches asyncio.run
            with self.assertRaises(ImportError):
                completeness.run_fetch(corpus, 0.1)
            self.assertFalse((corpus / "completeness").exists())


# --- Task 3: end-to-end contract behavior over the CLI (lean commands) -------

class TestJsonStdoutIsPure(unittest.TestCase):
    def test_report_json_stdout_is_single_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)
            rc, out, err = _run_json(["--json", "report", str(corpus)])
            # stdout parses as one JSON object (no human text mixed in).
            obj = json.loads(out)
            self.assertEqual(out.strip().count("\n"), 0)
            self.assertEqual(obj["schema_version"], "1.0")
            self.assertIsInstance(obj["ok"], bool)
            self.assertEqual(obj["command"], "report")
            self.assertIn("verdict", obj["result"])
            for key in ("recorded", "live_docs", "passed", "failed", "drop", "incomplete"):
                self.assertIn(key, obj["result"])

    def test_apply_verdicts_json_result_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            rc, out, err = _run_json(["--json", "apply-verdicts", str(corpus), "--dry-run"])
            obj = json.loads(out)
            self.assertIs(obj["ok"], True)
            self.assertEqual(obj["command"], "apply-verdicts")
            for key in ("dropped", "kept", "dry_run", "out"):
                self.assertIn(key, obj["result"])
            self.assertIs(obj["result"]["dry_run"], True)

    def test_completeness_json_invalid_on_empty_corpus(self) -> None:
        # No live docs to sample → invalid_input error object (does not need crawl4ai).
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            rc, out, err = _run_json(["--json", "completeness", str(corpus)])
            obj = json.loads(out)
            self.assertIs(obj["ok"], False)
            self.assertEqual(obj["error"]["type"], contract.INVALID_INPUT)
            self.assertEqual(rc, contract.EXIT_INVALID_INPUT)


class TestJsonHumanTextOnStderr(unittest.TestCase):
    def test_report_human_text_not_on_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)
            rc, out, err = _run_json(["--json", "report", str(corpus)])
            # stdout is clean JSON; the human "wrote ..."/verdict summary is NOT
            # mixed into stdout (in --json mode the compute layer prints nothing
            # to stdout — every human/progress line is kept off the JSON stream).
            json.loads(out)
            self.assertNotIn("wrote", out)
            self.assertNotIn("PASS", out)
            self.assertNotIn("FAIL", out)

    def test_completeness_human_hint_not_on_stdout(self) -> None:
        # stdout must be exactly one parseable JSON object (the error envelope);
        # no free-floating human text outside the JSON. The error *message* may
        # legitimately quote the reason, but the stream itself stays pure JSON.
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            rc, out, err = _run_json(["--json", "completeness", str(corpus)])
            obj = json.loads(out)
            self.assertIs(obj["ok"], False)
            self.assertEqual(out.strip().count("\n"), 0)


class TestJsonFailurePaths(unittest.TestCase):
    def test_report_nonexistent_corpus_is_error_object(self) -> None:
        missing = Path(tempfile.gettempdir()) / "jc-does-not-exist-xyz"
        rc, out, err = _run_json(["--json", "report", str(missing)])
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], contract.INVALID_INPUT)
        self.assertIn("type", obj["error"])
        self.assertIn("message", obj["error"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)

    def test_apply_verdicts_not_a_directory_is_error_object(self) -> None:
        missing = Path(tempfile.gettempdir()) / "jc-not-a-dir-xyz"
        rc, out, err = _run_json(["--json", "apply-verdicts", str(missing)])
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], contract.INVALID_INPUT)
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)

    @unittest.skipIf(_CRAWL4AI_PRESENT,
                     "crawl4ai importable; missing_dependency path not exercised")
    def test_crawl_missing_dependency_is_error_object(self) -> None:
        rc, out, err = _run_json(["--json", "crawl", "--seed", "https://example.org",
                                  "--out", "build/jc-crawl-out"])
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["command"], "crawl")
        self.assertEqual(obj["error"]["type"], contract.MISSING_DEPENDENCY)
        self.assertEqual(rc, contract.EXIT_MISSING_DEPENDENCY)
        # The actionable human hint still goes to stderr.
        self.assertIn("extra", err.lower())


def _make_complete_corpus(corpus: Path, *, passing: bool) -> None:
    """Build a corpus whose completeness audit is DONE so build_report yields a
    terminal pass/fail verdict (not 'incomplete'). With ``passing=True`` the
    single doc passes its eval → verdict 'pass'; with ``passing=False`` the eval
    fails (relevance below the gate) → verdict 'fail'."""
    _make_lean_corpus(corpus)
    relevance = 0.95 if passing else 0.05
    (corpus / "doc.eval.json").write_text(
        json.dumps({"doc": "doc.md", "verdict": "keep",
                    "relevance_score": relevance, "summary": "ok",
                    "url": "https://www.canada.ca/example"}),
        encoding="utf-8")
    cdir = corpus / "completeness"
    cdir.mkdir()
    (cdir / "sample.json").write_text(
        json.dumps({"fraction": 0.1, "total_live": 1, "sampled": 1,
                    "pairs": [{"doc": "doc.md"}]}),
        encoding="utf-8")
    (cdir / "doc.check.json").write_text(
        json.dumps({"doc": "doc.md", "coverage_verdict": "complete",
                    "explained_by_pruning": False}),
        encoding="utf-8")


class TestReportVerdictExitCodes(unittest.TestCase):
    """WR-02: exit 0 == verdict 'pass'; exit 1 == any non-pass verdict (both
    'fail' and 'incomplete'). The precise verdict is always in result.verdict."""

    def test_pass_verdict_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_complete_corpus(corpus, passing=True)
            rc, out, err = _run_json(["--json", "report", str(corpus)])
            obj = json.loads(out)
            self.assertEqual(obj["result"]["verdict"], "pass")
            self.assertEqual(rc, 0)

    def test_fail_verdict_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_complete_corpus(corpus, passing=False)
            rc, out, err = _run_json(["--json", "report", str(corpus)])
            obj = json.loads(out)
            self.assertEqual(obj["result"]["verdict"], "fail")
            self.assertEqual(rc, 1)

    def test_incomplete_verdict_also_exits_one(self) -> None:
        # A lean corpus with no completeness audit → verdict 'incomplete'.
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)
            rc, out, err = _run_json(["--json", "report", str(corpus)])
            obj = json.loads(out)
            self.assertEqual(obj["result"]["verdict"], "incomplete")
            self.assertIs(obj["ok"], True)  # not an execution error
            self.assertEqual(rc, 1)


class TestJsonStdoutPurityGuard(unittest.TestCase):
    """WR-01: when the underlying callee (crawl4ai for crawl / completeness
    --fetch) writes to STDOUT, the --json envelope must STILL be the only thing
    on stdout. The dispatcher redirects callee stdout to stderr. crawl4ai is not
    importable offline, so we simulate the callee printing to stdout."""

    def test_completeness_callee_stdout_does_not_corrupt_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)

            def _noisy_run_fetch(corpus_path, fraction):
                # Simulate crawl4ai logging progress to stdout mid-fetch.
                print("crawl4ai: [INIT] starting browser...")
                print("crawl4ai: fetched 1 page")
                return {"sampled": 1, "total_live": 1,
                        "fraction": fraction, "out": str(corpus_path / "completeness")}

            orig = completeness.run_fetch
            completeness.run_fetch = _noisy_run_fetch
            try:
                rc, out, err = _run_json(["--json", "completeness", str(corpus)])
            finally:
                completeness.run_fetch = orig
            # stdout is EXACTLY one parseable JSON object — the noisy prints landed
            # on stderr, not stdout.
            obj = json.loads(out)
            self.assertEqual(out.strip().count("\n"), 0)
            self.assertIs(obj["ok"], True)
            self.assertEqual(obj["command"], "completeness")
            self.assertEqual(obj["result"]["sampled"], 1)
            self.assertNotIn("crawl4ai", out)
            self.assertIn("crawl4ai", err)


class TestJsonInternalErrorEnvelope(unittest.TestCase):
    """Unexpected JSON failures use one parseable, path-free public boundary."""

    def test_report_corrupt_crawl_stats_is_internal_error(self) -> None:
        # build_report does json.loads(crawl_stats.json) with no guard.
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)
            (corpus / "crawl_stats.json").write_text("this is not json{",
                                                      encoding="utf-8")
            rc, out, err = _run_json(["--json", "report", str(corpus)])
            # stdout is STILL exactly one parseable JSON object.
            obj = json.loads(out)
            self.assertEqual(out.strip().count("\n"), 0)
            self.assertIs(obj["ok"], False)
            self.assertIsNone(obj["result"])
            self.assertEqual(obj["command"], "report")
            self.assertEqual(obj["error"]["type"], contract.INTERNAL_ERROR)
            self.assertEqual(
                obj["error"]["message"], "unexpected internal error")
            self.assertNotEqual(rc, 0)
            self.assertEqual(rc, contract.EXIT_INTERNAL_ERROR)
            # Raw traceback/exception details may contain private machine paths.
            self.assertNotIn("Traceback", out)
            self.assertNotIn("Traceback", err)
            self.assertEqual(err.strip(), "unexpected internal error")
            self.assertNotIn(str(corpus), out + err)

    def test_apply_verdicts_corrupt_dropped_log_is_internal_error(self) -> None:
        # apply() reads _dropped/dropped.log.json with bare json.loads when a
        # drop verdict is enacted — corrupt it to prove the catch-all fires.
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            (corpus / "gone.md").write_text(
                "---\nurl: \"https://www.canada.ca/gone\"\n---\n\nBody.\n",
                encoding="utf-8")
            (corpus / "gone.eval.json").write_text(
                json.dumps({"doc": "gone.md", "verdict": "drop",
                            "url": "https://www.canada.ca/gone"}),
                encoding="utf-8")
            dropped = corpus / "_dropped"
            dropped.mkdir()
            (dropped / "dropped.log.json").write_text("not json[[", encoding="utf-8")
            rc, out, err = _run_json(["--json", "apply-verdicts", str(corpus)])
            obj = json.loads(out)
            self.assertEqual(out.strip().count("\n"), 0)
            self.assertIs(obj["ok"], False)
            self.assertIsNone(obj["result"])
            self.assertEqual(obj["command"], "apply-verdicts")
            self.assertEqual(obj["error"], {
                "type": contract.INTERNAL_ERROR,
                "message": "unexpected internal error",
            })
            self.assertNotEqual(rc, 0)
            self.assertEqual(rc, contract.EXIT_INTERNAL_ERROR)
            self.assertEqual(err.strip(), "unexpected internal error")
            self.assertNotIn(str(corpus), out + err)


class TestCompletenessMissingDependencyMessage(unittest.TestCase):
    """WR-04: completeness's missing_dependency message must name the actual
    command ('completeness --fetch'), NOT 'crawl'. Reached on a lean install
    where a corpus WITH live docs hits crawl4ai's absence at asyncio.run."""

    @unittest.skipIf(_CRAWL4AI_PRESENT,
                     "crawl4ai importable; missing_dependency path not exercised")
    def test_message_names_completeness_not_crawl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)  # has a live doc → reaches the crawl4ai import
            rc, out, err = _run_json(["--json", "completeness", str(corpus)])
            obj = json.loads(out)
            self.assertIs(obj["ok"], False)
            self.assertEqual(obj["error"]["type"], contract.MISSING_DEPENDENCY)
            self.assertEqual(rc, contract.EXIT_MISSING_DEPENDENCY)
            msg = obj["error"]["message"]
            # Names the completeness step, not the crawl subcommand.
            self.assertIn("'completeness --fetch'", msg)
            self.assertNotIn("'crawl' step", msg)
            self.assertNotIn("'crawl' subcommand", msg)


class TestCrawlDefaultsSingleSourced(unittest.TestCase):
    """WR-03: the --json crawl path must NOT duplicate deepcrawl's literal
    defaults. They live in one place (deepcrawl.DEFAULT_*) so the json and
    default-mode paths cannot silently diverge. Importing deepcrawl requires
    crawl4ai, so this is gated on its presence."""

    @unittest.skipIf(not _CRAWL4AI_PRESENT, "deepcrawl import requires crawl4ai")
    def test_deepcrawl_exposes_default_constants(self) -> None:
        from crawler import deepcrawl
        self.assertEqual(deepcrawl.DEFAULT_DEPTH, 2)
        self.assertEqual(deepcrawl.DEFAULT_MAX_PAGES, 40)
        self.assertEqual(deepcrawl.DEFAULT_PROFILE, "ircc")

    def test_cli_json_crawl_does_not_hardcode_defaults(self) -> None:
        # Source-level guard that works WITHOUT crawl4ai: the --json crawl path
        # must reference deepcrawl.DEFAULT_* rather than bare literal defaults.
        import inspect
        src = inspect.getsource(cli._cmd_crawl)
        self.assertIn("deepcrawl.DEFAULT_DEPTH", src)
        self.assertIn("deepcrawl.DEFAULT_MAX_PAGES", src)
        self.assertIn("deepcrawl.DEFAULT_PROFILE", src)


class TestDefaultModeUnchanged(unittest.TestCase):
    def test_default_report_prints_human_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            _make_lean_corpus(corpus)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = cli.main(["report", str(corpus)])
            self.assertIsInstance(rc, int)
            # Default mode is byte-for-byte unchanged: human text on stdout, no JSON envelope.
            self.assertIn("wrote", out.getvalue())
            with self.assertRaises(json.JSONDecodeError):
                json.loads(out.getvalue())

    def test_default_apply_verdicts_prints_human_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["apply-verdicts", str(corpus), "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertIn("would drop 0 document(s)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
