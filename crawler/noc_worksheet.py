"""Grounded NOC-2021 duty worksheet generator (Phase 43 — NOC-01/NOC-02, Plan 01).

A validated 5-digit claimed NOC resolves its PINNED corpus chunks by EXACT
``chunk_id`` (never fuzzy / BM25 — a ranked lookup can return a neighbour
occupation), classifies each chunk by its stored ``section`` heading breadcrumb
(NEVER by a positional ordinal assumption), collects the lead statement, ALL
consecutive Main-duties chunks (a long list overflows the deterministic chunker
onto two chunks for ~9.6% of the corpus), and the Employment-requirements
chunk(s).

The per-duty split is a CORPUS-STRUCTURE + INDEX-GROUNDING design (WR-01/WR-02):
the AUTHORITATIVE list of duties is parsed STRUCTURALLY from the NOC markdown
SOURCE (each physical ``- `` line under the exact ``## Main duties`` heading is
ONE item — internal ``" - "`` hyphens stay inside the item, grouped
sub-occupation headers are kept VERBATIM, and only the exact boilerplate lead
line is dropped), NOT from the flattened index chunk. Parsing the flattened chunk
could neither tell a grouped header's internal ``" - "`` (e.g. 72410's
"Mechanical repairers - motor vehicle manufacturing") from a bullet delimiter
(WR-01 over-split) nor recover a duty the deterministic chunker split across a
chunk boundary (WR-02 dropped continuation, e.g. 11202 / 31100). Each full source
item is then DETERMINISTICALLY mapped, IN ORDER, onto the ordinal-ordered
Main-duties chunk STREAM: a whitespace-normalized token alignment locates the
item's span and emits ONE OR MORE exact per-chunk quote fragments (a duty that
overflows a boundary carries a fragment cited to EACH chunk it spans). EVERY
fragment is re-verified verbatim-present in its OWN sha-validated chunk via
``grounding.quote_is_grounded``; an item that cannot be covered in order across
grounded chunks FAILS CLOSED (``None``). The result renders a vault-only cited
worksheet with the SAFE-04 screening notice, imports it as a ``noc_worksheet``
document, and captures one born-pending value per confirmable item (lead statement
+ each duty, each carrying its ordered ``citations``) linked to a DEDICATED INERT
``review.noc`` factor (NEVER ``core.work``, so the frozen ``core.work`` audit
never reads a duty value). There is NO scoring / overlap / "essential"-invention
path — every emitted span is a VERBATIM corpus/source substring.

This module composes only frozen, release-gate-proven primitives
(``searchindex.resolve`` / ``searchindex.relpath_sections`` / ``chunk_sha``,
``grounding.quote_is_grounded``, ``paths.resolve_within``,
``audit_report.SCREENING_NOTICE``, ``vault`` writes, ``extraction.PARSER_VERSION``)
plus a read-only, containment-guarded read of the NOC markdown source (parsed with
``yaml.safe_load`` for its frontmatter ONLY — an already-present dep) — pure
stdlib + already-present deps, ZERO new dependencies. Retrieval reads the chunks
table read-only + parameter-bound; ``relpath_sections`` is a table-of-contents
(chunk_id/section only, no text), so every quotable span still flows through the
single sha-validated ``searchindex.resolve`` trust path, and every duty fragment
is a normalized substring of a resolved chunk.

Retrieval is fail-closed and SECTION-aware: a malformed claim, an absent NOC, or
an absent/ambiguous REQUIRED section (no lead statement, not exactly one lead, or
no Main-duties chunk) or a hash-drifted required chunk yields ``None`` from
``resolve_noc_spans`` (a normal refusal signal, never fabricated duty text, and
NEVER a positional chunk mislabelled as a different section). The DUTY-SPLIT
availability fault is DISTINCT (WR-01): once the index has resolved the NOC, an
absent/uncontained/unreadable/frontmatter-drifted NOC markdown SOURCE, or a source
item that cannot be grounded in order across the Main-duties chunk stream, raises a
typed :class:`NocSourceUnavailable` (a corpus-integrity fault carrying a STABLE,
PII-free ``reason=noc_source_unavailable`` token and NO absolute path) so a broken
corpus is never misdiagnosed as a bad ``--noc-code`` (``unresolved_noc``) nor
masked as a clean success.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from crawler import audit_report, extraction, grounding, paths, searchindex, vault
from crawler.models.vault import CrsProfileFactor

# NOC-2021 codes are exactly five digits (5-digit code + TEER). The untrusted
# claim is validated to this shape BEFORE any chunk_id is built (V5 input
# validation) so a malformed claim can never reach the corpus reader.
_NOC_CODE_RE = re.compile(r"^\d{5}$")

# The boilerplate lead bullet StatCan prefixes to every Main-duties list. Dropped
# from the per-duty split (it is not a confirmable duty); matched case-insensitively
# on the bullet body.
_BOILERPLATE_PREFIX = "this group performs"

# The heading-breadcrumb separator the chunker stamps into ``chunks.section``
# (mirrors ``searchindex._SEP`` — U+203A). The TRAILING component after the last
# separator is the section a chunk belongs to (e.g. "Main duties").
_SECTION_SEP = " \u203a "

# The three StatCan NOC-profile section labels this worksheet reads. Classification
# is EXACT trailing-breadcrumb equality (never a fuzzy / substring match), so a
# neighbour heading can never be silently misread as one of these.
_LEAD_SECTION = "Lead statement"
_MAIN_SECTION = "Main duties"
_REQS_SECTION = "Employment requirements"

# A NOC unit-group profile is a handful of chunks; nothing legitimate exceeds this.
# A defensive upper bound on the ordinal walk keeps a malformed/huge index bounded.
_MAX_SPAN_ORDINAL = 64

# The EXACT Main-duties section heading in the NOC markdown source. The
# structural source parse reads every physical ``- `` line from this heading
# through the next ``## `` heading — this is the AUTHORITATIVE duty list (the
# flattened index chunk cannot distinguish a grouped header's internal ``" - "``
# from a bullet delimiter, nor recover a boundary-split continuation).
_MAIN_HEADING = "## Main duties"

# The frontmatter ``source_type`` a NOC profile document must declare. Validated
# before any source item is trusted, so a mis-derived / drifted path fails closed.
_SOURCE_TYPE_NOC = "noc"

# The STABLE, PII-free reason token every "authoritative NOC source is
# missing/unreadable/drifted" refusal carries. DELIBERATELY DISTINCT from
# ``unresolved_noc`` (an absent / malformed NOC CODE — "check the code"): a source
# fault means the section-aware INDEX resolved the NOC but the co-located markdown
# SOURCE the structural duty split REQUIRES is gone / broken → refresh / rebuild
# the authoritative corpus, NOT a bad ``--noc-code``.
NOC_SOURCE_UNAVAILABLE_REASON = "noc_source_unavailable"


class NocSourceUnavailable(Exception):
    """The authoritative NOC markdown source is missing / unreadable / drifted.

    Raised (NEVER returned) once the section-aware INDEX has ALREADY resolved a
    NOC — so the 5-digit code is well-formed AND present in the pinned index —
    but the co-located ``noc-2021/noc-{code}.md`` SOURCE that the structural duty
    split REQUIRES is absent, unreadable, escapes containment (symlink / ``..``),
    carries missing / mismatched frontmatter, lacks a ``## Main duties`` heading,
    or cannot be grounded IN ORDER across the Main-duties chunk stream. This is a
    corpus-integrity / deployment fault (refresh / rebuild the authoritative
    corpus), DISTINCT from an absent-or-malformed NOC code (``unresolved_noc`` —
    check the code) and from a source-present, groundable NOC (success).

    The message is a STABLE, PII-free token: it carries the ``reason`` code and
    the (already caller-supplied, non-PII) 5-digit NOC code ONLY — NEVER an
    absolute path, a candidate id, or any duty text (the raising sites use
    ``raise … from None`` so an underlying ``OSError`` / ``PathEscapeError`` can
    never chain its absolute path into a traceback).
    """

    reason = NOC_SOURCE_UNAVAILABLE_REASON

    def __init__(self, code: str) -> None:
        super().__init__(
            f"NOC {code} authoritative source unavailable "
            f"(reason={NOC_SOURCE_UNAVAILABLE_REASON})")
        self.code = code


# Word tokenizer for the source-item -> chunk-stream alignment: any run of
# non-whitespace is one token. Whitespace-normalization (collapse + lowercase)
# happens on the token text so alignment is robust to the chunker's newline ->
# space flattening while the emitted quote fragments stay VERBATIM chunk slices.
_WORD_RE = re.compile(r"\S+")


def _section_label(section: "str | None") -> str:
    """The normalized trailing section label from a ``chunks.section`` breadcrumb.

    ``"NOC 2021 72400 — … › Main duties"`` -> ``"Main duties"``. Pure string op
    (split on the breadcrumb separator, take the last component, strip) — never a
    ranked / fuzzy match.
    """
    return (section or "").split(_SECTION_SEP)[-1].strip()


def _chunk_ordinal(chunk_id: str) -> int:
    """Parse the trailing ``#NNN`` ordinal from a ``relpath#ordinal`` chunk_id.

    ``"noc-2021/noc-72400.md#003"`` -> ``3``. The ordinal is the deterministic
    per-document chunk index, reused as the middle field of every duty_id so ids
    stay collision-free across multiple Main-duties chunks. Raises ``ValueError``
    on a malformed id (an internal invariant — chunk_ids are minted by the frozen
    indexer, never user input).
    """
    m = re.search(r"#(\d+)$", chunk_id)
    if m is None:
        raise ValueError(f"chunk_id has no #ordinal suffix: {chunk_id!r}")
    return int(m.group(1))


def resolve_noc_spans(db: "str | Path", code: str) -> dict | None:
    """Resolve the lead / Main-duties / Employment-requirements spans for *code*.

    Validates *code* against ``\\d{5}`` FIRST (never builds a chunk_id from a
    malformed claim), reads the document's read-only, parameter-bound
    table-of-contents via :func:`crawler.searchindex.relpath_sections`, and
    classifies EACH chunk by its stored ``section`` heading breadcrumb — NEVER by
    a positional ordinal assumption (the bug this replaces: ``#003`` is the
    Employment-requirements chunk for a short list but the SECOND Main-duties
    chunk when the list overflows, so trusting the ordinal mislabels duty text as
    requirements and drops the real requirements). Every quotable span is then
    fetched through the frozen sha-validated :func:`crawler.searchindex.resolve`
    (read-only, positional-bound, ``None`` on miss OR sha-drift) — NEVER
    :func:`crawler.searchindex.search` (BM25 ranked retrieval can return a
    neighbour occupation).

    Returns ``{"code", "lead", "main", "reqs"}`` where:

      * ``lead`` is the single Lead-statement resolve dict;
      * ``main`` is the ordinal-ordered LIST of Main-duties resolve dicts (ONE for
        a normal NOC, MANY for an overflowed one) — each chunk_id/text/hash
        preserved;
      * ``reqs`` is the ordinal-ordered LIST of Employment-requirements resolve
        dicts (zero or many; informational).

    Fails closed to ``None`` when: the claim is malformed; the document is absent;
    a REQUIRED section is absent or ambiguous (no lead, not exactly one lead, or no
    Main-duties chunk); or any listed lead/main/reqs chunk fails to resolve
    (absent / hash-drift). It NEVER returns a partial or a positionally-guessed
    span.
    """
    if not isinstance(code, str) or not _NOC_CODE_RE.match(code):
        return None  # malformed claim → refuse before touching the corpus
    rel = f"noc-2021/noc-{code}.md"
    toc = searchindex.relpath_sections(db, rel)
    if not toc:
        return None  # absent NOC (or unreadable index) → fail-closed

    # Classify each chunk by its EXACT trailing section label (never positional).
    lead_ids: list[str] = []
    main_ids: list[str] = []
    reqs_ids: list[str] = []
    for entry in toc:
        if entry["ordinal"] > _MAX_SPAN_ORDINAL:
            continue  # defensive bound; a real profile never reaches this
        label = _section_label(entry["section"])
        if label == _LEAD_SECTION:
            lead_ids.append(entry["chunk_id"])
        elif label == _MAIN_SECTION:
            main_ids.append(entry["chunk_id"])
        elif label == _REQS_SECTION:
            reqs_ids.append(entry["chunk_id"])

    # REQUIRED sections must be present + unambiguous: exactly one lead statement
    # and at least one Main-duties chunk. (Many Main-duties chunks is the SUPPORTED
    # overflow case, not ambiguity.) Employment requirements are informational and
    # may legitimately be absent → do not gate on them.
    if len(lead_ids) != 1 or len(main_ids) < 1:
        return None  # absent / ambiguous required section → fail-closed

    # sha-validated resolve for every needed chunk; any miss/drift → fail-closed
    # (never emit a stale/tampered span, never fabricate).
    lead = searchindex.resolve(db, lead_ids[0])
    if lead is None:
        return None
    main: list[dict] = []
    for cid in main_ids:
        span = searchindex.resolve(db, cid)
        if span is None:
            return None  # drift on a required Main-duties chunk → fail-closed
        main.append(span)
    reqs: list[dict] = []
    for cid in reqs_ids:
        span = searchindex.resolve(db, cid)
        if span is None:
            return None  # a listed reqs chunk that fails sha → fail-closed
        reqs.append(span)
    return {"code": code, "lead": lead, "main": main, "reqs": reqs}


def _frontmatter_and_body(text: str) -> "tuple[str, str]":
    """Split a corpus markdown file into ``(raw_frontmatter, body)``.

    Mirrors ``dupaudit.body_of`` / ``dupaudit._frontmatter_of`` (the same split the
    frozen indexer used to build the chunks): the block delimited by the opening
    ``---`` and the first ``\\n---`` is the frontmatter; everything after the line
    that closes it is the body. A file without a leading frontmatter block yields
    ``("", text)``.
    """
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            nl = text.find("\n", end + 1)
            body = text[nl + 1:] if nl != -1 else ""
            return fm, body
    return "", text


def _extract_main_duty_items(body: str) -> "list[str] | None":
    """Parse the ordered Main-duties source items from a NOC markdown *body*.

    Finds the EXACT ``## Main duties`` heading line, then walks every physical
    line up to the next ``## `` heading. Each ``- ``-prefixed line is ONE item
    (its body VERBATIM, the leading ``"- "`` marker stripped) — an internal
    ``" - "`` (a grouped sub-occupation header such as
    ``"Mechanical repairers - motor vehicle manufacturing"``) stays INSIDE the
    item, and grouped headers are kept verbatim as items (there is deliberately NO
    semantic header-vs-duty classification). ONLY the exact
    ``"This group performs…"`` boilerplate lead line is dropped. Returns the
    ordered item list, or ``None`` when no ``## Main duties`` heading exists
    (fail-closed — a drifted source can never yield a partial/guessed list).
    """
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == _MAIN_HEADING:
            start = i + 1
            break
    if start is None:
        return None  # no Main-duties heading → fail-closed
    items: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break  # next section heading terminates Main duties
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        if not item:
            continue
        if item.lower().startswith(_BOILERPLATE_PREFIX):
            continue  # boilerplate lead line — not a confirmable duty
        items.append(item)
    return items


def _source_main_duty_items(db: "str | Path", code: str) -> "list[str] | None":
    """Return the ordered Main-duties SOURCE items for *code*, or fail-closed.

    Derives the NOC markdown source path DETERMINISTICALLY from the index location
    (``Path(db).parent`` is the corpus root, ``noc-2021/noc-{code}.md`` the
    relpath) and CONTAINS it beneath that root via
    :func:`crawler.paths.resolve_within` (rejecting any symlink / ``..`` escape),
    reads it read-only, validates its frontmatter is the RIGHT document
    (``source_type == "noc"`` AND ``noc_code == code``) with ``yaml.safe_load``
    ONLY (never ``yaml.load``), and parses the ``## Main duties`` section
    structurally via :func:`_extract_main_duty_items`.

    Fail-closed semantics SEPARATE the two causes (WR-01 diagnosis) so callers can
    tell a bad NOC code from a broken corpus:

      * a MALFORMED *code* (syntax, not availability) returns ``None`` — the
        existing invalid-input semantics (``resolve_noc_spans`` guards this before
        the split is ever reached);
      * a MISSING / uncontained / unreadable source, malformed or drifted
        frontmatter (wrong / missing ``source_type`` or ``noc_code``), or an
        absent ``## Main duties`` heading raises :class:`NocSourceUnavailable` — a
        corpus-integrity fault (refresh / rebuild the corpus), never an
        input-error. ``raise … from None`` on the I/O paths keeps any absolute
        path out of the exception chain.

    This is the AUTHORITATIVE duty list — the flattened index chunk is used ONLY
    to GROUND + CITE each item, never to enumerate them.
    """
    if not isinstance(code, str) or not _NOC_CODE_RE.match(code):
        return None  # malformed CODE (syntax) — NOT a source-availability fault
    rel = f"noc-2021/noc-{code}.md"
    corpus_root = Path(db).resolve().parent
    try:
        src = paths.resolve_within(corpus_root, rel)
    except paths.PathEscapeError:
        raise NocSourceUnavailable(code) from None  # containment escape
    if not src.is_file():
        raise NocSourceUnavailable(code)            # missing source tree/file
    try:
        text = src.read_text(encoding="utf-8")
    except OSError:
        raise NocSourceUnavailable(code) from None  # unreadable source
    fm_raw, body = _frontmatter_and_body(text)
    try:
        meta = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError:
        raise NocSourceUnavailable(code) from None  # malformed frontmatter
    if not isinstance(meta, dict):
        raise NocSourceUnavailable(code)
    if str(meta.get("source_type", "")) != _SOURCE_TYPE_NOC:
        raise NocSourceUnavailable(code)            # wrong / drifted facet
    if str(meta.get("noc_code", "")) != code:
        raise NocSourceUnavailable(code)            # resolved file is not this NOC
    items = _extract_main_duty_items(body)
    if items is None:
        raise NocSourceUnavailable(code)            # no ## Main duties heading
    return items


def _norm_tokens(text: str) -> "list[tuple[str, int, int]]":
    """Tokenize *text* into ``(lowercased_token, start, end)`` over the ORIGINAL text.

    Each token is a maximal non-whitespace run; ``start``/``end`` are character
    offsets INTO *text* so a matched token run can be sliced back to a VERBATIM
    substring. Lowercasing mirrors :func:`crawler.grounding._norm` (whitespace +
    case are the only normalization) so alignment survives the chunker's newline
    -> space flattening.
    """
    return [(m.group(0).lower(), m.start(), m.end())
            for m in _WORD_RE.finditer(text)]


def _find_token_run(tokens: list, needle: list, start: int) -> int:
    """Index of the FIRST contiguous occurrence of *needle* in *tokens* at/after *start*.

    Plain first-match sublist search (``-1`` if absent). Because the source items
    appear in the SAME ORDER in the chunk stream, separated only by a single ``-``
    delimiter token (flattened) or nothing (newline), and the cursor advances past
    each match, the first match at/after the cursor is always the correct next
    item.
    """
    n = len(needle)
    if n == 0:
        return -1
    last = len(tokens) - n
    i = start
    while i <= last:
        if tokens[i:i + n] == needle:
            return i
        i += 1
    return -1


def split_duties(db: "str | Path", code: str,
                 main_spans: list[dict]) -> "list[dict] | None":
    """Map each Main-duties SOURCE item onto grounded per-chunk citation fragments.

    Deterministic + pure over its inputs — SAME source + index → byte-identical
    output. The AUTHORITATIVE item list comes from the NOC markdown source
    (:func:`_source_main_duty_items`); *main_spans* is the ordinal-ordered list of
    already sha-validated Main-duties chunks (ONE for a normal NOC, MANY for an
    overflowed one) used ONLY to ground + cite each item. Each returned duty is::

        {
          "duty_id":   f"{code}:{item_ordinal:02d}",   # SOURCE-item ordinal, stable
          "duty_sha":  chunk_sha(<full source item text>),
          "text":      <full source item text VERBATIM>,
          "citations": [{"chunk_id", "quote"}, ...],    # ordered, ≥1 (>1 = span)
          "citation":  <citations[0]["chunk_id"]>,      # primary compat field
        }

    The stable ``duty_id`` keys off the SOURCE-section item ordinal (never a
    fragile chunk ordinal), so a chunk-boundary move can't renumber a duty;
    ``duty_sha`` fingerprints the FULL source item, so an exact rerun is stable and
    any source edit yields a changed sha / a new pending value. A duty the frozen
    chunker split across a boundary carries ONE fragment per chunk it spans (e.g.
    11202 / 31100 → a ``#002`` fragment + a ``#003`` fragment), each a VERBATIM
    slice re-verified by :func:`crawler.grounding.quote_is_grounded` against its
    OWN chunk.

    Fails closed when the source cannot be produced, DISTINGUISHING the cause
    (WR-01): a MALFORMED *code* returns ``None`` (existing invalid-input
    semantics; never reached post-``resolve_noc_spans``), while a
    missing/unreadable/drifted source OR an item that cannot be covered —
    contiguously, in order, fully — across the grounded chunk stream raises
    :class:`NocSourceUnavailable` (a corpus-integrity fault: once the index has
    resolved the NOC, any split failure is a broken authoritative source, never a
    bad code — never a partial / mis-cited / fabricated duty).
    """
    items = _source_main_duty_items(db, code)
    if items is None:
        return None  # malformed code → fail-closed (source faults already raised)

    # Flatten the ordinal-ordered Main-duties chunks into ONE token stream, keeping
    # each token's (chunk_index, char-span) so a matched run maps back to a verbatim
    # per-chunk slice. Concatenating chunk token lists (no separator token between
    # chunks) is exactly what lets a boundary-split item match contiguously.
    tokens: list[str] = []
    meta: list[tuple[int, int, int]] = []   # (chunk_index, start_off, end_off)
    for ci, span in enumerate(main_spans):
        for tok, s, e in _norm_tokens(span["text"]):
            tokens.append(tok)
            meta.append((ci, s, e))

    duties: list[dict] = []
    cursor = 0
    for ordinal, item_text in enumerate(items):
        needle = [t for (t, _s, _e) in _norm_tokens(item_text)]
        if not needle:
            continue  # a whitespace-only item is never a confirmable duty
        run_start = _find_token_run(tokens, needle, cursor)
        if run_start == -1:
            raise NocSourceUnavailable(code)  # item ungroundable in order → drift
        run_end = run_start + len(needle)  # exclusive
        # Group the matched tokens by the chunk they came from; each group is one
        # verbatim per-chunk quote fragment (an item that overflows a boundary
        # yields >1 group, one citation per chunk).
        citations: list[dict] = []
        i = run_start
        while i < run_end:
            ci = meta[i][0]
            j = i
            while j + 1 < run_end and meta[j + 1][0] == ci:
                j += 1
            span = main_spans[ci]
            fragment = span["text"][meta[i][1]:meta[j][2]]
            if not grounding.quote_is_grounded(fragment, span["text"]):
                raise NocSourceUnavailable(code)  # fragment no longer grounds → drift
            citations.append({"chunk_id": span["chunk_id"], "quote": fragment})
            i = j + 1
        cursor = run_end
        duties.append({
            "duty_id": f"{code}:{ordinal:02d}",
            "duty_sha": searchindex.chunk_sha(item_text),
            "text": item_text,
            "citations": citations,
            "citation": citations[0]["chunk_id"],
        })
    return duties


# The dedicated INERT review factor every NOC duty/lead value is linked to. It is
# deliberately NOT ``core.work`` and is NEVER added to ``FULL_GRID_FACTORS``, so
# ``audit_eligible_values("core.work")`` can never return a duty value and the
# frozen ``core.work`` card stays byte-identical (B1 isolation, threat T43-08).
# Seeding it is a one-time INERT ``upsert_profile_factor`` DATA write (the FK
# parent ``extracted_values.factor_id`` -> ``crs_profile_factors`` requires under
# ``foreign_keys=ON``) — NOT a schema migration.
_REVIEW_NOC_FACTOR_ID = "review.noc"


def _review_noc_factor() -> CrsProfileFactor:
    """The inert ``review.noc`` FK-parent row (never in FULL_GRID_FACTORS)."""
    return CrsProfileFactor(
        factor_id=_REVIEW_NOC_FACTOR_ID, factor_group="additional_points",
        claimed_points=None, claimed_level=None, claimed_value={},
        source="user_entry")


def _render_worksheet(spans: dict, duties: list[dict], code: str) -> str:
    """Render the human-readable, cited worksheet body (vault-only artifact text).

    Prepends the SAFE-04 :data:`crawler.audit_report.SCREENING_NOTICE`, then shows
    the lead statement, each main duty (one bullet per confirmable item, tagged
    with its stable ``duty_id`` and ALL of its ordered source-chunk citations — a
    boundary-split duty renders EVERY chunk it spans, never a dangling single
    citation), and the Employment-requirements chunk(s) (read-only — no per-item
    split), EACH with its exact ``noc-2021/noc-{code}.md#00N`` citation.
    Main-duties and Employment-requirements are rendered under SEPARATE,
    correctly-labelled headings sourced from the SECTION-classified spans, so duty
    text can NEVER be mislabelled as an employment requirement (CR-01). Every
    rendered span is a VERBATIM corpus/source span (nothing is inlined / classified
    / invented). This body is written strictly under the vault and is PII-adjacent —
    it is NEVER returned on a stdout-facing structure.
    """
    lead = spans["lead"]
    main_spans = spans["main"]
    reqs_spans = spans["reqs"]
    main_cits = ", ".join(m["chunk_id"] for m in main_spans)
    lines = [
        audit_report.SCREENING_NOTICE,
        "",
        f"# NOC {code} — work-duty review worksheet",
        "",
        "> Read-only, cited review surface. Each confirmable item below is captured",
        "> as a PENDING value for your per-item confirmation; nothing here is",
        "> SUBSTANTIATED and no NOC-duty fit is asserted by this screening.",
        "",
        f"## Lead statement — {lead['chunk_id']}",
        "",
        lead["text"].strip(),
        "",
        f"## Main duties — {main_cits}",
        "",
    ]
    for d in duties:
        # Render ALL citations (a duty split across a chunk boundary lists each
        # chunk it spans), so the cited surface never advertises a chunk whose
        # content is not rendered here (WR-02).
        cits = ", ".join(c["chunk_id"] for c in d["citations"])
        lines.append(f"- {d['text']}  [{d['duty_id']} · {cits}]")
    lines += ["", "## Employment requirements (read-only)", ""]
    if reqs_spans:
        for r in reqs_spans:
            lines += [f"— {r['chunk_id']} —", "", r["text"].strip(), ""]
    else:
        lines += [
            "_No Employment-requirements section is present in the pinned corpus "
            "for this NOC._",
            "",
        ]
    return "\n".join(lines) + "\n"


def _existing_duty_values(vault_: vault.Vault,
                          candidate_id: str) -> dict[tuple[str, str], dict]:
    """Read-only map of THIS candidate's ``review.noc`` values by (duty_id, duty_sha).

    Narrow SELECT over ``extracted_values`` JOINed to ``documents`` on
    ``candidate_id`` and filtered to ``factor_id='review.noc'`` so the idempotency
    dedup only ever sees this candidate's inert duty rows. Parses each
    ``normalized_value`` ``duty_id``/``duty_sha`` and keys by the pair. This helper
    is strictly read-only — it NEVER mutates a status (no bulk status change): the
    caller reuses the existing ``value_id`` on an exact match and inserts a fresh
    born-pending row otherwise.
    """
    cid = paths.safe_candidate_id(candidate_id)
    rows = vault_.con.execute(
        "SELECT ev.value_id, ev.normalized_value_json, ev.confirmation_status, "
        "ev.document_id FROM extracted_values ev "
        "JOIN documents d ON d.document_id = ev.document_id "
        "WHERE d.candidate_id = ? AND ev.factor_id = ?",
        (cid, _REVIEW_NOC_FACTOR_ID),
    ).fetchall()
    existing: dict[tuple[str, str], dict] = {}
    for r in rows:
        nv = json.loads(r["normalized_value_json"])
        duty_id, duty_sha = nv.get("duty_id"), nv.get("duty_sha")
        if duty_id is None or duty_sha is None:
            continue
        # A (duty_id, duty_sha) key is unique in steady state; first-writer-wins.
        existing.setdefault((duty_id, duty_sha), {
            "value_id": r["value_id"],
            "document_id": r["document_id"],
            "confirmation_status": r["confirmation_status"],
        })
    return existing


def _newest_worksheet_document(vault_: vault.Vault,
                               candidate_id: str) -> str | None:
    """The candidate's most recent ``noc_worksheet`` ``document_id`` (or None).

    Used on an EXACT rerun (every current item already exists) so the returned
    ``worksheet_doc_id`` stays stable without importing a duplicate document.
    """
    cid = paths.safe_candidate_id(candidate_id)
    row = vault_.con.execute(
        "SELECT document_id FROM documents "
        "WHERE candidate_id = ? AND doc_type = 'noc_worksheet' "
        "ORDER BY added_at DESC, document_id DESC LIMIT 1",
        (cid,),
    ).fetchone()
    return None if row is None else row["document_id"]


def generate_worksheet(vault_: vault.Vault, db: "str | Path",
                       candidate_id: str, code: str) -> dict:
    """Render + capture the grounded NOC worksheet for *candidate_id* / *code*.

    Fail-closed FIRST: if :func:`resolve_noc_spans` returns ``None`` (absent /
    wrong-family / hash-drift / quote-drift) this writes ZERO artifacts and ZERO
    values and returns ``{worksheet_doc_id: None, value_ids: [], duty_count: 0}``.

    Otherwise it writes ONE vault-only cited artifact (under the vault via
    :func:`crawler.paths.resolve_within`, NEVER ``corpus/``) and captures one
    born-pending value per confirmable item (lead statement + each duty) on the
    inert ``review.noc`` factor (NEVER ``core.work``).

    Regeneration is IDEMPOTENT by ``(duty_id, duty_sha)`` (threat T43-09): an exact
    match REUSES the existing ``value_id`` (no new row, status preserved), a
    brand-new ``duty_id`` inserts exactly ONE born-pending row, and a same-``duty_id``
    /new-``duty_sha`` DRIFT inserts at most ONE new born-pending row for the current
    sha while the old value is left UNTOUCHED. A new ``noc_worksheet`` document +
    ``extraction_runs`` row are created ONLY when >=1 new value is inserted; an
    exact rerun reuses the newest existing document and returns the SAME
    ``{worksheet_doc_id, value_ids, duty_count}``.

    The returned summary is PII-LIGHT — ids / counts / citations ONLY; the
    worksheet body and raw duty spans stay vault-only. Every refusal carries a
    stable ``reason`` token so the CLI can tell a bad NOC code
    (``unresolved_noc``) from a broken corpus source
    (``noc_source_unavailable``) — see WR-01.
    """
    spans = resolve_noc_spans(db, code)
    if spans is None:
        # Fail-closed refusal: absent / malformed / wrong-family / hash-drift NOC.
        # No partial worksheet, no document, no value. "check the --noc-code".
        return {
            "noc_code": code, "worksheet_doc_id": None,
            "value_ids": [], "duty_count": 0, "citations": [],
            "reason": "unresolved_noc",
        }

    try:
        duties = split_duties(db, code, spans["main"])
    except NocSourceUnavailable:
        # The section-aware INDEX resolved the NOC, but the AUTHORITATIVE markdown
        # SOURCE is missing / unreadable / drifted / ungroundable — a
        # corpus-integrity fault, NOT a bad code. Fail closed with a DISTINCT
        # reason so the CLI says "refresh/rebuild the corpus", not "check the
        # code" (WR-01). Still zero artifacts, zero values.
        return {
            "noc_code": code, "worksheet_doc_id": None,
            "value_ids": [], "duty_count": 0, "citations": [],
            "reason": NOC_SOURCE_UNAVAILABLE_REASON,
        }
    if duties is None:
        # Defensive: a malformed code slips past resolve_noc_spans (unreachable in
        # practice) → same unresolved refusal (no partial worksheet/document/value).
        return {
            "noc_code": code, "worksheet_doc_id": None,
            "value_ids": [], "duty_count": 0, "citations": [],
            "reason": "unresolved_noc",
        }
    lead = spans["lead"]
    lead_text = lead["text"]

    # Deterministic current-item order: lead statement first, then each duty. Each
    # confirmable item carries its own stable (duty_id, duty_sha) + its ORDERED
    # citation fragments (a duty that overflows a chunk boundary carries one
    # {chunk_id, quote} per chunk it spans; the lead is a single-chunk citation).
    items: list[dict] = [{
        "field_name": "noc_lead_statement",
        "raw_text": lead_text,
        "duty_id": f"{code}:{_chunk_ordinal(lead['chunk_id'])}:00",
        "duty_sha": searchindex.chunk_sha(lead_text),
        "citations": [{"chunk_id": lead["chunk_id"], "quote": lead_text}],
        "citation": lead["chunk_id"],
    }]
    for d in duties:
        items.append({
            "field_name": "noc_duty",
            "raw_text": d["text"],
            "duty_id": d["duty_id"],
            "duty_sha": d["duty_sha"],
            "citations": d["citations"],
            "citation": d["citation"],
        })

    # PII-light citation set: the ACTUAL section-classified chunk_ids (lead + every
    # Main-duties chunk + every Employment-requirements chunk), in span order — no
    # positional ``#003``-is-requirements assumption.
    citations = (
        [lead["chunk_id"]]
        + [m["chunk_id"] for m in spans["main"]]
        + [r["chunk_id"] for r in spans["reqs"]]
    )

    # Vault-only artifact: render + write STRICTLY under the vault (never corpus/).
    artifact = paths.resolve_within(
        vault_.root, "output", "noc-worksheets", f"noc-{code}.md")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(_render_worksheet(spans, duties, code), encoding="utf-8")

    # Idempotency: which current items already exist by (duty_id, duty_sha)?
    existing = _existing_duty_values(vault_, candidate_id)
    has_new = any((it["duty_id"], it["duty_sha"]) not in existing for it in items)

    if has_new:
        # Seed the inert review.noc FK parent ONCE (data upsert, not a migration),
        # then import the new document + open a run for the fresh values.
        vault.upsert_profile_factor(vault_, _review_noc_factor())
        doc = vault.import_document(
            vault_, candidate_id, artifact, doc_type="noc_worksheet")
        worksheet_doc_id = doc.document_id
        run = vault.record_extraction_run(
            vault_, document_id=worksheet_doc_id,
            parser_version=extraction.PARSER_VERSION)
    else:
        # EXACT rerun: no new value → no new document/run; reuse the newest one.
        worksheet_doc_id = _newest_worksheet_document(vault_, candidate_id)
        run = None

    value_ids: list[str] = []
    for it in items:
        key = (it["duty_id"], it["duty_sha"])
        hit = existing.get(key)
        if hit is not None:
            # EXACT MATCH: reuse the existing value_id — NO insert, NO re-status
            # (pending/confirmed/corrected/rejected preserved).
            value_ids.append(hit["value_id"])
            continue
        # NEW duty_id OR same-duty_id/new-duty_sha DRIFT: insert exactly ONE
        # born-pending row for the CURRENT (duty_id, duty_sha). Any old drifted
        # value is left untouched (it becomes stale/ineligible, never mutated).
        vid = vault.add_extracted_value(
            vault_, document_id=worksheet_doc_id, page_id=None,
            factor_id=_REVIEW_NOC_FACTOR_ID, field_name=it["field_name"],
            raw_text=it["raw_text"],
            normalized_value={
                "duty_id": it["duty_id"], "duty_sha": it["duty_sha"],
                "citations": it["citations"], "citation": it["citation"],
            },
            bbox=None, extractor_confidence=None, quality_flag="ok",
            extraction_run_id=run)
        value_ids.append(vid)

    return {
        "noc_code": code, "worksheet_doc_id": worksheet_doc_id,
        "value_ids": value_ids, "duty_count": len(duties),
        "citations": citations,
    }
