"""Offline tests for the additive `vault audit` CLI verb (Phase 32 — AUDIT-02/06).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Reuses the Plan 03
synthetic fixtures (``_AuditorCase`` + ``_language_registry``) and drives
``crawler.cli.main([...])`` with ``$PR_PERSONAL_DIR`` pointed at a throwaway
tempdir vault + a synthetic corpus index. The explicit ``RegistrySnapshot`` seam
binds confirmation and eligibility to the same SYNTHETIC registry so the whole
slice runs hermetically (no real corpus).

Every ``--json`` run must print EXACTLY ONE valid five-key envelope to stdout
(``command == "vault"``); human detail goes to stderr.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_vault_audit_cli.py -q
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from crawler import audit_report, cli, crs_rules, vault
from crawler.tests.test_auditor import _AuditorCase, _language_registry


class _AuditCliCase(_AuditorCase):
    """Reuse the synthetic index + vault seeding; add a main([...]) runner."""

    @staticmethod
    def _snapshot(registry):
        return crs_rules.RegistrySnapshot(
            registry=registry,
            fingerprint=crs_rules.registry_fingerprint(registry),
        )

    def _seed_vault(self, *args, **kwargs):
        # Confirmation and the later CLI audit must observe the same live
        # synthetic registry.  CR-04 intentionally treats changing this content
        # between those operations as staleness.
        registry = _language_registry()
        with mock.patch(
                "crawler.crs_rules.load_registry_snapshot",
                return_value=self._snapshot(registry)):
            return super()._seed_vault(*args, **kwargs)

    def _run(self, argv, registry):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch(
                "crawler.crs_rules.load_registry_snapshot",
                return_value=self._snapshot(registry)) as loader:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = cli.main(argv)
        self.assertEqual(loader.call_count, 1)
        return rc, out.getvalue(), err.getvalue()

    def _one_envelope(self, stdout: str) -> dict:
        data = json.loads(stdout)  # raises unless exactly one JSON object
        self.assertEqual(
            set(data.keys()),
            {"schema_version", "ok", "command", "result", "error"})
        self.assertEqual(data["command"], "vault")
        self.assertEqual(data["schema_version"], "1.0")
        return data


class TestVaultAuditOk(_AuditCliCase):
    def test_grounded_substantiated_is_ok_true_pii_light(self) -> None:
        v = self._seed_vault(self._all(7.5))
        v.con.close()
        rc, out, err = self._run(
            ["--json", "vault", "audit", "--candidate", "default",
             "--db", str(self.db)], _language_registry())
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertIsNone(env["error"])
        result = env["result"]
        self.assertEqual(set(result), {
            "run_id", "factor_id", "verdicts", "claims", "counts",
            "private_output_path"})
        self.assertEqual(result["factor_id"], "core.language.first")
        self.assertEqual(result["verdicts"][0]["verdict"], "SUBSTANTIATED")
        # PII-light stdout: no ev_ pointer, vault-relative path only.
        self.assertNotIn("ev_", out)
        self.assertTrue(result["private_output_path"].startswith(
            "output/crs-audit/"))

    def test_below_threshold_is_ok_true_gap(self) -> None:
        v = self._seed_vault(self._all(6.5))
        v.con.close()
        rc, out, _ = self._run(
            ["--json", "vault", "audit", "--candidate", "default",
             "--db", str(self.db)], _language_registry())
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["verdicts"][0]["verdict"], "GAP")

    def test_not_claimed_is_ok_true_na(self) -> None:
        v = self._seed_vault(self._all(7.5), with_factor=False)
        v.con.close()
        rc, out, _ = self._run(
            ["--json", "vault", "audit", "--candidate", "default",
             "--db", str(self.db)], _language_registry())
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["verdicts"][0]["verdict"], "N/A")

    def test_human_detail_goes_to_stderr_not_stdout(self) -> None:
        v = self._seed_vault(self._all(7.5))
        v.con.close()
        rc, out, err = self._run(
            ["vault", "audit", "--candidate", "default", "--db", str(self.db)],
            _language_registry())
        self.assertEqual(rc, 0)
        # Non-json mode: stdout is empty, the factor detail is on stderr.
        self.assertEqual(out.strip(), "")
        self.assertIn("core.language.first", err)
        self.assertIn("SUBSTANTIATED", err)

    def test_live_registry_change_after_load_cannot_split_snapshot(self) -> None:
        original = _language_registry()
        changed = original.model_copy(deep=True)
        changed.rows[0].claim_text = "A changed but still grounded rule."
        snapshots = {
            False: self._snapshot(original),
            True: self._snapshot(changed),
        }
        v = self._seed_vault(self._all(7.5))
        v.con.close()
        state = {"changed": False}
        real_open = vault.open_vault

        def open_after_change(candidate_id):
            state["changed"] = True
            return real_open(candidate_id)

        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch(
                "crawler.crs_rules.load_registry_snapshot",
                side_effect=lambda: snapshots[state["changed"]]) as loader,
            mock.patch(
                "crawler.vault.open_vault",
                side_effect=open_after_change),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            rc = cli.main([
                "--json", "vault", "audit", "--candidate", "default",
                "--db", str(self.db),
            ])
        self.assertEqual(rc, 0, err.getvalue())
        self.assertEqual(loader.call_count, 1)
        env = self._one_envelope(out.getvalue())
        self.assertEqual(
            env["result"]["verdicts"][0]["verdict"], "SUBSTANTIATED")


class TestVaultAuditFailClosed(_AuditCliCase):
    def test_invalid_explicit_round_is_stable_grounding_error(self) -> None:
        v = self._seed_vault(self._all(7.5))
        private_path = str(v.root.resolve())
        v.con.close()
        rc, out, err = self._run(
            [
                "--json", "vault", "audit", "--all",
                "--candidate", "default", "--db", str(self.db),
                "--ita-round-id", "ita_missing_explicit",
            ],
            _language_registry(),
        )
        self.assertNotEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"], {
            "type": "invalid_input",
            "message": "ITA round is unavailable for candidate",
        })
        self.assertNotIn("persistence", out.lower())
        self.assertNotIn(private_path, out)
        self.assertEqual(err, "")
        crs_dir = v.root / "output" / "crs-audit"
        self.assertEqual(
            list(crs_dir.iterdir()) if crs_dir.exists() else [], [])

    def test_persistence_failure_is_stable_pii_free_internal_error(self) -> None:
        v = self._seed_vault(self._all(7.5))
        private_path = str(v.root.resolve())
        v.con.close()
        private_detail = f"{private_path}/ev_private"
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch(
                "crawler.crs_rules.load_registry_snapshot",
                return_value=self._snapshot(_language_registry())),
            mock.patch(
                "crawler.audit_report._commit_transaction",
                side_effect=RuntimeError(private_detail)),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            rc = cli.main([
                "--json", "vault", "audit", "--candidate", "default",
                "--db", str(self.db),
            ])
        self.assertNotEqual(rc, 0)
        env = self._one_envelope(out.getvalue())
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"], {
            "type": "internal_error",
            "message": "audit report persistence failed",
        })
        serialized = json.dumps(env)
        self.assertNotIn(private_path, serialized)
        self.assertNotIn(private_detail, serialized)
        self.assertNotIn("ev_", serialized)
        self.assertEqual(err.getvalue(), "")
        reopened = vault.open_vault("default")
        try:
            self.assertFalse(reopened.con.in_transaction)
            self.assertEqual(
                reopened.con.execute(
                    "SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
            self.assertEqual(
                reopened.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)
            crs_dir = reopened.root / "output" / "crs-audit"
            self.assertEqual(
                list(crs_dir.iterdir()) if crs_dir.exists() else [], [])
        finally:
            reopened.con.close()

    def test_post_commit_interrupt_propagates_without_private_json(self) -> None:
        v = self._seed_vault(self._all(7.5))
        private_path = str(v.root.resolve())
        v.con.close()
        private_detail = f"{private_path}/ev_interrupt"
        interrupt = KeyboardInterrupt(private_detail)
        out, err = io.StringIO(), io.StringIO()

        def commit_then_interrupt(vault_):
            vault_.con.commit()
            raise interrupt

        with (
            mock.patch(
                "crawler.crs_rules.load_registry_snapshot",
                return_value=self._snapshot(_language_registry())),
            mock.patch(
                "crawler.audit_report._commit_transaction",
                side_effect=commit_then_interrupt),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            self.assertRaises(KeyboardInterrupt) as caught,
        ):
            cli.main([
                "--json", "vault", "audit", "--candidate", "default",
                "--db", str(self.db),
            ])
        self.assertIs(caught.exception, interrupt)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn(private_path, out.getvalue())
        self.assertNotIn("ev_interrupt", out.getvalue())

        reopened = vault.open_vault("default")
        try:
            runs = reopened.con.execute(
                "SELECT audit_run_id, status FROM audit_runs").fetchall()
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["status"], "complete")
            self.assertEqual(
                len(vault.list_factor_verdicts(
                    reopened, runs[0]["audit_run_id"])),
                1,
            )
            crs_dir = reopened.root / "output" / "crs-audit"
            self.assertEqual(
                {path.suffix for path in crs_dir.iterdir()},
                {".json", ".md"},
            )
        finally:
            reopened.con.close()

    def test_grounding_failure_is_ok_false_nonzero_no_report(self) -> None:
        v = self._seed_vault(self._all(7.5))
        v.con.close()
        bad = _language_registry(points_quote="absolutely not a substring zzz")
        rc, out, _ = self._run(
            ["--json", "vault", "audit", "--candidate", "default",
             "--db", str(self.db)], bad)
        self.assertNotEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertFalse(env["ok"])
        self.assertIsNone(env["result"])
        self.assertIsNotNone(env["error"])
        self.assertEqual(env["error"]["type"], "invalid_input")
        # No report written on a grounding failure.
        crs_dir = v.root / "output" / "crs-audit"
        written = list(crs_dir.glob("*")) if crs_dir.exists() else []
        self.assertEqual(written, [])

    def test_registry_unavailable_refuses_before_vault_or_output(self) -> None:
        missing = Path(self._tmp.name) / "missing-registry"
        empty = Path(self._tmp.name) / "empty-registry"
        empty.mkdir()
        real_load = crs_rules.load_registry_snapshot
        for label, directory in (("missing", missing), ("empty", empty)):
            with self.subTest(case=label):
                out, err = io.StringIO(), io.StringIO()

                def load():
                    return real_load(directory)

                with (
                    mock.patch(
                        "crawler.crs_rules.load_registry_snapshot",
                        side_effect=load) as loader,
                    mock.patch("crawler.vault.open_vault") as open_vault,
                    contextlib.redirect_stdout(out),
                    contextlib.redirect_stderr(err),
                ):
                    rc = cli.main([
                        "--json", "vault", "audit", "--candidate", "default",
                        "--db", str(self.db),
                    ])
                self.assertNotEqual(rc, 0)
                self.assertEqual(loader.call_count, 1)
                open_vault.assert_not_called()
                env = self._one_envelope(out.getvalue())
                self.assertFalse(env["ok"])
                self.assertEqual(env["error"]["type"], "invalid_input")
                self.assertEqual(
                    env["error"]["message"], "CRS rule registry unavailable")
                self.assertNotIn(self._tmp.name, out.getvalue())
                self.assertFalse(
                    (Path(self._tmp.name) / "candidates" / "default").exists())

    def test_confirmation_under_another_snapshot_is_excluded(self) -> None:
        original = _language_registry()
        v = self._seed_vault(self._all(7.5))
        v.con.close()
        changed = original.model_copy(deep=True)
        changed.rows[0].claim_text = "A changed but still grounded rule."
        self.assertNotEqual(
            self._snapshot(original).fingerprint,
            self._snapshot(changed).fingerprint,
        )

        rc, out, _ = self._run(
            ["--json", "vault", "audit", "--candidate", "default",
             "--db", str(self.db)],
            changed,
        )
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertEqual(env["result"]["verdicts"][0]["verdict"], "GAP")
        self.assertEqual(
            env["result"]["verdicts"][0]["reason_code"], "missing_evidence")

    def test_full_grid_reuses_one_snapshot_fingerprint(self) -> None:
        registry = _language_registry()
        snapshot = self._snapshot(registry)
        v = self._seed_vault(self._all(7.5))
        vault.set_ita_round(
            v, "default", "full-grid", None, "EE", cutoff_score=None)
        v.con.close()
        seen: list[str | None] = []

        real_eligible = vault.audit_eligible_values

        def eligible(vault_, factor_id, *, registry_fingerprint=None):
            seen.append(registry_fingerprint)
            return real_eligible(
                vault_, factor_id,
                registry_fingerprint=registry_fingerprint)

        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch(
                "crawler.crs_rules.load_registry_snapshot",
                return_value=snapshot) as loader,
            mock.patch(
                "crawler.vault.audit_eligible_values",
                side_effect=eligible),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            rc = cli.main([
                "--json", "vault", "audit", "--all",
                "--candidate", "default", "--db", str(self.db),
            ])
        self.assertEqual(rc, 0, err.getvalue())
        self.assertEqual(loader.call_count, 1)
        self.assertTrue(seen)
        self.assertEqual(set(seen), {snapshot.fingerprint})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
