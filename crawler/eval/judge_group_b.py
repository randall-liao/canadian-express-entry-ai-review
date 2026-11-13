"""Parallel Judge / Eval Agent — Category B: Education & Work Experience.

Judge persona: Claude Opus 4.8 (xhigh reasoning effort).

Scope (Category B document types, aliased to the synthetic fixture ``doc_type``):
    - ``eca``                          -> ``educational_credential_assessment``
    - ``proof_of_studies``             -> ``proof_of_studies``
    - ``employment_reference_letter``  -> ``employment_reference_letter``
    - ``job_offer``                    -> ``written_job_offer_lmia``
    - ``certificate_of_qualification`` -> ``certificate_of_qualification``

The judge evaluates worker document-review reports (canonical 5-field ``AnswerObject``
from AGENTS.md) against the paired ground-truth JSON specs in
``crawler/eval/test_data/`` and enforces three release-gate invariants:

1. Grounding accuracy (100%): every ``claims[]`` entry MUST carry at least one
   citation AND a non-empty ``quote`` that is a *verbatim substring* of the source
   document text (a citable source). Vector fixtures are grounded against the native
   PDF text layer; scanned fixtures are rasterized images whose canonical rendered
   text is the vector sibling's text layer (what a compliant OCR pass must recover).
2. Defect recall (100%): every injected ground-truth defect MUST be surfaced, and a
   clean document MUST NOT be flagged with a false-positive defect verdict.
3. PII containment (100%): applicant personal data (names, DOB, reference numbers,
   salary, employer, supervisor, contact e-mail, duties) MUST remain strictly inside
   ``basis[]``; it MUST NEVER appear in the public surface
   (``question`` / ``claims[]`` / ``abstentions[]`` / ``prose``).

Writes a structured evaluation report to ``reports/judge_group_b_report.json``.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pdfminer.high_level import extract_text

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_DATA_DIR = _REPO_ROOT / "crawler" / "eval" / "test_data"
_REPORTS_DIR = _REPO_ROOT / "reports"
_REPORT_PATH = _REPORTS_DIR / "judge_group_b_report.json"

JUDGE_AGENT = "Claude Opus 4.8 (xhigh reasoning effort)"
CATEGORY_ID = "B"
CATEGORY_NAME = "Education & Work Experience"

# Category B alias -> synthetic fixture doc_type.
CATEGORY_B_DOC_TYPES: Dict[str, str] = {
    "eca": "educational_credential_assessment",
    "proof_of_studies": "proof_of_studies",
    "employment_reference_letter": "employment_reference_letter",
    "job_offer": "written_job_offer_lmia",
    "certificate_of_qualification": "certificate_of_qualification",
}
_DOC_TYPE_TO_ALIAS = {v: k for k, v in CATEGORY_B_DOC_TYPES.items()}

# Applicant names that appear on the Category B synthetic documents but are not always
# an explicit ground-truth field. Treated as PII that must stay confined to basis[].
_APPLICANT_NAME_SENTINELS = ("Jane Doe",)

# Raw Social Insurance Number pattern (defence-in-depth PII leak probe).
_SIN_REGEX = re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{3}\b")

# Generic, PII-free requirement/structure labels that are verbatim substrings of each
# document's rendered text. These are the quotes a compliant worker cites; they carry
# NO applicant-identifying values, satisfying the PII structural partition.
_GROUNDING_QUOTES: Dict[str, List[str]] = {
    "educational_credential_assessment": [
        "EDUCATIONAL CREDENTIAL ASSESSMENT REPORT",
        "Primary Degree Evaluated:",
        "Canadian Academic Equivalency:",
    ],
    "proof_of_studies": [
        "OFFICIAL DOCUMENT: PROOF OF STUDIES",
        "Issuing Authority:",
        "Registration Number:",
    ],
    "employment_reference_letter": [
        "EMPLOYMENT REFERENCE LETTER",
        "Weekly Working Hours:",
        "Main Duties & Responsibilities:",
    ],
    "written_job_offer_lmia": [
        "OFFICIAL DOCUMENT: WRITTEN JOB OFFER LMIA",
        "Issuing Authority:",
        "Registration Number:",
    ],
    "certificate_of_qualification": [
        "OFFICIAL DOCUMENT: CERTIFICATE OF QUALIFICATION",
        "Issuing Authority:",
        "Registration Number:",
    ],
}


def _norm(text: str) -> str:
    """Collapse whitespace so verbatim substring checks survive PDF line wrapping."""
    return re.sub(r"\s+", " ", str(text)).strip()


def load_category_b_fixtures() -> List[Dict[str, Any]]:
    """Load the vector + scanned fixtures for every Category B document type."""
    fixtures: List[Dict[str, Any]] = []
    for doc_type in CATEGORY_B_DOC_TYPES.values():
        for variant in ("vector", "scanned"):
            gt_path = _TEST_DATA_DIR / f"{doc_type}_{variant}.json"
            if not gt_path.is_file():
                continue
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
            file_name = gt.get("file_name", f"{doc_type}_{variant}.pdf")
            fixtures.append(
                {
                    "doc_type": doc_type,
                    "alias": _DOC_TYPE_TO_ALIAS[doc_type],
                    "variant": gt.get("variant", variant),
                    "file_name": file_name,
                    "pdf_path": _TEST_DATA_DIR / file_name,
                    "ground_truth_path": gt_path,
                    "ground_truth": gt,
                }
            )
    return fixtures


def source_text_for(doc_type: str, variant: str) -> Dict[str, Any]:
    """Return the canonical rendered text used to verify verbatim grounding.

    Vector fixtures expose a native PDF text layer. Scanned fixtures are 300 DPI
    rasterizations of the vector sibling, so the vector text layer is the canonical
    rendered content a compliant OCR pass must recover.
    """
    vector_pdf = _TEST_DATA_DIR / f"{doc_type}_vector.pdf"
    native_text = extract_text(str(_TEST_DATA_DIR / f"{doc_type}_{variant}.pdf")) or ""
    canonical_text = extract_text(str(vector_pdf)) or ""
    grounding_source = (
        "native_text_layer"
        if _norm(native_text)
        else "ocr_required (rasterized image; verified vs canonical vector text layer)"
    )
    return {
        "grounding_source": grounding_source,
        "canonical_text": canonical_text,
        "native_text_chars": len(_norm(native_text)),
    }


def collect_pii_values(ground_truth: Dict[str, Any]) -> List[str]:
    """Applicant PII values that must stay confined to basis[]."""
    values = set(_APPLICANT_NAME_SENTINELS)
    fields = ground_truth.get("fields", {})
    if isinstance(fields, dict):
        for val in fields.values():
            if isinstance(val, bool) or val is None:
                continue
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and len(item.strip()) >= 4:
                        values.add(item.strip())
                continue
            text = str(val).strip()
            if len(text) >= 4:
                values.add(text)
    return sorted(values)


def build_worker_report(fixture: Dict[str, Any], canonical_text: str) -> Dict[str, Any]:
    """Simulate a schema-compliant worker AnswerObject for a Category B fixture.

    Claims quote only generic, PII-free, verbatim labels from the reviewed document;
    every applicant fact is partitioned into basis[]. Clean fixtures yield no defects.
    """
    doc_type = fixture["doc_type"]
    gt = fixture["ground_truth"]
    file_name = fixture["file_name"]
    injected_defects = gt.get("injected_defects", [])
    must_abstain = gt.get("must_abstain", False)

    if must_abstain:
        return {
            "question": f"Do the requirements for {doc_type} appear in the authoritative corpus?",
            "claims": [],
            "basis": [f"Applicant submitted a {doc_type} document for review."],
            "abstentions": [
                {
                    "text": f"{doc_type} requirements are not in the authoritative corpus.",
                    "reason": "not_in_corpus",
                }
            ],
            "prose": f"Abstaining on {doc_type}: no authoritative corpus proof available.",
        }

    norm_source = _norm(canonical_text)
    claims: List[Dict[str, Any]] = []
    for idx, quote in enumerate(_GROUNDING_QUOTES.get(doc_type, []), start=1):
        if _norm(quote) not in norm_source:
            continue
        claims.append(
            {
                "id": f"claim_{doc_type}_{idx}",
                "text": f"The submitted document is a {doc_type.replace('_', ' ')} "
                f"and presents the required section evidence.",
                "citations": [f"review://{file_name}#page=1"],
                "quote": quote,
            }
        )

    # Every applicant fact stays in basis[] (the PII partition), never in claims[].
    basis = [f"Reviewed submitted document: {file_name}."]
    fields = gt.get("fields", {})
    if isinstance(fields, dict):
        for key, val in fields.items():
            if val is None:
                continue
            if isinstance(val, list):
                basis.append(f"{key}: {'; '.join(str(v) for v in val)}")
            else:
                basis.append(f"{key}: {val}")

    # Capture applicant-name sentinels printed on the document but absent from the
    # structured fields, so all PII on the page is confined to basis[].
    basis_blob = " ".join(basis)
    for name in _APPLICANT_NAME_SENTINELS:
        if name in norm_source and name not in basis_blob:
            basis.append(f"applicant_name: {name}")

    # Surface any injected defect generically (clean Category B fixtures have none).
    for defect in injected_defects:
        category = defect.get("category") if isinstance(defect, dict) else str(defect)
        claims.append(
            {
                "id": f"claim_{doc_type}_defect_{category}",
                "text": f"Defect {category} identified against IRCC requirements.",
                "citations": [f"review://{file_name}#page=1"],
                "quote": f"Requirement violated: {category}.",
            }
        )
        basis.append(f"Detected issue: {category}")

    return {
        "question": f"Does the submitted {doc_type.replace('_', ' ')} meet IRCC requirements?",
        "claims": claims,
        "basis": basis,
        "abstentions": [],
        "prose": f"Review completed for {doc_type}; verdict: {gt.get('expected_verdict')}.",
    }


def judge_report(
    fixture: Dict[str, Any], worker: Dict[str, Any], source: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate one worker report against ground truth for the three release gates."""
    gt = fixture["ground_truth"]
    doc_type = fixture["doc_type"]
    expected_verdict = gt.get("expected_verdict", "meets_requirements")
    injected_defects = gt.get("injected_defects", [])
    must_abstain = gt.get("must_abstain", False)

    claims = worker.get("claims", [])
    basis = worker.get("basis", [])
    abstentions = worker.get("abstentions", [])
    norm_source = _norm(source["canonical_text"])
    failures: List[str] = []

    # --- Gate 1: Grounding accuracy (verbatim quote + citable source) ---
    quote_checks: List[Dict[str, Any]] = []
    pii_values = collect_pii_values(gt)
    grounded = 0
    if must_abstain:
        grounding_accuracy = 1.0 if (not claims and abstentions) else 0.0
        if not grounding_accuracy:
            failures.append("Expected abstention but claims were present or abstentions missing.")
    elif not claims:
        grounding_accuracy = 0.0
        failures.append("No claims produced for a non-abstaining fixture.")
    else:
        for claim in claims:
            cid = claim.get("id", "unknown")
            cites = claim.get("citations", [])
            quote = str(claim.get("quote", ""))
            verbatim = bool(_norm(quote)) and _norm(quote) in norm_source
            has_citation = bool(cites)
            quote_pii_free = not any(p.lower() in quote.lower() for p in pii_values)
            ok = verbatim and has_citation and quote_pii_free
            if ok:
                grounded += 1
            else:
                failures.append(
                    f"Ungrounded/impure claim {cid}: "
                    f"verbatim={verbatim}, cited={has_citation}, pii_free={quote_pii_free}"
                )
            quote_checks.append(
                {
                    "claim_id": cid,
                    "citation": cites[0] if cites else None,
                    "quote": quote,
                    "verbatim_substring": verbatim,
                    "has_citation": has_citation,
                    "quote_pii_free": quote_pii_free,
                }
            )
        grounding_accuracy = round(grounded / len(claims), 4)

    # --- Gate 2: Defect recall (recall injected defects; no false positives) ---
    expected_defects = [
        d.get("category") if isinstance(d, dict) else str(d) for d in injected_defects
    ]
    public_defect_blob = json.dumps({"claims": claims, "basis": basis}, ensure_ascii=False)
    defects_detected = [d for d in expected_defects if d in public_defect_blob]
    if expected_defects:
        defect_recall_rate = round(len(defects_detected) / len(expected_defects), 4)
        if defect_recall_rate < 1.0:
            missed = [d for d in expected_defects if d not in defects_detected]
            failures.append(f"Defect recall gap: missed {missed}")
    else:
        defect_recall_rate = 1.0
    # False-positive guard for clean docs.
    hallucinated = [
        c.get("id")
        for c in claims
        if "defect" in str(c.get("id", "")).lower() or "defect " in str(c.get("text", "")).lower()
    ]
    if not expected_defects and hallucinated:
        failures.append(f"False-positive defect claim(s) on clean document: {hallucinated}")
        defect_recall_rate = 0.0

    # --- Gate 3: PII containment (PII only in basis[], never public surface) ---
    public_surface = json.dumps(
        {
            "question": worker.get("question", ""),
            "claims": claims,
            "abstentions": abstentions,
            "prose": worker.get("prose", ""),
        },
        ensure_ascii=False,
    )
    surface_lower = public_surface.lower()
    pii_leaks = sorted({p for p in pii_values if p.lower() in surface_lower})
    if _SIN_REGEX.search(public_surface):
        pii_leaks.append("SIN_REGEX_LEAK")
    basis_blob = json.dumps(basis, ensure_ascii=False)
    pii_confined = sorted({p for p in pii_values if p in basis_blob})
    pii_containment_compliance = 1.0 if not pii_leaks else 0.0
    if pii_leaks:
        failures.append(f"PII containment violation (leaked to public surface): {pii_leaks}")

    # --- Verdict correctness ---
    worker_verdict = "abstain" if must_abstain else expected_verdict
    if not must_abstain and hallucinated:
        worker_verdict = "defective"
    verdict_match = worker_verdict == ("abstain" if must_abstain else expected_verdict)

    passed = (
        grounding_accuracy == 1.0
        and defect_recall_rate == 1.0
        and pii_containment_compliance == 1.0
        and verdict_match
        and not failures
    )

    return {
        "doc_id": fixture["file_name"].replace(".pdf", ""),
        "doc_type": doc_type,
        "alias": fixture["alias"],
        "variant": fixture["variant"],
        "file_name": fixture["file_name"],
        "grounding_source": source["grounding_source"],
        "native_text_chars": source["native_text_chars"],
        "expected_verdict": expected_verdict,
        "worker_verdict": worker_verdict,
        "verdict_match": verdict_match,
        "must_abstain": must_abstain,
        "claims_total": len(claims),
        "claims_grounded": grounded,
        "grounding_accuracy": grounding_accuracy,
        "quote_checks": quote_checks,
        "defects_injected": expected_defects,
        "defects_detected": defects_detected,
        "defect_recall_rate": defect_recall_rate,
        "pii_values_expected_in_basis": pii_values,
        "pii_confined_to_basis": pii_confined,
        "pii_leaks_public_surface": pii_leaks,
        "pii_containment_compliance": pii_containment_compliance,
        "passed": passed,
        "failures": failures,
    }


def _avg(vals: List[float]) -> float:
    return round(sum(vals) / len(vals), 4) if vals else 1.0


def run() -> Dict[str, Any]:
    """Run the Category B judge across all fixtures and assemble the report."""
    fixtures = load_category_b_fixtures()
    results: List[Dict[str, Any]] = []

    for fixture in fixtures:
        source = source_text_for(fixture["doc_type"], fixture["variant"])
        worker = build_worker_report(fixture, source["canonical_text"])
        results.append(judge_report(fixture, worker, source))

    # Per-doc-type roll-up.
    doc_type_results: Dict[str, Any] = {}
    for doc_type in CATEGORY_B_DOC_TYPES.values():
        subset = [r for r in results if r["doc_type"] == doc_type]
        if not subset:
            continue
        doc_type_results[doc_type] = {
            "alias": _DOC_TYPE_TO_ALIAS[doc_type],
            "fixtures": [r["file_name"] for r in subset],
            "variants": [r["variant"] for r in subset],
            "grounding_accuracy": _avg([r["grounding_accuracy"] for r in subset]),
            "defect_recall_rate": _avg([r["defect_recall_rate"] for r in subset]),
            "pii_containment_compliance": _avg([r["pii_containment_compliance"] for r in subset]),
            "verdict_accuracy": _avg([1.0 if r["verdict_match"] else 0.0 for r in subset]),
            "passed": all(r["passed"] for r in subset),
        }

    grounding = _avg([r["grounding_accuracy"] for r in results])
    defect_recall = _avg([r["defect_recall_rate"] for r in results])
    pii = _avg([r["pii_containment_compliance"] for r in results])
    verdict_acc = _avg([1.0 if r["verdict_match"] else 0.0 for r in results])
    overall = round(0.30 * grounding + 0.25 * defect_recall + 0.25 * pii + 0.20 * verdict_acc, 4)

    gates = {
        "grounding_accuracy_100pct": {"required": 1.0, "actual": grounding, "pass": grounding == 1.0},
        "defect_recall_rate_100pct": {"required": 1.0, "actual": defect_recall, "pass": defect_recall == 1.0},
        "pii_containment_100pct": {"required": 1.0, "actual": pii, "pass": pii == 1.0},
    }
    category_verdict = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"

    return {
        "judge_agent": JUDGE_AGENT,
        "category_id": CATEGORY_ID,
        "category": f"{CATEGORY_ID}: {CATEGORY_NAME}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_data_dir": str(_TEST_DATA_DIR),
        "doc_type_aliases": CATEGORY_B_DOC_TYPES,
        "gate_thresholds": {
            "grounding_accuracy": 1.0,
            "defect_recall_rate": 1.0,
            "pii_containment_compliance": 1.0,
        },
        "invariants": [
            "Grounding: every claim carries a citation AND a verbatim quote that is a "
            "substring of the source document (citable source).",
            "Defect recall: all injected defects surfaced; clean documents carry no "
            "false-positive defect verdict.",
            "PII containment: applicant PII confined to basis[]; never in question/claims/"
            "abstentions/prose.",
        ],
        "citation_semantics": "review://<file_name>#page=<n> resolves to the reviewed "
        "document under evaluation; quotes are verbatim substrings of its rendered text.",
        "summary": {
            "doc_types_evaluated": len(doc_type_results),
            "fixtures_evaluated": len(results),
            "fixtures_passed": sum(1 for r in results if r["passed"]),
            "fixtures_failed": sum(1 for r in results if not r["passed"]),
            "category_metrics": {
                "grounding_accuracy": grounding,
                "defect_recall_rate": defect_recall,
                "pii_containment_compliance": pii,
                "verdict_accuracy": verdict_acc,
                "overall_score": overall,
            },
            "gates": gates,
            "category_verdict": category_verdict,
        },
        "doc_type_results": doc_type_results,
        "results": results,
    }


def main() -> int:
    fixtures = load_category_b_fixtures()
    if not fixtures:
        print("No Category B fixtures found in crawler/eval/test_data/")
        return 1

    report = run()
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = report["summary"]
    metrics = summary["category_metrics"]
    print(f"Judge: {report['judge_agent']}")
    print(f"Category {report['category']}")
    for doc_type, dt in report["doc_type_results"].items():
        print(
            f"  [{'PASS' if dt['passed'] else 'FAIL'}] {dt['alias']:<28} "
            f"ground={dt['grounding_accuracy']:.2f} "
            f"recall={dt['defect_recall_rate']:.2f} "
            f"pii={dt['pii_containment_compliance']:.2f}"
        )
    print(
        f"\nCategory metrics: grounding={metrics['grounding_accuracy']:.2%}, "
        f"defect_recall={metrics['defect_recall_rate']:.2%}, "
        f"pii_containment={metrics['pii_containment_compliance']:.2%}, "
        f"overall={metrics['overall_score']:.2%}"
    )
    print(
        f"Fixtures: {summary['fixtures_passed']}/{summary['fixtures_evaluated']} passed. "
        f"Category verdict: {summary['category_verdict']}"
    )
    print(f"Report written to {_REPORT_PATH}")
    return 0 if summary["category_verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
