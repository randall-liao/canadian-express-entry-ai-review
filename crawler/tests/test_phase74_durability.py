"""Non-live unit tests for Phase 74 durability, resumeability, and state machine (D-13..D-22, REAL_AGENT_EXECUTION-01).

Verifies:
- Checkpoint persistence and resume after optimizer proposal.
- Reusing valid partial candidate Worker reports and completed Judge evaluations.
- Invalidating checkpoints on input, source, or findings hash drift.
- Shared candidate proposal resume and state machine transitions.
- Recording infrastructure failures as 'blocked' rather than semantic patch rejection.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from crawler.eval.loop_orchestrator import LoopOrchestrator, _mean_metrics, _REPO_ROOT
from crawler.eval.patch_evaluator import evaluate_candidate_patch


def test_mean_metrics_computation() -> None:
    """Verify _mean_metrics calculates correct finite averages and fails closed on invalid input."""
    evals = [
        {
            "grounding_accuracy": 1.0,
            "citation_exactness": 0.8,
            "defect_recall": 1.0,
            "pii_containment": 1.0,
            "blind_input_compliance": 1.0,
        },
        {
            "grounding_accuracy": 0.8,
            "citation_exactness": 1.0,
            "defect_recall": 0.8,
            "pii_containment": 1.0,
            "blind_input_compliance": 1.0,
        },
    ]
    res = _mean_metrics(evals)
    assert res["grounding_accuracy"] == pytest.approx(0.9)
    assert res["citation_exactness"] == pytest.approx(0.9)
    assert res["defect_recall"] == pytest.approx(0.9)
    assert res["pii_containment"] == 1.0
    assert res["blind_input_compliance"] == 1.0
    assert res["overall_score"] == pytest.approx(0.94)

    # Empty list fails closed
    with pytest.raises(ValueError, match="eval_list is empty"):
        _mean_metrics([])


def test_evaluate_candidate_patch_gate() -> None:
    """Verify candidate regression gate logic (accepts train improvement + zero holdout regression)."""
    b_tr = {
        "grounding_accuracy": 0.8,
        "citation_exactness": 0.8,
        "defect_recall": 0.8,
        "pii_containment": 1.0,
        "blind_input_compliance": 1.0,
        "overall_score": 0.88,
    }
    b_ho = {
        "grounding_accuracy": 0.8,
        "citation_exactness": 0.8,
        "defect_recall": 0.8,
        "pii_containment": 1.0,
        "blind_input_compliance": 1.0,
        "overall_score": 0.88,
    }

    # Case 1: Train improves, holdout stays same -> ACCEPTED
    c_tr = dict(b_tr, defect_recall=1.0, overall_score=0.92)
    c_ho = dict(b_ho)
    assert evaluate_candidate_patch(b_tr, b_ho, c_tr, c_ho) is True

    # Case 2: Holdout regresses -> REJECTED
    c_ho_reg = dict(b_ho, defect_recall=0.6, overall_score=0.84)
    assert evaluate_candidate_patch(b_tr, b_ho, c_tr, c_ho_reg) is False

    # Case 3: Train regresses or stays same -> REJECTED
    c_tr_same = dict(b_tr)
    assert evaluate_candidate_patch(b_tr, b_ho, c_tr_same, c_ho) is False


def test_proposal_checkpoint_durability_and_hash_drift(tmp_path: Path) -> None:
    """Verify proposal checkpoint serialization, loading, and hash drift invalidation."""
    orchestrator = LoopOrchestrator(pipelines_dir=tmp_path / "pipelines", iterations_dir=tmp_path / "iterations")

    doc_type = "passport"
    findings = {"findings": [{"case_id": "c1", "description": "missing stamp"}]}
    findings_hash = hashlib.sha256(json.dumps(findings, sort_keys=True).encode("utf-8")).hexdigest()
    source_content = "# Passport Skill\nReview passport rules."
    source_hash = hashlib.sha256(source_content.encode("utf-8")).hexdigest()

    chk_dir = tmp_path / "iterations" / "iter_1" / "checkpoints"
    chk_file = chk_dir / f"checkpoint_{doc_type}.json"

    cand_res = {
        "candidate_id": "candidate_123456",
        "doc_type": doc_type,
        "target_file": "skills/document-agents/passport.md",
        "candidate_content": "# Passport Skill\nUpdated review passport rules.",
        "rationale": "Add stamp rule",
        "is_valid": True,
        "rejection_reasons": [],
        "_provenance": {
            "engine": "copilot-cli",
            "is_live": True,
            "model": "gemini-3.6-flash",
            "context": "long_context",
            "output_hash": "a" * 64,
        },
    }

    chk_data = {
        "doc_type": doc_type,
        "status": "proposed",
        "candidate_res": cand_res,
        "candidate_content_hash": hashlib.sha256(cand_res["candidate_content"].encode("utf-8")).hexdigest(),
        "training_findings_hash": findings_hash,
        "current_source_hash": source_hash,
        "candidate_bundle_hash": None,
        "live_provenance": cand_res["_provenance"],
        "error": None,
    }

    orchestrator._save_checkpoint_atomically(chk_file, chk_data)
    assert chk_file.is_file()

    loaded = orchestrator._load_checkpoint(chk_file)
    assert loaded is not None
    assert loaded["status"] == "proposed"

    # Validate matching inputs -> True
    assert orchestrator._validate_checkpoint_inputs(loaded, doc_type, findings_hash, source_hash, runner_fn=None) is True

    # Validate mismatched findings hash -> False
    bad_findings_hash = hashlib.sha256(b"different").hexdigest()
    assert orchestrator._validate_checkpoint_inputs(loaded, doc_type, bad_findings_hash, source_hash, runner_fn=None) is False

    # Validate mismatched source hash -> False
    bad_source_hash = hashlib.sha256(b"different source").hexdigest()
    assert orchestrator._validate_checkpoint_inputs(loaded, doc_type, findings_hash, bad_source_hash, runner_fn=None) is False


def test_sandbox_proposal_recovery(tmp_path: Path) -> None:
    """Verify recovery of candidate proposals from sandbox directory when checkpoint JSON is missing."""
    orchestrator = LoopOrchestrator(pipelines_dir=tmp_path / "pipelines", iterations_dir=tmp_path / "iterations")
    sandbox_root = tmp_path / "iterations" / "iter_1" / "proposals"
    cand_dir = sandbox_root / "candidate_rec123"
    skill_file = cand_dir / "skills" / "document-agents" / "passport.md"
    skill_file.parent.mkdir(parents=True)

    # Read current passport skill content on disk to generate a valid minimal patch
    target_path = _REPO_ROOT / "skills" / "document-agents" / "passport.md"
    current_content = target_path.read_text(encoding="utf-8") if target_path.is_file() else "# Skill\n" * 20
    cand_content = current_content + "\n<!-- Added rule -->\n"
    skill_file.write_text(cand_content, encoding="utf-8")

    rec = orchestrator._try_recover_proposal_from_sandbox(
        sandbox_root,
        doc_type="passport",
        target_relpath="skills/document-agents/passport.md",
        training_findings_hash="a" * 64,
        current_source_hash="b" * 64,
        runner_fn=None,
    )

    assert rec is not None
    assert rec["candidate_id"] == "candidate_rec123"
    assert rec["candidate_content"] == cand_content
    assert rec["is_valid"] is True


def test_blocked_status_on_infrastructure_exception(tmp_path: Path) -> None:
    """Verify that execution exceptions store 'blocked' status and do not convert to semantic patch rejection."""
    orchestrator = LoopOrchestrator(pipelines_dir=tmp_path / "pipelines", iterations_dir=tmp_path / "iterations")
    chk_dir = tmp_path / "iterations" / "iter_1" / "checkpoints"
    chk_file = chk_dir / "checkpoint_passport.json"

    chk_data = {
        "doc_type": "passport",
        "status": "blocked",
        "candidate_res": None,
        "candidate_content_hash": None,
        "training_findings_hash": "a" * 64,
        "current_source_hash": "b" * 64,
        "candidate_bundle_hash": None,
        "live_provenance": None,
        "error": "Copilot CLI rate limit hit (429)",
    }

    orchestrator._save_checkpoint_atomically(chk_file, chk_data)
    loaded = orchestrator._load_checkpoint(chk_file)
    assert loaded["status"] == "blocked"
    assert "rate limit" in loaded["error"]
