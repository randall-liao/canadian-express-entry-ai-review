"""Synthetic Document & Ground Truth Schemas.

Defines strongly typed dataclasses for synthetic applicant profiles, all 22
Express Entry e-APR supporting document types plus Letters of Explanation (LoE),
and ground-truth evaluation specifications.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ExpressEntryDocType(str, Enum):
    """Enumeration of all 22 Express Entry document types plus Letter of Explanation."""

    PASSPORT = "passport"
    LANGUAGE_TEST = "language_test"
    ECA = "educational_credential_assessment"
    EMPLOYMENT_REFERENCE = "employment_reference_letter"
    PROOF_OF_FUNDS = "proof_of_funds"
    MEDICAL_EXAM = "medical_examination"
    POLICE_CERTIFICATE = "police_certificate"
    DIGITAL_PHOTO = "digital_photo"
    TRANSLATION_AFFIDAVIT = "certified_translation"
    JOB_OFFER_LMIA = "written_job_offer_lmia"
    PROOF_OF_STUDIES = "proof_of_studies"
    TRADE_CERTIFICATION = "certificate_of_qualification"
    BIRTH_CERTIFICATE = "birth_certificate"
    MARRIAGE_CERTIFICATE = "marriage_certificate"
    COMMON_LAW_DECLARATION = "statutory_declaration_common_law"
    DIVORCE_CERTIFICATE = "divorce_certificate"
    DEATH_CERTIFICATE = "death_certificate"
    ADOPTION_CERTIFICATE = "adoption_certificate"
    USE_OF_REPRESENTATIVE = "use_of_representative"
    RELATIVE_IN_CANADA = "relative_in_canada"
    LEGAL_NAME_CHANGE = "proof_of_other_name"
    RELEASE_OF_INFO = "authority_to_release_info"
    LETTER_OF_EXPLANATION = "letter_of_explanation"


@dataclass
class PassportDoc:
    passport_number: str
    issuing_country: str
    full_name: str
    dob: str
    issue_date: str
    expiry_date: str
    mrz_code: Optional[str] = None


@dataclass
class LanguageTestDoc:
    test_type: str  # IELTS, CELPIP, TEF, TCF
    test_date: str
    registration_number: str
    listening: float
    reading: float
    writing: float
    speaking: float
    clb_levels: Dict[str, int] = field(default_factory=dict)


@dataclass
class ECADoc:
    agency: str  # WES, ICAS, IQAS, CES, ICES
    ref_number: str
    issue_date: str
    degree_evaluated: str
    canadian_equivalence: str


@dataclass
class EmploymentReferenceDoc:
    employer_name: str
    job_title: str
    noc_code: str
    start_date: str
    end_date: Optional[str]  # None if current
    hours_per_week: float
    annual_salary: float
    main_duties: List[str]
    lead_statement: str
    supervisor_name: str
    supervisor_title: str
    contact_email: str


@dataclass
class ProofOfFundsDoc:
    bank_name: str
    account_number: str
    account_type: str
    current_balance: float
    average_balance_6mo: float
    outstanding_debts: float
    issue_date: str
    is_unencumbered: bool = True


@dataclass
class MedicalExamDoc:
    ime_number: str
    umi_number: str
    exam_date: str
    clinic_name: str
    doctor_name: str
    panel_physician_id: str
    result_status: str


@dataclass
class PoliceCertificateDoc:
    country: str
    issue_date: str
    subject_name: str
    is_clear: bool
    offenses: List[str] = field(default_factory=list)
    residence_start_date: Optional[str] = None
    residence_end_date: Optional[str] = None


@dataclass
class DigitalPhotoDoc:
    photo_id: str
    dimensions_mm: str
    frame_size_mm: str
    date_taken: str
    studio_name: str
    meets_ircc_spec: bool = True


@dataclass
class TranslationAffidavitDoc:
    original_language: str
    target_language: str
    translator_name: str
    certification_body: str
    affidavit_date: str
    is_certified: bool = True


@dataclass
class JobOfferLMIADoc:
    employer_name: str
    noc_code: str
    lmia_number: Optional[str]
    is_lmia_exempt: bool
    wage_offered: float
    job_duration_years: float
    is_permanent_fulltime: bool = True


@dataclass
class ProofOfStudiesDoc:
    institution_name: str
    country: str
    credential_name: str
    graduation_date: str
    has_transcript: bool = True
    is_canadian_accredited: bool = False


@dataclass
class TradeCertificationDoc:
    issuing_authority: str
    trade_name: str
    noc_code: str
    certificate_number: str
    issue_date: str


@dataclass
class BirthCertificateDoc:
    registration_number: str
    person_name: str
    dob: str
    place_of_birth: str
    father_name: str
    mother_name: str


@dataclass
class MarriageCertificateDoc:
    registration_number: str
    spouse1_name: str
    spouse2_name: str
    marriage_date: str
    marriage_place: str


@dataclass
class CommonLawDeclarationDoc:
    partner1_name: str
    partner2_name: str
    cohabitation_start_date: str
    joint_accounts_listed: List[str] = field(default_factory=list)
    sworn_date: str = ""


@dataclass
class DivorceCertificateDoc:
    court_name: str
    spouse1_name: str
    spouse2_name: str
    decree_date: str
    case_number: str


@dataclass
class DeathCertificateDoc:
    deceased_name: str
    date_of_death: str
    place_of_death: str
    registration_number: str


@dataclass
class AdoptionCertificateDoc:
    child_name: str
    adoptive_parents: List[str]
    adoption_date: str
    issuing_authority: str
    decree_number: str


@dataclass
class UseOfRepresentativeDoc:
    rep_type: str  # paid_iccrc, unpaid
    rep_name: str
    organization_name: str
    membership_number: str
    client_signature_date: str


@dataclass
class RelativeInCanadaDoc:
    relative_name: str
    relationship: str  # sibling, parent, etc.
    status_in_canada: str  # citizen, pr
    proof_of_residency: bool = True
    proof_of_relation: bool = True


@dataclass
class LegalNameChangeDoc:
    former_name: str
    new_name: str
    change_date: str
    issuing_jurisdiction: str
    certificate_number: str


@dataclass
class ReleaseOfInfoDoc:
    designated_individual: str
    relationship: str
    client_name: str
    authorization_date: str


@dataclass
class LetterOfExplanationDoc:
    topic: str  # bank_balance_fluctuation, missing_job_duties, police_cert_delay, gift_deed_explanation
    explanation_text: str
    corroborating_docs_attached: List[str] = field(default_factory=list)
    author_signature_date: str = ""


@dataclass
class SyntheticDocument:
    """Wrapper dataclass for a synthetic document fixture."""

    doc_id: str
    doc_type: ExpressEntryDocType
    title: str
    issuing_authority: str
    issue_date: str
    expiry_date: Optional[str] = None
    fields: Dict[str, Any] = field(default_factory=dict)
    raw_text: Optional[str] = None


@dataclass
class SyntheticProfile:
    """Synthetic applicant profile containing personal details and supporting documents."""

    profile_id: str
    applicant_name: str
    date_of_birth: str
    citizenship: str
    country_of_residence: str
    marital_status: str
    family_size: int = 1
    target_noc: str = "21231"
    documents: List[SyntheticDocument] = field(default_factory=list)


@dataclass
class InjectedDefect:
    """Dataclass describing an injected defect in a synthetic document."""

    defect_id: str
    category: str  # DefectCategory value string
    target_doc: str
    severity: str  # "critical" | "warning"
    field_name: Optional[str] = None
    description: str = ""
    remediation_guidance: str = ""


@dataclass
class GroundTruthSpec:
    """Ground-truth specification model for evaluating agent review accuracy."""

    doc_type: str
    expected_verdict: str  # "meets_requirements" | "defective" | "incomplete"
    injected_defects: List[InjectedDefect] = field(default_factory=list)
    expected_claims: List[Dict[str, Any]] = field(default_factory=list)
    expected_basis_keys: List[str] = field(default_factory=list)
    must_abstain: bool = False


# =============================================================================
# Pydantic v2 Schemas for Synthetic Generation, Ground Truth & Staging
# =============================================================================

class DefectSpec(BaseModel):
    """Specification of an injected defect derived from research findings."""

    research_failure_id: Optional[str] = Field(
        None, description="Source research failure ID (e.g., 'PFL-PASSPORT-01')"
    )
    category: str = Field(..., description="Defect category string")
    severity: Literal["critical", "warning"] = Field(
        "critical", description="Defect severity classification"
    )
    description: str = Field(..., description="Human-readable description of the defect")
    affected_fields: List[str] = Field(
        default_factory=list, description="Fields affected or mutated by this defect"
    )
    mutation_details: Dict[str, Any] = Field(
        default_factory=dict, description="Detailed mutation parameters"
    )

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.strip().lower()
            if val in ("critical", "high", "severe", "critical_defect"):
                return "critical"
            if val in ("warning", "medium", "low", "minor", "warn"):
                return "warning"
        return v


class TestCaseSpec(BaseModel):
    """Specification for a single synthetic document test case."""

    __test__ = False

    case_kind: Literal["valid_control", "defective_case"] = Field(
        ..., description="Kind of test case: valid control or defective case"
    )
    doc_type: ExpressEntryDocType = Field(..., description="Target document type")
    title: str = Field(..., description="Document title")
    issuing_authority: str = Field(..., description="Issuing authority name")
    issue_date: str = Field(..., description="Issue date ISO string")
    expiry_date: Optional[str] = Field(None, description="Expiry date ISO string")
    fields: Dict[str, Any] = Field(
        default_factory=dict, description="Key-value document field data"
    )
    narrative_blocks: List[str] = Field(
        default_factory=list, description="Custom narrative paragraphs"
    )
    defect_spec: Optional[DefectSpec] = Field(
        None, description="Defect specification for defective cases"
    )

    @field_validator("issue_date", mode="before")
    @classmethod
    def normalize_issue_date(cls, v: Any) -> str:
        if v is None or not str(v).strip():
            return "2023-01-15"
        return str(v)

    @field_validator("title", "issuing_authority", mode="before")
    @classmethod
    def normalize_string_fields(cls, v: Any) -> str:
        if v is None or not str(v).strip():
            return "Official Issuing Authority"
        return str(v)


class GenerationSpec(BaseModel):
    """Agent-authored generation specification containing 1 valid control + N defective cases."""

    doc_type: ExpressEntryDocType = Field(..., description="Target document type")
    timestamp: str = Field(..., description="Generation timestamp ISO string")
    cases: List[TestCaseSpec] = Field(..., description="List of synthesized test cases")

    @model_validator(mode="after")
    def validate_case_coverage(self) -> "GenerationSpec":
        valid_cases = [c for c in self.cases if c.case_kind == "valid_control"]
        if len(valid_cases) != 1:
            raise ValueError(
                f"GenerationSpec must contain exactly 1 valid_control case, got {len(valid_cases)}"
            )

        defective_cases = [c for c in self.cases if c.case_kind == "defective_case"]
        for idx, c in enumerate(defective_cases):
            if not c.defect_spec:
                raise ValueError(
                    f"Defective case index {idx} must specify a non-null defect_spec"
                )
            if not c.defect_spec.research_failure_id:
                raise ValueError(
                    f"Defective case index {idx} defect_spec must have a non-null research_failure_id"
                )

        total_cases = len(self.cases)
        if total_cases < 3:
            raise ValueError(
                f"GenerationSpec must contain at least 3 cases (1 valid control + N defective cases), got {total_cases}"
            )

        return self


class PrivateCaseRecord(BaseModel):
    """Privileged private ground truth record stored in ground_truth directory."""

    opaque_case_id: str = Field(
        ..., description="32-character hexadecimal random opaque case ID"
    )
    sibling_case_id: str = Field(
        ..., description="32-character hexadecimal random opaque sibling case ID"
    )
    doc_type: str = Field(..., description="Document type string")
    variant: Literal["vector", "scanned"] = Field(..., description="PDF variant type")
    blind_filename: str = Field(
        ..., description="Opaque blind filename, e.g. '<opaque_32hex>.pdf'"
    )
    expected_verdict: Literal["meets_requirements", "defective"] = Field(
        ..., description="Expected evaluation verdict"
    )
    source_failure_id: Optional[str] = Field(
        None, description="Source research failure ID"
    )
    affected_fields: List[str] = Field(
        default_factory=list, description="List of mutated or missing fields"
    )
    fields: Dict[str, Any] = Field(
        default_factory=dict, description="Document field data"
    )
    pdf_sha256: str = Field(..., description="SHA-256 hash of generated PDF bytes")
    agent_spec_sha256: str = Field(
        ..., description="SHA-256 hash of agent GenerationSpec JSON"
    )
    timestamp: str = Field(..., description="Record creation timestamp ISO string")

    @model_validator(mode="after")
    def validate_opaque_ids(self) -> "PrivateCaseRecord":
        if not re.match(r"^[a-f0-9]{32}$", self.opaque_case_id):
            raise ValueError(f"opaque_case_id '{self.opaque_case_id}' is not a 32-hex string")
        if not re.match(r"^[a-f0-9]{32}$", self.sibling_case_id):
            raise ValueError(f"sibling_case_id '{self.sibling_case_id}' is not a 32-hex string")
        if not re.match(r"^[a-f0-9]{32}\.pdf$", self.blind_filename):
            raise ValueError(f"blind_filename '{self.blind_filename}' must match '<32hex>.pdf'")
        return self

