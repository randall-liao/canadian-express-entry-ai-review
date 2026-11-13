"""Local document extraction engine — the ONE non-grounded step (Phase 30 — Plan 02).

Renders every PDF page to an image (``pypdfium2``), reads embedded text first
(``pdfminer.six``), normalizes images (``Pillow``), OPTIONALLY OCRs scans
(``pytesseract`` behind the ``ocr`` extra + a local Tesseract binary), runs
deterministic regex/heuristic field extractors, classifies scan quality, and
writes EVERY proposed value as ``pending`` through the Plan-01 store — plus
rendered images and text into the git-ignored candidate vault ONLY.

Locked constraints honored:

* **Local stack only** — no cloud OCR / document-AI, no vector/embedding, no
  heavy ML (PaddleOCR/EasyOCR/docTR), no default PyMuPDF/pdf2image/Poppler.
* **Everything pending** (EXTRACT-02) — extraction never writes a confirmed value
  and never computes CLB/points (that is Phase 31's grounded rule work). All
  ``normalized_value`` are STRUCTURAL only (ISO dates, numbers, NOC strings).
* **PII stays in the vault** — rendered images (``files/rendered/``) and text
  (``files/text/``) are written via ``paths.resolve_within(vault.root, ...)``
  ONLY; nothing is written to ``corpus/``, stdout, or tracked fixtures.
* **Lazy heavy imports** — pypdfium2/pdfminer/pytesseract are imported INSIDE
  functions and a missing one raises a typed :class:`MissingExtractionDependency`
  (mapped to ``missing_dependency`` by the CLI), so ``import crawler.extraction``
  and ``import crawler.cli`` stay cheap on a lean install.

``PARSER_VERSION`` is the single source of truth consumed by Plan-01 staleness
(``vault.current_parser_version``).
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
from dataclasses import dataclass, field

from crawler import dlifields, mecfields, paths, siblingfields, testtypes, vault
from crawler.models.vault import CrsProfileFactor

# The extraction pipeline version. Bumping this invalidates prior confirmations
# via SC4 staleness (see crawler.vault.current_parser_version / is_stale).
PARSER_VERSION = "1"

# Below this many characters of stripped embedded text a page is "low_text"
# (sparse) — its derived values are flagged low_quality, never a silent 'ok'.
_LOW_TEXT_THRESHOLD = 24

# Pillow decompression-bomb guard: refuse to fully process an image larger than
# this (T-30-07); such pages are flagged low_quality rather than OOMing.
_MAX_IMAGE_PIXELS = 64_000_000  # ~64 MP


class MissingExtractionDependency(RuntimeError):
    """A required extraction dependency (or the Tesseract binary) is absent.

    Carries the missing ``module`` name and the ``extra`` that provides it so the
    CLI can map it to a ``missing_dependency`` envelope with an install hint —
    never an opaque ``ImportError``.
    """

    def __init__(self, module: str, extra: str) -> None:
        self.module = module
        self.extra = extra
        super().__init__(
            f"the '{module}' extraction dependency is not installed. Install it "
            f"with:\n    pip install 'corpus-crawler[{extra}]'\n"
            f"  (or, in a Poetry checkout: poetry install --extras {extra})")


# --------------------------------------------------------------------------- #
# Lazy dependency importers — the ONLY place heavy libs are imported. Patched in
# tests to prove a missing dep raises MissingExtractionDependency (not ImportError).
# --------------------------------------------------------------------------- #
def _import_pdfium():
    try:
        import pypdfium2 as pdfium
        return pdfium
    except ImportError as exc:
        raise MissingExtractionDependency("pypdfium2", "doc-extract") from exc


def _import_pil():
    try:
        from PIL import Image, ImageOps
        return Image, ImageOps
    except ImportError as exc:
        raise MissingExtractionDependency("Pillow", "doc-extract") from exc


def _import_pdfminer():
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.layout import LAParams
        from pdfminer.pdfpage import PDFPage
        return extract_text, LAParams, PDFPage
    except ImportError as exc:
        raise MissingExtractionDependency("pdfminer.six", "doc-extract") from exc


def _import_pytesseract():
    try:
        import pytesseract
        return pytesseract
    except ImportError as exc:
        raise MissingExtractionDependency("pytesseract", "ocr") from exc


def tesseract_available() -> bool:
    """True iff the ``pytesseract`` wrapper AND the ``tesseract`` binary are present.

    Never raises — a missing wrapper/binary simply means OCR is unavailable and
    the caller flags text-empty pages low_quality instead of OCR-ing them.
    """
    try:
        _import_pytesseract()
    except MissingExtractionDependency:
        return False
    return shutil.which("tesseract") is not None


def engine_versions() -> dict:
    """Return a small dict of tool versions for the extraction_run engine_json."""
    versions = {"parser_version": PARSER_VERSION}
    try:
        import pypdfium2
        versions["pypdfium2"] = getattr(pypdfium2, "V_PYPDFIUM2", None) or \
            getattr(pypdfium2, "__version__", "?")
    except Exception:  # noqa: BLE001
        pass
    try:
        import pdfminer
        versions["pdfminer.six"] = getattr(pdfminer, "__version__", "?")
    except Exception:  # noqa: BLE001
        pass
    try:
        import PIL
        versions["Pillow"] = getattr(PIL, "__version__", "?")
    except Exception:  # noqa: BLE001
        pass
    versions["tesseract"] = tesseract_available()
    return versions


# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #
@dataclass
class ExtractionResult:
    document_id: str
    extraction_run_id: str
    page_count: int = 0
    rendered_pages: int = 0
    cached_pages: int = 0
    value_ids: list = field(default_factory=list)
    quality_counts: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Deterministic field extractors — regex + simple heuristics ONLY (no ML, no
# semantic NOC/duty entailment). normalized_value is STRUCTURAL (ISO dates,
# numbers, NOC strings); CLB/points are NOT computed here (Phase 31's grounded
# rule work). Keyed by the document's doc_type.
# --------------------------------------------------------------------------- #
_TEST_TYPE_RE = re.compile(
    r"\b(IELTS|CELPIP|TEF\s*Canada|TEF|TCF\s*Canada|TCF|PTE\s*Core|PTE)\b", re.I)

# (field_name, label_regex, kind) — kind in {text, date, number, noc}.
_FIELD_SPECS: dict[str, list[tuple[str, str, str]]] = {
    "language_test": [
        ("test_date", r"(?:Test Date|Date of Test|Exam Date)", "date"),
        ("reference_number",
         r"(?:TRF (?:No\.?|Number)|Registration (?:No\.?|Number)|"
         r"Reference (?:No\.?|Number))", "text"),
        ("raw_score_listening", r"Listening", "number"),
        ("raw_score_reading", r"Reading", "number"),
        ("raw_score_writing", r"Writing", "number"),
        ("raw_score_speaking", r"Speaking", "number"),
    ],
    "eca": [
        ("eca_organization",
         r"(?:Organization|Issuing Organization|Assessed by)", "text"),
        ("eca_report_date", r"(?:Report Date|Date of Report|Issue Date)", "date"),
        ("reference_number",
         r"(?:Reference (?:No\.?|Number)|ECA Reference|File (?:No\.?|Number))",
         "text"),
        ("credential", r"(?:Credential|Diploma|Degree Awarded)", "text"),
        ("credential_level",
         r"(?:Canadian [Ee]quivalency|Equivalency|Credential Level)", "text"),
    ],
    "employment_reference": [
        ("issuer", r"(?:Employer|Company|Organization)", "text"),
        ("noc_code", r"(?:NOC(?: Code)?|National Occupational Classification)",
         "noc"),
        ("teer", r"TEER", "number"),
        ("hours_per_week",
         r"(?:Hours per [Ww]eek|Weekly Hours|Hours/[Ww]eek)", "number"),
        ("employment_start", r"(?:Start Date|Employment Start)", "date"),
        ("employment_end", r"(?:End Date|Employment End)", "date"),
        ("duration_months", r"(?:Duration|Total Duration)", "number"),
    ],
    "nomination": [
        ("nomination_stream", r"(?:Stream|Nomination Stream|Category)", "text"),
        ("expiry_date", r"(?:Expiry Date|Valid Until|Expiration Date)", "date"),
        ("issuer", r"(?:Province|Nominating Province|Issued by)", "text"),
    ],
    "passport": [
        # An identity/passport document carries the applicant's DOB. Routed to the
        # existing date-normalization path (_normalize_date) → ISO string, so
        # core.age is substantiable through the REAL pipeline WITHOUT relaxing the
        # frozen decide_age (which reads by_field["date_of_birth"] verbatim).
        ("date_of_birth",
         r"(?:Date of Birth|Date of birth|D\.?O\.?B\.?|Born)", "date"),
    ],
    "sibling_proof": [
        # A sibling-in-Canada attestation. Field NAMES are EXACTLY
        # siblingfields.SIBLING_FIELDS (pinned by test_siblingfields_vocab.py and by
        # the producer guard below). STRUCTURAL extraction only — no scoring; the
        # 35-04 decider reads the sibling points from a grounded registry row.
        ("sibling_relationship", r"(?:Relationship|Sibling)", "text"),
        ("sibling_status", r"(?:Status|Immigration Status|PR Status)", "text"),
        ("sibling_residence",
         r"(?:Residence|Lives in|Current Residence|Address)", "text"),
        # DOB routed through the shipped _normalize_date path (ISO string) — reuses
        # the existing date logic so the 35-04 adult/minor age check keys on ISO.
        ("sibling_date_of_birth",
         r"(?:Date of Birth|Sibling Date of Birth|D\.?O\.?B\.?)", "date"),
    ],
    "study_proof": [
        # Private Canadian-study intake. Field names are pinned set-equal to
        # dlifields.STUDY_FIELDS below; this producer performs structural
        # normalization only and never computes points or eligibility.
        ("institution_name",
         r"(?:Institution Name|School Name|Institution)", "text"),
        ("dli_number",
         r"(?:DLI Number|DLI No\.?|Designated Learning Institution Number)",
         "text"),
        ("credential_level",
         r"(?:Credential Level|Program Credential|Credential)", "text"),
        ("program_start",
         r"(?:Program Start|Program Start Date|Start of Program)", "date"),
        ("program_end",
         r"(?:Program End|Program End Date|End of Program)", "date"),
        ("study_status",
         r"(?:Study Status|Program Status|Completion Status)", "text"),
    ],
}
# ``identity`` is an alias doc_type for ``passport`` (both carry the DOB spec and
# link to core.age via _DOC_TYPE_FACTOR); share the SAME field spec list.
_FIELD_SPECS["identity"] = _FIELD_SPECS["passport"]

# ``job_offer`` is a physician / arranged-employment offer document. It REUSES the
# shared ``noc_code`` spec (SAME regex + ``noc`` kind as employment_reference — the
# name is already in the closed FieldName vocabulary, so NO vault migration) so a
# confirmed physician NOC can reach ``decide_job_offer``'s by_field, plus two fields
# that are inert to the decider (issuer, employment_start). Its value→factor linkage
# is per-DOCUMENT (additional.job_offer), claimed-only, and never mixes with an
# employment_reference document's core.work NOC.
_FIELD_SPECS["job_offer"] = [
    ("noc_code", r"(?:NOC(?: Code)?|National Occupational Classification)", "noc"),
    ("issuer", r"(?:Employer|Company|Organization)", "text"),
    ("employment_start", r"(?:Start Date|Employment Start)", "date"),
]

# Strict private labeled MEC forms.  These labels make facts that arbitrary prose
# cannot establish reliably reachable through the existing pending -> one-value
# decision lifecycle.  They perform structural normalization only.
_FIELD_SPECS.update(
    {
        "mec-profile": [
            ("application_date", r"Application Date", "mec"),
            ("eligibility_reference_date", r"Eligibility Reference Date", "mec"),
            ("ita_date", r"ITA Date", "mec"),
            ("primary_noc_code", r"Primary NOC Code", "mec"),
            ("work_history_scope_complete", r"Work History Scope Complete", "mec"),
            ("education_scope_complete", r"Education Scope Complete", "mec"),
            ("language_scope_complete", r"Language Scope Complete", "mec"),
            ("fsw_education_branch", r"FSW Education Branch", "mec"),
            ("offer_certificate_scope_complete",
             r"Offer Certificate Scope Complete", "mec"),
            ("adaptability_scope_complete", r"Adaptability Scope Complete", "mec"),
        ],
        "mec-employment-period": [
            ("employment_start", r"Employment Start", "mec"),
            ("employment_end", r"Employment End", "mec"),
            ("paid_status", r"Paid Status", "mec"),
            ("student_status", r"Student Status", "mec"),
            ("self_employed", r"Self Employed", "mec"),
            ("work_country", r"Work Country", "mec"),
            ("work_province", r"Work Province", "mec"),
            ("work_authorized", r"Work Authorized", "mec"),
            ("temporary_resident_status", r"Temporary Resident Status", "mec"),
            ("noc_code", r"NOC Code", "mec"),
            ("teer", r"TEER", "mec"),
            ("noc_version_date", r"NOC Version Date", "mec"),
            ("noc_version", r"NOC Version", "mec"),
            ("hours_per_week", r"Hours per Week", "mec"),
            ("total_hours", r"Total Hours", "mec"),
            ("duration_months", r"Duration Months", "mec"),
            ("qualified_to_practise", r"Qualified to Practise", "mec"),
            ("employment_continuous", r"Employment Continuous", "mec"),
            ("physically_in_canada", r"Physically in Canada", "mec"),
            ("is_remote", r"Is Remote", "mec"),
            ("canadian_employer_if_remote", r"Canadian Employer if Remote", "mec"),
        ],
        "mec-trade-certificate": [
            ("trade_certificate_authority", r"Trade Certificate Authority", "mec"),
            ("trade_certificate_jurisdiction",
             r"Trade Certificate Jurisdiction", "mec"),
            ("trade_certificate_noc_code", r"Trade Certificate NOC Code", "mec"),
            ("trade_name", r"Trade Name", "mec"),
            ("trade_certificate_status", r"Trade Certificate Status", "mec"),
            ("trade_certificate_issue_date",
             r"Trade Certificate Issue Date", "mec"),
            ("trade_certificate_expiry_date",
             r"Trade Certificate Expiry Date", "mec"),
        ],
        "mec-valid-offer": [
            ("offer_full_time", r"Offer Full Time", "mec"),
            ("offer_continuous", r"Offer Continuous", "mec"),
            ("offer_non_seasonal", r"Offer Non Seasonal", "mec"),
            ("offer_paid_status", r"Offer Paid Status", "mec"),
            ("offer_duration_months", r"Offer Duration Months", "mec"),
            ("offer_noc_code", r"Offer NOC Code", "mec"),
            ("offer_teer", r"Offer TEER", "mec"),
            ("offer_country", r"Offer Country", "mec"),
            ("offer_province", r"Offer Province", "mec"),
            ("offer_employer_count", r"Offer Employer Count", "mec"),
            ("offer_lmia_status", r"Offer LMIA Status", "mec"),
            ("offer_work_permit_basis", r"Offer Work Permit Basis", "mec"),
            ("offer_permit_valid_at_visa_issuance",
             r"Offer Permit Valid at Visa Issuance", "mec"),
            ("offer_lmia_exemption_basis", r"Offer LMIA Exemption Basis", "mec"),
            ("offer_status", r"Offer Status", "mec"),
            ("offer_valid_from", r"Offer Valid From", "mec"),
            ("offer_valid_until", r"Offer Valid Until", "mec"),
            ("offer_branch", r"Offer Branch", "mec"),
            ("current_work_permit_status", r"Current Work Permit Status", "mec"),
            ("currently_working_in_canada", r"Currently Working in Canada", "mec"),
            ("currently_working_for_offer_employer",
             r"Currently Working for Offer Employer", "mec"),
            ("offer_employer_matches_work_permit",
             r"Offer Employer Matches Work Permit", "mec"),
            ("one_year_for_offer_employer", r"One Year for Offer Employer", "mec"),
            ("plans_work_before_pr", r"Plans Work Before PR", "mec"),
            ("offer_employer_differs_current",
             r"Offer Employer Differs from Current", "mec"),
        ],
        "mec-funds": [
            ("funds_household_size", r"Funds Household Size", "mec"),
            ("funds_amount", r"Funds Amount", "mec"),
            ("funds_currency", r"Funds Currency", "mec"),
            ("funds_as_of_date", r"Funds As Of Date", "mec"),
            ("funds_accessible", r"Funds Accessible", "mec"),
            ("funds_borrowed", r"Funds Borrowed", "mec"),
            ("funds_real_property_equity", r"Funds Real Property Equity", "mec"),
        ],
        "mec-province-status": [
            ("intended_destination_country", r"Intended Destination Country", "mec"),
            ("intended_destination_province",
             r"Intended Destination Province", "mec"),
            ("province_status", r"Province Status", "mec"),
            ("work_authorization_start", r"Work Authorization Start", "mec"),
            ("work_authorization_end", r"Work Authorization End", "mec"),
            ("temporary_status_start", r"Temporary Status Start", "mec"),
            ("temporary_status_end", r"Temporary Status End", "mec"),
            ("legally_authorized_to_work_canada",
             r"Legally Authorized to Work Canada", "mec"),
        ],
    }
)

# Map a DOCUMENT to its SPECIFIC target grid factor id. A value's factor is a
# property of the DOCUMENT (an IELTS report substantiates the FIRST official
# language, an ECA the education factor, ...), NOT of the field — the old
# group-alphabetical linkage (`ORDER BY factor_id LIMIT 1`) landed every language
# value on `core.age` and every nomination value on `additional.french`
# (BLOCKER A). First-vs-second-language and other in-group ambiguities are
# disambiguated by the `factor_override` param / CLI `--factor`.
_DOC_TYPE_FACTOR: dict[str, str] = {
    "language_test": "core.language.first",
    "eca": "core.education",
    "employment_reference": "core.work",
    "nomination": "additional.nomination",
    "passport": "core.age",
    "identity": "core.age",
    # A sibling attestation links to the SPECIFIC sibling grid factor (claimed-only
    # via _resolve_factor) — never to core.age or additional.nomination.
    "sibling_proof": "additional.sibling",
    # A physician / arranged-employment offer links to the SPECIFIC job-offer factor
    # (claimed-only) — never to core.work; an employment_reference keeps core.work.
    "job_offer": "additional.job_offer",
    # Dedicated inert vault-only review parent. It is intentionally absent from
    # FULL_GRID_FACTORS and must never be confused with additional.study.
    "study_proof": "review.study",
    "mec-profile": "review.mec",
    "mec-employment-period": "review.mec",
    "mec-trade-certificate": "review.mec",
    "mec-valid-offer": "review.mec",
    "mec-funds": "review.mec",
    "mec-province-status": "review.mec",
}

# Producer anti-drift guard: the sibling_proof spec field NAMES must stay EXACTLY
# the shared siblingfields.SIBLING_FIELDS vocabulary. This fails fast at import if
# the extractor (producer) drifts from the vocab, complementing the set-equality
# pin in test_siblingfields_vocab.py (which also pins the FieldName boundary side).
assert {name for name, _regex, _kind in _FIELD_SPECS["sibling_proof"]} == set(
    siblingfields.SIBLING_FIELDS
), "sibling_proof _FIELD_SPECS drifted from siblingfields.SIBLING_FIELDS"

assert {name for name, _regex, _kind in _FIELD_SPECS["study_proof"]} == set(
    dlifields.STUDY_FIELDS
), "study_proof _FIELD_SPECS drifted from dlifields.STUDY_FIELDS"

for _mec_doc_type, _mec_fields in mecfields.MEC_DOCUMENT_FIELDS.items():
    _produced = {
        name for name, _regex, _kind in _FIELD_SPECS[_mec_doc_type]
    }
    _expected = set(_mec_fields) - (
        {"employment_period_id"}
        if _mec_doc_type == "mec-employment-period"
        else set()
    )
    assert _produced == _expected, (
        f"{_mec_doc_type} _FIELD_SPECS drifted from MEC_DOCUMENT_FIELDS"
    )

_REVIEW_STUDY_FACTOR_ID = "review.study"
_REVIEW_MEC_FACTOR_ID = "review.mec"


def _review_study_factor() -> CrsProfileFactor:
    """Return the inert FK-parent row used only for study evidence review."""
    return CrsProfileFactor(
        factor_id=_REVIEW_STUDY_FACTOR_ID,
        factor_group="additional_points",
        claimed_points=None,
        claimed_level=None,
        claimed_value={},
        source="user_entry",
    )


def _review_mec_factor() -> CrsProfileFactor:
    """Return the inert FK parent for private program-eligibility evidence."""
    return CrsProfileFactor(
        factor_id=_REVIEW_MEC_FACTOR_ID,
        factor_group="program_eligibility",
        claimed_points=None,
        claimed_level=None,
        claimed_value={},
        source="user_entry",
    )

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _normalize_date(raw: str) -> tuple[str, bool]:
    """Return (ISO-8601 string, ambiguous?). Unresolvable → (raw, True).

    Numeric ``A/B/YYYY`` where both components are <= 12 is genuinely ambiguous
    (Pitfall 1 date swap) and is flagged rather than silently normalized.
    """
    s = raw.strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", False
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if m and m.group(2).lower()[:3] in _MONTHS:
        return (f"{m.group(3)}-{_MONTHS[m.group(2).lower()[:3]]:02d}-"
                f"{int(m.group(1)):02d}", False)
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1).lower()[:3] in _MONTHS:
        return (f"{m.group(3)}-{_MONTHS[m.group(1).lower()[:3]]:02d}-"
                f"{int(m.group(2)):02d}", False)
    m = re.match(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if a > 12 and b <= 12:
            return f"{y}-{b:02d}-{a:02d}", False
        if b > 12 and a <= 12:
            return f"{y}-{a:02d}-{b:02d}", False
        return f"{y}-{a:02d}-{b:02d}", True  # both <= 12 → ambiguous
    return s, True


def _find_label(text: str, label_regex: str) -> str | None:
    """Return the value after ``label: `` (to end of line), or None."""
    m = re.search(label_regex + r"\s*[:\-]\s*(.+)", text, re.I)
    return m.group(1).strip() if m else None


def _extract_fields(doc_type: str, text: str) -> list[dict]:
    """Return proposed fields for *text* under *doc_type*.

    Each entry: {field_name, raw_text, normalized_value, ambiguous}. STRUCTURAL
    normalization only — no CLB/points computation.
    """
    results: list[dict] = []
    if not text or not text.strip():
        return results
    if doc_type == "language_test":
        m = _TEST_TYPE_RE.search(text)
        if m:
            # Normalize the captured token to the registry-accepted vocabulary
            # (BLOCKER B): the reviewer still sees the verbatim raw token, but the
            # normalized_value is the canonical spelling the registry accepted-enum
            # + conversion tables key on. An unknown token stays non-accepted
            # (fail-closed) rather than being coerced to an accepted value.
            normalized = testtypes.normalize_test_type(m.group(0))
            results.append({"field_name": "test_type", "raw_text": m.group(0),
                            "normalized_value": normalized,
                            "ambiguous": False})
    for field_name, label, kind in _FIELD_SPECS.get(doc_type, []):
        val = _find_label(text, label)
        if val is None:
            continue
        if kind == "mec":
            raw = val.strip()
            norm, ambiguous = mecfields.normalize_mec_field(field_name, raw)
        elif kind == "date":
            norm, ambiguous = _normalize_date(val)
            raw = val
        elif kind == "number":
            mnum = re.search(r"-?\d+(?:\.\d+)?", val)
            if not mnum:
                continue
            raw = mnum.group(0)
            num = float(raw)
            norm = int(num) if num.is_integer() else num
            ambiguous = False
        elif kind == "noc":
            mnoc = re.search(r"\d{5}", val)
            if not mnoc:
                continue
            raw = norm = mnoc.group(0)
            ambiguous = False
        else:  # text
            raw = val.strip()
            if field_name == "sibling_status":
                # Canonicalize the closed-enum sibling status onto the shared
                # accepted vocabulary (WR-01), mirroring test_type above: the
                # reviewer still sees the verbatim raw surface form, but the
                # normalized_value the decider gates on is the snake_case token
                # (e.g. "Permanent Resident" -> "permanent_resident"). An unknown
                # surface form stays non-accepted (fail-closed), never coerced.
                norm = siblingfields.normalize_sibling_status(raw) or raw
            elif field_name == "sibling_relationship":
                norm = siblingfields.normalize_sibling_relationship(raw) or raw
            elif field_name == "dli_number":
                norm = dlifields.normalize_dli(raw)
            elif field_name == "credential_level" and doc_type == "study_proof":
                norm = dlifields.normalize_credential_level(raw)
            elif field_name == "study_status":
                norm = dlifields.normalize_study_status(raw)
            else:
                norm = raw
            ambiguous = False
        results.append({"field_name": field_name, "raw_text": raw,
                        "normalized_value": norm, "ambiguous": ambiguous})
    return results


def _resolve_factor(v: vault.Vault, doc_type: str,
                    factor_override: "str | None") -> str | None:
    """Return the SPECIFIC claimed grid factor id for a document, or None.

    The target factor is a property of the DOCUMENT: ``factor_override`` (CLI
    ``--factor``, used to disambiguate e.g. first-vs-second language) takes
    precedence, otherwise the doc_type's entry in :data:`_DOC_TYPE_FACTOR`. The
    target is returned ONLY when it is actually CLAIMED in ``crs_profile_factors``
    (verified with a PARAMETERIZED lookup — never string interpolation, so an
    injected/renamed ``--factor`` value cannot reach SQL). An unclaimed / unknown /
    misnamed target leaves the value UNLINKED (returns None) — fail-closed, no
    cross-factor contamination.
    """
    target = factor_override or _DOC_TYPE_FACTOR.get(doc_type)
    if target is None:
        return None
    row = v.con.execute(
        "SELECT factor_id FROM crs_profile_factors WHERE factor_id = ? LIMIT 1",
        (target,)).fetchone()
    return row["factor_id"] if row is not None else None


# --------------------------------------------------------------------------- #
# Scan-quality classification (EXTRACT-05 quality half). Detects scanned /
# low_text / rotated / password_protected — never silently 'ok'.
# --------------------------------------------------------------------------- #
def classify_page_quality(text: str | None, rotation: int = 0, *,
                          password_protected: bool = False,
                          oversize: bool = False) -> dict:
    """Classify one page's scan quality into a JSON-serializable dict."""
    stripped = (text or "").strip()
    density = len(stripped)
    return {
        "scanned": density == 0 and not password_protected,
        "low_text": 0 < density < _LOW_TEXT_THRESHOLD,
        "rotated": (rotation % 360) in (90, 180, 270),
        "password_protected": password_protected,
        "oversize": oversize,
        "text_density": density,
    }


def _quality_flag(quality: dict) -> str:
    """Map a page-quality dict to the value-level quality flag (ok|low_quality)."""
    if (quality["scanned"] or quality["low_text"] or quality["rotated"]
            or quality["password_protected"] or quality.get("oversize")):
        return "low_quality"
    return "ok"


def _normalize_image(pil_image, Image, ImageOps):
    """Grayscale + autocontrast a rendered/loaded page for review/OCR."""
    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    gray = pil_image.convert("L")
    try:
        gray = ImageOps.autocontrast(gray)
    except Exception:  # noqa: BLE001 - autocontrast is best-effort
        pass
    return gray


# --------------------------------------------------------------------------- #
# PDF page text + rotation (pdfminer.six)
# --------------------------------------------------------------------------- #
def _pdf_page_text(data: bytes, index: int, extract_text, LAParams) -> str:
    try:
        return extract_text(io.BytesIO(data), page_numbers={index},
                            laparams=LAParams()) or ""
    except Exception:  # noqa: BLE001 - a page that will not parse yields no text
        return ""


def _pdf_page_rotations(data: bytes, PDFPage) -> list[int]:
    try:
        return [int(getattr(p, "rotate", 0) or 0)
                for p in PDFPage.get_pages(io.BytesIO(data))]
    except Exception:  # noqa: BLE001
        return []


def _ocr_image(pil_image) -> str:
    """Run local Tesseract OCR on a normalized page image; '' on any failure."""
    try:
        pytesseract = _import_pytesseract()
        return pytesseract.image_to_string(pil_image) or ""
    except Exception:  # noqa: BLE001 - OCR is best-effort; caller flags low_quality
        return ""


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def extract_document(v: vault.Vault, document_id: str, *, dpi: int = 200,
                     enable_ocr: "str | bool" = "auto",
                     factor_override: "str | None" = None) -> ExtractionResult:
    """Render + read a vault document and write ``pending`` values + artifacts.

    Renders EVERY page (never page-one-only), reads embedded text first, OCRs a
    text-empty page only when ``enable_ocr`` allows AND Tesseract is available
    (otherwise flags it low_quality), classifies scan quality, and persists each
    proposed field as a ``pending`` value through the Plan-01 store. Rendered
    PNGs land under ``files/rendered/<document_id>/`` and combined text under
    ``files/text/<document_id>.txt`` — vault-anchored via ``resolve_within``.

    ``factor_override`` disambiguates in-group targets (e.g. link a second language
    report to ``core.language.second``); when omitted the document's doc_type
    decides its target grid factor. ALL of a document's values share that single
    factor (an unclaimed/unknown target leaves them unlinked — fail-closed).
    """
    row = v.con.execute(
        "SELECT storage_relpath, doc_type, file_sha256 "
        "FROM documents WHERE document_id = ?",
        (document_id,)).fetchone()
    if row is None:
        raise vault.VaultError("unknown document_id")
    doc_type = row["doc_type"]
    if doc_type == "study_proof":
        # ``extracted_values.factor_id`` is an FK, so seed the dedicated inert
        # parent before claimed-only factor resolution. This is a data upsert,
        # not DDL or a migration.
        vault.upsert_profile_factor(v, _review_study_factor())
    if doc_type in mecfields.MEC_DOCUMENT_FIELDS:
        # Seed once without rewriting the parent: rewriting its updated_at would
        # change the profile-claim staleness key for prior MEC confirmations.
        existing = v.con.execute(
            "SELECT factor_id FROM crs_profile_factors WHERE factor_id = ?",
            (_REVIEW_MEC_FACTOR_ID,),
        ).fetchone()
        if existing is None:
            vault.upsert_profile_factor(v, _review_mec_factor())
    # A value's factor is a property of the DOCUMENT — resolve it ONCE (all fields
    # of a document share the same target grid factor).
    # A study proof is quarantined by doc type and cannot be redirected onto a
    # CRS grid factor via the general disambiguation override.
    effective_override = (
        None
        if doc_type == "study_proof" or doc_type in mecfields.MEC_DOCUMENT_FIELDS
        else factor_override
    )
    factor_id = _resolve_factor(v, doc_type, effective_override)
    raw_path = paths.resolve_within(v.root, *row["storage_relpath"].split("/"))
    data = raw_path.read_bytes()
    is_pdf = raw_path.suffix.lower() == ".pdf" or data[:5] == b"%PDF-"

    run_id = vault.record_extraction_run(
        v, document_id=document_id, parser_version=PARSER_VERSION,
        engine_json=engine_versions(), status="running")
    result = ExtractionResult(document_id=document_id, extraction_run_id=run_id)
    counts = {"ok": 0, "scanned": 0, "low_text": 0, "rotated": 0,
              "password_protected": 0}
    text_parts: list[str] = []
    text_rel = f"files/text/{document_id}.txt"
    period_id = (
        mecfields.employment_period_id(row["file_sha256"])
        if doc_type == "mec-employment-period"
        else None
    )
    period_key_written = False

    try:
        pages = (_pdf_pages(v, document_id, data, dpi, enable_ocr, result)
                 if is_pdf else
                 _image_page(v, document_id, data, dpi, enable_ocr, result))
        for page_no, page_id, page_text, quality in pages:
            text_parts.append(page_text or "")
            flag = _quality_flag(quality)
            for key in ("scanned", "low_text", "rotated", "password_protected"):
                if quality.get(key):
                    counts[key] += 1
            if flag == "ok":
                counts["ok"] += 1
            if period_id is not None and not period_key_written:
                key_id = vault.add_extracted_value(
                    v,
                    document_id=document_id,
                    page_id=page_id,
                    factor_id=factor_id,
                    field_name="employment_period_id",
                    raw_text=None,
                    normalized_value=period_id,
                    bbox=None,
                    extractor_confidence=1.0,
                    quality_flag=flag,
                    extraction_run_id=run_id,
                )
                vault.link_factor_evidence(v, factor_id, key_id, "primary")
                result.value_ids.append(key_id)
                period_key_written = True
            for f in _extract_fields(doc_type, page_text):
                value_quality = (
                    "low_quality" if flag == "low_quality"
                    else ("ambiguous" if f["ambiguous"] else "ok"))
                normalized_value = f["normalized_value"]
                if period_id is not None:
                    normalized_value = {
                        "employment_period_id": period_id,
                        "value": normalized_value,
                    }
                vid = vault.add_extracted_value(
                    v, document_id=document_id, page_id=page_id,
                    factor_id=factor_id, field_name=f["field_name"],
                    raw_text=f["raw_text"], normalized_value=normalized_value,
                    bbox=None, extractor_confidence=0.9,
                    quality_flag=value_quality, extraction_run_id=run_id)
                if factor_id is not None:
                    vault.link_factor_evidence(v, factor_id, vid, "primary")
                result.value_ids.append(vid)
    except MissingExtractionDependency:
        vault.complete_extraction_run(v, run_id, status="failed")
        raise
    except Exception:
        vault.complete_extraction_run(v, run_id, status="failed")
        raise

    # Write combined per-document text under the vault ONLY.
    text_path = paths.resolve_within(v.root, *text_rel.split("/"))
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text("\n".join(text_parts), encoding="utf-8")

    v.con.execute("UPDATE documents SET status = 'extracted', page_count = ? "
                  "WHERE document_id = ?", (result.page_count, document_id))
    v.con.commit()
    vault.complete_extraction_run(v, run_id, status="complete")
    result.quality_counts = counts
    return result


def _render_and_cache(v: vault.Vault, document_id: str, page_no: int,
                      pil_image, Image, ImageOps,
                      result: ExtractionResult) -> tuple[str, str]:
    """Render/normalize one page to a cached PNG. Returns (image_relpath, sha256).

    Content-hash cache: if the target PNG already exists (same document → same
    content-addressed source), reuse it WITHOUT re-encoding (Pitfall: repeated
    high-DPI renders). Returns the vault-relative path + the render sha256.
    """
    image_rel = f"files/rendered/{document_id}/page-{page_no:04d}.png"
    image_path = paths.resolve_within(v.root, *image_rel.split("/"))
    image_path.parent.mkdir(parents=True, exist_ok=True)
    if image_path.exists():
        png_bytes = image_path.read_bytes()
        result.cached_pages += 1
    else:
        norm = _normalize_image(pil_image, Image, ImageOps)
        buf = io.BytesIO()
        norm.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        image_path.write_bytes(png_bytes)
        result.rendered_pages += 1
    return image_rel, hashlib.sha256(png_bytes).hexdigest()


def _pdf_pages(v: vault.Vault, document_id: str, data: bytes, dpi: int,
               enable_ocr, result: ExtractionResult):
    """Process a PDF: render every page, read text, classify, add page rows.

    Yields (page_number, page_id, page_text, quality) per page.
    """
    pdfium = _import_pdfium()
    Image, ImageOps = _import_pil()
    extract_text, LAParams, PDFPage = _import_pdfminer()

    try:
        pdf = pdfium.PdfDocument(data)
        n = len(pdf)
    except pdfium.PdfiumError:
        # Encrypted / unparseable: flag one password_protected page, no render.
        page_id = vault.add_document_page(
            v, document_id=document_id, page_number=1,
            quality_json=classify_page_quality("", password_protected=True),
            extraction_run_id=result.extraction_run_id, renderer="pypdfium2",
            dpi=dpi)
        result.page_count = 1
        yield (1, page_id,
               "", classify_page_quality("", password_protected=True))
        return

    rotations = _pdf_page_rotations(data, PDFPage)
    result.page_count = n
    for i in range(n):
        page = pdf[i]
        pil = page.render(scale=dpi / 72.0).to_pil()
        width, height = pil.size
        oversize = (width * height) > _MAX_IMAGE_PIXELS
        page_text = _pdf_page_text(data, i, extract_text, LAParams)
        rotation = rotations[i] if i < len(rotations) else 0
        quality = classify_page_quality(page_text, rotation, oversize=oversize)
        # OCR only a text-empty page, only when allowed AND available.
        if quality["scanned"] and enable_ocr and tesseract_available():
            ocr_text = _ocr_image(_normalize_image(pil, Image, ImageOps))
            if ocr_text.strip():
                page_text = ocr_text
                quality = classify_page_quality(page_text, rotation,
                                                oversize=oversize)
        image_rel, render_sha = _render_and_cache(
            v, document_id, i + 1, pil, Image, ImageOps, result)
        page_id = vault.add_document_page(
            v, document_id=document_id, page_number=i + 1,
            image_relpath=image_rel, text_relpath=f"files/text/{document_id}.txt",
            render_sha256=render_sha, dpi=dpi, renderer="pypdfium2",
            width=width, height=height, quality_json=quality,
            extraction_run_id=result.extraction_run_id)
        yield (i + 1, page_id, page_text, quality)


def _image_page(v: vault.Vault, document_id: str, data: bytes, dpi: int,
                enable_ocr, result: ExtractionResult):
    """Process a single image input (jpg/png/tiff) as one page."""
    Image, ImageOps = _import_pil()
    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    pil = Image.open(io.BytesIO(data))
    pil.load()
    width, height = pil.size
    oversize = (width * height) > _MAX_IMAGE_PIXELS
    page_text = ""
    quality = classify_page_quality(page_text, 0, oversize=oversize)
    if enable_ocr and tesseract_available():
        ocr_text = _ocr_image(_normalize_image(pil, Image, ImageOps))
        if ocr_text.strip():
            page_text = ocr_text
            quality = classify_page_quality(page_text, 0, oversize=oversize)
    image_rel, render_sha = _render_and_cache(
        v, document_id, 1, pil, Image, ImageOps, result)
    result.page_count = 1
    page_id = vault.add_document_page(
        v, document_id=document_id, page_number=1, image_relpath=image_rel,
        text_relpath=f"files/text/{document_id}.txt", render_sha256=render_sha,
        dpi=dpi, renderer="pillow", width=width, height=height,
        quality_json=quality, extraction_run_id=result.extraction_run_id)
    yield (1, page_id, page_text, quality)
