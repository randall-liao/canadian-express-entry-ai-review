"""Offline compute-layer suite for the personalized Layer-1 checklist (Phase 26 — CHK-01/CHK-02).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network, NO browser (per the
``crawler/tests/test_searchindex.py`` / ``test_grounding.py`` / AGENTS.md
convention). Profile-loading tests write a SYNTHETIC ``profile.yaml`` into a
``tempfile.TemporaryDirectory`` and NEVER touch the real git-ignored
``personal/`` tree. The applicability tests are pure (in-memory profile dicts,
zero file I/O).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_checklist.py -q
    .venv/bin/python -m unittest crawler.tests.test_checklist -v

Behaviour map:

    TestPersonalDir   — $PR_PERSONAL_DIR default (./personal) + env override
    TestLoadProfile   — yaml.safe_load fail-fast: valid mapping / non-mapping /
                        missing file → ProfileError; the TRACKED synthetic
                        personal.example/profile.yaml loads as a mapping
    TestApplicability — pure applicable_items() selection (added in Task 2)
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from crawler import checklist, cli, contract, grounding, searchindex

# Reuse the sibling suite's frontmatter+body composer to plant synthetic corpus
# docs at chosen relpaths (a sibling-module import is acceptable per the house
# rule) — NEVER re-walk the real git-ignored corpus/.
from crawler.tests.test_searchindex import _doc_text

# Obvious sentinel PII tokens — also present in personal.example/profile.yaml.
# The applicability separation test asserts these NEVER leak into generic
# text/query fields (CHK-02).
_SENTINEL_TOKENS = ("Wakanda", "Latveria")

# The tracked synthetic example, relative to the repo root (tests run from root).
_EXAMPLE_PROFILE = Path("personal.example")

# Repo root (this suite lives at <root>/crawler/tests/test_checklist.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]

# The real, git-ignored, local-only index. Real-corpus tests are @skipUnless-guarded.
_REAL_DB = Path("corpus/index.db")


def _load_cps():
    """Import scripts/check_publish_safe (scripts/ is NOT a package → sys.path shim).

    Mirrors cli._cmd_checklist / test_grounding.TestFixturePublishSafety:870 — the
    shipped SAFE-02 publish-safety scanner is reused (NEVER re-implemented) so the
    Plan-03 self-scan asserts against the exact bytes the CLI write-gate scans.
    """
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # SAFE-02 share-safety scanner
    return cps


class TestPersonalDir(unittest.TestCase):
    """$PR_PERSONAL_DIR resolves to ./personal by default, env value when set."""

    def test_default_is_personal(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PR_PERSONAL_DIR", None)
            self.assertEqual(checklist.personal_dir(), Path("personal"))

    def test_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": "/some/dir"}):
            self.assertEqual(checklist.personal_dir(), Path("/some/dir"))


class TestLoadProfile(unittest.TestCase):
    """load_profile parses via yaml.safe_load and fails fast (ProfileError)."""

    def _write_profile(self, root: Path, text: str) -> None:
        (root / "profile.yaml").write_text(text, encoding="utf-8")

    def test_valid_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_profile(
                root,
                "applicant:\n"
                "  citizenship: Wakanda\n"
                "  family_members_18_plus: 1\n"
                "program:\n"
                "  stream: CEC\n"
                "  has_job_offer: false\n"
                "education:\n"
                "  claiming_foreign_education_points: true\n"
                "residence_since_18:\n"
                "  - country: Wakanda\n"
                "    months: 240\n"
                "    current: true\n",
            )
            data = checklist.load_profile(root)
            self.assertIsInstance(data, dict)
            self.assertEqual(
                sorted(data),
                ["applicant", "education", "program", "residence_since_18"],
            )

    def test_non_mapping_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # A YAML *list*, not a mapping — must be rejected fail-fast.
            self._write_profile(root, "- one\n- two\n")
            with self.assertRaises(checklist.ProfileError):
                checklist.load_profile(root)

    def test_missing_file_raises_profile_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)  # no profile.yaml written
            # Must surface as the domain ProfileError, never a bare OSError.
            with self.assertRaises(checklist.ProfileError):
                checklist.load_profile(root)

    def test_invalid_yaml_raises_profile_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_profile(root, "applicant: [unterminated\n")
            with self.assertRaises(checklist.ProfileError):
                checklist.load_profile(root)

    def test_invalid_yaml_error_message_carries_no_profile_pii(self) -> None:
        # CR-01 (BLOCKER PII LEAK): a syntax error in the REAL personal profile must
        # not splice the offending SOURCE LINE (PyYAML's caret snippet) into the
        # ProfileError message. PyYAML's MarkedYAMLError.__str__ echoes that line
        # verbatim, and the personal profile is exactly where real names/countries/
        # dates live. The raised message must be GENERIC (line/column only) — never
        # the PII-bearing snippet. FAILS on the old `f"...: {exc}"` formulation.
        pii = ("Maria", "Silva", "Portugal", "1990-05-03")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # `key: value: value` → "mapping values are not allowed here"; PyYAML's
            # snippet would echo the whole offending (PII-bearing) line.
            self._write_profile(
                root,
                "applicant:\n"
                "  citizenship: ok\n"
                "residence: Maria Silva lived in Portugal: 1990-05-03\n",
            )
            with self.assertRaises(checklist.ProfileError) as ctx:
                checklist.load_profile(root)
            message = str(ctx.exception)
            for token in pii:
                self.assertNotIn(
                    token, message,
                    f"CR-01: profile PII {token!r} leaked into the error message",
                )
            # A PII-free location hint (line/column) is still permitted/expected.
            self.assertIn("personal profile", message)

    def test_unreadable_profile_error_message_carries_no_exc_body(self) -> None:
        # CR-01 hardening: the sibling OSError branch must also stay PII-free — it
        # surfaces only the path, never the raw OS exception body.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)  # no profile.yaml → OSError → ProfileError
            with self.assertRaises(checklist.ProfileError) as ctx:
                checklist.load_profile(root)
            self.assertNotIn("Errno", str(ctx.exception))

    def test_tracked_example_loads_as_mapping(self) -> None:
        data = checklist.load_profile(_EXAMPLE_PROFILE)
        self.assertIsInstance(data, dict)
        # Schema keys the rest of the phase relies on.
        for key in ("applicant", "program", "education", "residence_since_18"):
            self.assertIn(key, data)

    def test_mistyped_subsection_raises_profile_error_not_attributeerror(self) -> None:
        # WR-01: a structurally-valid mapping whose sub-section has the WRONG type
        # (scalar where a mapping is expected) is malformed USER input. It must
        # raise ProfileError (→ invalid_input / exit 2), NOT crash later inside
        # applicable_items as `"FSW".get(...)` AttributeError (→ internal_error /
        # exit 4). The raised message must name only the field + type, never the
        # offending value (PII boundary).
        for field in ("program", "education", "applicant"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                # `<field>: "Maria Silva"` — a scalar carrying PII where a
                # sub-mapping is expected (top level stays a valid mapping).
                self._write_profile(root, f"{field}: \"Maria Silva\"\n")
                with self.assertRaises(checklist.ProfileError) as ctx:
                    checklist.load_profile(root)
                message = str(ctx.exception)
                self.assertIn(field, message)
                for token in ("Maria", "Silva"):
                    self.assertNotIn(
                        token, message,
                        f"WR-01: profile value {token!r} leaked into error message",
                    )

    def test_mistyped_residence_raises_profile_error(self) -> None:
        # WR-01: residence_since_18 must be a sequence; a scalar is malformed input.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_profile(root, "residence_since_18: Portugal\n")
            with self.assertRaises(checklist.ProfileError) as ctx:
                checklist.load_profile(root)
            self.assertNotIn("Portugal", str(ctx.exception))


def _ids(items: list) -> list:
    return [item["doc_type"] for item in items]


# The four Layer-1 items that apply to EVERY post-ITA Express Entry applicant.
_ALWAYS_ON = {"passport", "language", "medical", "biometrics"}


class TestApplicability(unittest.TestCase):
    """Pure applicable_items() selection — the RESEARCH applicability table.

    Personalization is which items appear (+ their basis reasons), NEVER mutated
    requirement text (SC2 / Pattern 3). PII (countries/dates/names) is isolated to
    each item's ``basis`` sentence — never its generic ``text``/``query``.
    """

    def test_each_item_has_the_four_required_keys(self) -> None:
        items = checklist.applicable_items(
            {"program": {"stream": "CEC"}, "education": {}, "applicant": {}}
        )
        self.assertTrue(items)
        for item in items:
            for key in ("doc_type", "query", "text", "basis"):
                self.assertIn(key, item, f"{item.get('doc_type')} missing {key}")

    def test_always_on_items_present(self) -> None:
        items = checklist.applicable_items(
            {"program": {"stream": "CEC"}, "education": {}, "applicant": {}}
        )
        self.assertTrue(_ALWAYS_ON.issubset(set(_ids(items))))

    def test_cec_omits_proof_of_funds_includes_eca_and_police(self) -> None:
        items = checklist.applicable_items(
            {
                "program": {"stream": "CEC", "has_job_offer": False},
                "education": {"claiming_foreign_education_points": True},
                "residence_since_18": [{"country": "Wakanda"}],
                "applicant": {"family_members_18_plus": 1},
            }
        )
        ids = _ids(items)
        self.assertNotIn("proof-of-funds", ids)  # CEC is exempt
        self.assertIn("eca", ids)  # claiming foreign-education points
        self.assertIn("police-certificates", ids)  # residence + family

    def test_fsw_includes_proof_of_funds(self) -> None:
        items = checklist.applicable_items(
            {
                "program": {"stream": "FSW"},
                "education": {},
                "residence_since_18": [],
                "applicant": {},
            }
        )
        self.assertIn("proof-of-funds", _ids(items))

    def test_fst_includes_proof_of_funds(self) -> None:
        items = checklist.applicable_items(
            {"program": {"stream": "FST"}, "education": {}, "applicant": {}}
        )
        self.assertIn("proof-of-funds", _ids(items))

    def test_eca_included_for_fsw_even_without_claiming_flag(self) -> None:
        items = checklist.applicable_items(
            {"program": {"stream": "FSW"}, "education": {}, "applicant": {}}
        )
        self.assertIn("eca", _ids(items))

    def test_eca_omitted_for_cec_not_claiming(self) -> None:
        items = checklist.applicable_items(
            {
                "program": {"stream": "CEC"},
                "education": {"claiming_foreign_education_points": False},
                "applicant": {},
            }
        )
        self.assertNotIn("eca", _ids(items))

    def test_job_offer_adds_letter(self) -> None:
        items = checklist.applicable_items(
            {
                "program": {"stream": "CEC", "has_job_offer": True},
                "education": {},
                "applicant": {},
            }
        )
        self.assertIn("job-offer", _ids(items))

    def test_no_job_offer_omits_letter(self) -> None:
        items = checklist.applicable_items(
            {
                "program": {"stream": "CEC", "has_job_offer": False},
                "education": {},
                "applicant": {},
            }
        )
        self.assertNotIn("job-offer", _ids(items))

    def test_empty_residence_zero_family_omits_police(self) -> None:
        items = checklist.applicable_items(
            {
                "program": {"stream": "CEC"},
                "education": {},
                "residence_since_18": [],
                "applicant": {"family_members_18_plus": 0},
            }
        )
        self.assertNotIn("police-certificates", _ids(items))

    def test_family_alone_triggers_police(self) -> None:
        items = checklist.applicable_items(
            {
                "program": {"stream": "CEC"},
                "education": {},
                "residence_since_18": [],
                "applicant": {"family_members_18_plus": 2},
            }
        )
        self.assertIn("police-certificates", _ids(items))

    def test_sparse_profile_does_not_keyerror(self) -> None:
        # A nearly-empty profile must still yield the always-on items, no KeyError.
        items = checklist.applicable_items({})
        self.assertTrue(_ALWAYS_ON.issubset(set(_ids(items))))

    def test_pii_isolated_to_basis_not_text_or_query(self) -> None:
        profile = {
            "applicant": {"citizenship": "Wakanda", "family_members_18_plus": 1},
            "program": {"stream": "CEC", "has_job_offer": False},
            "education": {"claiming_foreign_education_points": True},
            "residence_since_18": [
                {"country": "Wakanda", "months": 240, "current": True},
                {"country": "Latveria", "months": 14, "current": False},
            ],
        }
        items = checklist.applicable_items(profile)
        # The generic requirement label + corpus query must be PII-free.
        for item in items:
            for token in _SENTINEL_TOKENS:
                self.assertNotIn(
                    token,
                    item["text"],
                    f"PII '{token}' leaked into {item['doc_type']} text",
                )
                self.assertNotIn(
                    token,
                    item["query"],
                    f"PII '{token}' leaked into {item['doc_type']} query",
                )
        # The PII applicability reason IS allowed (expected) in the basis: the
        # specific country list routes ONLY to the police-certificates basis.
        police = next(i for i in items if i["doc_type"] == "police-certificates")
        for token in _SENTINEL_TOKENS:
            self.assertIn(token, police["basis"])


# --------------------------------------------------------------------------- #
# Plan 02 — the ASSEMBLER (grounded_claim / build_answer) driven against a
# SYNTHETIC tiny index built into a TemporaryDirectory in setUp. Mirrors
# test_grounding._GroundingCase: NEVER walk the real git-ignored corpus/. The
# generic pages below carry every token of the VERIFIED applicable_items queries
# so the REAL baked queries resolve end-to-end here, plus a single per-country
# police page to exercise the no-residence-leak backstop (threat T-26-08).
# --------------------------------------------------------------------------- #

_GENERIC_DOCS = {
    "guidance/police-certificates.md": (
        "You need a police certificate for every country where you lived during "
        "the last 10 years for six months in a row or longer since the age of "
        "eighteen. Each certificate must be issued by a national authority."
    ),
    "biometrics/when-to-give.md": (
        "You must give your biometrics, your fingerprints and photo, when you "
        "apply for permanent residence in Canada."
    ),
    "guidance/language-test.md": (
        "Submit the results of an approved language test for permanent residence; "
        "your results must show each of the four language abilities."
    ),
    "medical/immigration-medical-assessment.md": (
        "An immigration medical examination is required when you apply for "
        "permanent residence in Canada."
    ),
    "eca/educational-credential-assessment.md": (
        "A foreign educational credential assessment verifies that your foreign "
        "educational credential is valid for permanent residence."
    ),
    "legislation-irpr/FullText.md": (
        "Every applicant must hold a valid passport or travel document to be "
        "granted permanent residence."
    ),
    "pr-pdi/settlement-funds.md": (
        "Candidates must meet the settlement funds requirement unless they have a "
        "valid job offer or are already authorized to work in Canada."
    ),
    # PER-COUNTRY page — citing this would leak residence history (threat T-26-08).
    # The body deliberately carries NO sentinel token; the LEAK is the relpath.
    "police-certificates/wakanda-example.md": (
        "How to get a police certificate in this place: contact the national "
        "police service of the country where you lived."
    ),
}

# A synthetic item whose VERIFIED query resolves against the generic corpus above.
_POLICE_ITEM = {
    "doc_type": "police-certificates",
    "query": "police certificate 10 years country",
    "text": "Police certificate(s) for each required country.",
    "basis": "Applies because the profile lists residence since age 18.",
}


def _make_corpus(tmp: Path, docs: dict) -> Path:
    """Build a synthetic FTS5 index from ``{relpath: body}``; return the db path.

    Plants each doc (with minimal YAML frontmatter via ``_doc_text``) under a fresh
    ``corpus/`` tree inside *tmp* and builds the index INTO the same tempdir — never
    under the real git-ignored ``corpus/``.
    """
    root = tmp / "corpus"
    for relpath, body in docs.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        url = "https://www.canada.ca/en/" + relpath.replace("/", "-") + ".html"
        path.write_text(
            _doc_text(url, "2026-01-01T00:00:00Z", relpath, body), encoding="utf-8"
        )
    db = tmp / "index.db"
    searchindex.build_index(root, db)
    return db


def _example_profile() -> dict:
    """A CEC + foreign-education profile carrying sentinel residence PII.

    CEC (proof-of-funds EXEMPT) + claiming_foreign_education_points (ECA INCLUDED)
    + two residence countries + one family member 18+ (police-certificates applies)
    — so applicable_items yields passport/language/medical/biometrics/eca/police.
    """
    return {
        "applicant": {"citizenship": "Wakanda", "family_members_18_plus": 1},
        "program": {"stream": "CEC", "has_job_offer": False},
        "education": {"claiming_foreign_education_points": True},
        "residence_since_18": [
            {"country": "Wakanda", "months": 240, "current": True},
            {"country": "Latveria", "months": 14, "current": False},
        ],
    }


class _AssemblerCase(unittest.TestCase):
    """Base: a fresh synthetic generic-corpus index in one TemporaryDirectory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = _make_corpus(Path(self._tmp.name), _GENERIC_DOCS)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestGroundedClaim(_AssemblerCase):
    """grounded_claim: retrieve -> backstop -> resolve -> verbatim quote (fail-closed)."""

    def test_grounds_generic_chunk_with_verbatim_quote(self) -> None:
        claim = checklist.grounded_claim(self.db, _POLICE_ITEM)
        self.assertIsNotNone(claim)
        self.assertEqual(claim["id"], "police-certificates")
        self.assertEqual(claim["text"], _POLICE_ITEM["text"])  # generic label, unchanged
        self.assertEqual(len(claim["citations"]), 1)
        # The quote is a VERBATIM substring of the resolved chunk's stored text.
        chunk = searchindex.resolve(self.db, claim["citations"][0])
        self.assertIsNotNone(chunk)
        self.assertTrue(grounding.quote_is_grounded(claim["quote"], chunk["text"]))

    def test_zero_hit_grounds_to_none(self) -> None:
        item = dict(_POLICE_ITEM, query="zzzdoesnotexist nowherematchtoken")
        self.assertIsNone(checklist.grounded_claim(self.db, item))

    def test_empty_query_grounds_to_none(self) -> None:
        # An all-punctuation query => searchindex.EmptyQuery => fail-closed None.
        item = dict(_POLICE_ITEM, query="!!! ??? ...")
        self.assertIsNone(checklist.grounded_claim(self.db, item))

    def test_unresolvable_chunk_grounds_to_none(self) -> None:
        # search hits, but resolve returns None (miss/sha-drift) => fail-closed None.
        with mock.patch.object(searchindex, "resolve", return_value=None):
            self.assertIsNone(checklist.grounded_claim(self.db, _POLICE_ITEM))

    def test_degenerate_chunk_quote_grounds_to_none(self) -> None:
        # IN-01: a resolved chunk whose only quotable span is degenerate (a lone
        # terminator) must fail closed — grounded_claim returns None (abstention),
        # never a vacuous "." claim. FAILS on the old code, where _verbatim_quote
        # returned "." and grounded_claim emitted it.
        degenerate = {"relpath": "guidance/police-certificates.md", "text": "   .  x"}
        with mock.patch.object(searchindex, "resolve", return_value=degenerate):
            self.assertIsNone(checklist.grounded_claim(self.db, _POLICE_ITEM))

    def test_backstop_skips_country_page_grounds_generic(self) -> None:
        # A BROAD query matching BOTH the per-country page and the generic page —
        # the cited relpath must be the GENERIC one, never the country page.
        item = dict(_POLICE_ITEM, query="police certificate")
        claim = checklist.grounded_claim(self.db, item)
        self.assertIsNotNone(claim)
        relpath = claim["citations"][0].split("#", 1)[0]
        self.assertFalse(
            relpath.startswith("police-certificates/"),
            f"backstop failed: cited a per-country page {relpath!r}",
        )

    def test_only_country_page_grounds_to_none(self) -> None:
        # A corpus whose ONLY matching doc is a per-country page => fail-closed None,
        # never a residence-leaking citation.
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_corpus(
                Path(tmp),
                {
                    "police-certificates/latveria-example.md": (
                        "Police certificate guidance for this country and its "
                        "national authority over the last several years."
                    ),
                },
            )
            item = dict(_POLICE_ITEM, query="police certificate")
            self.assertIsNone(checklist.grounded_claim(db, item))

    def test_family_constraint_narrows_grounding(self) -> None:
        # The optional per-item family= constraint restricts retrieval to a relpath
        # prefix; constraining to 'guidance' still grounds the generic police page.
        item = dict(_POLICE_ITEM, query="police certificate", family="guidance")
        claim = checklist.grounded_claim(self.db, item)
        self.assertIsNotNone(claim)
        self.assertTrue(claim["citations"][0].startswith("guidance/"))


class TestCountrySpecificBackstop(unittest.TestCase):
    """WR-03: the _is_country_specific 'hard guarantee' is case/separator-robust."""

    def test_canonical_country_page_is_flagged(self) -> None:
        self.assertTrue(checklist._is_country_specific("police-certificates/france.md"))

    def test_generic_guidance_page_is_not_flagged(self) -> None:
        self.assertFalse(
            checklist._is_country_specific("guidance/police-certificates.md"))

    def test_case_and_separator_variants_are_all_flagged(self) -> None:
        # WR-03: a per-country page must be caught regardless of case, backslash
        # separators (Windows), or leading separators — otherwise a case-preserving
        # / case-insensitive corpus could surface a residence-leaking relpath.
        # FAILS on the old case-/separator-literal `rp.startswith("police-...")`.
        leaky_variants = [
            "Police-Certificates/France.md",          # capitalized dir
            "POLICE-CERTIFICATES/brazil.md",          # upper-case dir
            "police-certificates\\portugal.md",       # backslash separator
            "Police-Certificates\\Portugal.md",       # backslash + case
            "/police-certificates/spain.md",          # leading slash
            "\\Police-Certificates\\Spain.md",        # leading backslash + case
        ]
        for relpath in leaky_variants:
            self.assertTrue(
                checklist._is_country_specific(relpath),
                f"WR-03: residence-leaking relpath slipped the backstop: {relpath!r}",
            )

    def test_backstop_skips_uppercase_country_page_grounds_generic(self) -> None:
        # End-to-end: a corpus whose ONLY matching doc is an UPPER-CASE per-country
        # page must fail closed (None) — never a residence-leaking citation.
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_corpus(
                Path(tmp),
                {
                    "Police-Certificates/Latveria-Example.md": (
                        "Police certificate guidance for this country and its "
                        "national authority over the last several years."
                    ),
                },
            )
            item = dict(_POLICE_ITEM, query="police certificate")
            self.assertIsNone(checklist.grounded_claim(db, item))


class TestVerbatimQuote(unittest.TestCase):
    """IN-01: _verbatim_quote demands a minimally meaningful span (fail-closed)."""

    def test_degenerate_punctuation_span_returns_empty(self) -> None:
        # A lone-terminator chunk would previously yield "." — a vacuous quote that
        # still normalize-matches the chunk and "grounds". It must fail closed now.
        self.assertEqual(checklist._verbatim_quote("   .  x"), "")

    def test_too_few_word_chars_returns_empty(self) -> None:
        # 'a.' has a single word character — below the meaningful-quote floor.
        self.assertEqual(checklist._verbatim_quote("a. bcd efgh"), "")

    def test_empty_or_whitespace_chunk_returns_empty(self) -> None:
        self.assertEqual(checklist._verbatim_quote(""), "")
        self.assertEqual(checklist._verbatim_quote("    \n\t  "), "")

    def test_substantial_prose_yields_verbatim_substring(self) -> None:
        # Real prose still grounds: the quote is non-empty and a VERBATIM substring.
        text = "You need a police certificate for every country you lived in."
        quote = checklist._verbatim_quote(text)
        self.assertTrue(quote)
        self.assertIn(quote, text)


class TestBuildAnswerGrounds(_AssemblerCase):
    """build_answer: assemble the 5-key answer + pass it THROUGH the Phase-25 gate."""

    def test_assemble_answer_has_five_keys(self) -> None:
        answer = checklist.build_answer(_example_profile(), self.db)
        self.assertEqual(
            sorted(answer),
            ["abstentions", "basis", "claims", "prose", "question"],
        )

    def test_build_answer_grounds_pass_on_synthetic_corpus(self) -> None:
        answer = checklist.build_answer(_example_profile(), self.db)
        self.assertTrue(answer["claims"])  # the always-on items must ground
        report = grounding.check_answer(answer, self.db)
        self.assertEqual(report["verdict"], "pass", report.get("violations"))

    def test_every_claim_has_the_required_keys(self) -> None:
        answer = checklist.build_answer(_example_profile(), self.db)
        for claim in answer["claims"]:
            for key in ("id", "text", "citations", "quote"):
                self.assertIn(key, claim)
            self.assertIsInstance(claim["citations"], list)
            self.assertTrue(claim["citations"])
            self.assertIsInstance(claim["quote"], str)

    def test_build_answer_grounds_fsw_includes_proof_of_funds(self) -> None:
        profile = {
            "program": {"stream": "FSW"},
            "education": {},
            "residence_since_18": [],
            "applicant": {},
        }
        answer = checklist.build_answer(profile, self.db)
        self.assertIn("proof-of-funds", [c["id"] for c in answer["claims"]])
        self.assertEqual(
            grounding.check_answer(answer, self.db)["verdict"], "pass"
        )


class TestAbstention(_AssemblerCase):
    """Zero-applicable / zero-grounded => explicit abstention, never an empty answer."""

    def test_no_applicable_items_abstains(self) -> None:
        with mock.patch.object(checklist, "applicable_items", return_value=[]):
            answer = checklist.build_answer({}, self.db)
        self.assertEqual(answer["claims"], [])
        self.assertTrue(answer["abstentions"])  # explicit abstention, not empty

    def test_all_ungrounded_items_abstain(self) -> None:
        unmatched = [
            {
                "doc_type": "passport",
                "query": "zzznotacorpustoken neverappearsanywhere",
                "text": "Valid passport or travel document.",
                "basis": "Always required.",
            }
        ]
        with mock.patch.object(checklist, "applicable_items", return_value=unmatched):
            answer = checklist.build_answer({}, self.db)
        self.assertEqual(answer["claims"], [])
        self.assertTrue(answer["abstentions"])
        self.assertIn("passport", " ".join(answer["abstentions"]))


@unittest.skipUnless(
    Path("corpus/index.db").is_file(),
    "real corpus index (corpus/index.db) is local-only — skip when absent",
)
class TestRealCorpus(unittest.TestCase):
    """Integration: the VERIFIED baked queries ground against the LIVE 742-doc index."""

    db = Path("corpus/index.db")

    def test_real_corpus_build_answer_grounds_pass(self) -> None:
        answer = checklist.build_answer(_example_profile(), self.db)
        self.assertTrue(answer["claims"])
        self.assertEqual(
            grounding.check_answer(answer, self.db)["verdict"],
            "pass",
            grounding.check_answer(answer, self.db).get("violations"),
        )

    def test_real_corpus_cites_no_country_specific_page(self) -> None:
        answer = checklist.build_answer(_example_profile(), self.db)
        for claim in answer["claims"]:
            for cid in claim["citations"]:
                relpath = cid.split("#", 1)[0]
                self.assertFalse(
                    relpath.startswith("police-certificates/"),
                    f"residence leak: {claim['id']} cited {relpath!r}",
                )


class TestPiiSeparation(_AssemblerCase):
    """PII-free-by-construction: sentinel PII never in claims, retained in basis[]."""

    def test_pii_never_in_claims_text_or_quote(self) -> None:
        answer = checklist.build_answer(_example_profile(), self.db)
        self.assertTrue(answer["claims"])  # guard: the assertion is non-vacuous
        for claim in answer["claims"]:
            for token in _SENTINEL_TOKENS:
                self.assertNotIn(
                    token,
                    claim["text"],
                    f"PII '{token}' leaked into {claim['id']} claim text",
                )
                self.assertNotIn(
                    token,
                    claim["quote"],
                    f"PII '{token}' leaked into {claim['id']} claim quote",
                )

    def test_pii_retained_in_basis(self) -> None:
        # PII is RETAINED (not dropped) — it lives in the never-gated basis tier.
        answer = checklist.build_answer(_example_profile(), self.db)
        joined = " ".join(answer["basis"])
        self.assertTrue(
            any(token in joined for token in _SENTINEL_TOKENS),
            "expected sentinel PII to be retained in basis[]",
        )

    def test_pii_answer_validates_against_grounding_shape(self) -> None:
        # Structural assertion mirroring grounding._validate_shape: the 5-key shape
        # + every claim carries id/text/citations(list, non-empty)/quote(str).
        answer = checklist.build_answer(_example_profile(), self.db)
        self.assertEqual(
            sorted(answer),
            ["abstentions", "basis", "claims", "prose", "question"],
        )
        claims = grounding._validate_shape(answer)  # raises InvalidAnswer if malformed
        for claim in claims:
            self.assertIsInstance(claim["citations"], list)
            self.assertTrue(claim["citations"])
            self.assertIsInstance(claim["quote"], str)


class TestGenericCitation(_AssemblerCase):
    """Every claim cites a GENERIC page — never a per-country police relpath."""

    def test_no_claim_cites_country_specific_page(self) -> None:
        answer = checklist.build_answer(_example_profile(), self.db)
        self.assertTrue(answer["claims"])  # guard: the assertion is non-vacuous
        for claim in answer["claims"]:
            for cid in claim["citations"]:
                relpath = cid.split("#", 1)[0]
                self.assertFalse(
                    relpath.startswith("police-certificates/"),
                    f"residence leak: {claim['id']} cited per-country page {relpath!r}",
                )


# --------------------------------------------------------------------------- #
# Plan 03 — the `checklist` CLI verb driven end-to-end through cli.main (CHK-01,
# SC1-SC4). Mirrors test_grounding.TestGroundCli: the one-line CONTRACT envelope
# (ok/command/schema_version), stdout purity (human text -> stderr), the anchored
# --out-dir containment (CR-03), the verdict-fail/exit-1/no-write rule, the
# invalid_input/exit-2 boundaries, and the RPT-03 publish-unsafe refusal
# (internal_error/exit 4). The index + every write stays INSIDE the tempdir; the
# repo-anchored personal/ boundary is monkeypatched to a tempdir personal/ anchor.
# --------------------------------------------------------------------------- #
class _ChecklistCliCase(_AssemblerCase):
    """CLI-driving base: synthetic index + a tempdir profile + a pinned personal anchor."""

    def _anchor(self) -> Path:
        """The repo-anchored personal/ boundary, patched UNDER this case's tempdir."""
        return (Path(self._tmp.name) / "personal").resolve()

    def _out_dir(self) -> Path:
        """A tempdir output path UNDER the patched personal/ anchor (the PII boundary)."""
        return Path(self._tmp.name) / "personal" / "output"

    def _profile_dir(self, profile: dict | None = None, *, write: bool = True) -> Path:
        """Write a profile.yaml into a fresh tempdir subdir; return the dir.

        ``--profile`` takes the profile *directory* (the personal root); the verb
        reads ``<dir>/profile.yaml`` via ``checklist.load_profile``. ``write=False``
        yields a dir with NO profile.yaml (to exercise the missing-profile path).
        """
        root = Path(self._tmp.name) / "profile_root"
        root.mkdir(parents=True, exist_ok=True)
        if write:
            (root / "profile.yaml").write_text(
                yaml.safe_dump(profile if profile is not None else _example_profile()),
                encoding="utf-8",
            )
        return root

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        """Run cli.main(argv) capturing (exit_code, stdout, stderr).

        Pins the CR-03 anchored-containment boundary (``cli._personal_root``) to a
        ``personal/`` dir UNDER this case's tempdir, so the write-gate's repo-anchored
        containment is exercised WITHOUT ever writing under the real repo tree.
        """
        out, err = io.StringIO(), io.StringIO()
        anchor = self._anchor()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("crawler.cli._personal_root", return_value=anchor):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()


class TestChecklistCli(_ChecklistCliCase):
    """Drive the `checklist` verb through cli.main (GND-02 write-gate, CHK-01, SC1-SC4)."""

    def test_pass_emits_one_envelope_and_writes_one_md(self) -> None:
        """A gated checklist → one ok:true/verdict:"pass" envelope, exit 0, exactly one .md."""
        out_dir = self._out_dir()
        profile_dir = self._profile_dir()
        rc, out, err = self._run(
            ["--json", "checklist", "--db", str(self.db),
             "--out-dir", str(out_dir), "--profile", str(profile_dir)])
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("\n"), 1)             # exactly ONE JSON line
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertEqual(obj["command"], "checklist")
        self.assertEqual(obj["schema_version"], "1.0")   # additive change: unchanged
        self.assertEqual(obj["result"]["verdict"], "pass")
        self.assertIsNone(obj["error"])
        self.assertNotIn("{", err)                       # no JSON leaked to stderr
        # Exactly one file written under the personal/ out-dir; result.out points at it.
        written = list(out_dir.glob("*.md"))
        self.assertEqual(len(written), 1)
        self.assertEqual(obj["result"]["out"], str(written[0]))

    def test_out_dir_outside_anchor_is_rejected_containment(self) -> None:
        """CR-03: an --out-dir NOT under the repo anchor → invalid_input/exit 2, no write."""
        anchor = self._anchor()
        escaping = [
            Path(self._tmp.name) / "evil" / "personal" / "out",
            Path(self._tmp.name) / "x" / "personal",
            Path(self._tmp.name) / "personal-decoy" / "personal" / "z",
        ]
        profile_dir = self._profile_dir()
        for out_dir in escaping:
            # Precondition: it is genuinely outside the anchored boundary.
            self.assertNotEqual(out_dir.resolve(), anchor)
            self.assertNotIn(anchor, out_dir.resolve().parents)
            rc, out, _ = self._run(
                ["--json", "checklist", "--db", str(self.db),
                 "--out-dir", str(out_dir), "--profile", str(profile_dir)])
            self.assertEqual(rc, contract.EXIT_INVALID_INPUT,
                             f"{out_dir} must be rejected as invalid_input")
            obj = json.loads(out)
            self.assertIs(obj["ok"], False)
            self.assertEqual(obj["error"]["type"], "invalid_input")
            self.assertIsNone(obj["result"])
            self.assertFalse(out_dir.exists(), f"{out_dir} must not be created/written")

    def test_verdict_fail_is_ok_true_exit_1_no_write(self) -> None:
        """A gate-failing assembled answer → ok:true/verdict:"fail"/exit 1, NOTHING written."""
        out_dir = self._out_dir()
        profile_dir = self._profile_dir()
        # An uncited claim makes grounding.check_answer return verdict "fail".
        bad = {
            "question": "Personalized Layer-1 document checklist",
            "claims": [{"id": "c1", "text": "x", "citations": [], "quote": "z"}],
            "basis": [], "abstentions": [], "prose": "",
        }
        with mock.patch.object(checklist, "build_answer", return_value=bad):
            rc, out, _ = self._run(
                ["--json", "checklist", "--db", str(self.db),
                 "--out-dir", str(out_dir), "--profile", str(profile_dir)])
        self.assertEqual(rc, 1)
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)                   # verdict-fail is NOT an error
        self.assertIsNone(obj["error"])
        self.assertEqual(obj["result"]["verdict"], "fail")
        self.assertFalse(out_dir.exists())               # nothing rendered / written

    def test_non_file_db_is_invalid_input_exit_2(self) -> None:
        """A --db that is not a file → ok:false / invalid_input / exit 2."""
        profile_dir = self._profile_dir()
        rc, out, _ = self._run(
            ["--json", "checklist", "--db", "/no/such/db-26-03.db",
             "--out-dir", str(self._out_dir()), "--profile", str(profile_dir)])
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")
        self.assertIsNone(obj["result"])

    def test_missing_profile_is_invalid_input_exit_2(self) -> None:
        """A --profile dir with no profile.yaml → ProfileError → invalid_input / exit 2."""
        empty_dir = self._profile_dir(write=False)
        rc, out, _ = self._run(
            ["--json", "checklist", "--db", str(self.db),
             "--out-dir", str(self._out_dir()), "--profile", str(empty_dir)])
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")

    def test_non_mapping_profile_is_invalid_input_exit_2(self) -> None:
        """A profile.yaml that is not a mapping → ProfileError → invalid_input / exit 2."""
        root = Path(self._tmp.name) / "profile_root"
        root.mkdir(parents=True, exist_ok=True)
        (root / "profile.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
        rc, out, _ = self._run(
            ["--json", "checklist", "--db", str(self.db),
             "--out-dir", str(self._out_dir()), "--profile", str(root)])
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")

    def test_publish_unsafe_render_is_internal_error_exit_4_no_write(self) -> None:
        """A publish-safety hit in the rendered checklist → internal_error/exit 4, no write (SC3)."""
        out_dir = self._out_dir()
        profile_dir = self._profile_dir()
        # Stub the renderer to emit an abs-path line the RPT-03 scan MUST catch.
        with mock.patch(
                "crawler.grounding.render_answer",
                return_value="# leak\n\nsee /home/evil/secret for the key\n"):
            rc, out, _ = self._run(
                ["--json", "checklist", "--db", str(self.db),
                 "--out-dir", str(out_dir), "--profile", str(profile_dir)])
        self.assertEqual(rc, contract.EXIT_INTERNAL_ERROR)   # exit 4 (reused code)
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "internal_error")
        self.assertIn("refusing to write checklist", obj["error"]["message"])
        self.assertIsNone(obj["result"])
        self.assertFalse(out_dir.exists())                   # NOTHING written

    def test_json_stdout_is_pure_one_object(self) -> None:
        """stdout carries EXACTLY one parseable JSON object with command 'checklist'."""
        rc, out, err = self._run(
            ["--json", "checklist", "--db", str(self.db),
             "--out-dir", str(self._out_dir()), "--profile", str(self._profile_dir())])
        self.assertEqual(rc, 0)
        obj = json.loads(out)                            # must not raise
        self.assertEqual(obj["command"], "checklist")
        self.assertEqual(out.count("\n"), 1)
        self.assertNotIn("{", err)                       # no JSON leaked to stderr

    def test_emit_answer_prints_answer_and_writes_nothing(self) -> None:
        """--emit-answer prints the answer JSON to stdout and writes NOTHING (composability)."""
        out_dir = self._out_dir()
        profile_dir = self._profile_dir()
        rc, out, _ = self._run(
            ["--json", "checklist", "--db", str(self.db), "--emit-answer",
             "--out-dir", str(out_dir), "--profile", str(profile_dir)])
        self.assertEqual(rc, 0)
        answer = json.loads(out)                         # the raw answer object
        self.assertIn("claims", answer)
        self.assertIn("question", answer)
        self.assertFalse(out_dir.exists())               # nothing rendered / written

    def test_emit_answer_stdout_carries_no_basis_pii_still_grounds(self) -> None:
        """WR-02 (PII LEAK via the hatch): --emit-answer must NOT carry basis[] PII
        to unscanned/uncontained stdout, yet the emitted answer must still pipe
        into `ground` (claims[]+question, empty basis[]).

        FAILS on the old code: it printed the WHOLE answer, whose basis[] embeds
        the residence sentinels (Wakanda/Latveria).
        """
        out_dir = self._out_dir()
        # The example profile's basis[] embeds the residence sentinels.
        profile_dir = self._profile_dir(_example_profile())
        rc, out, _ = self._run(
            ["--json", "checklist", "--db", str(self.db), "--emit-answer",
             "--out-dir", str(out_dir), "--profile", str(profile_dir)])
        self.assertEqual(rc, 0)
        answer = json.loads(out)
        # Non-vacuous claims so the assertion is meaningful, and basis is redacted.
        self.assertTrue(answer["claims"])
        self.assertEqual(answer["basis"], [])
        # The HARD PII boundary: no sentinel residence token anywhere on stdout.
        for token in _SENTINEL_TOKENS:
            self.assertNotIn(token, out,
                             f"WR-02: PII {token!r} leaked to --emit-answer stdout")
        # Composability preserved: the emitted PII-free answer still grounds `pass`.
        report = grounding.check_answer(answer, self.db)
        self.assertEqual(report["verdict"], "pass", report.get("violations"))
        self.assertFalse(out_dir.exists())               # nothing rendered / written

    def _write_raw_profile(self, text: str) -> Path:
        """Write RAW (possibly malformed) profile.yaml bytes into a fresh dir."""
        root = Path(self._tmp.name) / "profile_root"
        root.mkdir(parents=True, exist_ok=True)
        (root / "profile.yaml").write_text(text, encoding="utf-8")
        return root

    # The PII sentinel that sits on the OFFENDING (syntactically broken) line.
    _SYNTAX_ERROR_PII = ("Maria", "Silva", "Portugal", "1990-05-03")
    _MALFORMED_PII_PROFILE = (
        "applicant:\n"
        "  citizenship: ok\n"
        "residence: Maria Silva lived in Portugal: 1990-05-03\n"
    )

    def test_malformed_profile_pii_never_reaches_json_stdout(self) -> None:
        """CR-01: a YAML syntax error in the personal profile must NOT echo the
        offending source line (PII) into the --json envelope on stdout/stderr.

        FAILS on the old code: load_profile interpolated str(YAMLError), whose
        snippet echoes the PII-bearing line straight into _fail's envelope.
        """
        profile_dir = self._write_raw_profile(self._MALFORMED_PII_PROFILE)
        rc, out, err = self._run(
            ["--json", "checklist", "--db", str(self.db),
             "--out-dir", str(self._out_dir()), "--profile", str(profile_dir)])
        # Contract: malformed personal input is invalid_input / exit 2.
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")
        self.assertIsNone(obj["result"])
        # The HARD PII boundary: no profile-derived byte on stdout OR stderr.
        for token in self._SYNTAX_ERROR_PII:
            self.assertNotIn(token, out,
                             f"CR-01: PII {token!r} leaked to --json stdout")
            self.assertNotIn(token, err,
                             f"CR-01: PII {token!r} leaked to stderr")

    def test_malformed_profile_pii_never_reaches_human_stderr(self) -> None:
        """CR-01: in human (non-json) mode the same syntax error must surface a
        GENERIC error on stderr — never the PII-bearing source snippet, exit 2."""
        profile_dir = self._write_raw_profile(self._MALFORMED_PII_PROFILE)
        rc, out, err = self._run(
            ["checklist", "--db", str(self.db),
             "--out-dir", str(self._out_dir()), "--profile", str(profile_dir)])
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        for token in self._SYNTAX_ERROR_PII:
            self.assertNotIn(token, out,
                             f"CR-01: PII {token!r} leaked to human stdout")
            self.assertNotIn(token, err,
                             f"CR-01: PII {token!r} leaked to human stderr")

    def test_mistyped_subsection_is_invalid_input_exit_2_no_traceback(self) -> None:
        """WR-01: a mis-typed sub-section (scalar where a mapping is expected) is
        invalid_input / exit 2 — NOT internal_error / exit 4 with a traceback, and
        no profile value leaks to stdout/stderr."""
        # `applicant: "Maria Silva"` — scalar PII where a sub-mapping is expected.
        profile_dir = self._write_raw_profile(
            "applicant: \"Maria Silva\"\nprogram:\n  stream: CEC\n")
        rc, out, err = self._run(
            ["--json", "checklist", "--db", str(self.db),
             "--out-dir", str(self._out_dir()), "--profile", str(profile_dir)])
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")
        self.assertIsNone(obj["result"])
        # No internal-crash signatures, no leaked profile value.
        self.assertNotIn("AttributeError", out)
        self.assertNotIn("AttributeError", err)
        self.assertNotIn("Traceback", err)
        for token in ("Maria", "Silva"):
            self.assertNotIn(token, out, f"WR-01: PII {token!r} leaked to stdout")
            self.assertNotIn(token, err, f"WR-01: PII {token!r} leaked to stderr")


# --------------------------------------------------------------------------- #
# Plan 03 ACCEPTANCE PROOF — the full PII boundary end-to-end (SC1, SC3, SC4):
#   (1) real-corpus integration over the TRACKED personal.example/profile.yaml
#       (@skipUnless — the live 742-doc index is git-ignored / local-only);
#   (2) RPT-03 publish-safe scan over the RENDERED checklist bytes (== []) + a
#       sentinel-PII rendered-bytes check (NOT skip-guarded — synthetic corpus);
#   (3) sentinel-PII self-scan over the TRACKED example profile (NOT skip-guarded);
#   (4) the personal/ tracked-tree fail-closed guard (NOT skip-guarded).
# Per RESEARCH lines 470-474 there is NO whole-tree `check_publish_safe exit 0`
# assertion (that reds on ~22 PRE-EXISTING unrelated ABS_PATH violations); every
# gate here is scoped to rendered bytes + the personal/ tracked-tree invariant.
# --------------------------------------------------------------------------- #
@unittest.skipUnless(_REAL_DB.is_file(), "real corpus/index.db not present")
class TestRealCorpusChecklist(unittest.TestCase):
    """Integration: the TRACKED example profile grounds against the LIVE index (SC1)."""

    def test_tracked_example_profile_grounds_pass_with_generic_citations(self) -> None:
        # Load the COMMITTED personal.example/profile.yaml (the public fixture) and
        # build + gate it against the real 742-doc index — the live SC1 proof.
        profile = checklist.load_profile(_EXAMPLE_PROFILE)
        answer = checklist.build_answer(profile, _REAL_DB)
        self.assertGreaterEqual(len(answer["claims"]), 1)
        report = grounding.check_answer(answer, _REAL_DB)
        self.assertEqual(report["verdict"], "pass", report.get("violations"))
        # Every citation relpath is GENERIC — none is a per-country police page that
        # would leak residence history (threat T-26-08).
        for claim in answer["claims"]:
            for cid in claim["citations"]:
                relpath = cid.split("#", 1)[0]
                self.assertFalse(
                    relpath.startswith("police-certificates/"),
                    f"residence leak: {claim['id']} cited {relpath!r}",
                )


class TestRenderedChecklistPublishSafe(_AssemblerCase):
    """RPT-03: the RENDERED checklist bytes scan clean and carry no sentinel PII (SC4)."""

    def test_rendered_bytes_scan_clean(self) -> None:
        answer = checklist.build_answer(_example_profile(), self.db)
        self.assertTrue(answer["claims"])               # guard: non-vacuous
        rendered = grounding.render_answer(answer, self.db)
        cps = _load_cps()
        violations = cps.scan_text("checklist.md", rendered)
        self.assertEqual(violations, [], [v.render() for v in violations])

    def test_no_sentinel_pii_in_rendered_bytes(self) -> None:
        # Belt-and-suspenders for SC4: profile PII lives ONLY in basis[] (never
        # rendered), so no sentinel residence token appears in the rendered bytes.
        answer = checklist.build_answer(_example_profile(), self.db)
        rendered = grounding.render_answer(answer, self.db)
        for token in _SENTINEL_TOKENS:
            self.assertNotIn(token, rendered,
                             f"sentinel PII {token!r} leaked into rendered checklist")


class TestExampleProfilePublishSafe(unittest.TestCase):
    """Share-safety self-scan over the TRACKED example profile (NOT skip-guarded, SC4)."""

    def test_example_profile_scans_clean_no_machine_paths(self) -> None:
        # The committed personal.example/profile.yaml is the phase's PII-leak surface
        # in the tracked tree; it MUST scan clean regardless of corpus presence.
        text = (_EXAMPLE_PROFILE / "profile.yaml").read_text(encoding="utf-8")
        cps = _load_cps()
        violations = cps.scan_text("personal.example/profile.yaml", text)
        self.assertEqual(violations, [], [v.render() for v in violations])
        # The sentinel COUNTRY names are intentionally present; the scan hunts
        # machine-path / project-venv leakage, which must be absent.
        for marker in ("/home/", "/Users/", "pr-ai-venv"):
            self.assertNotIn(marker, text)


class TestPersonalTrackedTree(unittest.TestCase):
    """The personal/ PII boundary: real tree empty, example tracked, CORPORA fail-closed (SC3)."""

    def _git(self, *args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), *args],
            check=True, capture_output=True, text=True,
        )
        return out.stdout

    def test_personal_dir_has_no_tracked_files(self) -> None:
        # No real PII ever enters the repo: the git-ignored personal/ tree is empty.
        self.assertEqual(self._git("ls-files", "personal/").strip(), "")

    def test_example_profile_is_tracked(self) -> None:
        # The synthetic example IS tracked (so users have a template to copy).
        self.assertTrue(self._git("ls-files", "personal.example/profile.yaml").strip())

    def test_corpora_prefix_fails_closed_with_tracked_corpora(self) -> None:
        # CORPORA_PREFIXES includes "personal/": any tracked path there fails closed.
        cps = _load_cps()
        violations = cps.scan_path_name("personal/whatever.yaml")
        self.assertTrue(violations)
        self.assertEqual({v.category for v in violations}, {"TRACKED_CORPORA"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
