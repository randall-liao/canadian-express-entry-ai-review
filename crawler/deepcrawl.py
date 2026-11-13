"""Config-driven deep crawler (crawl4ai) — records clean, in-scope content only.

Deep-crawls a content tree with crawl4ai's BFS strategy. All site-specific
behavior (scope exclusion, chrome stripping, URL normalization, the source
label/type) comes from a loaded :class:`~crawler.profile.SiteProfile` — selected
via ``--profile`` (default: the built-in ``ircc`` profile) — so the engine holds
no hardcoded site constants. The shared :class:`~crawler.pipeline.PageClassifier`
makes the record/skip decision, so this crawler's counts equal the offline
parity-tested counts by construction. Output is one clean markdown file per
page (with a small frontmatter) plus a manifest.

Run with your environment with the optional ``crawl`` extra installed::

    python -m crawler.deepcrawl \
        --seed https://www.canada.ca/.../standard-requirements/medical-requirements.html \
        --depth 2 --max-pages 40 --out corpus_new/pdi

(Run from the repo root so the ``crawler`` package is importable.)
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.deep_crawling import (
    BFSDeepCrawlStrategy,
    DomainFilter,
    FilterChain,
    URLPatternFilter,
)
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from crawler.profile import SiteProfile, load_profile, resolve_allowed_domains
from crawler.pipeline import PageClassifier

# Single source of truth for crawl defaults (WR-03). Both ``deepcrawl.main``'s
# argparse and the ``--json`` crawl path in ``crawler.cli`` read these, so the
# json and default-mode crawl paths can never silently diverge if a default
# changes.
DEFAULT_DEPTH = 2
DEFAULT_MAX_PAGES = 40
DEFAULT_PROFILE = "ircc"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    stem = path.rsplit("/", 1)[-1].replace(".html", "") or "index"
    return stem[:80]


def _run_config(depth: int, max_pages: int, allowed_domains: list[str],
                include_pattern: str) -> CrawlerRunConfig:
    chain = FilterChain([
        DomainFilter(allowed_domains=allowed_domains),
        # INCLUDE only: BFS may only follow links within the seed's content tree
        # (keeps it from wandering the global canada.ca nav/footer mega-menu).
        # Out-of-scope families are excluded in Python at record-time (reliable).
        URLPatternFilter(patterns=[include_pattern]),
    ])
    strategy = BFSDeepCrawlStrategy(
        max_depth=depth, max_pages=max_pages, include_external=False, filter_chain=chain,
    )
    return CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        markdown_generator=DefaultMarkdownGenerator(
            options={"ignore_links": True, "body_width": 0},
        ),
        # Scope extraction to the page's <main> content region and DO NOT apply a
        # content filter. PruningContentFilter (fit_markdown) silently drops short
        # list items / low-density lines — real policy content — which broke
        # grounding. <main> gives a complete, lossless capture of the article while
        # excluding the canada.ca nav mega-menu. Links for BFS are discovered from
        # the full page, so deep-crawl link discovery is unaffected.
        target_elements=["main"],
        excluded_tags=["script", "style"],
        check_robots_txt=True,
        page_timeout=60000,
        wait_until="domcontentloaded",
        stream=False,
        verbose=False,
    )


async def crawl(seed: str, depth: int, max_pages: int, out_dir: Path,
                profile: SiteProfile, source_type: str, label: str,
                include_pattern: str | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Config-driven (GEN-01): honor profile.allowed_domains when set, else derive
    # the single allowed domain from the seed's netloc (built-in IRCC behavior).
    allowed_domains = resolve_allowed_domains(profile, seed)
    if not include_pattern:
        # Default: constrain BFS to the seed's parent directory tree.
        parent = urlparse(seed).path.rsplit("/", 2)[-2] if "/" in urlparse(seed).path else ""
        include_pattern = f"*{parent}*" if parent else "*"
    cfg = _run_config(depth, max_pages, allowed_domains, include_pattern)
    manifest: dict[str, dict] = {}
    seen_slugs: set[str] = set()
    # The shared classifier owns the record/skip decision order and dedup state,
    # so deepcrawl's counts equal the parity-tested classifier counts.
    classifier = PageClassifier(profile)

    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as c:
        results = await c.arun(url=seed, config=cfg)
        for r in results:
            if not getattr(r, "success", False):
                continue
            raw_md = getattr(r.markdown, "raw_markdown", "") or getattr(r.markdown, "fit_markdown", "") or ""
            result_url = getattr(r, "url", seed)
            decision = classifier.classify(raw_md, result_url)
            if not decision.recorded:
                continue
            url = decision.url
            md = decision.cleaned_md
            slug = _slug(url)
            base = slug
            i = 1
            while slug in seen_slugs:
                slug = f"{base}-{i}"
                i += 1
            seen_slugs.add(slug)
            title = ""
            meta = getattr(r, "metadata", None) or {}
            if isinstance(meta, dict):
                title = meta.get("title", "") or ""
            front = {
                "url": url, "title": title, "source_type": source_type,
                "crawl_date": _now(), "label": label, "generator": "crawl4ai-deep",
            }
            fm = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}"
                                    for k, v in front.items()) + "\n---\n\n"
            (out_dir / f"{slug}.md").write_text(fm + md, encoding="utf-8")
            front["path"] = f"{slug}.md"
            front["chars"] = len(md)
            manifest[url] = front

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    counts = classifier.counts
    stats = {
        "seed": seed, "depth": depth, "max_pages": max_pages,
        "include_pattern": include_pattern, "source_type": source_type,
        "allowed_domains": allowed_domains, "crawl_date": _now(),
        "recorded": counts["recorded"], "skipped_stub": counts["skipped_stub"],
        "skipped_scope": counts["skipped_scope"], "skipped_dup": counts["skipped_dup"],
        "out": str(out_dir),
    }
    (out_dir / "crawl_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    return stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Config-driven deep crawler (clean, in-scope only).")
    p.add_argument("--seed", required=True)
    p.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    p.add_argument("--out", required=True)
    p.add_argument("--profile", default=DEFAULT_PROFILE,
                   help="built-in profile name or path to a .yaml profile")
    p.add_argument("--source-type", default=None,
                   help="override the profile's default source_type")
    p.add_argument("--include", dest="include_pattern", default=None,
                   help="glob the crawl must stay within (default: seed's parent dir)")
    p.add_argument("--label", default=None,
                   help="override the profile's default source label")
    args = p.parse_args(argv)
    profile = load_profile(args.profile)
    source_type = args.source_type or profile.default_source_type
    label = args.label or profile.default_label
    stats = asyncio.run(crawl(args.seed, args.depth, args.max_pages, Path(args.out),
                              profile, source_type, label, args.include_pattern))
    print(f"recorded={stats['recorded']} skipped_stub={stats['skipped_stub']} "
          f"skipped_scope={stats['skipped_scope']} skipped_dup={stats['skipped_dup']} "
          f"-> {stats['out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
