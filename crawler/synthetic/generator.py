"""Synthetic PDF Document Generator for Express Entry documents and LoEs.

Generates programmatic vector PDF bytes using ReportLab Platypus templates for all 22
Express Entry e-APR supporting document types plus Letters of Explanation (LoE),
with support for parametric profile injection and defect mutations.
"""

import io
import logging
from typing import Any, Dict, List, Optional, Union

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate

from crawler.synthetic.defects import DefectCategory, inject_defect
from crawler.synthetic.schemas import (
    ExpressEntryDocType,
    SyntheticDocument,
    SyntheticProfile,
    TestCaseSpec,
)
from crawler.synthetic.templates import build_document_story, get_doc_template

logger = logging.getLogger(__name__)


class SanitizedMetadataCanvas(canvas.Canvas):
    """Custom ReportLab canvasmaker class that explicitly overrides metadata properties per D-07, D-08."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setTitle("")
        self.setAuthor("")
        self.setSubject("")
        self.setKeywords([])
        self.setCreator("PDF Engine")
        if hasattr(self, "_doc") and hasattr(self._doc, "info"):
            self._doc.info.producer = "PDF Engine"

    def save(self):
        self.setTitle("")
        self.setAuthor("")
        self.setSubject("")
        self.setKeywords([])
        self.setCreator("PDF Engine")
        if hasattr(self, "_doc") and hasattr(self._doc, "info"):
            self._doc.info.producer = "PDF Engine"
        super().save()


def render_vector_pdf_bytes(case_spec: TestCaseSpec) -> bytes:
    """Compile a TestCaseSpec into a metadata-sanitized ReportLab vector PDF byte stream.

    Args:
        case_spec: Agent-authored TestCaseSpec object.

    Returns:
        Compiled vector PDF bytes.
    """
    story = build_document_story(case_spec)
    buffer = io.BytesIO()
    doc_pdf = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
        title="",
        author="",
        subject="",
        canvasmaker=SanitizedMetadataCanvas,
    )
    doc_pdf.build(story)
    return buffer.getvalue()



def default_fields_for_type(dt_str: str, profile_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Provide realistic default document fields for any Express Entry document type."""
    name = profile_dict.get("applicant_name", "Jane Doe")
    dob = profile_dict.get("date_of_birth", "1992-05-14")
    country = profile_dict.get("citizenship", "Canada")

    defaults: Dict[str, Dict[str, Any]] = {
        ExpressEntryDocType.PASSPORT.value: {
            "passport_number": "N9823411",
            "issuing_country": country,
            "full_name": name,
            "dob": dob,
            "issue_date": "2020-01-15",
            "expiry_date": "2030-01-15",
        },
        ExpressEntryDocType.LANGUAGE_TEST.value: {
            "test_type": "IELTS",
            "registration_number": "TRF-2024-883921",
            "test_date": "2024-03-10",
            "listening": 8.5,
            "reading": 8.0,
            "writing": 7.5,
            "speaking": 7.5,
        },
        ExpressEntryDocType.ECA.value: {
            "agency": "WES",
            "ref_number": "WES-4920193",
            "issue_date": "2023-11-20",
            "degree_evaluated": "Bachelor of Science in Computer Science",
            "canadian_equivalence": "Bachelor's degree (four years)",
        },
        ExpressEntryDocType.EMPLOYMENT_REFERENCE.value: {
            "employer_name": "Acme Software Solutions Ltd.",
            "job_title": "Software Engineer",
            "noc_code": "21231",
            "start_date": "2021-01-15",
            "end_date": None,
            "hours_per_week": 37.5,
            "annual_salary": 95000.0,
            "lead_statement": "Lead engineer responsible for NOC 21231 cloud software development.",
            "main_duties": [
                "Analyze user requirements and engineer resilient cloud microservices.",
                "Write clean, maintainable Python and TypeScript web applications.",
                "Conduct unit testing, code reviews, and automated CI/CD deployment pipelines.",
            ],
            "supervisor_name": "Alex Mercer",
            "supervisor_title": "Engineering Director",
            "contact_email": "hr@acmesoftware.com",
        },
        ExpressEntryDocType.PROOF_OF_FUNDS.value: {
            "bank_name": "Global First Bank",
            "account_number": "ACCT-981204",
            "account_type": "Chequing",
            "current_balance": 18500.0,
            "average_balance_6mo": 17200.0,
            "outstanding_debts": 0.0,
            "issue_date": "2024-06-01",
            "is_unencumbered": True,
        },
        ExpressEntryDocType.MEDICAL_EXAM.value: {
            "ime_number": "IME-99201948",
            "umi_number": "UMI-1029381",
            "exam_date": "2024-05-18",
            "clinic_name": "Metro Panel Physician Clinic",
            "doctor_name": "Dr. Sarah Jenkins",
            "panel_physician_id": "PP-881",
            "result_status": "COMPLETE - PASSED",
        },
        ExpressEntryDocType.POLICE_CERTIFICATE.value: {
            "country": country,
            "issue_date": "2024-04-01",
            "subject_name": name,
            "is_clear": True,
            "offenses": [],
            "residence_start_date": "2015-01-01",
            "residence_end_date": "2024-03-31",
        },
        ExpressEntryDocType.LETTER_OF_EXPLANATION.value: {
            "topic": "bank_balance_fluctuation",
            "explanation_text": (
                "I am writing to explain a temporary fluctuation in my bank balance during March 2024. "
                "A deposit of $10,000 CAD was made from my personal savings investment liquidation. "
                "Attached please find official bank transaction records and liquidation receipts."
            ),
            "corroborating_docs_attached": [
                "Investment Liquidation Confirmation Receipt",
                "Official Bank Transfer Statement",
            ],
            "author_signature_date": "2024-08-01",
        },
    }

    if dt_str in defaults:
        return defaults[dt_str].copy()

    # Generic default map for other doc types
    return {
        "full_name": name,
        "dob": dob,
        "issuing_authority": f"Official Government Registry of {country}",
        "registration_number": "REG-88301928",
        "issue_date": "2024-01-15",
    }


def generate_synthetic_document(
    doc_type: Union[ExpressEntryDocType, str],
    profile_data: Optional[Union[SyntheticProfile, Dict[str, Any]]] = None,
    defects: Optional[Union[List[Union[DefectCategory, str]], DefectCategory, str]] = None,
) -> bytes:
    """Generate a vector PDF byte string for any of the 22 Express Entry document types + LoE.

    Args:
        doc_type: ExpressEntryDocType enum or doc_type string.
        profile_data: SyntheticProfile dataclass or dictionary.
        defects: Optional defect or list of defects to inject into the document.

    Returns:
        Vector PDF bytes.
    """
    dt_str = doc_type.value if isinstance(doc_type, ExpressEntryDocType) else str(doc_type)

    if isinstance(profile_data, SyntheticProfile):
        profile_dict = {
            "applicant_name": profile_data.applicant_name,
            "date_of_birth": profile_data.date_of_birth,
            "citizenship": profile_data.citizenship,
            "country_of_residence": profile_data.country_of_residence,
            "marital_status": profile_data.marital_status,
        }
    elif isinstance(profile_data, dict):
        profile_dict = profile_data.copy()
    else:
        profile_dict = {
            "applicant_name": "Jane Doe",
            "date_of_birth": "1992-05-14",
            "citizenship": "Canada",
            "country_of_residence": "Canada",
            "marital_status": "Single",
        }

    fields = default_fields_for_type(dt_str, profile_dict)

    # Wrap as SyntheticDocument for defect injection if requested
    synth_doc = SyntheticDocument(
        doc_id=f"DOC-{dt_str.upper()[:10]}-01",
        doc_type=ExpressEntryDocType(dt_str) if dt_str in [e.value for e in ExpressEntryDocType] else dt_str,
        title=f"Synthetic {dt_str.replace('_', ' ').title()}",
        issuing_authority="Official Authority",
        issue_date=fields.get("issue_date", "2024-01-15"),
        fields=fields,
    )

    if defects:
        defect_list = defects if isinstance(defects, list) else [defects]
        for d in defect_list:
            synth_doc, _ = inject_defect(synth_doc, d)

    story = get_doc_template(dt_str, profile_data=profile_dict, fields=synth_doc.fields)

    buffer = io.BytesIO()
    doc_pdf = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
        title="",
        author="",
        subject="",
        canvasmaker=SanitizedMetadataCanvas,
    )
    doc_pdf.build(story)

    return buffer.getvalue()
