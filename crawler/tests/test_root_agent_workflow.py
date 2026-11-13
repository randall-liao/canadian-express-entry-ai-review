from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_agents_routes_natural_language_review_intent() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    lowered = text.lower()

    assert "natural-language review intent" in lowered
    assert "i want to review" in lowered
    assert "review my passport" in lowered
    assert "lead review coordinator" in lowered
    assert "local path" in lowered
    assert "document type" in lowered


def test_agents_root_review_contract_covers_all_four_stages() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    required_commands = (
        "corpus-crawler --json vault init",
        "corpus-crawler --json vault import",
        "corpus-crawler --json checklist",
        "corpus-crawler --json vault extract",
        "corpus-crawler --json vault fields",
        "corpus-crawler --json vault confirm",
        "corpus-crawler --json vault audit",
        "corpus-crawler --json vault screen-mec",
        "corpus-crawler --json vault noc-review",
        "corpus-crawler --json vault study-review",
        "corpus-crawler --json vault remediate",
        "corpus-crawler --json vault review-packet",
    )

    for command in required_commands:
        assert command in text


def test_agents_root_review_contract_is_fail_closed_and_pii_safe() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8").lower()

    assert "never print" in text
    assert "vault pii" in text
    assert "uncertain" in text
    assert "confirm" in text
    assert "not_in_corpus" in text
    assert "abstain" in text
    assert "redacted" in text


def test_readme_has_ready_to_use_copilot_onboarding() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lowered = text.lower()

    assert "python 3.11" in lowered
    assert "poetry install -e doc-extract -e ocr" in lowered
    assert "poetry run python -m copilot download-runtime" in lowered
    assert "poetry run corpus-crawler --json doctor" in lowered
    assert "\ncopilot\n" in lowered
    assert "i want to review my passport for my express entry application" in lowered
    assert "remain local" in lowered
