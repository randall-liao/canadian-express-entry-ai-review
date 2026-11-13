"""Unit and contract tests for Phase 74 Worker isolation, AnswerObject parsing, and public bundle construction."""

from __future__ import annotations

import json
import re
import string
import tempfile
import unittest
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from crawler.eval.public_bundle import (
    FORBIDDEN_PRIVILEGED_KEYWORDS,
    _PRIVILEGED_NORMALIZED_PHRASES,
    PublicBundleValidationError,
    build_public_review_bundle,
    find_public_content_leaks,
)
from crawler.eval.pipeline_worker import (
    ParentPiiManifest,
    _PII_CATEGORIES,
    _assert_answer_blindness_and_pii,
    _build_parent_pii_manifest,
    _canonical_json_hash,
    _collect_structured_pii,
    _has_explicit_private_person_semantics,
    _has_plural_private_person_token_semantics,
    _is_safe_structured_person_value,
    _label_tokens,
    _normalized_person_name_words,
    run_blind_worker_task,
)
from crawler.eval.real_worker import CopilotExecutionError
from crawler.synthetic.schemas import ExpressEntryDocType
from crawler.synthetic.staging import generate_opaque_32hex_id


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_PDF = next((_REPO_ROOT / "crawler" / "eval" / "pipelines").rglob("*.pdf"))
VALID_PDF_BYTES = _SAMPLE_PDF.read_bytes()

_PRIVILEGED_SCAN_VARIANTS = (
    "P.F.L / POON NAME / 01",
    "P F L POON NAME 0 1",
    "PFLPOONNAME01",
    "Ｐ．Ｆ．Ｌ／ＰＯＯＮ\u3000ＮＡＭＥ／０１",
    "expectedVerdict",
    "expected_verdict",
    "expected-verdict",
    "expected.verdict",
    "ｅｘｐｅｃｔｅｄＶｅｒｄｉｃｔ",
    "sourceFailureId",
    "source_failure_id",
    "source-failure-id",
    "source.failure.id",
    "groundTruth",
    "ground_truth",
    "ground-truth",
    "ground.truth",
    "courtClerkSignaturePresent",
    "court_clerk_signature_present",
    "court-clerk-signature-present",
    "court.clerk.signature.present",
    "translationCertified=false",
    "translation_certified_false",
    "translation-certified-false",
    "translation.certified.false",
    "case001",
    "case_001",
    "case-0-0-1",
    "ｃａｓｅ００１",
    "opaqueCaseId",
    "opaque_case_id",
    "opaque-case-id",
    "opaque.case.id",
)

_CLEAN_PUBLIC_RULE_CONTROLS = (
    "The expected result is determined from the cited public rule.",
    "Ground officers must verify source documents.",
    "A translation certification may be required.",
    "The court clerk must sign the public form when required.",
    "Use the examples in cases 1 through 3.",
    "A failure to include a passport can make an application incomplete.",
    "The latest database contains the public guidance.",
    "The showcase kindergarten application is complete.",
    "Failure identification is part of routine triage.",
    "The background truth is visible in the cited image.",
    "Coworker outputs are reviewed independently.",
)
_REVIEWER_CLEAN_CONTROLS = _CLEAN_PUBLIC_RULE_CONTROLS[:5]


def _private_phrase_internal_split_variants() -> tuple[tuple[str, str], ...]:
    """Split each eligible private word once, matching the reviewer's 75 probes."""
    variants: list[tuple[str, str]] = []
    for phrase in sorted(_PRIVILEGED_NORMALIZED_PHRASES):
        words = phrase.split()
        for index, word in enumerate(words):
            if len(word) < 4:
                continue
            split_at = len(word) // 2
            split_words = list(words)
            split_words[index] = f"{word[:split_at]}-{word[split_at:]}"
            variants.append((phrase, "-".join(split_words)))
    return tuple(variants)


_PRIVATE_PHRASE_INTERNAL_SPLIT_VARIANTS = (
    _private_phrase_internal_split_variants()
)
_C0_DELIMITERS = tuple(chr(codepoint) for codepoint in range(0x20))


def _private_phrase_c0_split_variants() -> tuple[tuple[str, str, int], ...]:
    """Insert every C0 separator at every intra-word private-phrase boundary."""
    variants: list[tuple[str, str, int]] = []
    for phrase in sorted(_PRIVILEGED_NORMALIZED_PHRASES):
        for split_at in range(1, len(phrase)):
            if not (phrase[split_at - 1].isalnum() and phrase[split_at].isalnum()):
                continue
            for codepoint, delimiter in enumerate(_C0_DELIMITERS):
                variants.append(
                    (
                        phrase,
                        f"{phrase[:split_at]}{delimiter}{phrase[split_at:]}",
                        codepoint,
                    )
                )
    return tuple(variants)


_PRIVATE_PHRASE_C0_SPLIT_VARIANTS = _private_phrase_c0_split_variants()
_PRIVILEGED_IDENTIFIER_EXAMPLES = (
    ("case-short", "case001"),
    ("case-long", "case12345678"),
    ("internal-def-vector", "defv1"),
    ("internal-def-scanned", "defs2048"),
    ("internal-val-vector", "valv17"),
    ("internal-val-scanned", "vals99999999"),
    ("pfl-short", "pfl01"),
    ("pfl-document", "pflpassport01"),
    ("pfl-other-name", "pflpoonname01"),
    ("failure-label", "failureid"),
    ("source-failure-label", "sourcefailureid"),
    ("research-failure-label", "researchfailureid"),
    ("opaque-label", "opaquecaseid"),
    ("opaque-hex", "0123456789abcdef0123456789abcdef"),
)
_IDENTIFIER_SPLIT_DELIMITERS = tuple(chr(codepoint) for codepoint in range(0x21)) + tuple(
    string.punctuation
)
_IDENTIFIER_COMBINING_MARKS = (
    ("acute", "\N{COMBINING ACUTE ACCENT}"),
    ("circumflex", "\N{COMBINING CIRCUMFLEX ACCENT}"),
    ("diaeresis", "\N{COMBINING DIAERESIS}"),
    ("cedilla-ccc202", "\N{COMBINING CEDILLA}"),
    ("comma-above-right-ccc232", "\N{COMBINING COMMA ABOVE RIGHT}"),
    ("ypogegrammeni-ccc240", "\N{COMBINING GREEK YPOGEGRAMMENI}"),
    ("spacing-combining-mark", "\N{DEVANAGARI SIGN VISARGA}"),
    ("enclosing-combining-mark", "\N{COMBINING ENCLOSING CIRCLE}"),
)
_COMBINING_IDENTIFIER_EXAMPLES = (
    ("case", "case001"),
    ("def", "defv1"),
    ("val", "vals99999999"),
    ("pfl", "pflpassport01"),
    ("opaque-hex", "0123456789abcdef0123456789abcdef"),
)


def _privileged_identifier_split_variants():
    """Yield every ASCII delimiter/C0 insertion at every identifier position."""
    for grammar, identifier in _PRIVILEGED_IDENTIFIER_EXAMPLES:
        for split_at in range(1, len(identifier)):
            for delimiter in _IDENTIFIER_SPLIT_DELIMITERS:
                yield (
                    grammar,
                    identifier,
                    split_at,
                    ord(delimiter),
                    f"{identifier[:split_at]}{delimiter}{identifier[split_at:]}",
                )


def _privileged_identifier_combining_mark_variants():
    """Yield each identifier with every representative mark at every position."""
    for grammar, identifier in _COMBINING_IDENTIFIER_EXAMPLES:
        for position in range(len(identifier) + 1):
            for mark_name, mark in _IDENTIFIER_COMBINING_MARKS:
                yield (
                    grammar,
                    identifier,
                    position,
                    mark_name,
                    f"{identifier[:position]}{mark}{identifier[position:]}",
                )


def _answer_jsonl(answer: dict) -> str:
    return "\n".join(
        [
            json.dumps(
                {
                    "type": "assistant.reasoning",
                    "data": {"content": json.dumps({"question": "poisoned"})},
                }
            ),
            json.dumps(
                {
                    "type": "assistant.message",
                    "data": {"content": json.dumps(answer)},
                }
            ),
        ]
    )


def _manifest_from_structured_test_data(fields: object) -> ParentPiiManifest:
    values = {category: set() for category in _PII_CATEGORIES}
    name_component_groups: set[tuple[str, ...]] = set()
    _collect_structured_pii(
        values,
        fields,
        name_component_groups=name_component_groups,
    )
    return ParentPiiManifest(
        values={
            category: tuple(sorted(category_values))
            for category, category_values in values.items()
        },
        name_component_groups=tuple(sorted(name_component_groups)),
        manifest_hash="0" * 64,
    )


_EXPECTED_FIXTURE_PERSON_LABEL_COUNTS = {
    "accompanying_spouse_full_name": 2,
    "adopted_child_full_name": 10,
    "adoptive_parent_1_full_name": 10,
    "adoptive_parent_2_full_name": 10,
    "applicant_family_name": 10,
    "applicant_full_name": 10,
    "applicant_given_names": 10,
    "applicant_name": 112,
    "applicant_signature": 10,
    "candidate_name": 10,
    "child_full_name": 10,
    "deceased_full_name": 10,
    "declarant_1_full_name": 10,
    "declarant_2_full_name": 10,
    "degree_certificate_name": 2,
    "designated_individual_full_name": 10,
    "eca_applicant_name": 2,
    "employee_name": 12,
    "employer_contact_person": 10,
    "family_name": 4,
    "father_full_name": 8,
    "full_name": 15,
    "given_name": 4,
    "given_names": 12,
    "mother_full_name": 8,
    "mother_maiden_name": 2,
    "new_name": 2,
    "officiant_name": 2,
    "parent_names": 8,
    "passport_full_name": 2,
    "previous_family_name": 4,
    "previous_given_name": 4,
    "previous_name": 2,
    "primary_spouse_family_name": 10,
    "primary_spouse_given_names": 10,
    "relative_name": 10,
    "section_a_applicant_name": 10,
    "section_b_representative_name": 8,
    "section_b_representative_signature": 6,
    "section_e_applicant_signature": 6,
    "spouse_family_name": 10,
    "spouse_given_names": 10,
    "spouse_name": 10,
    "supervisor_name": 10,
    "supervisor_signature": 10,
    "surname": 12,
    "translator_identity": 10,
}
_NON_COMPONENT_NAME_TOKENS = {"and", "rev"}


def _iter_labelled_strings(value: object):
    if isinstance(value, dict):
        for label, child in value.items():
            if isinstance(label, str) and isinstance(child, str):
                yield label, child
            yield from _iter_labelled_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_labelled_strings(child)


def _meaningful_name_components(value: str) -> set[str]:
    normalized = _normalized_person_name_words(value)
    return {
        token
        for token in normalized.split()
        if sum(char.isalpha() for char in token) >= 3
        and token not in _NON_COMPONENT_NAME_TOKENS
    }


def _expected_structured_name_groups(label: str, value: str) -> tuple[set[str], ...]:
    """Independently model known plural fixture labels without production helpers."""
    individual_values = (value,)
    if label == "parent_names":
        individual_values = tuple(
            candidate.strip()
            for candidate in re.split(
                r"\s+(?:and|y)\s+|\s*&\s*|\s*;\s*|\s+/\s+",
                value,
                flags=re.IGNORECASE,
            )
            if candidate.strip()
        )
    return tuple(
        _meaningful_name_components(individual)
        for individual in individual_values
    )


def _manifest_name_components(manifest: ParentPiiManifest) -> set[str]:
    return {
        component
        for group in manifest.name_component_groups
        for component in group
    }


def _public_answer_surfaces(fragment: str) -> tuple[tuple[str, dict], ...]:
    """Place one raw fragment in every recursively scanned public string leaf."""
    base = {
        "question": "Review the supplied document.",
        "claims": [],
        "basis": [],
        "abstentions": [],
        "prose": "No public applicant facts.",
    }
    claim = {
        "id": "c1",
        "text": "Generic rule.",
        "citations": ["public/rule.md#001"],
        "quote": "generic quote",
    }
    abstention = {"text": "Generic note.", "reason": "not_in_corpus"}
    return (
        ("question", {**base, "question": fragment}),
        ("claim key", {**base, "claims": [{fragment: "c1", **claim}]}),
        ("claim id", {**base, "claims": [{**claim, "id": fragment}]}),
        ("claim text", {**base, "claims": [{**claim, "text": fragment}]}),
        (
            "claim citation",
            {**base, "claims": [{**claim, "citations": [fragment]}]},
        ),
        ("claim quote", {**base, "claims": [{**claim, "quote": fragment}]}),
        (
            "abstention key",
            {**base, "abstentions": [{fragment: "Generic note.", **abstention}]},
        ),
        (
            "abstention text",
            {**base, "abstentions": [{**abstention, "text": fragment}]},
        ),
        (
            "abstention reason",
            {**base, "abstentions": [{**abstention, "reason": fragment}]},
        ),
        ("prose", {**base, "prose": fragment}),
    )


def _schema_public_answer_surfaces(fragment: str) -> tuple[tuple[str, dict], ...]:
    """Place a fragment in each requested schema-valid public text surface."""
    base = {
        "question": "Review the supplied document.",
        "claims": [],
        "basis": [],
        "abstentions": [],
        "prose": "No public applicant facts.",
    }
    claim = {
        "id": "c1",
        "text": "Generic rule.",
        "citations": ["public/rule.md#001"],
        "quote": "generic quote",
    }
    return (
        ("question", {**base, "question": fragment}),
        ("claim", {**base, "claims": [{**claim, "text": fragment}]}),
        ("quote", {**base, "claims": [{**claim, "quote": fragment}]}),
        (
            "citation",
            {**base, "claims": [{**claim, "citations": [fragment]}]},
        ),
        (
            "abstention",
            {
                **base,
                "abstentions": [
                    {"text": fragment, "reason": "not_in_corpus"},
                ],
            },
        ),
        ("prose", {**base, "prose": fragment}),
    )


class TestPhase74WorkerIsolation(unittest.TestCase):
    """Test suite for public review bundles and blind Worker runner isolation."""

    def test_public_bundle_missing_skill_raises_file_not_found(self) -> None:
        """Bundle creation for an unknown/missing doc_type raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            build_public_review_bundle("nonexistent_type_xyz")

    def test_public_bundle_zero_privileged_keywords(self) -> None:
        """Public review bundles contain zero privileged research/ground-truth keywords."""
        doc_types = [doc_type.value for doc_type in ExpressEntryDocType]
        for dt in doc_types:
            bundle = build_public_review_bundle(dt)
            self.assertIn("doc_type", bundle)
            self.assertIn("content", bundle)
            self.assertIn("bundle_hash", bundle)

            content = bundle["content"]
            for keyword in FORBIDDEN_PRIVILEGED_KEYWORDS:
                self.assertNotIn(
                    keyword.lower(),
                    content.lower(),
                    f"Public bundle for '{dt}' contains privileged keyword '{keyword}'",
                )
            self.assertIn("## Authoritative Local Corpus Quotes", content)

    def test_letter_of_explanation_uses_dedicated_skill(self) -> None:
        bundle = build_public_review_bundle("letter_of_explanation")
        self.assertIn("letter-of-explanation.md", bundle["content"])
        self.assertNotIn("other-name.md", bundle["content"])

    def test_public_bundle_missing_corpus_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                build_public_review_bundle(
                    "passport", corpus_db_path=Path(tmp_dir) / "missing.db"
                )

    def test_public_bundle_hash_deterministic(self) -> None:
        """Public bundle SHA-256 hash is deterministic and reproducible."""
        bundle1 = build_public_review_bundle("passport")
        bundle2 = build_public_review_bundle("passport")
        self.assertEqual(bundle1["bundle_hash"], bundle2["bundle_hash"])
        self.assertEqual(len(bundle1["bundle_hash"]), 64)  # 64 hex chars

    def test_worker_staging_isolation_and_command_construction(self) -> None:
        """Worker executes inside an isolated staging CWD with correct Copilot CLI flags."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)

            opaque_id = generate_opaque_32hex_id()
            pdf_path = pipeline_dir / f"{opaque_id}.pdf"
            pdf_path.write_bytes(VALID_PDF_BYTES)

            captured_cmd = []
            captured_cwd = None

            def mock_runner(cmd: list[str], cwd: Path) -> str:
                nonlocal captured_cmd, captured_cwd
                captured_cmd = list(cmd)
                captured_cwd = cwd

                # Verify staging CWD is outside pipeline_root
                self.assertNotEqual(cwd, pipeline_root)
                self.assertFalse(cwd.is_relative_to(pipeline_root))

                # Verify the model-visible staging filename is neutral.
                staged_files = [p.name for p in cwd.iterdir()]
                self.assertEqual(staged_files, ["document.pdf"])

                # Return valid AnswerObject JSON
                valid_answer = {
                    "question": "Review the supplied passport document for compliance.",
                    "claims": [
                        {
                            "id": "CLAIM-01",
                            "text": "Passport biographical data page is valid.",
                            "citations": ["pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md#016"],
                            "quote": "biographical data page of a passport or travel document",
                        }
                    ],
                    "basis": ["Passport holder name analyzed."],
                    "abstentions": [],
                    "prose": "Document meets requirements.",
                }
                return _answer_jsonl(valid_answer)

            result = run_blind_worker_task(
                opaque_case_id=opaque_id,
                doc_type="passport",
                runner_fn=mock_runner,
                pipeline_root=pipeline_root,
            )

            # Assert attachment, long context, JSONL, and zero tool/path privilege.
            self.assertNotIn("--allow-all", captured_cmd)
            self.assertNotIn("--allow-all-paths", captured_cmd)
            self.assertNotIn("--allow-all-tools", captured_cmd)
            self.assertNotIn("--available-tools", captured_cmd)
            self.assertIn("--no-custom-instructions", captured_cmd)
            self.assertIn("--no-ask-user", captured_cmd)
            self.assertIn("--disable-builtin-mcps", captured_cmd)
            self.assertIn("--disallow-temp-dir", captured_cmd)
            self.assertIn("--excluded-tools=*", captured_cmd)
            self.assertIn("--attachment", captured_cmd)
            self.assertEqual(
                captured_cmd[captured_cmd.index("--attachment") + 1],
                "document.pdf",
            )
            prompt = captured_cmd[captured_cmd.index("-p") + 1]
            self.assertNotIn(opaque_id, prompt)
            self.assertNotIn(f"{opaque_id}.pdf", " ".join(captured_cmd))
            self.assertNotIn(str(pdf_path), prompt)
            self.assertNotIn("OPAQUE CASE ID", prompt)
            self.assertNotIn("sha256=", prompt)
            self.assertIn("long_context", captured_cmd)
            self.assertIn("--output-format", captured_cmd)
            self.assertIn("json", captured_cmd)
            self.assertIn("gemini-3.6-flash", captured_cmd)

            # Assert output structure & provenance
            self.assertEqual(result["case_id"], opaque_id)
            self.assertEqual(result["doc_type"], "passport")
            self.assertIn("_provenance", result)
            self.assertEqual(result["_provenance"]["engine"], "injected-test-runner")
            self.assertEqual(result["_provenance"]["model"], "gemini-3.6-flash")
            self.assertFalse(result["_provenance"]["is_live"])
            self.assertNotIn("command", result["_provenance"])
            self.assertNotIn("staging_dir", result["_provenance"])
            self.assertEqual(len(result["_provenance"]["input_pdf_sha256"]), 64)
            self.assertEqual(len(result["_provenance"]["bundle_hash"]), 64)
            self.assertEqual(len(result["_provenance"]["provenance_digest"]), 64)
            self.assertFalse(captured_cwd.exists())

    def test_worker_fail_closed_on_subprocess_error(self) -> None:
        """Worker fails closed on CLI process error without emitting fake reports."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)

            opaque_id = generate_opaque_32hex_id()
            pdf_path = pipeline_dir / f"{opaque_id}.pdf"
            pdf_path.write_bytes(VALID_PDF_BYTES)

            def failing_runner(cmd: list[str], cwd: Path) -> str:
                raise CopilotExecutionError("Copilot process crashed")

            with self.assertRaises(CopilotExecutionError):
                run_blind_worker_task(
                    opaque_case_id=opaque_id,
                    doc_type="passport",
                    runner_fn=failing_runner,
                    pipeline_root=pipeline_root,
                )

    def test_worker_fail_closed_on_invalid_schema(self) -> None:
        """Worker fails closed when LLM returns invalid JSON/AnswerObject schema."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)

            opaque_id = generate_opaque_32hex_id()
            pdf_path = pipeline_dir / f"{opaque_id}.pdf"
            pdf_path.write_bytes(VALID_PDF_BYTES)

            def malformed_runner(cmd: list[str], cwd: Path) -> str:
                return "Not a valid JSON object"

            with self.assertRaises(CopilotExecutionError):
                run_blind_worker_task(
                    opaque_case_id=opaque_id,
                    doc_type="passport",
                    runner_fn=malformed_runner,
                    pipeline_root=pipeline_root,
                )

    def test_worker_rejects_fences_prose_and_extra_or_missing_top_level_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)
            opaque_id = generate_opaque_32hex_id()
            (pipeline_dir / f"{opaque_id}.pdf").write_bytes(VALID_PDF_BYTES)
            base_answer = {
                "question": "Review the supplied passport.",
                "claims": [],
                "basis": [],
                "abstentions": [],
                "prose": "No claims made.",
            }

            bad_contents = [
                f"```json\n{json.dumps(base_answer)}\n```",
                f"Result follows: {json.dumps(base_answer)}",
                json.dumps({**base_answer, "extra": "forbidden"}),
                json.dumps({k: v for k, v in base_answer.items() if k != "prose"}),
            ]
            for content in bad_contents:
                def bad_runner(cmd: list[str], cwd: Path, raw: str = content) -> str:
                    return json.dumps(
                        {"type": "assistant.message", "data": {"content": raw}}
                    )

                with self.subTest(content=content), self.assertRaises(
                    CopilotExecutionError
                ):
                    run_blind_worker_task(
                        opaque_case_id=opaque_id,
                        doc_type="passport",
                        runner_fn=bad_runner,
                        pipeline_root=pipeline_root,
                    )

    def test_worker_checks_question_and_abstentions_but_keeps_basis_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)
            opaque_id = generate_opaque_32hex_id()
            (pipeline_dir / f"{opaque_id}.pdf").write_bytes(VALID_PDF_BYTES)
            base_answer = {
                "question": "Review the supplied passport.",
                "claims": [],
                "basis": ["Jane Synthetic has passport X99999999."],
                "abstentions": [],
                "prose": "No claims made.",
            }

            for contaminated in (
                {**base_answer, "question": f"Review ground_truth case {opaque_id}."},
                {
                    **base_answer,
                    "abstentions": [
                        {
                            "text": "Jane Synthetic has SIN 123-456-789.",
                            "reason": "not_in_corpus",
                        }
                    ],
                },
            ):
                def contaminated_runner(
                    cmd: list[str], cwd: Path, answer: dict = contaminated
                ) -> str:
                    return _answer_jsonl(answer)

                with self.subTest(answer=contaminated), self.assertRaises(ValueError):
                    run_blind_worker_task(
                        opaque_case_id=opaque_id,
                        doc_type="passport",
                        runner_fn=contaminated_runner,
                        pipeline_root=pipeline_root,
                    )

            def basis_only_runner(cmd: list[str], cwd: Path) -> str:
                return _answer_jsonl(base_answer)

            result = run_blind_worker_task(
                opaque_case_id=opaque_id,
                doc_type="passport",
                runner_fn=basis_only_runner,
                pipeline_root=pipeline_root,
            )
            self.assertEqual(result["basis"], base_answer["basis"])

    def test_parent_pii_manifest_rejects_diverse_values_in_every_public_field(
        self,
    ) -> None:
        source_text = """
Applicant Name: Carlos Garcia
Date of Birth: 1990-01-02
Passport Number: AB123456
Home Address: 123 Maple Street, Ottawa, ON K1A 0B1
Email: carlos.garcia@example.test
Phone: +1 (613) 555-0199
SIN: 123-456-789
Rule Effective Date: 2016-01-01
Minimum Required Funds: $14,690
"""
        manifest = _build_parent_pii_manifest(
            pdf_path=None,
            extracted_text=source_text,
        )
        base = {
            "question": "Review the supplied document.",
            "claims": [],
            "basis": [source_text],
            "abstentions": [],
            "prose": "No public applicant facts.",
        }
        contaminated = (
            {**base, "question": "Review Carlos Garcia's document."},
            {
                **base,
                "claims": [
                    {
                        "id": "c1",
                        "text": "Passport AB123456 was reviewed.",
                        "citations": ["public/rule.md#001"],
                        "quote": "generic rule",
                    }
                ],
            },
            {
                **base,
                "claims": [
                    {
                        "id": "c1",
                        "text": "Generic rule.",
                        "citations": ["public/rule.md#001"],
                        "quote": "Born 1990/01/02.",
                    }
                ],
            },
            {
                **base,
                "claims": [
                    {
                        "id": "c1",
                        "text": "Generic rule.",
                        "citations": ["carlos.garcia@example.test"],
                        "quote": "generic rule",
                    }
                ],
            },
            {
                **base,
                "abstentions": [
                    {
                        "text": "Unable to assess 123 Maple Street Ottawa.",
                        "reason": "not_in_corpus",
                    }
                ],
            },
            {**base, "prose": "Call +1 613 555 0199 for details."},
        )
        for index, answer in enumerate(contaminated):
            with self.subTest(index=index, answer=answer), self.assertRaises(
                ValueError
            ):
                _assert_answer_blindness_and_pii(
                    answer,
                    pii_manifest=manifest,
                )

        public_rule_only = {
            **base,
            "prose": (
                "The generic public rule effective 2016-01-01 cites a minimum "
                "amount of $14,690."
            ),
        }
        _assert_answer_blindness_and_pii(
            public_rule_only,
            pii_manifest=manifest,
        )

    def test_public_pii_matches_compact_windows_in_every_raw_string_leaf(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "applicant_name": "John Smith",
                "home_address": "123 Maple Street",
                "birth_location": "Toronto Ontario",
                "document_identifier": "AB123456",
                "date_of_birth": "1990-01-02",
            }
        )
        base = {
            "question": "Review the supplied document.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "No public applicant facts.",
        }

        def public_surfaces(fragment: str) -> tuple[dict, ...]:
            claim = {
                "id": "c1",
                "text": "Generic rule.",
                "citations": ["public/rule.md#001"],
                "quote": "generic quote",
            }
            abstention = {"text": "Generic note.", "reason": "not_in_corpus"}
            return (
                {**base, "question": fragment},
                {**base, "claims": [{fragment: "c1", **claim}]},
                {**base, "claims": [{**claim, "id": fragment}]},
                {**base, "claims": [{**claim, "text": fragment}]},
                {**base, "claims": [{**claim, "citations": [fragment]}]},
                {**base, "claims": [{**claim, "quote": fragment}]},
                {**base, "abstentions": [{fragment: "Generic note.", **abstention}]},
                {**base, "abstentions": [{**abstention, "text": fragment}]},
                {**base, "abstentions": [{**abstention, "reason": fragment}]},
                {**base, "prose": fragment},
            )

        leaked_variants = (
            "Jo\nhn Smith",
            "John Sm-ith",
            "123 Ma-ple Street",
            "Tor-onto Ontario",
            "AB12\n3456",
            "1990\n0102",
            "01\n02\n1990",
        )
        for variant in leaked_variants:
            for surface, answer in enumerate(public_surfaces(variant)):
                with self.subTest(variant=variant, surface=surface), self.assertRaises(
                    ValueError
                ):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )

        for clean_control in (
            "Johnny Smithson",
            "9123 Maple Street",
            "Torontonian Ontario",
            "XAB1234567",
            "Reference 1199001023",
        ):
            with self.subTest(clean_control=clean_control):
                _assert_answer_blindness_and_pii(
                    {**base, "prose": clean_control},
                    pii_manifest=manifest,
                )

    def test_every_pii_category_rejects_every_single_c0_split_on_every_public_leaf(
        self,
    ) -> None:
        fields = {
            "home_address": "123 Maple Street",
            "date_of_birth": "January 2, 1990",
            "email_address": "john.smith@example.test",
            "passport_number": "AB123456",
            "birth_location": "Toronto Ontario",
            "applicant_name": "Mélanie O'Connor",
            "phone_number": "+1 (613) 555-0199",
            "sin_number": "123-456-789",
        }
        manifest = _manifest_from_structured_test_data(fields)
        raw_values = {
            "address": fields["home_address"],
            "date": fields["date_of_birth"],
            "email": fields["email_address"],
            "identifier": fields["passport_number"],
            "location": fields["birth_location"],
            "name": fields["applicant_name"],
            "phone": fields["phone_number"],
            "sin": fields["sin_number"],
        }
        self.assertEqual(set(manifest.category_summary), set(_PII_CATEGORIES))
        self.assertEqual(
            manifest.values["email"],
            ("john.smith@example.test",),
        )

        invalid_email_manifest = _manifest_from_structured_test_data(
            {"email_address": "john smith example test"}
        )
        self.assertEqual(invalid_email_manifest.values["email"], ())

        for category, raw_value in raw_values.items():
            for split_at in range(1, len(raw_value)):
                for codepoint, delimiter in enumerate(_C0_DELIMITERS):
                    variant = (
                        f"{raw_value[:split_at]}{delimiter}{raw_value[split_at:]}"
                    )
                    for surface, answer in _public_answer_surfaces(variant):
                        with self.subTest(
                            category=category,
                            split_at=split_at,
                            codepoint=codepoint,
                            surface=surface,
                        ), self.assertRaises(ValueError):
                            _assert_answer_blindness_and_pii(
                                answer,
                                pii_manifest=manifest,
                            )

    def test_parent_pii_manifest_recurses_realistic_structures_and_narratives(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "applicant": {
                    "full_name": "Mélanie O'Connor",
                    "date_of_birth": "January 2, 1990",
                    "place_of_birth": "Toronto, Ontario, Canada",
                    "document": {
                        "passport_number": "AB 123-456",
                        "applicant_reference_id": "REF/77-991",
                    },
                    "contacts": [
                        (
                            "Home Address",
                            "Unit 4, 12B Maple Street, Ottawa, ON",
                        ),
                        [
                            "Email: melanie.oconnor@example.test",
                            "Phone: +1 (613) 555-0199",
                            "SIN: 123-456-789",
                        ],
                    ],
                },
                "financial_narrative": (
                    "Funds are held in Chequing Account #9823-112 and Savings "
                    "Account #4410-098. The gift was provided by parent: Arthur "
                    "Doe."
                ),
                "notary_details": (
                    "Notary Public Sarah Jenkins, License #ON-883912, Toronto, ON"
                ),
            }
        )
        self.assertIn("location", manifest.category_summary)
        base = {
            "question": "Review the supplied document.",
            "claims": [],
            "basis": [
                "Mélanie O'Connor, January 2, 1990, Toronto, Ontario, Canada"
            ],
            "abstentions": [],
            "prose": "No public applicant facts.",
        }
        contaminated = (
            {**base, "question": "Review MÉLANIE   O’CONNOR's document."},
            {
                **base,
                "claims": [
                    {
                        "id": "c1",
                        "text": "Passport AB-123/456 was reviewed.",
                        "citations": ["public/rule.md#001"],
                        "quote": "generic rule",
                    }
                ],
            },
            {
                **base,
                "claims": [
                    {
                        "id": "c1",
                        "text": "Generic rule.",
                        "citations": ["public/rule.md#001", "REF 77 991"],
                        "quote": "Born 2 January 1990.",
                    }
                ],
            },
            {
                **base,
                "abstentions": [
                    {
                        "text": "Unable to assess Toronto, Ontario.",
                        "reason": "not_in_corpus",
                    }
                ],
            },
            {**base, "prose": "The address begins 12B Maple Street."},
            {**base, "prose": "The parent was Arthur Doe."},
            {**base, "prose": "The notary was sarah jenkins."},
            {**base, "prose": "Account 9823 112 was reviewed."},
            {**base, "prose": "Account 4410/098 was reviewed."},
            {**base, "prose": "Email MELANIE.OCONNOR@EXAMPLE.TEST."},
            {**base, "prose": "Call 1-613-555-0199."},
        )
        for index, answer in enumerate(contaminated):
            with self.subTest(index=index, answer=answer), self.assertRaises(
                ValueError
            ):
                _assert_answer_blindness_and_pii(
                    answer,
                    pii_manifest=manifest,
                )

        # PII remains permitted only in basis[]; unrelated lexical collisions
        # do not become standalone manifest matches.
        clean = {
            **base,
            "basis": [
                "Arthur Doe used account 9823-112 and lived at 12B Maple Street."
            ],
            "prose": (
                "Arthurian examples mention Dover, Toronto, January, account, "
                "and unit 12B only as isolated generic tokens."
            ),
        }
        _assert_answer_blindness_and_pii(clean, pii_manifest=manifest)

    def test_parent_pii_manifest_extracts_actual_letter_of_explanation_shape(
        self,
    ) -> None:
        ground_truth_path = (
            _REPO_ROOT
            / "crawler"
            / "eval"
            / "pipelines"
            / "letter_of_explanation"
            / "ground_truth"
            / "ground_truth.json"
        )
        records = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        case_id = records[0]["opaque_case_id"]
        manifest = _build_parent_pii_manifest(
            pdf_path=None,
            pipeline_root=ground_truth_path.parent.parent,
            case_id=case_id,
        )
        base = {
            "question": "Review the supplied letter.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "No public applicant facts.",
        }
        for public_value in (
            "Arthur Doe",
            "Sarah Jenkins",
            "Account 9823 112",
            "Account 4410/098",
            "Submitted March 15, 2024",
        ):
            with self.subTest(public_value=public_value), self.assertRaises(
                ValueError
            ):
                _assert_answer_blindness_and_pii(
                    {**base, "prose": public_value},
                    pii_manifest=manifest,
                )

    def test_parent_pii_manifest_blocks_actual_staged_private_identifiers(
        self,
    ) -> None:
        examples = (
            (
                "educational_credential_assessment",
                "eca_reference_number",
            ),
            ("digital_photo", "photo_reference_code"),
            ("language_test", "candidate_id"),
        )
        for doc_type, field_name in examples:
            pipeline_root = (
                _REPO_ROOT / "crawler" / "eval" / "pipelines" / doc_type
            )
            records = json.loads(
                (
                    pipeline_root / "ground_truth" / "ground_truth.json"
                ).read_text(encoding="utf-8")
            )
            record = records[0]
            case_id = record["opaque_case_id"]
            raw_value = record["fields"][field_name]
            manifest = _build_parent_pii_manifest(
                pdf_path=(
                    pipeline_root
                    / "ground_truth"
                    / "pdfs"
                    / f"{case_id}.pdf"
                ),
                pipeline_root=pipeline_root,
                case_id=case_id,
            )
            normalized_value = "".join(
                char for char in raw_value.casefold() if char.isalnum()
            )
            with self.subTest(doc_type=doc_type, field_name=field_name):
                self.assertIn(
                    normalized_value,
                    manifest.values["identifier"],
                )
                with self.assertRaises(ValueError):
                    _assert_answer_blindness_and_pii(
                        {
                            "question": "Review the supplied document.",
                            "claims": [],
                            "basis": [],
                            "abstentions": [],
                            "prose": f"Reference {raw_value}.",
                        },
                        pii_manifest=manifest,
                    )

        generic_manifest = _manifest_from_structured_test_data(
            {"reference_number": "REF-2026-77119"}
        )
        self.assertIn(
            "ref202677119",
            generic_manifest.values["identifier"],
        )

    def test_parent_pii_manifest_normalizes_exact_date_equivalents(self) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "applicant_date_of_birth": "20240315",
                "rule_effective_date": "1990-01-02",
            }
        )
        self.assertEqual(manifest.values["date"], ("20240315",))
        base = {
            "question": "Review the supplied document.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "",
        }
        for equivalent in (
            "20240315",
            "2024-03-15",
            "March 15, 2024",
            "15/03/2024",
            "03/15/2024",
        ):
            with self.subTest(equivalent=equivalent), self.assertRaises(
                ValueError
            ):
                _assert_answer_blindness_and_pii(
                    {**base, "prose": equivalent},
                    pii_manifest=manifest,
                )

        ambiguous = _manifest_from_structured_test_data(
            {"date_of_birth": "01/02/1990"}
        )
        self.assertEqual(
            set(ambiguous.values["date"]),
            {"19900102", "19900201"},
        )
        for equivalent in ("January 2, 1990", "February 1, 1990"):
            with self.subTest(equivalent=equivalent), self.assertRaises(
                ValueError
            ):
                _assert_answer_blindness_and_pii(
                    {**base, "prose": equivalent},
                    pii_manifest=ambiguous,
                )

    def test_compact_personal_dates_retain_every_valid_interpretation(self) -> None:
        base = {
            "question": "Review the supplied document.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "",
        }
        examples = (
            (
                "15032024",
                {"20240315"},
                (
                    "15032024",
                    "2024-03-15",
                    "15/03/2024",
                    "03/15/2024",
                    "March 15, 2024",
                    "15 March 2024",
                ),
            ),
            (
                "03152024",
                {"20240315"},
                (
                    "03152024",
                    "2024/03/15",
                    "15.03.2024",
                    "03.15.2024",
                    "March 15, 2024",
                    "15th March 2024",
                ),
            ),
            (
                "01021990",
                {"19900102", "19900201"},
                (
                    "01021990",
                    "1990-01-02",
                    "1990-02-01",
                    "01/02/1990",
                    "02/01/1990",
                    "January 2, 1990",
                    "1 February 1990",
                ),
            ),
        )
        for compact, expected_tokens, equivalents in examples:
            manifest = _manifest_from_structured_test_data(
                {"date_of_birth": compact}
            )
            with self.subTest(compact=compact, check="manifest"):
                self.assertEqual(
                    set(manifest.values["date"]),
                    expected_tokens,
                )
            for equivalent in equivalents:
                with self.subTest(
                    compact=compact,
                    equivalent=equivalent,
                ), self.assertRaises(ValueError):
                    _assert_answer_blindness_and_pii(
                        {**base, "prose": equivalent},
                        pii_manifest=manifest,
                    )

        invalid = _manifest_from_structured_test_data(
            {"date_of_birth": "31132024"}
        )
        self.assertEqual(invalid.values["date"], ())
        _assert_answer_blindness_and_pii(
            {**base, "prose": "Reference 31132024 is not a valid date."},
            pii_manifest=invalid,
        )

    def test_narrative_relationship_names_require_structural_delimiters(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "narrative": "\n".join(
                    (
                        "Applicant Name: John Smith",
                        "parent: Arthur Doe",
                        "spouse: Marie Skłodowska Curie",
                        "Applicant Name: Ana Maria Elena Lucia Cruz Vega",
                        "Applicant must provide",
                        "parent should submit",
                        "spouse details required",
                        "Applicant Should Submit",
                        "Applicant Needs Documents",
                        "Parent Supporting Documents",
                        "Applicant Must Provide",
                        "Applicant Can Apply",
                        "Applicant May Upload",
                        "Applicant Will Receive",
                        "Applicant Shall Submit",
                        "Applicant Could Attach",
                        "Applicant Would Complete",
                        "Applicant Please Review",
                        "Applicant: Can Apply",
                        "Applicant: May Upload",
                        "Applicant: Will Receive",
                        "Applicant: Should Include",
                        "Applicant: Verify Documents",
                        "Applicant Applies Online",
                        "Applicant Uploaded Documents",
                        "Applicant Receiving Proof",
                        "Applicant Submitted Proof",
                        "Applicant Provides Documents",
                        "Applicant Included Proof",
                        "Applicant Attaches Documents",
                        "Applicant Completed Review",
                        "Applicant Reviews Documents",
                        "Applicant Verifies Proof",
                        "Applicant Supports Documents",
                        "Applicant Might Qualify",
                        "Applicant Wants Help",
                        "Applicant Was Invited",
                        "Applicant Has Status",
                        "Applicant John Smith Wants Help",
                        "Applicant Bruce Wayne, Wants Help",
                        "Narrative ordinary lowercase",
                        "Applicant: María de la Cruz",
                        "Applicant: Zoë Müller",
                        "Applicant: Søren van der Meer",
                        "Applicant: Łukasz Żółć",
                        "Spouse: marie curie",
                        "Applicant AlEX JoNES",
                        "Applicant Henry Ford 2",
                        "Unlabelled Person Name",
                        "Dr. Chloë Dubois",
                        "Physician Łukasz Żółć",
                        "Notary Public Siobhán O’Brien",
                    )
                )
            }
        )
        for expected_name in (
            "john smith",
            "arthur doe",
            "marie skłodowska curie",
            "ana maria elena lucia cruz vega",
            "maría de la cruz",
            "zoë müller",
            "søren van der meer",
            "łukasz żółć",
            "chloë dubois",
            "siobhán o brien",
        ):
            with self.subTest(expected_name=expected_name):
                self.assertIn(expected_name, manifest.values["name"])
        for clean_control in (
            "must provide",
            "should submit",
            "details required",
            "applicant should submit",
            "applicant needs documents",
            "parent supporting documents",
            "applicant must provide",
            "needs documents",
            "supporting documents",
            "alex jones",
            "henry ford",
            "unlabelled person name",
            "can apply",
            "may upload",
            "will receive",
            "shall submit",
            "could attach",
            "would complete",
            "please review",
            "should include",
            "verify documents",
            "applies online",
            "uploaded documents",
            "receiving proof",
            "submitted proof",
            "provides documents",
            "included proof",
            "attaches documents",
            "completed review",
            "reviews documents",
            "verifies proof",
            "supports documents",
            "might qualify",
            "wants help",
            "was invited",
            "has status",
            "john smith wants help",
            "bruce wayne",
            "ordinary lowercase",
        ):
            with self.subTest(clean_control=clean_control):
                self.assertNotIn(clean_control, manifest.values["name"])

        public_instructions = (
            "Applicants can apply under the public rule.",
            "Applicants may upload supporting documents.",
            "Applicants will receive public instructions.",
            "Applicants should include proof and attach completed documents.",
        )
        for instruction in public_instructions:
            with self.subTest(public_instruction=instruction):
                _assert_answer_blindness_and_pii(
                    {
                        "question": "What may applicants submit?",
                        "claims": [],
                        "basis": [],
                        "abstentions": [],
                        "prose": instruction,
                    },
                    pii_manifest=manifest,
                )

    def test_narrative_names_require_explicit_structure_not_predicate_lists(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "narrative": "\n".join(
                    (
                        "Applicant Seeks Assistance",
                        "Applicant Holds Status",
                        "Applicant Travels Abroad",
                        "Applicant Discovers Opportunities",
                        "Applicant John Smith",
                        "Spouse Marie Curie",
                        "Applicant is John Smith",
                        "Applicant is legally married",
                        "Spouse is currently abroad",
                        "Applicant Name: Aoife McDonald",
                        "Spouse: María de la Cruz",
                        "Parent = PATRICK O'NEIL",
                        "Dr. Chloë Dubois",
                        "An Arbitrary Public Clause",
                    )
                )
            }
        )

        for expected_name in (
            "aoife mcdonald",
            "maría de la cruz",
            "patrick o neil",
            "chloë dubois",
        ):
            self.assertIn(expected_name, manifest.values["name"])
        for clean_control in (
            "seeks assistance",
            "holds status",
            "travels abroad",
            "discovers opportunities",
            "john smith",
            "marie curie",
            "legally married",
            "currently abroad",
            "an arbitrary public clause",
        ):
            self.assertNotIn(clean_control, manifest.values["name"])

    def _assert_private_fixture_person_label_inventory_is_completely_protected(
        self,
    ) -> None:
        fixture_sets: list[tuple[Path, list[dict], str]] = []
        for ground_truth_path in sorted(
            (_REPO_ROOT / "crawler" / "eval" / "pipelines").glob(
                "*/ground_truth/ground_truth.json"
            )
        ):
            fixture_sets.append(
                (
                    ground_truth_path,
                    json.loads(ground_truth_path.read_text(encoding="utf-8")),
                    "fields",
                )
            )
        extraction_path = (
            _REPO_ROOT
            / "crawler"
            / "eval"
            / "synthetic_fixtures"
            / "extractions_sample.json"
        )
        fixture_sets.append(
            (
                extraction_path,
                json.loads(extraction_path.read_text(encoding="utf-8"))[
                    "extractions"
                ],
                "extracted_fields",
            )
        )

        observed_label_counts: Counter[str] = Counter()
        for fixture_path, records, field_key in fixture_sets:
            for record_index, record in enumerate(records):
                fields = record.get(field_key, {})
                manifest = _manifest_from_structured_test_data(fields)
                for label, value in _iter_labelled_strings(fields):
                    if label not in _EXPECTED_FIXTURE_PERSON_LABEL_COUNTS:
                        continue
                    observed_label_counts[label] += 1
                    context = (
                        str(fixture_path.relative_to(_REPO_ROOT)),
                        record.get("opaque_case_id", record_index),
                        label,
                    )
                    self.assertTrue(
                        _is_safe_structured_person_value(value),
                        msg=("unsafe expected person value", *context),
                    )
                    complete_value = _normalized_person_name_words(value)
                    if len(complete_value.split()) >= 2:
                        self.assertIn(
                            complete_value,
                            manifest.values["name"],
                            msg=("unprotected complete name", *context),
                        )
                    else:
                        self.assertIn(
                            complete_value,
                            _manifest_name_components(manifest),
                            msg=("unprotected single name", *context),
                        )
                    expected_groups = _expected_structured_name_groups(label, value)
                    for expected_components in expected_groups:
                        self.assertTrue(
                            expected_components,
                            msg=("missing meaningful name components", *context),
                        )
                        self.assertTrue(
                            any(
                                expected_components.issubset(group)
                                for group in map(
                                    set,
                                    manifest.name_component_groups,
                                )
                            ),
                            msg=("unassociated name components", *context),
                        )
                    if len(expected_groups) > 1:
                        aggregate_components = set().union(*expected_groups)
                        self.assertFalse(
                            any(
                                aggregate_components.issubset(group)
                                for group in map(
                                    set,
                                    manifest.name_component_groups,
                                )
                            ),
                            msg=("merged unrelated person groups", *context),
                        )

        self.assertEqual(
            dict(sorted(observed_label_counts.items())),
            _EXPECTED_FIXTURE_PERSON_LABEL_COUNTS,
        )

    def test_private_fixture_person_label_inventory_is_completely_protected(
        self,
    ) -> None:
        self._assert_private_fixture_person_label_inventory_is_completely_protected()

    def test_fixture_inventory_oracle_detects_removed_production_rule(
        self,
    ) -> None:
        def classifier_without_supervisors(label: str) -> bool:
            if label in {"supervisor_name", "supervisor_signature"}:
                return False
            return _has_explicit_private_person_semantics(label)

        with patch(
            "crawler.eval.pipeline_worker._has_explicit_private_person_semantics",
            side_effect=classifier_without_supervisors,
        ), self.assertRaises(AssertionError):
            self._assert_private_fixture_person_label_inventory_is_completely_protected()

    def test_fixture_organization_name_spot_controls_remain_public(self) -> None:
        organization_fields = {
            "organization_name": "Northern Policy Organization",
            "companyName": "Example Company Limited",
            "institution_full_name": "Example Technical Institute",
            "foreign_institution_name": "Example Foreign University",
            "employer_name": "Example Employer Incorporated",
        }
        organization_manifest = _manifest_from_structured_test_data(
            organization_fields
        )
        self.assertEqual(organization_manifest.values["name"], ())
        for label in organization_fields:
            with self.subTest(organization_label=label):
                self.assertFalse(_has_explicit_private_person_semantics(label))

    def test_structured_person_schema_supports_camel_and_snake_label_forms(
        self,
    ) -> None:
        labels = {
            "surname": "Rostova",
            "lastname": "Rostoff",
            "last_name": "Dubois",
            "passportFullName": "Elena Rostova",
            "client_given_name": "Amélie",
            "clientGivenNames": "Amélie Marie",
            "client_first_name": "Zoë",
            "clientMiddleNames": "Sofia Marie",
            "client_family_name": "Müller",
            "clientSurname": "Żółć",
            "mother_maiden_name": "McDonald",
            "previousFamilyName": "Rostoff",
            "degreeCertificateName": "Elena Rostoff",
            "employerContactPerson": "Jane Doe",
        }
        manifest = _manifest_from_structured_test_data(labels)
        for label, value in labels.items():
            with self.subTest(label=label):
                self.assertTrue(_has_explicit_private_person_semantics(label))
                normalized_value = _normalized_person_name_words(value)
                if len(normalized_value.split()) >= 2:
                    self.assertIn(normalized_value, manifest.values["name"])
                else:
                    self.assertNotIn(normalized_value, manifest.values["name"])
                self.assertTrue(
                    _meaningful_name_components(value).issubset(
                        _manifest_name_components(manifest)
                    )
                )

    def test_exact_structured_person_fields_accept_complete_unicode_names(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "translator_identity": "Aoife McDonald",
                "translator_name": "María de la Cruz",
                "applicant_name": "PATRICK O'NEIL",
                "spouse": "mArY aNnE sMiTh",
                "parent_name": "李 小龍",
                "full_name": "ÉLODIE McDONALD",
                "family_name": "McDonald",
                "notary_public_name": "Siobhán O’Brien",
                "nested": {
                    "applicant_full_name": "ANA-MARÍA DE LA CRUZ",
                },
            }
        )
        for expected_name in (
            "aoife mcdonald",
            "maría de la cruz",
            "patrick o neil",
            "mary anne smith",
            "李 小龍",
            "élodie mcdonald",
            "mcdonald",
            "siobhán o brien",
            "ana maría de la cruz",
        ):
            with self.subTest(expected_name=expected_name):
                if len(expected_name.split()) >= 2:
                    self.assertIn(expected_name, manifest.values["name"])
                else:
                    self.assertIn(
                        expected_name,
                        _manifest_name_components(manifest),
                    )

        unsafe = _manifest_from_structured_test_data(
            {
                "applicant_name": "A",
                "spouse_name": "N/A",
                "parent_name": "Jane 123",
                "company_name": "PUBLIC POLICY GROUP",
                "applicant_status": "Travels Abroad",
            }
        )
        self.assertEqual(unsafe.values["name"], ())

    def test_short_structured_names_are_contextual_on_every_public_surface(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "surname": "Li",
                "family_name": "Ng",
                "given_name": "Yu",
                "middle_name": "Q",
                "full_name": "Li Wu",
            }
        )
        self.assertEqual(manifest.values["name"], ("li wu", "yu ng"))
        for expected_group in (
            ("li",),
            ("ng",),
            ("yu",),
            ("q",),
            ("li", "wu"),
        ):
            self.assertIn(expected_group, manifest.name_component_groups)

        identity_leaks = (
            "Surname: Li",
            "Family Name is Ng",
            "Given Name: Yu",
            "Middle Name: Q",
            "Name is Li Wu",
        )
        for fragment in identity_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="identity", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=manifest,
                        )

        for fragment in (
            "Section Q contains the generic public rule.",
            "Choose option X before continuing.",
            "Li may be used as a generic abbreviation.",
        ):
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="generic", fragment=fragment, surface=surface):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )

        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public birth-certificate review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "crawler.eval.pipeline_worker._build_parent_pii_manifest",
            return_value=manifest,
        ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
            output_dir = Path(tmp_dir)
            for fragment in identity_leaks:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def identity_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh",
                        fragment=fragment,
                        surface=surface,
                    ), self.assertRaises(ValueError):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=identity_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

    def test_protected_identity_tokens_override_predicate_and_case_guards(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "surname": "May",
                "given_name": "Will",
                "family_name": "Li",
                "middle_name": "Q",
            }
        )
        for expected_group in (("may",), ("will",), ("li",), ("q",)):
            self.assertIn(expected_group, manifest.name_component_groups)

        identity_leaks = (
            "Surname: May",
            "Surname is Will",
            "Family Name: li",
            "Middle Name: q",
            "Mr. May",
        )
        generic_controls = (
            "Applicant may submit supporting documents.",
            "Applicant will provide proof.",
            "Surname: must submit proof.",
            "Surname: generic",
        )
        for fragment in identity_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="identity", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=manifest,
                        )
        for fragment in generic_controls:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="generic", fragment=fragment, surface=surface):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )

        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public birth-certificate review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "crawler.eval.pipeline_worker._build_parent_pii_manifest",
            return_value=manifest,
        ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
            output_dir = Path(tmp_dir)
            for fragment in generic_controls:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def generic_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh-generic",
                        fragment=fragment,
                        surface=surface,
                    ):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=generic_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

            for fragment in identity_leaks:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def identity_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh-identity",
                        fragment=fragment,
                        surface=surface,
                    ), self.assertRaises(ValueError):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=identity_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

    def test_identity_field_and_value_modifiers_are_bounded(self) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "surname": "May",
                "given_name": "Will",
                "family_name": "Li",
            }
        )
        identity_leaks = (
            "Surname field: May",
            "Surname value = May",
            "Given Name field is Will",
            "Family Name value was Li",
        )
        generic_controls = (
            "Surname field must be completed",
            "Surname value should be provided",
            "Surname field May",
            "Surname: field May",
            "Surname is value May",
            "Surname field: generic May",
            "The field value is May",
        )
        for fragment in identity_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="identity", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=manifest,
                        )
        for fragment in generic_controls:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="generic", fragment=fragment, surface=surface):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )

        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public birth-certificate review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "crawler.eval.pipeline_worker._build_parent_pii_manifest",
            return_value=manifest,
        ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
            output_dir = Path(tmp_dir)
            for fragment in identity_leaks:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def identity_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh-identity",
                        fragment=fragment,
                        surface=surface,
                    ), self.assertRaises(ValueError):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=identity_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

            for fragment in generic_controls:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def generic_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh-generic",
                        fragment=fragment,
                        surface=surface,
                    ):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=generic_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

    def test_protected_surname_field_and_value_override_modifiers_and_stops_on_all_surfaces(
        self,
    ) -> None:
        """CR-18: Exact protected Field and Value surnames override modifier parsing and identity stop tokens across all leaves/surfaces."""
        field_manifest = _manifest_from_structured_test_data({"surname": "Field"})
        value_manifest = _manifest_from_structured_test_data({"surname": "Value"})
        smith_manifest = _manifest_from_structured_test_data({"surname": "Smith"})

        field_leaks = (
            "Surname: Field",
            "Surname = Field",
            "Surname - Field",
            "Surname, Field",
            "Surname is Field",
            "Surname was Field",
            "Mr. Field",
            "Ms. Field",
            "Dr. Field",
        )
        value_leaks = (
            "Surname: Value",
            "Surname = Value",
            "Surname - Value",
            "Surname, Value",
            "Surname is Value",
            "Surname was Value",
            "Mr. Value",
            "Ms. Value",
            "Dr. Value",
        )
        generic_completed_controls = (
            "Surname field must be completed",
            "Surname value must be completed",
        )
        generic_modifier_smith_leaks = (
            "Surname field: Smith",
            "Surname field is Smith",
            "Surname value: Smith",
            "Surname value is Smith",
        )

        # 1. Direct leaf validation across every public leaf
        for fragment in field_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(target="field", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=field_manifest,
                        )

        for fragment in value_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(target="value", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=value_manifest,
                        )

        for fragment in generic_completed_controls:
            for manifest_target, manifest in (
                ("field", field_manifest),
                ("value", value_manifest),
                ("smith", smith_manifest),
            ):
                for surface, answer in _public_answer_surfaces(fragment):
                    with self.subTest(
                        target=manifest_target,
                        fragment=fragment,
                        surface=surface,
                    ):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=manifest,
                        )

        for fragment in generic_modifier_smith_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(target="smith", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=smith_manifest,
                        )

        # 2. Fresh execution across representative document types
        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public review instructions.",
            "bundle_hash": "a" * 64,
        }

        test_doctypes = [doc_type.value for doc_type in ExpressEntryDocType]

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)

            with patch(
                "crawler.eval.pipeline_worker._build_parent_pii_manifest",
                return_value=field_manifest,
            ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
                for doc_type in test_doctypes[:3]:
                    for fragment in field_leaks:
                        for surface, answer in _schema_public_answer_surfaces(fragment):
                            def field_runner(_cmd, _cwd, *, current_answer=answer):
                                return _answer_jsonl(current_answer)

                            with self.subTest(
                                kind="fresh-field",
                                doc_type=doc_type,
                                fragment=fragment,
                                surface=surface,
                            ), self.assertRaises(ValueError):
                                run_blind_worker_task(
                                    opaque_case_id=case_id,
                                    doc_type=doc_type,
                                    public_bundle=public_bundle,
                                    runner_fn=field_runner,
                                    pipeline_root=pipeline_dir,
                                    output_dir=output_dir,
                                )

            with patch(
                "crawler.eval.pipeline_worker._build_parent_pii_manifest",
                return_value=value_manifest,
            ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
                for doc_type in test_doctypes[:3]:
                    for fragment in value_leaks:
                        for surface, answer in _schema_public_answer_surfaces(fragment):
                            def value_runner(_cmd, _cwd, *, current_answer=answer):
                                return _answer_jsonl(current_answer)

                            with self.subTest(
                                kind="fresh-value",
                                doc_type=doc_type,
                                fragment=fragment,
                                surface=surface,
                            ), self.assertRaises(ValueError):
                                run_blind_worker_task(
                                    opaque_case_id=case_id,
                                    doc_type=doc_type,
                                    public_bundle=public_bundle,
                                    runner_fn=value_runner,
                                    pipeline_root=pipeline_dir,
                                    output_dir=output_dir,
                                )

            with patch(
                "crawler.eval.pipeline_worker._build_parent_pii_manifest",
                return_value=smith_manifest,
            ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
                for fragment in generic_completed_controls:
                    for surface, answer in _schema_public_answer_surfaces(fragment):
                        def generic_runner(_cmd, _cwd, *, current_answer=answer):
                            return _answer_jsonl(current_answer)

                        with self.subTest(
                            kind="fresh-generic-completed",
                            fragment=fragment,
                            surface=surface,
                        ):
                            run_blind_worker_task(
                                opaque_case_id=case_id,
                                doc_type="birth_certificate",
                                public_bundle=public_bundle,
                                runner_fn=generic_runner,
                                pipeline_root=pipeline_dir,
                                output_dir=output_dir,
                            )

    def test_pre_delimited_protected_field_and_value_win_before_trailing_modifier_syntax(
        self,
    ) -> None:
        """CR-19: A protected value starts at the leading separator, before trailing modifier syntax is considered."""
        manifests = {
            protected: _manifest_from_structured_test_data(
                {"surname": protected}
            )
            for protected in ("Field", "Value")
        }
        smith_manifest = _manifest_from_structured_test_data(
            {"surname": "Smith"}
        )
        leading_separators = (": ", " = ", " - ", ", ", "#", "\n")
        trailing_syntax = (
            " is recorded",
            " was recorded",
            ": recorded",
            "/recorded",
        )
        protected_leaks = tuple(
            (
                protected,
                f"Surname{leading_separator}{protected}{trailing}",
            )
            for protected in manifests
            for leading_separator in leading_separators
            for trailing in trailing_syntax
        )

        for protected, fragment in protected_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(
                    kind="direct-protected-value",
                    protected=protected,
                    fragment=fragment,
                    surface=surface,
                ), self.assertRaises(ValueError):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifests[protected],
                    )

        modifier_control = "Surname field: Smith"
        for surface, answer in _public_answer_surfaces(modifier_control):
            with self.subTest(
                kind="direct-modifier-control",
                target="field",
                surface=surface,
            ):
                _assert_answer_blindness_and_pii(
                    answer,
                    pii_manifest=manifests["Field"],
                )
            with self.subTest(
                kind="direct-modifier-control",
                target="smith",
                surface=surface,
            ), self.assertRaises(ValueError):
                _assert_answer_blindness_and_pii(
                    answer,
                    pii_manifest=smith_manifest,
                )

        pipeline_dir = (
            _REPO_ROOT
            / "crawler"
            / "eval"
            / "pipelines"
            / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            for protected, fragment in protected_leaks:
                with patch(
                    "crawler.eval.pipeline_worker._build_parent_pii_manifest",
                    return_value=manifests[protected],
                ), patch(
                    "crawler.eval.pipeline_worker.check_answer_grounding"
                ):
                    for surface, answer in _schema_public_answer_surfaces(
                        fragment
                    ):

                        def protected_runner(
                            _cmd,
                            _cwd,
                            *,
                            current_answer=answer,
                        ):
                            return _answer_jsonl(current_answer)

                        with self.subTest(
                            kind="fresh-protected-value",
                            protected=protected,
                            fragment=fragment,
                            surface=surface,
                        ), self.assertRaises(ValueError):
                            run_blind_worker_task(
                                opaque_case_id=case_id,
                                doc_type="birth_certificate",
                                public_bundle=public_bundle,
                                runner_fn=protected_runner,
                                pipeline_root=pipeline_dir,
                                output_dir=output_dir,
                            )

            for target, manifest, should_raise in (
                ("field", manifests["Field"], False),
                ("smith", smith_manifest, True),
            ):
                with patch(
                    "crawler.eval.pipeline_worker._build_parent_pii_manifest",
                    return_value=manifest,
                ), patch(
                    "crawler.eval.pipeline_worker.check_answer_grounding"
                ):
                    for surface, answer in _schema_public_answer_surfaces(
                        modifier_control
                    ):

                        def modifier_runner(
                            _cmd,
                            _cwd,
                            *,
                            current_answer=answer,
                        ):
                            return _answer_jsonl(current_answer)

                        context = (
                            self.assertRaises(ValueError)
                            if should_raise
                            else nullcontext()
                        )
                        with self.subTest(
                            kind="fresh-modifier-control",
                            target=target,
                            surface=surface,
                        ), context:
                            run_blind_worker_task(
                                opaque_case_id=case_id,
                                doc_type="birth_certificate",
                                public_bundle=public_bundle,
                                runner_fn=modifier_runner,
                                pipeline_root=pipeline_dir,
                                output_dir=output_dir,
                            )

    def test_unqualified_plural_name_labels_cover_every_public_surface(
        self,
    ) -> None:
        structured_examples = (
            (
                "full_names",
                "Karen White Davis and Mark Steven Davis",
                (("karen", "white", "davis"), ("mark", "steven", "davis")),
            ),
            (
                "fullNames",
                ["Alice Marie Brown", "Robert James Green"],
                (("alice", "marie", "brown"), ("robert", "james", "green")),
            ),
            (
                "Full names",
                "Chloë Anne Dubois; René Louis Martin",
                (("chloë", "anne", "dubois"), ("rené", "louis", "martin")),
            ),
            (
                "names",
                ["Sofia Maria Rossi", "Luca Paolo Bianchi"],
                (("sofia", "maria", "rossi"), ("luca", "paolo", "bianchi")),
            ),
        )
        for label, value, expected_groups in structured_examples:
            with self.subTest(kind="structured", label=label):
                self.assertTrue(_has_explicit_private_person_semantics(label))
                self.assertTrue(
                    _has_plural_private_person_token_semantics(_label_tokens(label))
                )
                manifest = _manifest_from_structured_test_data({label: value})
                for expected_group in expected_groups:
                    self.assertIn(expected_group, manifest.name_component_groups)

        for label in ("given_names", "givenNames", "middle_names", "middleNames"):
            with self.subTest(kind="single-person-components", label=label):
                self.assertTrue(_has_explicit_private_person_semantics(label))
                self.assertFalse(
                    _has_plural_private_person_token_semantics(_label_tokens(label))
                )

        manifest = _manifest_from_structured_test_data(
            {
                "full_names": "Karen White Davis and Mark Steven Davis",
            }
        )
        identity_leaks = (
            "Full names are Mark and Karen.",
            "Names are Mark and Karen.",
        )
        for fragment in identity_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="identity", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=manifest,
                        )

        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public birth-certificate review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "crawler.eval.pipeline_worker._build_parent_pii_manifest",
            return_value=manifest,
        ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
            output_dir = Path(tmp_dir)
            for fragment in identity_leaks:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def identity_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh",
                        fragment=fragment,
                        surface=surface,
                    ), self.assertRaises(ValueError):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=identity_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

    def test_nonplural_list_name_components_preserve_one_person(self) -> None:
        examples = (
            (
                {
                    "given_names": ["Karen", "Marie"],
                    "family_name": "Davis",
                },
                (("karen", "marie"), ("karen", "marie", "davis")),
                (("karen",), ("marie",)),
            ),
            (
                {
                    "middle_names": ["Alice", "Rose"],
                    "family_name": "Brown",
                },
                (("alice", "rose"),),
                (("alice",), ("rose",)),
            ),
            (
                {"given_names": ["Chloë", "Anne"]},
                (("chloë", "anne"),),
                (("chloë",), ("anne",)),
            ),
            (
                {"middle_names": ["René", "Louis"]},
                (("rené", "louis"),),
                (("rené",), ("louis",)),
            ),
        )
        for fields, expected_groups, forbidden_groups in examples:
            with self.subTest(kind="component-sequence", fields=fields):
                manifest = _manifest_from_structured_test_data(fields)
                for expected_group in expected_groups:
                    self.assertIn(expected_group, manifest.name_component_groups)
                for forbidden_group in forbidden_groups:
                    self.assertNotIn(forbidden_group, manifest.name_component_groups)

        manifest = _manifest_from_structured_test_data(
            {
                "given_names": ["Karen", "Marie"],
                "family_name": "Davis",
                "spouse_middle_names": ["Alice", "Rose"],
            }
        )
        self.assertIn("karen marie davis", manifest.values["name"])
        current_payload = {
            "schema": "parent-pii-manifest-v2",
            "values": manifest.values,
            "name_component_groups": manifest.name_component_groups,
        }
        legacy_payload = {
            **current_payload,
            "name_component_groups": (
                ("alice",),
                ("davis",),
                ("karen",),
                ("marie",),
                ("rose",),
            ),
        }
        self.assertNotEqual(
            _canonical_json_hash(current_payload),
            _canonical_json_hash(legacy_payload),
        )

        identity_leaks = ("Karen Marie Davis", "Alice Rose")
        for fragment in identity_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="identity", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=manifest,
                        )

        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public birth-certificate review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "crawler.eval.pipeline_worker._build_parent_pii_manifest",
            return_value=manifest,
        ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
            output_dir = Path(tmp_dir)
            for fragment in identity_leaks:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def identity_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh",
                        fragment=fragment,
                        surface=surface,
                    ), self.assertRaises(ValueError):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=identity_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

    def test_policy_scope_uses_exact_container_tokens_and_propagates(self) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "public_policy": {
                    "metadata": {
                        "reference_number": "POL-2026-1001",
                        "effective_date": "20260131",
                    }
                },
                "policy_metadata": {
                    "nested_reference": {
                        "reference_number": "POL-2026-1002",
                        "effective_date": "January 30, 2026",
                    }
                },
                "regulation_details": {
                    "reference_number": "REG-2026-1003",
                    "effective_date": "30/01/2026",
                },
                "regulationDetails": {
                    "referenceNumber": "REG-2026-1006",
                    "effectiveDate": "2026-01-27",
                },
                "rule_metadata": {
                    "reference_number": "RULE-2026-1005",
                    "effective_date": "2026-01-28",
                },
                "statute_history": {
                    "reference_number": "STA-2026-1004",
                    "effective_date": "2026-01-29",
                },
                "source_of_funds": {
                    "reference_number": "FUNDS-2026-7711",
                    "effective_date": "2025-12-28",
                },
                "notary_public": {
                    "reference_number": "NOTARY-2026-8811",
                    "effective_date": "2025-12-27",
                },
                "sourceOfFunds": {
                    "referenceNumber": "FUNDS-2026-7712",
                    "effectiveDate": "2025-12-25",
                },
                "notaryPublic": {
                    "referenceNumber": "NOTARY-2026-8812",
                    "effectiveDate": "2025-12-24",
                },
                "policyholder_details": {
                    "reference_number": "CLIENT-2026-9911",
                    "effective_date": "2025-12-26",
                },
                "policyHolderDetails": {
                    "referenceNumber": "CLIENT-2026-9912",
                    "effectiveDate": "2025-12-23",
                },
                "policy_HolderDetails": {
                    "referenceNumber": "CLIENT-2026-9913",
                    "effectiveDate": "2025-12-22",
                },
                "policyholder_Details": {
                    "referenceNumber": "CLIENT-2026-9914",
                    "effectiveDate": "2025-12-21",
                },
                "holder_details": {
                    "referenceNumber": "CLIENT-2026-9915",
                    "effectiveDate": "2025-12-20",
                },
                "public_Policy": {
                    "referenceNumber": "POL-2026-1007",
                    "effectiveDate": "2026-01-26",
                },
                "policy_Metadata": {
                    "referenceNumber": "POL-2026-1008",
                    "effectiveDate": "2026-01-25",
                },
                "policySource": {
                    "referenceNumber": "POL-2026-1010",
                    "effectiveDate": "2026-01-23",
                },
                "publicPolicySource": {
                    "referenceNumber": "POL-2026-1011",
                    "effectiveDate": "2026-01-22",
                },
                "policy_source": {
                    "reference_number": "POL-2026-1012",
                    "effective_date": "2026-01-21",
                },
                "public_policy_source": {
                    "reference_number": "POL-2026-1013",
                    "effective_date": "2026-01-20",
                },
                "policySourceMetadata": {
                    "referenceNumber": "POL-2026-1014",
                    "effectiveDate": "2026-01-19",
                },
                "public_policy_source_details": {
                    "reference_number": "POL-2026-1015",
                    "effective_date": "2026-01-18",
                },
                "regulation_Details": {
                    "referenceNumber": "REG-2026-1009",
                    "effectiveDate": "2026-01-24",
                },
                "source_OfFunds": {
                    "referenceNumber": "FUNDS-2026-7713",
                    "effectiveDate": "2025-12-19",
                },
                "notary_Public": {
                    "referenceNumber": "NOTARY-2026-8813",
                    "effectiveDate": "2025-12-18",
                },
                "policyHolder": {
                    "referenceNumber": "CLIENT-2026-9916",
                    "effectiveDate": "2025-12-17",
                },
                "policyholder": {
                    "referenceNumber": "CLIENT-2026-9917",
                    "effectiveDate": "2025-12-16",
                },
                "policySourceOfFunds": {
                    "referenceNumber": "FUNDS-2026-7714",
                    "effectiveDate": "2025-12-15",
                },
                "public_policy_source_archive": {
                    "reference_number": "CLIENT-2026-9918",
                    "effective_date": "2025-12-14",
                },
            }
        )
        for public_identifier in (
            "pol20261001",
            "pol20261002",
            "reg20261003",
            "reg20261006",
            "rule20261005",
            "sta20261004",
            "pol20261007",
            "pol20261008",
            "reg20261009",
            "pol20261010",
            "pol20261011",
            "pol20261012",
            "pol20261013",
            "pol20261014",
            "pol20261015",
        ):
            with self.subTest(public_identifier=public_identifier):
                self.assertNotIn(
                    public_identifier,
                    manifest.values["identifier"],
                )
        for public_date in (
            "20260131",
            "20260130",
            "20260129",
            "20260128",
            "20260127",
            "20260126",
            "20260125",
            "20260124",
            "20260123",
            "20260122",
            "20260121",
            "20260120",
            "20260119",
            "20260118",
        ):
            with self.subTest(public_date=public_date):
                self.assertNotIn(public_date, manifest.values["date"])

        for private_identifier in (
            "funds20267711",
            "funds20267712",
            "notary20268811",
            "notary20268812",
            "client20269911",
            "client20269912",
            "client20269913",
            "client20269914",
            "client20269915",
            "funds20267713",
            "notary20268813",
            "client20269916",
            "client20269917",
            "funds20267714",
            "client20269918",
        ):
            with self.subTest(private_identifier=private_identifier):
                self.assertIn(
                    private_identifier,
                    manifest.values["identifier"],
                )
        for private_date in (
            "20251228",
            "20251227",
            "20251226",
            "20251225",
            "20251224",
            "20251223",
            "20251222",
            "20251221",
            "20251220",
            "20251219",
            "20251218",
            "20251217",
            "20251216",
            "20251215",
            "20251214",
        ):
            with self.subTest(private_date=private_date):
                self.assertIn(private_date, manifest.values["date"])

        public_answer = {
            "question": "What do the public policy and regulation require?",
            "claims": [
                {
                    "id": "c1",
                    "text": "The public references apply.",
                    "citations": ["POL-2026-1001", "REG-2026-1003"],
                    "quote": "Effective January 30, 2026.",
                }
            ],
            "basis": [],
            "abstentions": [],
            "prose": "Statute STA-2026-1004 was effective 2026-01-29.",
        }
        _assert_answer_blindness_and_pii(
            public_answer,
            pii_manifest=manifest,
        )

    def test_private_ancestry_overrides_nested_public_policy_scope(self) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "policySource": {
                    "referenceNumber": "PUBLIC-2026-1001",
                    "effectiveDate": "2026-01-31",
                    "policyHolder": {
                        "policySource": {
                            "referenceNumber": "CLIENT-2026-2001",
                            "effectiveDate": "2025-12-31",
                        }
                    },
                    "sourceOfFunds": {
                        "policySource": {
                            "referenceNumber": "FUNDS-2026-2002",
                            "effectiveDate": "2025-12-30",
                        }
                    },
                    "notaryPublic": {
                        "policySource": {
                            "referenceNumber": "NOTARY-2026-2003",
                            "effectiveDate": "2025-12-29",
                        }
                    },
                    "applicant_name": {
                        "policySource": {
                            "referenceNumber": "PERSON-2026-2004",
                            "effectiveDate": "2025-12-28",
                        }
                    },
                    "passport": {
                        "policySource": {
                            "referenceNumber": "DOC-2026-2005",
                            "effectiveDate": "2025-12-27",
                        }
                    },
                    "passportNumber": "PA-2026-2006",
                    "documentIdentifier": "DOC-2026-2007",
                    "dateOfBirth": "1990-05-14",
                    "emailAddress": "private.person@example.test",
                },
                "policyHolder": {
                    "policySource": {
                        "referenceNumber": "CLIENT-2026-3001",
                        "effectiveDate": "2025-11-30",
                    }
                },
                "sourceOfFunds": {
                    "policySource": {
                        "referenceNumber": "FUNDS-2026-3002",
                        "effectiveDate": "2025-11-29",
                    }
                },
                "notaryPublic": {
                    "policySource": {
                        "referenceNumber": "NOTARY-2026-3003",
                        "effectiveDate": "2025-11-28",
                    }
                },
                "policyholder": {
                    "policySource": {
                        "referenceNumber": "CLIENT-2026-3004",
                        "effectiveDate": "2025-11-27",
                    }
                },
                "pair_forms": [
                    [
                        "policySource",
                        {
                            "referenceNumber": "PUBLIC-2026-1002",
                            "effectiveDate": "2026-01-30",
                        },
                    ],
                    [
                        "sourceOfFunds",
                        {
                            "policySource": {
                                "referenceNumber": "FUNDS-2026-3005",
                                "effectiveDate": "2025-11-26",
                            }
                        },
                    ],
                ],
            }
        )

        self.assertNotIn("public20261001", manifest.values["identifier"])
        self.assertNotIn("public20261002", manifest.values["identifier"])
        self.assertNotIn("20260131", manifest.values["date"])
        self.assertNotIn("20260130", manifest.values["date"])
        for private_identifier in (
            "client20262001",
            "funds20262002",
            "notary20262003",
            "person20262004",
            "doc20262005",
            "pa20262006",
            "doc20262007",
            "client20263001",
            "funds20263002",
            "notary20263003",
            "client20263004",
            "funds20263005",
        ):
            with self.subTest(private_identifier=private_identifier):
                self.assertIn(private_identifier, manifest.values["identifier"])
        for private_date in (
            "20251231",
            "20251230",
            "20251229",
            "20251228",
            "20251227",
            "19900514",
            "20251130",
            "20251129",
            "20251128",
            "20251127",
            "20251126",
        ):
            with self.subTest(private_date=private_date):
                self.assertIn(private_date, manifest.values["date"])
        self.assertIn(
            "private.person@example.test",
            manifest.values["email"],
        )

    def test_certified_translation_person_fields_are_private_on_fresh_path(
        self,
    ) -> None:
        pipeline_dir = _REPO_ROOT / "crawler" / "eval" / "pipelines" / "certified_translation"
        records = json.loads(
            (pipeline_dir / "ground_truth" / "ground_truth.json").read_text(
                encoding="utf-8"
            )
        )
        case = next(
            record
            for record in records
            if record.get("fields", {}).get("translator_identity")
            == "Elena Rostova"
        )
        case_id = case["opaque_case_id"]
        source_pdf = pipeline_dir / "ground_truth" / "pdfs" / f"{case_id}.pdf"
        source_txt = source_pdf.with_suffix(".txt")
        manifest = _build_parent_pii_manifest(
            pdf_path=source_pdf,
            extracted_text=(
                source_txt.read_text(encoding="utf-8", errors="replace")
                if source_txt.is_file()
                else ""
            ),
            pipeline_root=pipeline_dir,
            case_id=case_id,
        )
        self.assertIn("elena rostova", manifest.values["name"])
        fixture_only_manifest = _build_parent_pii_manifest(
            pdf_path=None,
            extracted_text="",
            pipeline_root=pipeline_dir,
            case_id=case_id,
        )
        self.assertIn("elena rostova", fixture_only_manifest.values["name"])

        passport_pipeline = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "passport"
        )
        passport_records = json.loads(
            (
                passport_pipeline / "ground_truth" / "ground_truth.json"
            ).read_text(encoding="utf-8")
        )
        uppercase_case = next(
            record
            for record in passport_records
            if record.get("fields", {}).get("full_name") == "HANS MUELLER"
        )
        uppercase_fixture_manifest = _build_parent_pii_manifest(
            pdf_path=None,
            extracted_text="",
            pipeline_root=passport_pipeline,
            case_id=uppercase_case["opaque_case_id"],
        )
        self.assertIn("hans mueller", uppercase_fixture_manifest.values["name"])

        explicit_person_fields = {
            "translator_identity": "Elena Rostova",
            "translator_name": "Amélie Dubois",
            "translator": "Marek Nowak",
            "identity": "Sofia Rossi",
            "interpreter": "Zoë Müller",
            "declarant": "Søren Larsen",
            "affiant": "Łukasz Żółć",
            "notary": "Siobhán O’Brien",
            "person": "María de la Cruz",
        }
        direct_manifest = _manifest_from_structured_test_data(
            explicit_person_fields
        )
        for expected in (
            "elena rostova",
            "amélie dubois",
            "marek nowak",
            "sofia rossi",
            "zoë müller",
            "søren larsen",
            "łukasz żółć",
            "siobhán o brien",
            "maría de la cruz",
        ):
            self.assertIn(expected, direct_manifest.values["name"])

        contaminated_answer = {
            "question": "Review the supplied certified translation.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "The translator is Elena Rostova.",
        }
        clean_answer = {
            **contaminated_answer,
            "prose": "No public applicant facts.",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)

            def contaminated_runner(_cmd: list[str], _cwd: Path) -> str:
                return _answer_jsonl(contaminated_answer)

            with self.assertRaises(ValueError):
                run_blind_worker_task(
                    opaque_case_id=case_id,
                    doc_type="certified_translation",
                    runner_fn=contaminated_runner,
                    pipeline_root=pipeline_dir,
                    output_dir=output_dir,
                )
            self.assertFalse((output_dir / f"{case_id}.json").exists())

            def clean_runner(_cmd: list[str], _cwd: Path) -> str:
                return _answer_jsonl(clean_answer)

            report = run_blind_worker_task(
                opaque_case_id=case_id,
                doc_type="certified_translation",
                runner_fn=clean_runner,
                pipeline_root=pipeline_dir,
                output_dir=output_dir,
            )
            provenance = report["_provenance"]
            self.assertEqual(
                provenance["pii_manifest_hash"],
                manifest.manifest_hash,
            )
            self.assertEqual(provenance["pii_manifest_count"], manifest.count)
            self.assertEqual(
                provenance["pii_manifest_categories"],
                manifest.category_summary,
            )
            self.assertNotIn(
                "Elena Rostova",
                json.dumps(provenance, ensure_ascii=False),
            )

    def test_proof_of_other_name_fixture_names_are_rejected_on_fresh_path(
        self,
    ) -> None:
        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "proof_of_other_name"
        )
        case_id = "378ead7a471b75091f478ffb48739dfa"
        manifest = _build_parent_pii_manifest(
            pdf_path=None,
            extracted_text="",
            pipeline_root=pipeline_dir,
            case_id=case_id,
        )
        for protected_value in (
            "elena rostova",
            "elena rostoff",
        ):
            with self.subTest(protected_value=protected_value):
                self.assertIn(protected_value, manifest.values["name"])
        for protected_component in ("elena", "rostova", "rostoff"):
            with self.subTest(protected_component=protected_component):
                self.assertIn(
                    protected_component,
                    _manifest_name_components(manifest),
                )

        contaminated_answer = {
            "question": "Review the supplied proof of other name.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "The degree certificate names Elena Rostoff.",
        }

        def contaminated_runner(_cmd: list[str], _cwd: Path) -> str:
            return _answer_jsonl(contaminated_answer)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            with self.assertRaises(ValueError):
                run_blind_worker_task(
                    opaque_case_id=case_id,
                    doc_type="proof_of_other_name",
                    runner_fn=contaminated_runner,
                    pipeline_root=pipeline_dir,
                    output_dir=output_dir,
                )
            self.assertFalse((output_dir / f"{case_id}.json").exists())

    def test_plural_structured_person_values_create_only_individual_groups(
        self,
    ) -> None:
        examples = (
            (
                "Karen White Davis, Mark Steven Davis",
                ({"karen", "white", "davis"}, {"mark", "steven", "davis"}),
            ),
            (
                "Karen White Davis\nMark Steven Davis",
                ({"karen", "white", "davis"}, {"mark", "steven", "davis"}),
            ),
            (
                "Karen White Davis|Mark Steven Davis",
                ({"karen", "white", "davis"}, {"mark", "steven", "davis"}),
            ),
            (
                "Karen White Davis and Mark Steven Davis",
                ({"karen", "white", "davis"}, {"mark", "steven", "davis"}),
            ),
            (
                "Alice Marie Brown & Robert James Green",
                ({"alice", "marie", "brown"}, {"robert", "james", "green"}),
            ),
            (
                "Chloë Anne Dubois; René Louis Martin",
                ({"chloë", "anne", "dubois"}, {"rené", "louis", "martin"}),
            ),
            (
                "Sofia Maria Rossi/Luca Paolo Bianchi",
                ({"sofia", "maria", "rossi"}, {"luca", "paolo", "bianchi"}),
            ),
            (
                "Lucia Fernandez Gomez y Alejandro Fernandez Ruiz",
                (
                    {"lucia", "fernandez", "gomez"},
                    {"alejandro", "fernandez", "ruiz"},
                ),
            ),
        )
        for raw_value, expected_groups in examples:
            with self.subTest(raw_value=raw_value):
                manifest = _manifest_from_structured_test_data(
                    {"parent_names": raw_value}
                )
                actual_groups = tuple(map(set, manifest.name_component_groups))
                for expected_group in expected_groups:
                    self.assertIn(expected_group, actual_groups)
                merged_components = set().union(*expected_groups)
                self.assertFalse(
                    any(
                        merged_components.issubset(group)
                        for group in actual_groups
                    )
                )

        for label, raw_value in (
            ("full_name", "Davis, Mark"),
            ("parent_names", "Davis, Mark Steven"),
        ):
            with self.subTest(label=label, raw_value=raw_value):
                manifest = _manifest_from_structured_test_data({label: raw_value})
                self.assertIn(
                    {"davis", "mark"} if label == "full_name" else {
                        "davis",
                        "mark",
                        "steven",
                    },
                    tuple(map(set, manifest.name_component_groups)),
                )
                self.assertEqual(len(manifest.name_component_groups), 1)

        comma_manifest = _manifest_from_structured_test_data(
            {
                "parent_names": "Karen White Davis, Mark Steven Davis",
            }
        )
        current_payload = {
            "schema": "parent-pii-manifest-v2",
            "values": comma_manifest.values,
            "name_component_groups": comma_manifest.name_component_groups,
        }
        legacy_payload = {
            **current_payload,
            "name_component_groups": (
                ("karen", "white", "davis", "mark", "steven"),
            ),
        }
        self.assertNotEqual(
            _canonical_json_hash(current_payload),
            _canonical_json_hash(legacy_payload),
        )

        listed_manifest = _manifest_from_structured_test_data(
            {
                "parent_names": [
                    "Karen White Davis",
                    "Mark Steven Davis",
                ]
            }
        )
        self.assertEqual(
            tuple(map(set, listed_manifest.name_component_groups)),
            (
                {"karen", "white", "davis"},
                {"mark", "steven", "davis"},
            ),
        )

    def test_repeated_last_first_pairs_preserve_each_person_association(
        self,
    ) -> None:
        examples = (
            (
                "Davis, Mark, Smith, Karen",
                (("mark", "davis"), ("karen", "smith")),
            ),
            (
                "Davis, Mark Steven, Smith, Karen Anne Marie",
                (
                    ("mark", "steven", "davis"),
                    ("karen", "anne", "marie", "smith"),
                ),
            ),
            (
                "Davis, Mark, Smith, Karen; Brown, Alice Marie"
                "|Green, Robert/Black, Jo Ann",
                (
                    ("mark", "davis"),
                    ("karen", "smith"),
                    ("alice", "marie", "brown"),
                    ("robert", "green"),
                    ("jo", "ann", "black"),
                ),
            ),
        )
        for raw_value, expected_groups in examples:
            with self.subTest(kind="pair-sequence", raw_value=raw_value):
                manifest = _manifest_from_structured_test_data(
                    {"full_names": raw_value}
                )
                for expected_group in expected_groups:
                    self.assertIn(expected_group, manifest.name_component_groups)
                self.assertFalse(
                    any(
                        set(expected_groups[0] + expected_groups[1]).issubset(group)
                        for group in map(set, manifest.name_component_groups)
                    )
                )

        ordinary_manifest = _manifest_from_structured_test_data(
            {
                "full_names": "Karen White Davis, Mark Steven Davis",
            }
        )
        self.assertIn(
            ("karen", "white", "davis"),
            ordinary_manifest.name_component_groups,
        )
        self.assertIn(
            ("mark", "steven", "davis"),
            ordinary_manifest.name_component_groups,
        )
        self.assertNotIn(
            ("mark", "smith"),
            _manifest_from_structured_test_data(
                {"full_names": "Davis, Mark, Smith"}
            ).name_component_groups,
        )

        manifest = _manifest_from_structured_test_data(
            {
                "full_names": "Davis, Mark, Smith, Karen",
            }
        )
        current_payload = {
            "schema": "parent-pii-manifest-v2",
            "values": manifest.values,
            "name_component_groups": manifest.name_component_groups,
        }
        legacy_payload = {
            **current_payload,
            "name_component_groups": (
                ("davis",),
                ("karen",),
                ("mark",),
                ("smith",),
            ),
        }
        self.assertNotEqual(
            _canonical_json_hash(current_payload),
            _canonical_json_hash(legacy_payload),
        )

        identity_leaks = (
            "Mark Davis",
            "Karen Smith",
            "Name is Mark",
            "Surname: Davis",
            "Name is Karen",
            "Surname: Smith",
        )
        generic_controls = (
            "Applicants should mark each required field.",
            "Smith applies only to this generic example.",
        )
        for fragment in identity_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="identity", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=manifest,
                        )
        for fragment in generic_controls:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="generic", fragment=fragment, surface=surface):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )

        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public birth-certificate review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "crawler.eval.pipeline_worker._build_parent_pii_manifest",
            return_value=manifest,
        ), patch("crawler.eval.pipeline_worker.check_answer_grounding"):
            output_dir = Path(tmp_dir)
            for fragment in identity_leaks:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def identity_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh",
                        fragment=fragment,
                        surface=surface,
                    ), self.assertRaises(ValueError):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=identity_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

    def test_repeated_last_first_initials_are_normalized_all_or_none(
        self,
    ) -> None:
        examples = (
            (
                "Davis, M., Smith, K.",
                (("m", "davis"), ("k", "smith")),
            ),
            (
                "Davis, M, Smith, K",
                (("m", "davis"), ("k", "smith")),
            ),
            (
                "Davis, M., Smith, Karen",
                (("m", "davis"), ("karen", "smith")),
            ),
            (
                "Brown, A. Marie, Green, Robert J.",
                (("a", "marie", "brown"), ("robert", "j", "green")),
            ),
        )
        for raw_value, expected_groups in examples:
            with self.subTest(kind="initial-pairs", raw_value=raw_value):
                manifest = _manifest_from_structured_test_data(
                    {"full_names": raw_value}
                )
                for expected_group in expected_groups:
                    self.assertIn(expected_group, manifest.name_component_groups)
                self.assertTrue(
                    all(
                        "." not in component
                        for group in manifest.name_component_groups
                        for component in group
                    )
                )

        ambiguous_manifests = (
            _manifest_from_structured_test_data(
                {"full_names": "Davis, M., Smith"}
            ),
            _manifest_from_structured_test_data(
                {"full_names": "Davis, M.., Smith, K."}
            ),
        )
        for manifest in ambiguous_manifests:
            with self.subTest(kind="all-or-none", groups=manifest.name_component_groups):
                self.assertNotIn(("m", "davis"), manifest.name_component_groups)
                self.assertNotIn(("k", "smith"), manifest.name_component_groups)

        dotted_manifest = _manifest_from_structured_test_data(
            {"full_names": "Davis, M., Smith, K."}
        )
        current_payload = {
            "schema": "parent-pii-manifest-v2",
            "values": dotted_manifest.values,
            "name_component_groups": dotted_manifest.name_component_groups,
        }
        legacy_payload = {
            **current_payload,
            "name_component_groups": (
                ("davis",),
                ("k",),
                ("m",),
                ("smith",),
            ),
        }
        self.assertNotEqual(
            _canonical_json_hash(current_payload),
            _canonical_json_hash(legacy_payload),
        )

        path_examples = (
            ("Davis, M., Smith, K.", ("M Davis", "K Smith")),
            ("Davis, M, Smith, K", ("M Davis", "K Smith")),
            ("Davis, M., Smith, Karen", ("M Davis", "Karen Smith")),
        )
        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        public_bundle = {
            "content": "Generic public birth-certificate review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "crawler.eval.pipeline_worker.check_answer_grounding"
        ):
            output_dir = Path(tmp_dir)
            for raw_value, identity_leaks in path_examples:
                manifest = _manifest_from_structured_test_data(
                    {"full_names": raw_value}
                )
                for fragment in identity_leaks:
                    for surface, answer in _public_answer_surfaces(fragment):
                        with self.subTest(
                            kind="identity",
                            raw_value=raw_value,
                            fragment=fragment,
                            surface=surface,
                        ), self.assertRaises(ValueError):
                            _assert_answer_blindness_and_pii(
                                answer,
                                pii_manifest=manifest,
                            )

                    for surface, answer in _schema_public_answer_surfaces(fragment):

                        def identity_runner(
                            _cmd: list[str],
                            _cwd: Path,
                            *,
                            current_answer: dict = answer,
                        ) -> str:
                            return _answer_jsonl(current_answer)

                        with patch(
                            "crawler.eval.pipeline_worker._build_parent_pii_manifest",
                            return_value=manifest,
                        ), self.subTest(
                            kind="fresh",
                            raw_value=raw_value,
                            fragment=fragment,
                            surface=surface,
                        ), self.assertRaises(ValueError):
                            run_blind_worker_task(
                                opaque_case_id=case_id,
                                doc_type="birth_certificate",
                                public_bundle=public_bundle,
                                runner_fn=identity_runner,
                                pipeline_root=pipeline_dir,
                                output_dir=output_dir,
                            )

            ambiguous_manifest = ambiguous_manifests[0]
            fragment = "M Davis"
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(
                    kind="ambiguous",
                    surface=surface,
                ):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=ambiguous_manifest,
                    )
            for surface, answer in _schema_public_answer_surfaces(fragment):

                def ambiguous_runner(
                    _cmd: list[str],
                    _cwd: Path,
                    *,
                    current_answer: dict = answer,
                ) -> str:
                    return _answer_jsonl(current_answer)

                with patch(
                    "crawler.eval.pipeline_worker._build_parent_pii_manifest",
                    return_value=ambiguous_manifest,
                ), self.subTest(
                    kind="fresh-ambiguous",
                    surface=surface,
                ):
                    run_blind_worker_task(
                        opaque_case_id=case_id,
                        doc_type="birth_certificate",
                        public_bundle=public_bundle,
                        runner_fn=ambiguous_runner,
                        pipeline_root=pipeline_dir,
                        output_dir=output_dir,
                    )

    def test_current_mark_white_components_require_identity_context_on_fresh_path(
        self,
    ) -> None:
        pipeline_dir = (
            _REPO_ROOT / "crawler" / "eval" / "pipelines" / "birth_certificate"
        )
        case_id = "0d8e81145a14a0ecb6b3e3d948b4219a"
        manifest = _build_parent_pii_manifest(
            pdf_path=None,
            extracted_text="",
            pipeline_root=pipeline_dir,
            case_id=case_id,
        )

        self.assertNotIn("mark", manifest.values["name"])
        self.assertNotIn("white", manifest.values["name"])
        self.assertIn(
            ("mark", "steven", "davis"),
            manifest.name_component_groups,
        )
        self.assertIn(
            ("karen", "white", "davis"),
            manifest.name_component_groups,
        )
        self.assertNotIn(
            ("karen", "white", "davis", "mark", "steven"),
            manifest.name_component_groups,
        )
        self.assertIn(
            "karen white davis and mark steven davis",
            manifest.values["name"],
        )

        generic_controls = (
            "Applicants must mark each required field.",
            "The photo must have a white background.",
            "Applicants must mark white areas clearly.",
            "Use a white mark where required.",
            "The name is marked in white.",
            "Contact person must mark white areas.",
            "Consult Dr. guidance before applicants mark white areas.",
            "Applicant mark each required field.",
            "The applicant should mark each required field.",
            "Applicant is eligible.",
            "Applicant was invited.",
            "Applicants are eligible.",
            "Parents were invited to apply.",
            "Spouses are eligible.",
            "Children were invited to apply.",
        )
        for fragment in generic_controls:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="generic", fragment=fragment, surface=surface):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )

        identity_leaks = (
            "Name: Mark",
            "Name is Mark",
            "Applicant is Mark",
            "Father is Mark",
            "Surname:Davis",
            "applicant's name is Mark",
            "The applicant’s name is Mark",
            "Name:\nMark",
            "Family Name was Davis",
            "Given Name = Mark",
            "Translator: Karen",
            "Representative is Mark",
            "Supervisor Mark",
            "ContactPerson: Karen",
            "Ｎａｍｅ is Ｍａｒｋ",
            "Mr. Mark Davis",
            "Applicant Mark Davis",
            "Karen White",
            "Mark Davis",
            "Karen White Davis",
            "Mark Steven Davis",
            "The applicants' names are Mark and Karen.",
            "The parents’ names were Karen and Mark.",
            "The spouses' names are Mark and Karen.",
            "The children's names were Karen and Mark.",
        )
        for fragment in identity_leaks:
            for surface, answer in _public_answer_surfaces(fragment):
                with self.subTest(kind="identity", fragment=fragment, surface=surface):
                    with self.assertRaises(ValueError):
                        _assert_answer_blindness_and_pii(
                            answer,
                            pii_manifest=manifest,
                        )

        public_bundle = {
            "content": "Generic public birth-certificate review instructions.",
            "bundle_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "crawler.eval.pipeline_worker.check_answer_grounding"
        ):
            output_dir = Path(tmp_dir)
            for fragment in generic_controls:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def generic_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh",
                        fragment=fragment,
                        surface=surface,
                    ):
                        report = run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=generic_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )
                        for field in (
                            "question",
                            "claims",
                            "basis",
                            "abstentions",
                            "prose",
                        ):
                            self.assertEqual(report[field], answer[field])

            for fragment in identity_leaks:
                for surface, answer in _schema_public_answer_surfaces(fragment):

                    def identity_runner(
                        _cmd: list[str],
                        _cwd: Path,
                        *,
                        current_answer: dict = answer,
                    ) -> str:
                        return _answer_jsonl(current_answer)

                    with self.subTest(
                        kind="fresh-identity",
                        fragment=fragment,
                        surface=surface,
                    ), self.assertRaises(ValueError):
                        run_blind_worker_task(
                            opaque_case_id=case_id,
                            doc_type="birth_certificate",
                            public_bundle=public_bundle,
                            runner_fn=identity_runner,
                            pipeline_root=pipeline_dir,
                            output_dir=output_dir,
                        )

    def test_private_source_semantics_cover_nested_lists_pairs_and_narrative(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data(
            {
                "public_evidence": {
                    "source_of_funds": {
                        "account_number": "AC-2026-77119",
                    },
                    "notary_public_name": "Ada Lovelace",
                    "applicants": [
                        {
                            "label": "Applicant Name",
                            "value": "Grace Hopper",
                        },
                    ],
                    "persons": [
                        "Spouse: Marie Curie",
                    ],
                    "references": [
                        {
                            "label": "Reference Number",
                            "value": "REF-2026-88117",
                        },
                    ],
                },
                "case_narrative": (
                    "Applicant must provide proof of funds. "
                    "Spouse: Marie Curie."
                ),
            }
        )
        self.assertNotIn("must provide", manifest.values["name"])
        for category, expected in (
            ("identifier", "ac202677119"),
            ("identifier", "ref202688117"),
            ("name", "ada lovelace"),
            ("name", "grace hopper"),
            ("name", "marie curie"),
        ):
            with self.subTest(category=category, expected=expected):
                self.assertIn(expected, manifest.values[category])

        _assert_answer_blindness_and_pii(
            {
                "question": "What must an applicant provide?",
                "claims": [],
                "basis": [],
                "abstentions": [],
                "prose": "Applicant must provide proof of funds.",
            },
            pii_manifest=manifest,
        )

    def test_parent_pii_manifest_excludes_public_policy_identifier_context(
        self,
    ) -> None:
        manifests = (
            _build_parent_pii_manifest(
                pdf_path=None,
                extracted_text="\n".join(
                    (
                        "Policy Reference Number: AB123456",
                        "Regulation Citation: IRPR-75/2",
                        "Source Document ID: SRC-998877",
                        "NOC Code: 21232",
                        "Rule Effective Date: January 2, 1990",
                    )
                ),
            ),
            _manifest_from_structured_test_data(
                {
                    "public_evidence": [
                        "Policy Reference Number: AB123456",
                        (
                            "Regulation Citation",
                            "IRPR-75/2",
                        ),
                    ],
                    "policy": {
                        "source_document_id": "SRC-998877",
                        "noc_code": "21232",
                        "effective_date": "January 2, 1990",
                    },
                }
            ),
        )
        public_rule = {
            "question": "What does Policy Reference Number AB123456 require?",
            "claims": [
                {
                    "id": "c1",
                    "text": "NOC 21232 is addressed by the public rule.",
                    "citations": ["IRPR-75/2", "SRC-998877"],
                    "quote": "The rule was effective January 2, 1990.",
                }
            ],
            "basis": [],
            "abstentions": [],
            "prose": "Policy Reference Number: AB123456.",
        }
        for manifest in manifests:
            with self.subTest(categories=manifest.category_summary):
                _assert_answer_blindness_and_pii(
                    public_rule,
                    pii_manifest=manifest,
                )

    def test_parent_pii_manifest_stays_out_of_worker_input_and_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            pipeline_dir.mkdir(parents=True)
            opaque_id = generate_opaque_32hex_id()
            (pipeline_dir / f"{opaque_id}.pdf").write_bytes(VALID_PDF_BYTES)
            (pipeline_dir / f"{opaque_id}.txt").write_text(
                "\n".join(
                    [
                        "Applicant Name: Carlos Garcia",
                        "Date of Birth: 1990-01-02",
                        "Document Identifier: AB123456",
                    ]
                ),
                encoding="utf-8",
            )
            captured_prompt = ""
            clean_answer = {
                "question": "Review the supplied passport.",
                "claims": [],
                "basis": ["Carlos Garcia, 1990-01-02, AB123456"],
                "abstentions": [],
                "prose": "No public applicant facts.",
            }

            def runner(cmd: list[str], cwd: Path) -> str:
                nonlocal captured_prompt
                captured_prompt = cmd[cmd.index("-p") + 1]
                return _answer_jsonl(clean_answer)

            result = run_blind_worker_task(
                opaque_case_id=opaque_id,
                doc_type="passport",
                runner_fn=runner,
                pipeline_root=pipeline_root,
            )

            self.assertNotIn("pii_manifest", captured_prompt.lower())
            serialized = json.dumps(result["_provenance"], sort_keys=True)
            for private_value in ("Carlos Garcia", "1990-01-02", "AB123456"):
                self.assertNotIn(private_value, serialized)
            self.assertGreater(result["_provenance"]["pii_manifest_count"], 0)
            self.assertEqual(
                len(result["_provenance"]["pii_manifest_hash"]),
                64,
            )

    def test_public_bundle_includes_doc_and_shared_skills(self) -> None:
        """Public bundle includes both per-document skill rules and shared PDF review contract."""
        bundle = build_public_review_bundle("passport")
        self.assertIn("## Document Skill Rules", bundle["content"])
        self.assertIn("## Shared PDF Review Contract", bundle["content"])
        self.assertIn("## Authoritative Local Corpus Quotes", bundle["content"])

    def test_public_bundle_in_memory_overrides(self) -> None:
        """In-memory overrides alter bundle content and hash deterministically without editing source on disk."""
        passport_file = _REPO_ROOT / "skills" / "document-agents" / "passport.md"
        pdf_file = _REPO_ROOT / "skills" / "pdf" / "SKILL.md"
        passport_orig_bytes = passport_file.read_bytes()
        pdf_orig_bytes = pdf_file.read_bytes()

        default_bundle = build_public_review_bundle("passport")

        search_query_line = "> `biographical data page passport`"
        doc_override = f"## Passport Candidate Rules\n{search_query_line}\n- Custom candidate passport rule"

        doc_bundle = build_public_review_bundle("passport", override_skill_content=doc_override)
        self.assertNotEqual(default_bundle["bundle_hash"], doc_bundle["bundle_hash"])
        self.assertIn("Custom candidate passport rule", doc_bundle["content"])

        shared_override = "## Shared PDF Candidate Contract\n- Custom candidate PDF raster rule"
        shared_bundle = build_public_review_bundle("passport", override_shared_content=shared_override)
        self.assertNotEqual(default_bundle["bundle_hash"], shared_bundle["bundle_hash"])
        self.assertIn("Custom candidate PDF raster rule", shared_bundle["content"])

        both_bundle = build_public_review_bundle(
            "passport",
            override_skill_content=doc_override,
            override_shared_content=shared_override,
        )
        self.assertNotEqual(doc_bundle["bundle_hash"], both_bundle["bundle_hash"])
        self.assertNotEqual(shared_bundle["bundle_hash"], both_bundle["bundle_hash"])
        self.assertIn("Custom candidate passport rule", both_bundle["content"])
        self.assertIn("Custom candidate PDF raster rule", both_bundle["content"])

        # Source files on disk MUST remain untouched
        self.assertEqual(passport_file.read_bytes(), passport_orig_bytes)
        self.assertEqual(pdf_file.read_bytes(), pdf_orig_bytes)

    def test_public_bundle_override_safety_checks(self) -> None:
        """In-memory overrides fail closed if they contain privileged keywords or opaque case IDs."""
        search_query_line = "> `biographical data page passport`"
        bad_doc_override = f"## Candidate Rule\n{search_query_line}\n- Check ground_truth values"
        with self.assertRaises(ValueError):
            build_public_review_bundle("passport", override_skill_content=bad_doc_override)

        bad_case_override = f"## Candidate Rule\n{search_query_line}\n- Check case_001 defect"
        with self.assertRaises(ValueError):
            build_public_review_bundle("passport", override_skill_content=bad_case_override)

    def test_public_bundle_rejects_normalized_privileged_leakage_variants(self) -> None:
        query = "> `biographical data page passport`"
        for fragment in _PRIVILEGED_SCAN_VARIANTS:
            override = f"## Candidate Rule\n{query}\n- {fragment}"
            with self.subTest(fragment=fragment), self.assertRaises(
                PublicBundleValidationError
            ):
                build_public_review_bundle(
                    "passport",
                    override_skill_content=override,
                )

    def test_scanner_rejects_every_private_phrase_family_in_common_encodings(
        self,
    ) -> None:
        def camel_case(words: list[str]) -> str:
            return words[0] + "".join(word.title() for word in words[1:])

        for phrase in sorted(_PRIVILEGED_NORMALIZED_PHRASES):
            words = phrase.split()
            variants = (
                phrase,
                "_".join(words),
                "-".join(words),
                ".".join(words),
                camel_case(words),
                "".join(
                    chr(ord(char) + 0xFEE0) if 0x21 <= ord(char) <= 0x7E else char
                    for char in camel_case(words)
                ),
            )
            for variant in variants:
                with self.subTest(phrase=phrase, variant=variant):
                    self.assertTrue(find_public_content_leaks(variant))

    def test_scanner_rejects_every_private_phrase_internal_split_variant(
        self,
    ) -> None:
        self.assertEqual(len(_PRIVATE_PHRASE_INTERNAL_SPLIT_VARIANTS), 75)
        for phrase, variant in _PRIVATE_PHRASE_INTERNAL_SPLIT_VARIANTS:
            with self.subTest(phrase=phrase, variant=variant):
                self.assertTrue(find_public_content_leaks(variant))

    def test_scanner_rejects_every_privileged_identifier_split_variant(
        self,
    ) -> None:
        for grammar, identifier, split_at, codepoint, variant in (
            _privileged_identifier_split_variants()
        ):
            self.assertTrue(
                find_public_content_leaks(variant),
                (grammar, identifier, split_at, codepoint, repr(variant)),
            )

        for control in (
            "showcase001",
            "case123456789",
            "undefinedv1",
            "defv123456789",
            "profilepassport01",
            "pflpassport",
            "xpflpassport01",
            "0123456789abcdef0123456789abcde",
            "0123456789abcdef0123456789abcdef0",
        ):
            self.assertEqual(find_public_content_leaks(control), [], control)

    def test_scanner_rejects_every_identifier_combining_mark_position(
        self,
    ) -> None:
        for grammar, identifier, position, mark_name, variant in (
            _privileged_identifier_combining_mark_variants()
        ):
            self.assertTrue(
                find_public_content_leaks(variant),
                (grammar, identifier, position, mark_name, repr(variant)),
            )

        for control in (
            "The naïve applicant supplied a résumé.",
            "The public showcáse001 is complete.",
            "The cáse123456789 archive is public.",
            "The prófilepassport01 guidance is public.",
            "The défault v1 setting is documented.",
            "Gróund truth is an ordinary accented phrase here.",
        ):
            self.assertEqual(find_public_content_leaks(control), [], control)

    def test_bundle_surfaces_reject_every_identifier_combining_mark_position(
        self,
    ) -> None:
        query = "> `biographical data page passport`"
        clean_doc = f"## Passport Rules\n{query}\n- Review the public document."
        clean_shared = "## Shared Rules\n- Review the supplied PDF."
        quote = {"text": "Generic public corpus guidance."}

        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "document-agents"
            skills_dir.mkdir()
            doc_source = skills_dir / "passport.md"
            shared_source = Path(tmp_dir) / "SKILL.md"

            def resolve_quote(*_args, **_kwargs):
                return {"text": quote["text"]}

            with patch(
                "crawler.searchindex.search",
                return_value={"hits": [{"chunk_id": "public/rule.md#001"}]},
            ), patch("crawler.searchindex.resolve", side_effect=resolve_quote):
                for grammar, identifier, position, mark_name, variant in (
                    _privileged_identifier_combining_mark_variants()
                ):
                    context = (
                        grammar,
                        identifier,
                        position,
                        mark_name,
                        repr(variant),
                    )
                    unsafe_doc = f"{clean_doc}\n- {variant}"
                    unsafe_shared = f"{clean_shared}\n- {variant}"

                    doc_source.write_text(unsafe_doc, encoding="utf-8")
                    shared_source.write_text(clean_shared, encoding="utf-8")
                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("document source", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            skills_dir=skills_dir,
                            shared_skill_path=shared_source,
                        )

                    doc_source.write_text(clean_doc, encoding="utf-8")
                    shared_source.write_text(unsafe_shared, encoding="utf-8")
                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("shared source", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            skills_dir=skills_dir,
                            shared_skill_path=shared_source,
                        )

                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("document override", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            override_skill_content=unsafe_doc,
                        )
                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("shared override", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            override_shared_content=unsafe_shared,
                        )

                    doc_source.write_text(clean_doc, encoding="utf-8")
                    shared_source.write_text(clean_shared, encoding="utf-8")
                    quote["text"] = variant
                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("assembled bundle", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            skills_dir=skills_dir,
                            shared_skill_path=shared_source,
                        )
                    quote["text"] = "Generic public corpus guidance."

    def test_raw_answer_rejects_every_identifier_combining_mark_position(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data({})
        for grammar, identifier, position, mark_name, variant in (
            _privileged_identifier_combining_mark_variants()
        ):
            for surface, answer in _public_answer_surfaces(variant):
                with self.subTest(
                    grammar=grammar,
                    identifier=identifier,
                    position=position,
                    mark_name=mark_name,
                    surface=surface,
                ), self.assertRaises(ValueError):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )

    def test_bundle_sources_overrides_and_output_reject_every_identifier_split(
        self,
    ) -> None:
        query = "> `biographical data page passport`"
        clean_doc = f"## Passport Rules\n{query}\n- Review the public document."
        clean_shared = "## Shared Rules\n- Review the supplied PDF."
        quote = {"text": "Generic public corpus guidance."}

        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "document-agents"
            skills_dir.mkdir()
            doc_source = skills_dir / "passport.md"
            shared_source = Path(tmp_dir) / "SKILL.md"

            def resolve_quote(*_args, **_kwargs):
                return {"text": quote["text"]}

            with patch(
                "crawler.searchindex.search",
                return_value={"hits": [{"chunk_id": "public/rule.md#001"}]},
            ), patch("crawler.searchindex.resolve", side_effect=resolve_quote):
                for grammar, identifier, split_at, codepoint, variant in (
                    _privileged_identifier_split_variants()
                ):
                    context = (
                        grammar,
                        identifier,
                        split_at,
                        codepoint,
                        repr(variant),
                    )
                    unsafe_doc = f"{clean_doc}\n- {variant}"
                    unsafe_shared = f"{clean_shared}\n- {variant}"

                    doc_source.write_text(unsafe_doc, encoding="utf-8")
                    shared_source.write_text(clean_shared, encoding="utf-8")
                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("document source", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            skills_dir=skills_dir,
                            shared_skill_path=shared_source,
                        )

                    doc_source.write_text(clean_doc, encoding="utf-8")
                    shared_source.write_text(unsafe_shared, encoding="utf-8")
                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("shared source", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            skills_dir=skills_dir,
                            shared_skill_path=shared_source,
                        )

                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("document override", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            override_skill_content=unsafe_doc,
                        )
                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("shared override", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            override_shared_content=unsafe_shared,
                        )

                    doc_source.write_text(clean_doc, encoding="utf-8")
                    shared_source.write_text(clean_shared, encoding="utf-8")
                    quote["text"] = variant
                    with self.assertRaises(
                        PublicBundleValidationError,
                        msg=("assembled bundle", *context),
                    ):
                        build_public_review_bundle(
                            "passport",
                            skills_dir=skills_dir,
                            shared_skill_path=shared_source,
                        )
                    quote["text"] = "Generic public corpus guidance."

    def test_bundle_sources_and_overrides_reject_every_internal_split_variant(
        self,
    ) -> None:
        query = "> `biographical data page passport`"
        clean_doc = f"## Passport Rules\n{query}\n- Review the public document."
        clean_shared = "## Shared Rules\n- Review the supplied PDF."
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "document-agents"
            skills_dir.mkdir()
            doc_source = skills_dir / "passport.md"
            shared_source = Path(tmp_dir) / "SKILL.md"
            for phrase, variant in _PRIVATE_PHRASE_INTERNAL_SPLIT_VARIANTS:
                unsafe_doc = f"{clean_doc}\n- {variant}"
                unsafe_shared = f"{clean_shared}\n- {variant}"
                doc_source.write_text(unsafe_doc, encoding="utf-8")
                shared_source.write_text(clean_shared, encoding="utf-8")
                with self.subTest(
                    surface="document source",
                    phrase=phrase,
                    variant=variant,
                ), self.assertRaises(PublicBundleValidationError):
                    build_public_review_bundle(
                        "passport",
                        skills_dir=skills_dir,
                        shared_skill_path=shared_source,
                    )

                doc_source.write_text(clean_doc, encoding="utf-8")
                shared_source.write_text(unsafe_shared, encoding="utf-8")
                with self.subTest(
                    surface="shared source",
                    phrase=phrase,
                    variant=variant,
                ), self.assertRaises(PublicBundleValidationError):
                    build_public_review_bundle(
                        "passport",
                        skills_dir=skills_dir,
                        shared_skill_path=shared_source,
                    )

                with self.subTest(
                    surface="document override",
                    phrase=phrase,
                    variant=variant,
                ), self.assertRaises(PublicBundleValidationError):
                    build_public_review_bundle(
                        "passport",
                        override_skill_content=unsafe_doc,
                    )
                with self.subTest(
                    surface="shared override",
                    phrase=phrase,
                    variant=variant,
                ), self.assertRaises(PublicBundleValidationError):
                    build_public_review_bundle(
                        "passport",
                        override_shared_content=unsafe_shared,
                    )

    def test_bundle_sources_and_overrides_accept_five_clean_controls(self) -> None:
        query = "> `biographical data page passport`"
        clean_lines = "\n".join(f"- {control}" for control in _REVIEWER_CLEAN_CONTROLS)
        clean_doc = f"## Passport Rules\n{query}\n{clean_lines}"
        clean_shared = f"## Shared Rules\n{clean_lines}"
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_dir = Path(tmp_dir) / "document-agents"
            skills_dir.mkdir()
            doc_source = skills_dir / "passport.md"
            shared_source = Path(tmp_dir) / "SKILL.md"
            doc_source.write_text(clean_doc, encoding="utf-8")
            shared_source.write_text(clean_shared, encoding="utf-8")

            for kwargs in (
                {
                    "skills_dir": skills_dir,
                    "shared_skill_path": shared_source,
                },
                {"override_skill_content": clean_doc},
                {"override_shared_content": clean_shared},
            ):
                with self.subTest(surface=tuple(kwargs)):
                    build_public_review_bundle("passport", **kwargs)

    def test_answer_public_string_leaves_reject_every_c0_split_variant(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data({})
        base = {
            "question": "Review the supplied document.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "No public applicant facts.",
        }

        def contaminated_answers(fragment: str) -> tuple[tuple[str, dict], ...]:
            return (
                ("question", {**base, "question": fragment}),
                (
                    "claim key",
                    {
                        **base,
                        "claims": [
                            {
                                fragment: "c1",
                                "text": "Generic rule.",
                                "citations": ["public/rule.md#001"],
                                "quote": "generic rule",
                            }
                        ],
                    },
                ),
                (
                    "claim id",
                    {
                        **base,
                        "claims": [
                            {
                                "id": fragment,
                                "text": "Generic rule.",
                                "citations": ["public/rule.md#001"],
                                "quote": "generic rule",
                            }
                        ],
                    },
                ),
                (
                    "claim text",
                    {
                        **base,
                        "claims": [
                            {
                                "id": "c1",
                                "text": fragment,
                                "citations": ["public/rule.md#001"],
                                "quote": "generic rule",
                            }
                        ],
                    },
                ),
                (
                    "claim citation",
                    {
                        **base,
                        "claims": [
                            {
                                "id": "c1",
                                "text": "Generic rule.",
                                "citations": [fragment],
                                "quote": "generic rule",
                            }
                        ],
                    },
                ),
                (
                    "claim quote",
                    {
                        **base,
                        "claims": [
                            {
                                "id": "c1",
                                "text": "Generic rule.",
                                "citations": ["public/rule.md#001"],
                                "quote": fragment,
                            }
                        ],
                    },
                ),
                (
                    "abstention key",
                    {
                        **base,
                        "abstentions": [
                            {fragment: "Generic note.", "reason": "not_in_corpus"}
                        ],
                    },
                ),
                (
                    "abstention text",
                    {
                        **base,
                        "abstentions": [
                            {"text": fragment, "reason": "not_in_corpus"}
                        ],
                    },
                ),
                (
                    "abstention reason",
                    {
                        **base,
                        "abstentions": [
                            {"text": "Generic note.", "reason": fragment}
                        ],
                    },
                ),
                ("prose", {**base, "prose": fragment}),
            )

        self.assertEqual(len(_PRIVATE_PHRASE_C0_SPLIT_VARIANTS), 14_048)
        for phrase, variant, codepoint in _PRIVATE_PHRASE_C0_SPLIT_VARIANTS:
            for surface, answer in contaminated_answers(variant):
                with self.subTest(
                    surface=surface,
                    phrase=phrase,
                    codepoint=codepoint,
                ), self.assertRaises(ValueError):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )
            with self.subTest(
                surface="basis",
                phrase=phrase,
                codepoint=codepoint,
            ):
                _assert_answer_blindness_and_pii(
                    {**base, "basis": [variant]},
                    pii_manifest=manifest,
                )

    def test_every_identifier_split_rejected_on_every_raw_public_answer_leaf(
        self,
    ) -> None:
        manifest = _manifest_from_structured_test_data({})
        base = {
            "question": "Review the supplied document.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "No public applicant facts.",
        }
        for grammar, identifier, split_at, codepoint, variant in (
            _privileged_identifier_split_variants()
        ):
            for surface, answer in _public_answer_surfaces(variant):
                try:
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )
                except ValueError:
                    pass
                else:
                    self.fail(
                        (
                            surface,
                            grammar,
                            identifier,
                            split_at,
                            codepoint,
                            repr(variant),
                        )
                    )
            _assert_answer_blindness_and_pii(
                {**base, "basis": [variant]},
                pii_manifest=manifest,
            )

    def test_injected_worker_rejects_c0_leak_before_report_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pipeline_root = Path(tmp_dir) / "pipelines"
            pipeline_dir = pipeline_root / "passport" / "ground_truth"
            output_dir = Path(tmp_dir) / "worker_reports"
            pipeline_dir.mkdir(parents=True)
            output_dir.mkdir()
            opaque_id = generate_opaque_32hex_id()
            (pipeline_dir / f"{opaque_id}.pdf").write_bytes(VALID_PDF_BYTES)
            report_path = output_dir / f"{opaque_id}.json"
            report_path.write_text('{"stale": true}', encoding="utf-8")
            answer = {
                "question": "Review the supplied passport.",
                "claims": [],
                "basis": [],
                "abstentions": [],
                "prose": "ex\x00pected verdict",
            }

            def contaminated_runner(cmd: list[str], cwd: Path) -> str:
                return _answer_jsonl(answer)

            with self.assertRaises(ValueError):
                run_blind_worker_task(
                    opaque_case_id=opaque_id,
                    doc_type="passport",
                    runner_fn=contaminated_runner,
                    pipeline_root=pipeline_root,
                    output_dir=output_dir,
                )
            self.assertFalse(report_path.exists())

    def test_answer_public_surfaces_accept_five_clean_controls(self) -> None:
        manifest = _manifest_from_structured_test_data({})
        base = {
            "question": "Review the supplied document.",
            "claims": [],
            "basis": [],
            "abstentions": [],
            "prose": "No public applicant facts.",
        }
        for control in _REVIEWER_CLEAN_CONTROLS:
            answers = (
                {**base, "question": control},
                {
                    **base,
                    "claims": [
                        {
                            "id": "c1",
                            "text": control,
                            "citations": [control],
                            "quote": control,
                        }
                    ],
                },
                {
                    **base,
                    "abstentions": [
                        {"text": control, "reason": "not_in_corpus"}
                    ],
                },
                {**base, "prose": control},
            )
            for index, answer in enumerate(answers):
                with self.subTest(control=control, surface=index):
                    _assert_answer_blindness_and_pii(
                        answer,
                        pii_manifest=manifest,
                    )

    def test_public_bundle_accepts_clean_generic_public_rule_controls(self) -> None:
        override = "\n".join(
            (
                "## Candidate Rule",
                "> `biographical data page passport`",
                *("- " + control for control in _CLEAN_PUBLIC_RULE_CONTROLS),
            )
        )
        bundle = build_public_review_bundle(
            "passport",
            override_skill_content=override,
        )
        self.assertIn(_CLEAN_PUBLIC_RULE_CONTROLS[0], bundle["content"])

    def test_every_public_skill_and_shared_contract_passes_adversarial_scan(
        self,
    ) -> None:
        public_contracts = [
            *_REPO_ROOT.glob("skills/document-agents/*.md"),
            _REPO_ROOT / "skills" / "pdf" / "SKILL.md",
            _REPO_ROOT / "AGENTS.md",
            _REPO_ROOT / "crawler" / "AGENT_SKILL.md",
            _REPO_ROOT / "crawler" / "CONTRACT.md",
        ]
        for path in public_contracts:
            self.assertEqual(
                find_public_content_leaks(path.read_text(encoding="utf-8")),
                [],
                path,
            )
        for doc_type in (doc_type.value for doc_type in ExpressEntryDocType):
            bundle = build_public_review_bundle(doc_type)
            normalized = re.sub(r"[^a-z0-9]+", " ", bundle["content"].lower())
            for forbidden in (
                " pfl ",
                " ground truth ",
                " generation spec ",
                " expected verdict ",
                " injected defect ",
                " critical specification failure ",
                " critical recency failure ",
            ):
                self.assertNotIn(forbidden, f" {normalized} ")

    def test_public_bundle_empty_punctuation_query_raises_public_bundle_validation_error(self) -> None:
        """An all-punctuation corpus query in override skill raises PublicBundleValidationError, not EmptyQuery."""
        punctuation_query_override = "## Passport Candidate Rules\n> `???` \n- Candidate rule"
        with self.assertRaises(PublicBundleValidationError) as ctx:
            build_public_review_bundle("passport", override_skill_content=punctuation_query_override)
        self.assertIn("no searchable terms", str(ctx.exception))
        self.assertIn("???", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
