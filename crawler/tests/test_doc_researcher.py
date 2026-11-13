"""Unit contract test suite for crawler/eval/doc_researcher.py."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler.eval import doc_researcher
from crawler.eval.doc_researcher import (
    AuthorityClassification,
    CopilotExecutionError,
    FailureMode,
    ResearchReport,
    _discover_copilot_executable,
    _validate_research_schema,
    research_document_failure_modes,
    verify_policy_assertion_locally,
)


def _valid_failure_mode(
    failure_id: str = "PFL-PASS-01",
    authority: str = "authoritative",
) -> dict:
    ev = (
        [{"citation": "chunk_passport_1", "quote": "Names must match civil status documents exactly."}]
        if authority == "authoritative"
        else []
    )
    cites = ["chunk_passport_1"] if authority == "authoritative" else []
    return {
        "failure_id": failure_id,
        "category": "passport_mismatch",
        "severity": "critical",
        "title": "Passport bio data mismatch",
        "description": "Passport bio page name does not match Express Entry profile.",
        "affected_fields": ["given_name", "date_of_birth"],
        "authority_classification": authority,
        "source_url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/passport.html",
        "retrieval_date": "2026-07-22",
        "supporting_excerpt": "Names must match civil status documents exactly.",
        "remediation_hypothesis": "Provide legal name change certificate or updated passport.",
        "local_corpus_verified": authority == "authoritative",
        "local_corpus_citations": cites,
        "local_corpus_evidence": ev,
    }


def _valid_research_payload(
    doc_type: str = "passport",
    authority: str = "authoritative",
) -> dict:
    return {
        "doc_type": doc_type,
        "timestamp": "2026-07-22T22:00:00Z",
        "summary": "Research findings for passport",
        "failure_modes": [
            _valid_failure_mode("PFL-PASS-01", authority),
            _valid_failure_mode("PFL-PASS-02", authority),
            _valid_failure_mode("PFL-PASS-03", authority),
        ],
    }


def _make_jsonl_response(
    payload: dict,
    tool_calls: list[str] | None = None,
    extra_assistant_msg: str | None = None,
) -> str:
    if tool_calls is None:
        tool_calls = ["web_search", "web_fetch"]
    lines = [
        json.dumps({"type": "session.start", "data": {"session_id": "test-session"}}),
    ]
    for tc in tool_calls:
        lines.append(
            json.dumps(
                {
                    "type": "tool.execution_start",
                    "data": {"toolCall": {"name": tc, "args": {}}},
                }
            )
        )
    if extra_assistant_msg:
        lines.append(
            json.dumps(
                {
                    "type": "assistant.message",
                    "data": {"content": extra_assistant_msg},
                }
            )
        )
    lines.append(
        json.dumps(
            {
                "type": "assistant.message",
                "data": {"content": json.dumps(payload)},
            }
        )
    )
    return "\n".join(lines)


class TestDocResearcher(unittest.TestCase):
    def test_research_schema_validation(self) -> None:
        """Verify that _validate_research_schema validates valid dicts and rejects invalid dicts."""
        payload = _valid_research_payload("passport")
        report = _validate_research_schema(payload, "passport")
        self.assertIsInstance(report, ResearchReport)
        self.assertEqual(report.doc_type, "passport")
        self.assertEqual(len(report.failure_modes), 3)

        # Mismatched doc_type
        with self.assertRaises(ValueError):
            _validate_research_schema(payload, "language_test")

        # Missing required field in failure_mode
        invalid_payload = _valid_research_payload("passport")
        del invalid_payload["failure_modes"][0]["remediation_hypothesis"]
        invalid_payload["failure_modes"][0].pop("remediation", None)
        with self.assertRaises(ValueError):
            _validate_research_schema(invalid_payload, "passport")

        # Insufficient failure modes (< 3)
        short_payload = _valid_research_payload("passport")
        short_payload["failure_modes"] = short_payload["failure_modes"][:2]
        with self.assertRaises(ValueError):
            _validate_research_schema(short_payload, "passport")

    @mock.patch("crawler.eval.doc_researcher._discover_copilot_executable")
    def test_blocked_pipeline_no_fallback(self, mock_discover: mock.Mock) -> None:
        """Verify CLI failure raises CopilotExecutionError, unlinks stale success JSON, and records error JSON."""
        mock_discover.return_value = "/bin/copilot"

        def failing_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr="Copilot CLI authentication failure",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pipeline_dir = tmp_path / "passport" / "research"
            pipeline_dir.mkdir(parents=True, exist_ok=True)
            stale_file = pipeline_dir / "research.json"
            stale_file.write_text(json.dumps({"stale": True}), encoding="utf-8")

            with self.assertRaises(CopilotExecutionError):
                research_document_failure_modes(
                    "passport",
                    copilot_runner=failing_runner,
                    pipeline_root=tmp_path,
                )

            self.assertFalse(stale_file.exists(), "Stale research.json must be unlinked on failure")
            error_file = pipeline_dir / "research.error.json"
            self.assertTrue(error_file.exists(), "research.error.json must be written on failure")

            error_data = json.loads(error_file.read_text(encoding="utf-8"))
            self.assertEqual(error_data["doc_type"], "passport")
            self.assertEqual(error_data["execution"]["status"], "failed")
            self.assertEqual(error_data["execution"]["engine"], "injected-test-runner")
            self.assertFalse(error_data["execution"]["is_live"])

    def test_injected_copilot_runner_test_double(self) -> None:
        """Verify explicit copilot_runner dependency injection truthful provenance marking."""
        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            payload = _valid_research_payload("passport")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally") as mock_gate:
                mock_gate.return_value = (True, ["chunk_123"], [{"citation": "chunk_123", "quote": "Names must match civil status documents exactly."}])
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    res = research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            self.assertEqual(res["doc_type"], "passport")
            self.assertEqual(res["execution"]["status"], "success")
            self.assertEqual(res["execution"]["engine"], "injected-test-runner")
            self.assertFalse(res["execution"]["is_live"])
            self.assertEqual(res["execution"]["model"], "gemini-3.6-flash")
            self.assertTrue(res["execution"]["online_research_performed"])
            self.assertEqual(res["execution"]["tool_calls"], ["web_search", "web_fetch"])
            self.assertEqual(res["execution"]["tool_call_count"], 2)
            self.assertEqual(res["execution"]["output_format"], "json")
            self.assertEqual(res["execution"]["stream"], "off")

    def test_valid_jsonl_parsing(self) -> None:
        """Verify valid JSONL output parsing and tool call provenance collection."""
        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            payload = _valid_research_payload("passport")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload, tool_calls=["web_search", "web_fetch"]),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    res = research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            self.assertTrue(res["execution"]["online_research_performed"])
            self.assertEqual(res["execution"]["tool_calls"], ["web_search", "web_fetch"])
            self.assertEqual(res["execution"]["tool_call_count"], 2)
            self.assertEqual(res["execution"]["output_format"], "json")
            self.assertEqual(res["execution"]["stream"], "off")

    def test_missing_web_search_fails_closed(self) -> None:
        """Verify that JSONL missing a web_search tool event fails closed and records error."""
        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            payload = _valid_research_payload("passport")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload, tool_calls=["web_fetch"]),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pipeline_dir = tmp_path / "passport" / "research"
            pipeline_dir.mkdir(parents=True, exist_ok=True)
            stale_file = pipeline_dir / "research.json"
            stale_file.write_text(json.dumps({"stale": True}), encoding="utf-8")

            with self.assertRaises(CopilotExecutionError):
                research_document_failure_modes(
                    "passport",
                    copilot_runner=mock_runner,
                    pipeline_root=tmp_path,
                )

            self.assertFalse(stale_file.exists(), "Stale research.json must be removed on failure")
            error_file = pipeline_dir / "research.error.json"
            self.assertTrue(error_file.exists(), "research.error.json must be written on failure")
            error_data = json.loads(error_file.read_text(encoding="utf-8"))
            self.assertFalse(error_data["execution"]["online_research_performed"])

    def test_malformed_jsonl_fails_closed(self) -> None:
        """Verify that malformed JSONL output fails closed."""
        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout='{"type": "session.start"}\n{invalid_json_line}',
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with self.assertRaises(CopilotExecutionError):
                research_document_failure_modes(
                    "passport",
                    copilot_runner=mock_runner,
                    pipeline_root=tmp_path,
                )

    def test_missing_final_assistant_payload_fails_closed(self) -> None:
        """Verify that JSONL lacking a valid final assistant JSON report payload fails closed."""
        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            stdout = (
                json.dumps({"type": "session.start"})
                + "\n"
                + json.dumps({"type": "tool.execution_start", "data": {"toolCall": {"name": "web_search"}}})
                + "\n"
                + json.dumps({"type": "assistant.message", "data": {"content": "Search complete but no JSON payload."}})
            )
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=stdout,
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with self.assertRaises(CopilotExecutionError):
                research_document_failure_modes(
                    "passport",
                    copilot_runner=mock_runner,
                    pipeline_root=tmp_path,
                )

    def test_no_raw_reasoning_persistence(self) -> None:
        """Verify reasoning events cannot replace or leak into the final assistant payload."""
        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            payload = _valid_research_payload("passport")
            stdout = _make_jsonl_response(
                payload,
                tool_calls=["web_search"],
                extra_assistant_msg="Internal reasoning: analyzing IRCC refusal patterns and PFL triggers...",
            )
            poisoned_payload = _valid_research_payload("language_test")
            stdout += "\n" + json.dumps(
                {
                    "type": "assistant.reasoning",
                    "data": {"content": json.dumps(poisoned_payload)},
                }
            )
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=stdout,
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    res = research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            self.assertNotIn("reasoning", res)
            self.assertNotIn("reasoning", res["execution"])
            res_str = json.dumps(res)
            self.assertNotIn("Internal reasoning", res_str)

    def test_live_copilot_runner_provenance(self) -> None:
        """Verify live subprocess execution emits engine copilot-cli and is_live true."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            payload = _valid_research_payload("passport")
            completed = subprocess.CompletedProcess(
                args=["/bin/copilot"],
                returncode=0,
                stdout=_make_jsonl_response(payload),
                stderr="",
            )
            with mock.patch("subprocess.run", return_value=completed):
                with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                    with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                        res = research_document_failure_modes(
                            "passport",
                            copilot_runner=None,
                            pipeline_root=tmp_path,
                        )

            self.assertEqual(res["doc_type"], "passport")
            self.assertEqual(res["execution"]["status"], "success")
            self.assertEqual(res["execution"]["engine"], "copilot-cli")
            self.assertTrue(res["execution"]["is_live"])
            self.assertTrue(res["execution"]["online_research_performed"])

    def test_copilot_executable_discovery(self) -> None:
        """Verify executable discovery logic for COPILOT_PATH and PATH."""
        # 1. Custom COPILOT_PATH provided and executable
        with mock.patch.dict(os.environ, {"COPILOT_PATH": "/bin/sh"}, clear=True):
            exe = _discover_copilot_executable()
            self.assertEqual(exe, "/bin/sh")

        # 2. Custom COPILOT_PATH provided but invalid
        with mock.patch.dict(os.environ, {"COPILOT_PATH": "/nonexistent/path/to/copilot"}, clear=True):
            with self.assertRaises(CopilotExecutionError):
                _discover_copilot_executable()

        # 3. Unset COPILOT_PATH, found via shutil.which
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("shutil.which", return_value="/usr/local/bin/copilot"):
                exe = _discover_copilot_executable()
                self.assertEqual(exe, "/usr/local/bin/copilot")

        # 4. Unset COPILOT_PATH, shutil.which returns None
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("shutil.which", return_value=None):
                with self.assertRaises(CopilotExecutionError):
                    _discover_copilot_executable()

    def test_copilot_command_and_capability_isolation(self) -> None:
        """Verify Copilot command flags for model, context, available tools, output format, stream off, and lack of allow-all."""
        captured_command = []

        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            captured_command.extend(cmd)
            payload = _valid_research_payload("passport")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

        # Assert model flag
        self.assertIn("--model", captured_command)
        model_idx = captured_command.index("--model")
        self.assertEqual(captured_command[model_idx + 1], "gemini-3.6-flash")

        # Assert context flag
        self.assertIn("--context", captured_command)
        context_idx = captured_command.index("--context")
        self.assertEqual(captured_command[context_idx + 1], "long_context")

        # Assert available tools flag and restriction
        self.assertIn("--available-tools", captured_command)
        tools_idx = captured_command.index("--available-tools")
        self.assertEqual(captured_command[tools_idx + 1], "web_search,web_fetch")

        # Assert output-format json and stream off flags
        self.assertIn("--output-format", captured_command)
        fmt_idx = captured_command.index("--output-format")
        self.assertEqual(captured_command[fmt_idx + 1], "json")

        self.assertIn("--stream", captured_command)
        stream_idx = captured_command.index("--stream")
        self.assertEqual(captured_command[stream_idx + 1], "off")

        # Assert noninteractive / isolation flags present
        self.assertIn("--allow-all-tools", captured_command)
        self.assertIn("--allow-all-urls", captured_command)
        self.assertIn("--disallow-temp-dir", captured_command)
        self.assertIn("--no-ask-user", captured_command)
        self.assertIn("--no-custom-instructions", captured_command)

        # Assert no forbidden flags or tool names
        self.assertNotIn("-s", captured_command)
        self.assertNotIn("--silent", captured_command)
        self.assertNotIn("--allow-all", captured_command)
        self.assertNotIn("--yolo", captured_command)
        self.assertNotIn("--allow-all-paths", captured_command)
        self.assertNotIn("--allow-tool", captured_command)
        self.assertNotIn("fetch_web_page", " ".join(captured_command))

    def test_staging_directory_isolation(self) -> None:
        """Verify runner stages Copilot execution in per-document isolated directory."""
        captured_cwds = []

        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            captured_cwds.append(cwd)
            payload = _valid_research_payload("passport")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            expected_cwd = tmp_path / "passport" / "research"
            self.assertEqual(captured_cwds, [expected_cwd])

    def test_corpus_verification_gate(self) -> None:
        """Verify that corpus verification gate sets local_corpus_verified and downgrades unverified claims."""
        payload = _valid_research_payload("passport", authority="authoritative")

        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # Case A: Policy assertion verified locally -> retains authoritative status
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally") as mock_gate:
                mock_gate.return_value = (
                    True,
                    ["chunk_passport_1"],
                    [{"citation": "chunk_passport_1", "quote": "Names must match civil status documents exactly."}],
                )
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    res = research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            mode0 = res["failure_modes"][0]
            self.assertTrue(mode0["local_corpus_verified"])
            self.assertEqual(mode0["local_corpus_citations"], ["chunk_passport_1"])
            self.assertEqual(mode0["authority_classification"], "authoritative")
            self.assertEqual(
                mode0["local_corpus_evidence"],
                [{"citation": "chunk_passport_1", "quote": "Names must match civil status documents exactly."}],
            )

            # Case B: Policy assertion NOT verified locally -> downgraded to discovery status
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally") as mock_gate:
                mock_gate.return_value = (False, [], [])
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    res = research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            mode0 = res["failure_modes"][0]
            self.assertFalse(mode0["local_corpus_verified"])
            self.assertEqual(mode0["local_corpus_citations"], [])
            self.assertEqual(mode0["local_corpus_evidence"], [])
            self.assertEqual(mode0["authority_classification"], "discovery")

    def test_concurrent_execution_isolation(self) -> None:
        """Verify bounded concurrent execution across all 23 Express Entry document types."""
        captured_cwds = set()

        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            captured_cwds.add(cwd)
            prompt_str = cmd[2] if len(cmd) > 2 else ""
            dt_match = re.search(r"type:\s*'([^']+)'", prompt_str)
            dt = dt_match.group(1) if dt_match else "passport"
            payload = _valid_research_payload(dt)
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    results = doc_researcher.research_all_document_types(
                        max_workers=4,
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            all_doc_types = [dt.value for dt in doc_researcher.ExpressEntryDocType]
            self.assertEqual(len(results), 23)
            self.assertEqual(set(results.keys()), set(all_doc_types))

            for dt in all_doc_types:
                self.assertIn(dt, results)
                expected_cwd = tmp_path / dt / "research"
                self.assertIn(expected_cwd, captured_cwds)
                res_path = expected_cwd / "research.json"
                self.assertTrue(res_path.exists(), f"research.json must exist for {dt}")

    def test_summary_markdown_and_provenance(self) -> None:
        """Verify that research_summary.md is created and execution provenance contains all required fields."""
        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            payload = _valid_research_payload("passport")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    res = research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            pipeline_dir = tmp_path / "passport" / "research"
            summary_path = pipeline_dir / "research_summary.md"
            self.assertTrue(summary_path.exists(), "research_summary.md must be generated")
            summary_content = summary_path.read_text(encoding="utf-8")
            self.assertIn("# Research Summary: passport", summary_content)
            self.assertIn("## Executive Summary", summary_content)
            self.assertIn("## Identified Failure Modes", summary_content)
            self.assertIn("PFL-PASS-01", summary_content)

            execution = res.get("execution", {})
            self.assertEqual(execution.get("status"), "success")
            self.assertEqual(execution.get("engine"), "injected-test-runner")
            self.assertFalse(execution.get("is_live"))
            self.assertEqual(execution.get("model"), "gemini-3.6-flash")
            self.assertIn("timestamp", execution)
            self.assertIn("duration_seconds", execution)
            self.assertIsInstance(execution.get("duration_seconds"), float)
            self.assertIn("command", execution)
            cmd = execution.get("command", [])
            self.assertEqual(cmd[0], "copilot")
            self.assertNotIn("-p", cmd)
            self.assertIn("prompt_sha256", execution)
            self.assertIn("raw_output_sha256", execution)
            self.assertEqual(len(execution.get("prompt_sha256", "")), 64)
            self.assertEqual(len(execution.get("raw_output_sha256", "")), 64)
            self.assertEqual(execution.get("returncode"), 0)
            self.assertIn("provenance_token", execution)
            self.assertEqual(len(execution.get("provenance_token", "")), 64)
            self.assertTrue(execution.get("online_research_performed"))
            self.assertEqual(execution.get("tool_calls"), ["web_search", "web_fetch"])
            self.assertEqual(execution.get("tool_call_count"), 2)
            self.assertEqual(execution.get("output_format"), "json")
            self.assertEqual(execution.get("stream"), "off")

    def test_successful_search_and_cite_exact_quote(self) -> None:
        """Verify two-step search+cite flow resolves exact quote substring from chunk.text."""
        search_res = {"hits": [{"chunk_id": "chunk_passport_1"}]}
        cite_res = {
            "found": True,
            "chunk": {
                "id": "chunk_passport_1",
                "text": "All given names and surnames on the passport bio page must match civil status documents exactly.",
            },
        }

        def mock_crawler(args: list[str]) -> tuple[bool, dict]:
            if args[0] == "search" and "--cite" not in args:
                return True, search_res
            if args[0] == "search" and "--cite" in args:
                return True, cite_res
            return False, {}

        with mock.patch("crawler.eval.doc_researcher._run_corpus_crawler", side_effect=mock_crawler):
            verified, citations, evidence = verify_policy_assertion_locally(
                "Passport bio data mismatch",
                candidate_quote="must match civil status documents exactly",
            )

        self.assertTrue(verified)
        self.assertEqual(citations, ["chunk_passport_1"])
        self.assertEqual(
            evidence,
            [{"citation": "chunk_passport_1", "quote": "must match civil status documents exactly"}],
        )

    def test_unresolved_citation_downgrade(self) -> None:
        """Verify search or cite returning found: false fails verification and returns empty evidence."""
        def mock_crawler(args: list[str]) -> tuple[bool, dict]:
            if "--cite" in args:
                return True, {"found": False, "chunk": None}
            return True, {"hits": [{"chunk_id": "unknown_chunk"}]}

        with mock.patch("crawler.eval.doc_researcher._run_corpus_crawler", side_effect=mock_crawler):
            verified, citations, evidence = verify_policy_assertion_locally(
                "Passport bio data mismatch",
                candidate_quote="Names must match civil status documents exactly",
            )

        self.assertFalse(verified)
        self.assertEqual(citations, [])
        self.assertEqual(evidence, [])

    def test_quote_not_in_chunk_downgrade(self) -> None:
        """Verify candidate quote missing from chunk.text fails verification and clears evidence."""
        cite_res = {
            "found": True,
            "chunk": {
                "id": "chunk_passport_1",
                "text": "Unrelated medical examination requirements for Express Entry applicants.",
            },
        }

        def mock_crawler(args: list[str]) -> tuple[bool, dict]:
            if "--cite" in args:
                return True, cite_res
            return True, {"hits": [{"chunk_id": "chunk_passport_1"}]}

        with mock.patch("crawler.eval.doc_researcher._run_corpus_crawler", side_effect=mock_crawler):
            verified, citations, evidence = verify_policy_assertion_locally(
                "Passport bio data mismatch",
                candidate_quote="Nonexistent quote string about passport names",
            )

        self.assertFalse(verified)
        self.assertEqual(citations, [])
        self.assertEqual(evidence, [])

    def test_malformed_envelope_downgrade(self) -> None:
        """Verify ok: false or malformed envelope fails closed without raising exception."""
        with mock.patch("crawler.eval.doc_researcher._run_corpus_crawler", return_value=(False, {})):
            verified, citations, evidence = verify_policy_assertion_locally("Passport query")

        self.assertFalse(verified)
        self.assertEqual(citations, [])
        self.assertEqual(evidence, [])

    def test_publish_safe_metadata(self) -> None:
        """Verify execution command contains basename copilot, no abs paths, no prompt text, and valid hashes."""
        def mock_runner(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
            payload = _valid_research_payload("passport")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout=_make_jsonl_response(payload),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    res = research_document_failure_modes(
                        "passport",
                        copilot_runner=mock_runner,
                        pipeline_root=tmp_path,
                    )

            exec_meta = res.get("execution", {})
            command = exec_meta.get("command", [])
            self.assertEqual(command[0], "copilot")
            for arg in command:
                self.assertFalse(arg.startswith("/"), f"Command arg '{arg}' must not be an absolute path")
                self.assertNotIn("-p", arg)
                self.assertNotIn("home", arg)
                self.assertNotIn("Users", arg)

            self.assertIn("prompt_sha256", exec_meta)
            self.assertIn("raw_output_sha256", exec_meta)
            self.assertEqual(len(exec_meta["prompt_sha256"]), 64)
            self.assertEqual(len(exec_meta["raw_output_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()