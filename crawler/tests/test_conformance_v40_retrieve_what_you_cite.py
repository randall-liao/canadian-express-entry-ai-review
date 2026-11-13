"""SAFE-03 authoritative retrieve-what-you-cite conformance gate (Phase 34 — Plan 03).

The v4.0 release-gate proof that **FTS5 lexical match is disciplined into
correct-authority selection**: every registry rule grounds the INTENDED current
rule — not a historical, adjacent, or wrong-family chunk. It consolidates and
strengthens the Phase-31 retrieve-what-you-cite proofs into ONE clearly-labeled
module that:

* (a) re-selects and grounds EVERY non-gap rule across all four YAML groups
  against the REAL ``corpus/index.db`` (positive), asserts coverage is
  complete-or-documented-gaps, the committed COVERAGE.md is not stale, and the
  static no-inlined-volatile gate is clean; and
* (b) adds explicit NEGATIVE CONTROLS — wrong-family / historical-superseded
  (deny_families) / adjacent-missing-marker — proving the source-family
  allow/deny + marker selection actually BITES (each control is non-vacuous: a
  blind ``hits[0]`` selection would have mis-grounded).

Stdlib ``unittest`` ONLY — NO network. The synthetic-index negative controls
ALWAYS RUN (a real MECHANISM proof, corpus-less). The whole-registry real-corpus
class is guarded by the shipped ``@skipUnless(corpus/index.db)`` (present locally
→ RUNS; a fresh clone → SKIPS, structural-only).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_conformance_v40_retrieve_what_you_cite.py -q
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import pytest

from crawler import auditor, crs_rules, searchindex
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.tests.test_searchindex import _make_index_corpus

pytestmark = pytest.mark.conformance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"
_DATA_DIR = _REPO_ROOT / "crawler" / "data" / "crs_rules"
_COVERAGE_MD = _DATA_DIR / "COVERAGE.md"
_AUDITORS_DIR = _REPO_ROOT / "skills" / "crs-auditors"
_AUDITOR_PKG = _REPO_ROOT / "crawler" / "auditors"
_AUDITOR_SPINE = _REPO_ROOT / "crawler" / "auditor.py"

# Synthetic-corpus verbatim spans (see test_searchindex TINY_BODY / HEADING_BODY).
_TINY_ID = "pr-pdi/tiny.md#000"
_TINY_QUOTE = "Permanent residence applicants must provide police certificates"
_ADJACENT_ID = "pr-pdi/headings.md#002"  # lexically-matching adjacent chunk
_HISTORICAL_PREFIX = "pr-pdi/headings"   # treated as the "superseded" source


def _static_gate_surface() -> list[Path]:
    """The registry YAML + auditor surface the volatile-rule gate must cover."""
    surface: list[Path] = []
    if _AUDITORS_DIR.is_dir():
        surface.extend(sorted(_AUDITORS_DIR.rglob("*.md")))
        surface.extend(sorted(_AUDITORS_DIR.rglob("*.py")))
    if _AUDITOR_PKG.is_dir():
        surface.extend(sorted(_AUDITOR_PKG.rglob("*.py")))
    if _AUDITOR_SPINE.is_file():
        surface.append(_AUDITOR_SPINE)
    surface.extend(sorted(_DATA_DIR.glob("*.yaml")))
    return surface


def _syn_row(rule_id: str, *, family: str, marker: str | None = None,
             deny_families=None, citation_id: str = _TINY_ID,
             quote: str = _TINY_QUOTE, query: str = "police certificates") -> RuleRow:
    """A synthetic RuleRow citing a chosen chunk with a chosen selector."""
    return RuleRow(
        rule_id=rule_id,
        factor_group="core_human_capital",
        factor_ids=[rule_id],
        check_type="admissibility",
        query=query,
        selector=Selector(family=family, marker=marker,
                          deny_families=list(deny_families or [])),
        claim_text="A grounded CRS rule.",
        citations=[Citation(chunk_id=citation_id, quote=quote)],
        machine_check=MachineCheck(kind="accepted_enum", field="x"),
        volatility=VolatilityMeta(volatility="stable", source_family=family))


# --------------------------------------------------------------------------- #
# Task 1 — positive: every registry rule grounds the intended rule (real corpus).
# --------------------------------------------------------------------------- #
@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY GROUNDING GATE: corpus/index.db is git-ignored and absent — the "
    "whole-registry retrieve-what-you-cite proof did NOT run; a green suite here "
    "is STRUCTURAL ONLY",
)
class TestRetrieveWhatYouCiteWholeRegistry(unittest.TestCase):
    """Every non-gap rule agrees + grounds against the REAL corpus; coverage
    complete; COVERAGE.md fresh; static volatile-rule gate clean."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = crs_rules.load_registry(_DATA_DIR)
        cls.nongap = [r for r in cls.reg.rows if not r.gap]

    def test_every_non_gap_rule_agrees_and_grounds(self) -> None:
        report = crs_rules.retrieve_what_you_cite(self.reg, _REAL_DB)
        covered: set[str] = set()
        for row in self.nongap:
            with self.subTest(rule_id=row.rule_id):
                entry = report[row.rule_id]
                self.assertTrue(entry["agrees_with_citation"], row.rule_id)
                self.assertTrue(entry["grounds"], row.rule_id)
                covered.add(row.rule_id)
        # A future added rule cannot silently escape this proof.
        self.assertEqual(covered, {r.rule_id for r in self.nongap})

    def test_validate_registry_zero_violations_full_grid(self) -> None:
        result = crs_rules.validate_registry(self.reg, _REAL_DB)
        self.assertEqual(result["violations"], [], result["violations"])
        self.assertEqual(result["grounded"], result["total"])
        self.assertGreaterEqual(result["total"], 20)  # the full grid, not a pilot

    def test_coverage_complete_or_documented_gaps(self) -> None:
        cov = crs_rules.coverage_report(self.reg)
        for group, info in cov["by_group"].items():
            self.assertEqual(info["missing"], [],
                             f"{group}: required rule_ids missing: {info['missing']}")
        self.assertTrue(cov["complete"])

    def test_committed_coverage_md_not_stale(self) -> None:
        self.assertTrue(_COVERAGE_MD.is_file(), "COVERAGE.md is not committed")
        fresh = crs_rules.render_coverage_markdown(self.reg)
        committed = _COVERAGE_MD.read_text(encoding="utf-8")
        self.assertEqual(
            committed, fresh,
            "COVERAGE.md is stale — regenerate with "
            "`.venv/bin/python -m crawler.crs_rules > "
            "crawler/data/crs_rules/COVERAGE.md`")

    def test_static_no_inlined_volatile_gate_is_clean(self) -> None:
        violations = crs_rules.no_inlined_volatile_rules(_static_gate_surface())
        self.assertEqual(
            violations, [],
            [f"{v['path']}:{v['line']} {v['kind']} {v['snippet']}"
             for v in violations])


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY: corpus/index.db absent — the real job-offer historical/legacy "
    "control did NOT run",
)
class TestJobOfferCurrentVsLegacyRealCorpus(unittest.TestCase):
    """The current-policy job-offer row grounds from the CURRENT guidance
    authority; the distinct legacy row stays a SEPARATE ministerial-instructions
    row and never bleeds into the current verdict (T-34-09)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = crs_rules.load_registry(_DATA_DIR)
        cls.report = crs_rules.retrieve_what_you_cite(cls.reg, _REAL_DB)
        cls.rows = {r.rule_id: r for r in cls.reg.rows}

    def test_current_grounds_from_current_guidance_not_historical(self) -> None:
        cur = self.report["additional.job_offer.current"]
        self.assertTrue(cur["agrees_with_citation"])
        self.assertTrue(cur["grounds"])
        selected = cur["selected_chunk_id"]
        self.assertTrue(selected.startswith("guidance/"))
        # It is NOT a denied year-end / midyear historical chunk.
        deny = self.rows["additional.job_offer.current"].selector.deny_families
        for pref in deny:
            self.assertFalse(selected.startswith(pref), f"grounded from {pref}")

    def test_legacy_is_a_separate_row_from_a_distinct_family(self) -> None:
        legacy = self.report["additional.job_offer.legacy"]
        self.assertTrue(legacy["agrees_with_citation"])
        self.assertTrue(legacy["selected_chunk_id"].startswith(
            "ministerial-instructions/"))
        # current + legacy are distinct rows over the SAME factor, citing
        # DISJOINT chunks — the legacy points chunk never grounds the current row.
        cur_row = self.rows["additional.job_offer.current"]
        legacy_row = self.rows["additional.job_offer.legacy"]
        self.assertEqual(cur_row.factor_ids, ["additional.job_offer"])
        self.assertEqual(legacy_row.factor_ids, ["additional.job_offer"])
        cur_ids = {c.chunk_id for c in cur_row.citations}
        legacy_ids = {c.chunk_id for c in legacy_row.citations}
        self.assertEqual(cur_ids & legacy_ids, set())


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY: corpus/index.db absent — the physician public-policy grounding "
    "+ disjoint-citation control did NOT run",
)
class TestJobOfferPhysicianRealCorpus(unittest.TestCase):
    """POLICY-02: the physician public-policy row grounds from the CURRENT
    guidance authority and cites DISTINCT chunks from BOTH the current-repeal and
    the legacy rows — a distinct citation on the SAME ``additional.job_offer``
    factor, never a cross-ground into the general repeal / legacy verdict."""

    _PHYSICIAN = "additional.job_offer.physician"
    _CURRENT = "additional.job_offer.current"
    _LEGACY = "additional.job_offer.legacy"

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = crs_rules.load_registry(_DATA_DIR)
        cls.report = crs_rules.retrieve_what_you_cite(cls.reg, _REAL_DB)
        cls.rows = {r.rule_id: r for r in cls.reg.rows}

    def test_physician_agrees_and_grounds_from_current_guidance(self) -> None:
        phys = self.report[self._PHYSICIAN]
        self.assertTrue(phys["agrees_with_citation"])
        self.assertTrue(phys["grounds"])
        self.assertTrue(phys["selected_chunk_id"].startswith("guidance/"))

    def test_physician_citations_disjoint_from_current_and_legacy(self) -> None:
        phys_row = self.rows[self._PHYSICIAN]
        cur_row = self.rows[self._CURRENT]
        legacy_row = self.rows[self._LEGACY]
        # All three are DISTINCT rows over the SAME factor.
        self.assertEqual(phys_row.factor_ids, ["additional.job_offer"])
        self.assertEqual(cur_row.factor_ids, ["additional.job_offer"])
        self.assertEqual(legacy_row.factor_ids, ["additional.job_offer"])
        phys_ids = {c.chunk_id for c in phys_row.citations}
        cur_ids = {c.chunk_id for c in cur_row.citations}
        legacy_ids = {c.chunk_id for c in legacy_row.citations}
        # POLICY-02 distinct-citation invariant: the physician row cites chunks
        # DISJOINT from BOTH the general repeal (current) and the ITA-era legacy
        # rows — no cross-ground on the shared factor.
        self.assertEqual(phys_ids & cur_ids, set())
        self.assertEqual(phys_ids & legacy_ids, set())


# --------------------------------------------------------------------------- #
# ALWAYS-RUN hermetic physician grounding gate (WR-01 remediation).
#
# TestJobOfferPhysicianRealCorpus above proves the physician row grounds against
# the pinned corpus/index.db — but it is @skipUnless(_REAL_DB.is_file()), so it
# NEVER runs in CI / a fresh clone. Yet the physician row makes TWO new corpus
# chunks (guidance/job-offer.md#002 + the FSW-PDI physician span) load-bearing for
# the ENTIRE additional.job_offer consumed subset: auditor.gate_subset fail-closes
# the WHOLE factor (current + legacy + physician) if ANY consumed row ungrounds. A
# marker / citation / quote drift on the physician row would therefore pass CI and
# only surface as a runtime audit outage for EVERY applicant — a far larger blast
# radius than the physician branch alone.
#
# This class closes that gap WITHOUT weakening the whole-registry live tests: it
# builds a MINIMAL hermetic FTS5 index carrying ONLY the two authoritative
# physician chunk spans (text copied VERBATIM from the pinned corpus at the exact
# two relpaths), loads the REAL registry row from additional.yaml, and drives the
# SHIPPED spine gate (auditor.gate_subset), validate_registry, and
# retrieve_what_you_cite over it. It ALWAYS RUNS (no corpus/index.db needed), so a
# physician row/citation/marker drift is caught in CI; a non-vacuity control proves
# the gate actually BITES. The verbatim fixtures below live in a test file, which
# the no-inlined-volatile static gate does NOT scan (its surface is the auditor
# package + YAML, never crawler/tests/), so pinning the authoritative spans here is
# safe.
# --------------------------------------------------------------------------- #

# The exact two chunk spans the physician row cites, copied VERBATIM from the
# pinned corpus (guidance/job-offer.md#002 + the FSW arranged-employment PDI #020).
# Non-ASCII codepoints (U+2019 curly apostrophe, U+201C/U+201D curly quotes) are
# \u-escaped so the fixture is byte-exact regardless of editor encoding — the
# U+2019 in "you\u2019re a physician" is load-bearing for the row's grounded marker.
_JOB_OFFER_MD_002_ID = "guidance/job-offer.md#002"
_FSW_PDI_020_RELPATH = (
    "pr-pdi/economic-classes-federal-skilled-workers-arranged-employment-"
    "awarding-points-applications-received-on-after-may-4-2013.md")
_FSW_PDI_020_ID = _FSW_PDI_020_RELPATH + "#020"

_JOB_OFFER_MD_002 = (
    "Your job offer must:\n"
    "  * be recent\n"
    "  * be in writing\n"
    "  * not be from an embassy, high commission or consulate in Canada\n"
    "  * set out details of the job they\u2019re offering you, such as: \n"
    "    * your pay and deductions\n"
    "    * your duties\n"
    "    * the conditions of employment, like your hours of work\n"
    "\n"
    "**A work permit on its own is not a job offer, even if it is an open work permit.**\n"
    "Your job offer must also meet other criteria to be valid under the Express Entry program you qualify for below.\n"
    "If you\u2019re a physician with a job offer in Canada\n"
    "We introduced a temporary public policy for foreign national physicians who:\n"
    "  * were invited to apply for permanent residence through Express Entry on or after April 25, 2023, and submitted an application\n"
    "  * have a job offer to provide publicly funded medical services in Canada\n"
    "\n"
    "Under the policy, your job offer:\n"
    "  * is valid under the Federal Skilled Worker Program (FSWP) even if the job being offered is not continuous and does not last for at least 1 year after we issue your permanent resident visa\n"
    "  * allows you to earn points: \n"
    "    * for arranged employment under the FSWP selection factors\n"
    "    * toward your total Express Entry score in the Comprehensive Ranking System (CRS)\n"
    "\n"
    "Learn more about our updated requirements for a valid job offer to work as a physician."
)

_FSW_PDI_020 = (
    "Assessing arranged employment in the context of the [Temporary public policy to facilitate the issuance of permanent resident visas for physicians providing publicly funded medical services in Canada](https://www.canada.ca/en/immigration-refugees-citizenship/corporate/mandate/policies-operational-instructions-agreements/public-policies/physicians-4-2023.html)\n"
    "**Employee vs. self-employed: Assessing the \u201coffer of employment\u201d for arranged employment points under R82 and Express Entry MI29**\n"
    "For the purposes of assessing the offer of employment in the context of this public policy, the foreign national physician must be\n"
    "  * a specialist physician (NOC 3111) or a general practitioner (NOC 3112) under NOC 2016 or\n"
    "  * a specialist in clinical and laboratory medicine (NOC 31100), a specialist in surgery (NOC 31101) or a general practitioner and family physician (NOC 31102) under NOC 2021\n"
    "\n"
    "Despite the physician\u2019s employment status of \u201cself-employed,\u201d an offer of employment must be issued by one of the following: \n"
    "  * a provincial or territorial government\n"
    "  * a government agency\n"
    "  * a government-appointed agency, for example \n"
    "    * a regional health authority\n"
    "    * a health care service delivery entity managed by government-appointed members who oversee hospitals, long-term care facilities, home care and public health services\n"
    "    * a provincial ministry or department responsible for health care, children and/or family development, correctional services\n"
    "  * an organization providing health care, for example, a hospital or medical clinic"
)


class TestJobOfferPhysicianHermeticGrounding(unittest.TestCase):
    """ALWAYS-RUN: the physician row grounds against a hermetic 2-chunk index.

    Corpus-less (builds its own temp FTS5 index), so it runs in CI and a fresh
    clone — catching physician row/citation/marker drift that the skip-guarded
    real-corpus class above would silently miss.
    """

    _PHYSICIAN = "additional.job_offer.physician"

    # The exact two (chunk_id, relpath, ordinal, verbatim_text) spans the physician
    # row cites — copied verbatim from the pinned corpus.
    _FIXTURE_CHUNKS = (
        (_JOB_OFFER_MD_002_ID, "guidance/job-offer.md", 2, _JOB_OFFER_MD_002),
        (_FSW_PDI_020_ID, _FSW_PDI_020_RELPATH, 20, _FSW_PDI_020),
    )

    @staticmethod
    def _build_index(db: Path, chunks) -> None:
        """Build a minimal FTS5 index carrying exactly *chunks* (verbatim text).

        Inserts each (chunk_id, relpath, ordinal, text) span DIRECTLY with a REAL
        ``searchindex.chunk_sha`` fingerprint (so ``searchindex.resolve`` does not
        treat the row as drifted / stale) and rebuilds FTS — mirroring
        ``build_index``'s write shape without needing on-disk markdown or the
        chunker, so the chunk ids land at exactly the cited coordinates.
        """
        con = sqlite3.connect(str(db))
        try:
            con.executescript(searchindex.CHUNKS_DDL)
            con.executescript(searchindex.FTS_DDL)
            for chunk_id, relpath, ordinal, text in chunks:
                con.execute(
                    "INSERT INTO chunks(chunk_id, relpath, source_url, title, "
                    "section, crawl_date, source_type, chunk_sha, ordinal, text) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (chunk_id, relpath, "", "", "", "", "",
                     searchindex.chunk_sha(text), ordinal, text))
            con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
            con.commit()
        finally:
            con.close()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.reg = crs_rules.load_registry(_DATA_DIR)
        self.phys_row = next(
            (r for r in self.reg.rows if r.rule_id == self._PHYSICIAN), None)
        self.assertIsNotNone(
            self.phys_row,
            "additional.job_offer.physician missing from the registry")
        # Isolate the physician row so the hermetic 2-chunk index only has to carry
        # the physician spans (the exact two relpaths WR-01 flags as load-bearing).
        self.single = Registry(rows=[self.phys_row])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _fresh_db(self, chunks) -> Path:
        db = Path(self._tmp.name) / f"index-{len(chunks)}.db"
        self._build_index(db, chunks)
        return db

    def test_physician_row_is_load_bearing_for_whole_factor(self) -> None:
        # Documents the WR-01 coupling: the physician row joins the SHARED
        # additional.job_offer consumed subset, so a physician grounding failure
        # fail-closes the ENTIRE factor (current + legacy + physician) for EVERY
        # applicant — not only physicians. This is why the hermetic guard below is
        # a CI (non-skip) gate. Uses the SHIPPED spine selector, so a re-scoping of
        # the physician row's factor_ids that decoupled it would fail here.
        subset = auditor._consumed_rows(self.reg, "additional.job_offer")
        ids = {r.rule_id for r in subset.rows}
        self.assertIn(self._PHYSICIAN, ids)
        self.assertIn("additional.job_offer.current", ids)
        self.assertIn("additional.job_offer.legacy", ids)

    def test_physician_validate_registry_grounds_hermetically(self) -> None:
        # The SHIPPED grounding gate verifies BOTH physician citations (guidance
        # #002 quote + FSW-PDI #020 NOC quote) against the verbatim fixture spans.
        db = self._fresh_db(self._FIXTURE_CHUNKS)
        result = crs_rules.validate_registry(self.single, db)
        self.assertEqual(result["violations"], [], result["violations"])
        self.assertEqual(result["grounded"], result["total"])
        self.assertEqual(result["total"], 1)

    def test_physician_retrieve_what_you_cite_agrees_and_grounds(self) -> None:
        # The baked query + guidance-family + U+2019 marker re-select the cited
        # guidance chunk (agrees) and it verbatim-grounds the quote.
        db = self._fresh_db(self._FIXTURE_CHUNKS)
        entry = crs_rules.retrieve_what_you_cite(self.single, db)[self._PHYSICIAN]
        self.assertTrue(entry["agrees_with_citation"], entry)
        self.assertTrue(entry["grounds"], entry)
        self.assertEqual(entry["selected_chunk_id"], _JOB_OFFER_MD_002_ID)
        self.assertTrue(entry["selected_chunk_id"].startswith("guidance/"))

    def test_physician_gate_subset_passes_hermetically(self) -> None:
        # The SHIPPED spine gate must NOT raise on the grounded physician row.
        db = self._fresh_db(self._FIXTURE_CHUNKS)
        auditor.gate_subset(self.single, db)  # no AuditGroundingError

    def test_gate_bites_when_physician_citation_chunk_drifts(self) -> None:
        # Non-vacuity / drift proof: drop the FSW-PDI physician span (simulating a
        # corpus chunk-id drift on a refresh, or a citation edit that outruns the
        # corpus). The physician row can no longer ground BOTH cited chunks, so the
        # SHIPPED gate fail-closes — exactly the CI signal WR-01 asks for. Without
        # this the positive assertions above could pass vacuously.
        partial = self._FIXTURE_CHUNKS[:1]  # guidance #002 only, no FSW-PDI #020
        db = self._fresh_db(partial)
        with self.assertRaises(auditor.AuditGroundingError):
            auditor.gate_subset(self.single, db)


# --------------------------------------------------------------------------- #
# Task 2 — negative controls (synthetic index, ALWAYS RUN): the family/marker
# discipline BITES, and each control is non-vacuous.
# --------------------------------------------------------------------------- #
class TestNegativeControlsSynthetic(unittest.TestCase):
    """Wrong-family / historical / adjacent chunks cannot ground a rule."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
        self.db = Path(self._tmp.name) / "index.db"
        searchindex.build_index(self.root, self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _entry(self, row: RuleRow) -> dict:
        return crs_rules.retrieve_what_you_cite(Registry(rows=[row]), self.db)[
            row.rule_id]

    def _blind_top_hit(self, query: str, family: str) -> str:
        hits = searchindex.search(self.db, query, limit=8, family=family)["hits"]
        return hits[0]["chunk_id"]

    def test_wrong_family_cannot_ground(self) -> None:
        # A row citing the pr-pdi tiny chunk but pointing selector.family at a
        # DIFFERENT family selects a lexically-matching WRONG-family chunk → it
        # does not agree with the cited rule and does not ground.
        row = _syn_row("wrong.family", family="legislation-irpr")
        entry = self._entry(row)
        self.assertNotEqual(entry["selected_chunk_id"], _TINY_ID)
        self.assertFalse(entry["agrees_with_citation"])
        self.assertFalse(entry["grounds"])
        # Non-vacuous: the query DOES lexically match a wrong-family chunk (so the
        # family allow is what forces non-agreement, not an empty corpus)...
        self.assertTrue(self._blind_top_hit(
            "police certificates", "legislation-irpr").startswith(
            "legislation-irpr/"))
        # ...and with the CORRECT family + marker the SAME query grounds the rule.
        mirror = _syn_row("wrong.family.mirror", family="pr-pdi", marker=_TINY_QUOTE)
        m = self._entry(mirror)
        self.assertEqual(m["selected_chunk_id"], _TINY_ID)
        self.assertTrue(m["agrees_with_citation"])
        self.assertTrue(m["grounds"])

    def test_historical_superseded_deny_families_drops_the_stale_chunk(self) -> None:
        # The pr-pdi query surfaces the "superseded" headings chunk FIRST; a row
        # citing the CURRENT tiny chunk must drop it via deny_families.
        # Without deny → the superseded top hit is selected (agrees False)...
        no_deny = _syn_row("historical.no_deny", family="pr-pdi")
        n = self._entry(no_deny)
        self.assertEqual(n["selected_chunk_id"], _ADJACENT_ID)
        self.assertFalse(n["agrees_with_citation"])
        # ...WITH deny_families the superseded chunk is dropped → current selected.
        with_deny = _syn_row("historical.with_deny", family="pr-pdi",
                             deny_families=[_HISTORICAL_PREFIX])
        d = self._entry(with_deny)
        self.assertEqual(d["selected_chunk_id"], _TINY_ID)
        self.assertTrue(d["agrees_with_citation"])
        self.assertTrue(d["grounds"])
        # Non-vacuous: blind hits[0] is the superseded chunk — deny_families is
        # load-bearing, not a corpus that simply lacks the decoy.
        self.assertEqual(
            self._blind_top_hit("police certificates", "pr-pdi"), _ADJACENT_ID)

    def test_adjacent_missing_marker_is_dropped(self) -> None:
        # The adjacent headings chunk ranks FIRST for the pr-pdi query. Without a
        # discriminating marker the row mis-selects the adjacent chunk...
        no_marker = _syn_row("adjacent.no_marker", family="pr-pdi")
        n = self._entry(no_marker)
        self.assertEqual(n["selected_chunk_id"], _ADJACENT_ID)
        self.assertFalse(n["agrees_with_citation"])
        # ...WITH the non-volatile marker (present ONLY in the intended chunk) the
        # selector skips the adjacent hit and selects the cited chunk.
        with_marker = _syn_row("adjacent.with_marker", family="pr-pdi",
                               marker=_TINY_QUOTE)
        m = self._entry(with_marker)
        self.assertEqual(m["selected_chunk_id"], _TINY_ID)
        self.assertTrue(m["agrees_with_citation"])
        self.assertTrue(m["grounds"])
        # Non-vacuous: blind hits[0] is the adjacent chunk — the marker is the
        # discriminator, not luck.
        self.assertEqual(
            self._blind_top_hit("police certificates", "pr-pdi"), _ADJACENT_ID)

    def test_marker_absent_everywhere_abstains(self) -> None:
        # A marker present in NO hit → the selector abstains (None) rather than
        # grounding any chunk (fail-closed).
        row = _syn_row("marker.abstain", family="pr-pdi",
                       marker="THIS NON-VOLATILE MARKER IS IN NO CHUNK ZZZ")
        entry = self._entry(row)
        self.assertIsNone(entry["selected_chunk_id"])
        self.assertFalse(entry["agrees_with_citation"])
        self.assertFalse(entry["grounds"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
