"""Public Review Evidence Bundle Builder for Blind Worker Execution (Phase 74 D-06, D-07).

Assembles immutable, PII-free, research-free public review bundles for each document type
from canonical skills in skills/document-agents/ and exact local corpus quotes.
Records SHA-256 bundle hashes in Worker execution provenance.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / "skills" / "document-agents"
_SHARED_PDF_SKILL = _REPO_ROOT / "skills" / "pdf" / "SKILL.md"
_CORPUS_DB = _REPO_ROOT / "corpus" / "index.db"

# Map pipeline doc_types (underscores or hyphens) to skill file stems
DOC_TYPE_TO_SKILL: Dict[str, str] = {
    "passport": "passport",
    "language_test": "language-test",
    "language-test": "language-test",
    "educational_credential_assessment": "eca",
    "eca": "eca",
    "employment_reference_letter": "employment-reference-letter",
    "employment-reference-letter": "employment-reference-letter",
    "proof_of_funds": "proof-of-funds",
    "proof-of-funds": "proof-of-funds",
    "medical_examination": "medical",
    "medical": "medical",
    "police_certificate": "police-certificate",
    "police-certificate": "police-certificate",
    "digital_photo": "digital-photos",
    "digital-photos": "digital-photos",
    "certified_translation": "translation",
    "translation": "translation",
    "written_job_offer_lmia": "job-offer",
    "job-offer": "job-offer",
    "proof_of_studies": "proof-of-studies",
    "proof-of-studies": "proof-of-studies",
    "certificate_of_qualification": "certificate-of-qualification",
    "certificate-of-qualification": "certificate-of-qualification",
    "birth_certificate": "birth-certificate",
    "birth-certificate": "birth-certificate",
    "marriage_certificate": "marriage-certificate",
    "marriage-certificate": "marriage-certificate",
    "statutory_declaration_common_law": "common-law-union",
    "common-law-union": "common-law-union",
    "divorce_certificate": "divorce-certificate",
    "divorce-certificate": "divorce-certificate",
    "death_certificate": "death-certificate",
    "death-certificate": "death-certificate",
    "adoption_certificate": "adoption-certificate",
    "adoption-certificate": "adoption-certificate",
    "use_of_representative": "use-of-representative",
    "use-of-representative": "use-of-representative",
    "relative_in_canada": "relative-in-canada",
    "relative-in-canada": "relative-in-canada",
    "proof_of_other_name": "other-name",
    "other-name": "other-name",
    "authority_to_release_info": "authority-to-release",
    "authority-to-release": "authority-to-release",
    "letter_of_explanation": "letter-of-explanation",
    "letter-of-explanation": "letter-of-explanation",
}

FORBIDDEN_PRIVILEGED_KEYWORDS = [
    "research.json",
    "ground_truth",
    "ground truth",
    "generation_spec",
    "generation spec",
    "case_001",
    "case_002",
    "expected_verdict",
    "expected verdict",
    "defect_type",
    "injected_defect",
    "injected defect",
    "synthetic_defect",
    "synthetic defect",
    "worker_reports",
    "worker_outputs",
    "test_data",
    "defect_selection",
    "source_failure_id",
    "research_failure_id",
    "failure_id",
    "affected_fields",
    "defect_spec",
    "mutation_details",
]

_PRIVILEGED_NORMALIZED_PHRASES = {
    "affected fields",
    "agent spec sha256",
    "case kind",
    "court clerk signature present",
    "critical recency failure",
    "critical specification failure",
    "defect selection",
    "defect spec",
    "defect type",
    "expected basis keys",
    "expected claims",
    "expected verdict",
    "failure id",
    "framing and composition failure",
    "generation spec",
    "ground truth",
    "injected defect",
    "lighting and background failure",
    "mutation details",
    "opaque case id",
    "research failure id",
    "research findings",
    "research json",
    "research report",
    "seal present",
    "sibling case id",
    "source failure id",
    "synthetic defect",
    "test data",
    "translation certified false",
    "translation certified true",
    "worker outputs",
    "worker reports",
}
_CAMEL_ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_CAMEL_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_COMBINING_MARK_CATEGORIES = frozenset({"Mn", "Mc", "Me"})
_COMPACT_PRIVILEGED_IDENTIFIER_GRAMMARS = (
    ("privileged failure ID", re.compile(r"pfl"), 3, 3),
    (
        "privileged failure ID",
        re.compile(r"pfl(?:[a-z][a-z0-9]{0,63})?\d{1,4}"),
        4,
        71,
    ),
    ("privileged case ID", re.compile(r"case\d{1,8}"), 5, 12),
    (
        "privileged internal ID",
        re.compile(r"(?:def|val)[sv]\d{1,8}"),
        5,
        12,
    ),
    (
        "opaque case ID",
        re.compile(r"[a-f0-9]{32}"),
        32,
        32,
    ),
)


class PublicBundleValidationError(ValueError):
    """Deterministic candidate/public-bundle content validation failure."""


def _canonical_lexical_tokens(value: str) -> tuple[str, ...]:
    """Return NFKC/camel/delimiter-normalized tokens without losing boundaries."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _CAMEL_ACRONYM_BOUNDARY.sub(" ", normalized)
    normalized = _CAMEL_WORD_BOUNDARY.sub(" ", normalized).casefold()
    return tuple(
        "".join(char if char.isalnum() else " " for char in normalized).split()
    )


def _canonical_identifier_tokens(value: str) -> tuple[str, ...]:
    """Return a mark-insensitive skeleton only for privileged ID grammars."""
    decomposed = unicodedata.normalize("NFKD", value)
    identifier_skeleton = "".join(
        char
        for char in decomposed
        if unicodedata.category(char) not in _COMBINING_MARK_CATEGORIES
    )
    return _canonical_lexical_tokens(identifier_skeleton)


def _canonical_leakage_forms(value: str) -> tuple[str, str]:
    """Return word-delimited and compact NFKC forms for one lexical value."""
    tokens = _canonical_lexical_tokens(value)
    return " ".join(tokens), "".join(tokens)


def _normalize_for_leakage_scan(value: str) -> str:
    return _canonical_leakage_forms(value)[0]


def _contains_privileged_phrase(
    content_tokens: tuple[str, ...],
    phrase: str,
) -> bool:
    """Match a private key as an exact compact form of contiguous lexical tokens."""
    phrase_tokens = _canonical_lexical_tokens(phrase)
    phrase_compact = "".join(phrase_tokens)
    if not phrase_compact:
        return False
    for start in range(len(content_tokens)):
        candidate = ""
        for token in content_tokens[start:]:
            candidate += token
            if candidate == phrase_compact:
                return True
            if len(candidate) >= len(phrase_compact):
                break
    return False


def _contains_compact_grammar_window(
    content_tokens: tuple[str, ...],
    grammar: re.Pattern[str],
    *,
    minimum_length: int,
    maximum_length: int,
) -> bool:
    """Match one exact identifier grammar over bounded contiguous token windows."""
    for start in range(len(content_tokens)):
        candidate = ""
        for token in content_tokens[start:]:
            if len(candidate) + len(token) > maximum_length:
                break
            candidate += token
            if (
                len(candidate) >= minimum_length
                and grammar.fullmatch(candidate) is not None
            ):
                return True
    return False


def find_public_content_leaks(
    content: str,
    *,
    forbidden_private_texts: Iterable[str] = (),
) -> list[str]:
    """Return narrow privileged-leak categories after robust canonicalization."""
    content_tokens = _canonical_lexical_tokens(content)
    identifier_tokens = _canonical_identifier_tokens(content)
    normalized = " ".join(content_tokens)
    padded = f" {normalized} "
    leaks: list[str] = []
    for category, grammar, minimum_length, maximum_length in (
        _COMPACT_PRIVILEGED_IDENTIFIER_GRAMMARS
    ):
        if _contains_compact_grammar_window(
            identifier_tokens,
            grammar,
            minimum_length=minimum_length,
            maximum_length=maximum_length,
        ):
            leaks.append(category)
    for phrase in sorted(_PRIVILEGED_NORMALIZED_PHRASES):
        if _contains_privileged_phrase(content_tokens, phrase):
            leaks.append(f"privileged phrase ({phrase})")
    for private_text in forbidden_private_texts:
        if not isinstance(private_text, str):
            continue
        private_normalized = _normalize_for_leakage_scan(private_text)
        if (
            len(private_normalized) >= 48
            and len(private_normalized.split()) >= 7
            and f" {private_normalized} " in padded
        ):
            leaks.append("copied private recommendation text")
            break
    return list(dict.fromkeys(leaks))


def resolve_skill_path(doc_type: str, skills_dir: Optional[Path] = None) -> Path:
    """Resolve the canonical skill markdown path for a given doc_type."""
    raw_dir = Path(skills_dir or _SKILLS_DIR)
    if raw_dir.is_symlink():
        raise OSError(f"Document skills directory is a symlink: {raw_dir}")
    dir_path = raw_dir.resolve()
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Document skills directory not found: {raw_dir}")
    stem = DOC_TYPE_TO_SKILL.get(doc_type, doc_type.replace("_", "-"))
    raw_skill_file = dir_path / f"{stem}.md"
    if raw_skill_file.is_symlink():
        raise OSError(f"Canonical document skill file is a symlink: {raw_skill_file}")
    if not raw_skill_file.is_file():
        raise FileNotFoundError(
            f"Missing canonical document skill file for '{doc_type}': {raw_skill_file}"
        )
    skill_file = raw_skill_file.resolve(strict=True)
    if skill_file.parent != dir_path:
        raise OSError(
            f"Canonical document skill file escapes its expected directory: {raw_skill_file}"
        )
    return skill_file


def build_public_review_bundle(
    doc_type: str,
    corpus_db_path: Optional[Path] = None,
    skills_dir: Optional[Path] = None,
    override_skill_content: Optional[str] = None,
    override_shared_content: Optional[str] = None,
    shared_skill_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Assemble an immutable public review bundle containing skill rules, shared PDF contract, and verbatim corpus quotes.

    Args:
        doc_type: Document type name (e.g., 'passport', 'birth_certificate').
        corpus_db_path: Optional path to corpus/index.db for fetching verbatim quotes.
        skills_dir: Optional document skills directory override.
        override_skill_content: Optional in-memory candidate document skill content override.
        override_shared_content: Optional in-memory candidate shared PDF skill content override.
        shared_skill_path: Optional shared PDF skill file path override.

    Returns:
        Dict containing doc_type, content, and SHA-256 bundle_hash.

    Raises:
        FileNotFoundError: If skill file is missing.
        ValueError: If generated bundle contains privileged keywords or opaque case IDs.
    """
    skill_path = resolve_skill_path(doc_type, skills_dir=skills_dir)
    if override_skill_content is not None:
        skill_content = override_skill_content.strip()
    else:
        skill_content = skill_path.read_text(encoding="utf-8").strip()

    if override_shared_content is not None:
        shared_content = override_shared_content.strip()
    else:
        raw_shared_path = Path(shared_skill_path or _SHARED_PDF_SKILL)
        if raw_shared_path.is_symlink():
            raise OSError(
                f"Shared PDF review contract file is a symlink: {raw_shared_path}"
            )
        if not raw_shared_path.is_file():
            raise FileNotFoundError(
                f"Missing shared PDF review contract file: {raw_shared_path}"
            )
        s_path = raw_shared_path.resolve(strict=True)
        shared_content = s_path.read_text(encoding="utf-8").strip()

    for source_name, source_content in (
        ("document skill", skill_content),
        ("shared PDF review contract", shared_content),
    ):
        source_leaks = find_public_content_leaks(source_content)
        if source_leaks:
            raise PublicBundleValidationError(
                f"Public {source_name} for '{doc_type}' contains forbidden "
                f"privileged content: {', '.join(source_leaks)}"
            )

    bundle_sections = [
        f"# PUBLIC REVIEW EVIDENCE BUNDLE: {doc_type}",
        f"Skill Reference: {skill_path.name}",
        "",
        "## Document Skill Rules",
        skill_content,
        "",
        "## Shared PDF Review Contract",
        shared_content,
    ]

    raw_db_path = Path(corpus_db_path or _CORPUS_DB)
    if raw_db_path.is_symlink():
        raise OSError(f"Corpus index database is a symlink: '{raw_db_path}'")
    if not raw_db_path.is_file():
        raise FileNotFoundError(
            f"Corpus index database not found at '{raw_db_path}'"
        )
    db_path = raw_db_path.resolve(strict=True)

    match = re.search(r">\s*`([^`\n]+)`", skill_content) or re.search(r'search\s+["\']([^"\']+)["\']', skill_content)
    if not match:
        raise PublicBundleValidationError(
            f"No canonical search query found in skill for '{doc_type}'"
        )

    query = match.group(1).strip()
    from crawler import searchindex

    try:
        search_res = searchindex.search(db_path, query, limit=5)
    except searchindex.EmptyQuery as err:
        raise PublicBundleValidationError(
            f"Corpus search query contains no searchable terms '{query}' "
            f"(doc_type: '{doc_type}')"
        ) from err
    if not isinstance(search_res, dict):
        raise PublicBundleValidationError(
            f"Corpus search returned an invalid result schema for '{doc_type}'"
        )
    hits = search_res.get("hits", [])
    if not isinstance(hits, list):
        raise PublicBundleValidationError(
            f"Corpus search returned an invalid hits schema for '{doc_type}'"
        )
    if not hits:
        raise PublicBundleValidationError(
            f"Corpus search returned zero hits for query '{query}' "
            f"(doc_type: '{doc_type}')"
        )

    resolved_quotes = []
    for hit in hits:
        if not isinstance(hit, dict) or not isinstance(hit.get("chunk_id"), str):
            raise PublicBundleValidationError(
                f"Corpus search returned an invalid hit schema for '{doc_type}'"
            )
        chunk_id = hit["chunk_id"]
        chunk = searchindex.resolve(db_path, chunk_id)
        if chunk is not None and not isinstance(chunk, dict):
            raise PublicBundleValidationError(
                f"Corpus resolution returned an invalid chunk schema for '{doc_type}'"
            )
        if chunk and isinstance(chunk.get("text"), str) and chunk["text"].strip():
            resolved_quotes.append(
                f"### Chunk: {chunk_id}\n> {chunk['text'].strip()}"
            )

    if not resolved_quotes:
        raise PublicBundleValidationError(
            f"Failed to resolve any non-empty corpus chunks for query '{query}' "
            f"(doc_type: '{doc_type}')"
        )

    bundle_sections.extend(["", "## Authoritative Local Corpus Quotes", *resolved_quotes])

    content = "\n".join(bundle_sections)

    leaks = find_public_content_leaks(content)
    if leaks:
        raise PublicBundleValidationError(
            f"Public review bundle for '{doc_type}' contains forbidden "
            f"privileged content: {', '.join(leaks)}"
        )

    lower_content = content.lower()
    if re.search(r"\b[a-f0-9]{32}\b", lower_content):
        raise PublicBundleValidationError(
            f"Public review bundle for '{doc_type}' contains an opaque case ID"
        )

    bundle_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return {
        "doc_type": doc_type,
        "content": content,
        "bundle_hash": bundle_hash,
    }
