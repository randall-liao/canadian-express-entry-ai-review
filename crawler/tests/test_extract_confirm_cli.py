"""Offline tests for the confirm-what-I-read CLI + orchestration (Phase 30 — Plan 03).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Each test points
``$PR_PERSONAL_DIR`` at a throwaway ``tempfile.TemporaryDirectory``. Unit cases
insert SYNTHETIC pending values directly via the Plan-01 store (no real
extraction); end-to-end cases drive ``crawler.cli.main`` over synthetic fixtures.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_extract_confirm_cli.py -q
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import confirm, crs_rules, paths, vault
from crawler.models.vault import CrsProfileFactor
from crawler.tests.fixtures.extraction import make_fixtures as mf


class _ConfirmTmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _seed(self, v, *, field_name="raw_score_speaking", quality_flag="ok",
              raw_text="Speaking: 8.5", normalized_value=8.5,
              factor_id="lang_core", file_sha256="a" * 64):
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
             f"files/raw/{file_sha256}.pdf", None, None, 10, 1, now, "extracted"))
        v.con.commit()
        run_id = vault.record_extraction_run(
            v, document_id=document_id, parser_version="1",
            engine_json={"e": "1"}, status="complete")
        page_id = vault.add_document_page(
            v, document_id=document_id, page_number=1,
            image_relpath=f"files/rendered/{document_id}/page-0001.png",
            render_sha256="b" * 64, extraction_run_id=run_id)
        if factor_id is not None:
            vault.upsert_profile_factor(v, CrsProfileFactor(
                factor_id=factor_id, factor_group="core_human_capital",
                claimed_points=124, claimed_level="CLB 9",
                claimed_value={"clb": 9}, source="user_entry"))
        vid = vault.add_extracted_value(
            v, document_id=document_id, page_id=page_id, factor_id=factor_id,
            field_name=field_name, raw_text=raw_text,
            normalized_value=normalized_value, bbox=[10, 20, 30, 40],
            extractor_confidence=0.9, quality_flag=quality_flag,
            extraction_run_id=run_id)
        return document_id, vid


class TestFieldView(_ConfirmTmpCase):
    def test_view_exposes_all_five_facets(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(v)
            view = confirm.build_field_view(v, vid)
            # (1) raw value, (2) normalized value
            self.assertEqual(view["raw_value"], "Speaking: 8.5")
            self.assertEqual(view["normalized_value"], 8.5)
            # (3) source page/crop
            self.assertEqual(view["page_number"], 1)
            self.assertTrue(view["image_relpath"].startswith("files/rendered/"))
            self.assertEqual(view["bbox"], [10, 20, 30, 40])
            # (4) affected CRS factor
            self.assertEqual(view["factor_id"], "lang_core")
            self.assertEqual(view["factor_group"], "core_human_capital")
            # (5) the profile claim it substantiates
            self.assertEqual(view["claimed_level"], "CLB 9")
            self.assertEqual(view["claimed_points"], 124)
            self.assertEqual(view["claimed_value"], {"clb": 9})
            # plus status/quality/stale
            self.assertEqual(view["confirmation_status"], "pending")
            self.assertEqual(view["quality_flag"], "ok")
            self.assertFalse(view["stale"])
            self.assertFalse(view["audit_eligible"])
        finally:
            v.con.close()

    def test_summary_is_pii_light(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(v)
            summary = confirm.build_field_view_summary(v, vid)
            self.assertEqual(
                set(summary.keys()),
                {"value_id", "field_name", "confirmation_status",
                 "quality_flag", "factor_id", "stale", "audit_eligible"})
            blob = json.dumps(summary)
            for forbidden in ("Speaking", "8.5", "files/rendered", "bbox"):
                self.assertNotIn(forbidden, blob)
        finally:
            v.con.close()

    def test_list_field_views_returns_summaries(self) -> None:
        v = vault.open_vault("default")
        try:
            doc, _ = self._seed(v)
            self._seed(v, field_name="test_date", raw_text="Test Date",
                       normalized_value="2026-01-15", factor_id="lang_core")
            views = confirm.list_field_views(v)
            self.assertGreaterEqual(len(views), 2)
            for s in views:
                self.assertEqual(
                    set(s.keys()),
                    {"value_id", "field_name", "confirmation_status",
                     "quality_flag", "factor_id", "stale", "audit_eligible"})
        finally:
            v.con.close()


class TestApplyDecision(_ConfirmTmpCase):
    def test_apply_decision_confirms_exactly_one(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid1 = self._seed(v)
            _, vid2 = self._seed(v, field_name="raw_score_reading",
                                 raw_text="Reading: 7.5", normalized_value=7.5)
            summary = confirm.apply_decision(v, vid1, "confirm")
            self.assertEqual(summary["confirmation_status"], "confirmed")
            self.assertTrue(summary["audit_eligible"])
            # The OTHER value is untouched (still pending).
            other = vault.get_extracted_value(v, vid2)
            self.assertEqual(other.confirmation_status, "pending")
        finally:
            v.con.close()

    def test_correct_requires_corrected_value(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(v)
            with self.assertRaises(vault.VaultError):
                confirm.apply_decision(v, vid, "correct")
        finally:
            v.con.close()

    def test_invalid_decision_raises(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(v)
            with self.assertRaises(vault.VaultError):
                confirm.apply_decision(v, vid, "approve")
        finally:
            v.con.close()

    def test_stale_value_reports_not_eligible_until_reconfirm(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(v)
            confirm.apply_decision(v, vid, "confirm")
            self.assertTrue(confirm.build_field_view_summary(v, vid)["audit_eligible"])
            v.con.execute(
                "UPDATE extracted_values "
                "SET confirmed_rule_registry_version = 'obsolete' "
                "WHERE value_id = ?", (vid,))
            v.con.commit()
            s = confirm.build_field_view_summary(v, vid)
            self.assertTrue(s["stale"])
            self.assertFalse(s["audit_eligible"])
            # Re-confirm clears staleness.
            confirm.apply_decision(v, vid, "confirm")
            s2 = confirm.build_field_view_summary(v, vid)
            self.assertFalse(s2["stale"])
            self.assertTrue(s2["audit_eligible"])
        finally:
            v.con.close()


class TestExtractConfirmCli(unittest.TestCase):
    """Task 3: end-to-end SC1–SC4 conformance through crawler.cli.main."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()
        self._json_stdout: list[str] = []

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        from crawler import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        if "--json" in argv:
            self._json_stdout.append(out.getvalue())
        return rc, out.getvalue(), err.getvalue()

    def _one_envelope(self, stdout: str) -> dict:
        data = json.loads(stdout)
        self.assertEqual(
            set(data.keys()),
            {"schema_version", "ok", "command", "result", "error"})
        self.assertEqual(data["command"], "vault")
        self.assertEqual(data["schema_version"], "1.0")
        return data

    def _import(self, data: bytes, doc_type: str, ext: str = ".pdf") -> str:
        src = Path(self._tmp.name) / f"fixture{ext}"
        src.write_bytes(data)
        rc, out, _ = self._run(
            ["--json", "vault", "import", str(src), "--doc-type", doc_type])
        self.assertEqual(rc, 0)
        return self._one_envelope(out)["result"]["document_id"]

    def _set_factor(self) -> None:
        rc, _, _ = self._run([
            "--json", "vault", "profile", "set",
            "--factor-id", "core.language.first", "--group", "core_human_capital",
            "--points", "124", "--level", "CLB 9", "--value-json", '{"clb": 9}'])
        self.assertEqual(rc, 0)

    def _fields(self, extra: "list[str] | None" = None) -> list[dict]:
        rc, out, _ = self._run(
            ["--json", "vault", "fields"] + (extra or []))
        self.assertEqual(rc, 0)
        return self._one_envelope(out)["result"]["fields"]

    # -- SC1 --------------------------------------------------------------- #
    def test_sc1_extract_produces_pending_only(self) -> None:
        doc = self._import(mf.language_test_pdf(), "language_test")
        rc, out, _ = self._run(["--json", "vault", "extract",
                                "--document-id", doc])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["values_pending"], 7)
        for field_summary in self._fields():
            self.assertEqual(field_summary["confirmation_status"], "pending")
            self.assertFalse(field_summary["audit_eligible"])

    # -- SC2 --------------------------------------------------------------- #
    def test_sc2_human_shows_facets_json_is_pii_light(self) -> None:
        self._set_factor()
        doc = self._import(mf.language_test_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        # Human view (stderr) shows all five facets.
        _, out_human, err_human = self._run(["vault", "fields"])
        self.assertEqual(out_human.strip(), "")           # stdout empty in human mode
        self.assertIn(mf.FAKE_TRF, err_human)             # raw value
        self.assertIn("2026-01-15", err_human)            # normalized date
        self.assertIn("files/rendered/", err_human)       # source page/crop
        self.assertIn("core.language.first", err_human)   # affected CRS factor
        self.assertIn("CLB 9", err_human)                 # profile claim
        # --json envelope carries NONE of those PII facets.
        _, out_json, _ = self._run(["--json", "vault", "fields"])
        env = self._one_envelope(out_json)
        for token in (mf.FAKE_TRF, "2026-01-15", "files/rendered", "CLB 9",
                      "8.5"):
            self.assertNotIn(token, out_json)
        for field_summary in env["result"]["fields"]:
            self.assertEqual(
                set(field_summary.keys()),
                {"value_id", "field_name", "confirmation_status",
                 "quality_flag", "factor_id", "stale", "audit_eligible"})

    # -- SC3 --------------------------------------------------------------- #
    def test_sc3_only_confirmed_ok_fresh_is_eligible(self) -> None:
        doc = self._import(mf.language_test_multipage_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        fields = self._fields()
        by_id = {f["value_id"]: f for f in fields}
        # An ok page-1 value → confirm → eligible True.
        ok_val = next(f for f in fields
                      if f["quality_flag"] == "ok"
                      and f["field_name"] == "raw_score_listening")
        rc, out, _ = self._run(["--json", "vault", "confirm",
                                "--value-id", ok_val["value_id"],
                                "--decision", "confirm"])
        self.assertEqual(rc, 0)
        self.assertTrue(self._one_envelope(out)["result"]["audit_eligible"])
        # A low_quality value → confirm → still NOT eligible.
        low_val = next(f for f in fields if f["quality_flag"] == "low_quality")
        rc, out, _ = self._run(["--json", "vault", "confirm",
                                "--value-id", low_val["value_id"],
                                "--decision", "confirm"])
        self.assertEqual(rc, 0)
        self.assertFalse(self._one_envelope(out)["result"]["audit_eligible"])
        # A rejected value → NOT eligible; a pending value → NOT eligible.
        another = next(f for f in fields
                       if f["value_id"] not in (ok_val["value_id"],
                                                low_val["value_id"]))
        rc, out, _ = self._run(["--json", "vault", "confirm",
                                "--value-id", another["value_id"],
                                "--decision", "reject"])
        self.assertFalse(self._one_envelope(out)["result"]["audit_eligible"])
        for f in self._fields(["--status", "pending"]):
            self.assertFalse(f["audit_eligible"])

    def test_sc3_ambiguous_date_never_eligible_even_confirmed(self) -> None:
        doc = self._import(mf.ambiguous_date_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        date_val = next(f for f in self._fields()
                        if f["field_name"] == "test_date")
        self.assertEqual(date_val["quality_flag"], "ambiguous")
        rc, out, _ = self._run(["--json", "vault", "confirm",
                                "--value-id", date_val["value_id"],
                                "--decision", "confirm"])
        # Confirmed but quality != ok → still not audit-eligible.
        self.assertFalse(self._one_envelope(out)["result"]["audit_eligible"])

    # -- SC4 --------------------------------------------------------------- #
    def test_sc4_stale_until_reconfirm(self) -> None:
        self._set_factor()
        doc = self._import(mf.language_test_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        val = next(f for f in self._fields()
                   if f["field_name"] == "raw_score_listening")
        vid = val["value_id"]
        rc, out, _ = self._run(["--json", "vault", "confirm",
                                "--value-id", vid, "--decision", "confirm"])
        self.assertTrue(self._one_envelope(out)["result"]["audit_eligible"])
        # Drift the captured fingerprint fixture → the confirmation goes stale.
        v = vault.open_vault("default")
        try:
            v.con.execute(
                "UPDATE extracted_values "
                "SET confirmed_rule_registry_version = 'obsolete' "
                "WHERE value_id = ?", (vid,))
            v.con.commit()
        finally:
            v.con.close()
        stale = next(f for f in self._fields() if f["value_id"] == vid)
        self.assertTrue(stale["stale"])
        self.assertFalse(stale["audit_eligible"])
        # Re-confirm through the CLI clears staleness.
        rc, out, _ = self._run(["--json", "vault", "confirm",
                                "--value-id", vid, "--decision", "confirm"])
        env = self._one_envelope(out)
        self.assertFalse(env["result"]["stale"])
        self.assertTrue(env["result"]["audit_eligible"])

    def test_registry_load_failure_refuses_confirm_without_traceback(self) -> None:
        self._set_factor()
        doc = self._import(mf.language_test_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        value = next(
            field for field in self._fields()
            if field["field_name"] == "raw_score_listening")
        with mock.patch(
                "crawler.crs_rules.load_registry_snapshot",
                side_effect=crs_rules.RegistryUnavailable(
                    "CRS rule registry unavailable")):
            rc, out, err = self._run([
                "--json", "vault", "confirm",
                "--value-id", value["value_id"], "--decision", "confirm",
            ])
        self.assertEqual(rc, 2)
        envelope = self._one_envelope(out)
        self.assertFalse(envelope["ok"])
        self.assertEqual(
            envelope["error"]["message"], "rule registry unavailable")
        self.assertNotIn("Traceback", out + err)

    def test_registry_failure_precedes_confirmation_vault_open(self) -> None:
        with (
            mock.patch(
                "crawler.crs_rules.load_registry_snapshot",
                side_effect=crs_rules.RegistryUnavailable(
                    "CRS rule registry unavailable"),
            ) as load_snapshot,
            mock.patch("crawler.vault.open_vault") as open_vault,
        ):
            rc, out, err = self._run([
                "--json", "vault", "confirm",
                "--value-id", "val_never_opened", "--decision", "confirm",
            ])
        self.assertEqual(rc, 2)
        self.assertEqual(
            self._one_envelope(out)["error"]["message"],
            "rule registry unavailable",
        )
        load_snapshot.assert_called_once_with()
        open_vault.assert_not_called()
        self.assertNotIn("Traceback", out + err)

    def test_sc4_file_replacement_marks_stale(self) -> None:
        doc = self._import(mf.language_test_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        vid = self._fields()[0]["value_id"]
        self._run(["--json", "vault", "confirm", "--value-id", vid,
                   "--decision", "confirm"])
        # Replace the source file hash (simulate re-import of a new file).
        v = vault.open_vault("default")
        try:
            v.con.execute(
                "UPDATE documents SET file_sha256 = ? WHERE document_id = ?",
                ("f" * 64, doc))
            v.con.commit()
        finally:
            v.con.close()
        s = next(f for f in self._fields() if f["value_id"] == vid)
        self.assertTrue(s["stale"])
        self.assertFalse(s["audit_eligible"])

    # -- Structural rubber-stamp defense ---------------------------------- #
    def test_confirm_requires_a_single_value_id(self) -> None:
        # There is no bulk "confirm all": --value-id is required (argparse errors).
        with self.assertRaises(SystemExit):
            self._run(["--json", "vault", "confirm", "--decision", "confirm"])

    # -- missing dependency ------------------------------------------------ #
    def test_extract_missing_dependency_maps_to_exit_3(self) -> None:
        from crawler import extraction
        doc = self._import(mf.language_test_pdf(), "language_test")
        with mock.patch.object(
                extraction, "_import_pdfium",
                side_effect=extraction.MissingExtractionDependency(
                    "pypdfium2", "doc-extract")):
            rc, out, err = self._run(["--json", "vault", "extract",
                                      "--document-id", doc])
        self.assertEqual(rc, 3)
        env = self._one_envelope(out)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], "missing_dependency")
        self.assertIn("doc-extract", err)

    # -- cross-verb no-PII to stdout -------------------------------------- #
    def test_no_pii_across_all_json_envelopes(self) -> None:
        self._set_factor()
        doc = self._import(mf.language_test_pdf(), "language_test")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        fields = self._fields()
        self._run(["--json", "vault", "confirm",
                   "--value-id", fields[0]["value_id"], "--decision", "confirm"])
        combined = "".join(self._json_stdout)
        for token in (mf.FAKE_TRF, mf.FAKE_LISTENING, mf.FAKE_SPEAKING,
                      "2026-01-15", "files/rendered", self._tmp.name):
            self.assertNotIn(token, combined)

    # -- COV-03 sibling end-to-end through the CLI ------------------------- #
    def test_sibling_proof_extracts_four_pending_and_json_is_pii_light(self) -> None:
        # Free-form --doc-type sibling_proof (no CLI code change): import + extract.
        doc = self._import(mf.sibling_proof_pdf(), "sibling_proof")
        rc, out, _ = self._run(["--json", "vault", "extract",
                                "--document-id", doc])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["values_pending"], 4)
        # Every sibling field is pending + not audit-eligible.
        sibling_names = {"sibling_relationship", "sibling_status",
                         "sibling_residence", "sibling_date_of_birth"}
        seen = set()
        for f in self._fields():
            if f["field_name"] in sibling_names:
                seen.add(f["field_name"])
                self.assertEqual(f["confirmation_status"], "pending")
                self.assertFalse(f["audit_eligible"])
        self.assertEqual(seen, sibling_names)
        # No FAKE sibling PII token on ANY --json stdout envelope.
        combined = "".join(self._json_stdout)
        for token in (mf.FAKE_SIBLING_RELATIONSHIP, mf.FAKE_SIBLING_STATUS,
                      mf.FAKE_SIBLING_RESIDENCE, mf.FAKE_SIBLING_DOB, "1988-03-12"):
            self.assertNotIn(token, combined)

    def test_sibling_confirm_correct_reject_through_cli(self) -> None:
        doc = self._import(mf.sibling_proof_pdf(), "sibling_proof")
        self._run(["--json", "vault", "extract", "--document-id", doc])
        fields = {f["field_name"]: f for f in self._fields()}
        # confirm the status field → audit-eligible True.
        rc, out, _ = self._run([
            "--json", "vault", "confirm",
            "--value-id", fields["sibling_status"]["value_id"],
            "--decision", "confirm"])
        self.assertEqual(rc, 0)
        self.assertTrue(self._one_envelope(out)["result"]["audit_eligible"])
        # correct the relationship field (JSON corrected value) → eligible True.
        rc, out, _ = self._run([
            "--json", "vault", "confirm",
            "--value-id", fields["sibling_relationship"]["value_id"],
            "--decision", "correct", "--corrected-value", '"sister"'])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertEqual(env["result"]["confirmation_status"], "corrected")
        self.assertTrue(env["result"]["audit_eligible"])
        # reject the residence field → NOT eligible.
        rc, out, _ = self._run([
            "--json", "vault", "confirm",
            "--value-id", fields["sibling_residence"]["value_id"],
            "--decision", "reject"])
        self.assertEqual(rc, 0)
        self.assertFalse(self._one_envelope(out)["result"]["audit_eligible"])
        # The DOB field is still pending → NOT eligible (per-field, not bulk).
        for f in self._fields(["--status", "pending"]):
            self.assertFalse(f["audit_eligible"])
        # Still no sibling PII token on any --json envelope.
        combined = "".join(self._json_stdout)
        for token in (mf.FAKE_SIBLING_STATUS, mf.FAKE_SIBLING_RESIDENCE,
                      mf.FAKE_SIBLING_DOB, "1988-03-12"):
            self.assertNotIn(token, combined)


class TestSiblingConfirm(_ConfirmTmpCase):
    """COV-03: each pending sibling field is individually confirm/correct/reject-able
    through the SHIPPED confirm path (``confirm.apply_decision`` → ``vault.confirm_value``
    → the shared ``is_audit_eligible`` choke point) — a pending or rejected value is
    NOT audit-eligible; only a confirmed/corrected + ok + fresh value becomes eligible.
    No bespoke sibling quarantine/validator: the existing choke point is reused."""

    def test_pending_sibling_is_not_eligible_then_confirm_makes_eligible(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(
                v, field_name="sibling_status", raw_text="Status: permanent_resident",
                normalized_value="permanent_resident", factor_id="additional.sibling")
            # Pending → NOT audit-eligible (born-quarantined).
            summary = confirm.build_field_view_summary(v, vid)
            self.assertEqual(summary["confirmation_status"], "pending")
            self.assertFalse(summary["audit_eligible"])
            # Confirm this ONE field → confirmed + eligible.
            confirmed = confirm.apply_decision(v, vid, "confirm")
            self.assertEqual(confirmed["confirmation_status"], "confirmed")
            self.assertTrue(confirmed["audit_eligible"])
        finally:
            v.con.close()

    def test_correct_requires_value_then_makes_eligible(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(
                v, field_name="sibling_relationship",
                raw_text="Relationship: brohter", normalized_value="brohter",
                factor_id="additional.sibling")
            # correct WITHOUT a corrected value is rejected (field/type-only error).
            with self.assertRaises(vault.VaultError):
                confirm.apply_decision(v, vid, "correct")
            # correct WITH a value → corrected + eligible.
            corrected = confirm.apply_decision(
                v, vid, "correct", corrected_value="brother")
            self.assertEqual(corrected["confirmation_status"], "corrected")
            self.assertTrue(corrected["audit_eligible"])
        finally:
            v.con.close()

    def test_reject_sibling_is_never_eligible(self) -> None:
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(
                v, field_name="sibling_status", raw_text="Status: visitor",
                normalized_value="visitor", factor_id="additional.sibling")
            rejected = confirm.apply_decision(v, vid, "reject")
            self.assertEqual(rejected["confirmation_status"], "rejected")
            self.assertFalse(rejected["audit_eligible"])
        finally:
            v.con.close()

    def test_confirm_is_per_field_not_bulk(self) -> None:
        """Confirming one sibling field leaves the others pending (rubber-stamp
        defense is structural — there is no bulk confirm-all)."""
        v = vault.open_vault("default")
        try:
            _, vid_status = self._seed(
                v, field_name="sibling_status",
                raw_text="Status: permanent_resident",
                normalized_value="permanent_resident", factor_id="additional.sibling")
            _, vid_rel = self._seed(
                v, field_name="sibling_relationship", raw_text="Relationship: brother",
                normalized_value="brother", factor_id="additional.sibling")
            confirm.apply_decision(v, vid_status, "confirm")
            # The OTHER sibling field is untouched (still pending, not eligible).
            other = vault.get_extracted_value(v, vid_rel)
            self.assertEqual(other.confirmation_status, "pending")
            self.assertFalse(confirm.build_field_view_summary(
                v, vid_rel)["audit_eligible"])
        finally:
            v.con.close()

    def test_sibling_summary_is_pii_light(self) -> None:
        """The PII-light summary carries NO sibling PII token (reuses the shared
        ExtractedValueSummary shape)."""
        v = vault.open_vault("default")
        try:
            _, vid = self._seed(
                v, field_name="sibling_residence",
                raw_text="Residence: Synthetic City, Ontario",
                normalized_value="Synthetic City, Ontario",
                factor_id="additional.sibling")
            summary = confirm.build_field_view_summary(v, vid)
            self.assertEqual(
                set(summary.keys()),
                {"value_id", "field_name", "confirmation_status",
                 "quality_flag", "factor_id", "stale", "audit_eligible"})
            blob = json.dumps(summary)
            for forbidden in ("Synthetic City", "Ontario", "Residence"):
                self.assertNotIn(forbidden, blob)
        finally:
            v.con.close()


if __name__ == "__main__":
    unittest.main()
