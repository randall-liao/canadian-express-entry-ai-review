"""Automated Side-Channel Leakage Scanner.

Scans PDF filenames, metadata dictionaries, and text streams for privileged
document types, variant labels, research IDs, and explicit defect annotations per D-07, D-08, D-10.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Union

import pypdfium2 as pdfium

from crawler.synthetic.rasterizer import _PDFIUM_LOCK


FORBIDDEN_METADATA_KEYWORDS = [
    # Document type names
    "passport",
    "language_test",
    "educational_credential_assessment",
    "employment_reference_letter",
    "proof_of_funds",
    "medical_examination",
    "police_certificate",
    "digital_photo",
    "certified_translation",
    "written_job_offer_lmia",
    "proof_of_studies",
    "certificate_of_qualification",
    "birth_certificate",
    "marriage_certificate",
    "statutory_declaration_common_law",
    "divorce_certificate",
    "death_certificate",
    "adoption_certificate",
    "use_of_representative",
    "relative_in_canada",
    "proof_of_other_name",
    "authority_to_release_info",
    "letter_of_explanation",
    # Variant and case class labels
    "valid_control",
    "defective_case",
    "meets_requirements",
    "vector",
    "scanned",
    # Failure mode and ground truth labels
    "pfl-",
    "ground_truth",
    "research.json",
]

FORBIDDEN_TEXT_ANNOTATIONS = [
    "defective",
    "missing field",
    "expired credential",
    "pfl trigger",
    "synthetic test",
    "valid_control",
    "defective_case",
    "meets_requirements",
    "pfl-",
    "ground_truth",
    "research.json",
]


def scan_blind_artifact_leakage(pdf_input: Union[Path, bytes], filename: str = "") -> List[str]:
    """Scan a PDF file or bytes for side-channel leakage in filename, metadata, and page text.

    Args:
        pdf_input: Path to PDF file or raw PDF bytes.
        filename: Optional filename override if pdf_input is bytes or Path.

    Returns:
        List of string violation descriptions (empty if clean).
    """
    if isinstance(pdf_input, Path) and pdf_input.suffix.lower() == ".txt":
        return scan_blind_text_leakage(pdf_input, filename=filename)

    violations: List[str] = []

    # 1. Filename check
    fname = ""
    if isinstance(pdf_input, Path):
        fname = filename or pdf_input.name
    else:
        fname = filename

    if fname:
        fname_lower = fname.lower()
        if not re.match(r"^[a-f0-9]{32}\.pdf$", fname_lower):
            violations.append(f"Filename '{fname}' is not a 32-hex opaque ID matching '<32hex>.pdf'")

    # Read bytes
    if isinstance(pdf_input, Path):
        if not pdf_input.is_file():
            violations.append(f"File not found: {pdf_input}")
            return violations
        pdf_bytes = pdf_input.read_bytes()
    else:
        pdf_bytes = pdf_input

    with _PDFIUM_LOCK:
        try:
            pdf = pdfium.PdfDocument(pdf_bytes)
        except Exception as exc:
            violations.append(f"Could not parse PDF document: {exc}")
            return violations

        # 2. Metadata check via PyPDFium2 document metadata
        try:
            meta_dict = pdf.get_metadata_dict()
            for k, v in meta_dict.items():
                if not v:
                    continue
                v_lower = str(v).lower()
                for kw in FORBIDDEN_METADATA_KEYWORDS:
                    if kw in v_lower:
                        violations.append(f"PDF metadata key '{k}'='{v}' leaked forbidden term '{kw}'")
        except Exception as exc:
            violations.append(f"Could not read PDF metadata: {exc}")

        # 3. Extract text streams across all pages
        try:
            for page_idx in range(len(pdf)):
                page = pdf[page_idx]
                text = page.get_textpage().get_text_range().lower()
                for kw in FORBIDDEN_TEXT_ANNOTATIONS:
                    if kw in text:
                        violations.append(
                            f"Forbidden term '{kw}' found in text of page {page_idx + 1}"
                        )
        except Exception as exc:
            violations.append(f"Could not extract text from PDF pages: {exc}")

    return violations


def scan_blind_text_leakage(text_input: Union[Path, str], filename: str = "") -> List[str]:
    """Scan a text file or text string for side-channel leakage in filename and content.

    Args:
        text_input: Path to text file or raw text string.
        filename: Optional filename override if text_input is string or Path.

    Returns:
        List of string violation descriptions (empty if clean).
    """
    violations: List[str] = []

    # 1. Filename check
    fname = ""
    if isinstance(text_input, Path):
        fname = filename or text_input.name
        if not text_input.is_file():
            violations.append(f"Text file not found: {text_input}")
            return violations
        text_content = text_input.read_text(encoding="utf-8", errors="replace")
    else:
        fname = filename
        text_content = text_input

    if fname:
        fname_lower = fname.lower()
        if not re.match(r"^[a-f0-9]{32}\.txt$", fname_lower):
            violations.append(f"Filename '{fname}' is not a 32-hex opaque ID matching '<32hex>.txt'")

    # 2. Content check
    content_lower = text_content.lower()
    for kw in FORBIDDEN_METADATA_KEYWORDS + FORBIDDEN_TEXT_ANNOTATIONS:
        if kw in content_lower:
            violations.append(f"Forbidden term '{kw}' found in text artifact content")

    return violations