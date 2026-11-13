"""Generic fail-closed CRS audit spine (Phase 32 core → Phase 33 fan-out).

Phase 32 shipped ``audit_factor`` as the single-factor vertical slice. Phase 33
generalizes it into a reusable DISPATCH SPINE that fans the SAME proven verdict
contract out across the whole CRS grid — WITHOUT changing the trust path:

* :func:`audit_one` — the shared loop for ONE factor: N/A short-circuit → frozen
  grounding gate (reused verbatim) → evidence quarantine → decider dispatch →
  factor-card assembly. It attaches the ``ev_`` evidence ids + corpus
  ``rule_citation_ids`` itself, so a decider never touches either id namespace.
* :func:`audit_factor` — the THIN Phase-32 back-compat shim: it resolves the
  reference date, calls :func:`audit_one` for the single factor, and wraps the one
  card in a :class:`PrivateAuditReport` exactly as before (preserving the whole
  ``test_auditor.py`` contract). ``AuditGroundingError`` still propagates.
* :func:`run_full_audit` — the full-grid orchestration: iterate
  ``auditors.FULL_GRID_FACTORS`` (ordering ``transfer.*`` LAST so ``prior_cards``
  holds decided core/spouse cards), sum the SUBSTANTIATED points into
  ``substantiated_total``, and compare it to the ITA round cutoff.

The loop order + fail-closed semantics are unchanged from Phase 32:

1. **N/A short-circuit** — before any gate/evidence read: ``spouse.*`` in
   no-spouse mode → N/A ``not_applicable``; an unclaimed non-derived factor → N/A
   ``not_claimed``.
2. **Grounding-by-construction gate** — the consumed grounded rows go through the
   SHIPPED ``crs_rules.validate_registry`` (frozen gate). ANY violation — or any
   consumed ``gap:true`` row — raises :class:`AuditGroundingError`; no verdict, no
   report.
3. **Evidence quarantine** — applicant values are read ONLY through
   ``vault.audit_eligible_values`` (confirmed/corrected + quality ok + not stale).
4. **Deterministic decider** — the registered decider reads every band / window /
   points figure from grounded rows via ``crawler.crs_audit``; this module carries
   NO inlined volatile threshold (a self-scan test asserts it).

Only a true grounding / system failure is an ERROR (``AuditGroundingError``);
GAP / AT-RISK / N/A are returned verdicts, never exceptions.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from crawler import auditors, crs_audit, crs_rules
from crawler import vault as vault_module
from crawler.models.audit import PrivateAuditReport, PrivateFactorCard
from crawler.models.crs_rules import Registry

# The pilot factor + the conversion factor whose rows ``to_clb`` consumes (kept
# for back-compat with any importer of the Phase-32 constants).
FIRST_LANGUAGE_FACTOR = "core.language.first"
CONVERSION_FACTOR = auditors.CONVERSION_FACTOR


class AuditGroundingError(RuntimeError):
    """Raised ONLY on a true grounding / system failure.

    An ungrounded consumed rule (fails the shipped gate) or a consumed
    ``gap:true`` coverage-gap row. This is the SOLE "error" surface — GAP /
    AT-RISK / N/A are returned verdicts, never exceptions. The message is
    PII-free (rule ids + reasons only).
    """


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _consumed_rows(registry: Registry, factor_id: str) -> Registry:
    """Select the grounded rows this factor consumes (its own + any extra ids)."""
    wanted = set(auditors.consumed_factor_ids(factor_id))
    rows = [row for row in registry.rows if wanted.intersection(row.factor_ids)]
    return Registry(rows=rows)


def gate_subset(subset: Registry, db) -> None:
    """Validate and re-retrieve every consumed row through the shared gate.

    The same strict Registry first crosses ``validate_registry`` and then
    ``retrieve_what_you_cite``.  This helper only orchestrates those shipped
    primitives; selector, citation, quote, and grounding semantics remain owned by
    ``crawler.crs_rules``.  Any violation, retrieval disagreement, abstention,
    ungrounded selection, or consumed ``gap:true`` row fails closed.
    """
    result = crs_rules.validate_registry(subset, db)
    if result["violations"]:
        ids = sorted({v["rule_id"] for v in result["violations"]})
        reasons = sorted({r for v in result["violations"] for r in v["reasons"]})
        raise AuditGroundingError(
            f"ungrounded rule row(s) {ids}: {reasons}")
    for row in subset.rows:
        if row.gap:
            raise AuditGroundingError(
                f"consumed rule row {row.rule_id!r} is an ungrounded coverage gap")
    retrieval = crs_rules.retrieve_what_you_cite(subset, db)
    refused: list[str] = []
    for row in subset.rows:
        if row.gap:
            continue
        item = retrieval.get(row.rule_id)
        if (item is None
                or not item.get("selected_chunk_id")
                or not item.get("agrees_with_citation")
                or not item.get("grounds")):
            refused.append(row.rule_id)
    refused.sort()
    if refused:
        raise AuditGroundingError(
            f"rule row retrieval refused for {refused}")


# Back-compat alias — ``audit_one``'s call site (auditor.py:207) and any importer
# resolve to the SAME object, so the frozen CRS grid stays byte-for-byte green.
_gate_or_raise = gate_subset


def _rule_citation_ids(subset: Registry) -> list[str]:
    """The distinct corpus citation ids behind the consumed rows (order-stable)."""
    ids: list[str] = []
    for row in subset.rows:
        for citation in row.citations:
            if citation.chunk_id not in ids:
                ids.append(citation.chunk_id)
    return ids


def _rule_citation_ids_for(subset: Registry, rule_ids) -> list[str]:
    """The distinct citation ids of ONLY the named consumed rows (order-stable).

    Reason-aware citation scoping (WR-02): when a decider names the specific
    consumed rows its verdict derives from (``DecisionResult.rule_ids``), the card
    surfaces ONLY those rows' citations — so a verdict on a SHARED factor does not
    over-cite the sibling rows it did not derive from (e.g. a non-physician
    job-offer card must not surface the physician-NOC citations). The rows are
    taken from the ALREADY-GATED consumed *subset* (never re-selected or
    re-grounded), so this narrows surfacing WITHOUT weakening the fail-closed
    grounding gate that already validated the ENTIRE subset. An unknown / mistyped
    rule id simply matches no row (safely empty — the established fail-closed
    convention), never an error. Iteration follows ``subset.rows`` order so the id
    order stays stable and consistent with :func:`_rule_citation_ids`.
    """
    wanted = set(rule_ids)
    ids: list[str] = []
    for row in subset.rows:
        if row.rule_id not in wanted:
            continue
        for citation in row.citations:
            if citation.chunk_id not in ids:
                ids.append(citation.chunk_id)
    return ids


def _claimed_threshold(factor) -> int | None:
    """Parse the claimed benchmark level from the profile factor (level or value)."""
    if factor is None:
        return None
    for candidate in (factor.claimed_level, factor.claimed_value):
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _ita_date(vault, ita_round_id: str | None) -> str | None:
    """The ITA round date (ISO ``YYYY-MM-DD``), or None when no round is set."""
    if ita_round_id:
        row = vault.con.execute(
            "SELECT round_date FROM ita_rounds "
            "WHERE round_id = ? AND candidate_id = ?",
            (ita_round_id, vault.candidate_id),
        ).fetchone()
        if row is not None and row["round_date"]:
            return str(row["round_date"])[:10]
    return None


def _reference_date(vault, ita_round_id: str | None) -> str:
    """The freshness reference: the ITA round date if present, else the run date."""
    ita = _ita_date(vault, ita_round_id)
    return ita if ita is not None else date.today().isoformat()


def _cutoff_score(vault, ita_round_id: str | None):
    """The grounded ITA round cutoff score, or None when unavailable."""
    if ita_round_id:
        row = vault.con.execute(
            "SELECT cutoff_score FROM ita_rounds "
            "WHERE round_id = ? AND candidate_id = ?",
            (ita_round_id, vault.candidate_id),
        ).fetchone()
        if row is not None and row["cutoff_score"] is not None:
            return row["cutoff_score"]
    return None


def _latest_ita_round_id(vault) -> str | None:
    """The most recently entered ITA round id in the vault, or None.

    Lets ``vault audit --all`` surface the substantiated-total-vs-cutoff comparison
    (AUDIT-05) without the user having to know an internal round id.
    """
    row = vault.con.execute(
        "SELECT round_id FROM ita_rounds WHERE candidate_id = ? "
        "ORDER BY created_at DESC, round_id DESC LIMIT 1",
        (vault.candidate_id,),
    ).fetchone()
    return row["round_id"] if row is not None else None


def _effective_ita_round_id(vault, requested_round_id: str | None) -> str:
    """Resolve one candidate-owned round id, failing closed when unavailable."""
    if requested_round_id is not None:
        row = vault.con.execute(
            "SELECT round_id FROM ita_rounds "
            "WHERE round_id = ? AND candidate_id = ?",
            (requested_round_id, vault.candidate_id),
        ).fetchone()
        if row is None:
            raise AuditGroundingError("ITA round is unavailable for candidate")
        return row["round_id"]
    latest_round_id = _latest_ita_round_id(vault)
    if latest_round_id is None:
        raise AuditGroundingError("ITA round is required for full audit")
    return latest_round_id


class ProvenancedPrivateAuditReport(PrivateAuditReport):
    """Full-grid private report bound to the exact ITA round it evaluated."""

    ita_round_id: str


def _evidence_id_for(vault, document_id: str) -> str | None:
    """The private ``ev_`` evidence id for a value's backing document."""
    row = vault.con.execute(
        "SELECT evidence_id FROM documents WHERE document_id = ?",
        (document_id,)
    ).fetchone()
    return row["evidence_id"] if row is not None else None


def _na_card(factor_id: str, group, reason: str) -> PrivateFactorCard:
    """A closed-vocabulary N/A card (before any gate or evidence read)."""
    return PrivateFactorCard(
        factor_id=factor_id,
        factor_group=group,
        verdict="N/A",
        reason_code=reason,
    )


def _verified_registry_fingerprint(
    registry: Registry,
    claimed_fingerprint: str | None,
) -> str:
    """Bind an audit entry to the exact supplied Registry, or fail closed."""
    supplied_fingerprint = crs_rules.registry_fingerprint(registry)
    if (
        claimed_fingerprint is not None
        and claimed_fingerprint != supplied_fingerprint
    ):
        raise AuditGroundingError(
            "supplied registry fingerprint does not match registry"
        )
    return supplied_fingerprint


# --------------------------------------------------------------------------- #
# audit_one — the shared per-factor loop (reused by both entry points).
# --------------------------------------------------------------------------- #
def _audit_one_verified(vault, factor_id: str, db, registry: Registry, *,
                        spouse_mode: bool, reference_date: str,
                        prior_cards: dict[str, PrivateFactorCard],
                        registry_fingerprint: str,
                        ita_date: str | None = None,
                        profile_factors: dict | None = None) -> PrivateFactorCard:
    """Run the fail-closed loop for ONE factor and return its PrivateFactorCard.

    Raises :class:`AuditGroundingError` — and returns NO card — only on a true
    grounding failure (a consumed ungrounded / ``gap:true`` row). GAP / AT-RISK /
    N/A are valid returned verdicts.
    """
    if profile_factors is None:
        profile_factors = {
            f.factor_id: f for f in vault_module.load_profile_factors(vault)}
    factor = profile_factors.get(factor_id)
    group = auditors.FACTOR_GROUP.get(factor_id)

    # 1a. spouse.* in no-spouse mode -> N/A (before any gate or evidence read).
    if factor_id.startswith("spouse.") and not spouse_mode:
        return _na_card(factor_id, group, "not_applicable")
    # 1b. Unclaimed, non-derived factor -> N/A (before any gate or evidence read).
    if factor is None and not auditors.is_derived(factor_id):
        return _na_card(factor_id, group, "not_claimed")

    # 2. Grounding-by-construction gate BEFORE any evidence read or verdict.
    # The ENTIRE consumed subset is gated here (fail-closed); reason-aware
    # citation scoping below narrows only what the card SURFACES, never the gate.
    subset = _consumed_rows(registry, factor_id)
    _gate_or_raise(subset, db)

    # 3. Evidence quarantine: ONLY audit-eligible values.
    eligible = vault_module.audit_eligible_values(
        vault, factor_id, registry_fingerprint=registry_fingerprint)
    by_field: dict = {}
    evidence_ids: list[str] = []
    for value in eligible:
        by_field[value.field_name] = value
        eid = _evidence_id_for(vault, value.document_id)
        if eid and eid not in evidence_ids:
            evidence_ids.append(eid)

    # 4. Dispatch to the registered decider.
    ctx = auditors.DecisionContext(
        factor_id=factor_id, factor=factor, by_field=by_field,
        registry=registry, consumed=subset, spouse_mode=spouse_mode,
        reference_date=reference_date, ita_date=ita_date, prior_cards=prior_cards,
        eligible_values=tuple(eligible))
    decider = auditors.resolve(factor_id)
    result = decider(ctx)

    # Reason-aware citation attachment (WR-02): a decider may name the specific
    # consumed rows its verdict derives from (``result.rule_ids``) so the card does
    # not over-cite sibling rows on a SHARED factor. Empty / None (the default for
    # every other factor) → the historical UNION of the whole gated subset
    # (byte-identical behavior). A NON-EMPTY selection → only those rows' citations
    # (an unknown id matches no row → safely empty). The subset was already gated
    # in full above, so this only narrows what the card surfaces — never the gate.
    if result.rule_ids:
        rule_citation_ids = _rule_citation_ids_for(subset, result.rule_ids)
    else:
        rule_citation_ids = _rule_citation_ids(subset)

    # 5. Assemble the card (spine attaches evidence ids, citations, score delta).
    claimed_value = result.claimed_value
    if claimed_value is None and factor is not None:
        claimed_value = _claimed_threshold(factor)
    substantiated_points = result.substantiated_points
    score_delta = None
    if (factor is not None and factor.claimed_points is not None
            and substantiated_points is not None):
        score_delta = factor.claimed_points - substantiated_points

    # COV-02: flag a SUBSTANTIATED card that could not be priced from a grounded
    # row as an explicit unresolved item — the visible signal that the truthful-
    # but-incomplete 0-contribution below is a gap, not a real 0. This flags BOTH
    # the single-factor (audit_factor/run_audit) and full-grid (run_full_audit)
    # paths from one place; the roll-up's ``(points or 0)`` coalesce stays a
    # truthful 0 contribution (the total is never inflated to hide the gap).
    points_unresolved = (
        result.verdict == "SUBSTANTIATED" and substantiated_points is None)

    return PrivateFactorCard(
        factor_id=factor_id,
        factor_group=group,
        verdict=result.verdict,
        claimed_value=claimed_value,
        confirmed_value=result.confirmed_value,
        substantiated_points=substantiated_points,
        score_delta=score_delta,
        evidence_ids=sorted(evidence_ids),
        rule_citation_ids=rule_citation_ids,
        reason_code=result.reason_code,
        points_unresolved=points_unresolved,
    )


def audit_one(vault, factor_id: str, db, registry: Registry, *,
              spouse_mode: bool, reference_date: str,
              prior_cards: dict[str, PrivateFactorCard],
              registry_fingerprint: str | None = None,
              ita_date: str | None = None,
              profile_factors: dict | None = None) -> PrivateFactorCard:
    """Audit one factor against one verified caller-supplied registry snapshot."""
    supplied_fingerprint = _verified_registry_fingerprint(
        registry, registry_fingerprint)
    return _audit_one_verified(
        vault, factor_id, db, registry, spouse_mode=spouse_mode,
        reference_date=reference_date, prior_cards=prior_cards,
        registry_fingerprint=supplied_fingerprint, ita_date=ita_date,
        profile_factors=profile_factors)


# --------------------------------------------------------------------------- #
# audit_factor — the THIN Phase-32 back-compat shim (one factor, one report).
# --------------------------------------------------------------------------- #
def audit_factor(vault, factor_id: str, db, registry: Registry, *,
                 ita_round_id: str | None = None,
                 spouse_mode: bool = False,
                 registry_fingerprint: str | None = None) -> PrivateAuditReport:
    """Audit one factor against one verified caller-supplied registry snapshot."""
    supplied_fingerprint = _verified_registry_fingerprint(
        registry, registry_fingerprint)
    effective_round_id = (
        _effective_ita_round_id(vault, ita_round_id)
        if ita_round_id is not None
        else None
    )
    return _audit_factor_verified(
        vault, factor_id, db, registry, ita_round_id=effective_round_id,
        spouse_mode=spouse_mode, registry_fingerprint=supplied_fingerprint)


def _audit_factor_verified(vault, factor_id: str, db, registry: Registry, *,
                           ita_round_id: str | None = None,
                           spouse_mode: bool = False,
                           registry_fingerprint: str) -> PrivateAuditReport:
    """Run the fail-closed verdict loop for ``factor_id`` and return a report.

    Returns a :class:`PrivateAuditReport` with exactly one
    :class:`PrivateFactorCard`. Raises :class:`AuditGroundingError` — and returns
    NO report — only on a true grounding / system failure (SC5). GAP / AT-RISK /
    N/A are valid returned verdicts.
    """
    auditors.load_all()
    candidate_id = vault.candidate_id
    run_id = vault_module.new_audit_run_id()
    created_at = _now()
    reference_date = _reference_date(vault, ita_round_id)
    ita_date = _ita_date(vault, ita_round_id)

    card = _audit_one_verified(
        vault, factor_id, db, registry, spouse_mode=spouse_mode,
        reference_date=reference_date, prior_cards={},
        registry_fingerprint=registry_fingerprint, ita_date=ita_date)

    return PrivateAuditReport(
        run_id=run_id, candidate_id=candidate_id, created_at=created_at,
        factor_cards=[card], substantiated_total=card.substantiated_points,
        registry_fingerprint=registry_fingerprint)


# --------------------------------------------------------------------------- #
# run_full_audit — the full-grid orchestration (one card per factor + cutoff).
# --------------------------------------------------------------------------- #
def run_full_audit(vault, db, registry: Registry, *,
                   ita_round_id: str | None = None,
                   spouse_mode: bool | None = None,
                   registry_fingerprint: str | None = None) -> PrivateAuditReport:
    """Audit the full grid against one verified caller-supplied registry snapshot."""
    supplied_fingerprint = _verified_registry_fingerprint(
        registry, registry_fingerprint)
    # Direct, non-persisting audits retain their historical no-round behaviour.
    # An explicit id is nevertheless candidate-bound before entering the grid.
    effective_round_id = (
        _latest_ita_round_id(vault)
        if ita_round_id is None
        else _effective_ita_round_id(vault, ita_round_id)
    )
    return _run_full_audit_verified(
        vault, db, registry, ita_round_id=effective_round_id,
        spouse_mode=spouse_mode, registry_fingerprint=supplied_fingerprint)


def _run_full_audit_verified(vault, db, registry: Registry, *,
                             ita_round_id: str | None,
                             spouse_mode: bool | None = None,
                             registry_fingerprint: str) -> PrivateAuditReport:
    """Audit every factor on the grid; roll SUBSTANTIATED points up vs the cutoff.

    Iterates ``auditors.FULL_GRID_FACTORS`` ordering all ``transfer.*`` factors
    LAST so ``prior_cards`` holds the decided core/spouse cards a transferability
    decider recombines. ``substantiated_total`` sums the SUBSTANTIATED cards'
    points; when an ITA round with a cutoff is set, ``cutoff_delta`` +
    ``meets_cutoff`` are populated from ``crs_audit.compare_to_cutoff`` (a pure
    arithmetic delta — no legal advice). A single :class:`AuditGroundingError`
    from any factor propagates and writes nothing (the report writer preserves the
    SC5 fail-closed ordering).
    """
    auditors.load_all()
    candidate_id = vault.candidate_id
    run_id = vault_module.new_audit_run_id()
    created_at = _now()

    profile_factors = {
        f.factor_id: f for f in vault_module.load_profile_factors(vault)}
    if spouse_mode is None:
        spouse_mode = auditors.spouse.determine_spouse_mode(
            vault, list(profile_factors.values()))
    reference_date = _reference_date(vault, ita_round_id)
    ita_date = _ita_date(vault, ita_round_id)

    # Order transfer.* LAST (stable within each bucket) so prior_cards is populated.
    ordered = sorted(
        auditors.FULL_GRID_FACTORS,
        key=lambda fid: 1 if fid.startswith("transfer.") else 0)

    prior_cards: dict[str, PrivateFactorCard] = {}
    cards: list[PrivateFactorCard] = []
    for factor_id in ordered:
        card = _audit_one_verified(
            vault, factor_id, db, registry, spouse_mode=spouse_mode,
            reference_date=reference_date, prior_cards=prior_cards,
            registry_fingerprint=registry_fingerprint,
            ita_date=ita_date, profile_factors=profile_factors)
        prior_cards[factor_id] = card
        cards.append(card)

    substantiated_total = sum(
        (c.substantiated_points or 0)
        for c in cards if c.verdict == "SUBSTANTIATED")

    report_data = {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "created_at": created_at,
        "factor_cards": cards,
        "substantiated_total": substantiated_total,
        "registry_fingerprint": registry_fingerprint,
    }
    report = (
        ProvenancedPrivateAuditReport(
            **report_data, ita_round_id=ita_round_id)
        if ita_round_id is not None
        else PrivateAuditReport(**report_data)
    )

    cutoff = _cutoff_score(vault, ita_round_id)
    if cutoff is not None:
        comparison = crs_audit.compare_to_cutoff(
            substantiated_total, {"cutoff": cutoff}, registry)
        report.cutoff_delta = comparison["delta"]
        report.meets_cutoff = comparison["meets_cutoff"]

    return report
