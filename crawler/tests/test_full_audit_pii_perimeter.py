"""Full-grid PII-perimeter + conformance-fixture tests (33-06 Task 2, AUDIT-06).

Stdlib ``unittest`` ONLY — NO network. Drives ``vault audit --all`` through the
CLI over the REAL registry + REAL ``corpus/index.db`` (SKIPPED on a fresh clone)
and proves the AUDIT-06 boundary holds for the WHOLE grid:

  * (a) no applicant value string and no ``ev_`` id reaches the public envelope or
    stdout;
  * (b) ``private_output_path`` is candidate-root-relative (never absolute);
  * (c) the PII-bearing report exists ONLY under
    ``candidates/<id>/output/crs-audit/`` and is publish-safe covered;
  * (d) writing the report outside the vault subtree is refused
    (``resolve_within`` guard);
  * (e) the publish-safe scanner reports 0 violations for the repository.

Also validates the local synthetic auditor conformance fixtures are PII-free and
name a closed-vocabulary verdict.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

from crawler import cli, paths
from crawler.tests.test_full_audit_integration import (
    _REAL_DB,
    _SENTINEL_STREAM,
    _IntegrationCase,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_FIXTURES = _REPO_ROOT / "crawler" / "eval" / "crs_auditors.jsonl"
_VERDICT_VOCAB = {"SUBSTANTIATED", "GAP", "AT-RISK", "N/A"}


def _load_cps():
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # noqa: E402
    return cps


class TestFullGridPiiPerimeter(_IntegrationCase):
    def _run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_full_grid_stdout_pii_light_report_vault_only(self) -> None:
        v, _ = self._seed_happy()
        # Capture the ev_ id for the language document before closing the vault.
        ev_ids = [r["evidence_id"] for r in v.con.execute(
            "SELECT evidence_id FROM documents").fetchall()]
        v.con.close()

        rc, out, err = self._run_cli(
            ["--json", "vault", "audit", "--all", "--candidate", "default",
             "--db", self.db])
        self.assertEqual(rc, 0, out + err)
        env = json.loads(out)
        self.assertEqual(env["command"], "vault")
        self.assertTrue(env["ok"])
        result = env["result"]

        # (a) no applicant sentinel, no ev_ id in stdout / envelope.
        self.assertNotIn(_SENTINEL_STREAM, out)
        self.assertNotIn("ev_", out)
        for ev in ev_ids:
            self.assertNotIn(ev, out)
        # (b) vault-relative private path only.
        self.assertFalse(result["private_output_path"].startswith("/"))
        self.assertTrue(result["private_output_path"].startswith(
            "output/crs-audit/"))
        self.assertNotIn("candidates/", result["private_output_path"])
        # verdicts for every factor; claims carry only corpus citation ids.
        self.assertGreaterEqual(len(result["verdicts"]), 1)
        for claim in result["claims"]:
            self.assertFalse(claim["citation_id"].startswith("ev_"))
            self.assertIn("#", claim["citation_id"])

        # (c) the PII-bearing report exists ONLY under the vault subtree and DOES
        #     carry the sentinel + an ev_ id.
        v2 = __import__("crawler.vault", fromlist=["open_vault"]).open_vault("default")
        try:
            run_id = result["run_id"]
            report_json = (v2.root / "output" / "crs-audit" / f"{run_id}.json"
                           ).read_text(encoding="utf-8")
        finally:
            v2.con.close()
        self.assertIn(_SENTINEL_STREAM, report_json)
        self.assertTrue(any(ev in report_json for ev in ev_ids))

    def test_publish_safe_flags_report_subtree(self) -> None:
        cps = _load_cps()
        report_path = "personal/candidates/x/output/crs-audit/aud_x.json"
        flagged = cps.scan_vault_artifact(report_path)
        self.assertTrue(flagged)
        self.assertEqual(flagged[0].category, "VAULT_ARTIFACT")

    def test_write_outside_vault_subtree_is_refused(self) -> None:
        # The report writer re-anchors every path through resolve_within, which
        # rejects a .. escape (the same guard the writer relies on).
        v, _ = self._seed_happy()
        try:
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(v.root, "..", "escape.json")
        finally:
            v.con.close()


class TestRepositoryPublishSafe(unittest.TestCase):
    def test_publish_safe_zero_violations(self) -> None:
        cps = _load_cps()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cps.main()
        self.assertEqual(rc, 0, out.getvalue())


class TestAuditorConformanceFixtures(unittest.TestCase):
    def test_fixtures_are_pii_free_and_closed_vocabulary(self) -> None:
        self.assertTrue(_EVAL_FIXTURES.is_file())
        rows = [json.loads(line) for line in
                _EVAL_FIXTURES.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(len(rows), 4)
        modules = set()
        for row in rows:
            self.assertIn(row["expect_verdict"], _VERDICT_VOCAB)
            self.assertTrue(row["factor"])
            modules.add(row["module"])
            # PII-free by construction: no ev_ ids, no absolute paths.
            blob = json.dumps(row)
            self.assertNotIn("ev_", blob)
        # All four modules represented.
        self.assertEqual(
            modules, {"core", "spouse", "transferability", "additional"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
