"""23-document pipeline conformance test suite for Gemini 3.6 Flash research outputs.

Verifies schema compliance, source quality, citation presence, uniqueness, and cross-pipeline
isolation across all 23 Express Entry document pipeline outputs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional
from unittest import mock

from crawler.eval.doc_researcher import (
    _PIPELINES_DIR,
    _REPO_ROOT,
    ResearchReport,
    _cite_local_corpus_chunk,
    research_all_document_types,
)
from crawler.synthetic.schemas import ExpressEntryDocType

_ALL_DOC_TYPES = [dt.value for dt in ExpressEntryDocType]


def _mock_copilot_runner(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    """Mock Copilot runner test double generating valid schema-compliant research data in JSONL format."""
    prompt_str = cmd[2] if len(cmd) > 2 else ""
    dt_match = re.search(r"document type:\s*'([^']+)'", prompt_str)
    doc_type = dt_match.group(1) if dt_match else cwd.parent.name

    short_code = doc_type.upper().replace("_", "")
    payload = {
        "doc_type": doc_type,
        "timestamp": "2026-07-22T23:00:00Z",
        "summary": f"Research summary of IRCC failure cases and PFL triggers for {doc_type}.",
        "failure_modes": [
            {
                "failure_id": f"PFL-{short_code}-01",
                "category": f"{doc_type}_mismatch",
                "severity": "critical",
                "title": f"Critical {doc_type} requirement defect",
                "description": f"Primary failure mode for Express Entry document {doc_type}.",
                "affected_fields": ["primary_field", "secondary_field"],
                "authority_classification": "authoritative",
                "source_url": f"https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/{doc_type}.html",
                "retrieval_date": "2026-07-22",
                "supporting_excerpt": f"IRCC operational instructions for {doc_type}.",
                "remediation_hypothesis": f"Provide updated {doc_type} meeting IRCC criteria.",
                "local_corpus_verified": True,
                "local_corpus_citations": [f"chunk_{short_code}_01"],
                "local_corpus_evidence": [
                    {"citation": f"chunk_{short_code}_01", "quote": f"IRCC operational instructions for {doc_type}."}
                ],
            },
            {
                "failure_id": f"PFL-{short_code}-02",
                "category": f"{doc_type}_validity",
                "severity": "critical",
                "title": f"Expired or invalid {doc_type} issue",
                "description": f"Validity period or date defect for {doc_type}.",
                "affected_fields": ["issue_date", "expiry_date"],
                "authority_classification": "authoritative",
                "source_url": f"https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/{doc_type}.html",
                "retrieval_date": "2026-07-22",
                "supporting_excerpt": f"Validity regulations for {doc_type}.",
                "remediation_hypothesis": f"Obtain re-issued {doc_type} with valid coverage.",
                "local_corpus_verified": True,
                "local_corpus_citations": [f"chunk_{short_code}_02"],
                "local_corpus_evidence": [
                    {"citation": f"chunk_{short_code}_02", "quote": f"Validity regulations for {doc_type}."}
                ],
            },
            {
                "failure_id": f"PFL-{short_code}-03",
                "category": f"{doc_type}_omission",
                "severity": "warning",
                "title": f"Missing mandatory field in {doc_type}",
                "description": f"Incomplete detail or missing endorsement in {doc_type}.",
                "affected_fields": ["endorsement_seal", "signature"],
                "authority_classification": "discovery",
                "source_url": f"https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/documents/{doc_type}.html",
                "retrieval_date": "2026-07-22",
                "supporting_excerpt": f"Completeness checklist for {doc_type}.",
                "remediation_hypothesis": f"Submit supplementary explanation or completed {doc_type}.",
                "local_corpus_verified": False,
                "local_corpus_citations": [],
                "local_corpus_evidence": [],
            },
        ],
    }

    jsonl_lines = [
        json.dumps({"type": "session.start", "data": {"session_id": "test-session"}}),
        json.dumps({"type": "tool.execution_start", "data": {"toolCall": {"name": "web_search", "args": {"query": doc_type}}}}),
        json.dumps({"type": "tool.execution_start", "data": {"toolCall": {"name": "web_fetch", "args": {"url": "https://www.canada.ca"}}}}),
        json.dumps({"type": "assistant.message", "data": {"content": json.dumps(payload)}}),
    ]

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=0,
        stdout="\n".join(jsonl_lines),
        stderr="",
    )


def verify_live_conformance(pipelines_dir: Path) -> List[str]:
    """Strictly validate that a pipeline root contains 23 genuine live Gemini Flash research reports."""
    errors: List[str] = []

    if not pipelines_dir.is_dir():
        return [f"Pipeline root directory does not exist: {pipelines_dir}"]

    seen_failure_ids = set()

    for doc_type in _ALL_DOC_TYPES:
        research_dir = pipelines_dir / doc_type / "research"
        research_json = research_dir / "research.json"
        error_json = research_dir / "research.error.json"
        summary_md = research_dir / "research_summary.md"

        if not research_dir.is_dir():
            errors.append(f"Missing pipeline research directory for doc_type '{doc_type}' at {research_dir}")
            continue

        if error_json.is_file():
            errors.append(f"Pipeline '{doc_type}' contains research.error.json (execution failed or blocked)")

        if not research_json.is_file():
            errors.append(f"Missing research.json for doc_type '{doc_type}'")
            continue

        if not summary_md.is_file():
            errors.append(f"Missing research_summary.md for doc_type '{doc_type}'")

        try:
            data = json.loads(research_json.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"Malformed JSON in research.json for doc_type '{doc_type}': {exc}")
            continue

        # Validate Pydantic schema
        try:
            report = ResearchReport.model_validate(data)
            if report.doc_type != doc_type:
                errors.append(f"doc_type mismatch in research.json for '{doc_type}': got '{report.doc_type}'")
            if len(report.failure_modes) < 3:
                errors.append(f"Insufficient failure modes for '{doc_type}': {len(report.failure_modes)} < 3")
        except Exception as exc:
            errors.append(f"Schema validation failure for '{doc_type}': {exc}")

        # Strict execution metadata validation
        execution = data.get("execution")
        if not isinstance(execution, dict):
            errors.append(f"Missing execution metadata dictionary for '{doc_type}'")
        else:
            if execution.get("status") != "success":
                errors.append(f"Execution status for '{doc_type}' is '{execution.get('status')}', expected 'success'")

            engine = execution.get("engine")
            if engine != "copilot-cli":
                errors.append(
                    f"Truthful execution flaw: Pipeline '{doc_type}' engine is '{engine}', "
                    f"expected 'copilot-cli' (injected or non-live test runner detected)"
                )

            is_live = execution.get("is_live")
            if is_live is not True:
                errors.append(
                    f"Truthful execution flaw: Pipeline '{doc_type}' is_live is {is_live}, "
                    f"expected True (non-live output detected)"
                )

            if execution.get("model") != "gemini-3.6-flash":
                errors.append(f"Model mismatch for '{doc_type}': '{execution.get('model')}', expected 'gemini-3.6-flash'")

            if execution.get("returncode") != 0:
                errors.append(f"Non-zero returncode for '{doc_type}': {execution.get('returncode')}")

            token = execution.get("provenance_token")
            if not isinstance(token, str) or len(token) != 64:
                errors.append(f"Invalid provenance_token for '{doc_type}': '{token}'")

            # Validate online research provenance
            if execution.get("online_research_performed") is not True:
                errors.append(f"online_research_performed is not True for '{doc_type}'")

            tool_calls = execution.get("tool_calls")
            if not isinstance(tool_calls, list) or "web_search" not in tool_calls:
                errors.append(f"Missing required 'web_search' tool call in tool_calls for '{doc_type}': {tool_calls}")

            if not isinstance(execution.get("tool_call_count"), int) or execution.get("tool_call_count") < 1:
                errors.append(f"Invalid tool_call_count for '{doc_type}': {execution.get('tool_call_count')}")

            if execution.get("output_format") != "json":
                errors.append(f"output_format mismatch for '{doc_type}': {execution.get('output_format')}, expected 'json'")

            if execution.get("stream") != "off":
                errors.append(f"stream mode mismatch for '{doc_type}': {execution.get('stream')}, expected 'off'")

            prompt_hash = execution.get("prompt_sha256")
            if not isinstance(prompt_hash, str) or len(prompt_hash) != 64:
                errors.append(f"Invalid or missing prompt_sha256 for '{doc_type}': '{prompt_hash}'")

            raw_hash = execution.get("raw_output_sha256") or execution.get("event_stream_sha256")
            if not isinstance(raw_hash, str) or len(raw_hash) != 64:
                errors.append(f"Invalid or missing raw_output_sha256 for '{doc_type}': '{raw_hash}'")

            command = execution.get("command")
            if not isinstance(command, list):
                errors.append(f"Invalid command format for '{doc_type}'")
            else:
                if not command or command[0] != "copilot":
                    errors.append(f"Command executable basename flaw for '{doc_type}': expected 'copilot', got '{command[0] if command else None}'")

                for arg in command:
                    if isinstance(arg, str):
                        if arg.startswith("/") or "home" in arg or "Users" in arg:
                            errors.append(f"Absolute path leaked into command for '{doc_type}': '{arg}'")
                        if "-p" in arg:
                            errors.append(f"Raw prompt text leaked into command for '{doc_type}'")

                cmd_str = " ".join(command)
                if "--model" not in command or command[command.index("--model") + 1] != "gemini-3.6-flash":
                    errors.append(f"Command missing gemini-3.6-flash model flag for '{doc_type}'")
                if "--context" not in command or command[command.index("--context") + 1] != "long_context":
                    errors.append(f"Command missing long_context flag for '{doc_type}'")
                if "--available-tools" not in command or command[command.index("--available-tools") + 1] != "web_search,web_fetch":
                    errors.append(f"Command capability violation for '{doc_type}': tool restriction web_search,web_fetch missing or overridden")
                if "--output-format" not in command or command[command.index("--output-format") + 1] != "json":
                    errors.append(f"Command missing --output-format json flag for '{doc_type}'")
                if "--stream" not in command or command[command.index("--stream") + 1] != "off":
                    errors.append(f"Command missing --stream off flag for '{doc_type}'")

                # Disallowed flags
                forbidden_flags = ["--allow-all", "--yolo", "--allow-all-paths", "--allow-tool", "-s", "--silent"]
                for flag in forbidden_flags:
                    if flag in command or flag in cmd_str.split():
                        errors.append(f"Forbidden unrestricted/legacy flag '{flag}' found in command for '{doc_type}'")

        # Content quality check
        content_lower = json.dumps(data).lower()
        forbidden_phrases = ["incomplete or defective passport", "fallback research", "placeholder research", "structured_fallback"]
        for phrase in forbidden_phrases:
            if phrase in content_lower:
                errors.append(f"Generic/fallback phrase '{phrase}' found in '{doc_type}'")

        # Failure ID uniqueness tracking and local corpus evidence resolution
        index_db_path = _REPO_ROOT / "corpus" / "index.db"
        for mode in data.get("failure_modes", []):
            if not isinstance(mode, dict):
                continue
            f_id = mode.get("failure_id")
            if f_id:
                if f_id in seen_failure_ids:
                    errors.append(f"Duplicate failure_id '{f_id}' found in '{doc_type}'")
                seen_failure_ids.add(f_id)

            auth = mode.get("authority_classification")
            if hasattr(auth, "value"):
                auth = auth.value
            auth = str(auth)

            if auth == "authoritative":
                if not mode.get("local_corpus_verified"):
                    errors.append(f"Authoritative failure mode '{f_id}' in '{doc_type}' has local_corpus_verified=False")

                evidence = mode.get("local_corpus_evidence")
                if not isinstance(evidence, list) or not evidence:
                    errors.append(f"Authoritative failure mode '{f_id}' in '{doc_type}' missing local_corpus_evidence")
                else:
                    for ev in evidence:
                        if not isinstance(ev, dict):
                            errors.append(f"Malformed local_corpus_evidence item in '{doc_type}'")
                            continue
                        citation = ev.get("citation", "")
                        quote = ev.get("quote", "")
                        if not citation or not quote:
                            errors.append(f"Empty citation or quote in local_corpus_evidence for '{doc_type}'")
                            continue

                        found, chunk_text = _cite_local_corpus_chunk(citation, db_path=index_db_path)
                        if not found or not chunk_text:
                            errors.append(
                                f"Authoritative failure mode '{f_id}' in '{doc_type}' citation '{citation}' "
                                f"failed resolution against corpus index.db"
                            )
                        else:
                            norm_quote = " ".join(quote.strip().split()).lower()
                            norm_chunk = " ".join(chunk_text.strip().split()).lower()
                            if norm_quote not in norm_chunk:
                                errors.append(
                                    f"Authoritative failure mode '{f_id}' in '{doc_type}' quote '{quote}' "
                                    f"not found in resolving chunk '{citation}' text"
                                )

        # Cross-pipeline isolation check
        for other_doc in _ALL_DOC_TYPES:
            if other_doc != doc_type and f"/pipelines/{other_doc}/" in json.dumps(data):
                errors.append(f"Cross-pipeline leakage in '{doc_type}': references foreign path for '{other_doc}'")

    return errors


class TestDocResearchConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Populate isolated temporary pipeline directory for mock conformance testing."""
        cls._tmp_dir_obj = tempfile.TemporaryDirectory()
        cls.pipeline_root = Path(cls._tmp_dir_obj.name)
        with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
            with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                research_all_document_types(
                    max_workers=4,
                    copilot_runner=_mock_copilot_runner,
                    pipeline_root=cls.pipeline_root,
                )

    @classmethod
    def tearDownClass(cls) -> None:
        """Automatically clean up temporary pipeline directory."""
        cls._tmp_dir_obj.cleanup()

    def test_all_23_document_types_have_isolated_pipelines(self) -> None:
        """Verify all 23 ExpressEntryDocType values have dedicated pipeline research directories in mock run."""
        self.assertEqual(len(_ALL_DOC_TYPES), 23, "ExpressEntryDocType must contain exactly 23 document types")

        for doc_type in _ALL_DOC_TYPES:
            pipeline_dir = self.pipeline_root / doc_type / "research"
            self.assertTrue(
                pipeline_dir.is_dir(),
                f"Missing research pipeline directory for doc_type '{doc_type}' at {pipeline_dir}",
            )

    def test_research_json_schema_conformance(self) -> None:
        """Verify research.json for mock pipelines conforms to Pydantic ResearchReport schema and metadata specs."""
        for doc_type in _ALL_DOC_TYPES:
            research_path = self.pipeline_root / doc_type / "research" / "research.json"
            self.assertTrue(research_path.is_file(), f"Missing research.json for doc_type '{doc_type}'")

            raw = research_path.read_text(encoding="utf-8")
            data = json.loads(raw)

            # Pydantic schema validation
            report = ResearchReport.model_validate(data)
            self.assertEqual(report.doc_type, doc_type)
            self.assertGreaterEqual(
                len(report.failure_modes),
                3,
                f"Pipeline {doc_type} must contain at least 3 failure modes",
            )

            # Metadata validation
            execution = data.get("execution")
            self.assertIsNotNone(execution, f"Pipeline {doc_type} missing execution metadata")
            self.assertEqual(execution.get("status"), "success")
            self.assertEqual(execution.get("model"), "gemini-3.6-flash")
            self.assertEqual(execution.get("engine"), "injected-test-runner")
            self.assertFalse(execution.get("is_live"))
            self.assertIn("timestamp", execution)
            self.assertIn("duration_seconds", execution)
            self.assertIn("command", execution)
            self.assertIn("provenance_token", execution)

    def test_no_fallback_or_generic_research(self) -> None:
        """Verify no pipeline uses fallback execution or generic placeholder content."""
        forbidden_phrases = [
            "incomplete or defective passport",
            "fallback research",
            "placeholder research",
            "structured_fallback",
        ]

        for doc_type in _ALL_DOC_TYPES:
            research_path = self.pipeline_root / doc_type / "research" / "research.json"
            data = json.loads(research_path.read_text(encoding="utf-8"))

            execution = data.get("execution", {})
            self.assertNotIn(execution.get("status"), ("fallback", "structured_fallback"))

            content_text = json.dumps(data).lower()
            for phrase in forbidden_phrases:
                self.assertNotIn(
                    phrase,
                    content_text,
                    f"Pipeline '{doc_type}' contains forbidden generic/fallback phrase '{phrase}'",
                )

    def test_research_summary_markdown_exists(self) -> None:
        """Verify research_summary.md exists alongside research.json with required headings."""
        for doc_type in _ALL_DOC_TYPES:
            summary_path = self.pipeline_root / doc_type / "research" / "research_summary.md"
            self.assertTrue(summary_path.is_file(), f"Missing research_summary.md for doc_type '{doc_type}'")

            content = summary_path.read_text(encoding="utf-8")
            self.assertIn(f"# Research Summary: {doc_type}", content)
            self.assertIn("## Executive Summary", content)
            self.assertIn("## Identified Failure Modes", content)

    def test_failure_mode_uniqueness_across_pipelines(self) -> None:
        """Verify zero duplicate failure IDs across all 23 document pipelines."""
        seen_failure_ids = set()

        for doc_type in _ALL_DOC_TYPES:
            research_path = self.pipeline_root / doc_type / "research" / "research.json"
            data = json.loads(research_path.read_text(encoding="utf-8"))

            for mode in data.get("failure_modes", []):
                f_id = mode.get("failure_id")
                self.assertIsNotNone(f_id, f"Failure mode in {doc_type} missing failure_id")
                self.assertNotIn(
                    f_id,
                    seen_failure_ids,
                    f"Duplicate failure_id '{f_id}' found in pipeline {doc_type}",
                )
                seen_failure_ids.add(f_id)

    def test_cross_pipeline_isolation(self) -> None:
        """Verify no research report references path or files belonging to a different document pipeline."""
        for doc_type in _ALL_DOC_TYPES:
            research_path = self.pipeline_root / doc_type / "research" / "research.json"
            data_str = research_path.read_text(encoding="utf-8")

            # Check that no other doc_type pipeline path is referenced inside this report
            for other_doc in _ALL_DOC_TYPES:
                if other_doc == doc_type:
                    continue
                foreign_path_substring = f"/pipelines/{other_doc}/"
                self.assertNotIn(
                    foreign_path_substring,
                    data_str,
                    f"Cross-pipeline leakage: Report for '{doc_type}' references foreign pipeline path '{foreign_path_substring}'",
                )

    def test_live_research_conformance_gate(self) -> None:
        """Live-only conformance gate validating real crawler/eval/pipelines/ directory.

        Fails explicitly (no seeding, no skipping) when enabled and production artifacts are absent,
        blocked, non-live, or malformed.
        """
        env_vars = [
            "REQUIRE_LIVE_RESEARCH_CONFORMANCE",
            "PHASE72_LIVE_GATE",
            "LIVE_RESEARCH_GATE",
            "ENABLE_LIVE_RESEARCH_GATE",
        ]
        gate_enabled = any(os.getenv(v, "").lower() in ("1", "true", "yes") for v in env_vars)

        if not gate_enabled:
            self.skipTest(
                "Live research conformance gate disabled. Set REQUIRE_LIVE_RESEARCH_CONFORMANCE=1 to enable."
            )

        # Reads real production directory without generating anything
        errors = verify_live_conformance(_PIPELINES_DIR)
        if errors:
            self.fail(
                f"Live research conformance gate failed ({len(errors)} errors):\n"
                + "\n".join(f"  - {err}" for err in errors)
            )

    def test_injected_outputs_cannot_satisfy_live_gate(self) -> None:
        """Prove that injected/mocked runner outputs fail live conformance validation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    research_all_document_types(
                        max_workers=4,
                        copilot_runner=_mock_copilot_runner,
                        pipeline_root=tmp_path,
                    )

            errors = verify_live_conformance(tmp_path)
            self.assertGreater(
                len(errors),
                0,
                "Injected test runner outputs MUST NOT satisfy live conformance gate",
            )
            injected_flaw_detected = any("Truthful execution flaw" in err for err in errors)
            self.assertTrue(
                injected_flaw_detected,
                f"Injected test outputs must trigger 'Truthful execution flaw' error in gate. Errors: {errors}",
            )

    def test_mocked_conformance_leaves_pipeline_tree_unchanged(self) -> None:
        """Prove that mocked conformance execution leaves the real repository pipeline tree untouched."""
        def snapshot_tree(root: Path) -> set:
            if not root.exists():
                return set()
            return {
                (str(p.relative_to(root)), p.stat().st_mtime)
                for p in root.rglob("*")
                if p.is_file()
            }

        snapshot_before = snapshot_tree(_PIPELINES_DIR)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with mock.patch("crawler.eval.doc_researcher.verify_policy_assertion_locally", return_value=(False, [], [])):
                with mock.patch("crawler.eval.doc_researcher._discover_copilot_executable", return_value="/bin/copilot"):
                    research_all_document_types(
                        max_workers=4,
                        copilot_runner=_mock_copilot_runner,
                        pipeline_root=tmp_path,
                    )

        snapshot_after = snapshot_tree(_PIPELINES_DIR)
        self.assertEqual(
            snapshot_before,
            snapshot_after,
            "Mocked conformance execution mutated real repository pipeline directory crawler/eval/pipelines/",
        )


if __name__ == "__main__":
    unittest.main()
