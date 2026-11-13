"""Apply QC verdicts — quarantine ``drop`` documents out of the live corpus.

After the Gemini QC agents write a ``<doc>.eval.json`` for every page and
``crawler.eval_runner`` confirms the evals pass, this step enacts the ``drop``
verdicts: each dropped document (and its eval) is *moved* into a ``_dropped/``
subdirectory and recorded in an audit log, so the live corpus contains only
``keep``/``prune`` documents while nothing is silently deleted.

Run::

    python -m crawler.apply_verdicts trial/corpus_new/pdi
    python -m crawler.apply_verdicts trial/corpus_new/pdi --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def apply(corpus_dir: Path, dry_run: bool = False) -> dict:
    dropped_dir = corpus_dir / "_dropped"
    audit: list[dict] = []

    for eval_path in sorted(corpus_dir.glob("*.eval.json")):
        ev = json.loads(eval_path.read_text(encoding="utf-8"))
        if ev.get("verdict") != "drop":
            continue
        doc_name = ev.get("doc") or eval_path.name.replace(".eval.json", ".md")
        audit.append({
            "doc": doc_name,
            "url": ev.get("url", ""),
            "relevance_score": ev.get("relevance_score"),
            "quality_flags": ev.get("quality_flags", []),
            "reason": ev.get("notes") or ev.get("summary", ""),
            "dropped_at": _now(),
        })
        if dry_run:
            continue
        dropped_dir.mkdir(exist_ok=True)
        for src in (corpus_dir / doc_name, eval_path):
            if src.is_file():
                shutil.move(str(src), str(dropped_dir / src.name))

    # Prune dropped URLs from the manifest so it mirrors the live corpus.
    manifest_path = corpus_dir / "manifest.json"
    if not dry_run and manifest_path.is_file() and audit:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        dropped_urls = {a["url"] for a in audit if a["url"]}
        manifest = {u: m for u, m in manifest.items() if u not in dropped_urls}
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8")

    if not dry_run and audit:
        log = dropped_dir / "dropped.log.json"
        existing = json.loads(log.read_text(encoding="utf-8")) if log.is_file() else []
        log.write_text(json.dumps(existing + audit, indent=2, ensure_ascii=False),
                       encoding="utf-8")

    return {"dropped": len(audit), "audit": audit,
            "live_remaining": len(list(corpus_dir.glob("*.md")))}


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Quarantine drop-verdict docs.")
    p.add_argument("corpus_dir")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    corpus = Path(args.corpus_dir)
    if not corpus.is_dir():
        print(f"not a directory: {corpus}", file=sys.stderr)
        return 2

    res = apply(corpus, dry_run=args.dry_run)
    verb = "would drop" if args.dry_run else "dropped"
    print(f"{verb} {res['dropped']} document(s); "
          f"{res['live_remaining']} remain live in {corpus}.")
    for a in res["audit"]:
        print(f"  - {a['doc']}  (rel={a['relevance_score']})  {a['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
