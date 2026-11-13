"""Inert offer-for-program-eligibility sidecar (Phase 42 — 42-03, POLICY-03).

This module STRUCTURALLY separates "a valid job offer for program eligibility"
from "arranged-employment CRS additional points". It exposes a single pure
function, :func:`offer_for_program_eligibility`, that reports a claimed job offer
as an ``AT-RISK`` / ``N/A`` program-eligibility input with a CONSTANT ``crs_points``
of ``0`` — there is no branch that can ever set it non-zero, and the status is
NEVER ``SUBSTANTIATED``.

Inert-by-construction (POLICY-03):
  * NOT wired into the ``crawler.auditors`` dispatch — it is not a CRS decider and
    is never added to that lookup table at all;
  * NOT part of the canonical auditable factor grid and NOT summed into any
    ``PublicAuditEnvelope`` — it never contributes to a CRS total;
  * NO Phase-45 / MEC wiring here — the sidecar is shipped and unit-tested only.
    Phase 45 (the Minimum Entry Criteria integrator) consumes it LATER as an
    ``AT-RISK`` human-confirmed program-eligibility input (FST offer/certificate,
    FSW funds exemption), never as an automatic points award.

PII-light: the returned dict carries ONLY public / derived fields — no evidence
(``ev_``) id, no filesystem path, and no applicant value. The citation is reused
from the already-grounded ``additional.job_offer.current`` grounded rule row rather
than adding any new grounded surface.

stdlib-only; no CRS threshold literal lives here (the bare ``0`` is not a volatile
points value, so the aggregate no-inlined gate stays clean).
"""

from __future__ import annotations

# The closed, public field set the sidecar returns. Kept as a module constant so
# the PII-light contract is asserted structurally (no ev_ id / path / applicant
# value ever leaks) by the 42-03 test sweep.
PUBLIC_FIELDS: tuple[str, ...] = (
    "offer_present",
    "eligibility_status",
    "crs_points",
    "for_program_eligibility_only",
    "reason",
    "citation",
)


def offer_for_program_eligibility(claim_points, ita_date, registry) -> dict:
    """Expose a claimed job offer as an ``AT-RISK`` program-eligibility input.

    STRUCTURALLY cannot award CRS points: ``crs_points`` is a CONSTANT ``0`` and no
    branch assigns it otherwise; ``eligibility_status`` is ``AT-RISK`` (a claim is
    present) or ``N/A`` (no claim) and is NEVER ``SUBSTANTIATED``.

    This is a screening input for the Phase-45 MEC integrator, kept entirely
    separate from the frozen ``crs_audit.arranged_employment_guard`` CRS-additional
    -points path. It is not wired into the auditors dispatch and never summed into
    the audit envelope.

    Args:
        claim_points: The claimed job-offer value; only its truthiness is read
            (``present = bool(claim_points)``) — the value itself is never awarded.
        ita_date: Reserved for the Phase-45 MEC contract signature; the inert
            sidecar does not branch on it (no window math is re-added here).
        registry: The grounded rule registry; the sidecar reuses the already-
            grounded ``additional.job_offer.current`` citation rather than adding a
            new grounded surface.

    Returns:
        A PII-light dict over the closed :data:`PUBLIC_FIELDS` set.
    """
    present = bool(claim_points)
    current = next(
        (r for r in registry.rows if r.rule_id == "additional.job_offer.current"),
        None,
    )
    return {
        "offer_present": present,
        "eligibility_status": "AT-RISK" if present else "N/A",  # NEVER SUBSTANTIATED
        "crs_points": 0,  # CONSTANT — no branch reassigns it, never an award
        "for_program_eligibility_only": True,
        "reason": "offer_for_eligibility_manual",
        "citation": current.citations[0].chunk_id if current else None,
    }
