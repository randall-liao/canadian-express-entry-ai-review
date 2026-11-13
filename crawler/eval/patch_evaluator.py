"""Allowlist Patch Scanner and Candidate Regression Gate (D-15..D-18).

Validates candidate prompt/skill patch proposals against allowlists, forbidden patterns,
PII leaks, and diff bounds, and evaluates train improvement vs holdout regression.
"""

from __future__ import annotations

import difflib
import json
import logging
import math
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Tuple

from crawler.eval.public_bundle import (
    DOC_TYPE_TO_SKILL,
    find_public_content_leaks,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Strict Allowlisted Target Files for Skill/Prompt Patches
_ALLOWLISTED_SHARED_TARGETS = {"AGENTS.md", "skills/pdf/SKILL.md"}
_DOC_SKILL_PATTERN = re.compile(r"^skills/document-agents/([a-z0-9_-]+)\.md$")

# Forbidden Case ID and Internal Key Patterns
_CASE_ID_REGEX = re.compile(r"\b(case_\d+|opaque_case_\w+|val_[vs]\d+|def_[vs]\d+|case_001|case_002)\b", re.IGNORECASE)
_GROUND_TRUTH_REGEX = re.compile(r"\b(ground_truth/|research\.json|research/|expected_verdict|injected_defects|source_failure_id)\b", re.IGNORECASE)

# Forbidden PII / Applicant Sentinels
_PII_SENTINELS = (
    "Jane Synthetic",
    "John Synthetic",
    "Jane Doe",
    "John Doe",
    "X99999999",
    "Y88888888",
)
_SIN_REGEX = re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{3}\b")

# Safety & Grounding Weakening Patterns
_SAFETY_WEAKENING_REGEX = re.compile(
    r"\b(ignore grounding|skip pii|bypass validation|disable checks|allow ungrounded|override safety)\b",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


def validate_target_allowlist(
    target_relpath: str,
    doc_type: Optional[str] = None,
) -> Tuple[bool, List[str], str]:
    """Validate and normalize a repository-relative optimizer target."""
    reasons: List[str] = []
    if not isinstance(target_relpath, str) or not target_relpath.strip():
        return False, ["Target file path is empty"], ""

    raw_target = target_relpath.replace("\\", "/")
    path = PurePosixPath(raw_target)
    if path.is_absolute() or re.match(r"^[A-Za-z]:/", raw_target):
        reasons.append(f"Target file '{target_relpath}' must not be absolute")
    if ".." in path.parts:
        reasons.append(f"Target file '{target_relpath}' contains path traversal")

    norm_target = path.as_posix()
    target_leaks = find_public_content_leaks(norm_target)
    if target_leaks:
        reasons.extend(
            f"Target file contains forbidden privileged content: {leak}"
            for leak in target_leaks
        )
    is_shared = norm_target in _ALLOWLISTED_SHARED_TARGETS
    if doc_type:
        expected_stem = DOC_TYPE_TO_SKILL.get(doc_type, doc_type.replace("_", "-"))
        expected_target = f"skills/document-agents/{expected_stem}.md"
        if norm_target != expected_target and not is_shared:
            reasons.append(
                f"Target file '{norm_target}' does not match expected canonical path "
                f"'{expected_target}' for doc_type '{doc_type}'"
            )
    elif not is_shared and not _DOC_SKILL_PATTERN.fullmatch(norm_target):
        reasons.append(f"Target file '{norm_target}' is not in patch allowlist")
    return not reasons, reasons, norm_target


def validate_patch_allowlist(
    patch_content: str,
    target_relpath: str,
    doc_type: Optional[str] = None,
    current_content: Optional[str] = None,
    forbidden_private_texts: Iterable[str] = (),
) -> Tuple[bool, List[str]]:
    """Validate candidate patch content and target file against allowlist rules (D-18).

    Rejects:
    - Non-allowlisted target files or wrong doc_type canonical skill mapping
    - Case IDs, ground-truth paths, research paths
    - Synthetic applicant names / PII values
    - Safety or grounding rule weakenings
    - Control/binary characters or unclosed code fences
    - Excessive diff size or diff change ratio (>40%)
    """
    reasons: List[str] = []
    target_ok, target_reasons, norm_target = validate_target_allowlist(
        target_relpath, doc_type
    )
    reasons.extend(target_reasons)

    if not patch_content or not patch_content.strip():
        reasons.append("Patch content is empty")
        return False, reasons

    # Bounds check
    if len(patch_content) > 150_000:
        reasons.append("Patch size exceeds maximum allowed length (150KB)")

    # 2. Binary / Control Characters Check
    if any(ord(c) < 32 and c not in "\n\r\t" for c in patch_content):
        reasons.append("Patch contains forbidden control or binary characters")

    # 3. Diff Bounds Check (Changed lines and change ratio)
    if current_content is None and target_ok:
        target_path = _REPO_ROOT / norm_target
        if target_path.is_file():
            try:
                current_content = target_path.read_text(encoding="utf-8")
            except Exception:
                current_content = None

    if current_content is not None:
        curr_lines = current_content.splitlines()
        patch_lines = patch_content.splitlines()
        diff = list(difflib.unified_diff(curr_lines, patch_lines, lineterm=""))
        changed_lines = sum(
            1 for line in diff
            if (line.startswith("+") or line.startswith("-"))
            and not line.startswith("+++") and not line.startswith("---")
        )
        if changed_lines > 120:
            reasons.append(f"Patch changes too many lines ({changed_lines} > 120 max allowed)")

        diff_ratio = changed_lines / max(len(curr_lines), 1)
        if diff_ratio > 0.40:
            reasons.append(f"Patch line change ratio ({diff_ratio:.2f}) exceeds 40% threshold")

    # 4. Case IDs & Internal Secrets Check
    if _CASE_ID_REGEX.search(patch_content):
        reasons.append("Patch contains forbidden literal case ID pattern")

    if _GROUND_TRUTH_REGEX.search(patch_content):
        reasons.append("Patch contains forbidden ground-truth or research reference")

    public_leaks = find_public_content_leaks(
        patch_content,
        forbidden_private_texts=forbidden_private_texts,
    )
    if public_leaks:
        reasons.extend(
            f"Patch contains forbidden privileged content: {leak}"
            for leak in public_leaks
        )

    # 5. PII & Applicant Sentinels Check
    for sentinel in _PII_SENTINELS:
        if sentinel.lower() in patch_content.lower():
            reasons.append(f"Patch contains forbidden applicant PII sentinel '{sentinel}'")

    if _SIN_REGEX.search(patch_content):
        reasons.append("Patch contains forbidden Social Insurance Number (SIN) pattern")

    # 6. Safety & Grounding Weakening Check
    if _SAFETY_WEAKENING_REGEX.search(patch_content):
        reasons.append("Patch contains forbidden safety or grounding weakening rule")

    # 7. Basic Markdown Structure Check
    fences = len(re.findall(r"^```", patch_content, re.MULTILINE))
    if fences % 2 != 0:
        reasons.append("Patch contains malformed Markdown (unclosed code fence)")

    is_valid = len(reasons) == 0
    return is_valid, reasons


def evaluate_candidate_patch(
    baseline_train_metrics: Dict[str, float],
    baseline_holdout_metrics: Dict[str, float],
    candidate_train_metrics: Dict[str, float],
    candidate_holdout_metrics: Dict[str, float],
) -> bool:
    """Evaluate candidate patch performance against baseline (D-17).

    Accept IF AND ONLY IF:
    - All 5 required finite dimensions + overall_score are present and finite numbers
    - Targeted training overall score improves (candidate_train > baseline_train)
    - Zero regression in training safety dimensions (grounding, citation, PII, blindness)
    - ZERO holdout dimension regresses across all 5 dimensions
    """
    required_dims = [
        "grounding_accuracy",
        "citation_exactness",
        "defect_recall",
        "pii_containment",
        "blind_input_compliance",
    ]

    # Validate metric structures and finite float values
    all_metrics = [
        ("baseline_train", baseline_train_metrics),
        ("baseline_holdout", baseline_holdout_metrics),
        ("candidate_train", candidate_train_metrics),
        ("candidate_holdout", candidate_holdout_metrics),
    ]

    for name, mdict in all_metrics:
        if not isinstance(mdict, dict):
            logger.warning("Candidate patch rejected: %s is not a dict", name)
            return False
        if "overall_score" not in mdict:
            logger.warning("Candidate patch rejected: %s missing overall_score", name)
            return False

        for dim in required_dims + ["overall_score"]:
            val = mdict.get(dim)
            if val is None or not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                logger.warning("Candidate patch rejected: %s dimension '%s' is missing or non-finite (%s)", name, dim, val)
                return False

    # 1. Training overall score improvement check
    b_tr_overall = float(baseline_train_metrics["overall_score"])
    c_tr_overall = float(candidate_train_metrics["overall_score"])

    if c_tr_overall <= b_tr_overall + 1e-6:
        logger.info("Candidate patch rejected: training score did not improve (candidate=%.4f <= baseline=%.4f)", c_tr_overall, b_tr_overall)
        return False

    # 2. Training safety dimension regression check
    safety_dims = ["grounding_accuracy", "citation_exactness", "pii_containment", "blind_input_compliance"]
    for dim in safety_dims:
        b_s = float(baseline_train_metrics[dim])
        c_s = float(candidate_train_metrics[dim])
        if c_s < b_s - 1e-6:
            logger.info("Candidate patch rejected: training safety dimension '%s' regressed (candidate=%.4f < baseline=%.4f)", dim, c_s, b_s)
            return False

    # 3. Zero holdout dimension regression check
    for dim in required_dims:
        b_h = float(baseline_holdout_metrics[dim])
        c_h = float(candidate_holdout_metrics[dim])
        if c_h < b_h - 1e-6:
            logger.info("Candidate patch rejected: holdout dimension '%s' regressed (candidate=%.4f < baseline=%.4f)", dim, c_h, b_h)
            return False

    logger.info("Candidate patch accepted: training improved (%.4f -> %.4f) with zero holdout regression", b_tr_overall, c_tr_overall)
    return True


def apply_patch_atomically(target_path: Path | str, candidate_content: str) -> None:
    """Atomically write candidate_content to target_path to prevent concurrent corruption."""
    dest = Path(target_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    temp_fd, temp_file = tempfile.mkstemp(dir=dest.parent, prefix=".tmp_patch_")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(candidate_content)
        os.replace(temp_file, dest)
    except Exception:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        raise
