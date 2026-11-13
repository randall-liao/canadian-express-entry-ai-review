"""Offline cross-family duplicate-audit module (Phase 20 — DUP/CLEAN/RPT).

This is a **read-only** corpus analysis tool. It walks every corpus family,
finds documents that duplicate one another *across* families (which the
crawler's within-run dedup never catches), groups them into clusters via three
distinct signals (exact body hash, normalized source URL, high text overlap),
names one canonical copy to keep per cluster, and emits a shareable keep/delete
report. It touches **nothing** inside ``corpus/`` (Success Criterion 5).

Run it standalone (it is deliberately NOT wired into the ``corpus-crawler``
subparser — productization is DUP-05/06, explicitly out of scope)::

    python -m crawler.dupaudit corpus/
    python -m crawler.dupaudit corpus/ --json
    python -m crawler.dupaudit corpus/ --overlap-threshold 0.95 --out reports/

Reports are written OUTSIDE any family dir (Plan 03 writes them):
    reports/duplicate-audit.md    (human report, RPT-01/02)
    reports/duplicate-audit.json  (machine sidecar)

Design constraints:
* OFFLINE — no ``crawl4ai`` import, no network, no browser.
* Dependency-light — stdlib + already-present ``pyyaml`` only. No new packages.
* Reuse the repo's tested primitives so the audit's duplicate definition stays
  consistent with how the corpus was ingested:
    - body hash:        mirrors ``crawler/pipeline.py:115`` (sha1 over cleaned md)
    - URL canonical:    ``crawler.profile.normalize_url``
    - QC "passed":      ``crawler.eval_runner.check_doc(...).passed``
    - share-safety:     ``scripts/check_publish_safe.py:scan_text``
    - --json envelope:  ``crawler.contract.envelope`` / ``emit``

NOTE TO IMPLEMENTER (threat T-20-02, Tampering): when ``parse_doc`` parses a
document's YAML frontmatter, it MUST use ``yaml.safe_load`` ONLY — never
``yaml.load`` — so a malicious corpus file cannot trigger arbitrary object
construction. Frontmatter is semi-trusted local input.

This module is the *contract* for Phase 20: dataclasses + typed stubs. Only the
two trivial primitives (``body_of`` / ``body_hash``) are implemented here.
Detection / clustering / canonical-selection / report logic is implemented in
Plans 02 and 03 against the failing (RED) test suite this contract enables.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterator, Sequence

# pyyaml is already a project dependency; the implementer parses frontmatter with
# yaml.safe_load ONLY (never yaml.load) — see module docstring, threat T-20-02.
import yaml

from crawler.eval_runner import check_doc
from crawler.profile import load_profile, normalize_url


# --------------------------------------------------------------------------- #
# Implemented primitives (trivial — mirror the crawler's exact-dup definition)
# --------------------------------------------------------------------------- #

def body_of(text: str) -> str:
    """Return *text* minus its YAML frontmatter block.

    Mirrors ``crawler/eval_runner.py:43`` ``_strip_frontmatter``: the on-disk
    body (file minus the leading ``---…---`` block) IS the ``cleaned_md`` the
    crawler recorded, so hashing it reproduces the crawler's dedup digest.
    """
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1:] if nl != -1 else ""
    return text


def body_hash(text: str) -> str:
    """sha1 of the frontmatter-stripped body.

    Matches ``crawler/pipeline.py:115``::

        digest = hashlib.sha1(md.encode("utf-8")).hexdigest()
    """
    return hashlib.sha1(body_of(text).encode("utf-8")).hexdigest()


def _frontmatter_of(text: str) -> str:
    """Return the raw YAML frontmatter block (between the leading ``---`` pair).

    Mirrors the same split as :func:`body_of`: the block delimited by the opening
    ``---`` and the closing ``\\n---``. Returns ``""`` when no frontmatter exists.
    """
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end]
    return ""


# --------------------------------------------------------------------------- #
# Dataclasses (the data contract Plans 02/03 populate)
# --------------------------------------------------------------------------- #

@dataclass
class Doc:
    """One live corpus document, parsed for audit."""

    path: Path
    relpath: str
    family: str
    url: str
    title: str
    body: str
    body_hash: str
    body_len: int
    passed_qc: bool


@dataclass
class Cluster:
    """A group of ≥2 docs judged duplicates of one another."""

    members: list[int]
    signals: set[str]
    canonical_idx: int


@dataclass
class AuditResult:
    """The full audit outcome: live-doc count, clusters, per-signal edge tallies."""

    live_docs: int
    clusters: list[dict]
    exact: int
    url: int
    overlap: int


# --------------------------------------------------------------------------- #
# Enumeration + parsing (STUBS — implemented in Plan 02)
# --------------------------------------------------------------------------- #

def live_docs(corpus: Path) -> Iterator[tuple[Path, str]]:
    """Yield ``(path, text)`` for each live corpus doc (the 752-filter).

    Excludes ``_dropped/`` and ``completeness/`` subtrees, ``REPORT.md``,
    ``*.live.md`` captures, and any ``.md`` without YAML frontmatter.

    Enumeration is confined to the resolved corpus root (threat T-20-01): we walk
    only via ``rglob`` within the given directory and never dereference a path
    taken from file content.
    """
    root = Path(corpus).resolve()
    for p in root.rglob("*.md"):
        parts = set(p.parts)
        if "_dropped" in parts or "completeness" in parts:
            continue
        if p.name == "REPORT.md" or p.name.endswith(".live.md"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):  # drop generated artifacts w/o frontmatter
            continue
        yield p, text


def parse_doc(path: Path, text: str, profile, corpus_root: Path) -> Doc:
    """Build a :class:`Doc` from a file's path/text.

    Parses frontmatter with ``yaml.safe_load`` ONLY (threat T-20-02), normalizes
    the source URL via ``crawler.profile.normalize_url``, and resolves QC-passed
    via ``crawler.eval_runner.check_doc`` against either ``<doc>.md.eval.json`` or
    ``<stem>.eval.json`` (missing eval → ``passed_qc=False``).
    """
    # Frontmatter — safe_load ONLY (never yaml.load): semi-trusted local input.
    meta = yaml.safe_load(_frontmatter_of(text)) or {}
    if not isinstance(meta, dict):
        meta = {}
    raw_url = str(meta.get("url", "") or "")
    title = str(meta.get("title", "") or "")
    url = normalize_url(raw_url, profile) if raw_url else ""

    body = body_of(text)
    relpath = path.resolve().relative_to(Path(corpus_root).resolve()).as_posix()
    family = relpath.split("/", 1)[0]

    # passed_qc — locate the eval sibling under BOTH naming forms (Pitfall 5).
    passed_qc = False
    for cand in (path.name + ".eval.json", path.stem + ".eval.json"):
        eval_path = path.with_name(cand)
        if eval_path.is_file():
            passed_qc = check_doc(path, eval_path, min_relevance=0.4).passed
            break

    return Doc(
        path=path,
        relpath=relpath,
        family=family,
        url=url,
        title=title,
        body=body,
        body_hash=body_hash(text),
        body_len=len(body),
        passed_qc=passed_qc,
    )


# --------------------------------------------------------------------------- #
# Detectors — three distinct signals (STUBS — implemented in Plan 02)
# --------------------------------------------------------------------------- #

def exact_edges(docs: list[Doc]) -> list[tuple[int, int]]:
    """DUP-01: index pairs whose body hashes are identical."""
    groups: dict[str, list[int]] = defaultdict(list)
    for i, d in enumerate(docs):
        groups[d.body_hash].append(i)
    edges: list[tuple[int, int]] = []
    for members in groups.values():
        if len(members) >= 2:
            for k in range(1, len(members)):
                edges.append((members[0], members[k]))
    return edges


def url_edges(docs: list[Doc]) -> list[tuple[int, int]]:
    """DUP-02: index pairs sharing the same normalized source URL."""
    groups: dict[str, list[int]] = defaultdict(list)
    for i, d in enumerate(docs):
        if not d.url:  # skip docs with no/empty URL
            continue
        groups[d.url].append(i)
    edges: list[tuple[int, int]] = []
    for members in groups.values():
        if len(members) >= 2:
            for k in range(1, len(members)):
                edges.append((members[0], members[k]))
    return edges


def overlap_edges(docs: list[Doc], threshold: float = 0.95) -> list[tuple[int, int]]:
    """DUP-03: index pairs whose body text overlap ratio ≥ *threshold*.

    Length-bucket blocking + ``real_quick_ratio``/``quick_ratio`` prefilter over
    ``difflib.SequenceMatcher`` (autojunk=False); see RESEARCH Pattern 3.
    """
    # Sort indices by body length so partners only ever get longer (length block).
    order = sorted(range(len(docs)), key=lambda i: docs[i].body_len)
    edges: list[tuple[int, int]] = []
    for a in range(len(order)):
        i = order[a]
        li = docs[i].body_len
        for b in range(a + 1, len(order)):
            j = order[b]
            if docs[j].body_len > li * 1.06:  # ratio ≥ threshold impossible beyond band
                break
            sm = SequenceMatcher(None, docs[i].body, docs[j].body, autojunk=False)
            if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
                continue
            if sm.ratio() >= threshold:
                edges.append((i, j))
    return edges


# --------------------------------------------------------------------------- #
# Clustering (STUBS — implemented in Plan 02)
# --------------------------------------------------------------------------- #

class UF:
    """Stdlib union-find for connected components (DUP-04)."""

    def __init__(self, n: int) -> None:
        self.p = list(range(n))

    def find(self, x: int) -> int:
        # Path-halving: point each node to its grandparent while ascending.
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.p[self.find(a)] = self.find(b)


def cluster(n: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    """DUP-04: union *edges* over ``n`` nodes; return components of size ≥2."""
    uf = UF(n)
    for i, j in edges:
        uf.union(i, j)
    comps: dict[int, list[int]] = defaultdict(list)
    for idx in range(n):
        comps[uf.find(idx)].append(idx)
    return [sorted(members) for members in comps.values() if len(members) >= 2]


def cluster_signals(
    components: list[list[int]],
    edges_by_signal: dict[str, list[tuple[int, int]]],
) -> list[set[str]]:
    """For each component, the set of detector names whose edges fell inside it.

    ``edges_by_signal`` maps ``"exact"``/``"url"``/``"overlap"`` → that detector's
    edge list. Producer for :attr:`Cluster.signals` (Plan 02), so the ``signals``
    assertion in ``TestCluster`` is satisfiable in Wave 2 before ``audit``
    assembles full :class:`Cluster` records in Plan 03.
    """
    result: list[set[str]] = []
    for members in components:
        member_set = set(members)
        sigs: set[str] = set()
        for name, edges in edges_by_signal.items():
            if any(i in member_set and j in member_set for i, j in edges):
                sigs.add(name)
        result.append(sigs)
    return result


# --------------------------------------------------------------------------- #
# Canonical selection (STUB — implemented in Plan 02)
# --------------------------------------------------------------------------- #

def select_canonical(members: list[Doc]) -> tuple[int, dict[int, str]]:
    """CLEAN-01: pick the canonical member + per-member reason string.

    Deterministic rank: passed-QC first, then longest cleaned body, then
    lexicographically smallest path (total order — no run-to-run flips).
    Returns ``(canonical_index_into_members, {member_index: reason})``.
    """
    def rank_key(m: Doc):
        # Negated ordinals make the lexicographically SMALLEST relpath the LARGEST
        # key, so a single ``max`` yields the full total order in one pass.
        return (m.passed_qc, m.body_len, tuple(-ord(c) for c in m.relpath))

    canon = max(range(len(members)), key=lambda i: rank_key(members[i]))
    winner = members[canon]

    reasons: dict[int, str] = {}
    for i, m in enumerate(members):
        if i == canon:
            qc = "passed QC" if m.passed_qc else "no QC eval"
            reasons[i] = (
                f"kept: {qc} and longest cleaned body ({m.body_len:,} chars)"
            )
        elif winner.passed_qc and not m.passed_qc:
            reasons[i] = "delete: no QC eval"
        elif m.body_len < winner.body_len:
            reasons[i] = "delete: shorter body"
        else:
            reasons[i] = "delete: later relpath (lexicographic tie-break)"
    return canon, reasons


# --------------------------------------------------------------------------- #
# Orchestration + rendering (STUBS — implemented in Plan 03)
# --------------------------------------------------------------------------- #

def audit(corpus: Path, overlap_threshold: float = 0.95) -> AuditResult:
    """Run the full read-only audit pipeline over *corpus*.

    enumerate (:func:`live_docs`) → parse (:func:`parse_doc`) → three detectors
    (:func:`exact_edges` / :func:`url_edges` / :func:`overlap_edges`) → union-find
    (:func:`cluster`) → canonical selection (:func:`select_canonical`). Assembles
    one cluster record per connected component (members carry
    relpath/family/url/decision/reason, plus the component's canonical + signals),
    and counts ``exact``/``url``/``overlap`` as the number of *clusters* whose
    contributing signal set includes that detector. Strictly read-only over
    ``corpus/`` (Success Criterion 5): it only reads files and writes nothing.
    """
    corpus_root = Path(corpus).resolve()
    # The on-disk corpus is the IRCC site; url normalization must match ingest.
    profile = load_profile("ircc")

    docs: list[Doc] = [
        parse_doc(p, text, profile, corpus_root)
        for p, text in live_docs(corpus_root)
    ]

    edges_by_signal: dict[str, list[tuple[int, int]]] = {
        "exact": exact_edges(docs),
        "url": url_edges(docs),
        "overlap": overlap_edges(docs, threshold=overlap_threshold),
    }
    all_edges: list[tuple[int, int]] = [
        edge for edges in edges_by_signal.values() for edge in edges
    ]

    components = cluster(len(docs), all_edges)
    signals_per_component = cluster_signals(components, edges_by_signal)

    clusters: list[dict] = []
    exact = url = overlap = 0
    for members_idx, signals in zip(components, signals_per_component):
        member_docs = [docs[i] for i in members_idx]
        canon_local, reasons = select_canonical(member_docs)

        members: list[dict] = []
        for local_i, d in enumerate(member_docs):
            members.append({
                "relpath": d.relpath,
                "family": d.family,
                "url": d.url,
                "decision": "keep" if local_i == canon_local else "delete",
                "reason": reasons[local_i],
            })

        clusters.append({
            "signals": sorted(signals),
            "canonical": member_docs[canon_local].relpath,
            "size": len(member_docs),
            "members": members,
        })

        if "exact" in signals:
            exact += 1
        if "url" in signals:
            url += 1
        if "overlap" in signals:
            overlap += 1

    return AuditResult(
        live_docs=len(docs),
        clusters=clusters,
        exact=exact,
        url=url,
        overlap=overlap,
    )


# Stable, human-readable labels for the three detector signals.
_SIGNAL_LABELS = {
    "exact": "exact body hash",
    "url": "normalized source URL",
    "overlap": "high text overlap",
}


def _render_member_line(m: dict) -> str:
    """One markdown bullet for a cluster member (relpath/family/url + decision)."""
    decision = m["decision"].upper()  # KEEP | DELETE
    url = m["url"] or "(no source url)"
    return (
        f"  - **{decision}** `{m['relpath']}` "
        f"(family: {m['family']}, url: {url}) — {m['reason']}"
    )


def _render_cluster_block(idx: int, cluster: dict) -> list[str]:
    """Render one cluster as a titled markdown block."""
    sig_labels = ", ".join(_SIGNAL_LABELS.get(s, s) for s in cluster["signals"])
    lines = [
        f"### Cluster {idx} — {cluster['size']} members "
        f"(signals: {sig_labels})",
        "",
        f"Canonical (keep): `{cluster['canonical']}`",
        "",
    ]
    lines.extend(_render_member_line(m) for m in cluster["members"])
    lines.append("")
    return lines


def render_markdown(result: AuditResult) -> str:
    """RPT-01/02: render the human-readable markdown report.

    Mirrors the repo's ``REPORT.md`` style (numbered ``##`` sections). Presents
    EXACT-content clusters, then URL clusters, then overlap-only clusters in
    clearly separated sections; each member shows its corpus-relative path,
    family, source URL, KEEP/DELETE decision, and a reason. Uses ONLY
    corpus-relative paths and frontmatter source URLs — never absolute paths —
    so the rendered text passes ``check_publish_safe.scan_text`` (RPT-03).
    """
    # Partition clusters so each appears in exactly one section.
    exact_clusters = [c for c in result.clusters if "exact" in c["signals"]]
    url_clusters = [
        c for c in result.clusters
        if "url" in c["signals"] and "exact" not in c["signals"]
    ]
    overlap_only = [
        c for c in result.clusters if set(c["signals"]) == {"overlap"}
    ]

    L: list[str] = []
    L.append("# Cross-Family Duplicate Audit\n")
    L.append(
        "Read-only audit of cross-family duplicate documents (Phase 20). This "
        "report names one canonical copy to keep per cluster and proposes "
        "deletions; it makes NO changes to the corpus.\n"
    )

    L.append("## 1. Summary\n")
    L.append(f"- Live documents analyzed: **{result.live_docs}**")
    L.append(f"- Exact-content clusters: **{result.exact}**")
    L.append(f"- Same-URL clusters: **{result.url}**")
    L.append(f"- High-overlap clusters: **{result.overlap}**")
    total = len(result.clusters)
    L.append(f"- Total duplicate clusters: **{total}**\n")

    L.append("## 2. Exact-content duplicate clusters\n")
    if exact_clusters:
        L.append(
            "These clusters share a byte-identical cleaned body (same sha1) "
            "across families.\n"
        )
        for i, c in enumerate(exact_clusters, start=1):
            L.extend(_render_cluster_block(i, c))
    else:
        L.append("_None._\n")

    L.append("## 3. Same-URL duplicate clusters\n")
    if url_clusters:
        L.append(
            "These clusters resolve to the same normalized source URL but were "
            "not byte-identical.\n"
        )
        for i, c in enumerate(url_clusters, start=1):
            L.extend(_render_cluster_block(i, c))
    else:
        L.append("_None._\n")

    L.append("## 4. High-overlap (near-duplicate) clusters\n")
    if overlap_only:
        L.append(
            "These clusters were grouped solely by high text-overlap "
            "similarity; review before deletion (Phase 21).\n"
        )
        for i, c in enumerate(overlap_only, start=1):
            L.extend(_render_cluster_block(i, c))
    else:
        L.append("_None._\n")

    return "\n".join(L) + "\n"


def render_json(result: AuditResult) -> dict:
    """RPT-01/02: render the machine-readable JSON sidecar payload.

    Returns a plain ``dict`` (``json.dumps``-able) carrying the per-signal counts
    and the full ``clusters`` list, where each cluster records its ``signals`` and
    each member carries relpath/family/url/decision/reason. Only corpus-relative
    paths and frontmatter source URLs appear — never absolute paths.
    """
    return {
        "live_docs": result.live_docs,
        "exact": result.exact,
        "url": result.url,
        "overlap": result.overlap,
        "total_clusters": len(result.clusters),
        "clusters": result.clusters,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. ``--json`` emits the ``"audit-duplicates"`` envelope.

    Writes ``duplicate-audit.md`` + ``duplicate-audit.json`` under ``--out``
    (default ``reports/`` — outside any family dir, NEVER under ``corpus/``).
    Gates the rendered markdown report through ``check_publish_safe.scan_text``
    (RPT-03) and FAILS CLOSED — non-zero exit (and ``ok:false`` in ``--json``
    mode) — on any abs-path/secret/PII violation.
    """
    import argparse

    from crawler import contract

    # Import the publish-safety checker as a top-level module without requiring
    # ``scripts`` to be an importable package (mirrors the test convention).
    import sys as _sys
    _scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if _scripts_dir not in _sys.path:
        _sys.path.insert(0, _scripts_dir)
    import check_publish_safe as cps  # RPT-03 share-safety gate

    parser = argparse.ArgumentParser(
        prog="dupaudit",
        description="Offline cross-family duplicate audit (read-only).",
    )
    parser.add_argument("corpus", help="path to the corpus root directory")
    parser.add_argument("--json", action="store_true",
                        help="emit one audit-duplicates JSON envelope on stdout")
    parser.add_argument("--overlap-threshold", type=float, default=0.95,
                        help="text-overlap ratio to cluster near-duplicates")
    parser.add_argument("--out", default="reports",
                        help="output directory for the report (default: reports)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    json_mode = args.json
    corpus_path = Path(args.corpus)

    # --- Input validation -------------------------------------------------- #
    if not corpus_path.is_dir():
        msg = f"corpus path is not a directory: {args.corpus}"
        if json_mode:
            contract.emit(contract.envelope(
                "audit-duplicates",
                error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=_sys.stderr)
        return contract.EXIT_INVALID_INPUT

    try:
        result = audit(corpus_path, overlap_threshold=args.overlap_threshold)
        report_md = render_markdown(result)
        report_json = render_json(result)

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / "duplicate-audit.md"
        json_path = out_dir / "duplicate-audit.json"
        rel_md = md_path.as_posix()
        rel_json = json_path.as_posix()

        # --- RPT-03 share-safety gate: scan the rendered text directly ------ #
        violations = cps.scan_text(rel_md, report_md)
        if violations:
            rendered = "\n".join(v.render() for v in violations)
            err_msg = (
                f"refusing to write report: {len(violations)} publish-safety "
                f"violation(s) in {rel_md}"
            )
            if json_mode:
                contract.emit(contract.envelope(
                    "audit-duplicates",
                    error=(contract.INTERNAL_ERROR, err_msg)))
            else:
                print(rendered, file=_sys.stderr)
                print(f"error: {err_msg}", file=_sys.stderr)
            return contract.EXIT_INTERNAL_ERROR

        # Report is safe — write both renderings to --out (outside corpus/).
        md_path.write_text(report_md, encoding="utf-8")
        json_path.write_text(
            json.dumps(report_json, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

        if json_mode:
            contract.emit(contract.envelope("audit-duplicates", result={
                "verdict": "pass",
                "live_docs": result.live_docs,
                "exact": result.exact,
                "url": result.url,
                "overlap": result.overlap,
                "clusters": result.clusters,
                "report_md": rel_md,
                "report_json": rel_json,
            }))
        else:
            print(
                f"Audited {result.live_docs} live docs: "
                f"{result.exact} exact, {result.url} same-url, "
                f"{result.overlap} high-overlap clusters."
            )
            print(f"Report:      {rel_md}")
            print(f"JSON sidecar: {rel_json}")
        return 0

    except Exception as exc:  # noqa: BLE001 — last-resort machine-readable error
        if json_mode:
            contract.emit(contract.envelope(
                "audit-duplicates",
                error=(contract.INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")))
            return contract.EXIT_INTERNAL_ERROR
        raise


if __name__ == "__main__":
    raise SystemExit(main())
