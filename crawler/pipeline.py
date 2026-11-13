"""Pure, crawl4ai-free page classifier — the single source of truth for the
engine's record/skip decision order (GEN-02).

This module reproduces the CURRENT ``crawler.deepcrawl.crawl`` per-page decision
loop EXACTLY, but as a pure function of ``(raw_md, url)`` pairs and a
``SiteProfile``. By factoring the record/skip logic out of the crawl4ai-bound
crawler, the recorded/skipped counts become verifiable OFFLINE — no live crawl,
no browser stack, no network — which is what makes the PROF-01 counts-parity
test possible (see ``crawler/tests/test_parity_ircc.py``). Plan 13-3 will have
``deepcrawl`` reuse this classifier so the crawler's counts are, by construction,
the counts this module's tests pin to the frozen baseline.

Decision order (verbatim from the current engine), applied per page IN ORDER:

    1. clean      — ``md = clean_markdown(raw_md, profile)``
    2. stub       — if ``len(md) < MIN_CONTENT_CHARS`` -> skipped_stub
    3. normalize  — ``nurl = normalize_url(url, profile)``
    4. scope      — if ``is_excluded(nurl, profile)`` -> skipped_scope
    5. seen-url   — if ``nurl`` already recorded -> skipped_dup
    6. content    — if ``sha1(md)`` already recorded -> skipped_dup
    7. record     — else add to seen sets and record ``(nurl, md)``

Imports ONLY the standard library and ``crawler.profile`` — never ``crawl4ai`` —
so it imports and runs under a plain Python with no browser stack.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from crawler.profile import (
    SiteProfile,
    clean_markdown,
    is_excluded,
    normalize_url,
)

# Below this many cleaned characters a page is a stub/noise and is not recorded.
# This is generic engine policy (not site-specific), mirroring the current
# ``crawler.deepcrawl.MIN_CONTENT_CHARS`` verbatim.
MIN_CONTENT_CHARS = 200


@dataclass(frozen=True)
class ClassifyResult:
    """Outcome of classifying a single page.

    ``decision`` is one of ``"recorded"``, ``"skipped_stub"``,
    ``"skipped_scope"``, ``"skipped_dup"``. For a recorded page ``url`` is the
    normalized URL and ``cleaned_md`` is the cleaned markdown; for a skip both
    may be ``None`` when the skip happened before they were computed.
    """

    decision: str
    url: str | None = None
    cleaned_md: str | None = None

    @property
    def recorded(self) -> bool:
        return self.decision == "recorded"


class PageClassifier:
    """Stateful record/skip classifier over a stream of pages.

    Holds the dedup state (``seen_urls``/``seen_hashes``) and the integer
    counters so a caller can feed pages one at a time (as a live BFS crawl does)
    and read ``.counts`` at the end. The decision order is fixed and matches the
    current engine exactly.
    """

    def __init__(self, profile: SiteProfile) -> None:
        self.profile = profile
        self.seen_urls: set[str] = set()
        self.seen_hashes: dict[str, str] = {}
        self.recorded = 0
        self.skipped_stub = 0
        self.skipped_scope = 0
        self.skipped_dup = 0

    @property
    def counts(self) -> dict[str, int]:
        """Current record/skip tallies as a plain dict."""
        return {
            "recorded": self.recorded,
            "skipped_stub": self.skipped_stub,
            "skipped_scope": self.skipped_scope,
            "skipped_dup": self.skipped_dup,
        }

    def classify(self, raw_md: str, url: str) -> ClassifyResult:
        """Classify one page, updating counters and dedup state in place.

        Mirrors ``crawler.deepcrawl.crawl``'s per-result decision loop exactly.
        """
        # 1) clean
        md = clean_markdown(raw_md, self.profile)
        # 2) stub
        if len(md) < MIN_CONTENT_CHARS:
            self.skipped_stub += 1
            return ClassifyResult("skipped_stub")
        # 3) normalize
        nurl = normalize_url(url, self.profile)
        # 4) scope
        if is_excluded(nurl, self.profile):
            self.skipped_scope += 1
            return ClassifyResult("skipped_scope", url=nurl)
        # 5) seen-url dup
        if nurl in self.seen_urls:
            self.skipped_dup += 1
            return ClassifyResult("skipped_dup", url=nurl)
        # 6) content-hash dup
        digest = hashlib.sha1(md.encode("utf-8")).hexdigest()
        if digest in self.seen_hashes:
            self.skipped_dup += 1
            return ClassifyResult("skipped_dup", url=nurl)
        # 7) record
        self.seen_urls.add(nurl)
        self.seen_hashes[digest] = nurl
        self.recorded += 1
        return ClassifyResult("recorded", url=nurl, cleaned_md=md)


def classify_pages(
    pages: Iterable[tuple[str, str]], profile: SiteProfile
) -> tuple[dict[str, int], list[tuple[str, str]]]:
    """Classify an ordered iterable of ``(raw_md, url)`` pages.

    Runs a fresh :class:`PageClassifier` over the pages IN ORDER and returns
    ``(counts_dict, recorded_pairs)`` where ``recorded_pairs`` is the list of
    ``(normalized_url, cleaned_md)`` for the pages that were recorded.
    """
    classifier = PageClassifier(profile)
    recorded_pairs: list[tuple[str, str]] = []
    for raw_md, url in pages:
        result = classifier.classify(raw_md, url)
        if result.recorded:
            recorded_pairs.append((result.url, result.cleaned_md))
    return classifier.counts, recorded_pairs
