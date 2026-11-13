"""Offline tests for the Phase-32 audit-run store (schema v3 — AUDIT-02 / AUDIT-06).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Each test points
``$PR_PERSONAL_DIR`` at a ``tempfile.TemporaryDirectory`` so the vault is created
under a throwaway candidate root and NEVER touches the real git-ignored
``personal/`` tree. All fixtures are SYNTHETIC.

Covered:
  * the ADDITIVE v2 → v3 migration upgrades in place (audit_runs + factor_verdicts
    appear, ``PRAGMA user_version == 3``) WITHOUT mutating any pre-existing row;
  * ``record_audit_run`` / ``complete_audit_run`` / ``record_factor_verdict`` +
    the ``load_audit_run`` / ``list_factor_verdicts`` read helpers round-trip;
  * ev_ evidence ids and corpus relpath#ordinal ids persist in SEPARATE columns
    and never cross;
  * an out-of-vocabulary verdict raises ``VaultError`` (field/type only).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_audit_store.py -q
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import paths, vault


class _VaultTmpCase(unittest.TestCase):
    """Base case: a fresh tmp personal root ($PR_PERSONAL_DIR) per test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _seed_v2_db(self, candidate_id: str = "default") -> Path:
        """Create a v2-shaped vault.sqlite with a candidate + document row.

        Builds the v1 + v2 DDL directly, pins ``user_version = 2``, and inserts a
        candidate + a document so the in-place migration test can prove the
        pre-existing rows survive the v3 upgrade untouched.
        """
        root = paths.candidate_root(candidate_id)
        root.mkdir(parents=True, exist_ok=True)
        db_path = paths.resolve_within(root, "vault.sqlite")
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(vault._SCHEMA_V1_DDL)
        con.executescript(vault._SCHEMA_V2_DDL)
        con.execute(
            "INSERT INTO vault_meta(key, value) VALUES ('schema_version', '2')")
        con.execute(
            "INSERT INTO candidates(candidate_id, label, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (candidate_id, "seed", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"))
        con.execute(
            "INSERT INTO documents(document_id, candidate_id, evidence_id, "
            "doc_type, file_sha256, storage_relpath, original_name, mime_type, "
            "byte_size, page_count, added_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("doc_seed000001", candidate_id, "ev_seed12345", "language_test",
             "a" * 64, "files/raw/aaa.pdf", "test.pdf", "application/pdf",
             123, 1, "2026-01-01T00:00:00Z", "added"))
        con.execute("PRAGMA user_version = 2")
        con.commit()
        con.close()
        return db_path


class TestSchemaV3Migration(_VaultTmpCase):
    """The additive v2 → v3 migration (test names contain 'migration')."""

    def test_fresh_vault_migration_is_v3_with_new_tables(self) -> None:
        v = vault.open_vault("default")
        try:
            self.assertEqual(
                v.con.execute("PRAGMA user_version").fetchone()[0], 3)
            names = {r["name"] for r in v.con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertIn("audit_runs", names)
            self.assertIn("factor_verdicts", names)
            self.assertEqual(vault.vault_meta(v, "schema_version"), "3")
        finally:
            v.con.close()

    def test_v2_migration_upgrades_in_place_without_mutation(self) -> None:
        self._seed_v2_db("default")
        v = vault.open_vault("default")
        try:
            # Upgraded in place.
            self.assertEqual(
                v.con.execute("PRAGMA user_version").fetchone()[0], 3)
            names = {r["name"] for r in v.con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertIn("audit_runs", names)
            self.assertIn("factor_verdicts", names)
            # Pre-existing rows survive untouched.
            cand = v.con.execute(
                "SELECT candidate_id, label FROM candidates").fetchone()
            self.assertEqual(cand["candidate_id"], "default")
            self.assertEqual(cand["label"], "seed")
            doc = v.con.execute(
                "SELECT evidence_id, doc_type, file_sha256 FROM documents"
            ).fetchone()
            self.assertEqual(doc["evidence_id"], "ev_seed12345")
            self.assertEqual(doc["doc_type"], "language_test")
            # No audit rows were fabricated by the migration.
            self.assertEqual(
                v.con.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
        finally:
            v.con.close()

    def test_reopen_after_migration_is_idempotent(self) -> None:
        v1 = vault.open_vault("default")
        v1.con.close()
        v2 = vault.open_vault("default")
        try:
            self.assertEqual(
                v2.con.execute("PRAGMA user_version").fetchone()[0], 3)
        finally:
            v2.con.close()

    def test_id_minters_are_prefixed(self) -> None:
        self.assertTrue(vault.new_audit_run_id().startswith("aud_"))
        self.assertTrue(vault.new_verdict_id().startswith("ver_"))


class TestAuditRunPersistence(_VaultTmpCase):
    """record/complete/load audit runs + factor verdicts (vault-only)."""

    def _open(self):
        v = vault.open_vault("default")
        vault.create_candidate(v, "default")
        return v

    def test_run_and_verdict_round_trip(self) -> None:
        v = self._open()
        try:
            run_id = vault.record_audit_run(
                v, candidate_id=v.candidate_id, factor_id="core.language.first",
                rule_registry_version="1")
            self.assertTrue(run_id.startswith("aud_"))
            ver_id = vault.record_factor_verdict(
                v, audit_run_id=run_id, factor_id="core.language.first",
                verdict="SUBSTANTIATED", reason_code="grounded_substantiated",
                substantiated_points=116, score_delta=0,
                evidence_ids=["ev_abc123", "ev_def456"],
                rule_citation_ids=["guidance/crs-criteria.md#006"])
            self.assertTrue(ver_id.startswith("ver_"))

            run = vault.load_audit_run(v, run_id)
            self.assertIsNotNone(run)
            self.assertEqual(run["factor_id"], "core.language.first")
            self.assertEqual(run["status"], "running")

            verdicts = vault.list_factor_verdicts(v, run_id)
            self.assertEqual(len(verdicts), 1)
            self.assertEqual(verdicts[0]["verdict"], "SUBSTANTIATED")
            self.assertEqual(verdicts[0]["evidence_ids"],
                             ["ev_abc123", "ev_def456"])
            self.assertEqual(verdicts[0]["rule_citation_ids"],
                             ["guidance/crs-criteria.md#006"])
        finally:
            v.con.close()

    def test_complete_audit_run_stamps_status_and_report(self) -> None:
        v = self._open()
        try:
            run_id = vault.record_audit_run(
                v, candidate_id=v.candidate_id, factor_id="core.language.first",
                rule_registry_version="1")
            vault.complete_audit_run(
                v, run_id, status="complete",
                report_relpath="candidates/default/output/crs-audit/aud.json",
                substantiated_total=116, cutoff_delta=5)
            run = vault.load_audit_run(v, run_id)
            self.assertEqual(run["status"], "complete")
            self.assertEqual(
                run["report_relpath"],
                "candidates/default/output/crs-audit/aud.json")
            self.assertEqual(run["substantiated_total"], 116)
            self.assertEqual(run["cutoff_delta"], 5)
            self.assertIsNotNone(run["completed_at"])
        finally:
            v.con.close()

    def test_ev_and_corpus_ids_stay_in_separate_columns(self) -> None:
        v = self._open()
        try:
            run_id = vault.record_audit_run(
                v, candidate_id=v.candidate_id, factor_id="core.language.first",
                rule_registry_version="1")
            ver_id = vault.record_factor_verdict(
                v, audit_run_id=run_id, factor_id="core.language.first",
                verdict="GAP", evidence_ids=["ev_abc123"],
                rule_citation_ids=["guidance/language-test.md#009"])
            row = v.con.execute(
                "SELECT evidence_ids_json, rule_citation_ids_json "
                "FROM factor_verdicts WHERE verdict_id = ?", (ver_id,)
            ).fetchone()
            # ev_ id lives ONLY in the evidence column.
            self.assertIn("ev_abc123", row["evidence_ids_json"])
            self.assertNotIn("ev_abc123", row["rule_citation_ids_json"])
            # corpus id lives ONLY in the citation column.
            self.assertIn("guidance/language-test.md#009",
                          row["rule_citation_ids_json"])
            self.assertNotIn("guidance/language-test.md",
                             row["evidence_ids_json"])
        finally:
            v.con.close()

    def test_invalid_verdict_raises_vault_error(self) -> None:
        v = self._open()
        try:
            run_id = vault.record_audit_run(
                v, candidate_id=v.candidate_id, factor_id="core.language.first",
                rule_registry_version="1")
            with self.assertRaises(vault.VaultError):
                vault.record_factor_verdict(
                    v, audit_run_id=run_id, factor_id="core.language.first",
                    verdict="GREEN", evidence_ids=[], rule_citation_ids=[])
        finally:
            v.con.close()

    def test_load_missing_run_is_none(self) -> None:
        v = self._open()
        try:
            self.assertIsNone(vault.load_audit_run(v, "aud_does_not_exist"))
            self.assertEqual(vault.list_factor_verdicts(v, "aud_none"), [])
        finally:
            v.con.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
