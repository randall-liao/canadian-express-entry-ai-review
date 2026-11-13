# Phase 38 — Research: Redacted Professional Review Packet

**Researched:** 2026-07-17
**Consumed by:** 38-01..04 plans, 38-VALIDATION.md
**Scope:** a redacted, opt-in lawyer/RCIC review packet — a curated projection over the
Phase-37 remediation checklist. Zero new runtime deps; no second trust path.

## The projection chain (PKT-02/05)

`vault audit` → grounded `PrivateAuditReport` (vault) → Phase-37
`build_remediation` → `PrivateRemediationChecklist` (vault, one item per unresolved
finding) → **Phase-38 `build_packet`** → `ReviewPacket` (a FURTHER-redacted,
closed-allowlist projection). Each stage only DROPS or re-frames fields; nothing is
re-scored or re-grounded. The packet reuses the Phase-37 report-load + registry-drift
gate + projection (the roadmap's "reuses finding-selection and report-load").

**Reuse without re-writing a remediation artifact:** extract a shared
`remediation._build_checklist_for_run(vault, audit_run_id, registry)` (resolve
completed run → `_load_report` → registry-fingerprint gate → `build_remediation`) so
BOTH `run_remediation` (which then writes) and `run_review_packet` call it. No
duplication, one trust path.

## Closed-allowlist redaction model (PKT-02)

`PacketFinding` (pydantic v2, `extra="forbid"`) admits ONLY:
- `factor_id: str`, `verdict: Verdict`, `reason_code: str | None`,
  `finding_kind: Literal[gap|at_risk|unpriced]`,
- `score_impact` (score_delta / substantiated_points — CRS score numbers, not
  identifying PII),
- `citations: list[PacketCitation{citation_id (reject ev_), quote}]` (resolvable
  authoritative corpus spans),
- `action: str` (generic screening prose).

It structurally CANNOT carry a raw applicant value, an `ev_` evidence id, or an
absolute path: there is no field for them, `extra="forbid"` rejects an injected key,
a `citation_id` validator rejects `ev_`, and (where a path could appear) a validator
rejects absolute paths. This mirrors `PublicAuditEnvelope`/`PublicRemediationSummary`.

`ReviewPacket` = `{ source_audit_run_id, generated_note (screening notice),
findings: list[PacketFinding], manifest: RedactionManifest }`. It does NOT carry the
candidate id, `ev_` pointers, or any document bytes.

`RedactionManifest` = the auditable record: counts of findings included; the set of
finding fields EXCLUDED by the allowlist (e.g. `evidence_ids`, claimed/confirmed raw
values); the list of documents excluded-by-default; and any explicitly-included
documents (per-document opt-in). PKT-04's "records what was included, excluded, and
redacted."

## Render-then-scan double gate (PKT-04)

Before ANY real write, `run_review_packet` renders the packet (JSON + Markdown) to
bytes and scans those bytes with a self-contained deny-pattern scan
(`_scan_rendered_bytes`) for: absolute paths (`/home/`, `/Users/`, `/root/`, drive  <!-- # publish-safe: allow -->
paths), `ev_` evidence ids, and secret shapes (mirroring
`scripts/check_publish_safe.py` patterns — but self-contained, since `scripts` is not
an importable package). A hit REFUSES fail-closed (`RemediationError`-style
`invalid_input`/exit 2, `reason=rendered_leak`) and writes NOTHING. This is
belt-and-suspenders on top of the structural allowlist: even a future field addition
that leaked a path/`ev_` is caught before it lands on disk.

## `--dry-run` preview (PKT-01)

`vault review-packet --dry-run` builds the packet + manifest and emits the manifest
(PII-light counts) on stdout, writing NOTHING (no file, no dir). The non-dry-run path
writes the packet + manifest under the vault after the render-then-scan passes.

## Per-document opt-in staging (PKT-03)

By default the packet carries NO raw/rendered/OCR document content — only findings +
citations. `--include-document <doc_id>` (repeatable) opts in a specific vault
`documents` row; the included content is COPIED (staged) ONLY under
`candidates/<id>/output/review-packet/<pkt_id>/documents/` via `resolve_within`
(never published, never on stdout), and the manifest records the inclusion
(document_id only — never the raw path). An unknown/foreign document id is refused
fail-closed. Default (no `--include-document`) → the manifest lists every document as
excluded-by-default.

## Vault-only write + non-vault refusal (PKT-04)

Every path is re-anchored via `paths.resolve_within(vault.root, "output",
"review-packet", ...)`. A `--out-dir` (if offered) or any destination that does not
resolve under the vault raises `PathEscapeError` → `invalid_input`/exit 2. Mirrors the
`ground`/`checklist` `--out-dir` containment precedent, but anchored at the vault
(not the frozen repo-personal root) because the packet is a vault artifact.

## Publish-safe + no-inlined + conformance (PKT-02/03 hardening)

- `output/review-packet/` added to `scripts/check_publish_safe.py` `VAULT_SUBTREES`.
- The no-inlined-volatile-rules gate already forward-guards `crawler/review_packet.py`
  (added in Phase 37); it must stay clean.
- Conformance (38-04): a structural-firewall test (the packet models reject
  `ev_`/absolute/raw-value keys at construction), a redaction-leak test (a synthetic
  finding carrying an `ev_`/abs-path is dropped/refused, and the render-then-scan
  catches an injected leak), retrieve-what-you-cite (every packet citation+quote is a
  real registry pair), and a no-second-trust-path (AST import) check — forward-guards
  the Phase-39 SAFE-06/07 release gate.

## Frozen constraints (carried forward)
- Zero new runtime deps (pure stdlib + pydantic v2 in the stack).
- No second trust path; no re-ground/re-score/synthesized volatile requirement.
- Vault-only PII; stdout PII-light; screening framing on every artifact.
- Fail closed; every refusal writes zero artifacts.
- Tracked tree publish-safe.
