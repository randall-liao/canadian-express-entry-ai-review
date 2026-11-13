"""Offline one-time corpus cleanup — enact the cross-family duplicate audit.

This is the **mutating** counterpart to the read-only :mod:`crawler.dupaudit`
(Phase 20). It consumes the deterministic ``reports/duplicate-audit.json`` that
``dupaudit`` produced and *enacts* the keep/delete decisions frozen in that
report:

* For every cluster member with ``decision == "delete"``, the document is
**MOVED** (never hard-deleted) into its owning family's ``_dropped/``
  quarantine, together with its ``.eval.json`` sibling(s) — exactly mirroring the
  proven ``crawler.apply_verdicts`` quarantine pattern. ``corpus/`` is git-ignored,
so a true hard delete would be **unrecoverable**; the move is the safe analog
  and removes the doc from every "live" count (both ``dupaudit.live_docs`` and
  ``completeness.live_docs`` skip ``_dropped/``).
* **Dry-run by default.** Nothing on disk changes unless ``--apply`` is passed
  (fail-safe — the inverse of ``apply_verdicts``' opt-out ``--dry-run``).
* **Overlap-only clusters are excluded by default.** A cluster whose only signal
  is ``"overlap"`` (text ≥0.95 with no exact/URL edge) is a demonstrated
  false-positive risk over short boilerplate pages (distinct countries / Express
  Entry rounds). Those are processed only behind an explicit ``--include-overlap``
  flag; by default they are reviewed-and-retained.
* After moving, each affected family is **re-validated offline**: the moved doc's
  URL is pruned from the family ``manifest.json``, orphaned ``completeness/``
  sidecars are pruned, and ``crawler.completeness.build_report`` regenerates the
  family ``REPORT.md`` with the decremented live count — all pure-Python, no
  ``crawl4ai`` and no network.

Run standalone::

    python -m crawler.dupclean reports/duplicate-audit.json corpus/
    python -m crawler.dupclean reports/duplicate-audit.json corpus/ --apply
    python -m crawler.dupclean reports/duplicate-audit.json corpus/ --apply --include-overlap

Design constraints (identical to ``dupaudit``):
* OFFLINE — no ``crawl4ai`` import, no network, no browser.
* Dependency-light — stdlib + already-present repo modules only. No new packages.
* NEVER hard-delete a corpus file (no ``unlink``/``remove`` primitive) — removal is
  always a move into ``_dropped/`` (threat T-21-03, Denial-of-recovery).
* Report relpaths are semi-trusted local input: every relpath is passed through
  :func:`confine` before any filesystem move, which rejects absolute paths and
  ``..`` escapes (threat T-21-01, Tampering/Elevation).

This module is the **interface contract** for Phase 21: dataclasses + typed
stubs raising ``NotImplementedError``, plus the trivial ``_now()`` helper. The
detection/move/prune/re-validation logic is implemented in Plans 02-04 against
the failing (RED) test suite this contract enables; Plan 05 runs it against the
real corpus.
"""

from __future__ import annotations

import argparse
import json  # noqa: F401  (used by the implemented move/prune logic in Plans 02-04)
import shutil  # noqa: F401  (move-to-_dropped primitive — Plan 02)
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

# Repo-internal, OFFLINE modules only (no crawl4ai / network):
#   dupaudit       — live_docs/parse_doc/exact_edges/url_edges/cluster (zero-cluster re-check)
#   completeness   — build_report (offline per-family re-validation)
#   profile        — load_profile (manifest key canonicalization)
#   contract       — envelope/emit + EXIT_* codes (--json CLI, wired in Plan 04)
from crawler import dupaudit  # noqa: F401
from crawler.profile import load_profile


def _now() -> str:
    """UTC timestamp for audit-log records (mirrors ``apply_verdicts._now``)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Plan loading (STUB — implemented in Plan 02)
# --------------------------------------------------------------------------- #

def load_plan(report_json: Path, include_overlap: bool = False) -> list[dict]:
    """Load the delete plan from a persisted ``duplicate-audit.json`` (no re-audit).

    Parses the report and returns one target ``dict`` per cluster member with
    ``decision == "delete"``. Each target carries ``relpath`` / ``family`` /
    ``url`` / ``overlap_only``. Overlap-only clusters (``signals == {"overlap"}``)
    are **skipped** unless ``include_overlap`` is True — the default safety gate
    against false-positive deletes over short boilerplate pages.

    The report is consumed VERBATIM: the keep/delete decision and canonical
    selection were frozen by Phase 20's :mod:`crawler.dupaudit` and are never
    recomputed here. Canonical (``decision == "keep"``) members are never
    returned — only delete targets.
    """
    data = json.loads(Path(report_json).read_text(encoding="utf-8"))

    targets: list[dict] = []
    for cluster in data.get("clusters", []):
        overlap_only = set(cluster.get("signals", [])) == {"overlap"}
        # Default safety gate: skip overlap-only clusters unless widened.
        if overlap_only and not include_overlap:
            continue
        canonical = cluster.get("canonical")
        for member in cluster.get("members", []):
            # Read the frozen decision VERBATIM — never recompute canonical.
            if member.get("decision") != "delete":
                continue
            targets.append({
                "relpath": member["relpath"],
                "family": member.get("family")
                or member["relpath"].split("/", 1)[0],
                "url": member.get("url", ""),
                "overlap_only": overlap_only,
                # Carried for the move-boundary keep-canonical guard + audit log.
                "decision": member["decision"],
                "canonical": canonical,
                "reason": member.get("reason", ""),
            })
    return targets


# --------------------------------------------------------------------------- #
# Path-confinement guard (STUB — implemented in Plan 02; threat T-21-01)
# --------------------------------------------------------------------------- #

def confine(corpus_root: Path, relpath: str) -> Path:
    """Resolve ``relpath`` strictly inside ``corpus_root`` or raise ``ValueError``.

    The relpaths originate from a semi-trusted report file and drive filesystem
    moves, so before any move the resolved absolute path MUST be proven to live
    under the resolved corpus root. Raises ``ValueError`` on an absolute path or a
    ``..`` traversal that escapes the corpus tree (threat T-21-01).
    """
    # Defense-in-depth: refuse absolute paths and ``..`` segments up front,
    # before any resolution touches the filesystem.
    rel = Path(relpath)
    if rel.is_absolute():
        raise ValueError(f"refusing absolute relpath: {relpath!r}")
    if ".." in rel.parts:
        raise ValueError(f"refusing '..' traversal in relpath: {relpath!r}")

    root = Path(corpus_root).resolve()
    target = (root / rel).resolve()
    # The resolved target MUST live under the resolved corpus root.
    if target != root and root not in target.parents:
        raise ValueError(
            f"relpath escapes corpus root: {relpath!r} -> {target}")
    return target


# --------------------------------------------------------------------------- #
# Move-to-_dropped (STUB — implemented in Plan 02; threat T-21-03)
# --------------------------------------------------------------------------- #

def move_to_dropped(corpus_root: Path, relpath: str) -> bool:
    """Move one delete target (and its ``.eval.json`` sibling) into ``_dropped/``.

    Moves ``corpus_root/relpath`` into ``<family>/_dropped/<basename>`` plus any
    eval sibling in BOTH naming forms (``<doc>.md.eval.json`` and
    ``<stem>.eval.json``). Idempotent: a target whose live path no longer exists
    is a silent no-op (``is_file`` guard), so re-running ``--apply`` is safe.
    Returns True iff the document itself was moved. NEVER hard-deletes.
    """
    # Path-confinement guard FIRST — refuse escaping relpaths before any move.
    src = confine(corpus_root, relpath)

    # Idempotent no-op: a target whose live path no longer exists is skipped, so
    # re-running --apply is safe (mirrors apply_verdicts' is_file() guard).
    if not src.is_file():
        return False

    family = relpath.split("/", 1)[0]
    dropped_dir = Path(corpus_root) / family / "_dropped"
    dropped_dir.mkdir(parents=True, exist_ok=True)

    # Move the .md plus its eval sibling(s) in BOTH naming forms
    # (``<doc>.md.eval.json`` and ``<stem>.eval.json``); never unlink.
    movables = [src]
    for cand in (src.name + ".eval.json", src.stem + ".eval.json"):
        sibling = src.with_name(cand)
        if sibling.is_file():
            movables.append(sibling)
    for item in movables:
        shutil.move(str(item), str(dropped_dir / item.name))
    return True


# --------------------------------------------------------------------------- #
# Re-validation: manifest + completeness pruning (STUBS — implemented Plan 03)
# --------------------------------------------------------------------------- #

def prune_manifest(corpus_root: Path, family: str, urls: set[str]) -> int:
    """Drop the given normalized ``urls`` from ``<family>/manifest.json``.

    The family manifest is keyed by normalized source URL → page meta. Each moved
    doc's normalized URL is removed so the manifest mirrors the live corpus.
    Returns the number of manifest entries pruned (0 if no manifest exists).

    Mirrors the proven ``apply_verdicts`` manifest-prune pattern (read JSON, drop
    the dropped URLs, rewrite sorted/indented). The report members' URLs were
    already canonicalized via ``profile.normalize_url`` by Phase 20's
    ``dupaudit``, so they match the keys the manifest was written with. No-op if
    the manifest is absent or ``urls`` is empty.
    """
    if not urls:
        return 0
    manifest_path = Path(corpus_root) / family / "manifest.json"
    if not manifest_path.is_file():
        return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    removed = sum(1 for u in manifest if u in urls)
    if not removed:
        return 0
    manifest = {u: m for u, m in manifest.items() if u not in urls}
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8")
    return removed


def prune_completeness_orphans(
    corpus_root: Path, family: str, moved_basenames: set[str]
) -> int:
    """Prune orphaned ``<family>/completeness/`` sidecars for moved docs.

    For each moved document basename, removes its entry from
    ``completeness/sample.json`` (decrementing ``sampled``) and prunes the
    orphaned ``<stem>.live.md`` / ``<stem>.check.json`` capture/sidecar so the
    completeness verdict stays consistent. Returns the count of sidecar
    artifacts pruned.

    NEVER hard-deletes: each orphaned ``.live.md``/``.check.json`` is MOVED into
    the family ``_dropped/`` quarantine (threat T-21-03, Denial-of-recovery), so
    the captures remain recoverable. ``sampled`` is set to the new pair count so
    ``build_report``'s ``completeness_done = len(checks) >= sampled`` invariant
    stays satisfiable. No-op if the family has no ``completeness/sample.json``.
    """
    if not moved_basenames:
        return 0
    cdir = Path(corpus_root) / family / "completeness"
    sample_path = cdir / "sample.json"
    if not cdir.is_dir() or not sample_path.is_file():
        return 0

    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    pairs = sample.get("pairs", [])
    kept_pairs = [p for p in pairs if p.get("doc") not in moved_basenames]
    dropped_pairs = [p for p in pairs if p.get("doc") in moved_basenames]
    if not dropped_pairs:
        return 0

    dropped_dir = Path(corpus_root) / family / "_dropped"

    # Collect the orphaned sidecar filenames from BOTH the pair's recorded
    # ``live``/``check`` fields and the doc-stem derivation, so a pair missing
    # those keys still has its conventional ``<stem>.live.md``/``<stem>.check.json``
    # captures pruned.
    pruned = 0
    for pair in dropped_pairs:
        doc = pair.get("doc", "")
        stem = doc[:-3] if doc.endswith(".md") else doc
        candidates = {
            pair.get("live"), pair.get("check"),
            f"{stem}.live.md", f"{stem}.check.json",
        }
        for name in sorted(c for c in candidates if c):
            # Confine the sidecar path strictly inside the corpus root before
            # any move (threat T-21-01).
            src = confine(corpus_root, f"{family}/completeness/{name}")
            if not src.is_file():
                continue
            dropped_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dropped_dir / src.name))
            pruned += 1

    # Drop the orphaned pairs and keep ``sampled`` consistent with the remainder.
    sample["pairs"] = kept_pairs
    sample["sampled"] = len(kept_pairs)
    sample_path.write_text(
        json.dumps(sample, indent=2, ensure_ascii=False), encoding="utf-8")
    return pruned


def revalidate_family(corpus_root: Path, family: str) -> dict:
    """Re-validate one family offline after its docs were moved.

    Prunes the family manifest + completeness orphans, then regenerates
    ``<family>/REPORT.md`` via :func:`crawler.completeness.build_report` (offline,
    no network). Returns a summary dict with the family name, the refreshed
    ``live_docs`` count, the new ``verdict``, and the prune tallies.

    This is a thin wrapper over the offline ``build_report`` --report path; it
    NEVER invokes the ``--fetch`` (crawl4ai) path and NEVER edits
    ``crawl_stats.json`` — the historical crawl-time ``recorded`` count is left
    untouched; the live count of record is recomputed by ``build_report`` globbing
    the live docs (anti-pattern "edit crawl_stats.recorded" explicitly avoided).
    """
    from crawler import completeness

    summary = completeness.build_report(Path(corpus_root) / family)
    return {
        "family": family,
        "live_docs": summary["live_docs"],
        "verdict": summary["verdict"],
    }


# --------------------------------------------------------------------------- #
# Fast zero-cluster re-check (STUB — implemented in Plan 03; SC2)
# --------------------------------------------------------------------------- #

def recheck_zero_clusters(corpus_root: Path) -> list:
    """Re-enumerate the cleaned live corpus and assert zero exact/URL clusters.

    Runs ONLY the fast detectors (``exact_edges`` + ``url_edges``) over
    :func:`crawler.dupaudit.live_docs` and returns the remaining clusters — an
    empty list proves the high-confidence duplicates are gone. The ``O(n^2)``
    overlap detector is intentionally skipped (it would spuriously re-flag the
    retained overlap-only false positives and is ~9 min over the real corpus).
    """
    root = Path(corpus_root)
    profile = load_profile("ircc")
    # Re-enumerate the cleaned live corpus and re-parse each doc verbatim with
    # Phase 20's primitives so the "duplicate" definition stays identical.
    docs = [dupaudit.parse_doc(p, t, profile, root)
            for p, t in dupaudit.live_docs(root)]
    # FAST detectors ONLY — exact body-hash + normalized-URL edges. The slow
    # O(n^2) text-overlap detector is deliberately NOT called (see docstring).
    edges = dupaudit.exact_edges(docs) + dupaudit.url_edges(docs)
    return dupaudit.cluster(len(docs), edges)


# --------------------------------------------------------------------------- #
# Orchestrator (STUB — implemented in Plan 03/04)
# --------------------------------------------------------------------------- #

def clean(
    corpus_root: Path,
    report_json: Path,
    apply: bool = False,
    include_overlap: bool = False,
) -> dict:
    """Enact the duplicate-audit plan over *corpus_root* (dry-run by default).

    Loads the plan (:func:`load_plan`), and — only when ``apply`` is True — moves
    each delete target into ``_dropped/`` (:func:`move_to_dropped`, guarded by
    :func:`confine`) and re-validates every affected family
    (:func:`revalidate_family`). Returns a summary dict describing the planned /
    enacted moves and per-family re-validation results. With ``apply=False`` the
    filesystem is left byte-identical.
    """
    targets = load_plan(report_json, include_overlap=include_overlap)

    # retained_overlap_only: overlap-only delete targets held back by the default
    # safety gate (0 when --include-overlap widens scope to include them).
    if include_overlap:
        retained_overlap_only = 0
    else:
        full = load_plan(report_json, include_overlap=True)
        retained_overlap_only = sum(1 for t in full if t["overlap_only"])

    # Group planned moves by owning family (the relpath's first segment).
    plan_by_family: dict[str, list[str]] = {}
    for t in targets:
        plan_by_family.setdefault(t["family"], []).append(t["relpath"])
    families = sorted(plan_by_family)

    # ------------------------------------------------------------------- #
    # Dry-run (default): compute the would-move plan; touch NOTHING on disk.
    # The returned ``moved`` is the PLANNED-move count — the SAME key used in
    # apply mode (Plan 05's dry-run gate asserts moved == 10).
    # ------------------------------------------------------------------- #
    if not apply:
        return {
            "apply": False,
            "moved": len(targets),
            "retained_overlap_only": retained_overlap_only,
            "skipped": 0,
            "families": families,
            "plan": plan_by_family,
        }

    # ------------------------------------------------------------------- #
    # Apply: move each delete target into its family's _dropped/ + audit log.
    # ------------------------------------------------------------------- #
    # Snapshot the corpus-wide live count BEFORE any move so the result can
    # report the before/after delta (recomputed by globbing, not from
    # crawl_stats.json — the historical count of record is never touched).
    live_before = sum(1 for _ in dupaudit.live_docs(corpus_root))

    moved = 0
    skipped = 0
    audit_by_family: dict[str, list[dict]] = {}
    for t in targets:
        # Keep-canonical guarantee asserted at the move boundary: load_plan only
        # returns delete members, but assert it here so the invariant is
        # unambiguous (threat T-21-02 — never move a canonical).
        assert t["decision"] == "delete", (
            f"refusing to move non-delete target {t['relpath']!r}")
        if move_to_dropped(corpus_root, t["relpath"]):
            moved += 1
            audit_by_family.setdefault(t["family"], []).append({
                "relpath": t["relpath"],
                "family": t["family"],
                "url": t["url"],
                "reason": t["reason"],
                "overlap_only": t["overlap_only"],
                "dropped_at": _now(),
            })
        else:
            skipped += 1

    # Append the per-family audit trail under each family's _dropped/.
    for family, records in audit_by_family.items():
        log = Path(corpus_root) / family / "_dropped" / "duplicate-clean.log.json"
        existing = (json.loads(log.read_text(encoding="utf-8"))
                    if log.is_file() else [])
        log.write_text(
            json.dumps(existing + records, ensure_ascii=False, indent=2),
            encoding="utf-8")

    # ------------------------------------------------------------------- #
    # Re-validation (Plan 03): after a successful move pass, refresh every
    # derived artifact that still references a moved file. For each TOUCHED
    # family (one with at least one actually-moved doc), prune the moved docs'
    # normalized URLs from manifest.json, prune the orphaned completeness
    # sidecars, then regenerate REPORT.md offline via revalidate_family (which
    # recomputes the live count by globbing). Runs ONLY on touched families and
    # ONLY after a successful move pass.
    # ------------------------------------------------------------------- #
    family_results: list[dict] = []
    for family in sorted(audit_by_family):
        records = audit_by_family[family]
        moved_urls = {r["url"] for r in records if r["url"]}
        moved_basenames = {Path(r["relpath"]).name for r in records}
        pruned_urls = prune_manifest(corpus_root, family, moved_urls)
        prune_completeness_orphans(corpus_root, family, moved_basenames)
        revalidation = revalidate_family(corpus_root, family)
        family_results.append({
            "family": family,
            "verdict": revalidation["verdict"],
            "live_docs": revalidation["live_docs"],
            "pruned_urls": pruned_urls,
            "regenerated_report": True,
        })

    # Recompute the corpus-wide live count AFTER pruning + REPORT regeneration.
    live_after = sum(1 for _ in dupaudit.live_docs(corpus_root))

    return {
        "apply": True,
        "moved": moved,
        "skipped": skipped,
        "retained_overlap_only": retained_overlap_only,
        "live_before": live_before,
        "live_after": live_after,
        "families": family_results,
        "plan": plan_by_family,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point — ``python -m crawler.dupclean <corpus> [flags]``.

    Dry-run by default; ``--apply`` mutates, ``--include-overlap`` widens scope to
    overlap-only clusters. In ``--json`` mode emits EXACTLY ONE
    ``contract.envelope("clean-duplicates", ...)`` line on stdout (all human text
    routed to stderr); in human mode prints a ``would move N / moved N`` summary.

    Inputs are validated before any work: a bad corpus dir or a missing report
    yields the machine-readable ``INVALID_INPUT`` envelope + ``EXIT_INVALID_INPUT``
    (threat T-21-01). After an ``--apply`` run the fast zero-cluster re-check is
    folded into the result and the verdict is ``pass`` iff the re-check is empty
    AND no touched family re-validated to ``fail``.
    """
    import sys as _sys

    from crawler import contract

    # Import the publish-safety checker as a top-level module without requiring
    # ``scripts`` to be an importable package (mirrors dupaudit.py:567-573 — the
    # RPT-03 producer this gate replicates).
    _scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if _scripts_dir not in _sys.path:
        _sys.path.insert(0, _scripts_dir)
    import check_publish_safe as cps  # RPT-03 share-safety gate

    parser = argparse.ArgumentParser(
        prog="dupclean",
        description="Enact the cross-family duplicate-audit plan (move-to-_dropped).",
    )
    parser.add_argument("corpus", help="path to the corpus root directory")
    parser.add_argument("--report", default="reports/duplicate-audit.json",
                        help="path to the duplicate-audit JSON "
                             "(default: reports/duplicate-audit.json)")
    parser.add_argument("--apply", action="store_true",
                        help="actually move files (default: dry-run, no mutation)")
    parser.add_argument("--include-overlap", action="store_true",
                        help="also process risky overlap-only clusters")
    parser.add_argument("--json", action="store_true",
                        help="emit one clean-duplicates JSON envelope on stdout")
    args = parser.parse_args(list(argv) if argv is not None else None)

    json_mode = args.json
    corpus_path = Path(args.corpus)
    report_path = Path(args.report)

    # --- Input validation (before any filesystem work; threat T-21-01) ---- #
    err_msg: str | None = None
    if not corpus_path.is_dir():
        err_msg = f"corpus path is not a directory: {args.corpus}"
    elif not report_path.is_file():
        err_msg = f"duplicate-audit report not found: {args.report}"
    if err_msg is not None:
        if json_mode:
            contract.emit(contract.envelope(
                "clean-duplicates", error=(contract.INVALID_INPUT, err_msg)))
        else:
            print(f"error: {err_msg}", file=_sys.stderr)
        return contract.EXIT_INVALID_INPUT

    try:
        summary = clean(
            corpus_path, report_path,
            apply=args.apply, include_overlap=args.include_overlap,
        )

        moved = summary["moved"]
        retained = summary["retained_overlap_only"]
        families = summary["families"]

        if args.apply:
            # Fold in the fast exact/URL re-check (overlap detector skipped).
            recheck = recheck_zero_clusters(corpus_path)
            recheck_clusters = recheck
            live_before = summary["live_before"]
            live_after = summary["live_after"]
            family_fail = any(
                isinstance(f, dict) and f.get("verdict") == "fail"
                for f in families)
            verdict = "pass" if (not recheck and not family_fail) else "fail"
        else:
            recheck_clusters = None
            live_before = None
            live_after = None
            verdict = "dry-run"

        result = {
            "verdict": verdict,
            "live_before": live_before,
            "live_after": live_after,
            "moved": moved,
            "retained_overlap_only": retained,
            "families": families,
            "recheck_clusters": recheck_clusters,
        }

        # --- RPT-03 share-safety gate: render the to-be-emitted output and scan
        # it BEFORE emitting (mirrors dupaudit.py:614-629). dupclean's shareable
        # surface is its stdout contract output; the in-corpus regenerated
        # REPORT.md files live under the git-ignored local corpus/ and are never
        # shared, so they are intentionally OUT of the gate's scope. Fail CLOSED
        # (emit nothing normal, return EXIT_INTERNAL_ERROR) on any abs-path/
        # secret/PII violation.
        if json_mode:
            rendered = json.dumps(result, ensure_ascii=False, sort_keys=True)
        else:
            verb = "moved" if args.apply else "would move"
            live_str = (f"live {live_before}→{live_after}"
                        if args.apply else "live unchanged (dry-run)")
            human_lines = [
                f"{verb} {moved}; {retained} retained overlap-only; {live_str}"]
            if args.apply:
                human_lines.append(
                    f"residual exact/URL clusters: {len(recheck_clusters)} "
                    f"(verdict: {verdict})")
            rendered = "\n".join(human_lines)

        violations = cps.scan_text("dupclean-output", rendered)
        if violations:
            rendered_v = "\n".join(v.render() for v in violations)
            gate_msg = (
                f"refusing to emit output: {len(violations)} publish-safety "
                f"violation(s) in dupclean-output"
            )
            if json_mode:
                contract.emit(contract.envelope(
                    "clean-duplicates",
                    error=(contract.INTERNAL_ERROR, gate_msg)))
            else:
                print(rendered_v, file=_sys.stderr)
                print(f"error: {gate_msg}", file=_sys.stderr)
            return contract.EXIT_INTERNAL_ERROR

        # Output is publish-safe — emit normally.
        if json_mode:
            contract.emit(contract.envelope("clean-duplicates", result=result))
        else:
            print(rendered)

        # A "fail" verdict is NOT an execution error (ok:true) — exit 1 per the
        # contract convention; otherwise success exit 0.
        return 1 if verdict == "fail" else 0

    except Exception as exc:  # noqa: BLE001 — last-resort machine-readable error
        if json_mode:
            contract.emit(contract.envelope(
                "clean-duplicates",
                error=(contract.INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")))
            return contract.EXIT_INTERNAL_ERROR
        raise


if __name__ == "__main__":
    raise SystemExit(main())
