# Phase 30: Extraction Quarantine & Field Confirmation - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Applicant can turn vault documents into field-level confirmed evidence while all automated
extraction remains quarantined until reviewed. Requirements: EXTRACT-01, EXTRACT-02, EXTRACT-03,
EXTRACT-04, EXTRACT-05.

Success criteria (what must be TRUE):
1. Running extraction renders/reads vault documents and proposes structured fields (test scores,
   dates, credentials, NOC/TEER, hours, duration, issuer) only as `pending` vault values.
2. Applicant can confirm, correct, or reject each extracted field while seeing the raw value,
   normalized value, source page/crop, affected CRS factor, and profile claim.
3. Pending, rejected, low-quality, or ambiguous extracted fields cannot become audit-eligible
   evidence and cannot support a green verdict.
4. Replacing the source file, changing parser version, editing the profile claim, or updating the
   rule-registry version marks affected confirmations stale until re-confirmed.
5. A doctor/preflight check reports missing extraction dependencies and scan-quality issues
   (scanned, rotated, password-protected, low-text) instead of failing silently.

</domain>

<decisions>
## Implementation Decisions

### The agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use ROADMAP phase goal, success criteria, project constraints, and codebase conventions.

### Builds directly on the Phase 29 vault (already shipped)
- `crawler/vault.py` + `crawler/models/vault.py` — private per-candidate `vault.sqlite` with
  migrations, CRS factor/ITA store, content-addressed raw files at `files/raw/<sha256>`, and
  `ev_`-prefixed evidence IDs provably disjoint from corpus `relpath#ordinal` citations.
- `crawler/paths.py` — shared personal-path resolver + `resolve_within` containment guard.
- Additive `corpus-crawler vault` CLI (init/profile/ita/import/list) on the frozen 5-key JSON
  envelope; SCHEMA_VERSION "1.0"; extended publish-safe (`VAULT_ARTIFACT`) + `.gitignore`
  (`*.sqlite*`).

### Locked constraints (from PROJECT.md / research SUMMARY-v4.0 / PITFALLS-v4.0)
- **Extraction is the ONLY non-grounded step.** All extracted fields are written as `pending`
  vault values and are NOT audit-eligible until field-level user confirmation (confirm/correct/
  reject). Low-quality/ambiguous/rejected/pending values can never yield a green verdict.
- Confirmations are tied to source file hash, page/crop hash, parser version, profile-claim
  version, and rule-registry version; any change marks them stale and blocks green verdicts.
- New extraction stack (from STACK-v4.0, local-only, no cloud/heavy-ML): `pypdfium2` (default
  PDF-page → image renderer), `Pillow` (image handling/normalization/OCR handoff), `pdfminer.six`
  (first-tier born-digital text extraction, before OCR), optional `pytesseract` behind an OCR
  extra + `tesseract --version`/language preflight. Prefer render-to-image so the agent/user can
  visually read tables/forms. Do NOT add cloud OCR/document AI, vector/embedding, or heavy ML
  (PaddleOCR/EasyOCR/docTR). PyMuPDF only optional (AGPL). No default poppler/pdf2image dependency.
- All rendered images / OCR text / extracted values are PII and stay in the git-ignored vault;
  never repo/corpus/stdout/public reports/tracked fixtures. Extend publish-safe coverage as needed.
- Poetry-managed Python; pydantic models; reuse the Phase 29 vault primitives; do NOT modify the
  frozen v3.x trust path (search/`--cite`/grounding gate/JSON envelope).
- Provide a `doctor`/preflight verb reporting missing extraction deps and scan-quality problems.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be confirmed during plan-phase research. Build on Phase 29's shipped vault
(`crawler/vault.py`, `crawler/models/vault.py`, `crawler/paths.py`, `vault` CLI). Reference
research: `.planning/research/ARCHITECTURE-v4.0.md` (`crawler/extraction.py` — pdfminer text first,
pypdfium2 render always, Pillow normalization, optional Tesseract; writes only `pending` values +
vault-local artifacts; field-level confirm/correct/reject) and `.planning/research/PITFALLS-v4.0.md`
(silent-misread, rubber-stamp-confirmation, dependency-friction, PII-leak pitfalls → tests).

</code_context>

<specifics>
## Specific Ideas

Refer to ROADMAP Phase 30 description, the five success criteria above, and the v4.0 research
files for the extraction/confirmation design (render + text extraction to `pending` vault values,
field-level confirmation workflow showing raw/normalized/page-crop/factor/claim, staleness
invalidation on hash/version change, `doctor` preflight for deps and scan quality).

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
