"""Offline compute-layer suite for the grounding gate (Phase 25 — GND-01/GND-02).

Stdlib ``unittest`` ONLY — NO pytest fixtures, NO network, NO browser (per the
``crawler/tests/test_searchindex.py`` / AGENTS.md convention). Every test drives a
SYNTHETIC tiny corpus built into a ``tempfile.TemporaryDirectory`` in ``setUp``
(NEVER the real git-ignored ``corpus/``) via the shipped ``searchindex.build_index``,
then exercises ``crawler.grounding`` against real, resolving citation ids pulled
straight from the built ``chunks`` table.

Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_grounding.py -q
    .venv/bin/python -m unittest crawler.tests.test_grounding -v

Behaviour map (the fail-closed core + the honesty boundary):

    TestCheckClaim   — uncited / unresolvable / quote_not_in_chunk / grounded-pass /
                       case+whitespace tolerance (per-claim, GND-01/GND-02)
    TestCheckAnswer  — whole-answer verdict (SC2), claims-only inspection (SC1),
                       invalid-shape raises InvalidAnswer
    TestRenderAnswer — claim + verbatim quote + resolved citation side-by-side and
                       the honesty-boundary footer (SC5)
    TestGroundCli    — the `ground` CLI verb end-to-end through cli.main: one-line
                       envelope + stdout purity, fail-closed verdict (ok:true/exit 1,
                       no write), invalid_input/exit 2, RPT-03 publish-unsafe refusal
                       (ok:false/internal_error/exit 4, no write) (GND-02, SC1-SC3)
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import cli, contract, grounding, searchindex

# Reuse the synthetic-corpus builders from the sibling suite (a sibling-module
# import is acceptable per the house rule) — NEVER re-walk the real corpus/.
from crawler.tests.test_searchindex import _make_index_corpus


class _GroundingCase(unittest.TestCase):
    """Base case: a fresh synthetic 4-doc corpus + a real index DB in one tempdir."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_index_corpus(Path(self._tmp.name))
        # The DB lives in the tempdir — NEVER under the real git-ignored corpus/.
        self.db = Path(self._tmp.name) / "index.db"
        searchindex.build_index(self.root, self.db)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _known_row(self) -> tuple[str, str]:
        """Return a real ``(chunk_id, text)`` straight from the built `chunks` table.

        Mirrors ``test_searchindex.TestResolve._known_row`` — the tiny no-heading doc
        is a single whole-doc chunk, so its citation resolves and its text is quotable.
        """
        con = sqlite3.connect(str(self.db))
        try:
            return con.execute(
                "SELECT chunk_id, text FROM chunks "
                "WHERE relpath = 'pr-pdi/tiny.md' LIMIT 1"
            ).fetchone()
        finally:
            con.close()

    def _grounded_answer(self) -> dict:
        """Build a well-formed answer whose single claim is genuinely grounded.

        The quote is a VERBATIM substring of the resolved chunk's stored text, so the
        claim resolves AND the quote matches — verdict must be ``pass``.
        """
        chunk_id, text = self._known_row()
        quote = text[:60]  # a real verbatim span of the resolved chunk
        return {
            "question": "What police certificates are required?",
            "claims": [
                {
                    "id": "c1",
                    "text": "Applicants must provide police certificates.",
                    "citations": [chunk_id],
                    "quote": quote,
                }
            ],
            "basis": [],
            "abstentions": [],
            "prose": "",
        }


# --------------------------------------------------------------------------- #
# TestCheckClaim — the per-claim fail-closed reasons (GND-01/GND-02).
# --------------------------------------------------------------------------- #
class TestCheckClaim(_GroundingCase):
    def test_uncited_claim_is_fail_closed(self) -> None:
        """An empty citations[] yields ['uncited'] (fail-closed)."""
        claim = {"id": "c1", "text": "x", "citations": [], "quote": "anything"}
        self.assertEqual(grounding.check_claim(self.db, claim), ["uncited"])

    def test_absent_citations_is_uncited(self) -> None:
        """A missing/None citations field is treated as uncited (fail-closed)."""
        claim = {"id": "c1", "text": "x", "citations": None, "quote": "anything"}
        self.assertEqual(grounding.check_claim(self.db, claim), ["uncited"])

    def test_unknown_id_is_unresolvable(self) -> None:
        """Every cited id failing resolve() (unknown) yields ['unresolvable'] (GND-01)."""
        claim = {
            "id": "c1",
            "text": "x",
            "citations": ["no-such/doc.md#999"],
            "quote": "anything",
        }
        self.assertEqual(grounding.check_claim(self.db, claim), ["unresolvable"])

    def test_resolving_id_with_bad_quote_is_quote_not_in_chunk(self) -> None:
        """A real resolving id but a quote not in that chunk -> ['quote_not_in_chunk']."""
        chunk_id, _ = self._known_row()
        claim = {
            "id": "c1",
            "text": "x",
            "citations": [chunk_id],
            "quote": "this exact phrase is definitely not in the chunk zzz",
        }
        self.assertEqual(grounding.check_claim(self.db, claim), ["quote_not_in_chunk"])

    def test_real_id_with_verbatim_quote_is_grounded(self) -> None:
        """A real id + a verbatim substring of its chunk text -> grounded ([])."""
        chunk_id, text = self._known_row()
        claim = {
            "id": "c1",
            "text": "x",
            "citations": [chunk_id],
            "quote": text[:40],
        }
        self.assertEqual(grounding.check_claim(self.db, claim), [])

    def test_case_and_whitespace_tolerant_but_otherwise_exact(self) -> None:
        """The same grounded quote with altered case + collapsed whitespace still passes.

        Proves _norm is applied (whitespace-collapse + lowercase) while otherwise
        preserving exact substring semantics.
        """
        chunk_id, text = self._known_row()
        span = text[:50]
        mangled = "   ".join(span.upper().split())  # uppercase + re-spaced
        claim = {"id": "c1", "text": "x", "citations": [chunk_id], "quote": mangled}
        self.assertEqual(grounding.check_claim(self.db, claim), [])

    def test_whitespace_only_quote_is_not_grounded(self) -> None:
        """CR-01: a whitespace-only quote normalizes to "" and must NOT be grounded.

        The old ``bool(quote) and _norm(quote) in _norm(chunk_text)`` returned True
        for any non-empty whitespace string (``_norm`` collapses it to ``""`` and
        ``"" in <anything>`` is always True) — a fail-closed bypass. The fixed
        ``quote_is_grounded`` normalizes FIRST and requires a non-empty result.
        """
        for blank in ("   ", "\t\n", " \u00a0\t ", "\n"):
            self.assertFalse(
                grounding.quote_is_grounded(blank, "some real chunk text here"),
                f"whitespace-only quote {blank!r} must never be grounded")

    def test_check_claim_whitespace_quote_is_quote_not_in_chunk(self) -> None:
        """CR-01: a real resolving citation + a whitespace-only quote → fail-closed.

        Reproduces the reported bypass end-to-end through ``check_claim``: the
        citation resolves but the blank quote grounds nothing, so the only correct
        fail-closed reason is ``quote_not_in_chunk`` (the old code returned ``[]``).
        """
        chunk_id, _ = self._known_row()
        claim = {"id": "c1", "text": "x", "citations": [chunk_id], "quote": "   "}
        self.assertEqual(grounding.check_claim(self.db, claim),
                         ["quote_not_in_chunk"])

    def test_non_string_quote_is_not_coerced(self) -> None:
        """CR-02: a non-string quote must never be str()-coerced into a match.

        The synthetic ``legislation-irpa/statute.md#000`` chunk contains the inline
        token ``9.4``. The old ``str(claim.get("quote", ""))`` turned the FLOAT
        ``9.4`` into the string ``"9.4"`` which substring-matched that chunk → a
        bogus grounded pass with no genuine quoted span. A non-string quote
        (number, bool, ``None``) must instead be a fail-closed ``quote_not_in_chunk``.
        """
        statute_id = "legislation-irpa/statute.md#000"
        # Sanity: this id really resolves, so the ONLY thing under test is the quote.
        self.assertIsNotNone(searchindex.resolve(self.db, statute_id))
        for bad_quote in (9.4, True, None, 123, ["9.4"]):
            claim = {"id": "c1", "text": "x",
                     "citations": [statute_id], "quote": bad_quote}
            self.assertEqual(
                grounding.check_claim(self.db, claim), ["quote_not_in_chunk"],
                f"non-string quote {bad_quote!r} must be fail-closed, not coerced")


# --------------------------------------------------------------------------- #
# TestCheckAnswer — whole-answer verdict (SC2), claims-only (SC1), invalid shape.
# --------------------------------------------------------------------------- #
class TestCheckAnswer(_GroundingCase):
    def test_grounded_answer_verdict_pass(self) -> None:
        summary = grounding.check_answer(self._grounded_answer(), self.db)
        self.assertEqual(summary["verdict"], "pass")
        self.assertEqual(summary["total_claims"], 1)
        self.assertEqual(summary["grounded"], 1)
        self.assertEqual(summary["ungrounded"], 0)
        self.assertEqual(summary["violations"], [])

    def test_any_failing_claim_makes_whole_answer_fail(self) -> None:
        """One uncited claim alongside a grounded one -> verdict fail (SC2)."""
        answer = self._grounded_answer()
        answer["claims"].append(
            {"id": "c2", "text": "y", "citations": [], "quote": "z"}
        )
        summary = grounding.check_answer(answer, self.db)
        self.assertEqual(summary["verdict"], "fail")
        self.assertEqual(summary["total_claims"], 2)
        self.assertEqual(summary["ungrounded"], 1)
        self.assertEqual(summary["violations"][0]["id"], "c2")
        self.assertEqual(summary["violations"][0]["reasons"], ["uncited"])

    def test_whitespace_only_quote_makes_verdict_fail(self) -> None:
        """CR-01: a grounded answer whose quote is whitespace-only → verdict "fail".

        The single claim has a real, resolving citation but a blank ``"   "`` quote.
        The old gate passed it (``"" in chunk`` always True); the fixed gate must
        return ``verdict:"fail"`` with a ``quote_not_in_chunk`` violation.
        """
        answer = self._grounded_answer()
        answer["claims"][0]["quote"] = "   "
        summary = grounding.check_answer(answer, self.db)
        self.assertEqual(summary["verdict"], "fail")
        self.assertEqual(summary["ungrounded"], 1)
        self.assertEqual(summary["violations"][0]["reasons"],
                         ["quote_not_in_chunk"])

    def test_filler_is_never_inspected(self) -> None:
        """Bogus prose/basis/abstentions never affect the verdict (SC1)."""
        answer = self._grounded_answer()
        answer["prose"] = "Totally uncited free-text narration with no citations."
        answer["basis"] = ["some uncitable supporting note", "another bogus basis"]
        answer["abstentions"] = ["I will not answer about visas."]
        summary = grounding.check_answer(answer, self.db)
        self.assertEqual(summary["verdict"], "pass")  # claims[] all grounded
        self.assertEqual(summary["ungrounded"], 0)

    def test_non_dict_answer_raises_invalid(self) -> None:
        with self.assertRaises(grounding.InvalidAnswer):
            grounding.check_answer(["not", "a", "dict"], self.db)

    def test_missing_claims_raises_invalid(self) -> None:
        with self.assertRaises(grounding.InvalidAnswer):
            grounding.check_answer({"question": "q"}, self.db)

    def test_claim_missing_quote_raises_invalid(self) -> None:
        answer = {
            "question": "q",
            "claims": [{"id": "c1", "text": "x", "citations": ["a#1"]}],
        }
        with self.assertRaises(grounding.InvalidAnswer):
            grounding.check_answer(answer, self.db)

    def test_non_string_quote_value_raises_invalid(self) -> None:
        """CR-02: a present-but-non-string quote VALUE is malformed shape, not a pass.

        ``_validate_shape`` previously only checked the quote KEY was present, so a
        ``"quote": null`` (or number/bool) claim flowed into ``check_claim`` and was
        str()-coerced into an incidental match. It must now raise ``InvalidAnswer``
        (CLI → invalid_input / exit 2). Tested for each JSON non-string shape.
        """
        chunk_id, _ = self._known_row()
        for bad_quote in (None, True, 123, 9.4, ["q"], {"q": 1}):
            answer = {
                "question": "q",
                "claims": [{"id": "c1", "text": "x",
                            "citations": [chunk_id], "quote": bad_quote}],
            }
            with self.assertRaises(grounding.InvalidAnswer):
                grounding.check_answer(answer, self.db)


# --------------------------------------------------------------------------- #
# TestRenderAnswer — claim + quote + citation side-by-side + honesty footer (SC5).
# --------------------------------------------------------------------------- #
class TestRenderAnswer(_GroundingCase):
    def test_render_places_claim_quote_and_citation_side_by_side(self) -> None:
        answer = self._grounded_answer()
        out = grounding.render_answer(answer, self.db)
        self.assertIn(answer["question"], out)               # the question heading
        self.assertIn(answer["claims"][0]["text"], out)      # the claim text
        self.assertIn(answer["claims"][0]["quote"], out)     # the verbatim quote
        self.assertIn("pr-pdi/tiny.md", out)                 # the resolved citation relpath

    def test_render_contains_honesty_boundary_footer(self) -> None:
        out = grounding.render_answer(self._grounded_answer(), self.db)
        self.assertIn("NOT semantic entailment", out)
        self.assertIn("verify the quote supports the claim", out)

    def test_render_no_absolute_paths(self) -> None:
        """The rendered markdown must not leak any absolute filesystem path."""
        out = grounding.render_answer(self._grounded_answer(), self.db)
        self.assertNotIn(self._tmp.name, out)   # the real tempdir abs path
        self.assertNotIn(str(self.db), out)     # the real index-db abs path


# --------------------------------------------------------------------------- #
# TestRunEval — the gate-over-fixtures eval harness (GND-02, SC4). A tiny inline
# JSONL reference set is written into the tempdir and graded by `run_eval` against
# the SYNTHETIC index — proving the locked {total,passed,failed,failures} shape,
# exit-1-on-any-ungrounded, and must_abstain abstention-correctness. NEVER touches
# the real corpus/ (that round-trip is the @skipUnless TestRealCorpusEval below).
# --------------------------------------------------------------------------- #
class TestRunEval(_GroundingCase):
    """`run_eval` aggregates the eval_runner shape over a stored reference set."""

    def _write_jsonl(self, records: list[dict]) -> Path:
        """Write one JSON object per line into the tempdir; return the path."""
        path = Path(self._tmp.name) / "questions.jsonl"
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )
        return path

    def _grounded_record(self, rec_id: str) -> dict:
        """A grounded answer line (the gate's answer schema) with a real citation."""
        rec = self._grounded_answer()
        rec["id"] = rec_id
        rec["expect"] = "grounded"
        return rec

    def test_all_grounded_set_passes_exit_0(self) -> None:
        """An all-grounded reference set → {failed:0, failures:[]} and exit 0."""
        path = self._write_jsonl(
            [self._grounded_record("g1"), self._grounded_record("g2")])
        summary, code = grounding.run_eval(self.db, path)
        self.assertEqual(code, 0)
        self.assertEqual(set(summary), {"total", "passed", "failed", "failures"})
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["failures"], [])

    def test_one_ungrounded_line_exits_1_with_its_id_in_failures(self) -> None:
        """A single ungrounded line → exit 1 and that id appears in failures (SC4)."""
        bad = self._grounded_record("bad1")
        bad["claims"].append(
            {"id": "c2", "text": "y", "citations": [], "quote": "z"})  # uncited
        path = self._write_jsonl([self._grounded_record("g1"), bad])
        summary, code = grounding.run_eval(self.db, path)
        self.assertEqual(code, 1)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 1)
        failing_ids = [f["id"] for f in summary["failures"]]
        self.assertIn("bad1", failing_ids)
        # The per-claim reason is flattened into the failure record.
        self.assertTrue(any("uncited" in ",".join(f["reasons"])
                            for f in summary["failures"]))

    def test_must_abstain_with_empty_claims_passes(self) -> None:
        """A correct must_abstain line (no claims) passes — exit 0."""
        record = {
            "id": "abstain-ok",
            "must_abstain": True,
            "question": "A thing not in the corpus.",
            "claims": [],
            "basis": [],
            "abstentions": [{"text": "not in corpus", "reason": "not_in_corpus"}],
            "prose": "",
        }
        summary, code = grounding.run_eval(self.db, self._write_jsonl([record]))
        self.assertEqual(code, 0)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["passed"], 1)

    def test_must_abstain_carrying_claims_is_should_have_abstained(self) -> None:
        """A must_abstain line that smuggles any claim → should_have_abstained FAIL."""
        record = {
            "id": "abstain-bad",
            "must_abstain": True,
            "question": "A thing not in the corpus.",
            # Adversarial: a must_abstain line MUST carry an empty claims[].
            "claims": [{"id": "c1", "text": "x",
                        "citations": ["a#1"], "quote": "q"}],
            "basis": [],
            "abstentions": [],
            "prose": "",
        }
        summary, code = grounding.run_eval(self.db, self._write_jsonl([record]))
        self.assertEqual(code, 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["failures"][0]["id"], "abstain-bad")
        self.assertEqual(summary["failures"][0]["reasons"],
                         ["should_have_abstained"])

    def test_expect_ungrounded_passes_when_gate_correctly_rejects(self) -> None:
        """WR-03: an `expect:"ungrounded"` line PASSES when the gate rejects it.

        The line carries an uncited claim (verdict "fail") and asserts the gate
        SHOULD reject it. Honoring `expect` makes this a PASS (the gate behaved
        correctly). The old loop ignored `expect` and graded it a FAILURE.
        """
        rec = self._grounded_answer()
        rec["id"] = "neg-ok"
        rec["expect"] = "ungrounded"
        # Make it genuinely ungrounded: replace the claim with an uncited one.
        rec["claims"] = [{"id": "c1", "text": "x", "citations": [], "quote": "z"}]
        summary, code = grounding.run_eval(self.db, self._write_jsonl([rec]))
        self.assertEqual(code, 0)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 0)

    def test_expect_ungrounded_fails_when_gate_wrongly_accepts(self) -> None:
        """WR-03: an `expect:"ungrounded"` line FAILS when the gate accepts it.

        This is the silent-misgrade the dead `expect` field allowed: a GROUNDED
        answer mislabeled `expect:"ungrounded"` (the gate passed it) must be counted
        a FAILURE (the negative assertion did not hold). The old code graded it
        "PASS iff verdict == pass" → a silent PASS. Fails on the old code.
        """
        rec = self._grounded_record("neg-bad")    # genuinely grounded → verdict pass
        rec["expect"] = "ungrounded"               # but we assert it should be rejected
        summary, code = grounding.run_eval(self.db, self._write_jsonl([rec]))
        self.assertEqual(code, 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["failures"][0]["id"], "neg-bad")
        self.assertEqual(summary["failures"][0]["reasons"],
                         ["expected_ungrounded_but_passed"])

    def test_unknown_expect_value_is_fail_closed(self) -> None:
        """WR-03: an unrecognized `expect` value is a fail-closed per-line failure.

        A typo'd `expect` must NEVER be silently treated as "grounded" (the exact
        mis-grade WR-03 fixes). Even a genuinely grounded answer fails the line.
        """
        rec = self._grounded_record("typo")
        rec["expect"] = "grouded"                  # typo → unknown
        summary, code = grounding.run_eval(self.db, self._write_jsonl([rec]))
        self.assertEqual(code, 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["failures"][0]["reasons"], ["unknown_expect:grouded"])

    def test_malformed_line_is_counted_invalid_shape_failure(self) -> None:
        """WR-02: a malformed fixture line → counted invalid_shape failure, exit 1.

        A non-abstain line whose claim is missing the required ``quote`` key makes
        ``check_answer`` raise ``InvalidAnswer``. ``run_eval`` must CATCH it and record
        the line as a per-line ``invalid_shape`` failure (exit 1) — NOT let it
        propagate (which the old code did, collapsing the run into a traceback /
        internal_error). Other lines in the set still grade normally.
        """
        good = self._grounded_record("g1")
        bad = {
            "id": "bad-shape", "expect": "grounded", "question": "q",
            "claims": [{"id": "c1", "text": "x", "citations": ["a#1"]}],  # NO quote
            "basis": [], "abstentions": [], "prose": "",
        }
        path = self._write_jsonl([good, bad])
        summary, code = grounding.run_eval(self.db, path)  # must NOT raise
        self.assertEqual(code, 1)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 1)
        failing = {f["id"]: f["reasons"] for f in summary["failures"]}
        self.assertIn("bad-shape", failing)
        self.assertEqual(failing["bad-shape"], ["invalid_shape"])

    def test_blank_lines_are_skipped(self) -> None:
        """Blank/whitespace-only lines are ignored (not graded)."""
        path = Path(self._tmp.name) / "with_blanks.jsonl"
        path.write_text(
            json.dumps(self._grounded_record("g1"), ensure_ascii=False)
            + "\n\n   \n"
            + json.dumps(self._grounded_record("g2"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        summary, code = grounding.run_eval(self.db, path)
        self.assertEqual(code, 0)
        self.assertEqual(summary["total"], 2)  # the two blank lines were skipped


# --------------------------------------------------------------------------- #
# TestGroundCli — drive the REAL `ground` verb end-to-end through `cli.main`
# (GND-02): the one-line CONTRACT envelope (ok/command/schema_version), stdout
# purity (human text → stderr), the fail-closed verdict (ok:true/verdict:"fail"/
# exit 1, no write), the invalid_input/exit-2 boundaries, and the RPT-03
# render-then-gate publish-unsafe refusal (ok:false/internal_error/exit 4, no write).
# The index + every write stays INSIDE the tempdir — NEVER the real corpus/.
# --------------------------------------------------------------------------- #
class TestGroundCli(_GroundingCase):
    """Drive the `ground` verb through cli.main with stdin stubbing (GND-02, SC1-SC3)."""

    def _run(self, argv: list[str], stdin_text: str = "") -> tuple[int, str, str]:
        """Run cli.main(argv) capturing (exit_code, stdout, stderr), with stdin stubbed.

        Mirrors ``TestSearchCli._run`` (test_searchindex.py:871-880) plus a ``sys.stdin``
        swap — the one delta, because ``ground`` reads its answer from stdin. stdin is
        always restored in ``finally`` so a failing case never leaks the swap.

        Also pins the CR-03 anchored-containment boundary (``cli._personal_root``) to a
        ``personal/`` dir UNDER this case's tempdir, so the write-gate's repo-anchored
        containment is exercised WITHOUT ever writing under the real repo tree. Tests
        that assert rejection simply pass an --out-dir outside this tempdir anchor.
        """
        out, err = io.StringIO(), io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin_text)
        anchor = (Path(self._tmp.name) / "personal").resolve()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    mock.patch("crawler.cli._personal_root", return_value=anchor):
                rc = cli.main(argv)
        finally:
            sys.stdin = old_stdin
        return rc, out.getvalue(), err.getvalue()

    def _out_dir(self) -> Path:
        """A tempdir output path UNDER a `personal/` segment (the PII boundary)."""
        return Path(self._tmp.name) / "personal" / "output"

    def test_grounded_answer_emits_one_pass_envelope_and_writes(self) -> None:
        """A fully-grounded answer → one ok:true/verdict:"pass" envelope, exit 0, one file."""
        out_dir = self._out_dir()
        answer = self._grounded_answer()
        rc, out, err = self._run(
            ["--json", "ground", "--db", str(self.db), "--out-dir", str(out_dir)],
            stdin_text=json.dumps(answer))
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("\n"), 1)             # exactly ONE JSON line
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertEqual(obj["command"], "ground")
        self.assertEqual(obj["schema_version"], "1.0")   # additive change: unchanged
        self.assertEqual(obj["result"]["verdict"], "pass")
        self.assertIsNone(obj["error"])
        self.assertNotIn("{", err)                       # no JSON leaked to stderr
        # Exactly one file written under the personal/ out-dir; result.out points at it.
        written = list(out_dir.glob("*.md"))
        self.assertEqual(len(written), 1)
        self.assertEqual(obj["result"]["out"], str(written[0]))

    def test_out_dir_with_personal_segment_outside_anchor_is_rejected(self) -> None:
        """CR-03: a 'personal'-containing --out-dir NOT under the repo anchor → exit 2.

        The old containment only required SOME path component literally named
        'personal', so paths like ``<tmp>/evil/personal/out`` (and the real-world
        ``/tmp/personal/evil`` / ``~/personal`` / ``/var/www/personal/pub``) passed
        and rendered VERBATIM corpus text could be written outside ``.gitignore``
        protection. Each of these has a 'personal' part but is NOT nested under the
        anchored ``<repo>/personal`` (here patched to ``<tmp>/personal``) → must be
        refused as invalid_input / exit 2 with NOTHING written.
        """
        anchor = (Path(self._tmp.name) / "personal").resolve()
        escaping = [
            Path(self._tmp.name) / "evil" / "personal" / "out",   # personal nested elsewhere
            Path(self._tmp.name) / "x" / "personal",              # personal as a leaf, wrong parent
            Path(self._tmp.name) / "personal-decoy" / "personal" / "z",
        ]
        for out_dir in escaping:
            # Precondition: the old "'personal' in parts" check WOULD have accepted it.
            self.assertIn("personal", out_dir.resolve().parts)
            # Precondition: it is genuinely outside the anchored boundary.
            self.assertNotEqual(out_dir.resolve(), anchor)
            self.assertNotIn(anchor, out_dir.resolve().parents)
            rc, out, _ = self._run(
                ["--json", "ground", "--db", str(self.db),
                 "--out-dir", str(out_dir)],
                stdin_text=json.dumps(self._grounded_answer()))
            self.assertEqual(rc, contract.EXIT_INVALID_INPUT,
                             f"{out_dir} must be rejected as invalid_input")
            obj = json.loads(out)
            self.assertIs(obj["ok"], False)
            self.assertEqual(obj["error"]["type"], "invalid_input")
            self.assertIsNone(obj["result"])
            self.assertFalse(out_dir.exists(), f"{out_dir} must not be created/written")

    def test_out_dir_exactly_the_anchor_is_accepted(self) -> None:
        """CR-03: --out-dir equal to the anchored personal root itself is allowed."""
        out_dir = Path(self._tmp.name) / "personal"   # == the patched anchor exactly
        rc, out, _ = self._run(
            ["--json", "ground", "--db", str(self.db), "--out-dir", str(out_dir)],
            stdin_text=json.dumps(self._grounded_answer()))
        self.assertEqual(rc, 0)
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertEqual(obj["result"]["verdict"], "pass")
        self.assertEqual(len(list(out_dir.glob("*.md"))), 1)

    def test_fail_closed_verdict_is_ok_true_exit_1_no_write(self) -> None:
        """An uncited claim → ok:true/verdict:"fail"/exit 1 and NOTHING rendered (SC2)."""
        out_dir = self._out_dir()
        answer = self._grounded_answer()
        # Append an uncited claim → the whole-answer verdict fails (fail-closed).
        answer["claims"].append(
            {"id": "c2", "text": "y", "citations": [], "quote": "z"})
        rc, out, _ = self._run(
            ["--json", "ground", "--db", str(self.db), "--out-dir", str(out_dir)],
            stdin_text=json.dumps(answer))
        self.assertEqual(rc, 1)
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)                   # verdict-fail is NOT an error
        self.assertIsNone(obj["error"])
        self.assertEqual(obj["result"]["verdict"], "fail")
        self.assertEqual(obj["result"]["ungrounded"], 1)
        self.assertFalse(out_dir.exists())               # nothing rendered / written

    def test_malformed_stdin_is_invalid_input_exit_2(self) -> None:
        """Malformed stdin JSON → ok:false / invalid_input / exit 2 (no write)."""
        out_dir = self._out_dir()
        rc, out, _ = self._run(
            ["--json", "ground", "--db", str(self.db), "--out-dir", str(out_dir)],
            stdin_text="{not json")
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")
        self.assertIsNone(obj["result"])
        self.assertFalse(out_dir.exists())

    def test_non_file_db_is_invalid_input_exit_2(self) -> None:
        """A --db that is not a file → ok:false / invalid_input / exit 2."""
        rc, out, _ = self._run(
            ["--json", "ground", "--db", "/no/such/db-25-02.db",
             "--out-dir", str(self._out_dir())],
            stdin_text=json.dumps(self._grounded_answer()))
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")

    def test_null_quote_is_invalid_input_exit_2_no_write(self) -> None:
        """CR-02: a `"quote": null` claim → invalid_input / exit 2, NOTHING written.

        End-to-end through cli.main: a non-string quote value is malformed shape, so
        the gate must refuse it as invalid_input (never str()-coerce ``null`` into
        ``"none"`` and pass). No file is rendered or written.
        """
        out_dir = self._out_dir()
        answer = self._grounded_answer()
        answer["claims"][0]["quote"] = None     # JSON null
        rc, out, _ = self._run(
            ["--json", "ground", "--db", str(self.db), "--out-dir", str(out_dir)],
            stdin_text=json.dumps(answer))
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")
        self.assertIsNone(obj["result"])
        self.assertFalse(out_dir.exists())

    def test_publish_unsafe_render_is_internal_error_exit_4_no_write(self) -> None:
        """A publish-safety hit in the rendered text → internal_error/exit 4, no write (SC3)."""
        out_dir = self._out_dir()
        answer = self._grounded_answer()  # genuinely grounded → check_answer verdict "pass"
        # Stub the renderer to emit an abs-path line the RPT-03 scan MUST catch, exercising
        # the render-then-gate refusal without depending on a particular leaky fixture.
        with mock.patch(
                "crawler.grounding.render_answer",
                return_value="# leak\n\nsee /home/evil/secret for the key\n"):
            rc, out, _ = self._run(
                ["--json", "ground", "--db", str(self.db), "--out-dir", str(out_dir)],
                stdin_text=json.dumps(answer))
        self.assertEqual(rc, contract.EXIT_INTERNAL_ERROR)   # exit 4 (reused code)
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "internal_error")
        self.assertIn("refusing to write answer", obj["error"]["message"])
        self.assertIsNone(obj["result"])
        self.assertFalse(out_dir.exists())                   # NOTHING written

    def test_publish_scan_runs_even_under_excluded_looking_out_dir(self) -> None:
        """WR-01: the RPT-03 scan must run regardless of the destination path label.

        ``scan_text(path, text)`` self-excludes any path under ``scripts/tests/`` or
        ``.github/`` (the repo-tree publish-scan exclusions). The old write-gate fed
        the DESTINATION path into ``scan_text``, so a relative ``--out-dir`` such as
        ``scripts/tests/personal`` made ``is_excluded`` True and SKIPPED the scan,
        writing unscanned content. With the neutral ``"answer.md"`` label the scan
        ALWAYS runs: an unsafe rendered answer is refused (internal_error/exit 4),
        nothing written — EVEN when the destination path looks excluded.

        Runs with cwd chdir'd into the tempdir so the relative ``scripts/tests/...``
        out-dir resolves under the (patched) personal anchor and any old-code write
        lands in cleanable temp space, never the real repo tree.
        """
        import os

        rel_out = "scripts/tests/personal"   # str(out_path) starts with this excluded prefix
        answer = self._grounded_answer()     # genuinely grounded → reaches the write-gate
        out, err = io.StringIO(), io.StringIO()
        old_stdin, old_cwd = sys.stdin, os.getcwd()
        os.chdir(self._tmp.name)
        sys.stdin = io.StringIO(json.dumps(answer))
        try:
            anchor = Path(rel_out).resolve()   # == <tmp>/scripts/tests/personal
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    mock.patch("crawler.cli._personal_root", return_value=anchor), \
                    mock.patch("crawler.grounding.render_answer",
                               return_value="# leak\n\nsee /home/evil/secret key\n"):
                rc = cli.main(["--json", "ground", "--db", str(self.db),
                               "--out-dir", rel_out])
        finally:
            sys.stdin, _ = old_stdin, os.chdir(old_cwd)
        obj = json.loads(out.getvalue())
        self.assertEqual(rc, contract.EXIT_INTERNAL_ERROR)   # scan ran → refused
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "internal_error")
        self.assertIn("refusing to write answer", obj["error"]["message"])
        self.assertIsNone(obj["result"])
        # NOTHING written under the excluded-looking destination.
        self.assertFalse((Path(self._tmp.name) / rel_out).exists())

    def test_json_stdout_is_pure_one_object(self) -> None:
        """stdout carries EXACTLY one parseable JSON object; no JSON on stderr (P11)."""
        rc, out, err = self._run(
            ["--json", "ground", "--db", str(self.db),
             "--out-dir", str(self._out_dir())],
            stdin_text=json.dumps(self._grounded_answer()))
        self.assertEqual(rc, 0)
        json.loads(out)                                  # must not raise
        self.assertEqual(out.count("\n"), 1)
        self.assertNotIn("{", err)                       # no JSON leaked to stderr

    def test_eval_mode_emits_summary_envelope_without_touching_stdin(self) -> None:
        """--eval over an all-grounded set → ok:true {failed:0} envelope, exit 0.

        stdin carries garbage that would crash the single-answer path — proving the
        eval branch is reached BEFORE any stdin read (Pitfall 7).
        """
        rec = self._grounded_answer()
        rec["id"] = "g1"
        path = Path(self._tmp.name) / "q.jsonl"
        path.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
        rc, out, err = self._run(
            ["--json", "ground", "--db", str(self.db), "--eval", str(path)],
            stdin_text="this is not json and must never be read")
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("\n"), 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)
        self.assertEqual(obj["command"], "ground")
        self.assertEqual(set(obj["result"]),
                         {"total", "passed", "failed", "failures"})
        self.assertEqual(obj["result"]["failed"], 0)
        self.assertNotIn("{", err)

    def test_eval_mode_exit_1_when_a_line_is_ungrounded(self) -> None:
        """--eval with one ungrounded line → ok:true, exit 1, id in failures."""
        good = self._grounded_answer()
        good["id"] = "g1"
        bad = self._grounded_answer()
        bad["id"] = "bad1"
        bad["claims"].append(
            {"id": "c2", "text": "y", "citations": [], "quote": "z"})
        path = Path(self._tmp.name) / "q.jsonl"
        path.write_text(
            json.dumps(good, ensure_ascii=False) + "\n"
            + json.dumps(bad, ensure_ascii=False) + "\n",
            encoding="utf-8")
        rc, out, _ = self._run(
            ["--json", "ground", "--db", str(self.db), "--eval", str(path)])
        self.assertEqual(rc, 1)
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)             # ungrounded is a verdict, not an error
        self.assertIsNone(obj["error"])
        self.assertEqual(obj["result"]["failed"], 1)
        self.assertIn("bad1", [f["id"] for f in obj["result"]["failures"]])

    def test_eval_mode_non_file_path_is_invalid_input_exit_2(self) -> None:
        """--eval pointing at a non-file → ok:false / invalid_input / exit 2."""
        rc, out, _ = self._run(
            ["--json", "ground", "--db", str(self.db),
             "--eval", str(Path(self._tmp.name) / "no-such.jsonl")])
        self.assertEqual(rc, contract.EXIT_INVALID_INPUT)
        obj = json.loads(out)
        self.assertIs(obj["ok"], False)
        self.assertEqual(obj["error"]["type"], "invalid_input")

    def test_eval_mode_malformed_line_is_counted_failure_not_internal_error(self) -> None:
        """WR-02: a malformed fixture line in --eval → ok:true, exit 1 (NOT internal_error/4).

        The old run_eval let InvalidAnswer propagate, surfacing through cli.main's
        catch-all as internal_error/exit 4. The fixed loop counts it as an
        ``invalid_shape`` line failure: the eval still emits its ok:true summary
        envelope and exits 1, with the bad line's id in failures.
        """
        good = self._grounded_answer()
        good["id"] = "g1"
        bad = {"id": "bad-shape", "question": "q",
               "claims": [{"id": "c1", "text": "x", "citations": ["a#1"]}],  # NO quote
               "basis": [], "abstentions": [], "prose": ""}
        path = Path(self._tmp.name) / "q.jsonl"
        path.write_text(
            json.dumps(good, ensure_ascii=False) + "\n"
            + json.dumps(bad, ensure_ascii=False) + "\n",
            encoding="utf-8")
        rc, out, _ = self._run(
            ["--json", "ground", "--db", str(self.db), "--eval", str(path)])
        self.assertEqual(rc, 1)                       # counted failure, NOT exit 4
        obj = json.loads(out)
        self.assertIs(obj["ok"], True)                # an eval verdict, not an error
        self.assertIsNone(obj["error"])
        self.assertEqual(obj["result"]["failed"], 1)
        failing = {f["id"]: f["reasons"] for f in obj["result"]["failures"]}
        self.assertEqual(failing.get("bad-shape"), ["invalid_shape"])


# --------------------------------------------------------------------------- #
# Tracked-fixture suites (Plan 03): the eval reference set `crawler/eval/
# questions.jsonl` is COMMITTED (public), so it is the phase's highest PII-leak
# surface. These three classes prove (a) its grounded lines actually resolve with
# verbatim quotes against the LIVE 742-doc index (end-to-end, @skipUnless), (b) it
# carries no abs-path/secret/PII (NOT skip-guarded — the fixture is tracked), and
# (c) its structure is well-formed (every line parses; must_abstain ⇒ empty claims).
# --------------------------------------------------------------------------- #

# Repo-root-relative paths (this suite runs from the repo root, per AGENTS.md).
_FIXTURE_PATH = Path("crawler/eval/questions.jsonl")
_REAL_DB = Path("corpus/index.db")


@unittest.skipUnless(_REAL_DB.is_file(), "real corpus/index.db not present")
class TestRealCorpusEval(unittest.TestCase):
    """End-to-end: the tracked fixture's grounded lines resolve against the live index.

    This is the real-corpus integration smoke (GND-01/GND-02, SC4): it runs
    ``grounding.run_eval`` over the COMMITTED ``crawler/eval/questions.jsonl`` against
    the real ``corpus/index.db``. A fabricated citation id or a non-verbatim quote in
    the fixture would make a grounded line fail → ``failed > 0`` → this test red. It is
    ``@skipUnless``-guarded so CI without the git-ignored corpus simply skips it.
    """

    def test_fixture_grounds_clean_against_live_index(self) -> None:
        summary, code = grounding.run_eval(_REAL_DB, _FIXTURE_PATH)
        # The locked eval_runner shape is present and intact.
        self.assertEqual(set(summary), {"total", "passed", "failed", "failures"})
        # Every tracked line passes against the real index → exit 0.
        self.assertEqual(summary["failed"], 0, summary["failures"])
        self.assertEqual(code, 0)
        # ≥2 grounded + ≥1 adversarial must_abstain ⇒ at least 3 lines.
        self.assertGreaterEqual(summary["total"], 3)
        self.assertEqual(summary["passed"], summary["total"])


class TestFixturePublishSafety(unittest.TestCase):
    """PII / share-safety self-scan over the TRACKED fixture bytes (T-25-11).

    NOT skip-guarded — the fixture is committed regardless of whether the corpus is
    present, so this share-safety gate MUST always run. Reuses the shipped
    ``check_publish_safe.scan_text`` (the SAFE-02 abs-path/secret detector) plus a
    belt-and-suspenders raw-substring check for machine-path PII markers.
    """

    def test_fixture_pii_self_scan_is_clean(self) -> None:
        text = _FIXTURE_PATH.read_text(encoding="utf-8")
        # scripts/ is NOT a package → sys.path shim then top-level import (mirrors
        # cli._cmd_ground / dupclean.py:478-482). parents[2] == repo root.
        scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import check_publish_safe as cps  # SAFE-02 share-safety scanner

        violations = cps.scan_text(str(_FIXTURE_PATH), text)
        self.assertEqual(violations, [], [v.render() for v in violations])

        # Belt-and-suspenders: no machine-path / project-venv markers anywhere.
        for marker in ("/home/", "/Users/", "pr-ai-venv"):
            self.assertNotIn(marker, text)


class TestFixtureStructure(unittest.TestCase):
    """Structural invariants over the tracked fixture (NOT skip-guarded).

    Every line parses as JSON; every non-abstain line carries a ``question`` and a
    ``claims`` list whose entries each have ``id``/``text``/``citations``/``quote``;
    every ``must_abstain:true`` line carries an EMPTY ``claims[]`` (the abstention-
    correctness precondition the eval enforces).
    """

    def test_every_line_is_well_formed(self) -> None:
        lines = [ln for ln in _FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        self.assertGreaterEqual(len(lines), 3)  # ≥2 grounded + ≥1 must_abstain

        grounded = 0
        abstain = 0
        for raw in lines:
            rec = json.loads(raw)  # must parse
            self.assertIn("question", rec)
            if rec.get("must_abstain"):
                abstain += 1
                self.assertEqual(rec.get("claims"), [],
                                 f"must_abstain line {rec.get('id')!r} carries claims")
            else:
                grounded += 1
                self.assertIsInstance(rec.get("claims"), list)
                self.assertGreaterEqual(len(rec["claims"]), 1)
                for claim in rec["claims"]:
                    for key in ("id", "text", "citations", "quote"):
                        self.assertIn(key, claim, f"{rec.get('id')!r} claim missing {key}")
                    self.assertIsInstance(claim["citations"], list)
                    self.assertGreaterEqual(len(claim["citations"]), 1)
        self.assertGreaterEqual(grounded, 2)  # ≥2 grounded answer lines
        self.assertGreaterEqual(abstain, 1)   # ≥1 adversarial must_abstain line


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
