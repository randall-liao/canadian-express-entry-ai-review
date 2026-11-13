"""Automated benchmark and evaluation test suite for AGENTS.md instruction compliance."""

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestInstructionCompliance(unittest.TestCase):

    def setUp(self):
        self.agents_md = _REPO_ROOT / "AGENTS.md"

    def test_agents_md_syntax(self):
        """Verify canonical AGENTS.md exists and specifies core roles & tool contracts."""
        self.assertTrue(self.agents_md.is_file(), "AGENTS.md must exist at repository root")
        content = self.agents_md.read_text(encoding="utf-8")

        # Section 1 checks
        self.assertIn("PR Review Agent", content)
        self.assertIn("100% Grounded Citations", content)
        self.assertIn("Zero Ungrounded Assertions", content)
        self.assertIn("Strict PII Containment", content)

        # Section 2 checks
        self.assertIn("corpus-crawler --json", content)
        self.assertIn("schema_version", content)
        self.assertIn("ok", content)
        self.assertIn("command", content)
        self.assertIn("result", content)
        self.assertIn("error", content)
        self.assertIn("stderr", content)
        self.assertIn("checklist", content)
        self.assertIn("search", content)
        self.assertIn("ground", content)
        self.assertIn("vault", content)

    def test_grounding_rules(self):
        """Verify AGENTS.md enforces fail-closed grounding, AnswerObject schema, and PII containment."""
        self.assertTrue(self.agents_md.is_file(), "AGENTS.md must exist at repository root")
        content = self.agents_md.read_text(encoding="utf-8")

        # AnswerObject schema fields
        for field in ["question", "claims", "basis", "abstentions", "prose"]:
            self.assertIn(field, content)

        # Grounding and quote rules
        self.assertIn("corpus-crawler search --cite", content)
        self.assertIn("result.chunk.text", content)
        self.assertIn("corpus-crawler --json ground", content)
        self.assertIn("result.verdict", content)

        # PII containment
        self.assertIn("claims", content)
        self.assertIn("basis", content)

    def test_review_workflows(self):
        """Verify AGENTS.md details multi-agent roles and 4-stage operational review workflow."""
        self.assertTrue(self.agents_md.is_file(), "AGENTS.md must exist at repository root")
        content = self.agents_md.read_text(encoding="utf-8")

        # Roles
        self.assertIn("Lead Review Coordinator", content)
        self.assertIn("Document Review Agent", content)
        self.assertIn("CRS Auditor Agent", content)
        self.assertIn("Remediation Exporter", content)

        # Stages & subcommands
        subcommands = [
            "vault init",
            "vault profile",
            "vault ita",
            "vault import",
            "checklist",
            "vault extract",
            "doctor",
            "vault fields",
            "vault confirm",
            "vault audit",
            "vault screen-mec",
            "vault noc-review",
            "vault study-review",
            "vault remediate",
            "vault review-packet",
        ]
        for cmd in subcommands:
            self.assertIn(cmd, content, f"Subcommand '{cmd}' must be documented in workflow")

    def test_adapter_pointers(self):
        """Verify thin pointer adapters exist for all supported CLIs and delegate to AGENTS.md."""
        adapters = [
            _REPO_ROOT / "CLAUDE.md",
            _REPO_ROOT / ".github" / "copilot-instructions.md",
            _REPO_ROOT / ".codex" / "AGENTS.md",
            _REPO_ROOT / ".cursor" / "rules" / "agents.mdc",
            _REPO_ROOT / ".windsurfrules",
        ]
        for adapter in adapters:
            self.assertTrue(adapter.is_file(), f"Adapter file {adapter} must exist")
            text = adapter.read_text(encoding="utf-8")
            lines = text.splitlines()
            self.assertLess(len(lines), 35, f"Adapter file {adapter} must be under 35 lines, got {len(lines)}")
            self.assertIn("AGENTS.md", text, f"Adapter {adapter} must reference AGENTS.md")

        cursor_adapter = _REPO_ROOT / ".cursor" / "rules" / "agents.mdc"
        cursor_text = cursor_adapter.read_text(encoding="utf-8")
        self.assertIn("alwaysApply: true", cursor_text, "Cursor rule adapter must have alwaysApply: true")

    def test_skills_interface(self):
        """Verify portable skills interface and contracts."""
        skills_readme = _REPO_ROOT / "skills" / "README.md"
        self.assertTrue(skills_readme.is_file(), "skills/README.md must exist")
        readme_text = skills_readme.read_text(encoding="utf-8")
        self.assertIn("skills/document-agents/", readme_text)
        self.assertIn("skills/crs-auditors/", readme_text)

        doc_contract = _REPO_ROOT / "skills" / "document-agents" / "_contract.md"
        crs_contract = _REPO_ROOT / "skills" / "crs-auditors" / "_contract.md"
        self.assertTrue(doc_contract.is_file(), "Document contract must exist")
        self.assertTrue(crs_contract.is_file(), "CRS contract must exist")
        self.assertIn("Shared Answer-Object Contract", doc_contract.read_text(encoding="utf-8"))
        self.assertIn("Shared Substantiation Contract", crs_contract.read_text(encoding="utf-8"))

        # Verify all markdown skill files in skills/ pass portable markdown structure checks
        skills_dir = _REPO_ROOT / "skills"
        for md_file in skills_dir.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            self.assertNotIn("<anthropic:", content, f"Skill file {md_file} must not contain vendor-specific tags")
            self.assertNotIn("<openai:", content, f"Skill file {md_file} must not contain vendor-specific tags")

    def test_synthetic_fixtures_structure(self):
        """Verify synthetic PII-free benchmark JSON fixtures exist and have valid structure."""
        fixtures_dir = _REPO_ROOT / "crawler" / "eval" / "synthetic_fixtures"
        self.assertTrue(fixtures_dir.is_dir(), "synthetic_fixtures directory must exist")

        fsw = fixtures_dir / "candidate_fsw_pass.json"
        cec = fixtures_dir / "candidate_cec_fail.json"
        extractions = fixtures_dir / "extractions_sample.json"

        self.assertTrue(fsw.is_file(), "candidate_fsw_pass.json must exist")
        self.assertTrue(cec.is_file(), "candidate_cec_fail.json must exist")
        self.assertTrue(extractions.is_file(), "extractions_sample.json must exist")

        import json
        fsw_data = json.loads(fsw.read_text(encoding="utf-8"))
        cec_data = json.loads(cec.read_text(encoding="utf-8"))
        ext_data = json.loads(extractions.read_text(encoding="utf-8"))

        self.assertEqual(fsw_data["profile"]["program"], "FSW")
        self.assertEqual(fsw_data["expected_verdict"], "PASS")
        self.assertEqual(cec_data["profile"]["program"], "CEC")
        self.assertEqual(cec_data["expected_verdict"], "FAIL")
        self.assertIn("extractions", ext_data)
        self.assertGreater(len(ext_data["extractions"]), 0)

    def test_synthetic_fixtures_grounding(self):
        """Verify grounding gate works on synthetic answer object schema."""
        from crawler.grounding import check_answer
        db = _REPO_ROOT / "corpus" / "index.db"
        
        # Test valid AnswerObject schema with zero claims (pure abstention)
        answer_abstain = {
            "question": "What is the requirement for synthetic category X?",
            "claims": [],
            "basis": ["Synthetic basis"],
            "abstentions": ["No grounding found in authoritative corpus"],
            "prose": "I must abstain as no authoritative source exists."
        }
        if db.is_file():
            result = check_answer(answer_abstain, db)
            self.assertEqual(result["verdict"], "pass")
            self.assertEqual(result["total_claims"], 0)

    def test_out_of_corpus_abstention(self):
        """Verify out-of-corpus queries produce ungrounded violations or require abstention."""
        from crawler.grounding import check_answer
        db = _REPO_ROOT / "corpus" / "index.db"

        # Claim referencing a non-existent citation ID
        fake_claim_answer = {
            "question": "Fake question?",
            "claims": [
                {
                    "id": "c1",
                    "text": "Fake claim",
                    "citations": ["non_existent_citation_99999"],
                    "quote": "fake quote"
                }
            ],
            "basis": [],
            "abstentions": [],
            "prose": "Fake prose"
        }
        if db.is_file():
            result = check_answer(fake_claim_answer, db)
            self.assertEqual(result["verdict"], "fail")
            self.assertEqual(result["ungrounded"], 1)
            self.assertIn("unresolvable", result["violations"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
