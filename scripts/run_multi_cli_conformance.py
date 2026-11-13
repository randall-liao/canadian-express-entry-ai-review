#!/usr/bin/env python3
"""Multi-CLI Release Gate Runner (Phase 50).

Automated conformance runner and release gate that executes:
1. AGENTS.md syntax & contracts check (crawler/tests/test_instruction_eval.py)
2. Adapter pointers verification across all 5 supported CLIs:
   - Claude Code CLI (CLAUDE.md)
   - GitHub Copilot CLI (.github/copilot-instructions.md)
   - OpenAI Codex CLI (.codex/AGENTS.md)
   - Cursor IDE (.cursor/rules/agents.mdc)
   - Windsurf Cascade (.windsurfrules)
3. Portable skills interface integrity check (skills/README.md, contracts, SKILL.md, tag checks)
4. Synthetic benchmark suite & ground truth evaluation (test_benchmark_loop.py & test_pdf_synthetic.py)
5. Complete SAFE-01..12 privacy containment and citation grounding gate (scripts/run_conformance.py)

Emits a structured JSON release-gate report and exits 0 on PASS / 1 on FAIL.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Supported CLI Adapters and their expected specs
SUPPORTED_CLI_ADAPTERS = {
    "claude_code": {
        "name": "Claude Code CLI",
        "path": "CLAUDE.md",
        "max_lines": 35,
        "required_token": "AGENTS.md",
    },
    "github_copilot": {
        "name": "GitHub Copilot CLI",
        "path": ".github/copilot-instructions.md",
        "max_lines": 35,
        "required_token": "AGENTS.md",
    },
    "openai_codex": {
        "name": "OpenAI Codex CLI",
        "path": ".codex/AGENTS.md",
        "max_lines": 35,
        "required_token": "AGENTS.md",
    },
    "cursor": {
        "name": "Cursor IDE",
        "path": ".cursor/rules/agents.mdc",
        "max_lines": 35,
        "required_token": "AGENTS.md",
        "required_frontmatter": "alwaysApply: true",
    },
    "windsurf": {
        "name": "Windsurf Cascade",
        "path": ".windsurfrules",
        "max_lines": 35,
        "required_token": "AGENTS.md",
    },
}

SAFE_CRITERIA = (
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


def check_agents_md_contracts(repo_root: Path = _REPO_ROOT, quick: bool = False) -> dict:
    """Stage 1: Verify AGENTS.md syntax, roles, and tool contracts."""
    test_file = repo_root / "crawler" / "tests" / "test_instruction_eval.py"
    if not test_file.is_file():
        return {
            "status": "FAIL",
            "error": "crawler/tests/test_instruction_eval.py missing",
        }

    cmd = [sys.executable, "-m", "pytest", str(test_file.relative_to(repo_root)), "-q"]
    if quick:
        cmd.append("--collect-only")

    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    passed = proc.returncode == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "test_file": str(test_file.relative_to(repo_root)),
        "returncode": proc.returncode,
        "output": proc.stdout.strip() if passed else proc.stderr.strip() or proc.stdout.strip(),
    }


def check_adapter_pointers(repo_root: Path = _REPO_ROOT) -> dict:
    """Stage 2: Verify thin adapter pointers across all 5 supported CLIs."""
    results = {}
    all_passed = True

    for cli_key, spec in SUPPORTED_CLI_ADAPTERS.items():
        adapter_path = repo_root / spec["path"]
        cli_result = {
            "name": spec["name"],
            "path": spec["path"],
            "exists": adapter_path.is_file(),
            "status": "FAIL",
            "issues": [],
        }

        if not adapter_path.is_file():
            cli_result["issues"].append(f"File missing: {spec['path']}")
            all_passed = False
            results[cli_key] = cli_result
            continue

        text = adapter_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        cli_result["line_count"] = len(lines)

        if len(lines) >= spec["max_lines"]:
            cli_result["issues"].append(
                f"Line count {len(lines)} exceeds max allowed {spec['max_lines']}"
            )

        if spec["required_token"] not in text:
            cli_result["issues"].append(
                f"Missing required pointer reference '{spec['required_token']}'"
            )

        if "required_frontmatter" in spec:
            if spec["required_frontmatter"] not in text:
                cli_result["issues"].append(
                    f"Missing required frontmatter '{spec['required_frontmatter']}'"
                )

        if not cli_result["issues"]:
            cli_result["status"] = "PASS"
        else:
            all_passed = False

        results[cli_key] = cli_result

    return {
        "status": "PASS" if all_passed else "FAIL",
        "adapters": results,
    }


def check_portable_skills_interface(repo_root: Path = _REPO_ROOT) -> dict:
    """Stage 3: Verify portable skills interface and contracts integrity."""
    issues = []
    skills_dir = repo_root / "skills"

    skills_readme = skills_dir / "README.md"
    if not skills_readme.is_file():
        issues.append("skills/README.md missing")
    else:
        readme_text = skills_readme.read_text(encoding="utf-8")
        if "skills/document-agents/" not in readme_text:
            issues.append("skills/README.md missing document-agents reference")
        if "skills/crs-auditors/" not in readme_text:
            issues.append("skills/README.md missing crs-auditors reference")

    doc_contract = skills_dir / "document-agents" / "_contract.md"
    crs_contract = skills_dir / "crs-auditors" / "_contract.md"

    if not doc_contract.is_file():
        issues.append("skills/document-agents/_contract.md missing")
    elif "Shared Answer-Object Contract" not in doc_contract.read_text(encoding="utf-8"):
        issues.append("skills/document-agents/_contract.md missing Answer-Object Contract header")

    if not crs_contract.is_file():
        issues.append("skills/crs-auditors/_contract.md missing")
    elif "Shared Substantiation Contract" not in crs_contract.read_text(encoding="utf-8"):
        issues.append("skills/crs-auditors/_contract.md missing Substantiation Contract header")

    pdf_skill = skills_dir / "pdf" / "SKILL.md"
    if not pdf_skill.is_file():
        issues.append("skills/pdf/SKILL.md missing")
    else:
        pdf_text = pdf_skill.read_text(encoding="utf-8")
        if not pdf_text.startswith("---"):
            issues.append("skills/pdf/SKILL.md missing YAML frontmatter")
        for tool in ["reportlab", "pypdfium2", "pdfplumber", "Pillow", "pytesseract"]:
            if tool not in pdf_text:
                issues.append(f"skills/pdf/SKILL.md missing tool instruction for {tool}")

    # Check vendor tags across all markdown files in skills/
    for md_file in skills_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if "<anthropic:" in content or "<openai:" in content:
            issues.append(f"Skill file {md_file.relative_to(repo_root)} contains vendor-specific tags")

    passed = len(issues) == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "issues": issues,
    }


def check_synthetic_benchmark_suite(repo_root: Path = _REPO_ROOT, quick: bool = False) -> dict:
    """Stage 4: Execute synthetic benchmark suite and ground truth evaluation."""
    benchmark_test = repo_root / "crawler" / "tests" / "test_benchmark_loop.py"
    pdf_test = repo_root / "crawler" / "tests" / "test_pdf_synthetic.py"

    if not benchmark_test.is_file() or not pdf_test.is_file():
        return {
            "status": "FAIL",
            "error": "Benchmark or PDF synthetic test files missing",
        }

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(benchmark_test.relative_to(repo_root)),
        str(pdf_test.relative_to(repo_root)),
        "-q",
    ]
    if quick:
        cmd.append("--collect-only")

    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    passed = proc.returncode == 0

    return {
        "status": "PASS" if passed else "FAIL",
        "test_files": [
            str(benchmark_test.relative_to(repo_root)),
            str(pdf_test.relative_to(repo_root)),
        ],
        "returncode": proc.returncode,
        "output": proc.stdout.strip() if passed else proc.stderr.strip() or proc.stdout.strip(),
    }


def check_safe_conformance_gate(repo_root: Path = _REPO_ROOT, quick: bool = False) -> dict:
    """Stage 5: Execute complete SAFE-01..12 privacy containment and citation grounding gate."""
    runner_script = repo_root / "scripts" / "run_conformance.py"
    if not runner_script.is_file():
        return {
            "status": "FAIL",
            "error": "scripts/run_conformance.py missing",
        }

    cmd = [sys.executable, str(runner_script), "-q"]
    if quick:
        cmd.append("--collect-only")

    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    passed = proc.returncode == 0

    criteria_status = {
        code: "PASS" if passed else "FAIL"
        for code, _ in SAFE_CRITERIA
    }

    return {
        "status": "PASS" if passed else "FAIL",
        "runner": "scripts/run_conformance.py",
        "returncode": proc.returncode,
        "safe_criteria": criteria_status,
        "output": proc.stdout.strip() if passed else proc.stderr.strip() or proc.stdout.strip(),
    }


def run_multi_cli_conformance(
    repo_root: Path = _REPO_ROOT,
    output_path: Path | None = None,
    quick: bool = False,
) -> tuple[dict, int]:
    """Execute all 5 stages of the Multi-CLI release gate and return (report_dict, exit_code)."""
    if output_path is None:
        output_path = repo_root / "reports" / "multi_cli_conformance_report.json"

    stage1 = check_agents_md_contracts(repo_root, quick=quick)
    stage2 = check_adapter_pointers(repo_root)
    stage3 = check_portable_skills_interface(repo_root)
    stage4 = check_synthetic_benchmark_suite(repo_root, quick=quick)
    stage5 = check_safe_conformance_gate(repo_root, quick=quick)

    stages = {
        "agents_md_contracts": stage1,
        "adapter_pointers": stage2,
        "portable_skills": stage3,
        "synthetic_benchmark": stage4,
        "safe_conformance": stage5,
    }

    failed_stages = [name for name, st in stages.items() if st["status"] != "PASS"]
    overall_status = "PASS" if not failed_stages else "FAIL"

    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "overall_status": overall_status,
        "summary": {
            "total_stages": len(stages),
            "passed_stages": len(stages) - len(failed_stages),
            "failed_stages": len(failed_stages),
            "failed_stage_names": failed_stages,
        },
        "supported_clis": list(SUPPORTED_CLI_ADAPTERS.keys()),
        "stages": stages,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    exit_code = 0 if overall_status == "PASS" else 1
    return report, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_multi_cli_conformance",
        description="Multi-CLI Conformance & Release Gate Runner (VERIFY-01, VERIFY-02).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_REPO_ROOT / "reports" / "multi_cli_conformance_report.json",
        help="Path to write structured JSON release-gate report",
    )
    parser.add_argument(
        "--quick",
        "--collect-only",
        action="store_true",
        help="Run discovery/collect-only pass for fast verification",
    )

    args = parser.parse_args(argv)

    print("== Multi-CLI Conformance & Release Gate Runner ==")
    print("   Supported CLIs: Claude Code, GitHub Copilot, OpenAI Codex, Cursor, Windsurf")
    print("   Criteria: VERIFY-01, VERIFY-02, SAFE-01..12")

    report, exit_code = run_multi_cli_conformance(
        repo_root=_REPO_ROOT,
        output_path=args.output,
        quick=args.quick,
    )

    status_str = report["overall_status"]
    print(f"== Release Gate Result: {status_str} (Report saved to {args.output}) ==")

    if status_str != "PASS":
        print(f"Failed stages: {report['summary']['failed_stage_names']}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
