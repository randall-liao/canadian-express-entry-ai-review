"""ReportLab Platypus document templates for Express Entry documents.

Provides structured layout templates, custom styles, tables, and header/footer overlays
covering all 22 Express Entry document types plus Letters of Explanation (LoE).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from crawler.synthetic.downloader import (
    get_header_logo_path,
    get_seal_image_path,
    get_stamp_image_path,
    get_watermark_image_path,
)
from crawler.synthetic.schemas import ExpressEntryDocType, TestCaseSpec

logger = logging.getLogger(__name__)


def create_base_styles() -> Dict[str, ParagraphStyle]:
    """Create a dictionary of standardized ReportLab paragraph styles."""
    styles = getSampleStyleSheet()
    
    custom_styles = {
        "Title": ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1A365D"),
            alignment=1,  # Center
            spaceAfter=10,
        ),
        "Header": ParagraphStyle(
            "DocHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#2B6CB0"),
            spaceAfter=6,
        ),
        "SubTitle": ParagraphStyle(
            "DocSubTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#4A5568"),
            alignment=1,
            spaceAfter=12,
        ),
        "Body": ParagraphStyle(
            "DocBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#2D3748"),
            spaceAfter=6,
        ),
        "BodyBold": ParagraphStyle(
            "DocBodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1A202C"),
            spaceAfter=6,
        ),
        "Bullet": ParagraphStyle(
            "DocBullet",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            leftIndent=15,
            textColor=colors.HexColor("#2D3748"),
            spaceAfter=4,
        ),
        "SmallNote": ParagraphStyle(
            "DocSmallNote",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#718096"),
            spaceAfter=4,
        ),
    }
    return custom_styles


def build_key_value_table(
    data_dict: Dict[str, Any],
    col_widths: Optional[List[float]] = None,
    styles: Optional[Dict[str, ParagraphStyle]] = None,
) -> Table:
    """Build a clean two-column key-value summary table."""
    if styles is None:
        styles = create_base_styles()

    col_widths = col_widths or [180.0, 320.0]
    table_rows = []

    for key, val in data_dict.items():
        key_str = str(key).replace("_", " ").title() + ":"
        val_str = str(val) if val is not None else "N/A"
        
        p_key = Paragraph(f"<b>{key_str}</b>", styles["BodyBold"])
        p_val = Paragraph(val_str, styles["Body"])
        table_rows.append([p_key, p_val])

    t = Table(table_rows, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
            ]
        )
    )
    return t


def build_data_grid(
    headers: List[str],
    rows: List[List[Any]],
    col_widths: Optional[List[float]] = None,
    styles: Optional[Dict[str, ParagraphStyle]] = None,
) -> Table:
    """Build a multi-column data grid table with styled header row."""
    if styles is None:
        styles = create_base_styles()

    grid_data = []
    header_row = [Paragraph(f"<b>{h}</b>", styles["BodyBold"]) for h in headers]
    grid_data.append(header_row)

    for r in rows:
        row_cells = [
            Paragraph(str(cell), styles["Body"]) if not isinstance(cell, Paragraph) else cell
            for cell in r
        ]
        grid_data.append(row_cells)

    t = Table(grid_data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1A202C")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ]
        )
    )
    return t


def get_doc_template(
    doc_type: Union[ExpressEntryDocType, str],
    profile_data: Optional[Dict[str, Any]] = None,
    fields: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    """Generate a ReportLab Platypus flowable story for any of the 22 doc types + LoE.

    Args:
        doc_type: ExpressEntryDocType enum or string matching the document type.
        profile_data: Optional applicant profile dict.
        fields: Optional document field overrides.

    Returns:
        List of ReportLab Flowable objects representing the document.
    """
    dt_str = doc_type.value if isinstance(doc_type, ExpressEntryDocType) else str(doc_type)
    profile = profile_data or {}
    f_data = fields or {}
    styles = create_base_styles()
    story = []

    applicant_name = str(profile.get("applicant_name") or f_data.get("full_name") or "Jane Doe")
    dob = str(profile.get("date_of_birth") or f_data.get("dob") or "1992-05-14")
    citizenship = str(profile.get("citizenship") or f_data.get("issuing_country") or "Canada")

    # Top Header Logo / Seal
    try:
        logo_path = get_header_logo_path()
        story.append(Image(str(logo_path), width=120, height=35))
        story.append(Spacer(1, 8))
    except Exception:
        pass

    if dt_str in [ExpressEntryDocType.PASSPORT.value, "passport"]:
        story.append(Paragraph(f"REPUBLIC OF {citizenship.upper()} - PASSPORT", styles["Title"]))
        story.append(Paragraph("OFFICIAL TRAVEL DOCUMENT / PASSEPORT OFFICIEL", styles["SubTitle"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A365D"), spaceAfter=12))

        passport_fields = {
            "Passport Number": f_data.get("passport_number") or "N9823411",
            "Full Name": applicant_name,
            "Nationality": citizenship,
            "Date of Birth": dob,
            "Issuing Country": citizenship,
            "Issue Date": f_data.get("issue_date") or "2020-01-15",
            "Expiry Date": f_data.get("expiry_date") or "2030-01-15",
        }
        story.append(build_key_value_table(passport_fields, styles=styles))
        story.append(Spacer(1, 20))

        mrz = f_data.get("mrz_code")
        if not mrz or not isinstance(mrz, str):
            mrz = f"P<{citizenship[:3].upper()}{applicant_name.replace(' ', '<').upper()}<<<<<<<<<<<<<<\nN9823411<8{citizenship[:3].upper()}9205140M3001153<<<<<<<<<<<<<<02"
        mrz_style = ParagraphStyle("MRZ", parent=styles["Body"], fontName="Courier-Bold", fontSize=9, leading=12)
        story.append(Paragraph(f"<b>MRZ CODE:</b><br/>{mrz.replace(chr(10), '<br/>')}", mrz_style))

    elif dt_str in [ExpressEntryDocType.LANGUAGE_TEST.value, "language_test"]:
        test_type = str(f_data.get("test_type") or "IELTS")
        story.append(Paragraph(f"OFFICIAL {test_type.upper()} LANGUAGE TEST REPORT FORM", styles["Title"]))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2B6CB0"), spaceAfter=12))

        candidate_info = {
            "Candidate Name": applicant_name,
            "Date of Birth": dob,
            "Test Registration No": f_data.get("registration_number") or "TRF-2024-883921",
            "Test Date": f_data.get("test_date") or "2024-03-10",
            "Test Center": "Global Language Assessment Center #402",
        }
        story.append(build_key_value_table(candidate_info, styles=styles))
        story.append(Spacer(1, 15))

        headers = ["Skill", "Score Band", "IRCC CLB Level"]
        rows = [
            ["Listening", f_data.get("listening") if f_data.get("listening") is not None else 8.5, "CLB 9"],
            ["Reading", f_data.get("reading") if f_data.get("reading") is not None else 8.0, "CLB 9"],
            ["Writing", f_data.get("writing") if f_data.get("writing") is not None else 7.5, "CLB 9"],
            ["Speaking", f_data.get("speaking") if f_data.get("speaking") is not None else 7.5, "CLB 9"],
        ]
        story.append(build_data_grid(headers, rows, col_widths=[150, 150, 200], styles=styles))

    elif dt_str in [ExpressEntryDocType.ECA.value, "educational_credential_assessment"]:
        agency = str(f_data.get("agency") or "WES")
        story.append(Paragraph(f"{agency} - EDUCATIONAL CREDENTIAL ASSESSMENT REPORT", styles["Title"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2B6CB0"), spaceAfter=12))

        eca_info = {
            "Applicant Name": applicant_name,
            "WES Reference Number": f_data.get("ref_number") or "WES-4920193",
            "Date of Issue": f_data.get("issue_date") or "2023-11-20",
            "Primary Degree Evaluated": f_data.get("degree_evaluated") or "Bachelor of Science in Computer Science",
            "Canadian Academic Equivalency": f_data.get("canadian_equivalence") or "Bachelor's degree (four years)",
        }
        story.append(build_key_value_table(eca_info, styles=styles))

    elif dt_str in [ExpressEntryDocType.EMPLOYMENT_REFERENCE.value, "employment_reference_letter"]:
        employer = str(f_data.get("employer_name") or "Acme Software Solutions Ltd.")
        story.append(Paragraph(f"{employer.upper()}", styles["Title"]))
        story.append(Paragraph("HUMAN RESOURCES - EMPLOYMENT REFERENCE LETTER", styles["SubTitle"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A365D"), spaceAfter=12))

        story.append(Paragraph("<b>Date:</b> October 12, 2024", styles["Body"]))
        story.append(Paragraph("<b>To:</b> Immigration, Refugees and Citizenship Canada (IRCC)", styles["Body"]))
        story.append(Paragraph(f"<b>Re:</b> Employment Verification for {applicant_name}", styles["BodyBold"]))
        story.append(Spacer(1, 10))

        lead_stmt = str(f_data.get("lead_statement") or "This letter confirms that the employee performed all primary duties under NOC 21231 (Software Engineers).")
        story.append(Paragraph(f"This letter certifies that {applicant_name} was employed with {employer} as a <b>{f_data.get('job_title') or 'Software Engineer'}</b> (NOC Code: <b>{f_data.get('noc_code') or '21231'}</b>). {lead_stmt}", styles["Body"]))
        story.append(Spacer(1, 8))

        hrs_raw = f_data.get('hours_per_week')
        try:
            hrs_val = f"{float(hrs_raw):.1f} hours/week" if hrs_raw is not None else "37.5 hours/week"
        except (ValueError, TypeError):
            hrs_val = f"{hrs_raw} hours/week"

        sal_raw = f_data.get('annual_salary')
        try:
            sal_val = f"${float(sal_raw):,.2f} CAD" if sal_raw is not None else "$95,000.00 CAD"
        except (ValueError, TypeError):
            sal_val = f"${sal_raw} CAD"

        ref_details = {
            "Employment Dates": f"{f_data.get('start_date') or '2021-01-15'} to {f_data.get('end_date') or 'Present'}",
            "Weekly Working Hours": hrs_val,
            "Annual Base Salary": sal_val,
        }
        story.append(build_key_value_table(ref_details, styles=styles))
        story.append(Spacer(1, 10))

        story.append(Paragraph("<b>Main Duties & Responsibilities:</b>", styles["BodyBold"]))
        duties = f_data.get("main_duties") or [
            "Analyze user requirements and engineer resilient cloud microservices.",
            "Write clean, maintainable Python and TypeScript web applications.",
            "Conduct unit testing, code reviews, and automated CI/CD deployment pipelines."
        ]
        for d in duties:
            story.append(Paragraph(f"• {d}", styles["Bullet"]))

        story.append(Spacer(1, 15))
        story.append(Paragraph(f"<b>Supervisor:</b> {f_data.get('supervisor_name') or 'Alex Mercer'}, {f_data.get('supervisor_title') or 'Engineering Director'}", styles["Body"]))
        story.append(Paragraph(f"<b>Contact Email:</b> {f_data.get('contact_email') or 'hr@acmesoftware.com'}", styles["Body"]))

    elif dt_str in [ExpressEntryDocType.PROOF_OF_FUNDS.value, "proof_of_funds"]:
        bank = str(f_data.get("bank_name") or "Global First Bank")
        story.append(Paragraph(f"{bank.upper()} - FINANCIAL ACCOUNT STATEMENT", styles["Title"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2B6CB0"), spaceAfter=12))

        story.append(Paragraph(f"<b>Date:</b> {f_data.get('issue_date') or '2024-06-01'}", styles["Body"]))
        story.append(Paragraph(f"<b>Client Name:</b> {applicant_name}", styles["BodyBold"]))
        story.append(Paragraph("<b>Re:</b> Confirmation of Financial Account Balances and Liabilities", styles["Body"]))
        story.append(Spacer(1, 10))

        unenc = "unencumbered, fully liquid, and free of liens" if f_data.get("is_unencumbered", True) else "encumbered / restricted"
        story.append(Paragraph(f"We confirm that the account holder maintains active accounts with our institution. All funds listed are {unenc}.", styles["Body"]))
        story.append(Spacer(1, 10))

        headers = ["Account Number", "Type", "Current Balance", "6-Month Avg Balance"]
        curr_bal_raw = f_data.get("current_balance")
        try:
            curr_bal_str = f"${float(curr_bal_raw):,.2f} CAD" if curr_bal_raw is not None else "$18,500.00 CAD"
        except (ValueError, TypeError):
            curr_bal_str = f"${curr_bal_raw} CAD"

        avg_bal_raw = f_data.get("average_balance_6mo")
        try:
            avg_bal_str = f"${float(avg_bal_raw):,.2f} CAD" if avg_bal_raw is not None else "$17,200.00 CAD"
        except (ValueError, TypeError):
            avg_bal_str = f"${avg_bal_raw} CAD"

        rows = [
            [str(f_data.get("account_number") or "ACCT-981204"), str(f_data.get("account_type") or "Chequing"), curr_bal_str, avg_bal_str],
        ]
        story.append(build_data_grid(headers, rows, col_widths=[120, 100, 140, 140], styles=styles))
        story.append(Spacer(1, 10))

        debts_raw = f_data.get("outstanding_debts")
        try:
            debts_str = f"${float(debts_raw):,.2f} CAD" if debts_raw is not None else "$0.00 CAD"
        except (ValueError, TypeError):
            debts_str = f"${debts_raw} CAD"
        story.append(Paragraph(f"<b>Total Outstanding Debts/Loans:</b> {debts_str}", styles["BodyBold"]))

    elif dt_str in [ExpressEntryDocType.MEDICAL_EXAM.value, "medical_examination"]:
        story.append(Paragraph("IRCC eMEDICAL INFORMATION SHEET - IMMIGRATION MEDICAL EXAM", styles["Title"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2B6CB0"), spaceAfter=12))

        med_info = {
            "IME Number": f_data.get("ime_number") or "IME-99201948",
            "UMI Number": f_data.get("umi_number") or "UMI-1029381",
            "Patient Name": applicant_name,
            "Exam Date": f_data.get("exam_date") or "2024-05-18",
            "Clinic Name": f_data.get("clinic_name") or "Metro Panel Physician Clinic",
            "Panel Physician": f_data.get("doctor_name") or "Dr. Sarah Jenkins (ID: PP-881)",
            "Medical Result Status": f_data.get("result_status") or "COMPLETE - PASSED",
        }
        story.append(build_key_value_table(med_info, styles=styles))

    elif dt_str in [ExpressEntryDocType.POLICE_CERTIFICATE.value, "police_certificate"]:
        country = str(f_data.get("country") or "India")
        story.append(Paragraph(f"NATIONAL POLICE CLEARANCE CERTIFICATE - {country.upper()}", styles["Title"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A365D"), spaceAfter=12))

        clear_status = "NO CRIMINAL RECORD FOUND" if f_data.get("is_clear", True) else "OFFENSES RECORDED"
        pc_info = {
            "Subject Name": applicant_name,
            "Date of Birth": dob,
            "Issuing Country": country,
            "Date of Issue": f_data.get("issue_date") or "2024-04-01",
            "Clearance Verdict": clear_status,
            "Residence Coverage": f"{f_data.get('residence_start_date') or '2015-01-01'} to {f_data.get('residence_end_date') or '2024-03-31'}",
        }
        story.append(build_key_value_table(pc_info, styles=styles))

    elif dt_str in [ExpressEntryDocType.LETTER_OF_EXPLANATION.value, "letter_of_explanation"]:
        topic = str(f_data.get("topic") or "bank_balance_fluctuation")
        story.append(Paragraph("LETTER OF EXPLANATION (LoE)", styles["Title"]))
        story.append(Paragraph(f"RE: EXPLANATION REGARDING {topic.upper().replace('_', ' ')}", styles["SubTitle"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2B6CB0"), spaceAfter=12))

        story.append(Paragraph("<b>To:</b> Immigration, Refugees and Citizenship Canada (IRCC)", styles["Body"]))
        story.append(Paragraph(f"<b>From:</b> {applicant_name}", styles["BodyBold"]))
        story.append(Paragraph(f"<b>Date:</b> {f_data.get('author_signature_date') or '2024-08-01'}", styles["Body"]))
        story.append(Spacer(1, 10))

        text = f_data.get(
            "explanation_text",
            "I am submitting this Letter of Explanation to clarify my application details. "
            "All supporting documents provided are authentic, true, and complete."
        )
        story.append(Paragraph(text, styles["Body"]))
        story.append(Spacer(1, 10))

        docs = f_data.get("corroborating_docs_attached") or ["Official Bank Transfer Receipt", "Gift Deed Affidavit"]
        if docs:
            story.append(Paragraph("<b>Corroborating Documents Attached:</b>", styles["BodyBold"]))
            for doc_item in docs:
                story.append(Paragraph(f"• {doc_item}", styles["Bullet"]))

    else:
        # Generic document template builder for remaining document types
        doc_title = dt_str.upper().replace("_", " ")
        story.append(Paragraph(f"OFFICIAL DOCUMENT: {doc_title}", styles["Title"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2B6CB0"), spaceAfter=12))

        gen_info = {
            "Document Type": dt_str,
            "Primary Subject": applicant_name,
            "Date of Birth": dob,
            "Issue Date": f_data.get("issue_date", "2024-01-01"),
            "Registration / Reference No": f_data.get("registration_number", f_data.get("certificate_number", "REF-9920184")),
        }
        # Merge remaining field overrides
        for k, v in f_data.items():
            if k not in gen_info and not isinstance(v, (list, dict)):
                gen_info[k] = v

        story.append(build_key_value_table(gen_info, styles=styles))

    # Stamp / Seal Footer Flowable
    try:
        seal_path = get_seal_image_path()
        story.append(Spacer(1, 15))
        story.append(Image(str(seal_path), width=60, height=60))
    except Exception:
        pass

    return story


def build_document_story(case_spec: TestCaseSpec) -> List[Any]:
    """Generate a ReportLab Platypus flowable story from a TestCaseSpec.

    Args:
        case_spec: Agent-authored TestCaseSpec instance.

    Returns:
        List of ReportLab Flowable objects representing the document.
    """
    dt_str = case_spec.doc_type.value if isinstance(case_spec.doc_type, ExpressEntryDocType) else str(case_spec.doc_type)
    fields = case_spec.fields.copy() if case_spec.fields else {}

    if case_spec.issuing_authority:
        fields.setdefault("issuing_authority", case_spec.issuing_authority)
    if case_spec.issue_date:
        fields.setdefault("issue_date", case_spec.issue_date)
    if case_spec.expiry_date:
        fields.setdefault("expiry_date", case_spec.expiry_date)

    story = get_doc_template(doc_type=dt_str, profile_data=None, fields=fields)

    # Append custom narrative_blocks from case_spec if present
    if case_spec.narrative_blocks:
        styles = create_base_styles()
        story.append(Spacer(1, 15))
        story.append(Paragraph("<b>Narrative Statements / Detailed Notes:</b>", styles["BodyBold"]))
        for block in case_spec.narrative_blocks:
            story.append(Paragraph(str(block), styles["Body"]))
            story.append(Spacer(1, 6))

    # Assert no explanatory defect annotations are present in fields or narrative_blocks per D-08
    banned_annotations = ["defective", "missing field", "expired credential", "pfl trigger", "synthetic test"]
    all_text_blobs = [str(v) for v in fields.values()] + [str(b) for b in (case_spec.narrative_blocks or [])]
    for blob in all_text_blobs:
        blob_lower = blob.lower()
        for banned in banned_annotations:
            if banned in blob_lower:
                raise ValueError(f"Explanatory defect annotation '{banned}' detected in case_spec content per D-08")

    return story

