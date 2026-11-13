"""Privileged Batched LLM Judge powered by Claude Opus 4.8 (xhigh effort, long_context).

Executes exactly one privileged GitHub Copilot CLI session per document type per evaluation pass,
batching all Worker review reports and PDF attachments alongside Phase 72 research and Phase 73 ground truth specs.

Enforces strict Pydantic schema validation (JudgeEvaluationBatch), 100% case coverage, zero deterministic score fabrication,
and fail-closed error handling per JUDGE_IMPROVE-01 and D-08..D-11.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crawler.eval.agent_runtime import (
    AgentLifecycleError,
    AgentRequest,
    AgentRuntime,
    AgentRuntimeError,
    AgentTimeoutError,
    BlobAttachment,
    ResponseValidationIssue,
    ResponseValidationPolicy,
    TransientAgentError,
    canonical_provenance_digest,
    run_async,
    validate_agent_result,
    validate_persisted_agent_provenance,
)
from crawler.eval.copilot_sdk_runtime import CopilotSdkRuntime
from crawler.eval.pipeline_worker import _WORKER_PROVENANCE_EXTRA_FIELDS
from crawler.eval.pipeline_worker import build_worker_input_manifest
from crawler.eval.public_bundle import build_public_review_bundle

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_JUDGE_STAGE_ROOT = _REPO_ROOT / "reports" / "judge_staging"
_JUDGE_MODEL = "claude-opus-4.8"
_JUDGE_EFFORT = "xhigh"
_CONTEXT_TIER = "long_context"
_LLM_TIMEOUT_SECONDS = 900
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

logger = logging.getLogger(__name__)
_JUDGE_PROMPT_CONTRACT = {
    "version": "phase74-judge-v3",
    "role": "judge",
    "output_schema": {
        "top_level": [
            "doc_type",
            "case_evaluations",
            "findings",
            "patch_recommendations",
            "rationale",
        ],
        "extra_fields": "forbid",
        "case_coverage": "exact",
    },
    "constraints": [
        "no_tools",
        "single_raw_json_object",
        "evaluate_all_cases",
        "scores_finite_and_bounded",
        "blindness_scored_from_exact_worker_inputs",
    ],
}


class JudgeExecutionError(RuntimeError):
    """Raised when deterministic Judge output fails schema or coverage checks."""


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CaseScore(StrictBaseModel):
    grounding_accuracy: float = Field(ge=0.0, le=1.0)
    citation_exactness: float = Field(ge=0.0, le=1.0)
    defect_recall: float = Field(ge=0.0, le=1.0)
    pii_containment: float = Field(ge=0.0, le=1.0)
    blind_input_compliance: float = Field(ge=0.0, le=1.0)

    @field_validator(
        "grounding_accuracy",
        "citation_exactness",
        "defect_recall",
        "pii_containment",
        "blind_input_compliance",
        mode="before",
    )
    @classmethod
    def check_raw_json_number(cls, v: Any) -> int | float:
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError("Score must be a finite bounded float between 0.0 and 1.0")
        return v


class CaseFinding(StrictBaseModel):
    case_id: str
    category: Literal["grounding", "citation", "defect_recall", "pii", "blind_input"]
    severity: Literal["critical", "major", "minor"]
    description: str


class PatchRecommendation(StrictBaseModel):
    target_file: str
    suggested_patch: str

    @field_validator("target_file")
    @classmethod
    def validate_target_file(cls, v: str) -> str:
        if v in ("AGENTS.md", "skills/pdf/SKILL.md") or v.startswith("skills/document-agents/"):
            return v
        raise ValueError(f"Disallowed patch target file: '{v}'")


class JudgeEvaluationBatch(StrictBaseModel):
    doc_type: str
    case_evaluations: Dict[str, CaseScore]
    findings: List[CaseFinding]
    patch_recommendations: List[PatchRecommendation]
    rationale: str


def build_judge_response_validation_policy(
    *,
    doc_type: str,
    allowed_case_ids: List[str],
) -> ResponseValidationPolicy:
    """Build a structural-only same-session Judge correction policy."""
    exact_case_ids = tuple(sorted(allowed_case_ids))
    expected_ids = set(exact_case_ids)

    def validate(content: str) -> ResponseValidationIssue | None:
        try:
            batch = JudgeEvaluationBatch.model_validate_json(content)
        except Exception:
            return ResponseValidationIssue(("schema_invalid",))
        codes: list[str] = []
        if batch.doc_type != doc_type:
            codes.append("doc_type_mismatch")
        if set(batch.case_evaluations) != expected_ids:
            codes.append("case_coverage_mismatch")
        if any(finding.case_id not in expected_ids for finding in batch.findings):
            codes.append("finding_case_id_invalid")
        return (
            ResponseValidationIssue(tuple(codes))
            if codes
            else None
        )

    def build_prompt(issue: ResponseValidationIssue) -> str:
        summary = ",".join(issue.codes)
        allowed_json = json.dumps(
            list(exact_case_ids),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return (
            "The previous JSON failed structural validation: "
            f"{summary}. Allowed doc_type: {doc_type}. Allowed case IDs "
            f"(exact set): {allowed_json}. Return the same assessment again "
            "as one raw strict JSON object using exactly that doc_type and "
            "case ID set. Do not add new evidence or semantic content. The "
            "first character must be { and the last character }. Do not use "
            "a fence, preface, explanation, or trailing prose."
        )

    return ResponseValidationPolicy(
        correction_kind="judge_structure",
        validate=validate,
        build_correction_prompt=build_prompt,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def build_judge_input_manifest(
    *,
    doc_type: str,
    case_ids: List[str],
    pdf_hashes_by_case: Dict[str, str],
    worker_reports: Dict[str, Dict[str, Any]],
    worker_input_manifests: Dict[str, Dict[str, Any]],
    research_json: Dict[str, Any],
    ground_truth_specs: Dict[str, Dict[str, Any]],
) -> tuple[Dict[str, Any], str]:
    """Build the canonical complete Judge input manifest and its SHA-256 hash."""
    ordered_case_ids = sorted(case_ids)
    model_config = {
        "role": "judge",
        "model": _JUDGE_MODEL,
        "effort": _JUDGE_EFFORT,
        "context_tier": _CONTEXT_TIER,
        "timeout_seconds": _LLM_TIMEOUT_SECONDS,
    }
    manifest = {
        "schema_version": "judge-input-manifest-v2",
        "doc_type": doc_type,
        "case_ids": ordered_case_ids,
        "pdf_hashes": [
            pdf_hashes_by_case[case_id] for case_id in ordered_case_ids
        ],
        "worker_report_hashes": [
            _canonical_json_hash(worker_reports[case_id])
            for case_id in ordered_case_ids
        ],
        "worker_input_manifest_hashes": [
            _canonical_json_hash(worker_input_manifests[case_id])
            for case_id in ordered_case_ids
        ],
        "public_bundle_hashes": [
            worker_input_manifests[case_id]["public_bundle_hash"]
            for case_id in ordered_case_ids
        ],
        "worker_prompt_hashes": [
            worker_input_manifests[case_id]["worker_prompt_hash"]
            for case_id in ordered_case_ids
        ],
        "research_hash": _canonical_json_hash(research_json),
        "ground_truth_hash": _canonical_json_hash(ground_truth_specs),
        "prompt_contract_hash": _canonical_json_hash(_JUDGE_PROMPT_CONTRACT),
        "model_config": model_config,
    }
    return manifest, _canonical_json_hash(manifest)


def _build_judge_prompt(
    *,
    doc_type: str,
    case_ids: List[str],
    worker_reports: Dict[str, Dict[str, Any]],
    worker_input_manifests: Dict[str, Dict[str, Any]],
    research_json: Dict[str, Any],
    ground_truth_specs: Dict[str, Dict[str, Any]],
    input_manifest_hash: str,
    prompt_contract_hash: str,
) -> str:
    """Build the deterministic Judge prompt bound into runtime provenance."""
    safe_worker_reports = json.dumps(
        worker_reports, indent=2, ensure_ascii=False
    ).replace("</worker_reports>", "&lt;/worker_reports&gt;")
    safe_worker_inputs = json.dumps(
        worker_input_manifests, indent=2, ensure_ascii=False
    ).replace("</worker_input_manifests>", "&lt;/worker_input_manifests&gt;")
    safe_research = json.dumps(
        research_json, indent=2, ensure_ascii=False
    ).replace("</privileged_research>", "&lt;/privileged_research&gt;")
    safe_gt = json.dumps(
        ground_truth_specs, indent=2, ensure_ascii=False
    ).replace(
        "</privileged_ground_truth>", "&lt;/privileged_ground_truth&gt;"
    )
    ordered_case_ids = sorted(case_ids)
    return f"""You are the privileged LLM Judge evaluating blind Worker reports for Canadian Express Entry document review.

DOCUMENT TYPE: {doc_type}
JUDGE MODEL: claude-opus-4.8 (--effort xhigh, --context long_context)
WORKER MODEL EVALUATED: gemini-3.6-flash (long_context)
INPUT MANIFEST SHA256: {input_manifest_hash}
PROMPT CONTRACT SHA256: {prompt_contract_hash}

You are evaluating {len(worker_reports)} test cases for this document type.

<worker_reports>
{safe_worker_reports}
</worker_reports>

<worker_input_manifests>
{safe_worker_inputs}
</worker_input_manifests>

<privileged_research>
{safe_research}
</privileged_research>

<privileged_ground_truth>
{safe_gt}
</privileged_ground_truth>

CRITICAL INSTRUCTIONS:
- NO TOOLS: You have NO tool privileges in this session. Do NOT attempt to run bash commands, list directory contents, or execute tools. All required evidence (exact Worker prompts and public bundles, Worker reports, research findings, ground truth specs) is fully provided in the prompt context above and PDF attachments.
- DO NOT WRITE PROSE: Do NOT write intro thoughts, tool attempts, analysis steps, markdown headers, or prose commentary before or after your JSON output.
- WORKER MODEL: Workers operate with Gemini 3.6 Flash. This is expected; do not flag model mismatches for Workers.
- OUTPUT FORMAT: Return ONLY a single raw JSON object matching the required schema below.

Evaluate each Worker report against the attached PDF documents, research findings, and ground truth specs.
Score each of the {len(worker_reports)} cases on:
- grounding_accuracy: claims supported with no invented facts [0.0 to 1.0]
- citation_exactness: citations resolve to official sources [0.0 to 1.0]
- defect_recall: detected all injected defects [0.0 to 1.0]
- pii_containment: applicant facts kept inside basis[], claims/prose PII-free [0.0 to 1.0]
- blind_input_compliance: Worker operated blindly without ground truth leakage [0.0 to 1.0]

You MUST return evaluations for ALL {len(ordered_case_ids)} case IDs: {ordered_case_ids}.

Return ONLY a single valid JSON object matching this exact schema:
{{
  "doc_type": "{doc_type}",
  "case_evaluations": {{
    "<case_id>": {{
      "grounding_accuracy": 1.0,
      "citation_exactness": 1.0,
      "defect_recall": 1.0,
      "pii_containment": 1.0,
      "blind_input_compliance": 1.0
    }}
  }},
  "findings": [
    {{
      "case_id": "<case_id>",
      "category": "grounding|citation|defect_recall|pii|blind_input",
      "severity": "critical|major|minor",
      "description": "evidence-based finding"
    }}
  ],
  "patch_recommendations": [
    {{
      "target_file": "AGENTS.md or skills/pdf/SKILL.md or skills/document-agents/{doc_type}.md",
      "suggested_patch": "Specific directive to fix recurring Worker defect detection failures"
    }}
  ],
  "rationale": "Overall evaluation rationale"
}}
"""


_JUDGE_PROVENANCE_EXTRA_FIELDS = (
        "prompt_contract_hash",
        "input_manifest_hash",
        "case_ids",
        "pdf_hashes",
        "worker_report_hashes",
        "worker_input_manifest_hashes",
        "public_bundle_hashes",
        "worker_prompt_hashes",
        "research_hash",
        "ground_truth_hash",
        "model_config",
        "artifact_output_hash",
)


def _judge_provenance_digest(provenance: Dict[str, Any]) -> str:
    return canonical_provenance_digest(
        provenance,
        extra_fields=_JUDGE_PROVENANCE_EXTRA_FIELDS,
    )


def _parse_judge_jsonl_output(
    stdout_text: str,
) -> tuple[JudgeEvaluationBatch, str]:
    """Parse canonical Copilot JSONL stream assistant messages.

    Requires one raw JudgeEvaluationBatch JSON object in one final assistant message.
    """
    cleaned = _ANSI_ESCAPE.sub("", stdout_text).strip()
    candidates = []

    for line in cleaned.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        try:
            evt = json.loads(line_str)
        except json.JSONDecodeError as exc:
            raise JudgeExecutionError(f"Malformed Copilot JSONL event: {exc}") from exc

        if not isinstance(evt, dict):
            raise JudgeExecutionError("Malformed Copilot JSONL event: event is not a JSON object")

        evt_type = evt.get("type") or evt.get("event")
        if evt_type in (
            "assistant.reasoning",
            "tool.execution_start",
            "tool.execution_complete",
            "tool.execution_partial_result",
            "session.mcp_servers_loaded",
            "session.skills_loaded",
            "session.tools_updated",
            "session.background_tasks_changed",
        ):
            continue

        content = None
        if evt_type == "assistant.message":
            data = evt.get("data")
            if isinstance(data, dict):
                content = data.get("content")
            elif "content" in evt:
                content = evt.get("content")
        elif evt_type == "result":
            content = evt.get("content") or evt.get("result")

        if content and isinstance(content, str):
            candidates.append(content)

    if not candidates:
        raise JudgeExecutionError(
            "No valid JudgeEvaluationBatch JSON found in Judge response output"
        )
    if len(candidates) != 1:
        raise JudgeExecutionError(
            "Judge response must contain exactly one raw JSON object"
        )
    raw_content = candidates[0]
    try:
        return (
            JudgeEvaluationBatch.model_validate_json(raw_content),
            raw_content,
        )
    except Exception as exc:
        raise JudgeExecutionError(
            "Judge response must be one raw JSON object matching JudgeEvaluationBatch"
        ) from exc


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def run_batched_document_judge_async(
    doc_type: str,
    worker_reports: Dict[str, Dict[str, Any]],
    pdf_paths: List[Path],
    research_json: Dict[str, Any],
    ground_truth_specs: Dict[str, Dict[str, Any]],
    public_bundle: Optional[Dict[str, Any]] = None,
    runner_fn: Optional[Any] = None,
    output_dir: Optional[Path] = None,
    runtime: Optional[AgentRuntime] = None,
    descendant_registrar: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Execute privileged batched Claude Opus 4.8 Judge session for a document type.

    Evaluates all Worker reports against attached PDFs, Phase 72 research, and Phase 73 ground truth.
    Prohibits score fabrication or deterministic Python fallbacks.
    """
    if not isinstance(ground_truth_specs, dict):
        raise JudgeExecutionError("ground_truth_specs must be a dictionary")
    expected_case_ids = set(ground_truth_specs)
    if not expected_case_ids:
        raise JudgeExecutionError(
            f"No ground-truth cases provided for Judge evaluation of {doc_type}"
        )
    for case_id, spec in ground_truth_specs.items():
        if not isinstance(spec, dict):
            raise JudgeExecutionError(
                f"Ground-truth specification for '{case_id}' is not a dictionary"
            )
        embedded_case_id = spec.get("opaque_case_id")
        if embedded_case_id is not None and embedded_case_id != case_id:
            raise JudgeExecutionError(
                f"Ground-truth specification '{case_id}' opaque_case_id mismatch: "
                f"{embedded_case_id!r}"
            )
        embedded_doc_type = spec.get("doc_type")
        if embedded_doc_type is not None and embedded_doc_type != doc_type:
            raise JudgeExecutionError(
                f"Ground-truth specification '{case_id}' doc_type mismatch: "
                f"{embedded_doc_type!r}"
            )
    worker_case_ids = set(worker_reports)
    if worker_case_ids != expected_case_ids:
        missing = expected_case_ids - worker_case_ids
        extra = worker_case_ids - expected_case_ids
        raise JudgeExecutionError(
            f"Worker report key mismatch for {doc_type}: "
            f"missing {sorted(missing)}, extra {sorted(extra)}"
        )

    # Validate PDF attachment mapping: exactly one PDF attachment per expected Worker case ID
    pdf_map: Dict[str, Path] = {}
    for p in pdf_paths:
        cid = p.stem
        if cid in pdf_map:
            raise JudgeExecutionError(f"Duplicate PDF attachment for case_id '{cid}': {p}")
        pdf_map[cid] = p

    pdf_case_ids = set(pdf_map.keys())
    if pdf_case_ids != expected_case_ids:
        missing = expected_case_ids - pdf_case_ids
        extra = pdf_case_ids - expected_case_ids
        raise JudgeExecutionError(
            f"PDF attachment mismatch for {doc_type}: missing cases {sorted(missing)}, extra {sorted(extra)}"
        )

    active_public_bundle = public_bundle or build_public_review_bundle(doc_type)
    worker_input_manifests: Dict[str, Dict[str, Any]] = {}
    for cid in sorted(expected_case_ids):
        text_path = pdf_map[cid].with_suffix(".txt")
        if text_path.is_symlink():
            raise JudgeExecutionError(
                f"Worker extracted text for case '{cid}' is a symlink"
            )
        extracted_text = (
            text_path.read_text(encoding="utf-8", errors="replace")
            if text_path.is_file()
            else ""
        )
        allowed_text_sha256 = (
            hashlib.sha256(text_path.read_bytes()).hexdigest()
            if text_path.is_file()
            else None
        )
        worker_input_manifests[cid] = build_worker_input_manifest(
            doc_type=doc_type,
            public_bundle=active_public_bundle,
            input_pdf_sha256=hashlib.sha256(pdf_map[cid].read_bytes()).hexdigest(),
            extracted_text=extracted_text,
            allowed_text_sha256=allowed_text_sha256,
        )

    # Validate Worker report provenance and hashes before Judge invocation
    for cid, report in worker_reports.items():
        if not isinstance(report, dict):
            raise JudgeExecutionError(f"Worker report for case '{cid}' is not a dict")
        if report.get("case_id") != cid:
            raise JudgeExecutionError(
                f"Worker report '{cid}' case_id mismatch: {report.get('case_id')!r}"
            )
        if report.get("doc_type") != doc_type:
            raise JudgeExecutionError(
                f"Worker report '{cid}' doc_type mismatch: {report.get('doc_type')!r}"
            )
        prov = report.get("_provenance")
        if not isinstance(prov, dict):
            raise JudgeExecutionError(f"Worker report for case '{cid}' lacks required '_provenance'")
        input_pdf_sha = prov.get("input_pdf_sha256")
        if not input_pdf_sha:
            raise JudgeExecutionError(f"Worker report '{cid}' missing 'input_pdf_sha256' in provenance")
        actual_pdf_sha = hashlib.sha256(pdf_map[cid].read_bytes()).hexdigest()
        if input_pdf_sha != actual_pdf_sha:
            raise JudgeExecutionError(f"Worker report '{cid}' input_pdf_sha256 mismatch: expected {actual_pdf_sha}, got {input_pdf_sha}")
        worker_input = worker_input_manifests[cid]
        if (
            prov.get("bundle_hash") != worker_input["public_bundle_hash"]
            or prov.get("prompt_hash") != worker_input["worker_prompt_hash"]
            or prov.get("allowed_text_sha256")
            != worker_input["allowed_text_sha256"]
        ):
            raise JudgeExecutionError(
                f"Worker report '{cid}' input manifest binding mismatch"
            )
        is_injected_execution = runner_fn is not None or runtime is not None
        try:
            validate_persisted_agent_provenance(
                prov,
                expected_engine=(
                    "injected-test-runner"
                    if is_injected_execution
                    else "copilot-sdk"
                ),
                expected_is_live=not is_injected_execution,
                role="worker",
                model="gemini-3.6-flash",
                effort=None,
                context_tier=_CONTEXT_TIER,
                prompt_hash=prov.get("prompt_hash"),
                attachment_hashes=[actual_pdf_sha],
                output_hash=prov.get("output_hash"),
                extra_digest_fields=_WORKER_PROVENANCE_EXTRA_FIELDS,
                required_hash_fields=(
                    "input_pdf_sha256",
                    "bundle_hash",
                    "answer_hash",
                    "pii_manifest_hash",
                ),
                optional_hash_fields=("allowed_text_sha256",),
            )
        except Exception as exc:
            raise JudgeExecutionError(
                f"Worker report '{cid}' lacks complete valid provenance"
            ) from exc

    out_dir = Path(output_dir) if output_dir else None
    staging_cwd: Optional[Path] = None

    try:
        # Create fresh per-document privileged staging CWD outside repo/system temp
        _JUDGE_STAGE_ROOT.mkdir(parents=True, exist_ok=True)
        staging_cwd = Path(tempfile.mkdtemp(dir=_JUDGE_STAGE_ROOT))

        # Copy PDF attachments into privileged staging CWD and build BlobAttachments
        ordered_case_ids = sorted(expected_case_ids)
        staged_pdf_names: List[str] = []
        pdf_attachments: List[BlobAttachment] = []
        ordered_pdf_hashes: List[str] = []
        for cid in ordered_case_ids:
            src_pdf = pdf_map[cid]
            pdf_bytes = src_pdf.read_bytes()
            dst_pdf = staging_cwd / src_pdf.name
            shutil.copy2(src_pdf, dst_pdf)
            staged_pdf_names.append(src_pdf.name)
            ordered_pdf_hashes.append(hashlib.sha256(pdf_bytes).hexdigest())
            pdf_attachments.append(
                BlobAttachment(
                    data=pdf_bytes,
                    mime_type="application/pdf",
                    display_name=src_pdf.name,
                )
            )

        input_manifest, input_manifest_hash = build_judge_input_manifest(
            doc_type=doc_type,
            case_ids=ordered_case_ids,
            pdf_hashes_by_case=dict(zip(ordered_case_ids, ordered_pdf_hashes)),
            worker_reports=worker_reports,
            worker_input_manifests=worker_input_manifests,
            research_json=research_json,
            ground_truth_specs=ground_truth_specs,
        )
        worker_report_hashes = input_manifest["worker_report_hashes"]
        worker_input_manifest_hashes = input_manifest[
            "worker_input_manifest_hashes"
        ]
        public_bundle_hashes = input_manifest["public_bundle_hashes"]
        worker_prompt_hashes = input_manifest["worker_prompt_hashes"]
        research_hash = input_manifest["research_hash"]
        gt_hash = input_manifest["ground_truth_hash"]
        prompt_contract_hash = input_manifest["prompt_contract_hash"]
        model_config = input_manifest["model_config"]

        prompt = _build_judge_prompt(
            doc_type=doc_type,
            case_ids=ordered_case_ids,
            worker_reports=worker_reports,
            worker_input_manifests=worker_input_manifests,
            research_json=research_json,
            ground_truth_specs=ground_truth_specs,
            input_manifest_hash=input_manifest_hash,
            prompt_contract_hash=prompt_contract_hash,
        )

        max_attempts = 3 if runner_fn is None else 1
        last_error = None
        batch = None
        agent_result = None
        raw_judge_output = None

        for attempt in range(1, max_attempts + 1):
            try:
                if runner_fn is not None:
                    copilot_bin = shutil.which("copilot") or "copilot"
                    cmd = [copilot_bin, "-p", prompt]
                    for pdf_name in staged_pdf_names:
                        cmd.extend(["--attachment", pdf_name])
                    cmd.extend([
                        "--model", _JUDGE_MODEL,
                        "--effort", _JUDGE_EFFORT,
                        "--context", _CONTEXT_TIER,
                        "--output-format", "json",
                        "--stream", "off",
                        "--no-custom-instructions",
                        "--no-ask-user",
                        "--disable-builtin-mcps",
                        "--disallow-temp-dir",
                        "--excluded-tools=*",
                    ])
                    try:
                        stdout_text = runner_fn(cmd, staging_cwd)
                    except AgentRuntimeError:
                        raise
                    except Exception as exc:
                        raise AgentLifecycleError(
                            "Judge runner process lifecycle failed"
                        ) from exc
                    batch, raw_judge_output = _parse_judge_jsonl_output(
                        stdout_text
                    )
                else:
                    active_runtime = runtime or CopilotSdkRuntime(
                        base_directory=staging_cwd,
                        descendant_registrar=descendant_registrar,
                    )
                    request = AgentRequest(
                        role="judge",
                        model=_JUDGE_MODEL,
                        reasoning_effort=_JUDGE_EFFORT,
                        context_tier=_CONTEXT_TIER,
                        prompt=prompt,
                        attachments=pdf_attachments,
                        timeout_seconds=_LLM_TIMEOUT_SECONDS,
                        response_validation_policy=(
                            build_judge_response_validation_policy(
                                doc_type=doc_type,
                                allowed_case_ids=ordered_case_ids,
                            )
                        ),
                    )
                    agent_result = await active_runtime.run(request)
                    validate_agent_result(
                        agent_result,
                        request,
                        expected_engine=(
                            "injected-test-runner"
                            if runtime is not None
                            else "copilot-sdk"
                        ),
                        expected_is_live=runtime is None,
                    )
                    try:
                        batch = JudgeEvaluationBatch.model_validate_json(
                            agent_result.content
                        )
                        raw_judge_output = agent_result.content
                    except Exception as exc:
                        raise JudgeExecutionError(
                            "Judge response must be one raw JSON object matching "
                            "JudgeEvaluationBatch"
                        ) from exc

                if batch.doc_type != doc_type:
                    raise JudgeExecutionError(
                        f"Judge batch doc_type mismatch: expected '{doc_type}', got '{batch.doc_type}'"
                    )

                evaluated_case_ids = set(batch.case_evaluations.keys())
                if evaluated_case_ids != expected_case_ids:
                    missing = expected_case_ids - evaluated_case_ids
                    extra = evaluated_case_ids - expected_case_ids
                    raise JudgeExecutionError(
                        f"Judge case coverage mismatch for {doc_type}: missing {sorted(missing)}, extra {sorted(extra)}"
                    )

                for finding in batch.findings:
                    if finding.case_id not in expected_case_ids:
                        raise JudgeExecutionError(
                            f"Judge finding references invalid case_id '{finding.case_id}' for {doc_type}"
                        )
                break
            except AgentTimeoutError:
                raise
            except TransientAgentError as exc:
                last_error = exc
                if attempt < max_attempts:
                    logger.warning(
                        "Judge task attempt %d/%d failed for %s: %s. Retrying...",
                        attempt,
                        max_attempts,
                        doc_type,
                        exc,
                    )
                    await asyncio.sleep(3 * attempt)
                else:
                    raise last_error
            except Exception as exc:
                # Deterministic error fails immediately
                raise

        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        batch_dict = batch.model_dump()
        artifact_output_hash = _canonical_json_hash(batch_dict)

        prov = getattr(agent_result, "provenance", None) if agent_result else None
        sdk_ver = prov.sdk_version if prov else "injected-test-runner"
        protocol_ver = (
            prov.runtime_protocol_version
            if prov
            else "injected-test-protocol"
        )
        session_id = prov.session_id if prov else f"injected-judge-{doc_type}"
        is_injected = runner_fn is not None or runtime is not None
        completed_at = _utc_now()

        batch_dict["_provenance"] = {
            "engine": "injected-test-runner" if is_injected else "copilot-sdk",
            "is_live": not is_injected,
            "sdk_version": sdk_ver,
            "runtime_protocol_version": protocol_ver,
            "role": "judge",
            "model": _JUDGE_MODEL,
            "effort": _JUDGE_EFFORT,
            "context_tier": _CONTEXT_TIER,
            "session_id": session_id,
            "prompt_hash": prompt_hash,
            "prompt_contract_hash": prompt_contract_hash,
            "input_manifest_hash": input_manifest_hash,
            "case_ids": ordered_case_ids,
            "pdf_hashes": ordered_pdf_hashes,
            "attachment_hashes": ordered_pdf_hashes,
            "worker_report_hashes": worker_report_hashes,
            "worker_input_manifest_hashes": worker_input_manifest_hashes,
            "public_bundle_hashes": public_bundle_hashes,
            "worker_prompt_hashes": worker_prompt_hashes,
            "research_hash": research_hash,
            "ground_truth_hash": gt_hash,
            "model_config": model_config,
            "output_hash": (
                prov.output_hash
                if prov
                else hashlib.sha256(
                    raw_judge_output.encode("utf-8")
                ).hexdigest()
            ),
            "artifact_output_hash": artifact_output_hash,
            "terminal_event": prov.terminal_event if prov else "assistant.message",
            "started_at": prov.started_at if prov else completed_at,
            "completed_at": prov.completed_at if prov else completed_at,
            "duration_seconds": prov.duration_seconds if prov else 0.0,
            "retry_classification": (
                prov.retry_classification if prov else None
            ),
            "turn_count": prov.turn_count if prov else 1,
            "format_correction_count": (
                prov.format_correction_count if prov else 0
            ),
            "initial_prompt_hash": (
                prov.initial_prompt_hash if prov else prompt_hash
            ),
            "correction_prompt_hashes": (
                list(prov.correction_prompt_hashes) if prov else []
            ),
            "assistant_response_hash_chain": (
                list(prov.assistant_response_hash_chain)
                if prov
                else [
                    hashlib.sha256(
                        raw_judge_output.encode("utf-8")
                    ).hexdigest()
                ]
            ),
            "turn_session_ids": (
                list(prov.turn_session_ids) if prov else [session_id]
            ),
        }
        if prov is not None and prov.correction_kind is not None:
            batch_dict["_provenance"]["correction_kind"] = (
                prov.correction_kind
            )
        batch_dict["_provenance"]["provenance_digest"] = (
            _judge_provenance_digest(batch_dict["_provenance"])
        )

        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            _write_json(out_dir / "doc_type_eval.json", batch_dict)
            _write_json(out_dir / "judge_batch.json", batch_dict)

        return batch_dict

    except Exception as exc:
        if isinstance(exc, (AgentRuntimeError, JudgeExecutionError)):
            classified_error = exc
        elif isinstance(exc, OSError):
            classified_error = AgentLifecycleError(
                "Judge staging or artifact lifecycle failed"
            )
        else:
            classified_error = JudgeExecutionError(
                f"Batched Judge execution failed for {doc_type}: {exc}"
            )
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "doc_type_eval.json").unlink(missing_ok=True)
            (out_dir / "judge_batch.json").unlink(missing_ok=True)
            _write_json(
                out_dir / "judge_error.json",
                {
                    "doc_type": doc_type,
                    "error_type": type(classified_error).__name__,
                    "error": str(classified_error),
                    "timestamp": _utc_now(),
                },
            )
        if classified_error is exc:
            raise
        raise classified_error from exc
    finally:
        if staging_cwd is not None and staging_cwd.exists():
            shutil.rmtree(staging_cwd, ignore_errors=True)


def run_batched_document_judge(
    doc_type: str,
    worker_reports: Dict[str, Dict[str, Any]],
    pdf_paths: List[Path],
    research_json: Dict[str, Any],
    ground_truth_specs: Dict[str, Dict[str, Any]],
    public_bundle: Optional[Dict[str, Any]] = None,
    runner_fn: Optional[Any] = None,
    output_dir: Optional[Path] = None,
    runtime: Optional[AgentRuntime] = None,
    descendant_registrar: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Execute privileged batched Claude Opus 4.8 Judge session for a document type."""
    return run_async(
        run_batched_document_judge_async(
            doc_type=doc_type,
            worker_reports=worker_reports,
            pdf_paths=pdf_paths,
            research_json=research_json,
            ground_truth_specs=ground_truth_specs,
            public_bundle=public_bundle,
            runner_fn=runner_fn,
            output_dir=output_dir,
            runtime=runtime,
            descendant_registrar=descendant_registrar,
        ),
        async_api_name="run_batched_document_judge_async(...)",
    )


def judge_pipeline_case(doc_type: str, case_id: str) -> Dict[str, Any]:
    """Legacy single-case deterministic judge entrypoint.

    DISABLED per JUDGE_IMPROVE-01 and D-10. Deterministic Python score fabrication is prohibited.
    """
    raise NotImplementedError(
        "Legacy single-case deterministic Judge entrypoint disabled per JUDGE_IMPROVE-01. "
        "Use run_batched_document_judge."
    )


def run_pipeline_judge_for_doctype(
    doc_type: str,
    runner_fn: Optional[Any] = None,
    output_dir: Optional[Path] = None,
    pipeline_root: Optional[Path] = None,
    runtime: Optional[AgentRuntime] = None,
) -> Dict[str, Any]:
    """Run privileged batched Judge evaluation for all cases of a document type pipeline."""
    root = pipeline_root or _PIPELINES_DIR
    p_dir = root / doc_type

    worker_reports_dir = p_dir / "worker_reports"
    res_file = p_dir / "research" / "research.json"
    gt_dir = p_dir / "ground_truth"

    if not worker_reports_dir.exists():
        raise JudgeExecutionError(f"No worker_reports directory for pipeline {doc_type}")

    worker_reports = {}
    for wf in sorted(worker_reports_dir.glob("*.json")):
        try:
            worker_reports[wf.stem] = json.loads(wf.read_text(encoding="utf-8"))
        except Exception as exc:
            raise JudgeExecutionError(f"Failed to read worker report {wf.name}: {exc}") from exc

    research_json = json.loads(res_file.read_text(encoding="utf-8")) if res_file.is_file() else {}

    ground_truth_specs = {}
    gt_json = gt_dir / "ground_truth.json"
    if gt_json.is_file():
        for case in json.loads(gt_json.read_text(encoding="utf-8")):
            ground_truth_specs[case["opaque_case_id"]] = case
    else:
        for gf in sorted(gt_dir.glob("*.json")):
            if gf.name not in ("ground_truth.json", "generation_spec.json", "generation_provenance.json"):
                ground_truth_specs[gf.stem] = json.loads(gf.read_text(encoding="utf-8"))

    pdf_paths = []
    pdfs_dir = gt_dir / "pdfs"
    if pdfs_dir.is_dir():
        pdf_paths = list(pdfs_dir.glob("*.pdf"))

    return run_batched_document_judge(
        doc_type=doc_type,
        worker_reports=worker_reports,
        pdf_paths=pdf_paths,
        research_json=research_json,
        ground_truth_specs=ground_truth_specs,
        runner_fn=runner_fn,
        output_dir=output_dir or (p_dir / "judge_eval"),
        runtime=runtime,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    dt = sys.argv[1] if len(sys.argv) > 1 else "passport"
    run_pipeline_judge_for_doctype(dt)
