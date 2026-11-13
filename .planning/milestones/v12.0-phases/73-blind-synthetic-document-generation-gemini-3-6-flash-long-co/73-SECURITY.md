---
phase: 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co
slug: blind-synthetic-document-generation-gemini-3-6-flash-long-co
status: verified
threats_total: 21
threats_closed: 21
threats_open: 0
accepted_risks: 0
asvs_level: 1
register_authored_at_plan_time: true
last_audit: 2026-07-23
---

# Phase 73 - Security Audit Report

## Trust Boundaries

| Boundary | Data Crossing | Enforcement |
|----------|---------------|-------------|
| Phase 72 research to generator agent | Privileged failure-mode data | Validated live research, minimal whitelist, escaped untrusted-data boundary |
| Generator agent to renderer | Agent-authored GenerationSpec JSON | JSONL event filtering and strict Pydantic validation |
| Renderer to blind PDFs | Validated content and layout | Sanitized metadata, opaque IDs, leakage scans, exact-byte scan rasterization |
| Private pipeline to worker stage | One selected blind case | Fresh external directory, symlink/path/duplicate checks, allowed-file assertion |
| Concurrent generators to filesystem | 23 independent pipeline writes | Per-document path containment and global conformance |

## Threat Register

| Threat | Category | Mitigation Evidence | Status |
|--------|----------|---------------------|--------|
| T-73-01 | Prompt Injection | Research input is schema-validated, field-whitelisted, delimiter-escaped, and embedded as untrusted JSON; adversarial prompt tests pass; all 23 live artifacts were regenerated after the fix. | closed |
| T-73-02 | Input Tampering | `GenerationSpec`, `TestCaseSpec`, `DefectSpec`, and `PrivateCaseRecord` validate model output before rendering. | closed |
| T-73-03 | Fake Provenance | Live and injected engines are distinct; prompt/output/provenance SHA256 fields and sanitized command flags are conformance-checked. | closed |
| T-73-04 | Deterministic Substitution | Production invokes Copilot CLI and has no deterministic fallback; failures remove stale outputs and write explicit error artifacts. | closed |
| T-73-05 | Filename/Path Disclosure | Every PDF receives an independent random 32-hex filename; global uniqueness and hint scans cover all 236 artifacts. | closed |
| T-73-06 | PDF Metadata Disclosure | Sanitized canvas clears Info metadata; conformance scans metadata, visible/extracted text, and filenames. | closed |
| T-73-07 | Staging Escape | Source/target containment, symlink rejection, duplicate-source rejection, fresh-empty target, normalized metadata, exact allowed-file set, and cleanup tests pass. | closed |
| T-73-08 | Stale Artifact Reuse | Generation clears stale ground truth before work and deletes partial success on every failure. | closed |
| T-73-09 | PII Contamination | Generator prompt prohibits candidate data, uses fictional fixture identities, and publish/leakage tests inspect outputs. | closed |
| T-73-SC | Supply Chain | Phase adds no dependencies or runtime package installation. | closed |
| T-73-10 | PDF Info Leakage | `SanitizedMetadataCanvas` overrides title, author, subject, keywords, creator, and producer. | closed |
| T-73-11 | Scan Text-Layer Leakage | Scanned siblings are image-only PDFs; PyPDFium text extraction confirms zero text layer. | closed |
| T-73-12 | Rasterization DoS | Input bytes, DPI, page count, page dimensions, and aggregate pixels are bounded before render; PDF resources close on errors. | closed |
| T-73-13 | Explanatory Annotation Leakage | Templates and leakage scanner reject defect/test/PFL annotations rather than explaining the injected condition. | closed |
| T-73-14 | Ground-Truth Disclosure | Ground truth/spec/provenance remain in privileged directories; staging copies only an opaque PDF and optional scanned text. | closed |
| T-73-15 | Cross-Pipeline Contamination | Per-document path guards and globally unique opaque IDs prevent sibling pipeline writes/collisions. | closed |
| T-73-16 | Partial Research Coverage | Exact coverage requires 95 research failure IDs plus 23 controls; live gate requires 118 logical cases and 236 PDFs. | closed |
| T-73-17 | False Model Claims | Live gate requires `copilot-cli`, `is_live: true`, Gemini 3.6 Flash, long context, and successful provenance. | closed |
| T-73-18 | Live Artifact Disclosure | All 236 committed PDFs pass automated side-channel scans. | closed |
| T-73-19 | Live Provenance Repudiation | All 23 regenerated provenance records contain current hardened prompt/output hashes and live engine metadata. | closed |
| T-73-20 | Incomplete Live Dataset | The explicitly enabled gate passed after security-triggered regeneration of all 23 pipelines. | closed |

## Accepted Risks Log

No accepted risks.

## Security Audit Trail

| Date | Threats | Closed | Open | Evidence |
|------|---------|--------|------|----------|
| 2026-07-23 | 21 | 21 | 0 | Targeted tests, live gate, hardened 23-agent regeneration, publish-safety scan |

## Sign-Off

- [x] Every plan-time threat has implementation and test/gate evidence.
- [x] Hardened prompt behavior is reflected in regenerated live artifacts.
- [x] No high-severity risk was accepted.
- [x] `threats_open: 0`.

**Approval:** verified 2026-07-23
