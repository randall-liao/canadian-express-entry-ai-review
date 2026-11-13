"""GEN-02 source-inspection gate + config-shim parity (offline, no crawl4ai).

Locks the engine refactor in place by asserting, purely from source TEXT (no
imports of crawl4ai), that:

  * ``crawler/config.py`` and ``crawler/deepcrawl.py`` contain NONE of the moved
    site constants (exclusion list name, dept-slug neutralization, the footer/
    nav/residual regex names, ``wbdisable``, the IRCC label string);
  * ``crawler/deepcrawl.py`` wires the profile (``--profile``, ``load_profile``,
    ``PageClassifier``);
  * the moved constants DO live in ``crawler/profiles/ircc.yaml``.

Plus a behavioral guarantee that the default-profile shim
(``crawler.config.clean_markdown``) still reproduces the frozen golden baseline
that ``completeness.py`` depends on — byte for byte.

Reading source files as text imports no browser stack, so this runs under a
plain ``python3 -m unittest`` with no crawl4ai and no network.
"""

from __future__ import annotations

import difflib
import json
import unittest
from pathlib import Path

import crawler.config

_HERE = Path(__file__).parent
_CRAWLER = _HERE.parent
_CONFIG = _CRAWLER / "config.py"
_DEEPCRAWL = _CRAWLER / "deepcrawl.py"
_IRCC_YAML = _CRAWLER / "profiles" / "ircc.yaml"
_FIXTURES = _HERE / "fixtures"
_CLEAN_DIR = _HERE / "golden" / "clean"

# Tokens that MUST NOT appear in engine source — they belong in the profile now.
_FORBIDDEN_TOKENS = [
    "EXCLUDE_URL_PATTERNS",
    "immigration-refugees-citizenship",
    "_FOOTER_RE",
    "_NAV_SECTION_RE",
    "_RESIDUAL_LINE_RE",
    "wbdisable",
    "Source: IRCC",
]


def _strip_comment_lines(text: str) -> str:
    """Drop full-line ``#`` comments so the token scan only sees real code."""
    return "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )


class EngineSourceGateTest(unittest.TestCase):
    """GEN-02: no site-specific constants remain in engine source."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config_src = _strip_comment_lines(
            _CONFIG.read_text(encoding="utf-8")
        )
        cls.deepcrawl_src = _strip_comment_lines(
            _DEEPCRAWL.read_text(encoding="utf-8")
        )
        cls.ircc_yaml = _IRCC_YAML.read_text(encoding="utf-8")

    def test_no_site_constants_in_config(self) -> None:
        for token in _FORBIDDEN_TOKENS:
            with self.subTest(token=token):
                self.assertNotIn(token, self.config_src)

    def test_no_site_constants_in_deepcrawl(self) -> None:
        for token in _FORBIDDEN_TOKENS:
            with self.subTest(token=token):
                self.assertNotIn(token, self.deepcrawl_src)

    def test_deepcrawl_wires_profile(self) -> None:
        for token in ("--profile", "load_profile", "PageClassifier"):
            with self.subTest(token=token):
                self.assertIn(token, self.deepcrawl_src)

    def test_config_uses_load_profile(self) -> None:
        self.assertIn("load_profile", self.config_src)

    def test_moved_constants_live_in_ircc_profile(self) -> None:
        # The constants left the engine — prove they reside in the profile.
        for token in ("Source: IRCC", "immigration-refugees-citizenship", "wbdisable"):
            with self.subTest(token=token):
                self.assertIn(token, self.ircc_yaml)


class ConfigShimParityTest(unittest.TestCase):
    """The default-profile shim still reproduces the frozen golden baseline."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = json.loads(
            (_FIXTURES / "raw_pages.json").read_text(encoding="utf-8")
        )

    def test_shim_clean_markdown_matches_golden(self) -> None:
        for page in self.pages:
            with self.subTest(page=page["id"]):
                expected = (_CLEAN_DIR / f"{page['id']}.md").read_text(
                    encoding="utf-8"
                )
                actual = crawler.config.clean_markdown(page["raw_md"])
                if actual != expected:
                    diff = "".join(
                        difflib.unified_diff(
                            expected.splitlines(keepends=True),
                            actual.splitlines(keepends=True),
                            fromfile=f"golden/clean/{page['id']}.md",
                            tofile=f"config-shim:{page['id']}",
                        )
                    )
                    self.fail(
                        f"config shim cleaned markdown mismatch for "
                        f"{page['id']}:\n{diff}"
                    )


if __name__ == "__main__":
    unittest.main()
