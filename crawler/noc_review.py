"""Inert NOC work-duty review sidecar (Phase 43 — 43-02, NOC-02/NOC-03).

A pure, read-only roll-up over the born-pending / confirmed ``noc_duty`` +
``noc_lead_statement`` values captured by Plan 01. It reports the duty-review
verdict as a PII-light closed dict whose ``status`` is STRUCTURALLY constrained to
``{"AT-RISK", "GAP", "N/A"}`` — there is NO branch that can emit
``"SUBSTANTIATED"`` and NO numeric score / ``crs_points`` anywhere. Confirming
individual duties is NOT the officer's R87.1(2)(c) essential-duty finding, so even a
fully-confirmed, fresh, grounded set terminates at ``("AT-RISK",
"duty_review_manual")`` — human confirmation only changes the *reason* / completeness
of the AT-RISK signal, it never flips it green (NOC-03, Pitfall 1).

Inert-by-construction (like :mod:`crawler.policy_offer`):
  * NOT wired into the :mod:`crawler.auditors` dispatch — it is not a CRS decider and
    is never added to that lookup table at all;
  * NOT part of :data:`crawler.auditors.FULL_GRID_FACTORS` and NOT summed into any
    ``PublicAuditEnvelope`` — it never contributes to a CRS total;
  * NO Phase-45 / MEC wiring here — the sidecar is shipped and unit-tested only.
    Phase 45 (the Minimum Entry Criteria integrator) consumes it LATER as an
    ``AT-RISK`` human-confirmed skilled-work input, never as an automatic award.

Trust surface (NOC-02):
  * Duty values are read ONLY through the dedicated inert ``review.noc`` factor and
    ONLY for the current candidate — via the candidate-scoped
    ``_candidate_eligible_duty_values`` (a ``JOIN documents … WHERE candidate_id = ?``
    wrapper around the shipped 5-key ``crawler.vault.is_audit_eligible`` choke point)
    — NEVER ``core.work``, so the frozen ``core.work`` audit is never read or touched
    (B1 isolation, threat T43-06), and never another candidate's rows (WR-02).
  * A confirmation counts only when it passes Layer 1 (the shipped 5-key
    :func:`crawler.vault.is_audit_eligible` choke point, applied inside
    ``_candidate_eligible_duty_values``) AND its parsed ``(duty_id, duty_sha)`` is in
    the CURRENT worksheet key set rebuilt from the live corpus split (each
    ``duty_id`` counted at most once, so an old drifted value never inflates
    ``confirmed_count``) AND — added in the two-layer staleness pass — Layer 2
    corpus-drift re-check.

PII-light: the returned dict carries ONLY the closed :data:`PUBLIC_FIELDS` set —
no ``raw_text``, no evidence (``ev_``) id, no absolute path. stdlib-only.
"""

from __future__ import annotations

import json

from crawler import crs_rules, grounding, noc_worksheet, paths, searchindex, vault

# The closed, public field set the sidecar returns. Kept as a module constant so
# the PII-light contract is asserted structurally (no raw duty text / ev_ id / path
# ever leaks) by the 43-02 test sweep.
PUBLIC_FIELDS: tuple[str, ...] = (
    "noc_code",
    "duty_count",
    "confirmed_count",
    "status",
    "reason",
    "citations",
)

# The dedicated INERT review factor every NOC duty/lead value is linked to. It is
# deliberately NOT ``core.work`` and is NEVER in ``FULL_GRID_FACTORS``, so
# ``audit_eligible_values("core.work")`` can never return a duty value and the
# frozen ``core.work`` card stays byte-identical (B1 isolation, threat T43-06).
_REVIEW_NOC_FACTOR_ID = "review.noc"


def _pack(noc_code: str, duty_count: int, confirmed_count: int,
          status: str, reason: str, citations: list[str]) -> dict:
    """Build the closed PII-light dict in :data:`PUBLIC_FIELDS` order (no extras)."""
    return {
        "noc_code": noc_code,
        "duty_count": duty_count,
        "confirmed_count": confirmed_count,
        "status": status,           # ALWAYS one of {"AT-RISK", "GAP", "N/A"}
        "reason": reason,
        "citations": citations,
    }


def _current_key_sets(db: "str", noc_code: str) -> dict | None:
    """Rebuild the CURRENT worksheet ``{(duty_id, duty_sha)}`` from the live corpus.

    Reuses the SAME deterministic Plan-01 retrieval + split
    (:func:`crawler.noc_worksheet.resolve_noc_spans` +
    :func:`crawler.noc_worksheet.split_duties`) — NEVER a second retrieval / split
    path. ``resolve_noc_spans`` is SECTION-aware (``main`` / ``reqs`` are the
    ordinal-ordered LISTS of Main-duties / Employment-requirements spans) and
    ``split_duties`` parses the AUTHORITATIVE markdown source, grounding each source
    item across the Main-duties chunk stream, so the duty key set spans ALL
    Main-duties chunks and INCLUDES a duty the chunker split across a boundary (a
    continuation is never silently dropped). Returns ``None`` (fail-closed) when the
    NOC does not resolve (absent / drifted index → nothing to review). RAISES
    :class:`crawler.noc_worksheet.NocSourceUnavailable` (propagated, NOT swallowed)
    when the index resolved the NOC but its authoritative markdown SOURCE is
    missing / unreadable / drifted / ungroundable — a corpus-integrity fault the
    caller maps to a DISTINCT ``noc_source_unavailable`` verdict rather than a
    clean ``no_worksheet`` (WR-01). ``duty_count`` is the size of the current DUTY
    set; the lead statement carries its own separate key. ``citations`` is the
    ACTUAL section-classified chunk_id set (never a positional
    ``#003``-is-requirements guess).
    """
    spans = noc_worksheet.resolve_noc_spans(db, noc_code)
    if spans is None:
        return None
    duties = noc_worksheet.split_duties(db, noc_code, spans["main"])
    if duties is None:
        return None  # malformed code (source faults already raised) → fail-closed
    lead = spans["lead"]
    lead_ordinal = int(lead["chunk_id"].rsplit("#", 1)[-1])
    citations = (
        [lead["chunk_id"]]
        + [m["chunk_id"] for m in spans["main"]]
        + [r["chunk_id"] for r in spans["reqs"]]
    )
    return {
        "duty_keys": {(d["duty_id"], d["duty_sha"]) for d in duties},
        "lead_key": (f"{noc_code}:{lead_ordinal}:00",
                     searchindex.chunk_sha(lead["text"])),
        "duty_count": len(duties),
        "citations": citations,
    }


def _candidate_eligible_duty_values(
    vault_: vault.Vault,
    factor_id: str,
    candidate_id: str,
    registry_fingerprint: str | None = None,
) -> list:
    """Candidate-scoped mirror of ``vault.audit_eligible_values`` for the sidecar.

    The shipped :func:`crawler.vault.audit_eligible_values` filters by ``factor_id``
    ALONE — correct for the per-candidate ``vault.sqlite`` that ``open_vault`` mints
    (only one candidate's rows exist there). The sidecar makes that candidate scope
    EXPLICIT so ALL of its read paths agree even if that per-candidate-DB invariant
    ever changes (a shared / multi-candidate DB) — a latent cross-candidate leak
    otherwise (WR-02). It JOINs ``extracted_values`` to ``documents`` on
    ``candidate_id`` (parameter-bound), restricts to confirmed/corrected rows, and
    then applies the SAME shipped 5-key ``vault.is_audit_eligible`` choke point per
    row — never a second, weaker gate. Read-only: no status is mutated.
    """
    cid = paths.safe_candidate_id(candidate_id)
    rows = vault_.con.execute(
        "SELECT ev.value_id FROM extracted_values ev "
        "JOIN documents d ON d.document_id = ev.document_id "
        "WHERE d.candidate_id = ? AND ev.factor_id = ? "
        "AND ev.confirmation_status IN ('confirmed', 'corrected') "
        "ORDER BY ev.value_id",
        (cid, factor_id),
    ).fetchall()
    result: list = []
    for r in rows:
        # The shipped SC3 quarantine gate (confirmed/corrected + quality ok + not
        # 5-key stale) — the ONLY predicate the sidecar trusts, unchanged.
        if vault.is_audit_eligible(
            vault_,
            r["value_id"],
            registry_fingerprint=registry_fingerprint,
        ):
            val = vault.get_extracted_value(vault_, r["value_id"])
            if val is not None:
                result.append(val)
    return result


def _rejected_current_duty_ids(vault_: vault.Vault, current_keys: set,
                               candidate_id: str) -> set:
    """Duty ids EXPLICITLY rejected among the current key set (drives the GAP branch).

    Rejected values are (correctly) invisible to
    :func:`_candidate_eligible_duty_values` (it only returns confirmed/corrected),
    so an explicit rejection is read here directly — read-only, no status mutation —
    and reported as a genuine GAP. Scoped to THIS candidate via a parameter-bound
    ``JOIN documents … WHERE candidate_id = ?`` so all three read paths agree (no
    cross-candidate rejection leak; WR-02).
    """
    cid = paths.safe_candidate_id(candidate_id)
    rows = vault_.con.execute(
        "SELECT ev.normalized_value_json FROM extracted_values ev "
        "JOIN documents d ON d.document_id = ev.document_id "
        "WHERE d.candidate_id = ? AND ev.factor_id = ? "
        "AND ev.confirmation_status = 'rejected'",
        (cid, _REVIEW_NOC_FACTOR_ID),
    ).fetchall()
    rejected: set = set()
    for r in rows:
        nv = json.loads(r["normalized_value_json"])
        key = (nv.get("duty_id"), nv.get("duty_sha"))
        if key in current_keys:
            rejected.add(nv.get("duty_id"))
    return rejected


def _layer2_fresh(db: "str", val) -> bool:
    """Layer 2 — corpus-drift re-check of ONE confirmed value (retrieve-what-you-cite).

    The 5-key ``is_stale`` (Layer 1) binds parser/claim/registry/file/render but NOT
    the corpus chunk, so a re-crawl that rewords a duty would pass Layer 1. Layer 2
    closes that gap (Pitfall 3 / threat T43-01): re-resolve EVERY stored citation
    fragment via the frozen :func:`crawler.searchindex.resolve` and re-verify that
    fragment's verbatim ``quote`` is still present in the live chunk via
    :func:`crawler.grounding.quote_is_grounded`. A value stays fresh ONLY if ALL of
    its ordered fragments still resolve AND ground — so a boundary-split duty
    (fragments in ``#002`` + ``#003``) is demoted the moment EITHER chunk drifts,
    and its full source item is re-covered in order. A resolve MISS (unknown id /
    chunk-sha drift -> ``None``) or any quote mismatch demotes the duty to
    unresolved. No score/overlap — a binary grounded/not-grounded check only.

    Back-compat: a legacy value carrying only a single ``citation`` + ``raw_text``
    (no ``citations`` list) is re-checked as one fragment against ``raw_text``.
    """
    nv = val.normalized_value or {}
    fragments = nv.get("citations")
    if not fragments:
        # Legacy single-citation shape: re-check raw_text against the one citation.
        citation = nv.get("citation")
        if not citation:
            return False
        fragments = [{"chunk_id": citation, "quote": val.raw_text or ""}]
    if not isinstance(fragments, list):
        return False
    for frag in fragments:
        if not isinstance(frag, dict):
            return False
        chunk_id = frag.get("chunk_id")
        quote = frag.get("quote")
        if not chunk_id or not quote:
            return False
        resolved = searchindex.resolve(db, chunk_id)
        if resolved is None:
            return False  # unknown id / chunk-sha drift -> fail-closed
        if not grounding.quote_is_grounded(quote, resolved["text"]):
            return False  # a fragment that no longer grounds -> demote
    return True


def review_noc_duties(
    vault_: vault.Vault,
    db: "str",
    noc_code: str,
    candidate_id: "str | None" = None,
    *,
    registry_snapshot: crs_rules.RegistrySnapshot | None = None,
    registry_fingerprint: str | None = None,
) -> dict:
    """Inert duty-review roll-up for *noc_code* — a closed PII-light never-green dict.

    STRUCTURALLY cannot green a duty review: ``status`` is one of
    ``{"AT-RISK", "GAP", "N/A"}`` and no branch returns ``"SUBSTANTIATED"``; there is
    no score / ``crs_points`` field. The terminal state on a fully-confirmed, fresh,
    current duty set (plus a confirmed lead statement) is ``("AT-RISK",
    "duty_review_manual")`` — STILL not green.

    A corpus-integrity fault is DISTINCT from "no worksheet" (WR-01): when the
    index resolves the NOC but its authoritative markdown SOURCE is
    missing/unreadable/drifted (:class:`crawler.noc_worksheet.NocSourceUnavailable`),
    this returns ``("AT-RISK", "noc_source_unavailable")`` with zero counts — a
    closed PII-light signal that is never green and never the clean ``("N/A",
    "no_worksheet")`` a genuinely duty-less NOC returns, so a downstream consumer
    can tell "source unavailable" from "no duties".

    Reads confirmed values ONLY through the dedicated inert ``review.noc`` factor
    (never ``core.work``) AND scoped to THIS candidate: *candidate_id* defaults to
    ``vault_.candidate_id`` (the per-candidate ``vault.sqlite`` invariant) but is
    threaded explicitly through every read (:func:`_candidate_eligible_duty_values`
    and :func:`_rejected_current_duty_ids`) so the eligible/rejected reads agree
    even in a shared / multi-candidate DB — no cross-candidate leak (WR-02). Layer 1
    is the shipped 5-key ``is_audit_eligible`` gate applied inside that read; a value
    then counts only if its parsed ``(duty_id, duty_sha)`` is in the CURRENT
    worksheet key set (each ``duty_id`` at most once). An old drifted value
    (superseded ``duty_sha``) or an orphaned key is ignored, so
    ``confirmed_count <= duty_count`` always.
    """
    injected_fingerprint = registry_fingerprint
    if registry_snapshot is not None:
        if (
            registry_fingerprint is not None
            and registry_fingerprint != registry_snapshot.fingerprint
        ):
            return _pack(
                noc_code,
                0,
                0,
                "AT-RISK",
                "registry_fingerprint_mismatch",
                [],
            )
        injected_fingerprint = registry_snapshot.fingerprint

    cid = vault_.candidate_id if candidate_id is None else candidate_id
    try:
        current = _current_key_sets(db, noc_code)
    except noc_worksheet.NocSourceUnavailable:
        # The section-aware INDEX resolved the NOC, but its AUTHORITATIVE markdown
        # SOURCE is missing / unreadable / drifted — a corpus-integrity fault, NOT
        # "no worksheet" (WR-01). Return a CLOSED PII-light AT-RISK verdict with a
        # DISTINCT, accurate reason (never N/A / no_worksheet, never green) so a
        # downstream consumer can tell "source unavailable" from "no duties".
        return _pack(noc_code, 0, 0, "AT-RISK",
                     noc_worksheet.NOC_SOURCE_UNAVAILABLE_REASON, [])
    if current is None:
        # No current worksheet (absent / drifted NOC) — nothing to review.
        return _pack(noc_code, 0, 0, "N/A", "no_worksheet", [])

    citations = current["citations"]
    if current["duty_count"] == 0:
        return _pack(noc_code, 0, 0, "N/A", "no_duties", citations)

    duty_keys = current["duty_keys"]
    lead_key = current["lead_key"]

    # Layer 1: the shipped 5-key quarantine gate (confirmed/corrected + quality ok +
    # not 5-key stale), scoped to review.noc AND to this candidate — so core.work is
    # never read and another candidate's confirmations never leak in.
    eligible = _candidate_eligible_duty_values(
        vault_,
        _REVIEW_NOC_FACTOR_ID,
        cid,
        registry_fingerprint=injected_fingerprint,
    )

    confirmed_duty_ids: set = set()
    lead_confirmed = False
    for val in eligible:
        nv = val.normalized_value or {}
        key = (nv.get("duty_id"), nv.get("duty_sha"))
        is_lead = key == lead_key
        is_duty = key in duty_keys
        # Current-key membership + per-duty_id collapse: only a value whose key is in
        # the live worksheet counts, and each duty_id contributes at most once, so an
        # old drifted value (superseded duty_sha) or an orphan key never inflates the
        # count.
        if not (is_lead or is_duty):
            continue
        # Layer 2: re-check corpus drift; a resolve miss / quote mismatch demotes the
        # duty to unresolved even though it passed Layer 1 + current-key membership.
        if not _layer2_fresh(db, val):
            continue
        if is_lead:
            lead_confirmed = True
        else:
            confirmed_duty_ids.add(key[0])

    confirmed_count = len(confirmed_duty_ids)
    duty_count = current["duty_count"]

    # An explicit rejection of a current duty is a genuine GAP.
    if _rejected_current_duty_ids(vault_, duty_keys | {lead_key}, cid):
        return _pack(noc_code, duty_count, confirmed_count,
                     "GAP", "unresolved_noc", citations)

    # Terminal cap (Pitfall 1): lead + every current duty confirmed+fresh -> STILL
    # AT-RISK, never green.
    if lead_confirmed and confirmed_count == duty_count and duty_count >= 1:
        return _pack(noc_code, duty_count, confirmed_count,
                     "AT-RISK", "duty_review_manual", citations)

    # None / partial / stale / drifted -> fail-closed unresolved.
    return _pack(noc_code, duty_count, confirmed_count,
                 "AT-RISK", "unresolved_noc", citations)
