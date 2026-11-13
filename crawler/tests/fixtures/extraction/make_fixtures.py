"""Synthetic document fixtures for extraction tests (Phase 30 — Plan 02).

Everything here is GENERATED AT TEST TIME with FAKE values — never a real
document, never committed as a binary fixture (PITFALLS-v4.0 Anti-Pattern 4).
A minimal hand-rolled PDF writer (reportlab-free) embeds selectable text so
``pdfminer.six`` can extract it and ``pypdfium2`` can render it. Image fixtures
are built with Pillow.

The fake values (scores, dates, NOC codes, reference numbers) are deliberately
distinctive tokens so the PII-perimeter tests can assert they NEVER appear on
stdout / under corpus/.
"""

from __future__ import annotations

import io


# --------------------------------------------------------------------------- #
# Minimal PDF writer — a valid multi-page PDF with a Helvetica text stream per
# page. An empty page string produces a page with NO text (a synthetic "scan").
# --------------------------------------------------------------------------- #
def _text_stream(text: str) -> bytes:
    """Build a content stream drawing *text* (one Tj per line), or empty."""
    if not text.strip():
        return b""
    parts = [b"BT", b"/F1 12 Tf", b"72 720 Td"]
    for i, line in enumerate(text.split("\n")):
        esc = (line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)"))
        if i > 0:
            parts.append(b"0 -16 Td")
        parts.append(b"(" + esc.encode("latin-1", "replace") + b") Tj")
    parts.append(b"ET")
    return b"\n".join(parts)


def build_pdf(pages: list[str], rotations: "list[int] | None" = None) -> bytes:
    """Return the bytes of a valid PDF with one text page per *pages* entry.

    *rotations* (optional) sets each page's ``/Rotate`` value (0/90/180/270) so a
    "rotated scan" fixture can be built. Object numbering is contiguous 1..(2n+3):
    1=Catalog, 2=Pages, 3=Font, then (page, contents) pairs.
    """
    n = len(pages)
    rotations = rotations or [0] * n
    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    page_nums = []
    for i, text in enumerate(pages):
        page_num = 4 + 2 * i
        content_num = 5 + 2 * i
        page_nums.append(page_num)
        stream = _text_stream(text)
        objects[content_num] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream")
        objects[page_num] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Rotate "
            + str(int(rotations[i])).encode()
            + b" /Resources << /Font << /F1 3 0 R >> >> /Contents "
            + str(content_num).encode() + b" 0 R >>")
    kids = b" ".join(str(pn).encode() + b" 0 R" for pn in page_nums)
    objects[2] = (b"<< /Type /Pages /Kids [" + kids + b"] /Count "
                  + str(n).encode() + b" >>")

    max_num = 2 * n + 3
    body = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in range(1, max_num + 1):
        offsets[num] = len(body)
        body += str(num).encode() + b" 0 obj\n" + objects[num] + b"\nendobj\n"
    xref_pos = len(body)
    body += b"xref\n0 " + str(max_num + 1).encode() + b"\n"
    body += b"0000000000 65535 f \n"
    for num in range(1, max_num + 1):
        body += ("%010d 00000 n \n" % offsets[num]).encode()
    body += (b"trailer\n<< /Size " + str(max_num + 1).encode()
             + b" /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode()
             + b"\n%%EOF")
    return bytes(body)


# --------------------------------------------------------------------------- #
# Distinctive FAKE values (used by PII-perimeter assertions).
# --------------------------------------------------------------------------- #
FAKE_TRF = "TRF-ZZ99881"
FAKE_LISTENING = "8.5"
FAKE_READING = "7.5"
FAKE_WRITING = "7.0"
FAKE_SPEAKING = "8.0"
FAKE_NOC = "21231"
# A physician public-policy NOC (specialist in clinical and laboratory medicine).
# Distinct from FAKE_NOC so the per-document NOC non-leak assertions are unambiguous.
FAKE_PHYSICIAN_NOC = "31100"
FAKE_EMPLOYER = "Synthetic Widgets Incorporated"
FAKE_ECA_ORG = "World Education Services"
FAKE_STREAM = "Skilled Worker Synthetic Stream"
FAKE_DOB = "12 March 1990"
FAKE_PASSPORT_NO = "ZZ9988776"
FAKE_SURNAME = "SYNTHETICSON"
# Sibling-in-Canada attestation FAKE tokens (COV-03). Distinctive synthetic values
# so the PII-perimeter assertions can prove they NEVER reach stdout / corpus/.
FAKE_SIBLING_RELATIONSHIP = "brother"
FAKE_SIBLING_STATUS = "permanent_resident"
FAKE_SIBLING_RESIDENCE = "Synthetic City, Ontario"
FAKE_SIBLING_DOB = "12 March 1988"


def language_test_pdf() -> bytes:
    """A born-digital single-page IELTS-style report with all four abilities."""
    page = "\n".join([
        "IELTS Academic Test Report Form",
        "Test Date: 15 January 2026",
        f"TRF Number: {FAKE_TRF}",
        f"Listening: {FAKE_LISTENING}",
        f"Reading: {FAKE_READING}",
        f"Writing: {FAKE_WRITING}",
        f"Speaking: {FAKE_SPEAKING}",
    ])
    return build_pdf([page])


def language_test_multipage_pdf() -> bytes:
    """Three pages: full (ok), sparse (low_text), empty (scanned)."""
    full = "\n".join([
        "IELTS Academic Test Report Form",
        "Test Date: 15 January 2026",
        f"TRF Number: {FAKE_TRF}",
        f"Listening: {FAKE_LISTENING}",
        f"Reading: {FAKE_READING}",
        f"Writing: {FAKE_WRITING}",
        f"Speaking: {FAKE_SPEAKING}",
    ])
    sparse = f"Reading: {FAKE_READING}"      # < low-text threshold
    scanned = ""                             # no embedded text
    return build_pdf([full, sparse, scanned])


def ambiguous_date_pdf() -> bytes:
    """A born-digital (ok-quality) page whose test date is ambiguous (03/04/2024)."""
    page = "\n".join([
        "IELTS Academic Test Report Form",
        "Test Date: 03/04/2024",
        f"TRF Number: {FAKE_TRF}",
        f"Listening: {FAKE_LISTENING}",
    ])
    return build_pdf([page])


def employment_reference_pdf() -> bytes:
    """A born-digital employment letter with NOC/hours/duration/employer."""
    page = "\n".join([
        "Employment Reference Letter",
        f"Employer: {FAKE_EMPLOYER}",
        f"NOC Code: {FAKE_NOC}",
        "TEER: 1",
        "Hours per week: 37.5",
        "Start Date: 01 March 2022",
        "End Date: 30 June 2024",
        "Duration: 27 months",
    ])
    return build_pdf([page])


def job_offer_pdf() -> bytes:
    """A born-digital physician job-offer letter carrying a physician NOC line.

    Same shape as ``employment_reference_pdf`` but titled as a physician arranged-
    employment offer and carrying a PHYSICIAN NOC (plus an employer + start date so
    the inert fields extract). Synthetic FAKE values only — no PII, no tracked binary.
    """
    page = "\n".join([
        "Physician Arranged Employment — Offer of Employment",
        f"Employer: {FAKE_EMPLOYER}",
        f"NOC Code: {FAKE_PHYSICIAN_NOC}",
        "Start Date: 01 March 2024",
    ])
    return build_pdf([page])


def eca_pdf() -> bytes:
    """A born-digital ECA report with organization/report date/credential."""
    page = "\n".join([
        "Educational Credential Assessment Report",
        f"Organization: {FAKE_ECA_ORG}",
        "Report Date: 10 February 2025",
        "Reference Number: WES-778812",
        "Credential: Bachelor of Science",
        "Canadian equivalency: Bachelor's degree",
    ])
    return build_pdf([page])


def nomination_pdf() -> bytes:
    """A born-digital provincial nomination letter with stream/expiry."""
    page = "\n".join([
        "Provincial Nomination Certificate",
        f"Stream: {FAKE_STREAM}",
        "Expiry Date: 31 December 2026",
        "Province: Synthetica",
    ])
    return build_pdf([page])


def passport_pdf() -> bytes:
    """A born-digital identity/passport page carrying a Date of Birth line.

    Synthetic FAKE values ONLY (never real PII, never a tracked binary): the DOB
    drives the ``date_of_birth`` extraction spec (normalized to ISO by the existing
    date path) so ``core.age`` is substantiable through the real pipeline.
    """
    page = "\n".join([
        "Passport / Travel Document",
        f"Surname: {FAKE_SURNAME}",
        f"Passport Number: {FAKE_PASSPORT_NO}",
        f"Date of Birth: {FAKE_DOB}",
        "Nationality: Syntheticania",
    ])
    return build_pdf([page])


def sibling_proof_pdf() -> bytes:
    """A born-digital sibling-in-Canada attestation (COV-03).

    Synthetic FAKE values ONLY (never real PII, never a tracked binary). The four
    ``label: value`` lines match the ``_FIELD_SPECS["sibling_proof"]`` label regexes
    so the real extractor yields ``sibling_relationship``, ``sibling_status``,
    ``sibling_residence``, and ``sibling_date_of_birth`` (the DOB normalizes to ISO
    via the shipped ``_normalize_date`` path). The title deliberately avoids the
    field-label keywords so each ``label: value`` line is the sole match.
    """
    page = "\n".join([
        "Proof of Relative in Canada",
        f"Relationship: {FAKE_SIBLING_RELATIONSHIP}",
        f"Status: {FAKE_SIBLING_STATUS}",
        f"Residence: {FAKE_SIBLING_RESIDENCE}",
        f"Date of Birth: {FAKE_SIBLING_DOB}",
    ])
    return build_pdf([page])


def rotated_scan_pdf() -> bytes:
    """A single page rotated 90 degrees (rotation metadata → low_quality)."""
    return build_pdf(["Rotated content that should be flagged"], rotations=[90])


def synthetic_image_png() -> bytes:
    """A plain synthetic PNG (no embedded text → treated as a single scan page)."""
    from PIL import Image
    img = Image.new("RGB", (300, 400), color=(220, 220, 220))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
