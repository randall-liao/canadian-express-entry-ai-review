"""Loop Orchestrator for Phase 74 Agent Self-Improvement (D-13..D-22, REAL_AGENT_EXECUTION-01).

Coordinates end-to-end execution across 23 Phase 73 Express Entry document pipelines:
- Discovers doc types and loads 236 opaque cases with PDF SHA256 pre-call verification.
- Two-stage global pool architecture for baseline, shared candidate evaluation, and final passes:
  1. Global Worker pool (max_workers=5): schedules all selected Worker cases across all doc types.
  2. Global Judge pool (max_workers=5): schedules all 23 per-document Judge batches.
- Bounded Worker concurrency (<= 5) for targeted per-document candidate evaluation.
- Thread-safe runtime concurrency tracking and limit assertion.
- Deterministic result ordering (sorted by case ID and doc type) and artifact path creation.
- Fail-closed error metadata writing (`worker_error.json`, `judge_error.json`) on partial failures.
- Non-regressing patch evaluation, atomic commits, and loop convergence checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from crawler.eval.agent_runtime import (
    AgentRuntimeError,
    validate_persisted_agent_provenance,
)
from crawler.eval.genuine_optimizer import (
    OptimizerProposal,
    _OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
    derive_optimizer_candidate_id,
    run_candidate_optimization_pass,
)
from crawler.eval.patch_evaluator import (
    apply_patch_atomically,
    evaluate_candidate_patch,
    validate_patch_allowlist,
)
from crawler.eval.pipeline_judge import (
    JudgeEvaluationBatch,
    _JUDGE_PROVENANCE_EXTRA_FIELDS,
    _build_judge_prompt,
    _canonical_json_hash as _judge_artifact_hash,
    _judge_provenance_digest,
    build_judge_input_manifest,
    run_batched_document_judge,
)
from crawler.eval.pipeline_worker import (
    ParentPiiManifest,
    _assert_answer_blindness_and_pii,
    _build_parent_pii_manifest,
    _build_worker_prompt,
    _canonical_json_hash as _worker_answer_hash,
    _WORKER_PROVENANCE_EXTRA_FIELDS,
    _worker_provenance_digest,
    build_worker_input_manifest,
    run_blind_worker_task,
)
from crawler.eval.public_bundle import DOC_TYPE_TO_SKILL, build_public_review_bundle
from crawler.eval.real_worker import _validate_answer_object
from crawler.grounding import check_answer_grounding
from crawler.eval.holdout_splitter import (
    get_holdout_case_ids,
    seal_holdout_findings,
    split_doc_type_cases,
)
from crawler.synthetic.schemas import ExpressEntryDocType

logger = logging.getLogger("crawler.eval.loop_orchestrator")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORTS_DIR = _REPO_ROOT / "reports"
_ITERATIONS_DIR = _REPORTS_DIR / "phase74_iterations"
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"

DEFAULT_MAX_CONCURRENCY: int = 5
MIN_CONCURRENCY_LIMIT: int = 1
MAX_CONCURRENCY_LIMIT: int = 5
_CANDIDATE_ID_RE = re.compile(r"^candidate_[a-f0-9]{12}$")
_PUBLISHABLE_OPTIMIZER_PROVENANCE_FIELDS = (
    "engine",
    "is_live",
    "sdk_version",
    "runtime_protocol_version",
    "role",
    "model",
    "effort",
    "context_tier",
    "session_id",
    "attachment_hashes",
    "input_findings_sha256",
    "prompt_hash",
    "output_hash",
    "candidate_content_hash",
    "terminal_event",
    "candidate_id",
    "target_file",
    "started_at",
    "completed_at",
    "duration_seconds",
    "retry_classification",
    "provenance_digest",
)


def _validate_concurrency(val: Any) -> int:
    """Validate concurrency parameter within strict bounds 1..5."""
    if not isinstance(val, int) or isinstance(val, bool) or val < MIN_CONCURRENCY_LIMIT or val > MAX_CONCURRENCY_LIMIT:
        raise ValueError(
            f"max_concurrency must be an integer between {MIN_CONCURRENCY_LIMIT} and {MAX_CONCURRENCY_LIMIT}, got {val!r}"
        )
    return val


def _has_current_sdk_provenance(
    provenance: Any,
    *,
    role: str,
    model: str,
    effort: Optional[str],
    context_tier: str,
    attachment_hashes: List[str],
) -> bool:
    """Accept reusable live artifacts only with current, exact SDK evidence."""
    if not isinstance(provenance, dict):
        return False
    extra_fields = {
        "worker": _WORKER_PROVENANCE_EXTRA_FIELDS,
        "judge": _JUDGE_PROVENANCE_EXTRA_FIELDS,
        "optimizer": _OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
    }.get(role)
    if extra_fields is None:
        return False
    required_hash_fields = {
        "worker": (
            "input_pdf_sha256",
            "bundle_hash",
            "answer_hash",
            "pii_manifest_hash",
        ),
        "judge": (
            "prompt_contract_hash",
            "input_manifest_hash",
            "research_hash",
            "ground_truth_hash",
            "artifact_output_hash",
        ),
        "optimizer": (
            "input_findings_sha256",
            "candidate_content_hash",
        ),
    }[role]
    required_hash_list_fields = {
        "worker": (),
        "judge": (
            "pdf_hashes",
            "worker_report_hashes",
            "worker_input_manifest_hashes",
            "public_bundle_hashes",
            "worker_prompt_hashes",
        ),
        "optimizer": (),
    }[role]
    try:
        validate_persisted_agent_provenance(
            provenance,
            expected_engine="copilot-sdk",
            expected_is_live=True,
            role=role,
            model=model,
            effort=effort,
            context_tier=context_tier,
            prompt_hash=provenance.get("prompt_hash"),
            attachment_hashes=attachment_hashes,
            output_hash=provenance.get("output_hash"),
            extra_digest_fields=extra_fields,
            required_hash_fields=required_hash_fields,
            optional_hash_fields=(
                ("allowed_text_sha256",) if role == "worker" else ()
            ),
            required_hash_list_fields=required_hash_list_fields,
        )
    except AgentRuntimeError:
        return False
    return True


def _publishable_optimizer_provenance(
    candidate_result: Any,
) -> Dict[str, Any]:
    """Validate and return complete non-content optimizer execution evidence."""
    if not isinstance(candidate_result, dict):
        raise ValueError("Completed proposal lacks an optimizer candidate result")
    provenance = candidate_result.get("_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Completed proposal lacks optimizer provenance")

    missing_fields = [
        field
        for field in _PUBLISHABLE_OPTIMIZER_PROVENANCE_FIELDS
        if field not in provenance
    ]
    if missing_fields:
        raise ValueError(
            f"optimizer provenance missing required fields: {missing_fields}"
        )

    engine = provenance["engine"]
    is_live = provenance["is_live"]
    if engine not in {"copilot-sdk", "injected-test-runner"}:
        raise ValueError(f"optimizer provenance has invalid engine: {engine!r}")
    if type(is_live) is not bool or is_live != (engine == "copilot-sdk"):
        raise ValueError("optimizer provenance engine/is_live relationship is invalid")

    try:
        validate_persisted_agent_provenance(
            provenance,
            expected_engine=engine,
            expected_is_live=is_live,
            role="optimizer",
            model="gemini-3.6-flash",
            effort=None,
            context_tier="long_context",
            prompt_hash=provenance["prompt_hash"],
            attachment_hashes=[],
            output_hash=provenance["output_hash"],
            extra_digest_fields=_OPTIMIZER_PROVENANCE_EXTRA_FIELDS,
            required_hash_fields=(
                "input_findings_sha256",
                "candidate_content_hash",
            ),
            reject_unexpected_fields=False,
        )
    except AgentRuntimeError as exc:
        raise ValueError(f"optimizer provenance is invalid: {exc}") from exc

    target_file = candidate_result.get("target_file")
    if (
        not isinstance(target_file, str)
        or not target_file
        or provenance["target_file"] != target_file
    ):
        raise ValueError("optimizer provenance target_file does not bind the proposal")
    candidate_id = candidate_result.get("candidate_id")
    expected_candidate_id = derive_optimizer_candidate_id(
        provenance["input_findings_sha256"],
        provenance["prompt_hash"],
        target_file,
    )
    if (
        not isinstance(candidate_id, str)
        or not _CANDIDATE_ID_RE.fullmatch(candidate_id)
        or provenance["candidate_id"] != candidate_id
        or candidate_id != expected_candidate_id
    ):
        raise ValueError(
            "optimizer provenance candidate_id does not recompute from generation inputs"
        )
    candidate_content = candidate_result.get("candidate_content")
    if not isinstance(candidate_content, str):
        raise ValueError("Completed optimizer proposal lacks candidate content")
    expected_content_hash = hashlib.sha256(
        candidate_content.encode("utf-8")
    ).hexdigest()
    if provenance["candidate_content_hash"] != expected_content_hash:
        raise ValueError(
            "optimizer provenance candidate_content_hash does not bind candidate content"
        )

    raw_output = candidate_result.get("_optimizer_output")
    if not isinstance(raw_output, str):
        raise ValueError("optimizer output is unavailable for proposal validation")
    expected_output_hash = hashlib.sha256(
        raw_output.encode("utf-8")
    ).hexdigest()
    if provenance["output_hash"] != expected_output_hash:
        raise ValueError("optimizer output hash does not bind the raw output")
    try:
        output_proposal = OptimizerProposal.model_validate_json(raw_output)
    except Exception as exc:
        raise ValueError("optimizer output is not a strict proposal object") from exc
    if (
        output_proposal.target_file != target_file
        or output_proposal.candidate_content != candidate_content
        or output_proposal.rationale != candidate_result.get("rationale")
    ):
        raise ValueError(
            "optimizer candidate content does not match the validated output"
        )

    return {
        field: provenance[field]
        for field in _PUBLISHABLE_OPTIMIZER_PROVENANCE_FIELDS
    }


def _blocked_patch_record(
    *,
    iteration: int,
    doc_type: str,
    reason: str,
    candidate_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Represent infrastructure blockage without inventing optimizer success."""
    proposal_completed = isinstance(candidate_result, dict)
    record: Dict[str, Any] = {
        "iteration": iteration,
        "decision": "blocked",
        "proposal_completed": proposal_completed,
        "doc_type": doc_type,
        "reasons": [reason],
    }
    if proposal_completed:
        try:
            published = _publishable_optimizer_provenance(candidate_result)
        except ValueError:
            record["proposal_completed"] = False
            record["reasons"] = [
                f"{reason}: optimizer provenance could not be validated"
            ]
        else:
            for field in ("target_file", "candidate_id"):
                value = candidate_result.get(field)
                if isinstance(value, str) and value:
                    record[field] = value
            record["optimizer_provenance"] = published
    return record


def _worker_reuse_bindings(
    *,
    pipeline_dir: Path,
    case_id: str,
    doc_type: str,
    public_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    """Reconstruct every Worker input binding available at reuse time."""
    source_pdf = (
        pipeline_dir / "ground_truth" / "pdfs" / f"{case_id}.pdf"
    )
    if not source_pdf.is_file():
        raise FileNotFoundError(
            f"Current staged Worker PDF is missing: {source_pdf}"
        )
    source_txt = source_pdf.with_suffix(".txt")
    extracted_text = ""
    allowed_text_hash = None
    if source_txt.is_file():
        text_bytes = source_txt.read_bytes()
        extracted_text = text_bytes.decode("utf-8", errors="replace")
        allowed_text_hash = hashlib.sha256(text_bytes).hexdigest()
    prompt = _build_worker_prompt(
        doc_type=doc_type,
        public_bundle=public_bundle,
        extracted_text=extracted_text,
    )
    pii_manifest = _build_parent_pii_manifest(
        pdf_path=source_pdf,
        extracted_text=extracted_text,
        pipeline_root=pipeline_dir,
        case_id=case_id,
    )
    return {
        "bundle_hash": public_bundle["bundle_hash"],
        "allowed_text_sha256": allowed_text_hash,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "pii_manifest": pii_manifest,
    }


def _is_reusable_worker_report(
    data: Any,
    *,
    pipeline_dir: Path,
    case: Dict[str, Any],
    doc_type: str,
    public_bundle: Dict[str, Any],
) -> Optional[ParentPiiManifest]:
    """Accept only a live SDK Worker artifact bound to the exact current inputs."""
    if not isinstance(data, dict):
        return None
    case_id = case["opaque_case_id"]
    if data.get("case_id") != case_id or data.get("doc_type") != doc_type:
        return None
    try:
        answer = {
            field: data[field]
            for field in ("question", "claims", "basis", "abstentions", "prose")
        }
        expected = _worker_reuse_bindings(
            pipeline_dir=pipeline_dir,
            case_id=case_id,
            doc_type=doc_type,
            public_bundle=public_bundle,
        )
    except (KeyError, OSError, TypeError, ValueError):
        return None
    provenance = data.get("_provenance")
    pii_manifest = expected["pii_manifest"]
    reusable = bool(
        _has_current_sdk_provenance(
            provenance,
            role="worker",
            model="gemini-3.6-flash",
            effort=None,
            context_tier="long_context",
            attachment_hashes=[case["pdf_sha256"]],
        )
        and provenance.get("input_pdf_sha256") == case["pdf_sha256"]
        and provenance.get("bundle_hash") == expected["bundle_hash"]
        and provenance.get("allowed_text_sha256")
        == expected["allowed_text_sha256"]
        and provenance.get("prompt_hash") == expected["prompt_hash"]
        and provenance.get("answer_hash") == _worker_answer_hash(answer)
        and provenance.get("pii_manifest_hash")
        == pii_manifest.manifest_hash
        and provenance.get("pii_manifest_count") == pii_manifest.count
        and provenance.get("pii_manifest_categories")
        == pii_manifest.category_summary
        and provenance.get("provenance_digest")
        == _worker_provenance_digest(provenance)
    )
    return pii_manifest if reusable else None


class PipelineConcurrencyTracker:
    """Thread-safe tracker enforcing active Worker and Judge concurrency bounds (<= 5)."""

    def __init__(self, max_concurrency: int = DEFAULT_MAX_CONCURRENCY):
        self.max_concurrency = _validate_concurrency(max_concurrency)
        self.active_workers: int = 0
        self.peak_workers: int = 0
        self.active_judges: int = 0
        self.peak_judges: int = 0
        self._lock = threading.Lock()

    def reset_peaks(self) -> None:
        with self._lock:
            self.peak_workers = 0
            self.peak_judges = 0

    def enter_worker(self) -> None:
        with self._lock:
            self.active_workers += 1
            if self.active_workers > self.peak_workers:
                self.peak_workers = self.active_workers
            if self.active_workers > self.max_concurrency:
                raise RuntimeError(
                    f"Worker concurrency assertion failed: active workers {self.active_workers} exceeds max limit {self.max_concurrency}"
                )

    def exit_worker(self) -> None:
        with self._lock:
            self.active_workers -= 1

    def enter_judge(self) -> None:
        with self._lock:
            self.active_judges += 1
            if self.active_judges > self.peak_judges:
                self.peak_judges = self.active_judges
            if self.active_judges > self.max_concurrency:
                raise RuntimeError(
                    f"Judge concurrency assertion failed: active judges {self.active_judges} exceeds max limit {self.max_concurrency}"
                )

    def exit_judge(self) -> None:
        with self._lock:
            self.active_judges -= 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mean_metrics(eval_list: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculate mean metric scores across evaluations (fails closed on empty or non-finite)."""
    if not eval_list:
        raise ValueError("_mean_metrics failed closed: eval_list is empty")

    dims = [
        "grounding_accuracy",
        "citation_exactness",
        "defect_recall",
        "pii_containment",
        "blind_input_compliance",
    ]
    res: Dict[str, float] = {}
    for d in dims:
        vals = []
        for e in eval_list:
            if not isinstance(e, dict):
                raise ValueError(f"_mean_metrics failed closed: evaluation entry is not a dict: {type(e)}")
            val = e.get(d)
            if val is None or not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                raise ValueError(f"_mean_metrics failed closed: missing or non-finite metric '{d}' ({val})")
            vals.append(float(val))
        res[d] = sum(vals) / len(vals)

    res["overall_score"] = sum(res.values()) / len(res)
    return res


class LoopOrchestrator:
    """Orchestrates Phase 74 agent self-improvement loop across all document pipelines."""

    def __init__(
        self,
        pipelines_dir: Optional[Path] = None,
        iterations_dir: Optional[Path] = None,
        corpus_db_path: Optional[Path] = None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ):
        self.pipelines_dir = Path(pipelines_dir or _PIPELINES_DIR)
        self.iterations_dir = Path(iterations_dir or _ITERATIONS_DIR)
        self.corpus_db_path = Path(corpus_db_path or (_REPO_ROOT / "corpus" / "index.db"))
        self.iterations_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrency = _validate_concurrency(max_concurrency)
        self.tracker = PipelineConcurrencyTracker(max_concurrency=self.max_concurrency)
        self.accepted_patches: List[Dict[str, Any]] = []
        self.rejected_patches: List[Dict[str, Any]] = []
        self.blocked_patches: List[Dict[str, Any]] = []

    def _discover_doc_types(self, require_all_23: bool = True) -> List[str]:
        """Discover active Phase 73 document pipelines matching ExpressEntryDocType enum values."""
        valid_enum_names = {e.value for e in ExpressEntryDocType}
        discovered = []

        if not self.pipelines_dir.exists():
            if require_all_23:
                raise ValueError(f"Pipelines directory does not exist: {self.pipelines_dir}")
            return []

        for item in sorted(self.pipelines_dir.iterdir()):
            if not item.is_dir():
                continue
            doc_type = item.name
            if doc_type not in valid_enum_names:
                continue

            gt_file = item / "ground_truth" / "ground_truth.json"
            res_file = item / "research" / "research.json"
            pdfs_dir = item / "ground_truth" / "pdfs"

            if not (gt_file.is_file() and res_file.is_file() and pdfs_dir.is_dir()):
                if require_all_23:
                    raise ValueError(
                        f"Pipeline for {doc_type} missing required Phase 73 data files in {item}"
                    )
                continue

            discovered.append(doc_type)

        if require_all_23 and len(discovered) != 23:
            missing = sorted(list(valid_enum_names - set(discovered)))
            raise ValueError(
                f"Discovered {len(discovered)} pipelines, expected 23 ExpressEntryDocType pipelines. Missing: {missing}"
            )

        return sorted(discovered)

    def _load_doc_type_cases(
        self, doc_type: str, global_case_ids: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """Load, validate SHA256 pre-call, and verify reciprocal sibling links for a document type's cases."""
        p_dir = self.pipelines_dir / doc_type
        gt_file = p_dir / "ground_truth" / "ground_truth.json"
        pdfs_dir = p_dir / "ground_truth" / "pdfs"

        if not gt_file.is_file():
            raise FileNotFoundError(f"Missing ground_truth.json for {doc_type} at {gt_file}")

        try:
            cases = json.loads(gt_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to parse ground_truth.json for {doc_type}") from exc

        if not isinstance(cases, list) or len(cases) not in (10, 12):
            raise ValueError(
                f"Doc type {doc_type} ground_truth.json must contain 10 or 12 case dicts, got {len(cases)}"
            )

        case_map = {c.get("opaque_case_id"): c for c in cases if isinstance(c, dict)}
        if len(case_map) != len(cases):
            raise ValueError(f"Duplicate opaque_case_id in ground_truth.json for {doc_type}")

        hex32_pattern = re.compile(r"^[0-9a-f]{32}$")

        for c in cases:
            cid = c.get("opaque_case_id")
            sid = c.get("sibling_case_id")
            c_dt = c.get("doc_type")
            pdf_hash = c.get("pdf_sha256")

            if not cid or not hex32_pattern.match(cid):
                raise ValueError(f"Invalid opaque_case_id '{cid}' in {doc_type}")
            if not sid or not hex32_pattern.match(sid):
                raise ValueError(f"Invalid sibling_case_id '{sid}' in {doc_type}")
            if c_dt != doc_type:
                raise ValueError(f"Case {cid} doc_type '{c_dt}' does not match pipeline '{doc_type}'")

            if global_case_ids is not None:
                if cid in global_case_ids:
                    raise ValueError(f"Global duplicate case ID detected: {cid}")
                global_case_ids.add(cid)

            sibling = case_map.get(sid)
            if not sibling or sibling.get("sibling_case_id") != cid:
                raise ValueError(f"Sibling case ID reciprocal link broken between {cid} and {sid}")

            pdf_path = pdfs_dir / f"{cid}.pdf"
            if not pdf_path.is_file():
                raise FileNotFoundError(f"Missing PDF for case {cid} in {doc_type} at {pdf_path}")

            actual_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            if actual_hash != pdf_hash:
                raise ValueError(
                    f"PDF SHA256 mismatch for case {cid} in {doc_type}: expected {pdf_hash}, got {actual_hash}"
                )

        return sorted(cases, key=lambda x: x["opaque_case_id"])

    def run_doctype_workers_pass(
        self,
        doc_type: str,
        cases: List[Dict[str, Any]],
        iteration_name: str = "iter_00_baseline",
        custom_bundle: Optional[Dict[str, Any]] = None,
        runner_fn: Optional[Any] = None,
        max_concurrency: Optional[int] = None,
        max_worker_concurrency: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Run Workers with bounded concurrency (up to 5) for a single document type."""
        eff_concurrency = _validate_concurrency(
            max_concurrency if max_concurrency is not None else (
                max_worker_concurrency if max_worker_concurrency is not None else self.max_concurrency
            )
        )
        pipeline_dir = self.pipelines_dir / doc_type
        worker_out_dir = pipeline_dir / "iterations" / iteration_name / "worker_reports"
        worker_out_dir.mkdir(parents=True, exist_ok=True)
        worker_bundle = custom_bundle or build_public_review_bundle(
            doc_type=doc_type,
            corpus_db_path=self.corpus_db_path,
        )

        def _execute_worker_task(c: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
            cid = c["opaque_case_id"]
            report_file = worker_out_dir / f"{cid}.json"
            if not report_file.is_file():
                report_file = worker_out_dir / f"case_{cid}.json"
            if report_file.is_file() and runner_fn is None:
                try:
                    data = json.loads(report_file.read_text(encoding="utf-8"))
                    reuse_manifest = _is_reusable_worker_report(
                        data,
                        pipeline_dir=pipeline_dir,
                        case=c,
                        doc_type=doc_type,
                        public_bundle=worker_bundle,
                    )
                    if reuse_manifest is not None:
                        _validate_answer_object(data)
                        check_answer_grounding(data, db_path=self.corpus_db_path)
                        _assert_answer_blindness_and_pii(
                            data,
                            pii_manifest=reuse_manifest,
                        )
                        logger.info("Reusing existing validated worker report for case %s in %s", cid, doc_type)
                        return cid, data
                except Exception:
                    pass

            self.tracker.enter_worker()
            try:
                report = run_blind_worker_task(
                    opaque_case_id=cid,
                    doc_type=doc_type,
                    public_bundle=worker_bundle,
                    runner_fn=runner_fn,
                    pipeline_root=pipeline_dir,
                    output_dir=worker_out_dir,
                    corpus_db_path=self.corpus_db_path,
                )
                return cid, report
            finally:
                self.tracker.exit_worker()

        worker_reports: Dict[str, Dict[str, Any]] = {}
        worker_errors: Dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=eff_concurrency) as executor:
            future_to_case = {
                executor.submit(_execute_worker_task, case): case["opaque_case_id"] for case in cases
            }
            for future in as_completed(future_to_case):
                cid = future_to_case[future]
                try:
                    res_cid, report = future.result()
                    worker_reports[res_cid] = report
                except Exception as exc:
                    logger.error("Worker task failed for case %s in %s: %s", cid, doc_type, exc)
                    worker_errors[cid] = str(exc)

        if worker_errors or len(worker_reports) != len(cases):
            error_data = {
                "doc_type": doc_type,
                "iteration": iteration_name,
                "expected_cases": len(cases),
                "successful_reports": len(worker_reports),
                "errors": worker_errors,
                "timestamp": _utc_now(),
            }
            p_iter_dir = pipeline_dir / "iterations" / iteration_name
            p_iter_dir.mkdir(parents=True, exist_ok=True)
            (p_iter_dir / "worker_error.json").write_text(
                json.dumps(error_data, indent=2), encoding="utf-8"
            )
            raise RuntimeError(
                f"Worker pass failed closed for {doc_type}: {len(worker_errors)} worker errors ({list(worker_errors.keys())})"
            )

        worker_reports = {cid: worker_reports[cid] for cid in sorted(worker_reports.keys())}
        return worker_reports

    def run_doctype_judge_pass(
        self,
        doc_type: str,
        cases: List[Dict[str, Any]],
        worker_reports: Dict[str, Dict[str, Any]],
        iteration_name: str = "iter_00_baseline",
        public_bundle: Optional[Dict[str, Any]] = None,
        runner_fn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run privileged batched Judge for a single document type."""
        pipeline_dir = self.pipelines_dir / doc_type
        pipeline_iter_dir = pipeline_dir / "iterations" / iteration_name
        judge_out_dir = pipeline_iter_dir / "judge_eval"
        judge_out_dir.mkdir(parents=True, exist_ok=True)

        pdf_map: Dict[str, Path] = {}
        for case in cases:
            case_id = case["opaque_case_id"]
            pdf_path = pipeline_dir / "ground_truth" / "pdfs" / f"{case_id}.pdf"
            if not pdf_path.is_file():
                raise FileNotFoundError(f"PDF fixture for case '{case_id}' missing at {pdf_path}")
            pdf_map[case_id] = pdf_path

        ordered_pdf_paths = [pdf_map[cid] for cid in sorted(pdf_map.keys())]

        research_file = pipeline_dir / "research" / "research.json"
        if not research_file.is_file():
            raise FileNotFoundError(f"Missing research.json for {doc_type} at {research_file}")
        try:
            research_json = json.loads(research_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to parse research.json for {doc_type}: {exc}") from exc

        gt_specs = {c["opaque_case_id"]: c for c in cases}
        ordered_case_ids = sorted(pdf_map)
        pdf_hashes_by_case = {
            case_id: hashlib.sha256(pdf_map[case_id].read_bytes()).hexdigest()
            for case_id in ordered_case_ids
        }
        active_bundle = public_bundle or build_public_review_bundle(doc_type)
        worker_input_manifests = {}
        for case_id in ordered_case_ids:
            text_path = pdf_map[case_id].with_suffix(".txt")
            extracted_text = (
                text_path.read_text(encoding="utf-8", errors="replace")
                if text_path.is_file() and not text_path.is_symlink()
                else ""
            )
            worker_input_manifests[case_id] = build_worker_input_manifest(
                doc_type=doc_type,
                public_bundle=active_bundle,
                input_pdf_sha256=pdf_hashes_by_case[case_id],
                extracted_text=extracted_text,
                allowed_text_sha256=(
                    hashlib.sha256(text_path.read_bytes()).hexdigest()
                    if text_path.is_file() and not text_path.is_symlink()
                    else None
                ),
            )
        expected_manifest, expected_manifest_hash = build_judge_input_manifest(
            doc_type=doc_type,
            case_ids=ordered_case_ids,
            pdf_hashes_by_case=pdf_hashes_by_case,
            worker_reports=worker_reports,
            worker_input_manifests=worker_input_manifests,
            research_json=research_json,
            ground_truth_specs=gt_specs,
        )
        expected_prompt_hash = hashlib.sha256(
            _build_judge_prompt(
                doc_type=doc_type,
                case_ids=ordered_case_ids,
                worker_reports=worker_reports,
                worker_input_manifests=worker_input_manifests,
                research_json=research_json,
                ground_truth_specs=gt_specs,
                input_manifest_hash=expected_manifest_hash,
                prompt_contract_hash=expected_manifest[
                    "prompt_contract_hash"
                ],
            ).encode("utf-8")
        ).hexdigest()

        for candidate_filename in ("doc_type_eval.json", "judge_batch.json"):
            judge_out_file = judge_out_dir / candidate_filename
            if judge_out_file.is_file() and runner_fn is None:
                try:
                    data = json.loads(judge_out_file.read_text(encoding="utf-8"))
                    prov = data.get("_provenance", {})
                    artifact = {
                        key: value
                        for key, value in data.items()
                        if key != "_provenance"
                    }
                    validated = JudgeEvaluationBatch.model_validate(artifact)
                    if (
                        isinstance(data, dict)
                        and _has_current_sdk_provenance(
                            prov,
                            role="judge",
                            model="claude-opus-4.8",
                            effort="xhigh",
                            context_tier="long_context",
                            attachment_hashes=expected_manifest["pdf_hashes"],
                        )
                        and prov.get("input_manifest_hash")
                        == expected_manifest_hash
                        and prov.get("prompt_hash") == expected_prompt_hash
                        and prov.get("prompt_contract_hash")
                        == expected_manifest["prompt_contract_hash"]
                        and prov.get("case_ids")
                        == expected_manifest["case_ids"]
                        and prov.get("pdf_hashes")
                        == expected_manifest["pdf_hashes"]
                        and prov.get("worker_report_hashes")
                        == expected_manifest["worker_report_hashes"]
                        and prov.get("worker_input_manifest_hashes")
                        == expected_manifest["worker_input_manifest_hashes"]
                        and prov.get("public_bundle_hashes")
                        == expected_manifest["public_bundle_hashes"]
                        and prov.get("worker_prompt_hashes")
                        == expected_manifest["worker_prompt_hashes"]
                        and prov.get("research_hash")
                        == expected_manifest["research_hash"]
                        and prov.get("ground_truth_hash")
                        == expected_manifest["ground_truth_hash"]
                        and prov.get("model_config")
                        == expected_manifest["model_config"]
                        and prov.get("artifact_output_hash")
                        == _judge_artifact_hash(artifact)
                        and prov.get("provenance_digest")
                        == _judge_provenance_digest(prov)
                        and validated.doc_type == doc_type
                        and set(validated.case_evaluations)
                        == set(ordered_case_ids)
                    ):
                        logger.info(
                            "Reusing existing validated Judge evaluation for %s",
                            doc_type,
                        )
                        return data
                except Exception:
                    pass

        self.tracker.enter_judge()
        try:
            judge_batch = run_batched_document_judge(
                doc_type=doc_type,
                worker_reports=worker_reports,
                pdf_paths=ordered_pdf_paths,
                research_json=research_json,
                ground_truth_specs=gt_specs,
                public_bundle=active_bundle,
                runner_fn=runner_fn,
                output_dir=judge_out_dir,
            )
            return judge_batch
        finally:
            self.tracker.exit_judge()

    def run_doctype_eval_pass(
        self,
        doc_type: str,
        cases: List[Dict[str, Any]],
        iteration_name: str = "iter_00_baseline",
        custom_bundle: Optional[Dict[str, Any]] = None,
        runner_fn: Optional[Any] = None,
        max_concurrency: Optional[int] = None,
        max_worker_concurrency: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Run Workers with bounded concurrency and privileged batched Judge for a single document type."""
        pipeline_dir = self.pipelines_dir / doc_type
        pipeline_iter_dir = pipeline_dir / "iterations" / iteration_name
        if pipeline_iter_dir.exists():
            shutil.rmtree(pipeline_iter_dir, ignore_errors=True)

        worker_reports = self.run_doctype_workers_pass(
            doc_type=doc_type,
            cases=cases,
            iteration_name=iteration_name,
            custom_bundle=custom_bundle,
            runner_fn=runner_fn,
            max_concurrency=max_concurrency,
            max_worker_concurrency=max_worker_concurrency,
        )

        judge_batch = self.run_doctype_judge_pass(
            doc_type=doc_type,
            cases=cases,
            worker_reports=worker_reports,
            iteration_name=iteration_name,
            public_bundle=(
                custom_bundle or build_public_review_bundle(doc_type)
            ),
            runner_fn=runner_fn,
        )

        return worker_reports, judge_batch

    def run_baseline_workers_pass(
        self,
        runner_fn: Optional[Any] = None,
        iteration_name: str = "iter_00_baseline",
        require_all_23: bool = True,
        max_concurrency: Optional[int] = None,
        max_worker_concurrency: Optional[int] = None,
        custom_bundle: Optional[Any] = None,
        doc_types: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Run Stage 1 global Worker pass across all selected document types (up to 236 Workers) with a single global Worker pool."""
        eff_concurrency = _validate_concurrency(
            max_concurrency if max_concurrency is not None else (
                max_worker_concurrency if max_worker_concurrency is not None else self.max_concurrency
            )
        )

        target_doc_types = doc_types or self._discover_doc_types(require_all_23=require_all_23)
        if require_all_23 and len(target_doc_types) != 23:
            raise ValueError(f"Baseline Workers pass requires exactly 23 document types, discovered {len(target_doc_types)}")

        # Clear target iteration directories for all selected doc_types first
        for dt in target_doc_types:
            pipeline_dir = self.pipelines_dir / dt
            pipeline_iter_dir = pipeline_dir / "iterations" / iteration_name
            if pipeline_iter_dir.exists():
                shutil.rmtree(pipeline_iter_dir, ignore_errors=True)

        global_case_ids: set = set()
        all_tasks: List[Tuple[str, Dict[str, Any]]] = []
        cases_by_dt: Dict[str, List[Dict[str, Any]]] = {}
        worker_bundles_by_dt: Dict[str, Dict[str, Any]] = {}

        for dt in target_doc_types:
            cases = self._load_doc_type_cases(dt, global_case_ids=global_case_ids)
            cases_by_dt[dt] = cases
            provided_bundle = (
                custom_bundle.get(dt)
                if isinstance(custom_bundle, dict)
                else custom_bundle
            )
            worker_bundles_by_dt[dt] = (
                provided_bundle
                or build_public_review_bundle(
                    doc_type=dt,
                    corpus_db_path=self.corpus_db_path,
                )
            )
            for case in cases:
                all_tasks.append((dt, case))

        if require_all_23 and len(all_tasks) != 236:
            raise ValueError(f"Baseline Workers pass failed: expected 236 total worker cases, got {len(all_tasks)}")

        worker_reports_by_dt: Dict[str, Dict[str, Dict[str, Any]]] = {dt: {} for dt in target_doc_types}
        worker_errors_by_dt: Dict[str, Dict[str, Any]] = {dt: {} for dt in target_doc_types}

        def _execute_single_worker_task(dt: str, case: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
            cid = case["opaque_case_id"]
            pipeline_dir = self.pipelines_dir / dt
            worker_out_dir = pipeline_dir / "iterations" / iteration_name / "worker_reports"
            worker_out_dir.mkdir(parents=True, exist_ok=True)
            dt_bundle = worker_bundles_by_dt[dt]

            report_file = worker_out_dir / f"{cid}.json"
            if not report_file.is_file():
                report_file = worker_out_dir / f"case_{cid}.json"
            if report_file.is_file() and runner_fn is None:
                try:
                    data = json.loads(report_file.read_text(encoding="utf-8"))
                    reuse_manifest = _is_reusable_worker_report(
                        data,
                        pipeline_dir=pipeline_dir,
                        case=case,
                        doc_type=dt,
                        public_bundle=dt_bundle,
                    )
                    if reuse_manifest is not None:
                        _validate_answer_object(data)
                        check_answer_grounding(data, db_path=self.corpus_db_path)
                        _assert_answer_blindness_and_pii(
                            data,
                            pii_manifest=reuse_manifest,
                        )
                        logger.info("Reusing existing validated worker report for case %s in %s", cid, dt)
                        return dt, cid, data
                except Exception:
                    pass

            self.tracker.enter_worker()
            try:
                report = run_blind_worker_task(
                    opaque_case_id=cid,
                    doc_type=dt,
                    public_bundle=dt_bundle,
                    runner_fn=runner_fn,
                    pipeline_root=pipeline_dir,
                    output_dir=worker_out_dir,
                    corpus_db_path=self.corpus_db_path,
                )
                return dt, cid, report
            finally:
                self.tracker.exit_worker()

        with ThreadPoolExecutor(max_workers=eff_concurrency) as executor:
            future_to_task = {
                executor.submit(_execute_single_worker_task, dt, case): (dt, case["opaque_case_id"])
                for dt, case in all_tasks
            }
            for future in as_completed(future_to_task):
                dt, cid = future_to_task[future]
                try:
                    res_dt, res_cid, report = future.result()
                    worker_reports_by_dt[res_dt][res_cid] = report
                except Exception as exc:
                    logger.error("Worker task failed for case %s in %s: %s", cid, dt, exc)
                    worker_errors_by_dt[dt][cid] = str(exc)

        has_errors = False
        for dt in target_doc_types:
            errs = worker_errors_by_dt[dt]
            reps = worker_reports_by_dt[dt]
            exp_count = len(cases_by_dt[dt])
            if errs or len(reps) != exp_count:
                has_errors = True
                error_data = {
                    "doc_type": dt,
                    "iteration": iteration_name,
                    "expected_cases": exp_count,
                    "successful_reports": len(reps),
                    "errors": errs,
                    "timestamp": _utc_now(),
                }
                pipeline_iter_dir = self.pipelines_dir / dt / "iterations" / iteration_name
                pipeline_iter_dir.mkdir(parents=True, exist_ok=True)
                (pipeline_iter_dir / "worker_error.json").write_text(
                    json.dumps(error_data, indent=2), encoding="utf-8"
                )

        if has_errors:
            all_err_summary = {dt: errs for dt, errs in worker_errors_by_dt.items() if errs}
            raise RuntimeError(
                f"Worker pass failed closed across doc types: {all_err_summary}"
            )

        sorted_reports_by_dt = {
            dt: {cid: worker_reports_by_dt[dt][cid] for cid in sorted(worker_reports_by_dt[dt].keys())}
            for dt in target_doc_types
        }
        logger.info("Successfully executed Stage 1 Worker pass across %d document types (%d reports).", len(target_doc_types), len(all_tasks))
        return sorted_reports_by_dt

    def run_baseline_judges_pass(
        self,
        all_worker_reports: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
        runner_fn: Optional[Any] = None,
        iteration_name: str = "iter_00_baseline",
        require_all_23: bool = True,
        max_concurrency: Optional[int] = None,
        doc_types: Optional[List[str]] = None,
        public_bundles: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Run Stage 2 global Judge pass across all selected document types (up to 23 Judges) using a single global Judge pool."""
        eff_concurrency = _validate_concurrency(
            max_concurrency if max_concurrency is not None else self.max_concurrency
        )

        iter_dir = self.iterations_dir / iteration_name
        iter_dir.mkdir(parents=True, exist_ok=True)
        (self.iterations_dir / "loop_summary.json").unlink(missing_ok=True)

        target_doc_types = doc_types or self._discover_doc_types(require_all_23=require_all_23)
        if require_all_23 and len(target_doc_types) != 23:
            raise ValueError(f"Baseline Judges pass requires exactly 23 document types, discovered {len(target_doc_types)}")

        global_case_ids: set = set()
        cases_by_dt: Dict[str, List[Dict[str, Any]]] = {}
        for dt in target_doc_types:
            cases_by_dt[dt] = self._load_doc_type_cases(dt, global_case_ids=global_case_ids)

        judge_results_by_dt: Dict[str, Dict[str, Any]] = {}
        judge_errors_by_dt: Dict[str, Any] = {}

        def _execute_single_judge_task(dt: str) -> Tuple[str, Dict[str, Any]]:
            cases = cases_by_dt[dt]
            w_reports = (all_worker_reports or {}).get(dt)
            if w_reports is None:
                pipeline_dir = self.pipelines_dir / dt
                worker_out_dir = pipeline_dir / "iterations" / iteration_name / "worker_reports"
                w_reports = {}
                for case in cases:
                    cid = case["opaque_case_id"]
                    report_file = worker_out_dir / f"{cid}.json"
                    if not report_file.is_file():
                        alt = worker_out_dir / f"case_{cid}.json"
                        report_file = alt if alt.is_file() else report_file
                    if not report_file.is_file():
                        raise FileNotFoundError(f"Missing worker report for case '{cid}' in {dt} at {report_file}")
                    w_reports[cid] = json.loads(report_file.read_text(encoding="utf-8"))

            j_batch = self.run_doctype_judge_pass(
                doc_type=dt,
                cases=cases,
                worker_reports=w_reports,
                iteration_name=iteration_name,
                public_bundle=(
                    public_bundles.get(dt)
                    if public_bundles is not None
                    else None
                ),
                runner_fn=runner_fn,
            )
            return dt, j_batch

        with ThreadPoolExecutor(max_workers=eff_concurrency) as executor:
            future_to_dt = {executor.submit(_execute_single_judge_task, dt): dt for dt in target_doc_types}
            for future in as_completed(future_to_dt):
                dt = future_to_dt[future]
                try:
                    res_dt, j_batch = future.result()
                    judge_results_by_dt[res_dt] = j_batch
                except Exception as exc:
                    logger.error("Judge task failed for %s: %s", dt, exc)
                    judge_errors_by_dt[dt] = str(exc)

        if judge_errors_by_dt:
            for dt, err_msg in judge_errors_by_dt.items():
                pipeline_iter_dir = self.pipelines_dir / dt / "iterations" / iteration_name
                pipeline_iter_dir.mkdir(parents=True, exist_ok=True)
                error_data = {
                    "doc_type": dt,
                    "iteration": iteration_name,
                    "error": err_msg,
                    "timestamp": _utc_now(),
                }
                (pipeline_iter_dir / "judge_error.json").write_text(
                    json.dumps(error_data, indent=2), encoding="utf-8"
                )
            raise RuntimeError(f"Judge pass failed closed for doc types: {list(judge_errors_by_dt.keys())}")

        baseline_by_doc_type = {}
        total_cases = 0

        for dt in sorted(target_doc_types):
            cases = cases_by_dt[dt]
            train_cases, holdout_cases = split_doc_type_cases(cases, doc_type=dt)
            holdout_ids = {c["opaque_case_id"] for c in holdout_cases}

            judge_batch = judge_results_by_dt[dt]
            case_evals = judge_batch.get("case_evaluations", {})
            train_scores = [c_eval for cid, c_eval in case_evals.items() if cid not in holdout_ids]
            holdout_scores = [c_eval for cid, c_eval in case_evals.items() if cid in holdout_ids]

            sealed_findings = seal_holdout_findings(judge_batch, holdout_case_ids=holdout_ids)

            baseline_by_doc_type[dt] = {
                "doc_type": dt,
                "total_cases": len(cases),
                "train_count": len(train_cases),
                "holdout_count": len(holdout_cases),
                "judge_batch": judge_batch,
                "sealed_findings": sealed_findings,
                "train_evals": train_scores,
                "holdout_evals": holdout_scores,
            }
            total_cases += len(cases)

        if require_all_23:
            if len(baseline_by_doc_type) != 23:
                raise ValueError(f"Baseline Judges pass failed: expected 23 document types, got {len(baseline_by_doc_type)}")
            if total_cases != 236:
                raise ValueError(f"Baseline Judges pass failed: expected 236 total cases, got {total_cases}")

        all_train_evals = [e for dt_data in baseline_by_doc_type.values() for e in dt_data["train_evals"]]
        all_holdout_evals = [e for dt_data in baseline_by_doc_type.values() for e in dt_data["holdout_evals"]]

        report = {
            "timestamp": _utc_now(),
            "iteration_name": iteration_name,
            "total_doc_types": len(baseline_by_doc_type),
            "total_cases": total_cases,
            "doc_types": baseline_by_doc_type,
            "train_metrics": _mean_metrics(all_train_evals),
            "holdout_metrics": _mean_metrics(all_holdout_evals),
        }

        (iter_dir / "baseline_summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (self.iterations_dir / "loop_summary.json").write_text(
            json.dumps({"timestamp": _utc_now(), "baseline": report}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Successfully executed Stage 2 Judge pass: %d document types, %d judge evaluations.", len(target_doc_types), len(target_doc_types))
        return report

    def run_baseline_pass(
        self,
        runner_fn: Optional[Any] = None,
        iteration_name: str = "iter_00_baseline",
        require_all_23: bool = True,
        max_concurrency: Optional[int] = None,
        max_worker_concurrency: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run baseline pass across all 23 document types (236 Workers, 23 Judges) using two-stage global pools."""
        eff_concurrency = _validate_concurrency(
            max_concurrency if max_concurrency is not None else (
                max_worker_concurrency if max_worker_concurrency is not None else self.max_concurrency
            )
        )
        iter_dir = self.iterations_dir / iteration_name
        if iter_dir.exists():
            shutil.rmtree(iter_dir, ignore_errors=True)
        iter_dir.mkdir(parents=True, exist_ok=True)
        (self.iterations_dir / "loop_summary.json").unlink(missing_ok=True)

        all_worker_reports = self.run_baseline_workers_pass(
            runner_fn=runner_fn,
            iteration_name=iteration_name,
            require_all_23=require_all_23,
            max_concurrency=eff_concurrency,
        )
        return self.run_baseline_judges_pass(
            all_worker_reports=all_worker_reports,
            runner_fn=runner_fn,
            iteration_name=iteration_name,
            require_all_23=require_all_23,
            max_concurrency=eff_concurrency,
        )

    def run_optimization_iterations(
        self,
        baseline_report: Dict[str, Any],
        max_iterations: int = 3,
        runner_fn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run up to max_iterations optimization loops (D-14..D-19)."""
        current_baseline = baseline_report

        for iter_idx in range(1, max_iterations + 1):
            iter_dir = self.iterations_dir / f"iter_{iter_idx}"
            if iter_dir.exists():
                shutil.rmtree(iter_dir, ignore_errors=True)
            iter_dir.mkdir(parents=True, exist_ok=True)
            accepted_in_iter = 0

            doc_types_data = current_baseline.get("doc_types", {})

            # 1. Execute per-doc optimizer proposals
            for dt, dt_data in doc_types_data.items():
                sealed_findings = dt_data["sealed_findings"]
                findings = sealed_findings.get("findings", [])

                if not findings:
                    continue

                candidate_res: Optional[Dict[str, Any]] = None
                try:
                    candidate_res = run_candidate_optimization_pass(
                        doc_type=dt,
                        training_findings=sealed_findings,
                        runner_fn=runner_fn,
                        proposal_sandbox_root=iter_dir / "proposals",
                    )

                    if not candidate_res["is_valid"]:
                        self.rejected_patches.append({
                            "iteration": iter_idx,
                            "decision": "rejected",
                            "proposal_completed": True,
                            "doc_type": dt,
                            "target_file": candidate_res["target_file"],
                            "reasons": candidate_res["rejection_reasons"],
                            "candidate_id": candidate_res["candidate_id"],
                            "optimizer_provenance": (
                                _publishable_optimizer_provenance(
                                    candidate_res
                                )
                            ),
                        })
                        continue

                    candidate_content = candidate_res["candidate_content"]
                    candidate_bundle = build_public_review_bundle(
                        doc_type=dt,
                        corpus_db_path=self.corpus_db_path,
                        override_skill_content=candidate_content,
                    )

                    cases = self._load_doc_type_cases(dt)
                    train_cases, holdout_cases = split_doc_type_cases(cases, doc_type=dt)
                    holdout_ids = {c["opaque_case_id"] for c in holdout_cases}

                    cand_worker_reports, cand_judge_batch = self.run_doctype_eval_pass(
                        doc_type=dt,
                        cases=cases,
                        iteration_name=f"iter_{iter_idx}_cand_{dt}",
                        custom_bundle=candidate_bundle,
                        runner_fn=runner_fn,
                    )

                    cand_evals = cand_judge_batch.get("case_evaluations", {})
                    b_train_evals = dt_data["train_evals"]
                    b_holdout_evals = dt_data["holdout_evals"]

                    c_train_evals = [v for cid, v in cand_evals.items() if cid not in holdout_ids]
                    c_holdout_evals = [v for cid, v in cand_evals.items() if cid in holdout_ids]

                    b_tr_m = _mean_metrics(b_train_evals)
                    b_ho_m = _mean_metrics(b_holdout_evals)
                    c_tr_m = _mean_metrics(c_train_evals)
                    c_ho_m = _mean_metrics(c_holdout_evals)

                    is_accepted = evaluate_candidate_patch(b_tr_m, b_ho_m, c_tr_m, c_ho_m)

                    if is_accepted:
                        target_path = _REPO_ROOT / candidate_res["target_file"]
                        accepted_rec = {
                            "iteration": iter_idx,
                            "decision": "accepted",
                            "proposal_completed": True,
                            "doc_type": dt,
                            "target_file": candidate_res["target_file"],
                            "candidate_id": candidate_res["candidate_id"],
                            "baseline_train_metrics": b_tr_m,
                            "baseline_holdout_metrics": b_ho_m,
                            "candidate_train_metrics": c_tr_m,
                            "candidate_holdout_metrics": c_ho_m,
                            "optimizer_provenance": (
                                _publishable_optimizer_provenance(
                                    candidate_res
                                )
                            ),
                        }
                        apply_patch_atomically(target_path, candidate_content)
                        self.accepted_patches.append(accepted_rec)
                        accepted_in_iter += 1

                        dt_data["train_evals"] = c_train_evals
                        dt_data["holdout_evals"] = c_holdout_evals
                        dt_data["sealed_findings"] = seal_holdout_findings(cand_judge_batch, holdout_case_ids=holdout_ids)
                    else:
                        self.rejected_patches.append({
                            "iteration": iter_idx,
                            "decision": "rejected",
                            "proposal_completed": True,
                            "doc_type": dt,
                            "target_file": candidate_res["target_file"],
                            "candidate_id": candidate_res["candidate_id"],
                            "baseline_train_metrics": b_tr_m,
                            "baseline_holdout_metrics": b_ho_m,
                            "candidate_train_metrics": c_tr_m,
                            "candidate_holdout_metrics": c_ho_m,
                            "optimizer_provenance": (
                                _publishable_optimizer_provenance(
                                    candidate_res
                                )
                            ),
                            "reasons": ["Holdout score regressed or training score did not improve"],
                        })
                except Exception as exc:
                    logger.error("Per-doc candidate optimization/evaluation failed for %s: %s", dt, exc)
                    self.blocked_patches.append(
                        _blocked_patch_record(
                            iteration=iter_idx,
                            doc_type=dt,
                            reason=(
                                "Candidate evaluation infrastructure failed"
                                if candidate_res is not None
                                else "Optimizer proposal execution failed"
                            ),
                            candidate_result=candidate_res,
                        )
                    )

            # 2. Execute 1 shared Gemini optimizer proposal from aggregate findings
            all_findings = []
            all_training_evaluations: Dict[str, Dict[str, Any]] = {}
            for dt, dt_data in doc_types_data.items():
                sealed = dt_data["sealed_findings"]
                all_findings.extend(sealed.get("findings", []))
                all_training_evaluations.update(
                    sealed.get("case_evaluations", {})
                )

            if all_findings:
                commitments = [
                    {
                        "doc_type": dt,
                        **dt_data["sealed_findings"]["holdout_commitment"],
                    }
                    for dt, dt_data in sorted(doc_types_data.items())
                    if "holdout_commitment" in dt_data["sealed_findings"]
                ]
                aggregate_sealed = {
                    "doc_type": "shared",
                    "case_evaluations": all_training_evaluations,
                    "findings": all_findings,
                    "holdout_commitment": {
                        "count": sum(item["count"] for item in commitments),
                        "hash": hashlib.sha256(
                            json.dumps(
                                commitments,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest(),
                    },
                }

                shared_res: Optional[Dict[str, Any]] = None
                try:
                    shared_res = run_candidate_optimization_pass(
                        doc_type=None,
                        training_findings=aggregate_sealed,
                        target_file="skills/pdf/SKILL.md",
                        runner_fn=runner_fn,
                        proposal_sandbox_root=iter_dir / "proposals",
                    )

                    if shared_res["is_valid"] and shared_res["target_file"] in ("AGENTS.md", "skills/pdf/SKILL.md"):
                        all_c_train_evals = []
                        all_c_holdout_evals = []
                        all_b_train_evals = []
                        all_b_holdout_evals = []

                        shared_candidate_content = shared_res["candidate_content"]

                        s_bundles = {
                            dt: build_public_review_bundle(
                                doc_type=dt,
                                corpus_db_path=self.corpus_db_path,
                                override_shared_content=shared_candidate_content,
                            )
                            for dt in doc_types_data.keys()
                        }

                        s_worker_reports = self.run_baseline_workers_pass(
                            runner_fn=runner_fn,
                            iteration_name=f"iter_{iter_idx}_shared_cand",
                            require_all_23=False,
                            custom_bundle=s_bundles,
                            doc_types=list(doc_types_data.keys()),
                        )

                        s_baseline_report = self.run_baseline_judges_pass(
                            all_worker_reports=s_worker_reports,
                            runner_fn=runner_fn,
                            iteration_name=f"iter_{iter_idx}_shared_cand",
                            require_all_23=False,
                            doc_types=list(doc_types_data.keys()),
                            public_bundles=s_bundles,
                        )

                        for dt, dt_data in s_baseline_report.get("doc_types", {}).items():
                            cases = self._load_doc_type_cases(dt)
                            train_cases, holdout_cases = split_doc_type_cases(cases, doc_type=dt)
                            holdout_ids = {c["opaque_case_id"] for c in holdout_cases}

                            case_evals = dt_data.get("judge_batch", {}).get("case_evaluations", {})
                            all_b_train_evals.extend(doc_types_data[dt]["train_evals"])
                            all_b_holdout_evals.extend(doc_types_data[dt]["holdout_evals"])
                            all_c_train_evals.extend([v for cid, v in case_evals.items() if cid not in holdout_ids])
                            all_c_holdout_evals.extend([v for cid, v in case_evals.items() if cid in holdout_ids])

                        sb_tr_m = _mean_metrics(all_b_train_evals)
                        sb_ho_m = _mean_metrics(all_b_holdout_evals)
                        sc_tr_m = _mean_metrics(all_c_train_evals)
                        sc_ho_m = _mean_metrics(all_c_holdout_evals)

                        shared_accepted = evaluate_candidate_patch(sb_tr_m, sb_ho_m, sc_tr_m, sc_ho_m)

                        if shared_accepted:
                            target_path = _REPO_ROOT / shared_res["target_file"]
                            accepted_rec = {
                                "iteration": iter_idx,
                                "decision": "accepted",
                                "proposal_completed": True,
                                "doc_type": "shared",
                                "target_file": shared_res["target_file"],
                                "candidate_id": shared_res["candidate_id"],
                                "baseline_train_metrics": sb_tr_m,
                                "baseline_holdout_metrics": sb_ho_m,
                                "candidate_train_metrics": sc_tr_m,
                                "candidate_holdout_metrics": sc_ho_m,
                                "optimizer_provenance": (
                                    _publishable_optimizer_provenance(
                                        shared_res
                                    )
                                ),
                            }
                            apply_patch_atomically(
                                target_path,
                                shared_res["candidate_content"],
                            )
                            self.accepted_patches.append(accepted_rec)
                            accepted_in_iter += 1
                        else:
                            self.rejected_patches.append({
                                "iteration": iter_idx,
                                "decision": "rejected",
                                "proposal_completed": True,
                                "doc_type": "shared",
                                "target_file": shared_res["target_file"],
                                "candidate_id": shared_res["candidate_id"],
                                "baseline_train_metrics": sb_tr_m,
                                "baseline_holdout_metrics": sb_ho_m,
                                "candidate_train_metrics": sc_tr_m,
                                "candidate_holdout_metrics": sc_ho_m,
                                "optimizer_provenance": (
                                    _publishable_optimizer_provenance(
                                        shared_res
                                    )
                                ),
                                "reasons": ["Shared patch regressed holdout or failed train improvement"],
                            })
                    elif not shared_res["is_valid"]:
                        self.rejected_patches.append({
                            "iteration": iter_idx,
                            "decision": "rejected",
                            "proposal_completed": True,
                            "doc_type": "shared",
                            "target_file": shared_res["target_file"],
                            "reasons": shared_res["rejection_reasons"],
                            "candidate_id": shared_res["candidate_id"],
                            "optimizer_provenance": (
                                _publishable_optimizer_provenance(
                                    shared_res
                                )
                            ),
                        })
                    else:
                        self.rejected_patches.append({
                            "iteration": iter_idx,
                            "decision": "rejected",
                            "proposal_completed": True,
                            "doc_type": "shared",
                            "target_file": shared_res.get("target_file"),
                            "candidate_id": shared_res.get("candidate_id"),
                            "optimizer_provenance": (
                                _publishable_optimizer_provenance(
                                    shared_res
                                )
                            ),
                            "reasons": ["Shared optimizer target is not publishable"],
                        })
                except Exception as exc:
                    logger.error("Shared candidate optimization/evaluation failed: %s", exc)
                    self.blocked_patches.append(
                        _blocked_patch_record(
                            iteration=iter_idx,
                            doc_type="shared",
                            reason=(
                                "Shared candidate evaluation infrastructure failed"
                                if shared_res is not None
                                else "Shared optimizer proposal execution failed"
                            ),
                            candidate_result=shared_res,
                        )
                    )

            # Save iteration patch audit trails
            (iter_dir / "accepted_patches.json").write_text(
                json.dumps(self.accepted_patches, indent=2), encoding="utf-8"
            )
            (iter_dir / "rejected_patches.json").write_text(
                json.dumps(self.rejected_patches, indent=2), encoding="utf-8"
            )
            (iter_dir / "blocked_patches.json").write_text(
                json.dumps(self.blocked_patches, indent=2), encoding="utf-8"
            )

            if accepted_in_iter == 0:
                logger.info("Loop converged at iteration %d: no accepted non-regressing patches", iter_idx)
                break

        opt_res = {
            "accepted_patches": self.accepted_patches,
            "rejected_patches": self.rejected_patches,
            "blocked_patches": self.blocked_patches,
        }

        loop_summary_file = self.iterations_dir / "loop_summary.json"
        summary_data = {}
        if loop_summary_file.is_file():
            try:
                summary_data = json.loads(loop_summary_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        summary_data["optimization"] = opt_res
        loop_summary_file.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")

        return opt_res

    def run_final_pass(
        self,
        runner_fn: Optional[Any] = None,
        iteration_name: str = "final_pass",
        require_all_23: bool = True,
        max_concurrency: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run final pass across all 236 Worker sessions and 23 Judges using two-stage global pools."""
        eff_concurrency = _validate_concurrency(
            max_concurrency if max_concurrency is not None else self.max_concurrency
        )
        iter_dir = self.iterations_dir / iteration_name
        if iter_dir.exists():
            shutil.rmtree(iter_dir, ignore_errors=True)
        iter_dir.mkdir(parents=True, exist_ok=True)

        all_worker_reports = self.run_baseline_workers_pass(
            runner_fn=runner_fn,
            iteration_name=iteration_name,
            require_all_23=require_all_23,
            max_concurrency=eff_concurrency,
        )

        baseline_report = self.run_baseline_judges_pass(
            all_worker_reports=all_worker_reports,
            runner_fn=runner_fn,
            iteration_name=iteration_name,
            require_all_23=require_all_23,
            max_concurrency=eff_concurrency,
        )

        final_by_doc_type = baseline_report.get("doc_types", {})
        report = {
            "timestamp": _utc_now(),
            "iteration_name": iteration_name,
            "total_doc_types": len(final_by_doc_type),
            "total_cases": baseline_report.get("total_cases", 0),
            "doc_types": final_by_doc_type,
            "accepted_patches": self.accepted_patches,
            "rejected_patches": self.rejected_patches,
            "blocked_patches": self.blocked_patches,
        }

        (iter_dir / "final_summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        loop_summary_file = self.iterations_dir / "loop_summary.json"
        summary_data = {}
        if loop_summary_file.is_file():
            try:
                summary_data = json.loads(loop_summary_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        summary_data["final_pass"] = report
        loop_summary_file.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")

        return report

    def run_full_improvement_loop(
        self, max_iterations: int = 3, runner_fn: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Run end-to-end baseline, optimization iterations, and final full pass."""
        baseline = self.run_baseline_pass(runner_fn=runner_fn)
        opt = self.run_optimization_iterations(baseline, max_iterations=max_iterations, runner_fn=runner_fn)
        final = self.run_final_pass(runner_fn=runner_fn)

        summary = {
            "timestamp": _utc_now(),
            "baseline": baseline,
            "optimization": opt,
            "final_pass": final,
        }
        (self.iterations_dir / "loop_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return summary


def main(argv: Optional[List[str]] = None) -> int:
    """Delegate live loop modes; retain legacy methods for injected non-live tests."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Loop Orchestrator for Phase 74 Agent Self-Improvement")
    parser.add_argument(
        "--mode",
        choices=["baseline-workers", "baseline-judges", "baseline", "full-loop", "optimize", "final-pass"],
        default="baseline",
        help="Execution mode (default: baseline)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Max optimization iterations for full-loop (default: 3)",
    )
    parser.add_argument(
        "--concurrency",
        "--max-concurrency",
        type=int,
        default=DEFAULT_MAX_CONCURRENCY,
        dest="max_concurrency",
        help="Max worker/judge concurrency (1..5, default: 5)",
    )

    args = parser.parse_args(argv)
    if args.mode in {
        "baseline-workers",
        "baseline-judges",
        "baseline",
        "optimize",
        "final-pass",
        "full-loop",
    }:
        from crawler.eval.sdk_pipeline_orchestrator import (
            SdkPipelineOrchestrator,
        )

        SdkPipelineOrchestrator().run()
        return 0
    raise AssertionError(f"Unhandled mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
