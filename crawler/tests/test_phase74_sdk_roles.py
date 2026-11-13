"""Unit and contract tests for Phase 74 SDK roles (Worker, Judge, Optimizer).

Verifies that:
- Worker requests use Gemini 3.6 Flash long context, exact attachment structure, and retries only TransientAgentError.
- Judge requests use Claude Opus 4.8 xhigh long context, exact ordered attachments, strict Pydantic validation, and 100% case coverage.
- Optimizer requests use Gemini 3.6 Flash long context, sealed training findings, no attachments, strict proposal schema, and sandbox writing.
- Injected runtime provenance is always non-live and clearly labeled.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from crawler.eval.agent_runtime import (
    AgentProvenance,
    AgentRequest,
    AgentResult,
    AgentRuntime,
    AgentRuntimeError,
    BlobAttachment,
    TransientAgentError,
)
from crawler.eval.genuine_optimizer import run_candidate_optimization_pass_async
from crawler.eval.pipeline_judge import (
    JudgeExecutionError,
    run_batched_document_judge_async,
)
from crawler.eval.pipeline_worker import (
    _build_worker_prompt,
    run_blind_worker_task,
    run_blind_worker_task_async,
)
from crawler.eval.public_bundle import build_public_review_bundle
from crawler.synthetic.staging import generate_opaque_32hex_id
from crawler.tests.phase74_provenance import build_worker_provenance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PDF = next((_REPO_ROOT / "crawler" / "eval" / "pipelines").rglob("*.pdf"))
VALID_PDF_BYTES = _SAMPLE_PDF.read_bytes()


def _judge_worker_provenance(pdf_bytes: bytes) -> dict[str, Any]:
    bundle = build_public_review_bundle("passport")
    prompt = _build_worker_prompt(doc_type="passport", public_bundle=bundle)
    return build_worker_provenance(
        hashlib.sha256(pdf_bytes).hexdigest(),
        prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        bundle_hash=bundle["bundle_hash"],
    )


class MockSdkRuntime(AgentRuntime):
    """Mock AgentRuntime capturing AgentRequest and returning configured AgentResult or raising error."""

    def __init__(
        self,
        response_content: str | None = None,
        raise_error: Exception | None = None,
        sequential_responses: List[str | Exception] | None = None,
        provenance_overrides: Dict[str, Any] | None = None,
    ):
        self.response_content = response_content
        self.raise_error = raise_error
        self.sequential_responses = list(sequential_responses or [])
        self.provenance_overrides = provenance_overrides or {}
        self.requests: List[AgentRequest] = []
        self.call_count = 0

    async def run(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        self.call_count += 1

        if self.sequential_responses:
            item = self.sequential_responses.pop(0)
            if isinstance(item, Exception):
                raise item
            content = item
        elif self.raise_error:
            raise self.raise_error
        else:
            content = self.response_content or ""

        prompt_hash = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()
        output_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        provenance = AgentProvenance(
            engine="injected-test-runner",
            sdk_version="1.0.8",
            runtime_protocol_version="1.0",
            role=request.role,
            model=request.model,
            effort=request.reasoning_effort,
            context_tier=request.context_tier,
            session_id=f"sdk_session_{self.call_count}",
            prompt_hash=prompt_hash,
            attachment_hashes=[
                hashlib.sha256(att.data).hexdigest() for att in request.attachments
            ],
            output_hash=output_hash,
            started_at="2026-07-25T00:00:00Z",
            completed_at="2026-07-25T00:00:01Z",
            duration_seconds=1.0,
            terminal_event="assistant.message",
            is_live=False,
        )
        if self.provenance_overrides:
            provenance = replace(provenance, **self.provenance_overrides)
        return AgentResult(content=content, provenance=provenance)


class TestPhase74SdkRoles(unittest.IsolatedAsyncioTestCase):
    """Test suite for Worker, Judge, and Optimizer SDK role migration."""

    async def test_worker_sdk_request_and_provenance(self) -> None:
        """Worker task sends exact AgentRequest and records copilot-sdk provenance."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)

            opaque_id = generate_opaque_32hex_id()
            pdf_path = pipeline_dir / f"{opaque_id}.pdf"
            pdf_path.write_bytes(VALID_PDF_BYTES)

            valid_answer = {
                "question": "Review the supplied passport document for compliance.",
                "claims": [
                    {
                        "id": "CLAIM-01",
                        "text": "Passport biographical data page is valid.",
                        "citations": [
                            "pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#016"
                        ],
                        "quote": "biographical data page of a passport or travel document",
                    }
                ],
                "basis": ["Passport holder name analyzed."],
                "abstentions": [],
                "prose": "Document meets requirements.",
            }

            mock_runtime = MockSdkRuntime(response_content=json.dumps(valid_answer))

            result = await run_blind_worker_task_async(
                opaque_case_id=opaque_id,
                doc_type="passport",
                pipeline_root=pipeline_root,
                runtime=mock_runtime,
            )

            self.assertEqual(mock_runtime.call_count, 1)
            req = mock_runtime.requests[0]
            self.assertEqual(req.role, "worker")
            self.assertEqual(req.model, "gemini-3.6-flash")
            self.assertEqual(req.context_tier, "long_context")
            self.assertEqual(req.timeout_seconds, 600)

            self.assertEqual(len(req.attachments), 1)
            att = req.attachments[0]
            self.assertEqual(att.mime_type, "application/pdf")
            self.assertEqual(att.display_name, "document.pdf")
            self.assertEqual(att.data, VALID_PDF_BYTES)

            model_visible_input = req.prompt + "\n" + att.display_name
            internal_values = (
                opaque_id,
                f"{opaque_id}.pdf",
                str(pdf_path),
                hashlib.sha256(VALID_PDF_BYTES).hexdigest(),
                result["_provenance"]["bundle_hash"],
            )
            for internal_value in internal_values:
                self.assertNotIn(internal_value, model_visible_input)
            self.assertNotIn("OPAQUE CASE ID", req.prompt)
            self.assertNotIn("sha256=", req.prompt)

            # Deterministic pipeline identity is attached only after the strict
            # model AnswerObject has been parsed and validated.
            self.assertNotIn(opaque_id, mock_runtime.response_content)
            self.assertEqual(result["case_id"], opaque_id)
            self.assertEqual(result["doc_type"], "passport")
            self.assertEqual(result["_provenance"]["engine"], "injected-test-runner")
            self.assertFalse(result["_provenance"]["is_live"])
            self.assertEqual(result["_provenance"]["role"], "worker")
            self.assertEqual(
                result["_provenance"]["attachment_hashes"],
                [hashlib.sha256(VALID_PDF_BYTES).hexdigest()],
            )
            self.assertEqual(result["_provenance"]["terminal_event"], "assistant.message")

    async def test_worker_sdk_retries_transient_error_only(self) -> None:
        """Worker retries TransientAgentError up to max attempts, but fails immediately on deterministic errors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)

            opaque_id = generate_opaque_32hex_id()
            pdf_path = pipeline_dir / f"{opaque_id}.pdf"
            pdf_path.write_bytes(VALID_PDF_BYTES)

            valid_answer = {
                "question": "Review passport.",
                "claims": [
                    {
                        "id": "CLAIM-01",
                        "text": "Passport page valid.",
                        "citations": [
                            "pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#016"
                        ],
                        "quote": "biographical data page of a passport or travel document",
                    }
                ],
                "basis": ["Data analyzed."],
                "abstentions": [],
                "prose": "Valid.",
            }

            # 1. Transient error recovered on 2nd attempt
            mock_runtime = MockSdkRuntime(
                sequential_responses=[
                    TransientAgentError("Network timeout"),
                    json.dumps(valid_answer),
                ]
            )

            res = await run_blind_worker_task_async(
                opaque_case_id=opaque_id,
                doc_type="passport",
                pipeline_root=pipeline_root,
                runtime=mock_runtime,
            )
            self.assertEqual(mock_runtime.call_count, 2)
            self.assertEqual(res["case_id"], opaque_id)

            # 2. Deterministic JSON error -> NO retry
            invalid_json_runtime = MockSdkRuntime(
                sequential_responses=[
                    "Not valid JSON object",
                    json.dumps(valid_answer),
                ]
            )

            with self.assertRaises(Exception):
                await run_blind_worker_task_async(
                    opaque_case_id=opaque_id,
                    doc_type="passport",
                    pipeline_root=pipeline_root,
                    runtime=invalid_json_runtime,
                )
            self.assertEqual(invalid_json_runtime.call_count, 1)

    async def test_judge_sdk_request_and_validation(self) -> None:
        """Judge sends exact Opus 4.8 xhigh AgentRequest and performs strict schema and coverage validation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            p1_bytes = b"%PDF-1.4 test 1"
            p2_bytes = b"%PDF-1.4 test 2"
            pdf1 = tmp_path / "c1.pdf"
            pdf2 = tmp_path / "c2.pdf"
            pdf1.write_bytes(p1_bytes)
            pdf2.write_bytes(p2_bytes)

            worker_reports = {
                "c1": {
                    "question": "q",
                    "claims": [],
                    "basis": [],
                    "abstentions": [],
                    "prose": "p",
                    "case_id": "c1",
                    "doc_type": "passport",
                    "_provenance": _judge_worker_provenance(p1_bytes),
                },
                "c2": {
                    "question": "q",
                    "claims": [],
                    "basis": [],
                    "abstentions": [],
                    "prose": "p",
                    "case_id": "c2",
                    "doc_type": "passport",
                    "_provenance": _judge_worker_provenance(p2_bytes),
                },
            }

            judge_resp = {
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
                "rationale": "Perfect batch",
            }

            mock_runtime = MockSdkRuntime(response_content=json.dumps(judge_resp))

            res = await run_batched_document_judge_async(
                doc_type="passport",
                worker_reports=worker_reports,
                pdf_paths=[pdf1, pdf2],
                research_json={},
                ground_truth_specs={"c1": {}, "c2": {}},
                runtime=mock_runtime,
            )

            self.assertEqual(mock_runtime.call_count, 1)
            req = mock_runtime.requests[0]
            self.assertEqual(req.role, "judge")
            self.assertEqual(req.model, "claude-opus-4.8")
            self.assertEqual(req.reasoning_effort, "xhigh")
            self.assertEqual(req.context_tier, "long_context")
            self.assertEqual(req.timeout_seconds, 900)

            # Ordered PDF attachments matching sorted case IDs (c1, c2)
            self.assertEqual(len(req.attachments), 2)
            self.assertEqual(req.attachments[0].display_name, "c1.pdf")
            self.assertEqual(req.attachments[1].display_name, "c2.pdf")

            self.assertEqual(res["_provenance"]["engine"], "injected-test-runner")
            self.assertFalse(res["_provenance"]["is_live"])
            self.assertEqual(
                res["_provenance"]["pdf_hashes"],
                [
                    hashlib.sha256(p1_bytes).hexdigest(),
                    hashlib.sha256(p2_bytes).hexdigest(),
                ],
            )
            self.assertEqual(res["_provenance"]["case_ids"], ["c1", "c2"])
            self.assertEqual(len(res["_provenance"]["worker_report_hashes"]), 2)
            self.assertEqual(len(res["_provenance"]["input_manifest_hash"]), 64)
            self.assertEqual(len(res["_provenance"]["prompt_contract_hash"]), 64)

    async def test_judge_sdk_coverage_mismatch_fails_immediately(self) -> None:
        """Judge coverage or schema failure does not retry and fails closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            p1_bytes = b"%PDF-1.4 test 1"
            pdf1 = tmp_path / "c1.pdf"
            pdf1.write_bytes(p1_bytes)

            worker_reports = {
                "c1": {
                    "question": "q",
                    "claims": [],
                    "basis": [],
                    "abstentions": [],
                    "prose": "p",
                    "case_id": "c1",
                    "doc_type": "passport",
                    "_provenance": _judge_worker_provenance(p1_bytes),
                },
            }

            # Response missing c1
            bad_coverage_resp = {
                "doc_type": "passport",
                "case_evaluations": {},
                "findings": [],
                "patch_recommendations": [],
                "rationale": "Missing cases",
            }

            mock_runtime = MockSdkRuntime(
                response_content=json.dumps(bad_coverage_resp)
            )

            with self.assertRaises(JudgeExecutionError):
                await run_batched_document_judge_async(
                    doc_type="passport",
                    worker_reports=worker_reports,
                    pdf_paths=[pdf1],
                    research_json={},
                    ground_truth_specs={"c1": {}},
                    runtime=mock_runtime,
                )

            # Must fail on attempt 1 with zero retries
            self.assertEqual(mock_runtime.call_count, 1)

    async def test_judge_sdk_rejects_markdown_fenced_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_bytes = b"%PDF-1.4 strict judge"
            pdf = tmp_path / "c1.pdf"
            pdf.write_bytes(pdf_bytes)
            batch = {
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
                "rationale": "Pass",
            }
            runtime = MockSdkRuntime(
                response_content=f"```json\n{json.dumps(batch)}\n```"
            )
            worker_reports = {
                "c1": {
                    "question": "q",
                    "claims": [],
                    "basis": [],
                    "abstentions": [],
                    "prose": "p",
                    "case_id": "c1",
                    "doc_type": "passport",
                    "_provenance": _judge_worker_provenance(pdf_bytes),
                }
            }

            with self.assertRaisesRegex(
                JudgeExecutionError,
                "raw JSON object",
            ):
                await run_batched_document_judge_async(
                    doc_type="passport",
                    worker_reports=worker_reports,
                    pdf_paths=[pdf],
                    research_json={},
                    ground_truth_specs={"c1": {}},
                    runtime=runtime,
                )
            self.assertEqual(runtime.call_count, 1)

    async def test_optimizer_sdk_request_and_sandbox(self) -> None:
        """Optimizer sends AgentRequest with Gemini 3.6 Flash long context, no attachments, and writes candidate into sandbox."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            target_rel = "skills/document-agents/passport.md"
            source_content = (_REPO_ROOT / target_rel).read_text(encoding="utf-8")
            candidate_content = source_content + "\n- New signature verification check\n"

            resp = {
                "target_file": target_rel,
                "candidate_content": candidate_content,
                "rationale": "Fix signature check",
            }

            mock_runtime = MockSdkRuntime(response_content=json.dumps(resp))

            training_findings = {
                "doc_type": "passport",
                "case_evaluations": {"train_c1": {"defect_recall": 0.5}},
                "findings": [
                    {"case_id": "train_c1", "description": "Missed signature"}
                ],
                "holdout_commitment": {"count": 4, "hash": "f" * 64},
            }

            res = await run_candidate_optimization_pass_async(
                doc_type="passport",
                training_findings=training_findings,
                proposal_sandbox_root=tmp_path / "proposals",
                runtime=mock_runtime,
            )

            self.assertEqual(mock_runtime.call_count, 1)
            req = mock_runtime.requests[0]
            self.assertEqual(req.role, "optimizer")
            self.assertEqual(req.model, "gemini-3.6-flash")
            self.assertEqual(req.context_tier, "long_context")
            self.assertEqual(req.attachments, [])

            # Only model-facing training data is present; even the commitment stays local.
            self.assertNotIn("holdout", req.prompt.lower())
            self.assertNotIn("f" * 64, req.prompt)
            self.assertNotIn("holdout_evaluations", req.prompt)
            self.assertIn("first output character MUST be", req.prompt)
            self.assertIn("Do NOT wrap the object in Markdown", req.prompt)

            # Candidate file written into proposal sandbox
            cand_path = (
                tmp_path / "proposals" / res["candidate_id"] / res["target_file"]
            )
            self.assertTrue(cand_path.is_file())
            self.assertEqual(cand_path.read_text(encoding="utf-8"), candidate_content)

            self.assertEqual(res["_provenance"]["engine"], "injected-test-runner")
            self.assertFalse(res["_provenance"]["is_live"])

    async def test_runtime_provenance_must_match_exact_request_and_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)
            opaque_id = generate_opaque_32hex_id()
            (pipeline_dir / f"{opaque_id}.pdf").write_bytes(VALID_PDF_BYTES)
            valid_answer = {
                "question": "Review the supplied passport.",
                "claims": [],
                "basis": [],
                "abstentions": [],
                "prose": "No claims made.",
            }

            mismatches = {
                "engine": "copilot-sdk",
                "is_live": True,
                "role": "judge",
                "model": "wrong-model",
                "effort": "high",
                "context_tier": "default",
                "prompt_hash": "0" * 64,
                "attachment_hashes": [],
                "output_hash": "1" * 64,
                "terminal_event": "session.error",
                "sdk_version": "",
                "runtime_protocol_version": "",
                "session_id": "unknown",
                "completed_at": "2026-07-24T23:59:59Z",
                "duration_seconds": -1.0,
            }
            for field, bad_value in mismatches.items():
                runtime = MockSdkRuntime(
                    response_content=json.dumps(valid_answer),
                    provenance_overrides={field: bad_value},
                )
                with self.subTest(field=field), self.assertRaises(
                    AgentRuntimeError, msg=f"accepted mismatched provenance field {field}"
                ):
                    await run_blind_worker_task_async(
                        opaque_case_id=opaque_id,
                        doc_type="passport",
                        pipeline_root=pipeline_root,
                        runtime=runtime,
                    )

    async def test_injected_runtime_cannot_claim_live_sdk_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)
            opaque_id = generate_opaque_32hex_id()
            (pipeline_dir / f"{opaque_id}.pdf").write_bytes(VALID_PDF_BYTES)
            answer = {
                "question": "Review the supplied passport.",
                "claims": [],
                "basis": [],
                "abstentions": [],
                "prose": "No claims made.",
            }
            runtime = MockSdkRuntime(
                response_content=json.dumps(answer),
                provenance_overrides={"engine": "copilot-sdk", "is_live": True},
            )

            with self.assertRaises(AgentRuntimeError):
                await run_blind_worker_task_async(
                    opaque_case_id=opaque_id,
                    doc_type="passport",
                    pipeline_root=pipeline_root,
                    runtime=runtime,
                )

    async def test_judge_rejects_case_key_mismatch_before_runtime_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf = tmp_path / "c1.pdf"
            pdf.write_bytes(b"%PDF-1.4 test")
            runtime = MockSdkRuntime(response_content="{}")
            worker_reports = {
                "c1": {
                    "case_id": "c1",
                    "doc_type": "passport",
                    "_provenance": _judge_worker_provenance(pdf.read_bytes()),
                }
            }

            with self.assertRaises(JudgeExecutionError, msg="ground-truth key mismatch accepted"):
                await run_batched_document_judge_async(
                    doc_type="passport",
                    worker_reports=worker_reports,
                    pdf_paths=[pdf],
                    research_json={},
                    ground_truth_specs={"different-case": {}},
                    runtime=runtime,
                )
            self.assertEqual(runtime.call_count, 0)

            with self.assertRaises(
                JudgeExecutionError,
                msg="ground-truth payload case ID mismatch accepted",
            ):
                await run_batched_document_judge_async(
                    doc_type="passport",
                    worker_reports=worker_reports,
                    pdf_paths=[pdf],
                    research_json={},
                    ground_truth_specs={
                        "c1": {"opaque_case_id": "different-case"}
                    },
                    runtime=runtime,
                )
            self.assertEqual(runtime.call_count, 0)

    async def test_optimizer_uses_allowlisted_training_schema_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = "skills/document-agents/passport.md"
            source = (_REPO_ROOT / target).read_text(encoding="utf-8")
            runtime = MockSdkRuntime(
                response_content=json.dumps(
                    {
                        "target_file": target,
                        "candidate_content": source,
                        "rationale": "No-op",
                    }
                )
            )
            await run_candidate_optimization_pass_async(
                doc_type="passport",
                training_findings={
                    "doc_type": "passport",
                    "case_evaluations": {"train-c1": {"defect_recall": 0.5, "secret_label": "leak"}},
                    "findings": [
                        {
                            "case_id": "train-c1",
                            "category": "defect_recall",
                            "severity": "major",
                            "description": "Training miss",
                            "private_note": "leak",
                        },
                        {
                            "case_id": "sealed-c1",
                            "description": "Holdout case failed without naming its split",
                        },
                        {
                            "case_id": "train-c1",
                            "description": "Validation split score was zero for a sealed evaluation",
                        },
                    ],
                    "patch_recommendations": [
                        {"suggested_patch": "Recommendation derived from sealed evaluation"}
                    ],
                    "rationale": "Holdout score and label disclose the sealed result",
                    "arbitrary_precommitted_payload": {"holdout_label": "defective"},
                    "holdout_commitment": {"count": 4, "hash": "f" * 64},
                },
                proposal_sandbox_root=Path(tmp_dir) / "proposals",
                runtime=runtime,
            )

            prompt = runtime.requests[0].prompt
            self.assertIn("Training miss", prompt)
            for leaked in (
                "secret_label",
                "private_note",
                "sealed-c1",
                "Recommendation derived",
                "Holdout score",
                "arbitrary_precommitted_payload",
                "holdout_label",
                "Validation split score",
            ):
                self.assertNotIn(leaked, prompt)

    async def test_optimizer_rejects_empty_holdout_commitment_before_call(
        self,
    ) -> None:
        target = "skills/pdf/SKILL.md"
        source = (_REPO_ROOT / target).read_text(encoding="utf-8")
        runtime = MockSdkRuntime(
            response_content=json.dumps(
                {
                    "target_file": target,
                    "candidate_content": source,
                    "rationale": "No-op",
                }
            )
        )

        with self.assertRaises(ValueError):
            await run_candidate_optimization_pass_async(
                doc_type=None,
                target_file=target,
                training_findings={
                    "doc_type": "shared",
                    "case_evaluations": {},
                    "findings": [],
                    "holdout_commitment": {"count": 0, "hash": "f" * 64},
                },
                runtime=runtime,
            )
        self.assertEqual(runtime.call_count, 0)

    async def test_sync_wrapper_rejects_running_event_loop(self) -> None:
        with self.assertRaises(RuntimeError, msg="sync wrapper crossed event-loop boundary") as ctx:
            run_blind_worker_task("case", "passport")
        self.assertIn("run_blind_worker_task_async", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
