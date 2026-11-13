from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
HIGHLIGHTS = ROOT / "TECHNICAL_HIGHLIGHTS.md"


def _document() -> str:
    return HIGHLIGHTS.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_technical_highlights_has_two_pillar_portfolio_structure() -> None:
    text = _document()

    required_sections = (
        "# Technical Highlights",
        "## Project Snapshot",
        "## The Engineering Challenge",
        "## Self-Improving Agent Loop",
        "## Agent-Enabled Web Crawler",
        "## From Corpus to Applicant Review",
        "## Engineering Highlights",
        "## Reliability and Security",
        "## Measured Outcomes",
        "## What I Demonstrated",
        "## Technical References",
    )
    for section in required_sections:
        assert re.search(
            rf"^{re.escape(section)}$",
            text,
            flags=re.MULTILINE,
        ), section

    mermaid_blocks = re.findall(
        r"```mermaid\n(.*?)\n```",
        text,
        flags=re.DOTALL,
    )
    assert len(mermaid_blocks) == 2
    assert all(block.lstrip().startswith("flowchart ") for block in mermaid_blocks)


def test_technical_highlights_preserves_measured_release_facts() -> None:
    normalized = _normalized(_document())

    required_facts = (
        "23 document pipelines",
        "118 logical cases",
        "236 synthetic PDFs",
        "236 blind Worker runs",
        "23 privileged Judge runs",
        "Peak concurrency | 5",
        "11 accepted / 23 rejected",
        "2,409 passed",
        "203,795 subtests",
        "0 cleanup survivors",
    )
    for fact in required_facts:
        assert fact in normalized

    assert "rerun deltas move in both directions" in normalized
    assert "does not guarantee an immigration outcome" in normalized.lower()


def test_technical_highlights_explains_agent_enabled_crawler() -> None:
    normalized = _normalized(_document())

    required_crawler_concepts = (
        "crawl4ai",
        "source-agnostic",
        "delete-only",
        "deterministic eval enforcement",
        "full-fidelity re-fetch",
        "`pass`, `fail`, and `incomplete`",
        "five-key JSON envelope",
    )
    for concept in required_crawler_concepts:
        assert concept in normalized


def test_technical_highlights_explains_measured_improvement_loop() -> None:
    normalized = _normalized(_document())

    required_loop_concepts = (
        "sealed holdout",
        "proposal sandbox",
        "non-regression gate",
        "atomic patch",
        "11 accepted / 23 rejected",
        "Python validates and orchestrates model work",
    )
    for concept in required_loop_concepts:
        assert concept in normalized


def test_technical_highlights_local_links_resolve() -> None:
    text = _document()
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)

    for link in links:
        if link.startswith(("https://", "http://", "#")):
            continue
        path = link.split("#", 1)[0]
        assert path, f"Empty local link target: {link}"
        assert (ROOT / path).exists(), f"Missing local link target: {link}"
