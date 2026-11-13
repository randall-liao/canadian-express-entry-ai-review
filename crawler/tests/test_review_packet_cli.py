"""CLI-level proof for `vault review-packet` (PKT-01/03/04).

Uses a SYNTHETIC completed audit run written directly under the vault so the whole
path — build, redaction, render-then-scan, vault-only write, dry-run, and per-document
opt-in — runs UNGUARDED (no corpus/index.db). Stdlib unittest ONLY.
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


class ReviewPacketCli(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.personal = Path(self._tmp.name)
        self._prev = os.environ.get("PR_PERSONAL_DIR")
        os.environ["PR_PERSONAL_DIR"] = str(self.personal)
        self.candidate = "pkt"
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

    def _gap_card(self, quote_override=None):
        cites = _real_cites(self.registry, "core.language.first")
        card = PrivateFactorCard(
            factor_id="core.language.first", factor_group="core_human_capital",
            verdict="GAP", reason_code="missing_evidence",
            rule_citation_ids=cites, evidence_ids=["ev_secret999"])
        return card

    def _seed_completed_report(self, cards, *, bad_report=False,
                               registry_fingerprint=None) -> str:
        run_id = vault.record_audit_run(
            self.v, candidate_id=self.candidate, factor_id="*full-grid*",
            rule_registry_version=vault.rule_registry_version(self.v),
            status="running")
        fp = (registry_fingerprint if registry_fingerprint is not None
              else crs_rules.registry_fingerprint(self.registry))
        report = PrivateAuditReport(
            run_id=run_id, candidate_id=self.candidate, factor_cards=cards,
            registry_fingerprint=fp)
        out_dir = paths.resolve_within(self.v.root, "output", "crs-audit")
        out_dir.mkdir(parents=True, exist_ok=True)
        if not bad_report:
            (out_dir / f"{run_id}.json").write_text(
                json.dumps(report.model_dump(), ensure_ascii=False), encoding="utf-8")
        vault.complete_audit_run(
            self.v, run_id, status="complete",
            report_relpath=f"candidates/{self.candidate}/output/crs-audit/{run_id}.json")
        return run_id

    def _packet_dir(self) -> Path:
        return self.personal / "candidates" / self.candidate / "output" / "review-packet"

    def _packet_files(self) -> list[Path]:
        d = self._packet_dir()
        return list(d.rglob("*")) if d.exists() else []

    # -- happy path + vault-only (PKT-04) ----------------------------------- #
    def test_review_packet_writes_vault_only(self) -> None:
        self._seed_completed_report([self._gap_card()])
        env, code = _run_json(
            ["--json", "vault", "review-packet", "--candidate", self.candidate])
        self.assertTrue(env["ok"])
        self.assertEqual(code, 0)
        result = env["result"]
        self.assertGreaterEqual(result["findings_included"], 1)
        blob = json.dumps(result)
        self.assertNotIn("ev_", blob)
        self.assertTrue(result["private_output_path"].startswith(
            "output/review-packet/"))
        self.assertNotIn("candidates/", result["private_output_path"])
        files = [f for f in self._packet_files() if f.is_file()]
        self.assertEqual(len(files), 2)  # .json + .md
        md = next(f for f in files if f.suffix == ".md").read_text()
        self.assertIn("Substantiation screening", md)
        js = next(f for f in files if f.suffix == ".json").read_text()
        self.assertNotIn("ev_", js)  # the packet drops ev_ (unlike the remediation JSON)

    def test_vault_anchoring_rejects_escape(self) -> None:
        # No destination override is offered; writes are unconditionally vault-anchored.
        # Prove the exact anchor rejects a crafted escaping component.
        with self.assertRaises(paths.PathEscapeError):
            paths.resolve_within(self.v.root, "output", "review-packet",
                                 "../../escape.json")

    # -- refusals (PKT-04 fail-closed) -------------------------------------- #
    def _assert_refusal(self, argv, reason) -> None:
        env, code = _run_json(argv)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["type"], contract.INVALID_INPUT)
        self.assertEqual(code, contract.EXIT_INVALID_INPUT)
        self.assertIn(f"reason={reason}", env["error"]["message"])
        self.assertNotIn("ev_", env["error"]["message"])
        self.assertEqual([f for f in self._packet_files() if f.is_file()], [])

    def test_refusal_no_completed_audit(self) -> None:
        self._assert_refusal(
            ["--json", "vault", "review-packet", "--candidate", self.candidate],
            "no_completed_audit")

    def test_refusal_audit_report_unreadable(self) -> None:
        self._seed_completed_report([self._gap_card()], bad_report=True)
        self._assert_refusal(
            ["--json", "vault", "review-packet", "--candidate", self.candidate],
            "audit_report_unreadable")

    # -- dry-run preview (PKT-01) ------------------------------------------- #
    def test_dry_run_writes_nothing(self) -> None:
        self._seed_completed_report([self._gap_card()])
        env, code = _run_json(
            ["--json", "vault", "review-packet", "--candidate", self.candidate,
             "--dry-run"])
        self.assertTrue(env["ok"])
        self.assertIn("findings_total", env["result"]["manifest_counts"])
        self.assertIsNone(env["result"]["private_output_path"])
        # No file/dir created.
        self.assertEqual([f for f in self._packet_files() if f.is_file()], [])
        self.assertFalse(self._packet_dir().exists())

    # -- render-then-scan (PKT-04, mandatory ordering proof) ---------------- #
    def test_render_then_scan_ordering_via_quote(self) -> None:
        # RemediationCitation.quote is free text; a leak in a stored report's card quote
        # would flow through build_remediation -> build_packet -> render. We simulate by
        # constructing the checklist directly and calling run_review_packet's scan path.
        from crawler import remediation, review_packet
        # Seed a completed report so _build_checklist_for_run succeeds, then monkeypatch
        # build_remediation to inject a leaking quote into the produced checklist.
        run_id = self._seed_completed_report([self._gap_card()])
        orig = remediation.build_remediation

        def _leaky(report, registry):
            checklist = orig(report, registry)
            if checklist.items and checklist.items[0].citations:
                checklist.items[0].citations[0].quote = "/home/user/secret.pdf"
            return checklist

        remediation.build_remediation = _leaky
        try:
            env, code = _run_json(
                ["--json", "vault", "review-packet", "--candidate", self.candidate,
                 "--audit-run-id", run_id])
        finally:
            remediation.build_remediation = orig
        self.assertFalse(env["ok"])
        self.assertEqual(code, contract.EXIT_INVALID_INPUT)
        self.assertIn("reason=rendered_leak", env["error"]["message"])
        self.assertEqual([f for f in self._packet_files() if f.is_file()], [])

    # -- per-document opt-in staging (PKT-03) ------------------------------- #
    def _import_doc(self) -> str:
        src = self.personal / "syn.pdf"
        src.write_bytes(b"%PDF-1.4 synthetic doc bytes")
        return vault.import_document(
            self.v, self.candidate, src, doc_type="passport").document_id

    def test_include_document_stages_vault_only(self) -> None:
        doc_id = self._import_doc()
        self._seed_completed_report([self._gap_card()])
        env, code = _run_json(
            ["--json", "vault", "review-packet", "--candidate", self.candidate,
             "--include-document", doc_id])
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["documents_included"], 1)
        # The staged doc lives ONLY under output/review-packet/<pkt_id>/documents/.
        staged = [f for f in self._packet_files()
                  if f.is_file() and "documents" in f.parts and doc_id in f.name]
        self.assertEqual(len(staged), 1)
        # stdout carries no raw path/bytes.
        self.assertNotIn("syn.pdf", json.dumps(env["result"]))

    def test_include_unknown_document_refuses(self) -> None:
        self._seed_completed_report([self._gap_card()])
        self._assert_refusal(
            ["--json", "vault", "review-packet", "--candidate", self.candidate,
             "--include-document", "doc_does_not_exist"],
            "unknown_document")

    def test_include_document_missing_file_fails_closed(self) -> None:
        # CR-01: the DB row exists but its backing file is gone -> fail closed,
        # zero artifacts, no abs-path leak on stdout.
        doc_id = self._import_doc()
        row = vault.get_candidate_document(self.v, self.candidate, doc_id)
        src = paths.resolve_within(self.v.root, *row["storage_relpath"].split("/"))
        src.unlink()  # delete the backing file
        self._seed_completed_report([self._gap_card()])
        env, code = _run_json(
            ["--json", "vault", "review-packet", "--candidate", self.candidate,
             "--include-document", doc_id])
        self.assertFalse(env["ok"])
        self.assertEqual(code, contract.EXIT_INVALID_INPUT)
        self.assertIn("reason=document_unreadable", env["error"]["message"])
        self.assertNotIn("/", env["error"]["message"].split("reason=")[1][:40])  # no abs path
        self.assertEqual([f for f in self._packet_files() if f.is_file()], [])

    def test_duplicate_include_document_deduped(self) -> None:
        # WR-02: a repeated --include-document must not double-count / go negative.
        doc_id = self._import_doc()
        self._seed_completed_report([self._gap_card()])
        env, _ = _run_json(
            ["--json", "vault", "review-packet", "--candidate", self.candidate,
             "--include-document", doc_id, "--include-document", doc_id])
        self.assertEqual(env["result"]["documents_included"], 1)
        self.assertEqual(env["result"]["manifest_counts"]["documents_excluded"], 0)

    def test_documents_excluded_by_default(self) -> None:
        self._import_doc()
        self._seed_completed_report([self._gap_card()])
        env, _ = _run_json(
            ["--json", "vault", "review-packet", "--candidate", self.candidate,
             "--dry-run"])
        self.assertEqual(env["result"]["manifest_counts"]["documents_excluded"], 1)
        self.assertEqual(env["result"]["documents_included"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
