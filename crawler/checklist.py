"""Personalized Layer-1 checklist — PII source + pure applicability (Phase 26, CHK-01/CHK-02).

This module is the ONLY input layer that carries PII for the Layer-1 "which
documents you need" checklist. It does three deterministic things and nothing
else (no corpus retrieval, no gating, no rendering — those live in Plans 02/03):

* ``personal_dir()``   — resolve the git-ignored profile/output root from
  ``$PR_PERSONAL_DIR`` (default ``./personal/`` — the SC1/SC3 PII boundary).
* ``load_profile()``   — read ``<root>/profile.yaml`` with ``yaml.safe_load`` ONLY
  (never ``yaml.load`` — threat T-26-01) and fail fast via :class:`ProfileError`.
* ``applicable_items()`` — pure profile -> ordered list of Layer-1 items. Each
  item carries a GENERIC, PII-free requirement label (``text``) destined for the
  gated ``claims[]`` of Plan 02, and a SEPARATE ``basis`` sentence that holds the
  PII applicability reason destined for the never-gated, never-rendered
  ``basis[]``. Personalization = which items appear + their basis reasons; it is
  NEVER requirement-text mutation (SC2).

PII-TIER SPLIT (locked, CHK-02 / threat T-26-04): countries, dates, names and
counts from the profile drive WHICH items appear and populate ``basis`` ONLY. The
generic ``text``/``query`` fields never interpolate a profile value, so the
rendered checklist is PII-free by construction. The corpus pages this maps to are
GENERIC IRCC guidance (no PII).

Design constraints (mirroring ``crawler.profile`` / ``crawler.grounding``):
* STDLIB + PyYAML ONLY — zero new runtime dependencies (PyYAML already declared).
* ``applicable_items`` is PURE — no I/O, no retrieval, no mutation. Sparse
  profiles are read defensively (``.get`` + sensible defaults), never KeyError.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from crawler import grounding, searchindex
from crawler import paths


class ProfileError(ValueError):
    """Raised when the personal profile cannot be read or is malformed.

    Checklist-local on purpose — distinct from :class:`crawler.profile.ProfileError`
    (which validates the unrelated crawl-SITE profile). Fails fast on: an
    unreadable / missing ``profile.yaml``, malformed YAML, or a top-level value
    that is not a mapping.
    """


def personal_dir() -> Path:
    """Profile/output root: ``$PR_PERSONAL_DIR`` override, default ``./personal/``.

    The default is the git-ignored ``personal/`` boundary (SC1/SC3): real PII and
    rendered output never enter the repo. The value is untrusted input from the
    environment (threat T-26-02) — Plan 01 performs no writes, so it is only read
    here; output-write containment is enforced in Plan 03.

    Centralized (Phase 29): delegates to ``paths.legacy_personal_dir()``, which
    reproduces this exact behaviour (env override, relative ``personal`` default)
    verbatim — no behaviour change.
    """
    return paths.legacy_personal_dir()


def load_profile(root: Path) -> dict:
    """Read ``<root>/profile.yaml`` and return it as a mapping, or fail fast.

    Mirrors ``crawler.profile.load_profile`` error handling exactly: wrap
    ``OSError`` and ``yaml.YAMLError`` in :class:`ProfileError`, and reject any
    parsed value that is not a ``dict``. Parses with ``yaml.safe_load`` ONLY
    (never ``yaml.load`` — threat T-26-01: no arbitrary object construction).
    """
    source = root / "profile.yaml"

    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        # PII BOUNDARY (CR-01): keep the message PII-free. The OS exception text is
        # the file *location* (not its PII contents), but we still refuse to splice
        # ``{exc}`` in — surface only the generic reason plus the profile path.
        raise ProfileError(f"Could not read personal profile {source}.") from exc

    try:
        # safe_load ONLY — never yaml.load (threat T-26-01: no arbitrary objects).
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        # PII BOUNDARY (CR-01, threat T-26-04): PyYAML's ``MarkedYAMLError.__str__``
        # embeds the OFFENDING SOURCE LINE verbatim (its ``get_snippet`` caret
        # context). For the *personal* profile that line is exactly where real
        # names / countries / dates live, so interpolating ``str(exc)`` would ship
        # those bytes into the CLI's ``--json`` envelope on stdout (and human
        # stderr), bypassing the render-then-scan publish-safe gate and the
        # ``personal/`` containment. Surface ONLY a generic reason plus PII-free
        # line/column numbers (never the snippet text). Fail closed.
        mark = getattr(exc, "problem_mark", None)
        where = (
            f" (line {mark.line + 1}, column {mark.column + 1})"
            if mark is not None
            else ""
        )
        raise ProfileError(f"Invalid YAML in personal profile{where}.") from exc

    if not isinstance(data, dict):
        raise ProfileError(
            f"Profile {source} must be a YAML mapping; got {type(data).__name__}."
        )

    # WR-01: known sub-sections must have the RIGHT SHAPE, not merely be present.
    # applicable_items reads program/education/applicant as mappings (via .get) and
    # residence_since_18 as a sequence; a scalar there (e.g. `program: FSW`) is
    # malformed USER input. Map it to ProfileError here — which the CLI already
    # routes to invalid_input / exit 2 — instead of letting `"FSW".get("stream")`
    # crash later as an AttributeError that escapes to the catch-all
    # (internal_error / exit 4 + a traceback that could echo profile bytes). The
    # message names only the FIELD and its TYPE NAME — never the offending VALUE
    # (PII boundary, threat T-26-04).
    for field in ("program", "education", "applicant"):
        value = data.get(field)
        if value is not None and not isinstance(value, dict):
            raise ProfileError(
                f"Profile field {field!r} must be a mapping; "
                f"got {type(value).__name__}."
            )
    residence = data.get("residence_since_18")
    if residence is not None and not isinstance(residence, list):
        raise ProfileError(
            "Profile field 'residence_since_18' must be a list; "
            f"got {type(residence).__name__}."
        )

    return data


def applicable_items(profile: dict) -> list[dict]:
    """Pure profile -> ordered list of APPLICABLE Layer-1 document items.

    Deterministic and side-effect-free: no I/O, no corpus retrieval, no gating.
    Personalization is claim SELECTION (which items appear) plus their PII
    ``basis`` reasons — NEVER requirement-text mutation (SC2, Pattern 3). Each
    returned dict has four keys:

    * ``doc_type`` — stable id (e.g. ``"passport"``, ``"proof-of-funds"``).
    * ``query``    — a SHORT 2-4 token corpus query (Plan 02 tunes these live).
    * ``text``     — a GENERIC, PII-FREE requirement label (WHAT document). It
      NEVER interpolates a profile value (threat T-26-04).
    * ``basis``    — a single applicability sentence (WHY it applies). This is the
      ONLY field that may carry profile-derived PII (the specific residence
      countries route here, never to ``text``/``query``).

    Applies the RESEARCH applicability table exactly. Missing/sparse profile keys
    are read defensively (``.get`` + defaults) so a sparse profile never KeyErrors.
    """
    program = profile.get("program") or {}
    education = profile.get("education") or {}
    applicant = profile.get("applicant") or {}
    residence = profile.get("residence_since_18") or []

    stream = str(program.get("stream") or "").upper()
    has_job_offer = bool(program.get("has_job_offer"))
    claiming_foreign_edu = bool(education.get("claiming_foreign_education_points"))
    try:
        family_18_plus = int(applicant.get("family_members_18_plus") or 0)
    except (TypeError, ValueError):
        family_18_plus = 0

    items: list[dict] = []

    # --- Always-on Layer-1 items (apply to every applicant; generic, PII-free) ---
    items.append(
        {
            "doc_type": "passport",
            "query": "passport travel document permanent residence",
            "text": "Valid passport or travel document.",
            "basis": "Always required for an Express Entry permanent-residence application.",
        }
    )
    items.append(
        {
            "doc_type": "language",
            "query": "language test approved results",
            "text": "Results of an approved language test.",
            "basis": "Always required: Express Entry requires an approved language test.",
        }
    )
    items.append(
        {
            "doc_type": "medical",
            "query": "immigration medical examination permanent residence",
            "text": "Immigration medical exam (IME) confirmation.",
            "basis": "Always required: permanent-residence applicants must undergo an IME.",
        }
    )
    items.append(
        {
            "doc_type": "biometrics",
            "query": "give biometrics permanent residence",
            "text": "Biometrics (fingerprints and photo).",
            "basis": "Always required for permanent-residence applications.",
        }
    )

    # --- ECA: claiming foreign-education points OR the FSW stream ---
    if claiming_foreign_edu or stream == "FSW":
        reason = (
            "the profile claims foreign-education points"
            if claiming_foreign_edu
            else "the program stream is Federal Skilled Worker (FSW)"
        )
        items.append(
            {
                "doc_type": "eca",
                "query": "foreign educational credential assessment",
                "text": "Educational Credential Assessment (ECA) report.",
                "basis": f"Applies because {reason}.",
            }
        )

    # --- Proof of funds: FSW/FST only (CEC and PNP are exempt) ---
    if stream in {"FSW", "FST"}:
        items.append(
            {
                "doc_type": "proof-of-funds",
                "query": "settlement funds requirement unless",
                "text": "Proof of settlement funds.",
                "basis": (
                    f"Applies because the program stream ({stream}) must meet the "
                    "settlement-funds requirement; CEC and PNP applicants are exempt."
                ),
            }
        )

    # --- Police certificates: any qualifying residence country OR family >=18 ---
    # The SPECIFIC country list is PII and lives in the basis sentence ONLY. The
    # query stays generic AND grounded_claim's relpath backstop refuses any
    # per-country page, so the rendered citation can never leak residence history.
    countries = [
        str(entry.get("country"))
        for entry in residence
        if isinstance(entry, dict) and entry.get("country")
    ]
    if countries or family_18_plus > 0:
        reasons: list[str] = []
        if countries:
            reasons.append(
                "residence since age 18 in " + ", ".join(countries)
            )
        if family_18_plus > 0:
            reasons.append(
                f"{family_18_plus} accompanying family member(s) aged 18 or older"
            )
        items.append(
            {
                "doc_type": "police-certificates",
                "query": "police certificate 10 years country",
                "text": "Police certificate(s) for each required country.",
                "basis": "Applies because the profile lists " + "; ".join(reasons) + ".",
            }
        )

    # --- Written job-offer letter ---
    if has_job_offer:
        items.append(
            {
                "doc_type": "job-offer",
                "query": "arranged employment job offer letter",
                "text": "Written job-offer letter.",
                "basis": "Applies because the profile indicates a written job offer.",
            }
        )

    return items


# --------------------------------------------------------------------------- #
# The ASSEMBLER (Plan 02, CHK-01) — turn applicable items into gated, cited,
# PII-free claims[] and assemble the Phase-25 answer object, then run it THROUGH
# the shipped grounding gate. grounding-by-construction: every emitted claim
# resolves + verbatim-matches a GENERIC corpus page; PII never leaves basis[];
# anything ungroundable becomes an explicit abstention, never a bare claim.
# --------------------------------------------------------------------------- #

# The fixed, generic, never-gated, never-PII answer question.
_ANSWER_QUESTION = "Personalized Layer-1 document checklist"

# How much of a resolved chunk to slice as the verbatim quote (a real substring).
_QUOTE_MAX_CHARS = 300

# Minimum word-characters a sliced quote must carry to be MEANINGFUL (IN-01). A
# degenerate span (e.g. a lone terminator ".") would still normalize-match the
# chunk and "ground" a vacuous claim; below this floor we fail closed (skip → abstain).
_QUOTE_MIN_WORD_CHARS = 3

# Per-country corpus family prefixes whose RELPATH leaks residence history. A claim
# may NEVER cite a chunk under one of these (defense-in-depth backstop, threat
# T-26-08): the corpus carries 229 ``police-certificates/<country>.md`` pages whose
# path discloses where the applicant lived. The GENERIC rule lives at
# ``guidance/police-certificates.md`` (family ``guidance``), which is NOT rejected.
_COUNTRY_SPECIFIC_FAMILIES = ("police-certificates/",)


def _is_country_specific(relpath: str) -> bool:
    """True iff *relpath* is a per-country page whose path leaks residence history.

    Fail-closed backstop (threat T-26-08): a country-specific hit is skipped during
    retrieval, and if no generic hit remains the item abstains rather than cite a
    leaky page. Independent of (and additional to) query tuning — the no-leak
    guarantee does not rest on the query strings alone.

    The relpath is NORMALIZED before the prefix test (WR-03): backslash separators
    are folded to ``/``, leading separators stripped, and case lowered, so a
    ``Police-Certificates\\France`` page on a case-insensitive / Windows corpus is
    caught just like ``police-certificates/france``.
    """
    rp = (relpath or "").replace("\\", "/").lstrip("/").lower()
    return any(rp.startswith(prefix.lower()) for prefix in _COUNTRY_SPECIFIC_FAMILIES)


def _verbatim_quote(text: str) -> str:
    """Slice a VERBATIM span from *text* that the grounding gate will accept.

    Returns the first sentence (a prefix up to the first sentence terminator) when
    reasonably sized, else a capped prefix. The result is ALWAYS a real substring of
    *text*, so :func:`grounding.quote_is_grounded` (whitespace+case normalized,
    otherwise exact) accepts it. An empty/whitespace-only chunk — OR a degenerate
    span carrying fewer than ``_QUOTE_MIN_WORD_CHARS`` word characters (IN-01, e.g.
    a lone terminator ``"."``) — yields ``""`` so the caller ABSTAINS rather than
    emit a vacuous quote that would still normalize-match the chunk and "ground".
    """
    if not text or not text.strip():
        return ""
    window = text[:_QUOTE_MAX_CHARS]
    match = re.search(r"[.!?]\s", window)
    span = text[: match.end()] if match else window
    quote = span.strip()
    # IN-01: demand a minimally meaningful span — fail closed on a degenerate quote
    # (e.g. ".") so the caller abstains instead of emitting a vacuous grounded claim.
    if len(re.findall(r"\w", quote)) < _QUOTE_MIN_WORD_CHARS:
        return ""
    return quote


def grounded_claim(db: Path, item: dict) -> dict | None:
    """Retrieve -> backstop -> resolve -> verbatim-quote one item, or None (fail-closed).

    Runs the item's SHORT generic ``query`` over the read-only index (``_to_match``
    ANDs every token, so the query must stay 2-4 high-signal tokens), iterates the
    best hits, SKIPS any country-specific relpath (threat T-26-08), resolves the
    first generic hit to its exact stored chunk, and slices a VERBATIM quote span
    from the live text. Returns a gate-ready claim ``{id, text, citations, quote}``
    whose ``text`` is the GENERIC PII-free label from :func:`applicable_items` (never
    a profile value — threat T-26-04).

    Returns ``None`` — a fail-closed ABSTENTION, never an ungrounded claim — on:
    :class:`searchindex.EmptyQuery`, zero hits, an all-country-specific hit list, an
    unresolvable/sha-drifted chunk (:func:`searchindex.resolve` -> ``None``), or an
    empty quote. An optional ``item['family']`` further constrains retrieval to a
    relpath prefix (defense-in-depth — the relpath backstop below is the hard
    guarantee).
    """
    query = str(item.get("query") or "")
    family = item.get("family")  # optional per-item family= retrieval constraint
    try:
        res = searchindex.search(db, query, limit=5, family=family)
    except searchindex.EmptyQuery:
        return None

    for hit in res.get("hits") or []:
        chunk_id = hit.get("chunk_id")
        if not chunk_id:
            continue
        relpath = hit.get("relpath") or str(chunk_id).split("#", 1)[0]
        # Backstop: NEVER cite a per-country page — skip to the next generic hit.
        if _is_country_specific(relpath):
            continue
        chunk = searchindex.resolve(db, chunk_id)  # None == miss/drift -> fail-closed
        if chunk is None:
            continue
        # Re-check the RESOLVED relpath (resolve() is the source of truth, not the
        # search snippet row) before trusting the chunk for a citation.
        if _is_country_specific(chunk.get("relpath", "")):
            continue
        quote = _verbatim_quote(chunk.get("text", ""))
        if not quote:
            continue
        return {
            "id": item["doc_type"],
            "text": item["text"],           # GENERIC PII-free label — never a profile value
            "citations": [chunk_id],
            "quote": quote,
        }
    return None


def _assemble_answer(grounded: list[tuple[dict, str]], abstentions: list[str]) -> dict:
    """Assemble the 5-key Phase-25 answer object (PII confined to ``basis[]``)."""
    return {
        "question": _ANSWER_QUESTION,
        "claims": [claim for claim, _basis in grounded],
        "basis": [basis for _claim, basis in grounded],
        "abstentions": list(abstentions),
        "prose": "",
    }


def build_answer(profile: dict, db: Path) -> dict:
    """Assemble + gate the Phase-25 answer object for a profile's Layer-1 checklist.

    Selects applicable items (:func:`applicable_items`), grounds each one
    (:func:`grounded_claim`), and assembles
    ``{question, claims[], basis[], abstentions[], prose}`` with ALL profile PII
    confined to ``basis[]`` — every claim carries only the GENERIC label plus a
    verbatim corpus quote (threat T-26-04). Runs the assembled answer THROUGH the
    shipped Phase-25 gate (:func:`grounding.check_answer`) and demotes any claim the
    gate rejects to an explicit abstention, so the RETURNED answer always verifies
    ``pass`` (grounding-by-construction). The RETURN value is the answer object; the
    Plan-03 CLI verb owns render -> scan -> write.

    Honesty boundary (SC1): zero applicable items, or every item ungroundable, yields
    an explicit abstention — NEVER an empty, claimless, abstention-less answer.
    """
    items = applicable_items(profile)

    grounded: list[tuple[dict, str]] = []   # (claim, PII basis sentence) pairs
    abstentions: list[str] = []
    for item in items:
        claim = grounded_claim(db, item)
        if claim is None:
            abstentions.append(
                f"{item['doc_type']}: no resolving generic corpus citation found "
                "— omitted from the gated checklist."
            )
            continue
        grounded.append((claim, item["basis"]))

    answer = _assemble_answer(grounded, abstentions)

    # Fail-closed gate (grounding-by-construction): pass the assembled answer THROUGH
    # the shipped Phase-25 gate; demote any claim it rejects to an explicit
    # abstention so the returned answer always verifies `pass`. By construction
    # grounded_claim only emits resolving+verbatim claims, so this is belt-and-braces.
    report = grounding.check_answer(answer, db)
    if report["violations"]:
        rejected = {v["id"]: v["reasons"] for v in report["violations"]}
        for claim, _basis in grounded:
            if claim["id"] in rejected:
                abstentions.append(
                    f"{claim['id']}: failed the grounding gate "
                    f"({', '.join(rejected[claim['id']])}) — demoted to abstention."
                )
        grounded = [(c, b) for c, b in grounded if c["id"] not in rejected]
        answer = _assemble_answer(grounded, abstentions)

    # Honesty boundary (SC1): never an empty, claimless answer with NO abstention.
    if not answer["claims"] and not answer["abstentions"]:
        answer["abstentions"] = [
            "No applicable Layer-1 document could be grounded against the corpus "
            "— nothing to assert."
        ]
    return answer
