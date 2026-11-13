"""Physician public-policy arranged-employment tests (Phase 42 — 42-02, POLICY-02).

Stdlib ``unittest`` ONLY — NO network, NO vault (the branch tests). Drives
``additional.decide_job_offer`` DIRECTLY over a SYNTHETIC registry + synthetic
``ExtractedValue`` by_field, so the distinct physician public-policy branch is
exercised in isolation from the frozen guard it delegates to.

Proves (POLICY-02, threat register T-42-01 / T-42-03):
  * a confirmed physician ``noc_code`` in the grounded physician window →
    AT-RISK / ``physician_policy_manual`` / ``substantiated_points is None`` —
    NEVER SUBSTANTIATED, NEVER an award;
  * the physician branch fires BEFORE the frozen guard: a physician NOC inside the
    OVERLAPPING legacy window still resolves to the distinct physician reason, not
    ``arranged_employment_legacy_manual`` (branch-order proof, Pitfall 4);
  * every non-physician / missing-NOC / None-ITA / post-repeal / malformed-window
    path falls through to the frozen guard UNCHANGED (legacy AT-RISK/None and
    current AT-RISK/0 preserved);
  * the module carries no inlined volatile rule (the NOC set + the 2023-04-25 date
    live ONLY in the grounded row, never a Python literal).

The extraction/vault seam (real per-document NOC linkage) is proven separately by
``TestJobOfferExtractionLinkage`` below (42-02-02).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_physician_policy.py -q
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from crawler import auditor, auditors, crs_rules, extraction, policy_offer, remediation, vault
from crawler.auditors import DecisionContext
from crawler.auditors import additional as ad
from crawler.models.crs_rules import (
    AcceptedValue,
    Citation,
    MachineCheck,
    PointsEntry,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor, ExtractedValue
from crawler.tests.fixtures.extraction import make_fixtures as mf

_TINY_ID = "pr-pdi/tiny.md#000"
_TINY_QUOTE = "Permanent residence applicants must provide police certificates"

# The physician window + NOC set are TEST FIXTURES only — the production module
# (crawler/auditors/additional.py) inlines NEITHER; it reads them from the grounded
# row (asserted by TestNoInlinedRules, which scans ad.__file__ — NOT this test file).
_PHYS_EFF_FROM = "2023-04-25"          # physician public policy effective window start
_PHYS_NOCS = ("31100", "31101", "31102")


def _arow(rule_id, mc, *, factor_ids=None, check_type="points", eff_from=None,
          eff_to=None, gap=False, group="additional_points"):
    return RuleRow(
        rule_id=rule_id, factor_group=group,
        factor_ids=factor_ids or ["additional." + rule_id.split(".")[1]],
        check_type=check_type, query="police certificates",
        selector=Selector(family="pr-pdi"),
        claim_text="A grounded additional rule.",
        citations=[Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
        machine_check=mc,
        volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi",
                                  effective_from=eff_from, effective_to=eff_to),
        gap=gap)


def _physician_row(*, eff_from=_PHYS_EFF_FROM, nocs=_PHYS_NOCS, gap=False):
    """Synthetic ``additional.job_offer.physician`` accepted_enum row.

    Mirrors the grounded row's SHAPE (accepted-NOC set + an open effective window
    ``[eff_from, ∞)``) so ``row_in_effect`` and the decider's set-membership check
    exercise the real contract. ``eff_from`` is intentionally parameterisable so a
    malformed grounded date can drive the fail-closed try/except.
    """
    return _arow(
        "additional.job_offer.physician",
        MachineCheck(kind="accepted_enum", field="physician_noc",
                     accepted_values=[AcceptedValue(value=noc) for noc in nocs],
                     effective_from=eff_from),
        factor_ids=["additional.job_offer"], check_type="policy",
        eff_from=eff_from, gap=gap)


def _registry(*, physician_eff_from=_PHYS_EFF_FROM) -> Registry:
    """The job-offer registry (current + legacy + physician) the decider reads.

    Extends ``test_auditors_additional.py::_registry`` with the physician row so the
    physician branch is reachable; the current/legacy rows are byte-identical to the
    guard's fixtures so the delegated (non-physician) paths stay comparable.
    """
    return Registry(rows=[
        _arow("additional.job_offer.current",
              MachineCheck(kind="policy_flag", field="job_offer_additional_points",
                           flag_value=False, effective_from="2025-03-25"),
              factor_ids=["additional.job_offer"], check_type="policy",
              eff_from="2025-03-25"),
        _arow("additional.job_offer.legacy",
              MachineCheck(kind="points_table", field="job_offer_legacy",
                           points_by_level=[PointsEntry(
                               label="major_group_00", level="Major Group 00",
                               points=200)]),
              factor_ids=["additional.job_offer"], check_type="policy",
              eff_from="2010-01-01", eff_to="2025-03-25"),
        _physician_row(eff_from=physician_eff_from),
    ])


def _val(field, value):
    return ExtractedValue(
        value_id="val_" + field, document_id="doc_x", field_name=field,
        raw_text=str(value), normalized_value=value, extraction_run_id="run_x",
        confirmation_status="confirmed", quality_flag="ok")


def _offer_factor(claimed_points=200):
    return CrsProfileFactor(
        factor_id="additional.job_offer", factor_group="additional_points",
        claimed_points=claimed_points, claimed_value=claimed_points)


def _ctx(*, by_field=None, factor=None, ita_date=None, registry=None,
         reference_date=None):
    reference_date = reference_date or date.today().isoformat()
    reg = registry if registry is not None else _registry()
    return DecisionContext(
        factor_id="additional.job_offer", factor=factor, by_field=by_field or {},
        registry=reg, consumed=Registry(rows=[]), spouse_mode=False,
        reference_date=reference_date, ita_date=ita_date)


class TestPhysicianBranch(unittest.TestCase):
    """POLICY-02: the distinct physician branch — grounded, AT-RISK/manual, capped."""

    # (a) confirmed physician NOC in the physician window → distinct AT-RISK/manual.
    def test_confirmed_physician_noc_in_window_is_at_risk_manual(self) -> None:
        by = {"noc_code": _val("noc_code", "31100")}
        # ITA well after the physician policy took effect (also post-repeal), so the
        # ONLY thing that can produce a non-current reason is the physician branch.
        res = ad.decide_job_offer(
            _ctx(by_field=by, factor=_offer_factor(), ita_date="2023-06-01"))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "physician_policy_manual")
        self.assertIsNone(res.substantiated_points)
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    # (b) physician NOC inside the OVERLAPPING legacy window → branch-order proof.
    def test_physician_noc_in_legacy_window_branch_order_wins(self) -> None:
        by = {"noc_code": _val("noc_code", "31100")}
        # 2024-06-01 is inside BOTH the legacy window (< 2025-03-25) and the open
        # physician window ([2023-04-25, ∞)); the physician branch must win.
        res = ad.decide_job_offer(
            _ctx(by_field=by, factor=_offer_factor(), ita_date="2024-06-01"))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "physician_policy_manual")
        self.assertNotEqual(res.reason_code, "arranged_employment_legacy_manual")
        self.assertIsNone(res.substantiated_points)

    # (c) non-physician NOC inside the legacy window → the frozen guard's legacy path.
    def test_non_physician_noc_in_legacy_window_is_legacy_manual(self) -> None:
        by = {"noc_code": _val("noc_code", "21234")}
        res = ad.decide_job_offer(
            _ctx(by_field=by, factor=_offer_factor(), ita_date="2024-06-01"))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "arranged_employment_legacy_manual")
        self.assertNotEqual(res.reason_code, "physician_policy_manual")
        self.assertIsNone(res.substantiated_points)

    # (d) non-physician NOC after the repeal → the frozen guard's current path (0).
    def test_non_physician_noc_after_repeal_is_current_zero(self) -> None:
        by = {"noc_code": _val("noc_code", "21234")}
        res = ad.decide_job_offer(
            _ctx(by_field=by, factor=_offer_factor(), ita_date="2026-01-01"))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "arranged_employment_current")
        self.assertEqual(res.substantiated_points, 0)
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    # (e) missing noc_code → the physician branch never fires; delegate to the guard.
    def test_missing_noc_delegates_to_guard_never_physician(self) -> None:
        # Empty by_field but a claim + an in-physician-window ITA: without a
        # confirmed noc_code the physician branch cannot fire → guard's legacy path.
        res = ad.decide_job_offer(
            _ctx(by_field={}, factor=_offer_factor(), ita_date="2024-06-01"))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "arranged_employment_legacy_manual")
        self.assertNotEqual(res.reason_code, "physician_policy_manual")

    # (f) physician NOC but no ITA date → window unevaluable → current/0 (fail-closed).
    def test_physician_noc_with_no_ita_date_is_current_zero(self) -> None:
        by = {"noc_code": _val("noc_code", "31100")}
        res = ad.decide_job_offer(
            _ctx(by_field=by, factor=_offer_factor(), ita_date=None))
        self.assertEqual(res.verdict, "AT-RISK")
        self.assertEqual(res.reason_code, "arranged_employment_current")
        self.assertEqual(res.substantiated_points, 0)
        self.assertNotEqual(res.reason_code, "physician_policy_manual")

    # A malformed GROUNDED physician window fails closed (try/except → not-in-effect)
    # and delegates to the guard UNCHANGED — a physician NOC still never auto-greens.
    def test_malformed_physician_window_falls_through_to_guard(self) -> None:
        by = {"noc_code": _val("noc_code", "31100")}
        reg = _registry(physician_eff_from="not-a-real-date")
        res = ad.decide_job_offer(
            _ctx(by_field=by, factor=_offer_factor(), registry=reg,
                 ita_date="2024-06-01"))
        self.assertEqual(res.verdict, "AT-RISK")
        # In-window legacy guard path — NOT the physician branch (row not in effect).
        self.assertEqual(res.reason_code, "arranged_employment_legacy_manual")
        self.assertNotEqual(res.reason_code, "physician_policy_manual")
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")

    # A zero / unclaimed offer is N/A regardless of a physician NOC (no claim path).
    def test_zero_claim_is_na_even_with_physician_noc(self) -> None:
        by = {"noc_code": _val("noc_code", "31100")}
        res = ad.decide_job_offer(
            _ctx(by_field=by, factor=_offer_factor(claimed_points=0),
                 ita_date="2024-06-01"))
        self.assertEqual(res.verdict, "N/A")
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")


class TestJobOfferReasonAwareCitations(unittest.TestCase):
    """WR-02: each job-offer verdict scopes its card citations to the row it
    derives from — a card never over-cites the sibling rows on the shared factor.

    Drives the REAL ``decide_job_offer`` for the per-verdict ``rule_ids`` and the
    REAL registry (``crs_rules.load_registry`` — YAML parse only, no corpus DB) +
    the SHIPPED spine helper ``auditor._rule_citation_ids_for`` for the resulting
    citation ids, so the disjoint current / legacy / physician citations the
    scoping selects among are the actually-shipped ones.
    """

    _CURRENT = "additional.job_offer.current"
    _LEGACY = "additional.job_offer.legacy"
    _PHYSICIAN = "additional.job_offer.physician"

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = crs_rules.load_registry()
        cls.subset = auditor._consumed_rows(cls.reg, "additional.job_offer")
        cls.cur = set(auditor._rule_citation_ids_for(cls.subset, (cls._CURRENT,)))
        cls.legacy = set(auditor._rule_citation_ids_for(cls.subset, (cls._LEGACY,)))
        cls.phys = set(auditor._rule_citation_ids_for(cls.subset, (cls._PHYSICIAN,)))

    def _rule_ids(self, **kw):
        return ad.decide_job_offer(_ctx(**kw)).rule_ids

    def test_subset_rows_cite_disjoint_chunks(self) -> None:
        # Precondition (non-vacuity): the three rows cite DISJOINT chunks, else the
        # exclusion assertions below could pass trivially.
        self.assertTrue(self.cur and self.legacy and self.phys)
        self.assertEqual(self.cur & self.phys, set())
        self.assertEqual(self.cur & self.legacy, set())
        self.assertEqual(self.legacy & self.phys, set())

    def test_physician_card_cites_only_physician_row(self) -> None:
        rule_ids = self._rule_ids(
            by_field={"noc_code": _val("noc_code", "31100")},
            factor=_offer_factor(), ita_date="2023-06-01")
        self.assertEqual(rule_ids, (self._PHYSICIAN,))
        cites = set(auditor._rule_citation_ids_for(self.subset, rule_ids))
        self.assertEqual(cites, self.phys)
        self.assertEqual(cites & self.cur, set())
        self.assertEqual(cites & self.legacy, set())

    def test_nonphysician_current_card_excludes_physician_and_legacy(self) -> None:
        # A plain current-policy repeal verdict (0 points, non-physician) must NOT
        # surface the physician-NOC citations — the core WR-02 regression.
        rule_ids = self._rule_ids(
            by_field={"noc_code": _val("noc_code", "21234")},
            factor=_offer_factor(), ita_date="2026-01-01")
        self.assertEqual(rule_ids, (self._CURRENT,))
        cites = set(auditor._rule_citation_ids_for(self.subset, rule_ids))
        self.assertEqual(cites, self.cur)
        self.assertEqual(cites & self.phys, set())
        self.assertEqual(cites & self.legacy, set())

    def test_legacy_card_cites_only_legacy_row(self) -> None:
        rule_ids = self._rule_ids(
            by_field={"noc_code": _val("noc_code", "21234")},
            factor=_offer_factor(), ita_date="2024-06-01")
        self.assertEqual(rule_ids, (self._LEGACY,))
        cites = set(auditor._rule_citation_ids_for(self.subset, rule_ids))
        self.assertEqual(cites, self.legacy)
        self.assertEqual(cites & self.phys, set())
        self.assertEqual(cites & self.cur, set())

    def test_no_points_card_has_no_irrelevant_citations(self) -> None:
        # A no-claim N/A (awards nothing) scopes to the current-repeal row only —
        # no physician / legacy citations leak onto a card with no points.
        rule_ids = self._rule_ids(
            by_field={}, factor=_offer_factor(claimed_points=0), ita_date="2024-06-01")
        self.assertEqual(rule_ids, (self._CURRENT,))
        cites = set(auditor._rule_citation_ids_for(self.subset, rule_ids))
        self.assertEqual(cites & self.phys, set())
        self.assertEqual(cites & self.legacy, set())

    def test_invalid_selected_rule_id_is_safely_empty(self) -> None:
        # An unknown selected rule id matches no consumed row → the card is safely
        # left with no citation (the fail-closed convention), never an error.
        self.assertEqual(
            auditor._rule_citation_ids_for(
                self.subset, ("additional.job_offer.does_not_exist",)),
            [])

    def test_unset_rule_ids_preserves_union_for_other_factors(self) -> None:
        # Every non-job-offer decider leaves rule_ids None → the spine falls back to
        # the whole-subset UNION (byte-identical historical behavior).
        self.assertIsNone(
            ad.decide_nomination(_ctx(by_field={}, factor=None)).rule_ids)
        union = set(auditor._rule_citation_ids(self.subset))
        self.assertTrue(self.phys.issubset(union))
        self.assertTrue(self.cur.issubset(union))
        self.assertTrue(self.legacy.issubset(union))


class TestNoInlinedRules(unittest.TestCase):
    def test_module_has_no_inlined_volatile_rules(self) -> None:
        # Scans the physician decider module AND the inert offer-for-eligibility
        # sidecar (added in 42-03). The NOC set + the physician date must live in
        # the grounded row, never as a Python literal; the sidecar's bare 0 is not a
        # volatile points value, so both files must stay clean ([]).
        self.assertEqual(
            crs_rules.no_inlined_volatile_rules([ad.__file__, policy_offer.__file__]),
            [])


# --------------------------------------------------------------------------- #
# Inert offer-for-eligibility sidecar (42-03, POLICY-03 / threats T-42-01 / T-42-04).
# Drives crawler/policy_offer.py DIRECTLY over the synthetic _registry(). Proves the
# sidecar is INERT (unregistered, not summed), PII-light (closed public field set),
# deterministic, and STRUCTURALLY never-green: crs_points is a constant 0 and the
# status is AT-RISK / N/A only — never SUBSTANTIATED — for EVERY input.
# --------------------------------------------------------------------------- #
_SIDECAR_FIELDS = {
    "offer_present", "eligibility_status", "crs_points",
    "for_program_eligibility_only", "reason", "citation",
}


class TestOfferSidecar(unittest.TestCase):
    """POLICY-03: the inert sidecar — constant 0, never SUBSTANTIATED, unregistered."""

    def _current_chunk_id(self, reg):
        cur = next((r for r in reg.rows
                    if r.rule_id == "additional.job_offer.current"), None)
        return cur.citations[0].chunk_id if cur else None

    # (a) crs_points is a CONSTANT 0 and the status is AT-RISK/N/A (never
    # SUBSTANTIATED) for EVERY input — a present AND an absent claim across a sweep
    # of point counts (0, a legacy-era value, and an arbitrarily large one).
    def test_sidecar_crs_points_constant_zero_all_inputs(self) -> None:
        reg = _registry()
        want_citation = self._current_chunk_id(reg)
        for claim_points in (0, 200, 999):
            d = policy_offer.offer_for_program_eligibility(
                claim_points, "2026-01-01", reg)
            self.assertEqual(d["crs_points"], 0, d)
            self.assertIn(d["eligibility_status"], ("AT-RISK", "N/A"), d)
            self.assertNotEqual(d["eligibility_status"], "SUBSTANTIATED", d)
            self.assertIs(d["for_program_eligibility_only"], True, d)
            # present ⇔ AT-RISK; absent ⇔ N/A (bool(claim_points)).
            self.assertEqual(
                d["offer_present"], bool(claim_points), d)
            self.assertEqual(
                d["eligibility_status"],
                "AT-RISK" if claim_points else "N/A", d)
            self.assertEqual(d["citation"], want_citation, d)
            self.assertEqual(d["reason"], "offer_for_eligibility_manual", d)

    # (b) the status is NEVER SUBSTANTIATED and the points value is NEVER non-zero,
    # regardless of the claimed point count (there is no award path to reach).
    def test_sidecar_status_never_substantiated(self) -> None:
        reg = _registry()
        for claim_points in (0, 1, 50, 200, 600, 100_000):
            d = policy_offer.offer_for_program_eligibility(
                claim_points, "2024-06-01", reg)
            self.assertNotEqual(d["eligibility_status"], "SUBSTANTIATED", d)
            self.assertEqual(d["crs_points"], 0, d)

    # (c) the citation is the current row's chunk id — the sidecar REUSES the
    # already-grounded citation rather than minting a new grounded surface.
    def test_sidecar_reuses_grounded_current_citation(self) -> None:
        reg = _registry()
        d = policy_offer.offer_for_program_eligibility(200, "2026-01-01", reg)
        self.assertEqual(d["citation"], self._current_chunk_id(reg))

    # (d) with NO current row present the citation degrades to None (no new grounded
    # surface is invented) — safe, deterministic, still constant-0.
    def test_sidecar_citation_none_when_current_row_absent(self) -> None:
        reg = Registry(rows=[_physician_row()])  # no additional.job_offer.current
        d = policy_offer.offer_for_program_eligibility(200, "2026-01-01", reg)
        self.assertIsNone(d["citation"], d)
        self.assertEqual(d["crs_points"], 0, d)
        self.assertEqual(d["eligibility_status"], "AT-RISK", d)

    # (e) INERT proof: the sidecar is NOT the decider registered for
    # additional.job_offer, is not in the auditors registry, and adds no grid factor
    # (additional.job_offer stays a SINGLE grid factor; the envelope is untouched).
    def test_sidecar_is_inert_unregistered(self) -> None:
        self.assertIsNot(
            auditors.resolve("additional.job_offer"),
            policy_offer.offer_for_program_eligibility)
        self.assertNotIn(
            policy_offer.offer_for_program_eligibility,
            getattr(auditors, "_REGISTRY", {}).values())
        # The sidecar contributes NO grid factor — additional.job_offer is still one.
        self.assertEqual(
            auditors.FULL_GRID_FACTORS.count("additional.job_offer"), 1)

    # (f) PII-light proof: the returned dict keys are EXACTLY the closed public set —
    # no ev_ evidence id, no filesystem path, no applicant value ever leaks.
    def test_sidecar_return_dict_is_pii_light_closed_set(self) -> None:
        reg = _registry()
        d = policy_offer.offer_for_program_eligibility(200, "2026-01-01", reg)
        self.assertEqual(set(d.keys()), _SIDECAR_FIELDS)
        self.assertEqual(set(d.keys()), set(policy_offer.PUBLIC_FIELDS))
        for key, value in d.items():
            self.assertFalse(
                isinstance(value, str) and value.startswith("ev_"),
                f"{key} leaks an evidence id: {value!r}")
            # A public corpus chunk id (e.g. "pr-pdi/tiny.md#000") is an allowed
            # grounded citation; only an ABSOLUTE filesystem path would be PII-leaky.
            self.assertFalse(
                isinstance(value, str) and os.path.isabs(value),
                f"{key} leaks an absolute filesystem path: {value!r}")


# --------------------------------------------------------------------------- #
# Real extraction/vault seam (42-02-02): per-document NOC linkage is claimed-only
# and contamination-free — a physician NOC on a job_offer doc reaches the decider's
# by_field via additional.job_offer, never leaking to/from an employment_reference's
# core.work. Mirrors test_extraction_factor_linkage.py's real import→extract seam.
# --------------------------------------------------------------------------- #
class _LinkageTmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _open(self):
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        return v

    def _claim(self, v, factor_id, group, **kw):
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id=factor_id, factor_group=group, **kw))

    def _import(self, v, data: bytes, doc_type: str, name: str = "fixture") -> str:
        src = Path(self._tmp.name) / f"{name}.pdf"
        src.write_bytes(data)
        return vault.import_document(
            v, "default", src, doc_type=doc_type).document_id

    def _extract(self, v, doc_id: str, **kw):
        try:
            return extraction.extract_document(v, doc_id, **kw)
        except extraction.MissingExtractionDependency as exc:  # pragma: no cover
            self.skipTest(f"extraction deps unavailable: {exc.module}")

    def _values(self, v, doc_id: str):
        return vault.list_extracted_values(v, document_id=doc_id)


class TestJobOfferExtractionLinkage(_LinkageTmpCase):
    """POLICY-02 evidence path: per-document physician NOC linkage, contamination-free."""

    def _claim_both(self, v) -> None:
        # additional.job_offer is the physician / arranged-employment factor;
        # core.work is the employment factor. BOTH carry a noc_code, but the value
        # links per-DOCUMENT, never across factors.
        self._claim(v, "additional.job_offer", "additional_points",
                    claimed_points=200, claimed_value=200)
        self._claim(v, "core.work", "core_human_capital", claimed_value=3.0)

    def test_job_offer_noc_extraction_links_to_additional_job_offer(self) -> None:
        v = self._open()
        try:
            self._claim_both(v)
            jo = self._import(v, mf.job_offer_pdf(), "job_offer", "jo")
            self._extract(v, jo)
            jo_noc = [val for val in self._values(v, jo)
                      if val.field_name == "noc_code"]
            self.assertTrue(jo_noc, "job_offer noc_code not extracted")
            for val in jo_noc:
                self.assertEqual(val.factor_id, "additional.job_offer")
                self.assertEqual(val.normalized_value, mf.FAKE_PHYSICIAN_NOC)
        finally:
            v.con.close()

    def test_job_offer_and_reference_noc_extraction_no_cross_leak(self) -> None:
        v = self._open()
        try:
            self._claim_both(v)
            jo = self._import(v, mf.job_offer_pdf(), "job_offer", "jo")
            emp = self._import(v, mf.employment_reference_pdf(),
                               "employment_reference", "emp")
            self._extract(v, jo)
            self._extract(v, emp)
            jo_noc = [val for val in self._values(v, jo)
                      if val.field_name == "noc_code"]
            emp_noc = [val for val in self._values(v, emp)
                       if val.field_name == "noc_code"]
            self.assertTrue(jo_noc, "job_offer noc_code not extracted")
            self.assertTrue(emp_noc, "employment_reference noc_code not extracted")
            # job_offer NOC → additional.job_offer, NEVER core.work.
            for val in jo_noc:
                self.assertEqual(val.factor_id, "additional.job_offer")
                self.assertNotEqual(val.factor_id, "core.work")
            # employment_reference NOC → core.work, NEVER additional.job_offer.
            for val in emp_noc:
                self.assertEqual(val.factor_id, "core.work")
                self.assertNotEqual(val.factor_id, "additional.job_offer")
            # No value in EITHER document carries the OTHER document's factor.
            for val in self._values(v, jo):
                self.assertNotEqual(val.factor_id, "core.work")
            for val in self._values(v, emp):
                self.assertNotEqual(val.factor_id, "additional.job_offer")
        finally:
            v.con.close()

    def test_unclaimed_job_offer_leaves_extracted_noc_unlinked(self) -> None:
        # additional.job_offer is NOT claimed → _resolve_factor returns None → the
        # job_offer NOC is extracted but UNLINKED (fail-closed, no contamination).
        v = self._open()
        try:
            self._claim(v, "core.work", "core_human_capital", claimed_value=3.0)
            jo = self._import(v, mf.job_offer_pdf(), "job_offer", "jo")
            self._extract(v, jo)
            jo_vals = self._values(v, jo)
            self.assertTrue(jo_vals, "job_offer values not extracted")
            for val in jo_vals:
                self.assertIsNone(val.factor_id)
                self.assertNotEqual(val.factor_id, "core.work")
        finally:
            v.con.close()


# --------------------------------------------------------------------------- #
# Remediation reason→action templates (42-03, POLICY-03 / threat T-42-02). The two
# new reason codes (physician_policy_manual, offer_for_eligibility_manual) must
# surface as GENERIC, {factor}-parameterized, PII-light prose with NO inlined
# volatile threshold (date / NOC / points / CLB / window). Unknown reason codes
# still degrade safely to the generic _DEFAULT_ACTION_BY_KIND fallback.
# --------------------------------------------------------------------------- #
class TestRemediationReasons(unittest.TestCase):
    """POLICY-03: physician + offer-for-eligibility remediation templates."""

    _SAMPLE_FACTOR = "additional.job_offer"

    def test_reason_templates_exist(self) -> None:
        self.assertIn("physician_policy_manual", remediation._ACTION_TEMPLATES)
        self.assertIn("offer_for_eligibility_manual", remediation._ACTION_TEMPLATES)

    def test_reason_templates_render_factor_substituted(self) -> None:
        # Each template is {factor}-parameterized: rendering substitutes the factor
        # id and leaves no unfilled placeholder.
        for reason in ("physician_policy_manual", "offer_for_eligibility_manual"):
            rendered = remediation._action_for(
                self._SAMPLE_FACTOR, reason, "at_risk")
            self.assertIn(self._SAMPLE_FACTOR, rendered, reason)
            self.assertNotIn("{factor}", rendered, reason)

    def test_reason_templates_have_no_inlined_volatile_threshold(self) -> None:
        # Render both templates to a temp file and assert the aggregate no-inlined
        # gate (the SAME scanner that covers remediation.py) finds no volatile
        # literal — no date, NOC, points value, CLB benchmark, or validity window.
        rendered = "\n".join(
            remediation._action_for(self._SAMPLE_FACTOR, reason, "at_risk")
            for reason in ("physician_policy_manual", "offer_for_eligibility_manual"))
        with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(rendered + "\n")
            tmp_path = fh.name
        try:
            self.assertEqual(
                crs_rules.no_inlined_volatile_rules([tmp_path]), [])
        finally:
            os.unlink(tmp_path)

    def test_unknown_reason_degrades_to_generic_fallback(self) -> None:
        # An UNKNOWN reason code is not special-cased — it falls back to the generic
        # _DEFAULT_ACTION_BY_KIND action for the finding kind (safe degradation).
        rendered = remediation._action_for(
            self._SAMPLE_FACTOR, "some_unknown_reason_xyz", "at_risk")
        self.assertEqual(
            rendered,
            remediation._DEFAULT_ACTION_BY_KIND["at_risk"].format(
                factor=self._SAMPLE_FACTOR))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
