"""Offline tests for the doctor/preflight verb (Phase 30 — Plan 04).

Stdlib ``unittest`` ONLY — NO pytest, NO network. ``$PR_PERSONAL_DIR`` → tmp.
All fixtures are SYNTHETIC (generated at test time).

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_doctor.py -q
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

from crawler import doctor, extraction, vault
from crawler.tests.fixtures.extraction import make_fixtures as mf


class _DoctorTmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        from crawler import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _extract(self, data: bytes, doc_type: str) -> str:
        v = vault.open_vault("default")
        try:
            src = Path(self._tmp.name) / "d.pdf"
            src.write_bytes(data)
            doc = vault.import_document(v, "default", src, doc_type=doc_type)
            extraction.extract_document(v, doc.document_id)
            return doc.document_id
        finally:
            v.con.close()


class TestProbeDependencies(_DoctorTmpCase):
    def test_required_deps_present_here(self) -> None:
        required, optional = doctor.probe_dependencies()
        req_names = {d.name for d in required}
        self.assertTrue({"pypdfium2", "Pillow", "pdfminer.six"} <= req_names)
        for d in required:
            self.assertTrue(d.required)
            self.assertTrue(d.present)  # doc-extract installed in this env
            self.assertIn("doc-extract", d.hint)
        opt_names = {d.name for d in optional}
        self.assertIn("pytesseract", opt_names)
        self.assertIn("tesseract", opt_names)
        for d in optional:
            self.assertFalse(d.required)

    def test_missing_required_dep_makes_overall_missing(self) -> None:
        with mock.patch.object(
                extraction, "_import_pdfium",
                side_effect=extraction.MissingExtractionDependency(
                    "pypdfium2", "doc-extract")):
            report = doctor.run_doctor()
        self.assertEqual(report.overall, "missing_dependency")
        # optional OCR absence never flips overall.
        self.assertTrue(any(d.name == "pypdfium2" and not d.present
                            for d in report.required))


class TestDoctorCli(_DoctorTmpCase):
    def test_all_present_exits_0_ok(self) -> None:
        rc, out, _ = self._run(["--json", "doctor"])
        self.assertEqual(rc, 0)
        env = json.loads(out)
        self.assertEqual(env["command"], "doctor")
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["overall"], "ok")
        self.assertIn("deps", env["result"])
        self.assertIn("optional", env["result"])

    def test_missing_required_dep_exit_3(self) -> None:
        with mock.patch.object(
                extraction, "_import_pdfminer",
                side_effect=extraction.MissingExtractionDependency(
                    "pdfminer.six", "doc-extract")):
            rc, out, err = self._run(["--json", "doctor"])
        self.assertEqual(rc, 3)
        env = json.loads(out)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], "missing_dependency")
        # never internal_error
        self.assertNotEqual(env["error"]["type"], "internal_error")

    def test_scan_quality_surfaced(self) -> None:
        doc = self._extract(mf.language_test_multipage_pdf(), "language_test")
        rc, out, _ = self._run(
            ["--json", "doctor", "--candidate", "default", "--document-id", doc])
        self.assertEqual(rc, 0)
        env = json.loads(out)
        qc = env["result"]["quality_counts"]
        self.assertEqual(qc["pages"], 3)
        self.assertGreaterEqual(qc["scanned"], 1)
        self.assertGreaterEqual(qc["low_text"], 1)

    def test_envelope_is_pii_light(self) -> None:
        doc = self._extract(mf.language_test_pdf(), "language_test")
        rc, out, _ = self._run(
            ["--json", "doctor", "--candidate", "default", "--document-id", doc])
        # No raw values, no absolute tmp path in the machine envelope.
        self.assertNotIn(mf.FAKE_TRF, out)
        self.assertNotIn(self._tmp.name, out)

    def test_human_hints_go_to_stderr(self) -> None:
        rc, out, err = self._run(["doctor"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")          # human mode: stdout empty
        self.assertIn("pypdfium2", err)            # dep status on stderr


if __name__ == "__main__":
    unittest.main()
