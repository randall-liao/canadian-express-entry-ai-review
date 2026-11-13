"""Offline tests for the additive `vault` CLI verbs (Phase 29 — VAULT-01/02/03).

Stdlib ``unittest`` ONLY — NO pytest, NO network. Each test drives
``crawler.cli.main([...])`` with ``$PR_PERSONAL_DIR`` pointed at a throwaway
``tempfile.TemporaryDirectory`` so the vault is created under tmp and NEVER touches
the real git-ignored ``personal/`` tree. Every ``--json`` run must print EXACTLY
ONE valid five-key envelope to stdout; human text goes to stderr.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_vault_cli.py -q
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

from crawler import cli

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE_FACTORS = _REPO_ROOT / "personal.example" / "crs-profile.example.yaml"


class _VaultCliCase(unittest.TestCase):
    """Base case: fresh tmp $PR_PERSONAL_DIR per test + a main([...]) runner."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name}
        )
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _one_envelope(self, stdout: str) -> dict:
        """Assert stdout is EXACTLY one valid five-key envelope; return it."""
        data = json.loads(stdout)  # raises if not exactly one JSON object
        self.assertEqual(
            set(data.keys()),
            {"schema_version", "ok", "command", "result", "error"},
        )
        self.assertEqual(data["command"], "vault")
        self.assertEqual(data["schema_version"], "1.0")
        return data

    def _tmp_src(self, name: str, data: bytes = b"%PDF-1.4 synthetic") -> Path:
        src = Path(self._tmp.name) / name
        src.write_bytes(data)
        return src


class TestVaultInit(_VaultCliCase):
    def test_init_creates_then_selects(self) -> None:
        rc, out, _ = self._run(["--json", "vault", "init", "--candidate", "default"])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["candidate_id"], "default")
        self.assertEqual(env["result"]["vault_kind"], "candidate")
        self.assertTrue(env["result"]["created"])
        # Second init on the same id: exists, not created.
        rc2, out2, _ = self._run(["--json", "vault", "init", "--candidate", "default"])
        self.assertEqual(rc2, 0)
        self.assertFalse(self._one_envelope(out2)["result"]["created"])

    def test_init_slugifies_candidate(self) -> None:
        rc, out, _ = self._run(
            ["--json", "vault", "init", "--candidate", "My Candidate"])
        self.assertEqual(rc, 0)
        self.assertEqual(
            self._one_envelope(out)["result"]["candidate_id"], "my-candidate")


class TestVaultProfile(_VaultCliCase):
    def test_profile_set_from_factor_file(self) -> None:
        self.assertTrue(_EXAMPLE_FACTORS.is_file())
        rc, out, _ = self._run([
            "--json", "vault", "profile", "set",
            "--factor-file", str(_EXAMPLE_FACTORS)])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertGreaterEqual(env["result"]["factor_count"], 4)

    def test_profile_set_inline(self) -> None:
        rc, out, _ = self._run([
            "--json", "vault", "profile", "set",
            "--factor-id", "core_age", "--group", "core_human_capital",
            "--points", "100", "--value-json", '{"age_years": 29}'])
        self.assertEqual(rc, 0)
        self.assertEqual(self._one_envelope(out)["result"]["factor_count"], 1)

    def test_profile_show_is_pii_light(self) -> None:
        # Store a factor with a distinctive private points value...
        self._run([
            "--json", "vault", "profile", "set",
            "--factor-id", "core_age", "--group", "core_human_capital",
            "--points", "1373"])
        rc, out, _ = self._run(["--json", "vault", "profile", "show"])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertEqual(env["result"]["factor_count"], 1)
        self.assertIn("core_human_capital", env["result"]["groups_present"])
        # ...and assert the private claimed_points value never reaches stdout.
        self.assertNotIn("1373", out)

    def test_profile_set_missing_file_is_invalid_input(self) -> None:
        rc, out, _ = self._run([
            "--json", "vault", "profile", "set",
            "--factor-file", str(Path(self._tmp.name) / "nope.yaml")])
        self.assertEqual(rc, 2)
        env = self._one_envelope(out)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], "invalid_input")


class TestVaultIta(_VaultCliCase):
    def test_ita_set(self) -> None:
        rc, out, _ = self._run([
            "--json", "vault", "ita", "set", "--round", "round-999",
            "--date", "2026-01-15", "--program", "express_entry",
            "--cutoff", "520", "--claimed-score", "531"])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertTrue(env["result"]["round_id"].startswith("ita_"))
        self.assertTrue(env["result"]["has_cutoff"])
        self.assertEqual(env["result"]["program"], "express_entry")


class TestVaultImport(_VaultCliCase):
    def test_import_is_pii_light(self) -> None:
        # Decisive proof: a fake PII token in the basename must NEVER reach stdout,
        # nor the absolute source path — but the ev_ evidence id must.
        src = self._tmp_src("Jane_Doe_UCI123.pdf")
        rc, out, _ = self._run([
            "--json", "vault", "import", str(src), "--doc-type", "language_test"])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        self.assertTrue(env["result"]["evidence_id"].startswith("ev_"))
        self.assertEqual(env["result"]["doc_type"], "language_test")
        # PII-light stdout: filename token + absolute path absent; ev_ present.
        self.assertNotIn("Jane_Doe_UCI123", out)
        self.assertNotIn(str(src), out)
        self.assertIn(env["result"]["evidence_id"], out)

    def test_import_missing_path_is_invalid_input(self) -> None:
        missing = Path(self._tmp.name) / "nope.pdf"
        rc, out, _ = self._run([
            "--json", "vault", "import", str(missing), "--doc-type", "eca"])
        self.assertEqual(rc, 2)
        env = self._one_envelope(out)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], "invalid_input")
        # The bad path must not be echoed back into the envelope.
        self.assertNotIn(str(missing), out)

    def test_mec_import_is_pii_light_and_accepts_every_canonical_doc_type(self) -> None:
        from crawler import mecfields

        for index, doc_type in enumerate(mecfields.MEC_DOCUMENT_FIELDS):
            with self.subTest(doc_type=doc_type):
                src = self._tmp_src(
                    f"Private_MEC_{index}.pdf",
                    f"%PDF-1.4 synthetic {index}".encode(),
                )
                rc, out, _ = self._run(
                    ["--json", "vault", "import", str(src), "--doc-type", doc_type]
                )
                self.assertEqual(rc, 0)
                result = self._one_envelope(out)["result"]
                self.assertEqual(result["doc_type"], doc_type)
                self.assertNotIn("Private_MEC", out)


class TestVaultList(_VaultCliCase):
    def test_list_is_pii_light(self) -> None:
        src = self._tmp_src("Jane_Doe_UCI123.pdf")
        self._run(["--json", "vault", "import", str(src), "--doc-type", "eca"])
        rc, out, _ = self._run(["--json", "vault", "list"])
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertEqual(env["result"]["document_count"], 1)
        doc = env["result"]["documents"][0]
        self.assertEqual(set(doc.keys()),
                         {"document_id", "evidence_id", "doc_type", "status"})
        self.assertTrue(doc["evidence_id"].startswith("ev_"))
        # No original filename anywhere in the listing.
        self.assertNotIn("Jane_Doe_UCI123", out)


if __name__ == "__main__":
    unittest.main()
