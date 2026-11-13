"""Freeze / reproduce the parity baseline from the built-in IRCC profile.

One-shot baseline generator (NOT a unittest — the filename has no ``test_``
prefix so ``unittest discover`` ignores it). It records, byte-for-byte, how the
engine cleans markdown, normalizes URLs, decides URL exclusion, and classifies
pages into recorded/skipped counts over offline fixtures.

The site-specific rules now live entirely in the built-in IRCC profile
(``crawler/profiles/ircc.yaml``); this script loads them via
``load_profile("ircc")`` and applies the crawl4ai-free pure functions in
``crawler.profile`` plus the shared ``crawler.pipeline`` classifier (the single
source of truth for the record/skip decision order). It imports NO crawl4ai, so
it runs under a plain system Python.

The committed golden files are the frozen authoritative baseline. Re-running
this script is for HISTORICAL REPRODUCTION ONLY — it must reproduce the existing
golden files byte-for-byte and must not be used to "retune" them::

    python crawler/tests/capture_reference.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running directly as a script (``python3 crawler/tests/capture_reference.py``)
# from the repo root: ensure the repo root is importable so ``crawler`` resolves.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from crawler.pipeline import PageClassifier
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


def main() -> int:
    _CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    # The IRCC profile is the source of truth for all site-specific rules.
    profile = load_profile("ircc")

    urls = json.loads((_FIXTURES / "urls.json").read_text(encoding="utf-8"))
    pages = json.loads((_FIXTURES / "raw_pages.json").read_text(encoding="utf-8"))

    # 1) Normalized-URL baseline (input -> output) and exclusion baseline.
    normalized = {u: normalize_url(u, profile) for u in urls}
    exclusions = {u: is_excluded(u, profile) for u in urls}

    (_GOLDEN / "normalized_urls.json").write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (_GOLDEN / "exclusions.json").write_text(
        json.dumps(exclusions, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 2) Per-page cleaned markdown baseline (byte-exact).
    for page in pages:
        cleaned = clean_markdown(page["raw_md"], profile)
        (_CLEAN_DIR / f"{page['id']}.md").write_text(cleaned, encoding="utf-8")

    # 3) Replay the record/skip decision loop over the pages IN ORDER using the
    #    shared PageClassifier (the single source of truth for decision order).
    classifier = PageClassifier(profile)
    recorded_ids: list[str] = []
    for page in pages:
        if classifier.classify(page["raw_md"], page["url"]).recorded:
            recorded_ids.append(page["id"])

    classification = {
        "recorded": classifier.counts["recorded"],
        "skipped_stub": classifier.counts["skipped_stub"],
        "skipped_scope": classifier.counts["skipped_scope"],
        "skipped_dup": classifier.counts["skipped_dup"],
        "recorded_ids": recorded_ids,
    }
    (_GOLDEN / "classification.json").write_text(
        json.dumps(classification, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"baseline written -> {_GOLDEN}")
    print(json.dumps(classification))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
