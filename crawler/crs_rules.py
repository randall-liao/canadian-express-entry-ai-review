"""The PII-free CRS rule-registry ENGINE (Phase 31 — RULE-01/02/03).

This module is the *interface-first* foundation of Phase 31: it defines how a
grounded CRS rule row is loaded, validated through the SHIPPED grounding gate,
re-checked with retrieve-what-you-cite, and reported for full-grid coverage — and
the static "no inlined volatile rule" gate. It authors NO trust path of its own:
it is a pure CONSUMER of the frozen v3.x primitives —
:func:`crawler.grounding.check_answer` (the gate) and
:func:`crawler.searchindex.search` / :func:`crawler.searchindex.resolve` (the
resolver). Forking any of those would silently widen the grounding guarantee, so
this engine calls them verbatim (grep-asserted by the conformance tests).

The registry itself is PUBLIC and PII-FREE: it models only corpus authority (see
:mod:`crawler.models.crs_rules`). Nothing here reads the git-ignored candidate
vault; a rule row carries no applicant field.

Public surface:
  * :func:`load_registry`               — read + validate the ``*.yaml`` registry
  * :func:`row_to_answer`               — a rule row → grounding-gate answer object
  * :func:`validate_registry`           — gate every non-gap row (fail-closed)
  * :func:`retrieve_what_you_cite`      — re-select the cited chunk from query+selector
  * :func:`coverage_report`             — full four-group required-grid coverage
  * :func:`no_inlined_volatile_rules`   — static gate over prose / Python literals
  * :data:`REQUIRED_RULE_IDS`           — the authoritative full-grid manifest
"""

from __future__ import annotations

import ast
import hashlib
import io
import re
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

from crawler import grounding, searchindex
from crawler.models.crs_rules import Registry, RuleRow

# The public registry lives here; ``load_registry`` reads every ``*.yaml`` except
# ``_``-prefixed scratch files (COVERAGE.md is ``.md`` and never matches ``*.yaml``).
DEFAULT_DATA_DIR = "crawler/data/crs_rules"

# How many BM25 hits retrieve-what-you-cite inspects before abstaining. Mirrors the
# v3.1 document-agent selection budget (short query + non-volatile marker).
_SEARCH_LIMIT = 8

# --------------------------------------------------------------------------- #
# REQUIRED_RULE_IDS — the authoritative full-grid manifest (RULE-03).
#
# For each public rule domain, the set of required rule-id LABELS (dotted
# structural stems) that MUST be covered for the CRS grid to be complete. These
# are STRUCTURAL IDs ONLY (never volatile thresholds), derived from the
# SUMMARY-v4.0 Per-Factor CRS Feature Map. A rule row "covers" a label when the
# label's dotted components are a prefix of the row's rule_id components (so
# ``core.language.first.approved_test`` covers ``core.language.first``).
# --------------------------------------------------------------------------- #
REQUIRED_MEC_RULE_IDS: dict[str, tuple[str, ...]] = {
    "fsw": (
        "fsw.work.primary_noc",
        "fsw.work.teer",
        "fsw.work.paid",
        "fsw.work.recency",
        "fsw.work.continuity_duration_hours",
        "fsw.work.noc_duties",
        "fsw.language.first",
        "fsw.education.minimum",
        "fsw.grid.language",
        "fsw.grid.education",
        "fsw.grid.experience",
        "fsw.grid.age",
        "fsw.grid.arranged_employment",
        "fsw.grid.adaptability",
        "fsw.grid.pass_mark",
        "fsw.funds.requirement",
        "fsw.destination.outside_quebec",
    ),
    "fst": (
        "fst.work.trade_noc",
        "fst.work.same_noc",
        "fst.work.paid",
        "fst.work.qualified_to_practise",
        "fst.work.student_exclusion",
        "fst.work.recency_duration_hours",
        "fst.work.noc_duties_requirements",
        "fst.language.minimum",
        "fst.offer_or_certificate",
        "fst.funds.requirement",
        "fst.destination.outside_quebec",
    ),
    "cec": (
        "cec.work.teer",
        "cec.work.in_canada",
        "cec.work.authorized_tr_status",
        "cec.work.paid",
        "cec.work.recency_duration_hours",
        "cec.work.student_exclusion",
        "cec.work.self_employment_exclusion",
        "cec.work.noc_duties",
        "cec.language.minimum",
        "cec.destination.outside_quebec",
    ),
}

_MEC_REQUIRED_FLAT = tuple(
    rule_id
    for program in ("fsw", "fst", "cec")
    for rule_id in REQUIRED_MEC_RULE_IDS[program]
)

REQUIRED_RULE_IDS: dict[str, tuple[str, ...]] = {
    "core_human_capital": (
        "core.age",                 # age-on-ITA + spouse/no-spouse age table
        "core.education",           # credential admissibility + ECA 5y validity
        "core.language.first",      # accepted first-official-language test + validity
        "core.language.conversion", # CLB/NCLC raw-score conversion rows
        "core.language.second",     # second official language
        "core.work",                # Canadian work definition (TEER 0-3, 30h, 10y)
    ),
    "spouse_common_law": (
        "spouse.education",         # spouse education (owner-must-be-spouse)
        "spouse.language",          # spouse language (per-ability cap 20)
        "spouse.work",              # spouse Canadian work
    ),
    "skill_transferability": (
        "transfer.education_language",     # education × first official language
        "transfer.education_work",         # education × Canadian work
        "transfer.foreign_language",       # foreign work × first official language
        "transfer.foreign_work",           # foreign work × Canadian work
        "transfer.certificate_language",   # certificate of qualification × language
        "transfer.cap.education",          # education-combination cap (50)
        "transfer.cap.foreign_work",       # foreign-work-combination cap (50)
        "transfer.cap.total",              # total transferability cap (100)
    ),
    "additional_points": (
        "additional.nomination",        # provincial/territorial nomination (600)
        "additional.job_offer.current", # arranged-employment repeal (0 as of 2025-03-25)
        "additional.job_offer.legacy",  # distinct ITA-era legacy row (grounded or gap)
        "additional.job_offer.physician", # physician public-policy edge-case row (grounded, AT-RISK/manual)
        "additional.study",             # Canadian post-secondary study (15/30)
        "additional.french",            # strong French (25/50)
        "additional.sibling",           # sibling in Canada (15)
    ),
    "program_eligibility": _MEC_REQUIRED_FLAT,
}

# These rows are intentionally outside the scored CRS grid, but are still
# load-bearing trust inputs.  Study review requires both the current DLI
# designation rule and the R73 definition; neither is covered by
# ``REQUIRED_RULE_IDS`` because neither is a scored factor.  Keep this manifest
# exact rather than requiring every future auxiliary row added to the registry.
REQUIRED_AUXILIARY_RULE_IDS: tuple[str, ...] = (
    "study.dli.designation",
    "study.r73_definition",
)


# --------------------------------------------------------------------------- #
# load_registry — read + typed-validate the public YAML registry (fail-closed).
# --------------------------------------------------------------------------- #
class RegistryUnavailable(RuntimeError):
    """Stable, path-free failure for an unusable live rule registry."""


@dataclass(frozen=True, init=False)
class RegistrySnapshot:
    """Deeply isolated registry bytes and their matching content fingerprint.

    ``Registry`` and its nested Pydantic rows contain mutable lists for broad
    compatibility with existing callers.  The snapshot therefore retains only a
    canonical serialized copy and returns a fresh validated view on access.
    Mutating either the constructor input or a previously returned view cannot
    alter later reads or silently detach snapshot semantics from the fingerprint.
    """

    _registry_json: str
    fingerprint: str

    def __init__(self, registry: Registry, fingerprint: str | None = None) -> None:
        isolated = Registry.model_validate(registry.model_dump(mode="json"))
        computed = registry_fingerprint(isolated)
        if fingerprint is not None and fingerprint != computed:
            raise ValueError("registry snapshot fingerprint does not match content")
        object.__setattr__(self, "_registry_json", isolated.model_dump_json())
        object.__setattr__(self, "fingerprint", computed)

    @property
    def registry(self) -> Registry:
        """Return an independent validated, mutable-compatible registry view."""
        return Registry.model_validate_json(self._registry_json)


def load_registry(data_dir: str | Path = DEFAULT_DATA_DIR) -> Registry:
    """Read every ``*.yaml`` under *data_dir*, validate each row, return a Registry.

    Skips ``_``-prefixed scratch files (COVERAGE.md is ``.md`` and never matches
    ``*.yaml``). Each row is validated into a :class:`RuleRow` — a malformed row
    raises loudly (pydantic ``ValidationError`` / ``ValueError``), never persists
    as a partial (T-31-02, fail-closed). Files are read in sorted order so the
    resulting registry is deterministic.
    """
    root = Path(data_dir)
    rows: list[RuleRow] = []
    if root.is_dir():
        for path in sorted(root.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError(
                    f"{path}: top-level YAML must be a mapping with a 'rows' list"
                )
            for raw in data.get("rows", []) or []:
                rows.append(RuleRow.model_validate(raw))
    # Registry's validator rejects duplicate rule_ids across ALL files (fail-closed).
    return Registry(rows=rows)


def registry_fingerprint(registry: Registry) -> str:
    """A deterministic content fingerprint of a loaded registry (sha256 hex).

    Hashes the registry's canonical JSON (pydantic serialization is stable for a
    given model + row order), so two byte-identical registries fingerprint equal and
    ANY change to a rule/citation/quote changes the fingerprint. Used to stamp the
    audit report and let ``vault remediate`` FAIL CLOSED when the rule registry drifted
    between the audit and the remediation (so a re-derived verbatim quote can never be
    a span the audit never grounded).
    """
    return hashlib.sha256(
        registry.model_dump_json().encode("utf-8")).hexdigest()


def load_registry_snapshot(
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> RegistrySnapshot:
    """Load and validate one complete live-registry snapshot, or fail closed.

    All filesystem, YAML, model, duplicate, empty, and incomplete-coverage
    failures collapse to one stable path-free exception.  The fingerprint is
    computed from the same in-memory registry returned to the caller, preventing
    a command from validating one load while binding confirmations to another.
    """
    try:
        root = Path(data_dir)
        if not root.is_dir():
            raise ValueError("registry directory is unavailable")
        paths = sorted(
            path for path in root.iterdir()
            if path.is_file()
            and path.suffix == ".yaml"
            and not path.name.startswith("_")
        )
        if not paths:
            raise ValueError("registry directory contains no YAML files")

        rows: list[RuleRow] = []
        for path in paths:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "rows" not in data:
                raise ValueError("registry file must contain rows")
            raw_rows = data["rows"]
            if not isinstance(raw_rows, list) or not raw_rows:
                raise ValueError("registry rows must be a non-empty list")
            rows.extend(RuleRow.model_validate(raw) for raw in raw_rows)

        registry = Registry(rows=rows)
        rows_by_id = {row.rule_id: row for row in registry.rows}
        required_auxiliary_rows = [
            rows_by_id.get(rule_id) for rule_id in REQUIRED_AUXILIARY_RULE_IDS
        ]
        if (
            not registry.rows
            or not coverage_report(registry)["complete"]
            or any(
                row is None
                or row.gap
                or not row.citations
                or row.machine_check is None
                for row in required_auxiliary_rows
            )
        ):
            raise ValueError("registry is empty or incomplete")
        return RegistrySnapshot(
            registry=registry,
            fingerprint=registry_fingerprint(registry),
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise RegistryUnavailable("CRS rule registry unavailable") from None


# --------------------------------------------------------------------------- #
# row_to_answer — a rule row → the frozen grounding-gate answer object.
# --------------------------------------------------------------------------- #
def row_to_answer(row: RuleRow) -> dict:
    """Build a grounding-gate answer object from a rule row's PII-free fields ONLY.

    Emits ONE claim per :class:`Citation` (each claim cites exactly its own
    chunk_id and carries its own verbatim quote), so EVERY citation's quote must
    ground — any single ungrounded citation fails the whole-row verdict
    (fail-closed). ``basis`` / ``abstentions`` / ``prose`` are empty: the gate
    never inspects them, and nothing private is ever placed here.
    """
    claims = [
        {
            "id": f"{row.rule_id}::{i}",
            "text": row.claim_text,
            "citations": [cit.chunk_id],
            "quote": cit.quote,
        }
        for i, cit in enumerate(row.citations)
    ]
    return {
        "question": row.claim_text,
        "claims": claims,
        "basis": [],
        "abstentions": [],
        "prose": "",
    }


# --------------------------------------------------------------------------- #
# validate_registry — gate every non-gap row through the SHIPPED grounding gate.
# --------------------------------------------------------------------------- #
def validate_registry(registry: Registry, db: str | Path) -> dict:
    """Feed every NON-gap row through :func:`grounding.check_answer` (fail-closed).

    Returns ``{total, grounded, violations}`` where *total* counts non-gap rows,
    *grounded* is how many passed the gate, and each violation is
    ``{rule_id, reasons, citations}``. A gap:true row is SKIPPED (a documented
    coverage GAP is not expected to ground — surfaced by :func:`coverage_report`
    instead). One ungrounded non-gap row is a violation; a caller treats any
    violation as an aggregate failure.
    """
    db = Path(db)
    total = 0
    grounded = 0
    violations: list[dict] = []
    for row in registry.rows:
        if row.gap:
            continue
        total += 1
        verdict = grounding.check_answer(row_to_answer(row), db)
        if verdict["verdict"] == "pass":
            grounded += 1
        else:
            reasons = sorted({r for v in verdict["violations"] for r in v["reasons"]})
            violations.append({
                "rule_id": row.rule_id,
                "reasons": reasons,
                "citations": [c.chunk_id for c in row.citations],
            })
    return {"total": total, "grounded": grounded, "violations": violations}


# --------------------------------------------------------------------------- #
# retrieve_what_you_cite — re-select the cited chunk from the baked query+selector.
# --------------------------------------------------------------------------- #
def _select_chunk(db: Path, row: RuleRow) -> str | None:
    """Reproduce a row's documented selection rule against the live index.

    Mirrors ``test_document_agents._apply_selection_rule``: run the baked
    ``query`` (BM25 order, restricted to ``selector.family``), drop hits whose
    chunk_id starts with any ``deny_families`` prefix (year-end reports /
    superseded amendments), then return the FIRST surviving hit that resolves and
    — if the selector names a ``marker`` and/or ``require_title_contains`` —
    contains that non-volatile marker / title. Returns the selected chunk_id, or
    ``None`` if the rule abstains. A wrong / historical / adjacent chunk therefore
    cannot silently ground the row (T-31-01).
    """
    sel = row.selector
    hits = searchindex.search(db, row.query, limit=_SEARCH_LIMIT, family=sel.family)["hits"]
    for h in hits:
        cid = h["chunk_id"]
        if any(cid.startswith(pref) for pref in sel.deny_families):
            continue
        chunk = searchindex.resolve(db, cid)
        if chunk is None:
            continue
        if sel.require_title_contains and sel.require_title_contains not in (chunk.get("title") or ""):
            continue
        if sel.marker and sel.marker not in chunk["text"]:
            continue
        return cid
    return None


def retrieve_what_you_cite(registry: Registry, db: str | Path) -> dict:
    """Per non-gap row: re-select via query+selector, then check agree + ground.

    Returns ``{rule_id: {selected_chunk_id, agrees_with_citation, grounds}}``:
      * ``selected_chunk_id`` — what the baked query + selector select (or None);
      * ``agrees_with_citation`` — the selection is among the row's cited chunk ids
        (catches a row that steers to a different chunk than it cites);
      * ``grounds`` — the selected chunk verbatim-grounds the quote(s) the row cites
        FOR that chunk, via the SHIPPED gate (never a forked substring check).
    """
    db = Path(db)
    report: dict[str, dict] = {}
    for row in registry.rows:
        if row.gap:
            continue
        selected = _select_chunk(db, row)
        cited_ids = {c.chunk_id for c in row.citations}
        agrees = bool(selected) and selected in cited_ids
        grounds = False
        if selected is not None:
            probe = {
                "question": row.claim_text,
                "claims": [
                    {
                        "id": f"{row.rule_id}::sel",
                        "text": row.claim_text,
                        "citations": [selected],
                        "quote": c.quote,
                    }
                    for c in row.citations
                    if c.chunk_id == selected
                ],
                "basis": [],
                "abstentions": [],
                "prose": "",
            }
            if probe["claims"]:
                grounds = grounding.check_answer(probe, db)["verdict"] == "pass"
        report[row.rule_id] = {
            "selected_chunk_id": selected,
            "agrees_with_citation": agrees,
            "grounds": grounds,
        }
    return report


# --------------------------------------------------------------------------- #
# coverage_report — the full four-group required-grid coverage (RULE-03).
# --------------------------------------------------------------------------- #
def _covers(rule_id: str, label: str) -> bool:
    """True iff *label*'s dotted components are a prefix of *rule_id*'s components."""
    rc = rule_id.split(".")
    lc = label.split(".")
    return rc[: len(lc)] == lc


def coverage_report(registry: Registry) -> dict:
    """Report present / missing / gap coverage of the required grid, per group.

    Returns ``{by_group:{group:{required, present, missing, gaps}}, complete}``:
      * ``present`` — a label covered by at least one NON-gap row;
      * ``gaps``    — a label covered ONLY by gap:true rows (a documented GAP,
        never a fabricated citation);
      * ``missing`` — a label with NO row at all (a silent omission);
      * ``complete`` — True iff every group has an empty ``missing`` (every required
        label is either present or an explicitly documented gap).
    """
    by_group: dict[str, dict] = {}
    complete = True
    for group, labels in REQUIRED_RULE_IDS.items():
        group_rows = [r for r in registry.rows if r.factor_group == group]
        duplicates: list[str] = []
        unknown: list[str] = []
        malformed: list[str] = []
        if group == "program_eligibility":
            counts = Counter(row.rule_id for row in group_rows)
            duplicates = sorted(rule_id for rule_id, count in counts.items() if count > 1)
            unknown = sorted(set(counts).difference(labels))
            malformed = sorted(
                rule_id for rule_id in counts
                if not re.fullmatch(r"(?:fsw|fst|cec)(?:\.[a-z_]+)+", rule_id)
            )
        present: list[str] = []
        gaps: list[str] = []
        missing: list[str] = []
        for label in labels:
            covering = [
                r for r in group_rows
                if r.rule_id == label
                if group == "program_eligibility"
            ] if group == "program_eligibility" else [
                r for r in group_rows if _covers(r.rule_id, label)
            ]
            if any(not r.gap for r in covering):
                present.append(label)
            elif covering:  # covered only by gap rows
                gaps.append(label)
            else:
                missing.append(label)
        if missing or gaps or duplicates or unknown or malformed:
            complete = False
        by_group[group] = {
            "required": sorted(labels),
            "present": sorted(present),
            "missing": sorted(missing),
            "gaps": sorted(gaps),
            "duplicates": duplicates,
            "unknown": unknown,
            "malformed": malformed,
        }
    return {"by_group": by_group, "complete": complete}


# --------------------------------------------------------------------------- #
# render_coverage_markdown / main — the PII-free public COVERAGE.md emitter.
# --------------------------------------------------------------------------- #
def render_coverage_markdown(registry: Registry) -> str:
    """Render the coverage report as deterministic PII-free markdown.

    Consumed by Plan 31-05 (``python -m crawler.crs_rules > COVERAGE.md``). The
    output is a pure function of the registry structure (sorted labels, fixed
    group order) so a committed COVERAGE.md can be byte-compared against fresh
    output as a drift guard. Contains ONLY rule labels + gap reasons — no PII.
    """
    cov = coverage_report(registry)
    gap_notes: dict[str, list[tuple[str, str]]] = {}
    for row in registry.rows:
        if row.gap:
            gap_notes.setdefault(row.factor_group, []).append(
                (row.rule_id, row.gap_reason or "(no reason recorded)")
            )

    lines: list[str] = ["# CRS Rule Registry Coverage", ""]
    lines.append(
        "Full scored CRS grid plus grounded auxiliary rule domains. Each required rule label is "
        "present (grounded rows exist), a documented GAP (un-groundable from the "
        "current corpus — never a fabricated citation), or MISSING."
    )
    lines.append("")
    lines.append(
        f"**Status:** {'COMPLETE' if cov['complete'] else 'INCOMPLETE — see MISSING rows below'}"
    )
    lines.append("")

    for group in REQUIRED_RULE_IDS:
        info = cov["by_group"][group]
        lines.append(f"## {group}")
        lines.append("")
        lines.append(
            f"required: {len(info['required'])} · present: {len(info['present'])} · "
            f"gaps: {len(info['gaps'])} · missing: {len(info['missing'])}"
        )
        lines.append("")
        lines.append("| required rule label | status |")
        lines.append("| --- | --- |")
        for label in info["required"]:
            if label in info["present"]:
                status = "present"
            elif label in info["gaps"]:
                status = "GAP (documented — un-groundable in current corpus)"
            else:
                status = "MISSING"
            lines.append(f"| {label} | {status} |")
        lines.append("")
        notes = sorted(gap_notes.get(group, []))
        if notes:
            lines.append("Documented gaps:")
            lines.append("")
            for rule_id, reason in notes:
                lines.append(f"- `{rule_id}` — {reason}")
            lines.append("")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# no_inlined_volatile_rules — the static gate (RULE-02, Pitfall 4).
#
# The registry is the ONE place a volatile CRS value may live, each paired with a
# resolving citation + verbatim quote (inside a ``machine_check`` payload or a
# ``quote``). Anywhere else — a Python literal, a comparison, or auditor MARKDOWN
# PROSE — a volatile CRS threshold is a violation. The gate is deliberately
# conservative (a documented pattern set over non-comment lines) so a header /
# docstring / heading mentioning a value in prose does not self-invalidate it.
# --------------------------------------------------------------------------- #

# The registry fields that legitimately CARRY grounded values or verbatim corpus
# text — a line whose leading YAML key (or list-item key) is one of these is a
# grounded payload/quote carrier, NOT inlined prose, and is skipped. Derived from
# the registry models (machine_check payload + citation + volatility metadata), so
# the allow context is defined BY the registry schema, never an ad-hoc list.
_ALLOW_KEYS: frozenset[str] = frozenset({
    # MachineCheck / PointsEntry / AcceptedValue payload fields (volatile numbers live here)
    "min_value", "max_value", "window_days", "cap_value", "points",
    "min_score", "max_score", "years_min", "years_max", "level",
    "citation_index", "flag_value", "value", "label", "ability", "test_type",
    "accepted_values", "points_by_level",
    "minimum_duration_months", "minimum_hours", "minimum_hours_per_week",
    "maximum_hours_per_week",
    "lookback_years", "included_hierarchy", "excluded_hierarchy",
    "applicability", "conditional_na",
    # verbatim grounded corpus text + citation coordinate (carry real numbers, grounded)
    "quote", "chunk_id",
    # a selector marker is BY CONSTRUCTION a verbatim substring of the grounded
    # chunk (retrieve-what-you-cite fails otherwise), so it is a grounded carrier,
    # not inlined ungrounded prose — a tier marker may legitimately quote "CLB 9".
    "marker",
    # dated / provenance metadata (grounded, not prose)
    "effective_from", "effective_to", "crawl_date", "source_family",
})

# A leading YAML key / list-item key on a line: ``  key:`` or ``  - key:``.
_YAML_KEY_RE = re.compile(r"^\s*-?\s*\{?\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")

# Volatile CRS point / cap values that must be grounded, not inlined.
_VOLATILE_POINTS_RE = re.compile(r"\b(?:15|25|30|50|100|200|600)\b")
# A CLB/NCLC benchmark number is inherently a volatile CRS threshold (no extra
# context needed — ``CLB``/``NCLC`` IS the CRS context).
_CLB_RE = re.compile(r"\b(?:CLB|NCLC)\s*\d+", re.IGNORECASE)
# Validity / work windows (language <2y, ECA <5y, work within 10y).
_WINDOW_RE = re.compile(r"\b(?:less than\s+)?(?:2|5|10)\s+years?\b", re.IGNORECASE)
# A policy effective date (e.g. the 2025-03-25 arranged-employment repeal).
_DATE_RE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
_MEC_DURATION_RE = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:hours?|months?|years?)\b",
    re.IGNORECASE,
)
_MEC_DURATION_CTX_RE = re.compile(
    r"\b(?:minimum|maximum|duration|lookback|recency|continuous|fsw|fst|cec|mec)\b",
    re.IGNORECASE,
)
_MEC_NOC_RE = re.compile(
    r"\b(?:Major\s+Group|Minor\s+Group|Unit\s+Group|Sub-Major\s+Group)"
    r"\s*(?:category\s*)?\d+",
    re.IGNORECASE,
)
_MEC_TEER_RE = re.compile(r"\b(?:NOC|TEER)\s*(?:category\s*)?\d+", re.IGNORECASE)
_MEC_PROGRAM_CTX_RE = re.compile(
    r"\b(?:fsw|fst|cec|mec|program\s+eligibility|skilled\s+trade)\b",
    re.IGNORECASE,
)
_MEC_GRID_RE = re.compile(
    r"\b(?:fsw|pass[_\s-]?mark|selection[_\s-]?grid|mec[_\s-]?grid)\b",
    re.IGNORECASE,
)
_MEC_GRID_VALUE_RE = re.compile(r"\b(?:0|1|2|3|4|5|6|7|8|9|10|11|12|13|15|19|21|22|23|24|25|28|67|100)\b")
_MEC_DATE_CTX_RE = re.compile(
    r"\b(?:mec|eligib\w*|program|fsw|fst|cec)\b",
    re.IGNORECASE,
)
_DLI_CTX_RE = re.compile(
    r"\b(?:dli|designated\s+learning\s+institution|pgwp|study\s+permit)\b",
    re.IGNORECASE,
)
_DLI_THRESHOLD_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:days?|months?|years?|%)\b",
    re.IGNORECASE,
)
_MEC_FUNDS_CTX_RE = re.compile(
    r"\b(?:settlement|proof.of.funds|funds?|lico)\b",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(r"(?:[$€£]\s*|CAD\s*)\d[\d,]*(?:\.\d+)?", re.IGNORECASE)
# CRS context words that qualify an otherwise-ambiguous number/date as a CRS rule.
_CRS_CTX_RE = re.compile(
    r"\b(points?|pts|crs|cap|capped|transferab\w*|nomination|sibling|french|"
    r"arranged|job.?offer|bonus|clb|nclc|benchmark|validity|valid|eca|"
    r"language\s+test|credential\s+assessment)\b",
    re.IGNORECASE,
)


def _is_grounded_payload_line(line: str) -> bool:
    """True if the line's leading key is a grounded value/quote carrier (skip it)."""
    m = _YAML_KEY_RE.match(line)
    return bool(m) and m.group(1) in _ALLOW_KEYS


def _scan_line_for_volatile(line: str) -> str | None:
    """Return a violation kind for a volatile CRS threshold on *line*, else None."""
    probe = line.replace("_", " ")
    if _DLI_CTX_RE.search(probe) and _DATE_RE.search(probe):
        return "dli_policy_date"
    if _DLI_CTX_RE.search(probe) and _DLI_THRESHOLD_RE.search(probe):
        return "dli_threshold"
    if _MEC_FUNDS_CTX_RE.search(probe) and _CURRENCY_RE.search(probe):
        return "mec_funds_value"
    if _CLB_RE.search(probe):
        return "mec_language_level"
    if _MEC_NOC_RE.search(probe) or (
        _MEC_PROGRAM_CTX_RE.search(probe) and _MEC_TEER_RE.search(probe)
    ):
        return "mec_noc_hierarchy"
    if _MEC_DURATION_CTX_RE.search(probe) and _MEC_DURATION_RE.search(probe):
        return "mec_duration"
    if _MEC_GRID_RE.search(probe) and _MEC_GRID_VALUE_RE.search(probe):
        return "mec_grid_value"
    if _MEC_DATE_CTX_RE.search(probe) and _DATE_RE.search(probe):
        return "mec_policy_date"
    has_ctx = bool(_CRS_CTX_RE.search(probe))
    if has_ctx and _VOLATILE_POINTS_RE.search(probe):
        return "points_literal"
    if has_ctx and _WINDOW_RE.search(probe):
        return "validity_window"
    if has_ctx and _DATE_RE.search(probe):
        return "policy_date"
    return None


def _python_executable_lines(text: str) -> dict[int, str]:
    """Return Python source lines with comments removed by the tokenizer."""
    lines = text.splitlines()
    sanitized = list(lines)
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                lineno, column = token.start
                sanitized[lineno - 1] = sanitized[lineno - 1][:column]
    except (IndentationError, tokenize.TokenError):
        pass
    return {index: line for index, line in enumerate(sanitized, start=1)}


def _python_constant_lines(text: str) -> list[tuple[int, str]]:
    """Return executable constant contexts, excluding comments and docstrings."""
    tree = ast.parse(text)
    docstring_nodes: set[int] = set()
    for owner in ast.walk(tree):
        if not isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(owner, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstring_nodes.add(id(body[0].value))

    code_lines = _python_executable_lines(text)
    contexts: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in docstring_nodes:
            continue
        if not isinstance(node.value, (str, int, float)):
            continue
        line = code_lines.get(node.lineno, "")
        contexts.append((node.lineno, f"{line} {node.value}"))
    return contexts


def no_inlined_volatile_rules(paths) -> list[dict]:
    """Scan *paths* for volatile CRS thresholds inlined outside a grounded rule row.

    Returns a list of violations ``{path, line, snippet, kind}``. For each file:
      * blank lines and comment / heading lines (stripped text starts with ``#``)
        are skipped — a docstring header or a markdown heading mentioning a value
        in prose does NOT self-invalidate the gate;
      * a line whose leading YAML key is a grounded payload/quote carrier
        (:data:`_ALLOW_KEYS`, derived from the registry models) is skipped — that
        is exactly WHERE a volatile value is allowed to live, paired with a
        citation + verbatim quote;
      * every other line is checked for an inlined CLB/NCLC benchmark, a volatile
        points/cap value, a validity/work window, or a policy date in a CRS
        context — each is a violation (RULE-02).

    A clean file (values referenced via a RuleRow / registry lookup, never as a
    bare literal) returns ``[]``. A missing path is skipped silently (the auditor
    prose directory may not exist yet — the gate is WIRED, and trips the moment a
    file appears with an inlined threshold).
    """
    violations: list[dict] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            try:
                contexts = _python_constant_lines(text)
            except SyntaxError:
                contexts = [
                    (lineno, line)
                    for lineno, line in _python_executable_lines(text).items()
                    if line.strip()
                ]
            for lineno, context in contexts:
                kind = _scan_line_for_volatile(context)
                if kind:
                    violations.append({
                        "path": str(path),
                        "line": lineno,
                        "snippet": _python_executable_lines(text).get(lineno, "").strip(),
                        "kind": kind,
                    })
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _is_grounded_payload_line(line):
                continue
            kind = _scan_line_for_volatile(line)
            if kind:
                violations.append({
                    "path": str(path),
                    "line": lineno,
                    "snippet": stripped,
                    "kind": kind,
                })
    return violations


def main(argv: list[str] | None = None) -> int:
    """Print the coverage markdown for the public registry to stdout (PII-free)."""
    registry = load_registry()
    sys.stdout.write(render_coverage_markdown(registry))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
