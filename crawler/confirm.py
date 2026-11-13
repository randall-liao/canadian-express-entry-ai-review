"""Field-level confirm/correct/reject orchestration + confirmation view (Phase 30 — Plan 03).

This is the machine/human PII split for the "confirm what I read" checkpoint:

* :func:`build_field_view` returns the FULL, PII-bearing view an applicant sees
  on the local terminal (stderr) — the five EXTRACT-03 facets (raw value,
  normalized value, source page/crop, affected CRS factor, and the profile claim
  it substantiates) plus status / quality / staleness / audit-eligibility.
* :func:`build_field_view_summary` returns the PII-LIGHT projection that is safe
  for the ``--json`` machine envelope (ids / field name / status / quality /
  factor id / stale / audit_eligible ONLY).
* :func:`apply_decision` applies EXACTLY ONE confirm/correct/reject to ONE value
  (the rubber-stamp defense is structural — no bulk "confirm all").

Imports only :mod:`crawler.vault` (lean, pydantic-only) — never
:mod:`crawler.extraction` — so it loads without the extraction deps.
"""

from __future__ import annotations

import json

from crawler import vault

_VALID_DECISIONS = ("confirm", "correct", "reject")


def build_field_view(
    v: vault.Vault,
    value_id: str,
    *,
    registry_fingerprint: str | None = None,
) -> dict:
    """Return the FULL (PII-bearing) confirmation view for one value.

    Joins the extracted value to its page (page_number, vault-relative
    image_relpath, bbox) and its linked CRS factor (factor_group + the claim:
    claimed_level / claimed_points / claimed_value). Raises :class:`VaultError`
    (field/type only) for an unknown value id.
    """
    val = vault.get_extracted_value(v, value_id)
    if val is None:
        raise vault.VaultError("unknown value_id")

    page_number = None
    image_relpath = None
    if val.page_id is not None:
        prow = v.con.execute(
            "SELECT page_number, image_relpath FROM document_pages "
            "WHERE page_id = ?", (val.page_id,)).fetchone()
        if prow is not None:
            page_number = prow["page_number"]
            image_relpath = prow["image_relpath"]

    factor_group = None
    claimed_level = None
    claimed_points = None
    claimed_value = None
    if val.factor_id is not None:
        frow = v.con.execute(
            "SELECT factor_group, claimed_level, claimed_points, "
            "claimed_value_json FROM crs_profile_factors WHERE factor_id = ?",
            (val.factor_id,)).fetchone()
        if frow is not None:
            factor_group = frow["factor_group"]
            claimed_level = frow["claimed_level"]
            claimed_points = frow["claimed_points"]
            claimed_value = json.loads(frow["claimed_value_json"])

    return {
        "value_id": val.value_id,
        "field_name": val.field_name,
        "confirmation_status": val.confirmation_status,
        "quality_flag": val.quality_flag,
        "stale": vault.is_stale(
            v, value_id, registry_fingerprint=registry_fingerprint),
        "audit_eligible": vault.is_audit_eligible(
            v, value_id, registry_fingerprint=registry_fingerprint),
        # (1) raw value + (2) normalized value
        "raw_value": val.raw_text,
        "normalized_value": val.normalized_value,
        "confirmed_value": val.confirmed_value,
        # (3) source page / crop
        "page_number": page_number,
        "image_relpath": image_relpath,
        "bbox": val.bbox,
        # (4) affected CRS factor
        "factor_id": val.factor_id,
        "factor_group": factor_group,
        # (5) the profile claim it substantiates
        "claimed_level": claimed_level,
        "claimed_points": claimed_points,
        "claimed_value": claimed_value,
    }


def build_field_view_summary(
    v: vault.Vault,
    value_id: str,
    *,
    registry_fingerprint: str | None = None,
) -> dict:
    """Return the PII-LIGHT projection for the ``--json`` envelope.

    Shape matches :class:`crawler.models.vault.ExtractedValueSummary` plus the
    derived ``audit_eligible`` flag — NEVER a raw/normalized value, bbox, path,
    or original filename.
    """
    val = vault.get_extracted_value(v, value_id)
    if val is None:
        raise vault.VaultError("unknown value_id")
    return {
        "value_id": val.value_id,
        "field_name": val.field_name,
        "confirmation_status": val.confirmation_status,
        "quality_flag": val.quality_flag,
        "factor_id": val.factor_id,
        "stale": vault.is_stale(
            v, value_id, registry_fingerprint=registry_fingerprint),
        "audit_eligible": vault.is_audit_eligible(
            v, value_id, registry_fingerprint=registry_fingerprint),
    }


def list_field_views(v: vault.Vault, document_id: "str | None" = None,
                     status: "str | None" = None) -> list[dict]:
    """Return ordered PII-light summaries for ``vault fields``."""
    registry_fingerprint = vault.live_registry_fingerprint()
    return [build_field_view_summary(
                v, val.value_id, registry_fingerprint=registry_fingerprint)
            for val in vault.list_extracted_values(v, document_id=document_id,
                                                   status=status)]


def apply_decision(v: vault.Vault, value_id: str, decision: str,
                   corrected_value=None, confirmed_by: "str | None" = None,
                   *, registry_fingerprint: "str | None" = None) -> dict:
    """Apply ONE field-level decision to ONE value; return its refreshed summary.

    Validates ``decision ∈ {confirm, correct, reject}`` and requires
    ``corrected_value`` when correcting (VaultError, field/type only). Delegates
    to :func:`crawler.vault.confirm_value` for exactly this value — it never
    mutates any other value (the rubber-stamp defense is structural).
    """
    if decision not in _VALID_DECISIONS:
        raise vault.VaultError("decision must be confirm | correct | reject")
    if decision == "correct" and corrected_value is None:
        raise vault.VaultError("correct requires a corrected_value")
    if vault.get_extracted_value(v, value_id) is None:
        raise vault.VaultError("unknown value_id")
    vault.confirm_value(v, value_id, decision, corrected_value=corrected_value,
                        confirmed_by=confirmed_by,
                        registry_fingerprint=registry_fingerprint)
    return build_field_view_summary(
        v, value_id, registry_fingerprint=registry_fingerprint)


def format_field_view_human(view: dict) -> str:
    """Render a FULL field view as a multi-line human block (for stderr ONLY).

    This is the PII-rich detail the applicant reviews on their local terminal;
    it must NEVER be written to the ``--json`` machine envelope, ``corpus/``, or
    any tracked file.
    """
    eligible = "yes" if view["audit_eligible"] else "no"
    stale = "STALE" if view["stale"] else "fresh"
    lines = [
        f"● {view['field_name']}  [{view['value_id']}]",
        f"    status:       {view['confirmation_status']}  "
        f"(quality={view['quality_flag']}, {stale}, audit_eligible={eligible})",
        f"    raw value:    {view['raw_value']!r}",
        f"    normalized:   {view['normalized_value']!r}",
    ]
    if view["confirmed_value"] is not None:
        lines.append(f"    confirmed:    {view['confirmed_value']!r}")
    lines.append(
        f"    source:       page {view['page_number']} "
        f"[{view['image_relpath']}] bbox={view['bbox']}")
    lines.append(
        f"    CRS factor:   {view['factor_id']} ({view['factor_group']})")
    lines.append(
        f"    profile claim: level={view['claimed_level']} "
        f"points={view['claimed_points']} value={view['claimed_value']!r}")
    return "\n".join(lines)
