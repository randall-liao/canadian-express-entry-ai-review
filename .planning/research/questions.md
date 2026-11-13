# Research Questions

Open questions captured during exploration, for deeper investigation before or during planning.

## CRS Profile ↔ Document Substantiation Auditor (planted 2026-07-05)

Source: `/gsd-explore` session; concept in
`.planning/notes/crs-claim-substantiation-auditor.md`.

1. **PII-safe automated document extraction without heavy ML deps.**
   The applicant's real documents (IELTS/CELPIP/TEF score reports, ECA reports, employment
   reference letters, passport) must be read locally to pull structured values (scores, dates,
   credentials, NOC/hours/duration, issuer). Options to compare: render-to-image + agent-vision
   reading (user's stated preference for tables/forms) vs. `pdfminer.six` text extraction vs.
   `pymupdf`. Which is most reliable per document type while staying within the dependency-light,
   no-cloud, no-heavy-ML stack constraint? How should the mandatory "confirm what I read"
   checkpoint be surfaced so a silent misread can't undermine the fail-closed guarantee?

2. **Exact per-CRS-factor admissibility rules the corpus must ground.**
   For each scored factor, enumerate the corpus-citable rules the auditor checks:
   accepted test/document types, validity windows (e.g. language-test and ECA recency at
   ITA/submission), issuer/format requirements, and the value thresholds that map document
   content to CRS points. Confirm the current 16-family corpus already contains the authoritative
   basis for every factor's admissibility rule, or identify which sources must be crawled/added
   before the auditor can ground every verdict.
