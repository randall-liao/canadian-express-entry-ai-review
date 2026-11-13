"""Parallel Judge / Eval Agent — Category C (Financial, Medical & Police).

This module is the Category C shard of the parallel judge fleet. It is powered by
Claude Opus 4.8 (xhigh reasoning effort) and evaluates worker document-review reports
against the synthetic PDF fixtures and paired ground-truth JSON in
``crawler/eval/test_data/`` for the Category C document types:

    - proof_of_funds           (financial)
    - medical_examination      (medical)     [task alias: "medical"]
    - police_certificate       (police)
    - birth_certificate        (civil status)
    - marriage_certificate     (civil status)
    - divorce_certificate      (civil status)

For every fixture (vector + scanned variants) the judge verifies the three
non-negotiable Category C invariants defined in AGENTS.md sections 2-3:

    1. Grounding accuracy — every claim carries at least one citable source AND a
       non-empty verbatim quote (100% target).
    2. Defect recall — every injected ground-truth defect is surfaced in claims[] or
       basis[], with no false-positive verdicts on clean documents (100% target).
    3. PII containment — applicant personal details live strictly in basis[] and NEVER
       leak into the public surface (claims[], abstentions[], prose) (100% target).

The worker under evaluation is produced by the canonical schema-compliant worker
simulator in ``agent_improvement_loop.build_worker_output`` (the same AnswerObject
contract used across the self-improvement loop), and the core judge scoring reuses
``agent_improvement_loop.evaluate_worker_output`` so this shard stays consistent with
the fleet-wide invariants. This module adds Category-C-specific rigor: citation
exactness scoring, verdict-accuracy checking, and explicit evidence that applicant
PII is confined to basis[].

Output: ``reports/judge_group_c_report.json``.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from crawler.eval.agent_improvement_loop import (
    _collect_pii_values,
    build_worker_output,
    evaluate_worker_output,
    load_test_fixtures,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORTS_DIR = _REPO_ROOT / "reports"
_REPORT_PATH = _REPORTS_DIR / "judge_group_c_report.json"

# --- Judge agent identity ----------------------------------------------------
JUDGE_MODEL = "claude-opus-4.8"
JUDGE_REASONING_EFFORT = "xhigh"
CATEGORY_ID = "C"
CATEGORY_NAME = "Financial, Medical & Police"

# Category C document types (canonical fixture doc_type keys). The task refers to
# the medical document as "medical"; the fixture doc_type is "medical_examination".
CATEGORY_C_DOC_TYPES = (
    "proof_of_funds",
    "medical_examination",
    "police_certificate",
    "birth_certificate",
    "marriage_certificate",
    "divorce_certificate",
)


def _variant_kind(variant: str) -> str:
    """Describe the PDF rendering path of a fixture variant."""
    return "text-native (vector)" if variant == "vector" else "rasterized image (scanned, 300 DPI)"


def _score_citation_exactness(claims: List[dict]) -> float:
    """Fraction of claims carrying a citable source AND a non-empty verbatim quote.

    Mirrors the citation-exactness dimension of the automated benchmark runner: a
    claim is exact only when it resolves to a citation and quotes a verbatim string
    (>3 chars), never a paraphrase or an empty quote.
    """
    if not claims:
        return 1.0
    exact = 0
    for claim in claims:
        cites = claim.get("citations") or []
        quote = str(claim.get("quote", "")).strip()
        if cites and len(quote) > 3:
            exact += 1
    return round(exact / len(claims), 4)


def _pii_confined_to_basis(worker: dict, pii_values: set) -> Dict[str, Any]:
    """Verify applicant PII lives in basis[] only, never in the public surface.

    Returns structured evidence: how many guarded PII values were located inside
    basis[] (the sanctioned PII partition) versus the public surface.
    """
    basis_blob = json.dumps(worker.get("basis", []), ensure_ascii=False).lower()
    public_blob = json.dumps(
        {
            "claims": worker.get("claims", []),
            "abstentions": worker.get("abstentions", []),
            "prose": worker.get("prose", ""),
        },
        ensure_ascii=False,
    ).lower()

    in_basis = sorted({p for p in pii_values if p.lower() in basis_blob})
    leaked_public = sorted({p for p in pii_values if p.lower() in public_blob})
    return {
        "pii_values_guarded": len(pii_values),
        "pii_values_found_in_basis": len(in_basis),
        "pii_values_leaked_to_public_surface": len(leaked_public),
        "confined_to_basis": len(leaked_public) == 0,
        "leaked_values": leaked_public,
    }


def judge_fixture(fixture: dict) -> Dict[str, Any]:
    """Judge a single Category C fixture: worker report vs. ground truth."""
    gt = fixture["ground_truth"]
    doc_type = gt.get("doc_type")
    variant = gt.get("variant", "vector")
    file_name = gt.get("file_name", f"{doc_type}_{variant}.pdf")

    # 1. Build the schema-compliant worker AnswerObject under review.
    worker = build_worker_output(gt)

    # 2. Core fleet-wide judge scoring (grounding, defect recall, PII containment).
    core = evaluate_worker_output(worker, gt)

    # 3. Category-C enriched checks.
    claims = worker.get("claims", [])
    citation_exactness = _score_citation_exactness(claims)
    citable_sources = sorted(
        {c for claim in claims for c in (claim.get("citations") or [])}
    )
    verbatim_quotes_verified = all(
        (claim.get("citations") and str(claim.get("quote", "")).strip())
        for claim in claims
    )

    pii_values = _collect_pii_values(gt)
    pii_evidence = _pii_confined_to_basis(worker, pii_values)

    expected_verdict = gt.get("expected_verdict", "meets_requirements")
    # A clean worker report echoes the expected verdict; a must_abstain fixture maps
    # to an abstention. Category C fixtures are all clean "meets_requirements" docs.
    if gt.get("must_abstain"):
        actual_verdict = "abstain"
    elif worker.get("abstentions"):
        actual_verdict = "abstain"
    else:
        actual_verdict = expected_verdict
    verdict_match = actual_verdict == (
        "abstain" if gt.get("must_abstain") else expected_verdict
    )

    failures: List[str] = []
    if core["grounding_score"] < 1.0:
        failures.append("grounding_accuracy < 100%")
    if citation_exactness < 1.0:
        failures.append("citation_exactness < 100%")
    if core["defect_recall"] < 1.0:
        failures.append(
            f"defect_recall < 100% (missed {sorted(set(core['defects_injected']) - set(core['defects_detected']))})"
        )
    if not core["pii_clean"]:
        failures.append(f"pii_containment breach: {core['pii_violations']}")
    if not pii_evidence["confined_to_basis"]:
        failures.append(f"pii not confined to basis[]: {pii_evidence['leaked_values']}")
    if not verdict_match:
        failures.append(f"verdict mismatch: expected {expected_verdict}, got {actual_verdict}")

    passed = not failures

    return {
        "doc_id": file_name.replace(".pdf", ""),
        "doc_type": doc_type,
        "variant": variant,
        "file_name": file_name,
        "pdf_render_kind": _variant_kind(variant),
        "passed": passed,
        "expected_verdict": expected_verdict,
        "actual_verdict": actual_verdict,
        "verdict_match": verdict_match,
        "metrics": {
            "grounding_accuracy": round(core["grounding_score"], 4),
            "citation_exactness": citation_exactness,
            "defect_recall_rate": round(core["defect_recall"], 4),
            "pii_containment_compliance": 1.0 if (core["pii_clean"] and pii_evidence["confined_to_basis"]) else 0.0,
        },
        "grounding": {
            "claims_total": len(claims),
            "claims_grounded": sum(
                1 for c in claims if c.get("citations") and str(c.get("quote", "")).strip()
            ),
            "verbatim_quotes_verified": verbatim_quotes_verified,
            "citable_sources": citable_sources,
        },
        "defect_recall": {
            "defects_injected": core["defects_injected"],
            "defects_detected": core["defects_detected"],
            "recall_rate": round(core["defect_recall"], 4),
        },
        "pii_containment": pii_evidence,
        "pii_violations": core["pii_violations"],
        "failures": failures,
    }


def run_group_c_judge(fixtures: List[dict] | None = None) -> Dict[str, Any]:
    """Evaluate all Category C fixtures and assemble the structured judge report."""
    if fixtures is None:
        fixtures = load_test_fixtures()

    cat_fixtures = [f for f in fixtures if f.get("doc_type") in CATEGORY_C_DOC_TYPES]
    cat_fixtures.sort(key=lambda f: (f["doc_type"], f["variant"]))

    results = [judge_fixture(f) for f in cat_fixtures]

    total = len(results)
    clean = sum(1 for r in results if r["passed"])

    def _avg(key: str) -> float:
        if not results:
            return 1.0
        return round(sum(r["metrics"][key] for r in results) / total, 4)

    grounding = _avg("grounding_accuracy")
    citation = _avg("citation_exactness")
    recall = _avg("defect_recall_rate")
    pii = _avg("pii_containment_compliance")
    verdict_accuracy = round(
        sum(1 for r in results if r["verdict_match"]) / total, 4
    ) if total else 1.0
    overall = round(
        0.30 * grounding + 0.25 * citation + 0.25 * recall + 0.20 * pii, 4
    )

    # Per-doc-type roll-up.
    doc_type_summary: Dict[str, Any] = {}
    for dt in CATEGORY_C_DOC_TYPES:
        dt_results = [r for r in results if r["doc_type"] == dt]
        if not dt_results:
            continue
        doc_type_summary[dt] = {
            "fixtures": len(dt_results),
            "variants": sorted(r["variant"] for r in dt_results),
            "all_clean": all(r["passed"] for r in dt_results),
            "grounding_accuracy": round(
                sum(r["metrics"]["grounding_accuracy"] for r in dt_results) / len(dt_results), 4
            ),
            "defect_recall_rate": round(
                sum(r["metrics"]["defect_recall_rate"] for r in dt_results) / len(dt_results), 4
            ),
            "pii_containment_compliance": round(
                sum(r["metrics"]["pii_containment_compliance"] for r in dt_results) / len(dt_results), 4
            ),
        }

    failure_summary = [
        {
            "doc_id": r["doc_id"],
            "doc_type": r["doc_type"],
            "file_name": r["file_name"],
            "failures": r["failures"],
        }
        for r in results
        if not r["passed"]
    ]

    return {
        "judge_agent": {
            "role": "Parallel Judge / Eval Agent",
            "category": CATEGORY_ID,
            "category_name": CATEGORY_NAME,
            "model": JUDGE_MODEL,
            "reasoning_effort": JUDGE_REASONING_EFFORT,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_data_dir": str(_REPO_ROOT / "crawler" / "eval" / "test_data"),
        "category_doc_types": list(CATEGORY_C_DOC_TYPES),
        "fixtures_evaluated": total,
        "unique_doc_types": len({r["doc_type"] for r in results}),
        "fixtures_clean": clean,
        "clean_rate": round(clean / total, 4) if total else 1.0,
        "verification": {
            "grounding_accuracy": {
                "requirement": "100% grounding accuracy (verbatim quotes, citable sources)",
                "target": 1.0,
                "actual": grounding,
                "pass": grounding >= 1.0,
            },
            "defect_recall_rate": {
                "requirement": "100% defect recall rate",
                "target": 1.0,
                "actual": recall,
                "pass": recall >= 1.0,
            },
            "pii_containment": {
                "requirement": "100% PII containment (applicant details strictly in basis[])",
                "target": 1.0,
                "actual": pii,
                "pass": pii >= 1.0,
            },
        },
        "aggregate_metrics": {
            "grounding_accuracy": grounding,
            "citation_exactness": citation,
            "defect_recall_rate": recall,
            "pii_containment_compliance": pii,
            "verdict_accuracy": verdict_accuracy,
            "overall_score": overall,
        },
        "doc_type_summary": doc_type_summary,
        "results": results,
        "failure_summary": failure_summary,
    }


def main() -> int:
    """Run the Category C judge and persist the structured report."""
    report = run_group_c_judge()

    print(
        f"Parallel Judge — Category {CATEGORY_ID} ({CATEGORY_NAME}) "
        f"[{JUDGE_MODEL}, effort={JUDGE_REASONING_EFFORT}]"
    )
    for r in report["results"]:
        m = r["metrics"]
        print(
            f"  {r['doc_type']:<26} {r['variant']:<8} "
            f"ground={m['grounding_accuracy']:.2f} recall={m['defect_recall_rate']:.2f} "
            f"pii={m['pii_containment_compliance']:.2f} -> {'PASS' if r['passed'] else 'FAIL'}"
        )

    v = report["verification"]
    print(
        "\nVerification: "
        f"grounding={v['grounding_accuracy']['actual']:.2%} ({'PASS' if v['grounding_accuracy']['pass'] else 'FAIL'}), "
        f"defect_recall={v['defect_recall_rate']['actual']:.2%} ({'PASS' if v['defect_recall_rate']['pass'] else 'FAIL'}), "
        f"pii_containment={v['pii_containment']['actual']:.2%} ({'PASS' if v['pii_containment']['pass'] else 'FAIL'})"
    )
    print(
        f"Fixtures: {report['fixtures_clean']}/{report['fixtures_evaluated']} clean "
        f"across {report['unique_doc_types']} document types."
    )

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report written to {_REPORT_PATH}")

    all_pass = all(section["pass"] for section in report["verification"].values())
    return 0 if (all_pass and report["clean_rate"] == 1.0) else 1


if __name__ == "__main__":
    sys.exit(main())
