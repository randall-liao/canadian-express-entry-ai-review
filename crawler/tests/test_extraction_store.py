"""Offline unit tests for the extraction/confirmation store (Phase 30 — Plan 01).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network (mirrors
``crawler/tests/test_vault.py``). Every test points ``$PR_PERSONAL_DIR`` at a
throwaway ``tempfile.TemporaryDirectory`` so the vault is created under a tmp
candidate root and NEVER touches the real git-ignored ``personal/`` tree. ALL
rows are SYNTHETIC (fake values); no extraction dependency is imported — the
trust logic is proven with directly-inserted ``pending`` rows.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_extraction_store.py -q

Behaviour map:

    TestModels            — Pydantic boundary validation + PII-light summaries (Task 1)
    TestSchemaV2Migration — user_version→2 migration; v1 rows preserved (Task 2)
    TestStoreFunctions    — record/add/list store funcs; forced-pending insert (Task 2)
    TestAuditGate         — SC3 quarantine gate matrix (Task 3)
    TestStaleness         — SC4 five-key staleness invalidation (Task 3)
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic import ValidationError
import yaml

from crawler import crs_rules, paths, vault
from crawler.models import vault as models
from crawler.models.vault import CrsProfileFactor


class _VaultTmpCase(unittest.TestCase):
    """Base case: a fresh tmp personal root ($PR_PERSONAL_DIR) per test.

    Mirrors ``crawler/tests/test_vault.py::_VaultTmpCase`` so the vault is
    created under a throwaway tmp candidate root and never touches the real
    git-ignored ``personal/`` tree.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _seed_pending_value(self, v, *, field_name="clb_speaking",
                            quality_flag="ok", factor_id=None,
                            normalized_value=8, raw_text="Speaking: 8",
                            with_page=True, file_sha256="a" * 64):
        """Insert a synthetic document + run + (page) + one pending value.

        Returns the minted value_id. All data is SYNTHETIC. Uses the Plan-01
        store so the quarantine invariant (forced 'pending') is exercised.
        """
        vault.create_candidate(v, "default")
        document_id = vault.new_document_id()
        evidence_id = vault.new_evidence_id()
        now = vault._now()
        v.con.execute(
            "INSERT INTO documents(document_id, candidate_id, evidence_id, "
            "doc_type, file_sha256, storage_relpath, original_name, mime_type, "
            "byte_size, page_count, added_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (document_id, "default", evidence_id, "language_test", file_sha256,
             f"files/raw/{file_sha256}.pdf", None, None, 10, 1, now, "extracted"),
        )
        v.con.commit()
        run_id = vault.record_extraction_run(
            v, document_id=document_id, parser_version="1",
            engine_json={"pdfminer": "x"}, status="complete")
        page_id = None
        if with_page:
            page_id = vault.add_document_page(
                v, document_id=document_id, page_number=1,
                image_relpath=f"files/rendered/{document_id}/page-0001.png",
                render_sha256="b" * 64, extraction_run_id=run_id)
        if factor_id is not None:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id=factor_id, factor_group="core_human_capital",
                claimed_points=None, claimed_level="CLB 9",
                claimed_value={"clb": 9}, source="user_entry"))
        value_id = vault.add_extracted_value(
            v, document_id=document_id, page_id=page_id, factor_id=factor_id,
            field_name=field_name, raw_text=raw_text,
            normalized_value=normalized_value, bbox=[1, 2, 3, 4],
            extractor_confidence=0.9, quality_flag=quality_flag,
            extraction_run_id=run_id)
        return value_id


class TestSchemaV2Migration(_VaultTmpCase):
    """Task 2: schema v2 migration is additive + non-destructive."""

    def test_fresh_vault_is_v2_with_four_tables(self) -> None:
        v = vault.open_vault("default")
        try:
            # Schema now migrates through to v3 (Phase 32); the v2 extraction
            # tables remain present after the additive audit-trail migration.
            self.assertEqual(
                v.con.execute("PRAGMA user_version").fetchone()[0], 3)
            names = {
                r["name"] for r in v.con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table in ("extraction_runs", "document_pages",
                          "extracted_values", "factor_evidence"):
                self.assertIn(table, names)
        finally:
            v.con.close()

    def test_v1_vault_upgrades_in_place_preserving_rows(self) -> None:
        # Build a realistic Phase-29 (user_version=1) DB directly, seed rows,
        # then prove open_vault migrates it to v2 without losing v1 data.
        root = paths.candidate_root("default")
        root.mkdir(parents=True, exist_ok=True)
        db_path = paths.resolve_within(root, "vault.sqlite")
        con = sqlite3.connect(str(db_path))
        con.executescript(vault._SCHEMA_V1_DDL)
        con.execute("INSERT INTO vault_meta(key, value) VALUES ('schema_version', '1')")
        con.execute("INSERT INTO vault_meta(key, value) VALUES ('vault_kind', 'candidate')")
        now = vault._now()
        con.execute(
            "INSERT INTO candidates(candidate_id, label, created_at, updated_at) "
            "VALUES ('default', 'Legacy', ?, ?)", (now, now))
        con.execute(
            "INSERT INTO crs_profile_factors(factor_id, factor_group, "
            "claimed_points, claimed_level, claimed_value_json, source, "
            "confirmed_at, updated_at) VALUES "
            "('core_age', 'core_human_capital', 100, NULL, '{}', 'user_entry', NULL, ?)",
            (now,))
        con.execute(
            "INSERT INTO documents(document_id, candidate_id, evidence_id, "
            "doc_type, file_sha256, storage_relpath, original_name, mime_type, "
            "byte_size, page_count, added_at, status) VALUES "
            "('doc_legacy', 'default', 'ev_legacy', 'eca', 'deadbeef', "
            "'files/raw/deadbeef.pdf', NULL, NULL, 5, 1, ?, 'added')", (now,))
        con.execute("PRAGMA user_version = 1")
        con.commit()
        con.close()

        v = vault.open_vault("default")
        try:
            # v1 → v2 → v3: a Phase-29 DB upgrades through both additive
            # migrations in place, preserving all v1 rows.
            self.assertEqual(
                v.con.execute("PRAGMA user_version").fetchone()[0], 3)
            # v1 rows intact.
            cand = vault.select_candidate(v, "default")
            self.assertEqual(cand.label, "Legacy")
            factors = vault.load_profile_factors(v, "default")
            self.assertEqual(len(factors), 1)
            self.assertEqual(factors[0].factor_id, "core_age")
            doc = v.con.execute(
                "SELECT doc_type FROM documents WHERE document_id = 'doc_legacy'"
            ).fetchone()
            self.assertEqual(doc["doc_type"], "eca")
            # New tables + meta present.
            names = {
                r["name"] for r in v.con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")
            }
            self.assertIn("extracted_values", names)
            self.assertEqual(vault.vault_meta(v, "schema_version"), "3")
            self.assertEqual(vault.vault_meta(v, "rule_registry_version"), "0")
        finally:
            v.con.close()


class TestStoreFunctions(_VaultTmpCase):
    """Task 2: extraction/confirmation store functions + forced-pending insert."""

    def test_add_extracted_value_always_pending(self) -> None:
        v = vault.open_vault("default")
        try:
            value_id = self._seed_pending_value(v)
            row = v.con.execute(
                "SELECT confirmation_status, quality_flag, field_name "
                "FROM extracted_values WHERE value_id = ?", (value_id,)
            ).fetchone()
            self.assertEqual(row["confirmation_status"], "pending")
            self.assertEqual(row["quality_flag"], "ok")
            self.assertEqual(row["field_name"], "clb_speaking")
        finally:
            v.con.close()

    def test_store_functions_mint_prefixed_ids(self) -> None:
        self.assertTrue(vault.new_extraction_run_id().startswith("ext_"))
        self.assertTrue(vault.new_page_id().startswith("pg_"))
        self.assertTrue(vault.new_value_id().startswith("val_"))

    def test_list_and_get_extracted_values(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._seed_pending_value(v, field_name="test_date",
                                           normalized_value={"iso": "2026-01-15"})
            all_vals = vault.list_extracted_values(v)
            self.assertEqual(len(all_vals), 1)
            self.assertIsInstance(all_vals[0], models.ExtractedValue)
            self.assertEqual(all_vals[0].field_name, "test_date")
            self.assertEqual(all_vals[0].normalized_value, {"iso": "2026-01-15"})
            pend = vault.list_extracted_values(v, status="pending")
            self.assertEqual(len(pend), 1)
            self.assertEqual(len(vault.list_extracted_values(v, status="confirmed")), 0)
            got = vault.get_extracted_value(v, vid)
            self.assertIsNotNone(got)
            self.assertEqual(got.value_id, vid)
            self.assertIsNone(vault.get_extracted_value(v, "val_nope"))
        finally:
            v.con.close()

    def test_extraction_run_records_parser_version(self) -> None:
        v = vault.open_vault("default")
        try:
            self._seed_pending_value(v)
            row = v.con.execute(
                "SELECT parser_version, status FROM extraction_runs LIMIT 1"
            ).fetchone()
            self.assertEqual(row["parser_version"], "1")
            self.assertEqual(row["status"], "complete")
        finally:
            v.con.close()


class TestModels(unittest.TestCase):
    """Task 1: extraction/confirmation Pydantic boundary models."""

    def _valid_value_kwargs(self) -> dict:
        return dict(
            value_id="val_abc123",
            document_id="doc_abc123",
            page_id="pg_abc123",
            factor_id="lang_speaking",
            field_name="clb_speaking",
            raw_text="Speaking: 8",
            normalized_value=8,
            bbox=[10, 20, 30, 40],
            extractor_confidence=0.9,
            quality_flag="ok",
            extraction_run_id="ext_abc123",
            confirmation_status="pending",
        )

    def test_extracted_value_rejects_bad_confirmation_status(self) -> None:
        kwargs = self._valid_value_kwargs()
        kwargs["confirmation_status"] = "approved"  # out-of-vocabulary
        with self.assertRaises(ValidationError):
            models.ExtractedValue(**kwargs)

    def test_extracted_value_rejects_bad_quality_flag(self) -> None:
        kwargs = self._valid_value_kwargs()
        kwargs["quality_flag"] = "great"  # out-of-vocabulary
        with self.assertRaises(ValidationError):
            models.ExtractedValue(**kwargs)

    def test_extracted_value_rejects_bad_field_name(self) -> None:
        kwargs = self._valid_value_kwargs()
        kwargs["field_name"] = "favourite_colour"  # not in FieldName vocabulary
        with self.assertRaises(ValidationError):
            models.ExtractedValue(**kwargs)

    def test_extracted_value_accepts_valid_row(self) -> None:
        v = models.ExtractedValue(**self._valid_value_kwargs())
        self.assertEqual(v.field_name, "clb_speaking")
        self.assertEqual(v.confirmation_status, "pending")
        self.assertEqual(v.quality_flag, "ok")
        # normalized_value is JSON-serializable arbitrary data.
        self.assertEqual(v.normalized_value, 8)

    def test_extracted_value_accepts_structural_normalized_value(self) -> None:
        kwargs = self._valid_value_kwargs()
        kwargs["field_name"] = "test_date"
        kwargs["normalized_value"] = {"iso": "2026-01-15"}
        v = models.ExtractedValue(**kwargs)
        self.assertEqual(v.normalized_value, {"iso": "2026-01-15"})

    def test_summary_is_pii_light(self) -> None:
        s = models.ExtractedValueSummary(
            value_id="val_abc123",
            field_name="clb_speaking",
            confirmation_status="pending",
            quality_flag="ok",
            factor_id="lang_speaking",
            stale=False,
        )
        keys = set(s.model_dump().keys())
        self.assertEqual(
            keys,
            {"value_id", "field_name", "confirmation_status",
             "quality_flag", "factor_id", "stale"},
        )
        # PII-bearing fields must NOT exist on the summary model at all.
        for forbidden in ("raw_text", "normalized_value", "bbox",
                          "image_relpath", "confirmed_value"):
            self.assertNotIn(forbidden, keys)

    def test_summary_blob_carries_no_raw_or_normalized(self) -> None:
        s = models.ExtractedValueSummary(
            value_id="val_1", field_name="raw_score_listening",
            confirmation_status="confirmed", quality_flag="ok",
            factor_id=None, stale=False,
        )
        blob = s.model_dump_json()
        self.assertNotIn("raw_text", blob)
        self.assertNotIn("normalized", blob)
        self.assertNotIn("bbox", blob)

    def test_run_and_page_summaries_expose_ids_counts_only(self) -> None:
        run = models.ExtractionRunSummary(
            extraction_run_id="ext_1", document_id="doc_1",
            status="complete", value_count=3, page_count=2,
        )
        page = models.DocumentPageSummary(
            page_id="pg_1", document_id="doc_1", page_number=1,
            has_image=True, has_text=True,
        )
        run_keys = set(run.model_dump().keys())
        page_keys = set(page.model_dump().keys())
        # No raw text / normalized value / filesystem path on either summary.
        for forbidden in ("raw_text", "normalized_value", "image_relpath",
                          "text_relpath"):
            self.assertNotIn(forbidden, run_keys)
            self.assertNotIn(forbidden, page_keys)

    def test_field_name_vocabulary_is_complete(self) -> None:
        # The EXTRACT-01 field vocabulary must be accepted verbatim.
        import typing
        from crawler import mecfields

        allowed = set(typing.get_args(models.FieldName))
        expected = {
            "test_type", "test_date", "clb_listening", "clb_reading",
            "clb_writing", "clb_speaking", "raw_score_listening",
            "raw_score_reading", "raw_score_writing", "raw_score_speaking",
            "reference_number", "date_of_birth", "credential", "credential_level",
            "eca_organization", "eca_report_date", "issuer", "noc_code",
            "teer", "hours_per_week", "employment_start", "employment_end",
            "duration_months", "nomination_stream", "expiry_date",
            "sibling_relationship", "sibling_status", "sibling_residence",
            "sibling_date_of_birth",
            # Phase 43 (NOC-02): grounded NOC-2021 duty worksheet confirmation
            # surface — born-pending values on the inert review.noc factor.
            "noc_lead_statement", "noc_duty",
            # Phase 44 (STUDY-02): quarantined Canadian-study evidence fields.
            "institution_name", "dli_number", "program_start", "program_end",
            "study_status",
            # Phase 45: private review.mec evidence surface.
            *mecfields.MEC_ADDITIVE_FIELDS,
        }
        self.assertEqual(allowed, expected)

    def test_mec_additive_vocabulary_and_factor_group_are_exact(self) -> None:
        import typing

        from crawler import mecfields

        self.assertEqual(
            typing.get_args(models.FactorGroup),
            (
                "core_human_capital",
                "spouse_common_law",
                "skill_transferability",
                "additional_points",
                "program_eligibility",
            ),
        )
        allowed = set(typing.get_args(models.FieldName))
        self.assertEqual(
            allowed,
            {
                "test_type", "test_date", "clb_listening", "clb_reading",
                "clb_writing", "clb_speaking", "raw_score_listening",
                "raw_score_reading", "raw_score_writing", "raw_score_speaking",
                "reference_number", "date_of_birth", "credential", "credential_level",
                "eca_organization", "eca_report_date", "issuer", "noc_code",
                "teer", "hours_per_week", "employment_start", "employment_end",
                "duration_months", "nomination_stream", "expiry_date",
                "sibling_relationship", "sibling_status", "sibling_residence",
                "sibling_date_of_birth", "noc_lead_statement", "noc_duty",
                "institution_name", "dli_number", "program_start", "program_end",
                "study_status",
                *mecfields.MEC_ADDITIVE_FIELDS,
            },
        )
        self.assertEqual(
            set().union(*map(set, mecfields.MEC_DOCUMENT_FIELDS.values())),
            mecfields.MEC_FIELDS,
        )


class TestAuditGate(_VaultTmpCase):
    """Task 3 / SC3: only confirmed|corrected + quality ok + not-stale is eligible."""

    def _make_value(self, v, *, quality_flag="ok"):
        """Seed one value linked to a factor + page, return its value_id."""
        return self._seed_pending_value(
            v, quality_flag=quality_flag, factor_id="lang_speaking")

    def test_sc3_eligibility_matrix(self) -> None:
        v = vault.open_vault("default")
        try:
            for status in ("pending", "confirmed", "corrected", "rejected"):
                for quality in ("ok", "low_quality", "ambiguous"):
                    with self.subTest(status=status, quality=quality):
                        vid = self._make_value(v, quality_flag=quality)
                        if status == "confirmed":
                            vault.confirm_value(v, vid, "confirm")
                        elif status == "corrected":
                            vault.confirm_value(v, vid, "correct",
                                                corrected_value={"clb": 9})
                        elif status == "rejected":
                            vault.confirm_value(v, vid, "reject")
                        # pending: leave as-is.
                        eligible = vault.is_audit_eligible(v, vid)
                        expected = (status in ("confirmed", "corrected")
                                    and quality == "ok")
                        self.assertEqual(eligible, expected)
        finally:
            v.con.close()

    def test_mec_period_correction_preserves_its_stamped_document_key(self) -> None:
        from crawler import mecfields

        v = vault.open_vault("default")
        try:
            vault.create_candidate(v, "default")
            vault.upsert_profile_factor(
                v,
                CrsProfileFactor(
                    factor_id="review.mec",
                    factor_group="program_eligibility",
                    claimed_value={},
                    source="user_entry",
                ),
            )
            file_sha = "e" * 64
            document_id = vault.new_document_id()
            v.con.execute(
                "INSERT INTO documents(document_id, candidate_id, evidence_id, "
                "doc_type, file_sha256, storage_relpath, original_name, mime_type, "
                "byte_size, page_count, added_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    document_id, "default", vault.new_evidence_id(),
                    "mec-employment-period", file_sha,
                    f"files/raw/{file_sha}.pdf", None, None, 1, 1,
                    vault._now(), "extracted",
                ),
            )
            v.con.commit()
            run_id = vault.record_extraction_run(
                v, document_id=document_id, parser_version="1", status="complete"
            )
            page_id = vault.add_document_page(
                v,
                document_id=document_id,
                page_number=1,
                render_sha256="f" * 64,
                extraction_run_id=run_id,
            )
            period_id = mecfields.employment_period_id(file_sha)
            key_id = vault.add_extracted_value(
                v, document_id=document_id, page_id=page_id,
                factor_id="review.mec", field_name="employment_period_id",
                raw_text=None, normalized_value=period_id, bbox=None,
                extractor_confidence=1.0, quality_flag="ok",
                extraction_run_id=run_id,
            )
            paid_id = vault.add_extracted_value(
                v, document_id=document_id, page_id=page_id,
                factor_id="review.mec", field_name="paid_status",
                raw_text="yes",
                normalized_value={
                    "employment_period_id": period_id,
                    "value": True,
                },
                bbox=None, extractor_confidence=1.0, quality_flag="ok",
                extraction_run_id=run_id,
            )
            fingerprint = crs_rules.load_registry_snapshot().fingerprint
            vault.confirm_value(
                v, key_id, "confirm", registry_fingerprint=fingerprint
            )
            vault.confirm_value(
                v, paid_id, "correct", corrected_value=False,
                registry_fingerprint=fingerprint,
            )
            evidence = mecfields.load_mec_evidence(
                v, "default", fingerprint
            )
            self.assertEqual(len(evidence.periods), 1)
            self.assertTrue(evidence.periods[0].usable)
            self.assertIs(evidence.periods[0].values["paid_status"], False)
        finally:
            v.con.close()

    def test_pending_is_never_eligible(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._make_value(v)
            self.assertFalse(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_confirm_captures_binding_keys(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._make_value(v)
            vault.confirm_value(v, vid, "confirm")
            row = v.con.execute(
                "SELECT confirmed_file_sha256, confirmed_render_sha256, "
                "confirmed_parser_version, confirmed_profile_claim_version, "
                "confirmed_rule_registry_version, confirmation_status "
                "FROM extracted_values WHERE value_id = ?", (vid,)
            ).fetchone()
            self.assertEqual(row["confirmation_status"], "confirmed")
            self.assertIsNotNone(row["confirmed_file_sha256"])
            self.assertIsNotNone(row["confirmed_render_sha256"])
            self.assertEqual(row["confirmed_parser_version"], "1")
            self.assertIsNotNone(row["confirmed_profile_claim_version"])
            self.assertEqual(
                row["confirmed_rule_registry_version"],
                vault.live_registry_fingerprint())
        finally:
            v.con.close()

    def test_reject_clears_binding_keys(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._make_value(v)
            vault.confirm_value(v, vid, "confirm")
            vault.confirm_value(v, vid, "reject")
            row = v.con.execute(
                "SELECT confirmed_file_sha256, confirmed_parser_version, "
                "confirmation_status FROM extracted_values WHERE value_id = ?",
                (vid,)
            ).fetchone()
            self.assertEqual(row["confirmation_status"], "rejected")
            self.assertIsNone(row["confirmed_file_sha256"])
            self.assertIsNone(row["confirmed_parser_version"])
            self.assertFalse(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_correct_stores_corrected_value(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._make_value(v)
            vault.confirm_value(v, vid, "correct", corrected_value={"clb": 10})
            got = vault.get_extracted_value(v, vid)
            self.assertEqual(got.confirmation_status, "corrected")
            self.assertEqual(got.confirmed_value, {"clb": 10})
            self.assertTrue(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_audit_eligible_values_query(self) -> None:
        v = vault.open_vault("default")
        try:
            vid_ok = self._make_value(v)
            vault.confirm_value(v, vid_ok, "confirm")
            vid_pending = self._make_value(v)  # stays pending
            vid_lowq = self._make_value(v, quality_flag="low_quality")
            vault.confirm_value(v, vid_lowq, "confirm")  # confirmed but low_quality
            eligible = vault.audit_eligible_values(v, "lang_speaking")
            ids = {e.value_id for e in eligible}
            self.assertIn(vid_ok, ids)
            self.assertNotIn(vid_pending, ids)
            self.assertNotIn(vid_lowq, ids)
        finally:
            v.con.close()


class TestStaleness(_VaultTmpCase):
    """Task 3 / SC4: any of the five binding keys changing invalidates."""

    def _confirmed_value(self, v):
        vid = self._seed_pending_value(v, quality_flag="ok",
                                       factor_id="lang_speaking")
        vault.confirm_value(v, vid, "confirm")
        # Fresh: eligible + not stale.
        self.assertTrue(vault.is_audit_eligible(v, vid))
        self.assertFalse(vault.is_stale(v, vid))
        return vid

    def test_control_unchanged_stays_eligible(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._confirmed_value(v)
            self.assertFalse(vault.is_stale(v, vid))
            self.assertTrue(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_file_sha_change_invalidates(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._confirmed_value(v)
            got = vault.get_extracted_value(v, vid)
            v.con.execute(
                "UPDATE documents SET file_sha256 = ? WHERE document_id = ?",
                ("f" * 64, got.document_id))
            v.con.commit()
            self.assertTrue(vault.is_stale(v, vid))
            self.assertFalse(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_render_sha_change_invalidates(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._confirmed_value(v)
            got = vault.get_extracted_value(v, vid)
            v.con.execute(
                "UPDATE document_pages SET render_sha256 = ? WHERE page_id = ?",
                ("c" * 64, got.page_id))
            v.con.commit()
            self.assertTrue(vault.is_stale(v, vid))
            self.assertFalse(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_parser_version_change_invalidates(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._confirmed_value(v)
            with mock.patch.object(vault, "current_parser_version",
                                   return_value="999"):
                self.assertTrue(vault.is_stale(v, vid))
                self.assertFalse(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_profile_claim_change_invalidates(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._confirmed_value(v)
            # Edit the linked factor's claimed_value → new profile-claim version.
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="lang_speaking", factor_group="core_human_capital",
                claimed_points=None, claimed_level="CLB 10",
                claimed_value={"clb": 10}, source="user_entry"))
            self.assertTrue(vault.is_stale(v, vid))
            self.assertFalse(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_mutable_registry_metadata_does_not_invalidate(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._confirmed_value(v)
            vault.set_rule_registry_version(v, "1")
            self.assertFalse(vault.is_stale(v, vid))
            self.assertTrue(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_reconfirm_clears_staleness(self) -> None:
        v = vault.open_vault("default")
        try:
            vid = self._confirmed_value(v)
            v.con.execute(
                "UPDATE extracted_values "
                "SET confirmed_rule_registry_version = 'obsolete' "
                "WHERE value_id = ?", (vid,))
            v.con.commit()
            self.assertTrue(vault.is_stale(v, vid))
            # Re-confirm re-captures the current binding keys.
            vault.confirm_value(v, vid, "confirm")
            self.assertFalse(vault.is_stale(v, vid))
            self.assertTrue(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_real_registry_row_content_drift_invalidates_confirmation(self) -> None:
        registry_dir = Path(self._tmp.name) / "registry"
        shutil.copytree(crs_rules.DEFAULT_DATA_DIR, registry_dir)
        real_load = crs_rules.load_registry_snapshot

        def load_copy():
            return real_load(registry_dir)

        v = vault.open_vault("default")
        try:
            with mock.patch.object(
                    crs_rules, "load_registry_snapshot", side_effect=load_copy):
                vid = self._confirmed_value(v)
                yaml_path = sorted(registry_dir.glob("*.yaml"))[0]
                document = yaml.safe_load(
                    yaml_path.read_text(encoding="utf-8"))
                document["rows"][0]["claim_text"] += " (drifted)"
                yaml_path.write_text(
                    yaml.safe_dump(document, sort_keys=False),
                    encoding="utf-8")
                self.assertTrue(vault.is_stale(v, vid))
                self.assertFalse(vault.is_audit_eligible(v, vid))
        finally:
            v.con.close()

    def test_registry_failure_refuses_confirmation_and_eligibility(self) -> None:
        v = vault.open_vault("default")
        try:
            pending = self._seed_pending_value(
                v, quality_flag="ok", factor_id="lang_speaking")
            with mock.patch(
                    "crawler.crs_rules.load_registry_snapshot",
                    side_effect=crs_rules.RegistryUnavailable(
                        "CRS rule registry unavailable")):
                with self.assertRaisesRegex(
                        vault.VaultError, "^rule registry unavailable$"):
                    vault.confirm_value(v, pending, "confirm")
            self.assertEqual(
                vault.get_extracted_value(v, pending).confirmation_status,
                "pending")

            confirmed = self._confirmed_value(v)
            with mock.patch(
                    "crawler.crs_rules.load_registry_snapshot",
                    side_effect=crs_rules.RegistryUnavailable(
                        "CRS rule registry unavailable")):
                self.assertTrue(vault.is_stale(v, confirmed))
                self.assertFalse(vault.is_audit_eligible(v, confirmed))
                self.assertEqual(
                    vault.audit_eligible_values(v, "lang_speaking"), [])
        finally:
            v.con.close()

    def test_profile_claim_version_is_stable(self) -> None:
        v = vault.open_vault("default")
        try:
            vault.create_candidate(v, "default")
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id="f1", factor_group="core_human_capital",
                claimed_points=10, claimed_level="CLB 9",
                claimed_value={"clb": 9}, source="user_entry"))
            a = vault.profile_claim_version(v, "f1")
            b = vault.profile_claim_version(v, "f1")
            self.assertEqual(a, b)
            self.assertIsNone(vault.profile_claim_version(v, None))
            self.assertIsNone(vault.profile_claim_version(v, "missing"))
        finally:
            v.con.close()


if __name__ == "__main__":
    unittest.main()
