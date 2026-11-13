"""v5 NOC negative-control conformance — NO duty-review path auto-**greens**.

Phase 43 (43-04, NOC-03; threat register T43-02/03/04/06/07/08/09).

The phase's highest-stakes regression is a NOC work-duty review silently
auto-**greening** into a ``SUBSTANTIATED`` verdict or a non-zero CRS award, or a
confirmed duty value leaking into the FROZEN ``core.work`` grid card. This module is
the release-gate-grade negative control that proves it can NEVER happen. It mirrors
``test_conformance_v5_policy_no_job_offer_green.py`` wholesale, retargeted to the
inert NOC sidecar + the Plan-01 worksheet generator:

  * :class:`TestNoNocPathGreens` — an EXHAUSTIVE sweep driving the REAL
    :func:`crawler.noc_review.review_noc_duties` over EVERY duty-review input class
    (none / pending-only / partial / all-rejected / Layer-1-stale / Layer-2-drifted /
    changed-sha / all-confirmed-fresh, plus a GROUPED sub-occupation NOC), asserting
    for every case ``status != "SUBSTANTIATED"``, ``status in {"AT-RISK","GAP","N/A"}``
    and that NO score / ``crs_points`` key (hence no non-zero CRS/points delta) can
    ever appear, with ``confirmed_count <= duty_count`` (T43-02/03/04).
  * :class:`TestFrozenSurfacesByteIdentity` — a ``git diff --quiet HEAD`` byte-identity
    assertion over the FREEZE set (``crawler/auditors/core.py``,
    ``crawler/crs_audit.py``, ``crawler/models/audit.py``,
    ``crawler/auditors/__init__.py``), skip-guarded off a git checkout (T43-06).
  * :class:`TestSidecarInert` — the sidecar is absent from
    ``crawler.auditors._REGISTRY``, absent from ``FULL_GRID_FACTORS``, imports nothing
    from ``crawler/auditors`` (prose-immune AST scan), and the inert ``review.noc``
    factor is likewise never on the grid (T43-06).
  * :class:`TestSidecarPiiLightClosedSet` — the returned dict is EXACTLY the closed
    :data:`crawler.noc_review.PUBLIC_FIELDS` set (no ``raw_text`` / ``ev_`` id / abs
    path) (T43-04).
  * :class:`TestCoreWorkFactorIsolation` (B1) — a RUNTIME proof: a ``core.work`` audit
    is byte-for-behavior IDENTICAL BEFORE and AFTER confirmed ``review.noc`` duty
    values (verdict / reason_code / confirmed_value / sorted evidence_ids /
    substantiated_points / score_delta all unchanged); NO NOC evidence id enters the
    ``core.work`` card; ``review.noc`` is NOT in ``FULL_GRID_FACTORS``; and no NOC id
    appears in a built :class:`crawler.models.audit.PublicAuditEnvelope`
    (single-factor + full-grid) (T43-08).
  * :class:`TestIdempotentRegenerationIsolation` (B1 / T43-09) — an EXACT worksheet
    rerun mints no duplicate ``review.noc`` row (stable value_ids/duty_count, confirmed
    state preserved) and keeps the ``core.work`` card byte-identical; a changed-``duty_sha``
    rerun is counted ONCE (``confirmed_count <= duty_count``, old drifted value ignored),
    still never greens, and leaves the ``core.work`` card byte-identical.

Grounding note: every volatile literal (a NOC code, a citation, a duty span) lives
ONLY in FIXTURES here — the synthetic ``core.work`` corpus quote reused from
``test_auditor.py`` and the pinned NOC codes ``21232`` / ``53124``. This module drives
the REAL production functions over those fixtures; it inlines no production policy
value of its own (that is proven separately by the extended ``_EXPORT_MODULES`` static
gate in ``test_crs_no_inlined_rules.py``).

Naming (no Phase-45/46 wiring): the ``v5`` prefix is intentional. The v4.x
release-gate runner glob is ``crawler/tests/test_conformance_v4[01]_*.py``
(``scripts/run_conformance.py``), so this file is deliberately NOT captured by the
v4.x gate this phase — Phase 46 introduces the v5 glob. It still runs inside the full
``crawler/tests`` suite. ``scripts/run_conformance.py`` is NOT touched.

Stdlib ``unittest`` ONLY — NO network. The runtime-isolation + never-green classes
resolve against the PINNED, git-ignored ``corpus/index.db`` (skip-guarded so a fresh
clone stays STRUCTURAL-only rather than falsely failing); the frozen-surface +
structural-inertness classes need neither corpus nor git. Run from the repo root::

    .venv/bin/python -m pytest \\
        crawler/tests/test_conformance_v5_noc_no_auto_green.py -q
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from crawler import auditor, crs_rules, noc_review, noc_worksheet, searchindex, vault
from crawler import auditors
from crawler.models.audit import to_public_envelope
from crawler.models.crs_rules import (
    AcceptedValue,
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor

# Reuse the proven Plan-01/02 seeding helpers (every confirmed / rejected / stale /
# drifted value is minted through the SHIPPED generator + ``vault.confirm_value``
# verb) rather than re-declaring them here — the same cross-test-helper reuse the
# physician conformance mirror applies to ``test_physician_policy``. Importing helper
# functions does NOT re-collect the donor module's TestCase classes.
from crawler.tests.test_noc_review import (
    _confirm,
    _confirm_all,
    _current_duty_value_id,
    _drift_layer2_quote,
    _list_review_noc,
    _make_layer1_stale,
    _review_noc_factor,
)
from crawler.tests.test_searchindex import _make_index_corpus

# Marker-tagged like the sibling conformance modules (registered in pyproject). This
# does NOT enrol the file into the v4.x release gate, which selects by the file glob
# `test_conformance_v4[01]_*.py`, not by the marker.
pytestmark = pytest.mark.conformance

# --------------------------------------------------------------------------- #
# Repo-root-anchored coordinates + fixtures (test data only).
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"
_CORPUS_MISSING = (
    "LOCAL-ONLY: corpus/index.db is git-ignored — the grounded NOC negative-control "
    "slice did NOT run; a green suite here is STRUCTURAL ONLY"
)

# The FREEZE set: the four surfaces NOC-03 mandates stay byte-for-byte frozen.
_FREEZE_SET = (
    "crawler/auditors/core.py",         # decide_work (FROZEN)
    "crawler/crs_audit.py",             # CRS award chokepoints (FROZEN)
    "crawler/models/audit.py",          # PublicAuditEnvelope / PrivateFactorCard (FROZEN)
    "crawler/auditors/__init__.py",     # _REGISTRY / FULL_GRID_FACTORS (FROZEN)
)

# Pinned NOC fixtures (corpus-grounded): 21232 -> 7 duties; 53124 -> grouped
# sub-occupation headers preserved verbatim (18 items). Fixtures ONLY.
_NOC = "21232"
_NOC_GROUPED = "53124"

# The invariant every duty-review outcome must satisfy.
_FORBIDDEN_VERDICT = "SUBSTANTIATED"
_ALLOWED_STATUSES = ("AT-RISK", "GAP", "N/A")

# The synthetic core.work corpus chunk the synthetic registry cites verbatim (reused
# from test_auditor.py's tiny index — a FIXTURE, never a production value).
_TINY_ID = "pr-pdi/tiny.md#000"
_TINY_QUOTE = "Permanent residence applicants must provide police certificates"


def _git_root() -> Path | None:
    """The git work-tree root, or ``None`` when this is not a git checkout.

    Copied from ``test_dli_conformance.py`` so the frozen-surface byte-identity
    proof skips cleanly (never fails) on a fresh export / non-git tree.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return Path(out.stdout.strip())


_GIT_ROOT = _git_root()


def _work_row(rule_id: str, mc: MachineCheck, check_type: str = "threshold") -> RuleRow:
    """A grounded synthetic core.work rule row citing the tiny chunk verbatim."""
    return RuleRow(
        rule_id=rule_id, factor_group="core_human_capital", factor_ids=["core.work"],
        check_type=check_type, query="police certificates",
        selector=Selector(
            family="pr-pdi",
            marker=_TINY_QUOTE,
            require_title_contains="Tiny PR doc",
        ),
        claim_text="A grounded core rule.",
        citations=[Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
        machine_check=mc,
        volatility=VolatilityMeta(volatility="volatile", source_family="pr-pdi"))


def _work_registry() -> Registry:
    """A grounded synthetic core.work registry (teer + hours ceiling + window)."""
    return Registry(rows=[
        _work_row("core.work.definition",
                  MachineCheck(kind="accepted_enum", field="teer",
                               accepted_values=[AcceptedValue(value=v)
                                                for v in ("0", "1", "2", "3")]),
                  check_type="admissibility"),
        _work_row("core.work.hours",
                  MachineCheck(kind="threshold", field="hours_per_week",
                               max_value=30)),
        _work_row("core.work.window",
                  MachineCheck(kind="validity_window",
                               field="work_reference_period", window_days=3653)),
    ])


def _card_fingerprint(card) -> tuple:
    """The byte-for-behavior identity tuple NOC-03 mandates stay unchanged."""
    return (
        card.verdict,
        card.reason_code,
        card.confirmed_value,
        tuple(sorted(card.evidence_ids)),
        card.substantiated_points,
        card.score_delta,
    )


# --------------------------------------------------------------------------- #
# The exhaustive never-green sweep (NOC-03 — no duty-review path greens).
# --------------------------------------------------------------------------- #
@unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
class TestNoNocPathGreens(unittest.TestCase):
    """Every ``review_noc_duties`` outcome is AT-RISK/GAP/N/A — never SUBSTANTIATED.

    Drives the REAL ``noc_review.review_noc_duties`` over an exhaustive input matrix
    (none / pending-only / partial / all-rejected / Layer-1-stale / Layer-2-drifted /
    changed-sha / all-confirmed-fresh, plus a GROUPED sub-occupation NOC), asserting
    for EVERY case ``status != "SUBSTANTIATED"``, ``status in {AT-RISK,GAP,N/A}``, that
    no score / ``crs_points`` key exists (so no non-zero CRS/points delta can ever be
    produced), and ``confirmed_count <= duty_count`` (T43-02/03/04).
    """

    def setUp(self) -> None:
        self.db = str(_REAL_DB)

    def _scenario(self, build) -> dict:
        """Run *build* in a fresh throwaway vault + PR_PERSONAL_DIR; return the dict."""
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": td}):
                v = vault.open_vault("default")
                vault.create_candidate(v, "default")
                return build(v)

    # -- the input-class builders (all through the SHIPPED generator + verb) -- #
    def _none(self, v):
        # A well-formed code with no corpus file -> no current worksheet -> N/A.
        return noc_review.review_noc_duties(v, self.db, "99999")

    def _pending_only(self, v):
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC)
        return noc_review.review_noc_duties(v, self.db, _NOC)

    def _partial(self, v):
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC)
        _confirm(v, _current_duty_value_id(v, self.db, _NOC, f"{_NOC}:1:00"))
        for i in range(3):
            _confirm(v, _current_duty_value_id(v, self.db, _NOC, f"{_NOC}:{i:02d}"))
        return noc_review.review_noc_duties(v, self.db, _NOC)

    def _all_rejected(self, v):
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC)
        for val in _list_review_noc(v):
            _confirm(v, val.value_id, "reject")
        return noc_review.review_noc_duties(v, self.db, _NOC)

    def _layer1_stale(self, v):
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC)
        _confirm_all(v)
        _make_layer1_stale(v, _current_duty_value_id(v, self.db, _NOC, f"{_NOC}:00"))
        return noc_review.review_noc_duties(v, self.db, _NOC)

    def _layer2_drift(self, v):
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC)
        _confirm_all(v)
        _drift_layer2_quote(v, _current_duty_value_id(v, self.db, _NOC, f"{_NOC}:00"))
        return noc_review.review_noc_duties(v, self.db, _NOC)

    def _changed_sha(self, v):
        # Seed an OLD non-current confirmed value for duty 00 (superseded duty_sha),
        # then the current worksheet mints the fresh duty-00 value; confirm it. The
        # old drifted value must be IGNORED so the duty is counted exactly once.
        vault.upsert_profile_factor(v, _review_noc_factor())
        src = Path(tempfile.mkdtemp()) / "prior.md"
        src.write_text("# prior\n", encoding="utf-8")
        doc = vault.import_document(v, "default", src, doc_type="noc_worksheet")
        run = vault.record_extraction_run(
            v, document_id=doc.document_id, parser_version="1")
        old_id = vault.add_extracted_value(
            v, document_id=doc.document_id, page_id=None, factor_id="review.noc",
            field_name="noc_duty", raw_text="old drifted duty text",
            normalized_value={"duty_id": f"{_NOC}:00", "duty_sha": "0000oldsha00",
                              "citation": f"noc-2021/noc-{_NOC}.md#002"},
            bbox=None, extractor_confidence=None, quality_flag="ok",
            extraction_run_id=run)
        _confirm(v, old_id)
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC)
        _confirm(v, _current_duty_value_id(v, self.db, _NOC, f"{_NOC}:00"))
        return noc_review.review_noc_duties(v, self.db, _NOC)

    def _all_confirmed_fresh(self, v):
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC)
        _confirm_all(v)
        return noc_review.review_noc_duties(v, self.db, _NOC)

    def _grouped_pending(self, v):
        # A grouped sub-occupation NOC (headers preserved verbatim as items).
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC_GROUPED)
        return noc_review.review_noc_duties(v, self.db, _NOC_GROUPED)

    def _grouped_all_confirmed(self, v):
        noc_worksheet.generate_worksheet(v, self.db, "default", _NOC_GROUPED)
        _confirm_all(v)
        return noc_review.review_noc_duties(v, self.db, _NOC_GROUPED)

    def test_no_review_outcome_is_substantiated_or_scored(self) -> None:
        cases = {
            "none": self._none,
            "pending_only": self._pending_only,
            "partial": self._partial,
            "all_rejected": self._all_rejected,
            "layer1_stale": self._layer1_stale,
            "layer2_drift": self._layer2_drift,
            "changed_sha": self._changed_sha,
            "all_confirmed_fresh": self._all_confirmed_fresh,
            "grouped_pending": self._grouped_pending,
            "grouped_all_confirmed": self._grouped_all_confirmed,
        }
        for name, build in cases.items():
            with self.subTest(case=name):
                res = self._scenario(build)
                # (1) Never green.
                self.assertNotEqual(res["status"], _FORBIDDEN_VERDICT,
                                    f"{name}: sidecar returned SUBSTANTIATED")
                # (2) Always one of the safe statuses.
                self.assertIn(res["status"], _ALLOWED_STATUSES,
                              f"{name}: unexpected status {res['status']!r}")
                # (3) No score / CRS-points key can EVER cross the boundary — so no
                #     non-zero CRS/points delta is representable. The dict is the
                #     closed PII-light PUBLIC_FIELDS set, which carries no points key.
                self.assertNotIn("crs_points", res, name)
                self.assertNotIn("score", res, name)
                self.assertNotIn("substantiated_points", res, name)
                self.assertEqual(tuple(res.keys()), noc_review.PUBLIC_FIELDS, name)
                # (4) A confirmed count can NEVER exceed the current duty_count.
                self.assertLessEqual(res["confirmed_count"], res["duty_count"], name)

        # Spot-check the poles are correctly labelled: the absent NOC is N/A; the fully
        # confirmed+fresh set caps at AT-RISK duty_review_manual (STILL not green).
        self.assertEqual(self._scenario(self._none)["status"], "N/A")
        term = self._scenario(self._all_confirmed_fresh)
        self.assertEqual((term["status"], term["reason"]),
                         ("AT-RISK", "duty_review_manual"))
        # The changed-sha class counts the drifted duty exactly once.
        changed = self._scenario(self._changed_sha)
        self.assertEqual(changed["confirmed_count"], 1)
        self.assertLessEqual(changed["confirmed_count"], changed["duty_count"])


# --------------------------------------------------------------------------- #
# The frozen surfaces stay byte-for-byte frozen (T43-06).
# --------------------------------------------------------------------------- #
@unittest.skipUnless(
    _GIT_ROOT is not None,
    "not a git checkout — the frozen-surface byte-identity diff proof did NOT run",
)
class TestFrozenSurfacesByteIdentity(unittest.TestCase):
    """The FREEZE set is byte-for-byte identical to HEAD.

    Copies ``test_dli_conformance.py``'s ``git diff --quiet HEAD`` byte-identity
    pattern, scoped to the four surfaces NOC-03 mandates stay frozen, so a green run
    proves ``core.work``'s decider, the CRS award chokepoints, the public envelope /
    private card contracts, and the auditor registry/grid drifted ZERO this phase.
    Skips cleanly outside a git checkout (structural-only on a fresh export).
    """

    def test_freeze_set_unchanged_vs_head(self) -> None:
        assert _GIT_ROOT is not None  # for type-checkers; guarded by skipUnless
        for rel in _FREEZE_SET:
            with self.subTest(frozen=rel):
                self.assertTrue((_GIT_ROOT / rel).is_file(),
                                f"frozen surface missing: {rel}")
                result = subprocess.run(
                    ["git", "diff", "--quiet", "HEAD", "--", rel], cwd=_GIT_ROOT)
                self.assertEqual(
                    result.returncode, 0,
                    f"{rel} changed vs HEAD — the FROZEN NOC-03 surface MUST stay "
                    "byte-for-byte identical this phase")


# --------------------------------------------------------------------------- #
# The sidecar is inert by construction (T43-06).
# --------------------------------------------------------------------------- #
class TestSidecarInert(unittest.TestCase):
    """``noc_review`` is unregistered, off-grid, and imports no auditor.

    Neither the sidecar nor its inert ``review.noc`` factor is a CRS decider or a grid
    factor, so it can never be summed into a ``PublicAuditEnvelope`` (structural half
    of T43-06; the runtime envelope half lives in the isolation class).
    """

    def test_sidecar_not_registered_as_a_decider(self) -> None:
        auditors.load_all()
        # The sidecar function is NOT any registered decider value.
        self.assertNotIn(
            noc_review.review_noc_duties,
            getattr(auditors, "_REGISTRY", {}).values())
        # review.noc resolves to the fail-closed AT-RISK default, never a NOC decider.
        self.assertIs(auditors.resolve("review.noc"), auditors._default_decider)
        self.assertNotIn("review.noc", getattr(auditors, "_REGISTRY", {}))

    def test_review_noc_absent_from_full_grid(self) -> None:
        self.assertNotIn("review.noc", auditors.FULL_GRID_FACTORS)
        # No NOC-flavoured factor sneaks onto the grid at all.
        self.assertFalse(
            [f for f in auditors.FULL_GRID_FACTORS if "noc" in f.lower()],
            "a NOC factor leaked onto FULL_GRID_FACTORS")

    def test_sidecar_imports_nothing_from_auditors(self) -> None:
        # Prose-immune AST scan: a docstring that MENTIONS crawler.auditors must not
        # false-trip — only ACTUAL Import / ImportFrom nodes count.
        tree = ast.parse(Path(noc_review.__file__).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
                imported.extend(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        self.assertFalse(
            any(m == "crawler.auditors" or m.startswith("crawler.auditors.")
                for m in imported),
            f"noc_review must import nothing from crawler.auditors; saw {imported}")


# --------------------------------------------------------------------------- #
# The returned dict is a closed PII-light set (T43-04).
# --------------------------------------------------------------------------- #
class TestSidecarPiiLightClosedSet(unittest.TestCase):
    """The sidecar dict keys are EXACTLY the closed ``PUBLIC_FIELDS`` (no PII)."""

    def test_public_fields_is_a_closed_pii_light_set(self) -> None:
        # Structural: the contract constant carries no raw_text / ev_ id / path key.
        self.assertEqual(
            set(noc_review.PUBLIC_FIELDS),
            {"noc_code", "duty_count", "confirmed_count",
             "status", "reason", "citations"})
        for field in noc_review.PUBLIC_FIELDS:
            self.assertNotIn(field, ("raw_text", "evidence_id", "ev_id", "path"))

    @unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
    def test_returned_dict_is_exactly_public_fields_no_pii(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": td}):
                v = vault.open_vault("default")
                vault.create_candidate(v, "default")
                noc_worksheet.generate_worksheet(v, str(_REAL_DB), "default", _NOC)
                _confirm_all(v)
                res = noc_review.review_noc_duties(v, str(_REAL_DB), _NOC)
                # Keys equal the closed constant EXACTLY, in order.
                self.assertEqual(tuple(res.keys()), noc_review.PUBLIC_FIELDS)
                blob = json.dumps(res)
                self.assertNotIn("ev_", blob)          # no evidence id
                self.assertNotIn(str(v.root), blob)    # no absolute path
                # Citations are the PII-light chunk_id set only.
                self.assertEqual(res["citations"], [
                    f"noc-2021/noc-{_NOC}.md#001",
                    f"noc-2021/noc-{_NOC}.md#002",
                    f"noc-2021/noc-{_NOC}.md#003"])


# --------------------------------------------------------------------------- #
# Runtime factor-isolation base: synthetic core.work corpus + pinned NOC corpus.
# --------------------------------------------------------------------------- #
class _CoreWorkIsolationCase(unittest.TestCase):
    """A tmp vault with a SYNTHETIC core.work corpus (``self.db``) for the frozen grid
    audit AND the PINNED NOC corpus (``self.real_db``) for the worksheet generator.

    The two corpora are independent: ``core.work`` is audited over the synthetic index
    its synthetic registry cites; the NOC worksheet resolves the pinned corpus. Both
    live in the SAME vault, which is the whole point — confirming ``review.noc`` values
    must not perturb the ``core.work`` card.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self.root = _make_index_corpus(Path(self._tmp.name))
        self.db = str(Path(self._tmp.name) / "index.db")     # synthetic (core.work)
        searchindex.build_index(self.root, Path(self.db))
        self.work_registry = _work_registry()
        self.work_registry_fingerprint = crs_rules.registry_fingerprint(
            self.work_registry)
        self.real_db = str(_REAL_DB)                          # pinned (NOC worksheet)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _new_vault(self) -> vault.Vault:
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        return v

    def _seed_core_work(self, v: vault.Vault) -> None:
        """Seed + confirm a real core.work claim so its card is a real verdict."""
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id="core.work", factor_group="core_human_capital",
            claimed_points=40, claimed_value=1.0, source="user_entry"))
        src = Path(self._tmp.name) / "work_ref.pdf"
        src.write_bytes(b"%PDF-1.4 synthetic work letter")
        doc = vault.import_document(
            v, "default", src, doc_type="employment_reference_letter")
        run = vault.record_extraction_run(
            v, document_id=doc.document_id,
            parser_version=vault.current_parser_version())
        for field, value in {"employment_start": "2020-01-01",
                             "employment_end": "2021-12-31",
                             "hours_per_week": 40, "teer": "1"}.items():
            vid = vault.add_extracted_value(
                v, document_id=doc.document_id, page_id=None, factor_id="core.work",
                field_name=field, raw_text=str(value), normalized_value=value,
                bbox=None, extractor_confidence=0.9, quality_flag="ok",
                extraction_run_id=run)
            vault.confirm_value(
                v,
                vid,
                "confirm",
                registry_fingerprint=self.work_registry_fingerprint,
            )

    def _core_work_card(self, v: vault.Vault):
        report = auditor.audit_factor(
            v,
            "core.work",
            self.db,
            self.work_registry,
            registry_fingerprint=self.work_registry_fingerprint,
        )
        return report.factor_cards[0]


# The synthetic core.work fixture is fully hermetic and must run even when the
# git-ignored local NOC corpus is unavailable.
class TestCoreWorkSyntheticBaseline(_CoreWorkIsolationCase):
    def test_confirmed_synthetic_claim_is_substantiated(self) -> None:
        v = self._new_vault()
        self._seed_core_work(v)
        self.assertEqual(self._core_work_card(v).verdict, "SUBSTANTIATED")


# --------------------------------------------------------------------------- #
# B1 — the core.work card is byte-identical before/after confirmed review.noc (T43-08).
# --------------------------------------------------------------------------- #
class TestCoreWorkFactorIsolation(_CoreWorkIsolationCase):
    """Confirmed ``review.noc`` duty values NEVER touch the frozen ``core.work`` card."""

    @unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
    def test_core_work_card_byte_identical_before_after_confirmations(self) -> None:
        v = self._new_vault()
        self._seed_core_work(v)

        # Baseline: BEFORE any worksheet exists.
        baseline = self._core_work_card(v)
        self.assertEqual(baseline.verdict, "SUBSTANTIATED")  # a real, non-N/A verdict

        # Seed the inert review.noc factor + N born-pending duty values.
        noc_worksheet.generate_worksheet(v, self.real_db, "default", _NOC)
        after_worksheet = self._core_work_card(v)

        # Confirm SEVERAL duty values (lead + duties) via the shipped verb.
        _confirm(v, _current_duty_value_id(v, self.real_db, _NOC, f"{_NOC}:1:00"))
        for i in range(4):
            _confirm(v, _current_duty_value_id(v, self.real_db, _NOC, f"{_NOC}:{i:02d}"))
        after_confirm = self._core_work_card(v)

        # The card is byte-for-behavior IDENTICAL across all three snapshots.
        self.assertEqual(_card_fingerprint(baseline),
                         _card_fingerprint(after_worksheet))
        self.assertEqual(_card_fingerprint(baseline),
                         _card_fingerprint(after_confirm))
        # And FULLY byte-identical at the model level (no field drifts at all).
        self.assertEqual(baseline.model_dump(), after_worksheet.model_dump())
        self.assertEqual(baseline.model_dump(), after_confirm.model_dump())

        # NO NOC / worksheet evidence id ever enters the core.work card.
        for eid in after_confirm.evidence_ids:
            self.assertNotIn("noc", eid.lower(),
                             f"a NOC evidence id leaked into core.work: {eid}")
        # The sidecar meanwhile has genuinely counted the confirmations (proving the
        # isolation is not a no-op) — but STILL never greens.
        sub = noc_review.review_noc_duties(v, self.real_db, _NOC)
        self.assertNotEqual(sub["status"], _FORBIDDEN_VERDICT)
        self.assertGreater(sub["confirmed_count"], 0)

        # audit_eligible_values("core.work") never returns a review.noc value — the
        # structural reason the card cannot drift.
        core_vals = vault.audit_eligible_values(v, "core.work")
        self.assertTrue(all(x.factor_id == "core.work" for x in core_vals))
        self.assertFalse(any(x.factor_id == "review.noc" for x in core_vals))

    def test_review_noc_absent_from_full_grid(self) -> None:
        self.assertNotIn("review.noc", auditors.FULL_GRID_FACTORS)

    @unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
    def test_no_noc_id_in_built_public_envelope(self) -> None:
        v = self._new_vault()
        self._seed_core_work(v)
        noc_worksheet.generate_worksheet(v, self.real_db, "default", _NOC)
        _confirm_all(v)

        # A single-factor core.work envelope carries no NOC id.
        report = auditor.audit_factor(
            v,
            "core.work",
            self.db,
            self.work_registry,
            registry_fingerprint=self.work_registry_fingerprint,
        )
        env = to_public_envelope(
            report, f"output/crs-audit/{report.run_id}.json")
        blob = json.dumps(env.model_dump())
        for needle in ("review.noc", "noc-2021", "noc_duty", "noc_lead_statement"):
            self.assertNotIn(needle, blob, f"{needle} leaked into a PublicAuditEnvelope")

        # A FULL-GRID envelope likewise never surfaces a review.noc factor/id.
        full = auditor.run_full_audit(
            v,
            self.db,
            self.work_registry,
            registry_fingerprint=self.work_registry_fingerprint,
        )
        fenv = to_public_envelope(
            full, f"output/crs-audit/{full.run_id}.json")
        fdump = fenv.model_dump()
        self.assertNotIn("review.noc", [fv["factor_id"] for fv in fdump["verdicts"]])
        fblob = json.dumps(fdump)
        for needle in ("review.noc", "noc-2021", "noc_duty"):
            self.assertNotIn(needle, fblob,
                             f"{needle} leaked into the full-grid envelope")


# --------------------------------------------------------------------------- #
# B1 / T43-09 — idempotent regeneration keeps core.work frozen + never inflates.
# --------------------------------------------------------------------------- #
@unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
class TestIdempotentRegenerationIsolation(_CoreWorkIsolationCase):
    """An exact rerun mints no duplicate row; a changed-sha rerun is counted once —
    both leave the ``core.work`` card byte-identical and never green (T43-09)."""

    def _review_rows(self, v: vault.Vault) -> list:
        return v.con.execute(
            "SELECT value_id, normalized_value_json, confirmation_status "
            "FROM extracted_values WHERE factor_id='review.noc' ORDER BY value_id"
        ).fetchall()

    def test_exact_rerun_no_duplicate_row_core_work_frozen(self) -> None:
        v = self._new_vault()
        self._seed_core_work(v)
        baseline = self._core_work_card(v).model_dump()

        first = noc_worksheet.generate_worksheet(v, self.real_db, "default", _NOC)
        # Confirm the lead + 4 duties, then snapshot the confirmed state.
        _confirm(v, _current_duty_value_id(v, self.real_db, _NOC, f"{_NOC}:1:00"))
        for i in range(4):
            _confirm(v, _current_duty_value_id(v, self.real_db, _NOC, f"{_NOC}:{i:02d}"))
        rows_before = self._review_rows(v)
        states_before = {r["value_id"]: r["confirmation_status"] for r in rows_before}

        # EXACT rerun: identical envelope, no duplicate row, confirmed state preserved.
        second = noc_worksheet.generate_worksheet(v, self.real_db, "default", _NOC)
        self.assertEqual(second["worksheet_doc_id"], first["worksheet_doc_id"])
        self.assertEqual(second["value_ids"], first["value_ids"])
        self.assertEqual(second["duty_count"], first["duty_count"])
        rows_after = self._review_rows(v)
        self.assertEqual(len(rows_after), len(rows_before),
                         "an exact rerun minted a duplicate review.noc row")
        states_after = {r["value_id"]: r["confirmation_status"] for r in rows_after}
        self.assertEqual(states_after, states_before,
                         "an exact rerun changed a confirmed value's state")

        # The core.work card is STILL byte-identical to the pre-worksheet baseline.
        self.assertEqual(self._core_work_card(v).model_dump(), baseline)
        # And the sidecar still never greens.
        sub = noc_review.review_noc_duties(v, self.real_db, _NOC)
        self.assertNotEqual(sub["status"], _FORBIDDEN_VERDICT)
        self.assertLessEqual(sub["confirmed_count"], sub["duty_count"])

    def test_changed_sha_rerun_counted_once_core_work_frozen(self) -> None:
        v = self._new_vault()
        self._seed_core_work(v)
        baseline = self._core_work_card(v).model_dump()

        # A changed-duty_sha rerun: an OLD confirmed value for duty 00 carries a
        # SUPERSEDED duty_sha; the current worksheet mints the fresh duty-00 value.
        vault.upsert_profile_factor(v, _review_noc_factor())
        prior = Path(self._tmp.name) / "prior.md"
        prior.write_text("# prior\n", encoding="utf-8")
        pdoc = vault.import_document(v, "default", prior, doc_type="noc_worksheet")
        prun = vault.record_extraction_run(
            v, document_id=pdoc.document_id, parser_version="1")
        old_id = vault.add_extracted_value(
            v, document_id=pdoc.document_id, page_id=None, factor_id="review.noc",
            field_name="noc_duty", raw_text="old drifted duty text",
            normalized_value={"duty_id": f"{_NOC}:00", "duty_sha": "0000oldsha00",
                              "citation": f"noc-2021/noc-{_NOC}.md#002"},
            bbox=None, extractor_confidence=None, quality_flag="ok",
            extraction_run_id=prun)
        _confirm(v, old_id)  # the OLD (non-current) value is confirmed+eligible

        noc_worksheet.generate_worksheet(v, self.real_db, "default", _NOC)
        new_id = _current_duty_value_id(v, self.real_db, _NOC, f"{_NOC}:00")
        self.assertNotEqual(new_id, old_id)
        _confirm(v, new_id)  # confirm the CURRENT-sha value too

        sub = noc_review.review_noc_duties(v, self.real_db, _NOC)
        # Duty 00 is counted EXACTLY once (via the current value); old sha ignored.
        self.assertEqual(sub["confirmed_count"], 1)
        self.assertLessEqual(sub["confirmed_count"], sub["duty_count"])
        self.assertNotEqual(sub["status"], _FORBIDDEN_VERDICT)
        # The old drifted value is UNTOUCHED (same stale sha, still confirmed).
        old = vault.get_extracted_value(v, old_id)
        self.assertEqual(old.normalized_value["duty_sha"], "0000oldsha00")
        self.assertEqual(old.confirmation_status, "confirmed")
        # The core.work card is byte-identical to the pre-worksheet baseline.
        self.assertEqual(self._core_work_card(v).model_dump(), baseline)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
