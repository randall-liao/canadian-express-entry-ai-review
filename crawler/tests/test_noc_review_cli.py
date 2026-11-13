"""End-to-end CLI tests for `vault noc-worksheet` + `vault noc-review` (Phase 43 — Plan 03).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network. Each test points
``$PR_PERSONAL_DIR`` at a throwaway ``tempfile.TemporaryDirectory`` and drives
``crawler.cli.main`` through a ``_run(argv) -> (rc, out, err)`` helper (mirrors
``test_extract_confirm_cli.py``). The worksheet/review verbs resolve against the
PINNED, git-ignored ``corpus/index.db`` via the frozen ``searchindex.resolve`` path,
so the whole class is skipped when that local-only db is absent (a green suite here
is STRUCTURAL ONLY when the corpus is missing).

Covers (NOC-01/NOC-02, threats T43-01/03/04):
  * the cited worksheet artifact is written ONLY under the vault;
  * ``--json`` stdout is PII-light (no raw duty text / absolute path);
  * human mode leaves stdout empty and routes duty detail to stderr;
  * a single duty is confirmed at a time via the shipped ``vault confirm`` verb
    (there is NO bulk confirm-all);
  * a missing/corrupt index refuses once (``invalid_input``/exit-2) with zero artifacts;
  * re-running ``vault noc-worksheet`` is idempotent (stable envelope, a between-run
    confirmation is preserved, and ``vault noc-review`` confirmed_count never inflates);
  * ``vault noc-review`` emits the sidecar's CLOSED PII-light dict on stdout.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_noc_review_cli.py -q
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import noc_review, noc_worksheet

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DB = _REPO_ROOT / "corpus" / "index.db"
_CORPUS_MISSING = (
    "LOCAL-ONLY: corpus/index.db is git-ignored — the grounded NOC review CLI slice "
    "did NOT run; a green suite here is STRUCTURAL ONLY"
)
# A resolvable NOC-2021 code with a stable 7-duty main-duties split (see 43-01/02).
_NOC = "21232"


@unittest.skipUnless(_REAL_DB.is_file(), _CORPUS_MISSING)
class TestNocReviewCli(unittest.TestCase):
    """Task 2: end-to-end conformance for the two NOC vault verbs through cli.main."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(
            os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    # -- helpers ------------------------------------------------------------ #
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        from crawler import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _one_envelope(self, stdout: str) -> dict:
        data = json.loads(stdout)
        self.assertEqual(
            set(data.keys()),
            {"schema_version", "ok", "command", "result", "error"})
        self.assertEqual(data["command"], "vault")
        self.assertEqual(data["schema_version"], "1.0")
        return data

    def _worksheet(self, code: str = _NOC) -> dict:
        """Generate the worksheet in --json mode; return the PII-light result dict."""
        rc, out, _ = self._run(
            ["--json", "vault", "noc-worksheet", "--noc-code", code,
             "--db", str(_REAL_DB)])
        self.assertEqual(rc, 0, out)
        env = self._one_envelope(out)
        self.assertTrue(env["ok"])
        return env["result"]

    def _first_duty_text(self, code: str = _NOC) -> str:
        """A real, corpus-grounded duty string (used to prove it never hits stdout)."""
        spans = noc_worksheet.resolve_noc_spans(str(_REAL_DB), code)
        self.assertIsNotNone(spans)
        duties = noc_worksheet.split_duties(str(_REAL_DB), code, spans["main"])
        self.assertGreaterEqual(len(duties), 1)
        return duties[0]["text"]

    def _artifacts(self) -> list[Path]:
        """Every rendered NOC worksheet artifact under the throwaway personal dir."""
        return list(Path(self._tmp.name).rglob("noc-*.md"))

    def _confirmed_fields(self) -> list[dict]:
        rc, out, _ = self._run(
            ["--json", "vault", "fields", "--status", "confirmed"])
        self.assertEqual(rc, 0, out)
        return self._one_envelope(out)["result"]["fields"]

    # -- NOC-01: vault-only artifact + PII-light stdout (T43-04) ------------ #
    def test_worksheet_artifact_vault_only_and_json_pii_light(self) -> None:
        result = self._worksheet()
        # Closed PII-light envelope shape — ids / counts / corpus citations only.
        self.assertEqual(
            set(result.keys()),
            {"noc_code", "duty_count", "value_ids", "worksheet_doc_id",
             "citations"})
        self.assertEqual(result["noc_code"], _NOC)
        self.assertEqual(result["duty_count"], 7)
        # 1 lead statement + 7 duties are captured as confirmable pending values.
        self.assertEqual(len(result["value_ids"]), 8)
        self.assertEqual(
            result["citations"],
            [f"noc-2021/noc-{_NOC}.md#001", f"noc-2021/noc-{_NOC}.md#002",
             f"noc-2021/noc-{_NOC}.md#003"])
        # The cited artifact was written ONLY under the vault (never corpus/).
        arts = self._artifacts()
        self.assertEqual(len(arts), 1)
        self.assertIn(self._tmp.name, str(arts[0]))
        self.assertNotIn("corpus/", str(arts[0].relative_to(self._tmp.name)))
        # The raw duty text lives in the vault artifact but NEVER on --json stdout.
        duty_text = self._first_duty_text()
        self.assertIn(duty_text, arts[0].read_text(encoding="utf-8"))
        _, out, _ = self._run(
            ["--json", "vault", "noc-worksheet", "--noc-code", _NOC,
             "--db", str(_REAL_DB)])
        self.assertNotIn(duty_text, out)          # no raw duty text on stdout
        self.assertNotIn(self._tmp.name, out)     # no absolute vault path on stdout
        self.assertNotIn("raw_text", out)

    # -- NOC-01: human duty detail → stderr; stdout empty ------------------- #
    def test_worksheet_human_detail_on_stderr_stdout_empty(self) -> None:
        rc, out, err = self._run(
            ["vault", "noc-worksheet", "--noc-code", _NOC, "--db", str(_REAL_DB)])
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip(), "")                 # stdout empty in human mode
        self.assertIn(self._first_duty_text(), err)       # duty detail on stderr
        self.assertIn(f"NOC {_NOC}", err)

    # -- NOC-02: per-duty confirm one at a time (no bulk confirm-all) — T43-03 #
    def test_confirm_one_duty_at_a_time_no_bulk(self) -> None:
        result = self._worksheet()
        # value_ids[0] is the lead statement; [1:] are duties — confirm ONE duty.
        duty_vid = result["value_ids"][1]
        rc, out, _ = self._run(
            ["--json", "vault", "confirm", "--value-id", duty_vid,
             "--decision", "confirm"])
        self.assertEqual(rc, 0, out)
        env = self._one_envelope(out)
        self.assertEqual(env["result"]["value_id"], duty_vid)
        self.assertEqual(env["result"]["confirmation_status"], "confirmed")
        # Exactly ONE field is confirmed — the per-value verb touched nothing else.
        confirmed = self._confirmed_fields()
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0]["value_id"], duty_vid)
        # Structural rubber-stamp defense: there is NO bulk confirm-all verb, and
        # `vault confirm` REQUIRES a single --value-id (argparse errors otherwise).
        with self.assertRaises(SystemExit):
            self._run(["vault", "confirm-all"])
        with self.assertRaises(SystemExit):
            self._run(["--json", "vault", "confirm", "--decision", "confirm"])

    # -- T43-01: index preflight refuses fail-closed with ZERO artifacts ---- #
    def test_index_preflight_refusal_writes_zero_artifacts(self) -> None:
        for verb in ("noc-worksheet", "noc-review"):
            with self.subTest(verb=verb):
                rc, out, _ = self._run(
                    ["--json", "vault", verb, "--noc-code", _NOC,
                     "--db", "corpus/does-not-exist.db"])
                self.assertEqual(rc, 2)
                env = self._one_envelope(out)
                self.assertFalse(env["ok"])
                self.assertEqual(env["error"]["type"], "invalid_input")
                # Refused BEFORE open_vault/compute → not a single artifact written.
                self.assertEqual(self._artifacts(), [])

    # -- NOC-02: idempotent rerun (stable envelope, confirm preserved) — T43-03 #
    def test_idempotent_rerun_stable_envelope_and_confirmed_preserved(self) -> None:
        first = self._worksheet()
        # Confirm ONE duty BETWEEN the two runs via the shipped per-value verb.
        duty_vid = first["value_ids"][1]
        rc, _, _ = self._run(
            ["--json", "vault", "confirm", "--value-id", duty_vid,
             "--decision", "confirm"])
        self.assertEqual(rc, 0)
        # Re-run: the idempotent Plan-01 generator returns a byte-stable envelope.
        second = self._worksheet()
        self.assertEqual(second["worksheet_doc_id"], first["worksheet_doc_id"])
        self.assertEqual(second["value_ids"], first["value_ids"])
        self.assertEqual(second["duty_count"], first["duty_count"])
        # The between-run confirmation is preserved (no duplicate confirmable row).
        confirmed = self._confirmed_fields()
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0]["value_id"], duty_vid)
        # Only one artifact file exists (rerun overwrote it deterministically).
        self.assertEqual(len(self._artifacts()), 1)
        # And `vault noc-review` confirmed_count does not inflate across the rerun.
        rc, out, _ = self._run(
            ["--json", "vault", "noc-review", "--noc-code", _NOC,
             "--db", str(_REAL_DB)])
        self.assertEqual(rc, 0, out)
        review = self._one_envelope(out)["result"]
        self.assertEqual(review["confirmed_count"], 1)
        self.assertLessEqual(review["confirmed_count"], review["duty_count"])

    # -- NOC-02/NOC-03: noc-review emits the CLOSED PII-light dict (T43-04) -- #
    def test_noc_review_emits_closed_pii_light_dict(self) -> None:
        self._worksheet()  # seed the born-pending review.noc duty values
        rc, out, err = self._run(
            ["--json", "vault", "noc-review", "--noc-code", _NOC,
             "--db", str(_REAL_DB)])
        self.assertEqual(rc, 0, out)
        env = self._one_envelope(out)
        result = env["result"]
        # The closed PII-light contract is exactly the sidecar's PUBLIC_FIELDS.
        self.assertEqual(set(result.keys()), set(noc_review.PUBLIC_FIELDS))
        # Structurally never-green: status is confined to {AT-RISK, GAP, N/A}.
        self.assertIn(result["status"], {"AT-RISK", "GAP", "N/A"})
        self.assertNotEqual(result["status"], "SUBSTANTIATED")
        self.assertNotIn("SUBSTANTIATED", out)
        # No raw duty text / absolute path leaks onto --json stdout.
        self.assertNotIn(self._first_duty_text(), out)
        self.assertNotIn(self._tmp.name, out)
        # Human mode: stdout empty, verdict detail routes to stderr.
        rc, out_h, err_h = self._run(
            ["vault", "noc-review", "--noc-code", _NOC, "--db", str(_REAL_DB)])
        self.assertEqual(rc, 0, err_h)
        self.assertEqual(out_h.strip(), "")
        self.assertIn(result["status"], err_h)


if __name__ == "__main__":
    unittest.main()
