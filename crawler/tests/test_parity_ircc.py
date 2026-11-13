"""PROF-01 parity: prove the built-in IRCC profile reproduces the frozen
pre-refactor baseline BYTE-FOR-BYTE, fully offline (no crawl4ai, no network).

Loads the built-in ``ircc`` profile and the frozen golden baseline + fixtures
from plan 13-1, then asserts that the profile-driven pure functions
(``clean_markdown`` / ``normalize_url`` / ``is_excluded``) and the pure
``classify_pages`` classifier reproduce:

  * the cleaned markdown for every fixture page, byte-for-byte;
  * the normalized URL for every fixture URL;
  * the exclusion decision for every fixture URL (incl. the must-NOT-be-excluded
    department-slug URL);
  * the recorded/skipped-stub/skipped-scope/skipped-dup counts AND the ordered
    list of recorded page ids.

The golden files are authoritative and frozen — if any assertion fails, the
shipped IRCC profile has drifted from the engine and MUST be fixed (PROF-01).
"""

from __future__ import annotations

import difflib
import json
import unittest
from pathlib import Path

from crawler.pipeline import PageClassifier, classify_pages
from crawler.profile import (
    clean_markdown,
    is_excluded,
    load_profile,
    normalize_url,
)

_HERE = Path(__file__).parent
_FIXTURES = _HERE / "fixtures"
_GOLDEN = _HERE / "golden"
_CLEAN_DIR = _GOLDEN / "clean"


class IRCCParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile("ircc")
        cls.pages = json.loads(
            (_FIXTURES / "raw_pages.json").read_text(encoding="utf-8")
        )
        cls.urls = json.loads(
            (_FIXTURES / "urls.json").read_text(encoding="utf-8")
        )
        cls.golden_normalized = json.loads(
            (_GOLDEN / "normalized_urls.json").read_text(encoding="utf-8")
        )
        cls.golden_exclusions = json.loads(
            (_GOLDEN / "exclusions.json").read_text(encoding="utf-8")
        )
        cls.golden_classification = json.loads(
            (_GOLDEN / "classification.json").read_text(encoding="utf-8")
        )

    def test_profile_loads(self) -> None:
        self.assertEqual(self.profile.name, "ircc")
        self.assertEqual(self.profile.default_source_type, "pdi")

    def test_cleaned_markdown_byte_for_byte(self) -> None:
        for page in self.pages:
            with self.subTest(page=page["id"]):
                expected = (_CLEAN_DIR / f"{page['id']}.md").read_text(
                    encoding="utf-8"
                )
                actual = clean_markdown(page["raw_md"], self.profile)
                if actual != expected:
                    diff = "".join(
                        difflib.unified_diff(
                            expected.splitlines(keepends=True),
                            actual.splitlines(keepends=True),
                            fromfile=f"golden/clean/{page['id']}.md",
                            tofile=f"ircc-profile:{page['id']}",
                        )
                    )
                    self.fail(
                        f"cleaned markdown mismatch for {page['id']}:\n{diff}"
                    )

    def test_normalized_urls(self) -> None:
        for url in self.urls:
            with self.subTest(url=url):
                self.assertEqual(
                    normalize_url(url, self.profile),
                    self.golden_normalized[url],
                )

    def test_exclusions(self) -> None:
        for url in self.urls:
            with self.subTest(url=url):
                self.assertEqual(
                    is_excluded(url, self.profile),
                    self.golden_exclusions[url],
                )

    def test_classification_counts_match_golden(self) -> None:
        pages = [(p["raw_md"], p["url"]) for p in self.pages]
        counts, recorded_pairs = classify_pages(pages, self.profile)
        for key in ("recorded", "skipped_stub", "skipped_scope", "skipped_dup"):
            with self.subTest(count=key):
                self.assertEqual(counts[key], self.golden_classification[key])
        self.assertEqual(
            len(recorded_pairs), self.golden_classification["recorded"]
        )

    def test_recorded_ids_match_golden(self) -> None:
        classifier = PageClassifier(self.profile)
        recorded_ids: list[str] = []
        for page in self.pages:
            if classifier.classify(page["raw_md"], page["url"]).recorded:
                recorded_ids.append(page["id"])
        self.assertEqual(
            recorded_ids, self.golden_classification["recorded_ids"]
        )
        # The stateful classifier's counts must also equal the golden counts.
        self.assertEqual(
            classifier.counts["recorded"],
            self.golden_classification["recorded"],
        )


if __name__ == "__main__":
    unittest.main()
