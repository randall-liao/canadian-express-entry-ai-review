"""Full-grid report-writer + cutoff tests (33-01 Task 3, AUDIT-04/05, SC4/SC5).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Reuses the Plan 03
synthetic fixtures (``_AuditorCase`` + ``_language_registry``): a synthetic corpus
index, a synthetic registry, and a synthetic vault under ``$PR_PERSONAL_DIR``.

Proves:
  * SC4/AUDIT-05 — ``run_full_audit_report`` sets ``substantiated_total`` to the
    summed SUBSTANTIATED points and populates ``cutoff_delta`` + ``meets_cutoff``
    correctly; the rendered markdown carries the arithmetic cutoff line with NO
    legal-advice wording;
  * AUDIT-06 — the public envelope carries no applicant value and no ``ev_`` id,
    and lists one verdict per grid factor;
  * SC5 — an ungrounded consumed rule raises ``AuditGroundingError`` and leaves
    ZERO artifacts (no report file, no ``audit_runs`` row).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest import mock

from crawler import audit_report, auditor, auditors, vault
from crawler.models.audit import PublicAuditEnvelope
from crawler.tests.test_auditor import _AuditorCase, _language_registry

_SENTINEL_RAW = 7.7318209


class _FullGridCase(_AuditorCase):
    def _crs_audit_dir(self, v) -> Path:
        return v.root / "output" / "crs-audit"

    def _seed_with_ita(self, scores, *, cutoff):
        v = self._seed_vault(scores)
        # Round date == today so the freshness reference is >= the seeded test
        # date (today - 30 days); an ITA date BEFORE the test would (correctly)
        # make the test not-yet-valid → AT-RISK.
        rnd = vault.set_ita_round(
            v, "default", "test-round", date.today().isoformat(), "Express Entry",
            cutoff_score=cutoff, claimed_score=None)
        return v, rnd.round_id


class TestFullGridCutoff(_FullGridCase):
    def test_implicit_round_is_resolved_once_and_persisted_everywhere(self) -> None:
        v = self._seed_vault(self._all(7.5))
        old = vault.set_ita_round(
            v, "default", "old", date.today().isoformat(), "EE",
            cutoff_score=500)
        latest = vault.set_ita_round(
            v, "default", "latest", date.today().isoformat(), "EE",
            cutoff_score=100)
        vault.create_candidate(v, "other-candidate")
        other = vault.set_ita_round(
            v, "other-candidate", "other", date.today().isoformat(), "EE",
            cutoff_score=999)
        v.con.execute(
            "UPDATE ita_rounds SET created_at = ? WHERE round_id = ?",
            ("2026-01-01T00:00:00+00:00", old.round_id),
        )
        v.con.execute(
            "UPDATE ita_rounds SET created_at = ? WHERE round_id = ?",
            ("2026-01-02T00:00:00+00:00", latest.round_id),
        )
        v.con.execute(
            "UPDATE ita_rounds SET created_at = ? WHERE round_id = ?",
            ("2026-01-03T00:00:00+00:00", other.round_id),
        )
        v.con.commit()
        try:
            with mock.patch(
                    "crawler.auditor._latest_ita_round_id",
                    wraps=auditor._latest_ita_round_id) as resolver:
                report, envelope = audit_report.run_full_audit_report(
                    v, self.db, _language_registry())
            self.assertEqual(resolver.call_count, 1)
            self.assertEqual(report.ita_round_id, latest.round_id)
            self.assertEqual(report.cutoff_delta, 16)
            run = vault.load_audit_run(v, envelope.run_id)
            self.assertEqual(run["ita_round_id"], latest.round_id)
            private_json = json.loads(
                (self._crs_audit_dir(v) / f"{envelope.run_id}.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(private_json["ita_round_id"], latest.round_id)
            private_md = (
                self._crs_audit_dir(v) / f"{envelope.run_id}.md"
            ).read_text(encoding="utf-8")
            self.assertIn(f"ITA round: `{latest.round_id}`", private_md)
        finally:
            v.con.close()

    def test_explicit_round_remains_the_effective_round(self) -> None:
        v = self._seed_vault(self._all(7.5))
        explicit = vault.set_ita_round(
            v, "default", "explicit", date.today().isoformat(), "EE",
            cutoff_score=500)
        vault.set_ita_round(
            v, "default", "newer", date.today().isoformat(), "EE",
            cutoff_score=100)
        try:
            with mock.patch(
                    "crawler.auditor._latest_ita_round_id") as resolver:
                report, envelope = audit_report.run_full_audit_report(
                    v, self.db, _language_registry(),
                    ita_round_id=explicit.round_id)
            resolver.assert_not_called()
            self.assertEqual(report.ita_round_id, explicit.round_id)
            self.assertEqual(report.cutoff_delta, 116 - 500)
            self.assertEqual(
                vault.load_audit_run(v, envelope.run_id)["ita_round_id"],
                explicit.round_id,
            )
        finally:
            v.con.close()

    def test_invalid_explicit_round_refuses_both_public_apis_before_audit(self) -> None:
        v = self._seed_vault(self._all(7.5))
        try:
            for entry_point in (
                lambda: auditor.run_full_audit(
                    v, self.db, _language_registry(),
                    ita_round_id="ita_missing_explicit"),
                lambda: audit_report.run_full_audit_report(
                    v, self.db, _language_registry(),
                    ita_round_id="ita_missing_explicit"),
            ):
                with self.subTest(entry_point=entry_point):
                    with (
                        mock.patch(
                            "crawler.auditor._audit_one_verified") as audit_factor,
                        mock.patch(
                            "crawler.audit_report._stage_text") as stage_report,
                        self.assertRaisesRegex(
                            auditor.AuditGroundingError,
                            "^ITA round is unavailable for candidate$",
                        ),
                    ):
                        entry_point()
                    audit_factor.assert_not_called()
                    stage_report.assert_not_called()
            crs_dir = self._crs_audit_dir(v)
            self.assertEqual(
                list(crs_dir.iterdir()) if crs_dir.exists() else [], [])
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)
        finally:
            v.con.close()

    def test_other_candidates_explicit_round_is_unavailable(self) -> None:
        v = self._seed_vault(self._all(7.5))
        vault.create_candidate(v, "other-candidate")
        other = vault.set_ita_round(
            v, "other-candidate", "other", date.today().isoformat(), "EE",
            cutoff_score=100)
        try:
            for entry_point in (
                lambda: auditor.run_full_audit(
                    v, self.db, _language_registry(),
                    ita_round_id=other.round_id),
                lambda: audit_report.run_full_audit_report(
                    v, self.db, _language_registry(),
                    ita_round_id=other.round_id),
            ):
                with self.subTest(entry_point=entry_point):
                    with self.assertRaisesRegex(
                        auditor.AuditGroundingError,
                        "^ITA round is unavailable for candidate$",
                    ):
                        entry_point()
        finally:
            v.con.close()

    def test_substantiated_total_and_cutoff_delta(self) -> None:
        v, round_id = self._seed_with_ita(self._all(7.5), cutoff=100)
        try:
            report, envelope = audit_report.run_full_audit_report(
                v, self.db, _language_registry(), ita_round_id=round_id)
        finally:
            v.con.close()
        # SC1: one card per grid factor.
        self.assertEqual(
            sorted(c.factor_id for c in report.factor_cards),
            sorted(auditors.FULL_GRID_FACTORS))
        # SC4: substantiated_total == summed SUBSTANTIATED points.
        summed = sum(c.substantiated_points or 0 for c in report.factor_cards
                     if c.verdict == "SUBSTANTIATED")
        self.assertEqual(report.substantiated_total, summed)
        # Language substantiates to 4 x 29 = 116 in the synthetic registry.
        self.assertEqual(report.substantiated_total, 116)
        # Cutoff comparison arithmetic: 116 - 100 = 16, meets.
        self.assertEqual(report.cutoff_delta, 16)
        self.assertTrue(report.meets_cutoff)

    def test_below_cutoff_does_not_meet(self) -> None:
        v, round_id = self._seed_with_ita(self._all(7.5), cutoff=500)
        try:
            report, _ = audit_report.run_full_audit_report(
                v, self.db, _language_registry(), ita_round_id=round_id)
        finally:
            v.con.close()
        self.assertEqual(report.cutoff_delta, 116 - 500)
        self.assertFalse(report.meets_cutoff)

    def test_markdown_has_cutoff_line_no_legal_advice(self) -> None:
        v, round_id = self._seed_with_ita(self._all(7.5), cutoff=100)
        try:
            _, envelope = audit_report.run_full_audit_report(
                v, self.db, _language_registry(), ita_round_id=round_id)
            md = (self._crs_audit_dir(v) / f"{envelope.run_id}.md").read_text(
                encoding="utf-8")
        finally:
            v.con.close()
        self.assertIn("Cutoff comparison", md)
        self.assertIn("Substantiated total", md)
        lowered = md.lower()
        # The SAFE-04 screening notice carries the NEGATED disclaimer; normalize
        # it out before scanning for a bare legal-advice / eligibility CLAIM.
        normalized = (lowered.replace("not legal advice", "")
                      .replace("not a substitute", ""))
        for banned in ("you are eligible", "legal advice", "guaranteed",
                       "you qualify"):
            self.assertNotIn(banned, normalized)
        self.assertIn("not legal advice", lowered)


class TestFullGridPiiLight(_FullGridCase):
    def test_envelope_is_pii_light_one_verdict_per_factor(self) -> None:
        scores = self._all(7.5)
        scores["reading"] = _SENTINEL_RAW
        v = self._seed_vault(scores)
        rnd = vault.set_ita_round(
            v, "default", "r", date.today().isoformat(), "EE", cutoff_score=100)
        try:
            report, envelope = audit_report.run_full_audit_report(
                v, self.db, _language_registry(), ita_round_id=rnd.round_id)
        finally:
            v.con.close()
        self.assertIsInstance(envelope, PublicAuditEnvelope)
        # One verdict per grid factor.
        self.assertEqual(
            sorted(fv.factor_id for fv in envelope.verdicts),
            sorted(auditors.FULL_GRID_FACTORS))
        # PII-light: no applicant sentinel, no ev_ id anywhere in the envelope.
        serialized = json.dumps(envelope.model_dump())
        self.assertNotIn(str(_SENTINEL_RAW), serialized)
        self.assertNotIn("ev_", serialized)
        for claim in envelope.claims:
            self.assertFalse(claim.citation_id.startswith("ev_"))
        # But the private card DOES carry the ev_ evidence pointer.
        lang = next(c for c in report.factor_cards
                    if c.factor_id == "core.language.first")
        self.assertTrue(lang.evidence_ids)
        self.assertTrue(all(e.startswith("ev_") for e in lang.evidence_ids))


class TestFullGridFailClosed(_FullGridCase):
    def test_no_round_fails_closed_without_artifacts(self) -> None:
        v = self._seed_vault(self._all(7.5))
        try:
            with self.assertRaisesRegex(
                    auditor.AuditGroundingError,
                    "^ITA round is required for full audit$"):
                audit_report.run_full_audit_report(
                    v, self.db, _language_registry())
            crs_dir = self._crs_audit_dir(v)
            self.assertEqual(
                list(crs_dir.iterdir()) if crs_dir.exists() else [], [])
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)
        finally:
            v.con.close()

    def test_grounding_failure_writes_nothing(self) -> None:
        bad = _language_registry(points_quote="absolutely not a substring zzz")
        v, round_id = self._seed_with_ita(self._all(7.5), cutoff=100)
        try:
            with self.assertRaises(auditor.AuditGroundingError):
                audit_report.run_full_audit_report(
                    v, self.db, bad, ita_round_id=round_id)
            crs_dir = self._crs_audit_dir(v)
            written = list(crs_dir.glob("*")) if crs_dir.exists() else []
            self.assertEqual(written, [])
            self.assertEqual(
                v.con.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0], 0)
            self.assertEqual(
                v.con.execute(
                    "SELECT COUNT(*) FROM factor_verdicts").fetchone()[0], 0)
        finally:
            v.con.close()


if __name__ == "__main__":  # pragma: no cover
    import unittest
    unittest.main()
