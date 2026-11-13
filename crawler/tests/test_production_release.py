"""Production Release & Guidance Packaging Verification Suite (Phase 51 / SHIP-01 / SHIP-02).

Verifies README.md, GUIDE.md, publish-safety compliance, adapter pointers,
template profiles, and release packaging readiness.
"""

import os
import subprocess
import sys
from pathlib import Path
import pytest

from scripts.check_publish_safe import main as check_publish_safe_main


@pytest.fixture
def repo_root() -> Path:
    """Return absolute path to repository root."""
    return Path(__file__).resolve().parent.parent.parent


def test_readme_exists_and_valid(repo_root: Path):
    """Verify README.md exists and contains all required sections (SHIP-01)."""
    readme_path = repo_root / "README.md"
    assert readme_path.exists(), "README.md does not exist at repo root"
    content = readme_path.read_text(encoding="utf-8")
    assert len(content.strip()) > 500, "README.md is too short or empty"

    # Required sections & keywords
    required_keywords = [
        "Quickstart",
        "Multi-Agent Architecture",
        "AGENTS.md",
        "GitHub Copilot",
        "Claude Code",
        "OpenAI Codex",
        "Cursor",
        "Windsurf",
        "Antigravity",
        "Installation",
        "Key Features",
    ]
    for kw in required_keywords:
        assert kw in content, f"README.md missing required section/keyword: {kw}"


def test_guide_exists_and_valid(repo_root: Path):
    """Verify GUIDE.md exists and contains all required applicant guide sections (SHIP-01)."""
    guide_path = repo_root / "GUIDE.md"
    assert guide_path.exists(), "GUIDE.md does not exist at repo root"
    content = guide_path.read_text(encoding="utf-8")
    assert len(content.strip()) > 500, "GUIDE.md is too short or empty"

    # Required workflow stages & keywords
    required_keywords = [
        "Candidate Setup",
        "Document Extractions",
        "Field Confirmations",
        "Grounded CRS Audits",
        "Policy Screening",
        "Private Remediation",
        "Review Packet",
        "RCIC",
    ]
    for kw in required_keywords:
        assert kw in content, f"GUIDE.md missing required section/keyword: {kw}"


def test_publish_safe_check_passes():
    """Verify publish-safety checker executes cleanly with zero violations (SHIP-02)."""
    # Direct stdlib main() invocation
    exit_code = check_publish_safe_main()
    assert exit_code == 0, f"check_publish_safe main() returned non-zero exit code {exit_code}"


def test_publish_safe_cli_executable(repo_root: Path):
    """Verify scripts/check_publish_safe.py executable via subprocess (SHIP-02)."""
    script_path = repo_root / "scripts" / "check_publish_safe.py"
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert proc.returncode == 0, f"check_publish_safe.py failed: {proc.stderr}\n{proc.stdout}"
    assert "publish-safe" in proc.stdout
    assert "0 violations" in proc.stdout


def test_release_packaging_readiness(repo_root: Path):
    """Verify package configuration, adapter pointers, and template profiles (SHIP-02)."""
    # 1. pyproject.toml readiness
    pyproject_path = repo_root / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml missing"
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    assert 'name = "corpus-crawler"' in pyproject_text
    assert "corpus-crawler = " in pyproject_text

    # 2. AGENTS.md canonical standard
    agents_md = repo_root / "AGENTS.md"
    assert agents_md.exists(), "AGENTS.md missing"
    assert "Canonical System Specification" in agents_md.read_text(encoding="utf-8")

    # 3. Thin adapter pointers for all 5 CLIs
    adapters = [
        ("CLAUDE.md", "Claude Code"),
        (".github/copilot-instructions.md", "GitHub Copilot"),
        (".codex/AGENTS.md", "OpenAI Codex"),
        (".cursor/rules/agents.mdc", "Cursor"),
        (".windsurfrules", "Windsurf"),
    ]
    for rel_path, name in adapters:
        path = repo_root / rel_path
        assert path.exists(), f"Adapter pointer for {name} missing at {rel_path}"
        text = path.read_text(encoding="utf-8")
        assert "AGENTS.md" in text, f"Adapter pointer for {name} does not reference AGENTS.md"

    # 4. Template profiles readiness
    template_profiles = [
        repo_root / "personal.example" / "profile.yaml",
        repo_root / "personal.example" / "crs-profile.example.yaml",
        repo_root / "crawler" / "profiles" / "ircc.yaml",
    ]
    for profile_path in template_profiles:
        assert profile_path.exists(), f"Template profile missing: {profile_path}"
        assert len(profile_path.read_text(encoding="utf-8").strip()) > 50

    # 5. Core assets and skills directories
    assert (repo_root / "skills").is_dir(), "skills/ directory missing"
    assert (repo_root / "corpus" / "index.db").exists(), "corpus/index.db missing"
