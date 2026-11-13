"""Fail-closed grounding compute for structured answers (Phase 25 — GND-01/GND-02).

This is the deterministic, pure-stdlib heart of the grounding gate. It reads ONE
structured answer object of the shape::

    {
        "question":   str,
        "claims":     [{"id": str, "text": str, "citations": [str, ...], "quote": str}],
        "basis":      [...],   # free-form supporting material — NEVER citation-checked
        "abstentions":[...],   # declared non-answers       — NEVER citation-checked
        "prose":      str,     # human-readable narration    — NEVER citation-checked
    }

and checks ONLY ``claims[]`` (SC1). For each claim it resolves every citation id
IN-PROCESS via the shipped :func:`crawler.searchindex.resolve` (GND-01) — never
shelling out, never re-implementing resolution — and verifies the claim's
verbatim ``quote`` is a whitespace/case-normalized substring of a resolving
chunk's stored text. A claim passes iff at least ONE citation BOTH resolves AND
contains the normalized quote; otherwise it contributes a fail-closed violation
reason (``uncited`` / ``unresolvable`` / ``quote_not_in_chunk``). Any single
failing claim makes the whole-answer verdict ``"fail"`` (SC2, GND-02).

HONESTY BOUNDARY (locked v3.0): this gate guarantees citation RESOLVABILITY +
VERBATIM-QUOTE substring presence, NOT semantic entailment or faithfulness. It
proves the quoted span exists verbatim in a real, un-drifted indexed chunk — it
does NOT prove the chunk actually supports the claim's meaning. Semantic
faithfulness (VAL-01/VAL-02) is deferred: it would require a model and violates
the project's no-vectors / no-cloud constraint. A human (or a later, separate
phase) must judge whether the verbatim quote supports the claim; :func:`render_answer`
places the quote beside the claim precisely so that judgement is possible (SC5).

Design constraints (mirroring ``searchindex`` / ``eval_runner``):
* STDLIB ONLY — imports limited to ``re``, ``pathlib.Path`` and the in-repo
  ``crawler.searchindex``. Zero new runtime dependencies.
* PURE — no file I/O, no network, no mutation of the index (``resolve`` opens the
  DB strictly read-only). Plan 02 owns the render-then-scan-then-write side.
* Quote normalization reuses ``eval_runner._norm`` semantics EXACTLY:
  ``re.sub(r"\\s+", " ", s).strip().lower()`` — whitespace-collapse + lowercase
  ONLY. No Unicode folding, no curly→straight conversion, no markdown stripping.
  Loosening this silently widens the grounding guarantee — forbidden.
* Do NOT modify ``crawler/searchindex.py``: this module is a pure CONSUMER of the
  shipped, GREEN ``resolve``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from crawler import searchindex

# The exact keys a claim object must carry. A claim missing any of these is a
# malformed-shape error (InvalidAnswer), NOT a fail-closed grounding violation —
# the two are distinct outcomes (bad input vs. ungrounded input).
_REQUIRED_CLAIM_KEYS = ("id", "text", "citations", "quote")

# WR-03: the eval reference set's optional per-line ``expect`` marker. A line may
# assert that the gate should ACCEPT it (``"grounded"``/``"pass"``, the default) OR
# that the gate should correctly REJECT it (``"ungrounded"``/``"fail"``) — the latter
# lets a fixture positively test fail-closed behaviour. Any OTHER value is treated as
# a fail-closed per-line error (``unknown_expect``), never silently graded as grounded.
_EXPECT_GROUNDED = ("grounded", "pass")
_EXPECT_UNGROUNDED = ("ungrounded", "fail")


class InvalidAnswer(ValueError):
    """Raised when the answer object is malformed / missing required shape.

    Distinct from a fail-closed grounding violation: a well-formed-but-ungrounded
    answer yields ``verdict:"fail"``, whereas a structurally invalid answer (not a
    dict, missing ``question``/``claims``, or a claim missing a required key)
    raises this. The CLI verb (Plan 02) maps it to ``invalid_input`` / exit 2,
    mirroring how :class:`crawler.searchindex.EmptyQuery` is CLI-mapped.
    """


def _norm(s: str) -> str:
    """Whitespace-collapse + lowercase normalizer (copied verbatim from ``eval_runner._norm``).

    Collapses any run of whitespace to a single space, strips ends, and lowercases.
    NOTHING else — no Unicode folding, no quote normalization, no markdown removal.
    """
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_is_grounded(quote: str, chunk_text: str) -> bool:
    """Return True iff *quote* is a non-empty normalized substring of *chunk_text*.

    Pure check, no I/O. A quote whose NORMALIZED form is empty can never be
    grounded (fail-closed): this rejects not only the exact empty string ``""`` but
    also whitespace-only quotes (``" "``, ``"\\t\\n"``), which collapse to ``""``
    under :func:`_norm`. The earlier ``bool(quote)`` guard let a whitespace-only
    quote through, because ``"" in <anything>`` is always True — a citation must
    point at an actual quoted span, not blank whitespace (CR-01). Case- and
    whitespace-insensitive (via :func:`_norm`) but otherwise an exact substring.
    """
    nq = _norm(quote)
    return bool(nq) and nq in _norm(chunk_text)


def check_claim(db: Path, claim: dict) -> list[str]:
    """Return the list of violation reasons for one claim (empty list == grounded).

    Fail-closed semantics (GND-01/GND-02):
    * ``["uncited"]``            — ``citations`` is absent / not a list / empty.
    * ``["unresolvable"]``       — every cited id failed :func:`searchindex.resolve`
                                   (unknown id OR sha-drift → ``None`` → miss).
    * ``["quote_not_in_chunk"]`` — at least one citation resolved, but the verbatim
                                   quote is not a normalized substring of any
                                   resolving chunk's text.
    * ``[]``                     — at least ONE citation BOTH resolves AND contains
                                   the normalized quote.
    """
    cites = claim.get("citations") or []
    if not isinstance(cites, list) or len(cites) < 1:
        return ["uncited"]

    # CR-02: a non-string quote must NEVER be str()-coerced. The old
    # ``str(claim.get("quote", ""))`` turned JSON ``null`` into ``"None"`` →
    # ``"none"``, ``true`` into ``"true"``, ``123`` into ``"123"`` — all extremely
    # common tokens that incidentally substring-match real chunk text, letting a
    # claim with no genuine quoted span pass. Treat any non-string value as a
    # fail-closed grounding miss rather than coercing it. (``check_answer`` also
    # rejects a non-string quote earlier as InvalidAnswer via ``_validate_shape``;
    # this guard keeps the public ``check_claim`` fail-closed when called directly.)
    raw = claim.get("quote", "")
    if not isinstance(raw, str):
        return ["quote_not_in_chunk"]
    quote = raw
    resolved_any = False
    quote_ok = False
    for cid in cites:
        chunk = searchindex.resolve(db, str(cid))   # None == miss OR sha-drift (fail-closed)
        if chunk is None:
            continue
        resolved_any = True
        if quote_is_grounded(quote, chunk["text"]):
            quote_ok = True
            break

    if not resolved_any:
        return ["unresolvable"]
    if not quote_ok:
        return ["quote_not_in_chunk"]
    return []


def _validate_shape(answer: object) -> list[dict]:
    """Validate the answer shape, returning its ``claims`` list, or raise ``InvalidAnswer``.

    Checks: ``answer`` is a dict; ``question`` is present; ``claims`` is present and
    a list; every claim is a dict carrying all of ``id``/``text``/``citations``/``quote``.
    Does NOT inspect ``prose``/``basis``/``abstentions`` — those are free-form filler.
    """
    if not isinstance(answer, dict):
        raise InvalidAnswer(f"answer must be a dict, got {type(answer).__name__}")
    if "question" not in answer:
        raise InvalidAnswer("answer is missing required key: 'question'")
    claims = answer.get("claims")
    if claims is None or not isinstance(claims, list):
        raise InvalidAnswer("answer is missing a list-valued 'claims'")
    for idx, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise InvalidAnswer(f"claim #{idx} is not a dict")
        missing = [k for k in _REQUIRED_CLAIM_KEYS if k not in claim]
        if missing:
            raise InvalidAnswer(
                f"claim #{idx} (id={claim.get('id')!r}) is missing keys: {missing}"
            )
        # CR-02: the `quote` KEY being present is not enough — its VALUE must be a
        # string. A JSON `null`/`true`/number quote that slipped through here would
        # be str()-coerced downstream into a real word ("none"/"true"/"123") that
        # incidentally substring-matches chunk text, a fail-closed bypass. A
        # non-string quote is malformed input → InvalidAnswer (CLI: invalid_input,
        # exit 2), NOT a coerced near-match.
        if not isinstance(claim["quote"], str):
            raise InvalidAnswer(
                f"claim #{idx} (id={claim.get('id')!r}) has a non-string 'quote': "
                f"{type(claim['quote']).__name__}"
            )
    return claims


def check_answer(answer: object, db: Path) -> dict:
    """Validate shape, gate every claim, and return the whole-answer verdict.

    Iterates ``claims[]`` ONLY (SC1 — ``prose``/``basis``/``abstentions`` are never
    inspected and can never change the verdict). Any claim with a non-empty
    :func:`check_claim` result contributes a violation; ANY violation makes the
    whole-answer verdict ``"fail"`` (SC2, fail-closed GND-02).

    Returns ``{verdict, total_claims, grounded, ungrounded, violations}`` where each
    violation is ``{"id", "reasons", "citations"}``. Raises :class:`InvalidAnswer`
    for a malformed answer.
    """
    claims = _validate_shape(answer)

    violations: list[dict] = []
    for claim in claims:
        reasons = check_claim(db, claim)
        if reasons:
            violations.append({
                "id": claim.get("id"),
                "reasons": reasons,
                "citations": claim.get("citations", []),
            })

    return {
        "verdict": "fail" if violations else "pass",
        "total_claims": len(claims),
        "grounded": len(claims) - len(violations),
        "ungrounded": len(violations),
        "violations": violations,
    }


def check_answer_grounding(answer: object, db_path: Path | None = None) -> dict:
    """Verify local grounding for an AnswerObject, failing closed if ungrounded or invalid shape.

    Args:
        answer: Candidate AnswerObject dictionary.
        db_path: Optional path to corpus/index.db index.

    Returns:
        Dict verdict summary if grounded.

    Raises:
        InvalidAnswer: If answer shape is structurally invalid.
        ValueError: If any claim fails local grounding verification.
    """
    db = db_path or Path("corpus/index.db")
    if not db.is_file():
        raise FileNotFoundError(f"Grounding corpus database not found: {db}")
    result = check_answer(answer, db)
    if result.get("verdict") != "pass":
        raise ValueError(f"AnswerObject failed grounding gate: {result.get('violations')}")
    return result


def run_eval(db: Path, questions_path: Path) -> tuple[dict, int]:
    """Run the SAME per-claim gate over each stored answer in a reference set.

    This is the eval harness (GND-02, SC4): the bar and the regression test are the
    identical machinery. ``questions_path`` is a JSONL reference set — one COMPLETE
    stored answer object per line (the :func:`check_answer` schema) plus an optional
    ``must_abstain`` marker. No document agent generates answers here (that is a
    Phase 27 concern); the loader stays generic so Phase 27 can later feed agent
    output through this same gate.

    Grading, per line (deterministic file order):
    * ``must_abstain`` truthy → abstention-correctness: the line PASSES iff it carries
      NO claims (``len(claims) == 0``); a must-abstain line that smuggles any claim is
      a FAILURE with reason ``["should_have_abstained"]``.
    * otherwise → graded by the normal :func:`check_answer` gate, then reconciled
      against the line's optional ``expect`` marker (WR-03; default ``"grounded"``).
      ``expect`` in ``("grounded", "pass")`` PASSES iff ``verdict == "pass"`` (the
      per-claim reasons are flattened to ``f"{v['id']}:{','.join(v['reasons'])}"`` on a
      fail); ``expect`` in ``("ungrounded", "fail")`` PASSES iff ``verdict == "fail"``
      (a positive test that the gate REJECTS an ungrounded answer; reason
      ``["expected_ungrounded_but_passed"]`` if it wrongly passed). Any other ``expect``
      value is a fail-closed ``["unknown_expect:<value>"]`` failure. A line so malformed
      that :func:`check_answer` raises :class:`InvalidAnswer` is caught and recorded as a
      per-line FAILURE with reason ``["invalid_shape"]`` (WR-02) — one bad line never
      collapses the whole run into a traceback / internal_error.

    Returns ``(summary, exit_code)`` where *summary* is the LOCKED ``eval_runner`` shape
    ``{total, passed, failed, failures}`` (mirror ``eval_runner.main:135-139``) and
    *exit_code* is ``1`` if ANY line failed else ``0`` (mirror ``eval_runner.main:150``).
    A single ungrounded line makes the whole eval non-zero — uncited-claim count,
    citation-resolution rate, and quote-substring rate are hard 0%/100%/100% gates.

    Pure check: NO render, NO write. ``db`` is opened strictly read-only by
    :func:`searchindex.resolve` inside :func:`check_answer`.
    """
    results: list[tuple[object, bool, list[str]]] = []
    with open(questions_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)  # one stored answer + expect/must_abstain marker
            claims = rec.get("claims") or []
            if rec.get("must_abstain"):
                # Abstention-correctness: a must-abstain answer must carry NO claims.
                ok = len(claims) == 0
                reasons = [] if ok else ["should_have_abstained"]
            else:
                try:
                    summary = check_answer(rec, db)
                except InvalidAnswer:
                    # WR-02: a malformed fixture line (e.g. a claim missing `quote`,
                    # or a non-string quote per CR-02) raises InvalidAnswer inside
                    # check_answer. Catch it HERE so one bad line fails loudly as a
                    # per-line `invalid_shape` failure (counted → exit 1) instead of
                    # propagating out and collapsing the whole eval into an uncaught
                    # traceback / internal_error (exit 4). Fail-closed: a line the gate
                    # cannot even parse is never a pass.
                    ok = False
                    reasons = ["invalid_shape"]
                else:
                    # WR-03: honor the per-line `expect` marker so a fixture can assert
                    # the gate should correctly REJECT an ungrounded answer (not only
                    # accept a grounded one). The old loop ignored `expect` and graded
                    # "PASS iff verdict == pass", so an `expect:"ungrounded"` line was
                    # silently mis-graded (a gate-rejection counted as a FAILURE, and a
                    # bypass counted as a PASS). Default is "grounded".
                    expect = rec.get("expect", "grounded")
                    verdict_pass = summary["verdict"] == "pass"
                    if expect in _EXPECT_GROUNDED:
                        ok = verdict_pass
                        reasons = [] if ok else [
                            f"{v['id']}:{','.join(v['reasons'])}"
                            for v in summary["violations"]
                        ]
                    elif expect in _EXPECT_UNGROUNDED:
                        # The line ASSERTS the gate must reject it: ok iff verdict fail.
                        ok = not verdict_pass
                        reasons = [] if ok else ["expected_ungrounded_but_passed"]
                    else:
                        # Fail-closed: an unrecognized `expect` must never be silently
                        # treated as "grounded" — that is exactly the WR-03 mis-grade.
                        ok = False
                        reasons = [f"unknown_expect:{expect}"]
            results.append((rec.get("id"), ok, reasons))

    failed = [(i, r) for (i, ok, r) in results if not ok]
    summary = {
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "failures": [{"id": i, "reasons": r} for (i, r) in failed],
    }
    return summary, (1 if failed else 0)


def render_answer(answer: object, db: Path) -> str:
    """Render a deterministic markdown view: each claim beside its verbatim quote (SC5).

    For each claim, renders the claim text and — directly below it, side-by-side for
    human review — the verbatim ``quote`` as a blockquote together with its resolved
    citation fields (``relpath`` / ``source_url`` / ``section`` / ``crawl_date`` from
    :func:`searchindex.resolve`). Ends with the explicit honesty-boundary footer.

    Pure string builder: NO file I/O (Plan 02 owns the scan-then-write step) and NO
    absolute path is ever placed in the rendered text.
    """
    claims = _validate_shape(answer)

    lines: list[str] = []
    lines.append(f"# {str(answer.get('question', '')).strip()}")
    lines.append("")

    for idx, claim in enumerate(claims, start=1):
        lines.append(f"## Claim {idx}")
        lines.append("")
        lines.append(str(claim.get("text", "")).strip())
        lines.append("")
        quote = str(claim.get("quote", "")).strip()
        lines.append(f"> {quote}" if quote else "> (no quote)")
        lines.append("")

        # Side-by-side: the resolved citation(s) for this claim's quote.
        cites = claim.get("citations") or []
        rendered_any = False
        if isinstance(cites, list):
            for cid in cites:
                chunk = searchindex.resolve(db, str(cid))
                if chunk is None:
                    continue
                rendered_any = True
                lines.append(
                    f"- **{chunk['relpath']}**"
                    f"{(' §' + chunk['section']) if chunk.get('section') else ''}"
                    f" — {chunk.get('source_url', '')}"
                    f" (crawled {chunk.get('crawl_date', '')})"
                )
        if not rendered_any:
            lines.append("- (no resolving citation)")
        lines.append("")

    lines.append("---")
    lines.append(
        "Grounded for citation resolvability + verbatim quote, NOT semantic "
        "entailment — verify the quote supports the claim."
    )
    lines.append("")
    return "\n".join(lines)
