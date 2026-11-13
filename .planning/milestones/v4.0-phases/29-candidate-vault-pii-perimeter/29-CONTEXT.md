# Phase 29: Candidate Vault & PII Perimeter - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Applicant can safely store their CRS profile, ITA round/cutoff, and raw documents in a private
vault that cannot contaminate the public repo or authoritative corpus. Requirements: VAULT-01,
VAULT-02, VAULT-03, VAULT-04.

Success criteria (what must be TRUE):
1. Applicant can create or select a non-PII candidate vault and store CRS factor breakdown plus
   ITA round/cutoff under the git-ignored personal boundary.
2. Applicant can import raw PDFs/images and receive vault-local document/evidence IDs while files
   are content-addressed and kept out of the repo, corpus, and public reports.
3. Candidate evidence is visibly separate from authoritative citations: `evidence_id` is never
   interchangeable with `citation_id`, and candidate text is never citable as authority.
4. Attempts to stage or write vault DB/WAL files, rendered images, OCR text, logs, or private
   reports outside the vault are blocked by publish-safe/gitleaks/path-guard checks.

</domain>

<decisions>
## Implementation Decisions

### The agent's Discretion
All implementation choices are at the agent's discretion — discuss phase was skipped per user
setting. Use ROADMAP phase goal, success criteria, project constraints, and codebase conventions
to guide decisions.

### Locked constraints (from PROJECT.md / research SUMMARY-v4.0)
- All PII stays in the git-ignored candidate vault; never in the repo, corpus, stdout, public
  reports, tracked fixtures, or `.planning/`.
- Vault lives under the existing `personal/` boundary (git-ignored) with a platformdirs fallback
  for packaged installs; resolve via a shared path resolver that rejects symlink/`..` escapes.
- SQLite owns vault metadata (profile factors, document metadata, extraction runs, extracted
  values, confirmation state, evidence links, audit runs, verdicts); raw files are
  content-addressed on disk under `personal/candidates/<candidate-id>/`. Do NOT store raw files
  as SQLite BLOBs.
- Critical invariant: `corpus/index.db` is authoritative + PII-free + citeable; the candidate
  `vault.sqlite` is private, evidence-bearing, and never citeable as authority. Use
  `citation_id` only for corpus rules and `evidence_id` only for candidate evidence.
- Extend the existing publish-safe (`scripts/check_publish_safe.py` / `CORPORA_PREFIXES`) and
  gitleaks/pre-commit coverage to all new vault artifacts.
- Python remains Poetry-managed; use `pydantic` models and `platformdirs`; reuse existing
  `crawler/` primitives where sensible.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research (gsd-phase-researcher /
gsd-pattern-mapper). Relevant existing pieces to build on: the `crawler/` package, its `personal/`
prefix handling, `CORPORA_PREFIXES`, `scripts/check_publish_safe.py`, the corpus SQLite/FTS5
pattern, and `platformdirs` usage. Reference research: `.planning/research/ARCHITECTURE-v4.0.md`
(shared path resolver `crawler/paths.py`, candidate vault `crawler/vault.py`).

</code_context>

<specifics>
## Specific Ideas

Refer to ROADMAP phase description, the four success criteria above, and
`.planning/research/ARCHITECTURE-v4.0.md` / `.planning/research/PITFALLS-v4.0.md` for the vault
design (shared resolver, SQLite schema/migrations, content-addressed storage, factor IDs,
profile/ITA-round import, private output path, publish-safety/gitleaks regression tests).

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
