"""CLI perimeter tests for the private Canadian-study review sidecar."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import contract, index_health, study_review, vault
from crawler.tests.fixtures.extraction import make_fixtures as mf


_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _ROOT / "corpus" / "index.db"
_DLI = "O19332746152"
_INSTITUTION = "University of Toronto"
_AS_OF = "2026-07-16T18:08:26Z"
_FIVE_KEYS = {"schema_version", "ok", "command", "result", "error"}
_STUDY_TEXT = "\n".join([
    "Synthetic Proof of Canadian Studies",
    f"Institution Name: {_INSTITUTION}",
    f"DLI Number: {_DLI}",
    "Credential Level: Bachelor's degree",
    "Program Start: 15 September 2022",
    "Program End: 30 April 2026",
    "Study Status: Graduated",
])


class _CliCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.personal = Path(self._tmp.name) / "personal"
        self._env = mock.patch.dict(
            os.environ,
            {"PR_PERSONAL_DIR": str(self.personal)},
            clear=False,
        )
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        from crawler import cli

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = cli.main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()

    def _envelope(self, raw: str) -> dict:
        env = json.loads(raw)
        self.assertEqual(set(env), _FIVE_KEYS)
        self.assertEqual(env["schema_version"], "1.0")
        self.assertEqual(env["command"], "vault")
        return env

    def _candidate_root(self, candidate: str = "study-cli") -> Path:
        return self.personal / "candidates" / candidate


class TestStudyReviewBoundary(_CliCase):
    """Resolver-first ordering and closed-envelope tests use strict spies."""

    def test_recovery_marker_is_fatal_before_configuration_refusal(self) -> None:
        report_dir = (
            self._candidate_root() / "output" / "study-review"
        )
        report_dir.mkdir(parents=True)
        (report_dir / study_review._RECOVERY_MARKER_NAME).write_text(
            '{"state":"restore_required"}',
            encoding="ascii",
        )

        with mock.patch(
            "crawler.vault.open_vault",
            side_effect=AssertionError("vault must not be opened"),
        ) as opened:
            rc, out, err = self._run([
                "--json",
                "vault",
                "study-review",
                "--candidate",
                "study-cli",
                "--db",
                "fixture.db",
            ])

        self.assertEqual(rc, contract.EXIT_INTERNAL_ERROR)
        self.assertEqual(err, "")
        envelope = self._envelope(out)
        self.assertFalse(envelope["ok"])
        self.assertIsNone(envelope["result"])
        self.assertEqual(
            envelope["error"],
            {
                "type": contract.INTERNAL_ERROR,
                "message": "study report recovery failed",
            },
        )
        opened.assert_not_called()

    def test_positive_explicit_override_wins_environment_and_reaches_both_calls(
            self) -> None:
        from crawler import cli, snapshot_policy

        events: list[object] = []
        real_resolver = snapshot_policy.dli_snapshot_max_age_days

        class _Connection:
            def close(self) -> None:
                events.append("close")

        fake_vault = mock.Mock(con=_Connection(), candidate_id="study-cli")

        def resolve(value):
            events.append(("resolve", value))
            return real_resolver(value)

        def index(_args, db):
            events.append(("index", db))
            return None

        def snapshot(_args, db, family, age):
            events.append(("snapshot", db, family, age))
            return None

        def open_vault(candidate):
            events.append(("open", candidate))
            return fake_vault

        def review(v, db, *, candidate_id, max_age_days):
            events.append(("review", v, db, candidate_id, max_age_days))
            return {
                "status": "AT-RISK",
                "reason": "designation_historical_unproven",
                "required_count": 5,
                "confirmed_count": 6,
                "eligible_count": 6,
                "as_of": _AS_OF,
            }

        with mock.patch.dict(
                os.environ, {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "999"}), \
                mock.patch.object(
                    snapshot_policy, "dli_snapshot_max_age_days",
                    side_effect=resolve) as resolver, \
                mock.patch.object(cli, "_require_readable_index",
                                  side_effect=index), \
                mock.patch.object(cli, "_require_readable_snapshot",
                                  side_effect=snapshot), \
                mock.patch("crawler.vault.open_vault",
                           side_effect=open_vault), \
                mock.patch("crawler.study_review.review_study",
                           side_effect=review):
            rc, out, err = self._run([
                "--json", "vault", "study-review",
                "--candidate", "study-cli",
                "--db", "fixture.db",
                "--snapshot-max-age-days", "17",
            ])

        self.assertEqual(rc, 0, err)
        resolver.assert_called_once_with("17")
        self.assertEqual(
            [event[0] if isinstance(event, tuple) else event for event in events],
            ["resolve", "index", "snapshot", "open", "review", "close"],
        )
        self.assertEqual(events[2], ("snapshot", "fixture.db", "dli", 17))
        self.assertEqual(events[4][-1], 17)
        env = self._envelope(out)
        self.assertTrue(env["ok"])
        self.assertEqual(set(env["result"]), set(study_review.PUBLIC_FIELDS))

    def test_invalid_config_matrix_refuses_before_probe_open_or_write(self) -> None:
        cases = (
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
        for label, explicit, env_value in cases:
            with self.subTest(label=label):
                argv = [
                    "--json", "vault", "study-review",
                    "--candidate", "study-cli", "--db", "missing.db",
                ]
                if explicit is not None:
                    argv += ["--snapshot-max-age-days", explicit]
                env = {}
                if env_value is not None:
                    env["PR_DLI_SNAPSHOT_MAX_AGE_DAYS"] = env_value
                with mock.patch.dict(
                        os.environ, env, clear=True), \
                        mock.patch(
                            "crawler.index_health.probe_index") as index_probe, \
                        mock.patch(
                            "crawler.index_health.probe_snapshot") as snap_probe, \
                        mock.patch("crawler.vault.open_vault") as opener, \
                        mock.patch(
                            "crawler.study_review.review_study") as review:
                    rc, out, _ = self._run(argv)
                self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
                env_out = self._envelope(out)
                self.assertFalse(env_out["ok"])
                self.assertIsNone(env_out["result"])
                self.assertEqual(
                    env_out["error"]["type"], contract.INVALID_INPUT)
                self.assertNotIn("as_of", out)
                index_probe.assert_not_called()
                snap_probe.assert_not_called()
                opener.assert_not_called()
                review.assert_not_called()
                self.assertFalse(self._candidate_root().exists())

    def test_index_refusal_precedes_snapshot_and_open_for_every_class(self) -> None:
        statuses = (
            index_health.INDEX_MISSING,
            index_health.INDEX_EMPTY,
            index_health.INDEX_UNREADABLE,
            index_health.INDEX_CORRUPT,
            index_health.INDEX_DRIFTED,
        )
        for status in statuses:
            with self.subTest(status=status), \
                    mock.patch.dict(
                        os.environ,
                        {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "30"}), \
                    mock.patch(
                        "crawler.index_health.probe_index",
                        return_value=index_health.IndexHealth(status, status),
                    ) as index_probe, \
                    mock.patch(
                        "crawler.index_health.probe_snapshot") as snap_probe, \
                    mock.patch("crawler.vault.open_vault") as opener:
                rc, out, _ = self._run([
                    "--json", "vault", "study-review",
                    "--candidate", "study-cli", "--db", "fixture.db",
                ])
            self.assertEqual(rc, 2)
            env = self._envelope(out)
            self.assertFalse(env["ok"])
            self.assertIsNone(env["result"])
            self.assertIn(f"reason={status}", env["error"]["message"])
            index_probe.assert_called_once_with("fixture.db")
            snap_probe.assert_not_called()
            opener.assert_not_called()
            self.assertFalse(self._candidate_root().exists())

    def test_snapshot_refusal_precedes_open_for_every_class(self) -> None:
        statuses = (
            index_health.SNAPSHOT_MISSING,
            index_health.SNAPSHOT_EMPTY,
            index_health.SNAPSHOT_UNREADABLE,
            index_health.SNAPSHOT_CORRUPT,
            index_health.SNAPSHOT_DRIFTED,
            index_health.SNAPSHOT_STALE,
        )
        healthy = index_health.IndexHealth(index_health.INDEX_OK, "ok")
        for status in statuses:
            with self.subTest(status=status), \
                    mock.patch.dict(
                        os.environ,
                        {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "30"}), \
                    mock.patch(
                        "crawler.index_health.probe_index",
                        return_value=healthy), \
                    mock.patch(
                        "crawler.index_health.probe_snapshot",
                        return_value=index_health.SnapshotHealth(status, status),
                    ) as snap_probe, \
                    mock.patch("crawler.vault.open_vault") as opener:
                rc, out, _ = self._run([
                    "--json", "vault", "study-review",
                    "--candidate", "study-cli", "--db", "fixture.db",
                ])
            self.assertEqual(rc, 2)
            env = self._envelope(out)
            self.assertFalse(env["ok"])
            self.assertIsNone(env["result"])
            self.assertIn(f"reason={status}", env["error"]["message"])
            snap_probe.assert_called_once()
            self.assertEqual(snap_probe.call_args.kwargs["max_age_days"], 30)
            opener.assert_not_called()
            self.assertFalse(self._candidate_root().exists())

    def test_human_mode_keeps_stdout_empty_and_reports_only_safe_summary(self) -> None:
        result = study_review._pack(
            "AT-RISK", "designation_historical_unproven",
            confirmed_count=6, eligible_count=6, as_of=_AS_OF,
            report_created=True)
        fake_vault = mock.Mock()
        with mock.patch.dict(
                os.environ, {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "30"}), \
                mock.patch(
                    "crawler.index_health.probe_index",
                    return_value=index_health.IndexHealth("ok", "ok")), \
                mock.patch(
                    "crawler.index_health.probe_snapshot",
                    return_value=index_health.SnapshotHealth("ok", "ok")), \
                mock.patch("crawler.vault.open_vault",
                           return_value=fake_vault), \
                mock.patch("crawler.study_review.review_study",
                           return_value=result):
            rc, out, err = self._run([
                "vault", "study-review", "--candidate", "study-cli",
                "--db", "fixture.db",
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertIn("AT-RISK", err)
        self.assertIn("designation_historical_unproven", err)
        self.assertIn("6/5", err)
        self.assertIn("output/study-review/latest.json", err)
        for forbidden in (_DLI, _INSTITUTION, "ev_", str(self.personal)):
            self.assertNotIn(forbidden, err)

    def test_human_mode_does_not_advertise_report_on_refusal(self) -> None:
        result = study_review._pack(
            "AT-RISK", "snapshot_provenance_mismatch",
            confirmed_count=6, eligible_count=6)
        fake_vault = mock.Mock()
        with mock.patch.dict(
                os.environ, {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "30"}), \
                mock.patch(
                    "crawler.index_health.probe_index",
                    return_value=index_health.IndexHealth("ok", "ok")), \
                mock.patch(
                    "crawler.index_health.probe_snapshot",
                    return_value=index_health.SnapshotHealth("ok", "ok")), \
                mock.patch("crawler.vault.open_vault",
                           return_value=fake_vault), \
                mock.patch("crawler.study_review.review_study",
                           return_value=result):
            rc, out, err = self._run([
                "vault", "study-review", "--candidate", "study-cli",
                "--db", "fixture.db",
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertNotIn("output/study-review/latest.json", err)

    def test_human_mode_does_not_advertise_report_on_persistence_failure(
            self) -> None:
        result = study_review._pack(
            "AT-RISK", "report_write_failed",
            confirmed_count=6, eligible_count=6)
        fake_vault = mock.Mock()
        with mock.patch.dict(
                os.environ, {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "30"}), \
                mock.patch(
                    "crawler.index_health.probe_index",
                    return_value=index_health.IndexHealth("ok", "ok")), \
                mock.patch(
                    "crawler.index_health.probe_snapshot",
                    return_value=index_health.SnapshotHealth("ok", "ok")), \
                mock.patch("crawler.vault.open_vault",
                           return_value=fake_vault), \
                mock.patch("crawler.study_review.review_study",
                           return_value=result):
            rc, out, err = self._run([
                "vault", "study-review", "--candidate", "study-cli",
                "--db", "fixture.db",
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertIn("report_write_failed", err)
        self.assertNotIn("output/study-review/latest.json", err)

    def test_fatal_recovery_failure_is_path_free_and_has_no_success_result(
            self) -> None:
        fake_vault = mock.Mock()
        private_detail = f"{self.personal}/private/restore"
        with mock.patch.dict(
                os.environ, {"PR_DLI_SNAPSHOT_MAX_AGE_DAYS": "30"}), \
                mock.patch(
                    "crawler.index_health.probe_index",
                    return_value=index_health.IndexHealth("ok", "ok")), \
                mock.patch(
                    "crawler.index_health.probe_snapshot",
                    return_value=index_health.SnapshotHealth("ok", "ok")), \
                mock.patch("crawler.vault.open_vault",
                           return_value=fake_vault), \
                mock.patch(
                    "crawler.study_review.review_study",
                    side_effect=study_review.StudyReportRecoveryError(
                        private_detail),
                ):
            rc, out, err = self._run([
                "--json", "vault", "study-review", "--candidate", "study-cli",
                "--db", "fixture.db",
            ])

        self.assertEqual(rc, contract.EXIT_INTERNAL_ERROR)
        self.assertEqual(err, "")
        envelope = self._envelope(out)
        self.assertFalse(envelope["ok"])
        self.assertIsNone(envelope["result"])
        self.assertEqual(
            envelope["error"],
            {
                "type": contract.INTERNAL_ERROR,
                "message": "study report recovery failed",
            },
        )
        self.assertNotIn(private_detail, out)
        self.assertNotIn("output/study-review/latest.json", out)
        fake_vault.con.close.assert_called_once_with()


@unittest.skipUnless(
    _REAL_DB.is_file(),
    "LOCAL-ONLY: real DLI-bearing corpus index is required",
)
class TestStudyReviewCliEndToEnd(_CliCase):
    def _fields(self, candidate: str) -> list[dict]:
        rc, out, err = self._run([
            "--json", "vault", "fields", "--candidate", candidate,
        ])
        self.assertEqual(rc, 0, err)
        return self._envelope(out)["result"]["fields"]

    def test_import_extract_confirm_review_is_private_exact_and_idempotent(
            self) -> None:
        candidate = "study-cli"
        source = Path(self._tmp.name) / "private-study.pdf"
        source.write_bytes(mf.build_pdf([_STUDY_TEXT]))

        rc, out, err = self._run([
            "--json", "vault", "import", str(source),
            "--doc-type", "study_proof", "--candidate", candidate,
        ])
        self.assertEqual(rc, 0, err)
        document_id = self._envelope(out)["result"]["document_id"]

        rc, out, err = self._run([
            "--json", "vault", "extract", "--candidate", candidate,
            "--document-id", document_id,
        ])
        self.assertEqual(rc, 0, err)
        self.assertEqual(self._envelope(out)["result"]["values_pending"], 6)
        fields = self._fields(candidate)
        self.assertEqual({item["confirmation_status"] for item in fields},
                         {"pending"})

        for item in fields:
            argv = [
                "--json", "vault", "confirm", "--candidate", candidate,
                "--value-id", item["value_id"],
            ]
            if item["field_name"] == "institution_name":
                argv += ["--decision", "correct",
                         "--corrected-value", json.dumps(_INSTITUTION)]
            else:
                argv += ["--decision", "confirm"]
            rc, _out, err = self._run(argv)
            self.assertEqual(rc, 0, err)

        review_argv = [
            "--json", "vault", "study-review", "--candidate", candidate,
            "--db", str(_REAL_DB), "--snapshot-max-age-days", "30",
        ]
        rc, first, err = self._run(review_argv)
        self.assertEqual(rc, 0, err)
        env = self._envelope(first)
        self.assertTrue(env["ok"])
        self.assertEqual(set(env["result"]), set(study_review.PUBLIC_FIELDS))
        self.assertEqual(env["result"]["as_of"], _AS_OF)
        self.assertEqual(env["result"]["status"], "AT-RISK")
        self.assertEqual(
            env["result"]["reason"], "designation_historical_unproven")

        report_path = (
            self._candidate_root(candidate)
            / "output" / "study-review" / "latest.json"
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["as_of"], _AS_OF)
        self.assertIn("not legal advice", report["notice"].lower())
        self.assertEqual(
            [entry["chunk_id"] for entry in report["dynamic_citations"]],
            [f"dli/{_DLI}.md#000", f"dli/{_DLI}.md#001"],
        )
        self.assertTrue(all(
            set(entry) == {
                "rule_id", "kind", "chunk_id", "quote", "crawl_date",
                "observed_values",
            }
            for entry in report["dynamic_citations"]
        ))

        private_tokens = [
            _DLI,
            _INSTITUTION,
            "3+",
            "2022-09-15",
            "2026-04-30",
            "graduated",
            "ev_",
            f"dli/{_DLI}.md#000",
            "DLI number:",
            str(self._candidate_root(candidate)),
        ]
        for token in private_tokens:
            self.assertNotIn(token, first)

        before = report_path.read_bytes()
        rc, second, err = self._run(review_argv)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self._envelope(second)["result"], env["result"])
        self.assertEqual(report_path.read_bytes(), before)

        rc, out, err = self._run([
            "--json", "vault", "study-review", "--candidate", candidate,
            "--db", str(_REAL_DB), "--snapshot-max-age-days", "0",
        ])
        self.assertEqual(rc, 2)
        self.assertFalse(self._envelope(out)["ok"])
        self.assertEqual(report_path.read_bytes(), before)

        rc, out, err = self._run(review_argv)
        self.assertEqual(rc, 0, err)
        self.assertTrue(report_path.exists())
        before_correction = report_path.read_bytes()

        dli_value_id = next(
            item["value_id"] for item in fields
            if item["field_name"] == "dli_number")
        rc, out, err = self._run([
            "--json", "vault", "confirm", "--candidate", candidate,
            "--value-id", dli_value_id, "--decision", "correct",
            "--corrected-value", '{"dli":"O19332746152"}',
        ])
        self.assertEqual(rc, 0, err)
        self.assertTrue(self._envelope(out)["ok"])
        rc, out, err = self._run(review_argv)
        self.assertEqual(rc, 0, err)
        self.assertNotIn("Traceback", out + err)
        self.assertEqual(
            self._envelope(out)["result"]["reason"], "exact_dli_mismatch")
        self.assertEqual(report_path.read_bytes(), before_correction)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
