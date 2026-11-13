"""SC4 privacy-perimeter proof for the CRS audit slice (Phase 32 — AUDIT-06).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Proves end-to-end that
the ``vault audit`` public boundary is PII-light while the vault report retains
the evidence, and that the report artifact type is publish-safe covered.

* (a) the ``--json`` stdout envelope carries NEITHER a sentinel applicant value,
  NOR the ``ev_`` evidence id, NOR any absolute filesystem path (only the
  vault-relative private path);
* (b) the on-disk vault report JSON + MD DO carry the sentinel value + ``ev_`` id;
* (c) ``claims[]`` carry only corpus ``relpath#ordinal`` citation ids (no ``ev_``);
* (d) the publish-safe checker flags a tracked ``output/crs-audit/*.json`` report
  and a tracked ``*.sqlite`` vault DB as ``VAULT_ARTIFACT``.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_audit_pii_perimeter.py -q
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from crawler.tests.test_vault_audit_cli import _AuditCliCase
from crawler.tests.test_auditor import _language_registry

_REPO_ROOT = Path(__file__).resolve().parents[2]
# A distinctive applicant-value sentinel that maps to the upper benchmark band.
_SENTINEL_RAW = 8.135791


def _load_cps():
    """Import scripts/check_publish_safe (scripts/ is NOT a package → sys.path shim)."""
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # noqa: E402
    return cps


class TestAuditPiiPerimeter(_AuditCliCase):
    def _seed_with_sentinel(self):
        scores = self._all(7.5)
        scores["reading"] = _SENTINEL_RAW
        v = self._seed_vault(scores)
        ev_id = v.con.execute(
            "SELECT evidence_id FROM documents").fetchone()[0]
        v.con.close()
        return v, ev_id

    def test_stdout_is_pii_light_report_is_evidence_bearing(self) -> None:
        v, ev_id = self._seed_with_sentinel()
        rc, out, _ = self._run(
            ["--json", "vault", "audit", "--candidate", "default",
             "--db", str(self.db)], _language_registry())
        self.assertEqual(rc, 0)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])

        # (a) stdout carries NO sentinel value, NO ev_ id, NO absolute path.
        self.assertNotIn(str(_SENTINEL_RAW), out)
        self.assertNotIn(ev_id, out)
        self.assertNotIn("ev_", out)
        self.assertNotIn(self._tmp.name, out)  # no absolute tempdir path leaked
        self.assertFalse(env["result"]["private_output_path"].startswith("/"))
        self.assertTrue(env["result"]["private_output_path"].startswith(
            "output/crs-audit/"))
        self.assertNotIn("candidates/", env["result"]["private_output_path"])

        # (b) the on-disk vault report DOES carry the sentinel + ev_ id.
        run_id = env["result"]["run_id"]
        crs_dir = v.root / "output" / "crs-audit"
        json_text = (crs_dir / f"{run_id}.json").read_text(encoding="utf-8")
        md_text = (crs_dir / f"{run_id}.md").read_text(encoding="utf-8")
        self.assertIn(str(_SENTINEL_RAW), json_text)
        self.assertIn(ev_id, json_text)
        self.assertIn(ev_id, md_text)

        # (c) claims carry ONLY corpus citation ids (none ev_-shaped).
        for claim in env["result"]["claims"]:
            self.assertFalse(claim["citation_id"].startswith("ev_"))
            self.assertIn("#", claim["citation_id"])

    def test_publish_safe_flags_report_and_vault_db(self) -> None:
        cps = _load_cps()
        report_path = "personal/candidates/x/output/crs-audit/aud_x.json"
        db_path = "personal/candidates/x/vault.sqlite"
        self.assertTrue(cps.scan_vault_artifact(report_path))
        self.assertEqual(
            cps.scan_vault_artifact(report_path)[0].category, "VAULT_ARTIFACT")
        self.assertTrue(cps.scan_vault_artifact(db_path))
        self.assertEqual(
            cps.scan_vault_artifact(db_path)[0].category, "VAULT_ARTIFACT")
        # An MD report is flagged too (scoped to the crs-audit subtree).
        md_report = "personal/candidates/x/output/crs-audit/aud_x.md"
        self.assertTrue(cps.scan_vault_artifact(md_report))

    def test_publish_safe_does_not_flag_ordinary_repo_json(self) -> None:
        cps = _load_cps()
        # An ordinary repo JSON/MD OUTSIDE a vault subtree is NOT flagged.
        self.assertEqual(cps.scan_vault_artifact("crawler/CONTRACT.md"), [])
        self.assertEqual(cps.scan_vault_artifact("pyproject.toml"), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
