---
title: "CRS Profile ↔ Document Substantiation Auditor — concept & decisions"
date: 2026-07-05
context: "Captured from /gsd-explore after v3.1 (22 document agents) shipped. Scopes the next direction: proving the applicant's claimed CRS score is substantiated by the documents they will actually submit."
---

# CRS Profile ↔ Document Substantiation Auditor

## Problem

The CRS score that earned the ITA is, at e-APR stage, only a **claim**. An IRCC officer
substantiates each scored factor against the uploaded documents. If a document does not back a
factor **at the level claimed** (language below the CLB scored, ECA that doesn't attest the
degree, reference letters that don't sum to the claimed months / NOC / hours), those points are
removed. If that drops the applicant below the round's cutoff, the application can be **refused**
— or, worse, flagged as misrepresentation. The user wants the system to catch a
profile ↔ document mismatch **before** submission.

This is a **cross-consistency check between two PII artifacts**: the applicant's CRS factor
breakdown and their actual document set.

## The three stacked checks (per claimed CRS factor)

1. **Presence** — a supporting document of the right type exists for the factor.
2. **Value** — the actual values inside the document meet the claimed level (e.g. IELTS shows the
   claimed CLB in every ability; ECA attests the claimed credential; reference letters sum to the
   claimed skilled-experience duration at ≥30h/week under the claimed NOC/TEER).
3. **Admissibility** — the document is a *kind* IRCC actually accepts as proof of that factor
   (accepted test type, within the validity window, correct issuer/form) — **grounded and cited**
   from IRPR / IRCC guidance / PDIs in the corpus.

Output per factor: `SUBSTANTIATED` / `GAP` / `AT-RISK`, each carrying a rule citation **and** a
pointer to the document evidence.

## Decisions locked in this conversation

- **Scope: all CRS factors IRCC supports** (the full grid), not just the high-value subset.
- **Modular agent pack** — split the auditor along IRCC's own factor grid so each agent stays
  context-light (same proven pattern as the 22 v3.1 document agents). Suggested modules:
  - **Core human capital** — age, education, official languages (first/second), Canadian work experience
  - **Spouse / common-law factors** — spouse education, language, Canadian work experience
  - **Skill transferability** — education×language, education×Canadian-experience,
    foreign-experience×language, foreign-experience×Canadian-experience,
    certificate-of-qualification×language
  - **Additional points** — provincial nomination, arranged employment, Canadian study,
    French-language skills, sibling in Canada
- **Local git-ignored candidate vault** — a database-like store (SQLite-style, mirroring the
  corpus DB pattern) for the CRS breakdown/profile **and** the raw document files, in its own
  directory that is git-ignored and guarded by the existing publish-safe / gitleaks gates so it
  can **never** be staged or pushed. Extends the established `personal/`-prefix PII-separation
  principle.
- **Extraction: fully automated (user's choice)** — the system reads the applicant's actual
  PDFs/scans (render-to-image + text) and extracts values into the vault, rather than asking the
  user to transcribe them.
- **Reuse frozen primitives** — the grounded verdicts run on the existing
  `search` → grounding-gate → contract-envelope pipeline. No new trust-path code (same discipline
  as v3.1).

## Key design caveat — the extraction trust gap

Fully-automated extraction (chosen over the hybrid confirm-first option) is the **one part that
is NOT grounded-by-construction**. If the extractor misreads "CLB 8" as "CLB 9," the system could
give false confidence. Everything downstream (the rule verdicts) stays fail-closed and cited, but
the **extracted inputs are a new trust surface**. Recommendation for planning: keep a
"confirm what I read" checkpoint (show extracted values back to the user) even in the automated
path, so the fail-closed guarantee isn't undermined by a silent misread. Note: the user prefers
PDFs rendered to images for visual reading (charts/tables/forms), not text-only extraction.

## Scale

Milestone-scale (new machinery: candidate vault + document extraction + grounded CRS-rule registry
+ modular auditor agent pack). Start with `/gsd-new-milestone`. See seed:
`.planning/seeds/crs-claim-substantiation-auditor.md`.
