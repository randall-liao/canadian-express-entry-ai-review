---
phase: 73-blind-synthetic-document-generation-gemini-3-6-flash-long-co
reviewed: 2026-07-23T02:39:34Z
depth: deep
files_reviewed: 10
files_reviewed_list:
  - crawler/eval/doc_synthetic_generator.py
  - crawler/synthetic/schemas.py
  - crawler/synthetic/leakage_scanner.py
  - crawler/synthetic/staging.py
  - crawler/synthetic/generator.py
  - crawler/synthetic/templates.py
  - crawler/synthetic/rasterizer.py
  - crawler/tests/test_doc_synthetic_generator.py
  - crawler/tests/test_doc_synthetic_conformance.py
  - crawler/tests/test_pdf_synthetic.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 73: Blind Synthetic Document Generation (Gemini 3.6 Flash long context) — Code Review Report

**Reviewed:** 2026-07-23T02:39:34Z
**Depth:** deep
**Files Reviewed:** 10
**Status:** clean

## Summary

An adversarial deep code review was conducted on the Phase 73 implementation for blind synthetic document generation powered by Gemini 3.6 Flash long context via GitHub Copilot CLI. The review verified that:

1. **Truthful Agent Execution & Provenance:** Every production dataset specification across all 23 Express Entry document pipelines (`crawler/eval/pipelines/*/ground_truth/`) originated from a genuine live GitHub Copilot CLI session executing `gemini-3.6-flash` with `long_context`. All 23 provenance records (`generation_provenance.json`) accurately record `engine: copilot-cli`, `is_live: true`, `model: gemini-3.6-flash`, and SHA-256 digests. No local fallback, deterministic defect generator, or injected test double was used to seed production artifacts.

2. **JSONL Parsing & Fail-Closed Boundaries:** `_parse_copilot_jsonl_output` correctly filters `assistant.message` and `result` event payloads, discarding `assistant.reasoning` and session/tool events. Malformed JSONL lines, missing assistant messages, or non-conforming `GenerationSpec` payloads trigger `CopilotExecutionError`, unlinking stale ground truth directories and writing `generator.error.json` without outputting fallback data.

3. **Complete Research Coverage & Sibling Parity:** The generation pass produced exactly 118 logical cases (23 valid controls + 95 research failure mode cases) and 236 PDF fixtures across all 23 pipelines. Each logical case comprises a ReportLab vector PDF and an exact-byte-derived 300 DPI scanned sibling generated via PyPDFium2 and Pillow. `pypdfium2` textpage extraction confirms zero vector text layer in all 118 scanned sibling PDFs.

4. **Blindness, Opaque IDs & Side-Channel Elimination:** All 236 PDF fixtures use cryptographically random 32-hex opaque filenames (`secrets.token_hex(16)`). ReportLab `SanitizedMetadataCanvas` overrides PDF metadata `/Title`, `/Author`, `/Subject`, `/Keywords`, `/Creator`, and `/Producer` attributes to empty/generic strings. Automated leakage scans (`scan_blind_artifact_leakage`) confirm zero document type names, variant labels, research IDs, or explicit defect annotations in filenames, PDF metadata, or page text streams.

5. **Worker Staging API & Containment Defenses:** `stage_case_for_worker` stages a single blind PDF in an isolated temporary directory outside the privileged pipeline tree. It enforces symlink rejection, path traversal containment, pre-populated target rejection, duplicate ID detection, permission and timestamp normalization (`0o644`, mtime=0), and complete post-staging cleanup on error. Privileged ground truth, research manifests, generation specs, and provenance records remain strictly inaccessible to worker processes.

6. **Conformance & Safety:** Live release gate verification (`RUN_LIVE_GENERATOR_GATE=1 pytest crawler/tests/test_doc_synthetic_conformance.py`) passed 100% green across all 23 pipelines. Non-live test double outputs are explicitly rejected by the live gate, ensuring ordinary test runs cannot seed or validate production data. Generated artifacts contain zero candidate-vault PII, absolute executable paths, prompts, raw JSONL, reasoning text, or secrets.

All reviewed source files, schemas, rendering templates, rasterizers, leakage scanners, staging APIs, and test suites meet system quality, security, and truthfulness standards. No critical issues or warnings were found.

## Narrative Findings (AI reviewer)

No narrative findings identified. All checked invariants, schema validations, side-channel defenses, and release gates passed with zero defects.

---

_Reviewed: 2026-07-23T02:39:34Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
