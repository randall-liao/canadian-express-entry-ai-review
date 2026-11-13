---
title: "CRS Profile ↔ Document Substantiation Auditor — next milestone"
trigger_condition: "v3.1 shipped and archived (TRUE as of 2026-06-24). Start this milestone with /gsd-new-milestone."
planted_date: 2026-07-05
---

# Seed: CRS Profile ↔ Document Substantiation Auditor (next milestone)

## Why now

v3.1 completed the document-agent pack (22 grounded, CLI-agnostic agents that say *which*
documents are required and cite why). The system still cannot look at a document the applicant
*actually has* and say "this does not substantiate the CRS points you claimed." Proving the
claimed CRS score against the real document set is the natural, high-stakes next step — a mismatch
at e-APR means points removed → possible refusal or misrepresentation.

See `.planning/notes/crs-claim-substantiation-auditor.md` for the full concept and locked
decisions.

## What to do

Run `/gsd-new-milestone` to scope **"CRS Profile ↔ Document Substantiation Auditor"** (suggested
v3.2 or v4.0). Milestone-scale — do not append to the completed v3.1.

## Likely phase shape (for the roadmapper to refine)

1. **Candidate vault** — a local, git-ignored, database-like store (SQLite-style, mirroring the
   corpus DB) holding the applicant's CRS breakdown/profile and raw document files, in its own
   directory guarded by the existing publish-safe / gitleaks gates so it can never be staged.
2. **Document extraction** — fully automated: render-to-image + text extraction that pulls
   structured values (scores, dates, credentials, NOC/hours/duration, issuer) out of the real
   documents into the vault, with a "confirm what I read" checkpoint to protect the fail-closed
   guarantee (extraction is the one non-grounded step).
3. **Grounded CRS-rule registry** — per CRS factor, the corpus-cited admissibility rules:
   accepted document/test types, validity windows, thresholds, issuer requirements
   (IRPR / IRCC guidance / PDIs).
4. **Modular auditor agent pack** — one context-light agent per CRS factor group
   (core human capital · spouse/common-law · skill transferability · additional points), each
   running the frozen `search` → grounding-gate → contract pipeline and emitting cited
   `SUBSTANTIATED` / `GAP` / `AT-RISK` verdicts per factor.

## Acceptance bar (carried from project ethos)

- **Grounding-by-construction, fail-closed** for every admissibility/threshold verdict — each
  carries a citation resolving to a real corpus chunk (same bar as v3.0/v3.1).
- **All PII (profile + documents + extracted values) stays in the local git-ignored vault** —
  never the repo or the corpus DB.
- **Three checks per factor**: presence · value · admissibility.
- **All CRS factors IRCC supports** in scope (full grid), delivered as multiple small modules.

## Candidate requirement prefixes (for the fresh REQUIREMENTS.md)

- `VAULT-*` — local git-ignored candidate store + publish-safety guard
- `EXTRACT-*` — automated document extraction + confirm-what-I-read checkpoint
- `SUB-*` — grounded CRS-factor substantiation verdicts (presence/value/admissibility)
- Relates to previously deferred `VAL-01` / `VAL-02` (Layer-2 content validation & entailment) —
  this milestone realizes the *rule-matching* half (recency, amounts, format, translation)
  grounded and fail-closed; semantic entailment/NLI remains out of scope (needs a model, violates
  the no-vectors/no-cloud constraint).
