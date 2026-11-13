"""Extraction PII-perimeter conformance (Phase 30 — Plan 04, EXTRACT-05 / privacy).

Stdlib ``unittest`` ONLY — NO pytest, NO network. Proves the NEW extraction
artifact surface (rendered page images, OCR/extracted text, value/confirmation
exports) is publish-safe-flagged AND unstageable, and that the extraction engine
writes ONLY under covered vault subtrees. ALL fixtures SYNTHETIC + tempdir-only.

The publish-safety guard is imported via the same ``scripts`` sys.path shim used
by ``scripts/tests/test_check_publish_safe.py`` / ``test_vault_pii_perimeter.py``.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_extraction_pii_perimeter.py -q
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import extraction, paths, vault
from crawler.tests.fixtures.extraction import make_fixtures as mf

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GITIGNORE = _REPO_ROOT / ".gitignore"


def _load_cps():
    """Import scripts/check_publish_safe (scripts/ is NOT a package → sys.path shim)."""
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # noqa: E402 — SAFE-02 share-safety scanner
    return cps


class TestNewArtifactsFlagged(unittest.TestCase):
    """Each NEW extraction artifact type trips scan_vault_artifact."""

    def test_rendered_ocr_and_export_artifacts_flagged(self) -> None:
        cps = _load_cps()
        for path in (
            "personal/candidates/default/files/rendered/doc_x/page-0001.png",
            "personal/candidates/default/files/text/doc_x.txt",
            "personal/candidates/default/files/text/doc_x.json",
            # stray copies outside personal/ are ALSO caught by subtree+ext.
            "files/rendered/doc_x/page-0001.png",
            "files/text/doc_x.txt",
        ):
            violations = cps.scan_vault_artifact(path)
            self.assertTrue(violations, path)
            self.assertEqual(violations[0].category, "VAULT_ARTIFACT")


class TestUnstageable(unittest.TestCase):
    """`git add -A` cannot stage extraction artifacts (project .gitignore)."""

    def _git(self, cwd: Path, *args: str) -> str:
        env = dict(os.environ)
        env.update({"GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_SYSTEM": "/dev/null"})
        out = subprocess.run(["git", "-C", str(cwd), *args],
                             check=True, capture_output=True, text=True, env=env)
        return out.stdout

    def test_extraction_artifacts_stay_unstaged(self) -> None:
        self.assertTrue(_GITIGNORE.is_file())
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            self._git(repo, "init", "-q")
            (repo / ".gitignore").write_bytes(_GITIGNORE.read_bytes())
            base = repo / "personal/candidates/default/files"
            (base / "rendered/doc_x").mkdir(parents=True, exist_ok=True)
            (base / "rendered/doc_x/page-0001.png").write_bytes(b"\x89PNG synthetic")
            (base / "text").mkdir(parents=True, exist_ok=True)
            (base / "text/doc_x.txt").write_text("synthetic OCR text", "utf-8")

            self._git(repo, "add", "-A")
            tracked = self._git(repo, "ls-files")
            self.assertNotIn("candidates", tracked)
            self.assertNotIn("rendered", tracked)
            self.assertNotIn(".png", tracked)
            self.assertEqual(tracked.strip(), ".gitignore")

    def test_forced_tracked_copy_is_publish_unsafe(self) -> None:
        cps = _load_cps()
        # A stray rendered image tracked outside personal/ is publish-unsafe.
        violations = cps.scan_vault_artifact("docs/rendered/x/page-0001.png")
        self.assertTrue(violations)
        self.assertEqual(cps.exit_code(violations), 1)


class TestEngineWritesStayInVault(unittest.TestCase):
    """The engine's actual write paths resolve under covered vault subtrees."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def test_engine_artifacts_land_under_covered_subtrees(self) -> None:
        cps = _load_cps()
        v = vault.open_vault("default")
        try:
            src = Path(self._tmp.name) / "d.pdf"
            src.write_bytes(mf.language_test_pdf())
            doc = vault.import_document(v, "default", src,
                                        doc_type="language_test").document_id
            extraction.extract_document(v, doc)
            rendered = paths.resolve_within(v.root, "files", "rendered", doc)
            text = paths.resolve_within(v.root, "files", "text", f"{doc}.txt")
            self.assertTrue(rendered.is_dir())
            self.assertTrue(text.is_file())
            # Every produced artifact resolves inside the candidate root...
            for p in list(rendered.rglob("*")) + [text]:
                self.assertTrue(paths.is_within(v.root, p))
            # ...and its vault-relative path is VAULT_ARTIFACT-flagged.
            rel_png = f"personal/candidates/default/files/rendered/{doc}/page-0001.png"
            rel_txt = f"personal/candidates/default/files/text/{doc}.txt"
            self.assertTrue(cps.scan_vault_artifact(rel_png))
            self.assertTrue(cps.scan_vault_artifact(rel_txt))
        finally:
            v.con.close()


class TestRealTreeScansClean(unittest.TestCase):
    """The actual tracked repo tree scans publish-safe (0 violations)."""

    def test_tracked_tree_is_clean(self) -> None:
        cps = _load_cps()
        root = cps.repo_root()
        violations = []
        for path in cps.tracked_files(root):
            if cps.is_excluded(path):
                continue
            violations.extend(cps.scan_path_name(path))
            violations.extend(cps.scan_vault_artifact(path))
            try:
                with open(os.path.join(root, path), "rb") as handle:
                    raw = handle.read()
            except OSError:
                continue
            text = cps.decode_for_scan(raw)
            if text is None:
                continue
            violations.extend(cps.scan_text(path, text))
        self.assertEqual(cps.exit_code(violations), 0,
                         [v.render() for v in violations])


if __name__ == "__main__":
    unittest.main()
