"""Completeness verification + run report.

The previous corpus attempt failed silently: the crawler recorded pages but did
NOT capture all of each page's content, yet reported success. This module guards
against that by independently re-fetching a sample of recorded pages at FULL
fidelity (unfiltered markdown) so an LLM judge can confirm the recorded file is a
complete copy of the live webpage — catching content the crawler's content filter
dropped.

Two stages, run in this order:

1. ``--fetch`` (requires the optional ``crawl`` extra): pick ~10% of the live docs
   and re-download each
   live URL as *unfiltered* markdown into ``<corpus>/completeness/<slug>.live.md``,
   plus ``sample.json`` listing the pairs. This is the ground truth to compare
   against the recorded (content-filtered, then QC-pruned) ``<slug>.md``.

       python -m crawler.completeness \
           --fetch trial/corpus_new/pdi --fraction 0.1

   Then a Gemini "high-thinking" sub-agent reads each pair (+ the doc's eval, to
   know what was *intentionally* pruned) and writes ``<slug>.check.json``:
       {doc, url, coverage_verdict: "complete"|"incomplete",
        missing_sections: [...], explained_by_pruning: bool, notes}

2. ``--report`` (standard Python interpreter): aggregate crawl stats + eval results +
   completeness checks into a human-readable ``<corpus>/REPORT.md``.

       python -m crawler.completeness --report trial/corpus_new/pdi
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from crawler.config import clean_markdown


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1:] if nl != -1 else ""
    return text


def _frontmatter_url(text: str) -> str:
    for line in text.splitlines()[:15]:
        if line.startswith("url:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def live_docs(corpus: Path) -> list[Path]:
    """Recorded docs in the live corpus (excludes the _dropped/ quarantine)."""
    return sorted(p for p in corpus.glob("*.md")
                  if p.name not in {"REPORT.md"} and p.parent.name != "_dropped")


def select_sample(corpus: Path, fraction: float) -> list[Path]:
    """Deterministic, size-stratified ~``fraction`` sample (always the largest doc).

    Larger pages have the most content to silently lose, so the sample spans the
    size distribution from biggest to smallest.
    """
    docs = sorted(live_docs(corpus), key=lambda p: p.stat().st_size, reverse=True)
    if not docs:
        return []
    n = max(1, math.ceil(fraction * len(docs)))
    if n >= len(docs):
        return docs
    step = len(docs) / n
    idx = sorted({min(len(docs) - 1, int(round(i * step))) for i in range(n)})
    return [docs[i] for i in idx]


async def _fetch_full_markdown(urls: list[str]) -> dict[str, str]:
    """Re-fetch each URL as UNFILTERED markdown (no content filter) to capture the
    page in full, then strip only site chrome (so comparison is content-vs-content).
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

    cfg = CrawlerRunConfig(
        markdown_generator=DefaultMarkdownGenerator(options={"ignore_links": True, "body_width": 0}),
        excluded_tags=["script", "style"],
        check_robots_txt=True, page_timeout=60000,
        wait_until="domcontentloaded", stream=False, verbose=False,
    )
    out: dict[str, str] = {}
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as c:
        for url in urls:
            try:
                r = await c.arun(url=url, config=cfg)
                res = r[0] if isinstance(r, list) else r
                raw = getattr(res.markdown, "raw_markdown", "") or ""
                out[url] = clean_markdown(raw)
            except Exception as exc:  # noqa: BLE001 - record the failure, keep going
                out[url] = ""
                print(f"  ! fetch failed {url}: {exc}", file=sys.stderr)
    return out


class NoLiveDocsError(Exception):
    """Raised by ``run_fetch`` when the corpus has no live docs to sample.

    Lets the structured (--json) caller turn this into an ``invalid_input``
    error envelope while the human ``cmd_fetch`` path keeps printing its message
    and returning exit code 2 (both behaviors unchanged).
    """


def run_fetch(corpus: Path, fraction: float) -> dict:
    """Sample ~``fraction`` of live docs, re-fetch them at full fidelity, and
    write ``sample.json`` + ``*.live.md`` — the structured compute core of
    ``cmd_fetch`` (presentation split out per AGENT-01).

    Returns ``{sampled, total_live, fraction, out}``. Raises ``NoLiveDocsError``
    when there is nothing to sample (the human path maps that to "no live docs
    to sample" + exit 2). Files written and the ``asyncio.run`` re-fetch are
    IDENTICAL to the previous inline behavior.
    """
    import asyncio

    sample = select_sample(corpus, fraction)
    if not sample:
        raise NoLiveDocsError("no live docs to sample")
    cdir = corpus / "completeness"

    pairs = []
    for doc in sample:
        url = _frontmatter_url(doc.read_text(encoding="utf-8"))
        pairs.append({"doc": doc.name, "url": url,
                      "live": f"{doc.stem}.live.md", "check": f"{doc.stem}.check.json"})

    fetched = asyncio.run(_fetch_full_markdown([p["url"] for p in pairs if p["url"]]))
    # IN-01: create the completeness/ dir only AFTER the re-fetch succeeds, so a
    # failed run (e.g. crawl4ai missing → ImportError above) leaves no empty
    # artifact directory behind.
    cdir.mkdir(exist_ok=True)
    for p in pairs:
        (cdir / p["live"]).write_text(fetched.get(p["url"], ""), encoding="utf-8")

    total_live = len(live_docs(corpus))
    (cdir / "sample.json").write_text(
        json.dumps({"fraction": fraction, "total_live": total_live,
                    "sampled": len(pairs), "fetched_at": _now(), "pairs": pairs},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    return {"sampled": len(pairs), "total_live": total_live,
            "fraction": fraction, "out": str(cdir)}


def cmd_fetch(corpus: Path, fraction: float) -> int:
    try:
        res = run_fetch(corpus, fraction)
    except NoLiveDocsError:
        print("no live docs to sample", file=sys.stderr)
        return 2
    print(f"sampled {res['sampled']}/{res['total_live']} docs "
          f"(fraction={res['fraction']}); live copies + sample.json -> {res['out']}")
    print("Next: dispatch the Gemini completeness sub-agent (see QC_RUNBOOK.md §6),"
          " then run --report.")
    return 0


def _load_evals(corpus: Path) -> dict[str, dict]:
    out = {}
    for ev in corpus.glob("*.eval.json"):
        try:
            d = json.loads(ev.read_text(encoding="utf-8"))
            out[d.get("doc", ev.name)] = d
        except Exception:  # noqa: BLE001
            pass
    return out


def build_report(corpus: Path) -> dict:
    """Aggregate crawl stats + evals + completeness into ``REPORT.md`` and return
    the structured summary — the compute core of ``cmd_report`` (presentation
    split out per AGENT-01).

    Writes ``<corpus>/REPORT.md`` EXACTLY as before. Returns a dict with a
    machine ``verdict`` (``"pass"``/``"fail"``/``"incomplete"``), ``overall_pass``
    (bool), ``out`` (REPORT.md path str), the human verdict line (``verdict_human``
    for the unchanged stdout print), and the summary counts ``recorded``,
    ``live_docs``, ``passed``, ``failed``, ``drop``, ``incomplete``.
    """
    from crawler import eval_runner

    stats = {}
    sp = corpus / "crawl_stats.json"
    if sp.is_file():
        stats = json.loads(sp.read_text(encoding="utf-8"))

    evals = _load_evals(corpus)
    verdicts = {"keep": 0, "prune": 0, "drop": 0}
    for d in evals.values():
        verdicts[d.get("verdict", "?")] = verdicts.get(d.get("verdict", "?"), 0) + 1

    results = eval_runner.run(corpus, min_relevance=0.4)
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    flagged = [r for r in results if r.quality_flags]

    docs = live_docs(corpus)
    total_chars = sum(len(_strip_frontmatter(p.read_text(encoding="utf-8"))) for p in docs)

    dropped = []
    dlog = corpus / "_dropped" / "dropped.log.json"
    if dlog.is_file():
        dropped = json.loads(dlog.read_text(encoding="utf-8"))

    # Completeness checks
    cdir = corpus / "completeness"
    checks: list[dict] = []
    sample_meta = {}
    if (cdir / "sample.json").is_file():
        sample_meta = json.loads((cdir / "sample.json").read_text(encoding="utf-8"))
    for cf in sorted(cdir.glob("*.check.json")) if cdir.is_dir() else []:
        try:
            checks.append(json.loads(cf.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
    incomplete = [c for c in checks
                  if c.get("coverage_verdict") == "incomplete" and not c.get("explained_by_pruning")]

    # Overall verdict
    completeness_done = bool(sample_meta) and len(checks) >= int(sample_meta.get("sampled", 0))
    overall_pass = not failed and not incomplete and completeness_done
    if overall_pass:
        verdict = "✅ PASS — corpus is complete, in-scope, and groundable."
        verdict_str = "pass"
    elif not completeness_done:
        verdict = "⚠ INCOMPLETE RUN — completeness sub-agent has not checked the sample yet."
        verdict_str = "incomplete"
    else:
        verdict = "❌ FAIL — see findings below; do not use this corpus as-is."
        verdict_str = "fail"

    L: list[str] = []
    L.append(f"# Corpus Build Report\n")
    L.append(f"_Generated {_now()}_\n")
    L.append(f"**Overall: {verdict}**\n")

    L.append("## 1. Run configuration\n")
    if stats:
        L.append(f"- Seed: `{stats.get('seed','?')}`")
        L.append(f"- Source type: `{stats.get('source_type','?')}`  |  Depth: "
                 f"{stats.get('depth','?')}  |  Max pages: {stats.get('max_pages','?')}  |  "
                 f"Include: `{stats.get('include_pattern','?')}`")
        L.append(f"- Crawled: {stats.get('crawl_date','?')}\n")
    else:
        L.append("- (crawl_stats.json missing)\n")

    L.append("## 2. Crawl\n")
    if stats:
        L.append(f"- Recorded pages: **{stats.get('recorded','?')}**")
        L.append(f"- Skipped — stub: {stats.get('skipped_stub','?')}, "
                 f"out-of-scope: {stats.get('skipped_scope','?')}, "
                 f"duplicate URL/content: {stats.get('skipped_dup','?')}\n")

    L.append("## 3. Corpus after QC\n")
    L.append(f"- Live documents: **{len(docs)}**  ({total_chars:,} content chars)")
    L.append(f"- Verdicts: keep={verdicts.get('keep',0)}, prune={verdicts.get('prune',0)}, "
             f"drop={verdicts.get('drop',0)}")
    L.append(f"- Quarantined (drop): {len(dropped)}"
             + (f" → {', '.join(d['doc'] for d in dropped)}" if dropped else "") + "\n")

    L.append("## 4. Eval QC gate\n")
    L.append(f"- {len(results)} docs — **{len(passed)} passed, {len(failed)} failed**, "
             f"{len(flagged)} quality-flagged.")
    if failed:
        L.append("- Failures:")
        for r in failed:
            L.append(f"  - ✗ `{r.doc}` ({', '.join(r.failures)})")
    L.append("")

    L.append("## 5. Completeness audit (independent re-fetch)\n")
    if not sample_meta:
        L.append("- Not run. Execute `--fetch` then the Gemini completeness sub-agent.\n")
    else:
        L.append(f"- Sampled **{sample_meta.get('sampled')}/{sample_meta.get('total_live')}** "
                 f"live docs (fraction={sample_meta.get('fraction')}); re-fetched at full "
                 f"fidelity and judged by a Gemini high-thinking agent.")
        L.append(f"- Checks completed: {len(checks)}/{sample_meta.get('sampled')}")
        if checks:
            L.append("\n| Document | Coverage | Explained by pruning | Notes |")
            L.append("|---|---|---|---|")
            for c in sorted(checks, key=lambda x: x.get("doc", "")):
                miss = c.get("notes", "") or "; ".join(c.get("missing_sections", []) or [])
                L.append(f"| `{c.get('doc','?')}` | {c.get('coverage_verdict','?')} | "
                         f"{c.get('explained_by_pruning','-')} | {miss[:120]} |")
        if incomplete:
            L.append(f"\n- ⚠ **{len(incomplete)} doc(s) judged INCOMPLETE** (content the crawler "
                     "missed, not explained by intentional pruning):")
            for c in incomplete:
                L.append(f"  - `{c.get('doc')}`: {c.get('notes','')}")
        else:
            L.append("\n- ✅ Every sampled doc is a complete capture of its live page "
                     "(allowing for intentional out-of-scope pruning).")
        L.append("")

    L.append("## 6. How to read this report\n")
    L.append("- **Crawl** confirms pages were discovered and out-of-scope/dup pages excluded.")
    L.append("- **Eval QC** confirms each kept doc satisfies its grounding contract "
             "(required facts present, pruned content absent).")
    L.append("- **Completeness audit** is the key anti-regression check: it independently "
             "re-downloads a sample at full fidelity and confirms the crawler did not silently "
             "truncate content. If any doc is INCOMPLETE (unexplained), the crawl is not trustworthy "
             "— re-crawl that tree (raise depth/relax the content filter) before using the corpus.\n")

    out_path = corpus / "REPORT.md"
    out_path.write_text("\n".join(L), encoding="utf-8")
    return {
        "verdict": verdict_str,
        "verdict_human": verdict,
        "overall_pass": overall_pass,
        "out": str(out_path),
        "recorded": stats.get("recorded") if stats else None,
        "live_docs": len(docs),
        "passed": len(passed),
        "failed": len(failed),
        "drop": verdicts.get("drop", 0),
        "incomplete": len(incomplete),
    }


def cmd_report(corpus: Path) -> int:
    summary = build_report(corpus)
    print(f"wrote {summary['out']}")
    print(summary["verdict_human"])
    return 0 if summary["overall_pass"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Completeness verification + run report.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fetch", metavar="CORPUS_DIR",
                   help="sample ~fraction of live docs and re-fetch them at full fidelity")
    g.add_argument("--report", metavar="CORPUS_DIR",
                   help="aggregate stats/evals/completeness into REPORT.md")
    p.add_argument("--fraction", type=float, default=0.1)
    args = p.parse_args(argv)

    if args.fetch:
        return cmd_fetch(Path(args.fetch), args.fraction)
    return cmd_report(Path(args.report))


if __name__ == "__main__":
    raise SystemExit(main())
