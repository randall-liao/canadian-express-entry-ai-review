"""Unit tests for the shared personal-path resolver (Phase 29 — VAULT-01, T-29-01).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network (per the
``crawler/tests/test_searchindex.py`` / ``test_grounding.py`` / AGENTS.md
convention). Every filesystem test writes into a ``tempfile.TemporaryDirectory``
and NEVER touches the real git-ignored ``personal/`` tree.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_paths.py -q
    .venv/bin/python -m unittest crawler.tests.test_paths -v

Behaviour map:

    TestRepoAnchors      — repo_root / repo_personal_root / legacy_personal_dir /
                           running_from_repo_checkout (frozen v3.x anchors)
    TestPersonalRoot     — personal_root precedence: explicit > env > repo > platformdirs
    TestContainment      — is_within / resolve_within incl. symlink + ``..`` escapes
    TestCandidateId      — safe_candidate_id slugify + empty-raise; candidate_root
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import paths

# Repo root (this suite lives at <root>/crawler/tests/test_paths.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestRepoAnchors(unittest.TestCase):
    """repo_root / repo_personal_root / legacy_personal_dir anchors."""

    def test_repo_root_is_parent_of_crawler(self) -> None:
        # crawler/ is one level below the repo root; the anchor must match.
        self.assertEqual(paths.repo_root(), _REPO_ROOT)
        self.assertTrue((paths.repo_root() / "crawler" / "paths.py").is_file())

    def test_repo_personal_root_is_repo_slash_personal_resolved(self) -> None:
        expected = (_REPO_ROOT / "personal").resolve()
        self.assertEqual(paths.repo_personal_root(), expected)
        self.assertTrue(paths.repo_personal_root().is_absolute())

    def test_repo_personal_root_ignores_env(self) -> None:
        # The frozen ground/checklist write-gate anchor must NEVER consult
        # $PR_PERSONAL_DIR — it is unconditionally <repo>/personal.
        with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": "/some/other/dir"}):
            self.assertEqual(
                paths.repo_personal_root(), (_REPO_ROOT / "personal").resolve()
            )

    def test_legacy_personal_dir_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PR_PERSONAL_DIR", None)
            self.assertEqual(paths.legacy_personal_dir(), Path("personal"))

    def test_legacy_personal_dir_env_override_verbatim(self) -> None:
        with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": "/some/dir"}):
            self.assertEqual(paths.legacy_personal_dir(), Path("/some/dir"))

    def test_running_from_repo_checkout_true_here(self) -> None:
        # This test tree lives inside a real git checkout (<repo>/.git exists).
        self.assertTrue(paths.running_from_repo_checkout())


class TestPersonalRoot(unittest.TestCase):
    """personal_root precedence: explicit > $PR_PERSONAL_DIR > repo > platformdirs."""

    def test_explicit_arg_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            explicit = Path(tmp) / "vaultroot"
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": "/env/ignored"}):
                self.assertEqual(
                    paths.personal_root(explicit=explicit), explicit.resolve()
                )

    def test_env_wins_over_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": tmp}):
                self.assertEqual(paths.personal_root(), Path(tmp).resolve())

    def test_repo_when_in_checkout(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PR_PERSONAL_DIR", None)
            with mock.patch.object(paths, "running_from_repo_checkout",
                                   return_value=True):
                self.assertEqual(paths.personal_root(), paths.repo_personal_root())

    def test_platformdirs_fallback_when_not_in_checkout(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PR_PERSONAL_DIR", None)
            with mock.patch.object(paths, "running_from_repo_checkout",
                                   return_value=False):
                got = paths.personal_root()
                import platformdirs
                expected = (platformdirs.user_data_path("pr-review-agents")
                            / "personal").resolve()
                self.assertEqual(got, expected)

    def test_personal_root_always_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rel_child = Path(tmp).name  # relative-looking name
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": tmp}):
                self.assertTrue(paths.personal_root().is_absolute())


class TestContainment(unittest.TestCase):
    """is_within + resolve_within, including symlink and ``..`` escapes."""

    def test_is_within_equal_and_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(paths.is_within(root, root))
            child = root / "a" / "b"
            self.assertTrue(paths.is_within(root, child))

    def test_is_within_rejects_sibling_and_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            sibling = Path(tmp) / "sibling"
            self.assertFalse(paths.is_within(root, sibling))
            self.assertFalse(paths.is_within(root, root.parent))

    def test_resolve_within_returns_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            got = paths.resolve_within(root, "files", "raw", "x.pdf")
            self.assertEqual(got, root / "files" / "raw" / "x.pdf")

    def test_resolve_within_rejects_absolute_part(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(root, "/etc/passwd")

    def test_resolve_within_rejects_dotdot_part(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(root, "..", "escape.txt")

    def test_resolve_within_rejects_embedded_dotdot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(root, "a/../../escape.txt")

    def test_resolve_within_rejects_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            link = root / "escape"
            link.symlink_to(outside, target_is_directory=True)
            # A symlink under root pointing outside is caught because .resolve()
            # follows it before the containment check.
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(root, "escape", "x.txt")

    def test_resolve_within_allows_dotdot_lookalike_name(self) -> None:
        # A filename that merely starts with ".." is not a traversal component.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            got = paths.resolve_within(root, "..hidden")
            self.assertEqual(got, root / "..hidden")


class TestCandidateId(unittest.TestCase):
    """safe_candidate_id slugify + empty-raise; candidate_root composition."""

    def test_slugifies_and_lowercases(self) -> None:
        self.assertEqual(paths.safe_candidate_id("Default Candidate"),
                         "default-candidate")
        self.assertEqual(paths.safe_candidate_id("ABC_123"), "abc-123")

    def test_collapses_runs_and_strips_edges(self) -> None:
        self.assertEqual(paths.safe_candidate_id("  **weird**  "), "weird")
        self.assertEqual(paths.safe_candidate_id("a///b"), "a-b")

    def test_traversal_shaped_input_is_sanitized(self) -> None:
        slug = paths.safe_candidate_id("../../etc/passwd")
        self.assertNotIn("/", slug)
        self.assertNotIn("..", slug)

    def test_empty_result_raises(self) -> None:
        with self.assertRaises(paths.PathEscapeError):
            paths.safe_candidate_id("///")
        with self.assertRaises(paths.PathEscapeError):
            paths.safe_candidate_id("")

    def test_candidate_root_composition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"PR_PERSONAL_DIR": tmp}):
                got = paths.candidate_root("Default Candidate")
                expected = (Path(tmp).resolve() / "candidates"
                            / "default-candidate")
                self.assertEqual(got, expected)


if __name__ == "__main__":
    unittest.main()
