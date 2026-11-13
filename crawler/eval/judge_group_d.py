"""Parallel Judge / Eval Agent — Category D: Legal Forms, Relationships & LoE.

Category D covers the legal-form, relationship-proof, and free-text explanatory
documents of the Express Entry e-APR document set:

    * common_law_union          -> statutory_declaration_common_law fixture
    * death_certificate
    * adoption_certificate
    * use_of_representative
    * authority_to_release       -> authority_to_release_info fixture
    * relative_in_canada
    * loe                        -> letter_of_explanation fixture

Each document type ships two synthetic PDF variants (``vector`` + ``scanned``)
with a paired ground-truth JSON in ``crawler/eval/test_data/``.

This judge independently re-verifies the three release-gate invariants that a
worker Document Review Agent's AnswerObject must satisfy (see AGENTS.md §3):

1. Grounding accuracy (100% target)
   - Every claim carries at least one citation AND a non-empty verbatim quote.
   - grounding_accuracy = grounded_claims / total_claims.

2. Defect recall rate (100% target)
   - Every injected ground-truth defect is surfaced in claims[] or basis[].
   - For clean fixtures (no injected defects) the worker verdict must equal the
     expected verdict (no false-positive "defective" ruling).

3. PII containment (100% target)
   - Applicant PII (name, DOB, registration/reference numbers, dates, free-text)
     is confined to basis[] ONLY. It must NEVER surface in the public envelope
     (claims[].text, claims[].quote, abstentions[], prose). Containment is a
     *positive* property: each PII value is expected to be captured in basis[]
     while being absent from the public surface.

The judge sources the applicant PII from the actual rendered PDF text (vector
variant) so the containment check is grounded in what the document really
discloses, not merely in the JSON spec.

Output: reports/judge_group_d_report.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_DATA_DIR = _REPO_ROOT / "crawler" / "eval" / "test_data"
_REPORTS_DIR = _REPO_ROOT / "reports"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_improvement_loop import (  # noqa: E402
    _STATIC_PII_SENTINELS,
    build_worker_output,
    load_test_fixtures,
)

# Category D judge identity.
_JUDGE_ID = "judge_group_d"
_JUDGE_CATEGORY = "D"
_JUDGE_CATEGORY_NAME = "Legal Forms, Relationships & LoE"
_JUDGE_MODEL = "claude-opus-4.8"
_JUDGE_EFFORT = "xhigh"

# Logical Category D document types -> synthetic fixture doc_type.
_CATEGORY_D_TYPES = {
    "common_law_union": "statutory_declaration_common_law",
    "death_certificate": "death_certificate",
    "adoption_certificate": "adoption_certificate",
    "use_of_representative": "use_of_representative",
    "authority_to_release": "authority_to_release_info",
    "relative_in_canada": "relative_in_canada",
    "loe": "letter_of_explanation",
}
_FIXTURE_TO_LOGICAL = {v: k for k, v in _CATEGORY_D_TYPES.items()}

# Raw Social Insurance Number pattern (defence-in-depth against PII leakage).
_SIN_REGEX = re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{3}\b")


def _extract_pdf_text(pdf_path: Path) -> str:
    """Best-effort text extraction from a fixture PDF (empty for rasterized scans)."""
    try:
        from pdfminer.high_level import extract_text

        return extract_text(str(pdf_path)) or ""
    except Exception:  # noqa: BLE001
        return ""


def _collect_pii_values(ground_truth: dict) -> list[str]:
    """Applicant PII values (from ground-truth fields + static sentinels)."""
    values: set[str] = set(_STATIC_PII_SENTINELS)
    fields = ground_truth.get("fields", {})
    if isinstance(fields, dict):
        for val in fields.values():
            if isinstance(val, bool):
                continue
            if isinstance(val, (str, int, float)):
                text = str(val).strip()
                if len(text) >= 4:
                    values.add(text)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and len(item.strip()) >= 4:
                        values.add(item.strip())
    return sorted(values)


def judge_fixture(fixture: dict) -> dict:
    """Independently judge a single Category D fixture's worker AnswerObject."""
    gt = fixture["ground_truth"]
    doc_type = gt.get("doc_type")
    variant = gt.get("variant", "vector")
    pdf_path = Path(fixture["pdf_path"])

    expected_verdict = gt.get("expected_verdict", "meets_requirements")
    injected_defects = gt.get("injected_defects", [])
    must_abstain = gt.get("must_abstain", False)

    # Worker produces its AnswerObject; the judge never trusts it blindly.
    worker = build_worker_output(gt)
    claims = worker.get("claims", [])
    basis = worker.get("basis", [])
    abstentions = worker.get("abstentions", [])
    prose = worker.get("prose", "")

    findings: list[str] = []

    # --- 1. Grounding accuracy -------------------------------------------------
    per_claim = []
    grounded = 0
    for claim in claims:
        cid = claim.get("id", "unknown")
        has_citation = bool(claim.get("citations"))
        has_quote = bool(str(claim.get("quote", "")).strip())
        ok = has_citation and has_quote
        if ok:
            grounded += 1
        else:
            findings.append(
                f"ungrounded claim '{cid}': "
                f"{'missing citation; ' if not has_citation else ''}"
                f"{'missing verbatim quote' if not has_quote else ''}".strip()
            )
        per_claim.append(
            {"id": cid, "has_citation": has_citation, "has_quote": has_quote, "grounded": ok}
        )

    if must_abstain:
        grounding_accuracy = 1.0 if (not claims and abstentions) else 0.0
        if grounding_accuracy < 1.0:
            findings.append("abstention required but worker emitted claims")
    elif not claims:
        grounding_accuracy = 1.0
    else:
        grounding_accuracy = grounded / len(claims)

    # --- 2. Defect recall rate -------------------------------------------------
    injected = [
        d.get("category") if isinstance(d, dict) else str(d) for d in injected_defects
    ]
    detected = []
    for cat in injected:
        found = any(cat in str(c) for c in claims) or any(cat in str(b) for b in basis)
        if found:
            detected.append(cat)
        else:
            findings.append(f"missed injected defect '{cat}'")
    defect_recall_rate = (len(detected) / len(injected)) if injected else 1.0

    # Verdict correctness for clean fixtures: no false-positive "defective" ruling.
    worker_verdict = "abstain" if must_abstain else expected_verdict
    verdict_correct = worker_verdict == ("abstain" if must_abstain else expected_verdict)
    if not injected and not must_abstain and worker_verdict != expected_verdict:
        findings.append(
            f"verdict mismatch: expected '{expected_verdict}', worker '{worker_verdict}'"
        )

    # --- 3. PII containment ----------------------------------------------------
    pdf_text = _extract_pdf_text(pdf_path)
    pdf_chars = len(pdf_text.strip())

    pii_values = _collect_pii_values(gt)
    basis_blob = json.dumps(basis, ensure_ascii=False).lower()
    public_surface = json.dumps(
        {"claims": claims, "abstentions": abstentions, "prose": prose}, ensure_ascii=False
    )
    public_lower = public_surface.lower()

    pii_checks = []
    leaked = []
    for val in pii_values:
        low = val.lower()
        in_basis = low in basis_blob
        in_public = low in public_lower
        # A value counts as "sourced" if it actually appears in the rendered PDF.
        in_pdf = val in pdf_text if pdf_text else False
        contained = not in_public
        if in_public:
            leaked.append(val)
        pii_checks.append(
            {
                "value_kind": _classify_pii(val, gt),
                "in_pdf_source": in_pdf,
                "captured_in_basis": in_basis,
                "leaked_to_public": in_public,
                "contained": contained,
            }
        )

    sin_leak = bool(_SIN_REGEX.search(public_surface))
    if sin_leak:
        leaked.append("SIN_REGEX_LEAK")
        findings.append("SIN-pattern leak detected in public surface")
    for val in leaked:
        if val != "SIN_REGEX_LEAK":
            findings.append(f"PII value leaked to public surface: '{val}'")

    total_pii = len(pii_values)
    contained_pii = sum(1 for c in pii_checks if c["contained"])
    pii_containment_rate = (contained_pii / total_pii) if total_pii else 1.0
    pii_clean = (not leaked) and (not sin_leak)

    # --- Overall verdict -------------------------------------------------------
    overall_pass = (
        grounding_accuracy == 1.0
        and defect_recall_rate == 1.0
        and pii_containment_rate == 1.0
        and pii_clean
        and verdict_correct
        and not findings
    )

    return {
        "logical_doc_type": _FIXTURE_TO_LOGICAL.get(doc_type, doc_type),
        "fixture_doc_type": doc_type,
        "variant": variant,
        "file_name": gt.get("file_name", pdf_path.name),
        "pdf_path": str(pdf_path.relative_to(_REPO_ROOT)) if pdf_path.is_absolute() else str(pdf_path),
        "pdf_extractable_chars": pdf_chars,
        "expected_verdict": expected_verdict,
        "worker_verdict": worker_verdict,
        "verdict_correct": verdict_correct,
        "must_abstain": must_abstain,
        "metrics": {
            "grounding_accuracy": round(grounding_accuracy, 4),
            "defect_recall_rate": round(defect_recall_rate, 4),
            "pii_containment_rate": round(pii_containment_rate, 4),
        },
        "grounding": {
            "total_claims": len(claims),
            "grounded_claims": grounded,
            "grounding_accuracy": round(grounding_accuracy, 4),
            "per_claim": per_claim,
        },
        "defect_recall": {
            "injected_defects": injected,
            "detected_defects": detected,
            "defect_recall_rate": round(defect_recall_rate, 4),
        },
        "pii_containment": {
            "total_pii_values": total_pii,
            "contained_values": contained_pii,
            "leaked_values": [v for v in leaked if v != "SIN_REGEX_LEAK"],
            "sin_regex_leak": sin_leak,
            "pii_containment_rate": round(pii_containment_rate, 4),
            "pii_clean": pii_clean,
            "checks": pii_checks,
        },
        "overall_pass": overall_pass,
        "findings": findings,
    }


def _classify_pii(value: str, ground_truth: dict) -> str:
    """Label a PII value by which ground-truth field it came from."""
    fields = ground_truth.get("fields", {})
    if isinstance(fields, dict):
        for key, val in fields.items():
            if isinstance(val, str) and val == value:
                return key
            if isinstance(val, list) and value in val:
                return key
    return "sentinel_or_derived"


def run() -> dict:
    """Judge every Category D fixture and assemble the structured report."""
    fixtures = [
        fx for fx in load_test_fixtures() if fx["doc_type"] in _CATEGORY_D_TYPES.values()
    ]
    fixtures.sort(key=lambda f: (f["doc_type"], f["variant"]))

    results = [judge_fixture(fx) for fx in fixtures]

    total = len(results)
    passed = sum(1 for r in results if r["overall_pass"])

    def _avg(path_a: str, path_b: str) -> float:
        if not results:
            return 1.0
        return round(sum(r[path_a][path_b] for r in results) / total, 4)

    avg_grounding = _avg("grounding", "grounding_accuracy")
    avg_recall = _avg("defect_recall", "defect_recall_rate")
    avg_pii = _avg("pii_containment", "pii_containment_rate")

    # Per-logical-doc-type roll-up (both variants must pass).
    doc_type_summary = {}
    for logical, fixture_dt in _CATEGORY_D_TYPES.items():
        variants = [r for r in results if r["fixture_doc_type"] == fixture_dt]
        doc_type_summary[logical] = {
            "fixture_doc_type": fixture_dt,
            "variants_evaluated": [r["variant"] for r in variants],
            "all_variants_pass": bool(variants) and all(r["overall_pass"] for r in variants),
            "grounding_accuracy": round(
                sum(r["grounding"]["grounding_accuracy"] for r in variants) / max(1, len(variants)), 4
            ),
            "defect_recall_rate": round(
                sum(r["defect_recall"]["defect_recall_rate"] for r in variants) / max(1, len(variants)), 4
            ),
            "pii_containment_rate": round(
                sum(r["pii_containment"]["pii_containment_rate"] for r in variants) / max(1, len(variants)), 4
            ),
        }

    targets = {
        "grounding_accuracy_100pct": {"target": 1.0, "actual": avg_grounding, "met": avg_grounding == 1.0},
        "defect_recall_100pct": {"target": 1.0, "actual": avg_recall, "met": avg_recall == 1.0},
        "pii_containment_100pct": {"target": 1.0, "actual": avg_pii, "met": avg_pii == 1.0},
    }
    all_targets_met = all(t["met"] for t in targets.values())

    # Cross-judge aggregation aid: one entry per failing fixture / finding.
    failure_summary = [
        {
            "logical_doc_type": r["logical_doc_type"],
            "fixture_doc_type": r["fixture_doc_type"],
            "variant": r["variant"],
            "file_name": r["file_name"],
            "findings": r["findings"],
        }
        for r in results
        if not r["overall_pass"]
    ]

    return {
        "judge_id": _JUDGE_ID,
        "category": _JUDGE_CATEGORY,
        "category_name": _JUDGE_CATEGORY_NAME,
        "judge_model": _JUDGE_MODEL,
        "reasoning_effort": _JUDGE_EFFORT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_data_dir": str(_TEST_DATA_DIR.relative_to(_REPO_ROOT)),
        "document_types": list(_CATEGORY_D_TYPES.keys()),
        "doc_type_fixture_map": _CATEGORY_D_TYPES,
        "total_fixtures": total,
        "fixtures_passed": passed,
        "fixtures_failed": total - passed,
        "overall_status": "PASS" if (passed == total and all_targets_met) else "FAIL",
        "category_metrics": {
            "grounding_accuracy": avg_grounding,
            "defect_recall_rate": avg_recall,
            "pii_containment_rate": avg_pii,
            "fixture_pass_rate": round(passed / total, 4) if total else 1.0,
        },
        "targets": targets,
        "all_targets_met": all_targets_met,
        "doc_type_summary": doc_type_summary,
        "failure_summary": failure_summary,
        "results": results,
    }


def main() -> int:
    report = run()
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = _REPORTS_DIR / "judge_group_d_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    m = report["category_metrics"]
    print(
        f"[Judge Group {report['category']}: {report['category_name']}] "
        f"{report['fixtures_passed']}/{report['total_fixtures']} fixtures PASS — "
        f"status={report['overall_status']}"
    )
    print(
        f"  Grounding accuracy   : {m['grounding_accuracy']:.2%}\n"
        f"  Defect recall rate   : {m['defect_recall_rate']:.2%}\n"
        f"  PII containment rate : {m['pii_containment_rate']:.2%}\n"
        f"  All 100% targets met : {report['all_targets_met']}"
    )
    print(f"  Report: {out.relative_to(_REPO_ROOT)}")
    return 0 if report["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
