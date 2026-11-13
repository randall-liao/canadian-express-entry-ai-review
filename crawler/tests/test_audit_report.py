"""Tests for the vault-only, fail-closed audit report writer (32-04, AUDIT-02/06).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Reuses the Plan 03
synthetic fixtures (``_AuditorCase`` + ``_language_registry``): a synthetic corpus
index, a synthetic registry, and a synthetic vault under ``$PR_PERSONAL_DIR``.

Proves:
  * SC4 — a SUBSTANTIATED/GAP/AT-RISK/N/A run writes the JSON+MD report ONLY under
    ``candidate_root/output/crs-audit/`` and returns a PII-light envelope whose
    ``private_output_path`` is candidate-root-relative; the JSON file carries the applicant
    value + ``ev_`` id, the envelope carries neither;
  * SC5 — an ``AuditGroundingError`` leaves ZERO artifacts (no file, no rows); a
    grounded GAP/AT-RISK run writes a complete report without raising.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_audit_report.py -q
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from unittest import mock

from crawler import audit_report, auditor, crs_rules, paths, vault
from crawler.models.audit import PublicAuditEnvelope
from crawler.tests.test_auditor import _AuditorCase, _language_registry

# A distinctive raw score (maps to the upper benchmark band [7.0, 9.0]) used as a
# recognizable applicant-value sentinel for the PII-perimeter assertions.
_SENTINEL_RAW = 7.7654321


class _ReportCase(_AuditorCase):
    def _crs_audit_dir(self, v) -> Path:
        return v.root / "output" / "crs-audit"


class TestRunAuditWrites(_ReportCase):
    def test_writes_two_files_and_returns_pair(self) -> None:
        v = self._seed_vault(self._all(7.5))
        try:
            report, envelope = audit_report.run_audit(
                v, "core.language.first", self.db, _language_registry())
            run_id = envelope.run_id
            crs_dir = self._crs_audit_dir(v)
            self.assertTrue((crs_dir / f"{run_id}.json").is_file())
            self.assertTrue((crs_dir / f"{run_id}.md").is_file())
            self.assertIsInstance(envelope, PublicAuditEnvelope)
            self.assertEqual(report.factor_cards[0].verdict, "SUBSTANTIATED")
        finally:
            v.con.close()

    def test_persists_complete_run_and_verdict_row(self) -> None:
        v = self._seed_vault(self._all(7.5))
        try:
            _, envelope = audit_report.run_audit(
                v, "core.language.first", self.db, _language_registry())
            run = vault.load_audit_run(v, envelope.run_id)
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "complete")
            self.assertEqual(run["factor_id"], "core.language.first")
            self.assertTrue(run["report_relpath"].startswith("candidates/"))
            verdicts = vault.list_factor_verdicts(v, envelope.run_id)
            self.assertEqual(len(verdicts), 1)
            self.assertEqual(verdicts[0]["verdict"], "SUBSTANTIATED")
        finally:
            v.con.close()

    def test_envelope_path_is_relative_and_pii_free(self) -> None:
        scores = self._all(7.5)
        scores["reading"] = _SENTINEL_RAW
        v = self._seed_vault(scores)
        try:
            _, envelope = audit_report.run_audit(
                v, "core.language.first", self.db, _language_registry())
            # vault-RELATIVE, never absolute.
            self.assertFalse(envelope.private_output_path.startswith("/"))
            self.assertTrue(envelope.private_output_path.startswith(
                "output/crs-audit/"))
            self.assertNotIn(v.candidate_id, envelope.private_output_path)
            serialized = json.dumps(envelope.model_dump())
            self.assertNotIn("ev_", serialized)
            self.assertNotIn(str(_SENTINEL_RAW), serialized)
            # claims carry only corpus citation ids.
            for claim in envelope.claims:
                self.assertFalse(claim.citation_id.startswith("ev_"))
        finally:
            v.con.close()

    def test_json_report_carries_applicant_value_and_ev(self) -> None:
        scores = self._all(7.5)
        scores["reading"] = _SENTINEL_RAW
        v = self._seed_vault(scores)
        try:
            report, envelope = audit_report.run_audit(
                v, "core.language.first", self.db, _language_registry())
            json_text = (self._crs_audit_dir(v) / f"{envelope.run_id}.json"
                         ).read_text(encoding="utf-8")
            md_text = (self._crs_audit_dir(v) / f"{envelope.run_id}.md"
                       ).read_text(encoding="utf-8")
            # The on-disk vault report DOES carry the sentinel + ev_ id.
            self.assertIn(str(_SENTINEL_RAW), json_text)
            self.assertTrue(report.factor_cards[0].evidence_ids)
            ev_id = report.factor_cards[0].evidence_ids[0]
            self.assertTrue(ev_id.startswith("ev_"))
            self.assertIn(ev_id, json_text)
            self.assertIn(ev_id, md_text)
            # The public envelope carries NEITHER.
            env_serialized = json.dumps(envelope.model_dump())
            self.assertNotIn(ev_id, env_serialized)
            self.assertNotIn(str(_SENTINEL_RAW), env_serialized)
        finally:
            v.con.close()

    def test_na_run_writes_valid_report(self) -> None:
        v = self._seed_vault(self._all(7.5), with_factor=False)
        try:
            report, envelope = audit_report.run_audit(
                v, "core.language.first", self.db, _language_registry())
            self.assertEqual(report.factor_cards[0].verdict, "N/A")
            self.assertTrue(
                (self._crs_audit_dir(v) / f"{envelope.run_id}.json").is_file())
            run = vault.load_audit_run(v, envelope.run_id)
            self.assertEqual(run["status"], "complete")
        finally:
            v.con.close()


class TestRunAuditFailClosed(_ReportCase):
    def test_grounding_failure_writes_nothing(self) -> None:
        bad = _language_registry(points_quote="absolutely not a substring zzz")
        v = self._seed_vault(self._all(7.5))
        try:
            with self.assertRaises(auditor.AuditGroundingError):
                audit_report.run_audit(v, "core.language.first", self.db, bad)
            # ZERO artifacts: no report file, no persisted rows.
            crs_dir = self._crs_audit_dir(v)
            written = list(crs_dir.glob("*")) if crs_dir.exists() else []
            self.assertEqual(written, [])
            self.assertEqual(
                v.con.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)
            self.assertIsNone(vault.load_audit_run(v, "aud_never_minted"))
        finally:
            v.con.close()

    def test_registry_fingerprint_mismatch_writes_nothing(self) -> None:
        registry = _language_registry()
        v = self._seed_vault(self._all(7.5))
        try:
            with self.assertRaisesRegex(
                    auditor.AuditGroundingError,
                    "^supplied registry fingerprint does not match registry$"):
                audit_report.run_audit(
                    v,
                    "core.language.first",
                    self.db,
                    registry,
                    registry_fingerprint="0" * 64,
                )
            crs_dir = self._crs_audit_dir(v)
            self.assertEqual(
                list(crs_dir.glob("*")) if crs_dir.exists() else [], [])
            self.assertEqual(
                v.con.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)
        finally:
            v.con.close()

    def test_invalid_explicit_round_refuses_before_factor_or_staging(self) -> None:
        v = self._seed_vault(self._all(7.5))
        try:
            with (
                mock.patch(
                    "crawler.auditor._audit_factor_verified") as audit_factor,
                mock.patch("crawler.audit_report._stage_text") as stage_report,
                self.assertRaisesRegex(
                    auditor.AuditGroundingError,
                    "^ITA round is unavailable for candidate$",
                ),
            ):
                audit_report.run_audit(
                    v,
                    "core.language.first",
                    self.db,
                    _language_registry(),
                    ita_round_id="ita_missing_explicit",
                )
            audit_factor.assert_not_called()
            stage_report.assert_not_called()
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)
        finally:
            v.con.close()

    def test_grounded_gap_writes_report_without_raising(self) -> None:
        v = self._seed_vault(self._all(6.5))  # below-threshold -> grounded GAP
        try:
            report, envelope = audit_report.run_audit(
                v, "core.language.first", self.db, _language_registry())
            self.assertEqual(report.factor_cards[0].verdict, "GAP")
            self.assertTrue(
                (self._crs_audit_dir(v) / f"{envelope.run_id}.json").is_file())
            self.assertEqual(len(vault.list_factor_verdicts(v, envelope.run_id)), 1)
        finally:
            v.con.close()


class TestRunAuditAtomicPersistence(_ReportCase):
    def test_directory_fsync_opens_syncs_and_closes_directory(self) -> None:
        directory = Path(self._tmp.name)
        with (
            mock.patch("crawler.paths.os.open", return_value=73) as opened,
            mock.patch("crawler.paths.os.fsync") as fsync,
            mock.patch("crawler.paths.os.close") as close,
        ):
            paths.fsync_dir(directory)
        opened.assert_called_once_with(
            directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        fsync.assert_called_once_with(73)
        close.assert_called_once_with(73)

    def test_unsupported_directory_fsync_fails_with_stable_marker(self) -> None:
        with (
            mock.patch("crawler.paths.os.open", return_value=73),
            mock.patch(
                "crawler.paths.os.fsync",
                side_effect=OSError(errno.EINVAL, f"{self._tmp.name}/private"),
            ),
            mock.patch("crawler.paths.os.close") as close,
            self.assertRaisesRegex(
                OSError, "^\\[Errno 5\\] directory durability unavailable$",
            ) as caught,
        ):
            paths.fsync_dir(Path(self._tmp.name))
        self.assertNotIn(self._tmp.name, str(caught.exception))
        close.assert_called_once_with(73)

    def test_new_report_directories_sync_each_parent(self) -> None:
        root = Path(self._tmp.name) / "durable-root"
        target = root / "output" / "crs-audit"
        synced: list[Path] = []
        with mock.patch(
                "crawler.paths.fsync_dir",
                side_effect=lambda path: synced.append(path)):
            paths.mkdir_durable(target)
        self.assertEqual(synced, [root.parent, root, root / "output"])
        self.assertTrue(target.is_dir())

    def test_both_report_replacements_and_directory_sync_precede_commit(
            self) -> None:
        v = self._seed_vault(self._all(7.5))
        events: list[tuple[str, Path | None]] = []
        real_replace = audit_report.os.replace
        real_commit = audit_report._commit_transaction

        def replace(source, destination):
            events.append(("replace", Path(destination)))
            return real_replace(source, destination)

        def fsync_dir(directory):
            events.append(("fsync_dir", directory))

        def commit(vault_):
            events.append(("commit", None))
            return real_commit(vault_)

        try:
            with (
                mock.patch(
                    "crawler.audit_report.os.replace", side_effect=replace),
                mock.patch(
                    "crawler.paths.fsync_dir", side_effect=fsync_dir),
                mock.patch(
                    "crawler.audit_report._commit_transaction",
                    side_effect=commit),
            ):
                _, envelope = audit_report.run_audit(
                    v, "core.language.first", self.db, _language_registry())

            out_dir = self._crs_audit_dir(v)
            final_replacements = [
                (kind, path) for kind, path in events
                if kind == "replace" and path is not None
                and path.parent == out_dir
                and path.name in {
                    f"{envelope.run_id}.json", f"{envelope.run_id}.md"}
            ]
            self.assertEqual(
                [path.suffix for _, path in final_replacements], [".json", ".md"])
            json_index = events.index(final_replacements[0])
            md_index = events.index(final_replacements[1])
            precommit_sync = events.index(("fsync_dir", out_dir), md_index + 1)
            commit_index = events.index(("commit", None))
            self.assertLess(json_index, md_index)
            self.assertLess(md_index, precommit_sync)
            self.assertLess(precommit_sync, commit_index)
        finally:
            v.con.close()

    def test_rejects_caller_transaction_without_altering_it(self) -> None:
        v = self._seed_vault(self._all(7.5))
        try:
            v.con.execute(
                "UPDATE candidates SET label = ? WHERE candidate_id = ?",
                ("caller-uncommitted", v.candidate_id),
            )
            self.assertTrue(v.con.in_transaction)

            with self.assertRaisesRegex(
                    audit_report.AuditPersistenceError,
                    "^audit report persistence failed$"):
                audit_report.run_audit(
                    v, "core.language.first", self.db, _language_registry())

            self.assertTrue(v.con.in_transaction)
            self.assertEqual(
                v.con.execute(
                    "SELECT label FROM candidates WHERE candidate_id = ?",
                    (v.candidate_id,),
                ).fetchone()[0],
                "caller-uncommitted",
            )
            crs_dir = self._crs_audit_dir(v)
            self.assertEqual(
                list(crs_dir.iterdir()) if crs_dir.exists() else [], [])
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)

            v.con.rollback()
            self.assertFalse(v.con.in_transaction)
            self.assertNotEqual(
                v.con.execute(
                    "SELECT label FROM candidates WHERE candidate_id = ?",
                    (v.candidate_id,),
                ).fetchone()[0],
                "caller-uncommitted",
            )
        finally:
            v.con.close()

    def _assert_failed_run_preserves_prior(
            self, patcher, *,
            expected=audit_report.AuditPersistenceError) -> None:
        v = self._seed_vault(self._all(7.5))
        try:
            _, prior_envelope = audit_report.run_audit(
                v, "core.language.first", self.db, _language_registry())
            crs_dir = self._crs_audit_dir(v)
            prior_files = {
                path.name: path.read_bytes() for path in crs_dir.iterdir()
            }
            prior_runs = v.con.execute(
                "SELECT COUNT(*) FROM audit_runs").fetchone()[0]
            prior_verdicts = v.con.execute(
                "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0]

            with patcher:
                with self.assertRaises(expected) as caught:
                    audit_report.run_audit(
                        v,
                        "core.language.first",
                        self.db,
                        _language_registry(),
                    )

            if expected is audit_report.AuditPersistenceError:
                self.assertEqual(
                    str(caught.exception), "audit report persistence failed")
                self.assertNotIn(self._tmp.name, str(caught.exception))
            self.assertFalse(v.con.in_transaction)
            self.assertEqual(
                {
                    path.name: path.read_bytes() for path in crs_dir.iterdir()
                },
                prior_files,
            )
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM audit_runs").fetchone()[0],
                prior_runs,
            )
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0],
                prior_verdicts,
            )
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM audit_runs "
                    "WHERE status != 'complete'"
                ).fetchone()[0],
                0,
            )
            self.assertIsNotNone(
                vault.load_audit_run(v, prior_envelope.run_id))
        finally:
            v.con.close()

    def test_json_stage_failure_is_all_or_nothing(self) -> None:
        real_stage = audit_report._stage_text

        def fail_json(path, text):
            if path.suffix == ".json":
                raise OSError("synthetic JSON write failure")
            return real_stage(path, text)

        self._assert_failed_run_preserves_prior(mock.patch(
            "crawler.audit_report._stage_text", side_effect=fail_json))

    def test_output_directory_failure_is_path_free_and_all_or_nothing(self) -> None:
        self._assert_failed_run_preserves_prior(mock.patch(
            "crawler.paths.mkdir_durable",
            side_effect=OSError(
                f"private path {self._tmp.name}/candidates/default"),
        ))

    def test_runtime_file_failures_are_path_free_and_all_or_nothing(self) -> None:
        private_detail = f"private path {self._tmp.name}/candidates/default"
        seams = (
            ("mkdir", "crawler.paths.mkdir_durable"),
            ("stage", "crawler.audit_report._stage_text"),
            ("replace", "crawler.audit_report.os.replace"),
        )
        for label, target in seams:
            with self.subTest(seam=label):
                self._assert_failed_run_preserves_prior(mock.patch(
                    target, side_effect=RuntimeError(private_detail)))

    def test_mkstemp_failure_is_path_free_and_all_or_nothing(self) -> None:
        self._assert_failed_run_preserves_prior(mock.patch(
            "crawler.audit_report.tempfile.mkstemp",
            side_effect=OSError(
                f"private path {self._tmp.name}/candidates/default"),
        ))

    def test_markdown_stage_failure_is_all_or_nothing(self) -> None:
        real_stage = audit_report._stage_text

        def fail_markdown(path, text):
            if path.suffix == ".md":
                raise OSError("synthetic Markdown write failure")
            return real_stage(path, text)

        self._assert_failed_run_preserves_prior(mock.patch(
            "crawler.audit_report._stage_text", side_effect=fail_markdown))

    def test_second_replace_failure_removes_first_publish(self) -> None:
        real_replace = audit_report.os.replace
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic second replace failure")
            return real_replace(source, destination)

        self._assert_failed_run_preserves_prior(mock.patch(
            "crawler.audit_report.os.replace", side_effect=fail_second))

    def test_stage_cleanup_failure_never_replaces_stable_error(self) -> None:
        private_detail = f"{self._tmp.name}/ev_private"
        with (
            mock.patch(
                "crawler.audit_report.os.fdopen",
                side_effect=OSError(private_detail),
            ),
            mock.patch(
                "crawler.audit_report.Path.unlink",
                side_effect=OSError(private_detail),
            ),
        ):
            v = self._seed_vault(self._all(7.5))
            try:
                with self.assertRaisesRegex(
                        audit_report.AuditPersistenceError,
                        "^audit report persistence failed$") as caught:
                    audit_report.run_audit(
                        v, "core.language.first", self.db,
                        _language_registry())
                self.assertNotIn(private_detail, str(caught.exception))
                self.assertEqual(
                    v.con.execute(
                        "SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
                self.assertEqual(
                    v.con.execute(
                        "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)
            finally:
                v.con.close()

    def test_verdict_insert_failure_rolls_back_run(self) -> None:
        self._assert_failed_run_preserves_prior(mock.patch(
            "crawler.vault._insert_factor_verdict",
            side_effect=OSError("synthetic verdict insert failure"),
        ))

    def test_runtime_database_failures_roll_back_everything(self) -> None:
        private_detail = f"private path {self._tmp.name}/vault.sqlite"
        seams = (
            ("run", "crawler.vault._insert_audit_run"),
            ("verdict", "crawler.vault._insert_factor_verdict"),
            ("complete", "crawler.vault._complete_audit_run"),
            ("commit", "crawler.audit_report._commit_transaction"),
        )
        for label, target in seams:
            with self.subTest(seam=label):
                self._assert_failed_run_preserves_prior(mock.patch(
                    target, side_effect=RuntimeError(private_detail)))

    def test_sqlite_failure_rolls_back_run(self) -> None:
        self._assert_failed_run_preserves_prior(mock.patch(
            "crawler.vault._insert_factor_verdict",
            side_effect=vault.sqlite3.OperationalError(
                f"private path {self._tmp.name}/vault.sqlite"),
        ))

    def test_commit_failure_rolls_back_rows_and_published_files(self) -> None:
        self._assert_failed_run_preserves_prior(mock.patch(
            "crawler.audit_report._commit_transaction",
            side_effect=OSError("synthetic commit failure"),
        ))

    def test_report_directory_fsync_failure_restores_before_commit(self) -> None:
        v = self._seed_vault(self._all(7.5))
        run_id = vault.new_audit_run_id()
        crs_dir = self._crs_audit_dir(v)
        crs_dir.mkdir(parents=True, exist_ok=True)
        prior = {
            f"{run_id}.json": b"prior-json",
            f"{run_id}.md": b"prior-markdown",
        }
        for name, content in prior.items():
            (crs_dir / name).write_bytes(content)
        private_detail = f"{self._tmp.name}/ev_private"
        commit = mock.Mock()
        try:
            with (
                mock.patch(
                    "crawler.vault.new_audit_run_id", return_value=run_id),
                mock.patch(
                    "crawler.paths.fsync_dir",
                    side_effect=OSError(private_detail)),
                mock.patch(
                    "crawler.audit_report._commit_transaction", commit),
                self.assertRaisesRegex(
                    audit_report.AuditPersistenceError,
                    "^audit report persistence failed$",
                ) as caught,
            ):
                audit_report.run_audit(
                    v, "core.language.first", self.db, _language_registry())
            self.assertNotIn(private_detail, str(caught.exception))
            commit.assert_not_called()
            self.assertFalse(v.con.in_transaction)
            self.assertIsNone(vault.load_audit_run(v, run_id))
            self.assertEqual(
                {path.name: path.read_bytes() for path in crs_dir.iterdir()},
                prior,
            )
        finally:
            v.con.close()

    def _assert_post_commit_exception_preserves_complete_state(
            self, exception: BaseException) -> None:
        v = self._seed_vault(self._all(7.5))
        run_id = vault.new_audit_run_id()
        crs_dir = self._crs_audit_dir(v)
        crs_dir.mkdir(parents=True, exist_ok=True)
        old_bytes = b"old collision that must not be restored"
        for suffix in (".json", ".md"):
            (crs_dir / f"{run_id}{suffix}").write_bytes(old_bytes)
        real_commit = audit_report._commit_transaction

        def commit_then_raise(vault_):
            real_commit(vault_)
            raise exception

        try:
            with (
                mock.patch(
                    "crawler.vault.new_audit_run_id",
                    return_value=run_id,
                ),
                mock.patch(
                    "crawler.audit_report._commit_transaction",
                    side_effect=commit_then_raise,
                ),
            ):
                if isinstance(exception, Exception):
                    report, envelope = audit_report.run_audit(
                        v, "core.language.first", self.db,
                        _language_registry())
                    self.assertEqual(report.run_id, run_id)
                    self.assertEqual(envelope.run_id, run_id)
                else:
                    with self.assertRaises(type(exception)) as caught:
                        audit_report.run_audit(
                            v, "core.language.first", self.db,
                            _language_registry())
                    self.assertIs(caught.exception, exception)

            self.assertFalse(v.con.in_transaction)
            run = vault.load_audit_run(v, run_id)
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "complete")
            self.assertEqual(
                run["rule_registry_version"],
                crs_rules.registry_fingerprint(_language_registry()),
            )
            self.assertEqual(
                run["report_relpath"],
                f"candidates/default/output/crs-audit/{run_id}.json",
            )
            self.assertEqual(len(vault.list_factor_verdicts(v, run_id)), 1)
            for suffix in (".json", ".md"):
                path = crs_dir / f"{run_id}{suffix}"
                self.assertTrue(path.is_file())
                self.assertNotEqual(path.read_bytes(), old_bytes)
            self.assertEqual(list(crs_dir.glob("*.tmp")), [])
            self.assertEqual(list(crs_dir.glob("*.bak")), [])
            self.assertEqual(list(crs_dir.glob(".*.tmp")), [])
            self.assertEqual(list(crs_dir.glob(".*.bak")), [])
        finally:
            v.con.close()

    def test_runtime_error_after_real_commit_returns_durable_report(self) -> None:
        self._assert_post_commit_exception_preserves_complete_state(
            RuntimeError(f"{self._tmp.name}/ev_private"))

    def test_interrupt_after_real_commit_reraises_with_durable_report(self) -> None:
        self._assert_post_commit_exception_preserves_complete_state(
            KeyboardInterrupt(f"{self._tmp.name}/ev_private"))

    def test_ambiguous_post_commit_query_fails_closed_without_deleting(self) -> None:
        v = self._seed_vault(self._all(7.5))
        real_con = v.con
        run_id = vault.new_audit_run_id()
        crs_dir = self._crs_audit_dir(v)
        crs_dir.mkdir(parents=True, exist_ok=True)
        old_bytes = b"old collision retained for ambiguous recovery"
        for suffix in (".json", ".md"):
            (crs_dir / f"{run_id}{suffix}").write_bytes(old_bytes)

        private_path = self._tmp.name

        class QueryFailingConnection:
            @property
            def in_transaction(self):
                return real_con.in_transaction

            def execute(self, sql, parameters=()):
                if sql.startswith(
                        "SELECT status, rule_registry_version, report_relpath"):
                    raise RuntimeError(f"{private_path}/vault.sqlite")
                return real_con.execute(sql, parameters)

            def commit(self):
                return real_con.commit()

            def rollback(self):
                return real_con.rollback()

            def close(self):
                return real_con.close()

        v.con = QueryFailingConnection()

        def commit_then_raise(vault_):
            vault_.con.commit()
            raise RuntimeError(f"{private_path}/after-commit")

        try:
            with (
                mock.patch(
                    "crawler.vault.new_audit_run_id",
                    return_value=run_id,
                ),
                mock.patch(
                    "crawler.audit_report._commit_transaction",
                    side_effect=commit_then_raise,
                ),
                self.assertRaisesRegex(
                    audit_report.AuditPersistenceError,
                    "^audit report persistence failed$",
                ),
            ):
                audit_report.run_audit(
                    v, "core.language.first", self.db, _language_registry())

            row = real_con.execute(
                "SELECT status FROM audit_runs WHERE audit_run_id = ?",
                (run_id,),
            ).fetchone()
            self.assertEqual(row[0], "complete")
            for suffix in (".json", ".md"):
                path = crs_dir / f"{run_id}{suffix}"
                self.assertTrue(path.is_file())
                self.assertNotEqual(path.read_bytes(), old_bytes)
            backups = list(crs_dir.glob(".*.bak"))
            self.assertEqual(len(backups), 2)
            self.assertEqual({path.read_bytes() for path in backups}, {old_bytes})
        finally:
            real_con.close()

    def test_failed_commit_restores_colliding_reports(self) -> None:
        v = self._seed_vault(self._all(7.5))
        run_id = vault.new_audit_run_id()
        crs_dir = self._crs_audit_dir(v)
        crs_dir.mkdir(parents=True, exist_ok=True)
        prior = {
            f"{run_id}.json": b"prior-json",
            f"{run_id}.md": b"prior-markdown",
        }
        for name, content in prior.items():
            (crs_dir / name).write_bytes(content)
        try:
            with (
                mock.patch(
                    "crawler.vault.new_audit_run_id",
                    return_value=run_id,
                ),
                mock.patch(
                    "crawler.audit_report._commit_transaction",
                    side_effect=OSError("commit did not complete"),
                ),
                self.assertRaises(audit_report.AuditPersistenceError),
            ):
                audit_report.run_audit(
                    v, "core.language.first", self.db, _language_registry())
            self.assertFalse(v.con.in_transaction)
            self.assertIsNone(vault.load_audit_run(v, run_id))
            self.assertEqual(
                {path.name: path.read_bytes() for path in crs_dir.iterdir()},
                prior,
            )
        finally:
            v.con.close()

    def test_interrupt_cleanup_reraises_original_base_exception(self) -> None:
        self._assert_failed_run_preserves_prior(
            mock.patch(
                "crawler.audit_report._commit_transaction",
                side_effect=KeyboardInterrupt(),
            ),
            expected=KeyboardInterrupt,
        )


if __name__ == "__main__":  # pragma: no cover
    import unittest
    unittest.main()
