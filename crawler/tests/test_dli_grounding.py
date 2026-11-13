"""Golden DLI family + grounded `study.dli.designation` conformance (Phase 41 — STUDY-01 SC2/SC4).

Two proofs, both network-free against the COMMITTED offline golden family
(``crawler/tests/fixtures/dli/golden/dli/*.md`` + ``manifest.json``):

* **Golden byte-identity (Task 1 / T-41-01, T-41-06):** the committed golden
  family is byte-for-byte identical to a fresh regeneration of the Wave-1
  generator (:mod:`crawler.dli_snapshot`) over the curated
  ``fixtures/dli/dli-sample.json`` — a golden is NEVER hand-edited (Pitfall 6),
  and the set exercises every verified upstream landmine.

* **Auto-index + grounded row (Task 2 / T-41-04, T-41-06, T-41-06b, T-41-07):**
  building the FROZEN :func:`crawler.searchindex.build_index` over
  ``fixtures/dli/golden/`` auto-indexes each doc with ZERO indexer change
  (``chunk_id = dli/<DLI#>.md#000``, ``source_type='dli'``, ``crawl_date``
  populated); the ONE shipped row ``study.dli.designation`` (dedicated inert
  ``factor_ids``) validates + grounds a verbatim current-status span through the
  FROZEN registry/grounding gate; NO ``safe.dli_snapshot.max_age`` row exists;
  and the new ``factor_ids`` leave ``additional.study`` + the required grid
  byte-for-byte unchanged.

Stdlib ``unittest`` ONLY, run via pytest (repo convention). The single live
endpoint-contract test is skip-guarded by ``PR_LIVE_DLI`` so CI stays offline.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_dli_grounding.py -q
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from crawler import crs_rules, dli_snapshot, searchindex
from crawler.crs_rules import REQUIRED_RULE_IDS, _covers
from crawler.models.crs_rules import Registry

# --------------------------------------------------------------------------- #
# Fixed offline coordinates (repo-root anchored — no network, no real corpus).
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "crawler" / "tests" / "fixtures" / "dli"
_SAMPLE = _FIXTURES / "dli-sample.json"
# The golden ROOT (index root) whose CHILD is `dli/` — so relpath = `dli/<DLI#>.md`
# and chunk_id = `dli/<DLI#>.md#000`. NOT under any `corpus/` dir (.gitignore:8).
_GOLDEN_ROOT = _FIXTURES / "golden"
_GOLDEN_DLI = _GOLDEN_ROOT / "dli"

# The grounded citation anchor + its exact ASCII current-status span.
_UOFT_DOC = _GOLDEN_DLI / "O19332746152.md"
_UOFT_CHUNK_ID = "dli/O19332746152.md#000"
_MARKER = "DLI number: O19332746152"

# The exact authoritative Last-Modified the committed golden was pinned to
# (41-01: live payload `Last-Modified: Thu, 16 Jul 2026 18:08:26 GMT`).
_LAST_MODIFIED = "Thu, 16 Jul 2026 18:08:26 GMT"

# The one row this phase ships, on its dedicated inert namespace.
_RULE_ID = "study.dli.designation"

# The frozen decider row file that must stay byte-for-byte untouched.
_ADDITIONAL_YAML = _REPO_ROOT / "crawler" / "data" / "crs_rules" / "additional.yaml"
_STUDY_DLI_YAML = _REPO_ROOT / "crawler" / "data" / "crs_rules" / "study_dli.yaml"


def _regenerate(out_root: Path) -> Path:
    """Regenerate the whole golden family from the curated sample into *out_root*.

    Mirrors the exact generator call the committed golden was produced by
    (``normalize`` over the sample at the pinned ``as_of`` → ``write`` into the
    ``dli/`` leaf). Returns the ``dli/`` directory the family was written to.
    """
    payload = json.loads(_SAMPLE.read_text(encoding="utf-8"))
    as_of = dli_snapshot.as_of_from(_LAST_MODIFIED)
    docs = dli_snapshot.normalize(payload, as_of=as_of)
    out_dir = out_root / "dli"
    dli_snapshot.write(docs, out_dir=out_dir)
    return out_dir


def _build_golden_index(db: Path) -> None:
    """Build the FROZEN FTS5 index over the committed golden ROOT into *db*."""
    searchindex.build_index(_GOLDEN_ROOT, db)


# Module-level index over the committed golden family (built once, read-only).
_TMP: tempfile.TemporaryDirectory | None = None
_DB: Path | None = None


def setUpModule() -> None:  # noqa: N802 (unittest hook name)
    global _TMP, _DB
    _TMP = tempfile.TemporaryDirectory()
    _DB = Path(_TMP.name) / "golden-index.db"
    _build_golden_index(_DB)


def tearDownModule() -> None:  # noqa: N802 (unittest hook name)
    if _TMP is not None:
        _TMP.cleanup()


# --------------------------------------------------------------------------- #
# Task 1 — golden byte-identity + landmine coverage (T-41-01 / T-41-06).
# --------------------------------------------------------------------------- #
class GoldenFamilyByteIdentity(unittest.TestCase):
    def test_golden_uoft_doc_exists_starts_with_front_matter_and_carries_marker(self) -> None:
        self.assertTrue(_UOFT_DOC.is_file(), f"missing golden doc {_UOFT_DOC}")
        text = _UOFT_DOC.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---"), "golden doc must start with front-matter")
        # The exact ASCII current-status line the grounded row cites.
        self.assertIn(f"\n{_MARKER}\n", text)

    def test_golden_manifest_exists_and_is_not_md(self) -> None:
        manifest = _GOLDEN_DLI / "manifest.json"
        self.assertTrue(manifest.is_file(), "golden manifest.json must exist")
        self.assertFalse(manifest.name.endswith(".md"), "manifest must be non-.md (non-indexed)")
        # It is valid JSON and never an indexable front-matter doc.
        json.loads(manifest.read_text(encoding="utf-8"))

    def test_every_golden_file_is_committable(self) -> None:
        # `git check-ignore` exits 0 when a path IS ignored, 1 when none match.
        files = sorted(_GOLDEN_DLI.iterdir())
        self.assertTrue(files, "golden family must not be empty")
        for f in files:
            proc = subprocess.run(
                ["git", "check-ignore", "-q", str(f)],
                cwd=str(_REPO_ROOT),
                capture_output=True,
            )
            self.assertNotEqual(
                proc.returncode, 0,
                f"golden file is git-ignored (not committable): {f}",
            )

    def test_committed_golden_is_byte_identical_to_fresh_regeneration(self) -> None:
        # Pitfall 6: a drifted / hand-edited golden fails LOUD here.
        with tempfile.TemporaryDirectory() as tmp:
            fresh_dir = _regenerate(Path(tmp))
            committed = {p.name: p.read_bytes() for p in sorted(_GOLDEN_DLI.iterdir())}
            fresh = {p.name: p.read_bytes() for p in sorted(fresh_dir.iterdir())}
            self.assertEqual(
                set(committed), set(fresh),
                "committed golden file set differs from a fresh regeneration",
            )
            for name in committed:
                self.assertEqual(
                    committed[name], fresh[name],
                    f"committed golden {name} is not byte-identical to fresh output",
                )

    def test_regeneration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            da = _regenerate(Path(a))
            db = _regenerate(Path(b))
            fa = {p.name: p.read_bytes() for p in sorted(da.iterdir())}
            fb = {p.name: p.read_bytes() for p in sorted(db.iterdir())}
            self.assertEqual(fa, fb, "two regenerations are not byte-identical")

    def test_golden_family_covers_every_landmine(self) -> None:
        bodies = {
            p.name: p.read_text(encoding="utf-8")
            for p in _GOLDEN_DLI.glob("*.md")
        }
        # Multi-campus: University of Toronto has TWO campus rows.
        uoft = bodies["O19332746152.md"]
        self.assertEqual(uoft.count("| Yes |"), 2, "U-of-T must have two campus PGWP rows")
        # Multi-campus (larger): Eastern College has THREE campus rows.
        eastern = bodies["O112937696097.md"]
        self.assertEqual(eastern.count("| No |"), 3, "Eastern must have three campus rows")
        # Shared-DLI name UNION: O19305471522 lists three distinct institution names.
        waterloo = bodies["O19305471522.md"]
        self.assertIn("Conrad Grebel University College;", waterloo)
        self.assertIn("University of Waterloo", waterloo)
        self.assertIn("St. Jerome", waterloo)  # the U+2019 name is unioned in
        # Conflicting per-campus PGWP: Cestar has BOTH `No` and `Details`, never collapsed.
        cestar = bodies["O153601941355.md"]
        self.assertIn("| No |", cestar)
        self.assertIn("| Details |", cestar)
        # Trailing-space strip: `DLI #` "O110120953397 " normalized -> file exists sans space.
        self.assertIn("O110120953397.md", bodies)
        self.assertIn("DLI number: O110120953397\n", bodies["O110120953397.md"])
        # Non-ASCII NFC preserved: "Cestar Collège" (é) survives verbatim.
        self.assertIn("Cestar Coll\u00e8ge", cestar)
        # All three PGWP tri-state values are represented across the family.
        joined = "".join(bodies.values())
        for value in ("| Yes |", "| No |", "| Details |"):
            self.assertIn(value, joined, f"missing PGWP value {value!r} in family")


# --------------------------------------------------------------------------- #
# Task 2 — auto-index + grounded row + no-max-age + inert coverage.
# --------------------------------------------------------------------------- #
class DliAutoIndexAndGrounding(unittest.TestCase):
    def test_frozen_builder_auto_indexes_the_dli_family(self) -> None:
        # resolve() returns EXACTLY {chunk_id, relpath, source_url, title, section,
        # crawl_date, text} — it does NOT expose source_type.
        chunk = searchindex.resolve(_DB, _UOFT_CHUNK_ID)
        self.assertIsNotNone(chunk, f"{_UOFT_CHUNK_ID} did not auto-index")
        self.assertEqual(chunk["chunk_id"], _UOFT_CHUNK_ID)
        self.assertEqual(chunk["relpath"], "dli/O19332746152.md")
        self.assertTrue(chunk["crawl_date"], "crawl_date must be populated (auto-index proof)")
        self.assertEqual(chunk["crawl_date"], "2026-07-16T18:08:26Z")
        self.assertIn(_MARKER, chunk["text"])
        # source_type is only readable via a direct parameter-bound SELECT.
        con = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT source_type FROM chunks WHERE chunk_id = ?",
                (_UOFT_CHUNK_ID,),
            ).fetchone()
        finally:
            con.close()
        self.assertIsNotNone(row, "chunk row missing from the built DB")
        self.assertEqual(row[0], "dli", "source_type must be 'dli' (front-matter auto-indexed)")

    def test_study_dli_yaml_contributes_exactly_one_row(self) -> None:
        reg = crs_rules.load_registry()
        dli_rows = [r for r in reg.rows if r.selector.family == "dli"]
        self.assertEqual(len(dli_rows), 1, "study_dli.yaml must ship EXACTLY ONE dli-family row")
        row = dli_rows[0]
        self.assertEqual(row.rule_id, _RULE_ID)
        self.assertEqual(row.factor_ids, [_RULE_ID])  # dedicated inert namespace
        self.assertEqual(row.factor_group, "additional_points")
        self.assertEqual(row.selector.marker, _MARKER)

    def test_row_validates_and_grounds_against_golden_index(self) -> None:
        # Scope to the dli family: validating the FULL registry against a
        # dli-only index would (correctly) fail every non-dli row.
        dli_only = Registry(
            rows=[r for r in crs_rules.load_registry().rows if r.selector.family == "dli"]
        )
        report = crs_rules.validate_registry(dli_only, _DB)
        self.assertEqual(report["violations"], [], f"unexpected violations: {report['violations']}")
        self.assertEqual(report["grounded"], report["total"])
        self.assertEqual(report["total"], 1)

        rwc = crs_rules.retrieve_what_you_cite(dli_only, _DB)
        self.assertIn(_RULE_ID, rwc)
        self.assertEqual(rwc[_RULE_ID]["selected_chunk_id"], _UOFT_CHUNK_ID)
        self.assertIs(rwc[_RULE_ID]["agrees_with_citation"], True)
        self.assertIs(rwc[_RULE_ID]["grounds"], True)

    def test_no_max_age_row_exists(self) -> None:
        reg = crs_rules.load_registry()
        for row in reg.rows:
            self.assertNotIn("max_age", row.rule_id)
            self.assertNotIn("snapshot_max_age", row.rule_id)
            self.assertNotEqual(row.machine_check.field, "snapshot_max_age")
        # And the shipped YAML carries no max-age / bound / window key.
        yaml_text = _STUDY_DLI_YAML.read_text(encoding="utf-8")
        for forbidden in ("max_age", "snapshot_max_age", "window_days"):
            self.assertNotIn(forbidden, yaml_text, f"study_dli.yaml must not carry {forbidden!r}")

    def test_row_is_inert_and_leaves_grid_and_decider_unchanged(self) -> None:
        reg = crs_rules.load_registry()
        # Coverage stays complete and additional.study is still present.
        cov = crs_rules.coverage_report(reg)
        self.assertIs(cov["complete"], True)
        self.assertIn("additional.study", cov["by_group"]["additional_points"]["present"])
        # The inert row covers NO required additional-points grid label.
        for label in REQUIRED_RULE_IDS["additional_points"]:
            self.assertFalse(
                _covers(_RULE_ID, label),
                f"{_RULE_ID} must not cover required label {label!r}",
            )
        # The frozen credential-only study decider row file is byte-for-byte untouched.
        proc = subprocess.run(
            ["git", "diff", "--quiet", "--", str(_ADDITIONAL_YAML)],
            cwd=str(_REPO_ROOT),
        )
        self.assertEqual(proc.returncode, 0, "additional.yaml must be unchanged (git diff --quiet)")


# --------------------------------------------------------------------------- #
# Optional live endpoint contract — default-skipped (offline CI). PR_LIVE_DLI=1.
# --------------------------------------------------------------------------- #
class LiveDliSchemaContract(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("PR_LIVE_DLI"),
        "LIVE-ONLY: set PR_LIVE_DLI=1 to hit the fixed IRCC dli-full-list.json "
        "endpoint and assert its schema contract (default-skipped so CI stays offline)",
    )
    def test_live_dli_full_list_schema_contract(self) -> None:
        payload, _last_modified = dli_snapshot.fetch()
        self.assertIsInstance(payload, dict)
        self.assertEqual(set(payload), {"data"}, "top-level must be exactly {'data'}")
        data = payload["data"]
        self.assertIsInstance(data, list)
        self.assertTrue(data, "live data must be non-empty")
        nine_keys = {
            "Province", "Institution", "DLI #", "City", "Campus",
            "Grad Program", "PGWP", "HTML", "Public/Private",
        }
        for row in data:
            self.assertEqual(set(row), nine_keys, "each row must carry the nine known keys")
            self.assertIn(row["PGWP"], {"Yes", "No", "Details"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
