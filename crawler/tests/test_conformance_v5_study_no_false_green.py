"""Phase 44 study-review no-false-green and frozen-surface conformance.

This gate drives the production sidecar, CLI, audit spine, shared grounding gate,
and read-only local corpus.  Applicant fixtures are synthetic and every vault is
temporary.  The ignored DLI family/index are fingerprinted at runtime rather than
being passed to ``git diff``.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pytest
import tomli

from crawler import (
    auditor,
    crs_rules,
    index_health,
    searchindex,
    study_review,
    vault,
)
from crawler import auditors
from crawler.models.crs_rules import Registry
from crawler.models.vault import CrsProfileFactor
from crawler.tests.test_dli_grounding import _GOLDEN_DLI, _regenerate
from crawler.tests.test_snapshot_health import _build_snapshot_index


pytestmark = pytest.mark.conformance

_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _ROOT / "corpus" / "index.db"
_DLI_ROOT = _ROOT / "corpus" / "dli"
_AS_OF = "2026-07-16T18:08:26Z"
_PUBLIC = set(study_review.PUBLIC_FIELDS)
_FIVE = {"schema_version", "ok", "command", "result", "error"}
_SAFE = {"AT-RISK", "GAP", "N/A"}
_LOCK_SHA = "5561be20ae437b6ecabd66f3c5948f744c1f6562cb0d8929f386466323b42753"
_PYPROJECT_SHA = "14a8f76981990a930d6b41ef0784d23140a81dd3ef4bfb4ffbb7627fee037121"
_SCHEMA_SHA = "9b35bc925c4ee39216980d4f74b937cd0b971c4f423116f1b84bf6bdb561fe50"
_DEPENDENCIES = {
    "pyyaml>=6.0,<7.0",
    "pydantic (>=2.13,<3.0)",
    "platformdirs (>=4.10,<5.0)",
    "github-copilot-sdk>=1.0.8,<1.1.0",
}
# Independently approved from the Phase 43 completion bytes (f9acd73/127ca2b).
# ``crs_rules.py`` was re-approved after the earlier Phase 44 deep-review fix.
# Phase 45 re-approved its complete MEC manifest/citation scanner, the
# injected-snapshot study seam, and the additive MEC CLI handler after their
# dedicated no-network/no-loader conformance passed.
# The report lifecycle surfaces below were intentionally approved together after
# the final crash-durability correction; ``vault.py`` remains intentionally absent.
_APPROVED_SOURCE_SHA = {
    "crawler/paths.py":
        "aeea71c1e256cf0b9606c204feee19252f6bcd09c0028984930d8ec937c61b4f",
    "crawler/audit_report.py":
        "4589ab3079d31c7df036ac13c22c2b767dae3c1b37207e3b13f6a67803f9c846",
    "crawler/study_review.py":
        "9865756a541f50b5c4411a73c148129a9cd0d837bb6ee76fa13228f94e935c96",
    "crawler/cli.py":
        "75a3055723706b6daecff3949bebb739119759daf29bde8ab12cf24f428988eb",
    "crawler/models/audit.py":
        "1ed3dbba6d899dbfa89aeb9753471e15353efa5623578b60bcaebd86c0880910",
    "crawler/crs_audit.py":
        "cac7049a2d5e7e5cf7832f521c8da316ba201780a1f9fe1d94eb9658c924f5ac",
    "crawler/crs_rules.py":
        "5e465b7b99069a25fdab160c94b38f90a612ed72360c89b355754c51e328662a",
    "crawler/dli_snapshot.py":
        "b283c12cb6d09907ce94be8aa61b8685ab2bffdd42ff740a6d99ea9fd34f4ca4",
    "crawler/auditors/__init__.py":
        "48305e49d8763c81ca41004c4081ec59b6cedf78f5e01f7e60e745f81626e01d",
    "crawler/auditors/core.py":
        "6f618a56411031ed893b22a5c1bc629739287a1f1384a263af45f6ff4b3a868a",
    "crawler/auditors/spouse.py":
        "658fa5dcc96cd13489b9a6b07f889038b1148a22e0b3f5df64be1ea50f9a906b",
    "crawler/auditors/transferability.py":
        "1c30956b337fd5b5c28140468cf219f20fc35e50e91b6d703801dfedcddfae9f",
    "crawler/index_health.py":
        "178c94defa92d1676803d209a5a8a1f0a2b741e80cf043b580795d1a5e75793a",
    "crawler/searchindex.py":
        "355aea86e4420aba9f16137325f7ca3101d48b942b8675437e89155e354e4a39",
    "crawler/grounding.py":
        "8163dcc92272d2f0dbd90d7fa27718a4c78018f01d4010c102d69e993d221f45",
}
_APPROVED_GOLDEN_SHA = {
    "O110120953397.md":
        "5a29cfb77d15ba9b0026e6ae7767a8ed841f3d31c7bb8f8e777cd83d37fe79c2",
    "O112937696097.md":
        "cb57aa5f89c15fb111876b756acf399d97040f0ccb83991d9bcd424a395da316",
    "O153601941355.md":
        "d7d9bb115e8b4f2bf245c4ebf354524753486b97974929b50fa50039d2957de2",
    "O19305471522.md":
        "0d0d2405372d7b37f1012e7352c708f59e041e3554f1e2943c69d13fbe966332",
    "O19332746152.md":
        "80fe0be5ef8745eb0cec181f498bf287831dea9a48a76ed6da2447b46a31b3e9",
    "manifest.json":
        "3e81cd71b10cedb89c86de4fcfb77d5c5473bafa9bca31b8be6e4f16a1fb833b",
}
_VALUES = {
    "institution_name": "University of Toronto",
    "dli_number": "O19332746152",
    "credential_level": "3+",
    "program_start": "2022-09-15",
    "program_end": "2026-04-30",
    "study_status": "graduated",
}
_CANDIDATES = (
    ("uoft", "O19332746152", "University of Toronto",
     "designation_historical_unproven"),
    ("details", "O246878951383",
     "Centre de formation professionnelle de l’Envolée",
     "pgwp_details_manual"),
    ("no", "O110032269317", "Eston College", "pgwp_no"),
)


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    from crawler import cli

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(argv)
    return rc, out.getvalue(), err.getvalue()


def _assert_safe(test: unittest.TestCase, result: dict, label: str = "") -> None:
    test.assertEqual(set(result), _PUBLIC, label)
    test.assertIn(result["status"], _SAFE, label)
    test.assertNotEqual(result["status"], "SUBSTANTIATED", label)
    for forbidden in ("substantiated_points", "score", "crs_points", "points"):
        test.assertNotIn(forbidden, result, label)


def _schema_fingerprint(con: sqlite3.Connection) -> str:
    rows = con.execute(
        "SELECT type,name,tbl_name,coalesce(sql,'') FROM sqlite_master "
        "WHERE type IN ('table','index') "
        "ORDER BY type,name,tbl_name,coalesce(sql,'')"
    ).fetchall()
    payload = json.dumps(
        [list(row) for row in rows],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _body_bytes(raw: bytes) -> bytes:
    marker = b"\n---\n\n"
    return raw.split(marker, 1)[1] if marker in raw else raw


def _family_fingerprint(root: Path) -> tuple[str, int, str]:
    docs = sorted(root.glob("*.md"))
    manifest = root / "manifest.json"
    if not docs or not manifest.is_file():
        raise AssertionError("DLI runtime family must include documents and manifest")
    records = [
        (str(path.relative_to(root)),
         hashlib.sha256(_body_bytes(path.read_bytes())).hexdigest())
        for path in docs
    ]
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    payload = json.dumps(
        {"documents": records, "manifest_sha256": manifest_sha},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest(), len(docs), manifest_sha


def _db_fingerprint(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return (
        hashlib.sha256(path.read_bytes()).hexdigest(),
        stat.st_size,
        stat.st_mtime_ns,
    )


class _StudyCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _seed(
        self,
        candidate: str,
        *,
        values: dict | None = None,
        decisions: dict[str, str] | None = None,
        qualities: dict[str, str] | None = None,
        factor_id: str = "review.study",
    ) -> tuple[vault.Vault, dict[str, str]]:
        values = dict(_VALUES if values is None else values)
        decisions = decisions or {}
        qualities = qualities or {}
        v = vault.open_vault(candidate)
        vault.create_candidate(v, candidate)
        vault.upsert_profile_factor(v, CrsProfileFactor(
            factor_id=factor_id,
            factor_group="additional_points",
            claimed_value={},
        ))
        source = Path(self._tmp.name) / f"{candidate}.pdf"
        source.write_bytes(b"%PDF-1.4\n% synthetic study fixture\n")
        document = vault.import_document(
            v, candidate, source, doc_type="study_proof")
        run = vault.record_extraction_run(
            v,
            document_id=document.document_id,
            parser_version=vault.current_parser_version(),
            status="complete",
        )
        page = vault.add_document_page(
            v,
            document_id=document.document_id,
            page_number=1,
            image_relpath=f"files/rendered/{document.document_id}/page-0001.png",
            render_sha256="b" * 64,
            extraction_run_id=run,
        )
        ids: dict[str, str] = {}
        for field, value in values.items():
            value_id = vault.add_extracted_value(
                v,
                document_id=document.document_id,
                page_id=page,
                factor_id=factor_id,
                field_name=field,
                raw_text=str(value),
                normalized_value=value,
                bbox=None,
                extractor_confidence=1.0,
                quality_flag=qualities.get(field, "ok"),
                extraction_run_id=run,
            )
            ids[field] = value_id
            decision = decisions.get(field, "confirm")
            if decision == "pending":
                continue
            if decision == "correct":
                vault.confirm_value(
                    v, value_id, "correct", corrected_value=value)
            else:
                vault.confirm_value(v, value_id, decision)
        return v, ids

    def _review(self, v: vault.Vault, candidate: str,
                db: Path = _REAL_DB) -> dict:
        return study_review.review_study(
            v, db, candidate_id=candidate, max_age_days=30)

    def _report(self, v: vault.Vault) -> Path:
        return v.root / "output" / "study-review" / "latest.json"


class TestCanonicalMembershipSynthetic(_StudyCase):
    """Always-run canonical index membership regressions with no real corpus."""

    _DLI = "O12345678901"
    _DATE = "2026-07-18"
    _PAGE_URL = (
        "https://www.canada.ca/en/immigration-refugees-citizenship/services/"
        "study-canada/study-permit/prepare/"
        "designated-learning-institutions-list.html"
    )
    _FEED_URL = (
        "https://www.canada.ca/content/dam/ircc/documents/json/dli/"
        "dli-full-list.json"
    )

    def _build_canonical_fixture(self) -> tuple[Path, Path]:
        corpus = Path(self._tmp.name) / "canonical-corpus"
        dli_root = corpus / "dli"
        dli_root.mkdir(parents=True, exist_ok=True)
        body = "\n".join([
            f"# Synthetic DLI {self._DLI}",
            "",
            f"DLI number: {self._DLI}",
            "Designation status: Designated",
            "Status scope: Current only",
            "",
            "## Post-Graduation Work Permit (PGWP) eligibility by campus",
            "",
            "| City | Campus | PGWP |",
            "| ---- | ------ | ---- |",
            "| North | Main | Yes |",
            "",
            "## Post-Graduation Work Permit (PGWP) eligibility by campus continued",
            "",
            "| City | Campus | PGWP |",
            "| ---- | ------ | ---- |",
            "| South | Annex | Yes |",
        ])
        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        title = f"Synthetic canonical DLI {self._DLI}"
        raw = "\n".join([
            "---",
            f'url: "{self._PAGE_URL}"',
            f'title: "{title}"',
            f'crawl_date: "{self._DATE}"',
            'source_type: "dli"',
            f'dli_number: "{self._DLI}"',
            'status_scope: "current-only"',
            'generator: "ircc-dli-json"',
            f'content_sha256: "{body_sha}"',
            "---",
            body,
        ])
        document = dli_root / f"{self._DLI}.md"
        document.write_text(raw, encoding="utf-8")
        files = [{"file": document.name, "content_sha256": body_sha}]
        family_payload = json.dumps(
            files, ensure_ascii=False, sort_keys=True).encode("utf-8")
        manifest = {
            "source_url": self._FEED_URL,
            "as_of": self._DATE,
            "last_modified": self._DATE,
            "generator": "ircc-dli-json",
            "status_scope": "current-only",
            "files": files,
            "family_sha256": hashlib.sha256(family_payload).hexdigest(),
        }
        (dli_root / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8")
        db = Path(self._tmp.name) / "canonical-index.db"
        searchindex.build_index(corpus, db)
        return dli_root, db

    def _review_fixture(
        self,
        v: vault.Vault,
        db: Path,
        dli_root: Path,
        snapshot: crs_rules.RegistrySnapshot,
    ) -> tuple[dict, mock.Mock]:
        healthy = mock.Mock()
        healthy.ok.return_value = True
        with (
            mock.patch.object(study_review, "_DLI_SNAPSHOT_ROOT", dli_root),
            mock.patch(
                "crawler.study_review.index_health.probe_snapshot",
                return_value=healthy,
            ),
            mock.patch(
                "crawler.study_review._today", return_value=date(2026, 7, 19)),
            mock.patch("crawler.auditor.gate_subset") as gate,
        ):
            result = study_review.review_study(
                v,
                db,
                candidate_id="canonical-membership",
                max_age_days=30,
                registry_snapshot=snapshot,
            )
        return result, gate

    def test_legitimate_multichunk_build_passes_and_each_tamper_refuses(
            self) -> None:
        dli_root, db = self._build_canonical_fixture()
        snapshot = crs_rules.load_registry_snapshot()
        values = {
            **_VALUES,
            "dli_number": self._DLI,
            "institution_name": "Synthetic Canonical Institute",
        }
        v, _ = self._seed("canonical-membership", values=values)
        report = self._report(v)
        try:
            result, gate = self._review_fixture(v, db, dli_root, snapshot)
            self.assertEqual(
                (result["status"], result["reason"], result["as_of"]),
                ("AT-RISK", "designation_historical_unproven", self._DATE),
            )
            self.assertTrue(report.is_file())
            prior_report = report.read_bytes()
            gate.assert_called_once()
            self.assertEqual(
                [
                    row.citations[0].chunk_id
                    for row in gate.call_args.args[0].rows[2:]
                ],
                [
                    f"dli/{self._DLI}.md#000",
                    f"dli/{self._DLI}.md#001",
                    f"dli/{self._DLI}.md#002",
                ],
            )

            def extra(con):
                row = con.execute(
                    "SELECT relpath,source_url,title,section,crawl_date,"
                    "source_type,text FROM chunks WHERE chunk_id LIKE '%#002'"
                ).fetchone()
                con.execute(
                    "INSERT INTO chunks(chunk_id,relpath,source_url,title,section,"
                    "crawl_date,source_type,chunk_sha,ordinal,text) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"dli/{self._DLI}.md#999", *row[:6],
                        hashlib.sha1(row[6].encode("utf-8")).hexdigest()[:12],
                        999, row[6],
                    ),
                )

            def reorder(con):
                prefix = f"dli/{self._DLI}.md#"
                con.execute(
                    "UPDATE chunks SET chunk_id=?, ordinal=1 WHERE chunk_id=?",
                    (prefix + "999", prefix + "000"),
                )
                con.execute(
                    "UPDATE chunks SET chunk_id=?, ordinal=0 WHERE chunk_id=?",
                    (prefix + "000", prefix + "001"),
                )
                con.execute(
                    "UPDATE chunks SET chunk_id=? WHERE chunk_id=?",
                    (prefix + "001", prefix + "999"),
                )

            def replace(con):
                text = (
                    "| City | Campus | PGWP |\n"
                    "| ---- | ------ | ---- |\n"
                    "| Replaced | Main | Yes |"
                )
                con.execute(
                    "UPDATE chunks SET text=?, chunk_sha=? "
                    "WHERE chunk_id LIKE '%#001'",
                    (
                        text,
                        hashlib.sha1(text.encode("utf-8")).hexdigest()[:12],
                    ),
                )

            mutations = {
                "extra": extra,
                "missing-intermediate": lambda con: con.execute(
                    "DELETE FROM chunks WHERE chunk_id LIKE '%#001'"),
                "missing-trailing": lambda con: con.execute(
                    "DELETE FROM chunks WHERE chunk_id LIKE '%#002'"),
                "reordered-ids-ordinals": reorder,
                "replaced-text-rehashed": replace,
                "section": lambda con: con.execute(
                    "UPDATE chunks SET section='replacement section' "
                    "WHERE chunk_id LIKE '%#001'"),
                "title": lambda con: con.execute(
                    "UPDATE chunks SET title='replacement title' "
                    "WHERE chunk_id LIKE '%#001'"),
                "source-type": lambda con: con.execute(
                    "UPDATE chunks SET source_type='guidance' "
                    "WHERE chunk_id LIKE '%#001'"),
                "crawl-date": lambda con: con.execute(
                    "UPDATE chunks SET crawl_date='2026-07-17' "
                    "WHERE chunk_id LIKE '%#001'"),
                "source-url": lambda con: con.execute(
                    "UPDATE chunks SET source_url='https://example.invalid/' "
                    "WHERE chunk_id LIKE '%#001'"),
            }
            for label, mutate in mutations.items():
                with self.subTest(tamper=label):
                    searchindex.build_index(dli_root.parent, db)
                    with sqlite3.connect(db) as con:
                        mutate(con)
                    refused, refused_gate = self._review_fixture(
                        v, db, dli_root, snapshot)
                    self.assertEqual(
                        (
                            refused["status"],
                            refused["reason"],
                            refused["as_of"],
                        ),
                        ("AT-RISK", "snapshot_provenance_mismatch", None),
                    )
                    self.assertEqual(report.read_bytes(), prior_report)
                    refused_gate.assert_not_called()
        finally:
            v.con.close()


@unittest.skipUnless(_REAL_DB.is_file(), "local DLI index required")
class TestEvidenceNoFalseGreenMatrix(_StudyCase):
    def test_pending_rejected_corrected_stale_quality_and_field_matrix(self) -> None:
        cases: list[tuple[str, dict, dict, dict, str | None]] = [
            ("pending", _VALUES, {key: "pending" for key in _VALUES}, {}, None),
            ("rejected", _VALUES, {key: "reject" for key in _VALUES}, {}, None),
            ("corrected", _VALUES, {key: "correct" for key in _VALUES}, {},
             "designation_historical_unproven"),
            ("low_quality", _VALUES, {}, {key: "low_quality" for key in _VALUES},
             None),
            ("ambiguous_quality", _VALUES, {},
             {key: "ambiguous" for key in _VALUES}, None),
            ("exact_mismatch", {**_VALUES, "dli_number": "O99999999999"},
             {}, {}, "exact_dli_mismatch"),
            ("name_only", {**_VALUES, "dli_number": "University of Toronto"},
             {}, {}, "exact_dli_mismatch"),
            ("missing_start", {k: v for k, v in _VALUES.items()
                               if k != "program_start"},
             {}, {}, "missing_study_fields"),
            ("missing_end", {k: v for k, v in _VALUES.items()
                             if k != "program_end"},
             {}, {}, "missing_study_fields"),
            ("invalid_start", {**_VALUES, "program_start": "not-a-date"},
             {}, {}, "ambiguous_study_evidence"),
            ("invalid_end", {**_VALUES, "program_end": "2020-00-90"},
             {}, {}, "ambiguous_study_evidence"),
            ("reversed_dates", {**_VALUES, "program_start": "2026-05-01"},
             {}, {}, "ambiguous_study_evidence"),
            ("invalid_status", {**_VALUES, "study_status": "enrolled"},
             {}, {}, "study_not_completed"),
            ("invalid_tier", {**_VALUES, "credential_level": "secondary"},
             {}, {}, "below_grounded_credential_tier"),
            ("current_only", _VALUES, {}, {},
             "designation_historical_unproven"),
        ]
        for label, values, decisions, qualities, expected_reason in cases:
            with self.subTest(case=label):
                v, _ = self._seed(
                    label, values=values, decisions=decisions,
                    qualities=qualities)
                try:
                    result = self._review(v, label)
                    _assert_safe(self, result, label)
                    if expected_reason:
                        self.assertEqual(result["reason"], expected_reason)
                    if label == "corrected":
                        self.assertEqual(
                            result["status"], "AT-RISK",
                            "corrected evidence is eligible but never establishes "
                            "historical designation")
                finally:
                    v.con.close()

    def test_each_five_key_staleness_binding_never_greens(self) -> None:
        variants = (
            "file_sha",
            "render_sha",
            "parser_version",
            "profile_claim_version",
            "registry_version",
        )
        for variant in variants:
            with self.subTest(variant=variant):
                candidate = f"stale-{variant.replace('_', '-')}"
                v, ids = self._seed(candidate)
                patch = contextlib.nullcontext()
                try:
                    if variant == "file_sha":
                        v.con.execute(
                            "UPDATE documents SET file_sha256=?",
                            ("f" * 64,))
                    elif variant == "render_sha":
                        v.con.execute(
                            "UPDATE document_pages SET render_sha256=?",
                            ("f" * 64,))
                    elif variant == "profile_claim_version":
                        vault.upsert_profile_factor(v, CrsProfileFactor(
                            factor_id="review.study",
                            factor_group="additional_points",
                            claimed_value={"changed": True},
                        ))
                    elif variant == "registry_version":
                        v.con.execute(
                            "UPDATE extracted_values "
                            "SET confirmed_rule_registry_version = 'changed' "
                            "WHERE confirmation_status IN "
                            "('confirmed', 'corrected')")
                    else:
                        patch = mock.patch.object(
                            vault, "current_parser_version",
                            return_value="changed")
                    v.con.commit()
                    with patch:
                        self.assertTrue(any(
                            vault.is_stale(v, value_id)
                            for value_id in ids.values()))
                        result = self._review(v, candidate)
                    _assert_safe(self, result, variant)
                finally:
                    v.con.close()

    def test_conflicting_eligible_duplicate_evidence_refuses_without_report(
            self) -> None:
        candidate = "conflicting-duplicate"
        v, ids = self._seed(candidate)
        try:
            original = vault.get_extracted_value(v, ids["dli_number"])
            duplicate = vault.add_extracted_value(
                v,
                document_id=original.document_id,
                page_id=original.page_id,
                factor_id="review.study",
                field_name="dli_number",
                raw_text="O110032269317",
                normalized_value="O110032269317",
                bbox=None,
                extractor_confidence=1.0,
                quality_flag="ok",
                extraction_run_id=original.extraction_run_id,
            )
            vault.confirm_value(v, duplicate, "confirm")
            result = self._review(v, candidate)
            _assert_safe(self, result)
            self.assertEqual(
                (result["status"], result["reason"], result["as_of"]),
                ("AT-RISK", "ambiguous_study_evidence", None),
            )
            self.assertFalse(self._report(v).exists())
        finally:
            v.con.close()

    def test_every_non_string_corrected_dli_type_refuses_without_report(
            self) -> None:
        corrections = (
            19332746152,
            ["O19332746152"],
            {"dli": "O19332746152"},
            True,
            None,
        )
        for index, correction in enumerate(corrections):
            with self.subTest(correction=correction):
                candidate = f"corrected-type-{index}"
                v, ids = self._seed(candidate)
                try:
                    vault.confirm_value(
                        v, ids["dli_number"], "correct",
                        corrected_value=correction)
                    result = self._review(v, candidate)
                    _assert_safe(self, result)
                    self.assertEqual(
                        (result["status"], result["reason"], result["as_of"]),
                        ("AT-RISK", "exact_dli_mismatch", None),
                    )
                    self.assertFalse(self._report(v).exists())
                finally:
                    v.con.close()

    def test_three_real_candidates_cover_yes_details_and_no(self) -> None:
        for label, dli, institution, reason in _CANDIDATES:
            with self.subTest(candidate=label):
                values = {
                    **_VALUES,
                    "dli_number": dli,
                    "institution_name": institution,
                }
                v, _ = self._seed(label, values=values)
                try:
                    with mock.patch(
                            "crawler.auditor.gate_subset",
                            wraps=auditor.gate_subset) as gate:
                        result = self._review(v, label)
                    _assert_safe(self, result, label)
                    self.assertEqual(
                        (result["status"], result["reason"], result["as_of"]),
                        ("AT-RISK", reason, _AS_OF),
                    )
                    registry = gate.call_args.args[0]
                    self.assertEqual(
                        [row.rule_id for row in registry.rows[:2]],
                        ["additional.study", "study.r73_definition"],
                    )
                    self.assertNotIn(
                        "study.dli.designation",
                        [row.rule_id for row in registry.rows],
                    )
                    # Enumerate the SQLite fixture directly: expectations must
                    # not be produced by the resolver under test.
                    uri = f"file:{_REAL_DB}?mode=ro"
                    with sqlite3.connect(uri, uri=True) as con:
                        expected_chunks = [
                            row[0] for row in con.execute(
                                "SELECT chunk_id FROM chunks "
                                "WHERE relpath = ? AND "
                                "(ordinal = 0 OR section LIKE ?) "
                                "ORDER BY ordinal",
                                (
                                    f"dli/{dli}.md",
                                    "%Post-Graduation Work Permit (PGWP) "
                                    "eligibility by campus%",
                                ),
                            ).fetchall()
                        ]
                    self.assertGreaterEqual(len(expected_chunks), 2)
                    dynamic = registry.rows[2:]
                    self.assertEqual(
                        [row.citations[0].chunk_id for row in dynamic],
                        expected_chunks,
                    )
                    self.assertEqual(
                        len(set(row.citations[0].chunk_id for row in dynamic)),
                        len(expected_chunks),
                    )
                    report = json.loads(
                        self._report(v).read_text(encoding="utf-8"))
                    self.assertEqual(
                        [entry["chunk_id"]
                         for entry in report["dynamic_citations"]],
                        expected_chunks,
                    )
                    self.assertTrue(all(
                        set(entry) == {
                            "rule_id", "kind", "chunk_id", "quote",
                            "crawl_date", "observed_values",
                        }
                        for entry in report["dynamic_citations"]
                    ))
                finally:
                    v.con.close()


@unittest.skipUnless(_REAL_DB.is_file(), "local DLI index required")
class TestGroundingAndProvenanceMatrix(_StudyCase):
    def _copy_index(self, filename: str) -> Path:
        destination = Path(self._tmp.name) / filename
        shutil.copy2(_REAL_DB, destination)
        return destination

    def _captured_registry(self) -> Registry:
        v, _ = self._seed("capture")
        try:
            with mock.patch(
                    "crawler.auditor.gate_subset",
                    wraps=auditor.gate_subset) as gate:
                result = self._review(v, "capture")
            self.assertEqual(result["reason"], "designation_historical_unproven")
            return gate.call_args.args[0]
        finally:
            v.con.close()

    def test_missing_or_gap_governing_rows_refuse(self) -> None:
        base = crs_rules.load_registry()
        for rule_id in ("additional.study", "study.r73_definition"):
            for mode in ("missing", "gap"):
                with self.subTest(rule=rule_id, mode=mode):
                    rows = []
                    for row in base.rows:
                        if row.rule_id != rule_id:
                            rows.append(row)
                        elif mode == "gap":
                            rows.append(row.model_copy(update={"gap": True}))
                    v, _ = self._seed(f"{mode}-{rule_id.replace('.', '-')}")
                    try:
                        registry = Registry(rows=rows)
                        snapshot = crs_rules.RegistrySnapshot(
                            registry=registry,
                            fingerprint=crs_rules.registry_fingerprint(registry),
                        )
                        with mock.patch(
                                "crawler.study_review.crs_rules."
                                "load_registry_snapshot",
                                return_value=snapshot):
                            result = self._review(
                                v, f"{mode}-{rule_id.replace('.', '-')}")
                        _assert_safe(self, result)
                        self.assertEqual(result["reason"], "grounding_refused")
                        self.assertFalse(self._report(v).exists())
                    finally:
                        v.con.close()

    def test_shared_gate_rejects_quote_marker_family_title_dli_and_citation_tamper(
            self) -> None:
        registry = self._captured_registry()
        target = registry.rows[2]
        selector = target.selector
        cases = {
            "quote": target.model_copy(update={
                "citations": [
                    target.citations[0].model_copy(
                        update={"quote": "tampered quote"})
                ]}),
            "marker": target.model_copy(update={
                "selector": selector.model_copy(
                    update={"marker": "missing marker"})}),
            "family": target.model_copy(update={
                "selector": selector.model_copy(
                    update={"family": "guidance"})}),
            "title_dli": target.model_copy(update={
                "selector": selector.model_copy(
                    update={"require_title_contains": "DLI O99999999999"})}),
            "citation": target.model_copy(update={
                "citations": [
                    target.citations[0].model_copy(
                        update={"chunk_id": "dli/O19332746152.md#999"})
                ]}),
        }
        for label, tampered in cases.items():
            with self.subTest(tamper=label):
                rows = list(registry.rows)
                rows[2] = tampered
                with self.assertRaises(auditor.AuditGroundingError):
                    auditor.gate_subset(Registry(rows=rows), _REAL_DB)

    def test_invalid_consumed_chunk_dates_refuse_before_gate_or_report(
            self) -> None:
        relpath = "dli/O19332746152.md"
        mutations = (
            ("stale-common", None, "2026-05-01"),
            ("future-common", None, "2026-07-20"),
            ("designation-missing", 0, ""),
            ("pgwp-missing", 1, ""),
            ("designation-mismatched", 0, "2026-07-15"),
            ("pgwp-mismatched", 1, "2026-07-15"),
        )
        for label, ordinal, replacement in mutations:
            with self.subTest(case=label):
                db = self._copy_index(f"{label}.db")
                sql = "UPDATE chunks SET crawl_date = ? WHERE relpath = ?"
                params: tuple = (replacement, relpath)
                if ordinal is not None:
                    sql += " AND ordinal = ?"
                    params += (ordinal,)
                with sqlite3.connect(db) as con:
                    con.execute(sql, params)

                # Exercise the same canonical-row helper used by study review and
                # prove this independent SQLite mutation reached that boundary.
                seen = searchindex.canonical_rows_for_relpath(db, relpath)
                self.assertGreaterEqual(len(seen), 2)
                if ordinal is None:
                    self.assertEqual(
                        {row["crawl_date"] for row in seen}, {replacement})
                else:
                    target = [
                        row for row in seen if row["ordinal"] == ordinal
                    ]
                    self.assertEqual(len(target), 1)
                    self.assertEqual(target[0]["crawl_date"], replacement)

                v, _ = self._seed(label)
                try:
                    healthy = mock.Mock()
                    healthy.ok.return_value = True
                    with (
                        mock.patch(
                            "crawler.study_review.index_health.probe_snapshot",
                            return_value=healthy),
                        mock.patch(
                            "crawler.study_review._today",
                            return_value=date(2026, 7, 19)),
                        mock.patch(
                            "crawler.auditor.gate_subset",
                            wraps=auditor.gate_subset) as gate,
                    ):
                        result = self._review(v, label, db)
                    _assert_safe(self, result)
                    self.assertEqual(
                        (result["status"], result["reason"], result["as_of"]),
                        ("AT-RISK", "snapshot_provenance_mismatch", None),
                    )
                    gate.assert_not_called()
                    self.assertFalse(self._report(v).exists())
                finally:
                    v.con.close()

    def test_candidate_stale_while_family_fresh_refuses_without_report(
            self) -> None:
        db = self._copy_index("candidate-stale.db")
        with sqlite3.connect(db) as con:
            con.execute(
                "UPDATE chunks SET crawl_date = '2026-05-01' "
                "WHERE relpath = 'dli/O19332746152.md'")
        candidate = "candidate-stale-family-fresh"
        v, _ = self._seed(candidate)
        try:
            with mock.patch(
                    "crawler.study_review._today",
                    return_value=date(2026, 7, 19)):
                result = self._review(v, candidate, db)
            _assert_safe(self, result)
            self.assertEqual(
                (result["status"], result["reason"], result["as_of"]),
                ("AT-RISK", "snapshot_provenance_mismatch", None),
            )
            self.assertFalse(self._report(v).exists())
        finally:
            v.con.close()

    def test_unmanifested_pgwp_chunk_refuses_provenance_without_report(
            self) -> None:
        cases = (
            ("mixed-valid", "No"),
            ("malformed", "Maybe"),
        )
        for label, status in cases:
            with self.subTest(case=label):
                db = self._copy_index(f"{label}.db")
                with sqlite3.connect(db) as con:
                    source = con.execute(
                        "SELECT relpath, source_url, title, section, crawl_date, "
                        "source_type FROM chunks WHERE chunk_id = ?",
                        ("dli/O19332746152.md#001",),
                    ).fetchone()
                    text = (
                        "| City | Campus | PGWP |\n"
                        "| ---- | ------ | ---- |\n"
                        f"| Toronto | Synthetic second campus | {status} |"
                    )
                    inserted = con.execute(
                        "INSERT INTO chunks("
                        "chunk_id, relpath, source_url, title, section, "
                        "crawl_date, source_type, chunk_sha, ordinal, text"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            "dli/O19332746152.md#002",
                            source[0], source[1], source[2],
                            source[3] + " continued",
                            source[4], source[5],
                            hashlib.sha1(text.encode("utf-8")).hexdigest()[:12],
                            2, text,
                        ),
                    )
                    con.execute(
                        "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                        (inserted.lastrowid, text),
                    )
                candidate = f"pgwp-{label}"
                v, _ = self._seed(candidate)
                try:
                    result = self._review(v, candidate, db)
                    _assert_safe(self, result)
                    self.assertEqual(
                        (result["status"], result["reason"], result["as_of"]),
                        ("AT-RISK", "snapshot_provenance_mismatch", None),
                    )
                    self.assertFalse(self._report(v).exists())
                finally:
                    v.con.close()

    def test_direct_pre_resolution_refusal_has_null_as_of(self) -> None:
        v, _ = self._seed("pre-resolution")
        try:
            result = study_review.review_study(
                v, _REAL_DB, candidate_id="pre-resolution", max_age_days=0)
            _assert_safe(self, result)
            self.assertEqual(result["reason"], "snapshot_config_invalid")
            self.assertIsNone(result["as_of"])
            self.assertFalse(self._report(v).exists())
        finally:
            v.con.close()


class TestCliPreflightConformance(_StudyCase):
    def _candidate_root(self, candidate: str) -> Path:
        return Path(self._tmp.name) / "candidates" / candidate

    def test_config_index_and_snapshot_refusal_matrix_has_zero_artifacts(self) -> None:
        config = (
            ("missing", None, None),
            ("explicit-empty", "", "30"),
            ("explicit-text", "days", "30"),
            ("explicit-zero", "0", "30"),
            ("explicit-negative", "-1", "30"),
            ("env-empty", None, ""),
            ("env-text", None, "days"),
            ("env-zero", None, "0"),
            ("env-negative", None, "-1"),
        )
        for label, explicit, env_value in config:
            with self.subTest(boundary="config", case=label):
                candidate = f"config-{label}"
                argv = [
                    "--json", "vault", "study-review",
                    "--candidate", candidate, "--db", "never.db",
                ]
                if explicit is not None:
                    argv += ["--snapshot-max-age-days", explicit]
                environ = {}
                if env_value is not None:
                    environ["PR_DLI_SNAPSHOT_MAX_AGE_DAYS"] = env_value
                with mock.patch.dict(os.environ, environ, clear=True), \
                        mock.patch(
                            "crawler.index_health.probe_index") as index_probe:
                    rc, out, _ = _run_cli(argv)
                env = json.loads(out)
                self.assertEqual(rc, 2)
                self.assertEqual(set(env), _FIVE)
                self.assertIsNone(env["result"])
                self.assertNotIn("as_of", out)
                index_probe.assert_not_called()
                self.assertFalse(self._candidate_root(candidate).exists())

    def test_explicit_missing_index_stops_before_snapshot_vault_and_report(
            self) -> None:
        candidate = "ordered-missing-index"
        events: list[str] = []

        def missing_index(_db):
            events.append("index")
            return index_health.IndexHealth(
                index_health.INDEX_MISSING, "missing")

        def snapshot(*_args, **_kwargs):
            events.append("snapshot")
            raise AssertionError("snapshot probe must not run")

        def open_vault(*_args, **_kwargs):
            events.append("vault")
            raise AssertionError("vault must not open")

        with mock.patch(
                "crawler.index_health.probe_index",
                side_effect=missing_index), \
                mock.patch(
                    "crawler.index_health.probe_snapshot",
                    side_effect=snapshot), \
                mock.patch(
                    "crawler.vault.open_vault",
                    side_effect=open_vault):
            rc, out, err = _run_cli([
                "--json", "vault", "study-review",
                "--candidate", candidate, "--db", "missing.db",
                "--snapshot-max-age-days", "30",
            ])
        envelope = json.loads(out)
        self.assertEqual(rc, 2)
        self.assertEqual(events, ["index"])
        self.assertEqual(set(envelope), _FIVE)
        self.assertIsNone(envelope["result"])
        self.assertEqual(
            envelope["error"]["message"],
            "corpus index unusable (reason=index_missing): missing. Recover: "
            "rebuild it with 'corpus-crawler --json index corpus/ --db "
            "missing.db', then verify with 'corpus-crawler --json doctor'.",
        )
        self.assertNotIn("Traceback", out + err)
        self.assertFalse(
            (self._candidate_root(candidate) / "output" /
             "study-review" / "latest.json").exists())

        index_statuses = (
            index_health.INDEX_MISSING,
            index_health.INDEX_EMPTY,
            index_health.INDEX_UNREADABLE,
            index_health.INDEX_CORRUPT,
            index_health.INDEX_DRIFTED,
        )
        for status in index_statuses:
            with self.subTest(boundary="index", case=status):
                candidate = status.replace("_", "-")
                with mock.patch(
                        "crawler.index_health.probe_index",
                        return_value=index_health.IndexHealth(status, status)), \
                        mock.patch(
                            "crawler.index_health.probe_snapshot") as snap:
                    rc, out, _ = _run_cli([
                        "--json", "vault", "study-review",
                        "--candidate", candidate, "--db", "fixture.db",
                        "--snapshot-max-age-days", "30",
                    ])
                env = json.loads(out)
                self.assertEqual(rc, 2)
                self.assertIsNone(env["result"])
                self.assertIn(f"reason={status}", env["error"]["message"])
                snap.assert_not_called()
                self.assertFalse(self._candidate_root(candidate).exists())

        snapshot_statuses = (
            index_health.SNAPSHOT_MISSING,
            index_health.SNAPSHOT_EMPTY,
            index_health.SNAPSHOT_UNREADABLE,
            index_health.SNAPSHOT_CORRUPT,
            index_health.SNAPSHOT_DRIFTED,
            index_health.SNAPSHOT_STALE,
        )
        for status in snapshot_statuses:
            with self.subTest(boundary="snapshot", case=status):
                candidate = f"snap-{status.replace('_', '-')}"
                with mock.patch(
                        "crawler.index_health.probe_index",
                        return_value=index_health.IndexHealth("ok", "ok")), \
                        mock.patch(
                            "crawler.index_health.probe_snapshot",
                            return_value=index_health.SnapshotHealth(
                                status, status)):
                    rc, out, _ = _run_cli([
                        "--json", "vault", "study-review",
                        "--candidate", candidate, "--db", "fixture.db",
                        "--snapshot-max-age-days", "30",
                    ])
                env = json.loads(out)
                self.assertEqual(rc, 2)
                self.assertIsNone(env["result"])
                self.assertIn(f"reason={status}", env["error"]["message"])
                self.assertFalse(self._candidate_root(candidate).exists())

    def test_real_missing_empty_corrupt_drift_and_stale_files_create_nothing(
            self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            missing = root / "missing.db"
            empty = root / "empty.db"
            empty.write_bytes(b"")
            corrupt = root / "corrupt.db"
            corrupt.write_bytes(b"not sqlite")
            drift = root / "drift.db"
            _build_snapshot_index(
                drift, family="dli", chunks=["alpha"], tamper_first_sha=True)
            stale = root / "stale.db"
            _build_snapshot_index(
                stale, family="dli", chunks=["alpha"], crawl_date="2000-01-01")
            for label, db in (
                    ("missing", missing), ("empty", empty),
                    ("corrupt", corrupt), ("drift", drift),
                    ("stale", stale)):
                with self.subTest(case=label):
                    candidate = f"real-{label}"
                    before = (db.exists(), db.read_bytes() if db.exists() else None)
                    rc, out, _ = _run_cli([
                        "--json", "vault", "study-review",
                        "--candidate", candidate, "--db", str(db),
                        "--snapshot-max-age-days", "30",
                    ])
                    self.assertEqual(rc, 2)
                    self.assertIsNone(json.loads(out)["result"])
                    self.assertEqual(
                        (db.exists(),
                         db.read_bytes() if db.exists() else None),
                        before,
                    )
                    self.assertFalse(self._candidate_root(candidate).exists())


@unittest.skipUnless(_REAL_DB.is_file(), "local DLI index required")
class TestPublicEnvelopeAndGridIsolation(_StudyCase):
    def test_cli_envelope_is_closed_and_private_markers_are_absent(self) -> None:
        v, _ = self._seed("public")
        root = v.root
        v.con.close()
        rc, out, err = _run_cli([
            "--json", "vault", "study-review", "--candidate", "public",
            "--db", str(_REAL_DB), "--snapshot-max-age-days", "30",
        ])
        self.assertEqual(rc, 0, err)
        env = json.loads(out)
        self.assertEqual(set(env), _FIVE)
        self.assertEqual(set(env["result"]), _PUBLIC)
        _assert_safe(self, env["result"])
        self.assertEqual(env["result"]["as_of"], _AS_OF)
        report = json.loads(
            (root / "output" / "study-review" / "latest.json").read_text(
                encoding="utf-8"))
        private = (
            "O19332746152",
            "University of Toronto",
            "3+",
            "2022-09-15",
            "2026-04-30",
            "graduated",
            "ev_",
            "dli/O19332746152.md#000",
            "DLI number:",
            str(root),
        )
        for marker in private:
            self.assertNotIn(marker, out)
        self.assertIn("O19332746152", json.dumps(report))
        self.assertIn("ev_", json.dumps(report))

    def test_review_study_evidence_leaves_every_grid_card_byte_identical(
            self) -> None:
        v = vault.open_vault("grid-isolation")
        vault.create_candidate(v, "grid-isolation")
        try:
            registry = crs_rules.load_registry()
            before = auditor.run_full_audit(v, _REAL_DB, registry)
            v2, _ = self._seed("grid-isolation")
            v2.con.close()
            after = auditor.run_full_audit(v, _REAL_DB, registry)
            before_cards = {
                card.factor_id: card.model_dump_json()
                for card in before.factor_cards
            }
            after_cards = {
                card.factor_id: card.model_dump_json()
                for card in after.factor_cards
            }
            self.assertEqual(set(before_cards), set(auditors.FULL_GRID_FACTORS))
            self.assertIn("core.age", before_cards)
            self.assertEqual(before_cards, after_cards)
            self.assertNotIn("review.study", auditors.FULL_GRID_FACTORS)
        finally:
            v.con.close()

    def test_credential_only_and_unwired_paths_never_green_or_score(self) -> None:
        v, _ = self._seed(
            "credential-only",
            values={"credential_level": "3+"},
            factor_id="additional.study",
        )
        try:
            card = auditor.audit_one(
                v,
                "additional.study",
                _REAL_DB,
                crs_rules.load_registry(),
                spouse_mode=False,
                reference_date="2026-07-19",
                prior_cards={},
            )
            self.assertNotEqual(card.verdict, "SUBSTANTIATED")
            self.assertIn(card.substantiated_points, (None, 0))
            ctx = auditors.DecisionContext(
                factor_id="unwired.study",
                factor=None,
                by_field={},
                registry=Registry(rows=[]),
                consumed=Registry(rows=[]),
                spouse_mode=False,
                reference_date="2026-07-19",
            )
            unwired = auditors._default_decider(ctx)
            self.assertEqual(unwired.verdict, "AT-RISK")
            self.assertIn(unwired.substantiated_points, (None, 0))
        finally:
            v.con.close()


@unittest.skipUnless(
    _REAL_DB.is_file() and _DLI_ROOT.is_dir(),
    "local DLI family and index required",
)
class TestRuntimeReadOnlyAndFrozenPins(_StudyCase):
    def test_ignored_family_and_index_fingerprints_are_nonvacuous_and_stable(
            self) -> None:
        family_before = _family_fingerprint(_DLI_ROOT)
        db_before = _db_fingerprint(_REAL_DB)
        self.assertGreater(family_before[1], 0)
        self.assertTrue(family_before[2])
        uri = f"file:{_REAL_DB}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            self.assertGreater(
                con.execute("SELECT count(*) FROM chunks").fetchone()[0], 0)
        finally:
            con.close()

        v, _ = self._seed("fingerprint")
        try:
            result = self._review(v, "fingerprint")
            _assert_safe(self, result)
        finally:
            v.con.close()

        self.assertEqual(_family_fingerprint(_DLI_ROOT), family_before)
        self.assertEqual(_db_fingerprint(_REAL_DB), db_before)

    def test_vault_schema_user_version_and_fingerprint_stay_pinned(self) -> None:
        v, _ = self._seed("schema-pin")
        try:
            before = (
                v.con.execute("PRAGMA user_version").fetchone()[0],
                _schema_fingerprint(v.con),
            )
            self.assertEqual(before, (3, _SCHEMA_SHA))
            result = self._review(v, "schema-pin")
            _assert_safe(self, result)
            after = (
                v.con.execute("PRAGMA user_version").fetchone()[0],
                _schema_fingerprint(v.con),
            )
            self.assertEqual(after, before)
        finally:
            v.con.close()

    def test_tracked_goldens_match_regeneration_and_approved_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fresh = _regenerate(Path(td))
            committed = {
                path.name: path.read_bytes()
                for path in sorted(_GOLDEN_DLI.iterdir())
            }
            regenerated = {
                path.name: path.read_bytes()
                for path in sorted(fresh.iterdir())
            }
            self.assertEqual(committed, regenerated)
        actual = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(_GOLDEN_DLI.iterdir())
        }
        self.assertEqual(actual, _APPROVED_GOLDEN_SHA)

    def test_source_dependency_lock_and_network_surfaces_are_frozen(self) -> None:
        actual_source_sha = {
            rel: hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()
            for rel in _APPROVED_SOURCE_SHA
        }
        self.assertEqual(actual_source_sha, _APPROVED_SOURCE_SHA)

        parsed = tomli.loads(
            (_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(set(parsed["project"]["dependencies"]), _DEPENDENCIES)
        self.assertEqual(
            hashlib.sha256((_ROOT / "pyproject.toml").read_bytes()).hexdigest(),
            _PYPROJECT_SHA,
        )
        self.assertEqual(
            hashlib.sha256((_ROOT / "poetry.lock").read_bytes()).hexdigest(),
            _LOCK_SHA,
        )
        banned = {
            "aiohttp", "curl", "httpx", "requests", "socket",
            "urllib", "urllib3",
        }
        targets = (
            _ROOT / "crawler" / "study_review.py",
            _ROOT / "crawler" / "snapshot_policy.py",
        )
        for path in targets:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0]
                                   for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            self.assertTrue(imports.isdisjoint(banned), (path, imports & banned))

        cli_tree = ast.parse(
            (_ROOT / "crawler" / "cli.py").read_text(encoding="utf-8"))
        handler = next(
            node for node in cli_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_cmd_vault_study_review"
        )
        handler_imports: set[str] = set()
        for node in ast.walk(handler):
            if isinstance(node, ast.Import):
                handler_imports.update(alias.name.split(".")[0]
                                       for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                handler_imports.add(node.module.split(".")[0])
        self.assertTrue(
            handler_imports.isdisjoint(banned),
            handler_imports & banned,
        )

    def test_approved_tracked_surfaces_have_clean_worktrees(self) -> None:
        tracked = [
            *_APPROVED_SOURCE_SHA,
            *(
                str(path.relative_to(_ROOT))
                for path in sorted(_GOLDEN_DLI.iterdir())
            ),
            "pyproject.toml",
            "poetry.lock",
        ]
        proc = subprocess.run(
            ["git", "diff", "--quiet", "--", *tracked],
            cwd=_ROOT,
        )
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
