"""Pytest suite verifying scripts/run_multi_cli_conformance.py passes all release checks (Phase 50).

Verifies:
1. Multi-CLI release gate runner executes end-to-end and reports overall PASS.
2. AGENTS.md system prompt and tool contracts pass verification.
3. Thin adapter pointers exist and satisfy length/reference constraints across all 5 supported CLIs:
   - Claude Code CLI (CLAUDE.md)
   - GitHub Copilot CLI (.github/copilot-instructions.md)
   - OpenAI Codex CLI (.codex/AGENTS.md)
   - Cursor IDE (.cursor/rules/agents.mdc)
   - Windsurf Cascade (.windsurfrules)
4. Portable skills interface integrity check passes without vendor-specific tags.
5. Synthetic benchmark suite & ground truth evaluation passes.
6. Complete SAFE-01..12 privacy containment and citation grounding gate passes.
7. Runner failure handling works when adapters or contracts are missing/invalid.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.run_multi_cli_conformance import (
    SUPPORTED_CLI_ADAPTERS,
    SAFE_CRITERIA,
    check_adapter_pointers,
    check_agents_md_contracts,
    check_portable_skills_interface,
    check_safe_conformance_gate,
    check_synthetic_benchmark_suite,
    run_multi_cli_conformance,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestMultiCliConformance(unittest.TestCase):
    """Test suite for Phase 50 Multi-CLI Conformance and Release Gate."""

    def test_run_multi_cli_conformance_executes_and_passes(self) -> None:
        """Verify run_multi_cli_conformance executes all 5 stages and returns PASS status."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_report = Path(tmp_dir) / "report.json"
            report, exit_code = run_multi_cli_conformance(
                repo_root=_REPO_ROOT,
                output_path=tmp_report,
                quick=True,
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(report["overall_status"], "PASS")
            self.assertEqual(report["summary"]["passed_stages"], 5)
            self.assertEqual(report["summary"]["failed_stages"], 0)
            self.assertTrue(tmp_report.is_file())

            # Verify report structure
            self.assertIn("timestamp", report)
            self.assertIn("supported_clis", report)
            self.assertEqual(len(report["supported_clis"]), 5)
            self.assertIn("stages", report)

            stages = report["stages"]
            self.assertIn("agents_md_contracts", stages)
            self.assertIn("adapter_pointers", stages)
            self.assertIn("portable_skills", stages)
            self.assertIn("synthetic_benchmark", stages)
            self.assertIn("safe_conformance", stages)

            # Check SAFE criteria in safe_conformance
            safe_crit = stages["safe_conformance"]["safe_criteria"]
            for code, _ in SAFE_CRITERIA:
                self.assertIn(code, safe_crit)
                self.assertEqual(safe_crit[code], "PASS")

    def test_adapter_pointers_all_five_clis(self) -> None:
        """Verify thin adapter pointers for all 5 supported CLIs satisfy constraints."""
        res = check_adapter_pointers(repo_root=_REPO_ROOT)
        self.assertEqual(res["status"], "PASS")

        adapters = res["adapters"]
        self.assertEqual(set(adapters.keys()), set(SUPPORTED_CLI_ADAPTERS.keys()))

        for cli_key, spec in SUPPORTED_CLI_ADAPTERS.items():
            self.assertIn(cli_key, adapters)
            adapter = adapters[cli_key]
            self.assertTrue(adapter["exists"], f"Adapter {spec['path']} must exist")
            self.assertEqual(adapter["status"], "PASS")
            self.assertLess(adapter["line_count"], 35)
            self.assertEqual(adapter["issues"], [])

    def test_portable_skills_interface_integrity(self) -> None:
        """Verify portable skills interface, contract headers, and zero vendor-specific tags."""
        res = check_portable_skills_interface(repo_root=_REPO_ROOT)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["issues"], [])

    def test_agents_md_syntax_and_contracts(self) -> None:
        """Verify Stage 1 AGENTS.md contracts check passes."""
        res = check_agents_md_contracts(repo_root=_REPO_ROOT, quick=True)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["returncode"], 0)

    def test_synthetic_benchmark_suite(self) -> None:
        """Verify Stage 4 synthetic benchmark suite check passes."""
        res = check_synthetic_benchmark_suite(repo_root=_REPO_ROOT, quick=True)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["returncode"], 0)

    def test_safe_conformance_gate(self) -> None:
        """Verify Stage 5 SAFE-01..12 conformance gate check passes."""
        res = check_safe_conformance_gate(repo_root=_REPO_ROOT, quick=True)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["returncode"], 0)

    def test_cli_invocation_via_subprocess(self) -> None:
        """Verify scripts/run_multi_cli_conformance.py executable CLI entrypoint."""
        script_path = _REPO_ROOT / "scripts" / "run_multi_cli_conformance.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_json = Path(tmp_dir) / "cli_report.json"
            cmd = [sys.executable, str(script_path), "--output", str(out_json), "--quick"]
            proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True)

            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
            self.assertTrue(out_json.is_file())
            data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(data["overall_status"], "PASS")

    def test_failure_mode_missing_adapter_fails_gate(self) -> None:
        """Verify gate fails if an adapter file is missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_root = Path(tmp_dir)
            res = check_adapter_pointers(repo_root=fake_root)
            self.assertEqual(res["status"], "FAIL")
            self.assertTrue(any("File missing" in issue for adapter in res["adapters"].values() for issue in adapter["issues"]))

    def test_failure_mode_vendor_tag_fails_skills_gate(self) -> None:
        """Verify gate fails if a skill file contains vendor-specific tags."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_root = Path(tmp_dir)
            skills_dir = fake_root / "skills"
            skills_dir.mkdir(parents=True)
            (skills_dir / "README.md").write_text(
                "skills/document-agents/\nskills/crs-auditors/", encoding="utf-8"
            )
            doc_dir = skills_dir / "document-agents"
            doc_dir.mkdir(parents=True)
            (doc_dir / "_contract.md").write_text("Shared Answer-Object Contract", encoding="utf-8")
            crs_dir = skills_dir / "crs-auditors"
            crs_dir.mkdir(parents=True)
            (crs_dir / "_contract.md").write_text("Shared Substantiation Contract", encoding="utf-8")
            pdf_dir = skills_dir / "pdf"
            pdf_dir.mkdir(parents=True)
            (pdf_dir / "SKILL.md").write_text(
                "---\nname: pdf\ndescription: 300 DPI\n---\nreportlab pypdfium2 pdfplumber Pillow pytesseract <anthropic:prompt>",
                encoding="utf-8",
            )

            res = check_portable_skills_interface(repo_root=fake_root)
            self.assertEqual(res["status"], "FAIL")
            self.assertTrue(any("vendor-specific" in issue for issue in res["issues"]))


if __name__ == "__main__":
    unittest.main()
