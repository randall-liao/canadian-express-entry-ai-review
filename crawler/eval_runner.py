"""Eval runner — execute the per-document QC evals the Gemini agent writes.

Each cleaned corpus document gets a sibling eval file ``<doc>.eval.json`` authored
by the QC agent. This runner executes those evals deterministically so document
quality is *enforced*, not just asserted. An eval record looks like::

    {
      "doc": "who-must-submit-immigration-medical-examination.md",
      "url": "https://www.canada.ca/...",
      "relevance_score": 0.95,          // 0-1, relevance to post-ITA EE PR docs
      "verdict": "keep",                // keep | prune | drop
      "quality_flags": [],              // truncated | garbled | duplicate | off-topic
      "summary": "Who must undergo an IME for permanent residence.",
      "must_contain": [                 // groundable facts that MUST be present
        "immigration medical examination", "permanent resident", "R30"
      ],
      "must_not_contain": [             // content that should have been pruned
        "Refugee claimants", "Temporary residence applicants"
      ],
      "grounding_refs": ["R30", "R1(3)", "R30(3)"],
      "notes": "Pruned refugee/temp-resident sections."
    }

Run::

    python -m crawler.eval_runner trial/corpus_new/pdi
    python -m crawler.eval_runner trial/corpus_new/pdi --json --min-relevance 0.5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

VALID_VERDICTS = {"keep", "prune", "drop"}


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1:] if nl != -1 else ""
    return text


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


@dataclass
class DocResult:
    doc: str
    passed: bool
    relevance: float
    verdict: str
    failures: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)


def check_doc(doc_path: Path, eval_path: Path, min_relevance: float) -> DocResult:
    ev = json.loads(eval_path.read_text(encoding="utf-8"))
    body = _norm(_strip_frontmatter(doc_path.read_text(encoding="utf-8"))) if doc_path.is_file() else ""
    failures: list[str] = []

    verdict = ev.get("verdict", "")
    if verdict not in VALID_VERDICTS:
        failures.append(f"invalid verdict: {verdict!r}")

    relevance = float(ev.get("relevance_score", 0) or 0)

    # For documents we keep, enforce the contract; dropped docs are exempt.
    if verdict != "drop":
        if relevance < min_relevance:
            failures.append(f"relevance {relevance:.2f} < min {min_relevance:.2f}")
        for needle in ev.get("must_contain", []):
            if _norm(str(needle)) not in body:
                failures.append(f"missing required: {needle!r}")
        for needle in ev.get("must_not_contain", []):
            if _norm(str(needle)) and _norm(str(needle)) in body:
                failures.append(f"contains forbidden: {needle!r}")
        if not ev.get("summary"):
            failures.append("missing summary")

    return DocResult(
        doc=ev.get("doc", doc_path.name),
        passed=not failures,
        relevance=relevance,
        verdict=verdict or "?",
        failures=failures,
        quality_flags=ev.get("quality_flags", []),
    )


def run(corpus_dir: Path, min_relevance: float) -> list[DocResult]:
    results: list[DocResult] = []
    for eval_path in sorted(corpus_dir.glob("*.eval.json")):
        # Resolve the document from the eval's own ``doc`` field (authoritative),
        # so it works whether the eval is named ``<doc>.eval.json`` or
        # ``<doc>.md.eval.json``. Fall back to the filename if ``doc`` is absent.
        doc_name = ""
        try:
            doc_name = json.loads(eval_path.read_text(encoding="utf-8")).get("doc", "") or ""
        except Exception:  # noqa: BLE001
            pass
        if not doc_name:
            stem = eval_path.name[: -len(".eval.json")]
            doc_name = stem if stem.endswith(".md") else stem + ".md"
        results.append(check_doc(corpus_dir / doc_name, eval_path, min_relevance))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run per-document QC evals.")
    p.add_argument("corpus_dir")
    p.add_argument("--min-relevance", type=float, default=0.4)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    results = run(Path(args.corpus_dir), args.min_relevance)
    if not results:
        print("No .eval.json files found.", file=sys.stderr)
        return 2

    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    flagged = [r for r in results if r.quality_flags]

    if args.json:
        print(json.dumps({
            "total": len(results), "passed": len(passed), "failed": len(failed),
            "failures": [{"doc": r.doc, "failures": r.failures} for r in failed],
            "quality_flagged": [{"doc": r.doc, "flags": r.quality_flags} for r in flagged],
        }, indent=2, ensure_ascii=False))
    else:
        print(f"Eval QC: {len(results)} docs — {len(passed)} passed, {len(failed)} failed, "
              f"{len(flagged)} quality-flagged.\n")
        for r in failed:
            print(f"  ✗ {r.doc} (rel={r.relevance:.2f}, {r.verdict})")
            for f in r.failures:
                print(f"      - {f}")
        for r in flagged:
            print(f"  ⚠ {r.doc}: {', '.join(r.quality_flags)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
