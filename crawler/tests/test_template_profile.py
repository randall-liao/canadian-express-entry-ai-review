"""PROF-02 / GEN-01: the documented copyable template profile loads, validates,
and is genuinely documented (so a user can copy it to target their own source).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from crawler.profile import SiteProfile, load_profile

_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "profiles" / "template.yaml"
)


class TemplateProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Load BY PATH — the way a user would pass their own --profile path.
        cls.profile = load_profile(str(_TEMPLATE_PATH))

    def test_loads_as_site_profile(self) -> None:
        self.assertIsInstance(self.profile, SiteProfile)

    def test_required_fields_present_and_typed(self) -> None:
        p = self.profile
        self.assertIsInstance(p.name, str)
        self.assertTrue(p.name)
        self.assertIsInstance(p.allowed_domains, list)
        self.assertIsInstance(p.exclude_url_patterns, list)
        self.assertIsInstance(p.slug_substitutions, list)
        self.assertIsInstance(p.strip_query_params, list)
        self.assertIsInstance(p.footer_patterns, list)
        self.assertIsInstance(p.nav_section_patterns, list)
        self.assertIsInstance(p.residual_line_patterns, list)
        self.assertIsInstance(p.default_source_type, str)
        self.assertIsInstance(p.default_label, str)
        self.assertTrue(p.default_label)

    def test_regexes_compiled(self) -> None:
        # A successful load already compiled every regex; confirm the compiled
        # lists are present and aligned with their raw counterparts.
        p = self.profile
        self.assertEqual(len(p.footer_regexes), len(p.footer_patterns))
        self.assertEqual(
            len(p.nav_section_regexes), len(p.nav_section_patterns)
        )
        self.assertEqual(
            len(p.residual_line_regexes), len(p.residual_line_patterns)
        )

    def test_file_is_documented(self) -> None:
        raw = _TEMPLATE_PATH.read_text(encoding="utf-8")
        comment_lines = [
            ln for ln in raw.splitlines() if ln.lstrip().startswith("#")
        ]
        self.assertTrue(
            comment_lines,
            "template.yaml must contain explanatory '#' comment lines",
        )


if __name__ == "__main__":
    unittest.main()
