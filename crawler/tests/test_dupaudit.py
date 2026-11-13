"""Offline Nyquist Wave-0 test suite for the cross-family duplicate-audit module.

Stdlib ``unittest`` ONLY — NO pytest, NO crawl4ai, NO network, NO browser (per
the AGENTS.md / ``crawler/tests/test_json_contract.py`` convention). Every test
builds a tiny synthetic corpus in a tempdir (``_make_dup_corpus``) and exercises
``crawler.dupaudit`` in-process. Run from the repo root::

    python -m unittest crawler.tests.test_dupaudit -v

THIS SUITE IS INTENTIONALLY RED in Wave 0: ``crawler.dupaudit`` ships only the
typed interface contract (dataclasses + stubs raising ``NotImplementedError``,
plus the implemented ``body_of``/``body_hash``). Plans 02/03 are pure GREEN
phases against this executable specification — the contract/import checks pass
now, the behavior tests fail until the logic lands. Tests covered:

    TestEnumerate  — Success Criterion 5 752-filter (noise excluded)
    TestExact      — DUP-01 body-only sha1
    TestUrl        — DUP-02 normalized-URL collapse
    TestOverlap    — DUP-03 text-overlap threshold boundary
    TestCluster    — DUP-04 union-find transitive clustering + signals
    TestCanonical  — CLEAN-01 deterministic canonical selection
    TestReport     — RPT-01/02 markdown + JSON keep/delete rendering
    TestPublishSafe— RPT-03 publish-safety (scan_text) gate
    TestReadOnly   — Success Criterion 5 read-only guarantee
    TestJson       — RPT-01 --json envelope contract
    TestRealCorpus — optional real-corpus smoke (skipped if corpus/ absent)
    TestEmptyFamily— empty-family robustness (audit/live_docs tolerate empties)
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

from crawler import completeness, dupaudit
from crawler.profile import load_profile

# Import the publish-safety checker as a top-level module without requiring
# `scripts` to be an importable package (mirrors scripts/tests convention).
_SCRIPTS_DIR = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
import check_publish_safe as cps  # noqa: E402  (scan_text reuse — RPT-03)


# --------------------------------------------------------------------------- #
# Deterministic synthetic-body generators (near-dup ratios tuned with difflib:
# near ≈ 0.9675 → clusters at 0.95; far ≈ 0.9007 → does NOT cluster at 0.95).
# --------------------------------------------------------------------------- #

_BASE_LINES = [
    f"Line {i:03d}: the quick brown fox jumps over the lazy dog "
    f"near the river bank today."
    for i in range(60)
]


def _base_body() -> str:
    return "\n".join(_BASE_LINES) + "\n"


def _near_body() -> str:
    """~4% character change vs the base body → SequenceMatcher ratio ≈ 0.96."""
    lines = list(_BASE_LINES)
    for idx in range(0, 60, 4):  # 15 lines lightly edited
        lines[idx] = lines[idx].replace("quick brown fox", "slow grey wolf")
    return "\n".join(lines) + "\n"


def _far_body() -> str:
    """~10% character change vs the base body → ratio ≈ 0.90 (< 0.95)."""
    lines = list(_BASE_LINES)
    for idx in range(0, 60, 7):  # ~9 lines heavily edited
        lines[idx] = lines[idx].replace(
            "the quick brown fox jumps over the lazy dog near the river bank today",
            "COMPLETELY DIFFERENT SENTENCE WITH OTHER WORDS",
        )
    return "\n".join(lines) + "\n"


_EXACT_BODY = (
    "Police certificates are required for permanent residence applications.\n"
    "Each applicant aged 18 or older must provide one per country of residence.\n"
)
_URL_BODY_1 = "Express Entry rounds of invitations are published periodically.\n"
_URL_BODY_2 = "The latest invitation round issued invitations to candidates.\n"
_SINGLETON_BODY = "A wholly unique document about medical examination panel physicians.\n"


def _doc_text(url: str, crawl_date: str, title: str, body: str) -> str:
    """Compose a corpus .md file: YAML frontmatter block + body."""
    return (
        "---\n"
        f'url: "{url}"\n'
        f'title: "{title}"\n'
        f"crawl_date: \"{crawl_date}\"\n"
        "---\n\n"
        f"{body}"
    )


def _eval_json(doc_filename: str, body: str) -> str:
    """A passing QC eval: verdict=keep, relevant, with a groundable must_contain
    token that is actually present in *body* (so check_doc(...).passed is True)."""
    first_word = body.split()[0]
    return json.dumps(
        {
            "doc": doc_filename,
            "url": "https://www.canada.ca/example",
            "relevance_score": 0.95,
            "verdict": "keep",
            "quality_flags": [],
            "summary": "Synthetic passing eval for the dup-audit fixture.",
            "must_contain": [first_word],
            "must_not_contain": [],
            "grounding_refs": [],
            "notes": "fixture",
        }
    )


# --------------------------------------------------------------------------- #
# Synthetic multi-family corpus fixture
# --------------------------------------------------------------------------- #

def _make_dup_corpus(tmp: Path) -> Path:
    """Build a synthetic multi-family corpus under *tmp* and return its root.

    Plants, across three family dirs:
      (a) an EXACT pair        — byte-identical bodies, different url + crawl_date
      (b) a SAME-URL pair      — different bodies, urls differing only by
                                 #fragment / ?wbdisable=true / trailing slash
      (c) a NEAR-DUP pair      — bodies at ratio ≈0.96 (clusters @0.95) plus a
                                 NEGATIVE third doc at ratio ≈0.90 (does NOT)
      (d) a SINGLETON          — unique body + url
      (e) NOISE the 752-filter must drop — REPORT.md, completeness/*.live.md,
                                 _dropped/*, and a no-frontmatter .md
      (f) matching .eval.json siblings in BOTH naming forms (<doc>.md.eval.json
                                 and <stem>.eval.json), some passing, one missing
    """
    root = tmp / "corpus"
    for fam in ("famA", "famB", "famC"):
        (root / fam).mkdir(parents=True, exist_ok=True)

    # (a) EXACT pair — identical body, different frontmatter (url + crawl_date).
    (root / "famA" / "exact_one.md").write_text(
        _doc_text("https://www.canada.ca/en/exact-a.html", "2024-01-01",
                  "Police certificates A", _EXACT_BODY), encoding="utf-8")
    (root / "famB" / "exact_two.md").write_text(
        _doc_text("https://www.canada.ca/en/exact-b.html", "2024-06-01",
                  "Police certificates B", _EXACT_BODY), encoding="utf-8")

    # (b) SAME-URL pair — different bodies, url variants that normalize equal.
    (root / "famA" / "url_one.md").write_text(
        _doc_text("https://www.canada.ca/en/shared-page.html", "2024-02-02",
                  "Rounds one", _URL_BODY_1), encoding="utf-8")
    (root / "famC" / "url_two.md").write_text(
        _doc_text("https://www.canada.ca/en/shared-page.html?wbdisable=true#frag",
                  "2024-07-07", "Rounds two", _URL_BODY_2), encoding="utf-8")

    # (c) NEAR-DUP pair (≈0.96) + NEGATIVE far doc (≈0.90).
    (root / "famA" / "near_base.md").write_text(
        _doc_text("https://www.canada.ca/en/near-base.html", "2024-03-03",
                  "Near base", _base_body()), encoding="utf-8")
    (root / "famB" / "near_close.md").write_text(
        _doc_text("https://www.canada.ca/en/near-close.html", "2024-03-04",
                  "Near close", _near_body()), encoding="utf-8")
    (root / "famC" / "near_far.md").write_text(
        _doc_text("https://www.canada.ca/en/near-far.html", "2024-03-05",
                  "Near far", _far_body()), encoding="utf-8")

    # (d) SINGLETON.
    (root / "famB" / "singleton.md").write_text(
        _doc_text("https://www.canada.ca/en/singleton.html", "2024-04-04",
                  "Singleton", _SINGLETON_BODY), encoding="utf-8")

    # (f) eval siblings — both naming forms, plus a missing eval for the singleton.
    (root / "famA" / "exact_one.md.eval.json").write_text(  # <doc>.md.eval.json
        _eval_json("exact_one.md", _EXACT_BODY), encoding="utf-8")
    (root / "famB" / "exact_two.eval.json").write_text(     # <stem>.eval.json
        _eval_json("exact_two.md", _EXACT_BODY), encoding="utf-8")
    (root / "famA" / "url_one.md.eval.json").write_text(
        _eval_json("url_one.md", _URL_BODY_1), encoding="utf-8")
    (root / "famA" / "near_base.md.eval.json").write_text(
        _eval_json("near_base.md", _base_body()), encoding="utf-8")
    # singleton.md deliberately has NO eval → passed_qc must resolve False.

    # (e) NOISE the live-doc filter must exclude.
    (root / "famA" / "REPORT.md").write_text(
        "# Family report\nGenerated aggregate — not a corpus doc.\n", encoding="utf-8")
    (root / "famA" / "completeness").mkdir(exist_ok=True)
    (root / "famA" / "completeness" / "sample.live.md").write_text(
        _doc_text("https://www.canada.ca/en/live.html", "2024-05-05",
                  "Live capture", "Ground-truth re-fetch capture.\n"),
        encoding="utf-8")
    (root / "famB" / "_dropped").mkdir(exist_ok=True)
    (root / "famB" / "_dropped" / "dropped_doc.md").write_text(
        _doc_text("https://www.canada.ca/en/dropped.html", "2024-05-06",
                  "Dropped", "Quarantined dropped document.\n"), encoding="utf-8")
    (root / "famC" / "no_frontmatter.md").write_text(
        "Just a plain markdown artifact with no YAML frontmatter at all.\n",
        encoding="utf-8")

    return root


# The eight relpaths that the 752-filter MUST yield (noise excluded).
_LIVE_RELPATHS = {
    "famA/exact_one.md", "famB/exact_two.md",
    "famA/url_one.md", "famC/url_two.md",
    "famA/near_base.md", "famB/near_close.md", "famC/near_far.md",
    "famB/singleton.md",
}


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

def _rel(p: Path, root: Path) -> str:
    return p.relative_to(root).as_posix()


def _load_docs(root: Path) -> list:
    """Enumerate + parse the live corpus into Doc objects (RED until Plan 02)."""
    profile = load_profile("ircc")
    return [dupaudit.parse_doc(p, t, profile, root)
            for p, t in dupaudit.live_docs(root)]


def _index_by_relpath(docs: list) -> dict[str, int]:
    return {d.relpath: i for i, d in enumerate(docs)}


def _edge_set(edges) -> set:
    """Normalize an edge list to a set of frozensets for order-insensitive asserts."""
    return {frozenset((i, j)) for i, j in edges}


def _make_doc(relpath: str, family: str, url: str, body: str,
              passed_qc: bool = False) -> dupaudit.Doc:
    """Construct a Doc directly (deterministic detector unit tests)."""
    return dupaudit.Doc(
        path=Path(relpath),
        relpath=relpath,
        family=family,
        url=url,
        title=relpath,
        body=body,
        body_hash=dupaudit.body_hash(body),
        body_len=len(body),
        passed_qc=passed_qc,
    )


def _manifest(root: Path) -> dict:
    """{relpath: (size, mtime_ns, sha1)} over EVERY file under *root*."""
    out: dict[str, tuple] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            st = p.stat()
            out[_rel(p, root)] = (st.st_size, st.st_mtime_ns,
                                  hashlib.sha1(data).hexdigest())
    return out


class _CorpusCase(unittest.TestCase):
    """Base case that builds a fresh synthetic corpus per test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_dup_corpus(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()


# --------------------------------------------------------------------------- #
# TestEnumerate — Success Criterion 5 live-doc filter
# --------------------------------------------------------------------------- #

class TestEnumerate(_CorpusCase):
    def test_live_docs_yields_exactly_the_live_set(self) -> None:
        rels = {_rel(p, self.root) for p, _ in dupaudit.live_docs(self.root)}
        self.assertEqual(rels, _LIVE_RELPATHS)

    def test_noise_is_excluded(self) -> None:
        rels = {_rel(p, self.root) for p, _ in dupaudit.live_docs(self.root)}
        self.assertNotIn("famA/REPORT.md", rels)
        self.assertNotIn("famA/completeness/sample.live.md", rels)
        self.assertNotIn("famB/_dropped/dropped_doc.md", rels)
        self.assertNotIn("famC/no_frontmatter.md", rels)

    def test_every_yielded_text_has_frontmatter(self) -> None:
        for _, text in dupaudit.live_docs(self.root):
            self.assertTrue(text.startswith("---"))


# --------------------------------------------------------------------------- #
# TestExact — DUP-01 body-only sha1
# --------------------------------------------------------------------------- #

class TestExact(unittest.TestCase):
    def test_identical_body_different_frontmatter_is_one_edge(self) -> None:
        docs = [
            _make_doc("famA/a.md", "famA", "https://x/a", _EXACT_BODY),
            _make_doc("famB/b.md", "famB", "https://x/b", _EXACT_BODY),  # diff url
            _make_doc("famC/c.md", "famC", "https://x/a", _SINGLETON_BODY),
        ]
        edges = _edge_set(dupaudit.exact_edges(docs))
        self.assertIn(frozenset((0, 1)), edges)

    def test_same_url_different_body_is_not_an_exact_edge(self) -> None:
        docs = [
            _make_doc("famA/a.md", "famA", "https://x/same", _EXACT_BODY),
            _make_doc("famC/c.md", "famC", "https://x/same", _SINGLETON_BODY),
        ]
        edges = _edge_set(dupaudit.exact_edges(docs))
        self.assertNotIn(frozenset((0, 1)), edges)


# --------------------------------------------------------------------------- #
# TestUrl — DUP-02 normalized-URL collapse
# --------------------------------------------------------------------------- #

class TestUrl(_CorpusCase):
    def test_url_variants_collapse_to_one_edge(self) -> None:
        docs = _load_docs(self.root)
        idx = _index_by_relpath(docs)
        edges = _edge_set(dupaudit.url_edges(docs))
        self.assertIn(
            frozenset((idx["famA/url_one.md"], idx["famC/url_two.md"])), edges)

    def test_distinct_urls_do_not_form_a_url_edge(self) -> None:
        docs = _load_docs(self.root)
        idx = _index_by_relpath(docs)
        edges = _edge_set(dupaudit.url_edges(docs))
        self.assertNotIn(
            frozenset((idx["famA/exact_one.md"], idx["famB/exact_two.md"])), edges)


# --------------------------------------------------------------------------- #
# TestOverlap — DUP-03 text-overlap threshold boundary
# --------------------------------------------------------------------------- #

class TestOverlap(unittest.TestCase):
    def test_near_pair_clusters_far_pair_does_not(self) -> None:
        docs = [
            _make_doc("famA/base.md", "famA", "https://x/base", _base_body()),
            _make_doc("famB/close.md", "famB", "https://x/close", _near_body()),
            _make_doc("famC/far.md", "famC", "https://x/far", _far_body()),
        ]
        edges = _edge_set(dupaudit.overlap_edges(docs, threshold=0.95))
        self.assertIn(frozenset((0, 1)), edges)      # ≈0.96 → clustered
        self.assertNotIn(frozenset((0, 2)), edges)   # ≈0.90 → not clustered

    def test_threshold_parameter_is_honored(self) -> None:
        docs = [
            _make_doc("famA/base.md", "famA", "https://x/base", _base_body()),
            _make_doc("famB/close.md", "famB", "https://x/close", _near_body()),
        ]
        # ≈0.9675 clears 0.95 but not 0.99.
        self.assertIn(frozenset((0, 1)),
                      _edge_set(dupaudit.overlap_edges(docs, threshold=0.95)))
        self.assertNotIn(frozenset((0, 1)),
                         _edge_set(dupaudit.overlap_edges(docs, threshold=0.99)))


# --------------------------------------------------------------------------- #
# TestCluster — DUP-04 union-find transitive clustering + signals
# --------------------------------------------------------------------------- #

class TestCluster(unittest.TestCase):
    def test_uf_unions_into_one_component(self) -> None:
        uf = dupaudit.UF(3)
        uf.union(0, 1)
        self.assertEqual(uf.find(0), uf.find(1))
        self.assertNotEqual(uf.find(0), uf.find(2))

    def test_transitive_edges_form_single_cluster_singletons_excluded(self) -> None:
        # 0-1-2 connected transitively; 3 is a singleton.
        comps = dupaudit.cluster(4, [(0, 1), (1, 2)])
        comps = sorted(sorted(c) for c in comps)
        self.assertEqual(comps, [[0, 1, 2]])

    def test_mixed_signal_chain_clusters_via_detectors(self) -> None:
        # a≡b exact ; b and c share a URL → one 3-member cluster, d singleton.
        docs = [
            _make_doc("famA/a.md", "famA", "https://x/a", _EXACT_BODY),
            _make_doc("famB/b.md", "famB", "https://x/shared", _EXACT_BODY),
            _make_doc("famC/c.md", "famC", "https://x/shared", _URL_BODY_1),
            _make_doc("famB/d.md", "famB", "https://x/d", _SINGLETON_BODY),
        ]
        edges = dupaudit.exact_edges(docs) + dupaudit.url_edges(docs)
        comps = sorted(sorted(c) for c in dupaudit.cluster(len(docs), edges))
        self.assertEqual(comps, [[0, 1, 2]])

    def test_cluster_signals_records_detectors_per_component(self) -> None:
        sigs = dupaudit.cluster_signals(
            [[0, 1, 2]],
            {"exact": [(0, 1)], "url": [(1, 2)], "overlap": []},
        )
        self.assertEqual(sigs, [{"exact", "url"}])


# --------------------------------------------------------------------------- #
# TestCanonical — CLEAN-01 deterministic canonical selection
# --------------------------------------------------------------------------- #

class TestCanonical(unittest.TestCase):
    def test_passed_qc_beats_non_qc_even_if_shorter(self) -> None:
        members = [
            _make_doc("famA/long.md", "famA", "u1", "x" * 5000, passed_qc=False),
            _make_doc("famB/short.md", "famB", "u2", "y" * 100, passed_qc=True),
        ]
        canon, reasons = dupaudit.select_canonical(members)
        self.assertTrue(members[canon].passed_qc)
        self.assertEqual(members[canon].relpath, "famB/short.md")
        self.assertEqual(len(reasons), len(members))

    def test_longest_body_breaks_qc_tie(self) -> None:
        members = [
            _make_doc("famA/a.md", "famA", "u1", "x" * 200, passed_qc=True),
            _make_doc("famB/b.md", "famB", "u2", "x" * 900, passed_qc=True),
        ]
        canon, _ = dupaudit.select_canonical(members)
        self.assertEqual(members[canon].relpath, "famB/b.md")

    def test_lexicographic_path_breaks_length_tie(self) -> None:
        body = "z" * 300
        members = [
            _make_doc("famB/aaa.md", "famB", "u2", body, passed_qc=True),
            _make_doc("famA/zzz.md", "famA", "u1", body, passed_qc=True),
        ]
        canon, _ = dupaudit.select_canonical(members)
        self.assertEqual(members[canon].relpath, "famA/zzz.md")  # smallest path

    def test_selection_is_deterministic_across_shuffles(self) -> None:
        members = [
            _make_doc("famA/x.md", "famA", "u1", "a" * 100, passed_qc=False),
            _make_doc("famB/y.md", "famB", "u2", "b" * 800, passed_qc=True),
            _make_doc("famC/z.md", "famC", "u3", "c" * 400, passed_qc=True),
        ]
        winners = set()
        rng = random.Random(1234)
        for _ in range(100):
            shuffled = members[:]
            rng.shuffle(shuffled)
            canon, _ = dupaudit.select_canonical(shuffled)
            winners.add(shuffled[canon].relpath)
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners.pop(), "famB/y.md")  # QC + longest body


# --------------------------------------------------------------------------- #
# TestReport — RPT-01/02 markdown + JSON rendering
# --------------------------------------------------------------------------- #

class TestReport(_CorpusCase):
    def test_markdown_lists_members_with_keep_delete_and_reasons(self) -> None:
        md = dupaudit.render_markdown(dupaudit.audit(self.root))
        self.assertIsInstance(md, str)
        # Every exact-pair member's relpath appears with keep/delete decisions.
        self.assertIn("famA/exact_one.md", md)
        self.assertIn("famB/exact_two.md", md)
        lower = md.lower()
        self.assertIn("keep", lower)
        self.assertIn("delete", lower)

    def test_json_sidecar_is_a_serializable_dict(self) -> None:
        js = dupaudit.render_json(dupaudit.audit(self.root))
        self.assertIsInstance(js, dict)
        # Round-trips through json without error (machine sidecar contract).
        json.loads(json.dumps(js))


# --------------------------------------------------------------------------- #
# TestPublishSafe — RPT-03 publish-safety gate (scan_text reuse)
# --------------------------------------------------------------------------- #

class TestPublishSafe(_CorpusCase):
    def test_generated_report_has_no_violations(self) -> None:
        md = dupaudit.render_markdown(dupaudit.audit(self.root))
        self.assertEqual(cps.scan_text("reports/duplicate-audit.md", md), [])

    def test_scanner_flags_absolute_path_in_poisoned_copy(self) -> None:
        poisoned = "# Duplicate audit\n\nLeaked path: /home/user/secret/file.md\n"  # publish-safe: allow
        violations = cps.scan_text("reports/duplicate-audit.md", poisoned)
        self.assertTrue(violations)


# --------------------------------------------------------------------------- #
# TestReadOnly — Success Criterion 5 read-only guarantee
# --------------------------------------------------------------------------- #

class TestReadOnly(_CorpusCase):
    def test_corpus_tree_unchanged_after_audit(self) -> None:
        before = _manifest(self.root)
        dupaudit.audit(self.root)
        after = _manifest(self.root)
        self.assertEqual(before, after)

    def test_no_writes_inside_any_family_dir(self) -> None:
        before = {p for p in self.root.rglob("*") if p.is_file()}
        dupaudit.audit(self.root)
        after = {p for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


# --------------------------------------------------------------------------- #
# TestJson — RPT-01 --json envelope contract
# --------------------------------------------------------------------------- #

class TestJson(_CorpusCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = dupaudit.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_json_mode_emits_one_audit_duplicates_envelope(self) -> None:
        out_dir = Path(self._tmp.name) / "reports"
        _, out, _ = self._run([str(self.root), "--json", "--out", str(out_dir)])
        self.assertEqual(out.count("\n"), 1)        # exactly one JSON line
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertEqual(obj["command"], "audit-duplicates")


# --------------------------------------------------------------------------- #
# TestRealCorpus — optional smoke test against the real on-disk corpus.
# --------------------------------------------------------------------------- #

@unittest.skipUnless(Path("corpus").is_dir(),
                     "real corpus/ not present — skipping integration smoke test")
class TestRealCorpus(unittest.TestCase):
    def test_audit_runs_clean_with_expected_counts(self) -> None:
        result = dupaudit.audit(Path("corpus"))
        # The canonical 742 committed live docs, PLUS the git-ignored Phase-41
        # dli family when a local `refresh-dli` has populated corpus/dli/. A
        # fresh clone / CI sees exactly 742; a locally-refreshed tree sees
        # 742 + <dli .md count> (the flat family the generator writes). Both are
        # the correct live-doc set for the on-disk corpus.
        dli_dir = Path("corpus/dli")
        expected_live = 742 + (
            len(list(dli_dir.glob("*.md"))) if dli_dir.is_dir() else 0
        )
        self.assertEqual(result.live_docs, expected_live)
        # Post-v2.2 cleanup the live corpus carries ZERO exact-duplicate clusters:
        # `dupclean` moved every non-canonical exact copy into its family's
        # `_dropped/` (one canonical copy per cluster), which `dupaudit.live_docs`
        # excludes. `exact == 0` is the *clean* state this smoke test's name
        # promises — and now a regression guard against re-introducing an exact
        # duplicate. (The pre-cleanup `>= 1` expectation was stale once v2.2 ran.)
        self.assertEqual(result.exact, 0)


# --------------------------------------------------------------------------- #
# TestEmptyFamily — empty-family robustness regression (locks in graceful
# handling so a future refactor can't reintroduce a crash/miscount).
#
# After the v2.2 cleanup the real ``pdi-completeness-check`` family became empty
# (its manifest.json was pruned to ``{}`` by dupclean). No production-code defect
# exists today — ``dupaudit.live_docs`` (rglob) and ``completeness.live_docs``
# (glob) both yield nothing for an empty family without error. This fast,
# synthetic (tempdir) test pins that behavior. No real-corpus / network dep.
# --------------------------------------------------------------------------- #

class TestEmptyFamily(unittest.TestCase):
    def _make_corpus_with_empty_families(self, root: Path) -> tuple[Path, Path]:
        """Build (a) one real family with a frontmatter .md, (b) a wholly empty
        family dir, (c) a family whose ``manifest.json`` is ``{}`` with no live
        docs (mirrors the post-v2.2 ``pdi-completeness-check``). Returns the
        empty-family and pruned-family paths."""
        real = root / "real-family"
        real.mkdir(parents=True, exist_ok=True)
        (real / "doc.md").write_text(
            _doc_text("https://www.canada.ca/en/real.html", "2024-01-01",
                      "Real doc", _SINGLETON_BODY), encoding="utf-8")

        empty = root / "empty-family"
        empty.mkdir(parents=True, exist_ok=True)  # (b) completely empty

        pruned = root / "pdi-completeness-check"
        pruned.mkdir(parents=True, exist_ok=True)
        (pruned / "manifest.json").write_text("{}\n", encoding="utf-8")  # (c)
        return empty, pruned

    def test_audit_tolerates_empty_families_without_miscount(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "corpus"
            root.mkdir()
            empty, _pruned = self._make_corpus_with_empty_families(root)
            # audit() must not raise and must count ONLY the one real live doc
            # (empty + manifest-only families contribute zero, no miscount).
            result = dupaudit.audit(root)
            self.assertEqual(result.live_docs, 1)
            # completeness.live_docs returns [] for a wholly empty family dir.
            self.assertEqual(completeness.live_docs(empty), [])


if __name__ == "__main__":
    unittest.main()
