"""CHK-03 conformance harness for the six CLI-agnostic document agents (Phase 27).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network, NO browser (per the
``crawler/tests/test_grounding.py`` / AGENTS.md convention). The whole proof rests on
the SHIPPED Phase-25 gate: the tracked fixture ``crawler/eval/document_agents.jsonl``
is fed through ``grounding.run_eval`` / ``grounding.check_answer`` exactly as the
``corpus-crawler --json ground --eval`` CLI would. Because the entire trust path is
the Python gate + shell ``search`` (there is NO CLI-native tooling), the same fixture
passing the same gate IS the per-CLI conformance proof (CHK-03 SC3).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_document_agents.py -q
    .venv/bin/python -m unittest crawler.tests.test_document_agents -v

Behaviour map:

    TestDocumentAgentsConformance — @skipUnless(corpus/index.db): run_eval failed==0,
        per-agent deterministic generic citations (no per-country police leak), the
        retrieve-what-you-cite proof (each agent's baked query + selection rule lands
        a chunk that grounds the quote it cites — WR-01), the employment letter's >=4
        #019 element claims pass, the confab line fails closed (quote_not_in_chunk),
        the must_abstain line carries zero claims, and rendered bytes are publish-safe
        (scan_text over rendered output ONLY — Pitfall 6).
    TestFixtureStructure   — ALWAYS runs: every line is well-formed JSON.
    TestFixturePublishSafety — ALWAYS runs: the tracked fixture self-scans clean.
    TestSkillsStaticGate   — ALWAYS runs: static grep gate over the six agent skills.
    TestGroundingGateLocalOnly — ALWAYS runs: asserts the grounding gate's skip wiring
        matches corpus presence and shouts a banner when the local-only gate is skipped
        (WR-02), so a corpus-less green is never mistaken for a grounding proof.
    TestDocumentAgentsConformanceSynthetic — ALWAYS runs (TD-CONFORMANCE-CORPUS-GATED):
        proves the document-agent grounding LOOP end-to-end against a SYNTHETIC tempdir
        index (searchindex.resolve + the gate + run_eval over agent-style grounded /
        confabulated(expect:ungrounded) / must_abstain answer objects), so a corpus-less
        CI run still proves the loop works — not just static structure. The real-corpus
        class above remains the content-accuracy check (it grounds against real IRCC
        chunks like #019, which ship only in the git-ignored corpus).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

from crawler import checklist, grounding, searchindex
from crawler.tests.test_searchindex import _make_index_corpus

# Repo-root-relative paths (this suite runs from the repo root, per AGENTS.md).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = Path("crawler/eval/document_agents.jsonl")
_REAL_DB = Path("corpus/index.db")
_SKILLS_DIR = Path("skills/document-agents")

# The canonical employment proof-of-work-experience letter chunk (NOT the
# arranged-employment job-offer letter): one generic IRCC manual page, no PII.
# All four employment element claims cite ...completeness-check.md#019.
_EMPLOYMENT_RELPATH = (
    "pr-pdi/express-entry-applications-received-on-after-january-1-2016-"
    "completeness-check.md"
)
_EMPLOYMENT_ID = _EMPLOYMENT_RELPATH + "#019"

# The completeness-check PDI is the single authoritative e-APR document checklist;
# the employment letter and every "completeness-check" document agent below cite a
# chunk of it. Alias for readability in the registries.
_COMPLETENESS_RELPATH = _EMPLOYMENT_RELPATH

# Each grounded agent line MUST resolve to its expected GENERIC citation family
# (the deterministic per-CLI conformance assertion, SC3/SC4). Keyed by fixture id.
_EXPECTED_FAMILY = {
    "police-certificate-who-01": "guidance/police-certificates.md",
    "language-test-approved-01": "guidance/language-test.md",
    "eca-authenticity-01": "eca/educational-credential-assessment.md",
    "proof-of-funds-equity-01": "guidance/proof-funds.md",
    "medical-ime-exemption-01": "medical/requirements-permanent-residents.md",
    "employment-reference-letter-01": _EMPLOYMENT_RELPATH,
    # Express Entry e-APR completeness-check document agents (all cite the same PDI).
    "passport-biographical-page-01": _COMPLETENESS_RELPATH,
    "job-offer-arranged-employment-01": _COMPLETENESS_RELPATH,
    "proof-of-studies-credentials-01": _COMPLETENESS_RELPATH,
    "certificate-of-qualification-01": _COMPLETENESS_RELPATH,
    "birth-certificate-dependent-01": _COMPLETENESS_RELPATH,
    "marriage-certificate-married-01": _COMPLETENESS_RELPATH,
    "common-law-union-cohabitation-01": _COMPLETENESS_RELPATH,
    "divorce-certificate-divorced-01": _COMPLETENESS_RELPATH,
    "death-certificate-widowed-01": _COMPLETENESS_RELPATH,
    "adoption-certificate-adopted-01": _COMPLETENESS_RELPATH,
    "relative-in-canada-points-01": _COMPLETENESS_RELPATH,
    "digital-photos-identity-01": _COMPLETENESS_RELPATH,
    "other-name-alias-01": _COMPLETENESS_RELPATH,
    "use-of-representative-01": _COMPLETENESS_RELPATH,
    "authority-to-release-01": _COMPLETENESS_RELPATH,
    "translation-certified-01": _COMPLETENESS_RELPATH,
}

# The agent skills (the static-gate target). _contract.md + README.md are
# shared scaffolding and are checked separately, NOT as agents.
_AGENT_SKILLS = (
    "police-certificate.md",
    "language-test.md",
    "eca.md",
    "proof-of-funds.md",
    "medical.md",
    "employment-reference-letter.md",
    "passport.md",
    "job-offer.md",
    "proof-of-studies.md",
    "certificate-of-qualification.md",
    "birth-certificate.md",
    "marriage-certificate.md",
    "common-law-union.md",
    "divorce-certificate.md",
    "death-certificate.md",
    "adoption-certificate.md",
    "relative-in-canada.md",
    "digital-photos.md",
    "other-name.md",
    "use-of-representative.md",
    "authority-to-release.md",
    "translation.md",
    "letter-of-explanation.md",
)

# WR-01 — the retrieve-what-you-cite registry. For each agent: the baked
# ``--json search`` query it actually runs (which MUST equal the skill's baked-query
# blockquote — asserted below, closing skill<->harness), the optional ``--family``
# filter, and the DOCUMENTED selection rule from its worked example. This is what
# ``test_per_agent_retrieves_what_it_cites`` drives so the suite proves the agents
# retrieve the chunk they cite — not merely that a hand-coded fixture citation
# resolves (the gap that let CR-01/CR-02 stay green).
#
# Selection rules (mirroring each skill's worked example):
#   first            — take hits[0] (top BM25 hit).
#   first_not_arranged — hits[0], asserted NOT an arranged-employment job-offer id.
#   skip_country     — skip any police-certificates/<country> relpath (the residence
#                      no-leak backstop) and take the first generic hit.
#   contains_marker  — scan the top hits, resolve each, and take the FIRST whose
#                      chunk text contains the structural requirement span. NEVER
#                      blindly take hits[0] (the CR-01/CR-02 grounding-by-construction
#                      rule); the marker is a non-volatile requirement phrase.
_AGENT_RETRIEVAL = {
    "police-certificate.md": {
        "query": "police certificate every country",
        "family": "guidance",
        "rule": "skip_country",
        "marker": None,
        "fixture_id": "police-certificate-who-01",
    },
    "language-test.md": {
        "query": "language test approved results",
        "family": None,
        "rule": "first",
        "marker": None,
        "fixture_id": "language-test-approved-01",
    },
    "eca.md": {
        "query": "foreign educational credential assessment",
        "family": None,
        "rule": "first",
        "marker": None,
        "fixture_id": "eca-authenticity-01",
    },
    "proof-of-funds.md": {
        "query": "proof settlement funds",
        "family": None,
        "rule": "contains_marker",
        "marker": "equity on real property",
        "fixture_id": "proof-of-funds-equity-01",
    },
    "medical.md": {
        "query": "immigration medical examination permanent residence",
        "family": None,
        "rule": "contains_marker",
        "marker": "temporary public policy",
        "fixture_id": "medical-ime-exemption-01",
    },
    "employment-reference-letter.md": {
        "query": "reference letter company letterhead",
        "family": None,
        "rule": "first_not_arranged",
        "marker": None,
        "fixture_id": "employment-reference-letter-01",
    },
    # Express Entry e-APR completeness-check document agents. Each bakes a 2–4 token
    # query and selects via a `contains_marker` rule (resolve hits in BM25 order; take
    # the first whose text contains the non-volatile requirement marker), landing the
    # document-requirements chunk it cites.
    "passport.md": {
        "query": "biographical data page passport",
        "family": None,
        "rule": "contains_marker",
        "marker": "biographical data page of a passport",
        "fixture_id": "passport-biographical-page-01",
    },
    "job-offer.md": {
        "query": "qualifying offer arranged employment letter",
        "family": None,
        "rule": "contains_marker",
        "marker": "A letter from the employer(s) offering the job in Canada is required",
        "fixture_id": "job-offer-arranged-employment-01",
    },
    "proof-of-studies.md": {
        "query": "proof completed education transcripts",
        "family": None,
        "rule": "contains_marker",
        "marker": "Proof of completed Canadian or foreign educational credentials",
        "fixture_id": "proof-of-studies-credentials-01",
    },
    "certificate-of-qualification.md": {
        "query": "provincial territorial certificate qualification",
        "family": None,
        "rule": "contains_marker",
        "marker": "A copy of the certificate of qualification is required",
        "fixture_id": "certificate-of-qualification-01",
    },
    "birth-certificate.md": {
        "query": "birth certificate dependent children",
        "family": None,
        "rule": "contains_marker",
        "marker": "equivalent document from the birth country",
        "fixture_id": "birth-certificate-dependent-01",
    },
    "marriage-certificate.md": {
        "query": "marriage certificate married status",
        "family": None,
        "rule": "contains_marker",
        "marker": "marital status is listed as married",
        "fixture_id": "marriage-certificate-married-01",
    },
    "common-law-union.md": {
        "query": "common-law union cohabitation evidence",
        "family": None,
        "rule": "contains_marker",
        "marker": "Statutory Declaration of Common-Law Union",
        "fixture_id": "common-law-union-cohabitation-01",
    },
    "divorce-certificate.md": {
        "query": "divorce certificate separation agreement",
        "family": None,
        "rule": "contains_marker",
        "marker": "legal separation agreement must be provided",
        "fixture_id": "divorce-certificate-divorced-01",
    },
    "death-certificate.md": {
        "query": "death certificate widowed status",
        "family": None,
        "rule": "contains_marker",
        "marker": "marital status is listed as widowed",
        "fixture_id": "death-certificate-widowed-01",
    },
    "adoption-certificate.md": {
        "query": "adoption certificate adopted child",
        "family": None,
        "rule": "contains_marker",
        "marker": "dependent child status is listed as adopted",
        "fixture_id": "adoption-certificate-adopted-01",
    },
    "relative-in-canada.md": {
        "query": "relative Canada citizen permanent resident",
        "family": None,
        "rule": "contains_marker",
        "marker": "family member in Canada who is a permanent resident",
        "fixture_id": "relative-in-canada-points-01",
    },
    "digital-photos.md": {
        "query": "digital photos permanent resident card",
        "family": None,
        "rule": "contains_marker",
        "marker": "permanent resident card photo specifications",
        "fixture_id": "digital-photos-identity-01",
    },
    "other-name.md": {
        "query": "used another name maiden",
        "family": None,
        "rule": "contains_marker",
        "marker": "having used another name",
        "fixture_id": "other-name-alias-01",
    },
    "use-of-representative.md": {
        "query": "using representative consultant portal",
        "family": None,
        "rule": "contains_marker",
        "marker": "they are using a representative",
        "fixture_id": "use-of-representative-01",
    },
    "authority-to-release.md": {
        "query": "authority release personal information designated",
        "family": None,
        "rule": "contains_marker",
        "marker": "designate an individual",
        "fixture_id": "authority-to-release-01",
    },
    "translation.md": {
        "query": "translation certified translator affidavit",
        "family": None,
        "rule": "contains_marker",
        "marker": "The translation package should include a copy the original source document",
        "fixture_id": "translation-certified-01",
    },
}

# Each skill states its baked query as a single-line blockquote: ``> `…```` under
# the "The baked query" heading. Match a blockquote whose entire content is one
# backtick-wrapped token (so prose callouts like ``> Copy the quote VERBATIM…`` do
# NOT match).
_BAKED_QUERY_RE = re.compile(r"^>\s+`([^`\n]+)`\s*$", re.MULTILINE)
_SEARCH_QUERY_RE = re.compile(
    r'corpus-crawler\s+--json\s+search\s+"([^"\n]+)"'
)


def _extract_baked_query(skill_path: Path) -> str:
    """Pull the agent's baked ``--json search`` query out of its skill .md.

    Extracting the query from the .md (rather than trusting the registry) is what
    closes the skill<->harness loop: if an author retunes the baked query in the
    skill without updating ``_AGENT_RETRIEVAL``, the equality assertion in
    ``test_per_agent_retrieves_what_it_cites`` trips.
    """
    text = skill_path.read_text(encoding="utf-8")
    matches = _BAKED_QUERY_RE.findall(text)
    if not matches:
        matches = _SEARCH_QUERY_RE.findall(text)
    assert matches, f"no baked-query blockquote found in {skill_path}"
    return matches[0]


def _apply_selection_rule(db: Path, spec: dict) -> str | None:
    """Reproduce a skill's documented selection rule against the live index.

    Returns the selected ``chunk_id`` (the chunk the agent would resolve + cite), or
    ``None`` if the rule abstains. Mirrors the worked example in each skill .md so the
    harness exercises the agent's OWN retrieval path.
    """
    hits = searchindex.search(db, spec["query"], limit=5, family=spec["family"])["hits"]
    rule = spec["rule"]
    if rule in ("first", "first_not_arranged"):
        return hits[0]["chunk_id"] if hits else None
    if rule == "skip_country":
        generic = [
            h for h in hits if not h["chunk_id"].startswith("police-certificates/")
        ]
        return generic[0]["chunk_id"] if generic else None
    if rule == "contains_marker":
        for h in hits:
            chunk = searchindex.resolve(db, h["chunk_id"])
            if chunk and spec["marker"] in chunk["text"]:
                return h["chunk_id"]
        return None
    raise AssertionError(f"unknown selection rule {rule!r}")


def _load_cps():
    """Import scripts/check_publish_safe (scripts/ is NOT a package → sys.path shim).

    Mirrors test_checklist._load_cps / test_grounding.TestFixturePublishSafety — the
    shipped SAFE-02 publish-safety scanner is reused (NEVER re-implemented) so the
    self-scan asserts against the exact bytes the CLI write-gate scans.
    """
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # SAFE-02 share-safety scanner

    return cps


def _fixture_records() -> list[dict]:
    """Parse every non-blank fixture line into a stored-answer dict."""
    return [
        json.loads(ln)
        for ln in _FIXTURE.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def _is_grounded_line(rec: dict) -> bool:
    """True iff *rec* is a positive grounded example (not confab, not abstain)."""
    return (not rec.get("must_abstain")) and rec.get("expect", "grounded") in (
        "grounded",
        "pass",
    )


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY GROUNDING GATE: corpus/index.db is git-ignored and absent — the "
    "end-to-end grounding proof did NOT run; a green suite here is STRUCTURAL ONLY",
)
class TestDocumentAgentsConformance(unittest.TestCase):
    """End-to-end: every example answer passes the SHIPPED gate against the live index.

    This @skipUnless class is the per-CLI conformance proof (CHK-03 SC3): the same
    fixture passing the same ``grounding.run_eval`` gate that ``corpus-crawler --json
    ground --eval`` runs proves identical behaviour across CLIs — the entire trust
    path is the Python gate + shell ``search``, with NO CLI-native tooling.
    """

    def test_run_eval_grounds_clean(self) -> None:
        # (a) The "same fixture passes the same gate" proof (SC3).
        summary, code = grounding.run_eval(_REAL_DB, _FIXTURE)
        self.assertEqual(set(summary), {"total", "passed", "failed", "failures"})
        self.assertEqual(summary["failed"], 0, summary["failures"])
        self.assertEqual(code, 0)
        self.assertGreaterEqual(summary["total"], 8)
        self.assertEqual(summary["passed"], summary["total"])

    def test_per_agent_deterministic_generic_citations(self) -> None:
        # (b) Each grounded line resolves to its expected GENERIC family, and NO
        # citation is a per-country police page (SC4 no-leak backstop).
        for rec in _fixture_records():
            if not _is_grounded_line(rec):
                continue
            expected = _EXPECTED_FAMILY.get(rec["id"])
            self.assertIsNotNone(
                expected, f"unexpected grounded line id {rec['id']!r}"
            )
            for claim in rec["claims"]:
                for cid in claim["citations"]:
                    chunk = searchindex.resolve(_REAL_DB, cid)
                    self.assertIsNotNone(
                        chunk, f"{rec['id']}: citation {cid!r} did not resolve"
                    )
                    self.assertEqual(
                        chunk["relpath"],
                        expected,
                        f"{rec['id']}: {cid!r} resolved to {chunk['relpath']!r}, "
                        f"expected family {expected!r}",
                    )
                    self.assertFalse(
                        checklist._is_country_specific(chunk["relpath"]),
                        f"residence leak: {rec['id']} cited {chunk['relpath']!r}",
                    )

    def test_per_agent_retrieves_what_it_cites(self) -> None:
        # (b2) WR-01: the retrieve-what-you-cite proof. For EACH agent, re-run its
        # baked query + DOCUMENTED selection rule against the LIVE index and prove the
        # chunk it would actually select GROUNDS every quote it cites — closing the
        # skill<->fixture<->index loop. This is the assertion the suite previously
        # lacked, which is exactly why CR-01 (medical) and CR-02 (proof-of-funds)
        # sailed through green: the fixture hand-coded the correct chunk while the
        # skills steered the agent to the wrong one, and nothing reconciled the two.
        records = {r["id"]: r for r in _fixture_records()}
        for skill_name, spec in _AGENT_RETRIEVAL.items():
            with self.subTest(agent=skill_name):
                # (1) the registry query MUST equal the skill's baked query (sync guard).
                baked = _extract_baked_query(_SKILLS_DIR / skill_name)
                self.assertEqual(
                    baked, spec["query"],
                    f"{skill_name}: baked query {baked!r} != harness query "
                    f"{spec['query']!r} — retune the harness or the skill in lockstep",
                )
                # (2) apply the skill's documented selection rule against the live index.
                selected = _apply_selection_rule(_REAL_DB, spec)
                self.assertIsNotNone(
                    selected,
                    f"{skill_name}: selection rule abstained on an answerable question",
                )
                if spec["rule"] == "first_not_arranged":
                    self.assertNotIn(
                        "arranged-employment", selected,
                        f"{skill_name}: landed an arranged-employment job-offer chunk "
                        f"{selected!r} (wrong document type)",
                    )
                # (3) the selected chunk MUST be the chunk the agent would cite — i.e. it
                # AGREES with the fixture's hand-coded citation (skill<->fixture closure).
                rec = records[spec["fixture_id"]]
                cited = {c for claim in rec["claims"] for c in claim["citations"]}
                self.assertIn(
                    selected, cited,
                    f"{skill_name}: selection {selected!r} is not among the fixture "
                    f"citations {sorted(cited)} — the skill steers to a different chunk "
                    f"than it cites",
                )
                # (4) GROUNDING-BY-CONSTRUCTION: re-point every claim that cites this
                # chunk at the RETRIEVED chunk and run the SHIPPED gate. A pass proves
                # the agent's OWN retrieval lands a chunk that verbatim-grounds every
                # quote it would cite — not just that a hand-coded citation resolves.
                probe = {
                    "question": rec["question"],
                    "claims": [
                        {**claim, "citations": [selected]}
                        for claim in rec["claims"]
                        if selected in claim["citations"]
                    ],
                    "basis": [],
                    "abstentions": [],
                    "prose": "",
                }
                verdict = grounding.check_answer(probe, _REAL_DB)
                self.assertEqual(
                    verdict["verdict"], "pass",
                    f"{skill_name}: retrieved chunk {selected!r} does NOT ground its "
                    f"cited quote(s): {verdict['violations']}",
                )
                self.assertGreaterEqual(verdict["grounded"], 1)
        # (c) The employment-reference line carries >=4 grounded element claims, ALL
        # citing the #019 completeness-check relpath, and check_answer = "pass" (SC4).
        rec = next(
            r for r in _fixture_records() if r["id"] == "employment-reference-letter-01"
        )
        self.assertGreaterEqual(len(rec["claims"]), 4)
        for claim in rec["claims"]:
            self.assertIn(_EMPLOYMENT_ID, claim["citations"])
            chunk = searchindex.resolve(_REAL_DB, _EMPLOYMENT_ID)
            self.assertIsNotNone(chunk)
            self.assertEqual(chunk["relpath"], _EMPLOYMENT_RELPATH)
        verdict = grounding.check_answer(rec, _REAL_DB)
        self.assertEqual(verdict["verdict"], "pass", verdict["violations"])
        self.assertGreaterEqual(verdict["grounded"], 4)

    def test_confabulation_line_fails_closed(self) -> None:
        # (d) The confab line is REJECTED by the gate: verdict fail, reason
        # quote_not_in_chunk (fail-closed regression lock, SC2).
        rec = next(
            r for r in _fixture_records() if r["id"] == "employment-confab-notarized-01"
        )
        verdict = grounding.check_answer(rec, _REAL_DB)
        self.assertEqual(verdict["verdict"], "fail")
        self.assertEqual(verdict["violations"][0]["reasons"], ["quote_not_in_chunk"])

    def test_must_abstain_line_has_zero_claims(self) -> None:
        # (e) The must_abstain line passes only as a zero-claim abstention (SC2).
        rec = next(
            r for r in _fixture_records() if r["id"] == "abstain-fictional-document-01"
        )
        self.assertTrue(rec.get("must_abstain"))
        self.assertEqual(rec.get("claims"), [])

    def test_rendered_bytes_are_publish_safe(self) -> None:
        # (f) Render each grounded line and scan ONLY the rendered bytes — NEVER a
        # whole-tree scan (Pitfall 6, T-27-14).
        cps = _load_cps()
        for rec in _fixture_records():
            if not _is_grounded_line(rec):
                continue
            rendered = grounding.render_answer(rec, _REAL_DB)
            violations = cps.scan_text(f"rendered::{rec['id']}", rendered)
            self.assertEqual(
                violations, [], [v.render() for v in violations]
            )


class TestFixtureStructure(unittest.TestCase):
    """Structural invariants over the tracked fixture (NOT skip-guarded).

    Every line parses as JSON; every non-abstain line carries a ``question`` and a
    ``claims`` list whose entries each have ``id``/``text``/``citations``/``quote``;
    every ``must_abstain:true`` line carries an EMPTY ``claims[]``.
    """

    def test_every_line_is_well_formed(self) -> None:
        records = _fixture_records()
        self.assertGreaterEqual(len(records), 8)  # 6 agents + confab + must_abstain

        grounded = 0
        abstain = 0
        confab = 0
        for rec in records:
            self.assertIn("question", rec)
            if rec.get("must_abstain"):
                abstain += 1
                self.assertEqual(
                    rec.get("claims"), [],
                    f"must_abstain line {rec.get('id')!r} carries claims",
                )
                continue
            self.assertIsInstance(rec.get("claims"), list)
            self.assertGreaterEqual(len(rec["claims"]), 1)
            for claim in rec["claims"]:
                for key in ("id", "text", "citations", "quote"):
                    self.assertIn(key, claim, f"{rec.get('id')!r} claim missing {key}")
                self.assertIsInstance(claim["citations"], list)
                self.assertGreaterEqual(len(claim["citations"]), 1)
                self.assertIsInstance(claim["quote"], str)
                self.assertTrue(claim["quote"].strip())
            if rec.get("expect") in ("ungrounded", "fail"):
                confab += 1
            else:
                grounded += 1

        self.assertGreaterEqual(grounded, 6)  # the six agent example answers
        self.assertGreaterEqual(confab, 1)    # >=1 adversarial confabulation line
        self.assertGreaterEqual(abstain, 1)   # >=1 must_abstain line


class TestFixturePublishSafety(unittest.TestCase):
    """PII / share-safety self-scan over the TRACKED fixture bytes (T-27-14).

    NOT skip-guarded — the fixture is committed regardless of corpus presence, so this
    share-safety gate MUST always run. Reuses the shipped ``check_publish_safe.scan_text``
    (SAFE-02) plus a raw-substring check for machine-path PII markers.
    """

    def test_fixture_pii_self_scan_is_clean(self) -> None:
        text = _FIXTURE.read_text(encoding="utf-8")
        cps = _load_cps()
        violations = cps.scan_text(str(_FIXTURE), text)
        self.assertEqual(violations, [], [v.render() for v in violations])

        # Belt-and-suspenders: no machine-path / project-venv markers anywhere.
        for marker in ("/home/", "/Users/", "pr-ai-venv"):
            self.assertNotIn(marker, text)

    def test_no_per_country_police_citation(self) -> None:
        # SC4 no-leak: the police line cites the GENERIC guidance page, never a
        # police-certificates/<country>.md relpath whose path discloses residence.
        text = _FIXTURE.read_text(encoding="utf-8")
        self.assertNotIn("police-certificates/", text)


class TestGroundingGateLocalOnly(unittest.TestCase):
    """ALWAYS runs: makes the grounding gate's local-only nature loud & explicit (WR-02).

    The end-to-end grounding proof (``TestDocumentAgentsConformance``) is
    ``@skipUnless`` the git-ignored ``corpus/index.db``. On CI / a fresh clone the DB
    is ABSENT, so that proof is KNOWINGLY skipped and the suite's green is STRUCTURAL
    ONLY — never a grounding proof. This always-run guard asserts the skip wiring
    matches corpus presence in BOTH directions and emits a LOUD, on-the-record banner
    when the gate is skipped, so a corpus-less green run can never be mistaken for the
    grounding proof. We do NOT ship the corpus to "fix" this — the corpus stays
    local-only; we only make the skip impossible to overlook.
    """

    def test_skip_wiring_matches_corpus_presence(self) -> None:
        present = _REAL_DB.is_file()
        skipped = bool(getattr(TestDocumentAgentsConformance, "__unittest_skip__", False))
        if present:
            # Corpus present: the gate is LIVE and must NOT be skip-marked.
            self.assertFalse(
                skipped,
                "corpus/index.db is present but the grounding gate is marked skipped",
            )
        else:
            # Corpus absent: the gate MUST be skip-guarded (never a silent 'pass'),
            # and we shout so the missing grounding proof is impossible to miss.
            self.assertTrue(
                skipped,
                "corpus/index.db absent but the grounding gate is NOT skip-guarded — "
                "a corpus-less run would falsely advertise a grounding proof",
            )
            sys.stderr.write(
                "\n"
                "================================================================\n"
                "[document-agents] LOCAL-ONLY GROUNDING GATE SKIPPED\n"
                "  corpus/index.db is absent (git-ignored, local-only).\n"
                "  The end-to-end grounding proof did NOT run; this suite's\n"
                "  green is a STRUCTURAL pass ONLY, not a grounding proof.\n"
                "  Build the corpus locally, then:\n"
                "    .venv/bin/python -m pytest "
                "crawler/tests/test_document_agents.py -q\n"
                "================================================================\n"
            )
            # Also raise a warning so the missing grounding proof surfaces in
            # pytest's default end-of-run warnings summary, not only with -rs / -s.
            warnings.warn(
                "document-agents grounding gate SKIPPED: corpus/index.db absent — "
                "structural pass only, NOT a grounding proof",
                RuntimeWarning,
                stacklevel=2,
            )


class TestSkillsStaticGate(unittest.TestCase):
    """Static grep gate over the six document-agent skills (NOT skip-guarded, T-27-16).

    A pure static guard — runs regardless of corpus presence. It proves no agent skill
    carries proprietary front-matter, bakes a chunk_id, inlines a volatile value
    (dollar amount / calendar year / validity window), or uses bare-python; and that
    every agent links to ``_contract.md``. The employment agent additionally carries
    the do-not-confuse-with-the-job-offer-letter guard (SC1/SC4).
    """

    # Volatile-value patterns. The calendar-year pattern deliberately EXCLUDES Unicode
    # codepoint references such as ``U+2019`` (the curly-apostrophe hazard eca.md
    # documents per plan-check W1) via a negative look-behind — a codepoint reference
    # is documentation of an encoding hazard, NOT an inlined requirement value.
    _CHUNK_ID = re.compile(r"#[0-9]{3}")
    _DOLLAR = re.compile(r"\$[0-9]")
    _YEAR = re.compile(r"(?<![A-Za-z0-9+])(?:19|20)[0-9]{2}(?![0-9])")
    _DURATION = re.compile(r"\b[0-9]+ (?:years|months|days|hours)\b")
    # a bare `python` call: matches `python` NOT preceded by `.`, `/`, or an
    # alphanumeric (so `.venv/bin/python` and `corpus-crawler` are allowed; an
    # unqualified `python` is not).
    _BARE_PYTHON = re.compile(r"(?:^|[^./0-9A-Za-z])python(?: |$)", re.MULTILINE)

    def _agent_paths(self) -> list[Path]:
        return [_SKILLS_DIR / name for name in _AGENT_SKILLS]

    def test_expected_skill_file_set(self) -> None:
        # skills/document-agents/ holds _contract.md + README.md + every agent in
        # _AGENT_SKILLS. Derive the expected set from the registry (do NOT hardcode a
        # count) so adding an agent is a one-line registry change.
        present = sorted(p.name for p in _SKILLS_DIR.glob("*.md"))
        expected = sorted(("_contract.md", "README.md", *_AGENT_SKILLS))
        self.assertEqual(present, expected)
        for p in self._agent_paths():
            self.assertTrue(p.is_file(), f"missing agent skill {p}")

    def test_no_proprietary_front_matter(self) -> None:
        # No agent file may START with a line that is exactly `---` (front-matter
        # fence). A mid-document horizontal rule is fine; only the first line matters.
        for p in self._agent_paths():
            first = p.read_text(encoding="utf-8").splitlines()[0].strip()
            self.assertNotEqual(
                first, "---", f"{p.name} opens with proprietary front-matter"
            )

    def test_no_baked_chunk_id(self) -> None:
        # Agents bake a QUERY, not a volatile chunk_id (#NNN drifts with the corpus).
        for p in self._agent_paths():
            hits = self._CHUNK_ID.findall(p.read_text(encoding="utf-8"))
            self.assertEqual(hits, [], f"{p.name} bakes a chunk_id: {hits}")

    def test_no_inlined_volatile_values(self) -> None:
        # No inlined dollar amounts / calendar years / validity windows — those are
        # runtime-quoted from the corpus, never frozen into spec prose (Pitfall 2).
        for p in self._agent_paths():
            text = p.read_text(encoding="utf-8")
            self.assertEqual(self._DOLLAR.findall(text), [],
                             f"{p.name} inlines a dollar amount")
            self.assertEqual(self._YEAR.findall(text), [],
                             f"{p.name} inlines a calendar year")
            self.assertEqual(self._DURATION.findall(text), [],
                             f"{p.name} inlines a validity window")

    def test_no_bare_python(self) -> None:
        # Every example uses `.venv/bin/python` or `corpus-crawler`, never bare-python.
        for p in self._agent_paths():
            hits = [m.group(0) for m in self._BARE_PYTHON.finditer(
                p.read_text(encoding="utf-8"))]
            self.assertEqual(hits, [], f"{p.name} invokes bare-python: {hits}")

    def test_each_agent_links_contract(self) -> None:
        for p in self._agent_paths():
            self.assertIn(
                "_contract.md", p.read_text(encoding="utf-8"),
                f"{p.name} does not link the shared _contract.md",
            )

    def test_employment_guards_against_job_offer_letter(self) -> None:
        # The employment agent cites the proof-of-WORK-EXPERIENCE letter (#019), NOT
        # the arranged-employment job-offer letter — it must say so explicitly.
        text = (_SKILLS_DIR / "employment-reference-letter.md").read_text(
            encoding="utf-8")
        self.assertRegex(text, re.compile(r"job.?offer|arranged.?employment",
                                          re.IGNORECASE))


class TestDocumentAgentsConformanceSynthetic(unittest.TestCase):
    """ALWAYS-RUNS CI proof of the document-agent grounding LOOP (TD-CONFORMANCE-CORPUS-GATED).

    ``TestDocumentAgentsConformance`` above is ``@skipUnless(corpus/index.db)`` because the
    six agents cite REAL IRCC chunks (e.g. the employment letter's ``...#019``) that ship
    only in the git-ignored, local-only corpus — so on CI / a fresh clone it skips and the
    actual grounding never executes. This class closes that gap: it exercises the SAME
    machinery the agents rely on — ``searchindex.resolve`` + the ``grounding`` gate +
    ``run_eval`` over agent-style answer objects (a grounded line, a confabulated
    ``expect:"ungrounded"`` line, and a ``must_abstain`` line) — end-to-end against a
    SYNTHETIC index built into a ``TemporaryDirectory`` (NEVER the real ``corpus/``). It
    therefore RUNS in CI and proves the loop mechanism works, while the real-corpus class
    remains the content-accuracy check for the actual citations.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
        # The DB lives in the tempdir — NEVER under the real git-ignored corpus/.
        self.db = Path(self._tmp.name) / "index.db"
        searchindex.build_index(self.root, self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _known_row(self) -> tuple[str, str]:
        """A real ``(chunk_id, text)`` straight from the synthetic ``chunks`` table."""
        con = sqlite3.connect(str(self.db))
        try:
            return con.execute(
                "SELECT chunk_id, text FROM chunks "
                "WHERE relpath = 'pr-pdi/tiny.md' LIMIT 1"
            ).fetchone()
        finally:
            con.close()

    def _write_jsonl(self, records: list[dict]) -> Path:
        path = Path(self._tmp.name) / "agents.jsonl"
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
        )
        return path

    def test_synthetic_agent_loop_grounds_clean(self) -> None:
        """The agent answer-object mix (grounded + confab + abstain) passes the harness."""
        chunk_id, text = self._known_row()
        quote = text[:60]  # a VERBATIM span of the resolved chunk → verdict pass
        grounded = {
            "id": "synthetic-doc-agent",
            "question": "Which document elements are required?",
            "claims": [{
                "id": "c1",
                "text": "A required element is documented.",
                "citations": [chunk_id],
                "quote": quote,
            }],
            "basis": [], "abstentions": [], "prose": "",
        }
        confab = {  # expect:ungrounded → PASSES iff the gate REJECTS it (fail-closed)
            "id": "synthetic-confab", "expect": "ungrounded",
            "question": "A fabricated element?",
            "claims": [{
                "id": "c1",
                "text": "A confabulated requirement.",
                "citations": [chunk_id],
                "quote": "this span is definitely not in the chunk zzz",
            }],
            "basis": [], "abstentions": [], "prose": "",
        }
        abstain = {  # must_abstain → PASSES iff it carries zero claims
            "id": "synthetic-abstain", "must_abstain": True,
            "question": "Something not in the corpus?",
            "claims": [], "basis": [], "abstentions": ["not_in_corpus"], "prose": "",
        }
        summary, code = grounding.run_eval(
            self.db, self._write_jsonl([grounded, confab, abstain])
        )
        self.assertEqual(set(summary), {"total", "passed", "failed", "failures"})
        self.assertEqual(summary["failed"], 0, summary["failures"])
        self.assertEqual(code, 0)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["passed"], 3)

    def test_synthetic_confabulation_fails_closed(self) -> None:
        """A confabulated quote with NO expect marker must FAIL the gate (verdict fail)."""
        chunk_id, _ = self._known_row()
        confab = {
            "id": "c", "question": "q",
            "claims": [{
                "id": "c1", "text": "x", "citations": [chunk_id],
                "quote": "definitely not a substring of the chunk zzz",
            }],
            "basis": [], "abstentions": [], "prose": "",
        }
        summary, code = grounding.run_eval(self.db, self._write_jsonl([confab]))
        self.assertEqual(summary["failed"], 1, summary)
        self.assertEqual(code, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
