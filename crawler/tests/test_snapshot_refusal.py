"""CLI refusal + zero-artifact + PII-perimeter proof for the snapshot preflight (SAFE-10).

Drives ``cli._require_readable_snapshot`` DIRECTLY (Phase 40 ships no verb that calls it —
Assumption A5; the wiring verbs are Phase 44/45) against SYNTHETIC fixture snapshot families
built in a tempdir (NO dependency on ``corpus/dli/`` or the real corpus). Asserts:

  * a missing-family / drifted / stale snapshot yields ONE stable, PII-free refusal on the
    frozen ``invalid_input`` / exit-2 contract with a ``reason=snapshot_<code>`` token;
  * the preflight writes ZERO artifacts (no ``audit_runs`` row, no report file);
  * a healthy, fresh family returns ``None`` (permits downstream — SC4).

Stdlib ``unittest`` ONLY; the vault lives under a tempdir via ``PR_PERSONAL_DIR``.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from crawler import cli, contract, vault
from crawler.tests.test_snapshot_health import _build_snapshot_index


class SnapshotRefusal(unittest.TestCase):
    def setUp(self) -> None:
        # Corpus fixtures live in a DISTINCT tempdir from the vault so a refusal message
        # can never accidentally echo the vault/personal path.
        self._corpus_tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self._corpus_tmp.name)
        self._personal_tmp = tempfile.TemporaryDirectory()
        self.personal = Path(self._personal_tmp.name)
        self._prev = os.environ.get("PR_PERSONAL_DIR")
        os.environ["PR_PERSONAL_DIR"] = str(self.personal)
        # Init a vault so the zero-artifact assertions have a real audit_runs table to count.
        self.candidate = "snap-refusal"
        v = vault.open_vault(self.candidate)
        v.con.close()

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("PR_PERSONAL_DIR", None)
        else:
            os.environ["PR_PERSONAL_DIR"] = self._prev
        self._corpus_tmp.cleanup()
        self._personal_tmp.cleanup()

    # --- helpers ---------------------------------------------------------- #
    def _run(self, db, family, max_age_days) -> tuple[dict | None, int]:
        """Drive the wrapper with ``--json`` on; return (parsed_envelope_or_None, code)."""
        args = argparse.Namespace(json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli._require_readable_snapshot(args, str(db), family, max_age_days)
        out = buf.getvalue()
        return (json.loads(out) if out.strip() else None), code

    def _audit_runs_count(self) -> int:
        v = vault.open_vault(self.candidate)
        try:
            return v.con.execute("SELECT count(*) FROM audit_runs").fetchone()[0]
        finally:
            v.con.close()

    def _report_files(self) -> list[Path]:
        out = (self.personal / "candidates" / self.candidate / "output" / "crs-audit")
        return list(out.glob("*")) if out.exists() else []

    def _assert_refusal(self, env, code, expected_reason: str) -> None:
        self.assertEqual(code, contract.EXIT_INVALID_INPUT)  # non-zero (2)
        self.assertIsNotNone(env)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)
        msg = env["error"]["message"]
        self.assertIn(f"reason={expected_reason}", msg)  # stable machine reason token
        # PII-perimeter: no evidence id, no applicant value, no vault-internal path.
        self.assertNotIn("ev_", msg)
        self.assertNotIn(str(self.personal), msg)

    # --- refusal cases (SAFE-10) ------------------------------------------ #
    def test_missing_family_refuses_cleanly(self) -> None:
        db = self.corpus / "index.db"
        _build_snapshot_index(db, family="guidance", chunks=["alpha beta", "gamma delta"])
        env, code = self._run(db, "dli", 30)  # family 'dli' absent from the index
        self._assert_refusal(env, code, "snapshot_missing")

    def test_drifted_family_refuses_cleanly(self) -> None:
        db = self.corpus / "drift.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta", "gamma delta"],
                              tamper_first_sha=True)
        env, code = self._run(db, "dli", 3650)  # large bound: drift is the fault, not age
        self._assert_refusal(env, code, "snapshot_drifted")

    def test_stale_family_refuses_cleanly(self) -> None:
        db = self.corpus / "stale.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta"],
                              crawl_date="2000-01-01")
        env, code = self._run(db, "dli", 30)
        self._assert_refusal(env, code, "snapshot_stale")

    # --- zero-artifact proof (Pitfall 4) ---------------------------------- #
    def test_refusal_writes_zero_artifacts(self) -> None:
        db = self.corpus / "no-such-index.db"  # missing db → snapshot_missing
        self.assertEqual(self._audit_runs_count(), 0)
        env, code = self._run(db, "dli", 30)
        self._assert_refusal(env, code, "snapshot_missing")
        # Preflight-only: it opens the snapshot read-only and only emits an envelope.
        self.assertEqual(self._audit_runs_count(), 0)
        self.assertEqual(self._report_files(), [])

    # --- non-json refusal path -------------------------------------------- #
    def test_refusal_non_json_writes_stderr_line(self) -> None:
        db = self.corpus / "index.db"
        _build_snapshot_index(db, family="guidance", chunks=["alpha beta"])
        args = argparse.Namespace(json=False)
        err = io.StringIO()
        with redirect_stderr(err):
            code = cli._require_readable_snapshot(args, str(db), "dli", 30)
        self.assertEqual(code, contract.EXIT_INVALID_INPUT)
        self.assertIn("reason=snapshot_missing", err.getvalue())

    # --- positive control (SAFE-10 SC4) ----------------------------------- #
    def test_healthy_family_permits_downstream(self) -> None:
        db = self.corpus / "healthy.db"
        _build_snapshot_index(db, family="dli", chunks=["alpha beta", "gamma delta"],
                              crawl_date="2026-07-10")
        args = argparse.Namespace(json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = cli._require_readable_snapshot(args, str(db), "dli", 3650)
        self.assertIsNone(result)          # None → permits downstream work (SC4)
        self.assertEqual(buf.getvalue(), "")  # emits nothing on the healthy path


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
