"""CLI refusal + no-artifact proof for the corpus-index preflight (HARD-01/02).

Exercises the REAL ``vault audit`` CLI path (via ``cli.main``) against a bad ``--db``
and asserts a stable, PII-free refusal on the frozen ``invalid_input``/exit-2
contract with a ``reason=<code>`` token and the index/doctor recovery hint — and
that ZERO artifacts (audit report file / ``audit_runs`` row) are written. Stdlib
``unittest`` ONLY; the vault lives under a tempdir via ``PR_PERSONAL_DIR``.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from crawler import cli, contract, vault


def _run_json(argv: list[str]) -> tuple[dict, int]:
    """Run cli.main(argv) capturing stdout; return (parsed_envelope, exit_code)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return json.loads(buf.getvalue()), code


class AuditIndexRefusal(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.personal = Path(self._tmp.name)
        self._prev = os.environ.get("PR_PERSONAL_DIR")
        os.environ["PR_PERSONAL_DIR"] = str(self.personal)
        # Init a vault + a minimal claimed profile so the ONLY failure is the --db.
        self.candidate = "refusal"
        v = vault.open_vault(self.candidate)
        v.con.close()
        self.profile_file = self.personal / "profile.yaml"
        self.profile_file.write_text(
            "factors:\n"
            "  - factor_id: core.language.first\n"
            "    factor_group: core_human_capital\n"
            "    claimed_points: 124\n"
            "    claimed_level: CLB9\n"
            "    claimed_value: {listening: CLB9}\n",
            encoding="utf-8")
        _run_json(["--json", "vault", "profile", "set", "--candidate",
                   self.candidate, "--factor-file", str(self.profile_file)])

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("PR_PERSONAL_DIR", None)
        else:
            os.environ["PR_PERSONAL_DIR"] = self._prev
        self._tmp.cleanup()

    def _audit_runs_count(self) -> int:
        v = vault.open_vault(self.candidate)
        try:
            return v.con.execute("SELECT count(*) FROM audit_runs").fetchone()[0]
        finally:
            v.con.close()

    def _report_files(self) -> list[Path]:
        out = (self.personal / "candidates" / self.candidate / "output" / "crs-audit")
        return list(out.glob("*")) if out.exists() else []

    def _assert_refusal(self, db_arg: str, expected_reason: str) -> None:
        env, code = _run_json(["--json", "vault", "audit", "--all",
                               "--candidate", self.candidate, "--db", db_arg])
        # frozen contract vocabulary + specific reason code
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)
        self.assertEqual(code, contract.EXIT_INVALID_INPUT)  # non-zero (2)
        msg = env["error"]["message"]
        self.assertIn(f"reason={expected_reason}", msg)
        self.assertIn("index", msg)       # recovery: rebuild index
        self.assertIn("doctor", msg)      # recovery: verify with doctor
        # PII-free
        self.assertNotIn("ev_", msg)
        # HARD-02: zero artifacts written
        self.assertEqual(self._audit_runs_count(), 0)
        self.assertEqual(self._report_files(), [])

    def test_missing_db_refuses_cleanly(self) -> None:
        self._assert_refusal(str(self.personal / "no-such-index.db"), "index_missing")

    def test_empty_db_refuses_cleanly(self) -> None:
        empty = self.personal / "empty.db"
        empty.write_bytes(b"")
        self._assert_refusal(str(empty), "index_empty")

    def test_corrupt_db_refuses_cleanly(self) -> None:
        corrupt = self.personal / "corrupt.db"
        corrupt.write_bytes(b"this is not a sqlite database at all")
        self._assert_refusal(str(corrupt), "index_corrupt")


_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"


class AuditIndexPositiveControl(unittest.TestCase):
    """The healthy real index passes the preflight (no refusal envelope)."""

    @unittest.skipUnless(
        _REAL_DB.is_file(),
        "LOCAL-ONLY: corpus/index.db is git-ignored — preflight positive control "
        "did NOT run",
    )
    def test_real_index_passes_preflight(self) -> None:
        from crawler import index_health
        self.assertTrue(index_health.probe_index(_REAL_DB).ok())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
