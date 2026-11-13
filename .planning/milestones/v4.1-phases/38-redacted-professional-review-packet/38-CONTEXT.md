# Phase 38: Redacted Professional Review Packet - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via `workflow.skip_discuss`)

<domain>
## Phase Boundary

Let the applicant **preview and produce an opt-in, explicitly redacted lawyer/RCIC
review packet** from selected audit/remediation findings — a **curated, redacted
export layer over the Phase-37 remediation checklist** — staged ONLY inside the
vault, excluding raw documents by default. It is a further-redacted PROJECTION of
already-grounded data; no re-score, no re-ground, no second trust path, no new
runtime dependency.

Four seams:

1. **Closed-allowlist redaction model + `RedactionManifest` (PKT-02, PKT-05).** A
   `PacketFinding` whose schema STRUCTURALLY cannot carry raw applicant values,
   absolute paths, or `ev_` evidence ids unless the packet contract explicitly
   admits a field (`extra="forbid"` + field validators). The packet admits only:
   factor id, verdict + reason, score impact, `finding_kind`, the resolvable
   authoritative corpus citations (id + verbatim quote), and the deterministic
   action. A `RedactionManifest` records what was included, excluded, and redacted.
   Prominent screening-not-legal-advice framing; no approval/eligibility/outcome
   prediction.

2. **`vault review-packet` verb + writer + `output/review-packet/` subtree
   (PKT-04).** Build the packet from a selected completed audit run (reusing the
   Phase-37 report-load + `build_remediation` projection), write the packet JSON +
   Markdown ONLY under `candidates/<id>/output/review-packet/<pkt_id>.{json,md}` via
   `resolve_within`, refuse non-vault destinations / path escapes, and register the
   subtree in the publish-safe allow-list.

3. **Render-then-scan double gate + `--dry-run` preview (PKT-01, PKT-04).** Preview
   a dry-run `RedactionManifest` WITHOUT writing anything; and, before any real
   write, SCAN the rendered packet bytes for absolute paths / `ev_` ids / secret
   patterns and REFUSE (fail-closed) if the rendered bytes carry a leak — a
   defense-in-depth gate on top of the structural allowlist.

4. **Per-document opt-in staging (PKT-03).** Raw, rendered, and OCR document content
   is EXCLUDED by default; any document inclusion requires an explicit per-document
   opt-in (`--include-document <doc_id>`) and the included content is STAGED only
   inside the vault packet subtree (never published, never on stdout). The manifest
   records each inclusion.

Do NOT re-score/re-ground, synthesize a volatile requirement, add a PDF/templating/
encryption dependency, generate legal advice, or write anywhere outside the vault.

</domain>

<decisions>
## Implementation Decisions

### Locked Decisions

- The packet is a REDACTED PROJECTION of the Phase-37 remediation checklist (which is
  itself a projection of the grounded `PrivateAuditReport`) — it reuses the report
  load + `build_remediation`, never re-grounds/re-scores, and inlines no volatile
  literal (the no-inlined gate covers `crawler/review_packet.py`).
- Redaction is a CLOSED ALLOWLIST: `PacketFinding` is `extra="forbid"` and admits only
  the named PII-free fields; a `citation_id` validator rejects `ev_`; a path validator
  rejects absolute paths. Raw applicant values / `ev_` pointers / absolute paths are
  structurally unrepresentable in the packet schema.
- Raw/rendered/OCR document content is EXCLUDED by default; inclusion is explicit,
  per-document, and STAGED vault-only.
- Every write is UNCONDITIONALLY under `candidates/<id>/output/review-packet/` via `resolve_within`
  (the verb offers no destination override, mirroring `vault remediate`), so a non-vault destination is
  structurally unreachable and any crafted escaping path component raises `PathEscapeError` -> refusal.
- Render-then-scan: the rendered packet bytes are scanned for abs-path/`ev_`/secret
  patterns BEFORE the write; a hit refuses fail-closed (no artifact).
- `--dry-run` previews the `RedactionManifest` and writes NOTHING.
- Every rendered packet carries the substantiation-screening notice; no approval,
  eligibility, or outcome prediction.
- Prerequisite refusals reuse the Phase-36/37 clean-refusal style (`invalid_input`/
  exit 2 + reason code, zero artifacts); a bad corpus prerequisite is not on this path
  (the packet projects the stored report, like remediation).

### Agent Discretion

All remaining implementation choices are at the agent's discretion. Prefer the
existing remediation / audit-report / vault-path / render patterns. Add no runtime
dependency.

</decisions>

<code_context>
## Existing Code Insights

- `crawler/remediation.py` already loads a completed audit report, gates on the
  registry fingerprint, and builds a `PrivateRemediationChecklist` (finding
  selection + report load to reuse) — extract a shared "resolve+load+gate+build"
  helper so the packet reuses it without re-writing a remediation artifact.
- `crawler/models/audit.py` / `crawler/remediation.py` are the two-tier +
  allowlist-projection + PII-firewall patterns (`extra="forbid"`, reject `ev_`,
  reject absolute path).
- `crawler/audit_report.py::SCREENING_NOTICE` is the screening framing to reuse.
- `crawler/paths.py::resolve_within` + `is_within` are the vault-containment guards;
  `cli._cmd_ground`/`_cmd_checklist` are the `--out-dir` containment precedents.
- `scripts/check_publish_safe.py::ABS_PATH_PATTERNS`/`SECRET_PATTERNS` are the
  deny-pattern shapes to mirror for the render-then-scan (scripts is NOT a package —
  define a self-contained scan in the module, do not import scripts).
- `scripts/check_publish_safe.py::VAULT_SUBTREES` must gain `output/review-packet/`.
- `crawler/tests/test_crs_no_inlined_rules.py` already forward-guards
  `crawler/review_packet.py` in its scan surface (Phase 37).
- `crawler/vault.py` has document rows (`documents.document_id`, `evidence_id`,
  `storage_relpath`) for the per-document opt-in staging + `new_*_id` minters.

</code_context>

<specifics>
## Specific Ideas

- The manifest is the auditable record of the redaction (included/excluded/redacted).
- The render-then-scan gate is a belt-and-suspenders check on top of the structural
  allowlist — both must hold.

</specifics>

<deferred>
## Deferred Ideas

Recipient-specific export presets (LATER-06) and encrypted packet bundles (LATER-07)
remain out of scope. PDF packet generation is explicitly out of scope (Markdown/JSON
only). Automatic transmission to a lawyer/RCIC is out of scope (the tool only stages).

</deferred>
