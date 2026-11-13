"""Offline Nyquist Wave-0 RED suite for the corpus-cleanup module ``dupclean``.

Stdlib ``unittest`` ONLY — NO pytest, NO crawl4ai, NO network, NO browser (per
``AGENTS.md`` / the ``crawler/tests/test_dupaudit.py`` convention). Every test
builds a tiny synthetic corpus in a tempdir and exercises ``crawler.dupclean``
in-process. Run from the repo root::

    python -m unittest crawler.tests.test_dupclean -v

THIS SUITE IS INTENTIONALLY RED in Wave 0: ``crawler.dupclean`` ships only the
typed interface contract (stubs raising ``NotImplementedError`` + the trivial
``_now``). Plans 02-04 are pure GREEN phases against this executable
specification — the import/contract checks (``TestContract``) pass now; every
behavior test fails until the move/prune/re-validation logic lands.

The duplicate-audit report the cleanup consumes is **minted in-tempdir** by
running the real ``dupaudit.audit()`` + ``render_json()`` over the synthetic
corpus (``_mint_report``) — never hand-authored — so the report schema this
suite asserts against stays in lock-step with Phase 20's producer.

Test map (21-VALIDATION.md § Per-Task Verification Map):

    TestContract   — import/contract anchor (GREEN now: surface + no hard-delete)
    TestScope      — CLEAN-02 overlap-only excluded by default
    TestDryRun     — CLEAN-02 dry-run default leaves the tree byte-identical
    TestApply      — CLEAN-02 moves non-canonical, keeps canonical, idempotent,
                     moves both .eval.json sibling forms
    TestRecheck    — CLEAN-02 zero exact/URL clusters after apply
    TestRevalidate — CLEAN-03 manifest prune, completeness-orphan prune, report count
    TestGit        — SC5 every changed path stays inside the corpus tree
    TestSecurity   — confine() rejects ``..`` / absolute relpaths (threat T-21-01)
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import completeness, contract, dupaudit, dupclean
from crawler.profile import load_profile, normalize_url

# Reuse Phase 20's proven synthetic-corpus + read-only snapshot helpers verbatim.
from crawler.tests import test_dupaudit

# The publish-safety checker (``scan_text``) is reused for dupclean's RPT-03
# share-safety gate. Importing ``test_dupaudit`` above already put ``scripts/``
# on ``sys.path``, so this top-level module import resolves (mirrors the
# scripts/tests convention used in test_dupaudit).
import check_publish_safe as cps

_STATIC_TS = "2026-06-11T00:00:00Z"


# --------------------------------------------------------------------------- #
# Fixture helpers
# --------------------------------------------------------------------------- #

def _doc_url(md_path: Path) -> str:
    """Read the ``url:`` field out of a corpus doc's YAML frontmatter."""
    for line in md_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("url:"):
            return stripped.split(":", 1)[1].strip().strip('"')
    return ""


def _make_clean_corpus(tmp: Path) -> Path:
    """Build the Phase-20 synthetic corpus then augment it so re-validation is
    testable.

    Starts from ``test_dupaudit._make_dup_corpus`` (exact pair, same-url pair,
    overlap-only near-dup pair, singleton, ``_dropped/`` + ``completeness/``
    noise, ``.eval.json`` siblings in BOTH naming forms), then adds:

      (1) a per-family ``manifest.json`` for famB and famC, keyed by the
          NORMALIZED source URL of each live doc (via ``profile.normalize_url`` +
          ``load_profile("ircc")``) so the keys match what ``prune_manifest``
          computes from the report's normalized member URLs;
      (2) under famC (the family of the same-url delete target ``url_two.md``) a
          ``completeness/sample.json`` whose single pair references ``url_two.md``
          plus an on-disk ``url_two.live.md`` + ``url_two.check.json``, with
          ``sampled`` = the pair count, so an orphaned-sidecar prune is
          observable after the doc is moved;
      (3) the ``<doc>.md.eval.json`` eval form for the exact delete target
          ``famB/exact_two.md`` (which already carries the ``<stem>.eval.json``
          form) so a single delete target exercises BOTH naming forms moving.
    """
    root = test_dupaudit._make_dup_corpus(tmp)
    profile = load_profile("ircc")

    # (1) per-family manifest.json keyed by normalized URL (famB + famC).
    for fam in ("famB", "famC"):
        fam_dir = root / fam
        manifest: dict[str, dict] = {}
        for md in sorted(fam_dir.glob("*.md")):
            if md.name == "REPORT.md":
                continue
            raw = _doc_url(md)
            if not raw:  # e.g. famC/no_frontmatter.md
                continue
            key = normalize_url(raw, profile)
            manifest[key] = {
                "path": md.name,
                "url": key,
                "title": md.stem,
                "chars": len(md.read_text(encoding="utf-8")),
            }
        (fam_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8")

    # (2) completeness sample + sidecars under famC referencing url_two.md.
    cdir = root / "famC" / "completeness"
    cdir.mkdir(exist_ok=True)
    (cdir / "url_two.live.md").write_text(
        "Ground-truth re-fetch capture for url_two.\n", encoding="utf-8")
    (cdir / "url_two.check.json").write_text(
        json.dumps({"doc": "url_two.md", "coverage_verdict": "complete",
                    "explained_by_pruning": False}, indent=2),
        encoding="utf-8")
    famc_live = [p for p in sorted((root / "famC").glob("*.md"))
                 if p.name != "REPORT.md"]
    (cdir / "sample.json").write_text(json.dumps({
        "fraction": 1.0,
        "total_live": len(famc_live),
        "sampled": 1,
        "fetched_at": _STATIC_TS,
        "pairs": [{
            "doc": "url_two.md",
            "url": normalize_url(_doc_url(root / "famC" / "url_two.md"), profile),
            "live": "url_two.live.md",
            "check": "url_two.check.json",
        }],
    }, indent=2), encoding="utf-8")

    # (3) the <doc>.md.eval.json form for famB/exact_two.md (delete target that
    # already carries the <stem>.eval.json form) — so BOTH forms move together.
    (root / "famB" / "exact_two.md.eval.json").write_text(
        test_dupaudit._eval_json("exact_two.md", test_dupaudit._EXACT_BODY),
        encoding="utf-8")

    return root


def _mint_report(root: Path) -> Path:
    """Run the real ``dupaudit`` over *root* and persist its JSON sidecar.

    Writes ``duplicate-audit.json`` to *root*'s PARENT (the tempdir — NEVER under
    ``corpus/``) and returns its path. No hand-authored JSON: the schema is
    produced by ``dupaudit.render_json`` exactly as Phase 20 emits it.
    """
    payload = dupaudit.render_json(dupaudit.audit(root))
    report_path = root.parent / "duplicate-audit.json"
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return report_path


# The audit's ``overlap_edges`` is an intentionally ``O(n^2)`` SequenceMatcher
# (Phase 20), so a full mint costs ~2s. The report is DETERMINISTIC over the
# (structurally identical) synthetic corpus, so we mint it exactly ONCE from
# ``dupaudit.audit()`` + ``render_json()`` and reuse the payload across tests —
# keeping the whole suite well under the 5s feedback budget while still proving
# the report is machine-minted (no hand-authored JSON).
_REPORT_PAYLOAD: dict | None = None


def _minted_payload() -> dict:
    global _REPORT_PAYLOAD
    if _REPORT_PAYLOAD is None:
        with tempfile.TemporaryDirectory() as t:
            root = _make_clean_corpus(Path(t))
            report = _mint_report(root)  # exercises the mint helper end-to-end
            _REPORT_PAYLOAD = json.loads(report.read_text(encoding="utf-8"))
    return _REPORT_PAYLOAD


def _write_report(root: Path) -> Path:
    """Persist the once-minted report payload beside (NOT under) *root*."""
    report_path = root.parent / "duplicate-audit.json"
    report_path.write_text(
        json.dumps(_minted_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return report_path


def _live_relpaths(root: Path) -> set[str]:
    """The set of live-doc relpaths per ``dupaudit.live_docs`` (the 752-filter)."""
    return {p.resolve().relative_to(root.resolve()).as_posix()
            for p, _ in dupaudit.live_docs(root)}


class _CleanCase(unittest.TestCase):
    """Base case: a fresh augmented corpus + the once-minted report per test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_clean_corpus(Path(self._tmp.name))
        self.report = _write_report(self.root)
        self.profile = load_profile("ircc")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # Convenience: normalized URL of a live doc by relpath.
    def _norm(self, relpath: str) -> str:
        return normalize_url(_doc_url(self.root / relpath), self.profile)


# --------------------------------------------------------------------------- #
# TestContract — import/contract anchor (GREEN now)
# --------------------------------------------------------------------------- #

class TestContract(unittest.TestCase):
    _SURFACE = (
        "load_plan", "confine", "move_to_dropped", "prune_manifest",
        "prune_completeness_orphans", "revalidate_family",
        "recheck_zero_clusters", "clean", "main",
    )

    def test_module_exposes_full_surface(self) -> None:
        for name in self._SURFACE:
            self.assertTrue(hasattr(dupclean, name),
                            f"dupclean is missing contracted symbol: {name}")
            self.assertTrue(callable(getattr(dupclean, name)))

    def test_no_hard_delete_primitive_in_source(self) -> None:
        src = Path(dupclean.__file__).read_text(encoding="utf-8")
        for forbidden in ("os.unlink", "os.remove", ".unlink(", ".remove("):
            self.assertNotIn(forbidden, src,
                             f"hard-delete primitive {forbidden!r} must not appear "
                             "(removal is move-to-_dropped; threat T-21-03)")

    def test_report_fixture_is_minted_from_dupaudit(self) -> None:
        """The report fixture is machine-minted by ``dupaudit`` (no literal JSON),
        written BESIDE the corpus (never under it)."""
        data = _minted_payload()  # produced by dupaudit.audit() + render_json()
        self.assertEqual(data["live_docs"], 8)
        # Exactly one keep + one delete decision across the 3 clusters.
        decisions = {m["decision"] for c in data["clusters"]
                     for m in c["members"]}
        self.assertEqual(decisions, {"keep", "delete"})
        with tempfile.TemporaryDirectory() as t:
            root = _make_clean_corpus(Path(t))
            report = _write_report(root)
            self.assertEqual(report.parent, root.parent)   # beside the corpus …
            self.assertFalse(str(report).startswith(str(root) + "/"))  # … not in it
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")), data)


# --------------------------------------------------------------------------- #
# TestScope — CLEAN-02 overlap-only excluded by default
# --------------------------------------------------------------------------- #

class TestScope(_CleanCase):
    def test_overlap_only_excluded_by_default(self) -> None:
        default = dupclean.load_plan(self.report)
        default_rels = {t["relpath"] for t in default}
        # High-confidence (exact + url) delete targets are in scope by default.
        self.assertIn("famB/exact_two.md", default_rels)   # exact
        self.assertIn("famC/url_two.md", default_rels)      # url
        # The overlap-ONLY delete target is excluded by default (false-positive gate).
        self.assertNotIn("famB/near_close.md", default_rels)

        widened = dupclean.load_plan(self.report, include_overlap=True)
        widened_rels = {t["relpath"] for t in widened}
        self.assertIn("famB/near_close.md", widened_rels)
        # Each target carries the documented overlap_only flag.
        flags = {t["relpath"]: t["overlap_only"] for t in widened}
        self.assertTrue(flags["famB/near_close.md"])
        self.assertFalse(flags["famB/exact_two.md"])


# --------------------------------------------------------------------------- #
# TestDryRun — CLEAN-02 dry-run default
# --------------------------------------------------------------------------- #

class TestDryRun(_CleanCase):
    def test_default_is_dry_run(self) -> None:
        before = test_dupaudit._manifest(self.root)
        dupclean.clean(self.root, self.report)  # apply defaults to False
        after = test_dupaudit._manifest(self.root)
        self.assertEqual(before, after)  # corpus tree byte-identical


# --------------------------------------------------------------------------- #
# TestApply — CLEAN-02 move-to-_dropped guarantees
# --------------------------------------------------------------------------- #

class TestApply(_CleanCase):
    def test_moves_only_noncanonical(self) -> None:
        dupclean.clean(self.root, self.report, apply=True)
        # High-confidence delete targets leave the live set …
        self.assertFalse((self.root / "famB" / "exact_two.md").is_file())
        self.assertFalse((self.root / "famC" / "url_two.md").is_file())
        # … and land in their owning family's _dropped/ quarantine.
        self.assertTrue((self.root / "famB" / "_dropped" / "exact_two.md").is_file())
        self.assertTrue((self.root / "famC" / "_dropped" / "url_two.md").is_file())

    def test_canonical_untouched(self) -> None:
        dupclean.clean(self.root, self.report, apply=True)
        # The kept canonical of each cluster is NEVER moved.
        self.assertTrue((self.root / "famA" / "exact_one.md").is_file())
        self.assertTrue((self.root / "famA" / "url_one.md").is_file())
        # Overlap-only delete target retained by default (not in scope).
        self.assertTrue((self.root / "famB" / "near_close.md").is_file())

    def test_idempotent_reapply(self) -> None:
        dupclean.clean(self.root, self.report, apply=True)
        live_after_first = _live_relpaths(self.root)
        dupclean.clean(self.root, self.report, apply=True)  # second apply = no-op
        live_after_second = _live_relpaths(self.root)
        self.assertEqual(live_after_first, live_after_second)

    def test_eval_sibling_moved(self) -> None:
        dupclean.clean(self.root, self.report, apply=True)
        dropped = self.root / "famB" / "_dropped"
        # Both eval naming forms move with the famB/exact_two.md delete target.
        self.assertTrue((dropped / "exact_two.eval.json").is_file())     # <stem>
        self.assertTrue((dropped / "exact_two.md.eval.json").is_file())  # <doc>.md
        self.assertFalse((self.root / "famB" / "exact_two.eval.json").is_file())
        self.assertFalse((self.root / "famB" / "exact_two.md.eval.json").is_file())


# --------------------------------------------------------------------------- #
# TestRecheck — CLEAN-02 zero exact/URL clusters after apply
# --------------------------------------------------------------------------- #

class TestRecheck(_CleanCase):
    def test_no_exact_or_url_clusters_after_apply(self) -> None:
        dupclean.clean(self.root, self.report, apply=True)
        # The module's fast re-check (exact_edges + url_edges → cluster()) is empty.
        self.assertEqual(dupclean.recheck_zero_clusters(self.root), [])
        # And independently confirm via dupaudit's primitives over the live set.
        docs = [dupaudit.parse_doc(p, t, self.profile, self.root)
                for p, t in dupaudit.live_docs(self.root)]
        edges = dupaudit.exact_edges(docs) + dupaudit.url_edges(docs)
        self.assertEqual(dupaudit.cluster(len(docs), edges), [])


# --------------------------------------------------------------------------- #
# TestRevalidate — CLEAN-03 manifest + completeness + report re-validation
# --------------------------------------------------------------------------- #

class TestRevalidate(_CleanCase):
    def test_manifest_pruned(self) -> None:
        moved_url = self._norm("famC/url_two.md")
        kept_url = self._norm("famC/near_far.md")
        dupclean.clean(self.root, self.report, apply=True)
        manifest = json.loads(
            (self.root / "famC" / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn(moved_url, manifest)  # moved doc's URL pruned
        self.assertIn(kept_url, manifest)       # untouched live doc retained

    def test_completeness_orphans_pruned(self) -> None:
        dupclean.clean(self.root, self.report, apply=True)
        cdir = self.root / "famC" / "completeness"
        sample = json.loads((cdir / "sample.json").read_text(encoding="utf-8"))
        sampled_docs = {pair["doc"] for pair in sample["pairs"]}
        self.assertNotIn("url_two.md", sampled_docs)  # orphaned pair pruned
        # The orphaned capture + check sidecars are gone from the live location.
        self.assertFalse((cdir / "url_two.live.md").is_file())
        self.assertFalse((cdir / "url_two.check.json").is_file())

    def test_report_count_updated(self) -> None:
        before = len(completeness.live_docs(self.root / "famC"))
        dupclean.clean(self.root, self.report, apply=True)
        report_md = (self.root / "famC" / "REPORT.md").read_text(encoding="utf-8")
        # Live count decremented by exactly the one moved doc …
        self.assertIn(f"Live documents: **{before - 1}**", report_md)
        # … and the family verdict did not regress to a hard fail.
        self.assertNotIn("❌ FAIL", report_md)


# --------------------------------------------------------------------------- #
# TestGit — SC5 git-status-local (unit form: writes stay inside the corpus tree)
# --------------------------------------------------------------------------- #

class TestGit(_CleanCase):
    def test_corpus_changes_stay_ignored(self) -> None:
        tmp_root = Path(self._tmp.name)  # contains corpus/ AND the report json
        before = test_dupaudit._manifest(tmp_root)
        dupclean.clean(self.root, self.report, apply=True)
        after = test_dupaudit._manifest(tmp_root)

        changed = set(before) ^ set(after)
        changed |= {k for k in (before.keys() & after.keys())
                    if before[k] != after[k]}
        self.assertTrue(changed, "apply must have changed something on disk")
        for relpath in changed:
            # Every changed/new path is INSIDE corpus/ — nothing written outside it
            # (the report json lives at tmp root and must remain untouched).
            self.assertTrue(relpath.startswith("corpus/"),
                            f"path written outside the corpus tree: {relpath}")


# --------------------------------------------------------------------------- #
# TestSecurity — confine() path-traversal guard (threat T-21-01)
# --------------------------------------------------------------------------- #

class TestSecurity(_CleanCase):
    def test_rejects_escaping_relpath(self) -> None:
        with self.assertRaises(ValueError):
            dupclean.confine(self.root, "../escape.md")
        with self.assertRaises(ValueError):
            dupclean.confine(self.root, "/etc/passwd")
        with self.assertRaises(ValueError):
            dupclean.confine(self.root, "famB/../../escape.md")
        # A legitimate in-corpus relpath resolves to a path inside the root.
        resolved = dupclean.confine(self.root, "famC/url_two.md")
        self.assertTrue(
            str(Path(resolved).resolve()).startswith(str(self.root.resolve())))


# --------------------------------------------------------------------------- #
# TestPublishSafe — RPT-03 publish-safety self-gate (scan_text reuse)
# --------------------------------------------------------------------------- #


class TestPublishSafe(_CleanCase):
    """RPT-03 share-safety self-gate — dupclean must fail CLOSED rather than emit
    any abs-path/secret/PII on its stdout contract surface. Mirrors
    ``test_dupaudit.TestPublishSafe`` (clean output passes the gate; poisoned
    output is refused with ``EXIT_INTERNAL_ERROR``)."""

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = dupclean.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_clean_run_passes_gate_and_emits_normally(self) -> None:
        # A clean synthetic-corpus dry-run: the gate finds zero violations, so the
        # tool emits its normal clean-duplicates envelope (NOT INTERNAL_ERROR).
        rc, out, _ = self._run(
            [str(self.root), "--report", str(self.report), "--json"])
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertEqual(obj["command"], "clean-duplicates")
        self.assertNotEqual(rc, contract.EXIT_INTERNAL_ERROR)

    def test_gate_maps_poisoned_output_to_violation(self) -> None:
        # The reused scan_text helper maps a leaked absolute home-dir path that
        # would ride in the emitted payload to ≥1 publish-safety violation.
        poisoned = json.dumps(
            {"families": ["/home/user/leak/secret.md"]})  # publish-safe: allow
        self.assertTrue(cps.scan_text("dupclean-output", poisoned))

    def test_poisoned_output_fails_closed(self) -> None:
        # Force the to-be-emitted payload to carry a leaked absolute home-dir path
        # via the smallest seam (clean()'s returned summary). The gate must refuse
        # to emit the normal envelope and return EXIT_INTERNAL_ERROR (fail closed).
        poisoned_summary = {
            "apply": False,
            "moved": 0,
            "retained_overlap_only": 0,
            "skipped": 0,
            "families": ["/home/user/leak/secret.md"],  # publish-safe: allow
            "plan": {},
        }
        with mock.patch.object(dupclean, "clean", return_value=poisoned_summary):
            rc, out, _ = self._run(
                [str(self.root), "--report", str(self.report), "--json"])
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], contract.INTERNAL_ERROR)
        self.assertEqual(rc, contract.EXIT_INTERNAL_ERROR)


if __name__ == "__main__":
    unittest.main()
