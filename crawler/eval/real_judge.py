"""Live Claude Opus Judge evaluation harness."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from crawler.eval.pipeline_judge import (
    JudgeExecutionError,
    run_batched_document_judge,
    run_pipeline_judge_for_doctype,
)
from crawler.eval.real_worker import _write_json

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GROUND_TRUTH_DIR = _REPO_ROOT / "crawler" / "eval" / "ground_truth"
_REPORTS_DIR = _REPO_ROOT / "reports"
_JUDGE_MODEL = "claude-opus-4.8"
_JUDGE_EFFORT = "xhigh"
_CONTEXT_TIER = "long_context"

logger = logging.getLogger(__name__)

CATEGORY_GROUPS: Dict[str, Dict[str, Any]] = {
    "a": {
        "name": "Core Identity & Language",
        "doc_types": [
            "passport",
            "digital_photo",
            "language_test",
            "certified_translation",
            "proof_of_other_name",
        ],
    },
    "b": {
        "name": "Education & Work Experience",
        "doc_types": [
            "educational_credential_assessment",
            "proof_of_studies",
            "employment_reference_letter",
            "written_job_offer_lmia",
            "certificate_of_qualification",
        ],
    },
    "c": {
        "name": "Financial, Medical & Police",
        "doc_types": [
            "birth_certificate",
            "marriage_certificate",
            "divorce_certificate",
            "medical_examination",
            "police_certificate",
            "proof_of_funds",
        ],
    },
    "d": {
        "name": "Legal Forms, Relationships & LoE",
        "doc_types": [
            "statutory_declaration_common_law",
            "death_certificate",
            "adoption_certificate",
            "use_of_representative",
            "relative_in_canada",
            "authority_to_release_info",
            "letter_of_explanation",
        ],
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def judge_real_worker_output(
    case_id: str,
    *,
    force_worker: bool = False,
) -> Dict[str, Any]:
    """Single-case judge entrypoint.

    DISABLED per JUDGE_IMPROVE-01. Evaluator MUST use batched per-document Judge execution.
    """
    raise NotImplementedError(
        "Single-case judge entrypoint disabled per JUDGE_IMPROVE-01. Use run_batched_document_judge."
    )


def run_category_judge(
    category_key: str,
    *,
    case_ids: Optional[Iterable[str]] = None,
    force_worker: bool = False,
    runner_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run batched live Judge calls for a category group and persist structured report."""
    key = category_key.lower()
    group = CATEGORY_GROUPS.get(key)
    if group is None:
        raise ValueError(f"Unknown category group '{category_key}'")

    doc_types = group["doc_types"]
    doctype_results: Dict[str, Any] = {}

    for dt in doc_types:
        try:
            batch_eval = run_pipeline_judge_for_doctype(dt, runner_fn=runner_fn)
            doctype_results[dt] = batch_eval
        except Exception as exc:
            logger.error("Batched evaluation failed for document type %s: %s", dt, exc)
            doctype_results[dt] = {
                "doc_type": dt,
                "error": str(exc),
                "passed": False,
            }

    report = {
        "judge": "Batched Privileged LLM Judge",
        "judge_model": _JUDGE_MODEL,
        "judge_effort": _JUDGE_EFFORT,
        "judge_context": _CONTEXT_TIER,
        "category_key": key.upper(),
        "category_name": group["name"],
        "timestamp": _utc_now(),
        "doc_types": doctype_results,
    }

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(_REPORTS_DIR / f"judge_group_{key}_report.json", report)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run live Claude Judge evaluations.")
    parser.add_argument(
        "--category",
        choices=sorted(CATEGORY_GROUPS),
        action="append",
        help="Category to evaluate; may be repeated (default: all).",
    )
    args = parser.parse_args(argv)

    all_pass = True
    for key in args.category or sorted(CATEGORY_GROUPS):
        report = run_category_judge(key)
        print(f"Category {report['category_key']} ({report['category_name']}): evaluated {len(report['doc_types'])} doc types.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
