"""Defect Injection Taxonomy & Parametric Mutators.

Defines the DefectCategory taxonomy for post-ITA e-APR defects and provides
parametric mutators (inject_defect) to generate defective synthetic document
fixtures along with matching GroundTruthSpec evaluation models.
"""

import copy
from enum import Enum
from typing import Tuple, Union

from crawler.synthetic.schemas import (
    ExpressEntryDocType,
    GroundTruthSpec,
    InjectedDefect,
    SyntheticDocument,
)


class DefectCategory(str, Enum):
    """Taxonomy of injected document defects and post-ITA discrepancies."""

    MISSING_MANDATORY_FIELD = "missing_mandatory_field"
    UNENCUMBERED_FUNDS_VIOLATION = "unencumbered_funds_violation"
    EXPIRED_CREDENTIAL = "expired_credential"
    DATE_MISMATCH = "date_mismatch"
    POLICE_CERT_GAP = "police_cert_gap"
    LOE_UNSUBSTANTIATED_CLAIM = "loe_unsubstantiated_claim"


def inject_defect(
    doc: SyntheticDocument,
    defect_category: Union[DefectCategory, str],
) -> Tuple[SyntheticDocument, GroundTruthSpec]:
    """Inject a parametric defect into a synthetic document and produce matching GroundTruthSpec.

    Args:
        doc: The base synthetic document fixture.
        defect_category: The DefectCategory or category string to inject.

    Returns:
        Tuple of (mutated_doc, ground_truth_spec).
    """
    category_str = (
        defect_category.value
        if isinstance(defect_category, DefectCategory)
        else str(defect_category)
    )

    mutated_doc = copy.deepcopy(doc)
    defect_id = f"DEF-{category_str.upper()[:12]}-01"

    injected = InjectedDefect(
        defect_id=defect_id,
        category=category_str,
        target_doc=str(doc.doc_type),
        severity="critical",
        description=f"Injected defect: {category_str} into {doc.title}",
    )

    expected_basis_keys = list(mutated_doc.fields.keys())

    if category_str == DefectCategory.MISSING_MANDATORY_FIELD.value:
        injected.field_name = "lead_statement"
        injected.description = "Missing required NOC lead statement or weekly working hours."
        injected.remediation_guidance = "Obtain an updated reference letter containing explicit NOC lead duties and weekly hours."
        if "lead_statement" in mutated_doc.fields:
            del mutated_doc.fields["lead_statement"]
        if "hours_per_week" in mutated_doc.fields:
            del mutated_doc.fields["hours_per_week"]
        if mutated_doc.raw_text:
            mutated_doc.raw_text = mutated_doc.raw_text.replace("Hours per week:", "N/A:")

    elif category_str == DefectCategory.UNENCUMBERED_FUNDS_VIOLATION.value:
        injected.field_name = "current_balance"
        injected.description = "Bank balance ($4,200 CAD) is below IRCC 1-person LICO minimum threshold ($14,690 CAD) or funds are encumbered."
        injected.remediation_guidance = "Provide updated financial proof demonstrating unencumbered, liquid funds meeting LICO requirements."
        mutated_doc.fields["current_balance"] = 4200.0
        mutated_doc.fields["is_unencumbered"] = False
        if mutated_doc.raw_text:
            mutated_doc.raw_text = mutated_doc.raw_text.replace("14,200", "4,200")

    elif category_str == DefectCategory.EXPIRED_CREDENTIAL.value:
        injected.field_name = "expiry_date"
        injected.description = "Document or test credential issue date exceeds IRCC validity period (e.g., language test older than 2 years)."
        injected.remediation_guidance = "Provide a valid language test result or credential issued within IRCC validity limits."
        mutated_doc.issue_date = "2021-01-15"
        mutated_doc.expiry_date = "2023-01-15"
        mutated_doc.fields["issue_date"] = "2021-01-15"
        mutated_doc.fields["expiry_date"] = "2023-01-15"

    elif category_str == DefectCategory.DATE_MISMATCH.value:
        injected.field_name = "start_date"
        injected.description = "Inconsistent or overlapping dates across document records (e.g., employment start date postdates end date)."
        injected.remediation_guidance = "Provide corrected documentation reconciling date discrepancies across official records."
        mutated_doc.fields["start_date"] = "2025-06-01"
        mutated_doc.fields["end_date"] = "2023-01-01"

    elif category_str == DefectCategory.POLICE_CERT_GAP.value:
        injected.field_name = "residence_coverage"
        injected.description = "Police certificate coverage contains a gap of 6+ consecutive months for country of residence."
        injected.remediation_guidance = "Obtain an updated police certificate covering the entire duration of residence."
        mutated_doc.fields["is_clear"] = False
        mutated_doc.fields["residence_gap_months"] = 8

    elif category_str == DefectCategory.LOE_UNSUBSTANTIATED_CLAIM.value:
        injected.field_name = "corroborating_docs_attached"
        injected.description = "Letter of Explanation asserts claims (e.g., gift deed or bank balance fluctuation) without corroborating evidence."
        injected.remediation_guidance = "Attach official bank deposit receipts or sworn affidavits substantiating the Letter of Explanation claims."
        mutated_doc.fields["corroborating_docs_attached"] = []

    else:
        injected.description = f"Generic injected defect category: {category_str}"

    gt_spec = GroundTruthSpec(
        doc_type=str(doc.doc_type),
        expected_verdict="defective",
        injected_defects=[injected],
        expected_claims=[
            {
                "claim_id": f"CLAIM-{defect_id}",
                "text": f"Document {doc.title} contains defect {category_str}",
                "severity": injected.severity,
            }
        ],
        expected_basis_keys=expected_basis_keys,
        must_abstain=False,
    )

    return mutated_doc, gt_spec
