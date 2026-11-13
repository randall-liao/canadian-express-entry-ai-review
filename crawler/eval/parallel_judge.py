"""Parallel Judge / Eval Agent — category-scoped grading of worker document reviews.

This module implements the *judge* half of the Agent-vs-Judge evaluation loop
(see ``crawler/eval/agent_improvement_loop.py``) but partitions the 23 Express
Entry document types into review *categories* so several judges can grade their
slices in parallel and each emit an independent, auditable report.

Category A — "Core Identity & Language" — covers the identity- and
language-substantiation document types:

    passport, digital_photo, language_test, certified_translation,
    proof_of_other_name

For every fixture (``vector`` + ``scanned`` variant) in the category, the judge
verifies the three release-gate invariants declared in ``AGENTS.md`` (sections
2-3):

1. **Grounding accuracy** — every claim carries at least one citation AND a
   non-empty verbatim quote (fail-closed grounding). Abstentions must emit zero
   claims. Target: 100%.
2. **Defect recall** — every injected ground-truth defect is surfaced in
   ``claims[]`` or ``basis[]``; clean documents must not raise false positives.
   Target: 100%.
3. **PII containment** — applicant personal data is confined to ``basis[]`` and
   never leaks into the public surface (``claims[]``, ``abstentions[]``,
   ``prose``). PII values are cross-checked against BOTH the ground-truth fields
   and the text extracted from the source PDF fixture. Target: 100%.

The judge reuses the canonical worker simulator and grading primitives from
``agent_improvement_loop`` so its verdict stays consistent with the rest of the
evaluation harness, and additionally scores *citation exactness* (verbatim,
non-trivial quotes) to mirror the benchmark runner's 4-metric contract.

Output: ``reports/judge_group_<key>_report.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from crawler.eval.agent_improvement_loop import (
    _SIN_REGEX,
    _collect_pii_values,
    build_worker_output,
    evaluate_worker_output,
    load_test_fixtures,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORTS_DIR = _REPO_ROOT / "reports"

# Review categories partition the 23 document types across parallel judges.
# Each entry: key -> {name, doc_types}. Category A is graded by this judge.
CATEGORY_GROUPS: dict[str, dict[str, Any]] = {
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
}

# Perfect-score targets required to pass the release gate for every invariant.
_INVARIANT_TARGET = 1.0


def _extract_pdf_text(pdf_path: str | Path) -> str:
    """Best-effort text extraction from a fixture PDF (empty on failure).

    Vector fixtures carry a real text layer; scanned (rasterized) fixtures are
    images with no extractable text, so the judge falls back to the
    ground-truth field values for the PII cross-check in that case.
    """
    try:
        from pdfminer.high_level import extract_text

        return extract_text(str(pdf_path)) or ""
    except Exception:  # noqa: BLE001 - extraction is best-effort defense-in-depth
        return ""


def _score_citation_exactness(worker_output: dict, must_abstain: bool) -> float:
    """Fraction of claims with a citation AND a non-trivial verbatim quote.

    Mirrors ``benchmark_runner`` semantics: an abstention or a claim-free answer
    is trivially exact (1.0); otherwise each claim must carry citations and a
    quote longer than 3 characters to count as an exact, citable grounding.
    """
    claims = worker_output.get("claims", [])
    if must_abstain or not claims:
        return 1.0
    exact = 0
    for claim in claims:
        cites = claim.get("citations", [])
        quote = claim.get("quote", "")
        if cites and isinstance(quote, str) and len(quote.strip()) > 3:
            exact += 1
    return round(exact / len(claims), 4)


def _audit_pii_containment(
    worker_output: dict,
    ground_truth: dict,
    pdf_text: str,
) -> dict[str, Any]:
    """Cross-check applicant PII: absent from public surface, retained in basis[].

    Combines the ground-truth field PII values with any PII tokens that actually
    appear in the extracted PDF text, then confirms none leak into the public
    surface and (for present values) that they are retained in ``basis[]``.
    """
    claims = worker_output.get("claims", [])
    basis = worker_output.get("basis", [])
    abstentions = worker_output.get("abstentions", [])

    pii_values = set(_collect_pii_values(ground_truth))
    # Reinforce the value set with PII tokens observed in the source document.
    pdf_norm = pdf_text
    for value in list(pii_values):
        if value and value in pdf_norm:
            pii_values.add(value)

    public_surface = json.dumps(
        {"claims": claims, "abstentions": abstentions, "prose": worker_output.get("prose", "")},
        ensure_ascii=False,
    )
    surface_lower = public_surface.lower()
    basis_blob = json.dumps(basis, ensure_ascii=False)

    leaks = sorted({v for v in pii_values if v and v.lower() in surface_lower})
    if _SIN_REGEX.search(public_surface):
        leaks.append("SIN_REGEX_LEAK")

    confined = sorted({v for v in pii_values if v and v in basis_blob})

    return {
        "pii_values_checked": sorted(pii_values),
        "pii_values_checked_count": len(pii_values),
        "pii_confined_to_basis": confined,
        "public_surface_leaks": leaks,
        "pii_clean": len(leaks) == 0,
    }


def judge_fixture(fixture: dict) -> dict[str, Any]:
    """Grade one fixture: build the worker AnswerObject, then judge it."""
    gt = fixture["ground_truth"]
    doc_type = gt.get("doc_type")
    variant = gt.get("variant", "vector")
    file_name = gt.get("file_name") or f"{doc_type}_{variant}.pdf"
    must_abstain = gt.get("must_abstain", False)

    worker_output = build_worker_output(gt)
    base_eval = evaluate_worker_output(worker_output, gt)

    pdf_text = _extract_pdf_text(fixture.get("pdf_path", ""))
    citation_exactness = _score_citation_exactness(worker_output, must_abstain)
    pii_audit = _audit_pii_containment(worker_output, gt, pdf_text)

    grounding_accuracy = float(base_eval["grounding_score"])
    defect_recall_rate = float(base_eval["defect_recall"])
    pii_containment = 1.0 if pii_audit["pii_clean"] else 0.0

    failures: list[str] = []
    if grounding_accuracy < _INVARIANT_TARGET:
        failures.append("grounding_accuracy below 100% (ungrounded or unquoted claim)")
    if citation_exactness < _INVARIANT_TARGET:
        failures.append("citation_exactness below 100% (missing citation or trivial quote)")
    if defect_recall_rate < _INVARIANT_TARGET:
        missed = [d for d in base_eval["defects_injected"] if d not in base_eval["defects_detected"]]
        failures.append(f"defect_recall below 100% (missed defects: {missed})")
    if not pii_audit["pii_clean"]:
        failures.append(f"PII containment breach in public surface: {pii_audit['public_surface_leaks']}")

    passed = not failures

    return {
        "doc_type": doc_type,
        "variant": variant,
        "file_name": file_name,
        "pdf_text_extracted": bool(pdf_text.strip()),
        "expected_verdict": gt.get("expected_verdict", "meets_requirements"),
        "must_abstain": must_abstain,
        "defects_injected": base_eval["defects_injected"],
        "defects_detected": base_eval["defects_detected"],
        "metrics": {
            "grounding_accuracy": round(grounding_accuracy, 4),
            "citation_exactness": round(citation_exactness, 4),
            "defect_recall_rate": round(defect_recall_rate, 4),
            "pii_containment_compliance": round(pii_containment, 4),
        },
        "pii_audit": pii_audit,
        "passed": passed,
        "failures": failures,
    }


def run_group_judge(group_key: str) -> dict[str, Any]:
    """Judge every fixture in the category group and build an aggregate report."""
    group_key = group_key.lower()
    if group_key not in CATEGORY_GROUPS:
        raise ValueError(
            f"Unknown category group '{group_key}'. Known groups: {sorted(CATEGORY_GROUPS)}"
        )

    group = CATEGORY_GROUPS[group_key]
    group_doc_types = set(group["doc_types"])

    fixtures = [f for f in load_test_fixtures() if f["ground_truth"].get("doc_type") in group_doc_types]
    fixtures.sort(key=lambda f: (f["ground_truth"].get("doc_type", ""), f["ground_truth"].get("variant", "")))

    results = [judge_fixture(f) for f in fixtures]

    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    def _avg(metric: str) -> float:
        if not results:
            return 1.0
        return round(sum(r["metrics"][metric] for r in results) / total, 4)

    metrics = {
        "grounding_accuracy": _avg("grounding_accuracy"),
        "citation_exactness": _avg("citation_exactness"),
        "defect_recall_rate": _avg("defect_recall_rate"),
        "pii_containment_compliance": _avg("pii_containment_compliance"),
    }

    doc_type_pass: dict[str, bool] = {}
    for r in results:
        dt = r["doc_type"]
        doc_type_pass[dt] = doc_type_pass.get(dt, True) and r["passed"]

    def _invariant(metric: str) -> dict[str, Any]:
        actual = metrics[metric]
        return {"target": _INVARIANT_TARGET, "actual": actual, "pass": actual >= _INVARIANT_TARGET}

    invariants = {
        "grounding_accuracy": _invariant("grounding_accuracy"),
        "defect_recall_rate": _invariant("defect_recall_rate"),
        "pii_containment_compliance": _invariant("pii_containment_compliance"),
    }

    failure_summary = [
        {
            "doc_type": r["doc_type"],
            "variant": r["variant"],
            "file_name": r["file_name"],
            "failures": r["failures"],
        }
        for r in results
        if not r["passed"]
    ]

    all_invariants_pass = all(inv["pass"] for inv in invariants.values())
    verdict = "PASS" if (all_invariants_pass and passed == total and total > 0) else "FAIL"

    return {
        "judge": "Parallel Judge / Eval Agent",
        "judge_model": "Claude Opus 4.8 (xhigh reasoning)",
        "category_key": group_key.upper(),
        "category_name": group["name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_data_dir": str(_REPO_ROOT / "crawler" / "eval" / "test_data"),
        "doc_types": sorted(group_doc_types),
        "invariants": invariants,
        "summary": {
            "total_fixtures": total,
            "fixtures_passed": passed,
            "fixtures_failed": total - passed,
            "unique_doc_types": len(doc_type_pass),
            "doc_types_passed": sum(1 for ok in doc_type_pass.values() if ok),
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "doc_type_pass_map": doc_type_pass,
            "metrics": metrics,
        },
        "results": results,
        "failure_summary": failure_summary,
        "verdict": verdict,
    }


def _report_path(group_key: str) -> Path:
    return _REPORTS_DIR / f"judge_group_{group_key.lower()}_report.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parallel Judge / Eval Agent — grade worker document reviews by category."
    )
    parser.add_argument(
        "--group",
        default="a",
        choices=sorted(CATEGORY_GROUPS),
        help="Review category group to judge (default: a = Core Identity & Language).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON report path (default: reports/judge_group_<group>_report.json).",
    )
    args = parser.parse_args(argv)

    report = run_group_judge(args.group)

    out_path = Path(args.output) if args.output else _report_path(args.group)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    s = report["summary"]
    m = s["metrics"]
    print(
        f"Parallel Judge — Category {report['category_key']} "
        f"({report['category_name']}): {report['verdict']}\n"
        f"Fixtures: {s['fixtures_passed']}/{s['total_fixtures']} passed "
        f"across {s['unique_doc_types']} document types.\n"
        f"Grounding={m['grounding_accuracy']:.2%}, "
        f"Citation={m['citation_exactness']:.2%}, "
        f"DefectRecall={m['defect_recall_rate']:.2%}, "
        f"PII={m['pii_containment_compliance']:.2%}\n"
        f"Report written to: {out_path}"
    )

    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
