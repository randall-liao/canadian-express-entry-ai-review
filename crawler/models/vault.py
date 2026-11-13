"""Pydantic v2 boundary models for the candidate vault (Phase 29 — VAULT-01/02/03).

Two PII tiers are deliberately modelled:

* FULL records (``Candidate``, ``CrsProfileFactor``, ``ItaRound``,
  ``VaultDocument``) may carry private values (claimed points, original filename,
  storage relpath). They persist ONLY inside the git-ignored ``vault.sqlite`` and
  are never emitted to stdout / public reports.
* PII-LIGHT summaries (``DocumentSummary``, ``VaultSummary``) carry ONLY ids,
  counts, doc-types, and statuses — the shapes safe to surface on the ``--json``
  stdout envelope (Plan 03). They intentionally omit ``claimed_points``,
  ``original_name``, and any absolute/relative filesystem path.

Phase 30 extends BOTH tiers with the extraction/confirmation models:

* FULL records (``ExtractionRun``, ``DocumentPage``, ``ExtractedValue``,
  ``Confirmation``) may carry the extracted PII (``raw_text``,
  ``normalized_value``, ``bbox``, ``confirmed_value``, vault-relative image/text
  paths) and persist ONLY inside ``vault.sqlite``.
* PII-LIGHT summaries (``ExtractedValueSummary``, ``ExtractionRunSummary``,
  ``DocumentPageSummary``) carry ONLY ids/field-name/status/quality/counts +
  the derived ``stale`` boolean — never a raw/normalized value, bbox, or path.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

# Public rule-domain grouping. The first four members are the frozen CRS sub-scores;
# ``program_eligibility`` is an inert MEC registry domain and is not a CRS score.
# A Literal rejects out-of-vocabulary groups at the boundary rather than persisting.
FactorGroup = Literal[
    "core_human_capital",
    "spouse_common_law",
    "skill_transferability",
    "additional_points",
    "program_eligibility",
]

# Provenance of a stored factor value. ``corrected`` is reserved for Phase 30
# field-confirmation; this phase writes ``user_entry`` / ``profile_import``.
FactorSource = Literal["user_entry", "profile_import", "corrected"]

# --------------------------------------------------------------------------- #
# Phase 30 — extraction / confirmation vocabularies (Plan 01).
#
# Each is a ``Literal`` so an out-of-vocabulary token is rejected AT THE BOUNDARY
# (pydantic ValidationError) rather than silently persisted. The vocabularies are
# the trust contract the whole milestone's fail-closed ethos rests on:
# extraction may only ever write ``pending`` values (see ``crawler.vault``).
# --------------------------------------------------------------------------- #

# The lifecycle of an extracted value. Extraction ALWAYS writes ``pending``;
# confirm/correct/reject are the only user transitions (SC3).
ConfirmationStatus = Literal["pending", "confirmed", "corrected", "rejected"]

# Scan-quality / parse-confidence flag. ``ok`` is the ONLY quality that can be
# audit-eligible (with a confirmed/corrected status + not stale); scanned /
# rotated / low-text pages flag ``low_quality`` and genuinely ambiguous parses
# flag ``ambiguous`` — never a silent ``ok`` (Pitfall 1).
QualityFlag = Literal["ok", "low_quality", "ambiguous"]

# A single user decision on ONE field (the rubber-stamp defense is that this is
# always per-value — there is no bulk "confirm all").
ConfirmationDecision = Literal["confirm", "correct", "reject"]

# How an extracted value substantiates a linked CRS factor.
EvidenceRole = Literal[
    "primary", "supporting", "issuer", "date", "score", "hours", "noc",
]

# The EXTRACT-01 structured-field vocabulary. A Literal so an unknown field name
# is rejected at the boundary. Only the field NAME is ever modelled here — the
# extracted VALUE is PII and lives in the private ``ExtractedValue`` record.
FieldName = Literal[
    # language test
    "test_type", "test_date",
    "clb_listening", "clb_reading", "clb_writing", "clb_speaking",
    "raw_score_listening", "raw_score_reading",
    "raw_score_writing", "raw_score_speaking",
    "reference_number",
    # applicant identity
    "date_of_birth",
    # educational credential assessment (ECA)
    "credential", "credential_level",
    "eca_organization", "eca_report_date",
    # Canadian-study proof (STUDY-02). ``credential_level`` above is shared with
    # ECA; these five additive names complete the six-field private study surface.
    "institution_name", "dli_number", "program_start", "program_end",
    "study_status",
    # generic issuer / occupation
    "issuer", "noc_code", "teer",
    # employment
    "hours_per_week", "employment_start", "employment_end", "duration_months",
    # provincial nomination
    "nomination_stream", "expiry_date",
    # sibling in Canada (COV-03) — names mirror crawler.siblingfields.SIBLING_FIELDS
    "sibling_relationship", "sibling_status", "sibling_residence",
    "sibling_date_of_birth",
    # Phase 43: NOC duty worksheet confirmation surface (NOC-02). Each confirmable
    # item on the grounded NOC-2021 worksheet is captured as a born-pending value
    # on the dedicated inert ``review.noc`` factor (NEVER ``core.work``). Additive
    # closed-enum extension only — ``extracted_values.field_name`` is TEXT NOT NULL
    # with no CHECK, so this Literal is the ONLY enforcement (no DB migration).
    "noc_lead_statement", "noc_duty",
    # Phase 45: additive private MEC evidence surface.  The inert review.mec
    # factor already exists in the Wave-1 FactorGroup contract; these names add no
    # scoring factor and require no SQLite migration (the column is TEXT).
    "application_date", "eligibility_reference_date", "ita_date",
    "primary_noc_code", "work_history_scope_complete",
    "education_scope_complete", "language_scope_complete",
    "fsw_education_branch",
    "offer_certificate_scope_complete", "adaptability_scope_complete",
    "employment_period_id", "paid_status", "student_status", "self_employed",
    "work_country", "work_province", "work_authorized",
    "temporary_resident_status", "noc_version_date", "noc_version",
    "total_hours", "qualified_to_practise", "employment_continuous",
    "physically_in_canada", "is_remote", "canadian_employer_if_remote",
    "trade_certificate_authority", "trade_certificate_jurisdiction",
    "trade_certificate_noc_code", "trade_name", "trade_certificate_status",
    "trade_certificate_issue_date", "trade_certificate_expiry_date",
    "offer_full_time", "offer_continuous", "offer_non_seasonal",
    "offer_paid_status",
    "offer_duration_months", "offer_noc_code", "offer_teer", "offer_country",
    "offer_province", "offer_employer_count", "offer_lmia_status",
    "offer_work_permit_basis", "offer_permit_valid_at_visa_issuance",
    "offer_lmia_exemption_basis", "offer_status",
    "offer_valid_from",
    "offer_valid_until",
    "offer_branch", "current_work_permit_status", "currently_working_in_canada",
    "currently_working_for_offer_employer",
    "offer_employer_matches_work_permit", "one_year_for_offer_employer",
    "plans_work_before_pr", "offer_employer_differs_current",
    "funds_household_size", "funds_amount", "funds_currency",
    "funds_as_of_date", "funds_accessible", "funds_borrowed",
    "funds_real_property_equity", "intended_destination_country",
    "intended_destination_province", "province_status",
    "work_authorization_start", "work_authorization_end",
    "temporary_status_start", "temporary_status_end",
    "legally_authorized_to_work_canada",
]


class ExtractionRun(BaseModel):
    """One extraction pass over a document — FULL private record (Phase 30).

    ``parser_version`` is the single source of truth (``vault.PARSER_VERSION``)
    consumed by staleness (SC4); ``engine_json`` records the tool versions used.
    Persists in ``vault.sqlite`` ONLY.
    """

    extraction_run_id: str
    document_id: str
    started_at: str
    completed_at: str | None = None
    parser_version: str
    engine_json: Any = None
    status: str = "running"  # running | complete | failed
    notes: str | None = None


class DocumentPage(BaseModel):
    """One rendered/text-extracted page — FULL private record (Phase 30).

    ``image_relpath`` / ``text_relpath`` are vault-RELATIVE paths (never absolute,
    never emitted on stdout). ``render_sha256`` binds a confirmation to the exact
    rendered bytes the user reviewed (SC4).
    """

    page_id: str
    document_id: str
    page_number: int
    image_relpath: str | None = None
    text_relpath: str | None = None
    render_sha256: str | None = None
    ocr_sha256: str | None = None
    dpi: int | None = None
    renderer: str | None = None
    width: int | None = None
    height: int | None = None
    quality_json: Any = None
    extraction_run_id: str | None = None


class ExtractedValue(BaseModel):
    """One proposed structured field — FULL private record (Phase 30).

    Born quarantined: extraction persists ``confirmation_status='pending'`` and a
    ``quality_flag`` derived from scan quality; it can never write ``confirmed``.
    ``raw_text`` / ``normalized_value`` / ``bbox`` / ``confirmed_value`` are PII
    and live in ``vault.sqlite`` ONLY — the PII-light
    :class:`ExtractedValueSummary` is what crosses the ``--json`` boundary.

    The five ``confirmed_*`` binding columns capture, at confirmation time, the
    keys a later change would invalidate (SC4): the source file sha256, the
    page/crop render sha256, the parser version, the profile-claim version, and
    the rule-registry version.
    """

    value_id: str
    document_id: str
    page_id: str | None = None
    factor_id: str | None = None
    field_name: FieldName
    raw_text: str | None = None
    normalized_value: Any = None
    bbox: Any = None
    extractor_confidence: float | None = None
    quality_flag: QualityFlag = "ok"
    extraction_run_id: str
    confirmation_status: ConfirmationStatus = "pending"
    confirmed_value: Any = None
    confirmed_at: str | None = None
    confirmed_by: str | None = None
    confirmed_file_sha256: str | None = None
    confirmed_render_sha256: str | None = None
    confirmed_parser_version: str | None = None
    confirmed_profile_claim_version: str | None = None
    confirmed_rule_registry_version: str | None = None


class Confirmation(BaseModel):
    """A single field-level confirm/correct/reject decision (Phase 30).

    ``corrected_value`` is required by the store only when ``decision=='correct'``
    (enforced in ``crawler.confirm.apply_decision``); it is arbitrary
    JSON-serializable data. FULL private record.
    """

    decision: ConfirmationDecision
    corrected_value: Any = None
    confirmed_at: str | None = None
    notes: str | None = None


class ExtractedValueSummary(BaseModel):
    """PII-LIGHT extracted-value view — safe for stdout envelopes (Phase 30).

    Carries ONLY ids/field-name/status/quality/factor + the derived ``stale``
    boolean. It NEVER carries ``raw_text``, ``normalized_value``, ``bbox``,
    ``confirmed_value``, an image path, or an original filename (locked
    constraint / Pitfall 5 & 11). ``factor_id`` is nullable (unlinked values).
    """

    value_id: str
    field_name: FieldName
    confirmation_status: ConfirmationStatus
    quality_flag: QualityFlag
    factor_id: str | None = None
    stale: bool = False


class ExtractionRunSummary(BaseModel):
    """PII-LIGHT extraction-run view — ids/counts/status only (Phase 30)."""

    extraction_run_id: str
    document_id: str
    status: str
    value_count: int = 0
    page_count: int = 0


class DocumentPageSummary(BaseModel):
    """PII-LIGHT page view — ids/number + presence booleans only (Phase 30).

    Deliberately exposes ``has_image``/``has_text`` booleans instead of the
    vault-relative ``image_relpath``/``text_relpath`` so no filesystem path
    crosses the ``--json`` boundary.
    """

    page_id: str
    document_id: str
    page_number: int
    has_image: bool = False
    has_text: bool = False


class Candidate(BaseModel):
    """A vault candidate (non-PII label only; real identity stays out of the id)."""

    candidate_id: str
    label: str | None = None
    created_at: str
    updated_at: str


class CrsProfileFactor(BaseModel):
    """One claimed CRS factor breakdown row (VAULT-01).

    ``claimed_value`` is arbitrary JSON-serializable data; the store persists it as
    ``claimed_value_json`` via ``json.dumps``. ``claimed_points`` is the private
    claimed sub-score and is NEVER surfaced in a summary.
    """

    factor_id: str
    factor_group: FactorGroup
    claimed_points: int | None = None
    claimed_level: str | None = None
    claimed_value: Any = None
    source: FactorSource = "user_entry"
    confirmed_at: str | None = None
    updated_at: str | None = None


class ItaRound(BaseModel):
    """A stored Invitation-to-Apply round + the applicant's claimed score (VAULT-01)."""

    round_id: str
    candidate_id: str
    round_label: str
    round_date: str | None = None
    program: str | None = None
    cutoff_score: int | None = None
    claimed_score: int | None = None
    source: FactorSource = "user_entry"
    created_at: str


class VaultDocument(BaseModel):
    """A content-addressed imported document (VAULT-02) — FULL private record.

    ``original_name`` and ``storage_relpath`` are private and live in the DB only.
    """

    document_id: str
    candidate_id: str
    evidence_id: str
    doc_type: str
    file_sha256: str
    storage_relpath: str
    original_name: str | None = None
    mime_type: str | None = None
    byte_size: int | None = None
    page_count: int | None = None
    added_at: str
    status: str = "added"


class DocumentSummary(BaseModel):
    """PII-LIGHT document view — safe for stdout envelopes (ids/type/status only)."""

    document_id: str
    evidence_id: str
    doc_type: str
    status: str


class VaultSummary(BaseModel):
    """PII-LIGHT vault view — counts + doc-id/status list only (VAULT-03 stdout).

    Carries NO ``claimed_points`` values, NO ``original_name``, NO filesystem path.
    ``groups_present`` lists which CRS factor groups have at least one factor.
    """

    candidate_id: str
    factor_count: int
    ita_round_count: int
    document_count: int
    groups_present: list[str] = []
    documents: list[DocumentSummary] = []
