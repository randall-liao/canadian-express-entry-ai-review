"""v4.1 SAFE-06 conformance — remediation/packet privacy containment (release gate).

Authoritative, marker-tagged consolidation proving:
  * remediation + packet DEFAULT stdout summaries are PII-light (no ev_, no applicant
    value, vault-relative path);
  * the full remediation checklist + review packet write ONLY under the vault subtrees
    (the packet drops ev_; the checklist keeps it vault-only);
  * both output subtrees are unstageable (publish-safe VAULT_SUBTREES + scan_vault_artifact),
    and the tracked tree scans clean;
  * non-vault writes / missing prerequisites / rendered leaks fail closed with zero
    artifacts.

Stdlib ``unittest`` ONLY. Uses a SYNTHETIC completed audit run so the whole path runs
UNGUARDED (no corpus/index.db needed).
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from pydantic import ValidationError

from crawler import (
    auditors,
    cli,
    contract,
    crs_rules,
    paths,
    remediation,
    review_packet,
    vault,
)
from crawler.models.audit import PrivateAuditReport, PrivateFactorCard

pytestmark = pytest.mark.conformance

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_cps():
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # noqa: E402
    return cps


def _run_json(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return json.loads(buf.getvalue()), code


def _real_cites(registry, factor_id, n=2):
    wanted = set(auditors.consumed_factor_ids(factor_id))
    ids = []
    for row in registry.rows:
        if wanted.intersection(row.factor_ids):
            for c in row.citations:
                if c.chunk_id not in ids:
                    ids.append(c.chunk_id)
    return ids[:n]


class RemediationPacketPrivacy(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.personal = Path(self._tmp.name)
        self._prev = os.environ.get("PR_PERSONAL_DIR")
        os.environ["PR_PERSONAL_DIR"] = str(self.personal)
        self.candidate = "safe6"
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

    def _seed(self) -> str:
        run_id = vault.record_audit_run(
            self.v, candidate_id=self.candidate, factor_id="*full-grid*",
            rule_registry_version=vault.rule_registry_version(self.v),
            status="running")
        card = PrivateFactorCard(
            factor_id="core.language.first", factor_group="core_human_capital",
            verdict="GAP", reason_code="missing_evidence",
            rule_citation_ids=_real_cites(self.registry, "core.language.first"),
            evidence_ids=["ev_secretpii42"])
        report = PrivateAuditReport(
            run_id=run_id, candidate_id=self.candidate, factor_cards=[card],
            registry_fingerprint=crs_rules.registry_fingerprint(self.registry))
        out = paths.resolve_within(self.v.root, "output", "crs-audit")
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{run_id}.json").write_text(
            json.dumps(report.model_dump(), ensure_ascii=False), encoding="utf-8")
        vault.complete_audit_run(
            self.v, run_id, status="complete",
            report_relpath=f"candidates/{self.candidate}/output/crs-audit/{run_id}.json")
        return run_id

    def _cand_dir(self, *parts):
        return self.personal.joinpath("candidates", self.candidate, *parts)

    # -- PII-light stdout + vault-only artifacts --------------------------- #
    def test_remediate_and_packet_stdout_are_pii_light(self) -> None:
        self._seed()
        for verb in ("remediate", "review-packet"):
            env, code = _run_json(["--json", "vault", verb, "--candidate", self.candidate])
            self.assertTrue(env["ok"], verb)
            blob = json.dumps(env["result"])
            self.assertNotIn("ev_", blob, verb)
            self.assertNotIn("secretpii42", blob, verb)
            self.assertFalse(
                env["result"]["private_output_path"].startswith("/"), verb)
            self.assertTrue(
                env["result"]["private_output_path"].startswith("output/"), verb)
            self.assertNotIn(
                self.candidate, env["result"]["private_output_path"], verb)

    def test_full_artifacts_are_vault_only(self) -> None:
        self._seed()
        _run_json(["--json", "vault", "remediate", "--candidate", self.candidate])
        _run_json(["--json", "vault", "review-packet", "--candidate", self.candidate])
        # Checklist JSON keeps ev_ (vault-only); packet JSON drops it.
        rem = list(self._cand_dir("output", "remediation").glob("*.json"))
        pkt = list(self._cand_dir("output", "review-packet").glob("*.json"))
        self.assertTrue(rem and pkt)
        self.assertIn("ev_secretpii42", rem[0].read_text())
        self.assertNotIn("ev_", pkt[0].read_text())

    # -- unstageable subtrees + tracked tree clean ------------------------- #
    def test_both_subtrees_are_unstageable(self) -> None:
        cps = _load_cps()
        self.assertIn("output/remediation/", cps.VAULT_SUBTREES)
        self.assertIn("output/review-packet/", cps.VAULT_SUBTREES)
        self.assertTrue(cps.scan_vault_artifact(
            "personal/candidates/x/output/remediation/rem_x.json"))
        self.assertTrue(cps.scan_vault_artifact(
            "personal/candidates/x/output/review-packet/pkt_x.md"))

    def test_tracked_tree_scans_clean(self) -> None:
        cps = _load_cps()
        self.assertEqual(cps.main(), 0)

    # -- non-vault / fail-closed ------------------------------------------- #
    def test_write_paths_reject_escape(self) -> None:
        for subtree in ("remediation", "review-packet"):
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(
                    self.v.root, "output", subtree, "../../escape.json")

    def test_missing_prerequisite_refuses_zero_artifacts(self) -> None:
        for verb in ("remediate", "review-packet"):
            env, code = _run_json(["--json", "vault", verb, "--candidate", self.candidate])
            self.assertFalse(env["ok"], verb)
            self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)
            self.assertEqual(code, contract.EXIT_INVALID_INPUT)
            self.assertIn("reason=no_completed_audit", env["error"]["message"])
        self.assertFalse(self._cand_dir("output", "remediation").exists())
        self.assertFalse(self._cand_dir("output", "review-packet").exists())

    def test_rendered_leak_refuses_before_write(self) -> None:
        run_id = self._seed()
        orig = remediation.build_remediation

        def _leaky(report, registry):
            cl = orig(report, registry)
            if cl.items and cl.items[0].citations:
                cl.items[0].citations[0].quote = "/home/user/secret.pdf"
            return cl

        remediation.build_remediation = _leaky
        try:
            env, code = _run_json(
                ["--json", "vault", "review-packet", "--candidate", self.candidate,
                 "--audit-run-id", run_id])
        finally:
            remediation.build_remediation = orig
        self.assertFalse(env["ok"])
        self.assertIn("reason=rendered_leak", env["error"]["message"])
        self.assertFalse(self._cand_dir("output", "review-packet").exists())

    def test_audit_bad_db_refuses(self) -> None:
        self._seed()
        env, code = _run_json(
            ["--json", "vault", "audit", "--candidate", self.candidate, "--all",
             "--db", str(self.personal / "no-such-index.db")])
        self.assertFalse(env["ok"])
        self.assertEqual(code, contract.EXIT_INVALID_INPUT)
        self.assertIn("reason=index_missing", env["error"]["message"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
