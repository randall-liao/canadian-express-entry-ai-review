"""Logical sibling group train/holdout splitter and sealer engine.

Manages logical sibling group train/holdout partitioning and holdout sealing
per D-12, D-13, and JUDGE_IMPROVE-01.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_TRAINING_SCORE_FIELDS = {
    "grounding_accuracy",
    "citation_exactness",
    "defect_recall",
    "pii_containment",
    "blind_input_compliance",
}
_TRAINING_FINDING_FIELDS = {"case_id", "category", "severity", "description"}
_HOLDOUT_SEMANTIC_RE = re.compile(
    r"\b(?:hold[-_ ]?out|"
    r"sealed (?:case|set|split|score|label|finding|evaluation|result|metric)|"
    r"validation (?:case|set|split|score|label|finding|evaluation|result|metric))\b",
    re.IGNORECASE,
)


def contains_holdout_semantics(
    value: Any,
    holdout_case_ids: Iterable[str] = (),
) -> bool:
    """Detect explicit holdout IDs or holdout-semantic evaluation language."""
    serialized = json.dumps(value, ensure_ascii=False)
    lowered = serialized.lower()
    return bool(
        _HOLDOUT_SEMANTIC_RE.search(serialized)
        or any(str(case_id).lower() in lowered for case_id in holdout_case_ids)
    )


def get_pipeline_ground_truth(doc_type: str, pipeline_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load private ground_truth.json for a document type if available."""
    root = pipeline_root or _PIPELINES_DIR
    gt_file = root / doc_type / "ground_truth" / "ground_truth.json"
    if not gt_file.is_file():
        gt_dir = root / doc_type / "ground_truth"
        if gt_dir.is_dir():
            cases = []
            for f in sorted(gt_dir.glob("*.json")):
                if f.name != "ground_truth.json":
                    try:
                        cases.append(json.loads(f.read_text(encoding="utf-8")))
                    except Exception:
                        pass
            if cases:
                return cases
        raise FileNotFoundError(f"Ground truth not found for doc_type '{doc_type}' at {gt_file}")
    return json.loads(gt_file.read_text(encoding="utf-8"))


def split_doc_type_cases(
    cases: List[Dict[str, Any]],
    doc_type: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split cases into training and sealed holdout sets by logical sibling group.

    Guarantees:
    1. Sibling pairs (vector + scanned) are NEVER split across train and holdout boundaries.
    2. Holdout set contains exactly 4 cases: 1 valid control pair (vector + scanned) and 1 defective pair selected deterministically via sha256.
    3. Training set contains all remaining sibling pairs.
    """
    if not cases:
        return [], []

    dt = doc_type or cases[0].get("doc_type", "unknown")

    # Group cases into sibling pairs
    pair_map: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for case in cases:
        cid = case["opaque_case_id"]
        sid = case.get("sibling_case_id") or cid
        pair_key = tuple(sorted([cid, sid]))
        pair_map.setdefault(pair_key, []).append(case)

    # Classify pairs as valid or defective
    valid_pairs: List[Tuple[Tuple[str, ...], List[Dict[str, Any]]]] = []
    defective_pairs: List[Tuple[Tuple[str, ...], List[Dict[str, Any]]]] = []

    for pair_key in sorted(pair_map.keys()):
        pair_cases = pair_map[pair_key]
        is_valid = all(c.get("expected_verdict") == "meets_requirements" for c in pair_cases)
        if is_valid:
            valid_pairs.append((pair_key, pair_cases))
        else:
            defective_pairs.append((pair_key, pair_cases))

    if not valid_pairs:
        raise ValueError(f"No valid control sibling pair found for doc_type '{dt}'")
    if not defective_pairs:
        raise ValueError(f"No defective sibling pairs found for doc_type '{dt}'")

    # 1 valid control pair to holdout
    holdout_valid_pair_key, holdout_valid_cases = valid_pairs[0]
    train_valid_pairs = valid_pairs[1:]

    # Select 1 defective pair deterministically using sha256(doc_type)
    hash_val = int(hashlib.sha256(dt.encode("utf-8")).hexdigest(), 16)
    defective_idx = hash_val % len(defective_pairs)

    holdout_defective_pair_key, holdout_defective_cases = defective_pairs[defective_idx]
    train_defective_pairs = [p for i, p in enumerate(defective_pairs) if i != defective_idx]

    # Combine
    holdout_cases = holdout_valid_cases + holdout_defective_cases
    train_cases = []
    for _, pcs in train_valid_pairs + train_defective_pairs:
        train_cases.extend(pcs)

    if len(holdout_cases) != 4:
        raise ValueError(
            f"Holdout set size mismatch for doc_type '{dt}': expected exactly 4 cases, got {len(holdout_cases)}"
        )

    return train_cases, holdout_cases


def get_holdout_case_ids(
    doc_type: str,
    cases: Optional[List[Dict[str, Any]]] = None,
    pipeline_root: Optional[Path] = None,
) -> Set[str]:
    """Return the set of opaque_case_ids in the sealed holdout set for a document type."""
    if cases is None:
        cases = get_pipeline_ground_truth(doc_type, pipeline_root=pipeline_root)
    _, holdout_cases = split_doc_type_cases(cases, doc_type=doc_type)
    return {c["opaque_case_id"] for c in holdout_cases}


def seal_holdout_findings(
    judge_batch: Any,
    holdout_case_ids: Optional[Iterable[str]] = None,
    doc_type: Optional[str] = None,
    pipeline_root: Optional[Path] = None,
) -> Any:
    """Strip holdout case rationales, scores, failure labels, and ground truth from optimizer-facing data structures.

    Fails closed if holdout IDs cannot be loaded or resolved.
    Returns a sanitized copy containing ONLY training case information plus holdout commitment (count + hash).
    """
    holdout_ids: Set[str] = set(holdout_case_ids) if holdout_case_ids is not None else set()

    batch_doc_type = None
    if hasattr(judge_batch, "doc_type"):
        batch_doc_type = getattr(judge_batch, "doc_type")
    elif isinstance(judge_batch, dict):
        batch_doc_type = judge_batch.get("doc_type")
    if doc_type and batch_doc_type and doc_type != batch_doc_type:
        raise ValueError(
            "seal_holdout_findings doc_type mismatch: "
            f"expected {doc_type!r}, got {batch_doc_type!r}"
        )
    dt = doc_type or batch_doc_type

    if not holdout_ids and dt:
        try:
            holdout_ids = get_holdout_case_ids(dt, pipeline_root=pipeline_root)
        except Exception as exc:
            raise ValueError(f"seal_holdout_findings failed closed: Failed to resolve holdout case IDs for doc_type '{dt}': {exc}") from exc

    if not holdout_ids:
        raise ValueError("seal_holdout_findings failed closed: holdout_case_ids could not be determined")

    if hasattr(judge_batch, "model_dump"):
        batch_dict = judge_batch.model_dump()
    else:
        batch_dict = copy.deepcopy(judge_batch)

    if not isinstance(batch_dict, dict):
        raise ValueError("seal_holdout_findings requires a dict or Pydantic model")

    training_evaluations: Dict[str, Dict[str, Any]] = {}
    raw_evaluations = batch_dict.get("case_evaluations", {})
    if isinstance(raw_evaluations, dict):
        for case_id, raw_score in raw_evaluations.items():
            if case_id in holdout_ids or not isinstance(raw_score, dict):
                continue
            sanitized_score: Dict[str, float] = {}
            for key, value in raw_score.items():
                if key not in _TRAINING_SCORE_FIELDS:
                    continue
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                ):
                    raise ValueError(
                        f"Training score {key!r} for {case_id!r} is not finite "
                        "and bounded between 0.0 and 1.0"
                    )
                sanitized_score[key] = float(value)
            training_evaluations[str(case_id)] = sanitized_score

    training_case_ids = set(training_evaluations)
    training_findings: List[Dict[str, Any]] = []
    raw_findings = batch_dict.get("findings", [])
    if isinstance(raw_findings, list):
        for raw_finding in raw_findings:
            if hasattr(raw_finding, "model_dump"):
                raw_finding = raw_finding.model_dump()
            if not isinstance(raw_finding, dict):
                continue
            case_id = raw_finding.get("case_id")
            if (
                case_id not in training_case_ids
                or contains_holdout_semantics(raw_finding, holdout_ids)
            ):
                continue
            sanitized_finding: Dict[str, str] = {}
            for key, value in raw_finding.items():
                if key not in _TRAINING_FINDING_FIELDS:
                    continue
                if not isinstance(value, str):
                    raise ValueError(
                        f"Training finding field {key!r} must be a string"
                    )
                sanitized_finding[key] = value
            training_findings.append(sanitized_finding)

    # Recommendations and rationale are not case-bound, so they cannot be proven
    # training-only and never cross the holdout seal.
    sorted_holdout_list = sorted(list(holdout_ids))
    commitment_hash = hashlib.sha256(
        json.dumps(sorted_holdout_list, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    sealed = {
        "doc_type": dt,
        "case_evaluations": training_evaluations,
        "findings": training_findings,
        "holdout_commitment": {
            "count": len(sorted_holdout_list),
            "hash": commitment_hash,
        },
    }
    return sealed
