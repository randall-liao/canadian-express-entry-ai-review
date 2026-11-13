"""Blind Worker Report Generator powered by Gemini 3.6 Flash long context.

Evaluates blind synthetic document test cases in isolated staging CWD outside repository root
with ZERO access to research reports, ground truth specs, or repository tools.
Outputs validated AnswerObject review reports.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import logging
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from crawler import searchindex
from crawler.eval.agent_runtime import (
    AgentRequest,
    AgentRuntime,
    AgentTimeoutError,
    BlobAttachment,
    ResponseValidationIssue,
    ResponseValidationPolicy,
    TransientAgentError,
    canonical_provenance_digest,
    run_async,
    validate_agent_result,
)
from crawler.eval.copilot_sdk_runtime import CopilotSdkRuntime
from crawler.eval.public_bundle import (
    build_public_review_bundle,
    find_public_content_leaks,
)
from crawler.eval.real_worker import (
    CopilotExecutionError,
    _validate_answer_object,
    _write_json,
)
from crawler.grounding import check_answer_grounding, check_claim
from crawler.synthetic.staging import stage_case_for_worker

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINES_DIR = _REPO_ROOT / "crawler" / "eval" / "pipelines"
_WORKER_STAGE_ROOT = _REPO_ROOT / "reports" / "worker_staging"
_WORKER_MODEL = "gemini-3.6-flash"
_CONTEXT_TIER = "long_context"
_LLM_TIMEOUT_SECONDS = 600
_ANSWER_FIELDS = {"question", "claims", "basis", "abstentions", "prose"}
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CAMEL_ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_CAMEL_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_PII_SENTINELS = (
    "Jane Synthetic",
    "John Synthetic",
    "Jane Doe",
    "John Doe",
    "X99999999",
    "Y88888888",
)
_SIN_REGEX = re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{3}\b")
_EMAIL_REGEX = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
_PHONE_REGEX = re.compile(
    r"(?<!\d)(?:\+?1[\s().-]*)?(?:\d[\s().-]*){10}(?!\d)"
)
_DATE_REGEX = re.compile(
    r"(?<!\d)(?:\d{8}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
    r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4})(?!\d)"
)
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_PATTERN = "|".join(_MONTHS)
_MONTH_FIRST_DATE_REGEX = re.compile(
    rf"\b(?P<month>{_MONTH_PATTERN})\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:\s*,)?\s+"
    r"(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_DAY_FIRST_DATE_REGEX = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+"
    rf"(?P<month>{_MONTH_PATTERN})(?:\s*,)?\s+"
    r"(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_COMPACT_MONTH_FIRST_DATE_REGEX = re.compile(
    rf"^(?P<month>{_MONTH_PATTERN})(?P<day>\d{{1,2}})"
    r"(?:st|nd|rd|th)?(?P<year>\d{4})$",
    re.IGNORECASE,
)
_COMPACT_DAY_FIRST_DATE_REGEX = re.compile(
    rf"^(?P<day>\d{{1,2}})(?:st|nd|rd|th)?"
    rf"(?P<month>{_MONTH_PATTERN})(?P<year>\d{{4}})$",
    re.IGNORECASE,
)
_CLAIM_FIELDS = {"id", "text", "citations", "quote"}
_ABSTENTION_FIELDS = {"text", "reason"}
_ABSTENTION_REASONS = {"not_in_corpus"}
_PUBLIC_CITATION_ID = re.compile(
    r"^[a-z0-9][a-z0-9_./-]*\.md#[0-9]{3}$"
)
_PII_CATEGORIES = (
    "address",
    "date",
    "email",
    "identifier",
    "location",
    "name",
    "phone",
    "sin",
)
_PRIVATE_PDF_SOURCE = "private_pdf"
_PRIVATE_EXTRACTION_SOURCE = "private_extraction"
_PRIVATE_FIXTURE_SOURCE = "private_fixture"
_PRIVATE_SOURCE_KINDS = {
    _PRIVATE_PDF_SOURCE,
    _PRIVATE_EXTRACTION_SOURCE,
    _PRIVATE_FIXTURE_SOURCE,
}
_PUBLIC_POLICY_CONTAINER_LABELS = {
    "policy",
    "regulation",
    "rule",
    "statute",
}
_IDENTIFIER_LABEL_TOKENS = {
    "account",
    "candidate",
    "code",
    "document",
    "eca",
    "file",
    "id",
    "identifier",
    "ime",
    "licence",
    "license",
    "number",
    "passport",
    "photo",
    "reference",
    "registration",
    "sin",
    "trf",
    "uci",
    "umi",
}
_EXPLICIT_PRIVATE_PERSON_ROOTS = {
    "affiant",
    "applicant",
    "candidate",
    "child",
    "client",
    "declarant",
    "deceased",
    "deponent",
    "employee",
    "father",
    "identity",
    "individual",
    "interpreter",
    "mother",
    "notary",
    "officiant",
    "parent",
    "partner",
    "person",
    "recipient",
    "relative",
    "representative",
    "signer",
    "spouse",
    "sponsor",
    "supervisor",
    "translator",
}
_EXPLICIT_PRIVATE_PLURAL_PERSON_ROOTS = {
    "affiants": "affiant",
    "applicants": "applicant",
    "candidates": "candidate",
    "children": "child",
    "clients": "client",
    "declarants": "declarant",
    "deponents": "deponent",
    "employees": "employee",
    "fathers": "father",
    "identities": "identity",
    "individuals": "individual",
    "interpreters": "interpreter",
    "mothers": "mother",
    "notaries": "notary",
    "officiants": "officiant",
    "parents": "parent",
    "partners": "partner",
    "people": "person",
    "persons": "person",
    "recipients": "recipient",
    "relatives": "relative",
    "representatives": "representative",
    "signers": "signer",
    "spouses": "spouse",
    "sponsors": "sponsor",
    "supervisors": "supervisor",
    "translators": "translator",
}
_EXPLICIT_PRIVATE_PERSON_COMPACT_LABELS = {
    "affiant",
    "declarant",
    "identity",
    "interpreter",
    "notary",
    "person",
    "translator",
    "translatoridentity",
    "translatorname",
}
_EXPLICIT_PRIVATE_PLURAL_PERSON_EXACT_LABELS = {
    ("full", "names"),
    ("names",),
}
_EXPLICIT_PRIVATE_PERSON_EXACT_LABELS = {
    ("contact", "person"),
    ("degree", "certificate", "name"),
    ("name",),
    ("new", "name"),
    ("previous", "name"),
} | _EXPLICIT_PRIVATE_PLURAL_PERSON_EXACT_LABELS
_EXPLICIT_PRIVATE_PERSON_SUFFIXES = (
    ("full", "name"),
    ("given", "name"),
    ("given", "names"),
    ("first", "name"),
    ("middle", "name"),
    ("middle", "names"),
    ("last", "name"),
    ("lastname",),
    ("family", "name"),
    ("surname",),
    ("maiden", "name"),
    ("previous", "family", "name"),
)
_NON_PERSON_FIELD_ROOTS = {
    "agency",
    "association",
    "authority",
    "bank",
    "clinic",
    "company",
    "credential",
    "employer",
    "institution",
    "organization",
    "program",
    "school",
    "trade",
}
_PRIVATE_CONTAINER_TOKEN_PREFIXES = (
    ("policy", "holder"),
    ("source", "of", "funds"),
    ("notary", "public"),
)
_PRIVATE_CONTAINER_MODIFIERS = {"detail", "details", "history", "metadata"}
_PRIVATE_DOCUMENT_CONTAINER_LABELS = {
    ("birth", "certificate"),
    ("identity", "document"),
    ("marriage", "certificate"),
    ("passport",),
    ("police", "certificate"),
    ("travel", "document"),
}
_EXPLICIT_PRIVATE_DOCUMENT_TOKENS = {
    "account",
    "address",
    "candidate",
    "client",
    "dob",
    "email",
    "ime",
    "passport",
    "phone",
    "sin",
    "telephone",
    "trf",
    "uci",
    "umi",
}
_PRIVATE_DOCUMENT_FIELD_ROOTS = {
    "application",
    "certificate",
    "document",
    "eca",
    "file",
    "licence",
    "license",
    "photo",
    "registration",
}
_NON_PERSON_NAME_WORDS = {
    "account",
    "application",
    "bank",
    "document",
    "documents",
    "facts",
    "funds",
    "generic",
    "must",
    "need",
    "needed",
    "needs",
    "policy",
    "proof",
    "provide",
    "provides",
    "public",
    "reference",
    "required",
    "requires",
    "requirement",
    "requirements",
    "rule",
    "should",
    "source",
    "statement",
    "submit",
    "submits",
    "submitted",
    "supporting",
}
_CLAUSE_LEADING_TOKENS = {
    "are",
    "be",
    "been",
    "being",
    "can",
    "could",
    "did",
    "do",
    "does",
    "had",
    "has",
    "have",
    "is",
    "may",
    "might",
    "must",
    "please",
    "shall",
    "should",
    "was",
    "were",
    "will",
    "would",
}
_INSTRUCTION_PREDICATE_TOKENS = {
    "apply",
    "applied",
    "applies",
    "applying",
    "attach",
    "attached",
    "attaches",
    "attaching",
    "complete",
    "completed",
    "completes",
    "completing",
    "document",
    "documents",
    "help",
    "helped",
    "helping",
    "helps",
    "include",
    "included",
    "includes",
    "including",
    "invite",
    "invited",
    "invites",
    "inviting",
    "proof",
    "proofs",
    "provide",
    "provided",
    "provides",
    "providing",
    "receive",
    "received",
    "receives",
    "receiving",
    "qualifies",
    "qualified",
    "qualify",
    "qualifying",
    "review",
    "reviewed",
    "reviewing",
    "reviews",
    "submit",
    "submits",
    "submitted",
    "submitting",
    "support",
    "supported",
    "supporting",
    "supports",
    "upload",
    "uploaded",
    "uploading",
    "uploads",
    "verify",
    "verified",
    "verifies",
    "verifying",
    "want",
    "wanted",
    "wanting",
    "wants",
}
_IDENTITY_VALUE_STOP_TOKENS = (
    _CLAUSE_LEADING_TOKENS
    | _INSTRUCTION_PREDICATE_TOKENS
    | _NON_PERSON_NAME_WORDS
    | {
        "area",
        "areas",
        "before",
        "field",
        "fields",
        "guidance",
        "marked",
        "marking",
        "value",
    }
)
_IDENTITY_LABEL_MODIFIER_TOKENS = {"field", "value"}
_ALLOWED_NAME_PARTICLES = {
    "al",
    "da",
    "de",
    "del",
    "della",
    "den",
    "der",
    "di",
    "dos",
    "du",
    "el",
    "la",
    "le",
    "van",
    "von",
}
_NON_MEANINGFUL_NAME_COMPONENTS = _ALLOWED_NAME_PARTICLES | {
    "and",
    "doctor",
    "md",
    "miss",
    "mr",
    "mrs",
    "ms",
    "prof",
    "professor",
    "rev",
}
_PERSONAL_DATE_CONTEXT_TOKENS = {
    "applicant",
    "application",
    "authorization",
    "birth",
    "declaration",
    "details",
    "document",
    "employment",
    "exam",
    "expiry",
    "explanation",
    "funds",
    "history",
    "issue",
    "marriage",
    "registration",
    "signature",
    "submission",
    "submitted",
    "supporting",
    "test",
}
_PERSON_NAME_WORD = r"[^\W\d_]+(?:[’'\-][^\W\d_]+)?"
_RELATIONSHIP_LABEL_REGEX = re.compile(
    r"\b(?:applicant|client|parent|father|mother|spouse|partner|child|"
    r"sponsor|deponent|declarant)(?:[ \t]+name)?\b[ \t]*"
    r"(?P<delimiter>:|=|-|,)[ \t]*",
    re.IGNORECASE,
)
_TITLED_NAME_REGEX = re.compile(
    rf"\b(?:notary\s+public|commissioner\s+of\s+oaths|doctor|dr\.?|"
    rf"physician)\s+"
    rf"(?P<name>{_PERSON_NAME_WORD}(?:\s+{_PERSON_NAME_WORD}){{1,5}})"
    rf"(?=\s*(?:[,.;!?]|$))",
    re.IGNORECASE,
)
_FILENAME_NAME_REGEX = re.compile(
    rf"\b(?P<name>{_PERSON_NAME_WORD}\s+{_PERSON_NAME_WORD})\s+"
    r"(?:bank\s+statement|gift\s+deed)\b",
    re.IGNORECASE,
)
_INLINE_IDENTIFIER_REGEX = re.compile(
    r"\b(?P<label>"
    r"(?:applicant|application|document|passport|account|client|certificate|"
    r"licence|license|registration|file|uci|sin|ime|umi|candidate|eca|photo|"
    r"reference|code|trf)"
    r"(?:\s+(?:reference|number|no\.?|identifier|id))?"
    r")\s*(?:[:#=]|-\s*)\s*"
    r"(?P<value>"
    r"[A-Z0-9]{1,16}"
    r"(?:(?:[-_./]| (?=[A-Z0-9]*\d))[A-Z0-9]{1,16}){0,5}"
    r")",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


class _AncestryScope(Enum):
    """Trust-boundary scope inherited while traversing structured private data."""

    NEUTRAL = "neutral"
    PUBLIC_POLICY = "public_policy"
    PRIVATE_PERSONAL = "private_personal"


@dataclass(frozen=True)
class ParentPiiManifest:
    """Parent-only normalized PII values; only aggregate commitments may persist."""

    values: Dict[str, tuple[str, ...]]
    name_component_groups: tuple[tuple[str, ...], ...]
    manifest_hash: str

    @property
    def count(self) -> int:
        return sum(len(values) for values in self.values.values()) + sum(
            len(group) for group in self.name_component_groups
        )

    @property
    def category_summary(self) -> Dict[str, int]:
        summary = {
            category: len(values)
            for category, values in self.values.items()
            if values
        }
        component_count = sum(
            len(group) for group in self.name_component_groups
        )
        if component_count:
            summary["name"] = summary.get("name", 0) + component_count
        return summary


def _normalized_lexical_tokens(value: str) -> tuple[str, ...]:
    """Return NFKC/camel-aware tokens with every control/delimiter as a boundary."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _CAMEL_ACRONYM_BOUNDARY.sub(" ", normalized)
    normalized = _CAMEL_WORD_BOUNDARY.sub(" ", normalized).casefold()
    return tuple(
        "".join(char if char.isalnum() else " " for char in normalized).split()
    )


def _normalized_words(value: str) -> str:
    return " ".join(_normalized_lexical_tokens(value))


def _normalized_person_name_words(value: str) -> str:
    """Normalize a name without interpreting legitimate capitals as boundaries."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(
        "".join(char if char.isalnum() else " " for char in normalized).split()
    )


def _normalized_compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def _valid_date_token(year: int, month: int, day: int) -> str | None:
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}{month:02d}{day:02d}"


def _date_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value)
    tokens: list[str] = []
    for match in _DATE_REGEX.finditer(normalized):
        numeric_parts = re.findall(r"\d+", match.group(0))
        candidates: list[tuple[int, int, int]] = []
        if len(numeric_parts) == 1 and len(numeric_parts[0]) == 8:
            compact = numeric_parts[0]
            candidates.extend(
                (
                    (int(compact[:4]), int(compact[4:6]), int(compact[6:])),
                    (int(compact[4:]), int(compact[2:4]), int(compact[:2])),
                    (int(compact[4:]), int(compact[:2]), int(compact[2:4])),
                )
            )
        elif len(numeric_parts) == 3 and len(numeric_parts[0]) == 4:
            candidates.append(tuple(int(part) for part in numeric_parts))
        elif len(numeric_parts) == 3:
            first, second, year = (int(part) for part in numeric_parts)
            candidates.extend(
                (
                    (year, first, second),
                    (year, second, first),
                )
            )
        else:
            continue
        for year, month, day in candidates:
            date_key = _valid_date_token(year, month, day)
            if date_key is not None:
                tokens.append(date_key)
    for pattern in (_MONTH_FIRST_DATE_REGEX, _DAY_FIRST_DATE_REGEX):
        for match in pattern.finditer(normalized):
            date_key = _valid_date_token(
                int(match.group("year")),
                _MONTHS[match.group("month").casefold()],
                int(match.group("day")),
            )
            if date_key is not None:
                tokens.append(date_key)
    return tuple(dict.fromkeys(tokens))


def _compact_date_tokens(value: str) -> tuple[str, ...]:
    """Parse one punctuation-free numeric or textual date candidate."""
    compact = _normalized_compact(value)
    if not compact:
        return ()
    if compact.isdigit():
        return _date_tokens(compact)
    tokens: list[str] = []
    for pattern in (
        _COMPACT_MONTH_FIRST_DATE_REGEX,
        _COMPACT_DAY_FIRST_DATE_REGEX,
    ):
        match = pattern.fullmatch(compact)
        if match is None:
            continue
        date_key = _valid_date_token(
            int(match.group("year")),
            _MONTHS[match.group("month").casefold()],
            int(match.group("day")),
        )
        if date_key is not None:
            tokens.append(date_key)
    return tuple(dict.fromkeys(tokens))


def _compact_token_window_matches(
    public_tokens: tuple[str, ...],
    normalized_value: str,
) -> bool:
    """Match one PII value exactly across a contiguous lexical-token window."""
    target = _normalized_compact(normalized_value)
    if not target:
        return False
    for start in range(len(public_tokens)):
        candidate = ""
        for token in public_tokens[start:]:
            candidate += token
            if candidate == target:
                return True
            if len(candidate) >= len(target):
                break
    return False


def _public_date_tokens(
    value: str,
    lexical_tokens: tuple[str, ...],
) -> set[str]:
    """Parse ordinary dates plus compact contiguous lexical date windows."""
    tokens = set(_date_tokens(value))
    max_candidate_length = max(len(month) for month in _MONTHS) + 10
    for start in range(len(lexical_tokens)):
        candidate = ""
        for part in lexical_tokens[start:]:
            candidate += part
            if len(candidate) > max_candidate_length:
                break
            tokens.update(_compact_date_tokens(candidate))
    return tokens


def _label_tokens(label: str) -> tuple[str, ...]:
    """Tokenize every field/source label through one Unicode-aware path."""
    return _normalized_lexical_tokens(label)


def _canonical_private_person_label_tokens(
    tokens: Sequence[str],
) -> tuple[str, ...]:
    """Canonicalize exact plural roots and remove possessive markers."""
    canonical: list[str] = []
    for index, token in enumerate(tokens):
        if (
            token == "s"
            and canonical
            and canonical[-1] in _EXPLICIT_PRIVATE_PERSON_ROOTS
            and index + 1 < len(tokens)
        ):
            continue
        canonical.append(_EXPLICIT_PRIVATE_PLURAL_PERSON_ROOTS.get(token, token))
    return tuple(canonical)


def _has_explicit_private_person_token_semantics(
    raw_tokens: Sequence[str],
) -> bool:
    """Classify canonical person-label tokens for private fields and public syntax."""
    tokens = _canonical_private_person_label_tokens(raw_tokens)
    if not tokens:
        return False
    compact = "".join(tokens)
    if compact in _EXPLICIT_PRIVATE_PERSON_COMPACT_LABELS:
        return True
    contact_person = tokens[-2:] == ("contact", "person")
    if contact_person:
        return True
    if set(tokens).intersection(_NON_PERSON_FIELD_ROOTS) and not contact_person:
        return False
    if tokens in _EXPLICIT_PRIVATE_PERSON_EXACT_LABELS:
        return True
    if any(
        len(tokens) >= len(suffix) and tokens[-len(suffix) :] == suffix
        for suffix in _EXPLICIT_PRIVATE_PERSON_SUFFIXES
    ):
        return True
    roots = set(tokens).intersection(_EXPLICIT_PRIVATE_PERSON_ROOTS)
    if not roots:
        return False
    if len(tokens) == 1:
        return True
    return bool(
        tokens[-1] in {"name", "names", "signature"}
        or tokens[-2:] == ("full", "name")
        or tokens[-1] == "identity"
    )


def _has_plural_private_person_token_semantics(
    raw_tokens: Sequence[str],
) -> bool:
    """Recognize labels that denote multiple people, not one person's name parts."""
    tokens = tuple(raw_tokens)
    if not _has_explicit_private_person_token_semantics(tokens):
        return False
    if any(token in _EXPLICIT_PRIVATE_PLURAL_PERSON_ROOTS for token in tokens):
        return True
    canonical = _canonical_private_person_label_tokens(tokens)
    if canonical in _EXPLICIT_PRIVATE_PLURAL_PERSON_EXACT_LABELS:
        return True
    return bool(
        canonical[-1:] == ("names",)
        and set(canonical).intersection(_EXPLICIT_PRIVATE_PERSON_ROOTS)
        and not set(canonical).intersection({"given", "middle"})
    )


def _has_private_policy_holder_semantics(label: str) -> bool:
    """Keep policy-holder fields private under camel, snake, and compact forms."""
    tokens = _label_tokens(label)
    compact = "".join(tokens)
    return "policyholder" in compact or (
        "policy" in tokens and "holder" in tokens
    )


def _is_private_personal_container(label: str) -> bool:
    """Recognize exact private container families and their metadata wrappers."""
    tokens = _label_tokens(label)
    compact = "".join(tokens)
    if _has_private_policy_holder_semantics(label):
        return True
    for prefix in _PRIVATE_CONTAINER_TOKEN_PREFIXES:
        compact_prefix = "".join(prefix)
        if tokens[: len(prefix)] == prefix and all(
            token in _PRIVATE_CONTAINER_MODIFIERS for token in tokens[len(prefix) :]
        ):
            return True
        if compact == compact_prefix or any(
            compact == f"{compact_prefix}{modifier}"
            for modifier in _PRIVATE_CONTAINER_MODIFIERS
        ):
            return True
    return False


def _is_private_document_container(label: str) -> bool:
    """Recognize exact person-bearing document containers, never substrings."""
    return _label_tokens(label) in _PRIVATE_DOCUMENT_CONTAINER_LABELS


def _has_explicit_private_document_semantics(label: str) -> bool:
    """Recognize exact private document/identity fields under public metadata."""
    if _is_public_field_semantics(label):
        return False
    tokens = set(_label_tokens(label))
    if tokens.intersection(_EXPLICIT_PRIVATE_DOCUMENT_TOKENS):
        return True
    if "birth" in tokens and tokens.intersection(
        {"city", "country", "date", "location", "place"}
    ):
        return True
    return bool(
        tokens.intersection(_PRIVATE_DOCUMENT_FIELD_ROOTS)
        and tokens.intersection(_IDENTIFIER_LABEL_TOKENS)
    )


def _is_public_policy_container(label: str) -> bool:
    """Recognize explicit whole-label public policy metadata containers."""
    tokens = _label_tokens(label)
    if not tokens or _has_private_policy_holder_semantics(label):
        return False

    modifiers = {"detail", "details", "history", "metadata"}
    compact = "".join(tokens)
    policy_source_labels = {
        f"{prefix}policysource{suffix}"
        for prefix in ("", "public")
        for suffix in ("", "detail", "details", "metadata")
    }
    if compact in policy_source_labels:
        return True
    compact_labels = {
        candidate
        for root in _PUBLIC_POLICY_CONTAINER_LABELS
        for candidate in (
            root,
            f"{root}detail",
            f"{root}details",
            f"{root}history",
            f"{root}metadata",
            f"public{root}",
            f"public{root}detail",
            f"public{root}details",
            f"public{root}history",
            f"public{root}metadata",
        )
    }
    if compact in compact_labels:
        return True

    root_index = 1 if tokens[0] == "public" else 0
    return bool(
        root_index < len(tokens)
        and tokens[root_index] in _PUBLIC_POLICY_CONTAINER_LABELS
        and all(token in modifiers for token in tokens[root_index + 1 :])
    )


def _is_public_field_semantics(label: str) -> bool:
    """Exclude only direct labels that identify public policy/citation metadata."""
    if _has_private_policy_holder_semantics(label):
        return False
    tokens = set(_label_tokens(label))
    identifier_tokens = tokens.intersection(_IDENTIFIER_LABEL_TOKENS)
    if "citation" in tokens:
        return True
    if {"noc", "code"}.issubset(tokens):
        return True
    if tokens.intersection(_PUBLIC_POLICY_CONTAINER_LABELS) and (
        identifier_tokens
        or "effective" in tokens
        or "date" in tokens
    ):
        return True
    return bool(
        "source" in tokens
        and tokens.intersection(
            {"citation", "corpus", "document", "policy", "public", "rule"}
        )
        and identifier_tokens
    )


def _is_public_date_context(label: str) -> bool:
    if _has_private_policy_holder_semantics(label):
        return False
    tokens = set(_label_tokens(label))
    return bool(
        tokens.intersection(_PUBLIC_POLICY_CONTAINER_LABELS)
        and tokens.intersection({"date", "effective", "issue", "issued"})
    )


def _looks_like_person_name(value: str) -> bool:
    candidate = value.strip()
    if candidate.endswith((".", "!", "?")):
        candidate = candidate[:-1].rstrip()
    name_match = re.fullmatch(
        rf"(?P<name>{_PERSON_NAME_WORD}(?:[ \t]+{_PERSON_NAME_WORD}){{1,5}})",
        candidate,
    )
    if name_match is None:
        return False
    words = re.findall(_PERSON_NAME_WORD, name_match.group("name"))
    folded_words = tuple(word.casefold() for word in words)
    lexical_tokens = set(_normalized_lexical_tokens(name_match.group("name")))
    if not words or folded_words[0] in _CLAUSE_LEADING_TOKENS:
        return False
    if lexical_tokens.intersection(
        _CLAUSE_LEADING_TOKENS | _INSTRUCTION_PREDICATE_TOKENS
    ):
        return False
    if lexical_tokens.intersection(_NON_PERSON_NAME_WORDS):
        return False
    return all(_is_strict_name_word(word) for word in words)


def _has_person_name_casing(value: str) -> bool:
    words = re.findall(_PERSON_NAME_WORD, value)
    return bool(words) and all(_is_strict_name_word(word) for word in words)


def _is_strict_name_word(word: str) -> bool:
    """Accept title-cased name components and explicit lowercase particles."""
    parts = re.split(r"[’'\-]", word)
    return bool(parts) and all(
        (
            part[0].isupper() and part[1:] == part[1:].lower()
        ) or (
            part == part.casefold()
            and part.casefold() in _ALLOWED_NAME_PARTICLES
        )
        for part in parts
        if part
    )


def _relationship_name_candidates(value: str) -> tuple[str, ...]:
    """Extract complete names only after an explicit person-label delimiter."""
    candidates: list[str] = []
    for label_match in _RELATIONSHIP_LABEL_REGEX.finditer(value):
        remainder = value[label_match.end() :].strip()
        complete_value = re.fullmatch(
            rf"(?P<name>{_PERSON_NAME_WORD}(?:[ \t]+{_PERSON_NAME_WORD}){{1,5}})"
            rf"[ \t]*[.!?]?",
            remainder,
        )
        if complete_value is None:
            continue
        candidate = complete_value.group("name")
        lexical_tokens = set(_normalized_lexical_tokens(candidate))
        if (
            _is_safe_structured_person_value(candidate)
            and not lexical_tokens.intersection(
                _CLAUSE_LEADING_TOKENS
                | _INSTRUCTION_PREDICATE_TOKENS
                | _NON_PERSON_NAME_WORDS
            )
        ):
            candidates.append(candidate)
    return tuple(candidates)


def _has_explicit_private_person_semantics(label: str) -> bool:
    """Recognize only complete person-bearing field labels, not status fields."""
    return _has_explicit_private_person_token_semantics(_label_tokens(label))


def _is_safe_structured_person_value(value: str) -> bool:
    """Apply bounded content safety without imposing any capitalization style."""
    candidate = unicodedata.normalize("NFKC", value).strip()
    normalized = _normalized_person_name_words(candidate)
    letter_count = sum(
        unicodedata.category(char).startswith("L") for char in candidate
    )
    if (
        not candidate
        or len(candidate) > 200
        or letter_count < 1
        or "\n" in candidate
        or "\r" in candidate
        or any(char.isdigit() for char in candidate)
        or normalized in {
            "missing",
            "n a",
            "none",
            "not applicable",
            "not available",
            "not provided",
            "null",
            "unknown",
            "unverified",
        }
    ):
        return False
    return all(
        char.isspace()
        or char in {"'", "’", ",", "-", "."}
        or unicodedata.category(char)[0] in {"L", "M"}
        for char in candidate
    )


def _is_safe_narrative_person_value(label: str, value: str) -> bool:
    """Reject clause predicates from role-only narrative labels."""
    if not _is_safe_structured_person_value(value):
        return False
    if "name" in _label_tokens(label):
        return True
    lexical_tokens = set(_normalized_lexical_tokens(value))
    return not lexical_tokens.intersection(
        _CLAUSE_LEADING_TOKENS
        | _INSTRUCTION_PREDICATE_TOKENS
        | _NON_PERSON_NAME_WORDS
    )


def _last_first_person_values(
    comma_values: Sequence[str],
) -> tuple[str, ...]:
    """Parse a complete alternating Last, First sequence without partial pairing."""
    if len(comma_values) < 2 or len(comma_values) % 2:
        return ()
    individual_values: list[str] = []
    for family_name, given_names in zip(
        comma_values[::2],
        comma_values[1::2],
    ):
        if re.fullmatch(_PERSON_NAME_WORD, family_name) is None:
            return ()
        given_atom = rf"(?:[^\W\d_]\.|{_PERSON_NAME_WORD})"
        if re.fullmatch(
            rf"{given_atom}(?:[ \t]+{given_atom}){{0,2}}",
            given_names,
        ) is None:
            return ()
        normalized_given_names = " ".join(
            atom[:-1] if len(atom) == 2 and atom.endswith(".") else atom
            for atom in given_names.split()
        )
        individual_values.append(f"{normalized_given_names} {family_name}")
    return tuple(individual_values)


def _structured_person_name_values(label: str, value: str) -> tuple[str, ...]:
    """Split explicit structured person lists without merging unrelated people."""
    if not _has_explicit_private_person_semantics(label):
        return ()
    candidate = unicodedata.normalize("NFKC", value).strip()
    if not candidate:
        return ()
    label_tokens = _label_tokens(label)
    if _has_plural_private_person_token_semantics(label_tokens):
        conjunction_pattern = r"\s+and\s+|\s*&\s*|\s*;\s*|\s*/\s*|\s*\|\s*|\r?\n+"
        if (
            "parent" in _canonical_private_person_label_tokens(label_tokens)
            and label_tokens[-1:] == ("names",)
        ):
            conjunction_pattern += r"|\s+y\s+"
        separated_values = tuple(
            part.strip()
            for part in re.split(
                conjunction_pattern,
                candidate,
                flags=re.IGNORECASE,
            )
            if part.strip()
        )
        individual_values: list[str] = []
        for separated_value in separated_values:
            comma_values = tuple(
                part.strip()
                for part in separated_value.split(",")
                if part.strip()
            )
            last_first_values = _last_first_person_values(comma_values)
            if last_first_values:
                individual_values.extend(last_first_values)
            elif len(comma_values) > 1:
                individual_values.extend(comma_values)
            else:
                individual_values.append(separated_value)
        if len(individual_values) > 1:
            if all(
                _is_safe_structured_person_value(part)
                for part in individual_values
            ):
                return tuple(individual_values)
            return ()
    if _is_safe_structured_person_value(candidate):
        return (candidate,)
    return ()


def _child_ancestry_scope(
    ancestry_scope: _AncestryScope,
    label: str,
) -> _AncestryScope:
    """Resolve one child scope with sticky private ancestry precedence."""
    if ancestry_scope is _AncestryScope.PRIVATE_PERSONAL:
        return ancestry_scope
    if (
        _is_private_personal_container(label)
        or _has_explicit_private_person_semantics(label)
        or _is_private_document_container(label)
        or _has_explicit_private_document_semantics(label)
    ):
        return _AncestryScope.PRIVATE_PERSONAL
    if ancestry_scope is _AncestryScope.PUBLIC_POLICY:
        return ancestry_scope
    if _is_public_policy_container(label):
        return _AncestryScope.PUBLIC_POLICY
    return _AncestryScope.NEUTRAL


def _pii_category_for_label(
    label: str,
    value: str,
    *,
    source_kind: str = _PRIVATE_FIXTURE_SOURCE,
    ancestry_scope: _AncestryScope = _AncestryScope.NEUTRAL,
) -> str | None:
    label_tokens = set(_label_tokens(label))
    if ancestry_scope is _AncestryScope.PUBLIC_POLICY:
        return None
    if (
        ancestry_scope is not _AncestryScope.PRIVATE_PERSONAL
        and _is_public_field_semantics(label)
    ):
        return None
    if "email" in label_tokens:
        return "email"
    if "phone" in label_tokens or "telephone" in label_tokens:
        return "phone"
    if "address" in label_tokens:
        return "address"
    if (
        "birthplace" in label_tokens
        or (
            "birth" in label_tokens
            and label_tokens.intersection({"city", "country", "location", "place"})
        )
        or label_tokens.intersection({"location", "residence"})
    ):
        return "location"
    if (
        "dob" in label_tokens
        or "birth" in label_tokens
        or "date" in label_tokens
    ):
        return "date"
    identifier_semantics = (
        source_kind in _PRIVATE_SOURCE_KINDS
        and any(char.isdigit() for char in value)
        and bool(label_tokens.intersection(_IDENTIFIER_LABEL_TOKENS))
    )
    if identifier_semantics:
        return "sin" if "sin" in label_tokens else "identifier"
    if _structured_person_name_values(label, value):
        return "name"
    return None


def _add_pii_value(
    values: Dict[str, set[str]],
    category: str,
    raw_value: str,
    *,
    name_component_groups: Optional[set[tuple[str, ...]]] = None,
    allow_single_token_name: bool = False,
    record_name_component_group: bool = True,
) -> None:
    if not isinstance(raw_value, str):
        return
    cleaned = raw_value.strip()
    if not cleaned or cleaned.casefold() in {"n/a", "none", "null", "unknown"}:
        return
    if category == "date":
        for normalized in _date_tokens(cleaned):
            values[category].add(normalized)
        return
    elif category in {"identifier", "phone", "sin"}:
        normalized = _normalized_compact(cleaned)
        if category == "identifier" and not any(
            char.isdigit() for char in normalized
        ):
            return
    elif category == "email":
        match = _EMAIL_REGEX.search(unicodedata.normalize("NFKC", cleaned))
        normalized = match.group(0).casefold() if match else None
    elif category == "name":
        normalized = _normalized_person_name_words(cleaned)
    else:
        normalized = _normalized_words(cleaned)
    if normalized is None:
        return
    if category == "name":
        if sum(
            unicodedata.category(char).startswith("L") for char in cleaned
        ) < 1:
            return
    elif len(normalized) < 5:
        return
    if (
        category == "name"
        and not allow_single_token_name
        and len(normalized.split()) < 2
    ):
        return
    if category == "name":
        normalized_components = tuple(
            dict.fromkeys(
                component
                for component in normalized.split()
                if any(char.isalpha() for char in component)
                and component not in _NON_MEANINGFUL_NAME_COMPONENTS
            )
        )
        if (
            record_name_component_group
            and name_component_groups is not None
            and normalized_components
        ):
            name_component_groups.add(normalized_components)
        if len(normalized.split()) >= 2:
            values[category].add(normalized)
    else:
        values[category].add(normalized)
    if category == "address":
        tokens = normalized.split()
        search_start = (
            2
            if len(tokens) >= 3
            and tokens[0] in {"apartment", "apt", "suite", "unit"}
            and any(char.isdigit() for char in tokens[1])
            else 0
        )
        street_index = next(
            (
                index
                for index, token in enumerate(
                    tokens[search_start : search_start + 4],
                    start=search_start,
                )
                if any(char.isdigit() for char in token)
                and token.isalnum()
            ),
            None,
        )
        if street_index is not None and len(tokens) >= street_index + 3:
            values[category].add(
                " ".join(tokens[street_index : street_index + 3])
            )
            if len(tokens) >= street_index + 4:
                values[category].add(
                    " ".join(tokens[street_index : street_index + 4])
                )
    elif category == "location":
        tokens = normalized.split()
        if len(tokens) >= 3:
            values[category].add(" ".join(tokens[:2]))


def _add_structured_person_pii_value(
    values: Dict[str, set[str]],
    label: str,
    raw_value: str,
    *,
    name_component_groups: Optional[set[tuple[str, ...]]] = None,
) -> None:
    """Record a complete aggregate but associate components per individual only."""
    individual_values = _structured_person_name_values(label, raw_value)
    if not individual_values:
        return
    if len(individual_values) > 1:
        _add_pii_value(
            values,
            "name",
            raw_value,
            name_component_groups=name_component_groups,
            allow_single_token_name=True,
            record_name_component_group=False,
        )
    for individual_value in individual_values:
        _add_pii_value(
            values,
            "name",
            individual_value,
            name_component_groups=name_component_groups,
            allow_single_token_name=True,
        )


def _immediate_identity_name_tokens(
    normalized_value: str,
    lexemes: Sequence[tuple[str, int, int]],
    start: int,
    protected_components: set[str],
) -> tuple[str, ...]:
    """Parse only the immediate, name-shaped value after identity syntax."""
    value_tokens: list[str] = []
    previous_end = lexemes[start - 1][2] if start else 0
    for index in range(start, min(len(lexemes), start + 6)):
        token, token_start, token_end = lexemes[index]
        if value_tokens and any(
            delimiter in normalized_value[previous_end:token_start]
            for delimiter in ".,;!?=:#|/"
        ):
            break
        raw_lexeme = normalized_value[token_start:token_end]
        protected = token in protected_components
        if token in _IDENTITY_VALUE_STOP_TOKENS and not protected:
            break
        if not protected and not (
            _is_strict_name_word(raw_lexeme)
            or (len(raw_lexeme) > 1 and raw_lexeme.isupper())
        ):
            break
        value_tokens.append(token)
        previous_end = token_end
    return tuple(value_tokens)


def _identity_context_component_match(
    public_value: str,
    protected_components: set[str],
) -> bool:
    """Parse bounded, explicit identity syntax against canonical person labels."""
    normalized = unicodedata.normalize("NFKC", public_value)
    normalized = _CAMEL_ACRONYM_BOUNDARY.sub(" ", normalized)
    normalized = _CAMEL_WORD_BOUNDARY.sub(" ", normalized)
    lexemes = tuple(
        (match.group(0).casefold(), match.start(), match.end())
        for match in re.finditer(r"[^\W_]+", normalized, re.UNICODE)
    )
    if not lexemes:
        return False

    honorifics = {
        "doctor",
        "dr",
        "miss",
        "mr",
        "mrs",
        "ms",
        "prof",
        "professor",
        "rev",
    }
    for index, (token, _start, _end) in enumerate(lexemes):
        if token not in honorifics or index + 1 >= len(lexemes):
            continue
        value_tokens = _immediate_identity_name_tokens(
            normalized,
            lexemes,
            index + 1,
            protected_components,
        )
        if value_tokens and value_tokens[0] in protected_components:
            return True

    max_label_tokens = max(
        max(len(label) for label in _EXPLICIT_PRIVATE_PERSON_EXACT_LABELS),
        max(len(suffix) for suffix in _EXPLICIT_PRIVATE_PERSON_SUFFIXES) + 2,
    )
    for start in range(len(lexemes)):
        label_tokens: tuple[str, ...] = ()
        plural_person_label = False
        label_end = start
        for end in range(
            min(len(lexemes), start + max_label_tokens),
            start,
            -1,
        ):
            candidate = tuple(token for token, _begin, _finish in lexemes[start:end])
            if _has_explicit_private_person_token_semantics(candidate):
                label_tokens = _canonical_private_person_label_tokens(candidate)
                plural_person_label = (
                    _has_plural_private_person_token_semantics(candidate)
                )
                label_end = end
                break
        if not label_tokens or label_end >= len(lexemes):
            continue

        value_start = label_end
        modifier_index: Optional[int] = None
        allowed_copulas = {"is", "was"}
        if plural_person_label:
            allowed_copulas.update({"are", "were"})

        leading_gap = normalized[
            lexemes[label_end - 1][2] : lexemes[value_start][1]
        ]
        protected_value_started = (
            lexemes[value_start][0] in protected_components
            and any(char in ":=,#-\n\r" for char in leading_gap)
        )
        if (
            lexemes[value_start][0] in _IDENTITY_LABEL_MODIFIER_TOKENS
            and not protected_value_started
        ):
            if value_start + 1 < len(lexemes):
                next_lexeme = lexemes[value_start + 1][0]
                mod_separator = normalized[
                    lexemes[value_start][2] : lexemes[value_start + 1][1]
                ]
                has_mod_separator = any(
                    char in ":=,#-\n\r" for char in mod_separator
                )
                if has_mod_separator or next_lexeme in allowed_copulas:
                    modifier_index = value_start
                    value_start += 1

        used_copula = lexemes[value_start][0] in allowed_copulas
        if used_copula:
            value_start += 1
        if value_start >= len(lexemes):
            continue
        name_specific_label = bool(
            set(label_tokens).intersection(
                {"identity", "name", "names", "surname"}
            )
            or label_tokens[-2:] == ("contact", "person")
        )
        separator_index = (
            modifier_index if modifier_index is not None else label_end - 1
        )
        label_separator = normalized[
            lexemes[separator_index][2] : lexemes[value_start][1]
        ]
        has_explicit_separator = any(
            char in ":=,#-\n\r" for char in label_separator
        )
        if (
            modifier_index is not None
            and not used_copula
            and not has_explicit_separator
        ):
            continue
        value_tokens = _immediate_identity_name_tokens(
            normalized,
            lexemes,
            value_start,
            (
                protected_components
                if used_copula or has_explicit_separator
                else set()
            ),
        )
        if not value_tokens or value_tokens[0] not in protected_components:
            continue

        if name_specific_label and not used_copula and not has_explicit_separator:
            continue
        return True
    return False


def _public_name_component_match(
    public_value: str,
    public_tokens: tuple[str, ...],
    name_component_groups: tuple[tuple[str, ...], ...],
) -> bool:
    """Match protected name parts only inside bounded identity-bearing syntax."""
    if not name_component_groups:
        return False
    protected_components = {
        component
        for group in name_component_groups
        for component in group
    }
    if _identity_context_component_match(public_value, protected_components):
        return True

    for group in name_component_groups:
        group_components = set(group)
        if len(group_components) < 2:
            continue
        for start, token in enumerate(public_tokens):
            if token not in group_components:
                continue
            matched_components = {token}
            for end in range(start + 1, min(len(public_tokens), start + 6)):
                candidate = public_tokens[end]
                if candidate in group_components:
                    matched_components.add(candidate)
                    if len(matched_components) >= 2:
                        return True
                    continue
                if candidate in _ALLOWED_NAME_PARTICLES or (
                    len(candidate) == 1 and candidate.isalpha()
                ):
                    continue
                break
    return False


def _collect_text_pii(
    values: Dict[str, set[str]],
    text: str,
    *,
    name_component_groups: Optional[set[tuple[str, ...]]] = None,
    context_label: str = "",
    source_kind: str = _PRIVATE_EXTRACTION_SOURCE,
    ancestry_scope: _AncestryScope = _AncestryScope.NEUTRAL,
) -> None:
    if not text:
        return
    for line in text.splitlines():
        match = re.match(r"\s*([^:\n]{2,80})\s*:\s*(.+?)\s*$", line)
        if match:
            active_label = match.group(1).strip()
            active_text = match.group(2)
            active_scope = _child_ancestry_scope(ancestry_scope, active_label)
            category = _pii_category_for_label(
                active_label,
                active_text,
                source_kind=source_kind,
                ancestry_scope=active_scope,
            )
            if category is not None:
                if category == "name":
                    individual_values = _structured_person_name_values(
                        active_label,
                        active_text,
                    )
                    if (
                        len(individual_values) > 1
                        or _is_safe_narrative_person_value(
                            active_label,
                            active_text,
                        )
                    ):
                        _add_structured_person_pii_value(
                            values,
                            active_label,
                            active_text,
                            name_component_groups=name_component_groups,
                        )
                else:
                    _add_pii_value(
                        values,
                        category,
                        active_text,
                        name_component_groups=name_component_groups,
                    )
        else:
            active_label = context_label
            active_text = line
            active_scope = ancestry_scope
        if active_scope is _AncestryScope.PUBLIC_POLICY or (
            active_scope is not _AncestryScope.PRIVATE_PERSONAL
            and _is_public_field_semantics(active_label)
        ):
            continue
        canonical_text = unicodedata.normalize("NFKC", active_text)
        for email_match in _EMAIL_REGEX.finditer(canonical_text):
            _add_pii_value(values, "email", email_match.group(0))
        for phone_match in _PHONE_REGEX.finditer(canonical_text):
            _add_pii_value(values, "phone", phone_match.group(0))
        for sin_match in _SIN_REGEX.finditer(canonical_text):
            _add_pii_value(values, "sin", sin_match.group(0))
        date_context = f"{active_label} {canonical_text}".strip()
        if (
            set(_label_tokens(date_context)).intersection(
                _PERSONAL_DATE_CONTEXT_TOKENS
            )
            and (
                active_scope is _AncestryScope.PRIVATE_PERSONAL
                or not _is_public_date_context(date_context)
            )
        ):
            _add_pii_value(values, "date", canonical_text)
        for identifier_match in _INLINE_IDENTIFIER_REGEX.finditer(canonical_text):
            identifier_label = identifier_match.group("label")
            category = _pii_category_for_label(
                identifier_label,
                identifier_match.group("value"),
                source_kind=source_kind,
                ancestry_scope=active_scope,
            )
            if category is not None:
                _add_pii_value(
                    values,
                    category,
                    identifier_match.group("value"),
                )
        filename_text = canonical_text.replace("_", " ")
        for candidate in _relationship_name_candidates(canonical_text):
            _add_pii_value(
                values,
                "name",
                candidate,
                name_component_groups=name_component_groups,
            )
        for pattern, searchable_text in (
            (_TITLED_NAME_REGEX, canonical_text),
            (_FILENAME_NAME_REGEX, filename_text),
        ):
            for name_match in pattern.finditer(searchable_text):
                candidate = name_match.group("name")
                if (
                    _looks_like_person_name(candidate)
                    and _has_person_name_casing(candidate)
                ):
                    _add_pii_value(
                        values,
                        "name",
                        candidate,
                        name_component_groups=name_component_groups,
                    )


def _pdf_labelled_fields(pdf_path: Path) -> list[tuple[str, str]]:
    """Extract same-row label/value pairs from vector PDF layout."""
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer

        fields: list[tuple[str, str]] = []
        for page in extract_pages(str(pdf_path)):
            items = [
                (
                    float(element.x0),
                    float(element.y0),
                    element.get_text().strip(),
                )
                for element in page
                if isinstance(element, LTTextContainer)
                and element.get_text().strip()
            ]
            for x0, y0, label in items:
                if not label.endswith(":"):
                    continue
                candidates = [
                    (candidate_x, value)
                    for candidate_x, candidate_y, value in items
                    if candidate_x > x0 + 20 and abs(candidate_y - y0) <= 2.5
                ]
                if candidates:
                    fields.append(
                        (label[:-1], min(candidates, key=lambda item: item[0])[1])
                    )
        return fields
    except Exception:
        return []


def _private_case_fields(
    pipeline_root: Optional[Path],
    case_id: Optional[str],
) -> Dict[str, Any]:
    if pipeline_root is None or case_id is None:
        return {}
    root = Path(pipeline_root)
    candidates = list(root.rglob("ground_truth.json")) if root.is_dir() else []
    if root.name == "pdfs":
        candidates.append(root.parent / "ground_truth.json")
    for path in dict.fromkeys(candidates):
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            continue
        if not isinstance(records, list):
            continue
        for record in records:
            if (
                isinstance(record, dict)
                and record.get("opaque_case_id") == case_id
                and isinstance(record.get("fields"), dict)
            ):
                return record["fields"]
    return {}


def _nonplural_person_sequence_value(label: str, value: Any) -> Optional[str]:
    """Join one person's list-valued name components before recursive traversal."""
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and bool(value)
        and all(isinstance(item, str) for item in value)
        and _has_explicit_private_person_semantics(label)
        and not _has_plural_private_person_token_semantics(_label_tokens(label))
    ):
        return " ".join(value)
    return None


def _collect_structured_pii(
    values: Dict[str, set[str]],
    fields: Any,
    *,
    name_component_groups: Optional[set[tuple[str, ...]]] = None,
    prefix: str = "",
    field_label: str = "",
    source_kind: str = _PRIVATE_FIXTURE_SOURCE,
    ancestry_scope: _AncestryScope = _AncestryScope.NEUTRAL,
) -> None:
    direct_label = field_label or prefix
    if isinstance(fields, (str, int, float)) and not isinstance(fields, bool):
        raw_value = str(fields)
        category = _pii_category_for_label(
            direct_label,
            raw_value,
            source_kind=source_kind,
            ancestry_scope=ancestry_scope,
        )
        if category is not None:
            if category == "name":
                _add_structured_person_pii_value(
                    values,
                    direct_label,
                    raw_value,
                    name_component_groups=name_component_groups,
                )
            else:
                _add_pii_value(
                    values,
                    category,
                    raw_value,
                    name_component_groups=name_component_groups,
                )
        if isinstance(fields, str):
            _collect_text_pii(
                values,
                fields,
                name_component_groups=name_component_groups,
                context_label=direct_label,
                source_kind=source_kind,
                ancestry_scope=ancestry_scope,
            )
        return
    if isinstance(fields, Sequence) and not isinstance(
        fields, (str, bytes, bytearray)
    ):
        combined_person_value = _nonplural_person_sequence_value(
            direct_label,
            fields,
        )
        if combined_person_value is not None:
            _collect_structured_pii(
                values,
                combined_person_value,
                name_component_groups=name_component_groups,
                prefix=prefix,
                field_label=direct_label,
                source_kind=source_kind,
                ancestry_scope=ancestry_scope,
            )
            return
        if (
            len(fields) == 2
            and isinstance(fields[0], str)
            and ":" not in fields[0]
            and "\n" not in fields[0]
        ):
            pair_scope = _child_ancestry_scope(ancestry_scope, fields[0])
            pair_category = _pii_category_for_label(
                fields[0],
                str(fields[1]),
                source_kind=source_kind,
                ancestry_scope=pair_scope,
            )
            if pair_scope is not ancestry_scope or pair_category is not None:
                _collect_structured_pii(
                    values,
                    fields[1],
                    name_component_groups=name_component_groups,
                    prefix=prefix,
                    field_label=fields[0],
                    source_kind=source_kind,
                    ancestry_scope=pair_scope,
                )
                return
        for index, item in enumerate(fields):
            _collect_structured_pii(
                values,
                item,
                name_component_groups=name_component_groups,
                prefix=f"{prefix} [{index}]".strip(),
                field_label=direct_label,
                source_kind=source_kind,
                ancestry_scope=ancestry_scope,
            )
        return
    if not isinstance(fields, Mapping):
        return

    pair_label = next(
        (
            fields[key]
            for key in ("label", "field", "field_name", "key")
            if isinstance(fields.get(key), str)
        ),
        None,
    )
    pair_value_key = next(
        (key for key in ("value", "field_value") if key in fields),
        None,
    )
    if pair_label is not None and pair_value_key is not None:
        pair_scope = _child_ancestry_scope(ancestry_scope, pair_label)
        _collect_structured_pii(
            values,
            fields[pair_value_key],
            name_component_groups=name_component_groups,
            prefix=prefix,
            field_label=pair_label,
            source_kind=source_kind,
            ancestry_scope=pair_scope,
        )

    name_parts: Dict[str, Dict[str, str]] = {}
    for key, value in fields.items():
        if not isinstance(key, str):
            continue
        if pair_label is not None and key in {
            "label",
            "field",
            "field_name",
            "key",
            pair_value_key,
        }:
            continue
        canonical_value = (
            _nonplural_person_sequence_value(key, value)
            if not isinstance(value, str)
            else None
        )
        label = f"{prefix} {key}".strip()
        key_tokens = _label_tokens(key)
        child_scope = _child_ancestry_scope(ancestry_scope, key)
        _collect_structured_pii(
            values,
            value,
            name_component_groups=name_component_groups,
            prefix=label,
            field_label=key,
            source_kind=source_kind,
            ancestry_scope=child_scope,
        )
        sibling_value = canonical_value if canonical_value is not None else value
        if not isinstance(sibling_value, str):
            continue
        for suffix, part in (
            (("given", "names"), "given"),
            (("given", "name"), "given"),
            (("family", "name"), "family"),
        ):
            if key_tokens[-len(suffix) :] == suffix:
                stem = " ".join(key_tokens[: -len(suffix)])
                name_parts.setdefault(stem, {})[part] = sibling_value
    for parts in name_parts.values():
        if "given" in parts and "family" in parts:
            _add_pii_value(
                values,
                "name",
                f"{parts['given']} {parts['family']}",
                name_component_groups=name_component_groups,
            )


def _build_parent_pii_manifest(
    *,
    pdf_path: Optional[Path],
    extracted_text: str = "",
    pipeline_root: Optional[Path] = None,
    case_id: Optional[str] = None,
) -> ParentPiiManifest:
    """Build a source-aware PII manifest that never crosses the Worker boundary."""
    values: Dict[str, set[str]] = {
        category: set() for category in _PII_CATEGORIES
    }
    name_component_groups: set[tuple[str, ...]] = set()
    _collect_text_pii(
        values,
        extracted_text,
        name_component_groups=name_component_groups,
        source_kind=_PRIVATE_EXTRACTION_SOURCE,
    )
    if pdf_path is not None and Path(pdf_path).is_file():
        path = Path(pdf_path)
        try:
            from crawler.eval.real_worker import extract_document_text

            _collect_text_pii(
                values,
                extract_document_text(path),
                name_component_groups=name_component_groups,
                source_kind=_PRIVATE_PDF_SOURCE,
            )
        except Exception:
            pass
        layout_fields = dict(_pdf_labelled_fields(path))
        _collect_structured_pii(
            values,
            layout_fields,
            name_component_groups=name_component_groups,
            source_kind=_PRIVATE_PDF_SOURCE,
        )
    _collect_structured_pii(
        values,
        _private_case_fields(pipeline_root, case_id),
        name_component_groups=name_component_groups,
        source_kind=_PRIVATE_FIXTURE_SOURCE,
    )
    for sentinel in _PII_SENTINELS:
        category = "identifier" if any(char.isdigit() for char in sentinel) else "name"
        _add_pii_value(
            values,
            category,
            sentinel,
            name_component_groups=name_component_groups,
        )
    frozen_values = {
        category: tuple(sorted(category_values))
        for category, category_values in values.items()
    }
    frozen_component_groups = tuple(sorted(name_component_groups))
    manifest_hash = _canonical_json_hash(
        {
            "schema": "parent-pii-manifest-v2",
            "values": frozen_values,
            "name_component_groups": frozen_component_groups,
        }
    )
    return ParentPiiManifest(
        values=frozen_values,
        name_component_groups=frozen_component_groups,
        manifest_hash=manifest_hash,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


_WORKER_PROVENANCE_EXTRA_FIELDS = (
        "input_pdf_sha256",
        "allowed_text_sha256",
        "bundle_hash",
        "answer_hash",
        "pii_manifest_hash",
        "pii_manifest_count",
        "pii_manifest_categories",
)


def _worker_provenance_digest(provenance: Dict[str, Any]) -> str:
    return canonical_provenance_digest(
        provenance,
        extra_fields=_WORKER_PROVENANCE_EXTRA_FIELDS,
    )


def _parse_copilot_jsonl_output(stdout_text: str) -> Dict[str, Any]:
    """Extract exactly one strict raw AnswerObject from an injected JSONL event stream."""
    cleaned = _ANSI_ESCAPE.sub("", stdout_text).strip()
    candidates = []

    for line in cleaned.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        try:
            evt = json.loads(line_str)
            if not isinstance(evt, dict):
                continue
            evt_type = evt.get("type") or evt.get("event")
            # Ignore reasoning, tool, session events
            if evt_type in (
                "assistant.reasoning",
                "tool.execution_start",
                "tool.execution_complete",
                "tool.execution_partial_result",
                "session.mcp_servers_loaded",
                "session.skills_loaded",
                "session.tools_updated",
                "session.background_tasks_changed",
            ):
                continue

            content = None
            if evt_type == "assistant.message":
                data = evt.get("data")
                if isinstance(data, dict):
                    content = data.get("content")
                elif "content" in evt:
                    content = evt.get("content")
            elif evt_type == "result":
                content = evt.get("content") or evt.get("result")

            if content and isinstance(content, str):
                candidates.append(content)
        except json.JSONDecodeError as exc:
            raise CopilotExecutionError("Malformed Copilot JSONL event") from exc

    if len(candidates) != 1:
        raise CopilotExecutionError(
            "Worker response must contain exactly one final assistant JSON object"
        )
    return _parse_worker_response(candidates[0])


def _parse_worker_response(raw_content: str) -> Dict[str, Any]:
    """Parse one raw JSON object with exactly the canonical AnswerObject fields."""
    def _reject_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> Dict[str, Any]:
        parsed: Dict[str, Any] = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError(f"Duplicate JSON key: {key}")
            parsed[key] = value
        return parsed

    def _reject_non_finite(value: str) -> None:
        raise ValueError(f"Non-finite JSON value: {value}")

    try:
        parsed = json.loads(
            raw_content.strip(),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise CopilotExecutionError(
            "Final Copilot response was not one strict raw JSON object"
        ) from exc
    if not isinstance(parsed, dict) or set(parsed) != _ANSWER_FIELDS:
        raise CopilotExecutionError(
            "Worker response must contain exactly the canonical AnswerObject fields"
        )
    return parsed


def build_worker_response_validation_policy(
    *,
    corpus_db_path: Path,
    public_bundle: Dict[str, Any],
) -> ResponseValidationPolicy:
    """Build a generic structure + local-grounding correction policy."""
    corpus_db = Path(corpus_db_path).resolve(strict=True)
    bundle_content = public_bundle.get("content")
    if not isinstance(bundle_content, str):
        raise ValueError("Worker validation policy requires public bundle content")
    allowed_citations = frozenset(
        citation
        for citation in re.findall(
            r"(?m)^### Chunk: ([^\s]+)\s*$",
            bundle_content,
        )
        if (
            _PUBLIC_CITATION_ID.fullmatch(citation)
            and ".." not in citation
            and searchindex.resolve(corpus_db, citation) is not None
        )
    )

    def validate(content: str) -> ResponseValidationIssue | None:
        try:
            answer = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return ResponseValidationIssue(("invalid JSON object",))
        errors: list[str] = []
        if not isinstance(answer, dict):
            return ResponseValidationIssue(("top-level must be an object",))
        if set(answer) != _ANSWER_FIELDS:
            errors.append("top-level fields must be exact")
        if not isinstance(answer.get("question"), str):
            errors.append("question must be a string")
        if not isinstance(answer.get("prose"), str):
            errors.append("prose must be a string")

        claims = answer.get("claims")
        if not isinstance(claims, list):
            errors.append("claims must be an array")
        else:
            for index, claim in enumerate(claims):
                if not isinstance(claim, dict):
                    errors.append(f"claims[{index}] must be an object")
                    continue
                if set(claim) != _CLAIM_FIELDS:
                    errors.append(
                        f"claims[{index}] fields must be exact"
                    )
                if not isinstance(claim.get("id"), str):
                    errors.append(f"claims[{index}].id must be a string")
                if not isinstance(claim.get("text"), str):
                    errors.append(
                        f"claims[{index}].text must be a string"
                    )
                citations = claim.get("citations")
                if not isinstance(citations, list) or not all(
                    isinstance(value, str) for value in citations
                ):
                    errors.append(
                        f"claims[{index}].citations must be an array of strings"
                    )
                if not isinstance(claim.get("quote"), str):
                    errors.append(
                        f"claims[{index}].quote must be a string"
                    )

        basis = answer.get("basis")
        if not isinstance(basis, list):
            errors.append("basis must be an array")
        else:
            for index, value in enumerate(basis):
                if not isinstance(value, str):
                    errors.append(
                        f"basis[{index}] must be a string"
                    )

        abstentions = answer.get("abstentions")
        if not isinstance(abstentions, list):
            errors.append("abstentions must be an array")
        else:
            for index, abstention in enumerate(abstentions):
                if not isinstance(abstention, dict):
                    errors.append(
                        f"abstentions[{index}] must be an object"
                    )
                    continue
                if set(abstention) != _ABSTENTION_FIELDS:
                    errors.append(
                        f"abstentions[{index}] fields must be exact"
                    )
                if not isinstance(abstention.get("text"), str):
                    errors.append(
                        f"abstentions[{index}].text must be a string"
                    )
                reason = abstention.get("reason")
                if (
                    not isinstance(reason, str)
                    or reason not in _ABSTENTION_REASONS
                ):
                    errors.append(
                        f"abstentions[{index}].reason must be not_in_corpus"
                    )
        if isinstance(claims, list):
            for claim_index, claim in enumerate(claims):
                if (
                    not isinstance(claim, dict)
                    or set(claim) != _CLAIM_FIELDS
                    or not isinstance(claim.get("id"), str)
                    or not isinstance(claim.get("text"), str)
                    or not isinstance(claim.get("quote"), str)
                    or not isinstance(claim.get("citations"), list)
                    or not all(
                        isinstance(value, str)
                        for value in claim["citations"]
                    )
                ):
                    continue
                reasons = check_claim(corpus_db, claim)
                public_citations = [
                    citation
                    for citation in claim["citations"]
                    if citation in allowed_citations
                ]
                for reason in reasons:
                    if reason not in {
                        "uncited",
                        "unresolvable",
                        "quote_not_in_chunk",
                    }:
                        continue
                    detail = (
                        "grounding "
                        f"claim_index=claims[{claim_index}] "
                        f"category={reason}"
                    )
                    if public_citations:
                        detail += (
                            " citations="
                            + json.dumps(
                                public_citations,
                                ensure_ascii=True,
                                separators=(",", ":"),
                            )
                        )
                    errors.append(detail)
        return ResponseValidationIssue(tuple(errors)) if errors else None

    def build_prompt(issue: ResponseValidationIssue) -> str:
        summary = "; ".join(issue.codes)
        return (
            "The previous JSON failed AnswerObject structure and/or grounding "
            "validation: "
            f"{summary}. Return the same review again as one raw strict JSON "
            "object conforming exactly to this generic schema: top-level "
            "{question:string, claims:array, basis:array[string], "
            "abstentions:array, prose:string}; every claims item is exactly "
            "{id:string, text:string, citations:array[string], quote:string}; "
            "every abstentions item is exactly {text:string, "
            "reason:not_in_corpus}. Independently re-check the existing public "
            "review bundle. Every retained claim must use its existing public "
            "chunk ID and an exact verbatim quote, or independently abstain "
            "and remove an unsupported claim as required by the canonical "
            "contract. Do not use any new evidence. The first character must "
            "be { and the last character }. Do not use a fence, preface, "
            "explanation, or trailing prose."
        )

    return ResponseValidationPolicy(
        correction_kind="worker_validation",
        validate=validate,
        build_correction_prompt=build_prompt,
    )


def _iter_string_leaves(
    value: Any,
    *,
    _active_containers: Optional[set[int]] = None,
):
    """Yield raw string keys and values without serializing recursive JSON data."""
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, (bytes, bytearray)):
        return
    if not isinstance(value, (Mapping, Sequence)):
        return

    active_containers = (
        _active_containers if _active_containers is not None else set()
    )
    container_id = id(value)
    if container_id in active_containers:
        return
    active_containers.add(container_id)
    try:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if isinstance(key, str):
                    yield key
                yield from _iter_string_leaves(
                    child,
                    _active_containers=active_containers,
                )
        else:
            for child in value:
                yield from _iter_string_leaves(
                    child,
                    _active_containers=active_containers,
                )
    finally:
        active_containers.remove(container_id)


def _iter_public_answer_strings(answer: Mapping[str, Any]):
    """Yield actual public AnswerObject strings, excluding basis and provenance."""
    for field in ("question", "claims", "abstentions", "prose"):
        if field in answer:
            yield from _iter_string_leaves(answer[field])


def _assert_answer_blindness_and_pii(
    answer: Dict[str, Any],
    *,
    pii_manifest: Optional[ParentPiiManifest] = None,
) -> None:
    """Keep public AnswerObject fields free of privileged data and applicant PII."""
    public_strings = tuple(_iter_public_answer_strings(answer))
    for public_value in public_strings:
        public_leaks = find_public_content_leaks(public_value)
        if public_leaks:
            raise ValueError(
                "AnswerObject contains privileged contamination: "
                + ", ".join(public_leaks)
            )
        if _SIN_REGEX.search(public_value):
            raise ValueError(
                "AnswerObject public fields contain a SIN-like identifier"
            )
        if _EMAIL_REGEX.search(public_value):
            raise ValueError("AnswerObject public fields contain an email address")

    manifest = pii_manifest or _build_parent_pii_manifest(pdf_path=None)
    for public_value in public_strings:
        public_tokens = _normalized_lexical_tokens(public_value)
        public_casefold = unicodedata.normalize("NFKC", public_value).casefold()
        public_date_tokens = _public_date_tokens(public_value, public_tokens)
        for category, normalized_values in manifest.values.items():
            for normalized_value in normalized_values:
                if category == "email":
                    matched = (
                        normalized_value in public_casefold
                        or _compact_token_window_matches(
                            public_tokens,
                            normalized_value,
                        )
                    )
                elif category == "date":
                    matched = normalized_value in public_date_tokens
                else:
                    matched = _compact_token_window_matches(
                        public_tokens,
                        normalized_value,
                    )
                if matched:
                    raise ValueError(
                        "AnswerObject public fields contain applicant PII "
                        f"(category: {category})"
                    )
        if _public_name_component_match(
            public_value,
            public_tokens,
            manifest.name_component_groups,
        ):
            raise ValueError(
                "AnswerObject public fields contain applicant PII "
                "(category: name)"
            )


def _build_worker_prompt(
    *,
    doc_type: str,
    public_bundle: Dict[str, Any],
    extracted_text: str = "",
) -> str:
    """Build the deterministic Worker prompt bound into runtime provenance."""
    safe_bundle_content = public_bundle["content"].replace(
        "</public_review_bundle>", "&lt;/public_review_bundle&gt;"
    )
    safe_extracted_text = extracted_text.replace(
        "</extracted_text>", "&lt;/extracted_text&gt;"
    )
    text_section = (
        f"\n<extracted_text>\n{safe_extracted_text}\n</extracted_text>\n"
        if safe_extracted_text
        else ""
    )
    return f"""    You are the live LLM Worker for a blind Canadian Express Entry document review.

    DOCUMENT UPLOAD-SLOT TYPE: {doc_type}

    <public_review_bundle>
    {safe_bundle_content}
    </public_review_bundle>
    {text_section}
    INSTRUCTIONS:
    Evaluate ONLY the attached PDF document.
You have NO access to ground-truth specifications, research reports, or injected defect labels.
Keep applicant-specific facts in basis[]; question, claims, quotes, abstentions, and prose must remain PII-free.
Never invent a citation or quote. If authoritative corpus evidence is missing, abstain with zero claims.

Return ONLY one valid JSON AnswerObject with canonical fields: question, claims, basis, abstentions, prose.
Do not use Markdown code fences or commentary outside the JSON object.
"""


def build_worker_input_manifest(
    *,
    doc_type: str,
    public_bundle: Dict[str, Any],
    input_pdf_sha256: str,
    extracted_text: str = "",
    allowed_text_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the exact non-privileged input the parent supplied to one Worker."""
    content = public_bundle.get("content")
    bundle_hash = public_bundle.get("bundle_hash")
    if (
        public_bundle.get("doc_type") != doc_type
        or not isinstance(content, str)
        or not isinstance(bundle_hash, str)
        or bundle_hash != hashlib.sha256(content.encode("utf-8")).hexdigest()
        or not re.fullmatch(r"[a-f0-9]{64}", input_pdf_sha256)
        or not isinstance(extracted_text, str)
        or (
            allowed_text_sha256 is not None
            and not re.fullmatch(r"[a-f0-9]{64}", allowed_text_sha256)
        )
    ):
        raise ValueError("Worker input manifest requires an exact public bundle")
    prompt = _build_worker_prompt(
        doc_type=doc_type,
        public_bundle=public_bundle,
        extracted_text=extracted_text,
    )
    return {
        "schema_version": "worker-input-manifest-v1",
        "doc_type": doc_type,
        "public_bundle_content": content,
        "public_bundle_hash": bundle_hash,
        "worker_prompt": prompt,
        "worker_prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "input_pdf_sha256": input_pdf_sha256,
        "attachment_display_name": "document.pdf",
        "allowed_extracted_text": extracted_text,
        "allowed_text_sha256": (
            allowed_text_sha256
            if allowed_text_sha256 is not None
            else (
                hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()
                if extracted_text
                else None
            )
        ),
        "model_config": {
            "role": "worker",
            "model": _WORKER_MODEL,
            "effort": None,
            "context_tier": _CONTEXT_TIER,
            "timeout_seconds": _LLM_TIMEOUT_SECONDS,
        },
    }


async def run_blind_worker_task_async(
    opaque_case_id: str,
    doc_type: str,
    public_bundle: Optional[Dict[str, Any]] = None,
    runner_fn: Optional[Any] = None,
    pipeline_root: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    corpus_db_path: Optional[Path] = None,
    runtime: Optional[AgentRuntime] = None,
    descendant_registrar: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Execute Gemini 3.6 Flash blind worker review in an isolated staging CWD."""
    staging_cwd = None
    try:
        # 1. Stage outside both the privileged pipeline and the globally readable system temp.
        _WORKER_STAGE_ROOT.mkdir(parents=True, exist_ok=True)
        stage_target = Path(tempfile.mkdtemp(dir=_WORKER_STAGE_ROOT))
        staged_pdf = stage_case_for_worker(
            opaque_case_id,
            pipeline_root=pipeline_root,
            target_dir=stage_target,
        )
        staging_cwd = staged_pdf.parent

        # Keep deterministic case identity in the parent only. The Worker sees
        # neutral filenames; case IDs and source paths are not model inputs.
        staged_txt = staging_cwd / f"{opaque_case_id}.txt"
        neutral_pdf = staging_cwd / "document.pdf"
        neutral_txt = staging_cwd / "document.txt"
        staged_pdf.replace(neutral_pdf)
        staged_pdf = neutral_pdf
        if staged_txt.is_file():
            staged_txt.replace(neutral_txt)

        # Compute SHA-256 hashes of input files for parent-side provenance.
        pdf_bytes = staged_pdf.read_bytes()
        input_pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

        extracted_text = ""
        allowed_text_sha256 = None
        if neutral_txt.is_file():
            txt_bytes = neutral_txt.read_bytes()
            extracted_text = txt_bytes.decode("utf-8", errors="replace")
            allowed_text_sha256 = hashlib.sha256(txt_bytes).hexdigest()
        pii_manifest = _build_parent_pii_manifest(
            pdf_path=staged_pdf,
            extracted_text=extracted_text,
            pipeline_root=pipeline_root,
            case_id=opaque_case_id,
        )

        # 2. Build or accept public review bundle
        if public_bundle is None:
            public_bundle = build_public_review_bundle(doc_type, corpus_db_path=corpus_db_path)

        # 3. Construct prompt
        prompt = _build_worker_prompt(
            doc_type=doc_type,
            public_bundle=public_bundle,
            extracted_text=extracted_text,
        )

        max_attempts = 3 if runner_fn is None else 1
        last_error = None
        answer = {}
        prov_dict = {}

        for attempt in range(1, max_attempts + 1):
            try:
                if runner_fn is not None:
                    # Injected test runner path (compatibility wrapper)
                    staged_pdf_name = staged_pdf.name
                    cmd = [
                        "copilot",
                        "-p", prompt,
                        "--attachment", staged_pdf_name,
                        "--model", _WORKER_MODEL,
                        "--context", _CONTEXT_TIER,
                        "--output-format", "json",
                        "--stream", "off",
                        "--no-custom-instructions",
                        "--no-ask-user",
                        "--disable-builtin-mcps",
                        "--disallow-temp-dir",
                        "--excluded-tools=*",
                    ]
                    stdout_text = runner_fn(cmd, staging_cwd)
                    answer = _parse_copilot_jsonl_output(stdout_text)
                    _validate_answer_object(answer)
                    check_answer_grounding(answer, db_path=corpus_db_path)
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=pii_manifest,
                    )

                    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                    output_hash = _canonical_json_hash(answer)
                    completed_at = _utc_now()

                    prov_dict = {
                        "engine": "injected-test-runner",
                        "is_live": False,
                        "sdk_version": "injected-test-runner",
                        "runtime_protocol_version": "injected-test-protocol",
                        "role": "worker",
                        "model": _WORKER_MODEL,
                        "effort": None,
                        "context_tier": _CONTEXT_TIER,
                        "session_id": f"injected-worker-{opaque_case_id}",
                        "input_pdf_sha256": input_pdf_sha256,
                        "attachment_hashes": [input_pdf_sha256],
                        "allowed_text_sha256": allowed_text_sha256,
                        "bundle_hash": public_bundle["bundle_hash"],
                        "prompt_hash": prompt_hash,
                        "output_hash": output_hash,
                        "answer_hash": _canonical_json_hash(answer),
                        "pii_manifest_hash": pii_manifest.manifest_hash,
                        "pii_manifest_count": pii_manifest.count,
                        "pii_manifest_categories": (
                            pii_manifest.category_summary
                        ),
                        "terminal_event": "assistant.message",
                        "started_at": completed_at,
                        "completed_at": completed_at,
                        "duration_seconds": 0.0,
                        "retry_classification": None,
                        "turn_count": 1,
                        "format_correction_count": 0,
                        "initial_prompt_hash": prompt_hash,
                        "correction_prompt_hashes": [],
                        "assistant_response_hash_chain": [output_hash],
                        "turn_session_ids": [f"injected-worker-{opaque_case_id}"],
                    }
                    prov_dict["provenance_digest"] = _worker_provenance_digest(
                        prov_dict
                    )
                    break

                else:
                    # SDK runtime path
                    active_runtime = runtime or CopilotSdkRuntime(
                        base_directory=staging_cwd,
                        descendant_registrar=descendant_registrar,
                    )
                    request = AgentRequest(
                        role="worker",
                        model=_WORKER_MODEL,
                        context_tier=_CONTEXT_TIER,
                        prompt=prompt,
                        attachments=[
                            BlobAttachment(
                                data=pdf_bytes,
                                mime_type="application/pdf",
                                display_name=staged_pdf.name,
                            )
                        ],
                        timeout_seconds=_LLM_TIMEOUT_SECONDS,
                        response_validation_policy=(
                            build_worker_response_validation_policy(
                                corpus_db_path=Path(
                                    corpus_db_path or _REPO_ROOT / "corpus" / "index.db"
                                ),
                                public_bundle=public_bundle,
                            )
                        ),
                    )
                    agent_result = await active_runtime.run(request)
                    is_injected_runtime = runtime is not None
                    prov = validate_agent_result(
                        agent_result,
                        request,
                        expected_engine=(
                            "injected-test-runner"
                            if is_injected_runtime
                            else "copilot-sdk"
                        ),
                        expected_is_live=not is_injected_runtime,
                    )
                    answer = _parse_worker_response(agent_result.content)

                    _validate_answer_object(answer)
                    check_answer_grounding(answer, db_path=corpus_db_path)
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=pii_manifest,
                    )

                    prov_dict = {
                        "engine": prov.engine,
                        "is_live": prov.is_live,
                        "sdk_version": prov.sdk_version,
                        "runtime_protocol_version": prov.runtime_protocol_version,
                        "role": "worker",
                        "model": _WORKER_MODEL,
                        "effort": None,
                        "context_tier": _CONTEXT_TIER,
                        "session_id": prov.session_id,
                        "input_pdf_sha256": input_pdf_sha256,
                        "attachment_hashes": list(prov.attachment_hashes),
                        "allowed_text_sha256": allowed_text_sha256,
                        "bundle_hash": public_bundle["bundle_hash"],
                        "prompt_hash": prov.prompt_hash,
                        "output_hash": prov.output_hash,
                        "answer_hash": _canonical_json_hash(answer),
                        "pii_manifest_hash": pii_manifest.manifest_hash,
                        "pii_manifest_count": pii_manifest.count,
                        "pii_manifest_categories": (
                            pii_manifest.category_summary
                        ),
                        "terminal_event": prov.terminal_event,
                        "started_at": prov.started_at,
                        "completed_at": prov.completed_at,
                        "duration_seconds": prov.duration_seconds,
                        "retry_classification": prov.retry_classification,
                        "turn_count": prov.turn_count,
                        "format_correction_count": prov.format_correction_count,
                        "initial_prompt_hash": prov.initial_prompt_hash,
                        "correction_prompt_hashes": list(
                            prov.correction_prompt_hashes
                        ),
                        "assistant_response_hash_chain": list(
                            prov.assistant_response_hash_chain
                        ),
                        "turn_session_ids": list(prov.turn_session_ids),
                    }
                    if prov.correction_kind is not None:
                        prov_dict["correction_kind"] = prov.correction_kind
                    prov_dict["provenance_digest"] = _worker_provenance_digest(
                        prov_dict
                    )
                    break

            except AgentTimeoutError:
                raise
            except TransientAgentError as exc:
                last_error = exc
                if attempt < max_attempts:
                    logger.warning(
                        "Worker task attempt %d/%d failed for case %s in %s: %s. Retrying...",
                        attempt,
                        max_attempts,
                        opaque_case_id,
                        doc_type,
                        exc,
                    )
                    await asyncio.sleep(2 * attempt)
                else:
                    raise last_error
            except Exception as exc:
                # Deterministic failure (JSON decode, grounding, PII, blindness, schema error)
                # Do NOT retry! Immediately raise.
                raise

        answer["case_id"] = opaque_case_id
        answer["doc_type"] = doc_type
        answer["_provenance"] = prov_dict

        # Save output report if explicit output_dir is provided
        if output_dir is not None:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            _write_json(out_dir / f"{opaque_case_id}.json", answer)

        return answer

    except Exception:
        # Delete stale/partial report on failure
        if output_dir is not None:
            stale_report = Path(output_dir) / f"{opaque_case_id}.json"
            stale_report.unlink(missing_ok=True)
        raise
    finally:
        # Always clean up temporary stage directory
        if staging_cwd is not None and staging_cwd.exists():
            shutil.rmtree(staging_cwd, ignore_errors=True)


def run_blind_worker_task(
    opaque_case_id: str,
    doc_type: str,
    public_bundle: Optional[Dict[str, Any]] = None,
    runner_fn: Optional[Any] = None,
    pipeline_root: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    corpus_db_path: Optional[Path] = None,
    runtime: Optional[AgentRuntime] = None,
    descendant_registrar: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
    """Execute Gemini 3.6 Flash blind worker review in an isolated staging CWD."""
    return run_async(
        run_blind_worker_task_async(
            opaque_case_id=opaque_case_id,
            doc_type=doc_type,
            public_bundle=public_bundle,
            runner_fn=runner_fn,
            pipeline_root=pipeline_root,
            output_dir=output_dir,
            corpus_db_path=corpus_db_path,
            runtime=runtime,
            descendant_registrar=descendant_registrar,
        ),
        async_api_name="run_blind_worker_task_async(...)",
    )


def run_pipeline_worker_review(
    doc_type: str,
    case_id: str,
    pdf_path: Optional[Path] = None,
    runner_fn: Optional[Any] = None,
    output_dir: Optional[Path] = None,
    corpus_db_path: Optional[Path] = None,
    runtime: Optional[AgentRuntime] = None,
) -> Dict[str, Any]:
    """Execute blind worker review for a case ID using run_blind_worker_task."""
    return run_blind_worker_task(
        opaque_case_id=case_id,
        doc_type=doc_type,
        runner_fn=runner_fn,
        output_dir=output_dir,
        corpus_db_path=corpus_db_path,
        runtime=runtime,
    )


def run_pipeline_worker_for_doctype(
    doc_type: str,
    runner_fn: Optional[Any] = None,
    output_dir: Optional[Path] = None,
    runtime: Optional[AgentRuntime] = None,
) -> Dict[str, Dict[str, Any]]:
    """Run worker reviews for all blind test cases in a document type pipeline."""
    pipeline_dir = _PIPELINES_DIR / doc_type
    pdfs_dir = pipeline_dir / "ground_truth" / "pdfs"

    if not pdfs_dir.exists():
        logger.warning("No ground_truth/pdfs directory found for pipeline %s", doc_type)
        return {}

    pdf_files = sorted(pdfs_dir.glob("*.pdf"))
    results = {}

    for pdf_file in pdf_files:
        case_id = pdf_file.stem
        results[case_id] = run_pipeline_worker_review(
            doc_type,
            case_id,
            pdf_path=pdf_file,
            runner_fn=runner_fn,
            output_dir=output_dir,
            runtime=runtime,
        )

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    dt = sys.argv[1] if len(sys.argv) > 1 else "passport"
    run_pipeline_worker_for_doctype(dt)
