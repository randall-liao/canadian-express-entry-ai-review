"""Sandboxed Gemini Candidate Optimizer Agent Runner (D-15..D-18).

Executes Gemini 3.6 Flash long-context Copilot sessions to propose skill and prompt candidate
patches in isolated proposal sandboxes based strictly on sealed training Judge findings.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from crawler.eval.agent_runtime import (
    AgentRequest,
    AgentRuntime,
    AgentRuntimeError,
    AgentTimeoutError,
    TransientAgentError,
    canonical_provenance_digest,
    run_async,
    validate_agent_result,
)
from crawler.eval.copilot_sdk_runtime import CopilotSdkRuntime
from crawler.eval.holdout_splitter import (
    contains_holdout_semantics,
    seal_holdout_findings,
)
from crawler.eval.patch_evaluator import (
    validate_patch_allowlist,
    validate_target_allowlist,
)
from crawler.eval.public_bundle import DOC_TYPE_TO_SKILL

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_MD = _REPO_ROOT / "AGENTS.md"
_SKILL_PDF = _REPO_ROOT / "skills" / "pdf" / "SKILL.md"
_PROPOSALS_DIR = _REPO_ROOT / "reports" / "proposal_sandboxes"
_OPTIMIZER_MODEL = "gemini-3.6-flash"
_CONTEXT_TIER = "long_context"
_LLM_TIMEOUT_SECONDS = 300
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

logger = logging.getLogger(__name__)
_TRAINING_SCORE_FIELDS = (
    "grounding_accuracy",
    "citation_exactness",
    "defect_recall",
    "pii_containment",
    "blind_input_compliance",
)
_TRAINING_FINDING_FIELDS = ("case_id", "category", "severity", "description")
_OPTIMIZER_PROVENANCE_EXTRA_FIELDS = (
    "input_findings_sha256",
    "candidate_content_hash",
    "candidate_id",
    "target_file",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OptimizerProposal(BaseModel):
    """Strict JSON proposal model returned by optimizer agent."""

    model_config = ConfigDict(extra="forbid")

    target_file: str = Field(..., description="Target relative file path")
    candidate_content: str = Field(..., description="Proposed updated file content")
    rationale: str = Field(..., description="Technical rationale for the proposed patch")


def derive_optimizer_candidate_id(
    findings_hash: str,
    prompt_hash: str,
    target_relpath: str,
) -> str:
    """Derive the stable candidate identity from canonical generation inputs."""
    candidate_hash = hashlib.sha256(
        (findings_hash + prompt_hash + target_relpath).encode("utf-8")
    ).hexdigest()[:12]
    return f"candidate_{candidate_hash}"


def optimizer_provenance_digest(provenance: Dict[str, Any]) -> str:
    return canonical_provenance_digest(
        provenance,
        extra_fields=_OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
    )


def _build_optimizer_training_input(
    training_findings: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate and retain the internal training/holdout commitment record."""
    if not isinstance(training_findings, dict):
        raise ValueError("training_findings must be a dictionary")
    for forbidden_key in (
        "holdout_evaluations",
        "holdout_case_id",
        "holdout_findings",
    ):
        if forbidden_key in training_findings:
            raise ValueError(
                f"Holdout contamination detected in training_findings input: {forbidden_key}"
            )

    commitment = training_findings.get("holdout_commitment")
    if (
        not isinstance(commitment, dict)
        or not isinstance(commitment.get("count"), int)
        or isinstance(commitment.get("count"), bool)
        or commitment["count"] <= 0
        or not isinstance(commitment.get("hash"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", commitment["hash"])
    ):
        raise ValueError(
            "training_findings missing valid holdout_commitment structure "
            "(positive count and SHA-256 hash required)"
        )

    evaluations: Dict[str, Dict[str, Any]] = {}
    raw_evaluations = training_findings.get("case_evaluations", {})
    if not isinstance(raw_evaluations, dict):
        raise ValueError("training_findings case_evaluations must be a dictionary")
    for case_id, raw_score in raw_evaluations.items():
        if not isinstance(case_id, str) or not isinstance(raw_score, dict):
            raise ValueError("training case evaluations must map string IDs to objects")
        if "holdout" in case_id.lower():
            raise ValueError("Holdout-semantic case ID found in training evaluations")
        score: Dict[str, float] = {}
        for field in _TRAINING_SCORE_FIELDS:
            if field not in raw_score:
                continue
            value = raw_score[field]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise ValueError(
                    f"Training score {field!r} for {case_id!r} must be finite "
                    "and bounded between 0.0 and 1.0"
                )
            score[field] = float(value)
        evaluations[case_id] = score

    findings: List[Dict[str, Any]] = []
    raw_findings = training_findings.get("findings", [])
    if not isinstance(raw_findings, list):
        raise ValueError("training_findings findings must be an array")
    for raw_finding in raw_findings:
        if not isinstance(raw_finding, dict):
            raise ValueError("training findings must be objects")
        case_id = raw_finding.get("case_id")
        if case_id not in evaluations or contains_holdout_semantics(raw_finding):
            continue
        finding: Dict[str, str] = {}
        for field in _TRAINING_FINDING_FIELDS:
            if field not in raw_finding:
                continue
            value = raw_finding[field]
            if not isinstance(value, str):
                raise ValueError(f"Training finding field {field!r} must be a string")
            finding[field] = value
        findings.append(finding)

    doc_type = training_findings.get("doc_type")
    if doc_type is not None and not isinstance(doc_type, str):
        raise ValueError("training_findings doc_type must be a string or null")
    return {
        "schema_version": "optimizer-training-v1",
        "doc_type": doc_type,
        "case_evaluations": evaluations,
        "findings": findings,
        "holdout_commitment": {
            "count": commitment["count"],
            "hash": commitment["hash"],
        },
    }


def _build_optimizer_model_input(
    training_findings: Dict[str, Any],
) -> Dict[str, Any]:
    """Construct the explicit training-only object allowed into model input."""
    committed_input = _build_optimizer_training_input(training_findings)
    return {
        "schema_version": "optimizer-model-training-v1",
        "doc_type": committed_input["doc_type"],
        "case_evaluations": committed_input["case_evaluations"],
        "findings": committed_input["findings"],
    }


def _parse_optimizer_jsonl_output_with_raw(
    stdout_text: str,
    expected_target: str,
) -> tuple[OptimizerProposal, str]:
    """Parse JSONL stream from Copilot CLI and extract strict OptimizerProposal matching expected_target."""
    cleaned = _ANSI_ESCAPE.sub("", stdout_text).strip()
    valid_proposals: List[tuple[OptimizerProposal, str]] = []

    for line in cleaned.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        try:
            evt = json.loads(line_str)
            if not isinstance(evt, dict):
                continue
            evt_type = evt.get("type") or evt.get("event")
            if evt_type in (
                "assistant.reasoning",
                "tool.execution_start",
                "tool.execution_complete",
                "session.mcp_servers_loaded",
                "session.skills_loaded",
                "session.tools_updated",
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
                try:
                    prop = OptimizerProposal.model_validate_json(content)
                    if prop.target_file == expected_target:
                        valid_proposals.append((prop, content))
                except Exception:
                    continue
        except json.JSONDecodeError:
            continue

    if valid_proposals:
        return valid_proposals[-1]

    raise ValueError(
        f"No valid OptimizerProposal JSON matching target '{expected_target}' extracted from optimizer Copilot CLI session"
    )


def _parse_optimizer_jsonl_output(
    stdout_text: str,
    expected_target: str,
) -> OptimizerProposal:
    proposal, _ = _parse_optimizer_jsonl_output_with_raw(
        stdout_text,
        expected_target,
    )
    return proposal


async def run_candidate_optimization_pass_async(
    doc_type: Optional[str],
    training_findings: Dict[str, Any],
    current_skills: Optional[Dict[str, str]] = None,
    runner_fn: Optional[Any] = None,
    proposal_sandbox_root: Optional[Path] = None,
    target_file: Optional[str] = None,
    runtime: Optional[AgentRuntime] = None,
    descendant_registrar: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Execute Gemini 3.6 Flash candidate patch proposal session in sandbox (D-15..D-18).

    Inputs contain strictly training Judge findings (holdout findings sealed/purged).
    Optimizers write candidate proposals EXCLUSIVELY to proposal sandbox directories
    and NEVER edit shared source directly.
    """
    # 1. Target Relpath Resolution
    if target_file:
        target_relpath = target_file
    elif doc_type:
        stem = DOC_TYPE_TO_SKILL.get(doc_type, doc_type.replace("_", "-"))
        target_relpath = f"skills/document-agents/{stem}.md"
    else:
        target_relpath = "skills/pdf/SKILL.md"

    target_ok, target_reasons, target_relpath = validate_target_allowlist(
        target_relpath, doc_type
    )
    if not target_ok:
        raise RuntimeError(
            f"Candidate optimization failed for '{target_relpath}': "
            + "; ".join(target_reasons)
        )

    # 2. Holdout Commitment and Contamination Check
    for forbidden_key in (
        "holdout_evaluations",
        "holdout_case_id",
        "holdout_findings",
    ):
        if forbidden_key in training_findings:
            raise ValueError(
                f"Holdout contamination detected in training_findings input: "
                f"{forbidden_key}"
            )
    if doc_type:
        training_findings = seal_holdout_findings(training_findings, doc_type=doc_type)
    elif "holdout_commitment" not in training_findings:
        raise ValueError(
            "Shared optimizer inputs require an existing holdout commitment"
        )

    committed_input = _build_optimizer_training_input(training_findings)
    optimizer_input = _build_optimizer_model_input(committed_input)
    findings_str = json.dumps(
        optimizer_input, indent=2, ensure_ascii=False, sort_keys=True
    )
    findings_hash = hashlib.sha256(
        json.dumps(
            optimizer_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()

    # 3. Read Current Skill Content
    current_content = ""
    if current_skills and target_relpath in current_skills:
        current_content = current_skills[target_relpath]
    else:
        target_source_path = _REPO_ROOT / target_relpath
        if target_source_path.is_file():
            current_content = target_source_path.read_text(encoding="utf-8")

    # 4. XML-Escaped Prompt Construction
    def _xml_escape(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    prompt = f"""You are the Gemini 3.6 Flash optimizer agent proposing skill refinements for Canadian Express Entry document review.

TARGET FILE: {target_relpath}

<current_skill_content>
{_xml_escape(current_content)}
</current_skill_content>

<training_judge_findings sha256="{findings_hash}">
{_xml_escape(findings_str)}
</training_judge_findings>

INSTRUCTIONS:
Analyze the training Judge findings above.
Propose targeted, high-quality refinements to {target_relpath} that fix identified training failures.

CRITICAL RULES:
- Output a single strict JSON object with EXACTLY three fields:
  "target_file": "{target_relpath}",
  "candidate_content": "<complete updated file content for {target_relpath}>",
  "rationale": "<technical explanation of why this patch fixes training failures without regressing safety>"
- DIFF BOUNDS: Propose minimal, surgical, targeted edits to {target_relpath} that preserve existing document structure. Do NOT rewrite the file completely. Changed lines MUST be under 100 lines and change ratio MUST be under 30%.
- Do NOT include literal case IDs, opaque hashes, or test fixture names.
- Do NOT include applicant PII (names, SINs, DOBs).
- Do NOT reference ground_truth/, research.json, or internal evaluation code paths.
- Do NOT weaken safety, PII containment, or grounding contracts.
- Output ONLY the strict JSON object. The first output character MUST be "{{" and
  the last output character MUST be "}}". Do NOT wrap the object in Markdown or
  a ```json code fence.
"""

    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    sandbox_base = Path(proposal_sandbox_root or _PROPOSALS_DIR).resolve()
    candidate_id = derive_optimizer_candidate_id(
        findings_hash,
        prompt_hash,
        target_relpath,
    )
    sandbox_dir = (sandbox_base / candidate_id).resolve()
    if not sandbox_dir.is_relative_to(sandbox_base):
        raise RuntimeError("Candidate sandbox escaped the configured proposal root")

    # Clear sandbox directory before use
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    max_attempts = 3 if runner_fn is None else 1
    injected_runtime = (
        runtime is not None and not isinstance(runtime, CopilotSdkRuntime)
    )
    last_error = None
    proposal = None
    agent_result = None
    raw_optimizer_output = None

    try:
        for attempt in range(1, max_attempts + 1):
            try:
                if runner_fn is not None:
                    copilot_bin = shutil.which("copilot") or "copilot"
                    cmd = [
                        copilot_bin,
                        "-p", prompt,
                        "--model", _OPTIMIZER_MODEL,
                        "--context", _CONTEXT_TIER,
                        "--output-format", "json",
                        "--stream", "off",
                        "--no-custom-instructions",
                        "--no-ask-user",
                        "--disable-builtin-mcps",
                        "--disallow-temp-dir",
                        "--excluded-tools=*",
                    ]
                    stdout_text = runner_fn(cmd, sandbox_dir)
                    proposal, raw_optimizer_output = (
                        _parse_optimizer_jsonl_output_with_raw(
                            stdout_text,
                            expected_target=target_relpath,
                        )
                    )
                else:
                    active_runtime = runtime or CopilotSdkRuntime(
                        base_directory=sandbox_dir,
                        descendant_registrar=descendant_registrar,
                    )
                    request = AgentRequest(
                        role="optimizer",
                        model=_OPTIMIZER_MODEL,
                        context_tier=_CONTEXT_TIER,
                        prompt=prompt,
                        attachments=[],
                        timeout_seconds=_LLM_TIMEOUT_SECONDS,
                    )
                    agent_result = await active_runtime.run(request)
                    validate_agent_result(
                        agent_result,
                        request,
                        expected_engine=(
                            "injected-test-runner"
                            if injected_runtime
                            else "copilot-sdk"
                        ),
                        expected_is_live=not injected_runtime,
                    )
                    try:
                        proposal = OptimizerProposal.model_validate_json(
                            agent_result.content
                        )
                        raw_optimizer_output = agent_result.content
                    except Exception as exc:
                        raise ValueError(f"Invalid OptimizerProposal JSON from optimizer session: {exc}") from exc

                    if proposal.target_file != target_relpath:
                        raise ValueError(f"Optimizer proposal target_file mismatch: expected '{target_relpath}', got '{proposal.target_file}'")
                break
            except AgentTimeoutError:
                raise
            except TransientAgentError as exc:
                last_error = exc
                if attempt < max_attempts:
                    logger.warning("Optimizer task attempt %d/%d failed for %s: %s. Retrying...", attempt, max_attempts, target_relpath, exc)
                    await asyncio.sleep(2 * attempt)
                else:
                    raise last_error
            except Exception as exc:
                # Deterministic error fails immediately
                raise

        candidate_content = proposal.candidate_content

        is_valid, rejection_reasons = validate_patch_allowlist(
            candidate_content,
            target_relpath,
            doc_type=doc_type,
            current_content=current_content,
            forbidden_private_texts=(
                finding["description"]
                for finding in optimizer_input["findings"]
                if "description" in finding
            ),
        )
        candidate_file = (sandbox_dir / target_relpath).resolve()
        if not candidate_file.is_relative_to(sandbox_dir):
            raise ValueError("Candidate target escaped its proposal sandbox")
        if is_valid:
            candidate_file.parent.mkdir(parents=True, exist_ok=True)
            candidate_file.write_text(candidate_content, encoding="utf-8")
        else:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    except AgentRuntimeError:
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir)
        raise
    except Exception as exc:
        # Fail closed: clean up stale candidate sandbox on error
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir)
        raise RuntimeError(f"Candidate optimization failed for '{target_relpath}': {exc}") from exc

    candidate_content_hash = hashlib.sha256(
        candidate_content.encode("utf-8")
    ).hexdigest()
    raw_output_hash = hashlib.sha256(
        raw_optimizer_output.encode("utf-8")
    ).hexdigest()

    prov = getattr(agent_result, "provenance", None) if agent_result else None
    sdk_ver = prov.sdk_version if prov else "injected-test-runner"
    protocol_ver = (
        prov.runtime_protocol_version
        if prov
        else "injected-test-protocol"
    )
    session_id = prov.session_id if prov else f"injected-optimizer-{candidate_id}"
    is_injected = runner_fn is not None or injected_runtime
    completed_at = _utc_now()

    prov_dict = {
        "engine": "injected-test-runner" if is_injected else "copilot-sdk",
        "is_live": not is_injected,
        "sdk_version": sdk_ver,
        "runtime_protocol_version": protocol_ver,
        "role": "optimizer",
        "model": _OPTIMIZER_MODEL,
        "effort": None,
        "context_tier": _CONTEXT_TIER,
        "session_id": session_id,
        "attachment_hashes": [],
        "input_findings_sha256": findings_hash,
        "prompt_hash": prompt_hash,
        "output_hash": prov.output_hash if prov else raw_output_hash,
        "candidate_content_hash": candidate_content_hash,
        "terminal_event": prov.terminal_event if prov else "assistant.message",
        "candidate_id": candidate_id,
        "target_file": target_relpath,
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
            else [raw_output_hash]
        ),
        "turn_session_ids": (
            list(prov.turn_session_ids) if prov else [session_id]
        ),
    }
    if prov is not None and prov.correction_kind is not None:
        prov_dict["correction_kind"] = prov.correction_kind
    prov_dict["provenance_digest"] = optimizer_provenance_digest(prov_dict)

    return {
        "candidate_id": candidate_id,
        "doc_type": doc_type,
        "target_file": target_relpath,
        "candidate_relpath": f"proposals/{candidate_id}/{target_relpath}",
        "candidate_content": candidate_content,
        "rationale": proposal.rationale,
        "_optimizer_output": raw_optimizer_output,
        "is_valid": is_valid,
        "rejection_reasons": rejection_reasons,
        "_holdout_commitment": committed_input["holdout_commitment"],
        "_provenance": prov_dict,
    }


def run_candidate_optimization_pass(
    doc_type: Optional[str],
    training_findings: Dict[str, Any],
    current_skills: Optional[Dict[str, str]] = None,
    runner_fn: Optional[Any] = None,
    proposal_sandbox_root: Optional[Path] = None,
    target_file: Optional[str] = None,
    runtime: Optional[AgentRuntime] = None,
    descendant_registrar: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Execute Gemini 3.6 Flash candidate patch proposal session in sandbox (D-15..D-18)."""
    return run_async(
        run_candidate_optimization_pass_async(
            doc_type=doc_type,
            training_findings=training_findings,
            current_skills=current_skills,
            runner_fn=runner_fn,
            proposal_sandbox_root=proposal_sandbox_root,
            target_file=target_file,
            runtime=runtime,
            descendant_registrar=descendant_registrar,
        ),
        async_api_name="run_candidate_optimization_pass_async(...)",
    )


def run_genuine_optimization_loop(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Legacy entrypoint wrapper delegating to LoopOrchestrator."""
    raise NotImplementedError(
        "run_genuine_optimization_loop is deprecated. Use LoopOrchestrator in crawler.eval.loop_orchestrator"
    )
