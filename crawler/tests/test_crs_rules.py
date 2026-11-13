"""Corpus-less synthetic tests for the PII-free CRS rule-registry ENGINE (Phase 31 — Plan 01).

These ALWAYS-RUN in CI. They build a SYNTHETIC FTS5 index in a ``TemporaryDirectory``
(via ``crawler.tests.test_searchindex._make_index_corpus`` + ``searchindex.build_index``
— NEVER the real git-ignored ``corpus/``) and drive the whole registry loop against
it, exactly like ``TestDocumentAgentsConformanceSynthetic``. A corpus-less green here
is therefore a real MECHANISM proof (the engine calls the SHIPPED grounding gate +
resolver end-to-end), not just static structure.

Covered:
  * schema load from YAML (fail-closed on a malformed row);
  * ``row_to_answer`` shape;
  * ``validate_registry`` grounds a verbatim-quote row and FAILS-CLOSED on a
    quote that is not in the cited chunk (``quote_not_in_chunk``);
  * ``retrieve_what_you_cite`` re-selects the cited chunk and grounds it, and flags
    a row whose baked query+selector select a DIFFERENT chunk than it cites;
  * ``coverage_report`` detects a missing required rule_id and surfaces a gap:true row;
  * the engine REUSES the frozen gate/resolver (grep-asserted), never forks them.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from crawler import crs_rules, searchindex
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    RuleRow,
    Registry,
    Selector,
    VolatilityMeta,
)
from crawler.tests.test_searchindex import _make_index_corpus

# Verbatim spans of the synthetic chunks (see test_searchindex TINY_BODY / STATUTE_BODY).
_TINY_ID = "pr-pdi/tiny.md#000"
_TINY_QUOTE = "Permanent residence applicants must provide police certificates"
_STATUTE_ID = "legislation-irpa/statute.md#000"
_STATUTE_QUOTE = "an officer may examine an applicant"


def _row(
    rule_id: str,
    *,
    factor_group: str = "core_human_capital",
    factor_ids: list[str] | None = None,
    query: str = "police certificates",
    selector: Selector | None = None,
    claim_text: str = "A grounded CRS rule.",
    citations: list[Citation] | None = None,
    machine_check: MachineCheck | None = None,
    gap: bool = False,
    gap_reason: str | None = None,
) -> RuleRow:
    """Build a RuleRow with sensible synthetic defaults (tiny-chunk citation)."""
    return RuleRow(
        rule_id=rule_id,
        factor_group=factor_group,
        factor_ids=factor_ids or [rule_id],
        check_type="admissibility",
        query=query,
        selector=selector or Selector(family="pr-pdi"),
        claim_text=claim_text,
        citations=citations or [Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
        machine_check=machine_check or MachineCheck(kind="accepted_enum", field="x"),
        volatility=VolatilityMeta(volatility="stable", source_family="pr-pdi"),
        gap=gap,
        gap_reason=gap_reason,
    )


class TestRegistryEngineSynthetic(unittest.TestCase):
    """Drive load/validate/retrieve/coverage against a SYNTHETIC tempdir index."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
        self.db = Path(self._tmp.name) / "index.db"
        searchindex.build_index(self.root, self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ---- load_registry ---------------------------------------------------- #

    def test_load_registry_reads_yaml_and_validates(self) -> None:
        data_dir = Path(self._tmp.name) / "rules"
        data_dir.mkdir()
        payload = {
            "rows": [
                {
                    "rule_id": "core.language.first.approved",
                    "factor_group": "core_human_capital",
                    "factor_ids": ["core.language.first"],
                    "check_type": "admissibility",
                    "query": "police certificates",
                    "selector": {"family": "pr-pdi"},
                    "claim_text": "A grounded CRS rule.",
                    "citations": [{"chunk_id": _TINY_ID, "quote": _TINY_QUOTE}],
                    "machine_check": {"kind": "accepted_enum", "field": "test_type"},
                    "volatility": {"volatility": "stable", "source_family": "pr-pdi"},
                }
            ]
        }
        (data_dir / "core.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
        # An excluded file (prefixed "_") and COVERAGE.md must be skipped.
        (data_dir / "_scratch.yaml").write_text("rows: [not, a, valid, row]\n", encoding="utf-8")
        (data_dir / "COVERAGE.md").write_text("# coverage\n", encoding="utf-8")

        reg = crs_rules.load_registry(data_dir)
        self.assertEqual(len(reg.rows), 1)
        self.assertEqual(reg.rows[0].rule_id, "core.language.first.approved")

    def test_load_registry_fails_closed_on_malformed_row(self) -> None:
        data_dir = Path(self._tmp.name) / "rules_bad"
        data_dir.mkdir()
        # factor_group is out of vocabulary -> pydantic ValidationError at load.
        payload = {
            "rows": [
                {
                    "rule_id": "bad.row",
                    "factor_group": "NOT_A_GROUP",
                    "factor_ids": ["bad"],
                    "check_type": "admissibility",
                    "query": "q",
                    "selector": {"family": "pr-pdi"},
                    "claim_text": "x",
                    "citations": [{"chunk_id": _TINY_ID, "quote": "x"}],
                    "machine_check": {"kind": "accepted_enum", "field": "x"},
                    "volatility": {"volatility": "stable", "source_family": "pr-pdi"},
                }
            ]
        }
        (data_dir / "bad.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
        with self.assertRaises(Exception):
            crs_rules.load_registry(data_dir)

    def test_validated_snapshot_rejects_every_unavailable_registry_shape(
            self) -> None:
        root = Path(self._tmp.name)
        missing = root / "snapshot-missing"
        empty = root / "snapshot-empty"
        empty.mkdir()
        malformed = root / "snapshot-malformed"
        malformed.mkdir()
        (malformed / "rules.yaml").write_text(
            "rows: [unterminated", encoding="utf-8")
        invalid = root / "snapshot-invalid"
        invalid.mkdir()
        (invalid / "rules.yaml").write_text(
            yaml.safe_dump({"rows": [{}]}), encoding="utf-8")
        incomplete = root / "snapshot-incomplete"
        incomplete.mkdir()
        (incomplete / "rules.yaml").write_text(
            yaml.safe_dump({"rows": [_row("core.age.synthetic").model_dump(
                mode="json")]}),
            encoding="utf-8",
        )
        io_error = root / "snapshot-io"
        io_error.mkdir()
        io_file = io_error / "rules.yaml"
        io_file.write_text("rows: []\n", encoding="utf-8")

        for label, directory in (
                ("missing", missing),
                ("empty", empty),
                ("malformed", malformed),
                ("pydantic-invalid", invalid),
                ("incomplete", incomplete)):
            with self.subTest(case=label):
                with self.assertRaisesRegex(
                        crs_rules.RegistryUnavailable,
                        "^CRS rule registry unavailable$") as caught:
                    crs_rules.load_registry_snapshot(directory)
                self.assertNotIn(str(directory), str(caught.exception))

        with mock.patch.object(
                Path, "read_text", side_effect=OSError("private path detail")):
            with self.assertRaisesRegex(
                    crs_rules.RegistryUnavailable,
                    "^CRS rule registry unavailable$"):
                crs_rules.load_registry_snapshot(io_error)

    def test_validated_snapshot_strictly_parses_every_yaml_file(self) -> None:
        source = Path(crs_rules.DEFAULT_DATA_DIR)
        root = Path(self._tmp.name)
        payloads = {
            "empty-mapping": "{}\n",
            "null-document": "null\n",
            "rows-null": "rows: null\n",
            "rows-empty": "rows: []\n",
            "rows-wrong-type": "rows: not-a-list\n",
            "top-level-wrong-type": "- rows\n",
            "malformed": "rows: [unterminated\n",
        }
        for label, payload in payloads.items():
            with self.subTest(case=label):
                directory = root / f"strict-{label}"
                shutil.copytree(source, directory)
                (directory / "zzz-invalid.yaml").write_text(
                    payload, encoding="utf-8")
                with self.assertRaisesRegex(
                        crs_rules.RegistryUnavailable,
                        "^CRS rule registry unavailable$") as caught:
                    crs_rules.load_registry_snapshot(directory)
                self.assertNotIn(str(directory), str(caught.exception))

    def test_validated_snapshot_requires_each_load_bearing_auxiliary_rule(
            self) -> None:
        source = Path(crs_rules.DEFAULT_DATA_DIR)
        self.assertEqual(
            set(crs_rules.REQUIRED_AUXILIARY_RULE_IDS),
            {"study.dli.designation", "study.r73_definition"},
        )

        no_aux_file = Path(self._tmp.name) / "without-aux-file"
        shutil.copytree(source, no_aux_file)
        (no_aux_file / "study_dli.yaml").unlink()
        with self.assertRaises(crs_rules.RegistryUnavailable):
            crs_rules.load_registry_snapshot(no_aux_file)

        for rule_id in crs_rules.REQUIRED_AUXILIARY_RULE_IDS:
            with self.subTest(missing_rule=rule_id):
                directory = Path(self._tmp.name) / (
                    "without-" + rule_id.replace(".", "-"))
                shutil.copytree(source, directory)
                path = directory / "study_dli.yaml"
                payload = yaml.safe_load(path.read_text(encoding="utf-8"))
                payload["rows"] = [
                    row for row in payload["rows"]
                    if row["rule_id"] != rule_id
                ]
                path.write_text(yaml.safe_dump(payload), encoding="utf-8")

                # The scored structural grid remains complete, proving the
                # auxiliary manifest (not grid coverage) causes this refusal.
                low_level = crs_rules.load_registry(directory)
                self.assertTrue(crs_rules.coverage_report(low_level)["complete"])
                with self.assertRaisesRegex(
                        crs_rules.RegistryUnavailable,
                        "^CRS rule registry unavailable$"):
                    crs_rules.load_registry_snapshot(directory)

        for rule_id in crs_rules.REQUIRED_AUXILIARY_RULE_IDS:
            with self.subTest(gap_rule=rule_id):
                directory = Path(self._tmp.name) / (
                    "gap-" + rule_id.replace(".", "-"))
                shutil.copytree(source, directory)
                path = directory / "study_dli.yaml"
                payload = yaml.safe_load(path.read_text(encoding="utf-8"))
                for row in payload["rows"]:
                    if row["rule_id"] == rule_id:
                        row["gap"] = True
                        row["gap_reason"] = "synthetic required-row gap"
                path.write_text(yaml.safe_dump(payload), encoding="utf-8")

                with self.assertRaisesRegex(
                        crs_rules.RegistryUnavailable,
                        "^CRS rule registry unavailable$"):
                    crs_rules.load_registry_snapshot(directory)

    def test_validated_snapshot_fingerprints_the_same_real_registry(self) -> None:
        snapshot = crs_rules.load_registry_snapshot()
        self.assertTrue(snapshot.registry.rows)
        self.assertTrue(crs_rules.coverage_report(
            snapshot.registry)["complete"])
        self.assertEqual(
            snapshot.fingerprint,
            crs_rules.registry_fingerprint(snapshot.registry),
        )

    # ---- row_to_answer ---------------------------------------------------- #

    def test_row_to_answer_shape_is_pii_free_gate_object(self) -> None:
        ans = crs_rules.row_to_answer(_row("core.age.table"))
        self.assertEqual(set(ans), {"question", "claims", "basis", "abstentions", "prose"})
        self.assertEqual(ans["basis"], [])
        self.assertEqual(ans["abstentions"], [])
        self.assertEqual(ans["prose"], "")
        self.assertGreaterEqual(len(ans["claims"]), 1)
        for claim in ans["claims"]:
            self.assertEqual(set(claim), {"id", "text", "citations", "quote"})

    # ---- validate_registry ------------------------------------------------ #

    def test_validate_registry_grounds_verbatim_quote(self) -> None:
        reg = Registry(rows=[_row("core.age.table")])
        result = crs_rules.validate_registry(reg, self.db)
        self.assertEqual(result["violations"], [], result)
        self.assertEqual(result["grounded"], result["total"])
        self.assertGreaterEqual(result["total"], 1)

    def test_validate_registry_fails_closed_on_quote_not_in_chunk(self) -> None:
        bad = _row(
            "core.age.table",
            citations=[Citation(chunk_id=_TINY_ID, quote="this span is absolutely not present zzz")],
        )
        result = crs_rules.validate_registry(Registry(rows=[bad]), self.db)
        self.assertEqual(len(result["violations"]), 1, result)
        self.assertEqual(result["violations"][0]["rule_id"], "core.age.table")
        reasons = result["violations"][0]["reasons"]
        self.assertIn("quote_not_in_chunk", reasons)

    def test_validate_registry_skips_gap_rows(self) -> None:
        # A gap:true row cannot ground; it must be skipped, not counted as a violation.
        gap_row = _row(
            "core.work.definition",
            citations=[Citation(chunk_id=_TINY_ID, quote="placeholder ungroundable text zzz")],
            gap=True,
            gap_reason="exact NOC TEER hours rule not in current corpus",
        )
        result = crs_rules.validate_registry(Registry(rows=[gap_row]), self.db)
        self.assertEqual(result["violations"], [], result)

    # ---- retrieve_what_you_cite ------------------------------------------- #

    def test_retrieve_reselects_cited_chunk_and_grounds(self) -> None:
        row = _row(
            "core.age.table",
            query="police certificates",
            selector=Selector(family="pr-pdi", marker=_TINY_QUOTE),
            citations=[Citation(chunk_id=_TINY_ID, quote=_TINY_QUOTE)],
        )
        report = crs_rules.retrieve_what_you_cite(Registry(rows=[row]), self.db)
        entry = report["core.age.table"]
        self.assertEqual(entry["selected_chunk_id"], _TINY_ID)
        self.assertTrue(entry["agrees_with_citation"])
        self.assertTrue(entry["grounds"])

    def test_retrieve_flags_row_that_cites_a_different_chunk(self) -> None:
        # query+selector select the tiny chunk, but the row CITES the statute chunk.
        row = _row(
            "core.age.table",
            query="police certificates",
            selector=Selector(family="pr-pdi", marker=_TINY_QUOTE),
            citations=[Citation(chunk_id=_STATUTE_ID, quote=_STATUTE_QUOTE)],
        )
        report = crs_rules.retrieve_what_you_cite(Registry(rows=[row]), self.db)
        entry = report["core.age.table"]
        self.assertEqual(entry["selected_chunk_id"], _TINY_ID)
        self.assertFalse(entry["agrees_with_citation"])

    # ---- coverage_report -------------------------------------------------- #

    def test_coverage_report_detects_missing_required_id(self) -> None:
        # An empty registry -> every required label is missing; complete is False.
        cov = crs_rules.coverage_report(Registry(rows=[]))
        self.assertFalse(cov["complete"])
        core = cov["by_group"]["core_human_capital"]
        self.assertIn("core.age", core["required"])
        self.assertIn("core.age", core["missing"])
        self.assertEqual(core["present"], [])

    def test_coverage_report_moves_present_and_surfaces_gap(self) -> None:
        rows = [
            _row("core.age.table", factor_group="core_human_capital"),
            _row(
                "core.work.definition",
                factor_group="core_human_capital",
                gap=True,
                gap_reason="ungroundable in current corpus",
            ),
        ]
        cov = crs_rules.coverage_report(Registry(rows=rows))
        core = cov["by_group"]["core_human_capital"]
        self.assertIn("core.age", core["present"])
        self.assertIn("core.work", core["gaps"])
        self.assertNotIn("core.age", core["missing"])

    # ---- frozen-gate reuse ------------------------------------------------ #

    def test_engine_reuses_frozen_gate_and_resolver(self) -> None:
        src = Path("crawler/crs_rules.py").read_text(encoding="utf-8")
        self.assertIn("grounding.check_answer", src)
        self.assertTrue("searchindex.search" in src or "searchindex.resolve" in src)


class TestNoInlinedVolatileRules(unittest.TestCase):
    """The static gate: volatile CRS thresholds may live ONLY in grounded rule rows.

    Every test name contains ``inlined`` so ``pytest -k inlined`` selects them.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_inlined_python_points_literal_is_flagged(self) -> None:
        p = self._write(
            "auditor_bad.py",
            "def score():\n    points = 200  # arranged-employment bonus\n    return points\n",
        )
        violations = crs_rules.no_inlined_volatile_rules([p])
        self.assertTrue(violations, "an inlined `points = 200` CRS literal must flag")
        self.assertEqual(violations[0]["path"], str(p))

    def test_inlined_markdown_clb_claim_is_flagged(self) -> None:
        p = self._write(
            "auditor_bad.md",
            "Award the applicant points when a CLB 9 result unlocks the 50-point cap.\n",
        )
        violations = crs_rules.no_inlined_volatile_rules([p])
        self.assertTrue(violations, "an inlined 'CLB 9 ... 50-point' prose claim must flag")

    def test_no_inlined_registry_sourced_python_is_clean(self) -> None:
        # Reads the volatile value from the grounded registry row — no literal.
        p = self._write(
            "auditor_ok.py",
            "def clamp(points, row):\n"
            "    cap = row.machine_check.cap_value\n"
            "    return min(points, cap)\n",
        )
        self.assertEqual(crs_rules.no_inlined_volatile_rules([p]), [])

    def test_no_inlined_comment_lines_do_not_self_trigger(self) -> None:
        p_py = self._write(
            "with_comment.py",
            "# This module explains the CLB 9 boundary and the 50 point cap in prose.\n"
            "def f(row):\n    return row.machine_check.cap_value\n",
        )
        p_md = self._write(
            "with_heading.md",
            "# CLB 9 and the 50 point cap\n\nSee the grounded registry rows for values.\n",
        )
        self.assertEqual(crs_rules.no_inlined_volatile_rules([p_py, p_md]), [])

    def test_no_inlined_registry_yaml_payload_is_clean(self) -> None:
        # Volatile numbers live ONLY inside machine_check payload + verbatim quote.
        p = self._write(
            "core.yaml",
            "rows:\n"
            "  - rule_id: transfer.cap.total\n"
            "    factor_group: skill_transferability\n"
            "    factor_ids: [transfer.cap.total]\n"
            "    check_type: cap\n"
            "    query: skill transferability maximum\n"
            "    selector:\n"
            "      family: guidance\n"
            "    claim_text: Total skill transferability points are capped.\n"
            "    citations:\n"
            "      - chunk_id: guidance/crs-criteria.md#010\n"
            "        quote: \"maximum of 100 points for skill transferability\"\n"
            "    machine_check:\n"
            "      kind: cap\n"
            "      field: skill_transferability_total\n"
            "      cap_value: 100\n"
            "    volatility:\n"
            "      volatility: stable\n"
            "      source_family: guidance\n",
        )
        self.assertEqual(crs_rules.no_inlined_volatile_rules([p]), [])


class TestSnapshotFreshnessBoundFingerprint(unittest.TestCase):
    """Drift coverage over a ``snapshot_max_age`` validity_window row shape (SAFE-09).

    Honest grounding rationale: the CONCRETE grounded DLI snapshot max-age value and
    its authoritative citation are a Phase 41 (STUDY-01) data responsibility — no
    authoritative "list is refreshed every N days" span is groundable in the current
    corpus — so NO bound row is shipped to ``crawler/data/crs_rules/*.yaml`` this phase
    (a non-gap row would fail whole-registry grounding; a ``gap:true`` non-required
    ``safe.*`` row would fail ``test_gap_rows_are_surfaced_by_coverage``). Phase 40
    proves the ``registry_fingerprint`` drift-coverage MECHANISM extends automatically
    to a freshness-bound row SHAPE — never a fabricated shipped value — using a
    SYNTHETIC grounded registry (mirroring ``test_crs_audit._validity_registry``).
    """

    @staticmethod
    def _freshness_bound_registry(window_days: int = 180) -> Registry:
        row = _row(
            "safe.dli_snapshot.max_age",
            machine_check=MachineCheck(
                kind="validity_window",
                field="snapshot_max_age",
                window_days=window_days,
                citation_index=0,
            ),
        )
        return Registry(rows=[row])

    def test_fingerprint_is_stable_64_hex(self) -> None:
        fp = crs_rules.registry_fingerprint(self._freshness_bound_registry())
        self.assertRegex(fp, r"^[0-9a-f]{64}$")

    def test_identical_registries_fingerprint_equal(self) -> None:
        # A byte-identical second registry fingerprints EQUAL (deterministic hash).
        a = crs_rules.registry_fingerprint(self._freshness_bound_registry())
        b = crs_rules.registry_fingerprint(self._freshness_bound_registry())
        self.assertEqual(a, b)

    def test_tampering_window_days_flips_freshness_fingerprint(self) -> None:
        # Tampering the grounded window_days flips registry_fingerprint (different
        # sha256) — drift coverage reaches a freshness-bound row shape for free.
        base = crs_rules.registry_fingerprint(self._freshness_bound_registry(180))
        tampered = crs_rules.registry_fingerprint(self._freshness_bound_registry(365))
        self.assertNotEqual(base, tampered)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
