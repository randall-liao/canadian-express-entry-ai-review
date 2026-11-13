"""Closed private MEC evidence vocabulary and period-safe vault adapter.

All values handled here remain inside the candidate vault.  The adapter accepts
only candidate-owned ``review.mec`` rows that pass the existing confirmation,
quality, and five-key freshness gate.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Mapping, get_args

from crawler import paths, vault
from crawler.models.mec import OfferLmiaExemptionBasis


MEC_DOCUMENT_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "mec-profile": frozenset(
            {
                "application_date",
                "eligibility_reference_date",
                "ita_date",
                "primary_noc_code",
                "work_history_scope_complete",
                "education_scope_complete",
                "language_scope_complete",
                "fsw_education_branch",
                "offer_certificate_scope_complete",
                "adaptability_scope_complete",
            }
        ),
        "mec-employment-period": frozenset(
            {
                "employment_period_id",
                "employment_start",
                "employment_end",
                "paid_status",
                "student_status",
                "self_employed",
                "work_country",
                "work_province",
                "work_authorized",
                "temporary_resident_status",
                "noc_code",
                "teer",
                "noc_version_date",
                "noc_version",
                "hours_per_week",
                "total_hours",
                "duration_months",
                "qualified_to_practise",
                "employment_continuous",
                "physically_in_canada",
                "is_remote",
                "canadian_employer_if_remote",
            }
        ),
        "mec-trade-certificate": frozenset(
            {
                "trade_certificate_authority",
                "trade_certificate_jurisdiction",
                "trade_certificate_noc_code",
                "trade_name",
                "trade_certificate_status",
                "trade_certificate_issue_date",
                "trade_certificate_expiry_date",
            }
        ),
        "mec-valid-offer": frozenset(
            {
                "offer_full_time",
                "offer_continuous",
                "offer_non_seasonal",
                "offer_paid_status",
                "offer_duration_months",
                "offer_noc_code",
                "offer_teer",
                "offer_country",
                "offer_province",
                "offer_employer_count",
                "offer_lmia_status",
                "offer_work_permit_basis",
                "offer_permit_valid_at_visa_issuance",
                "offer_lmia_exemption_basis",
                "offer_status",
                "offer_valid_from",
                "offer_valid_until",
                "offer_branch",
                "current_work_permit_status",
                "currently_working_in_canada",
                "currently_working_for_offer_employer",
                "offer_employer_matches_work_permit",
                "one_year_for_offer_employer",
                "plans_work_before_pr",
                "offer_employer_differs_current",
            }
        ),
        "mec-funds": frozenset(
            {
                "funds_household_size",
                "funds_amount",
                "funds_currency",
                "funds_as_of_date",
                "funds_accessible",
                "funds_borrowed",
                "funds_real_property_equity",
            }
        ),
        "mec-province-status": frozenset(
            {
                "intended_destination_country",
                "intended_destination_province",
                "province_status",
                "work_authorization_start",
                "work_authorization_end",
                "temporary_status_start",
                "temporary_status_end",
                "legally_authorized_to_work_canada",
            }
        ),
    }
)

MEC_FIELDS = frozenset().union(*MEC_DOCUMENT_FIELDS.values())
_PREEXISTING_FIELDS = frozenset(
    {
        "noc_code",
        "teer",
        "hours_per_week",
        "employment_start",
        "employment_end",
        "duration_months",
    }
)
MEC_ADDITIVE_FIELDS = MEC_FIELDS - _PREEXISTING_FIELDS

_BOOLEAN_FIELDS = frozenset(
    {
        "work_history_scope_complete",
        "education_scope_complete",
        "language_scope_complete",
        "offer_certificate_scope_complete",
        "adaptability_scope_complete",
        "paid_status",
        "student_status",
        "self_employed",
        "work_authorized",
        "qualified_to_practise",
        "employment_continuous",
        "physically_in_canada",
        "is_remote",
        "canadian_employer_if_remote",
        "offer_full_time",
        "offer_continuous",
        "offer_non_seasonal",
        "offer_paid_status",
        "offer_permit_valid_at_visa_issuance",
        "currently_working_in_canada",
        "currently_working_for_offer_employer",
        "offer_employer_matches_work_permit",
        "one_year_for_offer_employer",
        "plans_work_before_pr",
        "offer_employer_differs_current",
        "funds_accessible",
        "funds_borrowed",
        "funds_real_property_equity",
        "legally_authorized_to_work_canada",
    }
)
_DATE_FIELDS = frozenset(
    {
        "application_date",
        "eligibility_reference_date",
        "ita_date",
        "employment_start",
        "employment_end",
        "noc_version_date",
        "trade_certificate_issue_date",
        "trade_certificate_expiry_date",
        "funds_as_of_date",
        "work_authorization_start",
        "work_authorization_end",
        "temporary_status_start",
        "temporary_status_end",
        "offer_valid_from",
        "offer_valid_until",
    }
)
_NOC_FIELDS = frozenset(
    {"primary_noc_code", "noc_code", "trade_certificate_noc_code", "offer_noc_code"}
)
_INTEGER_FIELDS = frozenset(
    {"teer", "duration_months", "offer_teer", "offer_duration_months", "offer_employer_count",
     "funds_household_size"}
)
_NUMBER_FIELDS = frozenset({"hours_per_week", "total_hours"})
_COUNTRY_FIELDS = frozenset(
    {"work_country", "offer_country", "intended_destination_country"}
)
_PROVINCE_FIELDS = frozenset(
    {"work_province", "offer_province", "intended_destination_province"}
)
_STATUS_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "temporary_resident_status": frozenset(
            {"valid", "not_valid", "maintained", "unknown"}
        ),
        "trade_certificate_status": frozenset(
            {"valid", "expired", "revoked", "pending"}
        ),
        "offer_lmia_status": frozenset(
            {"positive", "exempt", "not_required", "missing", "unknown"}
        ),
        "offer_lmia_exemption_basis": frozenset(
            get_args(OfferLmiaExemptionBasis)
        ),
        "offer_status": frozenset({"valid", "expired", "withdrawn", "manual_review"}),
        "offer_branch": frozenset(
            {"situation_1", "situation_2", "situation_3", "situation_4"}
        ),
        "current_work_permit_status": frozenset(
            {"valid", "authorized_without_permit", "none", "invalid", "unknown"}
        ),
        "province_status": frozenset(
            {"citizen", "permanent_resident", "temporary_resident", "none"}
        ),
    }
)
_PROVINCES = MappingProxyType(
    {
        "alberta": "AB", "ab": "AB",
        "british columbia": "BC", "bc": "BC",
        "manitoba": "MB", "mb": "MB",
        "new brunswick": "NB", "nb": "NB",
        "newfoundland and labrador": "NL", "nl": "NL",
        "northwest territories": "NT", "nt": "NT",
        "nova scotia": "NS", "ns": "NS",
        "nunavut": "NU", "nu": "NU",
        "ontario": "ON", "on": "ON",
        "prince edward island": "PE", "pe": "PE",
        "quebec": "QC", "québec": "QC", "qc": "QC",
        "saskatchewan": "SK", "sk": "SK",
        "yukon": "YT", "yt": "YT",
    }
)
_COUNTRIES = MappingProxyType(
    {
        "canada": "CA", "ca": "CA",
        "united states": "US", "united states of america": "US", "us": "US",
        "france": "FR", "fr": "FR",
        "india": "IN", "in": "IN",
        "united kingdom": "GB", "uk": "GB", "gb": "GB",
    }
)
MEC_TRADE_JURISDICTIONS = frozenset(_PROVINCES.values()) | {"federal"}
_TRUE = frozenset({"true", "yes", "y", "1", "paid", "authorized"})
_FALSE = frozenset(
    {"false", "no", "n", "0", "unpaid", "not authorized", "not_authorized"}
)
_PERIOD_RE = re.compile(r"^mep_[0-9a-f]{32}$")
_PERIOD_SCOPE_ISSUE_PREFIXES = (
    "period_key_invalid:",
    "period_key_mismatch:",
    "period_cross_document:",
    "period_value_key_mismatch:",
    "period_value_invalid:",
    "period_value_conflict:",
)


def employment_period_id(source_identity: str, slot: int = 0) -> str:
    """Derive one stable opaque period key from source identity and a fixed slot."""
    if not isinstance(source_identity, str) or not source_identity.strip():
        raise ValueError("stable source identity is required")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ValueError("period slot must be a non-negative integer")
    digest = hashlib.sha256(
        f"review.mec\0mec-employment-period\0{source_identity}\0{slot}".encode()
    ).hexdigest()
    return f"mep_{digest[:32]}"


def _text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def normalize_mec_field(field_name: str, value: Any) -> tuple[Any, bool]:
    """Return ``(normalized, ambiguous)`` without coercing unknown values."""
    if field_name not in MEC_FIELDS:
        return None, True
    if isinstance(value, Mapping) and "value" in value:
        value = value["value"]
    if field_name == "employment_period_id":
        text = _text(value)
        return (text, False) if text and _PERIOD_RE.fullmatch(text) else (None, True)
    if field_name in _BOOLEAN_FIELDS:
        if isinstance(value, bool):
            return value, False
        text = _text(value)
        if text is not None:
            folded = text.casefold()
            if folded in _TRUE:
                return True, False
            if folded in _FALSE:
                return False, False
        return None, True
    if field_name in _DATE_FIELDS:
        text = _text(value)
        try:
            return date.fromisoformat(text).isoformat(), False  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None, True
    if field_name in _NOC_FIELDS:
        text = _text(str(value) if value is not None else None)
        return (text, False) if text and re.fullmatch(r"\d{5}", text) else (None, True)
    if field_name == "teer":
        if isinstance(value, bool):
            return None, True
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return None, True
        return (number, False) if 0 <= number <= 5 else (None, True)
    if field_name in _INTEGER_FIELDS:
        if isinstance(value, bool):
            return None, True
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, AttributeError):
            return None, True
        if number != number.to_integral_value() or number < 0:
            return None, True
        return int(number), False
    if field_name in _NUMBER_FIELDS:
        if isinstance(value, bool):
            return None, True
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, AttributeError):
            return None, True
        if not number.is_finite() or number < 0:
            return None, True
        return float(number), False
    if field_name == "funds_amount":
        try:
            amount = Decimal(str(value).replace(",", "").strip())
        except (InvalidOperation, ValueError, AttributeError):
            return None, True
        if not amount.is_finite() or amount < 0:
            return None, True
        return format(amount, "f"), False
    if field_name == "funds_currency":
        text = _text(value)
        text = text.upper() if text else None
        return (text, False) if text and re.fullmatch(r"[A-Z]{3}", text) else (None, True)
    if field_name in _COUNTRY_FIELDS:
        text = _text(value)
        if text is None:
            return None, True
        normalized = _COUNTRIES.get(text.casefold())
        if normalized is None and re.fullmatch(r"[A-Za-z]{2}", text):
            normalized = text.upper()
        return (normalized, False) if normalized else (None, True)
    if field_name in _PROVINCE_FIELDS:
        text = _text(value)
        normalized = _PROVINCES.get(text.casefold()) if text else None
        return (normalized, False) if normalized else (None, True)
    if field_name == "trade_certificate_jurisdiction":
        text = _text(value)
        if text and text.casefold() in {"federal", "canada"}:
            return "federal", False
        normalized = _PROVINCES.get(text.casefold()) if text else None
        return (normalized, False) if normalized else (None, True)
    if field_name == "offer_work_permit_basis":
        text = _text(value)
        normalized = text.casefold().replace("-", "_").replace(" ", "_") if text else None
        allowed = {"lmia", "lmia_exempt", "open_work_permit", "other", "unknown"}
        return (normalized, False) if normalized in allowed else (None, True)
    if field_name == "offer_lmia_exemption_basis":
        text = _text(value)
        return (
            (text, False)
            if text in _STATUS_FIELDS[field_name]
            else (None, True)
        )
    if field_name in _STATUS_FIELDS:
        text = _text(value)
        normalized = text.casefold().replace("-", "_").replace(" ", "_") if text else None
        return (
            (normalized, False)
            if normalized in _STATUS_FIELDS[field_name]
            else (None, True)
        )
    text = _text(value)
    return (text, False) if text is not None else (None, True)


@dataclass(frozen=True)
class MecEvidenceValue:
    value_id: str
    document_id: str
    doc_type: str
    field_name: str
    value: Any


@dataclass(frozen=True)
class EmploymentPeriod:
    employment_period_id: str
    document_id: str
    values: Mapping[str, Any]
    evidence_ids: tuple[str, ...]
    issues: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class MecEvidence:
    candidate_id: str
    registry_fingerprint: str
    scalars: Mapping[str, Any]
    scalar_evidence_ids: Mapping[str, tuple[str, ...]]
    periods: tuple[EmploymentPeriod, ...]
    conflicts: frozenset[str] = field(default_factory=frozenset)
    issues: tuple[str, ...] = ()

    def value(self, field_name: str, default: Any = None) -> Any:
        return self.scalars.get(field_name, default)

    @property
    def has_period_scope_issue(self) -> bool:
        """Whether any malformed period envelope makes work scope incomplete."""
        issue_sets = (self.issues, *(period.issues for period in self.periods))
        return any(
            issue.startswith(_PERIOD_SCOPE_ISSUE_PREFIXES)
            for issues in issue_sets
            for issue in issues
        )


def _effective_value(item: Any) -> Any:
    return (
        item.confirmed_value
        if item.confirmation_status == "corrected"
        else item.normalized_value
    )


def load_mec_evidence(
    vault_: vault.Vault,
    candidate_id: str,
    registry_fingerprint: str,
) -> MecEvidence:
    """Read one candidate's current confirmed MEC evidence without mutation."""
    candidate_id = paths.safe_candidate_id(candidate_id)
    if not isinstance(registry_fingerprint, str) or not registry_fingerprint:
        raise ValueError("registry fingerprint is required")
    doc_types = tuple(MEC_DOCUMENT_FIELDS)
    placeholders = ",".join("?" for _ in doc_types)
    period_rows = vault_.con.execute(
        "SELECT document_id, file_sha256 FROM documents "
        "WHERE candidate_id = ? AND doc_type = 'mec-employment-period' "
        "ORDER BY document_id",
        (candidate_id,),
    ).fetchall()
    period_documents = {
        row["document_id"]: row["file_sha256"] for row in period_rows
    }
    rows = vault_.con.execute(
        "SELECT ev.value_id, ev.document_id, ev.field_name, ev.confirmation_status, "
        "d.doc_type, d.file_sha256 "
        "FROM extracted_values ev JOIN documents d ON d.document_id = ev.document_id "
        f"WHERE d.candidate_id = ? AND ev.factor_id = 'review.mec' "
        f"AND d.doc_type IN ({placeholders}) ORDER BY d.document_id, ev.value_id",
        (candidate_id, *doc_types),
    ).fetchall()

    eligible: list[tuple[Any, Any]] = []
    for row in rows:
        if row["field_name"] not in MEC_DOCUMENT_FIELDS[row["doc_type"]]:
            continue
        if vault.is_audit_eligible(
            vault_,
            row["value_id"],
            registry_fingerprint=registry_fingerprint,
        ):
            item = vault.get_extracted_value(vault_, row["value_id"])
            if item is not None:
                eligible.append((row, item))

    scalar_values: dict[str, list[tuple[Any, str]]] = {}
    period_docs: dict[str, list[tuple[Any, Any]]] = {}
    for row, item in eligible:
        if row["doc_type"] == "mec-employment-period":
            period_docs.setdefault(row["document_id"], []).append((row, item))
            continue
        value, ambiguous = normalize_mec_field(
            row["field_name"], _effective_value(item)
        )
        if ambiguous:
            continue
        scalar_values.setdefault(row["field_name"], []).append(
            (value, row["value_id"])
        )

    scalars: dict[str, Any] = {}
    scalar_ids: dict[str, tuple[str, ...]] = {}
    conflicts: set[str] = set()
    for name, entries in scalar_values.items():
        unique = {repr(value): value for value, _ in entries}
        if len(unique) != 1:
            conflicts.add(name)
            continue
        scalars[name] = next(iter(unique.values()))
        scalar_ids[name] = tuple(sorted(value_id for _, value_id in entries))

    periods: list[EmploymentPeriod] = []
    issues: list[str] = []
    seen_period_docs: dict[str, str] = {}
    for document_id in sorted(period_documents):
        entries = period_docs.get(document_id, [])
        key_entries = [
            (row, item) for row, item in entries
            if row["field_name"] == "employment_period_id"
        ]
        if len(key_entries) != 1:
            issues.append(f"period_key_invalid:{document_id}")
            continue
        key_row, key_item = key_entries[0]
        period_id, invalid = normalize_mec_field(
            "employment_period_id", _effective_value(key_item)
        )
        expected = employment_period_id(period_documents[document_id])
        if invalid or period_id != expected:
            issues.append(f"period_key_mismatch:{document_id}")
            continue
        if period_id in seen_period_docs and seen_period_docs[period_id] != document_id:
            issues.append(f"period_cross_document:{period_id}")
            periods = [
                period for period in periods
                if period.employment_period_id != period_id
            ]
            continue
        seen_period_docs[period_id] = document_id

        grouped: dict[str, list[tuple[Any, str]]] = {}
        period_issues: list[str] = []
        evidence_ids = [key_row["value_id"]]
        for row, item in entries:
            name = row["field_name"]
            if name == "employment_period_id":
                continue
            stamped = item.normalized_value
            if (
                not isinstance(stamped, Mapping)
                or stamped.get("employment_period_id") != period_id
            ):
                period_issues.append(f"period_value_key_mismatch:{name}")
                continue
            effective = _effective_value(item)
            if item.confirmation_status == "corrected":
                if isinstance(effective, Mapping):
                    if effective.get("employment_period_id") != period_id:
                        period_issues.append(f"period_value_key_mismatch:{name}")
                        continue
                    effective = effective.get("value")
            else:
                effective = stamped.get("value")
            value, ambiguous = normalize_mec_field(name, effective)
            if ambiguous:
                period_issues.append(f"period_value_invalid:{name}")
                continue
            grouped.setdefault(name, []).append((value, row["value_id"]))
            evidence_ids.append(row["value_id"])
        values: dict[str, Any] = {}
        for name, field_entries in grouped.items():
            unique = {repr(value): value for value, _ in field_entries}
            if len(unique) != 1:
                period_issues.append(f"period_value_conflict:{name}")
            else:
                values[name] = next(iter(unique.values()))
        periods.append(
            EmploymentPeriod(
                employment_period_id=period_id,
                document_id=document_id,
                values=MappingProxyType(values),
                evidence_ids=tuple(sorted(evidence_ids)),
                issues=tuple(sorted(set(period_issues))),
            )
        )

    return MecEvidence(
        candidate_id=candidate_id,
        registry_fingerprint=registry_fingerprint,
        scalars=MappingProxyType(scalars),
        scalar_evidence_ids=MappingProxyType(scalar_ids),
        periods=tuple(periods),
        conflicts=frozenset(conflicts),
        issues=tuple(sorted(set(issues))),
    )


def employment_periods(evidence: MecEvidence) -> tuple[EmploymentPeriod, ...]:
    """Expose only internally consistent keyed period envelopes."""
    return tuple(period for period in evidence.periods if period.usable)


def eligibility_reference_date(evidence: MecEvidence) -> date:
    """Return the exact confirmed applicant eligibility anchor, or fail closed.

    The dedicated reference field is authoritative when present.  A confirmed
    ITA date is the only fallback.  Application chronology is validated when
    supplied, and conflicted/unparseable anchors are never replaced with today.
    """
    anchor_fields = {
        "application_date",
        "eligibility_reference_date",
        "ita_date",
    }
    if evidence.conflicts & anchor_fields:
        raise ValueError("MEC eligibility reference is conflicting")
    raw = evidence.value("eligibility_reference_date")
    if raw is None:
        raw = evidence.value("ita_date")
    if raw is None:
        raise ValueError("MEC eligibility reference is unavailable")
    try:
        reference = date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError("MEC eligibility reference is unavailable") from None
    application = evidence.value("application_date")
    if application is not None:
        try:
            application_date = date.fromisoformat(str(application))
        except ValueError:
            raise ValueError("MEC application date is unavailable") from None
        if application_date > reference:
            raise ValueError("MEC eligibility reference chronology is invalid")
    return reference
