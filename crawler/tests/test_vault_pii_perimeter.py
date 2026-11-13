"""PII-perimeter conformance suite (Phase 29 — SC3 + SC4 / VAULT-03 + VAULT-04).

Stdlib ``unittest`` ONLY — NO pytest, NO network. Proves the candidate-vault
boundary end-to-end:

* SC4 — vault artifacts are publish-safe-flagged AND unstageable (``git add -A``
  cannot stage them), and writes cannot escape the candidate root.
* SC3 — a candidate ``evidence_id`` is never a corpus ``citation_id`` and is never
  resolvable as a corpus chunk; importing never contaminates ``corpus/``.

ALL fixtures are SYNTHETIC and tempdir-only — never real PII, never written under
the repo tree (PITFALLS-v4.0 Anti-Pattern 4). The publish-safety guard is imported
as a top-level module via the same ``scripts`` sys.path shim used by
``scripts/tests/test_check_publish_safe.py``.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_vault_pii_perimeter.py -q
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import paths, searchindex, vault

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GITIGNORE = _REPO_ROOT / ".gitignore"


def _load_cps():
    """Import scripts/check_publish_safe (scripts/ is NOT a package → sys.path shim)."""
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # noqa: E402 — SAFE-02 share-safety scanner
    return cps


class _TmpVaultCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()


class TestSc4PublishSafe(_TmpVaultCase):
    """SC4: publish-safe flags the vault DB via both categories."""

    def test_vault_db_flagged_by_both_categories(self) -> None:
        cps = _load_cps()
        path = "personal/candidates/default/vault.sqlite"
        self.assertTrue(cps.scan_vault_artifact(path))
        corpora = cps.scan_path_name(path)
        self.assertEqual(len(corpora), 1)
        self.assertEqual(corpora[0].category, "TRACKED_CORPORA")


class TestSc4GitStaging(_TmpVaultCase):
    """SC4: `git add -A` cannot stage a vault artifact (the project .gitignore)."""

    def _git(self, cwd: Path, *args: str) -> str:
        env = dict(os.environ)
        env.update({
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        })
        out = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True, capture_output=True, text=True, env=env,
        )
        return out.stdout

    def test_vault_artifact_stays_unstaged(self) -> None:
        self.assertTrue(_GITIGNORE.is_file())
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            self._git(repo, "init", "-q")
            # Seed the project's real .gitignore into the throwaway repo.
            (repo / ".gitignore").write_bytes(_GITIGNORE.read_bytes())
            vault_rel = "personal/candidates/default/vault.sqlite"
            vpath = repo / vault_rel
            vpath.parent.mkdir(parents=True, exist_ok=True)
            vpath.write_bytes(b"SQLite format 3\x00 synthetic")
            # Also a WAL sidecar + a raw doc under files/raw.
            (vpath.parent / "vault.sqlite-wal").write_bytes(b"wal")
            raw = repo / "personal/candidates/default/files/raw"
            raw.mkdir(parents=True, exist_ok=True)
            (raw / "abc.pdf").write_bytes(b"%PDF-1.4 synthetic")

            self._git(repo, "add", "-A")
            tracked = self._git(repo, "ls-files")
            status = self._git(repo, "status", "--porcelain")

            self.assertNotIn("candidates", tracked)
            self.assertNotIn(".sqlite", tracked)
            self.assertNotIn("candidates", status)
            # Only .gitignore itself is stageable.
            self.assertEqual(tracked.strip(), ".gitignore")


class TestSc4PathGuard(_TmpVaultCase):
    """SC4: writes cannot escape the candidate root (`..` + symlink)."""

    def test_dotdot_escape_raises(self) -> None:
        root = paths.candidate_root("default")
        root.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(paths.PathEscapeError):
            paths.resolve_within(root, "..", "..", "escape.txt")

    def test_symlink_escape_raises(self) -> None:
        root = paths.candidate_root("default")
        root.mkdir(parents=True, exist_ok=True)
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        link = root / "escape"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(paths.PathEscapeError):
            paths.resolve_within(root, "escape", "x.txt")

    def test_import_writes_only_inside_candidate_root(self) -> None:
        v = vault.open_vault("default")
        try:
            src = Path(self._tmp.name) / "doc.pdf"
            src.write_bytes(b"%PDF-1.4 synthetic")
            summary = vault.import_document(v, "default", src, doc_type="eca")
            row = v.con.execute(
                "SELECT storage_relpath FROM documents WHERE document_id = ?",
                (summary.document_id,),
            ).fetchone()
            written = (v.root / row["storage_relpath"]).resolve()
            self.assertTrue(paths.is_within(v.root, written))
            self.assertTrue(written.is_file())
        finally:
            v.con.close()


class TestSc3IdSeparation(_TmpVaultCase):
    """SC3: evidence_id and citation_id namespaces are disjoint."""

    def test_evidence_vs_citation_disjoint(self) -> None:
        eid = vault.new_evidence_id()
        self.assertTrue(vault.is_evidence_id(eid))
        self.assertFalse(vault.is_citation_id(eid))
        cid = "guides/eca.md#0"
        self.assertTrue(vault.is_citation_id(cid))
        self.assertFalse(vault.is_evidence_id(cid))


class TestSc3NeverCitable(unittest.TestCase):
    """SC3: a candidate evidence_id never resolves as a corpus chunk."""

    def _build_corpus(self, tmp: Path) -> Path:
        corpus = tmp / "corpus_src"
        corpus.mkdir()
        (corpus / "doc.md").write_text(
            "---\n"
            'url: "https://www.canada.ca/en/immigration/example"\n'
            'title: "Synthetic Rule Page"\n'
            'source_type: "guidance"\n'
            'crawl_date: "2026-01-01"\n'
            "---\n\n"
            "# Heading\n\nA synthetic PII-free rule sentence for the index.\n",
            encoding="utf-8",
        )
        db = tmp / "index.db"
        try:
            searchindex.build_index(corpus, db)
        except searchindex.FTS5Unavailable as exc:  # pragma: no cover
            self.skipTest(f"FTS5 unavailable: {exc}")
        return db

    def test_evidence_id_is_not_a_corpus_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = self._build_corpus(Path(d))
            # Sanity: a real corpus chunk_id resolves.
            row = None
            import sqlite3
            con = sqlite3.connect(str(db))
            try:
                r = con.execute(
                    "SELECT chunk_id FROM chunks LIMIT 1").fetchone()
                row = r[0] if r else None
            finally:
                con.close()
            self.assertIsNotNone(row)
            self.assertIsNotNone(searchindex.resolve(db, row))
            # A minted candidate evidence id is NOT a corpus chunk.
            eid = vault.new_evidence_id()
            self.assertIsNone(searchindex.resolve(db, eid))


class TestSc3NoContamination(_TmpVaultCase):
    """SC3: importing a document never writes under corpus/."""

    def test_import_leaves_corpus_unchanged(self) -> None:
        corpus_dir = Path(self._tmp.name) / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "index.db").write_bytes(b"CORPUS-SENTINEL")
        before = sorted(
            (p.name, p.read_bytes()) for p in corpus_dir.iterdir())
        v = vault.open_vault("default")
        try:
            src = Path(self._tmp.name) / "doc.pdf"
            src.write_bytes(b"%PDF-1.4 synthetic")
            vault.import_document(v, "default", src, doc_type="nomination")
        finally:
            v.con.close()
        after = sorted(
            (p.name, p.read_bytes()) for p in corpus_dir.iterdir())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
