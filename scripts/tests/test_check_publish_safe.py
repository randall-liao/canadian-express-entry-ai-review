"""Unit tests for the publish-safety checker (SAFE-02).

Pure stdlib unittest, consistent with the crawler test style (no pytest, no new
deps). These tests exercise the importable pure functions (`scan_text`,
`is_excluded`) so they need no git and no real tree.
"""

import os
import sys
import subprocess
import tempfile
import unittest

# Import the checker as a top-level module without requiring `scripts` to be a
# package on sys.path. The checker lives one directory up from this test file.
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import check_publish_safe as cps  # noqa: E402


class ScanTextCleanTests(unittest.TestCase):
    def test_clean_text_has_no_violations(self):
        # Test 1: clean source passes.
        violations = cps.scan_text("crawler/foo.py", "import os\nx = 1\n")
        self.assertEqual(violations, [])


class ScanTextAbsPathTests(unittest.TestCase):
    def test_home_abs_path_flagged_with_line_number(self):
        # Test 2: an absolute /home/<user> path is an ABS_PATH violation, line 2.
        text = "import os\npath = open('/home/devuser/x')\n"
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(len(violations), 1)
        v = violations[0]
        self.assertEqual(v.category, "ABS_PATH")
        self.assertEqual(v.line, 2)
        self.assertEqual(v.path, "crawler/cli.py")

    def test_uppercase_digit_underscore_usernames_flagged(self):
        # WR-01 regression: /home/<user> must match capitalized, numeric, and
        # underscore-leading usernames, not just lowercase.
        for home in ("/home/Foo/secret", "/home/123/secret", "/home/_priv/x"):
            with self.subTest(home=home):
                violations = cps.scan_text("crawler/cli.py", home + "\n")
                self.assertEqual(len(violations), 1, home)
                self.assertEqual(violations[0].category, "ABS_PATH")

    def test_venv_path_flagged(self):
        # Test 3: a pr-ai-venv reference is an ABS_PATH violation.
        text = "interp = 'pr-ai-venv/bin/python'\n"
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "ABS_PATH")

    def test_machine_interpreter_path_flagged(self):
        text = "shebang = '/usr/bin/python3.10'\n"
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "ABS_PATH")

    def test_bare_interpreter_path_flagged(self):
        # IN-02 coverage: /usr/bin/python3 without a minor version is flagged.
        text = "shebang = '/usr/bin/python3'\n"
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "ABS_PATH")

    def test_users_and_root_paths_flagged(self):
        text = "a = '/Users/john'\nb = '/root/secret'\n"
        violations = cps.scan_text("crawler/cli.py", text)
        cats = [v.category for v in violations]
        self.assertEqual(cats, ["ABS_PATH", "ABS_PATH"])


class ScanTextHttpUrlPathTests(unittest.TestCase):
    def test_official_http_home_pathnames_are_not_local_paths(self):
        for text in (
            "[Rwanda](http://nppa.gov.rw/home/?L=1)",
            "[Switzerland](https://www.bj.admin.ch/bj/en/home/"
            "publiservice/strafregister.html)",
            "<https://www.dubaipolice.gov.ae/wps/portal/home/services/>",
            'url = "HTTPS://www.canada.ca/en/home/services.html"',
        ):
            with self.subTest(text=text):
                self.assertEqual(cps.scan_text("corpus/policy.md", text), [])

    def test_http_pathname_does_not_hide_local_paths_on_same_line(self):
        for text in (
            "https://www.canada.ca/home/help /home/PrivateUser/project",
            "[help](https://www.canada.ca/home/help)/Users/PrivateUser/project",
            "<https://www.canada.ca/home/help>/root/private",
        ):
            with self.subTest(text=text):
                violations = cps.scan_text("docs/setup.md", text)
                self.assertEqual([v.category for v in violations], ["ABS_PATH"])

    def test_http_queries_and_fragments_still_report_local_paths(self):
        for text in (
            "https://www.canada.ca/home/help?file=/home/PrivateUser/project",
            "https://www.canada.ca/home/help?file=/Users/PrivateUser/project",
            "https://www.canada.ca/home/help#file=/root/private",
        ):
            with self.subTest(text=text):
                violations = cps.scan_text("docs/setup.md", text)
                self.assertEqual([v.category for v in violations], ["ABS_PATH"])

    def test_non_http_or_incomplete_urls_do_not_hide_local_paths(self):
        for text in (
            "file:///home/PrivateUser/project",
            "ssh://example.test/home/PrivateUser/project",
            "https:///home/PrivateUser/project",
            "//example.test/home/PrivateUser/project",
        ):
            with self.subTest(text=text):
                violations = cps.scan_text("docs/setup.md", text)
                self.assertEqual([v.category for v in violations], ["ABS_PATH"])

    def test_machine_markers_in_http_pathnames_remain_flagged(self):
        for text in (
            "https://example.test/home/public/pr-ai-venv/bin/python",
            "https://example.test/home/public/usr/bin/python3.12",
        ):
            with self.subTest(text=text):
                violations = cps.scan_text("docs/setup.md", text)
                self.assertEqual([v.category for v in violations], ["ABS_PATH"])

    def test_credentials_inside_http_urls_remain_flagged(self):
        for text in (
            "https://www.canada.ca/home/help?api_key=abcdef1234567890",
            "https://www.canada.ca/home/password=abcdef1234567890",
            "https://www.canada.ca/home/ghp_0123456789abcdefghijABCDEFGHIJ012345",
        ):
            with self.subTest(text=text):
                violations = cps.scan_text("docs/setup.md", text)
                self.assertEqual([v.category for v in violations], ["SECRET"])


class ScanTextSecretTests(unittest.TestCase):
    def test_private_key_header_flagged(self):
        # Test 4a: a private-key header is a SECRET violation.
        text = "-----BEGIN RSA PRIVATE KEY-----\n"
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "SECRET")

    def test_aws_access_key_flagged(self):
        # Test 4b: an AKIA... access key id is a SECRET violation.
        text = "key = 'AKIA0000000000000000'\n"
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "SECRET")

    def test_assigned_secret_flagged(self):
        text = "api_key = 'abcdef1234567890'\n"
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "SECRET")

    def test_unquoted_env_style_secret_flagged(self):
        # WR-02 regression: .env-style unquoted assignments are the most likely
        # real leak vector and must be caught.
        for line in (
            "SECRET_KEY=supersecretvalue123",
            "API_TOKEN=mysecretvalue1234",
            "PASSWORD=hunter2hunter2hunter2",
        ):
            with self.subTest(line=line):
                violations = cps.scan_text("crawler/cli.py", line + "\n")
                self.assertEqual(len(violations), 1, line)
                self.assertEqual(violations[0].category, "SECRET")

    def test_tokenized_secrets_flagged(self):
        # WR-02 regression: high-signal token formats need no assignment keyword.
        for line in (
            "val = 'ghp_0123456789abcdefghijABCDEFGHIJ012345'",  # GitHub PAT (36)
            "ASIA0000000000000000",                            # AWS STS temp key
            "Authorization: Bearer abcdef1234567890ABCDEF",    # Bearer token
            "tok = 'xoxb-1234567890-abcdefghijkl'",            # Slack token
        ):
            with self.subTest(line=line):
                violations = cps.scan_text("crawler/cli.py", line + "\n")
                self.assertGreaterEqual(len(violations), 1, line)
                self.assertEqual(violations[0].category, "SECRET")


class ScanTextAllowMarkerTests(unittest.TestCase):
    def test_allow_marker_skips_line(self):
        # Test 5: an explicit allow marker suppresses the violation on that line.
        text = 'path = "/home/x"  # publish-safe: allow\n'
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(violations, [])


class IsExcludedTests(unittest.TestCase):
    def test_self_and_framework_excluded(self):
        # Test 6: the checker self-excludes and skips the vendored .github tree.
        self.assertTrue(cps.is_excluded("scripts/check_publish_safe.py"))
        self.assertTrue(cps.is_excluded("scripts/tests/test_check_publish_safe.py"))
        self.assertTrue(cps.is_excluded(".github/foo.md"))

    def test_planning_is_scanned_not_excluded(self):
        # CR-01 regression: .planning/ is project-authored and IS scanned, so a
        # real machine path there can no longer hide behind a blanket exclusion.
        self.assertFalse(cps.is_excluded(".planning/STATE.md"))

    def test_github_prefix_is_exact_not_substring(self):
        # CR-01: the .github/ exclusion must match the directory prefix exactly,
        # not a substring like a file literally named "x.github_notes".
        self.assertFalse(cps.is_excluded("x.github_notes"))
        self.assertFalse(cps.is_excluded("docs/.github_template.md"))

    def test_real_source_not_excluded(self):
        self.assertFalse(cps.is_excluded("crawler/cli.py"))

    def test_excluded_path_scan_returns_empty(self):
        # scan_text on an excluded path must never flag (driven by `path`).
        text = "path = '/home/devuser/x'\n"
        self.assertEqual(cps.scan_text("scripts/check_publish_safe.py", text), [])
        self.assertEqual(cps.scan_text(".github/foo.md", text), [])

    def test_tracked_planning_path_reports_real_pii(self):
        # CR-01 regression: a real venv/home path in a tracked, non-excluded
        # planning file IS reported (the exact blind spot CR-01 closed).
        text = "interp = '/home/devuser/.cache/pr-ai-venv/bin/python'\n"
        violations = cps.scan_text(".planning/ROADMAP.md", text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "ABS_PATH")


class TrackedCorporaTests(unittest.TestCase):
    def test_tracked_corpora_path_flagged(self):
        # A tracked path under trial/ is a TRACKED_CORPORA violation (path-based).
        violations = cps.scan_path_name("trial/corpus_new/pdi/foo.md")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "TRACKED_CORPORA")

    def test_non_corpora_path_not_flagged(self):
        self.assertEqual(cps.scan_path_name("crawler/cli.py"), [])


class VaultArtifactTests(unittest.TestCase):
    """VAULT-04: scan_vault_artifact flags vault DB/sidecars, the candidates/
    tree, and vault-subtree render/OCR/report files — with zero false positives."""

    def test_tracked_vault_db_trips_both_categories(self):
        # A tracked personal/candidates/default/vault.sqlite is BOTH a
        # TRACKED_CORPORA (personal/ prefix) and a VAULT_ARTIFACT.
        path = "personal/candidates/default/vault.sqlite"
        corpora = cps.scan_path_name(path)
        vault = cps.scan_vault_artifact(path)
        self.assertEqual(len(corpora), 1)
        self.assertEqual(corpora[0].category, "TRACKED_CORPORA")
        self.assertEqual(len(vault), 1)
        self.assertEqual(vault[0].category, "VAULT_ARTIFACT")

    def test_stray_sqlite_wal_sidecar_flagged(self):
        # A stray build/x.sqlite-wal is a VAULT_ARTIFACT by basename suffix.
        vault = cps.scan_vault_artifact("build/x.sqlite-wal")
        self.assertEqual(len(vault), 1)
        self.assertEqual(vault[0].category, "VAULT_ARTIFACT")

    def test_all_db_sidecar_suffixes_flagged(self):
        for name in ("a.sqlite", "a.sqlite-wal", "a.sqlite-shm",
                     "a.db-wal", "a.db-shm", "vault.sqlite"):
            with self.subTest(name=name):
                vault = cps.scan_vault_artifact("build/" + name)
                self.assertEqual(len(vault), 1, name)
                self.assertEqual(vault[0].category, "VAULT_ARTIFACT")

    def test_candidates_segment_anywhere_flagged(self):
        # A stray 'candidates' segment outside personal/ is still flagged.
        vault = cps.scan_vault_artifact("some/candidates/page-0001.png")
        self.assertEqual(len(vault), 1)
        self.assertEqual(vault[0].category, "VAULT_ARTIFACT")

    def test_vault_subtree_render_file_flagged(self):
        for path in ("x/rendered/page-1.png", "x/files/raw/abc.pdf",
                     "x/text/doc.txt", "x/output/crs-audit/run-1.md"):
            with self.subTest(path=path):
                vault = cps.scan_vault_artifact(path)
                self.assertEqual(len(vault), 1, path)
                self.assertEqual(vault[0].category, "VAULT_ARTIFACT")

    def test_ordinary_repo_files_not_flagged(self):
        # No false positives: normal repo docs/images/JSON are NOT vault artifacts.
        for path in ("crawler/README.md", "docs/logo.png", "crawler/cli.py",
                     "personal.example/crs-profile.example.yaml",
                     "reports/REPORT.md"):
            with self.subTest(path=path):
                self.assertEqual(cps.scan_vault_artifact(path), [], path)

    def test_excluded_paths_never_vault_flagged(self):
        # Self/test/framework exclusions apply to the vault scan too.
        self.assertEqual(
            cps.scan_vault_artifact("crawler/tests/test_vault.py"), [])
        self.assertEqual(
            cps.scan_vault_artifact(".github/x/candidates/y.sqlite"), [])


class ExitContractTests(unittest.TestCase):
    def test_violations_map_to_nonzero(self):
        # Test 7: integration of the exit-code mapping helper.
        viols = cps.scan_text("crawler/cli.py", "x = '/home/devuser/y'\n")
        self.assertEqual(cps.exit_code(viols), 1)

    def test_clean_maps_to_zero(self):
        self.assertEqual(cps.exit_code([]), 0)


class DecodeForScanTests(unittest.TestCase):
    def test_single_bad_byte_still_scanned(self):
        # WR-03 regression: one stray non-UTF-8 byte must NOT hide the file's
        # text; the abs path on the same blob is still decoded and scannable.
        raw = b"first line\nx = '/home/devuser/y' \xff trailing\n"
        text = cps.decode_for_scan(raw)
        self.assertIsNotNone(text)
        violations = cps.scan_text("crawler/cli.py", text)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].category, "ABS_PATH")

    def test_binary_nul_content_skipped(self):
        # Genuinely binary content (NUL byte) is skipped, returning None.
        self.assertIsNone(cps.decode_for_scan(b"\x00\x01\x02binary"))


class FailClosedTests(unittest.TestCase):
    def test_tracked_files_raises_outside_repo(self):
        # WR-05 regression: git failure must surface as RuntimeError (fail
        # closed), never an uncaught traceback.
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                cps.tracked_files(d)

    def test_repo_root_raises_outside_repo(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            try:
                os.chdir(d)
                with self.assertRaises(RuntimeError):
                    cps.repo_root()
            finally:
                os.chdir(cwd)

    def test_main_returns_nonzero_outside_repo(self):
        # End-to-end: main() must return a non-zero code, not crash.
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            try:
                os.chdir(d)
                self.assertNotEqual(cps.main(), 0)
            finally:
                os.chdir(cwd)


class CwdIndependenceTests(unittest.TestCase):
    def test_same_result_from_root_and_subdir(self):
        # WR-04 regression: results are identical regardless of cwd because the
        # scan is pinned to the repo root.
        probe = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=_SCRIPTS_DIR, capture_output=True, text=True,
        )
        if probe.returncode != 0:
            self.skipTest("not inside a git repository")
        root = probe.stdout.strip()
        script = os.path.join(_SCRIPTS_DIR, "check_publish_safe.py")
        from_root = subprocess.run(
            [sys.executable, script], cwd=root, capture_output=True, text=True
        )
        from_sub = subprocess.run(
            [sys.executable, script],
            cwd=os.path.join(root, "scripts"), capture_output=True, text=True,
        )
        self.assertEqual(from_root.returncode, from_sub.returncode)
        self.assertEqual(from_root.stdout, from_sub.stdout)


if __name__ == "__main__":
    unittest.main()
