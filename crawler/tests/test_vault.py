"""Offline unit tests for the candidate vault (Phase 29 — VAULT-01/02/03).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network (per the
``crawler/tests/test_searchindex.py`` / AGENTS.md convention). Every test points
``$PR_PERSONAL_DIR`` at a ``tempfile.TemporaryDirectory`` so the vault is created
under a throwaway tmp candidate root and NEVER touches the real git-ignored
``personal/`` tree. All fixtures are SYNTHETIC (fake bytes / fake values).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_vault.py -q

Behaviour map:

    TestOpenVault      — open/create idempotency, schema, user_version, meta seed
    TestIdNamespaces   — evidence_id vs citation_id disjointness (VAULT-03)
    TestProfileFactors — CRS factor + ITA round round-trip; YAML import (VAULT-01)
    TestSummarize      — summarize_vault is PII-light
    TestImportDocument — content-addressed ingest + ev_ minting (VAULT-02/03)
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import paths, vault
from crawler.models.vault import CrsProfileFactor


class _VaultTmpCase(unittest.TestCase):
    """Base case: a fresh tmp personal root ($PR_PERSONAL_DIR) per test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name}
        )
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _personal_root(self) -> Path:
        return Path(self._tmp.name).resolve()


class TestOpenVault(_VaultTmpCase):
    def test_open_creates_db_under_candidate_root(self) -> None:
        v = vault.open_vault("default")
        try:
            expected_root = self._personal_root() / "candidates" / "default"
            self.assertEqual(v.root, expected_root)
            self.assertTrue(v.db_path.is_file())
            self.assertEqual(v.db_path.name, "vault.sqlite")
        finally:
            v.con.close()

    def test_schema_tables_present(self) -> None:
        v = vault.open_vault("default")
        try:
            rows = v.con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            names = {r["name"] for r in rows}
            for table in ("vault_meta", "candidates", "crs_profile_factors",
                          "ita_rounds", "documents"):
                self.assertIn(table, names)
            # Phase 30 (schema v2) extraction/confirmation tables are now PRESENT.
            for present in ("extraction_runs", "document_pages",
                            "extracted_values", "factor_evidence"):
                self.assertIn(present, names)
        finally:
            v.con.close()

    def test_user_version_is_two(self) -> None:
        v = vault.open_vault("default")
        try:
            # Schema v3 (Phase 32) — audit_runs + factor_verdicts added additively.
            self.assertEqual(v.con.execute("PRAGMA user_version").fetchone()[0], 3)
        finally:
            v.con.close()

    def test_meta_seeded(self) -> None:
        v = vault.open_vault("default")
        try:
            self.assertEqual(vault.vault_meta(v, "vault_kind"), "candidate")
            self.assertEqual(vault.vault_meta(v, "evidence_id_prefix"), "ev_")
            self.assertEqual(vault.vault_meta(v, "schema_version"), "3")
            # Phase 30: rule_registry_version seeded (default "0") for SC4.
            self.assertEqual(vault.vault_meta(v, "rule_registry_version"), "0")
        finally:
            v.con.close()

    def test_reopen_is_idempotent(self) -> None:
        v1 = vault.open_vault("default")
        vault.create_candidate(v1, "default", label="First")
        v1.con.close()
        # Re-open: same DB, migrations not re-run destructively, row survives.
        v2 = vault.open_vault("default")
        try:
            self.assertEqual(v2.con.execute("PRAGMA user_version").fetchone()[0], 3)
            cand = vault.select_candidate(v2, "default")
            self.assertIsNotNone(cand)
            self.assertEqual(cand.label, "First")
        finally:
            v2.con.close()

    def test_create_select_candidate_idempotent(self) -> None:
        v = vault.open_vault("default")
        try:
            c1 = vault.create_candidate(v, "default", label="Alpha")
            self.assertEqual(c1.candidate_id, "default")
            self.assertEqual(c1.label, "Alpha")
            # Re-create is a no-op (label preserved, no duplicate row).
            c2 = vault.create_candidate(v, "default", label="Ignored")
            self.assertEqual(c2.label, "Alpha")
            count = v.con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
            self.assertEqual(count, 1)
            self.assertIsNone(vault.select_candidate(v, "nonexistent"))
        finally:
            v.con.close()

    def test_candidate_id_is_slugified(self) -> None:
        v = vault.open_vault("Default Candidate")
        try:
            self.assertEqual(v.candidate_id, "default-candidate")
            self.assertEqual(
                v.root, self._personal_root() / "candidates" / "default-candidate"
            )
        finally:
            v.con.close()


class TestIdNamespaces(_VaultTmpCase):
    """VAULT-03: evidence_id and citation_id namespaces are provably disjoint."""

    def test_minted_evidence_id_is_never_a_citation(self) -> None:
        for _ in range(200):
            eid = vault.new_evidence_id()
            self.assertTrue(eid.startswith("ev_"))
            self.assertTrue(vault.is_evidence_id(eid))
            self.assertFalse(vault.is_citation_id(eid))

    def test_corpus_citation_is_never_an_evidence_id(self) -> None:
        for cid in ("guides/eca.md#0", "a/b/c.md#003", "x.md#12"):
            self.assertTrue(vault.is_citation_id(cid))
            self.assertFalse(vault.is_evidence_id(cid))

    def test_document_and_round_id_prefixes(self) -> None:
        self.assertTrue(vault.new_document_id().startswith("doc_"))
        self.assertTrue(vault.new_round_id().startswith("ita_"))


_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE_FACTORS = _REPO_ROOT / "personal.example" / "crs-profile.example.yaml"


class TestProfileFactors(_VaultTmpCase):
    """VAULT-01: CRS factor + ITA round round-trip and YAML import."""

    def test_factor_round_trip(self) -> None:
        v = vault.open_vault("default")
        try:
            vault.create_candidate(v, "default")
            f = CrsProfileFactor(
                factor_id="core_age",
                factor_group="core_human_capital",
                claimed_points=100,
                claimed_level=None,
                claimed_value={"age_years": 29},
                source="user_entry",
            )
            vault.upsert_profile_factor(v, f)
            loaded = vault.load_profile_factors(v, "default")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].factor_id, "core_age")
            self.assertEqual(loaded[0].factor_group, "core_human_capital")
            self.assertEqual(loaded[0].claimed_value, {"age_years": 29})
            # Upsert same id updates rather than duplicating.
            f2 = f.model_copy(update={"claimed_points": 110})
            vault.upsert_profile_factor(v, f2)
            loaded2 = vault.load_profile_factors(v, "default")
            self.assertEqual(len(loaded2), 1)
            self.assertEqual(loaded2[0].claimed_points, 110)
        finally:
            v.con.close()

    def test_ita_round_persists(self) -> None:
        v = vault.open_vault("default")
        try:
            r = vault.set_ita_round(
                v, "default", round_label="round-999",
                round_date="2026-01-15", program="express_entry",
                cutoff_score=520, claimed_score=531,
            )
            self.assertTrue(r.round_id.startswith("ita_"))
            self.assertEqual(r.cutoff_score, 520)
            row = v.con.execute(
                "SELECT round_label, cutoff_score, claimed_score FROM ita_rounds "
                "WHERE round_id = ?", (r.round_id,)
            ).fetchone()
            self.assertEqual(row["round_label"], "round-999")
            self.assertEqual(row["cutoff_score"], 520)
            self.assertEqual(row["claimed_score"], 531)
        finally:
            v.con.close()

    def test_import_profile_yaml_synthetic_example(self) -> None:
        self.assertTrue(_EXAMPLE_FACTORS.is_file(), _EXAMPLE_FACTORS)
        v = vault.open_vault("default")
        try:
            imported = vault.import_profile_yaml(v, "default", _EXAMPLE_FACTORS)
            self.assertGreaterEqual(len(imported), 4)
            self.assertTrue(all(f.source == "profile_import" for f in imported))
            groups = {f.factor_group for f in imported}
            self.assertEqual(
                groups,
                {"core_human_capital", "spouse_common_law",
                 "skill_transferability", "additional_points"},
            )
            # Persisted + reloadable.
            self.assertEqual(
                len(vault.load_profile_factors(v, "default")), len(imported)
            )
        finally:
            v.con.close()

    def test_import_profile_yaml_bad_shape_is_pii_free(self) -> None:
        v = vault.open_vault("default")
        try:
            bad = Path(self._tmp.name) / "bad.yaml"
            # claimed_points must be int; the offending value is a PII-shaped token.
            bad.write_text(
                "factors:\n"
                "  - factor_id: core_age\n"
                "    factor_group: core_human_capital\n"
                "    claimed_points: SECRET_UCI_12345\n",
                encoding="utf-8",
            )
            with self.assertRaises(vault.VaultError) as ctx:
                vault.import_profile_yaml(v, "default", bad)
            # PII boundary: the offending value must NOT appear in the message.
            self.assertNotIn("SECRET_UCI_12345", str(ctx.exception))
            self.assertIn("claimed_points", str(ctx.exception))
        finally:
            v.con.close()


class TestSummarize(_VaultTmpCase):
    """summarize_vault is PII-light: counts/ids/status only, no claimed_points."""

    def test_summary_is_pii_light(self) -> None:
        v = vault.open_vault("default")
        try:
            vault.create_candidate(v, "default")
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="core_age", factor_group="core_human_capital",
                claimed_points=1373,  # distinctive sentinel value
                claimed_value={"age_years": 29}, source="user_entry",
            ))
            vault.set_ita_round(
                v, "default", round_label="round-999", round_date="2026-01-15",
                program="express_entry", cutoff_score=520, claimed_score=531,
            )
            summary = vault.summarize_vault(v, "default")
            self.assertEqual(summary.factor_count, 1)
            self.assertEqual(summary.ita_round_count, 1)
            self.assertEqual(summary.document_count, 0)
            self.assertIn("core_human_capital", summary.groups_present)
            blob = summary.model_dump_json()
            # No claimed_points value, no absolute tmp path in the PII-light view.
            self.assertNotIn("1373", blob)
            self.assertNotIn(self._tmp.name, blob)
        finally:
            v.con.close()


class TestImportDocument(_VaultTmpCase):
    """VAULT-02/03: content-addressed ingest, ev_ minting, PII-light returns."""

    _SYNTHETIC_PDF = b"%PDF-1.4 synthetic"

    def _write_src(self, name: str, data: bytes = _SYNTHETIC_PDF) -> Path:
        src = Path(self._tmp.name) / name
        src.write_bytes(data)
        return src

    def test_content_addressed_file_and_pii_light_return(self) -> None:
        v = vault.open_vault("default")
        try:
            src = self._write_src("Jane_Doe_UCI123.pdf")
            summary = vault.import_document(
                v, "default", src, doc_type="language_test",
            )
            import hashlib as _h
            sha = _h.sha256(self._SYNTHETIC_PDF).hexdigest()
            dest = v.root / "files" / "raw" / f"{sha}.pdf"
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_bytes(), self._SYNTHETIC_PDF)
            # PII-light: ev_ evidence id present; original filename absent.
            self.assertTrue(vault.is_evidence_id(summary.evidence_id))
            blob = summary.model_dump_json()
            self.assertNotIn("Jane_Doe_UCI123", blob)
            self.assertNotIn(str(src), blob)
            # original_name IS stored privately in the DB.
            row = v.con.execute(
                "SELECT original_name, storage_relpath FROM documents "
                "WHERE document_id = ?", (summary.document_id,)
            ).fetchone()
            self.assertEqual(row["original_name"], "Jane_Doe_UCI123.pdf")
            self.assertEqual(row["storage_relpath"], f"files/raw/{sha}.pdf")
        finally:
            v.con.close()

    def test_identical_bytes_dedupe_on_disk_distinct_rows(self) -> None:
        v = vault.open_vault("default")
        try:
            src1 = self._write_src("a.pdf")
            src2 = self._write_src("b.pdf")  # identical bytes, different name
            s1 = vault.import_document(v, "default", src1, doc_type="eca")
            s2 = vault.import_document(v, "default", src2, doc_type="eca")
            raw_dir = v.root / "files" / "raw"
            files = list(raw_dir.iterdir())
            self.assertEqual(len(files), 1)  # one on-disk content-addressed file
            # ...but two distinct logical records.
            self.assertNotEqual(s1.document_id, s2.document_id)
            self.assertNotEqual(s1.evidence_id, s2.evidence_id)
            count = v.con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            self.assertEqual(count, 2)
        finally:
            v.con.close()

    def test_import_never_touches_corpus(self) -> None:
        # A sibling tmp corpus/ must be byte-for-byte unchanged after an import.
        corpus_dir = Path(self._tmp.name) / "corpus"
        corpus_dir.mkdir()
        corpus_db = corpus_dir / "index.db"
        corpus_db.write_bytes(b"CORPUS-SENTINEL")
        before = sorted((p.name, p.read_bytes()) for p in corpus_dir.iterdir())
        v = vault.open_vault("default")
        try:
            src = self._write_src("doc.pdf")
            vault.import_document(v, "default", src, doc_type="nomination")
        finally:
            v.con.close()
        after = sorted((p.name, p.read_bytes()) for p in corpus_dir.iterdir())
        self.assertEqual(before, after)
        self.assertEqual(corpus_db.read_bytes(), b"CORPUS-SENTINEL")

    def test_forged_escaping_dest_raises(self) -> None:
        # The dest mechanism (resolve_within) refuses any '..' escape out of the
        # candidate root — proving import_document's write can never escape.
        v = vault.open_vault("default")
        try:
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(v.root, "files", "raw", "..", "..", "escape.pdf")
        finally:
            v.con.close()


if __name__ == "__main__":
    unittest.main()
