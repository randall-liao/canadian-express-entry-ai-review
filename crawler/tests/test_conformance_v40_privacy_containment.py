"""SAFE-02 authoritative privacy-containment conformance gate (Phase 34 — Plan 02).

The v4.0 release-gate proof that **the vault is the privacy perimeter**: no PII
can reach stdout, the public JSON envelope, the repo, the corpus, public reports,
tracked fixtures, or any non-vault output path — and non-vault output is refused.
It consolidates the four PII-perimeter proofs shipped across Phases 29/30/32/33
(``test_vault_pii_perimeter`` / ``test_extraction_pii_perimeter`` /
``test_audit_pii_perimeter`` / ``test_full_audit_pii_perimeter``) into ONE
authoritative module that exercises the WHOLE flow end-to-end (seed → confirm →
full-grid audit → report) with distinctive synthetic sentinels, and strengthens
the non-vault-output-refusal + git-staging guarantees.

Stdlib ``unittest`` ONLY — NO network. Every fixture is SYNTHETIC; NEVER real
applicant data. The real-corpus classes are guarded by the shipped
``@skipUnless(corpus/index.db)`` inherited from ``_IntegrationCase``.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_conformance_v40_privacy_containment.py -q
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

from crawler import cli, crs_rules, paths, vault
from crawler.models.audit import PublicAuditEnvelope, PublicClaim
from crawler.models.crs_rules import (
    Citation,
    MachineCheck,
    Registry,
    RuleRow,
    Selector,
    VolatilityMeta,
)
from crawler.models.vault import CrsProfileFactor
from crawler.tests.test_full_audit_integration import (
    _SENTINEL_STREAM,
    _IntegrationCase,
)

pytestmark = pytest.mark.conformance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GITIGNORE = _REPO_ROOT / ".gitignore"
_EVAL_FIXTURES = _REPO_ROOT / "crawler" / "eval" / "crs_auditors.jsonl"
_VERDICT_VOCAB = {"SUBSTANTIATED", "GAP", "AT-RISK", "N/A"}

# Distinctive synthetic applicant-value sentinels — recognizable in leak checks.
# _SENTINEL_STREAM (a fake nomination stream) is imported from the shared seed.
_SENTINEL_SCORE = 7.031791          # a distinctive in-band language raw score
_SENTINEL_DOB = "1987-06-13"        # a distinctive date-of-birth


def _load_cps():
    """Import scripts/check_publish_safe (scripts/ is NOT a package → sys.path shim)."""
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_publish_safe as cps  # noqa: E402 — SAFE-02 share-safety scanner
    return cps


def _ungrounded_registry(registry: Registry) -> Registry:
    """The real registry + one ungrounded consumed core.language.first row."""
    bad = RuleRow(
        rule_id="core.language.first.conformance_ungrounded",
        factor_group="core_human_capital",
        factor_ids=["core.language.first"],
        check_type="admissibility",
        query="synthetic conformance probe",
        selector=Selector(family="guidance"),
        claim_text="synthetic conformance rule",
        citations=[Citation(chunk_id="guidance/job-offer.md#001",
                            quote="this span is absolutely not present zzz")],
        machine_check=MachineCheck(kind="policy_flag", field="x",
                                   flag_value=True),
        volatility=VolatilityMeta(volatility="stable", source_family="guidance"))
    return Registry(rows=list(registry.rows) + [bad])


class _ContainmentCase(_IntegrationCase):
    """A synthetic vault seeded with distinctive sentinels + a CLI capture helper."""

    def _seed_sentinels(self):
        """A full green-ish profile carrying DISTINCTIVE synthetic sentinels."""
        v = self._open()
        today = date.today()
        self._claim(v, "core.age", "core_human_capital",
                    claimed_points=110, claimed_value=25)
        self._claim(v, "core.language.first", "core_human_capital",
                    claimed_points=124, claimed_level="9", claimed_value=9)
        self._claim(v, "additional.nomination", "additional_points",
                    claimed_points=600, claimed_value="nominated")
        # Distinctive DOB sentinel.
        self._doc(v, "passport", "core.age", {"date_of_birth": _SENTINEL_DOB})
        # Distinctive test-score sentinel (still in the CLB-9 band → green).
        self._doc(v, "language_test", "core.language.first", {
            "test_type": "IELTS General Training",
            "test_date": (today - timedelta(days=30)).isoformat(),
            "raw_score_reading": _SENTINEL_SCORE, "raw_score_writing": 7.0,
            "raw_score_listening": 8.0, "raw_score_speaking": 7.0})
        # Distinctive nomination-stream sentinel (the shared _SENTINEL_STREAM).
        self._doc(v, "provincial_nomination", "additional.nomination", {
            "nomination_stream": _SENTINEL_STREAM, "expiry_date": "2099-01-01"})
        rnd = vault.set_ita_round(
            v, "default", "r", today.isoformat(), "EE", cutoff_score=500)
        return v, rnd.round_id

    def _run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _sentinels(self):
        return (_SENTINEL_STREAM, str(_SENTINEL_SCORE), _SENTINEL_DOB)


class TestEndToEndNoPiiToStdoutVaultOnlyReport(_ContainmentCase):
    """The full import→audit flow keeps every sentinel + ev_ id out of stdout /
    the public envelope; the PII-bearing report lives ONLY inside the vault."""

    def test_full_flow_stdout_pii_light_report_vault_only(self) -> None:
        v, _ = self._seed_sentinels()
        ev_ids = [r["evidence_id"] for r in v.con.execute(
            "SELECT evidence_id FROM documents").fetchall()]
        v.con.close()

        rc, out, err = self._run_cli(
            ["--json", "vault", "audit", "--all", "--candidate", "default",
             "--db", self.db])
        self.assertEqual(rc, 0, out + err)
        env = json.loads(out)
        result = env["result"]

        # (a) NO applicant sentinel value anywhere in stdout / the envelope.
        dumped = json.dumps(result)
        for sentinel in self._sentinels():
            self.assertNotIn(sentinel, out, f"sentinel {sentinel!r} on stdout")
            self.assertNotIn(sentinel, dumped, f"sentinel {sentinel!r} in envelope")
        # (b) NO ev_ id in stdout / the envelope; claims cite corpus coordinates.
        self.assertNotIn("ev_", out)
        for ev in ev_ids:
            self.assertNotIn(ev, out)
        for claim in result["claims"]:
            self.assertFalse(claim["citation_id"].startswith("ev_"))
            self.assertIn("#", claim["citation_id"])
        # (c) locator is relative to the selected candidate root.
        self.assertFalse(result["private_output_path"].startswith("/"))
        self.assertTrue(result["private_output_path"].startswith(
            "output/crs-audit/"))
        self.assertNotIn("candidates/", result["private_output_path"])
        self.assertNotIn(self._tmp.name, out)  # no absolute tempdir path leaked

        # (d) the PII-BEARING report lives ONLY under the vault subtree and DOES
        #     carry the sentinels + an ev_ id.
        v2 = vault.open_vault("default")
        try:
            run_id = result["run_id"]
            report_json = (v2.root / "output" / "crs-audit" / f"{run_id}.json"
                           ).read_text(encoding="utf-8")
            report_md = (v2.root / "output" / "crs-audit" / f"{run_id}.md"
                         ).read_text(encoding="utf-8")
        finally:
            v2.con.close()
        self.assertIn(_SENTINEL_STREAM, report_json)
        self.assertTrue(any(ev in report_json for ev in ev_ids))
        self.assertTrue(any(ev in report_md for ev in ev_ids))

    def test_error_path_envelope_is_pii_free(self) -> None:
        # (e) An error/edge path (an ungrounded consumed rule) surfaces a
        #     PII-FREE error envelope — no sentinel / ev_ / tempdir path leaks.
        v, _ = self._seed_sentinels()
        ev_ids = [r["evidence_id"] for r in v.con.execute(
            "SELECT evidence_id FROM documents").fetchall()]
        v.con.close()
        bad = _ungrounded_registry(self.registry)
        snapshot = crs_rules.RegistrySnapshot(
            registry=bad,
            fingerprint=crs_rules.registry_fingerprint(bad),
        )
        with mock.patch.object(
                crs_rules, "load_registry_snapshot", return_value=snapshot):
            rc, out, err = self._run_cli(
                ["--json", "vault", "audit", "--all", "--candidate", "default",
                 "--db", self.db])
        self.assertNotEqual(rc, 0)  # a grounding failure is a non-zero exit
        combined = out + err
        for sentinel in self._sentinels():
            self.assertNotIn(sentinel, combined)
        self.assertNotIn("ev_", combined)
        for ev in ev_ids:
            self.assertNotIn(ev, combined)
        self.assertNotIn(self._tmp.name, combined)


class TestPublicModelFirewall(unittest.TestCase):
    """The public model tier makes an applicant-key / ev_ citation leak impossible
    by CONSTRUCTION — not merely by test."""

    def test_public_claim_rejects_ev_citation_id(self) -> None:
        with self.assertRaises(ValidationError):
            PublicClaim(claim_text="x", citation_id="ev_abc123def456",
                        verdict="GAP")
        # A legitimate corpus coordinate constructs fine.
        PublicClaim(claim_text="x", citation_id="guidance/a.md#001",
                    verdict="GAP")

    def test_envelope_rejects_injected_applicant_key(self) -> None:
        with self.assertRaises(ValidationError):
            PublicAuditEnvelope(
                run_id="aud_deadbeef0015", factor_id="core.language.first",
                private_output_path="output/crs-audit/aud_deadbeef0015.json",
                applicant_name="SYNTHETIC-APPLICANT")  # extra="forbid"

    def test_envelope_rejects_absolute_private_path(self) -> None:
        with self.assertRaises(ValidationError):
            PublicAuditEnvelope(
                run_id="aud_deadbeef0015", factor_id="core.language.first",
                private_output_path="/home/user/candidates/x/aud_x.json")


class TestNonVaultOutputRefused(_IntegrationCase):
    """A private report can never land outside the vault subtree (resolve_within)."""

    def test_dotdot_escape_is_refused(self) -> None:
        v, _ = self._seed_happy()
        try:
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(v.root, "..", "escape.json")
        finally:
            v.con.close()

    def test_symlink_escape_is_refused(self) -> None:
        v, _ = self._seed_happy()
        try:
            outside = Path(self._tmp.name) / "outside"
            outside.mkdir(parents=True, exist_ok=True)
            link = v.root / "escape_link"
            if not link.exists():
                link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(paths.PathEscapeError):
                paths.resolve_within(v.root, "escape_link", "x.json")
        finally:
            v.con.close()

    def test_report_writer_targets_only_the_crs_audit_subtree(self) -> None:
        # The report writer re-anchors every write through the crs-audit subtree.
        v, round_id = self._seed_happy()
        try:
            from crawler import audit_report
            _, envelope = audit_report.run_full_audit_report(
                v, self.db, self.registry, ita_round_id=round_id)
            rel = envelope.private_output_path
        finally:
            v.con.close()
        self.assertTrue(rel.startswith("output/crs-audit/"))
        self.assertNotIn("candidates/", rel)


class TestPublishSafeFlagsVaultArtifacts(unittest.TestCase):
    """scan_vault_artifact flags EVERY vault-artifact type and no ordinary repo JSON."""

    def test_flags_every_vault_artifact_type(self) -> None:
        cps = _load_cps()
        report = "personal/candidates/x/output/crs-audit/aud_x.json"
        report_md = "personal/candidates/x/output/crs-audit/aud_x.md"
        db = "personal/candidates/x/vault.sqlite"
        wal = "personal/candidates/x/vault.sqlite-wal"
        image = "personal/candidates/x/files/rendered/d/page-0001.png"
        ocr = "personal/candidates/x/files/text/d/page-0001.txt"
        for path in (report, report_md, db, wal, image, ocr):
            flagged = cps.scan_vault_artifact(path)
            self.assertTrue(flagged, f"not flagged: {path}")
            self.assertEqual(flagged[0].category, "VAULT_ARTIFACT")

    def test_does_not_flag_ordinary_repo_json_or_md(self) -> None:
        cps = _load_cps()
        # No false positives — an untrustworthy gate would flag ordinary files.
        self.assertEqual(cps.scan_vault_artifact("pyproject.toml"), [])
        self.assertEqual(cps.scan_vault_artifact("crawler/CONTRACT.md"), [])
        self.assertEqual(
            cps.scan_vault_artifact("crawler/data/crs_rules/COVERAGE.md"), [])


class TestGitAddCannotStageVaultArtifacts(unittest.TestCase):
    """`git add -A` cannot stage any vault artifact (the project .gitignore)."""

    def _git(self, cwd: Path, *args: str) -> str:
        env = dict(os.environ)
        env.update({"GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_SYSTEM": "/dev/null"})
        out = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True, capture_output=True, text=True, env=env)
        return out.stdout

    def test_vault_artifacts_stay_unstaged(self) -> None:
        self.assertTrue(_GITIGNORE.is_file())
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            self._git(repo, "init", "-q")
            (repo / ".gitignore").write_bytes(_GITIGNORE.read_bytes())
            base = repo / "personal/candidates/default"
            (base / "output/crs-audit").mkdir(parents=True, exist_ok=True)
            (base / "files/raw").mkdir(parents=True, exist_ok=True)
            (base / "files/rendered").mkdir(parents=True, exist_ok=True)
            (base / "files/text").mkdir(parents=True, exist_ok=True)
            # Every representative vault-artifact type.
            (base / "vault.sqlite").write_bytes(b"SQLite format 3\x00 synthetic")
            (base / "vault.sqlite-wal").write_bytes(b"wal")
            (base / "files/raw/abc.pdf").write_bytes(b"%PDF-1.4 synthetic")
            (base / "files/rendered/page-0001.png").write_bytes(b"\x89PNG synthetic")
            (base / "files/text/page-0001.txt").write_text("synthetic ocr text")
            (base / "output/crs-audit/aud_x.json").write_text('{"synthetic": true}')

            self._git(repo, "add", "-A")
            tracked = self._git(repo, "ls-files")
            status = self._git(repo, "status", "--porcelain")

        self.assertNotIn("candidates", tracked)
        self.assertNotIn(".sqlite", tracked)
        self.assertNotIn(".png", tracked)
        self.assertNotIn("candidates", status)
        self.assertEqual(tracked.strip(), ".gitignore")


class TestTrackedTreeScansClean(unittest.TestCase):
    """The whole tracked repo/corpus/reports/fixture tree scans publish-safe."""

    def test_publish_safe_main_zero_violations(self) -> None:
        cps = _load_cps()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cps.main()
        self.assertEqual(rc, 0, out.getvalue())

    def test_tracked_conformance_fixtures_are_synthetic(self) -> None:
        self.assertTrue(_EVAL_FIXTURES.is_file())
        rows = [json.loads(line) for line in
                _EVAL_FIXTURES.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        self.assertGreaterEqual(len(rows), 4)
        modules = set()
        for row in rows:
            self.assertIn(row["expect_verdict"], _VERDICT_VOCAB)
            self.assertNotIn("ev_", json.dumps(row))  # no vault evidence ids
            modules.add(row["module"])
        self.assertEqual(
            modules, {"core", "spouse", "transferability", "additional"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
