"""CLI-level proof for `vault remediate` (REM-04).

Uses a SYNTHETIC completed audit run (written directly under the vault) so the whole
path — report load, projection, vault-only write, PII-light stdout, and every
fail-closed refusal — runs UNGUARDED (no corpus/index.db, no real `vault audit`).
Stdlib unittest ONLY; the vault lives under a tempdir via PR_PERSONAL_DIR.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from crawler import auditors, cli, contract, crs_rules, paths, vault
from crawler.models.audit import PrivateAuditReport, PrivateFactorCard


def _run_json(argv: list[str]) -> tuple[dict, int]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return json.loads(buf.getvalue()), code


def _real_cites(registry, factor_id, n=2) -> list[str]:
    wanted = set(auditors.consumed_factor_ids(factor_id))
    ids: list[str] = []
    for row in registry.rows:
        if wanted.intersection(row.factor_ids):
            for c in row.citations:
                if c.chunk_id not in ids:
                    ids.append(c.chunk_id)
    return ids[:n]


class RemediateCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.personal = Path(self._tmp.name)
        self._prev = os.environ.get("PR_PERSONAL_DIR")
        os.environ["PR_PERSONAL_DIR"] = str(self.personal)
        self.candidate = "rem"
        self.registry = crs_rules.load_registry()
        v = vault.open_vault(self.candidate)
        vault.create_candidate(v, self.candidate)
        self.v = v

    def tearDown(self) -> None:
        self.v.con.close()
        if self._prev is None:
            os.environ.pop("PR_PERSONAL_DIR", None)
        else:
            os.environ["PR_PERSONAL_DIR"] = self._prev
        self._tmp.cleanup()

    # -- helpers ------------------------------------------------------------ #
    def _seed_completed_report(self, cards, *, bad_report=False) -> str:
        """Write a synthetic PrivateAuditReport + a completed audit_runs row.

        Returns the minted audit_run_id. When ``bad_report`` the report file is NOT
        written (so _load_report must fail closed with audit_report_unreadable).
        """
        run_id = vault.record_audit_run(
            self.v, candidate_id=self.candidate, factor_id="*full-grid*",
            rule_registry_version=vault.rule_registry_version(self.v),
            status="running")
        report = PrivateAuditReport(
            run_id=run_id, candidate_id=self.candidate, factor_cards=cards)
        subtree = ("output", "crs-audit")
        out_dir = paths.resolve_within(self.v.root, *subtree)
        out_dir.mkdir(parents=True, exist_ok=True)
        relpath = f"candidates/{self.candidate}/output/crs-audit/{run_id}.json"
        if not bad_report:
            (out_dir / f"{run_id}.json").write_text(
                json.dumps(report.model_dump(), ensure_ascii=False), encoding="utf-8")
        vault.complete_audit_run(
            self.v, run_id, status="complete", report_relpath=relpath)
        return run_id

    def _remediation_files(self) -> list[Path]:
        d = self.personal / "candidates" / self.candidate / "output" / "remediation"
        return list(d.glob("*")) if d.exists() else []

    def _gap_card(self):
        return PrivateFactorCard(
            factor_id="core.language.first", factor_group="core_human_capital",
            verdict="GAP", reason_code="missing_evidence",
            rule_citation_ids=_real_cites(self.registry, "core.language.first"),
            evidence_ids=["ev_secret999"])

    # -- happy path (UNGUARDED) --------------------------------------------- #
    def test_remediate_writes_vault_only_pii_light(self) -> None:
        self._seed_completed_report([self._gap_card()])
        env, code = _run_json(
            ["--json", "vault", "remediate", "--candidate", self.candidate])
        self.assertTrue(env["ok"])
        self.assertEqual(code, 0)
        result = env["result"]
        self.assertEqual(result["item_count"], 1)
        self.assertEqual(result["counts"]["gap"], 1)
        # PII-light: no ev_ pointer, vault-relative path
        blob = json.dumps(result)
        self.assertNotIn("ev_", blob)
        self.assertTrue(result["private_output_path"].startswith(
            "output/remediation/"))
        self.assertNotIn("candidates/", result["private_output_path"])
        # Files written ONLY under the vault subtree; MD carries the screening notice.
        files = self._remediation_files()
        self.assertEqual(len(files), 2)  # .json + .md
        md = next(f for f in files if f.suffix == ".md").read_text()
        self.assertIn("Substantiation screening", md)
        # The full checklist JSON DOES carry the ev_ pointer (vault-only).
        js = next(f for f in files if f.suffix == ".json").read_text()
        self.assertIn("ev_secret999", js)

    def test_remediate_specific_run_id(self) -> None:
        run_id = self._seed_completed_report([self._gap_card()])
        env, code = _run_json(
            ["--json", "vault", "remediate", "--candidate", self.candidate,
             "--audit-run-id", run_id])
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["source_audit_run_id"], run_id)

    # -- refusals (UNGUARDED, zero artifacts) ------------------------------- #
    def _assert_refusal(self, argv, reason) -> None:
        env, code = _run_json(argv)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)
        self.assertEqual(code, contract.EXIT_INVALID_INPUT)
        self.assertIn(f"reason={reason}", env["error"]["message"])
        self.assertNotIn("ev_", env["error"]["message"])
        self.assertEqual(self._remediation_files(), [])

    def test_refusal_no_completed_audit(self) -> None:
        self._assert_refusal(
            ["--json", "vault", "remediate", "--candidate", self.candidate],
            "no_completed_audit")

    def test_refusal_audit_run_not_found(self) -> None:
        self._assert_refusal(
            ["--json", "vault", "remediate", "--candidate", self.candidate,
             "--audit-run-id", "aud_doesnotexist"],
            "audit_run_not_found")

    def test_refusal_audit_report_unreadable(self) -> None:
        # A completed run whose report file was never written -> fail closed.
        self._seed_completed_report([self._gap_card()], bad_report=True)
        self._assert_refusal(
            ["--json", "vault", "remediate", "--candidate", self.candidate],
            "audit_report_unreadable")

    def test_refusal_registry_drift(self) -> None:
        # A report stamped with a stale registry fingerprint -> fail closed
        # (never re-derive a verbatim span the audit did not ground).
        run_id = vault.record_audit_run(
            self.v, candidate_id=self.candidate, factor_id="*full-grid*",
            rule_registry_version=vault.rule_registry_version(self.v),
            status="running")
        report = PrivateAuditReport(
            run_id=run_id, candidate_id=self.candidate,
            factor_cards=[self._gap_card()],
            registry_fingerprint="stale-fingerprint-that-will-never-match")
        out_dir = paths.resolve_within(self.v.root, "output", "crs-audit")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{run_id}.json").write_text(
            json.dumps(report.model_dump(), ensure_ascii=False), encoding="utf-8")
        vault.complete_audit_run(
            self.v, run_id, status="complete",
            report_relpath=f"candidates/{self.candidate}/output/crs-audit/{run_id}.json")
        self._assert_refusal(
            ["--json", "vault", "remediate", "--candidate", self.candidate],
            "registry_drift")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
