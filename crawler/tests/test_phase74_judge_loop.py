"""Unit and contract tests for Phase 74 privileged Judge engine and holdout splitter.

Verifies:
- Logical sibling group train/holdout partitioning and sealing
- Deterministic holdout pair selection via SHA-256 (exactly 4 holdout cases per doc type)
- Privileged batched Claude Opus 4.8 xhigh long-context execution
- Strict Pydantic schema validation and 100% case coverage assertion
- Zero deterministic score fabrication or fallback
- Sanitized provenance and redaction of privileged inputs
- Attachment validation, repository/temp denial, and staging cleanup
- Strict JSONL parsing and reasoning event rejection
- Fail-closed worker report provenance and hash verification
- Disabled legacy single-case Judge entrypoints
"""

from __future__ import annotations

import hashlib
import json
import re
import string
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from crawler.eval.agent_runtime import AgentLifecycleError
from crawler.eval.genuine_optimizer import (
    derive_optimizer_candidate_id,
    optimizer_provenance_digest,
    run_candidate_optimization_pass,
)
from crawler.eval.holdout_splitter import (
    get_holdout_case_ids,
    seal_holdout_findings,
    split_doc_type_cases,
)
from crawler.eval.loop_orchestrator import (
    _PUBLISHABLE_OPTIMIZER_PROVENANCE_FIELDS,
    _publishable_optimizer_provenance,
)
from crawler.eval.patch_evaluator import (
    apply_patch_atomically,
    evaluate_candidate_patch,
    validate_patch_allowlist,
    validate_target_allowlist,
)
from crawler.eval.pipeline_judge import (
    CaseFinding,
    CaseScore,
    JudgeEvaluationBatch,
    JudgeExecutionError,
    PatchRecommendation,
    judge_pipeline_case,
    run_batched_document_judge,
    run_pipeline_judge_for_doctype,
)
from crawler.eval.pipeline_worker import _build_worker_prompt
from crawler.eval.public_bundle import (
    _PRIVILEGED_NORMALIZED_PHRASES,
    build_public_review_bundle,
)
from crawler.eval.real_judge import judge_real_worker_output, run_category_judge
from crawler.tests.phase74_provenance import (
    build_provenance,
    build_worker_provenance,
)


def _make_mock_case(
    opaque_case_id: str,
    sibling_case_id: str,
    doc_type: str = "passport",
    variant: str = "vector",
    expected_verdict: str = "defective",
    source_failure_id: str = "PFL-PASSPORT-01",
) -> Dict[str, Any]:
    return {
        "opaque_case_id": opaque_case_id,
        "sibling_case_id": sibling_case_id,
        "doc_type": doc_type,
        "variant": variant,
        "expected_verdict": expected_verdict,
        "source_failure_id": source_failure_id,
    }


def _build_mock_doc_type_cases(doc_type: str = "passport") -> List[Dict[str, Any]]:
    """Build 5 logical sibling pairs (10 total cases) for a document type with valid 32-hex IDs."""
    from crawler.synthetic.staging import generate_opaque_32hex_id

    cases = []
    # Pair 0: Valid control
    v0, s0 = generate_opaque_32hex_id(), generate_opaque_32hex_id()
    cases.append(_make_mock_case(v0, s0, doc_type, "vector", "meets_requirements", None))
    cases.append(_make_mock_case(s0, v0, doc_type, "scanned", "meets_requirements", None))

    # Pairs 1..4: Defective pairs
    for i in range(1, 5):
        vid, sid = generate_opaque_32hex_id(), generate_opaque_32hex_id()
        cases.append(_make_mock_case(vid, sid, doc_type, "vector", "defective", f"PFL-DEF-{i}"))
        cases.append(_make_mock_case(sid, vid, doc_type, "scanned", "defective", f"PFL-DEF-{i}"))

    return cases


def _make_mock_worker_report(case_id: str, pdf_bytes: bytes, doc_type: str = "passport") -> Dict[str, Any]:
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    public_bundle = build_public_review_bundle(doc_type)
    prompt = _build_worker_prompt(
        doc_type=doc_type,
        public_bundle=public_bundle,
    )
    return {
        "question": "Canadian Express Entry document review",
        "claims": ["Valid claim"],
        "basis": ["Passport bio page clear"],
        "abstentions": [],
        "prose": "Review completed.",
        "case_id": case_id,
        "doc_type": doc_type,
        "_provenance": build_worker_provenance(
            pdf_sha,
            prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            bundle_hash=public_bundle["bundle_hash"],
        ),
    }


# --- Holdout Splitter & Sealer Tests ---


def test_holdout_splitter_exact_split() -> None:
    """Verify logical sibling group split places exactly 1 valid pair and 1 defective pair (4 cases) in holdout."""
    cases = _build_mock_doc_type_cases("passport")
    train_cases, holdout_cases = split_doc_type_cases(cases, doc_type="passport")

    assert len(train_cases) + len(holdout_cases) == len(cases)
    # Holdout gets 1 valid pair (2 cases) + 1 defective pair (2 cases) = 4 cases exactly
    assert len(holdout_cases) == 4
    assert len(train_cases) == 6

    # Verify no sibling pair is split across train/holdout
    train_ids = {c["opaque_case_id"] for c in train_cases}
    holdout_ids = {c["opaque_case_id"] for c in holdout_cases}

    assert len(train_ids.intersection(holdout_ids)) == 0

    for case in cases:
        cid = case["opaque_case_id"]
        sid = case["sibling_case_id"]
        if cid in holdout_ids:
            assert sid in holdout_ids, f"Sibling {sid} of holdout case {cid} was not in holdout set"
        else:
            assert sid in train_ids, f"Sibling {sid} of train case {cid} was not in train set"


def test_holdout_splitter_sibling_sealing_determinism() -> None:
    """Verify holdout selection is 100% deterministic across multiple runs."""
    cases = _build_mock_doc_type_cases("passport")
    train1, holdout1 = split_doc_type_cases(cases, doc_type="passport")
    train2, holdout2 = split_doc_type_cases(cases, doc_type="passport")

    h1_ids = [c["opaque_case_id"] for c in holdout1]
    h2_ids = [c["opaque_case_id"] for c in holdout2]
    assert h1_ids == h2_ids

    t1_ids = [c["opaque_case_id"] for c in train1]
    t2_ids = [c["opaque_case_id"] for c in train2]
    assert t1_ids == t2_ids


def test_holdout_splitter_optimizer_redaction() -> None:
    """Verify seal_holdout_findings strips all holdout scores, findings, recommendations, and labels, adding commitment hash/count."""
    cases = _build_mock_doc_type_cases("passport")
    train_cases, holdout_cases = split_doc_type_cases(cases, doc_type="passport")
    holdout_ids = {c["opaque_case_id"] for c in holdout_cases}
    train_ids = {c["opaque_case_id"] for c in train_cases}

    holdout_cid = list(holdout_ids)[0]
    train_cid = list(train_ids)[0]

    judge_batch = {
        "doc_type": "passport",
        "case_evaluations": {
            train_cid: {
                "grounding_accuracy": 1.0,
                "citation_exactness": 1.0,
                "defect_recall": 1.0,
                "pii_containment": 1.0,
                "blind_input_compliance": 1.0,
            },
            holdout_cid: {
                "grounding_accuracy": 0.5,
                "citation_exactness": 0.5,
                "defect_recall": 0.5,
                "pii_containment": 0.5,
                "blind_input_compliance": 0.5,
            },
        },
        "findings": [
            {"case_id": train_cid, "category": "defect_recall", "severity": "minor", "description": f"Finding for {train_cid}"},
            {"case_id": holdout_cid, "category": "defect_recall", "severity": "critical", "description": f"Finding for holdout {holdout_cid}"},
        ],
        "patch_recommendations": [
            {"target_file": "skills/document-agents/passport.md", "suggested_patch": f"Patch for {train_cid}"},
            {"target_file": "skills/document-agents/passport.md", "suggested_patch": f"Patch for {holdout_cid}"},
        ],
        "rationale": f"Overall batch rationale mentioning train {train_cid} and holdout {holdout_cid}.",
    }

    sealed = seal_holdout_findings(judge_batch, holdout_case_ids=holdout_ids)

    # Assert holdout case is completely purged from case_evaluations
    assert holdout_cid not in sealed["case_evaluations"]
    assert train_cid in sealed["case_evaluations"]

    # Assert holdout findings and patch recs purged
    finding_descs = [f["description"] for f in sealed["findings"]]
    assert not any(holdout_cid in desc for desc in finding_descs)

    # Rationale and recommendations are not case-bound, so neither crosses the seal.
    assert "rationale" not in sealed
    assert "patch_recommendations" not in sealed

    # Assert holdout commitment exists and contains count + hash
    assert "holdout_commitment" in sealed
    assert sealed["holdout_commitment"]["count"] == len(holdout_ids)
    assert len(sealed["holdout_commitment"]["hash"]) == 64


def test_holdout_sealer_emits_only_allowlisted_training_schema() -> None:
    sealed_id = "a" * 32
    training_id = "b" * 32
    sealed = seal_holdout_findings(
        {
            "doc_type": "passport",
            "case_evaluations": {
                training_id: {
                    "defect_recall": 0.5,
                    "expected_verdict": "defective",
                    "private_label": "training-only-secret",
                },
                sealed_id: {
                    "defect_recall": 0.0,
                    "expected_verdict": "defective",
                },
            },
            "findings": [
                {
                    "case_id": training_id,
                    "category": "defect_recall",
                    "severity": "major",
                    "description": "Training miss",
                    "score": 0.5,
                },
                {
                    "case_id": sealed_id,
                    "category": "defect_recall",
                    "severity": "critical",
                    "description": "Sealed miss",
                },
                {
                    "case_id": training_id,
                    "category": "defect_recall",
                    "severity": "major",
                    "description": "The holdout label was defective",
                },
            ],
            "patch_recommendations": [
                {
                    "target_file": "skills/document-agents/passport.md",
                    "suggested_patch": "Derived only from a sealed case without its ID",
                }
            ],
            "rationale": "Holdout score was zero and expected label was defective.",
            "_provenance": {"ground_truth_hash": "secret"},
            "holdout_findings": [{"case_id": sealed_id}],
        },
        holdout_case_ids={sealed_id},
    )

    assert set(sealed) == {
        "doc_type",
        "case_evaluations",
        "findings",
        "holdout_commitment",
    }
    assert sealed["case_evaluations"] == {training_id: {"defect_recall": 0.5}}
    assert sealed["findings"] == [
        {
            "case_id": training_id,
            "category": "defect_recall",
            "severity": "major",
            "description": "Training miss",
        }
    ]
    serialized = json.dumps(sealed).lower()
    assert sealed_id not in serialized
    assert "expected_verdict" not in serialized
    assert "holdout label" not in serialized
    assert "sealed miss" not in serialized


def test_holdout_sealer_rejects_explicit_doc_type_mismatch() -> None:
    with pytest.raises(ValueError, match="doc_type mismatch"):
        seal_holdout_findings(
            {
                "doc_type": "language_test",
                "case_evaluations": {"train-c1": {"defect_recall": 1.0}},
                "findings": [],
            },
            holdout_case_ids={"sealed-c1"},
            doc_type="passport",
        )


def test_holdout_loading_failure_fails_closed() -> None:
    """Verify seal_holdout_findings fails closed when holdout IDs cannot be resolved."""
    judge_batch = {"doc_type": "nonexistent_doc_type_12345", "case_evaluations": {}}
    with pytest.raises(ValueError, match="seal_holdout_findings failed closed"):
        seal_holdout_findings(judge_batch, doc_type="nonexistent_doc_type_12345")


# --- Privileged Batched Judge Tests ---


def test_batched_judge_command_flags_and_attachments(tmp_path: Path) -> None:
    """Verify batched Judge executes with claude-opus-4.8, --effort xhigh, --context long_context, --attachment, and isolation flags."""
    captured_cmds = []
    captured_cwds = []

    def mock_runner(cmd: List[str], cwd: Path) -> str:
        captured_cmds.append(cmd)
        captured_cwds.append(cwd)
        evt = {
            "type": "assistant.message",
            "content": json.dumps({
                "doc_type": "passport",
                "case_evaluations": {
                    "c1": {
                        "grounding_accuracy": 1.0,
                        "citation_exactness": 1.0,
                        "defect_recall": 1.0,
                        "pii_containment": 1.0,
                        "blind_input_compliance": 1.0,
                    },
                    "c2": {
                        "grounding_accuracy": 1.0,
                        "citation_exactness": 1.0,
                        "defect_recall": 1.0,
                        "pii_containment": 1.0,
                        "blind_input_compliance": 1.0,
                    },
                },
                "findings": [],
                "patch_recommendations": [],
                "rationale": "Perfect score",
            }),
        }
        return json.dumps(evt)

    pdf1 = tmp_path / "c1.pdf"
    pdf2 = tmp_path / "c2.pdf"
    p1_bytes = b"%PDF-1.4 test 1"
    p2_bytes = b"%PDF-1.4 test 2"
    pdf1.write_bytes(p1_bytes)
    pdf2.write_bytes(p2_bytes)

    worker_reports = {
        "c1": _make_mock_worker_report("c1", p1_bytes),
        "c2": _make_mock_worker_report("c2", p2_bytes),
    }
    pdf_paths = [pdf1, pdf2]
    research_json = {"triggers": ["PFL-01"]}
    gt_specs = {"c1": {"verdict": "defective"}, "c2": {"verdict": "meets_requirements"}}

    result = run_batched_document_judge(
        doc_type="passport",
        worker_reports=worker_reports,
        pdf_paths=pdf_paths,
        research_json=research_json,
        ground_truth_specs=gt_specs,
        runner_fn=mock_runner,
        output_dir=tmp_path / "output",
    )

    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    cwd = captured_cwds[0]

    # Verify model flags
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "claude-opus-4.8"
    assert "--effort" in cmd and cmd[cmd.index("--effort") + 1] == "xhigh"
    assert "--context" in cmd and cmd[cmd.index("--context") + 1] == "long_context"
    assert "--output-format" in cmd and cmd[cmd.index("--output-format") + 1] == "json"
    assert "--stream" in cmd and cmd[cmd.index("--stream") + 1] == "off"
    judge_prompt = cmd[cmd.index("-p") + 1]
    public_bundle = build_public_review_bundle("passport")
    worker_prompt = _build_worker_prompt(
        doc_type="passport",
        public_bundle=public_bundle,
    )
    assert json.dumps(public_bundle["content"], ensure_ascii=False)[1:-1] in judge_prompt
    assert json.dumps(worker_prompt, ensure_ascii=False)[1:-1] in judge_prompt
    assert "<worker_input_manifests>" in judge_prompt
    provenance = result["_provenance"]
    assert provenance["public_bundle_hashes"] == [
        public_bundle["bundle_hash"],
        public_bundle["bundle_hash"],
    ]
    assert provenance["worker_prompt_hashes"] == [
        hashlib.sha256(worker_prompt.encode("utf-8")).hexdigest(),
        hashlib.sha256(worker_prompt.encode("utf-8")).hexdigest(),
    ]
    assert len(provenance["worker_input_manifest_hashes"]) == 2

    # Verify isolation and security flags
    assert "--disallow-temp-dir" in cmd
    assert "--excluded-tools=*" in cmd
    assert "--disable-builtin-mcps" in cmd
    assert "--no-custom-instructions" in cmd
    assert "--no-ask-user" in cmd
    assert "--attach" not in cmd

    # Verify attachment flags (using --attachment, not --attach)
    attach_indices = [i for i, arg in enumerate(cmd) if arg == "--attachment"]
    attached_files = [cmd[i + 1] for i in attach_indices]
    assert "c1.pdf" in attached_files
    assert "c2.pdf" in attached_files
    assert len(attached_files) == 2

    # Verify privileged staging CWD isolation and stage cleanup
    assert "judge_staging" in str(cwd)
    assert not cwd.exists()  # Cleaned up in finally block!


def test_attachment_case_mismatch(tmp_path: Path) -> None:
    """Verify Judge fails closed when PDF attachments mismatch expected worker cases."""
    p1_bytes = b"%PDF-1.4 test 1"
    pdf1 = tmp_path / "c1.pdf"
    pdf1.write_bytes(p1_bytes)

    # worker_reports expects c1 and c2, but only c1 PDF provided
    worker_reports = {
        "c1": _make_mock_worker_report("c1", p1_bytes),
        "c2": _make_mock_worker_report("c2", p1_bytes),
    }

    with pytest.raises(JudgeExecutionError, match="PDF attachment mismatch"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports=worker_reports,
            pdf_paths=[pdf1],
            research_json={},
            ground_truth_specs={"c1": {}, "c2": {}},
            runner_fn=lambda c, w: "",
        )


def test_strict_jsonl_reasoning_and_malformed(tmp_path: Path) -> None:
    """Verify strict JSONL parser ignores reasoning events and fails on malformed JSONL or missing final JSON."""
    pdf1 = tmp_path / "c1.pdf"
    p1_bytes = b"%PDF-1.4 test 1"
    pdf1.write_bytes(p1_bytes)
    worker_reports = {"c1": _make_mock_worker_report("c1", p1_bytes)}

    # 1. Output with reasoning followed by valid assistant.message -> SUCCEEDS
    def mock_runner_with_reasoning(cmd: List[str], cwd: Path) -> str:
        l1 = json.dumps({"type": "assistant.reasoning", "content": "Thinking about scores..."})
        l2 = json.dumps({
            "type": "assistant.message",
            "data": {
                "content": json.dumps({
                    "doc_type": "passport",
                    "case_evaluations": {
                        "c1": {
                            "grounding_accuracy": 1.0,
                            "citation_exactness": 1.0,
                            "defect_recall": 1.0,
                            "pii_containment": 1.0,
                            "blind_input_compliance": 1.0,
                        },
                    },
                    "findings": [],
                    "patch_recommendations": [],
                    "rationale": "Pass",
                })
            },
        })
        return f"{l1}\n{l2}\n"

    res = run_batched_document_judge(
        doc_type="passport",
        worker_reports=worker_reports,
        pdf_paths=[pdf1],
        research_json={},
        ground_truth_specs={"c1": {}},
        runner_fn=mock_runner_with_reasoning,
    )
    assert res["rationale"] == "Pass"

    # 2. Malformed JSONL line -> FAILS CLOSED
    def mock_runner_malformed(cmd: List[str], cwd: Path) -> str:
        return "{\"type\": \"assistant.message\", INVALID_JSON}\n"

    with pytest.raises(JudgeExecutionError, match="Malformed Copilot JSONL event"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports=worker_reports,
            pdf_paths=[pdf1],
            research_json={},
            ground_truth_specs={"c1": {}},
            runner_fn=mock_runner_malformed,
        )

    # 3. Missing final JSON object -> FAILS CLOSED
    def mock_runner_no_final(cmd: List[str], cwd: Path) -> str:
        return json.dumps({"type": "assistant.reasoning", "content": "Only reasoning, no final message"})

    with pytest.raises(JudgeExecutionError, match="No valid JudgeEvaluationBatch JSON found"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports=worker_reports,
            pdf_paths=[pdf1],
            research_json={},
            ground_truth_specs={"c1": {}},
            runner_fn=mock_runner_no_final,
        )

    # 4. Prose-wrapped JSON must not be recovered by brace scanning.
    def mock_runner_prose_wrapped(cmd: List[str], cwd: Path) -> str:
        content = (
            "Here is the result: "
            + json.dumps(
                {
                    "doc_type": "passport",
                    "case_evaluations": {},
                    "findings": [],
                    "patch_recommendations": [],
                    "rationale": "wrapped",
                }
            )
        )
        return json.dumps(
            {"type": "assistant.message", "data": {"content": content}}
        )

    with pytest.raises(JudgeExecutionError, match="raw JSON object"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports=worker_reports,
            pdf_paths=[pdf1],
            research_json={},
            ground_truth_specs={"c1": {}},
            runner_fn=mock_runner_prose_wrapped,
        )

    # 5. Markdown-fenced JSON is not a raw JudgeEvaluationBatch object.
    def mock_runner_fenced(cmd: List[str], cwd: Path) -> str:
        content = "```json\n" + json.dumps(
            {
                "doc_type": "passport",
                "case_evaluations": {
                    "c1": {
                        "grounding_accuracy": 1.0,
                        "citation_exactness": 1.0,
                        "defect_recall": 1.0,
                        "pii_containment": 1.0,
                        "blind_input_compliance": 1.0,
                    }
                },
                "findings": [],
                "patch_recommendations": [],
                "rationale": "fenced",
            }
        ) + "\n```"
        return json.dumps(
            {"type": "assistant.message", "data": {"content": content}}
        )

    with pytest.raises(JudgeExecutionError, match="raw JSON object"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports=worker_reports,
            pdf_paths=[pdf1],
            research_json={},
            ground_truth_specs={"c1": {}},
            runner_fn=mock_runner_fenced,
        )


def test_batched_judge_doc_type_and_case_coverage(tmp_path: Path) -> None:
    """Verify Judge fails closed when response returns wrong doc_type or missing/extra cases."""
    pdf1 = tmp_path / "c1.pdf"
    pdf2 = tmp_path / "c2.pdf"
    p1_bytes = b"%PDF-1.4 test 1"
    p2_bytes = b"%PDF-1.4 test 2"
    pdf1.write_bytes(p1_bytes)
    pdf2.write_bytes(p2_bytes)

    worker_reports = {
        "c1": _make_mock_worker_report("c1", p1_bytes),
        "c2": _make_mock_worker_report("c2", p2_bytes),
    }

    # Wrong doc_type
    def mock_runner_wrong_doc_type(cmd: List[str], cwd: Path) -> str:
        return json.dumps({
            "type": "assistant.message",
            "content": json.dumps({
                "doc_type": "digital_photo",  # Wrong! Expected passport
                "case_evaluations": {
                    "c1": {"grounding_accuracy": 1.0, "citation_exactness": 1.0, "defect_recall": 1.0, "pii_containment": 1.0, "blind_input_compliance": 1.0},
                    "c2": {"grounding_accuracy": 1.0, "citation_exactness": 1.0, "defect_recall": 1.0, "pii_containment": 1.0, "blind_input_compliance": 1.0},
                },
                "findings": [],
                "patch_recommendations": [],
                "rationale": "Wrong doc_type",
            }),
        })

    with pytest.raises(JudgeExecutionError, match="doc_type mismatch"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports=worker_reports,
            pdf_paths=[pdf1, pdf2],
            research_json={},
            ground_truth_specs={"c1": {}, "c2": {}},
            runner_fn=mock_runner_wrong_doc_type,
        )

    # Missing case coverage
    def mock_runner_missing_case(cmd: List[str], cwd: Path) -> str:
        return json.dumps({
            "type": "assistant.message",
            "content": json.dumps({
                "doc_type": "passport",
                "case_evaluations": {
                    "c1": {"grounding_accuracy": 1.0, "citation_exactness": 1.0, "defect_recall": 1.0, "pii_containment": 1.0, "blind_input_compliance": 1.0},
                },
                "findings": [],
                "patch_recommendations": [],
                "rationale": "Incomplete",
            }),
        })

    with pytest.raises(JudgeExecutionError, match="case coverage mismatch"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports=worker_reports,
            pdf_paths=[pdf1, pdf2],
            research_json={},
            ground_truth_specs={"c1": {}, "c2": {}},
            runner_fn=mock_runner_missing_case,
        )


def test_fake_worker_provenance_and_hash_rejected(tmp_path: Path) -> None:
    """Verify Judge rejects Worker reports lacking valid Gemini long-context provenance or matching pdf sha256."""
    pdf1 = tmp_path / "c1.pdf"
    p1_bytes = b"%PDF-1.4 test 1"
    pdf1.write_bytes(p1_bytes)

    # 1. Missing _provenance
    bad_report_1 = {
        "question": "q",
        "claims": [],
        "basis": [],
        "case_id": "c1",
        "doc_type": "passport",
    }
    with pytest.raises(JudgeExecutionError, match="lacks required '_provenance'"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports={"c1": bad_report_1},
            pdf_paths=[pdf1],
            research_json={},
            ground_truth_specs={"c1": {}},
            runner_fn=lambda c, w: "",
        )

    # 2. Mismatched input_pdf_sha256
    bad_report_2 = _make_mock_worker_report("c1", p1_bytes)
    bad_report_2["_provenance"]["input_pdf_sha256"] = "0" * 64
    with pytest.raises(JudgeExecutionError, match="input_pdf_sha256 mismatch"):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports={"c1": bad_report_2},
            pdf_paths=[pdf1],
            research_json={},
            ground_truth_specs={"c1": {}},
            runner_fn=lambda c, w: "",
        )


def test_pydantic_schema_extra_forbid_nan_invalid_category_patch_target() -> None:
    """Verify Pydantic models forbid extra fields, non-finite scores, invalid categories, and bad patch targets."""
    # Extra fields forbidden
    with pytest.raises(ValidationError):
        CaseScore.model_validate({
            "grounding_accuracy": 1.0,
            "citation_exactness": 1.0,
            "defect_recall": 1.0,
            "pii_containment": 1.0,
            "blind_input_compliance": 1.0,
            "extra_field": 123,
        })

    # Non-finite score
    with pytest.raises(ValidationError):
        CaseScore.model_validate({
            "grounding_accuracy": float("nan"),
            "citation_exactness": 1.0,
            "defect_recall": 1.0,
            "pii_containment": 1.0,
            "blind_input_compliance": 1.0,
        })

    # Invalid finding category
    with pytest.raises(ValidationError):
        CaseFinding.model_validate({
            "case_id": "c1",
            "category": "invented_category",
            "severity": "minor",
            "description": "desc",
        })

    # Invalid patch target file
    with pytest.raises(ValidationError):
        PatchRecommendation.model_validate({
            "target_file": "random/unauthorized/path.py",
            "suggested_patch": "patch",
        })


@pytest.mark.parametrize(
    "invalid_score",
    [True, False, "1.0", "0", float("nan"), float("inf"), Decimal("1.0")],
)
def test_judge_scores_reject_coercion_and_non_json_numbers(
    invalid_score: object,
) -> None:
    scores = {
        "grounding_accuracy": 1.0,
        "citation_exactness": 1.0,
        "defect_recall": 1.0,
        "pii_containment": 1.0,
        "blind_input_compliance": 1.0,
    }
    scores["grounding_accuracy"] = invalid_score

    with pytest.raises(ValidationError):
        CaseScore.model_validate(scores)


@pytest.mark.parametrize("invalid_json_score", [True, "1.0", "0"])
def test_judge_raw_json_scores_are_validated_before_dump(
    invalid_json_score: object,
) -> None:
    payload = {
        "doc_type": "passport",
        "case_evaluations": {
            "c1": {
                "grounding_accuracy": invalid_json_score,
                "citation_exactness": 1.0,
                "defect_recall": 1.0,
                "pii_containment": 1.0,
                "blind_input_compliance": 1.0,
            }
        },
        "findings": [],
        "patch_recommendations": [],
        "rationale": "Strict score test.",
    }

    with pytest.raises(ValidationError):
        JudgeEvaluationBatch.model_validate_json(json.dumps(payload))


def test_batched_judge_prohibits_score_fabrication(tmp_path: Path) -> None:
    """Verify process failure stays infrastructure and never fabricates scores."""
    def mock_runner_failing(cmd: List[str], cwd: Path) -> str:
        raise RuntimeError("Copilot CLI process timeout")

    pdf1 = tmp_path / "c1.pdf"
    p1_bytes = b"%PDF-1.4 test 1"
    pdf1.write_bytes(p1_bytes)
    worker_reports = {"c1": _make_mock_worker_report("c1", p1_bytes)}

    out_dir = tmp_path / "output"

    with pytest.raises(AgentLifecycleError):
        run_batched_document_judge(
            doc_type="passport",
            worker_reports=worker_reports,
            pdf_paths=[pdf1],
            research_json={},
            ground_truth_specs={"c1": {}},
            runner_fn=mock_runner_failing,
            output_dir=out_dir,
        )

    # Verify judge_error.json exists and no fake judge_batch.json was written
    assert (out_dir / "judge_error.json").is_file()
    assert not (out_dir / "judge_batch.json").is_file()

    error_data = json.loads((out_dir / "judge_error.json").read_text(encoding="utf-8"))
    assert error_data["doc_type"] == "passport"
    assert "error" in error_data


def test_batched_judge_provenance_and_redaction(tmp_path: Path) -> None:
    """Verify provenance contains truthful metadata and no raw privileged input is leaked in aggregate output."""
    pdf1 = tmp_path / "c1.pdf"
    p1_bytes = b"%PDF-1.4 test 1"
    pdf1.write_bytes(p1_bytes)
    worker_reports = {"c1": _make_mock_worker_report("c1", p1_bytes)}

    def mock_runner_success(cmd: List[str], cwd: Path) -> str:
        return json.dumps({
            "type": "assistant.message",
            "content": json.dumps({
                "doc_type": "passport",
                "case_evaluations": {
                    "c1": {
                        "grounding_accuracy": 1.0,
                        "citation_exactness": 1.0,
                        "defect_recall": 1.0,
                        "pii_containment": 1.0,
                        "blind_input_compliance": 1.0,
                    },
                },
                "findings": [],
                "patch_recommendations": [],
                "rationale": "Pass",
            }),
        })

    research = {"secret_trigger": "PFL-TOP-SECRET"}
    gt = {"c1": {"secret_gt_key": "CLASSIFIED"}}

    res = run_batched_document_judge(
        doc_type="passport",
        worker_reports=worker_reports,
        pdf_paths=[pdf1],
        research_json=research,
        ground_truth_specs=gt,
        runner_fn=mock_runner_success,
        output_dir=tmp_path / "output",
    )

    prov = res["_provenance"]
    assert prov["model"] == "claude-opus-4.8"
    assert prov["effort"] == "xhigh"
    assert prov["context_tier"] == "long_context"
    assert prov["engine"] == "injected-test-runner"
    assert prov["is_live"] is False

    serialized = json.dumps(prov)
    assert "command" not in prov
    assert "PFL-TOP-SECRET" not in serialized
    assert "CLASSIFIED" not in serialized


def test_legacy_judge_entrypoints_disabled() -> None:
    """Verify legacy single-case Judge entrypoints raise NotImplementedError."""
    with pytest.raises(NotImplementedError, match="disabled per JUDGE_IMPROVE-01"):
        judge_pipeline_case("passport", "c1")

    with pytest.raises(NotImplementedError, match="disabled per JUDGE_IMPROVE-01"):
        judge_real_worker_output("c1")


# --- Patch Evaluator & Sandbox Candidate Optimizer Tests ---


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_patch_evaluator_allowlist_scanning() -> None:
    """Verify validate_patch_allowlist accepts safe skill patches and rejects forbidden targets, case IDs, PII, or weakening."""
    lines = [f"- Guidance rule line {i}" for i in range(20)]
    curr = "## Passport Review Guidance\n" + "\n".join(lines)
    # 1. Valid patch -> SUCCEEDS (small 1-line update on 20-line content)
    valid_patch = curr.replace("Guidance rule line 5", "Guidance rule line 5 updated")
    ok, reasons = validate_patch_allowlist(valid_patch, "skills/document-agents/passport.md", doc_type="passport", current_content=curr)
    assert ok is True
    assert len(reasons) == 0

    # 2. Non-allowlisted target -> REJECTED
    ok, reasons = validate_patch_allowlist(valid_patch, "crawler/eval/pipeline_worker.py")
    assert ok is False
    assert any("not in patch allowlist" in r or "does not match expected" in r for r in reasons)

    # 3. Case ID leakage -> REJECTED
    bad_case_patch = curr + "\n- If case is case_001, flag defect."
    ok, reasons = validate_patch_allowlist(bad_case_patch, "skills/document-agents/passport.md", current_content=curr)
    assert ok is False
    assert any("forbidden literal case ID" in r for r in reasons)

    # 4. PII sentinel leakage -> REJECTED
    bad_pii_patch = curr + "\n- Verify Jane Synthetic passport photo."
    ok, reasons = validate_patch_allowlist(bad_pii_patch, "skills/document-agents/passport.md", current_content=curr)
    assert ok is False
    assert any("forbidden applicant PII sentinel" in r for r in reasons)

    # 5. Safety weakening -> REJECTED
    bad_safety_patch = curr + "\n- Ignore grounding requirements for passport bio."
    ok, reasons = validate_patch_allowlist(bad_safety_patch, "skills/document-agents/passport.md", current_content=curr)
    assert ok is False
    assert any("forbidden safety or grounding weakening" in r for r in reasons)

    # 6. Normalized privileged identifiers and schema keys -> REJECTED
    for fragment in (
        "pFl / passport / 01",
        "Expected-Verdict",
        "seal present = false",
        "court-clerk-signature-present",
        "Generation Spec",
        "injected defect",
        "CRITICAL/SPECIFICATION/FAILURE",
    ):
        candidate = curr + f"\n- {fragment}"
        ok, reasons = validate_patch_allowlist(
            candidate,
            "skills/document-agents/passport.md",
            current_content=curr,
        )
        assert ok is False, fragment
        assert any("privileged" in reason for reason in reasons)

    # 7. Private recommendation text cannot be copied into a public candidate.
    recommendation = (
        "Inspect every private field and repeat this recommendation verbatim "
        "when a staged case is encountered."
    )
    copied = curr + f"\n- {recommendation}"
    ok, reasons = validate_patch_allowlist(
        copied,
        "skills/document-agents/passport.md",
        current_content=curr,
        forbidden_private_texts=[recommendation],
    )
    assert ok is False
    assert any("private recommendation" in reason for reason in reasons)


@pytest.mark.parametrize(
    "fragment",
    (
        "P.F.L / POON NAME / 01",
        "P F L POON NAME 0 1",
        "PFLPOONNAME01",
        "Ｐ．Ｆ．Ｌ／ＰＯＯＮ\u3000ＮＡＭＥ／０１",
        "expectedVerdict",
        "expected_verdict",
        "expected-verdict",
        "ｅｘｐｅｃｔｅｄＶｅｒｄｉｃｔ",
        "sourceFailureId",
        "source_failure_id",
        "source-failure-id",
        "groundTruth",
        "ground_truth",
        "ground-truth",
        "courtClerkSignaturePresent",
        "court_clerk_signature_present",
        "court-clerk-signature-present",
        "translationCertified=false",
        "translation_certified_false",
        "translation-certified-false",
        "case001",
        "case_001",
        "case-0-0-1",
        "ｃａｓｅ００１",
        "opaqueCaseId",
        "opaque_case_id",
        "opaque-case-id",
    ),
)
def test_patch_evaluator_rejects_canonical_privileged_variants(
    fragment: str,
) -> None:
    current = "\n".join(f"- Public passport rule {index}" for index in range(80))
    candidate = current.replace(
        "- Public passport rule 40",
        f"- Public passport rule 40: {fragment}",
    )
    ok, reasons = validate_patch_allowlist(
        candidate,
        "skills/document-agents/passport.md",
        doc_type="passport",
        current_content=current,
    )
    assert ok is False
    assert any("privileged" in reason for reason in reasons)


def _private_phrase_internal_split_variants() -> tuple[tuple[str, str], ...]:
    variants = []
    for phrase in sorted(_PRIVILEGED_NORMALIZED_PHRASES):
        words = phrase.split()
        for index, word in enumerate(words):
            if len(word) < 4:
                continue
            split_at = len(word) // 2
            split_words = list(words)
            split_words[index] = f"{word[:split_at]}-{word[split_at:]}"
            variants.append((phrase, "-".join(split_words)))
    return tuple(variants)


_PRIVILEGED_IDENTIFIER_EXAMPLES = (
    ("case-short", "case001"),
    ("case-long", "case12345678"),
    ("internal-def-vector", "defv1"),
    ("internal-def-scanned", "defs2048"),
    ("internal-val-vector", "valv17"),
    ("internal-val-scanned", "vals99999999"),
    ("pfl-short", "pfl01"),
    ("pfl-document", "pflpassport01"),
    ("pfl-other-name", "pflpoonname01"),
    ("failure-label", "failureid"),
    ("source-failure-label", "sourcefailureid"),
    ("research-failure-label", "researchfailureid"),
    ("opaque-label", "opaquecaseid"),
    ("opaque-hex", "0123456789abcdef0123456789abcdef"),
)
_IDENTIFIER_SPLIT_DELIMITERS = tuple(chr(codepoint) for codepoint in range(0x21)) + tuple(
    string.punctuation
)
_IDENTIFIER_COMBINING_MARKS = (
    ("acute", "\N{COMBINING ACUTE ACCENT}"),
    ("circumflex", "\N{COMBINING CIRCUMFLEX ACCENT}"),
    ("diaeresis", "\N{COMBINING DIAERESIS}"),
    ("cedilla-ccc202", "\N{COMBINING CEDILLA}"),
    ("comma-above-right-ccc232", "\N{COMBINING COMMA ABOVE RIGHT}"),
    ("ypogegrammeni-ccc240", "\N{COMBINING GREEK YPOGEGRAMMENI}"),
    ("spacing-combining-mark", "\N{DEVANAGARI SIGN VISARGA}"),
    ("enclosing-combining-mark", "\N{COMBINING ENCLOSING CIRCLE}"),
)
_COMBINING_IDENTIFIER_EXAMPLES = (
    ("case", "case001"),
    ("def", "defv1"),
    ("val", "vals99999999"),
    ("pfl", "pflpassport01"),
    ("opaque-hex", "0123456789abcdef0123456789abcdef"),
)


def _privileged_identifier_split_variants():
    for grammar, identifier in _PRIVILEGED_IDENTIFIER_EXAMPLES:
        for split_at in range(1, len(identifier)):
            for delimiter in _IDENTIFIER_SPLIT_DELIMITERS:
                yield (
                    grammar,
                    identifier,
                    split_at,
                    ord(delimiter),
                    f"{identifier[:split_at]}{delimiter}{identifier[split_at:]}",
                )


def _privileged_identifier_combining_mark_variants():
    for grammar, identifier in _COMBINING_IDENTIFIER_EXAMPLES:
        for position in range(len(identifier) + 1):
            for mark_name, mark in _IDENTIFIER_COMBINING_MARKS:
                yield (
                    grammar,
                    identifier,
                    position,
                    mark_name,
                    f"{identifier[:position]}{mark}{identifier[position:]}",
                )


@pytest.mark.parametrize(
    ("phrase", "fragment"),
    _private_phrase_internal_split_variants(),
)
def test_candidate_and_optimizer_target_reject_private_internal_splits(
    phrase: str,
    fragment: str,
) -> None:
    current = "\n".join(f"- Public passport rule {index}" for index in range(80))
    candidate = current.replace(
        "- Public passport rule 40",
        f"- Public passport rule 40: {fragment}",
    )
    ok, reasons = validate_patch_allowlist(
        candidate,
        "skills/document-agents/passport.md",
        doc_type="passport",
        current_content=current,
    )
    assert ok is False, phrase
    assert any("privileged" in reason for reason in reasons), (phrase, reasons)

    ok, reasons, _ = validate_target_allowlist(
        f"skills/document-agents/{fragment}.md"
    )
    assert ok is False, phrase
    assert any("privileged" in reason for reason in reasons), (phrase, reasons)


def test_patch_candidate_and_optimizer_target_reject_every_identifier_split() -> None:
    current = "\n".join(f"- Public passport rule {index}" for index in range(80))
    for grammar, identifier, split_at, codepoint, fragment in (
        _privileged_identifier_split_variants()
    ):
        context = (grammar, identifier, split_at, codepoint, repr(fragment))
        candidate = current.replace(
            "- Public passport rule 40",
            f"- Public passport rule 40: {fragment}",
        )
        ok, reasons = validate_patch_allowlist(
            candidate,
            "skills/document-agents/passport.md",
            doc_type="passport",
            current_content=current,
        )
        assert ok is False, ("patch/candidate", *context)
        assert any("privileged" in reason for reason in reasons), (
            "patch/candidate",
            *context,
            reasons,
        )

        ok, reasons, _ = validate_target_allowlist(
            f"skills/document-agents/{fragment}.md"
        )
        assert ok is False, ("optimizer target", *context)
        assert any("privileged" in reason for reason in reasons), (
            "optimizer target",
            *context,
            reasons,
        )


def test_patch_candidate_and_optimizer_reject_identifier_combining_marks() -> None:
    current = "\n".join(f"- Public passport rule {index}" for index in range(80))
    for grammar, identifier, position, mark_name, fragment in (
        _privileged_identifier_combining_mark_variants()
    ):
        context = (grammar, identifier, position, mark_name, repr(fragment))
        candidate = current.replace(
            "- Public passport rule 40",
            f"- Public passport rule 40: {fragment}",
        )
        ok, reasons = validate_patch_allowlist(
            candidate,
            "skills/document-agents/passport.md",
            doc_type="passport",
            current_content=current,
        )
        assert ok is False, ("patch/candidate", *context)
        assert any("privileged" in reason for reason in reasons), (
            "patch/candidate",
            *context,
            reasons,
        )

        ok, reasons, _ = validate_target_allowlist(
            f"skills/document-agents/{fragment}.md"
        )
        assert ok is False, ("optimizer target", *context)
        assert any("privileged" in reason for reason in reasons), (
            "optimizer target",
            *context,
            reasons,
        )


@pytest.mark.parametrize(
    "control",
    (
        "The expected result is determined from the cited public rule.",
        "Ground officers must verify source documents.",
        "A translation certification may be required.",
        "The court clerk must sign the public form when required.",
        "Use the examples in cases 1 through 3.",
        "A failure to include a passport can make an application incomplete.",
        "The latest database contains the public guidance.",
        "The showcase kindergarten application is complete.",
        "Failure identification is part of routine triage.",
        "The background truth is visible in the cited image.",
        "Coworker outputs are reviewed independently.",
    ),
)
def test_patch_evaluator_accepts_clean_public_rule_controls(control: str) -> None:
    current = "\n".join(f"- Public passport rule {index}" for index in range(80))
    candidate = current.replace(
        "- Public passport rule 40",
        f"- Public passport rule 40: {control}",
    )
    ok, reasons = validate_patch_allowlist(
        candidate,
        "skills/document-agents/passport.md",
        doc_type="passport",
        current_content=current,
    )
    assert ok is True, reasons


def _make_full_metrics(overall: float = 1.0, grounding: float = 1.0, citation: float = 1.0, recall: float = 1.0, pii: float = 1.0, blind: float = 1.0) -> Dict[str, float]:
    return {
        "grounding_accuracy": grounding,
        "citation_exactness": citation,
        "defect_recall": recall,
        "pii_containment": pii,
        "blind_input_compliance": blind,
        "overall_score": overall,
    }


def test_patch_evaluator_regression_gate() -> None:
    """Verify evaluate_candidate_patch accepts only train-improving patches with zero holdout regression."""
    b_train = _make_full_metrics(0.80, recall=0.60)
    b_holdout = _make_full_metrics(1.0)

    # Case 1: Train improved, zero holdout regression -> ACCEPTED
    c_train_good = _make_full_metrics(0.90, recall=0.80)
    c_holdout_good = dict(b_holdout)
    assert evaluate_candidate_patch(b_train, b_holdout, c_train_good, c_holdout_good) is True

    # Case 2: Train improved, but holdout defect_recall regressed -> REJECTED
    c_holdout_regressed = dict(b_holdout)
    c_holdout_regressed["defect_recall"] = 0.75
    assert evaluate_candidate_patch(b_train, b_holdout, c_train_good, c_holdout_regressed) is False

    # Case 3: Train regressed or unchanged -> REJECTED
    c_train_flat = _make_full_metrics(0.80, recall=0.60)
    assert evaluate_candidate_patch(b_train, b_holdout, c_train_flat, b_holdout) is False


def test_optimizer_candidate_generation_sandbox_isolation(tmp_path: Path) -> None:
    """Verify Gemini candidate optimizer writes patch proposals exclusively into proposal sandboxes without modifying source."""
    captured_cmds = []

    # Read current skill to construct a realistic candidate patch with minimal diff
    passport_skill = (_REPO_ROOT / "skills" / "document-agents" / "passport.md").read_text(encoding="utf-8")
    updated_skill = passport_skill + "\n- Check visa seal and signature clarity.\n"

    def mock_optimizer_runner(cmd: List[str], cwd: Path) -> str:
        captured_cmds.append(cmd)
        resp = {
            "target_file": "skills/document-agents/passport.md",
            "candidate_content": updated_skill,
            "rationale": "Fix signature verification defect",
        }
        return json.dumps({"type": "assistant.message", "content": json.dumps(resp)})

    training_findings = {
        "doc_type": "passport",
        "case_evaluations": {"train_c1": {"defect_recall": 0.5}},
        "findings": [{"case_id": "train_c1", "description": "Missed signature defect"}],
        "holdout_commitment": {"count": 4, "hash": "f" * 64},
    }

    res = run_candidate_optimization_pass(
        doc_type="passport",
        training_findings=training_findings,
        runner_fn=mock_optimizer_runner,
        proposal_sandbox_root=tmp_path / "proposals",
    )

    # Verify optimizer command flags
    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "gemini-3.6-flash"
    assert "--context" in cmd and cmd[cmd.index("--context") + 1] == "long_context"

    # Verify output written to sandbox, NOT shared source
    assert "proposals" in res["candidate_relpath"]
    candidate_file = tmp_path / "proposals" / res["candidate_id"] / res["target_file"]
    assert candidate_file.is_file()
    assert candidate_file.read_text(encoding="utf-8") == updated_skill

    # Verify patch is valid
    assert res["is_valid"] is True
    assert res["_provenance"]["model"] == "gemini-3.6-flash"


def test_all_23_doc_types_canonical_mapping() -> None:
    """Verify all 23 document types resolve to canonical hyphenated skill files in skills/document-agents/."""
    from crawler.eval.public_bundle import DOC_TYPE_TO_SKILL, resolve_skill_path

    all_23_doc_types = [
        "passport", "language_test", "educational_credential_assessment",
        "employment_reference_letter", "proof_of_funds", "medical_examination",
        "police_certificate", "digital_photo", "certified_translation",
        "written_job_offer_lmia", "proof_of_studies", "certificate_of_qualification",
        "birth_certificate", "marriage_certificate", "statutory_declaration_common_law",
        "divorce_certificate", "death_certificate", "adoption_certificate",
        "use_of_representative", "relative_in_canada", "proof_of_other_name",
        "authority_to_release_info", "letter_of_explanation"
    ]

    skills_dir = _REPO_ROOT / "skills" / "document-agents"
    for dt in all_23_doc_types:
        skill_file = resolve_skill_path(dt)
        assert skill_file.is_file(), f"Missing skill file for {dt}: {skill_file}"
        assert "_" not in skill_file.name, f"Skill file {skill_file.name} for {dt} contains forbidden underscore"
        stem = DOC_TYPE_TO_SKILL[dt]
        assert skill_file.name == f"{stem}.md"


def test_optimizer_strict_json_proposal() -> None:
    """Verify _parse_optimizer_jsonl_output enforces strict OptimizerProposal JSON matching expected target."""
    from crawler.eval.genuine_optimizer import _parse_optimizer_jsonl_output

    target = "skills/document-agents/passport.md"

    # 1. Valid JSON proposal -> SUCCEEDS
    valid_evt = {
        "type": "assistant.message",
        "data": {
            "content": json.dumps({
                "target_file": target,
                "candidate_content": "## Updated Passport Rules",
                "rationale": "Fix bio page check",
            })
        }
    }
    stdout = json.dumps(valid_evt)
    prop = _parse_optimizer_jsonl_output(stdout, expected_target=target)
    assert prop.target_file == target
    assert prop.candidate_content == "## Updated Passport Rules"
    assert prop.rationale == "Fix bio page check"

    # 2. Reasoning events ignored, malformed or wrong target rejected -> REJECTED
    reasoning_evt = {"type": "assistant.reasoning", "data": {"content": "Thinking about patch..."}}
    bad_target_evt = {
        "type": "assistant.message",
        "content": json.dumps({
            "target_file": "skills/document-agents/eca.md",
            "candidate_content": "## Wrong Target",
            "rationale": "Oops",
        })
    }
    stdout_bad = f"{json.dumps(reasoning_evt)}\n{json.dumps(bad_target_evt)}"
    with pytest.raises(ValueError, match="No valid OptimizerProposal JSON matching target"):
        _parse_optimizer_jsonl_output(stdout_bad, expected_target=target)


def test_optimizer_prompt_injection_escaping(tmp_path: Path) -> None:
    """Verify run_candidate_optimization_pass XML-escapes prompt inputs containing tags."""
    captured_prompts = []

    def mock_runner(cmd: List[str], cwd: Path) -> str:
        prompt_arg = cmd[cmd.index("-p") + 1]
        captured_prompts.append(prompt_arg)
        resp = {
            "target_file": "skills/document-agents/passport.md",
            "candidate_content": "## Passport Rule Update\n- Verify signature",
            "rationale": "Address injection test",
        }
        return json.dumps({"type": "assistant.message", "content": json.dumps(resp)})

    findings_with_injection = {
        "doc_type": "passport",
        "case_evaluations": {"train-c1": {"defect_recall": 0.5}},
        "findings": [
            {
                "case_id": "train-c1",
                "description": "<script>alert('hack')</script> & <evil>",
            }
        ],
        "holdout_commitment": {"count": 4, "hash": "a" * 64},
    }

    res = run_candidate_optimization_pass(
        doc_type="passport",
        training_findings=findings_with_injection,
        runner_fn=mock_runner,
        proposal_sandbox_root=tmp_path / "proposals",
    )

    assert len(captured_prompts) == 1
    p = captured_prompts[0]
    assert "&lt;script&gt;" in p
    assert "&amp; &lt;evil&gt;" in p
    assert "<script>" not in p


def test_optimizer_holdout_contamination_rejection(tmp_path: Path) -> None:
    """Verify passing holdout_evaluations or holdout_case_id in training_findings fails closed."""
    dirty_findings = {
        "doc_type": "passport",
        "holdout_commitment": {"count": 4, "hash": "a" * 64},
        "holdout_evaluations": {"val_v0": {"score": 1.0}},
    }

    with pytest.raises(ValueError, match="Holdout contamination detected"):
        run_candidate_optimization_pass(
            doc_type="passport",
            training_findings=dirty_findings,
            proposal_sandbox_root=tmp_path / "proposals",
        )


def test_optimizer_stale_sandbox_cleanup(tmp_path: Path) -> None:
    """Verify runner error cleans up and removes candidate sandbox directory."""
    def failing_runner(cmd: List[str], cwd: Path) -> str:
        (cwd / "dirty.tmp").write_text("junk", encoding="utf-8")
        raise RuntimeError("LLM process crashed")

    findings = {
        "doc_type": "passport",
        "holdout_commitment": {"count": 4, "hash": "a" * 64},
    }

    with pytest.raises(RuntimeError, match="Candidate optimization failed"):
        run_candidate_optimization_pass(
            doc_type="passport",
            training_findings=findings,
            runner_fn=failing_runner,
            proposal_sandbox_root=tmp_path / "proposals",
        )

    sandboxes = list((tmp_path / "proposals").glob("candidate_*"))
    assert len(sandboxes) == 0


def test_optimizer_provenance_no_absolute_paths(tmp_path: Path) -> None:
    """Verify optimizer output dictionary and provenance contain candidate ID and hashes, but NO absolute paths."""
    def mock_runner(cmd: List[str], cwd: Path) -> str:
        resp = {
            "target_file": "skills/document-agents/passport.md",
            "candidate_content": "# Passport Skill\n- Verify signature",
            "rationale": "Clean path test",
        }
        return json.dumps({"type": "assistant.message", "content": json.dumps(resp)})

    findings = {
        "doc_type": "passport",
        "holdout_commitment": {"count": 4, "hash": "b" * 64},
    }

    res = run_candidate_optimization_pass(
        doc_type="passport",
        training_findings=findings,
        runner_fn=mock_runner,
        proposal_sandbox_root=tmp_path / "proposals",
    )

    prov = res["_provenance"]
    prov_str = json.dumps(prov)

    assert str(tmp_path) not in prov_str
    assert "/home/" not in prov_str
    assert "/tmp/" not in prov_str

    assert prov["output_hash"] == hashlib.sha256(
        res["_optimizer_output"].encode("utf-8")
    ).hexdigest()
    assert prov["engine"] == "injected-test-runner"
    assert prov["is_live"] is False


def _valid_optimizer_candidate_result() -> Dict[str, Any]:
    candidate_content = "# Passport Skill\n- Verify signature"
    target_file = "skills/document-agents/passport.md"
    rationale = "Verify passport signature"
    raw_output = json.dumps(
        {
            "target_file": target_file,
            "candidate_content": candidate_content,
            "rationale": rationale,
        }
    )
    findings_hash = "a" * 64
    prompt_hash = "b" * 64
    candidate_id = derive_optimizer_candidate_id(
        findings_hash,
        prompt_hash,
        target_file,
    )
    provenance = build_provenance(
        "optimizer",
        live=False,
        prompt_hash=prompt_hash,
        attachment_hashes=[],
        output_hash=hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
        extras={
            "input_findings_sha256": findings_hash,
            "candidate_content_hash": hashlib.sha256(
                candidate_content.encode("utf-8")
            ).hexdigest(),
            "candidate_id": candidate_id,
            "target_file": target_file,
        },
    )
    return {
        "candidate_id": candidate_id,
        "candidate_content": candidate_content,
        "target_file": target_file,
        "rationale": rationale,
        "_optimizer_output": raw_output,
        "_provenance": provenance,
    }


def _redigest_optimizer_candidate_result(candidate_result: Dict[str, Any]) -> None:
    provenance = candidate_result["_provenance"]
    provenance["provenance_digest"] = optimizer_provenance_digest(provenance)


def test_optimizer_provenance_publication_is_complete_and_content_free() -> None:
    candidate_result = _valid_optimizer_candidate_result()
    candidate_result["_provenance"].update(
        {
            "raw_prompt": "Applicant Jane Doe at /home/private/candidate.json",
            "reasoning": "private chain of thought",
            "candidate_content": candidate_result["candidate_content"],
            "pii": {"name": "Jane Doe"},
            "private_path": "/home/private/proposal",
        }
    )

    published = _publishable_optimizer_provenance(candidate_result)

    assert set(published) == set(_PUBLISHABLE_OPTIMIZER_PROVENANCE_FIELDS)
    for forbidden_key in (
        "raw_prompt",
        "reasoning",
        "candidate_content",
        "pii",
        "private_path",
    ):
        assert forbidden_key not in published
    serialized = json.dumps(published, sort_keys=True)
    for secret in (
        "Jane Doe",
        "/home/private",
    ):
        assert secret not in serialized


@pytest.mark.parametrize(
    "missing_field",
    _PUBLISHABLE_OPTIMIZER_PROVENANCE_FIELDS,
)
def test_optimizer_provenance_publication_rejects_each_missing_required_field(
    missing_field: str,
) -> None:
    candidate_result = _valid_optimizer_candidate_result()
    candidate_result["_provenance"].pop(missing_field)
    if missing_field != "provenance_digest":
        _redigest_optimizer_candidate_result(candidate_result)

    with pytest.raises(ValueError, match="optimizer provenance"):
        _publishable_optimizer_provenance(candidate_result)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("input_findings_sha256", "not-a-hash"),
        ("prompt_hash", "A" * 64),
        ("output_hash", None),
        ("candidate_content_hash", "d" * 63),
        ("provenance_digest", "e" * 64),
        ("started_at", "not-a-timestamp"),
        ("completed_at", "2026-07-25T11:59:59+00:00"),
        ("duration_seconds", -1.0),
        ("duration_seconds", float("nan")),
        ("duration_seconds", True),
        ("candidate_id", "candidate_not-a-digest"),
        ("session_id", "/home/private/session"),
        ("retry_classification", "transient"),
    ],
)
def test_optimizer_provenance_publication_rejects_malformed_values(
    field: str,
    invalid_value: Any,
) -> None:
    candidate_result = _valid_optimizer_candidate_result()
    candidate_result["_provenance"][field] = invalid_value
    if field != "provenance_digest":
        _redigest_optimizer_candidate_result(candidate_result)

    with pytest.raises(ValueError, match="optimizer provenance"):
        _publishable_optimizer_provenance(candidate_result)


def test_optimizer_provenance_publication_binds_candidate_identity_and_content() -> None:
    for mutation in ("identity", "content"):
        candidate_result = deepcopy(_valid_optimizer_candidate_result())
        if mutation == "identity":
            candidate_result["candidate_id"] = "candidate_fedcba987654"
        else:
            candidate_result["candidate_content"] += "\n- Unbound mutation"

        with pytest.raises(ValueError, match="optimizer provenance"):
            _publishable_optimizer_provenance(candidate_result)


def test_optimizer_provenance_recomputes_coordinated_candidate_identity() -> None:
    candidate_result = _valid_optimizer_candidate_result()
    forged_id = "candidate_fedcba987654"
    candidate_result["candidate_id"] = forged_id
    candidate_result["_provenance"]["candidate_id"] = forged_id
    _redigest_optimizer_candidate_result(candidate_result)

    with pytest.raises(ValueError, match="candidate_id"):
        _publishable_optimizer_provenance(candidate_result)


def test_optimizer_provenance_recomputes_candidate_from_raw_output() -> None:
    candidate_result = _valid_optimizer_candidate_result()
    candidate_result.update(
        {
            "target_file": "skills/document-agents/passport.md",
            "rationale": "Original rationale",
            "_optimizer_output": json.dumps(
                {
                    "target_file": "skills/document-agents/passport.md",
                    "candidate_content": candidate_result["candidate_content"],
                    "rationale": "Original rationale",
                }
            ),
        }
    )
    forged_content = candidate_result["candidate_content"] + "\n- Forged mutation"
    candidate_result["candidate_content"] = forged_content
    candidate_result["_provenance"]["candidate_content_hash"] = hashlib.sha256(
        forged_content.encode("utf-8")
    ).hexdigest()
    _redigest_optimizer_candidate_result(candidate_result)

    with pytest.raises(ValueError, match="output"):
        _publishable_optimizer_provenance(candidate_result)


def test_injected_optimizer_provenance_cannot_be_relabelled_live() -> None:
    candidate_result = _valid_optimizer_candidate_result()
    candidate_result["_provenance"].update(
        {
            "engine": "copilot-sdk",
            "is_live": True,
        }
    )
    _redigest_optimizer_candidate_result(candidate_result)

    with pytest.raises(ValueError, match="optimizer provenance"):
        _publishable_optimizer_provenance(candidate_result)


def test_patch_evaluator_adversarial_checks() -> None:
    """Verify validate_patch_allowlist catches diff bounds, control chars, unclosed fences, case IDs, and safety weakening."""
    lines = [f"- Guidance rule line {i}" for i in range(20)]
    curr = "## Skill\n" + "\n".join(lines)

    # 1. Valid patch with matching current_content -> SUCCEEDS
    valid_patch = curr.replace("Guidance rule line 5", "Guidance rule line 5 updated")
    ok, reasons = validate_patch_allowlist(valid_patch, "skills/document-agents/passport.md", doc_type="passport", current_content=curr)
    assert ok is True
    assert len(reasons) == 0

    # 2. Control chars -> REJECTED
    ctrl_patch = curr + "\x00\x01\x02"
    ok, reasons = validate_patch_allowlist(ctrl_patch, "skills/document-agents/passport.md", doc_type="passport", current_content=curr)
    assert ok is False
    assert any("control or binary" in r for r in reasons)

    # 3. Unclosed code fence -> REJECTED
    fence_patch = curr + "\n```markdown\nsome code\nno closing fence"
    ok, reasons = validate_patch_allowlist(fence_patch, "skills/document-agents/passport.md", doc_type="passport", current_content=curr)
    assert ok is False
    assert any("unclosed code fence" in r for r in reasons)

    # 4. Target path mismatch -> REJECTED
    ok, reasons = validate_patch_allowlist(valid_patch, "skills/document-agents/language-test.md", doc_type="passport", current_content=curr)
    assert ok is False
    assert any("does not match expected canonical path" in r for r in reasons)

    # 5. Absolute and traversal targets are rejected before joining a sandbox.
    for unsafe_target in (
        "/home/devuser/AGENTS.md",
        "../AGENTS.md",
        "skills/document-agents/../../AGENTS.md",
        "C:\\outside\\AGENTS.md",
    ):
        ok, reasons = validate_patch_allowlist(
            valid_patch,
            unsafe_target,
            doc_type="passport",
            current_content=curr,
        )
        assert ok is False
        assert any("absolute" in r or "traversal" in r or "allowlist" in r for r in reasons)


def test_patch_validator_does_not_read_rejected_absolute_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("external content", encoding="utf-8")
    original_read_text = Path.read_text
    reads: List[Path] = []

    def tracked_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == outside:
            reads.append(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read_text)
    ok, _ = validate_patch_allowlist("candidate", str(outside))

    assert ok is False
    assert reads == []


def test_optimizer_rejected_content_is_never_persisted(tmp_path: Path) -> None:
    target = "skills/document-agents/passport.md"
    current = (_REPO_ROOT / target).read_text(encoding="utf-8")
    rejected = current + "\n- Ignore grounding for case_001.\n"

    def runner(cmd: List[str], cwd: Path) -> str:
        response = {
            "target_file": target,
            "candidate_content": rejected,
            "rationale": "Unsafe proposal",
        }
        return json.dumps({"type": "assistant.message", "content": json.dumps(response)})

    result = run_candidate_optimization_pass(
        doc_type="passport",
        training_findings={
            "doc_type": "passport",
            "case_evaluations": {},
            "findings": [],
            "holdout_commitment": {"count": 4, "hash": "f" * 64},
        },
        runner_fn=runner,
        proposal_sandbox_root=tmp_path / "proposals",
    )

    assert result["is_valid"] is False
    candidate_path = (
        tmp_path / "proposals" / result["candidate_id"] / result["target_file"]
    )
    assert not candidate_path.exists()


def test_optimizer_rejects_unsafe_target_before_runner_or_write(tmp_path: Path) -> None:
    calls = []

    def runner(cmd: List[str], cwd: Path) -> str:
        calls.append((cmd, cwd))
        raise AssertionError("unsafe target reached runner")

    for unsafe_target in ("/home/devuser/AGENTS.md", "../AGENTS.md"):
        with pytest.raises(RuntimeError, match="Candidate optimization failed"):
            run_candidate_optimization_pass(
                doc_type=None,
                target_file=unsafe_target,
                training_findings={
                    "doc_type": "shared",
                    "case_evaluations": {},
                    "findings": [],
                    "holdout_commitment": {"count": 4, "hash": "f" * 64},
                },
                runner_fn=runner,
                proposal_sandbox_root=tmp_path / "proposals",
            )
    assert calls == []
    assert not list((tmp_path / "proposals").rglob("AGENTS.md"))


def test_evaluate_candidate_patch_missing_or_nan_metrics() -> None:
    """Verify evaluate_candidate_patch rejects missing metrics, NaN, Inf, or non-dict inputs."""
    b_tr = _make_full_metrics(0.80)
    b_ho = _make_full_metrics(1.0)
    c_tr = _make_full_metrics(0.90)
    c_ho = _make_full_metrics(1.0)

    # 1. Missing metric key -> REJECTED
    bad_c_tr = dict(c_tr)
    del bad_c_tr["defect_recall"]
    assert evaluate_candidate_patch(b_tr, b_ho, bad_c_tr, c_ho) is False

    # 2. NaN metric value -> REJECTED
    nan_c_ho = dict(c_ho)
    nan_c_ho["pii_containment"] = float("nan")
    assert evaluate_candidate_patch(b_tr, b_ho, c_tr, nan_c_ho) is False

    # 3. Inf metric value -> REJECTED
    inf_b_tr = dict(b_tr)
    inf_b_tr["grounding_accuracy"] = float("inf")
    assert evaluate_candidate_patch(inf_b_tr, b_ho, c_tr, c_ho) is False


def test_evaluate_candidate_patch_safety_and_holdout_regression() -> None:
    """Verify candidate patches are rejected if training safety or holdout metrics regress."""
    b_tr = _make_full_metrics(overall=0.80, grounding=1.0, citation=1.0, recall=0.60, pii=1.0, blind=1.0)
    b_ho = _make_full_metrics(overall=1.0, grounding=1.0, citation=1.0, recall=1.0, pii=1.0, blind=1.0)

    # 1. Overall train improved, but training grounding regressed -> REJECTED
    c_tr_reg_grounding = _make_full_metrics(overall=0.90, grounding=0.80, citation=1.0, recall=0.80, pii=1.0, blind=1.0)
    assert evaluate_candidate_patch(b_tr, b_ho, c_tr_reg_grounding, b_ho) is False

    # 2. Overall train improved, but holdout defect_recall regressed -> REJECTED
    c_tr_good = _make_full_metrics(overall=0.90, grounding=1.0, citation=1.0, recall=0.80, pii=1.0, blind=1.0)
    c_ho_reg_recall = _make_full_metrics(overall=0.95, grounding=1.0, citation=1.0, recall=0.75, pii=1.0, blind=1.0)
    assert evaluate_candidate_patch(b_tr, b_ho, c_tr_good, c_ho_reg_recall) is False

    # 3. Valid overall train improvement + zero regression -> ACCEPTED
    assert evaluate_candidate_patch(b_tr, b_ho, c_tr_good, b_ho) is True


def test_mean_metrics_fails_closed() -> None:
    """Verify _mean_metrics in orchestrator fails closed on empty list or invalid values."""
    from crawler.eval.loop_orchestrator import _mean_metrics

    # 1. Empty list -> raises ValueError
    with pytest.raises(ValueError, match="eval_list is empty"):
        _mean_metrics([])

    # 2. Missing metric -> raises ValueError
    incomplete_evals = [{"grounding_accuracy": 1.0}]
    with pytest.raises(ValueError, match="missing or non-finite metric"):
        _mean_metrics(incomplete_evals)

    # 3. NaN value -> raises ValueError
    nan_evals = [_make_full_metrics(overall=0.8, recall=float("nan"))]
    with pytest.raises(ValueError, match="missing or non-finite metric"):
        _mean_metrics(nan_evals)


def test_no_direct_edits_before_acceptance_and_rejection_byte_identity(tmp_path: Path) -> None:
    """Verify candidate optimization pass does not edit source files, and rejected patch leaves target bytes unchanged."""
    target_rel = "skills/document-agents/passport.md"
    source_file = _REPO_ROOT / target_rel
    original_bytes = source_file.read_bytes()

    def mock_runner(cmd: List[str], cwd: Path) -> str:
        resp = {
            "target_file": target_rel,
            "candidate_content": "## Dirty Content\n- Case ID case_001",
            "rationale": "Test direct edit safety",
        }
        return json.dumps({"type": "assistant.message", "content": json.dumps(resp)})

    findings = {
        "doc_type": "passport",
        "holdout_commitment": {"count": 4, "hash": "c" * 64},
    }

    res = run_candidate_optimization_pass(
        doc_type="passport",
        training_findings=findings,
        runner_fn=mock_runner,
        proposal_sandbox_root=tmp_path / "proposals",
    )

    # Patch is invalid due to case_001
    assert res["is_valid"] is False

    # Source file on disk MUST be byte-identical to before candidate generation
    assert source_file.read_bytes() == original_bytes


def test_orchestrator_candidate_bundle_overrides_and_source_protection(tmp_path: Path) -> None:
    """Verify orchestrator passes per-doc and shared override bundles to candidate workers, and rejected patches leave disk source untouched."""
    from crawler.eval.loop_orchestrator import LoopOrchestrator
    from crawler.eval.public_bundle import build_public_review_bundle

    passport_source = _REPO_ROOT / "skills" / "document-agents" / "passport.md"
    pdf_source = _REPO_ROOT / "skills" / "pdf" / "SKILL.md"
    passport_orig_bytes = passport_source.read_bytes()
    pdf_orig_bytes = pdf_source.read_bytes()

    # Set up mock pipeline structure (Phase 73 layout)
    pipelines_dir = tmp_path / "pipelines"
    p_dir = pipelines_dir / "passport"
    gt_dir = p_dir / "ground_truth"
    pdfs_dir = gt_dir / "pdfs"
    res_dir = p_dir / "research"
    gt_dir.mkdir(parents=True)
    pdfs_dir.mkdir(parents=True)
    res_dir.mkdir(parents=True)

    cases = _build_mock_doc_type_cases("passport")
    sample_pdf = next((_REPO_ROOT / "crawler" / "eval" / "pipelines").rglob("*.pdf"))
    p1_bytes = sample_pdf.read_bytes()
    for c in cases:
        cid = c["opaque_case_id"]
        (pdfs_dir / f"{cid}.pdf").write_bytes(p1_bytes)
        c["pdf_sha256"] = hashlib.sha256(p1_bytes).hexdigest()

    (gt_dir / "ground_truth.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    (res_dir / "research.json").write_text(json.dumps({"triggers": []}), encoding="utf-8")

    passport_orig_text = passport_source.read_text(encoding="utf-8")
    pdf_orig_text = pdf_source.read_text(encoding="utf-8")

    captured_prompts = []

    def mock_runner(cmd: List[str], cwd: Path) -> str:
        prompt_arg = cmd[cmd.index("-p") + 1]
        captured_prompts.append(prompt_arg)

        # Handle Optimizer CLI call
        if "optimizer" in prompt_arg or "PROPOSALS" in prompt_arg or "TARGET FILE:" in prompt_arg:
            if "skills/pdf/SKILL.md" in prompt_arg:
                resp = {
                    "target_file": "skills/pdf/SKILL.md",
                    "candidate_content": pdf_orig_text + "\n- Custom PDF rule\n",
                    "rationale": "Shared PDF test patch",
                }
            else:
                resp = {
                    "target_file": "skills/document-agents/passport.md",
                    "candidate_content": passport_orig_text + "\n- Custom passport rule\n",
                    "rationale": "Per-doc test patch",
                }
            return json.dumps({"type": "assistant.message", "content": json.dumps(resp)})

        # Handle Judge batch call
        if "JUDGE MODEL:" in prompt_arg or "privileged LLM Judge" in prompt_arg:
            match = re.search(r"<worker_reports>\s*(.*?)\s*</worker_reports>", prompt_arg, re.DOTALL)
            if match:
                try:
                    w_reports = json.loads(match.group(1))
                    target_case_ids = list(w_reports.keys())
                except Exception:
                    target_case_ids = [c["opaque_case_id"] for c in cases]
            else:
                target_case_ids = [c["opaque_case_id"] for c in cases]

            case_evals = {}
            findings = []
            for cid in target_case_ids:
                case_evals[cid] = {
                    "grounding_accuracy": 1.0,
                    "citation_exactness": 1.0,
                    "defect_recall": 1.0,
                    "pii_containment": 1.0,
                    "blind_input_compliance": 1.0,
                }
                findings.append({
                    "case_id": cid,
                    "category": "defect_recall",
                    "severity": "minor",
                    "description": f"Missed defect in {cid}",
                })
            judge_resp = {
                "doc_type": "passport",
                "case_evaluations": case_evals,
                "findings": findings,
                "patch_recommendations": [],
                "rationale": "Eval pass",
            }
            return json.dumps({"type": "assistant.message", "content": json.dumps(judge_resp)})

        # Handle Worker task call
        if "<public_review_bundle" in prompt_arg:
            answer = {
                "question": "Canadian Express Entry document review",
                "claims": [{"id": "C1", "text": "Bio page clear", "citations": ["pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#016"], "quote": "biographical data page of a passport"}],
                "basis": ["Passport bio page checked"],
                "abstentions": [],
                "prose": "Review completed.",
            }
            return json.dumps({"type": "assistant.message", "content": json.dumps(answer)})

    orchestrator = LoopOrchestrator(
        pipelines_dir=pipelines_dir,
        iterations_dir=tmp_path / "iterations",
    )

    baseline = orchestrator.run_baseline_pass(runner_fn=mock_runner, require_all_23=False)
    assert baseline["total_doc_types"] == 1

    captured_prompts.clear()

    opt = orchestrator.run_optimization_iterations(baseline, max_iterations=1, runner_fn=mock_runner)

    per_doc_prompts = [p for p in captured_prompts if "Custom passport rule" in p]
    shared_prompts = [p for p in captured_prompts if "Custom PDF rule" in p]

    assert len(per_doc_prompts) > 0, "Per-doc override was not observed in candidate worker prompts"
    assert len(shared_prompts) > 0, "Shared override was not observed in candidate worker prompts"

    doc_expected_bundle = build_public_review_bundle(
        "passport",
        override_skill_content=passport_orig_text + "\n- Custom passport rule\n",
    )
    assert "Custom passport rule" in doc_expected_bundle["content"]
    assert doc_expected_bundle["bundle_hash"] not in per_doc_prompts[0]

    shared_expected_bundle = build_public_review_bundle(
        "passport",
        override_shared_content=pdf_orig_text + "\n- Custom PDF rule\n",
    )
    assert "Custom PDF rule" in shared_expected_bundle["content"]
    assert shared_expected_bundle["bundle_hash"] not in shared_prompts[0]

    proposal_rejections = [
        record
        for record in opt["rejected_patches"]
        if record["doc_type"] in {"passport", "shared"}
    ]
    assert {record["doc_type"] for record in proposal_rejections} == {
        "passport",
        "shared",
    }
    for record in proposal_rejections:
        assert record["decision"] == "rejected"
        assert record["proposal_completed"] is True
        assert record["optimizer_provenance"]["role"] == "optimizer"
        assert record["optimizer_provenance"]["engine"] == "injected-test-runner"
        assert "command" not in record["optimizer_provenance"]
        assert "prompt" not in record["optimizer_provenance"]
        assert "candidate_content" not in record

    # Source files on disk MUST remain untouched if metrics did not improve (scores were flat)
    assert passport_source.read_bytes() == passport_orig_bytes
    assert pdf_source.read_bytes() == pdf_orig_bytes


def test_orchestrator_optimizer_failure_is_blocked_without_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from crawler.eval import loop_orchestrator
    from crawler.eval.loop_orchestrator import LoopOrchestrator

    def fail_before_proposal(**kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("optimizer infrastructure unavailable")

    monkeypatch.setattr(
        loop_orchestrator,
        "run_candidate_optimization_pass",
        fail_before_proposal,
    )
    orchestrator = LoopOrchestrator(
        pipelines_dir=tmp_path / "pipelines",
        iterations_dir=tmp_path / "iterations",
    )
    baseline = {
        "doc_types": {
            "passport": {
                "sealed_findings": {
                    "doc_type": "passport",
                    "case_evaluations": {},
                    "findings": [
                        {
                            "case_id": "train-case",
                            "description": "Missed signature defect",
                        }
                    ],
                    "holdout_commitment": {"count": 4, "hash": "f" * 64},
                },
                "train_evals": [],
                "holdout_evals": [],
            }
        }
    }

    result = orchestrator.run_optimization_iterations(
        baseline,
        max_iterations=1,
    )

    assert result["accepted_patches"] == []
    assert result["rejected_patches"] == []
    assert {record["doc_type"] for record in result["blocked_patches"]} == {
        "passport",
        "shared",
    }
    for record in result["blocked_patches"]:
        assert record["decision"] == "blocked"
        assert record["proposal_completed"] is False
        assert "candidate_id" not in record
        assert "optimizer_provenance" not in record


def test_orchestrator_accepted_candidate_applies_source_after_metrics(tmp_path: Path) -> None:
    """Verify accepted candidate patch updates source file on disk only after metrics pass."""
    from crawler.eval.loop_orchestrator import LoopOrchestrator

    passport_source = _REPO_ROOT / "skills" / "document-agents" / "passport.md"
    passport_orig_bytes = passport_source.read_bytes()
    passport_orig_text = passport_source.read_text(encoding="utf-8")

    # Set up mock pipeline structure (Phase 73 layout)
    pipelines_dir = tmp_path / "pipelines"
    p_dir = pipelines_dir / "passport"
    gt_dir = p_dir / "ground_truth"
    pdfs_dir = gt_dir / "pdfs"
    res_dir = p_dir / "research"
    gt_dir.mkdir(parents=True)
    pdfs_dir.mkdir(parents=True)
    res_dir.mkdir(parents=True)

    cases = _build_mock_doc_type_cases("passport")
    sample_pdf = next((_REPO_ROOT / "crawler" / "eval" / "pipelines").rglob("*.pdf"))
    p1_bytes = sample_pdf.read_bytes()
    for c in cases:
        cid = c["opaque_case_id"]
        (pdfs_dir / f"{cid}.pdf").write_bytes(p1_bytes)
        c["pdf_sha256"] = hashlib.sha256(p1_bytes).hexdigest()

    (gt_dir / "ground_truth.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    (res_dir / "research.json").write_text(json.dumps({"triggers": []}), encoding="utf-8")

    candidate_text = passport_orig_text + "\n- Accepted test candidate rule\n"
    current_run_is_candidate = False
    applied_patches_count_during_worker_eval = None

    def mock_runner(cmd: List[str], cwd: Path) -> str:
        nonlocal current_run_is_candidate, applied_patches_count_during_worker_eval
        prompt_arg = cmd[cmd.index("-p") + 1]

        if "optimizer" in prompt_arg or "PROPOSALS" in prompt_arg or "TARGET FILE:" in prompt_arg:
            if "skills/pdf/SKILL.md" in prompt_arg:
                return json.dumps({
                    "type": "assistant.message",
                    "content": json.dumps({
                        "target_file": "skills/pdf/SKILL.md",
                        "candidate_content": (_REPO_ROOT / "skills" / "pdf" / "SKILL.md").read_text(encoding="utf-8") + "\n- Shared rule\n",
                        "rationale": "Shared PDF test patch",
                    })
                })
            return json.dumps({
                "type": "assistant.message",
                "content": json.dumps({
                    "target_file": "skills/document-agents/passport.md",
                    "candidate_content": candidate_text,
                    "rationale": "Accepted test patch",
                })
            })

        # Judge calls: baseline gets lower score (0.6 recall), candidate gets higher score (1.0 recall)
        if "JUDGE MODEL:" in prompt_arg or "privileged LLM Judge" in prompt_arg:
            match = re.search(r"<worker_reports>\s*(.*?)\s*</worker_reports>", prompt_arg, re.DOTALL)
            if match:
                try:
                    w_reports = json.loads(match.group(1))
                    target_case_ids = list(w_reports.keys())
                except Exception:
                    target_case_ids = [c["opaque_case_id"] for c in cases]
            else:
                target_case_ids = [c["opaque_case_id"] for c in cases]

            score = 1.0 if current_run_is_candidate else 0.6
            case_evals = {
                cid: {
                    "grounding_accuracy": 1.0,
                    "citation_exactness": 1.0,
                    "defect_recall": score,
                    "pii_containment": 1.0,
                    "blind_input_compliance": 1.0,
                }
                for cid in target_case_ids
            }
            findings = [
                {"case_id": cid, "category": "defect_recall", "severity": "minor", "description": "Missed defect"}
                for cid in target_case_ids
            ]
            return json.dumps({
                "type": "assistant.message",
                "content": json.dumps({
                    "doc_type": "passport",
                    "case_evaluations": case_evals,
                    "findings": findings,
                    "patch_recommendations": [],
                    "rationale": "Judge score pass",
                })
            })

        if "<public_review_bundle" in prompt_arg:
            if "- Accepted test candidate rule" in prompt_arg:
                current_run_is_candidate = True
                if applied_patches_count_during_worker_eval is None:
                    applied_patches_count_during_worker_eval = len(orchestrator.accepted_patches)
                    assert passport_source.read_bytes() == passport_orig_bytes, "Source on disk was prematurely modified before candidate metrics pass!"
            else:
                current_run_is_candidate = False

            return json.dumps({
                "type": "assistant.message",
                "content": json.dumps({
                    "question": "Canadian Express Entry document review",
                    "claims": [{"id": "C1", "text": "Bio page clear", "citations": ["pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#016"], "quote": "biographical data page of a passport"}],
                    "basis": ["Passport bio page checked"],
                    "abstentions": [],
                    "prose": "Review completed.",
                })
            })

    orchestrator = LoopOrchestrator(
        pipelines_dir=pipelines_dir,
        iterations_dir=tmp_path / "iterations",
    )

    try:
        baseline = orchestrator.run_baseline_pass(runner_fn=mock_runner, require_all_23=False)
        opt = orchestrator.run_optimization_iterations(baseline, max_iterations=1, runner_fn=mock_runner)

        # After metrics passed and patch accepted, source on disk MUST be updated
        assert len(orchestrator.accepted_patches) > 0
        assert passport_source.read_text(encoding="utf-8") == candidate_text
        passport_record = next(
            record
            for record in opt["accepted_patches"]
            if record["doc_type"] == "passport"
        )
        assert passport_record["decision"] == "accepted"
        assert passport_record["proposal_completed"] is True
        assert (
            passport_record["optimizer_provenance"]["engine"]
            == "injected-test-runner"
        )
        assert "command" not in passport_record["optimizer_provenance"]
        assert "prompt" not in passport_record["optimizer_provenance"]
        assert "candidate_content" not in passport_record
    finally:
        # Restore original source content
        passport_source.write_bytes(passport_orig_bytes)


@pytest.mark.parametrize(
    ("scope", "target_file"),
    [
        ("document", "skills/document-agents/passport.md"),
        ("shared", "skills/pdf/SKILL.md"),
    ],
)
def test_orchestrator_validates_publishable_record_before_source_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    target_file: str,
) -> None:
    from crawler.eval import loop_orchestrator
    from crawler.eval.loop_orchestrator import LoopOrchestrator

    source = tmp_path / target_file
    source.parent.mkdir(parents=True, exist_ok=True)
    original = b"# Original trusted source\n"
    source.write_bytes(original)
    candidate_content = original.decode() + "- Proposed change\n"

    candidate_result = _valid_optimizer_candidate_result()
    candidate_result.update(
        {
            "doc_type": "passport" if scope == "document" else None,
            "target_file": target_file,
            "candidate_content": candidate_content,
            "is_valid": True,
            "rejection_reasons": [],
        }
    )
    candidate_result["_provenance"]["candidate_content_hash"] = hashlib.sha256(
        candidate_content.encode("utf-8")
    ).hexdigest()
    candidate_result["_provenance"]["provenance_digest"] = "0" * 64

    cases = _build_mock_doc_type_cases("passport")
    candidate_scores = {
        case["opaque_case_id"]: {
            "grounding_accuracy": 1.0,
            "citation_exactness": 1.0,
            "defect_recall": 1.0,
            "pii_containment": 1.0,
            "blind_input_compliance": 1.0,
        }
        for case in cases
    }
    baseline_scores = [
        {
            "grounding_accuracy": 0.5,
            "citation_exactness": 0.5,
            "defect_recall": 0.5,
            "pii_containment": 0.5,
            "blind_input_compliance": 0.5,
        }
    ]
    baseline = {
        "doc_types": {
            "passport": {
                "sealed_findings": {
                    "doc_type": "passport",
                    "case_evaluations": {},
                    "findings": [
                        {
                            "case_id": cases[0]["opaque_case_id"],
                            "description": "Training finding",
                        }
                    ],
                    "holdout_commitment": {"count": 4, "hash": "f" * 64},
                },
                "train_evals": baseline_scores,
                "holdout_evals": baseline_scores,
            }
        }
    }

    def optimizer(**kwargs: Any) -> Dict[str, Any]:
        is_shared = kwargs.get("doc_type") is None
        if is_shared == (scope == "shared"):
            return deepcopy(candidate_result)
        raise RuntimeError("skip other optimizer scope")

    monkeypatch.setattr(loop_orchestrator, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        loop_orchestrator,
        "run_candidate_optimization_pass",
        optimizer,
    )
    monkeypatch.setattr(
        loop_orchestrator,
        "build_public_review_bundle",
        lambda **kwargs: {},
    )

    orchestrator = LoopOrchestrator(
        pipelines_dir=tmp_path / "pipelines",
        iterations_dir=tmp_path / "iterations",
    )
    monkeypatch.setattr(orchestrator, "_load_doc_type_cases", lambda *args, **kwargs: cases)
    monkeypatch.setattr(
        orchestrator,
        "run_doctype_eval_pass",
        lambda **kwargs: ({}, {"case_evaluations": candidate_scores}),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_baseline_workers_pass",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(
        orchestrator,
        "run_baseline_judges_pass",
        lambda **kwargs: {
            "doc_types": {
                "passport": {
                    "judge_batch": {"case_evaluations": candidate_scores}
                }
            }
        },
    )

    try:
        result = orchestrator.run_optimization_iterations(
            baseline,
            max_iterations=1,
        )
    finally:
        assert source.read_bytes() == original

    assert not [
        record
        for record in result["accepted_patches"]
        if record["doc_type"] == scope
        or (scope == "document" and record["doc_type"] == "passport")
    ]
    assert any(
        record["doc_type"] == scope
        or (scope == "document" and record["doc_type"] == "passport")
        for record in result["blocked_patches"]
    )
