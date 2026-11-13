"""Unit tests for crawler.profile.load_profile and the pure functions (GEN-04).

Stdlib unittest only (no pytest, no crawl4ai). Run from the repo root::

    python -m unittest crawler.tests.test_profile_loader -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

from crawler.profile import (
    ProfileError,
    SiteProfile,
    clean_markdown,
    is_excluded,
    load_profile,
    normalize_url,
    resolve_allowed_domains,
)

# A minimal but complete, valid profile YAML used for the success path. Does NOT
# embed IRCC-specific patterns inside profile.py — they live in the YAML fixture.
_VALID_YAML = textwrap.dedent(
    r"""
    name: testprofile
    allowed_domains:
      - www.example.com
    exclude_url_patterns:
      - "*refugee*"
      - "*citizenship*"
    slug_substitutions:
      - ["immigration-refugees-citizenship", "ircc"]
    strip_query_params:
      - wbdisable
    footer_patterns:
      - '^#{1,6}\s*Page details\b'
    nav_section_patterns:
      - '^#{1,6}\s*(See also|On this page)\s*:?\s*$'
    residual_line_patterns:
      - '^\s*\d{4}-\d{2}-\d{2}\s*$'
    default_source_type: pdi
    default_label: "Source: test profile"
    """
).strip()


def _write_tmp(text: str, suffix: str = ".yaml") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class LoadProfileSuccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp: list[str] = []

    def tearDown(self) -> None:
        for p in self._tmp:
            try:
                os.unlink(p)
            except OSError:
                pass

    def _tmpfile(self, text: str, suffix: str = ".yaml") -> str:
        path = _write_tmp(text, suffix)
        self._tmp.append(path)
        return path

    def test_load_by_path_returns_typed_profile(self) -> None:
        prof = load_profile(self._tmpfile(_VALID_YAML))
        self.assertIsInstance(prof, SiteProfile)
        self.assertEqual(prof.name, "testprofile")
        self.assertEqual(prof.allowed_domains, ["www.example.com"])
        self.assertIn("*refugee*", prof.exclude_url_patterns)
        self.assertEqual(prof.strip_query_params, ["wbdisable"])
        self.assertEqual(prof.default_source_type, "pdi")
        self.assertEqual(prof.default_label, "Source: test profile")

    def test_slug_substitutions_coerced_to_tuples(self) -> None:
        prof = load_profile(self._tmpfile(_VALID_YAML))
        self.assertTrue(prof.slug_substitutions)
        for entry in prof.slug_substitutions:
            self.assertIsInstance(entry, tuple)
            self.assertEqual(len(entry), 2)

    def test_compiled_pattern_lists_present(self) -> None:
        import re

        prof = load_profile(self._tmpfile(_VALID_YAML))
        for compiled in (prof.footer_regexes, prof.nav_section_regexes,
                         prof.residual_line_regexes):
            self.assertTrue(compiled)
            for pat in compiled:
                self.assertIsInstance(pat, re.Pattern)

    def test_pure_functions_use_profile(self) -> None:
        prof = load_profile(self._tmpfile(_VALID_YAML))
        # clean_markdown truncates at footer marker.
        cleaned = clean_markdown(
            "# Title\n\nReal body text here.\n\n## Page details\n\nchrome\n", prof
        )
        self.assertIn("Real body text here.", cleaned)
        self.assertNotIn("chrome", cleaned)
        # is_excluded applies slug substitution then fnmatch.
        self.assertFalse(
            is_excluded(
                "https://www.example.com/immigration-refugees-citizenship/x.html",
                prof,
            )
        )
        self.assertTrue(
            is_excluded("https://www.example.com/services/refugee/claim.html", prof)
        )
        # normalize_url drops fragment, strips listed query params and trailing slash.
        self.assertEqual(
            normalize_url("https://www.example.com/p.html?wbdisable=true#sec", prof),
            "https://www.example.com/p.html",
        )

    def test_normalize_url_query_param_removal(self) -> None:
        # WR-01: stripping a param must never leave a malformed query string.
        prof = load_profile(self._tmpfile(_VALID_YAML))
        base = "https://www.example.com/a.html"
        # sole param -> no query at all
        self.assertEqual(
            normalize_url(f"{base}?wbdisable=true", prof), base
        )
        # first-of-many -> following param promoted behind '?', not '&'
        self.assertEqual(
            normalize_url(f"{base}?wbdisable=true&foo=bar", prof),
            f"{base}?foo=bar",
        )
        # middle -> neighbors stay joined correctly
        self.assertEqual(
            normalize_url(f"{base}?foo=bar&wbdisable=true&baz=qux", prof),
            f"{base}?foo=bar&baz=qux",
        )
        # last -> leading params preserved
        self.assertEqual(
            normalize_url(f"{base}?foo=bar&wbdisable=true", prof),
            f"{base}?foo=bar",
        )
        # no stripped param present -> query left intact
        self.assertEqual(
            normalize_url(f"{base}?foo=bar", prof), f"{base}?foo=bar"
        )

    def test_no_crawl4ai_dependency(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import crawler.profile; "
                    "assert 'crawl4ai' not in sys.modules"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


class LoadProfileFailFastTests(unittest.TestCase):
    """GEN-04: every load/validation failure must fail fast with a clear error."""

    def setUp(self) -> None:
        self._tmp: list[str] = []

    def tearDown(self) -> None:
        for p in self._tmp:
            try:
                os.unlink(p)
            except OSError:
                pass

    def _tmpfile(self, text: str, suffix: str = ".yaml") -> str:
        path = _write_tmp(text, suffix)
        self._tmp.append(path)
        return path

    def test_unknown_builtin_name(self) -> None:
        with self.assertRaisesRegex(ProfileError, r"Unknown profile"):
            load_profile("does-not-exist-xyz")

    def test_builtin_name_with_path_separator_rejected(self) -> None:
        # IN-03: a "name" must not escape the profiles dir via path traversal.
        for bad in ("../../foo", "../ircc", "sub/ircc"):
            with self.subTest(name=bad):
                with self.assertRaisesRegex(ProfileError, r"Unknown profile"):
                    load_profile(bad)

    def test_missing_file_path(self) -> None:
        with self.assertRaisesRegex(ProfileError, r"/no/such/file\.yaml"):
            load_profile("/no/such/file.yaml")

    def test_malformed_yaml(self) -> None:
        bad = "name: testprofile\n  : : not valid yaml : :\n\t- broken\n"
        with self.assertRaisesRegex(ProfileError, r"(?i)yaml"):
            load_profile(self._tmpfile(bad))

    def test_missing_required_field(self) -> None:
        # Drop the required 'name' field.
        without_name = "\n".join(
            ln for ln in _VALID_YAML.splitlines() if not ln.startswith("name:")
        )
        with self.assertRaisesRegex(ProfileError, r"name"):
            load_profile(self._tmpfile(without_name))

    def test_uncompilable_regex(self) -> None:
        bad = _VALID_YAML.replace(
            r"'^#{1,6}\s*Page details\b'", r"'^(unbalanced['"
        )
        with self.assertRaisesRegex(ProfileError, r"footer_patterns"):
            load_profile(self._tmpfile(bad))


class ResolveAllowedDomainsTests(unittest.TestCase):
    """CR-01 (GEN-01): the engine must honor profile.allowed_domains."""

    def setUp(self) -> None:
        self._tmp: list[str] = []

    def tearDown(self) -> None:
        for p in self._tmp:
            try:
                os.unlink(p)
            except OSError:
                pass

    def _tmpfile(self, text: str, suffix: str = ".yaml") -> str:
        path = _write_tmp(text, suffix)
        self._tmp.append(path)
        return path

    def test_nonempty_allowed_domains_is_used(self) -> None:
        # A profile with multiple allowed domains must drive the domain filter,
        # NOT be silently replaced by the seed netloc.
        multi = _VALID_YAML.replace(
            "allowed_domains:\n  - www.example.com",
            "allowed_domains:\n  - www.example.com\n  - cdn.example.com",
        )
        prof = load_profile(self._tmpfile(multi))
        self.assertEqual(prof.allowed_domains, ["www.example.com", "cdn.example.com"])
        resolved = resolve_allowed_domains(
            prof, "https://seed.other-host.org/a/b.html"
        )
        self.assertEqual(resolved, ["www.example.com", "cdn.example.com"])
        # The seed's netloc must NOT leak in when the profile is explicit.
        self.assertNotIn("seed.other-host.org", resolved)

    def test_empty_allowed_domains_falls_back_to_seed_netloc(self) -> None:
        # Empty list -> derive from the seed netloc (preserves IRCC behavior).
        empty = _VALID_YAML.replace(
            "allowed_domains:\n  - www.example.com", "allowed_domains: []"
        )
        prof = load_profile(self._tmpfile(empty))
        self.assertEqual(prof.allowed_domains, [])
        resolved = resolve_allowed_domains(
            prof, "https://www.canada.ca/en/x/y.html"
        )
        self.assertEqual(resolved, ["www.canada.ca"])

    def test_ircc_default_falls_back_to_seed(self) -> None:
        prof = load_profile("ircc")
        self.assertEqual(prof.allowed_domains, [])
        self.assertEqual(
            resolve_allowed_domains(prof, "https://www.canada.ca/a.html"),
            ["www.canada.ca"],
        )


if __name__ == "__main__":
    unittest.main()
